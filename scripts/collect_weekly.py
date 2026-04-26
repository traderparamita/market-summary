"""주간 보고서 수집 러너 — 매주 일요일 19:30 KST launchd 실행.

1. 미래에셋증권 상세분석 보고서 (collect_securities_reports.py)
2. MVP PRISM 보고서 (collect_prism_reports.py)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

COLLECTORS = [
    ("미래에셋증권 상세분석", "collect_securities_reports.py"),
    ("MVP PRISM", "collect_prism_reports.py"),
]


def main() -> None:
    print("=" * 52)
    print("  주간 보고서 수집")
    print("=" * 52)

    for label, script in COLLECTORS:
        print(f"\n[{label}]")
        try:
            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / script)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=600,
            )
            print(result.stdout[-3000:])
            if result.stderr:
                print(result.stderr[-500:])
            if result.returncode != 0:
                print(f"  [WARN] {label} exit {result.returncode}")
        except Exception as e:
            print(f"  [ERROR] {label}: {e}")

    print("\n완료.")


if __name__ == "__main__":
    main()
