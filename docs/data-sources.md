# 데이터 소스 & 수집

## 1. 일간 시장 데이터 (`collect_market.py`)

### 수집 대상 (96개 티커 → 90개 지표코드)

`collect_market.py`의 `TICKERS` dict에 86개 yfinance 티커가 선언되어 있고,
`fetch_kr_rates()`로 ECOS에서 KR 금리 5개를 별도 수집하여 일간 수집 대상은 총 91개.
`INDICATOR_CODES` dict에 88개 `(category, ticker) → 지표코드` 매핑이 정의되어 있다.
매핑이 없는 티커(VKOSPI, KR 5Y, KR 30Y)는 보고서에는 표시되지만 CSV/Snowflake 적재에서 스킵된다.

#### Equity (18 티커 → 18 지표)

| 지표코드 | 이름 | yfinance 티커 | 비고 |
|----------|------|---------------|------|
| EQ_KOSPI | KOSPI | ^KS11 | FDR/investiny fallback |
| EQ_KOSDAQ | KOSDAQ | ^KQ11 | FDR fallback |
| EQ_SP500 | S&P500 | ^GSPC | |
| EQ_NASDAQ | NASDAQ | ^IXIC | |
| EQ_RUSSELL2000 | Russell 2000 | ^RUT | |
| EQ_EUROSTOXX50 | Euro Stoxx 50 | ^STOXX50E | investiny fallback (id=175) |
| EQ_DAX | DAX | ^GDAXI | investiny fallback (id=172) |
| EQ_CAC40 | CAC 40 | ^FCHI | investiny fallback (id=167) |
| EQ_FTSE100 | FTSE 100 | ^FTSE | investiny fallback (id=27) |
| EQ_NIKKEI225 | Nikkei 225 | ^N225 | FDR/investiny fallback |
| EQ_SHANGHAI | Shanghai Composite | 000001.SS | FDR/investiny fallback |
| EQ_HSI | Hang Seng | ^HSI | FDR/investiny fallback |
| EQ_NIFTY50 | Nifty 50 | ^NSEI | investiny fallback (id=17940) |
| EQ_TWSE | TWSE | ^TWII | |
| EQ_MSCI_WORLD | MSCI World | URTH (ETF proxy) | |
| EQ_MSCI_ACWI | MSCI ACWI | ACWI (ETF proxy) | |
| EQ_MSCI_LATAM | MSCI LATAM | ILF (ETF proxy) | |
| EQ_MSCI_EMEA | MSCI EMEA | EZA (ETF proxy) | |

#### Bond (11 티커 → 11 지표)

| 지표코드 | 이름 | 소스 | 비고 |
|----------|------|------|------|
| BD_US_2Y | US 2Y Yield | yfinance ^IRX | 13-week proxy |
| BD_US_10Y | US 10Y Yield | yfinance ^TNX | |
| BD_US_30Y | US 30Y Yield | yfinance ^TYX | |
| BD_TLT | 20+Y Treasury ETF | yfinance TLT | |
| BD_AGG | US Aggregate Bond | yfinance AGG | |
| BD_HYG | High Yield | yfinance HYG | |
| BD_LQD | Investment Grade | yfinance LQD | |
| BD_EMB | EM Bond | yfinance EMB | |
| BD_KR_CD91D | KR CD 91일 | ECOS API 817Y002/010502000 | |
| BD_KR_3Y | KR 국고 3Y | ECOS API 817Y002/010200000 | |
| BD_KR_10Y | KR 국고 10Y | ECOS API 817Y002/010200001 | |

추가로 SHY/IEI/TIP는 `TICKERS`에 선언 + `INDICATOR_CODES`에 매핑 있으나, 백필은 `portfolio/collectors/sector_etfs.py`에서 수행.

#### FX (8 티커 → 8 지표)

| 지표코드 | 이름 | yfinance 티커 | 실제 소스 |
|----------|------|---------------|-----------|
| FX_DXY | Dollar Index | DX-Y.NYB | investiny (id=1224074) 우선 |
| FX_USDKRW | USD/KRW | KRW=X | FDR → investiny (id=650) |
| FX_EURUSD | EUR/USD | EURUSD=X | FDR → investiny (id=1) |
| FX_USDJPY | USD/JPY | JPY=X | FDR → investiny (id=3) |
| FX_USDCNY | USD/CNY | CNY=X | FDR → investiny (id=2111) |
| FX_AUDUSD | AUD/USD | AUDUSD=X | investiny (id=5) |
| FX_GBPUSD | GBP/USD | GBPUSD=X | investiny (id=2) |
| FX_USDINR | USD/INR | USDINR=X | yfinance only |

FX/Commodity는 `needs_inv_fix = True` — yfinance 날짜가 1영업일 밀리므로 항상 FDR → investiny 순 보정 시도.

#### Commodity (6 티커 → 6 지표)

| 지표코드 | 이름 | yfinance 티커 | 실제 소스 |
|----------|------|---------------|-----------|
| CM_WTI | WTI Crude Oil | CL=F | investiny (id=8849) 우선 |
| CM_BRENT | Brent Crude Oil | BZ=F | investiny (id=8833) 우선 |
| CM_GOLD | Gold | GC=F | investiny (id=8830) 우선 |
| CM_SILVER | Silver | SI=F | investiny (id=8836) 우선 |
| CM_COPPER | Copper | HG=F | investiny (id=8831) 우선 |
| CM_NATGAS | Natural Gas | NG=F | investiny (id=8862) 우선 |

#### Risk (3 티커 → 2 지표)

| 지표코드 | 이름 | yfinance 티커 | 비고 |
|----------|------|---------------|------|
| RK_VIX | VIX | ^VIX | |
| RK_VIX3M | VIX 3M | ^VIX3M | |
| (없음) | VKOSPI | ^KS11V | INDICATOR_CODES 미포함, 수집 실패 지속 |

#### US Sector ETFs (11 티커 → 11 지표)

| 지표코드 | ETF | 티커 |
|----------|-----|------|
| SC_US_TECH | SPDR Tech | XLK |
| SC_US_FIN | SPDR Financial | XLF |
| SC_US_ENERGY | SPDR Energy | XLE |
| SC_US_HEALTH | SPDR Healthcare | XLV |
| SC_US_INDU | SPDR Industrial | XLI |
| SC_US_DISCR | SPDR Consumer Discretionary | XLY |
| SC_US_STAPLES | SPDR Consumer Staples | XLP |
| SC_US_UTIL | SPDR Utilities | XLU |
| SC_US_MATL | SPDR Materials | XLB |
| SC_US_REIT | SPDR Real Estate | XLRE |
| SC_US_COMM | SPDR Communication | XLC |

#### US Factor/Style ETFs (5 티커 → 5 지표)

| 지표코드 | ETF | 티커 |
|----------|-----|------|
| FA_US_GROWTH | iShares S&P 500 Growth | IVW |
| FA_US_VALUE | iShares S&P 500 Value | IVE |
| FA_US_QUALITY | iShares MSCI USA Quality | QUAL |
| FA_US_MOMENTUM | iShares MSCI USA Momentum | MTUM |
| FA_US_LOWVOL | iShares MSCI USA Min Vol | USMV |

#### KR Sector ETFs (10 티커 → 10 지표)

| 지표코드 | ETF | KRX 티커 |
|----------|-----|----------|
| SC_KR_SEMI | TIGER 반도체 | 277630.KS |
| SC_KR_BATTERY | TIGER 2차전지테마 | 137610.KS |
| SC_KR_BIO | TIGER 헬스케어 | 166400.KS |
| SC_KR_FIN | TIGER 200 금융 | 435420.KS |
| SC_KR_BANK | TIGER 은행 | 261140.KS |
| SC_KR_STEEL | TIGER 200 철강소재 | 494840.KS |
| SC_KR_ENERGY | TIGER 200 에너지화학 | 472170.KS |
| SC_KR_HEALTH | TIGER 의료기기 | 400970.KS |
| SC_KR_CONSTR | TIGER 200 건설 | 139270.KS |
| SC_KR_INDU | TIGER 200 산업재 | 227560.KS |

#### Major Stocks (14 티커 → 14 지표)

| 지표코드 | 종목 | 티커 |
|----------|------|------|
| ST_NVDA | NVIDIA | NVDA |
| ST_AVGO | Broadcom | AVGO |
| ST_GOOGL | Alphabet | GOOGL |
| ST_AMZN | Amazon | AMZN |
| ST_META | META | META |
| ST_AAPL | Apple | AAPL |
| ST_MSFT | Microsoft | MSFT |
| ST_TSLA | Tesla | TSLA |
| ST_TSMC | TSMC | TSM |
| ST_SAMSUNG | Samsung | 005930.KS |
| ST_PLTR | Palantir | PLTR |
| ST_BABA | Alibaba | 9988.HK |
| ST_MEITUAN | Meituan | 3690.HK |
| ST_TENCENT | Tencent | 0700.HK |

### 소스 우선순위 & Fallback 체인

```
yfinance (1차, 배치 다운로드)
  ↓ 데이터 없거나 holiday
FinanceDataReader (FDR_FALLBACK dict에 있는 티커만)
  ↓ 여전히 누락
investiny / investing.com (INVESTINY_FALLBACK dict에 있는 티커만)
```

- FX/Commodity 카테고리는 `needs_inv_fix = True` → yfinance 성공해도 항상 FDR/investiny 재시도
- 한국 금리(KR CD 91D, KR 3Y, KR 10Y)는 yfinance 체인 밖에서 `fetch_kr_rates()` → ECOS API 직접 호출
- 수집 결과의 `SOURCE` 컬럼에 실제 승자 기록: `yfinance` / `FDR` / `investiny` / `ECOS`

### 데이터 흐름 (일간)

```
collect_market.fetch_data()
  ├─ yfinance.download() (96 tickers, batch)
  ├─ FDR fallback (개별)
  ├─ investiny fallback (개별)
  └─ fetch_kr_rates() → ECOS API

generate.py main()
  ├─ fetch_data() → result_dict + history_rows
  ├─ append_to_history(history_rows) → history/market_data.csv (dedup by DATE+INDICATOR_CODE)
  ├─ Snowflake dual-write: upsert_rows() → MKT100_MARKET_DAILY (해당 일자 DELETE+INSERT)
  ├─ build_report_data() → Snowflake에서 읽어 지표 계산 (CSV fallback)
  └─ generate_html() → output/summary/YYYY-MM-DD.html + _data.json
```

---

## 2. 보조 수집기 (`portfolio/collectors/`)

일간 `collect_market.py`와 별도로, 이력 백필·특수 지표용 수집기 4종이 있다.
모두 `history/market_data.csv` (또는 `macro_indicators.csv`)에 append + Snowflake dual-write.

### 2-1. Sector ETFs (`sector_etfs.py`)

- **대상**: US Sector 11 + KR Sector GICS 11 + KR 기타 ETF 16 + US Factor 5 + Bond ETF 3 = **46종**
- **소스**: yfinance (OHLCV)
- **용도**: 2010~현재 장기 이력 백필 (ETF 상장일 이후)
- **적재**: `history/market_data.csv` + Snowflake `MKT100_MARKET_DAILY`
- **실행**: `python -m portfolio.collectors.sector_etfs --start 2010-01-01`

### 2-2. KRX Sectors (`krx_sectors.py`)

- **대상**: KOSPI 200 GICS 섹터 지수 11개 (`IX_KR_` prefix) + 전통 업종 지수 11개 (optional)
- **소스**: pykrx (`stock.get_index_ohlcv_by_date`)
- **용도**: ETF보다 긴 2010~ 이력 확보 (ETF는 2015~2022 상장), sector_country 보고서에서 사용
- **적재**: `history/market_data.csv` + Snowflake `MKT100_MARKET_DAILY`
- **실행**: `python -m portfolio.collectors.krx_sectors --start 2010-01-01 [--traditional]`
- **환경변수**: `KRX_ID`, `KRX_PW` (pykrx 인증)

### 2-3. Valuation (`valuation.py`)

- **대상**: KOSPI PER / PBR / 배당수익률 3개 (`VAL_KR_PER`, `VAL_KR_PBR`, `VAL_KR_DY`)
- **소스**: pykrx (`stock.get_index_fundamental_by_date`, 지수코드 1001=KOSPI)
- **용도**: KR 시장 밸류에이션 수준 판단 (Valuation View)
- **적재**: `history/market_data.csv` + Snowflake `MKT100_MARKET_DAILY`
- **실행**: `python -m portfolio.collectors.valuation --start 2010-01-01`

### 2-4. Macro Indicators (`macro.py`)

- **대상**: 48개 거시지표 (`portfolio/macro_indicators.yaml`에 정의)
- **소스**: FRED API (US/JP/CN/EU/UK/IN/Global) + ECOS API (KR)
- **적재**: `history/macro_indicators.csv` + Snowflake `MKT200_MACRO_DAILY`
- **실행**: `python -m portfolio.collectors.macro --start 2010-01-01`
- **환경변수**: `FRED_API_KEY`, `ECOS_API_KEY`

#### 거시지표 목록 (48개)

| 카테고리 | 지역 | 지표코드 | FRED/ECOS 시리즈 | 주기 |
|----------|------|----------|-------------------|------|
| **Growth** | US | US_GDP_QOQ, US_GDP_YOY | GDP | Q |
| | KR | KR_GDP_QOQ, KR_GDP_YOY | ECOS 200Y104/1400 | Q |
| | JP | JP_GDP_QOQ | NAEXKP01JPQ657S | Q |
| | CN | CN_GDP_YOY | CHNGDPNQDSMEI | Q |
| | EU | EU_GDP_QOQ | NAEXKP01EZQ657S | Q |
| | UK | UK_GDP_QOQ | NAEXKP01GBQ657S | Q |
| | IN | IN_GDP_YOY | INDGDPRQPSMEI | Q |
| **Inflation** | US | US_CPI_YOY, US_CORE_CPI_YOY | CPIAUCSL, CPILFESL | M |
| | US | US_PCE_YOY, US_CORE_PCE_YOY | PCEPI, PCEPILFE | M |
| | KR | KR_CPI_YOY, KR_CORE_CPI_YOY | ECOS 901Y009/0, X0 | M |
| | JP | JP_CPI_YOY | JPNCPIALLMINMEI | M |
| | CN | CN_CPI_YOY | CHNCPIALLMINMEI | M |
| | EU | EU_CPI_YOY | CP0000EZ19M086NEST | M |
| | UK | UK_CPI_YOY | GBRCPIALLMINMEI | M |
| | IN | IN_CPI_YOY | INDCPIALLMINMEI | M |
| **Employment** | US | US_UNEMP_RATE, US_NFP_MOM | UNRATE, PAYEMS | M |
| | US | MACRO_US_JOLTS | JTSJOL | M |
| | KR | KR_UNEMP_RATE | ECOS 901Y027/I61BC | M |
| | JP | JP_UNEMP_RATE | LRUNTTTTJPM156S | M |
| **Sentiment** | US | US_ISM_MFG, US_ISM_SVC | NAPM, NAPMNOI | M |
| | US | MACRO_US_CONSUMER_SENT | UMCSENT | M |
| **Policy** | US | US_FED_RATE | FEDFUNDS | M |
| | US | US_10Y_YIELD, US_2Y_YIELD | DGS10, DGS2 | D |
| | US | US_YIELD_CURVE | T10Y2Y | D |
| | KR | KR_BASE_RATE | ECOS 722Y001/0101000 | D |
| | JP | JP_POLICY_RATE | IRSTCI01JPM156N | M |
| | EU | EU_POLICY_RATE | ECBDFR | M |
| **Credit** | US | US_IG_SPREAD, US_HY_SPREAD | BAMLC0A0CM, BAMLH0A0HYM2 | D |
| | US | CREDIT_TED_SPREAD | TEDRATE | D |
| **Rates** | US | BOND_REAL_YIELD_10Y | DFII10 | D |
| | US | BOND_TERM_PREMIUM | ACMTP10 | D |
| | US | BOND_BREAKEVEN_10Y | T10YIE | D |
| **Volatility** | US | BOND_MOVE_INDEX | MOVE | D |
| **Activity** | US | MACRO_US_INDPRO | INDPRO | M |
| | US | MACRO_US_RETAIL_SALES | RSXFS | M |
| **Liquidity** | US | US_M2_YOY | M2SL | M |
| | US | US_FED_BALANCE | WALCL | M |
| **Risk** | GLOBAL | VIX | VIXCLS | D |
| **FX** | GLOBAL | DXY | DTWEXBGS | D |

---

## 3. 증권사 보고서 (`scripts/collect_securities_reports.py`)

- **대상**: 미래에셋증권 상세분석 게시판 (categoryId=1521) PDF 보고서
- **소스**: `https://securities.miraeasset.com/bbs/board/message/list.do` (requests + BeautifulSoup 스크래핑)
- **적재**: S3 `s3://mai-life-fund-documents-.../anthillia/miraeasset-securities/YYYY-MM/`
- **스케줄**: 매주 일요일 19:30 KST (launchd), 직전 영업주(월~금) 보고서 수집
- **중복 방지**: S3 기존 키 조회 → attachmentId 기반 스킵
- **실행**: `.venv/bin/python scripts/collect_securities_reports.py [--week-of YYYY-MM-DD] [--dry-run]`

---

## 4. CSV 스키마

### `history/market_data.csv` (약 30만 행)

```
DATE, INDICATOR_CODE, CATEGORY, TICKER, CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE
```

- **Dedup 키**: `(DATE, INDICATOR_CODE)`
- **CATEGORY**: equity / bond / fx / commodity / risk / sector_us / sector_kr / style_us / stocks / index_kr / valuation
- **SOURCE**: `yfinance` / `FDR` / `investiny` / `ECOS` / `pykrx`
- KR bond 행: OHLCV 중 CLOSE만 있고 나머지 NULL (ECOS는 금리만 반환)
- FX/risk 행: VOLUME은 NULL (시장 특성)

### `history/macro_indicators.csv` (약 5.6만 행)

```
DATE, INDICATOR_CODE, CATEGORY, REGION, VALUE, UNIT, SOURCE
```

- **Dedup 키**: `(DATE, INDICATOR_CODE)`
- **REGION**: US / KR / JP / CN / EU / UK / IN / GLOBAL
- **SOURCE**: `FRED` / `ECOS`
- 분기 데이터는 분기말 날짜로 저장, 월간 데이터는 해당월 1일로 저장

---

## 5. Snowflake 연동

### 테이블 구조

| 테이블 | 용도 | CSV 대응 |
|--------|------|----------|
| `FDE_DB.PUBLIC.MKT100_MARKET_DAILY` | 시장 데이터 (단일 정본) | `market_data.csv` |
| `FDE_DB.PUBLIC.MKT200_MACRO_DAILY` | 거시지표 | `macro_indicators.csv` |
| `FDE_DB.PUBLIC.MKT001_MACRO_INDICATOR` | 거시지표 마스터 (주기/소스_시리즈 lookup) | — |

### 컬럼 매핑 (MKT100)

```
CSV (English)    →  Snowflake (한글)
DATE             →  일자
INDICATOR_CODE   →  지표코드
CATEGORY         →  카테고리
TICKER           →  티커
CLOSE            →  종가        (NUMBER 18,3)
OPEN             →  시가        (NUMBER 18,3)
HIGH             →  고가        (NUMBER 18,3)
LOW              →  저가        (NUMBER 18,3)
VOLUME           →  거래량
SOURCE           →  소스
```

### 적재 패턴

| 상황 | 방법 | 모듈 |
|------|------|------|
| 일간 수집 후 | 해당 일자 DELETE + INSERT (dual-write) | `generate.py` → `snowflake_loader.upsert_rows()` |
| 전체 재적재 | TRUNCATE + bulk INSERT | `python snowflake_loader.py --truncate` |
| 보조 수집기 | 동일 upsert (best-effort, 실패 시 Telegram 알림) | `snowflake_loader.sync_new_rows()` |
| 매크로 지표 | (일자, 지표코드) DELETE + INSERT | `snowflake_loader.sync_macro_rows()` |

### Reader 패턴

모든 소비자는 `portfolio.market_source` 경유:

```python
from portfolio.market_source import load_long, load_wide_close, load_macro_long

load_long(start, end, codes)        # Long format (MKT100 → CSV fallback)
load_wide_close(start, end, codes)  # DATE × INDICATOR_CODE pivot
load_macro_long(start, end, codes)  # MKT200 → macro_indicators.csv fallback
```

- `prefer="snowflake"` (기본): Snowflake 우선, 실패 시 CSV fallback
- `prefer="csv"`: CSV 강제 (시뮬레이션/테스트)
- `SNOWFLAKE_DISABLE=1`: 전역 CSV fallback

---

## 6. 외부 API 요약

| API | 용도 | 인증 | 환경변수 |
|-----|------|------|----------|
| yfinance | 주식/ETF/지수/채권/FX/원자재 OHLCV | 불필요 (Yahoo Finance 무료) | — |
| FinanceDataReader | 한국 주식/지수, FX fallback | 불필요 | — |
| investiny | investing.com 스크래핑 fallback | 불필요 | — |
| ECOS (한국은행) | KR 금리, KR 거시지표 | API 키 | `ECOS_API_KEY` |
| FRED (미 연준) | US/글로벌 거시지표 | API 키 | `FRED_API_KEY` |
| pykrx (KRX) | KOSPI 200 섹터 지수, 밸류에이션 | KRX 계정 | `KRX_ID`, `KRX_PW` |
| Snowflake | 데이터 정본 저장소 | 계정 | `SNOWFLAKE_*` (6개) |
| AWS S3 | 펀드/증권 보고서 저장 | IAM 키 | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| Telegram | 수집 완료/실패 알림 | Bot 토큰 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| 미래에셋증권 BBS | 상세분석 PDF 스크래핑 | 불필요 | — |
