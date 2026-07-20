"""runner: envelope 전달, 전역 옵션 고정, 차단이 실제로 전송을 막는지."""

from __future__ import annotations

import json

import pytest

from kiwoom_mcp.runner import ServeSettings, build_argv, run_cli

READ_ONLY = ServeSettings(allow_orders=False)
ORDERS = ServeSettings(allow_orders=True)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """실제 ~/.kiwoom과 개발자 셸의 KIWOOM_* 로부터 격리한다."""
    from kiwoom_cli import config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")
    for name in [k for k in list(__import__("os").environ) if k.startswith("KIWOOM_")]:
        monkeypatch.delenv(name, raising=False)


# ── 전역 옵션 고정 ────────────────────────────────────


def test_format_is_forced_to_json():
    assert build_argv(["stock", "info", "005930"], READ_ONLY)[:2] == ["-f", "json"]


def test_profile_is_injected_when_set():
    argv = build_argv(["account", "balance"], ServeSettings(profile="isa"))
    assert argv[:4] == ["-f", "json", "-p", "isa"]


def test_profile_absent_when_unset():
    assert "-p" not in build_argv(["account", "balance"], READ_ONLY)


def test_fields_projection():
    argv = build_argv(["stock", "info", "005930"], READ_ONLY, fields="symbol,price")
    assert "--fields" in argv and "symbol,price" in argv


@pytest.mark.parametrize("bad", [
    ["-f", "table", "stock", "info", "005930"],
    ["--format", "csv", "stock", "info", "005930"],
    ["--format=table", "stock", "info", "005930"],
    ["-p", "other", "account", "balance"],
    ["--profile", "other", "account", "balance"],
    ["--profile=other", "account", "balance"],
])
def test_caller_cannot_override_global_flags(bad):
    result = run_cli(bad, READ_ONLY)
    assert result["envelope"]["error"]["code"] == "MCP_DENIED"


# ── 차단이 실제로 전송을 막는지 (공허하지 않은 스파이) ──


class _Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("차단되어야 할 호출이 네트워크로 나갔다")


def test_spy_fires_on_an_allowed_path(monkeypatch):
    """스파이가 실제로 발동하는지 먼저 증명한다.

    이 테스트가 없으면 아래 '전송되지 않았다' 테스트는 스파이가 배선되지
    않았어도 통과한다 — 아무것도 막지 못하는 고정이 된다.
    """
    fired = []
    monkeypatch.setattr(
        "kiwoom_cli.client.KiwoomClient.request",
        lambda self, *a, **k: fired.append(a) or ({}, {}),
    )
    run_cli(["stock", "info", "005930"], READ_ONLY)
    assert fired, "스파이가 발동하지 않았다 — 이 배선으로는 아무것도 검증할 수 없다"


@pytest.mark.parametrize("argv", [
    ["order", "buy", "005930", "1", "--confirm"],
    ["order", "sell", "005930", "1", "--confirm"],
    ["account", "exchange", "apply", "--confirm"],
    ["api", "kt10000", "{}", "--confirm"],
])
def test_blocked_calls_transmit_nothing(monkeypatch, argv):
    spy = _Spy()
    monkeypatch.setattr("kiwoom_cli.client.KiwoomClient.request", spy)
    result = run_cli(argv, READ_ONLY)
    assert result["envelope"]["error"]["code"] == "MCP_ORDERS_DISABLED"
    assert spy.calls == []


def test_local_admin_transmits_nothing_even_with_orders(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr("kiwoom_cli.client.KiwoomClient.request", spy)
    result = run_cli(["config", "set", "domain", "prod"], ORDERS)
    assert result["envelope"]["error"]["code"] == "MCP_ADMIN_BLOCKED"
    assert spy.calls == []


def test_local_admin_does_not_write_config(tmp_path):
    """config set이 차단된다면 설정 파일이 생기지 않아야 한다."""
    from kiwoom_cli import config

    run_cli(["config", "set", "domain", "prod"], ORDERS)
    assert not config.CONFIG_FILE.exists()


# ── envelope 전달 ────────────────────────────────────


def test_envelope_passes_through_intact():
    result = run_cli(["describe", "--paths"], READ_ONLY)
    env = result["envelope"]
    assert result["exit_code"] == 0
    assert env["ok"] is True and env["schema"] == "v1"
    assert "meta" in env and "profile" in env["meta"]


def test_input_error_maps_to_exit_1():
    result = run_cli(["api", "not-a-real-api-id", "{}"], READ_ONLY)
    assert result["exit_code"] == 1
    assert result["envelope"]["ok"] is False


def test_auth_error_maps_to_exit_3():
    """토큰이 없으면 exit 3 — 인증 필요."""
    result = run_cli(["stock", "info", "005930"], READ_ONLY)
    assert result["exit_code"] == 3
    assert result["envelope"]["error"]["code"] == "AUTH_REQUIRED"


def test_fields_projection_reaches_the_envelope(monkeypatch):
    monkeypatch.setattr(
        "kiwoom_cli.client.KiwoomClient.request",
        lambda self, *a, **k: ({"stk_cd": "005930", "cur_prc": "+70000"}, {}),
    )
    result = run_cli(["stock", "info", "005930"], READ_ONLY, fields="symbol")
    data = result["envelope"]["data"]
    assert "raw" not in data


# ── stream 경계 ──────────────────────────────────────


def test_unbounded_stream_rejected():
    assert run_cli(["stream", "quote", "005930"], READ_ONLY)["envelope"]["error"]["code"] == "MCP_DENIED"


@pytest.mark.parametrize("bound", [
    ["--max-events", "1"], ["--duration", "5s"], ["--until", "2026-01-01T00:00:00"],
])
def test_bounded_stream_passes_the_gate(bound):
    result = run_cli(["stream", "quote", "005930", *bound], READ_ONLY)
    code = (result.get("envelope") or {}).get("error", {}).get("code")
    assert code != "MCP_DENIED"


def test_empty_argv_rejected():
    assert run_cli([], READ_ONLY)["envelope"]["error"]["code"] == "MCP_DENIED"


# ── NDJSON ───────────────────────────────────────────


def test_ndjson_lines_become_events():
    from kiwoom_mcp.runner import _parse_stdout

    lines = "\n".join(json.dumps({"ok": True, "data": {"n": i}}) for i in range(3))
    envelope, events = _parse_stdout(lines)
    assert envelope is None
    assert len(events) == 3


def test_single_document_becomes_envelope():
    from kiwoom_mcp.runner import _parse_stdout

    envelope, events = _parse_stdout(json.dumps({"ok": True, "data": None}))
    assert envelope == {"ok": True, "data": None} and events == []
