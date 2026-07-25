"""scripts/auto_market.py — 일일 시장 보고서 완전 자동화

일 18:50 + 화~금 06:50 KST macOS launchd가 이 스크립트를 실행한다.

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

from dotenv import load_dotenv

from _utils import prev_business_day as _prev_biz_util, telegram_send

# ── 경로 설정 ─────────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")

GITHUB_PAGES = "https://traderparamita.github.io/market-summary"

KST = ZoneInfo("Asia/Seoul")

# nvm 기본 노드 버전의 claude 경로 (launchd는 nvm PATH를 모름)
NVM_NODE_DEFAULT = Path.home() / ".nvm" / "alias" / "default"
CLAUDE_CANDIDATES = [
    # macOS / Linux
    Path("/usr/local/bin/claude"),
    Path("/opt/homebrew/bin/claude"),
    Path.home() / ".local" / "bin" / "claude",
    # Windows
    Path.home() / ".local" / "bin" / "claude.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "claude" / "claude.exe",
    Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
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
    """실행 시점 기준 전 영업일 = 보고서 대상 날짜.

    일요일 18:50 실행 → 직전 영업일 (보통 금요일, 공휴일이면 그 전)
    화~금  06:50 실행 → 직전 영업일 (보통 전날, 공휴일이면 그 전)
    """
    today = datetime.now(KST).date()
    return _prev_biz_util(today).isoformat()


def should_skip() -> bool:
    """월요일·일요일은 스킵 (토요일이 금요일 보고서 담당)."""
    wd = datetime.now(KST).date().weekday()
    return wd in (0, 6)  # 0=월, 6=일


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
# 3. Claude Code로 market-full 실행 (Part A + Part B 분리)
# ─────────────────────────────────────────────────────────────

def _build_claude_env(claude_bin: str) -> dict:
    """claude 실행용 환경변수 반환 (ANTHROPIC_API_KEY 제거, UTF-8 강제)."""
    import platform as _platform
    clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    sep = ";" if _platform.system() == "Windows" else ":"
    if _platform.system() == "Windows":
        path_extra = str(Path(claude_bin).parent)
        extra = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    else:
        path_extra = (
            str(Path(claude_bin).parent)
            + ":/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
        )
        extra = {"HOME": str(Path.home()), "LANG": "ko_KR.UTF-8"}
    return {**clean_env, "PATH": path_extra + sep + clean_env.get("PATH", ""), **extra}


def _run_claude(prompt: str, persist_prompt: str, label: str, timeout: int = 3600) -> bool:
    """claude --dangerously-skip-permissions 로 단일 커맨드 실행."""
    claude_bin = find_claude()
    if not claude_bin:
        print("[ERROR] claude CLI를 찾을 수 없습니다.")
        print("        후보 경로: " + ", ".join(str(p) for p in CLAUDE_CANDIDATES))
        return False

    print(f"\n{label}: {claude_bin}")
    print(f"      {prompt}")

    result = subprocess.run(
        [
            claude_bin,
            "--dangerously-skip-permissions",
            "--verbose",
            "--append-system-prompt", persist_prompt,
            "-p", prompt,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_build_claude_env(claude_bin),
    )

    # 출력 마지막 200줄 기록 (진단 가시성 향상)
    if result.stdout:
        lines = result.stdout.strip().splitlines()
        print("\n".join(lines[-200:]))
    if result.stderr:
        print("[STDERR]", result.stderr[-500:])

    if result.returncode != 0:
        print(f"[ERROR] claude 실행 실패 (exit {result.returncode})")
        return False

    print("  → 완료")
    return True


def run_market_full(date_str: str) -> bool:
    """Part A: 데이터 수집 + Market Story (Step 0 ~ Step 3 + 3-E)."""
    persist_prompt = (
        "/market-full (Part A): generate.py 가 출력하는 '[Step 1~2 완료]' 또는 'Done!' 은 "
        "데이터 단계만 끝난 신호이다. 반드시 Step 3 (Market Story, Sources 주입 포함) → "
        "Step 3-E (Catalysts) → Step 4/6 (주간·월간 Dashboard 파일 존재 확인) 을 완수한 뒤 "
        "'완료 보고 (Part A)' 표를 출력하고 종료하라. "
        "CS·PM·Stocks·검증·push 는 /market-full-b (Part B) 가 담당하므로 여기서 하지 않는다."
    )
    return _run_claude(
        prompt=f"/market-full {date_str}",
        persist_prompt=persist_prompt,
        label="[1/4] Claude Part A (/market-full)",
        timeout=2400,  # 40분: 데이터 수집 + Market Story 웹 검색
    )


def run_market_full_b(date_str: str) -> bool:
    """Part B: CS·PM·Stocks → 주간·월간 Story → 수치 검증 → git push (Step 3-B ~ Step 9)."""
    persist_prompt = (
        "/market-full-b (Part B): Part A 에서 생성된 _story.html 을 기반으로 "
        "Step 3-B(CS) → 3-C(PM) → 3-D(Stocks) 를 순서대로 완수하라. "
        "이후 캘린더 체크로 마지막 영업일 여부를 확인해 Step 5/7(주간·월간 Story) 실행 여부를 결정하고, "
        "Step 7.7(수치 검증) → 8(git push) → 9(Telegram) 까지 모두 완수한 뒤 "
        "'완료 보고 (Part B)' 표를 출력하고 종료하라."
    )
    return _run_claude(
        prompt=f"/market-full-b {date_str}",
        persist_prompt=persist_prompt,
        label="[2/4] Claude Part B (/market-full-b)",
        timeout=3600,  # 60분: CS+PM+Stocks+주간·월간(금요일)+검증+push
    )


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

    return telegram_send("\n".join(lines), parse_mode="HTML")


def _git_head() -> str:
    """현재 HEAD 커밋 해시 (짧은 7자). 실패 시 빈 문자열."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def send_telegram_push_blocked(date_str: str) -> None:
    """verify 위반으로 git push가 차단됐을 때 Telegram 알림."""
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    wd = weekdays[date.fromisoformat(date_str).weekday()]
    now_kst = datetime.now(KST).strftime("%H:%M KST")
    lines = [
        "⚠️ <b>Market Summary — git push 차단</b>",
        f"📅 {date_str} ({wd})",
        f"⏱ {now_kst}",
        "",
        "수치 검증(Step 7.7) 위반이 남아 git push가 차단됐습니다.",
        "로그: <code>logs/verify_numbers.log</code>",
    ]
    telegram_send("\n".join(lines), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────
# 6. 메인
# ─────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) > 1:
        date_str = sys.argv[1]          # 수동 지정 (테스트용)
    else:
        if should_skip():
            print("월요일/일요일입니다. 실행을 건너뜁니다.")
            return
        date_str = prev_business_day()  # 전 영업일 자동 계산

    print("=" * 52)
    print(f"  Auto Market Report — {date_str}")
    print("=" * 52)

    # ── Part A: 데이터 수집 + Market Story ───────────────────────────
    ok_a = run_market_full(date_str)
    if not ok_a:
        metrics = load_metrics(date_str)
        send_telegram(date_str, metrics, False)
        return

    # ── Part B: CS·PM·Stocks → 주간·월간 → 검증 → push ───────────────
    head_before = _git_head()
    ok_b = run_market_full_b(date_str)
    if not ok_b:
        metrics = load_metrics(date_str)
        send_telegram(date_str, metrics, False)
        return

    # Claude exit 0이어도 verify 위반으로 push를 건너뛰었을 수 있음 — 커밋 해시로 판별
    head_after = _git_head()
    if head_before and head_after and head_before == head_after:
        print(f"[WARN] Part B 완료했으나 커밋 해시 변화 없음 ({head_before}) — push 차단됨")
        send_telegram_push_blocked(date_str)
        return

    # ── S3 증분 업로드 ────────────────────────────────────────────────
    print("\n[3/4] S3 업로드 (market-summary/summary/) ...")
    s3_ok = False
    s3_summary = ""
    try:
        s3_result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sync_summary_s3.py")],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        s3_summary = s3_result.stdout.strip()
        print(s3_summary)
        if s3_result.returncode == 0:
            s3_ok = True
        else:
            print(f"  [WARN] S3 업로드 일부 실패 (exit {s3_result.returncode})")
            s3_summary += f"\n(exit {s3_result.returncode})"
    except Exception as e:
        s3_summary = f"S3 업로드 실패: {e}"
        print(f"  [WARN] {s3_summary}")

    # S3 결과 Telegram 알림
    now_kst = datetime.now(KST).strftime("%H:%M KST")
    if s3_ok:
        # 업로드 건수 파싱 (예: "완료: 12개 업로드 / 0개 오류")
        import re as _re
        m = _re.search(r"(\d+)개 업로드", s3_summary)
        n = m.group(1) if m else "?"
        telegram_send(
            f"☁️ <b>S3 업로드 완료</b> — {date_str}\n"
            f"📁 market-summary/summary/ ({n}개 파일)\n"
            f"⏱ {now_kst}",
            parse_mode="HTML",
        )
    else:
        telegram_send(
            f"⚠️ <b>S3 업로드 실패</b> — {date_str}\n"
            f"<code>{s3_summary[:300]}</code>\n"
            f"⏱ {now_kst}",
            parse_mode="HTML",
        )

    # ── RDS drift 검증 (P0 운영 안정성 강화) ────────────────────────
    # CSV ↔ market_daily/macro_daily 일치 여부 자동 검증. 불일치 시 Telegram 알림.
    print("\n[4/4] RDS drift 검증 ...")
    try:
        drift_result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_rds_drift.py"), date_str],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120,
        )
        print(drift_result.stdout[-2000:])
        if drift_result.returncode == 0:
            print("  → 일치 확인")
        else:
            print(f"  [WARN] drift 감지 (exit {drift_result.returncode}) — Telegram 알림 발송됨")

    except Exception as e:
        print(f"  [WARN] drift 검증 자체 실패: {e}")




if __name__ == "__main__":
    main()
