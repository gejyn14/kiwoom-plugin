"""서버가 실제로 뜨고, 도구 목록이 게이트를 따르고, 조회 전용이 지켜지는지."""

from __future__ import annotations

import pytest

from kiwoom_mcp.runner import ServeSettings, run_cli
from kiwoom_mcp.server import build_server

READ_ONLY = ServeSettings(allow_orders=False)
ORDERS = ServeSettings(allow_orders=True)


async def _tool_names(settings: ServeSettings) -> set[str]:
    tools = await build_server(settings).list_tools()
    return {t.name for t in tools}


@pytest.mark.asyncio
async def test_read_only_manifest_has_no_order_tool():
    names = await _tool_names(READ_ONLY)
    assert names == {
        "kiwoom_describe",
        "kiwoom_find",
        "kiwoom_run",
        "kiwoom_stream_snapshot",
        "kiwoom_order_validate",
    }


@pytest.mark.asyncio
async def test_allow_orders_adds_exactly_one_tool():
    assert await _tool_names(ORDERS) - await _tool_names(READ_ONLY) == {"kiwoom_order"}


def test_describe_returns_a_real_envelope():
    """탐색은 토큰 없이 동작해야 한다 — 네트워크를 타지 않는다."""
    result = run_cli(["describe", "--paths"], READ_ONLY)
    assert result["exit_code"] == 0
    assert result["envelope"]["ok"] is True
    paths = [row["path"] for row in result["envelope"]["data"]]
    assert "kiwoom order buy" in paths


def test_order_blocked_when_read_only():
    result = run_cli(["order", "buy", "005930", "1", "--confirm"], READ_ONLY)
    assert result["exit_code"] == 1
    assert result["envelope"]["error"]["code"] == "MCP_ORDERS_DISABLED"


def test_order_validate_allowed_when_read_only():
    """read-only 사전점검은 조회 전용 서버에서도 막히면 안 된다."""
    result = run_cli(["order", "validate", "buy", "005930", "1"], READ_ONLY)
    assert result["envelope"]["error"]["code"] != "MCP_ORDERS_DISABLED"


def test_local_admin_blocked_even_with_orders():
    result = run_cli(["config", "set", "domain", "prod"], ORDERS)
    assert result["envelope"]["error"]["code"] == "MCP_ADMIN_BLOCKED"


def test_tty_command_denied():
    """watch는 Rich Live TUI다 — 터미널을 점유하고 끝나지 않는다."""
    assert run_cli(["watch", "005930"], ORDERS)["envelope"]["error"]["code"] == "MCP_DENIED"


def test_format_flag_rejected():
    result = run_cli(["-f", "table", "stock", "info", "005930"], READ_ONLY)
    assert result["envelope"]["error"]["code"] == "MCP_DENIED"


def test_unbounded_stream_rejected():
    result = run_cli(["stream", "quote", "005930"], READ_ONLY)
    assert result["envelope"]["error"]["code"] == "MCP_DENIED"


def test_bounded_stream_passes_the_gate():
    """경계가 있으면 게이트를 통과한다 — 위 테스트가 공허하지 않음을 보인다."""
    result = run_cli(["stream", "quote", "005930", "--max-events", "1"], READ_ONLY)
    assert result.get("envelope", {}).get("error", {}).get("code") != "MCP_DENIED"


def test_startup_never_reads_keychain(monkeypatch):
    """기동 경로가 키체인을 건드리면 안 된다.

    macOS는 키체인 접근을 바이너리 단위로 승인한다. 처음 보는 실행 파일(uvx
    캐시 등)이 읽으려 하면 GUI 승인 창이 뜨고, 헤드리스로 뜬 MCP 서버에는 답할
    사람이 없어 무한정 멈춘다. 실제로 이것 때문에 플러그인이 "Failed to
    connect"으로 끝났다 — initialize에 응답조차 하지 못했다.
    """
    import keyring

    def explode(*args, **kwargs):
        raise AssertionError("기동 중 키체인 접근 — 헤드리스에서 멈출 수 있다")

    monkeypatch.setattr(keyring, "get_password", explode)
    monkeypatch.setattr(keyring, "set_password", explode)

    from kiwoom_mcp.cli import _banner
    from kiwoom_mcp.runner import credentials_available

    assert credentials_available() in (True, False)
    _banner(READ_ONLY)


def test_credentials_available_reads_env_only(monkeypatch, tmp_path):
    from kiwoom_mcp.runner import credentials_available

    for n in ("KIWOOM_APPKEY", "KIWOOM_SECRETKEY", "KIWOOM_APPKEY_FILE", "KIWOOM_SECRETKEY_FILE"):
        monkeypatch.delenv(n, raising=False)
    assert credentials_available() is False

    monkeypatch.setenv("KIWOOM_APPKEY", "a")
    assert credentials_available() is False  # secretkey 없음

    secret = tmp_path / "sk"
    secret.write_text("b\n", encoding="utf-8")
    monkeypatch.setenv("KIWOOM_SECRETKEY_FILE", str(secret))
    assert credentials_available() is True
