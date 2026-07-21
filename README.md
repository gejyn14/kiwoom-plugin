# kiwoom-plugin

키움증권 REST API 236종(217 REST + 19 WebSocket)을 Claude Code에 연결하는 플러그인 모음입니다.

시세·차트·계좌·순위·실시간 스트리밍을 대화로 조회하고, 원한다면 주문까지 넣을 수 있습니다.

## 설치

```
/plugin marketplace add gejyn14/kiwoom-plugin
```

그다음 둘 중 **하나만** 고릅니다.

```
/plugin install kiwoom@kiwoom            # 조회 전용 (권장)
/plugin install kiwoom-trader@kiwoom     # 조회 + 주문
```

> 두 플러그인은 서로 대체하는 관계입니다. 같이 설치하면 같은 도구가 두 번
> 등록됩니다. 주문이 필요해지면 `kiwoom`을 제거하고 `kiwoom-trader`를 설치하세요.

MCP 서버는 [`uvx`](https://docs.astral.sh/uv/)로 자동 실행되므로 별도 설치가 없습니다. `uv`만 있으면 됩니다.

## 왜 두 개인가

`kiwoom`에는 주문 도구가 **아예 등록되지 않습니다.** 설정으로 끄는 것이 아니라 도구 목록에 존재하지 않으므로, 모델이 실수로도 주문을 낼 수 없습니다.

안전 여부를 대화 중이 아니라 **설치 시점에** 정하는 편이 낫다고 보았습니다.

## 인증

kiwoom-cli와 같은 자격증명을 씁니다. 이미 설정했다면 추가 작업이 없습니다.

```bash
uv tool install kiwoom-cli
kiwoom config setup      # appkey/secretkey를 OS 키체인에 저장
kiwoom auth login        # 토큰 발급
```

기본값은 **모의투자(mock)** 입니다. 실거래로 바꾸려면 `kiwoom config set domain prod`.

### 키체인이 없는 환경 (컨테이너·CI)

OS 키체인을 읽을 수 없는 곳에서는 호스트에서 발급한 토큰을 주입합니다.

```bash
kiwoom auth login                          # 키체인 있는 호스트에서 발급
export KIWOOM_TOKEN='...'                   # 발급된 토큰
export KIWOOM_DOMAIN=mock                   # prod = 실계좌
```

`KIWOOM_TOKEN`은 키체인 토큰보다 우선하며, 만료되면 다시 발급해 넣어야 합니다.

## 할 수 있는 것

```
삼성전자 지금 얼마야?
내 계좌 상태 정리해줘
오늘 거래량 상위 종목 보여줘
005930 최근 한 달 추세랑 외국인 수급 같이 봐줘
미체결 주문 있어?
내 조건식 돌려서 걸린 종목 알려줘
이번 달 실현손익 정리해줘
```

`kiwoom-trader`를 설치했다면:

```
삼성전자 10주 71000원에 매수 주문 넣어줘
```

주문은 항상 **사전점검 → 미리보기 → 확인** 순서로 진행되며, 전송 전에 반드시 내용을 보여주고 승인을 받습니다.

## 포함된 스킬

| 스킬 | 언제 |
|---|---|
| `stock-research` | 종목 조사 — 시세, 차트, 수급을 하나로 |
| `portfolio-review` | 계좌·보유종목·평가손익·미체결 점검 |
| `pnl-report` | 실현손익·수익률을 기간별로 정리 |
| `market-scan` | 순위, 업종, 테마, 실시간 시세 |
| `condition-search` | HTS에 저장한 조건식으로 종목 걸러내기 |
| `kiwoom-setup` | 인증·설정 진단 (연결이 안 될 때) |
| `place-order` | 주문 절차 — `kiwoom-trader` 전용 |

## 안전 모델

- 조회 전용 플러그인에는 주문 도구가 등록되지 않습니다.
- `config set`, `auth login/logout` 같은 로컬 설정 변경은 **어느 플러그인에서도** 차단됩니다. 모델이 도메인을 실거래로 바꾸거나 토큰을 폐기할 수 없습니다.
- 주문은 `dry_run`이 기본값입니다. 전송하려면 명시적으로 꺼야 합니다.
- 멱등키(`client_order_id`)로 재시도해도 중복 주문이 나가지 않습니다.
- 모든 응답에 `meta.env`가 실려 있어 모의(`mock`)인지 실거래(`prod`)인지 항상 확인할 수 있습니다.

## 구성

이 저장소가 MCP 관련 전부를 담습니다 — 플러그인, 스킬, 그리고 MCP 서버 본체.

```
kiwoom-plugin/
├── plugins/kiwoom/           조회 전용 플러그인 + 스킬
├── plugins/kiwoom-trader/    조회 + 주문 플러그인 + 스킬
└── server/                   MCP 서버 (uvx로 직접 실행)
```

서버는 PyPI에 [`kiwoom-mcp`](https://pypi.org/project/kiwoom-mcp/)로 게시되며, 플러그인이 `uvx`로 실행합니다. 안전장치(주문 확인, dry-run, 멱등키, envelope)는 [kiwoom-cli](https://github.com/gejyn14/kiwoom-cli)의 것을 그대로 씁니다 — 서버는 kiwoom-cli를 감쌀 뿐 다시 구현하지 않습니다.

MCP 서버만 필요하면 플러그인 없이 직접 실행할 수 있습니다 (Claude Desktop, 다른 MCP 클라이언트 등):

```bash
uvx kiwoom-mcp                  # 조회 전용
uvx kiwoom-mcp --allow-orders   # 조회 + 주문
```

## 면책

투자 판단과 그 결과는 사용자 본인의 책임입니다. 이 도구는 조회와 주문 실행을 도울 뿐 투자 조언을 하지 않습니다. **실거래 전에 반드시 모의투자로 충분히 검증하세요.**

## 라이선스

Apache-2.0. kiwoom-cli는 별도의 소스 공개 라이선스를 따릅니다.
