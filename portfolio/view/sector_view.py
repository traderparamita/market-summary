"""Sector rotation view — 섹터 로테이션 의견.

US SPDR 11개 섹터 ETF + KR TIGER 섹터 ETF 10개에 대한 로테이션 신호를 생성한다.
- 신호: 모멘텀(1/3/6M), MA200/MA50 추세, 매크로 Regime 친화도 매트릭스
- 섹터 리더/래거 순위 + KR-US 섹터 연계 비교

Usage:
    python -m portfolio.view.sector_view --date 2026-04-14 --html
"""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "sector"
MARKET_CSV = ROOT / "history" / "market_data.csv"
MACRO_CSV = ROOT / "history" / "macro_indicators.csv"

# ── Sector definitions ────────────────────────────────────────────────────

US_SECTORS = {
    "SC_US_TECH":    {"name": "Technology",       "etf": "XLK",  "cycle": ["Goldilocks"], "kr_peer": "SC_KR_IT"},
    "SC_US_COMM":    {"name": "Communication",    "etf": "XLC",  "cycle": ["Goldilocks"], "kr_peer": "SC_KR_COMM"},
    "SC_US_FIN":     {"name": "Financials",       "etf": "XLF",  "cycle": ["Reflation"], "kr_peer": "SC_KR_FIN"},
    "SC_US_ENERGY":  {"name": "Energy",           "etf": "XLE",  "cycle": ["Reflation", "Stagflation"], "kr_peer": "SC_KR_ENERGY"},
    "SC_US_HEALTH":  {"name": "Health Care",      "etf": "XLV",  "cycle": ["Deflation", "Stagflation"], "kr_peer": "SC_KR_HLTH"},
    "SC_US_INDU":    {"name": "Industrials",      "etf": "XLI",  "cycle": ["Goldilocks", "Reflation"], "kr_peer": "SC_KR_INDU"},
    "SC_US_MATL":    {"name": "Materials",        "etf": "XLB",  "cycle": ["Reflation"], "kr_peer": "SC_KR_HEAVY"},
    "SC_US_DISCR":   {"name": "Consumer Discr.",  "etf": "XLY",  "cycle": ["Goldilocks"], "kr_peer": "SC_KR_DISCR"},
    "SC_US_STAPLES": {"name": "Consumer Staples", "etf": "XLP",  "cycle": ["Deflation", "Stagflation"], "kr_peer": "SC_KR_STAPLES"},
    "SC_US_UTIL":    {"name": "Utilities",        "etf": "XLU",  "cycle": ["Deflation"], "kr_peer": "SC_KR_STEEL"},
    "SC_US_REIT":    {"name": "Real Estate",      "etf": "XLRE", "cycle": ["Deflation"], "kr_peer": "SC_KR_CONSTR"},
}

# ── TIGER 200 GICS 11개 (sector_country 사이클 기준) ─────────────────────
KR_SECTORS = {
    "SC_KR_CONSTR":  {"name": "건설",             "etf": "TIGER 200 건설",              "ticker": "139270.KS", "cycle": ["Reflation", "Early"],              "us_peer": "SC_US_REIT"},
    "SC_KR_DISCR":   {"name": "경기소비재",        "etf": "TIGER 200 경기소비재",        "ticker": "227540.KS", "cycle": ["Goldilocks", "Early"],              "us_peer": "SC_US_DISCR"},
    "SC_KR_FIN":     {"name": "금융",             "etf": "TIGER 200 금융",              "ticker": "435420.KS", "cycle": ["Reflation", "Early"],              "us_peer": "SC_US_FIN"},
    "SC_KR_INDU":    {"name": "산업재",            "etf": "TIGER 200 산업재",            "ticker": "227560.KS", "cycle": ["Goldilocks", "Reflation", "Early"], "us_peer": "SC_US_INDU"},
    "SC_KR_STAPLES": {"name": "생활소비재",        "etf": "TIGER 200 생활소비재",        "ticker": "227550.KS", "cycle": ["Deflation", "Stagflation"],        "us_peer": "SC_US_STAPLES"},
    "SC_KR_ENERGY":  {"name": "에너지화학",        "etf": "TIGER 200 에너지화학",        "ticker": "472170.KS", "cycle": ["Reflation", "Stagflation"],        "us_peer": "SC_US_ENERGY"},
    "SC_KR_HEAVY":   {"name": "중공업",            "etf": "TIGER 200 중공업",            "ticker": "157490.KS", "cycle": ["Reflation", "Mid"],                "us_peer": "SC_US_MATL"},
    "SC_KR_STEEL":   {"name": "철강소재",          "etf": "TIGER 200 철강소재",          "ticker": "494840.KS", "cycle": ["Reflation"],                       "us_peer": "SC_US_UTIL"},
    "SC_KR_COMM":    {"name": "커뮤니케이션서비스","etf": "TIGER 200 커뮤니케이션서비스","ticker": "364990.KS", "cycle": ["Goldilocks"],                      "us_peer": "SC_US_COMM"},
    "SC_KR_HLTH":    {"name": "헬스케어",          "etf": "TIGER 200 헬스케어",          "ticker": "227570.KS", "cycle": ["Deflation", "Stagflation"],        "us_peer": "SC_US_HEALTH"},
    "SC_KR_IT":      {"name": "IT",               "etf": "TIGER 200 IT",               "ticker": "364980.KS", "cycle": ["Goldilocks", "Mid"],              "us_peer": "SC_US_TECH"},
}

# 매크로 국면 → 선호 섹터 매핑
REGIME_SECTOR_MAP = {
    "Goldilocks":  ["SC_US_TECH", "SC_US_DISCR", "SC_US_INDU", "SC_US_COMM",
                    "SC_KR_IT", "SC_KR_COMM", "SC_KR_INDU", "SC_KR_DISCR"],
    "Reflation":   ["SC_US_ENERGY", "SC_US_FIN", "SC_US_MATL", "SC_US_INDU",
                    "SC_KR_FIN", "SC_KR_HEAVY", "SC_KR_STEEL", "SC_KR_ENERGY", "SC_KR_CONSTR"],
    "Stagflation": ["SC_US_ENERGY", "SC_US_HEALTH", "SC_US_STAPLES",
                    "SC_KR_STAPLES", "SC_KR_ENERGY", "SC_KR_HLTH"],
    "Deflation":   ["SC_US_HEALTH", "SC_US_STAPLES", "SC_US_UTIL", "SC_US_REIT",
                    "SC_KR_HLTH", "SC_KR_STAPLES", "SC_KR_CONSTR"],
}

SP500_CODE = "EQ_SP500"
KOSPI_CODE = "EQ_KOSPI"

# ── Business cycle × sector matrix ────────────────────────────────────────
# 4-phase NBER-style cycle: Early / Mid / Late / Recession
# Based on Fidelity sector rotation research

CYCLE_SECTOR_MAP = {
    "Early":     ["SC_US_DISCR", "SC_US_FIN",    "SC_US_INDU",
                  "SC_KR_FIN",   "SC_KR_DISCR",  "SC_KR_CONSTR", "SC_KR_INDU"],
    "Mid":       ["SC_US_TECH",  "SC_US_INDU",   "SC_US_COMM",
                  "SC_KR_IT",    "SC_KR_COMM",   "SC_KR_HEAVY"],
    "Late":      ["SC_US_ENERGY","SC_US_MATL",   "SC_US_HEALTH", "SC_US_STAPLES",
                  "SC_KR_STEEL", "SC_KR_ENERGY", "SC_KR_STAPLES"],
    "Recession": ["SC_US_HEALTH","SC_US_STAPLES","SC_US_UTIL",   "SC_US_REIT",
                  "SC_KR_HLTH",  "SC_KR_STAPLES","SC_KR_CONSTR"],
}

CYCLE_DESCRIPTIONS = {
    "Early":     "경기 회복 초기 — 성장 반등, 금리 하락, 신용 개선",
    "Mid":       "경기 확장 중반 — 이익 성장, 금리 상승 시작, 유동성 양호",
    "Late":      "경기 확장 후기 — 인플레이션 상승, 원자재 강세, 수익률 피크",
    "Recession": "경기 침체 — 성장 위축, 방어주·채권 선호, 크레딧 스프레드 확대",
}


# ── Data loaders ──────────────────────────────────────────────────────────

def _load_prices(date: str) -> pd.DataFrame:
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    target = pd.Timestamp(date)
    return wide[wide.index <= target].sort_index()


def _latest_macro(date: str) -> str:
    """현재 US 매크로 국면 (2×2 Goldilocks/Reflation/Stagflation/Deflation)."""
    if not MACRO_CSV.exists():
        return "N/A"
    df = pd.read_csv(MACRO_CSV, parse_dates=["DATE"])
    target = pd.Timestamp(date)
    df = df[df["DATE"] <= target]

    def _latest_val(code):
        sub = df[df["INDICATOR_CODE"] == code]
        return float(sub.iloc[-1]["VALUE"]) if not sub.empty else np.nan

    gdp = _latest_val("US_GDP_QOQ")
    cpi = _latest_val("US_CPI_YOY")
    if np.isnan(gdp) or np.isnan(cpi):
        return "N/A"
    growing = gdp > 0
    inflating = cpi > 3.0
    if growing and not inflating:
        return "Goldilocks"
    elif growing and inflating:
        return "Reflation"
    elif not growing and inflating:
        return "Stagflation"
    return "Deflation"


def _estimate_cycle_phase(date: str, prices: pd.DataFrame) -> str:
    """경기 사이클 4단계 추정 (Early/Mid/Late/Recession).

    Heuristic mapping using:
      1. Macro regime (Goldilocks/Reflation/Stagflation/Deflation)
      2. Yield curve direction (from market_data.csv 10Y vs 2Y)
      3. VIX momentum (rising = risk-off, late/recession)
      4. SP500 momentum trend

    Rule table:
      Goldilocks + curve steepening + SP500 ↑ → Mid
      Goldilocks + curve flattening  → Late
      Reflation  + curve flat/inverted → Late
      Stagflation                    → Late/Recession
      Deflation + VIX elevated       → Recession
      Deflation + SP500 recovering   → Early
    """
    macro_regime = _latest_macro(date)

    # SP500 trend
    sp_col = SP500_CODE
    sp_trend = 0
    if sp_col in prices.columns:
        sp_px = prices[sp_col].dropna()
        if len(sp_px) >= 205:
            ma200 = float(sp_px.tail(200).mean())
            sp_trend = 1 if float(sp_px.iloc[-1]) > ma200 else -1

    # VIX level
    vix_val = np.nan
    for col in ["RK_VIX"]:
        if col in prices.columns:
            px = prices[col].dropna()
            if not px.empty:
                vix_val = float(px.iloc[-1])
                break

    # Yield curve from market_data: BD_US_10Y - BD_US_2Y (both are rates)
    curve_slope = 0  # positive = steep, negative = inverted
    if not MACRO_CSV.exists():
        macro_df_here = pd.DataFrame()
    else:
        macro_df_here = pd.read_csv(MACRO_CSV, parse_dates=["DATE"])
        target = pd.Timestamp(date)
        macro_df_here = macro_df_here[macro_df_here["DATE"] <= target]

    def _mv(code):
        sub = macro_df_here[macro_df_here["INDICATOR_CODE"] == code] if not macro_df_here.empty else pd.DataFrame()
        return float(sub.sort_values("DATE").iloc[-1]["VALUE"]) if not sub.empty else np.nan

    us_10y = _mv("US_10Y_YIELD")
    us_2y  = _mv("US_2Y_YIELD")
    if not np.isnan(us_10y) and not np.isnan(us_2y):
        curve_slope = us_10y - us_2y  # positive = normal, negative = inverted

    # Decision tree
    high_vix = (not np.isnan(vix_val) and vix_val > 28)

    if macro_regime in ("Stagflation",):
        phase = "Late" if sp_trend >= 0 else "Recession"
    elif macro_regime == "Deflation":
        if high_vix or sp_trend < 0:
            phase = "Recession"
        else:
            phase = "Early"
    elif macro_regime == "Goldilocks":
        if curve_slope > 0.3 and sp_trend > 0:
            phase = "Mid"
        elif curve_slope < 0:
            phase = "Late"
        else:
            phase = "Mid"
    elif macro_regime == "Reflation":
        phase = "Late" if curve_slope < 0.2 else "Mid"
    else:
        phase = "Mid"  # default

    return phase


def _momentum_dispersion(sectors: list) -> dict:
    """섹터 간 모멘텀 분산도 측정.

    분산도 높음 → 강한 로테이션 신호 (리더/래거 명확)
    분산도 낮음 → 시장 전반 약세/강세 (섹터 선택 효과 낮음)
    """
    composites = [s["composite"] for s in sectors
                  if s.get("composite") is not None and not np.isnan(s.get("composite", np.nan))]
    if len(composites) < 3:
        return {"std": np.nan, "range": np.nan, "signal": "데이터 부족", "color": "#94a3b8"}

    std_val   = float(np.std(composites))
    range_val = float(max(composites) - min(composites))

    if range_val > 0.6:
        signal = "강한 로테이션 — 섹터 선택 효과 극대화"
        color  = "#059669"
    elif range_val > 0.3:
        signal = "보통 로테이션 — 상위 섹터 집중 전략"
        color  = "#d97706"
    else:
        signal = "낮은 분산 — 인덱스 중립 전략 유리"
        color  = "#64748b"

    return {
        "std":    round(std_val,   3),
        "range":  round(range_val, 3),
        "signal": signal,
        "color":  color,
        "top_score":    round(max(composites), 3),
        "bottom_score": round(min(composites), 3),
    }


# ── Signal calculators ───────────────────────────────────────────────────

def _momentum(px: pd.Series, months: int) -> float:
    target = px.index[-1] - pd.DateOffset(months=months)
    past = px[px.index <= target]
    if past.empty:
        return np.nan
    return float(px.iloc[-1] / past.iloc[-1] - 1)


def _trend_score(px: pd.Series) -> int:
    """MA200/MA50 추세: +2(둘다 위), +1(MA50만), 0(중립), -1(MA50만 아래), -2(둘다 아래)."""
    if len(px) < 205:
        if len(px) >= 55:
            ma50 = float(px.tail(50).mean())
            last = float(px.iloc[-1])
            return 1 if last > ma50 else -1
        return 0
    ma200 = float(px.tail(200).mean())
    ma50 = float(px.tail(50).mean())
    last = float(px.iloc[-1])
    if last > ma200 and last > ma50:
        return 2
    elif last > ma200:
        return 1
    elif last < ma200 and last < ma50:
        return -2
    else:
        return -1


def _relative_mom(px: pd.Series, px_bench: pd.Series, months: int = 3) -> float:
    """vs 벤치마크 초과수익."""
    ret = _momentum(px, months)
    bench = _momentum(px_bench, months)
    if np.isnan(ret) or np.isnan(bench):
        return np.nan
    return ret - bench


def _composite_score(mom_1m, mom_3m, mom_6m, trend, rel_3m) -> float:
    def _s(v, w):
        return 0.0 if np.isnan(v) else np.sign(v) * w
    return round(
        _s(mom_1m, 0.15)
        + _s(mom_3m, 0.25)
        + _s(mom_6m, 0.25)
        + (trend / 2 * 0.20)    # trend 범위 -2~+2
        + _s(rel_3m, 0.15),
        3
    )


# ── Main compute ─────────────────────────────────────────────────────────

def _score_sector(code: str, prices: pd.DataFrame, bench: pd.Series) -> dict:
    if code not in prices.columns:
        return None
    px = prices[code].dropna()
    if len(px) < 30:
        return None

    mom_1m = _momentum(px, 1)
    mom_3m = _momentum(px, 3)
    mom_6m = _momentum(px, 6)
    trend = _trend_score(px)
    rel_3m = _relative_mom(px, bench, 3) if not bench.empty else np.nan
    comp = _composite_score(mom_1m, mom_3m, mom_6m, trend, rel_3m)

    last = float(px.iloc[-1])
    last_date = str(px.index[-1].date())

    return {
        "last": last,
        "last_date": last_date,
        "mom_1m": round(mom_1m * 100, 2) if not np.isnan(mom_1m) else np.nan,
        "mom_3m": round(mom_3m * 100, 2) if not np.isnan(mom_3m) else np.nan,
        "mom_6m": round(mom_6m * 100, 2) if not np.isnan(mom_6m) else np.nan,
        "trend": trend,
        "rel_3m": round(rel_3m * 100, 2) if not np.isnan(rel_3m) else np.nan,
        "composite": comp,
    }


def compute_sector_view(date: str) -> dict:
    prices = _load_prices(date)
    regime = _latest_macro(date)
    preferred = set(REGIME_SECTOR_MAP.get(regime, []))

    # Cycle phase and its preferred sectors
    cycle_phase = _estimate_cycle_phase(date, prices)
    cycle_preferred = set(CYCLE_SECTOR_MAP.get(cycle_phase, []))
    cycle_desc = CYCLE_DESCRIPTIONS.get(cycle_phase, "")

    sp500 = prices[SP500_CODE].dropna() if SP500_CODE in prices.columns else pd.Series(dtype=float)
    kospi = prices[KOSPI_CODE].dropna() if KOSPI_CODE in prices.columns else pd.Series(dtype=float)

    us_results = []
    for code, info in US_SECTORS.items():
        sig = _score_sector(code, prices, sp500)
        if sig is None:
            sig = {k: np.nan for k in ["last", "mom_1m", "mom_3m", "mom_6m", "trend", "rel_3m", "composite"]}
            sig["last_date"] = "—"
            sig["composite"] = 0.0

        us_results.append({
            "code": code,
            "name": info["name"],
            "etf": info["etf"],
            "regime_favored": code in preferred,
            "cycle_favored":  code in cycle_preferred,
            "kr_peer": info.get("kr_peer"),
            **sig,
        })

    kr_results = []
    for code, info in KR_SECTORS.items():
        sig = _score_sector(code, prices, kospi)
        if sig is None:
            sig = {k: np.nan for k in ["last", "mom_1m", "mom_3m", "mom_6m", "trend", "rel_3m", "composite"]}
            sig["last_date"] = "—"
            sig["composite"] = 0.0

        kr_results.append({
            "code": code,
            "name": info["name"],
            "etf": info["etf"],
            "regime_favored": code in preferred,
            "cycle_favored":  code in cycle_preferred,
            "us_peer": info.get("us_peer"),
            **sig,
        })

    # 순위 정렬
    us_results.sort(key=lambda x: x["composite"], reverse=True)
    kr_results.sort(key=lambda x: x["composite"], reverse=True)

    # Momentum dispersion
    dispersion = _momentum_dispersion(us_results)

    return {
        "date": date,
        "us_regime": regime,
        "cycle_phase": cycle_phase,
        "cycle_desc": cycle_desc,
        "cycle_preferred": list(cycle_preferred),
        "us_sectors": us_results,
        "kr_sectors": kr_results,
        "dispersion": dispersion,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ── HTML rendering ────────────────────────────────────────────────────────

def _chg(v, na="—") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return na
    color = "#16a34a" if v >= 0 else "#dc2626"
    return f'<span style="color:{color}">{v:+.2f}%</span>'


def _trend_label(t) -> str:
    if isinstance(t, float) and np.isnan(t):
        return "—"
    labels = {2: "↑↑ 강한 상승", 1: "↑ 상승", 0: "→ 중립", -1: "↓ 약세", -2: "↓↓ 강한 하락"}
    colors = {2: "#16a34a", 1: "#22c55e", 0: "#64748b", -1: "#f97316", -2: "#dc2626"}
    return f'<span style="color:{colors.get(int(t), "#64748b")}">{labels.get(int(t), "—")}</span>'


def _rank_badge(i: int) -> str:
    if i == 0:
        return '<span style="background:#fef3c7;color:#d97706;padding:2px 7px;border-radius:4px;font-weight:700;font-size:11px">1위</span>'
    elif i <= 2:
        return f'<span style="background:#f0f9ff;color:#0284c7;padding:2px 7px;border-radius:4px;font-size:11px">{i+1}위</span>'
    return f'<span style="color:#94a3b8;font-size:12px">{i+1}위</span>'


def _regime_preferred_badge(favored: bool) -> str:
    if favored:
        return '<span style="background:#dcfce7;color:#16a34a;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:600">★ 선호</span>'
    return ""


def _cycle_badge(favored: bool) -> str:
    if favored:
        return '<span style="background:#dbeafe;color:#2563eb;padding:2px 5px;border-radius:4px;font-size:10px;font-weight:600">●사이클</span>'
    return ""


def _sector_rows(sectors: list) -> str:
    rows = ""
    for i, s in enumerate(sectors):
        fav   = _regime_preferred_badge(s.get("regime_favored", False))
        cyc   = _cycle_badge(s.get("cycle_favored", False))
        comp  = s["composite"]
        comp_color = "#16a34a" if comp > 0.2 else ("#dc2626" if comp < -0.2 else "#64748b")
        rows += f"""
        <tr>
          <td>{_rank_badge(i)}</td>
          <td>
            <strong>{s["name"]}</strong>
            <span style="color:#94a3b8;font-size:12px;margin-left:6px">{s["etf"]}</span>
            {fav}{cyc}
          </td>
          <td style="text-align:right">{_chg(s["mom_1m"])}</td>
          <td style="text-align:right">{_chg(s["mom_3m"])}</td>
          <td style="text-align:right">{_chg(s["mom_6m"])}</td>
          <td style="text-align:center">{_trend_label(s["trend"])}</td>
          <td style="text-align:right">{_chg(s["rel_3m"])}</td>
          <td style="text-align:right;font-family:monospace;color:{comp_color};font-weight:700">{comp:+.3f}</td>
        </tr>"""
    return rows


def render_html(data: dict) -> str:
    from ._shared import nav_html, NAV_CSS
    date  = data["date"]
    regime = data["us_regime"]
    us    = data["us_sectors"]
    kr    = data["kr_sectors"]
    gen   = data["generated_at"]
    cycle = data.get("cycle_phase", "Mid")
    cycle_desc = data.get("cycle_desc", "")
    cycle_preferred = data.get("cycle_preferred", [])
    disp  = data.get("dispersion", {})
    _nav_html = nav_html(date, "sector")

    # Regime 색
    regime_colors = {
        "Goldilocks":  ("#16a34a", "#dcfce7"),
        "Reflation":   ("#d97706", "#fef3c7"),
        "Stagflation": ("#dc2626", "#fee2e2"),
        "Deflation":   ("#2563eb", "#dbeafe"),
        "N/A":         ("#64748b", "#f1f5f9"),
    }
    rfg, rbg = regime_colors.get(regime, ("#64748b", "#f1f5f9"))

    # Cycle phase 색
    cycle_colors = {
        "Early":     ("#059669", "#dcfce7"),
        "Mid":       ("#0284c7", "#dbeafe"),
        "Late":      ("#d97706", "#fef3c7"),
        "Recession": ("#dc2626", "#fee2e2"),
    }
    cfg, cbg = cycle_colors.get(cycle, ("#64748b", "#f1f5f9"))

    # Dispersion
    disp_color  = disp.get("color", "#64748b")
    disp_signal = disp.get("signal", "—")
    disp_range  = disp.get("range", np.nan)
    disp_range_str = f"{disp_range:.3f}" if not np.isnan(disp_range) else "—"
    _top_s    = disp.get("top_score", np.nan)
    _bot_s    = disp.get("bottom_score", np.nan)
    disp_top_str = f"{_top_s:+.3f}" if isinstance(_top_s, float) and not np.isnan(_top_s) else "—"
    disp_bot_str = f"{_bot_s:+.3f}" if isinstance(_bot_s, float) and not np.isnan(_bot_s) else "—"

    # Cycle preferred sector names
    cycle_pref_us   = [s for s in US_SECTORS if s in cycle_preferred]
    cycle_pref_kr   = [s for s in KR_SECTORS if s in cycle_preferred]
    cycle_chips_us  = " ".join(
        f'<span style="background:#dbeafe;color:#2563eb;padding:2px 8px;border-radius:5px;font-size:12px">{US_SECTORS[s]["etf"]}</span>'
        for s in cycle_pref_us
    ) or '<span style="color:#94a3b8">해당없음</span>'
    cycle_chips_kr  = " ".join(
        f'<span style="background:#dbeafe;color:#2563eb;padding:2px 8px;border-radius:5px;font-size:12px">{KR_SECTORS[s]["name"]}</span>'
        for s in cycle_pref_kr
    ) or '<span style="color:#94a3b8">해당없음</span>'

    # 4-phase cycle mini-diagram
    cycle_phases = ["Early", "Mid", "Late", "Recession"]
    phase_html = ""
    for ph in cycle_phases:
        fc, bc = cycle_colors.get(ph, ("#64748b", "#f1f5f9"))
        active = ph == cycle
        phase_html += f'<div style="flex:1;text-align:center;padding:8px 4px;border-radius:8px;background:{bc if active else "#f1f5f9"};border:{"2px solid " + fc if active else "1px solid #e2e8f0"};font-size:12px;font-weight:{"700" if active else "400"};color:{fc if active else "#94a3b8"}">{ph}{"✓" if active else ""}</div>'

    # US 리더/래거 top3/bottom3
    us_leaders = [s["etf"] for s in us[:3]]
    us_laggers = [s["etf"] for s in us[-3:]][::-1]

    kr_leaders = [s["name"] for s in kr[:2]]
    kr_laggers = [s["name"] for s in kr[-2:]][::-1]

    def chips(items, color, bg):
        return " ".join(
            f'<span style="background:{bg};color:{color};padding:3px 9px;border-radius:6px;font-size:12px;font-weight:600">{x}</span>'
            for x in items
        )

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sector View — {date}</title>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{ --bg:#f4f5f9; --card:#fff; --border:#e0e3ed; --text:#2d3148; --muted:#7c8298; --primary:#F58220; --navy:#043B72; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Spoqa Han Sans Neo',sans-serif; background:var(--bg); color:var(--text); }}
.header {{ margin-bottom:24px; padding-bottom:20px; border-bottom:2px solid var(--border); }}
.header h1 {{ font-size:26px; font-weight:700; }}
.header .sub {{ font-size:14px; color:var(--muted); margin-top:6px; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px 24px; margin-bottom:20px; box-shadow:0 2px 6px rgba(0,0,0,.04); }}
.card h2 {{ font-size:16px; font-weight:700; margin-bottom:14px; }}
.regime-banner {{ border-radius:10px; padding:14px 20px; margin-bottom:20px; font-size:14px; display:flex; align-items:center; gap:16px; flex-wrap:wrap; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
thead tr {{ background:#f8f9fc; }}
th {{ padding:9px 12px; font-weight:600; font-size:12px; color:var(--muted); text-align:center; border-bottom:2px solid var(--border); white-space:nowrap; }}
td {{ padding:9px 12px; border-bottom:1px solid #f0f1f7; vertical-align:middle; }}
tr:hover td {{ background:#fafbff; }}
.two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
.footer {{ text-align:center; font-size:12px; color:var(--muted); margin-top:32px; padding-top:16px; border-top:1px solid var(--border); }}
@media(max-width:900px) {{ .two-col {{ grid-template-columns:1fr; }} }}
{NAV_CSS}
</style>
</head>
<body>
{_nav_html}
<div style="max-width:1200px;margin:0 auto;padding:28px 24px 48px">
<div class="header">
  <h1>🏭 Sector Rotation View</h1>
  <div class="sub">섹터 로테이션 신호 &nbsp;|&nbsp; 기준일: {date} &nbsp;|&nbsp; 생성: {gen}</div>
</div>

<div class="regime-banner" style="background:{rbg};border:1px solid #e0e3ed">
  <strong>매크로 국면:</strong>
  <span style="background:{rfg};color:white;padding:4px 12px;border-radius:6px;font-weight:700">{regime}</span>
  &nbsp;&nbsp;
  <strong>경기 사이클:</strong>
  <span style="background:{cfg};color:white;padding:4px 12px;border-radius:6px;font-weight:700">{cycle}</span>
  <span style="color:#64748b;font-size:13px"> — {cycle_desc}</span>
</div>

<!-- 경기 사이클 × 섹터 카드 -->
<div class="card">
  <h2>🔄 경기 사이클 단계 분석</h2>
  <div style="display:flex;gap:8px;margin-bottom:16px">{phase_html}</div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px">
    <div style="background:#f8fafc;border-radius:10px;padding:14px;border-top:3px solid {cfg}">
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">현재 사이클 단계</div>
      <div style="font-size:20px;font-weight:800;color:{cfg}">{cycle}</div>
      <div style="font-size:12px;color:#64748b;margin-top:4px">{cycle_desc}</div>
    </div>
    <div style="background:#f8fafc;border-radius:10px;padding:14px">
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">US 사이클 선호 섹터 (●사이클)</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">{cycle_chips_us}</div>
    </div>
    <div style="background:#f8fafc;border-radius:10px;padding:14px">
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">KR 사이클 선호 섹터 (●사이클)</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">{cycle_chips_kr}</div>
    </div>
  </div>
  <!-- 섹터 모멘텀 분산도 -->
  <div style="margin-top:16px;background:#f8fafc;border-radius:10px;padding:14px;display:flex;align-items:center;gap:24px;flex-wrap:wrap">
    <div>
      <div style="font-size:11px;color:#94a3b8">모멘텀 분산도 (Range)</div>
      <div style="font-size:22px;font-weight:800;color:{disp_color}">{disp_range_str}</div>
    </div>
    <div style="flex:1">
      <div style="font-size:13px;font-weight:600;color:{disp_color}">{disp_signal}</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:2px">Top − Bottom 복합점수 차이. 0.6↑ = 강한 로테이션, 0.3↓ = 인덱스 중립</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:11px;color:#94a3b8">Top 점수</div>
      <div style="font-size:15px;font-weight:700;color:#059669">{disp_top_str}</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:4px">Bottom 점수</div>
      <div style="font-size:15px;font-weight:700;color:#dc2626">{disp_bot_str}</div>
    </div>
  </div>
</div>

<div class="card">
  <h2>📊 섹터 요약 (리더 vs 래거)</h2>
  <div style="display:flex;gap:40px;flex-wrap:wrap">
    <div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:6px">🇺🇸 US 섹터 리더 (모멘텀 Top3)</div>
      <div class="chips">{chips(us_leaders, "#16a34a", "#dcfce7")}</div>
    </div>
    <div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:6px">🇺🇸 US 섹터 래거 (모멘텀 Bottom3)</div>
      <div class="chips">{chips(us_laggers, "#dc2626", "#fee2e2")}</div>
    </div>
    <div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:6px">🇰🇷 KR 섹터 리더</div>
      <div class="chips">{chips(kr_leaders, "#16a34a", "#dcfce7")}</div>
    </div>
    <div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:6px">🇰🇷 KR 섹터 래거</div>
      <div class="chips">{chips(kr_laggers, "#dc2626", "#fee2e2")}</div>
    </div>
  </div>
</div>

<div class="two-col">
  <div class="card">
    <h2>🇺🇸 US 섹터 로테이션 (vs S&amp;P500)</h2>
    <table>
      <thead>
        <tr>
          <th>순위</th>
          <th style="text-align:left">섹터</th>
          <th>1M</th>
          <th>3M</th>
          <th>6M</th>
          <th>추세</th>
          <th>vs SPY</th>
          <th>점수</th>
        </tr>
      </thead>
      <tbody>{_sector_rows(us)}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>🇰🇷 KR 섹터 로테이션 (vs KOSPI)</h2>
    <table>
      <thead>
        <tr>
          <th>순위</th>
          <th style="text-align:left">섹터</th>
          <th>1M</th>
          <th>3M</th>
          <th>6M</th>
          <th>추세</th>
          <th>vs KOSPI</th>
          <th>점수</th>
        </tr>
      </thead>
      <tbody>{_sector_rows(kr)}</tbody>
    </table>
    <div style="margin-top:12px;font-size:12px;color:var(--muted)">
      ⚠️ KR 섹터 ETF 데이터 미수집 시 점수 0. 데이터 수집 후 재실행 필요.
    </div>
  </div>
</div>

<div class="card" style="font-size:13px;color:var(--muted)">
  <strong>해석 안내</strong> &nbsp;|&nbsp;
  복합점수 = 1M(15%) + 3M(25%) + 6M(25%) + MA추세(20%) + vs벤치(15%)
  &nbsp;|&nbsp; ★ 선호 = 현재 매크로 국면({regime}) 친화 섹터
</div>

<div class="footer">Sector View &nbsp;·&nbsp; 미래에셋생명 변액보험 운용 참고 &nbsp;·&nbsp; 본 자료는 투자 권유가 아닙니다</div>
</div>
</body>
</html>"""
    return html


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    data = compute_sector_view(args.date)

    if args.html:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{args.date}.html"
        out_path.write_text(render_html(data), encoding="utf-8")
        print(f"Saved: {out_path}")
    else:
        print(f"US 매크로 국면: {data['us_regime']}")
        print("\n🇺🇸 US 섹터 (순위순):")
        for s in data["us_sectors"]:
            fav = " ★" if s["regime_favored"] else ""
            print(f"  {s['name']:22s} {s['etf']:5s} comp={s['composite']:+.3f}  3M={s['mom_3m']:+.1f}%{fav}" if not np.isnan(s.get("mom_3m", np.nan)) else f"  {s['name']:22s} {s['etf']:5s} comp={s['composite']:+.3f}{fav}")
        print("\n🇰🇷 KR 섹터 (순위순):")
        for s in data["kr_sectors"]:
            fav = " ★" if s["regime_favored"] else ""
            print(f"  {s['name']:12s} comp={s['composite']:+.3f}{fav}")


if __name__ == "__main__":
    main()
