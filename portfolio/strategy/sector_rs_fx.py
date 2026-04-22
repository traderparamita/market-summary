"""Sector RS + FX — 섹터 가격과 FX 만 사용한 최소 구조 실험.

가설: KR vs US 베팅에서 환율이 가장 직접적 채널이므로, 섹터 RS + FX 단독 조합이
가장 깔끔한 신호일 수 있다.

변형:
  mean_rs               — 기준선 (sync, FX 없음)
  rs_usdkrw_w03/w05     — Mean-RS + USDKRW 3M 모멘텀 tilt (가중 0.3 / 0.5)
  rs_dxy_w03/w05        — Mean-RS + DXY 3M 모멘텀 tilt
  rs_both_w03           — Mean-RS + (USDKRW + DXY 평균) tilt
  per_pair_fx_weighted  — 페어별 export exposure 에 따라 FX tilt 차등 적용
  fx_only_usdkrw        — 섹터 무시, USDKRW 만으로 KR/US 결정
  fx_only_dxy           — 섹터 무시, DXY 만

집계:
  agg_signal = w_rs · mean_rs + w_fx · fx_tilt
  > +τ → KR, < -τ → US, 그 외 이전 상태 유지

Usage:
    python -m portfolio.strategy.sector_rs_fx --date 2026-04-21
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.market_source import load_wide_close
from portfolio.strategy.sector_rs_sync import (
    SECTOR_PAIRS, LOOKBACK_MONTHS, BACKTEST_START, COST_BPS,
    KOSPI_CODE, SP500_CODE,
    _log_return, next_month_return, perf, _badge, _C,
    compute_rs_pairs,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "portfolio" / "strategy" / "rs_fx"

# 월말 시그널 생성에 필요한 최소 유효 페어 수 (4쌍 variant 에선 3 으로 낮춤)
MIN_PAIRS = 5


# 페어 export exposure (per-pair variant 용)
# 1.0 = 수출 민감도 최대, 0.0 = 내수 중심
PAIR_EXPORT_EXPOSURE = {
    "IT":      1.0,   # 반도체/전자 — 최고 수출 민감
    "FIN":     0.0,   # 내수 은행
    "HEALTH":  0.2,   # 대부분 내수, 일부 수출
    "INDU":    0.8,   # 조선/기계 수출
    "ENERGY":  0.4,   # 정유 수출하지만 원유 수입 상쇄
    "DISCR":   0.3,   # 자동차/화장품 부분 수출
    "STAPLES": 0.1,   # 주로 내수
    "COMM":    0.0,   # NAVER/Kakao 등 내수
}
PAIR_LABELS = list(PAIR_EXPORT_EXPOSURE.keys())
assert len(PAIR_LABELS) == len(SECTOR_PAIRS)


# ──────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────

@dataclass
class Config:
    name: str = "mean_rs"
    # Base: Mean-RS
    w_rs:  float = 1.0
    # FX overlay
    fx_source: str = "none"        # none / usdkrw / dxy / both
    w_fx: float = 0.0
    fx_scale_usdkrw: float = 0.03  # 3% 3M 움직임이 tanh(1) ≈ 0.76
    fx_scale_dxy:    float = 0.03
    # Per-pair FX (export exposure 가중)
    use_per_pair_fx: bool = False
    # Thresholds — raw scale (sync Mean-RS 와 동일)
    #   mean_rs: 로그수익 차 평균, 일반 ±0.02
    #   fx_tilt: tanh(3M 수익률 / scale) ∈ [-1, +1], × 0.02 로 rs 스케일에 정렬
    tau: float = 0.02


SWEEP_CONFIGS: list[Config] = [
    # 기준선
    Config(name="mean_rs"),
    # USDKRW 단독 추가
    Config(name="rs_usdkrw_w03", fx_source="usdkrw", w_rs=0.7, w_fx=0.3),
    Config(name="rs_usdkrw_w05", fx_source="usdkrw", w_rs=0.5, w_fx=0.5),
    # DXY 단독 추가
    Config(name="rs_dxy_w03",    fx_source="dxy",    w_rs=0.7, w_fx=0.3),
    Config(name="rs_dxy_w05",    fx_source="dxy",    w_rs=0.5, w_fx=0.5),
    # 둘 다
    Config(name="rs_both_w03",   fx_source="both",   w_rs=0.7, w_fx=0.3),
    Config(name="rs_both_w05",   fx_source="both",   w_rs=0.5, w_fx=0.5),
    # 페어별 export exposure 가중 FX
    Config(name="per_pair_fx",   fx_source="usdkrw", w_rs=0.7, w_fx=0.3,
           use_per_pair_fx=True),
    # FX only — agg = w_fx × fx_val × 0.02 ∈ ±0.02; tau 조정 필요
    Config(name="fx_only_usdkrw", fx_source="usdkrw", w_rs=0.0, w_fx=1.0, tau=0.006),
    Config(name="fx_only_dxy",    fx_source="dxy",    w_rs=0.0, w_fx=1.0, tau=0.006),
]


# ──────────────────────────────────────────────────────
# FX tilt
# ──────────────────────────────────────────────────────

def _price_return_pct(px: pd.Series | None, as_of: pd.Timestamp, months: int) -> float | None:
    if px is None or px.empty:
        return None
    data = px.loc[:as_of].dropna()
    if data.empty:
        return None
    target = as_of - pd.DateOffset(months=months)
    past = data[data.index <= target]
    if past.empty:
        return None
    start = float(past.iloc[-1])
    end = float(data.iloc[-1])
    if start <= 0:
        return None
    return end / start - 1.0


def fx_tilt(cfg: Config, pivot: pd.DataFrame, as_of: pd.Timestamp) -> float:
    """순 방향: positive = KR 편향 (KRW 약세 → KR 수출주 유리).

    USDKRW 오르면 KRW 약세 → KR 편향 → positive
    DXY    오르면 USD 강세 (=KRW 약세 근사) → 동일 방향
    """
    if cfg.fx_source == "none":
        return 0.0
    sources = []
    if cfg.fx_source in ("usdkrw", "both"):
        r = _price_return_pct(pivot.get("FX_USDKRW"), as_of, 3)
        if r is not None:
            sources.append(math.tanh(r / cfg.fx_scale_usdkrw))
    if cfg.fx_source in ("dxy", "both"):
        r = _price_return_pct(pivot.get("FX_DXY"), as_of, 3)
        if r is not None:
            sources.append(math.tanh(r / cfg.fx_scale_dxy))
    return sum(sources) / len(sources) if sources else 0.0


# ──────────────────────────────────────────────────────
# Aggregate
# ──────────────────────────────────────────────────────

def aggregate_signal(cfg: Config, rs_list: list[dict],
                     pivot: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    if not rs_list:
        return {"n_pairs": 0, "mean_rs": 0.0, "fx_tilt": 0.0, "agg": 0.0}
    n = len(rs_list)

    # FX tilt 을 rs 스케일 (log-return diff ~ ±0.02) 로 맞추기 위해 × 0.02
    FX_SCALE_TO_RS = 0.02

    if cfg.use_per_pair_fx and cfg.fx_source != "none":
        base_fx = fx_tilt(cfg, pivot, as_of)
        adjusted_rs = []
        for r in rs_list:
            lbl = next((pl for pl, pair in zip(PAIR_LABELS, SECTOR_PAIRS)
                       if pair[0] == r["kr"]), None)
            exposure = PAIR_EXPORT_EXPOSURE.get(lbl, 0.0)
            adjusted_rs.append(r["rs"] + base_fx * exposure * FX_SCALE_TO_RS)
        mean_rs = sum(adjusted_rs) / n
        fx_val = base_fx
        agg = cfg.w_rs * mean_rs
    else:
        mean_rs = sum(r["rs"] for r in rs_list) / n
        fx_val = fx_tilt(cfg, pivot, as_of)
        # 둘 다 raw rs 스케일로 (sync Mean-RS 와 apples-to-apples)
        agg = cfg.w_rs * mean_rs + cfg.w_fx * fx_val * FX_SCALE_TO_RS

    return {
        "n_pairs": n,
        "mean_rs": mean_rs,
        "fx_tilt": fx_val,
        "agg":     agg,
    }


# ──────────────────────────────────────────────────────
# Backtest
# ──────────────────────────────────────────────────────

def run_backtest(cfg: Config, pivot: pd.DataFrame) -> pd.DataFrame:
    month_ends = pivot.resample("BME").last().index
    cost = COST_BPS / 10_000

    records: list[dict] = []
    prev_signal: str | None = None
    prev_state: str = "Neutral"

    for me in month_ends[:-1]:
        rs_list = compute_rs_pairs(pivot, me)
        if not rs_list or len(rs_list) < MIN_PAIRS:
            continue
        agg_d = aggregate_signal(cfg, rs_list, pivot, me)
        ws = agg_d["agg"]

        # Hysteresis: 임계값 초과 시 상태 전환, 아니면 이전 유지
        if ws > cfg.tau:
            signal = "KR"
        elif ws < -cfg.tau:
            signal = "US"
        else:
            signal = prev_state  # hold

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

        tc = cost if (prev_signal is not None and signal != prev_signal) else 0.0
        strat_ret = base_r - tc
        prev_signal = signal
        prev_state = signal

        records.append({
            "as_of":    me.strftime("%Y-%m-%d"),
            "signal":   signal,
            "n_pairs":  agg_d["n_pairs"],
            "mean_rs":  round(agg_d["mean_rs"], 5),
            "fx_tilt":  round(agg_d["fx_tilt"], 4),
            "agg":      round(ws, 5),
            "cost":     round(tc, 5),
            "kr_return":     round(kr_ret, 4),
            "us_return":     round(us_ret, 4),
            "blend_return":  round(blend_ret, 4),
            "strategy_return": round(strat_ret, 4),
        })
    return pd.DataFrame(records)


# ──────────────────────────────────────────────────────
# Sweep / HTML
# ──────────────────────────────────────────────────────

def run_sweep(cfgs: list[Config], pivot: pd.DataFrame) -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    for cfg in cfgs:
        bt = run_backtest(cfg, pivot)
        if bt.empty:
            continue
        results[cfg.name] = bt
        m = perf(bt["strategy_return"], cfg.name)
        if m:
            print(f"  {cfg.name:22s}  CAGR={m['ann_return']*100:+6.2f}%  "
                  f"Sharpe={m['sharpe']:+5.2f}  MDD={m['mdd']*100:+6.1f}%  "
                  f"Win={m['win_rate']*100:3.0f}%  n={m['n_months']}")
    return results


def build_sweep_html(results: dict[str, pd.DataFrame],
                     bench: dict[str, pd.Series], date_str: str) -> str:
    rows = []
    for name, bt in results.items():
        rows.append(perf(bt["strategy_return"], name))
    for name, ser in bench.items():
        rows.append(perf(ser, name))
    rows_sorted = sorted(rows, key=lambda m: -m["sharpe"])
    best = rows_sorted[0]

    m_rows = ""
    for m in rows_sorted:
        mark = "🏆 " if m is best else ""
        bg = "background:#FFF7EE;font-weight:700" if m is best else ""
        m_rows += (
            f'<tr style="{bg}">'
            f'<td>{mark}{m["label"]}</td>'
            f'<td class="num">{m["total_return"]*100:+.1f}%</td>'
            f'<td class="num">{m["ann_return"]*100:+.1f}%</td>'
            f'<td class="num">{m["ann_vol"]*100:.1f}%</td>'
            f'<td class="num"><b>{m["sharpe"]:.2f}</b></td>'
            f'<td class="num" style="color:#DC2626">{m["mdd"]*100:.1f}%</td>'
            f'<td class="num">{m["win_rate"]*100:.0f}%</td>'
            f'<td class="num">{m["n_months"]}</td>'
            f'</tr>'
        )

    sample_bt = next(iter(results.values()))
    labels_j = json.dumps(list(sample_bt["as_of"]))
    palette = ["#F58220", "#E63946", "#059669", "#8B5CF6", "#0EA5E9",
               "#F59E0B", "#EC4899", "#6366F1", "#14B8A6", "#F97316"]
    datasets = []
    for i, (name, bt) in enumerate(results.items()):
        cum = ((1 + bt["strategy_return"]).cumprod() - 1).round(4).tolist()
        datasets.append({
            "label": name, "data": cum,
            "borderColor": palette[i % len(palette)],
            "backgroundColor": "transparent",
            "borderWidth": 2.2 if name == best["label"] else 1.3, "tension": 0.15,
        })
    for name, ser in bench.items():
        cum = ((1 + ser).cumprod() - 1).round(4).tolist()
        datasets.append({
            "label": name, "data": cum,
            "borderColor": "#6B7280", "borderDash": [5, 4],
            "backgroundColor": "transparent",
            "borderWidth": 1.0, "tension": 0.1,
        })

    last = sample_bt.iloc[-1]
    cfg_table = ""
    base = Config()
    for cfg in SWEEP_CONFIGS:
        if cfg.name not in results:
            continue
        diff = []
        for k, v in asdict(cfg).items():
            if k == "name":
                continue
            if getattr(base, k) != v:
                diff.append(f"<code>{k}={v}</code>")
        cfg_table += f'<tr><td><b>{cfg.name}</b></td><td>{(" · ".join(diff)) or "<i>baseline</i>"}</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Sector + FX — {date_str}</title>
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

<h1>Sector RS + FX — 섹터 가격과 FX 만 사용</h1>
<div class="subtitle">KR vs US 결정에서 FX 역할 isolated 실험 · {BACKTEST_START} ~ {date_str}</div>

<div class="hero">
  🏆 <b>베스트 Sharpe</b>: {best["label"]} — CAGR {best["ann_return"]*100:+.2f}%, Sharpe {best["sharpe"]:.2f}, MDD {best["mdd"]*100:.1f}%
</div>

<h2>성과 비교 (Sharpe 내림차순)</h2>
<table>
  <thead><tr><th>전략</th><th>Total</th><th>연수익</th><th>연변동</th><th>Sharpe</th><th>MDD</th><th>Win%</th><th>#월</th></tr></thead>
  <tbody>{m_rows}</tbody>
</table>

<h2>현재 시그널 ({last["as_of"]})</h2>
<table>
  <thead><tr><th>config</th><th style="text-align:right">mean_rs</th><th style="text-align:right">fx_tilt</th><th style="text-align:right">agg</th><th style="text-align:center">signal</th></tr></thead>
  <tbody>
    {"".join(f'<tr><td>{name}</td><td class="num">{bt.iloc[-1]["mean_rs"]*100:+.2f}%</td><td class="num">{bt.iloc[-1]["fx_tilt"]:+.3f}</td><td class="num">{bt.iloc[-1]["agg"]:+.3f}</td><td style="text-align:center">{_badge(bt.iloc[-1]["signal"])}</td></tr>' for name, bt in results.items())}
  </tbody>
</table>

<h2>누적 수익 곡선</h2>
<div class="canvas-wrap">
  <canvas id="cum" style="max-height:440px"></canvas>
</div>

<h2>Config 설명</h2>
<table>
  <thead><tr><th>config</th><th>차이</th></tr></thead>
  <tbody>{cfg_table}</tbody>
</table>

<div class="note">
  <b>FX tilt 정의</b>: USDKRW 또는 DXY 의 3M 수익률을 tanh(r/0.03) 로 정규화. positive=KR 편향(KRW 약세→KR 수출 유리). Per-pair variant 는 섹터별 export exposure 계수(IT=1.0/INDU=0.8/... /COMM=0.0)로 가중.
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
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    codes = ([p[0] for p in SECTOR_PAIRS] + [p[1] for p in SECTOR_PAIRS]
             + [KOSPI_CODE, SP500_CODE, "FX_USDKRW", "FX_DXY"])
    pivot = load_wide_close(start=args.start, codes=codes)
    if pivot.empty:
        raise SystemExit("[ERROR] 가격 데이터 로드 실패")

    if args.date:
        pivot = pivot.loc[:args.date]
        date_str = args.date
    else:
        date_str = pivot.index.max().strftime("%Y-%m-%d")
    print(f"[load] pivot {pivot.shape} · cutoff {date_str}")

    cfgs = [c for c in SWEEP_CONFIGS if c.name == args.config] if args.config else SWEEP_CONFIGS
    print(f"[sweep] {len(cfgs)} configs")
    results = run_sweep(cfgs, pivot)

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
            print(f"  {name:22s}  CAGR={m['ann_return']*100:+6.2f}%  "
                  f"Sharpe={m['sharpe']:+5.2f}  MDD={m['mdd']*100:+6.1f}%")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = build_sweep_html(results, bench, date_str)
    html_path = OUTPUT_DIR / f"{date_str}_sweep.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n[write] {html_path}")

    if results:
        best_name = max(results.keys(),
                        key=lambda n: perf(results[n]["strategy_return"], n).get("sharpe", -1))
        csv_path = OUTPUT_DIR / f"{date_str}_{best_name}_signals.csv"
        results[best_name].to_csv(csv_path, index=False)
        print(f"[write] {csv_path} (best: {best_name})")


if __name__ == "__main__":
    main()
