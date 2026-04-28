"""
US 2Y / 10Y / 10-2 Spread 데이터를 investing.com(investiny)으로 교체하는 백필 스크립트.

- 교체 범위: 2020-01-01 ~ 오늘 (그 이전은 yfinance 원본 유지)
- 대상: history/market_data.csv + Snowflake MKT100_MARKET_DAILY
- BD_US_10_2_SPREAD는 신규 추가 (computed)

사용법:
    .venv/bin/python scripts/backfill_us_yields.py [--dry-run]
"""

import sys
import datetime as dt
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKFILL_START = "01/01/2020"
HISTORY_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "history", "market_data.csv")

INV_IDS = {
    "BD_US_2Y":  (23701, "bond", "US 2Y"),
    "BD_US_10Y": (23705, "bond", "US 10Y"),
}


def fetch_investiny(inv_id: int, from_date: str, to_date: str) -> pd.DataFrame:
    from investiny import historical_data
    data = historical_data(investing_id=inv_id, from_date=from_date, to_date=to_date)
    if not data or not data.get("date"):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y").dt.date
    df = df[df["date"].apply(lambda d: d.weekday() < 5)]  # 주말 제외
    return df


def build_rows(df: pd.DataFrame, indicator_code: str, category: str, name: str) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "DATE": str(r["date"]),
            "INDICATOR_CODE": indicator_code,
            "CATEGORY": category,
            "TICKER": name,
            "CLOSE": round(float(r["close"]), 4),
            "OPEN": round(float(r["open"]), 4) if r.get("open") else None,
            "HIGH": round(float(r["high"]), 4) if r.get("high") else None,
            "LOW": round(float(r["low"]), 4) if r.get("low") else None,
            "VOLUME": 0.0,
            "SOURCE": "investiny",
        })
    return pd.DataFrame(rows)


def compute_spread(df2y: pd.DataFrame, df10y: pd.DataFrame) -> pd.DataFrame:
    m2 = df2y.set_index("date")[["close"]].rename(columns={"close": "c2"})
    m10 = df10y.set_index("date")[["close"]].rename(columns={"close": "c10"})
    merged = m10.join(m2, how="inner")
    merged["spread"] = (merged["c10"] - merged["c2"]).round(4)
    rows = []
    for date, r in merged.iterrows():
        rows.append({
            "DATE": str(date),
            "INDICATOR_CODE": "BD_US_10_2_SPREAD",
            "CATEGORY": "bond",
            "TICKER": "US 10-2 Spread",
            "CLOSE": r["spread"],
            "OPEN": None, "HIGH": None, "LOW": None,
            "VOLUME": 0.0,
            "SOURCE": "computed",
        })
    return pd.DataFrame(rows)


def update_csv(new_rows: pd.DataFrame, dry_run: bool):
    csv_df = pd.read_csv(HISTORY_CSV)
    cutoff = dt.date(2020, 1, 1)

    # 교체 대상 코드
    codes = new_rows["INDICATOR_CODE"].unique().tolist()

    # 2020-01-01 이전 기존 행은 보존
    mask_keep = ~(
        (csv_df["INDICATOR_CODE"].isin(codes)) &
        (pd.to_datetime(csv_df["DATE"]).dt.date >= cutoff)
    )
    kept = csv_df[mask_keep]
    result = pd.concat([kept, new_rows], ignore_index=True)
    result = result.sort_values(["DATE", "INDICATOR_CODE"]).reset_index(drop=True)

    removed = (~mask_keep).sum()
    added = len(new_rows)
    print(f"  CSV: removed {removed} rows, added {added} rows (net {added - removed:+d})")

    if not dry_run:
        result.to_csv(HISTORY_CSV, index=False)
        print(f"  CSV saved: {HISTORY_CSV}")


def update_snowflake(new_rows: pd.DataFrame, dry_run: bool):
    from snowflake_loader import upsert_rows

    # CSV 컬럼명 → Snowflake 컬럼명 변환
    COL_MAP = {
        "DATE": "일자", "INDICATOR_CODE": "지표코드", "CATEGORY": "카테고리",
        "TICKER": "티커", "CLOSE": "종가", "OPEN": "시가", "HIGH": "고가",
        "LOW": "저가", "VOLUME": "거래량", "SOURCE": "소스",
    }
    sf_df = new_rows.rename(columns=COL_MAP)
    sf_df["일자"] = pd.to_datetime(sf_df["일자"]).dt.date

    dates = sorted(sf_df["일자"].astype(str).unique())
    print(f"  Snowflake: {len(sf_df)} rows across {len(dates)} dates")

    if not dry_run:
        n = upsert_rows(sf_df)
        print(f"  Snowflake upserted: {n} rows")


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN (no writes) ===")

    today = dt.date.today().strftime("%m/%d/%Y")
    print(f"Fetching investiny data: {BACKFILL_START} ~ {today}")

    # 1. investiny에서 2Y / 10Y fetch
    raw = {}
    for code, (inv_id, category, name) in INV_IDS.items():
        print(f"  Fetching {name} (id={inv_id})...")
        df = fetch_investiny(inv_id, BACKFILL_START, today)
        print(f"    → {len(df)} rows ({df['date'].min()} ~ {df['date'].max()})")
        raw[code] = (df, category, name)

    # 2. 행 구성
    all_rows = []
    for code, (df, category, name) in raw.items():
        rows = build_rows(df, code, category, name)
        all_rows.append(rows)

    # 3. 10-2 Spread 계산
    df2y = raw["BD_US_2Y"][0]
    df10y = raw["BD_US_10Y"][0]
    spread_rows = compute_spread(df2y, df10y)
    print(f"  Spread: {len(spread_rows)} rows")
    all_rows.append(spread_rows)

    combined = pd.concat(all_rows, ignore_index=True)
    print(f"\nTotal new rows: {len(combined)}")

    # 4. CSV 업데이트
    print("\n--- CSV ---")
    update_csv(combined, dry_run)

    # 5. Snowflake 업데이트
    print("\n--- Snowflake ---")
    update_snowflake(combined, dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
