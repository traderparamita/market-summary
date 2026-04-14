"""Signal validation framework — Forward Return IC / Hit Rate / Walk-Forward.

Usage:
    from portfolio.backtest_signals import validate_signal, walk_forward_validate
"""

from __future__ import annotations

import warnings
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=RuntimeWarning)


# ─────────────────────────────────────────────────────────────
# 1. 단일 신호 검증
# ─────────────────────────────────────────────────────────────

def validate_signal(
    signal: pd.Series,
    target_returns: pd.Series,
    periods: list[int] = (5, 21, 63),
    min_obs: int = 30,
) -> pd.DataFrame:
    """Forward return IC / Hit Rate / t-stat for a single signal.

    Args:
        signal: 날짜 인덱스 신호 시리즈 (임의 스케일 가능)
        target_returns: 해당 자산 일별 수익률 시리즈
        periods: 검증할 선행 기간 (거래일 수)
        min_obs: 최소 유효 관측 수

    Returns:
        DataFrame with columns [period, IC_spearman, hit_rate, t_stat, n_obs, is_valid]
    """
    results = []
    for n in periods:
        fwd = target_returns.rolling(n).sum().shift(-n)
        aligned = pd.concat([signal, fwd], axis=1).dropna()
        aligned.columns = ["sig", "fwd"]

        n_obs = len(aligned)
        if n_obs < min_obs:
            results.append({
                "period": n, "IC_spearman": np.nan,
                "hit_rate": np.nan, "t_stat": np.nan,
                "n_obs": n_obs, "is_valid": False,
            })
            continue

        ic, p_val = stats.spearmanr(aligned["sig"], aligned["fwd"])
        hit = float((np.sign(aligned["sig"]) == np.sign(aligned["fwd"])).mean())
        t = ic * np.sqrt((n_obs - 2) / max(1 - ic**2, 1e-8))
        is_valid = abs(ic) >= 0.05 and hit >= 0.55 and abs(t) >= 1.96

        results.append({
            "period": n, "IC_spearman": round(ic, 4),
            "hit_rate": round(hit, 4), "t_stat": round(t, 3),
            "n_obs": n_obs, "is_valid": is_valid,
        })
    return pd.DataFrame(results)


def validate_multi_signal(
    signals_df: pd.DataFrame,
    target_returns: pd.Series,
    periods: list[int] = (5, 21, 63),
) -> pd.DataFrame:
    """여러 신호를 한 번에 검증.

    Returns:
        MultiIndex DataFrame — (signal_name, period) × 지표
    """
    rows = []
    for col in signals_df.columns:
        v = validate_signal(signals_df[col], target_returns, periods)
        v.insert(0, "signal", col)
        rows.append(v)
    return pd.concat(rows, ignore_index=True).set_index(["signal", "period"])


# ─────────────────────────────────────────────────────────────
# 2. Walk-Forward 엔진
# ─────────────────────────────────────────────────────────────

def walk_forward_validate(
    signal_fn,
    prices: pd.DataFrame,
    target_col: str,
    train_years: int = 3,
    test_years: int = 1,
    start_year: int = 2013,
    end_year: int = 2024,
    period_days: int = 21,
) -> pd.DataFrame:
    """Walk-forward out-of-sample validation.

    Args:
        signal_fn: callable(prices_df, date) → pd.Series (signal values per asset)
        prices: wide DataFrame (date × asset)
        target_col: 검증 대상 자산 코드
        train_years / test_years: 훈련/테스트 기간
        start_year / end_year: 검증 범위

    Returns:
        DataFrame with OOS IC / Hit Rate per test window
    """
    records = []
    for test_start_yr in range(start_year, end_year, test_years):
        train_end   = pd.Timestamp(f"{test_start_yr}-01-01")
        test_end    = pd.Timestamp(f"{test_start_yr + test_years}-01-01")
        train_start = train_end - pd.DateOffset(years=train_years)

        test_prices = prices[(prices.index >= train_end) & (prices.index < test_end)]
        if len(test_prices) < 60:
            continue

        signals_list = []
        for d in test_prices.index[::21]:  # 월 1회
            try:
                s = signal_fn(prices[prices.index <= d], str(d.date()))
                if isinstance(s, (float, int)):
                    signals_list.append((d, s))
                elif isinstance(s, pd.Series) and target_col in s.index:
                    signals_list.append((d, s[target_col]))
            except Exception:
                pass

        if len(signals_list) < 5:
            continue

        sig_series = pd.Series(
            {d: v for d, v in signals_list}, name="signal"
        ).sort_index()
        ret_series = prices[target_col].pct_change()
        v = validate_signal(sig_series, ret_series, periods=[period_days])
        v["window"] = f"{test_start_yr}"
        records.append(v)

    if not records:
        return pd.DataFrame()
    return pd.concat(records, ignore_index=True)


# ─────────────────────────────────────────────────────────────
# 3. 레짐별 신호 성과 분해
# ─────────────────────────────────────────────────────────────

def regime_conditional_ic(
    signal: pd.Series,
    target_returns: pd.Series,
    regime: pd.Series,
    period: int = 21,
) -> pd.DataFrame:
    """레짐별 IC를 분리 계산.

    Args:
        regime: 날짜 인덱스, 값 예) 'RiskON' / 'Neutral' / 'RiskOFF'

    Returns:
        DataFrame: regime × [IC, hit_rate, n_obs]
    """
    fwd = target_returns.rolling(period).sum().shift(-period)
    df = pd.concat([signal, fwd, regime], axis=1).dropna()
    df.columns = ["sig", "fwd", "regime"]

    rows = []
    for reg, grp in df.groupby("regime"):
        if len(grp) < 15:
            rows.append({"regime": reg, "IC": np.nan, "hit_rate": np.nan, "n_obs": len(grp)})
            continue
        ic, _ = stats.spearmanr(grp["sig"], grp["fwd"])
        hit = float((np.sign(grp["sig"]) == np.sign(grp["fwd"])).mean())
        rows.append({"regime": reg, "IC": round(ic, 4), "hit_rate": round(hit, 4), "n_obs": len(grp)})
    return pd.DataFrame(rows).set_index("regime")


# ─────────────────────────────────────────────────────────────
# 4. 성과 요약 출력
# ─────────────────────────────────────────────────────────────

def print_validation_report(name: str, df: pd.DataFrame) -> None:
    print(f"\n{'='*60}")
    print(f"  Signal: {name}")
    print(f"{'='*60}")
    print(df.to_string())
    valid = df["is_valid"].sum() if "is_valid" in df.columns else "N/A"
    print(f"\n  → Valid periods: {valid}/{len(df)}")
    print()


if __name__ == "__main__":
    # 사용 예시
    np.random.seed(42)
    dates = pd.date_range("2015-01-01", "2024-12-31", freq="B")
    signal = pd.Series(np.random.randn(len(dates)), index=dates)
    returns = pd.Series(np.random.randn(len(dates)) * 0.01, index=dates)

    result = validate_signal(signal, returns)
    print_validation_report("Sample Signal", result)
