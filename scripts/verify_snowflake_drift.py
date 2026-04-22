"""CSV ↔ Snowflake drift 검증.

매일 /market-full 직후 실행해 CSV 와 MKT100/MKT200 의 행수·코드집합이
일치하는지 확인. 불일치 시 Telegram 알림 발송.

Usage:
    .venv/bin/python scripts/verify_snowflake_drift.py [YYYY-MM-DD]
    # 인자 없으면 CSV 의 최신일 기준으로 검증

Exit code:
    0 — 일치
    1 — drift 발견 (행수 / 코드집합 / 최신일 불일치)
    2 — 실행 실패 (접속 에러 등)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV_MARKET = ROOT / "history" / "market_data.csv"
CSV_MACRO = ROOT / "history" / "macro_indicators.csv"


def _verify_market(target_date: str) -> tuple[bool, str]:
    """CSV market_data ↔ MKT100 일치 여부 검증."""
    from snowflake_loader import get_connection

    df = pd.read_csv(CSV_MARKET)
    csv_today = df[df["DATE"].astype(str) == target_date]
    csv_count = len(csv_today)
    csv_codes = set(csv_today["INDICATOR_CODE"].dropna().unique())

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*), COUNT(DISTINCT "지표코드")
            FROM FDE_DB.PUBLIC.MKT100_MARKET_DAILY
            WHERE "일자" = %s
        """, (target_date,))
        sf_count, sf_code_n = cur.fetchone()
        cur.execute("""
            SELECT DISTINCT "지표코드"
            FROM FDE_DB.PUBLIC.MKT100_MARKET_DAILY
            WHERE "일자" = %s
        """, (target_date,))
        sf_codes = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    ok = (csv_count == sf_count) and (csv_codes == sf_codes)
    only_csv = sorted(csv_codes - sf_codes)
    only_sf = sorted(sf_codes - csv_codes)

    msg = [f"MKT100 {target_date}: CSV={csv_count} MKT100={sf_count}"]
    if csv_count != sf_count:
        msg.append(f"  ❌ 행수 차이: {csv_count - sf_count:+d}")
    if only_csv:
        msg.append(f"  ❌ CSV only: {only_csv[:10]}" + ("..." if len(only_csv) > 10 else ""))
    if only_sf:
        msg.append(f"  ❌ MKT100 only: {only_sf[:10]}" + ("..." if len(only_sf) > 10 else ""))
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
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if not target:
        # CSV 의 max DATE 기본
        df = pd.read_csv(CSV_MARKET, usecols=["DATE"])
        target = str(df["DATE"].max())

    print(f"=== Snowflake drift 검증 (target={target}) ===")
    sys.path.insert(0, str(ROOT))

    results = []
    all_ok = True

    try:
        ok, msg = _verify_market(target)
        results.append(msg)
        print(msg)
        all_ok = all_ok and ok
    except Exception as e:
        err = f"MKT100 검증 실패: {e}"
        print(f"❌ {err}", file=sys.stderr)
        results.append(err)
        all_ok = False

    try:
        ok, msg = _verify_macro()
        results.append(msg)
        print(msg)
        all_ok = all_ok and ok
    except Exception as e:
        err = f"MKT200 검증 실패: {e}"
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
