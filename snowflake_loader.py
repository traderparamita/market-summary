"""Snowflake 적재 유틸리티.

history/market_data.csv → MKT100_MARKET_DAILY (FDE_DB.PUBLIC)

Usage:
    from snowflake_loader import bulk_load_csv, upsert_rows, get_connection

    # 전체 재적재 (TRUNCATE + insert)
    bulk_load_csv(csv_path, truncate=True)

    # 하루치 덮어쓰기 (특정 일자 DELETE 후 INSERT)
    upsert_rows(rows_dataframe, target_date="2026-04-09")
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TABLE = "MKT100_MARKET_DAILY"

# CSV (English uppercase) → Snowflake (Korean) 컬럼 매핑
COL_MAP = {
    "DATE":           "일자",
    "INDICATOR_CODE": "지표코드",
    "CATEGORY":       "카테고리",
    "TICKER":         "티커",
    "CLOSE":          "종가",
    "OPEN":           "시가",
    "HIGH":           "고가",
    "LOW":            "저가",
    "VOLUME":         "거래량",
    "SOURCE":         "소스",
}


def get_connection():
    """환경변수에서 Snowflake 연결 생성."""
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    )


def _csv_to_df(csv_path: str) -> pd.DataFrame:
    """CSV 를 읽어 Snowflake 컬럼명으로 rename 한 DataFrame 반환."""
    df = pd.read_csv(csv_path)

    # INDICATOR_CODE 없는 행(하위호환 구 CSV 또는 lookup 실패) 제거
    if "INDICATOR_CODE" not in df.columns:
        raise ValueError(f"{csv_path}: INDICATOR_CODE 컬럼이 없습니다. 새 스키마로 재수집이 필요합니다.")
    df = df[df["INDICATOR_CODE"].notna() & (df["INDICATOR_CODE"] != "")]

    df = df.rename(columns=COL_MAP)
    df["일자"] = pd.to_datetime(df["일자"]).dt.date
    for col in ("종가", "시가", "고가", "저가"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["거래량"] = pd.to_numeric(df["거래량"], errors="coerce")

    # Nullable int for 거래량: write_pandas 는 NaN→NULL 처리. 그대로 둬도 OK.
    cols = ["일자", "지표코드", "카테고리", "티커",
            "종가", "시가", "고가", "저가", "거래량", "소스"]
    return df[cols]


def bulk_load_csv(csv_path: str, *, truncate: bool = False) -> int:
    """CSV 전체를 MKT100_MARKET_DAILY 에 벌크 적재.

    Args:
        csv_path:  history/market_data.csv 경로
        truncate:  True 이면 기존 테이블 전체 TRUNCATE 후 INSERT

    Returns:
        적재된 행 수
    """
    df = _csv_to_df(csv_path).reset_index(drop=True)
    print(f"[loader] rows to upload: {len(df)}")

    conn = get_connection()
    try:
        cur = conn.cursor()
        if truncate:
            cur.execute(f"TRUNCATE TABLE {TABLE}")
            print(f"[loader] TRUNCATE {TABLE}")

        success, nchunks, nrows, _ = write_pandas(
            conn, df, TABLE,
            quote_identifiers=True,   # 한글 컬럼명 쿼팅
            chunk_size=10000,
        )
        print(f"[loader] write_pandas: success={success} chunks={nchunks} rows={nrows}")

        cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
        total = cur.fetchone()[0]
        print(f"[loader] {TABLE} total rows now: {total}")
        return nrows
    finally:
        conn.close()


def upsert_rows(df: pd.DataFrame, *, target_date: Optional[str] = None) -> int:
    """일간 대체 적재.

    target_date 가 주어지면 그 날짜의 기존 행을 DELETE 후 INSERT.
    없으면 df 에 포함된 일자 전체를 DELETE 후 INSERT.

    Args:
        df:          CSV 포맷 DataFrame (CSV 대문자 컬럼)
        target_date: 'YYYY-MM-DD'. 지정 시 해당 일자만 replace.

    Returns:
        적재된 행 수
    """
    # 포맷 정규화
    if "INDICATOR_CODE" in df.columns:
        df = df.rename(columns=COL_MAP)
    df["일자"] = pd.to_datetime(df["일자"]).dt.date
    df = df[df["지표코드"].notna() & (df["지표코드"] != "")]

    cols = ["일자", "지표코드", "카테고리", "티커",
            "종가", "시가", "고가", "저가", "거래량", "소스"]
    df = df[cols].reset_index(drop=True)

    if target_date:
        df = df[df["일자"].astype(str) == target_date].reset_index(drop=True)
        dates_to_delete = [target_date]
    else:
        dates_to_delete = sorted(set(df["일자"].astype(str).tolist()))

    if df.empty:
        print("[loader] no rows to upsert")
        return 0

    conn = get_connection()
    try:
        cur = conn.cursor()
        if dates_to_delete:
            placeholders = ", ".join(f"'{d}'" for d in dates_to_delete)
            cur.execute(f'DELETE FROM {TABLE} WHERE "일자" IN ({placeholders})')
            print(f"[loader] DELETE rows for {len(dates_to_delete)} date(s)")

        success, nchunks, nrows, _ = write_pandas(
            conn, df, TABLE,
            quote_identifiers=True,
            chunk_size=10000,
        )
        print(f"[loader] upsert rows={nrows}")
        return nrows
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="market_data.csv → Snowflake MKT100_MARKET_DAILY")
    parser.add_argument("csv", nargs="?", default=os.path.join(BASE_DIR, "history", "market_data.csv"))
    parser.add_argument("--truncate", action="store_true", help="적재 전 TRUNCATE")
    args = parser.parse_args()
    bulk_load_csv(args.csv, truncate=args.truncate)
