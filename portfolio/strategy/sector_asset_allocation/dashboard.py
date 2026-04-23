"""시그널 대시보드 (v2) — 메인 6M-only + 보조 Champion.

운영 구조:
  PRIMARY  : 6M-only lookback (메인 시그널) — Sharpe 0.97
  SECONDARY: Champion [1,3,6] lookback (보조/경보) — 단기 조정 감지용

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

# 모델 파라미터 (공통)
COMMON_PARAMS = {
    "w_rs": 0.7, "w_fx": 0.3, "tau": 0.02,
    "fx_scale": 0.03, "fx_to_rs_scale": 0.02, "cost_bps": 30,
}

PRIMARY_CFG = Config(
    name="Primary (6M-only)",
    pairs=SECTOR_PAIRS_ECO4,
    w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
    tau=0.02, lookbacks=[6],
)

ALERT_CFG = Config(
    name="Alert (Champion [1,3,6])",
    pairs=SECTOR_PAIRS_ECO4,
    w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
    tau=0.02, lookbacks=[1, 3, 6],
)


# ─────────────────────────────────────────────────────
# 신호 분해
# ─────────────────────────────────────────────────────

def decompose(pivot: pd.DataFrame, as_of: pd.Timestamp, lookbacks: list[int]) -> dict:
    """해당 월말 시그널 완전 분해 (lookback 가변)."""
    pair_details = []
    for kr_code, us_code, label in SECTOR_PAIRS_ECO4:
        if kr_code not in pivot.columns or us_code not in pivot.columns:
            continue
        entry = {"pair": label, "kr_code": kr_code, "us_code": us_code, "lookbacks": {}}
        diffs = []
        for m in lookbacks:
            kr = log_return(pivot[kr_code], as_of, m)
            us = log_return(pivot[us_code], as_of, m)
            if kr is None or us is None:
                continue
            diffs.append(kr - us)
            entry["lookbacks"][f"{m}M"] = {"kr": kr, "us": us, "diff": kr - us}
        if diffs:
            entry["rs"] = sum(diffs) / len(diffs)
            entry["vote"] = "KR" if entry["rs"] > 0 else ("US" if entry["rs"] < 0 else "—")
            pair_details.append(entry)

    mean_rs = sum(p["rs"] for p in pair_details) / len(pair_details) if pair_details else 0.0

    usdkrw_r = pct_return(pivot.get(FX_USDKRW), as_of, 3)
    fx_tilt = math.tanh(usdkrw_r / COMMON_PARAMS["fx_scale"]) if usdkrw_r is not None else 0.0

    rs_contrib = COMMON_PARAMS["w_rs"] * mean_rs
    fx_contrib = COMMON_PARAMS["w_fx"] * fx_tilt * COMMON_PARAMS["fx_to_rs_scale"]
    agg = rs_contrib + fx_contrib

    tau = COMMON_PARAMS["tau"]
    signal = "KR" if agg > tau else ("US" if agg < -tau else "Neutral")

    return {
        "as_of": as_of, "pairs": pair_details,
        "mean_rs": mean_rs, "rs_contrib": rs_contrib,
        "usdkrw_3m": usdkrw_r, "fx_tilt": fx_tilt, "fx_contrib": fx_contrib,
        "agg": agg, "tau": tau, "signal": signal, "lookbacks": lookbacks,
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


def _primary_hero(d: dict) -> str:
    bg = _BG[d["signal"]]
    as_of = d["as_of"].strftime("%Y-%m-%d")
    return f"""
<div class="hero" style="background:{bg}">
  <div class="hero-badge">MAIN · 6M-only</div>
  <div class="hero-row">
    <div>
      <div class="hero-label">기준일</div>
      <div class="hero-value" style="font-size:1.3rem">{as_of}</div>
    </div>
    <div>
      <div class="hero-label">메인 시그널</div>
      <div style="margin-top:4px">{_badge(d["signal"], "lg")}</div>
    </div>
    <div>
      <div class="hero-label">agg</div>
      <div class="hero-value">{d["agg"]:+.4f}</div>
      <div class="hero-sub">임계 ±{d["tau"]}</div>
    </div>
    <div>
      <div class="hero-label">평균 RS (6M 로그차)</div>
      <div class="hero-value">{d["mean_rs"]*100:+.2f}%</div>
    </div>
    <div>
      <div class="hero-label">FX tilt</div>
      <div class="hero-value">{d["fx_tilt"]:+.3f}</div>
      <div class="hero-sub">{d["usdkrw_3m"]*100:+.2f}% USDKRW 3M</div>
    </div>
  </div>
</div>
"""


def _alert_card(d: dict, primary_sig: str) -> str:
    agree = d["signal"] == primary_sig
    border = "#10B981" if agree else "#DC2626"
    status_icon = "일치" if agree else "⚠ 불일치"
    status_color = "#065F46" if agree else "#991B1B"
    bg = "#ECFDF5" if agree else "#FEF2F2"

    return f"""
<div class="alert-card" style="border:2px solid {border};background:{bg}">
  <div class="alert-left">
    <div class="alert-label">ALERT · Champion [1,3,6]</div>
    <div style="margin-top:4px">{_badge(d['signal'], 'md')}</div>
    <div class="alert-agg">agg {d['agg']:+.4f}</div>
  </div>
  <div class="alert-right">
    <div class="alert-status" style="color:{status_color}">{status_icon}</div>
    <div class="alert-desc">
      {'두 시그널이 같음. 확신 강함.' if agree else '메인·보조 시그널 불일치 — 단기 조정 가능성 주시 (2018 Q4 같은 패턴)'}
    </div>
  </div>
</div>
"""


def _formula_block(d: dict, title: str) -> str:
    rs_pct = d["rs_contrib"] * 100
    fx_pct = d["fx_contrib"] * 100
    agg_pct = d["agg"] * 100
    tau_pct = d["tau"] * 100
    total_abs = abs(d["rs_contrib"]) + abs(d["fx_contrib"])
    rs_share = abs(d["rs_contrib"]) / total_abs * 100 if total_abs > 0 else 50
    fx_share = 100 - rs_share

    return f"""
<h3>{title}</h3>
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
    <div class="pair-rs">RS <b style="color:{vote_color}">{p["rs"]*100:+.2f}%</b></div>
  </div>
  <table class="pair-table">
    <thead><tr><th>룩백</th><th>KR</th><th>US</th><th>RS</th></tr></thead>
    <tbody>{sub_rows}</tbody>
  </table>
</div>
"""
    return cards


def _recent_table(bt_primary: pd.DataFrame, bt_alert: pd.DataFrame, n: int = 12) -> str:
    merged = pd.merge(
        bt_primary[["as_of","signal","agg","strategy_return","kr_return","us_return","blend_return"]].rename(
            columns={"signal": "p_sig", "agg": "p_agg", "strategy_return": "p_ret"}),
        bt_alert[["as_of","signal","agg","strategy_return"]].rename(
            columns={"signal": "a_sig", "agg": "a_agg", "strategy_return": "a_ret"}),
        on="as_of", how="inner",
    )
    recent = merged.tail(n).iloc[::-1]

    rows = ""
    for _, r in recent.iterrows():
        agree = r["p_sig"] == r["a_sig"]
        bg = "#FFF0F1" if r["p_sig"] == "KR" else ("#EEF1F8" if r["p_sig"] == "US" else "#F8F9FA")
        agree_mark = "" if agree else '<span style="color:#DC2626;font-size:0.7rem">⚠</span>'
        p_color = "#16A34A" if r["p_ret"] > 0 else "#DC2626"
        a_color = "#16A34A" if r["a_ret"] > 0 else "#DC2626"
        excess = r["p_ret"] - r["blend_return"]
        exc_color = "#16A34A" if excess > 0 else "#DC2626"
        rows += (
            f'<tr style="background:{bg}">'
            f'<td>{r["as_of"]}</td>'
            f'<td class="num"><b>{r["p_agg"]:+.4f}</b></td>'
            f'<td style="text-align:center">{_badge(r["p_sig"], "sm")}</td>'
            f'<td class="num">{r["a_agg"]:+.4f}</td>'
            f'<td style="text-align:center">{_badge(r["a_sig"], "sm")} {agree_mark}</td>'
            f'<td class="num" style="color:{"#16A34A" if r["kr_return"]>0 else "#DC2626"}">{r["kr_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{"#16A34A" if r["us_return"]>0 else "#DC2626"}">{r["us_return"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{p_color};font-weight:700">{r["p_ret"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{a_color}">{r["a_ret"]*100:+.1f}%</td>'
            f'<td class="num" style="color:{exc_color}">{excess*100:+.1f}%</td>'
            f'</tr>'
        )
    return rows


def _perf_table(m_primary, m_alert, m_bench) -> str:
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
        + _row("★ MAIN — 6M-only", m_primary, "★ ")
        + _row("  ALERT — Champion [1,3,6]", m_alert)
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

    # 최신 월말
    month_ends = pivot.resample("BME").last().index
    latest = month_ends[-1] if month_ends[-1] <= pivot.index.max() else month_ends[-2]
    decomp_primary = decompose(pivot, latest, [6])
    decomp_alert   = decompose(pivot, latest, [1, 3, 6])
    print(f"[signal] {latest.date()}")
    print(f"         PRIMARY  (6M-only)  → {decomp_primary['signal']} (agg={decomp_primary['agg']:+.4f})")
    print(f"         ALERT    ([1,3,6])  → {decomp_alert['signal']} (agg={decomp_alert['agg']:+.4f})")

    # 백테스트
    bt_primary = run_backtest(PRIMARY_CFG, pivot)
    bt_alert   = run_backtest(ALERT_CFG,   pivot)

    m_primary = perf(bt_primary["strategy_return"], "Primary")
    m_alert   = perf(bt_alert["strategy_return"],   "Alert")
    m_bench = {
        "Blend":  perf(bt_primary["blend_return"], "Blend"),
        "KOSPI":  perf(bt_primary["kr_return"],    "KOSPI"),
        "SP500":  perf(bt_primary["us_return"],    "SP500"),
    }

    # 차트 데이터
    dates = bt_primary["as_of"].tolist()

    def _cum(bt, col):
        return ((1 + bt[col]).cumprod() - 1).round(4).tolist()

    # 시그널 일치 시계열 (1=agree, 0=disagree)
    sig_agree = []
    for i in range(len(bt_primary)):
        p = bt_primary["signal"].iloc[i]
        a = bt_alert["signal"].iloc[i] if i < len(bt_alert) else None
        sig_agree.append(1 if p == a else 0)
    agree_rate = sum(sig_agree) / len(sig_agree) if sig_agree else 0

    # agg 시계열
    primary_agg = bt_primary["agg"].tolist()
    alert_agg   = bt_alert["agg"].tolist()

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Sector Asset Allocation · Dual Signal Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; background: #F3F4F6;
         color: #1F2937; padding: 20px; max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; font-weight: 900; margin-bottom: 4px; color: #111827; }}
  .subtitle {{ color: #6B7280; font-size: 0.88rem; margin-bottom: 20px; }}
  .status-banner {{ background: #FEF3C7; border: 1px solid #F59E0B; border-radius: 8px;
                    padding: 10px 16px; font-size: 0.85rem; color: #92400E; margin-bottom: 14px;
                    display: flex; align-items: center; gap: 10px; }}
  h2 {{ font-size: 1.05rem; color: #111827; margin: 28px 0 12px; padding-left: 12px;
        border-left: 4px solid #F58220; font-weight: 700; }}
  h3 {{ font-size: 0.9rem; color: #374151; margin: 12px 0 6px; }}
  .muted {{ color: #6B7280; font-size: 0.8rem; margin-top: 4px; }}

  .hero {{ border-radius: 14px; padding: 24px 28px; color: #fff; margin-bottom: 14px;
          box-shadow: 0 4px 14px rgba(0,0,0,0.12); position: relative; }}
  .hero-badge {{ position: absolute; top: 12px; right: 18px; font-size: 0.7rem;
                letter-spacing: 0.1em; background: rgba(255,255,255,0.2);
                padding: 3px 10px; border-radius: 12px; font-weight: 700; }}
  .hero-row {{ display: grid; grid-template-columns: auto 1.1fr auto auto auto;
              gap: 28px; align-items: center; }}
  .hero-label {{ font-size: 0.7rem; opacity: 0.8; letter-spacing: 0.05em; text-transform: uppercase; }}
  .hero-value {{ font-size: 1.6rem; font-weight: 800; font-variant-numeric: tabular-nums; margin-top: 4px; }}
  .hero-sub {{ font-size: 0.75rem; opacity: 0.75; }}

  .alert-card {{ border-radius: 12px; padding: 14px 20px; margin-bottom: 18px;
                 display: flex; align-items: center; justify-content: space-between; gap: 20px; }}
  .alert-left {{ display: flex; flex-direction: column; }}
  .alert-label {{ font-size: 0.68rem; color: #6B7280; letter-spacing: 0.1em; font-weight: 700; }}
  .alert-agg {{ font-size: 0.78rem; color: #6B7280; margin-top: 4px; }}
  .alert-right {{ flex: 1; text-align: right; }}
  .alert-status {{ font-size: 0.95rem; font-weight: 700; margin-bottom: 4px; }}
  .alert-desc {{ font-size: 0.8rem; color: #6B7280; }}

  .formula-box {{ background: #fff; border-radius: 12px; padding: 20px;
                  border: 1px solid #E5E7EB; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
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

  .footer {{ text-align: center; color: #9CA3AF; font-size: 0.75rem; margin-top: 32px; padding: 16px; }}
</style>
</head>
<body>

<h1>Sector Asset Allocation — Dual Signal Dashboard</h1>
<div class="subtitle">
  MAIN = 6M-only lookback (Sharpe 0.97) · ALERT = Champion [1,3,6] (보조 경보) ·
  4 GICS 페어 (IT/FIN/ENERGY/STAPLES) + USDKRW 3M 30% · 월말 리밸런싱 · 30 bp 비용
</div>

<div class="status-banner">
  <span style="font-weight:700">📋 검증 단계:</span>
  <span>Paper Trading (3-6개월 실시간 병행 관찰) · IC 심의 준비 중</span>
</div>

<div class="nav">
  <a class="primary" href="#main">메인 시그널</a>
  <a href="#alert">보조 경보</a>
  <a href="#decompose">신호 분해</a>
  <a href="#timeline">히스토리</a>
  <a href="#perf">성과</a>
  <a href="#recent">최근 12개월</a>
  <a href="sector_asset_allocation/FORMAL_REPORT.pdf">📄 정식 보고서 (PDF)</a>
  <a href="sector_asset_allocation/README.html">📒 Research Notes</a>
  <a href="../index.html">← Portfolio 홈</a>
</div>

<h2 id="main">① 메인 시그널 (6M-only)</h2>
{_primary_hero(decomp_primary)}

<h2 id="alert">② 보조 경보 시그널 (Champion)</h2>
{_alert_card(decomp_alert, decomp_primary['signal'])}

<h2 id="decompose">③ 신호 분해 — 메인 (6M-only)</h2>
{_formula_block(decomp_primary, "메인 signal agg 분해")}

<h2>④ 섹터 페어별 RS</h2>
<div class="pair-grid">{_pair_cards(decomp_primary)}</div>

<h2 id="timeline">⑤ agg 히스토리 (MAIN vs ALERT)</h2>
<div class="canvas-wrap"><canvas id="aggChart" style="max-height:320px"></canvas></div>
<p class="muted">점선 = 임계 ±{COMMON_PARAMS['tau']} · 불일치 구간은 2018 Q4 같은 단기 조정 가능성</p>

<h2>⑥ 누적 수익 — MAIN vs ALERT vs 벤치마크</h2>
<div class="canvas-wrap"><canvas id="cumChart" style="max-height:380px"></canvas></div>

<h2 id="perf">⑦ 성과 비교</h2>
{_perf_table(m_primary, m_alert, m_bench)}
<p class="muted">
  MAIN 은 Full-sample Sharpe {m_primary['sharpe']:.2f} · OOS Test 1.09.
  ALERT 는 Sharpe {m_alert['sharpe']:.2f} · 2018 Q4 단기 조정 방어력 보유.
  시그널 일치율: {agree_rate*100:.0f}% (전체 {len(sig_agree)}개월).
</p>

<h2 id="recent">⑧ 최근 12개월 시그널 상세 (MAIN + ALERT)</h2>
<table>
  <thead><tr>
    <th>월말</th>
    <th>Main agg</th><th style="text-align:center">Main</th>
    <th>Alert agg</th><th style="text-align:center">Alert</th>
    <th>KOSPI</th><th>S&P500</th>
    <th>Main ret</th><th>Alert ret</th>
    <th>vs Blend</th>
  </tr></thead>
  <tbody>{_recent_table(bt_primary, bt_alert, 12)}</tbody>
</table>

<div class="footer">
  Dual Signal Dashboard · 최종 갱신: {pivot.index.max().strftime("%Y-%m-%d")} ·
  검증: Walk-forward OOS [완료] · Parameter Sensitivity [완료] · Rolling OOS [완료]
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  const dates = {json.dumps(dates)};
  const primaryAgg = {json.dumps(primary_agg)};
  const alertAgg   = {json.dumps(alert_agg)};
  const tau = {COMMON_PARAMS['tau']};

  new Chart(document.getElementById('aggChart'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label: 'MAIN (6M-only)', data: primaryAgg,
           borderColor: '#F58220', backgroundColor: 'rgba(245,130,32,0.08)',
           fill: true, tension: 0.15, borderWidth: 2.5, pointRadius: 1 }},
        {{ label: 'ALERT (Champion [1,3,6])', data: alertAgg,
           borderColor: '#1D3557', backgroundColor: 'transparent',
           tension: 0.1, borderWidth: 1.5, pointRadius: 0, borderDash: [5,3] }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line', font:{{size:10}} }} }},
      }},
      scales: {{
        y: {{ title: {{ display: true, text: 'agg score' }},
             ticks: {{ callback: v => v.toFixed(3) }} }},
        x: {{ ticks: {{ maxTicksLimit: 14 }} }}
      }}
    }}
  }});

  const cumPrimary = {json.dumps(_cum(bt_primary, "strategy_return"))};
  const cumAlert   = {json.dumps(_cum(bt_alert,   "strategy_return"))};
  const cumBlend   = {json.dumps(_cum(bt_primary, "blend_return"))};
  const cumKospi   = {json.dumps(_cum(bt_primary, "kr_return"))};
  const cumSp500   = {json.dumps(_cum(bt_primary, "us_return"))};

  new Chart(document.getElementById('cumChart'), {{
    type: 'line',
    data: {{ labels: dates, datasets: [
      {{ label: '★ MAIN (6M-only)',      data: cumPrimary, borderColor: '#F58220', borderWidth: 2.8, tension: 0.15, backgroundColor: 'transparent' }},
      {{ label: 'ALERT (Champion [1,3,6])', data: cumAlert, borderColor: '#1D3557', borderWidth: 1.8, tension: 0.15, backgroundColor: 'transparent' }},
      {{ label: '50/50 Blend',            data: cumBlend, borderColor: '#8B5CF6', borderWidth: 1.0, tension: 0.1, borderDash: [5,4], backgroundColor: 'transparent' }},
      {{ label: 'KOSPI',                  data: cumKospi, borderColor: '#E63946', borderWidth: 0.9, tension: 0.1, borderDash: [2,3], backgroundColor: 'transparent' }},
      {{ label: 'S&P500',                 data: cumSp500, borderColor: '#6B7280', borderWidth: 0.9, tension: 0.1, borderDash: [2,3], backgroundColor: 'transparent' }},
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
