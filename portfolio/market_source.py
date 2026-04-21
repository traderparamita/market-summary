"""Snowflake 기반 시장 데이터 소스.

MKT100_MARKET_DAILY (FDE_DB.PUBLIC) 를 단일 소스로 하는 reader 유틸.
기존 `pd.read_csv('history/market_data.csv')` 를 대체한다.

Schema:
    Snowflake 테이블은 한글 컬럼(일자/지표코드/...), 이 모듈은 영문 대문자(DATE/INDICATOR_CODE/...)
    로 renormalize 해서 반환하므로 기존 CSV 소비자와 호환된다.

기본 사용법:
    from portfolio.market_source import load_long, load_wide_close

    # Long format (CSV 와 동일 스키마)
    df = load_long(start="2020-01-01")

    # Wide CLOSE pivot (scoring / correlation 계열이 선호)
    wide = load_wide_close(start="2020-01-01", codes=["EQ_KOSPI", "EQ_SP500"])

CSV fallback:
    `prefer="snowflake"` (기본) — Snowflake 우선, 실패 시 CSV fallback.
    `prefer="csv"` — CSV 우선 (시뮬레이션/테스트용).
    `SNOWFLAKE_DISABLE=1` 환경변수로 전역 비활성화 가능.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "history" / "market_data.csv"

# Snowflake 한글 컬럼 → CSV 영문 대문자 컬럼 (read 시 rename)
_SF_TO_CSV = {
    "일자": "DATE",
    "지표코드": "INDICATOR_CODE",
    "카테고리": "CATEGORY",
    "티커": "TICKER",
    "종가": "CLOSE",
    "시가": "OPEN",
    "고가": "HIGH",
    "저가": "LOW",
    "거래량": "VOLUME",
    "소스": "SOURCE",
}

_CSV_COLUMNS = list(_SF_TO_CSV.values())


def _snowflake_disabled() -> bool:
    return os.environ.get("SNOWFLAKE_DISABLE", "").strip() in ("1", "true", "TRUE", "yes")


def _load_from_snowflake(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    from snowflake_loader import get_connection

    where = []
    params: list = []
    if start:
        where.append('"일자" >= %s')
        params.append(start)
    if end:
        where.append('"일자" <= %s')
        params.append(end)
    if codes:
        codes_list = list(codes)
        if codes_list:
            placeholders = ", ".join(["%s"] * len(codes_list))
            where.append(f'"지표코드" IN ({placeholders})')
            params.extend(codes_list)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    sql = f"""
        SELECT "일자", "지표코드", "카테고리", "티커",
               "종가", "시가", "고가", "저가", "거래량", "소스"
        FROM FDE_DB.PUBLIC.MKT100_MARKET_DAILY
        {where_sql}
        ORDER BY "일자", "지표코드"
    """

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        col_names = [c[0] for c in cur.description]
        df = pd.DataFrame(rows, columns=col_names)
    finally:
        conn.close()

    df = df.rename(columns=_SF_TO_CSV)
    df["DATE"] = pd.to_datetime(df["DATE"])
    for col in ("CLOSE", "OPEN", "HIGH", "LOW"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "VOLUME" in df.columns:
        df["VOLUME"] = pd.to_numeric(df["VOLUME"], errors="coerce")
    return df[_CSV_COLUMNS]


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


def load_long(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
    *,
    prefer: str = "snowflake",
) -> pd.DataFrame:
    """Long format DataFrame (CSV 스키마와 동일).

    Args:
        start: 'YYYY-MM-DD' inclusive. None 이면 제한 없음.
        end:   'YYYY-MM-DD' inclusive.
        codes: 지표코드 필터 (예: ["EQ_KOSPI","EQ_SP500"]).
        prefer: "snowflake" (기본) 또는 "csv".

    Returns:
        DataFrame with columns: DATE, INDICATOR_CODE, CATEGORY, TICKER,
                                CLOSE, OPEN, HIGH, LOW, VOLUME, SOURCE
    """
    if prefer == "csv" or _snowflake_disabled():
        return _load_from_csv(start, end, codes)
    try:
        return _load_from_snowflake(start, end, codes)
    except Exception as e:
        print(f"[market_source] Snowflake 실패 → CSV fallback: {str(e)[:200]}")
        return _load_from_csv(start, end, codes)


def load_wide_close(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
    *,
    prefer: str = "snowflake",
) -> pd.DataFrame:
    """Wide format: DATE index × INDICATOR_CODE columns, CLOSE values.

    scoring / correlation / regime 계열이 주로 쓰는 포맷.
    """
    long = load_long(start=start, end=end, codes=codes, prefer=prefer)
    if long.empty:
        return pd.DataFrame()
    wide = long.pivot_table(
        index="DATE", columns="INDICATOR_CODE", values="CLOSE", aggfunc="last"
    )
    return wide.sort_index()


_MACRO_COLUMNS = ["DATE", "INDICATOR_CODE", "CATEGORY", "REGION", "VALUE", "UNIT", "SOURCE"]


def _empty_macro_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_MACRO_COLUMNS)


def load_macro_long(
    start: Optional[str] = None,
    end: Optional[str] = None,
    codes: Optional[Iterable[str]] = None,
    *,
    prefer: str = "snowflake",
) -> pd.DataFrame:
    """MKT200_MACRO_DAILY (매크로 지표) 읽기. macro_indicators.csv 대체.

    Snowflake MKT200 이 비어 있으면 자동으로 CSV fallback.
    Returns columns: DATE, INDICATOR_CODE, CATEGORY, REGION, VALUE, UNIT, SOURCE
    (비어 있어도 빈 DataFrame 을 돌려주며, 빈 df 도 expected columns 보유)
    """
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

    if prefer == "csv" or _snowflake_disabled():
        return _from_csv()

    try:
        from snowflake_loader import get_connection
        where = []
        params: list = []
        if start:
            where.append('"일자" >= %s')
            params.append(start)
        if end:
            where.append('"일자" <= %s')
            params.append(end)
        if codes:
            codes_list = list(codes)
            placeholders = ", ".join(["%s"] * len(codes_list))
            where.append(f'"지표코드" IN ({placeholders})')
            params.extend(codes_list)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        sql = f"""
            SELECT "일자" AS DATE, "지표코드" AS INDICATOR_CODE,
                   "카테고리" AS CATEGORY, "지역" AS REGION,
                   "값" AS VALUE, "단위" AS UNIT, "소스" AS SOURCE
            FROM FDE_DB.PUBLIC.MKT200_MACRO_DAILY
            {where_sql}
            ORDER BY "일자", "지표코드"
        """
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            col_names = [c[0] for c in cur.description]
            df = pd.DataFrame(rows, columns=col_names)
        finally:
            conn.close()

        if df.empty:
            # MKT200 이 아직 비어 있으면 CSV fallback
            print("[market_source] MKT200 empty → macro CSV fallback")
            return _from_csv()

        df["DATE"] = pd.to_datetime(df["DATE"])
        df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce")
        return df
    except Exception as e:
        print(f"[market_source] MKT200 실패 → CSV fallback: {str(e)[:200]}")
        return _from_csv()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Snowflake market data reader smoke test")
    parser.add_argument("--start", default="2026-04-15")
    parser.add_argument("--end", default="2026-04-20")
    parser.add_argument("--codes", nargs="*", default=None)
    parser.add_argument("--wide", action="store_true")
    args = parser.parse_args()

    if args.wide:
        df = load_wide_close(args.start, args.end, args.codes)
        print(df)
    else:
        df = load_long(args.start, args.end, args.codes)
        print(df.head(20))
        print(f"...\ntotal rows: {len(df)}")
