"""릴리스 매니페스트가 서로 어긋나지 않는지 고정한다.

버전이 여러 파일에 흩어져 있고, 어긋나도 로컬에서는 아무 증상이 없다 —
태그를 밀고 CI가 돌아 **레지스트리 등록 단계에서** 처음 드러난다.

의도적으로 검사하지 **않는** 것: `.mcp.json`의 `kiwoom-mcp==X.Y.Z` pin.
그 pin은 __version__이 아니라 **이미 PyPI에 게시된** 버전을 가리켜야 한다.
버전을 올린 뒤 게시 전까지는 둘이 달라야 정상이다 (pin이 게시보다 먼저 main에
닿으면 플러그인이 연결에 실패한다 — CLAUDE.md 릴리스 절).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from kiwoom_mcp import __version__

REPO = Path(__file__).resolve().parents[2]
SERVER_JSON = REPO / "server.json"
SERVER_README = REPO / "server" / "README.md"

_MCP_NAME = re.compile(r"mcp-name:\s*(\S+)")


def _manifest() -> dict:
    return json.loads(SERVER_JSON.read_text(encoding="utf-8"))


def test_server_json_version_matches_the_package() -> None:
    """태그 시점에 server.json이 그 버전을 가리켜야 한다.

    어긋나면 레지스트리에 옛 버전을 등록하거나, 아직 PyPI에 없는 버전을
    가리켜 등록이 실패한다.
    """
    assert _manifest()["version"] == __version__


def test_declared_package_matches_what_we_publish() -> None:
    packages = _manifest()["packages"]
    assert len(packages) == 1
    assert packages[0]["identifier"] == "kiwoom-mcp"
    assert packages[0]["registryType"] == "pypi"
    assert packages[0]["version"] == __version__


def test_mcp_name_marker_matches_the_registry_name() -> None:
    """PyPI 소유권 검증의 연결고리.

    레지스트리는 PyPI 패키지 README에서 `mcp-name:` 줄을 읽어 server.json의
    name과 같은지 본다. 둘이 갈리면 등록이 거부되는데, 이 사실은 게시를
    시도해야만 알 수 있다.
    """
    match = _MCP_NAME.search(SERVER_README.read_text(encoding="utf-8"))
    assert match is not None, f"{SERVER_README}에 mcp-name 마커가 없다 — 레지스트리 등록이 거부된다"
    assert match.group(1) == _manifest()["name"]


def test_registry_name_is_owned_by_the_github_account() -> None:
    """GitHub 인증으로 등록하므로 이름은 io.github.<계정>/ 로 시작해야 한다."""
    assert _manifest()["name"].startswith("io.github.gejyn14/")


def test_description_fits_the_registry_limit() -> None:
    """레지스트리는 100자를 넘기면 422로 거부한다 (실제로 겪음)."""
    assert len(_manifest()["description"]) <= 100
