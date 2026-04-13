"""Asset scoring engine.

Loads history/market_data.csv, computes per-asset signals (momentum, trend,
volatility), macro overlays (yield curve, VIX regime, DXY trend), and
outputs a composite score table.

Usage:
    python -m portfolio.view.scoring --date 2026-04-09
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY_CSV = ROOT / "history" / "market_data.csv"
UNIVERSE_YAML = Path(__file__).resolve().parent.parent / "universe.yaml"


def load_universe(path: Path = UNIVERSE_YAML) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_prices(csv_path: str | Path = HISTORY_CSV) -> pd.DataFrame:
    """Load market_data.csv and pivot to wide format (DATE x INDICATOR_CODE -> CLOSE)."""
    df = pd.read_csv(csv_path, parse_dates=["DATE"])
    df = df[["DATE", "INDICATOR_CODE", "CLOSE"]].dropna(subset=["CLOSE"])
    wide = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE")
    wide = wide.sort_index()
    return wide


def _safe_momentum(series: pd.Series, lookback: int, skip: int = 22) -> float:
    """Momentum = price(t-skip) / price(t-lookback) - 1."""
    if len(series) < lookback:
        return np.nan
    p_end = series.iloc[-skip] if len(series) >= skip else series.iloc[-1]
    p_start = series.iloc[-lookback]
    if p_start <= 0:
        return np.nan
    return float(p_end / p_start - 1)


def compute_signals(prices: pd.DataFrame, date: str, universe: dict) -> pd.DataFrame:
    """Compute per-asset signals as of a given date."""
    target = pd.Timestamp(date)
    px = prices[prices.index <= target].copy()

    assets = universe["assets"]
    macro = universe.get("macro_signals", {})

    records = []
    for etf, info in assets.items():
        code = info["indicator_code"]
        if code not in px.columns:
            continue

        series = px[code].dropna()
        if len(series) < 50:
            continue

        last_price = float(series.iloc[-1])

        mom_12_1 = _safe_momentum(series, 252, 22)
        mom_6_1 = _safe_momentum(series, 126, 22)

        ma200 = float(series.tail(200).mean()) if len(series) >= 200 else float(series.mean())
        trend = 1.0 if last_price > ma200 else 0.0

        returns = series.pct_change().dropna()
        vol_20d = float(returns.tail(20).std() * np.sqrt(252)) if len(returns) >= 20 else np.nan

        records.append({
            "etf": etf,
            "asset_class": info["asset_class"],
            "indicator_code": code,
            "close": last_price,
            "mom_12_1": mom_12_1,
            "mom_6_1": mom_6_1,
            "trend_ma200": trend,
            "vol_20d": vol_20d,
        })

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Cross-sectional z-scores for momentum
    for col in ["mom_12_1", "mom_6_1"]:
        mean = df[col].mean()
        std = df[col].std()
        df[f"{col}_z"] = (df[col] - mean) / std if std and std > 0 else 0.0

    # ── Macro overlays ────────────────────────────────────────────
    yield_curve_slope = np.nan
    yc = macro.get("yield_curve", {})
    if yc:
        long_code = yc.get("long")
        short_code = yc.get("short")
        if long_code in px.columns and short_code in px.columns:
            ly = px[long_code].dropna()
            sy = px[short_code].dropna()
            if not ly.empty and not sy.empty:
                yield_curve_slope = float(ly.iloc[-1] - sy.iloc[-1])

    vix_level = np.nan
    vix_code = macro.get("vix")
    if vix_code and vix_code in px.columns:
        vix_s = px[vix_code].dropna()
        if not vix_s.empty:
            vix_level = float(vix_s.iloc[-1])

    vix_regime = 0.0
    if not np.isnan(vix_level):
        if vix_level > 25:
            vix_regime = -1.0
        elif vix_level < 15:
            vix_regime = 1.0

    dxy_trend = 0.0
    dxy_code = macro.get("dxy")
    if dxy_code and dxy_code in px.columns:
        dxy_s = px[dxy_code].dropna()
        if len(dxy_s) >= 200:
            dxy_ma200 = float(dxy_s.tail(200).mean())
            dxy_trend = 1.0 if float(dxy_s.iloc[-1]) > dxy_ma200 else -1.0

    df["macro_yc"] = yield_curve_slope
    df["macro_vix"] = vix_level
    df["macro_vix_regime"] = vix_regime
    df["macro_dxy_trend"] = dxy_trend

    # ── Composite score ───────────────────────────────────────────
    mom_z = (df["mom_12_1_z"].fillna(0) + df["mom_6_1_z"].fillna(0)) / 2
    trend_score = df["trend_ma200"] * 0.5

    macro_adj = pd.Series(0.0, index=df.index)
    if not np.isnan(yield_curve_slope) and yield_curve_slope < 0:
        macro_adj = df["asset_class"].apply(
            lambda ac: -0.3 if ac.startswith("equity") or ac == "stocks" else 0.2
        )

    df["composite_score"] = (mom_z + trend_score + macro_adj + vix_regime * 0.1).round(3)

    return df.sort_values("composite_score", ascending=False).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Asset scoring engine")
    parser.add_argument("--date", required=True, help="Score as-of date (YYYY-MM-DD)")
    parser.add_argument("--csv", default=str(HISTORY_CSV))
    args = parser.parse_args()

    universe = load_universe()
    prices = load_prices(args.csv)
    scores = compute_signals(prices, args.date, universe)

    if scores.empty:
        print("No scores computed — insufficient data.")
        sys.exit(1)

    row = scores.iloc[0]
    print(f"\n{'='*70}")
    print(f"  Asset Scores as of {args.date}")
    print(f"{'='*70}")
    yc = row["macro_yc"]
    vx = row["macro_vix"]
    print(f"  Yield Curve (10Y-2Y): {yc:.2f}%" if not np.isnan(yc) else "  Yield Curve: N/A")
    regime = "High" if row["macro_vix_regime"] < 0 else ("Low" if row["macro_vix_regime"] > 0 else "Normal")
    print(f"  VIX: {vx:.1f} ({regime})" if not np.isnan(vx) else "  VIX: N/A")
    print(f"  DXY Trend: {'Bullish' if row['macro_dxy_trend'] > 0 else 'Bearish'}")
    print(f"{'='*70}\n")

    display = ["etf", "asset_class", "close", "mom_12_1", "mom_6_1",
               "trend_ma200", "vol_20d", "composite_score"]
    print(scores[display].to_string(index=False, float_format="%.3f"))
    print()


if __name__ == "__main__":
    main()
