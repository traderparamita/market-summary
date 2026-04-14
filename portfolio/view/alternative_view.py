"""Alternative assets view — 대체자산 포지셔닝.

귀금속(Gold/Silver) · 에너지(WTI/Brent/Nat Gas) · 산업금속(Copper) · REIT를 분석해
달러(DXY) · 실질금리(TIPS) · VIX 오버레이 기반 OW/N/UW 포지셔닝을 제안한다.

Usage:
    python -m portfolio.view.alternative_view --date 2026-04-14 --html
"""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "alternative"
MARKET_CSV = ROOT / "history" / "market_data.csv"

# ── Asset definitions ─────────────────────────────────────────────────────

PRECIOUS_METALS = {
    "CM_GOLD":   {"name": "Gold (금)",   "unit": "USD/oz",  "group": "precious"},
    "CM_SILVER": {"name": "Silver (은)", "unit": "USD/oz",  "group": "precious"},
}

ENERGY = {
    "CM_WTI":    {"name": "WTI 원유",    "unit": "USD/bbl", "group": "energy"},
    "CM_BRENT":  {"name": "Brent 원유",  "unit": "USD/bbl", "group": "energy"},
    "CM_NATGAS": {"name": "천연가스",    "unit": "USD/MMBtu","group": "energy"},
}

INDUSTRIAL = {
    "CM_COPPER": {"name": "Copper (구리)", "unit": "USD/lb", "group": "industrial"},
}

REAL_ESTATE = {
    "SC_US_REIT": {"name": "SPDR REIT (XLRE)", "unit": "ETF", "group": "reit"},
}

# Cross-asset overlay codes
OVERLAY_CODES = ["FX_DXY", "RK_VIX", "BD_US_TIPS", "BD_US_10Y", "BD_US_2Y"]

ALL_ALT = {**PRECIOUS_METALS, **ENERGY, **INDUSTRIAL, **REAL_ESTATE}


# ── Data loader ───────────────────────────────────────────────────────────

def _load_prices(date: str) -> pd.DataFrame:
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    target = pd.Timestamp(date)
    return wide[wide.index <= target].sort_index()


# ── Signal calculators ────────────────────────────────────────────────────

def _momentum(px: pd.Series, days: int) -> float:
    if len(px) < days + 3:
        return np.nan
    return float(px.iloc[-1] / px.iloc[-days] - 1) * 100


def _trend_score(px: pd.Series) -> int:
    """MA200/MA50 추세 점수 (-2~+2)."""
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
    if len(series) < 30:
        return np.nan
    hist = series.tail(window)
    return float(np.sum(hist <= hist.iloc[-1]) / len(hist) * 100)


def _ow_nu_uw(mom_1m: float, mom_3m: float, mom_6m: float,
              trend: int, pct_1y: float) -> tuple[str, str]:
    """복합 점수 기반 OW/N/UW + 색상."""
    scores = []

    # 모멘텀 점수 (정규화: 개별 방향성)
    for m, w in [(mom_1m, 0.4), (mom_3m, 0.35), (mom_6m, 0.25)]:
        if not np.isnan(m):
            scores.append(np.sign(m) * w)

    # 추세 점수
    scores.append(trend * 0.3)

    # 백분위 점수 (70+: 강세, 30-: 약세)
    if not np.isnan(pct_1y):
        if pct_1y >= 70:
            scores.append(0.2)
        elif pct_1y <= 30:
            scores.append(-0.2)

    if not scores:
        return "N", "#94a3b8"

    composite = sum(scores)
    if composite >= 0.45:
        return "OW", "#059669"
    elif composite <= -0.45:
        return "UW", "#dc2626"
    return "N", "#d97706"


# ── Asset scorer ──────────────────────────────────────────────────────────

def _score_asset(code: str, prices: pd.DataFrame) -> dict:
    meta = ALL_ALT.get(code, {})
    result = {
        "code": code,
        "name": meta.get("name", code),
        "unit": meta.get("unit", ""),
        "group": meta.get("group", ""),
        "last": np.nan,
        "last_date": "N/A",
        "mom_1m": np.nan,
        "mom_3m": np.nan,
        "mom_6m": np.nan,
        "trend": 0,
        "pct_1y": np.nan,
        "rating": "N",
        "rating_color": "#94a3b8",
    }
    if code not in prices.columns:
        return result

    px = prices[code].dropna()
    if px.empty:
        return result

    m1 = round(_momentum(px, 21), 2)
    m3 = round(_momentum(px, 63), 2)
    m6 = round(_momentum(px, 126), 2)
    tr = _trend_score(px)
    pc = round(_percentile(px, 252), 1)
    rating, rcolor = _ow_nu_uw(m1, m3, m6, tr, pc)

    result.update({
        "last":         round(float(px.iloc[-1]), 3),
        "last_date":    str(px.index[-1].date()),
        "mom_1m":       m1,
        "mom_3m":       m3,
        "mom_6m":       m6,
        "trend":        tr,
        "pct_1y":       pc,
        "rating":       rating,
        "rating_color": rcolor,
    })
    return result


# ── Overlay calculators ───────────────────────────────────────────────────

def _dxy_regime(px: pd.DataFrame) -> dict:
    """DXY 추세 기반 달러 국면 → 원자재 헤드/테일윈드 분류."""
    if "FX_DXY" not in px.columns:
        return {"label": "N/A", "color": "#94a3b8", "signal": "데이터 없음",
                "mom_1m": np.nan, "last": np.nan}
    dxy = px["FX_DXY"].dropna()
    if dxy.empty:
        return {"label": "N/A", "color": "#94a3b8", "signal": "데이터 없음",
                "mom_1m": np.nan, "last": np.nan}
    last  = float(dxy.iloc[-1])
    m1    = _momentum(dxy, 21)
    tr    = _trend_score(dxy)

    # DXY 강세 → 원자재 헤드윈드, DXY 약세 → 테일윈드
    if tr >= 1:
        label, color = "달러 강세 (원자재 헤드윈드)", "#dc2626"
    elif tr <= -1:
        label, color = "달러 약세 (원자재 테일윈드)", "#059669"
    else:
        label, color = "달러 중립", "#d97706"

    return {"label": label, "color": color,
            "signal": f"DXY {last:.2f}, 1M {'+' if m1 >= 0 else ''}{m1:.2f}%" if not np.isnan(m1) else f"DXY {last:.2f}",
            "mom_1m": m1, "last": last, "trend": tr}


def _real_rate_regime(px: pd.DataFrame) -> dict:
    """TIPS ETF (TIP) 추세 → 실질금리 방향 신호."""
    if "BD_US_TIPS" not in px.columns:
        return {"label": "N/A", "color": "#94a3b8", "signal": "데이터 없음",
                "mom_1m": np.nan}
    tip = px["BD_US_TIPS"].dropna()
    if tip.empty:
        return {"label": "N/A", "color": "#94a3b8", "signal": "데이터 없음",
                "mom_1m": np.nan}
    m1 = _momentum(tip, 21)
    tr = _trend_score(tip)

    # TIP 상승(가격 상승) = 실질금리 하락 = 금 우호
    # TIP 하락(가격 하락) = 실질금리 상승 = 금 역풍
    if tr >= 1:
        label = "실질금리 하락 추세 (금·은 우호)"
        color = "#059669"
    elif tr <= -1:
        label = "실질금리 상승 추세 (금·은 역풍)"
        color = "#dc2626"
    else:
        label = "실질금리 중립"
        color = "#d97706"

    sign = "+" if (not np.isnan(m1) and m1 >= 0) else ""
    signal = f"TIP 1M {sign}{m1:.2f}%" if not np.isnan(m1) else "TIP 추세 중립"
    return {"label": label, "color": color, "signal": signal, "mom_1m": m1, "trend": tr}


def _vix_regime(px: pd.DataFrame) -> dict:
    """VIX 레벨 → 원자재 지정학 프리미엄."""
    if "RK_VIX" not in px.columns:
        return {"label": "N/A", "color": "#94a3b8", "last": np.nan}
    vix = px["RK_VIX"].dropna()
    if vix.empty:
        return {"label": "N/A", "color": "#94a3b8", "last": np.nan}
    last = float(vix.iloc[-1])
    if last >= 30:
        label, color = f"공포 구간 (VIX {last:.1f}) — 유가·금 지정학 프리미엄 확대", "#dc2626"
    elif last >= 20:
        label, color = f"경계 구간 (VIX {last:.1f}) — 불확실성 반영 중", "#d97706"
    else:
        label, color = f"안정 구간 (VIX {last:.1f}) — 원자재 펀더멘털 중심", "#059669"
    return {"label": label, "color": color, "last": last}


def _copper_signal(px: pd.DataFrame) -> dict:
    """Dr. Copper: 구리 추세로 경기 방향 진단."""
    if "CM_COPPER" not in px.columns:
        return {"label": "경기 신호 없음", "color": "#94a3b8",
                "mom_1m": np.nan, "mom_3m": np.nan, "trend": 0, "last": np.nan}
    cop = px["CM_COPPER"].dropna()
    if cop.empty:
        return {"label": "경기 신호 없음", "color": "#94a3b8",
                "mom_1m": np.nan, "mom_3m": np.nan, "trend": 0, "last": np.nan}
    last = float(cop.iloc[-1])
    m1 = _momentum(cop, 21)
    m3 = _momentum(cop, 63)
    tr = _trend_score(cop)

    if tr >= 1 and (not np.isnan(m3) and m3 > 0):
        label = "경기 확장 신호 (Copper 상승 추세)"
        color = "#059669"
    elif tr <= -1 and (not np.isnan(m3) and m3 < 0):
        label = "경기 둔화 신호 (Copper 하락 추세)"
        color = "#dc2626"
    else:
        label = "경기 방향 불분명 (Copper 횡보)"
        color = "#d97706"

    return {"label": label, "color": color,
            "last": last, "mom_1m": m1, "mom_3m": m3, "trend": tr}


def _reit_rate_signal(px: pd.DataFrame) -> dict:
    """REIT vs 10Y 금리 민감도: 금리 하락 = REIT 우호."""
    us10y_m1 = np.nan
    if "BD_US_10Y" in px.columns:
        r = px["BD_US_10Y"].dropna()
        if len(r) > 21:
            us10y_m1 = float(r.iloc[-1] - r.iloc[-22])  # bps 변화 (금리는 레벨)

    if "SC_US_REIT" not in px.columns:
        return {"label": "데이터 없음", "color": "#94a3b8", "us10y_change": us10y_m1}

    reit = px["SC_US_REIT"].dropna()
    if reit.empty:
        return {"label": "데이터 없음", "color": "#94a3b8", "us10y_change": us10y_m1}

    tr = _trend_score(reit)
    # 금리가 지난 1M 동안 하락했으면 REIT 우호
    if not np.isnan(us10y_m1) and us10y_m1 < -0.2 and tr >= 0:
        label = "금리 하락 + REIT 상승 추세 — 우호적"
        color = "#059669"
    elif not np.isnan(us10y_m1) and us10y_m1 > 0.2:
        label = f"금리 상승 ({us10y_m1:+.2f}%p) — REIT 역풍"
        color = "#dc2626"
    else:
        label = "금리 중립 — REIT 방향 불분명"
        color = "#d97706"

    return {"label": label, "color": color, "us10y_change": us10y_m1, "trend": tr}


# ── ALM recommendation ────────────────────────────────────────────────────

def _alm_alt_rec(precious: list, energy: list, industrial: list,
                 reit: list, dxy: dict, real_rate: dict) -> list[str]:
    """변액보험 관점 대체자산 포지셔닝 권고."""
    lines = []

    gold_rating = next((a["rating"] for a in precious if "Gold" in a["name"]), "N")
    wti_rating  = next((a["rating"] for a in energy if "WTI" in a["name"]), "N")
    reit_rating = reit[0]["rating"] if reit else "N"
    cop_trend   = next((a["trend"] for a in industrial if "Copper" in a["name"]), 0)

    # Gold
    if gold_rating == "OW":
        lines.append("▶ Gold OW — 실질금리 하락·지정학 프리미엄 환경. 변액보험 안전자산 버킷에 5~10% 편입 검토")
    elif gold_rating == "UW":
        lines.append("▶ Gold UW — 실질금리 상승 추세. 귀금속 비중 축소 또는 중립 유지")
    else:
        lines.append("▶ Gold N — 실질금리·달러 방향 확인 후 진입 결정")

    # Energy
    if wti_rating == "OW":
        lines.append("▶ 에너지 OW — 유가 모멘텀 강세. 에너지 인프라 펀드·원자재 ETF 단기 오버웨이트")
    elif wti_rating == "UW":
        lines.append("▶ 에너지 UW — 유가 하락 추세. 에너지 섹터 비중 축소")
    else:
        lines.append("▶ 에너지 N — 지정학 이벤트 모니터링 하에 중립 유지")

    # Copper → 주식 비중 참고
    if cop_trend >= 1:
        lines.append("▶ Copper 상승 추세 (Dr. Copper 확장 신호) — 경기민감 자산(주식·IG 크레딧) 비중 지지")
    elif cop_trend <= -1:
        lines.append("▶ Copper 하락 추세 (Dr. Copper 둔화 신호) — 방어 자산 비중 확대 고려")

    # REIT
    if reit_rating == "OW":
        lines.append("▶ REIT OW — 금리 하락 추세 동반. 부동산 리츠 편입 가능 (단, 공모 리츠 환금성 확인)")
    elif reit_rating == "UW":
        lines.append("▶ REIT UW — 금리 상승 역풍. 부동산 배분 축소")

    # DXY overlay
    if dxy.get("trend", 0) <= -1:
        lines.append("▶ 달러 약세 환경 — USD 표시 원자재(Gold·WTI)의 KRW 환산 수익 개선 기대")
    elif dxy.get("trend", 0) >= 1:
        lines.append("▶ 달러 강세 환경 — 원자재 전체 달러 가격 압박. KRW 환헤지 비용 감안 후 투자")

    return lines


# ── Main compute ──────────────────────────────────────────────────────────

def compute_alternative_view(date) -> dict:
    date_str = str(date)
    prices = _load_prices(date_str)

    precious  = [_score_asset(c, prices) for c in PRECIOUS_METALS]
    energy    = [_score_asset(c, prices) for c in ENERGY]
    industrial = [_score_asset(c, prices) for c in INDUSTRIAL]
    reit      = [_score_asset(c, prices) for c in REAL_ESTATE]

    dxy_reg   = _dxy_regime(prices)
    rr_reg    = _real_rate_regime(prices)
    vix_reg   = _vix_regime(prices)
    copper_sig = _copper_signal(prices)
    reit_sig  = _reit_rate_signal(prices)

    alm_lines = _alm_alt_rec(precious, energy, industrial, reit, dxy_reg, rr_reg)

    return {
        "date":       date_str,
        "precious":   precious,
        "energy":     energy,
        "industrial": industrial,
        "reit":       reit,
        "dxy":        dxy_reg,
        "real_rate":  rr_reg,
        "vix":        vix_reg,
        "copper":     copper_sig,
        "reit_sig":   reit_sig,
        "alm_lines":  alm_lines,
    }


# ── HTML rendering ────────────────────────────────────────────────────────

def _fmt(v, decimals=2, suffix=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{decimals}f}{suffix}"


def _trend_badge(t: int) -> str:
    labels = {2: ("강한 상승", "#059669"), 1: ("상승", "#16a34a"),
              0: ("중립",   "#94a3b8"), -1: ("하락", "#ea580c"), -2: ("강한 하락", "#dc2626")}
    label, color = labels.get(t, ("N/A", "#94a3b8"))
    return f'<span style="color:{color};font-weight:600">{label}</span>'


def _pct_bar(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    color = "#dc2626" if v < 30 else ("#059669" if v > 70 else "#d97706")
    return f'<span style="color:{color}">{v:.0f}%ile</span>'


def _rating_badge(rating: str, color: str) -> str:
    bg_map = {"OW": "rgba(5,150,105,0.12)", "UW": "rgba(220,38,38,0.12)", "N": "rgba(148,163,184,0.12)"}
    bg = bg_map.get(rating, "rgba(148,163,184,0.12)")
    return (f'<span style="background:{bg};color:{color};padding:3px 10px;'
            f'border-radius:10px;font-weight:700;font-size:12px">{rating}</span>')


def _mc(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "muted"
    return "up" if v > 0 else ("down" if v < 0 else "muted")


def _asset_row(seg: dict, show_unit: bool = False) -> str:
    unit_col = f'<td class="muted" style="font-size:11px">{seg["unit"]}</td>' if show_unit else ""
    return f"""<tr>
      <td><strong>{seg["name"]}</strong></td>
      {unit_col}
      <td class="mono">{_fmt(seg["last"])}</td>
      <td class="{_mc(seg['mom_1m'])}">{_fmt(seg['mom_1m'],2,'%')}</td>
      <td class="{_mc(seg['mom_3m'])}">{_fmt(seg['mom_3m'],2,'%')}</td>
      <td class="{_mc(seg['mom_6m'])}">{_fmt(seg['mom_6m'],2,'%')}</td>
      <td>{_trend_badge(seg['trend'])}</td>
      <td>{_pct_bar(seg['pct_1y'])}</td>
      <td>{_rating_badge(seg['rating'], seg['rating_color'])}</td>
    </tr>"""


def render_html(data: dict) -> str:
    from ._shared import html_page

    date_str  = data["date"]
    dxy       = data["dxy"]
    rr        = data["real_rate"]
    vix       = data["vix"]
    copper    = data["copper"]
    reit_sig  = data["reit_sig"]
    alm_lines = data["alm_lines"]

    precious_rows  = "".join(_asset_row(s) for s in data["precious"])
    energy_rows    = "".join(_asset_row(s) for s in data["energy"])
    industrial_rows= "".join(_asset_row(s) for s in data["industrial"])
    reit_rows      = "".join(_asset_row(s) for s in data["reit"])

    alm_html = "".join(f'<li style="margin-bottom:8px">{l}</li>' for l in alm_lines)

    # ── DXY×리스크 오버레이 매트릭스 ─────────────────────────────────────
    def overlay_cell(assets: str, rating: str, note: str, bg: str) -> str:
        return (f'<td style="background:{bg};padding:12px 14px;vertical-align:top;'
                f'border:1px solid #e2e8f0">'
                f'<div style="font-weight:700;margin-bottom:4px">{assets}</div>'
                f'<div style="font-size:11px;color:#64748b">{note}</div>'
                f'<div style="margin-top:6px">{_rating_badge(rating, "#059669" if rating=="OW" else "#dc2626" if rating=="UW" else "#94a3b8")}</div>'
                f'</td>')

    def sig_card(label: str, value_html: str, sub: str = "") -> str:
        sub_html = f'<div class="sub">{sub}</div>' if sub else ""
        return (f'<div class="stat-card">'
                f'<div class="label">{label}</div>'
                f'<div style="font-size:15px;font-weight:700;margin:4px 0">{value_html}</div>'
                f'{sub_html}'
                f'</div>')

    # DXY trend color mapping
    dxy_color_map = {"#dc2626": "var(--down)", "#059669": "var(--up)", "#d97706": "#d97706"}
    dxy_fg  = dxy_color_map.get(dxy["color"], dxy["color"])
    rr_color_map  = {"#dc2626": "var(--down)", "#059669": "var(--up)", "#d97706": "#d97706"}
    rr_fg   = rr_color_map.get(rr["color"], rr["color"])
    vix_color_map = {"#dc2626": "var(--down)", "#059669": "var(--up)", "#d97706": "#d97706"}
    vix_fg  = vix_color_map.get(vix["color"], vix["color"])
    cop_color_map = {"#dc2626": "var(--down)", "#059669": "var(--up)", "#d97706": "#d97706"}
    cop_fg  = cop_color_map.get(copper["color"], copper["color"])
    reit_color_map= {"#dc2626": "var(--down)", "#059669": "var(--up)", "#d97706": "#d97706"}
    reit_fg = reit_color_map.get(reit_sig["color"], reit_sig["color"])

    # 모든 대체자산 OW/UW/N 카운트
    all_assets = data["precious"] + data["energy"] + data["industrial"] + data["reit"]
    ow_count = sum(1 for a in all_assets if a["rating"] == "OW")
    uw_count = sum(1 for a in all_assets if a["rating"] == "UW")
    n_count  = sum(1 for a in all_assets if a["rating"] == "N")
    sentiment = "대체자산 전반 강세" if ow_count > uw_count + 1 else \
                "대체자산 전반 약세" if uw_count > ow_count + 1 else "대체자산 중립·혼조"
    sent_color = "#059669" if ow_count > uw_count + 1 else \
                 "#dc2626" if uw_count > ow_count + 1 else "#d97706"

    body = f"""
<div class="card">
  <h2>🌐 대체자산 환경 요약</h2>
  <div class="stat-grid">
    {sig_card("달러 (DXY) 국면",
        f'<span style="color:{dxy_fg}">{dxy["label"]}</span>',
        dxy["signal"])}
    {sig_card("실질금리 방향 (TIPS)",
        f'<span style="color:{rr_fg}">{rr["label"]}</span>',
        rr["signal"])}
    {sig_card("VIX (지정학 프리미엄)",
        f'<span style="color:{vix_fg}">{vix["label"]}</span>',
        "공포지수 레벨")}
    {sig_card("Dr. Copper (경기 신호)",
        f'<span style="color:{cop_fg}">{copper["label"]}</span>',
        f"Copper 1M {_fmt(copper['mom_1m'],2,'%')} / 3M {_fmt(copper['mom_3m'],2,'%')}")}
    {sig_card("REIT 금리 민감도",
        f'<span style="color:{reit_fg}">{reit_sig["label"]}</span>',
        f"US 10Y 1M 변화 {_fmt(reit_sig['us10y_change'],2,'%p')}")}
    {sig_card("전체 대체자산 센티먼트",
        f'<span style="color:{sent_color}">{sentiment}</span>',
        f"OW {ow_count} / N {n_count} / UW {uw_count}")}
  </div>
</div>

<div class="card">
  <h2>🥇 귀금속 (Precious Metals)</h2>
  <div style="padding:10px 14px;background:#fef9f0;border-left:4px solid #d97706;border-radius:0 8px 8px 0;font-size:12px;color:#78350f;margin-bottom:16px;line-height:1.6">
    💡 <strong>핵심 드라이버</strong>: 실질금리 방향 · 달러(DXY) 강도 · 지정학 리스크.
    실질금리 상승/달러 강세 → 금 역풍. 반대 환경 → 금 우호. Silver는 금 + 산업 수요 혼합.
  </div>
  <table>
    <thead><tr>
      <th>자산</th><th>현재가</th>
      <th>1M 수익률</th><th>3M 수익률</th><th>6M 수익률</th>
      <th>추세</th><th>1Y 백분위</th><th>의견</th>
    </tr></thead>
    <tbody>{precious_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>⛽ 에너지 원자재 (Energy)</h2>
  <div style="padding:10px 14px;background:#fff7ed;border-left:4px solid #ea580c;border-radius:0 8px 8px 0;font-size:12px;color:#7c2d12;margin-bottom:16px;line-height:1.6">
    💡 <strong>핵심 드라이버</strong>: 지정학 리스크(OPEC+·중동 분쟁) · 달러 강도 · 수급 밸런스.
    Nat Gas는 계절성·LNG 수출 수요에 별도 영향. VIX 급등 구간에선 지정학 프리미엄 확대.
  </div>
  <table>
    <thead><tr>
      <th>자산</th><th>현재가</th>
      <th>1M 수익률</th><th>3M 수익률</th><th>6M 수익률</th>
      <th>추세</th><th>1Y 백분위</th><th>의견</th>
    </tr></thead>
    <tbody>{energy_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>🔩 산업금속 — Dr. Copper</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
    <div style="padding:16px;background:#f0fdf4;border:1px solid #86efac;border-radius:8px">
      <div style="font-size:13px;font-weight:700;color:#15803d;margin-bottom:8px">경기 선행 신호 (Dr. Copper)</div>
      <div style="font-size:20px;font-weight:800;color:{cop_fg}">{copper["label"]}</div>
      <div style="font-size:12px;color:#166534;margin-top:6px">
        현재가: {_fmt(copper["last"])} USD/lb &nbsp;|&nbsp;
        1M {_fmt(copper["mom_1m"],2,'%')} &nbsp;|&nbsp; 3M {_fmt(copper["mom_3m"],2,'%')}
      </div>
    </div>
    <div style="padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:12px;color:#475569;line-height:1.8">
      <strong>구리를 경제 온도계로 읽는 법</strong><br>
      ▶ 구리 상승 + MA200 상향돌파 → 글로벌 제조업 · 건설 수요 회복<br>
      ▶ 구리 하락 + MA200 하향이탈 → 경기 둔화 선행<br>
      ▶ 구리 vs. Gold 비율 상승 → 위험선호 / 하락 → 안전선호
    </div>
  </div>
  <table>
    <thead><tr>
      <th>자산</th><th>현재가</th>
      <th>1M 수익률</th><th>3M 수익률</th><th>6M 수익률</th>
      <th>추세</th><th>1Y 백분위</th><th>의견</th>
    </tr></thead>
    <tbody>{industrial_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>🏢 상장 부동산 (REIT)</h2>
  <div style="padding:10px 14px;background:#eff6ff;border-left:4px solid #3b82f6;border-radius:0 8px 8px 0;font-size:12px;color:#1e40af;margin-bottom:16px;line-height:1.6">
    💡 <strong>핵심 드라이버</strong>: US 10Y 국채 수익률 방향 (금리 하락 = REIT 우호).
    금리가 하락할 때 REIT 배당 수익의 상대적 매력이 높아지고 부동산 자산가치도 상승.
    SPDR REIT(XLRE) = US 상장 리츠 ETF.
  </div>
  <table>
    <thead><tr>
      <th>자산</th><th>현재가</th>
      <th>1M 수익률</th><th>3M 수익률</th><th>6M 수익률</th>
      <th>추세</th><th>1Y 백분위</th><th>의견</th>
    </tr></thead>
    <tbody>{reit_rows}</tbody>
  </table>
</div>

<div class="card">
  <h2>🧭 달러·리스크 오버레이 매트릭스</h2>
  <div style="font-size:12px;color:#64748b;margin-bottom:14px">
    달러(DXY) 방향 × 리스크 환경(VIX 레벨)에 따른 대체자산 포지셔닝 가이드.
    현재 환경: <strong style="color:{dxy_fg}">{dxy["label"]}</strong> &amp;
    <strong style="color:{vix_fg}">{vix["label"]}</strong>
  </div>
  <table style="border-collapse:collapse;width:100%;font-size:13px">
    <thead>
      <tr style="background:#f1f5f9">
        <th style="padding:10px 14px;border:1px solid #e2e8f0;text-align:left">구분</th>
        <th style="padding:10px 14px;border:1px solid #e2e8f0">달러 강세 (DXY↑)</th>
        <th style="padding:10px 14px;border:1px solid #e2e8f0">달러 약세 (DXY↓)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e2e8f0;font-weight:600;background:#fef2f2;color:#991b1b">
          리스크 오프<br><span style="font-size:11px;font-weight:400">VIX &gt; 25</span>
        </td>
        {overlay_cell("Gold OW · REIT UW",   "OW", "안전자산 수요 + 달러 강세 혼재 → 금 단기 방어, 원자재 전반 역풍", "rgba(220,38,38,0.04)")}
        {overlay_cell("Gold OW · Oil 관망",   "OW", "달러 약세 + 위기 → 금 강한 우위. 유가는 수요 우려 vs. 공급 충격 혼조", "rgba(5,150,105,0.04)")}
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e2e8f0;font-weight:600;background:#f0fdf4;color:#166534">
          리스크 온<br><span style="font-size:11px;font-weight:400">VIX &lt; 20</span>
        </td>
        {overlay_cell("Oil N · Gold UW",      "N",  "달러 강세 → 원자재 전반 헤드윈드. 달러 표시 가격 압박. 금 실질금리 의존", "rgba(148,163,184,0.06)")}
        {overlay_cell("Oil OW · Copper OW",   "OW", "달러 약세 + 위험선호 → 에너지·산업금속 최우선. Gold는 실질금리 따라", "rgba(5,150,105,0.06)")}
      </tr>
    </tbody>
  </table>
</div>

<div class="card">
  <h2>📋 변액보험 대체자산 포지셔닝 권고</h2>
  <div style="background:var(--primary-light);border-left:4px solid var(--primary);border-radius:0 8px 8px 0;padding:16px 20px;margin-bottom:12px">
    <ul style="list-style:none;padding:0">
      {alm_html}
    </ul>
  </div>
  <p class="muted" style="font-size:12px">
    📌 대체자산 배분 원칙 (변액보험): 공모 펀드 편입 가능 자산 = 상장 ETF(Gold ETF·REITs·원자재 ETF) 기준.
    비유동성 프리미엄(인프라·사모대출)은 K-ICS 비율 및 유동성 테스트 후 별도 검토.
    대체자산 전체 비중은 통상 10~20% 내에서 운영.
  </p>
</div>
"""

    return html_page(
        title="대체자산 View",
        date_str=date_str,
        body=body,
        current_view="alternative",
        source="yfinance (Gold·Silver·Oil·Copper·REIT) · investing.com (WTI·Brent·Nat Gas·Copper)",
    )


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Alternative Assets View")
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    data = compute_alternative_view(target)

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
