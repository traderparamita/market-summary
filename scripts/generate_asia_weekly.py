#!/usr/bin/env python3
"""Generate Asia Weekly Brief — data skeleton + Claude AI narrative tabs.

Usage:
    .venv/bin/python scripts/generate_asia_weekly.py [YYYY-MM-DD] [--no-ai]

If date is omitted, uses the most recent Friday.
--no-ai: skip Claude API calls, write skeleton only (for testing).

Outputs:
    output/summary/weekly/YYYY-WNN_asia.html       — full report (data + AI narrative)
    output/summary/weekly/YYYY-WNN_asia_data.json  — extracted data

Skill: .claude/skills/asia-weekly/SKILL.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from _utils import is_business_day

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = PROJECT_ROOT / "history"
OUTPUT_DIR = PROJECT_ROOT / "output" / "summary" / "weekly"


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

ASIA_INDICES = [
    "KOSPI", "KOSDAQ", "Nikkei225", "HSI", "Shanghai", "TWSE", "NIFTY50", "MSCI EM",
]
ASIA_FX = [
    "USD/KRW", "USD/JPY", "USD/INR", "USD/CNY", "DXY",
]

INDEX_LABELS = {
    "KOSPI": ("코스피", "한국"),
    "KOSDAQ": ("코스닥", "한국"),
    "Shanghai": ("상하이종합", "중국 본토"),
    "HSI": ("HSI 항셍", "홍콩"),
    "Nikkei225": ("Nikkei225", "일본"),
    "TWSE": ("TWSE 가권", "대만"),
    "NIFTY50": ("NIFTY50", "인도"),
    "MSCI EM": ("MSCI EM", "신흥국 전체"),
}

FX_LABELS = {
    "USD/KRW": ("USD/KRW", "원"),
    "USD/JPY": ("USD/JPY", "엔"),
    "USD/INR": ("USD/INR", "루피"),
    "USD/CNY": ("USD/CNY", "위안"),
    "DXY":     ("DXY",     "달러지수"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Date helpers
# ─────────────────────────────────────────────────────────────────────────────

def to_friday_of_week(target: date) -> date:
    """Returns Friday of the ISO week containing `target`."""
    return target + timedelta(days=(4 - target.weekday()))


def to_prev_friday(target: date) -> date:
    """Returns the Friday-of-week of `target`; if target is itself the Friday or later in the week,
    keeps that Friday."""
    wd = target.weekday()  # Mon=0..Sun=6
    if wd >= 5:  # Sat/Sun — use the Friday just past
        return target - timedelta(days=wd - 4)
    elif wd == 4:  # Fri
        return target
    else:  # Mon-Thu — Friday of the same ISO week
        return target + timedelta(days=4 - wd)


def get_week_window(target: date) -> tuple[date, date, str]:
    """Return (monday, friday, 'YYYY-WNN')."""
    friday = to_prev_friday(target)
    monday = friday - timedelta(days=4)
    iso_year, iso_week, _ = friday.isocalendar()
    return monday, friday, f"{iso_year}-W{iso_week:02d}"


def get_last_trading_day_of_week(friday: date, df: pd.DataFrame) -> date:
    """Return the actual last trading day on/before `friday` within the same week.

    `friday` is not always a trading day (KR public holiday, e.g. 제헌절) — walking
    back to the nearest KR business day that actually has KOSPI data avoids the
    0/180 matching failure that happens when the week's nominal end date has no
    rows collected at all (W25/W28/W29 all hit this).
    """
    monday = friday - timedelta(days=4)
    kospi_dates = set(
        pd.Timestamp(x).date() for x in df.loc[df["TICKER"] == "KOSPI", "DATE"].unique()
    )
    d = friday
    while d >= monday:
        if is_business_day(d) and d in kospi_dates:
            return d
        d -= timedelta(days=1)
    return friday  # no trading day found this week — caller will surface 0 matches


def get_prev_friday_close(monday: date, df: pd.DataFrame) -> date:
    """Find the trading day before `monday` that has data (typically previous Friday).

    Excludes `SOURCE == 'computed'` rows (e.g. weekend carry-forward duplicates like
    a Sunday-dated BD_US_10_2_SPREAD row) which can corrupt the max-date scan and
    silently pick a non-trading date as the reference.
    """
    real = df[df["SOURCE"] != "computed"]
    available_dates = sorted(real["DATE"].unique())
    available_dates = [pd.Timestamp(d).date() for d in available_dates]
    # find the latest available date strictly before `monday`
    eligible = [d for d in available_dates if d < monday]
    if not eligible:
        raise SystemExit(f"No reference date before {monday} in market_data.csv")
    return max(eligible)


# ─────────────────────────────────────────────────────────────────────────────
# Data extraction
# ─────────────────────────────────────────────────────────────────────────────

def load_universe() -> pd.DataFrame:
    xl_path = HISTORY_DIR / "아시아종목.xlsx"
    if not xl_path.exists():
        raise SystemExit(f"Universe file not found: {xl_path}")
    df = pd.read_excel(xl_path, sheet_name="전체")
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={
        "종목명": "name",
        "티커":   "ticker",
        "국가":   "country",
        "비중(%)": "weight",
    })
    return df[["name", "ticker", "country", "weight"]].dropna(subset=["name", "country"])


def load_market() -> pd.DataFrame:
    csv_path = HISTORY_DIR / "market_data.csv"
    if not csv_path.exists():
        raise SystemExit(f"Market data not found: {csv_path}")
    df = pd.read_csv(csv_path)
    df["DATE"] = pd.to_datetime(df["DATE"])
    return df


def compute_wtd_returns(
    df: pd.DataFrame,
    tickers: list[str],
    ref_date: date,
    end_date: date,
) -> dict[str, dict]:
    """Compute WTD% for each ticker. Returns dict: {ticker: {start, end, pct}}."""
    sub = df[df["TICKER"].isin(tickers)].copy()
    piv = sub.pivot_table(index="DATE", columns="TICKER", values="CLOSE", aggfunc="first").sort_index()

    result = {}
    ref_ts = pd.Timestamp(ref_date)
    end_ts = pd.Timestamp(end_date)
    for t in tickers:
        if t not in piv.columns:
            continue
        s = piv[t].dropna()
        if ref_ts in s.index and end_ts in s.index:
            sv = float(s.loc[ref_ts])
            ev = float(s.loc[end_ts])
            if sv > 0:
                result[t] = {
                    "start": round(sv, 4),
                    "end":   round(ev, 4),
                    "pct":   round((ev / sv - 1) * 100, 4),
                }
    return result


def build_country_summary(
    universe: pd.DataFrame, stock_returns: dict[str, dict]
) -> dict[str, dict]:
    summary = {}
    for country, group in universe.groupby("country"):
        rows = []
        for _, r in group.iterrows():
            name = r["name"]
            if name in stock_returns:
                rows.append({
                    "name":   name,
                    "ticker": r["ticker"],
                    "weight": float(r["weight"]),
                    "pct":    stock_returns[name]["pct"],
                    "start":  stock_returns[name]["start"],
                    "end":    stock_returns[name]["end"],
                })
        if not rows:
            summary[country] = {
                "n_universe": int(len(group)),
                "n_matched":  0,
                "weight_total_universe": round(float(group["weight"].sum()), 4),
                "weight_total_matched": 0.0,
                "simple_avg": None,
                "weighted_avg": None,
                "stocks": [],
            }
            continue
        n_matched = len(rows)
        weight_total = sum(x["weight"] for x in rows)
        simple_avg = sum(x["pct"] for x in rows) / n_matched
        weighted_avg = sum(x["weight"] * x["pct"] for x in rows) / weight_total if weight_total else None
        summary[country] = {
            "n_universe": int(len(group)),
            "n_matched":  int(n_matched),
            "weight_total_universe": round(float(group["weight"].sum()), 4),
            "weight_total_matched":  round(weight_total, 4),
            "simple_avg":   round(simple_avg, 4),
            "weighted_avg": round(weighted_avg, 4) if weighted_avg is not None else None,
            "stocks":       sorted(rows, key=lambda x: x["pct"], reverse=True),
        }
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# HTML generation
# ─────────────────────────────────────────────────────────────────────────────

# Read the reference template once (the W20 skeleton). We embed it as a string.
def render_html(data: dict) -> str:
    """Render the full HTML skeleton with KPI strip + Data tab + placeholders for Story tabs."""
    period_label = f"{data['monday']} ~ {data['friday']}"
    week_label = data["week"]

    # Mood badge logic based on MSCI EM
    msci_em_pct = data["indices"].get("MSCI EM", {}).get("pct")
    if msci_em_pct is None:
        mood_color = "var(--muted)"
        mood_text = "데이터 부족"
    elif msci_em_pct <= -3:
        mood_color = "var(--down)"
        mood_text = f'아시아 광역 약세 — MSCI EM <span style="font-family:\'JetBrains Mono\',monospace">{msci_em_pct:+.2f}%</span>'
    elif msci_em_pct >= 3:
        mood_color = "var(--up)"
        mood_text = f'아시아 광역 강세 — MSCI EM <span style="font-family:\'JetBrains Mono\',monospace">{msci_em_pct:+.2f}%</span>'
    else:
        mood_color = "var(--warn)"
        mood_text = f'Mixed — MSCI EM <span style="font-family:\'JetBrains Mono\',monospace">{msci_em_pct:+.2f}%</span>'

    # KPI strip
    kpi_html = []
    for code in ["KOSPI", "KOSDAQ", "Nikkei225", "HSI", "Shanghai", "TWSE", "NIFTY50"]:
        d = data["indices"].get(code)
        if not d:
            continue
        label, _ = INDEX_LABELS[code]
        pct = d["pct"]
        cls = "up" if pct > 0.05 else ("down" if pct < -0.05 else "flat")
        sign = "+" if pct > 0 else "−" if pct < 0 else ""
        pct_str = f"{sign}{abs(pct):.2f}%"
        kpi_html.append(
            f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{d["end"]:,.2f}</div>'
            f'<div class="kpi-chg {cls}">{pct_str}</div></div>'
        )
    for code in ["USD/KRW", "USD/JPY", "USD/INR", "USD/CNY"]:
        d = data["fx"].get(code)
        if not d:
            continue
        pct = d["pct"]
        cls = "up" if pct > 0.05 else ("down" if pct < -0.05 else "flat")
        sign = "+" if pct > 0 else "−" if pct < 0 else ""
        pct_str = f"{sign}{abs(pct):.2f}%"
        kpi_html.append(
            f'<div class="kpi"><div class="kpi-label">{code}</div>'
            f'<div class="kpi-value">{d["end"]:,.2f}</div>'
            f'<div class="kpi-chg {cls}">{pct_str}</div></div>'
        )
    em = data["indices"].get("MSCI EM")
    if em:
        pct = em["pct"]
        cls = "up" if pct > 0.05 else ("down" if pct < -0.05 else "flat")
        sign = "+" if pct > 0 else "−" if pct < 0 else ""
        pct_str = f"{sign}{abs(pct):.2f}%"
        kpi_html.append(
            f'<div class="kpi"><div class="kpi-label">MSCI EM</div>'
            f'<div class="kpi-value">{em["end"]:,.2f}</div>'
            f'<div class="kpi-chg {cls}">{pct_str}</div></div>'
        )
    kpi_strip = "\n  ".join(kpi_html)

    # Data tab — index table (WTD% 내림차순)
    idx_entries = []
    for code, (label, region) in INDEX_LABELS.items():
        d = data["indices"].get(code)
        if not d:
            continue
        idx_entries.append((label, region, d))
    idx_entries.sort(key=lambda x: x[2]["pct"], reverse=True)
    idx_rows = []
    for label, region, d in idx_entries:
        pct = d["pct"]
        cls = "up" if pct > 0.05 else ("down" if pct < -0.05 else "flat")
        sign = "+" if pct > 0 else "−" if pct < 0 else ""
        idx_rows.append(
            f'<tr><td class="name-cell">{label}</td>'
            f'<td class="close-cell">{region}</td>'
            f'<td class="close-cell">{d["start"]:,.2f}</td>'
            f'<td class="close-cell">{d["end"]:,.2f}</td>'
            f'<td class="heat-cell {cls}">{sign}{abs(pct):.2f}%</td></tr>'
        )
    index_table = "\n      ".join(idx_rows)

    # FX table
    fx_rows = []
    for code, (label, name) in FX_LABELS.items():
        d = data["fx"].get(code)
        if not d:
            continue
        pct = d["pct"]
        cls = "up" if pct > 0.05 else ("down" if pct < -0.05 else "flat")
        sign = "+" if pct > 0 else "−" if pct < 0 else ""
        fx_rows.append(
            f'<tr><td class="name-cell">{label}</td>'
            f'<td class="close-cell">{d["start"]:,.4f}</td>'
            f'<td class="close-cell">{d["end"]:,.4f}</td>'
            f'<td class="heat-cell {cls}">{sign}{abs(pct):.2f}%</td>'
            f'<td style="font-size:12px;color:var(--muted)">{name}</td></tr>'
        )
    fx_table = "\n      ".join(fx_rows)

    # Top 20 / Bottom 20 across all stocks
    all_stocks = []
    for country, info in data["countries"].items():
        for s in info["stocks"]:
            all_stocks.append({"country": country, **s})
    top20 = sorted(all_stocks, key=lambda x: x["pct"], reverse=True)[:20]
    bot20 = sorted(all_stocks, key=lambda x: x["pct"])[:20]

    def stock_row(idx, s):
        pct = s["pct"]
        cls = "up" if pct > 0 else "down"
        sign = "+" if pct > 0 else "−"
        return (
            f'<tr><td class="close-cell">{idx}</td>'
            f'<td class="name-cell">{s["name"]}</td>'
            f'<td class="close-cell">{s["country"]}</td>'
            f'<td class="close-cell">{s["weight"]:.2f}</td>'
            f'<td class="close-cell">{s["start"]:,.2f}</td>'
            f'<td class="close-cell">{s["end"]:,.2f}</td>'
            f'<td class="heat-cell {cls}">{sign}{abs(pct):.2f}%</td></tr>'
        )

    top20_rows = "\n      ".join(stock_row(i + 1, s) for i, s in enumerate(top20))
    bot20_rows = "\n      ".join(stock_row(i + 1, s) for i, s in enumerate(bot20))

    # Country summary table (단순평균 WTD% 내림차순)
    country_flag = {"중국": "🇨🇳", "일본": "🇯🇵", "인도": "🇮🇳", "대만": "🇹🇼",
                    "홍콩": "🇭🇰", "베트남": "🇻🇳", "호주": "🇦🇺", "인도네시아": "🇮🇩"}
    country_order = sorted(
        [c for c, info in data["countries"].items() if info and info["n_matched"] > 0],
        key=lambda c: data["countries"][c]["simple_avg"],
        reverse=True,
    )
    country_rows = []
    for c in country_order:
        info = data["countries"].get(c)
        if not info or info["n_matched"] == 0:
            continue
        sa = info["simple_avg"]
        wa = info["weighted_avg"]
        sa_cls = "up" if sa > 0 else "down"
        wa_cls = "up" if wa > 0 else "down"
        country_rows.append(
            f'<tr><td class="name-cell">{country_flag[c]} {c}</td>'
            f'<td class="close-cell">{info["n_matched"]}/{info["n_universe"]}</td>'
            f'<td class="close-cell">{info["weight_total_matched"]:.2f}%</td>'
            f'<td class="heat-cell {sa_cls}">{"+" if sa>0 else "−"}{abs(sa):.2f}%</td>'
            f'<td class="heat-cell {wa_cls}">{"+" if wa>0 else "−"}{abs(wa):.2f}%</td></tr>'
        )
    country_table = "\n      ".join(country_rows)

    # Read the W20 reference template style — we'll inline a minimal CSS block.
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Asia Weekly Brief | {week_label}</title>
<meta name="description" content="{period_label} — 아시아 중심 주간 시황 (중국·일본·대만·인도·홍콩·한국)">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');
:root{{--bg:#f4f5f9;--card:#fff;--card2:#f0f1f6;--border:#e0e3ed;--text:#2d3148;--muted:#7c8298;--accent:#F58220;--accent2:#043B72;--up:#d92b2b;--down:#1a5fb4;--warn:#CB6015;--cn:#d92b2b;--jp:#043B72;--tw:#0f7f5a;--in:#7c4dff;--hk:#9c27b0;--kr:#F58220}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.65;padding:24px;max-width:1360px;margin:0 auto}}
.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:28px;padding-bottom:20px;border-bottom:2px solid var(--border)}}
.header-left h1{{font-size:26px;font-weight:700;color:#1a1d2e;margin-bottom:2px}}
.header-left .date{{font-size:13px;color:var(--muted);letter-spacing:1px}}
.mood-badge{{display:flex;align-items:center;gap:8px;padding:8px 18px;border-radius:24px;font-size:13px;font-weight:600;background:rgba(26,95,180,0.08);color:{mood_color};border:1px solid rgba(26,95,180,0.2)}}
.kpi-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:24px}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px}}
.kpi-label{{font-size:11px;color:var(--muted);font-weight:500;margin-bottom:2px}}
.kpi-value{{font-size:18px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}
.kpi-chg{{font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace}}
.up{{color:var(--up)}} .down{{color:var(--down)}} .flat{{color:var(--muted)}}
.back-link{{display:inline-block;margin-bottom:18px;color:var(--accent);text-decoration:none;font-size:13px;font-weight:500}}
.tab-bar{{display:flex;gap:0;margin-bottom:26px;border-bottom:2px solid var(--border);flex-wrap:wrap}}
.tab-btn{{padding:12px 24px;font-size:14px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s;font-family:inherit}}
.tab-btn:hover{{color:var(--text)}}
.tab-btn.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.tab-panel{{display:none}} .tab-panel.active{{display:block}}
.story-hero{{background:linear-gradient(135deg,#fff5eb,#fde9d3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:28px}}
.story-hero h2{{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}}
.story-text{{font-size:16px;color:#2d3148;line-height:1.9}}
.story-text p{{margin-bottom:14px}} .story-text p:last-child{{margin-bottom:0}}
.story-text strong{{color:#1a1d2e}}
.story-text .hl-up{{color:var(--up);font-weight:600}}
.story-text .hl-down{{color:var(--down);font-weight:600}}
.story-text .hl-warn{{color:var(--warn);font-weight:600}}
.story-text .hl-accent{{color:var(--accent);font-weight:600}}
.causal-chain{{display:flex;align-items:stretch;gap:0;margin-bottom:28px;overflow-x:auto;padding-bottom:8px}}
.cause-node{{flex:1;min-width:170px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 14px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.cause-node .node-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
.cause-node .node-title{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:4px}}
.cause-node .node-detail{{font-size:12px;color:var(--text);line-height:1.5}}
.cause-node .node-impact{{margin-top:8px;font-size:17px;font-weight:700}}
.cause-arrow{{display:flex;align-items:center;padding:0 4px;color:var(--muted);font-size:18px;flex-shrink:0}}
.country-section{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px 28px;margin-bottom:18px;box-shadow:0 2px 6px rgba(0,0,0,0.04);border-left:5px solid var(--accent2)}}
.country-section.cn{{border-left-color:var(--cn)}} .country-section.jp{{border-left-color:var(--jp)}} .country-section.tw{{border-left-color:var(--tw)}} .country-section.in{{border-left-color:var(--in)}} .country-section.hk{{border-left-color:var(--hk)}} .country-section.kr{{border-left-color:var(--kr)}}
.country-head{{display:flex;align-items:center;gap:14px;margin-bottom:14px}}
.country-flag{{font-size:30px}}
.country-title{{font-size:20px;font-weight:700;color:#1a1d2e}}
.country-sub{{font-size:13px;color:var(--muted);margin-left:auto;font-family:'JetBrains Mono',monospace}}
.country-section p{{font-size:14.5px;line-height:1.85;margin-bottom:12px;color:#2d3148}}
.country-section h4{{font-size:14px;font-weight:700;color:#1a1d2e;margin:14px 0 8px 0}}
.stock-table{{width:100%;border-collapse:collapse;font-size:13px;background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:14px}}
.stock-table th{{font-size:11px;font-weight:600;color:var(--muted);padding:9px 12px;text-align:right;background:var(--card2);border-bottom:1px solid var(--border)}}
.stock-table th:first-child,.stock-table th:nth-child(2){{text-align:left}}
.stock-table td{{padding:7px 12px;font-size:12.5px;border-bottom:1px solid #f3f4f8;font-family:'JetBrains Mono',monospace;text-align:right}}
.stock-table td:first-child{{font-weight:600;color:#1a1d2e;text-align:left;font-family:inherit}}
.stock-table td:nth-child(2){{text-align:left;font-family:inherit;color:var(--muted);font-size:12px}}
.stock-table tr.gain{{background:rgba(217,43,43,0.03)}} .stock-table tr.loss{{background:rgba(26,95,180,0.03)}}
.theme-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px 28px;margin-bottom:18px;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.theme-card h3{{font-size:17px;font-weight:700;color:#1a1d2e;margin-bottom:12px;display:flex;align-items:center;gap:10px}}
.theme-card .theme-tag{{font-size:11px;padding:3px 10px;border-radius:14px;background:var(--accent);color:#fff;font-weight:600}}
.theme-card p{{font-size:14px;color:#2d3148;line-height:1.85;margin-bottom:10px}}
.theme-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}
.theme-side{{background:var(--card2);border-radius:10px;padding:14px 16px}}
.theme-side h5{{font-size:13px;font-weight:700;color:#1a1d2e;margin-bottom:8px}}
.theme-side ul{{list-style:none;padding:0}}
.theme-side li{{font-size:12.5px;line-height:1.7;padding:3px 0;font-family:'JetBrains Mono',monospace}}
.heatmap{{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:16px}}
.heatmap th{{font-size:11px;font-weight:600;color:var(--muted);padding:10px 12px;text-align:right;background:var(--card2);border-bottom:1px solid var(--border);white-space:nowrap}}
.heatmap th:first-child,.heatmap th:nth-child(2){{text-align:left}}
.heatmap td{{padding:8px 12px;font-size:13px;border-bottom:1px solid #f3f4f8}}
.name-cell{{font-weight:600;color:#1a1d2e;white-space:nowrap}}
.close-cell{{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text);text-align:left;white-space:nowrap}}
.heat-cell{{text-align:right;font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600}}
.insight-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
.insight-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:22px;position:relative;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.insight-card .badge{{position:absolute;top:14px;right:14px;padding:2px 10px;border-radius:16px;font-size:11px;font-weight:600;background:rgba(245,130,32,0.12);color:var(--accent)}}
.insight-card h3{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:10px;padding-right:50px}}
.insight-card p{{font-size:13px;color:var(--text);line-height:1.8}}
.insight-card .metric-row{{display:flex;gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}}
.metric-item{{flex:1;text-align:center}}
.metric-label{{font-size:10px;color:var(--muted)}}
.metric-value{{font-size:16px;font-weight:700;font-family:'JetBrains Mono',monospace}}
.outlook-card{{background:linear-gradient(135deg,#eef4fb,#dde9f6);border:1px solid var(--border);border-left:4px solid var(--accent2);border-radius:12px;padding:24px 28px;margin-bottom:18px}}
.outlook-card h3{{font-size:16px;font-weight:700;color:var(--accent2);margin-bottom:12px}}
.outlook-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:12px}}
.scenario{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}}
.scenario h4{{font-size:13px;font-weight:700;margin-bottom:6px}}
.scenario.bull h4{{color:var(--up)}} .scenario.base h4{{color:var(--warn)}} .scenario.bear h4{{color:var(--down)}}
.scenario p{{font-size:12.5px;line-height:1.7;color:#2d3148}}
.risk-section{{background:linear-gradient(135deg,#fdf2f4,#f8f5ff);border:1px solid rgba(217,48,79,0.12);border-radius:12px;padding:24px 28px;margin-bottom:20px}}
.risk-section h2{{font-size:16px;font-weight:700;color:#1a1d2e;margin-bottom:14px}}
.risk-items{{list-style:none;display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.risk-item{{display:flex;align-items:flex-start;gap:8px;padding:10px 14px;border-radius:8px;background:rgba(255,255,255,0.6);font-size:13px;line-height:1.7}}
.risk-tag{{flex-shrink:0;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;margin-top:2px}}
.risk-tag.high{{background:rgba(26,95,180,0.15);color:var(--down)}}
.risk-tag.med{{background:rgba(212,139,7,0.15);color:var(--warn)}}
.sources-section{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 20px;margin-bottom:12px}}
.sources-section h3{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.sources-list{{margin:0;padding-left:18px;font-size:13px;line-height:1.8}}
.sources-list a{{color:var(--accent);text-decoration:none}}
.source-meta{{font-size:11px;color:var(--muted)}}
.placeholder{{background:repeating-linear-gradient(45deg,#fafbfc,#fafbfc 10px,#f4f5f9 10px,#f4f5f9 20px);border:2px dashed #c8cce0;border-radius:12px;padding:32px;text-align:center;color:var(--muted);font-size:13px;margin-bottom:18px}}
.placeholder strong{{color:var(--accent);display:block;font-size:15px;margin-bottom:6px}}
.footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:36px;padding-top:18px;border-top:1px solid var(--border)}}
.ai-disclaimer{{text-align:center;color:var(--muted);font-size:11px;margin-top:20px;padding:12px 16px;background:rgba(0,0,0,0.03);border-radius:8px;line-height:1.6}}
@media(max-width:900px){{
  .insight-grid,.theme-grid,.outlook-grid,.risk-items{{grid-template-columns:1fr}}
  .causal-chain{{flex-direction:column}}.cause-arrow{{transform:rotate(90deg);padding:4px 0}}
  .kpi-strip{{grid-template-columns:repeat(3,1fr)}}
}}
</style>
</head>
<body>
<a href="../index.html" class="back-link">← Back to Index</a>

<div class="header">
  <div class="header-left">
    <h1>Asia Weekly Brief | {week_label}</h1>
    <div class="date">{period_label} · 아시아 중심 주간 시황</div>
  </div>
  <div class="header-right">
    <div class="mood-badge">
      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{mood_color}"></span>
      {mood_text}
    </div>
  </div>
</div>

<div class="kpi-strip">
  {kpi_strip}
</div>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('story')">Asia Story</button>
  <button class="tab-btn" onclick="switchTab('country')">Country Drilldown</button>
  <button class="tab-btn" onclick="switchTab('themes')">Themes</button>
  <button class="tab-btn" onclick="switchTab('data')">Data</button>
  <button class="tab-btn" onclick="switchTab('outlook')">Outlook</button>
  <button class="tab-btn" onclick="switchTab('sources')">Sources</button>
</div>

<!-- TAB: Asia Story (placeholder) -->
<div id="tab-story" class="tab-panel active">
  <div class="story-hero">
    <h2>{week_label} 한 줄 요약</h2>
    <div class="story-text">
      <p><strong>[Claude 작성 영역]</strong> 핵심 내러티브 1단락 (가장 큰 그림)</p>
      <p><strong>[Claude 작성 영역]</strong> 국가별 명암 1단락 (어디가 강했고 어디가 약했나)</p>
      <p><strong>[Claude 작성 영역]</strong> 매크로 컨텍스트 1단락 (달러·금리·정상회담 등)</p>
    </div>
  </div>

  <div class="causal-chain">
    <div class="cause-node"><div class="node-label">월요일 트리거</div><div class="node-title">[작성 필요]</div><div class="node-detail">[작성 필요]</div><div class="node-impact">[작성 필요]</div></div>
    <div class="cause-arrow">→</div>
    <div class="cause-node"><div class="node-label">중반 흐름</div><div class="node-title">[작성 필요]</div><div class="node-detail">[작성 필요]</div><div class="node-impact">[작성 필요]</div></div>
    <div class="cause-arrow">→</div>
    <div class="cause-node"><div class="node-label">목요일</div><div class="node-title">[작성 필요]</div><div class="node-detail">[작성 필요]</div><div class="node-impact">[작성 필요]</div></div>
    <div class="cause-arrow">→</div>
    <div class="cause-node"><div class="node-label">금요일</div><div class="node-title">[작성 필요]</div><div class="node-detail">[작성 필요]</div><div class="node-impact">[작성 필요]</div></div>
    <div class="cause-arrow">→</div>
    <div class="cause-node"><div class="node-label">주말 마감</div><div class="node-title">[작성 필요]</div><div class="node-detail">[작성 필요]</div><div class="node-impact">[작성 필요]</div></div>
  </div>

  <div class="insight-grid">
    <div class="insight-card"><span class="badge">Theme 1</span><h3>[작성 필요] 인사이트 제목</h3><p>[Claude 작성 영역]</p></div>
    <div class="insight-card"><span class="badge">Theme 2</span><h3>[작성 필요]</h3><p>[Claude 작성 영역]</p></div>
    <div class="insight-card"><span class="badge">Theme 3</span><h3>[작성 필요]</h3><p>[Claude 작성 영역]</p></div>
    <div class="insight-card"><span class="badge">Theme 4</span><h3>[작성 필요]</h3><p>[Claude 작성 영역]</p></div>
    <div class="insight-card"><span class="badge">Theme 5</span><h3>[작성 필요]</h3><p>[Claude 작성 영역]</p></div>
    <div class="insight-card"><span class="badge">Theme 6</span><h3>[작성 필요]</h3><p>[Claude 작성 영역]</p></div>
  </div>
</div><!-- /tab-story -->

<!-- TAB: Country Drilldown (placeholder) -->
<div id="tab-country" class="tab-panel">
  <div class="placeholder"><strong>Country Drilldown — Claude 작성 영역</strong>국가별 6 섹션 (🇨🇳 중국 · 🇯🇵 일본 · 🇹🇼 대만 · 🇮🇳 인도 · 🇭🇰 홍콩 · 🇰🇷 한국).<br>각 섹션에 country-section 클래스 사용. references/story-template.md 참조.</div>
</div><!-- /tab-country -->

<!-- TAB: Themes (placeholder) -->
<div id="tab-themes" class="tab-panel">
  <div class="placeholder"><strong>Themes — Claude 작성 영역</strong>횡단 주제 4~5개 (반도체 디커플링·달러 강세·AI 인프라·정책 리스크·지정학).<br>theme-card 클래스 사용. references/story-template.md 참조.</div>
</div><!-- /tab-themes -->

<!-- TAB: Data (auto-filled) -->
<div id="tab-data" class="tab-panel">
  <h2 style="font-size:18px;font-weight:700;color:#1a1d2e;margin:8px 0 14px 0;padding-bottom:6px;border-bottom:2px solid #F58220">아시아 지수 {week_label} 변동률</h2>
  <table class="heatmap">
    <thead><tr><th>지수</th><th>국가/지역</th><th>{data['ref_date']} 종가</th><th>{data['friday']} 종가</th><th>WTD %</th></tr></thead>
    <tbody>
      {index_table}
    </tbody>
  </table>

  <h2 style="font-size:18px;font-weight:700;color:#1a1d2e;margin:22px 0 14px 0;padding-bottom:6px;border-bottom:2px solid #F58220">아시아 통화 {week_label} 변동률</h2>
  <table class="heatmap">
    <thead><tr><th>통화쌍</th><th>{data['ref_date']}</th><th>{data['friday']}</th><th>WTD %</th><th>비고</th></tr></thead>
    <tbody>
      {fx_table}
    </tbody>
  </table>

  <h2 style="font-size:18px;font-weight:700;color:#1a1d2e;margin:22px 0 14px 0;padding-bottom:6px;border-bottom:2px solid #F58220">아시아 종목 {week_label} TOP 20</h2>
  <table class="heatmap">
    <thead><tr><th>#</th><th>종목</th><th>국가</th><th>비중%</th><th>{data['ref_date']}</th><th>{data['friday']}</th><th>WTD %</th></tr></thead>
    <tbody>
      {top20_rows}
    </tbody>
  </table>

  <h2 style="font-size:18px;font-weight:700;color:#1a1d2e;margin:22px 0 14px 0;padding-bottom:6px;border-bottom:2px solid #F58220">아시아 종목 {week_label} BOTTOM 20</h2>
  <table class="heatmap">
    <thead><tr><th>#</th><th>종목</th><th>국가</th><th>비중%</th><th>{data['ref_date']}</th><th>{data['friday']}</th><th>WTD %</th></tr></thead>
    <tbody>
      {bot20_rows}
    </tbody>
  </table>

  <h2 style="font-size:18px;font-weight:700;color:#1a1d2e;margin:22px 0 14px 0;padding-bottom:6px;border-bottom:2px solid #F58220">국가별 종합</h2>
  <table class="heatmap">
    <thead><tr><th>국가</th><th>매칭/유니버스</th><th>비중 합계</th><th>단순평균 WTD %</th><th>가중평균 WTD %</th></tr></thead>
    <tbody>
      {country_table}
    </tbody>
  </table>
</div><!-- /tab-data -->

<!-- TAB: Outlook (placeholder + required risk-section markers) -->
<div id="tab-outlook" class="tab-panel">
  <div class="outlook-card">
    <h3>{week_label} 다음 주 시나리오 — [Claude 작성 영역]</h3>
    <p>[작성 필요] 핵심 미해결 변수 3가지...</p>
    <div class="outlook-grid">
      <div class="scenario bull"><h4>🐂 Bull (확률 ~%)</h4><p>[작성 필요]</p></div>
      <div class="scenario base"><h4>📊 Base (확률 ~%)</h4><p>[작성 필요]</p></div>
      <div class="scenario bear"><h4>🐻 Bear (확률 ~%)</h4><p>[작성 필요]</p></div>
    </div>
  </div>

  <div class="risk-section">
    <h2>⚠️ 주목 리스크 TOP 5 — [Claude 작성 영역]</h2>
    <ul class="risk-items">
      <li class="risk-item"><span class="risk-tag high">高</span><div>[작성 필요]</div></li>
      <li class="risk-item"><span class="risk-tag high">高</span><div>[작성 필요]</div></li>
      <li class="risk-item"><span class="risk-tag high">高</span><div>[작성 필요]</div></li>
      <li class="risk-item"><span class="risk-tag med">中</span><div>[작성 필요]</div></li>
      <li class="risk-item"><span class="risk-tag med">中</span><div>[작성 필요]</div></li>
    </ul>
  </div>

  <div class="theme-card">
    <h3><span class="theme-tag">데이터 캘린더</span> 다음 주 모니터링</h3>
    <p>[Claude 작성 영역] 5~7개 이벤트...</p>
  </div>
</div><!-- /tab-outlook -->

<!-- TAB: Sources (partial auto-fill) -->
<div id="tab-sources" class="tab-panel">
  <div class="sources-section">
    <h3>1. 시장 데이터 (Quotes)</h3>
    <ul class="sources-list">
      <li><strong>history/market_data.csv</strong> — Snowflake MKT100 정본 미러 <span class="source-meta">아시아 종목·지수·환율 {data['ref_date']}~{data['friday']} 시계열</span></li>
      <li><strong>history/아시아종목.xlsx</strong> — 운용 유니버스 180종목 (중국 71 · 인도 38 · 일본 44 · 대만 5 · 홍콩 9 · 호주 2 · 베트남 10 · 인도네시아 1)</li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>2. 미래에셋증권 Research Digest</h3>
    <ul class="sources-list">
      <li><strong>[Claude 작성]</strong> W##-3, W##-2, W##-1, W## 4건 링크 + 핵심 메시지</li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>3. 미래에셋증권 핵심 단편 보고서 (원문)</h3>
    <ul class="sources-list">
      <li><strong>[Claude 작성]</strong> 「보고서명」 핵심 메시지 한 줄</li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>4. 외부 참고 자료 (웹 검색)</h3>
    <ul class="sources-list">
      <li><strong>[Claude 작성]</strong> 외부 URL · 출처</li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>5. 본 보고서 산출 방법론</h3>
    <ul class="sources-list" style="list-style:none;padding-left:0">
      <li><strong>기간 정의</strong>: {week_label} = {period_label} ({data['n_business_days']}영업일)</li>
      <li><strong>WTD 변동률</strong>: {data['ref_date']} 종가 → {data['friday']} 종가</li>
      <li><strong>가중평균</strong>: Σ(비중 × WTD%) / Σ(비중)</li>
      <li><strong>유니버스 매칭</strong>: {data['n_matched']}/{data['n_universe']} ({100*data['n_matched']/data['n_universe']:.1f}%) — 매칭은 종목명 정확 일치 기준</li>
      <li><strong>제한</strong>: 미매칭 종목은 가중평균에서 제외 (Coverage 한계 명시)</li>
      <li><strong>지수·환율</strong>: history/market_data.csv (yfinance 백필) — 동일 윈도우</li>
    </ul>
  </div>

  <div class="ai-disclaimer">
    ⚠️ 본 보고서는 미래에셋증권 다이제스트 및 history/market_data.csv를 기반으로 생성됐습니다.
    수치·해석은 작성 시점 기준이며, 투자 권유가 아닙니다.
  </div>
</div><!-- /tab-sources -->

<div class="footer">
  Asia Weekly Brief · {week_label} ({period_label}) · 생성: {data['generated_at']} · market_summary 프로젝트
</div>

<script>
function switchTab(id){{
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  event.currentTarget.classList.add('active');
  window.scrollTo({{top:0,behavior:'smooth'}});
}}
</script>
</body>
</html>
"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# AI Tab Generation (Claude API)
# ─────────────────────────────────────────────────────────────────────────────

_AI_MODEL = "sonnet"  # claude CLI --model 값
_CLAUDE_BIN = r"C:\Users\user\.local\bin\claude.exe"  # Task Scheduler PATH 보장용

_RULES_PREAMBLE = """당신은 아시아 주식 시장 전문 애널리스트입니다. 아래 규칙을 반드시 준수하십시오.
1. 문체: 합니다체 (했습니다, 됐습니다, 입니다). 반말 금지.
2. Forward-looking 금지: 보고서 기간 금요일 종가 이후 데이터 사용 금지. "~할 수 있다", "~가능성이 있다"만 허용.
3. 수치 정확성: 제공된 데이터의 수치만 사용. 임의 추측 금지.
4. 인과관계 방향: 과거→미래 순서만 허용.
5. HTML만 출력: 지정 CSS 클래스만 사용. Markdown·설명 불필요.
6. 종목명: 데이터에 있는 영문명 그대로 사용.
"""

def _build_data_brief(data: dict) -> str:
    """데이터를 Claude 프롬프트용 텍스트 요약으로 변환."""
    lines = [
        f"## 대상 기간: {data['week']} ({data['monday']} ~ {data['friday']})",
        f"기준 종가: {data['ref_date']} → {data['friday']}",
        f"유니버스 매칭: {data['n_matched']}/{data['n_universe']}종목",
        "",
        "## 아시아 지수 WTD%",
    ]
    for code, label_region in {
        "KOSPI": "코스피(한국)", "KOSDAQ": "코스닥(한국)", "Nikkei225": "Nikkei225(일본)",
        "HSI": "HSI항셍(홍콩)", "Shanghai": "상하이종합(중국)", "TWSE": "TWSE가권(대만)",
        "NIFTY50": "NIFTY50(인도)", "MSCI EM": "MSCI EM(신흥국)",
    }.items():
        d = data["indices"].get(code)
        if d:
            lines.append(f"  {label_region}: {d['pct']:+.2f}% ({d['start']:,.2f}→{d['end']:,.2f})")

    lines += ["", "## FX WTD%"]
    for code in ["USD/KRW", "USD/JPY", "USD/INR", "USD/CNY", "DXY"]:
        d = data["fx"].get(code)
        if d:
            lines.append(f"  {code}: {d['pct']:+.2f}% ({d['start']:.4f}→{d['end']:.4f})")

    lines += ["", "## 국가별 종합 (단순평균 WTD% | 가중평균 WTD% | 매칭/유니버스)"]
    for c, info in data["countries"].items():
        if info["n_matched"] > 0:
            lines.append(
                f"  {c}: 단순{info['simple_avg']:+.2f}% | 가중{info['weighted_avg']:+.2f}%"
                f" | {info['n_matched']}/{info['n_universe']} | 비중합{info['weight_total_matched']:.1f}%"
            )
            # Top 3 / Bottom 3
            stocks = info.get("stocks", [])
            top3 = sorted(stocks, key=lambda x: x["pct"], reverse=True)[:3]
            bot3 = sorted(stocks, key=lambda x: x["pct"])[:3]
            if top3:
                lines.append("    TOP: " + ", ".join(f"{s['name']} {s['pct']:+.1f}%" for s in top3))
            if bot3:
                lines.append("    BOT: " + ", ".join(f"{s['name']} {s['pct']:+.1f}%" for s in bot3))

    return "\n".join(lines)


def _find_digest_info(week_label: str) -> str:
    """최신 securities digest 파일 4건 정보 수집."""
    import re as _re
    research_dir = PROJECT_ROOT / "output" / "securities" / "digest"
    digests = sorted(research_dir.glob("digest_2026-W*.html"), reverse=True)
    # 현재 주 포함 최대 4건
    items = []
    for p in digests[:4]:
        m = _re.search(r"digest_(2026-W\d+)\.html", p.name)
        if not m:
            continue
        wk = m.group(1)
        # Extract theme names from HTML
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")[:8000]
            themes = _re.findall(r'class="theme-name">(.*?)</h2>', txt)
            theme_str = " · ".join(themes) if themes else "테마 미확인"
        except Exception:
            theme_str = "읽기 실패"
        rel = f"../../securities/digest/digest_{wk}.html"
        items.append(f'<li><a href="{rel}"><strong>{wk} Digest</strong></a> — {theme_str}</li>')
    return "\n      ".join(items) if items else '<li>Digest 파일 없음</li>'


def _replace_tab(html: str, tab_id: str, new_inner: str) -> str:
    """탭 div 내부 content를 교체. <!-- /tab-{id} --> 마커 기준."""
    import re as _re
    pat = (
        rf'(<div id="tab-{tab_id}"[^>]*>)'  # opening tag
        rf'.*?'                              # existing content
        rf'(</div><!-- /tab-{tab_id} -->)'  # closing marker
    )
    repl = rf'\1\n{new_inner}\n\2'
    result, n = _re.subn(pat, repl, html, count=1, flags=_re.DOTALL)
    if n == 0:
        print(f"[asia-weekly][ai] WARNING: tab-{tab_id} 교체 실패 (마커 없음)")
    return result


def _call_claude_cli(prompt: str, label: str = "", timeout: int = 480) -> str:
    """claude CLI를 subprocess stdin 파이프로 호출하여 결과 반환."""
    import subprocess, shutil
    tag = f"[asia-weekly][ai]{f'[{label}]' if label else ''}"
    print(f"{tag} 호출 중...", flush=True)
    # 절대경로 우선, 없으면 PATH에서 탐색
    import os
    claude_bin = _CLAUDE_BIN if os.path.isfile(_CLAUDE_BIN) else (shutil.which("claude") or "claude")
    result = subprocess.run(
        [claude_bin, "-p", "--model", _AI_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if result.returncode != 0:
        err = (result.stderr or "").strip()[:400]
        raise RuntimeError(f"claude CLI 오류 (exit {result.returncode}): {err}")
    out = result.stdout.strip()
    print(f"{tag} 완료 ({len(out)}자)", flush=True)
    return out


def _fill_ai_tabs(html: str, data: dict) -> str:
    """claude CLI로 5개 내러티브 탭을 생성하여 skeleton HTML에 주입."""
    brief = _build_data_brief(data)
    week_label = data["week"]
    next_week_num = int(week_label.split("-W")[1]) + 1
    next_week = f"{week_label.split('-W')[0]}-W{next_week_num}"
    digest_items = _find_digest_info(week_label)

    # ── CALL 1: Story Tab ──────────────────────────────────────────────────
    story_prompt = f"""{_RULES_PREAMBLE}
다음 데이터를 바탕으로 Asia Weekly 보고서의 Story 탭 HTML을 작성하십시오.

{brief}

## 출력 규칙
- HTML만 출력 (설명·마크다운 코드블록 없이)
- 아래 세 블록을 순서대로 출력

## 블록 1: story-hero
<div class="story-hero">
  <h2>[한 줄 핵심 요약 15자 이내]</h2>
  <div class="story-text">
    <p>[이 주를 관통한 핵심 테마. hl-up/hl-down/hl-warn/hl-accent 스팬 활용. 2~3문장.]</p>
    <p>[국가별 명암: 강한 국가·약한 국가, 핵심 종목 수치 포함. 2~3문장.]</p>
    <p>[매크로 컨텍스트: 금리·환율·지정학 2문장.]</p>
  </div>
</div>

## 블록 2: causal-chain (요일별 5노드, cause-arrow로 연결)
<div class="causal-chain">
  <div class="cause-node">
    <div class="node-label">월요일</div>
    <div class="node-title">[트리거]</div>
    <div class="node-detail">[2문장]</div>
    <div class="node-impact up">[한 줄 영향]</div>
  </div>
  <div class="cause-arrow">→</div>
  [화요일, 수요일, 목요일, 금요일 동일 구조]
</div>

## 블록 3: insight-grid (6개 insight-card)
<div class="insight-grid">
  <div class="insight-card">
    <span class="badge">[테마명]</span>
    <h3>[인사이트 제목]</h3>
    <p>[2~3문장]</p>
    <div class="metric-row">
      <div class="metric-item"><div class="metric-label">[종목]</div><div class="metric-value up">[수치]</div></div>
      <div class="metric-item"><div class="metric-label">[종목]</div><div class="metric-value down">[수치]</div></div>
    </div>
  </div>
  [6개 총합]
</div>

node-impact / metric-value 클래스: up=상승, down=하락, flat=보합. 데이터에 없는 수치 사용 금지."""

    story_html = _call_claude_cli(story_prompt, "Story")
    html = _replace_tab(html, "story", story_html)

    import re as _re
    kospi_pct = data["indices"].get("KOSPI", {}).get("pct", 0)
    kosdaq_pct = data["indices"].get("KOSDAQ", {}).get("pct", 0)

    # ── CALL 2: Country Drilldown ──────────────────────────────────────────
    country_prompt = f"""{_RULES_PREAMBLE}
다음 데이터를 바탕으로 Asia Weekly 보고서의 Country Drilldown 탭 HTML을 작성하십시오.

{brief}

## 출력 규칙
- HTML 내부 콘텐츠만 출력 (설명 없이, 탭 div 태그 자체는 제외)
- 각 국가: <div class="country-section cn|jp|tw|in|hk|kr"> 구조
  - <div class="country-head"><span class="country-flag">🏳</span><span class="country-title">국가명</span><span class="country-sub">단순 X% · 가중 Y% · N/N 매칭</span></div>
  - 2~3단락 <p> 서술
  - <h4>🔺 상위 종목</h4> + <table class="stock-table"><thead><tr><th>종목</th><th>카테고리</th><th>WTD %</th></tr></thead><tbody>...</tbody></table>
  - <h4>🔻 하위 종목</h4> + 동일 구조 표
- 국가 순서: 단순평균 WTD% 내림차순 (일본→대만→중국→호주→베트남→인도→홍콩→인도네시아)
- 한국은 마지막에 class="kr" 컨텍스트 섹션 추가 (KOSPI {kospi_pct:+.2f}%, KOSDAQ {kosdaq_pct:+.2f}%)
- 데이터에 없는 수치 사용 금지. 합니다체."""

    raw_country = _call_claude_cli(country_prompt, "Country")
    html = _replace_tab(html, "country", raw_country)

    # ── CALL 3: Themes + Outlook + Sources ────────────────────────────────
    digest_items = _find_digest_info(week_label)

    tos_prompt = f"""{_RULES_PREAMBLE}
다음 데이터를 바탕으로 Asia Weekly 보고서의 Themes·Outlook·Sources 3탭 HTML을 작성하십시오.

{brief}

## 출력 규칙
- HTML만 출력 (설명 없이)
- 반드시 아래 3개 XML 태그로 구분 출력

<TAB_THEMES>
4~5개 theme-card. 각 카드:
<div class="theme-card">
  <h3><span class="theme-tag">Theme N</span> 제목</h3>
  <p>본문 2~3단락</p>
  <div class="theme-grid">
    <div class="theme-side"><h5>소제목</h5><ul><li>항목</li></ul></div>
    <div class="theme-side"><h5>소제목</h5><ul><li>항목</li></ul></div>
  </div>
</div>
</TAB_THEMES>

<TAB_OUTLOOK>
<div class="outlook-card">
  <h3>{week_label} → {next_week} 시나리오</h3>
  <p>핵심 미결 변수 2~3개</p>
  <div class="outlook-grid">
    <div class="scenario bull"><h4>🐂 Bull (NN%)</h4><p>시나리오</p></div>
    <div class="scenario base"><h4>📊 Base (NN%)</h4><p>시나리오</p></div>
    <div class="scenario bear"><h4>🐻 Bear (NN%)</h4><p>시나리오</p></div>
  </div>
</div>
<div class="risk-section">
  <h2>⚠️ 주목 리스크 TOP 5</h2>
  <ul class="risk-items">
    <li class="risk-item"><span class="risk-tag high">高</span><div><strong>제목</strong><br>한 문장</div></li>
    <li class="risk-item"><span class="risk-tag high">高</span><div>...</div></li>
    <li class="risk-item"><span class="risk-tag high">高</span><div>...</div></li>
    <li class="risk-item"><span class="risk-tag med">中</span><div>...</div></li>
    <li class="risk-item"><span class="risk-tag med">中</span><div>...</div></li>
  </ul>
</div>
<div class="theme-card">
  <h3><span class="theme-tag">W+1 캘린더</span> 다음 주 모니터링</h3>
  <table class="stock-table">
    <thead><tr><th>날짜</th><th>이벤트</th><th>시장 영향</th></tr></thead>
    <tbody>
      <tr><td>날짜</td><td>이벤트명</td><td style="font-size:12px;color:var(--muted)">영향</td></tr>
    </tbody>
  </table>
</div>
</TAB_OUTLOOK>

<TAB_SOURCES>
<div class="sources-section">
  <h3>3. 미래에셋증권 핵심 단편 보고서</h3>
  <ul class="sources-list">
    <li>「보고서명」 — 핵심 메시지 한 줄 (3~4건)</li>
  </ul>
</div>
<div class="sources-section">
  <h3>4. 외부 참고 자료</h3>
  <ul class="sources-list">
    <li><strong>기관명</strong> — 설명 (3~4건, URL 없이)</li>
  </ul>
</div>
</TAB_SOURCES>

데이터에 없는 수치 사용 금지. 합니다체 유지."""

    raw3 = _call_claude_cli(tos_prompt, "Themes+Outlook+Sources")

    for tab_id, tag in [("themes", "TAB_THEMES"), ("outlook", "TAB_OUTLOOK"), ("sources", "TAB_SOURCES")]:
        m = _re.search(rf"<{tag}>(.*?)</{tag}>", raw3, _re.DOTALL)
        if m:
            content = m.group(1).strip()
            if tab_id == "sources":
                html = _inject_sources(html, data, content, digest_items)
            else:
                html = _replace_tab(html, tab_id, content)
        else:
            print(f"[asia-weekly][ai] WARNING: {tag} 파싱 실패")

    return html


def _inject_sources(html: str, data: dict, ai_sections: str, digest_items: str = "") -> str:
    """Sources 탭: 자동 생성 섹션 1·5 + Digest 링크 섹션 2 + AI 생성 섹션 3~4 조합."""
    week_label = data["week"]
    period_label = f"{data['monday']} ~ {data['friday']}"
    # 국가별 매칭 현황
    country_match_lines = []
    for c, info in data["countries"].items():
        if info["n_matched"] > 0:
            country_match_lines.append(
                f"{c} {info['n_matched']}/{info['n_universe']}"
                f"({100*info['n_matched']/info['n_universe']:.0f}%)"
            )
    match_summary = " · ".join(country_match_lines)

    digest_section = ""
    if digest_items:
        digest_section = f"""  <div class="sources-section">
    <h3>2. 미래에셋증권 Research Digest — 최근 4주</h3>
    <ul class="sources-list">
      {digest_items}
    </ul>
  </div>
"""

    sources_inner = f"""  <div class="sources-section">
    <h3>1. 시장 데이터 (Quotes)</h3>
    <ul class="sources-list">
      <li><strong>history/market_data.csv</strong> — Snowflake MKT100 정본 미러 <span class="source-meta">아시아 종목·지수·환율 {data['ref_date']}~{data['friday']} 시계열</span></li>
      <li><strong>history/아시아종목.xlsx</strong> — 운용 유니버스 {data['n_universe']}종목</li>
      <li><strong>매칭 현황</strong>: {data['n_matched']}/{data['n_universe']} ({100*data['n_matched']/data['n_universe']:.1f}%) — {match_summary}</li>
    </ul>
  </div>
  {digest_section}  {ai_sections}
  <div class="sources-section">
    <h3>5. 본 보고서 산출 방법론</h3>
    <ul class="sources-list" style="list-style:none;padding-left:0">
      <li><strong>기간 정의</strong>: {week_label} = {period_label} ({data['n_business_days']}영업일)</li>
      <li><strong>WTD 변동률</strong>: {data['ref_date']} 종가 → {data['friday']} 종가</li>
      <li><strong>가중평균</strong>: Σ(비중 × WTD%) / Σ(비중)</li>
      <li><strong>유니버스 매칭</strong>: {data['n_matched']}/{data['n_universe']} ({100*data['n_matched']/data['n_universe']:.1f}%) — 종목명 정확 일치</li>
      <li><strong>제한</strong>: 미매칭 종목은 가중평균에서 제외</li>
      <li><strong>생성 도구</strong>: scripts/generate_asia_weekly.py + Claude {_AI_MODEL}</li>
    </ul>
  </div>
  <div class="ai-disclaimer">
    ⚠️ 본 보고서는 미래에셋증권 다이제스트 및 history/market_data.csv를 기반으로 Claude AI가 생성했습니다.
    수치·해석은 작성 시점({data['generated_at']}) 기준이며, 투자 권유가 아닙니다.
  </div>"""

    return _replace_tab(html, "sources", sources_inner)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Generate Asia Weekly Brief — data + AI narrative.")
    ap.add_argument("target_date", nargs="?", help="YYYY-MM-DD (any business day of the target week). Default: most recent Friday.")
    ap.add_argument("--no-ai", action="store_true", help="Skip Claude API calls; write skeleton only.")
    args = ap.parse_args()

    if args.target_date:
        target = datetime.strptime(args.target_date, "%Y-%m-%d").date()
    else:
        target = date.today()

    monday, friday, week_label = get_week_window(target)
    print(f"[asia-weekly] Target week: {week_label} ({monday} ~ {friday})")

    # Load data
    universe = load_universe()
    print(f"[asia-weekly] Universe: {len(universe)} stocks loaded")

    df = load_market()
    end_date = get_last_trading_day_of_week(friday, df)
    if end_date != friday:
        print(f"[asia-weekly] {friday} has no trading data (holiday?) — using {end_date} as week end")
    ref_date = get_prev_friday_close(monday, df)
    print(f"[asia-weekly] Reference close: {ref_date} → {end_date}")

    # Compute stock returns
    stock_names = universe["name"].dropna().unique().tolist()
    stock_returns = compute_wtd_returns(df, stock_names, ref_date, end_date)
    print(f"[asia-weekly] Stock matches: {len(stock_returns)}/{len(stock_names)}")

    # Compute index/FX returns
    index_returns = compute_wtd_returns(df, ASIA_INDICES, ref_date, end_date)
    fx_returns = compute_wtd_returns(df, ASIA_FX, ref_date, end_date)
    print(f"[asia-weekly] Index: {len(index_returns)}/{len(ASIA_INDICES)}, FX: {len(fx_returns)}/{len(ASIA_FX)}")

    # Country summary
    countries = build_country_summary(universe, stock_returns)
    for c, info in countries.items():
        if info["n_matched"] > 0:
            print(f"[asia-weekly]   {c}: matched {info['n_matched']}/{info['n_universe']}, simple={info['simple_avg']:+.2f}%, weighted={info['weighted_avg']:+.2f}%")

    # Business day count — actual trading days monday..end_date (KR holiday-aware)
    business_days = sum(1 for i in range((end_date - monday).days + 1)
                       if is_business_day(monday + timedelta(days=i)))

    # Build data dict. "friday" holds the actual last trading day used for WTD
    # (may be earlier than the calendar Friday if it's a KR holiday, e.g. 제헌절).
    data = {
        "week":             week_label,
        "monday":           monday.isoformat(),
        "friday":           end_date.isoformat(),
        "ref_date":         ref_date.isoformat(),
        "n_business_days":  business_days,
        "n_universe":       len(stock_names),
        "n_matched":        len(stock_returns),
        "indices":          index_returns,
        "fx":               fx_returns,
        "countries":        countries,
        "generated_at":     datetime.now().strftime("%Y-%m-%d %H:%M KST"),
    }

    # Write JSON
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"{week_label}_asia_data.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[asia-weekly] Data → {json_path}")

    # Render HTML skeleton
    html = render_html(data)

    # Claude AI 내러티브 탭 생성
    if not args.no_ai:
        print("[asia-weekly] Claude AI 탭 생성 시작 (Story / Country / Themes / Outlook / Sources)...")
        try:
            html = _fill_ai_tabs(html, data)
            print("[asia-weekly] AI 탭 생성 완료")
        except Exception as exc:
            print(f"[asia-weekly][ai] ERROR: {exc} — 스켈레톤으로 저장")
    else:
        print("[asia-weekly] --no-ai: 스켈레톤만 저장")

    html_path = OUTPUT_DIR / f"{week_label}_asia.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[asia-weekly] HTML → {html_path}")

    # PM 랜딩 페이지 갱신
    generate_pm_index()
    generate_pm_hub()
    print(f"[asia-weekly] Done. Open: {html_path}")


def generate_pm_index():
    """output/pm/asia_weekly/index.html — PM 전용 Asia Weekly 랜딩 페이지"""
    import glob
    import re as _re

    pm_dir = PROJECT_ROOT / "output" / "pm" / "asia_weekly"
    pm_dir.mkdir(parents=True, exist_ok=True)

    # *_asia.html 수집 (최신순)
    asia_files = sorted(
        glob.glob(str(OUTPUT_DIR / "*_asia.html")), reverse=True
    )

    items_html = ""
    for i, path in enumerate(asia_files):
        fname = Path(path).name
        week_label = fname.replace("_asia.html", "")  # e.g. "2026-W20"

        # HTML에서 날짜 범위 추출
        date_range = ""
        try:
            head = Path(path).read_text(encoding="utf-8")[:20000]
            m = _re.search(r'class="date">\s*([\d-]+)\s*~\s*([\d-]+)', head)
            if m:
                date_range = f"{m.group(1)} ~ {m.group(2)}"
        except Exception:
            pass

        label = f"{week_label}  {date_range}" if date_range else week_label
        badge = '<span class="badge">Latest</span> ' if i == 0 else ""
        # 상대 경로: pm/asia_weekly/ → summary/weekly/
        href = f"../../summary/weekly/{fname}"
        items_html += f'    <li><a href="{href}">{badge}{label}</a></li>\n'

    if not items_html:
        items_html = '    <li style="color:#7c8298;font-style:italic;padding:12px 18px">No Asia Weekly reports yet.</li>\n'

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Asia Weekly PM | Market Summary</title>
<link rel="icon" href="../../favicon.svg" type="image/svg+xml">
<style>
  @import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400&display=swap');
  body {{ font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic',sans-serif; background:#f4f5f9; color:#2d3148; padding:40px 24px; max-width:640px; margin:0 auto; }}
  h1 {{ font-size:26px; font-weight:700; margin-bottom:4px; }}
  .sub {{ font-size:14px; color:#7c8298; margin-bottom:32px; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ margin-bottom:10px; }}
  li a {{
    display:block; padding:14px 20px; background:#fff; border:1px solid #e0e3ed;
    border-radius:10px; text-decoration:none; color:#2d3148; font-size:14px; font-weight:500;
    transition:all .15s; box-shadow:0 1px 3px rgba(0,0,0,0.04);
    font-family:'JetBrains Mono','Spoqa Han Sans Neo',monospace;
  }}
  li a:hover {{ border-color:#F58220; color:#F58220; transform:translateX(4px); }}
  .badge {{
    display:inline-block; background:#F58220; color:#fff; font-size:11px; font-weight:700;
    padding:2px 8px; border-radius:10px; margin-right:8px; vertical-align:middle;
    font-family:'Spoqa Han Sans Neo',sans-serif;
  }}
  .back {{ font-size:13px; color:#7c8298; text-decoration:none; display:inline-block; margin-bottom:24px; }}
  .back:hover {{ color:#F58220; }}
</style>
</head>
<body>
  <a href="../../summary/index.html" class="back">← Market Summary</a>
  <h1>🌏 Asia Weekly</h1>
  <p class="sub">아시아 주간 시황 브리프 — 매주 일요일 발행</p>
  <ul>
{items_html}  </ul>
</body>
</html>"""

    pm_index = pm_dir / "index.html"
    pm_index.write_text(html, encoding="utf-8")
    print(f"[asia-weekly] PM index → {pm_index}")


def generate_pm_hub():
    """output/pm/index.html — PM 허브 (모든 PM 페이지 진입점)"""
    pm_dir = PROJECT_ROOT / "output" / "pm"
    pm_dir.mkdir(parents=True, exist_ok=True)

    # 등록된 PM 섹션 (향후 weekly, daily 추가 시 여기에 append)
    sections = [
        {
            "href": "asia_weekly/",
            "icon": "🌏",
            "title": "Asia Weekly",
            "desc": "아시아 주간 시황 브리프 — 매주 일요일 발행",
        },
    ]

    cards_html = ""
    for s in sections:
        cards_html += f"""    <li>
      <a href="{s['href']}">
        <span class="icon">{s['icon']}</span>
        <span class="info">
          <span class="title">{s['title']}</span>
          <span class="desc">{s['desc']}</span>
        </span>
      </a>
    </li>\n"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PM Hub | Market Summary</title>
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<style>
  @import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
  body {{ font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic',sans-serif; background:#f4f5f9; color:#2d3148; padding:40px 24px; max-width:640px; margin:0 auto; }}
  h1 {{ font-size:26px; font-weight:700; margin-bottom:4px; }}
  .sub {{ font-size:14px; color:#7c8298; margin-bottom:32px; }}
  ul {{ list-style:none; padding:0; margin:0; }}
  li {{ margin-bottom:12px; }}
  li a {{
    display:flex; align-items:center; gap:16px;
    padding:16px 20px; background:#fff; border:1px solid #e0e3ed;
    border-radius:12px; text-decoration:none; color:#2d3148;
    transition:all .15s; box-shadow:0 1px 3px rgba(0,0,0,0.04);
  }}
  li a:hover {{ border-color:#F58220; transform:translateX(4px); }}
  .icon {{ font-size:28px; line-height:1; flex-shrink:0; }}
  .info {{ display:flex; flex-direction:column; gap:3px; }}
  .title {{ font-size:15px; font-weight:700; color:#2d3148; }}
  li a:hover .title {{ color:#F58220; }}
  .desc {{ font-size:13px; color:#7c8298; }}
  .back {{ font-size:13px; color:#7c8298; text-decoration:none; display:inline-block; margin-bottom:24px; }}
  .back:hover {{ color:#F58220; }}
</style>
</head>
<body>
  <a href="../summary/index.html" class="back">← Market Summary</a>
  <h1>PM Hub</h1>
  <p class="sub">포트폴리오 매니저를 위한 시황 브리핑 모음</p>
  <ul>
{cards_html}  </ul>
</body>
</html>"""

    hub_path = pm_dir / "index.html"
    hub_path.write_text(html, encoding="utf-8")
    print(f"[asia-weekly] PM hub → {hub_path}")


if __name__ == "__main__":
    main()
