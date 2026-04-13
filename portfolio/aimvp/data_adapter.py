"""Bridge: market_data.csv -> monthly Series matching riskon's fetch_all() interface."""

from pathlib import Path

import numpy as np
import pandas as pd

from .config import STOCK_CODE, BOND_CODE, CASH_CODE, VIX_CODE

ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY_CSV = ROOT / "history" / "market_data.csv"


def load_monthly_from_csv(csv_path: str | Path | None = None) -> dict[str, pd.Series]:
    """Load daily prices from CSV, resample to month-end.

    Returns dict with keys "stock", "bond", "cash", "vix" —
    same interface as riskon's data.fetch_all().
    """
    path = Path(csv_path) if csv_path else HISTORY_CSV
    df = pd.read_csv(path, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    wide = wide.sort_index()

    result = {}
    for key, code in [("stock", STOCK_CODE), ("bond", BOND_CODE), ("vix", VIX_CODE)]:
        if code not in wide.columns:
            raise KeyError(f"{code} not found in market_data.csv")
        series = wide[code].dropna().resample("ME").last().dropna()
        series.name = key
        result[key] = series

    # Cash proxy: synthesize from 2Y yield -> monthly price series
    if CASH_CODE and CASH_CODE in wide.columns:
        yield_monthly = wide[CASH_CODE].dropna().resample("ME").last().dropna()
        monthly_ret = yield_monthly / 1200  # annual % -> monthly decimal
        cash_price = (1 + monthly_ret).cumprod()
        cash_price.name = "cash"
        result["cash"] = cash_price
    else:
        idx = result["stock"].index
        result["cash"] = pd.Series(1.0, index=idx, name="cash")

    return result
