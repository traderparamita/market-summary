"""시그널 대시보드 — 단일 시그널 (MAIN 6M-only).

운영 구조:
  MAIN (6M-only lookback, 4쌍 경제축) 단독 — Sharpe 0.97 / OOS 1.09

과거 시도: ALERT (Champion [1,3,6]) 이중 시그널 구조는
  63개 변형 실증 결과 조합 Sharpe 개선 실패 → 폐기. alert_explorer.html 참고.

Usage:
    python -m portfolio.strategy.sector_asset_allocation.dashboard
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from portfolio.strategy.sector_asset_allocation.core import (
    BACKTEST_START, Config, load_all_data, run_backtest, perf,
    SECTOR_PAIRS_ECO4,
    log_return, pct_return,
    KOSPI_CODE, SP500_CODE, FX_USDKRW,
)

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_PATH = ROOT / "output" / "portfolio" / "strategy" / "sector_asset_allocation.html"

# 모델 파라미터
PARAMS = {
    "w_rs": 0.7, "w_fx": 0.3, "tau": 0.02,
    "fx_scale": 0.03, "fx_to_rs_scale": 0.02, "cost_bps": 30,
    "lookback": 6,
}

PRIMARY_CFG = Config(
    name="MAIN (6M-only)",
    pairs=SECTOR_PAIRS_ECO4,
    w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
    tau=0.02, lookbacks=[6],
)


# ─────────────────────────────────────────────────────
# 신호 분해
# ─────────────────────────────────────────────────────

def decompose(pivot: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    """월말 시그널 완전 분해."""
    pair_details = []
    for kr_code, us_code, label in SECTOR_PAIRS_ECO4:
        if kr_code not in pivot.columns or us_code not in pivot.columns:
            continue
        entry = {"pair": label, "kr_code": kr_code, "us_code": us_code}
        kr = log_return(pivot[kr_code], as_of, PARAMS["lookback"])
        us = log_return(pivot[us_code], as_of, PARAMS["lookback"])
        if kr is None or us is None:
            continue
        entry["kr_ret"] = kr
        entry["us_ret"] = us
        entry["rs"] = kr - us
        entry["vote"] = "KR" if entry["rs"] > 0 else ("US" if entry["rs"] < 0 else "—")
        pair_details.append(entry)

    mean_rs = sum(p["rs"] for p in pair_details) / len(pair_details) if pair_details else 0.0

    usdkrw_r = pct_return(pivot.get(FX_USDKRW), as_of, 3)
    fx_tilt = math.tanh(usdkrw_r / PARAMS["fx_scale"]) if usdkrw_r is not None else 0.0

    rs_contrib = PARAMS["w_rs"] * mean_rs
    fx_contrib = PARAMS["w_fx"] * fx_tilt * PARAMS["fx_to_rs_scale"]
    agg = rs_contrib + fx_contrib

    tau = PARAMS["tau"]
    signal = "KR" if agg > tau else ("US" if agg < -tau else "Neutral")

    return {
        "as_of": as_of, "pairs": pair_details,
        "mean_rs": mean_rs, "rs_contrib": rs_contrib,
        "usdkrw_3m": usdkrw_r, "fx_tilt": fx_tilt, "fx_contrib": fx_contrib,
        "agg": agg, "tau": tau, "signal": signal,
    }


# ─────────────────────────────────────────────────────
# HTML helpers
# ─────────────────────────────────────────────────────

_COLOR = {"KR": "#E63946", "US": "#1D3557", "Neutral": "#6C757D"}
_BG    = {"KR": "linear-gradient(135deg,#7F1D1D,#E63946)",
          "US": "linear-gradient(135deg,#1e3a5f,#1D3557)",
          "Neutral": "linear-gradient(135deg,#374151,#6B7280)"}


def _badge(sig: str, size: str = "md") -> str:
    fs = "0.72rem" if size == "sm" else "0.95rem" if size == "md" else "1.4rem"
    pad = "2px 9px" if size == "sm" else "4px 16px" if size == "md" else "10px 28px"
    return (
        f'<span style="background:{_COLOR.get(sig)};color:#fff;padding:{pad};'
        f'border-radius:30px;font-size:{fs};font-weight:800;letter-spacing:.04em">{sig}</span>'
    )


def _hero(d: dict) -> str:
    bg = _BG[d["signal"]]
    as_of = d["as_of"].strftime("%Y-%m-%d")
    return f"""
<div class="hero" style="background:{bg}">
  <div class="hero-row">
    <div>
      <div class="hero-label">기준일</div>
      <div class="hero-value">{as_of}</div>
    </div>
    <div>
      <div class="hero-label">현재 시그널</div>
      <div style="margin-top:4px">{_badge(d["signal"], "lg")}</div>
    </div>
    <div>
      <div class="hero-label">합성 점수 agg</div>
      <div class="hero-value">{d["agg"]:+.4f}</div>
      <div class="hero-sub">임계 ±{d["tau"]}</div>
    </div>
    <div>
      <div class="hero-label">평균 RS (6M 로그차)</div>
      <div class="hero-value">{d["mean_rs"]*100:+.2f}%</div>
    </div>
    <div>
      <div class="hero-label">FX tilt (USDKRW 3M)</div>
      <div class="hero-value">{d["fx_tilt"]:+.3f}</div>
      <div class="hero-sub">{d["usdkrw_3m"]*100:+.2f}% 3M</div>
    </div>
  </div>
</div>
"""


def _formula_block(d: dict) -> str:
    rs_pct = d["rs_contrib"] * 100
    fx_pct = d["fx_contrib"] * 100
    agg_pct = d["agg"] * 100
    tau_pct = d["tau"] * 100
    total_abs = abs(d["rs_contrib"]) + abs(d["fx_contrib"])
    rs_share = abs(d["rs_contrib"]) / total_abs * 100 if total_abs > 0 else 50
    fx_share = 100 - rs_share
    return f"""
<div class="formula-box">
  <div class="formula-row">
    <div class="formula-item">
      <div class="formula-label">RS 기여 (0.70)</div>
      <div class="formula-value" style="color:{'#16A34A' if d['rs_contrib']>0 else '#DC2626'}">{rs_pct:+.3f}%</div>
      <div class="formula-sub">= 0.70 × {d['mean_rs']*100:+.2f}%</div>
    </div>
    <div class="formula-plus">+</div>
    <div class="formula-item">
      <div class="formula-label">FX 기여 (0.30)</div>
      <div class="formula-value" style="color:{'#16A34A' if d['fx_contrib']>0 else '#DC2626'}">{fx_pct:+.3f}%</div>
      <div class="formula-sub">= 0.30 × {d['fx_tilt']:+.3f} × 0.02</div>
    </div>
    <div class="formula-plus">=</div>
    <div class="formula-item">
      <div class="formula-label">합성 agg</div>
      <div class="formula-value" style="color:{_COLOR[d['signal']]};font-size:2rem">{agg_pct:+.3f}%</div>
      <div class="formula-sub">vs 임계 ±{tau_pct:.1f}%</div>
    </div>
  </div>
  <div class="contribution-bar">
    <div style="width:{rs_share:.1f}%;background:#F58220">{rs_share:.0f}%</div>
    <div style="width:{fx_share:.1f}%;background:#1D3557">{fx_share:.0f}%</div>
  </div>
</div>
"""


def _pair_cards(d: dict) -> str:
    cards = ""
    for p in d["pairs"]:
        vote_color = _COLOR["KR"] if p["rs"] > 0 else _COLOR["US"]
        diff_color = "#16A34A" if p["rs"] > 0 else "#DC2626"
        cards += f"""
<div class="pair-card">
  <div class="pair-header" style="border-left:4px solid {vote_color}">
    <div class="pair-name">{p["pair"]}</div>
    <div class="pair-vote" style="color:{vote_color}">투표: {p["vote"]}</div>
    <div class="pair-rs">RS <b style="color:{vote_color}">{p["rs"]*100:+.2f}%</b></div>
  </div>
  <table class="pair-table">
    <thead><tr><th>구분</th><th style="text-align:right">6M 로그수익</th></tr></thead>
    <tbody>
      <tr><td>KR ({p['kr_code']})</td><td class="num">{p['kr_ret']*100:+.1f}%</td></tr>
      <tr><td>US ({p['us_code']})</td><td class="num">{p['us_ret']*100:+.1f}%</td></tr>
      <tr><td><b>차이 (RS)</b></td><td class="num" style="color:{diff_color};font-weight:700">{p['rs']*100:+.2f}%</td></tr>
    </tbody>
  </table>
</div>
"""
    return cards


def _recent_table(bt: pd.DataFrame, n: int = 12) -> str:
    recent = bt.tail(n).iloc[::-1]
    rows = ""
    for _, r in recent.iterrows():
        bg = "#FFF0F1" if r["signal"] == "KR" else ("#EEF1F8" if r["signal"] == "US" else "#F8F9FA")
        kr_color = "#16A34A" if r["kr_return"] > 0 else "#DC2626"
        us_color = "#16A34A" if r["us_return"] > 0 else "#DC2626"
        strat_color = "#16A34A" if r["strategy_return"] > 0 else "#DC2626"
        excess = r["strategy_return"] - r["blend_return"]
        exc_color = "#16A34A" if excess > 0 else "#DC2626"
        cost_mark = f' <span style="color:#94A3B8;font-size:0.7rem">-{r["cost"]*100:.2f}%</span>' if r["cost"] > 0 else ""
        rows += (
            f'<tr style="background:{bg}">'
            f'<td>{r["as_of"]}</td>'
            f'<td class="num">{r["mean_rs"]*100:+.2f}%</td>'
            f'<td class="num">{r["fx_tilt"]:+.3f}</td>'
            f'<td class="num"><b>{r["agg"]:+.4f}</b></td>'
            f'<td style="text-align:center">{_badge(r["signal"], "sm")}{cost_mark}</td>'
            f'<td class="num" style="color:{kr_color}">{r["kr_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{us_color}">{r["us_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{strat_color};font-weight:700">{r["strategy_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{exc_color}">{excess*100:+.1f}%</td>'
            f'</tr>'
        )
    return rows


def _perf_table(m_strat, m_bench) -> str:
    def _row(label, m, mark=""):
        return (
            f'<tr><td>{mark}{label}</td>'
            f'<td class="num">{m["total_return"]*100:+.1f}%</td>'
            f'<td class="num">{m["ann_return"]*100:+.1f}%</td>'
            f'<td class="num">{m["ann_vol"]*100:.1f}%</td>'
            f'<td class="num"><b>{m["sharpe"]:.2f}</b></td>'
            f'<td class="num" style="color:#DC2626">{m["mdd"]*100:.1f}%</td>'
            f'<td class="num">{m["win_rate"]*100:.0f}%</td>'
            f'</tr>'
        )
    return (
        '<table><thead><tr><th>전략</th><th>Total</th><th>CAGR</th>'
        '<th>연변동</th><th>Sharpe</th><th>MDD</th><th>Win%</th></tr></thead><tbody>'
        + _row("★ MAIN (6M-only)", m_strat, "★ ")
        + _row("  50/50 Blend", m_bench["Blend"])
        + _row("  KOSPI", m_bench["KOSPI"])
        + _row("  S&P500", m_bench["SP500"])
        + '</tbody></table>'
    )


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main() -> None:
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    pivot = load_all_data()
    print(f"[load] {pivot.shape} · {pivot.index.min().date()} ~ {pivot.index.max().date()}")

    month_ends = pivot.resample("BME").last().index
    latest = month_ends[-1] if month_ends[-1] <= pivot.index.max() else month_ends[-2]
    d = decompose(pivot, latest)
    print(f"[signal] {latest.date()} → {d['signal']} (agg={d['agg']:+.4f})")

    bt = run_backtest(PRIMARY_CFG, pivot)
    m_strat = perf(bt["strategy_return"], "MAIN")
    m_bench = {
        "Blend":  perf(bt["blend_return"], "Blend"),
        "KOSPI":  perf(bt["kr_return"],    "KOSPI"),
        "SP500":  perf(bt["us_return"],    "SP500"),
    }

    dates = bt["as_of"].tolist()

    def _cum(col):
        return ((1 + bt[col]).cumprod() - 1).round(4).tolist()

    sig_colors = [_COLOR[s] for s in bt["signal"].tolist()]

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<title>Sector Asset Allocation · Signal Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; background: #F3F4F6;
         color: #1F2937; padding: 20px; max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; font-weight: 900; margin-bottom: 4px; color: #111827; }}
  .subtitle {{ color: #6B7280; font-size: 0.88rem; margin-bottom: 20px; }}
  h2 {{ font-size: 1.05rem; color: #111827; margin: 28px 0 12px; padding-left: 12px;
        border-left: 4px solid #F58220; font-weight: 700; }}

  .hero {{ border-radius: 14px; padding: 24px 28px; color: #fff; margin-bottom: 18px;
          box-shadow: 0 4px 14px rgba(0,0,0,0.12); }}
  .hero-row {{ display: grid; grid-template-columns: auto 1.1fr auto auto auto;
              gap: 32px; align-items: center; }}
  .hero-label {{ font-size: 0.7rem; opacity: 0.8; letter-spacing: 0.05em; text-transform: uppercase; }}
  .hero-value {{ font-size: 1.6rem; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: 4px; }}
  .hero-sub {{ font-size: 0.75rem; opacity: 0.75; }}

  .formula-box {{ background: #fff; border-radius: 12px; padding: 20px; border: 1px solid #E5E7EB; }}
  .formula-row {{ display: flex; align-items: center; justify-content: space-around; gap: 8px; }}
  .formula-item {{ text-align: center; flex: 1; }}
  .formula-label {{ font-size: 0.78rem; color: #6B7280; margin-bottom: 6px; font-weight: 600; }}
  .formula-value {{ font-size: 1.5rem; font-weight: 800; font-variant-numeric: tabular-nums; }}
  .formula-sub {{ font-size: 0.72rem; color: #9CA3AF; margin-top: 4px; }}
  .formula-plus {{ font-size: 1.8rem; color: #D1D5DB; font-weight: 300; }}
  .contribution-bar {{ display: flex; height: 22px; border-radius: 6px; overflow: hidden;
                       margin-top: 16px; font-size: 0.72rem; color: #fff; font-weight: 700; }}
  .contribution-bar > div {{ display: flex; align-items: center; justify-content: center; padding: 0 8px; }}

  .pair-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
  .pair-card {{ background: #fff; border-radius: 10px; padding: 14px; border: 1px solid #E5E7EB; }}
  .pair-header {{ padding: 8px 12px; margin-bottom: 10px; background: #F9FAFB; border-radius: 6px; }}
  .pair-name {{ font-weight: 800; font-size: 1rem; color: #111827; }}
  .pair-vote {{ font-size: 0.75rem; font-weight: 700; margin-top: 2px; }}
  .pair-rs {{ font-size: 0.8rem; color: #4B5563; margin-top: 4px; }}
  .pair-table {{ width: 100%; font-size: 0.75rem; }}
  .pair-table th {{ background: #F3F4F6; padding: 5px 7px; text-align: left; color: #6B7280; font-weight: 600; }}
  .pair-table td {{ padding: 5px 7px; border-bottom: 1px solid #F9FAFB; }}
  .pair-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}

  .canvas-wrap {{ background: #fff; padding: 16px; border-radius: 10px; border: 1px solid #E5E7EB; }}

  table {{ width: 100%; background: #fff; border-collapse: collapse; font-size: 0.85rem;
          border-radius: 10px; overflow: hidden; border: 1px solid #E5E7EB; }}
  th {{ background: #F3F4F6; padding: 10px 12px; text-align: left; font-weight: 600; color: #374151; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #F9FAFB; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr:last-child td {{ border-bottom: none; }}

  .nav {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
  .nav a {{ padding: 6px 14px; background: #fff; border: 1px solid #E5E7EB; border-radius: 20px;
           color: #374151; text-decoration: none; font-size: 0.82rem; transition: all 0.15s; }}
  .nav a:hover {{ background: #F58220; color: #fff; border-color: #F58220; }}
  .nav a.primary {{ background: #F58220; color: #fff; border-color: #F58220; font-weight: 600; }}

  .note-box {{ background: #FFF7ED; border: 1px solid #FCD34D; border-radius: 8px;
               padding: 12px 16px; font-size: 0.82rem; color: #78350F; margin: 16px 0; line-height: 1.6; }}
  .footer {{ text-align: center; color: #9CA3AF; font-size: 0.75rem; margin-top: 32px; padding: 16px; }}
</style>
</head>
<body>

<h1>Sector Asset Allocation — Signal Dashboard</h1>
<div class="subtitle">
  MAIN = 6M-only lookback (Sharpe {m_strat['sharpe']:.2f}) · 4 GICS 페어 (IT/FIN/ENERGY/STAPLES) + USDKRW 3M 30% ·
  월말 리밸런싱 · 30 bp 비용 · Paper Trading 검증 단계
</div>

<div class="nav">
  <a class="primary" href="#hero">현재 시그널</a>
  <a href="#decompose">신호 분해</a>
  <a href="#timeline">히스토리</a>
  <a href="#perf">성과</a>
  <a href="#recent">최근 12개월</a>
  <a href="sector_asset_allocation/FORMAL_REPORT.pdf">📄 정식 보고서 (PDF)</a>
  <a href="sector_asset_allocation/README.html">📒 Research Notes</a>
  <a href="../index.html">← Portfolio 홈</a>
</div>

<div id="hero">{_hero(d)}</div>

<h2 id="decompose">① 신호 분해 — agg 가 어떻게 만들어졌나</h2>
{_formula_block(d)}

<h2>② 섹터 페어별 RS (6개월 로그수익 차)</h2>
<div class="pair-grid">{_pair_cards(d)}</div>

<h2 id="timeline">③ agg 히스토리 (2011-04 ~ 현재)</h2>
<div class="canvas-wrap"><canvas id="aggChart" style="max-height:280px"></canvas></div>
<p style="color:#6B7280;font-size:0.78rem;margin-top:6px">
  주황선 = agg 점수. 점은 해당 월 시그널 색 (KR=빨강, US=남색, Neutral=회색).
  점선 = 임계 ±{PARAMS['tau']}. 초과 시 포지션 전환.
</p>

<h2>④ 누적 수익 곡선</h2>
<div class="canvas-wrap"><canvas id="cumChart" style="max-height:360px"></canvas></div>

<h2 id="perf">⑤ 성과 비교</h2>
{_perf_table(m_strat, m_bench)}

<h2 id="recent">⑥ 최근 12개월 시그널 상세</h2>
<table>
  <thead><tr>
    <th>월말</th><th>평균 RS</th><th>FX tilt</th><th>agg</th>
    <th style="text-align:center">시그널</th>
    <th>KOSPI</th><th>S&P500</th><th>전략</th><th>vs Blend</th>
  </tr></thead>
  <tbody>{_recent_table(bt, 12)}</tbody>
</table>

<div class="note-box">
  <b>참고: ALERT 이중 시그널 실험</b><br>
  과거 "Champion [1,3,6] lookback 을 ALERT 보조 시그널로" 하는 이중 구조를 검토했으나,
  63개 변형 실증 결과 <b>MAIN 단독 Sharpe 0.97 을 넘는 조합 없음</b> 확인 → 폐기.
  상세는 <a href="sector_asset_allocation/outputs/alert_explorer.html">ALERT Explorer</a> 참조.
</div>

<div class="footer">
  Signal Dashboard · 기준일 {latest.strftime("%Y-%m-%d")} ·
  검증: Walk-forward OOS · Parameter Sensitivity · Rolling OOS · ALERT 탐색 (모두 완료)
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  const dates = {json.dumps(dates)};
  const aggSeries = {json.dumps(bt["agg"].tolist())};
  const sigColors = {json.dumps(sig_colors)};
  const tau = {PARAMS['tau']};

  new Chart(document.getElementById('aggChart'), {{
    type: 'line',
    data: {{ labels: dates, datasets: [
      {{ label: 'agg', data: aggSeries,
         borderColor: '#F58220', backgroundColor: 'rgba(245,130,32,0.08)', fill: true,
         tension: 0.15, borderWidth: 2,
         pointRadius: dates.map((_, i) => i === dates.length-1 ? 6 : 2),
         pointBackgroundColor: sigColors, pointBorderColor: sigColors, pointBorderWidth: 1 }},
      {{ label: '임계 +τ', data: Array(dates.length).fill(tau),
         borderColor: 'rgba(0,0,0,0.25)', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false }},
      {{ label: '임계 -τ', data: Array(dates.length).fill(-tau),
         borderColor: 'rgba(0,0,0,0.25)', borderWidth: 1, borderDash: [4,4], pointRadius: 0, fill: false }},
    ]}},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line' }} }} }},
                scales: {{ y: {{ title: {{ display: true, text: 'agg' }}, ticks: {{ callback: v => v.toFixed(3) }} }},
                          x: {{ ticks: {{ maxTicksLimit: 14 }} }} }} }}
  }});

  const cumStrat = {json.dumps(_cum("strategy_return"))};
  const cumBlend = {json.dumps(_cum("blend_return"))};
  const cumKospi = {json.dumps(_cum("kr_return"))};
  const cumSp500 = {json.dumps(_cum("us_return"))};

  new Chart(document.getElementById('cumChart'), {{
    type: 'line',
    data: {{ labels: dates, datasets: [
      {{ label: '★ MAIN (6M-only)', data: cumStrat, borderColor: '#F58220', borderWidth: 2.8, tension: 0.15, backgroundColor: 'transparent' }},
      {{ label: '50/50 Blend',      data: cumBlend, borderColor: '#8B5CF6', borderWidth: 1.0, tension: 0.1, borderDash: [5,4], backgroundColor: 'transparent' }},
      {{ label: 'KOSPI',            data: cumKospi, borderColor: '#E63946', borderWidth: 0.9, tension: 0.1, borderDash: [2,3], backgroundColor: 'transparent' }},
      {{ label: 'S&P500',           data: cumSp500, borderColor: '#1D3557', borderWidth: 0.9, tension: 0.1, borderDash: [2,3], backgroundColor: 'transparent' }},
    ]}},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line' }} }} }},
                scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }}, x: {{ ticks: {{ maxTicksLimit: 14 }} }} }} }}
  }});
</script>

</body></html>
"""
    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    print(f"[write] {DASHBOARD_PATH}")


if __name__ == "__main__":
    main()
