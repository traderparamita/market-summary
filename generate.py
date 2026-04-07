#!/usr/local/bin/python3.12
"""
Daily Market Summary Report Generator
- yfinance로 글로벌 시장 데이터 수집
- HTML 보고서 자동 생성
"""

import yfinance as yf
import FinanceDataReader as fdr
import datetime as dt
import json
import os
import requests

# ── Config ──────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# yfinance 지수 데이터 누락 시 FinanceDataReader로 보완
FDR_FALLBACK = {
    "^KS11":  "KS11",    # KOSPI
    "^KQ11":  "KQ11",    # KOSDAQ
    "^N225":  "N225",    # Nikkei225
    "^HSI":   "HSI",     # Hang Seng
    "000001.SS": "SSEC", # Shanghai
}

# 수집 대상 티커
TICKERS = {
    # Equity indices
    "equity": {
        "KOSPI":    "^KS11",
        "KOSDAQ":   "^KQ11",
        "S&P500":   "^GSPC",
        "NASDAQ":   "^IXIC",
        "Russell2K": "^RUT",
        "STOXX50":  "^STOXX50E",
        "DAX":      "^GDAXI",
        "CAC40":    "^FCHI",
        "FTSE100":  "^FTSE",
        "Nikkei225":"^N225",
        "Shanghai": "000001.SS",
        "HSI":      "^HSI",
        "NIFTY50":  "^NSEI",
    },
    # Bonds (yield proxies via ETFs + treasury rates)
    "bond": {
        "US 2Y":    "^IRX",   # 13-week proxy; 실제는 아래 별도 처리
        "US 10Y":   "^TNX",
        "US 30Y":   "^TYX",
        "TLT":      "TLT",    # 20+Y Treasury ETF
        "HYG":      "HYG",    # High Yield
        "LQD":      "LQD",    # Investment Grade
        "EMB":      "EMB",    # EM Bond
    },
    # FX
    "fx": {
        "DXY":      "DX-Y.NYB",
        "USD/KRW":  "KRW=X",
        "EUR/USD":  "EURUSD=X",
        "USD/JPY":  "JPY=X",
        "USD/CNY":  "CNY=X",
        "AUD/USD":  "AUDUSD=X",
        "GBP/USD":  "GBPUSD=X",
    },
    # Commodities
    "commodity": {
        "WTI":      "CL=F",
        "Brent":    "BZ=F",
        "Gold":     "GC=F",
        "Silver":   "SI=F",
        "Copper":   "HG=F",
        "Nat Gas":  "NG=F",
    },
    # Volatility / Risk
    "risk": {
        "VIX":      "^VIX",
        "VKOSPI":   "^KS11V",  # fallback 처리 필요
    },
    # Major stocks
    "stocks": {
        "NVIDIA":   "NVDA",
        "Broadcom": "AVGO",
        "Alphabet": "GOOGL",
        "Amazon":   "AMZN",
        "META":     "META",
        "Apple":    "AAPL",
        "Microsoft":"MSFT",
        "Tesla":    "TSLA",
        "TSMC":     "TSM",
        "Samsung":  "005930.KS",
    },
}


def fetch_data(end_date=None):
    """yfinance로 전체 데이터 수집, dict 반환. end_date: 'YYYY-MM-DD' or None(최신)"""
    all_tickers = {}
    for cat, items in TICKERS.items():
        for name, ticker in items.items():
            all_tickers[f"{cat}|{name}"] = ticker

    symbols = list(all_tickers.values())
    print(f"Fetching {len(symbols)} tickers...")
    if end_date:
        end_dt = dt.datetime.strptime(end_date, "%Y-%m-%d") + dt.timedelta(days=1)
        start_dt = end_dt - dt.timedelta(days=200)
        raw = yf.download(symbols, start=start_dt.strftime("%Y-%m-%d"), end=end_dt.strftime("%Y-%m-%d"),
                          interval="1d", group_by="ticker", threads=True)
    else:
        raw = yf.download(symbols, period="6mo", interval="1d", group_by="ticker", threads=True)

    today = dt.date.today()
    target = dt.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    result = {}

    def calc_metrics(df, ref_date):
        """DataFrame에서 지표 계산."""
        df = df.dropna(subset=["Close"])
        if df.empty:
            return None

        last_date = df.index[-1].date() if hasattr(df.index[-1], 'date') else df.index[-1]
        close = float(df.iloc[-1]["Close"])

        # 해당 시장이 휴일이었는지 판단
        is_holiday = last_date < ref_date

        daily_chg = 0.0
        if not is_holiday and len(df) >= 2:
            prev = float(df.iloc[-2]["Close"])
            daily_chg = (close - prev) / prev * 100 if prev else 0

        weekly_chg = 0.0
        if len(df) >= 6:
            w = float(df.iloc[-6]["Close"])
            weekly_chg = (close - w) / w * 100 if w else 0

        monthly_chg = 0.0
        if len(df) >= 23:
            m = float(df.iloc[-23]["Close"])
            monthly_chg = (close - m) / m * 100 if m else 0

        ytd_chg = 0.0
        yr_start = df[df.index.year == ref_date.year]
        if not yr_start.empty:
            y = float(yr_start.iloc[0]["Close"])
            ytd_chg = (close - y) / y * 100 if y else 0

        spark = []
        tail = df.tail(20)
        if not tail.empty:
            first_val = float(tail.iloc[0]["Close"])
            spark = [round((float(r["Close"]) / first_val - 1) * 100, 2) for _, r in tail.iterrows()]

        return {
            "close": close,
            "date": str(last_date),
            "daily": round(daily_chg, 2),
            "weekly": round(weekly_chg, 2),
            "monthly": round(monthly_chg, 2),
            "ytd": round(ytd_chg, 2),
            "spark": spark,
            "holiday": is_holiday,
            "holiday_note": "" if not is_holiday else "Holiday",
        }

    for key, ticker in all_tickers.items():
        cat, name = key.split("|")
        try:
            if len(symbols) == 1:
                df = raw
            else:
                df = raw[ticker] if ticker in raw.columns.get_level_values(0) else None

            metrics = None
            if df is not None and not df.empty:
                df = df.dropna(subset=["Close"])
                metrics = calc_metrics(df, target) if not df.empty else None

            # Fallback: yfinance 데이터가 없거나 휴일이면 FDR로 보완
            if (metrics is None or metrics["holiday"]) and ticker in FDR_FALLBACK:
                fdr_code = FDR_FALLBACK[ticker]
                try:
                    fdr_start = (target - dt.timedelta(days=200)).strftime("%Y-%m-%d")
                    fdr_end = (target + dt.timedelta(days=1)).strftime("%Y-%m-%d")
                    fdr_df = fdr.DataReader(fdr_code, fdr_start, fdr_end)
                    if not fdr_df.empty:
                        fdr_metrics = calc_metrics(fdr_df, target)
                        if fdr_metrics and not fdr_metrics["holiday"]:
                            metrics = fdr_metrics
                            print(f"  [FDR] {name}: {fdr_metrics['close']:.2f} ({fdr_metrics['daily']:+.2f}%) via {fdr_code}")
                except Exception as fe:
                    print(f"  [FDR WARN] {name}: {fe}")

            if metrics is None:
                continue

            if cat not in result:
                result[cat] = {}

            result[cat][name] = metrics
        except Exception as e:
            print(f"  [WARN] {name} ({ticker}): {e}")

    # ── 한국 금리: 한국은행 ECOS API ──
    kr_rates = fetch_kr_rates(end_date)
    if kr_rates:
        if "bond" not in result:
            result["bond"] = {}
        result["bond"].update(kr_rates)

    return result


def fetch_kr_rates(end_date=None):
    """한국은행 ECOS API에서 한국 금리 데이터 수집"""
    BOK_API_KEY = os.environ.get("BOK_API_KEY", "sample")
    BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
    STAT_CODE = "817Y002"  # 시장금리(일별)

    items = {
        "KR CD 91D":  "010502000",
        "KR 3Y":      "010200000",
        "KR 5Y":      "010200002",
        "KR 10Y":     "010200001",
        "KR 30Y":     "010200003",
    }

    ref_date = dt.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else dt.date.today()
    is_sample = (BOK_API_KEY == "sample")
    max_rows = 5 if is_sample else 200
    lookback = 10 if is_sample else 200
    start = (ref_date - dt.timedelta(days=lookback)).strftime("%Y%m%d")
    end = ref_date.strftime("%Y%m%d")

    result = {}
    for name, item_code in items.items():
        try:
            url = f"{BASE_URL}/{BOK_API_KEY}/json/kr/1/{max_rows}/{STAT_CODE}/D/{start}/{end}/{item_code}"
            resp = requests.get(url, timeout=10)
            data = resp.json()

            if "RESULT" in data and "ERROR" in data["RESULT"].get("CODE", ""):
                print(f"  [BOK] {name}: API error - {data['RESULT']['MESSAGE'][:80]}")
                continue

            rows = data.get("StatisticSearch", {}).get("row", [])
            if not rows:
                continue

            valid = [(r["TIME"], float(r["DATA_VALUE"])) for r in rows if r.get("DATA_VALUE")]
            if not valid:
                continue

            close = valid[-1][1]
            date_str = valid[-1][0]
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            daily_chg = 0.0
            if len(valid) >= 2:
                daily_chg = (close - valid[-2][1]) / valid[-2][1] * 100

            weekly_chg = 0.0
            if len(valid) >= 5:
                weekly_chg = (close - valid[-5][1]) / valid[-5][1] * 100

            # sample 키에서는 월간/YTD 계산 불가
            monthly_chg = 0.0
            ytd_chg = 0.0
            if not is_sample:
                if len(valid) >= 23:
                    monthly_chg = (close - valid[-23][1]) / valid[-23][1] * 100
                yr_vals = [(t, v) for t, v in valid if t[:4] == str(today.year)]
                if yr_vals:
                    ytd_chg = (close - yr_vals[0][1]) / yr_vals[0][1] * 100

            spark_vals = [v for _, v in valid]
            first = spark_vals[0] if spark_vals else 1
            spark = [round((v / first - 1) * 100, 2) for v in spark_vals]

            result[name] = {
                "close": close,
                "date": date_fmt,
                "daily": round(daily_chg, 2),
                "weekly": round(weekly_chg, 2),
                "monthly": round(monthly_chg, 2),
                "ytd": round(ytd_chg, 2),
                "spark": spark,
            }
            print(f"  [BOK] {name}: {close}% ({date_fmt})")
        except Exception as e:
            print(f"  [WARN] BOK {name}: {e}")

    return result


def fmt(val, decimals=2):
    if abs(val) >= 1000:
        return f"{val:,.{decimals}f}"
    return f"{val:.{decimals}f}"

def chg_class(val):
    return "up" if val > 0 else ("down" if val < 0 else "flat")

def chg_sign(val):
    return f"+{val:.2f}%" if val > 0 else f"{val:.2f}%"

def heat_color(val):
    """변동폭에 따른 배경색 (라이트 테마용)"""
    if val >= 3:    return "#c6f6d5"
    if val >= 1.5:  return "#d4edda"
    if val >= 0.5:  return "#e8f5e9"
    if val > 0:     return "#f1f8f4"
    if val == 0:    return "#f7f8fa"
    if val > -0.5:  return "#fef2f2"
    if val > -1.5:  return "#fde8e8"
    if val > -3:    return "#fbd5d5"
    return "#f8b4b4"

def heat_text(val):
    if val >= 1.5:  return "#065f46"
    if val > 0:     return "#047857"
    if val == 0:    return "#6b7280"
    if val > -1.5:  return "#b91c1c"
    return "#7f1d1d"

def spark_svg(data, w=80, h=24, color="#3b6ee6"):
    """미니 SVG 스파크라인"""
    if not data or len(data) < 2:
        return ""
    mn, mx = min(data), max(data)
    rng = mx - mn if mx != mn else 1
    pts = []
    step = w / (len(data) - 1)
    for i, v in enumerate(data):
        x = round(i * step, 1)
        y = round(h - (v - mn) / rng * (h - 2) - 1, 1)
        pts.append(f"{x},{y}")
    last_y = round(h - (data[-1] - mn) / rng * (h - 2) - 1, 1)
    # 마지막 값이 양이면 초록, 음이면 빨강
    end_color = "#0d9b6a" if data[-1] >= 0 else "#d9304f"
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        f'<circle cx="{round((len(data)-1)*step,1)}" cy="{last_y}" r="2.5" fill="{end_color}"/>'
        f'</svg>'
    )


def generate_html(data):
    """데이터로 HTML 보고서 생성"""

    dates = [item["date"] for cat in data.values() for item in cat.values()]
    report_date = max(dates) if dates else str(dt.date.today())
    report_dt = dt.datetime.strptime(report_date, "%Y-%m-%d")
    day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][report_dt.weekday()]

    eq = data.get("equity", {})
    bd = data.get("bond", {})
    fx = data.get("fx", {})
    cm = data.get("commodity", {})
    rk = data.get("risk", {})
    st = data.get("stocks", {})

    # === 히트맵 행 생성 ===
    def heatmap_row(name, d, show_dollar=False):
        close = d["close"]
        is_hol = d.get("holiday", False)
        hol_note = d.get("holiday_note", "")

        if show_dollar:
            close_str = f"${fmt(close)}" if close < 10000 else f"${close:,.0f}"
        else:
            close_str = fmt(close, 0) if close > 100 else fmt(close, 2)

        # 휴일이면 이름 옆에 표시
        name_display = name
        if is_hol:
            name_display = f'{name} <span style="font-size:10px;color:var(--warn);font-weight:400;">(Holiday)</span>'

        spark = spark_svg(d.get("spark", []))
        cells = ""
        for period in ["daily", "weekly", "monthly", "ytd"]:
            v = d[period]
            if is_hol and period == "daily":
                # 휴일: 전일 종가 유지, 0.00%, 회색 배경
                cells += f'<td class="heat-cell" style="background:#f7f8fa;color:#7c8298">0.00%</td>'
            else:
                bg = heat_color(v)
                tc = heat_text(v)
                cells += f'<td class="heat-cell" style="background:{bg};color:{tc}">{chg_sign(v)}</td>'
        return f"""<tr>
          <td class="name-cell">{name_display}</td>
          <td class="close-cell">{close_str}</td>
          <td class="spark-cell">{spark}</td>
          {cells}
        </tr>"""

    # === 주요 무버 (daily 기준 상위/하위) ===
    all_items = [(n, d) for cat in [eq, st, cm, fx] for n, d in cat.items()]
    sorted_by_daily = sorted(all_items, key=lambda x: x[1]["daily"], reverse=True)
    top3 = sorted_by_daily[:3]
    bottom3 = sorted_by_daily[-3:]

    # === VIX 레벨 판정 ===
    vix = rk.get("VIX", {})
    vix_val = vix.get("close", 0)
    if vix_val >= 30:
        vix_label, vix_color = "Extreme Fear", "#d9304f"
    elif vix_val >= 20:
        vix_label, vix_color = "Elevated", "#d48b07"
    elif vix_val >= 15:
        vix_label, vix_color = "Normal", "#7c8298"
    else:
        vix_label, vix_color = "Complacent", "#0d9b6a"

    # === HTML 조립 ===
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Summary | {report_date}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --card2:#f0f1f6;
  --border:#e0e3ed; --text:#2d3148; --muted:#7c8298;
  --accent:#3b6ee6; --accent2:#6b5ce7;
  --up:#0d9b6a; --down:#d9304f; --warn:#d48b07;
  --gold:#b8860b; --oil:#d35400;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Noto Sans KR',-apple-system,sans-serif;
  background:var(--bg);color:var(--text);
  line-height:1.65;padding:24px;max-width:1360px;margin:0 auto;
}}

/* ── Header ── */
.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px;padding-bottom:20px;border-bottom:2px solid var(--border)}}
.header-left h1{{font-size:26px;font-weight:700;color:#1a1d2e;margin-bottom:2px}}
.header-left .date{{font-size:13px;color:var(--muted);letter-spacing:1px}}
.header-right{{display:flex;gap:20px;align-items:center}}
.mood-badge{{display:flex;align-items:center;gap:8px;padding:8px 18px;border-radius:24px;font-size:13px;font-weight:600}}

/* ── KPI Strip ── */
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:28px}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.kpi-label{{font-size:11px;color:var(--muted);font-weight:500;margin-bottom:1px}}
.kpi-value{{font-size:18px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}
.kpi-chg{{font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.up{{color:var(--up)}}.down{{color:var(--down)}}.flat{{color:var(--muted)}}

/* ── Top Movers ── */
.movers-row{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
.movers-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 20px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.movers-card h3{{font-size:13px;color:var(--muted);font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px}}
.mover-item{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #f0f1f5}}
.mover-item:last-child{{border:none}}
.mover-name{{font-size:13px;font-weight:500}}
.mover-val{{font-size:15px;font-weight:700;font-family:'JetBrains Mono',monospace}}

/* ── Heatmap Table ── */
.heatmap-section{{margin-bottom:28px}}
.heatmap-section h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.heatmap-section h2 .badge{{font-size:11px;padding:2px 8px;border-radius:12px;background:var(--card2);color:var(--muted);font-weight:500}}
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

/* ── Charts ── */
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
.chart-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.chart-card .title{{font-size:13px;color:var(--muted);font-weight:600;margin-bottom:12px}}
.chart-box{{position:relative;height:260px}}

/* ── Risk ── */
.risk-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:28px}}
.risk-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.risk-card .label{{font-size:12px;color:var(--muted);margin-bottom:4px}}
.risk-card .value{{font-size:28px;font-weight:700;font-family:'JetBrains Mono',monospace}}
.risk-card .desc{{font-size:11px;font-weight:600;margin-top:2px}}
.risk-card .bar-track{{height:6px;background:#ecedf2;border-radius:3px;margin-top:8px;overflow:hidden}}
.risk-card .bar-fill{{height:100%;border-radius:3px}}

/* ── Tabs ── */
.tab-bar{{display:flex;gap:0;margin-bottom:28px;border-bottom:2px solid var(--border)}}
.tab-btn{{padding:12px 28px;font-size:14px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s}}
.tab-btn:hover{{color:var(--text)}}
.tab-btn.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.tab-panel{{display:none}}
.tab-panel.active{{display:block}}

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

.footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:40px;padding-top:20px;border-top:1px solid var(--border)}}

@media(max-width:900px){{
  .session-grid,.insight-grid,.chart-grid,.movers-row{{grid-template-columns:1fr}}
  .causal-chain{{flex-direction:column}}.cause-arrow{{transform:rotate(90deg);padding:4px 0}}
  .af-map{{grid-template-columns:1fr}}.risk-items{{grid-template-columns:1fr}}
}}

</style>
</head>
<body>

<!-- ══ HEADER ══ -->
<div class="header">
  <div class="header-left">
    <h1>Daily Market Summary</h1>
    <div class="date">{day_name}, {report_date}</div>
  </div>
  <div class="header-right">
    <div class="mood-badge" style="background:{'#fef2f2' if vix_val>=20 else '#f0fdf4'};color:{vix_color};border:1px solid {vix_color}33">
      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{vix_color}"></span>
      VIX {vix_val:.1f} &mdash; {vix_label}
    </div>
  </div>
</div>

<!-- ══ TABS ══ -->
<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('data')">Data Dashboard</button>
  <button class="tab-btn" onclick="switchTab('story')">Market Story</button>
</div>

<!-- ══════ TAB 1: DATA ══════ -->
<div id="tab-data" class="tab-panel active">

<div class="kpi-strip">
"""
    # KPI 목록
    kpi_list = [
        ("KOSPI", eq.get("KOSPI")),
        ("S&P500", eq.get("S&P500")),
        ("NASDAQ", eq.get("NASDAQ")),
        ("Nikkei", eq.get("Nikkei225")),
        ("US 10Y", bd.get("US 10Y")),
        ("USD/KRW", fx.get("USD/KRW")),
        ("WTI", cm.get("WTI")),
        ("Gold", cm.get("Gold")),
    ]
    for label, d in kpi_list:
        if not d:
            continue
        c = d["close"]
        if label in ["WTI", "Gold"]:
            v = f"${fmt(c)}"
        elif label == "US 10Y":
            v = f"{c:.2f}%"
        elif c > 100:
            v = fmt(c, 0)
        else:
            v = fmt(c, 2)
        cls = chg_class(d["daily"])
        html += f"""  <div class="kpi">
    <div class="kpi-label">{label}</div>
    <div class="kpi-value">{v}</div>
    <div class="kpi-chg {cls}">{chg_sign(d['daily'])}</div>
  </div>\n"""
    html += "</div>\n"

    # ── Top/Bottom Movers ──
    html += '<div class="movers-row">\n'
    html += '<div class="movers-card"><h3>Top Gainers</h3>\n'
    for name, d in top3:
        cls = chg_class(d["daily"])
        html += f'<div class="mover-item"><span class="mover-name">{name}</span><span class="mover-val {cls}">{chg_sign(d["daily"])}</span></div>\n'
    html += '</div>\n<div class="movers-card"><h3>Top Losers</h3>\n'
    for name, d in bottom3:
        cls = chg_class(d["daily"])
        html += f'<div class="mover-item"><span class="mover-name">{name}</span><span class="mover-val {cls}">{chg_sign(d["daily"])}</span></div>\n'
    html += '</div>\n</div>\n'

    # ── 이미지 순서에 맞는 고정 정렬 ──
    EQUITY_ORDER = [
        "KOSPI", "KOSDAQ",                                    # 한국
        "S&P500", "NASDAQ", "Russell2K",                      # 미국
        "STOXX50", "FTSE100", "DAX", "CAC40",                 # 유럽
        "Shanghai", "HSI",                                     # 중국
        "Nikkei225",                                           # 일본
        "NIFTY50",                                             # 인도
    ]
    BOND_RATE_ORDER = [
        "KR CD 91D", "KR 3Y", "KR 5Y", "KR 10Y", "KR 30Y",  # 한국
        "US 2Y", "US 10Y", "US 30Y",                          # 미국
    ]
    BOND_ETF_ORDER = ["TLT", "LQD", "HYG", "EMB"]
    FX_ORDER = ["DXY", "USD/KRW", "EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY", "USD/CNY"]
    CM_ORDER = ["WTI", "Brent", "Gold", "Silver", "Copper", "Nat Gas"]
    ST_ORDER = [
        "NVIDIA", "Broadcom", "Alphabet", "Amazon", "META",
        "Apple", "Microsoft", "Tesla", "TSMC", "Samsung",
    ]

    def ordered(cat, order):
        """order 리스트 순서대로 정렬, 없는 항목은 뒤에 추가"""
        idx = {name: i for i, name in enumerate(order)}
        return sorted(cat.items(), key=lambda x: idx.get(x[0], 999))

    bond_etfs = {"TLT", "HYG", "LQD", "EMB"}
    bd_rates = {k: v for k, v in bd.items() if k not in bond_etfs}
    bd_etf = {k: v for k, v in bd.items() if k in bond_etfs}

    # ── Heatmap Tables ──
    sections = [
        ("Equity",        eq,       False, EQUITY_ORDER),
        ("Bonds & Rates", bd_rates, False, BOND_RATE_ORDER),
        ("Bond ETF",      bd_etf,   True,  BOND_ETF_ORDER),
        ("FX",            fx,       False, FX_ORDER),
        ("Commodities",   cm,       True,  CM_ORDER),
        ("Major Stocks",  st,       True,  ST_ORDER),
    ]
    for title, cat, dollar, order in sections:
        if not cat:
            continue
        items = ordered(cat, order)
        html += f"""<div class="heatmap-section">
<h2>{title} <span class="badge">{len(items)}</span></h2>
<table class="heatmap">
<thead><tr><th>Name</th><th>Close</th><th>20D Trend</th><th>Daily</th><th>Weekly</th><th>Monthly</th><th>YTD</th></tr></thead>
<tbody>\n"""
        for name, d in items:
            html += heatmap_row(name, d, dollar)
        html += "</tbody></table></div>\n"

    # ── Risk Dashboard ──
    html += '<div class="heatmap-section"><h2>Risk Dashboard</h2></div>\n<div class="risk-strip">\n'
    # VIX
    vix_pct = min(vix_val / 50 * 100, 100) if vix_val else 0
    html += f"""<div class="risk-card">
  <div class="label">VIX</div>
  <div class="value" style="color:{vix_color}">{vix_val:.1f}</div>
  <div class="desc" style="color:{vix_color}">{vix_label}</div>
  <div class="bar-track"><div class="bar-fill" style="width:{vix_pct:.0f}%;background:{vix_color}"></div></div>
</div>\n"""
    # 기타 리스크 지표
    for name, d in rk.items():
        if name == "VIX":
            continue
        html += f"""<div class="risk-card">
  <div class="label">{name}</div>
  <div class="value">{d['close']:.1f}</div>
  <div class="desc {chg_class(d['daily'])}">{chg_sign(d['daily'])}</div>
</div>\n"""
    # 채권 ETF도 리스크에 추가
    for name in ["HYG", "EMB"]:
        if name in bd:
            d = bd[name]
            html += f"""<div class="risk-card">
  <div class="label">{name}</div>
  <div class="value">{d['close']:.1f}</div>
  <div class="desc {chg_class(d['daily'])}">{chg_sign(d['daily'])}</div>
</div>\n"""
    html += '</div>\n'

    # ── Charts ──
    eq_sorted_names = [n for n, _ in sorted(eq.items(), key=lambda x: x[1]["daily"], reverse=True)]
    eq_sorted_daily = [eq[n]["daily"] for n in eq_sorted_names]
    st_sorted_names = [n for n, _ in sorted(st.items(), key=lambda x: x[1]["daily"], reverse=True)]
    st_sorted_daily = [st[n]["daily"] for n in st_sorted_names]
    cm_names = list(cm.keys())
    cm_ytd = [cm[n]["ytd"] for n in cm_names]
    fx_names = list(fx.keys())
    fx_daily = [fx[n]["daily"] for n in fx_names]

    # Scatter: daily vs weekly (cross-asset)
    scatter_data = []
    for cat_items, cat_label in [(eq, "equity"), (st, "stocks"), (cm, "commodity")]:
        for name, d in cat_items.items():
            scatter_data.append({"x": d["weekly"], "y": d["daily"], "label": name, "cat": cat_label})

    html += f"""
<!-- ══ CHARTS ══ -->
<div class="chart-grid">
  <div class="chart-card">
    <div class="title">Equity: Daily Change (%)</div>
    <div class="chart-box"><canvas id="eqChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="title">Stocks: Daily Change (%)</div>
    <div class="chart-box"><canvas id="stChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="title">Daily vs Weekly (Cross-Asset)</div>
    <div class="chart-box"><canvas id="scatterChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="title">Commodity YTD (%)</div>
    <div class="chart-box"><canvas id="cmChart"></canvas></div>
  </div>
</div>


</div><!-- /tab-data -->

<!-- ══════ TAB 2: STORY ══════ -->
<div id="tab-story" class="tab-panel">

<!-- STORY_CONTENT_PLACEHOLDER -->

</div><!-- /tab-story -->

<div class="footer">Daily Market Summary | yfinance auto-generated | {report_date}</div>

<script>
function switchTab(id){{
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  event.target.classList.add('active');
  // 차트 리사이즈 (탭 전환 후)
  if(id==='data') setTimeout(()=>window.dispatchEvent(new Event('resize')),50);
}}
Chart.defaults.color='#7c8298';
Chart.defaults.borderColor='#e8eaf0';
Chart.defaults.font.family="'Noto Sans KR',sans-serif";
Chart.defaults.font.size=11;
const UP='#0d9b6a',DN='#d9304f',AC='#3b6ee6',WN='#d48b07',MU='#b0b4c4',GD='#b8860b';
function bc(d){{return d.map(v=>v>0?UP:v<0?DN:MU)}}

// Equity bar
new Chart(document.getElementById('eqChart'),{{
  type:'bar',
  data:{{labels:{json.dumps(eq_sorted_names)},datasets:[{{data:{json.dumps(eq_sorted_daily)},backgroundColor:bc({json.dumps(eq_sorted_daily)}),borderRadius:4,barPercentage:.6}}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{weight:'600',size:11}}}}}}}}}}
}});

// Stocks bar
new Chart(document.getElementById('stChart'),{{
  type:'bar',
  data:{{labels:{json.dumps(st_sorted_names)},datasets:[{{data:{json.dumps(st_sorted_daily)},backgroundColor:bc({json.dumps(st_sorted_daily)}),borderRadius:4,barPercentage:.6}}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},y:{{grid:{{display:false}},ticks:{{font:{{weight:'600',size:11}}}}}}}}}}
}});

// Scatter: daily vs weekly
new Chart(document.getElementById('scatterChart'),{{
  type:'scatter',
  data:{{
    datasets:[
      {{label:'Equity',data:{json.dumps([s for s in scatter_data if s['cat']=='equity'])},backgroundColor:AC+'aa',pointRadius:6}},
      {{label:'Stocks',data:{json.dumps([s for s in scatter_data if s['cat']=='stocks'])},backgroundColor:'#6b5ce7aa',pointRadius:6}},
      {{label:'Commodity',data:{json.dumps([s for s in scatter_data if s['cat']=='commodity'])},backgroundColor:WN+'aa',pointRadius:6}}
    ]
  }},
  options:{{
    responsive:true,maintainAspectRatio:false,
    plugins:{{
      legend:{{position:'top',labels:{{boxWidth:8}}}},
      tooltip:{{callbacks:{{label:c=>c.raw.label+' (W:'+c.raw.x.toFixed(1)+'%, D:'+c.raw.y.toFixed(1)+'%)'}}}}
    }},
    scales:{{
      x:{{title:{{display:true,text:'Weekly %',color:'#7c8298'}},grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}},
      y:{{title:{{display:true,text:'Daily %',color:'#7c8298'}},grid:{{color:'#ecedf2'}},ticks:{{callback:v=>v+'%'}}}}
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

    return html, report_date


def prev_business_day(ref=None):
    """한국 영업일 기준 전 영업일 (주말 제외, 공휴일은 미반영). KST 기준."""
    if ref:
        d = ref
    else:
        # UTC 환경에서도 KST(+9) 기준으로 오늘 날짜 계산
        kst = dt.timezone(dt.timedelta(hours=9))
        d = dt.datetime.now(kst).date()
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:  # 토=5, 일=6
        d -= dt.timedelta(days=1)
    return d


def generate_index():
    """일간/주간/월간 탭이 있는 index.html 생성"""
    import glob

    # ── 일간 보고서 수집 ──
    months = {}
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "????-??", "????-??-??.html")), reverse=True):
        fname = os.path.basename(path)
        date = fname.replace(".html", "")
        month = date[:7]
        try:
            d = dt.datetime.strptime(date, "%Y-%m-%d")
            day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d.weekday()]
        except:
            day_name = ""
        if month not in months:
            months[month] = []
        months[month].append((date, day_name))

    sorted_months = sorted(months.keys(), reverse=True)
    latest_month = sorted_months[0] if sorted_months else ""

    daily_month_btns = ""
    daily_panels = ""
    for m in sorted_months:
        active = " active" if m == latest_month else ""
        label = dt.datetime.strptime(m, "%Y-%m").strftime("%Y %b")
        daily_month_btns += f'      <button class="month-btn{active}" onclick="showSub(\'daily\',\'{m}\')">{label}</button>\n'
        items = ""
        for date, day in months[m]:
            items += f'          <li><a href="{m}/{date}.html">{date} ({day})</a></li>\n'
        daily_panels += f'      <div class="sub-panel{active}" id="daily-{m}"><ul>\n{items}      </ul></div>\n'

    # ── 주간 보고서 수집 (월별 그룹) ──
    weekly_by_month = {}  # {"2026-01": [("2026-W02", "Jan 5 ~ Jan 9"), ...]}
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "weekly", "*.html")), reverse=True):
        fname = os.path.basename(path)
        week_label = fname.replace(".html", "")  # e.g. "2026-W02"
        try:
            year = int(week_label[:4])
            week_num = int(week_label.split("W")[1])
            # ISO week → 해당 주의 월요일 날짜로 월 판단
            monday = dt.datetime.strptime(f"{year}-W{week_num:02d}-1", "%Y-W%W-%w").date()
            month_key = monday.strftime("%Y-%m")
        except:
            month_key = week_label[:7]
        if month_key not in weekly_by_month:
            weekly_by_month[month_key] = []
        weekly_by_month[month_key].append((week_label, fname))

    sorted_weekly_months = sorted(weekly_by_month.keys(), reverse=True)
    latest_weekly_month = sorted_weekly_months[0] if sorted_weekly_months else ""

    weekly_month_btns = ""
    weekly_panels = ""
    for m in sorted_weekly_months:
        active = " active" if m == latest_weekly_month else ""
        label = dt.datetime.strptime(m, "%Y-%m").strftime("%Y %b")
        weekly_month_btns += f'      <button class="month-btn{active}" onclick="showSub(\'weekly\',\'{m}\')">{label}</button>\n'
        items = ""
        for week_label, fname in weekly_by_month[m]:
            items += f'          <li><a href="weekly/{fname}">{week_label}</a></li>\n'
        weekly_panels += f'      <div class="sub-panel{active}" id="weekly-{m}"><ul>\n{items}      </ul></div>\n'

    # ── 월간 보고서 수집 ──
    monthly_items = ""
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "monthly", "*.html")), reverse=True):
        fname = os.path.basename(path)
        label = fname.replace(".html", "")
        try:
            d = dt.datetime.strptime(label, "%Y-%m")
            label = d.strftime("%Y %B")
        except:
            pass
        monthly_items += f'      <li><a href="monthly/{fname}">{label}</a></li>\n'

    index_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Summary</title>
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<meta property="og:title" content="Daily Market Summary">
<meta property="og:description" content="매일 자동 생성되는 글로벌 시장 요약 보고서">
<meta property="og:image" content="https://traderparamita.github.io/market-summary/favicon.svg">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&family=JetBrains+Mono:wght@400&display=swap');
  body {{ font-family:'Noto Sans KR',sans-serif; background:#f4f5f9; color:#2d3148; padding:40px 24px; max-width:720px; margin:0 auto; }}
  h1 {{ font-size:28px; font-weight:700; margin-bottom:4px; }}
  .sub {{ font-size:14px; color:#7c8298; margin-bottom:24px; }}
  .main-tabs {{ display:flex; gap:0; margin-bottom:24px; border-bottom:2px solid #e0e3ed; }}
  .main-tab {{
    padding:10px 24px; font-size:14px; font-weight:600; color:#7c8298; background:none;
    border:none; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px;
    transition:all .2s; font-family:inherit;
  }}
  .main-tab:hover {{ color:#2d3148; }}
  .main-tab.active {{ color:#3b6ee6; border-bottom-color:#3b6ee6; }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}
  .month-bar {{ display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }}
  .month-btn {{
    padding:6px 14px; border:1px solid #e0e3ed; border-radius:16px;
    background:#fff; color:#7c8298; font-size:12px; font-weight:600;
    cursor:pointer; transition:all .15s; font-family:inherit;
  }}
  .month-btn:hover {{ border-color:#3b6ee6; color:#3b6ee6; }}
  .month-btn.active {{ background:#3b6ee6; color:#fff; border-color:#3b6ee6; }}
  .sub-panel {{ display:none; }}
  .sub-panel.active {{ display:block; }}
  ul {{ list-style:none; padding:0; }}
  li {{ margin-bottom:8px; }}
  li a {{
    display:block; padding:12px 18px; background:#fff; border:1px solid #e0e3ed;
    border-radius:10px; text-decoration:none; color:#2d3148; font-size:14px;
    font-weight:500; transition:all .15s; box-shadow:0 1px 3px rgba(0,0,0,0.04);
    font-family:'JetBrains Mono','Noto Sans KR',monospace;
  }}
  li a:hover {{ border-color:#3b6ee6; color:#3b6ee6; transform:translateX(4px); }}
</style>
</head>
<body>
  <h1>Market Summary</h1>
  <p class="sub">Auto-generated market reports</p>

  <div class="main-tabs">
    <button class="main-tab active" onclick="showTab('daily')">Daily</button>
    <button class="main-tab" onclick="showTab('weekly')">Weekly</button>
    <button class="main-tab" onclick="showTab('monthly')">Monthly</button>
  </div>

  <div id="tab-daily" class="tab-content active">
    <div class="month-bar">
{daily_month_btns}    </div>
{daily_panels}
  </div>

  <div id="tab-weekly" class="tab-content">
    <div class="month-bar">
{weekly_month_btns}    </div>
{weekly_panels}
  </div>

  <div id="tab-monthly" class="tab-content">
    <ul>
{monthly_items if monthly_items else '      <li style="color:#7c8298;font-style:italic">No monthly reports yet.</li>'}
    </ul>
  </div>

  <script>
  function showTab(id) {{
    document.querySelectorAll('.tab-content').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.main-tab').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-'+id).classList.add('active');
    event.target.classList.add('active');
  }}
  function showSub(tab, key) {{
    const container = document.getElementById('tab-'+tab);
    container.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
    container.querySelectorAll('.month-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tab+'-'+key).classList.add('active');
    event.target.classList.add('active');
  }}
  </script>
</body>
</html>"""

    idx_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(idx_path, "w") as f:
        f.write(index_html)
    print(f"Index saved: {idx_path}")


def main(target_date=None):
    """target_date: 'YYYY-MM-DD' 형식. None이면 전 영업일."""
    if not target_date:
        target_date = str(prev_business_day())

    print("=== Daily Market Summary Generator ===")
    print(f"Target date: {target_date}")

    data = fetch_data(end_date=target_date)

    # 월별 폴더에 저장
    month_dir = os.path.join(OUTPUT_DIR, target_date[:7])
    os.makedirs(month_dir, exist_ok=True)

    json_path = os.path.join(month_dir, f"{target_date}_data.json")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Data saved: {json_path}")

    html, report_date = generate_html(data)

    html_path = os.path.join(month_dir, f"{report_date}.html")
    with open(html_path, "w") as f:
        f.write(html)
    print(f"Report saved: {html_path}")

    generate_index()

    return html_path


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else None
    path = main(target)
    print(f"\nDone! Open: file://{path}")
