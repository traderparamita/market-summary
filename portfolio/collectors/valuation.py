"""KOSPI PER/PBR/배당수익률 수집 (pykrx).

pykrx로 KOSPI 지수의 PER/PBR/배당수익률 시계열을 수집하여 market_data.csv에 추가한다.
Valuation Agent가 KR 시장의 밸류에이션 수준을 판단하는 데 사용.

Usage:
    python -m portfolio.collectors.valuation --start 2010-01-01
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from pykrx import stock  # noqa: E402

from portfolio.io import load_csv_dedup, append_save_csv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MARKET_CSV = ROOT / "history" / "market_data.csv"

VALUATION_TARGETS: list[tuple[str, str, str]] = [
    ("VAL_KR_PER", "valuation", "KOSPI PER"),
    ("VAL_KR_PBR", "valuation", "KOSPI PBR"),
    ("VAL_KR_DY",  "valuation", "KOSPI 배당수익률"),
]

COL_MAP = {
    "VAL_KR_PER": "PER",
    "VAL_KR_PBR": "PBR",
    "VAL_KR_DY":  "배당수익률",
}


def fetch_kospi_fundamental(start: str, end: str) -> pd.DataFrame | None:
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    frames = []
    year = start_dt.year
    while year <= end_dt.year:
        y_start = max(start_dt, pd.Timestamp(f"{year}-01-01")).strftime("%Y%m%d")
        y_end = min(end_dt, pd.Timestamp(f"{year}-12-31")).strftime("%Y%m%d")
        try:
            df = stock.get_index_fundamental_by_date(y_start, y_end, "1001")
            if not df.empty:
                frames.append(df)
        except Exception as e:
            print(f"    [ERR] KOSPI fundamental {year}: {e}")
        year += 1
        time.sleep(0.3)

    if not frames:
        return None

    result = pd.concat(frames)
    result = result[~result.index.duplicated(keep="last")]
    result = result.sort_index()
    result.index.name = "DATE"
    return result


def collect_valuation(start: str = "2010-01-01", end: str = "9999-12-31") -> int:
    market_cols = ["DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
                   "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE"]
    existing, existing_set = load_csv_dedup(MARKET_CSV, market_cols, parse_dates=True)

    if end == "9999-12-31":
        end = pd.Timestamp.today().strftime("%Y-%m-%d")

    print(f"  KOSPI PER/PBR/DY 수집: {start} ~ {end}")
    raw = fetch_kospi_fundamental(start, end)
    if raw is None or raw.empty:
        print("  → 데이터 없음")
        return 0

    new_rows: list[dict] = []
    for code, category, ticker in VALUATION_TARGETS:
        col = COL_MAP[code]
        if col not in raw.columns:
            print(f"  {code}: '{col}' column not found in {list(raw.columns)}")
            continue

        added = 0
        for dt, row in raw.iterrows():
            key = (dt.strftime("%Y-%m-%d"), code)
            if key in existing_set:
                continue
            val = row[col]
            if pd.isna(val) or val == 0:
                continue
            new_rows.append({
                "DATE": dt.date(),
                "INDICATOR_CODE": code,
                "CATEGORY": category,
                "TICKER": ticker,
                "CLOSE": round(float(val), 4),
                "OPEN": None,
                "HIGH": None,
                "LOW": None,
                "VOLUME": None,
                "SOURCE": "pykrx",
            })
            existing_set.add(key)
            added += 1
        print(f"  {code:20s}: {added}행 추가")

    n = append_save_csv(MARKET_CSV, existing, new_rows, sort_cols=("INDICATOR_CODE", "DATE"))
    if n:
        print(f"\n  → market_data.csv 업데이트: {n}행 추가")
    else:
        print("\n  → 신규 데이터 없음")

    # Snowflake dual-write (best-effort)
    try:
        from snowflake_loader import sync_new_rows
        sync_new_rows(new_rows, source="collect_valuation")
    except Exception as e:
        print(f"[SNOWFLAKE] FAILED source=collect_valuation reason={str(e)[:200]}")

    return len(new_rows)


def main():
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="KOSPI PER/PBR/배당수익률 수집")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default=today)
    args = parser.parse_args()

    print(f"Valuation 수집: {args.start} ~ {args.end}")
    n = collect_valuation(args.start, args.end)
    print(f"완료: {n}행")


if __name__ == "__main__":
    main()
