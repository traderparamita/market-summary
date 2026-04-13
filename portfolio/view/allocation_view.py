"""Tactical asset-allocation view — View Agent deliverable.

Current-state allocation view combining:
  1. TAA regime reference (from aimvp)
  2. Market Pulse: VIX, Yield Curve, Breadth, DXY
  3. Asset-class OW/N/UW views (regime-conditional composite)
  4. Individual asset scores (momentum, trend, nearness, vol)

NO backtest. For backtest, see portfolio.aimvp.generate.

Generates standalone HTML report to output/view/allocation/.

Usage:
    python -m portfolio.view.allocation_view --date 2026-04-09 --html
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..aimvp import compute_all_signals, load_monthly_from_csv, score_to_regime
from ..aimvp.model import build_weight_series
from .scoring import load_universe, load_prices, compute_signals

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "allocation"

VIEW_LABELS = {2: "OW+", 1: "OW", 0: "N", -1: "UW", -2: "UW-"}

ASSET_CLASS_ORDER = [
    "equity_us", "equity_dm", "equity_em", "equity_global",
    "ust_long", "ust_mid", "agg_bond", "credit_hy", "credit_ig", "em_debt",
    "gold", "commodity", "usd", "stocks",
]

AC_LABELS = {
    "equity_us":     "US Equity",
    "equity_dm":     "DM Equity",
    "equity_em":     "EM Equity",
    "equity_global": "Global Equity",
    "ust_long":      "UST Long",
    "ust_mid":       "UST Mid",
    "agg_bond":      "Agg Bond",
    "credit_hy":     "High Yield",
    "credit_ig":     "IG Credit",
    "em_debt":       "EM Debt",
    "gold":          "Gold",
    "commodity":     "Commodity",
    "usd":           "USD",
    "stocks":        "Stocks",
}


def _score_to_view(z: float) -> int:
    if z >= 1.0:  return  2
    if z >= 0.3:  return  1
    if z <= -1.0: return -2
    if z <= -0.3: return -1
    return 0


def _fv(val, fmt=".2f", fallback="—"):
    """Format float value or return fallback."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return fallback
    return format(val, fmt)


def compute_allocation_view(date: str, csv_path: str | Path | None = None) -> dict:
    """Compute current-state allocation view: TAA regime + market pulse + asset-class views."""
    monthly = load_monthly_from_csv(csv_path)
    sig_df  = compute_all_signals(monthly["stock"], monthly["bond"], monthly["vix"])

    target    = pd.Timestamp(date)
    available = sig_df.index[sig_df.index <= target]
    if available.empty:
        return {"error": "Insufficient data for TAA signals"}
    last_sig = sig_df.loc[available[-1]]

    taa_score  = int(last_sig["score"])
    taa_regime = score_to_regime(taa_score)

    weight_df    = build_weight_series(sig_df)
    last_weights = weight_df.loc[available[-1]]

    taa_signals = {
        "trend":    int(last_sig["trend"]),
        "momentum": int(last_sig["momentum"]),
        "vix":      int(last_sig["vix"]),
    }
    taa_weights = {
        "stock": float(last_weights["w_stock"]),
        "bond":  float(last_weights["w_bond"]),
        "cash":  float(last_weights["w_cash"]),
    }

    universe     = load_universe()
    prices       = load_prices(csv_path) if csv_path else load_prices()
    asset_scores = compute_signals(prices, date, universe)

    asset_class_views = []
    top_assets        = []
    market_pulse      = {}

    if not asset_scores.empty:
        # ── Market Pulse ─────────────────────────────────────────
        r = asset_scores.iloc[0]

        def _f(col):
            v = r[col]
            return float(v) if not np.isnan(v) else None

        market_pulse = {
            # VIX
            "vix":           _f("macro_vix"),
            "vix_ma20":      _f("macro_vix_ma20"),
            "vix_1m_chg":    _f("macro_vix_1m_chg"),
            "vix_direction": _f("macro_vix_direction"),   # +1=falling, -1=rising
            "vix_regime":    _f("macro_vix_regime"),
            # Yield curve
            "yield_curve":   _f("macro_yc"),
            # Breadth
            "breadth_ma200":  _f("macro_breadth_ma200"),
            "breadth_ma50":   _f("macro_breadth_ma50"),
            "breadth_3m_pos": _f("macro_breadth_3m_pos"),
            # DXY
            "dxy_trend":   "Bullish" if r["macro_dxy_trend"] > 0 else "Bearish",
            "dxy_3m_chg":  _f("macro_dxy_3m_chg"),
            # Price-based regime
            "market_regime": r["market_regime"],
        }

        # ── Asset class views ─────────────────────────────────────
        grouped  = asset_scores.groupby("asset_class")["composite_score"]
        ac_mean  = grouped.mean()
        ac_std   = ac_mean.std()
        ac_z     = (ac_mean - ac_mean.mean()) / ac_std if ac_std > 0 else ac_mean * 0

        for ac in ASSET_CLASS_ORDER:
            if ac not in ac_z.index:
                continue
            z        = float(ac_z[ac])
            view_int = _score_to_view(z)
            asset_class_views.append({
                "class":    ac,
                "view":     VIEW_LABELS[view_int],
                "view_int": view_int,
                "score":    round(z, 2),
                "n_assets": int(grouped.count().get(ac, 0)),
            })

        # ── Individual assets ──────────────────────────────────────
        cols = [
            "etf", "asset_class", "close",
            "mom_12_1", "mom_6_1", "mom_3_1",
            "trend_ma200", "trend_ma50", "nearness_52w",
            "vol_ratio", "composite_score",
        ]
        top_assets = asset_scores[cols].to_dict("records")

    return {
        "date":              date,
        "taa_regime":        taa_regime,
        "taa_score":         taa_score,
        "taa_signals":       taa_signals,
        "taa_weights":       taa_weights,
        "market_pulse":      market_pulse,
        "asset_class_views": asset_class_views,
        "top_assets":        top_assets,
    }


# ── HTML helpers ──────────────────────────────────────────────────

def _signal_badge(name: str, val: int) -> str:
    if val > 0:
        return f'<span class="sig-badge sig-up">▲ {name} +1</span>'
    elif val < 0:
        return f'<span class="sig-badge sig-down">▼ {name} -1</span>'
    return f'<span class="sig-badge sig-neutral">● {name} 0</span>'


def _view_badge(view_str: str) -> str:
    cls = {"OW+": "v-ow2", "OW": "v-ow", "N": "v-n", "UW": "v-uw", "UW-": "v-uw2"}
    return f'<span class="view-badge {cls.get(view_str, "v-n")}">{view_str}</span>'


def _pulse_card(title: str, rows: list[tuple[str, str, str]]) -> str:
    """rows: list of (label, value_html, sub_html)"""
    inner = ""
    for label, val_html, sub in rows:
        inner += f"""
        <div class="pulse-row">
          <span class="pulse-label">{label}</span>
          <span class="pulse-val">{val_html}</span>
          <span class="pulse-sub">{sub}</span>
        </div>"""
    return f"""
    <div class="pulse-card">
      <div class="pulse-title">{title}</div>
      {inner}
    </div>"""


def generate_allocation_html(view: dict) -> str:
    if "error" in view:
        return f"<html><body><h1>Error</h1><p>{view['error']}</p></body></html>"

    report_date = view["date"]
    regime      = view["taa_regime"]
    score       = view["taa_score"]
    signals     = view["taa_signals"]
    weights     = view["taa_weights"]
    pulse       = view.get("market_pulse", {})
    ac_views    = view.get("asset_class_views", [])
    top_assets  = view.get("top_assets", [])

    regime_css  = {"RiskON": "regime-on", "Neutral": "regime-neutral", "RiskOFF": "regime-off"}
    now         = datetime.now().strftime("%Y-%m-%d %H:%M")

    sig_html = " ".join([
        _signal_badge("Trend",    signals["trend"]),
        _signal_badge("Momentum", signals["momentum"]),
        _signal_badge("VIX",      signals["vix"]),
    ])

    # ── Market Pulse cards ────────────────────────────────────────
    vix       = pulse.get("vix")
    vix_ma20  = pulse.get("vix_ma20")
    vix_1m    = pulse.get("vix_1m_chg")
    vix_dir   = pulse.get("vix_direction")
    vix_level_str = _fv(vix, ".1f")
    vix_ma20_str  = f"MA20 {_fv(vix_ma20, '.1f')}"
    vix_1m_str    = f"1M {_fv(vix_1m, '+.1%')}" if vix_1m is not None else ""
    if vix_dir is not None:
        dir_label = '<span class="down">▲ Rising</span>' if vix_dir < 0 else '<span class="up">▼ Falling</span>'
    else:
        dir_label = "—"
    vix_regime_val = pulse.get("vix_regime", 0) or 0
    if vix is not None:
        vix_regime_label = "High" if vix_regime_val < 0 else ("Low" if vix_regime_val > 0 else "Normal")
    else:
        vix_regime_label = "—"

    vix_card = _pulse_card("VIX", [
        ("Level",   f'<b>{vix_level_str}</b>',          vix_ma20_str),
        ("1M Chg",  vix_1m_str or "—",                  dir_label),
        ("Regime",  vix_regime_label,                    ""),
    ])

    yc    = pulse.get("yield_curve")
    yc_str = _fv(yc, "+.2f") + "%" if yc is not None else "—"
    yc_status = ""
    if yc is not None:
        if yc < 0:
            yc_status = '<span class="down">Inverted</span>'
        elif yc < 0.5:
            yc_status = '<span class="neutral">Flat</span>'
        else:
            yc_status = '<span class="up">Normal</span>'

    yc_card = _pulse_card("Yield Curve (10Y-2Y)", [
        ("Spread",  f'<b>{yc_str}</b>',  yc_status),
        ("Signal",  "Caution" if (yc is not None and yc < 0) else "Neutral", ""),
    ])

    bm200     = pulse.get("breadth_ma200")
    bm50      = pulse.get("breadth_ma50")
    b3m       = pulse.get("breadth_3m_pos")
    bm200_str = f"{bm200:.0%}" if bm200 is not None else "—"
    bm50_str  = f"{bm50:.0%}"  if bm50  is not None else "—"
    b3m_str   = f"{b3m:.0%}"   if b3m   is not None else "—"
    breadth_signal = "Weak" if (bm200 is not None and bm200 < 0.4) else (
        "Strong" if (bm200 is not None and bm200 > 0.65) else "Mixed"
    )

    breadth_card = _pulse_card("Market Breadth", [
        ("Above MA200", f'<b>{bm200_str}</b>',  breadth_signal),
        ("Above MA50",  bm50_str,                ""),
        ("3M Positive", b3m_str,                 ""),
    ])

    dxy_trend = pulse.get("dxy_trend", "—")
    dxy_3m    = pulse.get("dxy_3m_chg")
    dxy_3m_str = f"3M {dxy_3m:+.1%}" if dxy_3m is not None else ""
    dxy_trend_html = f'<span class="{"down" if dxy_trend == "Bullish" else "up"}">{dxy_trend}</span>'

    dxy_card = _pulse_card("DXY (US Dollar)", [
        ("Trend",   f'<b>{dxy_trend_html}</b>',  dxy_3m_str),
    ])

    market_regime = pulse.get("market_regime", "—")
    regime_col    = {"RiskON": "up", "RiskOFF": "down", "Neutral": "neutral"}.get(market_regime, "neutral")
    price_regime_html = f'<span class="{regime_col}">Price Regime: <b>{market_regime}</b></span>'

    pulse_html = f"""
    <div class="section">
      <h2>Market Pulse <span class="badge">{report_date}</span>
        <span style="margin-left:12px;font-size:13px">{price_regime_html}</span>
      </h2>
      <div class="pulse-grid">
        {vix_card}
        {yc_card}
        {breadth_card}
        {dxy_card}
      </div>
    </div>"""

    # ── Asset class views ─────────────────────────────────────────
    ac_rows = ""
    for ac in ac_views:
        label = AC_LABELS.get(ac["class"], ac["class"])
        ac_rows += (
            f'<tr>'
            f'<td>{label}</td>'
            f'<td class="center">{_view_badge(ac["view"])}</td>'
            f'<td class="right mono">{ac["score"]:+.2f}</td>'
            f'<td class="right muted">{ac["n_assets"]}</td>'
            f'</tr>'
        )

    # ── Individual asset rows ─────────────────────────────────────
    asset_rows = ""
    for a in top_assets:
        # Trend: show both MA200 and MA50
        t200 = a["trend_ma200"]
        t50  = a["trend_ma50"]
        trend_200 = f'<span class="{"up" if t200 > 0 else "down"}">{"▲" if t200 > 0 else "▼"}200</span>'
        trend_50  = f'<span class="{"up" if t50  > 0 else "down"}">{"▲" if t50  > 0 else "▼"}50</span>'

        def _pct(v):
            return f'{v:.1%}' if v == v else "—"

        nearness = a["nearness_52w"]
        near_str = f'{nearness:.0%}' if nearness == nearness else "—"
        near_cls = "up" if (nearness == nearness and nearness > 0.95) else (
            "down" if (nearness == nearness and nearness < 0.80) else ""
        )

        vr = a["vol_ratio"]
        vr_str = f'{vr:.2f}x' if vr == vr else "—"
        vr_cls = "down" if (vr == vr and vr > 1.3) else ("up" if (vr == vr and vr < 0.8) else "")

        sc     = a["composite_score"]
        sc_cls = "up" if sc > 0.3 else ("down" if sc < -0.3 else "")

        asset_rows += (
            f'<tr>'
            f'<td class="mono">{a["etf"]}</td>'
            f'<td class="muted">{AC_LABELS.get(a["asset_class"], a["asset_class"])}</td>'
            f'<td class="right mono">{a["close"]:.2f}</td>'
            f'<td class="right mono">{_pct(a["mom_12_1"])}</td>'
            f'<td class="right mono">{_pct(a["mom_6_1"])}</td>'
            f'<td class="right mono">{_pct(a["mom_3_1"])}</td>'
            f'<td class="center">{trend_200}&nbsp;{trend_50}</td>'
            f'<td class="right mono {near_cls}">{near_str}</td>'
            f'<td class="right mono {vr_cls}">{vr_str}</td>'
            f'<td class="right mono {sc_cls}">{sc:+.3f}</td>'
            f'</tr>'
        )

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tactical Asset Allocation View | {report_date}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --border:#e0e3ed; --text:#2d3148; --muted:#7c8298;
  --up:#0d9b6a; --down:#d9304f; --primary:#3b6ee6;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans KR',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.65;padding:28px 24px;max-width:1300px;margin:0 auto}}
.mono{{font-family:'JetBrains Mono',monospace}}
.muted{{color:var(--muted)}}
.up{{color:var(--up)}}.down{{color:var(--down)}}.neutral{{color:var(--muted)}}
.center{{text-align:center}}.right{{text-align:right}}

.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:24px;padding-bottom:18px;border-bottom:2px solid var(--border)}}
.header h1{{font-size:23px;font-weight:700;color:#1a1d2e}}
.header .meta{{font-size:12px;color:var(--muted);margin-top:3px}}
.regime-tag{{display:inline-block;padding:4px 14px;border-radius:8px;font-size:14px;font-weight:700;margin-bottom:6px}}
.regime-on{{background:#ecfdf5;color:#059669;border:1px solid #05966933}}
.regime-neutral{{background:#fffbeb;color:#d97706;border:1px solid #d9770633}}
.regime-off{{background:#fef2f2;color:#dc2626;border:1px solid #dc262633}}

.signal-row{{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:20px}}
.sig-badges{{display:flex;gap:6px}}
.sig-badge{{padding:4px 10px;border-radius:6px;font-weight:600;font-size:12px}}
.sig-up{{background:#ecfdf5;color:#059669}}
.sig-down{{background:#fef2f2;color:#dc2626}}
.sig-neutral{{background:#f3f4f6;color:#6b7280}}

.weight-pills{{display:flex;gap:6px}}
.pill{{padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600}}
.pill-stock{{background:#dbeafe;color:#1d4ed8}}
.pill-bond{{background:#fce7f3;color:#be185d}}
.pill-cash{{background:#d1fae5;color:#065f46}}

.section{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px 24px;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.05)}}
.section h2{{font-size:15px;font-weight:600;color:#1a1d2e;margin-bottom:16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.badge{{font-size:11px;padding:2px 8px;border-radius:10px;background:#f0f1f6;color:var(--muted);font-weight:500}}

/* Market Pulse grid */
.pulse-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}}
.pulse-card{{background:#f8fafc;border:1px solid var(--border);border-radius:10px;padding:14px 16px}}
.pulse-title{{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}}
.pulse-row{{display:flex;align-items:baseline;gap:6px;margin-bottom:5px}}
.pulse-label{{font-size:11px;color:var(--muted);min-width:72px;flex-shrink:0}}
.pulse-val{{font-size:14px;font-weight:700;font-family:'JetBrains Mono',monospace;color:#1a1d2e}}
.pulse-sub{{font-size:11px;color:var(--muted)}}

.view-badge{{padding:2px 10px;border-radius:4px;font-weight:600;font-size:12px}}
.v-ow2{{background:#ecfdf5;color:#059669}}
.v-ow{{background:#d1fae5;color:#047857}}
.v-n{{background:#f3f4f6;color:#6b7280}}
.v-uw{{background:#fef3c7;color:#d97706}}
.v-uw2{{background:#fef2f2;color:#dc2626}}

.inner-table{{width:100%;border-collapse:collapse;font-size:13px}}
.inner-table thead tr{{background:#f8fafc;border-bottom:1px solid var(--border)}}
.inner-table th{{padding:8px 10px;font-size:11px;color:var(--muted);font-weight:600}}
.inner-table td{{padding:7px 10px;border-bottom:1px solid #f1f5f9}}
.inner-table tbody tr:hover{{background:#f8fafc}}

.footer{{text-align:center;font-size:11px;color:#94a3b8;padding:16px 0 4px}}
.back-link{{display:inline-block;margin-bottom:16px;font-size:13px;color:var(--primary);text-decoration:none}}
.back-link:hover{{text-decoration:underline}}

@media(max-width:768px){{
  .pulse-grid{{grid-template-columns:repeat(2,1fr)}}
}}
@media(max-width:480px){{
  .pulse-grid{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>

<a class="back-link" href="../../index.html">← Back to Index</a>

<div class="header">
  <div>
    <h1>Tactical Asset Allocation View</h1>
    <div class="meta">Price-based signals | View Agent</div>
  </div>
  <div style="text-align:right">
    <div class="regime-tag {regime_css.get(regime, "regime-neutral")}">TAA: {regime} ({score:+d})</div>
    <div style="font-size:11px;color:var(--muted);margin-top:4px">Generated: {now}</div>
  </div>
</div>

<div class="signal-row">
  <div class="sig-badges">{sig_html}</div>
  <div class="weight-pills">
    <span class="pill pill-stock">Stock {weights["stock"]:.0%}</span>
    <span class="pill pill-bond">Bond {weights["bond"]:.0%}</span>
    <span class="pill pill-cash">Cash {weights["cash"]:.0%}</span>
  </div>
</div>

{pulse_html}

<div class="section">
  <h2>Asset Class Views <span class="badge">{report_date}</span></h2>
  <table class="inner-table">
    <thead><tr>
      <th style="text-align:left">Asset Class</th>
      <th>View</th>
      <th style="text-align:right">Z-Score</th>
      <th style="text-align:right">Assets</th>
    </tr></thead>
    <tbody>{ac_rows}</tbody>
  </table>
</div>

<div class="section">
  <h2>Individual Asset Scores <span class="badge">{report_date}</span></h2>
  <div style="overflow-x:auto">
  <table class="inner-table">
    <thead><tr>
      <th style="text-align:left">Ticker</th>
      <th style="text-align:left">Class</th>
      <th style="text-align:right">Close</th>
      <th style="text-align:right">Mom 12M</th>
      <th style="text-align:right">Mom 6M</th>
      <th style="text-align:right">Mom 3M</th>
      <th style="text-align:center">Trend</th>
      <th style="text-align:right">52W Hi%</th>
      <th style="text-align:right">Vol Ratio</th>
      <th style="text-align:right">Score</th>
    </tr></thead>
    <tbody>{asset_rows}</tbody>
  </table>
  </div>
</div>

<div class="footer">Tactical Asset Allocation View | Price-based regime-conditional signals | View Agent</div>

</body>
</html>'''


def generate_report(date: str, csv_path: str | Path | None = None) -> str:
    """Generate allocation view HTML report."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    view = compute_allocation_view(date, csv_path)
    html = generate_allocation_html(view)

    out_path = OUTPUT_DIR / f"{date}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Tactical asset-allocation view")
    parser.add_argument("--date",  required=True)
    parser.add_argument("--html",  action="store_true", help="Generate HTML report")
    parser.add_argument("--csv",   default=None, help="Override CSV path")
    args = parser.parse_args()

    if args.html:
        path = generate_report(args.date, args.csv)
        print(f"HTML report: {path}")
        return

    view = compute_allocation_view(args.date, args.csv)

    if "error" in view:
        print(f"Error: {view['error']}")
        sys.exit(1)

    pulse = view["market_pulse"]
    print(f"\n{'='*60}")
    print(f"  Allocation View as of {view['date']}")
    print(f"{'='*60}")
    print(f"  TAA Regime     : {view['taa_regime']}  (score: {view['taa_score']:+d}/3)")
    print(f"  Price Regime   : {pulse.get('market_regime', '—')}")
    print(f"  Signals        : Trend={view['taa_signals']['trend']:+d}  "
          f"Momentum={view['taa_signals']['momentum']:+d}  VIX={view['taa_signals']['vix']:+d}")
    print(f"  Weights        : Stock={view['taa_weights']['stock']:.0%}  "
          f"Bond={view['taa_weights']['bond']:.0%}  Cash={view['taa_weights']['cash']:.0%}")

    vix = pulse.get("vix")
    yc  = pulse.get("yield_curve")
    bm  = pulse.get("breadth_ma200")
    print(f"\n  Market Pulse:")
    if vix: print(f"    VIX          : {vix:.1f}  ({('Rising' if (pulse.get('vix_direction') or 0) < 0 else 'Falling')})")
    if yc:  print(f"    Yield Curve  : {yc:+.2f}%  ({'Inverted' if yc < 0 else 'Normal'})")
    if bm:  print(f"    Breadth MA200: {bm:.0%}  ({'Weak' if bm < 0.4 else 'Strong' if bm > 0.65 else 'Mixed'})")

    print(f"\n  {'Asset Class':<18s} {'View':>5s}  {'Z-Score':>8s}")
    print(f"  {'-'*35}")
    for ac in view["asset_class_views"]:
        label = AC_LABELS.get(ac["class"], ac["class"])
        print(f"  {label:<18s} {ac['view']:>5s}  {ac['score']:>+8.2f}")
    print()


if __name__ == "__main__":
    main()
