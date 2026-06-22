#!/usr/local/bin/python3.12
"""
Daily Market Summary Report Generator
- HTML 보고서 자동 생성
- 데이터 수집은 collect_market.py 에 위임
"""

import datetime as dt
import json
import logging
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Logging setup ───────────────────────────────────────────────
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, f"market-full-{dt.date.today().strftime('%Y-%m-%d')}.log")

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

# File handler
_fh = logging.FileHandler(_log_file, encoding='utf-8')
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
_logger.addHandler(_fh)

# Console handler (stdout에만, stderr 아님)
_ch = logging.StreamHandler(sys.stdout)
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter('%(message)s'))
_logger.addHandler(_ch)

def _log(msg):
    """Step 메시지는 logger 대신 이 함수 사용 (print도 동시에 출력)"""
    _logger.info(msg)
    print(msg)

# Bump when the OG image (og-image.png) changes so that social caches (KakaoTalk,
# Slack, Facebook) refetch instead of showing the stale thumbnail.
OG_IMAGE_VERSION = "20260410-1"

# ── Data collection (collect_market.py) ─────────────────────────
from collectors.collect_market import (
    fetch_data, fetch_kr_rates, calc_metrics,
    append_to_history, build_report_data,
    HISTORY_CSV, HISTORY_CSV_COLUMNS,
)

# ── Config ──────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output", "summary")
os.makedirs(OUTPUT_DIR, exist_ok=True)
HISTORY_DIR = os.path.join(os.path.dirname(__file__), "history")


from report_utils import (
    fmt, chg_class, chg_sign, heat_color, heat_text, spark_svg,
    KO_LABELS, EQUITY_ORDER, MSCI_ORDER, BOND_RATE_ORDER, BOND_ETF_ORDER,
    FX_ORDER, CM_ORDER, ST_ORDER, DATA_SOURCES,
    KR_STOCK_ORDER, US_STOCK_ORDER, ASIA_STOCK_ORDER,
    KR_STOCK_TOP_N, US_STOCK_TOP_N, ASIA_STOCK_TOP_N,
    DAILY_TAB_SPECS, extract_tab, save_story_files, inject_existing_story,
    ordered,
)


def generate_html(data):
    """데이터로 HTML 보고서 생성"""

    dates = [item["date"] for cat in data.values() for item in cat.values()]
    report_date = max(dates) if dates else str(dt.date.today())
    report_dt = dt.datetime.strptime(report_date, "%Y-%m-%d")
    ym = report_date[:7]
    day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][report_dt.weekday()]

    eq = data.get("equity", {})
    bd = data.get("bond", {})
    fx = data.get("fx", {})
    cm = data.get("commodity", {})
    rk = data.get("risk", {})
    # stocks: KR50/US50 백필분(stocks_universe.py)이 시계열에 합쳐져 있으나 dashboard
    # 노출은 ST_ORDER 화이트리스트로만 통제. 본문/검증은 build_report_data 전체 결과를 활용.
    st_all = data.get("stocks", {})
    st = {k: v for k, v in st_all.items() if k in ST_ORDER}

    # === 히트맵 행 생성 ===
    def heatmap_row(name, d, show_dollar=False, as_bp=False):
        close = d["close"]
        # data_status: "ok" | "holiday" | "stale" (legacy holiday flag fallback for old JSON)
        status = d.get("data_status")
        if status is None:
            status = "holiday" if d.get("holiday", False) else "ok"
        is_hol = (status == "holiday")
        is_stale = (status == "stale")

        if as_bp:
            close_str = f"{close * 100:.0f} bp" if "Spread" in name else f"{close:.2f}%"
        elif show_dollar:
            close_str = f"${fmt(close)}" if close < 10000 else f"${close:,.0f}"
        else:
            close_str = fmt(close, 0) if close > 100 else fmt(close, 2)

        # 한글병행표기
        ko = KO_LABELS.get(name)
        base_name = f'{ko}({name})' if ko and ko != name else name
        # 휴일/지연이면 이름 옆에 배지
        name_display = base_name
        if is_hol:
            name_display = f'{base_name} <span style="font-size:10px;color:var(--warn);font-weight:400;">(Holiday)</span>'
        elif is_stale:
            name_display = f'{base_name} <span style="font-size:10px;color:#c87f00;font-weight:400;background:#fff5e0;padding:1px 5px;border-radius:3px;">데이터 지연</span>'

        spark = spark_svg(d.get("spark", []))
        cells = ""
        for period in ["daily", "weekly", "monthly", "ytd"]:
            v = d[period]
            if (is_hol or is_stale) and period == "daily":
                # 휴일/지연: 전일 종가 유지, 0 변화, 회색 배경
                zero_txt = "0 bp" if as_bp else "0.00%"
                cells += f'<td class="heat-cell" style="background:#f7f8fa;color:#7c8298">{zero_txt}</td>'
            else:
                bg = heat_color(v)
                tc = heat_text(v)
                if as_bp:
                    # v 는 yield 의 상대 % 변화 → 절대 bp 변화로 환산
                    prev = close / (1 + v / 100) if (1 + v / 100) else close
                    bp = (close - prev) * 100
                    sign = "+" if bp > 0 else ""
                    cells += f'<td class="heat-cell" style="background:{bg};color:{tc}">{sign}{bp:.0f} bp</td>'
                else:
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
<meta name="description" content="글로벌 시장 요약 보고서 — {report_date} (Equity · Bonds · FX · Commodities · Risk)">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="icon" type="image/png" sizes="192x192" href="../favicon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="../favicon-512.png">
<link rel="apple-touch-icon" sizes="180x180" href="../apple-touch-icon.png">
<meta property="og:type" content="article">
<meta property="og:title" content="Market Summary | {report_date}">
<meta property="og:description" content="글로벌 시장 요약 보고서 — {report_date} (Equity · Bonds · FX · Commodities · Risk)">
<meta property="og:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://traderparamita.github.io/market-summary/{ym}/{report_date}.html">
<meta property="og:site_name" content="Market Summary">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Market Summary | {report_date}">
<meta name="twitter:description" content="글로벌 시장 요약 보고서 — {report_date}">
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
body{{
  font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic','맑은 고딕',-apple-system,sans-serif;
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
.session-block.europe::before{{background:linear-gradient(90deg,#F58220,#043B72)}}
.session-block.us::before{{background:linear-gradient(90deg,#043B72,#7F9FC3)}}
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
.risk-tag.high{{background:rgba(217,48,79,0.15);color:var(--down)}}.risk-tag.med{{background:rgba(212,139,7,0.15);color:var(--warn)}}.risk-tag.low{{background:rgba(45,180,100,0.15);color:#2d7d46}}

.footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:40px;padding-top:20px;border-top:1px solid var(--border)}}
.ai-disclaimer{{text-align:center;color:var(--muted);font-size:11px;margin-top:24px;padding:12px 16px;background:rgba(0,0,0,0.03);border-radius:8px;line-height:1.6}}

/* ── Macro Tab ── */
.macro-header{{background:linear-gradient(135deg,#f0f4ff,#e8edf8);border:1px solid var(--border);border-left:4px solid #043B72;border-radius:12px;padding:18px 24px;margin-bottom:20px}}
.macro-header h2{{font-size:13px;color:#043B72;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}}
.macro-header .mh-sub{{font-size:12px;color:var(--muted)}}
.macro-block{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px 24px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.macro-block h3{{font-size:15px;font-weight:700;color:#1a1d2e;margin-bottom:10px;padding-bottom:7px;border-bottom:1.5px solid var(--border)}}
.macro-block ul{{margin:0;padding-left:18px;font-size:13px;color:#2d3148;line-height:1.85}}
.macro-block li{{margin-bottom:3px}}
.macro-kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}}
.macro-kpi{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 14px;text-align:center}}
.macro-kpi-label{{font-size:11px;color:var(--muted);margin-bottom:4px}}
.macro-kpi-value{{font-size:16px;font-weight:700;color:#1a1d2e}}
.macro-kpi-sub{{font-size:11px;color:var(--muted);margin-top:2px}}
.event-table{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px}}
.event-table th{{background:#f7f8fc;font-size:12px;font-weight:600;color:var(--muted);padding:7px 10px;text-align:left;border-bottom:1px solid var(--border)}}
.event-table td{{padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#2d3148}}
.event-table tr:last-child td{{border-bottom:none}}
.imp-high{{color:var(--down);font-weight:700}}.imp-med{{color:#d47f00;font-weight:600}}.imp-low{{color:var(--muted)}}
.macro-section{{margin-bottom:32px}}
.macro-section h2{{font-size:16px;font-weight:700;color:var(--accent2);margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid var(--border)}}

/* ── Sources ── */
.sources-header{{background:linear-gradient(135deg,#eef4fb,#dde9f6);border:1px solid var(--border);border-left:4px solid #043B72;border-radius:12px;padding:24px 28px;margin-bottom:20px}}
.sources-header h2{{font-size:13px;color:#043B72;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}}
.sources-sub{{font-size:12px;color:var(--muted)}}
.sources-section{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px 22px;margin-bottom:12px}}
.sources-section h3{{font-size:14px;font-weight:700;color:#1a1d2e;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.sources-list{{list-style:none;padding-left:0;margin:0;font-size:13px;line-height:1.85}}
.sources-list li{{padding:4px 0;color:#2d3148}}
.sources-list a{{color:#043B72;text-decoration:none}}
.sources-list a:hover{{text-decoration:underline}}
.source-meta{{color:var(--muted);font-size:12px}}

/* ── CS Story ── */
.cs-hero{{background:linear-gradient(135deg,#fff5eb,#fde9d3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:24px}}
.cs-hero h2{{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}}
.cs-hero .cs-subtitle{{font-size:12px;color:var(--muted);margin-bottom:16px}}
.cs-text{{font-size:16px;color:#2d3148;line-height:1.9}}
.cs-text p{{margin-bottom:14px}}
.cs-text p:last-child{{margin-bottom:0}}
.cs-section{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px 28px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.cs-section h3{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:10px}}
.cs-section p{{font-size:15px;color:#2d3148;line-height:1.85;margin-bottom:10px}}
.cs-section p:last-child{{margin-bottom:0}}
.cs-footer{{font-size:12px;color:var(--muted);border-top:1px solid var(--border);padding-top:12px;margin-top:8px}}
.cs-funds-desc{{font-size:13px;color:var(--muted);margin-bottom:12px}}
.cs-fund-chips{{display:flex;flex-wrap:wrap;gap:8px}}
.cs-fund-chip{{display:inline-block;font-size:12px;font-weight:600;color:#6b21a8;background:#f8f0ff;border:1px solid #e9d5ff;padding:4px 12px;border-radius:16px}}
.cs-fund-chip em{{font-style:normal;font-weight:400;color:#7c8298}}

/* ── PM Story ── */
.pm-hero{{background:linear-gradient(135deg,#eef4fb,#dde9f6);border:1px solid var(--border);border-left:4px solid #043B72;border-radius:12px;padding:24px 28px;margin-bottom:20px}}
.pm-hero h2{{font-size:13px;color:#043B72;letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}}
.pm-hero .pm-subtitle{{font-size:12px;color:var(--muted);margin-bottom:14px}}
.pm-tl{{font-size:15px;color:#1a1d2e;line-height:1.8}}
.pm-tl p{{margin-bottom:8px}}
.pm-tl p:last-child{{margin-bottom:0}}
.pm-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-bottom:16px}}
.pm-section{{background:var(--card);border:1px solid var(--border);border-left:3px solid #043B72;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}}
.pm-section h3{{font-size:15px;font-weight:700;color:#043B72;margin-bottom:10px;display:flex;align-items:center;gap:8px}}
.pm-section ul{{list-style:none;padding:0;margin:0}}
.pm-section li{{font-size:13.5px;color:#2d3148;line-height:1.75;margin-bottom:6px;padding-left:12px;position:relative}}
.pm-section li::before{{content:'·';position:absolute;left:0;color:#043B72;font-weight:700}}
.pm-section li:last-child{{margin-bottom:0}}
.pm-section .pm-num{{font-weight:600;color:#1a1d2e}}
.pm-section .pm-up{{color:#d92b2b;font-weight:600}}
.pm-section .pm-dn{{color:#1a5fb4;font-weight:600}}
.pm-section .pm-note{{font-size:12px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px dashed var(--border)}}
.pm-footer{{font-size:12px;color:var(--muted);border-top:1px solid var(--border);padding-top:10px;margin-top:12px;text-align:center}}

@media(max-width:900px){{
  .session-grid,.insight-grid,.chart-grid,.movers-row{{grid-template-columns:1fr}}
  .causal-chain{{flex-direction:column}}.cause-arrow{{transform:rotate(90deg);padding:4px 0}}
  .af-map{{grid-template-columns:1fr}}.risk-items{{grid-template-columns:1fr}}
  .pm-grid{{grid-template-columns:1fr}}
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
  <button class="tab-btn active" onclick="switchTab('cs')">CS Story</button>
  <button class="tab-btn" onclick="switchTab('pm')">PM Story</button>
  <button class="tab-btn" onclick="switchTab('story')">Market Story</button>
  <button class="tab-btn" onclick="switchTab('stocks')">Stocks</button>
  <button class="tab-btn" onclick="switchTab('data')">Data Dashboard</button>
  <button class="tab-btn" onclick="switchTab('macro')">Macro &amp; Events</button>
  <button class="tab-btn" onclick="switchTab('sources')">Sources</button>
</div>

<!-- ══════ TAB 1: DATA ══════ -->
<div id="tab-data" class="tab-panel">

<div class="kpi-strip">
"""
    # KPI 목록
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
        cls = chg_class(d["daily"])
        html += f"""  <div class="kpi">
    <div class="kpi-label">{ko_label}</div>
    <div class="kpi-value">{v}</div>
    <div class="kpi-chg {cls}">{chg_sign(d['daily'])}</div>
  </div>\n"""
    html += "</div>\n"

    # ── Top/Bottom Movers ──
    html += '<div class="movers-row">\n'
    html += '<div class="movers-card"><h3>상승 Top 3</h3>\n'
    for name, d in top3:
        ko = KO_LABELS.get(name)
        disp = f'{ko}({name})' if ko and ko != name else name
        cls = chg_class(d["daily"])
        html += f'<div class="mover-item"><span class="mover-name">{disp}</span><span class="mover-val {cls}">{chg_sign(d["daily"])}</span></div>\n'
    html += '</div>\n<div class="movers-card"><h3>하락 Top 3</h3>\n'
    for name, d in bottom3:
        ko = KO_LABELS.get(name)
        disp = f'{ko}({name})' if ko and ko != name else name
        cls = chg_class(d["daily"])
        html += f'<div class="mover-item"><span class="mover-name">{disp}</span><span class="mover-val {cls}">{chg_sign(d["daily"])}</span></div>\n'
    html += '</div>\n</div>\n'

    # ── 이미지 순서에 맞는 고정 정렬 ──
    bond_etfs = {"AGG", "TLT", "HYG", "LQD", "EMB", "IEI", "SHY", "TIP"}
    bd_rates = {k: v for k, v in bd.items() if k not in bond_etfs}
    bd_etf = {k: v for k, v in bd.items() if k in bond_etfs}

    msci_names = set(MSCI_ORDER)
    eq_regional = {k: v for k, v in eq.items() if k not in msci_names}
    eq_msci = {k: v for k, v in eq.items() if k in msci_names}

    # ── Heatmap Tables ── (종목은 Stocks 탭으로 이동)
    sections = [
        ("주식(Equity)",           eq_regional, False, False, EQUITY_ORDER),
        ("MSCI 지수",              eq_msci,     False, False, MSCI_ORDER),
        ("채권·금리(Bonds & Rates)", bd_rates,  False, True,  BOND_RATE_ORDER),
        ("채권 ETF(Bond ETF)",     bd_etf,      True,  False, BOND_ETF_ORDER),
        ("환율(FX)",               fx,          False, False, FX_ORDER),
        ("원자재(Commodities)",    cm,          True,  False, CM_ORDER),
    ]
    for title, cat, dollar, as_bp, order in sections:
        if not cat:
            continue
        items = ordered(cat, order)
        src = DATA_SOURCES.get(title, "")
        src_html = f' <span class="src-tag">{src}</span>' if src else ""
        html += f"""<div class="heatmap-section">
<h2>{title} <span class="badge">{len(items)}</span>{src_html}</h2>
<table class="heatmap">
<thead><tr><th>종목</th><th>종가</th><th>20일 추이</th><th>일간</th><th>주간</th><th>월간</th><th>연초대비</th></tr></thead>
<tbody>\n"""
        for name, d in items:
            html += heatmap_row(name, d, dollar, as_bp)
        html += "</tbody></table></div>\n"

    # ── Risk Dashboard ──
    html += '<div class="heatmap-section"><h2>Risk Dashboard <span class="src-tag">yfinance · FinanceDataReader</span></h2></div>\n<div class="risk-strip">\n'
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
    eq_sorted_names = [n for n, _ in sorted(eq_regional.items(), key=lambda x: x[1]["daily"], reverse=True)]
    eq_sorted_daily = [eq_regional[n]["daily"] for n in eq_sorted_names]
    st_sorted_names = [n for n, _ in sorted(st.items(), key=lambda x: x[1]["daily"], reverse=True)]
    st_sorted_daily = [st[n]["daily"] for n in st_sorted_names]
    cm_names = list(cm.keys())
    cm_ytd = [cm[n]["ytd"] for n in cm_names]
    fx_names = list(fx.keys())
    fx_daily = [fx[n]["daily"] for n in fx_names]

    # Scatter: daily vs weekly (cross-asset)
    scatter_data = []
    for cat_items, cat_label in [(eq_regional, "equity"), (eq_msci, "msci"), (st, "stocks"), (cm, "commodity")]:
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

<!-- ══════ TAB: STOCKS ══════ -->
<div id="tab-stocks" class="tab-panel">

<!-- STOCKS_STORY_PLACEHOLDER -->

<!-- STOCKS_TABLES_PLACEHOLDER -->

</div><!-- /tab-stocks -->

<!-- ══════ TAB 2: STORY ══════ -->
<div id="tab-story" class="tab-panel">

<!-- STORY_CONTENT_PLACEHOLDER -->

</div><!-- /tab-story -->

<!-- ══════ TAB 3: CS STORY ══════ -->
<div id="tab-cs" class="tab-panel active">

<!-- CS_STORY_PLACEHOLDER -->

</div><!-- /tab-cs -->

<!-- ══════ TAB 4: PM STORY ══════ -->
<div id="tab-pm" class="tab-panel">

<!-- PM_STORY_PLACEHOLDER -->

</div><!-- /tab-pm -->

<!-- ══════ TAB 5: MACRO ══════ -->
<div id="tab-macro" class="tab-panel">

<!-- MACRO_EVENTS_PLACEHOLDER -->

</div><!-- /tab-macro -->

<!-- ══════ TAB 6: SOURCES ══════ -->
<div id="tab-sources" class="tab-panel">

<!-- SOURCES_PLACEHOLDER -->

</div><!-- /tab-sources -->

<div class="ai-disclaimer">⚠️ 본 보고서는 AI가 자동 생성한 참고 자료이며, 투자 권유가 아닙니다. 수치·해석에 오류가 포함될 수 있으므로 투자 판단 시 반드시 원본 데이터를 확인하시기 바랍니다.</div>
<div class="footer">Daily Market Summary | AI auto-generated | {report_date}</div>

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
Chart.defaults.font.family="'Spoqa Han Sans Neo','Spoqa Han Sans',sans-serif";
Chart.defaults.font.size=11;
const UP='#d92b2b',DN='#1a5fb4',AC='#F58220',WN='#CB6015',MU='#b0b4c4',GD='#b8860b';
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
      {{label:'MSCI',data:{json.dumps([s for s in scatter_data if s['cat']=='msci'])},backgroundColor:'#8B5CF6aa',pointRadius:6}},
      {{label:'Stocks',data:{json.dumps([s for s in scatter_data if s['cat']=='stocks'])},backgroundColor:'#043B72aa',pointRadius:6}},
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

    # ── tab-stocks 4섹션 inject (전체 stocks 데이터 활용) ──
    kr_stocks = {n: st_all[n] for n in KR_STOCK_ORDER[:KR_STOCK_TOP_N] if n in st_all}
    us_stocks = {n: st_all[n] for n in US_STOCK_ORDER[:US_STOCK_TOP_N] if n in st_all}
    asia_stocks = {n: st_all[n] for n in ASIA_STOCK_ORDER[:ASIA_STOCK_TOP_N] if n in st_all}
    other_stocks = {
        n: d for n, d in st_all.items()
        if n not in KR_STOCK_ORDER and n not in US_STOCK_ORDER and n not in ASIA_STOCK_ORDER
    }

    stocks_sections = [
        (f"한국 주식(Korean Stocks · Top {KR_STOCK_TOP_N})", kr_stocks, False, KR_STOCK_ORDER),
        (f"미국 주식(US Stocks · Top {US_STOCK_TOP_N})", us_stocks, True, US_STOCK_ORDER),
        (f"아시아 종목(Asian Stocks · Top {ASIA_STOCK_TOP_N})", asia_stocks, False, ASIA_STOCK_ORDER),
    ]
    if other_stocks:
        stocks_sections.append(
            ("기타 종목(ADR · HK · 기타)", other_stocks, True, list(other_stocks.keys()))
        )

    stocks_html = ""
    for title, cat, dollar, order in stocks_sections:
        if not cat:
            continue
        items = [(n, cat[n]) for n in order if n in cat]
        src = DATA_SOURCES.get(title) or next(
            (v for k, v in DATA_SOURCES.items() if title.startswith(k)), ""
        )
        src_html = f' <span class="src-tag">{src}</span>' if src else ""
        stocks_html += f"""<div class="heatmap-section">
<h2>{title} <span class="badge">{len(items)}</span>{src_html}</h2>
<table class="heatmap">
<thead><tr><th>종목</th><th>종가</th><th>20일 추이</th><th>일간</th><th>주간</th><th>월간</th><th>연초대비</th></tr></thead>
<tbody>
"""
        for name, d in items:
            stocks_html += heatmap_row(name, d, dollar, False)
        stocks_html += "</tbody></table></div>\n"

    html = html.replace("<!-- STOCKS_TABLES_PLACEHOLDER -->", stocks_html)

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
        except Exception:
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

    # ── 주간 보고서 수집 (월별 그룹, 날짜 범위 표시) ──
    import re as _re
    weekly_by_month = {}
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "weekly", "*.html")), reverse=True):
        fname = os.path.basename(path)
        if any(s in fname for s in ("_story", "_macro", "_cs", "_pm", "_stocks", "_sources", "_asia")):
            continue
        week_label = fname.replace(".html", "")  # e.g. "2026-W02"

        # HTML에서 날짜 범위 추출
        date_range = ""
        try:
            with open(path, encoding="utf-8") as _f:
                head = _f.read(25000)
            m = _re.search(r'class="date">\s*([\d-]+)\s*~\s*([\d-]+)', head)
            if m:
                date_range = f"{m.group(1)} ~ {m.group(2)}"
        except Exception:
            pass

        # 월 판단
        try:
            year = int(week_label[:4])
            week_num = int(week_label.split("W")[1])
            monday = dt.datetime.strptime(f"{year}-W{week_num:02d}-1", "%Y-W%W-%w").date()
            month_key = monday.strftime("%Y-%m")
        except Exception:
            month_key = week_label[:7]

        if month_key not in weekly_by_month:
            weekly_by_month[month_key] = []
        display = f"{week_label} ({date_range})" if date_range else week_label
        weekly_by_month[month_key].append((display, fname))

    sorted_weekly_months = sorted(weekly_by_month.keys(), reverse=True)
    latest_weekly_month = sorted_weekly_months[0] if sorted_weekly_months else ""

    weekly_month_btns = ""
    weekly_panels = ""
    for m in sorted_weekly_months:
        active = " active" if m == latest_weekly_month else ""
        label = dt.datetime.strptime(m, "%Y-%m").strftime("%Y %b")
        weekly_month_btns += f'      <button class="month-btn{active}" onclick="showSub(\'weekly\',\'{m}\')">{label}</button>\n'
        items = ""
        for display, fname in weekly_by_month[m]:
            items += f'          <li><a href="weekly/{fname}">{display}</a></li>\n'
        weekly_panels += f'      <div class="sub-panel{active}" id="weekly-{m}"><ul>\n{items}      </ul></div>\n'

    # ── 월간 보고서 수집 ──
    SIBLING_SUFFIXES = ("_story.html", "_pm.html", "_cs.html", "_macro.html", "_stocks.html", "_sources.html", "_asia.html")

    monthly_items = ""
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "monthly", "*.html")), reverse=True):
        fname = os.path.basename(path)
        if fname.endswith(SIBLING_SUFFIXES):
            continue
        label = fname.replace(".html", "")
        try:
            d = dt.datetime.strptime(label, "%Y-%m")
            label = d.strftime("%Y %B")
        except Exception:
            pass
        monthly_items += f'      <li><a href="monthly/{fname}">{label}</a></li>\n'

    quarterly_items = ""
    for path in sorted(glob.glob(os.path.join(OUTPUT_DIR, "quarterly", "*.html")), reverse=True):
        fname = os.path.basename(path)
        if fname.endswith(SIBLING_SUFFIXES):
            continue
        label = fname.replace(".html", "")  # e.g. 2026-Q1
        quarterly_items += f'      <li><a href="quarterly/{fname}">{label}</a></li>\n'

    index_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Summary</title>
<meta name="description" content="매일 자동 생성되는 글로벌 시장 요약 보고서 — Equity, Bonds, FX, Commodities, Risk">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="icon" type="image/png" sizes="192x192" href="favicon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="favicon-512.png">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:title" content="Market Summary | Daily Global Markets">
<meta property="og:description" content="매일 자동 생성되는 글로벌 시장 요약 보고서 — Equity, Bonds, FX, Commodities, Risk">
<meta property="og:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="https://traderparamita.github.io/market-summary/">
<meta property="og:site_name" content="Market Summary">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Market Summary | Daily Global Markets">
<meta name="twitter:description" content="매일 자동 생성되는 글로벌 시장 요약 보고서">
<meta name="twitter:image" content="https://traderparamita.github.io/market-summary/og-image.png?v={OG_IMAGE_VERSION}">
<style>
  @import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400&display=swap');
  body {{ font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic','맑은 고딕',sans-serif; background:#f4f5f9; color:#2d3148; padding:40px 24px; max-width:720px; margin:0 auto; }}
  h1 {{ font-size:28px; font-weight:700; margin-bottom:4px; }}
  .sub {{ font-size:14px; color:#7c8298; margin-bottom:24px; }}
  .main-tabs {{ display:flex; gap:0; margin-bottom:24px; border-bottom:2px solid #e0e3ed; }}
  .main-tab {{
    padding:10px 24px; font-size:14px; font-weight:600; color:#7c8298; background:none;
    border:none; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px;
    transition:all .2s; font-family:inherit;
  }}
  .main-tab:hover {{ color:#2d3148; }}
  .main-tab.active {{ color:#F58220; border-bottom-color:#F58220; }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}
  .month-bar {{ display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }}
  .month-btn {{
    padding:6px 14px; border:1px solid #e0e3ed; border-radius:16px;
    background:#fff; color:#7c8298; font-size:12px; font-weight:600;
    cursor:pointer; transition:all .15s; font-family:inherit;
  }}
  .month-btn:hover {{ border-color:#F58220; color:#F58220; }}
  .month-btn.active {{ background:#F58220; color:#fff; border-color:#F58220; }}
  .sub-panel {{ display:none; }}
  .sub-panel.active {{ display:block; }}
  ul {{ list-style:none; padding:0; }}
  li {{ margin-bottom:8px; }}
  li a {{
    display:block; padding:12px 18px; background:#fff; border:1px solid #e0e3ed;
    border-radius:10px; text-decoration:none; color:#2d3148; font-size:14px;
    font-weight:500; transition:all .15s; box-shadow:0 1px 3px rgba(0,0,0,0.04);
    font-family:'JetBrains Mono','Spoqa Han Sans Neo',monospace;
  }}
  li a:hover {{ border-color:#F58220; color:#F58220; transform:translateX(4px); }}
</style>
</head>
<body>
  <h1>Market Summary</h1>
  <p class="sub">AI가 매일 아침 전 세계 시장을 분석해 상담원을 위한 시황 브리핑을 준비합니다.</p>

  <div class="main-tabs">
    <button class="main-tab active" onclick="showTab('daily')">Daily</button>
    <button class="main-tab" onclick="showTab('weekly')">Weekly</button>
    <button class="main-tab" onclick="showTab('monthly')">Monthly</button>
    <button class="main-tab" onclick="showTab('quarterly')">Quarterly</button>
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

  <div id="tab-quarterly" class="tab-content">
    <ul>
{quarterly_items if quarterly_items else '      <li style="color:#7c8298;font-style:italic">No quarterly reports yet.</li>'}
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
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"Index saved: {idx_path}")



def _run_aux_collectors(target_date: str) -> None:
    """Auxiliary collectors 일간 실행 (CSV + Snowflake 동시 적재).

    daily market-full 에서 MKT100 이 단일 소스가 되려면 보조 지표들도 매일 수집돼야 한다.
    각 collector 는 dedup 로직이 있어 중복 호출해도 이미 있는 행은 건너뛴다.

    - collect_sector_etfs:      SC_US_*, FA_US_*, US Bond ETFs (yfinance)
    - collect_krx_sectors:      IX_KR_* (KOSPI200 GICS 지수, pykrx)
    - collect_valuation:        VAL_KR_* (KOSPI PER/PBR/DY, pykrx)
    - collect_stocks_universe:  ST_KR_* / 신규 ST_<TICKER> (KR50 + US S&P50 종목, yfinance)
    - collect_macro:            FRED + ECOS 거시지표 (history/macro_indicators.csv + MKT200 upsert)

    실패해도 메인 파이프라인은 계속 — 각 collector 는 [AUX] 마커로 결과 표시.

    macro 만 lookback 윈도우가 다르다: FRED/ECOS 는 발표 시차가 있어 (예: CPI 익월,
    실업률 익월 초) target_date 만 좁히면 새 데이터를 못 잡는다. 따라서 macro 는
    target_date - 90일 부터 재조회해 dedup 으로 멱등 append.
    """
    print(f"\n=== Aux collectors (date={target_date}) ===")

    aux_tasks = [
        ("sector_etfs",     "collectors.sector_etfs",     "collect_sector_etfs",     "narrow"),
        ("krx_sectors",     "collectors.krx_sectors",     "collect_krx_sectors",     "narrow"),
        ("valuation",       "collectors.valuation",       "collect_valuation",       "narrow"),
        ("stocks_universe", "collectors.stocks_universe", "collect_stocks_universe", "narrow"),
        ("macro",           "collectors.macro",           "collect_macro",           "lookback90"),
    ]

    macro_start = (dt.datetime.strptime(target_date, "%Y-%m-%d").date()
                   - dt.timedelta(days=90)).strftime("%Y-%m-%d")

    for label, module_path, func_name, window in aux_tasks:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            if window == "lookback90":
                # macro: 발표 시차 흡수 위해 90일 룩백
                added = func(start=macro_start, end=target_date)
            else:
                # 기타 collector 는 dedup 하므로 start/end 를 target_date 로 좁혀 호출
                added = func(start=target_date, end=target_date)
            _log(f"[AUX] OK collector={label} rows={added}")
        except Exception as e:
            reason = str(e).replace("\n", " ")[:200]
            _log(f"[AUX] FAILED collector={label} reason={reason}")


def main(target_date=None, start_date=None):
    """일간 리포트 생성.

    Args:
        target_date: 'YYYY-MM-DD'. None 이면 전 영업일.
        start_date:  수집 시작일. None 이면 fetch_data 기본값 (target-200일).
                     재수집 용도로 사용: main(target_date='2026-04-09', start_date='2025-01-01').
    """
    _start_time = dt.datetime.now()

    if not target_date:
        target_date = str(prev_business_day())

    _log("=" * 60)
    _log("  [Step 1~2] Data Dashboard 생성")
    _log("=" * 60)
    _log(f"Target date: {target_date}")
    if start_date:
        _log(f"Collecting from: {start_date}")

    # Step 1a: API 에서 원시 데이터 수집 → CSV 에 축적 (collect_market 핵심 56+ 지표)
    _log("\n  [Step 1a] 마켓 데이터 수집 중...")
    _, history_rows = fetch_data(start_date=start_date, end_date=target_date)
    append_to_history(history_rows)
    _log(f"    ✓ CSV 업데이트: {len(history_rows)} 행")

    # Step 1b: 보조 수집기 일간 실행 (pykrx KR 섹터 지수 + KOSPI 밸류에이션 + 추가 ETF)
    #   - 전체 재수집(--start) 시에는 실행 안 함 (별도 백필 권장).
    #   - 각 collector 내부에서 CSV append + Snowflake upsert 자동 수행.
    _log("\n  [Step 1b] 보조 수집기 실행 중...")
    if not start_date:
        _run_aux_collectors(target_date)
        _log("    ✓ 보조 수집 완료")
    else:
        _log("    ⊘ 스킵 (bulk mode: --start)")

    # Step 1c: RDS market_daily 통합 upsert
    #   - target_date 외에 직전 5영업일(=달력 7일) 도 함께 upsert.
    #     (Naver/FDR/investiny fallback 으로 과거 행이 사후 업데이트되는 경우 RDS 와의 드리프트 방지)
    #   - upsert_rows 는 (일자 × 지표코드) 교집합 DELETE 후 INSERT — df 에 없는 코드는 안전.
    #   - 표준 마커: [RDS] OK date=... rows=N  또는  [RDS] FAILED date=... reason=...
    _log("\n  [Step 1c] RDS 통합 upsert 중...")
    if not start_date:
        try:
            import pandas as pd
            from rds_loader import upsert_rows, _alert_failure
            df_full = pd.read_csv(HISTORY_CSV)
            df_full["DATE"] = df_full["DATE"].astype(str)
            window_start = (dt.datetime.strptime(target_date, "%Y-%m-%d").date()
                            - dt.timedelta(days=7)).strftime("%Y-%m-%d")
            df_recent = df_full[(df_full["DATE"] >= window_start) & (df_full["DATE"] <= target_date)]
            if df_recent.empty:
                _log(f"    [RDS] SKIP date={target_date} reason=no-csv-rows-in-window")
            else:
                nrows = upsert_rows(df_recent.copy())  # multi-date upsert
                ndates = df_recent["DATE"].nunique()
                _log(f"    [RDS] OK date={target_date} window={window_start}~{target_date} dates={ndates} rows={nrows}")
        except Exception as e:
            reason = str(e).replace("\n", " ")[:300]
            try:
                _alert_failure(source=f"generate.py-step1c-{target_date}",
                               reason=reason, table="mkt100_market_daily")
            except Exception:
                _log(f"    [RDS] FAILED date={target_date} reason={reason}")
    else:
        _log(f"    ⊘ 스킵 (bulk mode: --start)")

    # Step 2: CSV에서 메트릭 계산
    _log("\n  [Step 2] 메트릭 계산 및 HTML 생성 중...")
    data = build_report_data(target_date)

    # 월별 폴더에 저장
    month_dir = os.path.join(OUTPUT_DIR, target_date[:7])
    os.makedirs(month_dir, exist_ok=True)

    json_path = os.path.join(month_dir, f"{target_date}_data.json")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _log(f"    ✓ _data.json 저장")

    html, report_date = generate_html(data)

    html_path = os.path.join(month_dir, f"{report_date}.html")
    _inject_existing_story(html_path, html)
    _log(f"    ✓ Daily HTML 저장: {html_path}")

    # 당일이 포함된 주간/월간 보고서 자동 갱신 (index보다 먼저 — index는 weekly HTML의 date range를 파싱함)
    update_current_periodic(target_date)

    generate_index()

    _log("\n  ✅ [Step 1~2] 완료")
    _log("=" * 60)

    return html_path


def update_current_periodic(target_date):
    """target_date가 포함된 주간 및 월간 보고서를 갱신"""
    try:
        from generate_periodic import (
            load_market_data, get_week_ranges, aggregate_period,
            generate_periodic_html
        )

        td = dt.datetime.strptime(target_date, "%Y-%m-%d").date()
        year = td.year

        market_data, trading_days = load_market_data()

        # ── 당일 포함 주간 보고서 갱신 ──
        iso = td.isocalendar()
        iso_week = iso[1]
        weeks = get_week_ranges(trading_days, year)
        week_key = (iso[0], iso_week)

        if week_key in weeks:
            dates = weeks[week_key]
            agg = aggregate_period(market_data, trading_days, dates)
            if agg:
                first, last = agg["first"], agg["last"]
                n_days = len(agg["dates"])
                week_label = f"W{iso_week:02d}"
                title = f"Weekly Summary | {year} {week_label}"
                subtitle = f"{first} ~ {last} ({n_days} trading days)"
                filename = f"{year}-W{iso_week:02d}.html"

                weekly_dir = os.path.join(OUTPUT_DIR, "weekly")
                os.makedirs(weekly_dir, exist_ok=True)
                html = generate_periodic_html(agg, title, subtitle, "Weekly", filename)
                path = os.path.join(weekly_dir, filename)

                # 기존 Story 보존
                _inject_existing_story(path, html)
                _log(f"    ✓ Weekly auto-updated: {filename}")

        # ── 당일 포함 월간 보고서 갱신 ──
        month_str = target_date[:7]
        month_dates = sorted([d for d in trading_days if d.startswith(month_str)])
        if month_dates:
            agg = aggregate_period(market_data, trading_days, month_dates)
            if agg:
                month_name = td.strftime("%B")
                title = f"Monthly Summary | {year} {month_name}"
                subtitle = f"{month_dates[0]} ~ {month_dates[-1]} ({len(month_dates)} trading days)"
                filename = f"{year}-{td.month:02d}.html"

                monthly_dir = os.path.join(OUTPUT_DIR, "monthly")
                os.makedirs(monthly_dir, exist_ok=True)
                html = generate_periodic_html(agg, title, subtitle, "Monthly", filename)
                path = os.path.join(monthly_dir, filename)

                _inject_existing_story(path, html)
                _log(f"    ✓ Monthly auto-updated: {filename}")

    except Exception as e:
        _log(f"    ⚠ Periodic update 경고: {e}")


_TAB_SPECS = DAILY_TAB_SPECS


def _find_prev_weekly_macro(daily_html_path):
    """일간 보고서 경로에서 해당 날짜를 역산해, 직전 주 weekly _macro.html 내용을 반환."""
    import re as _re
    try:
        fname = os.path.basename(daily_html_path)
        m = _re.match(r"(\d{4}-\d{2}-\d{2})", fname)
        if not m:
            return ""
        report_date = dt.datetime.strptime(m.group(1), "%Y-%m-%d").date()
        iso = report_date.isocalendar()
        prev_week = report_date - dt.timedelta(weeks=1)
        prev_iso = prev_week.isocalendar()
        weekly_dir = os.path.join(OUTPUT_DIR, "weekly")
        for candidate in [prev_iso, iso]:
            macro_path = os.path.join(
                weekly_dir,
                f"{candidate[0]}-W{candidate[1]:02d}_macro.html"
            )
            if os.path.exists(macro_path):
                with open(macro_path, encoding="utf-8") as f:
                    content = f.read().strip()
                if content and "MACRO_EVENTS_PLACEHOLDER" not in content:
                    _log(f"  Macro injected from: {os.path.basename(macro_path)}")
                    return content
    except Exception:
        pass
    return ""


def _inject_existing_story(path, new_html):
    """기존 파일의 Story/CS/PM 탭 내용을 새 HTML placeholder에 주입 + sibling 파일 저장."""
    new_html = inject_existing_story(path, new_html, _TAB_SPECS)
    # macro 탭 추가 fallback: 직전 주 weekly _macro.html
    if "<!-- MACRO_EVENTS_PLACEHOLDER -->" in new_html:
        macro = _find_prev_weekly_macro(path)
        if macro:
            new_html = new_html.replace("<!-- MACRO_EVENTS_PLACEHOLDER -->", macro)

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)

    save_story_files(path, new_html, _TAB_SPECS, log_fn=_log)


def _reinject_stories(target_date: str | None = None):
    """사이드카 파일(_cs/_pm/_stocks/_story/_macro/_sources)을 메인 HTML에 재주입.

    generate.py --reinject [YYYY-MM-DD] 로 호출.
    데이터 재수집 없이 스토리 탭 주입만 수행한다.
    """
    if not target_date:
        target_date = prev_business_day()
    month_dir = os.path.join(OUTPUT_DIR, target_date[:7])
    html_path = os.path.join(month_dir, f"{target_date}.html")
    if not os.path.exists(html_path):
        _log(f"[reinject] 파일 없음: {html_path}")
        return
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    _inject_existing_story(html_path, html)
    _log(f"[reinject] 완료: {html_path}")


def backfill_macro_to_daily(week_macro_path):
    """주간 _macro.html 작성 후, 해당 주 마지막 영업일(금요일) 보고서에만 macro 탭을 주입.

    market-full Step 5.6 이후 호출.
    금요일 보고서는 주가 끝난 뒤 생성되므로 이번 주 macro가 들어가야 자연스럽다.
    """
    import re as _re
    fname = os.path.basename(week_macro_path)
    m = _re.match(r"(\d{4})-W(\d{2})_macro\.html", fname)
    if not m:
        return
    year, week = int(m.group(1)), int(m.group(2))

    if not os.path.exists(week_macro_path):
        return
    with open(week_macro_path, encoding='utf-8') as f:
        macro_content = f.read().strip()
    if not macro_content or "MACRO_EVENTS_PLACEHOLDER" in macro_content:
        return

    # 해당 주 금요일(마지막 영업일) 보고서만 대상
    friday = dt.date.fromisocalendar(year, week, 5)
    daily_path = os.path.join(OUTPUT_DIR, friday.strftime("%Y-%m"), f"{friday.isoformat()}.html")
    if not os.path.exists(daily_path):
        return
    with open(daily_path, encoding='utf-8') as f:
        html = f.read()
    pattern = r'(<div id="tab-macro" class="tab-panel">)\s*\n.*?\n(</div><!-- /tab-macro -->)'
    replacement = rf'\1\n\n{macro_content}\n\n\2'
    new_html, n = _re.subn(pattern, replacement, html, flags=_re.DOTALL)
    if n > 0:
        with open(daily_path, "w", encoding='utf-8') as f:
            f.write(new_html)
        base, ext = os.path.splitext(daily_path)
        macro_sibling = f"{base}_macro{ext}"
        with open(macro_sibling, "w", encoding='utf-8') as f:
            f.write(macro_content)
        _log(f"  Macro backfilled to Friday: {os.path.basename(daily_path)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Market Summary daily generator")
    parser.add_argument("target_date", nargs="?", default=None,
                        help="보고서 기준일 YYYY-MM-DD (기본: 전 영업일)")
    parser.add_argument("--start", dest="start_date", default=None,
                        help="수집 시작일 YYYY-MM-DD (전체 재수집 용)")
    parser.add_argument("--reinject", action="store_true",
                        help="사이드카(_cs/_pm/_stocks/_story) → 메인 HTML 재주입만 수행 (데이터 재수집 없음)")
    args = parser.parse_args()

    if args.reinject:
        _reinject_stories(args.target_date)
        sys.exit(0)

    path = main(target_date=args.target_date, start_date=args.start_date)
    # NOTE: 이 메시지는 generate.py(데이터 수집 + HTML 생성) 자체의 종료 신호다.
    # /market-full 워크플로우 입장에서는 Step 1~2 가 끝난 것일 뿐이며, Story 작성
    # (Step 3-A/B/C/D) + 검증(7.7) + 커밋(8) + Sector-Country(10~13) 가 남아 있다.
    # Claude 가 이 메시지를 보고 워크플로우 전체가 종료된 것으로 오인하지 않도록
    # 메시지를 의도적으로 'Step 1~2'로 명시한다.
    _log(f"\n[Step 1~2 완료 — Data Dashboard 생성됨. 후속 Step 3+ 계속 진행]")
    _log(f"Output: file://{path}")
