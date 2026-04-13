"""Tactical asset-allocation view — View Agent deliverable.

Current-state allocation view combining:
  1. TAA regime reference (from aimvp)
  2. Asset-class OW/N/UW views
  3. Individual asset scores

NO backtest. For backtest, see portfolio.aimvp.generate.

Generates standalone HTML report to output/view/allocation/.

Usage:
    python -m portfolio.view.allocation_view --date 2026-04-09 --html
"""

import argparse
import json
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
    "equity_us": "US Equity", "equity_dm": "DM Equity", "equity_em": "EM Equity",
    "equity_global": "Global Equity",
    "ust_long": "UST Long", "ust_mid": "UST Mid", "agg_bond": "Agg Bond",
    "credit_hy": "High Yield", "credit_ig": "IG Credit", "em_debt": "EM Debt",
    "gold": "Gold", "commodity": "Commodity", "usd": "USD", "stocks": "Stocks",
}


def _score_to_view(z: float) -> int:
    if z >= 1.0:
        return 2
    if z >= 0.3:
        return 1
    if z <= -1.0:
        return -2
    if z <= -0.3:
        return -1
    return 0


def compute_allocation_view(date: str, csv_path: str | Path | None = None) -> dict:
    """Compute current-state macro view: TAA regime + asset-class views."""
    monthly = load_monthly_from_csv(csv_path)
    sig_df = compute_all_signals(monthly["stock"], monthly["bond"], monthly["vix"])

    target = pd.Timestamp(date)
    available = sig_df.index[sig_df.index <= target]
    if available.empty:
        return {"error": "Insufficient data for TAA signals"}
    last_sig = sig_df.loc[available[-1]]

    taa_score = int(last_sig["score"])
    taa_regime = score_to_regime(taa_score)

    weight_df = build_weight_series(sig_df)
    last_weights = weight_df.loc[available[-1]]

    taa_signals = {
        "trend": int(last_sig["trend"]),
        "momentum": int(last_sig["momentum"]),
        "vix": int(last_sig["vix"]),
    }
    taa_weights = {
        "stock": float(last_weights["w_stock"]),
        "bond": float(last_weights["w_bond"]),
        "cash": float(last_weights["w_cash"]),
    }

    universe = load_universe()
    prices = load_prices(csv_path) if csv_path else load_prices()
    asset_scores = compute_signals(prices, date, universe)

    asset_class_views = []
    top_assets = []
    if not asset_scores.empty:
        grouped = asset_scores.groupby("asset_class")["composite_score"]
        ac_mean = grouped.mean()
        ac_std = ac_mean.std()
        ac_z = (ac_mean - ac_mean.mean()) / ac_std if ac_std > 0 else ac_mean * 0

        for ac in ASSET_CLASS_ORDER:
            if ac not in ac_z.index:
                continue
            z = float(ac_z[ac])
            view_int = _score_to_view(z)
            asset_class_views.append({
                "class": ac,
                "view": VIEW_LABELS[view_int],
                "view_int": view_int,
                "score": round(z, 2),
                "n_assets": int(grouped.count().get(ac, 0)),
            })

        cols = ["etf", "asset_class", "close", "mom_12_1", "mom_6_1",
                "trend_ma200", "vol_20d", "composite_score"]
        top_assets = asset_scores[cols].to_dict("records")

    macro_ctx = {}
    if not asset_scores.empty:
        row = asset_scores.iloc[0]
        macro_ctx = {
            "yield_curve": float(row["macro_yc"]) if not np.isnan(row["macro_yc"]) else None,
            "vix": float(row["macro_vix"]) if not np.isnan(row["macro_vix"]) else None,
            "dxy_trend": "Bullish" if row["macro_dxy_trend"] > 0 else "Bearish",
        }

    return {
        "date": date,
        "taa_regime": taa_regime,
        "taa_score": taa_score,
        "taa_signals": taa_signals,
        "taa_weights": taa_weights,
        "asset_class_views": asset_class_views,
        "top_assets": top_assets,
        "macro_context": macro_ctx,
    }


# ── HTML Generation ───────────────────────────────────────────────

def _signal_badge(name: str, val: int) -> str:
    if val > 0:
        return f'<span class="sig-badge sig-up">▲ {name} +1</span>'
    elif val < 0:
        return f'<span class="sig-badge sig-down">▼ {name} -1</span>'
    return f'<span class="sig-badge sig-neutral">● {name} 0</span>'


def _view_badge(view_str: str) -> str:
    cls = {"OW+": "v-ow2", "OW": "v-ow", "N": "v-n", "UW": "v-uw", "UW-": "v-uw2"}
    return f'<span class="view-badge {cls.get(view_str, "v-n")}">{view_str}</span>'


def generate_allocation_html(view: dict) -> str:
    """Generate macro view HTML (current state only, no backtest)."""
    if "error" in view:
        return f"<html><body><h1>Error</h1><p>{view['error']}</p></body></html>"

    report_date = view["date"]
    regime = view["taa_regime"]
    score = view["taa_score"]
    signals = view["taa_signals"]
    weights = view["taa_weights"]
    ac_views = view.get("asset_class_views", [])
    top_assets = view.get("top_assets", [])
    macro_ctx = view.get("macro_context", {})

    regime_css = {"RiskON": "regime-on", "Neutral": "regime-neutral", "RiskOFF": "regime-off"}

    sig_html = " ".join([
        _signal_badge("Trend", signals["trend"]),
        _signal_badge("Momentum", signals["momentum"]),
        _signal_badge("VIX", signals["vix"]),
    ])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Asset class views section
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

    # Individual asset scores section
    asset_rows = ""
    for a in top_assets:
        trend_icon = "▲" if a["trend_ma200"] > 0 else "▼"
        trend_cls = "up" if a["trend_ma200"] > 0 else "down"
        mom12 = f'{a["mom_12_1"]:.1%}' if a["mom_12_1"] == a["mom_12_1"] else "—"
        mom6 = f'{a["mom_6_1"]:.1%}' if a["mom_6_1"] == a["mom_6_1"] else "—"
        vol = f'{a["vol_20d"]:.1%}' if a["vol_20d"] == a["vol_20d"] else "—"
        sc = a["composite_score"]
        sc_cls = "up" if sc > 0.3 else ("down" if sc < -0.3 else "")
        asset_rows += (
            f'<tr>'
            f'<td class="mono">{a["etf"]}</td>'
            f'<td class="muted">{AC_LABELS.get(a["asset_class"], a["asset_class"])}</td>'
            f'<td class="right mono">{a["close"]:.2f}</td>'
            f'<td class="right mono">{mom12}</td>'
            f'<td class="right mono">{mom6}</td>'
            f'<td class="center {trend_cls}">{trend_icon}</td>'
            f'<td class="right mono">{vol}</td>'
            f'<td class="right mono {sc_cls}">{sc:+.3f}</td>'
            f'</tr>'
        )

    # Macro context section
    yc_val = f"{macro_ctx['yield_curve']:.2f} bps" if macro_ctx.get("yield_curve") else "—"
    vix_val = f"{macro_ctx['vix']:.1f}" if macro_ctx.get("vix") else "—"
    dxy_val = macro_ctx.get("dxy_trend", "—")

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
  --up:#0d9b6a; --down:#d9304f;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans KR',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.65;padding:28px 24px;max-width:1200px;margin:0 auto}}
.mono{{font-family:'JetBrains Mono',monospace}}
.muted{{color:var(--muted)}}
.up{{color:var(--up)}}.down{{color:var(--down)}}
.center{{text-align:center}}.right{{text-align:right}}

.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:24px;padding-bottom:18px;border-bottom:2px solid var(--border)}}
.header h1{{font-size:23px;font-weight:700;color:#1a1d2e}}
.header .meta{{font-size:12px;color:var(--muted);margin-top:3px}}
.header .gen{{font-size:12px;color:var(--muted);text-align:right}}
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
.section h2{{font-size:15px;font-weight:600;color:#1a1d2e;margin-bottom:16px;display:flex;align-items:center;gap:8px}}
.badge{{font-size:11px;padding:2px 8px;border-radius:10px;background:#f0f1f6;color:var(--muted);font-weight:500}}

.view-badge{{padding:2px 10px;border-radius:4px;font-weight:600;font-size:12px}}
.v-ow2{{background:#ecfdf5;color:#059669}}
.v-ow{{background:#d1fae5;color:#047857}}
.v-n{{background:#f3f4f6;color:#6b7280}}
.v-uw{{background:#fef3c7;color:#d97706}}
.v-uw2{{background:#fef2f2;color:#dc2626}}

.inner-table{{width:100%;border-collapse:collapse;font-size:13px}}
.inner-table thead tr{{background:#f8fafc;border-bottom:1px solid var(--border)}}
.inner-table th{{padding:8px 12px;font-size:12px;color:var(--muted);font-weight:600}}
.inner-table td{{padding:7px 12px;border-bottom:1px solid #f1f5f9}}
.inner-table tbody tr:hover{{background:#f8fafc}}

.macro-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:12px}}
.macro-item{{background:#f8fafc;border-radius:10px;padding:12px 14px}}
.macro-label{{font-size:10px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px}}
.macro-value{{font-size:16px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}

.footer{{text-align:center;font-size:11px;color:#94a3b8;padding:16px 0 4px}}
.back-link{{display:inline-block;margin-bottom:16px;font-size:13px;color:#3b6ee6;text-decoration:none}}
.back-link:hover{{text-decoration:underline}}

@media(max-width:768px){{
  .macro-grid{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>

<a class="back-link" href="../../index.html">← Back to Index</a>

<div class="header">
  <div>
    <h1>Tactical Asset Allocation View</h1>
    <div class="meta">Current-state allocation view | View Agent</div>
  </div>
  <div class="gen">
    <div class="regime-tag {regime_css.get(regime, "regime-neutral")}">TAA: {regime} ({score:+d})</div>
    <div style="margin-top:4px">Generated: {now}</div>
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

<div class="section">
  <h2>Macro Context <span class="badge">{report_date}</span></h2>
  <div class="macro-grid">
    <div class="macro-item">
      <div class="macro-label">Yield Curve (10Y-2Y)</div>
      <div class="macro-value">{yc_val}</div>
    </div>
    <div class="macro-item">
      <div class="macro-label">VIX</div>
      <div class="macro-value">{vix_val}</div>
    </div>
    <div class="macro-item">
      <div class="macro-label">DXY Trend</div>
      <div class="macro-value">{dxy_val}</div>
    </div>
  </div>
</div>

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
      <th style="text-align:right">Mom 12-1</th>
      <th style="text-align:right">Mom 6-1</th>
      <th>Trend</th>
      <th style="text-align:right">Vol 20d</th>
      <th style="text-align:right">Score</th>
    </tr></thead>
    <tbody>{asset_rows}</tbody>
  </table>
  </div>
</div>

<div class="footer">Tactical Asset Allocation View | TAA Regime Reference + Asset-Class Views | View Agent</div>

</body>
</html>'''


def generate_report(date: str, csv_path: str | Path | None = None) -> str:
    """Generate macro view HTML report."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    view = compute_allocation_view(date, csv_path)
    html = generate_allocation_html(view)

    out_path = OUTPUT_DIR / f"{date}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Tactical asset-allocation view")
    parser.add_argument("--date", required=True)
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    args = parser.parse_args()

    if args.html:
        path = generate_report(args.date)
        print(f"HTML report: {path}")
        return

    view = compute_allocation_view(args.date)

    if "error" in view:
        print(f"Error: {view['error']}")
        sys.exit(1)

    print(f"\n{'='*55}")
    print(f"  Allocation View as of {view['date']}")
    print(f"{'='*55}")
    print(f"  TAA Regime: {view['taa_regime']}  (score: {view['taa_score']:+d}/3)")
    print(f"  Signals:    Trend={view['taa_signals']['trend']:+d}  "
          f"Momentum={view['taa_signals']['momentum']:+d}  "
          f"VIX={view['taa_signals']['vix']:+d}")
    print(f"  Weights:    Stock={view['taa_weights']['stock']:.0%}  "
          f"Bond={view['taa_weights']['bond']:.0%}  "
          f"Cash={view['taa_weights']['cash']:.0%}")
    print(f"{'='*55}")

    if view["asset_class_views"]:
        print(f"\n  {'Asset Class':<18s} {'View':>5s}  {'Z-Score':>8s}")
        print(f"  {'-'*35}")
        for ac in view["asset_class_views"]:
            label = ac["class"].replace("_", " ").title()
            print(f"  {label:<18s} {ac['view']:>5s}  {ac['score']:>+8.2f}")
    print()


if __name__ == "__main__":
    main()
