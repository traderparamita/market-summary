"""Extended FRED data collector — new indicators for VIEW AGENT enhancement.

Fetches additional FRED series not covered by collect_macro.py:
  - HY Credit Spread (BAMLH0A0HYM2)
  - TED Spread (TEDRATE)
  - 10Y TIPS Real Yield (DFII10)
  - ACM Term Premium (ACMTP10)
  - Fed Balance Sheet (WALCL)
  - U Michigan Consumer Sentiment (UMCSENT)
  - JOLTS Job Openings (JTSJOL)
  - 10Y Breakeven Inflation (T10YIE)
  - MOVE Index (MOVE) — Merrill Lynch bond volatility

Output: appended rows to history/macro_indicators.csv

Usage:
    python -m portfolio.collect_extended --start 2015-01-01
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
FRED_KEY = os.getenv("FRED_API_KEY", "")

MACRO_CSV = ROOT / "history" / "macro_indicators.csv"

# ─────────────────────────────────────────────────────────────
# 신규 FRED 지표 정의
# ─────────────────────────────────────────────────────────────

EXTENDED_INDICATORS: list[dict] = [
    # 크레딧 시장
    {
        "code": "CREDIT_HY_SPREAD",
        "fred_series": "BAMLH0A0HYM2",
        "category": "credit",
        "region": "US",
        "unit": "%",
        "description": "US HY Option-Adjusted Spread",
    },
    {
        "code": "CREDIT_TED_SPREAD",
        "fred_series": "TEDRATE",
        "category": "credit",
        "region": "US",
        "unit": "%",
        "description": "TED Spread (3M LIBOR - T-Bill)",
    },
    {
        "code": "CREDIT_IG_SPREAD",
        "fred_series": "BAMLC0A0CM",
        "category": "credit",
        "region": "US",
        "unit": "%",
        "description": "US IG Option-Adjusted Spread",
    },
    # 금리 분해
    {
        "code": "BOND_REAL_YIELD_10Y",
        "fred_series": "DFII10",
        "category": "rates",
        "region": "US",
        "unit": "%",
        "description": "10Y TIPS Real Yield",
    },
    {
        "code": "BOND_TERM_PREMIUM",
        "fred_series": "ACMTP10",
        "category": "rates",
        "region": "US",
        "unit": "%",
        "description": "ACM Term Premium 10Y",
    },
    {
        "code": "BOND_BREAKEVEN_10Y",
        "fred_series": "T10YIE",
        "category": "rates",
        "region": "US",
        "unit": "%",
        "description": "10Y Breakeven Inflation Rate",
    },
    # 채권 변동성
    {
        "code": "BOND_MOVE_INDEX",
        "fred_series": "MOVE",
        "category": "volatility",
        "region": "US",
        "unit": "index",
        "description": "MOVE Index (Bond Volatility)",
    },
    # 연준 대차대조표
    {
        "code": "MACRO_FED_BALANCE_SHEET",
        "fred_series": "WALCL",
        "category": "liquidity",
        "region": "US",
        "unit": "billions",
        "description": "Federal Reserve Total Assets",
    },
    # 소비자 센티먼트
    {
        "code": "MACRO_US_CONSUMER_SENT",
        "fred_series": "UMCSENT",
        "category": "sentiment",
        "region": "US",
        "unit": "index",
        "description": "U Michigan Consumer Sentiment",
    },
    # 노동시장 선행지표
    {
        "code": "MACRO_US_JOLTS",
        "fred_series": "JTSJOL",
        "category": "employment",
        "region": "US",
        "unit": "thousands",
        "description": "JOLTS Job Openings",
    },
    # PMI 대리 지표
    {
        "code": "MACRO_US_INDPRO",
        "fred_series": "INDPRO",
        "category": "activity",
        "region": "US",
        "unit": "index",
        "description": "Industrial Production Index",
    },
    {
        "code": "MACRO_US_RETAIL_SALES",
        "fred_series": "RSXFS",
        "category": "activity",
        "region": "US",
        "unit": "millions",
        "description": "Advance Retail Sales (ex-food)",
    },
]


# ─────────────────────────────────────────────────────────────
# FRED 수집 함수
# ─────────────────────────────────────────────────────────────

def fetch_fred(
    series_id: str,
    start: str,
    end: str = "9999-12-31",
    api_key: str = FRED_KEY,
) -> pd.Series | None:
    """FRED API → 날짜 인덱스 Series.

    일별 변환을 먼저 시도하고, 400 에러 시 native 주기로 재시도.
    """
    if not api_key:
        print(f"  [SKIP] FRED_API_KEY 없음: {series_id}")
        return None

    url = "https://api.stlouisfed.org/fred/series/observations"
    base_params = {
        "series_id": series_id,
        "observation_start": start,
        "observation_end": end,
        "api_key": api_key,
        "file_type": "json",
    }

    def _parse(obs_list):
        data = {
            pd.Timestamp(o["date"]): (
                float(o["value"]) if o["value"] not in (".", "") else None
            )
            for o in obs_list
        }
        s = pd.Series(data).dropna()
        s.index.name = "DATE"
        return s

    # 1차 시도: 일별 강제
    try:
        r = requests.get(url, params={**base_params, "frequency": "d",
                                       "aggregation_method": "eop"}, timeout=30)
        r.raise_for_status()
        return _parse(r.json().get("observations", []))
    except Exception:
        pass

    # 2차 시도: native 주기 (월간/주간 시리즈용)
    try:
        r = requests.get(url, params=base_params, timeout=30)
        r.raise_for_status()
        return _parse(r.json().get("observations", []))
    except Exception as e:
        print(f"  [ERR] FRED {series_id}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# 메인 수집 및 저장
# ─────────────────────────────────────────────────────────────

def load_existing(path: Path) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, parse_dates=["DATE"])
        df.columns = df.columns.str.upper()
        return df
    cols = ["DATE", "INDICATOR_CODE", "CATEGORY", "REGION", "VALUE", "UNIT", "SOURCE"]
    return pd.DataFrame(columns=cols)


def collect_extended(
    start: str = "2015-01-01",
    end: str = "9999-12-31",
    target_codes: list[str] | None = None,
) -> int:
    """수집 실행. 새 행 수 반환."""
    existing = load_existing(MACRO_CSV)
    existing_set = set(
        zip(existing["DATE"].astype(str), existing["INDICATOR_CODE"])
    ) if not existing.empty else set()

    new_rows: list[dict] = []

    indicators = EXTENDED_INDICATORS
    if target_codes:
        indicators = [i for i in indicators if i["code"] in target_codes]

    for ind in indicators:
        code = ind["code"]
        series_id = ind["fred_series"]
        print(f"  Fetching {code} ({series_id}) ...", end=" ")

        series = fetch_fred(series_id, start, end)
        if series is None or series.empty:
            print("no data")
            continue

        added = 0
        for dt, val in series.items():
            key = (str(dt.date()), code)
            if key in existing_set:
                continue
            new_rows.append({
                "DATE": dt.date(),
                "INDICATOR_CODE": code,
                "CATEGORY": ind["category"],
                "REGION": ind["region"],
                "VALUE": round(float(val), 6),
                "UNIT": ind["unit"],
                "SOURCE": "FRED",
            })
            existing_set.add(key)
            added += 1
        print(f"{added} rows added")

    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df_all = pd.concat([existing, df_new], ignore_index=True)
        df_all["DATE"] = pd.to_datetime(df_all["DATE"])
        df_all = df_all.sort_values(["INDICATOR_CODE", "DATE"]).reset_index(drop=True)
        df_all.to_csv(MACRO_CSV, index=False, date_format="%Y-%m-%d")
        print(f"\n  → macro_indicators.csv 업데이트: {len(new_rows)}행 추가")
    else:
        print("\n  → 신규 데이터 없음")

    return len(new_rows)


def main():
    parser = argparse.ArgumentParser(description="Extended FRED data collector")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="9999-12-31")
    parser.add_argument("--codes", nargs="*", help="특정 지표만 수집 (예: CREDIT_HY_SPREAD)")
    args = parser.parse_args()

    if not FRED_KEY:
        print("[ERROR] FRED_API_KEY 환경변수가 없습니다. .env 파일을 확인하세요.")
        sys.exit(1)

    print(f"Extended FRED 데이터 수집: {args.start} ~ {args.end}")
    n = collect_extended(args.start, args.end, args.codes)
    print(f"완료: {n}행")


if __name__ == "__main__":
    main()
