"""토큰 자동 발급이 실제로 env 자격증명을 쓰는지 고정한다.

`credentials_available()`은 KIWOOM_APPKEY/KIWOOM_SECRETKEY를 보고 "발급할 수
있다"고 답하는데, kiwoom-cli 2.14.0은 그 두 변수를 **읽지 않는다**
(아는 것은 KIWOOM_ACCOUNT / KIWOOM_DOMAIN / KIWOOM_PROFILE / KIWOOM_TOKEN 넷뿐).
그래서 mint_token이 `issue_token()`을 인자 없이 부르면 kiwoom-cli는 설정·키체인만
뒤지다가 "appkey/secretkey not set"으로 죽고, 그 예외는 `except Exception:
return None`에 삼켜져 서버는 만료된 토큰을 계속 쓴다 — 밖에서는 8005로만 보인다.

검사가 확인하는 것: 서버가 자기가 검사한 그 자격증명을 **실제로 넘기는지**.
"""

from __future__ import annotations

import pytest

from kiwoom_mcp import runner
from kiwoom_mcp.cli import ServeSettings


class _RecordingClient:
    """issue_token이 받은 인자를 기록하는 가짜 KiwoomClient."""

    calls: list[dict[str, str | None]] = []

    def __init__(self, profile=None, **kwargs):
        self.profile = profile

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def issue_token(self, appkey=None, secretkey=None):
        type(self).calls.append({"appkey": appkey, "secretkey": secretkey})
        return "minted-token"


@pytest.fixture
def mint_env(monkeypatch):
    """가짜 클라이언트를 꽂고, 발급 throttle과 키체인 접근을 무력화한다."""
    import kiwoom_cli.auth as auth
    import kiwoom_cli.client as client_mod

    _RecordingClient.calls = []
    monkeypatch.setattr(client_mod, "KiwoomClient", _RecordingClient)
    # 키체인을 건드리면 macOS 승인 창이 뜬다 — 테스트에서는 읽을 수 있다고 둔다.
    monkeypatch.setattr(auth, "keychain_readable", lambda: True)
    monkeypatch.setattr(runner, "_last_mint_at", 0.0)
    for name in ("KIWOOM_APPKEY", "KIWOOM_SECRETKEY", "KIWOOM_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_mint_passes_env_credentials_through(mint_env):
    """env에 자격증명이 있으면 그대로 issue_token에 넘겨야 한다.

    이게 깨지면 kiwoom-cli가 설정·키체인만 보게 되고, 키체인이 없는 환경
    (컨테이너·CI)에서는 자동 발급이 **영원히** 실패한다.
    """
    mint_env.setenv("KIWOOM_APPKEY", "APPKEY-FROM-ENV")
    mint_env.setenv("KIWOOM_SECRETKEY", "SECRETKEY-FROM-ENV")

    token = runner.mint_token(ServeSettings())

    assert token == "minted-token"
    assert _RecordingClient.calls == [
        {"appkey": "APPKEY-FROM-ENV", "secretkey": "SECRETKEY-FROM-ENV"}
    ]


def test_mint_reads_the_file_variants(mint_env, tmp_path):
    """*_FILE도 같은 경로로 흘러야 한다 (도커 시크릿)."""
    (tmp_path / "ak").write_text("APPKEY-FROM-FILE\n", encoding="utf-8")
    (tmp_path / "sk").write_text("SECRETKEY-FROM-FILE\n", encoding="utf-8")
    mint_env.setenv("KIWOOM_APPKEY_FILE", str(tmp_path / "ak"))
    mint_env.setenv("KIWOOM_SECRETKEY_FILE", str(tmp_path / "sk"))

    runner.mint_token(ServeSettings())

    assert _RecordingClient.calls == [
        {"appkey": "APPKEY-FROM-FILE", "secretkey": "SECRETKEY-FROM-FILE"}
    ]


def test_mint_without_env_credentials_leaves_resolution_to_kiwoom_cli(mint_env):
    """env가 비어 있으면 None을 넘겨 kiwoom-cli의 설정·키체인 해석에 맡긴다.

    데스크톱 사용자(키체인에만 자격증명이 있는 경우)의 동작을 바꾸지 않는다.
    """
    runner.mint_token(ServeSettings())

    assert _RecordingClient.calls == [{"appkey": None, "secretkey": None}]


def test_mint_failure_is_reported_not_swallowed(mint_env, capsys):
    """발급이 실패하면 **조용히** 넘어가지 않는다.

    이 결함이 오래 숨어 있던 이유가 바로 침묵이다. 밖에서는 만료된 토큰으로
    인한 8005로만 보여서, 자동 발급이 애초에 동작한 적 없다는 사실이 가려졌다.
    """
    import kiwoom_cli.client as client_mod

    class _Failing(_RecordingClient):
        def issue_token(self, appkey=None, secretkey=None):
            raise RuntimeError("appkey/secretkey not set")

    mint_env.setattr(client_mod, "KiwoomClient", _Failing)
    mint_env.setenv("KIWOOM_APPKEY", "AK")
    mint_env.setenv("KIWOOM_SECRETKEY", "SK")

    assert runner.mint_token(ServeSettings()) is None
    assert "appkey/secretkey not set" in capsys.readouterr().err


# ── 이 파일이 공허하지 않은지 증명한다 ──


def test_recording_client_actually_records(mint_env):
    """가짜가 꽂히지 않으면 위 단언들은 무엇도 검사하지 못한다.

    (배선이 끊긴 채로 calls가 늘 비어 있으면 == [] 류의 단언이 통과해 버린다.)
    """
    import kiwoom_cli.client as client_mod

    assert client_mod.KiwoomClient is _RecordingClient
    runner.mint_token(ServeSettings())
    assert len(_RecordingClient.calls) == 1


# ── 만료 토큰이 자동 갱신을 발동시키는가 ──
#
# 실측: 만료된 토큰으로 일반 조회를 하면 키움이 돌려주는 것은
#   error.code = "UPSTREAM_ERROR", upstream_code = 3,
#   message   = "인증에 실패했습니다[8005:Token이 유효하지 않습니다]"
# 즉 구체적인 8005는 **메시지 문자열 안에만** 있고 upstream_code에는 3만 온다.
# _should_refresh가 error.code만 보면 만료 토큰에서 갱신이 영원히 안 걸린다.


def _envelope(code: str, message: str, upstream: int | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "upstream_code": upstream}}


def test_expired_token_triggers_refresh_even_when_code_is_generic():
    """실제로 받은 응답 모양 그대로 고정한다."""
    env = _envelope("UPSTREAM_ERROR", "인증에 실패했습니다[8005:Token이 유효하지 않습니다]", 3)
    assert runner._should_refresh(3, env) is True


def test_plain_auth_codes_still_trigger_refresh():
    assert runner._should_refresh(3, _envelope("TOKEN_EXPIRED", "만료", 8005)) is True
    assert runner._should_refresh(3, _envelope("AUTH_REQUIRED", "토큰 없음", 1513)) is True


def test_non_auth_failures_do_not_trigger_refresh():
    """넓게 잡으면 아무 상류 오류에나 재발급을 시도하게 된다.

    INVALID_CREDENTIALS(8001)도 재발급 대상이 아니다 — 키가 틀린 것이므로
    다시 발급해도 같은 결과이고, 호출만 두 배로 늘어난다.
    """
    assert runner._should_refresh(3, _envelope("INVALID_INPUT", "입력 오류[2:...]", 2)) is False
    assert runner._should_refresh(3, _envelope("UPSTREAM_ERROR", "서버 오류", 3)) is False
    assert runner._should_refresh(3, _envelope("UPSTREAM_ERROR", "검증 실패[8001:...]", 3)) is False
    assert runner._should_refresh(0, _envelope("UPSTREAM_ERROR", "[8005:...]", 3)) is False


def test_refresh_cases_actually_diverge():
    """전부 True거나 전부 False면 위 단언들은 상수를 검사하는 셈이다."""
    env = _envelope("UPSTREAM_ERROR", "인증 실패[8005:...]", 3)
    other = _envelope("UPSTREAM_ERROR", "검증 실패[8001:...]", 3)
    assert runner._should_refresh(3, env) != runner._should_refresh(3, other)
