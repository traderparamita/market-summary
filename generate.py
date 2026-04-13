#!/usr/local/bin/python3.12
"""
Daily Market Summary Report Generator
- yfinance로 글로벌 시장 데이터 수집
- HTML 보고서 자동 생성
"""

import yfinance as yf
import FinanceDataReader as fdr
import datetime as dt
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Bump when the OG image (og-image.png) changes so that social caches (KakaoTalk,
# Slack, Facebook) refetch instead of showing the stale thumbnail.
OG_IMAGE_VERSION = "20260410-1"

try:
    from investiny import historical_data as inv_historical
    HAS_INVESTINY = True
except ImportError:
    HAS_INVESTINY = False

# ── Config ──────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "summary")
os.makedirs(OUTPUT_DIR, exist_ok=True)
HISTORY_DIR = os.path.join(os.path.dirname(__file__), "history")
HISTORY_CSV = os.path.join(HISTORY_DIR, "market_data.csv")

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

# 수집 대상 티커
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
    ("commodity", "WTI"):     "CM_WTI",
    ("commodity", "Brent"):   "CM_BRENT",
    ("commodity", "Gold"):    "CM_GOLD",
    ("commodity", "Silver"):  "CM_SILVER",
    ("commodity", "Copper"):  "CM_COPPER",
    ("commodity", "Nat Gas"): "CM_NATGAS",
    ("risk", "VIX"): "RK_VIX",
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

# CSV 스키마 (Snowflake MKT100_MARKET_DAILY 1:1)
HISTORY_CSV_COLUMNS = [
    "DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
    "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE",
]


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
        # 잡이 오래 스킵됐어도 CSV 최신일 기준으로 자동 복구.
        range_start = None
        if os.path.exists(HISTORY_CSV):
            try:
                import pandas as _pd
                _df = _pd.read_csv(HISTORY_CSV, usecols=["DATE"])
                if len(_df):
                    _max = _pd.to_datetime(_df["DATE"]).max().date()
                    # CSV 에 target 보다 미래 행이 섞여 있으면 target 기준으로 앵커
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
    history_rows = []  # 10-tuple per row

    def _num(row, *names):
        """row 에서 첫 번째로 발견되는 컬럼의 값을 float 으로 반환. 없거나 NaN 이면 None."""
        import math
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
            return  # MKT000 에 없는 지표 (예: VKOSPI) — CSV/Snowflake 에 기록하지 않음
        for idx, row in used_df.iterrows():
            d = idx.date() if hasattr(idx, "date") else idx
            if d.weekday() >= 5:   # 토/일 제외
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
            used_df = None        # winning DataFrame
            used_source = None    # "yfinance" / "FDR" / "investiny"
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
                    inv_start = (range_start - dt.timedelta(days=3)).strftime("%m/%d/%Y")
                    inv_end = (target + dt.timedelta(days=1)).strftime("%m/%d/%Y")
                    inv_data = inv_historical(investing_id=inv_id, from_date=inv_start, to_date=inv_end)
                    if inv_data and "date" in inv_data and inv_data["date"]:
                        import pandas as pd
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
        # ECOS max_rows 는 기간 길이에 맞춰 여유 있게
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

            # Collect full history for CSV (10-tuple)
            indicator_code = INDICATOR_CODES.get(("bond", name))
            for t, v in valid:
                d = f"{t[:4]}-{t[4:6]}-{t[6:8]}"
                d_date = dt.datetime.strptime(d, "%Y-%m-%d").date()
                if d_date.weekday() >= 5:  # 토/일 제외
                    continue
                if d_date < range_start or d_date > ref_date:
                    continue
                if indicator_code is None:
                    continue  # MKT000 에 없는 KR bond (KR 5Y, KR 30Y) → 스킵
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

            # sample 키에서는 월간/YTD 계산 불가
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


def fmt(val, decimals=2):
    if abs(val) >= 1000:
        return f"{val:,.{decimals}f}"
    return f"{val:.{decimals}f}"

def chg_class(val):
    return "up" if val > 0 else ("down" if val < 0 else "flat")

def chg_sign(val):
    return f"+{val:.2f}%" if val > 0 else f"{val:.2f}%"

def heat_color(val):
    """변동폭에 따른 배경색 (라이트 테마용)"""
    if val >= 3:    return "#c6f6d5"
    if val >= 1.5:  return "#d4edda"
    if val >= 0.5:  return "#e8f5e9"
    if val > 0:     return "#f1f8f4"
    if val == 0:    return "#f7f8fa"
    if val > -0.5:  return "#fef2f2"
    if val > -1.5:  return "#fde8e8"
    if val > -3:    return "#fbd5d5"
    return "#f8b4b4"

def heat_text(val):
    if val >= 1.5:  return "#065f46"
    if val > 0:     return "#047857"
    if val == 0:    return "#6b7280"
    if val > -1.5:  return "#b91c1c"
    return "#7f1d1d"

def spark_svg(data, w=80, h=24, color="#F58220"):
    """미니 SVG 스파크라인"""
    if not data or len(data) < 2:
        return ""
    mn, mx = min(data), max(data)
    rng = mx - mn if mx != mn else 1
    pts = []
    step = w / (len(data) - 1)
    for i, v in enumerate(data):
        x = round(i * step, 1)
        y = round(h - (v - mn) / rng * (h - 2) - 1, 1)
        pts.append(f"{x},{y}")
    last_y = round(h - (data[-1] - mn) / rng * (h - 2) - 1, 1)
    # 마지막 값이 양이면 초록, 음이면 빨강
    end_color = "#0d9b6a" if data[-1] >= 0 else "#d9304f"
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        f'<circle cx="{round((len(data)-1)*step,1)}" cy="{last_y}" r="2.5" fill="{end_color}"/>'
        f'</svg>'
    )


def generate_html(data):
    """데이터로 HTML 보고서 생성"""

    dates = [item["date"] for cat in data.values() for item in cat.values()]
    report_date = max(dates) if dates else str(dt.date.today())
    report_dt = dt.datetime.strptime(report_date, "%Y-%m-%d")
    ym = report_date[:7]
    day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][report_dt.weekday()]

    eq = data.get("equity", {})
    bd = data.get("bond", {})
    fx = data.get("fx", {})
    cm = data.get("commodity", {})
    rk = data.get("risk", {})
    st = data.get("stocks", {})

    # === 히트맵 행 생성 ===
    def heatmap_row(name, d, show_dollar=False, as_bp=False):
        close = d["close"]
        is_hol = d.get("holiday", False)
        hol_note = d.get("holiday_note", "")

        if as_bp:
            close_str = f"{close:.2f}%"
        elif show_dollar:
            close_str = f"${fmt(close)}" if close < 10000 else f"${close:,.0f}"
        else:
            close_str = fmt(close, 0) if close > 100 else fmt(close, 2)

        # 휴일이면 이름 옆에 표시
        name_display = name
        if is_hol:
            name_display = f'{name} <span style="font-size:10px;color:var(--warn);font-weight:400;">(Holiday)</span>'

        spark = spark_svg(d.get("spark", []))
        cells = ""
        for period in ["daily", "weekly", "monthly", "ytd"]:
            v = d[period]
            if is_hol and period == "daily":
                # 휴일: 전일 종가 유지, 0 변화, 회색 배경
                zero_txt = "0 bp" if as_bp else "0.00%"
                cells += f'<td class="heat-cell" style="background:#f7f8fa;color:#7c8298">{zero_txt}</td>'
            else:
                bg = heat_color(v)
                tc = heat_text(v)
                if as_bp:
                    # v 는 yield 의 상대 % 변화 → 절대 bp 변화로 환산
                    prev = close / (1 + v / 100) if (1 + v / 100) else close
                    bp = (close - prev) * 100
                    sign = "+" if bp > 0 else ""
                    cells += f'<td class="heat-cell" style="background:{bg};color:{tc}">{sign}{bp:.0f} bp</td>'
                else:
                    cells += f'<td class="heat-cell" style="background:{bg};color:{tc}">{chg_sign(v)}</td>'
        return f"""<tr>
          <td class="name-cell">{name_display}</td>
          <td class="close-cell">{close_str}</td>
          <td class="spark-cell">{spark}</td>
          {cells}
        </tr>"""

    # === 주요 무버 (daily 기준 상위/하위) ===
    all_items = [(n, d) for cat in [eq, st, cm, fx] for n, d in cat.items()]
    sorted_by_daily = sorted(all_items, key=lambda x: x[1]["daily"], reverse=True)
    top3 = sorted_by_daily[:3]
    bottom3 = sorted_by_daily[-3:]

    # === VIX 레벨 판정 ===
    vix = rk.get("VIX", {})
    vix_val = vix.get("close", 0)
    if vix_val >= 30:
        vix_label, vix_color = "Extreme Fear", "#d9304f"
    elif vix_val >= 20:
        vix_label, vix_color = "Elevated", "#d48b07"
    elif vix_val >= 15:
        vix_label, vix_color = "Normal", "#7c8298"
    else:
        vix_label, vix_color = "Complacent", "#0d9b6a"

    # === HTML 조립 ===
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Summary | {report_date}</title>
<meta name="description" content="글로벌 시장 요약 보고서 — {report_date} (Equity · Bonds · FX · Commodities · Risk)">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="icon" type="image/png" sizes="192x192" href="../favicon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="../favicon-512.png">
<link rel="apple-touch-icon" sizes="180x180" href="../apple-touch-icon.png">
<meta property="og:type" content="article">
<meta property="og:title" content="Market Summary | {report_date}">
<meta property="og:description" content="글로벌 시장 요약 보고서 — {report_date} (Equity · Bonds · FX · Commodities · Risk)">
<meta property="og:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://traderparamita.github.io/market-summary/{ym}/{report_date}.html">
<meta property="og:site_name" content="Market Summary">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Market Summary | {report_date}">
<meta name="twitter:description" content="글로벌 시장 요약 보고서 — {report_date}">
<meta name="twitter:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --card2:#f0f1f6;
  --border:#e0e3ed; --text:#2d3148; --muted:#7c8298;
  --accent:#F58220; --accent2:#043B72;
  --up:#0d9b6a; --down:#d9304f; --warn:#CB6015;
  --gold:#b8860b; --oil:#d35400;
}}
::selection{{background:#F58220;color:#ffffff}}
::-moz-selection{{background:#F58220;color:#ffffff}}
/* Story Hero keeps original blue — brand accents apply elsewhere */
.story-hero{{border-left-color:#3b6ee6!important}}
.story-hero h2{{color:#3b6ee6!important}}
.story-text .hl-accent{{color:#3b6ee6!important}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic','맑은 고딕',-apple-system,sans-serif;
  background:var(--bg);color:var(--text);
  line-height:1.65;padding:24px;max-width:1360px;margin:0 auto;
}}

/* ── Header ── */
.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px;padding-bottom:20px;border-bottom:2px solid var(--border)}}
.header-left h1{{font-size:26px;font-weight:700;color:#1a1d2e;margin-bottom:2px}}
.header-left .date{{font-size:13px;color:var(--muted);letter-spacing:1px}}
.header-right{{display:flex;gap:20px;align-items:center}}
.mood-badge{{display:flex;align-items:center;gap:8px;padding:8px 18px;border-radius:24px;font-size:13px;font-weight:600}}

/* ── KPI Strip ── */
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:28px}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.kpi-label{{font-size:11px;color:var(--muted);font-weight:500;margin-bottom:1px}}
.kpi-value{{font-size:18px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}
.kpi-chg{{font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.up{{color:var(--up)}}.down{{color:var(--down)}}.flat{{color:var(--muted)}}

/* ── Top Movers ── */
.movers-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
.movers-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 20px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.movers-card h3{{font-size:13px;color:var(--muted);font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px}}
.mover-item{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #f0f1f5}}
.mover-item:last-child{{border:none}}
.mover-name{{font-size:13px;font-weight:500}}
.mover-val{{font-size:15px;font-weight:700;font-family:'JetBrains Mono',monospace}}

/* ── Heatmap Table ── */
.heatmap-section{{margin-bottom:28px}}
.heatmap-section h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.heatmap-section h2 .badge{{font-size:11px;padding:2px 8px;border-radius:12px;background:var(--card2);color:var(--muted);font-weight:500}}
.heatmap-section h2 .src-tag{{font-size:10px;padding:2px 8px;border-radius:10px;background:#f0f1f5;color:#9a9db5;font-weight:400;margin-left:6px;letter-spacing:0.3px}}
.heatmap{{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.heatmap th{{font-size:11px;font-weight:600;color:var(--muted);padding:10px 12px;text-align:right;background:var(--card2);border-bottom:1px solid var(--border);white-space:nowrap}}
.heatmap th:first-child,.heatmap th:nth-child(2),.heatmap th:nth-child(3){{text-align:left}}
.heatmap td{{padding:8px 12px;font-size:13px;border-bottom:1px solid #f3f4f8}}
.heatmap tr:last-child td{{border-bottom:none}}
.name-cell{{font-weight:600;color:#1a1d2e;white-space:nowrap;min-width:100px}}
.close-cell{{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text);text-align:left;white-space:nowrap}}
.spark-cell{{text-align:center;padding:4px 8px}}
.heat-cell{{text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600;border-radius:0;transition:all 0.15s}}
.heatmap tr:hover{{filter:brightness(0.97)}}

/* ── Charts ── */
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
.chart-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.chart-card .title{{font-size:13px;color:var(--muted);font-weight:600;margin-bottom:12px}}
.chart-box{{position:relative;height:260px}}

/* ── Risk ── */
.risk-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:28px}}
.risk-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.risk-card .label{{font-size:12px;color:var(--muted);margin-bottom:4px}}
.risk-card .value{{font-size:28px;font-weight:700;font-family:'JetBrains Mono',monospace}}
.risk-card .desc{{font-size:11px;font-weight:600;margin-top:2px}}
.risk-card .bar-track{{height:6px;background:#ecedf2;border-radius:3px;margin-top:8px;overflow:hidden}}
.risk-card .bar-fill{{height:100%;border-radius:3px}}

/* ── Tabs ── */
.tab-bar{{display:flex;gap:0;margin-bottom:28px;border-bottom:2px solid var(--border)}}
.tab-btn{{padding:12px 28px;font-size:14px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s}}
.tab-btn:hover{{color:var(--text)}}
.tab-btn.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.tab-panel{{display:none}}
.tab-panel.active{{display:block}}

/* ── Story Tab ── */
.story-hero{{background:linear-gradient(135deg,#eef1f8,#e8e5f3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:32px}}
.story-hero h2{{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}}
.story-text{{font-size:16px;color:#2d3148;line-height:1.9}}
.story-text strong{{color:#1a1d2e}}.story-text .hl-up{{color:var(--up);font-weight:600}}.story-text .hl-down{{color:var(--down);font-weight:600}}.story-text .hl-warn{{color:var(--warn);font-weight:600}}.story-text .hl-accent{{color:var(--accent);font-weight:600}}

.causal-chain{{display:flex;align-items:stretch;gap:0;margin-bottom:28px;overflow-x:auto;padding-bottom:8px}}
.cause-node{{flex:1;min-width:160px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 14px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.cause-node .node-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
.cause-node .node-title{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:4px}}
.cause-node .node-detail{{font-size:12px;color:var(--text)}}
.cause-node .node-impact{{margin-top:8px;font-size:17px;font-weight:700}}
.cause-arrow{{display:flex;align-items:center;padding:0 4px;color:var(--muted);font-size:18px;flex-shrink:0}}

.session-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:32px}}
.session-block{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.session-block::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px}}
.session-block.asia::before{{background:linear-gradient(90deg,#d48b07,#e06818)}}
.session-block.europe::before{{background:linear-gradient(90deg,#F58220,#043B72)}}
.session-block.us::before{{background:linear-gradient(90deg,#043B72,#7F9FC3)}}
.session-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.session-icon{{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px}}
.session-icon.asia{{background:rgba(212,139,7,0.1)}}.session-icon.europe{{background:rgba(59,110,230,0.1)}}.session-icon.us{{background:rgba(107,92,231,0.1)}}
.session-name{{font-size:15px;font-weight:600;color:#1a1d2e}}
.session-time{{font-size:11px;color:var(--muted)}}
.session-verdict{{display:inline-block;padding:3px 10px;border-radius:16px;font-size:11px;font-weight:600;margin-bottom:10px}}
.verdict-up{{background:rgba(13,155,106,0.1);color:var(--up)}}.verdict-down{{background:rgba(217,48,79,0.1);color:var(--down)}}.verdict-mixed{{background:rgba(212,139,7,0.1);color:var(--warn)}}
.session-events{{list-style:none}}.session-events li{{font-size:12px;padding:6px 0 6px 12px;border-bottom:1px solid #f3f4f8;position:relative}}
.session-events li:last-child{{border:none}}.session-events li::before{{content:'';position:absolute;left:0;top:12px;width:4px;height:4px;border-radius:50%;background:var(--muted)}}
.session-events .ev-time{{color:var(--muted);font-size:10px;font-weight:600}}
.session-kpi{{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px;padding-top:10px;border-top:1px solid var(--border)}}
.s-kpi{{text-align:center;padding:6px;border-radius:6px;background:var(--card2)}}
.s-kpi-label{{font-size:10px;color:var(--muted)}}.s-kpi-value{{font-size:15px;font-weight:700}}

.insight-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:32px}}
.insight-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:22px;position:relative;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.insight-card .badge{{position:absolute;top:14px;right:14px;padding:2px 10px;border-radius:16px;font-size:11px;font-weight:600}}
.insight-card h3{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:10px;padding-right:50px}}
.insight-card p{{font-size:13px;color:var(--text);line-height:1.8}}
.insight-card .metric-row{{display:flex;gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}}
.metric-item{{flex:1;text-align:center}}.metric-label{{font-size:10px;color:var(--muted)}}.metric-value{{font-size:16px;font-weight:700;font-family:'JetBrains Mono',monospace}}

.cross-asset{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:28px;margin-bottom:28px;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.cross-asset h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:6px}}
.cross-asset .sub{{font-size:12px;color:var(--muted);margin-bottom:18px}}
.af-map{{display:grid;grid-template-columns:auto 1fr auto 1fr auto;align-items:center;gap:10px 6px}}
.af-node{{background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:12px 14px;text-align:center;min-width:120px}}
.af-node-title{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}}
.af-node-value{{font-size:18px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}
.af-node-chg{{font-size:12px;font-weight:600}}
.af-arrow{{text-align:center;color:var(--muted);font-size:12px;line-height:1.3}}
.af-arrow .arr{{font-size:16px;display:block}}.af-arrow .lbl{{font-size:10px}}

.risk-section{{background:linear-gradient(135deg,#fdf2f4,#f8f5ff);border:1px solid rgba(217,48,79,0.12);border-radius:12px;padding:28px;margin-bottom:28px}}
.risk-section h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:16px}}
.risk-items{{list-style:none;display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.risk-item{{display:flex;align-items:flex-start;gap:8px;padding:10px 14px;border-radius:8px;background:rgba(255,255,255,0.6);font-size:12px;line-height:1.6}}
.risk-tag{{flex-shrink:0;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;margin-top:1px}}
.risk-tag.high{{background:rgba(217,48,79,0.15);color:var(--down)}}.risk-tag.med{{background:rgba(212,139,7,0.15);color:var(--warn)}}

.footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:40px;padding-top:20px;border-top:1px solid var(--border)}}

@media(max-width:900px){{
  .session-grid,.insight-grid,.chart-grid,.movers-row{{grid-template-columns:1fr}}
  .causal-chain{{flex-direction:column}}.cause-arrow{{transform:rotate(90deg);padding:4px 0}}
  .af-map{{grid-template-columns:1fr}}.risk-items{{grid-template-columns:1fr}}
}}

</style>
</head>
<body>

<!-- ══ HEADER ══ -->
<div class="header">
  <div class="header-left">
    <h1>Daily Market Summary</h1>
    <div class="date">{day_name}, {report_date}</div>
  </div>
  <div class="header-right">
    <div class="mood-badge" style="background:{'#fef2f2' if vix_val>=20 else '#f0fdf4'};color:{vix_color};border:1px solid {vix_color}33">
      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{vix_color}"></span>
      VIX {vix_val:.1f} &mdash; {vix_label}
    </div>
  </div>
</div>

<!-- ══ TABS ══ -->
<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('story')">Market Story</button>
  <button class="tab-btn" onclick="switchTab('data')">Data Dashboard</button>
</div>

<!-- ══════ TAB 1: DATA ══════ -->
<div id="tab-data" class="tab-panel">

<div class="kpi-strip">
"""
    # KPI 목록
    kpi_list = [
        ("KOSPI", eq.get("KOSPI")),
        ("S&P500", eq.get("S&P500")),
        ("NASDAQ", eq.get("NASDAQ")),
        ("Nikkei", eq.get("Nikkei225")),
        ("US 10Y", bd.get("US 10Y")),
        ("USD/KRW", fx.get("USD/KRW")),
        ("WTI", cm.get("WTI")),
        ("Gold", cm.get("Gold")),
    ]
    for label, d in kpi_list:
        if not d:
            continue
        c = d["close"]
        if label in ["WTI", "Gold"]:
            v = f"${fmt(c)}"
        elif label == "US 10Y":
            v = f"{c:.2f}%"
        elif c > 100:
            v = fmt(c, 0)
        else:
            v = fmt(c, 2)
        cls = chg_class(d["daily"])
        html += f"""  <div class="kpi">
    <div class="kpi-label">{label}</div>
    <div class="kpi-value">{v}</div>
    <div class="kpi-chg {cls}">{chg_sign(d['daily'])}</div>
  </div>\n"""
    html += "</div>\n"

    # ── Top/Bottom Movers ──
    html += '<div class="movers-row">\n'
    html += '<div class="movers-card"><h3>Top Gainers</h3>\n'
    for name, d in top3:
        cls = chg_class(d["daily"])
        html += f'<div class="mover-item"><span class="mover-name">{name}</span><span class="mover-val {cls}">{chg_sign(d["daily"])}</span></div>\n'
    html += '</div>\n<div class="movers-card"><h3>Top Losers</h3>\n'
    for name, d in bottom3:
        cls = chg_class(d["daily"])
        html += f'<div class="mover-item"><span class="mover-name">{name}</span><span class="mover-val {cls}">{chg_sign(d["daily"])}</span></div>\n'
    html += '</div>\n</div>\n'

    # ── 이미지 순서에 맞는 고정 정렬 ──
    EQUITY_ORDER = [
        "KOSPI", "KOSDAQ",                                    # 한국
        "S&P500", "NASDAQ", "Russell2K",                      # 미국
        "STOXX50", "FTSE100", "DAX", "CAC40",                 # 유럽
        "Shanghai", "HSI",                                     # 중국
        "Nikkei225",                                           # 일본
        "NIFTY50",                                             # 인도
    ]
    MSCI_ORDER = ["MSCI World", "MSCI ACWI", "MSCI LATAM", "MSCI EMEA"]
    BOND_RATE_ORDER = [
        "KR CD 91D", "KR 3Y", "KR 5Y", "KR 10Y", "KR 30Y",  # 한국
        "US 2Y", "US 10Y", "US 30Y",                          # 미국
    ]
    BOND_ETF_ORDER = ["AGG", "TLT", "LQD", "HYG", "EMB"]
    FX_ORDER = ["DXY", "USD/KRW", "EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY", "USD/CNY"]
    CM_ORDER = ["WTI", "Brent", "Gold", "Silver", "Copper", "Nat Gas"]
    ST_ORDER = [
        "NVIDIA", "Broadcom", "Alphabet", "Amazon", "META",
        "Apple", "Microsoft", "Tesla", "TSMC", "Samsung",
    ]

    def ordered(cat, order):
        """order 리스트 순서대로 정렬, 없는 항목은 뒤에 추가"""
        idx = {name: i for i, name in enumerate(order)}
        return sorted(cat.items(), key=lambda x: idx.get(x[0], 999))

    bond_etfs = {"AGG", "TLT", "HYG", "LQD", "EMB"}
    bd_rates = {k: v for k, v in bd.items() if k not in bond_etfs}
    bd_etf = {k: v for k, v in bd.items() if k in bond_etfs}

    msci_names = set(MSCI_ORDER)
    eq_regional = {k: v for k, v in eq.items() if k not in msci_names}
    eq_msci = {k: v for k, v in eq.items() if k in msci_names}

    # ── Heatmap Tables ──
    DATA_SOURCES = {
        "Equity":        "yfinance · FinanceDataReader · investiny",
        "MSCI Equity":   "yfinance (ETF proxy)",
        "Bonds & Rates": "yfinance · ECOS(한국은행)",
        "Bond ETF":      "yfinance",
        "FX":            "investiny(investing.com) · FinanceDataReader",
        "Commodities":   "investiny(investing.com) · yfinance",
        "Major Stocks":  "yfinance",
    }
    sections = [
        ("Equity",        eq_regional, False, False, EQUITY_ORDER),
        ("MSCI Equity",   eq_msci,     False, False, MSCI_ORDER),
        ("Bonds & Rates", bd_rates,    False, True,  BOND_RATE_ORDER),
        ("Bond ETF",      bd_etf,      True,  False, BOND_ETF_ORDER),
        ("FX",            fx,          False, False, FX_ORDER),
        ("Commodities",   cm,          True,  False, CM_ORDER),
        ("Major Stocks",  st,          True,  False, ST_ORDER),
    ]
    for title, cat, dollar, as_bp, order in sections:
        if not cat:
            continue
        items = ordered(cat, order)
        src = DATA_SOURCES.get(title, "")
        src_html = f' <span class="src-tag">{src}</span>' if src else ""
        html += f"""<div class="heatmap-section">
<h2>{title} <span class="badge">{len(items)}</span>{src_html}</h2>
<table class="heatmap">
<thead><tr><th>Name</th><th>Close</th><th>20D Trend</th><th>Daily</th><th>Weekly</th><th>Monthly</th><th>YTD</th></tr></thead>
<tbody>\n"""
        for name, d in items:
            html += heatmap_row(name, d, dollar, as_bp)
        html += "</tbody></table></div>\n"

    # ── Risk Dashboard ──
    html += '<div class="heatmap-section"><h2>Risk Dashboard <span class="src-tag">yfinance · FinanceDataReader</span></h2></div>\n<div class="risk-strip">\n'
    # VIX
    vix_pct = min(vix_val / 50 * 100, 100) if vix_val else 0
    html += f"""<div class="risk-card">
  <div class="label">VIX</div>
  <div class="value" style="color:{vix_color}">{vix_val:.1f}</div>
  <div class="desc" style="color:{vix_color}">{vix_label}</div>
  <div class="bar-track"><div class="bar-fill" style="width:{vix_pct:.0f}%;background:{vix_color}"></div></div>
</div>\n"""
    # 기타 리스크 지표
    for name, d in rk.items():
        if name == "VIX":
            continue
        html += f"""<div class="risk-card">
  <div class="label">{name}</div>
  <div class="value">{d['close']:.1f}</div>
  <div class="desc {chg_class(d['daily'])}">{chg_sign(d['daily'])}</div>
</div>\n"""
    # 채권 ETF도 리스크에 추가
    for name in ["HYG", "EMB"]:
        if name in bd:
            d = bd[name]
            html += f"""<div class="risk-card">
  <div class="label">{name}</div>
  <div class="value">{d['close']:.1f}</div>
  <div class="desc {chg_class(d['daily'])}">{chg_sign(d['daily'])}</div>
</div>\n"""
    html += '</div>\n'

    # ── Charts ──
    eq_sorted_names = [n for n, _ in sorted(eq.items(), key=lambda x: x[1]["daily"], reverse=True)]
    eq_sorted_daily = [eq[n]["daily"] for n in eq_sorted_names]
    st_sorted_names = [n for n, _ in sorted(st.items(), key=lambda x: x[1]["daily"], reverse=True)]
    st_sorted_daily = [st[n]["daily"] for n in st_sorted_names]
    cm_names = list(cm.keys())
    cm_ytd = [cm[n]["ytd"] for n in cm_names]
    fx_names = list(fx.keys())
    fx_daily = [fx[n]["daily"] for n in fx_names]

    # Scatter: daily vs weekly (cross-asset)
    scatter_data = []
    for cat_items, cat_label in [(eq, "equity"), (st, "stocks"), (cm, "commodity")]:
        for name, d in cat_items.items():
            scatter_data.append({"x": d["weekly"], "y": d["daily"], "label": name, "cat": cat_label})

    html += f"""
<!-- ══ CHARTS ══ -->
<div class="chart-grid">
  <div class="chart-card">
    <div class="title">Equity: Daily Change (%)</div>
    <div class="chart-box"><canvas id="eqChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="title">Stocks: Daily Change (%)</div>
    <div class="chart-box"><canvas id="stChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="title">Daily vs Weekly (Cross-Asset)</div>
    <div class="chart-box"><canvas id="scatterChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="title">Commodity YTD (%)</div>
    <div class="chart-box"><canvas id="cmChart"></canvas></div>
  </div>
</div>


</div><!-- /tab-data -->

<!-- ══════ TAB 2: STORY ══════ -->
<div id="tab-story" class="tab-panel active">

<!-- STORY_CONTENT_PLACEHOLDER -->

</div><!-- /tab-story -->

<div class="footer">Daily Market Summary | yfinance auto-generated | {report_date}</div>

<script>
function switchTab(id){{
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  event.target.classList.add('active');
  // 차트 리사이즈 (탭 전환 후)
  if(id==='data') setTimeout(()=>window.dispatchEvent(new Event('resize')),50);
}}
Chart.defaults.color='#7c8298';
Chart.defaults.borderColor='#e8eaf0';
Chart.defaults.font.family="'Spoqa Han Sans Neo','Spoqa Han Sans',sans-serif";
Chart.defaults.font.size=11;
const UP='#0d9b6a',DN='#d9304f',AC='#F58220',WN='#CB6015',MU='#b0b4c4',GD='#b8860b';
function bc(d){{return d.map(v=>v>0?UP:v<0?DN:MU)}}

// Equity bar
new Chart(document.getElementById('eqChart'),{{
  type:'bar',
  data:{{labels:{json.dumps(eq_sorted_names)},datasets:[{{data:{json.dumps(eq_sorted_daily)},backgroundColor:bc({json.dumps(eq_sorted_daily)}),borderRadius:4,barPercentage:.6}}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{weight:'600',size:11}}}}}}}}}}
}});

// Stocks bar
new Chart(document.getElementById('stChart'),{{
  type:'bar',
  data:{{labels:{json.dumps(st_sorted_names)},datasets:[{{data:{json.dumps(st_sorted_daily)},backgroundColor:bc({json.dumps(st_sorted_daily)}),borderRadius:4,barPercentage:.6}}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{weight:'600',size:11}}}}}}}}}}
}});

// Scatter: daily vs weekly
new Chart(document.getElementById('scatterChart'),{{
  type:'scatter',
  data:{{
    datasets:[
      {{label:'Equity',data:{json.dumps([s for s in scatter_data if s['cat']=='equity'])},backgroundColor:AC+'aa',pointRadius:6}},
      {{label:'Stocks',data:{json.dumps([s for s in scatter_data if s['cat']=='stocks'])},backgroundColor:'#043B72aa',pointRadius:6}},
      {{label:'Commodity',data:{json.dumps([s for s in scatter_data if s['cat']=='commodity'])},backgroundColor:WN+'aa',pointRadius:6}}
    ]
  }},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{
      legend:{{position:'top',labels:{{boxWidth:8}}}},
      tooltip:{{callbacks:{{label:c=>c.raw.label+' (W:'+c.raw.x.toFixed(1)+'%, D:'+c.raw.y.toFixed(1)+'%)'}}}}
    }},
    scales:{{
      x:{{title:{{display:true,text:'Weekly %',color:'#7c8298'}},grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},
      y:{{title:{{display:true,text:'Daily %',color:'#7c8298'}},grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}}
    }}
  }}
}});

// Commodity YTD
new Chart(document.getElementById('cmChart'),{{
  type:'bar',
  data:{{labels:{json.dumps(cm_names)},datasets:[{{data:{json.dumps(cm_ytd)},backgroundColor:bc({json.dumps(cm_ytd)}),borderRadius:4,barPercentage:.55}}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{weight:'600'}}}}}}}}}}
}});
</script>
</body>
</html>"""

    return html, report_date


def prev_business_day(ref=None):
    """한국 영업일 기준 전 영업일 (주말 제외, 공휴일은 미반영). KST 기준."""
    if ref:
        d = ref
    else:
        # UTC 환경에서도 KST(+9) 기준으로 오늘 날짜 계산
        kst = dt.timezone(dt.timedelta(hours=9))
        d = dt.datetime.now(kst).date()
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:  # 토=5, 일=6
        d -= dt.timedelta(days=1)
    return d


def generate_index():
    """일간/주간/월간 탭이 있는 index.html 생성"""
    import glob

    # ── 일간 보고서 수집 ──
    months = {}
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "????-??", "????-??-??.html")), reverse=True):
        fname = os.path.basename(path)
        date = fname.replace(".html", "")
        month = date[:7]
        try:
            d = dt.datetime.strptime(date, "%Y-%m-%d")
            day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d.weekday()]
        except:
            day_name = ""
        if month not in months:
            months[month] = []
        months[month].append((date, day_name))

    sorted_months = sorted(months.keys(), reverse=True)
    latest_month = sorted_months[0] if sorted_months else ""

    daily_month_btns = ""
    daily_panels = ""
    for m in sorted_months:
        active = " active" if m == latest_month else ""
        label = dt.datetime.strptime(m, "%Y-%m").strftime("%Y %b")
        daily_month_btns += f'      <button class="month-btn{active}" onclick="showSub(\'daily\',\'{m}\')">{label}</button>\n'
        items = ""
        for date, day in months[m]:
            items += f'          <li><a href="{m}/{date}.html">{date} ({day})</a></li>\n'
        daily_panels += f'      <div class="sub-panel{active}" id="daily-{m}"><ul>\n{items}      </ul></div>\n'

    # ── 주간 보고서 수집 (월별 그룹, 날짜 범위 표시) ──
    import re as _re
    weekly_by_month = {}
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "weekly", "*.html")), reverse=True):
        fname = os.path.basename(path)
        if fname.endswith("_story.html"):
            continue
        week_label = fname.replace(".html", "")  # e.g. "2026-W02"

        # HTML에서 날짜 범위 추출
        date_range = ""
        try:
            with open(path) as _f:
                head = _f.read(15000)
            m = _re.search(r'class="date">\s*([\d-]+)\s*~\s*([\d-]+)', head)
            if m:
                date_range = f"{m.group(1)} ~ {m.group(2)}"
        except:
            pass

        # 월 판단
        try:
            year = int(week_label[:4])
            week_num = int(week_label.split("W")[1])
            monday = dt.datetime.strptime(f"{year}-W{week_num:02d}-1", "%Y-W%W-%w").date()
            month_key = monday.strftime("%Y-%m")
        except:
            month_key = week_label[:7]

        if month_key not in weekly_by_month:
            weekly_by_month[month_key] = []
        display = f"{week_label} ({date_range})" if date_range else week_label
        weekly_by_month[month_key].append((display, fname))

    sorted_weekly_months = sorted(weekly_by_month.keys(), reverse=True)
    latest_weekly_month = sorted_weekly_months[0] if sorted_weekly_months else ""

    weekly_month_btns = ""
    weekly_panels = ""
    for m in sorted_weekly_months:
        active = " active" if m == latest_weekly_month else ""
        label = dt.datetime.strptime(m, "%Y-%m").strftime("%Y %b")
        weekly_month_btns += f'      <button class="month-btn{active}" onclick="showSub(\'weekly\',\'{m}\')">{label}</button>\n'
        items = ""
        for display, fname in weekly_by_month[m]:
            items += f'          <li><a href="weekly/{fname}">{display}</a></li>\n'
        weekly_panels += f'      <div class="sub-panel{active}" id="weekly-{m}"><ul>\n{items}      </ul></div>\n'

    # ── 월간 보고서 수집 ──
    monthly_items = ""
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "monthly", "*.html")), reverse=True):
        fname = os.path.basename(path)
        if fname.endswith("_story.html"):
            continue
        label = fname.replace(".html", "")
        try:
            d = dt.datetime.strptime(label, "%Y-%m")
            label = d.strftime("%Y %B")
        except:
            pass
        monthly_items += f'      <li><a href="monthly/{fname}">{label}</a></li>\n'

    index_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Summary</title>
<meta name="description" content="매일 자동 생성되는 글로벌 시장 요약 보고서 — Equity, Bonds, FX, Commodities, Risk">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="icon" type="image/png" sizes="192x192" href="favicon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="favicon-512.png">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:title" content="Market Summary | Daily Global Markets">
<meta property="og:description" content="매일 자동 생성되는 글로벌 시장 요약 보고서 — Equity, Bonds, FX, Commodities, Risk">
<meta property="og:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://traderparamita.github.io/market-summary/">
<meta property="og:site_name" content="Market Summary">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Market Summary | Daily Global Markets">
<meta name="twitter:description" content="매일 자동 생성되는 글로벌 시장 요약 보고서">
<meta name="twitter:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<style>
  @import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400&display=swap');
  body {{ font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic','맑은 고딕',sans-serif; background:#f4f5f9; color:#2d3148; padding:40px 24px; max-width:720px; margin:0 auto; }}
  h1 {{ font-size:28px; font-weight:700; margin-bottom:4px; }}
  .sub {{ font-size:14px; color:#7c8298; margin-bottom:24px; }}
  .main-tabs {{ display:flex; gap:0; margin-bottom:24px; border-bottom:2px solid #e0e3ed; }}
  .main-tab {{
    padding:10px 24px; font-size:14px; font-weight:600; color:#7c8298; background:none;
    border:none; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px;
    transition:all .2s; font-family:inherit;
  }}
  .main-tab:hover {{ color:#2d3148; }}
  .main-tab.active {{ color:#F58220; border-bottom-color:#F58220; }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}
  .month-bar {{ display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }}
  .month-btn {{
    padding:6px 14px; border:1px solid #e0e3ed; border-radius:16px;
    background:#fff; color:#7c8298; font-size:12px; font-weight:600;
    cursor:pointer; transition:all .15s; font-family:inherit;
  }}
  .month-btn:hover {{ border-color:#F58220; color:#F58220; }}
  .month-btn.active {{ background:#F58220; color:#fff; border-color:#F58220; }}
  .sub-panel {{ display:none; }}
  .sub-panel.active {{ display:block; }}
  ul {{ list-style:none; padding:0; }}
  li {{ margin-bottom:8px; }}
  li a {{
    display:block; padding:12px 18px; background:#fff; border:1px solid #e0e3ed;
    border-radius:10px; text-decoration:none; color:#2d3148; font-size:14px;
    font-weight:500; transition:all .15s; box-shadow:0 1px 3px rgba(0,0,0,0.04);
    font-family:'JetBrains Mono','Spoqa Han Sans Neo',monospace;
  }}
  li a:hover {{ border-color:#F58220; color:#F58220; transform:translateX(4px); }}
</style>
</head>
<body>
  <h1>Market Summary</h1>
  <p class="sub">Auto-generated market reports · Updated daily before 08:30 KST</p>

  <div class="main-tabs">
    <button class="main-tab active" onclick="showTab('daily')">Daily</button>
    <button class="main-tab" onclick="showTab('weekly')">Weekly</button>
    <button class="main-tab" onclick="showTab('monthly')">Monthly</button>
  </div>

  <div id="tab-daily" class="tab-content active">
    <div class="month-bar">
{daily_month_btns}    </div>
{daily_panels}
  </div>

  <div id="tab-weekly" class="tab-content">
    <div class="month-bar">
{weekly_month_btns}    </div>
{weekly_panels}
  </div>

  <div id="tab-monthly" class="tab-content">
    <ul>
{monthly_items if monthly_items else '      <li style="color:#7c8298;font-style:italic">No monthly reports yet.</li>'}
    </ul>
  </div>

  <script>
  function showTab(id) {{
    document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.main-tab').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-'+id).classList.add('active');
    event.target.classList.add('active');
  }}
  function showSub(tab, key) {{
    const container = document.getElementById('tab-'+tab);
    container.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
    container.querySelectorAll('.month-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tab+'-'+key).classList.add('active');
    event.target.classList.add('active');
  }}
  </script>
</body>
</html>"""

    idx_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(idx_path, "w") as f:
        f.write(index_html)
    print(f"Index saved: {idx_path}")


def build_report_data(target_date):
    """history/market_data.csv 에서 읽어 지표를 계산하여 보고서 데이터 dict 반환.

    신규 스키마: DATE, INDICATOR_CODE, CATEGORY, TICKER, CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE
    구 스키마(date,category,ticker,close) 도 하위호환으로 읽어들임.
    """
    import pandas as pd

    df = pd.read_csv(HISTORY_CSV)
    # 하위호환: 구 소문자 헤더를 대문자로 정규화
    rename_map = {}
    for col in df.columns:
        u = col.upper()
        if u in ("DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
                 "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE"):
            rename_map[col] = u
    if rename_map:
        df = df.rename(columns=rename_map)

    df["DATE"] = pd.to_datetime(df["DATE"])
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
    import csv as _csv
    os.makedirs(HISTORY_DIR, exist_ok=True)
    file_exists = os.path.exists(HISTORY_CSV) and os.path.getsize(HISTORY_CSV) > 0

    # Load existing (DATE, INDICATOR_CODE) keys for dedup
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
        """가격 컬럼(CLOSE/OPEN/HIGH/LOW)은 항상 3자리로 포맷."""
        if v is None or v == "":
            return ""
        try:
            return f"{round(float(v), 3):.3f}"
        except (TypeError, ValueError):
            return ""

    def _vol(v):
        """VOLUME 은 정수. 없으면 공백."""
        if v is None or v == "":
            return ""
        try:
            return str(int(round(float(v))))
        except (TypeError, ValueError):
            return ""

    def _text(v):
        """문자열 컬럼."""
        if v is None:
            return ""
        return str(v)

    new_rows = []
    for row in history_rows:
        if len(row) != 10:
            continue  # 방어적: 구 포맷 튜플 무시
        d, code, cat, tk, close, o, h, l, vol, src = row
        if not code:
            continue  # MKT000 매핑 없는 행 스킵
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


def main(target_date=None, start_date=None):
    """일간 리포트 생성.

    Args:
        target_date: 'YYYY-MM-DD'. None 이면 전 영업일.
        start_date:  수집 시작일. None 이면 fetch_data 기본값 (target-200일).
                     재수집 용도로 사용: main(target_date='2026-04-09', start_date='2025-01-01').
    """
    if not target_date:
        target_date = str(prev_business_day())

    print("=== Daily Market Summary Generator ===")
    if start_date:
        print(f"Collecting {start_date} ~ {target_date}")
    else:
        print(f"Target date: {target_date}")

    # Step 1: API 에서 원시 데이터 수집 → CSV 에 축적
    _, history_rows = fetch_data(start_date=start_date, end_date=target_date)
    append_to_history(history_rows)
    print(f"History updated: {HISTORY_CSV}")

    # Step 1b: Snowflake MKT100_MARKET_DAILY dual-write (best-effort)
    #   - 일간 실행: target_date 한 날짜만 DELETE 후 INSERT.
    #   - 전체 재수집(--start) 시엔 별도 snowflake_loader.py --truncate 로 벌크 적재.
    #   - Snowflake 실패해도 CSV 는 이미 저장됐으므로 진행.
    if history_rows and not start_date:
        try:
            import pandas as pd
            df_hist = pd.DataFrame(history_rows, columns=HISTORY_CSV_COLUMNS)
            from snowflake_loader import upsert_rows
            upsert_rows(df_hist, target_date=target_date)
            print(f"Snowflake MKT100_MARKET_DAILY updated for {target_date}")
        except Exception as e:
            print(f"[WARN] Snowflake upsert 실패 (CSV 는 저장됨): {e}")

    # Step 2: CSV에서 메트릭 계산
    data = build_report_data(target_date)

    # 월별 폴더에 저장
    month_dir = os.path.join(OUTPUT_DIR, target_date[:7])
    os.makedirs(month_dir, exist_ok=True)

    json_path = os.path.join(month_dir, f"{target_date}_data.json")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Data saved: {json_path}")

    html, report_date = generate_html(data)

    html_path = os.path.join(month_dir, f"{report_date}.html")
    _inject_existing_story(html_path, html)
    print(f"Report saved: {html_path}")

    # 당일이 포함된 주간/월간 보고서 자동 갱신 (index보다 먼저 — index는 weekly HTML의 date range를 파싱함)
    update_current_periodic(target_date)

    generate_index()

    return html_path


def update_current_periodic(target_date):
    """target_date가 포함된 주간 및 월간 보고서를 갱신"""
    try:
        from generate_periodic import (
            load_market_data, get_week_ranges, aggregate_period,
            generate_periodic_html
        )

        td = dt.datetime.strptime(target_date, "%Y-%m-%d").date()
        year = td.year

        market_data, trading_days = load_market_data()

        # ── 당일 포함 주간 보고서 갱신 ──
        iso = td.isocalendar()
        iso_week = iso[1]
        weeks = get_week_ranges(trading_days, year)
        week_key = (iso[0], iso_week)

        if week_key in weeks:
            dates = weeks[week_key]
            agg = aggregate_period(market_data, trading_days, dates)
            if agg:
                first, last = agg["first"], agg["last"]
                n_days = len(agg["dates"])
                week_label = f"W{iso_week:02d}"
                title = f"Weekly Summary | {year} {week_label}"
                subtitle = f"{first} ~ {last} ({n_days} trading days)"
                filename = f"{year}-W{iso_week:02d}.html"

                weekly_dir = os.path.join(OUTPUT_DIR, "weekly")
                os.makedirs(weekly_dir, exist_ok=True)
                html = generate_periodic_html(agg, title, subtitle, "Weekly", filename)
                path = os.path.join(weekly_dir, filename)

                # 기존 Story 보존
                _inject_existing_story(path, html)
                print(f"Weekly updated: {filename}")

        # ── 당일 포함 월간 보고서 갱신 ──
        month_str = target_date[:7]
        month_dates = sorted([d for d in trading_days if d.startswith(month_str)])
        if month_dates:
            agg = aggregate_period(market_data, trading_days, month_dates)
            if agg:
                month_name = td.strftime("%B")
                title = f"Monthly Summary | {year} {month_name}"
                subtitle = f"{month_dates[0]} ~ {month_dates[-1]} ({len(month_dates)} trading days)"
                filename = f"{year}-{td.month:02d}.html"

                monthly_dir = os.path.join(OUTPUT_DIR, "monthly")
                os.makedirs(monthly_dir, exist_ok=True)
                html = generate_periodic_html(agg, title, subtitle, "Monthly", filename)
                path = os.path.join(monthly_dir, filename)

                _inject_existing_story(path, html)
                print(f"Monthly updated: {filename}")

    except Exception as e:
        print(f"[WARN] Periodic update failed: {e}")


def _inject_existing_story(path, new_html):
    """기존 파일에 Story가 있으면 새 HTML의 placeholder에 주입 + Story를 별도 파일로 저장"""
    import re
    old_story = ""
    if os.path.exists(path):
        with open(path) as f:
            old_content = f.read()
        # tab-story 내용 추출 (class="tab-panel" 또는 "tab-panel active" 모두 허용)
        m = re.search(
            r'<div id="tab-story" class="tab-panel(?: active)?">\s*\n(.*?)\n</div><!-- /tab-story -->',
            old_content, re.DOTALL
        )
        if m:
            story_content = m.group(1).strip()
            if story_content and "STORY_CONTENT_PLACEHOLDER" not in story_content:
                old_story = story_content
    # path 본문에 스토리가 없으면 sibling `_story.html` 에서 복원 시도
    if not old_story:
        base, ext = os.path.splitext(path)
        sibling = f"{base}_story{ext}"
        if os.path.exists(sibling):
            with open(sibling) as f:
                sib_story = f.read().strip()
            if sib_story and "STORY_CONTENT_PLACEHOLDER" not in sib_story:
                old_story = sib_story

    if old_story:
        new_html = new_html.replace("<!-- STORY_CONTENT_PLACEHOLDER -->", old_story)

    with open(path, "w") as f:
        f.write(new_html)

    # Story를 별도 파일로 저장
    _save_story_file(path, new_html)


def _save_story_file(html_path, html_content):
    """HTML에서 Story 콘텐츠를 추출하여 _story.html 파일로 저장"""
    import re
    m = re.search(
        r'<div id="tab-story" class="tab-panel(?: active)?">\s*\n(.*?)\n</div><!-- /tab-story -->',
        html_content, re.DOTALL
    )
    if not m:
        return
    story = m.group(1).strip()
    if not story or "STORY_CONTENT_PLACEHOLDER" in story:
        return

    # _story.html 경로 생성: YYYY-MM-DD.html → YYYY-MM-DD_story.html
    base, ext = os.path.splitext(html_path)
    story_path = f"{base}_story{ext}"

    with open(story_path, "w") as f:
        f.write(story)
    print(f"  Story saved: {os.path.basename(story_path)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Market Summary daily generator")
    parser.add_argument("target_date", nargs="?", default=None,
                        help="보고서 기준일 YYYY-MM-DD (기본: 전 영업일)")
    parser.add_argument("--start", dest="start_date", default=None,
                        help="수집 시작일 YYYY-MM-DD (전체 재수집 용)")
    args = parser.parse_args()
    path = main(target_date=args.target_date, start_date=args.start_date)
    print(f"\nDone! Open: file://{path}")
