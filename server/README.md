<!-- mcp-name: io.github.gejyn14/kiwoom-mcp -->

# kiwoom-mcp (server)

이 디렉터리는 [kiwoom-plugin](https://github.com/gejyn14/kiwoom-plugin)의 MCP 서버 본체이며, PyPI에 [`kiwoom-mcp`](https://pypi.org/project/kiwoom-mcp/)로 게시됩니다. 플러그인은 이 패키지를 `uvx`로 실행합니다.

kiwoom-cli 236종 API를 MCP 도구로 노출합니다. 안전장치(주문 확인 게이트, dry-run, 멱등키, envelope)는 kiwoom-cli의 것을 그대로 통과시킵니다.

## 단독 실행

```bash
uvx kiwoom-mcp                  # 조회 전용
uvx kiwoom-mcp --allow-orders   # 조회 + 주문
```

저장소에서 직접 실행하려면 (게시 전 버전 등):

```bash
uvx --from "git+https://github.com/gejyn14/kiwoom-plugin@v0.1.1#subdirectory=server" kiwoom-mcp
```

전송·인증·안전 모델은 상위 [README](../README.md)를 참고하세요.

## 개발

```bash
pip install -e ".[dev]"
pytest tests/ -q
ruff check kiwoom_mcp/
```

## 도구

| 도구 | 설명 |
|---|---|
| `kiwoom_describe` | 명령 트리 조회 |
| `kiwoom_find` | 키워드로 명령·API 검색 |
| `kiwoom_run` | 임의의 kiwoom-cli 명령 실행 |
| `kiwoom_stream_snapshot` | 실시간 스트림에서 N개 이벤트 |
| `kiwoom_order_validate` | 주문 사전점검 (read-only) |
| `kiwoom_order` | 주문 전송 — `--allow-orders` 시에만 등록 |

## 라이선스

Apache-2.0.
