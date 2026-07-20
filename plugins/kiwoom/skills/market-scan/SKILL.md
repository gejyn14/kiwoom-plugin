---
name: market-scan
description: 시장 전반을 훑는다. 거래량·등락률·시가총액 순위, 업종, 테마, ETF, 프로그램매매, 실시간 시세. "오늘 시장 어때", "거래량 상위", "많이 오른 종목", "무슨 테마가 강해?", "코스닥 상황" 같은 요청에 사용한다.
---

# 시장 훑기

## 순위 (28종)

`kiwoom_run(["market","rank","<종류>","--market","kospi|kosdaq|all"])`

자주 쓰는 것: `volume`(거래량), `change`(등락률), `amount`(거래대금),
`market-cap`(시가총액), `foreigner`(외국인 순매수).

전체 목록은 `kiwoom_describe(["market","rank"])`로 확인한다 — 28종이라 외우지 말고
필요할 때 조회한다.

## 그 밖

- 업종: `kiwoom_run(["market","sector"])`
- 테마: `kiwoom_run(["market","theme"])` — "무슨 테마가 강한지" 물을 때
- ETF: `kiwoom_run(["market","etf"])`
- 프로그램매매: `kiwoom_run(["market","program"])`

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
