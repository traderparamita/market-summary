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
generate.py          # 핵심 엔진 - 데이터 수집 + HTML 보고서 생성 + Snowflake dual-write
generate_periodic.py # 주간/월간 집계 보고서 생성
snowflake_loader.py  # CSV ↔ Snowflake MKT100_MARKET_DAILY 적재 유틸 (bulk / upsert)
simulate.py          # 과거 날짜 시뮬레이션
inject_stories.py    # 시뮬레이션 보고서에 Story 주입
gen_assets.py        # favicon 등 assets 생성
history/market_data.csv       # 일별 시계열 (10컬럼 대문자, Snowflake MKT100_MARKET_DAILY 1:1)
history/macro_indicators.csv  # 거시지표 시계열 (7컬럼 대문자)

portfolio/
├── aimvp/           # Portfolio Agent (AIMVP RiskOn 전략)
│   ├── generate.py      # 백테스트 HTML 생성
│   ├── backfill.py      # 장기 히스토리 백필 (2010~)
│   ├── signals.py       # TAA 신호 계산
│   ├── model.py         # 가중치 모델
│   ├── config.py        # 전략 파라미터
│   └── data_adapter.py  # CSV → 월간 데이터
├── view/            # View Agent (확장 가능한 분석 뷰)
│   ├── price_view.py       # 가격 기반 시장 신호 뷰 (모멘텀, 추세, VIX, 폭, Sentiment)
│   ├── macro_view.py       # 거시지표 뷰 (GDP, 인플레이션, 고용 등, Regime 헤더)
│   ├── correlation_view.py # 자산 상관관계 히트맵 뷰 (30/60/90일 롤링)
│   ├── regime_view.py      # 종합 국면 뷰 (규칙 기반 한국어 투자 해설)
│   └── scoring.py          # 자산 점수 계산 (sentiment_score, regime_duration 포함)
├── collect_macro.py     # 거시지표 수집 (FRED/ECOS)
├── macro_indicators.yaml # 거시지표 정의
├── backtest.py      # 공통 백테스트 엔진
├── universe.yaml    # 자산 유니버스
└── strategies/      # 전략 YAML
```

**CSV 스키마** (영문 대문자, Snowflake MKT100_MARKET_DAILY 와 정렬):
```
DATE, INDICATOR_CODE, CATEGORY, TICKER, CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE
```

- `INDICATOR_CODE`: MKT000_MARKET_INDICATOR 의 `지표코드` (EQ_KOSPI, BD_US_10Y, ...). `generate.py` 상단 `INDICATOR_CODES` dict 로 `(category, ticker) → 지표코드` 매핑.
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
- 모든 Data Dashboard: `history/market_data.csv`가 단일 소스 (Single Source of Truth)
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
├── portfolio/                   # Portfolio Agent
│   └── aimvp/
│       └── YYYY-MM-DD.html     # 백테스트 리포트
└── view/                        # View Agent
    ├── price/
    │   └── YYYY-MM-DD.html     # 가격 기반 시장 신호 뷰
    ├── macro/
    │   └── YYYY-MM-DD.html     # 거시지표 뷰
    ├── correlation/
    │   └── YYYY-MM-DD.html     # 자산 상관관계 히트맵
    └── regime/
        └── YYYY-MM-DD.html     # 종합 국면 + 투자 해설
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
- `history/market_data.csv`: OHLCV 시계열, 10 대문자 컬럼. git 에 커밋됨. 보고서 재현의 단일 소스
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

**구조적 확장 가능**:
- `view/country_view.py` - 국가별 비교 (Phase 2)
- `view/sector_view.py` - 섹터 로테이션 (Phase 3)

### 공통

- `portfolio/backtest.py`: 정적/동적 전략 백테스트 엔진
- `portfolio/universe.yaml`: 자산 유니버스 정의
- `portfolio/strategies/`: 전략 YAML 설정

- Portfolio Agent / Price View: `history/market_data.csv` 단일 소스
- Macro View: `history/macro_indicators.csv` (FRED + ECOS 수집)

## 관련 설정

- `.claude/settings.json`: Market Story 시간 정확성 검증 훅 3개 (PreToolUse WebSearch, PreToolUse Edit, PostToolUse Write)
- `.claude/skills/market-summary/SKILL.md`: Story 작성 규칙·절차 (Story 작업 시 자동 로드)
- `.claude/commands/`: `/market-data`, `/market-deploy`, `/market-full`
