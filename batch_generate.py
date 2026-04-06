#!/usr/local/bin/python3.12
"""2026-03-26 ~ 2026-04-03 영업일 일괄 생성"""
import subprocess, datetime

start = datetime.date(2026, 3, 26)
end = datetime.date(2026, 4, 3)

d = start
while d <= end:
    if d.weekday() < 5:  # 평일만
        print(f"\n{'='*60}")
        print(f"  Generating: {d}")
        print(f"{'='*60}")
        subprocess.run(["python3.12", "generate.py", str(d)])
    d += datetime.timedelta(days=1)

print("\n\nAll done!")
