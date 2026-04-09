#!/usr/local/bin/python3.12
"""
시뮬레이션: 2026-03-02 ~ 2026-03-06 매일 08:00 워크플로우 재현
- 각 날짜별로 일간/주간/월간 보고서 생성
- 결과를 simulation/ 폴더에 저장
- 기존 output/ 폴더는 건드리지 않음
"""

import os
import sys
import shutil
import datetime as dt
import csv
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIM_DIR = os.path.join(BASE_DIR, "simulation")
HISTORY_CSV = os.path.join(BASE_DIR, "history", "market_data.csv")

# 시뮬레이션 날짜 범위
SIM_DATES = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]


def create_truncated_csv(cutoff_date, dest_path):
    """market_data.csv에서 cutoff_date 이하의 데이터만 복사"""
    with open(HISTORY_CSV, encoding="utf-8") as f_in, \
         open(dest_path, "w", encoding="utf-8") as f_out:
        reader = csv.reader(f_in)
        header = next(reader)
        f_out.write(",".join(header) + "\n")
        for row in reader:
            if not row or not row[0]:
                continue
            if row[0] <= cutoff_date:
                f_out.write(",".join(row) + "\n")


def run_simulation():
    # 깨끗한 simulation 폴더 준비 (stories 폴더는 보존)
    if os.path.exists(SIM_DIR):
        stories_dir = os.path.join(SIM_DIR, "stories")
        stories_backup = None
        if os.path.exists(stories_dir):
            stories_backup = os.path.join(BASE_DIR, "_stories_backup")
            if os.path.exists(stories_backup):
                shutil.rmtree(stories_backup)
            shutil.copytree(stories_dir, stories_backup)
        shutil.rmtree(SIM_DIR)
        os.makedirs(SIM_DIR)
        if stories_backup and os.path.exists(stories_backup):
            shutil.copytree(stories_backup, stories_dir)
            shutil.rmtree(stories_backup)
    else:
        os.makedirs(SIM_DIR)

    # 임시 CSV 파일 (날짜별로 잘라서 사용)
    tmp_csv = os.path.join(SIM_DIR, "_market_data_tmp.csv")

    for sim_date in SIM_DATES:
        print(f"\n{'='*60}")
        print(f"  Simulating: {sim_date} 08:00 KST workflow")
        print(f"{'='*60}")

        # 1) 해당 날짜까지의 CSV 생성
        create_truncated_csv(sim_date, tmp_csv)
        row_count = sum(1 for _ in open(tmp_csv)) - 1
        print(f"  CSV rows (up to {sim_date}): {row_count}")

        # 2) 모듈 임포트 전에 OUTPUT_DIR과 HISTORY_CSV를 패치
        #    매번 fresh import를 위해 캐시 제거
        for mod_name in list(sys.modules.keys()):
            if mod_name in ("generate", "generate_periodic"):
                del sys.modules[mod_name]

        # generate 모듈 패치
        import generate
        generate.OUTPUT_DIR = SIM_DIR
        generate.HISTORY_CSV = tmp_csv

        import generate_periodic
        generate_periodic.OUTPUT_DIR = SIM_DIR
        generate_periodic.HISTORY_CSV = tmp_csv

        # 3) 일간 보고서 생성 (fetch_data 건너뜀 — CSV 데이터 직접 사용)
        print(f"\n  [DAILY] Generating daily report...")
        data = generate.build_report_data(sim_date)

        month_dir = os.path.join(SIM_DIR, sim_date[:7])
        os.makedirs(month_dir, exist_ok=True)

        # _data.json 저장
        import json
        json_path = os.path.join(month_dir, f"{sim_date}_data.json")
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {json_path}")

        # HTML 생성
        html, report_date = generate.generate_html(data)
        html_path = os.path.join(month_dir, f"{report_date}.html")
        generate._inject_existing_story(html_path, html)
        print(f"  Saved: {html_path}")

        # 4) 주간/월간 보고서 갱신
        print(f"\n  [WEEKLY/MONTHLY] Updating periodic reports...")
        td = dt.datetime.strptime(sim_date, "%Y-%m-%d").date()
        year = td.year

        market_data, trading_days = generate_periodic.load_market_data()

        # 주간
        iso = td.isocalendar()
        iso_week = iso[1]
        weeks = generate_periodic.get_week_ranges(trading_days, year)
        week_key = (iso[0], iso_week)

        if week_key in weeks:
            dates = weeks[week_key]
            agg = generate_periodic.aggregate_period(market_data, trading_days, dates)
            if agg:
                first, last = agg["first"], agg["last"]
                n_days = len(agg["dates"])
                week_label = f"W{iso_week:02d}"
                title = f"Weekly Summary | {year} {week_label}"
                subtitle = f"{first} ~ {last} ({n_days} trading days)"
                filename = f"{year}-W{iso_week:02d}.html"

                weekly_dir = os.path.join(SIM_DIR, "weekly")
                os.makedirs(weekly_dir, exist_ok=True)
                html = generate_periodic.generate_periodic_html(
                    agg, title, subtitle, "Weekly", filename
                )
                path = os.path.join(weekly_dir, filename)
                generate._inject_existing_story(path, html)
                print(f"  Weekly: {filename} ({first} ~ {last}, {n_days} days)")

        # 월간
        month_str = sim_date[:7]
        month_dates = sorted([d for d in trading_days if d.startswith(month_str)])
        if month_dates:
            agg = generate_periodic.aggregate_period(market_data, trading_days, month_dates)
            if agg:
                month_name = td.strftime("%B")
                title = f"Monthly Summary | {year} {month_name}"
                subtitle = f"{month_dates[0]} ~ {month_dates[-1]} ({len(month_dates)} trading days)"
                filename = f"{year}-{td.month:02d}.html"

                monthly_dir = os.path.join(SIM_DIR, "monthly")
                os.makedirs(monthly_dir, exist_ok=True)
                html = generate_periodic.generate_periodic_html(
                    agg, title, subtitle, "Monthly", filename
                )
                path = os.path.join(monthly_dir, filename)
                generate._inject_existing_story(path, html)
                print(f"  Monthly: {filename} ({month_dates[0]} ~ {month_dates[-1]}, {len(month_dates)} days)")

    # 5) index.html 생성
    print(f"\n{'='*60}")
    print("  Generating index.html...")
    generate.generate_index()
    print(f"{'='*60}")

    # 임시 CSV 정리
    if os.path.exists(tmp_csv):
        os.remove(tmp_csv)

    # 결과 요약
    print(f"\n=== Simulation Complete ===")
    print(f"Output directory: {SIM_DIR}")
    for root, dirs, files in os.walk(SIM_DIR):
        level = root.replace(SIM_DIR, "").count(os.sep)
        indent = "  " * level
        dirname = os.path.basename(root) or "simulation/"
        print(f"{indent}{dirname}/")
        sub_indent = "  " * (level + 1)
        for f in sorted(files):
            fpath = os.path.join(root, f)
            size = os.path.getsize(fpath)
            print(f"{sub_indent}{f} ({size:,} bytes)")


if __name__ == "__main__":
    run_simulation()
