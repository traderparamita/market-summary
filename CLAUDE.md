# Market Summary

일일/주간/월간 글로벌 시장 요약 보고서를 자동 생성하는 프로젝트.

## 실행 방법

매일 영업일 08:00 KST 전체 워크플로우:

```
/market-full [YYYY-MM-DD]    # 데이터 수집 → Dashboard → Story(일/주/월) → 배포
```

개별 단계:

```
/market-data [YYYY-MM-DD]    # 데이터 수집 + Data Dashboard만
/market-deploy               # output/ 변경분 commit + push
```

Market Story 작성 규칙·절차는 **`market-summary` 스킬**에 있다 (Story 작업 시 자동 로드).

**주의**: 미래 날짜의 보고서를 미리 생성하지 않는다.

## 구조

```
collect_market.py         # 시장 데이터 수집 전용 - TICKERS/INDICATOR_CODES + fetch_data/build_report_data
generate.py               # HTML 보고서 생성 전용 - collect_market에서 수집 함수 import + Snowflake dual-write
generate_periodic.py      # 주간/월간 집계 보고서 생성
generate_sector_country.py # 섹터·국가 초보자 보고서 생성 (11일 사이클, /sector-country 커맨드)
snowflake_loader.py       # CSV ↔ Snowflake MKT100_MARKET_DAILY 적재 유틸 (bulk / upsert)
simulate.py               # 과거 날짜 시뮬레이션
inject_stories.py         # 시뮬레이션 보고서에 Story 주입
gen_assets.py             # favicon 등 assets 생성
history/market_data.csv       # 일별 시계열 (10컬럼 대문자, Snowflake MKT100_MARKET_DAILY 1:1)
history/macro_indicators.csv  # 거시지표 시계열 (7컬럼 대문자)

portfolio/
├── market_source.py # Snowflake MKT100/MKT200 리더 유틸 (CSV fallback) — 모든 reader 의 단일 진입점
├── io.py            # CSV 공통 유틸 - load_csv_dedup(), append_save_csv()
├── aimvp/           # Portfolio Agent (AIMVP RiskOn 전략)
│   ├── generate.py      # 백테스트 HTML 생성
│   ├── backfill.py      # 장기 히스토리 백필 (2010~)
│   ├── signals.py       # TAA 신호 계산
│   ├── model.py         # 가중치 모델
│   ├── config.py        # 전략 파라미터
│   └── data_adapter.py  # CSV → 월간 데이터
├── view/            # View Agent (Phase 1 진단 + Phase 2 의사결정)
│   ├── _shared.py          # 공유 디자인 시스템 (Mirae Asset 브랜드)
│   │                       #   BASE_CSS / NAV_CSS / nav_html() / html_page()
│   │                       #   Spoqa Han Sans Neo, #F58220 Orange, #043B72 Navy
│   ├── scoring.py          # 자산 점수 계산 (sentiment_score, regime_duration 포함)
│   ├── price_view.py       # [P1] 가격 기반 시장 신호 뷰 (모멘텀, 추세, VIX, 폭, Sentiment)
│   ├── macro_view.py       # [P1] 거시지표 뷰 (GDP, 인플레이션, 고용 등, Regime 헤더)
│   ├── correlation_view.py # [P1] 자산 상관관계 히트맵 뷰 (30/60/90일 롤링)
│   ├── regime_view.py      # [P1] 종합 국면 뷰 (규칙 기반 한국어 투자 해설)
│   ├── country_view.py     # [P2] 8개국 OW/N/UW (모멘텀+FX+매크로+KRW 환헤지)
│   ├── sector_view.py      # [P2] US 11섹터 + KR 4섹터 로테이션
│   ├── bond_view.py        # [P2] 채권 커브·크레딧·ALM 포지셔닝
│   ├── style_view.py       # [P2] 팩터 로테이션 (Growth/Value/Quality/Momentum/LowVol)
│   └── allocation_view.py  # [P2] 변액보험 펀드 배분안 (K-ICS 체크, KR+US 2-패널)
├── collect_macro.py     # 거시지표 수집 (FRED/ECOS) — macro_indicators.yaml 정의 기반
├── collect_sector_etfs.py # 섹터/스타일/채권 ETF 72개 이력 수집 (yfinance)
├── macro_indicators.yaml # 거시지표 정의 (FRED/ECOS 지표 + 확장 지표 통합)
├── backtest.py      # 공통 백테스트 엔진
├── universe.yaml    # 자산 유니버스
├── strategies/      # 전략 YAML
└── strategy/        # 멀티에이전트 전략 모델
    └── sector_rotation.py  # KR vs US 월간 로테이션 (Momentum+Breadth+RelStrength)
```

**CSV 스키마** (영문 대문자, Snowflake MKT100_MARKET_DAILY 와 정렬):
```
DATE, INDICATOR_CODE, CATEGORY, TICKER, CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE
```

- `INDICATOR_CODE`: MKT000_MARKET_INDICATOR 의 `지표코드` (EQ_KOSPI, BD_US_10Y, ...). `collect_market.py` 상단 `INDICATOR_CODES` dict 로 `(category, ticker) → 지표코드` 매핑.
- `SOURCE`: 실제 수집 승자 (`yfinance` / `investiny` / `FDR` / `ECOS`)
- KR bond 행은 OHLCV 전부 NULL (ECOS 는 금리만)
- FX/risk 행은 VOLUME NULL (시장 특성)

## 데이터 소스

| 섹션 | 1차 소스 | 폴백 |
|------|----------|------|
| Equity | yfinance | FinanceDataReader → investiny |
| Bonds & Rates | yfinance (US), ECOS API (KR) | — |
| Bond ETF | yfinance | — |
| FX | investiny | FinanceDataReader |
| Commodities | investiny | yfinance |
| Risk (VIX, VKOSPI) | yfinance | FinanceDataReader |
| Major Stocks | yfinance | — |

- FX/Commodity는 `needs_inv_fix = True`로 항상 FDR → investiny 순 보정 시도
- 모든 Data Dashboard 읽기: **Snowflake MKT100_MARKET_DAILY 가 단일 정본** (2026-04-21 전환). `history/market_data.csv` 는 legacy mirror + simulate.py 용 fallback (`SNOWFLAKE_DISABLE=1` 로 강제 전환). 모든 reader 는 `portfolio.market_source.load_long()` / `load_wide_close()` / `load_macro_long()` 경유.
- Snowflake `MKT100_MARKET_DAILY` 는 CSV 의 미러. `generate.py main()` 이 CSV append 직후 dual-write (해당 일자 DELETE + INSERT, best-effort; Snowflake 실패해도 CSV 는 살아있음)
- 전체 재수집은 `python snowflake_loader.py --truncate` 로 CSV 통째로 벌크 적재
- 모든 Market Story: Claude 작성. 주간/월간은 일간 `_story.html`들을 종합

## 수집 대상

전체 56개 지표 (MKT000_MARKET_INDICATOR 와 1:1).

- **Equity** (17): KOSPI, KOSDAQ, S&P500, NASDAQ, Russell2K, STOXX50, DAX, CAC40, FTSE100, Nikkei225, Shanghai, HSI, NIFTY50, MSCI World/ACWI/LATAM/EMEA
- **Bond** (11): US 2Y/10Y/30Y, TLT, AGG, HYG, LQD, EMB, KR CD91D/3Y/10Y
- **FX** (7): DXY, USD/KRW, EUR/USD, USD/JPY, USD/CNY, AUD/USD, GBP/USD
- **Commodity** (6): WTI, Brent, Gold, Silver, Copper, Nat Gas
- **Risk** (1): VIX (VKOSPI 는 `TICKERS` 에 선언만 있고 수집 실패 지속 — INDICATOR_CODES 미포함)
- **Stocks** (14): NVIDIA, Broadcom, Alphabet, Amazon, META, Apple, Microsoft, Tesla, TSMC, Samsung, Palantir, Alibaba, Meituan, Tencent

## 핵심 함수

- `_inject_existing_story(path, new_html)`: 보고서 재생성 시 기존 Story 보존 + `_save_story_file()` 자동 호출
- `_save_story_file(html_path, html_content)`: HTML에서 Story 추출 → `_story.html` 별도 저장 (Story가 있을 때만)

## 출력

```
output/
├── index.html                   # 메인 허브 (Summary + Portfolio + View)
├── summary/                     # Market Summary 일/주/월간 보고서
│   ├── index.html              # Summary 인덱스
│   ├── YYYY-MM/
│   │   ├── YYYY-MM-DD.html     # 일일 보고서 (Data + Story 탭)
│   │   ├── YYYY-MM-DD_story.html
│   │   └── YYYY-MM-DD_data.json
│   ├── weekly/
│   │   ├── YYYY-WNN.html
│   │   └── YYYY-WNN_story.html
│   └── monthly/
│       ├── YYYY-MM.html
│       └── YYYY-MM_story.html
├── sector-country/              # 섹터·국가 초보자 포지셔닝 보고서 (11일 사이클)
│   └── daily/
│       └── YYYY-MM/
│           ├── YYYY-MM-DD.html       # Data + Story 탭 (섹터 Day N/11 · 국가 Day M/11)
│           └── YYYY-MM-DD_story.html
├── portfolio/                   # Portfolio Agent
│   └── aimvp/
│       └── YYYY-MM-DD.html     # 백테스트 리포트
└── view/                        # View Agent
    ├── index.html              # View Agent 허브 (9개 뷰 한눈에 보기, 메인에 미연동)
    ├── price/          → YYYY-MM-DD.html  # [P1] 가격 기반 시장 신호 뷰
    ├── macro/          → YYYY-MM-DD.html  # [P1] 거시지표 뷰
    ├── correlation/    → YYYY-MM-DD.html  # [P1] 자산 상관관계 히트맵
    ├── regime/         → YYYY-MM-DD.html  # [P1] 종합 국면 + 투자 해설
    ├── country/        → YYYY-MM-DD.html  # [P2] 8개국 OW/N/UW
    ├── sector/         → YYYY-MM-DD.html  # [P2] 섹터 로테이션
    ├── bond/           → YYYY-MM-DD.html  # [P2] 채권 구조·ALM
    ├── style/          → YYYY-MM-DD.html  # [P2] 팩터 로테이션
    └── allocation/     → YYYY-MM-DD.html  # [P2] 변액보험 배분안
```

GitHub Pages로 자동 배포 (main 브랜치 push 시 `output/` 폴더)

## 환경

- Python 3.12 (`.venv/` 로컬 venv 권장; gitignore 됨)
- 의존성: yfinance, FinanceDataReader, requests, python-dotenv, investiny, snowflake-connector-python[pandas], PyYAML
- 환경변수 (`.env` 에서 dotenv 로딩):
  - `ECOS_API_KEY` — 한국은행 ECOS API
  - `FRED_API_KEY` — 미국 FRED API (거시지표)
  - `SNOWFLAKE_ACCOUNT` / `SNOWFLAKE_USER` / `SNOWFLAKE_PASSWORD` / `SNOWFLAKE_DATABASE` / `SNOWFLAKE_SCHEMA` / `SNOWFLAKE_WAREHOUSE` — Snowflake dual-write

## 주의사항

- HTML 보고서는 Data 탭과 Story 탭 2개로 구성. Story가 없으면 placeholder 유지
- Data 탭의 각 섹션 헤더에 데이터 소스 표시 (src-tag CSS 클래스)
- `history/market_data.csv`: OHLCV 시계열, 10 대문자 컬럼. git 에 커밋됨. **legacy mirror** — simulate.py 시뮬레이션 (point-in-time cutoff) 에서만 authoritative. 평상시 read 는 Snowflake MKT100 이 우선
- `.gitignore`: `_data.json`, `data/`, `history/market_data.csv.bak_*`, `.venv/`, `.DS_Store` (macOS 메타데이터) 포함
- investiny 소스가 주말 날짜 데이터를 반환할 수 있음 → 수집 시 자동 필터링
- `generate.py` 의 dual-write 는 `--start` 없이 실행한 일간 수집에만 작동. 전체 재수집은 반드시 `snowflake_loader.py --truncate` 로 별도 벌크 적재

## Portfolio Agent & View Agent

market_summary 프로젝트는 두 가지 agent를 포함:

### 1. Portfolio Agent (aimvp)

market-strategy 프로젝트에서 통합된 AIMVP RiskOn 전략. Faber TAA 3-Signal Model.

**목적**: TAA 전략 백테스트 + 성과 분석

**핵심 기능**:
- Trend / Momentum / VIX 기반 3-신호 체계
- 동적 자산배분 (Stock/Bond/Cash)
- 월간 수익률 히트맵 (vs 75/25 초과수익)
- 누적 수익률 + 드로다운 차트
- 성과 비교 (Dynamic vs 75/25 vs 60/40 vs ACWI vs AGG)

실행:
```
python -m portfolio.aimvp.generate --date 2026-04-09
```

출력: `output/portfolio/aimvp/{date}.html`

장기 히스토리 백필 (2010~):
```
python -m portfolio.aimvp.backfill --snowflake
```

### 2. View Agent (view)

현재 시점 분석 뷰. 향후 섹터/리스크/팩터 뷰 추가 가능 (확장 구조).

**목적**: 현재 상태 분석 (백테스트 없음)

#### 2.1 Price View (가격 기반 시장 신호)

**핵심 기능**:
- Market Pulse: VIX 레짐/방향, Yield Curve, Breadth, DXY, **Sentiment 카드**
- 자산군별 OW/N/UW 뷰 (레짐 조건부 복합 점수)
- 개별 자산 점수 테이블 (모멘텀 3개, 추세 MA200/MA50, 52주 고점, vol ratio)
- 가격 기반 레짐 자동 감지 (VIX + Breadth) + **레짐 지속 일수/전환 날짜**

실행:
```
python -m portfolio.view.price_view --date 2026-04-09 --html
```

출력: `output/view/price/{date}.html`

데이터 소스: `history/market_data.csv`

#### 2.2 Macro View (거시지표)

**수집 완료 지표** (2020~):
- 🇺🇸 미국 (16): GDP QoQ/YoY, CPI/Core CPI/PCE/Core PCE YoY, 실업률, NFP, 연준금리, 10Y/2Y 국채, Yield Curve, IG/HY Spread, **M2 YoY**, **Fed Balance Sheet YoY**
- 🇰🇷 한국 (5): GDP QoQ/YoY, CPI YoY, 실업률, 기준금리
- 🌍 글로벌 (2): VIX, DXY

**추가 기능 (Phase 1-B)**:
- 지표 행마다 vs 평균 백분위 (High/Mid/Low) + 방향 화살표 (↑→↓)
- US/KR 2×2 Regime 헤더 카드 (Goldilocks/Reflation/Stagflation/Deflation)
- FED Implied Rate (2Y − Fed Funds) 정책 섹션 자동 계산
- Liquidity 섹션: 실질금리 + M2 YoY + Fed Balance Sheet

**미구현 이슈**:
- `KR_CORE_CPI_YOY` — ECOS item_code X0 확인 필요
- `KR_MFG_BSI` — ECOS 다층 item_code 미구현
- `US_ISM_MFG/SVC` — FRED series_id 오류, 교체 필요

실행:
```
# 데이터 수집 (FRED + ECOS API)
python -m portfolio.collect_macro --start 2010-01-01

# HTML 생성
python -m portfolio.view.macro_view --date 2026-04-09 --html
```

출력: `output/view/macro/{date}.html`

데이터 소스: `history/macro_indicators.csv` (7컬럼: DATE, INDICATOR_CODE, CATEGORY, REGION, VALUE, UNIT, SOURCE)

#### 2.3 Correlation View (자산 상관관계)

**핵심 기능**:
- Core 8 자산 (S&P500/NASDAQ/TLT/HYG/Gold/WTI/DXY/KOSPI) 롤링 상관관계
- 30일 / 90일 히트맵 나란히 표시
- 핵심 신호: 주식-채권 상관관계 부호 (음수 = 분산 효과 작동, 양수 = 경고)

실행:
```
python -m portfolio.view.correlation_view --date 2026-04-09 --html
```

출력: `output/view/correlation/{date}.html`

#### 2.4 Regime View (종합 국면 해설)

**핵심 기능**:
- macro_view + price_view + correlation_view 신호 통합
- 규칙 기반 한국어 투자 해설 자동 생성 (외부 API 불필요)
  1. 현재 시장 국면 진단
  2. 주요 리스크 요인 (심각도 정렬 상위 3개)
  3. 자산군별 투자 의견 (OW/N/UW + 근거)
  4. 핵심 모니터링 지표

실행:
```
python -m portfolio.view.regime_view --date 2026-04-09 --html
```

출력: `output/view/regime/{date}.html`

**Phase 2 뷰 완료 (의사결정 레이어)**:
- `view/country_view.py` - 8개국 OW/N/UW, KRW 환헤지 배너 ✅
- `view/sector_view.py` - US 11섹터 + KR 4섹터 로테이션 ✅
- `view/bond_view.py` - 채권 커브·크레딧·ALM 포지셔닝 ✅
- `view/style_view.py` - Growth/Value/Quality/Momentum 팩터 ✅
- `view/allocation_view.py` - 변액보험 펀드 배분안 (K-ICS 체크) ✅

실행:
```
python -m portfolio.view.country_view --date YYYY-MM-DD --html
python -m portfolio.view.sector_view --date YYYY-MM-DD --html
python -m portfolio.view.bond_view --date YYYY-MM-DD --html
python -m portfolio.view.style_view --date YYYY-MM-DD --html
python -m portfolio.view.allocation_view --date YYYY-MM-DD --html
```

출력: `output/view/{country,sector,bond,style,allocation}/{date}.html`

#### 디자인 시스템 (`_shared.py`)

**Mirae Asset 브랜드** 공통 적용 (2026-04-13 완료):
- `portfolio/view/_shared.py`: `BASE_CSS`, `NAV_CSS`, `nav_html()`, `html_page()` 제공
  - Spoqa Han Sans Neo 서체, #F58220 (Orange), #043B72 (Navy) 변수
  - `nav_html(date_str, current)`: 스티키 네이비 nav 생성, NAV_CSS를 직접 포함하지 않음
  - `html_page(title, date_str, body, current_view, extra_css, source)`: P2 다크 테마 뷰를 라이트 테마로 래핑
  - **NAV CSS 주입 규칙**: P1/country/sector 뷰는 자체 `<head><style>` 블록에 `{NAV_CSS}` 주입. P2 bond/style/allocation은 `html_page()` → `BASE_CSS`로 자동 포함.
- `output/view/index.html`: 9개 뷰 허브 페이지 (분석 흐름 다이어그램 + 카드). **메인 index.html에 아직 미연동**.

### 공통

- `portfolio/backtest.py`: 정적/동적 전략 백테스트 엔진
- `portfolio/universe.yaml`: 자산 유니버스 정의
- `portfolio/strategies/`: 전략 YAML 설정

- Portfolio Agent / Price View / Sector Rotation: **Snowflake MKT100** 단일 정본 (via `portfolio.market_source`). 시뮬레이션 모드에서만 CSV
- Macro View: `history/macro_indicators.csv` (FRED + ECOS 수집)

### 3. Sector Rotation Strategy (KR vs US)

멀티에이전트 신호로 한국/미국 시장 중 다음 달 베팅 결정.

**핵심 기능**:
- Momentum Agent (40%): 11개 KR+US 섹터 ETF 1M/3M/6M 평균 수익률 비교
- Breadth Agent (30%): MA200 상회 섹터 비율 (KR vs US)
- Relative Strength Agent (30%): KOSPI vs S&P500 1M/3M/6M 상대 수익률
- 월간 리밸런싱, 임계값 ±0.08 (KR/Neutral/US)
- 벤치마크 3개: 50/50 블렌드, KOSPI, S&P500

실행:
```
python -m portfolio.strategy.sector_rotation --date 2026-04-20
```

출력: `output/portfolio/strategy/{date}.html` + `{date}_signals.csv`

## 관련 설정

- `.claude/settings.json`: Market Story 시간 정확성 검증 훅 3개 (PreToolUse WebSearch, PreToolUse Edit, PostToolUse Write)
- `.claude/skills/market-summary/SKILL.md`: Story 작성 규칙·절차 (Story 작업 시 자동 로드)
- `.claude/skills/sector-country/SKILL.md`: 섹터·국가 보고서 작성 규칙 (Tavily 검색 전략, 초보자 언어 변환, 품질 기준)
- `.claude/commands/`: `/market-data`, `/market-deploy`, `/market-full`, `/sector-country`

## 섹터·국가 사이클

`generate_sector_country.py`의 `get_focus(date)` 로 자동 계산. 섹터(11일)·국가(11일) 사이클 모두 **기준일 2026-01-05** 영업일 기준으로 독립 순환.

국가 사이클: KR(1) · US(2) · CN(3) · JP(4) · EU(5) · UK(6) · DE(7) · FR(8) · IN(9) · TW(10) · EM(11)

- 각 국가 차트는 해당 국가의 고유 지수를 표시 (`portfolio/view/country_view.py` `COUNTRIES` dict의 `eq_code` 사용)
- 이전 보고서 링크 레이블: `↩ 이전 보고서` (날짜·타입 불포함)
- `_country_prev_date()`: `get_focus()` 역방향 스캔으로 이전 사이클 날짜 탐색 (idx 산술 불사용)
