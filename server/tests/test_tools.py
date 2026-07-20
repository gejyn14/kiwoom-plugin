"""도구 목록·스키마·주문 argv 조립 고정, HTTP 인증 게이트."""

from __future__ import annotations

import pytest

from kiwoom_mcp.runner import ServeSettings
from kiwoom_mcp.server import _duration_seconds, build_server

READ_ONLY = ServeSettings(allow_orders=False)
ORDERS = ServeSettings(allow_orders=True)


async def _tools(settings):
    return {t.name: t for t in await build_server(settings).list_tools()}


# ── 도구 목록 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_only_manifest_pinned():
    assert set(await _tools(READ_ONLY)) == {
        "kiwoom_describe",
        "kiwoom_find",
        "kiwoom_run",
        "kiwoom_stream_snapshot",
        "kiwoom_order_validate",
    }


@pytest.mark.asyncio
async def test_orders_manifest_pinned():
    assert set(await _tools(ORDERS)) == {
        "kiwoom_describe",
        "kiwoom_find",
        "kiwoom_run",
        "kiwoom_stream_snapshot",
        "kiwoom_order_validate",
        "kiwoom_order",
    }


@pytest.mark.asyncio
async def test_order_tool_absent_without_allow_orders():
    """설정으로 끄는 게 아니라 목록에 없어야 한다 — 모델이 부를 수 없다."""
    assert "kiwoom_order" not in await _tools(READ_ONLY)


@pytest.mark.asyncio
async def test_order_tool_marks_money_risk():
    """설명에 실제 돈이 움직인다는 경고가 있어야 한다."""
    desc = (await _tools(ORDERS))["kiwoom_order"].description
    assert "실제" in desc and "dry_run" in desc


@pytest.mark.asyncio
async def test_dry_run_defaults_to_true_in_schema():
    schema = (await _tools(ORDERS))["kiwoom_order"].inputSchema
    assert schema["properties"]["dry_run"]["default"] is True
    assert schema["properties"]["confirm"]["default"] is False


@pytest.mark.asyncio
async def test_run_tool_requires_argv():
    schema = (await _tools(READ_ONLY))["kiwoom_run"].inputSchema
    assert "argv" in schema.get("required", [])


# ── 주문 argv 조립 ───────────────────────────────────


@pytest.fixture
def captured(monkeypatch):
    """run_cli를 가로채 조립된 argv만 본다 — 아무것도 실행하지 않는다."""
    seen = {}

    def fake(argv, settings, **kwargs):
        seen["argv"] = argv
        return {"exit_code": 0, "envelope": {"ok": True}}

    monkeypatch.setattr("kiwoom_mcp.server.run_cli", fake)
    return seen


async def _call_order(**kwargs):
    tools = build_server(ORDERS)._tool_manager
    return await tools.call_tool("kiwoom_order", kwargs)


@pytest.mark.asyncio
async def test_buy_dry_run_argv(captured):
    await _call_order(action="buy", symbol="005930", qty=10, price=70000)
    assert captured["argv"] == [
        "order", "buy", "005930", "10", "--price", "70000.0", "--dry-run",
    ]


@pytest.mark.asyncio
async def test_buy_transmit_requires_both_flags(captured):
    await _call_order(action="buy", symbol="005930", qty=10, price=70000,
                      dry_run=False, confirm=True, client_order_id="k-1")
    argv = captured["argv"]
    assert "--confirm" in argv and "--dry-run" not in argv
    assert argv[argv.index("--client-order-id") + 1] == "k-1"


@pytest.mark.asyncio
async def test_confirm_without_dry_run_false_still_previews(captured):
    """dry_run을 끄지 않으면 confirm=True여도 전송되지 않는다."""
    await _call_order(action="buy", symbol="005930", qty=1, confirm=True)
    assert "--dry-run" in captured["argv"] and "--confirm" not in captured["argv"]


@pytest.mark.asyncio
async def test_credit_variant_argv(captured):
    await _call_order(action="buy", symbol="005930", qty=5, variant="credit")
    assert captured["argv"][:3] == ["order", "credit", "buy"]


@pytest.mark.asyncio
async def test_gold_variant_argv(captured):
    await _call_order(action="sell", symbol="M04020000", qty=1, variant="gold")
    assert captured["argv"][:3] == ["order", "gold", "sell"]


@pytest.mark.asyncio
async def test_cancel_places_order_no_before_symbol(captured):
    await _call_order(action="cancel", symbol="005930", order_no="X99", qty=3)
    argv = captured["argv"]
    assert argv[:4] == ["order", "cancel", "X99", "005930"]
    assert argv[argv.index("--qty") + 1] == "3"


@pytest.mark.asyncio
async def test_modify_passes_price_positionally(captured):
    await _call_order(action="modify", symbol="005930", order_no="X99", qty=3, price=71000)
    assert captured["argv"][:6] == ["order", "modify", "X99", "005930", "3", "71000.0"]


@pytest.mark.asyncio
async def test_modify_without_order_no_is_rejected(captured):
    result = await _call_order(action="modify", symbol="005930", qty=1, price=100)
    assert "argv" not in captured, "order_no 없이 CLI까지 내려갔다"
    body = result[1] if isinstance(result, tuple) else result
    assert "INVALID_INPUT" in str(body)


# ── duration 파싱 ────────────────────────────────────


@pytest.mark.parametrize("text,seconds", [
    ("30s", 30), ("5m", 300), ("2h", 7200), ("bogus", 30), ("", 30), ("10", 30),
])
def test_duration_parsing(text, seconds):
    assert _duration_seconds(text) == seconds


# ── HTTP 인증 게이트 ─────────────────────────────────


def test_non_loopback_without_token_refuses_to_start(monkeypatch):
    """증권 계좌에 닿는 엔드포인트를 인증 없이 네트워크에 여는 모드는 없다."""
    from kiwoom_mcp.cli import main

    monkeypatch.delenv("KIWOOM_MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("KIWOOM_MCP_AUTH_TOKEN_FILE", raising=False)
    with pytest.raises(SystemExit) as exc:
        main(["--transport", "http", "--host", "0.0.0.0"])
    assert exc.value.code == 2


def test_loopback_without_token_is_allowed(monkeypatch):
    """루프백은 경고만 하고 뜬다 — 실제 서빙 직전에 멈춰 확인한다."""
    from kiwoom_mcp import cli as cli_mod

    monkeypatch.delenv("KIWOOM_MCP_AUTH_TOKEN", raising=False)
    started = {}
    monkeypatch.setattr(cli_mod, "_serve_http", lambda mcp, s: started.setdefault("host", s.host))
    cli_mod.main(["--transport", "http", "--host", "127.0.0.1"])
    assert started["host"] == "127.0.0.1"


def test_conflicting_auth_token_env_is_fatal(monkeypatch, tmp_path):
    from kiwoom_mcp.cli import main

    f = tmp_path / "t"
    f.write_text("x", encoding="utf-8")
    monkeypatch.setenv("KIWOOM_MCP_AUTH_TOKEN", "y")
    monkeypatch.setenv("KIWOOM_MCP_AUTH_TOKEN_FILE", str(f))
    with pytest.raises(SystemExit):
        main(["--transport", "http"])
