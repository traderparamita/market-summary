"""Regime View — rule-based synthesis of macro + price + correlation views.

Combines signals from all three views and generates Korean-language investment
commentary using deterministic rule-based logic. No external API required.

Usage:
    python -m portfolio.view.regime_view --date 2026-04-13 --html
    python -m portfolio.view.regime_view --date 2026-04-13
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from .macro_view import compute_macro_view
from .price_view import compute_price_view, AC_LABELS
from .correlation_view import compute_correlation_view

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "regime"


# ── Korean label maps ─────────────────────────────────────────────────

_MACRO_REGIME_KR = {
    "Goldilocks":  "골디락스 (성장↑ 물가↓)",
    "Reflation":   "리플레이션 (성장↑ 물가↑)",
    "Stagflation": "스태그플레이션 (성장↓ 물가↑)",
    "Deflation":   "디플레이션 (성장↓ 물가↓)",
    "Unknown":     "불확실",
}

_PRICE_REGIME_KR = {
    "RiskON":  "위험선호",
    "RiskOFF": "위험회피",
    "Neutral": "중립",
}


# ── Formatting helpers ────────────────────────────────────────────────

def _f(v, fmt: str = ".2f", fallback: str = "N/A") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return fallback
    return format(v, fmt)


def _pct(v, fallback: str = "N/A") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return fallback
    return f"{v:.0%}"


def _isnan(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


# ── Signal extraction ─────────────────────────────────────────────────

def _find_val(group_list: list, code: str) -> Optional[float]:
    for ind in group_list:
        if ind["code"] == code:
            return ind["value"]
    return None


def _build_signals(macro: dict, price: dict, corr: dict) -> dict:
    """Extract and flatten key signals from all three views into one dict."""
    pulse    = price.get("market_pulse", {})
    ac_views = price.get("asset_class_views", [])

    us = macro.get("us", {})
    kr = macro.get("kr", {})

    us_gdp_qoq   = _find_val(us.get("growth",    []), "US_GDP_QOQ")
    us_cpi_yoy   = _find_val(us.get("inflation",  []), "US_CPI_YOY")
    us_unemp     = _find_val(us.get("employment", []), "US_UNEMP_RATE")
    us_fed_rate  = _find_val(us.get("policy",     []), "US_FED_RATE")
    us_10y       = _find_val(us.get("policy",     []), "US_10Y_YIELD")
    us_2y        = _find_val(us.get("policy",     []), "US_2Y_YIELD")
    us_yc        = _find_val(us.get("policy",     []), "US_YIELD_CURVE")
    us_hy_spread = _find_val(us.get("credit",     []), "US_HY_SPREAD")
    us_ig_spread = _find_val(us.get("credit",     []), "US_IG_SPREAD")
    fed_implied  = _find_val(us.get("policy",     []), "FED_IMPLIED_DELTA")
    us_real_rate = _find_val(us.get("liquidity",  []), "US_REAL_RATE")
    us_m2        = _find_val(us.get("liquidity",  []), "US_M2_YOY")

    kr_gdp_qoq   = _find_val(kr.get("growth",    []), "KR_GDP_QOQ")
    kr_cpi_yoy   = _find_val(kr.get("inflation",  []), "KR_CPI_YOY")
    kr_base_rate = _find_val(kr.get("policy",     []), "KR_BASE_RATE")

    # Yield curve: macro source first, price_view fallback
    yc = us_yc if not _isnan(us_yc) else pulse.get("yield_curve")

    eb = corr.get("equity_bond_corr", {})

    ow_list = [ac["class"] for ac in ac_views if ac["view_int"] >= 1]
    uw_list = [ac["class"] for ac in ac_views if ac["view_int"] <= -1]
    n_list  = [ac["class"] for ac in ac_views if ac["view_int"] == 0]

    return {
        # Macro
        "us_regime":         macro.get("us_regime", {}).get("label", "Unknown"),
        "kr_regime":         macro.get("kr_regime", {}).get("label", "Unknown"),
        "regime_divergence": macro.get("regime_divergence", False),
        "us_gdp_qoq":    us_gdp_qoq,
        "us_cpi_yoy":    us_cpi_yoy,
        "us_unemp":      us_unemp,
        "us_fed_rate":   us_fed_rate,
        "us_10y_yield":  us_10y,
        "us_2y_yield":   us_2y,
        "yield_curve":   yc,
        "us_hy_spread":  us_hy_spread,
        "us_ig_spread":  us_ig_spread,
        "fed_implied":   fed_implied,
        "us_real_rate":  us_real_rate,
        "us_m2_yoy":     us_m2,
        "kr_gdp_qoq":    kr_gdp_qoq,
        "kr_cpi_yoy":    kr_cpi_yoy,
        "kr_base_rate":  kr_base_rate,
        # Price
        "price_regime":     pulse.get("market_regime", "Neutral"),
        "regime_duration":  pulse.get("regime_duration", 0),
        "regime_since":     pulse.get("regime_since", "—"),
        "vix":              pulse.get("vix"),
        "vix_1m_chg":       pulse.get("vix_1m_chg"),
        "vix_direction":    pulse.get("vix_direction"),
        "breadth_ma200":    pulse.get("breadth_ma200"),
        "dxy_trend":        pulse.get("dxy_trend", "—"),
        "dxy_3m_chg":       pulse.get("dxy_3m_chg"),
        "sentiment_score":  pulse.get("sentiment_score", 0),
        "sentiment_label":  pulse.get("sentiment_label", "Neutral"),
        "ow_assets":        ow_list,
        "uw_assets":        uw_list,
        "n_assets":         n_list,
        # Correlation
        "corr_30d":      eb.get("30d"),
        "corr_60d":      eb.get("60d"),
        "corr_90d":      eb.get("90d"),
        "corr_signal":   eb.get("signal", "—"),
        "regime_change": corr.get("regime_change", False),
    }


# ── Section 1: 현재 국면 진단 ─────────────────────────────────────────

def _diagnosis(s: dict) -> str:
    us_r  = s["us_regime"]
    kr_r  = s["kr_regime"]
    pr    = s["price_regime"]
    sent  = s["sentiment_score"]
    dur   = s["regime_duration"]
    since = s["regime_since"]
    div   = s["regime_divergence"]
    yc    = s["yield_curve"]
    vix   = s["vix"]
    bm    = s["breadth_ma200"]

    us_kr = _MACRO_REGIME_KR.get(us_r, us_r)
    kr_kr = _MACRO_REGIME_KR.get(kr_r, kr_r)

    # Macro sentence
    if not div:
        macro_sent = (
            f"미국과 한국 거시경제 모두 현재 **{us_kr}** 국면에 있으며, "
            "양국의 경기 방향성이 일치하고 있다."
        )
    else:
        macro_sent = (
            f"미국 거시경제는 **{us_kr}** 국면인 반면 한국은 **{kr_kr}** 국면으로, "
            "양국 간 경기 국면이 상이하다. 이는 통화·무역 채널을 통해 한국 수출 기업 실적에 "
            "엇갈린 영향을 줄 수 있다."
        )

    # Price regime sentence
    pr_kr = _PRICE_REGIME_KR.get(pr, pr)
    dur_str = (
        f" ({dur}일째 지속, {since} 이후)" if dur > 0 and since != "—" else ""
    )
    if pr == "RiskOFF":
        price_sent = (
            f"가격 신호는 **{pr_kr}** 레짐{dur_str}에 진입해 있어, "
            "변동성 상승 또는 시장 폭 약화가 관찰되고 있다. "
            "방어적 자산 배분 및 포지션 관리가 요구된다."
        )
    elif pr == "RiskON":
        price_sent = (
            f"가격 신호는 **{pr_kr}** 레짐{dur_str}으로, "
            "모멘텀과 추세 지표 모두 우호적 환경을 형성하고 있다. "
            "공격적 비중 확대의 기술적 여건은 충족된 상태다."
        )
    else:
        price_sent = (
            f"가격 신호는 **{pr_kr}** 레짐{dur_str}이며, "
            "강한 방향성보다는 선별적 접근이 유효한 구간이다. "
            "레짐 전환 신호를 확인하며 점진적 대응이 적절하다."
        )

    # Sentiment sentence
    if sent <= -60:
        sent_sent = (
            f"시장 심리 지수는 극단적 공포 수준(점수: {sent:+d})으로, "
            "과매도 구간에서의 역발상 매수 관점도 검토 가능하다."
        )
    elif sent <= -20:
        sent_sent = (
            f"시장 심리 지수는 공포 구간(점수: {sent:+d})에 위치해, "
            "투자자들의 위험 회피 성향이 강화되어 있다."
        )
    elif sent >= 60:
        sent_sent = (
            f"시장 심리 지수는 극단적 탐욕 수준(점수: {sent:+d})으로, "
            "과매수 신호에 주의가 필요하며 차익 실현 기회를 점검할 시점이다."
        )
    elif sent >= 20:
        sent_sent = (
            f"시장 심리 지수는 탐욕 구간(점수: {sent:+d})으로, "
            "위험 선호 분위기가 우세하나 점진적 경계감을 유지하는 것이 적절하다."
        )
    else:
        sent_sent = (
            f"시장 심리 지수는 중립 구간(점수: {sent:+d})으로, "
            "공포와 탐욕 사이에서 방향성을 탐색하고 있다."
        )

    # Yield curve addendum
    yc_addendum = ""
    if not _isnan(yc):
        if yc < 0:
            yc_addendum = (
                f" 수익률 곡선은 {yc:+.2f}%로 역전 상태를 유지하고 있어 "
                "경기 침체 선행 경고가 유효하다."
            )
        elif yc < 0.3:
            yc_addendum = (
                f" 수익률 곡선은 {yc:+.2f}%로 평탄화 상태이며, "
                "경기 전환 국면에서의 주의가 요구된다."
            )

    return "\n\n".join(filter(None, [macro_sent, price_sent, sent_sent + yc_addendum]))


# ── Section 2: 주요 리스크 요인 ──────────────────────────────────────

def _risks(s: dict) -> list[tuple[str, str]]:
    """Return top-3 risk bullets as list of (title, description)."""
    risks: list[tuple[float, str, str]] = []

    vix       = s["vix"]
    yc        = s["yield_curve"]
    hy        = s["us_hy_spread"]
    bm        = s["breadth_ma200"]
    c30       = s["corr_30d"]
    c90       = s["corr_90d"]
    pr        = s["price_regime"]
    dxy       = s["dxy_trend"]
    dxy3m     = s["dxy_3m_chg"]
    fed_impl  = s["fed_implied"]
    real_rate = s["us_real_rate"]
    vix_dir   = s["vix_direction"]
    div       = s["regime_divergence"]
    chg       = s["regime_change"]
    us_r      = s["us_regime"]
    kr_r      = s["kr_regime"]
    dur       = s["regime_duration"]

    # ── VIX ──────────────────────────────────────────────────────
    if not _isnan(vix):
        if vix > 35:
            risks.append((3.0, "변동성 극단 구간",
                f"VIX {vix:.1f} — 공황에 준하는 변동성 수준. 유동성 리스크 및 "
                "강제 청산 압력에 주의. 포지션 축소 및 헤지 강화 필요."))
        elif vix > 25:
            trend = "상승 압력 지속" if not _isnan(vix_dir) and vix_dir < 0 else "단기 진정 가능성"
            risks.append((2.5, "변동성 상승 국면",
                f"VIX {vix:.1f} — 위험회피 임계치(25) 상회. {trend}. "
                "레짐 정상화 시까지 방어적 비중 유지."))
        elif vix > 20 and not _isnan(vix_dir) and vix_dir < 0:
            risks.append((1.5, "VIX 상승 추세",
                f"VIX {vix:.1f} — 아직 임계치(25) 미만이나 상승 추세 중. "
                "RiskOFF 레짐 전환 여부를 FOMC·지경학적 이벤트 전후 모니터링."))

    # ── Yield curve ───────────────────────────────────────────────
    if not _isnan(yc):
        if yc < -0.5:
            risks.append((2.5, "수익률 곡선 깊은 역전",
                f"10Y-2Y 스프레드 {yc:+.2f}% — 역사적으로 12~18개월 내 침체 선행. "
                "은행 대출 수익성 악화 및 신용 위축 경로 주시."))
        elif yc < 0:
            risks.append((2.0, "수익률 곡선 역전 지속",
                f"10Y-2Y 스프레드 {yc:+.2f}% — 경기 둔화 기대 반영. "
                "장기물 매수 심리 및 GDP 지표 추이 확인 필요."))
        elif yc < 0.3:
            risks.append((1.0, "수익률 곡선 평탄화",
                f"10Y-2Y 스프레드 {yc:+.2f}% — 역전까지 여유 제한. "
                "경제지표 추가 악화 시 역전 가속 위험."))

    # ── HY spread ─────────────────────────────────────────────────
    if not _isnan(hy):
        if hy > 600:
            risks.append((2.5, "하이일드 스프레드 급확대",
                f"HY 스프레드 {hy:.0f}bp — 크레딧 시장 스트레스 신호. "
                "디폴트 우려 증가 및 기업 자금조달 비용 급등. 주식 변동성 선행 지표."))
        elif hy > 400:
            risks.append((1.5, "하이일드 스프레드 확대",
                f"HY 스프레드 {hy:.0f}bp — 중간 수준 스트레스. "
                "레버리지 기업 선별 리스크 상승. 크레딧 사이클 점검 권고."))

    # ── Equity-bond correlation ───────────────────────────────────
    if not _isnan(c30) and c30 > 0.3:
        sev = 2.0 if c30 > 0.5 else 1.5
        risks.append((sev, "주식-채권 분산 효과 약화",
            f"S&P500↔TLT 30일 상관계수 {c30:+.3f} — 양(+) 상관관계로 "
            "전통적 60/40 포트폴리오의 방어력 저하. "
            "채권이 주식 하락 시 헤지 역할을 못할 수 있음."))

    # ── Correlation regime change ─────────────────────────────────
    if chg and not _isnan(c30) and not _isnan(c90):
        risks.append((1.5, "상관관계 레짐 전환 징후",
            f"주식-채권 30일({_f(c30, '+.3f')}) vs 90일({_f(c90, '+.3f')}) 부호 상이. "
            "구조적 레짐 변화 가능성. 대체 헤지 수단 재검토 필요."))

    # ── Market breadth ────────────────────────────────────────────
    if not _isnan(bm):
        if bm < 0.35:
            risks.append((2.5, "시장 폭 심각 약화",
                f"MA200 상회 비율 {bm:.0%} — 극소수 종목이 지수 지지. "
                "지수 하방 전환 시 낙폭 심화 위험."))
        elif bm < 0.4:
            risks.append((1.5, "시장 폭 약화",
                f"MA200 상회 비율 {bm:.0%} — RiskOFF 임계(40%) 근접. "
                "추가 하락 시 레짐 전환 가능."))

    # ── DXY strength ─────────────────────────────────────────────
    em_uw = "equity_em" in s["uw_assets"]
    if dxy == "Bullish" and not _isnan(dxy3m) and dxy3m > 0.03:
        sev = 1.5 if em_uw else 1.0
        em_note = "이머징 주식 비중축소 신호와 일치." if em_uw else "EM·원자재 익스포저 모니터링 필요."
        risks.append((sev, "강달러 압박",
            f"DXY 강세 추세 (3M: {dxy3m:+.1%}) — 신흥국 외채 부담 증가 및 "
            f"달러 표시 원자재 가격 하방 압력. {em_note}"))

    # ── FED implied rate ──────────────────────────────────────────
    if not _isnan(fed_impl) and fed_impl > 0.5:
        risks.append((1.0, "시장 금리 인상 기대 과도",
            f"2Y-Fed Rate 스프레드 {fed_impl:+.2f}% — 시장이 추가 인상 과잉 반영. "
            "기대 되돌림 시 금리 변동성 확대 가능."))

    # ── Real rate ─────────────────────────────────────────────────
    if not _isnan(real_rate) and real_rate > 2.5:
        risks.append((1.5, "실질금리 고점 부담",
            f"미국 실질금리 {real_rate:.2f}% — 역사적 고점 수준. "
            "성장주·기술주 밸류에이션 압박 지속. 금리 민감 섹터 선별 필요."))

    # ── US/KR divergence ──────────────────────────────────────────
    if div:
        risks.append((0.8, "미·한 경기 국면 불일치",
            f"미국({_MACRO_REGIME_KR.get(us_r, us_r)}) vs 한국({_MACRO_REGIME_KR.get(kr_r, kr_r)}). "
            "환율·무역 채널을 통한 한국 수출 기업 실적 불확실성."))

    risks.sort(key=lambda x: -x[0])
    return [(title, desc) for _, title, desc in risks[:3]]


# ── Section 3: 자산군별 투자 의견 ─────────────────────────────────────

def _asset_views(s: dict) -> list[tuple[str, str, str]]:
    """Return list of (group_name, OW/N/UW, rationale)."""
    ow = set(s["ow_assets"])
    uw = set(s["uw_assets"])

    yc        = s["yield_curve"]
    dxy       = s["dxy_trend"]
    dxy3m     = s["dxy_3m_chg"]
    vix       = s["vix"]
    bm        = s["breadth_ma200"]
    pr        = s["price_regime"]
    c30       = s["corr_30d"]
    us_r      = s["us_regime"]
    kr_r      = s["kr_regime"]
    div       = s["regime_divergence"]
    hy        = s["us_hy_spread"]
    real_rate = s["us_real_rate"]
    fed_impl  = s["fed_implied"]
    sent      = s["sentiment_score"]

    results = []

    # ── 글로벌 주식 ───────────────────────────────────────────────
    eq_codes = ["equity_us", "equity_dm", "equity_em", "equity_global"]
    eq_ow = [c for c in eq_codes if c in ow]
    eq_uw = [c for c in eq_codes if c in uw]

    if len(eq_ow) >= 2:
        view = "OW"
        if us_r in ("Goldilocks", "Reflation") and pr in ("RiskON", "Neutral"):
            rationale = (
                f"'{_MACRO_REGIME_KR.get(us_r, us_r)}' 매크로 + {pr} 레짐에서 "
                "모멘텀 주도 환경 유지. "
            )
            rationale += (
                "단, 강달러 환경에서 EM 내 선별적 접근 권고."
                if dxy == "Bullish" else
                f"브레드스({_pct(bm)}) 확인 시 추가 비중 확대 여지."
            )
        else:
            rationale = (
                f"단기 기술적 지지로 OW 신호이나, "
                f"'{_MACRO_REGIME_KR.get(us_r, us_r)}' 매크로 환경에서 리스크 관리 병행 필요."
            )
    elif len(eq_uw) >= 2:
        view = "UW"
        rationale = (
            f"'{_MACRO_REGIME_KR.get(us_r, us_r)}' 국면 + {pr} 레짐에서 주가 신호 약화. "
        )
        if not _isnan(vix) and vix > 25:
            rationale += f"VIX {vix:.1f} 고변동성 환경에서 비중 축소 유효."
        elif not _isnan(bm) and bm < 0.4:
            rationale += f"브레드스({_pct(bm)}) 약화로 지수 방어력 제한."
        else:
            rationale += "포지션 축소 또는 방어 섹터 로테이션 검토."
    else:
        view = "N"
        rationale = (
            f"매크로({_MACRO_REGIME_KR.get(us_r, us_r)})와 기술적 신호 혼재. "
        )
        rationale += (
            "명확한 방향성 확인 전 중립 유지, 모멘텀 고점 자산 선별."
            if pr == "Neutral" else
            "레짐 확인 후 전환 기회 탐색."
        )
    results.append(("글로벌 주식", view, rationale))

    # ── 미국 채권 ─────────────────────────────────────────────────
    bond_codes = ["ust_long", "ust_mid", "agg_bond"]
    bond_ow = [c for c in bond_codes if c in ow]
    bond_uw = [c for c in bond_codes if c in uw]

    if bond_ow:
        view = "OW"
        if not _isnan(yc) and yc < 0:
            rationale = f"역전 수익률 곡선({yc:+.2f}%)에서 장기물 보유 시 자본 차익 기대. "
        else:
            rationale = "가격 모멘텀 우세. "
        if pr == "RiskOFF":
            rationale += "RiskOFF 레짐의 안전자산 수요 지지."
        elif not _isnan(c30) and c30 < 0:
            rationale += f"주식-채권 음(−) 상관({c30:+.3f}) 유지, 분산 효과 작동 중."
        else:
            rationale += "금리 추가 하락 시 자본 차익 가능."
    elif bond_uw:
        view = "UW"
        parts = []
        if not _isnan(real_rate) and real_rate > 2.0:
            parts.append(f"실질금리 {real_rate:.2f}% 고점 부담")
        if not _isnan(fed_impl) and fed_impl > 0.25:
            parts.append(f"시장 금리 인상 기대({fed_impl:+.2f}%)로 채권 가격 하방 압력")
        rationale = ". ".join(parts) + ("." if parts else "") if parts else "듀레이션 리스크 대비 기대 수익 제한."
    else:
        view = "N"
        if not _isnan(yc) and -0.2 < yc < 0.3:
            rationale = (
                f"수익률 곡선 근 제로({yc:+.2f}%) — 장단기 금리 차 확대 여부 확인 후 포지션 결정. "
                "듀레이션 중립 유지."
            )
        else:
            rationale = "금리 방향성 불확실. 듀레이션 중립 유지."
    results.append(("미국 채권", view, rationale))

    # ── 크레딧 ────────────────────────────────────────────────────
    credit_codes = ["credit_hy", "credit_ig"]
    credit_ow = [c for c in credit_codes if c in ow]
    credit_uw = [c for c in credit_codes if c in uw]

    if credit_ow:
        view = "OW"
        rationale = "스프레드 축소 모멘텀 우세. "
        if not _isnan(hy) and hy < 300:
            rationale += f"HY 스프레드({hy:.0f}bp) 역사적 타이트 구간 진입, 추가 압축 여지 제한적."
        else:
            rationale += "금리 변동성 확대 시 스프레드 재확대 리스크 관리 병행."
    elif credit_uw:
        view = "UW"
        if not _isnan(hy) and hy > 500:
            rationale = f"HY 스프레드 {hy:.0f}bp 확대 — 크레딧 스트레스 신호. 투자등급 이하 회피."
        else:
            rationale = "크레딧 신호 약화. 투자등급 위주 방어적 접근."
    else:
        view = "N"
        if not _isnan(hy) and 350 < hy < 500:
            rationale = f"HY 스프레드 {hy:.0f}bp — 중간 구간. 매크로 방향에 연동 예상."
        else:
            rationale = "크레딧 모멘텀 중립. 매크로 확인 후 방향성 포지션 검토."
    results.append(("크레딧 (HY/IG)", view, rationale))

    # ── 금·원자재 ─────────────────────────────────────────────────
    alt_codes = ["gold", "commodity"]
    alt_ow = [c for c in alt_codes if c in ow]
    alt_uw = [c for c in alt_codes if c in uw]

    if alt_ow:
        view = "OW"
        if "gold" in alt_ow:
            rationale = "금 모멘텀 우세. "
            if pr == "RiskOFF":
                rationale += "RiskOFF 환경의 안전자산 수요 강화."
            elif not _isnan(real_rate) and real_rate < 1.0:
                rationale += f"실질금리({real_rate:.2f}%) 하락 국면의 금 가격 지지."
            else:
                rationale += "달러 방향성과의 역상관 유지 여부 확인 필요."
        else:
            rationale = "원자재 모멘텀 우세. "
            rationale += (
                "강달러 헤드윈드 — 에너지 중심 선별 접근."
                if dxy == "Bullish" else
                "글로벌 수요 회복 흐름에 연동 기대."
            )
    elif alt_uw:
        view = "UW"
        rationale = "원자재·금 모멘텀 약화. "
        if dxy == "Bullish" and not _isnan(dxy3m):
            rationale += f"강달러(3M: {dxy3m:+.1%}) 압박으로 달러 표시 원자재 가격 하방 압력."
        else:
            rationale += "수요 둔화 우려. 비중 축소 유효."
    else:
        view = "N"
        if not _isnan(real_rate) and real_rate > 2.0:
            rationale = f"실질금리 고점({real_rate:.2f}%)에서 금의 상대적 매력 제한. 원자재 방향성 중립."
        else:
            rationale = "달러·인플레이션 방향성 확인 후 포지션 결정."
    results.append(("금·원자재", view, rationale))

    # ── 달러 (DXY) ────────────────────────────────────────────────
    if "usd" in ow:
        view = "OW"
        rationale = "DXY 기술적 강세 추세 유지. "
        rationale += (
            "글로벌 위험 회피 시 안전통화 수요 강화."
            if pr == "RiskOFF" else
            "금리 차 우위 지속 구간에서 달러 강세 모멘텀 유효."
        )
    elif "usd" in uw:
        view = "UW"
        rationale = "DXY 추세 약화. 연준 금리 인하 기대 증대 또는 글로벌 성장 회복 시 달러 헤드윈드."
    else:
        view = "N"
        if dxy == "Bullish":
            rationale = (
                f"DXY 장기 추세 강세이나 가격 모멘텀 중립 구간. "
                f"3M 변화율({_f(dxy3m, '+.1%')}) 확인 필요."
            )
        else:
            rationale = "DXY 장기 약세 전환 신호 혼재. 방향성 확인 전 중립."
    results.append(("달러 (DXY)", view, rationale))

    # ── 한국 주식 ─────────────────────────────────────────────────
    kr_kr = _MACRO_REGIME_KR.get(kr_r, kr_r)
    if "equity_em" in ow or "equity_global" in ow:
        view = "OW"
        if div and kr_r in ("Deflation", "Stagflation"):
            rationale = (
                f"글로벌 기술적 신호 OW이나 한국 자체 '{kr_kr}' 국면 유의. "
                "수출 기업 중심 선별 접근 권고."
            )
        else:
            rationale = (
                f"'{kr_kr}' 국면 + 글로벌 위험선호 흐름에 연동. "
                "원·달러 환율 및 반도체 사이클 방향성 병행 확인."
            )
    elif "equity_em" in uw:
        view = "UW"
        rationale = (
            f"강달러 환경 및 '{kr_kr}' 국면에서 외국인 자금 이탈 압력. "
        )
        if dxy == "Bullish":
            rationale += "DXY 강세 유지 시 원화 약세·환차손 리스크 추가."
    else:
        view = "N"
        rationale = f"한국 '{kr_kr}' 국면 진행 중. "
        if div:
            rationale += f"미·한 국면 불일치({us_r} vs {kr_r}) — 한국 증시 방향성 탐색 필요. "
        rationale += "반도체·자동차 수출 지표 및 환율 흐름 병행 모니터링."
    results.append(("한국 주식", view, rationale))

    return results


# ── Section 4: 핵심 모니터링 지표 ─────────────────────────────────────

def _monitoring(s: dict) -> list[tuple[str, str]]:
    """Return 2-3 key monitoring items as list of (title, description)."""
    items: list[tuple[float, str, str]] = []

    vix       = s["vix"]
    vix_dir   = s["vix_direction"]
    yc        = s["yield_curve"]
    bm        = s["breadth_ma200"]
    c30       = s["corr_30d"]
    c90       = s["corr_90d"]
    pr        = s["price_regime"]
    us_r      = s["us_regime"]
    kr_r      = s["kr_regime"]
    div       = s["regime_divergence"]
    fed_impl  = s["fed_implied"]
    dur       = s["regime_duration"]
    since     = s["regime_since"]
    sent      = s["sentiment_score"]

    # ── VIX at critical threshold ──────────────────────────────────
    if not _isnan(vix):
        if 20 < vix < 30:
            items.append((3.0, "VIX 임계 구간 (15 / 25)",
                f"현재 {vix:.1f} — RiskON(15) · RiskOFF(25) 경계 근처. "
                "돌파 방향이 레짐 전환을 결정. FOMC·지경학적 이벤트 전후 집중 모니터링."))
        elif vix > 30:
            items.append((3.0, "VIX 고점 안정화 여부",
                f"현재 {vix:.1f} — 고변동성 국면. "
                "VIX 25 이하 복귀 시 RiskOFF 해제 신호로 해석 가능."))

    # ── Yield curve inflection ─────────────────────────────────────
    if not _isnan(yc) and -0.5 < yc < 0.2:
        items.append((2.5, "수익률 곡선 방향 전환 여부",
            f"현재 {yc:+.2f}% — 역전·평탄 구간. "
            "곡선 스팁 전환 시 경기 전망 개선 신호. GDP·고용 지표 연동 확인."))

    # ── Market breadth threshold ───────────────────────────────────
    if not _isnan(bm):
        if 0.35 < bm < 0.50:
            items.append((2.0, "시장 폭 (Breadth) 회복 여부",
                f"MA200 상회 비율 {bm:.0%} — RiskOFF 임계(40%) 근접 구간. "
                "50% 회복 시 랠리 신뢰도 제고, 하락 시 레짐 전환 경보."))
        elif 0.60 < bm < 0.72:
            items.append((1.5, "시장 폭 지속성 확인",
                f"MA200 상회 비율 {bm:.0%} — RiskON 기준(65%) 근접. "
                "유지 시 공격적 전략 강화 근거, 60% 하회 시 축소 신호."))

    # ── Equity-bond correlation regime ────────────────────────────
    if not _isnan(c30) and not _isnan(c90):
        if (c30 > 0 and c90 < 0) or (c30 < 0 and c90 > 0):
            items.append((2.0, "주식-채권 상관 레짐 전환",
                f"30일 {c30:+.3f} vs 90일 {c90:+.3f} — 부호 상이. "
                "구조적 전환인지 노이즈인지 2주 내 확인 필요. 포트폴리오 헤지 비용 재점검."))
        elif not _isnan(c30) and c30 > 0.4:
            items.append((1.5, "주식-채권 동조화 지속 여부",
                f"30일 상관 {c30:+.3f} — 채권의 헤지 기능 약화 중. "
                "60일 이상 지속 시 대체 헤지(금·현금·변동성 매수) 비중 검토."))

    # ── US/KR divergence ──────────────────────────────────────────
    if div:
        items.append((1.5, "미·한 경기 국면 수렴 여부",
            f"미국 {_MACRO_REGIME_KR.get(us_r, us_r)} vs 한국 {_MACRO_REGIME_KR.get(kr_r, kr_r)}. "
            "한국 GDP·수출 지표 및 KOSPI 상대 성과 모니터링. 환율 급변 시 통화정책 대응 속도 주목."))

    # ── FED implied rate ──────────────────────────────────────────
    if not _isnan(fed_impl) and abs(fed_impl) > 0.5:
        direction = "인상" if fed_impl > 0 else "인하"
        items.append((1.5, f"연준 금리 {direction} 기대 반영 동향",
            f"2Y-Fed Rate 스프레드 {fed_impl:+.2f}% — 추가 {direction} 반영 중. "
            "FOMC 회의록·CPI 발표가 기대치 재조정 촉발 가능. 금리 변동성 대비 필요."))

    # ── Long regime — reversal watch ──────────────────────────────
    if dur > 60:
        items.append((1.0, f"{pr} 레짐 장기 지속 후 반전 신호",
            f"{dur}일째 {pr} 레짐 지속 (since {since}). "
            "장기 유지 후 전환 징후(VIX 방향, 브레드스 변화, 국면 지표)에 조기 대응 준비."))

    items.sort(key=lambda x: -x[0])
    return [(title, desc) for _, title, desc in items[:3]]


# ── Full commentary assembly ──────────────────────────────────────────

def generate_commentary(s: dict) -> dict:
    """Generate rule-based commentary from signal summary."""
    return {
        "diagnosis":  _diagnosis(s),
        "risks":      _risks(s),
        "views":      _asset_views(s),
        "monitoring": _monitoring(s),
    }


# ── Public API ────────────────────────────────────────────────────────

def compute_regime_view(date: str) -> dict:
    """Gather all view data and generate rule-based commentary."""
    macro = compute_macro_view(date)
    price = compute_price_view(date)
    corr  = compute_correlation_view(date)

    signals    = _build_signals(macro, price, corr)
    commentary = generate_commentary(signals)

    return {
        "date":         date,
        "signals":      signals,
        "commentary":   commentary,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ── HTML generation ───────────────────────────────────────────────────

def _md(text: str) -> str:
    """Minimal markdown → HTML: **bold** only."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _view_colors(v: str) -> tuple[str, str]:
    if v == "OW":  return ("#ecfdf5", "#059669")
    if v == "UW":  return ("#fef2f2", "#dc2626")
    return ("#f3f4f6", "#6b7280")


def generate_regime_html(view: dict) -> str:  # noqa: C901
    report_date  = view["date"]
    generated_at = view["generated_at"]
    s   = view["signals"]
    com = view["commentary"]

    pr    = s["price_regime"]
    us_r  = s["us_regime"]
    kr_r  = s["kr_regime"]
    div   = s["regime_divergence"]
    sent  = s["sentiment_score"]
    sent_label = s["sentiment_label"]
    dur   = s["regime_duration"]
    since = s["regime_since"]

    # ── Price regime badge ────────────────────────────────────────
    rc = {
        "RiskON":  ("#ecfdf5", "#059669", "#05966933"),
        "RiskOFF": ("#fef2f2", "#dc2626", "#dc262633"),
        "Neutral": ("#fffbeb", "#d97706", "#d9770633"),
    }.get(pr, ("#f3f4f6", "#6b7280", "#6b728033"))
    dur_str = (
        f"&nbsp;<span style='font-size:11px;color:#7c8298'>({dur}d · {since})</span>"
        if dur > 0 and since != "—" else ""
    )
    regime_badge = (
        f'<span style="background:{rc[0]};color:{rc[1]};border:1px solid {rc[2]};'
        f'padding:4px 14px;border-radius:8px;font-size:14px;font-weight:700">'
        f'{pr}</span>{dur_str}'
    )
    macro_badges = (
        f'<span style="font-size:13px;font-weight:600;color:#2d3148">'
        f'🇺🇸 {_MACRO_REGIME_KR.get(us_r, us_r)}</span>'
        f'<span style="color:#7c8298;margin:0 8px">/</span>'
        f'<span style="font-size:13px;font-weight:600;color:#2d3148">'
        f'🇰🇷 {_MACRO_REGIME_KR.get(kr_r, kr_r)}</span>'
    )
    div_badge = (
        '<span style="background:#fff8e6;color:#92400e;border:1px solid #f59e0b;'
        'padding:3px 10px;border-radius:6px;font-size:12px;font-weight:600">'
        '⚠️ US/KR 국면 불일치</span>'
        if div else ""
    )

    # ── OW/UW chips ───────────────────────────────────────────────
    def _chips(codes, bg, fg):
        if not codes:
            return '<span style="font-size:12px;color:#7c8298">없음</span>'
        return "".join(
            f'<span style="background:{bg};color:{fg};border:1px solid {fg}33;'
            f'padding:3px 10px;border-radius:6px;font-size:12px;font-weight:600;margin:2px">'
            f'{AC_LABELS.get(c, c)}</span>'
            for c in codes
        )

    ow_chips = _chips(s["ow_assets"], "#ecfdf5", "#059669")
    uw_chips = _chips(s["uw_assets"], "#fef2f2", "#dc2626")

    # ── Mini signal cards ─────────────────────────────────────────
    def _mini_card(title, rows):
        inner = "".join(
            f'<div style="display:flex;justify-content:space-between;margin-bottom:5px">'
            f'<span style="font-size:12px;color:#7c8298">{lbl}</span>'
            f'<span style="font-size:12px;font-weight:600;'
            f'font-family:\'JetBrains Mono\',monospace;color:#1a1d2e">{val}</span>'
            f'</div>'
            for lbl, val in rows
        )
        return (
            f'<div style="background:#fff;border:1px solid #e0e3ed;'
            f'border-radius:12px;padding:16px 18px">'
            f'<div style="font-size:11px;font-weight:700;color:#7c8298;'
            f'text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">{title}</div>'
            f'{inner}</div>'
        )

    yc  = s["yield_curve"]
    c30 = s["corr_30d"]
    c60 = s["corr_60d"]
    c90 = s["corr_90d"]

    macro_card = _mini_card("🌍 매크로", [
        ("US 국면",    us_r),
        ("KR 국면",    kr_r),
        ("US CPI YoY", f"{_f(s['us_cpi_yoy'])}%"),
        ("US GDP QoQ", f"{_f(s['us_gdp_qoq'])}%"),
        ("Yield Curve", f"{yc:+.2f}%" if not _isnan(yc) else "N/A"),
        ("HY Spread",   f"{_f(s['us_hy_spread'], '.0f')}bp"),
    ])
    price_card = _mini_card("📊 가격 신호", [
        ("Regime",        pr),
        ("VIX",           _f(s["vix"], ".1f")),
        ("Breadth MA200", _pct(s["breadth_ma200"])),
        ("Sentiment",     f"{sent:+d} ({sent_label})"),
        ("DXY",           s["dxy_trend"]),
    ])
    corr_card = _mini_card("🔗 상관관계", [
        ("S&P500 vs TLT 30d", f"{c30:+.3f}" if not _isnan(c30) else "N/A"),
        ("S&P500 vs TLT 60d", f"{c60:+.3f}" if not _isnan(c60) else "N/A"),
        ("S&P500 vs TLT 90d", f"{c90:+.3f}" if not _isnan(c90) else "N/A"),
        ("분산 효과", "작동 중" if not _isnan(c30) and c30 < 0 else "약화"),
    ])

    # ── Section HTMLs ─────────────────────────────────────────────

    # 1. Diagnosis
    diagnosis_html = "".join(
        f'<p style="margin-bottom:12px">{_md(p)}</p>'
        for p in com["diagnosis"].split("\n\n") if p.strip()
    )

    # 2. Risks
    risk_html = ""
    for title, desc in com["risks"]:
        risk_html += (
            f'<div style="display:flex;gap:12px;margin-bottom:16px;align-items:flex-start">'
            f'<div style="flex-shrink:0;margin-top:6px;width:7px;height:7px;'
            f'background:#d9304f;border-radius:50%"></div>'
            f'<div>'
            f'<div style="font-size:13px;font-weight:700;color:#1a1d2e;margin-bottom:3px">{title}</div>'
            f'<div style="font-size:13px;color:#4b5563;line-height:1.7">{_md(desc)}</div>'
            f'</div></div>'
        )
    if not risk_html:
        risk_html = '<p style="font-size:13px;color:#7c8298">주요 리스크 신호 없음</p>'

    # 3. Asset views
    view_rows = ""
    for group, v, rationale in com["views"]:
        bg, fg = _view_colors(v)
        badge = (
            f'<span style="background:{bg};color:{fg};padding:2px 10px;'
            f'border-radius:4px;font-size:12px;font-weight:700">{v}</span>'
        )
        view_rows += (
            f'<tr>'
            f'<td style="padding:10px 12px;font-size:13px;font-weight:600;'
            f'white-space:nowrap;border-bottom:1px solid #f1f5f9">{group}</td>'
            f'<td style="padding:10px 12px;text-align:center;'
            f'border-bottom:1px solid #f1f5f9">{badge}</td>'
            f'<td style="padding:10px 12px;font-size:13px;color:#4b5563;'
            f'line-height:1.65;border-bottom:1px solid #f1f5f9">{_md(rationale)}</td>'
            f'</tr>'
        )

    # 4. Monitoring
    monitor_html = ""
    for i, (title, desc) in enumerate(com["monitoring"], 1):
        monitor_html += (
            f'<div style="display:flex;gap:14px;margin-bottom:16px;align-items:flex-start">'
            f'<div style="flex-shrink:0;width:24px;height:24px;background:#3b6ee6;color:#fff;'
            f'border-radius:50%;display:flex;align-items:center;justify-content:center;'
            f'font-size:12px;font-weight:700;margin-top:1px">{i}</div>'
            f'<div>'
            f'<div style="font-size:13px;font-weight:700;color:#1a1d2e;margin-bottom:3px">{title}</div>'
            f'<div style="font-size:13px;color:#4b5563;line-height:1.7">{_md(desc)}</div>'
            f'</div></div>'
        )
    if not monitor_html:
        monitor_html = '<p style="font-size:13px;color:#7c8298">특이 신호 없음</p>'

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Regime View | {report_date}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --border:#e0e3ed;
  --text:#2d3148; --muted:#7c8298; --primary:#3b6ee6;
}}
* {{ margin:0; padding:0; box-sizing:border-box }}
body {{
  font-family:'Noto Sans KR',-apple-system,sans-serif;
  background:var(--bg); color:var(--text);
  line-height:1.75; padding:28px 24px;
  max-width:1200px; margin:0 auto;
}}
strong {{ font-weight:600 }}
.back-link {{
  display:inline-block; margin-bottom:20px;
  font-size:13px; color:var(--primary); text-decoration:none;
}}
.back-link:hover {{ text-decoration:underline }}
.page-header {{
  display:flex; justify-content:space-between; align-items:flex-end;
  margin-bottom:24px; padding-bottom:18px; border-bottom:2px solid var(--border);
}}
.page-header h1 {{ font-size:24px; font-weight:700; color:#1a1d2e }}
.page-header .sub {{ font-size:12px; color:var(--muted); margin-top:3px }}
.card {{
  background:var(--card); border:1px solid var(--border);
  border-radius:14px; padding:24px 26px; margin-bottom:20px;
  box-shadow:0 1px 4px rgba(0,0,0,.05);
}}
.card-title {{
  font-size:16px; font-weight:700; color:#1a1d2e;
  margin-bottom:18px; padding-bottom:10px; border-bottom:1px solid var(--border);
}}
.signals-grid {{
  display:grid; grid-template-columns:repeat(3,1fr);
  gap:16px; margin-bottom:20px;
}}
.inner-table {{ width:100%; border-collapse:collapse; font-size:13px }}
.inner-table thead tr {{ background:#f8fafc; border-bottom:1px solid var(--border) }}
.inner-table th {{
  padding:8px 12px; font-size:12px; color:var(--muted);
  font-weight:600; text-align:left;
}}
.inner-table tbody tr:hover {{ background:#f8fafc }}
.footer {{
  text-align:center; font-size:11px; color:#94a3b8;
  padding:16px 0 4px; margin-top:8px; border-top:1px solid var(--border);
}}
@media(max-width:900px) {{ .signals-grid {{ grid-template-columns:1fr }} }}
</style>
</head>
<body>

<a class="back-link" href="../../index.html">← Back to Index</a>

<div class="page-header">
  <div>
    <h1>Regime View</h1>
    <div class="sub">종합 시장 국면 분석 + 규칙 기반 투자 해설 | View Agent</div>
  </div>
  <div style="text-align:right;font-size:11px;color:var(--muted)">
    <div style="font-size:13px;font-weight:600;color:#1a1d2e;margin-bottom:3px">As of {report_date}</div>
    <div>Generated: {generated_at}</div>
  </div>
</div>

<!-- Regime row -->
<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:20px">
  {regime_badge}
  {macro_badges}
  {div_badge}
</div>

<!-- OW/UW strip -->
<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;
            padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;
            gap:16px;flex-wrap:wrap">
  <span style="font-size:12px;font-weight:700;color:var(--muted);min-width:80px">OW (비중확대)</span>
  <div>{ow_chips}</div>
  <span style="font-size:12px;font-weight:700;color:var(--muted);margin-left:16px;min-width:80px">UW (비중축소)</span>
  <div>{uw_chips}</div>
</div>

<!-- Signal cards -->
<div class="signals-grid">
  {macro_card}
  {price_card}
  {corr_card}
</div>

<!-- 1. 현재 국면 진단 -->
<div class="card">
  <div class="card-title">1. 현재 시장 국면 진단</div>
  <div style="font-size:14px;color:#2d3148;line-height:1.9">
    {diagnosis_html}
  </div>
</div>

<!-- 2. 주요 리스크 -->
<div class="card">
  <div class="card-title">2. 주요 리스크 요인</div>
  {risk_html}
</div>

<!-- 3. 자산군별 투자 의견 -->
<div class="card">
  <div class="card-title">3. 자산군별 투자 의견</div>
  <div style="overflow-x:auto">
    <table class="inner-table">
      <thead><tr>
        <th style="min-width:120px">자산군</th>
        <th style="text-align:center;min-width:70px">의견</th>
        <th>근거</th>
      </tr></thead>
      <tbody>{view_rows}</tbody>
    </table>
  </div>
</div>

<!-- 4. 핵심 모니터링 -->
<div class="card">
  <div class="card-title">4. 핵심 모니터링 지표</div>
  {monitor_html}
</div>

<div class="footer">
  Regime View | macro_view + price_view + correlation_view 종합 | View Agent
</div>

</body>
</html>'''


# ── Report entry point ────────────────────────────────────────────────

def generate_report(date: str) -> str:
    """Compute regime view and save HTML to OUTPUT_DIR."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    view     = compute_regime_view(date)
    html     = generate_regime_html(view)
    out_path = OUTPUT_DIR / f"{date}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return str(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regime view — rule-based synthesis of all three views"
    )
    parser.add_argument("--date", required=True, help="Report date (YYYY-MM-DD)")
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    args = parser.parse_args()

    if args.html:
        path = generate_report(args.date)
        print(f"HTML report: {path}")
        return

    view = compute_regime_view(args.date)
    s    = view["signals"]
    com  = view["commentary"]

    print(f"\n{'='*70}")
    print(f"  Regime View as of {view['date']}")
    print(f"{'='*70}")
    print(f"  US Regime  : {s['us_regime']}")
    print(f"  KR Regime  : {s['kr_regime']}")
    print(f"  Price      : {s['price_regime']}")
    print(f"  Sentiment  : {s['sentiment_score']:+d} ({s['sentiment_label']})")
    print(f"\n--- 현재 국면 진단 ---\n{com['diagnosis']}")
    print(f"\n--- 주요 리스크 ---")
    for title, desc in com["risks"]:
        print(f"  • {title}")
        print(f"    {desc[:100]}...")
    print(f"\n--- 자산군 의견 ---")
    for group, v, _ in com["views"]:
        print(f"  {group:<16s}  {v}")
    print(f"\n--- 핵심 모니터링 ---")
    for title, _ in com["monitoring"]:
        print(f"  → {title}")
    print()


if __name__ == "__main__":
    main()