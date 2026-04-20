"""
KR vs US Sector Rotation — Multi-Agent Signal Model
Monthly rebalancing. Five parallel agents → weighted ensemble → KR/US/Neutral signal.

Agents (price-based):
  1. MomentumAgent    (30%) — 1M/3M/6M sector ETF return scores
  2. BreadthAgent     (15%) — % sectors above MA200
  3. RelStrengthAgent (15%) — KOSPI vs S&P500 relative strength (1M/3M/6M)
Agents (fundamental/risk):
  4. RiskAgent        (15%) — VIX regime, HY spread trend, yield curve
  5. MacroRegimeAgent (25%) — GDP/CPI/policy rate differential (KR vs US)

Signal: KR_score - US_score → KR / Neutral / US
Benchmarks: 50/50 blend, KOSPI-only, S&P500-only
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "history" / "market_data.csv"
OUTPUT_DIR = ROOT / "output" / "portfolio" / "strategy"

# Sector ETF pools used for momentum & breadth
US_SECTORS = [
    "SC_US_TECH", "SC_US_FIN", "SC_US_HEALTH", "SC_US_INDU",
    "SC_US_ENERGY", "SC_US_DISCR", "SC_US_STAPLES", "SC_US_MATL",
    "SC_US_UTIL", "SC_US_COMM", "SC_US_REIT",
]
KR_SECTORS = [
    "IX_KR_IT", "IX_KR_FIN", "IX_KR_HEALTH", "IX_KR_INDU",
    "IX_KR_ENERGY", "IX_KR_DISCR", "IX_KR_STAPLES", "IX_KR_HEAVY",
    "IX_KR_CONSTR", "IX_KR_STEEL", "IX_KR_COMM",
]

BACKTEST_START = "2010-01-01"   # EQ_KOSPI/EQ_SP500/FX_USDKRW all available from 2010
AGENT_WEIGHTS = {
    "momentum": 0.30, "breadth": 0.15, "rel_strength": 0.15,
    "risk": 0.15, "macro": 0.25,
}
COST_BPS = 30  # one-way transaction cost (bps) applied on signal change
THRESHOLD = 0.08   # KR_score - US_score > +threshold → KR; < -threshold → US

MACRO_CSV = ROOT / "history" / "macro_indicators.csv"


# ──────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────

def load_pivot(start: str = BACKTEST_START) -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["DATE"])
    df = df[df["DATE"] >= start]
    pivot = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE", aggfunc="last")
    pivot.index.name = "date"
    pivot = pivot.sort_index()

    if "EQ_KOSPI" in pivot.columns and "FX_USDKRW" in pivot.columns:
        fx = pivot["FX_USDKRW"].ffill()
        pivot["EQ_KOSPI_USD"] = pivot["EQ_KOSPI"] / fx

    return pivot


def load_macro(start: str = BACKTEST_START) -> pd.DataFrame:
    if not MACRO_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(MACRO_CSV, parse_dates=["DATE"])
    df = df[df["DATE"] >= start]
    pivot = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="VALUE", aggfunc="last")
    pivot.index.name = "date"
    pivot = pivot.sort_index().ffill()
    return pivot


def month_ends(pivot: pd.DataFrame) -> pd.DatetimeIndex:
    return pivot.resample("BME").last().index


# ──────────────────────────────────────────────
# Agent 1: Momentum
# ──────────────────────────────────────────────

def momentum_score(px: pd.Series, lookback_days: int) -> float:
    """Return over lookback window, or NaN if insufficient data."""
    if len(px) < lookback_days + 1:
        return float("nan")
    end = px.iloc[-1]
    start = px.iloc[-(lookback_days + 1)]
    if start == 0 or pd.isna(start) or pd.isna(end):
        return float("nan")
    return end / start - 1.0


def momentum_agent(pivot: pd.DataFrame, sectors: list[str], as_of: pd.Timestamp) -> float:
    """
    For each sector ETF available as_of, compute (1M+3M+6M)/3 momentum.
    Return average across sectors (NaN sectors excluded). Normalised to [-1,1].
    """
    data = pivot.loc[:as_of]
    scores = []
    for code in sectors:
        if code not in data.columns:
            continue
        px = data[code].dropna()
        if len(px) < 2:
            continue
        m1 = momentum_score(px, 21)
        m3 = momentum_score(px, 63)
        m6 = momentum_score(px, 126)
        vals = [v for v in [m1, m3, m6] if not math.isnan(v)]
        if vals:
            scores.append(sum(vals) / len(vals))
    return float(np.nanmean(scores)) if scores else float("nan")


# ──────────────────────────────────────────────
# Agent 2: Breadth (% above MA200)
# ──────────────────────────────────────────────

def breadth_agent(pivot: pd.DataFrame, sectors: list[str], as_of: pd.Timestamp) -> float:
    """Fraction of sectors whose last price > 200-day MA. Returns [0, 1]."""
    data = pivot.loc[:as_of]
    above = total = 0
    for code in sectors:
        if code not in data.columns:
            continue
        px = data[code].dropna()
        if len(px) < 200:
            continue
        last = px.iloc[-1]
        ma200 = px.iloc[-200:].mean()
        total += 1
        if last > ma200:
            above += 1
    return above / total if total > 0 else float("nan")


# ──────────────────────────────────────────────
# Agent 3: Relative Strength
# ──────────────────────────────────────────────

def rel_strength_agent(pivot: pd.DataFrame, as_of: pd.Timestamp) -> float:
    """
    KR vs US relative strength: KOSPI / S&P500 ratio trend.
    Returns positive when KR outperforms, negative otherwise.
    Score = average of 1M/3M/6M relative returns.
    """
    data = pivot.loc[:as_of]
    if "EQ_KOSPI" not in data.columns or "EQ_SP500" not in data.columns:
        return float("nan")
    kr = data["EQ_KOSPI"].dropna()
    us = data["EQ_SP500"].dropna()
    # align
    common = kr.index.intersection(us.index)
    kr = kr.loc[common]
    us = us.loc[common]
    scores = []
    for lb in [21, 63, 126]:
        if len(kr) < lb + 1:
            continue
        kr_ret = kr.iloc[-1] / kr.iloc[-(lb + 1)] - 1
        us_ret = us.iloc[-1] / us.iloc[-(lb + 1)] - 1
        scores.append(kr_ret - us_ret)
    return float(np.nanmean(scores)) if scores else float("nan")


# ──────────────────────────────────────────────
# Agent 4: Risk (VIX regime, HY Spread, Yield Curve)
# ──────────────────────────────────────────────

def risk_agent(pivot: pd.DataFrame, macro: pd.DataFrame, as_of: pd.Timestamp) -> float:
    """
    Risk regime score. High risk → favor US (safe haven), Low risk → favor KR (risk-on).
    Returns [-1, 1]: positive = risk-on (favor KR), negative = risk-off (favor US).

    Components:
      - VIX level: <20 risk-on, 20-30 neutral, >30 risk-off
      - VIX trend: 20d change (falling = risk-on)
      - HY Spread trend: 3M change (widening = risk-off)
      - Yield curve: positive = normal (risk-on), inverted = risk-off
    """
    scores = []

    # --- VIX from market_data ---
    vix_data = pivot.loc[:as_of].get("RK_VIX")
    if vix_data is not None:
        vix = vix_data.dropna()
        if len(vix) >= 21:
            vix_now = float(vix.iloc[-1])
            vix_20d_ago = float(vix.iloc[-21])

            # Level score
            if vix_now < 15:
                level_score = 1.0
            elif vix_now < 20:
                level_score = 0.5
            elif vix_now < 25:
                level_score = 0.0
            elif vix_now < 30:
                level_score = -0.5
            else:
                level_score = -1.0
            scores.append(level_score)

            # Trend score (falling VIX = risk-on = positive)
            vix_change = (vix_now - vix_20d_ago) / vix_20d_ago if vix_20d_ago > 0 else 0
            trend_score = max(-1.0, min(1.0, -vix_change * 5))
            scores.append(trend_score)

    # --- HY Spread from macro ---
    hy_data = macro.loc[:as_of].get("US_HY_SPREAD")
    if hy_data is not None:
        hy = hy_data.dropna()
        if len(hy) >= 63:
            hy_now = float(hy.iloc[-1])
            hy_3m = float(hy.iloc[-63])
            spread_change = hy_now - hy_3m
            # Narrowing spread = risk-on (KR favor), widening = risk-off (US favor)
            spread_score = max(-1.0, min(1.0, -spread_change * 0.5))
            scores.append(spread_score)

    # --- Yield Curve from macro ---
    yc_data = macro.loc[:as_of].get("US_YIELD_CURVE")
    if yc_data is not None:
        yc = yc_data.dropna()
        if len(yc) >= 1:
            yc_val = float(yc.iloc[-1])
            # Positive = normal (risk-on), negative = inverted (risk-off)
            yc_score = max(-1.0, min(1.0, yc_val * 0.3))
            scores.append(yc_score)

    return float(np.nanmean(scores)) if scores else float("nan")


# ──────────────────────────────────────────────
# Agent 5: Macro Regime (GDP/CPI/Policy Rate differential)
# ──────────────────────────────────────────────

def macro_regime_agent(macro: pd.DataFrame, as_of: pd.Timestamp) -> float:
    """
    Macro regime differential. Positive = KR fundamentals stronger, negative = US stronger.

    Components:
      - GDP growth differential (KR - US): higher KR growth → favor KR
      - CPI differential (KR - US): higher KR inflation → slight US favor (stagflation risk)
      - Policy rate differential (KR - US): KR rate > US → KR tighter → slight US favor
      - US Fed stance: rate trend (cutting = risk-on → KR favor)
    """
    data = macro.loc[:as_of]
    scores = []

    # --- GDP Growth differential ---
    kr_gdp = data.get("KR_GDP_YOY")
    us_gdp = data.get("US_GDP_YOY")
    if kr_gdp is not None and us_gdp is not None:
        kr_g = kr_gdp.dropna()
        us_g = us_gdp.dropna()
        if len(kr_g) >= 1 and len(us_g) >= 1:
            diff = float(kr_g.iloc[-1]) - float(us_g.iloc[-1])
            # KR GDP growing faster → favor KR
            gdp_score = max(-1.0, min(1.0, diff * 0.15))
            scores.append(gdp_score * 1.5)  # higher weight

    # --- CPI differential ---
    kr_cpi = data.get("KR_CPI_YOY")
    us_cpi = data.get("US_CPI_YOY")
    if kr_cpi is not None and us_cpi is not None:
        kr_c = kr_cpi.dropna()
        us_c = us_cpi.dropna()
        if len(kr_c) >= 1 and len(us_c) >= 1:
            diff = float(kr_c.iloc[-1]) - float(us_c.iloc[-1])
            # Higher KR inflation relative to US → slight KR unfavor
            cpi_score = max(-1.0, min(1.0, -diff * 0.2))
            scores.append(cpi_score)

    # --- Policy Rate differential ---
    kr_rate = data.get("KR_BASE_RATE")
    us_rate = data.get("US_FED_RATE")
    if kr_rate is not None and us_rate is not None:
        kr_r = kr_rate.dropna()
        us_r = us_rate.dropna()
        if len(kr_r) >= 1 and len(us_r) >= 1:
            diff = float(kr_r.iloc[-1]) - float(us_r.iloc[-1])
            # KR rate much higher than US → tighter KR → slight US favor
            rate_score = max(-1.0, min(1.0, -diff * 0.2))
            scores.append(rate_score)

    # --- US CPI trend (falling = dovish expectations = risk-on = KR favor) ---
    if us_cpi is not None:
        us_c = us_cpi.dropna()
        if len(us_c) >= 4:
            cpi_trend = float(us_c.iloc[-1]) - float(us_c.iloc[-4])
            # Falling US CPI → dovish Fed → risk-on → KR favor
            trend_score = max(-1.0, min(1.0, -cpi_trend * 0.3))
            scores.append(trend_score)

    return float(np.nanmean(scores)) if scores else float("nan")


# ──────────────────────────────────────────────
# Signal Aggregation
# ──────────────────────────────────────────────

def _normalise(val: float, center: float = 0.0, scale: float = 0.10) -> float:
    """Soft normalise to [-1, 1] range via tanh."""
    if math.isnan(val):
        return 0.0
    return math.tanh((val - center) / scale)


def aggregate_signal(
    pivot: pd.DataFrame,
    as_of: pd.Timestamp,
    macro: pd.DataFrame | None = None,
) -> dict:
    """Run five agents and return combined composite score and signal."""
    if macro is None:
        macro = pd.DataFrame()

    # --- Momentum ---
    kr_mom = momentum_agent(pivot, KR_SECTORS, as_of)
    us_mom = momentum_agent(pivot, US_SECTORS, as_of)
    mom_diff = (0.0 if math.isnan(kr_mom) else kr_mom) - (0.0 if math.isnan(us_mom) else us_mom)

    # --- Breadth ---
    kr_brd = breadth_agent(pivot, KR_SECTORS, as_of)
    us_brd = breadth_agent(pivot, US_SECTORS, as_of)
    brd_diff = (0.0 if math.isnan(kr_brd) else kr_brd) - (0.0 if math.isnan(us_brd) else us_brd)

    # --- Relative Strength ---
    rs = rel_strength_agent(pivot, as_of)
    rs_norm = _normalise(0.0 if math.isnan(rs) else rs, center=0.0, scale=0.05)

    # --- Risk ---
    risk_raw = risk_agent(pivot, macro, as_of)
    risk_n = 0.0 if math.isnan(risk_raw) else max(-1.0, min(1.0, risk_raw))

    # --- Macro Regime ---
    macro_raw = macro_regime_agent(macro, as_of)
    macro_n = 0.0 if math.isnan(macro_raw) else max(-1.0, min(1.0, macro_raw))

    # weighted composite (normalise each diff to ~[-1,1])
    mom_n = _normalise(mom_diff, 0.0, 0.05)
    brd_n = _normalise(brd_diff, 0.0, 0.20)

    composite = (
        AGENT_WEIGHTS["momentum"] * mom_n
        + AGENT_WEIGHTS["breadth"] * brd_n
        + AGENT_WEIGHTS["rel_strength"] * rs_norm
        + AGENT_WEIGHTS["risk"] * risk_n
        + AGENT_WEIGHTS["macro"] * macro_n
    )

    if composite > THRESHOLD:
        signal = "KR"
    elif composite < -THRESHOLD:
        signal = "US"
    else:
        signal = "Neutral"

    return {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "kr_mom": round(kr_mom, 4) if not math.isnan(kr_mom) else None,
        "us_mom": round(us_mom, 4) if not math.isnan(us_mom) else None,
        "kr_breadth": round(kr_brd, 4) if not math.isnan(kr_brd) else None,
        "us_breadth": round(us_brd, 4) if not math.isnan(us_brd) else None,
        "rel_strength": round(rs, 4) if not math.isnan(rs) else None,
        "risk_score": round(risk_raw, 4) if not math.isnan(risk_raw) else None,
        "macro_score": round(macro_raw, 4) if not math.isnan(macro_raw) else None,
        "composite": round(composite, 4),
        "signal": signal,
    }


# ──────────────────────────────────────────────
# Backtest Engine
# ──────────────────────────────────────────────

def next_month_return(pivot: pd.DataFrame, month_end: pd.Timestamp, code: str) -> float | None:
    """Return of `code` from month_end to the following month's end."""
    future = pivot.loc[month_end:][code].dropna()
    if len(future) < 2:
        return None
    start_price = future.iloc[0]
    # find next month end
    next_me = month_end + pd.offsets.BusinessMonthEnd()
    future_until = future.loc[:next_me]
    if len(future_until) < 2:
        return None
    end_price = future_until.iloc[-1]
    return float(end_price / start_price - 1)


def run_backtest(pivot: pd.DataFrame, macro: pd.DataFrame | None = None) -> pd.DataFrame:
    months = month_ends(pivot)
    # skip first 6 months (need lookback data) and last (no future return)
    months = months[6:-1]

    has_fx = "EQ_KOSPI_USD" in pivot.columns
    cost = COST_BPS / 10_000  # 30bp → 0.003

    records = []
    prev_signal = None
    for me in months:
        sig = aggregate_signal(pivot, me, macro=macro)
        signal = sig["signal"]

        kr_ret    = next_month_return(pivot, me, "EQ_KOSPI")
        us_ret    = next_month_return(pivot, me, "EQ_SP500")
        kr_ret_fx = next_month_return(pivot, me, "EQ_KOSPI_USD") if has_fx else None

        if kr_ret is None or us_ret is None:
            continue

        # Transaction cost on signal change
        tc = cost if (prev_signal is not None and signal != prev_signal) else 0.0
        prev_signal = signal

        # Strategy return (KRW basis — signal logic uses local-currency momentum)
        if signal == "KR":
            strat_ret = kr_ret - tc
        elif signal == "US":
            strat_ret = us_ret - tc
        else:
            strat_ret = 0.5 * kr_ret + 0.5 * us_ret - tc

        # FX-adjusted strategy return (USD basis for apples-to-apples comparison)
        if kr_ret_fx is not None:
            if signal == "KR":
                strat_ret_fx = kr_ret_fx - tc
            elif signal == "US":
                strat_ret_fx = us_ret - tc
            else:
                strat_ret_fx = 0.5 * kr_ret_fx + 0.5 * us_ret - tc
            blend_ret_fx = 0.5 * kr_ret_fx + 0.5 * us_ret
        else:
            strat_ret_fx = None
            blend_ret_fx = None

        # FX return (USD/KRW monthly change — positive = KRW appreciation = KR investor gains)
        fx_ret = next_month_return(pivot, me, "FX_USDKRW")  # +ve = KRW weakens

        records.append({
            **sig,
            "cost": round(tc, 4),
            "kr_return":     round(kr_ret, 4),
            "us_return":     round(us_ret, 4),
            "kr_return_usd": round(kr_ret_fx, 4) if kr_ret_fx is not None else None,
            "fx_return":     round(fx_ret, 4) if fx_ret is not None else None,
            "blend_return":  round(0.5 * kr_ret + 0.5 * us_ret, 4),
            "blend_return_usd": round(blend_ret_fx, 4) if blend_ret_fx is not None else None,
            "strategy_return":     round(strat_ret, 4),
            "strategy_return_usd": round(strat_ret_fx, 4) if strat_ret_fx is not None else None,
        })

    return pd.DataFrame(records)


# ──────────────────────────────────────────────
# Performance Metrics
# ──────────────────────────────────────────────

def perf_metrics(returns: pd.Series, label: str) -> dict:
    r = returns.dropna()
    if len(r) == 0:
        return {}
    cum = (1 + r).cumprod()
    total = float(cum.iloc[-1] - 1)
    n_months = len(r)
    ann_ret = (1 + total) ** (12 / n_months) - 1
    ann_vol = float(r.std() * (12 ** 0.5))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    drawdown = (cum / cum.cummax() - 1)
    mdd = float(drawdown.min())
    win_rate = float((r > 0).mean())
    return {
        "label": label,
        "total_return": round(total, 4),
        "ann_return": round(ann_ret, 4),
        "ann_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 2),
        "mdd": round(mdd, 4),
        "win_rate": round(win_rate, 3),
        "n_months": n_months,
    }


# ──────────────────────────────────────────────
# HTML Report
# ──────────────────────────────────────────────

_C = {"KR": "#E63946", "US": "#1D3557", "Neutral": "#6C757D"}
_LIGHT = {"KR": "#FFF0F1", "US": "#EEF1F8", "Neutral": "#F8F9FA"}


def _badge(sig: str, size: str = "sm") -> str:
    fs = "0.75rem" if size == "sm" else "0.95rem"
    pad = "2px 9px" if size == "sm" else "4px 16px"
    return (
        f'<span style="background:{_C.get(sig,"#6C757D")};color:#fff;'
        f'padding:{pad};border-radius:20px;font-size:{fs};font-weight:700;'
        f'letter-spacing:.03em">{sig}</span>'
    )


def _ret_cell(val: float) -> str:
    color = "#16A34A" if val > 0 else ("#DC2626" if val < 0 else "#6B7280")
    arrow = "▲" if val > 0 else ("▼" if val < 0 else "")
    return f'<td class="num" style="color:{color}">{arrow}{abs(val*100):.1f}%</td>'


def _gauge_bar(kr: float, us: float) -> str:
    """Horizontal dual bar: KR left (red), US right (navy)."""
    total = abs(kr) + abs(us) or 1
    kr_pct = abs(kr) / total * 100
    us_pct = abs(us) / total * 100
    return (
        f'<div style="display:flex;height:6px;border-radius:3px;overflow:hidden;margin-top:6px">'
        f'<div style="width:{kr_pct:.0f}%;background:#E63946"></div>'
        f'<div style="width:{us_pct:.0f}%;background:#1D3557"></div>'
        f'</div>'
    )


def build_html(bt: pd.DataFrame, metrics: list[dict], date_str: str, metrics_fx: list[dict] | None = None) -> str:
    bs = bt.sort_values("as_of").reset_index(drop=True)

    # ── Cumulative return series ──────────────────
    cum_strat = ((1 + bs["strategy_return"]).cumprod() - 1).round(4).tolist()
    cum_blend = ((1 + bs["blend_return"]).cumprod() - 1).round(4).tolist()
    cum_kr    = ((1 + bs["kr_return"]).cumprod() - 1).round(4).tolist()
    cum_us    = ((1 + bs["us_return"]).cumprod() - 1).round(4).tolist()
    labels_j  = json.dumps(list(bs["as_of"]))

    # ── Drawdown series ───────────────────────────
    def _dd(rets: pd.Series) -> list:
        cum = (1 + rets).cumprod()
        return (cum / cum.cummax() - 1).round(4).tolist()

    dd_strat = _dd(bs["strategy_return"])
    dd_blend = _dd(bs["blend_return"])
    dd_kr    = _dd(bs["kr_return"])
    dd_us    = _dd(bs["us_return"])

    # ── Monthly heatmap data (strategy) ──────────
    bs["year"]  = bs["as_of"].str[:4]
    bs["month"] = bs["as_of"].str[5:7]
    years  = sorted(bs["year"].unique())
    months = [f"{m:02d}" for m in range(1, 13)]
    hm_rows = ""
    for y in years:
        hm_rows += f'<tr><td class="hm-year">{y}</td>'
        for m in months:
            row = bs[(bs["year"] == y) & (bs["month"] == m)]
            if row.empty:
                hm_rows += '<td class="hm-cell hm-empty">—</td>'
            else:
                v = row["strategy_return"].values[0]
                sig = row["signal"].values[0]
                intensity = min(int(abs(v) * 400), 90)
                if v > 0:
                    bg = f"rgba(22,163,74,0.{intensity:02d})"
                    fg = "#14532D" if intensity > 50 else "#166534"
                else:
                    bg = f"rgba(220,38,38,0.{intensity:02d})"
                    fg = "#7F1D1D" if intensity > 50 else "#991B1B"
                dot = f'<span style="width:6px;height:6px;border-radius:50%;background:{_C.get(sig,"#888")};display:inline-block;margin-left:2px;vertical-align:middle"></span>'
                hm_rows += (
                    f'<td class="hm-cell" style="background:{bg};color:{fg}">'
                    f'{v*100:+.1f}%{dot}</td>'
                )
        hm_rows += "</tr>"

    # ── Monthly bar chart (monthly excess vs blend) ─
    excess_vals = (bs["strategy_return"] - bs["blend_return"]).round(4).tolist()
    excess_colors = json.dumps(["rgba(22,163,74,0.75)" if v >= 0 else "rgba(220,38,38,0.75)" for v in excess_vals])

    # ── Signal indicator timeline (colored squares) ─
    timeline_html = ""
    for _, r in bs.iterrows():
        sig = r["signal"]
        color = _C.get(sig, "#888")
        timeline_html += (
            f'<div title="{r["as_of"]} · {sig} · {r["strategy_return"]*100:+.1f}%" '
            f'style="width:12px;height:24px;background:{color};border-radius:2px;cursor:default"></div>'
        )

    # ── Recent 24 months table ─────────────────────
    recent = bs.tail(24).iloc[::-1]
    tbl_rows = ""
    for _, r in recent.iterrows():
        sig = r["signal"]
        bg = _LIGHT.get(sig, "#fff")
        excess = r["strategy_return"] - r["blend_return"]
        exc_color = "#16A34A" if excess >= 0 else "#DC2626"
        kr_m = r["kr_mom"] if not math.isnan(r["kr_mom"] or float("nan")) else 0
        us_m = r["us_mom"] if not math.isnan(r["us_mom"] or float("nan")) else 0
        kr_b = r["kr_breadth"] if not math.isnan(r["kr_breadth"] or float("nan")) else 0
        us_b = r["us_breadth"] if not math.isnan(r["us_breadth"] or float("nan")) else 0
        r_risk = r.get("risk_score") or 0
        r_macro = r.get("macro_score") or 0
        r_cost = r.get("cost") or 0
        tbl_rows += (
            f'<tr style="background:{bg}">'
            f'<td>{r["as_of"]}</td>'
            f'<td style="text-align:center">{_badge(sig)}</td>'
            f'<td class="num">{r["composite"]:+.3f}</td>'
            f'<td class="num">{kr_m*100:+.1f}%<br><small style="color:#888">{kr_b*100:.0f}%⬆MA200</small></td>'
            f'<td class="num">{us_m*100:+.1f}%<br><small style="color:#888">{us_b*100:.0f}%⬆MA200</small></td>'
            f'<td class="num">{(r["rel_strength"] or 0)*100:+.1f}%</td>'
            f'<td class="num" style="font-size:0.75rem">{r_risk:+.2f}<br>{r_macro:+.2f}</td>'
            + _ret_cell(r["kr_return"])
            + _ret_cell(r["us_return"])
            + _ret_cell(r["strategy_return"])
            + f'<td class="num" style="color:{exc_color}">{excess*100:+.1f}%</td>'
            + (f'<td class="num" style="color:#94A3B8">{r_cost*10000:.0f}bp</td>' if r_cost > 0 else '<td class="num" style="color:#CBD5E1">—</td>')
            + f'</tr>'
        )

    # ── Metrics table ─────────────────────────────
    def _metrics_rows(m_list: list[dict], highlight_label: str) -> str:
        rows = ""
        dot_map = {
            "KR/US Rotation (KRW)": "#F58220", "KR/US Rotation (USD)": "#F58220",
            "50/50 Blend (KRW)": "#6C757D",    "50/50 Blend (USD)": "#6C757D",
            "KOSPI (KRW)": "#E63946",           "KOSPI (USD)": "#E63946",
            "S&P500 (USD)": "#1D3557",
        }
        for m in m_list:
            is_h = highlight_label in m["label"]
            bg = "background:#FFF7EE" if is_h else ""
            fw = "font-weight:700" if is_h else ""
            dc = dot_map.get(m["label"], "#888")
            dot = f'<span style="width:10px;height:10px;border-radius:50%;background:{dc};display:inline-block;margin-right:6px"></span>'
            rows += (
                f'<tr style="{bg};{fw}">'
                f'<td>{dot}{m["label"]}</td>'
                f'<td class="num">{m["total_return"]*100:+.1f}%</td>'
                f'<td class="num">{m["ann_return"]*100:+.1f}%</td>'
                f'<td class="num">{m["ann_vol"]*100:.1f}%</td>'
                f'<td class="num">{m["sharpe"]:.2f}</td>'
                f'<td class="num" style="color:#DC2626">{m["mdd"]*100:.1f}%</td>'
                f'<td class="num">{m["win_rate"]*100:.0f}%</td>'
                f'<td class="num">{m["n_months"]}</td>'
                f'</tr>'
            )
        return rows

    m_rows    = _metrics_rows(metrics,    "KR/US Rotation")
    m_rows_fx = _metrics_rows(metrics_fx, "KR/US Rotation") if metrics_fx else ""

    # ── FX (USD/KRW) monthly return series for chart ──
    has_fx_data = "fx_return" in bs.columns and bs["fx_return"].notna().any()
    if has_fx_data:
        fx_vals = bs["fx_return"].fillna(0).round(4).tolist()
        fx_colors_js = json.dumps([
            "rgba(220,38,38,0.6)" if v > 0 else "rgba(22,163,74,0.6)"
            for v in bs["fx_return"].fillna(0)
        ])
        # KRW appreciation = FX_USDKRW가 내려감 = fx_return < 0 → KR USD 수익 증가
        cum_kr_usd = ((1 + bs["kr_return_usd"].fillna(0)).cumprod() - 1).round(4).tolist()
        cum_strat_usd = ((1 + bs["strategy_return_usd"].fillna(0)).cumprod() - 1).round(4).tolist()
    else:
        fx_vals = []
        fx_colors_js = "[]"
        cum_kr_usd = []
        cum_strat_usd = []

    # ── Current signal hero ───────────────────────
    last = bs.iloc[-1]
    sig_now = last["signal"]
    hero_bg = {"KR": "linear-gradient(135deg,#7F1D1D,#E63946)", "US": "linear-gradient(135deg,#1e3a5f,#1D3557)", "Neutral": "linear-gradient(135deg,#374151,#6B7280)"}[sig_now]
    kr_m_now = (last["kr_mom"] or 0) * 100
    us_m_now = (last["us_mom"] or 0) * 100
    kr_b_now = (last["kr_breadth"] or 0) * 100
    us_b_now = (last["us_breadth"] or 0) * 100
    rs_now   = (last["rel_strength"] or 0) * 100
    risk_now = last.get("risk_score") or 0
    macro_now = last.get("macro_score") or 0
    total_cost = bs["cost"].sum() if "cost" in bs.columns else 0
    n_trades = (bs["cost"] > 0).sum() if "cost" in bs.columns else 0
    sig_counts = bs["signal"].value_counts().to_dict()

    def _build_narrative(last_row: pd.Series, bt_df: pd.DataFrame, m_list: list[dict], ds: str) -> str:
        """Generate a dynamic plain-Korean narrative explaining the current signal and strategy logic."""
        sig = last_row["signal"]
        comp = last_row["composite"]
        kr_m = (last_row["kr_mom"] or 0) * 100
        us_m = (last_row["us_mom"] or 0) * 100
        kr_b = (last_row["kr_breadth"] or 0) * 100
        us_b = (last_row["us_breadth"] or 0) * 100
        rs = (last_row["rel_strength"] or 0) * 100
        risk_s = last_row.get("risk_score") or 0
        macro_s = last_row.get("macro_score") or 0
        strat_m = m_list[0]
        blend_m = m_list[1]
        kospi_m = m_list[2]
        sp500_m = m_list[3]
        n = len(bt_df)
        kr_count = (bt_df["signal"] == "KR").sum()
        us_count = (bt_df["signal"] == "US").sum()
        nt_count = (bt_df["signal"] == "Neutral").sum()

        # Signal strength description
        if abs(comp) >= 0.5:
            strength = "강한"
        elif abs(comp) >= 0.2:
            strength = "보통 수준의"
        else:
            strength = "약한"

        # Signal direction narrative
        if sig == "KR":
            direction = f"한국 시장 비중 확대(KR)"
            reason_parts = []
            if kr_m > us_m:
                reason_parts.append(f"한국 섹터 모멘텀({kr_m:+.1f}%)이 미국({us_m:+.1f}%)보다 강하고")
            if kr_b > us_b:
                reason_parts.append(f"MA200 상회 섹터 비율도 한국({kr_b:.0f}%)이 미국({us_b:.0f}%)보다 높으며")
            if rs > 0:
                reason_parts.append(f"KOSPI의 상대 강도 역시 플러스({rs:+.1f}%)")
            reason = "、".join(reason_parts) if reason_parts else "종합 지표가 한국 우위를 가리키고 있어"
        elif sig == "US":
            direction = f"미국 시장 비중 확대(US)"
            reason_parts = []
            if us_m > kr_m:
                reason_parts.append(f"미국 섹터 모멘텀({us_m:+.1f}%)이 한국({kr_m:+.1f}%)을 앞서고")
            if us_b > kr_b:
                reason_parts.append(f"MA200 상회 섹터 비율도 미국({us_b:.0f}%)이 한국({kr_b:.0f}%)보다 넓으며")
            if rs < 0:
                reason_parts.append(f"S&P500 대비 KOSPI 상대 수익률이 마이너스({rs:+.1f}%)")
            reason = "、".join(reason_parts) if reason_parts else "종합 지표가 미국 우위를 가리키고 있어"
        else:
            direction = "중립(Neutral)"
            reason = f"KR과 US의 점수 차이가 임계값(±{THRESHOLD}) 이내에 머물러 뚜렷한 방향성이 없어"

        risk_desc = "위험 선호(Risk-On)" if risk_s > 0.2 else ("위험 회피(Risk-Off)" if risk_s < -0.2 else "중립")
        macro_desc = "한국 펀더멘탈 우위" if macro_s > 0.15 else ("미국 펀더멘탈 우위" if macro_s < -0.15 else "양국 유사")

        # Backtest summary
        alpha = strat_m["ann_return"] - blend_m["ann_return"]
        sharpe_diff = strat_m["sharpe"] - blend_m["sharpe"]
        mdd_diff = strat_m["mdd"] - blend_m["mdd"]

        # Recent 6-month wins
        recent6 = bt_df.tail(6)
        recent6_strat = recent6["strategy_return"].mean() * 100
        recent6_blend = recent6["blend_return"].mean() * 100

        return f"""
<div class="narr-section">
  <h3 class="narr-h">이 전략이란?</h3>
  <p>이 모델은 매달 한국(KOSPI)과 미국(S&amp;P500) 중 어느 시장이 <strong>다음 달에 더 좋을지</strong>를 다섯 가지 에이전트가 독립적으로 판단한 뒤, 가중 합산으로 포지션을 결정합니다. 두 시장을 반반(50/50)씩 들고 가는 것이 기본이고, 신호가 강할 때만 한쪽으로 베팅합니다. 신호 변경 시 편도 {COST_BPS}bp 거래비용을 차감합니다.</p>
</div>

<div class="narr-section">
  <h3 class="narr-h">다섯 가지 판단 에이전트</h3>
  <div class="narr-agent-grid" style="grid-template-columns:repeat(3,1fr)">
    <div class="narr-agent">
      <div class="na-icon">① 모멘텀</div>
      <div class="na-weight">가중치 30%</div>
      <div class="na-desc">한국·미국 <strong>섹터 11개씩</strong>의 1M/3M/6M 수익률 평균. 더 많이 오른 시장에 힘이 있다고 봅니다.</div>
    </div>
    <div class="narr-agent">
      <div class="na-icon">② 확산도</div>
      <div class="na-weight">가중치 15%</div>
      <div class="na-desc"><strong>200일 이동평균선 위에 있는 섹터 비율</strong>. 많은 섹터가 장기 추세 위 = 시장이 건강합니다.</div>
    </div>
    <div class="narr-agent">
      <div class="na-icon">③ 상대강도</div>
      <div class="na-weight">가중치 15%</div>
      <div class="na-desc">KOSPI vs S&amp;P500 <strong>1M/3M/6M 수익률 직접 비교</strong>. 한국이 더 올랐으면 한국 유리.</div>
    </div>
    <div class="narr-agent" style="border-left-color:#DC2626">
      <div class="na-icon">④ 리스크</div>
      <div class="na-weight">가중치 15%</div>
      <div class="na-desc"><strong>VIX 수준·추세, HY 스프레드, 수익률 곡선</strong>을 종합. Risk-Off → 미국(안전), Risk-On → 한국(위험선호) 유리.</div>
    </div>
    <div class="narr-agent" style="border-left-color:#059669">
      <div class="na-icon">⑤ 매크로</div>
      <div class="na-weight">가중치 25%</div>
      <div class="na-desc"><strong>GDP 성장률·CPI·기준금리</strong> 한미 격차. 한국 경제가 상대적으로 강하면 한국 유리.</div>
    </div>
  </div>
</div>

<div class="narr-section">
  <h3 class="narr-h">지금 신호: <span style="color:{_C.get(sig,'#888')}">{direction}</span></h3>
  <p>가장 최근 월말({last_row["as_of"]}) 기준으로 모델은 <strong>{strength} {direction}</strong> 신호를 내고 있습니다 (Composite Score {comp:+.3f}).</p>
  <ul class="narr-list">
    <li><strong>모멘텀</strong>: 한국 섹터 평균 {kr_m:+.1f}% vs 미국 섹터 평균 {us_m:+.1f}%</li>
    <li><strong>확산도</strong>: 한국 MA200 상회 섹터 {kr_b:.0f}% vs 미국 {us_b:.0f}%</li>
    <li><strong>상대강도</strong>: KOSPI의 대미(對美) 초과수익 {rs:+.1f}%</li>
    <li><strong>리스크</strong>: {risk_desc} (score {risk_s:+.2f}) — VIX·HY스프레드·수익률곡선 종합</li>
    <li><strong>매크로</strong>: {macro_desc} (score {macro_s:+.2f}) — GDP·CPI·금리 한미 격차</li>
  </ul>
  <p style="margin-top:10px">{reason}서 {direction}이 선택되었습니다.</p>
</div>

<div class="narr-section">
  <h3 class="narr-h">백테스트 성과 요약 ({bt_df["as_of"].iloc[0][:7]} ~ {bt_df["as_of"].iloc[-1][:7]}, {n}개월)</h3>
  <p>전략은 연 <strong>{strat_m["ann_return"]*100:.1f}%</strong>를 기록해, 그냥 반반씩 보유한 블렌드(연 {blend_m["ann_return"]*100:.1f}%)보다 <strong>연간 {alpha*100:.1f}%p 더 벌었습니다</strong>. 위험 대비 수익(Sharpe) 역시 {strat_m["sharpe"]:.2f}로 블렌드({blend_m["sharpe"]:.2f})보다 {sharpe_diff:+.2f} 높습니다.</p>
  <ul class="narr-list">
    <li><strong>최대낙폭(MDD)</strong>: {strat_m["mdd"]*100:.1f}% — 블렌드 {blend_m["mdd"]*100:.1f}%보다 {"낙폭이 작습니다" if mdd_diff > 0 else f"{abs(mdd_diff)*100:.1f}%p 작습니다"}</li>
    <li><strong>월간 승률</strong>: {strat_m["win_rate"]*100:.0f}% ({n}개월 중 {int(strat_m["win_rate"]*n)}개월 플러스)</li>
    <li><strong>신호 분포</strong>: KR {kr_count}회 · Neutral {nt_count}회 · US {us_count}회 — 전체의 {kr_count/n*100:.0f}%가 KR, {us_count/n*100:.0f}%가 US였습니다</li>
    <li><strong>최근 6개월 평균</strong>: 전략 월평균 {recent6_strat:+.1f}% vs 블렌드 {recent6_blend:+.1f}%</li>
  </ul>
</div>

<div class="narr-section">
  <h3 class="narr-h">전략의 한계</h3>
  <ul class="narr-list">
    <li><strong>데이터 제약</strong>: 2010년부터 {n}개월 백테스트입니다. 2008년 금융위기나 닷컴 버블 같은 극단 국면은 검증되지 않았습니다.</li>
    <li><strong>매크로 지표 지연</strong>: GDP·CPI 등 거시지표는 월간/분기간 발표되어 실시간 반응이 느립니다. 리스크 에이전트(VIX)가 빠른 위기 대응을 보완합니다.</li>
    <li><strong>환율 영향</strong>: KR 신호 시 KOSPI 원화 수익률 적용. FX 섹션에서 USD 환산 성과를 별도 확인할 수 있습니다.</li>
    <li><strong>거래비용</strong>: 신호 변경 시 편도 {COST_BPS}bp를 차감합니다. 세금은 미포함입니다.</li>
  </ul>
</div>
"""

    def _score_row(label: str, kr_v: float, us_v: float, unit: str = "%") -> str:
        diff = kr_v - us_v
        bar = _gauge_bar(kr_v, us_v)
        sign = "+" if diff >= 0 else ""
        return (
            f'<div class="sr-row">'
            f'<div class="sr-label">{label}</div>'
            f'<div class="sr-vals">'
            f'<span style="color:#E63946">🇰🇷 {kr_v:+.1f}{unit}</span>'
            f'<span class="sr-diff" style="color:{"#E63946" if diff>=0 else "#1D3557"}">{sign}{diff:.1f}{unit}</span>'
            f'<span style="color:#1D3557">🇺🇸 {us_v:+.1f}{unit}</span>'
            f'</div>'
            f'{bar}</div>'
        )

    # ── Narrative explanation ──────────────────────
    narrative = _build_narrative(last, bs, metrics, date_str)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>KR/US 섹터 로테이션 — {date_str}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Noto Sans KR',sans-serif;background:#F0F2F5;color:#1A1A2E;font-size:14px}}
.page{{max-width:1200px;margin:0 auto;padding:28px 20px}}

/* Header */
.header{{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:24px;flex-wrap:wrap;gap:12px}}
.header-left h1{{font-size:1.6rem;font-weight:700;color:#043B72;line-height:1.2}}
.header-left .sub{{color:#64748B;font-size:0.85rem;margin-top:4px}}
.header-right{{font-size:0.82rem;color:#94A3B8;text-align:right}}

/* Hero Signal */
.hero{{background:{hero_bg};border-radius:16px;padding:28px 32px;color:#fff;margin-bottom:24px;display:grid;grid-template-columns:auto 1fr auto;gap:32px;align-items:center}}
.hero-signal{{text-align:center}}
.hero-signal .sig-label{{font-size:0.75rem;opacity:.7;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}}
.hero-signal .sig-big{{font-size:3rem;font-weight:900;letter-spacing:-.02em;line-height:1}}
.hero-signal .sig-sub{{font-size:0.8rem;opacity:.6;margin-top:6px}}
.hero-score{{text-align:center;padding:0 24px;border-left:1px solid rgba(255,255,255,.2);border-right:1px solid rgba(255,255,255,.2)}}
.hero-score .sc-label{{font-size:0.72rem;opacity:.7;text-transform:uppercase;letter-spacing:.05em}}
.hero-score .sc-val{{font-family:'JetBrains Mono',monospace;font-size:2.2rem;font-weight:700;margin-top:4px}}
.hero-agents{{flex:1}}
.sr-row{{margin-bottom:12px}}
.sr-label{{font-size:0.72rem;opacity:.7;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px}}
.sr-vals{{display:flex;justify-content:space-between;font-size:0.82rem;font-weight:600}}
.sr-diff{{opacity:.9}}

/* Cards */
.card{{background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.07),0 2px 8px rgba(0,0,0,.04);padding:22px 24px;margin-bottom:20px}}
.card-title{{font-size:0.92rem;font-weight:700;color:#043B72;margin-bottom:16px;display:flex;align-items:center;gap:8px}}
.card-title .tag{{background:#EEF4FF;color:#4361EE;font-size:0.72rem;font-weight:600;padding:2px 8px;border-radius:4px}}

/* Grid layouts */
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
@media(max-width:720px){{.grid2,.grid3{{grid-template-columns:1fr}}.hero{{grid-template-columns:1fr}}}}

/* KPI chips */
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.kpi{{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.kpi-label{{font-size:0.73rem;color:#64748B;font-weight:500;margin-bottom:6px}}
.kpi-val{{font-size:1.5rem;font-weight:700}}
.kpi-sub{{font-size:0.75rem;color:#94A3B8;margin-top:3px}}

/* Tables */
table{{width:100%;border-collapse:collapse;font-size:0.84rem}}
th{{background:#F8FAFC;color:#475569;font-weight:600;padding:8px 10px;border-bottom:2px solid #E2E8F0;white-space:nowrap}}
td{{padding:7px 10px;border-bottom:1px solid #F1F5F9}}
.num{{font-family:'JetBrains Mono',monospace;font-size:0.82rem;text-align:right;white-space:nowrap}}
tr:hover td{{background:#FAFBFF}}

/* Heatmap */
.hm-table{{width:100%;border-collapse:separate;border-spacing:2px;font-size:0.78rem}}
.hm-year{{font-weight:700;color:#334155;padding:4px 8px;white-space:nowrap}}
.hm-cell{{text-align:center;padding:5px 3px;border-radius:4px;min-width:52px;cursor:default;font-family:'JetBrains Mono',monospace;font-size:0.75rem;white-space:nowrap}}
.hm-empty{{background:#F8FAFC;color:#CBD5E1}}

/* Timeline */
.timeline{{display:flex;gap:3px;flex-wrap:wrap;padding:8px 0}}
.timeline-legend{{display:flex;gap:16px;margin-top:8px;font-size:0.78rem;color:#64748B}}
.tl-dot{{width:10px;height:10px;border-radius:2px;display:inline-block;margin-right:4px}}

/* Narrative */
.narr-card{{background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.07),0 2px 8px rgba(0,0,0,.04);padding:28px 32px;margin-bottom:20px}}
.narr-card-title{{font-size:1rem;font-weight:700;color:#043B72;margin-bottom:20px;padding-bottom:12px;border-bottom:2px solid #F0F2F5}}
.narr-section{{margin-bottom:22px}}
.narr-section:last-child{{margin-bottom:0}}
.narr-h{{font-size:0.9rem;font-weight:700;color:#1E293B;margin-bottom:8px}}
.narr-section p{{font-size:0.88rem;line-height:1.75;color:#374151}}
.narr-list{{font-size:0.86rem;line-height:1.7;color:#374151;padding-left:18px;margin-top:6px}}
.narr-list li{{margin-bottom:4px}}
.narr-agent-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:10px}}
.narr-agent{{background:#F8FAFC;border-radius:10px;padding:14px 16px;border-left:4px solid #4361EE}}
.na-icon{{font-size:0.88rem;font-weight:700;color:#1E293B;margin-bottom:3px}}
.na-weight{{font-size:0.75rem;color:#4361EE;font-weight:600;margin-bottom:6px}}
.na-desc{{font-size:0.82rem;line-height:1.65;color:#475569}}
@media(max-width:720px){{.narr-agent-grid{{grid-template-columns:1fr}}}}

/* Donut stat boxes */
.sig-stat{{background:#F8FAFC;border-radius:8px;padding:12px;text-align:center}}
.sig-stat-val{{font-size:1.8rem;font-weight:800}}
.sig-stat-label{{font-size:0.75rem;color:#64748B;margin-top:2px}}
</style>
</head>
<body>
<div class="page">

<!-- Header -->
<div class="header">
  <div class="header-left">
    <h1>🔄 KR / US 섹터 로테이션 모델</h1>
    <div class="sub">5-Agent Ensemble · Momentum 30% + Breadth 15% + RelStrength 15% + Risk 15% + Macro 25% · 월간 리밸런싱 · 신호변경시 30bp 비용</div>
  </div>
  <div class="header-right">
    생성일: {date_str}<br>
    백테스트: {bs["as_of"].iloc[0]} ~ {bs["as_of"].iloc[-1]}<br>
    총 {len(bs)}개월
  </div>
</div>

<!-- Hero: Current Signal -->
<div class="hero">
  <div class="hero-signal">
    <div class="sig-label">이번 달 신호</div>
    <div class="sig-big">{sig_now}</div>
    <div class="sig-sub">{last["as_of"]} 월말 기준</div>
  </div>
  <div class="hero-score">
    <div class="sc-label">Composite Score</div>
    <div class="sc-val">{last["composite"]:+.3f}</div>
  </div>
  <div class="hero-agents">
    {_score_row("Momentum (30%)", kr_m_now, us_m_now)}
    {_score_row("Breadth (15%)", kr_b_now, us_b_now)}
    {_score_row("RelStrength (15%)", rs_now, 0.0)}
    <div class="sr-row" style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,.15)">
      <div style="display:flex;gap:20px;font-size:0.82rem">
        <span>🛡️ Risk (15%) <b style="color:{'#4ADE80' if risk_now>0 else '#F87171'}">{risk_now:+.2f}</b></span>
        <span>📊 Macro (25%) <b style="color:{'#4ADE80' if macro_now>0 else '#F87171'}">{macro_now:+.2f}</b></span>
      </div>
      <div style="font-size:0.72rem;color:rgba(255,255,255,.5);margin-top:4px">거래비용 {total_cost*10000:.0f}bp ({n_trades}회 변경)</div>
    </div>
  </div>
</div>

<!-- KPI Row -->
<div class="kpi-row">
  <div class="kpi">
    <div class="kpi-label">KR/US 로테이션 · 연환산</div>
    <div class="kpi-val" style="color:#F58220">{metrics[0]["ann_return"]*100:+.1f}%</div>
    <div class="kpi-sub">총수익률 {metrics[0]["total_return"]*100:+.1f}% · {metrics[0]["n_months"]}개월</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Sharpe Ratio</div>
    <div class="kpi-val" style="color:#043B72">{metrics[0]["sharpe"]:.2f}</div>
    <div class="kpi-sub">50/50 블렌드 {metrics[1]["sharpe"]:.2f} 대비 +{metrics[0]["sharpe"]-metrics[1]["sharpe"]:.2f}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">최대낙폭 (MDD)</div>
    <div class="kpi-val" style="color:#DC2626">{metrics[0]["mdd"]*100:.1f}%</div>
    <div class="kpi-sub">KOSPI {metrics[2]["mdd"]*100:.1f}% vs S&amp;P500 {metrics[3]["mdd"]*100:.1f}%</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">월간 승률</div>
    <div class="kpi-val" style="color:#16A34A">{metrics[0]["win_rate"]*100:.0f}%</div>
    <div class="kpi-sub">블렌드 {metrics[1]["win_rate"]*100:.0f}% · KOSPI {metrics[2]["win_rate"]*100:.0f}%</div>
  </div>
</div>

<!-- Narrative -->
<div class="narr-card">
  <div class="narr-card-title">💬 전략 해설</div>
  {narrative}
</div>

<!-- Chart: Cumulative + Drawdown -->
<div class="card">
  <div class="card-title">📈 누적 수익률 비교 <span class="tag">백테스트</span></div>
  <canvas id="cumChart" height="55"></canvas>
</div>
<div class="card">
  <div class="card-title">📉 드로다운 (Drawdown)</div>
  <canvas id="ddChart" height="40"></canvas>
</div>

{f'''<div class="card">
  <div class="card-title">💱 환율(USD/KRW) 영향 <span class="tag">원/달러 월간 변동 + 누적 수익 비교</span></div>
  <div class="grid2" style="gap:16px">
    <div>
      <div style="font-size:0.8rem;color:#64748B;margin-bottom:8px">USD/KRW 월간 변동률 <span style="color:#DC2626">■ 원화약세(KR불리)</span> <span style="color:#16A34A">■ 원화강세(KR유리)</span></div>
      <canvas id="fxBarChart" height="100"></canvas>
    </div>
    <div>
      <div style="font-size:0.8rem;color:#64748B;margin-bottom:8px">누적 수익률 비교 — KRW vs USD 기준</div>
      <canvas id="fxCumChart" height="100"></canvas>
    </div>
  </div>
</div>''' if has_fx_data else ''}

<!-- Performance Table + Signal Distribution -->
<div class="grid2">
  <div class="card">
    <div class="card-title">🏆 전략별 성과 요약 <span class="tag">원화(KRW) 기준</span></div>
    <table>
      <thead><tr><th>전략</th><th>총수익률</th><th>연환산</th><th>변동성</th><th>Sharpe</th><th>MDD</th><th>승률</th><th>N</th></tr></thead>
      <tbody>{m_rows}</tbody>
    </table>
    {f'''<div style="margin-top:16px;padding-top:14px;border-top:1px solid #F1F5F9">
    <div class="card-title" style="margin-bottom:10px">💱 환율 반영 성과 <span class="tag">USD 기준 (KOSPI→달러 환산)</span></div>
    <table>
      <thead><tr><th>전략</th><th>총수익률</th><th>연환산</th><th>변동성</th><th>Sharpe</th><th>MDD</th><th>승률</th><th>N</th></tr></thead>
      <tbody>{m_rows_fx}</tbody>
    </table>
    <p style="font-size:0.78rem;color:#94A3B8;margin-top:8px">KOSPI(KRW) ÷ USD/KRW 환율 = KOSPI(USD). 원화 강세 시 USD 기준 수익↑, 원화 약세 시↓</p>
    </div>''' if m_rows_fx else ''}
  </div>
  <div class="card">
    <div class="card-title">📊 신호 분포 <span class="tag">{len(bs)}개월</span></div>
    <canvas id="sigChart" height="160"></canvas>
    <div class="grid3" style="margin-top:16px">
      <div class="sig-stat">
        <div class="sig-stat-val" style="color:{_C['KR']}">{sig_counts.get('KR',0)}</div>
        <div class="sig-stat-label">🇰🇷 KR 신호</div>
      </div>
      <div class="sig-stat">
        <div class="sig-stat-val" style="color:{_C['Neutral']}">{sig_counts.get('Neutral',0)}</div>
        <div class="sig-stat-label">⚖️ Neutral</div>
      </div>
      <div class="sig-stat">
        <div class="sig-stat-val" style="color:{_C['US']}">{sig_counts.get('US',0)}</div>
        <div class="sig-stat-label">🇺🇸 US 신호</div>
      </div>
    </div>
  </div>
</div>

<!-- Excess Return Bar Chart -->
<div class="card">
  <div class="card-title">📊 월별 초과수익 (vs 50/50 블렌드) <span class="tag">green=초과, red=미달</span></div>
  <canvas id="excessChart" height="35"></canvas>
</div>

<!-- Heatmap -->
<div class="card">
  <div class="card-title">🗓️ 월별 수익률 히트맵
    <span class="tag">전략 수익률</span>
    <span style="font-size:0.75rem;color:#64748B;font-weight:400;margin-left:8px">
      점(●) 색상: 🔴KR 신호 · 🔵US 신호 · ⚫Neutral
    </span>
  </div>
  <div style="overflow-x:auto">
    <table class="hm-table">
      <thead><tr><th></th>{''.join(f'<th style="text-align:center;color:#64748B;font-size:0.78rem">{m}월</th>' for m in range(1,13))}</tr></thead>
      <tbody>{hm_rows}</tbody>
    </table>
  </div>
</div>

<!-- Signal Timeline -->
<div class="card">
  <div class="card-title">🕐 신호 타임라인 <span class="tag">월별 포지션</span></div>
  <div class="timeline">{timeline_html}</div>
  <div class="timeline-legend">
    <span><span class="tl-dot" style="background:#E63946"></span>KR</span>
    <span><span class="tl-dot" style="background:#6B7280"></span>Neutral</span>
    <span><span class="tl-dot" style="background:#1D3557"></span>US</span>
    <span style="color:#94A3B8">← {bs["as_of"].iloc[0][:7]} &nbsp;·&nbsp; {bs["as_of"].iloc[-1][:7]} →</span>
  </div>
</div>

<!-- Full History Table -->
<div class="card">
  <div class="card-title">📋 최근 24개월 상세 내역 <span class="tag">초과수익 = 전략 − 50/50 블렌드</span></div>
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th>월말</th><th style="text-align:center">신호</th><th class="num">Score</th>
        <th class="num">KR 모멘텀<br><small>/ MA200↑</small></th>
        <th class="num">US 모멘텀<br><small>/ MA200↑</small></th>
        <th class="num">상대강도</th>
        <th class="num">Risk<br><small>Macro</small></th>
        <th class="num">KOSPI</th><th class="num">S&amp;P500</th>
        <th class="num">전략</th><th class="num">초과수익</th><th class="num">비용</th>
      </tr>
    </thead>
    <tbody>{tbl_rows}</tbody>
  </table>
  </div>
</div>

<!-- Footer -->
<div style="font-size:0.78rem;color:#94A3B8;text-align:center;padding:16px 0 8px">
  Momentum (30%) · Breadth (15%) · RelStrength (15%) · Risk (15%) · Macro (25%) &nbsp;|&nbsp;
  5-Agent Ensemble · 월간 리밸런싱 · 신호변경시 30bp &nbsp;|&nbsp;
  데이터: market_data.csv + macro_indicators.csv
</div>

</div><!-- .page -->

<script>
const labels = {labels_j};
const strat  = {json.dumps([round(v,4) for v in cum_strat])};
const blend  = {json.dumps([round(v,4) for v in cum_blend])};
const kospi  = {json.dumps([round(v,4) for v in cum_kr])};
const sp500  = {json.dumps([round(v,4) for v in cum_us])};
const ddStrat = {json.dumps([round(v,4) for v in dd_strat])};
const ddBlend = {json.dumps([round(v,4) for v in dd_blend])};
const ddKospi = {json.dumps([round(v,4) for v in dd_kr])};
const ddSp500 = {json.dumps([round(v,4) for v in dd_us])};
const excess  = {json.dumps([round(v,4) for v in excess_vals])};
const exColors = {excess_colors};

const baseOpts = {{
  responsive:true,
  interaction:{{mode:'index',intersect:false}},
  plugins:{{legend:{{position:'bottom',labels:{{boxWidth:12,font:{{size:11}}}}}}}},
  scales:{{x:{{ticks:{{maxTicksLimit:12,font:{{size:10}}}}}},y:{{ticks:{{font:{{size:10}}}}}}}}
}};

// Cumulative
new Chart('cumChart',{{
  type:'line',
  data:{{labels,datasets:[
    {{label:'🟠 KR/US Rotation',data:strat,borderColor:'#F58220',borderWidth:2.5,pointRadius:0,fill:false,tension:0.1}},
    {{label:'⚫ 50/50 Blend',   data:blend,borderColor:'#94A3B8',borderWidth:1.5,borderDash:[5,3],pointRadius:0,fill:false}},
    {{label:'🔴 KOSPI',         data:kospi,borderColor:'#E63946',borderWidth:1.5,borderDash:[2,3],pointRadius:0,fill:false}},
    {{label:'🔵 S&P500',        data:sp500,borderColor:'#1D3557',borderWidth:1.5,borderDash:[2,3],pointRadius:0,fill:false}},
  ]}},
  options:{{...baseOpts,scales:{{...baseOpts.scales,y:{{ticks:{{callback:v=>(v*100).toFixed(0)+'%',font:{{size:10}}}}}}}}}}
}});

// Drawdown
new Chart('ddChart',{{
  type:'line',
  data:{{labels,datasets:[
    {{label:'🟠 KR/US Rotation',data:ddStrat,borderColor:'#F58220',borderWidth:2,pointRadius:0,fill:true,backgroundColor:'rgba(245,130,32,0.08)',tension:0.1}},
    {{label:'⚫ 50/50 Blend',   data:ddBlend,borderColor:'#94A3B8',borderWidth:1,borderDash:[5,3],pointRadius:0,fill:false}},
    {{label:'🔴 KOSPI',         data:ddKospi,borderColor:'#E63946',borderWidth:1,borderDash:[2,3],pointRadius:0,fill:false}},
    {{label:'🔵 S&P500',        data:ddSp500,borderColor:'#1D3557',borderWidth:1,borderDash:[2,3],pointRadius:0,fill:false}},
  ]}},
  options:{{...baseOpts,scales:{{...baseOpts.scales,y:{{ticks:{{callback:v=>(v*100).toFixed(1)+'%',font:{{size:10}}}}}}}}}}
}});

// Excess Bar
new Chart('excessChart',{{
  type:'bar',
  data:{{labels,datasets:[{{label:'초과수익 vs 블렌드',data:excess,backgroundColor:exColors,borderRadius:3}}]}},
  options:{{...baseOpts,plugins:{{...baseOpts.plugins,legend:{{display:false}}}},scales:{{...baseOpts.scales,y:{{ticks:{{callback:v=>(v*100).toFixed(1)+'%',font:{{size:10}}}}}}}}}}
}});

{f"""
// FX Bar
const fxVals = {json.dumps([round(v,4) for v in fx_vals])};
const fxColors = {fx_colors_js};
if(document.getElementById('fxBarChart')){{
  new Chart('fxBarChart',{{
    type:'bar',
    data:{{labels,datasets:[{{label:'USD/KRW 월간변동',data:fxVals,backgroundColor:fxColors,borderRadius:2}}]}},
    options:{{...baseOpts,plugins:{{...baseOpts.plugins,legend:{{display:false}}}},
      scales:{{...baseOpts.scales,y:{{ticks:{{callback:v=>(v*100).toFixed(1)+'%',font:{{size:10}}}}}}}}}}
  }});
}}
// FX Cum comparison
const cumKrUsd = {json.dumps([round(v,4) for v in cum_kr_usd])};
const cumStratUsd = {json.dumps([round(v,4) for v in cum_strat_usd])};
const cumKr = {json.dumps([round(v,4) for v in cum_kr])};
if(document.getElementById('fxCumChart')){{
  new Chart('fxCumChart',{{
    type:'line',
    data:{{labels,datasets:[
      {{label:'🟠 전략(KRW)',  data:cumKr,      borderColor:'#F58220',borderWidth:2,pointRadius:0,borderDash:[3,2],fill:false}},
      {{label:'🟠 전략(USD)',  data:cumStratUsd,borderColor:'#F58220',borderWidth:2.5,pointRadius:0,fill:false}},
      {{label:'🔴 KOSPI(KRW)',data:cumKr,       borderColor:'#E63946',borderWidth:1.2,pointRadius:0,borderDash:[3,2],fill:false}},
      {{label:'🔴 KOSPI(USD)',data:cumKrUsd,    borderColor:'#E63946',borderWidth:1.5,pointRadius:0,fill:false}},
    ]}},
    options:{{...baseOpts,scales:{{...baseOpts.scales,y:{{ticks:{{callback:v=>(v*100).toFixed(0)+'%',font:{{size:10}}}}}}}}}}
  }});
}}
""" if has_fx_data else ""}
// Donut
new Chart('sigChart',{{
  type:'doughnut',
  data:{{
    labels:['🇰🇷 KR ({sig_counts.get("KR",0)})','⚖️ Neutral ({sig_counts.get("Neutral",0)})','🇺🇸 US ({sig_counts.get("US",0)})'],
    datasets:[{{data:[{sig_counts.get("KR",0)},{sig_counts.get("Neutral",0)},{sig_counts.get("US",0)}],backgroundColor:['#E63946','#94A3B8','#1D3557'],borderWidth:0}}]
  }},
  options:{{cutout:'65%',plugins:{{legend:{{position:'bottom',labels:{{font:{{size:11}}}}}}}}}}
}});
</script>
</body>
</html>"""
    return html


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main(date_str: str | None = None) -> None:
    if date_str is None:
        date_str = date.today().isoformat()

    print(f"[sector_rotation] Loading data from {CSV_PATH}")
    pivot = load_pivot()
    macro = load_macro()
    print(f"[sector_rotation] Macro indicators: {len(macro.columns)} series, {len(macro)} rows")

    print("[sector_rotation] Running backtest (6 agents)...")
    bt = run_backtest(pivot, macro=macro)

    if bt.empty:
        print("ERROR: No backtest results — check data availability.")
        return

    # Performance — KRW basis
    metrics = [
        perf_metrics(bt["strategy_return"], "KR/US Rotation (KRW)"),
        perf_metrics(bt["blend_return"],    "50/50 Blend (KRW)"),
        perf_metrics(bt["kr_return"],       "KOSPI (KRW)"),
        perf_metrics(bt["us_return"],       "S&P500 (USD)"),
    ]
    # Performance — USD basis (FX-adjusted)
    has_fx_col = bt["strategy_return_usd"].notna().any()
    if has_fx_col:
        metrics_fx = [
            perf_metrics(bt["strategy_return_usd"].dropna(), "KR/US Rotation (USD)"),
            perf_metrics(bt["blend_return_usd"].dropna(),    "50/50 Blend (USD)"),
            perf_metrics(bt["kr_return_usd"].dropna(),       "KOSPI (USD)"),
            perf_metrics(bt["us_return"],                    "S&P500 (USD)"),
        ]
    else:
        metrics_fx = []

    print(f"[sector_rotation] {len(bt)} months backtested ({bt['as_of'].iloc[0]} ~ {bt['as_of'].iloc[-1]})")
    for m in metrics:
        print(f"  {m['label']:20s}  ann={m['ann_return']*100:.1f}%  sharpe={m['sharpe']:.2f}  mdd={m['mdd']*100:.1f}%")

    # Save signals CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bt_path = OUTPUT_DIR / f"{date_str}_signals.csv"
    bt.to_csv(bt_path, index=False)
    print(f"[sector_rotation] Signals saved → {bt_path}")

    # Build HTML
    html = build_html(bt, metrics, date_str, metrics_fx=metrics_fx)
    html_path = OUTPUT_DIR / f"{date_str}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[sector_rotation] Report saved → {html_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Report date YYYY-MM-DD")
    args = parser.parse_args()
    main(args.date)
