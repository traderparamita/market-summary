"""Bond structure view — 채권 커브 · 크레딧 · 듀레이션 포지셔닝.

US 채권 커브(1-3Y/3-7Y/10Y/30Y/TIPS) + KR 커브(CD91D/3Y/10Y)를 분석해
KR 변액보험 운용 관점의 듀레이션·크레딧 포지셔닝을 제안한다.

Usage:
    python -m portfolio.view.bond_view --date 2026-04-14 --html
"""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "bond"
MARKET_CSV = ROOT / "history" / "market_data.csv"
MACRO_CSV = ROOT / "history" / "macro_indicators.csv"

# ── Bond segment definitions ──────────────────────────────────────────────

US_BOND_SEGMENTS = {
    "BD_US_1_3Y":  {"name": "US 1-3Y",    "etf": "SHY",     "dur": 1.9,  "type": "govvt"},
    "BD_US_3_7Y":  {"name": "US 3-7Y",    "etf": "IEI",     "dur": 4.5,  "type": "govvt"},
    "BD_US_10Y":   {"name": "US 7-10Y",   "etf": "IEF",     "dur": 7.5,  "type": "govvt"},
    "BD_TLT":      {"name": "US 20Y+",    "etf": "TLT",     "dur": 17.0, "type": "govvt"},
    "BD_US_TIPS":  {"name": "US TIPS",    "etf": "TIP",     "dur": 6.5,  "type": "inflation"},
    "BD_LQD":      {"name": "IG Credit",  "etf": "LQD",     "dur": 8.5,  "type": "credit"},
    "BD_HYG":      {"name": "HY Credit",  "etf": "HYG",     "dur": 4.0,  "type": "credit"},
    "BD_EMB":      {"name": "EM Bond",    "etf": "EMB",     "dur": 7.5,  "type": "em"},
}

KR_BOND_SEGMENTS = {
    "BD_KR_CD91D": {"name": "KR CD 91D",  "dur": 0.25, "type": "money"},
    "BD_KR_3Y":    {"name": "KR 국고 3Y", "dur": 3.0,  "type": "govvt"},
    "BD_KR_10Y":   {"name": "KR 국고 10Y","dur": 10.0, "type": "govvt"},
}

# FRED macro codes for yield/spread context
MACRO_RATES = {
    "US_FED_RATE":    "연준 기준금리",
    "US_2Y_YIELD":    "미국 2년 국채",
    "US_10Y_YIELD":   "미국 10년 국채",
    "US_YIELD_CURVE": "미국 10Y-2Y 스프레드",
    "US_IG_SPREAD":   "IG 크레딧 스프레드",
    "US_HY_SPREAD":   "HY 크레딧 스프레드",
}


# ── Data loaders ──────────────────────────────────────────────────────────

def _load_prices(date: str) -> pd.DataFrame:
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    target = pd.Timestamp(date)
    return wide[wide.index <= target].sort_index()


def _load_macro(date: str) -> dict:
    """FRED 금리/스프레드 최근 값."""
    if not MACRO_CSV.exists():
        return {}
    df = pd.read_csv(MACRO_CSV, parse_dates=["DATE"])
    target = pd.Timestamp(date)
    df = df[df["DATE"] <= target]
    result = {}
    for code in MACRO_RATES:
        sub = df[df["INDICATOR_CODE"] == code]
        if not sub.empty:
            row = sub.sort_values("DATE").iloc[-1]
            result[code] = {"value": float(row["VALUE"]), "date": str(row["DATE"].date())}
    return result


# ── Signal calculators ────────────────────────────────────────────────────

def _momentum(px: pd.Series, days: int) -> float:
    if len(px) < days + 3:
        return np.nan
    return float(px.iloc[-1] / px.iloc[-days] - 1) * 100


def _trend_score(px: pd.Series) -> int:
    """MA200/MA50 추세 점수."""
    if len(px) < 55:
        return 0
    last = float(px.iloc[-1])
    ma50 = float(px.tail(50).mean())
    if len(px) < 205:
        return 1 if last > ma50 else -1
    ma200 = float(px.tail(200).mean())
    if last > ma200 and last > ma50:
        return 2
    elif last > ma200:
        return 1
    elif last < ma200 and last < ma50:
        return -2
    return -1


def _percentile(series: pd.Series, window: int = 252) -> float:
    """최근 window일 기준 현재 값의 백분위."""
    if len(series) < 30:
        return np.nan
    hist = series.tail(window)
    return float(np.sum(hist <= hist.iloc[-1]) / len(hist) * 100)


# ── Regime & positioning logic ────────────────────────────────────────────

def _credit_regime(hy_spread: float) -> tuple[str, str]:
    """HY 스프레드 기준 크레딧 국면 분류."""
    if np.isnan(hy_spread):
        return "N/A", "grey"
    if hy_spread < 300:
        return "Risk-On (스프레드 타이트)", "#27ae60"
    elif hy_spread < 500:
        return "경계 (스프레드 확대)", "#f39c12"
    return "위기 (스프레드 급등)", "#e74c3c"


def _duration_rec(yield_curve: float, fed_rate: float, us_10y: float) -> dict:
    """금리 환경 기반 듀레이션 포지셔닝 권고."""
    if np.isnan(yield_curve) or np.isnan(fed_rate):
        return {"label": "N/A", "bias": "neutral", "rationale": "데이터 부족"}

    # 수익률 곡선 분석
    if yield_curve > 50:          # 스팁(정상)
        curve_sig = "steepening"
    elif yield_curve < -20:       # 역전
        curve_sig = "inverted"
    else:
        curve_sig = "flat"

    # 연준 사이클 추정 (2Y-Fed 스프레드: 시장의 금리 인상/인하 기대)
    us_2y_fed_spread = fed_rate  # will be enriched below

    if curve_sig == "steepening":
        label = "중립~장기 비중 확대"
        bias = "long"
        rationale = "정상 기울기 → 장기채 보유 유리, 만기 확장 기회"
    elif curve_sig == "inverted":
        label = "단기 집중 (역전 해소 대기)"
        bias = "short"
        rationale = "역전 커브 → 단기채 금리 매력, 장기채 가격 리스크"
    else:
        label = "중립 (바벨 전략)"
        bias = "neutral"
        rationale = "플랫 커브 → 단기+장기 바벨, 중기채 기회비용"

    return {"label": label, "bias": bias, "rationale": rationale, "curve_sig": curve_sig}


def _kr_us_rate_diff(kr_10y: float, us_10y: float) -> dict:
    """KR-US 10Y 금리차 → 환헤지 비용 및 원화 방향 시사."""
    if np.isnan(kr_10y) or np.isnan(us_10y):
        return {"diff": np.nan, "signal": "N/A", "hedge_cost": np.nan}
    diff = kr_10y - us_10y
    # KR < US → KRW 약세 압력 (금리차 역전)
    if diff < -0.5:
        signal = "원화 약세 압력 (KR<US 역전)"
        color = "#e74c3c"
    elif diff < 0.5:
        signal = "금리차 중립"
        color = "#f39c12"
    else:
        signal = "원화 강세 지지 (KR>US)"
        color = "#27ae60"
    return {"diff": round(diff, 2), "signal": signal, "color": color}


# ── Main compute ──────────────────────────────────────────────────────────

def _score_bond_segment(code: str, prices: pd.DataFrame) -> dict:
    meta = {**US_BOND_SEGMENTS.get(code, {}), **KR_BOND_SEGMENTS.get(code, {})}
    result = {
        "code": code,
        "name": meta.get("name", code),
        "etf": meta.get("etf", "—"),
        "dur": meta.get("dur", np.nan),
        "type": meta.get("type", ""),
        "last": np.nan,
        "last_date": "N/A",
        "mom_1m": np.nan,
        "mom_3m": np.nan,
        "mom_6m": np.nan,
        "trend": 0,
        "pct_1y": np.nan,
    }
    if code not in prices.columns:
        return result

    px = prices[code].dropna()
    if px.empty:
        return result

    result["last"] = round(float(px.iloc[-1]), 2)
    result["last_date"] = str(px.index[-1].date())
    result["mom_1m"] = round(_momentum(px, 21), 2)
    result["mom_3m"] = round(_momentum(px, 63), 2)
    result["mom_6m"] = round(_momentum(px, 126), 2)
    result["trend"] = _trend_score(px)
    result["pct_1y"] = round(_percentile(px, 252), 1)
    return result


def compute_bond_view(date) -> dict:
    date_str = str(date)
    prices = _load_prices(date_str)
    macro = _load_macro(date_str)

    # Bond ETF signals
    us_bonds = [_score_bond_segment(c, prices) for c in US_BOND_SEGMENTS]
    kr_bonds = [_score_bond_segment(c, prices) for c in KR_BOND_SEGMENTS]

    # FRED macro rates
    fed_rate   = macro.get("US_FED_RATE",    {}).get("value", np.nan)
    us_2y      = macro.get("US_2Y_YIELD",    {}).get("value", np.nan)
    us_10y     = macro.get("US_10Y_YIELD",   {}).get("value", np.nan)
    yield_curve = macro.get("US_YIELD_CURVE", {}).get("value", np.nan)
    hy_spread  = macro.get("US_HY_SPREAD",   {}).get("value", np.nan)
    ig_spread  = macro.get("US_IG_SPREAD",   {}).get("value", np.nan)

    # KR rates from ETF price data (ECOS: level = rate)
    kr_cd91d_row = kr_bonds[0]
    kr_3y_row    = kr_bonds[1]
    kr_10y_row   = kr_bonds[2]
    kr_10y_val   = kr_10y_row["last"] if not np.isnan(kr_10y_row["last"]) else np.nan

    # Spread and regime signals
    credit_reg, credit_color = _credit_regime(hy_spread)
    dur_rec  = _duration_rec(yield_curve, fed_rate, us_10y)
    kr_us_diff = _kr_us_rate_diff(kr_10y_val, us_10y)

    # Implied cut/hike: 2Y - Fed Funds
    implied = round(us_2y - fed_rate, 2) if not (np.isnan(us_2y) or np.isnan(fed_rate)) else np.nan
    implied_sig = "금리 인하 기대" if (not np.isnan(implied) and implied < -0.25) \
        else ("금리 인상 기대" if (not np.isnan(implied) and implied > 0.25) else "동결 기대")

    # ALM recommendation for 변액보험
    alm_rec = _alm_recommendation(dur_rec["bias"], hy_spread, kr_us_diff["diff"])

    return {
        "date": date_str,
        "us_bonds": us_bonds,
        "kr_bonds": kr_bonds,
        "rates": {
            "fed_rate": fed_rate,
            "us_2y": us_2y,
            "us_10y": us_10y,
            "yield_curve": yield_curve,
            "hy_spread": hy_spread,
            "ig_spread": ig_spread,
            "kr_10y": kr_10y_val,
        },
        "credit_regime": credit_reg,
        "credit_color": credit_color,
        "duration_rec": dur_rec,
        "kr_us_diff": kr_us_diff,
        "implied_move": {"value": implied, "signal": implied_sig},
        "alm_rec": alm_rec,
    }


def _alm_recommendation(dur_bias: str, hy_spread: float, kr_us_diff: float) -> dict:
    """변액보험 ALM 관점 채권 포지셔닝 권고."""
    # 보험사는 장기 부채 → 장기 자산 선호. 단 금리 하락기엔 장기채 가격 리스크.
    lines = []

    if dur_bias == "long":
        lines.append("▶ 장기 국고채(KR 10Y / TLT) 비중 유지 — 부채 듀레이션 매칭 유리")
    elif dur_bias == "short":
        lines.append("▶ 단기채 집중 운용 — 역전 커브 해소 후 장기 재진입 검토")
    else:
        lines.append("▶ 바벨 전략: KR CD91D + KR 10Y 조합으로 ALM 유지")

    if not np.isnan(hy_spread):
        if hy_spread < 300:
            lines.append("▶ IG 크레딧 일부 편입 가능 — 스프레드 타이트하나 캐리 확보")
        elif hy_spread > 500:
            lines.append("▶ HY 크레딧 축소 — 스프레드 급등, 신용리스크 확대")

    if not np.isnan(kr_us_diff):
        if kr_us_diff < -0.5:
            lines.append("▶ 해외 채권 환헤지 비용 상승 (KR<US) — 언헤지 EM/US 채권 비중 축소 고려")
        else:
            lines.append("▶ KR-US 금리차 안정 — 해외 채권 헤지 비용 관리 가능")

    return {"lines": lines}


# ── HTML rendering ────────────────────────────────────────────────────────

def _fmt(v, decimals=2, suffix=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{decimals}f}{suffix}"


def _mom_color(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "#888"
    return "#27ae60" if v > 0 else "#e74c3c"


def _trend_badge(t: int) -> str:
    labels = {2: ("강한 상승", "#27ae60"), 1: ("상승", "#8bc34a"),
              0: ("중립", "#888"), -1: ("하락", "#e67e22"), -2: ("강한 하락", "#e74c3c")}
    label, color = labels.get(t, ("N/A", "#888"))
    return f'<span style="color:{color};font-weight:600">{label}</span>'


def _pct_bar(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    color = "#e74c3c" if v < 30 else ("#27ae60" if v > 70 else "#f39c12")
    return (f'<span style="color:{color}">{v:.0f}%ile</span>')


def render_html(data: dict) -> str:
    date_str = data["date"]
    rates = data["rates"]
    dur = data["duration_rec"]
    kr_us = data["kr_us_diff"]
    alm = data["alm_rec"]
    implied = data["implied_move"]

    # ── Duration bias color
    bias_color = {"long": "#27ae60", "short": "#e74c3c", "neutral": "#f39c12"}.get(dur["bias"], "#888")

    # ── Curve signal badge
    curve_labels = {
        "steepening": ("정상 (스팁)", "#27ae60"),
        "inverted":   ("역전", "#e74c3c"),
        "flat":       ("플랫", "#f39c12"),
    }
    curve_label, curve_color = curve_labels.get(dur.get("curve_sig", ""), ("N/A", "#888"))

    def rate_card(label, value, unit="%", extra=""):
        val_str = _fmt(value, 2)
        return f"""
        <div style="background:#1e2a3a;border-radius:8px;padding:14px 18px;min-width:130px">
          <div style="color:#aaa;font-size:11px;margin-bottom:4px">{label}</div>
          <div style="color:#e8eaf6;font-size:20px;font-weight:700">{val_str}<span style="font-size:13px;color:#aaa"> {unit}</span></div>
          {f'<div style="color:#aaa;font-size:11px;margin-top:2px">{extra}</div>' if extra else ''}
        </div>"""

    def bond_row(seg: dict, is_kr=False) -> str:
        type_badge = {
            "govvt":     ('<span style="background:#1a4a6e;color:#7ec8e3;padding:2px 7px;border-radius:10px;font-size:10px">국채</span>', ),
            "inflation": ('<span style="background:#3d2b00;color:#f9ca74;padding:2px 7px;border-radius:10px;font-size:10px">물가연동</span>', ),
            "credit":    ('<span style="background:#3d1a2e;color:#f48fb1;padding:2px 7px;border-radius:10px;font-size:10px">크레딧</span>', ),
            "em":        ('<span style="background:#1a3d2e;color:#a5d6a7;padding:2px 7px;border-radius:10px;font-size:10px">EM</span>', ),
            "money":     ('<span style="background:#2e2a1a;color:#ffe082;padding:2px 7px;border-radius:10px;font-size:10px">단기</span>', ),
        }
        badge = type_badge.get(seg["type"], ("",))[0]
        etf_col = f'<td style="color:#aaa;font-size:12px">{seg.get("etf","—")}</td>' if not is_kr else ""
        dur_col = f'<td style="color:#ccc;font-size:13px">{_fmt(seg["dur"],1)}Y</td>'
        return f"""<tr style="border-bottom:1px solid #2a3a4e">
          <td style="padding:8px 12px">{badge} <span style="color:#e8eaf6;font-size:13px">{seg["name"]}</span></td>
          {etf_col}
          {dur_col}
          <td style="color:#e8eaf6;font-size:13px">{_fmt(seg["last"])}</td>
          <td style="color:{_mom_color(seg['mom_1m'])};font-size:13px">{_fmt(seg['mom_1m'],2,'%')}</td>
          <td style="color:{_mom_color(seg['mom_3m'])};font-size:13px">{_fmt(seg['mom_3m'],2,'%')}</td>
          <td style="color:{_mom_color(seg['mom_6m'])};font-size:13px">{_fmt(seg['mom_6m'],2,'%')}</td>
          <td>{_trend_badge(seg['trend'])}</td>
          <td>{_pct_bar(seg['pct_1y'])}</td>
        </tr>"""

    us_rows = "".join(bond_row(s) for s in data["us_bonds"])
    kr_rows = "".join(bond_row(s, is_kr=True) for s in data["kr_bonds"])

    alm_lines = "".join(f'<li style="margin-bottom:6px;color:#ccc">{l}</li>' for l in alm["lines"])

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bond View — {date_str}</title>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#0d1b2a; color:#e8eaf6; font-family:'Segoe UI',sans-serif; padding:24px; }}
h2 {{ color:#7ec8e3; margin-bottom:4px; }}
h3 {{ color:#90caf9; margin:20px 0 10px; font-size:15px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ background:#162032; color:#90caf9; padding:8px 12px; text-align:left; font-size:11px; letter-spacing:.5px; }}
.card-grid {{ display:flex; flex-wrap:wrap; gap:12px; margin-bottom:20px; }}
.section {{ background:#132030; border-radius:10px; padding:20px; margin-bottom:20px; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; }}
</style>
</head>
<body>

<div style="max-width:1100px;margin:0 auto">
  <h2>Bond View</h2>
  <div style="color:#aaa;font-size:13px;margin-bottom:20px">{date_str} 기준 | 미래에셋생명 변액보험 운용 관점</div>

  <!-- ── 금리 환경 요약 ── -->
  <div class="section">
    <h3>금리 환경 요약</h3>
    <div class="card-grid">
      {rate_card("연준 기준금리", rates["fed_rate"])}
      {rate_card("미국 2Y 국채", rates["us_2y"])}
      {rate_card("미국 10Y 국채", rates["us_10y"])}
      {rate_card("10Y-2Y 스프레드", rates["yield_curve"], "bp")}
      {rate_card("HY 스프레드", rates["hy_spread"], "bp")}
      {rate_card("IG 스프레드", rates["ig_spread"], "bp")}
      {rate_card("KR 국고 10Y", rates["kr_10y"])}
    </div>

    <!-- Key signals row -->
    <div style="display:flex;flex-wrap:wrap;gap:14px;margin-top:12px">
      <div style="background:#1e2a3a;border-radius:8px;padding:12px 18px;flex:1;min-width:180px">
        <div style="color:#aaa;font-size:11px;margin-bottom:4px">수익률 곡선 형태</div>
        <div style="color:{curve_color};font-size:16px;font-weight:700">{curve_label}</div>
        <div style="color:#aaa;font-size:11px;margin-top:2px">10Y-2Y = {_fmt(rates["yield_curve"], 1)}bp</div>
      </div>
      <div style="background:#1e2a3a;border-radius:8px;padding:12px 18px;flex:1;min-width:180px">
        <div style="color:#aaa;font-size:11px;margin-bottom:4px">연준 금리 방향 기대</div>
        <div style="color:#e8eaf6;font-size:16px;font-weight:700">{implied["signal"]}</div>
        <div style="color:#aaa;font-size:11px;margin-top:2px">2Y-Fed = {_fmt(implied["value"], 2)}%p</div>
      </div>
      <div style="background:#1e2a3a;border-radius:8px;padding:12px 18px;flex:1;min-width:180px">
        <div style="color:#aaa;font-size:11px;margin-bottom:4px">크레딧 국면</div>
        <div style="color:{data["credit_color"]};font-size:16px;font-weight:700">{data["credit_regime"]}</div>
        <div style="color:#aaa;font-size:11px;margin-top:2px">HY = {_fmt(rates["hy_spread"],1)}bp</div>
      </div>
      <div style="background:#1e2a3a;border-radius:8px;padding:12px 18px;flex:1;min-width:180px">
        <div style="color:#aaa;font-size:11px;margin-bottom:4px">KR-US 10Y 금리차</div>
        <div style="color:{kr_us["color"]};font-size:16px;font-weight:700">{_fmt(kr_us["diff"],2)}%p</div>
        <div style="color:#aaa;font-size:11px;margin-top:2px">{kr_us["signal"]}</div>
      </div>
      <div style="background:#1e2a3a;border-radius:8px;padding:12px 18px;flex:1;min-width:220px">
        <div style="color:#aaa;font-size:11px;margin-bottom:4px">듀레이션 포지셔닝</div>
        <div style="color:{bias_color};font-size:15px;font-weight:700">{dur["label"]}</div>
        <div style="color:#aaa;font-size:11px;margin-top:2px">{dur["rationale"]}</div>
      </div>
    </div>
  </div>

  <!-- ── US 채권 ETF ── -->
  <div class="section">
    <h3>미국 채권 ETF</h3>
    <table>
      <thead><tr>
        <th>세그먼트</th><th>ETF</th><th>듀레이션</th><th>현재가</th>
        <th>1M 수익률</th><th>3M 수익률</th><th>6M 수익률</th>
        <th>추세</th><th>1Y 백분위</th>
      </tr></thead>
      <tbody>{us_rows}</tbody>
    </table>
  </div>

  <!-- ── KR 채권 금리 ── -->
  <div class="section">
    <h3>한국 채권 금리 (ECOS)</h3>
    <table>
      <thead><tr>
        <th>세그먼트</th><th>듀레이션</th><th>금리(%)</th>
        <th>1M 변화</th><th>3M 변화</th><th>6M 변화</th>
        <th>추세</th><th>1Y 백분위</th>
      </tr></thead>
      <tbody>{kr_rows}</tbody>
    </table>
    <div style="color:#aaa;font-size:11px;margin-top:8px">* KR 채권은 금리 레벨 기준. 수익률(%) 변화 = 금리 변화(%p × 방향 주의)</div>
  </div>

  <!-- ── 변액보험 ALM 포지셔닝 ── -->
  <div class="section">
    <h3>변액보험 ALM 포지셔닝 권고</h3>
    <div style="background:#1e2a3a;border-radius:8px;padding:16px 20px">
      <ul style="list-style:none;padding:0">
        {alm_lines}
      </ul>
      <div style="margin-top:12px;padding-top:12px;border-top:1px solid #2a3a4e;color:#7ec8e3;font-size:12px">
        📋 변액보험 ALM 원칙: 보험 부채 장기 듀레이션(8-12Y) → 자산 듀레이션 매칭 기본 유지.
        금리 상승기엔 단기채 집중 후 장기 재진입 기회 포착.
      </div>
    </div>
  </div>

  <div style="color:#555;font-size:11px;text-align:center;margin-top:16px">
    데이터: FRED (금리/스프레드) · yfinance (채권 ETF) · ECOS (한국 금리) | Bond View v1.0
  </div>
</div>

</body>
</html>"""
    return html


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bond View")
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    data = compute_bond_view(target)

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
                if hasattr(o, "item"):
                    return o.item()
                return super().default(o)
        print(json.dumps(data, ensure_ascii=False, indent=2, cls=_E))


if __name__ == "__main__":
    main()
