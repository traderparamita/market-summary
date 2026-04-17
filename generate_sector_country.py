"""섹터·국가 초보자 보고서 생성기.

compute_sector_view() + compute_country_view() 데이터를 결합해
초보자 친화 HTML Data Dashboard를 생성한다.

사이클 구조:
  - 섹터: 11일 사이클 (US SPDR 11개 × KR TIGER 200 11개 1:1 페어)
  - 국가: 10일 독립 사이클 (한국·미국 5일 간격 2회 반복)
  - 하루에 섹터 2개(US + KR) + 국가 1개 = 3개 주제

Usage:
    python generate_sector_country.py 2026-04-16        # daily (자동 주제 선택)
    python generate_sector_country.py 2026-04-16 daily
    python generate_sector_country.py 2026-04-16 weekly
    python generate_sector_country.py 2026-04-16 monthly
"""

import argparse
import math
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from portfolio.view.sector_view import compute_sector_view
from portfolio.view.country_view import compute_country_view, COUNTRIES

OUTPUT_ROOT = ROOT / "output" / "sector-country"
HISTORY_CSV = ROOT / "history" / "market_data.csv"

# ── 사이클 기준일 ─────────────────────────────────────────────────────────
# 섹터: 11일 사이클 / 국가: 10일 독립 사이클
# 기준일: 2026-01-05 (월요일)

REFERENCE_DATE = date(2026, 1, 5)

# ── 대표 주식 정의 ─────────────────────────────────────────────────────────
# 각 섹터/국가별 대표 주식 3~5개 (code, 이름, 시가총액 기준 상위)
SECTOR_REP_STOCKS = {
    # US 섹터
    "SC_US_TECH":    [("NVDA", "NVIDIA"), ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("AVGO", "Broadcom")],
    "SC_US_COMM":    [("GOOGL", "Alphabet"), ("META", "Meta"), ("NFLX", "Netflix"), ("DIS", "Disney")],
    "SC_US_FIN":     [("JPM", "JPMorgan"), ("BAC", "Bank of America"), ("V", "Visa"), ("MS", "Morgan Stanley")],
    "SC_US_ENERGY":  [("XOM", "ExxonMobil"), ("CVX", "Chevron"), ("COP", "ConocoPhillips"), ("SLB", "Schlumberger")],
    "SC_US_HEALTH":  [("UNH", "UnitedHealth"), ("LLY", "Eli Lilly"), ("JNJ", "J&J"), ("PFE", "Pfizer")],
    "SC_US_INDU":    [("GE", "GE Aerospace"), ("CAT", "Caterpillar"), ("RTX", "RTX"), ("HON", "Honeywell")],
    "SC_US_MATL":    [("LIN", "Linde"), ("APD", "Air Products"), ("FCX", "Freeport-McMoRan"), ("NEM", "Newmont")],
    "SC_US_DISCR":   [("AMZN", "Amazon"), ("TSLA", "Tesla"), ("HD", "Home Depot"), ("MCD", "McDonald's")],
    "SC_US_STAPLES": [("PG", "P&G"), ("KO", "Coca-Cola"), ("PEP", "PepsiCo"), ("WMT", "Walmart")],
    "SC_US_UTIL":    [("NEE", "NextEra Energy"), ("SO", "Southern Co"), ("DUK", "Duke Energy")],
    "SC_US_REIT":    [("PLD", "Prologis"), ("AMT", "American Tower"), ("EQIX", "Equinix")],
    # KR 섹터
    "SC_KR_CONSTR":  [("000720.KS", "현대건설"), ("047040.KS", "대우건설"), ("000080.KS", "하이트진로건설")],
    "SC_KR_DISCR":   [("005380.KS", "현대차"), ("000270.KS", "기아"), ("012330.KS", "현대모비스")],
    "SC_KR_FIN":     [("055550.KS", "신한지주"), ("105560.KS", "KB금융"), ("086790.KS", "하나금융지주")],
    "SC_KR_INDU":    [("042660.KS", "한화오션"), ("329180.KS", "HD현대중공업"), ("010140.KS", "삼성중공업")],
    "SC_KR_STAPLES": [("097950.KS", "CJ제일제당"), ("271560.KS", "오리온"), ("004370.KS", "농심")],
    "SC_KR_ENERGY":  [("051910.KS", "LG화학"), ("011170.KS", "롯데케미칼"), ("096770.KS", "SK이노베이션")],
    "SC_KR_HEAVY":   [("047050.KS", "포스코인터내셔널"), ("012450.KS", "한화에어로스페이스"), ("064350.KS", "현대로템")],
    "SC_KR_STEEL":   [("005490.KS", "POSCO홀딩스"), ("004020.KS", "현대제철"), ("010060.KS", "OCI홀딩스")],
    "SC_KR_COMM":    [("017670.KS", "SK텔레콤"), ("030200.KS", "KT"), ("032640.KS", "LG유플러스")],
    "SC_KR_HLTH":    [("068270.KS", "셀트리온"), ("207940.KS", "삼성바이오로직스"), ("128940.KS", "한미약품")],
    "SC_KR_IT":      [("005930.KS", "삼성전자"), ("000660.KS", "SK하이닉스"), ("066570.KS", "LG전자")],
}

# 국가별 대표 주식/지수 구성종목
COUNTRY_REP_STOCKS = {
    "KR": [("005930.KS", "삼성전자"), ("000660.KS", "SK하이닉스"), ("005380.KS", "현대차"), ("051910.KS", "LG화학")],
    "US": [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"), ("AMZN", "Amazon")],
    "JP": [("7203.T", "Toyota"), ("6758.T", "Sony"), ("9984.T", "SoftBank"), ("6861.T", "Keyence")],
    "CN": [("0700.HK", "Tencent"), ("9988.HK", "Alibaba"), ("3690.HK", "Meituan"), ("1810.HK", "Xiaomi")],
    "EU": [("ASML", "ASML"), ("MC.PA", "LVMH"), ("SAP", "SAP"), ("NESN.SW", "Nestlé")],
    "UK": [("SHEL.L", "Shell"), ("AZN.L", "AstraZeneca"), ("HSBA.L", "HSBC"), ("BP.L", "BP")],
    "IN": [("RELIANCE.NS", "Reliance"), ("TCS.NS", "TCS"), ("INFY.NS", "Infosys"), ("HDFCBANK.NS", "HDFC Bank")],
    "EM": [("TSM", "TSMC"), ("005930.KS", "삼성전자"), ("BABA", "Alibaba"), ("VALE3.SA", "Vale")],
}

# ── 섹터 11일 로테이션 ─────────────────────────────────────────────────────
# US SPDR 11개 × KR TIGER 200 11개 1:1 페어
SECTOR_ROTATION = [
    {
        "sector_day": 1,
        "theme": "기술·IT",
        "theme_en": "Technology & IT",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_TECH",  "name": "Technology",   "etf": "XLK"},
            {"type": "kr_sector", "code": "SC_KR_IT",    "name": "IT",           "etf": "TIGER 200 IT",               "ticker": "364980.KS"},
        ],
    },
    {
        "sector_day": 2,
        "theme": "통신·커뮤니케이션",
        "theme_en": "Communication Services",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_COMM",    "name": "Communication",  "etf": "XLC"},
            {"type": "kr_sector", "code": "SC_KR_COMM",   "name": "커뮤니케이션서비스", "etf": "TIGER 200 커뮤니케이션서비스", "ticker": "364990.KS"},
        ],
    },
    {
        "sector_day": 3,
        "theme": "금융",
        "theme_en": "Financials",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_FIN",    "name": "Financials",   "etf": "XLF"},
            {"type": "kr_sector", "code": "SC_KR_FIN",    "name": "금융",          "etf": "TIGER 200 금융",              "ticker": "435420.KS"},
        ],
    },
    {
        "sector_day": 4,
        "theme": "에너지·화학",
        "theme_en": "Energy & Chemicals",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_ENERGY", "name": "Energy",       "etf": "XLE"},
            {"type": "kr_sector", "code": "SC_KR_ENERGY", "name": "에너지화학",    "etf": "TIGER 200 에너지화학",         "ticker": "472170.KS"},
        ],
    },
    {
        "sector_day": 5,
        "theme": "헬스케어",
        "theme_en": "Health Care",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_HEALTH", "name": "Health Care",  "etf": "XLV"},
            {"type": "kr_sector", "code": "SC_KR_HLTH",   "name": "헬스케어",      "etf": "TIGER 200 헬스케어",           "ticker": "227570.KS"},
        ],
    },
    {
        "sector_day": 6,
        "theme": "산업재",
        "theme_en": "Industrials",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_INDU",   "name": "Industrials",  "etf": "XLI"},
            {"type": "kr_sector", "code": "SC_KR_INDU",   "name": "산업재",        "etf": "TIGER 200 산업재",             "ticker": "227560.KS"},
        ],
    },
    {
        "sector_day": 7,
        "theme": "소재·중공업",
        "theme_en": "Materials & Heavy Industry",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_MATL",   "name": "Materials",    "etf": "XLB"},
            {"type": "kr_sector", "code": "SC_KR_HEAVY",  "name": "중공업",        "etf": "TIGER 200 중공업",             "ticker": "157490.KS"},
        ],
    },
    {
        "sector_day": 8,
        "theme": "경기소비재",
        "theme_en": "Consumer Discretionary",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_DISCR",  "name": "Consumer Discr.", "etf": "XLY"},
            {"type": "kr_sector", "code": "SC_KR_DISCR",  "name": "경기소비재",      "etf": "TIGER 200 경기소비재",        "ticker": "227540.KS"},
        ],
    },
    {
        "sector_day": 9,
        "theme": "생활소비재",
        "theme_en": "Consumer Staples",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_STAPLES","name": "Consumer Staples","etf": "XLP"},
            {"type": "kr_sector", "code": "SC_KR_STAPLES","name": "생활소비재",      "etf": "TIGER 200 생활소비재",        "ticker": "227550.KS"},
        ],
    },
    {
        "sector_day": 10,
        "theme": "유틸리티·철강소재",
        "theme_en": "Utilities & Steel/Materials",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_UTIL",   "name": "Utilities",    "etf": "XLU"},
            {"type": "kr_sector", "code": "SC_KR_STEEL",  "name": "철강소재",      "etf": "TIGER 200 철강소재",           "ticker": "494840.KS"},
        ],
    },
    {
        "sector_day": 11,
        "theme": "부동산·건설",
        "theme_en": "Real Estate & Construction",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_REIT",   "name": "Real Estate",  "etf": "XLRE"},
            {"type": "kr_sector", "code": "SC_KR_CONSTR", "name": "건설",          "etf": "TIGER 200 건설",              "ticker": "139270.KS"},
        ],
    },
]

# ── 국가 10일 로테이션 (섹터와 독립) ──────────────────────────────────────
# 한국·미국 5일 간격으로 2회 반복
COUNTRY_ROTATION = [
    {"country_day": 1,  "code": "KR", "name": "한국",   "flag": "🇰🇷"},
    {"country_day": 2,  "code": "US", "name": "미국",   "flag": "🇺🇸"},
    {"country_day": 3,  "code": "CN", "name": "중국",   "flag": "🇨🇳"},
    {"country_day": 4,  "code": "JP", "name": "일본",   "flag": "🇯🇵"},
    {"country_day": 5,  "code": "EU", "name": "유럽",   "flag": "🇪🇺"},
    {"country_day": 6,  "code": "KR", "name": "한국",   "flag": "🇰🇷"},
    {"country_day": 7,  "code": "US", "name": "미국",   "flag": "🇺🇸"},
    {"country_day": 8,  "code": "CN", "name": "중국",   "flag": "🇨🇳"},
    {"country_day": 9,  "code": "IN", "name": "인도",   "flag": "🇮🇳"},
    {"country_day": 10, "code": "EM", "name": "신흥국", "flag": "🌍"},
]


def get_focus(date_str: str) -> dict:
    """날짜 → 오늘의 섹터(2개) + 국가(1개) 로테이션 슬롯.

    반환 형식:
    {
        "sector_day": int,      # 1~11
        "country_day": int,     # 1~10
        "theme": str,           # 섹터 테마 (예: "기술·IT")
        "country_name": str,    # 오늘의 국가 이름
        "type": "sector_country",
        "subjects": [us_sector_dict, kr_sector_dict, country_dict],
        # 이전 사이클 링크용
        "prev_sector_date": str | None,
        "prev_country_date": str | None,
    }
    """
    d = date.fromisoformat(date_str)
    elapsed = (d - REFERENCE_DATE).days

    sector_idx   = elapsed % len(SECTOR_ROTATION)
    country_idx  = elapsed % len(COUNTRY_ROTATION)

    sector_slot  = SECTOR_ROTATION[sector_idx]
    country_slot = COUNTRY_ROTATION[country_idx]

    # 이전 사이클 날짜 계산 (영업일 기준 역산)
    from datetime import timedelta as _td
    def _prev_biz_date(start: date, biz_days: int) -> date:
        """start에서 biz_days 영업일 전 날짜를 반환 (주말 건너뜀)."""
        cur = start
        counted = 0
        while counted < biz_days:
            cur -= _td(days=1)
            if cur.weekday() < 5:  # 0=Mon … 4=Fri
                counted += 1
        return cur

    prev_sector_date  = _prev_biz_date(d, len(SECTOR_ROTATION)).isoformat()
    prev_country_date = _prev_biz_date(d, len(COUNTRY_ROTATION)).isoformat()

    country_subject = {
        "type": "country",
        "code": country_slot["code"],
        "name": country_slot["name"],
        "flag": country_slot["flag"],
    }

    return {
        "sector_day":        sector_slot["sector_day"],
        "country_day":       country_slot["country_day"],
        "theme":             sector_slot["theme"],
        "theme_en":          sector_slot["theme_en"],
        "country_name":      country_slot["name"],
        "type":              "sector_country",
        "subjects":          sector_slot["subjects"] + [country_subject],
        "prev_sector_date":  prev_sector_date,
        "prev_country_date": prev_country_date,
    }


# ── 초보자 언어 변환 ──────────────────────────────────────────────────────

REGIME_KR = {
    "Goldilocks":  "골디락스",
    "Reflation":   "리플레이션",
    "Stagflation": "스태그플레이션",
    "Deflation":   "디플레이션",
    "N/A":         "국면 미확인",
}

REGIME_DESC_KR = {
    "Goldilocks":  "성장도 좋고 물가도 안정된 이상적인 경제 환경",
    "Reflation":   "경제가 살아나면서 물가도 함께 오르는 구간",
    "Stagflation": "경기는 나쁜데 물가만 오르는 가장 어려운 환경",
    "Deflation":   "경기와 물가 모두 위축되는 구간 — 방어 자산 선호",
    "N/A":         "",
}

CYCLE_KR = {
    "Early":     "회복 초기",
    "Mid":       "확장 중반",
    "Late":      "확장 후기",
    "Recession": "경기 침체",
}

CYCLE_COLOR = {
    "Early":     "#16a34a",
    "Mid":       "#2563eb",
    "Late":      "#d97706",
    "Recession": "#dc2626",
}


def _rep_stocks_html(code: str, is_country: bool = False) -> str:
    """대표 주식 칩 HTML."""
    stocks = (COUNTRY_REP_STOCKS if is_country else SECTOR_REP_STOCKS).get(code, [])
    if not stocks:
        return ""
    chips = "".join(
        f'<span class="rep-stock">{name}</span>'
        for _, name in stocks
    )
    return f'<div class="rep-stocks">{chips}</div>'


def _prev_cycle_link_html(prev_date: str, label: str) -> str:
    """이전 사이클 보고서 링크 HTML."""
    if not prev_date:
        return ""
    ym = prev_date[:7]
    url = f"../../daily/{ym}/{prev_date}.html"
    return (
        f'<a href="{url}" class="prev-cycle-link" target="_blank">'
        f'↩ 이전 사이클 ({prev_date}) {label}'
        f'</a>'
    )


def _chg_span(v, na="—") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return na
    color = "#16a34a" if v >= 0 else "#dc2626"
    return f'<span style="color:{color};font-weight:600">{v:+.2f}%</span>'


def _week_label(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def _month_label(date_str: str) -> str:
    return date_str[:7]


# ── CSS ───────────────────────────────────────────────────────────────────

_BASE_CSS = """
<style>
:root {
  --orange: #F58220;
  --navy:   #043B72;
  --bg:     #f8fafc;
  --card:   #ffffff;
  --text:   #1e293b;
  --muted:  #64748b;
  --border: #e2e8f0;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Spoqa Han Sans Neo', 'Noto Sans KR', sans-serif;
  background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.6;
}
.header {
  background: var(--navy); color: #fff; padding: 20px 32px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}
.header-title { font-size: 20px; font-weight: 700; }
.header-sub   { font-size: 13px; color: #93c5fd; }
.badge { padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.main { max-width: 1400px; margin: 0 auto; padding: 24px 20px; }

/* 오늘의 주제 배너 */
.focus-banner {
  background: linear-gradient(135deg, var(--navy) 0%, #1e40af 100%);
  color: #fff; border-radius: 14px; padding: 20px 24px; margin-bottom: 24px;
  display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
}
.focus-label { font-size: 11px; color: #93c5fd; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
.focus-theme { font-size: 22px; font-weight: 800; margin: 4px 0; }
.focus-en    { font-size: 12px; color: #93c5fd; }
.focus-chips { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
.focus-chip {
  background: rgba(255,255,255,0.15); border-radius: 8px; padding: 6px 14px;
  font-size: 13px; font-weight: 600;
}
.focus-day { margin-left: auto; font-size: 11px; color: #93c5fd; text-align: right; }

.section-title {
  font-size: 16px; font-weight: 700; color: var(--navy);
  margin: 32px 0 12px; padding-bottom: 6px;
  border-bottom: 2px solid var(--orange);
  display: flex; align-items: center; gap: 8px;
}

.sector-grid   { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-bottom: 8px; }
.country-grid  { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }

.sector-card, .country-card {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px;
  transition: box-shadow 0.2s;
}
.sector-card:hover, .country-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
/* 오늘의 주제 하이라이트 */
.sector-card.focus, .country-card.focus {
  border: 2px solid var(--orange) !important;
  background: #fffbf5;
  box-shadow: 0 0 0 3px rgba(245,130,32,0.12);
}

/* 대표 주식 칩 */
.rep-stocks { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 8px; }
.rep-stock  {
  background: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd;
  border-radius: 4px; padding: 2px 7px; font-size: 11px; font-weight: 600;
}

/* 이전 사이클 링크 */
.prev-cycle-link {
  display: inline-block; margin-top: 8px;
  font-size: 11px; color: #6366f1; text-decoration: none;
  background: #eef2ff; padding: 3px 8px; border-radius: 4px;
}
.prev-cycle-link:hover { background: #e0e7ff; text-decoration: underline; }
.focus-star {
  background: var(--orange); color: #fff;
  padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;
  margin-left: 4px;
}

.sc-name { font-weight: 700; font-size: 14px; }
.sc-etf  { font-size: 11px; color: var(--muted); }
.sc-metrics { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; margin-top: 6px; }
.sc-metric  { display: flex; flex-direction: column; }
.sc-metric .mk { color: var(--muted); font-size: 10px; }
.tag-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.tag { background: #f0f9ff; color: #0369a1; border-radius: 4px; padding: 1px 6px; font-size: 10px; }

.cc-flag { font-size: 24px; }
.cc-name { font-weight: 700; font-size: 15px; }

.story-section {
  background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-top: 24px;
}
.story-section h2 {
  font-size: 18px; font-weight: 700; color: var(--navy);
  margin-bottom: 16px; border-bottom: 2px solid var(--orange); padding-bottom: 8px;
}
.story-content p { margin: 0 0 12px 0; line-height: 1.75; }
.story-content h3 { margin-top: 28px; }
.story-placeholder { color: var(--muted); font-style: italic; text-align: center; padding: 32px; }

.footer {
  text-align: center; color: var(--muted); font-size: 11px;
  padding: 24px; margin-top: 32px; border-top: 1px solid var(--border);
}
</style>
"""

STORY_PLACEHOLDER = "<!-- STORY_PLACEHOLDER -->"


# ── HTML 컴포넌트 ─────────────────────────────────────────────────────────

def _focus_banner_html(focus: dict, date_str: str) -> str:
    chips = []
    for s in focus["subjects"]:
        if s["type"] == "country":
            label = f'{s["flag"]} {s["name"]}'
        elif s["type"] == "us_sector":
            label = f'🇺🇸 {s["name"]} ({s.get("etf","")})'
        else:
            label = f'🇰🇷 {s["name"]} ({s.get("etf","")})'
        chips.append(f'<span class="focus-chip">{label}</span>')
    chips_html = "".join(chips)

    sector_day   = focus.get("sector_day", "?")
    country_day  = focus.get("country_day", "?")
    country_name = focus.get("country_name", "")

    return f"""
<div class="focus-banner">
  <div style="flex:1">
    <div class="focus-label">🎯 오늘의 주제</div>
    <div class="focus-theme">{focus["theme"]} + {country_name}</div>
    <div class="focus-en">{focus["theme_en"]}</div>
    <div class="focus-chips">{chips_html}</div>
    <div style="font-size:11px;color:#bfdbfe;margin-top:8px">
      섹터 Day {sector_day}/11 &nbsp;|&nbsp; 국가 Day {country_day}/10
    </div>
  </div>
  <div class="focus-day">
    {date_str}<br>
    <span style="color:#bfdbfe">{(date.fromisoformat(date_str).strftime("%A"))}</span>
  </div>
</div>"""


def _sector_card_html(s: dict, is_focus: bool = False, prev_date: str = None) -> str:
    focus_cls  = " focus" if is_focus else ""
    focus_star = '<span class="focus-star">★ 오늘 주제</span>' if is_focus else ""

    etf_line = s.get("etf", "")
    if s.get("ticker"):
        etf_line += f' ({s["ticker"]})'

    rep = _rep_stocks_html(s["code"])
    prev_link = _prev_cycle_link_html(prev_date, "섹터 보고서") if is_focus and prev_date else ""

    return f"""
<div class="sector-card{focus_cls}">
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
    <span class="sc-name">{s.get('name', '')}</span>{focus_star}
  </div>
  <div class="sc-etf">{etf_line}</div>
  <div class="sc-metrics" style="margin-top:8px">
    <div class="sc-metric"><span class="mk">1개월</span>{_chg_span(s.get('mom_1m'))}</div>
    <div class="sc-metric"><span class="mk">3개월</span>{_chg_span(s.get('mom_3m'))}</div>
    <div class="sc-metric"><span class="mk">6개월</span>{_chg_span(s.get('mom_6m'))}</div>
  </div>
  {rep}
  {prev_link}
</div>"""


def _country_card_html(c: dict, is_focus: bool = False, prev_date: str = None) -> str:
    focus_cls  = " focus" if is_focus else ""
    focus_star = '<span class="focus-star">★ 오늘 주제</span>' if is_focus else ""

    rep = _rep_stocks_html(c.get("code", ""), is_country=True)
    prev_link = _prev_cycle_link_html(prev_date, "국가 보고서") if is_focus and prev_date else ""

    view_label = {"OW": "▲ 비중확대", "UW": "▼ 비중축소", "N": "→ 중립"}.get(c.get("view"), c.get("view", ""))
    view_color = {"OW": "#16a34a", "UW": "#dc2626", "N": "#d97706"}.get(c.get("view"), "#64748b")

    return f"""
<div class="country-card{focus_cls}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
    <span class="cc-flag">{c.get('flag', '')}</span>
    <div style="flex:1">
      <div style="display:flex;align-items:center;gap:4px">
        <span class="cc-name">{c.get('name', '')}</span>{focus_star}
      </div>
      <div style="font-size:11px;color:#64748b">{c.get('fund_type', '')}</div>
    </div>
    <span style="font-weight:700;font-size:12px;color:{view_color}">{view_label}</span>
  </div>
  <div class="sc-metrics">
    <div class="sc-metric"><span class="mk">3개월</span>{_chg_span(c.get('mom_3m'))}</div>
    <div class="sc-metric"><span class="mk">6개월</span>{_chg_span(c.get('mom_6m'))}</div>
  </div>
  {rep}
  {prev_link}
</div>"""



# ── HTML 전체 조립 ─────────────────────────────────────────────────────────

def _get_focus_codes(focus: dict) -> set:
    """오늘 주제의 섹터/국가 코드 집합."""
    return {s["code"] for s in focus["subjects"]}


def _build_html(date_str: str, period: str, sv: dict, cv: dict, focus: dict) -> str:
    period_label = {"daily": "일간", "weekly": "주간", "monthly": "월간"}.get(period, period)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    focus_codes = _get_focus_codes(focus)
    prev_sector_date  = focus.get("prev_sector_date")
    prev_country_date = focus.get("prev_country_date")

    banner  = _focus_banner_html(focus, date_str) if period == "daily" else ""

    # 오늘 주제인 섹터에만 이전 사이클 링크 표시
    us_cards = "\n".join(
        _sector_card_html(s, is_focus=(s["code"] in focus_codes),
                          prev_date=prev_sector_date if s["code"] in focus_codes else None)
        for s in sv["us_sectors"]
    )
    kr_cards = "\n".join(
        _sector_card_html(s, is_focus=(s["code"] in focus_codes),
                          prev_date=prev_sector_date if s["code"] in focus_codes else None)
        for s in sv["kr_sectors"]
    )
    country_cards = "\n".join(
        _country_card_html(c, is_focus=(c["code"] in focus_codes),
                           prev_date=prev_country_date if c["code"] in focus_codes else None)
        for c in cv["countries"]
    )

    focus_hint = ""
    if period == "daily":
        focus_hint = (f'<p style="margin-top:8px;font-size:12px">오늘 주제: '
                      f'<strong>{focus["theme"]} + {focus["country_name"]}</strong> '
                      f'— /sector-country {date_str} 커맨드를 실행하면 심층 분석이 추가됩니다.</p>')

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>섹터·국가 보고서 {date_str} ({period_label}) — {focus["theme"]}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700;800&display=swap" rel="stylesheet">
{_BASE_CSS}
</head>
<body>
<div class="header">
  <div>
    <div class="header-title">🌐 섹터·국가 보고서</div>
    <div class="header-sub">{date_str} ({period_label})</div>
  </div>
  <span style="margin-left:auto;font-size:11px;color:#93c5fd">생성: {generated_at}</span>
</div>

<div class="main">

  {banner}

  <div class="story-section" id="story-section">
    <h2>📰 오늘의 심층 분석 — {focus["theme"]} + {focus["country_name"]}</h2>
    {STORY_PLACEHOLDER}
    <div class="story-placeholder" id="story-default">
      <p>아직 심층 분석이 추가되지 않았습니다.</p>
      {focus_hint}
    </div>
  </div>

  <div class="section-title">🇺🇸 미국 섹터 (SPDR GICS 11개)</div>
  <div class="sector-grid">{us_cards}</div>

  <div class="section-title">🇰🇷 한국 섹터 (TIGER 200 GICS 11개)</div>
  <div class="sector-grid">{kr_cards}</div>

  <div class="section-title">🌍 국가별 투자 의견 (8개국)</div>
  <div class="country-grid">{country_cards}</div>

</div>

<div class="footer">
  Mirae Asset Securities · 섹터·국가 보고서 · {date_str} ({period_label}) · 데이터: history/market_data.csv
</div>
</body>
</html>"""


# ── 파일 저장 ─────────────────────────────────────────────────────────────

def _out_path(date_str: str, period: str) -> Path:
    if period == "daily":
        d = datetime.strptime(date_str, "%Y-%m-%d")
        folder = OUTPUT_ROOT / "daily" / f"{d.year}-{d.month:02d}"
        return folder / f"{date_str}.html"
    elif period == "weekly":
        return OUTPUT_ROOT / "weekly" / f"{_week_label(date_str)}.html"
    else:
        return OUTPUT_ROOT / "monthly" / f"{_month_label(date_str)}.html"


def _update_index_link(date_str: str, period: str, out_path: Path) -> None:
    """output/index.html의 Market Research 카드 링크를 최신 daily 보고서로 갱신."""
    if period != "daily":
        return
    index_path = ROOT / "output" / "index.html"
    if not index_path.exists():
        return

    # 상대 경로: output/index.html 기준
    rel = out_path.relative_to(ROOT / "output")
    new_href = str(rel).replace("\\", "/")

    content = index_path.read_text(encoding="utf-8")
    import re
    # sector-country/daily/ 로 시작하는 href만 교체
    updated = re.sub(
        r'href="sector-country/daily/[^"]*"',
        f'href="{new_href}"',
        content,
    )
    if updated != content:
        index_path.write_text(updated, encoding="utf-8")


def _extract_existing_story(html_path: Path) -> str | None:
    """기존 HTML에서 story 블록 추출. 없으면 None."""
    if not html_path.exists():
        return None
    # _story.html 파일 우선
    story_path = html_path.with_name(html_path.stem + "_story.html")
    if story_path.exists():
        return story_path.read_text(encoding="utf-8")
    # HTML 내 인라인 story 추출
    content = html_path.read_text(encoding="utf-8")
    if STORY_PLACEHOLDER in content:
        return None  # placeholder 그대로 → story 없음
    import re
    m = re.search(r'(<!-- STORY_START -->.*?<!-- STORY_END -->)', content, re.DOTALL)
    if m:
        return m.group(1)
    return None


def _save_story_file(html_path: Path, story_html: str) -> None:
    """story HTML을 _story.html 파일로 저장."""
    story_path = html_path.with_name(html_path.stem + "_story.html")
    story_path.write_text(story_html, encoding="utf-8")


def generate(date_str: str, period: str = "daily") -> tuple[str, dict]:
    """Data Dashboard HTML 생성 → (파일경로, focus) 반환. 기존 story 자동 보존."""
    sv = compute_sector_view(date_str)
    cv = compute_country_view(date_str)
    focus = get_focus(date_str)

    html = _build_html(date_str, period, sv, cv, focus)

    out = _out_path(date_str, period)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 기존 story 보존
    existing_story = _extract_existing_story(out)

    out.write_text(html, encoding="utf-8")

    if existing_story:
        inject_story(str(out), existing_story)
        _save_story_file(out, existing_story)

    _update_index_link(date_str, period, out)

    return str(out), focus


def inject_story(html_path: str, story_html: str) -> None:
    """STORY_PLACEHOLDER를 실제 Story HTML로 치환."""
    p = Path(html_path)
    content = p.read_text(encoding="utf-8")
    replaced = content.replace(STORY_PLACEHOLDER, story_html, 1)
    replaced = replaced.replace(
        '<div class="story-placeholder" id="story-default">',
        '<div class="story-placeholder" id="story-default" style="display:none">',
        1,
    )
    p.write_text(replaced, encoding="utf-8")


# ── CLI ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="섹터·국가 보고서 생성")
    parser.add_argument("date", help="YYYY-MM-DD")
    parser.add_argument("period", nargs="?", default="daily",
                        choices=["daily", "weekly", "monthly"])
    args = parser.parse_args()

    out_path, focus = generate(args.date, args.period)
    print(f"✓ 생성 완료: {out_path}")
    print(f"  섹터 Day {focus['sector_day']}/11: {focus['theme']} — {focus['theme_en']}")
    print(f"  국가 Day {focus['country_day']}/10: {focus['country_name']}")
    for s in focus["subjects"]:
        etf = s.get("etf", "")
        ticker = f" ({s['ticker']})" if s.get("ticker") else ""
        flag = s.get("flag", "")
        print(f"    • {flag} {s['name']} {etf}{ticker}")
