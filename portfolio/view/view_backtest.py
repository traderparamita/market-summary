"""View Agent Signal Backtest — Cross-sectional IC / Hit Rate / Regime Analysis.

매월 말 compute_signals()를 실행하여 각 신호의 순방향 수익률 예측력을 검증한다.

방법론:
- Cross-sectional Spearman IC: 특정 날짜에서 자산별 점수 vs 실제 forward return
- 월별 IC를 집계하여 Mean IC, ICIR(= IC / std_IC) 산출
- 레짐별(RiskOFF/Neutral/RiskON) IC 분해
- 롱-숏 퀸타일 시뮬레이션 (상위 20% - 하위 20%)

Usage:
    python -m portfolio.view.view_backtest --date 2026-04-14 --html
    python -m portfolio.view.view_backtest --date 2026-04-14 --start 2016-01-01 --html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import ConstantInputWarning
import warnings
warnings.filterwarnings("ignore", category=ConstantInputWarning)

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from portfolio.view.scoring import compute_signals, load_prices, load_universe
from portfolio.view._shared import BASE_CSS, NAV_CSS, nav_html, ALL_VIEWS

HISTORY_CSV = ROOT / "history" / "market_data.csv"
OUTPUT_DIR  = ROOT / "output" / "view" / "backtest"

# ── ETF-class assets only (skip individual stocks for IC) ─────────────────
ETF_CLASSES = {
    # 광의 주식
    "equity_us", "equity_dm", "equity_em", "equity_global",
    # 미국 섹터
    "sector_us",
    # 한국 섹터
    "sector_kr",
    # 팩터/스타일
    "style_us",
    # 채권
    "ust_long", "ust_mid", "ust_mid_etf", "ust_short", "tips",
    "agg_bond", "credit_hy", "credit_ig", "em_debt",
    # 대안
    "gold", "commodity", "usd",
}

# Yield-based proxies: forward return must be inverted (yield↑ = price↓)
YIELD_BASED_CODES = {"BD_US_10Y", "BD_US_2Y", "BD_US_30Y"}

# Signal columns to backtest
SIGNALS: dict[str, str] = {
    "composite_score": "Composite Score",
    "mom_12_1_z":      "12M Momentum",
    "mom_6_1_z":       "6M Momentum",
    "mom_3_1_z":       "3M Momentum",
    "trend_ma200":     "Trend MA200",
    "macd_hist_z":     "MACD Hist",
    "rsi_signal":      "RSI Contrarian",
    "bb_signal":       "BB %B Contrarian",
}


# ─────────────────────────────────────────────────────────────
# 1. 월별 신호 이력 생성
# ─────────────────────────────────────────────────────────────

def _monthly_dates(start: str, end: str) -> list[pd.Timestamp]:
    """월 말 영업일 리스트."""
    return list(pd.date_range(start, end, freq="BME"))


def _forward_return(prices: pd.DataFrame, code: str, date: pd.Timestamp, horizon: int) -> float | None:
    """date로부터 horizon 영업일 후 수익률. 수익률 = p1/p0 - 1."""
    if code not in prices.columns:
        return None
    series = prices[code].dropna()

    before = series[series.index <= date]
    if before.empty:
        return None
    p0 = float(before.iloc[-1])
    if p0 <= 0:
        return None

    future_ts = date + pd.offsets.BusinessDay(horizon)
    after = series[(series.index > date) & (series.index <= future_ts)]
    if after.empty:
        return None
    p1 = float(after.iloc[-1])

    ret = p1 / p0 - 1.0
    # 금리 계열은 부호 반전 (yield↑ = bond price↓)
    if code in YIELD_BASED_CODES:
        ret = -ret
    return ret


def build_signal_history(
    prices: pd.DataFrame,
    universe: dict,
    dates: list[pd.Timestamp],
    horizons: list[int] = (21, 63),
) -> pd.DataFrame:
    """월별 날짜 × 자산 단위 신호 + forward return DataFrame."""
    records: list[dict] = []
    n = len(dates)

    for i, d in enumerate(dates):
        print(f"\r  [{i+1:3d}/{n}] {d.date()} ...", end="", flush=True)

        try:
            scores = compute_signals(prices, str(d.date()), universe)
        except Exception as e:
            print(f" ERROR: {e}")
            continue
        if scores.empty:
            continue

        for _, row in scores.iterrows():
            ac   = row.get("asset_class", "")
            code = row.get("indicator_code", "")
            if ac not in ETF_CLASSES:
                continue  # 개별 주식 제외

            rec: dict = {
                "date":          d,
                "asset":         row["etf"],
                "asset_class":   ac,
                "code":          code,
                "regime":        row.get("market_regime", "Neutral"),
                "composite_score": row.get("composite_score", np.nan),
                "mom_12_1_z":    row.get("mom_12_1_z",   np.nan),
                "mom_6_1_z":     row.get("mom_6_1_z",    np.nan),
                "mom_3_1_z":     row.get("mom_3_1_z",    np.nan),
                "trend_ma200":   row.get("trend_ma200",  np.nan),
                "macd_hist_z":   row.get("macd_hist_z",  np.nan),
                "rsi_signal":    row.get("rsi_signal",   np.nan),
                "bb_signal":     row.get("bb_signal",    np.nan),
            }
            for h in horizons:
                r = _forward_return(prices, code, d, h)
                rec[f"fwd_{h}d"] = r if r is not None else np.nan
            records.append(rec)

    print()
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────
# 2. IC 계산 함수
# ─────────────────────────────────────────────────────────────

def _cs_ic_series(df: pd.DataFrame, sig: str, fwd: str) -> pd.Series:
    """월별 Cross-sectional Spearman IC 시계열."""
    rows = []
    for dt, g in df.groupby("date"):
        sub = g[[sig, fwd]].dropna()
        if len(sub) < 4:
            continue
        ic_val, _ = stats.spearmanr(sub[sig], sub[fwd])
        if not np.isnan(ic_val):
            rows.append({"date": dt, "ic": float(ic_val)})
    if not rows:
        return pd.Series(dtype=float, name=sig)
    s = pd.DataFrame(rows).set_index("date")["ic"]
    s.name = sig
    return s


def _ic_summary(df: pd.DataFrame, horizons: list[int] = (21, 63)) -> pd.DataFrame:
    """신호별 × 기간별 IC 요약 테이블."""
    rows = []
    for sig, name in SIGNALS.items():
        if sig not in df.columns:
            continue
        row: dict = {"signal": name}
        for h in horizons:
            fwd = f"fwd_{h}d"
            ics = _cs_ic_series(df, sig, fwd)
            if len(ics) < 8:
                row.update({f"ic_{h}d": np.nan, f"icir_{h}d": np.nan,
                             f"hit_{h}d": np.nan, f"valid_{h}d": False})
                continue
            mean_ic = float(ics.mean())
            std_ic  = float(ics.std())
            icir    = mean_ic / std_ic if std_ic > 0 else 0.0
            t_stat  = mean_ic / (std_ic / np.sqrt(len(ics))) if std_ic > 0 else 0.0

            # Hit rate: sign(score) == sign(return) across all obs
            all_sig = df[sig].dropna()
            all_fwd = df[fwd].dropna()
            aligned = pd.concat([all_sig, all_fwd], axis=1).dropna()
            aligned.columns = ["s", "r"]
            hit = float((np.sign(aligned["s"]) == np.sign(aligned["r"])).mean())

            valid = (abs(mean_ic) >= 0.05) and (hit >= 0.50) and (abs(t_stat) >= 1.65)
            row.update({
                f"ic_{h}d":    round(mean_ic, 4),
                f"icir_{h}d":  round(icir,    3),
                f"hit_{h}d":   round(hit,     4),
                f"valid_{h}d": valid,
            })
        rows.append(row)
    return pd.DataFrame(rows)


def _regime_ic(df: pd.DataFrame, sig: str = "composite_score", horizon: int = 21) -> pd.DataFrame:
    """레짐별 Cross-sectional IC."""
    fwd = f"fwd_{horizon}d"
    rows = []
    for regime in ["RiskON", "Neutral", "RiskOFF"]:
        sub = df[df["regime"] == regime]
        ics = _cs_ic_series(sub, sig, fwd)
        n   = len(ics)
        rows.append({
            "regime":   regime,
            "mean_ic":  round(float(ics.mean()), 4) if n >= 5 else np.nan,
            "n_months": n,
            "pct":      round(n / max(len(df.groupby("date")), 1) * 100, 1),
        })
    return pd.DataFrame(rows)


def _longshor_returns(df: pd.DataFrame, sig: str = "composite_score", horizon: int = 21) -> pd.Series:
    """Top quintile − Bottom quintile monthly return spread."""
    fwd = f"fwd_{horizon}d"
    spreads = []
    for dt, g in df.groupby("date"):
        sub = g[[sig, fwd]].dropna()
        if len(sub) < 5:
            continue
        q = sub[sig].quantile([0.2, 0.8])
        top    = float(sub.loc[sub[sig] >= q[0.8], fwd].mean())
        bottom = float(sub.loc[sub[sig] <= q[0.2], fwd].mean())
        spreads.append({"date": dt, "spread": top - bottom})
    if not spreads:
        return pd.Series(dtype=float, name="ls_spread")
    s = pd.DataFrame(spreads).set_index("date")["spread"]
    s.name = "ls_spread"
    return s


# ─────────────────────────────────────────────────────────────
# 3. HTML 렌더링
# ─────────────────────────────────────────────────────────────

def _ic_badge(ic: float | None) -> str:
    if ic is None or np.isnan(ic):
        return '<span style="color:#aaa">N/A</span>'
    if abs(ic) >= 0.08:
        color = "#059669"
    elif abs(ic) >= 0.05:
        color = "#16a34a"
    elif abs(ic) >= 0.02:
        color = "#ca8a04"
    else:
        color = "#dc2626"
    sign = "+" if ic > 0 else ""
    return f'<span style="color:{color};font-weight:600">{sign}{ic:.3f}</span>'


def _hit_badge(hit: float | None) -> str:
    if hit is None or np.isnan(hit):
        return '<span style="color:#aaa">N/A</span>'
    if hit >= 0.58:
        color = "#059669"; fw = "600"
    elif hit >= 0.52:
        color = "#16a34a"; fw = "500"
    elif hit >= 0.48:
        color = "#ca8a04"; fw = "400"
    else:
        color = "#dc2626"; fw = "400"
    return f'<span style="color:{color};font-weight:{fw}">{hit:.1%}</span>'


def _valid_badge(v: bool) -> str:
    if v:
        return '<span style="background:#dcfce7;color:#166534;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700">✓ VALID</span>'
    return '<span style="background:#fee2e2;color:#991b1b;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600">✗</span>'


def _ic_bar(ic: float | None, scale: float = 0.25) -> str:
    """IC 값을 수평 바로 시각화 (±scale 기준)."""
    if ic is None or np.isnan(ic):
        return ""
    pct = min(abs(ic) / scale * 50, 50)
    color = "#059669" if ic >= 0 else "#dc2626"
    if ic >= 0:
        left = "50%"
        style = f"position:absolute;left:{left};width:{pct:.1f}%;height:6px;background:{color};border-radius:0 3px 3px 0;top:50%;transform:translateY(-50%)"
    else:
        right_pct = 50 - pct
        style = f"position:absolute;left:{right_pct:.1f}%;width:{pct:.1f}%;height:6px;background:{color};border-radius:3px 0 0 3px;top:50%;transform:translateY(-50%)"
    return (
        f'<div style="position:relative;width:100%;height:14px;background:#f0f0f0;border-radius:3px">'
        f'<div style="position:absolute;left:50%;width:1px;height:100%;background:#ccc;top:0"></div>'
        f'<div style="{style}"></div>'
        f'</div>'
    )


def _ic_chart_html(ic_series: pd.Series, title: str) -> str:
    """Chart.js를 사용한 월별 IC 시계열 차트 HTML snippet."""
    if ic_series.empty:
        return "<p style='color:#aaa;text-align:center'>데이터 부족</p>"

    labels = [d.strftime("%Y-%m") for d in ic_series.index]
    values = [round(v, 4) for v in ic_series.values]
    ma_raw = ic_series.rolling(3, min_periods=1).mean()
    ma_vals = [round(v, 4) for v in ma_raw.values]

    colors = ["rgba(5,150,105,.6)" if v >= 0 else "rgba(220,38,38,.6)" for v in values]

    labels_js = json.dumps(labels)
    values_js = json.dumps(values)
    ma_js     = json.dumps(ma_vals)
    colors_js = json.dumps(colors)

    cid = f"chart_{abs(hash(title)) % 100000}"

    return f"""
<div style="position:relative;height:220px">
  <canvas id="{cid}"></canvas>
</div>
<script>
(function(){{
  var ctx = document.getElementById('{cid}').getContext('2d');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels_js},
      datasets: [
        {{
          type: 'bar',
          label: 'Monthly IC',
          data: {values_js},
          backgroundColor: {colors_js},
          borderRadius: 2,
          order: 2,
        }},
        {{
          type: 'line',
          label: '3M MA',
          data: {ma_js},
          borderColor: '#F58220',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          order: 1,
        }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: true, position: 'top', labels: {{ font: {{ size: 11 }} }} }},
        tooltip: {{
          callbacks: {{
            label: function(c) {{
              return c.dataset.label + ': ' + c.raw.toFixed(3);
            }}
          }}
        }}
      }},
      scales: {{
        x: {{ ticks: {{ maxTicksLimit: 12, font: {{ size: 10 }} }}, grid: {{ display: false }} }},
        y: {{
          ticks: {{ font: {{ size: 10 }}, callback: function(v){{ return v.toFixed(2); }} }},
          grid: {{ color: '#e5e7eb' }},
          suggestedMin: -0.3, suggestedMax: 0.3
        }}
      }}
    }}
  }});
}})();
</script>"""


def _ls_chart_html(ls_cumulative: pd.Series, title: str = "Long-Short Cumulative") -> str:
    """롱-숏 누적 수익률 차트."""
    if ls_cumulative.empty:
        return ""
    labels = [d.strftime("%Y-%m") for d in ls_cumulative.index]
    values = [round(v, 4) for v in ls_cumulative.values]
    cid = f"ls_{abs(hash(title)) % 100000}"
    return f"""
<div style="position:relative;height:200px">
  <canvas id="{cid}"></canvas>
</div>
<script>
(function(){{
  var ctx = document.getElementById('{cid}').getContext('2d');
  var data = {json.dumps(values)};
  var colors = data.map(function(v){{ return v >= 0 ? 'rgba(5,150,105,.7)' : 'rgba(220,38,38,.7)'; }});
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: {json.dumps(labels)},
      datasets: [{{
        label: 'L/S Cumulative Return',
        data: data,
        borderColor: '#043B72',
        backgroundColor: 'rgba(4,59,114,.08)',
        fill: true,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.2,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ labels: {{ font: {{ size: 11 }} }} }} }},
      scales: {{
        x: {{ ticks: {{ maxTicksLimit: 10, font: {{ size: 10 }} }}, grid: {{ display: false }} }},
        y: {{
          ticks: {{
            font: {{ size: 10 }},
            callback: function(v){{ return (v*100).toFixed(1) + '%'; }}
          }},
          grid: {{ color: '#e5e7eb' }}
        }}
      }}
    }}
  }});
}})();
</script>"""


def build_html(
    date_str: str,
    ic_table: pd.DataFrame,
    regime_df: pd.DataFrame,
    ic_series_1m: pd.Series,
    ic_series_3m: pd.Series,
    ls_series: pd.Series,
    n_dates: int,
    n_assets_avg: float,
    start_str: str,
    end_str: str,
) -> str:

    # ── IC 요약 테이블 ─────────────────────────────────────────
    ic_rows_html = ""
    for _, row in ic_table.iterrows():
        sig_name = row["signal"]

        # 1M
        ic1  = row.get("ic_21d", np.nan)
        hit1 = row.get("hit_21d", np.nan)
        v1   = row.get("valid_21d", False)
        icir1 = row.get("icir_21d", np.nan)

        # 3M
        ic3  = row.get("ic_63d", np.nan)
        hit3 = row.get("hit_63d", np.nan)
        v3   = row.get("valid_63d", False)
        icir3 = row.get("icir_63d", np.nan)

        icir1_str = f"{icir1:.2f}" if not np.isnan(icir1) else "—"
        icir3_str = f"{icir3:.2f}" if not np.isnan(icir3) else "—"

        ic_rows_html += f"""
<tr>
  <td style="font-weight:600;white-space:nowrap">{sig_name}</td>
  <td>{_ic_badge(ic1)}<br>{_ic_bar(ic1)}</td>
  <td style="font-size:12px;color:#64748b">{icir1_str}</td>
  <td>{_hit_badge(hit1)}</td>
  <td>{_valid_badge(v1)}</td>
  <td>{_ic_badge(ic3)}<br>{_ic_bar(ic3)}</td>
  <td style="font-size:12px;color:#64748b">{icir3_str}</td>
  <td>{_hit_badge(hit3)}</td>
  <td>{_valid_badge(v3)}</td>
</tr>"""

    # ── 레짐별 IC ──────────────────────────────────────────────
    regime_rows_html = ""
    regime_icons = {"RiskON": "🟢", "Neutral": "🟡", "RiskOFF": "🔴"}
    for _, row in regime_df.iterrows():
        reg  = row["regime"]
        mic  = row.get("mean_ic", np.nan)
        nm   = int(row.get("n_months", 0))
        pct  = row.get("pct", 0)
        icon = regime_icons.get(reg, "")
        regime_rows_html += f"""
<tr>
  <td>{icon} <strong>{reg}</strong></td>
  <td>{_ic_badge(mic)}<br>{_ic_bar(mic)}</td>
  <td style="color:#64748b">{nm}개월 ({pct:.0f}%)</td>
</tr>"""

    # ── L/S 누적 수익률 시계열 ─────────────────────────────────
    ls_cum_pct = (ls_series + 1).cumprod() - 1 if not ls_series.empty else ls_series
    ls_html = _ls_chart_html(ls_cum_pct, "ls")
    ls_total = f"{float(ls_cum_pct.iloc[-1])*100:.1f}%" if not ls_cum_pct.empty else "N/A"
    ls_ann   = ""
    if not ls_series.empty:
        n_yr = len(ls_series) / 12
        ann  = (float(ls_cum_pct.iloc[-1]) + 1) ** (1 / max(n_yr, 1)) - 1
        ls_ann = f"연환산 {ann*100:.1f}%"

    # ── IC 시계열 차트 ─────────────────────────────────────────
    chart1m = _ic_chart_html(ic_series_1m, "1M_IC")
    chart3m = _ic_chart_html(ic_series_3m, "3M_IC")

    # ── composite IC 1M 요약 숫자 ──────────────────────────────
    comp_row = ic_table[ic_table["signal"] == "Composite Score"]
    if not comp_row.empty:
        c_ic1  = comp_row.iloc[0].get("ic_21d", np.nan)
        c_hit1 = comp_row.iloc[0].get("hit_21d", np.nan)
        c_v1   = comp_row.iloc[0].get("valid_21d", False)
        c_ic1_str  = f"{c_ic1:+.3f}" if not np.isnan(c_ic1) else "N/A"
        c_hit1_str = f"{c_hit1:.1%}" if not np.isnan(c_hit1) else "N/A"
        c_verdict  = "✓ 통계적 유의" if c_v1 else "✗ 미달"
        badge_color = "#059669" if c_v1 else "#dc2626"
    else:
        c_ic1_str = c_hit1_str = c_verdict = "N/A"
        badge_color = "#aaa"

    nav = nav_html(date_str, "backtest")

    body = f"""
{nav}
<div class="ma-page">

  <!-- 헤더 -->
  <div class="ma-header">
    <div>
      <h1>View Agent 신호 백테스트</h1>
      <p class="muted" style="margin-top:4px">
        Cross-sectional IC · 레짐 분해 · 롱-숏 시뮬레이션 &nbsp;|&nbsp;
        기간 {start_str} ~ {end_str} ({n_dates}개월, 자산 평균 {n_assets_avg:.0f}개/월)
      </p>
    </div>
    <div style="text-align:right">
      <div style="font-size:11px;color:#aaa;margin-bottom:4px">기준일</div>
      <div style="font-size:18px;font-weight:700;color:#043B72">{date_str}</div>
    </div>
  </div>

  <!-- 핵심 요약 카드 -->
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px">
    <div class="card" style="text-align:center;padding:20px 16px">
      <div style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Composite IC (1M)</div>
      <div style="font-size:28px;font-weight:700;color:{badge_color}">{c_ic1_str}</div>
      <div style="font-size:12px;color:#64748b;margin-top:4px">Hit {c_hit1_str}</div>
    </div>
    <div class="card" style="text-align:center;padding:20px 16px">
      <div style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">신호 유효성</div>
      <div style="font-size:22px;font-weight:700;color:{badge_color}">{c_verdict}</div>
      <div style="font-size:12px;color:#64748b;margin-top:4px">IC≥0.05, Hit≥50%, |t|≥1.65</div>
    </div>
    <div class="card" style="text-align:center;padding:20px 16px">
      <div style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">L/S 누적 수익</div>
      <div style="font-size:28px;font-weight:700;color:#043B72">{ls_total}</div>
      <div style="font-size:12px;color:#64748b;margin-top:4px">{ls_ann}</div>
    </div>
    <div class="card" style="text-align:center;padding:20px 16px">
      <div style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">백테스트 기간</div>
      <div style="font-size:22px;font-weight:700;color:#043B72">{n_dates}M</div>
      <div style="font-size:12px;color:#64748b;margin-top:4px">ETF {n_assets_avg:.0f}종 / 월</div>
    </div>
  </div>

  <!-- IC 요약 테이블 -->
  <div class="card" style="margin-bottom:28px">
    <div class="card-title">
      신호 IC 요약
      <span class="card-sub">1M (21영업일) / 3M (63영업일) 선행 수익률</span>
    </div>
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead>
          <tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0">
            <th rowspan="2" style="padding:10px 14px;text-align:left;font-weight:700">신호</th>
            <th colspan="4" style="padding:6px;text-align:center;border-left:1px solid #e2e8f0;color:#043B72">1M Forward Return</th>
            <th colspan="4" style="padding:6px;text-align:center;border-left:1px solid #e2e8f0;color:#F58220">3M Forward Return</th>
          </tr>
          <tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0">
            <th style="padding:8px;text-align:center;border-left:1px solid #e2e8f0;font-weight:600">IC</th>
            <th style="padding:8px;text-align:center;font-weight:600">ICIR</th>
            <th style="padding:8px;text-align:center;font-weight:600">Hit%</th>
            <th style="padding:8px;text-align:center;font-weight:600">유효?</th>
            <th style="padding:8px;text-align:center;border-left:1px solid #e2e8f0;font-weight:600">IC</th>
            <th style="padding:8px;text-align:center;font-weight:600">ICIR</th>
            <th style="padding:8px;text-align:center;font-weight:600">Hit%</th>
            <th style="padding:8px;text-align:center;font-weight:600">유효?</th>
          </tr>
        </thead>
        <tbody>
          {ic_rows_html}
        </tbody>
      </table>
    </div>
    <div style="margin-top:10px;font-size:11px;color:#94a3b8;line-height:1.6">
      IC: 크로스-섹셔널 Spearman 상관계수 (월별 IC 평균) &nbsp;·&nbsp;
      ICIR: IC / std(IC) &nbsp;·&nbsp;
      Hit%: 부호 일치율 &nbsp;·&nbsp;
      유효 기준: |IC|≥0.05, Hit≥50%, |t-stat|≥1.65
    </div>
  </div>

  <!-- 레짐별 IC + L/S 차트 -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:28px">

    <div class="card">
      <div class="card-title">
        레짐별 Composite IC (1M)
        <span class="card-sub">시장 국면에 따른 신호 예측력 차이</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead>
          <tr style="background:#f8fafc;border-bottom:1px solid #e2e8f0">
            <th style="padding:8px 12px;text-align:left">레짐</th>
            <th style="padding:8px 12px;text-align:left">IC</th>
            <th style="padding:8px 12px;text-align:left">관찰</th>
          </tr>
        </thead>
        <tbody>{regime_rows_html}</tbody>
      </table>
      <div style="margin-top:12px;font-size:11px;color:#94a3b8">
        레짐 = VIX 기반 당일 시장 국면 분류 (RiskOFF: VIX>25 / RiskON: VIX&lt;15)
      </div>
    </div>

    <div class="card">
      <div class="card-title">
        Composite Score 롱-숏 시뮬레이션
        <span class="card-sub">Top 20% − Bottom 20% 1M 스프레드 누적</span>
      </div>
      {ls_html}
      <div style="margin-top:8px;font-size:11px;color:#94a3b8">
        거래비용·슬리피지 미반영 (gross). ETF 유니버스 기준.
      </div>
    </div>

  </div>

  <!-- IC 시계열 차트 -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:28px">

    <div class="card">
      <div class="card-title">
        월별 Cross-sectional IC — 1M
        <span class="card-sub">Composite Score vs 1개월 선행 수익률</span>
      </div>
      {chart1m}
      <div style="margin-top:6px;font-size:11px;color:#94a3b8">
        오렌지선: 3개월 이동평균 IC
      </div>
    </div>

    <div class="card">
      <div class="card-title">
        월별 Cross-sectional IC — 3M
        <span class="card-sub">Composite Score vs 3개월 선행 수익률</span>
      </div>
      {chart3m}
      <div style="margin-top:6px;font-size:11px;color:#94a3b8">
        오렌지선: 3개월 이동평균 IC
      </div>
    </div>

  </div>

  <!-- 방법론 주석 -->
  <div class="card" style="background:#f8fafc;border:1px solid #e2e8f0">
    <div class="card-title">방법론 & 해석 가이드</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;font-size:13px;color:#475569;line-height:1.7">
      <div>
        <strong style="color:#043B72">IC (Information Coefficient)</strong><br>
        각 월 말에서 ETF 자산들의 Composite Score와 이후 1M/3M 실제 수익률 사이의
        Spearman 순위 상관계수. 월별 IC를 평균하면 해당 신호의 전체 예측력.
        <br><br>
        <strong style="color:#043B72">유효 기준</strong><br>
        |Mean IC| ≥ 0.05 &nbsp;AND&nbsp; Hit Rate ≥ 50% &nbsp;AND&nbsp; |t-stat| ≥ 1.65
      </div>
      <div>
        <strong style="color:#F58220">ICIR (IC Information Ratio)</strong><br>
        IC의 안정성 지표: ICIR = Mean IC / Std(IC).
        ICIR &gt; 0.5 이면 일관성 있는 신호, &gt; 1.0 이면 강한 신호.
        <br><br>
        <strong style="color:#F58220">롱-숏 시뮬레이션</strong><br>
        매월 Composite Score 상위 20% 자산을 매수, 하위 20%를 매도한 경우의
        1M 스프레드 누적. 거래비용 미포함(gross) 기준.
      </div>
    </div>
  </div>

</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
"""

    # ── CSS 추가 ──────────────────────────────────────────────
    extra_css = """
.card {
  background: #fff;
  border: 1px solid #e0e3ed;
  border-radius: 10px;
  padding: 20px;
}
.card-title {
  font-size: 15px;
  font-weight: 700;
  color: #043B72;
  margin-bottom: 14px;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.card-sub {
  font-size: 11px;
  font-weight: 400;
  color: #94a3b8;
}
tbody tr:hover { background: #f8fafc; }
tbody td { padding: 9px 14px; border-bottom: 1px solid #f0f0f5; vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
"""

    # ── 전체 페이지 조립 ──────────────────────────────────────
    full = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>View Agent Backtest — {date_str}</title>
<style>
{BASE_CSS}
{NAV_CSS}
{extra_css}
</style>
</head>
<body>
{body}
</body>
</html>"""
    return full


# ─────────────────────────────────────────────────────────────
# 4. 메인 실행
# ─────────────────────────────────────────────────────────────

def run_backtest(
    date_str: str,
    start: str = "2016-01-01",
    save_html: bool = True,
) -> dict:
    """백테스트 실행 후 결과 dict 반환."""
    print(f"\n[View Backtest] {start} ~ {date_str}")

    prices   = load_prices()
    universe = load_universe()

    # 종료일은 forward return 계산에 63일 여유 필요 → 약 3개월 전까지
    # 단, 최신 신호 포인트를 포함하기 위해 date_str 당일까지 사용
    end_ts   = pd.Timestamp(date_str)
    dates    = _monthly_dates(start, str(end_ts.date()))

    print(f"  월별 기준일 {len(dates)}개 처리 중...")
    df = build_signal_history(prices, universe, dates, horizons=[21, 63])

    if df.empty:
        print("[ERROR] 신호 이력 생성 실패")
        return {}

    n_dates     = df["date"].nunique()
    n_assets_avg = df.groupby("date").size().mean()
    print(f"  완료: {n_dates}개월 × 평균 {n_assets_avg:.1f}종")

    print("  IC 요약 계산 중...")
    ic_table  = _ic_summary(df, horizons=[21, 63])
    regime_df = _regime_ic(df, "composite_score", 21)
    ic_s1m    = _cs_ic_series(df, "composite_score", "fwd_21d")
    ic_s3m    = _cs_ic_series(df, "composite_score", "fwd_63d")
    ls_series = _longshor_returns(df, "composite_score", 21)

    result = {
        "n_dates":      n_dates,
        "n_assets_avg": n_assets_avg,
        "ic_table":     ic_table,
        "regime_ic":    regime_df,
    }

    if save_html:
        html = build_html(
            date_str    = date_str,
            ic_table    = ic_table,
            regime_df   = regime_df,
            ic_series_1m = ic_s1m,
            ic_series_3m = ic_s3m,
            ls_series   = ls_series,
            n_dates     = n_dates,
            n_assets_avg = n_assets_avg,
            start_str   = start,
            end_str     = date_str,
        )
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{date_str}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"\n  → 저장: {out_path}")
        result["html_path"] = str(out_path)

    return result


def main():
    parser = argparse.ArgumentParser(description="View Agent Signal Backtest")
    parser.add_argument("--date",  default=None, help="기준일 (YYYY-MM-DD, 기본=오늘)")
    parser.add_argument("--start", default="2016-01-01", help="백테스트 시작일")
    parser.add_argument("--html",  action="store_true", help="HTML 저장")
    args = parser.parse_args()

    date_str = args.date or pd.Timestamp.today().strftime("%Y-%m-%d")

    result = run_backtest(
        date_str  = date_str,
        start     = args.start,
        save_html = args.html,
    )

    if result:
        print("\n── IC 요약 ────────────────────────────────────────────")
        print(result["ic_table"].to_string(index=False))
        print("\n── 레짐별 IC (1M) ─────────────────────────────────────")
        print(result["regime_ic"].to_string(index=False))


if __name__ == "__main__":
    main()
