"""Bond structure view — 채권 커브 · 크레딧 · 듀레이션 포지셔닝.

US 채권 커브(1-3Y/3-7Y/10Y/30Y/TIPS) + KR 커브(CD91D/3Y/10Y)를 분석해
KR 변액보험 운용 관점의 듀레이션·크레딧 포지셔닝을 제안한다.

Usage:
    python -m portfolio.view.bond_view --date 2026-04-14 --html
"""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "bond"
MARKET_CSV = ROOT / "history" / "market_data.csv"
MACRO_CSV = ROOT / "history" / "macro_indicators.csv"

# ── Bond segment definitions ──────────────────────────────────────────────

US_BOND_SEGMENTS = {
    "BD_US_1_3Y":  {"name": "US 1-3Y",    "etf": "SHY",     "dur": 1.9,  "type": "govvt"},
    "BD_US_3_7Y":  {"name": "US 3-7Y",    "etf": "IEI",     "dur": 4.5,  "type": "govvt"},
    "BD_US_10Y":   {"name": "US 7-10Y",   "etf": "IEF",     "dur": 7.5,  "type": "govvt"},
    "BD_TLT":      {"name": "US 20Y+",    "etf": "TLT",     "dur": 17.0, "type": "govvt"},
    "BD_US_TIPS":  {"name": "US TIPS",    "etf": "TIP",     "dur": 6.5,  "type": "inflation"},
    "BD_LQD":      {"name": "IG Credit",  "etf": "LQD",     "dur": 8.5,  "type": "credit"},
    "BD_HYG":      {"name": "HY Credit",  "etf": "HYG",     "dur": 4.0,  "type": "credit"},
    "BD_EMB":      {"name": "EM Bond",    "etf": "EMB",     "dur": 7.5,  "type": "em"},
}

KR_BOND_SEGMENTS = {
    "BD_KR_CD91D": {"name": "KR CD 91D",  "dur": 0.25, "type": "money"},
    "BD_KR_3Y":    {"name": "KR 국고 3Y", "dur": 3.0,  "type": "govvt"},
    "BD_KR_10Y":   {"name": "KR 국고 10Y","dur": 10.0, "type": "govvt"},
}

# FRED macro codes for yield/spread context
MACRO_RATES = {
    "US_FED_RATE":       "연준 기준금리",
    "US_2Y_YIELD":       "미국 2년 국채",
    "US_10Y_YIELD":      "미국 10년 국채",
    "US_YIELD_CURVE":    "미국 10Y-2Y 스프레드",
    "US_IG_SPREAD":        "IG 크레딧 스프레드",
    "US_HY_SPREAD":        "HY 크레딧 스프레드",
    "CREDIT_TED_SPREAD":   "TED 스프레드",
    "BOND_REAL_YIELD_10Y": "10Y TIPS 실질금리",
    "BOND_TERM_PREMIUM":   "ACM 기간프리미엄",
    "BOND_BREAKEVEN_10Y":  "10Y 손익분기점 인플레이션",
    "BOND_MOVE_INDEX":     "MOVE 채권변동성지수",
}


# ── Data loaders ──────────────────────────────────────────────────────────

def _load_prices(date: str) -> pd.DataFrame:
    from portfolio.market_source import load_wide_close
    target = pd.Timestamp(date)
    wide = load_wide_close(end=date)
    return wide[wide.index <= target].sort_index()


def _load_macro(date: str) -> dict:
    """FRED 금리/스프레드 최근 값."""
    from portfolio.market_source import load_macro_long
    df = load_macro_long(end=date)
    if df.empty:
        return {}
    target = pd.Timestamp(date)
    df = df[df["DATE"] <= target]
    result = {}
    for code in MACRO_RATES:
        sub = df[df["INDICATOR_CODE"] == code]
        if not sub.empty:
            row = sub.sort_values("DATE").iloc[-1]
            result[code] = {"value": float(row["VALUE"]), "date": str(row["DATE"].date())}
    return result


# ── Signal calculators ────────────────────────────────────────────────────

def _momentum(px: pd.Series, months: int) -> float:
    target = px.index[-1] - pd.DateOffset(months=months)
    past = px[px.index <= target]
    if past.empty:
        return np.nan
    return float(px.iloc[-1] / past.iloc[-1] - 1) * 100


def _trend_score(px: pd.Series) -> int:
    """MA200/MA50 추세 점수."""
    if len(px) < 55:
        return 0
    last = float(px.iloc[-1])
    ma50 = float(px.tail(50).mean())
    if len(px) < 205:
        return 1 if last > ma50 else -1
    ma200 = float(px.tail(200).mean())
    if last > ma200 and last > ma50:
        return 2
    elif last > ma200:
        return 1
    elif last < ma200 and last < ma50:
        return -2
    return -1


def _percentile(series: pd.Series, window: int = 252) -> float:
    """최근 window일 기준 현재 값의 백분위."""
    if len(series) < 30:
        return np.nan
    hist = series.tail(window)
    return float(np.sum(hist <= hist.iloc[-1]) / len(hist) * 100)


# ── Regime & positioning logic ────────────────────────────────────────────

def _credit_regime(hy_spread: float) -> tuple[str, str]:
    """HY 스프레드 기준 크레딧 국면 분류."""
    if np.isnan(hy_spread):
        return "N/A", "grey"
    if hy_spread < 300:
        return "Risk-On (스프레드 타이트)", "#27ae60"
    elif hy_spread < 500:
        return "경계 (스프레드 확대)", "#f39c12"
    return "위기 (스프레드 급등)", "#e74c3c"


def _duration_rec(yield_curve: float, fed_rate: float, us_10y: float) -> dict:
    """금리 환경 기반 듀레이션 포지셔닝 권고."""
    if np.isnan(yield_curve) or np.isnan(fed_rate):
        return {"label": "N/A", "bias": "neutral", "rationale": "데이터 부족"}

    # 수익률 곡선 분석
    if yield_curve > 50:          # 스팁(정상)
        curve_sig = "steepening"
    elif yield_curve < -20:       # 역전
        curve_sig = "inverted"
    else:
        curve_sig = "flat"

    # 연준 사이클 추정 (2Y-Fed 스프레드: 시장의 금리 인상/인하 기대)
    us_2y_fed_spread = fed_rate  # will be enriched below

    if curve_sig == "steepening":
        label = "중립~장기 비중 확대"
        bias = "long"
        rationale = "정상 기울기 → 장기채 보유 유리, 만기 확장 기회"
    elif curve_sig == "inverted":
        label = "단기 집중 (역전 해소 대기)"
        bias = "short"
        rationale = "역전 커브 → 단기채 금리 매력, 장기채 가격 리스크"
    else:
        label = "중립 (바벨 전략)"
        bias = "neutral"
        rationale = "플랫 커브 → 단기+장기 바벨, 중기채 기회비용"

    return {"label": label, "bias": bias, "rationale": rationale, "curve_sig": curve_sig}


def _kr_us_rate_diff(kr_10y: float, us_10y: float) -> dict:
    """KR-US 10Y 금리차 → 환헤지 비용 및 원화 방향 시사."""
    if np.isnan(kr_10y) or np.isnan(us_10y):
        return {"diff": np.nan, "signal": "N/A", "hedge_cost": np.nan}
    diff = kr_10y - us_10y
    # KR < US → KRW 약세 압력 (금리차 역전)
    if diff < -0.5:
        signal = "원화 약세 압력 (KR<US 역전)"
        color = "#e74c3c"
    elif diff < 0.5:
        signal = "금리차 중립"
        color = "#f39c12"
    else:
        signal = "원화 강세 지지 (KR>US)"
        color = "#27ae60"
    return {"diff": round(diff, 2), "signal": signal, "color": color}


# ── Main compute ──────────────────────────────────────────────────────────

def _score_bond_segment(code: str, prices: pd.DataFrame) -> dict:
    meta = {**US_BOND_SEGMENTS.get(code, {}), **KR_BOND_SEGMENTS.get(code, {})}
    result = {
        "code": code,
        "name": meta.get("name", code),
        "etf": meta.get("etf", "—"),
        "dur": meta.get("dur", np.nan),
        "type": meta.get("type", ""),
        "last": np.nan,
        "last_date": "N/A",
        "mom_1m": np.nan,
        "mom_3m": np.nan,
        "mom_6m": np.nan,
        "trend": 0,
        "pct_1y": np.nan,
    }
    if code not in prices.columns:
        return result

    px = prices[code].dropna()
    if px.empty:
        return result

    result["last"] = round(float(px.iloc[-1]), 2)
    result["last_date"] = str(px.index[-1].date())
    result["mom_1m"] = round(_momentum(px, 1), 2)
    result["mom_3m"] = round(_momentum(px, 3), 2)
    result["mom_6m"] = round(_momentum(px, 6), 2)
    result["trend"] = _trend_score(px)
    result["pct_1y"] = round(_percentile(px, 252), 1)
    return result


def _decompose_yield(nominal_10y: float, real_yield_10y: float,
                     breakeven_10y: float, fed_rate: float) -> dict:
    """명목금리 분해: 실질금리 + 기대인플레이션 + 기간프리미엄 근사.

    명목 ≈ 실질 + 손익분기점 (TIPS 기반)
    기간프리미엄 ≈ 명목 - 실질 - 손익분기점 (잔차)
    """
    result = {
        "nominal": nominal_10y,
        "real":    real_yield_10y,
        "breakeven": breakeven_10y,
        "term_premium": np.nan,
        "interpretation": "데이터 부족",
    }
    if np.isnan(nominal_10y) or np.isnan(real_yield_10y):
        return result

    if not np.isnan(breakeven_10y):
        term_prem = nominal_10y - real_yield_10y - breakeven_10y
    else:
        # 근사: 목표 인플레이션 2%로 가정
        term_prem = nominal_10y - real_yield_10y - 2.0

    result["term_premium"] = round(term_prem, 3)

    # 해석
    if real_yield_10y < 0:
        interp = "실질금리 음수 → 유동성 장세, 위험자산 우호"
    elif real_yield_10y > 2.5:
        interp = f"실질금리 {real_yield_10y:.2f}% 고점 → 성장주·EM 밸류에이션 압박"
    elif term_prem > 0.5:
        interp = f"기간프리미엄 {term_prem:.2f}% 상승 → 장기채 공급 압력 / 재정 우려"
    elif term_prem < -0.3:
        interp = f"기간프리미엄 {term_prem:.2f}% 음수 → 안전자산 수요 강세"
    else:
        interp = f"실질금리 {real_yield_10y:.2f}%, 기간프리미엄 {term_prem:.2f}% 중립 수준"

    result["interpretation"] = interp
    return result


def _nelson_siegel_approx(fed_rate: float, us_2y: float, us_10y: float,
                          us_30y: float = np.nan) -> dict:
    """Nelson-Siegel 커브 Level/Slope/Curvature 근사치.

    β0 (Level)    ≈ 장기금리 수준 (10Y 근사)
    β1 (Slope)    ≈ -(단기 - 장기) = -(FF - 10Y)
    β2 (Curvature)≈ 2×중기 - 단기 - 장기 (2Y를 중기로 사용)
    """
    result = {
        "level": np.nan, "slope": np.nan, "curvature": np.nan,
        "interpretation": "데이터 부족"
    }
    if np.isnan(us_10y):
        return result

    level = us_10y
    slope = -(fed_rate - us_10y) if not np.isnan(fed_rate) else np.nan
    curv  = (2 * us_2y - fed_rate - us_10y) if not np.isnan(us_2y) and not np.isnan(fed_rate) else np.nan

    result.update({"level": round(level, 3),
                   "slope": round(slope, 3) if not np.isnan(slope) else np.nan,
                   "curvature": round(curv, 3) if not np.isnan(curv) else np.nan})

    # 해석
    interps = []
    if not np.isnan(level):
        if level > 4.5:
            interps.append(f"장기금리 수준 높음({level:.2f}%) → 채권 발행 비용 상승")
        elif level < 2.5:
            interps.append(f"장기금리 낮음({level:.2f}%) → 성장 기대 약화 또는 안전자산 선호")
    if not np.isnan(slope):
        if slope < 0:
            interps.append(f"기울기 역전({slope:+.2f}%) → 경기침체 선행 경고")
        elif slope > 1.5:
            interps.append(f"기울기 가파름({slope:+.2f}%) → 경기 정상화 기대")
    if not np.isnan(curv):
        if curv > 1.0:
            interps.append(f"곡률 높음({curv:+.2f}%) → 중기채 상대적 고금리")

    result["interpretation"] = "; ".join(interps) if interps else "커브 구조 중립"
    return result


def _move_regime(move_index: float) -> tuple[str, str]:
    """MOVE 지수 기준 채권 변동성 국면."""
    if np.isnan(move_index):
        return "N/A", "#94a3b8"
    if move_index > 140:
        return "채권변동성 극도 위험 (MOVE>140)", "#dc2626"
    elif move_index > 100:
        return "채권변동성 경계 (MOVE>100)", "#f59e0b"
    else:
        return f"채권변동성 안정 (MOVE={move_index:.0f})", "#059669"


def compute_bond_view(date) -> dict:
    date_str = str(date)
    prices = _load_prices(date_str)
    macro = _load_macro(date_str)

    # Bond ETF signals
    us_bonds = [_score_bond_segment(c, prices) for c in US_BOND_SEGMENTS]
    kr_bonds = [_score_bond_segment(c, prices) for c in KR_BOND_SEGMENTS]

    # FRED macro rates (기존)
    fed_rate   = macro.get("US_FED_RATE",    {}).get("value", np.nan)
    us_2y      = macro.get("US_2Y_YIELD",    {}).get("value", np.nan)
    us_10y     = macro.get("US_10Y_YIELD",   {}).get("value", np.nan)
    yield_curve = macro.get("US_YIELD_CURVE", {}).get("value", np.nan)
    hy_spread  = macro.get("US_HY_SPREAD",   {}).get("value", np.nan)
    ig_spread  = macro.get("US_IG_SPREAD",   {}).get("value", np.nan)

    real_yield_10y = macro.get("BOND_REAL_YIELD_10Y", {}).get("value", np.nan)
    term_premium   = macro.get("BOND_TERM_PREMIUM",   {}).get("value", np.nan)
    breakeven_10y  = macro.get("BOND_BREAKEVEN_10Y",  {}).get("value", np.nan)
    move_index     = macro.get("BOND_MOVE_INDEX",     {}).get("value", np.nan)
    ted_spread     = macro.get("CREDIT_TED_SPREAD",   {}).get("value", np.nan)

    hy_best = hy_spread
    ig_best = ig_spread

    # KR rates from ETF price data (ECOS: level = rate)
    kr_cd91d_row = kr_bonds[0]
    kr_3y_row    = kr_bonds[1]
    kr_10y_row   = kr_bonds[2]
    kr_10y_val   = kr_10y_row["last"] if not np.isnan(kr_10y_row["last"]) else np.nan

    # Spread and regime signals
    credit_reg, credit_color = _credit_regime(hy_best)
    dur_rec  = _duration_rec(yield_curve, fed_rate, us_10y)
    kr_us_diff = _kr_us_rate_diff(kr_10y_val, us_10y)

    # Implied cut/hike: 2Y - Fed Funds
    implied = round(us_2y - fed_rate, 2) if not (np.isnan(us_2y) or np.isnan(fed_rate)) else np.nan
    implied_sig = "금리 인하 기대" if (not np.isnan(implied) and implied < -0.25) \
        else ("금리 인상 기대" if (not np.isnan(implied) and implied > 0.25) else "동결 기대")

    # ── 새로운 분석 ───────────────────────────────────────────
    yield_decomp = _decompose_yield(us_10y, real_yield_10y, breakeven_10y, fed_rate)
    ns_curve     = _nelson_siegel_approx(fed_rate, us_2y, us_10y)
    move_label, move_color = _move_regime(move_index)

    # MOVE 기반 듀레이션 조정 권고
    if not np.isnan(move_index) and move_index > 100:
        dur_rec["rationale"] += f" | MOVE {move_index:.0f} 상승 → 변동성 주의, 듀레이션 축소 경향"

    # ALM recommendation for 변액보험
    alm_rec = _alm_recommendation(dur_rec["bias"], hy_best, kr_us_diff["diff"])

    return {
        "date": date_str,
        "us_bonds": us_bonds,
        "kr_bonds": kr_bonds,
        "rates": {
            "fed_rate": fed_rate,
            "us_2y": us_2y,
            "us_10y": us_10y,
            "yield_curve": yield_curve,
            "hy_spread": hy_best,
            "ig_spread": ig_best,
            "kr_10y": kr_10y_val,
            # 확장
            "real_yield_10y": real_yield_10y,
            "breakeven_10y":  breakeven_10y,
            "move_index":     move_index,
            "ted_spread":     ted_spread,
        },
        "credit_regime": credit_reg,
        "credit_color": credit_color,
        "duration_rec": dur_rec,
        "kr_us_diff": kr_us_diff,
        "implied_move": {"value": implied, "signal": implied_sig},
        "alm_rec": alm_rec,
        # 새로운 분석 결과
        "yield_decomp": yield_decomp,
        "ns_curve": ns_curve,
        "move_regime": {"label": move_label, "color": move_color, "value": move_index},
    }


def _alm_recommendation(dur_bias: str, hy_spread: float, kr_us_diff: float) -> dict:
    """변액보험 ALM 관점 채권 포지셔닝 권고."""
    # 보험사는 장기 부채 → 장기 자산 선호. 단 금리 하락기엔 장기채 가격 리스크.
    lines = []

    if dur_bias == "long":
        lines.append("▶ 장기 국고채(KR 10Y / TLT) 비중 유지 — 부채 듀레이션 매칭 유리")
    elif dur_bias == "short":
        lines.append("▶ 단기채 집중 운용 — 역전 커브 해소 후 장기 재진입 검토")
    else:
        lines.append("▶ 바벨 전략: KR CD91D + KR 10Y 조합으로 ALM 유지")

    if not np.isnan(hy_spread):
        if hy_spread < 300:
            lines.append("▶ IG 크레딧 일부 편입 가능 — 스프레드 타이트하나 캐리 확보")
        elif hy_spread > 500:
            lines.append("▶ HY 크레딧 축소 — 스프레드 급등, 신용리스크 확대")

    if not np.isnan(kr_us_diff):
        if kr_us_diff < -0.5:
            lines.append("▶ 해외 채권 환헤지 비용 상승 (KR<US) — 언헤지 EM/US 채권 비중 축소 고려")
        else:
            lines.append("▶ KR-US 금리차 안정 — 해외 채권 헤지 비용 관리 가능")

    return {"lines": lines}


# ── HTML rendering ────────────────────────────────────────────────────────

def _fmt(v, decimals=2, suffix=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{decimals}f}{suffix}"


def _mom_color(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "#888"
    return "#27ae60" if v > 0 else "#e74c3c"


def _trend_badge(t: int) -> str:
    labels = {2: ("강한 상승", "#27ae60"), 1: ("상승", "#8bc34a"),
              0: ("중립", "#888"), -1: ("하락", "#e67e22"), -2: ("강한 하락", "#e74c3c")}
    label, color = labels.get(t, ("N/A", "#888"))
    return f'<span style="color:{color};font-weight:600">{label}</span>'


def _pct_bar(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    color = "#e74c3c" if v < 30 else ("#27ae60" if v > 70 else "#f39c12")
    return (f'<span style="color:{color}">{v:.0f}%ile</span>')


def _decomp_bar(label: str, value: float, color: str, total: float = 5.0) -> str:
    """수익률 분해 가로 막대."""
    if np.isnan(value):
        return f'<div style="margin:6px 0"><span style="color:#94a3b8;font-size:12px">{label}: —</span></div>'
    pct = min(max(abs(value) / total * 100, 2), 100)
    sign_color = color if value >= 0 else "#dc2626"
    sign = "+" if value > 0 else ""
    return f"""<div style="margin:6px 0">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="width:160px;font-size:12px;color:#64748b">{label}</span>
        <div style="flex:1;height:10px;background:#f1f5f9;border-radius:5px;overflow:hidden">
          <div style="width:{pct:.0f}%;height:100%;background:{sign_color};border-radius:5px"></div>
        </div>
        <span style="width:60px;text-align:right;font-weight:700;color:{sign_color};font-size:13px">{sign}{value:.2f}%</span>
      </div>
    </div>"""


def _ns_component_badge(label: str, value: float, hint: str) -> str:
    if np.isnan(value):
        return f'<div class="stat-card"><div class="label">{label}</div><div style="font-size:18px;font-weight:700;color:#94a3b8">—</div><div class="sub">{hint}</div></div>'
    # color logic
    if label == "Level":
        color = "#dc2626" if value > 4.5 else ("#059669" if value < 2.5 else "#d97706")
    elif label == "Slope":
        color = "#dc2626" if value < 0 else ("#059669" if value > 1.5 else "#d97706")
    else:
        color = "#7c3aed" if abs(value) > 1 else "#64748b"
    sign = "+" if value > 0 else ""
    return f'<div class="stat-card"><div class="label">{label}</div><div style="font-size:18px;font-weight:700;color:{color}">{sign}{value:.2f}%</div><div class="sub">{hint}</div></div>'


def render_html(data: dict) -> str:
    from ._shared import html_page

    date_str     = data["date"]
    rates        = data["rates"]
    dur          = data["duration_rec"]
    kr_us        = data["kr_us_diff"]
    alm          = data["alm_rec"]
    implied      = data["implied_move"]
    yield_decomp = data.get("yield_decomp", {})
    ns_curve     = data.get("ns_curve", {})
    move_regime  = data.get("move_regime", {})

    # ── signal colors (light-theme friendly)
    bias_colors = {"long": "#059669", "short": "#dc2626", "neutral": "#d97706"}
    bias_color  = bias_colors.get(dur["bias"], "#6b7280")
    curve_labels = {
        "steepening": ("정상 (스팁)", "#059669"),
        "inverted":   ("역전", "#dc2626"),
        "flat":       ("플랫", "#d97706"),
    }
    curve_label, curve_color = curve_labels.get(dur.get("curve_sig", ""), ("N/A", "#6b7280"))

    def stat_card(label, value, unit="", sub=""):
        return f"""<div class="stat-card">
          <div class="label">{label}</div>
          <div class="value">{_fmt(value, 2)}<span style="font-size:13px;font-weight:400;color:var(--muted)"> {unit}</span></div>
          {f'<div class="sub">{sub}</div>' if sub else ''}
        </div>"""

    def sig_card(label, value_html, sub=""):
        return f"""<div class="stat-card" style="flex:1;min-width:160px">
          <div class="label">{label}</div>
          <div style="font-size:16px;font-weight:700;margin:4px 0">{value_html}</div>
          {f'<div class="sub">{sub}</div>' if sub else ''}
        </div>"""

    type_badge_map = {
        "govvt":     '<span style="background:#dbeafe;color:#1d4ed8;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600">국채</span>',
        "inflation": '<span style="background:#fef3c7;color:#d97706;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600">물가연동</span>',
        "credit":    '<span style="background:#fce7f3;color:#be185d;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600">크레딧</span>',
        "em":        '<span style="background:#dcfce7;color:#15803d;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600">EM</span>',
        "money":     '<span style="background:#f3f4f6;color:#6b7280;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600">단기</span>',
    }

    def bond_row(seg: dict, is_kr=False) -> str:
        badge   = type_badge_map.get(seg["type"], "")
        etf_col = f'<td class="muted" style="font-size:12px">{seg.get("etf","—")}</td>' if not is_kr else ""
        mc = lambda v: "up" if (v and not np.isnan(v) and v > 0) else ("down" if (v and not np.isnan(v) and v < 0) else "muted")
        return f"""<tr>
          <td>{badge} <strong>{seg["name"]}</strong></td>
          {etf_col}
          <td class="muted">{_fmt(seg["dur"],1)}Y</td>
          <td><span class="mono">{_fmt(seg["last"])}</span></td>
          <td class="{mc(seg['mom_1m'])}">{_fmt(seg['mom_1m'],2,'%')}</td>
          <td class="{mc(seg['mom_3m'])}">{_fmt(seg['mom_3m'],2,'%')}</td>
          <td class="{mc(seg['mom_6m'])}">{_fmt(seg['mom_6m'],2,'%')}</td>
          <td>{_trend_badge(seg['trend'])}</td>
          <td>{_pct_bar(seg['pct_1y'])}</td>
        </tr>"""

    us_rows  = "".join(bond_row(s) for s in data["us_bonds"])
    kr_rows  = "".join(bond_row(s, is_kr=True) for s in data["kr_bonds"])
    alm_html = "".join(f'<li style="margin-bottom:8px">{l}</li>' for l in alm["lines"])

    credit_color_map = {"#27ae60": "var(--up)", "#f39c12": "#d97706", "#e74c3c": "var(--down)"}
    credit_fg = credit_color_map.get(data["credit_color"], data["credit_color"])
    krus_color_map = {"#e74c3c": "var(--down)", "#27ae60": "var(--up)", "#f39c12": "#d97706"}
    krus_fg = krus_color_map.get(kr_us["color"], kr_us["color"])

    # ── Yield Decomposition HTML ───────────────────────────────────────────
    yd = yield_decomp
    yd_nominal   = yd.get("nominal",     np.nan)
    yd_real      = yd.get("real",        np.nan)
    yd_breakeven = yd.get("breakeven",   np.nan)
    yd_term      = yd.get("term_premium",np.nan)
    yd_interp    = yd.get("interpretation", "데이터 부족")

    decomp_total  = max(abs(yd_nominal) if not np.isnan(yd_nominal) else 0,
                        abs(yd_real) if not np.isnan(yd_real) else 0, 6.0)
    decomp_html   = (
        _decomp_bar("명목 10Y 금리",     yd_nominal,   "#1d4ed8", decomp_total) +
        _decomp_bar("실질금리 (TIPS)",   yd_real,      "#059669", decomp_total) +
        _decomp_bar("기대인플레이션",    yd_breakeven, "#d97706", decomp_total) +
        _decomp_bar("기간프리미엄",      yd_term,      "#7c3aed", decomp_total)
    )

    # ── Nelson-Siegel badges ───────────────────────────────────────────────
    ns_level  = ns_curve.get("level",       np.nan)
    ns_slope  = ns_curve.get("slope",       np.nan)
    ns_curv   = ns_curve.get("curvature",   np.nan)
    ns_interp = ns_curve.get("interpretation", "데이터 부족")
    ns_badges = (
        _ns_component_badge("Level (β₀)", ns_level,  "장기금리 수준") +
        _ns_component_badge("Slope (β₁)", ns_slope,  "장단기 기울기") +
        _ns_component_badge("Curvature (β₂)", ns_curv, "중기채 곡률")
    )

    # ── MOVE Index ────────────────────────────────────────────────────────
    move_label = move_regime.get("label", "N/A")
    move_color = move_regime.get("color", "#94a3b8")
    move_val   = move_regime.get("value", np.nan)
    move_val_str = f"{move_val:.1f}" if not np.isnan(move_val) else "—"

    # TED spread
    ted = rates.get("ted_spread", np.nan)
    ted_color = "#dc2626" if (not np.isnan(ted) and ted > 100) else \
                "#d97706" if (not np.isnan(ted) and ted > 50) else "#059669"

    body = f"""
<div class="card">
  <h2>💰 금리 환경 요약</h2>
  <div class="stat-grid">
    {stat_card("연준 기준금리", rates["fed_rate"], "%")}
    {stat_card("미국 2Y 국채", rates["us_2y"], "%")}
    {stat_card("미국 10Y 국채", rates["us_10y"], "%")}
    {stat_card("10Y-2Y 스프레드", rates["yield_curve"], "bp")}
    {stat_card("HY 스프레드", rates["hy_spread"], "bp")}
    {stat_card("IG 스프레드", rates["ig_spread"], "bp")}
    {stat_card("KR 국고 10Y", rates["kr_10y"], "%")}
  </div>
  <div class="stat-grid" style="margin-top:0">
    {sig_card("수익률 곡선 형태",
      f'<span style="color:{curve_color}">{curve_label}</span>',
      f"10Y-2Y = {_fmt(rates['yield_curve'],1)}bp")}
    {sig_card("연준 금리 방향 기대",
      implied["signal"],
      f"2Y-Fed = {_fmt(implied['value'],2)}%p")}
    {sig_card("크레딧 국면",
      f'<span style="color:{credit_fg}">{data["credit_regime"]}</span>',
      f"HY = {_fmt(rates['hy_spread'],1)}bp")}
    {sig_card("KR-US 10Y 금리차",
      f'<span style="color:{krus_fg}">{_fmt(kr_us["diff"],2)}%p</span>',
      kr_us["signal"])}
    {sig_card("듀레이션 포지셔닝",
      f'<span style="color:{bias_color}">{dur["label"]}</span>',
      dur["rationale"])}
  </div>
</div>

<div class="card">
  <h2>🔬 채권 수익률 분해 (Yield Decomposition)</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
    <div>
      <h3 style="font-size:14px;color:#64748b;margin-bottom:12px">명목금리 = 실질금리 + 기대인플레이션 + 기간프리미엄</h3>
      {decomp_html}
      <div style="margin-top:12px;padding:10px 14px;background:#f8fafc;border-radius:8px;font-size:12px;color:#475569;line-height:1.6">
        💡 {yd_interp}
      </div>
    </div>
    <div>
      <h3 style="font-size:14px;color:#64748b;margin-bottom:12px">Nelson-Siegel 커브 분해 (근사)</h3>
      <div class="stat-grid" style="grid-template-columns:repeat(3,1fr)">
        {ns_badges}
      </div>
      <div style="margin-top:10px;padding:10px 14px;background:#f8fafc;border-radius:8px;font-size:12px;color:#475569;line-height:1.6">
        💡 {ns_interp}
      </div>
    </div>
  </div>
</div>

<div class="card">
  <h2>📊 채권 변동성 & 신용 시장</h2>
  <div class="stat-grid">
    <div class="stat-card" style="border-top:3px solid {move_color}">
      <div class="label">MOVE 채권변동성지수</div>
      <div style="font-size:22px;font-weight:800;color:{move_color}">{move_val_str}</div>
      <div class="sub" style="color:{move_color}">{move_label}</div>
    </div>
    {sig_card("TED 스프레드",
      f'<span style="color:{ted_color}">{_fmt(ted,1)} bp</span>',
      "단기 달러 유동성 긴장도 (>50bp 경계)")}
    {sig_card("TIPS 실질금리",
      f'<span style="color:{"#dc2626" if (not np.isnan(yd_real) and yd_real > 2.5) else ("#059669" if (not np.isnan(yd_real) and yd_real < 0) else "#d97706")}">{_fmt(yd_real,2)}%</span>',
      "양수·상승 → 성장주 밸류에이션 압박")}
    {sig_card("기간프리미엄 (ACM)",
      f'<span style="color:{"#d97706" if (not np.isnan(yd_term) and yd_term > 0.5) else "#64748b"}">{_fmt(yd_term,2)}%</span>',
      ">0.5% → 장기채 공급 압력")}
    {sig_card("기대인플레이션 (BEI)",
      f'<span style="color:{"#dc2626" if (not np.isnan(yd_breakeven) and yd_breakeven > 2.5) else "#059669"}">{_fmt(yd_breakeven,2)}%</span>',
      "10Y 손익분기점")}
  </div>
</div>

<div class="card">
  <h2>🇺🇸 미국 채권 ETF</h2>
  <table>
    <thead><tr>
      <th>세그먼트</th><th>ETF</th><th>듀레이션</th><th>현재가</th>
      <th>1M 수익률</th><th>3M 수익률</th><th>6M 수익률</th>
      <th>추세</th><th>1Y 백분위</th>
    </tr></thead>
    <tbody>{us_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>🇰🇷 한국 채권 금리 (ECOS)</h2>
  <table>
    <thead><tr>
      <th>세그먼트</th><th>듀레이션</th><th>금리(%)</th>
      <th>1M 변화</th><th>3M 변화</th><th>6M 변화</th>
      <th>추세</th><th>1Y 백분위</th>
    </tr></thead>
    <tbody>{kr_rows}</tbody>
  </table>
  <p class="muted" style="font-size:11px;margin-top:8px">* KR 채권은 금리 레벨 기준</p>
</div>

<div class="card">
  <h2>📋 변액보험 ALM 포지셔닝 권고</h2>
  <div style="background:var(--primary-light);border-left:4px solid var(--primary);border-radius:0 8px 8px 0;padding:16px 20px;margin-bottom:12px">
    <ul style="list-style:none;padding:0">
      {alm_html}
    </ul>
  </div>
  <p class="muted" style="font-size:12px">
    📌 ALM 원칙: 보험 부채 장기 듀레이션(8-12Y) → 자산 듀레이션 매칭 유지.
    금리 상승기엔 단기채 집중 후 장기 재진입 기회 포착.
  </p>
</div>
"""

    return html_page(
        title="채권 View",
        date_str=date_str,
        body=body,
        current_view="bond",
        source="FRED (금리/스프레드) · yfinance (채권 ETF) · ECOS (한국 금리)",
    )


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bond View")
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    data = compute_bond_view(target)

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
                if hasattr(o, "item"):
                    return o.item()
                return super().default(o)
        print(json.dumps(data, ensure_ascii=False, indent=2, cls=_E))


if __name__ == "__main__":
    main()
