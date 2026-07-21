"""무엇을 MCP로 실행하게 둘지 분류한다.

argv를 **Click의 파서로** 해석한다. 문자열을 직접 훑으면 `--opt=value`,
옵션 사이에 끼인 인자, 축약 옵션에서 실제 실행 경로와 분류가 갈릴 수 있다.
분류기가 "조회"라고 판단한 argv가 실제로는 주문을 보내는 상황을 원리적으로
막으려면 실행과 같은 해석기를 써야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import click
from kiwoom_cli.api_spec import MUTATION_APIS
from kiwoom_cli.main import cli

Kind = Literal["ok", "denied", "local_admin", "mutation"]

# 어떤 모드에서도 MCP로 실행하지 않는다.
#   mcp*  — 서버가 자기 자신을 띄우는 재귀
#   watch — Rich Live TUI. 터미널을 점유하고 끝나지 않는다
DENIED_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("mcp",),
    ("watch",),
)

# 로컬 상태를 바꾸는 명령. --allow-orders와 무관하게 차단한다: 서버의 자격증명
# 수명주기는 서버가 소유한다. 모델이 config.toml을 다시 쓰거나, 토큰을 폐기하거나,
# 멱등성 원장을 잘라내는 것은 어느 모드에서도 이득이 없다.
# (config show/profiles, auth status 같은 조회는 통과시킨다.)
LOCAL_ADMIN_PATHS: tuple[tuple[str, ...], ...] = (
    ("config", "setup"),
    ("config", "set"),
    ("config", "use"),
    ("config", "prune-ledger"),
    ("auth", "login"),
    ("auth", "logout"),
)

# --allow-orders가 있어야 실행되는 경로.
MUTATION_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("order",),
    ("account", "exchange", "apply"),
)

# order 하위지만 아무것도 전송하지 않는 경로.
#   validate   — read-only 사전점검
#   condition  — 조건검색 (list/search/realtime/stop). kiwoom-cli가 order 아래
#                두었을 뿐 조회·구독이며, stop은 실시간 구독 해제이지 주문 취소가
#                아니다. 여기 없으면 조회 전용 플러그인에서 조건검색이 통째로
#                막힌다 (ka10171~ka10174).
MUTATION_EXCEPTIONS: tuple[tuple[str, ...], ...] = (
    ("order", "validate"),
    ("order", "condition"),
)


@dataclass(frozen=True)
class Classification:
    path: tuple[str, ...]
    kind: Kind
    detail: str = ""


def _starts_with(path: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return path[: len(prefix)] == prefix


def _remaining_args(ctx: click.Context) -> list[str]:
    """Group.parse_args 이후 남은 인자 전부.

    Click의 Group.parse_args는 첫 번째 남은 토큰(= 하위 명령 이름)을 반환값이
    아니라 protected_args에 넣는다. 반환값만 보면 하위 명령이 통째로 사라져
    트리를 한 칸도 내려가지 못한다 — 실제로 이 실수로 주문 경로가 조회로
    분류됐다. 속성 이름은 Click 8.2에서 _protected_args로 바뀌었으므로 둘 다 본다.
    """
    # _protected_args를 먼저 본다: Click 8.4의 공개 protected_args는 접근만 해도
    # DeprecationWarning을 낸다. Click 9에서는 둘 다 없고 ctx.args가 전부 담으므로
    # 이 함수는 그대로 옳다.
    protected = getattr(ctx, "_protected_args", None)
    if protected is None:
        protected = getattr(ctx, "protected_args", [])
    return [*protected, *ctx.args]


def resolve_path(argv: list[str]) -> tuple[tuple[str, ...], list[str]]:
    """argv를 Click 트리로 걸어 (명령 경로, 남은 인자)를 돌려준다.

    resilient_parsing=True는 부작용 없이 옵션을 소비한다 — 필수 인자 누락으로
    죽지 않고, 프롬프트도 뜨지 않는다. 해석할 수 없는 경로는 거기서 멈춘다
    (그대로 실행하면 CLI 자신의 INVALID_INPUT으로 끝나므로 안전하다).
    """
    command: click.Command = cli
    path: list[str] = []
    args = list(argv)

    while isinstance(command, click.Group):
        ctx = click.Context(command, info_name=path[-1] if path else "kiwoom",
                            resilient_parsing=True)
        try:
            command.parse_args(ctx, list(args))
        except Exception:
            return tuple(path), args
        remaining = _remaining_args(ctx)
        if not remaining:
            return tuple(path), []
        name = remaining[0]
        try:
            sub = command.get_command(ctx, name)
        except Exception:
            sub = None
        if sub is None:
            # 알 수 없는 하위 명령 — 여기까지가 경로다
            return tuple(path), remaining
        path.append(sub.name or name)
        command = sub
        args = remaining[1:]

    return tuple(path), args


def _mutation_api_id(path: tuple[str, ...], rest: list[str]) -> str | None:
    """`kiwoom api <id>` 형태에서 주문성 api_id를 찾는다.

    문자열을 훑지 않고 남은 인자의 첫 위치 인자만 본다. `api list`는 통과.
    """
    if path != ("api",):
        return None
    for token in rest:
        if token.startswith("-"):
            continue
        return token if token in MUTATION_APIS else None
    return None


def classify_argv(argv: list[str]) -> Classification:
    path, rest = resolve_path(argv)

    for prefix in DENIED_PREFIXES:
        if _starts_with(path, prefix):
            return Classification(path, "denied", f"{'/'.join(prefix)}는 MCP로 실행하지 않습니다")

    if path in LOCAL_ADMIN_PATHS:
        return Classification(path, "local_admin", "로컬 설정·자격증명 변경은 MCP로 실행하지 않습니다")

    api_id = _mutation_api_id(path, rest)
    if api_id is not None:
        return Classification(path, "mutation", f"주문성 API ({api_id})")

    for prefix in MUTATION_PREFIXES:
        if _starts_with(path, prefix):
            if any(_starts_with(path, exc) for exc in MUTATION_EXCEPTIONS):
                break
            return Classification(path, "mutation", f"{' '.join(path)}는 주문을 전송할 수 있습니다")

    return Classification(path, "ok")
