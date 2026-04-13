"""Backtest engine.

Supports two strategy types:
  - Static: fixed weights rebalanced monthly (e.g. static_60_40)
  - Dynamic TAA: signal-driven monthly weight changes (e.g. aimvp_riskon)

Usage:
    python -m portfolio.backtest --strategy static_60_40
    python -m portfolio.backtest --strategy aimvp_riskon
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
HISTORY_CSV = ROOT / "history" / "market_data.csv"
UNIVERSE_YAML = Path(__file__).resolve().parent / "universe.yaml"
STRATEGIES_DIR = Path(__file__).resolve().parent / "strategies"


def load_strategy(name: str) -> dict:
    path = STRATEGIES_DIR / f"{name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_universe(path: Path = UNIVERSE_YAML) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_prices(csv_path: str | Path = HISTORY_CSV) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    wide = wide.sort_index()
    return wide


def _calc_metrics(nav: pd.Series, port_ret: pd.Series, rf: float = 0.04) -> dict:
    total_days = (nav.index[-1] - nav.index[0]).days
    total_return = float(nav.iloc[-1]) - 1.0
    cagr = (1 + total_return) ** (365.25 / total_days) - 1 if total_days > 0 else 0
    ann_vol = float(port_ret.std() * np.sqrt(252))
    sharpe = (cagr - rf) / ann_vol if ann_vol > 0 else 0
    cummax = nav.cummax()
    drawdown = (nav - cummax) / cummax
    mdd = float(drawdown.min())
    return {
        "cagr": cagr,
        "sharpe": sharpe,
        "mdd": mdd,
        "ann_vol": ann_vol,
        "total_return": total_return,
    }


# ── Static strategy backtest ─────────────────────────────────

def _run_static_backtest(
    prices: pd.DataFrame,
    strategy: dict,
    universe: dict,
    cost_bps: float,
) -> dict:
    assets_config = universe["assets"]
    allocations = strategy["allocations"]

    weights = {}
    for etf, weight in allocations.items():
        if etf not in assets_config:
            continue
        info = assets_config[etf]
        if info.get("is_yield", False):
            continue
        code = info["indicator_code"]
        weights[code] = {"weight": weight, "etf": etf}

    available = [c for c in weights if c in prices.columns]
    if not available:
        print("ERROR: No overlapping data for strategy assets.")
        sys.exit(1)

    px = prices[available].copy().dropna(how="any").ffill()
    daily_ret = px.pct_change().iloc[1:]

    total_w = sum(weights[c]["weight"] for c in available)
    w = pd.Series({c: weights[c]["weight"] / total_w for c in available})
    port_ret = daily_ret[available].mul(w).sum(axis=1)

    rebal_dates = port_ret.index.to_series().dt.is_month_end
    n_rebal = int(rebal_dates.sum())
    cost_drag = pd.Series(0.0, index=port_ret.index)
    cost_drag[rebal_dates] = 0.05 * (cost_bps / 10000) * 2
    port_ret_net = port_ret - cost_drag

    nav = (1 + port_ret_net).cumprod()

    metrics = _calc_metrics(nav, port_ret)
    metrics.update({
        "nav": nav,
        "n_rebal": n_rebal,
        "n_days": len(nav),
        "start": str(nav.index[0].date()),
        "end": str(nav.index[-1].date()),
    })
    return metrics


# ── Dynamic TAA backtest ──────────────────────────────────────

def _run_taa_backtest(
    prices: pd.DataFrame,
    strategy: dict,
    universe: dict,
    cost_bps: float,
) -> dict:
    from .aimvp import compute_all_signals, load_monthly_from_csv
    from .aimvp.model import build_weight_series
    from .aimvp.config import STOCK_CODE, BOND_CODE, CASH_CODE

    monthly = load_monthly_from_csv()
    sig_df = compute_all_signals(monthly["stock"], monthly["bond"], monthly["vix"])
    weight_df = build_weight_series(sig_df)

    # Daily prices for stock/bond/cash
    stock_daily = prices[STOCK_CODE].dropna() if STOCK_CODE in prices.columns else None
    bond_daily = prices[BOND_CODE].dropna() if BOND_CODE in prices.columns else None

    if stock_daily is None or bond_daily is None:
        print("ERROR: Missing ACWI or AGG data.")
        sys.exit(1)

    # Cash: synthesize from 2Y yield or use 0
    if CASH_CODE and CASH_CODE in prices.columns:
        cash_yield = prices[CASH_CODE].dropna().ffill()
        cash_daily_ret = cash_yield / 25200  # annual % -> daily decimal
    else:
        cash_daily_ret = pd.Series(0.0, index=stock_daily.index)

    stock_ret = stock_daily.pct_change()
    bond_ret = bond_daily.pct_change()

    common = stock_ret.index.intersection(bond_ret.index)
    stock_ret = stock_ret.loc[common]
    bond_ret = bond_ret.loc[common]
    cash_ret = cash_daily_ret.reindex(common).fillna(0)

    # Map monthly weights to daily: each day uses the weight from the latest month-end
    # Shift by 1 month to avoid look-ahead bias (signal at month-end -> applied next month)
    weight_df_shifted = weight_df.shift(1).dropna()

    daily_w_stock = pd.Series(np.nan, index=common)
    daily_w_bond = pd.Series(np.nan, index=common)
    daily_w_cash = pd.Series(np.nan, index=common)

    for dt in weight_df_shifted.index:
        mask = common >= dt
        daily_w_stock[mask] = weight_df_shifted.loc[dt, "w_stock"]
        daily_w_bond[mask] = weight_df_shifted.loc[dt, "w_bond"]
        daily_w_cash[mask] = weight_df_shifted.loc[dt, "w_cash"]

    valid = daily_w_stock.notna()
    stock_ret = stock_ret[valid]
    bond_ret = bond_ret[valid]
    cash_ret = cash_ret[valid]
    daily_w_stock = daily_w_stock[valid]
    daily_w_bond = daily_w_bond[valid]
    daily_w_cash = daily_w_cash[valid]

    if stock_ret.empty:
        print("ERROR: No valid backtest period after signal lookback.")
        sys.exit(1)

    port_ret = (stock_ret * daily_w_stock
                + bond_ret * daily_w_bond
                + cash_ret * daily_w_cash)

    # Transaction costs on weight changes (monthly)
    w_changes = daily_w_stock.diff().abs() + daily_w_bond.diff().abs() + daily_w_cash.diff().abs()
    is_month_start = port_ret.index.to_series().dt.is_month_start
    turnover_cost = pd.Series(0.0, index=port_ret.index)
    turnover_cost[is_month_start] = w_changes[is_month_start] * (cost_bps / 10000)
    port_ret_net = port_ret - turnover_cost

    nav = (1 + port_ret_net).cumprod()
    n_switches = int((w_changes[is_month_start] > 0.01).sum())

    metrics = _calc_metrics(nav, port_ret)
    metrics.update({
        "nav": nav,
        "n_rebal": n_switches,
        "n_days": len(nav),
        "start": str(nav.index[0].date()),
        "end": str(nav.index[-1].date()),
    })
    return metrics


# ── Main entry point ──────────────────────────────────────────

def run_backtest(
    prices: pd.DataFrame,
    strategy: dict,
    universe: dict,
    cost_bps: float = 10.0,
) -> dict:
    if strategy.get("type") == "dynamic_taa":
        return _run_taa_backtest(prices, strategy, universe,
                                  cost_bps=strategy.get("cost_bps", cost_bps))
    return _run_static_backtest(prices, strategy, universe, cost_bps)


def main():
    parser = argparse.ArgumentParser(description="Backtest engine")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--csv", default=str(HISTORY_CSV))
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()

    universe = load_universe()
    strategy = load_strategy(args.strategy)
    prices = load_prices(args.csv)

    result = run_backtest(prices, strategy, universe, cost_bps=args.cost_bps)

    print(f"\n{'='*55}")
    print(f"  Backtest: {strategy.get('name', args.strategy)}")
    print(f"{'='*55}")
    print(f"  Period:        {result['start']} -> {result['end']} ({result['n_days']} trading days)")
    print(f"  Total Return:  {result['total_return']:+.1%}")
    print(f"  CAGR:          {result['cagr']:+.1%}")
    print(f"  Ann. Vol:      {result['ann_vol']:.1%}")
    print(f"  Sharpe (rf=4%): {result['sharpe']:.2f}")
    print(f"  Max Drawdown:  {result['mdd']:.1%}")
    print(f"  Regime changes: {result['n_rebal']}")
    print(f"{'='*55}\n")

    if "allocations" in strategy:
        print("  Static Allocations:")
        for etf, weight in strategy["allocations"].items():
            print(f"    {etf:>6s}: {weight:.0%}")
        print()


if __name__ == "__main__":
    main()
