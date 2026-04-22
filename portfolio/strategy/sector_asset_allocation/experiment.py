"""전체 실험 runner — 4 phase 순차 실행 + HTML 보고서.

Phase 1: Benchmarks (50/50 / KOSPI / S&P500)
Phase 2: Sector Selection (A. 전체 5쌍 / B. 상관 기반 4쌍 / C. 경제축 4쌍)
Phase 3: FX Overlay (USDKRW / DXY / Both × 가중 0/20/30/50)
Phase 4: Combined Sweep + Champion

Usage:
    python -m portfolio.strategy.sector_asset_allocation.experiment
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.strategy.sector_asset_allocation.core import (
    BACKTEST_START, KOSPI_CODE, SP500_CODE,
    SECTOR_PAIRS_5, SECTOR_PAIRS_ECO4,
    Config, load_all_data, run_backtest, perf,
    compute_rs_timeseries, select_low_correlation_subset,
)

OUTPUT_DIR = Path(__file__).parent / "outputs"


# ─────────────────────────────────────────────────────
# 공통 HTML 빌더
# ─────────────────────────────────────────────────────

_BASE_CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Pretendard', sans-serif; background: #F7F8FA; color: #1F2937;
         padding: 24px; max-width: 1280px; margin: 0 auto; }
  h1 { font-size: 1.5rem; font-weight: 800; margin-bottom: 4px; }
  .subtitle { color: #6B7280; font-size: 0.85rem; margin-bottom: 24px; }
  h2 { font-size: 1rem; color: #111827; margin: 28px 0 10px; padding-left: 10px; border-left: 3px solid #F58220; }
  table { width: 100%; background: #fff; border-collapse: collapse; font-size: 0.85rem;
          border-radius: 8px; overflow: hidden; border: 1px solid #E5E7EB; }
  th { background: #F3F4F6; padding: 9px 10px; text-align: left; font-weight: 600; color: #374151;
       border-bottom: 1px solid #E5E7EB; }
  td { padding: 8px 10px; border-bottom: 1px solid #F3F4F6; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr:last-child td { border-bottom: none; }
  .canvas-wrap { background: #fff; padding: 16px; border-radius: 10px; border: 1px solid #E5E7EB; }
  .note { color: #6B7280; font-size: 0.78rem; margin-top: 8px; line-height: 1.55; }
  .champion { background: #FFF7EE; font-weight: 700; }
  code { font-family: 'SF Mono', Menlo, monospace; font-size: 0.78rem; color: #6B7280;
         background: #F3F4F6; padding: 1px 5px; border-radius: 3px; }
"""


def metric_table_rows(rows: list[dict], champion_label: str | None = None) -> str:
    """성과 dict 리스트 → HTML 테이블 rows."""
    out = ""
    for m in rows:
        if not m:
            continue
        is_champ = (m.get("label") == champion_label)
        trstyle = "class='champion'" if is_champ else ""
        mark = "🏆 " if is_champ else ""
        out += (
            f"<tr {trstyle}>"
            f"<td>{mark}{m['label']}</td>"
            f"<td class='num'>{m['total_return']*100:+.1f}%</td>"
            f"<td class='num'>{m['ann_return']*100:+.1f}%</td>"
            f"<td class='num'>{m['ann_vol']*100:.1f}%</td>"
            f"<td class='num'><b>{m['sharpe']:.2f}</b></td>"
            f"<td class='num' style='color:#DC2626'>{m['mdd']*100:.1f}%</td>"
            f"<td class='num'>{m['win_rate']*100:.0f}%</td>"
            f"<td class='num'>{m['n_months']}</td>"
            f"</tr>"
        )
    return out


_METRIC_TABLE_HEAD = (
    "<thead><tr><th>전략</th><th>Total</th><th>CAGR</th><th>연변동</th>"
    "<th>Sharpe</th><th>MDD</th><th>Win%</th><th>#월</th></tr></thead>"
)


def cumulative_chart(results: dict[str, pd.Series], title: str, canvas_id: str) -> str:
    """전략별 누적 수익 Chart.js 블록."""
    # x-axis: 첫 번째 시리즈 기준
    first = next(iter(results.values()))
    labels = first.index.strftime("%Y-%m-%d").tolist() if hasattr(first.index, "strftime") else list(range(len(first)))

    palette = ["#F58220", "#E63946", "#059669", "#8B5CF6", "#0EA5E9",
               "#F59E0B", "#EC4899", "#6366F1", "#14B8A6", "#F97316",
               "#DC2626", "#84CC16"]
    datasets = []
    for i, (name, ser) in enumerate(results.items()):
        cum = ((1 + ser).cumprod() - 1).fillna(0).round(4).tolist()
        is_bench = ("benchmark" in name.lower() or name in ("KOSPI", "S&P500", "50/50 Blend"))
        datasets.append({
            "label": name, "data": cum,
            "borderColor": "#6B7280" if is_bench else palette[i % len(palette)],
            "borderDash": [5, 4] if is_bench else [],
            "backgroundColor": "transparent",
            "borderWidth": 1.2 if is_bench else 1.8,
            "tension": 0.15,
        })

    return (
        f"<h2>{title}</h2>"
        f"<div class='canvas-wrap'><canvas id='{canvas_id}' style='max-height:380px'></canvas></div>"
        f"<script>new Chart(document.getElementById('{canvas_id}'), "
        f"{{ type:'line', data: {{labels:{json.dumps(labels)}, datasets:{json.dumps(datasets)} }}, "
        f"options: {{ responsive:true, plugins: {{ legend: {{ position:'top', "
        f"labels:{{ usePointStyle:true, pointStyle:'line', font:{{size:10}} }} }} }}, "
        f"scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }}, "
        f"x: {{ ticks: {{ maxTicksLimit:12 }} }} }} }} }});</script>"
    )


def write_html(path: Path, title: str, body: str) -> None:
    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<title>{title}</title><style>{_BASE_CSS}</style>
</head><body>{body}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
</body></html>"""
    path.write_text(html, encoding="utf-8")


# ─────────────────────────────────────────────────────
# Phase 1 — Benchmarks
# ─────────────────────────────────────────────────────

def phase1_benchmarks(pivot: pd.DataFrame) -> dict:
    print("\n" + "=" * 70)
    print("Phase 1 — 벤치마크")
    print("=" * 70)

    # Mean-RS baseline 없이 pure buy-and-hold 같은 벤치마크 3개
    cfg_blend = Config(name="50/50 Blend", w_rs=0.0, w_fx=0.0, tau=999)  # tau=999 이면 전혀 안 바뀜 → 항상 Neutral
    bt_blend = run_backtest(cfg_blend, pivot)

    if bt_blend.empty:
        raise RuntimeError("Phase 1: 백테스트 실패")

    date_index = pd.to_datetime(bt_blend["as_of"])
    bench_series = {
        "50/50 Blend": pd.Series(bt_blend["blend_return"].values, index=date_index),
        "KOSPI":       pd.Series(bt_blend["kr_return"].values,    index=date_index),
        "S&P500":      pd.Series(bt_blend["us_return"].values,    index=date_index),
    }

    metrics = [perf(s, name) for name, s in bench_series.items()]
    for m in metrics:
        print(f"  {m['label']:15s}  CAGR {m['ann_return']*100:+6.2f}%  "
              f"Sharpe {m['sharpe']:+5.2f}  MDD {m['mdd']*100:+6.1f}%")

    # HTML
    body = (
        f"<h1>Phase 1 — 벤치마크 수립</h1>"
        f"<div class='subtitle'>{BACKTEST_START} ~ {bt_blend['as_of'].iloc[-1]} · {len(bt_blend)}개월</div>"
        f"<p class='note'>이길 대상: 가장 Sharpe 높은 S&P500 과 가장 CAGR 우수한 포트폴리오.</p>"
        f"<h2>성과</h2>"
        f"<table>{_METRIC_TABLE_HEAD}<tbody>{metric_table_rows(metrics)}</tbody></table>"
        + cumulative_chart(bench_series, "누적 수익률", "p1cum")
    )
    write_html(OUTPUT_DIR / "phase1_benchmarks.html", "Phase 1 — Benchmarks", body)

    return {"metrics": metrics, "series": bench_series, "date_index": date_index}


# ─────────────────────────────────────────────────────
# Phase 2 — Sector Selection (A. 전체 5쌍 / B. 상관 기반 / C. 경제축)
# ─────────────────────────────────────────────────────

def phase2_sector_selection(pivot: pd.DataFrame, phase1: dict) -> dict:
    print("\n" + "=" * 70)
    print("Phase 2 — 섹터 구성 실험 (FX 없이 순수 Mean-RS)")
    print("=" * 70)

    # (A) 전체 5쌍
    cfg_A = Config(name="A. 전체 5쌍 (All 5)", pairs=SECTOR_PAIRS_5, w_rs=1.0, w_fx=0.0)
    # (B) 상관 기반 자동 선택 4쌍
    pairs_B = select_low_correlation_subset(pivot, k=4, pool=SECTOR_PAIRS_5)
    labels_B = [p[2] for p in pairs_B]
    cfg_B = Config(name=f"B. 상관최소 4쌍 ({'+'.join(labels_B)})",
                   pairs=pairs_B, w_rs=1.0, w_fx=0.0)
    # (C) 경제축 4쌍
    cfg_C = Config(name="C. 경제축 4쌍 (IT+FIN+ENERGY+STAPLES)",
                   pairs=SECTOR_PAIRS_ECO4, w_rs=1.0, w_fx=0.0)

    backtests = {}
    series_dict = dict(phase1["series"])  # 벤치마크 포함
    metrics = []
    for cfg in [cfg_A, cfg_B, cfg_C]:
        bt = run_backtest(cfg, pivot)
        if bt.empty:
            continue
        backtests[cfg.name] = bt
        date_idx = pd.to_datetime(bt["as_of"])
        ser = pd.Series(bt["strategy_return"].values, index=date_idx)
        series_dict[cfg.name] = ser
        m = perf(ser, cfg.name)
        metrics.append(m)
        print(f"  {cfg.name:42s}  CAGR {m['ann_return']*100:+6.2f}%  "
              f"Sharpe {m['sharpe']:+5.2f}  MDD {m['mdd']*100:+6.1f}%")

    # 벤치마크 metrics 도 같이
    all_metrics = metrics + phase1["metrics"]
    # 상관 매트릭스 계산 & HTML 출력 (섹터 상관 참고용)
    df_rs = compute_rs_timeseries(pivot, SECTOR_PAIRS_5)
    corr = df_rs.corr()
    corr_html = "<table><thead><tr><th></th>"
    for c in corr.columns:
        corr_html += f"<th style='text-align:center'>{c}</th>"
    corr_html += "</tr></thead><tbody>"
    for i, row in corr.iterrows():
        corr_html += f"<tr><td><b>{i}</b></td>"
        for j, v in row.items():
            bg = "" if i == j else (
                "background:#FEE2E2" if v > 0.5 else ("background:#FEF3C7" if v > 0.3 else "")
            )
            corr_html += f"<td class='num' style='{bg}'>{v:+.2f}</td>" if i != j else "<td class='num'>—</td>"
        corr_html += "</tr>"
    corr_html += "</tbody></table>"

    best_name = max(metrics, key=lambda m: m["sharpe"])["label"]
    body = (
        f"<h1>Phase 2 — 섹터 구성 실험 (FX 없이)</h1>"
        f"<div class='subtitle'>3가지 섹터 선택 방식 비교 · 2011-04 이후 clean</div>"
        f"<h2>5 섹터 RS 내부 상관 매트릭스 (3M 로그수익 차)</h2>{corr_html}"
        f"<p class='note'>빨간 셀 = 상관 &gt; 0.5 (정보 중복), 노란 = 0.3-0.5</p>"
        f"<h2>3가지 섹터 구성 성과</h2>"
        f"<table>{_METRIC_TABLE_HEAD}<tbody>{metric_table_rows(all_metrics, best_name)}</tbody></table>"
        + cumulative_chart(series_dict, "누적 수익률 (Phase 2)", "p2cum")
    )
    write_html(OUTPUT_DIR / "phase2_sector_selection.html", "Phase 2 — Sector Selection", body)

    return {
        "configs": {"A": cfg_A, "B": cfg_B, "C": cfg_C},
        "pairs_B": pairs_B,
        "metrics": metrics,
        "series": series_dict,
        "best_name": best_name,
    }


# ─────────────────────────────────────────────────────
# Phase 3 — FX Overlay
# ─────────────────────────────────────────────────────

def phase3_fx_overlay(pivot: pd.DataFrame, phase2: dict, phase1: dict) -> dict:
    print("\n" + "=" * 70)
    print("Phase 3 — FX Overlay (Phase 2 에서 이긴 구성 × FX 가중 sweep)")
    print("=" * 70)

    # Phase 2 에서 Sharpe 최고 구성을 베이스로 FX 가중 실험
    best_name = phase2["best_name"]
    base_cfg = next(c for c in phase2["configs"].values() if c.name == best_name)
    print(f"  베이스 구성: {base_cfg.name}")

    # FX 가중 × source 조합
    fx_weights = [0.0, 0.2, 0.3, 0.5]
    fx_sources = ["usdkrw", "dxy"]

    metrics = []
    series_dict = {}
    configs_out = []

    # baseline (FX 없음) 먼저
    cfg0 = Config(name=f"(base) {base_cfg.pairs[0][2]}+... FX=0%",
                  pairs=base_cfg.pairs, w_rs=1.0, w_fx=0.0)
    bt0 = run_backtest(cfg0, pivot)
    if not bt0.empty:
        ser = pd.Series(bt0["strategy_return"].values, index=pd.to_datetime(bt0["as_of"]))
        m = perf(ser, cfg0.name)
        metrics.append(m); series_dict[cfg0.name] = ser; configs_out.append(cfg0)
        print(f"  {cfg0.name:50s}  CAGR {m['ann_return']*100:+6.2f}%  Sharpe {m['sharpe']:+5.2f}  MDD {m['mdd']*100:+6.1f}%")

    # FX sweep
    for w_fx in fx_weights:
        if w_fx == 0:
            continue
        for src in fx_sources:
            cfg = Config(
                name=f"{src.upper()} {int(w_fx*100)}%",
                pairs=base_cfg.pairs,
                w_rs=1.0 - w_fx, w_fx=w_fx, fx_source=src,
            )
            bt = run_backtest(cfg, pivot)
            if bt.empty:
                continue
            ser = pd.Series(bt["strategy_return"].values, index=pd.to_datetime(bt["as_of"]))
            m = perf(ser, cfg.name)
            metrics.append(m); series_dict[cfg.name] = ser; configs_out.append(cfg)
            print(f"  {cfg.name:50s}  CAGR {m['ann_return']*100:+6.2f}%  "
                  f"Sharpe {m['sharpe']:+5.2f}  MDD {m['mdd']*100:+6.1f}%")

    # 벤치마크도 차트에 포함
    chart_series = {**series_dict, **phase1["series"]}

    all_metrics = metrics + phase1["metrics"]
    best = max(metrics, key=lambda m: m["sharpe"])
    body = (
        f"<h1>Phase 3 — FX Overlay</h1>"
        f"<div class='subtitle'>베이스 구성: <b>{best_name}</b> · USDKRW 또는 DXY × 가중 sweep</div>"
        f"<h2>성과 비교</h2>"
        f"<table>{_METRIC_TABLE_HEAD}<tbody>{metric_table_rows(all_metrics, best['label'])}</tbody></table>"
        f"<p class='note'>FX tilt 계산: tanh(3M 수익률 / 0.03). USDKRW↑(원화 약세) → KR 편향.</p>"
        + cumulative_chart(chart_series, "누적 수익률 (Phase 3)", "p3cum")
    )
    write_html(OUTPUT_DIR / "phase3_fx_overlay.html", "Phase 3 — FX Overlay", body)

    return {
        "configs": configs_out,
        "metrics": metrics,
        "best_name": best["label"],
        "series": series_dict,
    }


# ─────────────────────────────────────────────────────
# Phase 4 — Combined Sweep & Champion
# ─────────────────────────────────────────────────────

def phase4_champion(pivot: pd.DataFrame, phase1: dict, phase2: dict, phase3: dict) -> dict:
    print("\n" + "=" * 70)
    print("Phase 4 — 최종 Sweep: 섹터 구성 3종 × FX 가중 4개 × FX 소스 2종")
    print("=" * 70)

    sector_configs = phase2["configs"]
    fx_weights = [0.0, 0.2, 0.3, 0.5]
    fx_sources = ["usdkrw", "dxy"]

    metrics = []
    series_dict = {}
    all_results = []

    for pkey, base_cfg in sector_configs.items():
        # no FX
        cfg0 = Config(name=f"{pkey}+FX0", pairs=base_cfg.pairs, w_rs=1.0, w_fx=0.0)
        bt = run_backtest(cfg0, pivot)
        if not bt.empty:
            ser = pd.Series(bt["strategy_return"].values, index=pd.to_datetime(bt["as_of"]))
            m = perf(ser, cfg0.name); m["_cfg"] = cfg0
            metrics.append(m); series_dict[cfg0.name] = ser
            all_results.append((cfg0.name, bt, m))

        for w_fx in fx_weights:
            if w_fx == 0:
                continue
            for src in fx_sources:
                name = f"{pkey}+{src.upper()}{int(w_fx*100)}"
                cfg = Config(
                    name=name, pairs=base_cfg.pairs,
                    w_rs=1.0 - w_fx, w_fx=w_fx, fx_source=src,
                )
                bt = run_backtest(cfg, pivot)
                if bt.empty:
                    continue
                ser = pd.Series(bt["strategy_return"].values, index=pd.to_datetime(bt["as_of"]))
                m = perf(ser, name); m["_cfg"] = cfg
                metrics.append(m); series_dict[name] = ser
                all_results.append((name, bt, m))

    # Sharpe 기준 챔피언
    metrics_sorted = sorted(metrics, key=lambda m: -m["sharpe"])
    champion = metrics_sorted[0]
    champ_name = champion["label"]
    champ_cfg: Config = champion["_cfg"]
    champ_bt = next(bt for n, bt, _ in all_results if n == champ_name)

    print(f"\n  🏆 Champion: {champ_name}")
    print(f"     CAGR {champion['ann_return']*100:+6.2f}% / "
          f"Sharpe {champion['sharpe']:+5.2f} / MDD {champion['mdd']*100:+6.1f}%")

    # 결과 저장
    signals_path = OUTPUT_DIR / "final_champion_signals.csv"
    champ_bt.to_csv(signals_path, index=False)
    print(f"     Signals → {signals_path}")

    # HTML 전체 결과
    # 챔피언 표시를 위해 metrics 에서 _cfg 제거
    clean_metrics = [{k: v for k, v in m.items() if not k.startswith("_")} for m in metrics_sorted]
    all_metrics = clean_metrics + phase1["metrics"]

    # 차트에는 상위 5개 + 벤치마크만
    top5_series = {n: series_dict[n] for _, _, m in all_results for n in [m["label"]]}  # all
    # 실제로 상위 5
    top_names = [m["label"] for m in metrics_sorted[:5]]
    chart_series = {n: series_dict[n] for n in top_names}
    chart_series.update(phase1["series"])

    # config diff 요약 (챔피언)
    cfg_details = (
        f"<p><b>Pairs</b>: {' · '.join(p[2] for p in champ_cfg.pairs)}</p>"
        f"<p><b>w_rs</b>: {champ_cfg.w_rs:.2f} · <b>w_fx</b>: {champ_cfg.w_fx:.2f} · "
        f"<b>fx_source</b>: {champ_cfg.fx_source} · <b>tau</b>: {champ_cfg.tau}</p>"
    )

    body = (
        f"<h1>Phase 4 — 최종 Champion</h1>"
        f"<div class='subtitle'>{len(metrics)} config sweep · {BACKTEST_START} ~ {champ_bt['as_of'].iloc[-1]} ({len(champ_bt)}개월)</div>"
        f"<h2>🏆 Champion: {champ_name}</h2>{cfg_details}"
        f"<h2>전체 성과 (Sharpe 내림차순)</h2>"
        f"<table>{_METRIC_TABLE_HEAD}<tbody>{metric_table_rows(all_metrics, champ_name)}</tbody></table>"
        + cumulative_chart(chart_series, "누적 수익률 — 상위 5 전략 + 벤치마크", "p4cum")
    )
    write_html(OUTPUT_DIR / "phase4_champion.html", "Phase 4 — Champion", body)

    return {
        "champion": champion,
        "champion_cfg": champ_cfg,
        "champion_bt": champ_bt,
        "all_metrics": metrics_sorted,
    }


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(" Sector-based Asset Allocation Research")
    print(f" 기간: {BACKTEST_START} ~ 현재")
    print("=" * 70)

    pivot = load_all_data()
    print(f"\n[load] {pivot.shape[0]} rows × {pivot.shape[1]} codes")
    print(f"       {pivot.index.min().date()} ~ {pivot.index.max().date()}")

    p1 = phase1_benchmarks(pivot)
    p2 = phase2_sector_selection(pivot, p1)
    p3 = phase3_fx_overlay(pivot, p2, p1)
    p4 = phase4_champion(pivot, p1, p2, p3)

    print("\n" + "=" * 70)
    print(" 완료")
    print("=" * 70)
    for p in ["phase1_benchmarks.html", "phase2_sector_selection.html",
              "phase3_fx_overlay.html", "phase4_champion.html",
              "final_champion_signals.csv"]:
        print(f"  {OUTPUT_DIR / p}")


if __name__ == "__main__":
    main()
