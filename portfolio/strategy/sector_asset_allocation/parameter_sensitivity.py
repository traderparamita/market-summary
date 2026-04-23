"""Parameter Sensitivity 상세 sweep.

챔피언 파라미터 주변에서 각 축을 독립적으로 흔들며 Sharpe 민감도 측정.

검증 대상:
  A. 1D — w_fx (FX 가중) 0.0 → 0.5 (0.05 간격)
  B. 1D — tau (임계값) 0.005 → 0.035 (0.005 간격)
  C. 1D — lookback 조합 7가지
  D. 1D — 거래비용 10bp → 100bp
  E. 1D — 섹터 조합 (DISCR/FIN/IT/ENERGY/STAPLES 중 하나 제외)
  F. 2D — w_fx × tau heatmap

각 축에서 "Sharpe 가 champion 대비 10% 이내 유지되는 robust region" 확인.

Usage:
    python -m portfolio.strategy.sector_asset_allocation.parameter_sensitivity
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.strategy.sector_asset_allocation.core import (
    BACKTEST_START, Config, load_all_data, run_backtest, perf,
    SECTOR_PAIRS_5, SECTOR_PAIRS_ECO4,
)

OUTPUT_DIR = Path(__file__).parent / "outputs"

# 챔피언 (drop_DISCR_w30_usdkrw_tau0.020)
CHAMPION = Config(
    name="Champion",
    pairs=SECTOR_PAIRS_ECO4,
    w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
    tau=0.02, cost_bps=30,
    lookbacks=[1, 3, 6],
)


def _cfg_variant(**overrides) -> Config:
    """챔피언 복제 후 일부 필드 덮어쓰기."""
    from dataclasses import replace
    return replace(CHAMPION, **overrides)


def _run_and_metric(cfg: Config, pivot: pd.DataFrame) -> dict:
    bt = run_backtest(cfg, pivot)
    if bt.empty:
        return {"sharpe": None, "cagr": None, "mdd": None, "n": 0}
    m = perf(bt["strategy_return"], cfg.name)
    return {"sharpe": m["sharpe"], "cagr": m["ann_return"], "mdd": m["mdd"], "n": m["n_months"]}


# ─────────────────────────────────────────────────────
# 1D Sensitivities
# ─────────────────────────────────────────────────────

def sweep_w_fx(pivot):
    print("\n[A] w_fx sweep (0.0 → 0.5)")
    results = []
    for w_fx in np.arange(0.0, 0.51, 0.05):
        w_fx = round(w_fx, 2)
        name = f"w_fx={w_fx:.2f}"
        cfg = _cfg_variant(name=name, w_rs=1.0 - w_fx, w_fx=w_fx,
                           fx_source="none" if w_fx == 0 else "usdkrw")
        m = _run_and_metric(cfg, pivot)
        results.append({"axis": "w_fx", "param": w_fx, "label": f"{w_fx:.2f}", **m})
        print(f"    {name}: Sharpe {m['sharpe']:.2f}")
    return results


def sweep_tau(pivot):
    print("\n[B] tau sweep (0.005 → 0.035)")
    results = []
    for tau in np.arange(0.005, 0.0351, 0.005):
        tau = round(tau, 3)
        name = f"tau={tau:.3f}"
        cfg = _cfg_variant(name=name, tau=tau)
        m = _run_and_metric(cfg, pivot)
        results.append({"axis": "tau", "param": tau, "label": f"{tau:.3f}", **m})
        print(f"    {name}: Sharpe {m['sharpe']:.2f}")
    return results


def sweep_lookback(pivot):
    print("\n[C] lookback 조합 sweep")
    combos = [
        ("1M", [1]),
        ("3M", [3]),
        ("6M", [6]),
        ("1M+3M", [1, 3]),
        ("3M+6M", [3, 6]),
        ("1M+3M+6M (champion)", [1, 3, 6]),
        ("1M+3M+6M+12M", [1, 3, 6, 12]),
        ("2M+4M+8M", [2, 4, 8]),
    ]
    results = []
    for label, lbs in combos:
        cfg = _cfg_variant(name=f"lookback={label}", lookbacks=lbs)
        m = _run_and_metric(cfg, pivot)
        results.append({"axis": "lookback", "param": ",".join(map(str, lbs)),
                        "label": label, **m})
        print(f"    {label}: Sharpe {m['sharpe']:.2f}")
    return results


def sweep_cost(pivot):
    print("\n[D] 거래비용 sweep (10 → 100 bps)")
    results = []
    for cost in [10, 20, 30, 40, 50, 60, 80, 100]:
        cfg = _cfg_variant(name=f"cost={cost}bp", cost_bps=cost)
        m = _run_and_metric(cfg, pivot)
        results.append({"axis": "cost", "param": cost, "label": f"{cost}bp", **m})
        print(f"    {cost}bp: Sharpe {m['sharpe']:.2f}  CAGR {m['cagr']*100:+.2f}%")
    return results


def sweep_sector(pivot):
    print("\n[E] 섹터 조합 sweep")
    variants = [
        ("Full 5 pairs", SECTOR_PAIRS_5),
    ]
    label_to_code = {p[2]: p for p in SECTOR_PAIRS_5}
    for drop_label in ["IT", "FIN", "ENERGY", "DISCR", "STAPLES"]:
        subset = [p for p in SECTOR_PAIRS_5 if p[2] != drop_label]
        variants.append((f"drop {drop_label}", subset))
    results = []
    for label, pairs_list in variants:
        is_champ = (label == "drop DISCR")
        cfg = _cfg_variant(name=f"sector={label}", pairs=pairs_list)
        m = _run_and_metric(cfg, pivot)
        results.append({"axis": "sector", "param": label, "label": label,
                        "is_champion": is_champ, **m})
        sh = f"{m['sharpe']:.2f}" if m['sharpe'] is not None else "N/A"
        print(f"    {'★ ' if is_champ else '  '}{label}: Sharpe {sh}")
    return results


# ─────────────────────────────────────────────────────
# 2D Heatmap — w_fx × tau
# ─────────────────────────────────────────────────────

def sweep_heatmap(pivot):
    print("\n[F] 2D heatmap — w_fx × tau")
    w_fx_vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    tau_vals = [0.010, 0.015, 0.020, 0.025, 0.030]
    grid = np.zeros((len(tau_vals), len(w_fx_vals)))
    for i, tau in enumerate(tau_vals):
        row = []
        for j, w_fx in enumerate(w_fx_vals):
            cfg = _cfg_variant(name=f"wfx{w_fx:.2f}_tau{tau:.3f}",
                               w_rs=1.0 - w_fx, w_fx=w_fx,
                               fx_source="none" if w_fx == 0 else "usdkrw",
                               tau=tau)
            m = _run_and_metric(cfg, pivot)
            grid[i, j] = m["sharpe"] or 0
            row.append(f"{m['sharpe']:.2f}" if m["sharpe"] else "—")
        print(f"    tau={tau:.3f}: " + "  ".join(f"{v:>5}" for v in row))
    return grid, w_fx_vals, tau_vals


# ─────────────────────────────────────────────────────
# Robustness 평가
# ─────────────────────────────────────────────────────

def _compute_robust_stats(results_1d: list[dict], champion_sharpe: float) -> dict:
    sharpes = [r["sharpe"] for r in results_1d if r["sharpe"] is not None]
    within_10pct = sum(1 for s in sharpes if s >= champion_sharpe * 0.9)
    within_20pct = sum(1 for s in sharpes if s >= champion_sharpe * 0.8)
    return {
        "n": len(sharpes),
        "min": min(sharpes) if sharpes else None,
        "max": max(sharpes) if sharpes else None,
        "std": np.std(sharpes) if sharpes else None,
        "champion": champion_sharpe,
        "within_10pct": within_10pct,
        "within_20pct": within_20pct,
    }


# ─────────────────────────────────────────────────────
# HTML 생성
# ─────────────────────────────────────────────────────

def _line_chart_block(canvas_id: str, title: str, labels: list,
                       data: list, champ_val: float) -> str:
    colors = ["#F58220" if v == champ_val else "#6B7280" for v in data]
    datasets = [
        {"label": "Sharpe", "data": data,
         "borderColor": "#F58220", "backgroundColor": "rgba(245,130,32,0.15)",
         "borderWidth": 2, "tension": 0.2,
         "pointBackgroundColor": colors, "pointRadius": 5},
        {"label": "Champion band (±10%)",
         "data": [champ_val * 0.9] * len(data),
         "borderColor": "rgba(220,38,38,0.3)", "borderDash": [4, 4],
         "borderWidth": 1, "pointRadius": 0, "fill": False},
    ]
    return (
        f"<h3>{title}</h3>"
        f"<div class='canvas-wrap'><canvas id='{canvas_id}' style='max-height:260px'></canvas></div>"
        f"<script>new Chart(document.getElementById('{canvas_id}'),"
        f"{{type:'line',data:{{labels:{json.dumps(labels)},datasets:{json.dumps(datasets)}}},"
        f"options:{{responsive:true,plugins:{{legend:{{display:false}}}},"
        f"scales:{{y:{{title:{{display:true,text:'Sharpe'}}}}}}}}}});</script>"
    )


def _heatmap_block(grid: np.ndarray, w_fx_vals: list, tau_vals: list,
                    champion_sharpe: float) -> str:
    rows = ""
    for i, tau in enumerate(tau_vals):
        row_cells = f"<td style='font-weight:700'>{tau:.3f}</td>"
        for j, w_fx in enumerate(w_fx_vals):
            s = grid[i, j]
            # Color scale: green(high) → yellow(mid) → red(low)
            t = max(0, min(1, (s - 0.3) / (1.0 - 0.3)))
            r = int(255 * (1 - t) + 100 * t)
            g = int(100 * (1 - t) + 200 * t)
            b = int(100 * (1 - t) + 100 * t)
            bg = f"rgb({r},{g},{b})"
            is_champ = (abs(w_fx - 0.3) < 0.01 and abs(tau - 0.02) < 0.001)
            border = "border:2px solid #DC2626;" if is_champ else ""
            mark = "★" if is_champ else ""
            row_cells += (
                f"<td style='background:{bg};color:#fff;font-weight:700;text-align:center;{border}'>"
                f"{mark}{s:.2f}</td>"
            )
        rows += f"<tr>{row_cells}</tr>"

    header = "<tr><th>τ \\ w_fx</th>" + "".join(f"<th>{w:.2f}</th>" for w in w_fx_vals) + "</tr>"
    return (
        "<h3>F. 2D Heatmap: w_fx × tau</h3>"
        f"<table class='heatmap'><thead>{header}</thead><tbody>{rows}</tbody></table>"
        "<p class='note'>★ = 챔피언 (w_fx=0.30, τ=0.020). 셀 값 = Full-sample Sharpe. 진한 녹색일수록 높음.</p>"
    )


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pivot = load_all_data(start=BACKTEST_START)
    print(f"[load] {pivot.shape}")

    # 챔피언 기준 성과
    champ_m = _run_and_metric(CHAMPION, pivot)
    champion_sharpe = champ_m["sharpe"]
    print(f"[Champion] Sharpe {champion_sharpe:.2f}, CAGR {champ_m['cagr']*100:+.2f}%, MDD {champ_m['mdd']*100:.1f}%")

    # 1D sensitivities
    w_fx_results    = sweep_w_fx(pivot)
    tau_results     = sweep_tau(pivot)
    lookback_results = sweep_lookback(pivot)
    cost_results    = sweep_cost(pivot)
    sector_results  = sweep_sector(pivot)

    # 2D heatmap
    grid, w_fx_vals, tau_vals = sweep_heatmap(pivot)

    # Robustness 통계
    print("\n" + "=" * 70)
    print("Robustness (Sharpe 유지 비율)")
    print("=" * 70)
    for label, results in [
        ("w_fx", w_fx_results), ("tau", tau_results),
        ("lookback", lookback_results), ("cost", cost_results),
        ("sector", sector_results),
    ]:
        stats = _compute_robust_stats(results, champion_sharpe)
        print(f"  {label:10s}  n={stats['n']:2d}  "
              f"range=[{stats['min']:.2f}, {stats['max']:.2f}]  "
              f"within_10%={stats['within_10pct']}/{stats['n']}  "
              f"within_20%={stats['within_20pct']}/{stats['n']}")

    # ── HTML ─────────────────────────────────────────
    def _table_rows(results, champion_filter=None) -> str:
        out = ""
        for r in results:
            is_champ = champion_filter and champion_filter(r)
            bg = "background:#FFF7EE;font-weight:700;" if is_champ else ""
            mark = "★ " if is_champ else ""
            delta = (r["sharpe"] - champion_sharpe) if r["sharpe"] else 0
            delta_color = "#16A34A" if delta >= 0 else "#DC2626"
            out += (
                f"<tr style='{bg}'>"
                f"<td>{mark}{r['label']}</td>"
                f"<td class='num'>{r['sharpe']:.2f}</td>"
                f"<td class='num'>{r['cagr']*100:+.2f}%</td>"
                f"<td class='num' style='color:#DC2626'>{r['mdd']*100:.1f}%</td>"
                f"<td class='num' style='color:{delta_color}'>{delta:+.2f}</td>"
                f"</tr>"
            )
        return out

    champ_filters = {
        "w_fx":    lambda r: abs(r["param"] - 0.30) < 0.01,
        "tau":     lambda r: abs(r["param"] - 0.020) < 0.001,
        "lookback": lambda r: r["label"] == "1M+3M+6M (champion)",
        "cost":    lambda r: r["param"] == 30,
        "sector":  lambda r: r.get("is_champion", False),
    }

    sections_html = ""
    for axis_label, axis_title, results in [
        ("w_fx",     "A. FX 가중 (w_fx) 민감도",              w_fx_results),
        ("tau",      "B. 임계값 (tau) 민감도",                tau_results),
        ("lookback", "C. 룩백 조합 민감도",                    lookback_results),
        ("cost",     "D. 거래비용 민감도",                      cost_results),
        ("sector",   "E. 섹터 조합 민감도",                     sector_results),
    ]:
        stats = _compute_robust_stats(results, champion_sharpe)
        badge = "✓ 견고" if stats["within_10pct"] >= stats["n"] * 0.6 else (
                "⚠ 중간" if stats["within_10pct"] >= stats["n"] * 0.3 else "✗ 민감")
        filt = champ_filters[axis_label]
        rows = _table_rows(results, champion_filter=filt)
        chart_labels = [r["label"] for r in results]
        chart_data = [r["sharpe"] for r in results]

        sections_html += (
            f"<h2>{axis_title}</h2>"
            f"<p class='note'>범위 [{stats['min']:.2f}, {stats['max']:.2f}] · "
            f"챔피언±10% 내 {stats['within_10pct']}/{stats['n']} · "
            f"챔피언±20% 내 {stats['within_20pct']}/{stats['n']} · <b>{badge}</b></p>"
            + _line_chart_block(f"chart_{axis_label}", "", chart_labels, chart_data, champion_sharpe)
            + f"<table><thead><tr><th>값</th><th>Sharpe</th><th>CAGR</th><th>MDD</th>"
            + f"<th>Δ Sharpe</th></tr></thead><tbody>{rows}</tbody></table>"
        )

    heatmap_html = _heatmap_block(grid, w_fx_vals, tau_vals, champion_sharpe)

    # 종합 verdict
    total_tests = sum(_compute_robust_stats(r, champion_sharpe)["n"] for r in
                       [w_fx_results, tau_results, lookback_results, cost_results, sector_results])
    total_within_10 = sum(_compute_robust_stats(r, champion_sharpe)["within_10pct"] for r in
                           [w_fx_results, tau_results, lookback_results, cost_results, sector_results])
    robust_ratio = total_within_10 / total_tests if total_tests else 0

    verdict = f"전체 {total_tests}개 검증 중 {total_within_10}개 ({robust_ratio*100:.0f}%) 가 챔피언 Sharpe 의 90% 이상 유지"
    if robust_ratio >= 0.5:
        verdict_icon = "✅ 견고"
    elif robust_ratio >= 0.3:
        verdict_icon = "⚠ 부분 견고"
    else:
        verdict_icon = "❌ 민감"

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>Parameter Sensitivity</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, sans-serif; background: #F7F8FA; color: #1F2937; padding: 24px; max-width: 1280px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; font-weight: 800; margin-bottom: 4px; }}
  .subtitle {{ color: #6B7280; font-size: 0.85rem; margin-bottom: 24px; }}
  h2 {{ font-size: 1rem; color: #111827; margin: 28px 0 10px; padding-left: 10px; border-left: 3px solid #F58220; }}
  h3 {{ font-size: 0.9rem; color: #374151; margin: 12px 0 6px; }}
  table {{ width: 100%; background: #fff; border-collapse: collapse; font-size: 0.85rem;
          border-radius: 8px; overflow: hidden; border: 1px solid #E5E7EB; margin: 12px 0; }}
  th {{ background: #F3F4F6; padding: 8px 10px; text-align: left; font-weight: 600; color: #374151; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #F3F4F6; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr:last-child td {{ border-bottom: none; }}
  .canvas-wrap {{ background: #fff; padding: 12px; border-radius: 8px; border: 1px solid #E5E7EB; margin: 8px 0; }}
  .verdict {{ background: #fff; border-left: 4px solid #F58220; padding: 14px 18px; border-radius: 6px; margin: 16px 0 24px; }}
  .note {{ color: #6B7280; font-size: 0.78rem; margin: 4px 0 8px; }}
  table.heatmap td {{ padding: 12px 16px; font-family: 'SF Mono', Menlo, monospace; }}
  table.heatmap th {{ padding: 8px 16px; text-align: center; }}
</style></head><body>

<h1>Parameter Sensitivity 상세 분석</h1>
<div class="subtitle">챔피언 (drop_DISCR / w_fx=0.30 / τ=0.020 / lookback=[1,3,6] / cost=30bp) 주변 민감도</div>

<div class="verdict">
  <h2 style="border:none;padding:0;margin:0 0 6px">종합 결론</h2>
  <p><b>{verdict_icon}</b> — {verdict}</p>
  <p class='note'>챔피언 Sharpe = {champion_sharpe:.2f} (Full sample). 각 축에서 10% 이내 유지되면 "견고한 파라미터 영역" 으로 판단.</p>
</div>

{sections_html}

<h2>F. 2D Heatmap (w_fx × tau 동시 변화)</h2>
{heatmap_html}

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
</body></html>
"""
    out = OUTPUT_DIR / "parameter_sensitivity.html"
    out.write_text(html, encoding="utf-8")

    # CSV 저장
    all_results = (
        [{**r, "axis_label": "w_fx"} for r in w_fx_results]
        + [{**r, "axis_label": "tau"} for r in tau_results]
        + [{**r, "axis_label": "lookback"} for r in lookback_results]
        + [{**r, "axis_label": "cost"} for r in cost_results]
        + [{**r, "axis_label": "sector"} for r in sector_results]
    )
    pd.DataFrame(all_results).to_csv(OUTPUT_DIR / "parameter_sensitivity_results.csv", index=False)
    print(f"\n[write] {out}")
    print(f"[write] {OUTPUT_DIR / 'parameter_sensitivity_results.csv'}")
    print(f"\n{verdict_icon} {verdict}")


if __name__ == "__main__":
    main()
