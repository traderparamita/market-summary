"""Sector RS Sync — 8쌍 GICS 공통 섹터 상대강도 단일 신호 모델.

핵심 아이디어: 11개씩 있는 KR/US 섹터 중 GICS 가 깔끔히 매칭되는 8쌍만 사용해
페어별 상대수익(1M/3M/6M 로그수익 차이의 평균)을 구하고, 이를 세 가지 방식으로
단일 수치로 집계한 뒤, 임계값을 넘어설 때 KR/US 포지션으로 전환.

8 GICS 공통쌍:
  IT, FIN, HEALTH, INDU, ENERGY, DISCR, STAPLES, COMM
  (HEAVY↔MATL, CONSTR↔UTIL, STEEL↔REIT 은 억지매핑이라 제외)

3 집계 신호:
  1) mean_rs        평균 RS (연속 신호, 임계 ±0.02)
  2) breadth        양의 RS 페어 비율 (0.5 중심, 임계 ±0.125 = 5/8 다수결)
  3) weighted       mean × (2·breadth − 1) — 일관성 가중 (임계 ±0.01)

상태 기계 (hysteresis):
  |agg| > θ → KR/US 전환, |agg| ≤ θ → 직전 상태 유지 (churn 억제)

백테스트:
  월말 리밸런싱, 상태 전환 시만 30bps one-way 비용, EQ_KOSPI / EQ_SP500 직접 베팅.
  벤치마크: 50/50 블렌드, KOSPI, S&P500.

Usage:
    python -m portfolio.strategy.sector_rs_sync --date 2026-04-21
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.market_source import load_wide_close

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "portfolio" / "strategy" / "rs_sync"

# ── 설정 ───────────────────────────────────────────────
SECTOR_PAIRS: list[tuple[str, str, str]] = [
    ("IX_KR_IT",      "SC_US_TECH",    "IT / Tech"),
    ("IX_KR_FIN",     "SC_US_FIN",     "금융 / Financials"),
    ("IX_KR_HEALTH",  "SC_US_HEALTH",  "헬스케어 / Health"),
    ("IX_KR_INDU",    "SC_US_INDU",    "산업재 / Industrials"),
    ("IX_KR_ENERGY",  "SC_US_ENERGY",  "에너지 / Energy"),
    ("IX_KR_DISCR",   "SC_US_DISCR",   "경기소비재 / ConsDiscr"),
    ("IX_KR_STAPLES", "SC_US_STAPLES", "생활소비재 / ConsStap"),
    ("IX_KR_COMM",    "SC_US_COMM",    "커뮤니케이션 / Comm"),
]
LOOKBACK_MONTHS = [1, 3, 6]
BACKTEST_START = "2010-01-01"
COST_BPS = 30
MIN_PAIRS = 5  # 월말 시그널 생성 최소 유효 페어 (4쌍 variant 는 3)

THRESHOLDS = {
    "mean":     0.02,   # log-return 평균 차
    "breadth":  0.125,  # 0.5 기준 편차 (5/8 다수결)
    "weighted": 0.01,   # mean × (2·breadth − 1)
}

KOSPI_CODE = "EQ_KOSPI"
SP500_CODE = "EQ_SP500"

_C = {"KR": "#E63946", "US": "#1D3557", "Neutral": "#6C757D"}
_LIGHT = {"KR": "#FFF0F1", "US": "#EEF1F8", "Neutral": "#F8F9FA"}


# ──────────────────────────────────────────────────────
# Core calculations
# ──────────────────────────────────────────────────────

def _log_return(px: pd.Series, as_of: pd.Timestamp, months: int) -> float | None:
    """as_of 기준 months 개월 전 대비 로그수익. 데이터 부족 시 None."""
    data = px.loc[:as_of].dropna()
    if data.empty:
        return None
    target = as_of - pd.DateOffset(months=months)
    past = data[data.index <= target]
    if past.empty:
        return None
    start = float(past.iloc[-1])
    end = float(data.iloc[-1])
    if start <= 0 or end <= 0:
        return None
    return math.log(end / start)


def compute_rs_pairs(pivot: pd.DataFrame, as_of: pd.Timestamp) -> list[dict]:
    """8 페어별 RS(1M/3M/6M 평균). 데이터 없는 페어는 제외."""
    rs_list: list[dict] = []
    for kr_code, us_code, label in SECTOR_PAIRS:
        if kr_code not in pivot.columns or us_code not in pivot.columns:
            continue
        kr_px = pivot[kr_code]
        us_px = pivot[us_code]
        diffs = []
        for m in LOOKBACK_MONTHS:
            kr_lr = _log_return(kr_px, as_of, m)
            us_lr = _log_return(us_px, as_of, m)
            if kr_lr is None or us_lr is None:
                continue
            diffs.append(kr_lr - us_lr)
        if not diffs:
            continue
        rs_list.append({
            "pair":  label,
            "kr":    kr_code,
            "us":    us_code,
            "rs":    sum(diffs) / len(diffs),
            "n_win": len(diffs),
        })
    return rs_list


def aggregate(rs_list: list[dict]) -> dict | None:
    """3가지 집계 + 각 상태 계산."""
    if not rs_list:
        return None
    rs_vals = [r["rs"] for r in rs_list]
    n = len(rs_vals)
    mean_rs = sum(rs_vals) / n
    breadth = sum(1 for v in rs_vals if v > 0) / n
    breadth_centered = breadth - 0.5
    weighted = mean_rs * (2 * breadth - 1)

    def _state(score: float, thr: float) -> str | None:
        if score > thr:
            return "KR"
        if score < -thr:
            return "US"
        return None

    return {
        "n_pairs":          n,
        "mean_rs":          mean_rs,
        "breadth":          breadth,
        "breadth_centered": breadth_centered,
        "weighted":         weighted,
        "mean_state":       _state(mean_rs,          THRESHOLDS["mean"]),
        "breadth_state":    _state(breadth_centered, THRESHOLDS["breadth"]),
        "weighted_state":   _state(weighted,         THRESHOLDS["weighted"]),
    }


def next_month_return(pivot: pd.DataFrame, me: pd.Timestamp, code: str) -> float | None:
    """me 다음 월말까지의 수익률. 데이터 부족 시 None."""
    if code not in pivot.columns:
        return None
    data = pivot[code].dropna()
    data = data[data.index >= me]
    if len(data) < 2:
        return None
    start = float(data.iloc[0])
    next_me = me + pd.offsets.BusinessMonthEnd()
    data_until = data[data.index <= next_me]
    if len(data_until) < 2:
        return None
    return float(data_until.iloc[-1] / start - 1)


# ──────────────────────────────────────────────────────
# Backtest
# ──────────────────────────────────────────────────────

def run_backtest(pivot: pd.DataFrame) -> pd.DataFrame:
    month_ends = pivot.resample("BME").last().index
    cost = COST_BPS / 10_000

    records: list[dict] = []
    prev = {"mean": None, "breadth": None, "weighted": None}

    for me in month_ends[:-1]:
        rs_list = compute_rs_pairs(pivot, me)
        agg = aggregate(rs_list)
        if agg is None or agg["n_pairs"] < MIN_PAIRS:
            continue

        kr_ret = next_month_return(pivot, me, KOSPI_CODE)
        us_ret = next_month_return(pivot, me, SP500_CODE)
        if kr_ret is None or us_ret is None:
            continue

        # 상태 resolve (None 이면 직전 유지; 최초는 Neutral)
        def _resolve(key: str, new_state: str | None) -> str:
            if new_state is not None:
                return new_state
            return prev[key] if prev[key] is not None else "Neutral"

        m_sig = _resolve("mean",     agg["mean_state"])
        b_sig = _resolve("breadth",  agg["breadth_state"])
        w_sig = _resolve("weighted", agg["weighted_state"])

        def _ret_and_cost(sig: str, prev_sig: str | None) -> tuple[float, float]:
            if sig == "KR":
                r = kr_ret
            elif sig == "US":
                r = us_ret
            else:
                r = 0.5 * kr_ret + 0.5 * us_ret
            tc = cost if (prev_sig is not None and sig != prev_sig) else 0.0
            return r - tc, tc

        m_r, m_tc = _ret_and_cost(m_sig, prev["mean"])
        b_r, b_tc = _ret_and_cost(b_sig, prev["breadth"])
        w_r, w_tc = _ret_and_cost(w_sig, prev["weighted"])

        prev["mean"] = m_sig
        prev["breadth"] = b_sig
        prev["weighted"] = w_sig

        records.append({
            "as_of":            me.strftime("%Y-%m-%d"),
            "n_pairs":          agg["n_pairs"],
            "mean_rs":          round(agg["mean_rs"], 5),
            "breadth":          round(agg["breadth"], 4),
            "breadth_centered": round(agg["breadth_centered"], 4),
            "weighted":         round(agg["weighted"], 5),
            "mean_signal":      m_sig,
            "breadth_signal":   b_sig,
            "weighted_signal":  w_sig,
            "mean_cost":        round(m_tc, 5),
            "breadth_cost":     round(b_tc, 5),
            "weighted_cost":    round(w_tc, 5),
            "kr_return":        round(kr_ret, 4),
            "us_return":        round(us_ret, 4),
            "mean_strategy":    round(m_r, 4),
            "breadth_strategy": round(b_r, 4),
            "weighted_strategy": round(w_r, 4),
            "blend_return":     round(0.5 * kr_ret + 0.5 * us_ret, 4),
        })

    return pd.DataFrame(records)


# ──────────────────────────────────────────────────────
# Performance metrics
# ──────────────────────────────────────────────────────

def perf(returns: pd.Series, label: str) -> dict:
    r = returns.dropna()
    if len(r) == 0:
        return {}
    cum = (1 + r).cumprod()
    total = float(cum.iloc[-1] - 1)
    n = len(r)
    ann_ret = (1 + total) ** (12 / n) - 1 if n > 0 else 0.0
    ann_vol = float(r.std() * math.sqrt(12))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    dd = cum / cum.cummax() - 1
    mdd = float(dd.min())
    win = float((r > 0).mean())
    return {
        "label":        label,
        "total_return": round(total, 4),
        "ann_return":   round(ann_ret, 4),
        "ann_vol":      round(ann_vol, 4),
        "sharpe":       round(sharpe, 2),
        "mdd":          round(mdd, 4),
        "win_rate":     round(win, 3),
        "n_months":     n,
    }


# ──────────────────────────────────────────────────────
# HTML report
# ──────────────────────────────────────────────────────

def _badge(sig: str) -> str:
    return (
        f'<span style="background:{_C.get(sig,"#6C757D")};color:#fff;'
        f'padding:2px 9px;border-radius:20px;font-size:0.72rem;font-weight:700">{sig}</span>'
    )


def build_html(bt: pd.DataFrame, rs_latest: list[dict], date_str: str,
               metrics_all: dict[str, list[dict]]) -> str:
    bs = bt.sort_values("as_of").reset_index(drop=True)
    labels_j = json.dumps(list(bs["as_of"]))

    def _cum(col: str) -> list:
        return ((1 + bs[col]).cumprod() - 1).round(4).tolist()

    cum_mean     = _cum("mean_strategy")
    cum_breadth  = _cum("breadth_strategy")
    cum_weighted = _cum("weighted_strategy")
    cum_blend    = _cum("blend_return")
    cum_kr       = _cum("kr_return")
    cum_us       = _cum("us_return")

    # Per-pair RS table (latest)
    pair_rows = ""
    for r in sorted(rs_latest, key=lambda x: -x["rs"]):
        color = "#16A34A" if r["rs"] > 0 else "#DC2626"
        arrow = "▲" if r["rs"] > 0 else "▼"
        pair_rows += (
            f'<tr>'
            f'<td>{r["pair"]}</td>'
            f'<td class="mono">{r["kr"]}</td>'
            f'<td class="mono">{r["us"]}</td>'
            f'<td class="num" style="color:{color};font-weight:700">{arrow} {r["rs"]*100:+.2f}%</td>'
            f'</tr>'
        )

    # Aggregate signal hero
    last = bs.iloc[-1]
    hero_rows = ""
    for key, label in [("mean", "평균 RS"), ("breadth", "Breadth(편차)"), ("weighted", "가중 합성")]:
        col = "mean_rs" if key == "mean" else ("breadth_centered" if key == "breadth" else "weighted")
        sig_col = f"{key}_signal"
        val = last[col]
        sig = last[sig_col]
        thr = THRESHOLDS[key]
        bar_pct = min(100, abs(val) / (thr * 3) * 100)
        hero_rows += (
            f'<div class="hero-card">'
            f'<div class="hero-label">{label} <small style="color:#888">(θ=±{thr})</small></div>'
            f'<div class="hero-val">{val*100:+.2f}{"%" if key != "breadth" else "pp"}</div>'
            f'<div class="hero-sig">{_badge(sig)}</div>'
            f'<div class="hero-bar"><div style="width:{bar_pct:.0f}%;background:{_C.get(sig)}"></div></div>'
            f'</div>'
        )

    # Recent 24 months timeline
    recent = bs.tail(24).iloc[::-1]
    tl_rows = ""
    for _, r in recent.iterrows():
        bg = _LIGHT.get(r["weighted_signal"], "#fff")
        excess = r["weighted_strategy"] - r["blend_return"]
        exc_color = "#16A34A" if excess >= 0 else "#DC2626"
        tl_rows += (
            f'<tr style="background:{bg}">'
            f'<td>{r["as_of"]}</td>'
            f'<td class="num">{r["n_pairs"]}</td>'
            f'<td class="num">{r["mean_rs"]*100:+.2f}%</td>'
            f'<td class="num">{r["breadth"]*100:.0f}%</td>'
            f'<td class="num">{r["weighted"]*100:+.2f}%</td>'
            f'<td style="text-align:center">{_badge(r["mean_signal"])}</td>'
            f'<td style="text-align:center">{_badge(r["breadth_signal"])}</td>'
            f'<td style="text-align:center">{_badge(r["weighted_signal"])}</td>'
            f'<td class="num" style="color:{"#16A34A" if r["kr_return"]>0 else "#DC2626"}">{r["kr_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{"#16A34A" if r["us_return"]>0 else "#DC2626"}">{r["us_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{"#16A34A" if r["weighted_strategy"]>0 else "#DC2626"}">{r["weighted_strategy"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{exc_color}">{excess*100:+.1f}%</td>'
            f'</tr>'
        )

    # Metrics table
    def _metric_rows(m_list: list[dict]) -> str:
        rows = ""
        for m in m_list:
            rows += (
                f'<tr>'
                f'<td>{m["label"]}</td>'
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

    m_rows = _metric_rows(metrics_all["all"])

    # Signal count summary
    sig_counts_w = bs["weighted_signal"].value_counts().to_dict()
    n_trades_w = int((bs["weighted_cost"] > 0).sum())
    total_cost_w = float(bs["weighted_cost"].sum())

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Sector RS Sync — {date_str}</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; background:#F7F8FA; color:#1F2937; padding:24px; max-width:1280px; margin:0 auto; }}
  h1 {{ font-size:1.5rem; font-weight:800; margin-bottom:4px; }}
  .subtitle {{ color:#6B7280; font-size:0.85rem; margin-bottom:24px; }}
  h2 {{ font-size:1rem; color:#111827; margin:28px 0 10px; padding-left:10px; border-left:3px solid #F58220; }}
  .hero-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
  .hero-card {{ background:#fff; border-radius:10px; padding:14px 18px; box-shadow:0 1px 3px rgba(0,0,0,0.04); border:1px solid #E5E7EB; }}
  .hero-label {{ font-size:0.78rem; color:#6B7280; margin-bottom:4px; }}
  .hero-val {{ font-size:1.8rem; font-weight:800; color:#111827; }}
  .hero-sig {{ margin:6px 0 10px; }}
  .hero-bar {{ height:4px; background:#F3F4F6; border-radius:2px; overflow:hidden; }}
  .hero-bar > div {{ height:100%; border-radius:2px; }}
  table {{ width:100%; background:#fff; border-collapse:collapse; font-size:0.85rem; border-radius:8px; overflow:hidden; border:1px solid #E5E7EB; }}
  th {{ background:#F3F4F6; padding:9px 10px; text-align:left; font-weight:600; color:#374151; border-bottom:1px solid #E5E7EB; }}
  td {{ padding:8px 10px; border-bottom:1px solid #F3F4F6; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.mono {{ font-family: 'SF Mono', Menlo, monospace; color:#6B7280; font-size:0.78rem; }}
  tr:last-child td {{ border-bottom:none; }}
  .canvas-wrap {{ background:#fff; padding:16px; border-radius:10px; border:1px solid #E5E7EB; }}
  .summary-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:6px; }}
  .summary-card {{ background:#fff; padding:14px; border-radius:8px; border:1px solid #E5E7EB; }}
  .summary-card .k {{ font-size:0.72rem; color:#6B7280; }}
  .summary-card .v {{ font-size:1.1rem; font-weight:700; color:#111827; margin-top:2px; }}
  .note {{ color:#6B7280; font-size:0.75rem; margin-top:6px; line-height:1.5; }}
</style>
</head>
<body>

<h1>Sector RS Sync — {date_str}</h1>
<div class="subtitle">
  8 GICS 공통 섹터쌍 기반 상대강도 단일 신호 모델 · 월말 리밸런싱 · 비용 {COST_BPS}bps · {BACKTEST_START} ~ {date_str}
</div>

<h2>현재 신호 (3 집계 방식)</h2>
<div class="hero-grid">
  {hero_rows}
</div>

<h2>섹터별 상대강도 (as of {last["as_of"]}, 1/3/6M 로그수익 평균)</h2>
<table>
  <thead><tr><th>페어</th><th>KR 코드</th><th>US 코드</th><th style="text-align:right">RS (log)</th></tr></thead>
  <tbody>{pair_rows}</tbody>
</table>

<h2>누적 수익률 (Gross of cost 는 빼고, 비용 차감 후 기준)</h2>
<div class="canvas-wrap">
  <canvas id="cum" style="max-height:380px"></canvas>
</div>

<h2>Breadth / Mean RS Timeline</h2>
<div class="canvas-wrap">
  <canvas id="sig" style="max-height:300px"></canvas>
</div>

<h2>성과 비교</h2>
<table>
  <thead><tr><th>전략</th><th>Total</th><th>연수익</th><th>연변동</th><th>Sharpe</th><th>MDD</th><th>Win%</th><th>#월</th></tr></thead>
  <tbody>{m_rows}</tbody>
</table>

<h2>최근 24개월 시그널 & 수익</h2>
<table>
  <thead><tr>
    <th>월</th><th style="text-align:right">쌍</th><th style="text-align:right">평균RS</th><th style="text-align:right">Breadth</th><th style="text-align:right">Weighted</th>
    <th style="text-align:center">M</th><th style="text-align:center">B</th><th style="text-align:center">W</th>
    <th style="text-align:right">KR</th><th style="text-align:right">US</th><th style="text-align:right">W-전략</th><th style="text-align:right">vs Blend</th>
  </tr></thead>
  <tbody>{tl_rows}</tbody>
</table>

<h2>Weighted 전략 요약</h2>
<div class="summary-grid">
  <div class="summary-card"><div class="k">KR / US / Neutral 개월</div><div class="v">{sig_counts_w.get("KR",0)} / {sig_counts_w.get("US",0)} / {sig_counts_w.get("Neutral",0)}</div></div>
  <div class="summary-card"><div class="k">상태 전환 횟수</div><div class="v">{n_trades_w} 회</div></div>
  <div class="summary-card"><div class="k">누적 거래비용</div><div class="v">{total_cost_w*100:.2f}%</div></div>
</div>
<div class="note">
  집계 방식: <b>평균 RS</b>=페어별 로그수익 차의 평균 · <b>Breadth</b>=양의 RS 페어 비율(0.5=중립) · <b>Weighted</b>=평균×(2·Breadth−1).<br>
  임계값 이하일 때는 직전 상태 유지(hysteresis) → 잦은 전환 억제. 8쌍 중 SC_US_COMM 은 2018-06 이후만 집계.
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  const labels = {labels_j};
  new Chart(document.getElementById('cum'), {{
    type: 'line',
    data: {{ labels: labels, datasets: [
      {{ label: 'Mean-RS',     data: {cum_mean},     borderColor:'#F58220', backgroundColor:'transparent', tension:0.15, borderWidth:2 }},
      {{ label: 'Breadth',     data: {cum_breadth},  borderColor:'#059669', backgroundColor:'transparent', tension:0.15, borderWidth:2 }},
      {{ label: 'Weighted',    data: {cum_weighted}, borderColor:'#DC2626', backgroundColor:'transparent', tension:0.15, borderWidth:2.5 }},
      {{ label: '50/50 Blend', data: {cum_blend},    borderColor:'#6B7280', borderDash:[6,4], backgroundColor:'transparent', tension:0.15, borderWidth:1.5 }},
      {{ label: 'KOSPI',       data: {cum_kr},       borderColor:'#E63946', borderDash:[2,3], backgroundColor:'transparent', tension:0.15, borderWidth:1 }},
      {{ label: 'S&P500',      data: {cum_us},       borderColor:'#1D3557', borderDash:[2,3], backgroundColor:'transparent', tension:0.15, borderWidth:1 }},
    ]}},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position:'top', labels:{{ usePointStyle:true, pointStyle:'line' }} }} }},
      scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }}, x: {{ ticks: {{ maxTicksLimit:12 }} }} }}
    }}
  }});

  new Chart(document.getElementById('sig'), {{
    type: 'line',
    data: {{ labels: labels, datasets: [
      {{ label: '평균 RS',        data: {json.dumps(bs["mean_rs"].tolist())},          yAxisID:'y1', borderColor:'#F58220', backgroundColor:'transparent', tension:0.1, borderWidth:1.8 }},
      {{ label: 'Breadth(편차)',   data: {json.dumps(bs["breadth_centered"].tolist())}, yAxisID:'y2', borderColor:'#059669', backgroundColor:'transparent', tension:0.1, borderWidth:1.8 }},
      {{ label: 'Weighted',       data: {json.dumps(bs["weighted"].tolist())},         yAxisID:'y1', borderColor:'#DC2626', backgroundColor:'transparent', tension:0.1, borderWidth:1.8 }},
    ]}},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position:'top' }} }},
      scales: {{
        y1: {{ position:'left',  ticks: {{ callback: v => (v*100).toFixed(1)+'%' }} }},
        y2: {{ position:'right', grid: {{ drawOnChartArea:false }}, ticks: {{ callback: v => (v*100).toFixed(0)+'pp' }} }},
        x:  {{ ticks: {{ maxTicksLimit:12 }} }}
      }}
    }}
  }});
</script>

</body>
</html>
"""
    return html


# ──────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",  default=None, help="기준일 YYYY-MM-DD (미지정 시 CSV 최신)")
    parser.add_argument("--start", default=BACKTEST_START)
    args = parser.parse_args()

    codes = [p[0] for p in SECTOR_PAIRS] + [p[1] for p in SECTOR_PAIRS] + [KOSPI_CODE, SP500_CODE]
    pivot = load_wide_close(start=args.start, codes=codes)
    if pivot.empty:
        raise SystemExit("[ERROR] 데이터 로드 실패")
    print(f"[load] {pivot.index.min().date()} ~ {pivot.index.max().date()} · {pivot.shape[1]}개 코드")

    if args.date:
        pivot = pivot.loc[:args.date]
        date_str = args.date
    else:
        date_str = pivot.index.max().strftime("%Y-%m-%d")
    print(f"[cutoff] {date_str}")

    # Backtest
    bt = run_backtest(pivot)
    if bt.empty:
        raise SystemExit("[ERROR] 백테스트 결과 비어있음")
    print(f"[backtest] {len(bt)} 개월 ({bt['as_of'].iloc[0]} ~ {bt['as_of'].iloc[-1]})")

    # Latest RS per pair
    last_me = pd.Timestamp(bt["as_of"].iloc[-1])
    rs_latest = compute_rs_pairs(pivot, last_me)

    # Performance metrics
    bs = bt.copy()
    metrics = [
        perf(bs["mean_strategy"],     "Mean-RS 전략"),
        perf(bs["breadth_strategy"],  "Breadth 전략"),
        perf(bs["weighted_strategy"], "Weighted 전략"),
        perf(bs["blend_return"],      "50/50 Blend"),
        perf(bs["kr_return"],         "KOSPI-only"),
        perf(bs["us_return"],         "S&P500-only"),
    ]

    for m in metrics:
        if m:
            print(f"  {m['label']:20s}  CAGR={m['ann_return']*100:+6.2f}%  "
                  f"Sharpe={m['sharpe']:+5.2f}  MDD={m['mdd']*100:+6.1f}%  Win={m['win_rate']*100:3.0f}%")

    # HTML
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = build_html(bt, rs_latest, date_str, {"all": metrics})
    html_path = OUTPUT_DIR / f"{date_str}.html"
    html_path.write_text(html, encoding="utf-8")
    csv_path = OUTPUT_DIR / f"{date_str}_signals.csv"
    bt.to_csv(csv_path, index=False)
    print(f"[write] {html_path}")
    print(f"[write] {csv_path}")


if __name__ == "__main__":
    main()
