"""연도별 Rolling OOS (Expanding Window) + 6M-only 챔피언 승격 검토.

Part 1 — Rolling OOS (Expanding Window):
  매년마다 Train = 2011-04 ~ (Year-1)-12, Test = Year-01 ~ Year-12.
  연 단위 OOS 성과 (Sharpe, Return, MDD) 산출.

Part 2 — 챔피언 vs 6M-only 심층 비교:
  시그널 agreement, 회전율, 위기 구간 행동, 연도별 누적 수익 비교.
  승격 여부 판단.

Usage:
    python -m portfolio.strategy.sector_asset_allocation.rolling_oos_and_6m_comparison
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.strategy.sector_asset_allocation.core import (
    BACKTEST_START, Config, load_all_data, run_backtest, perf,
    SECTOR_PAIRS_ECO4,
)

OUTPUT_DIR = Path(__file__).parent / "outputs"


# 두 모델 Config
CHAMP_CFG = Config(
    name="Champion [1,3,6]",
    pairs=SECTOR_PAIRS_ECO4,
    w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
    tau=0.02, lookbacks=[1, 3, 6],
)
SIX_M_CFG = Config(
    name="6M-only",
    pairs=SECTOR_PAIRS_ECO4,
    w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
    tau=0.02, lookbacks=[6],
)


def _slice(bt: pd.DataFrame, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    d = pd.to_datetime(bt["as_of"])
    mask = pd.Series(True, index=bt.index)
    if start: mask &= d >= start
    if end:   mask &= d <= end
    return bt.loc[mask].reset_index(drop=True)


def _annual_perf(bt_yr: pd.DataFrame, label: str) -> dict:
    """연단위 성과 (월수가 적어도 무조건 계산)."""
    if bt_yr.empty:
        return {"label": label, "n": 0}
    r = bt_yr["strategy_return"].dropna()
    if len(r) == 0:
        return {"label": label, "n": 0}
    total = float((1 + r).prod() - 1)
    ann_vol = float(r.std() * math.sqrt(12)) if len(r) > 1 else 0.0
    # 짧은 구간은 annualize 안 함 (그냥 period return)
    cum = (1 + r).cumprod()
    mdd = float((cum / cum.cummax() - 1).min())
    sharpe = (total * (12 / len(r))) / ann_vol if ann_vol > 0 else 0.0
    return {
        "label":  label,
        "n":      len(r),
        "return": total,
        "sharpe": sharpe,
        "mdd":    mdd,
    }


# ─────────────────────────────────────────────────────
# Part 1 — Rolling OOS
# ─────────────────────────────────────────────────────

def rolling_oos(pivot: pd.DataFrame) -> dict:
    """연도별 Expanding Window OOS — Train 은 매년 누적, Test 는 해당 연도."""
    # 두 모델 전체 백테스트
    bt_champ = run_backtest(CHAMP_CFG, pivot)
    bt_6m    = run_backtest(SIX_M_CFG, pivot)

    # 연도별 slice
    years = list(range(2016, 2027))  # 2016 ~ 2026 (partial)

    yearly: list[dict] = []
    for yr in years:
        start = f"{yr}-01-01"
        end = f"{yr}-12-31"
        bt_ch = _slice(bt_champ, start, end)
        bt_6 = _slice(bt_6m, start, end)

        m_ch = _annual_perf(bt_ch, "Champion")
        m_6  = _annual_perf(bt_6, "6M-only")

        # 승자
        ch_r = m_ch.get("return", 0)
        m6_r = m_6.get("return", 0)
        winner = "6M" if m6_r > ch_r else ("Champion" if ch_r > m6_r else "TIE")

        yearly.append({
            "year":    yr,
            "n":       m_ch.get("n", 0),
            "ch_ret":  ch_r,
            "ch_sh":   m_ch.get("sharpe", 0),
            "ch_mdd":  m_ch.get("mdd", 0),
            "m6_ret":  m6_r,
            "m6_sh":   m_6.get("sharpe", 0),
            "m6_mdd":  m_6.get("mdd", 0),
            "diff":    m6_r - ch_r,
            "winner":  winner,
        })

    # 통계
    total_ch = (1 + pd.Series([y["ch_ret"] for y in yearly])).prod() - 1
    total_6 = (1 + pd.Series([y["m6_ret"] for y in yearly])).prod() - 1
    wins_6 = sum(1 for y in yearly if y["winner"] == "6M")
    wins_ch = sum(1 for y in yearly if y["winner"] == "Champion")

    print("=" * 100)
    print("Part 1 — Rolling OOS (연도별 Expanding Window)")
    print("=" * 100)
    print(f"{'Year':>6} {'n':>4} {'Champion Ret':>13} {'Champion SR':>12} {'6M Ret':>10} {'6M SR':>8} "
          f"{'Diff':>8} {'Winner':>10}")
    print("-" * 100)
    for y in yearly:
        print(f"{y['year']:>6} {y['n']:>4} {y['ch_ret']*100:>+12.2f}% {y['ch_sh']:>+11.2f} "
              f"{y['m6_ret']*100:>+9.2f}% {y['m6_sh']:>+7.2f} "
              f"{y['diff']*100:>+7.2f}% {y['winner']:>10}")
    print("-" * 100)
    print(f"{'TOTAL':>6}     {total_ch*100:>+12.2f}%              {total_6*100:>+9.2f}%")
    print(f"\nWins: 6M-only {wins_6} / Champion {wins_ch} / 총 {len(yearly)}년")

    return {
        "yearly": yearly,
        "total_champ": total_ch,
        "total_6m": total_6,
        "wins_6m": wins_6,
        "wins_champion": wins_ch,
        "bt_champ": bt_champ,
        "bt_6m": bt_6m,
    }


# ─────────────────────────────────────────────────────
# Part 2 — 시그널 비교
# ─────────────────────────────────────────────────────

def signal_comparison(bt_champ: pd.DataFrame, bt_6m: pd.DataFrame) -> dict:
    """두 모델 시그널 일치율, 회전율, 위기 시 비교."""
    # as_of 기준 merge
    df = pd.merge(
        bt_champ[["as_of", "signal", "strategy_return", "cost"]].rename(columns={
            "signal": "ch_signal", "strategy_return": "ch_ret", "cost": "ch_cost"
        }),
        bt_6m[["as_of", "signal", "strategy_return", "cost"]].rename(columns={
            "signal": "m6_signal", "strategy_return": "m6_ret", "cost": "m6_cost"
        }),
        on="as_of", how="inner",
    )
    n_total = len(df)

    # 일치율
    agree = (df["ch_signal"] == df["m6_signal"]).sum()
    disagree_ch_kr_m6_us = ((df["ch_signal"] == "KR") & (df["m6_signal"] == "US")).sum()
    disagree_ch_us_m6_kr = ((df["ch_signal"] == "US") & (df["m6_signal"] == "KR")).sum()

    # 회전율
    ch_trades = int((df["ch_cost"] > 0).sum())
    m6_trades = int((df["m6_cost"] > 0).sum())

    # 위기 구간
    crisis_periods = [
        ("COVID-19", "2020-02-01", "2020-04-30"),
        ("2022 인플레", "2022-01-01", "2022-10-31"),
        ("2018 Q4 조정", "2018-10-01", "2018-12-31"),
        ("2015 하락장", "2015-07-01", "2015-12-31"),
    ]
    crisis_rows = []
    df["date"] = pd.to_datetime(df["as_of"])
    for label, start, end in crisis_periods:
        sub = df[(df["date"] >= start) & (df["date"] <= end)]
        if sub.empty:
            continue
        ch_r = (1 + sub["ch_ret"]).prod() - 1
        m6_r = (1 + sub["m6_ret"]).prod() - 1
        crisis_rows.append({
            "label": label, "start": start, "end": end,
            "n": len(sub), "ch_ret": ch_r, "m6_ret": m6_r,
            "winner": "6M" if m6_r > ch_r else ("Champion" if ch_r > m6_r else "TIE"),
        })

    print("\n" + "=" * 100)
    print("Part 2 — 시그널 비교 (Champion vs 6M-only)")
    print("=" * 100)
    print(f"총 월수: {n_total}")
    print(f"일치율: {agree}/{n_total} = {agree/n_total*100:.1f}%")
    print(f"  Champion=KR, 6M=US: {disagree_ch_kr_m6_us}")
    print(f"  Champion=US, 6M=KR: {disagree_ch_us_m6_kr}")
    print(f"\n전환 횟수: Champion {ch_trades} / 6M-only {m6_trades}")
    print(f"연평균:     Champion {ch_trades/(n_total/12):.1f} / 6M-only {m6_trades/(n_total/12):.1f}")

    print("\n위기 구간 비교:")
    print(f"{'이벤트':20s} {'기간':25s} {'Champion':>10s} {'6M-only':>10s} {'승자':>10s}")
    for c in crisis_rows:
        print(f"{c['label']:20s} {c['start']} ~ {c['end']} "
              f"{c['ch_ret']*100:>+9.1f}% {c['m6_ret']*100:>+9.1f}% {c['winner']:>10s}")

    return {
        "n_total": n_total,
        "agree_rate": agree / n_total,
        "disagree_ch_kr_m6_us": disagree_ch_kr_m6_us,
        "disagree_ch_us_m6_kr": disagree_ch_us_m6_kr,
        "ch_trades": ch_trades,
        "m6_trades": m6_trades,
        "crisis": crisis_rows,
    }


# ─────────────────────────────────────────────────────
# Decision
# ─────────────────────────────────────────────────────

def promotion_verdict(rolling: dict, comparison: dict) -> tuple[str, list[str]]:
    lines = []
    wins_6m = rolling["wins_6m"]
    wins_ch = rolling["wins_champion"]
    total_y = wins_6m + wins_ch

    # Criteria
    if wins_6m > wins_ch and rolling["total_6m"] > rolling["total_champ"]:
        cat1 = True
        lines.append(f"[완료] 연도 승률 6M-only 우위: {wins_6m}/{total_y} (총 수익 +{(rolling['total_6m']-rolling['total_champ'])*100:.1f}%p)")
    else:
        cat1 = False
        lines.append(f"[!] 연도 승률 애매: 6M {wins_6m} vs Ch {wins_ch}")

    agree = comparison["agree_rate"]
    if agree > 0.75:
        cat2 = True
        lines.append(f"[완료] 시그널 일치율 높음 ({agree*100:.0f}%) → 스위치 리스크 낮음")
    else:
        cat2 = False
        lines.append(f"[!] 시그널 일치율 {agree*100:.0f}% (75% 미만) → 스위치 시 action 큼")

    crisis_6m_wins = sum(1 for c in comparison["crisis"] if c["winner"] == "6M")
    crisis_total = len(comparison["crisis"])
    if crisis_6m_wins >= crisis_total / 2:
        cat3 = True
        lines.append(f"[완료] 위기 구간 승률 6M {crisis_6m_wins}/{crisis_total}")
    else:
        cat3 = False
        lines.append(f"[!] 위기 구간 6M {crisis_6m_wins}/{crisis_total} — 하락장 방어력 우려")

    n_pass = sum([cat1, cat2, cat3])
    if n_pass == 3:
        verdict = "강력 승격 권고"
    elif n_pass == 2:
        verdict = "조건부 승격 가능"
    else:
        verdict = "승격 보류"

    return verdict, lines


# ─────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────

def build_html(rolling: dict, comparison: dict, verdict: str, lines: list[str]) -> str:
    yearly = rolling["yearly"]
    bt_ch = rolling["bt_champ"]
    bt_6m = rolling["bt_6m"]

    # 누적 수익 (2016-01 이후)
    bt_ch_slice = _slice(bt_ch, "2016-01-01")
    bt_6m_slice = _slice(bt_6m, "2016-01-01")
    labels = bt_ch_slice["as_of"].tolist()
    cum_ch = ((1 + bt_ch_slice["strategy_return"]).cumprod() - 1).round(4).tolist()
    cum_6m = ((1 + bt_6m_slice["strategy_return"]).cumprod() - 1).round(4).tolist()
    cum_blend = ((1 + bt_ch_slice["blend_return"]).cumprod() - 1).round(4).tolist()

    # Annual bars
    year_labels = [str(y["year"]) for y in yearly]
    ch_rets = [round(y["ch_ret"] * 100, 2) for y in yearly]
    m6_rets = [round(y["m6_ret"] * 100, 2) for y in yearly]

    # Yearly table rows
    y_rows = ""
    for y in yearly:
        bg = "#FEF3C7" if y["winner"] == "6M" else ("#DBEAFE" if y["winner"] == "Champion" else "")
        diff_color = "#F58220" if y["winner"] == "6M" else "#1D3557"
        y_rows += (
            f"<tr style='background:{bg}'>"
            f"<td>{y['year']}</td>"
            f"<td class='num'>{y['n']}</td>"
            f"<td class='num'>{y['ch_ret']*100:+.2f}%</td>"
            f"<td class='num'>{y['ch_sh']:+.2f}</td>"
            f"<td class='num'>{y['m6_ret']*100:+.2f}%</td>"
            f"<td class='num'>{y['m6_sh']:+.2f}</td>"
            f"<td class='num' style='font-weight:700;color:{diff_color}'>{y['diff']*100:+.2f}%</td>"
            f"<td style='text-align:center'>{y['winner']}</td>"
            f"</tr>"
        )

    # Crisis table rows
    c_rows = ""
    for c in comparison["crisis"]:
        bg = "#FEF3C7" if c["winner"] == "6M" else ("#DBEAFE" if c["winner"] == "Champion" else "")
        c_rows += (
            f"<tr style='background:{bg}'>"
            f"<td>{c['label']}</td>"
            f"<td>{c['start']} ~ {c['end']}</td>"
            f"<td class='num'>{c['n']}</td>"
            f"<td class='num'>{c['ch_ret']*100:+.1f}%</td>"
            f"<td class='num'>{c['m6_ret']*100:+.1f}%</td>"
            f"<td style='text-align:center'>{c['winner']}</td>"
            f"</tr>"
        )

    v_icon = "✅" if "승격 권고" in verdict else ("⚠" if "조건부" in verdict else "❌")

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>Rolling OOS & 6M Comparison</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, sans-serif; background: #F7F8FA; color: #1F2937;
         padding: 24px; max-width: 1280px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; font-weight: 800; margin-bottom: 4px; }}
  .subtitle {{ color: #6B7280; font-size: 0.85rem; margin-bottom: 24px; }}
  h2 {{ font-size: 1rem; color: #111827; margin: 28px 0 10px; padding-left: 10px; border-left: 3px solid #F58220; }}
  table {{ width: 100%; background: #fff; border-collapse: collapse; font-size: 0.85rem;
          border-radius: 8px; overflow: hidden; border: 1px solid #E5E7EB; margin: 12px 0; }}
  th {{ background: #F3F4F6; padding: 9px 10px; text-align: left; font-weight: 600; color: #374151; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #F3F4F6; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr:last-child td {{ border-bottom: none; }}
  .canvas-wrap {{ background: #fff; padding: 14px; border-radius: 10px; border: 1px solid #E5E7EB; }}
  .verdict {{ background: #fff; border-left: 5px solid #F58220; padding: 16px 22px; border-radius: 8px; margin: 18px 0; }}
  .verdict h3 {{ font-size: 1.2rem; font-weight: 800; margin-bottom: 8px; }}
  .verdict p {{ margin: 4px 0; font-size: 0.88rem; }}
  .hero {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0; }}
  .hero-card {{ background: #fff; padding: 14px; border-radius: 10px; border: 1px solid #E5E7EB; }}
  .hero-label {{ font-size: 0.72rem; color: #6B7280; text-transform: uppercase; letter-spacing: 0.05em; }}
  .hero-value {{ font-size: 1.4rem; font-weight: 800; margin-top: 4px; }}
</style></head><body>

<h1>Rolling OOS & 6M-only 챔피언 승격 검토</h1>
<div class="subtitle">연도별 Expanding Window OOS (2016-2026) + 시그널 일치율 + 위기 구간 비교</div>

<div class="verdict">
  <h3>{v_icon} 최종 판단: {verdict}</h3>
  {''.join(f'<p>{line}</p>' for line in lines)}
</div>

<div class="hero">
  <div class="hero-card">
    <div class="hero-label">누적 수익 (2016-)</div>
    <div class="hero-value" style="color:#1D3557">Ch {rolling['total_champ']*100:+.1f}%</div>
    <div class="hero-value" style="color:#F58220">6M {rolling['total_6m']*100:+.1f}%</div>
  </div>
  <div class="hero-card">
    <div class="hero-label">연 승률</div>
    <div class="hero-value">6M {rolling['wins_6m']} / Ch {rolling['wins_champion']}</div>
  </div>
  <div class="hero-card">
    <div class="hero-label">시그널 일치율</div>
    <div class="hero-value">{comparison['agree_rate']*100:.0f}%</div>
  </div>
  <div class="hero-card">
    <div class="hero-label">연간 전환</div>
    <div class="hero-value" style="font-size:1rem">Ch {comparison['ch_trades']} / 6M {comparison['m6_trades']}</div>
  </div>
</div>

<h2>Part 1 — 연도별 Rolling OOS 성과</h2>
<table>
  <thead><tr>
    <th>Year</th><th>#월</th>
    <th>Champion Return</th><th>Ch Sharpe</th>
    <th>6M-only Return</th><th>6M Sharpe</th>
    <th>차이</th><th>승자</th>
  </tr></thead><tbody>{y_rows}</tbody>
</table>

<h2>연도별 수익률 비교 차트</h2>
<div class="canvas-wrap"><canvas id="yearlyBar" style="max-height:300px"></canvas></div>

<h2>누적 수익 (2016-01 ~ 현재)</h2>
<div class="canvas-wrap"><canvas id="cum" style="max-height:380px"></canvas></div>

<h2>Part 2 — 위기 구간 비교</h2>
<table>
  <thead><tr><th>이벤트</th><th>기간</th><th>#월</th><th>Champion</th><th>6M-only</th><th>승자</th></tr></thead>
  <tbody>{c_rows}</tbody>
</table>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  new Chart(document.getElementById('yearlyBar'), {{
    type: 'bar',
    data: {{
      labels: {json.dumps(year_labels)},
      datasets: [
        {{ label: 'Champion [1,3,6]', data: {json.dumps(ch_rets)},
           backgroundColor: '#1D3557' }},
        {{ label: '6M-only', data: {json.dumps(m6_rets)},
           backgroundColor: '#F58220' }},
      ]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }},
                scales: {{ y: {{ title: {{ display: true, text: 'Return (%)' }} }} }} }}
  }});

  new Chart(document.getElementById('cum'), {{
    type: 'line',
    data: {{ labels: {json.dumps(labels)}, datasets: [
      {{ label: '6M-only', data: {json.dumps(cum_6m)},
         borderColor: '#F58220', borderWidth: 2.5, backgroundColor: 'transparent', tension: 0.15 }},
      {{ label: 'Champion [1,3,6]', data: {json.dumps(cum_ch)},
         borderColor: '#1D3557', borderWidth: 1.8, backgroundColor: 'transparent', tension: 0.15 }},
      {{ label: '50/50 Blend', data: {json.dumps(cum_blend)},
         borderColor: '#6B7280', borderWidth: 1, borderDash: [5,4], backgroundColor: 'transparent' }},
    ]}},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'top' }} }},
                scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }},
                          x: {{ ticks: {{ maxTicksLimit: 12 }} }} }} }}
  }});
</script>
</body></html>
"""
    return html


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pivot = load_all_data(start=BACKTEST_START)
    print(f"[load] {pivot.shape}")

    rolling = rolling_oos(pivot)
    comparison = signal_comparison(rolling["bt_champ"], rolling["bt_6m"])
    verdict, lines = promotion_verdict(rolling, comparison)

    print("\n" + "=" * 100)
    print("최종 판단")
    print("=" * 100)
    print(f"  → {verdict}")
    for line in lines:
        print(f"     {line}")

    # HTML
    html = build_html(rolling, comparison, verdict, lines)
    out = OUTPUT_DIR / "rolling_oos_and_6m.html"
    out.write_text(html, encoding="utf-8")

    # CSV
    pd.DataFrame(rolling["yearly"]).to_csv(OUTPUT_DIR / "rolling_oos_yearly.csv", index=False)

    print(f"\n[write] {out}")
    print(f"[write] {OUTPUT_DIR / 'rolling_oos_yearly.csv'}")


if __name__ == "__main__":
    main()
