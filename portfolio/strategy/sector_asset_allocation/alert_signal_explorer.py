"""ALERT 시그널 재설계 실험.

가설: 현재 ALERT (MAIN 과 같은 4쌍 + [1,3,6M]) 는 94% 일치 → 차별화 부족.
  → 다른 섹터 조합 + 더 짧은 lookback 으로 단기 트렌드 감지력 강화 가능.

측정 지표:
  1. Agreement rate   : MAIN 과 시그널 일치율 (낮을수록 차별화 ↑)
  2. Disagree Hit Rate: 불일치 월에 ALERT 가 맞춘 비율 (50%+ 면 가치 있음)
  3. Combined Sharpe  : "일치=full, 불일치=Neutral" 조합 전략 성과
  4. Short-term IC    : 다음달 실현 KR-US 수익 차와 ALERT agg 상관

Usage:
    python -m portfolio.strategy.sector_asset_allocation.alert_signal_explorer
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

# MAIN 시그널 (고정)
MAIN_CFG = Config(
    name="MAIN (6M-only, 4쌍)",
    pairs=SECTOR_PAIRS_ECO4,
    w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
    tau=0.02, lookbacks=[6],
)


def _cfg(name: str, pairs: list, lookbacks: list) -> Config:
    return Config(
        name=name, pairs=pairs,
        w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
        tau=0.02, lookbacks=lookbacks,
        min_pairs=min(3, len(pairs)),
    )


# ALERT 후보 Pool
def alert_candidates():
    """(label, pairs, lookbacks) 조합 생성."""
    label_to_pair = {p[2]: p for p in SECTOR_PAIRS_5}
    # 섹터 조합 변형
    pair_sets = {
        "4econ (current)":  SECTOR_PAIRS_ECO4,  # IT/FIN/ENERGY/STAPLES
        "Full 5":           SECTOR_PAIRS_5,
        "4 w/ DISCR":       [label_to_pair[l] for l in ["IT", "FIN", "ENERGY", "DISCR"]],
        "3 cyclical":       [label_to_pair[l] for l in ["IT", "FIN", "DISCR"]],
        "3 defensive+IT":   [label_to_pair[l] for l in ["IT", "STAPLES", "ENERGY"]],
        "IT+DISCR only":    [label_to_pair[l] for l in ["IT", "DISCR"]],
        "DISCR+ENERGY":     [label_to_pair[l] for l in ["DISCR", "ENERGY"]],
    }
    # 짧은 lookback 조합
    lookback_sets = {
        "1M":       [1],
        "1+2M":     [1, 2],
        "1+3M":     [1, 3],
        "2M":       [2],
        "2+3M":     [2, 3],
        "1+2+3M":   [1, 2, 3],
        "3M":       [3],
        # 비교용
        "1+3+6M":   [1, 3, 6],
        "6M":       [6],
    }

    out = []
    for ps_label, pairs in pair_sets.items():
        for lb_label, lbs in lookback_sets.items():
            if len(pairs) < 2:
                continue
            name = f"{ps_label} × {lb_label}"
            out.append((name, pairs, lbs))
    return out


# ─────────────────────────────────────────────────────
# 평가
# ─────────────────────────────────────────────────────

def evaluate_alert(pivot: pd.DataFrame, main_bt: pd.DataFrame,
                   cfg: Config) -> dict:
    """ALERT 후보 평가."""
    alert_bt = run_backtest(cfg, pivot)
    if alert_bt.empty:
        return None

    df = pd.merge(
        main_bt[["as_of", "signal", "agg", "kr_return", "us_return", "blend_return"]].rename(
            columns={"signal": "m_sig", "agg": "m_agg"}),
        alert_bt[["as_of", "signal", "agg"]].rename(
            columns={"signal": "a_sig", "agg": "a_agg"}),
        on="as_of", how="inner",
    )
    if df.empty:
        return None

    n = len(df)
    # 1. Agreement rate
    agree_mask = df["m_sig"] == df["a_sig"]
    agree_rate = agree_mask.sum() / n

    # 2. Disagreement hit rate
    # 불일치 월에서 실제 다음달 kr_return vs us_return 비교
    disagree = df[~agree_mask].copy()
    if len(disagree) > 0:
        disagree["actual"] = np.where(
            disagree["kr_return"] > disagree["us_return"], "KR", "US"
        )
        alert_correct = (disagree["a_sig"] == disagree["actual"]).sum()
        # Hold 을 제외한 실질 투표만
        actionable = disagree[disagree["a_sig"].isin(["KR", "US"])]
        if len(actionable) > 0:
            alert_correct_act = (actionable["a_sig"] == actionable["actual"]).sum()
            hit_rate = alert_correct_act / len(actionable)
        else:
            hit_rate = None
        disagree_n = len(disagree)
    else:
        hit_rate = None
        disagree_n = 0

    # 3. Combined strategy: 일치 시 full, 불일치 시 Neutral
    combined_ret = []
    prev_sig = None
    cost = 30 / 10_000
    for _, r in df.iterrows():
        m, a = r["m_sig"], r["a_sig"]
        if m == a:
            # 일치 → MAIN 방향 full
            if m == "KR":
                ret = r["kr_return"]
                sig = "KR"
            elif m == "US":
                ret = r["us_return"]
                sig = "US"
            else:
                ret = r["blend_return"]
                sig = "Neutral"
        else:
            # 불일치 → Neutral (50/50)
            ret = r["blend_return"]
            sig = "Neutral"
        tc = cost if (prev_sig is not None and sig != prev_sig) else 0
        combined_ret.append(ret - tc)
        prev_sig = sig

    combined_series = pd.Series(combined_ret)
    m_combined = perf(combined_series, "combined")

    # 4. Short-term IC (불일치 월에서 ALERT agg vs 실현 KR-US diff 상관)
    if len(disagree) > 3:
        ic = disagree["a_agg"].corr(
            disagree["kr_return"] - disagree["us_return"]
        )
    else:
        ic = None

    return {
        "name":          cfg.name,
        "pairs":         len(cfg.pairs),
        "lookbacks":     str(cfg.lookbacks),
        "agree_rate":    agree_rate,
        "disagree_n":    disagree_n,
        "hit_rate":      hit_rate,
        "combined_cagr": m_combined["ann_return"],
        "combined_sharpe": m_combined["sharpe"],
        "combined_mdd":  m_combined["mdd"],
        "ic":            ic,
        "alert_sharpe":  perf(alert_bt["strategy_return"], "alert")["sharpe"],
    }


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pivot = load_all_data(start=BACKTEST_START)
    print(f"[load] {pivot.shape}")

    # MAIN 백테스트 (고정)
    main_bt = run_backtest(MAIN_CFG, pivot)
    main_sharpe = perf(main_bt["strategy_return"], "MAIN")["sharpe"]
    main_cagr = perf(main_bt["strategy_return"], "MAIN")["ann_return"]
    print(f"[MAIN] Sharpe {main_sharpe:.2f} · CAGR {main_cagr*100:+.2f}%")

    # ALERT 후보 평가
    candidates = alert_candidates()
    print(f"\n[sweep] {len(candidates)} ALERT 후보 평가")

    results = []
    for name, pairs, lbs in candidates:
        cfg = _cfg(name, pairs, lbs)
        r = evaluate_alert(pivot, main_bt, cfg)
        if r:
            results.append(r)

    df = pd.DataFrame(results).sort_values("combined_sharpe", ascending=False)

    # 출력
    print("\n" + "=" * 130)
    print(f"{'ALERT 후보':40s} {'#쌍':>4s} {'Lookback':>12s} "
          f"{'일치%':>6s} {'불일치':>7s} {'적중%':>6s} {'IC':>6s} "
          f"{'조합Sh':>7s} {'조합CAGR':>9s} {'조합MDD':>8s}")
    print("=" * 130)
    for i, r in df.iterrows():
        hit = f"{r['hit_rate']*100:.0f}%" if r['hit_rate'] is not None else "N/A"
        ic = f"{r['ic']:+.2f}" if r['ic'] is not None else "N/A"
        print(f"{r['name']:40s} {r['pairs']:>4d} {r['lookbacks']:>12s} "
              f"{r['agree_rate']*100:>5.0f}% {r['disagree_n']:>7d} {hit:>6s} {ic:>6s} "
              f"{r['combined_sharpe']:>+7.2f} {r['combined_cagr']*100:>+8.2f}% "
              f"{r['combined_mdd']*100:>+7.1f}%")

    # 최고 후보
    best = df.iloc[0]
    print("\n" + "=" * 80)
    print("★ 최고 조합 Sharpe 후보 (MAIN vs ALERT 일치=full, 불일치=Neutral)")
    print("=" * 80)
    print(f"  {best['name']}")
    print(f"  일치율 {best['agree_rate']*100:.0f}% · 불일치 {best['disagree_n']}회 · "
          f"적중 {best['hit_rate']*100 if best['hit_rate'] else 0:.0f}%")
    print(f"  조합 Sharpe {best['combined_sharpe']:+.2f} (MAIN 단독 {main_sharpe:+.2f})")
    print(f"  조합 CAGR   {best['combined_cagr']*100:+.2f}% (MAIN 단독 {main_cagr*100:+.2f}%)")

    # CSV
    df.to_csv(OUTPUT_DIR / "alert_explorer_results.csv", index=False)

    # HTML
    html = _build_html(df, main_sharpe, main_cagr)
    out = OUTPUT_DIR / "alert_explorer.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n[write] {out}")
    print(f"[write] {OUTPUT_DIR / 'alert_explorer_results.csv'}")


def _build_html(df: pd.DataFrame, main_sharpe: float, main_cagr: float) -> str:
    rows = ""
    for _, r in df.iterrows():
        hit = f"{r['hit_rate']*100:.0f}%" if r['hit_rate'] is not None else "—"
        ic = f"{r['ic']:+.2f}" if r['ic'] is not None else "—"

        better = r['combined_sharpe'] > main_sharpe
        bg = "#DBEAFE" if better else ""
        mark = "★ " if better else ""

        rows += (
            f"<tr style='background:{bg}'>"
            f"<td>{mark}{r['name']}</td>"
            f"<td class='num'>{r['pairs']}</td>"
            f"<td class='num'>{r['lookbacks']}</td>"
            f"<td class='num'>{r['agree_rate']*100:.0f}%</td>"
            f"<td class='num'>{r['disagree_n']}</td>"
            f"<td class='num'>{hit}</td>"
            f"<td class='num'>{ic}</td>"
            f"<td class='num' style='font-weight:700'>{r['combined_sharpe']:+.2f}</td>"
            f"<td class='num'>{r['combined_cagr']*100:+.2f}%</td>"
            f"<td class='num' style='color:#DC2626'>{r['combined_mdd']*100:.1f}%</td>"
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>ALERT Signal Explorer</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; background: #F7F8FA;
         color: #1F2937; padding: 24px; max-width: 1400px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; font-weight: 800; margin-bottom: 4px; }}
  .subtitle {{ color: #6B7280; font-size: 0.85rem; margin-bottom: 24px; }}
  h2 {{ font-size: 1rem; color: #111827; margin: 28px 0 10px; padding-left: 10px;
        border-left: 3px solid #F58220; }}
  table {{ width: 100%; background: #fff; border-collapse: collapse; font-size: 0.82rem;
          border-radius: 8px; overflow: hidden; border: 1px solid #E5E7EB; }}
  th {{ background: #F3F4F6; padding: 9px 10px; text-align: left; font-weight: 600;
       color: #374151; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #F3F4F6; font-family: 'SF Mono', Menlo, monospace; font-size: 0.78rem; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; font-family: inherit; }}
  .baseline {{ background: #fff; border-left: 4px solid #F58220; padding: 14px 18px;
              border-radius: 6px; margin-bottom: 16px; }}
  .note {{ color: #6B7280; font-size: 0.78rem; margin-top: 8px; line-height: 1.55; }}
</style></head><body>

<h1>ALERT 시그널 재설계 실험</h1>
<div class="subtitle">MAIN 고정 (6M-only, 4쌍 경제축) × ALERT 변형 {len(df)} 조합 × 조합 전략 평가</div>

<div class="baseline">
  <b>MAIN 단독 baseline</b>: Sharpe <b>{main_sharpe:.2f}</b> · CAGR <b>{main_cagr*100:+.2f}%</b><br>
  <span class="note">★ = ALERT 를 조합 했을 때 MAIN 단독보다 나은 조합 (Sharpe 기준)</span>
</div>

<h2>평가 지표 해석</h2>
<div class="note">
  <b>일치%</b>: MAIN 과 같은 시그널 월 비율 (낮을수록 차별화 ↑)<br>
  <b>불일치</b>: 두 시그널 다른 개월 수<br>
  <b>적중%</b>: 불일치 월 중 ALERT 가 실제 방향 맞춘 비율 (50% 넘으면 가치 있음)<br>
  <b>IC</b>: 불일치 월에서 ALERT agg 와 실현 (KR-US) 수익 상관 (높을수록 예측력 ↑)<br>
  <b>조합 Sharpe</b>: "일치=full position, 불일치=Neutral" 조합 전략의 Sharpe<br>
</div>

<h2>전체 {len(df)} 후보 결과 (조합 Sharpe 내림차순)</h2>
<table>
  <thead><tr>
    <th>ALERT 후보</th><th>#쌍</th><th>Lookback</th>
    <th>일치%</th><th>불일치</th><th>적중%</th><th>IC</th>
    <th>조합 Sharpe</th><th>조합 CAGR</th><th>조합 MDD</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>

</body></html>
"""


if __name__ == "__main__":
    main()
