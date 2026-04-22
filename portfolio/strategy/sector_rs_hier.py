"""Sector RS Hierarchical — Config-driven, parameter sweep + cross-sectional signals.

v2 변경점 (vs v1):
  - Config dataclass 로 파라미터화 — sweep 가능
  - cross-sectional 신호 2종 추가: Dispersion, Leadership Stability
  - sweep 모드: 여러 config 동시 백테스트 + 비교 HTML

per-pair agent:
  pair_score = W_RS·tanh(rs/rs_scale) + W_VOL·tanh(vol_tilt/vol_scale), × volume_confirm
  |score| > pair_vote_tau 에서 KR/US, 그 외 Hold

meta-layer:
  adaptive : 최근 N개월 hit rate 가중
  equal    : 균등 1/N 가중

cross-sectional filters (옵션):
  dispersion_filter : std(RS_i) 가 롤링 하위 30% 면 확신 0.5x (blend 희석)
  leadership_filter : 상위 3 KR/US 섹터가 3M 전과 1/3 미만 겹치면 Neutral 강제

Usage:
    # 단일 config
    python -m portfolio.strategy.sector_rs_hier --config baseline --date 2026-04-21
    # sweep (기본): 주요 변형 병렬 비교
    python -m portfolio.strategy.sector_rs_hier --sweep --date 2026-04-21
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.market_source import load_wide_close
from portfolio.strategy.sector_rs_sync import (
    SECTOR_PAIRS, LOOKBACK_MONTHS, BACKTEST_START, COST_BPS,
    KOSPI_CODE, SP500_CODE,
    _log_return, next_month_return, perf, _badge, _C, _LIGHT,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "portfolio" / "strategy" / "rs_hier"

VIX_CODE = "RK_VIX"


# ──────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────

@dataclass
class Config:
    name: str = "baseline"
    # Per-pair agent
    w_rs: float = 0.70
    w_vol: float = 0.30
    rs_scale: float = 0.02
    vol_scale: float = 0.10
    pair_vote_tau: float = 0.15
    use_volume_confirm: bool = True
    # Meta layer
    meta_mode: str = "adaptive"      # "adaptive" | "equal"
    meta_window: int = 6
    meta_min_votes: int = 3
    final_tau: float = 0.15
    # Risk overlay
    use_vix_overlay: bool = True
    vix_stress: float = 30.0
    # Cross-sectional filters
    use_dispersion_filter: bool = False
    dispersion_window_months: int = 24
    dispersion_low_q: float = 0.30   # 하위 30% 분위수 → 저 dispersion 레짐
    use_leadership_filter: bool = False
    leadership_lookback_months: int = 3
    leadership_min_overlap: float = 0.34  # 0.34 = 2/3 이상 겹쳐야 trend 로 인정


SWEEP_CONFIGS: list[Config] = [
    Config(name="baseline"),                                            # v1 그대로
    Config(name="no_vix",      use_vix_overlay=False),
    Config(name="low_tau",     pair_vote_tau=0.05, final_tau=0.05),
    Config(name="pure_rs",     w_rs=1.0, w_vol=0.0),
    Config(name="equal_meta",  meta_mode="equal"),
    Config(name="no_volume",   use_volume_confirm=False),
    Config(name="combo_1",     use_vix_overlay=False, pair_vote_tau=0.05, final_tau=0.05),
    Config(name="combo_2",     use_vix_overlay=False, w_rs=1.0, w_vol=0.0, meta_mode="equal"),
    Config(name="+dispersion", use_vix_overlay=False, use_dispersion_filter=True),
    Config(name="+leadership", use_vix_overlay=False, use_leadership_filter=True),
    Config(name="+both",       use_vix_overlay=False,
                                use_dispersion_filter=True, use_leadership_filter=True),
]


# ──────────────────────────────────────────────────────
# Per-pair inputs
# ──────────────────────────────────────────────────────

def _realized_vol(px: pd.Series, as_of: pd.Timestamp, window: int = 20) -> float | None:
    data = px.loc[:as_of].dropna()
    if len(data) < window + 1:
        return None
    rets = np.log(data / data.shift(1)).dropna()
    if len(rets) < window:
        return None
    return float(rets.iloc[-window:].std())


def _volume_confirm(volume_series: pd.Series | None, as_of: pd.Timestamp,
                    window: int = 20) -> float:
    if volume_series is None or volume_series.empty:
        return 1.0
    data = volume_series.loc[:as_of].dropna()
    if len(data) < window + 1:
        return 1.0
    avg = float(data.iloc[-(window + 1):-1].mean())
    last = float(data.iloc[-1])
    if avg <= 0:
        return 1.0
    ratio = last / avg
    return 1.0 if ratio >= 0.8 else 0.8


def _load_long_with_volume(codes: list[str], start: str) -> dict[str, pd.Series]:
    from portfolio.market_source import load_long
    df = load_long(start=start, codes=codes)
    if df.empty:
        return {}
    out: dict[str, pd.Series] = {}
    for code, sub in df.groupby("INDICATOR_CODE"):
        ser = sub.set_index("DATE")["VOLUME"].sort_index()
        ser = pd.to_numeric(ser, errors="coerce")
        out[code] = ser
    return out


# ──────────────────────────────────────────────────────
# Per-pair agent (config-driven)
# ──────────────────────────────────────────────────────

def pair_agent(cfg: Config, kr_px: pd.Series, us_px: pd.Series,
               kr_vol_ser: pd.Series | None, us_vol_ser: pd.Series | None,
               as_of: pd.Timestamp) -> dict | None:
    diffs = []
    for m in LOOKBACK_MONTHS:
        kr_lr = _log_return(kr_px, as_of, m)
        us_lr = _log_return(us_px, as_of, m)
        if kr_lr is None or us_lr is None:
            continue
        diffs.append(kr_lr - us_lr)
    if not diffs:
        return None
    rs = sum(diffs) / len(diffs)

    kr_vol = _realized_vol(kr_px, as_of)
    us_vol = _realized_vol(us_px, as_of)
    vol_tilt = (math.log(us_vol / kr_vol)
                if (kr_vol and us_vol and kr_vol > 0 and us_vol > 0) else 0.0)

    if cfg.use_volume_confirm:
        kr_conf = _volume_confirm(kr_vol_ser, as_of)
        us_conf = _volume_confirm(us_vol_ser, as_of)
        vol_confirm = min(kr_conf, us_conf)
    else:
        vol_confirm = 1.0

    score = (cfg.w_rs  * math.tanh(rs / cfg.rs_scale)
             + cfg.w_vol * math.tanh(vol_tilt / cfg.vol_scale))
    score *= vol_confirm

    if score > cfg.pair_vote_tau:
        vote = "KR"
    elif score < -cfg.pair_vote_tau:
        vote = "US"
    else:
        vote = "Hold"

    return {"rs": rs, "vol_tilt": vol_tilt, "vol_confirm": vol_confirm,
            "score": score, "vote": vote}


# ──────────────────────────────────────────────────────
# Meta-layer: adaptive pair weighting
# ──────────────────────────────────────────────────────

def _compute_hit_rates(cfg: Config, history: pd.DataFrame, n_pairs: int) -> np.ndarray:
    if cfg.meta_mode == "equal" or len(history) == 0:
        return np.ones(n_pairs) / n_pairs

    recent = history.tail(cfg.meta_window)
    weights = np.zeros(n_pairs)
    valid_mask = np.zeros(n_pairs, dtype=bool)

    for i in range(n_pairs):
        vote_col = f"pair_{i}_vote"
        if vote_col not in recent.columns:
            continue
        hits = 0
        total = 0
        for _, row in recent.iterrows():
            v = row[vote_col]
            if v == "Hold" or pd.isna(v):
                continue
            kr_r = row.get("kr_return")
            us_r = row.get("us_return")
            if pd.isna(kr_r) or pd.isna(us_r) or kr_r == us_r:
                continue
            actual = "KR" if kr_r > us_r else "US"
            total += 1
            if v == actual:
                hits += 1
        if total >= cfg.meta_min_votes:
            weights[i] = hits / total
            valid_mask[i] = True

    if not valid_mask.any():
        return np.ones(n_pairs) / n_pairs

    mean_valid = weights[valid_mask].mean()
    weights[~valid_mask] = mean_valid
    weights = np.clip(weights, 0.1, 1.0)
    total_w = weights.sum()
    return weights / total_w if total_w > 0 else np.ones(n_pairs) / n_pairs


def meta_aggregate(pair_results: list[dict | None], weights: np.ndarray) -> dict:
    n = len(pair_results)
    numeric_votes = np.zeros(n)
    scores = np.zeros(n)
    for i, r in enumerate(pair_results):
        if r is None:
            continue
        scores[i] = r["score"]
        if r["vote"] == "KR":
            numeric_votes[i] = 1
        elif r["vote"] == "US":
            numeric_votes[i] = -1

    active_weight = sum(weights[i] for i, r in enumerate(pair_results) if r is not None)
    if active_weight == 0:
        return {"weighted_vote": 0.0, "weighted_score": 0.0,
                "kr_w": 0, "us_w": 0, "hold_w": 0}

    weighted_vote = float(np.sum(weights * numeric_votes) / active_weight)
    weighted_score = float(np.sum(weights * scores) / active_weight)

    kr_w = float(sum(weights[i] for i, r in enumerate(pair_results) if r and r["vote"] == "KR"))
    us_w = float(sum(weights[i] for i, r in enumerate(pair_results) if r and r["vote"] == "US"))
    hold_w = float(sum(weights[i] for i, r in enumerate(pair_results) if r and r["vote"] == "Hold"))

    return {"weighted_vote": weighted_vote, "weighted_score": weighted_score,
            "kr_w": kr_w, "us_w": us_w, "hold_w": hold_w}


# ──────────────────────────────────────────────────────
# Cross-sectional signals
# ──────────────────────────────────────────────────────

def compute_dispersion(pair_results: list[dict | None]) -> float | None:
    """Std dev of RS across pairs (unitless — log-return diff scale)."""
    rs_vals = [r["rs"] for r in pair_results if r is not None]
    if len(rs_vals) < 3:
        return None
    return float(np.std(rs_vals))


def compute_leadership_overlap(pivot: pd.DataFrame, sector_codes: list[str],
                                as_of: pd.Timestamp, lookback_months: int,
                                top_n: int = 3) -> float | None:
    """상위 top_n 섹터가 lookback_months 전의 상위 top_n 과 겹치는 비율 (0~1)."""
    # Current 3M momentum
    now_scores = {}
    for code in sector_codes:
        if code not in pivot.columns:
            continue
        lr = _log_return(pivot[code], as_of, 3)
        if lr is not None:
            now_scores[code] = lr
    if len(now_scores) < top_n:
        return None

    past_date = as_of - pd.DateOffset(months=lookback_months)
    past_scores = {}
    for code in sector_codes:
        if code not in pivot.columns:
            continue
        lr = _log_return(pivot[code], past_date, 3)
        if lr is not None:
            past_scores[code] = lr
    if len(past_scores) < top_n:
        return None

    now_top = set([k for k, _ in sorted(now_scores.items(), key=lambda x: -x[1])[:top_n]])
    past_top = set([k for k, _ in sorted(past_scores.items(), key=lambda x: -x[1])[:top_n]])
    return len(now_top & past_top) / top_n


# ──────────────────────────────────────────────────────
# Backtest
# ──────────────────────────────────────────────────────

def run_backtest(cfg: Config, pivot: pd.DataFrame,
                 vol_map: dict[str, pd.Series]) -> pd.DataFrame:
    month_ends = pivot.resample("BME").last().index
    cost = COST_BPS / 10_000
    n_pairs = len(SECTOR_PAIRS)

    kr_sectors = [p[0] for p in SECTOR_PAIRS]
    us_sectors = [p[1] for p in SECTOR_PAIRS]

    history_rows: list[dict] = []
    prev_signal: str | None = None
    dispersion_history: list[float] = []

    for me in month_ends[:-1]:
        pair_results: list[dict | None] = []
        for kr_code, us_code, _label in SECTOR_PAIRS:
            if kr_code not in pivot.columns or us_code not in pivot.columns:
                pair_results.append(None)
                continue
            pair_results.append(pair_agent(
                cfg, pivot[kr_code], pivot[us_code],
                vol_map.get(kr_code), vol_map.get(us_code), me,
            ))
        if all(r is None for r in pair_results):
            continue

        history_df = pd.DataFrame(history_rows) if history_rows else pd.DataFrame()
        weights = _compute_hit_rates(cfg, history_df, n_pairs)
        meta = meta_aggregate(pair_results, weights)

        # VIX stress
        vix_val = None
        if VIX_CODE in pivot.columns:
            vix_data = pivot[VIX_CODE].loc[:me].dropna()
            if len(vix_data) > 0:
                vix_val = float(vix_data.iloc[-1])
        vix_stress = cfg.use_vix_overlay and (vix_val is not None and vix_val > cfg.vix_stress)

        # Cross-sectional: dispersion
        dispersion = compute_dispersion(pair_results)
        if dispersion is not None:
            dispersion_history.append(dispersion)
        low_disp_regime = False
        if cfg.use_dispersion_filter and dispersion is not None:
            recent_disp = dispersion_history[-cfg.dispersion_window_months:]
            if len(recent_disp) >= 6:
                q = np.quantile(recent_disp, cfg.dispersion_low_q)
                low_disp_regime = dispersion < q

        # Cross-sectional: leadership (아시아 평균과 미국 평균 둘 다 본 뒤 낮은 쪽 적용)
        leadership_break = False
        kr_overlap = us_overlap = None
        if cfg.use_leadership_filter:
            kr_overlap = compute_leadership_overlap(
                pivot, kr_sectors, me, cfg.leadership_lookback_months)
            us_overlap = compute_leadership_overlap(
                pivot, us_sectors, me, cfg.leadership_lookback_months)
            if (kr_overlap is not None and kr_overlap < cfg.leadership_min_overlap) or \
               (us_overlap is not None and us_overlap < cfg.leadership_min_overlap):
                leadership_break = True

        # 시그널
        ws = meta["weighted_score"]
        if leadership_break:
            signal = "Neutral"
        elif ws > cfg.final_tau:
            signal = "KR"
        elif ws < -cfg.final_tau:
            signal = "US"
        else:
            signal = "Neutral"

        # 수익
        kr_ret = next_month_return(pivot, me, KOSPI_CODE)
        us_ret = next_month_return(pivot, me, SP500_CODE)
        if kr_ret is None or us_ret is None:
            continue
        blend_ret = 0.5 * kr_ret + 0.5 * us_ret

        if signal == "KR":
            base_r = kr_ret
        elif signal == "US":
            base_r = us_ret
        else:
            base_r = blend_ret

        # 확신 감쇠 (VIX stress OR low dispersion)
        dilute = (vix_stress or low_disp_regime) and signal != "Neutral"
        strat_ret = 0.5 * base_r + 0.5 * blend_ret if dilute else base_r

        tc = cost if (prev_signal is not None and signal != prev_signal) else 0.0
        strat_ret -= tc
        prev_signal = signal

        row: dict = {
            "as_of":    me.strftime("%Y-%m-%d"),
            "signal":   signal,
            "ws":       round(ws, 4),
            "vix":      round(vix_val, 2) if vix_val is not None else None,
            "stress":   vix_stress,
            "disp":     round(dispersion, 5) if dispersion is not None else None,
            "low_disp": low_disp_regime,
            "kr_ldrshp": round(kr_overlap, 2) if kr_overlap is not None else None,
            "us_ldrshp": round(us_overlap, 2) if us_overlap is not None else None,
            "ldr_break": leadership_break,
            "kr_w":     round(meta["kr_w"], 3),
            "us_w":     round(meta["us_w"], 3),
            "hold_w":   round(meta["hold_w"], 3),
            "cost":     round(tc, 5),
            "kr_return":     round(kr_ret, 4),
            "us_return":     round(us_ret, 4),
            "blend_return":  round(blend_ret, 4),
            "strategy_return": round(strat_ret, 4),
        }
        for i, r in enumerate(pair_results):
            row[f"pair_{i}_weight"] = round(float(weights[i]), 4)
            if r is None:
                row[f"pair_{i}_vote"] = None
                row[f"pair_{i}_score"] = None
            else:
                row[f"pair_{i}_vote"] = r["vote"]
                row[f"pair_{i}_score"] = round(r["score"], 4)
                row[f"pair_{i}_rs"] = round(r["rs"], 5)
        history_rows.append(row)

    return pd.DataFrame(history_rows)


# ──────────────────────────────────────────────────────
# Sweep & comparison HTML
# ──────────────────────────────────────────────────────

def run_sweep(cfgs: list[Config], pivot: pd.DataFrame,
              vol_map: dict[str, pd.Series]) -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    for cfg in cfgs:
        bt = run_backtest(cfg, pivot, vol_map)
        if bt.empty:
            print(f"  [{cfg.name}] empty")
            continue
        results[cfg.name] = bt
        m = perf(bt["strategy_return"], cfg.name)
        if m:
            print(f"  {cfg.name:18s}  CAGR={m['ann_return']*100:+6.2f}%  "
                  f"Sharpe={m['sharpe']:+5.2f}  MDD={m['mdd']*100:+6.1f}%  "
                  f"Win={m['win_rate']*100:3.0f}%  n={m['n_months']}")
    return results


def build_sweep_html(results: dict[str, pd.DataFrame],
                     bench: dict[str, pd.Series],
                     date_str: str) -> str:
    """여러 config + 벤치마크 한눈에 비교."""
    # 성과 테이블
    rows = []
    for name, bt in results.items():
        rows.append(perf(bt["strategy_return"], name))
    for name, ser in bench.items():
        rows.append(perf(ser, name))

    rows_sorted = sorted(rows, key=lambda m: -m["sharpe"])

    m_rows = ""
    for m in rows_sorted:
        is_strat = m["label"] in results
        bg = "background:#FFF7EE;" if is_strat and m["sharpe"] == rows_sorted[0]["sharpe"] else ""
        m_rows += (
            f'<tr style="{bg}">'
            f'<td>{"🏆 " if bg else ""}{m["label"]}</td>'
            f'<td class="num">{m["total_return"]*100:+.1f}%</td>'
            f'<td class="num">{m["ann_return"]*100:+.1f}%</td>'
            f'<td class="num">{m["ann_vol"]*100:.1f}%</td>'
            f'<td class="num"><b>{m["sharpe"]:.2f}</b></td>'
            f'<td class="num" style="color:#DC2626">{m["mdd"]*100:.1f}%</td>'
            f'<td class="num">{m["win_rate"]*100:.0f}%</td>'
            f'<td class="num">{m["n_months"]}</td>'
            f'</tr>'
        )

    # Cumulative chart data
    sample_bt = next(iter(results.values()))
    labels_j = json.dumps(list(sample_bt["as_of"]))

    palette = ["#F58220", "#E63946", "#059669", "#8B5CF6", "#0EA5E9",
               "#F59E0B", "#EC4899", "#6366F1", "#14B8A6", "#F97316", "#84CC16"]
    datasets = []
    for i, (name, bt) in enumerate(results.items()):
        cum = ((1 + bt["strategy_return"]).cumprod() - 1).round(4).tolist()
        datasets.append({
            "label": name, "data": cum,
            "borderColor": palette[i % len(palette)],
            "backgroundColor": "transparent",
            "borderWidth": 1.8, "tension": 0.15,
        })
    # benchmarks
    for i, (name, ser) in enumerate(bench.items()):
        cum = ((1 + ser).cumprod() - 1).round(4).tolist()
        datasets.append({
            "label": name, "data": cum,
            "borderColor": "#6B7280", "borderDash": [4, 4],
            "backgroundColor": "transparent",
            "borderWidth": 1.2, "tension": 0.1,
        })

    # Config 설명
    cfg_table = ""
    for cfg in SWEEP_CONFIGS:
        if cfg.name not in results:
            continue
        diff = []
        base = Config()
        for k, v in asdict(cfg).items():
            if k == "name":
                continue
            if getattr(base, k) != v:
                diff.append(f"<code>{k}={v}</code>")
        diff_str = " · ".join(diff) if diff else "<i>baseline defaults</i>"
        cfg_table += f'<tr><td><b>{cfg.name}</b></td><td>{diff_str}</td></tr>'

    best = rows_sorted[0]

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Sector RS Hierarchical — Sweep {date_str}</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; background:#F7F8FA; color:#1F2937; padding:24px; max-width:1280px; margin:0 auto; }}
  h1 {{ font-size:1.5rem; font-weight:800; margin-bottom:4px; }}
  .subtitle {{ color:#6B7280; font-size:0.85rem; margin-bottom:24px; }}
  h2 {{ font-size:1rem; color:#111827; margin:28px 0 10px; padding-left:10px; border-left:3px solid #F58220; }}
  .hero {{ background:linear-gradient(135deg,#FFF7EE,#FDE68A22); border-radius:12px; padding:18px 22px; border:1px solid #FCD34D; margin-bottom:20px; }}
  .hero b {{ color:#B45309; }}
  table {{ width:100%; background:#fff; border-collapse:collapse; font-size:0.85rem; border-radius:8px; overflow:hidden; border:1px solid #E5E7EB; }}
  th {{ background:#F3F4F6; padding:9px 10px; text-align:left; font-weight:600; color:#374151; border-bottom:1px solid #E5E7EB; }}
  td {{ padding:8px 10px; border-bottom:1px solid #F3F4F6; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  code {{ font-family:'SF Mono',Menlo,monospace; font-size:0.78rem; color:#6B7280; background:#F3F4F6; padding:1px 5px; border-radius:3px; }}
  .canvas-wrap {{ background:#fff; padding:16px; border-radius:10px; border:1px solid #E5E7EB; }}
  .note {{ color:#6B7280; font-size:0.75rem; margin-top:8px; line-height:1.55; }}
</style>
</head>
<body>

<h1>Sector RS Hierarchical — Parameter Sweep + Cross-Sectional Signals</h1>
<div class="subtitle">기준일 {date_str} · {BACKTEST_START} ~ 전략 백테스트</div>

<div class="hero">
  🏆 <b>베스트 Sharpe</b>: {best["label"]} (Sharpe {best["sharpe"]:.2f}, CAGR {best["ann_return"]*100:+.2f}%, MDD {best["mdd"]*100:.1f}%)
</div>

<h2>성과 비교 (Sharpe 내림차순)</h2>
<table>
  <thead><tr><th>전략</th><th>Total</th><th>연수익</th><th>연변동</th><th>Sharpe</th><th>MDD</th><th>Win%</th><th>#월</th></tr></thead>
  <tbody>{m_rows}</tbody>
</table>

<h2>누적 수익 곡선</h2>
<div class="canvas-wrap">
  <canvas id="cum" style="max-height:420px"></canvas>
</div>

<h2>Config 변주점 (vs baseline)</h2>
<table>
  <thead><tr><th>config</th><th>차이</th></tr></thead>
  <tbody>{cfg_table}</tbody>
</table>

<div class="note">
  Cross-sectional filters:<br>
  • <b>dispersion</b>: std(RS_i) 가 롤링 {SWEEP_CONFIGS[0].dispersion_window_months}개월 하위 30% 면 신호 희석(0.5×blend)<br>
  • <b>leadership</b>: 상위 3 섹터가 {SWEEP_CONFIGS[0].leadership_lookback_months}개월 전과 1/3 미만 겹치면 Neutral 강제
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  new Chart(document.getElementById('cum'), {{
    type: 'line',
    data: {{ labels: {labels_j}, datasets: {json.dumps(datasets)} }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position:'top', labels:{{ usePointStyle:true, pointStyle:'line', font:{{size:11}} }} }} }},
      scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }}, x: {{ ticks: {{ maxTicksLimit:14 }} }} }}
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
    parser.add_argument("--date",   default=None)
    parser.add_argument("--start",  default=BACKTEST_START)
    parser.add_argument("--config", default=None, help="단일 config 이름 (sweep 대신)")
    parser.add_argument("--sweep",  action="store_true", help="전체 config sweep")
    args = parser.parse_args()

    codes = [p[0] for p in SECTOR_PAIRS] + [p[1] for p in SECTOR_PAIRS] + [KOSPI_CODE, SP500_CODE, VIX_CODE]
    pivot = load_wide_close(start=args.start, codes=codes)
    if pivot.empty:
        raise SystemExit("[ERROR] 가격 데이터 로드 실패")

    sector_codes = [p[0] for p in SECTOR_PAIRS] + [p[1] for p in SECTOR_PAIRS]
    vol_map = _load_long_with_volume(sector_codes, args.start)

    if args.date:
        pivot = pivot.loc[:args.date]
        date_str = args.date
    else:
        date_str = pivot.index.max().strftime("%Y-%m-%d")

    print(f"[load] pivot {pivot.shape} · volumes {len(vol_map)} codes · cutoff {date_str}")

    if args.config:
        cfgs = [c for c in SWEEP_CONFIGS if c.name == args.config]
        if not cfgs:
            raise SystemExit(f"[ERROR] unknown config: {args.config}")
    elif args.sweep:
        cfgs = SWEEP_CONFIGS
    else:
        # default: sweep
        cfgs = SWEEP_CONFIGS

    print(f"[sweep] {len(cfgs)} configs")
    results = run_sweep(cfgs, pivot, vol_map)

    # 벤치마크
    sample_bt = next(iter(results.values()))
    bench = {
        "50/50 Blend": sample_bt["blend_return"],
        "KOSPI":       sample_bt["kr_return"],
        "S&P500":      sample_bt["us_return"],
    }
    print("\n[benchmarks]")
    for name, ser in bench.items():
        m = perf(ser, name)
        if m:
            print(f"  {name:18s}  CAGR={m['ann_return']*100:+6.2f}%  "
                  f"Sharpe={m['sharpe']:+5.2f}  MDD={m['mdd']*100:+6.1f}%  "
                  f"Win={m['win_rate']*100:3.0f}%")

    # HTML
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = build_sweep_html(results, bench, date_str)
    html_path = OUTPUT_DIR / f"{date_str}_sweep.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n[write] {html_path}")

    # 베스트 config signals CSV
    if results:
        best_name = max(results.keys(),
                        key=lambda n: perf(results[n]["strategy_return"], n).get("sharpe", -1))
        csv_path = OUTPUT_DIR / f"{date_str}_{best_name}_signals.csv"
        results[best_name].to_csv(csv_path, index=False)
        print(f"[write] {csv_path} (best: {best_name})")


if __name__ == "__main__":
    main()
