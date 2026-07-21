# kiwoom-plugin

키움증권 REST API를 Claude Code에 연결하는 것 전부를 담은 저장소. 플러그인 두 개 + MCP 서버 본체.

## 구조

```
kiwoom-plugin/
├── .claude-plugin/marketplace.json   마켓플레이스 (플러그인 2개 등록)
├── plugins/
│   ├── kiwoom/                        조회 전용 플러그인
│   │   ├── .claude-plugin/plugin.json
│   │   ├── .mcp.json                  서버를 uvx로 실행 (주문 없음)
│   │   └── skills/                    stock-research, portfolio-review, pnl-report,
│   │                                  market-scan, condition-search, kiwoom-setup
│   └── kiwoom-trader/                 조회 + 주문 플러그인
│       ├── .mcp.json                  서버를 --allow-orders로 실행
│       └── skills/                    위 6개 + place-order
├── server.json                       공식 MCP 레지스트리 매니페스트
└── server/                           MCP 서버 본체 (파이썬 패키지 kiwoom-mcp)
    ├── kiwoom_mcp/{cli,server,runner,policy}.py
    ├── tests/                         211개
    ├── pyproject.toml
    ├── Dockerfile / compose.yaml      헤드리스 컨테이너 (토큰 주입)
    └── README.md
```

## 세 저장소의 관계

- [kiwoom-cli](https://github.com/gejyn14/kiwoom-cli) — 키움 API 236종 CLI. **안전장치(주문 확인 게이트, dry-run, 멱등키, envelope)가 전부 여기 있다.** 서버는 이것을 감쌀 뿐 다시 구현하지 않는다.
- **kiwoom-plugin** (이 저장소) — 플러그인 + 스킬 + 서버.
- ~~kiwoom-mcp~~ — 서버를 담던 별도 저장소. 이 저장소로 흡수하고 삭제 중(로컬 삭제됨, GitHub는 수동 삭제 대기).

## 개발

```bash
cd server
pip install -e ".[dev]"
pytest tests/ -q          # 211개
ruff check kiwoom_mcp/ tests/
```

서버는 kiwoom-cli를 의존성으로 쓴다 (PyPI의 kiwoom-cli). 도구 표면이 kiwoom-cli의 명령 트리에서 나오므로, kiwoom-cli가 바뀌면 여기 테스트가 먼저 깨진다.

## 플러그인 배선 (중요)

두 플러그인의 `.mcp.json`은 서버를 PyPI에서 실행한다:

```
uvx --from "kiwoom-mcp==0.1.1" kiwoom-mcp [--allow-orders]
```

- **정확한 버전에 고정한다** (`==0.1.1`), 범위나 bare가 아니라. 진짜 제약은 "git 태그여야 한다"가 아니라 **uvx 캐시 경로가 안정적이어야 한다**는 것이다 — bare `kiwoom-mcp`는 새 릴리스가 나올 때마다 경로가 바뀌고, macOS는 키체인 접근을 바이너리 단위로 승인하므로 그때마다 승인 창이 다시 뜬다.
- **`.mcp.json`이 고정하는 버전은 반드시 PyPI에 게시된 버전이어야 한다.** 서버를 올렸으면: 버전 범프 → 빌드 → PyPI 게시 → 두 `.mcp.json`의 `==X.Y.Z`를 갱신. 게시 전에 pin을 올리면 플러그인이 연결에 실패한다.
- 게시 전 검증이나 저장소 직접 실행은 git 형태를 쓴다:
  `uvx --from "git+https://github.com/gejyn14/kiwoom-plugin@vX.Y.Z#subdirectory=server" kiwoom-mcp` (`#subdirectory=server`로 하위 디렉터리만 설치, uv가 지원함).

## 설계 불변식 — 되돌리지 말 것

- **서버는 kiwoom-cli를 `CliRunner.invoke(cli, argv)`로 같은 프로세스에서 실행한다.** 파사드를 만들지 않는다 — 확인 게이트·멱등성 원장·페이지네이션·exit code·envelope이 전부 활성 Click 컨텍스트에 매달려 있고, 별도 해석 경로를 만들면 kiwoom-cli에서 세 번 재발한 프로필 해석 버그를 되풀이한다. (`server/kiwoom_mcp/runner.py`)
- **argv 분류는 Click 파서로 한다, 문자열 훑기가 아니라.** (`policy.py`) 손으로 토큰을 훑으면 `--opt=value`나 끼어든 인자에서 분류와 실제 실행이 갈려, "조회"로 분류된 argv가 주문을 보낸다. Click 8.4가 하위 명령을 `protected_args`로 옮기는 것을 놓쳐 실제로 이 버그가 났다 (`test_policy.py`가 고정).
- **스킬의 argv는 문서가 아니라 실행 대상이다.** `SKILL.md`의 모든 `kiwoom_run([...])`은 `test_skills.py`가 Click 트리로 걸어 **리프에 도달하는지** 검사한다. kiwoom-cli의 그룹을 리프처럼 부르면 런타임에 `INVALID_INPUT`이 나는데, 이건 문서를 읽어서는 보이지 않고 사용자가 겪어야만 드러난다 — 실제로 출하된 스킬 6개에 이런 argv가 12곳 있었다(`place-order`의 주문 확인 경로 포함). 스킬은 두 플러그인에 복사본으로 존재하므로 같은 테스트가 바이트 동일성도 고정한다. **한쪽만 고치지 말 것.**
- **`order condition`(조건검색)은 주문이 아니다.** kiwoom-cli가 `order` 아래 두었을 뿐 ka10171~ka10174는 조회·구독이다. `policy.py`의 `MUTATION_EXCEPTIONS`에서 빼면 조회 전용 플러그인에서 조건검색이 통째로 막힌다.
- **`kiwoom_order`는 `--allow-orders`일 때만 등록된다.** 설정으로 끄는 게 아니라 도구 목록에 아예 없어야 한다. 안전 여부는 대화 중이 아니라 설치 시점(어느 플러그인을 깔지)에 정한다.
- **기동 경로는 절대 키체인을 읽지 않는다.** macOS 키체인 승인은 바이너리 단위라, 헤드리스 서버가 기동 중 키체인을 읽으면 답할 수 없는 GUI 창이 떠 무한정 멈춘다 — 타임아웃처럼 보이지만 아니다. 토큰은 첫 호출에서 필요할 때 확보한다. `credentials_available()`은 env만 본다.

## 테스트 규칙 (kiwoom-cli와 동일)

- 값 고정은 **리터럴 하드코딩**. 상수에서 기대값을 가져오면 상수를 바꿔도 통과한다.
- 서로 다른 분류로 갈리는 케이스를 고른다. 전부 같은 분류면 분류기가 상수를 돌려줘도 통과한다 (`test_policy.py::test_cases_actually_diverge`가 이걸 지킨다).
- 차단이 전송을 막는지 확인하는 스파이는 **먼저 스파이가 발동하는 것을 증명**한다 (`test_runner.py::test_spy_fires_on_an_allowed_path`). 그 증명이 없으면 배선이 끊겨도 통과한다.
- 새 테스트는 변경 전 코드에 대고 돌려 실패하는지 확인한다 (worktree 등).

## 릴리스

- 서버 버전은 `server/kiwoom_mcp/__init__.py`가 유일 소스. pyproject는 dynamic 참조.
- **플러그인의 `.mcp.json`은 git 태그를 고정하지 패키지 버전이 아니다.** 서버를 바꿨으면: 버전 범프 → 새 태그 push → 두 `.mcp.json`의 `@vX.Y.Z`를 새 태그로 갱신.
- PyPI 게시: `server/`의 kiwoom-mcp 패키지를 Trusted Publishing으로 올린다 (`.github/workflows/publish.yml`, OIDC, 장기 토큰 없음). **최초 1회는 프로젝트가 없어 pending publisher/토큰 문제가 있으므로 수동 `twine upload`로 프로젝트를 만든 뒤** 이후 릴리스를 워크플로에 맡긴다.
- 플러그인 자체는 PyPI가 아니라 마켓플레이스(git)로 배포된다.

## 검증 (엔드투엔드)

```bash
# GitHub에서 마켓플레이스 새로 받아 설치
claude plugin marketplace add gejyn14/kiwoom-plugin
claude plugin install kiwoom@kiwoom
claude mcp list | grep plugin:kiwoom      # ✔ Connected 여야 한다
# 매니페스트 검증
claude plugin validate .
```

## 주의

- README·스킬은 한국어 우선.
- 실거래(`prod`)와 모의(`mock`)를 절대 혼동하지 않는다. 모든 envelope의 `meta.env`로 확인 가능. 스킬은 주문 전 이걸 확인하도록 쓰여 있다.
- 서버는 조회 전용이 기본. 주문 도구는 `--allow-orders`에서만.
