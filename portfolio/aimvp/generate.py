"""AIMVP RiskOn strategy backtest report generator.

Full backtest with monthly returns heatmap, performance metrics, charts.

Generates to output/aimvp/.

Usage:
    python -m portfolio.aimvp.generate --date 2026-04-09
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import compute_all_signals, load_monthly_from_csv, score_to_regime
from .model import build_weight_series
from .config import (
    STOCK_CODE, BOND_CODE, CASH_CODE,
    ALLOC_RISK_ON, ALLOC_NEUTRAL, ALLOC_RISK_OFF,
    RISK_ON_THRESHOLD, RISK_OFF_THRESHOLD,
    TREND_WINDOW, MOMENTUM_WINDOW, VIX_LOW, VIX_HIGH,
)

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "portfolio" / "aimvp"


def _calc_monthly_metrics(returns: pd.Series) -> dict:
    cum = (1 + returns).cumprod()
    n_years = len(returns) / 12
    cagr = (cum.iloc[-1] ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
    rolling_max = cum.cummax()
    mdd = ((cum - rolling_max) / rolling_max).min() * 100
    sharpe = (returns.mean() / returns.std()) * (12 ** 0.5) if returns.std() > 0 else 0
    hit_rate = (returns > 0).mean() * 100
    return {
        "cagr": round(cagr, 2),
        "mdd": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "hit_rate": round(hit_rate, 1),
    }


def _monthly_returns_matrix(returns: pd.Series) -> dict:
    df = returns.copy()
    df.index = pd.to_datetime(df.index)
    matrix = {}
    for year, grp in df.groupby(df.index.year):
        matrix[int(year)] = {}
        for month, val in grp.groupby(grp.index.month):
            matrix[int(year)][int(month)] = round(float(val.iloc[-1]) * 100, 2)
    return matrix


def _monthly_signal_matrix(series: pd.Series) -> dict:
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    matrix = {}
    for year, grp in s.groupby(s.index.year):
        matrix[int(year)] = {}
        for month, val in grp.groupby(grp.index.month):
            v = val.iloc[-1]
            matrix[int(year)][int(month)] = (
                None if (v is None or (isinstance(v, float) and pd.isna(v))) else v
            )
    return matrix


def _drawdown_series(returns: pd.Series) -> list[float]:
    cum = (1 + returns).cumprod()
    dd = ((cum - cum.cummax()) / cum.cummax()) * 100
    return [round(v, 3) for v in dd.tolist()]


def _make_heatmap_html(matrix, neutral_matrix=None, signal_matrix=None) -> str:
    def _bg(val):
        if val is None:
            return "background:#f4f5f9", "#aaa"
        intensity = min(abs(val) / 6, 1)
        if val > 0:
            r = int(255 - intensity * (255 - 13))
            g = int(255 - intensity * (255 - 155))
            b = int(255 - intensity * (255 - 106))
        else:
            r = int(255 - intensity * (255 - 217))
            g = int(255 - intensity * (255 - 48))
            b = int(255 - intensity * (255 - 79))
        fg = "#fff" if intensity > 0.5 else "#1a1d2e"
        return f"background:rgb({r},{g},{b})", fg

    SIG_STYLE = {
        "ON":  "background:#3b6ee6;color:#fff",
        "N":   "background:#d1d5db;color:#374151",
        "OFF": "background:#d9304f;color:#fff",
    }

    rows = ""
    for year in sorted(matrix.keys(), reverse=True):
        year_vals = [matrix[year].get(m) for m in range(1, 13)]
        year_excesses: list[float] = []
        win_count = 0
        month_count = 0
        cells = ""

        for m_idx, v in enumerate(year_vals):
            month = m_idx + 1
            bg, fg = _bg(v)

            sig = (signal_matrix or {}).get(year, {}).get(month)
            sig_html = ""
            if sig:
                sig_html = (
                    f'<span style="{SIG_STYLE.get(sig, "")};font-size:8px;'
                    f'padding:1px 4px;border-radius:3px;font-weight:700">{sig}</span>'
                )

            excess_html = ""
            if neutral_matrix is not None and v is not None:
                n = (neutral_matrix.get(year) or {}).get(month)
                if n is not None:
                    exc = round(v - n, 2)
                    year_excesses.append(exc)
                    month_count += 1
                    if exc > 0:
                        win_count += 1
                    ec = "#0d9b6a" if exc >= 0 else "#d9304f"
                    ar = "▲" if exc >= 0 else "▼"
                    excess_html = (
                        f'<span style="color:{ec};font-size:10px;'
                        f'font-family:JetBrains Mono,monospace">'
                        f'{ar}{abs(exc):.1f}</span>'
                    )

            main_txt = f"{v:+.1f}%" if v is not None else "—"
            cell_inner = (
                f'<div style="font-size:12px;font-weight:700;'
                f'font-family:JetBrains Mono,monospace">{main_txt}</div>'
                f'<div style="display:flex;align-items:center;justify-content:flex-end;'
                f'gap:3px;margin-top:2px">{sig_html}{excess_html}</div>'
            )
            cells += (
                f'<td style="{bg};color:{fg};padding:5px 8px;'
                f'text-align:right;min-width:68px">{cell_inner}</td>'
            )

        year_total = sum(v for v in year_vals if v is not None)
        bg_t, fg_t = _bg(year_total)
        cells += (
            f'<td style="{bg_t};color:{fg_t};padding:5px 8px;text-align:right;'
            f'font-family:JetBrains Mono,monospace;font-size:12px;font-weight:700;'
            f'border-left:2px solid #e0e3ed;white-space:nowrap">{year_total:+.1f}%</td>'
        )

        if month_count > 0 and neutral_matrix is not None:
            wr = win_count / month_count * 100
            wc = "#0d9b6a" if wr >= 50 else "#d9304f"
            win_html = (
                f'<span style="color:{wc};font-weight:700;font-size:12px;'
                f'font-family:JetBrains Mono,monospace">{win_count}/{month_count}</span>'
                f'<br><span style="color:{wc};font-size:10px">{wr:.0f}%</span>'
            )
        else:
            win_html = "—"
        cells += (
            f'<td style="padding:5px 10px;text-align:center;'
            f'border-left:1px solid #e0e3ed">{win_html}</td>'
        )

        if year_excesses and neutral_matrix is not None:
            wins = [e for e in year_excesses if e > 0]
            losses = [e for e in year_excesses if e < 0]
            if wins and losses:
                plr = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
                rc = "#0d9b6a" if plr >= 1 else "#d9304f"
                plr_html = (
                    f'<span style="color:{rc};font-weight:700;font-size:12px;'
                    f'font-family:JetBrains Mono,monospace">{plr:.2f}x</span>'
                )
            elif wins:
                plr_html = '<span style="color:#0d9b6a;font-weight:700">∞</span>'
            else:
                plr_html = '<span style="color:#d9304f;font-weight:700;font-size:12px">0.00x</span>'
        else:
            plr_html = "—"
        cells += f'<td style="padding:5px 10px;text-align:center">{plr_html}</td>'

        rows += (
            f"<tr><td style='padding:5px 12px;font-weight:600;font-size:13px;"
            f"white-space:nowrap;color:#1a1d2e'>{year}</td>{cells}</tr>"
        )

    return rows


def _compute_backtest_data(csv_path=None) -> dict:
    """Run AIMVP monthly backtest and return all data."""
    monthly = load_monthly_from_csv(csv_path)
    sig_df = compute_all_signals(monthly["stock"], monthly["bond"], monthly["vix"])
    weight_df = build_weight_series(sig_df)

    stock_ret = monthly["stock"].pct_change().dropna()
    bond_ret = monthly["bond"].pct_change().dropna()
    cash_ret = monthly["cash"].pct_change().dropna()

    w_shifted = weight_df.shift(1).dropna()
    common = (
        stock_ret.index
        .intersection(bond_ret.index)
        .intersection(cash_ret.index)
        .intersection(w_shifted.index)
    )

    stock_ret = stock_ret.loc[common]
    bond_ret = bond_ret.loc[common]
    cash_ret = cash_ret.loc[common]
    ws = w_shifted.loc[common]

    dynamic_ret = (
        stock_ret * ws["w_stock"]
        + bond_ret * ws["w_bond"]
        + cash_ret * ws["w_cash"]
    )
    bench_75_25 = stock_ret * 0.75 + bond_ret * 0.25
    bench_60_40 = stock_ret * 0.60 + bond_ret * 0.40

    labels = [d.strftime("%Y-%m") for d in common]

    shifted_score = sig_df["score"].shift(1)

    def _s(v):
        if pd.isna(v):
            return None
        v = int(v)
        if v >= RISK_ON_THRESHOLD:
            return "ON"
        if v <= RISK_OFF_THRESHOLD:
            return "OFF"
        return "N"

    sig_matrix = _monthly_signal_matrix(shifted_score.map(_s))

    dynamic_matrix = _monthly_returns_matrix(dynamic_ret)
    bench75_matrix = _monthly_returns_matrix(bench_75_25)
    heatmap_html = _make_heatmap_html(dynamic_matrix, bench75_matrix, sig_matrix)

    return {
        "labels": labels,
        "cum_dynamic": [round(v, 4) for v in (1 + dynamic_ret).cumprod().tolist()],
        "cum_75_25": [round(v, 4) for v in (1 + bench_75_25).cumprod().tolist()],
        "cum_60_40": [round(v, 4) for v in (1 + bench_60_40).cumprod().tolist()],
        "cum_stock": [round(v, 4) for v in (1 + stock_ret).cumprod().tolist()],
        "cum_bond": [round(v, 4) for v in (1 + bond_ret).cumprod().tolist()],
        "dd_dynamic": _drawdown_series(dynamic_ret),
        "dd_75_25": _drawdown_series(bench_75_25),
        "dd_stock": _drawdown_series(stock_ret),
        "w_stock": [round(float(v) * 100, 1) for v in ws["w_stock"]],
        "w_bond": [round(float(v) * 100, 1) for v in ws["w_bond"]],
        "w_cash": [round(float(v) * 100, 1) for v in ws["w_cash"]],
        "avg_stock_weight": round(ws["w_stock"].mean() * 100, 1),
        "m_dynamic": _calc_monthly_metrics(dynamic_ret),
        "m_75_25": _calc_monthly_metrics(bench_75_25),
        "m_60_40": _calc_monthly_metrics(bench_60_40),
        "m_stock": _calc_monthly_metrics(stock_ret),
        "m_bond": _calc_monthly_metrics(bond_ret),
        "heatmap_html": heatmap_html,
        "period_start": labels[0] if labels else "",
        "period_end": labels[-1] if labels else "",
    }


def _signal_badge(name: str, val: int) -> str:
    if val > 0:
        return f'<span class="sig-badge sig-up">▲ {name} +1</span>'
    elif val < 0:
        return f'<span class="sig-badge sig-down">▼ {name} -1</span>'
    return f'<span class="sig-badge sig-neutral">● {name} 0</span>'


def generate_report(date: str, csv_path: str | Path | None = None) -> str:
    """Generate AIMVP backtest HTML report."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    monthly = load_monthly_from_csv(csv_path)
    sig_df = compute_all_signals(monthly["stock"], monthly["bond"], monthly["vix"])
    weight_df = build_weight_series(sig_df)

    target = pd.Timestamp(date)
    available = sig_df.index[sig_df.index <= target]
    if available.empty:
        return ""

    last_sig = sig_df.loc[available[-1]]
    last_weights = weight_df.loc[available[-1]]

    taa_score = int(last_sig["score"])
    taa_regime = score_to_regime(taa_score)

    signals = {
        "trend": int(last_sig["trend"]),
        "momentum": int(last_sig["momentum"]),
        "vix": int(last_sig["vix"]),
    }
    weights = {
        "stock": float(last_weights["w_stock"]),
        "bond": float(last_weights["w_bond"]),
        "cash": float(last_weights["w_cash"]),
    }

    backtest = _compute_backtest_data(csv_path)
    html = _render_html(date, taa_regime, taa_score, signals, weights, backtest)

    out_path = OUTPUT_DIR / f"{date}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(out_path)


def _render_html(date: str, regime: str, score: int, signals: dict, weights: dict, bt: dict) -> str:
    """Render AIMVP backtest HTML."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    regime_css = {"RiskON": "regime-on", "Neutral": "regime-neutral", "RiskOFF": "regime-off"}

    sig_html = " ".join([
        _signal_badge("Trend", signals["trend"]),
        _signal_badge("Momentum", signals["momentum"]),
        _signal_badge("VIX", signals["vix"]),
    ])

    month_headers = "".join(
        f"<th>{m}</th>" for m in [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
    )

    chart_data = json.dumps({
        "labels": bt["labels"],
        "cumDynamic": bt["cum_dynamic"],
        "cum7525": bt["cum_75_25"],
        "cum6040": bt["cum_60_40"],
        "cumStock": bt["cum_stock"],
        "cumBond": bt["cum_bond"],
        "ddDynamic": bt["dd_dynamic"],
        "dd7525": bt["dd_75_25"],
        "ddStock": bt["dd_stock"],
        "wStock": bt["w_stock"],
        "wBond": bt["w_bond"],
        "wCash": bt["w_cash"],
    }, ensure_ascii=False)

    m_d = bt["m_dynamic"]
    m_75 = bt["m_75_25"]
    m_60 = bt["m_60_40"]
    m_st = bt["m_stock"]
    m_bd = bt["m_bond"]

    def _row(name, m, highlight=False):
        cls = ' class="hl"' if highlight else ''
        cu = "up" if m["cagr"] >= 0 else "down"
        return (
            f'<tr{cls}>'
            f'<td>{name}</td>'
            f'<td class="{cu}">{m["cagr"]:+.2f}%</td>'
            f'<td class="down">{m["mdd"]:.2f}%</td>'
            f'<td>{m["sharpe"]:.2f}</td>'
            f'<td>{m["hit_rate"]:.1f}%</td>'
            f'</tr>'
        )

    perf_rows = (
        _row("AIMVP Dynamic TAA (30bp)", m_d, highlight=True)
        + _row("75/25 Fixed", m_75)
        + _row("60/40 Fixed", m_60)
        + _row("ACWI 100%", m_st)
        + _row("AGG 100%", m_bd)
    )

    d_cagr_cls = "up" if m_d["cagr"] >= 0 else "down"
    b_cagr_cls = "up" if m_75["cagr"] >= 0 else "down"

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIMVP RiskOn | {bt["period_start"]} ~ {bt["period_end"]}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --card2:#f0f1f6;
  --border:#e0e3ed; --text:#2d3148; --muted:#7c8298;
  --up:#0d9b6a; --down:#d9304f;
  --c1:#3b6ee6; --c2:#f59e0b; --c3:#6b7280; --c4:#0d9b6a; --c5:#d9304f;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans KR',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.65;padding:28px 24px;max-width:1320px;margin:0 auto}}
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

.strat-row{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}}
.strat-block{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:20px 22px;box-shadow:0 1px 4px rgba(0,0,0,.05)}}
.strat-block h3{{font-size:13px;font-weight:700;color:#1a1d2e;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}}
.strat-block h3 .dot{{width:10px;height:10px;border-radius:50%;display:inline-block}}
.kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.kpi{{background:var(--bg);border-radius:10px;padding:12px 14px}}
.kpi-label{{font-size:10px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px}}
.kpi-value{{font-size:19px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}
.kpi-sub{{font-size:10px;color:var(--muted);margin-top:1px}}
.badge{{font-size:11px;padding:2px 8px;border-radius:10px;background:var(--card2);color:var(--muted);font-weight:500}}

.section{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px 24px;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.05)}}
.section h2{{font-size:15px;font-weight:600;color:#1a1d2e;margin-bottom:16px;display:flex;align-items:center;gap:8px}}
.chart-wrap{{position:relative;height:300px}}
.chart-wrap.md{{height:220px}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}}

.metrics-table{{width:100%;border-collapse:separate;border-spacing:0}}
.metrics-table th{{font-size:11px;color:var(--muted);font-weight:600;padding:10px 14px;text-align:right;background:var(--card2);border-bottom:1px solid var(--border);text-transform:uppercase;letter-spacing:.4px}}
.metrics-table th:first-child{{text-align:left}}
.metrics-table td{{padding:10px 14px;font-size:13px;border-bottom:1px solid #f3f4f8;text-align:right;font-family:'JetBrains Mono',monospace}}
.metrics-table td:first-child{{text-align:left;font-family:inherit;font-weight:600;color:#1a1d2e}}
.metrics-table tr:last-child td{{border-bottom:none}}
.metrics-table .hl td{{background:#f0f4ff}}

.heatmap-wrap{{overflow-x:auto}}
.heatmap-tbl{{width:100%;border-collapse:separate;border-spacing:0;min-width:700px}}
.heatmap-tbl th{{font-size:11px;color:var(--muted);font-weight:600;padding:8px 10px;text-align:right;background:var(--card2);border-bottom:1px solid var(--border)}}
.heatmap-tbl th:first-child{{text-align:left}}
.heatmap-tbl tr:last-child td{{border-bottom:none}}

.footer{{text-align:center;font-size:11px;color:#94a3b8;padding:16px 0 4px}}
.back-link{{display:inline-block;margin-bottom:16px;font-size:13px;color:var(--c1);text-decoration:none}}
.back-link:hover{{text-decoration:underline}}

@media(max-width:768px){{
  .strat-row,.two-col{{grid-template-columns:1fr}}
  .kpi-grid{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>

<a class="back-link" href="../../index.html">← Back to Index</a>

<div class="header">
  <div>
    <h1>AIMVP RiskOn Strategy</h1>
    <div class="meta">ACWI / AGG / Cash &nbsp;|&nbsp; {bt["period_start"]} ~ {bt["period_end"]}</div>
  </div>
  <div class="gen">
    <div class="regime-tag {regime_css.get(regime, "regime-neutral")}">{regime} ({score:+d})</div>
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

<div class="strat-row">
  <div class="strat-block">
    <h3><span class="dot" style="background:var(--c1)"></span>AIMVP Dynamic TAA <span class="badge">ACWI / AGG / Cash</span></h3>
    <div class="kpi-grid">
      <div class="kpi"><div class="kpi-label">CAGR</div><div class="kpi-value {d_cagr_cls}">{m_d["cagr"]:+.1f}%</div><div class="kpi-sub">vs 75/25 {m_75["cagr"]:+.1f}%</div></div>
      <div class="kpi"><div class="kpi-label">MDD</div><div class="kpi-value down">{m_d["mdd"]:.1f}%</div><div class="kpi-sub">vs 75/25 {m_75["mdd"]:.1f}%</div></div>
      <div class="kpi"><div class="kpi-label">Sharpe</div><div class="kpi-value">{m_d["sharpe"]:.2f}</div><div class="kpi-sub">Hit Rate {m_d["hit_rate"]:.0f}%</div></div>
      <div class="kpi"><div class="kpi-label">Avg ACWI</div><div class="kpi-value">{bt["avg_stock_weight"]:.0f}%</div><div class="kpi-sub">RiskON {int(ALLOC_RISK_ON[0]*100)}% / OFF {int(ALLOC_RISK_OFF[0]*100)}%</div></div>
    </div>
  </div>
  <div class="strat-block">
    <h3><span class="dot" style="background:var(--c3)"></span>75/25 Benchmark <span class="badge">Fixed</span></h3>
    <div class="kpi-grid">
      <div class="kpi"><div class="kpi-label">CAGR</div><div class="kpi-value {b_cagr_cls}">{m_75["cagr"]:+.1f}%</div><div class="kpi-sub">vs 60/40 {m_60["cagr"]:+.1f}%</div></div>
      <div class="kpi"><div class="kpi-label">MDD</div><div class="kpi-value down">{m_75["mdd"]:.1f}%</div><div class="kpi-sub">vs 60/40 {m_60["mdd"]:.1f}%</div></div>
      <div class="kpi"><div class="kpi-label">Sharpe</div><div class="kpi-value">{m_75["sharpe"]:.2f}</div><div class="kpi-sub">Hit Rate {m_75["hit_rate"]:.0f}%</div></div>
      <div class="kpi"><div class="kpi-label">ACWI Wt</div><div class="kpi-value">75%</div><div class="kpi-sub">Fixed allocation</div></div>
    </div>
  </div>
</div>

<div class="section">
  <h2>Cumulative Returns <span class="badge">Monthly Rebalance</span></h2>
  <div class="chart-wrap">
    <canvas id="cumChart"></canvas>
  </div>
</div>

<div class="two-col">
  <div class="section">
    <h2>Drawdown</h2>
    <div class="chart-wrap md">
      <canvas id="ddChart"></canvas>
    </div>
  </div>
  <div class="section">
    <h2>Weight History <span class="badge">ACWI / AGG / Cash</span></h2>
    <div class="chart-wrap md">
      <canvas id="weightChart"></canvas>
    </div>
  </div>
</div>

<div class="section">
  <h2>Performance Comparison</h2>
  <table class="metrics-table">
    <thead>
      <tr><th>Strategy</th><th>CAGR</th><th>MDD</th><th>Sharpe</th><th>Hit Rate</th></tr>
    </thead>
    <tbody>
      {perf_rows}
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Monthly Returns Heatmap <span class="badge">vs 75/25 Excess</span></h2>
  <div class="heatmap-wrap">
    <table class="heatmap-tbl">
      <thead><tr>
        <th style="text-align:left">Year</th>
        {month_headers}
        <th style="border-left:2px solid #e0e3ed">Annual</th>
        <th style="border-left:1px solid #e0e3ed;text-align:center">Win Rate</th>
        <th style="text-align:center">P/L Ratio</th>
      </tr></thead>
      <tbody>{bt["heatmap_html"]}</tbody>
    </table>
  </div>
</div>

<div class="footer">AIMVP RiskOn (Faber TAA) | 3-Signal Regime → Dynamic Asset Allocation | Portfolio Agent</div>

<script>
const D = {chart_data};
const C = {{ c1:'#3b6ee6', c2:'#f59e0b', c3:'#6b7280', c4:'#0d9b6a', c5:'#d9304f' }};

function baseOpts(yLabel) {{
  return {{
    responsive:true, maintainAspectRatio:false,
    interaction:{{mode:'index',intersect:false}},
    plugins:{{
      legend:{{position:'top',labels:{{font:{{size:11}},boxWidth:12}}}},
      tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y.toFixed(3)}}`}}}}
    }},
    scales:{{
      x:{{ticks:{{maxTicksLimit:12,font:{{size:10}},color:'#7c8298'}},grid:{{color:'#f0f1f6'}}}},
      y:{{title:{{display:!!yLabel,text:yLabel,font:{{size:10}},color:'#7c8298'}},ticks:{{font:{{size:10}},color:'#7c8298'}},grid:{{color:'#f0f1f6'}}}}
    }}
  }};
}}

new Chart(document.getElementById('cumChart'),{{
  type:'line',
  data:{{
    labels:D.labels,
    datasets:[
      {{label:'AIMVP Dynamic',data:D.cumDynamic,borderColor:C.c1,borderWidth:2.5,pointRadius:0,tension:.1}},
      {{label:'75/25 Fixed',data:D.cum7525,borderColor:C.c3,borderWidth:1.5,pointRadius:0,borderDash:[5,3],tension:.1}},
      {{label:'60/40 Fixed',data:D.cum6040,borderColor:'#9ca3af',borderWidth:1,pointRadius:0,borderDash:[3,3],tension:.1}},
      {{label:'ACWI',data:D.cumStock,borderColor:C.c4,borderWidth:1,pointRadius:0,borderDash:[2,2],tension:.1}},
      {{label:'AGG',data:D.cumBond,borderColor:C.c5,borderWidth:1,pointRadius:0,borderDash:[2,2],tension:.1}},
    ]
  }},
  options:{{
    ...baseOpts(''),
    plugins:{{
      ...baseOpts('').plugins,
      tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{(ctx.parsed.y*100-100).toFixed(1)}}%`}}}}
    }}
  }}
}});

new Chart(document.getElementById('ddChart'),{{
  type:'line',
  data:{{
    labels:D.labels,
    datasets:[
      {{label:'AIMVP',data:D.ddDynamic,borderColor:C.c1,borderWidth:2,pointRadius:0,fill:true,backgroundColor:'rgba(59,110,230,0.07)'}},
      {{label:'75/25',data:D.dd7525,borderColor:C.c3,borderWidth:1.5,pointRadius:0,borderDash:[4,3]}},
      {{label:'ACWI',data:D.ddStock,borderColor:C.c4,borderWidth:1,pointRadius:0,borderDash:[2,2]}},
    ]
  }},
  options:{{
    ...baseOpts('Drawdown (%)'),
    plugins:{{...baseOpts('').plugins,tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y.toFixed(2)}}%`}}}}}}
  }}
}});

new Chart(document.getElementById('weightChart'),{{
  type:'bar',
  data:{{
    labels:D.labels,
    datasets:[
      {{label:'ACWI',data:D.wStock,backgroundColor:'rgba(59,110,230,0.75)',borderWidth:0,stack:'w'}},
      {{label:'AGG',data:D.wBond,backgroundColor:'rgba(217,48,79,0.65)',borderWidth:0,stack:'w'}},
      {{label:'Cash',data:D.wCash,backgroundColor:'rgba(16,185,129,0.65)',borderWidth:0,stack:'w'}},
    ]
  }},
  options:{{
    responsive:true, maintainAspectRatio:false,
    interaction:{{mode:'index',intersect:false}},
    plugins:{{
      legend:{{position:'top',labels:{{font:{{size:11}},boxWidth:12}}}},
      tooltip:{{callbacks:{{label:ctx=>` ${{ctx.dataset.label}}: ${{ctx.parsed.y.toFixed(0)}}%`}}}}
    }},
    scales:{{
      x:{{stacked:true,ticks:{{maxTicksLimit:12,font:{{size:10}},color:'#7c8298'}},grid:{{display:false}}}},
      y:{{stacked:true,min:0,max:100,ticks:{{font:{{size:10}},color:'#7c8298',callback:v=>v+'%'}},grid:{{color:'#f0f1f6'}}}}
    }}
  }}
}});
</script>
</body>
</html>'''


def main():
    parser = argparse.ArgumentParser(description="AIMVP RiskOn backtest report")
    parser.add_argument("--date", required=True)
    parser.add_argument("--csv", help="Path to market_data.csv")
    args = parser.parse_args()

    path = generate_report(args.date, args.csv)
    print(f"HTML report: {path}")


if __name__ == "__main__":
    main()
