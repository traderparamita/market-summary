"""KRX KOSPI 200 GICS 섹터 지수 수집 (pykrx).

pykrx로 KRX 공식 업종 지수 OHLCV를 수집하여 market_data.csv에 추가한다.
ETF(2015~2022 상장)보다 훨씬 긴 2010년 이력을 확보한다.

KRX_ID / KRX_PW 환경변수 필요 (.env에 설정).

Usage:
    python -m collectors.krx_sectors --start 2010-01-01
    python -m collectors.krx_sectors --start 2010-01-01 --traditional  # 전통 업종(2000~)
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from pykrx import stock  # noqa: E402

try:
    from .io_utils import load_csv_dedup, append_save_csv
except ImportError:
    from io_utils import load_csv_dedup, append_save_csv

ROOT = Path(__file__).resolve().parent.parent  # market_summary/ (from collectors/)
MARKET_CSV = ROOT / "history" / "market_data.csv"

# KOSPI 200 GICS 섹터 지수 (2010~ )
# IX_KR_ prefix. KR 섹터 데이터의 단일 정본 (이전 SC_KR_* ETF 시계열은 2026-05-07 제거).
GICS_SECTORS: list[tuple[str, str, str, str]] = [
    ("IX_KR_IT",       "1155", "index_kr", "KOSPI200 정보기술"),
    ("IX_KR_COMM",     "1150", "index_kr", "KOSPI200 커뮤니케이션"),
    ("IX_KR_FIN",      "1156", "index_kr", "KOSPI200 금융"),
    ("IX_KR_ENERGY",   "1154", "index_kr", "KOSPI200 에너지/화학"),
    ("IX_KR_HEALTH",   "1160", "index_kr", "KOSPI200 헬스케어"),
    ("IX_KR_INDU",     "1159", "index_kr", "KOSPI200 산업재"),
    ("IX_KR_HEAVY",    "1152", "index_kr", "KOSPI200 중공업"),
    ("IX_KR_DISCR",    "1158", "index_kr", "KOSPI200 경기소비재"),
    ("IX_KR_STAPLES",  "1157", "index_kr", "KOSPI200 생활소비재"),
    ("IX_KR_STEEL",    "1153", "index_kr", "KOSPI200 철강/소재"),
    ("IX_KR_CONSTR",   "1151", "index_kr", "KOSPI200 건설"),
]

# 전통 업종 지수 (2000~ , GICS와 1:1은 아니지만 유사 매핑)
TRADITIONAL_SECTORS: list[tuple[str, str, str, str]] = [
    ("IX_KR_ELEC",      "1013", "index_kr", "전기전자"),
    ("IX_KR_TELECOM",   "1020", "index_kr", "통신"),
    ("IX_KR_FINANCE",   "1021", "index_kr", "금융"),
    ("IX_KR_CHEM",      "1008", "index_kr", "화학"),
    ("IX_KR_PHARMA",    "1009", "index_kr", "제약"),
    ("IX_KR_MACHINE",   "1012", "index_kr", "기계·장비"),
    ("IX_KR_METAL",     "1011", "index_kr", "금속"),
    ("IX_KR_VEHICLE",   "1015", "index_kr", "운송장비·부품"),
    ("IX_KR_FOOD",      "1005", "index_kr", "음식료·담배"),
    ("IX_KR_UTIL",      "1017", "index_kr", "전기·가스"),
    ("IX_KR_CONSTRUCT", "1018", "index_kr", "건설"),
]


def fetch_krx_index(krx_code: str, start: str, end: str) -> pd.DataFrame | None:
    """pykrx로 KRX 지수 OHLCV 수집. 연도별 분할 요청으로 안정성 확보."""
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    frames = []
    year = start_dt.year
    while year <= end_dt.year:
        y_start = max(start_dt, pd.Timestamp(f"{year}-01-01")).strftime("%Y%m%d")
        y_end = min(end_dt, pd.Timestamp(f"{year}-12-31")).strftime("%Y%m%d")
        try:
            df = stock.get_index_ohlcv_by_date(y_start, y_end, krx_code)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            print(f"    [ERR] KRX {krx_code} {year}: {e}")
        year += 1
        time.sleep(0.2)

    if not frames:
        return None

    result = pd.concat(frames)
    result = result[~result.index.duplicated(keep="last")]
    result = result.sort_index()

    result = result.rename(columns={
        "시가": "OPEN", "고가": "HIGH", "저가": "LOW",
        "종가": "CLOSE", "거래량": "VOLUME",
    })
    result.index.name = "DATE"
    return result[["CLOSE", "OPEN", "HIGH", "LOW", "VOLUME"]].dropna(subset=["CLOSE"])


def collect_krx_sectors(
    start: str = "2010-01-01",
    end: str = "9999-12-31",
    targets: list | None = None,
) -> int:
    market_cols = ["DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
                   "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE"]
    existing, existing_set = load_csv_dedup(
        MARKET_CSV, market_cols, parse_dates=True,
    )

    if end == "9999-12-31":
        end = pd.Timestamp.today().strftime("%Y-%m-%d")

    new_rows: list[dict] = []
    if targets is None:
        targets = GICS_SECTORS

    for code, krx_code, category, name in targets:
        print(f"  {code:20s} (KRX {krx_code:6s} {name}) ...", end=" ", flush=True)

        raw = fetch_krx_index(krx_code, start, end)
        if raw is None or raw.empty:
            print("no data")
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
                "OPEN":           round(float(row["OPEN"]), 4) if pd.notna(row["OPEN"]) else None,
                "HIGH":           round(float(row["HIGH"]), 4) if pd.notna(row["HIGH"]) else None,
                "LOW":            round(float(row["LOW"]), 4)  if pd.notna(row["LOW"])  else None,
                "VOLUME":         int(row["VOLUME"])            if pd.notna(row["VOLUME"]) else None,
                "SOURCE":         "pykrx",
            })
            existing_set.add(key)
            added += 1

        print(f"{added}행 추가")

    # KRX 직접 수집 실패 시 RDS fallback (로컬에서 KRX 접속 차단된 경우)
    if not new_rows and targets is not None and len(targets) > 0:
        new_rows = _pull_from_rds(
            codes=[t[0] for t in targets],
            start=start,
            end=end,
            existing_set=existing_set,
        )

    n = append_save_csv(
        MARKET_CSV, existing, new_rows,
        sort_cols=("INDICATOR_CODE", "DATE"),
    )
    if n:
        print(f"\n  → market_data.csv 업데이트: {n}행 추가")
    else:
        print("\n  → 신규 데이터 없음")

    # Snowflake dual-write (best-effort) — RDS fallback 경유 행은 제외
    rds_rows = [r for r in new_rows if r.get("SOURCE") != "rds_pull"]
    if rds_rows:
        try:
            from rds_loader import sync_new_rows
            sync_new_rows(rds_rows, source="collect_krx_sectors")
        except Exception as e:
            try:
                from rds_loader import _alert_failure
                _alert_failure(source="collect_krx_sectors", reason=str(e)[:200])
            except Exception:
                print(f"[SNOWFLAKE] FAILED source=collect_krx_sectors reason={str(e)[:200]}")

    return len(new_rows)


def _pull_from_rds(
    codes: list[str],
    start: str,
    end: str,
    existing_set: set,
) -> list[dict]:
    """KRX 직접 수집 실패 시 RDS에서 IX_KR_* 행을 pull해 CSV dedup 후 반환."""
    try:
        from rds_loader import get_connection
        conn = get_connection()
        placeholders = ", ".join(["%s"] * len(codes))
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT date, indicator_code, category, ticker,
                           close, open, high, low, volume
                    FROM mkt100_market_daily
                    WHERE indicator_code IN ({placeholders})
                      AND date BETWEEN %s AND %s
                    ORDER BY indicator_code, date
                    """,
                    codes + [start, end],
                )
                rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"  [RDS fallback] FAILED: {e}")
        return []

    result = []
    for r in rows:
        key = (str(r[0]), r[1])
        if key in existing_set:
            continue
        result.append({
            "DATE":           r[0],
            "INDICATOR_CODE": r[1],
            "CATEGORY":       r[2],
            "TICKER":         r[3],
            "CLOSE":          r[4],
            "OPEN":           r[5],
            "HIGH":           r[6],
            "LOW":            r[7],
            "VOLUME":         r[8],
            "SOURCE":         "rds_pull",
        })
        existing_set.add(key)

    if result:
        print(f"  [RDS fallback] {len(result)}행 pull 완료")
    else:
        print("  [RDS fallback] 신규 데이터 없음")
    return result


def main():
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="KRX KOSPI 200 GICS 섹터 지수 수집")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default=today)
    parser.add_argument("--traditional", action="store_true",
                        help="전통 업종 지수(2000~)도 함께 수집")
    args = parser.parse_args()

    targets = list(GICS_SECTORS)
    if args.traditional:
        targets += TRADITIONAL_SECTORS

    print(f"KRX 섹터 지수 수집: {args.start} ~ {args.end} ({len(targets)}종)")
    n = collect_krx_sectors(args.start, args.end, targets)
    print(f"완료: {n}행")


if __name__ == "__main__":
    main()
