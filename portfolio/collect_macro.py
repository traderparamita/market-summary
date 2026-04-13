"""Macro indicators collector.

Fetches macro economic indicators from FRED and ECOS APIs,
appends to history/macro_indicators.csv.

Usage:
    python -m portfolio.collect_macro --start 2010-01-01
    python -m portfolio.collect_macro --start 2010-01-01 --snowflake  # Also upload to Snowflake
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
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = df["value"].astype(float)
        return df[["date", "value"]].rename(columns={"date": "DATE", "value": "raw_value"})

    except Exception as e:
        print(f"  ERROR fetching {series_id}: {e}")
        return pd.DataFrame()


def fetch_ecos_series(series_id: str, start_date: str) -> pd.DataFrame:
    """Fetch data from ECOS API (placeholder - needs ECOS-specific implementation)."""
    if not ECOS_API_KEY:
        print(f"  WARNING: ECOS_API_KEY not set, skipping {series_id}")
        return pd.DataFrame()

    # TODO: Implement ECOS API call
    # ECOS API는 통계표별로 엔드포인트가 다르므로 series_id를 파싱해서 적절한 호출 필요
    print(f"  WARNING: ECOS fetch not yet implemented for {series_id}")
    return pd.DataFrame()


def transform_series(df: pd.DataFrame, transform: str) -> pd.DataFrame:
    """Apply transformation to raw values."""
    if df.empty:
        return df

    df = df.sort_values("DATE").reset_index(drop=True)

    if transform == "none" or transform == "value":
        df["VALUE"] = df["raw_value"]

    elif transform == "pct_change":
        df["VALUE"] = df["raw_value"].pct_change() * 100

    elif transform == "pct_change_yoy":
        df["VALUE"] = df["raw_value"].pct_change(periods=4) * 100  # Quarterly data -> YoY

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

    print(f"  Fetching {code} ({source}/{series_id}) ...")

    if source == "FRED":
        df = fetch_fred_series(series_id, start_date)
    elif source == "ECOS":
        df = fetch_ecos_series(series_id, start_date)
    else:
        print(f"  WARNING: Unknown source '{source}'")
        return pd.DataFrame()

    if df.empty:
        return df

    df = transform_series(df, transform)

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

    # Load existing CSV to find dates already present
    existing = pd.DataFrame(columns=CSV_COLUMNS)
    if HISTORY_CSV.exists():
        existing = pd.read_csv(HISTORY_CSV)
        existing_keys = set(zip(existing["DATE"], existing["INDICATOR_CODE"]))
        print(f"Existing CSV: {len(existing)} rows")
    else:
        existing_keys = set()
        print("Creating new CSV")

    all_new = []
    for code, info in indicators.items():
        df = collect_indicator(code, info, args.start)
        if df.empty:
            continue

        # Filter out dates already in CSV
        before = len(df)
        df = df[~df.apply(lambda r: (r["DATE"], r["INDICATOR_CODE"]) in existing_keys, axis=1)]
        print(f"    Fetched {before} rows, {len(df)} new")
        all_new.append(df)

    if not all_new:
        print("\nNo new data to add.")
        return

    new_df = pd.concat(all_new, ignore_index=True)
    print(f"\nTotal new rows: {len(new_df)}")

    # Append to CSV
    if HISTORY_CSV.exists():
        new_df.to_csv(HISTORY_CSV, mode="a", header=False, index=False)
    else:
        new_df.to_csv(HISTORY_CSV, index=False)

    total = len(existing) + len(new_df)
    print(f"CSV updated: {total} total rows")

    # Sort CSV by DATE, INDICATOR_CODE
    print("Sorting CSV ...")
    full = pd.read_csv(HISTORY_CSV)
    full = full.sort_values(["DATE", "INDICATOR_CODE"]).reset_index(drop=True)
    full.to_csv(HISTORY_CSV, index=False)
    print(f"CSV sorted: {len(full)} rows")

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
