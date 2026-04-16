"""scripts/auto_market.py — 일일 시장 보고서 완전 자동화

매일 06:50 KST macOS launchd가 이 스크립트를 실행한다.

  claude --dangerously-skip-permissions -p "/market-full DATE"

로 전체 워크플로우를 Claude가 직접 수행:
  - generate.py (데이터 + HTML)
  - Market Story 작성 (일/주/월)
  - git commit + push
  - Telegram 알림 (완료 후)

Usage:
    .venv/bin/python scripts/auto_market.py            # 오늘 날짜
    .venv/bin/python scripts/auto_market.py 2026-04-14 # 특정 날짜 (테스트)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# ── 경로 설정 ─────────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GITHUB_PAGES     = "https://traderparamita.github.io/market-summary"

KST = ZoneInfo("Asia/Seoul")

# nvm 기본 노드 버전의 claude 경로 (launchd는 nvm PATH를 모름)
NVM_NODE_DEFAULT = Path.home() / ".nvm" / "alias" / "default"
CLAUDE_CANDIDATES = [
    Path("/usr/local/bin/claude"),
    Path("/opt/homebrew/bin/claude"),
    Path.home() / ".local" / "bin" / "claude",
]

# 핵심 지표: (섹션, 이름, 표시라벨, 이모지)
KEY_METRICS = [
    ("equity",    "KOSPI",    "KOSPI",   "🇰🇷"),
    ("equity",    "S&P500",   "S&P500",  "🇺🇸"),
    ("equity",    "NASDAQ",   "NASDAQ",  "💻"),
    ("fx",        "USD/KRW",  "USD/KRW", "💵"),
    ("commodity", "WTI",      "WTI",     "🛢"),
    ("commodity", "Gold",     "Gold",    "🥇"),
    ("risk",      "VIX",      "VIX",     "😰"),
    ("bond",      "US 10Y",   "US 10Y",  "📈"),
]


# ─────────────────────────────────────────────────────────────
# 1. 날짜 유틸
# ─────────────────────────────────────────────────────────────

def prev_business_day() -> str:
    """06:50 KST 실행 시점 기준 전 영업일 = 보고서 대상 날짜.

    실행일(스크립트 구동일)과 보고서 날짜는 다르다:
      월요일 06:50 실행 → 금요일 보고서
      화~금  06:50 실행 → 전날 보고서
    """
    today = datetime.now(KST).date()
    days_back = 3 if today.weekday() == 0 else 1  # 월=금요일, 그 외=전날
    return (today - timedelta(days=days_back)).isoformat()


def is_weekend() -> bool:
    return datetime.now(KST).date().weekday() >= 5


# ─────────────────────────────────────────────────────────────
# 2. claude 바이너리 탐색
# ─────────────────────────────────────────────────────────────

def find_claude() -> str | None:
    """claude CLI 바이너리 경로 반환. 못 찾으면 None."""

    # 후보 1: 고정 경로들
    for p in CLAUDE_CANDIDATES:
        if p.exists():
            return str(p)

    # 후보 2: nvm default 버전에서 찾기
    # ~/.nvm/alias/default 파일에 버전 번호가 있음 (예: "24")
    if NVM_NODE_DEFAULT.exists():
        nvm_ver = NVM_NODE_DEFAULT.read_text().strip()
        nvm_root = Path.home() / ".nvm" / "versions" / "node"
        # "24" → v24.x.x 최신 디렉터리 검색
        candidates = sorted(nvm_root.glob(f"v{nvm_ver}*/bin/claude"), reverse=True)
        if not candidates:
            # 정확한 버전 매칭 실패 시 전체 검색
            candidates = sorted(nvm_root.glob("v*/bin/claude"), reverse=True)
        if candidates:
            return str(candidates[0])

    # 후보 3: PATH에서 찾기 (launchd PATH가 좁아 보통 실패하지만 시도)
    import shutil
    found = shutil.which("claude")
    return found


# ─────────────────────────────────────────────────────────────
# 3. Claude Code로 market-full 실행
# ─────────────────────────────────────────────────────────────

def run_market_full(date_str: str) -> bool:
    """claude --dangerously-skip-permissions 로 전체 워크플로우 실행."""
    claude_bin = find_claude()
    if not claude_bin:
        print("[ERROR] claude CLI를 찾을 수 없습니다.")
        print("        후보 경로: " + ", ".join(str(p) for p in CLAUDE_CANDIDATES))
        return False

    print(f"\n[1/2] Claude Code 실행: {claude_bin}")
    print(f"      /market-full {date_str}")

    prompt = f"/market-full {date_str}"

    result = subprocess.run(
        [claude_bin, "--dangerously-skip-permissions", "-p", prompt],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=3600,   # Story 작성 + 웹 검색 포함 최대 1시간
        env={
            **os.environ,
            # nvm PATH 보강
            "PATH": (
                str(Path(claude_bin).parent)
                + ":/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
                + ":/opt/homebrew/bin"
            ),
            "HOME":     str(Path.home()),
            "LANG":     "ko_KR.UTF-8",
        },
    )

    # 출력 마지막 50줄 기록
    if result.stdout:
        lines = result.stdout.strip().splitlines()
        print("\n".join(lines[-50:]))
    if result.stderr:
        print("[STDERR]", result.stderr[-300:])

    if result.returncode != 0:
        print(f"[ERROR] claude 실행 실패 (exit {result.returncode})")
        return False

    print("  → 완료")
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
            "label": label,
            "icon":  icon,
            "close": asset.get("close"),
            "daily": asset.get("daily"),
        })
    return metrics


# ─────────────────────────────────────────────────────────────
# 5. Telegram 알림
# ─────────────────────────────────────────────────────────────

def _fmt_chg(chg: float | None) -> str:
    if chg is None:
        return ""
    sign  = "+" if chg > 0 else ""
    arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "–")
    return f" {arrow} {sign}{chg:.2f}%"


def send_telegram(date_str: str, metrics: list[dict], success: bool) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 → 알림 생략")
        return False

    print("\n[2/2] Telegram 알림 발송 ...")

    yyyy_mm    = date_str[:7]
    report_url = f"{GITHUB_PAGES}/summary/{yyyy_mm}/{date_str}.html"
    now_kst    = datetime.now(KST).strftime("%H:%M KST")
    weekdays   = ["월", "화", "수", "목", "금", "토", "일"]
    wd         = weekdays[date.fromisoformat(date_str).weekday()]

    if success:
        lines = [
            "📊 <b>Market Summary 배포 완료</b>",
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
        lines += ["", f"⏱ {now_kst}"]
    else:
        lines = [
            "❌ <b>Market Summary 생성 실패</b>",
            f"📅 {date_str} ({wd})",
            f"⏱ {now_kst}",
            "로그: <code>logs/auto_market.log</code>",
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
        print(f"  [ERROR] Telegram {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"  [ERROR] Telegram 전송 실패: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# 6. 메인
# ─────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) > 1:
        date_str = sys.argv[1]          # 수동 지정 (테스트용)
    else:
        if is_weekend():
            print("주말입니다. 실행을 건너뜁니다.")
            return
        date_str = prev_business_day()  # 전 영업일 자동 계산

    print("=" * 52)
    print(f"  Auto Market Report — {date_str}")
    print("=" * 52)

    ok = run_market_full(date_str)

    # 성공 시 Telegram은 Claude market-full Step 10(notify_telegram.py)이 담당.
    # 실패 시에만 여기서 오류 알림 발송.
    if not ok:
        metrics = load_metrics(date_str)
        send_telegram(date_str, metrics, ok)


if __name__ == "__main__":
    main()
