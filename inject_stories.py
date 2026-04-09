#!/usr/local/bin/python3.12
"""
시뮬레이션 보고서에 Market Story HTML을 주입하는 스크립트
simulation/stories/ 폴더의 원본 Story를 읽어 simulation/ 보고서에 주입
주입 후 _save_story_file()로 별도 파일에도 저장
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIM_DIR = os.path.join(BASE_DIR, "simulation")
STORIES_DIR = os.path.join(SIM_DIR, "stories")

# generate.py의 _inject_existing_story / _save_story_file 재사용
sys.path.insert(0, BASE_DIR)
from generate import _inject_existing_story


def main():
    if not os.path.exists(STORIES_DIR):
        print(f"Stories directory not found: {STORIES_DIR}")
        return

    # 일간 Story 주입
    print("=== Injecting Daily Stories ===")
    for date in ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]:
        story_file = os.path.join(STORIES_DIR, f"{date}_story.html")
        report_path = os.path.join(SIM_DIR, "2026-03", f"{date}.html")
        if not os.path.exists(story_file):
            print(f"  [SKIP] Story not found: {os.path.basename(story_file)}")
            continue
        if not os.path.exists(report_path):
            print(f"  [SKIP] Report not found: {os.path.basename(report_path)}")
            continue
        # Story를 HTML에 주입
        with open(story_file) as f:
            story_html = f.read()
        with open(report_path) as f:
            content = f.read()
        content = content.replace("<!-- STORY_CONTENT_PLACEHOLDER -->", story_html)
        # _inject_existing_story로 저장 (→ _save_story_file도 자동 호출)
        with open(report_path, "w") as f:
            f.write(content)
        # 별도 _story.html 저장
        from generate import _save_story_file
        _save_story_file(report_path, content)
        print(f"  [OK] {os.path.basename(report_path)}")

    # 주간 Story 주입
    print("\n=== Injecting Weekly Story ===")
    _inject_from_source(
        os.path.join(STORIES_DIR, "weekly_W10_story.html"),
        os.path.join(SIM_DIR, "weekly", "2026-W10.html"),
    )

    # 월간 Story 주입
    print("\n=== Injecting Monthly Story ===")
    _inject_from_source(
        os.path.join(STORIES_DIR, "monthly_03_story.html"),
        os.path.join(SIM_DIR, "monthly", "2026-03.html"),
    )

    print("\nDone!")


def _inject_from_source(story_file, report_path):
    if not os.path.exists(story_file):
        print(f"  [SKIP] {os.path.basename(story_file)} not found")
        return
    if not os.path.exists(report_path):
        print(f"  [SKIP] {os.path.basename(report_path)} not found")
        return
    with open(story_file) as f:
        story_html = f.read()
    with open(report_path) as f:
        content = f.read()
    content = content.replace("<!-- STORY_CONTENT_PLACEHOLDER -->", story_html)
    with open(report_path, "w") as f:
        f.write(content)
    from generate import _save_story_file
    _save_story_file(report_path, content)
    print(f"  [OK] {os.path.basename(report_path)}")


if __name__ == "__main__":
    main()
