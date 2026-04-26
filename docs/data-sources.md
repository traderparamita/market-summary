# 데이터 소스 & 수집

## 수집 대상 (56개 지표)

MKT000_MARKET_INDICATOR 와 1:1 매핑.

- **Equity** (17): KOSPI, KOSDAQ, S&P500, NASDAQ, Russell2K, STOXX50, DAX, CAC40, FTSE100, Nikkei225, Shanghai, HSI, NIFTY50, MSCI World/ACWI/LATAM/EMEA
- **Bond** (11): US 2Y/10Y/30Y, TLT, AGG, HYG, LQD, EMB, KR CD91D/3Y/10Y
- **FX** (7): DXY, USD/KRW, EUR/USD, USD/JPY, USD/CNY, AUD/USD, GBP/USD
- **Commodity** (6): WTI, Brent, Gold, Silver, Copper, Nat Gas
- **Risk** (1): VIX (VKOSPI 는 TICKERS 에 선언만 있고 수집 실패 지속 — INDICATOR_CODES 미포함)
- **Stocks** (14): NVIDIA, Broadcom, Alphabet, Amazon, META, Apple, Microsoft, Tesla, TSMC, Samsung, Palantir, Alibaba, Meituan, Tencent

## 소스 우선순위

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
- investiny 소스가 주말 날짜 데이터를 반환할 수 있음 → 수집 시 자동 필터링

## CSV 스키마

`history/market_data.csv` — 영문 대문자 10컬럼, Snowflake MKT100_MARKET_DAILY 와 정렬:

```
DATE, INDICATOR_CODE, CATEGORY, TICKER, CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE
```

- `INDICATOR_CODE`: `collect_market.py` 상단 `INDICATOR_CODES` dict 로 `(category, ticker) → 지표코드` 매핑
- `SOURCE`: 실제 수집 승자 (`yfinance` / `investiny` / `FDR` / `ECOS`)
- KR bond 행은 OHLCV 전부 NULL (ECOS 는 금리만)
- FX/risk 행은 VOLUME NULL (시장 특성)

`history/macro_indicators.csv` — 7컬럼:

```
DATE, INDICATOR_CODE, CATEGORY, REGION, VALUE, UNIT, SOURCE
```

## Snowflake 연동

- **MKT100_MARKET_DAILY 가 단일 정본** (2026-04-21 전환)
- `history/market_data.csv` 는 legacy mirror + simulate.py 용 fallback (`SNOWFLAKE_DISABLE=1` 로 강제 전환)
- 모든 reader 는 `portfolio.market_source.load_long()` / `load_wide_close()` / `load_macro_long()` 경유
- `generate.py main()` 이 CSV append 직후 dual-write (해당 일자 DELETE + INSERT, best-effort)
- dual-write 는 `--start` 없이 실행한 일간 수집에만 작동
- 전체 재수집은 `python snowflake_loader.py --truncate` 로 CSV 통째로 벌크 적재

## 거시지표 (Macro View)

수집 완료 지표 (2020~):

- US (16): GDP QoQ/YoY, CPI/Core CPI/PCE/Core PCE YoY, 실업률, NFP, 연준금리, 10Y/2Y 국채, Yield Curve, IG/HY Spread, M2 YoY, Fed Balance Sheet YoY
- KR (5): GDP QoQ/YoY, CPI YoY, 실업률, 기준금리
- Global (2): VIX, DXY

미구현:
- `KR_CORE_CPI_YOY` — ECOS item_code X0 확인 필요
- `KR_MFG_BSI` — ECOS 다층 item_code 미구현
- `US_ISM_MFG/SVC` — FRED series_id 오류, 교체 필요
