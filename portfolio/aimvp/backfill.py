"""Backfill long-term history for AIMVP RiskOn model.

Fetches ACWI, AGG, ^VIX, ^IRX (US 2Y proxy) from yfinance (2010-01-01 ~ 2024-12-31)
and appends to history/market_data.csv + Snowflake MKT100_MARKET_DAILY.

Usage:
    python -m portfolio.aimvp.backfill                 # CSV only
    python -m portfolio.aimvp.backfill --snowflake     # CSV + Snowflake upload
"""

import argparse
import os
import sys
from datetime import date

import pandas as pd
import yfinance as yf

# Project root: portfolio/aimvp/ -> portfolio/ -> root/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)  # Allow importing snowflake_loader from root
HISTORY_CSV = os.path.join(BASE_DIR, "history", "market_data.csv")

BACKFILL_START = "2010-01-01"
BACKFILL_END = "2024-12-31"

# yfinance ticker -> (INDICATOR_CODE, CATEGORY, TICKER_NAME)
TARGETS = {
    "ACWI":  ("EQ_MSCI_ACWI", "equity", "MSCI ACWI"),
    "AGG":   ("BD_AGG",       "bond",   "AGG"),
    "^VIX":  ("RK_VIX",       "risk",   "VIX"),
    "^IRX":  ("BD_US_2Y",     "bond",   "US 2Y"),
}

CSV_COLUMNS = [
    "DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
    "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE",
]


def fetch_and_format(yf_ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch OHLCV from yfinance and format to CSV schema."""
    indicator_code, category, ticker_name = TARGETS[yf_ticker]

    end_dt = pd.Timestamp(end) + pd.offsets.Day(1)
    df = yf.download(yf_ticker, start=start, end=end_dt.strftime("%Y-%m-%d"),
                     auto_adjust=True, progress=False)

    if df.empty:
        print(f"  WARNING: no data for {yf_ticker}")
        return pd.DataFrame(columns=CSV_COLUMNS)

    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)

    rows = []
    for idx, row in df.iterrows():
        d = idx.date() if hasattr(idx, "date") else idx
        if d.weekday() >= 5:
            continue
        close = row.get("Close")
        if pd.isna(close):
            continue
        rows.append({
            "DATE": str(d),
            "INDICATOR_CODE": indicator_code,
            "CATEGORY": category,
            "TICKER": ticker_name,
            "CLOSE": round(float(close), 3),
            "OPEN": round(float(row["Open"]), 3) if pd.notna(row.get("Open")) else None,
            "HIGH": round(float(row["High"]), 3) if pd.notna(row.get("High")) else None,
            "LOW": round(float(row["Low"]), 3) if pd.notna(row.get("Low")) else None,
            "VOLUME": int(row["Volume"]) if pd.notna(row.get("Volume")) and row.get("Volume", 0) > 0 else None,
            "SOURCE": "yfinance",
        })

    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def main():
    parser = argparse.ArgumentParser(description="Backfill AIMVP model data")
    parser.add_argument("--start", default=BACKFILL_START)
    parser.add_argument("--end", default=BACKFILL_END)
    parser.add_argument("--snowflake", action="store_true", help="Also upload to Snowflake")
    args = parser.parse_args()

    # Load existing CSV to find dates already present per indicator
    existing = pd.read_csv(HISTORY_CSV)
    existing_keys = set(zip(existing["DATE"], existing["INDICATOR_CODE"]))
    print(f"Existing CSV: {len(existing)} rows")

    all_new = []
    for yf_ticker in TARGETS:
        indicator_code = TARGETS[yf_ticker][0]
        print(f"\nFetching {yf_ticker} ({indicator_code}) ...")
        df = fetch_and_format(yf_ticker, args.start, args.end)
        if df.empty:
            continue

        # Filter out dates already in CSV
        before = len(df)
        df = df[~df.apply(lambda r: (r["DATE"], r["INDICATOR_CODE"]) in existing_keys, axis=1)]
        print(f"  Fetched {before} rows, {len(df)} new (skipped {before - len(df)} existing)")
        all_new.append(df)

    if not all_new:
        print("\nNo new data to add.")
        return

    new_df = pd.concat(all_new, ignore_index=True)
    print(f"\nTotal new rows: {len(new_df)}")

    # Append to CSV
    new_df.to_csv(HISTORY_CSV, mode="a", header=False, index=False)
    total = len(existing) + len(new_df)
    print(f"CSV updated: {total} total rows")

    # Sort CSV by DATE, INDICATOR_CODE for clean ordering
    print("Sorting CSV ...")
    full = pd.read_csv(HISTORY_CSV)
    full = full.sort_values(["DATE", "INDICATOR_CODE"]).reset_index(drop=True)
    full.to_csv(HISTORY_CSV, index=False)
    print(f"CSV sorted: {len(full)} rows")

    # Snowflake upload
    if args.snowflake:
        print("\nUploading to Snowflake ...")
        try:
            from snowflake_loader import upsert_rows
            n = upsert_rows(new_df)
            print(f"Snowflake: {n} rows upserted")
        except Exception as e:
            print(f"Snowflake upload failed (CSV is safe): {e}")

    # Verify
    verify = pd.read_csv(HISTORY_CSV)
    for yf_ticker, (code, _, _) in TARGETS.items():
        sub = verify[verify["INDICATOR_CODE"] == code]
        print(f"  {code}: {sub['DATE'].min()} ~ {sub['DATE'].max()} ({len(sub)} rows)")


if __name__ == "__main__":
    main()
