"""RDS PostgreSQL 적재 유틸리티.

history/market_data.csv → market_daily (RDS PostgreSQL)

snowflake_loader.py 와 동일한 public API를 제공한다:
    bulk_load_csv(csv_path, truncate=True)
    upsert_rows(df, target_date="YYYY-MM-DD")
    get_connection()
"""

from __future__ import annotations

import os
from io import StringIO
from typing import Optional

import pandas as pd
import psycopg2
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TABLE = "market_daily"
NULL = r"\N"

_CSV_COLUMNS = ["DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
                "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE"]
_DB_COLUMNS  = ["date", "indicator_code", "category", "ticker",
                "close", "open", "high", "low", "volume", "source"]


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ["RDS_HOST"],
        port=int(os.environ.get("RDS_PORT", 5432)),
        dbname=os.environ["RDS_DB"],
        user=os.environ["RDS_USER"],
        password=os.environ["RDS_PASSWORD"],
        connect_timeout=10,
    )


def _df_to_tsv(df: pd.DataFrame) -> StringIO:
    def safe(val):
        if pd.isna(val):
            return NULL
        return str(val)

    buf = StringIO()
    for _, row in df.iterrows():
        vals = [str(row["DATE"].date()) if pd.notna(row["DATE"]) else NULL]
        vals += [safe(row.get(c)) for c in _CSV_COLUMNS[1:]]
        buf.write("\t".join(vals) + "\n")
    buf.seek(0)
    return buf


def _alert_failure(*, source: str, reason: str, table: str = "") -> None:
    print(f"[RDS] FAILED source={source} reason={reason}")
    try:
        from notify_telegram import send
        send(
            f"⚠ *RDS write 실패*\n"
            f"source: `{source}`\n"
            f"{'table: `' + table + '`' + chr(10) if table else ''}"
            f"reason: `{reason[:300]}`"
        )
    except Exception:
        pass


def bulk_load_csv(csv_path: str, *, truncate: bool = False) -> int:
    """CSV 전체를 market_daily에 적재.

    Args:
        csv_path: market_data.csv 경로
        truncate: True면 TRUNCATE 후 insert, False면 upsert

    Returns:
        적재된 행 수
    """
    df = pd.read_csv(csv_path, parse_dates=["DATE"])
    df = df[[c for c in _CSV_COLUMNS if c in df.columns]]

    conn = get_connection()
    try:
        cur = conn.cursor()
        if truncate:
            cur.execute(f"TRUNCATE {TABLE}")
            buf = _df_to_tsv(df)
            cur.copy_from(buf, TABLE, columns=_DB_COLUMNS, null=NULL)
        else:
            # upsert: 임시 테이블 → INSERT ON CONFLICT
            cur.execute(f"CREATE TEMP TABLE _tmp (LIKE {TABLE}) ON COMMIT DROP")
            buf = _df_to_tsv(df)
            cur.copy_from(buf, "_tmp", columns=_DB_COLUMNS, null=NULL)
            cur.execute(f"""
                INSERT INTO {TABLE} ({', '.join(_DB_COLUMNS)})
                SELECT {', '.join(_DB_COLUMNS)} FROM _tmp
                ON CONFLICT (date, indicator_code) DO UPDATE SET
                    category       = EXCLUDED.category,
                    ticker         = EXCLUDED.ticker,
                    close          = EXCLUDED.close,
                    open           = EXCLUDED.open,
                    high           = EXCLUDED.high,
                    low            = EXCLUDED.low,
                    volume         = EXCLUDED.volume,
                    source         = EXCLUDED.source
            """)
        conn.commit()
        return len(df)
    except Exception as e:
        conn.rollback()
        _alert_failure(source=csv_path, reason=str(e), table=TABLE)
        raise
    finally:
        conn.close()


def sync_new_rows(new_rows: list[dict], *, source: str) -> int:
    """collectors 공용 헬퍼 — market_daily upsert.

    snowflake_loader.sync_new_rows 와 동일한 시그니처.
    """
    if not new_rows:
        print(f"[RDS] SKIP source={source} reason=no-new-rows")
        return 0
    try:
        cols = _CSV_COLUMNS
        df = pd.DataFrame(new_rows, columns=cols)
        n = upsert_rows(df)
        print(f"[RDS] OK source={source} rows={n}")
        return n
    except Exception as e:
        reason = str(e).replace("\n", " ")[:300]
        _alert_failure(source=source, reason=reason, table=TABLE)
        return 0


def sync_macro_rows(new_rows: list[dict], *, source: str) -> int:
    """collectors 공용 헬퍼 — macro_daily upsert.

    snowflake_loader.sync_macro_rows 와 동일한 시그니처.
    """
    if not new_rows:
        print(f"[RDS] SKIP source={source} reason=no-new-rows")
        return 0
    try:
        df = pd.DataFrame(new_rows)
        df["DATE"] = pd.to_datetime(df["DATE"])
        if "VALUE" in df.columns:
            df["VALUE"] = pd.to_numeric(df["VALUE"], errors="coerce").round(4)

        macro_cols = ["date", "indicator_code", "category", "region", "value", "unit", "source"]
        df.columns = [c.lower() for c in df.columns]
        df = df[[c for c in macro_cols if c in df.columns]]

        conn = get_connection()
        try:
            cur = conn.cursor()
            # (date, indicator_code) 단위 DELETE 후 INSERT
            keys = df[["date", "indicator_code"]].drop_duplicates()
            for _, row in keys.iterrows():
                cur.execute(
                    "DELETE FROM macro_daily WHERE date = %s AND indicator_code = %s",
                    (row["date"].date(), row["indicator_code"]),
                )

            buf = StringIO()
            for _, row in df.iterrows():
                def safe(v):
                    return NULL if pd.isna(v) else str(v)
                vals = [
                    str(row["date"].date()) if pd.notna(row["date"]) else NULL,
                    safe(row.get("indicator_code")),
                    safe(row.get("category")),
                    safe(row.get("region")),
                    safe(row.get("value")),
                    safe(row.get("unit")),
                    safe(row.get("source")),
                ]
                buf.write("\t".join(vals) + "\n")
            buf.seek(0)
            cur.copy_from(buf, "macro_daily",
                columns=macro_cols, null=NULL)
            conn.commit()
            n = len(df)
            print(f"[RDS] OK source={source} rows={n}")
            return n
        finally:
            conn.close()
    except Exception as e:
        reason = str(e).replace("\n", " ")[:300]
        _alert_failure(source=source, reason=reason, table="macro_daily")
        return 0


def upsert_rows(df: pd.DataFrame, target_date: Optional[str] = None) -> int:
    """특정 날짜 행을 DELETE 후 INSERT (당일 갱신용).

    Args:
        df: CSV 스키마(DATE/INDICATOR_CODE/...) DataFrame
        target_date: 'YYYY-MM-DD'. None이면 df의 모든 날짜 처리

    Returns:
        INSERT된 행 수
    """
    if df.empty:
        return 0

    df = df.copy()
    if "DATE" in df.columns:
        df["DATE"] = pd.to_datetime(df["DATE"])

    conn = get_connection()
    try:
        cur = conn.cursor()
        if target_date:
            cur.execute(f"DELETE FROM {TABLE} WHERE date = %s", (target_date,))
        else:
            dates = df["DATE"].dt.date.unique().tolist()
            cur.execute(f"DELETE FROM {TABLE} WHERE date = ANY(%s)", (dates,))

        buf = _df_to_tsv(df)
        cur.copy_from(buf, TABLE, columns=_DB_COLUMNS, null=NULL)
        conn.commit()
        return len(df)
    except Exception as e:
        conn.rollback()
        _alert_failure(source="upsert_rows", reason=str(e), table=TABLE)
        raise
    finally:
        conn.close()
