"""섹터·국가 초보자 보고서 생성기.

compute_sector_view() + compute_country_view() 데이터를 결합해
초보자 친화 HTML Data Dashboard를 생성한다.
하루 2개 주제(섹터 페어 or 국가 페어)를 15일 사이클로 로테이션.

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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from portfolio.view.sector_view import compute_sector_view
from portfolio.view.country_view import compute_country_view

OUTPUT_ROOT = ROOT / "output" / "sector-country"

# ── 15일 로테이션 사이클 ──────────────────────────────────────────────────
# 기준일: 2026-01-05 (월요일) → day 0

REFERENCE_DATE = date(2026, 1, 5)

# subject type: "us_sector" | "kr_sector" | "country"
ROTATION = [
    # ── 섹터 페어 (US + KR 대응) ─────────────────────────────────────────
    {
        "day": 1,
        "theme": "기술·반도체",
        "theme_en": "Technology & Semiconductor",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_TECH",   "name": "Technology",   "etf": "XLK"},
            {"type": "kr_sector", "code": "SC_KR_SEMI",   "name": "반도체",        "etf": "TIGER 반도체",        "ticker": "277630.KS"},
        ],
    },
    {
        "day": 2,
        "theme": "금융",
        "theme_en": "Financials",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_FIN",    "name": "Financials",   "etf": "XLF"},
            {"type": "kr_sector", "code": "SC_KR_FIN",    "name": "금융",          "etf": "TIGER 200 금융",      "ticker": "435420.KS"},
        ],
    },
    {
        "day": 3,
        "theme": "에너지·화학",
        "theme_en": "Energy & Chemicals",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_ENERGY", "name": "Energy",       "etf": "XLE"},
            {"type": "kr_sector", "code": "SC_KR_ENERGY", "name": "에너지화학",   "etf": "TIGER 200 에너지화학", "ticker": "472170.KS"},
        ],
    },
    {
        "day": 4,
        "theme": "헬스케어",
        "theme_en": "Health Care",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_HEALTH", "name": "Health Care",  "etf": "XLV"},
            {"type": "kr_sector", "code": "SC_KR_BIO",    "name": "헬스케어",      "etf": "TIGER 헬스케어",      "ticker": "166400.KS"},
        ],
    },
    {
        "day": 5,
        "theme": "산업재",
        "theme_en": "Industrials",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_INDU",   "name": "Industrials",  "etf": "XLI"},
            {"type": "kr_sector", "code": "SC_KR_INDU",   "name": "산업재",        "etf": "TIGER 200 산업재",    "ticker": "227560.KS"},
        ],
    },
    {
        "day": 6,
        "theme": "소재·2차전지",
        "theme_en": "Materials & Battery",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_MATL",   "name": "Materials",    "etf": "XLB"},
            {"type": "kr_sector", "code": "SC_KR_BATTERY","name": "2차전지",       "etf": "TIGER 2차전지테마",   "ticker": "137610.KS"},
        ],
    },
    # ── KR 대응 없는 US 섹터 묶음 ──────────────────────────────────────────
    {
        "day": 7,
        "theme": "소비재 (임의·필수)",
        "theme_en": "Consumer (Discretionary & Staples)",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_DISCR",   "name": "Consumer Discr.", "etf": "XLY"},
            {"type": "us_sector", "code": "SC_US_STAPLES", "name": "Consumer Staples","etf": "XLP"},
        ],
        "kr_note": "한국에는 직접 대응 TIGER ETF 없음 — KOSPI 소비재 업종 참조",
    },
    {
        "day": 8,
        "theme": "유틸리티·부동산",
        "theme_en": "Utilities & Real Estate",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_UTIL",   "name": "Utilities",    "etf": "XLU"},
            {"type": "us_sector", "code": "SC_US_REIT",   "name": "Real Estate",  "etf": "XLRE"},
        ],
        "kr_note": "한국에는 직접 대응 TIGER ETF 없음 — 국내 리츠·한국전력 참조",
    },
    {
        "day": 9,
        "theme": "통신·미디어",
        "theme_en": "Communication Services",
        "type": "sector_pair",
        "subjects": [
            {"type": "us_sector", "code": "SC_US_COMM",   "name": "Communication", "etf": "XLC"},
            {"type": "kr_sector", "code": "SC_KR_SEMI",   "name": "반도체 (IT·통신 연계)", "etf": "TIGER 반도체", "ticker": "277630.KS"},
        ],
        "kr_note": "한국 통신 ETF 없음 — 반도체·IT 업종과 연계해 해설",
    },
    # ── KR 단독 페어 ───────────────────────────────────────────────────────
    {
        "day": 10,
        "theme": "은행·철강소재",
        "theme_en": "Banking & Steel/Materials (KR)",
        "type": "kr_pair",
        "subjects": [
            {"type": "kr_sector", "code": "SC_KR_BANK",  "name": "은행",     "etf": "TIGER 은행",          "ticker": "261140.KS"},
            {"type": "kr_sector", "code": "SC_KR_STEEL", "name": "철강소재", "etf": "TIGER 200 철강소재",  "ticker": "494840.KS"},
        ],
        "us_note": "US 대응: XLF (금융), XLB (소재)",
    },
    {
        "day": 11,
        "theme": "의료기기·건설",
        "theme_en": "Medical Device & Construction (KR)",
        "type": "kr_pair",
        "subjects": [
            {"type": "kr_sector", "code": "SC_KR_HEALTH",  "name": "의료기기", "etf": "TIGER 의료기기",    "ticker": "400970.KS"},
            {"type": "kr_sector", "code": "SC_KR_CONSTR",  "name": "건설",     "etf": "TIGER 200 건설",   "ticker": "139270.KS"},
        ],
        "us_note": "US 대응: XLV (헬스케어), XLI (산업재)",
    },
    # ── 국가 페어 ──────────────────────────────────────────────────────────
    {
        "day": 12,
        "theme": "미국·한국",
        "theme_en": "United States & South Korea",
        "type": "country_pair",
        "subjects": [
            {"type": "country", "code": "US", "name": "미국",  "flag": "🇺🇸"},
            {"type": "country", "code": "KR", "name": "한국",  "flag": "🇰🇷"},
        ],
    },
    {
        "day": 13,
        "theme": "일본·중국",
        "theme_en": "Japan & China",
        "type": "country_pair",
        "subjects": [
            {"type": "country", "code": "JP", "name": "일본",  "flag": "🇯🇵"},
            {"type": "country", "code": "CN", "name": "중국",  "flag": "🇨🇳"},
        ],
    },
    {
        "day": 14,
        "theme": "유럽·영국",
        "theme_en": "Europe & United Kingdom",
        "type": "country_pair",
        "subjects": [
            {"type": "country", "code": "EU", "name": "유럽",  "flag": "🇪🇺"},
            {"type": "country", "code": "UK", "name": "영국",  "flag": "🇬🇧"},
        ],
    },
    {
        "day": 15,
        "theme": "인도·신흥국",
        "theme_en": "India & Emerging Markets",
        "type": "country_pair",
        "subjects": [
            {"type": "country", "code": "IN", "name": "인도",   "flag": "🇮🇳"},
            {"type": "country", "code": "EM", "name": "신흥국", "flag": "🌍"},
        ],
    },
]


def get_focus(date_str: str) -> dict:
    """날짜 → 오늘의 로테이션 슬롯."""
    d = date.fromisoformat(date_str)
    idx = (d - REFERENCE_DATE).days % len(ROTATION)
    return ROTATION[idx]


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


def _comp_to_view(comp) -> str:
    if comp is None or (isinstance(comp, float) and math.isnan(comp)):
        return "N"
    if comp >= 0.25:
        return "OW"
    if comp <= -0.25:
        return "UW"
    return "N"


def _view_badge_html(view: str) -> str:
    styles = {
        "OW": "background:#dcfce7;color:#16a34a",
        "N":  "background:#f1f5f9;color:#64748b",
        "UW": "background:#fee2e2;color:#dc2626",
    }
    labels = {
        "OW": "지금 담으면 좋은",
        "N":  "지켜보는",
        "UW": "줄이거나 피하는",
    }
    s = styles.get(view, styles["N"])
    l = labels.get(view, view)
    return (
        f'<span style="{s};padding:3px 8px;border-radius:5px;font-weight:700;font-size:12px">{view}</span>'
        f'<span style="color:#64748b;font-size:11px;margin-left:4px">{l}</span>'
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
.summary-cards {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px;
}
.summary-card {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; text-align: center;
}
.summary-card .num   { font-size: 28px; font-weight: 800; color: var(--navy); }
.summary-card .label { font-size: 12px; color: var(--muted); margin-top: 4px; }

.sector-grid   { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-bottom: 8px; }
.country-grid  { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }

.sector-card, .country-card {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px;
  transition: box-shadow 0.2s;
}
.sector-card:hover, .country-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.sector-card.ow, .country-card.ow { border-left: 4px solid #16a34a; }
.sector-card.uw, .country-card.uw { border-left: 4px solid #dc2626; }
.sector-card.n,  .country-card.n  { border-left: 4px solid #94a3b8; }

/* 오늘의 주제 하이라이트 */
.sector-card.focus, .country-card.focus {
  border: 2px solid var(--orange) !important;
  background: #fffbf5;
  box-shadow: 0 0 0 3px rgba(245,130,32,0.12);
}
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
    chips = "".join(
        f'<span class="focus-chip">'
        f'{"🇺🇸" if s["type"]=="us_sector" else ("🇰🇷" if s["type"]=="kr_sector" else s.get("flag","🌍"))} '
        f'{s["name"]} ({s.get("etf","")}{(" "+s["ticker"]) if s.get("ticker") else ""})'
        f'</span>'
        for s in focus["subjects"]
    )
    note = ""
    if focus.get("kr_note"):
        note = f'<div style="font-size:11px;color:#bfdbfe;margin-top:8px">※ {focus["kr_note"]}</div>'
    elif focus.get("us_note"):
        note = f'<div style="font-size:11px;color:#bfdbfe;margin-top:8px">※ {focus["us_note"]}</div>'

    return f"""
<div class="focus-banner">
  <div style="flex:1">
    <div class="focus-label">🎯 오늘의 주제 (Day {focus["day"]} / 15)</div>
    <div class="focus-theme">{focus["theme"]}</div>
    <div class="focus-en">{focus["theme_en"]}</div>
    <div class="focus-chips">{chips}</div>
    {note}
  </div>
  <div class="focus-day">
    {date_str}<br>
    <span style="color:#bfdbfe">{(date.fromisoformat(date_str).strftime("%A"))}</span>
  </div>
</div>"""


def _sector_card_html(s: dict, is_focus: bool = False) -> str:
    view = _comp_to_view(s.get("composite"))
    vc = view.lower()
    focus_cls = " focus" if is_focus else ""
    focus_star = '<span class="focus-star">★ 오늘 주제</span>' if is_focus else ""

    etf_line = s.get("etf", "")
    if s.get("ticker"):
        etf_line += f' ({s["ticker"]})'

    tags = ""
    peer = s.get("us_peer") or s.get("kr_peer")
    if peer and not is_focus:
        tags += f'<span class="tag">대응: {peer}</span>'

    return f"""
<div class="sector-card {vc}{focus_cls}">
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">
    {_view_badge_html(view)}{focus_star}
  </div>
  <div class="sc-name">{s.get('name', '')}</div>
  <div class="sc-etf">{etf_line}</div>
  <div class="tag-row">{tags}</div>
  <div class="sc-metrics">
    <div class="sc-metric"><span class="mk">1개월</span>{_chg_span(s.get('mom_1m'))}</div>
    <div class="sc-metric"><span class="mk">3개월</span>{_chg_span(s.get('mom_3m'))}</div>
    <div class="sc-metric"><span class="mk">6개월</span>{_chg_span(s.get('mom_6m'))}</div>
  </div>
</div>"""


def _country_card_html(c: dict, is_focus: bool = False) -> str:
    view = c.get("view", "N")
    vc = view.lower()
    focus_cls = " focus" if is_focus else ""
    focus_star = '<span class="focus-star">★ 오늘 주제</span>' if is_focus else ""

    regime_map = {
        "Goldilocks": "골디락스", "Reflation": "리플레이션",
        "Stagflation": "스태그플레이션", "Deflation": "디플레이션", "N/A": "미확인",
    }
    regime_kr = regime_map.get(c.get("regime", ""), "")

    return f"""
<div class="country-card {vc}{focus_cls}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
    <span class="cc-flag">{c.get('flag', '')}</span>
    <div style="flex:1">
      <div style="display:flex;align-items:center;gap:4px">
        <span class="cc-name">{c.get('name', '')}</span>{focus_star}
      </div>
      <div style="font-size:11px;color:#64748b">{c.get('fund_type', '')}</div>
    </div>
    <div>{_view_badge_html(view)}</div>
  </div>
  <div class="sc-metrics">
    <div class="sc-metric"><span class="mk">3개월</span>{_chg_span(c.get('mom_3m'))}</div>
    <div class="sc-metric"><span class="mk">6개월</span>{_chg_span(c.get('mom_6m'))}</div>
  </div>
</div>"""


def _summary_cards_html(sv: dict, cv: dict) -> str:
    us_ow = sum(1 for s in sv["us_sectors"] if _comp_to_view(s.get("composite")) == "OW")
    kr_ow = sum(1 for s in sv["kr_sectors"] if _comp_to_view(s.get("composite")) == "OW")
    country_ow = sum(1 for c in cv["countries"] if c.get("view") == "OW")

    regime = sv.get("us_regime", "N/A")
    regime_kr = REGIME_KR.get(regime, regime)
    regime_desc = REGIME_DESC_KR.get(regime, "")
    cycle = sv.get("cycle_phase", "N/A")
    cycle_kr = CYCLE_KR.get(cycle, cycle)
    cycle_color = CYCLE_COLOR.get(cycle, "#64748b")

    return f"""
<div class="summary-cards">
  <div class="summary-card">
    <div class="num" style="color:#16a34a">{us_ow}</div>
    <div class="label">미국 섹터 OW</div>
  </div>
  <div class="summary-card">
    <div class="num" style="color:#16a34a">{kr_ow}</div>
    <div class="label">한국 섹터 OW</div>
  </div>
  <div class="summary-card">
    <div class="num" style="color:#16a34a">{country_ow}</div>
    <div class="label">국가 OW</div>
  </div>
</div>"""


# ── HTML 전체 조립 ─────────────────────────────────────────────────────────

def _get_focus_codes(focus: dict) -> set:
    """오늘 주제의 섹터/국가 코드 집합."""
    return {s["code"] for s in focus["subjects"]}


def _build_html(date_str: str, period: str, sv: dict, cv: dict, focus: dict) -> str:
    regime = sv.get("us_regime", "N/A")
    regime_kr = REGIME_KR.get(regime, regime)
    cycle = sv.get("cycle_phase", "N/A")
    cycle_kr = CYCLE_KR.get(cycle, cycle)
    cycle_color = CYCLE_COLOR.get(cycle, "#64748b")
    period_label = {"daily": "일간", "weekly": "주간", "monthly": "월간"}.get(period, period)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    focus_codes = _get_focus_codes(focus)

    banner = _focus_banner_html(focus, date_str) if period == "daily" else ""
    summary = _summary_cards_html(sv, cv)

    us_cards = "\n".join(
        _sector_card_html(s, is_focus=(s["code"] in focus_codes))
        for s in sv["us_sectors"]
    )
    kr_cards = "\n".join(
        _sector_card_html(s, is_focus=(s["code"] in focus_codes))
        for s in sv["kr_sectors"]
    )
    country_cards = "\n".join(
        _country_card_html(c, is_focus=(c["code"] in focus_codes))
        for c in cv["countries"]
    )

    focus_hint = ""
    if period == "daily":
        focus_hint = f'<p style="margin-top:8px;font-size:12px">오늘 주제: <strong>{focus["theme"]}</strong> — /sector-country {date_str} 커맨드를 실행하면 심층 분석이 추가됩니다.</p>'

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
  {summary}

  <div class="section-title">🇺🇸 미국 섹터 (SPDR GICS 11개)</div>
  <div class="sector-grid">{us_cards}</div>

  <div class="section-title">🇰🇷 한국 섹터 (TIGER ETF 10개)</div>
  <div class="sector-grid">{kr_cards}</div>

  <div class="section-title">🌍 국가별 투자 의견 (8개국)</div>
  <div class="country-grid">{country_cards}</div>

  <div class="story-section" id="story-section">
    <h2>📰 오늘의 심층 분석 — {focus["theme"]}</h2>
    {STORY_PLACEHOLDER}
    <div class="story-placeholder" id="story-default">
      <p>아직 심층 분석이 추가되지 않았습니다.</p>
      {focus_hint}
    </div>
  </div>

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


def generate(date_str: str, period: str = "daily") -> tuple[str, dict]:
    """Data Dashboard HTML 생성 → (파일경로, focus) 반환."""
    sv = compute_sector_view(date_str)
    cv = compute_country_view(date_str)
    focus = get_focus(date_str)

    html = _build_html(date_str, period, sv, cv, focus)

    out = _out_path(date_str, period)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

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
    print(f"  오늘의 주제 (Day {focus['day']}/15): {focus['theme']} — {focus['theme_en']}")
    for s in focus["subjects"]:
        etf = s.get("etf", "")
        ticker = f" ({s['ticker']})" if s.get("ticker") else ""
        print(f"    • {s['name']} {etf}{ticker}")
