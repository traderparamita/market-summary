"""Position and weight logic — ported from market-strategy/riskon/model.py."""

import pandas as pd
from .config import (
    RISK_ON_THRESHOLD, RISK_OFF_THRESHOLD,
    ALLOC_RISK_ON, ALLOC_NEUTRAL, ALLOC_RISK_OFF,
)
from .signals import compute_all_signals


def score_to_position(score: float, prev_position: str | None) -> str:
    if score >= RISK_ON_THRESHOLD:
        return "RISK_ON"
    if score <= RISK_OFF_THRESHOLD:
        return "RISK_OFF"
    return prev_position if prev_position else "RISK_OFF"


def score_to_regime(score: float) -> str:
    if score >= RISK_ON_THRESHOLD:
        return "RiskON"
    if score <= RISK_OFF_THRESHOLD:
        return "RiskOFF"
    return "Neutral"


def build_position_series(signal_df: pd.DataFrame) -> pd.Series:
    positions = []
    prev = None
    for _date, row in signal_df.iterrows():
        pos = score_to_position(row["score"], prev)
        positions.append(pos)
        prev = pos
    return pd.Series(positions, index=signal_df.index, name="position")


def build_weight_series(signal_df: pd.DataFrame) -> pd.DataFrame:
    def _score_to_weights(score: float) -> tuple:
        if score >= RISK_ON_THRESHOLD:
            return ALLOC_RISK_ON
        if score <= RISK_OFF_THRESHOLD:
            return ALLOC_RISK_OFF
        return ALLOC_NEUTRAL

    rows = [_score_to_weights(s) for s in signal_df["score"]]
    return pd.DataFrame(rows, index=signal_df.index, columns=["w_stock", "w_bond", "w_cash"])
