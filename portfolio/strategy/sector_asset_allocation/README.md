# Sector-based Asset Allocation Research

**한국과 미국에 어떻게 비중 배분을 해야 할까?** — 섹터와 환율 데이터로 답을 찾아가는 여정

**백테스트 기간**: 2011-04-01 ~ 현재 (179 개월)
**운영 구조** (이중 시그널):
- **MAIN** (6M-only): CAGR **+18.40%** / Sharpe **0.97** / MDD **−24.8%** · Walk-forward OOS Sharpe 1.09
- **ALERT** (Champion [1,3,6]): CAGR +16.53% / Sharpe 0.86 · 단기 조정 감지용

**후속 검증 (§4.9 ~ §4.12)**:
- FX 시나리오: KRW 환오픈 우선 권장
- Walk-forward OOS: 과적합 없음
- Parameter Sensitivity: 88% 견고
- Rolling OOS: 6M-only 우위 확인

**현재 단계**: Paper Trading (3-6개월 실시간 병행 관찰)

---

## 1. 질문

> **"매달 KOSPI(한국)와 S&P500(미국) 중 어디에 투자해야 더 나은 성과를 얻을까?"**

일상에서 투자자가 마주치는 실제 질문입니다. 답변 방식:

- **감에 의존**: 뉴스·애널리스트 의견 → 일관성 없음, 감정 개입
- **고정 비율 (50/50)**: 단순하지만 시장 상황 무시
- **데이터 기반 규칙**: 이 프로젝트의 접근

목표: **매달 객관적인 데이터 시그널로 국가 비중 결정**

---

## 2. 데이터

### 왜 대표 지수만 보면 부족한가?

KOSPI vs S&P500 직접 비교는 **1차원 신호** 하나:
```
지난 3M KOSPI 수익률 vs 지난 3M S&P500 수익률
```

이 방식의 한계:
- 시장 전체 평균만 보므로 **구조적 차이 반영 못 함**
- 예: "KR IT 가 강하지만 KR 금융은 약함" 같은 세부 정보 손실
- 환율 movement 무시

### 세분화된 접근

**A. 미국 GICS 섹터 지수** — SPDR Select Sector ETFs
- 1998년 이후 지속, OHLCV 완전
- 11개 섹터 (TECH, FIN, HEALTH, INDU, ENERGY, DISCR, STAPLES, MATL, UTIL, COMM, REIT)

**B. 한국 GICS 섹터 지수** — KRX 공식 KOSPI 200 섹터 지수
- **2011-04-01 공식 발표** (5개 섹터: IT/FIN/ENERGY/DISCR/STAPLES + 건설/중공업/철강 = 8개)
- 2015-07-13 추가 (산업재, 헬스케어)
- 2018-10-22 추가 (커뮤니케이션서비스, GICS 2018 개편 반영)

**중요**: pre-publication 구간은 KRX 가 현재 구성종목으로 back-calculate 한 값 → 실시간 시그널 아님. **이 프로젝트는 2011-04-01 이후 5쌍만 사용해 이 편향 제거**.

**C. 환율 데이터**
- USDKRW: 직접 KR↔US 환율 (Korean won vs US dollar)
- DXY: 광의 달러 지수 (USD vs 6개 통화 가중)

### 데이터 페어 (최종 사용)

| 페어 | KR (KOSPI 200) | US (SPDR) | KRX 발표일 |
|---|---|---|---|
| IT | 정보기술 | TECH (XLK) | 2011-04-01 |
| FIN | 금융 | FIN (XLF) | 2011-04-01 |
| ENERGY | 에너지/화학 | ENERGY (XLE) | 2011-04-01 |
| DISCR | 경기소비재 | DISCR (XLY) | 2011-04-01 |
| STAPLES | 생활소비재 | STAPLES (XLP) | 2011-04-01 |

→ **2011-04-01 부터 5쌍 모두 실시간 가용**

---

## 3. 방법론

### 설계 철학

> "**복잡성은 정당화되어야 한다**". 단순한 규칙부터 시작해 점진 개선.

### Phase 1: 벤치마크 수립

**이길 대상**:
1. **50/50 Blend** — 매달 50:50 리밸런싱 (passive diversification)
2. **KOSPI only** — 한국 단독
3. **S&P500 only** — 미국 단독

새 전략은 **Sharpe 기준으로 이 셋보다 우수**해야 함.

### Phase 2: 섹터 구성 선택 (3 가지)

5쌍 풀(IT/FIN/ENERGY/DISCR/STAPLES) 에서 **어떻게 신호 추출할 것인가?**

#### A. 전체 5쌍 사용 (maximum information)
- 5쌍 평균 RS 를 신호로
- **가정**: "정보 많을수록 좋다"
- **리스크**: 상관 높은 섹터가 중복 계산, 노이즈 추가

#### B. 상관관계 최소화 4쌍 (통계적 선택)
- C(5,4) = 5 조합 중 내부 상관 평균이 최저인 조합 자동 선택
- **로직**: 서로 독립적인 4개가 5개 혼합보다 깔끔할 수 있음

#### C. 경제축 4쌍 (도메인 지식)
- **IT**: 성장 / Duration (금리 민감 장기 자산)
- **FIN**: 가치 / Curve (예대마진, 크레딧)
- **ENERGY**: 인플레 / Commodity (원자재 가격)
- **STAPLES**: 방어 / 저베타 (경기 방어)
- DISCR 는 IT 와 상관 높으므로 제외
- **로직**: 4개의 직교 경제 레짐을 커버

### Phase 3: 환율 오버레이

섹터 신호에 FX 를 얹으면 도움될까?

**가설**: KR vs US 투자 의사결정에서 **환율은 1차 채널**.
- USDKRW 상승 = KRW 약세 = KR 수출주 이익 증가 → KR 매수 편향
- USDKRW 하락 = KRW 강세 = KR 수출주 타격 → US 매수 편향

**실험**:
- FX 소스: {USDKRW, DXY}
- FX 가중: {0%, 20%, 30%, 50%}
- 기본 섹터 신호 + FX 신호 가중 평균

### Phase 4: 최종 조합 Sweep

- 섹터 구성 3개 × FX 가중 4개 × FX 소스 2개 = **24 조합**
- Sharpe 최고 조합을 챔피언으로 확정

### 백테스트 규칙 (모든 Phase 공통)

- 기간: **2011-04-01 ~ 현재 (179개월)**
- 리밸런싱: **월말 (Business Month End)**
- 거래비용: **30 bps one-way** (전환 시 적용)
- 포지션: {KOSPI 100%, S&P500 100%, 50/50 Neutral} 중 하나
- 임계값: ±0.02 (log-return diff scale)
- Hysteresis: 임계값 내일 때 이전 상태 유지 (churn 억제)

---

## 4. 실험 결과

### Phase 1: 벤치마크

| 전략 | CAGR | Sharpe | MDD | Win% |
|---|---:|---:|---:|---:|
| 50/50 Blend | +10.13% | 0.65 | −27.4% | 61% |
| KOSPI | +7.77% | 0.39 | −35.9% | 55% |
| **S&P500** | **+11.90%** | **0.83** | **−24.8%** | 66% |

→ **넘어야 할 기준선: S&P500 의 Sharpe 0.83 / MDD −24.8%**

[outputs/phase1_benchmarks.html](outputs/phase1_benchmarks.html)

### Phase 2: 섹터 구성 실험

**상관 매트릭스** (5쌍 RS 3M 내부 상관):

| | IT | FIN | ENERGY | DISCR | STAPLES |
|---|---:|---:|---:|---:|---:|
| IT | — | +0.47 | +0.13 | **+0.76** | +0.34 |
| FIN | +0.47 | — | +0.14 | +0.53 | +0.51 |
| ENERGY | +0.13 | +0.14 | — | +0.09 | +0.23 |
| DISCR | **+0.76** | +0.53 | +0.09 | — | +0.34 |
| STAPLES | +0.34 | +0.51 | +0.23 | +0.34 | — |

관찰:
- **IT–DISCR +0.76** ⚠ — 거의 같은 신호 (성장주 덩어리)
- **IT–ENERGY +0.13**, **FIN–ENERGY +0.14** → 진짜 직교
- DISCR 이 "여분 섹터" 역할

**성과 비교**:

| 구성 | CAGR | Sharpe | MDD | Win% |
|---|---:|---:|---:|---:|
| A. 전체 5쌍 | +13.34% | 0.69 | −32.0% | 58% |
| **B. 상관최소 4쌍** | **+15.21%** | **0.80** | **−24.8%** | 62% |
| **C. 경제축 4쌍** | **+15.21%** | **0.80** | **−24.8%** | 62% |

**🎯 핵심 발견 #1**: B 와 C 가 **완전히 같은 4쌍**을 선택
- **통계적 선택(B)**: 상관 최소 = **IT+FIN+ENERGY+STAPLES**
- **경제적 선택(C)**: 경제축 = **IT+FIN+ENERGY+STAPLES**
- → **데이터가 도메인 지식을 확인**. DISCR 제거의 정당성 확보.

**🎯 핵심 발견 #2**: 4쌍 축소가 5쌍보다 strictly better
- CAGR +1.87%p (13.34 → 15.21)
- Sharpe +0.11 (0.69 → 0.80)
- **MDD +7.2pp 개선** (−32.0% → −24.8%)
- → "정보가 많을수록 좋다" 가설 **틀림**. 상관 높은 섹터 제거가 핵심.

[outputs/phase2_sector_selection.html](outputs/phase2_sector_selection.html)

### Phase 3: FX Overlay

Phase 2 베이스 구성 (B = C = 4쌍) + FX 가중 sweep:

| Config | CAGR | Sharpe | MDD |
|---|---:|---:|---:|
| FX 0% (베이스) | +15.21% | 0.80 | −24.8% |
| USDKRW 20% | +16.10% | 0.84 | −24.8% |
| DXY 20% | +16.10% | 0.84 | −24.8% |
| **USDKRW 30%** 🏆 | **+16.49%** | **0.87** | **−24.8%** |
| **DXY 30%** 🏆 | **+16.49%** | **0.87** | **−24.8%** |
| USDKRW 50% | +16.23% | 0.85 | −24.8% |
| DXY 50% | +15.74% | 0.82 | −24.8% |

**🎯 핵심 발견 #3**: FX 30% 가 sweet spot
- 20%: 약함 (+0.04 Sharpe)
- 30%: 최적 (+0.07 Sharpe)
- 50%: 과함 (USDKRW +0.05, DXY +0.02)

**🎯 핵심 발견 #4**: 30% 가중에서는 USDKRW ≈ DXY
- 낮은 가중에서 FX 종류 덜 중요 — "있다/없다" 가 핵심
- 50% 에서만 USDKRW(0.85) > DXY(0.82) 차이 확연

[outputs/phase3_fx_overlay.html](outputs/phase3_fx_overlay.html)

### Phase 4: 최종 챔피언

**24 조합 sweep** 중 Sharpe 상위 5:

| 순위 | Config | CAGR | Sharpe | MDD |
|---|---|---:|---:|---:|
| 🏆 1 | **B + USDKRW 30%** | **+16.49%** | **0.87** | **−24.8%** |
| 2 | B + DXY 30% | +16.49% | 0.87 | −24.8% |
| 3 | C + USDKRW 30% | +16.49% | 0.87 | −24.8% |
| 4 | C + DXY 30% | +16.49% | 0.87 | −24.8% |
| 5 | B + USDKRW 50% | +16.23% | 0.85 | −24.8% |

상위 4개가 **tie** — B/C 는 같은 4쌍이므로 필연적 동일. USDKRW/DXY 30% 에서도 동일.

[outputs/phase4_champion.html](outputs/phase4_champion.html) | [outputs/final_champion_signals.csv](outputs/final_champion_signals.csv)

---

## 5. 현재 운영 구조 (이중 시그널)

> **업데이트**: Phase 1-4 에서 확정한 단일 챔피언이 §4.9~§4.12 후속 검증을 거쳐 **이중 시그널** (MAIN + ALERT) 구조로 발전. 정식 운영 스펙은 [FORMAL_REPORT](FORMAL_REPORT.pdf) 참조.

### 이중 시그널 개요

| 역할 | 모델 | Lookback | Full Sharpe | OOS Sharpe | 용도 |
|---|---|---|---:|---:|---|
| **MAIN** | 6M-only | [6] | **0.97** | **1.09** | 방향 결정, 포지션 크기 |
| **ALERT** | Champion [1,3,6] | [1, 3, 6] | 0.86 | 1.02 | 단기 조정 감지 (2018 Q4 같은) |

**공통 파라미터** (변경 없음):
- 4 경제축 섹터 페어 (IT / FIN / ENERGY / STAPLES)
- USDKRW 3M 모멘텀 30% 가중
- 월말 리밸런싱, 임계 ±0.02, 30 bp 거래비용

### 신호 일치/불일치 처리

| 상태 | 권고 포지션 |
|---|---|
| MAIN·ALERT 둘 다 KR | KOSPI 100% (full) |
| MAIN·ALERT 둘 다 US | S&P500 100% (full) |
| 불일치 (MAIN=KR, ALERT=US 등) | 부분 전환 (50/50) — 단기 조정 가능성 주시 |
| MAIN Neutral | 50/50 Blend 유지 |

**시그널 일치율**: 94% (174개월 중 164개월)
**전환 빈도**: MAIN 연 0.5회, ALERT 연 0.7회

### 기존 단일 챔피언 (아래 §5 원본, 참고용)

**이름**: **Sector 4-pair RS + FX 30%** (Phase 1-4 확정 버전)

**구성**:
- **신호 입력**: 4 경제축 섹터 페어 (IT / FIN / ENERGY / STAPLES)
- **FX 오버레이**: USDKRW 3M 모멘텀, 30% 가중
- **리밸런싱**: 월말
- **출력**: KOSPI 100% / S&P500 100% / 50-50 Neutral

### 월별 의사결정 프로세스

```
매월 말:
  1. 4개 섹터 페어에서 각각 RS (1/3/6M 로그수익 차 평균) 계산
     RS_i = avg(log(KR_i/past_KR_i) - log(US_i/past_US_i) for each lookback)

  2. 평균 RS = mean(RS_IT, RS_FIN, RS_ENERGY, RS_STAPLES)

  3. USDKRW 3M 수익률 → tanh(r/0.03) → fx_tilt ∈ [-1, +1]

  4. 합성: agg = 0.7 × mean_RS + 0.3 × fx_tilt × 0.02

  5. 판정 (임계 ±0.02):
     agg > +0.02 → 🇰🇷 KOSPI 100%
     agg < -0.02 → 🇺🇸 S&P500 100%
     그 외 → 이전 상태 유지 (hysteresis)
```

### 벤치마크 대비 이점

| 지표 | 챔피언 | S&P500 | 50/50 | KOSPI | 챔피언 vs S&P500 |
|---|---:|---:|---:|---:|---:|
| CAGR | **+16.49%** | +11.90% | +10.13% | +7.77% | **+4.59%p** |
| Sharpe | **0.87** | 0.83 | 0.65 | 0.39 | **+0.04** |
| MDD | −24.8% | −24.8% | −27.4% | −35.9% | 동일 |
| Win Rate | 64% | 66% | 61% | 55% | −2pp |

**요약**: MDD 같은 수준에서 CAGR +4.59%p 초과, Sharpe 도 앞섬.

---

## 6. 사고 과정의 교훈

### 🎯 교훈 1: 정보 많다고 항상 좋은 건 아님
- 5쌍 (전체) < 4쌍 (축소): CAGR 1.87%p, Sharpe 0.11, MDD 7.2pp 차이
- **원인**: IT-DISCR 상관 0.76 → DISCR 가 IT 신호를 복제·증폭. 쏠림 유발
- **교훈**: **상관 높은 feature 는 제거하는 게 낫다** (ML 기본 원리 재확인)

### 🎯 교훈 2: 데이터와 도메인 지식이 만나다
- 통계적 최소 상관 (B) 결과 = 경제축 이론 (C) 결과
- 둘 다 **IT + FIN + ENERGY + STAPLES** 선택
- **교훈**: 데이터 과학과 도메인 지식이 수렴하면 **결과 신뢰도 ↑**

### 🎯 교훈 3: FX 는 1차 채널
- Mean-RS 만 → Sharpe 0.80
- + FX 30% → Sharpe 0.87 (+0.07)
- **원인**: KR vs US PnL 에서 환율이 **가장 직접적 변수**
  - KR 주식 +5% but KRW -3% = USD 기준 +2% 만 벌음
  - FX 를 무시하면 "경제적으로 틀린 계산"
- **교훈**: **직교 정보만이 진짜 알파** (이전 실패 실험들 — Vol/Volume/Macro 2차효과들은 2차적)

### 🎯 교훈 4: 단순성의 미학
- 5 Agent Hierarchical? 실패 (Sharpe 0.74)
- 페어별 VIX overlay? 실패
- Cross-sectional dispersion/leadership? 실패
- **성공한 유일한 구조**: **"상관 낮은 4쌍 평균 + FX"** — 매우 단순

### 🎯 교훈 5: 데이터 출시일 확인은 필수
- KRX 섹터 지수 공식 발표일 조회 → pre-publication 구간 back-fill 확인
- 2011-04 이전 데이터는 "당시 실시간 참조 불가" → in-sample bias
- **교훈**: 백테스트 기간은 **실제 데이터 생산 가능했던 구간으로 제한**

---

## 7. 한계와 주의

### 통계적 취약점

1. **OOS 검증 미완** — 2011-04 이후 전 구간이 in-sample optimization
2. **Walk-forward 부재** — "2011-2018 optimize + 2019-2026 test" 미실시
3. **위기 샘플 부족** — 2020-03 COVID 하나. 2008/70년대 미포함

### 경제적 우려

4. **MDD −24.8% 여전히 고통** — 일반 투자자 견디는 선 −15~−20%
5. **비용 가정 낙관적** — 현실은 40-60 bps 가능 (ETF 스왑 + FX 스프레드)
6. **100% 집중 투자** — 중간 단계(70/30 등) 없음

### 방법론적 한계

7. **섹터 구성종목 현재 기준 역산** — KRX 가 지수 rebalance 시 편출된 종목은 과거에도 없음 (survivorship bias)
8. **월말 리밸런싱만 테스트** — 주간/2주 주기 대안 미탐색
9. **5쌍 pool 자체가 선택** — HEALTH/INDU/COMM (다른 시기 출시) 은 배제

### 향후 검증 과제

1. **Walk-forward OOS** — 명확한 시계열 분리
2. **2019-01 이후 clean period** — 모든 섹터 real-time publish 후 기간
3. **위기 시 행동 분석** — 2020-03 전후 세부 PnL
4. **다른 resample frequency** — 주간/2주 리밸런싱
5. **부분 전환 (70/30, 80/20)** — 100% 집중 완화
6. **4쌍 외 다른 조합** — KOSDAQ 150 섹터, 글로벌 섹터 ETF 등

---

## 8. 코드 구조

```
portfolio/strategy/sector_asset_allocation/
├── __init__.py       # 패키지 엔트리
├── core.py           # 공통 로직 (데이터·RS·FX·백테스트·성과)
├── experiment.py     # 4 Phase 순차 실행 + HTML 생성
├── README.md         # 이 보고서
└── outputs/          # 결과물
    ├── phase1_benchmarks.html      # Phase 1: 벤치마크
    ├── phase2_sector_selection.html # Phase 2: 섹터 구성 비교
    ├── phase3_fx_overlay.html       # Phase 3: FX 가중 sweep
    ├── phase4_champion.html         # Phase 4: 최종 24 조합
    └── final_champion_signals.csv   # 챔피언 월별 시그널
```

### 재실행

```bash
# 전체 실험 재실행 (5초 내 완료)
.venv/bin/python -m portfolio.strategy.sector_asset_allocation.experiment
```

### 특정 Config 만 테스트

```python
from portfolio.strategy.sector_asset_allocation.core import (
    Config, load_all_data, run_backtest, perf, SECTOR_PAIRS_ECO4,
)

pivot = load_all_data()
cfg = Config(
    name="MyTest",
    pairs=SECTOR_PAIRS_ECO4,
    w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
    tau=0.02,
)
bt = run_backtest(cfg, pivot)
print(perf(bt["strategy_return"], "MyTest"))
```

---

## 9. 주요 숫자 요약

| 항목 | 값 |
|---|---|
| 백테스트 기간 | 2011-04-01 ~ 2026-04-21 (179 개월) |
| 섹터 페어 수 | **4개** (IT, FIN, ENERGY, STAPLES) |
| 룩백 | 1M / 3M / 6M 로그수익 차 평균 |
| FX 지표 | USDKRW 3M 모멘텀 |
| FX 가중 | **30%** (RS 70%) |
| 임계값 | ±0.02 |
| 거래비용 | 30 bps one-way |
| **챔피언 CAGR** | **+16.49%** |
| **챔피언 Sharpe** | **0.87** |
| **챔피언 MDD** | **−24.8%** |
| vs S&P500 CAGR | **+4.59%p 우위** |
| vs S&P500 Sharpe | **+0.04 우위** |
| vs S&P500 MDD | 동일 |
| Win Rate | 64% |
| 총 거래 횟수 (전환) | (CSV 확인) |

---

## 10. 결론

**단순성 + 직교 정보 = 알파**.

1. **섹터 데이터는 유용하지만 전체가 아닌 선별이 중요**
   - 5쌍 → 4쌍 (상관 0.5 이상 페어 제거) 이 1.87%p CAGR 개선
2. **환율은 1차 알파 소스**
   - 단순 RS 에 USDKRW 30% 가중 추가로 Sharpe 0.80 → 0.87
3. **도메인 지식과 통계는 수렴**
   - 상관 최소 조합 = 경제축 이론 모두 **IT+FIN+ENERGY+STAPLES** 선택
4. **복잡한 구조는 해로웠음**
   - Hierarchical, Meta-weighting, Cross-sectional filter 모두 실패한 실험

**최종 권고**: 이 전략은 **벤치마크 대비 실질적 알파** 를 보이며, **실행도 단순**. 다만 OOS 검증 필요 (Phase 5 제안: walk-forward).

---

**작성**: 2026-04-22
**저자**: lifesailor (with Claude Code / Claude Opus 4.7)
**저장소**: [github.com/traderparamita/market-summary](https://github.com/traderparamita/market-summary)
