# market_summary → 자산배분 운용 플랫폼 확장 로드맵

> 2026-04-11 초안 작성
> 
> 2026-04-13 최종 업데이트: **Phase 0, 1, 2 완료** — 9개 View Agent 전체 구축 완료
> 
> 사용자: 운영자 / 1차 독자: PM·리서치 + PB·영업

---

## 진행 상황

```
[VISION Stage 1] ████████████████████ 100% — 시황 보고서 (Data + Story)
[VISION Stage 2] ████████░░░░░░░░░░░░  40% — 자산배분 View (Phase 0-2 완료)
[VISION Stage 3] ░░░░░░░░░░░░░░░░░░░░   0% — 자율 운용 Multi-Agent (Stage 2 안정화 후)
```

**Stage별 의미** ([VISION.md](VISION.md) 참조):
- **Stage 1 (완료)**: 사람을 돕는 도구 — 시장 데이터 수집 + 보고서 자동 생성
- **Stage 2 (진행 중)**: 사람과 협업하는 에이전트 — 분석·추천·근거 제시, 최종 결정은 사람
- **Stage 3 (미래)**: 자율 운용 Multi-Agent — Agent가 자율 판단·실행, 사람은 감독·개입

---

## 현재 완료 상태 (2026-04-13)

### ✅ Phase 0 — 인프라 토대 (100% 완료)

**3-Tier 출력 구조**
```
output/
├── summary/         # Market Summary (Data + Story) — Stage 1 완료
├── portfolio/aimvp/ # Portfolio Agent (AIMVP 전략) — Stage 2 시작
└── view/            # View Agent (9개 뷰) — Stage 2 핵심
```

**디자인 시스템 통일 (Mirae Asset 브랜드)**
- ✅ `portfolio/view/_shared.py` 신규 작성
  - Spoqa Han Sans Neo, #F58220 Orange, #043B72 Navy
  - `BASE_CSS` / `NAV_CSS` / `nav_html()` / `html_page()` 공통 함수
  - 9개 뷰 전체 적용 완료
- ✅ `output/view/index.html` — View Agent 허브 페이지
  - P1 진단(4) → P2 의사결정(5) → 배분안 흐름 다이어그램
  - ⏸️ 메인 `output/index.html`에 아직 미연동 (다음 단계)

**Core Components**
- ✅ `portfolio/universe.yaml` — 투자 가능 ETF 매핑 (asset_class → ticker → indicator_code)
- ✅ `portfolio/view/scoring.py` — 자산별 시그널 계산
  - 모멘텀×3, 추세 MA200/MA50, 52주 고점, vol ratio
  - VIX 방향, Breadth, 레짐 조건부 복합 점수
  - **sentiment_score/label** (−100~+100: Extreme Fear ~ Extreme Greed)
  - **regime_duration/since** (레짐 지속 일수 + 전환 날짜)
- ✅ `portfolio/backtest.py` — 공통 백테스트 엔진 (CAGR/Sharpe/MDD)
- ⏸️ `MKT200_PORTFOLIO_DAILY` DDL — Snowflake 테이블 미작성 (Phase 3 진입 시 필요)

**Commands/Skills 경로 정합**
- ✅ `/market-full` — 데이터 수집 → Dashboard → Story → 배포
- ✅ `/market-data` — 데이터 수집 + Data Dashboard만
- ✅ `/market-deploy` — output/ 변경분 commit + push
- ✅ `market-summary` 스킬 — Story 작성 규칙·절차

---

### ✅ Portfolio Agent — AIMVP 전략 (100% 완료)

**AIMVP RiskOn (Faber TAA 3-Signal Model)**
- ✅ Trend / Momentum / VIX 기반 3-신호 체계
- ✅ 동적 자산배분 (Stock/Bond/Cash)
- ✅ 월간 수익률 히트맵 (vs 75/25 초과수익)
- ✅ 누적 수익률 + 드로다운 차트
- ✅ 성과 비교 (Dynamic vs 75/25 vs 60/40 vs ACWI vs AGG)
- ✅ 장기 히스토리 백필 (2010~) via `backfill.py --snowflake`

**실행**
```bash
python -m portfolio.aimvp.generate --date 2026-04-09
python -m portfolio.aimvp.backfill --snowflake  # 장기 백필
```

**출력**: `output/portfolio/aimvp/{date}.html`

---

### ✅ Phase 1 — View Agent 진단 레이어 (100% 완료)

> **"현재 시장 어디에 있는가"** — 4개 독립 뷰 + 종합 해설

#### 데이터 인프라

**거시지표 확장**
- ✅ `portfolio/macro_indicators.yaml` — **37개 거시지표**
  - 🇺🇸 US (16): GDP, CPI/Core CPI/PCE/Core PCE, 실업률, NFP, 연준금리, 10Y/2Y, Yield Curve, IG/HY Spread, **M2 YoY**, **Fed Balance Sheet YoY**
  - 🇰🇷 KR (5): GDP QoQ/YoY, CPI YoY, 실업률, 기준금리
  - 🇯🇵 JP (4): GDP, CPI, 실업률, 중앙은행 금리
  - 🇨🇳 CN (4): GDP, CPI, 실업률, 중앙은행 금리
  - 🇪🇺 EU (4): GDP, CPI, 실업률, 중앙은행 금리
  - 🇬🇧 UK (4): GDP, CPI, 실업률, 중앙은행 금리
  - 🇮🇳 IN (4): GDP, CPI, 실업률, 중앙은행 금리
  - 🌍 Global (2): VIX, DXY

- ✅ `portfolio/collect_macro.py` — FRED + ECOS API 수집기
- ✅ `history/macro_indicators.csv` — 2020-01-01 ~ 2026-04-13 (14,206행)

#### 4개 진단 뷰

**1-A. Price View (가격 기반 시장 신호)** ✅
- ✅ `portfolio/view/price_view.py`
- **Market Pulse 섹션**
  - VIX 레짐/방향 (Low/High Volatility)
  - Yield Curve (Inverted/Normal/Steepening)
  - Breadth (% above MA200)
  - DXY 추세
- **Sentiment 카드** ✅ NEW
  - VIX regime + breadth_ma200_norm + nearness_52w_avg_norm
  - −100 ~ +100: Extreme Fear ~ Extreme Greed
  - 5단계 컬러 레이블 (Extreme Fear / Fear / Neutral / Greed / Extreme Greed)
- **Regime 지속 일수 + 전환 날짜** ✅ NEW
  - VIX rolling window 역산으로 레짐 전환 시점 추적
- **자산군별 OW/N/UW**
  - 레짐 조건부 복합 점수 (모멘텀, 추세, vol ratio 종합)
  - 개별 자산 점수 테이블 (6개 지표 × N개 자산)
- **출력**: `output/view/price/{date}.html`

**1-B. Macro View (거시지표 현황)** ✅
- ✅ `portfolio/view/macro_view.py`
- **Regime 헤더 카드** (US + KR 2×2)
  - Goldilocks (성장↑ 물가↓)
  - Reflation (성장↑ 물가↑)
  - Stagflation (성장↓ 물가↑)
  - Deflation (성장↓ 물가↓)
  - 불일치 시 경고 배너
- **8개 섹션**: US / KR / JP / CN / EU / UK / IN / Global
  - 지표 행별 **Z-score/방향** (High/Mid/Low + ↑→↓)
  - 마지막 업데이트 날짜 표시
- **FED Implied Rate 자동 계산**
  - US_2Y_YIELD − US_FED_RATE → 시장 금리 기대
- **Liquidity 섹션**
  - 실질금리 (US_10Y − CPI)
  - M2 YoY
  - Fed Balance Sheet YoY
- **출력**: `output/view/macro/{date}.html`

**1-C. Correlation View (자산 상관관계)** ✅
- ✅ `portfolio/view/correlation_view.py`
- **Core 8 자산**
  - S&P500 / NASDAQ / TLT / HYG / Gold / WTI / DXY / KOSPI
- **30일 / 90일 롤링 상관관계 히트맵** 나란히 표시
- **주식-채권 부호 신호**
  - 음수 = 분산 효과 작동
  - 양수 = 경고 (동반 하락 위험)
- **출력**: `output/view/correlation/{date}.html`

**1-D. Regime View (종합 국면 해설)** ✅
- ✅ `portfolio/view/regime_view.py`
- **규칙 기반 한국어 투자 해설 자동 생성** (외부 API 불필요)
  - ① 현재 시장 국면 진단
  - ② 주요 리스크 요인 (심각도 정렬 상위 3개)
  - ③ 자산군별 투자 의견 (OW/N/UW + 근거)
  - ④ 핵심 모니터링 지표
- **입력**: macro_view + price_view + correlation_view 신호 통합
- **출력**: `output/view/regime/{date}.html`

#### 실행 방법

```bash
# 개별 뷰 생성
python -m portfolio.view.price_view --date 2026-04-09 --html
python -m portfolio.view.macro_view --date 2026-04-09 --html
python -m portfolio.view.correlation_view --date 2026-04-09 --html
python -m portfolio.view.regime_view --date 2026-04-09 --html
```

---

### ✅ Phase 2 — View Agent 의사결정 레이어 (100% 완료)

> **"어디에 투자할 것인가"** — 5개 의사결정 뷰 (미래에셋생명 변액보험 운용 관점)

#### 데이터 확장

**시장 데이터 확장**
- ✅ `generate.py` TICKERS/INDICATOR_CODES 확장
  - **US 섹터 ETF 11개**: XLK / XLF / XLE / XLV / XLI / XLY / XLP / XLU / XLB / XLRE / XLC
  - **스타일 ETF 5개**: IVW(Growth) / IVE(Value) / QUAL(Quality) / MTUM(Momentum) / USMV(LowVol)
  - **채권 3개**: SHY / IEI / TIP
  - **기타**: VIX3M
- ✅ **역사적 데이터 백필** (2020-01-01~): 신규 ETF 모두 1,576행+ 확보

#### 5개 의사결정 뷰

**2-A. Country View (국가별 비교)** ✅
- ✅ `portfolio/view/country_view.py`
- **대상 8개국**
  - 🇺🇸 US / 🇰🇷 KR / 🇯🇵 JP / 🇨🇳 CN / 🇪🇺 EU / 🇬🇧 UK / 🇮🇳 IN / 🌍 EM
- **신호 체계**
  - 주가지수 모멘텀 (3M/6M/12M)
  - FX 추세 (vs USD)
  - 매크로 Regime (GDP/CPI)
  - ACWI 상대수익률
- **KRW 환산 수익률** + **환헤지 권고 배너**
  - USDKRW MA60 기반 환헤지 타이밍 제안
- **변액보험 펀드 매핑**
  - JP OW → 일본주식형
  - US OW → 미국주식형
  - EM OW → 신흥시장형
- **출력**: `output/view/country/{date}.html`

**2-B. Sector View (섹터 로테이션)** ✅
- ✅ `portfolio/view/sector_view.py`
- **US 섹터 (SPDR 11개)**
  - Tech (XLK) / Financial (XLF) / Energy (XLE) / Healthcare (XLV)
  - Industrial (XLI) / Cons Disc (XLY) / Cons Staples (XLP) / Utilities (XLU)
  - Materials (XLB) / Real Estate (XLRE) / Communication (XLC)
- **KR 섹터 (KODEX 4개)**
  - 반도체 / 2차전지 / 바이오 / 금융
- **Regime 친화도 매트릭스**
  - Goldilocks → Tech/Cons Disc
  - Reflation → Energy/Materials
  - Stagflation → Cons Staples/Utilities
  - Deflation → Defensive
- **KR-US 섹터 연계 비교**
- **출력**: `output/view/sector/{date}.html`

**2-C. Bond View (채권 구조·ALM)** ✅
- ✅ `portfolio/view/bond_view.py`
- **US 채권 8개 세그먼트**
  - **국채**: SHY(1-3Y) / IEI(3-7Y) / IEF(7-10Y) / TLT(20+Y)
  - **인플레이션**: TIP (TIPS)
  - **크레딧**: LQD (IG) / HYG (HY) / EMB (EM)
- **KR 채권 (ECOS)**
  - CD91D / 3Y / 10Y
- **크레딧 레짐**
  - HY 스프레드 분석 (Tight/Normal/Wide)
- **KR-US 금리차**
- **듀레이션 권고**
  - 금리 상승기 → Short Duration (SHY/IEI)
  - 금리 하락기 → Long Duration (TLT)
- **변액보험 ALM 권고**
  - 부채 듀레이션 매칭 제안
- **출력**: `output/view/bond/{date}.html`

**2-D. Style View (팩터 로테이션)** ✅
- ✅ `portfolio/view/style_view.py`
- **US 팩터 5개**
  - IVW (Growth) — 성장주
  - IVE (Value) — 가치주
  - QUAL (Quality) — 우량주
  - MTUM (Momentum) — 모멘텀
  - USMV (Low Volatility) — 저변동성
- **KR 비교**
  - KOSPI / KOSDAQ
  - US SmallCap / LargeCap
- **금리방향 × VIX레짐 × Regime 친화도 매트릭스**
  - 금리 상승 + 저변동성 → Value/Quality
  - 금리 하락 + 저변동성 → Growth
  - 고변동성 → Low Volatility/Quality
- **출력**: `output/view/style/{date}.html`

**2-E. Allocation View (변액보험 배분안)** ✅ **Phase 2 종착점**
- ✅ `portfolio/view/allocation_view.py`
- **변액보험 10개 펀드 카테고리**
  - 국내주식형 / 해외주식형 / 국내채권형 / 해외채권형
  - 국내주식혼합형 / 해외주식혼합형 / 채권혼합형
  - 특별자산형 / 부동산형 / 현금성자산
- **K-ICS 규제 자동 체크**
  - 주식 30% 한도 자동 체크
  - 초과 시 자동 조정 (채권혼합형으로 이동)
- **2-패널 구조**
  - KR 투자자 (KRW 기준) — 주력
  - US 참고 배분 — 벤치마크
- **Phase 1+2 모든 뷰 신호 통합**
  - 배분 근거 bullet 자동 생성
  - 국가/섹터/채권/스타일 뷰 권고 반영
- **출력**: `output/view/allocation/{date}.html`

#### 실행 방법

```bash
# 개별 뷰 생성
python -m portfolio.view.country_view --date 2026-04-09 --html
python -m portfolio.view.sector_view --date 2026-04-09 --html
python -m portfolio.view.bond_view --date 2026-04-09 --html
python -m portfolio.view.style_view --date 2026-04-09 --html
python -m portfolio.view.allocation_view --date 2026-04-09 --html
```

---

## 다음 단계 (Phase 1-E ~ Phase 7)

### ⏸️ Phase 1-E — View 탭 통합 (다음 우선순위)

**목표**: Market Summary HTML에 View 연동

- ❌ `generate.py` 수정 — View 탭 placeholder 추가
  - 기존: Data 탭 / Story 탭
  - 추가: **View 탭** (Phase 1+2 뷰 링크 + 요약 카드)
- ❌ `output/view/index.html` → 메인 `output/index.html`에 링크
- ❌ 주간/월간 보고서에도 View 섹션 추가

**검증**: `/market-data 2026-04-09` 실행 후 HTML View 탭 렌더 확인

---

### ⏸️ Phase 3 — 모델 포트폴리오 + 리밸런싱 시그널

**목표**: View → 실제 비중 산출

**신규 컴포넌트**
- ❌ `portfolio/strategies/` 디렉터리
  - `static_60_40.yaml` — 베이스라인
  - `risk_parity.yaml` — 변동성 기반
  - `taa_macro_tilt.yaml` — 베이스 60/40 ± 매크로 view tilt (±10%p 캡)
- ❌ `portfolio/builder.py` — 전략 yaml + Phase 1 view → 일일 목표 비중 dict
- ❌ `portfolio/rebalance.py` — 직전 비중 vs 신규 목표 → 리밸런싱 신호
  - 트리거: 캘린더(월말) + threshold(자산별 절대편차 ≥3%)
- ❌ `output/YYYY-MM/YYYY-MM-DD_portfolio.json` — 전략별 비중·시그널 저장 (gitignore)
- ❌ **Snowflake dual-write**: `MKT200_PORTFOLIO_DAILY` 적재

**검증**: `_portfolio.json` 생성 + Snowflake 쿼리 확인

---

### ⏸️ Phase 4 — 무료 데이터 소스 통합 (일부 선행 완료)

**목표**: 매크로 view 정확도 + 이벤트 대응 능력

**완료**
- ✅ `portfolio/collect_macro.py` — FRED + ECOS (37개 지표)
- ✅ `M2SL` — US M2 Money Supply YoY
- ✅ `WALCL` — Fed Balance Sheet YoY

**미해결 이슈**
- ❌ `KR_CORE_CPI_YOY` — ECOS item_code X0 확인 필요
- ❌ `KR_MFG_BSI` — ECOS 다층 item_code (C0000/AA) 구현 필요
- ❌ `US_ISM_MFG/SVC` — FRED series_id NAPM/NAPMNOI 오류 (대체 코드 필요)

**추가 계획**
- ❌ `fetchers/calendar.py` — 경제 캘린더 (향후 7일 이벤트)
- ❌ `fetchers/news.py` — Reuters/Bloomberg/연합 RSS 헤드라인
- ❌ `fetchers/earnings.py` — 14개 stock earnings calendar

---

### ⏸️ Phase 5 — 백테스트 + 검증 + 주간/월간 통합

**목표**: PM 신뢰 확보 레이어

**신규 기능**
- ❌ `portfolio/backtest.py` 강화
  - Phase 0 미니 엔진 → 전략 yaml들에 대한 walk-forward
  - equity curve, drawdown, exposure, turnover
  - **hit rate** (view 적중률 — OW 자산이 N/UW 자산을 outperform 했는가)
- ❌ 백테스트 결과를 View 탭 하단에 시각화
  - 누적수익 라인
  - 월별 hit rate 표
- ❌ 주간/월간 보고서 통합
  - `generate_periodic.py` 수정
  - 일간 view 평균/말일 기준 요약 + 기간 백테스트 성과

**검증**: 백테스트 결과 카드 렌더 + `/market-full 2026-04-13` 실행

---

### ⏸️ Phase 6 — 이중 페르소나 narrative

**목표**: 같은 시그널을 두 톤으로

**PM/리서치 톤**
- 점수, z-score, 신뢰도, 리스크 시나리오, 백테스트 metric
- Phase 1-5에서 산출된 정량 정보 그대로

**PB/영업 톤**
- 시장 내러티브 중심, 한국 증권사 모닝코멘트 톤
- Claude가 동일 시그널 dict를 받아 다른 톤으로 재작성
- `market-summary` 스킬에 `--audience pm|pb` 옵션 추가

**HTML 토글**
- View 탭 안에 PM ⇄ PB 토글 버튼
- 두 narrative 모두 임베드

**8주 MVP 도달 지점**: 매일 매크로 view + 모델 PF + 섹터 view + 백테스트 카드 + 두 가지 톤의 해설

---

### ⏸️ Phase 7+ — 자산배분 운용으로의 진화 (MVP 이후)

**목표**: Stage 2 → Stage 3 전환 (사람 협업 → 자율 운용)

사용자가 명시한 "그 정보를 기반으로 자산배분 운용으로 이어진다" 단계.

**운용 레이어**
1. **Paper trading**
   - 모델 PF별로 가상 NAV 일일 추적
   - 포지션 변화 히스토리, 실현/미실현 손익
   - Snowflake `MKT201_PORTFOLIO_NAV` 신규

2. **운용 의사결정 워크플로우**
   - 매일 아침 리밸런싱 시그널 → 슬랙/이메일 알림
   - 사람이 승인 → 실행 기록

3. **위험 모니터링**
   - VaR, vol target 위반
   - Drawdown 임계, 단일자산 익스포저 한도
   - 위반 시 알림

4. **이벤트 트리거 액션**
   - FOMC/CPI 직후 자동 view 재산출
   - 의견 변경 시 PB 알림

5. **(장기) Live 운용 어댑터**
   - 증권사 API (KIS, 키움 등) 연동
   - MVP 아키텍처가 paper/live 구분만으로 갈리도록 처음부터 분리 인터페이스

**Stage 3 진입 조건** ([VISION.md](VISION.md) 참조):
- Paper trading 6개월 이상
- View 적중률 60% 이상
- MDD 관리 입증
- Agent 간 합의 프로토콜 안정화
- **사람의 판단** — 시스템을 신뢰할 수 있다는 운영자의 확신

---

## Context

현재 market_summary는 56개 글로벌 지표를 매일 수집하고 Data 대시보드 + Claude가 쓴 Market Story를 산출하는 "모닝미팅 시황 보고서" 수준이다 (Stage 1 완료).

사용자는 이 위에:
1. **증권사 애널리스트 업무**(매크로 전략 + 섹터/테마 로테이션) 자동화 → Stage 2 진행 중
2. **실제 자산배분 운용**까지 발전 → Stage 3 목표

### 핵심 결정

- **MVP(8주)**: 매일 자산배분 view + 모델 포트폴리오 산출 (Phase 0-6)
- **독자**: PM/리서치 + PB/영업 (이중 페르소나)
- **데이터**: 무료 소스 최대 활용 (FRED, yfinance, investpy, FMP free, RSS, FDR)
- **그 다음**: 같은 시그널/PF 위에 paper-trading → 실제 자산배분 운용 레이어 (Phase 7+)

### 기존 인프라 강점

- `history/market_data.csv`: 15개월 (2025-01 ~ 2026-04) 일별 시계열 → 백테스트 가능
- `_data.json`: 카테고리별 dict로 정규화 → 자산배분 엔진 입력으로 그대로 사용
- `inject_stories.py`: placeholder 치환 패턴 → 새 View 탭에 재사용 가능

---

## 핵심 파일 구조

```
market_summary/
├── generate.py                   # 일일 데이터 수집 + HTML 보고서 생성
├── generate_periodic.py          # 주간/월간 집계 보고서
├── inject_stories.py             # Story 주입 유틸
├── snowflake_loader.py           # CSV ↔ Snowflake 적재 유틸
├── history/
│   ├── market_data.csv           # ✅ 시장 가격 시계열 (56개 지표, 일별)
│   └── macro_indicators.csv      # ✅ 거시지표 시계열 (37개 지표, 14,206행)
├── portfolio/
│   ├── universe.yaml             # ✅ 자산 유니버스 정의
│   ├── backtest.py               # ✅ 공통 백테스트 엔진
│   ├── macro_indicators.yaml     # ✅ 37개 거시지표 정의
│   ├── collect_macro.py          # ✅ FRED + ECOS 수집기
│   ├── aimvp/                    # ✅ AIMVP RiskOn 전략
│   │   ├── generate.py
│   │   ├── backfill.py
│   │   ├── signals.py
│   │   ├── model.py
│   │   ├── config.py
│   │   └── data_adapter.py
│   ├── view/
│   │   ├── _shared.py            # ✅ 공유 디자인 시스템 (Mirae Asset 브랜드)
│   │   ├── scoring.py            # ✅ 자산 점수 계산
│   │   ├── price_view.py         # ✅ [P1] 가격 기반 시장 신호 뷰
│   │   ├── macro_view.py         # ✅ [P1] 거시지표 뷰
│   │   ├── correlation_view.py   # ✅ [P1] 자산 상관관계 히트맵
│   │   ├── regime_view.py        # ✅ [P1] 종합 국면 해설 (규칙 기반)
│   │   ├── country_view.py       # ✅ [P2] 8개국 OW/N/UW
│   │   ├── sector_view.py        # ✅ [P2] US 11섹터 + KR 4섹터
│   │   ├── bond_view.py          # ✅ [P2] 채권 커브·크레딧·ALM
│   │   ├── style_view.py         # ✅ [P2] 팩터 로테이션
│   │   └── allocation_view.py    # ✅ [P2] 변액보험 배분안 (K-ICS)
│   ├── builder.py                # ❌ Phase 3
│   ├── rebalance.py              # ❌ Phase 3
│   └── strategies/               # ❌ Phase 3
│       ├── static_60_40.yaml
│       ├── risk_parity.yaml
│       └── taa_macro_tilt.yaml
├── fetchers/                     # ❌ Phase 4 (calendar/news/earnings)
├── output/
│   ├── index.html                # ✅ 메인 허브 (Summary 전용)
│   ├── summary/                  # ✅ Market Summary 일/주/월간
│   ├── portfolio/aimvp/          # ✅ AIMVP 백테스트 리포트
│   └── view/
│       ├── index.html            # ✅ View 허브 (9개 뷰, 메인 미연동)
│       ├── price/                # ✅ [P1] Price View
│       ├── macro/                # ✅ [P1] Macro View
│       ├── correlation/          # ✅ [P1] Correlation View
│       ├── regime/               # ✅ [P1] Regime View (종합 해설)
│       ├── country/              # ✅ [P2] Country View
│       ├── sector/               # ✅ [P2] Sector View
│       ├── bond/                 # ✅ [P2] Bond View
│       ├── style/                # ✅ [P2] Style View
│       └── allocation/           # ✅ [P2] Allocation View (배분안)
└── .claude/
    ├── commands/                 # ✅ /market-full, /market-data, /market-deploy
    └── skills/market-summary/    # ✅ Story 작성 규칙
```

---

## 검증 전략

각 Phase는 다음 방법으로 end-to-end 동작 확인:

- **Phase 0**: `python -m portfolio.view.scoring --date 2026-04-09` → 자산별 점수 표 출력
- **Phase 1**: `/market-data 2026-04-09` 실행 후 View 탭 렌더 확인 (기존 Data/Story 탭 무손상)
- **Phase 2**: 섹터/스타일 ETF가 `history/market_data.csv`에 추가 + View 탭 렌더 확인
- **Phase 3**: `_portfolio.json` 생성 + Snowflake `MKT200_PORTFOLIO_DAILY` 쿼리
- **Phase 4**: FRED 호출 결과가 `_data.json`에 저장 + 매크로 view 룰 사용 확인
- **Phase 5**: 백테스트 결과 카드 렌더 + `/market-full 2026-04-13` 주간/월간 View 섹션 갱신
- **Phase 6**: PM ⇄ PB 토글 동작 + 두 톤이 시그널은 동일하게 인용하는지 spot check

각 Phase 종료 시 `history/market_data.csv`와 기존 일일/주간/월간 보고서가 깨지지 않았다는 회귀 확인을 함께 한다.

---

## 우선순위 결정 가이드

8주가 부족하면 다음 우선순위로 컷:

1. **유지**: Phase 0, 1, 2 (MVP 핵심 — 매일 view + 9개 뷰) ✅ 완료
2. **유지**: Phase 5의 백테스트 (PM 신뢰 확보용)
3. **컷 후순위**: Phase 3의 섹터 ETF 확장 (주식 view 안에 OW일 때만 실효)
4. **컷 후순위**: Phase 4의 news/earnings (FRED만 우선)
5. **컷 후순위**: Phase 6의 PB 톤 (Phase 1의 PM 톤만으로 시작)

**Phase 7 운용 레이어는 Phase 1-5가 안정화된 후에만 시작.**

---

## 미해결 이슈 (Known Issues)

### 데이터 수집
- ❌ `KR_CORE_CPI_YOY` — ECOS item_code X0 확인 필요
- ❌ `KR_MFG_BSI` — ECOS 다층 item_code (C0000/AA) 구현 필요
- ❌ `US_ISM_MFG/SVC` — FRED series_id NAPM/NAPMNOI 오류, 대체 코드 필요

### 인프라
- ⏸️ `MKT200_PORTFOLIO_DAILY` DDL — Snowflake 테이블 미작성 (Phase 3 진입 시 필요)
- ⏸️ View 허브 연동 — `output/view/index.html` → 메인 `output/index.html`에 링크 (사용자 승인 시)

---

## 참고 문서

- [VISION.md](VISION.md) — Stage 1/2/3 전체 진화 비전
- [CLAUDE.md](../CLAUDE.md) — 프로젝트 실행 방법 + 전체 구조
- [MKT200_PORTFOLIO_DAILY.sql](MKT200_PORTFOLIO_DAILY.sql) — Snowflake DDL (미작성)
