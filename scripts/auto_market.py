"""scripts/auto_market.py — 일일 시장 보고서 자동화

매일 08:05 KST macOS launchd가 이 스크립트를 실행한다.
  1. generate.py 실행 (데이터 수집 + HTML 생성 + Snowflake dual-write)
  2. git add / commit / push (output/ + history/market_data.csv)
  3. Telegram 알림 (배포 완료 + 핵심 지표)

Story 작성은 Claude가 필요하므로 별도 (Claude Code 세션 CronCreate 활용).

Usage:
    .venv/bin/python scripts/auto_market.py            # 오늘 날짜
    .venv/bin/python scripts/auto_market.py 2026-04-14 # 특정 날짜 (테스트)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# ── 경로 설정 ─────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
LOG_DIR     = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GITHUB_PAGES     = "https://traderparamita.github.io/market-summary"

KST = ZoneInfo("Asia/Seoul")

# 핵심 지표: (섹션, 이름, 표시라벨, 이모지)
KEY_METRICS = [
    ("equity",    "KOSPI",     "KOSPI",    "🇰🇷"),
    ("equity",    "S&P500",    "S&P500",   "🇺🇸"),
    ("equity",    "NASDAQ",    "NASDAQ",   "💻"),
    ("fx",        "USD/KRW",   "USD/KRW",  "💵"),
    ("commodity", "WTI",       "WTI",      "🛢"),
    ("commodity", "Gold",      "Gold",     "🥇"),
    ("risk",      "VIX",       "VIX",      "😰"),
    ("bond",      "US 10Y",    "US 10Y",   "📈"),
]


# ─────────────────────────────────────────────────────────────
# 1. 날짜 유틸
# ─────────────────────────────────────────────────────────────

def today_kst() -> str:
    return datetime.now(KST).date().isoformat()


def is_weekend(date_str: str) -> bool:
    return date.fromisoformat(date_str).weekday() >= 5


# ─────────────────────────────────────────────────────────────
# 2. generate.py 실행
# ─────────────────────────────────────────────────────────────

def run_generate(date_str: str) -> bool:
    print(f"\n[1/3] generate.py {date_str} ...")
    result = subprocess.run(
        [str(VENV_PYTHON), "generate.py", date_str],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        # 마지막 10줄만 출력
        lines = result.stdout.strip().splitlines()
        print("\n".join(lines[-10:]))
    if result.returncode != 0:
        print(f"[ERROR] generate.py 실패:\n{result.stderr[-500:]}")
        return False
    print("  → 완료")
    return True


# ─────────────────────────────────────────────────────────────
# 3. git commit + push
# ─────────────────────────────────────────────────────────────

def git_commit_push(date_str: str) -> bool:
    print("\n[2/3] git commit + push ...")

    def run(cmd: list[str]) -> tuple[bool, str]:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        return r.returncode == 0, r.stdout + r.stderr

    # stage
    ok, _ = run(["git", "add", "output/", "history/market_data.csv"])
    if not ok:
        print("[ERROR] git add 실패")
        return False

    # commit (nothing-to-commit은 OK)
    ok, out = run(["git", "commit", "-m", f"market: {date_str} daily report"])
    if not ok and "nothing to commit" not in out:
        print(f"[ERROR] git commit 실패:\n{out}")
        return False

    # push
    ok, out = run(["git", "push", "origin", "main"])
    if not ok:
        print(f"[ERROR] git push 실패:\n{out}")
        return False

    print("  → push 완료")
    return True


# ─────────────────────────────────────────────────────────────
# 4. _data.json 핵심 지표 추출
# ─────────────────────────────────────────────────────────────

def load_metrics(date_str: str) -> list[dict]:
    yyyy_mm = date_str[:7]
    path = ROOT / "output" / "summary" / yyyy_mm / f"{date_str}_data.json"
    if not path.exists():
        return []

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    metrics = []
    for section, key, label, icon in KEY_METRICS:
        asset = data.get(section, {}).get(key)
        if not asset:
            continue
        metrics.append({
            "label":  label,
            "icon":   icon,
            "close":  asset.get("close"),
            "daily":  asset.get("daily"),      # % change
            "weekly": asset.get("weekly"),
        })
    return metrics


# ─────────────────────────────────────────────────────────────
# 5. Telegram 알림
# ─────────────────────────────────────────────────────────────

def _fmt_chg(chg: float | None) -> str:
    if chg is None:
        return ""
    sign = "+" if chg > 0 else ""
    arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "–")
    return f" {arrow} {sign}{chg:.2f}%"


def send_telegram(date_str: str, metrics: list[dict], success: bool) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 → 알림 생략")
        return False

    print("\n[3/3] Telegram 알림 발송 ...")

    yyyy_mm   = date_str[:7]
    report_url = f"{GITHUB_PAGES}/summary/{yyyy_mm}/{date_str}.html"
    now_kst    = datetime.now(KST).strftime("%H:%M KST")
    weekdays   = ["월", "화", "수", "목", "금", "토", "일"]
    wd         = weekdays[date.fromisoformat(date_str).weekday()]

    if success:
        lines = [
            f"📊 <b>Market Summary 배포 완료</b>",
            f"📅 {date_str} ({wd})",
            f'🔗 <a href="{report_url}">보고서 열기</a>',
            "",
        ]
        for m in metrics:
            close = m["close"]
            chg   = m["daily"]
            close_str = (
                f"{close:,.0f}" if close and close > 100
                else f"{close:.2f}" if close else "—"
            )
            lines.append(f"{m['icon']} {m['label']}: {close_str}{_fmt_chg(chg)}")

        lines += ["", f"⏱ {now_kst}  |  📝 Story 작성 필요"]
    else:
        lines = [
            "❌ <b>Market Summary 생성 실패</b>",
            f"📅 {date_str} ({wd})",
            f"⏱ {now_kst}",
            "서버 로그를 확인해주세요.",
            f"<code>logs/auto_market.log</code>",
        ]

    text = "\n".join(lines)
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id":                  TELEGRAM_CHAT_ID,
                "text":                     text,
                "parse_mode":               "HTML",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        if resp.ok:
            print("  → 발송 완료")
            return True
        else:
            print(f"  [ERROR] Telegram API: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"  [ERROR] Telegram 전송 실패: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# 6. 메인
# ─────────────────────────────────────────────────────────────

def main() -> None:
    date_str = sys.argv[1] if len(sys.argv) > 1 else today_kst()

    print("=" * 52)
    print(f"  Auto Market Report — {date_str}")
    print("=" * 52)

    if is_weekend(date_str) and len(sys.argv) <= 1:
        print("주말입니다. 실행을 건너뜁니다.")
        return

    ok_gen = run_generate(date_str)
    if ok_gen:
        ok_push   = git_commit_push(date_str)
        metrics   = load_metrics(date_str)
        send_telegram(date_str, metrics, ok_push)
    else:
        send_telegram(date_str, [], False)


if __name__ == "__main__":
    main()
