---
name: kiwoom-setup
description: 키움 MCP 인증·설정을 진단하고 고친다. 도구가 AUTH_REQUIRED / TOKEN_EXPIRED / NOT_CONFIGURED / KEYCHAIN_UNAVAILABLE로 실패하거나, "연결이 안 돼", "토큰 만료", "설정 어떻게 해", "모의랑 실거래 바꾸고 싶어" 같은 요청에 사용한다.
---

# 설정 진단

## 먼저 상태를 본다

```
kiwoom_run(["auth","status"])
```

돌아오는 것: `profile`, `domain`(실제 접속 도메인), `configured`,
`appkey_source`, `has_token`, `token_source`, `token_storage`.

**`domain`은 설정 파일 값이 아니라 실제로 접속하는 도메인이다.** `KIWOOM_DOMAIN`
환경변수가 모든 프로필을 덮으므로, 설정에 `mock`이라 적혀 있어도 실거래로 갈 수 있다.

## 오류별 대응

| error.code | 뜻 | 대응 |
|---|---|---|
| `AUTH_REQUIRED` | 토큰 없음 | 아래 "토큰 발급" |
| `TOKEN_EXPIRED` | 토큰 만료 (upstream 8005) | 재발급 |
| `INVALID_CREDENTIALS` | appkey/secretkey를 키움이 거부 (upstream 8001) | 키가 폐기·만료된 것이다. 개발자센터에서 새로 발급받아 `kiwoom config setup` |
| `NOT_CONFIGURED` | appkey 없음 또는 config.toml 손상 | `kiwoom config setup` (터미널에서) |
| `KEYCHAIN_UNAVAILABLE` | OS 키체인 접근 불가 | 아래 "키체인 없는 환경" |

**만료 토큰이 `TOKEN_EXPIRED`로 안 올 수 있다.** 일반 조회에서 토큰이 만료되면
실제 응답은 `code: "UPSTREAM_ERROR"`, `upstream_code: 3`이고 구체적인 번호는
메시지 안에만 들어 있다 — `인증에 실패했습니다[8005:Token이 유효하지 않습니다]`.
`error.code`만 보고 "서버 오류"라고 답하지 말고 **메시지의 대괄호 번호를 읽는다.**

## 토큰 발급

**MCP 도구로는 `auth login`을 실행할 수 없다** — 서버가 차단한다
(`MCP_ADMIN_BLOCKED`). 자격증명 수명주기는 서버가 소유하며, 모델이 토큰을
발급·폐기하게 두지 않는다. 사용자에게 터미널에서 직접 실행하도록 안내한다:

```bash
kiwoom auth login
```

appkey/secretkey가 환경변수로 주어져 있으면 MCP 서버가 **첫 호출에서** 토큰을
발급하고 만료되면 스스로 재발급한다 (기동 중에는 발급하지 않는다 — 키체인 승인
창이 뜨면 헤드리스 서버가 답할 수 없어 멈춘다). 이 경우 사용자가 할 일은 없다.

## 키체인 없는 환경 (컨테이너, CI, 샌드박스)

**어느 쪽이 무엇을 읽는지 구분해야 한다.**

kiwoom-cli 2.14.0이 읽는 환경변수는 넷뿐이다:
`KIWOOM_ACCOUNT`, `KIWOOM_DOMAIN`, `KIWOOM_PROFILE`, `KIWOOM_TOKEN`.
**appkey/secretkey는 kiwoom-cli가 읽지 않는다** — 그래서 셸에 `KIWOOM_APPKEY`를
export해 두어도 `kiwoom auth login`은 "appkey/secretkey not set"으로 실패한다.

appkey/secretkey 환경변수를 쓰는 것은 **MCP 서버**다. 서버가 이 값으로 직접
토큰을 발급해 `KIWOOM_TOKEN`에 심고, 그다음부터는 kiwoom-cli가 그 토큰을 쓴다.

```bash
# MCP 서버가 읽는다 (서버가 토큰을 발급해 준다)
export KIWOOM_APPKEY_FILE=/run/secrets/kiwoom_appkey       # 또는 KIWOOM_APPKEY
export KIWOOM_SECRETKEY_FILE=/run/secrets/kiwoom_secretkey # 또는 KIWOOM_SECRETKEY

# kiwoom-cli가 읽는다
export KIWOOM_DOMAIN=mock
```

서버 없이 kiwoom-cli만 쓰거나 자격증명을 컨테이너에 넣고 싶지 않다면, 키체인이
있는 호스트에서 발급한 토큰을 직접 주입한다 — 이쪽은 kiwoom-cli가 바로 이해한다:

```bash
export KIWOOM_TOKEN='...'   # 우선순위가 가장 높다. 만료되면 다시 넣어야 한다
```

**발급이 실패하면 서버가 stderr에 이유를 찍는다** (`kiwoom-mcp: 토큰 발급 실패: …`).
조회가 계속 인증 오류로 끝나는데 이유를 모르겠으면 서버 로그를 먼저 본다.

## 모의 ↔ 실거래

`config set`도 MCP로는 차단된다. 사용자에게 안내한다:

```bash
kiwoom config set domain mock    # 또는 prod
```

또는 `KIWOOM_DOMAIN` 환경변수로 덮는다 (모든 프로필에 적용).

**실거래로 바꾸라고 먼저 제안하지 않는다.** 사용자가 명시적으로 요청할 때만
방법을 알려주고, 그 전에 `prod`가 실제 계좌·실제 돈이라는 점을 확인한다.

## 환경변수가 키체인을 덮는다

`appkey_source`가 `"env"`나 `"env_file"`인데 사용자가 `config setup`으로 저장한
값을 기대한다면, 셸에 `KIWOOM_APPKEY`가 export되어 있다는 뜻이다. 우선순위는
env > 키체인이며 의도된 동작이지만 눈에 띄지 않으므로 짚어 준다.
