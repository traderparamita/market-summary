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
        df[col] = pd.to_numeric(df[col], errors="coerce").round(3)
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

    # Enforce NUMBER(18,3) scale on OHLC columns (defensive; DDL already limits)
    for _col in ("종가", "시가", "고가", "저가"):
        if _col in df.columns:
            df[_col] = pd.to_numeric(df[_col], errors="coerce").round(3)

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


def sync_macro_rows(new_rows: list[dict], *, source: str) -> int:
    """macro_indicators CSV rows → MKT200_MACRO_DAILY upsert.

    `new_rows` 는 CSV 컬럼 (DATE/INDICATOR_CODE/CATEGORY/REGION/VALUE/UNIT/SOURCE) 기반.
    MKT200 스키마의 주기/소스_시리즈 는 MKT001 마스터에서 lookup 해 보강한다.
    (DATE, INDICATOR_CODE) 기준 delete+insert.

    표준 마커: [SNOWFLAKE] OK source=... rows=N  또는 FAILED/SKIP.

    Args:
        new_rows: CSV 포맷 row dict 리스트
        source:   호출한 collector 이름 (로그 추적용)

    Returns:
        적재된 행 수 (실패 시 0)
    """
    if not new_rows:
        print(f"[SNOWFLAKE] SKIP source={source} reason=no-new-rows")
        return 0
    try:
        df = pd.DataFrame(new_rows)
        # 컬럼명 한글 치환
        df = df.rename(columns={
            "DATE": "일자", "INDICATOR_CODE": "지표코드", "CATEGORY": "카테고리",
            "REGION": "지역", "VALUE": "값", "UNIT": "단위", "SOURCE": "소스",
        })
        df["일자"] = pd.to_datetime(df["일자"]).dt.date
        df["값"] = pd.to_numeric(df["값"], errors="coerce").round(4)

        conn = get_connection()
        try:
            cur = conn.cursor()
            # MKT001 마스터에서 주기/소스_시리즈 lookup
            cur.execute('SELECT "지표코드", "주기", "소스_시리즈" FROM FDE_DB.PUBLIC.MKT001_MACRO_INDICATOR')
            master = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            df["주기"] = df["지표코드"].map(lambda c: master.get(c, (None, None))[0])
            df["소스_시리즈"] = df["지표코드"].map(lambda c: master.get(c, (None, None))[1])

            cols = ["일자", "지표코드", "카테고리", "지역", "값", "단위",
                    "주기", "소스", "소스_시리즈"]
            df = df[cols].reset_index(drop=True)

            # (일자, 지표코드) 단위 DELETE 후 INSERT
            keys = df[["일자", "지표코드"]].drop_duplicates()
            if len(keys):
                placeholders = ", ".join(f"(TO_DATE('{r.일자}'), '{r.지표코드}')" for r in keys.itertuples())
                cur.execute(f'''
                  DELETE FROM FDE_DB.PUBLIC.MKT200_MACRO_DAILY
                  WHERE ("일자", "지표코드") IN ({placeholders})
                ''')

            success, nchunks, nrows, _ = write_pandas(
                conn, df, "MKT200_MACRO_DAILY",
                quote_identifiers=True, chunk_size=10000,
            )
            print(f"[SNOWFLAKE] OK source={source} rows={nrows}")
            return nrows
        finally:
            conn.close()
    except Exception as e:
        reason = str(e).replace("\n", " ")[:300]
        print(f"[SNOWFLAKE] FAILED source={source} reason={reason}")
        return 0


def sync_new_rows(new_rows: list[dict], *, source: str) -> int:
    """Auxiliary collector 공용 헬퍼.

    `new_rows` 는 CSV 컬럼(DATE/INDICATOR_CODE/...) 기반 dict 리스트.
    upsert_rows 를 호출하고 [SNOWFLAKE] 표준 마커를 출력한다.

    Args:
        new_rows: CSV 포맷 row dict 리스트
        source:   호출한 collector 이름 (로그 추적용)

    Returns:
        적재된 행 수 (실패 시 0)
    """
    if not new_rows:
        print(f"[SNOWFLAKE] SKIP source={source} reason=no-new-rows")
        return 0
    try:
        cols = ["DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
                "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE"]
        df = pd.DataFrame(new_rows, columns=cols)
        n = upsert_rows(df)
        print(f"[SNOWFLAKE] OK source={source} rows={n}")
        return n
    except Exception as e:
        reason = str(e).replace("\n", " ")[:300]
        print(f"[SNOWFLAKE] FAILED source={source} reason={reason}")
        return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="market_data.csv → Snowflake MKT100_MARKET_DAILY")
    parser.add_argument("csv", nargs="?", default=os.path.join(BASE_DIR, "history", "market_data.csv"))
    parser.add_argument("--truncate", action="store_true", help="적재 전 TRUNCATE")
    args = parser.parse_args()
    bulk_load_csv(args.csv, truncate=args.truncate)
