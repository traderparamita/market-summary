"""CSV ↔ Snowflake drift 검증.

매일 /market-full 직후 실행해 CSV 와 MKT100/MKT200 의 행수·코드집합·CLOSE 값이
일치하는지 확인. 불일치 시 Telegram 알림 발송.

Usage:
    .venv/bin/python scripts/verify_snowflake_drift.py [YYYY-MM-DD] [--days N]
    # 인자 없으면 CSV 의 최신일 기준
    # --days N: target_date 를 끝점으로 한 N영업일 윈도우(달력일+2)까지 CLOSE 값 비교 (기본 7)

검증 항목:
    1. (단일일) MKT100 행수·INDICATOR_CODE 집합 일치
    2. (윈도우) MKT100 (DATE × CODE × CLOSE) 일치 — Naver/FDR fallback 의 retroactive
       보정이 SF 로 흘러갔는지, 다른 프로세스가 우리 코드를 덮어쓰진 않았는지 감지
    3. MKT200 macro 행수 (legacy 정리 허용 ±100)

Exit code:
    0 — 일치
    1 — drift 발견 (행수 / 코드집합 / 최신일 / CLOSE 값 불일치)
    2 — 실행 실패 (접속 에러 등)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV_MARKET = ROOT / "history" / "market_data.csv"
CSV_MACRO = ROOT / "history" / "macro_indicators.csv"

# CLOSE 값 비교 허용 오차. CSV 는 NUMBER(18,3) 으로 저장되므로 0.005 면 충분.
CLOSE_TOLERANCE = 0.005

# 윈도우 비교에서 무시할 코드 — 다른 프로젝트가 같은 SF 테이블에 쓰는 경우.
# market_summary 가 책임지지 않는 코드는 "extra in SF" 로 잡지 않는다.
EXTERNAL_CODES_PREFIXES: tuple[str, ...] = ()  # 필요 시 운영 중 추가


def _verify_market_single(target_date: str) -> tuple[bool, str]:
    """단일일 행수·코드집합 검증 (기존 로직)."""
    from snowflake_loader import get_connection

    df = pd.read_csv(CSV_MARKET)
    csv_today = df[df["DATE"].astype(str) == target_date]
    csv_count = len(csv_today)
    csv_codes = set(csv_today["INDICATOR_CODE"].dropna().unique())

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT COUNT(*), COUNT(DISTINCT "지표코드") '
            'FROM FDE_DB.PUBLIC.MKT100_MARKET_DAILY WHERE "일자" = %s',
            (target_date,),
        )
        sf_count, _ = cur.fetchone()
        cur.execute(
            'SELECT DISTINCT "지표코드" FROM FDE_DB.PUBLIC.MKT100_MARKET_DAILY '
            'WHERE "일자" = %s',
            (target_date,),
        )
        sf_codes = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    ok = (csv_count == sf_count) and (csv_codes == sf_codes)
    only_csv = sorted(csv_codes - sf_codes)
    only_sf = sorted(sf_codes - csv_codes)

    msg = [f"MKT100 {target_date} (단일일): CSV={csv_count} MKT100={sf_count}"]
    if csv_count != sf_count:
        msg.append(f"  ❌ 행수 차이: {csv_count - sf_count:+d}")
    if only_csv:
        msg.append(f"  ❌ CSV only: {only_csv[:10]}" + ("..." if len(only_csv) > 10 else ""))
    if only_sf:
        msg.append(f"  ❌ MKT100 only: {only_sf[:10]}" + ("..." if len(only_sf) > 10 else ""))
    return ok, "\n".join(msg)


def _verify_market_window(target_date: str, days: int) -> tuple[bool, str]:
    """윈도우 검증 — CSV ↔ MKT100 의 (DATE, CODE, CLOSE) 비교.

    Naver/FDR/investiny fallback 이 직전 영업일 데이터를 사후 보정하면
    generate.py Step 1c 가 그 윈도우를 다시 upsert 하므로 다음 run 에서 일치해야 함.
    여기서 잡히면 = 어떤 이유로든 동기화가 끊긴 상태.
    """
    sys.path.insert(0, str(ROOT))
    from market_source import load_long

    target = dt.datetime.strptime(target_date, "%Y-%m-%d").date()
    window_start = (target - dt.timedelta(days=days)).strftime("%Y-%m-%d")

    # CSV
    df_csv = pd.read_csv(CSV_MARKET, usecols=["DATE", "INDICATOR_CODE", "CLOSE"])
    df_csv["DATE"] = df_csv["DATE"].astype(str)
    df_csv = df_csv[(df_csv["DATE"] >= window_start) & (df_csv["DATE"] <= target_date)]
    df_csv = df_csv.dropna(subset=["INDICATOR_CODE"])
    df_csv["CLOSE"] = pd.to_numeric(df_csv["CLOSE"], errors="coerce")

    # SF
    df_sf = load_long(start=window_start, end=target_date)
    if df_sf.empty:
        return False, f"MKT100 윈도우 {window_start}~{target_date}: SF 응답 비어있음"
    df_sf = df_sf.copy()
    df_sf["DATE"] = df_sf["DATE"].dt.strftime("%Y-%m-%d")
    df_sf["CLOSE"] = pd.to_numeric(df_sf["CLOSE"], errors="coerce")

    # 우리가 책임지는 코드 = CSV 윈도우에 등장한 코드
    owned_codes = set(df_csv["INDICATOR_CODE"].unique())

    csv_keys = set(zip(df_csv["DATE"], df_csv["INDICATOR_CODE"]))
    sf_keys = set(zip(df_sf["DATE"], df_sf["INDICATOR_CODE"]))

    missing_in_sf = sorted(csv_keys - sf_keys)
    # extra: SF 에만 있고, 우리가 책임지는 코드인 경우만 (다른 프로젝트 데이터는 무시)
    extra_in_sf = sorted(
        (d, c) for d, c in (sf_keys - csv_keys)
        if c in owned_codes and not any(c.startswith(p) for p in EXTERNAL_CODES_PREFIXES)
    )

    # CLOSE 값 비교 (key 교집합)
    merged = df_csv[["DATE", "INDICATOR_CODE", "CLOSE"]].merge(
        df_sf[["DATE", "INDICATOR_CODE", "CLOSE"]],
        on=["DATE", "INDICATOR_CODE"], how="inner", suffixes=("_csv", "_sf"),
    )
    merged["DIFF"] = (merged["CLOSE_csv"] - merged["CLOSE_sf"]).abs()
    close_diff = merged[merged["DIFF"] > CLOSE_TOLERANCE].sort_values(["DATE", "INDICATOR_CODE"])

    ok = not (missing_in_sf or extra_in_sf or len(close_diff))
    msg = [
        f"MKT100 윈도우 {window_start}~{target_date} ({days}일): "
        f"CSV={len(csv_keys)} SF={len(sf_keys)} 교집합={len(merged)}"
    ]
    if missing_in_sf:
        msg.append(f"  ❌ Missing in SF ({len(missing_in_sf)}건): "
                   + str(missing_in_sf[:5]) + ("..." if len(missing_in_sf) > 5 else ""))
    if extra_in_sf:
        msg.append(f"  ❌ Owned-code Extra in SF ({len(extra_in_sf)}건, 다른 프로세스 침범 의심): "
                   + str(extra_in_sf[:5]) + ("..." if len(extra_in_sf) > 5 else ""))
    if len(close_diff):
        msg.append(f"  ❌ CLOSE 값 mismatch ({len(close_diff)}건, 허용 ±{CLOSE_TOLERANCE}):")
        for _, r in close_diff.head(8).iterrows():
            msg.append(f"      {r['DATE']} {r['INDICATOR_CODE']}: "
                       f"CSV={r['CLOSE_csv']} SF={r['CLOSE_sf']} (diff {r['DIFF']:.3f})")
        if len(close_diff) > 8:
            msg.append(f"      ... 외 {len(close_diff) - 8}건")
    return ok, "\n".join(msg)


def _verify_macro() -> tuple[bool, str]:
    """CSV macro_indicators ↔ MKT200 전체 행수 일치 여부 (macro 는 증분)."""
    from snowflake_loader import get_connection

    if not CSV_MACRO.exists():
        return True, "MKT200: macro CSV 없음 — skip"

    df = pd.read_csv(CSV_MACRO)
    csv_count = len(df)
    csv_max_date = df["DATE"].max()

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*), MAX("일자") FROM FDE_DB.PUBLIC.MKT200_MACRO_DAILY')
        sf_count, sf_max = cur.fetchone()
    finally:
        conn.close()

    drift = abs(csv_count - sf_count)
    # macro 는 legacy 코드 3종(CREDIT_HY_SPREAD 등) 정리했으므로 완전 일치 어려울 수 있음.
    # 행수 차이 100 이하는 허용 (매일 신규 ~14-50 행 추가되는 수준).
    ok = drift <= 100
    msg = [f"MKT200: CSV={csv_count:,} MKT200={sf_count:,} (최신 CSV={csv_max_date} SF={sf_max})"]
    if not ok:
        msg.append(f"  ❌ 행수 차이 {drift:,} (허용 100 초과)")
    return ok, "\n".join(msg)


def _send_alert(title: str, body: str) -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from notify_telegram import send
        send(f"⚠ *{title}*\n```\n{body}\n```")
    except Exception as e:
        print(f"[WARN] Telegram 알림 실패: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="CSV ↔ Snowflake drift 검증")
    parser.add_argument("date", nargs="?", help="target date YYYY-MM-DD (기본: CSV max DATE)")
    parser.add_argument("--days", type=int, default=7,
                        help="윈도우 검증 일수 (기본 7)")
    args = parser.parse_args()

    target = args.date
    if not target:
        df = pd.read_csv(CSV_MARKET, usecols=["DATE"])
        target = str(df["DATE"].max())

    print(f"=== Snowflake drift 검증 (target={target}, 윈도우={args.days}일) ===")
    sys.path.insert(0, str(ROOT))

    results = []
    all_ok = True

    for label, fn in [
        ("MKT100 단일일", lambda: _verify_market_single(target)),
        (f"MKT100 윈도우({args.days}일)", lambda: _verify_market_window(target, args.days)),
        ("MKT200 macro", _verify_macro),
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
        print("\n✓ Drift 없음 — CSV ↔ Snowflake 일치")
        return 0

    print("\n❌ Drift 발견 — Telegram 알림 발송")
    _send_alert(
        f"Snowflake drift 발견 ({target})",
        "\n".join(results),
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
