"""TAA signal computation — ported from market-strategy/riskon/signals.py.

Signal 1 (Trend)   : price > N-month MA -> +1, else -> -1
Signal 2 (Momentum): stock 12mo return > bond 12mo return -> +1, else -> -1
Signal 3 (VIX)     : VIX <= 20 -> +1 / VIX >= 30 -> -1 / else -> 0

All functions take month-end pd.Series and return per-month signal pd.Series.
"""

import pandas as pd
from .config import TREND_WINDOW, MOMENTUM_WINDOW, VIX_LOW, VIX_HIGH


def trend_signal(stock_prices: pd.Series, window: int = TREND_WINDOW) -> pd.Series:
    ma = stock_prices.rolling(window).mean()
    signal = pd.Series(index=stock_prices.index, dtype=int, name="trend")
    signal[stock_prices >= ma] =  1
    signal[stock_prices <  ma] = -1
    return signal


def momentum_signal(
    stock_prices: pd.Series,
    bond_prices:  pd.Series,
    window: int = MOMENTUM_WINDOW,
) -> pd.Series:
    stock_ret = stock_prices.pct_change(window)
    bond_ret  = bond_prices.pct_change(window)

    common = stock_ret.index.intersection(bond_ret.index)
    s = stock_ret.loc[common]
    b = bond_ret.loc[common]

    signal = pd.Series(index=common, dtype=int, name="momentum")
    signal[s >= b] =  1
    signal[s <  b] = -1
    return signal


def vix_signal(vix_prices: pd.Series) -> pd.Series:
    signal = pd.Series(0, index=vix_prices.index, dtype=int, name="vix")
    signal[vix_prices <= VIX_LOW]  =  1
    signal[vix_prices >= VIX_HIGH] = -1
    return signal


def compute_all_signals(
    stock_prices: pd.Series,
    bond_prices:  pd.Series,
    vix_prices:   pd.Series,
) -> pd.DataFrame:
    trend    = trend_signal(stock_prices)
    momentum = momentum_signal(stock_prices, bond_prices)
    vix      = vix_signal(vix_prices)

    df = pd.DataFrame({"trend": trend, "momentum": momentum, "vix": vix})
    df["score"] = df["trend"] + df["momentum"] + df["vix"]
    return df.dropna(subset=["trend", "momentum"])
