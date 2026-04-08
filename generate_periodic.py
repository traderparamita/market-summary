#!/usr/local/bin/python3.12
"""
Weekly & Monthly Market Summary Report Generator
- 일간 _data.json을 집계하여 주간/월간 HTML 보고서 생성
"""

import json
import os
import glob
import datetime as dt
from generate import generate_index, fmt, chg_class, chg_sign, heat_color, heat_text, spark_svg

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def load_daily_data(month_pattern=None):
    """일간 JSON 데이터를 모두 로드. {date_str: data_dict}"""
    pattern = os.path.join(OUTPUT_DIR, "????-??", "????-??-??_data.json")
    all_data = {}
    for f in sorted(glob.glob(pattern)):
        date_str = os.path.basename(f).replace("_data.json", "")
        if month_pattern and not date_str.startswith(month_pattern):
            continue
        with open(f) as fp:
            all_data[date_str] = json.load(fp)
    return all_data


def get_week_ranges(year=2026):
    """ISO 주차 기반으로 주간 범위 반환. {(year, week): [date_str, ...]}"""
    weeks = {}
    d = dt.date(year, 1, 1)
    while d.year == year:
        if d.weekday() < 5:  # 평일만
            iso = d.isocalendar()
            key = (iso[0], iso[1])
            if key not in weeks:
                weeks[key] = []
            weeks[key].append(str(d))
        d += dt.timedelta(days=1)
    return weeks


def aggregate_period(daily_data, date_list):
    """여러 일간 데이터를 집계하여 기간 요약 생성"""
    # 해당 기간에 데이터가 있는 날짜만 필터
    available = [d for d in date_list if d in daily_data]
    if not available:
        return None

    first_date = available[0]
    last_date = available[-1]
    first_data = daily_data[first_date]
    last_data = daily_data[last_date]

    result = {"dates": available, "first": first_date, "last": last_date}

    # 각 카테고리별 집계
    for cat in ["equity", "bond", "fx", "commodity", "risk", "stocks"]:
        result[cat] = {}
        last_cat = last_data.get(cat, {})
        first_cat = first_data.get(cat, {})

        for name, last_item in last_cat.items():
            first_item = first_cat.get(name, {})
            first_close = first_item.get("close")
            last_close = last_item.get("close")

            if first_close and last_close and first_close != 0:
                period_chg = (last_close - first_close) / first_close * 100
            else:
                period_chg = 0

            # 기간 중 일별 변동 수집 (스파크라인용)
            daily_closes = []
            for d in available:
                d_data = daily_data.get(d, {}).get(cat, {}).get(name, {})
                if d_data.get("close"):
                    daily_closes.append(d_data["close"])

            spark = []
            if daily_closes and daily_closes[0] != 0:
                spark = [round((c / daily_closes[0] - 1) * 100, 2) for c in daily_closes]

            # 일별 변동 최대/최소
            daily_chgs = []
            for d in available:
                d_item = daily_data.get(d, {}).get(cat, {}).get(name, {})
                if "daily" in d_item:
                    daily_chgs.append(d_item["daily"])

            best_day = max(daily_chgs) if daily_chgs else 0
            worst_day = min(daily_chgs) if daily_chgs else 0

            result[cat][name] = {
                "close": last_close or 0,
                "open": first_close or 0,
                "period_chg": round(period_chg, 2),
                "best_day": round(best_day, 2),
                "worst_day": round(worst_day, 2),
                "spark": spark,
                "date": last_item.get("date", last_date),
                "ytd": last_item.get("ytd", 0),
            }

    return result


def generate_periodic_html(agg, title, subtitle, period_label, filename):
    """집계 데이터로 주간/월간 HTML 생성"""

    eq = agg.get("equity", {})
    bd = agg.get("bond", {})
    fx = agg.get("fx", {})
    cm = agg.get("commodity", {})
    rk = agg.get("risk", {})
    st = agg.get("stocks", {})

    # KPI 목록
    kpi_items = []
    for label, cat, key in [
        ("KOSPI", eq, "KOSPI"), ("S&P500", eq, "S&P500"), ("NASDAQ", eq, "NASDAQ"),
        ("WTI", cm, "WTI"), ("Gold", cm, "Gold"), ("VIX", rk, "VIX"),
    ]:
        if key in cat:
            d = cat[key]
            if label in ["WTI", "Gold"]:
                v = f"${fmt(d['close'])}"
            elif label == "VIX":
                v = f"{d['close']:.1f}"
            else:
                v = fmt(d["close"], 0)
            kpi_items.append({"label": label, "value": v, "chg": d["period_chg"]})

    # 히트맵 행 생성
    def heatmap_row(name, d, show_dollar=False):
        close = d["close"]
        if show_dollar:
            close_str = f"${fmt(close)}" if close < 10000 else f"${close:,.0f}"
        else:
            close_str = fmt(close, 0) if close > 100 else fmt(close, 2)

        spark = spark_svg(d.get("spark", []))
        chg = d["period_chg"]
        bg = heat_color(chg)
        tc = heat_text(chg)
        best = d["best_day"]
        worst = d["worst_day"]
        ytd = d.get("ytd", 0)

        return f"""<tr>
          <td class="name-cell">{name}</td>
          <td class="close-cell">{close_str}</td>
          <td class="spark-cell">{spark}</td>
          <td class="heat-cell" style="background:{heat_color(chg)};color:{heat_text(chg)}">{chg_sign(chg)}</td>
          <td class="heat-cell" style="background:{heat_color(best)};color:{heat_text(best)}">{chg_sign(best)}</td>
          <td class="heat-cell" style="background:{heat_color(worst)};color:{heat_text(worst)}">{chg_sign(worst)}</td>
          <td class="heat-cell" style="background:{heat_color(ytd)};color:{heat_text(ytd)}">{chg_sign(ytd)}</td>
        </tr>"""

    # 정렬 순서
    EQUITY_ORDER = ["KOSPI","KOSDAQ","S&P500","NASDAQ","Russell2K","STOXX50","FTSE100","DAX","CAC40","Shanghai","HSI","Nikkei225","NIFTY50"]
    BOND_ORDER = ["KR CD 91D","KR 3Y","KR 5Y","KR 10Y","KR 30Y","US 2Y","US 10Y","US 30Y"]
    FX_ORDER = ["DXY","USD/KRW","EUR/USD","GBP/USD","AUD/USD","USD/JPY","USD/CNY"]
    CM_ORDER = ["WTI","Brent","Gold","Silver","Copper","Nat Gas"]
    ST_ORDER = ["NVIDIA","Broadcom","Alphabet","Amazon","META","Apple","Microsoft","Tesla","TSMC","Samsung"]

    def ordered(cat, order):
        idx = {n: i for i, n in enumerate(order)}
        return sorted(cat.items(), key=lambda x: idx.get(x[0], 999))

    bond_etfs = {"TLT", "HYG", "LQD", "EMB"}
    bd_rates = {k: v for k, v in bd.items() if k not in bond_etfs}
    bd_etf = {k: v for k, v in bd.items() if k in bond_etfs}

    # 상위/하위 종목
    all_items = [(n, d) for c in [eq, st, cm] for n, d in c.items()]
    sorted_items = sorted(all_items, key=lambda x: x[1]["period_chg"], reverse=True)
    top3 = sorted_items[:3]
    bottom3 = sorted_items[-3:]

    # Chart 데이터
    eq_sorted = sorted(eq.items(), key=lambda x: x[1]["period_chg"], reverse=True)
    eq_names = [n for n, _ in eq_sorted]
    eq_chgs = [d["period_chg"] for _, d in eq_sorted]
    st_sorted = sorted(st.items(), key=lambda x: x[1]["period_chg"], reverse=True)
    st_names = [n for n, _ in st_sorted]
    st_chgs = [d["period_chg"] for _, d in st_sorted]

    # VIX
    vix = rk.get("VIX", {})
    vix_val = vix.get("close", 0)
    if vix_val >= 30: vix_label, vix_color = "Extreme Fear", "#d9304f"
    elif vix_val >= 20: vix_label, vix_color = "Elevated", "#d48b07"
    elif vix_val >= 15: vix_label, vix_color = "Normal", "#7c8298"
    else: vix_label, vix_color = "Complacent", "#0d9b6a"

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9;--card:#fff;--card2:#f0f1f6;--border:#e0e3ed;--text:#2d3148;--muted:#7c8298;
  --accent:#3b6ee6;--accent2:#6b5ce7;--up:#0d9b6a;--down:#d9304f;--warn:#d48b07;--gold:#b8860b;--oil:#d35400;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans KR',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.65;padding:24px;max-width:1360px;margin:0 auto}}
.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px;padding-bottom:20px;border-bottom:2px solid var(--border)}}
.header-left h1{{font-size:26px;font-weight:700;color:#1a1d2e;margin-bottom:2px}}
.header-left .date{{font-size:13px;color:var(--muted);letter-spacing:1px}}
.header-right{{display:flex;gap:20px;align-items:center}}
.mood-badge{{display:flex;align-items:center;gap:8px;padding:8px 18px;border-radius:24px;font-size:13px;font-weight:600}}
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:28px}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);text-align:center}}
.kpi-label{{font-size:11px;color:var(--muted);font-weight:500;margin-bottom:1px}}
.kpi-value{{font-size:18px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}
.kpi-chg{{font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.up{{color:var(--up)}}.down{{color:var(--down)}}.flat{{color:var(--muted)}}
.movers-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
.movers-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 20px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.movers-card h3{{font-size:13px;color:var(--muted);font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px}}
.mover-item{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #f0f1f5}}
.mover-item:last-child{{border:none}}
.mover-name{{font-size:13px;font-weight:500}}
.mover-val{{font-size:15px;font-weight:700;font-family:'JetBrains Mono',monospace}}
.heatmap-section{{margin-bottom:28px}}
.heatmap-section h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.heatmap{{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.heatmap th{{font-size:11px;font-weight:600;color:var(--muted);padding:10px 12px;text-align:right;background:var(--card2);border-bottom:1px solid var(--border);white-space:nowrap}}
.heatmap th:first-child,.heatmap th:nth-child(2),.heatmap th:nth-child(3){{text-align:left}}
.heatmap td{{padding:8px 12px;font-size:13px;border-bottom:1px solid #f3f4f8}}
.heatmap tr:last-child td{{border-bottom:none}}
.name-cell{{font-weight:600;color:#1a1d2e;white-space:nowrap;min-width:100px}}
.close-cell{{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text);text-align:left;white-space:nowrap}}
.spark-cell{{text-align:center;padding:4px 8px}}
.heat-cell{{text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600}}
.heatmap tr:hover{{filter:brightness(0.97)}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
.chart-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.chart-card .title{{font-size:13px;color:var(--muted);font-weight:600;margin-bottom:12px}}
.chart-box{{position:relative;height:280px}}
.footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:40px;padding-top:20px;border-top:1px solid var(--border)}}
.back-link{{display:inline-block;margin-bottom:20px;color:var(--accent);text-decoration:none;font-size:13px;font-weight:500}}
.back-link:hover{{text-decoration:underline}}
.tab-bar{{display:flex;gap:0;margin-bottom:28px;border-bottom:2px solid var(--border)}}
.tab-btn{{padding:12px 28px;font-size:14px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s;font-family:inherit}}
.tab-btn:hover{{color:var(--text)}}
.tab-btn.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.tab-panel{{display:none}}.tab-panel.active{{display:block}}

/* ── Story Tab ── */
.story-hero{{background:linear-gradient(135deg,#eef1f8,#e8e5f3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:32px}}
.story-hero h2{{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}}
.story-text{{font-size:16px;color:#2d3148;line-height:1.9}}
.story-text strong{{color:#1a1d2e}}.story-text .hl-up{{color:var(--up);font-weight:600}}.story-text .hl-down{{color:var(--down);font-weight:600}}.story-text .hl-warn{{color:var(--warn);font-weight:600}}.story-text .hl-accent{{color:var(--accent);font-weight:600}}

.causal-chain{{display:flex;align-items:stretch;gap:0;margin-bottom:28px;overflow-x:auto;padding-bottom:8px}}
.cause-node{{flex:1;min-width:160px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 14px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.cause-node .node-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
.cause-node .node-title{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:4px}}
.cause-node .node-detail{{font-size:12px;color:var(--text)}}
.cause-node .node-impact{{margin-top:8px;font-size:17px;font-weight:700}}
.cause-arrow{{display:flex;align-items:center;padding:0 4px;color:var(--muted);font-size:18px;flex-shrink:0}}

.session-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:32px}}
.session-block{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.session-block::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px}}
.session-block.asia::before{{background:linear-gradient(90deg,#d48b07,#e06818)}}
.session-block.europe::before{{background:linear-gradient(90deg,#3b6ee6,#6b5ce7)}}
.session-block.us::before{{background:linear-gradient(90deg,#6b5ce7,#a78bfa)}}
.session-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.session-icon{{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px}}
.session-icon.asia{{background:rgba(212,139,7,0.1)}}.session-icon.europe{{background:rgba(59,110,230,0.1)}}.session-icon.us{{background:rgba(107,92,231,0.1)}}
.session-name{{font-size:15px;font-weight:600;color:#1a1d2e}}
.session-time{{font-size:11px;color:var(--muted)}}
.session-verdict{{display:inline-block;padding:3px 10px;border-radius:16px;font-size:11px;font-weight:600;margin-bottom:10px}}
.verdict-up{{background:rgba(13,155,106,0.1);color:var(--up)}}.verdict-down{{background:rgba(217,48,79,0.1);color:var(--down)}}.verdict-mixed{{background:rgba(212,139,7,0.1);color:var(--warn)}}
.session-events{{list-style:none}}.session-events li{{font-size:12px;padding:6px 0 6px 12px;border-bottom:1px solid #f3f4f8;position:relative}}
.session-events li:last-child{{border:none}}.session-events li::before{{content:'';position:absolute;left:0;top:12px;width:4px;height:4px;border-radius:50%;background:var(--muted)}}
.session-events .ev-time{{color:var(--muted);font-size:10px;font-weight:600}}
.session-kpi{{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px;padding-top:10px;border-top:1px solid var(--border)}}
.s-kpi{{text-align:center;padding:6px;border-radius:6px;background:var(--card2)}}
.s-kpi-label{{font-size:10px;color:var(--muted)}}.s-kpi-value{{font-size:15px;font-weight:700}}

.insight-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:32px}}
.insight-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:22px;position:relative;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.insight-card .badge{{position:absolute;top:14px;right:14px;padding:2px 10px;border-radius:16px;font-size:11px;font-weight:600}}
.insight-card h3{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:10px;padding-right:50px}}
.insight-card p{{font-size:13px;color:var(--text);line-height:1.8}}
.insight-card .metric-row{{display:flex;gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}}
.metric-item{{flex:1;text-align:center}}.metric-label{{font-size:10px;color:var(--muted)}}.metric-value{{font-size:16px;font-weight:700;font-family:'JetBrains Mono',monospace}}

.cross-asset{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:28px;margin-bottom:28px;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.cross-asset h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:6px}}
.cross-asset .sub{{font-size:12px;color:var(--muted);margin-bottom:18px}}
.af-map{{display:grid;grid-template-columns:auto 1fr auto 1fr auto;align-items:center;gap:10px 6px}}
.af-node{{background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:12px 14px;text-align:center;min-width:120px}}
.af-node-title{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}}
.af-node-value{{font-size:18px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}
.af-node-chg{{font-size:12px;font-weight:600}}
.af-arrow{{text-align:center;color:var(--muted);font-size:12px;line-height:1.3}}
.af-arrow .arr{{font-size:16px;display:block}}.af-arrow .lbl{{font-size:10px}}

.risk-section{{background:linear-gradient(135deg,#fdf2f4,#f8f5ff);border:1px solid rgba(217,48,79,0.12);border-radius:12px;padding:28px;margin-bottom:28px}}
.risk-section h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:16px}}
.risk-items{{list-style:none;display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.risk-item{{display:flex;align-items:flex-start;gap:8px;padding:10px 14px;border-radius:8px;background:rgba(255,255,255,0.6);font-size:12px;line-height:1.6}}
.risk-tag{{flex-shrink:0;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;margin-top:1px}}
.risk-tag.high{{background:rgba(217,48,79,0.15);color:var(--down)}}.risk-tag.med{{background:rgba(212,139,7,0.15);color:var(--warn)}}

@media(max-width:900px){{
  .chart-grid,.movers-row{{grid-template-columns:1fr}}
  .kpi-strip{{grid-template-columns:repeat(3,1fr)}}
  .session-grid,.insight-grid{{grid-template-columns:1fr}}
  .causal-chain{{flex-direction:column}}.cause-arrow{{transform:rotate(90deg);padding:4px 0}}
  .af-map{{grid-template-columns:1fr}}.risk-items{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
<a href="../index.html" class="back-link">&larr; Back to Index</a>
<div class="header">
  <div class="header-left">
    <h1>{title}</h1>
    <div class="date">{subtitle}</div>
  </div>
  <div class="header-right">
    <div class="mood-badge" style="background:{'#fef2f2' if vix_val>=20 else '#f0fdf4'};color:{vix_color};border:1px solid {vix_color}33">
      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{vix_color}"></span>
      VIX {vix_val:.1f} &mdash; {vix_label}
    </div>
  </div>
</div>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('data')">Data Dashboard</button>
  <button class="tab-btn" onclick="switchTab('story')">{period_label} Story</button>
</div>

<div id="tab-data" class="tab-panel active">
<div class="kpi-strip">
"""
    for k in kpi_items:
        cls = chg_class(k["chg"])
        html += f"""  <div class="kpi">
    <div class="kpi-label">{k['label']}</div>
    <div class="kpi-value">{k['value']}</div>
    <div class="kpi-chg {cls}">{chg_sign(k['chg'])}</div>
  </div>\n"""
    html += "</div>\n"

    # Top/Bottom
    html += '<div class="movers-row">\n<div class="movers-card"><h3>Top Gainers ({0})</h3>\n'.format(period_label)
    for name, d in top3:
        cls = chg_class(d["period_chg"])
        html += f'<div class="mover-item"><span class="mover-name">{name}</span><span class="mover-val {cls}">{chg_sign(d["period_chg"])}</span></div>\n'
    html += '</div>\n<div class="movers-card"><h3>Top Losers ({0})</h3>\n'.format(period_label)
    for name, d in bottom3:
        cls = chg_class(d["period_chg"])
        html += f'<div class="mover-item"><span class="mover-name">{name}</span><span class="mover-val {cls}">{chg_sign(d["period_chg"])}</span></div>\n'
    html += '</div>\n</div>\n'

    # 히트맵 테이블
    sections = [
        ("Equity", eq, False, EQUITY_ORDER),
        ("Bonds & Rates", bd_rates, False, BOND_ORDER),
        ("Bond ETF", bd_etf, True, ["TLT","LQD","HYG","EMB"]),
        ("FX", fx, False, FX_ORDER),
        ("Commodities", cm, True, CM_ORDER),
        ("Major Stocks", st, True, ST_ORDER),
    ]
    for sec_title, cat, dollar, order in sections:
        if not cat:
            continue
        idx = {n: i for i, n in enumerate(order)}
        items = sorted(cat.items(), key=lambda x: idx.get(x[0], 999))
        html += f"""<div class="heatmap-section">
<h2>{sec_title}</h2>
<table class="heatmap">
<thead><tr><th>Name</th><th>Close</th><th>Trend</th><th>{period_label}</th><th>Best Day</th><th>Worst Day</th><th>YTD</th></tr></thead>
<tbody>\n"""
        for name, d in items:
            html += heatmap_row(name, d, dollar)
        html += "</tbody></table></div>\n"

    # Charts
    html += f"""
<div class="chart-grid">
  <div class="chart-card">
    <div class="title">Equity {period_label} Change (%)</div>
    <div class="chart-box"><canvas id="eqChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="title">Stocks {period_label} Change (%)</div>
    <div class="chart-box"><canvas id="stChart"></canvas></div>
  </div>
</div>


</div><!-- /tab-data -->

<div id="tab-story" class="tab-panel">
<!-- STORY_CONTENT_PLACEHOLDER -->
</div><!-- /tab-story -->

<div class="footer">{title} | Auto-generated</div>

<script>
function switchTab(id){{
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  event.target.classList.add('active');
  if(id==='data') setTimeout(()=>window.dispatchEvent(new Event('resize')),50);
}}
Chart.defaults.color='#7c8298';Chart.defaults.borderColor='#e8eaf0';
Chart.defaults.font.family="'Noto Sans KR',sans-serif";Chart.defaults.font.size=11;
const UP='#0d9b6a',DN='#d9304f',MU='#b0b4c4';
function bc(d){{return d.map(v=>v>0?UP:v<0?DN:MU)}}
new Chart(document.getElementById('eqChart'),{{
  type:'bar',
  data:{{labels:{json.dumps(eq_names)},datasets:[{{data:{json.dumps(eq_chgs)},backgroundColor:bc({json.dumps(eq_chgs)}),borderRadius:4,barPercentage:.6}}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{weight:'600'}}}}}}}}}}
}});
new Chart(document.getElementById('stChart'),{{
  type:'bar',
  data:{{labels:{json.dumps(st_names)},datasets:[{{data:{json.dumps(st_chgs)},backgroundColor:bc({json.dumps(st_chgs)}),borderRadius:4,barPercentage:.6}}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{weight:'600'}}}}}}}}}}
}});
</script>
</body>
</html>"""
    return html


def generate_weekly_reports(year=2026):
    """주간 보고서 생성"""
    daily_data = load_daily_data()
    weeks = get_week_ranges(year)

    weekly_dir = os.path.join(OUTPUT_DIR, "weekly")
    os.makedirs(weekly_dir, exist_ok=True)

    count = 0
    for (iso_year, iso_week), dates in sorted(weeks.items()):
        available = [d for d in dates if d in daily_data]
        if not available:
            continue

        agg = aggregate_period(daily_data, dates)
        if not agg:
            continue

        first = available[0]
        last = available[-1]
        week_label = f"W{iso_week:02d}"
        title = f"Weekly Summary | {year} {week_label}"
        subtitle = f"{first} ~ {last} ({len(available)} trading days)"
        filename = f"{year}-W{iso_week:02d}.html"

        html = generate_periodic_html(agg, title, subtitle, "Weekly", filename)
        path = os.path.join(weekly_dir, filename)
        with open(path, "w") as f:
            f.write(html)
        count += 1
        print(f"  [WEEKLY] {filename}: {first} ~ {last}")

    print(f"Total: {count} weekly reports")
    return count


def generate_monthly_reports(year=2026):
    """월간 보고서 생성"""
    daily_data = load_daily_data()

    monthly_dir = os.path.join(OUTPUT_DIR, "monthly")
    os.makedirs(monthly_dir, exist_ok=True)

    count = 0
    for month in range(1, 13):
        month_str = f"{year}-{month:02d}"
        month_dates = sorted([d for d in daily_data if d.startswith(month_str)])

        if not month_dates:
            continue

        agg = aggregate_period(daily_data, month_dates)
        if not agg:
            continue

        month_name = dt.date(year, month, 1).strftime("%B")
        title = f"Monthly Summary | {year} {month_name}"
        subtitle = f"{month_dates[0]} ~ {month_dates[-1]} ({len(month_dates)} trading days)"
        filename = f"{year}-{month:02d}.html"

        html = generate_periodic_html(agg, title, subtitle, "Monthly", filename)
        path = os.path.join(monthly_dir, filename)
        with open(path, "w") as f:
            f.write(html)
        count += 1
        print(f"  [MONTHLY] {filename}: {month_dates[0]} ~ {month_dates[-1]}")

    print(f"Total: {count} monthly reports")
    return count


if __name__ == "__main__":
    import sys
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026

    print("=== Weekly Reports ===")
    generate_weekly_reports(year)

    print("\n=== Monthly Reports ===")
    generate_monthly_reports(year)

    # index 갱신
    generate_index()
    print("\nDone!")
