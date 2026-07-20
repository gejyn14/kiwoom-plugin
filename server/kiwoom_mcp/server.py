"""MCP 도구 정의.

명령마다 도구를 하나씩 만들지 않는다 — kiwoom-cli는 200개가 넘는 명령을 갖고
있고, 그만큼의 도구 목록은 모든 클라이언트의 컨텍스트를 잡아먹는다. 대신
탐색 도구(describe/find)로 표면을 찾게 하고, 실행은 범용 run 하나로 받는다.
주문만 별도 도구로 두는데, 이쪽은 dry_run/confirm/멱등키를 파라미터로 드러내
모델이 안전 계약을 우회할 수 없게 하기 위함이다.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .runner import ServeSettings, run_cli

_ENVELOPE_CONTRACT = """
반환값은 kiwoom-cli의 envelope입니다:
  {"exit_code": 0|1|2|3, "envelope": {"ok", "schema", "data", "meta", "error"}}
exit_code: 0=성공, 1=입력오류, 2=API오류, 3=인증필요.
data는 정규화된 필드 + data.raw(원본). meta.env가 "prod"인지 "mock"인지
반드시 확인하세요 — prod는 실제 계좌입니다. 실패는 error.code로 분기하세요.
""".strip()


def build_server(settings: ServeSettings) -> FastMCP:
    mcp = FastMCP(
        "kiwoom",
        instructions=(
            "키움증권 REST API 236종을 kiwoom-cli를 통해 사용합니다. "
            "먼저 kiwoom_describe로 명령 표면을 확인하고 kiwoom_run으로 실행하세요. "
            + ("주문이 활성화되어 있습니다 — dry_run으로 먼저 확인하세요."
               if settings.allow_orders else "이 서버는 조회 전용입니다.")
        ),
        host=settings.host,
        port=settings.port,
        stateless_http=True,
    )

    @mcp.tool()
    def kiwoom_describe(
        command_path: list[str] | None = None,
        paths_only: bool = True,
        depth: int | None = None,
    ) -> dict[str, Any]:
        """kiwoom-cli의 명령 트리를 조회합니다 (에이전트용 자기서술).

        paths_only=True(기본)는 경로 목록만 돌려주어 토큰을 아낍니다. 특정
        명령의 인자·옵션 스키마가 필요하면 command_path를 주고 paths_only=False로
        호출하세요. 예: command_path=["order","buy"], paths_only=False
        """
        argv = ["describe", *(command_path or [])]
        if paths_only:
            argv.append("--paths")
        elif depth is not None:
            argv += ["--depth", str(depth)]
        return run_cli(argv, settings)

    @mcp.tool()
    def kiwoom_find(keyword: str) -> dict[str, Any]:
        """키워드로 명령과 API를 찾습니다. 무엇을 쓸지 모를 때 먼저 호출하세요."""
        return run_cli(["find", keyword], settings)

    @mcp.tool()
    def kiwoom_run(
        argv: list[str],
        fields: str | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """kiwoom-cli 명령을 실행합니다. 'kiwoom' 뒤의 토큰만 넘기세요.

        예: ["stock","info","005930"], ["account","balance","--market","kr"]

        -f/--format과 -p/--profile은 서버가 고정하므로 넘기면 거부됩니다.
        fields에 "symbol,price"처럼 주면 응답을 그 키로만 투영해 토큰을 아낍니다.

        조회 전용으로 기동된 서버에서는 주문 계열 경로가 MCP_ORDERS_DISABLED로
        거부되며 아무것도 전송되지 않습니다.
        """
        return run_cli(argv, settings, fields=fields, timeout=timeout_seconds)

    @mcp.tool()
    def kiwoom_stream_snapshot(
        stream_type: str,
        symbols: list[str],
        max_events: int = 20,
        duration: str = "30s",
    ) -> dict[str, Any]:
        """실시간 스트림에서 정해진 개수/시간만큼 이벤트를 받아 돌려줍니다.

        stream_type은 kiwoom_describe(["stream"])로 확인하세요 (quote, orderbook 등).
        반드시 유한하게 끝납니다 — max_events나 duration 중 먼저 도달하는 쪽에서
        종료합니다.
        """
        max_events = max(1, min(int(max_events), 200))
        argv = ["stream", stream_type, *symbols,
                "--max-events", str(max_events), "--duration", duration]
        return run_cli(argv, settings, timeout=min(_duration_seconds(duration) + 15, 300))

    @mcp.tool()
    def kiwoom_order_validate(
        side: str,
        symbol: str,
        qty: int,
        price: float | None = None,
        order_type: str | None = None,
    ) -> dict[str, Any]:
        """주문 사전점검 (read-only, 아무것도 전송하지 않음).

        symbol_ok / market_open / sufficient_balance / price_ok를 확인합니다.
        주문 전에 항상 먼저 호출하세요. side는 "buy" 또는 "sell".
        """
        argv = ["order", "validate", side, symbol, str(qty)]
        if price is not None:
            argv += ["--price", str(price)]
        if order_type:
            argv += ["--type", order_type]
        return run_cli(argv, settings)

    if settings.allow_orders:
        _register_order_tool(mcp, settings)

    return mcp


def _register_order_tool(mcp: FastMCP, settings: ServeSettings) -> None:
    """--allow-orders일 때만 등록한다. 미등록이면 tools/list에 아예 없다."""

    @mcp.tool()
    def kiwoom_order(
        action: str,
        symbol: str,
        qty: int = 0,
        variant: str = "stock",
        price: float | None = None,
        order_type: str | None = None,
        exchange: str | None = None,
        order_no: str | None = None,
        dry_run: bool = True,
        confirm: bool = False,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """주문을 전송합니다. **실제 돈이 움직입니다.**

        권장 순서: kiwoom_order_validate → dry_run=True → dry_run=False, confirm=True.

        action: buy | sell | modify | cancel (modify/cancel은 order_no 필수)
        variant: stock | credit | gold (미국주식은 티커로 자동 판별)
        dry_run: 기본 True — 전송하지 않고 보낼 body만 돌려줍니다.
        confirm: dry_run=False일 때 반드시 True여야 전송됩니다.
        client_order_id: 멱등키. 같은 키+같은 내용 재호출은 재전송하지 않고
          이전 응답을 돌려줍니다. 재시도할 때 반드시 같은 값을 쓰세요.

        전송 전에 envelope의 meta.env를 확인하세요 — "prod"는 실계좌입니다.
        """
        argv = ["order"]
        if variant in ("credit", "gold"):
            argv.append(variant)
        argv.append(action)

        if action in ("modify", "cancel"):
            if not order_no:
                return {"exit_code": 1, "envelope": {
                    "ok": False, "schema": "v1", "data": None, "meta": {},
                    "error": {"code": "INVALID_INPUT", "retryable": False,
                              "message": f"{action}에는 order_no가 필요합니다."},
                }}
            argv.append(order_no)

        argv.append(symbol)

        if action == "cancel":
            if qty:
                argv += ["--qty", str(qty)]
        else:
            argv.append(str(qty))

        if action == "modify":
            argv.append(str(price if price is not None else 0))
        elif price is not None:
            argv += ["--price", str(price)]

        if order_type:
            argv += ["--type", order_type]
        if exchange:
            argv += ["--exchange", exchange]
        if client_order_id:
            argv += ["--client-order-id", client_order_id]

        # --dry-run이 --confirm보다 우선한다 (kiwoom-cli 계약). 실수로 둘 다
        # 켜져도 전송되지 않는 방향이므로 그대로 둔다.
        if dry_run:
            argv.append("--dry-run")
        elif confirm:
            argv.append("--confirm")

        return run_cli(argv, settings, timeout=60)


def _duration_seconds(duration: str) -> int:
    """"30s" / "5m" / "2h" → 초. 해석할 수 없으면 보수적으로 30초."""
    try:
        unit, value = duration[-1], int(duration[:-1])
    except (ValueError, IndexError):
        return 30
    return {"s": value, "m": value * 60, "h": value * 3600}.get(unit, 30)
