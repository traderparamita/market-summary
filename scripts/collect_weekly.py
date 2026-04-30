"""주간 보고서 수집 러너 — 매주 일요일 19:30 KST launchd 실행.

1. 미래에셋증권 상세분석 보고서 (collect_securities_reports.py)
2. MVP PRISM 보고서 (collect_prism_reports.py)
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PYTHON = sys.executable
KST = ZoneInfo("Asia/Seoul")

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHILLIA_CHAT_ID = os.getenv("ANTHILLIA_CHAT_ID", "")

COLLECTORS = [
    ("미래에셋증권 상세분석", "collect_securities_reports.py"),
    ("MVP PRISM", "collect_prism_reports.py"),
    ("주간 리서치 다이제스트", "generate_securities_digest.py"),
    ("Securities Index 재생성", "generate_securities_index.py"),
]


def _send_telegram(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 → 알림 생략")
        return
    chat_ids = [TELEGRAM_CHAT_ID]
    if ANTHILLIA_CHAT_ID and ANTHILLIA_CHAT_ID != TELEGRAM_CHAT_ID:
        chat_ids.append(ANTHILLIA_CHAT_ID)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for cid in chat_ids:
        try:
            requests.post(url, json={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=10)
        except Exception as e:
            print(f"  [WARN] Telegram 발송 실패 ({cid}): {e}")


def main() -> None:
    start_dt = datetime.now(KST)
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S KST")

    print("=" * 52)
    print("  주간 보고서 수집")
    print(f"  시작: {start_str}")
    print("=" * 52)

    results: list[tuple[str, bool, str]] = []  # (label, ok, summary)

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
            ok = result.returncode == 0
            if not ok:
                print(f"  [WARN] {label} exit {result.returncode}")
            # 업로드/스킵 숫자 추출 (요약용)
            summary = ""
            for line in result.stdout.splitlines():
                if "업로드" in line or "완료" in line:
                    summary = line.strip()
                    break
            results.append((label, ok, summary))
        except Exception as e:
            print(f"  [ERROR] {label}: {e}")
            results.append((label, False, str(e)))

    end_dt = datetime.now(KST)
    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S KST")
    elapsed = int((end_dt - start_dt).total_seconds())

    print(f"\n완료. (종료: {end_str}, 소요: {elapsed}s)")

    # 텔레그램 알림
    all_ok = all(ok for _, ok, _ in results)
    status_icon = "✅" if all_ok else "⚠️"
    lines = [
        f"{status_icon} <b>주간 보고서 수집 {'완료' if all_ok else '일부 실패'}</b>",
        f"🕐 시작: {start_str}",
        f"🕑 종료: {end_str}  ({elapsed}s)",
        "",
    ]
    for label, ok, summary in results:
        icon = "✅" if ok else "❌"
        lines.append(f"{icon} {label}" + (f"  {summary}" if summary else ""))
    _send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
