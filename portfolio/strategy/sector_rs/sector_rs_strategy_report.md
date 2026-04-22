# KR vs US 섹터 상대강도 전략 연구 보고서

**일자**: 2026-04-22
**대상**: 투자 전략 입문자 + 이 프로젝트 히스토리 참조용
**핵심 결과**: 4쌍 경제축 섹터 + USDKRW 30% 가중 모델, CAGR +16.34% / Sharpe 0.87 / MDD −24.8% (194 개월 백테스트)

---

## 0. 이 문서에 대해

이 보고서는 "**매달 한국(KOSPI)과 미국(S&P500) 중 어느 쪽에 투자해야 하는가?**" 라는 질문에 대한 답을 **데이터 기반으로 자동화**하려 시도한 실험 기록입니다.

6 라운드 실험을 거쳐 최종 모델을 찾았으며, 그 과정에서 얻은 교훈과 실패한 가설도 함께 기록합니다. 단순히 결과만 적는 보고서가 아니라 **"왜 단순한 모델이 이겼는가"** 에 대한 방법론 반성이기도 합니다.

---

## 1. 문제 정의

### 1.1 일상의 질문

개인 투자자도 운용 전문가도 매달 마주치는 결정:
- 이번 달 KR 주식 더 살까? US 주식 더 살까?
- 둘 다 반반 놓을까?
- 아니면 현금화?

기존 답변의 한계:
- **감(感)으로 결정**: 뉴스/애널리스트 의견에 흔들림, 일관성 없음
- **고정 비율(예: 50/50)**: 단순하지만 시장 상황 무시
- **리밸런싱 규칙**: 비중 맞추는 룰은 있어도 타이밍 판단 없음

### 1.2 이 프로젝트의 목표

> **"섹터별 가격 데이터만으로 KR vs US 방향을 객관적으로 판단하는 모델 만들기"**

3가지 제약:
1. **데이터 제한**: 섹터 가격, 환율, VIX 같은 공개 정보만 사용
2. **단순성**: 블랙박스 AI 아닌 해석 가능한 규칙
3. **실행 가능**: 월 1회 리밸런싱, 현실적 거래 비용

### 1.3 벤치마크

다음 3개를 이겨야 의미 있는 전략:

| 벤치마크 | CAGR | Sharpe | MDD | 설명 |
|---|---:|---:|---:|---|
| 50/50 Blend | +11.04% | 0.72 | −27.4% | KR:US 균등 매달 리밸런싱 |
| KOSPI | +9.06% | 0.46 | −35.9% | 한국 시장만 (매수 후 보유) |
| S&P500 | +12.41% | **0.86** | −24.8% | 미국 시장만 (매수 후 보유) |

---

## 2. 기본 개념 (초보자 가이드)

### 2.1 섹터(Sector)란?

시장을 산업별로 나눈 것. 예:
- **IT**: 기술주 (삼성전자, Apple, NVIDIA)
- **Financials**: 금융 (KB금융, JPMorgan)
- **Energy**: 에너지 (SK이노베이션, ExxonMobil)
- **Staples**: 생필품 (CJ제일제당, Coca-Cola)

전세계 표준은 **GICS (Global Industry Classification Standard)** — 11개 섹터. 이 프로젝트는 GICS 기준 KR 섹터와 US 섹터를 매칭합니다.

### 2.2 상대강도(Relative Strength, RS)

> "**KR 섹터가 US 섹터보다 얼마나 더 잘 올랐는가?**"

계산:
```
RS = log(KR_섹터_현재 / KR_섹터_과거) - log(US_섹터_현재 / US_섹터_과거)
```

예: 지난 3개월 KR IT 가 +10% 올랐고 US IT 가 +3% 올랐다면
`RS = log(1.10) - log(1.03) = 0.095 - 0.030 = +0.065 (약 +6.5%)`

해석: 지난 3개월간 KR IT 가 US IT 를 6.5%p 앞섬.

### 2.3 백테스트(Backtest)

> **"과거 데이터에 전략을 돌려보는 시뮬레이션"**

"2010년 1월 31일에 이 모델이 KR 을 사라고 했다면, 2월 말까지 KR 수익은 얼마였을까?" 같은 계산을 **194개월 반복**.

주의점:
- **과적합(Overfitting)**: 과거에 잘 맞도록 파라미터 조정하면 미래에 실패
- **Look-ahead bias**: 과거 시점에서 알 수 없던 정보로 판단하는 오류
- **거래비용 무시**: 현실 수수료 반영 안 하면 결과 과대 추정

### 2.4 핵심 지표 설명

| 지표 | 의미 | 좋은 값 |
|---|---|---|
| **CAGR** | 연평균 수익률 (복리) | 높을수록 좋음 |
| **Sharpe** | 위험 대비 수익 (수익/변동성) | 1 이상이 우수 |
| **MDD** | 최대 낙폭 (고점 대비) | 낮을수록 좋음 |
| **Win Rate** | 수익 낸 달의 비율 | 55%+ 이상 의미 있음 |

### 2.5 임계값 & 거래비용

**임계값(Threshold)**: 신호가 이 값 이상이면 포지션 전환 — 작은 흔들림에 매번 사고팔지 않도록.

**거래비용(Transaction Cost)**: 이 프로젝트는 30 bps (0.3%) one-way 가정. 1억 원 전환 시 30만 원.

---

## 3. 데이터 셋업

### 3.1 8 GICS 공통 섹터 페어

KR (KOSPI200 GICS 지수) ↔ US (SPDR 섹터 ETF) 1:1 매칭:

| # | 페어 | KR 코드 | US 코드 |
|---|---|---|---|
| 1 | IT | IX_KR_IT | SC_US_TECH |
| 2 | Financials | IX_KR_FIN | SC_US_FIN |
| 3 | Healthcare | IX_KR_HEALTH | SC_US_HEALTH |
| 4 | Industrials | IX_KR_INDU | SC_US_INDU |
| 5 | Energy | IX_KR_ENERGY | SC_US_ENERGY |
| 6 | Consumer Discretionary | IX_KR_DISCR | SC_US_DISCR |
| 7 | Consumer Staples | IX_KR_STAPLES | SC_US_STAPLES |
| 8 | Communication | IX_KR_COMM | SC_US_COMM |

HEAVY/CONSTR/STEEL 같은 KR 고유 섹터는 억지 매핑이라 **제외**.

### 3.2 데이터 소스

- **Snowflake `MKT100_MARKET_DAILY`** 를 단일 정본으로 사용 (이 프로젝트의 경우 `portfolio.market_source` 경유)
- 2010-01-04 ~ 현재, 일별 OHLCV
- `SC_US_COMM` 은 2018-06 부터 (XLC ETF 상장 이후) — 이전은 7쌍으로 동작

### 3.3 백테스트 설정

- 기간: **2010-02 ~ 2026-03 (194 개월)**
- 리밸런싱: 월말 (Business Month End)
- 거래비용: **30 bps one-way**
- 포지션: {100% KR, 100% US, 50/50 Neutral} 중 하나

---

## 4. 실험 여정 — 6 라운드

### 4.1 Round 1 — Mean-RS (sync) 🎯

**가설**: "8 페어의 평균 상대강도가 양수면 KR, 음수면 US"

**파일**: [portfolio/strategy/sector_rs_sync.py](../portfolio/strategy/sector_rs_sync.py)

**로직**:
```
1. 각 페어에서 RS 계산 (1M / 3M / 6M 평균)
2. 8 페어 평균 RS 계산
3. 임계값 ±0.02 (log-return diff)
   - 평균 > +0.02 → KR
   - 평균 < -0.02 → US
   - 그 외 → 이전 상태 유지 (hysteresis)
```

**결과**:

| 지표 | Mean-RS | vs 벤치마크 |
|---|---:|---|
| CAGR | **+15.62%** | vs Blend +4.6%p |
| Sharpe | **0.83** | vs S&P500 −0.03 |
| MDD | −32.0% | vs S&P500 −7.2pp |
| Win Rate | 64% | vs Blend +2pp |

**교훈**:
- 첫 시도부터 벤치마크를 뚜렷이 앞섬
- 단순한 평균이 복잡한 로직보다 효과적일 수 있음을 시사
- MDD 는 여전히 큼 — 개선 여지

### 4.2 Round 2 — Hierarchical v1 (가격 + 변동성 + 거래량)

**가설**: "페어별로 독립 투표하고, 과거 정확도 기반 가중평균하면 더 낫겠다"

**파일**: [portfolio/strategy/sector_rs_hier.py](../portfolio/strategy/sector_rs_hier.py)

**로직**:
```
[각 페어 독립 에이전트]
  - RS (70%)
  - Vol ratio: KR 조용할수록 KR 편향 (30%)
  - Volume 확인
  → 페어별 KR/US/Hold 투표

[Meta 레이어]
  - 최근 6개월 페어별 hit rate 계산
  - hit rate 높은 페어에 가중치 ↑

[리스크 오버레이]
  - VIX > 30 시 50/50 블렌드로 희석
```

**결과**:

| 지표 | Hier v1 | vs Mean-RS |
|---|---:|---|
| CAGR | +12.90% | **−2.72%p** |
| Sharpe | 0.74 | −0.09 |
| MDD | −27.2% | +4.8pp 개선 |

**교훈** (중요한 실패):
- **구조만 복잡하게 해서는 안 됨** — Mean-RS 보다 뒤처짐
- 같은 가격축 정보를 쥐어짜도 알파 안 나옴
- Vol/Volume 은 가격의 파생 → **정보 중복**, 노이즈만 추가
- MDD 는 개선됐지만 CAGR 손실이 너무 큼

### 4.3 Round 3 — v2 Parameter Sweep (11개 변형 튜닝)

**가설**: "Hierarchical 의 파라미터를 제대로 튜닝하면 개선될 것"

**파일**: [portfolio/strategy/sector_rs_hier.py](../portfolio/strategy/sector_rs_hier.py) — Config dataclass + SWEEP_CONFIGS

**11개 변형**: baseline, no_vix, low_tau, pure_rs, equal_meta, no_volume, combo_1, combo_2, +dispersion, +leadership, +both

**결과** (상위 5):

| Config | CAGR | Sharpe | MDD |
|---|---:|---:|---:|
| no_vix 🏆 | +13.11% | 0.75 | −27.0% |
| baseline | +12.90% | 0.74 | −27.2% |
| no_volume | +13.19% | 0.73 | −29.5% |
| equal_meta | +12.40% | 0.73 | −30.4% |
| combo_1 | +13.20% | 0.72 | −29.3% |

**교훈**:
- **VIX stress overlay 가 drag** — 확신 순간을 희석
- **Adaptive meta weighting 효과 미미** — 페어별 hit rate 가 크게 갈리지 않음
- **Cross-sectional 필터 (dispersion/leadership) 는 오히려 해로움** — Leadership 은 regime transition 을 너무 자주 Neutral 로 몰아감
- **여전히 Mean-RS (0.83) 를 못 넘음** — 최고 Sharpe 0.75

### 4.4 Round 4 — Macro Sensitivity (섹터별 매크로 주입)

**가설**: "각 섹터가 고유한 매크로 변수에 민감하니, 섹터별 매크로 tilt 추가하면 개선"

**파일**: [portfolio/strategy/sector_rs_macro.py](../portfolio/strategy/sector_rs_macro.py)

**섹터-매크로 매핑**:

| 페어 | 매크로 변수 | 로직 |
|---|---|---|
| IT | DXY 3M | 달러↑ → 원화↓ → KR IT 수출 유리 |
| FIN | US Yield Curve | 가파름 → US 은행 마진 우위 |
| ENERGY | WTI 3M | 유가↑ → KR 에너지/화학 우위 |
| INDU | Copper / DXY 역방향 | 구리↑ 약달러 → KR 중공업 |
| DISCR | HY Spread 3M | 축소 → 위험선호 → 고베타 KR |
| STAPLES | VIX 수준 | 높음 → 안전자산 → US 우위 |
| HEALTH | DXY 3M | 약달러 → KR 헬스 미세 유리 |
| COMM | NVDA 3M | AI 붐 → US Comm 직수혜 |

**결과** (Macro 가중별):

| Config | CAGR | Sharpe | MDD |
|---|---:|---:|---:|
| macro_w20 🏆 | +14.01% | 0.77 | −30.9% |
| macro_w30_lowtau | +13.69% | 0.75 | −29.3% |
| macro_w10 | +13.46% | 0.74 | −32.4% |
| v2_best_no_macro | +12.63% | 0.74 | −30.2% |
| macro_only (70%) | +10.93% | 0.63 | −25.6% |

**교훈**:
- **Macro tilt 는 Hierarchical 에 도움** — v2_best 대비 +1.38%p CAGR
- **최적 매크로 가중 = 20%** — 낮으면 약함, 높으면 과민 반응
- **그래도 Mean-RS (15.62%) 를 못 넘음** — Hierarchical 구조 자체의 한계
- **"섹터 고유 매크로"** 접근 자체는 타당했음 (WTI ← ENERGY 등). 하지만 예측력 한계

### 4.5 Round 5 — FX Isolated (환율 단독 실험)

**가설**: "KR vs US PnL 에 가장 직접적인 건 환율이다. 다른 매크로 다 빼고 FX 만 테스트"

**파일**: [portfolio/strategy/sector_rs_fx.py](../portfolio/strategy/sector_rs_fx.py)

**10개 변형**: mean_rs, rs_usdkrw_w03/w05, rs_dxy_w03/w05, rs_both_w03/w05, per_pair_fx, fx_only_*

**결과**:

| Config | CAGR | Sharpe | MDD |
|---|---:|---:|---:|
| **rs_usdkrw_w05** 🏆 | **+16.29%** | **0.87** | −30.9% |
| rs_both_w05 | +16.29% | 0.87 | −30.9% |
| rs_usdkrw_w03 | +15.93% | 0.84 | −32.0% |
| rs_dxy_w03 | +15.77% | 0.84 | −32.0% |
| **Mean-RS (baseline)** | +15.62% | 0.83 | −32.0% |
| fx_only_dxy | +12.92% | 0.74 | −34.2% |
| fx_only_usdkrw | +12.52% | 0.71 | −34.2% |

**교훈** (**Breakthrough!**):
- **Mean-RS + USDKRW (50%) 가 strictly dominate** — CAGR +0.67%p, Sharpe +0.04, MDD +1.1pp 개선
- **S&P500 Sharpe (0.86) 를 최초로 이김**
- **USDKRW > DXY** — 직접 환율이 광의 달러지수보다 유효
- **FX 단독은 약함** — 섹터 RS 가 main, FX 는 확증 역할
- **진짜 직교 정보**: FX 는 currency translation 의 1차 채널

### 4.6 Round 6 — 4쌍 축소 (최종 챔피언 🏆)

**가설**: "8 페어 중 상관 높은 것들(IT-DISCR, HEALTH-STAPLES) 은 정보 중복. 경제축 4개만 쓰면 더 깔끔"

**파일**: [portfolio/strategy/sector_rs_4pairs.py](../portfolio/strategy/sector_rs_4pairs.py) (monkey-patch 드라이버)

**선택한 4쌍**:

| 페어 | 경제축 | 설명 |
|---|---|---|
| IT ↔ Tech | **성장 / Duration** | 장기 자산, 금리 민감 |
| FIN ↔ Financials | **가치 / Curve** | 예대마진, 크레딧 사이클 |
| ENERGY ↔ Energy | **커머디티 / 인플레** | 유가 연동 |
| STAPLES ↔ Staples | **방어 / Consumer** | 저베타 |

**결과**:

| Config | CAGR | Sharpe | MDD |
|---|---:|---:|---:|
| **4쌍 rs_usdkrw_w03** 🏆 | **+16.34%** | **0.87** | **−24.8%** |
| 4쌍 rs_usdkrw_w05 | +16.10% | 0.86 | −24.8% |
| 4쌍 rs_dxy_w03 | +16.34% | 0.87 | −24.8% |
| 4쌍 mean_rs | +15.02% | 0.80 | −24.8% |

**핵심 발견**:
- **8쌍 최고 MDD −30.9% → 4쌍 −24.8%** (6.1pp 극적 개선)
- **S&P500 MDD 와 동일 (−24.8%)** — 벤치마크 수준 달성
- **CAGR 도 근소하게 개선** (+16.34% vs 이전 +16.29%)
- **Sharpe 0.87** 유지 (S&P500 0.86 초과)

**MDD 개선 메커니즘**:
- 8쌍은 IT-DISCR-COMM 이 상관 0.7+ → 성장주 덩어리 쏠림
- 4쌍은 4축이 상대적으로 분산 → 위기 시 STAPLES 가 평균 끌어올림
- FX 가중 30% 가 sweet spot (8쌍 보다 덜 필요 — 이미 분산됨)

---

## 5. 최종 챔피언 상세

### 5.1 전략 정의

**이름**: Sector RS + FX (4-pair)
**구성**:
- **신호 입력**: 4 경제축 섹터 페어 (IT / FIN / ENERGY / STAPLES)
- **FX 오버레이**: USDKRW 3M 모멘텀, 30% 가중
- **리밸런싱**: 월말
- **출력**: KOSPI 100% / S&P500 100% / 50-50 Neutral

### 5.2 월별 의사결정 프로세스

```
매월 말:
  1. 4개 섹터 페어에서 각각 RS (1M/3M/6M 로그수익 차 평균) 계산
  2. 4 RS 산술평균 = mean_rs
  3. USDKRW 3M 수익률 → tanh normalize → fx_tilt
  4. agg = 0.7 × mean_rs + 0.3 × fx_tilt × 0.02
  5. 임계값 ±0.02:
     agg > +0.02 → 🇰🇷 KOSPI 100%
     agg < -0.02 → 🇺🇸 S&P500 100%
     else → 이전 상태 유지 (hysteresis)
```

### 5.3 실제 예시 (2026-03-31 월말)

**페어별 RS**:

| 페어 | KR 3M | US 3M | KR 6M | US 6M | 평균 RS |
|---|---:|---:|---:|---:|---:|
| IT | +25.4% | −7.9% | +64.4% | −5.6% | **+27.5%** |
| FIN | +16.8% | −9.9% | +23.0% | −7.9% | **+16.1%** |
| ENERGY | +13.1% | +32.1% | +25.9% | +33.1% | **−19.1%** |
| STAPLES | +6.2% | +6.0% | +8.5% | +5.9% | **+0.5%** |

- **평균 RS = +6.23%** (KR 섹터 평균 6.2%p 앞섬)
- **USDKRW**: 1440 → 1507 (+4.6%) → fx_tilt = +0.911
- **agg = 0.7 × 0.0623 + 0.3 × 0.911 × 0.02 = +0.0491**
- **> +0.02 → KR 시그널**

**실제 결과** (다음달, 2026-04):
- KOSPI +26.4%, S&P500 +8.2%
- 전략은 KR 선택 → **+26.4% 획득** (US 선택했으면 +8.2%)

### 5.4 성과 테이블 (전체 비교)

| 전략 | CAGR | Sharpe | MDD | Win | 특징 |
|---|---:|---:|---:|---:|---|
| **★ 4쌍 + USDKRW w03** | **+16.34%** | **0.87** | **−24.8%** | 63% | **챔피언** |
| 8쌍 + USDKRW w05 | +16.29% | 0.87 | −30.9% | 64% | FX 실험 최고 |
| 8쌍 Mean-RS | +15.62% | 0.83 | −32.0% | 64% | 초기 기준선 |
| Macro w20 | +14.01% | 0.77 | −30.9% | 63% | Hier + macro best |
| Hier v2 no_vix | +13.11% | 0.75 | −27.0% | 63% | Hier 최고 |
| S&P500 | +12.41% | 0.86 | −24.8% | 66% | 벤치마크 |
| 50/50 Blend | +11.04% | 0.72 | −27.4% | 62% | 벤치마크 |
| KOSPI | +9.06% | 0.46 | −35.9% | 56% | 벤치마크 |

---

## 6. 직교성 검증 (사후 분석)

**질문**: "4쌍 선택이 정말 직교한가? 아니면 우연?"

### 6.1 상관계수 매트릭스 (RS 3M, 92개월)

내 4쌍 내부:
- IT–ENERGY: +0.13 ✓ (직교)
- FIN–ENERGY: +0.14 ✓ (직교)
- IT–FIN: +0.47 (중간)
- FIN–STAPLES: +0.51 ⚠ (예상보다 높음)
- IT–STAPLES: +0.34
- ENERGY–STAPLES: +0.23

8쌍 중 가장 상관 높은 페어:
- **IT–DISCR: +0.76** (거의 동일 신호)
- IT–INDU: +0.51
- FIN–INDU: +0.47

### 6.2 70개 4-조합 전체 비교

전체 C(8,4) = 70개 조합을 내부 평균 상관으로 정렬:

| 순위 | 조합 | 평균 상관 |
|---|---|---:|
| 🥇 1 | IT·HEALTH·INDU·COMM | +0.215 |
| 2 | IT·FIN·HEALTH·COMM | +0.218 |
| 3 | IT·HEALTH·STAPLES·COMM | +0.224 |
| **★ 36** | **IT·FIN·ENERGY·STAPLES (제 선택)** | **+0.302** |
| 70 | IT·FIN·INDU·DISCR | +0.557 |

→ **36/70 중위권**. 특별히 직교하지 않음.
→ 8쌍 전체 평균 상관 +0.308 과 거의 동일.

### 6.3 PCA — 실제 독립 차원

| PC | 설명력 | 누적 | 해석 |
|---|---:|---:|---|
| PC1 | 41.0% | 41.0% | 전체 RS 강도 |
| PC2 | 20.2% | 61.1% | 경기민감 vs 방어 |
| PC3 | 10.6% | 71.7% | COMM/STAPLES vs FIN |
| PC4 | 8.8% | 80.5% | IT/ENERGY vs STAPLES/COMM |

→ **8쌍의 실제 독립 차원 ≈ 4** (PC1-4 로 80.5% 설명)

### 6.4 결정적 증거

**corr(8쌍 평균 RS, 4쌍 평균 RS) = +0.95**

→ 사실상 **같은 신호**. 4쌍 축소는 정보 95% 보존.

### 6.5 재해석

| 주장 | 실제 |
|---|---|
| "4축 경제적 직교성" | **부분 사실** — 일부 페어만 직교, 일부는 높음 |
| "4쌍이 정보 보존" | **맞음** — 0.95 상관, PCA 도 지지 |
| "직교성이 MDD 개선 원인" | **아닐 가능성** — DISCR/INDU (IT 와 고상관) 제거의 부수 효과 |
| "더 직교한 4쌍이 더 좋을 것" | **미검증** — 순위 1 조합 백테스트 필요 |

---

## 7. 솔직한 한계

### 7.1 통계적 취약점

1. **샘플 하나짜리 백테스트 (2010~2026, 16년)**
   - 한 경제 레짐만 경험 (저금리·저인플레·글로벌라이제이션)
   - 2008 금융위기, 70년대 스태그플레이션 미포함
   - Future regime 에서 동일 작동 보장 없음

2. **In-sample 선택 편향**
   - 8 GICS 페어는 사전에 제가 고름
   - USDKRW 는 macro sweep **결과를 보고** isolated 테스트
   - 4쌍 축소는 MDD 개선 **예감한 뒤** 검증
   - 여러 선택의 누적 편향 존재

3. **Walk-forward OOS 검증 부재**
   - 모든 실험이 전체 기간 in-sample
   - 2010-2018 optimize + 2019-2026 OOS 같은 rigor 없음

### 7.2 경제적 우려

4. **MDD −24.8% 여전히 고통**
   - 일반 투자자 견디는 선은 −15~−20%
   - 전략 중단 유혹 큼 → 실제 실행 리스크

5. **비용 가정 낙관**
   - 30 bps 는 기관 수준
   - 현실: KR↔US ETF 스왑 + FX 스프레드 40-60 bps 가능성
   - 비용 민감도 미검증

6. **위기 시 작동 불확실**
   - USDKRW 상승 → 모델이 "KR 사라"
   - 하지만 KR 위기 때 KRW 도 폭락 (flight-to-quality)
   - 2008, 2020-03 샘플 1개 뿐

7. **100% 올인 집중 위험**
   - KR 선택 시 전량 KOSPI 매수 (삼성전자 25%+ 편중)
   - 실제 기관은 이렇게 집중 투자 안 함

### 7.3 방법론 성찰

8. **직교성 논리 사후 분석에서 약함**
   - 내 4쌍이 특별히 직교하지 않음 (사후 분석 결과)
   - "경제축" 내러티브는 합리화에 가까울 수 있음
   - 진짜 원인은 IT-correlated 섹터 제거의 부수 효과

9. **비표준 구성**
   - 이 정확한 4쌍을 지지하는 학술 프레임워크 부재
   - Dalio All-Weather, Stovall cycle, GICS 11 전체 같은 표준 미사용

---

## 8. Claude 의 역할

이 프로젝트 전 과정을 Claude (Sonnet 4.6 / Opus 4.7, Claude Code 환경) 와 페어워크 방식으로 진행했습니다. 객관적 기록을 위해 **도움이 된 부분**과 **한계/오류**를 모두 적습니다.

### 8.1 도움이 된 부분

1. **코드 생성 속도 10x**
   - 각 라운드 Python 모듈 (300-800 줄) 을 5-10 분 내 초안 완성
   - 직접 작성했다면 2-3 시간 소요
   - Config dataclass, argparse, HTML 리포트 보일러플레이트 즉시 작성

2. **여러 가설 병렬 탐색**
   - Round 3: 11개 config 변형을 한 번에 sweep
   - Round 5: 10개 FX 변형을 동시 비교
   - 사용자가 하나씩 시도했으면 몇 배의 시간

3. **패턴 인식 및 반성**
   - Round 2 실패 후 "복잡도 < 단순성" 원칙 명시화
   - Round 4 후 "진짜 직교 정보 필요" 가설 도출
   - Round 5 breakthrough 후 원인 분석 (FX 가 1차 채널인 이유)

4. **솔직한 비평**
   - 사용자가 "전략 평가" 요청 시 방어적이지 않은 평가
   - MDD, OOS 검증 부재, in-sample 편향 지적
   - "돌파구 아닌 점진 개선" 같은 명확한 톤

5. **사후 검증 제안**
   - 직교성 질문에 **실제로 상관 매트릭스 + PCA 돌려 검증**
   - 제 4쌍이 36/70 중위권임을 실증적으로 확인

6. **문서화 및 가독성**
   - HTML 리포트 생성 (Chart.js, 성과 테이블)
   - 이 문서 같은 내러티브 형태 정리
   - 초보자용 번역 (기술 용어 → 일상 언어)

### 8.2 한계와 오류

1. **버그 및 즉석 실수**
   - `MIN_PAIRS = 5` 하드코딩 → 4쌍 variant 에서 전부 skip (수정 필요)
   - `normalize=True` + `tau=0.02` 조합 스케일 오류 → Round 5 초기 결과 왜곡
   - 4pairs 드라이버에서 sync.MIN_PAIRS 도 패치 필요했음

2. **테스트 부족**
   - 각 모듈을 제대로 자기검증하지 않고 "돌려보고 결과 확인" 방식
   - 더 조심스러웠으면 2-3 번 덜 재돌릴 수 있었음

3. **사용자 요청 해석 모호**
   - "최대한 자세히" vs "너무 무식한 작업" 같은 모순 신호 혼선
   - 우선순위 판단 실수 가능성

4. **과도한 초기 자신감**
   - Round 2 (Hierarchical) 제안 시 성능 확신 → 실제로는 후퇴
   - Cross-sectional 필터 (dispersion/leadership) 예상 도움 → 실제 drag
   - "복잡한 구조가 낫다"는 사전 믿음 교정 필요했음

5. **직교성 주장의 사후 실증 부족**
   - 4쌍 "경제축 직교" 주장 시 실제 상관 검증 안 함
   - 사용자가 "직교성에 대해서 얘기해달라" 한 뒤에야 데이터 봄
   - 처음부터 직교 검증했으면 더 정직했을 것

6. **데이터 정확성 가정**
   - MKT100 데이터 품질 전제 (simulate 없음)
   - Snowflake dual-write drift 등 운영 이슈 영향 가능성 고려 미흡

### 8.3 협업 패턴 성찰

가장 효과적이었던 워크플로우:
```
[사용자] 가설 제안 또는 질문
    ↓
[Claude] 가설 구현 (코드 + 백테스트)
    ↓
[결과 관찰]
    ↓
[Claude] 솔직한 평가 (성공 / 실패 / 교훈)
    ↓
[사용자] 다음 방향 선택
    ↓
반복
```

비효과적이었던 순간:
- Claude 가 먼저 "A/B/C 중 고르세요" 하지 않고 하나 선택해 실행
- 사용자가 지루해하거나 방향성 모호해졌을 때 Claude 가 더 자주 선택지 제시
- 직교성 / 표준 프랙티스 같은 메타 질문 나오기 전까지 내러티브에 몰입

### 8.4 Claude 없었다면?

솔직한 평가:
- 최종 결과 (4쌍 + USDKRW) 는 **상대적으로 직관적**이라 단독으로도 도달 가능
- 하지만 **6 라운드 × 40+ config 변형 비교는 실질적으로 불가** (시간)
- 문서화 (HTML 리포트, 이 MD) 도 혼자면 훨씬 나중에
- **주요 가치**: 아이디어 검증 속도 + 솔직한 피드백 동시 제공

---

## 9. 파일 맵 / 재현 방법

### 9.1 전략 모듈

| 파일 | 설명 |
|---|---|
| [portfolio/strategy/sector_rs_sync.py](../portfolio/strategy/sector_rs_sync.py) | Round 1 — Mean-RS (기준선) |
| [portfolio/strategy/sector_rs_hier.py](../portfolio/strategy/sector_rs_hier.py) | Round 2, 3 — Hierarchical v1/v2 + Sweep |
| [portfolio/strategy/sector_rs_macro.py](../portfolio/strategy/sector_rs_macro.py) | Round 4 — Macro Sensitivity |
| [portfolio/strategy/sector_rs_fx.py](../portfolio/strategy/sector_rs_fx.py) | Round 5 — FX Isolated |
| [portfolio/strategy/sector_rs_4pairs.py](../portfolio/strategy/sector_rs_4pairs.py) | Round 6 — **최종 챔피언 드라이버** |

### 9.2 실행 방법

```bash
# 각 라운드 개별 실행
.venv/bin/python -m portfolio.strategy.sector_rs_sync   --date 2026-04-21
.venv/bin/python -m portfolio.strategy.sector_rs_hier   --sweep --date 2026-04-21
.venv/bin/python -m portfolio.strategy.sector_rs_macro  --date 2026-04-21
.venv/bin/python -m portfolio.strategy.sector_rs_fx     --date 2026-04-21

# ★ 최종 챔피언 (4쌍 + USDKRW w03)
.venv/bin/python -m portfolio.strategy.sector_rs_4pairs --date 2026-04-21
```

### 9.3 출력 위치

```
output/portfolio/strategy/
├── rs_sync/            # Round 1
├── rs_hier/            # Round 2, 3
├── rs_macro/           # Round 4
├── rs_fx/              # Round 5 (8쌍)
└── rs_fx_4pairs/       # Round 6 (4쌍, ★ 최종)
    ├── 2026-04-21_sweep.html                   # 전체 비교 대시보드
    └── 2026-04-21_rs_usdkrw_w03_signals.csv    # 월별 시그널 (챔피언)
```

### 9.4 차트

[sector_rs_performance.png](sector_rs_performance.png) — 6라운드 주요 전략 누적수익 + Drawdown 비교

---

## 10. 다음 단계

### 10.1 즉시 가치 있는 검증

1. **Walk-forward OOS 검증** — 2010-2018 optimize / 2019-2026 test
2. **Crisis period 분석** — 2020-03 (COVID), 2022-06 (인플레 shock) 각각 PnL
3. **Rolling 36M Sharpe 플롯** — 성능 steady 한지 lumpy 한지
4. **파라미터 robustness** — lookback ±2M, τ ±0.005 흔들기

### 10.2 직교성 재탐색

1. **순위 1 조합 (IT·HEALTH·INDU·COMM) 백테스트** — 제 4쌍보다 MDD 낮을 가능성
2. **PCA factor 직접 사용** — PC1 (전반 강도) + PC2 (경기 rotation) 를 신호로
3. **자동 선택** — 매월 가장 상관 낮은 4쌍 동적 선택

### 10.3 섹터별 확장

1. **Per-sector directional model** — 4 섹터 각각 KR/US 독립 선택 → 25% 씩 분산
2. **Conviction-weighted** — RS 강도에 따라 포지션 크기 조절
3. **Tilt-only** — 현재 모델 + 강한 확신 섹터 오버레이

### 10.4 Production 준비

1. **일일/월간 시그널 생성기** — 현재 포지션 자동 계산
2. **Telegram 알림 연동** — 시그널 변경 시 즉시 통보
3. **대시보드 통합** — output/portfolio/strategy/ 를 index.html 에 연결
4. **실행 ETF 매핑** — KOSPI (KODEX 200) / S&P500 (SPY 또는 TIGER 미국S&P500)

---

## 부록 A: 용어집

| 용어 | 의미 |
|---|---|
| RS (Relative Strength) | 두 자산 간 수익 차. KR 섹터 - US 섹터 |
| CAGR | 연복리 수익률 |
| Sharpe Ratio | (수익-무위험금리) / 변동성. 위험 대비 수익 |
| MDD | Max Drawdown. 고점 대비 최대 하락률 |
| Win Rate | 수익 발생 월의 비율 |
| Hysteresis | 임계값 내 신호는 이전 상태 유지 (잦은 전환 억제) |
| Overfitting | 과거에만 잘 맞고 미래엔 실패하는 과적합 |
| In-sample / Out-of-sample | 최적화 기간 / 검증 기간 |
| Log return | log(P_t / P_{t-1}), 복리 합산이 쉬운 수익률 |
| Hit rate | 맞춘 예측 비율 |
| Hierarchical | 개별 의견 → 가중합 구조 |
| Meta-weighting | 과거 적중도 기반 가중 조정 |

## 부록 B: 주요 숫자 요약

| 항목 | 값 |
|---|---|
| 백테스트 기간 | 2010-02 ~ 2026-03 (194 개월) |
| 페어 수 (최종) | 4개 (IT, FIN, ENERGY, STAPLES) |
| 룩백 | 1M / 3M / 6M 평균 |
| 임계값 | ±0.02 |
| FX 가중 | 30% (USDKRW 3M) |
| 거래비용 | 30 bps one-way |
| 리밸런싱 | 월말 |
| 챔피언 CAGR | +16.34% |
| 챔피언 Sharpe | 0.87 |
| 챔피언 MDD | −24.8% |
| vs 50/50 Blend CAGR | +5.3%p |
| vs 50/50 Blend Sharpe | +0.15 |
| vs 50/50 Blend MDD | +2.6pp 개선 |

---

**작성자**: lifesailor (with Claude)
**도구**: Claude Code (Opus 4.7 / Sonnet 4.6), Python 3.12, Snowflake MKT100/MKT200
**저장소**: [github.com/traderparamita/market-summary](https://github.com/traderparamita/market-summary)
