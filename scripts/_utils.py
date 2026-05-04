"""scripts/ 공통 유틸리티.

- business_day: 영업일 계산 (한국 공휴일 반영)
- telegram_send: multi-chat Telegram 발송
- S3_BUCKET: 공용 S3 버킷명
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ── S3 ────────────────────────────────────────────────────────
S3_BUCKET = os.getenv(
    "S3_BUCKET_NAME",
    "mai-life-fund-documents-533370893966-ap-northeast-2-an",
)

# ── Telegram ──────────────────────────────────────────────────
_BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID", "")
_ANTHILLIA_ID  = os.getenv("ANTHILLIA_CHAT_ID", "")


def telegram_send(text: str, *, parse_mode: str = "HTML") -> bool:
    """개인 채팅 + Anthillia 그룹 동시 발송.

    Returns True if all messages succeeded.
    """
    if not _BOT_TOKEN or not _CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 → 알림 생략")
        return False
    chat_ids = [_CHAT_ID]
    if _ANTHILLIA_ID and _ANTHILLIA_ID != _CHAT_ID:
        chat_ids.append(_ANTHILLIA_ID)
    url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
    ok = True
    for cid in chat_ids:
        try:
            resp = requests.post(
                url,
                json={"chat_id": cid, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            if resp.ok:
                print(f"  → Telegram 발송 완료 ({cid})")
            else:
                print(f"  [ERROR] Telegram {resp.status_code} ({cid}): {resp.text[:200]}")
                ok = False
        except Exception as e:
            print(f"  [ERROR] Telegram 전송 오류 ({cid}): {e}")
            ok = False
    return ok


# ── 영업일 계산 ────────────────────────────────────────────────

def _kr_holidays(years: list[int]) -> set:
    try:
        import holidays
        return holidays.KR(years=years)
    except ImportError:
        return set()


def prev_business_day(d: date | None = None) -> date:
    """d 직전 영업일 (한국 공휴일 반영). d=None이면 오늘 기준."""
    if d is None:
        d = date.today()
    kr_hols = _kr_holidays([d.year, d.year - 1])
    d -= timedelta(days=1)
    while d.weekday() >= 5 or d in kr_hols:
        d -= timedelta(days=1)
    return d


def next_business_day(d: date | None = None) -> date:
    """d 다음 영업일 (한국 공휴일 반영). d=None이면 오늘 기준."""
    if d is None:
        d = date.today()
    kr_hols = _kr_holidays([d.year, d.year + 1])
    d += timedelta(days=1)
    while d.weekday() >= 5 or d in kr_hols:
        d += timedelta(days=1)
    return d


def is_business_day(d: date) -> bool:
    """영업일 여부 (주말 + 한국 공휴일 제외)."""
    if d.weekday() >= 5:
        return False
    return d not in _kr_holidays([d.year])
