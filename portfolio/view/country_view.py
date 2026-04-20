"""Country allocation view — 국가별 투자 배분 의견.

8개국 주식시장에 대한 OW/N/UW 배분 의견을 생성한다.
- 신호: 주가 모멘텀(3/6/12M), vs ACWI 초과수익, FX 추세, 매크로 국면(2×2)
- KRW 투자자 관점: 원화 환산 수익률 + 환헤지 권고
- 변액보험 펀드 유형 매핑: OW/UW → 펀드 비중 확대/축소 방향

Usage:
    python -m portfolio.view.country_view --date 2026-04-14 --html
"""

import argparse
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "country"
MARKET_CSV = ROOT / "history" / "market_data.csv"
MACRO_CSV = ROOT / "history" / "macro_indicators.csv"

# ── Country definitions ────────────────────────────────────────────────────
# fx_code: 해당 통화의 USD 기준 가격 지표 (higher = USD 강세 = 현지통화 약세)
# fx_usd_based: True면 USD/XXX (높을수록 현지통화 약세)
#               False면 XXX/USD (높을수록 현지통화 강세 → FX 긍정)
COUNTRIES = {
    "US": {
        "name": "미국", "flag": "🇺🇸",
        "eq_code": "EQ_SP500",
        "fx_code": None,          # 기준 통화 — FX 신호 없음
        "fx_usd_based": None,
        "macro_gdp": "US_GDP_QOQ",
        "macro_cpi": "US_CPI_YOY",
        "fund_type": "해외주식형(미국)",
    },
    "KR": {
        "name": "한국", "flag": "🇰🇷",
        "eq_code": "EQ_KOSPI",
        "fx_code": "FX_USDKRW",   # 높을수록 원화 약세 (KR 주식 부정적)
        "fx_usd_based": True,
        "macro_gdp": "KR_GDP_QOQ",
        "macro_cpi": "KR_CPI_YOY",
        "fund_type": "국내주식형",
    },
    "JP": {
        "name": "일본", "flag": "🇯🇵",
        "eq_code": "EQ_NIKKEI225",
        "fx_code": "FX_USDJPY",   # 높을수록 엔화 약세 (수출기업 유리, 혼재)
        "fx_usd_based": True,
        "macro_gdp": "JP_GDP_QOQ",
        "macro_cpi": "JP_CPI_YOY",
        "fund_type": "해외주식형(일본)",
    },
    "CN": {
        "name": "중국", "flag": "🇨🇳",
        "eq_code": "EQ_SHANGHAI",
        "fx_code": "FX_USDCNY",   # 높을수록 위안화 약세
        "fx_usd_based": True,
        "macro_gdp": "CN_GDP_YOY",
        "macro_cpi": "CN_CPI_YOY",
        "fund_type": "해외주식형(중국)",
    },
    "EU": {
        "name": "유럽", "flag": "🇪🇺",
        "eq_code": "EQ_EUROSTOXX50",
        "fx_code": "FX_EURUSD",   # 높을수록 유로화 강세 (KR 투자자에게 긍정)
        "fx_usd_based": False,
        "macro_gdp": "EU_GDP_QOQ",
        "macro_cpi": "EU_CPI_YOY",
        "fund_type": "해외주식형(유럽)",
    },
    "UK": {
        "name": "영국", "flag": "🇬🇧",
        "eq_code": "EQ_FTSE100",
        "fx_code": "FX_GBPUSD",   # 높을수록 파운드 강세
        "fx_usd_based": False,
        "macro_gdp": "UK_GDP_QOQ",
        "macro_cpi": "UK_CPI_YOY",
        "fund_type": "해외주식형(선진국)",
    },
    "IN": {
        "name": "인도", "flag": "🇮🇳",
        "eq_code": "EQ_NIFTY50",
        "fx_code": "FX_USDINR",   # 높을수록 루피 약세
        "fx_usd_based": True,
        "macro_gdp": "IN_GDP_YOY",
        "macro_cpi": "IN_CPI_YOY",
        "fund_type": "해외주식형(이머징)",
    },
    "EM": {
        "name": "신흥국(EM)", "flag": "🌍",
        "eq_code": "EQ_MSCI_LATAM",
        "fx_code": None,
        "fx_usd_based": None,
        "macro_gdp": None,
        "macro_cpi": None,
        "fund_type": "해외주식형(이머징)",
    },
    "DE": {
        "name": "독일", "flag": "🇩🇪",
        "eq_code": "EQ_DAX",
        "fx_code": "FX_EURUSD",
        "fx_usd_based": False,
        "macro_gdp": None,
        "macro_cpi": None,
        "fund_type": "해외주식형(유럽)",
    },
    "FR": {
        "name": "프랑스", "flag": "🇫🇷",
        "eq_code": "EQ_CAC40",
        "fx_code": "FX_EURUSD",
        "fx_usd_based": False,
        "macro_gdp": None,
        "macro_cpi": None,
        "fund_type": "해외주식형(유럽)",
    },
    "TW": {
        "name": "대만", "flag": "🇹🇼",
        "eq_code": "EQ_TWSE",
        "fx_code": None,
        "fx_usd_based": None,
        "macro_gdp": None,
        "macro_cpi": None,
        "fund_type": "해외주식형(이머징)",
    },
}

ACWI_CODE = "EQ_MSCI_ACWI"


# ── Data loaders ──────────────────────────────────────────────────────────

def _load_prices(date: str) -> pd.DataFrame:
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    target = pd.Timestamp(date)
    return wide[wide.index <= target].sort_index()


def _load_macro(date: str) -> pd.DataFrame:
    if not MACRO_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(MACRO_CSV, parse_dates=["DATE"])
    target = pd.Timestamp(date)
    return df[df["DATE"] <= target].sort_values("DATE")


def _latest_macro(macro_df: pd.DataFrame, code: str) -> float:
    sub = macro_df[macro_df["INDICATOR_CODE"] == code]
    if sub.empty:
        return np.nan
    return float(sub.iloc[-1]["VALUE"])


# ── Signal calculators ───────────────────────────────────────────────────

def _momentum(px: pd.Series, days: int) -> float:
    """단순 수익률 (소수점)."""
    if len(px) < days + 5:
        return np.nan
    return float(px.iloc[-1] / px.iloc[-days] - 1)


def _vs_acwi(px_country: pd.Series, px_acwi: pd.Series, days: int = 126) -> float:
    """ACWI 대비 초과수익 (6M, ~126 거래일)."""
    if len(px_country) < days + 5 or len(px_acwi) < days + 5:
        return np.nan
    country_ret = float(px_country.iloc[-1] / px_country.iloc[-days] - 1)
    acwi_ret = float(px_acwi.iloc[-1] / px_acwi.iloc[-days] - 1)
    return country_ret - acwi_ret


def _fx_score(px_fx: pd.Series, usd_based: bool) -> int:
    """FX 추세 점수: +1(현지통화 강세/긍정), 0(중립), -1(현지통화 약세/부정).

    usd_based=True (USD/XXX): 높을수록 현지통화 약세 → 상승 = 부정
    usd_based=False (XXX/USD): 높을수록 현지통화 강세 → 상승 = 긍정
    """
    if len(px_fx) < 65:
        return 0
    ma20 = float(px_fx.tail(20).mean())
    ma60 = float(px_fx.tail(60).mean())
    last = float(px_fx.iloc[-1])
    above = (last > ma20) and (ma20 > ma60)  # 상승 추세
    below = (last < ma20) and (ma20 < ma60)  # 하락 추세

    if usd_based:
        # USD 강세 = 현지통화 약세 → 주식 부정
        if above:
            return -1   # USD 상승 추세 = 현지통화 약세
        elif below:
            return +1   # USD 하락 추세 = 현지통화 강세
    else:
        # XXX/USD: 현지통화/달러 = 높을수록 현지통화 강세
        if above:
            return +1
        elif below:
            return -1
    return 0


def _macro_regime(gdp: float, cpi: float) -> str:
    """2×2 국면 분류.

    Goldilocks:   성장 ↑ + 인플레 ↓(또는 적정)
    Reflation:    성장 ↑ + 인플레 ↑
    Stagflation:  성장 ↓ + 인플레 ↑
    Deflation:    성장 ↓ + 인플레 ↓
    """
    if np.isnan(gdp) or np.isnan(cpi):
        return "N/A"
    growing = gdp > 0
    inflating = cpi > 3.0  # 3% 이상을 "인플레이션 압력"으로 정의
    if growing and not inflating:
        return "Goldilocks"
    elif growing and inflating:
        return "Reflation"
    elif not growing and inflating:
        return "Stagflation"
    else:
        return "Deflation"


def _macro_score(regime: str) -> int:
    """매크로 국면 → 주식 친화도 점수 (-2~+2)."""
    return {
        "Goldilocks": 2,
        "Reflation": 1,
        "Deflation": -1,
        "Stagflation": -2,
        "N/A": 0,
    }.get(regime, 0)


# ── Multi-factor signal additions ─────────────────────────────────────────

# Known approximate policy rates for countries without FRED data (fallback table)
_APPROX_POLICY_RATES = {
    "JP": 0.1,    # BOJ 0% ~ +0.1% (2024)
    "CN": 3.45,   # PBoC LPR 1Y (2024)
    "EU": 4.0,    # ECB deposit rate (2024)
    "UK": 5.25,   # BOE (2024)
    "IN": 6.5,    # RBI (2024)
    "EM": 8.0,    # EM average estimate
    "US": np.nan, # from FRED
    "KR": np.nan, # from ECOS
}

_POLICY_RATE_MACRO_CODES = {
    "US": "US_FED_RATE",
    "KR": "KR_BOK_RATE",
}


def _carry_proxy(country_code: str, macro_df: pd.DataFrame, us_fed: float) -> int:
    """캐리 신호: 국가 정책금리 − US 연준금리.

    양수(국가 금리 > US) → 자본 유입 압력, 현지 자산 매력 증가 → +1
    음수(국가 금리 < US) → 달러 캐리 우호, USD 자산으로 자금 유출 압력 → -1

    KRW 투자자 입장에서 해외자산(USD) 배분 시:
    - KR 금리 > US → 헤지 비용 낮음 (유리) → 해외 OW 여지
    - KR 금리 < US → 헤지 비용 높음 (불리) → 해외 UW 압력
    """
    # US가 기준이므로 0
    if country_code == "US":
        return 0

    # macro_df에서 정책금리 조회
    rate_code = _POLICY_RATE_MACRO_CODES.get(country_code)
    if rate_code and not macro_df.empty:
        sub = macro_df[macro_df["INDICATOR_CODE"] == rate_code]
        if not sub.empty:
            local_rate = float(sub.sort_values("DATE").iloc[-1]["VALUE"])
        else:
            local_rate = _APPROX_POLICY_RATES.get(country_code, np.nan)
    else:
        local_rate = _APPROX_POLICY_RATES.get(country_code, np.nan)

    if np.isnan(local_rate) or np.isnan(us_fed):
        return 0

    diff = local_rate - us_fed
    if diff > 0.5:
        return +1
    elif diff < -0.5:
        return -1
    return 0


def _value_proxy(eq_px: pd.Series, acwi_px: pd.Series) -> int:
    """밸류 프록시: 단기 모멘텀 대비 장기 모멘텀 역전 신호.

    단기(3M) 수익률 < 장기(12M) 수익률 → 최근 조정, 저평가 가능성 → +1(Value 매력)
    단기 >> 장기 → 최근 과매수, 고평가 가능성 → -1

    ACWI 대비 3년 누적 상대수익률도 고려 (원래 계획은 P/E인데 데이터 없음).
    """
    if len(eq_px) < 260:
        return 0

    mom_3m  = float(eq_px.iloc[-1] / eq_px.iloc[-63]  - 1) if len(eq_px) >= 66  else np.nan
    mom_12m = float(eq_px.iloc[-1] / eq_px.iloc[-252] - 1) if len(eq_px) >= 255 else np.nan

    if np.isnan(mom_3m) or np.isnan(mom_12m):
        return 0

    # 최근 급등 후 단기 조정 = Value 신호
    if mom_3m < -0.05 and mom_12m > 0.10:
        return +1   # 단기 조정, 장기 추세 양호 → 매수 기회
    elif mom_3m > 0.10 and mom_12m < 0.02:
        return -1   # 단기 급등, 장기 성과 부진 → 과매수
    return 0


def _dynamic_hedge(prices: pd.DataFrame) -> dict:
    """USDKRW 변동성 기반 동적 환헤지 비율 계산.

    Returns:
        vol_30d: 30일 연율화 변동성
        vol_1y_pct: 1년 히스토리 내 현재 vol 백분위
        base_ratio: 기본 헤지 비율 (0.7)
        adj_ratio: 변동성 조정 헤지 비율
        note: 권고 메모
    """
    code = "FX_USDKRW"
    result = {"vol_30d": np.nan, "vol_1y_pct": np.nan,
              "base_ratio": 0.7, "adj_ratio": 0.7, "note": "데이터 부족"}

    if code not in prices.columns:
        return result

    px = prices[code].dropna()
    if len(px) < 35:
        return result

    log_ret = np.log(px / px.shift(1)).dropna()
    vol_30d = float(log_ret.iloc[-30:].std() * np.sqrt(252) * 100) if len(log_ret) >= 30 else np.nan

    if np.isnan(vol_30d):
        return result

    result["vol_30d"] = round(vol_30d, 2)

    # 1Y 백분위
    if len(log_ret) >= 252:
        vol_series = log_ret.rolling(30).std() * np.sqrt(252) * 100
        vol_series = vol_series.dropna()
        pct = float(np.sum(vol_series <= vol_30d) / len(vol_series) * 100)
        result["vol_1y_pct"] = round(pct, 1)
    else:
        pct = 50.0

    # 조정 헤지 비율
    base = 0.7
    if vol_30d > 15:       # 고변동성: 헤지 효과 불확실 → 비율 축소
        adj = max(base - 0.15, 0.4)
        note = f"USDKRW 변동성 {vol_30d:.1f}% (고위험) → 헤지 비율 {adj:.0%} 권고"
    elif vol_30d < 7:       # 저변동성: 헤지 비용 낮고 안정 → 비율 확대
        adj = min(base + 0.10, 0.90)
        note = f"USDKRW 변동성 {vol_30d:.1f}% (안정) → 헤지 비율 {adj:.0%} 권고"
    else:
        adj = base
        note = f"USDKRW 변동성 {vol_30d:.1f}% (중립) → 기본 헤지 비율 {adj:.0%} 유지"

    result["adj_ratio"] = round(adj, 2)
    result["note"] = note
    return result


# ── Composite OW/N/UW ────────────────────────────────────────────────────

def _composite(mom_3m, mom_6m, mom_12m, excess_6m, fx_s, mac_s,
               carry_s=0, value_s=0) -> float:
    """복합 점수 (-1 ~ +1 내외). carry/value 추가."""
    def _safe(v, w):
        return 0.0 if np.isnan(v) else np.sign(v) * w

    score = (
        _safe(mom_3m,   0.13)
        + _safe(mom_6m,   0.18)
        + _safe(mom_12m,  0.13)
        + _safe(excess_6m,0.18)
        + (fx_s    * 0.13)
        + (mac_s / 2 * 0.13)
        + (carry_s * 0.08)
        + (value_s * 0.04)
    )
    return round(score, 3)


def _view_label(score: float) -> str:
    if score > 0.25:
        return "OW"
    elif score < -0.25:
        return "UW"
    return "N"


# ── KRW investor signals ─────────────────────────────────────────────────

def _krw_fx_return(prices: pd.DataFrame, days: int = 126) -> dict:
    """USDKRW 추세 요약 — KRW 투자자의 환헤지 방향."""
    code = "FX_USDKRW"
    if code not in prices.columns or len(prices[code].dropna()) < days + 5:
        return {"trend": "N/A", "chg_6m": np.nan, "hedge_rec": "데이터 부족"}

    px = prices[code].dropna()
    chg_6m = float(px.iloc[-1] / px.iloc[-days] - 1) * 100
    ma20 = float(px.tail(20).mean())
    ma60 = float(px.tail(60).mean())
    last = float(px.iloc[-1])

    if last > ma20 > ma60:
        trend = "원화 약세"
        # USD 강세 구간 → 해외 자산(USD) 수익 추가 → 헤지 비용보다 이득
        hedge_rec = "부분 헤지 권고 (USD 강세 → 해외자산 수익 확대)"
    elif last < ma20 < ma60:
        trend = "원화 강세"
        hedge_rec = "전체 헤지 권고 (USD 약세 → 환손실 위험)"
    else:
        trend = "횡보"
        hedge_rec = "중립 (방향성 불명확)"

    return {"trend": trend, "chg_6m": round(chg_6m, 2), "hedge_rec": hedge_rec}


# ── Main compute ─────────────────────────────────────────────────────────

def compute_country_view(date: str) -> dict:
    """국가별 OW/N/UW 신호와 KRW 환율 관점을 반환."""
    prices = _load_prices(date)
    macro_df = _load_macro(date)

    acwi = prices[ACWI_CODE].dropna() if ACWI_CODE in prices.columns else pd.Series(dtype=float)

    # US Fed rate for carry calculation
    us_fed_sub = macro_df[macro_df["INDICATOR_CODE"] == "US_FED_RATE"]
    us_fed = float(us_fed_sub.sort_values("DATE").iloc[-1]["VALUE"]) if not us_fed_sub.empty else np.nan

    results = []
    for code, info in COUNTRIES.items():
        eq_c = info["eq_code"]
        fx_c = info["fx_code"]
        usd_based = info["fx_usd_based"]

        # Price series
        eq_px = prices[eq_c].dropna() if eq_c in prices.columns else pd.Series(dtype=float)
        fx_px = prices[fx_c].dropna() if (fx_c and fx_c in prices.columns) else pd.Series(dtype=float)

        # Momentum
        mom_3m = _momentum(eq_px, 63)
        mom_6m = _momentum(eq_px, 126)
        mom_12m = _momentum(eq_px, 252)

        # vs ACWI
        excess_3m = _vs_acwi(eq_px, acwi, 63)
        excess_6m = _vs_acwi(eq_px, acwi, 126)

        # FX
        if fx_c and not fx_px.empty and usd_based is not None:
            fx_s = _fx_score(fx_px, usd_based)
        else:
            fx_s = 0

        # Macro
        gdp_code = info["macro_gdp"]
        cpi_code = info["macro_cpi"]
        gdp_val = _latest_macro(macro_df, gdp_code) if gdp_code else np.nan
        cpi_val = _latest_macro(macro_df, cpi_code) if cpi_code else np.nan
        regime = _macro_regime(gdp_val, cpi_val)
        mac_s = _macro_score(regime)

        # ── New signals ──────────────────────────────────────────────
        carry_s = _carry_proxy(code, macro_df, us_fed)
        value_s = _value_proxy(eq_px, acwi)

        # Composite
        comp = _composite(mom_3m, mom_6m, mom_12m, excess_6m, fx_s, mac_s,
                          carry_s, value_s)
        view = _view_label(comp)

        # Latest price for display
        last_price = float(eq_px.iloc[-1]) if not eq_px.empty else np.nan
        last_date = str(eq_px.index[-1].date()) if not eq_px.empty else "—"
        fx_last = float(fx_px.iloc[-1]) if not fx_px.empty else np.nan

        # Carry rate info for display
        rate_code = _POLICY_RATE_MACRO_CODES.get(code)
        local_rate = np.nan
        if rate_code and not macro_df.empty:
            sub = macro_df[macro_df["INDICATOR_CODE"] == rate_code]
            if not sub.empty:
                local_rate = float(sub.sort_values("DATE").iloc[-1]["VALUE"])
        if np.isnan(local_rate):
            local_rate = _APPROX_POLICY_RATES.get(code, np.nan)

        results.append({
            "code": code,
            "name": info["name"],
            "flag": info["flag"],
            "fund_type": info["fund_type"],
            "eq_code": eq_c,
            "last_price": last_price,
            "last_date": last_date,
            "fx_last": fx_last,
            "mom_3m": round(mom_3m * 100, 2) if not np.isnan(mom_3m) else np.nan,
            "mom_6m": round(mom_6m * 100, 2) if not np.isnan(mom_6m) else np.nan,
            "mom_12m": round(mom_12m * 100, 2) if not np.isnan(mom_12m) else np.nan,
            "excess_3m": round(excess_3m * 100, 2) if not np.isnan(excess_3m) else np.nan,
            "excess_6m": round(excess_6m * 100, 2) if not np.isnan(excess_6m) else np.nan,
            "fx_score": fx_s,
            "gdp": round(gdp_val, 2) if not np.isnan(gdp_val) else np.nan,
            "cpi": round(cpi_val, 2) if not np.isnan(cpi_val) else np.nan,
            "regime": regime,
            "macro_score": mac_s,
            "carry_score": carry_s,
            "value_score": value_s,
            "local_rate": round(local_rate, 2) if not np.isnan(local_rate) else np.nan,
            "composite": comp,
            "view": view,
        })

    krw_fx = _krw_fx_return(prices)
    hedge_info = _dynamic_hedge(prices)

    return {
        "date": date,
        "countries": results,
        "krw_fx": krw_fx,
        "hedge_info": hedge_info,
        "us_fed_rate": round(us_fed, 2) if not np.isnan(us_fed) else np.nan,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ── HTML rendering ────────────────────────────────────────────────────────

def _fmt(v, suffix="", prec=2, na="—"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return na
    return f"{v:+.{prec}f}{suffix}" if suffix == "%" else f"{v:.{prec}f}{suffix}"


def _view_badge(view: str) -> str:
    color = {"OW": "#16a34a", "N": "#64748b", "UW": "#dc2626"}.get(view, "#64748b")
    bg = {"OW": "#dcfce7", "N": "#f1f5f9", "UW": "#fee2e2"}.get(view, "#f1f5f9")
    return f'<span style="background:{bg};color:{color};padding:3px 10px;border-radius:6px;font-weight:700;font-size:13px">{view}</span>'


def _regime_badge(regime: str) -> str:
    colors = {
        "Goldilocks":  ("#16a34a", "#dcfce7"),
        "Reflation":   ("#d97706", "#fef3c7"),
        "Stagflation": ("#dc2626", "#fee2e2"),
        "Deflation":   ("#2563eb", "#dbeafe"),
        "N/A":         ("#64748b", "#f1f5f9"),
    }
    fg, bg = colors.get(regime, ("#64748b", "#f1f5f9"))
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600">{regime}</span>'


def _fx_score_label(score: int) -> str:
    if score > 0:
        return '<span style="color:#16a34a">현지통화 강세 ↑</span>'
    elif score < 0:
        return '<span style="color:#dc2626">현지통화 약세 ↓</span>'
    return '<span style="color:#64748b">중립 →</span>'


def _chg_span(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    color = "#16a34a" if v >= 0 else "#dc2626"
    return f'<span style="color:{color}">{v:+.2f}%</span>'


def _carry_badge(s: int) -> str:
    if s > 0:  return '<span style="color:#16a34a;font-size:12px">캐리 ↑</span>'
    if s < 0:  return '<span style="color:#dc2626;font-size:12px">캐리 ↓</span>'
    return '<span style="color:#94a3b8;font-size:12px">—</span>'


def _value_badge(s: int) -> str:
    if s > 0:  return '<span style="color:#2563eb;font-size:12px">저평가</span>'
    if s < 0:  return '<span style="color:#f97316;font-size:12px">과매수</span>'
    return '<span style="color:#94a3b8;font-size:12px">—</span>'


def render_html(data: dict) -> str:
    from ._shared import nav_html, NAV_CSS
    date = data["date"]
    countries = data["countries"]
    krw_fx = data["krw_fx"]
    hedge_info = data.get("hedge_info", {})
    gen = data["generated_at"]
    us_fed = data.get("us_fed_rate", np.nan)
    _nav_html = nav_html(date, "country")

    # KRW 배너
    krw_trend = krw_fx.get("trend", "N/A")
    krw_chg = krw_fx.get("chg_6m", np.nan)
    krw_hedge = krw_fx.get("hedge_rec", "—")
    krw_banner_color = "#fef3c7" if "약세" in krw_trend else ("#dcfce7" if "강세" in krw_trend else "#f1f5f9")
    krw_chg_str = f"{krw_chg:+.2f}%" if not np.isnan(krw_chg) else "—"

    # Dynamic hedge card
    vol_30d    = hedge_info.get("vol_30d", np.nan)
    vol_pct    = hedge_info.get("vol_1y_pct", np.nan)
    adj_ratio  = hedge_info.get("adj_ratio", 0.7)
    hedge_note = hedge_info.get("note", "—")
    vol_color  = "#dc2626" if (not np.isnan(vol_30d) and vol_30d > 15) else \
                 "#d97706" if (not np.isnan(vol_30d) and vol_30d > 9) else "#059669"
    vol_str    = f"{vol_30d:.1f}%" if not np.isnan(vol_30d) else "—"
    vol_pct_str= f"{vol_pct:.0f}%ile" if not np.isnan(vol_pct) else "—"

    # Rows
    rows_html = ""
    for c in countries:
        view_b = _view_badge(c["view"])
        regime_b = _regime_badge(c["regime"])
        lr = c.get("local_rate", np.nan)
        lr_str = f"{lr:.2f}%" if not np.isnan(lr) else "—"
        carry_diff = round(lr - us_fed, 2) if (not np.isnan(lr) and not np.isnan(us_fed)) else np.nan
        carry_diff_str = f"{carry_diff:+.2f}%p" if not np.isnan(carry_diff) else "—"

        rows_html += f"""
        <tr>
          <td style="font-size:20px;text-align:center">{c["flag"]}</td>
          <td>
            <strong>{c["name"]}</strong>
            <div style="font-size:11px;color:#64748b;margin-top:2px">{c["fund_type"]}</div>
          </td>
          <td style="text-align:center">{view_b}</td>
          <td style="text-align:right">{_chg_span(c["mom_3m"])}</td>
          <td style="text-align:right">{_chg_span(c["mom_6m"])}</td>
          <td style="text-align:right">{_chg_span(c["mom_12m"])}</td>
          <td style="text-align:right">{_chg_span(c["excess_6m"])}</td>
          <td style="text-align:center">{_fx_score_label(c["fx_score"])}</td>
          <td style="text-align:center">{regime_b}</td>
          <td style="text-align:center;font-size:11px">{lr_str}<br><span style="color:#94a3b8">{carry_diff_str}</span></td>
          <td style="text-align:center">{_carry_badge(c.get("carry_score",0))}</td>
          <td style="text-align:center">{_value_badge(c.get("value_score",0))}</td>
          <td style="text-align:right;font-family:monospace;font-size:13px">{c["composite"]:+.3f}</td>
        </tr>"""

    # OW/UW 요약 칩
    ow_countries = [c for c in countries if c["view"] == "OW"]
    uw_countries = [c for c in countries if c["view"] == "UW"]

    ow_chips = " ".join(
        f'<span style="background:#dcfce7;color:#16a34a;padding:3px 10px;border-radius:6px;font-size:13px;font-weight:600">{c["flag"]} {c["name"]}</span>'
        for c in ow_countries
    ) or '<span style="color:#64748b">없음</span>'
    uw_chips = " ".join(
        f'<span style="background:#fee2e2;color:#dc2626;padding:3px 10px;border-radius:6px;font-size:13px;font-weight:600">{c["flag"]} {c["name"]}</span>'
        for c in uw_countries
    ) or '<span style="color:#64748b">없음</span>'

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Country View — {date}</title>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{
  --bg: #f4f5f9; --card: #fff; --border: #e0e3ed;
  --text: #2d3148; --muted: #7c8298; --primary: #F58220; --navy: #043B72;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Spoqa Han Sans Neo',sans-serif; background:var(--bg); color:var(--text); }}
.header {{ margin-bottom:24px; padding-bottom:20px; border-bottom:2px solid var(--border); }}
.header h1 {{ font-size:26px; font-weight:700; }}
.header .sub {{ font-size:14px; color:var(--muted); margin-top:6px; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px 24px; margin-bottom:20px; box-shadow:0 2px 6px rgba(0,0,0,.04); }}
.card h2 {{ font-size:16px; font-weight:700; margin-bottom:14px; }}
.krw-banner {{ border-radius:10px; padding:14px 20px; margin-bottom:20px; font-size:14px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
thead tr {{ background:#f8f9fc; }}
th {{ padding:10px 10px; font-weight:600; font-size:11px; color:var(--muted); text-align:center; border-bottom:2px solid var(--border); white-space:nowrap; }}
td {{ padding:9px 10px; border-bottom:1px solid #f0f1f7; vertical-align:middle; }}
tr:hover td {{ background:#fafbff; }}
.summary-row {{ display:flex; gap:24px; flex-wrap:wrap; margin-bottom:12px; }}
.summary-item .label {{ font-size:12px; color:var(--muted); margin-bottom:4px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; }}
.footer {{ text-align:center; font-size:12px; color:var(--muted); margin-top:32px; padding-top:16px; border-top:1px solid var(--border); }}
.stat-grid {{ display:flex;gap:16px;flex-wrap:wrap;margin-top:12px }}
.stat-card {{ background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 18px;min-width:160px;flex:1 }}
.stat-card .label {{ font-size:11px;color:#94a3b8;margin-bottom:4px }}
.stat-card .value {{ font-size:20px;font-weight:800 }}
{NAV_CSS}
</style>
</head>
<body>
{_nav_html}
<div style="max-width:1400px;margin:0 auto;padding:28px 24px 48px">
<div class="header">
  <h1>🌍 Country Allocation View</h1>
  <div class="sub">국가별 투자 배분 의견 (Momentum+FX+Macro+Carry+Value) &nbsp;|&nbsp; 기준일: {date} &nbsp;|&nbsp; 생성: {gen}</div>
</div>

<!-- KRW 투자자 배너 -->
<div class="krw-banner" style="background:{krw_banner_color};border:1px solid #e0e3ed">
  <strong>🇰🇷 변액보험 KRW 투자자 환율 신호</strong>&nbsp;&nbsp;
  USDKRW 추세: <strong>{krw_trend}</strong> (6M 변화: {krw_chg_str}) &nbsp;|&nbsp; 💱 {krw_hedge}
</div>

<!-- 요약 -->
<div class="card">
  <h2>📊 배분 요약</h2>
  <div class="summary-row">
    <div class="summary-item">
      <div class="label">Overweight (OW)</div>
      <div class="chips">{ow_chips}</div>
    </div>
    <div class="summary-item">
      <div class="label">Underweight (UW)</div>
      <div class="chips">{uw_chips}</div>
    </div>
  </div>
</div>

<!-- 동적 환헤지 권고 -->
<div class="card">
  <h2>💱 동적 환헤지 권고 (USDKRW 변동성 기반)</h2>
  <div class="stat-grid">
    <div class="stat-card" style="border-top:3px solid {vol_color}">
      <div class="label">USDKRW 30D 변동성(연율)</div>
      <div class="value" style="color:{vol_color}">{vol_str}</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:4px">1Y 백분위 {vol_pct_str}</div>
    </div>
    <div class="stat-card">
      <div class="label">기본 헤지 비율</div>
      <div class="value" style="color:#64748b">70%</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:4px">변액보험 기본값</div>
    </div>
    <div class="stat-card" style="border-top:3px solid {vol_color}">
      <div class="label">변동성 조정 권고 헤지 비율</div>
      <div class="value" style="color:{vol_color}">{adj_ratio:.0%}</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:4px">{hedge_note}</div>
    </div>
    <div class="stat-card" style="flex:2">
      <div class="label">US Fed Rate (캐리 기준)</div>
      <div class="value" style="color:#475569">{f"{us_fed:.2f}%" if not np.isnan(us_fed) else "—"}</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:4px">각국 금리 − US Fed = 캐리 스프레드 (양수 → 현지 자산 매력)</div>
    </div>
  </div>
</div>

<!-- 국가별 상세 -->
<div class="card">
  <h2>🗺️ 국가별 신호 상세 (Momentum + FX + Macro + Carry + Value)</h2>
  <table>
    <thead>
      <tr>
        <th></th>
        <th style="text-align:left">국가</th>
        <th>배분의견</th>
        <th>3M 수익</th>
        <th>6M 수익</th>
        <th>12M 수익</th>
        <th>vs ACWI(6M)</th>
        <th>FX 신호</th>
        <th>매크로 국면</th>
        <th>정책금리<br>캐리차</th>
        <th>캐리</th>
        <th>밸류</th>
        <th>복합점수</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>

<!-- 해석 안내 -->
<div class="card" style="font-size:13px;color:var(--muted)">
  <strong>해석 안내</strong>
  &nbsp;|&nbsp; <span style="color:#16a34a">OW</span> 복합점수 > +0.25
  &nbsp;|&nbsp; <span style="color:#64748b">N</span> ±0.25 이내
  &nbsp;|&nbsp; <span style="color:#dc2626">UW</span> < −0.25
  <br><br>
  복합점수 = 3M모멘텀(13%) + 6M모멘텀(18%) + 12M모멘텀(13%) + vs ACWI(18%) + FX 추세(13%) + 매크로 국면(13%) + <strong>캐리(8%) + 밸류(4%)</strong>
  <br>캐리: 현지 정책금리 − US Fed Rate. 양수 = 현지 금리 우위 → 자본 유입 압력.
  <br>밸류 프록시: 단기 조정(3M < −5%) + 장기 성과(12M > +10%) → 저평가 신호.
</div>

<div class="footer">Country View &nbsp;·&nbsp; 미래에셋생명 변액보험 운용 참고 &nbsp;·&nbsp; 본 자료는 투자 권유가 아닙니다</div>
</div>
</body>
</html>"""
    return html


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    data = compute_country_view(args.date)

    if args.html:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        html = render_html(data)
        out_path = OUTPUT_DIR / f"{args.date}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"Saved: {out_path}")
    else:
        for c in data["countries"]:
            print(f"{c['flag']} {c['name']:10s} {c['view']:3s}  composite={c['composite']:+.3f}  regime={c['regime']}")
        print(f"\nKRW: {data['krw_fx']['trend']}  {data['krw_fx']['hedge_rec']}")


if __name__ == "__main__":
    main()
