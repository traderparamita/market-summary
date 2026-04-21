"""
Telegram 알림 전송 — market-full Step 10
사용: .venv/bin/python notify_telegram.py YYYY-MM-DD [--weekly] [--monthly]
"""

import json
import sys
import argparse
import os
import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHILLIA_ID  = os.getenv("ANTHILLIA_CHAT_ID", "")  # LL 두 개. 빈 값이면 이중 발송 안 함
GITHUB_PAGES = "https://traderparamita.github.io/market-summary"


def _sign(v: float) -> str:
    return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"


def _arrow(v: float) -> str:
    return "▲" if v > 0 else ("▼" if v < 0 else "—")


def _asset(data: dict, category: str, key: str) -> dict | None:
    return data.get(category, {}).get(key)


def build_message(date_str: str, data: dict, is_weekly: bool, is_monthly: bool, focus: str = "") -> str:
    eq = data.get("equity", {})
    fx = data.get("fx", {})
    risk = data.get("risk", {})
    commodity = data.get("commodity", {})
    bond = data.get("bond", {})

    kospi = eq.get("KOSPI", {})
    sp500 = eq.get("S&P500", {})
    nasdaq = eq.get("NASDAQ", {})
    gold = commodity.get("Gold", {})
    wti = commodity.get("WTI", {})
    vix = risk.get("VIX", {})
    dxy = fx.get("DXY", {})
    usdkrw = fx.get("USD/KRW", {})

    # 날짜·요일
    dt = datetime.date.fromisoformat(date_str)
    weekday_ko = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]

    lines = []

    # 헤더
    period_tag = ""
    if is_monthly:
        period_tag = " 📅 월간 마감"
    elif is_weekly:
        period_tag = " 📋 주간 마감"
    lines.append(f"📊 *{date_str}({weekday_ko}) 시장 브리핑*{period_tag}")
    lines.append("")

    # 핵심 지수
    lines.append("*🌏 주요 지수*")
    if kospi:
        holiday_note = " _(휴장)_" if kospi.get("holiday") else ""
        lines.append(f"  KOSPI  {_arrow(kospi.get('daily',0))} {_sign(kospi.get('daily',0))}{holiday_note}")
    if sp500:
        lines.append(f"  S&P500 {_arrow(sp500.get('daily',0))} {_sign(sp500.get('daily',0))}")
    if nasdaq:
        lines.append(f"  NASDAQ {_arrow(nasdaq.get('daily',0))} {_sign(nasdaq.get('daily',0))}")
    lines.append("")

    # 주요 지표
    lines.append("*📌 주요 지표*")
    if vix:
        lines.append(f"  VIX    {vix.get('close', '—'):.2f} ({_sign(vix.get('daily', 0))})")
    if gold:
        lines.append(f"  Gold   {_sign(gold.get('daily', 0))}  (주간 {_sign(gold.get('weekly', 0))})")
    if wti:
        lines.append(f"  WTI    ${wti.get('close', 0):.2f}  {_sign(wti.get('daily', 0))}")
    if dxy:
        lines.append(f"  DXY    {dxy.get('close', 0):.2f}  {_sign(dxy.get('daily', 0))}")
    if usdkrw:
        lines.append(f"  USD/KRW {usdkrw.get('close', 0):,.2f}  {_sign(usdkrw.get('daily', 0))}")
    lines.append("")

    # 주간·월간 누적 (주간/월간 마감일)
    if is_weekly and sp500:
        lines.append("*📈 주간 누적*")
        parts = []
        for label, asset in [("KOSPI", kospi), ("S&P", sp500), ("Gold", gold), ("WTI", wti)]:
            if asset:
                parts.append(f"{label} {_sign(asset.get('weekly', 0))}")
        lines.append("  " + " | ".join(parts))
        lines.append("")

    if is_monthly and sp500:
        lines.append("*📅 월간 누적*")
        parts = []
        for label, asset in [("KOSPI", kospi), ("S&P", sp500), ("Gold", gold), ("WTI", wti)]:
            if asset:
                parts.append(f"{label} {_sign(asset.get('monthly', 0))}")
        lines.append("  " + " | ".join(parts))
        lines.append("")

    # 섹터·국가 포커스
    if focus:
        lines.append(f"*🎯 섹터·국가 오늘의 주제*")
        lines.append(f"  {focus}")
        lines.append("")

    # 링크
    year_month = date_str[:7]
    daily_url = f"{GITHUB_PAGES}/summary/{year_month}/{date_str}.html"

    # ISO 주차 계산
    iso_year, iso_week, _ = dt.isocalendar()
    weekly_url = f"{GITHUB_PAGES}/summary/weekly/{iso_year}-W{iso_week:02d}.html"
    monthly_url = f"{GITHUB_PAGES}/summary/monthly/{year_month}.html"
    sc_url = f"{GITHUB_PAGES}/sector-country/daily/{year_month}/{date_str}.html"

    link_parts = [f"[일간]({daily_url})", f"[주간]({weekly_url})", f"[월간]({monthly_url})", f"[섹터·국가]({sc_url})"]
    lines.append("🔗 " + "  |  ".join(link_parts))

    return "\n".join(lines)


def send(message: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠ TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정 — 전송 스킵")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # 개인 채팅 + Anthillia 그룹 동시 발송 (ANTHILLIA_CHAT_ID 설정 시)
    chat_ids = [CHAT_ID]
    if ANTHILLIA_ID and ANTHILLIA_ID != CHAT_ID:
        chat_ids.append(ANTHILLIA_ID)
    success = True
    for cid in chat_ids:
        try:
            resp = requests.post(url, json={
                "chat_id": cid,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }, timeout=10)
            if resp.status_code == 200:
                print(f"✓ Telegram 전송 완료 ({cid})")
            else:
                print(f"✗ Telegram 전송 실패 ({cid}): {resp.status_code} {resp.text}")
                success = False
        except Exception as e:
            print(f"✗ Telegram 전송 오류 ({cid}): {e}")
            success = False
    return success


def build_start_message(date_str: str, label: str = "") -> str:
    dt = datetime.date.fromisoformat(date_str)
    weekday_ko = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
    now = datetime.datetime.now().strftime("%H:%M")
    title = f"{label} 보고서 생성 시작" if label else "보고서 생성 시작"
    workflow = "데이터 수집 → Dashboard → Story → 배포" if not label else f"Dashboard → Tavily 검색 → Story 주입"
    return (
        f"⏳ *{date_str}({weekday_ko}) {title}*\n"
        f"\n"
        f"  시각: {now} KST\n"
        f"  워크플로우: {workflow}\n"
        f"\n"
        f"_완료 시 결과 브리핑을 전송합니다._"
    )


def build_sc_complete_message(date_str: str, focus: str = "", ow_sectors: str = "", uw_sectors: str = "") -> str:
    dt = datetime.date.fromisoformat(date_str)
    weekday_ko = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
    now = datetime.datetime.now().strftime("%H:%M")
    year_month = date_str[:7]
    sc_url = f"{GITHUB_PAGES}/sector-country/daily/{year_month}/{date_str}.html"

    lines = [
        f"✅ *{date_str}({weekday_ko}) 섹터·국가 보고서 완료*",
        f"",
        f"  완료 시각: {now} KST",
    ]
    if focus:
        lines += [f"", f"*🎯 오늘의 주제*", f"  {focus}"]
    if ow_sectors:
        lines += [f"", f"*▲ OW*  {ow_sectors}"]
    if uw_sectors:
        lines += [f"*▼ UW*  {uw_sectors}"]
    lines += [f"", f"🔗 [섹터·국가 보고서]({sc_url})"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="YYYY-MM-DD")
    parser.add_argument("--weekly", action="store_true", help="주간 마감일 여부")
    parser.add_argument("--monthly", action="store_true", help="월간 마감일 여부")
    parser.add_argument("--focus", default="", help="섹터·국가 오늘의 주제 텍스트")
    parser.add_argument("--start", action="store_true", help="생성 시작 알림 전송")
    parser.add_argument("--label", default="", help="시작 알림에 표시할 레이블 (예: '섹터·국가')")
    parser.add_argument("--sc-complete", action="store_true", help="섹터·국가 보고서 완료 알림")
    parser.add_argument("--ow", default="", help="OW 섹터/국가 목록 (--sc-complete용)")
    parser.add_argument("--uw", default="", help="UW 섹터/국가 목록 (--sc-complete용)")
    args = parser.parse_args()

    date_str = args.date

    if args.start:
        message = build_start_message(date_str, args.label)
        send(message)
        return

    if args.sc_complete:
        message = build_sc_complete_message(date_str, args.focus, args.ow, args.uw)
        send(message)
        return

    year_month = date_str[:7]
    data_path = ROOT / "output" / "summary" / year_month / f"{date_str}_data.json"

    if not data_path.exists():
        print(f"⚠ _data.json 없음: {data_path} — 전송 스킵")
        sys.exit(0)

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    message = build_message(date_str, data, args.weekly, args.monthly, args.focus)
    send(message)


if __name__ == "__main__":
    main()
