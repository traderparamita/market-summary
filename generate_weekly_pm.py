#!/usr/local/bin/python3.12
"""
Weekly PM Brief (Mon-Thu, 4영업일) 보고서 생성

금요일 오전 발행 — 그 주의 월~목 누적 변동을 매니저 톤으로 정리한다.
Story·Data Dashboard·Macro·Sources 탭은 기존 weekly 템플릿을 재사용하고,
PM 탭에는 6개 지역·자산군 섹션 + 다음 주(또는 금요일 잔여) Outlook 섹션을 주입한다.

산출물:
  output/weekly-pm/YYYY-MM-DD.html
  output/weekly-pm/YYYY-MM-DD_pm.html  (sibling)

사용:
  .venv/bin/python generate_weekly_pm.py 2026-05-01
"""

import argparse
import datetime as dt
import os
import sys

from generate_periodic import (
    aggregate_period,
    generate_periodic_html,
    load_market_data,
)
from report_utils import (
    PERIODIC_TAB_SPECS,
    inject_existing_story,
    save_story_files,
)


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "weekly-pm")


def get_mon_thu_window(report_date: dt.date, trading_days: list[str]) -> list[str]:
    """report_date 와 같은 ISO 주의 월~목 영업일만 반환."""
    iso = report_date.isocalendar()
    target_year, target_week = iso[0], iso[1]

    window: list[str] = []
    for d_str in trading_days:
        d = dt.date.fromisoformat(d_str)
        d_iso = d.isocalendar()
        if d_iso[0] == target_year and d_iso[1] == target_week and d.weekday() <= 3:
            window.append(d_str)
    return sorted(window)


def generate_weekly_pm(report_date: dt.date) -> str:
    """금요일 오전용 weekly-PM HTML 생성. 경로 반환."""
    market_data, trading_days = load_market_data()
    window = get_mon_thu_window(report_date, trading_days)
    if not window:
        raise SystemExit(f"No Mon-Thu trading days for ISO week of {report_date}")

    agg = aggregate_period(market_data, trading_days, window)
    if not agg:
        raise SystemExit(f"Aggregation failed for window {window}")

    iso = report_date.isocalendar()
    week_label = f"W{iso[1]:02d}"
    n_days = len(window)
    title = f"Weekly PM Brief | {report_date.year} {week_label} (Mon-Thu)"
    weekday_kr = "월화수목금토일"[report_date.weekday()]
    subtitle = (
        f"{window[0]} ~ {window[-1]} · {n_days}영업일 · "
        f"발행: {report_date.isoformat()} ({weekday_kr}) 오전"
    )
    filename = f"{report_date.isoformat()}.html"

    html = generate_periodic_html(agg, title, subtitle, "Weekly", filename)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)

    # 기존 파일이 있으면 PM/Story/CS/Sources 탭 보존 후 재생성
    html = inject_existing_story(path, html, PERIODIC_TAB_SPECS)
    with open(path, "w") as f:
        f.write(html)
    save_story_files(path, html, PERIODIC_TAB_SPECS, log_fn=print)

    print(f"[WEEKLY-PM] {filename}: {window[0]} ~ {window[-1]} ({n_days} days)")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weekly PM Brief generator (Mon-Thu)")
    parser.add_argument(
        "report_date",
        nargs="?",
        help="발행일 YYYY-MM-DD (보통 금요일 오전). 생략 시 오늘.",
    )
    args = parser.parse_args()

    if args.report_date:
        rd = dt.date.fromisoformat(args.report_date)
    else:
        rd = dt.date.today()

    if rd > dt.date.today():
        raise SystemExit(f"미래 날짜 금지: {rd}")

    generate_weekly_pm(rd)
    print("Done.")
