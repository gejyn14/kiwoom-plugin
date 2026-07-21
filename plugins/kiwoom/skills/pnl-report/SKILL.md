---
name: pnl-report
description: 실현손익과 계좌 수익률을 기간별로 정리한다. "이번 달 얼마 벌었어", "올해 수익률", "실현손익 보여줘", "어떤 종목에서 벌고 잃었어", "매매일지" 같은 요청에 사용한다. 잔고·미체결 점검은 portfolio-review를 쓴다.
---

# 손익·수익률

## 먼저 구분한다

- **실현손익** — 실제로 팔아서 확정된 것. `account pnl *`
- **평가손익** — 아직 들고 있는 것의 장부상 증감. `account balance` (portfolio-review)
- **수익률** — 투입 대비 비율. `account returns *`

사용자의 "얼마 벌었어"는 대개 **실현손익**이지만 둘을 합쳐 생각하는 경우가 많다.
어느 쪽을 말하는지 애매하면 **둘 다 보여 주고 각각 무엇인지 밝힌다.**

## 기간

`account pnl`과 대부분의 `account returns`는 `--from`/`--to`가 **필수**다.
사용자가 기간을 말하지 않았으면 정하고 **답에 그 기간을 밝힌다** — "이번 달"을
멋대로 "올해"로 넓히지 않는다. 날짜는 `YYYYMMDD`.

## 무엇을 부를까

### 기간 실현손익

```
kiwoom_run(["account","pnl","daily","--from","<YYYYMMDD>","--to","<YYYYMMDD>"])
```

일자별 실현손익. "이번 달 얼마 벌었어"의 기본 답이다.

### 종목별로 쪼개기

```
kiwoom_run(["account","pnl","by-period","--from","<YYYYMMDD>","--to","<YYYYMMDD>"])
```

"어떤 종목에서 벌고 잃었는지"에 쓴다. `--code`로 한 종목만, `--market us`로 미국,
`--krw`로 미국 손익을 원화 환산. 일자 기준은 `account pnl by-date --from …`.

### 당일 한 종목

```
kiwoom_run(["account","pnl","today","<코드>"])
```

**국내는 종목코드가 필수다.** 미국은 `--market us`로 코드 없이 전체를 받는다.

### 계좌 수익률

```
kiwoom_run(["account","returns","summary"])
```

인자가 필요 없다. 기간별로는
`account returns daily-detail --from … --to …`(일별 계좌수익률 상세),
`account returns daily-balance --date …`(일별 잔고수익률),
`account returns daily-asset --from … --to …`(일별 추정예탁자산).

### 매매일지

```
kiwoom_run(["account","history","journal"])
```

당일 무엇을 사고팔았는지. 기간 거래내역은 `account history transactions`.

## 답할 때

- **합계를 먼저, 내역은 그다음.** 표를 통째로 붙이지 말고 기간 합계를 말한 뒤
  기여가 큰 종목 몇 개를 짚는다.
- **이긴 것과 진 것을 같이 보여 준다.** 수익 종목만 나열하면 그림이 왜곡된다.
- 상승 빨강 / 하락 파랑 (한국 관습).
- **수수료·세금이 반영된 값인지 단정하지 않는다.** 키움이 돌려준 필드를 그대로
  전하고, 사용자가 증권사 앱과 다르다고 하면 계산 기준 차이일 수 있다고 말한다.
- **`meta.env`가 `"mock"`이면 모의투자 계좌다.** 실제 수익으로 오해하지 않도록 명시한다.
- 기간에 거래가 없으면 빈 결과가 정상이다. "손익 0"이 아니라 "그 기간에 매도가
  없었다"고 말한다.

## 하지 않을 것

성과를 평가하거나 다음에 무엇을 사라고 하지 않는다. 숫자와 그 구성까지가 범위다.
