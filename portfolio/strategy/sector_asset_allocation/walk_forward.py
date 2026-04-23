"""Walk-forward OOS 검증.

구조:
  Train (2011-04 ~ 2018-12, 93개월): 파라미터 sweep 수행
  Test  (2019-01 ~ 2026-04, 88개월): Train 에서 선택된 최적 파라미터로 OOS 백테스트

검증 포인트:
  1. Train 최적 config 이 Test 에서도 Sharpe 유지?
  2. In-sample (전체) Sharpe 와 Test (OOS) Sharpe 격차?
  3. Bootstrap 으로 Test Sharpe 의 95% CI

Usage:
    python -m portfolio.strategy.sector_asset_allocation.walk_forward
"""
from __future__ import annotations

import json
from dataclasses import asdict
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.strategy.sector_asset_allocation.core import (
    BACKTEST_START, Config, load_all_data, run_backtest, perf,
    SECTOR_PAIRS_5, SECTOR_PAIRS_ECO4,
)

OUTPUT_DIR = Path(__file__).parent / "outputs"

TRAIN_START = "2011-04-01"
TRAIN_END   = "2018-12-31"
TEST_START  = "2019-01-01"
TEST_END    = "2026-04-30"


# ─────────────────────────────────────────────────────
# 파라미터 공간 — 120 조합
# ─────────────────────────────────────────────────────

def pair_candidates() -> list[tuple[str, list]]:
    """섹터 조합 5가지 (full 5, drop each of 5)."""
    all_labels = [p[2] for p in SECTOR_PAIRS_5]
    cands = [("Full5", SECTOR_PAIRS_5)]
    for drop_label in all_labels:
        subset = [p for p in SECTOR_PAIRS_5 if p[2] != drop_label]
        cands.append((f"drop_{drop_label}", subset))
    return cands


def param_grid():
    """sweep 파라미터 조합."""
    pair_list = pair_candidates()
    w_fx_vals = [0.0, 0.2, 0.3, 0.5]
    fx_sources = ["usdkrw", "dxy"]
    taus = [0.015, 0.02, 0.025]

    for (pname, pairs), w_fx, fx_src, tau in product(pair_list, w_fx_vals, fx_sources, taus):
        if w_fx == 0 and fx_src == "dxy":
            continue  # w_fx=0 이면 fx_src 무관 → usdkrw 한 번만
        name = f"{pname}_w{int(w_fx*100):02d}_{fx_src}_tau{tau:.3f}"
        yield name, Config(
            name=name, pairs=pairs,
            w_rs=1.0 - w_fx, w_fx=w_fx,
            fx_source=fx_src if w_fx > 0 else "none",
            tau=tau,
        )


# ─────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────

def _slice_bt(bt: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    dates = pd.to_datetime(bt["as_of"])
    mask = (dates >= start) & (dates <= end)
    return bt.loc[mask].reset_index(drop=True)


def _bootstrap_sharpe_ci(rets: np.ndarray, n_boot: int = 3000, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(rets)
    sharpes = []
    for _ in range(n_boot):
        sample = rng.choice(rets, size=n, replace=True)
        c = (1 + sample).prod() ** (12/n) - 1
        v = sample.std() * np.sqrt(12)
        if v > 0:
            sharpes.append(c / v)
    return float(np.percentile(sharpes, 2.5)), float(np.percentile(sharpes, 97.5))


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pivot = load_all_data(start=BACKTEST_START)
    print(f"[load] {pivot.shape}")
    print(f"       Train: {TRAIN_START} ~ {TRAIN_END}")
    print(f"       Test : {TEST_START} ~ {TEST_END}")

    # ── Full sweep: 모든 config 를 전체 기간 백테스트 → train/test 슬라이스 ──
    print("\n[sweep] 파라미터 공간 전수 탐색 ...")
    results: list[dict] = []
    total = sum(1 for _ in param_grid())
    print(f"       총 {total} 조합")

    for i, (name, cfg) in enumerate(param_grid(), 1):
        bt_full = run_backtest(cfg, pivot)
        if bt_full.empty:
            continue
        bt_train = _slice_bt(bt_full, TRAIN_START, TRAIN_END)
        bt_test  = _slice_bt(bt_full, TEST_START,  TEST_END)

        if len(bt_train) < 50 or len(bt_test) < 50:
            continue

        m_train = perf(bt_train["strategy_return"], "train")
        m_test  = perf(bt_test["strategy_return"],  "test")
        m_full  = perf(bt_full["strategy_return"], "full")

        results.append({
            "name": name,
            "pairs_key": cfg.name.split("_")[0],
            "w_fx": cfg.w_fx,
            "fx_source": cfg.fx_source,
            "tau": cfg.tau,
            "train_sharpe": m_train["sharpe"],
            "train_cagr":   m_train["ann_return"],
            "train_mdd":    m_train["mdd"],
            "test_sharpe":  m_test["sharpe"],
            "test_cagr":    m_test["ann_return"],
            "test_mdd":     m_test["mdd"],
            "full_sharpe":  m_full["sharpe"],
            "full_cagr":    m_full["ann_return"],
            "full_mdd":     m_full["mdd"],
            "bt_test":      bt_test,
        })
        if i % 30 == 0:
            print(f"       {i}/{total} ...")

    df = pd.DataFrame([{k: v for k, v in r.items() if k != "bt_test"} for r in results])
    df = df.sort_values("train_sharpe", ascending=False).reset_index(drop=True)

    # ── Train 최상위 10 config 의 Test 성과 ──
    print("\n" + "=" * 110)
    print("Train 상위 10개 Config 의 Train / Test / Full 성과")
    print("=" * 110)
    print(f"{'#':>2} {'Config':55s} {'Train Sharpe':>12s} {'Test Sharpe':>12s} {'Full Sharpe':>12s} {'Decay':>8s}")
    top10 = df.head(10)
    for i, r in top10.iterrows():
        decay = r["test_sharpe"] - r["train_sharpe"]
        print(f"{i+1:>2} {r['name']:55s} {r['train_sharpe']:>12.2f} {r['test_sharpe']:>12.2f} "
              f"{r['full_sharpe']:>12.2f} {decay:>+8.2f}")

    # ── 챔피언 (기존 4쌍 + USDKRW w30 + tau 0.02) 의 Train/Test ──
    CHAMP_NAME = "drop_DISCR_w30_usdkrw_tau0.020"
    champ_row = df[df["name"] == CHAMP_NAME]
    if champ_row.empty:
        print(f"\n[WARN] 챔피언 {CHAMP_NAME} 못 찾음")
    else:
        r = champ_row.iloc[0]
        print(f"\n[Champion] {CHAMP_NAME}")
        print(f"  Train Sharpe {r['train_sharpe']:.2f} / CAGR {r['train_cagr']*100:+.2f}% / MDD {r['train_mdd']*100:.1f}%")
        print(f"  Test  Sharpe {r['test_sharpe']:.2f} / CAGR {r['test_cagr']*100:+.2f}% / MDD {r['test_mdd']*100:.1f}%")
        print(f"  Full  Sharpe {r['full_sharpe']:.2f} / CAGR {r['full_cagr']*100:+.2f}% / MDD {r['full_mdd']*100:.1f}%")

        # Test 구간 Sharpe CI
        champ_bt = next(x["bt_test"] for x in results if x["name"] == CHAMP_NAME)
        lo, hi = _bootstrap_sharpe_ci(champ_bt["strategy_return"].values, n_boot=5000)
        print(f"  Test Sharpe 95% CI: [{lo:.2f}, {hi:.2f}]")

    # ── Test 기준 re-rank ──
    print("\n" + "=" * 110)
    print("[참고] Test Sharpe 내림차순 상위 10")
    print("=" * 110)
    df_by_test = df.sort_values("test_sharpe", ascending=False).reset_index(drop=True).head(10)
    for i, r in df_by_test.iterrows():
        print(f"{i+1:>2} {r['name']:55s} Train {r['train_sharpe']:+5.2f} | Test {r['test_sharpe']:+5.2f} | Full {r['full_sharpe']:+5.2f}")

    # ── Train Sharpe vs Test Sharpe 산점도 ──
    # HTML 생성
    labels = []
    train_sharpes = []
    test_sharpes = []
    config_names = []
    for _, r in df.iterrows():
        config_names.append(r["name"])
        train_sharpes.append(r["train_sharpe"])
        test_sharpes.append(r["test_sharpe"])

    # Champion highlight
    champ_train = champ_row.iloc[0]["train_sharpe"] if not champ_row.empty else None
    champ_test  = champ_row.iloc[0]["test_sharpe"]  if not champ_row.empty else None

    # 챔피언 test 누적 수익 차트 (vs benchmark)
    if not champ_row.empty:
        champ_bt = next(x["bt_test"] for x in results if x["name"] == CHAMP_NAME)
        test_dates = champ_bt["as_of"].tolist()
        cum_strat = ((1 + champ_bt["strategy_return"]).cumprod() - 1).round(4).tolist()
        cum_blend = ((1 + champ_bt["blend_return"]).cumprod() - 1).round(4).tolist()
        cum_kospi = ((1 + champ_bt["kr_return"]).cumprod() - 1).round(4).tolist()
        cum_sp500 = ((1 + champ_bt["us_return"]).cumprod() - 1).round(4).tolist()
    else:
        test_dates = cum_strat = cum_blend = cum_kospi = cum_sp500 = []

    # ── Summary 판단 ──
    decay_median = df["test_sharpe"].median() - df["train_sharpe"].median()
    champ_decay = (champ_row.iloc[0]["test_sharpe"] - champ_row.iloc[0]["train_sharpe"]
                   if not champ_row.empty else 0)

    verdict_lines = []
    if not champ_row.empty:
        if champ_test >= champ_train * 0.8:
            verdict_lines.append(f"✅ 챔피언 Test Sharpe ({champ_test:.2f}) 가 Train Sharpe ({champ_train:.2f}) 의 80% 이상 유지 → 견고")
        elif champ_test >= champ_train * 0.5:
            verdict_lines.append(f"⚠ 챔피언 Test Sharpe ({champ_test:.2f}) 가 Train 대비 상당 하락 (Train {champ_train:.2f})")
        else:
            verdict_lines.append(f"❌ 챔피언 Test Sharpe ({champ_test:.2f}) << Train ({champ_train:.2f}) → 과적합 의심")

    if abs(decay_median) < 0.1:
        verdict_lines.append(f"✅ 전체 config median decay {decay_median:+.2f} — 체계적 overfit 없음")
    else:
        verdict_lines.append(f"⚠ 전체 config median decay {decay_median:+.2f}")

    print("\n" + "=" * 60)
    print("검증 결과")
    print("=" * 60)
    for line in verdict_lines:
        print(f"  {line}")

    # ── HTML ─────────────────────────────────────────
    def _fmt_table(df_sub, n=10):
        rows = ""
        for i, r in df_sub.head(n).iterrows():
            decay = r["test_sharpe"] - r["train_sharpe"]
            dc = "#16A34A" if decay >= -0.1 else ("#DC2626" if decay < -0.3 else "#D97706")
            mark = "🏆 " if r["name"] == CHAMP_NAME else ""
            bg = "background:#FFF7EE;font-weight:700" if r["name"] == CHAMP_NAME else ""
            rows += (
                f'<tr style="{bg}">'
                f'<td>{mark}{r["name"]}</td>'
                f'<td class="num">{r["train_sharpe"]:.2f}</td>'
                f'<td class="num">{r["train_cagr"]*100:+.1f}%</td>'
                f'<td class="num">{r["test_sharpe"]:.2f}</td>'
                f'<td class="num">{r["test_cagr"]*100:+.1f}%</td>'
                f'<td class="num" style="color:{dc}">{decay:+.2f}</td>'
                f'<td class="num">{r["full_sharpe"]:.2f}</td>'
                f'</tr>'
            )
        return rows

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>Walk-forward OOS</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, sans-serif; background: #F7F8FA; color: #1F2937; padding: 24px; max-width: 1280px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; font-weight: 800; margin-bottom: 4px; }}
  .subtitle {{ color: #6B7280; font-size: 0.85rem; margin-bottom: 24px; }}
  h2 {{ font-size: 1rem; color: #111827; margin: 28px 0 10px; padding-left: 10px; border-left: 3px solid #F58220; }}
  table {{ width: 100%; background: #fff; border-collapse: collapse; font-size: 0.85rem; border-radius: 8px; overflow: hidden; border: 1px solid #E5E7EB; }}
  th {{ background: #F3F4F6; padding: 9px 10px; text-align: left; font-weight: 600; color: #374151; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #F3F4F6; font-family: 'SF Mono', Menlo, monospace; font-size: 0.78rem; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; font-family: inherit; }}
  .canvas-wrap {{ background: #fff; padding: 16px; border-radius: 10px; border: 1px solid #E5E7EB; }}
  .verdict {{ background: #fff; border-left: 4px solid #F58220; padding: 14px 18px; border-radius: 6px; margin-bottom: 20px; }}
  .verdict p {{ margin: 4px 0; font-size: 0.88rem; }}
  .hero {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
  .hero-card {{ background: #fff; padding: 16px; border-radius: 10px; border: 1px solid #E5E7EB; }}
  .hero-label {{ font-size: 0.72rem; color: #6B7280; text-transform: uppercase; letter-spacing: 0.05em; }}
  .hero-value {{ font-size: 1.6rem; font-weight: 800; margin-top: 4px; }}
  .hero-sub {{ font-size: 0.78rem; color: #6B7280; margin-top: 2px; }}
</style>
</head><body>

<h1>Walk-forward OOS 검증</h1>
<div class="subtitle">Train {TRAIN_START} ~ {TRAIN_END} (93개월) → Test {TEST_START} ~ {TEST_END} (88개월)</div>

<div class="verdict">
  <h2 style="border:none;padding:0;margin:0 0 8px">검증 결론</h2>
  {''.join(f'<p>{line}</p>' for line in verdict_lines)}
</div>

<h2>🏆 챔피언 성과 (drop_DISCR_w30_usdkrw_tau0.020)</h2>
<div class="hero">
  <div class="hero-card">
    <div class="hero-label">Train (2011-2018)</div>
    <div class="hero-value">Sharpe {champ_row.iloc[0]['train_sharpe']:.2f}</div>
    <div class="hero-sub">CAGR {champ_row.iloc[0]['train_cagr']*100:+.2f}% · MDD {champ_row.iloc[0]['train_mdd']*100:.1f}%</div>
  </div>
  <div class="hero-card" style="border-color:#F58220;border-width:2px">
    <div class="hero-label">Test (2019-2026) ★ OOS</div>
    <div class="hero-value" style="color:#F58220">Sharpe {champ_row.iloc[0]['test_sharpe']:.2f}</div>
    <div class="hero-sub">CAGR {champ_row.iloc[0]['test_cagr']*100:+.2f}% · MDD {champ_row.iloc[0]['test_mdd']*100:.1f}%</div>
  </div>
  <div class="hero-card">
    <div class="hero-label">Full (전체)</div>
    <div class="hero-value">Sharpe {champ_row.iloc[0]['full_sharpe']:.2f}</div>
    <div class="hero-sub">CAGR {champ_row.iloc[0]['full_cagr']*100:+.2f}% · MDD {champ_row.iloc[0]['full_mdd']*100:.1f}%</div>
  </div>
</div>

<h2>Test 구간 누적 수익 (OOS 검증)</h2>
<div class="canvas-wrap"><canvas id="cumTest" style="max-height:380px"></canvas></div>

<h2>Train Sharpe vs Test Sharpe 산점도 (전체 {len(df)} config)</h2>
<div class="canvas-wrap"><canvas id="scatter" style="max-height:380px"></canvas></div>
<p style="font-size:0.78rem;color:#6B7280;margin-top:8px">각 점은 하나의 config. 대각선 위면 Test 가 Train 보다 좋음(보기 드뭄), 아래면 decay. 챔피언은 주황 큰 점.</p>

<h2>Train Sharpe 상위 10 Config (Train/Test 비교)</h2>
<table>
  <thead><tr>
    <th>Config</th>
    <th>Train Sharpe</th><th>Train CAGR</th>
    <th>Test Sharpe</th><th>Test CAGR</th>
    <th>Decay</th>
    <th>Full Sharpe</th>
  </tr></thead>
  <tbody>{_fmt_table(df, 10)}</tbody>
</table>

<h2>Test Sharpe 상위 10 (참고)</h2>
<table>
  <thead><tr>
    <th>Config</th>
    <th>Train Sharpe</th><th>Train CAGR</th>
    <th>Test Sharpe</th><th>Test CAGR</th>
    <th>Decay</th>
    <th>Full Sharpe</th>
  </tr></thead>
  <tbody>{_fmt_table(df.sort_values('test_sharpe', ascending=False), 10)}</tbody>
</table>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  // 누적수익 (OOS)
  new Chart(document.getElementById('cumTest'), {{
    type: 'line',
    data: {{ labels: {json.dumps(test_dates)}, datasets: [
      {{ label: '챔피언 전략', data: {json.dumps(cum_strat)}, borderColor: '#F58220', borderWidth: 2.5, backgroundColor: 'transparent', tension: 0.15 }},
      {{ label: '50/50 Blend', data: {json.dumps(cum_blend)}, borderColor: '#6B7280', borderDash: [5,4], borderWidth: 1.2, backgroundColor: 'transparent' }},
      {{ label: 'KOSPI', data: {json.dumps(cum_kospi)}, borderColor: '#E63946', borderDash: [3,3], borderWidth: 1, backgroundColor: 'transparent' }},
      {{ label: 'S&P500', data: {json.dumps(cum_sp500)}, borderColor: '#1D3557', borderDash: [3,3], borderWidth: 1, backgroundColor: 'transparent' }},
    ]}},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }},
                scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }}, x: {{ ticks: {{ maxTicksLimit: 10 }} }} }} }}
  }});

  // 산점도 Train vs Test Sharpe
  const scatterPoints = {json.dumps([{"x": ts, "y": es, "label": name} for name, ts, es in zip(config_names, train_sharpes, test_sharpes)])};
  const champPoint = {'null' if champ_train is None else '{"x":' + f'{champ_train}' + ',"y":' + f'{champ_test}' + ',"label":"CHAMPION"}'};
  new Chart(document.getElementById('scatter'), {{
    type: 'scatter',
    data: {{ datasets: [
      {{ label: 'All configs', data: scatterPoints,
         backgroundColor: 'rgba(29,53,87,0.45)', pointRadius: 3 }},
      ...(champPoint ? [{{ label: 'Champion', data: [champPoint],
         backgroundColor: '#F58220', pointRadius: 10, pointBorderColor: '#7F1D1D', pointBorderWidth: 2 }}] : []),
    ]}},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position: 'top' }},
                  tooltip: {{ callbacks: {{ label: c => c.raw.label + ' (T:' + c.raw.x.toFixed(2) + ' / OOS:' + c.raw.y.toFixed(2) + ')' }} }} }},
      scales: {{
        x: {{ title: {{ display: true, text: 'Train Sharpe (2011-2018)' }}, min: -0.5, max: 2 }},
        y: {{ title: {{ display: true, text: 'Test Sharpe OOS (2019-2026)' }}, min: -0.5, max: 2 }},
      }}
    }}
  }});
</script>
</body></html>
"""

    out = OUTPUT_DIR / "walk_forward.html"
    out.write_text(html, encoding="utf-8")
    df.to_csv(OUTPUT_DIR / "walk_forward_results.csv", index=False)
    print(f"\n[write] {out}")
    print(f"[write] {OUTPUT_DIR / 'walk_forward_results.csv'}")


if __name__ == "__main__":
    main()
