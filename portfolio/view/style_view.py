"""Style/Factor rotation view — 스타일·팩터 로테이션 의견.

US 5대 팩터 ETF(Growth/Value/Quality/Momentum/LowVol) + KR 대형/소형/성장 비교.
금리 환경 × VIX 국면 × 매크로 Regime → 어떤 스타일에 투자할지 결정.

Usage:
    python -m portfolio.view.style_view --date 2026-04-14 --html
"""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "style"
MARKET_CSV = ROOT / "history" / "market_data.csv"
MACRO_CSV  = ROOT / "history" / "macro_indicators.csv"

# ── Style/Factor definitions ──────────────────────────────────────────────

US_STYLES = {
    "FA_US_GROWTH":   {"name": "US Growth",   "etf": "IVW",  "prefer": ["Goldilocks"],                   "vix_prefer": "low",    "rate_prefer": "falling"},
    "FA_US_VALUE":    {"name": "US Value",    "etf": "IVE",  "prefer": ["Reflation", "Stagflation"],     "vix_prefer": "any",    "rate_prefer": "rising"},
    "FA_US_QUALITY":  {"name": "US Quality",  "etf": "QUAL", "prefer": ["Deflation", "Stagflation"],     "vix_prefer": "high",   "rate_prefer": "any"},
    "FA_US_MOMENTUM": {"name": "US Momentum", "etf": "MTUM", "prefer": ["Goldilocks", "Reflation"],      "vix_prefer": "low",    "rate_prefer": "any"},
    "FA_US_LOWVOL":   {"name": "US Low Vol",  "etf": "USMV", "prefer": ["Deflation", "Stagflation"],     "vix_prefer": "high",   "rate_prefer": "any"},
}

KR_STYLES = {
    "EQ_KOSPI":       {"name": "KOSPI 대형", "etf": "KOSPI"},
    "EQ_KOSDAQ":      {"name": "KOSDAQ 성장","etf": "KOSDAQ"},
    "EQ_RUSSELL2000": {"name": "US SmallCap","etf": "IWM"},
    "EQ_SP500":       {"name": "US LargeCap","etf": "SPY"},
}

# Regime × Style 매핑: 선호 스타일 코드 목록
REGIME_STYLE_MAP = {
    "Goldilocks":  ["FA_US_GROWTH", "FA_US_MOMENTUM", "EQ_KOSDAQ", "EQ_RUSSELL2000"],
    "Reflation":   ["FA_US_VALUE",  "FA_US_MOMENTUM", "EQ_KOSPI"],
    "Stagflation": ["FA_US_VALUE",  "FA_US_QUALITY",  "FA_US_LOWVOL"],
    "Deflation":   ["FA_US_QUALITY","FA_US_LOWVOL",   "EQ_SP500"],
}

# VIX 레짐별 스타일 선호
VIX_STYLE_MAP = {
    "low":    ["FA_US_GROWTH", "FA_US_MOMENTUM", "EQ_KOSDAQ", "EQ_RUSSELL2000"],
    "medium": ["FA_US_VALUE",  "FA_US_QUALITY"],
    "high":   ["FA_US_QUALITY","FA_US_LOWVOL"],
}

SP500_CODE  = "EQ_SP500"
KOSPI_CODE  = "EQ_KOSPI"
VIX_CODE    = "RK_VIX"


# ── Data loaders ──────────────────────────────────────────────────────────

def _load_prices(date: str) -> pd.DataFrame:
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    target = pd.Timestamp(date)
    return wide[wide.index <= target].sort_index()


def _get_macro(date: str) -> dict:
    if not MACRO_CSV.exists():
        return {}
    df = pd.read_csv(MACRO_CSV, parse_dates=["DATE"])
    target = pd.Timestamp(date)
    df = df[df["DATE"] <= target]

    def _v(code):
        sub = df[df["INDICATOR_CODE"] == code]
        return float(sub.sort_values("DATE").iloc[-1]["VALUE"]) if not sub.empty else np.nan

    gdp = _v("US_GDP_QOQ")
    cpi = _v("US_CPI_YOY")
    fed = _v("US_FED_RATE")
    us_2y = _v("US_2Y_YIELD")
    us_10y = _v("US_10Y_YIELD")

    if np.isnan(gdp) or np.isnan(cpi):
        regime = "N/A"
    else:
        growing   = gdp > 0
        inflating = cpi > 3.0
        if growing and not inflating:
            regime = "Goldilocks"
        elif growing and inflating:
            regime = "Reflation"
        elif not growing and inflating:
            regime = "Stagflation"
        else:
            regime = "Deflation"

    # 금리 방향: 최근 3M 2Y yield 변화
    rate_direction = "stable"
    if not np.isnan(us_2y):
        sub2y = df[df["INDICATOR_CODE"] == "US_2Y_YIELD"].sort_values("DATE")
        if len(sub2y) >= 65:
            old_val = float(sub2y.iloc[-65]["VALUE"])
            diff = us_2y - old_val
            if diff > 0.2:
                rate_direction = "rising"
            elif diff < -0.2:
                rate_direction = "falling"

    return {
        "regime": regime,
        "fed_rate": fed,
        "us_2y": us_2y,
        "us_10y": us_10y,
        "rate_direction": rate_direction,
    }


# ── Signal calculators ────────────────────────────────────────────────────

def _momentum(px: pd.Series, days: int) -> float:
    if len(px) < days + 3:
        return np.nan
    return float(px.iloc[-1] / px.iloc[-days] - 1) * 100


def _trend_score(px: pd.Series) -> int:
    if len(px) < 55:
        return 0
    last  = float(px.iloc[-1])
    ma50  = float(px.tail(50).mean())
    if len(px) < 205:
        return 1 if last > ma50 else -1
    ma200 = float(px.tail(200).mean())
    if last > ma200 and last > ma50:   return 2
    elif last > ma200:                  return 1
    elif last < ma200 and last < ma50: return -2
    return -1


def _relative_mom(px: pd.Series, bench: pd.Series, days: int = 63) -> float:
    if len(px) < days + 3 or len(bench) < days + 3:
        return np.nan
    return float(px.iloc[-1] / px.iloc[-days] - 1) - float(bench.iloc[-1] / bench.iloc[-days] - 1)


def _composite(mom_1m, mom_3m, mom_6m, trend, rel_3m) -> float:
    def _s(v, w):
        return 0.0 if np.isnan(v) else np.sign(v) * w
    return round(
        _s(mom_1m, 0.15) + _s(mom_3m, 0.25) + _s(mom_6m, 0.25)
        + (trend / 2 * 0.20)
        + _s(rel_3m, 0.15),
        3,
    )


def _vix_regime(prices: pd.DataFrame) -> str:
    """VIX 현재 레벨 기반 공포 레짐."""
    vix_col = None
    for c in ["RK_VIX", "VIX_CODE"]:
        if c in prices.columns:
            vix_col = c
            break
    if vix_col is None:
        return "medium"
    px = prices[vix_col].dropna()
    if px.empty:
        return "medium"
    v = float(px.iloc[-1])
    if v < 18:
        return "low"
    elif v < 28:
        return "medium"
    return "high"


# ── Preference matching ───────────────────────────────────────────────────

def _regime_favored(code: str, regime: str, vix_reg: str,
                    rate_dir: str, meta: dict) -> bool:
    in_regime = regime in meta.get("prefer", [])
    vix_ok    = meta.get("vix_prefer", "any") in ("any", vix_reg)
    rate_ok   = meta.get("rate_prefer", "any") in ("any", rate_dir)
    return in_regime and vix_ok and rate_ok


def _view_label(score: float) -> str:
    if score >= 0.4:  return "OW"
    if score <= -0.4: return "UW"
    return "N"


# ── Main compute ──────────────────────────────────────────────────────────

def _score_style(code: str, prices: pd.DataFrame, bench: pd.Series) -> dict:
    result = {
        "code": code, "last": np.nan, "last_date": "N/A",
        "mom_1m": np.nan, "mom_3m": np.nan, "mom_6m": np.nan,
        "trend": 0, "rel_3m": np.nan, "composite": np.nan,
    }
    if code not in prices.columns:
        return result
    px = prices[code].dropna()
    if len(px) < 5:
        return result

    result["last"]       = round(float(px.iloc[-1]), 2)
    result["last_date"]  = str(px.index[-1].date())
    result["mom_1m"]     = round(_momentum(px, 21),  2)
    result["mom_3m"]     = round(_momentum(px, 63),  2)
    result["mom_6m"]     = round(_momentum(px, 126), 2)
    result["trend"]      = _trend_score(px)
    result["rel_3m"]     = round(_relative_mom(px, bench, 63) * 100, 2) if len(bench) >= 66 else np.nan
    result["composite"]  = _composite(
        result["mom_1m"], result["mom_3m"], result["mom_6m"],
        result["trend"],  result["rel_3m"]
    )
    result["view"]       = _view_label(result["composite"])
    return result


def compute_style_view(date) -> dict:
    date_str = str(date)
    prices   = _load_prices(date_str)
    macro    = _get_macro(date_str)

    regime    = macro.get("regime", "N/A")
    rate_dir  = macro.get("rate_direction", "stable")
    vix_reg   = _vix_regime(prices)

    bench_us = prices[SP500_CODE].dropna()  if SP500_CODE  in prices.columns else pd.Series(dtype=float)
    bench_kr = prices[KOSPI_CODE].dropna()  if KOSPI_CODE  in prices.columns else pd.Series(dtype=float)

    # US factor styles vs SP500
    us_styles = []
    for code, meta in US_STYLES.items():
        row = _score_style(code, prices, bench_us)
        row.update({
            "name":           meta["name"],
            "etf":            meta["etf"],
            "regime_favored": _regime_favored(code, regime, vix_reg, rate_dir, meta),
        })
        us_styles.append(row)
    us_styles.sort(key=lambda x: (-(x.get("composite") or -99)))

    # KR/comparison styles (KOSPI/KOSDAQ vs SP500)
    kr_styles = []
    for code, meta in KR_STYLES.items():
        bench = bench_kr if code in ("EQ_SP500", "EQ_RUSSELL2000") else bench_kr
        row = _score_style(code, prices, bench_us)
        row.update({"name": meta["name"], "etf": meta["etf"]})
        kr_styles.append(row)

    # Regime-favored style codes
    favored_codes = REGIME_STYLE_MAP.get(regime, [])
    vix_favored   = VIX_STYLE_MAP.get(vix_reg, [])

    # Rate × Style interpretation
    rate_style_note = {
        "rising":  "금리 상승기 → Value/Low Duration(Growth 불리), 금융/에너지 섹터 선호",
        "falling": "금리 하락기 → Growth/Long Duration(TLT) 유리, 고성장주 반등 기대",
        "stable":  "금리 안정 → Momentum/Quality 중심, 추세 지속 구간",
    }.get(rate_dir, "")

    # 변액보험 펀드 스타일 매핑
    fund_style_map = {
        "FA_US_GROWTH":   "해외주식형(미국/성장)",
        "FA_US_VALUE":    "해외주식형(미국/가치)",
        "FA_US_QUALITY":  "해외주식형(미국/퀄리티혼합)",
        "FA_US_MOMENTUM": "해외주식형(미국/모멘텀)",
        "FA_US_LOWVOL":   "해외주식형(미국/저변동성)",
    }
    for row in us_styles:
        row["fund_type"] = fund_style_map.get(row["code"], "해외주식형")

    return {
        "date":           date_str,
        "regime":         regime,
        "vix_regime":     vix_reg,
        "rate_direction": rate_dir,
        "rate_style_note":rate_style_note,
        "macro":          macro,
        "us_styles":      us_styles,
        "kr_styles":      kr_styles,
        "favored_codes":  favored_codes,
        "vix_favored":    vix_favored,
    }


# ── HTML rendering ────────────────────────────────────────────────────────

def _fmt(v, dec=2, suffix=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{dec}f}{suffix}"


def _mc(v):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "#888"
    return "#27ae60" if v > 0 else "#e74c3c"


def _view_badge(v):
    colors = {"OW": "#27ae60", "N": "#f39c12", "UW": "#e74c3c"}
    return f'<span style="background:{colors.get(v,"#888")};color:#fff;padding:2px 9px;border-radius:10px;font-size:12px;font-weight:700">{v}</span>'


def _trend_badge(t):
    labels = {2:("강세","#27ae60"), 1:("상승","#8bc34a"), 0:("중립","#888"),
              -1:("하락","#e67e22"), -2:("약세","#e74c3c")}
    lbl, col = labels.get(t, ("N/A","#888"))
    return f'<span style="color:{col};font-weight:600">{lbl}</span>'


def render_html(data: dict) -> str:
    date_str  = data["date"]
    regime    = data["regime"]
    vix_reg   = data["vix_regime"]
    rate_dir  = data["rate_direction"]
    favored   = set(data["favored_codes"] + data["vix_favored"])

    regime_cls = {
        "Goldilocks": "regime-goldilocks", "Reflation": "regime-reflation",
        "Stagflation": "regime-stagflation", "Deflation": "regime-deflation",
    }.get(regime, "badge")

    vix_labels = {"low": "낮음 (Risk-ON)", "medium": "보통", "high": "높음 (Risk-OFF)"}
    vix_label  = vix_labels.get(vix_reg, vix_reg)
    vix_cls    = {"low": "up", "medium": "muted", "high": "down"}.get(vix_reg, "muted")

    rate_labels = {"rising": "상승중 ↑", "falling": "하락중 ↓", "stable": "안정 →"}
    rate_label  = rate_labels.get(rate_dir, rate_dir)
    rate_cls    = {"rising": "down", "falling": "up", "stable": "muted"}.get(rate_dir, "muted")

    def _vbadge(v):
        if v == "OW":  return '<span class="ow">OW</span>'
        if v == "UW":  return '<span class="uw">UW</span>'
        return '<span class="neutral-b">N</span>'

    def _tbadge(t):
        if t >= 1:   return '<span class="ow">▲강세</span>'
        if t <= -1:  return '<span class="uw2">▼약세</span>'
        return '<span class="neutral-b">→중립</span>'

    def _mc2(v):
        if v is None or (isinstance(v, float) and np.isnan(v)): return "var(--muted)"
        return "var(--up)" if v > 0 else ("var(--down)" if v < 0 else "var(--muted)")

    def style_row(row) -> str:
        fav = row["code"] in favored
        star = ' ⭐' if fav else ''
        bg   = "background:#fff8f0;" if fav else ""
        return f"""<tr style="border-bottom:1px solid var(--border);{bg}">
          <td style="padding:8px 12px">
            <span style="font-size:13px;font-weight:600">{row["name"]}{star}</span>
            <span class="muted" style="font-size:11px;margin-left:6px">{row.get("etf","")}</span>
          </td>
          <td>{_vbadge(row.get("view","N"))}</td>
          <td class="mono">{_fmt(row.get("composite"),2)}</td>
          <td class="mono" style="color:{_mc2(row.get('mom_1m'))}">{_fmt(row.get('mom_1m'),2,'%')}</td>
          <td class="mono" style="color:{_mc2(row.get('mom_3m'))}">{_fmt(row.get('mom_3m'),2,'%')}</td>
          <td class="mono" style="color:{_mc2(row.get('mom_6m'))}">{_fmt(row.get('mom_6m'),2,'%')}</td>
          <td>{_tbadge(row.get("trend",0))}</td>
          <td class="mono" style="color:{_mc2(row.get('rel_3m'))}">{_fmt(row.get('rel_3m'),2,'%')}</td>
          <td class="muted" style="font-size:11px">{row.get("fund_type","")}</td>
        </tr>"""

    def compare_row(row) -> str:
        return f"""<tr style="border-bottom:1px solid var(--border)">
          <td style="padding:8px 12px">
            <span style="font-size:13px;font-weight:600">{row["name"]}</span>
            <span class="muted" style="font-size:11px;margin-left:6px">{row.get("etf","")}</span>
          </td>
          <td>{_vbadge(row.get("view","N"))}</td>
          <td class="mono">{_fmt(row.get("composite"),2)}</td>
          <td class="mono" style="color:{_mc2(row.get('mom_1m'))}">{_fmt(row.get('mom_1m'),2,'%')}</td>
          <td class="mono" style="color:{_mc2(row.get('mom_3m'))}">{_fmt(row.get('mom_3m'),2,'%')}</td>
          <td class="mono" style="color:{_mc2(row.get('mom_6m'))}">{_fmt(row.get('mom_6m'),2,'%')}</td>
          <td>{_tbadge(row.get("trend",0))}</td>
          <td class="mono" style="color:{_mc2(row.get('rel_3m'))}">{_fmt(row.get('rel_3m'),2,'%')}</td>
        </tr>"""

    us_rows = "".join(style_row(r) for r in data["us_styles"])
    kr_rows = "".join(compare_row(r) for r in data["kr_styles"])

    top_picks = [r for r in data["us_styles"] if r.get("view") == "OW" and r["code"] in favored]
    top_html  = ""
    if top_picks:
        cards = "".join(f"""<div class="stat-card">
          <div class="label">{r["name"]} <span class="muted" style="font-size:10px">{r.get("etf","")}</span></div>
          <div class="value">{_fmt(r.get("composite"),2)}</div>
          <div class="sub">{r.get("fund_type","")}</div>
        </div>""" for r in top_picks[:3])
        top_html = f'<div class="stat-grid">{cards}</div>'

    from ._shared import html_page
    body = f"""<div class="ma-header">
  <div>
    <h1>스타일 / 팩터 View</h1>
    <div class="meta">변액보험 스타일 팩터 로테이션</div>
  </div>
  <div class="date-badge">{date_str}</div>
</div>

<div class="card">
  <h2>📊 투자 환경 요약</h2>
  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">매크로 국면</div>
      <div style="margin-top:6px"><span class="{regime_cls}">{regime}</span></div>
    </div>
    <div class="stat-card">
      <div class="label">VIX 레짐</div>
      <div class="value {vix_cls}" style="font-size:16px">{vix_label}</div>
    </div>
    <div class="stat-card">
      <div class="label">금리 방향</div>
      <div class="value {rate_cls}" style="font-size:16px">{rate_label}</div>
    </div>
    <div class="stat-card" style="flex:2;min-width:240px">
      <div class="label">금리 × 스타일 시사점</div>
      <div style="font-size:13px;color:var(--text);margin-top:6px">{data["rate_style_note"]}</div>
    </div>
  </div>
  {top_html}
</div>

<div class="card">
  <h2>🇺🇸 미국 팩터 ETF <span class="badge">⭐ = 현 국면 선호</span></h2>
  <table>
    <thead><tr>
      <th style="text-align:left">스타일</th><th>의견</th><th>종합점수</th>
      <th>1M 수익률</th><th>3M 수익률</th><th>6M 수익률</th>
      <th>추세</th><th>vs SP500 3M</th><th>변액보험 펀드 유형</th>
    </tr></thead>
    <tbody>{us_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>🇰🇷 대형·소형·성장 비교 (KR vs US)</h2>
  <table>
    <thead><tr>
      <th style="text-align:left">지수</th><th>의견</th><th>종합점수</th>
      <th>1M 수익률</th><th>3M 수익률</th><th>6M 수익률</th>
      <th>추세</th><th>vs KOSPI 3M</th>
    </tr></thead>
    <tbody>{kr_rows}</tbody>
  </table>
  <div class="muted" style="font-size:11px;margin-top:8px">* KOSPI/KOSDAQ: 원화 기준 / SP500/Russell2000: USD 기준. vs KOSPI 초과수익 표시.</div>
</div>

<div class="card">
  <h2>📋 매크로 국면 × 팩터 선택 가이드</h2>
  <table>
    <thead><tr>
      <th style="text-align:left">국면</th><th>선호 팩터</th><th>기피 팩터</th><th>변액보험 전략</th>
    </tr></thead>
    <tbody>
      <tr><td style="padding:8px 12px"><span class="regime-goldilocks">Goldilocks</span></td>
        <td>Growth · Momentum · SmallCap</td>
        <td class="muted">LowVol · Defensive</td>
        <td>해외주식형(성장·모멘텀) 비중 확대</td></tr>
      <tr><td style="padding:8px 12px"><span class="regime-reflation">Reflation</span></td>
        <td>Value · Momentum · Cyclical</td>
        <td class="muted">Growth · Long Duration</td>
        <td>해외주식형(가치·경기순환) 전환</td></tr>
      <tr><td style="padding:8px 12px"><span class="regime-stagflation">Stagflation</span></td>
        <td>Value · Quality · LowVol</td>
        <td class="muted">Growth · SmallCap · High Beta</td>
        <td>방어적 혼합형·채권 비중 확대</td></tr>
      <tr><td style="padding:8px 12px"><span class="regime-deflation">Deflation</span></td>
        <td>Quality · LowVol · LargeCap</td>
        <td class="muted">Value · Cyclical · HY Credit</td>
        <td>국내채권·해외채권형 비중 최대화</td></tr>
    </tbody>
  </table>
</div>"""
    return html_page("스타일 / 팩터 View", date_str, body, "style",
                     source="yfinance (팩터 ETF) · FRED (매크로)")


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Style/Factor View")
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    data   = compute_style_view(target)

    if args.html:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{args.date}.html"
        html = render_html(data)
        out_path.write_text(html, encoding="utf-8")
        print(f"Saved: {out_path}")
    else:
        import json
        class _E(json.JSONEncoder):
            def default(self, o):
                if hasattr(o, "item"): return o.item()
                return super().default(o)
        print(json.dumps(data, ensure_ascii=False, indent=2, cls=_E))


if __name__ == "__main__":
    main()
