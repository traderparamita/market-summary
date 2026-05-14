#!/usr/local/bin/python3.12
"""
Weekly / Monthly / Quarterly Market Summary Report Generator
- Snowflake MKT100 (CSV fallback) 기준으로 주간·월간·분기 HTML 보고서 생성
"""

import json
import os
import re
import glob
import datetime as dt
import csv
from report_utils import (
    fmt, chg_class, chg_sign, heat_color, heat_text, spark_svg,
    KO_LABELS, EQUITY_ORDER, MSCI_ORDER, BOND_RATE_ORDER, BOND_ETF_ORDER,
    FX_ORDER, CM_ORDER, ST_ORDER, DATA_SOURCES,
    KR_STOCK_ORDER, US_STOCK_ORDER, ASIA_STOCK_ORDER,
    KR_STOCK_TOP_N, US_STOCK_TOP_N, ASIA_STOCK_TOP_N,
    PERIODIC_TAB_SPECS, save_story_files, inject_existing_story, extract_tab,
    ordered,
)
from generate import generate_index

# Shared OG image version (bump in generate.py when the OG image changes)
try:
    from generate import OG_IMAGE_VERSION
except ImportError:
    OG_IMAGE_VERSION = "1"


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "summary")
HISTORY_CSV = os.path.join(os.path.dirname(__file__), "history", "market_data.csv")


def load_market_data():
    """MKT100 (Snowflake) → 중첩 dict 로드. CSV fallback 지원.

    스키마: DATE, INDICATOR_CODE, CATEGORY, TICKER, CLOSE, ...

    반환: ({date_str: {category: {ticker: close}}}, 전체 거래일 목록 sorted)
    """
    from market_source import load_long

    df = load_long()
    data: dict = {}
    for row in df.itertuples(index=False):
        d = row.DATE.strftime("%Y-%m-%d") if hasattr(row.DATE, "strftime") else str(row.DATE)
        cat = row.CATEGORY
        ticker = row.TICKER
        close = row.CLOSE
        if not (d and cat and ticker):
            continue
        try:
            close = float(close)
        except (ValueError, TypeError):
            continue
        data.setdefault(d, {}).setdefault(cat, {})[ticker] = close

    trading_days = sorted(data.keys())
    return data, trading_days


def get_week_ranges(trading_days, year=2026):
    """ISO 주차 기반으로 주간 범위 반환. {(year, week): [date_str, ...]}"""
    weeks = {}
    for d_str in trading_days:
        d = dt.date.fromisoformat(d_str)
        if d.year != year:
            continue
        iso = d.isocalendar()
        key = (iso[0], iso[1])
        weeks.setdefault(key, []).append(d_str)
    return weeks


def get_quarter_ranges(trading_days, year=2026):
    """분기(캘린더 기준) 범위 반환. {(year, quarter): [date_str, ...]}

    Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec.
    """
    quarters: dict = {}
    for d_str in trading_days:
        d = dt.date.fromisoformat(d_str)
        if d.year != year:
            continue
        quarter = (d.month - 1) // 3 + 1
        key = (d.year, quarter)
        quarters.setdefault(key, []).append(d_str)
    return quarters


def aggregate_period(market_data, trading_days, date_list):
    """market_data.csv 기반으로 기간 요약 집계"""
    available = [d for d in date_list if d in market_data]
    if not available:
        return None

    first_date = available[0]
    last_date = available[-1]

    # 기간 직전 영업일 (기준가)
    idx = trading_days.index(first_date) if first_date in trading_days else -1
    prev_date = trading_days[idx - 1] if idx > 0 else None

    # 기간 시작일 직전 영업일 후보 (글로벌 prev_date 에 ticker 데이터 없을 때 ticker-level fallback)
    # 예: W19 KOSPI — 5/1 KR Labor Day 휴장이라 5/4 가 first_date. prev_date=5/1 KR 데이터 없음.
    #     ticker 별로 5/1 → 4/30 → 4/29 ... 거꾸로 탐색해 그 ticker 가 가졌던 마지막 종가 사용.
    prev_period_days = [d for d in trading_days if d < first_date]

    # YTD 기준: 전년 마지막 영업일
    year = int(first_date[:4])
    ye_date = None
    for d in reversed(trading_days):
        if d < f"{year}-01-01":
            ye_date = d
            break

    # 전년 영업일 후보 (글로벌 ye_date 에 ticker 데이터가 없을 때 ticker-level fallback)
    prev_year_days = [d for d in trading_days if d < f"{year}-01-01"]

    result = {"dates": available, "first": first_date, "last": last_date}

    last_day = market_data[last_date]
    prev_day = market_data[prev_date] if prev_date else {}
    ye_day = market_data[ye_date] if ye_date else {}

    for cat in ["equity", "bond", "fx", "commodity", "risk", "stocks"]:
        result[cat] = {}

        # 기간 내 모든 날짜에서 이 카테고리의 티커를 수집
        all_tickers = set()
        for d in available:
            all_tickers.update(market_data.get(d, {}).get(cat, {}).keys())

        for ticker in all_tickers:
            # 기간 내 가장 최근 종가 찾기
            last_close = None
            ticker_last_date = None
            for d in reversed(available):
                c = market_data.get(d, {}).get(cat, {}).get(ticker)
                if c:
                    last_close = c
                    ticker_last_date = d
                    break
            if not last_close:
                continue

            # period_chg: 직전 영업일 종가 → 기간 마지막 종가
            # 글로벌 prev_date 에 ticker 데이터 없으면 그 ticker 가 가졌던 마지막 직전 종가로 fallback
            # (예: W19 KOSPI — 5/1 KR 휴장이라 4/30 종가를 base 로 사용해야 정확한 Mon-Thu 누적)
            base_close = prev_day.get(cat, {}).get(ticker)
            if not base_close:
                for d in reversed(prev_period_days):
                    candidate = market_data.get(d, {}).get(cat, {}).get(ticker)
                    if candidate:
                        base_close = candidate
                        break
            if not base_close:
                base_close = market_data[first_date].get(cat, {}).get(ticker)

            if base_close and last_close and base_close != 0:
                period_chg = (last_close - base_close) / base_close * 100
            else:
                period_chg = 0

            # YTD: 전년 마지막 종가 → 기간 마지막 종가
            # 글로벌 ye_date 에 해당 ticker 데이터 없으면 그 ticker가 가졌던 마지막 전년도 종가로 fallback
            # (예: KR Top50 백필 누락으로 2025-12-31 데이터 없음 → 2025-12-30 사용)
            ytd = 0
            ye_close = ye_day.get(cat, {}).get(ticker)
            if not ye_close:
                for d in reversed(prev_year_days):
                    candidate = market_data.get(d, {}).get(cat, {}).get(ticker)
                    if candidate:
                        ye_close = candidate
                        break
            if ye_close and last_close and ye_close != 0:
                ytd = (last_close - ye_close) / ye_close * 100

            # 스파크라인: 직전 영업일 종가를 기준점(0%)으로 포함
            daily_closes = []
            if base_close:
                daily_closes.append(base_close)
            for d in available:
                c = market_data.get(d, {}).get(cat, {}).get(ticker)
                if c:
                    daily_closes.append(c)

            spark = []
            if daily_closes and daily_closes[0] != 0:
                spark = [round((c / daily_closes[0] - 1) * 100, 2) for c in daily_closes]

            # 일별 변동률 최대/최소
            daily_chgs = []
            for i, d in enumerate(available):
                cur = market_data.get(d, {}).get(cat, {}).get(ticker)
                # 전일: 기간 내 이전일 또는 직전 영업일
                if i == 0:
                    prev_c = base_close
                else:
                    prev_c = market_data.get(available[i - 1], {}).get(cat, {}).get(ticker)
                if cur and prev_c and prev_c != 0:
                    daily_chgs.append((cur - prev_c) / prev_c * 100)

            best_day = max(daily_chgs) if daily_chgs else 0
            worst_day = min(daily_chgs) if daily_chgs else 0

            result[cat][ticker] = {
                "close": last_close,
                "open": base_close or 0,
                "period_chg": round(period_chg, 2),
                "best_day": round(best_day, 2),
                "worst_day": round(worst_day, 2),
                "spark": spark,
                "date": ticker_last_date,
                "ytd": round(ytd, 2),
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

    # KPI 목록 (일간과 동일한 8개)
    kpi_list = [
        ("코스피", "KOSPI", eq.get("KOSPI")),
        ("S&P500", "S&P500", eq.get("S&P500")),
        ("나스닥", "NASDAQ", eq.get("NASDAQ")),
        ("니케이", "Nikkei225", eq.get("Nikkei225")),
        ("미국10년", "US 10Y", bd.get("US 10Y")),
        ("달러/원", "USD/KRW", fx.get("USD/KRW")),
        ("WTI유", "WTI", cm.get("WTI")),
        ("금", "Gold", cm.get("Gold")),
    ]
    kpi_items = []
    for ko_label, en_label, d in kpi_list:
        if not d:
            continue
        c = d["close"]
        if en_label in ["WTI", "Gold"]:
            v = f"${fmt(c)}"
        elif en_label == "US 10Y":
            v = f"{c:.2f}%"
        elif c > 100:
            v = fmt(c, 0)
        else:
            v = fmt(c, 2)
        kpi_items.append({"label": ko_label, "value": v, "chg": d["period_chg"]})

    # 히트맵 행 생성
    def heatmap_row(name, d, show_dollar=False, as_bp=False):
        close = d["close"]
        if as_bp:
            close_str = f"{close:.2f}%"
        elif show_dollar:
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

        def cell(v):
            bg_ = heat_color(v)
            tc_ = heat_text(v)
            if as_bp:
                prev = close / (1 + v / 100) if (1 + v / 100) else close
                bp = (close - prev) * 100
                sign = "+" if bp > 0 else ""
                txt = f"{sign}{bp:.0f} bp"
            else:
                txt = chg_sign(v)
            return f'<td class="heat-cell" style="background:{bg_};color:{tc_}">{txt}</td>'

        ko = KO_LABELS.get(name)
        disp = f'{ko}({name})' if ko and ko != name else name
        return f"""<tr>
          <td class="name-cell">{disp}</td>
          <td class="close-cell">{close_str}</td>
          <td class="spark-cell">{spark}</td>
          {cell(chg)}
          {cell(best)}
          {cell(worst)}
          {cell(ytd)}
        </tr>"""

    BOND_ORDER = BOND_RATE_ORDER  # periodic uses rate order for bonds

    bond_etfs = {"AGG", "TLT", "HYG", "LQD", "EMB", "IEI", "SHY", "TIP"}
    bd_rates = {k: v for k, v in bd.items() if k not in bond_etfs}
    bd_etf = {k: v for k, v in bd.items() if k in bond_etfs}

    msci_names = set(MSCI_ORDER)
    eq_regional = {k: v for k, v in eq.items() if k not in msci_names}
    eq_msci = {k: v for k, v in eq.items() if k in msci_names}

    # 상위/하위 종목 (일간과 동일: equity, stocks, commodity, fx)
    all_items = [(n, d) for c in [eq, st, cm, fx] for n, d in c.items()]
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
    cm_names = list(cm.keys())
    cm_ytd = [cm[n].get("ytd", 0) for n in cm_names]

    # Scatter: period_chg vs ytd (cross-asset)
    scatter_data = []
    for cat_items, cat_label in [(eq, "equity"), (st, "stocks"), (cm, "commodity")]:
        for name, d in cat_items.items():
            scatter_data.append({"x": d.get("ytd", 0), "y": d["period_chg"], "label": name, "cat": cat_label})

    # VIX
    vix = rk.get("VIX", {})
    vix_val = vix.get("close", 0)
    if vix_val >= 30: vix_label, vix_color = "Extreme Fear", "#d9304f"
    elif vix_val >= 20: vix_label, vix_color = "Elevated", "#d48b07"
    elif vix_val >= 15: vix_label, vix_color = "Normal", "#7c8298"
    else: vix_label, vix_color = "Complacent", "#0d9b6a"

    period_dir = {"weekly": "weekly", "monthly": "monthly", "quarterly": "quarterly"}.get(
        period_label.lower(), "monthly"
    )
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{subtitle} — {period_label} 시장 요약 (Equity · Bonds · FX · Commodities · Risk)">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="icon" type="image/png" sizes="192x192" href="../favicon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="../favicon-512.png">
<link rel="apple-touch-icon" sizes="180x180" href="../apple-touch-icon.png">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{subtitle} — {period_label} 시장 요약 보고서">
<meta property="og:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://traderparamita.github.io/market-summary/{period_dir}/{filename}">
<meta property="og:site_name" content="Market Summary">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{subtitle} — {period_label} 시장 요약 보고서">
<meta name="twitter:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --card2:#f0f1f6;
  --border:#e0e3ed; --text:#2d3148; --muted:#7c8298;
  --accent:#F58220; --accent2:#043B72;
  --up:#d92b2b; --down:#1a5fb4; --warn:#CB6015;
  --gold:#b8860b; --oil:#d35400;
}}
::selection{{background:#F58220;color:#ffffff}}
::-moz-selection{{background:#F58220;color:#ffffff}}
/* Story Hero keeps original blue — brand accents apply elsewhere */
.story-hero{{border-left-color:#3b6ee6!important}}
.story-hero h2{{color:#3b6ee6!important}}
.story-text .hl-accent{{color:#3b6ee6!important}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic','맑은 고딕',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.65;padding:24px;max-width:1360px;margin:0 auto}}
.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px;padding-bottom:20px;border-bottom:2px solid var(--border)}}
.header-left h1{{font-size:26px;font-weight:700;color:#1a1d2e;margin-bottom:2px}}
.header-left .date{{font-size:13px;color:var(--muted);letter-spacing:1px}}
.header-right{{display:flex;gap:20px;align-items:center}}
.mood-badge{{display:flex;align-items:center;gap:8px;padding:8px 18px;border-radius:24px;font-size:13px;font-weight:600}}
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:28px}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
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
.heatmap-section h2 .badge{{font-size:11px;padding:2px 8px;border-radius:12px;background:var(--card2);color:var(--muted);font-weight:500}}
.heatmap-section h2 .src-tag{{font-size:10px;padding:2px 8px;border-radius:10px;background:#f0f1f5;color:#9a9db5;font-weight:400;margin-left:6px;letter-spacing:0.3px}}
.heatmap{{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.heatmap th{{font-size:11px;font-weight:600;color:var(--muted);padding:10px 12px;text-align:right;background:var(--card2);border-bottom:1px solid var(--border);white-space:nowrap}}
.heatmap th:first-child,.heatmap th:nth-child(2),.heatmap th:nth-child(3){{text-align:left}}
.heatmap td{{padding:8px 12px;font-size:13px;border-bottom:1px solid #f3f4f8}}
.heatmap tr:last-child td{{border-bottom:none}}
.name-cell{{font-weight:600;color:#1a1d2e;white-space:nowrap;min-width:100px}}
.close-cell{{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text);text-align:left;white-space:nowrap}}
.spark-cell{{text-align:center;padding:4px 8px}}
.heat-cell{{text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600;border-radius:0;transition:all 0.15s}}
.heatmap tr:hover{{filter:brightness(0.97)}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
.chart-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.chart-card .title{{font-size:13px;color:var(--muted);font-weight:600;margin-bottom:12px}}
.chart-box{{position:relative;height:260px}}
.risk-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:28px}}
.risk-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.risk-card .label{{font-size:12px;color:var(--muted);margin-bottom:4px}}
.risk-card .value{{font-size:28px;font-weight:700;font-family:'JetBrains Mono',monospace}}
.risk-card .desc{{font-size:11px;font-weight:600;margin-top:2px}}
.risk-card .bar-track{{height:6px;background:#ecedf2;border-radius:3px;margin-top:8px;overflow:hidden}}
.risk-card .bar-fill{{height:100%;border-radius:3px}}
.footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:40px;padding-top:20px;border-top:1px solid var(--border)}}
.ai-disclaimer{{text-align:center;color:var(--muted);font-size:11px;margin-top:24px;padding:12px 16px;background:rgba(0,0,0,0.03);border-radius:8px;line-height:1.6}}
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
.session-block.europe::before{{background:linear-gradient(90deg,#F58220,#043B72)}}
.session-block.us::before{{background:linear-gradient(90deg,#043B72,#7F9FC3)}}
.session-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.session-icon{{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px}}
.session-icon.asia{{background:rgba(212,139,7,0.1)}}.session-icon.europe{{background:rgba(59,110,230,0.1)}}.session-icon.us{{background:rgba(107,92,231,0.1)}}
.session-name{{font-size:15px;font-weight:600;color:#1a1d2e}}
.session-time{{font-size:11px;color:var(--muted)}}
.session-verdict{{display:inline-block;padding:3px 10px;border-radius:16px;font-size:11px;font-weight:600;margin-bottom:10px}}
.verdict-up{{background:rgba(217,43,43,0.1);color:var(--up)}}.verdict-down{{background:rgba(26,95,180,0.1);color:var(--down)}}.verdict-mixed{{background:rgba(212,139,7,0.1);color:var(--warn)}}
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
.risk-tag.high{{background:rgba(26,95,180,0.15);color:var(--down)}}.risk-tag.med{{background:rgba(212,139,7,0.15);color:var(--warn)}}

/* ── Macro & Events Tab ── */
.macro-section{{margin-bottom:32px}}
.macro-section h2{{font-size:16px;font-weight:700;color:var(--accent2);margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid var(--border)}}
.macro-cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}}
.macro-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;border-left:4px solid var(--accent);box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.macro-date{{font-size:11px;color:var(--muted);margin-bottom:4px;font-weight:500}}
.macro-title{{font-size:15px;font-weight:700;color:var(--text);margin-bottom:8px}}
.macro-values{{font-size:13px;margin-bottom:8px;font-family:'JetBrains Mono',monospace}}
.macro-explain{{font-size:13px;color:var(--text);line-height:1.75;background:var(--card2);padding:10px 12px;border-radius:6px;margin-bottom:8px}}
.macro-reaction{{font-size:12px;color:var(--muted);font-style:italic}}
.macro-calendar{{width:100%;border-collapse:collapse;font-size:13px;background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.macro-calendar th{{background:var(--accent2);color:#fff;padding:10px 14px;text-align:left;font-size:12px;font-weight:600}}
.macro-calendar td{{padding:10px 14px;border-bottom:1px solid var(--border);vertical-align:top;line-height:1.6}}
.macro-calendar tr:last-child td{{border-bottom:none}}
.macro-calendar tr:hover td{{background:var(--card2)}}
.macro-importance{{color:var(--warn);font-weight:700}}
/* ── Sources ── */
.sources-header{{margin-bottom:20px}}
.sources-header h2{{font-size:15px;font-weight:700;color:#1a1d2e;margin-bottom:4px}}
.sources-header .sources-sub{{font-size:12px;color:var(--muted)}}
.sources-section{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 20px;margin-bottom:12px}}
.sources-section h3{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.sources-list{{margin:0;padding-left:18px;font-size:13px;line-height:1.8}}
.sources-list a{{color:var(--accent);text-decoration:none}}
.sources-list a:hover{{text-decoration:underline}}
.source-meta{{font-size:11px;color:var(--muted)}}
/* ── CS Story Tab ── */
.cs-hero{{background:linear-gradient(135deg,#fff5eb,#fde9d3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:24px}}
.cs-hero h2{{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}}
.cs-text{{font-size:16px;color:#2d3148;line-height:1.9}}
.cs-text p{{margin-bottom:14px}}.cs-text p:last-child{{margin-bottom:0}}
.cs-section{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px 28px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.cs-section h3{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:10px}}
.cs-section p{{font-size:15px;color:#2d3148;line-height:1.85;margin-bottom:10px}}.cs-section p:last-child{{margin-bottom:0}}
/* ── PM Story Tab ── */
.pm-hero{{background:linear-gradient(135deg,#eef4fb,#dde9f6);border:1px solid var(--border);border-left:4px solid #043B72;border-radius:12px;padding:24px 28px;margin-bottom:20px}}
.pm-hero h2{{font-size:13px;color:#043B72;letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}}
.pm-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-bottom:16px}}
.pm-section{{background:var(--card);border:1px solid var(--border);border-left:3px solid #043B72;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.pm-section h3{{font-size:15px;font-weight:700;color:#043B72;margin-bottom:10px;display:flex;align-items:center;gap:8px}}
.pm-section ul{{list-style:none;padding:0;margin:0}}
.pm-section li{{font-size:13.5px;color:#2d3148;line-height:1.75;margin-bottom:6px;padding-left:12px;position:relative}}
.pm-section li::before{{content:'·';position:absolute;left:0;color:#043B72;font-weight:700}}
@media(max-width:900px){{
  .chart-grid,.movers-row{{grid-template-columns:1fr}}
  .kpi-strip{{grid-template-columns:repeat(3,1fr)}}
  .session-grid,.insight-grid{{grid-template-columns:1fr}}
  .causal-chain{{flex-direction:column}}.cause-arrow{{transform:rotate(90deg);padding:4px 0}}
  .af-map{{grid-template-columns:1fr}}.risk-items{{grid-template-columns:1fr}}
  .macro-cards{{grid-template-columns:1fr}}
  .pm-grid{{grid-template-columns:1fr}}
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
  <button class="tab-btn active" onclick="switchTab('cs')">CS Story</button>
  <button class="tab-btn" onclick="switchTab('pm')">PM Story</button>
  <button class="tab-btn" onclick="switchTab('story')">{period_label} Story</button>
  <button class="tab-btn" onclick="switchTab('data')">Data Dashboard</button>
  <button class="tab-btn" onclick="switchTab('macro')">Macro &amp; Events</button>
  <button class="tab-btn" onclick="switchTab('sources')">Sources</button>
</div>

<div id="tab-data" class="tab-panel">
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
    html += '<div class="movers-row">\n<div class="movers-card"><h3>상승 Top 3 ({0})</h3>\n'.format(period_label)
    for name, d in top3:
        ko = KO_LABELS.get(name)
        disp = f'{ko}({name})' if ko and ko != name else name
        cls = chg_class(d["period_chg"])
        html += f'<div class="mover-item"><span class="mover-name">{disp}</span><span class="mover-val {cls}">{chg_sign(d["period_chg"])}</span></div>\n'
    html += '</div>\n<div class="movers-card"><h3>하락 Top 3 ({0})</h3>\n'.format(period_label)
    for name, d in bottom3:
        ko = KO_LABELS.get(name)
        disp = f'{ko}({name})' if ko and ko != name else name
        cls = chg_class(d["period_chg"])
        html += f'<div class="mover-item"><span class="mover-name">{disp}</span><span class="mover-val {cls}">{chg_sign(d["period_chg"])}</span></div>\n'
    html += '</div>\n</div>\n'

    # 종목: 시가총액 순 (KR_TOP50 / US_TOP50 / ASIA_TOP 순서) Top N 만 표시
    kr_stocks = {n: st[n] for n in KR_STOCK_ORDER[:KR_STOCK_TOP_N] if n in st}
    us_stocks = {n: st[n] for n in US_STOCK_ORDER[:US_STOCK_TOP_N] if n in st}
    asia_stocks = {n: st[n] for n in ASIA_STOCK_ORDER[:ASIA_STOCK_TOP_N] if n in st}
    # KR/US/ASIA 어디에도 안 속한 잔여 (안전망)
    other_stocks = {
        n: d for n, d in st.items()
        if n not in KR_STOCK_ORDER and n not in US_STOCK_ORDER and n not in ASIA_STOCK_ORDER
    }

    # 아시아 종목 통화 표기: HK/CN/IN/JP/TW/AU 는 비-USD 라 $ 기호 부적절 → False
    # 히트맵 테이블 (filter_to_order=True 면 order 화이트리스트만 표시)
    sections = [
        ("주식(Equity)", eq_regional, False, False, EQUITY_ORDER, False),
        ("MSCI 지수", eq_msci, False, False, MSCI_ORDER, False),
        ("채권·금리(Bonds & Rates)", bd_rates, False, True, BOND_ORDER, False),
        ("채권 ETF(Bond ETF)", bd_etf, True, False, ["AGG","TLT","IEI","SHY","TIP","LQD","HYG","EMB"], False),
        ("환율(FX)", fx, False, False, FX_ORDER, False),
        ("원자재(Commodities)", cm, True, False, CM_ORDER, False),
        (f"한국 주식(Korean Stocks · Top {KR_STOCK_TOP_N})",
         kr_stocks, False, False, KR_STOCK_ORDER, True),
        (f"미국 주식(US Stocks · Top {US_STOCK_TOP_N})",
         us_stocks, True, False, US_STOCK_ORDER, True),
        (f"아시아 종목(Asian Stocks · Top {ASIA_STOCK_TOP_N})",
         asia_stocks, False, False, ASIA_STOCK_ORDER, True),
    ]
    if other_stocks:
        sections.append((
            "기타 종목(ETC)", other_stocks, True, False,
            list(other_stocks.keys()), True,
        ))

    for sec_title, cat, dollar, as_bp, order, filter_to_order in sections:
        if not cat:
            continue
        idx = {n: i for i, n in enumerate(order)}
        if filter_to_order:
            items = [(n, cat[n]) for n in order if n in cat]
        else:
            items = sorted(cat.items(), key=lambda x: idx.get(x[0], 999))
        # DATA_SOURCES 키는 prefix 매칭 (Top N 변동 흡수)
        src = DATA_SOURCES.get(sec_title) or next(
            (v for k, v in DATA_SOURCES.items() if sec_title.startswith(k)), ""
        )
        src_html = f' <span class="src-tag">{src}</span>' if src else ""
        html += f"""<div class="heatmap-section">
<h2>{sec_title} <span class="badge">{len(items)}</span>{src_html}</h2>
<table class="heatmap">
<thead><tr><th>종목</th><th>종가</th><th>추이</th><th>{period_label}</th><th>최고일</th><th>최저일</th><th>연초대비</th></tr></thead>
<tbody>\n"""
        for name, d in items:
            html += heatmap_row(name, d, dollar, as_bp)
        html += "</tbody></table></div>\n"

    # ── Risk Dashboard ──
    html += '<div class="heatmap-section"><h2>Risk Dashboard <span class="src-tag">yfinance · FinanceDataReader</span></h2></div>\n<div class="risk-strip">\n'
    vix_pct = min(vix_val / 50 * 100, 100) if vix_val else 0
    html += f"""<div class="risk-card">
  <div class="label">VIX</div>
  <div class="value" style="color:{vix_color}">{vix_val:.1f}</div>
  <div class="desc" style="color:{vix_color}">{vix_label}</div>
  <div class="bar-track"><div class="bar-fill" style="width:{vix_pct:.0f}%;background:{vix_color}"></div></div>
</div>\n"""
    for name, d in rk.items():
        if name == "VIX":
            continue
        html += f"""<div class="risk-card">
  <div class="label">{name}</div>
  <div class="value">{d['close']:.1f}</div>
  <div class="desc {chg_class(d['period_chg'])}">{chg_sign(d['period_chg'])}</div>
</div>\n"""
    for name in ["HYG", "EMB"]:
        if name in bd:
            d = bd[name]
            html += f"""<div class="risk-card">
  <div class="label">{name}</div>
  <div class="value">{d['close']:.1f}</div>
  <div class="desc {chg_class(d['period_chg'])}">{chg_sign(d['period_chg'])}</div>
</div>\n"""
    html += '</div>\n'

    # ── Charts (일간과 동일 4개) ──
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
  <div class="chart-card">
    <div class="title">{period_label} vs YTD (Cross-Asset)</div>
    <div class="chart-box"><canvas id="scatterChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="title">Commodity YTD (%)</div>
    <div class="chart-box"><canvas id="cmChart"></canvas></div>
  </div>
</div>


</div><!-- /tab-data -->

<div id="tab-macro" class="tab-panel">
<!-- MACRO_EVENTS_PLACEHOLDER -->
</div><!-- /tab-macro -->

<div id="tab-story" class="tab-panel">
<!-- STORY_CONTENT_PLACEHOLDER -->
</div><!-- /tab-story -->

<div id="tab-cs" class="tab-panel active">
<!-- CS_STORY_PLACEHOLDER -->
</div><!-- /tab-cs -->

<div id="tab-pm" class="tab-panel">
<!-- PM_STORY_PLACEHOLDER -->
</div><!-- /tab-pm -->

<div id="tab-sources" class="tab-panel">
<!-- SOURCES_PLACEHOLDER -->
</div><!-- /tab-sources -->

<div class="ai-disclaimer">⚠️ 본 보고서는 AI가 자동 생성한 참고 자료이며, 투자 권유가 아닙니다. 수치·해석에 오류가 포함될 수 있으므로 투자 판단 시 반드시 원본 데이터를 확인하시기 바랍니다.</div>
<div class="footer">{title} | AI auto-generated</div>

<script>
function switchTab(id){{
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  event.target.classList.add('active');
  if(id==='data') setTimeout(()=>window.dispatchEvent(new Event('resize')),50);
}}
Chart.defaults.color='#7c8298';Chart.defaults.borderColor='#e8eaf0';
Chart.defaults.font.family="'Spoqa Han Sans Neo','Spoqa Han Sans',sans-serif";Chart.defaults.font.size=11;
const UP='#d92b2b',DN='#1a5fb4',AC='#F58220',WN='#CB6015',MU='#b0b4c4';
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
// Scatter: period vs YTD
new Chart(document.getElementById('scatterChart'),{{
  type:'scatter',
  data:{{
    datasets:[
      {{label:'Equity',data:{json.dumps([s for s in scatter_data if s['cat']=='equity'])},backgroundColor:AC+'aa',pointRadius:6}},
      {{label:'Stocks',data:{json.dumps([s for s in scatter_data if s['cat']=='stocks'])},backgroundColor:'#043B72aa',pointRadius:6}},
      {{label:'Commodity',data:{json.dumps([s for s in scatter_data if s['cat']=='commodity'])},backgroundColor:WN+'aa',pointRadius:6}}
    ]
  }},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{
      legend:{{position:'top',labels:{{boxWidth:8}}}},
      tooltip:{{callbacks:{{label:c=>c.raw.label+' (YTD:'+c.raw.x.toFixed(1)+'%, {period_label}:'+c.raw.y.toFixed(1)+'%)'}}}}
    }},
    scales:{{
      x:{{title:{{display:true,text:'YTD %',color:'#7c8298'}},grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},
      y:{{title:{{display:true,text:'{period_label} %',color:'#7c8298'}},grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}}
    }}
  }}
}});
// Commodity YTD
new Chart(document.getElementById('cmChart'),{{
  type:'bar',
  data:{{labels:{json.dumps(cm_names)},datasets:[{{data:{json.dumps(cm_ytd)},backgroundColor:bc({json.dumps(cm_ytd)}),borderRadius:4,barPercentage:.55}}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{weight:'600'}}}}}}}}}}
}});
</script>
</body>
</html>"""
    return html


_PERIODIC_TAB_SPECS = PERIODIC_TAB_SPECS


def _save_story_file(html_path, html_content):
    """Story/CS/PM 탭 내용을 각각 sibling 파일로 저장."""
    save_story_files(html_path, html_content, _PERIODIC_TAB_SPECS,
                     log_fn=lambda msg: print(msg))


def _inject_existing_story(path, new_html):
    """기존 파일의 Story/CS/PM 탭을 새 HTML placeholder에 주입."""
    return inject_existing_story(path, new_html, _PERIODIC_TAB_SPECS)


def _save_macro_file(html_path, html_content):
    """HTML에서 Macro & Events 콘텐츠를 추출하여 _macro.html 파일로 저장"""
    macro = extract_tab(html_content, "macro")
    if not macro or "MACRO_EVENTS_PLACEHOLDER" in macro:
        return
    base, ext = os.path.splitext(html_path)
    macro_path = f"{base}_macro{ext}"
    with open(macro_path, "w") as f:
        f.write(macro)
    print(f"  Macro saved: {os.path.basename(macro_path)}")


def _inject_existing_macro(path, new_html):
    """기존 파일에 Macro & Events가 있으면 새 HTML의 placeholder에 주입 + _macro.html 저장"""
    old_macro = ""
    if os.path.exists(path):
        with open(path) as f:
            old_content = f.read()
        candidate = extract_tab(old_content, "macro")
        if candidate and "MACRO_EVENTS_PLACEHOLDER" not in candidate:
            old_macro = candidate
        if not old_macro:
            base, ext = os.path.splitext(path)
            sib_path = f"{base}_macro{ext}"
            if os.path.exists(sib_path):
                with open(sib_path) as f:
                    sib_macro = f.read().strip()
                if sib_macro and "MACRO_EVENTS_PLACEHOLDER" not in sib_macro:
                    old_macro = sib_macro
    if old_macro:
        new_html = new_html.replace("<!-- MACRO_EVENTS_PLACEHOLDER -->", old_macro)
    new_html = _inject_existing_story(path, new_html)
    with open(path, "w") as f:
        f.write(new_html)
    _save_macro_file(path, new_html)
    _save_story_file(path, new_html)


def generate_weekly_reports(year=2026):
    """주간 보고서 생성 (market_data.csv 기반)"""
    market_data, trading_days = load_market_data()
    weeks = get_week_ranges(trading_days, year)

    weekly_dir = os.path.join(OUTPUT_DIR, "weekly")
    os.makedirs(weekly_dir, exist_ok=True)

    count = 0
    for (iso_year, iso_week), dates in sorted(weeks.items()):
        agg = aggregate_period(market_data, trading_days, dates)
        if not agg:
            continue

        first = agg["first"]
        last = agg["last"]
        n_days = len(agg["dates"])
        week_label = f"W{iso_week:02d}"
        title = f"Weekly Summary | {year} {week_label}"
        subtitle = f"{first} ~ {last} ({n_days} trading days)"
        filename = f"{year}-W{iso_week:02d}.html"

        html = generate_periodic_html(agg, title, subtitle, "Weekly", filename)
        path = os.path.join(weekly_dir, filename)
        _inject_existing_macro(path, html)
        count += 1
        print(f"  [WEEKLY] {filename}: {first} ~ {last}")

    print(f"Total: {count} weekly reports")
    return count


def generate_monthly_reports(year=2026):
    """월간 보고서 생성 (market_data.csv 기반)"""
    market_data, trading_days = load_market_data()

    monthly_dir = os.path.join(OUTPUT_DIR, "monthly")
    os.makedirs(monthly_dir, exist_ok=True)

    count = 0
    for month in range(1, 13):
        month_str = f"{year}-{month:02d}"
        month_dates = sorted([d for d in trading_days if d.startswith(month_str)])

        if not month_dates:
            continue

        agg = aggregate_period(market_data, trading_days, month_dates)
        if not agg:
            continue

        month_name = dt.date(year, month, 1).strftime("%B")
        title = f"Monthly Summary | {year} {month_name}"
        subtitle = f"{month_dates[0]} ~ {month_dates[-1]} ({len(month_dates)} trading days)"
        filename = f"{year}-{month:02d}.html"

        html = generate_periodic_html(agg, title, subtitle, "Monthly", filename)
        path = os.path.join(monthly_dir, filename)
        _inject_existing_macro(path, html)
        count += 1
        print(f"  [MONTHLY] {filename}: {month_dates[0]} ~ {month_dates[-1]}")

    print(f"Total: {count} monthly reports")
    return count


def generate_quarterly_reports(year=2026, only_quarter=None):
    """분기 보고서 생성 (Snowflake MKT100 → CSV fallback).

    only_quarter: 1~4 지정 시 해당 분기만 생성. None 이면 전체 분기.
    """
    market_data, trading_days = load_market_data()
    quarters = get_quarter_ranges(trading_days, year)

    quarterly_dir = os.path.join(OUTPUT_DIR, "quarterly")
    os.makedirs(quarterly_dir, exist_ok=True)

    count = 0
    for (iso_year, quarter), dates in sorted(quarters.items()):
        if only_quarter is not None and quarter != only_quarter:
            continue
        agg = aggregate_period(market_data, trading_days, dates)
        if not agg:
            continue

        first = agg["first"]
        last = agg["last"]
        n_days = len(agg["dates"])
        q_label = f"Q{quarter}"
        title = f"Quarterly Summary | {year} {q_label}"
        subtitle = f"{first} ~ {last} ({n_days} trading days)"
        filename = f"{year}-Q{quarter}.html"

        html = generate_periodic_html(agg, title, subtitle, "Quarterly", filename)
        path = os.path.join(quarterly_dir, filename)
        _inject_existing_macro(path, html)
        count += 1
        print(f"  [QUARTERLY] {filename}: {first} ~ {last}")

    print(f"Total: {count} quarterly reports")
    return count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Periodic Market Summary generator")
    parser.add_argument("year", nargs="?", type=int, default=2026,
                        help="대상 연도 (기본 2026)")
    parser.add_argument("--only", choices=["weekly", "monthly", "quarterly", "all"],
                        default="all", help="생성 범위 (기본 all)")
    parser.add_argument("--quarter", type=int, choices=[1, 2, 3, 4], default=None,
                        help="분기 한정 (--only quarterly 와 함께 사용)")
    parser.add_argument("--skip-index", action="store_true",
                        help="generate_index 갱신 스킵")
    args = parser.parse_args()

    if args.only in ("all", "weekly"):
        print("=== Weekly Reports ===")
        generate_weekly_reports(args.year)

    if args.only in ("all", "monthly"):
        print("\n=== Monthly Reports ===")
        generate_monthly_reports(args.year)

    if args.only in ("all", "quarterly"):
        print("\n=== Quarterly Reports ===")
        generate_quarterly_reports(args.year, only_quarter=args.quarter)

    if not args.skip_index:
        generate_index()
    print("\nDone!")
