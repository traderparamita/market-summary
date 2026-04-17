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
import json
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


def _load_price_series(indicator_code: str, date_str: str, days: int = 60) -> dict:
    """특정 지표의 최근 N일 가격 시계열 반환."""
    df = pd.read_csv(HISTORY_CSV, parse_dates=["DATE"])
    df = df[df["INDICATOR_CODE"] == indicator_code].copy()
    df = df[df["DATE"] <= date_str].tail(days)

    if df.empty:
        return {"dates": [], "prices": []}

    return {
        "dates": df["DATE"].dt.strftime("%Y-%m-%d").tolist(),
        "prices": df["CLOSE"].fillna(0).round(2).tolist()
    }

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

# ── 국가 11일 로테이션 (섹터와 독립) ──────────────────────────────────────
# 한국·미국·중국 일부 반복 포함 11개국
COUNTRY_ROTATION = [
    {"country_day": 1,  "code": "KR", "name": "한국",   "flag": "🇰🇷"},
    {"country_day": 2,  "code": "US", "name": "미국",   "flag": "🇺🇸"},
    {"country_day": 3,  "code": "CN", "name": "중국",   "flag": "🇨🇳"},
    {"country_day": 4,  "code": "JP", "name": "일본",   "flag": "🇯🇵"},
    {"country_day": 5,  "code": "EU", "name": "유럽",   "flag": "🇪🇺"},
    {"country_day": 6,  "code": "KR", "name": "한국",   "flag": "🇰🇷"},
    {"country_day": 7,  "code": "US", "name": "미국",   "flag": "🇺🇸"},
    {"country_day": 8,  "code": "CN", "name": "중국",   "flag": "🇨🇳"},
    {"country_day": 9,  "code": "UK", "name": "영국",   "flag": "🇬🇧"},
    {"country_day": 10, "code": "IN", "name": "인도",   "flag": "🇮🇳"},
    {"country_day": 11, "code": "EM", "name": "신흥국", "flag": "🌍"},
]


def get_focus(date_str: str) -> dict:
    """날짜 → 오늘의 섹터(2개) + 국가(1개) 로테이션 슬롯.

    반환 형식:
    {
        "sector_day": int,      # 1~11
        "country_day": int,     # 1~11
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


def _prev_cycle_link_html(prev_date: str, label: str = "섹터") -> str:
    """이전 보고서 링크 HTML."""
    if not prev_date:
        return ""
    ym = prev_date[:7]
    url = f"../../daily/{ym}/{prev_date}.html"
    display = prev_date.replace("-", ".")
    return (
        f'<a href="{url}" class="prev-cycle-link" target="_blank">'
        f'↩ 이전 {label} 보고서 ({display})'
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

/* ── Tabs ── */
.tab-bar {
  display: flex; gap: 0; margin-bottom: 28px; border-bottom: 2px solid var(--border);
}
.tab-btn {
  padding: 12px 28px; font-size: 14px; font-weight: 600; color: var(--muted);
  background: none; border: none; cursor: pointer; border-bottom: 2px solid transparent;
  margin-bottom: -2px; transition: all 0.2s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--orange); border-bottom-color: var(--orange); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

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

/* ── Chart Section ── */
.chart-section { margin: 28px 0 36px; }
.chart-section-title {
  font-size: 17px; font-weight: 700; color: var(--navy);
  margin: 0 0 16px; padding-bottom: 8px;
  border-bottom: 2px solid var(--orange);
  display: flex; align-items: center; gap: 8px;
}
.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.chart-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  min-height: 340px;
}
.chart-card .chart-title {
  font-size: 13px; color: var(--muted); font-weight: 600; margin-bottom: 12px;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.chart-box { position: relative; height: 300px; }
.chart-full { grid-column: 1 / -1; }
.chart-full .chart-box { height: 240px; }

/* Dispersion gauge */
.dispersion-card {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 24px; margin-bottom: 20px;
  display: flex; align-items: center; gap: 24px; flex-wrap: wrap;
}
.dispersion-label {
  font-size: 12px; color: var(--muted); font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.dispersion-value {
  font-size: 20px; font-weight: 700; color: var(--navy);
}
.dispersion-bar-wrap {
  flex: 1; min-width: 240px;
}
.dispersion-bar {
  height: 32px; background: #e2e8f0; border-radius: 6px;
  position: relative; overflow: hidden;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
}
.dispersion-fill {
  position: absolute; height: 100%; background: linear-gradient(90deg, #dc2626, #f97316, #16a34a);
  border-radius: 6px; transition: width 0.3s;
}
.dispersion-markers {
  display: flex; justify-content: space-between; margin-top: 4px;
  font-size: 10px; color: var(--muted);
}

@media(max-width:768px) {
  .chart-grid { grid-template-columns: 1fr; }
  .chart-box { height: 220px; }
  .chart-full .chart-box { height: 200px; }
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
      섹터 Day {sector_day}/11 &nbsp;|&nbsp; 국가 Day {country_day}/11
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
    prev_link = _prev_cycle_link_html(prev_date) if prev_date else ""

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
    prev_link = _prev_cycle_link_html(prev_date, label="국가") if prev_date else ""

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
    prev_country_date = focus.get("prev_country_date")

    banner  = _focus_banner_html(focus, date_str) if period == "daily" else ""

    # 섹터별 이전 사이클 날짜 계산
    # 각 섹터의 sector_day를 찾아서, 현재 날짜에서 (현재 sector_day - 해당 sector_day) + 11일 전 날짜를 역산
    from datetime import timedelta as _td
    d_today = date.fromisoformat(date_str)
    elapsed_today = (d_today - REFERENCE_DATE).days
    cur_sector_idx = elapsed_today % len(SECTOR_ROTATION)  # 0-based

    def _sector_prev_date(sector_code: str) -> str | None:
        """해당 섹터 코드가 마지막으로 등장한 이전 사이클 날짜 반환."""
        # SECTOR_ROTATION에서 해당 code의 sector_day(0-based idx) 찾기
        target_idx = None
        for i, slot in enumerate(SECTOR_ROTATION):
            for subj in slot["subjects"]:
                if subj["code"] == sector_code:
                    target_idx = i
                    break
            if target_idx is not None:
                break
        if target_idx is None:
            return None
        # 현재 날짜에서 target_idx까지 역산 (영업일 기준)
        steps_back = (cur_sector_idx - target_idx) % len(SECTOR_ROTATION)
        if steps_back == 0:
            steps_back = len(SECTOR_ROTATION)  # 오늘 주제면 한 사이클 전
        # steps_back 영업일 전 날짜
        cur = d_today
        counted = 0
        while counted < steps_back:
            cur -= _td(days=1)
            if cur.weekday() < 5:
                counted += 1
        return cur.isoformat()

    cur_country_idx = elapsed_today % len(COUNTRY_ROTATION)

    def _country_prev_date(country_code: str) -> str | None:
        """해당 국가 코드의 가장 최근 이전 사이클 날짜 반환.
        같은 국가가 여러 번 등장할 경우 steps_back이 최소인 idx를 선택.
        """
        best_steps = None
        for i, slot in enumerate(COUNTRY_ROTATION):
            if slot["code"] != country_code:
                continue
            steps = (cur_country_idx - i) % len(COUNTRY_ROTATION)
            if steps == 0:
                steps = len(COUNTRY_ROTATION)
            if best_steps is None or steps < best_steps:
                best_steps = steps
        if best_steps is None:
            return None
        cur = d_today
        counted = 0
        while counted < best_steps:
            cur -= _td(days=1)
            if cur.weekday() < 5:
                counted += 1
        return cur.isoformat()

    us_cards = "\n".join(
        _sector_card_html(s, is_focus=(s["code"] in focus_codes),
                          prev_date=_sector_prev_date(s["code"]))
        for s in sv["us_sectors"]
    )
    kr_cards = "\n".join(
        _sector_card_html(s, is_focus=(s["code"] in focus_codes),
                          prev_date=_sector_prev_date(s["code"]))
        for s in sv["kr_sectors"]
    )
    country_cards = "\n".join(
        _country_card_html(c, is_focus=(c["code"] in focus_codes),
                           prev_date=_country_prev_date(c["code"]))
        for c in cv["countries"]
    )

    focus_hint = ""
    if period == "daily":
        focus_hint = (f'<p style="margin-top:8px;font-size:12px">오늘 주제: '
                      f'<strong>{focus["theme"]} + {focus["country_name"]}</strong> '
                      f'— /sector-country {date_str} 커맨드를 실행하면 심층 분석이 추가됩니다.</p>')

    # ── Chart Data Preparation ──
    def _safe(v):
        """NaN/None을 0으로 변환."""
        return round(v, 2) if v is not None and not (isinstance(v, float) and math.isnan(v)) else 0

    # Sector ranking charts (3M Return 기준)
    us_sorted = sorted(sv["us_sectors"], key=lambda x: x.get("mom_3m", 0), reverse=True)
    kr_sorted = sorted(sv["kr_sectors"], key=lambda x: x.get("mom_3m", 0), reverse=True)

    us_rank_labels = json.dumps([s.get("name", "") for s in us_sorted])
    us_rank_scores = json.dumps([_safe(s.get("mom_3m")) for s in us_sorted])
    us_rank_colors = json.dumps(["#16a34a" if _safe(s.get("mom_3m")) >= 0 else "#dc2626" for s in us_sorted])

    kr_rank_labels = json.dumps([s.get("name", "") for s in kr_sorted])
    kr_rank_scores = json.dumps([_safe(s.get("mom_3m")) for s in kr_sorted])
    kr_rank_colors = json.dumps(["#16a34a" if _safe(s.get("mom_3m")) >= 0 else "#dc2626" for s in kr_sorted])

    # Country scatter (3M Return vs ACWI Excess 기준)
    country_scatter = json.dumps([
        {
            "x": _safe(c.get("mom_3m")),
            "y": _safe(c.get("excess_3m")),
            "label": c.get("name", ""),
            "view": c.get("view", "N"),
            "r": max(abs(_safe(c.get("mom_3m"))) * 1.2, 5),
        }
        for c in cv.get("countries", [])
    ])

    # Focus 섹터 이름 (차트 제목용 — story inject 시 사용)
    focus_us_name = next((s.get("name", "") for s in focus.get("subjects", []) if s.get("type") == "us_sector"), "")
    focus_kr_name = next((s.get("name", "") for s in focus.get("subjects", []) if s.get("type") == "kr_sector"), "")
    focus_country_name = focus.get("country_name", "")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>섹터·국가 보고서 {date_str} ({period_label}) — {focus["theme"]}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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

  <div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('story')">📰 Story</button>
    <button class="tab-btn" onclick="switchTab('data')">📊 Data Dashboard</button>
  </div>

  <div id="tab-story" class="tab-panel active">
    {STORY_PLACEHOLDER}
    <div class="story-section" id="story-section" style="display:none">
      <h2>📰 오늘의 심층 분석 — {focus["theme"]} + {focus["country_name"]}</h2>
      <div class="story-placeholder" id="story-default">
        <p>아직 심층 분석이 추가되지 않았습니다.</p>
        {focus_hint}
      </div>
    </div>

  </div><!-- /tab-story -->

  <div id="tab-data" class="tab-panel">

    <div class="section-title">🇺🇸 미국 섹터 (SPDR GICS 11개)</div>
    <div class="chart-card chart-full" style="margin-bottom:12px">
      <div class="chart-title">US Sector 3M Return Ranking</div>
      <div class="chart-box">
        <canvas id="usRankChart2"></canvas>
      </div>
    </div>
    <div class="sector-grid">{us_cards}</div>

    <div class="section-title">🇰🇷 한국 섹터 (TIGER 200 GICS 11개)</div>
    <div class="chart-card chart-full" style="margin-bottom:12px">
      <div class="chart-title">KR Sector 3M Return Ranking</div>
      <div class="chart-box">
        <canvas id="krRankChart2"></canvas>
      </div>
    </div>
    <div class="sector-grid">{kr_cards}</div>

    <div class="section-title">🌍 국가별 투자 의견 (8개국)</div>
    <div class="chart-card chart-full" style="margin-bottom:12px">
      <div class="chart-title">Country Positioning (3M Return vs ACWI Excess)</div>
      <div class="chart-box">
        <canvas id="countryScatterChart2"></canvas>
      </div>
    </div>
    <div class="country-grid">{country_cards}</div>

  </div><!-- /tab-data -->

</div>

<div class="footer">
  Mirae Asset Securities · 섹터·국가 보고서 · {date_str} ({period_label}) · 데이터: history/market_data.csv
</div>

<script>
// Chart.js defaults
Chart.defaults.color = '#7c8298';
Chart.defaults.font.family = "'Noto Sans KR', sans-serif";
Chart.defaults.font.size = 11;

const UP='#16a34a', DN='#dc2626', AC='#F58220', NAVY='#043B72', MU='#94a3b8';

// ── Data 탭 차트 ──
// US Sector Ranking (Data tab)
new Chart(document.getElementById('usRankChart2'), {{
  type: 'bar',
  data: {{
    labels: {us_rank_labels},
    datasets: [{{
      data: {us_rank_scores},
      backgroundColor: {us_rank_colors},
      borderRadius: 4,
      barPercentage: 0.7
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: function(ctx) {{
            return '3M Return: ' + ctx.parsed.x.toFixed(2) + '%';
          }}
        }}
      }}
    }},
    scales: {{
      x: {{
        grid: {{ color: '#ecedf2' }},
        ticks: {{ callback: v => v.toFixed(1) + '%' }},
        title: {{ display: true, text: '3M Return (%)', color: '#7c8298', font: {{ size: 10 }} }}
      }},
      y: {{
        grid: {{ display: false }},
        ticks: {{ font: {{ weight: '600', size: 11 }} }}
      }}
    }}
  }}
}});

// KR Sector Ranking (Data tab)
new Chart(document.getElementById('krRankChart2'), {{
  type: 'bar',
  data: {{
    labels: {kr_rank_labels},
    datasets: [{{
      data: {kr_rank_scores},
      backgroundColor: {kr_rank_colors},
      borderRadius: 4,
      barPercentage: 0.7
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: function(ctx) {{
            return '3M Return: ' + ctx.parsed.x.toFixed(2) + '%';
          }}
        }}
      }}
    }},
    scales: {{
      x: {{
        grid: {{ color: '#ecedf2' }},
        ticks: {{ callback: v => v.toFixed(1) + '%' }},
        title: {{ display: true, text: '3M Return (%)', color: '#7c8298', font: {{ size: 10 }} }}
      }},
      y: {{
        grid: {{ display: false }},
        ticks: {{ font: {{ weight: '600', size: 11 }} }}
      }}
    }}
  }}
}});

// Country Scatter (Data tab)
const countryData2 = {country_scatter};
const owData2 = countryData2.filter(d => d.view === 'OW');
const nData2 = countryData2.filter(d => d.view === 'N');
const uwData2 = countryData2.filter(d => d.view === 'UW');

new Chart(document.getElementById('countryScatterChart2'), {{
  type: 'scatter',
  data: {{
    datasets: [
      {{
        label: 'OW (비중확대)',
        data: owData2,
        backgroundColor: UP + 'cc',
        borderColor: UP,
        borderWidth: 2,
        pointRadius: owData2.map(d => d.r)
      }},
      {{
        label: 'N (중립)',
        data: nData2,
        backgroundColor: '#d97706cc',
        borderColor: '#d97706',
        borderWidth: 2,
        pointRadius: nData2.map(d => d.r)
      }},
      {{
        label: 'UW (비중축소)',
        data: uwData2,
        backgroundColor: DN + 'cc',
        borderColor: DN,
        borderWidth: 2,
        pointRadius: uwData2.map(d => d.r)
      }}
    ]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{
        position: 'top',
        labels: {{ boxWidth: 10, padding: 12, font: {{ size: 11 }} }}
      }},
      tooltip: {{
        callbacks: {{
          label: function(ctx) {{
            return ctx.raw.label + ' (3M: ' + ctx.raw.x.toFixed(1) + '%, vs ACWI: ' + ctx.raw.y.toFixed(1) + '%)';
          }}
        }}
      }}
    }},
    scales: {{
      x: {{
        title: {{ display: true, text: '3개월 수익률 (%)', color: '#7c8298' }},
        grid: {{ color: '#ecedf2' }},
        ticks: {{ callback: v => v + '%' }}
      }},
      y: {{
        title: {{ display: true, text: 'vs ACWI 초과수익 (%)', color: '#7c8298' }},
        grid: {{ color: '#ecedf2' }},
        ticks: {{ callback: v => v + '%' }}
      }}
    }}
  }}
}});

// ── Tab switching ──
function switchTab(tab) {{
  // Update buttons
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  event.target.classList.add('active');

  // Update panels
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
}}
</script>
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
        inject_story(str(out), existing_story, focus=focus, date_str=date_str)
        _save_story_file(out, existing_story)

    _update_index_link(date_str, period, out)

    return str(out), focus


def _build_inline_chart(canvas_id: str, chart_type: str, labels_json: str,
                         datasets_json: str, options_json: str) -> str:
    """인라인 canvas + script 블록 생성 (Data 탭 ID와 충돌 없음)."""
    return f"""<div class="chart-card" style="margin:16px 0">
  <div class="chart-box">
    <canvas id="{canvas_id}"></canvas>
  </div>
</div>
<script>
(function() {{
  var ctx = document.getElementById('{canvas_id}');
  if (!ctx) return;
  new Chart(ctx, {{
    type: '{chart_type}',
    data: {{ labels: {labels_json}, datasets: {datasets_json} }},
    options: {options_json}
  }});
}})();
</script>"""


def _load_story_chart_data(date_str: str, focus: dict) -> dict:
    """inject_story에서 사용할 차트 데이터를 미리 계산."""
    import json as _json

    focus_us_code = None
    focus_kr_code = None
    focus_country_code = None
    for s in focus.get("subjects", []):
        if s.get("type") == "us_sector":
            focus_us_code = s["code"]
        elif s.get("type") == "kr_sector":
            focus_kr_code = s["code"]
        elif s.get("type") == "country":
            focus_country_code = s["code"]

    def norm(prices):
        if not prices or prices[0] == 0:
            return [100.0] * len(prices)
        base = prices[0]
        return [round(p / base * 100, 2) for p in prices]

    # US 섹터 vs S&P500 (normalized)
    us_series   = _load_price_series(focus_us_code, date_str, 60) if focus_us_code else {"dates": [], "prices": []}
    sp500_series = _load_price_series("EQ_SP500", date_str, 60)
    us_norm      = norm(us_series["prices"])
    sp500_norm   = norm(sp500_series["prices"])

    # KR 섹터 vs KOSPI (normalized)
    kr_series   = _load_price_series(focus_kr_code, date_str, 60) if focus_kr_code else {"dates": [], "prices": []}
    kospi_series = _load_price_series("EQ_KOSPI", date_str, 60)
    kr_norm      = norm(kr_series["prices"])
    kospi_norm   = norm(kospi_series["prices"])

    # 국가 지수 (focus 국가에 맞는 eq_code 사용)
    try:
        from portfolio.view.country_view import COUNTRIES
        country_eq_code = COUNTRIES.get(focus_country_code, {}).get("eq_code", "EQ_SP500") if focus_country_code else "EQ_SP500"
    except Exception:
        country_eq_code = "EQ_SP500"
    country_series = _load_price_series(country_eq_code, date_str, 60)
    country_raw    = country_series["prices"]

    us_name      = next((s.get("name", "") for s in focus.get("subjects", []) if s.get("type") == "us_sector"), "")
    kr_name      = next((s.get("name", "") for s in focus.get("subjects", []) if s.get("type") == "kr_sector"), "")
    country_name = next((s.get("name", "") for s in focus.get("subjects", []) if s.get("type") == "country"), "")

    return {
        "us_dates":       _json.dumps(us_series["dates"]),
        "us_norm":        _json.dumps(us_norm),
        "sp500_norm":     _json.dumps(sp500_norm),
        "kr_dates":       _json.dumps(kr_series["dates"]),
        "kr_norm":        _json.dumps(kr_norm),
        "kospi_norm":     _json.dumps(kospi_norm),
        "country_dates":  _json.dumps(country_series["dates"]),
        "country_raw":    _json.dumps([round(p, 2) for p in country_raw]),
        "us_name":        us_name,
        "kr_name":        kr_name,
        "country_name":   country_name,
    }


def _make_story_charts(cd: dict) -> dict:
    """h3별 삽입용 차트 HTML 반환."""
    line_opts = """{
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10 } } },
               tooltip: { callbacks: { label: function(ctx) { return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1); } } } },
    scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 9 } } },
              y: { grid: { color: '#ecedf2' }, ticks: { callback: v => v.toFixed(0) } } }
  }"""

    raw_opts = """{
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false },
               tooltip: { callbacks: { label: function(ctx) { return '$' + ctx.parsed.y.toFixed(2); } } } },
    scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 9 } } },
              y: { grid: { color: '#ecedf2' }, ticks: { callback: v => '$' + v.toFixed(0) } } }
  }"""

    us_datasets = (
        f'[{{"label":"{cd["us_name"]}","data":{cd["us_norm"]},'
        f'"borderColor":"#F58220","borderWidth":2,"fill":false,"tension":0.1,"pointRadius":0}},'
        f'{{"label":"S&P500","data":{cd["sp500_norm"]},'
        f'"borderColor":"#94a3b8","borderWidth":2,"fill":false,"tension":0.1,"pointRadius":0,"borderDash":[5,5]}}]'
    )
    kr_datasets = (
        f'[{{"label":"{cd["kr_name"]}","data":{cd["kr_norm"]},'
        f'"borderColor":"#043B72","borderWidth":2,"fill":false,"tension":0.1,"pointRadius":0}},'
        f'{{"label":"KOSPI","data":{cd["kospi_norm"]},'
        f'"borderColor":"#94a3b8","borderWidth":2,"fill":false,"tension":0.1,"pointRadius":0,"borderDash":[5,5]}}]'
    )
    country_datasets = (
        f'[{{"label":"{cd["country_name"]}","data":{cd["country_raw"]},'
        f'"borderColor":"#F58220","backgroundColor":"rgba(245,130,32,0.1)","borderWidth":2,'
        f'"fill":true,"tension":0.1,"pointRadius":0}}]'
    )

    return {
        "us":      _build_inline_chart("sc_us_rel_chart",      "line", cd["us_dates"],      us_datasets,      line_opts),
        "kr":      _build_inline_chart("sc_kr_rel_chart",      "line", cd["kr_dates"],      kr_datasets,      line_opts),
        "country": _build_inline_chart("sc_country_raw_chart", "line", cd["country_dates"], country_datasets, raw_opts),
    }


def inject_story(html_path: str, story_html: str, focus: dict = None, date_str: str = None) -> None:
    """Story HTML을 STORY_PLACEHOLDER에 주입. h3별로 차트를 인라인 삽입."""
    import re
    p = Path(html_path)
    content = p.read_text(encoding="utf-8")

    # 차트 데이터 준비 (focus/date 있을 때만)
    charts = {}
    if focus and date_str:
        try:
            cd = _load_story_chart_data(date_str, focus)
            charts = _make_story_charts(cd)
        except Exception:
            pass

    # focus에서 오늘 주제 키워드 추출 (차트 매칭용)
    us_keywords: list[str] = []
    kr_keywords: list[str] = []
    country_keywords: list[str] = []
    if focus:
        for s in focus.get("subjects", []):
            kind = s.get("type", "")
            if kind == "us_sector":
                us_keywords += [s.get("etf", ""), s.get("name", "")]
            elif kind == "kr_sector":
                kr_keywords += [s.get("etf", ""), s.get("name", ""), s.get("ticker", "")]
            elif kind == "country":
                country_keywords += [s.get("name", ""), s.get("flag", "")]

    # story-content 내부 추출
    story_match = re.search(r'<div class="story-content">(.*)</div>\s*</div>\s*$', story_html, re.DOTALL)
    if not story_match:
        # 파싱 실패 → div 균형 보정 후 삽입
        opens = story_html.count('<div')
        closes = story_html.count('</div>')
        if opens > closes:
            story_html = story_html.rstrip() + '\n' + '</div>\n' * (opens - closes)
        _do_replace(p, content, story_html)
        return

    story_inner = story_match.group(1)

    # story_inner 내부 div 균형 보정
    inner_opens = story_inner.count('<div')
    inner_closes = story_inner.count('</div>')
    if inner_opens > inner_closes:
        story_inner = story_inner.rstrip() + '\n' + '</div>\n' * (inner_opens - inner_closes)

    h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', story_html)
    h2_html = f'<h2>{h2_match.group(1)}</h2>\n' if h2_match else ''

    # h3 단위로 분할 후 재조립
    sections = re.split(r'(<h3[^>]*>.*?</h3>)', story_inner)
    rebuilt = '<div class="story-section" id="story-section">\n' + h2_html
    rebuilt += '<div class="story-content">\n'

    i = 0
    while i < len(sections):
        part = sections[i]
        if not part.startswith('<h3'):
            rebuilt += part
            i += 1
            continue

        # h3 헤더 + 다음 텍스트 내용
        rebuilt += part + '\n'
        text = sections[i + 1] if i + 1 < len(sections) else ''
        rebuilt += text

        # h3 내용으로 차트 결정 — focus 키워드 동적 매칭
        def _kw_match(kws: list[str]) -> bool:
            return any(k and k in part for k in kws)

        if _kw_match(us_keywords) and 'us' in charts:
            rebuilt += charts['us']
        elif _kw_match(kr_keywords) and 'kr' in charts:
            rebuilt += charts['kr']
        elif _kw_match(country_keywords) and 'country' in charts:
            rebuilt += charts['country']
        # fallback: 키워드 없으면 h3 순서로 배분 (1→us, 2→kr, 3→country)
        elif not (us_keywords or kr_keywords or country_keywords) and charts:
            h3_idx = sum(1 for s in sections[:i] if s.startswith('<h3'))
            if h3_idx == 0 and 'us' in charts:
                rebuilt += charts['us']
            elif h3_idx == 1 and 'kr' in charts:
                rebuilt += charts['kr']
            elif h3_idx == 2 and 'country' in charts:
                rebuilt += charts['country']

        i += 2  # h3 + 내용 함께 소비

    rebuilt += '</div>\n</div>\n'

    _do_replace(p, content, rebuilt)


def _do_replace(p: Path, content: str, new_story: str) -> None:
    """STORY_PLACEHOLDER 교체. 없으면 기존 story-section 블록을 통째로 교체."""
    import re
    if STORY_PLACEHOLDER in content:
        replaced = content.replace(STORY_PLACEHOLDER, new_story, 1)
        replaced = re.sub(
            r'<div class="story-section"[^>]*?style="display:none"[^>]*>.*?</div>\s*</div>',
            '', replaced, count=1, flags=re.DOTALL
        )
    else:
        # 이미 주입된 HTML — story-section 블록을 새 내용으로 교체
        # story-section은 중첩 div를 포함하므로 </body> 직전까지 greedy 매칭
        replaced = re.sub(
            r'<div class="story-section"[^>]*>.*(?=\s*</body>)',
            new_story.rstrip(),
            content, count=1, flags=re.DOTALL
        )
    p.write_text(replaced, encoding="utf-8")
    # _story.html 저장 — story-content 전체를 greedy로 추출
    m = re.search(r'(<div class="story-content">.*</div>)', new_story, re.DOTALL)
    if m:
        _save_story_file(p, m.group(1))


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
    print(f"  국가 Day {focus['country_day']}/11: {focus['country_name']}")
    for s in focus["subjects"]:
        etf = s.get("etf", "")
        ticker = f" ({s['ticker']})" if s.get("ticker") else ""
        flag = s.get("flag", "")
        print(f"    • {flag} {s['name']} {etf}{ticker}")
