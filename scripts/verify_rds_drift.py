"""CSV ↔ RDS drift 검증.

매일 /market-full 직후 실행해 CSV 와 mkt100_market_daily/mkt200_macro_daily 의 행수·코드집합·CLOSE 값이
일치하는지 확인. 불일치 시 Telegram 알림 발송.

Usage:
    .venv/bin/python scripts/verify_rds_drift.py [YYYY-MM-DD] [--days N]
    # 인자 없으면 CSV 의 최신일 기준
    # --days N: target_date 를 끝점으로 한 N영업일 윈도우(달력일+2)까지 CLOSE 값 비교 (기본 7)

검증 항목:
    1. (단일일) mkt100_market_daily 행수·indicator_code 집합 일치
    2. (윈도우) mkt100_market_daily (date × indicator_code × close) 일치
    3. mkt200_macro_daily 전체 행수 (±100 허용)

Exit code:
    0 — 일치
    1 — drift 발견
    2 — 실행 실패 (접속 에러 등)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CSV_MARKET = ROOT / "history" / "market_data.csv"
CSV_MACRO  = ROOT / "history" / "macro_indicators.csv"

CLOSE_TOLERANCE = 0.005


def _verify_market_single(target_date: str) -> tuple[bool, str]:
    from rds_loader import get_connection

    df = pd.read_csv(CSV_MARKET)
    csv_today = df[df["DATE"].astype(str) == target_date]
    csv_count = len(csv_today)
    csv_codes = set(csv_today["INDICATOR_CODE"].dropna().unique())

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT indicator_code) "
            "FROM mkt100_market_daily WHERE date = %s",
            (target_date,),
        )
        rds_count, _ = cur.fetchone()
        cur.execute(
            "SELECT DISTINCT indicator_code FROM mkt100_market_daily WHERE date = %s",
            (target_date,),
        )
        rds_codes = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    ok = (csv_count == rds_count) and (csv_codes == rds_codes)
    only_csv = sorted(csv_codes - rds_codes)
    only_rds = sorted(rds_codes - csv_codes)

    msg = [f"mkt100_market_daily {target_date} (단일일): CSV={csv_count} RDS={rds_count}"]
    if csv_count != rds_count:
        msg.append(f"  ❌ 행수 차이: {csv_count - rds_count:+d}")
    if only_csv:
        msg.append(f"  ❌ CSV only: {only_csv[:10]}" + ("..." if len(only_csv) > 10 else ""))
    if only_rds:
        msg.append(f"  ❌ RDS only: {only_rds[:10]}" + ("..." if len(only_rds) > 10 else ""))
    return ok, "\n".join(msg)


def _verify_market_window(target_date: str, days: int) -> tuple[bool, str]:
    from market_source import load_long

    target = dt.datetime.strptime(target_date, "%Y-%m-%d").date()
    window_start = (target - dt.timedelta(days=days)).strftime("%Y-%m-%d")

    df_csv = pd.read_csv(CSV_MARKET, usecols=["DATE", "INDICATOR_CODE", "CLOSE"])
    df_csv["DATE"] = df_csv["DATE"].astype(str)
    df_csv = df_csv[(df_csv["DATE"] >= window_start) & (df_csv["DATE"] <= target_date)]
    df_csv = df_csv.dropna(subset=["INDICATOR_CODE"])
    df_csv["CLOSE"] = pd.to_numeric(df_csv["CLOSE"], errors="coerce")

    df_rds = load_long(start=window_start, end=target_date)
    if df_rds.empty:
        return False, f"mkt100_market_daily 윈도우 {window_start}~{target_date}: RDS 응답 비어있음"
    df_rds = df_rds.copy()
    df_rds["DATE"] = df_rds["DATE"].dt.strftime("%Y-%m-%d")
    df_rds["CLOSE"] = pd.to_numeric(df_rds["CLOSE"], errors="coerce")

    owned_codes = set(df_csv["INDICATOR_CODE"].unique())
    csv_keys = set(zip(df_csv["DATE"], df_csv["INDICATOR_CODE"]))
    rds_keys = set(zip(df_rds["DATE"], df_rds["INDICATOR_CODE"]))

    missing_in_rds = sorted(csv_keys - rds_keys)
    extra_in_rds = sorted(
        (d, c) for d, c in (rds_keys - csv_keys) if c in owned_codes
    )

    merged = df_csv[["DATE", "INDICATOR_CODE", "CLOSE"]].merge(
        df_rds[["DATE", "INDICATOR_CODE", "CLOSE"]],
        on=["DATE", "INDICATOR_CODE"], how="inner", suffixes=("_csv", "_rds"),
    )
    merged["DIFF"] = (merged["CLOSE_csv"] - merged["CLOSE_rds"]).abs()
    close_diff = merged[merged["DIFF"] > CLOSE_TOLERANCE].sort_values(["DATE", "INDICATOR_CODE"])

    ok = not (missing_in_rds or extra_in_rds or len(close_diff))
    msg = [
        f"mkt100_market_daily 윈도우 {window_start}~{target_date} ({days}일): "
        f"CSV={len(csv_keys)} RDS={len(rds_keys)} 교집합={len(merged)}"
    ]
    if missing_in_rds:
        msg.append(f"  ❌ Missing in RDS ({len(missing_in_rds)}건): "
                   + str(missing_in_rds[:5]) + ("..." if len(missing_in_rds) > 5 else ""))
    if extra_in_rds:
        msg.append(f"  ❌ Extra in RDS ({len(extra_in_rds)}건): "
                   + str(extra_in_rds[:5]) + ("..." if len(extra_in_rds) > 5 else ""))
    if len(close_diff):
        msg.append(f"  ❌ CLOSE 값 mismatch ({len(close_diff)}건, 허용 ±{CLOSE_TOLERANCE}):")
        for _, r in close_diff.head(8).iterrows():
            msg.append(f"      {r['DATE']} {r['INDICATOR_CODE']}: "
                       f"CSV={r['CLOSE_csv']} RDS={r['CLOSE_rds']} (diff {r['DIFF']:.3f})")
        if len(close_diff) > 8:
            msg.append(f"      ... 외 {len(close_diff) - 8}건")
    return ok, "\n".join(msg)


def _verify_macro() -> tuple[bool, str]:
    from rds_loader import get_connection

    if not CSV_MACRO.exists():
        return True, "mkt200_macro_daily: macro CSV 없음 — skip"

    df = pd.read_csv(CSV_MACRO)
    csv_count = len(df)
    csv_max_date = df["DATE"].max()

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MAX(date)::text FROM mkt200_macro_daily")
        rds_count, rds_max = cur.fetchone()
    finally:
        conn.close()

    drift = abs(csv_count - rds_count)
    # 이관 시 Snowflake 중복 196건 제거됐으므로 250까지 허용
    ok = drift <= 250
    msg = [f"mkt200_macro_daily: CSV={csv_count:,} RDS={rds_count:,} (최신 CSV={csv_max_date} RDS={rds_max})"]
    if not ok:
        msg.append(f"  ❌ 행수 차이 {drift:,} (허용 100 초과)")
    return ok, "\n".join(msg)


def _send_alert(title: str, body: str) -> None:
    try:
        from notify_telegram import send
        send(f"⚠ *{title}*\n```\n{body}\n```")
    except Exception as e:
        print(f"[WARN] Telegram 알림 실패: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="CSV ↔ RDS drift 검증")
    parser.add_argument("date", nargs="?", help="target date YYYY-MM-DD (기본: CSV max DATE)")
    parser.add_argument("--days", type=int, default=7, help="윈도우 검증 일수 (기본 7)")
    args = parser.parse_args()

    target = args.date
    if not target:
        df = pd.read_csv(CSV_MARKET, usecols=["DATE"])
        target = str(df["DATE"].max())

    print(f"=== RDS drift 검증 (target={target}, 윈도우={args.days}일) ===")

    results = []
    all_ok = True

    for label, fn in [
        ("mkt100_market_daily 단일일", lambda: _verify_market_single(target)),
        (f"mkt100_market_daily 윈도우({args.days}일)", lambda: _verify_market_window(target, args.days)),
        ("mkt200_macro_daily", _verify_macro),
    ]:
        try:
            ok, msg = fn()
            results.append(msg)
            print(msg)
            all_ok = all_ok and ok
        except Exception as e:
            err = f"{label} 검증 실패: {e}"
            print(f"❌ {err}", file=sys.stderr)
            results.append(err)
            all_ok = False

    if all_ok:
        print("\n✓ Drift 없음 — CSV ↔ RDS 일치")
        return 0

    print("\n❌ Drift 발견 — Telegram 알림 발송")
    _send_alert(f"RDS drift 발견 ({target})", "\n".join(results))
    return 1


if __name__ == "__main__":
    sys.exit(main())
