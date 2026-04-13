"""Allocation View — 변액보험 펀드 배분 의견 (Phase 2 종착점).

Phase 1 진단(regime) + Phase 2 드릴다운(country/sector/bond/style) 신호를
통합해 변액보험 펀드 유형별 추천 비중을 제안한다.

- KR 투자자 관점: KRW 기준, K-ICS 주식한도(30%) 인식, ALM 듀레이션
- US 투자자 관점: USD 기준 글로벌 배분 (참고용)
- 환헤지 권고: USDKRW 트렌드 + KR-US 금리차 기반

Usage:
    python -m portfolio.view.allocation_view --date 2026-04-14 --html
"""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "allocation"
MARKET_CSV = ROOT / "history" / "market_data.csv"
MACRO_CSV  = ROOT / "history" / "macro_indicators.csv"

# ── 변액보험 펀드 카테고리 정의 ───────────────────────────────────────────

FUND_CATEGORIES = [
    {"id": "kr_eq",        "name": "국내주식형",          "group": "equity",  "kr_only": True},
    {"id": "us_eq",        "name": "해외주식형(미국)",     "group": "equity",  "kr_only": False},
    {"id": "global_eq",    "name": "해외주식형(글로벌)",   "group": "equity",  "kr_only": False},
    {"id": "em_eq",        "name": "해외주식형(신흥국)",   "group": "equity",  "kr_only": False},
    {"id": "sector_eq",    "name": "해외주식형(섹터·테마)","group": "equity",  "kr_only": False},
    {"id": "kr_bond",      "name": "국내채권형",          "group": "bond",    "kr_only": True},
    {"id": "us_bond",      "name": "해외채권형(미국·선진)","group": "bond",    "kr_only": False},
    {"id": "mixed",        "name": "혼합형(주식+채권)",   "group": "mixed",   "kr_only": False},
    {"id": "alternative",  "name": "대안(금·원자재·부동산)","group": "alts",  "kr_only": False},
    {"id": "cash",         "name": "현금성(MMF·CD)",      "group": "cash",    "kr_only": True},
]

# ── Base allocation templates by regime ──────────────────────────────────
# KR 변액보험 기준 (K-ICS 주식한도 약 30% 고려한 보수적 기준)

BASE_ALLOC = {
    "Goldilocks": {
        "kr_eq": 10, "us_eq": 12, "global_eq": 8, "em_eq": 5, "sector_eq": 5,
        "kr_bond": 20, "us_bond": 15, "mixed": 10, "alternative": 5, "cash": 10,
    },
    "Reflation": {
        "kr_eq": 8, "us_eq": 10, "global_eq": 7, "em_eq": 5, "sector_eq": 5,
        "kr_bond": 18, "us_bond": 15, "mixed": 12, "alternative": 10, "cash": 10,
    },
    "Stagflation": {
        "kr_eq": 5, "us_eq": 5, "global_eq": 5, "em_eq": 3, "sector_eq": 2,
        "kr_bond": 22, "us_bond": 18, "mixed": 15, "alternative": 15, "cash": 10,
    },
    "Deflation": {
        "kr_eq": 5, "us_eq": 5, "global_eq": 5, "em_eq": 2, "sector_eq": 2,
        "kr_bond": 28, "us_bond": 22, "mixed": 12, "alternative": 5, "cash": 14,
    },
    "N/A": {
        "kr_eq": 7, "us_eq": 8, "global_eq": 7, "em_eq": 4, "sector_eq": 4,
        "kr_bond": 22, "us_bond": 18, "mixed": 12, "alternative": 8, "cash": 10,
    },
}

# US investor reference allocation (unconstrained, 60/40 style)
BASE_ALLOC_US = {
    "Goldilocks": {
        "us_eq": 40, "intl_eq": 20, "em_eq": 10,
        "us_bond": 15, "em_bond": 5, "alts": 5, "cash": 5,
    },
    "Reflation": {
        "us_eq": 30, "intl_eq": 18, "em_eq": 10,
        "us_bond": 15, "em_bond": 7, "alts": 12, "cash": 8,
    },
    "Stagflation": {
        "us_eq": 20, "intl_eq": 10, "em_eq": 5,
        "us_bond": 22, "em_bond": 8, "alts": 20, "cash": 15,
    },
    "Deflation": {
        "us_eq": 20, "intl_eq": 10, "em_eq": 5,
        "us_bond": 38, "em_bond": 7, "alts": 5, "cash": 15,
    },
    "N/A": {
        "us_eq": 28, "intl_eq": 15, "em_eq": 7,
        "us_bond": 25, "em_bond": 6, "alts": 9, "cash": 10,
    },
}

K_ICS_EQUITY_LIMIT = 30  # %


# ── Data loaders ──────────────────────────────────────────────────────────

def _load_prices(date: str) -> pd.DataFrame:
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    return wide[wide.index <= pd.Timestamp(date)].sort_index()


def _get_macro_regime(date: str) -> str:
    if not MACRO_CSV.exists():
        return "N/A"
    df = pd.read_csv(MACRO_CSV, parse_dates=["DATE"])
    df = df[df["DATE"] <= pd.Timestamp(date)]

    def _v(code):
        sub = df[df["INDICATOR_CODE"] == code]
        return float(sub.sort_values("DATE").iloc[-1]["VALUE"]) if not sub.empty else np.nan

    gdp = _v("US_GDP_QOQ")
    cpi = _v("US_CPI_YOY")
    if np.isnan(gdp) or np.isnan(cpi):
        return "N/A"
    g = gdp > 0
    i = cpi > 3.0
    if g and not i:   return "Goldilocks"
    if g and i:       return "Reflation"
    if not g and i:   return "Stagflation"
    return "Deflation"


def _get_country_signals(date: str) -> dict:
    """country_view에서 국가별 OW/N/UW 가져오기."""
    try:
        from portfolio.view.country_view import compute_country_view
        data = compute_country_view(_parse_date(date))
        return {c["code"]: c["view"] for c in data["countries"]}
    except Exception:
        return {}


def _get_bond_signals(date: str) -> dict:
    """bond_view에서 듀레이션/크레딧 신호 가져오기."""
    try:
        from portfolio.view.bond_view import compute_bond_view
        data = compute_bond_view(_parse_date(date))
        return {
            "dur_bias":     data["duration_rec"]["bias"],
            "credit_regime": data["credit_regime"],
            "kr_us_diff":   data["kr_us_diff"]["diff"],
            "hy_spread":    data["rates"]["hy_spread"],
        }
    except Exception:
        return {}


def _get_style_signals(date: str) -> dict:
    """style_view에서 팩터 선호 가져오기."""
    try:
        from portfolio.view.style_view import compute_style_view
        data = compute_style_view(_parse_date(date))
        return {
            "regime":       data["regime"],
            "vix_regime":   data["vix_regime"],
            "rate_dir":     data["rate_direction"],
            "top_style":    data["us_styles"][0]["name"] if data["us_styles"] else "",
        }
    except Exception:
        return {}


def _get_sector_signals(date: str) -> list:
    """sector_view에서 상위 US 섹터 가져오기."""
    try:
        from portfolio.view.sector_view import compute_sector_view
        data = compute_sector_view(_parse_date(date))
        tops = [s["name"] for s in data["us_sectors"][:3] if s.get("view") == "OW"]
        return tops
    except Exception:
        return []


def _get_krw_signal(date: str) -> dict:
    """USDKRW 추세 기반 환헤지 권고."""
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[df["INDICATOR_CODE"] == "FX_USDKRW"][["DATE", "CLOSE"]].dropna()
    df = df[df["DATE"] <= pd.Timestamp(date)].sort_values("DATE")
    if len(df) < 60:
        return {"trend": "N/A", "hedge_rec": "중립", "color": "#f39c12"}
    px = df["CLOSE"]
    last = float(px.iloc[-1])
    ma60 = float(px.tail(60).mean())
    chg_3m = float(px.iloc[-1] / px.iloc[-63] - 1) * 100 if len(px) >= 66 else np.nan

    if last > ma60 and (np.isnan(chg_3m) or chg_3m > 1):
        trend = "원화 약세 (달러 강세)"
        hedge_rec = "환헤지 권고 — 해외자산 FX 손실 위험"
        color = "#e74c3c"
    elif last < ma60 and (np.isnan(chg_3m) or chg_3m < -1):
        trend = "원화 강세 (달러 약세)"
        hedge_rec = "환노출 가능 — 해외자산 FX 이득 기대"
        color = "#27ae60"
    else:
        trend = "원화 중립"
        hedge_rec = "부분 환헤지 (50%) 권고"
        color = "#f39c12"
    return {"trend": trend, "hedge_rec": hedge_rec, "color": color,
            "last": round(last, 0), "chg_3m": round(chg_3m, 1) if not np.isnan(chg_3m) else None}


def _parse_date(date):
    if hasattr(date, "year"):
        return date
    return datetime.strptime(str(date), "%Y-%m-%d").date()


# ── Allocation logic ──────────────────────────────────────────────────────

def _adjust_alloc(base: dict, country_sig: dict, bond_sig: dict,
                  style_sig: dict, krw_sig: dict) -> dict:
    """신호 기반 기준 배분 조정 (±3~5% 틸트)."""
    alloc = dict(base)

    # 1) Country signals → 지역별 주식 비중 조정
    us_view = country_sig.get("US", "N")
    kr_view = country_sig.get("KR", "N")
    em_view = country_sig.get("IN", "N")  # 신흥국 대표로 인도 사용

    if us_view == "OW":
        alloc["us_eq"]     = min(alloc["us_eq"] + 3, 15)
    elif us_view == "UW":
        alloc["us_eq"]     = max(alloc["us_eq"] - 3, 2)

    if kr_view == "OW":
        alloc["kr_eq"]     = min(alloc["kr_eq"] + 2, 12)
    elif kr_view == "UW":
        alloc["kr_eq"]     = max(alloc["kr_eq"] - 2, 2)

    em_ow = any(v == "OW" for k, v in country_sig.items() if k in ("IN", "CN", "EM"))
    if em_ow:
        alloc["em_eq"]     = min(alloc["em_eq"] + 2, 8)

    # 2) Bond signals → 채권 비중 조정
    dur_bias = bond_sig.get("dur_bias", "neutral")
    hy_spread = bond_sig.get("hy_spread", np.nan)

    if dur_bias == "long":
        alloc["kr_bond"] = min(alloc["kr_bond"] + 3, 32)
        alloc["us_bond"] = min(alloc["us_bond"] + 2, 22)
    elif dur_bias == "short":
        alloc["kr_bond"] = max(alloc["kr_bond"] - 2, 10)
        alloc["cash"]    = min(alloc["cash"]    + 3, 18)

    if not np.isnan(hy_spread) if isinstance(hy_spread, float) else True:
        try:
            if float(hy_spread) > 500:  # HY 위기
                alloc["us_bond"] = max(alloc["us_bond"] - 3, 8)
                alloc["cash"]    = min(alloc["cash"] + 3, 20)
        except (ValueError, TypeError):
            pass

    # 3) Style signals → 미국 주식 스타일 틸트
    vix_reg = style_sig.get("vix_regime", "medium")
    if vix_reg == "high":  # Risk-OFF → 방어적
        alloc["us_eq"]    = max(alloc["us_eq"] - 2, 2)
        alloc["mixed"]    = min(alloc["mixed"] + 2, 18)

    # 4) KRW signal → 해외 비중 조정
    krw_trend = krw_sig.get("trend", "N/A")
    if "약세" in krw_trend:   # 원화 약세 → 해외 헤지 비용 고려
        alloc["us_bond"] = max(alloc["us_bond"] - 2, 8)
        alloc["cash"]    = min(alloc["cash"] + 2, 18)

    # 5) K-ICS 주식 한도 체크 및 조정
    total_eq = sum(alloc[k] for k in ["kr_eq", "us_eq", "global_eq", "em_eq", "sector_eq"])
    if total_eq > K_ICS_EQUITY_LIMIT:
        excess = total_eq - K_ICS_EQUITY_LIMIT
        # 비례 축소
        for k in ["sector_eq", "em_eq", "us_eq", "global_eq", "kr_eq"]:
            cut = min(alloc[k], excess)
            alloc[k] -= cut
            excess   -= cut
            alloc["mixed"] = min(alloc["mixed"] + cut, 20)
            if excess == 0:
                break

    # 6) 합계 100% 조정
    total = sum(alloc.values())
    if total != 100:
        diff = 100 - total
        alloc["cash"] = max(0, alloc["cash"] + diff)

    return alloc


def compute_allocation_view(date) -> dict:
    date_str = str(date)

    # 1) 기본 신호 수집
    regime      = _get_macro_regime(date_str)
    country_sig = _get_country_signals(date_str)
    bond_sig    = _get_bond_signals(date_str)
    style_sig   = _get_style_signals(date_str)
    sector_tops = _get_sector_signals(date_str)
    krw_sig     = _get_krw_signal(date_str)

    # 2) 기준 배분
    base_kr = BASE_ALLOC.get(regime, BASE_ALLOC["N/A"])
    base_us = BASE_ALLOC_US.get(regime, BASE_ALLOC_US["N/A"])

    # 3) 신호 반영 → 조정 배분
    adj_kr = _adjust_alloc(base_kr, country_sig, bond_sig, style_sig, krw_sig)

    # 4) K-ICS 주식 한도 확인
    total_eq = sum(adj_kr.get(k, 0) for k in ["kr_eq", "us_eq", "global_eq", "em_eq", "sector_eq"])
    kics_breach = total_eq > K_ICS_EQUITY_LIMIT

    # 5) 상위 국가·섹터 코멘트
    ow_countries = [k for k, v in country_sig.items() if v == "OW"]
    uw_countries = [k for k, v in country_sig.items() if v == "UW"]

    # 6) 변액보험 포트폴리오 주요 코멘트
    rationale = _build_rationale(regime, country_sig, bond_sig, style_sig, krw_sig, sector_tops)

    return {
        "date":        date_str,
        "regime":      regime,
        "kr_alloc":    adj_kr,
        "base_kr":     base_kr,
        "us_alloc":    base_us,
        "total_eq":    total_eq,
        "kics_breach": kics_breach,
        "ow_countries": ow_countries,
        "uw_countries": uw_countries,
        "sector_tops": sector_tops,
        "krw_sig":     krw_sig,
        "bond_sig":    bond_sig,
        "style_sig":   style_sig,
        "rationale":   rationale,
    }


def _build_rationale(regime, country_sig, bond_sig, style_sig, krw_sig, sector_tops) -> list:
    """배분 근거 bullet points."""
    lines = []
    # Regime
    regime_text = {
        "Goldilocks":  "Goldilocks 국면 — 완만한 성장 + 저물가 → 위험자산 우호적",
        "Reflation":   "Reflation 국면 — 성장 회복 + 인플레 상승 → Value/원자재 강세",
        "Stagflation": "Stagflation 국면 — 성장 둔화 + 고물가 → 방어적 배분 우선",
        "Deflation":   "Deflation 국면 — 성장·물가 동반 하락 → 채권 비중 극대화",
        "N/A":         "매크로 국면 판단 불충분 — 중립적 배분 유지",
    }
    lines.append(f"📊 {regime_text.get(regime, regime)}")

    # Country
    ow = [k for k, v in country_sig.items() if v == "OW"]
    uw = [k for k, v in country_sig.items() if v == "UW"]
    if ow:
        lines.append(f"🌏 OW 국가: {', '.join(ow)} → 해당 지역 주식형 비중 확대")
    if uw:
        lines.append(f"⚠️ UW 국가: {', '.join(uw)} → 해당 지역 비중 축소")

    # Bond
    dur = bond_sig.get("dur_bias", "neutral")
    if dur == "long":
        lines.append("📈 듀레이션 확대 권고 → KR 국고 10Y + 해외채권형(TLT) 비중 유지")
    elif dur == "short":
        lines.append("📉 단기 집중 권고 → CD91D + 단기채 비중 확대, 장기채 축소")
    else:
        lines.append("⚖️ 바벨 전략 유지 → 단기 CD + 장기 KTB 조합")

    # KRW
    hedge = krw_sig.get("hedge_rec", "")
    if hedge:
        lines.append(f"💱 환율: {krw_sig.get('trend','')} (USDKRW {krw_sig.get('last','')})\n   → {hedge}")

    # Style
    top_style = style_sig.get("top_style", "")
    if top_style:
        lines.append(f"🎯 우선 스타일: {top_style} → 해당 스타일 해외주식형 내 비중 확대")

    # Sectors
    if sector_tops:
        lines.append(f"🏭 상위 섹터: {', '.join(sector_tops[:3])} → 섹터형 펀드 편입 고려")

    return lines


# ── HTML rendering ────────────────────────────────────────────────────────

def _fmt(v, dec=1, suffix="%"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{dec}f}{suffix}"


def _alloc_bar(pct: int, color: str = "#4a90d9") -> str:
    w = max(pct, 1)
    return f'<div style="background:{color};height:10px;border-radius:3px;width:{w*3}px;display:inline-block"></div>'


def render_html(data: dict) -> str:
    date_str = data["date"]
    regime   = data["regime"]
    adj_kr   = data["kr_alloc"]
    us_alloc = data["us_alloc"]
    krw_sig  = data["krw_sig"]
    total_eq = data["total_eq"]
    breach   = data["kics_breach"]
    rationale= data["rationale"]

    regime_colors = {
        "Goldilocks": "#27ae60", "Reflation": "#f39c12",
        "Stagflation": "#e74c3c", "Deflation": "#3498db", "N/A": "#888",
    }
    regime_color = regime_colors.get(regime, "#888")

    # Fund category colors by group
    group_colors = {
        "equity": "#4a90d9", "bond": "#27ae60",
        "mixed": "#9b59b6", "alts": "#f39c12", "cash": "#95a5a6",
    }

    def alloc_row(cat: dict, alloc: dict) -> str:
        cid   = cat["id"]
        pct   = alloc.get(cid, 0)
        base  = data["base_kr"].get(cid, 0)
        diff  = pct - base
        color = group_colors.get(cat["group"], "#888")
        diff_str = (f'<span style="color:#27ae60">+{diff}%p</span>' if diff > 0
                    else (f'<span style="color:#e74c3c">{diff}%p</span>' if diff < 0
                          else '<span style="color:#888">—</span>'))
        return f"""<tr style="border-bottom:1px solid #2a3a4e">
          <td style="padding:8px 12px;color:#e8eaf6;font-size:13px">{cat["name"]}</td>
          <td style="padding:8px 12px;text-align:right;color:{color};font-size:15px;font-weight:700">{pct}%</td>
          <td style="padding:8px 12px">{_alloc_bar(pct, color)}</td>
          <td style="padding:8px 12px;text-align:right;color:#aaa;font-size:13px">{base}%</td>
          <td style="padding:8px 12px;text-align:right">{diff_str}</td>
        </tr>"""

    def us_alloc_row(label, pct, color="#4a90d9") -> str:
        return f"""<tr style="border-bottom:1px solid #2a3a4e">
          <td style="padding:8px 12px;color:#e8eaf6;font-size:13px">{label}</td>
          <td style="padding:8px 12px;text-align:right;color:{color};font-size:15px;font-weight:700">{pct}%</td>
          <td style="padding:8px 12px">{_alloc_bar(pct, color)}</td>
        </tr>"""

    kr_rows = "".join(alloc_row(cat, adj_kr) for cat in FUND_CATEGORIES)

    us_labels = {
        "us_eq": ("미국 주식", "#4a90d9"),
        "intl_eq": ("선진국 주식(비미국)", "#5ba0e9"),
        "em_eq": ("신흥국 주식", "#3498db"),
        "us_bond": ("미국/선진 채권", "#27ae60"),
        "em_bond": ("신흥국 채권", "#2ecc71"),
        "alts": ("대안(금·원자재)", "#f39c12"),
        "cash": ("현금", "#95a5a6"),
    }
    us_rows = "".join(
        us_alloc_row(us_labels[k][0], v, us_labels[k][1])
        for k, v in us_alloc.items() if k in us_labels
    )

    kics_color = "#e74c3c" if breach else "#27ae60"
    kics_label = f"⚠️ K-ICS 주식한도({K_ICS_EQUITY_LIMIT}%) 초과 — 자동 조정됨" if breach \
                 else f"✅ K-ICS 주식한도({K_ICS_EQUITY_LIMIT}%) 이내"

    rationale_html = "".join(
        f'<li style="margin-bottom:8px;color:#ccc;font-size:13px">{line}</li>'
        for line in rationale
    )

    # equity/bond/alts/cash 합계
    eq_total   = sum(adj_kr.get(k, 0) for k in ["kr_eq","us_eq","global_eq","em_eq","sector_eq"])
    bond_total = sum(adj_kr.get(k, 0) for k in ["kr_bond","us_bond"])
    mix_total  = adj_kr.get("mixed", 0)
    alt_total  = adj_kr.get("alternative", 0)
    cash_total = adj_kr.get("cash", 0)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Allocation View — {date_str}</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#0d1b2a; color:#e8eaf6; font-family:'Segoe UI',sans-serif; padding:24px; }}
h2 {{ color:#7ec8e3; margin-bottom:4px; }}
h3 {{ color:#90caf9; margin:20px 0 10px; font-size:15px; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ background:#162032; color:#90caf9; padding:8px 12px; text-align:left; font-size:11px; letter-spacing:.5px; }}
.section {{ background:#132030; border-radius:10px; padding:20px; margin-bottom:20px; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
@media(max-width:800px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div style="max-width:1100px;margin:0 auto">
  <h2>Allocation View</h2>
  <div style="color:#aaa;font-size:13px;margin-bottom:20px">{date_str} 기준 | 미래에셋생명 변액보험 펀드 배분 의견</div>

  <!-- ── 현재 국면 + 환율 배너 ── -->
  <div class="section">
    <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center">
      <div style="flex:1;min-width:180px">
        <div style="color:#aaa;font-size:11px;margin-bottom:4px">현재 매크로 국면</div>
        <div style="color:{regime_color};font-size:24px;font-weight:700">{regime}</div>
      </div>
      <div style="flex:1;min-width:200px;background:#1e2a3a;border-radius:8px;padding:12px 16px">
        <div style="color:#aaa;font-size:11px;margin-bottom:4px">USDKRW 추세 / 환헤지 권고</div>
        <div style="color:{krw_sig["color"]};font-size:14px;font-weight:600">{krw_sig.get("trend","N/A")}</div>
        <div style="color:#ccc;font-size:12px;margin-top:3px">{krw_sig.get("hedge_rec","")}</div>
      </div>
      <div style="flex:1;min-width:200px;background:{kics_color}22;border:1px solid {kics_color};border-radius:8px;padding:12px 16px">
        <div style="color:#aaa;font-size:11px;margin-bottom:4px">K-ICS 주식한도</div>
        <div style="color:{kics_color};font-size:14px;font-weight:600">{kics_label}</div>
        <div style="color:#aaa;font-size:11px;margin-top:3px">현재 주식 합계: {eq_total}% / 한도 {K_ICS_EQUITY_LIMIT}%</div>
      </div>
    </div>
  </div>

  <!-- ── 배분 요약 도넛 대용 바 ── -->
  <div class="section">
    <h3>자산군 요약</h3>
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:10px">
      {"".join(f'<div style="background:{c}22;border:1px solid {c};border-radius:8px;padding:10px 16px;flex:1;min-width:100px;text-align:center"><div style="color:#aaa;font-size:11px">{l}</div><div style="color:{c};font-size:20px;font-weight:700">{v}%</div></div>'
               for l, v, c in [
                   ("주식합계", eq_total, "#4a90d9"),
                   ("채권합계", bond_total, "#27ae60"),
                   ("혼합형", mix_total, "#9b59b6"),
                   ("대안", alt_total, "#f39c12"),
                   ("현금", cash_total, "#95a5a6"),
               ])}
    </div>
  </div>

  <div class="grid2">
    <!-- ── KR 변액보험 배분 ── -->
    <div class="section">
      <h3>🇰🇷 KR 변액보험 펀드 배분 (KRW 기준)</h3>
      <table>
        <thead><tr>
          <th>펀드 유형</th>
          <th style="text-align:right">추천</th>
          <th>비중</th>
          <th style="text-align:right">기준</th>
          <th style="text-align:right">조정</th>
        </tr></thead>
        <tbody>{kr_rows}</tbody>
      </table>
      <div style="color:#aaa;font-size:11px;margin-top:8px">
        기준 = 국면별 베이스라인 | 조정 = 국가·채권·스타일 신호 반영
      </div>
    </div>

    <!-- ── US 참고 배분 ── -->
    <div class="section">
      <h3>🇺🇸 US 투자자 참고 배분 (USD 기준)</h3>
      <table>
        <thead><tr>
          <th>자산군</th>
          <th style="text-align:right">비중</th>
          <th>바</th>
        </tr></thead>
        <tbody>{us_rows}</tbody>
      </table>
      <div style="color:#aaa;font-size:11px;margin-top:8px">
        * USD 기준 글로벌 배분 참고 (K-ICS 제약 없음)
      </div>
    </div>
  </div>

  <!-- ── 배분 근거 ── -->
  <div class="section">
    <h3>배분 근거 및 주요 신호</h3>
    <div style="background:#1e2a3a;border-radius:8px;padding:16px 20px">
      <ul style="list-style:none;padding:0">
        {rationale_html}
      </ul>
    </div>
  </div>

  <!-- ── 주의사항 ── -->
  <div style="background:#1a1200;border:1px solid #5a3a00;border-radius:8px;padding:14px 18px;margin-bottom:20px">
    <div style="color:#f39c12;font-size:12px;font-weight:700;margin-bottom:6px">⚠️ 주의사항</div>
    <div style="color:#ccc;font-size:12px;line-height:1.6">
      본 배분 의견은 규칙 기반 알고리즘으로 자동 생성되며 투자 권유가 아닙니다.
      실제 운용 시 K-ICS 규제, ALM 듀레이션 매칭, 유동성 요건, 계약자 리스크 성향 등을 종합 고려하십시오.
      주식 비중은 K-ICS 규제상 30% 한도를 참고 기준으로 적용하였습니다.
    </div>
  </div>

  <div style="color:#555;font-size:11px;text-align:center">
    데이터: FRED · yfinance · ECOS · country/sector/bond/style view 통합 | Allocation View v1.0
  </div>
</div>
</body>
</html>"""
    return html


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Allocation View")
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    data   = compute_allocation_view(target)

    if args.html:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{args.date}.html"
        html = render_html(data)
        out_path.write_text(html, encoding="utf-8")
        print(f"Saved: {out_path}")
    else:
        import json
        class _E(json.JSONEncoder):
            def default(self, o):
                if hasattr(o, "item"): return o.item()
                return super().default(o)
        print(json.dumps(data, ensure_ascii=False, indent=2, cls=_E))


if __name__ == "__main__":
    main()
