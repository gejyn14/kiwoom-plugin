"""argv 분류 고정.

리터럴로 고정한다 — 기대값을 상수에서 가져오면 상수를 통째로 바꿔도 통과한다.
그리고 **실제로 값이 갈리는 쌍**을 고른다: 같은 분류로 떨어지는 것만 모아 두면
분류기가 전부 "ok"를 돌려줘도 통과할 수 있다.
"""

from __future__ import annotations

import pytest

from kiwoom_mcp.policy import classify_argv, resolve_path

# (argv, 기대 분류) — 각 줄의 짝은 의도적으로 서로 다른 분류로 갈린다.
CASES = [
    # order: 전송하는 것 vs 하지 않는 것
    (["order", "buy", "005930", "1"], "mutation"),
    (["order", "sell", "005930", "1"], "mutation"),
    (["order", "validate", "buy", "005930", "1"], "ok"),
    (["order", "credit", "buy", "005930", "1"], "mutation"),
    (["order", "gold", "cancel", "X1", "M04020000"], "mutation"),
    # order condition: kiwoom-cli가 조건검색을 order 아래 두었을 뿐, 아무것도
    # 전송하지 않는 조회·구독이다. stop은 실시간 구독 해제이지 주문 취소가 아니다.
    (["order", "condition", "list"], "ok"),
    (["order", "condition", "search", "0"], "ok"),
    (["order", "condition", "realtime", "0"], "ok"),
    (["order", "condition", "stop", "0"], "ok"),
    # raw api: 같은 명령, api_id로만 갈린다
    (["api", "kt10000", "{}"], "mutation"),
    (["api", "ka10001", "{}"], "ok"),
    (["api", "list"], "ok"),
    # account: 하위 명령 하나로 갈린다
    (["account", "exchange", "apply"], "mutation"),
    (["account", "balance"], "ok"),
    (["account", "orders"], "ok"),
    # config/auth: 쓰기 vs 읽기
    (["config", "set", "domain", "prod"], "local_admin"),
    (["config", "setup"], "local_admin"),
    (["config", "show"], "ok"),
    (["config", "profiles"], "ok"),
    (["auth", "login"], "local_admin"),
    (["auth", "logout"], "local_admin"),
    (["auth", "status"], "ok"),
    # 터미널 점유
    (["watch", "005930"], "denied"),
    (["dashboard"], "ok"),
    # 평범한 조회
    (["stock", "info", "005930"], "ok"),
    (["market", "rank", "volume"], "ok"),
    (["stream", "quote", "005930"], "ok"),
]


@pytest.mark.parametrize("argv,expected", CASES, ids=[" ".join(a) for a, _ in CASES])
def test_classification(argv, expected):
    assert classify_argv(argv).kind == expected


def test_cases_actually_diverge():
    """이 표가 공허하지 않은지 스스로 확인한다.

    전부 같은 분류면 분류기가 상수를 돌려줘도 통과한다.
    """
    kinds = {expected for _, expected in CASES}
    assert kinds == {"ok", "mutation", "local_admin", "denied"}


# ── 옵션이 끼어들어도 경로 해석이 흔들리지 않아야 한다 ──


@pytest.mark.parametrize("argv,expected_path", [
    (["stock", "info", "005930"], ("stock", "info")),
    (["--fields", "a,b", "stock", "info", "005930"], ("stock", "info")),
    (["--fields=a,b", "stock", "info", "005930"], ("stock", "info")),
    (["--all-pages", "account", "balance"], ("account", "balance")),
    (["order", "buy", "005930", "1", "--confirm"], ("order", "buy")),
    (["order", "buy", "--price", "70000", "005930", "1"], ("order", "buy")),
])
def test_path_resolution_survives_options(argv, expected_path):
    assert resolve_path(argv)[0] == expected_path


def test_option_value_matching_a_command_name_is_not_a_command():
    """--fields의 값이 하위 명령 이름과 같아도 경로로 오인하면 안 된다.

    문자열을 훑는 분류기가 정확히 여기서 틀린다. Click 파서를 쓰는 이유다.
    """
    assert resolve_path(["--fields", "order", "stock", "info", "005930"])[0] == ("stock", "info")


def test_unknown_command_is_not_a_mutation():
    """해석할 수 없는 경로는 CLI 자신의 INVALID_INPUT으로 끝난다 — 주문에 닿지 않는다."""
    assert classify_argv(["nonexistent", "buy"]).kind == "ok"


def test_empty_argv():
    assert classify_argv([]).kind == "ok"
