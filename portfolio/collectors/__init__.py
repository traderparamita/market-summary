"""Market data collectors (auxiliary to core fetch_data).

Modules:
    krx_sectors  — KOSPI200 GICS 지수 (pykrx, IX_KR_*)
    valuation    — KOSPI PER/PBR/DY (pykrx, VAL_KR_*)
    sector_etfs  — SC_US_*, FA_US_*, SC_KR_* (yfinance)
    macro        — FRED + ECOS 매크로 지표 (MKT200)

각 모듈은 CSV append + Snowflake upsert (`snowflake_loader.sync_new_rows`) 를
모두 수행한다. 표준 마커: [SNOWFLAKE] OK/FAILED/SKIP.

Usage:
    python -m portfolio.collectors.krx_sectors --start 2010-01-01
    python -m portfolio.collectors.macro --start 2010-01-01
"""
