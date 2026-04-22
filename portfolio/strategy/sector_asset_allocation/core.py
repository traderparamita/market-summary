"""공통 유틸 — 데이터 로드, RS 계산, 백테스트, 성과 지표."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.market_source import load_wide_close

ROOT = Path(__file__).resolve().parents[3]

# ─────────────────────────────────────────────────────
# 설정: 섹터 페어 & 벤치마크
# ─────────────────────────────────────────────────────

# 5 GICS 페어 — 2011-04-01 KRX 공식 출시 이후 실시간 참조 가능
# (HEALTH/INDU 는 2015-07, COMM 은 2018-10 이후만 real-time → 제외)
SECTOR_PAIRS_5: list[tuple[str, str, str]] = [
    ("IX_KR_IT",      "SC_US_TECH",    "IT"),
    ("IX_KR_FIN",     "SC_US_FIN",     "FIN"),
    ("IX_KR_ENERGY",  "SC_US_ENERGY",  "ENERGY"),
    ("IX_KR_DISCR",   "SC_US_DISCR",   "DISCR"),
    ("IX_KR_STAPLES", "SC_US_STAPLES", "STAPLES"),
]

# 경제축 4쌍 (도메인 지식 기반: Growth / Value / Inflation / Defensive)
SECTOR_PAIRS_ECO4: list[tuple[str, str, str]] = [
    ("IX_KR_IT",      "SC_US_TECH",    "IT"),       # 성장 / Duration
    ("IX_KR_FIN",     "SC_US_FIN",     "FIN"),      # 가치 / Curve
    ("IX_KR_ENERGY",  "SC_US_ENERGY",  "ENERGY"),   # 인플레 / Commodity
    ("IX_KR_STAPLES", "SC_US_STAPLES", "STAPLES"),  # 방어 / 저베타
]

KOSPI_CODE = "EQ_KOSPI"
SP500_CODE = "EQ_SP500"
FX_USDKRW  = "FX_USDKRW"
FX_DXY     = "FX_DXY"

BACKTEST_START = "2011-04-01"  # KRX 5 섹터 지수 공식 출시일
LOOKBACK_MONTHS = [1, 3, 6]
COST_BPS = 30


# ─────────────────────────────────────────────────────
# 데이터 로딩
# ─────────────────────────────────────────────────────

def load_all_data(start: str = BACKTEST_START) -> pd.DataFrame:
    """백테스트 필요한 모든 코드를 wide format 으로 로드."""
    codes = (
        [p[0] for p in SECTOR_PAIRS_5]
        + [p[1] for p in SECTOR_PAIRS_5]
        + [KOSPI_CODE, SP500_CODE, FX_USDKRW, FX_DXY]
    )
    pivot = load_wide_close(start=start, codes=codes)
    return pivot


# ─────────────────────────────────────────────────────
# 수익/시그널 계산
# ─────────────────────────────────────────────────────

def log_return(px: pd.Series, as_of: pd.Timestamp, months: int) -> float | None:
    """as_of 기준 N개월 전 대비 로그수익."""
    data = px.loc[:as_of].dropna()
    if data.empty:
        return None
    target = as_of - pd.DateOffset(months=months)
    past = data[data.index <= target]
    if past.empty:
        return None
    start = float(past.iloc[-1])
    end = float(data.iloc[-1])
    if start <= 0 or end <= 0:
        return None
    return math.log(end / start)


def pct_return(px: pd.Series | None, as_of: pd.Timestamp, months: int) -> float | None:
    """단순 수익률."""
    if px is None or px.empty:
        return None
    data = px.loc[:as_of].dropna()
    if data.empty:
        return None
    target = as_of - pd.DateOffset(months=months)
    past = data[data.index <= target]
    if past.empty:
        return None
    start = float(past.iloc[-1])
    end = float(data.iloc[-1])
    if start <= 0:
        return None
    return end / start - 1.0


def compute_rs_list(pivot: pd.DataFrame, pairs: list[tuple[str, str, str]],
                    as_of: pd.Timestamp, lookbacks: list[int] = LOOKBACK_MONTHS) -> list[dict]:
    """페어별 RS = log(KR/과거KR) - log(US/과거US), 여러 룩백 평균."""
    rs_list = []
    for kr_code, us_code, label in pairs:
        if kr_code not in pivot.columns or us_code not in pivot.columns:
            continue
        diffs = []
        for m in lookbacks:
            kr = log_return(pivot[kr_code], as_of, m)
            us = log_return(pivot[us_code], as_of, m)
            if kr is not None and us is not None:
                diffs.append(kr - us)
        if not diffs:
            continue
        rs_list.append({
            "pair":  label,
            "kr":    kr_code,
            "us":    us_code,
            "rs":    sum(diffs) / len(diffs),
        })
    return rs_list


def compute_fx_tilt(pivot: pd.DataFrame, as_of: pd.Timestamp,
                    source: str = "usdkrw", lookback: int = 3,
                    scale: float = 0.03) -> float:
    """FX tilt ∈ [-1, +1]. positive = KR 편향 (KRW 약세 → KR 수출 유리)."""
    values = []
    if source in ("usdkrw", "both"):
        r = pct_return(pivot.get(FX_USDKRW), as_of, lookback)
        if r is not None:
            values.append(math.tanh(r / scale))
    if source in ("dxy", "both"):
        r = pct_return(pivot.get(FX_DXY), as_of, lookback)
        if r is not None:
            values.append(math.tanh(r / scale))
    return sum(values) / len(values) if values else 0.0


def next_month_return(pivot: pd.DataFrame, me: pd.Timestamp, code: str) -> float | None:
    """me 다음 월말까지의 수익률."""
    if code not in pivot.columns:
        return None
    data = pivot[code].dropna()
    data = data[data.index >= me]
    if len(data) < 2:
        return None
    start = float(data.iloc[0])
    next_me = me + pd.offsets.BusinessMonthEnd()
    until = data[data.index <= next_me]
    if len(until) < 2:
        return None
    return float(until.iloc[-1] / start - 1)


# ─────────────────────────────────────────────────────
# 백테스트 Config & 엔진
# ─────────────────────────────────────────────────────

@dataclass
class Config:
    name: str = "baseline"
    pairs: list[tuple[str, str, str]] | None = None   # None → SECTOR_PAIRS_5
    w_rs: float = 1.0
    w_fx: float = 0.0
    fx_source: str = "none"       # none / usdkrw / dxy / both
    tau: float = 0.02             # 임계값 (log-return diff)
    min_pairs: int = 3            # 최소 유효 페어 (작으면 skip)
    cost_bps: int = COST_BPS
    # 통화 기준 — KR 투자자 관점에서 US 투자 시 FX 처리
    #   "local"        : 각 시장 로컬 통화 기준 (기본, USD 투자자 관점 근사)
    #   "krw_unhedged" : KR 투자자 환오픈 — US 수익 = (1+SP500_USD)×(1+USDKRW변화)-1
    #   "krw_hedged"   : KR 투자자 환헤지 — US 수익 = SP500_USD - 월별 헤지비용
    base_currency: str = "local"
    hedge_cost_annual: float = 0.018  # 연 1.8% (≈ US-KR 금리차 평균), krw_hedged 시만 사용


def run_backtest(cfg: Config, pivot: pd.DataFrame) -> pd.DataFrame:
    pairs = cfg.pairs or SECTOR_PAIRS_5
    FX_SCALE_TO_RS = 0.02
    cost = cfg.cost_bps / 10_000
    monthly_hedge_cost = cfg.hedge_cost_annual / 12  # 월별 차감

    month_ends = pivot.resample("BME").last().index
    records: list[dict] = []
    prev_signal: str | None = None
    prev_state: str = "Neutral"

    for me in month_ends[:-1]:
        rs_list = compute_rs_list(pivot, pairs, me)
        if len(rs_list) < cfg.min_pairs:
            continue

        mean_rs = sum(r["rs"] for r in rs_list) / len(rs_list)
        fx_val = compute_fx_tilt(pivot, me, cfg.fx_source) if cfg.fx_source != "none" else 0.0

        agg = cfg.w_rs * mean_rs + cfg.w_fx * fx_val * FX_SCALE_TO_RS

        if agg > cfg.tau:
            signal = "KR"
        elif agg < -cfg.tau:
            signal = "US"
        else:
            signal = prev_state

        kr_ret_local = next_month_return(pivot, me, KOSPI_CODE)
        us_ret_local = next_month_return(pivot, me, SP500_CODE)
        if kr_ret_local is None or us_ret_local is None:
            continue

        # ── 통화 기준 변환 ─────────────────────────────
        # KOSPI 는 KRW-denominated → base_currency 와 무관하게 동일
        kr_ret = kr_ret_local
        fx_ret = next_month_return(pivot, me, FX_USDKRW)  # 양수 = KRW 약세 = US ETF 환익

        if cfg.base_currency == "krw_unhedged":
            if fx_ret is None:
                continue
            us_ret = (1 + us_ret_local) * (1 + fx_ret) - 1
        elif cfg.base_currency == "krw_hedged":
            us_ret = us_ret_local - monthly_hedge_cost
        else:  # "local"
            us_ret = us_ret_local

        blend_ret = 0.5 * kr_ret + 0.5 * us_ret

        if signal == "KR":
            base_r = kr_ret
        elif signal == "US":
            base_r = us_ret
        else:
            base_r = blend_ret

        tc = cost if (prev_signal is not None and signal != prev_signal) else 0.0
        strat_ret = base_r - tc
        prev_signal = signal
        prev_state = signal

        records.append({
            "as_of":    me.strftime("%Y-%m-%d"),
            "signal":   signal,
            "n_pairs":  len(rs_list),
            "mean_rs":  round(mean_rs, 5),
            "fx_tilt":  round(fx_val, 4),
            "agg":      round(agg, 5),
            "cost":     round(tc, 5),
            "kr_return":     round(kr_ret, 4),
            "us_return":     round(us_ret, 4),
            "blend_return":  round(blend_ret, 4),
            "strategy_return": round(strat_ret, 4),
        })
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────
# 성과 지표
# ─────────────────────────────────────────────────────

def perf(returns: pd.Series, label: str) -> dict:
    r = returns.dropna()
    if len(r) == 0:
        return {"label": label}
    cum = (1 + r).cumprod()
    total = float(cum.iloc[-1] - 1)
    n = len(r)
    ann_ret = (1 + total) ** (12 / n) - 1 if n > 0 else 0.0
    ann_vol = float(r.std() * math.sqrt(12))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    dd = cum / cum.cummax() - 1
    mdd = float(dd.min())
    win = float((r > 0).mean())
    return {
        "label":        label,
        "total_return": round(total, 4),
        "ann_return":   round(ann_ret, 4),
        "ann_vol":      round(ann_vol, 4),
        "sharpe":       round(sharpe, 2),
        "mdd":          round(mdd, 4),
        "win_rate":     round(win, 3),
        "n_months":     n,
    }


# ─────────────────────────────────────────────────────
# 자동 섹터 선택 — 상관 기반
# ─────────────────────────────────────────────────────

def compute_rs_timeseries(pivot: pd.DataFrame,
                          pairs: list[tuple[str, str, str]] | None = None,
                          lookback: int = 3) -> pd.DataFrame:
    """각 페어의 RS 시계열 (월말 기준)."""
    pairs = pairs or SECTOR_PAIRS_5
    month_ends = pivot.resample("BME").last().index
    data = {}
    for kr_code, us_code, label in pairs:
        if kr_code not in pivot.columns or us_code not in pivot.columns:
            continue
        series = []
        idx = []
        for me in month_ends:
            kr = log_return(pivot[kr_code], me, lookback)
            us = log_return(pivot[us_code], me, lookback)
            if kr is not None and us is not None:
                series.append(kr - us)
                idx.append(me)
        data[label] = pd.Series(series, index=idx)
    return pd.DataFrame(data).dropna()


def select_low_correlation_subset(pivot: pd.DataFrame, k: int = 4,
                                  pool: list[tuple[str, str, str]] | None = None) -> list[tuple[str, str, str]]:
    """Pool 에서 k 개 섹터 중 내부 상관 최소화하는 조합 선택."""
    from itertools import combinations
    pool = pool or SECTOR_PAIRS_5
    df_rs = compute_rs_timeseries(pivot, pool)

    labels = list(df_rs.columns)
    best_avg = float("inf")
    best_combo = None
    for combo in combinations(labels, k):
        sub_corr = df_rs[list(combo)].corr()
        mask = np.triu(np.ones_like(sub_corr, dtype=bool), k=1)
        avg = sub_corr.where(mask).stack().mean()
        if avg < best_avg:
            best_avg = avg
            best_combo = combo

    # combo 라벨 → pool 에서 페어 튜플 되살리기
    label_to_pair = {p[2]: p for p in pool}
    return [label_to_pair[lbl] for lbl in best_combo]
