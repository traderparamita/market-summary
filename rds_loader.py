"""RDS PostgreSQL 적재 유틸리티.

history/market_data.csv → mkt100_market_daily (RDS PostgreSQL)

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

TABLE = "mkt100_market_daily"
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

    def safe_int(val):
        """volume bigint: float '12387424.0' → '12387424'"""
        if pd.isna(val):
            return NULL
        try:
            return str(int(float(val)))
        except (ValueError, OverflowError):
            return NULL

    buf = StringIO()
    for _, row in df.iterrows():
        vals = [str(row["DATE"].date()) if pd.notna(row["DATE"]) else NULL]
        for c in _CSV_COLUMNS[1:]:
            if c == "VOLUME":
                vals.append(safe_int(row.get(c)))
            else:
                vals.append(safe(row.get(c)))
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
    """CSV 전체를 mkt100_market_daily에 적재.

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
    """collectors 공용 헬퍼 — mkt100_market_daily upsert.

    snowflake_loader.sync_new_rows 와 동일한 시그니처.
    ON CONFLICT 방식으로 기존 행을 보존하면서 merge — DELETE+INSERT 금지.
    """
    if not new_rows:
        print(f"[RDS] SKIP source={source} reason=no-new-rows")
        return 0
    try:
        cols = _CSV_COLUMNS
        df = pd.DataFrame(new_rows, columns=cols)
        df["DATE"] = pd.to_datetime(df["DATE"])
        df = df.drop_duplicates(subset=["DATE", "INDICATOR_CODE"], keep="last")

        buf = _df_to_tsv(df)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"CREATE TEMP TABLE _tmp (LIKE {TABLE}) ON COMMIT DROP")
            cur.copy_from(buf, "_tmp", columns=_DB_COLUMNS, null=NULL)
            cur.execute(f"""
                INSERT INTO {TABLE} ({', '.join(_DB_COLUMNS)})
                SELECT {', '.join(_DB_COLUMNS)} FROM _tmp
                ON CONFLICT (date, indicator_code) DO UPDATE SET
                    category = EXCLUDED.category,
                    ticker   = EXCLUDED.ticker,
                    close    = EXCLUDED.close,
                    open     = EXCLUDED.open,
                    high     = EXCLUDED.high,
                    low      = EXCLUDED.low,
                    volume   = EXCLUDED.volume,
                    source   = EXCLUDED.source
            """)
            conn.commit()
            n = len(df)
        finally:
            conn.close()

        print(f"[RDS] OK source={source} rows={n}")
        return n
    except Exception as e:
        reason = str(e).replace("\n", " ")[:300]
        _alert_failure(source=source, reason=reason, table=TABLE)
        return 0


def sync_macro_rows(new_rows: list[dict], *, source: str) -> int:
    """collectors 공용 헬퍼 — mkt200_macro_daily upsert.

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

        # (date, indicator_code) 중복 제거 — COPY 중 PK 위반 방지
        df = df.drop_duplicates(subset=["date", "indicator_code"], keep="last")

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

        conn = get_connection()
        try:
            cur = conn.cursor()
            # temp table → INSERT ON CONFLICT (atomic upsert, race-condition-free)
            cur.execute("CREATE TEMP TABLE _tmp_macro (LIKE mkt200_macro_daily) ON COMMIT DROP")
            cur.copy_from(buf, "_tmp_macro", columns=macro_cols, null=NULL)
            cur.execute(f"""
                INSERT INTO mkt200_macro_daily ({', '.join(macro_cols)})
                SELECT {', '.join(macro_cols)} FROM _tmp_macro
                ON CONFLICT (date, indicator_code) DO UPDATE SET
                    category       = EXCLUDED.category,
                    region         = EXCLUDED.region,
                    value          = EXCLUDED.value,
                    unit           = EXCLUDED.unit,
                    source         = EXCLUDED.source
            """)
            conn.commit()
            n = len(df)
            print(f"[RDS] OK source={source} rows={n}")
            return n
        finally:
            conn.close()
    except Exception as e:
        reason = str(e).replace("\n", " ")[:300]
        _alert_failure(source=source, reason=reason, table="mkt200_macro_daily")
        return 0


def download_csv(out_path: Optional[str] = None) -> int:
    """mkt100_market_daily → history/market_data.csv 덤프.

    RDS 가 단일 정본이므로 git 에 CSV 를 추적하지 않는 환경에서
    clone 후 한 번 실행해 로컬 CSV 를 생성한다.

    Args:
        out_path: 저장 경로. None 이면 history/market_data.csv.

    Returns:
        다운로드한 행 수.
    """
    if out_path is None:
        out_path = os.path.join(BASE_DIR, "history", "market_data.csv")

    print(f"[DOWNLOAD] {TABLE} → {out_path} ...")
    conn = get_connection()
    try:
        sql = f"SELECT {', '.join(_DB_COLUMNS)} FROM {TABLE} ORDER BY indicator_code, date"
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()

    df.columns = _CSV_COLUMNS
    df["VOLUME"] = df["VOLUME"].astype("Int64")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"[DOWNLOAD] {len(df):,}행 → {out_path}")
    return len(df)


def upsert_rows(df: pd.DataFrame, target_date: Optional[str] = None) -> int:
    """ON CONFLICT upsert — 다른 collector가 쓴 행을 보존한다.

    Args:
        df: CSV 스키마(DATE/INDICATOR_CODE/...) DataFrame
        target_date: 사용하지 않음 (하위호환 유지용)

    Returns:
        upsert된 행 수
    """
    if df.empty:
        return 0

    df = df.copy()
    if "DATE" in df.columns:
        df["DATE"] = pd.to_datetime(df["DATE"])

    # (DATE, INDICATOR_CODE) 중복 제거 — COPY 중 PK 위반 방지
    df = df.drop_duplicates(subset=["DATE", "INDICATOR_CODE"], keep="last")

    buf = _df_to_tsv(df)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"CREATE TEMP TABLE _tmp (LIKE {TABLE}) ON COMMIT DROP")
        cur.copy_from(buf, "_tmp", columns=_DB_COLUMNS, null=NULL)
        cur.execute(f"""
            INSERT INTO {TABLE} ({', '.join(_DB_COLUMNS)})
            SELECT {', '.join(_DB_COLUMNS)} FROM _tmp
            ON CONFLICT (date, indicator_code) DO UPDATE SET
                category = EXCLUDED.category,
                ticker   = EXCLUDED.ticker,
                close    = EXCLUDED.close,
                open     = EXCLUDED.open,
                high     = EXCLUDED.high,
                low      = EXCLUDED.low,
                volume   = EXCLUDED.volume,
                source   = EXCLUDED.source
        """)
        conn.commit()
        return len(df)
    except Exception as e:
        conn.rollback()
        _alert_failure(source="upsert_rows", reason=str(e), table=TABLE)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="market_data.csv ↔ RDS mkt100_market_daily")
    parser.add_argument("csv", nargs="?", default=os.path.join(BASE_DIR, "history", "market_data.csv"))
    parser.add_argument("--truncate", action="store_true", help="업로드 전 TRUNCATE (CSV → RDS)")
    parser.add_argument("--download", action="store_true",
                        help="RDS → CSV 덤프 (clone 후 로컬 CSV 재생성용)")
    args = parser.parse_args()
    if args.download:
        download_csv(args.csv)
    else:
        bulk_load_csv(args.csv, truncate=args.truncate)
