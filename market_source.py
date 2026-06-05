"""RDS PostgreSQL 기반 시장 데이터 소스.

market_daily / macro_daily (RDS PostgreSQL) 를 단일 소스로 하는 reader 유틸.
기존 `pd.read_csv('history/market_data.csv')` 및 Snowflake reader를 대체한다.

기본 사용법:
    from market_source import load_long, load_wide_close

    df = load_long(start="2020-01-01")
    wide = load_wide_close(start="2020-01-01", codes=["EQ_KOSPI", "EQ_SP500"])

Fallback:
    RDS 접속 실패 시 자동으로 CSV fallback.
    RDS_DISABLE=1 환경변수로 전역 비활성화 가능.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "history" / "market_data.csv"

_CSV_COLUMNS = ["DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
                "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE"]
_MACRO_COLUMNS = ["DATE", "INDICATOR_CODE", "CATEGORY", "REGION", "VALUE", "UNIT", "SOURCE"]


def _rds_disabled() -> bool:
    return os.environ.get("RDS_DISABLE", "").strip() in ("1", "true", "TRUE", "yes")


# ── RDS reader ──────────────────────────────────────────────────────────────

def _load_from_rds(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    from rds_loader import get_connection

    where, params = [], []
    if start:
        where.append("date >= %s"); params.append(start)
    if end:
        where.append("date <= %s"); params.append(end)
    if codes:
        codes_list = list(codes)
        if codes_list:
            where.append("indicator_code = ANY(%s)"); params.append(codes_list)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT date, indicator_code, category, ticker,
               close, open, high, low, volume, source
        FROM market_daily
        {where_sql}
        ORDER BY date, indicator_code
    """
    conn = get_connection()
    try:
        df = pd.read_sql(sql, conn, params=params if params else None, parse_dates=["date"])
    finally:
        conn.close()

    df.columns = [c.upper() for c in df.columns]
    for col in ("CLOSE", "OPEN", "HIGH", "LOW"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "VOLUME" in df.columns:
        df["VOLUME"] = pd.to_numeric(df["VOLUME"], errors="coerce")
    return df[_CSV_COLUMNS]


def _load_macro_from_rds(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    from rds_loader import get_connection

    where, params = [], []
    if start:
        where.append("date >= %s"); params.append(start)
    if end:
        where.append("date <= %s"); params.append(end)
    if codes:
        codes_list = list(codes)
        if codes_list:
            where.append("indicator_code = ANY(%s)"); params.append(codes_list)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT date, indicator_code, category, region, value, unit, source
        FROM macro_daily
        {where_sql}
        ORDER BY date, indicator_code
    """
    conn = get_connection()
    try:
        df = pd.read_sql(sql, conn, params=params if params else None, parse_dates=["date"])
    finally:
        conn.close()

    df.columns = [c.upper() for c in df.columns]
    if "VALUE" in df.columns:
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")
    return df


# ── CSV fallback ─────────────────────────────────────────────────────────────

def _load_from_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["DATE"])
    if codes is not None:
        df = df[df["INDICATOR_CODE"].isin(list(codes))]
    if start:
        df = df[df["DATE"] >= pd.Timestamp(start)]
    if end:
        df = df[df["DATE"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


def _empty_macro_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_MACRO_COLUMNS)


# ── Public API ───────────────────────────────────────────────────────────────

def load_long(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
    *,
    prefer: str = "rds",
) -> pd.DataFrame:
    """Long format DataFrame.

    Args:
        start: 'YYYY-MM-DD' inclusive.
        end:   'YYYY-MM-DD' inclusive.
        codes: 지표코드 필터 (예: ["EQ_KOSPI","EQ_SP500"]).
        prefer: "rds" (기본) 또는 "csv".

    Returns:
        DataFrame with columns: DATE, INDICATOR_CODE, CATEGORY, TICKER,
                                CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE
    """
    if prefer == "csv" or _rds_disabled():
        return _load_from_csv(start, end, codes)
    try:
        return _load_from_rds(start, end, codes)
    except Exception as e:
        print(f"[market_source] RDS 실패 → CSV fallback: {str(e)[:200]}")
        return _load_from_csv(start, end, codes)


def load_wide_close(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
    *,
    prefer: str = "rds",
) -> pd.DataFrame:
    """Wide format: DATE index × INDICATOR_CODE columns, CLOSE values."""
    long = load_long(start=start, end=end, codes=codes, prefer=prefer)
    if long.empty:
        return pd.DataFrame()
    wide = long.pivot_table(
        index="DATE", columns="INDICATOR_CODE", values="CLOSE", aggfunc="last"
    )
    return wide.sort_index()


def load_macro_long(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
    *,
    prefer: str = "rds",
) -> pd.DataFrame:
    """macro_daily 읽기. macro_indicators.csv 대체."""
    csv_path = ROOT / "history" / "macro_indicators.csv"

    def _from_csv() -> pd.DataFrame:
        if not csv_path.exists():
            return _empty_macro_df()
        df = pd.read_csv(csv_path, parse_dates=["DATE"])
        if codes is not None:
            df = df[df["INDICATOR_CODE"].isin(list(codes))]
        if start:
            df = df[df["DATE"] >= pd.Timestamp(start)]
        if end:
            df = df[df["DATE"] <= pd.Timestamp(end)]
        return df.reset_index(drop=True)

    if prefer == "csv" or _rds_disabled():
        return _from_csv()
    try:
        df = _load_macro_from_rds(start, end, codes)
        if df.empty:
            print("[market_source] macro_daily empty → CSV fallback")
            return _from_csv()
        return df
    except Exception as e:
        print(f"[market_source] macro_daily RDS 실패 → CSV fallback: {str(e)[:200]}")
        return _from_csv()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="RDS market data reader smoke test")
    parser.add_argument("--start", default="2026-05-01")
    parser.add_argument("--end",   default="2026-05-05")
    parser.add_argument("--codes", nargs="*", default=None)
    parser.add_argument("--wide",  action="store_true")
    parser.add_argument("--csv",   action="store_true")
    args = parser.parse_args()
    prefer = "csv" if args.csv else "rds"

    if args.wide:
        df = load_wide_close(args.start, args.end, args.codes, prefer=prefer)
    else:
        df = load_long(args.start, args.end, args.codes, prefer=prefer)
    print(df.head(20))
    print(f"total rows: {len(df)}")
