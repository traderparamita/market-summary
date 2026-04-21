"""
Daily market data collector.

Extracted from generate.py: all data-collection logic lives here.
generate.py imports from this module for HTML report generation.
simulate.py patches HISTORY_CSV on this module, not generate.py.

Public API:
    fetch_data(start_date, end_date)    -> (result_dict, history_rows)
    fetch_kr_rates(start_date, end_date) -> (kr_rates_dict, history_rows)
    calc_metrics(df, ref_date)          -> metrics_dict | None
    append_to_history(history_rows)
    build_report_data(target_date)      -> result_dict
    HISTORY_CSV                         (patchable by simulate.py)
    HISTORY_CSV_COLUMNS
"""

import csv as _csv
import datetime as dt
import math
import os

import FinanceDataReader as fdr
import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

try:
    from investiny import historical_data as inv_historical
    HAS_INVESTINY = True
except ImportError:
    HAS_INVESTINY = False

# ── Paths ────────────────────────────────────────────────────────
HISTORY_DIR = os.path.join(os.path.dirname(__file__), "history")
HISTORY_CSV = os.path.join(HISTORY_DIR, "market_data.csv")

# CSV 스키마 (Snowflake MKT100_MARKET_DAILY 1:1)
HISTORY_CSV_COLUMNS = [
    "DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
    "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE",
]

# ── Fallback tables ──────────────────────────────────────────────
# yfinance 지수 데이터 누락 시 FinanceDataReader로 보완
FDR_FALLBACK = {
    "^KS11":  "KS11",    # KOSPI
    "^KQ11":  "KQ11",    # KOSDAQ
    "^N225":  "N225",    # Nikkei225
    "^HSI":   "HSI",     # Hang Seng
    "000001.SS": "SSEC", # Shanghai
    # FX: yfinance =X 티커는 날짜가 1영업일 밀리므로 FDR로 보정
    "KRW=X":    "USD/KRW",
    "EURUSD=X": "EUR/USD",
    "JPY=X":    "USD/JPY",
    "CNY=X":    "USD/CNY",
}

# yfinance + FDR 모두 실패 시 investiny(investing.com) fallback
# key: yfinance ticker, value: investing.com ID
INVESTINY_FALLBACK = {
    "^STOXX50E": 175,    # Euro Stoxx 50
    "^GDAXI":    172,    # DAX
    "^FCHI":     167,    # CAC 40
    "^FTSE":      27,    # FTSE 100
    "^N225":     178,    # Nikkei 225
    "^HSI":      179,    # Hang Seng
    "000001.SS": 40820,  # Shanghai Composite
    "^NSEI":     17940,  # Nifty 50
    # FX: yfinance =X 티커 날짜가 1영업일 밀리므로 investiny로 보정
    "DX-Y.NYB":  1224074, # DXY (US Dollar Index)
    "KRW=X":     650,     # USD/KRW
    "EURUSD=X":  1,       # EUR/USD
    "JPY=X":     3,       # USD/JPY
    "CNY=X":     2111,    # USD/CNY
    "AUDUSD=X":  5,       # AUD/USD
    "GBPUSD=X":  2,       # GBP/USD
    # Commodity: yfinance =F 선물 데이터 보정
    "CL=F":      8849,    # WTI Crude Oil
    "BZ=F":      8833,    # Brent Crude Oil
    "GC=F":      8830,    # Gold
    "SI=F":      8836,    # Silver
    "HG=F":      8831,    # Copper
    "NG=F":      8862,    # Natural Gas
}

# ── Ticker universe ──────────────────────────────────────────────
TICKERS = {
    # Equity indices
    "equity": {
        "KOSPI":    "^KS11",
        "KOSDAQ":   "^KQ11",
        "S&P500":   "^GSPC",
        "NASDAQ":   "^IXIC",
        "Russell2K": "^RUT",
        "STOXX50":  "^STOXX50E",
        "DAX":      "^GDAXI",
        "CAC40":    "^FCHI",
        "FTSE100":  "^FTSE",
        "Nikkei225":"^N225",
        "Shanghai": "000001.SS",
        "HSI":      "^HSI",
        "NIFTY50":  "^NSEI",
        "TWSE":     "^TWII",  # 대만 가권지수
        # MSCI ETF proxies
        "MSCI World": "URTH",  # iShares MSCI World ETF
        "MSCI ACWI":  "ACWI",  # iShares MSCI ACWI ETF
        "MSCI LATAM": "ILF",   # iShares Latin America 40 ETF
        "MSCI EMEA":  "EZA",   # iShares South Africa ETF (EMEA proxy)
    },
    # Bonds (yield proxies via ETFs + treasury rates)
    "bond": {
        "US 2Y":    "^IRX",   # 13-week proxy; 실제는 아래 별도 처리
        "US 10Y":   "^TNX",
        "US 30Y":   "^TYX",
        "TLT":      "TLT",    # 20+Y Treasury ETF
        "AGG":      "AGG",    # US Aggregate Bond ETF
        "HYG":      "HYG",    # High Yield
        "LQD":      "LQD",    # Investment Grade
        "EMB":      "EMB",    # EM Bond
        "SHY":      "SHY",    # 1-3Y Treasury
        "IEI":      "IEI",    # 3-7Y Treasury
        "TIP":      "TIP",    # TIPS (inflation-linked)
    },
    # FX
    "fx": {
        "DXY":      "DX-Y.NYB",
        "USD/KRW":  "KRW=X",
        "EUR/USD":  "EURUSD=X",
        "USD/JPY":  "JPY=X",
        "USD/CNY":  "CNY=X",
        "AUD/USD":  "AUDUSD=X",
        "GBP/USD":  "GBPUSD=X",
        "USD/INR":  "USDINR=X",
    },
    # Commodities
    "commodity": {
        "WTI":      "CL=F",
        "Brent":    "BZ=F",
        "Gold":     "GC=F",
        "Silver":   "SI=F",
        "Copper":   "HG=F",
        "Nat Gas":  "NG=F",
    },
    # Volatility / Risk
    "risk": {
        "VIX":      "^VIX",
        "VKOSPI":   "^KS11V",  # fallback 처리 필요
        "VIX3M":    "^VIX3M",  # 3-month VIX (term structure)
    },
    # US Sector ETFs (SPDR 11개)
    "sector_us": {
        "SPDR Tech":      "XLK",
        "SPDR Fin":       "XLF",
        "SPDR Energy":    "XLE",
        "SPDR Health":    "XLV",
        "SPDR Indu":      "XLI",
        "SPDR ConsDiscr": "XLY",
        "SPDR ConsStap":  "XLP",
        "SPDR Util":      "XLU",
        "SPDR Matl":      "XLB",
        "SPDR REIT":      "XLRE",
        "SPDR Comm":      "XLC",
    },
    # US Factor / Style ETFs
    "style_us": {
        "iShares Growth":   "IVW",
        "iShares Value":    "IVE",
        "iShares Quality":  "QUAL",
        "iShares Momentum": "MTUM",
        "iShares LowVol":   "USMV",
    },
    # KR Sector ETFs (TIGER, 미래에셋자산운용)
    "sector_kr": {
        "TIGER Semi":    "277630.KS",   # TIGER 반도체       → SC_KR_SEMI
        "TIGER Battery": "137610.KS",   # TIGER 2차전지테마  → SC_KR_BATTERY
        "TIGER Health":  "166400.KS",   # TIGER 헬스케어     → SC_KR_BIO
        "TIGER Fin":     "435420.KS",   # TIGER 200 금융     → SC_KR_FIN
        "TIGER Bank":    "261140.KS",   # TIGER 은행         → SC_KR_BANK
        "TIGER Steel":   "494840.KS",   # TIGER 200 철강소재 → SC_KR_STEEL
        "TIGER Energy":  "472170.KS",   # TIGER 200 에너지화학→ SC_KR_ENERGY
        "TIGER Medtech": "400970.KS",   # TIGER 의료기기     → SC_KR_HEALTH
        "TIGER Constr":  "139270.KS",   # TIGER 200 건설     → SC_KR_CONSTR
        "TIGER Indu":    "227560.KS",   # TIGER 200 산업재   → SC_KR_INDU
    },
    # Major stocks
    "stocks": {
        "NVIDIA":   "NVDA",
        "Broadcom": "AVGO",
        "Alphabet": "GOOGL",
        "Amazon":   "AMZN",
        "META":     "META",
        "Apple":    "AAPL",
        "Microsoft":"MSFT",
        "Tesla":    "TSLA",
        "TSMC":     "TSM",
        "Samsung":  "005930.KS",
        "Palantir": "PLTR",
        "Alibaba":  "9988.HK",
        "Meituan":  "3690.HK",
        "Tencent":  "0700.HK",
    },
}

# (category, ticker) -> Snowflake MKT000_MARKET_INDICATOR.지표코드
# 56개 지표. TICKERS/fetch_kr_rates에 추가되는 항목은 여기도 함께 업데이트.
# 누락된 (cat, ticker)는 lookup이 None 이 되어 CSV에 빈 값으로 기록되고
# Snowflake 적재에서 스킵된다 (ex. VKOSPI는 TICKERS에 있으나 MKT000에 없음).
INDICATOR_CODES = {
    ("equity", "KOSPI"):     "EQ_KOSPI",
    ("equity", "KOSDAQ"):    "EQ_KOSDAQ",
    ("equity", "S&P500"):    "EQ_SP500",
    ("equity", "NASDAQ"):    "EQ_NASDAQ",
    ("equity", "Russell2K"): "EQ_RUSSELL2000",
    ("equity", "STOXX50"):   "EQ_EUROSTOXX50",
    ("equity", "DAX"):       "EQ_DAX",
    ("equity", "CAC40"):     "EQ_CAC40",
    ("equity", "FTSE100"):   "EQ_FTSE100",
    ("equity", "Nikkei225"): "EQ_NIKKEI225",
    ("equity", "Shanghai"):  "EQ_SHANGHAI",
    ("equity", "HSI"):       "EQ_HSI",
    ("equity", "NIFTY50"):   "EQ_NIFTY50",
    ("equity", "TWSE"):      "EQ_TWSE",
    ("equity", "MSCI World"): "EQ_MSCI_WORLD",
    ("equity", "MSCI ACWI"):  "EQ_MSCI_ACWI",
    ("equity", "MSCI LATAM"): "EQ_MSCI_LATAM",
    ("equity", "MSCI EMEA"):  "EQ_MSCI_EMEA",
    ("bond", "US 2Y"):  "BD_US_2Y",
    ("bond", "US 10Y"): "BD_US_10Y",
    ("bond", "US 30Y"): "BD_US_30Y",
    ("bond", "TLT"):    "BD_TLT",
    ("bond", "AGG"):    "BD_AGG",
    ("bond", "HYG"):    "BD_HYG",
    ("bond", "LQD"):    "BD_LQD",
    ("bond", "EMB"):    "BD_EMB",
    ("bond", "SHY"):    "BD_US_1_3Y",
    ("bond", "IEI"):    "BD_US_3_7Y",
    ("bond", "TIP"):    "BD_US_TIPS",
    ("bond", "KR CD 91D"): "BD_KR_CD91D",
    ("bond", "KR 3Y"):     "BD_KR_3Y",
    ("bond", "KR 10Y"):    "BD_KR_10Y",
    ("fx", "DXY"):     "FX_DXY",
    ("fx", "USD/KRW"): "FX_USDKRW",
    ("fx", "EUR/USD"): "FX_EURUSD",
    ("fx", "USD/JPY"): "FX_USDJPY",
    ("fx", "USD/CNY"): "FX_USDCNY",
    ("fx", "AUD/USD"): "FX_AUDUSD",
    ("fx", "GBP/USD"): "FX_GBPUSD",
    ("fx", "USD/INR"): "FX_USDINR",
    ("commodity", "WTI"):     "CM_WTI",
    ("commodity", "Brent"):   "CM_BRENT",
    ("commodity", "Gold"):    "CM_GOLD",
    ("commodity", "Silver"):  "CM_SILVER",
    ("commodity", "Copper"):  "CM_COPPER",
    ("commodity", "Nat Gas"): "CM_NATGAS",
    ("risk", "VIX"):   "RK_VIX",
    ("risk", "VIX3M"): "RK_VIX3M",
    # US Sector ETFs
    ("sector_us", "SPDR Tech"):      "SC_US_TECH",
    ("sector_us", "SPDR Fin"):       "SC_US_FIN",
    ("sector_us", "SPDR Energy"):    "SC_US_ENERGY",
    ("sector_us", "SPDR Health"):    "SC_US_HEALTH",
    ("sector_us", "SPDR Indu"):      "SC_US_INDU",
    ("sector_us", "SPDR ConsDiscr"): "SC_US_DISCR",
    ("sector_us", "SPDR ConsStap"):  "SC_US_STAPLES",
    ("sector_us", "SPDR Util"):      "SC_US_UTIL",
    ("sector_us", "SPDR Matl"):      "SC_US_MATL",
    ("sector_us", "SPDR REIT"):      "SC_US_REIT",
    ("sector_us", "SPDR Comm"):      "SC_US_COMM",
    # US Style / Factor ETFs
    ("style_us", "iShares Growth"):   "FA_US_GROWTH",
    ("style_us", "iShares Value"):    "FA_US_VALUE",
    ("style_us", "iShares Quality"):  "FA_US_QUALITY",
    ("style_us", "iShares Momentum"): "FA_US_MOMENTUM",
    ("style_us", "iShares LowVol"):   "FA_US_LOWVOL",
    # KR Sector ETFs (TIGER)
    ("sector_kr", "TIGER Semi"):    "SC_KR_SEMI",
    ("sector_kr", "TIGER Battery"): "SC_KR_BATTERY",
    ("sector_kr", "TIGER Health"):  "SC_KR_BIO",
    ("sector_kr", "TIGER Fin"):     "SC_KR_FIN",
    ("sector_kr", "TIGER Bank"):    "SC_KR_BANK",
    ("sector_kr", "TIGER Steel"):   "SC_KR_STEEL",
    ("sector_kr", "TIGER Energy"):  "SC_KR_ENERGY",
    ("sector_kr", "TIGER Medtech"): "SC_KR_HEALTH",
    ("sector_kr", "TIGER Constr"):  "SC_KR_CONSTR",
    ("sector_kr", "TIGER Indu"):    "SC_KR_INDU",
    ("stocks", "NVIDIA"):    "ST_NVDA",
    ("stocks", "Broadcom"):  "ST_AVGO",
    ("stocks", "Alphabet"):  "ST_GOOGL",
    ("stocks", "Amazon"):    "ST_AMZN",
    ("stocks", "META"):      "ST_META",
    ("stocks", "Apple"):     "ST_AAPL",
    ("stocks", "Microsoft"): "ST_MSFT",
    ("stocks", "Tesla"):     "ST_TSLA",
    ("stocks", "TSMC"):      "ST_TSMC",
    ("stocks", "Samsung"):   "ST_SAMSUNG",
    ("stocks", "Palantir"):  "ST_PLTR",
    ("stocks", "Alibaba"):   "ST_BABA",
    ("stocks", "Meituan"):   "ST_MEITUAN",
    ("stocks", "Tencent"):   "ST_TENCENT",
}


# ── Core functions ───────────────────────────────────────────────

def calc_metrics(df, ref_date):
    """DataFrame(index=date, columns=[Close])에서 지표 계산."""
    df = df.dropna(subset=["Close"])
    if df.empty:
        return None

    last_date = df.index[-1].date() if hasattr(df.index[-1], 'date') else df.index[-1]
    close = float(df.iloc[-1]["Close"])

    is_holiday = last_date < ref_date

    daily_chg = 0.0
    if not is_holiday and len(df) >= 2:
        prev = float(df.iloc[-2]["Close"])
        daily_chg = (close - prev) / prev * 100 if prev else 0

    weekly_chg = 0.0
    if len(df) >= 6:
        w = float(df.iloc[-6]["Close"])
        weekly_chg = (close - w) / w * 100 if w else 0

    monthly_chg = 0.0
    if len(df) >= 23:
        m = float(df.iloc[-23]["Close"])
        monthly_chg = (close - m) / m * 100 if m else 0

    ytd_chg = 0.0
    yr_start = df[df.index.year == ref_date.year]
    if not yr_start.empty:
        y = float(yr_start.iloc[0]["Close"])
        ytd_chg = (close - y) / y * 100 if y else 0

    spark = []
    tail = df.tail(20)
    if not tail.empty:
        first_val = float(tail.iloc[0]["Close"])
        spark = [round((float(r["Close"]) / first_val - 1) * 100, 2) for _, r in tail.iterrows()]

    return {
        "close": close,
        "date": str(last_date),
        "daily": round(daily_chg, 2),
        "weekly": round(weekly_chg, 2),
        "monthly": round(monthly_chg, 2),
        "ytd": round(ytd_chg, 2),
        "spark": spark,
        "holiday": is_holiday,
        "holiday_note": "" if not is_holiday else "Holiday",
    }


def fetch_data(start_date=None, end_date=None):
    """yfinance 로 전체 데이터 수집.

    Args:
        start_date: 'YYYY-MM-DD' 수집 시작일. None 이면 end_date - 200일.
        end_date:   'YYYY-MM-DD' 수집 종료일. None 이면 오늘.

    Returns:
        (result_dict, history_rows)
        history_rows: list of 10-tuples
            (date, indicator_code, category, ticker, close, open, high, low, volume, source)
    """
    all_tickers = {}
    for cat, items in TICKERS.items():
        for name, ticker in items.items():
            all_tickers[f"{cat}|{name}"] = ticker

    # --- 기간 결정 ---
    today = dt.date.today()
    target = dt.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    if start_date:
        # 명시적 재수집
        range_start = dt.datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        # Dynamic lookback: CSV 최신일 - 3일 (안전 마진).
        # CSV 가 없거나 읽기 실패 시 target - 10일 fallback.
        range_start = None
        if os.path.exists(HISTORY_CSV):
            try:
                import pandas as _pd
                _df = _pd.read_csv(HISTORY_CSV, usecols=["DATE"])
                if len(_df):
                    _max = _pd.to_datetime(_df["DATE"]).max().date()
                    anchor = min(_max, target)
                    range_start = anchor - dt.timedelta(days=3)
            except Exception as _e:
                print(f"  [WARN] CSV lookback detect 실패 → fallback: {_e}")
        if range_start is None:
            range_start = target - dt.timedelta(days=10)

    # yfinance end 는 exclusive 이므로 +1
    yf_start = range_start.strftime("%Y-%m-%d")
    yf_end = (target + dt.timedelta(days=1)).strftime("%Y-%m-%d")

    symbols = list(all_tickers.values())
    print(f"Fetching {len(symbols)} tickers ({yf_start} ~ {target})...")
    raw = yf.download(
        symbols, start=yf_start, end=yf_end,
        interval="1d", group_by="ticker", threads=True,
    )

    result = {}
    history_rows = []

    def _num(row, *names):
        for n in names:
            if n in row.index:
                v = row[n]
                try:
                    f = float(v)
                    if math.isnan(f):
                        continue
                    return f
                except (TypeError, ValueError):
                    continue
        return None

    def _emit_rows(used_df, cat, name, source):
        """used_df 의 전 행을 history_rows 로 push (주말 제외, range_start 이상만)."""
        indicator_code = INDICATOR_CODES.get((cat, name))
        if indicator_code is None:
            return
        for idx, row in used_df.iterrows():
            d = idx.date() if hasattr(idx, "date") else idx
            if d.weekday() >= 5:
                continue
            if d < range_start or d > target:
                continue
            close_val = _num(row, "Close", "close")
            if close_val is None:
                continue
            open_val = _num(row, "Open", "open")
            high_val = _num(row, "High", "high")
            low_val = _num(row, "Low", "low")
            vol_val = _num(row, "Volume", "volume")
            history_rows.append((
                str(d), indicator_code, cat, name,
                close_val, open_val, high_val, low_val, vol_val, source,
            ))

    for key, ticker in all_tickers.items():
        cat, name = key.split("|")
        try:
            if len(symbols) == 1:
                df = raw
            else:
                df = raw[ticker] if ticker in raw.columns.get_level_values(0) else None

            metrics = None
            used_df = None
            used_source = None
            if df is not None and not df.empty:
                df = df.dropna(subset=["Close"])
                if not df.empty:
                    metrics = calc_metrics(df, target)
                    used_df = df
                    used_source = "yfinance"

            # FX/Commodity 는 yfinance 데이터 부정확 → 항상 FDR/investiny 로 재시도
            needs_inv_fix = cat in ("fx", "commodity")

            # Fallback 1: FDR
            if (metrics is None or metrics["holiday"] or needs_inv_fix) and ticker in FDR_FALLBACK:
                fdr_code = FDR_FALLBACK[ticker]
                try:
                    fdr_start = (range_start - dt.timedelta(days=3)).strftime("%Y-%m-%d")
                    fdr_end = (target + dt.timedelta(days=1)).strftime("%Y-%m-%d")
                    fdr_df = fdr.DataReader(fdr_code, fdr_start, fdr_end)
                    if not fdr_df.empty:
                        fdr_metrics = calc_metrics(fdr_df, target)
                        if fdr_metrics and not fdr_metrics["holiday"]:
                            metrics = fdr_metrics
                            used_df = fdr_df
                            used_source = "FDR"
                            print(f"  [FDR] {name}: {fdr_metrics['close']:.2f} ({fdr_metrics['daily']:+.2f}%) via {fdr_code}")
                except Exception as fe:
                    print(f"  [FDR WARN] {name}: {fe}")

            # Fallback 2: investiny
            if (metrics is None or metrics["holiday"] or needs_inv_fix) and HAS_INVESTINY and ticker in INVESTINY_FALLBACK:
                inv_id = INVESTINY_FALLBACK[ticker]
                try:
                    import pandas as pd
                    inv_start = (range_start - dt.timedelta(days=3)).strftime("%m/%d/%Y")
                    inv_end = (target + dt.timedelta(days=1)).strftime("%m/%d/%Y")
                    inv_data = inv_historical(investing_id=inv_id, from_date=inv_start, to_date=inv_end)
                    if inv_data and "date" in inv_data and inv_data["date"]:
                        inv_df = pd.DataFrame(inv_data)
                        inv_df["date_parsed"] = pd.to_datetime(inv_df["date"], format="%m/%d/%Y")
                        inv_df = inv_df.set_index("date_parsed").sort_index()
                        inv_df = inv_df.rename(columns={"close": "Close"})
                        inv_df["Close"] = pd.to_numeric(inv_df["Close"], errors="coerce")
                        inv_df = inv_df.dropna(subset=["Close"])
                        inv_df = inv_df[inv_df.index.date <= target]
                        if not inv_df.empty:
                            inv_metrics = calc_metrics(inv_df, target)
                            if inv_metrics and not inv_metrics["holiday"]:
                                metrics = inv_metrics
                                used_df = inv_df
                                used_source = "investiny"
                                print(f"  [INV] {name}: {inv_metrics['close']:.2f} ({inv_metrics['daily']:+.2f}%) via investing.com id={inv_id}")
                except Exception as ie:
                    print(f"  [INV WARN] {name}: {ie}")

            if metrics is None:
                continue

            if used_df is not None and used_source is not None:
                _emit_rows(used_df, cat, name, used_source)

            if cat not in result:
                result[cat] = {}
            result[cat][name] = metrics
        except Exception as e:
            print(f"  [WARN] {name} ({ticker}): {e}")

    # ── 한국 금리: 한국은행 ECOS API ──
    kr_rates, kr_history = fetch_kr_rates(start_date=start_date, end_date=end_date)
    if kr_rates:
        if "bond" not in result:
            result["bond"] = {}
        result["bond"].update(kr_rates)
    history_rows.extend(kr_history)

    return result, history_rows


def fetch_kr_rates(start_date=None, end_date=None):
    """한국은행 ECOS API 에서 한국 금리 데이터 수집.

    Args:
        start_date: 'YYYY-MM-DD' 수집 시작일. None 이면 end_date - 200 영업일 상당.
        end_date:   'YYYY-MM-DD' 수집 종료일. None 이면 오늘.
    """
    BOK_API_KEY = os.environ.get("BOK_API_KEY") or os.environ.get("ECOS_API_KEY", "sample")
    BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
    STAT_CODE = "817Y002"  # 시장금리(일별)

    items = {
        "KR CD 91D":  "010502000",
        "KR 3Y":      "010200000",
        "KR 5Y":      "010200002",
        "KR 10Y":     "010200001",
        "KR 30Y":     "010200003",
    }

    ref_date = dt.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else dt.date.today()
    is_sample = (BOK_API_KEY == "sample")
    if start_date:
        range_start = dt.datetime.strptime(start_date, "%Y-%m-%d").date()
        days_span = (ref_date - range_start).days + 10
        max_rows = max(200, days_span)
    else:
        range_start = ref_date - dt.timedelta(days=10 if is_sample else 200)
        max_rows = 5 if is_sample else 200
    start = range_start.strftime("%Y%m%d")
    end = ref_date.strftime("%Y%m%d")

    result = {}
    history_rows = []
    for name, item_code in items.items():
        try:
            url = f"{BASE_URL}/{BOK_API_KEY}/json/kr/1/{max_rows}/{STAT_CODE}/D/{start}/{end}/{item_code}"
            resp = requests.get(url, timeout=10)
            data = resp.json()

            if "RESULT" in data and "ERROR" in data["RESULT"].get("CODE", ""):
                print(f"  [BOK] {name}: API error - {data['RESULT']['MESSAGE'][:80]}")
                continue

            rows = data.get("StatisticSearch", {}).get("row", [])
            if not rows:
                continue

            valid = [(r["TIME"], float(r["DATA_VALUE"])) for r in rows if r.get("DATA_VALUE")]
            if not valid:
                continue

            indicator_code = INDICATOR_CODES.get(("bond", name))
            for t, v in valid:
                d = f"{t[:4]}-{t[4:6]}-{t[6:8]}"
                d_date = dt.datetime.strptime(d, "%Y-%m-%d").date()
                if d_date.weekday() >= 5:
                    continue
                if d_date < range_start or d_date > ref_date:
                    continue
                if indicator_code is None:
                    continue
                history_rows.append((
                    d, indicator_code, "bond", name,
                    float(v), None, None, None, None, "ECOS",
                ))

            close = valid[-1][1]
            date_str = valid[-1][0]
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            daily_chg = 0.0
            if len(valid) >= 2:
                daily_chg = (close - valid[-2][1]) / valid[-2][1] * 100

            weekly_chg = 0.0
            if len(valid) >= 5:
                weekly_chg = (close - valid[-5][1]) / valid[-5][1] * 100

            monthly_chg = 0.0
            ytd_chg = 0.0
            if not is_sample:
                if len(valid) >= 23:
                    monthly_chg = (close - valid[-23][1]) / valid[-23][1] * 100
                yr_vals = [(t, v) for t, v in valid if t[:4] == str(ref_date.year)]
                if yr_vals:
                    ytd_chg = (close - yr_vals[0][1]) / yr_vals[0][1] * 100

            spark_vals = [v for _, v in valid]
            first = spark_vals[0] if spark_vals else 1
            spark = [round((v / first - 1) * 100, 2) for v in spark_vals]

            result[name] = {
                "close": close,
                "date": date_fmt,
                "daily": round(daily_chg, 2),
                "weekly": round(weekly_chg, 2),
                "monthly": round(monthly_chg, 2),
                "ytd": round(ytd_chg, 2),
                "spark": spark,
            }
            print(f"  [BOK] {name}: {close}% ({date_fmt})")
        except Exception as e:
            print(f"  [WARN] BOK {name}: {e}")

    return result, history_rows


def build_report_data(target_date):
    """MKT100_MARKET_DAILY (Snowflake) 에서 읽어 지표를 계산하여 보고서 데이터 dict 반환.

    스키마: DATE, INDICATOR_CODE, CATEGORY, TICKER, CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE

    Snowflake 접속 실패 시 market_source 가 자동으로 CSV fallback.
    simulate.py 는 SNOWFLAKE_DISABLE=1 을 세팅해 CSV 경로 (cutoff 패치) 를 강제한다.
    """
    import pandas as pd
    from portfolio.market_source import load_long

    # target_date 기준 과거 2년분만 읽어 충분 (월간/연간 지표 계산용)
    start_ts = pd.Timestamp(target_date) - pd.DateOffset(years=2)
    df = load_long(start=start_ts.strftime("%Y-%m-%d"), end=target_date)

    if df.empty:
        return {}

    ref_date = dt.datetime.strptime(target_date, "%Y-%m-%d").date()
    target_ts = pd.Timestamp(target_date)

    result = {}
    for (cat, ticker), group in df.groupby(["CATEGORY", "TICKER"]):
        group = group.sort_values("DATE")
        group = group[group["DATE"] <= target_ts]
        if group.empty:
            continue

        metrics_df = group.set_index("DATE")[["CLOSE"]].rename(columns={"CLOSE": "Close"})
        metrics = calc_metrics(metrics_df, ref_date)
        if metrics is None:
            continue

        if cat not in result:
            result[cat] = {}
        result[cat][ticker] = metrics

    return result


def append_to_history(history_rows):
    """Append history_rows (10-tuples) to history/market_data.csv, skipping duplicates.

    Columns: DATE, INDICATOR_CODE, CATEGORY, TICKER, CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE
    Dedup 키: (DATE, INDICATOR_CODE).
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)
    file_exists = os.path.exists(HISTORY_CSV) and os.path.getsize(HISTORY_CSV) > 0

    existing = set()
    if file_exists:
        with open(HISTORY_CSV, newline="", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                d = row.get("DATE") or row.get("date")
                code = row.get("INDICATOR_CODE")
                if d and code:
                    existing.add((d, code))

    def _price(v):
        if v is None or v == "":
            return ""
        try:
            return f"{round(float(v), 3):.3f}"
        except (TypeError, ValueError):
            return ""

    def _vol(v):
        if v is None or v == "":
            return ""
        try:
            return str(int(round(float(v))))
        except (TypeError, ValueError):
            return ""

    def _text(v):
        if v is None:
            return ""
        return str(v)

    new_rows = []
    for row in history_rows:
        if len(row) != 10:
            continue
        d, code, cat, tk, close, o, h, l, vol, src = row
        if not code:
            continue
        if (d, code) in existing:
            continue
        new_rows.append((d, code, cat, tk, close, o, h, l, vol, src))

    if not new_rows:
        return

    new_rows.sort(key=lambda r: (r[0], r[1]))
    write_header = not file_exists
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        if write_header:
            writer.writerow(HISTORY_CSV_COLUMNS)
        for r in new_rows:
            d, code, cat, tk, close, o, h, l, vol, src = r
            writer.writerow([
                _text(d), _text(code), _text(cat), _text(tk),
                _price(close), _price(o), _price(h), _price(l),
                _vol(vol), _text(src),
            ])
