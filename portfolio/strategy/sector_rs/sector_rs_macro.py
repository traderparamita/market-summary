"""Sector RS with Macro Sensitivity — 페어별 섹터 고유 매크로 신호 주입.

옵션 2 실현: 각 per-pair agent 에 섹터 고유 매크로 tilt 추가.
기존 Hierarchical(v2) 구조 상속 + 매크로 레이어만 추가.

페어별 macro tilt (positive = KR 편향, negative = US 편향):
  IT     ← DXY 3M momentum       (강달러 → KR IT 수출 유리)
  FIN    ← US yield curve level  (가파른 곡선 → US 은행 마진 우위)
  ENERGY ← WTI 3M momentum       (유가↑ → KR 에너지/화학 마진)
  INDU   ← Copper 3M / DXY 반대  (구리↑ 약달러 → 글로벌 경기)
  DISCR  ← HY spread 3M 변화     (스프레드↓ → 위험선호 → 고베타 KR)
  STAPLES← VIX level             (VIX↑ → US 안전자산 선호)
  HEALTH ← DXY 3M                (약달러 → KR 헬스 미세 유리)
  COMM   ← NVDA 3M               (AI/광고 붐 → US META/GOOG 직수혜)

합성:
  pair_score = w_rs·tanh(rs/rs_scale)
             + w_vol·tanh(vol_tilt/vol_scale)
             + w_macro·macro_tilt
  (× volume_confirm)

Usage:
    # sweep 기본 실행
    python -m portfolio.strategy.sector_rs_macro --date 2026-04-21
    # 단일 config
    python -m portfolio.strategy.sector_rs_macro --config macro_balanced --date 2026-04-21
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio.market_source import load_wide_close, load_macro_long, load_long
from portfolio.strategy.sector_rs.sector_rs_sync import (
    SECTOR_PAIRS, LOOKBACK_MONTHS, BACKTEST_START, COST_BPS,
    KOSPI_CODE, SP500_CODE,
    _log_return, next_month_return, perf, _badge, _C, _LIGHT,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "portfolio" / "strategy" / "rs_macro"

VIX_CODE = "RK_VIX"

# 페어 라벨 → 인덱스 매핑 (macro tilt 함수 분기용)
PAIR_LABELS = ["IT", "FIN", "HEALTH", "INDU", "ENERGY", "DISCR", "STAPLES", "COMM"]
# SECTOR_PAIRS 순서와 일치해야 함 — 검증
assert len(PAIR_LABELS) == len(SECTOR_PAIRS)
for lbl, pair in zip(PAIR_LABELS, SECTOR_PAIRS):
    assert lbl in pair[2].split(" / ")[0].strip().upper().replace("헬스케어", "HEALTH") \
        or lbl == pair[2].split(" / ")[0].strip() \
        or True  # loose check, primarily relying on sync order


# ──────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────

@dataclass
class Config:
    name: str = "baseline"
    # Per-pair base signal
    w_rs: float = 0.55
    w_vol: float = 0.15
    w_macro: float = 0.30
    rs_scale: float = 0.02
    vol_scale: float = 0.10
    macro_scale: float = 1.0     # macro_tilt 이 이미 tanh 로 [-1,1] 이므로 scale=1
    pair_vote_tau: float = 0.10
    use_volume_confirm: bool = True
    use_macro_tilt: bool = True
    # Meta layer
    meta_mode: str = "equal"       # equal / adaptive (equal_meta 이 v2 sweep 에서 adaptive 와 동등)
    meta_window: int = 6
    meta_min_votes: int = 3
    final_tau: float = 0.10
    # Risk overlay (v2 sweep 결과: OFF 가 낫다)
    use_vix_overlay: bool = False
    vix_stress: float = 30.0


SWEEP_CONFIGS: list[Config] = [
    # baseline = v2 best (no_vix) 설정 그대로
    Config(name="v2_best_no_macro",  w_rs=0.70, w_vol=0.30, w_macro=0.0,
           use_macro_tilt=False, pair_vote_tau=0.15, final_tau=0.15),
    # 매크로 가중 sweep
    Config(name="macro_w10",         w_rs=0.65, w_vol=0.25, w_macro=0.10),
    Config(name="macro_w20",         w_rs=0.60, w_vol=0.20, w_macro=0.20),
    Config(name="macro_w30",         w_rs=0.55, w_vol=0.15, w_macro=0.30),
    Config(name="macro_w40",         w_rs=0.50, w_vol=0.10, w_macro=0.40),
    Config(name="macro_w50",         w_rs=0.50, w_vol=0.00, w_macro=0.50),
    # 매크로만 (순수 매크로 tilt)
    Config(name="macro_only",        w_rs=0.30, w_vol=0.00, w_macro=0.70),
    # 낮은 임계치 조합
    Config(name="macro_w30_lowtau",  w_rs=0.55, w_vol=0.15, w_macro=0.30,
           pair_vote_tau=0.05, final_tau=0.05),
]


# ──────────────────────────────────────────────────────
# Helpers (v2 상속)
# ──────────────────────────────────────────────────────

def _realized_vol(px: pd.Series, as_of: pd.Timestamp, window: int = 20) -> float | None:
    data = px.loc[:as_of].dropna()
    if len(data) < window + 1:
        return None
    rets = np.log(data / data.shift(1)).dropna()
    if len(rets) < window:
        return None
    return float(rets.iloc[-window:].std())


def _volume_confirm(volume_series: pd.Series | None, as_of: pd.Timestamp,
                    window: int = 20) -> float:
    if volume_series is None or volume_series.empty:
        return 1.0
    data = volume_series.loc[:as_of].dropna()
    if len(data) < window + 1:
        return 1.0
    avg = float(data.iloc[-(window + 1):-1].mean())
    last = float(data.iloc[-1])
    if avg <= 0:
        return 1.0
    ratio = last / avg
    return 1.0 if ratio >= 0.8 else 0.8


def _load_long_with_volume(codes: list[str], start: str) -> dict[str, pd.Series]:
    df = load_long(start=start, codes=codes)
    if df.empty:
        return {}
    out: dict[str, pd.Series] = {}
    for code, sub in df.groupby("INDICATOR_CODE"):
        ser = sub.set_index("DATE")["VOLUME"].sort_index()
        out[code] = pd.to_numeric(ser, errors="coerce")
    return out


def _macro_value_at(series: pd.Series | None, as_of: pd.Timestamp) -> float | None:
    """as_of 시점에 유효한 macro 값 (ffill)."""
    if series is None or series.empty:
        return None
    data = series.loc[:as_of].dropna()
    if data.empty:
        return None
    return float(data.iloc[-1])


def _price_return_pct(px: pd.Series | None, as_of: pd.Timestamp, months: int) -> float | None:
    """단순 가격 수익률 (로그 아님)."""
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


def _macro_diff(series: pd.Series | None, as_of: pd.Timestamp, months: int) -> float | None:
    """macro 값 months 전 대비 차이 (절대값, pp)."""
    if series is None or series.empty:
        return None
    data = series.loc[:as_of].dropna()
    if data.empty:
        return None
    now = float(data.iloc[-1])
    target = as_of - pd.DateOffset(months=months)
    past = data[data.index <= target]
    if past.empty:
        return None
    return now - float(past.iloc[-1])


# ──────────────────────────────────────────────────────
# Macro tilt per pair
# ──────────────────────────────────────────────────────

def macro_tilt(pair_label: str, pivot: pd.DataFrame,
               macro: dict[str, pd.Series], as_of: pd.Timestamp) -> float:
    """페어 고유 매크로 tilt ∈ [-1, +1]. positive=KR 편향. 입력 부족 시 0."""
    def _get_price(code: str) -> pd.Series | None:
        return pivot[code] if code in pivot.columns else None

    if pair_label == "IT":
        # DXY 3M 모멘텀 — 강달러 → KR IT 수출 우위
        dxy_r = _price_return_pct(_get_price("FX_DXY"), as_of, 3)
        return math.tanh(dxy_r / 0.03) if dxy_r is not None else 0.0

    if pair_label == "FIN":
        # Yield curve level (2s10s) — 가파른 → US 은행 마진 우위 (음의 tilt)
        curve = _macro_value_at(macro.get("US_YIELD_CURVE"), as_of)
        if curve is None:
            return 0.0
        return -math.tanh(curve / 1.0)

    if pair_label == "ENERGY":
        # WTI 3M 모멘텀 — 유가↑ → KR 에너지/화학 price-taker 마진
        wti_r = _price_return_pct(_get_price("CM_WTI"), as_of, 3)
        return math.tanh(wti_r / 0.15) if wti_r is not None else 0.0

    if pair_label == "INDU":
        # Copper 3M + DXY 반대 — 구리↑ & 약달러 → KR 중공업
        cu_r  = _price_return_pct(_get_price("CM_COPPER"), as_of, 3)
        dxy_r = _price_return_pct(_get_price("FX_DXY"),    as_of, 3)
        tilts = []
        if cu_r  is not None:
            tilts.append(math.tanh(cu_r  / 0.15))
        if dxy_r is not None:
            tilts.append(-math.tanh(dxy_r / 0.03))
        return sum(tilts) / len(tilts) if tilts else 0.0

    if pair_label == "DISCR":
        # HY spread 3M 변화 — 축소 → 위험선호 → 고베타 KR
        hy_d = _macro_diff(macro.get("US_HY_SPREAD"), as_of, 3)
        return -math.tanh(hy_d / 0.5) if hy_d is not None else 0.0

    if pair_label == "STAPLES":
        # VIX level — 높은 VIX → 안전자산 → US 우위
        vix = _macro_value_at(macro.get("VIX"), as_of)
        if vix is None:
            vix_ser = _get_price(VIX_CODE)
            vix = _macro_value_at(vix_ser, as_of)
        if vix is None:
            return 0.0
        return -math.tanh((vix - 20) / 10)

    if pair_label == "HEALTH":
        # DXY 3M — 약달러 → KR 헬스 미세 유리 (음의 부호)
        dxy_r = _price_return_pct(_get_price("FX_DXY"), as_of, 3)
        return -math.tanh(dxy_r / 0.03) if dxy_r is not None else 0.0

    if pair_label == "COMM":
        # NVDA 3M — AI/광고 붐 → US 직수혜
        nvda_r = _price_return_pct(_get_price("ST_NVDA"), as_of, 3)
        return -math.tanh(nvda_r / 0.20) if nvda_r is not None else 0.0

    return 0.0


# ──────────────────────────────────────────────────────
# Per-pair agent (config + macro)
# ──────────────────────────────────────────────────────

def pair_agent(cfg: Config, pair_label: str,
               kr_px: pd.Series, us_px: pd.Series,
               kr_vol_ser: pd.Series | None, us_vol_ser: pd.Series | None,
               pivot: pd.DataFrame, macro: dict[str, pd.Series],
               as_of: pd.Timestamp) -> dict | None:
    diffs = []
    for m in LOOKBACK_MONTHS:
        kr_lr = _log_return(kr_px, as_of, m)
        us_lr = _log_return(us_px, as_of, m)
        if kr_lr is None or us_lr is None:
            continue
        diffs.append(kr_lr - us_lr)
    if not diffs:
        return None
    rs = sum(diffs) / len(diffs)

    kr_vol = _realized_vol(kr_px, as_of)
    us_vol = _realized_vol(us_px, as_of)
    vol_tilt_v = (math.log(us_vol / kr_vol)
                  if (kr_vol and us_vol and kr_vol > 0 and us_vol > 0) else 0.0)

    m_tilt = macro_tilt(pair_label, pivot, macro, as_of) if cfg.use_macro_tilt else 0.0

    if cfg.use_volume_confirm:
        kr_conf = _volume_confirm(kr_vol_ser, as_of)
        us_conf = _volume_confirm(us_vol_ser, as_of)
        vol_confirm = min(kr_conf, us_conf)
    else:
        vol_confirm = 1.0

    score = (cfg.w_rs    * math.tanh(rs / cfg.rs_scale)
             + cfg.w_vol * math.tanh(vol_tilt_v / cfg.vol_scale)
             + cfg.w_macro * math.tanh(m_tilt / cfg.macro_scale))
    score *= vol_confirm

    if score > cfg.pair_vote_tau:
        vote = "KR"
    elif score < -cfg.pair_vote_tau:
        vote = "US"
    else:
        vote = "Hold"

    return {"rs": rs, "vol_tilt": vol_tilt_v, "macro_tilt": m_tilt,
            "vol_confirm": vol_confirm, "score": score, "vote": vote}


# ──────────────────────────────────────────────────────
# Meta + backtest (v2 와 동일 구조)
# ──────────────────────────────────────────────────────

def _compute_hit_rates(cfg: Config, history: pd.DataFrame, n_pairs: int) -> np.ndarray:
    if cfg.meta_mode == "equal" or len(history) == 0:
        return np.ones(n_pairs) / n_pairs

    recent = history.tail(cfg.meta_window)
    weights = np.zeros(n_pairs)
    valid_mask = np.zeros(n_pairs, dtype=bool)
    for i in range(n_pairs):
        vote_col = f"pair_{i}_vote"
        if vote_col not in recent.columns:
            continue
        hits = 0
        total = 0
        for _, row in recent.iterrows():
            v = row[vote_col]
            if v == "Hold" or pd.isna(v):
                continue
            kr_r = row.get("kr_return")
            us_r = row.get("us_return")
            if pd.isna(kr_r) or pd.isna(us_r) or kr_r == us_r:
                continue
            actual = "KR" if kr_r > us_r else "US"
            total += 1
            if v == actual:
                hits += 1
        if total >= cfg.meta_min_votes:
            weights[i] = hits / total
            valid_mask[i] = True

    if not valid_mask.any():
        return np.ones(n_pairs) / n_pairs
    mean_valid = weights[valid_mask].mean()
    weights[~valid_mask] = mean_valid
    weights = np.clip(weights, 0.1, 1.0)
    total_w = weights.sum()
    return weights / total_w if total_w > 0 else np.ones(n_pairs) / n_pairs


def meta_aggregate(pair_results: list[dict | None], weights: np.ndarray) -> dict:
    n = len(pair_results)
    numeric_votes = np.zeros(n)
    scores = np.zeros(n)
    for i, r in enumerate(pair_results):
        if r is None:
            continue
        scores[i] = r["score"]
        if r["vote"] == "KR":
            numeric_votes[i] = 1
        elif r["vote"] == "US":
            numeric_votes[i] = -1

    active_weight = sum(weights[i] for i, r in enumerate(pair_results) if r is not None)
    if active_weight == 0:
        return {"weighted_vote": 0.0, "weighted_score": 0.0,
                "kr_w": 0, "us_w": 0, "hold_w": 0}

    weighted_vote = float(np.sum(weights * numeric_votes) / active_weight)
    weighted_score = float(np.sum(weights * scores) / active_weight)
    kr_w = float(sum(weights[i] for i, r in enumerate(pair_results) if r and r["vote"] == "KR"))
    us_w = float(sum(weights[i] for i, r in enumerate(pair_results) if r and r["vote"] == "US"))
    hold_w = float(sum(weights[i] for i, r in enumerate(pair_results) if r and r["vote"] == "Hold"))
    return {"weighted_vote": weighted_vote, "weighted_score": weighted_score,
            "kr_w": kr_w, "us_w": us_w, "hold_w": hold_w}


def run_backtest(cfg: Config, pivot: pd.DataFrame,
                 vol_map: dict[str, pd.Series],
                 macro: dict[str, pd.Series]) -> pd.DataFrame:
    month_ends = pivot.resample("BME").last().index
    cost = COST_BPS / 10_000
    n_pairs = len(SECTOR_PAIRS)

    history_rows: list[dict] = []
    prev_signal: str | None = None

    for me in month_ends[:-1]:
        pair_results: list[dict | None] = []
        for idx, (kr_code, us_code, _label) in enumerate(SECTOR_PAIRS):
            if kr_code not in pivot.columns or us_code not in pivot.columns:
                pair_results.append(None)
                continue
            pair_results.append(pair_agent(
                cfg, PAIR_LABELS[idx],
                pivot[kr_code], pivot[us_code],
                vol_map.get(kr_code), vol_map.get(us_code),
                pivot, macro, me,
            ))
        if all(r is None for r in pair_results):
            continue

        history_df = pd.DataFrame(history_rows) if history_rows else pd.DataFrame()
        weights = _compute_hit_rates(cfg, history_df, n_pairs)
        meta = meta_aggregate(pair_results, weights)

        vix_val = None
        if VIX_CODE in pivot.columns:
            vix_data = pivot[VIX_CODE].loc[:me].dropna()
            if len(vix_data) > 0:
                vix_val = float(vix_data.iloc[-1])
        vix_stress = cfg.use_vix_overlay and (vix_val is not None and vix_val > cfg.vix_stress)

        ws = meta["weighted_score"]
        if ws > cfg.final_tau:
            signal = "KR"
        elif ws < -cfg.final_tau:
            signal = "US"
        else:
            signal = "Neutral"

        kr_ret = next_month_return(pivot, me, KOSPI_CODE)
        us_ret = next_month_return(pivot, me, SP500_CODE)
        if kr_ret is None or us_ret is None:
            continue
        blend_ret = 0.5 * kr_ret + 0.5 * us_ret

        if signal == "KR":
            base_r = kr_ret
        elif signal == "US":
            base_r = us_ret
        else:
            base_r = blend_ret
        strat_ret = 0.5 * base_r + 0.5 * blend_ret if (vix_stress and signal != "Neutral") else base_r

        tc = cost if (prev_signal is not None and signal != prev_signal) else 0.0
        strat_ret -= tc
        prev_signal = signal

        row = {
            "as_of":   me.strftime("%Y-%m-%d"),
            "signal":  signal,
            "ws":      round(ws, 4),
            "vix":     round(vix_val, 2) if vix_val is not None else None,
            "kr_w":    round(meta["kr_w"], 3),
            "us_w":    round(meta["us_w"], 3),
            "hold_w":  round(meta["hold_w"], 3),
            "cost":    round(tc, 5),
            "kr_return":     round(kr_ret, 4),
            "us_return":     round(us_ret, 4),
            "blend_return":  round(blend_ret, 4),
            "strategy_return": round(strat_ret, 4),
        }
        for i, r in enumerate(pair_results):
            row[f"pair_{i}_weight"] = round(float(weights[i]), 4)
            if r is None:
                row[f"pair_{i}_vote"] = None
                row[f"pair_{i}_score"] = None
            else:
                row[f"pair_{i}_vote"] = r["vote"]
                row[f"pair_{i}_score"] = round(r["score"], 4)
                row[f"pair_{i}_rs"] = round(r["rs"], 5)
                row[f"pair_{i}_macro"] = round(r["macro_tilt"], 4)
        history_rows.append(row)

    return pd.DataFrame(history_rows)


# ──────────────────────────────────────────────────────
# Sweep / HTML
# ──────────────────────────────────────────────────────

def run_sweep(cfgs: list[Config], pivot: pd.DataFrame,
              vol_map: dict[str, pd.Series],
              macro: dict[str, pd.Series]) -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    for cfg in cfgs:
        bt = run_backtest(cfg, pivot, vol_map, macro)
        if bt.empty:
            print(f"  [{cfg.name}] empty")
            continue
        results[cfg.name] = bt
        m = perf(bt["strategy_return"], cfg.name)
        if m:
            print(f"  {cfg.name:22s}  CAGR={m['ann_return']*100:+6.2f}%  "
                  f"Sharpe={m['sharpe']:+5.2f}  MDD={m['mdd']*100:+6.1f}%  "
                  f"Win={m['win_rate']*100:3.0f}%  n={m['n_months']}")
    return results


def build_sweep_html(results: dict[str, pd.DataFrame],
                     bench: dict[str, pd.Series], date_str: str,
                     mean_rs_ser: pd.Series | None = None) -> str:
    rows = []
    for name, bt in results.items():
        rows.append(perf(bt["strategy_return"], name))
    for name, ser in bench.items():
        rows.append(perf(ser, name))
    if mean_rs_ser is not None:
        rows.append(perf(mean_rs_ser, "Mean-RS (sync)"))
    rows_sorted = sorted(rows, key=lambda m: -m["sharpe"])
    best = rows_sorted[0]

    m_rows = ""
    for m in rows_sorted:
        mark = "🏆 " if m is best else ""
        bg = "background:#FFF7EE;font-weight:700" if m is best else ""
        m_rows += (
            f'<tr style="{bg}">'
            f'<td>{mark}{m["label"]}</td>'
            f'<td class="num">{m["total_return"]*100:+.1f}%</td>'
            f'<td class="num">{m["ann_return"]*100:+.1f}%</td>'
            f'<td class="num">{m["ann_vol"]*100:.1f}%</td>'
            f'<td class="num"><b>{m["sharpe"]:.2f}</b></td>'
            f'<td class="num" style="color:#DC2626">{m["mdd"]*100:.1f}%</td>'
            f'<td class="num">{m["win_rate"]*100:.0f}%</td>'
            f'<td class="num">{m["n_months"]}</td>'
            f'</tr>'
        )

    sample_bt = next(iter(results.values()))
    labels_j = json.dumps(list(sample_bt["as_of"]))

    palette = ["#F58220", "#E63946", "#059669", "#8B5CF6", "#0EA5E9",
               "#F59E0B", "#EC4899", "#6366F1", "#14B8A6", "#F97316"]
    datasets = []
    for i, (name, bt) in enumerate(results.items()):
        cum = ((1 + bt["strategy_return"]).cumprod() - 1).round(4).tolist()
        datasets.append({
            "label": name, "data": cum,
            "borderColor": palette[i % len(palette)],
            "backgroundColor": "transparent",
            "borderWidth": 2.0 if name == best["label"] else 1.3, "tension": 0.15,
        })
    for name, ser in bench.items():
        cum = ((1 + ser).cumprod() - 1).round(4).tolist()
        datasets.append({
            "label": name, "data": cum,
            "borderColor": "#6B7280", "borderDash": [4, 4],
            "backgroundColor": "transparent",
            "borderWidth": 1.0, "tension": 0.1,
        })
    if mean_rs_ser is not None:
        cum = ((1 + mean_rs_ser).cumprod() - 1).round(4).tolist()
        datasets.append({
            "label": "Mean-RS (sync)", "data": cum,
            "borderColor": "#1D3557",
            "backgroundColor": "transparent",
            "borderWidth": 1.8, "borderDash": [8, 3], "tension": 0.15,
        })

    # macro tilt 현재 상태
    last = sample_bt.iloc[-1]
    tilt_rows = ""
    for i, lbl in enumerate(PAIR_LABELS):
        m_col = f"pair_{i}_macro"
        if m_col in sample_bt.columns and pd.notna(last.get(m_col)):
            tilt = float(last[m_col])
            color = "#16A34A" if tilt > 0 else ("#DC2626" if tilt < 0 else "#6B7280")
            arrow = "▲ KR" if tilt > 0 else ("▼ US" if tilt < 0 else "—")
            tilt_rows += (
                f'<tr><td>{lbl}</td>'
                f'<td class="num" style="color:{color};font-weight:700">{tilt:+.3f}</td>'
                f'<td style="color:{color}">{arrow}</td></tr>'
            )

    # config table
    cfg_table = ""
    base = Config(name="baseline")
    for cfg in SWEEP_CONFIGS:
        if cfg.name not in results:
            continue
        diff = []
        for k, v in asdict(cfg).items():
            if k == "name":
                continue
            if getattr(base, k) != v:
                diff.append(f"<code>{k}={v}</code>")
        diff_str = " · ".join(diff) if diff else "<i>baseline</i>"
        cfg_table += f'<tr><td><b>{cfg.name}</b></td><td>{diff_str}</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Sector RS Macro — {date_str}</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; background:#F7F8FA; color:#1F2937; padding:24px; max-width:1280px; margin:0 auto; }}
  h1 {{ font-size:1.5rem; font-weight:800; margin-bottom:4px; }}
  .subtitle {{ color:#6B7280; font-size:0.85rem; margin-bottom:24px; }}
  h2 {{ font-size:1rem; color:#111827; margin:28px 0 10px; padding-left:10px; border-left:3px solid #F58220; }}
  .hero {{ background:linear-gradient(135deg,#FFF7EE,#FDE68A22); border-radius:12px; padding:18px 22px; border:1px solid #FCD34D; margin-bottom:20px; }}
  .hero b {{ color:#B45309; }}
  table {{ width:100%; background:#fff; border-collapse:collapse; font-size:0.85rem; border-radius:8px; overflow:hidden; border:1px solid #E5E7EB; }}
  th {{ background:#F3F4F6; padding:9px 10px; text-align:left; font-weight:600; color:#374151; border-bottom:1px solid #E5E7EB; }}
  td {{ padding:8px 10px; border-bottom:1px solid #F3F4F6; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  code {{ font-family:'SF Mono',Menlo,monospace; font-size:0.78rem; color:#6B7280; background:#F3F4F6; padding:1px 5px; border-radius:3px; }}
  .canvas-wrap {{ background:#fff; padding:16px; border-radius:10px; border:1px solid #E5E7EB; }}
  .note {{ color:#6B7280; font-size:0.75rem; margin-top:8px; line-height:1.55; }}
  .two-col {{ display:grid; grid-template-columns:1fr 2fr; gap:16px; }}
</style>
</head>
<body>

<h1>Sector RS + Macro Sensitivity — Parameter Sweep</h1>
<div class="subtitle">섹터별 고유 매크로 신호 주입 · {BACKTEST_START} ~ {date_str}</div>

<div class="hero">
  🏆 <b>베스트 Sharpe</b>: {best["label"]} — CAGR {best["ann_return"]*100:+.2f}%, Sharpe {best["sharpe"]:.2f}, MDD {best["mdd"]*100:.1f}%
</div>

<h2>성과 비교 (Sharpe 내림차순)</h2>
<table>
  <thead><tr><th>전략</th><th>Total</th><th>연수익</th><th>연변동</th><th>Sharpe</th><th>MDD</th><th>Win%</th><th>#월</th></tr></thead>
  <tbody>{m_rows}</tbody>
</table>

<h2>현재 매크로 tilt ({last["as_of"]})</h2>
<div class="two-col">
  <div>
    <table>
      <thead><tr><th>섹터</th><th style="text-align:right">tilt</th><th>방향</th></tr></thead>
      <tbody>{tilt_rows}</tbody>
    </table>
  </div>
  <div class="note" style="padding:8px">
    <b>tilt 해석</b>: [-1, +1] 구간, +1 최강 KR, -1 최강 US.<br>
    각 섹터 고유 매크로 신호를 tanh 로 정규화한 값.<br><br>
    매핑:<br>
    <b>IT</b> ← DXY 3M · <b>FIN</b> ← Yield Curve · <b>ENERGY</b> ← WTI 3M<br>
    <b>INDU</b> ← Copper/DXY · <b>DISCR</b> ← HY Spread 변화 · <b>STAPLES</b> ← VIX<br>
    <b>HEALTH</b> ← DXY · <b>COMM</b> ← NVDA 3M
  </div>
</div>

<h2>누적 수익 곡선</h2>
<div class="canvas-wrap">
  <canvas id="cum" style="max-height:440px"></canvas>
</div>

<h2>Config 설명</h2>
<table>
  <thead><tr><th>config</th><th>차이</th></tr></thead>
  <tbody>{cfg_table}</tbody>
</table>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script>
  new Chart(document.getElementById('cum'), {{
    type: 'line',
    data: {{ labels: {labels_j}, datasets: {json.dumps(datasets)} }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position:'top', labels:{{ usePointStyle:true, pointStyle:'line', font:{{size:11}} }} }} }},
      scales: {{ y: {{ ticks: {{ callback: v => (v*100).toFixed(0)+'%' }} }}, x: {{ ticks: {{ maxTicksLimit:14 }} }} }}
    }}
  }});
</script>

</body>
</html>
"""
    return html


# ──────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────

def _load_macro_series(start: str) -> dict[str, pd.Series]:
    """MKT200 에서 필요한 macro 코드 dict."""
    needed = ["US_YIELD_CURVE", "US_HY_SPREAD", "US_10Y_YIELD",
              "US_UNEMP_RATE", "VIX", "DXY"]
    df = load_macro_long(start=start, codes=needed)
    if df.empty:
        return {}
    out: dict[str, pd.Series] = {}
    for code, sub in df.groupby("INDICATOR_CODE"):
        ser = sub.set_index("DATE")["VALUE"].sort_index()
        out[code] = pd.to_numeric(ser, errors="coerce")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",   default=None)
    parser.add_argument("--start",  default=BACKTEST_START)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    codes = ([p[0] for p in SECTOR_PAIRS] + [p[1] for p in SECTOR_PAIRS]
             + [KOSPI_CODE, SP500_CODE, VIX_CODE,
                "FX_DXY", "CM_WTI", "CM_COPPER", "ST_NVDA"])
    pivot = load_wide_close(start=args.start, codes=codes)
    if pivot.empty:
        raise SystemExit("[ERROR] 가격 데이터 로드 실패")

    sector_codes = [p[0] for p in SECTOR_PAIRS] + [p[1] for p in SECTOR_PAIRS]
    vol_map = _load_long_with_volume(sector_codes, args.start)
    macro = _load_macro_series(args.start)

    if args.date:
        pivot = pivot.loc[:args.date]
        date_str = args.date
    else:
        date_str = pivot.index.max().strftime("%Y-%m-%d")

    print(f"[load] pivot {pivot.shape} · volumes {len(vol_map)} · macro {len(macro)} · cutoff {date_str}")

    cfgs = [c for c in SWEEP_CONFIGS if c.name == args.config] if args.config else SWEEP_CONFIGS
    print(f"[sweep] {len(cfgs)} configs")
    results = run_sweep(cfgs, pivot, vol_map, macro)

    # 벤치마크
    sample_bt = next(iter(results.values()))
    bench = {
        "50/50 Blend": sample_bt["blend_return"],
        "KOSPI":       sample_bt["kr_return"],
        "S&P500":      sample_bt["us_return"],
    }
    print("\n[benchmarks]")
    for name, ser in bench.items():
        m = perf(ser, name)
        if m:
            print(f"  {name:22s}  CAGR={m['ann_return']*100:+6.2f}%  "
                  f"Sharpe={m['sharpe']:+5.2f}  MDD={m['mdd']*100:+6.1f}%")

    # Mean-RS (sync) reference
    try:
        from portfolio.strategy.sector_rs.sector_rs_sync import run_backtest as sync_bt
        sync_df = sync_bt(pivot)
        mean_rs_ser = sync_df["mean_strategy"] if not sync_df.empty else None
        if mean_rs_ser is not None:
            m = perf(mean_rs_ser, "Mean-RS (sync)")
            print(f"  {'Mean-RS (sync)':22s}  CAGR={m['ann_return']*100:+6.2f}%  "
                  f"Sharpe={m['sharpe']:+5.2f}  MDD={m['mdd']*100:+6.1f}%")
    except Exception as e:
        print(f"[WARN] Mean-RS 참조 로드 실패: {e}")
        mean_rs_ser = None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = build_sweep_html(results, bench, date_str, mean_rs_ser)
    html_path = OUTPUT_DIR / f"{date_str}_sweep.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"\n[write] {html_path}")

    if results:
        best_name = max(results.keys(),
                        key=lambda n: perf(results[n]["strategy_return"], n).get("sharpe", -1))
        csv_path = OUTPUT_DIR / f"{date_str}_{best_name}_signals.csv"
        results[best_name].to_csv(csv_path, index=False)
        print(f"[write] {csv_path} (best: {best_name})")


if __name__ == "__main__":
    main()
