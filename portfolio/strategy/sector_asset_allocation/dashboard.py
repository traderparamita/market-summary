"""시그널 중심 대시보드 — output/portfolio/strategy/sector_asset_allocation.html.

운용역 한눈 점검용. 가장 중요한 것은 "이번 달 시그널이 어떻게 나왔는가" 이다.

구성:
  [HERO]       현재 시그널 + 핵심 수치 큰 카드
  [DECOMPOSE]  페어별 RS 기여 + FX tilt → agg 수식 시각화
  [HISTORY]    agg 점수 & 시그널 타임라인 (임계 ±0.02 표시)
  [PERF]       핵심 성과 (local / KRW 환오픈 각각)
  [TABLE]      최근 12개월 시그널 상세

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
    SECTOR_PAIRS_ECO4, LOOKBACK_MONTHS,
    compute_rs_list, compute_fx_tilt,
    log_return, pct_return,
    KOSPI_CODE, SP500_CODE, FX_USDKRW,
)

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_PATH = ROOT / "output" / "portfolio" / "strategy" / "sector_asset_allocation.html"

# 챔피언 파라미터 (고정)
PARAMS = {
    "w_rs": 0.7,
    "w_fx": 0.3,
    "tau": 0.02,
    "fx_scale": 0.03,
    "fx_to_rs_scale": 0.02,
    "cost_bps": 30,
}


# ─────────────────────────────────────────────────────
# 현재 시그널 분해 (월말 → 상세 기여)
# ─────────────────────────────────────────────────────

def decompose_signal(pivot: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    """해당 월말 시그널을 완전 분해해서 반환."""
    # 페어별 RS 상세 (1M/3M/6M 개별 + 평균)
    pair_details = []
    for kr_code, us_code, label in SECTOR_PAIRS_ECO4:
        if kr_code not in pivot.columns or us_code not in pivot.columns:
            continue
        entry = {"pair": label, "kr_code": kr_code, "us_code": us_code, "lookbacks": {}}
        diffs = []
        for m in LOOKBACK_MONTHS:
            kr = log_return(pivot[kr_code], as_of, m)
            us = log_return(pivot[us_code], as_of, m)
            if kr is None or us is None:
                continue
            diffs.append(kr - us)
            entry["lookbacks"][f"{m}M"] = {
                "kr": kr, "us": us, "diff": kr - us,
            }
        if diffs:
            entry["rs"] = sum(diffs) / len(diffs)
            pair_details.append(entry)

    mean_rs = sum(p["rs"] for p in pair_details) / len(pair_details) if pair_details else 0.0

    # FX tilt
    usdkrw_return = pct_return(pivot.get(FX_USDKRW), as_of, 3)
    fx_tilt = math.tanh(usdkrw_return / PARAMS["fx_scale"]) if usdkrw_return is not None else 0.0

    # Agg
    rs_contrib = PARAMS["w_rs"] * mean_rs
    fx_contrib = PARAMS["w_fx"] * fx_tilt * PARAMS["fx_to_rs_scale"]
    agg = rs_contrib + fx_contrib

    # 시그널
    if agg > PARAMS["tau"]:
        signal = "KR"
    elif agg < -PARAMS["tau"]:
        signal = "US"
    else:
        signal = "Neutral"

    # 페어별 기여 (mean_rs 에서 각 페어의 % 기여)
    if pair_details:
        for p in pair_details:
            p["rs_contrib"] = p["rs"] / len(pair_details) * PARAMS["w_rs"]
            p["vote"] = "KR" if p["rs"] > 0 else ("US" if p["rs"] < 0 else "—")

    return {
        "as_of":        as_of,
        "pairs":        pair_details,
        "mean_rs":      mean_rs,
        "rs_contrib":   rs_contrib,
        "usdkrw_3m":    usdkrw_return,
        "fx_tilt":      fx_tilt,
        "fx_contrib":   fx_contrib,
        "agg":          agg,
        "tau":          PARAMS["tau"],
        "signal":       signal,
    }


# ─────────────────────────────────────────────────────
# HTML 조각 빌더
# ─────────────────────────────────────────────────────

_COLOR = {"KR": "#E63946", "US": "#1D3557", "Neutral": "#6C757D"}
_BG    = {"KR": "linear-gradient(135deg,#7F1D1D,#E63946)",
          "US": "linear-gradient(135deg,#1e3a5f,#1D3557)",
          "Neutral": "linear-gradient(135deg,#374151,#6B7280)"}


def _signal_badge(sig: str, size: str = "md") -> str:
    fs = "0.72rem" if size == "sm" else "0.95rem" if size == "md" else "1.4rem"
    pad = "2px 9px" if size == "sm" else "4px 16px" if size == "md" else "10px 28px"
    return (
        f'<span style="background:{_COLOR.get(sig)};color:#fff;padding:{pad};'
        f'border-radius:30px;font-size:{fs};font-weight:800;letter-spacing:.04em">{sig}</span>'
    )


def _hero_card(d: dict) -> str:
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
      <div class="hero-label">현재 시그널 (다음 달 포지션)</div>
      <div style="margin-top:4px">{_signal_badge(d["signal"], "lg")}</div>
    </div>
    <div>
      <div class="hero-label">합성 점수 agg</div>
      <div class="hero-value">{d["agg"]:+.4f}</div>
      <div class="hero-sub">임계 ±{d["tau"]}</div>
    </div>
    <div>
      <div class="hero-label">평균 RS (4쌍)</div>
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

    # 기여도 %
    total_abs = abs(d["rs_contrib"]) + abs(d["fx_contrib"])
    rs_share = abs(d["rs_contrib"]) / total_abs * 100 if total_abs > 0 else 50
    fx_share = abs(d["fx_contrib"]) / total_abs * 100 if total_abs > 0 else 50

    return f"""
<div class="formula-box">
  <div class="formula-row">
    <div class="formula-item">
      <div class="formula-label">RS 기여 (가중 0.70)</div>
      <div class="formula-value" style="color:{'#16A34A' if d['rs_contrib']>0 else '#DC2626'}">{rs_pct:+.3f}%</div>
      <div class="formula-sub">= 0.70 × {d['mean_rs']*100:+.2f}%</div>
    </div>
    <div class="formula-plus">+</div>
    <div class="formula-item">
      <div class="formula-label">FX 기여 (가중 0.30)</div>
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
  <div class="formula-legend">
    <span><span class="dot" style="background:#F58220"></span>RS 기여 {rs_share:.0f}%</span>
    <span><span class="dot" style="background:#1D3557"></span>FX 기여 {fx_share:.0f}%</span>
  </div>
</div>
"""


def _pair_cards(d: dict) -> str:
    cards = ""
    for p in d["pairs"]:
        vote_color = _COLOR["KR"] if p["rs"] > 0 else _COLOR["US"]
        sub_rows = ""
        for lb, data in p["lookbacks"].items():
            diff_color = "#16A34A" if data["diff"] > 0 else "#DC2626"
            sub_rows += (
                f'<tr><td>{lb}</td>'
                f'<td class="num">{data["kr"]*100:+.1f}%</td>'
                f'<td class="num">{data["us"]*100:+.1f}%</td>'
                f'<td class="num" style="color:{diff_color};font-weight:700">{data["diff"]*100:+.2f}%</td>'
                f'</tr>'
            )
        cards += f"""
<div class="pair-card">
  <div class="pair-header" style="border-left:4px solid {vote_color}">
    <div class="pair-name">{p["pair"]}</div>
    <div class="pair-vote" style="color:{vote_color}">투표: {p["vote"]}</div>
    <div class="pair-rs">평균 RS <b style="color:{vote_color}">{p["rs"]*100:+.2f}%</b></div>
  </div>
  <table class="pair-table">
    <thead><tr><th>룩백</th><th>KR</th><th>US</th><th>RS</th></tr></thead>
    <tbody>{sub_rows}</tbody>
  </table>
</div>
"""
    return cards


def _recent_signals_table(bt: pd.DataFrame, n: int = 12) -> str:
    recent = bt.tail(n).iloc[::-1]
    rows = ""
    for _, r in recent.iterrows():
        sig = r["signal"]
        bg = {"KR": "#FFF0F1", "US": "#EEF1F8", "Neutral": "#F8F9FA"}[sig]
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
            f'<td style="text-align:center">{_signal_badge(sig, "sm")}{cost_mark}</td>'
            f'<td class="num" style="color:{kr_color}">{r["kr_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{us_color}">{r["us_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{strat_color};font-weight:700">{r["strategy_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{exc_color}">{excess*100:+.1f}%</td>'
            f'</tr>'
        )
    return rows


def _perf_table(metrics_local: dict, metrics_krw: dict) -> str:
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
        + _row("★ 전략 (local, USD 기준)", metrics_local["Strategy"], "★ ")
        + _row("★ 전략 (KRW 환오픈)",       metrics_krw["Strategy"],   "★ ")
        + _row("50/50 Blend (local)",     metrics_local["Blend"])
        + _row("50/50 Blend (KRW 환오픈)", metrics_krw["Blend"])
        + _row("KOSPI",                    metrics_local["KOSPI"])
        + _row("S&P500 (USD)",             metrics_local["SP500"])
        + _row("S&P500 (KRW 환오픈)",      metrics_krw["SP500"])
        + '</tbody></table>'
    )


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main() -> None:
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)

    pivot = load_all_data()
    print(f"[load] {pivot.shape} · {pivot.index.min().date()} ~ {pivot.index.max().date()}")

    # 최신 월말 시그널
    month_ends = pivot.resample("BME").last().index
    latest = month_ends[-1] if month_ends[-1] <= pivot.index.max() else month_ends[-2]
    decomp = decompose_signal(pivot, latest)
    print(f"[signal] {latest.date()} → {decomp['signal']} (agg={decomp['agg']:+.4f})")

    # 백테스트 (local + KRW 환오픈)
    cfg_local = Config(name="Strategy (local)", pairs=SECTOR_PAIRS_ECO4,
                       w_rs=0.7, w_fx=0.3, fx_source="usdkrw", tau=0.02,
                       base_currency="local")
    cfg_krw   = Config(name="Strategy (KRW 환오픈)", pairs=SECTOR_PAIRS_ECO4,
                       w_rs=0.7, w_fx=0.3, fx_source="usdkrw", tau=0.02,
                       base_currency="krw_unhedged")
    bt_local = run_backtest(cfg_local, pivot)
    bt_krw   = run_backtest(cfg_krw,   pivot)

    metrics_local = {
        "Strategy": perf(bt_local["strategy_return"], "Strategy"),
        "Blend":    perf(bt_local["blend_return"],    "Blend"),
        "KOSPI":    perf(bt_local["kr_return"],       "KOSPI"),
        "SP500":    perf(bt_local["us_return"],       "SP500"),
    }
    metrics_krw = {
        "Strategy": perf(bt_krw["strategy_return"], "Strategy"),
        "Blend":    perf(bt_krw["blend_return"],    "Blend"),
        "SP500":    perf(bt_krw["us_return"],       "SP500"),
    }

    # 차트 데이터
    dates = bt_local["as_of"].tolist()
    agg_series    = bt_local["agg"].tolist()
    mean_rs_series = bt_local["mean_rs"].tolist()
    fx_tilt_series = [f * 0.02 for f in bt_local["fx_tilt"].tolist()]  # RS 스케일로

    def _cum(bt, col):
        return ((1 + bt[col]).cumprod() - 1).round(4).tolist()

    # 시그널별 색 (타임라인 점)
    sig_colors = [_COLOR[s] for s in bt_local["signal"].tolist()]

    # ── HTML ─────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Sector Asset Allocation — 시그널 대시보드</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; background: #F3F4F6;
         color: #1F2937; padding: 20px; max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; font-weight: 900; margin-bottom: 4px; color: #111827; }}
  .subtitle {{ color: #6B7280; font-size: 0.88rem; margin-bottom: 20px; }}
  h2 {{ font-size: 1.05rem; color: #111827; margin: 28px 0 12px;
        padding-left: 12px; border-left: 4px solid #F58220; font-weight: 700; }}
  .muted {{ color: #6B7280; font-size: 0.8rem; margin-top: 4px; }}

  .hero {{ border-radius: 14px; padding: 24px 28px; color: #fff; margin-bottom: 16px;
          box-shadow: 0 4px 14px rgba(0,0,0,0.12); }}
  .hero-row {{ display: grid; grid-template-columns: auto 1.3fr auto auto auto;
              gap: 32px; align-items: center; }}
  .hero-label {{ font-size: 0.72rem; opacity: 0.8; letter-spacing: 0.05em; text-transform: uppercase; }}
  .hero-value {{ font-size: 1.6rem; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: 4px; }}
  .hero-sub {{ font-size: 0.75rem; opacity: 0.75; }}

  .formula-box {{ background: #fff; border-radius: 12px; padding: 24px;
                  border: 1px solid #E5E7EB; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
  .formula-row {{ display: flex; align-items: center; justify-content: space-around; gap: 8px; }}
  .formula-item {{ text-align: center; flex: 1; }}
  .formula-label {{ font-size: 0.78rem; color: #6B7280; margin-bottom: 6px; font-weight: 600; }}
  .formula-value {{ font-size: 1.5rem; font-weight: 800; font-variant-numeric: tabular-nums; }}
  .formula-sub {{ font-size: 0.72rem; color: #9CA3AF; margin-top: 4px; }}
  .formula-plus {{ font-size: 1.8rem; color: #D1D5DB; font-weight: 300; }}
  .contribution-bar {{ display: flex; height: 24px; border-radius: 6px; overflow: hidden;
                       margin-top: 20px; font-size: 0.75rem; color: #fff;
                       align-items: center; justify-content: center; font-weight: 700; }}
  .contribution-bar > div {{ height: 100%; display: flex; align-items: center;
                             justify-content: center; padding: 0 8px; }}
  .formula-legend {{ display: flex; gap: 16px; justify-content: center; margin-top: 8px;
                     font-size: 0.78rem; color: #6B7280; }}
  .formula-legend .dot {{ display: inline-block; width: 10px; height: 10px;
                          border-radius: 50%; margin-right: 4px; vertical-align: middle; }}

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

  .footer {{ text-align: center; color: #9CA3AF; font-size: 0.75rem; margin-top: 32px; padding: 16px; }}
</style>
</head>
<body>

<h1>Sector Asset Allocation — 시그널 대시보드</h1>
<div class="subtitle">
  4 GICS 섹터 페어 (IT·FIN·ENERGY·STAPLES) 상대강도 + USDKRW 3M 모멘텀 · 월말 리밸런싱 ·
  거래비용 30 bp · 백테스트 {BACKTEST_START} ~ {latest.strftime("%Y-%m-%d")}
</div>

<div class="nav">
  <a class="primary" href="#hero">현재 시그널</a>
  <a href="#decompose">신호 분해</a>
  <a href="#timeline">히스토리</a>
  <a href="#perf">성과</a>
  <a href="#recent">최근 12개월</a>
  <a href="sector_asset_allocation/FORMAL_REPORT.pdf">📄 정식 보고서 (PDF)</a>
  <a href="sector_asset_allocation/README.md">📒 Research Notes</a>
  <a href="../index.html">← Portfolio 홈</a>
</div>

<div id="hero">{_hero_card(decomp)}</div>

<h2 id="decompose">① 신호 분해 — agg 가 어떻게 만들어졌나</h2>
{_formula_block(decomp)}

<h2>② 섹터 페어별 RS (4쌍 각각의 기여)</h2>
<div class="pair-grid">{_pair_cards(decomp)}</div>

<h2 id="timeline">③ 시그널 히스토리 (2011-04 ~ 현재)</h2>
<div class="canvas-wrap" style="margin-bottom:10px">
  <canvas id="aggChart" style="max-height:280px"></canvas>
</div>
<div class="muted">- 주황색선 (agg): 합성 점수. ±{PARAMS["tau"]} 임계를 넘으면 포지션 전환.<br>
  - 녹색선 (RS 기여): 섹터 상대강도의 raw 평균<br>
  - 파란선 (FX 기여): USDKRW 모멘텀의 RS 스케일 변환 값</div>

<h2>④ 누적 수익 곡선 (Local 기준 vs KRW 환오픈)</h2>
<div class="canvas-wrap">
  <canvas id="cumChart" style="max-height:340px"></canvas>
</div>

<h2 id="perf">⑤ 성과 비교 — Local vs KRW 환오픈</h2>
{_perf_table(metrics_local, metrics_krw)}
<div class="muted">★ = 본 전략 · KRW 환오픈 = KR 투자자가 US 포지션을 환노출로 보유 (USDKRW 자연 노출)</div>

<h2 id="recent">⑥ 최근 12개월 시그널 상세</h2>
<table>
  <thead><tr>
    <th>월말</th><th>평균 RS</th><th>FX tilt</th><th>agg</th>
    <th style="text-align:center">시그널</th>
    <th>KOSPI</th><th>S&P500</th><th>전략</th><th>vs Blend</th>
  </tr></thead>
  <tbody>{_recent_signals_table(bt_local, 12)}</tbody>
</table>

<div class="footer">
  Sector Asset Allocation Dashboard · 마지막 갱신: {pivot.index.max().strftime("%Y-%m-%d")} ·
  코드: <code>portfolio/strategy/sector_asset_allocation/</code>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  const dates = {json.dumps(dates)};
  const aggSeries = {json.dumps(agg_series)};
  const meanRsSeries = {json.dumps(mean_rs_series)};
  const fxTiltSeries = {json.dumps(fx_tilt_series)};
  const sigColors = {json.dumps(sig_colors)};
  const tau = {PARAMS["tau"]};

  // Agg 히스토리 + 시그널 색 점
  new Chart(document.getElementById('aggChart'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label: 'agg (합성)', data: aggSeries, borderColor: '#F58220',
           backgroundColor: 'rgba(245,130,32,0.08)', fill: true,
           tension: 0.15, borderWidth: 2,
           pointRadius: dates.map((_, i) => i === dates.length-1 ? 6 : 2),
           pointBackgroundColor: sigColors, pointBorderColor: sigColors, pointBorderWidth: 1 }},
        {{ label: 'RS 기여 (0.7 × mean_RS)', data: meanRsSeries.map(v => v * 0.7),
           borderColor: '#059669', backgroundColor: 'transparent',
           tension: 0.1, borderWidth: 1.2, borderDash: [5, 3], pointRadius: 0 }},
        {{ label: 'FX 기여 (0.3 × fx_tilt × 0.02)', data: fxTiltSeries.map(v => v * 0.3),
           borderColor: '#1D3557', backgroundColor: 'transparent',
           tension: 0.1, borderWidth: 1.2, borderDash: [5, 3], pointRadius: 0 }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line', font: {{size:10}} }} }},
        annotation: {{
          annotations: {{
            tauPos: {{ type: 'line', yMin: tau, yMax: tau,
                      borderColor: 'rgba(0,0,0,0.25)', borderWidth: 1, borderDash: [4, 4] }},
            tauNeg: {{ type: 'line', yMin: -tau, yMax: -tau,
                      borderColor: 'rgba(0,0,0,0.25)', borderWidth: 1, borderDash: [4, 4] }}
          }}
        }}
      }},
      scales: {{
        y: {{ title: {{ display: true, text: 'agg score' }},
             ticks: {{ callback: v => v.toFixed(3) }} }},
        x: {{ ticks: {{ maxTicksLimit: 14 }} }}
      }}
    }}
  }});

  // 누적 수익
  const cumLocal = {json.dumps(_cum(bt_local, "strategy_return"))};
  const cumKrw   = {json.dumps(_cum(bt_krw,   "strategy_return"))};
  const cumBlendLocal = {json.dumps(_cum(bt_local, "blend_return"))};
  const cumBlendKrw   = {json.dumps(_cum(bt_krw,   "blend_return"))};
  const cumKospi      = {json.dumps(_cum(bt_local, "kr_return"))};
  const cumSp500Local = {json.dumps(_cum(bt_local, "us_return"))};
  const cumSp500Krw   = {json.dumps(_cum(bt_krw,   "us_return"))};

  new Chart(document.getElementById('cumChart'), {{
    type: 'line',
    data: {{ labels: dates, datasets: [
      {{ label: '★ 전략 (KRW 환오픈)',   data: cumKrw,        borderColor: '#F58220', backgroundColor: 'transparent', borderWidth: 2.5, tension: 0.15 }},
      {{ label: '★ 전략 (local)',        data: cumLocal,      borderColor: '#DC2626', backgroundColor: 'transparent', borderWidth: 1.8, tension: 0.15 }},
      {{ label: 'S&P500 (KRW 환오픈)',   data: cumSp500Krw,   borderColor: '#059669', backgroundColor: 'transparent', borderWidth: 1.2, tension: 0.1, borderDash: [5,4] }},
      {{ label: 'S&P500 (USD)',         data: cumSp500Local, borderColor: '#1D3557', backgroundColor: 'transparent', borderWidth: 1.0, tension: 0.1, borderDash: [3,3] }},
      {{ label: '50/50 Blend (KRW)',    data: cumBlendKrw,   borderColor: '#8B5CF6', backgroundColor: 'transparent', borderWidth: 1.0, tension: 0.1, borderDash: [2,3] }},
      {{ label: 'KOSPI',                 data: cumKospi,      borderColor: '#94A3B8', backgroundColor: 'transparent', borderWidth: 1.0, tension: 0.1, borderDash: [2,3] }},
    ]}},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line', font:{{size:10}} }} }} }},
      scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }}, x: {{ ticks: {{ maxTicksLimit: 14 }} }} }}
    }}
  }});
</script>

</body>
</html>
"""
    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    print(f"[write] {DASHBOARD_PATH}")


if __name__ == "__main__":
    main()
