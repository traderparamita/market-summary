"""Allocation View — 변액보험 펀드 배분 의견 (Phase 2 종착점).

Phase 1 진단(regime) + Phase 2 드릴다운(country/sector/bond/style) 신호를
통합해 변액보험 펀드 유형별 추천 비중을 제안한다.

- KR 투자자 관점: KRW 기준, K-ICS 주식한도(30%) 인식, ALM 듀레이션
- US 투자자 관점: USD 기준 글로벌 배분 (참고용)
- 환헤지 권고: USDKRW 트렌드 + KR-US 금리차 기반

Usage:
    python -m portfolio.view.allocation_view --date 2026-04-14 --html
"""

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "allocation"
MARKET_CSV = ROOT / "history" / "market_data.csv"
MACRO_CSV  = ROOT / "history" / "macro_indicators.csv"

# ── 변액보험 펀드 카테고리 정의 ───────────────────────────────────────────

FUND_CATEGORIES = [
    {"id": "kr_eq",        "name": "국내주식형",          "group": "equity",  "kr_only": True},
    {"id": "us_eq",        "name": "해외주식형(미국)",     "group": "equity",  "kr_only": False},
    {"id": "global_eq",    "name": "해외주식형(글로벌)",   "group": "equity",  "kr_only": False},
    {"id": "em_eq",        "name": "해외주식형(신흥국)",   "group": "equity",  "kr_only": False},
    {"id": "sector_eq",    "name": "해외주식형(섹터·테마)","group": "equity",  "kr_only": False},
    {"id": "kr_bond",      "name": "국내채권형",          "group": "bond",    "kr_only": True},
    {"id": "us_bond",      "name": "해외채권형(미국·선진)","group": "bond",    "kr_only": False},
    {"id": "mixed",        "name": "혼합형(주식+채권)",   "group": "mixed",   "kr_only": False},
    {"id": "alternative",  "name": "대안(금·원자재·부동산)","group": "alts",  "kr_only": False},
    {"id": "cash",         "name": "현금성(MMF·CD)",      "group": "cash",    "kr_only": True},
]

# ── Base allocation templates by regime ──────────────────────────────────
# KR 변액보험 기준 (K-ICS 주식한도 약 30% 고려한 보수적 기준)

BASE_ALLOC = {
    "Goldilocks": {
        "kr_eq": 10, "us_eq": 12, "global_eq": 8, "em_eq": 5, "sector_eq": 5,
        "kr_bond": 20, "us_bond": 15, "mixed": 10, "alternative": 5, "cash": 10,
    },
    "Reflation": {
        "kr_eq": 8, "us_eq": 10, "global_eq": 7, "em_eq": 5, "sector_eq": 5,
        "kr_bond": 18, "us_bond": 15, "mixed": 12, "alternative": 10, "cash": 10,
    },
    "Stagflation": {
        "kr_eq": 5, "us_eq": 5, "global_eq": 5, "em_eq": 3, "sector_eq": 2,
        "kr_bond": 22, "us_bond": 18, "mixed": 15, "alternative": 15, "cash": 10,
    },
    "Deflation": {
        "kr_eq": 5, "us_eq": 5, "global_eq": 5, "em_eq": 2, "sector_eq": 2,
        "kr_bond": 28, "us_bond": 22, "mixed": 12, "alternative": 5, "cash": 14,
    },
    "N/A": {
        "kr_eq": 7, "us_eq": 8, "global_eq": 7, "em_eq": 4, "sector_eq": 4,
        "kr_bond": 22, "us_bond": 18, "mixed": 12, "alternative": 8, "cash": 10,
    },
}

# US investor reference allocation (unconstrained, 60/40 style)
BASE_ALLOC_US = {
    "Goldilocks": {
        "us_eq": 40, "intl_eq": 20, "em_eq": 10,
        "us_bond": 15, "em_bond": 5, "alts": 5, "cash": 5,
    },
    "Reflation": {
        "us_eq": 30, "intl_eq": 18, "em_eq": 10,
        "us_bond": 15, "em_bond": 7, "alts": 12, "cash": 8,
    },
    "Stagflation": {
        "us_eq": 20, "intl_eq": 10, "em_eq": 5,
        "us_bond": 22, "em_bond": 8, "alts": 20, "cash": 15,
    },
    "Deflation": {
        "us_eq": 20, "intl_eq": 10, "em_eq": 5,
        "us_bond": 38, "em_bond": 7, "alts": 5, "cash": 15,
    },
    "N/A": {
        "us_eq": 28, "intl_eq": 15, "em_eq": 7,
        "us_bond": 25, "em_bond": 6, "alts": 9, "cash": 10,
    },
}

K_ICS_EQUITY_LIMIT = 30  # %


# ── Data loaders ──────────────────────────────────────────────────────────

def _load_prices(date: str) -> pd.DataFrame:
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    return wide[wide.index <= pd.Timestamp(date)].sort_index()


def _get_macro_regime(date: str) -> str:
    if not MACRO_CSV.exists():
        return "N/A"
    df = pd.read_csv(MACRO_CSV, parse_dates=["DATE"])
    df = df[df["DATE"] <= pd.Timestamp(date)]

    def _v(code):
        sub = df[df["INDICATOR_CODE"] == code]
        return float(sub.sort_values("DATE").iloc[-1]["VALUE"]) if not sub.empty else np.nan

    gdp = _v("US_GDP_QOQ")
    cpi = _v("US_CPI_YOY")
    if np.isnan(gdp) or np.isnan(cpi):
        return "N/A"
    g = gdp > 0
    i = cpi > 3.0
    if g and not i:   return "Goldilocks"
    if g and i:       return "Reflation"
    if not g and i:   return "Stagflation"
    return "Deflation"


def _get_country_signals(date: str) -> dict:
    """country_view에서 국가별 OW/N/UW 가져오기."""
    try:
        from portfolio.view.country_view import compute_country_view
        data = compute_country_view(_parse_date(date))
        return {c["code"]: c["view"] for c in data["countries"]}
    except Exception:
        return {}


def _get_bond_signals(date: str) -> dict:
    """bond_view에서 듀레이션/크레딧 신호 가져오기."""
    try:
        from portfolio.view.bond_view import compute_bond_view
        data = compute_bond_view(_parse_date(date))
        return {
            "dur_bias":     data["duration_rec"]["bias"],
            "credit_regime": data["credit_regime"],
            "kr_us_diff":   data["kr_us_diff"]["diff"],
            "hy_spread":    data["rates"]["hy_spread"],
        }
    except Exception:
        return {}


def _get_style_signals(date: str) -> dict:
    """style_view에서 팩터 선호 가져오기."""
    try:
        from portfolio.view.style_view import compute_style_view
        data = compute_style_view(_parse_date(date))
        return {
            "regime":       data["regime"],
            "vix_regime":   data["vix_regime"],
            "rate_dir":     data["rate_direction"],
            "top_style":    data["us_styles"][0]["name"] if data["us_styles"] else "",
        }
    except Exception:
        return {}


def _get_sector_signals(date: str) -> list:
    """sector_view에서 상위 US 섹터 가져오기."""
    try:
        from portfolio.view.sector_view import compute_sector_view
        data = compute_sector_view(_parse_date(date))
        tops = [s["name"] for s in data["us_sectors"][:3] if s.get("view") == "OW"]
        return tops
    except Exception:
        return []


def _get_krw_signal(date: str) -> dict:
    """USDKRW 추세 기반 환헤지 권고."""
    df = pd.read_csv(MARKET_CSV, parse_dates=["DATE"])
    df = df[df["INDICATOR_CODE"] == "FX_USDKRW"][["DATE", "CLOSE"]].dropna()
    df = df[df["DATE"] <= pd.Timestamp(date)].sort_values("DATE")
    if len(df) < 60:
        return {"trend": "N/A", "hedge_rec": "중립", "color": "#f39c12"}
    px = df.set_index("DATE")["CLOSE"]
    last = float(px.iloc[-1])
    ma60 = float(px.tail(60).mean())
    target_3m = px.index[-1] - pd.DateOffset(months=3)
    past_3m = px[px.index <= target_3m]
    chg_3m = float(px.iloc[-1] / past_3m.iloc[-1] - 1) * 100 if not past_3m.empty else np.nan

    if last > ma60 and (np.isnan(chg_3m) or chg_3m > 1):
        trend = "원화 약세 (달러 강세)"
        hedge_rec = "환헤지 권고 — 해외자산 FX 손실 위험"
        color = "#e74c3c"
    elif last < ma60 and (np.isnan(chg_3m) or chg_3m < -1):
        trend = "원화 강세 (달러 약세)"
        hedge_rec = "환노출 가능 — 해외자산 FX 이득 기대"
        color = "#27ae60"
    else:
        trend = "원화 중립"
        hedge_rec = "부분 환헤지 (50%) 권고"
        color = "#f39c12"
    return {"trend": trend, "hedge_rec": hedge_rec, "color": color,
            "last": round(last, 0), "chg_3m": round(chg_3m, 1) if not np.isnan(chg_3m) else None}


def _parse_date(date):
    if hasattr(date, "year"):
        return date
    return datetime.strptime(str(date), "%Y-%m-%d").date()


# ── Fund category → price proxy mapping ──────────────────────────────────

CATEGORY_PROXIES = {
    "kr_eq":       "EQ_KOSPI",
    "us_eq":       "EQ_SP500",
    "global_eq":   "EQ_MSCI_ACWI",
    "em_eq":       "EQ_MSCI_LATAM",
    "sector_eq":   "EQ_NASDAQ",
    "us_bond":     "BD_TLT",
    "kr_bond":     "BD_TLT",    # TLT as proxy (ECOS rate data can't be used for returns)
    "mixed":       "EQ_SP500",  # simplified: SP500 proxy
    "alternative": "CM_GOLD",
    "cash":        None,        # near-zero: handled separately
}

# Approximate global market-cap weights for BL equilibrium
MARKET_CAP_WEIGHTS = {
    "kr_eq": 0.02, "us_eq": 0.28, "global_eq": 0.18, "em_eq": 0.06,
    "sector_eq": 0.05, "kr_bond": 0.04, "us_bond": 0.18,
    "mixed": 0.08, "alternative": 0.05, "cash": 0.06,
}

CATEGORY_IDS = [c["id"] for c in FUND_CATEGORIES]


def _get_proxy_returns(prices: pd.DataFrame, lookback: int = 756) -> pd.DataFrame:
    """펀드 카테고리별 로그 수익률 행렬 (lookback 거래일).

    cash는 0으로 채움. 데이터 없는 카테고리는 NaN → 후처리.
    """
    series = {}
    for cid in CATEGORY_IDS:
        proxy = CATEGORY_PROXIES.get(cid)
        if proxy is None or proxy not in prices.columns:
            series[cid] = pd.Series(0.0, index=prices.index[-lookback:])
            continue
        px = prices[proxy].dropna()
        if len(px) < 30:
            series[cid] = pd.Series(0.0, index=prices.index[-lookback:])
            continue
        log_ret = np.log(px / px.shift(1)).dropna()
        series[cid] = log_ret.iloc[-lookback:]

    df = pd.DataFrame(series).dropna()
    return df


def _black_litterman(
    sigma: np.ndarray,
    implied_mu: np.ndarray,
    views: list,          # list of {"p": np.ndarray (n,), "q": float, "conf": float}
    tau: float = 0.05,
) -> np.ndarray:
    """Black-Litterman 포스테리어 기대수익률.

    P (k×n), Q (k,), Omega = diag(conf^-1 * p @ tau*Σ @ p')
    μ_BL = [(τΣ)^-1 + P'Ω^-1P]^-1 × [(τΣ)^-1μ_eq + P'Ω^-1Q]
    """
    n = len(implied_mu)
    if not views:
        return implied_mu.copy()

    P = np.array([v["p"] for v in views])           # (k, n)
    Q = np.array([v["q"] for v in views])            # (k,)
    confs = np.array([v.get("conf", 0.5) for v in views])

    # Omega: confidence-scaled uncertainty
    tau_sigma = tau * sigma
    omega_diag = np.array([
        (1 - c) / c * float(P[i] @ tau_sigma @ P[i])
        for i, c in enumerate(confs)
    ])
    omega_diag = np.maximum(omega_diag, 1e-8)
    Omega = np.diag(omega_diag)

    try:
        import scipy.linalg as la
        tS_inv = la.inv(tau_sigma + 1e-6 * np.eye(n))
        O_inv  = la.inv(Omega)
        M      = la.inv(tS_inv + P.T @ O_inv @ P)
        mu_bl  = M @ (tS_inv @ implied_mu + P.T @ O_inv @ Q)
    except Exception:
        mu_bl = implied_mu.copy()

    return mu_bl


def _risk_parity_weights(
    sigma: np.ndarray,
    n: int,
    eq_indices: list[int],
    eq_limit: float = 0.30,
    min_w: float = 0.01,
) -> np.ndarray:
    """리스크 패리티 (동일 위험기여) 최적화.

    목적함수: Σ_i(w_i*(Σw)_i - 1/n)^2  (equal risk contribution)
    제약: Σw = 1, w >= min_w, Σ equity weights <= eq_limit
    """
    try:
        from scipy.optimize import minimize

        budget = 1.0 / n

        def objective(w):
            Sw = sigma @ w
            rc = w * Sw
            total_rc = rc.sum()
            if total_rc <= 0:
                return 1e6
            rc_norm = rc / total_rc
            return float(np.sum((rc_norm - budget) ** 2))

        def jac(w):
            eps = 1e-6
            grad = np.zeros(n)
            f0 = objective(w)
            for i in range(n):
                w2 = w.copy(); w2[i] += eps
                grad[i] = (objective(w2) - f0) / eps
            return grad

        w0 = np.ones(n) / n
        bounds = [(min_w, 1.0)] * n
        constraints = [
            {"type": "eq",  "fun": lambda w: w.sum() - 1.0},
            {"type": "ineq","fun": lambda w: eq_limit - sum(w[i] for i in eq_indices)},
        ]
        result = minimize(objective, w0, jac=jac, method="SLSQP",
                          bounds=bounds, constraints=constraints,
                          options={"maxiter": 300, "ftol": 1e-9})
        if result.success:
            w = result.x
            w = np.maximum(w, min_w)
            w = w / w.sum()
            return w
    except Exception:
        pass
    # Fallback: equal weight
    return np.ones(n) / n


def _expected_return_ensemble(
    proxy_returns: pd.DataFrame,
    implied_mu: np.ndarray,
    regime: str,
) -> dict:
    """기대수익률 앙상블: BL 균형 + 역사적(1Y/3Y) + 매크로 조정.

    Returns:
        dict: {category: {"bl": float, "hist_1y": float, "hist_3y": float,
                           "macro_adj": float, "ensemble": float}}
    """
    result = {}
    n = len(CATEGORY_IDS)

    # Macro adjustment factors by regime (annualized premium vs equilibrium)
    macro_adj_map = {
        "Goldilocks":  {"equity": +0.02, "bond": +0.005, "alts": 0, "cash": 0},
        "Reflation":   {"equity": +0.01, "bond": -0.01,  "alts": +0.03, "cash": 0},
        "Stagflation": {"equity": -0.02, "bond": -0.005, "alts": +0.02, "cash": +0.01},
        "Deflation":   {"equity": -0.03, "bond": +0.02,  "alts": -0.01, "cash": +0.01},
        "N/A":         {"equity": 0,     "bond": 0,      "alts": 0,     "cash": 0},
    }
    adj = macro_adj_map.get(regime, macro_adj_map["N/A"])

    group_map = {c["id"]: c["group"] for c in FUND_CATEGORIES}

    for i, cid in enumerate(CATEGORY_IDS):
        bl_val   = float(implied_mu[i]) * 252 if i < len(implied_mu) else 0.0

        # Historical returns
        if cid in proxy_returns.columns and len(proxy_returns[cid]) >= 21:
            hist_1y = float(proxy_returns[cid].iloc[-252:].sum())  if len(proxy_returns[cid]) >= 252 else np.nan
            hist_3y = float(proxy_returns[cid].iloc[-756:].sum() / 3) if len(proxy_returns[cid]) >= 756 else np.nan
        else:
            hist_1y = hist_3y = np.nan

        # Macro adjustment
        grp = group_map.get(cid, "cash")
        macro_grp = "equity" if grp == "equity" else ("bond" if grp == "bond" else ("alts" if grp == "alts" else "cash"))
        m_adj = adj.get(macro_grp, 0)

        # Ensemble: 40% BL + 30% hist_3y + 30% macro_adj
        hist_for_ens = hist_3y if not np.isnan(hist_3y) else bl_val
        ensemble = round(0.40 * bl_val + 0.30 * hist_for_ens + 0.30 * (bl_val + m_adj), 4)

        result[cid] = {
            "bl":        round(bl_val, 4),
            "hist_1y":   round(hist_1y, 4) if not np.isnan(hist_1y) else np.nan,
            "hist_3y":   round(hist_3y, 4) if not np.isnan(hist_3y) else np.nan,
            "macro_adj": round(m_adj, 4),
            "ensemble":  ensemble,
        }

    return result


def _build_bl_views(country_sig: dict, bond_sig: dict, style_sig: dict,
                    n: int) -> list:
    """신호 → BL views 변환.

    각 view: {"p": np.ndarray (n,), "q": float, "conf": float}
    """
    idx = {cid: i for i, cid in enumerate(CATEGORY_IDS)}
    views = []

    def _p(long_cat, short_cat=None):
        p = np.zeros(n)
        if long_cat in idx:  p[idx[long_cat]] = +1.0
        if short_cat and short_cat in idx: p[idx[short_cat]] = -1.0
        return p

    # US OW → US equity > global equity by ~2%
    if country_sig.get("US") == "OW":
        views.append({"p": _p("us_eq", "global_eq"), "q": 0.02, "conf": 0.6})
    elif country_sig.get("US") == "UW":
        views.append({"p": _p("global_eq", "us_eq"), "q": 0.015, "conf": 0.5})

    # KR OW/UW
    if country_sig.get("KR") == "OW":
        views.append({"p": _p("kr_eq", "global_eq"), "q": 0.015, "conf": 0.5})
    elif country_sig.get("KR") == "UW":
        views.append({"p": _p("kr_bond", "kr_eq"), "q": 0.01, "conf": 0.5})

    # EM OW
    em_ow = any(country_sig.get(c) == "OW" for c in ["IN", "CN", "EM"])
    if em_ow:
        views.append({"p": _p("em_eq", "us_bond"), "q": 0.025, "conf": 0.45})

    # Duration bias
    dur = bond_sig.get("dur_bias", "neutral")
    if dur == "long":
        views.append({"p": _p("us_bond", "cash"), "q": 0.015, "conf": 0.6})
    elif dur == "short":
        views.append({"p": _p("cash", "us_bond"), "q": 0.01, "conf": 0.55})

    # VIX regime
    if style_sig.get("vix_regime") == "high":
        views.append({"p": _p("alternative", "sector_eq"), "q": 0.02, "conf": 0.5})
    elif style_sig.get("vix_regime") == "low":
        views.append({"p": _p("us_eq", "alternative"), "q": 0.02, "conf": 0.5})

    return views


# ── Allocation logic ──────────────────────────────────────────────────────

def _adjust_alloc(base: dict, country_sig: dict, bond_sig: dict,
                  style_sig: dict, krw_sig: dict) -> dict:
    """신호 기반 기준 배분 조정 (±3~5% 틸트)."""
    alloc = dict(base)

    # 1) Country signals → 지역별 주식 비중 조정
    us_view = country_sig.get("US", "N")
    kr_view = country_sig.get("KR", "N")
    em_view = country_sig.get("IN", "N")  # 신흥국 대표로 인도 사용

    if us_view == "OW":
        alloc["us_eq"]     = min(alloc["us_eq"] + 3, 15)
    elif us_view == "UW":
        alloc["us_eq"]     = max(alloc["us_eq"] - 3, 2)

    if kr_view == "OW":
        alloc["kr_eq"]     = min(alloc["kr_eq"] + 2, 12)
    elif kr_view == "UW":
        alloc["kr_eq"]     = max(alloc["kr_eq"] - 2, 2)

    em_ow = any(v == "OW" for k, v in country_sig.items() if k in ("IN", "CN", "EM"))
    if em_ow:
        alloc["em_eq"]     = min(alloc["em_eq"] + 2, 8)

    # 2) Bond signals → 채권 비중 조정
    dur_bias = bond_sig.get("dur_bias", "neutral")
    hy_spread = bond_sig.get("hy_spread", np.nan)

    if dur_bias == "long":
        alloc["kr_bond"] = min(alloc["kr_bond"] + 3, 32)
        alloc["us_bond"] = min(alloc["us_bond"] + 2, 22)
    elif dur_bias == "short":
        alloc["kr_bond"] = max(alloc["kr_bond"] - 2, 10)
        alloc["cash"]    = min(alloc["cash"]    + 3, 18)

    if not np.isnan(hy_spread) if isinstance(hy_spread, float) else True:
        try:
            if float(hy_spread) > 500:  # HY 위기
                alloc["us_bond"] = max(alloc["us_bond"] - 3, 8)
                alloc["cash"]    = min(alloc["cash"] + 3, 20)
        except (ValueError, TypeError):
            pass

    # 3) Style signals → 미국 주식 스타일 틸트
    vix_reg = style_sig.get("vix_regime", "medium")
    if vix_reg == "high":  # Risk-OFF → 방어적
        alloc["us_eq"]    = max(alloc["us_eq"] - 2, 2)
        alloc["mixed"]    = min(alloc["mixed"] + 2, 18)

    # 4) KRW signal → 해외 비중 조정
    krw_trend = krw_sig.get("trend", "N/A")
    if "약세" in krw_trend:   # 원화 약세 → 해외 헤지 비용 고려
        alloc["us_bond"] = max(alloc["us_bond"] - 2, 8)
        alloc["cash"]    = min(alloc["cash"] + 2, 18)

    # 5) K-ICS 주식 한도 체크 및 조정
    total_eq = sum(alloc[k] for k in ["kr_eq", "us_eq", "global_eq", "em_eq", "sector_eq"])
    if total_eq > K_ICS_EQUITY_LIMIT:
        excess = total_eq - K_ICS_EQUITY_LIMIT
        # 비례 축소
        for k in ["sector_eq", "em_eq", "us_eq", "global_eq", "kr_eq"]:
            cut = min(alloc[k], excess)
            alloc[k] -= cut
            excess   -= cut
            alloc["mixed"] = min(alloc["mixed"] + cut, 20)
            if excess == 0:
                break

    # 6) 합계 100% 조정
    total = sum(alloc.values())
    if total != 100:
        diff = 100 - total
        alloc["cash"] = max(0, alloc["cash"] + diff)

    return alloc


def compute_allocation_view(date) -> dict:
    date_str = str(date)

    # 1) 기본 신호 수집
    regime      = _get_macro_regime(date_str)
    country_sig = _get_country_signals(date_str)
    bond_sig    = _get_bond_signals(date_str)
    style_sig   = _get_style_signals(date_str)
    sector_tops = _get_sector_signals(date_str)
    krw_sig     = _get_krw_signal(date_str)

    # 2) 기준 배분
    base_kr = BASE_ALLOC.get(regime, BASE_ALLOC["N/A"])
    base_us = BASE_ALLOC_US.get(regime, BASE_ALLOC_US["N/A"])

    # 3) 신호 반영 → 조정 배분
    adj_kr = _adjust_alloc(base_kr, country_sig, bond_sig, style_sig, krw_sig)

    # 4) K-ICS 주식 한도 확인
    total_eq = sum(adj_kr.get(k, 0) for k in ["kr_eq", "us_eq", "global_eq", "em_eq", "sector_eq"])
    kics_breach = total_eq > K_ICS_EQUITY_LIMIT

    # 5) 상위 국가·섹터 코멘트
    ow_countries = [k for k, v in country_sig.items() if v == "OW"]
    uw_countries = [k for k, v in country_sig.items() if v == "UW"]

    # 6) 변액보험 포트폴리오 주요 코멘트
    rationale = _build_rationale(regime, country_sig, bond_sig, style_sig, krw_sig, sector_tops)

    # ── 7) Black-Litterman + Risk Parity ──────────────────────────────────
    prices = _load_prices(date_str)
    proxy_ret = _get_proxy_returns(prices)

    n = len(CATEGORY_IDS)
    bl_result = {"implied_mu": {}, "bl_mu": {}, "rp_weights": {}, "expected_returns": {}}

    if len(proxy_ret) >= 60:
        try:
            # Annualized covariance from daily log returns
            sigma_daily = proxy_ret.cov().values
            sigma_ann   = sigma_daily * 252

            # Market-cap equilibrium weights
            mkt_w = np.array([MARKET_CAP_WEIGHTS.get(cid, 0.05) for cid in CATEGORY_IDS])
            mkt_w = mkt_w / mkt_w.sum()

            # Implied equilibrium returns: μ = δ * Σ * w_mkt
            delta = 2.5   # risk aversion
            implied_mu_arr = delta * sigma_ann @ mkt_w

            # BL views from signals
            views = _build_bl_views(country_sig, bond_sig, style_sig, n)
            bl_mu_arr = _black_litterman(sigma_ann, implied_mu_arr, views)

            # Risk parity
            eq_indices = [CATEGORY_IDS.index(c) for c in
                          ["kr_eq","us_eq","global_eq","em_eq","sector_eq"]
                          if c in CATEGORY_IDS]
            rp_w = _risk_parity_weights(sigma_ann, n, eq_indices,
                                        eq_limit=K_ICS_EQUITY_LIMIT / 100)

            # Expected return ensemble
            exp_ret = _expected_return_ensemble(proxy_ret, bl_mu_arr, regime)

            bl_result = {
                "implied_mu": {cid: round(float(implied_mu_arr[i]) * 100, 2)
                               for i, cid in enumerate(CATEGORY_IDS)},
                "bl_mu":      {cid: round(float(bl_mu_arr[i]) * 100, 2)
                               for i, cid in enumerate(CATEGORY_IDS)},
                "rp_weights": {cid: round(float(rp_w[i]) * 100, 1)
                               for i, cid in enumerate(CATEGORY_IDS)},
                "expected_returns": exp_ret,
            }
        except Exception as e:
            bl_result["error"] = str(e)[:100]

    return {
        "date":        date_str,
        "regime":      regime,
        "kr_alloc":    adj_kr,
        "base_kr":     base_kr,
        "us_alloc":    base_us,
        "total_eq":    total_eq,
        "kics_breach": kics_breach,
        "ow_countries": ow_countries,
        "uw_countries": uw_countries,
        "sector_tops": sector_tops,
        "krw_sig":     krw_sig,
        "bond_sig":    bond_sig,
        "style_sig":   style_sig,
        "rationale":   rationale,
        "bl_result":   bl_result,
    }


def _build_rationale(regime, country_sig, bond_sig, style_sig, krw_sig, sector_tops) -> list:
    """배분 근거 bullet points."""
    lines = []
    # Regime
    regime_text = {
        "Goldilocks":  "Goldilocks 국면 — 완만한 성장 + 저물가 → 위험자산 우호적",
        "Reflation":   "Reflation 국면 — 성장 회복 + 인플레 상승 → Value/원자재 강세",
        "Stagflation": "Stagflation 국면 — 성장 둔화 + 고물가 → 방어적 배분 우선",
        "Deflation":   "Deflation 국면 — 성장·물가 동반 하락 → 채권 비중 극대화",
        "N/A":         "매크로 국면 판단 불충분 — 중립적 배분 유지",
    }
    lines.append(f"📊 {regime_text.get(regime, regime)}")

    # Country
    ow = [k for k, v in country_sig.items() if v == "OW"]
    uw = [k for k, v in country_sig.items() if v == "UW"]
    if ow:
        lines.append(f"🌏 OW 국가: {', '.join(ow)} → 해당 지역 주식형 비중 확대")
    if uw:
        lines.append(f"⚠️ UW 국가: {', '.join(uw)} → 해당 지역 비중 축소")

    # Bond
    dur = bond_sig.get("dur_bias", "neutral")
    if dur == "long":
        lines.append("📈 듀레이션 확대 권고 → KR 국고 10Y + 해외채권형(TLT) 비중 유지")
    elif dur == "short":
        lines.append("📉 단기 집중 권고 → CD91D + 단기채 비중 확대, 장기채 축소")
    else:
        lines.append("⚖️ 바벨 전략 유지 → 단기 CD + 장기 KTB 조합")

    # KRW
    hedge = krw_sig.get("hedge_rec", "")
    if hedge:
        lines.append(f"💱 환율: {krw_sig.get('trend','')} (USDKRW {krw_sig.get('last','')})\n   → {hedge}")

    # Style
    top_style = style_sig.get("top_style", "")
    if top_style:
        lines.append(f"🎯 우선 스타일: {top_style} → 해당 스타일 해외주식형 내 비중 확대")

    # Sectors
    if sector_tops:
        lines.append(f"🏭 상위 섹터: {', '.join(sector_tops[:3])} → 섹터형 펀드 편입 고려")

    return lines


# ── HTML rendering ────────────────────────────────────────────────────────

def _fmt(v, dec=1, suffix="%"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{dec}f}{suffix}"


def _alloc_bar(pct: int, color: str = "#4a90d9") -> str:
    w = max(pct, 1)
    return f'<div style="background:{color};height:10px;border-radius:3px;width:{w*3}px;display:inline-block"></div>'


def _bl_html(data: dict) -> str:
    """Black-Litterman 기대수익률 + 리스크 패리티 배분 카드."""
    bl = data.get("bl_result", {})
    if not bl or "error" in bl:
        err = bl.get("error", "데이터 부족") if bl else "계산 미수행"
        return f'<div class="card"><h2>🧮 BL / 리스크 패리티</h2><p style="color:#94a3b8;font-size:13px">분석 불가: {err}</p></div>'

    exp_ret   = bl.get("expected_returns", {})
    rp_w      = bl.get("rp_weights", {})
    bl_mu     = bl.get("bl_mu", {})
    imp_mu    = bl.get("implied_mu", {})
    adj_kr    = data.get("kr_alloc", {})

    name_map = {c["id"]: c["name"] for c in FUND_CATEGORIES}
    group_colors = {"equity":"#1d4ed8","bond":"#059669","mixed":"#7c3aed","alts":"#d97706","cash":"#6b7280"}
    group_map = {c["id"]: c["group"] for c in FUND_CATEGORIES}

    def _ret_str(v):
        if isinstance(v, float) and np.isnan(v): return "—"
        return f"{v*100:+.1f}%" if abs(v) < 10 else f"{v:+.1f}%"

    # Expected returns table
    ret_rows = ""
    for cid in CATEGORY_IDS:
        er = exp_ret.get(cid, {})
        ens = er.get("ensemble", np.nan)
        bl_v = bl_mu.get(cid, np.nan)
        h3y  = er.get("hist_3y", np.nan)
        madj = er.get("macro_adj", 0)
        color = group_colors.get(group_map.get(cid, "cash"), "#64748b")
        ens_color = "#059669" if (not isinstance(ens, float) or ens > 0) else "#dc2626"
        h3_str  = f"{h3y*100:+.1f}%" if isinstance(h3y, float) and not np.isnan(h3y) else "—"
        bl_str  = f"{bl_v:+.1f}%" if isinstance(bl_v, float) and not np.isnan(bl_v) else "—"
        adj_str = f"{madj*100:+.1f}%p" if isinstance(madj, float) else "—"
        ens_str = f"{ens*100:+.1f}%" if isinstance(ens, float) and not np.isnan(ens) else "—"
        ret_rows += f"""<tr>
          <td style="font-size:12px;color:{color};font-weight:600">{name_map.get(cid, cid)}</td>
          <td style="text-align:right;font-family:monospace;font-size:12px">{bl_str}</td>
          <td style="text-align:right;font-family:monospace;font-size:12px">{h3_str}</td>
          <td style="text-align:right;font-family:monospace;font-size:12px;color:#d97706">{adj_str}</td>
          <td style="text-align:right;font-family:monospace;font-size:13px;font-weight:700;color:{ens_color}">{ens_str}</td>
        </tr>"""

    # RP vs Signal comparison table
    cmp_rows = ""
    for cid in CATEGORY_IDS:
        rp_pct   = rp_w.get(cid, 0)
        sig_pct  = adj_kr.get(cid, 0)
        diff     = round(rp_pct - sig_pct, 1)
        color    = group_colors.get(group_map.get(cid, "cash"), "#64748b")
        diff_str = f'<span style="color:{"#059669" if diff > 0 else "#dc2626" if diff < 0 else "#94a3b8"}">{diff:+.1f}%p</span>' if diff != 0 else '<span style="color:#94a3b8">—</span>'
        cmp_rows += f"""<tr>
          <td style="font-size:12px;color:{color};font-weight:600">{name_map.get(cid, cid)}</td>
          <td style="text-align:right;font-weight:700;color:{color}">{rp_pct:.1f}%</td>
          <td style="text-align:right;color:#64748b">{sig_pct}%</td>
          <td style="text-align:right">{diff_str}</td>
        </tr>"""

    return f"""
<div class="card">
  <h2>🧮 BL 기대수익률 & 리스크 패리티 배분</h2>
  <div class="grid2">
    <div>
      <h3 style="font-size:13px;color:var(--muted);margin-bottom:10px">앙상블 기대수익률 (연율, BL 40% + 역사 30% + 매크로 30%)</h3>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="border-bottom:1px solid #e2e8f0">
          <th style="text-align:left;padding:6px 8px;color:#64748b">펀드 유형</th>
          <th style="padding:6px 4px;color:#64748b">BL균형</th>
          <th style="padding:6px 4px;color:#64748b">역사(3Y)</th>
          <th style="padding:6px 4px;color:#d97706">매크로조정</th>
          <th style="padding:6px 4px;color:#1e293b;font-weight:700">앙상블</th>
        </tr></thead>
        <tbody>{ret_rows}</tbody>
      </table>
      <p style="font-size:11px;color:#94a3b8;margin-top:6px">BL균형: δ=2.5 시장위험프리미엄 | 역사: 3Y 로그수익률 합산</p>
    </div>
    <div>
      <h3 style="font-size:13px;color:var(--muted);margin-bottom:10px">리스크 패리티 vs 신호 기반 배분 (K-ICS ≤30% 제약)</h3>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="border-bottom:1px solid #e2e8f0">
          <th style="text-align:left;padding:6px 8px;color:#64748b">펀드 유형</th>
          <th style="padding:6px 4px;color:#2563eb;font-weight:700">RP</th>
          <th style="padding:6px 4px;color:#64748b">신호기반</th>
          <th style="padding:6px 4px;color:#64748b">차이</th>
        </tr></thead>
        <tbody>{cmp_rows}</tbody>
      </table>
      <p style="font-size:11px;color:#94a3b8;margin-top:6px">RP = 동일 위험기여 (Equal Risk Contribution). 양수 = RP가 더 많이 배분.</p>
    </div>
  </div>
</div>"""


def render_html(data: dict) -> str:
    date_str = data["date"]
    regime   = data["regime"]
    adj_kr   = data["kr_alloc"]
    us_alloc = data["us_alloc"]
    krw_sig  = data["krw_sig"]
    total_eq = data["total_eq"]
    breach   = data["kics_breach"]
    rationale= data["rationale"]

    regime_cls = {
        "Goldilocks": "regime-goldilocks", "Reflation": "regime-reflation",
        "Stagflation": "regime-stagflation", "Deflation": "regime-deflation",
    }.get(regime, "badge")

    # Fund category colors by group
    group_colors = {
        "equity": "#1d4ed8", "bond": "#059669",
        "mixed": "#7c3aed", "alts": "#d97706", "cash": "#6b7280",
    }

    def alloc_row(cat: dict, alloc: dict) -> str:
        cid   = cat["id"]
        pct   = alloc.get(cid, 0)
        base  = data["base_kr"].get(cid, 0)
        diff  = pct - base
        color = group_colors.get(cat["group"], "#888")
        if diff > 0:   diff_str = f'<span class="up">+{diff}%p</span>'
        elif diff < 0: diff_str = f'<span class="down">{diff}%p</span>'
        else:          diff_str = '<span class="muted">—</span>'
        return f"""<tr>
          <td style="font-size:13px">{cat["name"]}</td>
          <td style="text-align:right;color:{color};font-size:15px;font-weight:700">{pct}%</td>
          <td>{_alloc_bar(pct, color)}</td>
          <td style="text-align:right" class="muted">{base}%</td>
          <td style="text-align:right">{diff_str}</td>
        </tr>"""

    def us_alloc_row(label, pct, color="#1d4ed8") -> str:
        return f"""<tr>
          <td style="font-size:13px">{label}</td>
          <td style="text-align:right;color:{color};font-size:15px;font-weight:700">{pct}%</td>
          <td>{_alloc_bar(pct, color)}</td>
        </tr>"""

    kr_rows = "".join(alloc_row(cat, adj_kr) for cat in FUND_CATEGORIES)

    us_labels = {
        "us_eq":    ("미국 주식",       "#1d4ed8"),
        "intl_eq":  ("선진국 주식(비미국)", "#2563eb"),
        "em_eq":    ("신흥국 주식",      "#3b82f6"),
        "us_bond":  ("미국/선진 채권",   "#059669"),
        "em_bond":  ("신흥국 채권",      "#10b981"),
        "alts":     ("대안(금·원자재)", "#d97706"),
        "cash":     ("현금",            "#6b7280"),
    }
    us_rows = "".join(
        us_alloc_row(us_labels[k][0], v, us_labels[k][1])
        for k, v in us_alloc.items() if k in us_labels
    )

    kics_cls   = "down" if breach else "up"
    kics_bg    = "var(--down-bg)" if breach else "var(--up-bg)"
    kics_bdr   = "var(--down)" if breach else "var(--up)"
    kics_label = f"⚠️ K-ICS 주식한도({K_ICS_EQUITY_LIMIT}%) 초과 — 자동 조정됨" if breach \
                 else f"✅ K-ICS 주식한도({K_ICS_EQUITY_LIMIT}%) 이내"

    rationale_html = "".join(
        f'<li style="margin-bottom:8px;font-size:13px">{line}</li>'
        for line in rationale
    )

    # equity/bond/alts/cash 합계
    eq_total   = sum(adj_kr.get(k, 0) for k in ["kr_eq","us_eq","global_eq","em_eq","sector_eq"])
    bond_total = sum(adj_kr.get(k, 0) for k in ["kr_bond","us_bond"])
    mix_total  = adj_kr.get("mixed", 0)
    alt_total  = adj_kr.get("alternative", 0)
    cash_total = adj_kr.get("cash", 0)

    summary_cards = "".join(
        f'<div class="stat-card" style="text-align:center">'
        f'<div class="label">{l}</div>'
        f'<div class="value" style="color:{c}">{v}%</div>'
        f'</div>'
        for l, v, c in [
            ("주식합계", eq_total,   "#1d4ed8"),
            ("채권합계", bond_total, "#059669"),
            ("혼합형",   mix_total,  "#7c3aed"),
            ("대안",     alt_total,  "#d97706"),
            ("현금",     cash_total, "#6b7280"),
        ]
    )

    from ._shared import html_page
    extra_css = ".grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:800px){.grid2{grid-template-columns:1fr}}"
    body = f"""<div class="ma-header">
  <div>
    <h1>배분안 View</h1>
    <div class="meta">미래에셋생명 변액보험 펀드 배분 의견</div>
  </div>
  <div class="date-badge">{date_str}</div>
</div>

<!-- ── 현재 국면 + 환율 배너 ── -->
<div class="card">
  <div class="stat-grid">
    <div class="stat-card">
      <div class="label">현재 매크로 국면</div>
      <div style="margin-top:6px"><span class="{regime_cls}">{regime}</span></div>
    </div>
    <div class="stat-card" style="flex:2;min-width:200px">
      <div class="label">USDKRW 추세 / 환헤지 권고</div>
      <div style="font-size:14px;font-weight:600;margin-top:4px;color:{krw_sig["color"]}">{krw_sig.get("trend","N/A")}</div>
      <div class="sub">{krw_sig.get("hedge_rec","")}</div>
    </div>
    <div class="stat-card" style="flex:2;min-width:200px;background:{kics_bg};border-color:{kics_bdr}">
      <div class="label">K-ICS 주식한도</div>
      <div class="{kics_cls}" style="font-size:14px;font-weight:600;margin-top:4px">{kics_label}</div>
      <div class="sub">현재 주식 합계: {eq_total}% / 한도 {K_ICS_EQUITY_LIMIT}%</div>
    </div>
  </div>
</div>

<!-- ── 자산군 요약 ── -->
<div class="card">
  <h2>📊 자산군 요약</h2>
  <div class="stat-grid">{summary_cards}</div>
</div>

<div class="grid2">
  <!-- ── KR 변액보험 배분 ── -->
  <div class="card">
    <h2>🇰🇷 KR 변액보험 펀드 배분 (KRW 기준)</h2>
    <table>
      <thead><tr>
        <th>펀드 유형</th>
        <th style="text-align:right">추천</th>
        <th>비중</th>
        <th style="text-align:right">기준</th>
        <th style="text-align:right">조정</th>
      </tr></thead>
      <tbody>{kr_rows}</tbody>
    </table>
    <div class="muted" style="font-size:11px;margin-top:8px">
      기준 = 국면별 베이스라인 | 조정 = 국가·채권·스타일 신호 반영
    </div>
  </div>

  <!-- ── US 참고 배분 ── -->
  <div class="card">
    <h2>🇺🇸 US 투자자 참고 배분 (USD 기준)</h2>
    <table>
      <thead><tr>
        <th>자산군</th>
        <th style="text-align:right">비중</th>
        <th>바</th>
      </tr></thead>
      <tbody>{us_rows}</tbody>
    </table>
    <div class="muted" style="font-size:11px;margin-top:8px">
      * USD 기준 글로벌 배분 참고 (K-ICS 제약 없음)
    </div>
  </div>
</div>

<!-- ── BL 기대수익률 & 리스크 패리티 ── -->
{_bl_html(data)}

<!-- ── 배분 근거 ── -->
<div class="card">
  <h2>📋 배분 근거 및 주요 신호</h2>
  <ul style="list-style:none;padding:0">
    {rationale_html}
  </ul>
</div>

<!-- ── 주의사항 ── -->
<div style="background:var(--primary-light);border:1px solid var(--primary);border-radius:8px;padding:14px 18px;margin-bottom:20px">
  <div style="color:var(--primary);font-size:12px;font-weight:700;margin-bottom:6px">⚠️ 주의사항</div>
  <div style="font-size:12px;line-height:1.6;color:var(--text)">
    본 배분 의견은 규칙 기반 알고리즘으로 자동 생성되며 투자 권유가 아닙니다.
    실제 운용 시 K-ICS 규제, ALM 듀레이션 매칭, 유동성 요건, 계약자 리스크 성향 등을 종합 고려하십시오.
    주식 비중은 K-ICS 규제상 30% 한도를 참고 기준으로 적용하였습니다.
  </div>
</div>"""
    return html_page("배분안 View", date_str, body, "allocation",
                     extra_css=extra_css,
                     source="FRED · yfinance · ECOS · country/sector/bond/style 통합")


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Allocation View")
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    data   = compute_allocation_view(target)

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
