"""Macro economic view — Real macro indicators analysis.

Analyzes macro indicators (GDP, inflation, employment, policy, credit, liquidity)
from history/macro_indicators.csv.

Enhancements:
  A1. Z-score / percentile bracket + direction arrow per indicator row
  A2. US & KR 2×2 regime header cards (Goldilocks / Reflation / Stagflation / Deflation)
  A3. FED implied rate (2Y − Fed Funds) in policy section
  A4. Liquidity section (real rate, M2 YoY, Fed balance sheet YoY)

NO asset allocation. For price-based signals, see portfolio.view.price_view.

Generates standalone HTML report to output/view/macro/.

Usage:
    python -m portfolio.view.macro_view --date 2026-04-09 --html
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "macro"
HISTORY_CSV = ROOT / "history" / "macro_indicators.csv"


def load_macro_data(csv_path: Path = HISTORY_CSV) -> pd.DataFrame:
    """Load macro indicators CSV."""
    if not csv_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv_path, parse_dates=["DATE"])
    return df.sort_values("DATE")


# ── Helpers ───────────────────────────────────────────────────────────

def _percentile_label(value: float, p25: float, p75: float) -> str:
    """Return High/Mid/Low bracket label."""
    if np.isnan(value) or np.isnan(p25) or np.isnan(p75):
        return "—"
    if value >= p75:
        return "High"
    elif value <= p25:
        return "Low"
    else:
        return "Mid"


def _direction_arrow(latest: float, prev: float) -> str:
    """Return direction arrow ↑ / → / ↓ based on relative change."""
    if np.isnan(latest) or np.isnan(prev):
        return "→"
    denom = abs(prev) if abs(prev) > 0.001 else 0.001
    change = (latest - prev) / denom
    if change > 0.05:
        return "↑"
    elif change < -0.05:
        return "↓"
    else:
        return "→"


def _macro_regime(gdp_qoq: float | None, cpi_yoy_latest: float | None,
                  cpi_yoy_prev: float | None,
                  indpro_mom: float | None = None,
                  consumer_sent: float | None = None) -> dict:
    """Determine 2×2 macro regime with probability estimates.

    Args:
        gdp_qoq: GDP 분기 성장률 (%)
        cpi_yoy_latest: 최근 CPI YoY (%)
        cpi_yoy_prev: 3개월 전 CPI YoY (%) — 인플레이션 방향 판단
        indpro_mom: 산업생산 MoM 변화율 — Nowcasting 보조
        consumer_sent: U Michigan 소비자 심리 — 선행 지표

    Returns:
        dict with label, color, desc, probabilities (4-cell)
    """
    # ── 성장 신호 ──────────────────────────────────────────
    growth_signals = []

    if gdp_qoq is not None and not np.isnan(gdp_qoq):
        growth_signals.append(1 if gdp_qoq > 0 else -1)

    if indpro_mom is not None and not np.isnan(indpro_mom):
        # 산업생산 MoM: 0 이상이면 성장, 음수면 수축
        growth_signals.append(1 if indpro_mom > 0 else -1)

    if consumer_sent is not None and not np.isnan(consumer_sent):
        # 소비자 심리 75 이상 = 긍정, 이하 = 부정
        growth_signals.append(1 if consumer_sent >= 75 else -1)

    if growth_signals:
        growth_score = sum(growth_signals) / len(growth_signals)
        growth_pos = growth_score > 0
        growth_conf = abs(growth_score)  # 0~1: 신호 일치도
    else:
        growth_pos = False
        growth_conf = 0.5

    # ── 인플레이션 방향 ─────────────────────────────────────
    if (cpi_yoy_latest is not None and cpi_yoy_prev is not None
            and not np.isnan(cpi_yoy_latest) and not np.isnan(cpi_yoy_prev)):
        inflation_rising = cpi_yoy_latest > cpi_yoy_prev
        infl_conf = min(abs(cpi_yoy_latest - cpi_yoy_prev) / 0.5, 1.0)
    else:
        inflation_rising = None
        infl_conf = 0.5

    # ── 레짐 결정 ───────────────────────────────────────────
    if growth_pos and inflation_rising is False:
        label = "Goldilocks"
        color = "#0d9b6a"
        desc  = "성장 ↑  물가 ↓"
    elif growth_pos and inflation_rising:
        label = "Reflation"
        color = "#f59e0b"
        desc  = "성장 ↑  물가 ↑"
    elif not growth_pos and inflation_rising:
        label = "Stagflation"
        color = "#d9304f"
        desc  = "성장 ↓  물가 ↑"
    elif not growth_pos and inflation_rising is False:
        label = "Deflation"
        color = "#64748b"
        desc  = "성장 ↓  물가 ↓"
    else:
        label = "Unknown"
        color = "#94a3b8"
        desc  = "데이터 부족"

    # ── 4-Cell 확률 추정 (퍼지 로직) ────────────────────────
    # growth_conf, infl_conf ∈ [0,1]
    # dominant에 (0.4 + conf*0.4) 배분, 나머지 3셀에 균등 배분
    dominant_prob = round(0.40 + growth_conf * 0.20 + infl_conf * 0.20, 2)
    dominant_prob = min(dominant_prob, 0.85)
    others = round((1.0 - dominant_prob) / 3, 2)

    probs = {"Goldilocks": others, "Reflation": others,
             "Stagflation": others, "Deflation": others}
    if label in probs:
        probs[label] = dominant_prob

    return {
        "label": label,
        "color": color,
        "desc": desc,
        "probabilities": probs,
    }


def _nowcast_gdp(df_hist: pd.DataFrame, target: pd.Timestamp) -> dict | None:
    """간이 Nowcasting: 월간 지표로 GDP 성장률 예측.

    산업생산(INDPRO) MoM + 소비자심리(UMCSENT) 변화를 이용한
    Bridge Equation 근사치.
    """
    result = {"available": False}

    indpro_hist = df_hist[df_hist["INDICATOR_CODE"] == "MACRO_US_INDPRO"]["VALUE"].dropna()
    csent_hist  = df_hist[df_hist["INDICATOR_CODE"] == "MACRO_US_CONSUMER_SENT"]["VALUE"].dropna()
    gdp_hist    = df_hist[df_hist["INDICATOR_CODE"] == "US_GDP_YOY"]["VALUE"].dropna()

    if len(indpro_hist) < 3:
        return result

    # 산업생산 최근 3개월 평균 MoM
    indpro_mom3 = float(indpro_hist.pct_change().tail(3).mean()) * 100

    # 소비자심리 방향
    csent_dir = None
    if len(csent_hist) >= 2:
        csent_dir = "상승" if float(csent_hist.iloc[-1]) > float(csent_hist.iloc[-2]) else "하락"

    # 간이 GDP Nowcast: indpro MoM 3개월 평균 * 4 (연환산 근사)
    nowcast_gdp = round(indpro_mom3 * 4, 2)

    result = {
        "available": True,
        "nowcast_gdp": nowcast_gdp,
        "indpro_mom3": round(indpro_mom3, 3),
        "csent_dir": csent_dir,
        "interpretation": (
            f"산업생산 3M MoM 평균 {indpro_mom3:+.2f}% → 연환산 GDP 근사: {nowcast_gdp:+.1f}%"
            + (f", 소비자심리 {csent_dir}" if csent_dir else "")
        ),
    }
    return result


# ── Core computation ──────────────────────────────────────────────────

def compute_macro_view(date: str, csv_path: Path = HISTORY_CSV) -> dict:
    """Compute macro view as of a given date."""
    df = load_macro_data(csv_path)
    if df.empty:
        return {"error": "No macro data available"}

    target = pd.Timestamp(date)
    df_hist = df[df["DATE"] <= target].copy()

    if df_hist.empty:
        return {"error": f"No data available before {date}"}

    # Latest value per indicator (as-of date)
    latest = df_hist.groupby("INDICATOR_CODE").last().reset_index()

    def _get_latest(code: str) -> float | None:
        row = latest[latest["INDICATOR_CODE"] == code]
        if row.empty:
            return None
        v = row.iloc[0]["VALUE"]
        return float(v) if not np.isnan(v) else None

    def format_group(group_df: pd.DataFrame) -> list:
        """Format indicator group with percentile and direction enrichment."""
        if group_df.empty:
            return []
        result = []
        for _, row in group_df.iterrows():
            code = row["INDICATOR_CODE"]
            val = float(row["VALUE"]) if not np.isnan(row["VALUE"]) else None

            # Full history for this indicator (up to target date)
            hist = df_hist[df_hist["INDICATOR_CODE"] == code]["VALUE"].dropna()

            # Percentile brackets
            p25 = float(hist.quantile(0.25)) if len(hist) >= 4 else np.nan
            p75 = float(hist.quantile(0.75)) if len(hist) >= 4 else np.nan
            pct_label = _percentile_label(val if val is not None else np.nan, p25, p75)

            # 3-month-ago value (~3 records back for monthly, 1 for quarterly)
            lookback = 3 if len(hist) >= 4 else 1
            prev_val = float(hist.iloc[-lookback - 1]) if len(hist) > lookback else np.nan
            direction = _direction_arrow(val if val is not None else np.nan, prev_val)

            result.append({
                "code": code,
                "value": val,
                "unit": row["UNIT"],
                "date": row["DATE"].strftime("%Y-%m-%d"),
                "category": row["CATEGORY"],
                "percentile": pct_label,
                "direction": direction,
            })
        return result

    # ── Group by category / region ────────────────────────────────
    us_growth     = latest[(latest["CATEGORY"] == "growth")     & (latest["REGION"] == "US")]
    us_inflation  = latest[(latest["CATEGORY"] == "inflation")  & (latest["REGION"] == "US")]
    us_employment = latest[(latest["CATEGORY"] == "employment") & (latest["REGION"] == "US")]
    us_sentiment  = latest[(latest["CATEGORY"].isin(["sentiment", "activity"])) & (latest["REGION"] == "US")]
    us_policy     = latest[(latest["CATEGORY"] == "policy")     & (latest["REGION"] == "US")]
    us_credit     = latest[(latest["CATEGORY"].isin(["credit"])) & (latest["REGION"] == "US")]
    us_liquidity  = latest[(latest["CATEGORY"] == "liquidity")  & (latest["REGION"] == "US")]

    kr_growth     = latest[(latest["CATEGORY"] == "growth")     & (latest["REGION"] == "KR")]
    kr_inflation  = latest[(latest["CATEGORY"] == "inflation")  & (latest["REGION"] == "KR")]
    kr_employment = latest[(latest["CATEGORY"] == "employment") & (latest["REGION"] == "KR")]
    kr_sentiment  = latest[(latest["CATEGORY"] == "sentiment")  & (latest["REGION"] == "KR")]
    kr_policy     = latest[(latest["CATEGORY"] == "policy")     & (latest["REGION"] == "KR")]

    global_indicators = latest[latest["REGION"] == "GLOBAL"]

    # ── A2. Regime computation ────────────────────────────────────
    # US regime: GDP QoQ > 0? + CPI YoY direction + Nowcasting 보조
    us_gdp_qoq = _get_latest("US_GDP_QOQ")
    us_cpi_latest = _get_latest("US_CPI_YOY")
    us_cpi_hist = df_hist[df_hist["INDICATOR_CODE"] == "US_CPI_YOY"]["VALUE"].dropna()
    us_cpi_prev = float(us_cpi_hist.iloc[-4]) if len(us_cpi_hist) >= 4 else None

    # 확장 지표로 Nowcasting 보조
    us_indpro = _get_latest("MACRO_US_INDPRO")
    us_csent  = _get_latest("MACRO_US_CONSUMER_SENT")

    us_regime = _macro_regime(us_gdp_qoq, us_cpi_latest, us_cpi_prev, us_indpro, us_csent)

    # KR regime: GDP QoQ > 0? + CPI YoY direction
    kr_gdp_qoq = _get_latest("KR_GDP_QOQ")
    kr_cpi_latest = _get_latest("KR_CPI_YOY")
    kr_cpi_hist = df_hist[df_hist["INDICATOR_CODE"] == "KR_CPI_YOY"]["VALUE"].dropna()
    kr_cpi_prev = float(kr_cpi_hist.iloc[-4]) if len(kr_cpi_hist) >= 4 else None
    kr_regime = _macro_regime(kr_gdp_qoq, kr_cpi_latest, kr_cpi_prev)

    # Divergence flag
    regime_divergence = us_regime["label"] != kr_regime["label"]

    # ── Nowcasting ────────────────────────────────────────────────
    nowcast = _nowcast_gdp(df_hist, target)

    # ── A3. FED implied rate ──────────────────────────────────────
    fed_policy_list = format_group(us_policy)
    us_2y = _get_latest("US_2Y_YIELD")
    us_fed = _get_latest("US_FED_RATE")
    if us_2y is not None and us_fed is not None:
        implied = us_2y - us_fed
        # Add synthetic indicator to policy list
        fed_policy_list.append({
            "code": "FED_IMPLIED_DELTA",
            "value": round(implied, 2),
            "unit": "%",
            "date": date,
            "category": "policy",
            "percentile": "—",
            "direction": "↑" if implied > 0.25 else ("↓" if implied < -0.25 else "→"),
        })

    # ── A4. Liquidity: real rate (computed) ───────────────────────
    liquidity_list = format_group(us_liquidity)
    us_10y = _get_latest("US_10Y_YIELD")
    us_cpi_val = _get_latest("US_CPI_YOY")
    if us_10y is not None and us_cpi_val is not None:
        real_rate = us_10y - us_cpi_val
        # Compute direction: compare real rate now vs ~3 months ago
        us_10y_hist = df_hist[df_hist["INDICATOR_CODE"] == "US_10Y_YIELD"]["VALUE"].dropna()
        cpi_hist_align = df_hist[df_hist["INDICATOR_CODE"] == "US_CPI_YOY"]["VALUE"].dropna()
        prev_real = np.nan
        if len(us_10y_hist) >= 4 and len(cpi_hist_align) >= 4:
            prev_real = float(us_10y_hist.iloc[-4]) - float(cpi_hist_align.iloc[-4])

        liquidity_list.insert(0, {
            "code": "US_REAL_RATE",
            "value": round(real_rate, 2),
            "unit": "%",
            "date": date,
            "category": "liquidity",
            "percentile": "—",
            "direction": _direction_arrow(real_rate, prev_real),
        })

    return {
        "date": date,
        "us_regime": us_regime,
        "kr_regime": kr_regime,
        "regime_divergence": regime_divergence,
        "nowcast": nowcast,
        "us": {
            "growth":     format_group(us_growth),
            "inflation":  format_group(us_inflation),
            "employment": format_group(us_employment),
            "sentiment":  format_group(us_sentiment),
            "policy":     fed_policy_list,
            "credit":     format_group(us_credit),
            "liquidity":  liquidity_list,
        },
        "kr": {
            "growth":     format_group(kr_growth),
            "inflation":  format_group(kr_inflation),
            "employment": format_group(kr_employment),
            "sentiment":  format_group(kr_sentiment),
            "policy":     format_group(kr_policy),
        },
        "global": format_group(global_indicators),
    }


# ── HTML Generation ───────────────────────────────────────────────────

def _indicator_row(ind: dict) -> str:
    """Format single indicator row with value, percentile, direction, date."""
    val = ind["value"]
    if val is None:
        val_str = "—"
    elif ind["unit"] == "%":
        val_str = f"{val:.2f}%"
    elif ind["unit"] == "bp":
        val_str = f"{val:.0f}bp"
    elif ind["unit"] == "k":
        val_str = f"{val:.0f}k"
    else:
        val_str = f"{val:.2f}"

    pct = ind.get("percentile", "—")
    direction = ind.get("direction", "→")

    pct_class = ""
    if pct == "High":
        pct_class = "pct-high"
    elif pct == "Low":
        pct_class = "pct-low"

    dir_class = ""
    if direction == "↑":
        dir_class = "dir-up"
    elif direction == "↓":
        dir_class = "dir-down"

    return f"""
    <tr>
      <td class="mono">{ind['code']}</td>
      <td class="right mono value-cell">{val_str}</td>
      <td class="right"><span class="pct-badge {pct_class}">{pct}</span></td>
      <td class="right {dir_class}">{direction}</td>
      <td class="right muted">{ind['date']}</td>
    </tr>
    """


def _section_html(title: str, indicators: list) -> str:
    """Format section HTML with enriched columns."""
    if not indicators:
        return f"""
        <div class="section">
          <h3>{title}</h3>
          <p class="muted">No data available</p>
        </div>
        """

    rows = "".join([_indicator_row(ind) for ind in indicators])
    return f"""
    <div class="section">
      <h3>{title}</h3>
      <table class="indicator-table">
        <thead>
          <tr>
            <th style="text-align:left">Indicator</th>
            <th style="text-align:right">Value</th>
            <th style="text-align:right">vs Avg</th>
            <th style="text-align:right">Dir</th>
            <th style="text-align:right">As of</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>
    """


def _regime_prob_bar(probs: dict, current_label: str) -> str:
    """4-Cell 확률 막대 렌더링."""
    colors = {
        "Goldilocks":  "#0d9b6a",
        "Reflation":   "#f59e0b",
        "Stagflation": "#d9304f",
        "Deflation":   "#64748b",
    }
    bars = ""
    for label, prob in probs.items():
        color = colors.get(label, "#94a3b8")
        is_current = label == current_label
        border = f"border:2px solid {color}" if is_current else "border:1px solid #e0e3ed"
        fw = "font-weight:700" if is_current else ""
        bars += f"""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
          <span style="font-size:11px;{fw};min-width:88px;color:#4b5563">{label}</span>
          <div style="flex:1;background:#f0f1f6;border-radius:4px;height:10px;overflow:hidden">
            <div style="width:{prob*100:.0f}%;background:{color};height:100%;border-radius:4px"></div>
          </div>
          <span style="font-size:11px;{fw};color:{color};min-width:34px;text-align:right">{prob*100:.0f}%</span>
          {'<span style="font-size:10px;color:#6b7280">◀ 현재</span>' if is_current else ''}
        </div>"""
    return bars


def _regime_cards_html(us_regime: dict, kr_regime: dict, divergence: bool,
                       nowcast: dict | None = None) -> str:
    """Render US + KR regime cards with probability bars and Nowcasting."""
    divergence_banner = ""
    if divergence:
        divergence_banner = """
        <div class="regime-divergence">
          ⚠️ US/KR 국면 불일치 — 분산 투자 기회 검토
        </div>
        """

    def _card(flag: str, country: str, regime: dict) -> str:
        probs = regime.get("probabilities", {})
        prob_html = ""
        if probs:
            prob_html = f"""
            <div style="margin-top:10px;padding-top:10px;border-top:1px solid #e0e3ed">
              <div style="font-size:10px;font-weight:700;color:#94a3b8;
                          text-transform:uppercase;margin-bottom:6px">레짐 확률 추정</div>
              {_regime_prob_bar(probs, regime['label'])}
            </div>"""
        return f"""
        <div class="regime-card" style="border-left:4px solid {regime['color']}">
          <div class="regime-flag">{flag} {country}</div>
          <div class="regime-label" style="color:{regime['color']}">{regime['label']}</div>
          <div class="regime-desc">{regime['desc']}</div>
          {prob_html}
        </div>
        """

    # Nowcasting 카드
    nowcast_html = ""
    if nowcast and nowcast.get("available"):
        nc_gdp = nowcast.get("nowcast_gdp", 0)
        nc_interp = nowcast.get("interpretation", "")
        nc_color = "#0d9b6a" if nc_gdp > 0 else "#d9304f"
        nowcast_html = f"""
        <div class="regime-card" style="border-left:4px solid {nc_color}">
          <div class="regime-flag">📡 Nowcasting</div>
          <div class="regime-label" style="color:{nc_color}">GDP {nc_gdp:+.1f}%</div>
          <div class="regime-desc" style="font-size:12px;line-height:1.6">{nc_interp}</div>
        </div>
        """

    return f"""
    <div class="regime-header">
      <div class="regime-cards">
        {_card("🇺🇸", "United States", us_regime)}
        {_card("🇰🇷", "Korea", kr_regime)}
        {nowcast_html}
      </div>
      {divergence_banner}
    </div>
    """


def generate_macro_html(view: dict) -> str:
    """Generate macro view HTML."""
    if "error" in view:
        return f"<html><body><h1>Error</h1><p>{view['error']}</p></body></html>"

    report_date = view["date"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    from ._shared import nav_html, NAV_CSS
    _nav = nav_html(report_date, "macro")

    us = view["us"]
    kr = view["kr"]
    global_ind = view["global"]
    us_regime = view.get("us_regime", {"label": "—", "color": "#94a3b8", "desc": ""})
    kr_regime = view.get("kr_regime", {"label": "—", "color": "#94a3b8", "desc": ""})
    divergence = view.get("regime_divergence", False)

    nowcast = view.get("nowcast")

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Macro Economic View | {report_date}</title>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --border:#e0e3ed; --text:#2d3148; --muted:#7c8298;
  --primary:#F58220; --navy:#043B72; --up:#059669; --down:#dc2626;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Spoqa Han Sans Neo',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.65;padding:0;max-width:none;margin:0}}
.mono{{font-family:'JetBrains Mono',monospace}}
.muted{{color:var(--muted)}}
.right{{text-align:right}}

.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:24px;padding-bottom:20px;border-bottom:2px solid var(--border)}}
.header h1{{font-size:26px;font-weight:700;color:#1a1d2e}}
.header .meta{{font-size:13px;color:var(--muted);margin-top:4px}}
.header .gen{{font-size:12px;color:var(--muted);text-align:right}}

/* Regime header */
.regime-header{{margin-bottom:28px}}
.regime-cards{{display:flex;gap:16px;flex-wrap:wrap}}
.regime-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 20px;flex:1;min-width:220px;box-shadow:0 1px 4px rgba(0,0,0,.04)}}
.regime-flag{{font-size:13px;color:var(--muted);margin-bottom:4px}}
.regime-label{{font-size:22px;font-weight:700;margin-bottom:4px}}
.regime-desc{{font-size:13px;color:var(--muted)}}
.regime-divergence{{margin-top:12px;padding:10px 16px;background:#fff8e6;border:1px solid #f59e0b;border-radius:8px;font-size:13px;color:#92400e}}

.region-title{{font-size:20px;font-weight:700;color:#1a1d2e;margin:28px 0 16px;padding-bottom:8px;border-bottom:2px solid var(--primary)}}

.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px;margin-bottom:28px}}

.section{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.04)}}
.section h3{{font-size:15px;font-weight:600;color:#1a1d2e;margin-bottom:14px}}

.indicator-table{{width:100%;border-collapse:collapse;font-size:13px}}
.indicator-table thead tr{{background:#f8fafc;border-bottom:1px solid var(--border)}}
.indicator-table th{{padding:8px 10px;font-size:12px;color:var(--muted);font-weight:600}}
.indicator-table td{{padding:8px 10px;border-bottom:1px solid #f1f5f9}}
.indicator-table tbody tr:hover{{background:#f8fafc}}
.value-cell{{font-weight:600;color:#1a1d2e}}

/* Percentile badges */
.pct-badge{{font-size:11px;padding:2px 6px;border-radius:4px;background:#f1f5f9;color:var(--muted)}}
.pct-high{{background:#dcfce7;color:#166534}}
.pct-low{{background:#fee2e2;color:#991b1b}}

/* Direction arrows */
.dir-up{{color:var(--up);font-weight:700}}
.dir-down{{color:var(--down);font-weight:700}}

.footer{{text-align:center;font-size:11px;color:#94a3b8;padding:20px 0 4px;margin-top:32px;border-top:1px solid var(--border)}}
.back-link{{display:inline-block;margin-bottom:20px;font-size:13px;color:var(--primary);text-decoration:none}}
.back-link:hover{{text-decoration:underline}}

@media(max-width:768px){{
  .grid{{grid-template-columns:1fr}}
  .regime-cards{{flex-direction:column}}
}}
{NAV_CSS}
</style>
</head>
<body>
{_nav}
<div style="max-width:1400px;margin:0 auto;padding:28px 24px 48px">
<div class="header">
  <div>
    <h1>Macro Economic View</h1>
    <div class="meta">Real macro indicators | GDP · Inflation · Employment · Policy · Credit · Liquidity</div>
  </div>
  <div class="gen">
    <div style="font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:4px">As of {report_date}</div>
    <div>Generated: {now}</div>
  </div>
</div>

{_regime_cards_html(us_regime, kr_regime, divergence, nowcast)}

<div class="region-title">🇺🇸 United States</div>
<div class="grid">
  {_section_html("Growth", us["growth"])}
  {_section_html("Inflation", us["inflation"])}
  {_section_html("Employment", us["employment"])}
  {_section_html("Sentiment", us["sentiment"])}
  {_section_html("Policy & Rates", us["policy"])}
  {_section_html("Credit Spreads", us["credit"])}
  {_section_html("Liquidity", us["liquidity"])}
</div>

<div class="region-title">🇰🇷 Korea</div>
<div class="grid">
  {_section_html("Growth", kr["growth"])}
  {_section_html("Inflation", kr["inflation"])}
  {_section_html("Employment", kr["employment"])}
  {_section_html("Sentiment", kr["sentiment"])}
  {_section_html("Policy", kr["policy"])}
</div>

<div class="region-title">🌍 Global</div>
<div class="grid">
  {_section_html("Risk & FX", global_ind)}
</div>

<div class="footer">Macro Economic View | GDP · Inflation · Employment · Policy · Credit · Liquidity | View Agent</div>
</div>
</body>
</html>'''


def generate_report(date: str, csv_path: Path = HISTORY_CSV) -> str:
    """Generate macro view HTML report."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    view = compute_macro_view(date, csv_path)
    html = generate_macro_html(view)

    out_path = OUTPUT_DIR / f"{date}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Macro economic view")
    parser.add_argument("--date", required=True, help="View date (YYYY-MM-DD)")
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    args = parser.parse_args()

    if args.html:
        path = generate_report(args.date)
        print(f"HTML report: {path}")
        return

    view = compute_macro_view(args.date)

    if "error" in view:
        print(f"Error: {view['error']}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Macro Economic View as of {view['date']}")
    print(f"{'='*60}")
    print(f"  🇺🇸 US Regime : {view['us_regime']['label']} ({view['us_regime']['desc']})")
    print(f"  🇰🇷 KR Regime : {view['kr_regime']['label']} ({view['kr_regime']['desc']})")
    if view.get("regime_divergence"):
        print("  ⚠️  US/KR 국면 불일치")

    print(f"\n🇺🇸 United States")
    for category, indicators in view["us"].items():
        if indicators:
            print(f"\n  {category.upper()}:")
            for ind in indicators:
                val = ind["value"]
                val_str = f"{val:.2f}" if val is not None else "—"
                print(f"    {ind['code']:<25s} {val_str:>10s} {ind['unit']:<5s} "
                      f"[{ind['percentile']}] {ind['direction']}")

    print(f"\n🇰🇷 Korea")
    for category, indicators in view["kr"].items():
        if indicators:
            print(f"\n  {category.upper()}:")
            for ind in indicators:
                val = ind["value"]
                val_str = f"{val:.2f}" if val is not None else "—"
                print(f"    {ind['code']:<25s} {val_str:>10s} {ind['unit']:<5s} "
                      f"[{ind['percentile']}] {ind['direction']}")

    if view["global"]:
        print(f"\n🌍 Global")
        for ind in view["global"]:
            val = ind["value"]
            val_str = f"{val:.2f}" if val is not None else "—"
            print(f"  {ind['code']:<25s} {val_str:>10s} {ind['unit']:<5s} "
                  f"[{ind['percentile']}] {ind['direction']}")

    print()


if __name__ == "__main__":
    main()
