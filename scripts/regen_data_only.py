#!/usr/bin/env python
"""build_report_data + generate_html + _inject_existing_story 만 호출하는 핫패치 재생성 스크립트.

fetch_data (yfinance/외부 API) 는 호출하지 않음 — CSV/Snowflake 의 현재 데이터로
ISO WTD/MTD 를 다시 계산하여 _data.json 과 HTML 의 데이터 박스만 갱신, Story 는 보존.

사용:
    .venv/bin/python scripts/regen_data_only.py 2026-04-14 2026-04-15 ...
    .venv/bin/python scripts/regen_data_only.py --month 2026-04
"""
import argparse
import calendar
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def regen(target_date: str) -> tuple[bool, str]:
    from collectors.collect_market import build_report_data
    from generate import generate_html, _inject_existing_story, OUTPUT_DIR, update_current_periodic

    data = build_report_data(target_date)
    if not data:
        return False, "no data"

    month_dir = os.path.join(OUTPUT_DIR, target_date[:7])
    os.makedirs(month_dir, exist_ok=True)

    json_path = os.path.join(month_dir, f"{target_date}_data.json")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    html, report_date = generate_html(data)
    html_path = os.path.join(month_dir, f"{report_date}.html")
    _inject_existing_story(html_path, html)

    update_current_periodic(target_date)
    return True, "ok"


def list_business_days(year: int, month: int) -> list[str]:
    import datetime as dt
    import holidays
    kr = holidays.KR()
    us = holidays.US()
    last_day = calendar.monthrange(year, month)[1]
    out = []
    today = dt.date.today()
    for d in range(1, last_day + 1):
        date = dt.date(year, month, d)
        if date > today:
            break
        if date.weekday() >= 5:
            continue
        # KR 또는 US 모두 휴장이면 제외 (둘 중 하나라도 거래일이면 보고서 존재 가능)
        if date in kr and date in us:
            continue
        out.append(date.isoformat())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="*", help="YYYY-MM-DD list")
    ap.add_argument("--month", help="YYYY-MM (전체 영업일 일괄)")
    args = ap.parse_args()

    targets = list(args.dates)
    if args.month:
        y, m = args.month.split("-")
        targets.extend(list_business_days(int(y), int(m)))

    if not targets:
        ap.error("dates or --month required")

    ok = 0
    fail = []
    for d in targets:
        try:
            success, note = regen(d)
            if success:
                ok += 1
                print(f"  ✓ {d} ({note})")
            else:
                fail.append((d, note))
                print(f"  ⚠ {d} ({note})")
        except Exception as e:
            fail.append((d, str(e)[:120]))
            print(f"  ✗ {d}: {e}")

    print(f"\n[regen] ok={ok}/{len(targets)}, fail={len(fail)}")
    for d, err in fail:
        print(f"  - {d}: {err}")


if __name__ == "__main__":
    main()
