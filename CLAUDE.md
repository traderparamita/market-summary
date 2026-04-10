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
history/market_data.csv  # 일별 시계열 (10컬럼 대문자, Snowflake MKT100_MARKET_DAILY 1:1)
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
├── YYYY-MM/
│   ├── YYYY-MM-DD.html          # 일일 보고서 (Data + Story 탭)
│   ├── YYYY-MM-DD_story.html    # 일일 Story 별도 저장
│   └── YYYY-MM-DD_data.json     # 원시 데이터 (gitignore)
├── weekly/
│   ├── YYYY-WNN.html
│   └── YYYY-WNN_story.html
├── monthly/
│   ├── YYYY-MM.html
│   └── YYYY-MM_story.html
└── index.html                   # 전체 인덱스
```

GitHub Pages로 자동 배포 (main 브랜치 push 시 `output/` 폴더)

## 환경

- Python 3.12 (`.venv/` 로컬 venv 권장; gitignore 됨)
- 의존성: yfinance, FinanceDataReader, requests, python-dotenv, investiny, snowflake-connector-python[pandas]
- 환경변수 (`.env` 에서 dotenv 로딩):
  - `ECOS_API_KEY` — 한국은행 ECOS API
  - `SNOWFLAKE_ACCOUNT` / `SNOWFLAKE_USER` / `SNOWFLAKE_PASSWORD` / `SNOWFLAKE_DATABASE` / `SNOWFLAKE_SCHEMA` / `SNOWFLAKE_WAREHOUSE` — Snowflake dual-write

## 주의사항

- HTML 보고서는 Data 탭과 Story 탭 2개로 구성. Story가 없으면 placeholder 유지
- Data 탭의 각 섹션 헤더에 데이터 소스 표시 (src-tag CSS 클래스)
- `history/market_data.csv`: OHLCV 시계열, 10 대문자 컬럼. git 에 커밋됨. 보고서 재현의 단일 소스
- `.gitignore`: `_data.json`, `data/`, `history/market_data.csv.bak_*`, `.venv/` 포함
- investiny 소스가 주말 날짜 데이터를 반환할 수 있음 → 수집 시 자동 필터링
- `generate.py` 의 dual-write 는 `--start` 없이 실행한 일간 수집에만 작동. 전체 재수집은 반드시 `snowflake_loader.py --truncate` 로 별도 벌크 적재

## 관련 설정

- `.claude/settings.json`: Market Story 시간 정확성 검증 훅 3개 (PreToolUse WebSearch, PreToolUse Edit, PostToolUse Write)
- `.claude/skills/market-summary/SKILL.md`: Story 작성 규칙·절차 (Story 작업 시 자동 로드)
- `.claude/commands/`: `/market-data`, `/market-deploy`, `/market-full`
