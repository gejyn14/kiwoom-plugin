"""kiwoom-cli를 같은 프로세스 안에서 실행하고 envelope을 돌려준다.

**왜 CliRunner인가.** kiwoom-cli의 안전장치 — 주문 확인 게이트, 멱등성 원장,
페이지네이션 억제, exit code 매핑, envelope — 는 전부 활성 Click 컨텍스트에
매달려 있다. 별도의 파사드를 만들면 프로필·도메인 해석 경로가 하나 더 생기는데,
그 코드베이스에서 같은 종류의 결함이 세 번 재발한 이력이 있다. CliRunner는
kiwoom-cli 자신의 테스트 2000여 개가 고정하고 있는 바로 그 경로다.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from click.testing import CliRunner
from kiwoom_cli.main import cli

from . import policy

# CliRunner는 프로세스 전역 stdout을 갈아끼운다 — 동시 실행은 서로의 출력을
# 삼킨다. stdio 전송은 원래 순차지만 streamable HTTP는 아니므로 직렬화한다.
# 증권 API의 호출 한도와 원장 잠금을 생각하면 큐잉이 오히려 맞는 동작이다.
_CLI_LOCK = threading.Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kiwoom-cli")

_MINT_LOCK = threading.Lock()
_MIN_MINT_INTERVAL_SECONDS = 30.0

MAX_TIMEOUT_SECONDS = 300
AUTH_ERROR_CODES = ("AUTH_REQUIRED", "TOKEN_EXPIRED")


@dataclass
class ServeSettings:
    allow_orders: bool = False
    profile: str | None = None
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8765
    auth_token: str | None = None
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)


def _error(code: str, message: str, **extra: Any) -> dict:
    """CLI envelope과 같은 모양의 오류. MCP 계층이 만든 것은 MCP_ 접두사를 쓴다."""
    body = {
        "ok": False,
        "schema": "v1",
        "data": None,
        "meta": {},
        "error": {"code": code, "retryable": False, "message": message},
    }
    body["error"].update(extra)
    return body


def _parse_stdout(stdout: str) -> tuple[dict | None, list[dict]]:
    """stdout을 envelope 하나 또는 NDJSON 이벤트 목록으로 읽는다.

    stream 명령은 json 모드에서 REAL 이벤트당 한 줄을 낸다. 나머지는 한 덩어리.
    """
    text = stdout.strip()
    if not text:
        return None, []
    try:
        return json.loads(text), []
    except json.JSONDecodeError:
        pass
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return None, events


def _invoke(argv: list[str]) -> tuple[int, str]:
    with _CLI_LOCK:
        result = CliRunner().invoke(cli, argv, catch_exceptions=True)
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        return result.exit_code, result.stdout


def build_argv(argv: list[str], settings: ServeSettings, fields: str | None = None) -> list[str]:
    """전역 옵션을 서버가 정한 값으로 고정한다.

    -f/-p를 호출자가 넘기지 못하게 막는다: 출력 형식이 table이 되면 envelope
    계약이 깨지고 주문이 프롬프트에서 멈춘다. 프로필은 서버 기동 시 정해진다.
    """
    final = ["-f", "json"]
    if settings.profile:
        final += ["-p", settings.profile]
    if fields:
        final += ["--fields", fields]
    return final + argv


def _reject_global_flags(argv: list[str]) -> dict | None:
    for token in argv:
        if token in ("-f", "--format") or token.startswith("--format="):
            return _error("MCP_DENIED", "출력 형식은 json으로 고정됩니다 — argv에서 -f/--format을 빼세요.")
        if token in ("-p", "--profile") or token.startswith("--profile="):
            return _error("MCP_DENIED", "프로필은 서버 기동 시 결정됩니다 — argv에서 -p/--profile을 빼세요.")
    return None


def _stream_is_bounded(argv: list[str]) -> bool:
    return any(
        t == flag or t.startswith(f"{flag}=")
        for t in argv
        for flag in ("--max-events", "--duration", "--until")
    )


def run_cli(
    argv: list[str],
    settings: ServeSettings,
    *,
    fields: str | None = None,
    timeout: float = 60.0,
) -> dict:
    """분류 → 실행 → envelope. 차단된 호출은 아무것도 전송하지 않는다."""
    if not argv:
        return {"exit_code": 1, "envelope": _error("MCP_DENIED", "argv가 비어 있습니다.")}

    rejected = _reject_global_flags(argv)
    if rejected is not None:
        return {"exit_code": 1, "envelope": rejected}

    verdict = policy.classify_argv(argv)

    if verdict.kind == "denied":
        return {"exit_code": 1, "envelope": _error("MCP_DENIED", verdict.detail)}
    if verdict.kind == "local_admin":
        return {"exit_code": 1, "envelope": _error("MCP_ADMIN_BLOCKED", verdict.detail)}
    if verdict.kind == "mutation" and not settings.allow_orders:
        return {
            "exit_code": 1,
            "envelope": _error(
                "MCP_ORDERS_DISABLED",
                f"이 서버는 조회 전용으로 기동되었습니다 ({verdict.detail}). "
                "주문을 허용하려면 --allow-orders로 다시 시작하세요.",
            ),
        }

    if verdict.path[:1] == ("stream",) and not _stream_is_bounded(argv):
        return {
            "exit_code": 1,
            "envelope": _error(
                "MCP_DENIED",
                "stream 명령에는 --max-events / --duration / --until 중 하나가 필요합니다 "
                "(끝나지 않는 호출을 막기 위함). kiwoom_stream_snapshot 도구를 쓰세요.",
            ),
        }

    timeout = min(float(timeout), MAX_TIMEOUT_SECONDS)
    final_argv = build_argv(argv, settings, fields)

    try:
        exit_code, stdout = _EXECUTOR.submit(_invoke, final_argv).result(timeout=timeout)
    except TimeoutError:
        return {
            "exit_code": 2,
            "envelope": _error("MCP_TIMEOUT", f"{timeout:.0f}초 안에 끝나지 않았습니다."),
        }
    except Exception as exc:  # noqa: BLE001 — 서버가 죽는 것보다 오류를 돌려주는 쪽
        return {
            "exit_code": 2,
            "envelope": _error("MCP_INTERNAL", f"{type(exc).__name__}: {exc}"),
        }

    envelope, events = _parse_stdout(stdout)

    if _should_refresh(exit_code, envelope) and _refresh_token(settings):
        if verdict.kind == "mutation":
            # 주문은 서버 권한으로 자동 재시도하지 않는다. 재전송 여부는 멱등키를
            # 쥔 호출자가 결정해야 한다.
            if envelope is not None:
                envelope.setdefault("error", {})["detail"] = (
                    "토큰을 갱신했습니다 — 같은 client_order_id로 다시 호출하세요."
                )
            return {"exit_code": exit_code, "envelope": envelope, "events": events}
        exit_code, stdout = _EXECUTOR.submit(_invoke, final_argv).result(timeout=timeout)
        envelope, events = _parse_stdout(stdout)

    if events:
        return {"exit_code": exit_code, "events": events, "count": len(events)}
    return {"exit_code": exit_code, "envelope": envelope}


# ── 토큰 수명주기 ────────────────────────────────────

_last_mint_at = 0.0


def _should_refresh(exit_code: int, envelope: dict | None) -> bool:
    if exit_code != 3:
        return False
    if envelope is None:
        return True
    code = (envelope.get("error") or {}).get("code")
    return code in AUTH_ERROR_CODES


def credentials_available() -> bool:
    """env 자격증명으로 토큰을 발급할 수 있는지.

    **키체인은 보지 않는다.** macOS는 키체인 접근을 바이너리 단위로 승인하는데,
    처음 보는 실행 파일(uvx 캐시 등)이 읽기를 시도하면 GUI 승인 창을 띄운다.
    헤드리스로 뜬 MCP 서버에는 그 창에 답할 사람이 없어 무한정 멈춘다 —
    실제로 이 경로 때문에 서버가 initialize에 응답하지 못했다.

    자동 발급은 env 자격증명이 있을 때만 하는 기능이다. 키체인에만 자격증명이
    있는 데스크톱 사용자는 터미널에서 `kiwoom auth login`으로 발급한다.
    """
    return bool(_env_credential("KIWOOM_APPKEY") and _env_credential("KIWOOM_SECRETKEY"))


def _env_credential(name: str) -> str | None:
    """NAME 또는 NAME_FILE. 키체인을 건드리지 않는다."""
    direct = os.environ.get(name)
    if direct and direct.strip():
        return direct.strip()
    path = os.environ.get(f"{name}_FILE")
    if path:
        try:
            from pathlib import Path

            return Path(path).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


def mint_token(settings: ServeSettings) -> str | None:
    """au10001로 토큰을 발급하고 이 프로세스의 KIWOOM_TOKEN에 심는다.

    kiwoom-cli에서 KIWOOM_TOKEN은 이미 가장 높은 우선순위다. 여기에 넣으면
    이후의 모든 자식 호출이 별도 배선 없이 그 토큰을 쓴다 — 해석 경로를
    새로 만들지 않는다. 키체인이 없는 컨테이너에서는 저장을 시도하지 않는다.
    """
    import time

    from kiwoom_cli import auth
    from kiwoom_cli.client import KiwoomClient

    global _last_mint_at
    with _MINT_LOCK:
        now = time.monotonic()
        if now - _last_mint_at < _MIN_MINT_INTERVAL_SECONDS:
            return None
        _last_mint_at = now

        if not auth.keychain_readable():
            # 키체인에 못 쓰는 환경 — save_token이 죽지 않도록 env 모드로 선언한다.
            os.environ.setdefault("KIWOOM_TOKEN_STORAGE", "env")
        try:
            with KiwoomClient(profile=settings.profile) as client:
                token = client.issue_token()
        except Exception:
            return None
        if token:
            os.environ["KIWOOM_TOKEN"] = token
            return token
        return None


def _refresh_token(settings: ServeSettings) -> bool:
    if not credentials_available():
        return False
    return mint_token(settings) is not None
