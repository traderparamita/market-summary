"""Sector / Factor / Bond ETF 전체 이력 수집.

신규 KR 섹터 ETF를 포함하여 market_data.csv에 추가한다.
중복 행은 자동으로 건너뜀.

Usage:
    python -m portfolio.collect_sector_etfs --start 2010-01-01
    python -m portfolio.collect_sector_etfs --kr-only   # KR 섹터만
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from portfolio.io import load_csv_dedup, append_save_csv

ROOT = Path(__file__).resolve().parent.parent
MARKET_CSV = ROOT / "history" / "market_data.csv"

# ── 수집 대상 ──────────────────────────────────────────────────
# (indicator_code, yfinance_ticker, category, display_name)
TARGETS: list[tuple[str, str, str, str]] = [
    # US Sector ETFs
    ("SC_US_TECH",    "XLK",       "sector_us", "SPDR Tech"),
    ("SC_US_FIN",     "XLF",       "sector_us", "SPDR Fin"),
    ("SC_US_ENERGY",  "XLE",       "sector_us", "SPDR Energy"),
    ("SC_US_HEALTH",  "XLV",       "sector_us", "SPDR Health"),
    ("SC_US_INDU",    "XLI",       "sector_us", "SPDR Indu"),
    ("SC_US_DISCR",   "XLY",       "sector_us", "SPDR ConsDiscr"),
    ("SC_US_STAPLES", "XLP",       "sector_us", "SPDR ConsStap"),
    ("SC_US_UTIL",    "XLU",       "sector_us", "SPDR Util"),
    ("SC_US_MATL",    "XLB",       "sector_us", "SPDR Matl"),
    ("SC_US_REIT",    "XLRE",      "sector_us", "SPDR REIT"),    # since 2015
    ("SC_US_COMM",    "XLC",       "sector_us", "SPDR Comm"),    # since 2018
    # ── KR 섹터 ETF (collect_market.py TIGER 기준과 통일) ──────────
    # ── KR 섹터 ETF (TIGER 200 GICS 11개 — sector_country 사이클 기준) ──
    ("SC_KR_CONSTR",    "139270.KS", "sector_kr", "TIGER 200 건설"),              # 2011~
    ("SC_KR_DISCR",     "227540.KS", "sector_kr", "TIGER 200 경기소비재"),        # 2017~
    ("SC_KR_FIN",       "435420.KS", "sector_kr", "TIGER 200 금융"),              # 2021~
    ("SC_KR_INDU",      "227560.KS", "sector_kr", "TIGER 200 산업재"),            # 2017~
    ("SC_KR_STAPLES",   "227550.KS", "sector_kr", "TIGER 200 생활소비재"),        # 2017~
    ("SC_KR_ENERGY",    "472170.KS", "sector_kr", "TIGER 200 에너지화학"),        # 2022~
    ("SC_KR_HEAVY",     "157490.KS", "sector_kr", "TIGER 200 중공업"),            # 2012~
    ("SC_KR_STEEL",     "494840.KS", "sector_kr", "TIGER 200 철강소재"),          # 2022~
    ("SC_KR_COMM",      "364990.KS", "sector_kr", "TIGER 200 커뮤니케이션서비스"), # 2020~
    ("SC_KR_HLTH",      "227570.KS", "sector_kr", "TIGER 200 헬스케어"),          # 2015~
    ("SC_KR_IT",        "364980.KS", "sector_kr", "TIGER 200 IT"),                # 2020~
    # ── KR 기타 ETF (참조용, sector_country 사이클 미사용) ──────────────
    ("SC_KR_SEMI",      "277630.KS", "sector_kr", "TIGER 반도체"),                # 2009~
    ("SC_KR_BIO",       "166400.KS", "sector_kr", "TIGER 헬스케어"),              # 2013~
    ("SC_KR_BATTERY",   "137610.KS", "sector_kr", "TIGER 2차전지테마"),           # 2018~
    ("SC_KR_BANK",      "261140.KS", "sector_kr", "TIGER 은행"),                  # 2016~
    ("SC_KR_HEALTH",    "400970.KS", "sector_kr", "TIGER 의료기기"),              # 2021~
    ("SC_KR_AUTO",      "091180.KS", "sector_kr", "KODEX 자동차"),                # 2006~
    ("SC_KR_TELECOM",   "098560.KS", "sector_kr", "KODEX 통신"),                  # 2010~
    ("SC_KR_INSUR",     "140700.KS", "sector_kr", "KODEX 보험"),                  # 2011~
    ("SC_KR_TRANSPORT", "140710.KS", "sector_kr", "KODEX 운송"),                  # 2011~
    ("SC_KR_MEDIA",     "108590.KS", "sector_kr", "KODEX 미디어&엔터"),           # 2011~
    ("SC_KR_DEFENSE",   "174360.KS", "sector_kr", "TIGER 경기방어"),              # 2013~
    ("SC_KR_STAPLES",   "227550.KS", "sector_kr", "TIGER 200 필수소비재"), # 2017~
    ("SC_KR_INDU",      "227560.KS", "sector_kr", "TIGER 200 산업재"),    # 2017~
    ("SC_KR_GAME",      "228800.KS", "sector_kr", "KODEX 게임&엔터"),     # 2015~
    ("SC_KR_BIOTECH",   "278530.KS", "sector_kr", "KODEX 바이오테크"),     # 2019~
    ("SC_KR_COSDAQ_IT", "261240.KS", "sector_kr", "KODEX 코스닥150IT"),   # 2019~
    # US Factor ETFs
    ("FA_US_GROWTH",   "IVW",  "style_us", "iShares Growth"),
    ("FA_US_VALUE",    "IVE",  "style_us", "iShares Value"),
    ("FA_US_QUALITY",  "QUAL", "style_us", "iShares Quality"),   # since 2012
    ("FA_US_MOMENTUM", "MTUM", "style_us", "iShares Momentum"),  # since 2013
    ("FA_US_LOWVOL",   "USMV", "style_us", "iShares LowVol"),    # since 2011
    # Bond ETFs (short/intermediate)
    ("BD_US_1_3Y", "SHY",  "bond", "SHY"),
    ("BD_US_3_7Y", "IEI",  "bond", "IEI"),
    ("BD_US_TIPS", "TIP",  "bond", "TIP"),
]


def fetch_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    """yfinance에서 OHLCV 수집."""
    try:
        raw = yf.download(ticker, start=start, end=end,
                          auto_adjust=True, progress=False)
        if raw.empty:
            return None

        # MultiIndex → flat
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        raw = raw.rename(columns={
            "Open": "OPEN", "High": "HIGH", "Low": "LOW",
            "Close": "CLOSE", "Volume": "VOLUME",
        })
        raw.index.name = "DATE"
        return raw[["CLOSE", "OPEN", "HIGH", "LOW", "VOLUME"]].dropna(subset=["CLOSE"])
    except Exception as e:
        print(f"    [ERR] yfinance {ticker}: {e}")
        return None


def collect_sector_etfs(
    start: str = "2010-01-01",
    end: str   = "9999-12-31",
    targets: list | None = None,
) -> int:
    """백필 수집. 추가된 행 수 반환."""
    market_cols = ["DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
                   "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE"]
    existing, existing_set = load_csv_dedup(
        MARKET_CSV, market_cols, parse_dates=True,
    )

    new_rows: list[dict] = []
    if targets is None:
        targets = TARGETS

    for code, ticker, category, name in targets:
        print(f"  {code:25s} ({ticker:12s}) ...", end=" ")

        raw = fetch_yfinance(ticker, start, end)
        if raw is None or raw.empty:
            print("no data")
            time.sleep(0.3)
            continue

        added = 0
        for dt, row in raw.iterrows():
            key = (dt.strftime("%Y-%m-%d"), code)
            if key in existing_set:
                continue
            new_rows.append({
                "DATE":           dt.date(),
                "INDICATOR_CODE": code,
                "CATEGORY":       category,
                "TICKER":         name,
                "CLOSE":          round(float(row["CLOSE"]), 4),
                "OPEN":           round(float(row["OPEN"]), 4)   if pd.notna(row["OPEN"])   else None,
                "HIGH":           round(float(row["HIGH"]), 4)   if pd.notna(row["HIGH"])   else None,
                "LOW":            round(float(row["LOW"]), 4)    if pd.notna(row["LOW"])    else None,
                "VOLUME":         int(row["VOLUME"])              if pd.notna(row["VOLUME"]) else None,
                "SOURCE":         "yfinance",
            })
            existing_set.add(key)
            added += 1

        print(f"{added}행 추가")
        time.sleep(0.3)

    n = append_save_csv(
        MARKET_CSV, existing, new_rows,
        sort_cols=("INDICATOR_CODE", "DATE"),
    )
    if n:
        print(f"\n  → market_data.csv 업데이트: {n}행 추가")
    else:
        print("\n  → 신규 데이터 없음")

    return len(new_rows)


def main():
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="Sector/Factor ETF 전체 이력 수집")
    parser.add_argument("--start",   default="2010-01-01")
    parser.add_argument("--end",     default=today)
    parser.add_argument("--kr-only", action="store_true", help="KR 섹터만 수집")
    args = parser.parse_args()

    targets = TARGETS
    if args.kr_only:
        targets = [t for t in TARGETS if t[2] == "sector_kr"]

    print(f"Sector/Factor ETF 수집: {args.start} ~ {args.end} ({len(targets)}종)")
    n = collect_sector_etfs(args.start, args.end, targets)
    print(f"완료: {n}행")


if __name__ == "__main__":
    main()
