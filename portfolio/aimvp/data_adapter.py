"""Bridge: market_data.csv -> monthly Series matching riskon's fetch_all() interface."""

from pathlib import Path

import numpy as np
import pandas as pd

from .config import STOCK_CODE, BOND_CODE, CASH_CODE, VIX_CODE

ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY_CSV = ROOT / "history" / "market_data.csv"


def load_monthly_from_csv(csv_path: str | Path | None = None) -> dict[str, pd.Series]:
    """Load daily prices from Snowflake MKT100 (CSV fallback), resample to month-end.

    함수명에 `from_csv` 가 남아있는 건 하위호환용. 실제로는 Snowflake 를 우선 읽는다.
    csv_path override 가 들어오면 해당 CSV 를 그대로 읽는다.
    """
    if csv_path is not None:
        path = Path(csv_path)
        df = pd.read_csv(path, parse_dates=["DATE"])
    else:
        from portfolio.market_source import load_long
        df = load_long()
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    wide = wide.sort_index()

    result = {}
    for key, code in [("stock", STOCK_CODE), ("bond", BOND_CODE), ("vix", VIX_CODE)]:
        if code not in wide.columns:
            raise KeyError(f"{code} not found in MKT100 / market_data.csv")
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
