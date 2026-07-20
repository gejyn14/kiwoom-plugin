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
| `TOKEN_EXPIRED` | 토큰 만료 (upstream 8005 / HTTP 401) | 재발급 |
| `NOT_CONFIGURED` | appkey 없음 또는 config.toml 손상 | `kiwoom config setup` (터미널에서) |
| `KEYCHAIN_UNAVAILABLE` | OS 키체인 접근 불가 | 아래 "키체인 없는 환경" |

## 토큰 발급

**MCP 도구로는 `auth login`을 실행할 수 없다** — 서버가 차단한다
(`MCP_ADMIN_BLOCKED`). 자격증명 수명주기는 서버가 소유하며, 모델이 토큰을
발급·폐기하게 두지 않는다. 사용자에게 터미널에서 직접 실행하도록 안내한다:

```bash
kiwoom auth login
```

appkey/secretkey가 환경변수(`KIWOOM_APPKEY` 등)로 주어져 있으면 MCP 서버는
기동 시 토큰을 발급하고 만료되면 스스로 재발급한다. 이 경우 사용자가 할 일은 없다.

## 키체인 없는 환경 (컨테이너, CI, 샌드박스)

kiwoom-cli 2.15.0+ 에서:

```bash
export KIWOOM_APPKEY_FILE=/run/secrets/kiwoom_appkey   # 또는 KIWOOM_APPKEY
export KIWOOM_SECRETKEY_FILE=/run/secrets/kiwoom_secretkey
export KIWOOM_TOKEN_STORAGE=env    # 없으면 발급에 성공하고도 저장에서 실패한다
export KIWOOM_DOMAIN=mock
```

`KIWOOM_TOKEN_STORAGE=env`를 빠뜨리는 것이 흔한 실수다 — 토큰은 발급되는데
키체인에 쓰려다 `KEYCHAIN_UNAVAILABLE`로 끝난다.

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
