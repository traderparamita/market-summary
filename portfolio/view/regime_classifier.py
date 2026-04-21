"""HMM-based regime classifier — 3-state Gaussian HMM.

States: RiskOFF (0) / Neutral (1) / RiskON (2)
Features: VIX, yield_curve, breadth_ma200, hy_spread

Usage:
    from portfolio.view.regime_classifier import RegimeClassifier
    clf = RegimeClassifier()
    clf.fit(features_df)
    proba_df = clf.predict_proba(features_df)   # columns: RiskOFF / Neutral / RiskON
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    from hmmlearn import hmm as _hmm
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False


ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY_CSV = ROOT / "history" / "market_data.csv"


# ─────────────────────────────────────────────────────────────
# Fallback: 규칙 기반 레짐 (HMM 없을 때)
# ─────────────────────────────────────────────────────────────

def rule_based_regime(
    vix: float | None,
    breadth: float | None,
    hy_spread: float | None = None,
) -> dict:
    """현재 규칙 기반 레짐 → 확률 형태로 변환.

    Returns:
        dict with keys RiskOFF / Neutral / RiskON (합=1.0)
    """
    vix = vix or 20.0
    breadth = breadth or 0.5

    if vix > 30 or (breadth < 0.35):
        return {"RiskOFF": 0.75, "Neutral": 0.20, "RiskON": 0.05}
    elif vix > 25 or breadth < 0.50:
        return {"RiskOFF": 0.45, "Neutral": 0.40, "RiskON": 0.15}
    elif vix < 14 and breadth > 0.70:
        return {"RiskOFF": 0.05, "Neutral": 0.20, "RiskON": 0.75}
    elif vix < 18 and breadth > 0.60:
        return {"RiskOFF": 0.10, "Neutral": 0.35, "RiskON": 0.55}
    else:
        return {"RiskOFF": 0.15, "Neutral": 0.60, "RiskON": 0.25}


# ─────────────────────────────────────────────────────────────
# HMM 기반 분류기
# ─────────────────────────────────────────────────────────────

class RegimeClassifier:
    """3-state Gaussian HMM regime classifier.

    Feature columns expected (all numeric, NaN→ffill):
        vix_norm        : VIX normalized (divide by 20)
        yield_curve     : 10Y - 2Y spread (raw %)
        breadth_ma200   : fraction above 200-day MA
        hy_spread_norm  : HY credit spread normalized (divide by 5)

    Falls back to rule_based_regime() if hmmlearn is unavailable
    or training data insufficient.
    """

    STATE_NAMES = ["RiskOFF", "Neutral", "RiskON"]

    def __init__(self, n_states: int = 3, n_iter: int = 200, random_state: int = 42):
        self.n_states = n_states
        self.n_iter = n_iter
        self.random_state = random_state
        self._model = None
        self._state_order: list[int] = list(range(n_states))  # index → state index
        self._fitted = False

    # ------------------------------------------------------------------
    def _build_features(self, df: pd.DataFrame) -> np.ndarray:
        needed = ["vix_norm", "yield_curve", "breadth_ma200", "hy_spread_norm"]
        available = [c for c in needed if c in df.columns]
        X = df[available].ffill().fillna(0).values
        return X.astype(float)

    # ------------------------------------------------------------------
    def fit(self, features_df: pd.DataFrame) -> "RegimeClassifier":
        """Train HMM on historical feature data.

        Args:
            features_df: DataFrame with date index + feature columns.
                         Should cover at least 2 years for meaningful training.
        """
        if not HMM_AVAILABLE:
            return self

        X = self._build_features(features_df)
        if len(X) < 200:
            return self

        model = _hmm.GaussianHMM(
            n_components=self.n_states,
            covariance_type="full",
            n_iter=self.n_iter,
            random_state=self.random_state,
        )
        model.fit(X)
        self._model = model
        self._fitted = True

        # 상태 정렬: VIX 평균 기준 (높을수록 RiskOFF)
        vix_col = features_df.columns.get_loc("vix_norm") if "vix_norm" in features_df.columns else 0
        means = model.means_[:, vix_col]
        self._state_order = list(np.argsort(means)[::-1])  # 높은 VIX = RiskOFF = 0
        return self

    # ------------------------------------------------------------------
    def predict_proba(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """Posterior state probabilities for each date.

        Returns:
            DataFrame(index=features_df.index, columns=['RiskOFF','Neutral','RiskON'])
            Probabilities sum to 1.0 per row.
        """
        if not self._fitted or self._model is None:
            # 규칙 기반 fallback
            return self._rule_based_proba(features_df)

        X = self._build_features(features_df)
        try:
            posteriors = self._model.predict_proba(X)  # shape (T, n_states)
        except Exception:
            return self._rule_based_proba(features_df)

        # 상태 순서 재배열 → [RiskOFF, Neutral, RiskON]
        reordered = posteriors[:, self._state_order]

        result = pd.DataFrame(
            reordered,
            index=features_df.index,
            columns=self.STATE_NAMES,
        )

        # Degenerate 체크: 단일 상태 확률 > 95% → rule-based fallback
        last_max = result.iloc[-1].max()
        if last_max > 0.95:
            self._fitted = False  # method 표시를 rule-based로 전환
            return self._rule_based_proba(features_df)

        return result

    # ------------------------------------------------------------------
    def predict(self, features_df: pd.DataFrame) -> pd.Series:
        """Most likely regime label per date."""
        proba = self.predict_proba(features_df)
        return proba.idxmax(axis=1)

    # ------------------------------------------------------------------
    def _rule_based_proba(self, features_df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, row in features_df.iterrows():
            vix = row.get("vix_norm", 1.0) * 20
            breadth = row.get("breadth_ma200", 0.5)
            hy = row.get("hy_spread_norm", 1.0) * 5
            p = rule_based_regime(vix, breadth, hy)
            rows.append([p["RiskOFF"], p["Neutral"], p["RiskON"]])
        return pd.DataFrame(rows, index=features_df.index, columns=self.STATE_NAMES)

    # ------------------------------------------------------------------
    def transition_probability(self) -> pd.DataFrame | None:
        """상태 전이 확률 행렬 (HMM fitted 후에만)."""
        if not self._fitted or self._model is None:
            return None
        T = self._model.transmat_
        T_reordered = T[np.ix_(self._state_order, self._state_order)]
        return pd.DataFrame(
            T_reordered,
            index=self.STATE_NAMES,
            columns=self.STATE_NAMES,
        ).round(3)


# ─────────────────────────────────────────────────────────────
# 특성 데이터 빌더
# ─────────────────────────────────────────────────────────────

def build_hmm_features(
    prices: pd.DataFrame,
    macro_signals: dict,
    end_date: str | None = None,
) -> pd.DataFrame:
    """market_data.csv wide DataFrame → HMM feature DataFrame.

    Args:
        prices: DATE-indexed wide price DataFrame (from scoring.load_prices)
        macro_signals: universe.yaml macro_signals dict
        end_date: cut-off date (YYYY-MM-DD), default = latest

    Returns:
        DataFrame with columns: vix_norm, yield_curve, breadth_ma200, hy_spread_norm
    """
    if end_date:
        prices = prices[prices.index <= pd.Timestamp(end_date)]

    features = pd.DataFrame(index=prices.index)

    # VIX normalized
    vix_code = macro_signals.get("vix")
    if vix_code and vix_code in prices.columns:
        features["vix_norm"] = (prices[vix_code] / 20.0).clip(0.3, 5.0)

    # Yield curve (10Y - 2Y)
    yc = macro_signals.get("yield_curve", {})
    long_code  = yc.get("long")
    short_code = yc.get("short")
    if long_code in prices.columns and short_code in prices.columns:
        features["yield_curve"] = (prices[long_code] - prices[short_code]).fillna(0)

    # Breadth MA200 — rolling proxy using equity assets
    # We use a simple approach: if available from scoring output, inject externally
    # Otherwise default 0.5
    features["breadth_ma200"] = 0.5  # will be overridden at score time

    # HY spread normalized (canonical: US_HY_SPREAD, legacy alias: CREDIT_HY_SPREAD)
    hy_code = None
    for cand in ("US_HY_SPREAD", "CREDIT_HY_SPREAD"):
        if cand in prices.columns:
            hy_code = cand
            break
    if hy_code:
        features["hy_spread_norm"] = (prices[hy_code] / 5.0).clip(0.5, 5.0)
    else:
        features["hy_spread_norm"] = 1.0

    return features.dropna(subset=["vix_norm"]) if "vix_norm" in features else features


# ─────────────────────────────────────────────────────────────
# 편의 함수: 단일 날짜 레짐 확률
# ─────────────────────────────────────────────────────────────

def get_regime_proba(
    prices: pd.DataFrame,
    date: str,
    macro_signals: dict,
    classifier: RegimeClassifier | None = None,
) -> dict:
    """한 날짜의 레짐 확률 딕셔너리 반환.

    Returns: {"RiskOFF": 0.15, "Neutral": 0.60, "RiskON": 0.25, "dominant": "Neutral"}
    """
    feats = build_hmm_features(prices, macro_signals, end_date=date)
    if feats.empty:
        return {"RiskOFF": 0.15, "Neutral": 0.70, "RiskON": 0.15, "dominant": "Neutral"}

    if classifier is None:
        classifier = RegimeClassifier()
        if HMM_AVAILABLE and len(feats) >= 200:
            classifier.fit(feats)

    proba_df = classifier.predict_proba(feats)
    last_row = proba_df.iloc[-1]
    result = last_row.to_dict()
    result["dominant"] = last_row.idxmax()
    return result
