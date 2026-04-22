"""
KR vs US GICS 섹터 동조화 시각화
- 11개 섹터 쌍 누적수익률 + 롤링 상관관계
- 출력: output/sector_sync.html
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path

# ── GICS 매핑 (US SPDR ↔ KR KOSPI200) ──────────────────────────────────────
SECTOR_MAP = [
    ("IT / Technology",     "SC_US_TECH",    "IX_KR_IT"),
    ("커뮤니케이션",           "SC_US_COMM",    "IX_KR_COMM"),
    ("경기소비재",             "SC_US_DISCR",   "IX_KR_DISCR"),
    ("필수소비재",             "SC_US_STAPLES", "IX_KR_STAPLES"),
    ("헬스케어",              "SC_US_HEALTH",  "IX_KR_HEALTH"),
    ("금융",                 "SC_US_FIN",     "IX_KR_FIN"),
    ("산업재",               "SC_US_INDU",    "IX_KR_INDU"),
    ("에너지",               "SC_US_ENERGY",  "IX_KR_ENERGY"),
    ("소재 / 철강",           "SC_US_MATL",    "IX_KR_STEEL"),
    ("건설 / 중공업 (Util↔)",  "SC_US_UTIL",    "IX_KR_HEAVY"),  # 가장 근접 매핑
    ("금융 / 건설 (REIT↔)",   "SC_US_REIT",    "IX_KR_CONSTR"), # REIT 없는 KR → 건설
]

SECTOR_COLORS = [
    "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f",
    "#edc948","#b07aa1","#ff9da7","#9c755f","#bab0ac","#a0cbe8",
]

def load_sector_prices(csv_path: str, start: str = "2020-01-01") -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["DATE"])
    codes = [c for _, us, kr in SECTOR_MAP for c in [us, kr]]
    df = df[df["INDICATOR_CODE"].isin(codes) & (df["DATE"] >= start)].copy()
    pivot = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE", aggfunc="last")
    pivot = pivot.sort_index().ffill()
    return pivot

def cumulative_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return (prices / prices.iloc[0] - 1) * 100

def rolling_corr(s1: pd.Series, s2: pd.Series, window: int = 60) -> pd.Series:
    r1 = s1.pct_change()
    r2 = s2.pct_change()
    return r1.rolling(window).corr(r2)

def build_chart_data(prices: pd.DataFrame) -> dict:
    cum = cumulative_returns(prices)
    dates = [d.strftime("%Y-%m-%d") for d in prices.index]
    sectors = []
    for i, (name, us_code, kr_code) in enumerate(SECTOR_MAP):
        if us_code not in prices.columns or kr_code not in prices.columns:
            continue
        us_cum = cum[us_code].round(2).tolist()
        kr_cum = cum[kr_code].round(2).tolist()
        corr60  = rolling_corr(prices[us_code], prices[kr_code], 60).round(3).tolist()
        corr120 = rolling_corr(prices[us_code], prices[kr_code], 120).round(3).tolist()
        # latest corr
        latest_corr60  = next((v for v in reversed(corr60)  if v == v), None)
        latest_corr120 = next((v for v in reversed(corr120) if v == v), None)
        sectors.append({
            "name": name, "us_code": us_code, "kr_code": kr_code,
            "color": SECTOR_COLORS[i],
            "us_cum": us_cum, "kr_cum": kr_cum,
            "corr60": corr60, "corr120": corr120,
            "latest_corr60":  round(latest_corr60,  3) if latest_corr60  is not None else None,
            "latest_corr120": round(latest_corr120, 3) if latest_corr120 is not None else None,
        })
    return {"dates": dates, "sectors": sectors}

def render_html(data: dict, out_path: str):
    json_str = json.dumps(data, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>KR vs US 섹터 동조화 분석</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Pretendard', -apple-system, sans-serif; background: #0f1117; color: #e2e8f0; }}
  h1 {{ text-align: center; padding: 24px 0 4px; font-size: 22px; color: #f8fafc; }}
  .subtitle {{ text-align: center; color: #94a3b8; font-size: 13px; margin-bottom: 20px; }}

  /* Summary table */
  .summary-wrap {{ max-width: 900px; margin: 0 auto 32px; padding: 0 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #1e2535; color: #94a3b8; padding: 8px 12px; text-align: center; border-bottom: 1px solid #2d3748; }}
  td {{ padding: 7px 12px; text-align: center; border-bottom: 1px solid #1e2535; }}
  tr:hover td {{ background: #1a2236; }}
  .corr-high {{ color: #34d399; font-weight: 600; }}
  .corr-mid  {{ color: #fbbf24; }}
  .corr-low  {{ color: #f87171; }}

  /* Grid */
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(560px, 1fr)); gap: 24px; padding: 0 20px 40px; max-width: 1320px; margin: 0 auto; }}
  .card {{ background: #1a2236; border-radius: 12px; padding: 20px; border: 1px solid #2d3748; }}
  .card-title {{ font-size: 14px; font-weight: 600; margin-bottom: 4px; color: #f1f5f9; }}
  .card-meta  {{ font-size: 11px; color: #64748b; margin-bottom: 14px; }}
  .tab-bar {{ display: flex; gap: 8px; margin-bottom: 12px; }}
  .tab {{ padding: 4px 12px; border-radius: 20px; font-size: 12px; cursor: pointer; border: 1px solid #2d3748; color: #94a3b8; background: transparent; transition: all .15s; }}
  .tab.active {{ background: #334155; color: #f1f5f9; border-color: #475569; }}
  canvas {{ max-height: 200px; }}
  .corr-badge {{ display: inline-block; margin-top: 8px; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }}
</style>
</head>
<body>
<h1>KR vs US 섹터 동조화 분석</h1>
<p class="subtitle">US: SPDR Sector ETF &nbsp;|&nbsp; KR: KOSPI200 섹터지수 &nbsp;|&nbsp; 기준: 2020-01-01</p>

<div class="summary-wrap">
  <table id="summary-table">
    <thead><tr>
      <th>섹터</th><th>US 코드</th><th>KR 코드</th>
      <th>상관관계 60일</th><th>상관관계 120일</th>
      <th>US 누적수익률</th><th>KR 누적수익률</th>
    </tr></thead>
    <tbody id="summary-body"></tbody>
  </table>
</div>

<div class="grid" id="grid"></div>

<script>
const DATA = {json_str};

function corrClass(v) {{
  if (v === null) return '';
  if (v >= 0.6) return 'corr-high';
  if (v >= 0.3) return 'corr-mid';
  return 'corr-low';
}}
function corrColor(v) {{
  if (v === null) return '#64748b';
  if (v >= 0.6) return '#34d399';
  if (v >= 0.3) return '#fbbf24';
  return '#f87171';
}}

// ── Summary table ─────────────────────────────────────────────────────────
const tbody = document.getElementById('summary-body');
DATA.sectors.forEach(s => {{
  const usLast = s.us_cum[s.us_cum.length-1];
  const krLast = s.kr_cum[s.kr_cum.length-1];
  const c60  = s.latest_corr60;
  const c120 = s.latest_corr120;
  tbody.innerHTML += `<tr>
    <td style="text-align:left;font-weight:600;color:${{s.color}}">${{s.name}}</td>
    <td style="color:#94a3b8;font-size:11px">${{s.us_code}}</td>
    <td style="color:#94a3b8;font-size:11px">${{s.kr_code}}</td>
    <td class="${{corrClass(c60)}}">${{c60 !== null ? c60.toFixed(3) : '-'}}</td>
    <td class="${{corrClass(c120)}}">${{c120 !== null ? c120.toFixed(3) : '-'}}</td>
    <td style="color:${{usLast>=0?'#34d399':'#f87171'}}">${{usLast>=0?'+':''}}${{usLast?.toFixed(1)}}%</td>
    <td style="color:${{krLast>=0?'#34d399':'#f87171'}}">${{krLast>=0?'+':''}}${{krLast?.toFixed(1)}}%</td>
  </tr>`;
}});

// ── Cards ─────────────────────────────────────────────────────────────────
const grid = document.getElementById('grid');
DATA.sectors.forEach((s, idx) => {{
  const id = `card-${{idx}}`;
  const c60  = s.latest_corr60;
  const c120 = s.latest_corr120;
  const badgeText  = c60 !== null ? `60일 상관 ${{c60.toFixed(3)}}` : '-';
  const badgeColor = corrColor(c60);

  const div = document.createElement('div');
  div.className = 'card';
  div.innerHTML = `
    <div class="card-title">${{s.name}}</div>
    <div class="card-meta">${{s.us_code}} (SPDR) &nbsp;vs&nbsp; ${{s.kr_code}} (KOSPI200)</div>
    <div class="tab-bar">
      <button class="tab active" onclick="showChart(${{idx}},'cum')">누적수익률</button>
      <button class="tab" onclick="showChart(${{idx}},'corr')">롤링 상관관계</button>
    </div>
    <canvas id="canvas-${{idx}}"></canvas>
    <span class="corr-badge" style="background:${{badgeColor}}22;color:${{badgeColor}};border:1px solid ${{badgeColor}}44">
      ${{badgeText}}
    </span>
    &nbsp;
    <span class="corr-badge" style="background:#33415522;color:#94a3b8;border:1px solid #47556944">
      120일 ${{c120 !== null ? c120.toFixed(3) : '-'}}
    </span>
  `;
  grid.appendChild(div);

  // initial chart: cum
  renderCum(idx, s);
}});

const chartInstances = {{}};

function renderCum(idx, s) {{
  const ctx = document.getElementById(`canvas-${{idx}}`).getContext('2d');
  if (chartInstances[idx]) chartInstances[idx].destroy();
  chartInstances[idx] = new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: DATA.dates,
      datasets: [
        {{ label: 'US', data: s.us_cum, borderColor: '#60a5fa', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false }},
        {{ label: 'KR', data: s.kr_cum, borderColor: s.color,   borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false }},
      ]
    }},
    options: {{
      responsive: true, animation: false,
      plugins: {{ legend: {{ labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 8, font: {{ size: 10 }} }}, grid: {{ color: '#1e2535' }} }},
        y: {{ ticks: {{ color: '#64748b', font: {{ size: 10 }}, callback: v => v+'%' }}, grid: {{ color: '#1e2535' }} }},
      }}
    }}
  }});
}}

function renderCorr(idx, s) {{
  const ctx = document.getElementById(`canvas-${{idx}}`).getContext('2d');
  if (chartInstances[idx]) chartInstances[idx].destroy();
  chartInstances[idx] = new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: DATA.dates,
      datasets: [
        {{ label: '60일 상관', data: s.corr60,  borderColor: '#fbbf24', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false }},
        {{ label: '120일 상관', data: s.corr120, borderColor: '#818cf8', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, borderDash: [4,3] }},
      ]
    }},
    options: {{
      responsive: true, animation: false,
      plugins: {{
        legend: {{ labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }},
        annotation: {{ annotations: {{
          zero: {{ type:'line', yMin:0, yMax:0, borderColor:'#475569', borderWidth:1, borderDash:[4,4] }}
        }} }}
      }},
      scales: {{
        x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 8, font: {{ size: 10 }} }}, grid: {{ color: '#1e2535' }} }},
        y: {{ min: -1, max: 1, ticks: {{ color: '#64748b', font: {{ size: 10 }} }}, grid: {{ color: '#1e2535' }} }},
      }}
    }}
  }});
}}

function showChart(idx, type) {{
  const card = document.getElementById(`card-${{idx}}`);
  const s = DATA.sectors[idx];
  // update tab style
  const tabs = document.querySelectorAll(`#grid .card`)[idx].querySelectorAll('.tab');
  tabs.forEach(t => t.classList.remove('active'));
  tabs[type === 'cum' ? 0 : 1].classList.add('active');
  if (type === 'cum') renderCum(idx, s);
  else renderCorr(idx, s);
}}
</script>
</body>
</html>"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--out",   default="output/sector_sync.html")
    args = ap.parse_args()

    prices = load_sector_prices("history/market_data.csv", start=args.start)
    print(f"Loaded {len(prices)} trading days × {len(prices.columns)} series")
    data   = build_chart_data(prices)
    render_html(data, args.out)
