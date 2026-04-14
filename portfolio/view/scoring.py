"""Asset scoring engine — Option A enhanced signals.

Loads history/market_data.csv, computes per-asset signals (momentum, trend,
volatility, reversal, nearness, RSI, MACD, Bollinger) plus market-level
overlays (VIX regime, breadth, yield curve, DXY), then derives a
regime-conditional composite score.

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
    """Momentum = price(t-skip) / price(t-lookback) - 1.

    skip=0 means use the latest price as the numerator.
    """
    if len(series) < lookback:
        return np.nan
    p_end = series.iloc[-skip] if skip > 0 else series.iloc[-1]
    p_start = series.iloc[-lookback]
    if p_start <= 0:
        return np.nan
    return float(p_end / p_start - 1)


def _cs_z(series: pd.Series) -> pd.Series:
    """Cross-sectional z-score."""
    m, std = series.mean(), series.std()
    if std and std > 0:
        return (series - m) / std
    return pd.Series(0.0, index=series.index)


# ─────────────────────────────────────────────────────────────
# 기술적 지표 계산 함수
# ─────────────────────────────────────────────────────────────

def _rsi(series: pd.Series, period: int = 14) -> float:
    """RSI(period) — returns latest value (0–100)."""
    if len(series) < period + 1:
        return np.nan
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).tail(period).mean()
    loss = (-delta.clip(upper=0)).tail(period).mean()
    if loss == 0:
        return 100.0
    rs = gain / loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def _macd_histogram(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    """MACD histogram = MACD line − Signal line.

    Positive = bullish momentum, negative = bearish.
    """
    if len(series) < slow + signal:
        return np.nan
    macd_line   = _ema(series, fast) - _ema(series, slow)
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return float(hist.iloc[-1])


def _bollinger_pct_b(series: pd.Series, period: int = 20, n_std: float = 2.0) -> float:
    """Bollinger %B = (price - lower band) / (upper - lower).

    0 = at lower band, 1 = at upper band, >1 = above upper (over-bought).
    """
    if len(series) < period:
        return np.nan
    tail = series.tail(period)
    mid  = tail.mean()
    std  = tail.std()
    if std == 0:
        return np.nan
    upper = mid + n_std * std
    lower = mid - n_std * std
    last  = float(series.iloc[-1])
    band_range = upper - lower
    if band_range == 0:
        return np.nan
    return float((last - lower) / band_range)


def _macd_crossover(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    """MACD 크로스오버 신호: +1(골든크로스) / -1(데드크로스) / 0(유지)."""
    if len(series) < slow + signal + 2:
        return 0.0
    macd_line   = _ema(series, fast) - _ema(series, slow)
    signal_line = _ema(macd_line, signal)
    hist        = macd_line - signal_line
    if len(hist) < 2:
        return 0.0
    prev_hist = float(hist.iloc[-2])
    curr_hist = float(hist.iloc[-1])
    if prev_hist <= 0 and curr_hist > 0:
        return 1.0   # 골든크로스
    if prev_hist >= 0 and curr_hist < 0:
        return -1.0  # 데드크로스
    return 0.0


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
        returns = series.pct_change().dropna()

        # ── Momentum signals ──────────────────────────────────────
        mom_12_1 = _safe_momentum(series, 252, 22)
        mom_6_1  = _safe_momentum(series, 126, 22)
        mom_3_1  = _safe_momentum(series, 66,  22)   # 3-1 month
        reversal = float(series.iloc[-1] / series.iloc[-22] - 1) if len(series) >= 22 else np.nan

        # Risk-adjusted momentum: mom_12_1 / annualised vol
        vol_12m = float(returns.tail(252).std() * np.sqrt(252)) if len(returns) >= 252 else np.nan
        mom_12_1_adj = (mom_12_1 / vol_12m) if (
            not np.isnan(mom_12_1) and vol_12m and vol_12m > 0
        ) else np.nan

        # ── Trend signals ─────────────────────────────────────────
        ma200 = float(series.tail(200).mean()) if len(series) >= 200 else float(series.mean())
        trend_ma200 = 1.0 if last_price > ma200 else 0.0

        ma50 = float(series.tail(50).mean()) if len(series) >= 50 else float(series.mean())
        trend_ma50 = 1.0 if last_price > ma50 else 0.0

        # 52-week nearness: how close to the recent high
        high_52w = float(series.tail(252).max()) if len(series) >= 252 else float(series.max())
        nearness_52w = (last_price / high_52w) if high_52w > 0 else np.nan

        # ── Volatility signals ────────────────────────────────────
        vol_20d = float(returns.tail(20).std() * np.sqrt(252)) if len(returns) >= 20 else np.nan
        vol_60d = float(returns.tail(60).std() * np.sqrt(252)) if len(returns) >= 60 else np.nan
        vol_ratio = (vol_20d / vol_60d) if (
            not np.isnan(vol_20d) and vol_60d and vol_60d > 0
        ) else np.nan

        # ── Technical signals (RSI / MACD / Bollinger) ────────────
        rsi_14        = _rsi(series, 14)
        macd_hist     = _macd_histogram(series)
        macd_cross    = _macd_crossover(series)
        bollinger_pct = _bollinger_pct_b(series, 20)

        # RSI signal: oversold(≤30) = +1, overbought(≥70) = -1, neutral = 0
        if not np.isnan(rsi_14):
            if rsi_14 <= 30:
                rsi_signal = 1.0    # 과매도 = 반등 기대
            elif rsi_14 >= 70:
                rsi_signal = -1.0   # 과매수 = 조정 경고
            else:
                rsi_signal = 0.0
        else:
            rsi_signal = np.nan

        # Bollinger signal: <0.2 = oversold (buy), >0.8 = overbought (sell)
        if not np.isnan(bollinger_pct):
            if bollinger_pct < 0.2:
                bb_signal = 1.0
            elif bollinger_pct > 0.8:
                bb_signal = -1.0
            else:
                bb_signal = 0.0
        else:
            bb_signal = np.nan

        records.append({
            "etf": etf,
            "asset_class": info["asset_class"],
            "indicator_code": code,
            "close": last_price,
            # Momentum
            "mom_12_1":     mom_12_1,
            "mom_6_1":      mom_6_1,
            "mom_3_1":      mom_3_1,
            "reversal":     reversal,
            "mom_12_1_adj": mom_12_1_adj,
            # Trend
            "trend_ma200":  trend_ma200,
            "trend_ma50":   trend_ma50,
            "nearness_52w": nearness_52w,
            # Volatility
            "vol_20d":   vol_20d,
            "vol_ratio": vol_ratio,
            # Technical (RSI / MACD / Bollinger)
            "rsi_14":        rsi_14,
            "rsi_signal":    rsi_signal,
            "macd_hist":     macd_hist,
            "macd_cross":    macd_cross,
            "bb_pct_b":      bollinger_pct,
            "bb_signal":     bb_signal,
        })

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # ── Cross-sectional z-scores ──────────────────────────────────
    for col in ["mom_12_1", "mom_6_1", "mom_3_1", "reversal",
                "mom_12_1_adj", "nearness_52w", "macd_hist"]:
        df[f"{col}_z"] = _cs_z(df[col])

    # ── Market-level signals ──────────────────────────────────────

    # VIX: level, MA20, direction, 1-month change
    vix_level = vix_ma20 = vix_1m_chg = vix_direction = np.nan
    vix_regime = 0.0
    vix_code = macro.get("vix")
    if vix_code and vix_code in px.columns:
        vix_s = px[vix_code].dropna()
        if not vix_s.empty:
            vix_level = float(vix_s.iloc[-1])
        if len(vix_s) >= 20:
            vix_ma20 = float(vix_s.tail(20).mean())
        if len(vix_s) >= 22:
            vix_1m_chg = float(vix_s.iloc[-1] / vix_s.iloc[-22] - 1)
        if not np.isnan(vix_level):
            vix_regime = -1.0 if vix_level > 25 else (1.0 if vix_level < 15 else 0.0)
        if not np.isnan(vix_level) and not np.isnan(vix_ma20):
            # -1 = rising (bad), +1 = falling (calm)
            vix_direction = -1.0 if vix_level > vix_ma20 else 1.0

    # Yield curve: 10Y - 2Y slope
    yield_curve_slope = np.nan
    yc = macro.get("yield_curve", {})
    if yc:
        long_code  = yc.get("long")
        short_code = yc.get("short")
        if long_code in px.columns and short_code in px.columns:
            ly = px[long_code].dropna()
            sy = px[short_code].dropna()
            if not ly.empty and not sy.empty:
                yield_curve_slope = float(ly.iloc[-1] - sy.iloc[-1])

    # DXY: long-term trend + 3-month change
    dxy_trend = 0.0
    dxy_3m_chg = np.nan
    dxy_code = macro.get("dxy")
    if dxy_code and dxy_code in px.columns:
        dxy_s = px[dxy_code].dropna()
        if len(dxy_s) >= 200:
            dxy_ma200 = float(dxy_s.tail(200).mean())
            dxy_trend = 1.0 if float(dxy_s.iloc[-1]) > dxy_ma200 else -1.0
        if len(dxy_s) >= 66:
            dxy_3m_chg = float(dxy_s.iloc[-1] / dxy_s.iloc[-66] - 1)

    # Market breadth (using all assets in the universe)
    breadth_ma200 = float((df["trend_ma200"] == 1.0).mean())
    breadth_ma50  = float((df["trend_ma50"]  == 1.0).mean())
    breadth_3m_pos = float((df["mom_3_1"].fillna(0) > 0).mean())

    # ── Price-based regime (from VIX + breadth) ───────────────────
    if (not np.isnan(vix_level) and vix_level > 25) or breadth_ma200 < 0.4:
        market_regime = "RiskOFF"
    elif (not np.isnan(vix_level) and vix_level < 15) and breadth_ma200 > 0.65:
        market_regime = "RiskON"
    else:
        market_regime = "Neutral"

    # ── Attach market-level signals to every row ──────────────────
    df["macro_yc"]              = yield_curve_slope
    df["macro_vix"]             = vix_level
    df["macro_vix_ma20"]        = vix_ma20
    df["macro_vix_1m_chg"]      = vix_1m_chg
    df["macro_vix_direction"]   = vix_direction
    df["macro_vix_regime"]      = vix_regime
    df["macro_dxy_trend"]       = dxy_trend
    df["macro_dxy_3m_chg"]      = dxy_3m_chg
    df["macro_breadth_ma200"]   = breadth_ma200
    df["macro_breadth_ma50"]    = breadth_ma50
    df["macro_breadth_3m_pos"]  = breadth_3m_pos
    df["market_regime"]         = market_regime

    # ── Regime-conditional composite score ───────────────────────

    # Yield curve adjustment: inverted curve → penalise equities
    macro_adj = pd.Series(0.0, index=df.index)
    if not np.isnan(yield_curve_slope) and yield_curve_slope < 0:
        macro_adj = df["asset_class"].apply(
            lambda ac: -0.3 if (ac.startswith("equity") or ac == "stocks") else 0.2
        )

    # Composite sub-components
    mom_z = (
        df["mom_12_1_z"].fillna(0) * 1.0 +
        df["mom_6_1_z"].fillna(0)  * 0.8 +
        df["mom_3_1_z"].fillna(0)  * 0.6
    ) / 2.4

    trend_score    = df["trend_ma200"] * 0.7 + df["trend_ma50"] * 0.3
    nearness_z_cs  = df["nearness_52w_z"].fillna(0)
    reversal_z_cs  = df["reversal_z"].fillna(0)
    mom_adj_z_cs   = df["mom_12_1_adj_z"].fillna(0)
    macd_z_cs      = df["macd_hist_z"].fillna(0)

    # RSI/BB 역방향 신호 (과매도=매수 / 과매수=매도) — 레짐에 따라 가중치 조절
    rsi_signal_cs  = df["rsi_signal"].fillna(0)
    bb_signal_cs   = df["bb_signal"].fillna(0)
    # MACD 크로스오버 (순방향)
    macd_cross_cs  = df["macd_cross"].fillna(0)

    # 기술적 신호 합성 (Bollinger + RSI 평균)
    tech_contrarian = (rsi_signal_cs + bb_signal_cs) / 2.0

    vol_penalty = df["vol_ratio"].apply(
        lambda x: -0.25 if (not np.isnan(x) and x > 1.3) else 0.0
    )

    if market_regime == "RiskOFF":
        # Defence: trend dominates, momentum discounted, expanding vol heavily penalised
        # RSI/BB 역발상 신호 비중 소폭 추가 (바닥 매수 기회)
        composite = (
            trend_score      * 1.5  +
            mom_z            * 0.5  +
            nearness_z_cs    * 0.1  +
            vol_penalty      * 2.0  +
            tech_contrarian  * 0.2  +  # 과매도 신호 소폭 반영
            macd_cross_cs    * 0.1  +
            macro_adj
        )
    elif market_regime == "RiskON":
        # Offence: momentum + breakouts lead, trend confirms
        # MACD 추세 추종 신호 강화
        composite = (
            mom_z          * 1.5  +
            trend_score    * 0.8  +
            nearness_z_cs  * 0.3  +
            mom_adj_z_cs   * 0.3  +
            macd_z_cs      * 0.2  +  # MACD 모멘텀 추가
            macd_cross_cs  * 0.15 +  # 크로스오버 신호
            vix_regime     * 0.1  +
            macro_adj
        )
    else:  # Neutral — balanced weighting
        composite = (
            mom_z            * 1.0  +
            trend_score      * 1.0  +
            nearness_z_cs    * 0.2  +
            reversal_z_cs    * -0.1 +   # small contrarian discount
            vol_penalty               +
            macd_z_cs        * 0.15 +  # MACD 신호 (중립 구간 보조)
            tech_contrarian  * 0.1  +  # 기술적 역발상
            vix_regime       * 0.1  +
            macro_adj
        )

    df["composite_score"] = composite.round(3)

    # ── B1. Sentiment score (-100 to +100) ───────────────────────
    # Components: VIX regime + breadth + avg nearness
    breadth_norm = float(np.clip((breadth_ma200 - 0.50) / 0.15, -1, 1))

    avg_nearness = float(df["nearness_52w"].dropna().mean()) if not df["nearness_52w"].dropna().empty else 0.875
    nearness_norm = float(np.clip((avg_nearness - 0.875) / 0.075, -1, 1))

    vix_component = float(vix_regime) if not np.isnan(vix_regime) else 0.0

    # Weighted composite → scale to -100..+100
    sentiment_raw = vix_component * 0.40 + breadth_norm * 0.35 + nearness_norm * 0.25
    sentiment_score = round(float(sentiment_raw) * 100)

    if sentiment_score <= -60:
        sentiment_label = "Extreme Fear"
    elif sentiment_score <= -20:
        sentiment_label = "Fear"
    elif sentiment_score <= 20:
        sentiment_label = "Neutral"
    elif sentiment_score <= 60:
        sentiment_label = "Greed"
    else:
        sentiment_label = "Extreme Greed"

    df["sentiment_score"] = sentiment_score
    df["sentiment_label"] = sentiment_label

    # ── B2. Regime duration (VIX-based proxy) ────────────────────
    regime_duration = 0
    regime_since: str | None = None

    if vix_code and vix_code in px.columns:
        vix_s = px[vix_code].dropna()

        def _regime_from_vix(v: float) -> str:
            if v > 25:
                return "RiskOFF"
            if v < 15:
                return "RiskON"
            return "Neutral"

        # Walk backwards from target date
        dates_rev = vix_s.index[::-1]
        for d in dates_rev:
            if _regime_from_vix(float(vix_s[d])) == market_regime:
                regime_duration += 1
            else:
                regime_since = d.strftime("%Y-%m-%d")
                break

    df["regime_duration"] = regime_duration
    df["regime_since"] = regime_since if regime_since else "—"

    return df.sort_values("composite_score", ascending=False).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Asset scoring engine")
    parser.add_argument("--date", required=True, help="Score as-of date (YYYY-MM-DD)")
    parser.add_argument("--csv", default=str(HISTORY_CSV))
    args = parser.parse_args()

    universe = load_universe()
    prices   = load_prices(args.csv)
    scores   = compute_signals(prices, args.date, universe)

    if scores.empty:
        print("No scores computed — insufficient data.")
        sys.exit(1)

    row = scores.iloc[0]
    print(f"\n{'='*70}")
    print(f"  Asset Scores as of {args.date}")
    print(f"{'='*70}")

    yc  = row["macro_yc"]
    vx  = row["macro_vix"]
    v1m = row["macro_vix_1m_chg"]
    bm  = row["macro_breadth_ma200"]

    print(f"  Market Regime : {row['market_regime']}")
    print(f"  Yield Curve   : {yc:.2f}%" if not np.isnan(yc) else "  Yield Curve   : N/A")
    print(f"  VIX           : {vx:.1f}  (1M: {v1m:+.1%})" if not np.isnan(vx) else "  VIX           : N/A")
    print(f"  Breadth MA200 : {bm:.0%}" if not np.isnan(bm) else "  Breadth MA200 : N/A")
    print(f"{'='*70}\n")

    display = ["etf", "asset_class", "close",
               "mom_12_1", "mom_6_1", "mom_3_1",
               "trend_ma200", "trend_ma50", "nearness_52w",
               "vol_ratio", "composite_score"]
    print(scores[display].to_string(index=False, float_format="%.3f"))
    print()


if __name__ == "__main__":
    main()
