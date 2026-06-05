"""Snowflake 전체 데이터 → RDS PostgreSQL 이관 스크립트.

Usage:
    .venv/Scripts/python scripts/migrate_sf_to_rds.py
"""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import snowflake.connector
import psycopg2
from io import StringIO

# ── 접속 ──────────────────────────────────────────────────────────────────
print("Connecting to Snowflake...")
sf = snowflake.connector.connect(
    account=os.environ['SNOWFLAKE_ACCOUNT'],
    user=os.environ['SNOWFLAKE_USER'],
    password=os.environ['SNOWFLAKE_PASSWORD'],
    database=os.environ['SNOWFLAKE_DATABASE'],
    schema=os.environ.get('SNOWFLAKE_SCHEMA', 'PUBLIC'),
    warehouse=os.environ['SNOWFLAKE_WAREHOUSE'],
)
print("Connecting to RDS...")
pg = psycopg2.connect(
    host=os.environ['RDS_HOST'],
    port=int(os.environ.get('RDS_PORT', 5432)),
    dbname=os.environ['RDS_DB'],
    user=os.environ['RDS_USER'],
    password=os.environ['RDS_PASSWORD'],
    connect_timeout=10,
)
print("Both connected\n")

sf_cur = sf.cursor()
pg_cur = pg.cursor()
NULL = r'\N'

# ── MKT100 → market_daily ─────────────────────────────────────────────────
print("[1/2] MKT100_MARKET_DAILY 읽는 중...")
sf_cur.execute('''
    SELECT "일자", "지표코드", "카테고리", "티커",
           "종가", "시가", "고가", "저가", "거래량", "소스"
    FROM MKT100_MARKET_DAILY
    ORDER BY "일자", "지표코드"
''')
rows = sf_cur.fetchall()
print(f"  Snowflake: {len(rows)} rows")

buf = StringIO()
for r in rows:
    vals = [NULL if v is None else str(v) for v in r]
    buf.write('\t'.join(vals) + '\n')
buf.seek(0)

pg_cur.execute("TRUNCATE market_daily")
pg_cur.copy_from(buf, 'market_daily',
    columns=['date','indicator_code','category','ticker',
             'close','open','high','low','volume','source'],
    null=NULL)
pg.commit()

pg_cur.execute("SELECT COUNT(*), MIN(date)::text, MAX(date)::text FROM market_daily")
cnt, mn, mx = pg_cur.fetchone()
print(f"  RDS: {cnt} rows  {mn} ~ {mx}")

# ── MKT200 → macro_daily ──────────────────────────────────────────────────
print("\n[2/2] MKT200_MACRO_DAILY 읽는 중...")
sf_cur.execute('''
    SELECT "일자", "지표코드", "카테고리", "지역",
           "값", "단위", "소스"
    FROM MKT200_MACRO_DAILY
    ORDER BY "일자", "지표코드"
''')
rows2 = sf_cur.fetchall()
print(f"  Snowflake: {len(rows2)} rows")

if rows2:
    import pandas as pd
    cols2 = ['date','indicator_code','category','region','value','unit','source']
    df2 = pd.DataFrame(rows2, columns=cols2)
    before = len(df2)
    df2 = df2.drop_duplicates(subset=['date','indicator_code'], keep='last')
    print(f"  중복 제거: {before} → {len(df2)} rows")

    buf2 = StringIO()
    for _, r in df2.iterrows():
        vals = [NULL if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v) for v in r]
        buf2.write('\t'.join(vals) + '\n')
    buf2.seek(0)

    pg_cur.execute("TRUNCATE macro_daily")
    pg_cur.copy_from(buf2, 'macro_daily',
        columns=cols2, null=NULL)
    pg.commit()

    pg_cur.execute("SELECT COUNT(*), MIN(date)::text, MAX(date)::text FROM macro_daily")
    cnt2, mn2, mx2 = pg_cur.fetchone()
    print(f"  RDS: {cnt2} rows  {mn2} ~ {mx2}")
else:
    print("  MKT200 비어 있음 — 스킵")

sf.close()
pg.close()
print("\n이관 완료")
