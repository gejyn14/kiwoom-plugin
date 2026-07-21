---
name: market-scan
description: 시장 전반을 훑는다. 거래량·등락률·거래대금 순위, 업종, 테마, ETF, 프로그램매매, 실시간 시세. "오늘 시장 어때", "거래량 상위", "많이 오른 종목", "무슨 테마가 강해?", "코스닥 상황" 같은 요청에 사용한다.
---

# 시장 훑기

## 순위 (28종)

종류는 **하위 명령**이다 (`--market`은 `all`/`kospi`/`kosdaq`):

```
kiwoom_run(["market","rank","volume","--market","kospi"])
```

자주 쓰는 것: `volume`(당일 거래량), `change`(전일대비 등락률), `amount`(거래대금),
`volume-surge`(거래량 급증), `foreign-inst`(외국인/기관 매매 상위),
`new-highlow`(신고저가), `limit`(상하한가).

전체 목록은 `kiwoom_describe(["market","rank"])`로 확인한다 — 28종이라 외우지 말고
필요할 때 조회한다. **시가총액 순위는 없다** — 없는 종류를 지어내지 말고 목록에서 고른다.

## 그 밖

`market sector`·`theme`·`etf`·`program`은 전부 **그룹**이다. 그대로 호출하면
`INVALID_INPUT`이 나므로 하위 명령까지 내려간다.

- 업종 지수: `kiwoom_run(["market","sector","index"])` — 기본 `--sector-code 001`(KOSPI종합),
  KOSDAQ종합은 `101`. 업종별 등락은 `market sector investor`, 개별 업종은 `market sector current <업종코드>`.
- 테마: `kiwoom_run(["market","theme","groups"])` — "무슨 테마가 강한지" 물을 때.
  구성종목은 `market theme stocks <테마코드>`.
- ETF: `kiwoom_run(["market","etf","all"])` — 개별 ETF는 `market etf info <코드>`.
- 프로그램매매: `kiwoom_run(["market","program","time-trend","--date","<YYYYMMDD>"])`
  — `--date`가 **필수**다. 일자별은 `market program daily-trend`.

## 실시간

지금 이 순간의 호가·체결을 보려면 `kiwoom_stream_snapshot`을 쓴다:

```
kiwoom_stream_snapshot(stream_type="quote", symbols=["005930"], max_events=10, duration="15s")
```

반드시 유한하게 끝난다 — `max_events`나 `duration` 중 먼저 닿는 쪽에서 종료한다.
장 시간이 아니면 이벤트가 오지 않고 시간만 흐르므로, 장외 시간에는
`stock info`로 종가를 보는 편이 낫다.

## 답할 때

- 순위표를 통째로 붙이지 않는다. 상위 몇 개를 추리고 **무엇이 눈에 띄는지**
  말한다 — 한 업종이 상위를 채우고 있다든가, 거래량이 평소와 다르다든가.
- 상승 빨강 / 하락 파랑 (한국 관습).
- 장 시간을 의식한다. 국내장은 09:00–15:30 (KST). 장 마감 후의 "오늘 시장"은
  종가 기준이라는 점을 밝힌다.
- `meta.env`가 `"mock"`이면 모의투자 서버 데이터이며 실제 시장과 다를 수 있다.
