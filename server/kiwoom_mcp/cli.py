"""`kiwoom-mcp` 실행 진입점."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from . import __version__
from .runner import ServeSettings, credentials_available

LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def _env_or_file(name: str) -> str | None:
    """NAME 또는 NAME_FILE. 컨테이너 시크릿은 파일로 마운트된다."""
    direct = os.environ.get(name)
    path = os.environ.get(f"{name}_FILE")
    if direct and path:
        _die(f"{name}와 {name}_FILE이 동시에 설정되었습니다. 하나만 쓰세요.")
    if direct:
        return direct.strip() or None
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip() or None
        except OSError as exc:
            _die(f"{name}_FILE을 읽을 수 없습니다 ({path}): {exc}")
    return None


def _die(message: str) -> None:
    print(f"kiwoom-mcp: {message}", file=sys.stderr)
    raise SystemExit(2)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kiwoom-mcp",
        description="키움증권 kiwoom-cli를 MCP 서버로 노출합니다.",
    )
    parser.add_argument("--version", action="version", version=f"kiwoom-mcp {__version__}")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio",
                        help="기본 stdio. http는 streamable HTTP.")
    parser.add_argument("--host", default="127.0.0.1", help="http 바인드 주소 (기본 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="http 포트 (기본 8765)")
    parser.add_argument("--profile", default=os.environ.get("KIWOOM_PROFILE") or None,
                        help="kiwoom-cli 프로필. 모든 호출에 고정 적용됩니다.")
    parser.add_argument("--allow-orders", action="store_true",
                        default=_env_flag("KIWOOM_MCP_ALLOW_ORDERS"),
                        help="주문 도구를 활성화합니다 (기본: 조회 전용).")
    parser.add_argument("--allowed-host", action="append", default=[],
                        help="http Host 헤더 허용 목록에 추가합니다.")
    return parser


def _resolve_http_auth(settings: ServeSettings) -> None:
    """비루프백 바인드에는 토큰을 강제한다.

    증권 계좌에 닿는 엔드포인트를 네트워크에 인증 없이 여는 모드는 두지 않는다.
    조회 전용이어도 마찬가지다 — 잔고와 보유종목도 남에게 보일 것은 아니다.
    """
    token = _env_or_file("KIWOOM_MCP_AUTH_TOKEN")
    settings.auth_token = token
    is_loopback = settings.host in LOOPBACK_HOSTS
    if not is_loopback and not token:
        _die(
            f"--host {settings.host}는 루프백이 아닙니다. KIWOOM_MCP_AUTH_TOKEN "
            "(또는 _FILE)을 설정하세요. 컨테이너에서는 0.0.0.0 바인드가 정상이며, "
            "호스트 노출은 -p 127.0.0.1:8765:8765로 제한하세요."
        )
    if is_loopback and not token:
        print("kiwoom-mcp: [경고] 인증 토큰 없이 루프백에 바인드합니다 — "
              "이 머신의 모든 로컬 프로세스가 호출할 수 있습니다.", file=sys.stderr)


def _banner(settings: ServeSettings) -> None:
    """기동 상태를 stderr로 알린다 (stdout은 stdio 전송이 쓴다)."""
    from kiwoom_cli import config

    try:
        env = config.get_domain_key(settings.profile)
    except Exception:
        env = "unknown"
    # 자격증명 출처는 보고하지 않는다: config.appkey_source()가 키체인을 읽고,
    # 그 읽기가 macOS에서 GUI 승인 창을 띄워 서버를 멈추게 할 수 있다.
    # env 자격증명 여부만 키체인 없이 확인한다.
    creds = "환경변수" if credentials_available() else "환경변수 없음 (키체인 또는 KIWOOM_TOKEN 사용)"

    lines = [
        f"kiwoom-mcp {__version__} — transport={settings.transport}",
        f"  도메인: {env}" + ("  [실거래]" if env == "prod" else ""),
        f"  프로필: {settings.profile or '(기본)'}",
        f"  자격증명: {creds}",
        f"  주문: {'허용 (--allow-orders)' if settings.allow_orders else '차단 (조회 전용)'}",
    ]
    if settings.transport == "http":
        lines.append(f"  바인드: {settings.host}:{settings.port}  "
                     f"인증: {'bearer' if settings.auth_token else '없음'}")
    print("\n".join(lines), file=sys.stderr)


def _serve_http(mcp, settings: ServeSettings) -> None:
    import uvicorn
    from starlette.responses import JSONResponse

    app = mcp.streamable_http_app()
    expected = settings.auth_token

    if expected:
        async def auth_middleware(scope, receive, send):
            if scope["type"] != "http":
                await app(scope, receive, send)
                return
            headers = dict(scope.get("headers") or [])
            presented = headers.get(b"authorization", b"").decode()
            expected_header = f"Bearer {expected}"
            if not secrets.compare_digest(presented, expected_header):
                response = JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
            await app(scope, receive, send)

        served = auth_middleware
    else:
        served = app

    uvicorn.run(served, host=settings.host, port=settings.port, log_level="info")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    settings = ServeSettings(
        allow_orders=args.allow_orders,
        profile=args.profile,
        transport=args.transport,
        host=args.host,
        port=args.port,
        allowed_hosts=tuple(args.allowed_host),
    )

    if settings.transport == "http":
        _resolve_http_auth(settings)
    elif _env_or_file("KIWOOM_MCP_AUTH_TOKEN"):
        print("kiwoom-mcp: [알림] stdio 전송에는 인증 개념이 없어 "
              "KIWOOM_MCP_AUTH_TOKEN을 무시합니다.", file=sys.stderr)

    _banner(settings)

    # 기동 시에는 토큰을 만지지 않는다. auth.load_token()이 키체인을 읽는데,
    # macOS는 처음 보는 바이너리의 키체인 접근에 GUI 승인 창을 띄우고, 헤드리스
    # MCP 서버에는 그 창에 답할 사람이 없다 — 서버가 initialize에 응답하지 못하고
    # 클라이언트는 "Failed to connect"으로 끝난다.
    #
    # 토큰은 첫 호출에서 필요할 때 확보한다. runner가 exit 3(AUTH_REQUIRED/
    # TOKEN_EXPIRED)을 보면 env 자격증명으로 발급을 시도한다. MCP 서버는 빨리
    # 뜨고 일은 늦게 하는 편이 옳기도 하다.
    from .server import build_server

    mcp = build_server(settings)

    if settings.transport == "http":
        _serve_http(mcp, settings)
    else:
        mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
