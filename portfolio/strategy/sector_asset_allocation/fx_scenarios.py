"""KR 투자자 관점 FX 시나리오 비교.

챔피언 config (4쌍 + USDKRW 30%) 을 3가지 통화 기준에서 백테스트:
  1. local         : 로컬 통화 (기존 백테스트 — USD 투자자 관점 근사)
  2. krw_unhedged  : KR 투자자 환오픈 — US ETF 환변동 노출
  3. krw_hedged    : KR 투자자 환헤지 — 월별 헤지비용(연 1.8%) 차감

벤치마크도 3가지 기준으로 각각 계산해 apples-to-apples 비교.

Usage:
    python -m portfolio.strategy.sector_asset_allocation.fx_scenarios
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from portfolio.strategy.sector_asset_allocation.core import (
    BACKTEST_START, Config, load_all_data, run_backtest, perf,
    SECTOR_PAIRS_ECO4,
)

OUTPUT_DIR = Path(__file__).parent / "outputs"


def build_champion_cfg(base_currency: str) -> Config:
    return Config(
        name=f"Champion ({base_currency})",
        pairs=SECTOR_PAIRS_ECO4,
        w_rs=0.7, w_fx=0.3, fx_source="usdkrw",
        tau=0.02,
        base_currency=base_currency,
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pivot = load_all_data()
    print(f"[load] {pivot.shape} · {pivot.index.min().date()} ~ {pivot.index.max().date()}")

    # 3 시나리오 백테스트
    scenarios = ["local", "krw_unhedged", "krw_hedged"]
    bts: dict[str, pd.DataFrame] = {}
    for base in scenarios:
        cfg = build_champion_cfg(base)
        bt = run_backtest(cfg, pivot)
        bts[base] = bt
        print(f"[run] {base}: {len(bt)}개월")

    # 성과 산출 (각 기준별 전략 + 벤치마크 3종)
    print("\n" + "=" * 85)
    print(f"{'Base Currency':20s} {'Strategy':>18s} {'50/50':>12s} {'KOSPI':>12s} {'S&P500':>12s}")
    print("=" * 85)
    all_metrics: dict[str, list[dict]] = {}
    for base, bt in bts.items():
        date_idx = pd.to_datetime(bt["as_of"])
        ms = {
            "Strategy":     perf(pd.Series(bt["strategy_return"].values, index=date_idx), "전략"),
            "50/50 Blend":  perf(pd.Series(bt["blend_return"].values,    index=date_idx), "50/50 Blend"),
            "KOSPI":        perf(pd.Series(bt["kr_return"].values,       index=date_idx), "KOSPI"),
            "S&P500":       perf(pd.Series(bt["us_return"].values,       index=date_idx), "S&P500"),
        }
        all_metrics[base] = ms
        s_r  = ms["Strategy"]["ann_return"] * 100
        b_r  = ms["50/50 Blend"]["ann_return"] * 100
        kr_r = ms["KOSPI"]["ann_return"] * 100
        us_r = ms["S&P500"]["ann_return"] * 100
        print(f"{base:20s} {s_r:>17.2f}% {b_r:>11.2f}% {kr_r:>11.2f}% {us_r:>11.2f}%")

    print("\n[MDD & Sharpe]")
    print(f"{'Base':20s} {'Strat Sharpe':>14s} {'Strat MDD':>12s} {'SP500 Sharpe':>14s} {'SP500 MDD':>12s}")
    for base in scenarios:
        ms = all_metrics[base]
        print(f"{base:20s} "
              f"{ms['Strategy']['sharpe']:>13.2f}  "
              f"{ms['Strategy']['mdd']*100:>10.1f}%  "
              f"{ms['S&P500']['sharpe']:>13.2f}  "
              f"{ms['S&P500']['mdd']*100:>10.1f}%")

    # HTML 생성
    css = """
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: -apple-system, 'Pretendard', sans-serif; background: #F7F8FA; color: #1F2937;
             padding: 24px; max-width: 1280px; margin: 0 auto; }
      h1 { font-size: 1.5rem; font-weight: 800; margin-bottom: 4px; }
      .subtitle { color: #6B7280; font-size: 0.85rem; margin-bottom: 24px; }
      h2 { font-size: 1rem; color: #111827; margin: 28px 0 10px; padding-left: 10px; border-left: 3px solid #F58220; }
      h3 { font-size: 0.95rem; color: #374151; margin: 16px 0 8px; }
      table { width: 100%; background: #fff; border-collapse: collapse; font-size: 0.85rem;
              border-radius: 8px; overflow: hidden; border: 1px solid #E5E7EB; margin-bottom: 10px; }
      th { background: #F3F4F6; padding: 9px 10px; text-align: left; font-weight: 600; color: #374151; }
      td { padding: 8px 10px; border-bottom: 1px solid #F3F4F6; }
      td.num { text-align: right; font-variant-numeric: tabular-nums; }
      tr:last-child td { border-bottom: none; }
      .canvas-wrap { background: #fff; padding: 16px; border-radius: 10px; border: 1px solid #E5E7EB; }
      .hero { background: linear-gradient(135deg, #FFF7EE, #FDE68A22); border-radius: 12px;
              padding: 18px 22px; border: 1px solid #FCD34D; margin-bottom: 20px; }
      .note { color: #6B7280; font-size: 0.78rem; margin-top: 8px; line-height: 1.55; }
      .scenario-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 16px 0; }
      .scenario-card { background: #fff; padding: 16px; border-radius: 10px; border: 1px solid #E5E7EB; }
      .scenario-card h3 { border: none; padding: 0; margin-bottom: 8px; font-size: 0.9rem; }
      .scenario-card .big { font-size: 1.3rem; font-weight: 800; color: #F58220; }
      .scenario-card .sub { font-size: 0.75rem; color: #6B7280; }
    """

    # 시나리오 요약 카드
    card_html = ""
    labels_map = {
        "local": ("🌐 Local (USD 기준)", "기존 백테스트 (각 시장 로컬 통화)"),
        "krw_unhedged": ("🇰🇷 KRW 환오픈", "KR 투자자, US ETF 환변동 노출"),
        "krw_hedged": ("🛡 KRW 환헤지 (연 1.8%)", "KR 투자자, 환 리스크 제거 대신 비용"),
    }
    for base in scenarios:
        ms = all_metrics[base]
        title, desc = labels_map[base]
        s = ms["Strategy"]
        card_html += (
            f'<div class="scenario-card">'
            f'<h3>{title}</h3>'
            f'<div class="big">CAGR {s["ann_return"]*100:+.2f}%</div>'
            f'<div class="sub">Sharpe {s["sharpe"]:.2f} · MDD {s["mdd"]*100:.1f}%</div>'
            f'<div class="sub">{desc}</div>'
            f'</div>'
        )

    # 성과 테이블 (각 시나리오 × 전략/벤치)
    metric_rows_html = ""
    for base in scenarios:
        title = labels_map[base][0]
        metric_rows_html += f"<h3>{title}</h3><table>"
        metric_rows_html += (
            "<thead><tr><th>전략/벤치</th><th>Total</th><th>CAGR</th><th>연변동</th>"
            "<th>Sharpe</th><th>MDD</th><th>Win%</th><th>#월</th></tr></thead><tbody>"
        )
        ms = all_metrics[base]
        for name in ["Strategy", "50/50 Blend", "KOSPI", "S&P500"]:
            m = ms[name]
            is_strat = name == "Strategy"
            style = "background:#FFF7EE;font-weight:700;" if is_strat else ""
            metric_rows_html += (
                f'<tr style="{style}">'
                f'<td>{"★ " if is_strat else ""}{name}</td>'
                f'<td class="num">{m["total_return"]*100:+.1f}%</td>'
                f'<td class="num">{m["ann_return"]*100:+.1f}%</td>'
                f'<td class="num">{m["ann_vol"]*100:.1f}%</td>'
                f'<td class="num"><b>{m["sharpe"]:.2f}</b></td>'
                f'<td class="num" style="color:#DC2626">{m["mdd"]*100:.1f}%</td>'
                f'<td class="num">{m["win_rate"]*100:.0f}%</td>'
                f'<td class="num">{m["n_months"]}</td>'
                f'</tr>'
            )
        metric_rows_html += "</tbody></table>"

    # 3 시나리오 전략 누적 비교 차트
    first_bt = bts["local"]
    labels_j = json.dumps(first_bt["as_of"].tolist())

    def _cum(bt, col):
        return ((1 + bt[col]).cumprod() - 1).round(4).tolist()

    palette = {"local": "#1D3557", "krw_unhedged": "#F58220", "krw_hedged": "#059669"}
    datasets_strat = []
    for base in scenarios:
        datasets_strat.append({
            "label": f"전략 ({base})",
            "data": _cum(bts[base], "strategy_return"),
            "borderColor": palette[base],
            "backgroundColor": "transparent",
            "borderWidth": 2,
            "tension": 0.15,
        })
    # 벤치도 3 시나리오 KRW unhedged 기준으로 추가
    bt_kr = bts["krw_unhedged"]
    datasets_strat += [
        {"label": "50/50 Blend (KRW 환오픈)", "data": _cum(bt_kr, "blend_return"),
         "borderColor": "#6B7280", "borderDash": [5, 4], "borderWidth": 1.2, "backgroundColor": "transparent"},
        {"label": "S&P500 (USD)", "data": _cum(bts["local"], "us_return"),
         "borderColor": "#94A3B8", "borderDash": [3, 3], "borderWidth": 1.0, "backgroundColor": "transparent"},
        {"label": "S&P500 (KRW 환오픈)", "data": _cum(bt_kr, "us_return"),
         "borderColor": "#F97316", "borderDash": [3, 3], "borderWidth": 1.0, "backgroundColor": "transparent"},
        {"label": "KOSPI", "data": _cum(bt_kr, "kr_return"),
         "borderColor": "#E63946", "borderDash": [3, 3], "borderWidth": 1.0, "backgroundColor": "transparent"},
    ]

    # 통화 기준 간 CAGR 차이 테이블
    diff_rows = ""
    base_local = all_metrics["local"]["Strategy"]["ann_return"]
    for base in scenarios:
        s = all_metrics[base]["Strategy"]
        diff = (s["ann_return"] - base_local) * 100
        arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "─")
        color = "#16A34A" if diff > 0 else ("#DC2626" if diff < 0 else "#6B7280")
        diff_rows += (
            f'<tr><td>{labels_map[base][0]}</td>'
            f'<td class="num">{s["ann_return"]*100:+.2f}%</td>'
            f'<td class="num" style="color:{color}">{arrow} {diff:+.2f}%p</td>'
            f'<td class="num">{s["sharpe"]:.2f}</td>'
            f'<td class="num" style="color:#DC2626">{s["mdd"]*100:.1f}%</td>'
            f'</tr>'
        )

    body = f"""
<h1>FX 시나리오 비교 — KR 투자자 관점</h1>
<div class="subtitle">챔피언 (4쌍 IT+FIN+ENERGY+STAPLES + USDKRW 30%) 을 3 통화 기준에서 재백테스트<br>
기간: {BACKTEST_START} ~ {first_bt['as_of'].iloc[-1]} · {len(first_bt)}개월</div>

<div class="hero">
  💡 <b>핵심</b>: KR 투자자가 실제 실행 시 "local 수익률" 은 USD 계좌 전용이고, KRW 계좌에서는 환오픈/헤지 선택에 따라 실질 수익이 달라집니다.
</div>

<h2>시나리오 3종</h2>
<div class="scenario-grid">{card_html}</div>

<h2>전략 누적 수익 (시나리오별)</h2>
<div class="canvas-wrap"><canvas id="cum" style="max-height:420px"></canvas></div>

<h2>통화 기준별 전략 성과 (vs local 기준 차이)</h2>
<table>
  <thead><tr><th>통화 기준</th><th>전략 CAGR</th><th>vs local 차이</th><th>Sharpe</th><th>MDD</th></tr></thead>
  <tbody>{diff_rows}</tbody>
</table>

<h2>각 시나리오 상세 (전략 + 벤치마크)</h2>
{metric_rows_html}

<div class="note">
<b>가정</b>: 환헤지비용 연 1.8% (= 월 15bp, US-KR 금리차 장기 평균 근사) · 환오픈 FX 수익 = (USDKRW 월변화율) ·
슬리피지·체결 지연 미반영.<br>
<b>해석 포인트</b>:<br>
• local vs krw_unhedged 차이 = USDKRW 추세 구간별 왜곡 크기<br>
• krw_hedged 는 로컬 기준 - 1.8% 연 (헤지 비용) 근사<br>
• 전략 시그널은 모두 동일 (섹터 RS + USDKRW 30%) — 실행 방식만 다름
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  new Chart(document.getElementById('cum'), {{
    type: 'line',
    data: {{ labels: {labels_j}, datasets: {json.dumps(datasets_strat)} }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position: 'top', labels: {{ usePointStyle:true, pointStyle:'line', font:{{size:10}} }} }} }},
      scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }}, x: {{ ticks: {{ maxTicksLimit:12 }} }} }}
    }}
  }});
</script>
"""

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>FX Scenarios — Champion</title>
<style>{css}</style></head><body>{body}</body></html>"""
    out = OUTPUT_DIR / "phase5_fx_scenarios.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n[write] {out}")

    # 시그널 CSV 3종
    for base in scenarios:
        csv_path = OUTPUT_DIR / f"fx_{base}_signals.csv"
        bts[base].to_csv(csv_path, index=False)
    print(f"[write] fx_*_signals.csv (3 files)")


if __name__ == "__main__":
    main()
