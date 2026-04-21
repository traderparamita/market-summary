"""Macro indicators collector.

Fetches macro economic indicators from FRED and ECOS APIs,
appends to history/macro_indicators.csv.

Usage:
    python -m portfolio.collectors.macro --start 2010-01-01
    python -m portfolio.collectors.macro --start 2010-01-01 --snowflake  # Also upload to Snowflake
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv

from portfolio.io import load_csv_dedup, append_save_csv

# Load environment
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

FRED_API_KEY = os.getenv("FRED_API_KEY")
ECOS_API_KEY = os.getenv("ECOS_API_KEY")

MACRO_YAML = Path(__file__).resolve().parent / "macro_indicators.yaml"
HISTORY_CSV = BASE_DIR / "history" / "macro_indicators.csv"

CSV_COLUMNS = ["DATE", "INDICATOR_CODE", "CATEGORY", "REGION", "VALUE", "UNIT", "SOURCE"]


def load_indicators():
    """Load indicator definitions from YAML."""
    with open(MACRO_YAML) as f:
        config = yaml.safe_load(f)
    return config["indicators"]


def fetch_fred_series(series_id: str, start_date: str) -> pd.DataFrame:
    """Fetch data from FRED API."""
    if not FRED_API_KEY:
        print(f"  WARNING: FRED_API_KEY not set, skipping {series_id}")
        return pd.DataFrame()

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if "observations" not in data:
            print(f"  WARNING: No data for {series_id}")
            return pd.DataFrame()

        obs = data["observations"]
        df = pd.DataFrame(obs)
        df = df[df["value"] != "."]  # Filter missing values
        df["DATE"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["value"] = df["value"].astype(float)
        return df[["DATE", "value"]].rename(columns={"value": "raw_value"})

    except Exception as e:
        print(f"  ERROR fetching {series_id}: {e}")
        return pd.DataFrame()


def fetch_ecos_series(series_id: str, start_date: str, item_code: str = None, cycle: str = "M") -> pd.DataFrame:
    """Fetch data from ECOS API.

    Args:
        series_id: ECOS 통계표 코드 (e.g., "901Y009")
        start_date: 시작일 (YYYY-MM-DD)
        item_code: 항목 코드 (통계표별로 다름)
        cycle: 주기 (Q=분기, M=월, D=일)
    """
    if not ECOS_API_KEY:
        print(f"  WARNING: ECOS_API_KEY not set, skipping {series_id}")
        return pd.DataFrame()

    # Parse start date to ECOS format (YYYYQ1, YYYYMM, or YYYYMMDD)
    start_dt = pd.to_datetime(start_date)
    end_dt = datetime.now()

    if cycle == "Q":
        # Quarterly: YYYYQ1 format
        start_str = f"{start_dt.year}Q{(start_dt.month - 1) // 3 + 1}"
        end_str = f"{end_dt.year}Q{(end_dt.month - 1) // 3 + 1}"
    elif cycle == "M":
        # Monthly: YYYYMM format
        start_str = start_dt.strftime("%Y%m")
        end_str = end_dt.strftime("%Y%m")
    else:
        # Daily: YYYYMMDD format
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

    # ECOS API endpoint
    url = f"http://ecos.bok.or.kr/api/StatisticSearch/{ECOS_API_KEY}/json/kr/1/10000/{series_id}/{cycle}/{start_str}/{end_str}"

    if item_code:
        url += f"/{item_code}"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if "StatisticSearch" not in data or "row" not in data["StatisticSearch"]:
            print(f"  WARNING: No data for {series_id}")
            return pd.DataFrame()

        rows = data["StatisticSearch"]["row"]
        df = pd.DataFrame(rows)

        # Parse TIME column to DATE (always store as YYYY-MM-DD string)
        if cycle == "Q":
            # YYYYQ1 -> quarter-end date as YYYY-MM-DD
            def q_to_date(t):
                year, q = int(t[:4]), int(t[5])
                month = q * 3
                import calendar
                day = calendar.monthrange(year, month)[1]
                return f"{year}-{month:02d}-{day:02d}"
            df["DATE"] = df["TIME"].apply(q_to_date)
        elif cycle == "M":
            # YYYYMM -> first day of month YYYY-MM-DD
            df["DATE"] = pd.to_datetime(df["TIME"], format="%Y%m").dt.strftime("%Y-%m-%d")
        else:
            # YYYYMMDD format
            df["DATE"] = pd.to_datetime(df["TIME"], format="%Y%m%d").dt.strftime("%Y-%m-%d")

        df["raw_value"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
        df = df.dropna(subset=["raw_value"])

        return df[["DATE", "raw_value"]].sort_values("DATE").reset_index(drop=True)

    except Exception as e:
        print(f"  ERROR fetching {series_id}: {e}")
        return pd.DataFrame()


def transform_series(df: pd.DataFrame, transform: str, cycle: str = "M") -> pd.DataFrame:
    """Apply transformation to raw values."""
    if df.empty:
        return df

    df = df.sort_values("DATE").reset_index(drop=True)

    if transform == "none" or transform == "value":
        df["VALUE"] = df["raw_value"]

    elif transform == "pct_change":
        df["VALUE"] = df["raw_value"].pct_change() * 100

    elif transform == "pct_change_yoy":
        # YoY: 12 periods for monthly, 4 periods for quarterly
        periods = 12 if cycle == "M" else 4
        df["VALUE"] = df["raw_value"].pct_change(periods=periods) * 100

    elif transform == "diff":
        df["VALUE"] = df["raw_value"].diff()

    else:
        print(f"  WARNING: Unknown transform '{transform}', using raw value")
        df["VALUE"] = df["raw_value"]

    return df.dropna(subset=["VALUE"])


def collect_indicator(code: str, info: dict, start_date: str) -> pd.DataFrame:
    """Collect single indicator."""
    source = info["source"]
    series_id = info["series_id"]
    category = info["category"]
    region = info["region"]
    unit = info["unit"]
    transform = info.get("transform", "none")
    cycle = info.get("cycle", "M")

    print(f"  Fetching {code} ({source}/{series_id}) ...")

    if source == "FRED":
        df = fetch_fred_series(series_id, start_date)
    elif source == "ECOS":
        item_code = info.get("item_code")
        df = fetch_ecos_series(series_id, start_date, item_code, cycle)
    else:
        print(f"  WARNING: Unknown source '{source}'")
        return pd.DataFrame()

    if df.empty:
        return df

    df = transform_series(df, transform, cycle)

    df["INDICATOR_CODE"] = code
    df["CATEGORY"] = category
    df["REGION"] = region
    df["UNIT"] = unit
    df["SOURCE"] = source

    return df[CSV_COLUMNS]


def main():
    parser = argparse.ArgumentParser(description="Collect macro indicators")
    parser.add_argument("--start", default="2010-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--snowflake", action="store_true", help="Upload to Snowflake")
    args = parser.parse_args()

    indicators = load_indicators()

    existing, existing_keys = load_csv_dedup(HISTORY_CSV, CSV_COLUMNS)
    print(f"Existing CSV: {len(existing)} rows" if not existing.empty else "Creating new CSV")

    all_new = []
    for code, info in indicators.items():
        df = collect_indicator(code, info, args.start)
        if df.empty:
            continue

        before = len(df)
        df = df[~df.apply(lambda r: (str(r["DATE"]), r["INDICATOR_CODE"]) in existing_keys, axis=1)]
        print(f"    Fetched {before} rows, {len(df)} new")
        all_new.append(df)

    if not all_new:
        print("\nNo new data to add.")
        return

    new_df = pd.concat(all_new, ignore_index=True)
    print(f"\nTotal new rows: {len(new_df)}")

    n = append_save_csv(HISTORY_CSV, existing, new_df)
    print(f"CSV updated: {len(existing) + n} total rows")

    # Snowflake upload (TODO)
    if args.snowflake:
        print("\nSnowflake upload not yet implemented")

    # Verify
    verify = pd.read_csv(HISTORY_CSV)
    print("\nIndicator coverage:")
    for code in sorted(verify["INDICATOR_CODE"].unique()):
        sub = verify[verify["INDICATOR_CODE"] == code]
        print(f"  {code}: {sub['DATE'].min()} ~ {sub['DATE'].max()} ({len(sub)} rows)")


if __name__ == "__main__":
    main()
