"""스킬이 지시하는 명령이 실제로 존재하는지 고정한다.

스킬은 모델에게 "이 argv를 실행하라"고 지시하는 문서다. 그 argv가 kiwoom-cli의
**그룹**을 가리키면 실행은 `INVALID_INPUT`으로 끝난다 — 문서만 읽어서는 보이지
않고, 사용자가 쓸 때 처음 드러난다. 실제로 출하된 스킬 6개에 이런 argv가 있었다.

경로 해석은 서버가 쓰는 것과 **같은 Click 파서**(`policy.resolve_path`)로 한다.
손으로 토큰을 훑으면 문서 검증과 실제 실행이 갈리므로, 이 파일이 검증하는 대상과
런타임이 해석하는 대상이 같아야 한다.

kiwoom-cli의 명령 트리가 바뀌면 (리프가 그룹이 되거나 이름이 바뀌면) 여기가 먼저
깨진다 — 그게 이 파일의 목적이다.
"""

from __future__ import annotations

import re
from pathlib import Path

import click
import pytest
from kiwoom_cli.main import cli

from kiwoom_mcp.policy import classify_argv, resolve_path

PLUGINS_DIR = Path(__file__).resolve().parents[2] / "plugins"
READ_ONLY_PLUGIN = "kiwoom"
TRADER_PLUGIN = "kiwoom-trader"

# kiwoom_run(["a","b",...]) 의 argv 리터럴. 여는 괄호부터 첫 ']'까지가 argv이며,
# 뒤따르는 fields= 같은 키워드 인자는 포함하지 않는다.
# kiwoom_describe([...])는 일부러 잡지 않는다 — 그쪽은 그룹 경로가 정당하다.
_RUN_CALL = re.compile(r"kiwoom_run\(\s*\[(.*?)\]", re.DOTALL)
_STRING = re.compile(r'"([^"]*)"')


def _skill_files() -> list[Path]:
    return sorted(PLUGINS_DIR.glob("*/skills/*/SKILL.md"))


def _extract_argvs(text: str) -> list[list[str]]:
    return [_STRING.findall(inner) for inner in _RUN_CALL.findall(text)]


def _resolve_command(argv: list[str]) -> tuple[tuple[str, ...], click.Command]:
    """argv가 최종적으로 도달하는 Command 객체를 돌려준다.

    resolve_path는 경로만 주므로, 그 경로를 다시 걸어 객체를 얻는다. 도달한
    것이 Group이면 그 argv는 실행할 수 없다.
    """
    path, _rest = resolve_path(argv)
    command: click.Command = cli
    for name in path:
        ctx = click.Context(command, resilient_parsing=True)
        command = command.get_command(ctx, name)  # type: ignore[union-attr]
    return path, command


# 파일 경로와 argv를 함께 파라미터로 실어 실패 메시지에서 바로 찾을 수 있게 한다.
_CASES = [
    (path, argv)
    for path in _skill_files()
    for argv in _extract_argvs(path.read_text(encoding="utf-8"))
]


@pytest.mark.parametrize(
    "skill_path,argv",
    _CASES,
    ids=[f"{p.parent.parent.parent.name}/{p.parent.name}: {' '.join(a)}" for p, a in _CASES],
)
def test_skill_argv_resolves_to_a_leaf_command(skill_path: Path, argv: list[str]) -> None:
    """스킬의 모든 argv는 실행 가능한 리프에 도달해야 한다.

    그룹에서 멈추면 실행 시 `INVALID_INPUT`이 난다. 하위 명령 자리에 `<종류>`
    같은 자리표시자를 쓰면 여기서 걸린다 — 모델이 그대로 복사해 실행하기 때문에
    예시는 구체적인 리프여야 한다. (인자 자리의 자리표시자는 통과한다.)
    """
    path, command = _resolve_command(argv)
    assert not isinstance(command, click.Group), (
        f"{skill_path}: {argv} 는 그룹 'kiwoom {' '.join(path)}' 에서 멈춘다 — "
        f"하위 명령 중 하나를 지정해야 한다: {sorted(command.commands)}"  # type: ignore[union-attr]
    )


@pytest.mark.parametrize(
    "skill_path,argv",
    _CASES,
    ids=[f"{p.parent.parent.parent.name}/{p.parent.name}: {' '.join(a)}" for p, a in _CASES],
)
def test_read_only_plugin_skills_never_reference_orders(skill_path: Path, argv: list[str]) -> None:
    """조회 전용 플러그인의 스킬은 주문 계열 argv를 지시하지 않는다.

    지시해 봤자 `MCP_ORDERS_DISABLED`로 끝나므로, 그런 스킬이 있다는 것은
    두 플러그인의 스킬이 갈렸다는 뜻이다.
    """
    plugin = skill_path.parent.parent.parent.name
    kind = classify_argv(argv).kind
    if plugin == READ_ONLY_PLUGIN:
        assert kind == "ok", f"{skill_path}: {argv} 가 조회 전용 플러그인에서 {kind} 로 분류된다"
    else:
        assert kind in {"ok", "mutation"}, f"{skill_path}: {argv} → {kind}"


def test_shared_skills_are_identical_across_plugins() -> None:
    """두 플러그인이 공유하는 스킬은 바이트 동일해야 한다.

    스킬은 복사본으로 존재한다. 한쪽만 고치면 조용히 갈라지고, 어느 쪽이 맞는지는
    사용자가 겪기 전까지 아무도 모른다.
    """
    read_only = {p.parent.name: p for p in (PLUGINS_DIR / READ_ONLY_PLUGIN / "skills").glob("*/SKILL.md")}
    trader = {p.parent.name: p for p in (PLUGINS_DIR / TRADER_PLUGIN / "skills").glob("*/SKILL.md")}

    assert read_only, "조회 전용 플러그인에서 스킬을 하나도 찾지 못했다"
    missing = sorted(set(read_only) - set(trader))
    assert not missing, f"kiwoom-trader에 빠진 스킬: {missing}"

    for name, path in sorted(read_only.items()):
        assert path.read_bytes() == trader[name].read_bytes(), f"스킬 '{name}' 이 두 플러그인에서 갈렸다"


# ── 이 파일이 공허하지 않은지 스스로 증명한다 ──
#
# 추출기가 아무것도 찾지 못하면 위 파라미터화 테스트는 0건으로 전부 통과한다.
# 배선이 끊겨도 초록불이 뜨는 상태이므로, 먼저 이 검사들이 발동하는 것을 증명한다.


def test_extractor_actually_finds_argvs() -> None:
    assert len(_skill_files()) >= 5, f"스킬 파일을 찾지 못했다 (PLUGINS_DIR={PLUGINS_DIR})"
    assert len(_CASES) >= 10, f"kiwoom_run argv를 {len(_CASES)}개밖에 추출하지 못했다"


def test_extractor_handles_trailing_keyword_arguments() -> None:
    """`kiwoom_run([...], fields="a,b")` 에서 fields 값이 argv로 섞여 들어오면 안 된다."""
    extracted = _extract_argvs('kiwoom_run(["stock","info","005930"], fields="symbol,price")')
    assert extracted == [["stock", "info", "005930"]]


def test_leaf_check_rejects_a_group_and_accepts_a_leaf() -> None:
    """리프 판정이 실제로 갈리는 것을 증명한다.

    둘 다 통과시키는 판정이면 위 테스트는 무엇도 막지 못한다.
    `market theme` 는 라이브 서버에서 INVALID_INPUT을 내는 것을 확인한 실제 사례다.
    """
    assert isinstance(_resolve_command(["market", "theme"])[1], click.Group)
    assert not isinstance(_resolve_command(["market", "theme", "groups"])[1], click.Group)


def test_placeholder_in_command_position_is_caught() -> None:
    """자리표시자가 하위 명령 자리에 오면 그룹에서 멈춘다 (인자 자리는 통과)."""
    assert isinstance(_resolve_command(["market", "rank", "<종류>"])[1], click.Group)
    assert not isinstance(_resolve_command(["stock", "info", "<코드>"])[1], click.Group)
