"""Rolling correlation view — asset correlation heatmaps.

Computes 30/60/90-day rolling correlations between key assets.
Core signal: equity-bond correlation sign (negative = diversification working).

Usage:
    python -m portfolio.view.correlation_view --date 2026-04-13 --html
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "correlation"
HISTORY_CSV = ROOT / "history" / "market_data.csv"

# Core 8 assets for the correlation heatmap
CORE_ASSETS: list[str] = [
    "EQ_SP500",
    "EQ_NASDAQ",
    "BD_TLT",
    "BD_HYG",
    "CM_GOLD",
    "CM_WTI",
    "FX_DXY",
    "EQ_KOSPI",
]

# Human-readable short labels for heatmap axis
ASSET_LABELS: dict[str, str] = {
    "EQ_SP500":  "S&P500",
    "EQ_NASDAQ": "NASDAQ",
    "BD_TLT":    "TLT",
    "BD_HYG":    "HYG",
    "CM_GOLD":   "Gold",
    "CM_WTI":    "WTI",
    "FX_DXY":    "DXY",
    "EQ_KOSPI":  "KOSPI",
}

# Equity-bond pair for the key signal card
_EQUITY_CODE = "EQ_SP500"
_BOND_CODE = "BD_TLT"


# ── Data loading ──────────────────────────────────────────────────────

def _load_wide(csv_path: Path, as_of_date: str) -> pd.DataFrame:
    """Load market_data.csv and pivot to a wide DATE × INDICATOR_CODE price frame.

    Args:
        csv_path: Path to market_data.csv.
        as_of_date: Upper bound date string (inclusive), e.g. '2026-04-13'.

    Returns:
        DataFrame indexed by DATE with INDICATOR_CODE columns containing CLOSE prices.
        Only rows up to and including as_of_date are returned.
    """
    if not csv_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(
        csv_path,
        usecols=["DATE", "INDICATOR_CODE", "CLOSE"],
        parse_dates=["DATE"],
    )
    df = df.sort_values("DATE")

    cutoff = pd.Timestamp(as_of_date)
    df = df[df["DATE"] <= cutoff]

    wide = df.pivot_table(
        index="DATE",
        columns="INDICATOR_CODE",
        values="CLOSE",
        aggfunc="first",
    )
    wide.index.name = "DATE"
    return wide


# ── Correlation computation ───────────────────────────────────────────

def _rolling_corr_pair(
    returns: pd.DataFrame,
    code_a: str,
    code_b: str,
    window: int,
) -> Optional[float]:
    """Compute trailing ``window``-day Pearson correlation between two return series.

    Args:
        returns: Daily return DataFrame (DATE × INDICATOR_CODE).
        code_a: First indicator code.
        code_b: Second indicator code.
        window: Look-back window in trading days.

    Returns:
        Scalar correlation, or None if either series is missing or too short.
    """
    if code_a not in returns.columns or code_b not in returns.columns:
        return None

    tail = returns[[code_a, code_b]].dropna().iloc[-window:]
    if len(tail) < max(10, window // 3):
        return None

    corr_val = tail[code_a].corr(tail[code_b])
    return float(corr_val) if not np.isnan(corr_val) else None


def _corr_matrix(
    returns: pd.DataFrame,
    codes: list[str],
    window: int,
) -> dict[str, dict[str, float]]:
    """Build a correlation matrix dict for the given codes over the trailing window.

    Only codes present in ``returns`` are included.

    Args:
        returns: Daily return DataFrame.
        codes: Ordered list of indicator codes.
        window: Look-back window in trading days.

    Returns:
        Nested dict: {code_row: {code_col: correlation}}.
        Missing pairs are represented as NaN.
    """
    available = [c for c in codes if c in returns.columns]
    if not available:
        return {}

    tail = returns[available].dropna(how="all").iloc[-window:]
    corr_df = tail.corr(method="pearson")

    result: dict[str, dict[str, float]] = {}
    for row in available:
        result[row] = {}
        for col in available:
            val = corr_df.loc[row, col] if (row in corr_df.index and col in corr_df.columns) else np.nan
            result[row][col] = float(val)
    return result


def _equity_bond_signal(corr_30d: Optional[float]) -> str:
    """Return Korean-annotated signal string for the equity-bond correlation.

    Args:
        corr_30d: 30-day equity-bond correlation value, or None.

    Returns:
        Human-readable signal string.
    """
    if corr_30d is None:
        return "데이터 부족"
    if corr_30d < 0:
        return "Negative (분산 효과 작동)"
    return "Positive (주식-채권 분산 약화)"


# ── Public API ────────────────────────────────────────────────────────

def compute_correlation_view(date: str, csv_path: Path = HISTORY_CSV) -> dict:
    """Compute rolling correlation view as of the given date.

    Args:
        date: Report date string in 'YYYY-MM-DD' format.
        csv_path: Path to market_data.csv. Defaults to HISTORY_CSV.

    Returns:
        Dict containing:
          - date: report date string
          - equity_bond_corr: 30/60/90-day S&P500 vs TLT correlations + signal
          - core_matrix_30d: 8×8 correlation matrix dict (30-day window)
          - core_matrix_90d: 8×8 correlation matrix dict (90-day window)
          - regime_change: True if 30d vs 90d equity-bond correlation sign differs
          - assets: list of asset codes actually found in the data
    """
    wide = _load_wide(csv_path, date)

    if wide.empty:
        return {"error": "No price data available", "date": date}

    # Daily log returns (more stable than pct_change for extreme moves)
    returns = np.log(wide / wide.shift(1))

    # ── Equity-bond correlations across windows ──────────────────────
    corr_30 = _rolling_corr_pair(returns, _EQUITY_CODE, _BOND_CODE, 30)
    corr_60 = _rolling_corr_pair(returns, _EQUITY_CODE, _BOND_CODE, 60)
    corr_90 = _rolling_corr_pair(returns, _EQUITY_CODE, _BOND_CODE, 90)

    signal = _equity_bond_signal(corr_30)

    # Regime change: 30d and 90d have opposite signs
    regime_change = False
    if corr_30 is not None and corr_90 is not None:
        regime_change = (corr_30 < 0) != (corr_90 < 0)

    # ── Core 8-asset correlation matrices ───────────────────────────
    available_assets = [c for c in CORE_ASSETS if c in returns.columns]
    matrix_30d = _corr_matrix(returns, CORE_ASSETS, 30)
    matrix_90d = _corr_matrix(returns, CORE_ASSETS, 90)

    return {
        "date": date,
        "equity_bond_corr": {
            "30d": corr_30,
            "60d": corr_60,
            "90d": corr_90,
            "signal": signal,
        },
        "core_matrix_30d": matrix_30d,
        "core_matrix_90d": matrix_90d,
        "regime_change": regime_change,
        "assets": available_assets,
    }


# ── HTML helpers ──────────────────────────────────────────────────────

def _corr_cell_color(value: float) -> str:
    """Map a correlation value in [-1, 1] to an RGB hex color string.

    +1.0 → deep red  (#d9304f)
     0.0 → white     (#ffffff)
    -1.0 → deep blue (#3b6ee6)

    Args:
        value: Correlation coefficient.

    Returns:
        CSS hex color string.
    """
    if np.isnan(value):
        return "#f0f1f6"

    v = max(-1.0, min(1.0, value))

    if v >= 0:
        # Blend white → deep red
        r = int(255 * (1 - v) + 217 * v)   # 255 → 217 (0xd9)
        g = int(255 * (1 - v) + 48 * v)    # 255 → 48  (0x30)
        b = int(255 * (1 - v) + 79 * v)    # 255 → 79  (0x4f)
    else:
        # Blend deep blue → white (v goes from -1 to 0)
        t = -v  # 0..1 as we go from 0 to -1
        r = int(59 * t + 255 * (1 - t))    # 59  (0x3b) → 255
        g = int(110 * t + 255 * (1 - t))   # 110 (0x6e) → 255
        b = int(230 * t + 255 * (1 - t))   # 230 (0xe6) → 255

    return f"#{r:02x}{g:02x}{b:02x}"


def _text_color_for_bg(hex_color: str) -> str:
    """Return black or white text color based on background luminance.

    Args:
        hex_color: CSS hex color string like '#d9304f'.

    Returns:
        '#1a1d2e' (dark) or '#ffffff' (light).
    """
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    # Relative luminance (simplified)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#1a1d2e" if luminance > 140 else "#ffffff"


def _build_heatmap_html(
    matrix: dict[str, dict[str, float]],
    assets: list[str],
    title: str,
) -> str:
    """Render a correlation matrix as an HTML table.

    Args:
        matrix: Nested dict from _corr_matrix().
        assets: Ordered list of asset codes present in the matrix.
        title: Section title displayed above the table.

    Returns:
        HTML string for the heatmap card.
    """
    if not matrix or not assets:
        return f'<div class="heatmap-card"><div class="hm-title">{title}</div><p class="muted">데이터 없음</p></div>'

    labels = [ASSET_LABELS.get(a, a) for a in assets]

    # Header row
    header_cells = '<th class="hm-corner"></th>'
    for lbl in labels:
        header_cells += f'<th class="hm-col-hdr">{lbl}</th>'

    # Data rows
    body_rows = ""
    for i, row_code in enumerate(assets):
        row_label = labels[i]
        cells = f'<td class="hm-row-hdr">{row_label}</td>'
        for col_code in assets:
            val = matrix.get(row_code, {}).get(col_code, np.nan)
            is_diag = row_code == col_code

            if is_diag:
                bg = "#e8eaf0"
                txt = "#7c8298"
                display = "1.00"
            else:
                bg = _corr_cell_color(val)
                txt = _text_color_for_bg(bg)
                display = f"{val:.2f}" if not np.isnan(val) else "—"

            cells += (
                f'<td class="hm-cell{" hm-diag" if is_diag else ""}" '
                f'style="background:{bg};color:{txt}" '
                f'title="{row_label} / {col_code}: {display}">'
                f'{display}</td>'
            )
        body_rows += f"<tr>{cells}</tr>\n"

    return f"""
<div class="heatmap-card">
  <div class="hm-title">{title}</div>
  <div class="hm-scroll">
    <table class="hm-table">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{body_rows}</tbody>
    </table>
  </div>
</div>"""


def _corr_value_display(val: Optional[float]) -> str:
    """Format optional correlation value for display."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{val:+.3f}"


def _corr_pill_class(val: Optional[float]) -> str:
    """Return CSS class suffix for a correlation value pill."""
    if val is None:
        return "neutral"
    if val < -0.1:
        return "neg"
    if val > 0.1:
        return "pos"
    return "neutral"


# ── Main HTML generator ───────────────────────────────────────────────

def generate_correlation_html(view: dict) -> str:
    """Generate a standalone HTML correlation view page.

    Args:
        view: Output dict from compute_correlation_view().

    Returns:
        Complete HTML document as a string.
    """
    if "error" in view:
        return f"<html><body><h1>Error</h1><p>{view['error']}</p></body></html>"

    report_date = view["date"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    from ._shared import nav_html
    _nav = nav_html(report_date, "correlation")

    eb = view.get("equity_bond_corr", {})
    corr_30 = eb.get("30d")
    corr_60 = eb.get("60d")
    corr_90 = eb.get("90d")
    signal = eb.get("signal", "—")
    regime_change = view.get("regime_change", False)
    assets_used = view.get("assets", [])

    matrix_30 = view.get("core_matrix_30d", {})
    matrix_90 = view.get("core_matrix_90d", {})

    # ── Key signal card ───────────────────────────────────────────────
    # Color-code: negative = green (diversification working), positive = red
    is_negative = corr_30 is not None and corr_30 < 0
    signal_color = "var(--up)" if is_negative else "var(--down)"
    signal_bg = "#ecfdf5" if is_negative else "#fff0f2"
    signal_border = "#0d9b6a" if is_negative else "#d9304f"

    regime_badge_html = ""
    if regime_change:
        regime_badge_html = """
        <span class="regime-change-badge">
          Regime Change — 30d vs 90d 부호 상이
        </span>"""

    def _pill(val: Optional[float], window: str) -> str:
        cls = _corr_pill_class(val)
        disp = _corr_value_display(val)
        return (
            f'<div class="corr-pill corr-pill-{cls}">'
            f'<span class="corr-pill-label">{window}</span>'
            f'<span class="corr-pill-val">{disp}</span>'
            f'</div>'
        )

    # Assets used note
    labels_used = [ASSET_LABELS.get(a, a) for a in assets_used]
    assets_note = ", ".join(labels_used) if labels_used else "—"

    # Build heatmaps
    heatmap_30 = _build_heatmap_html(matrix_30, assets_used, "30-Day Correlation")
    heatmap_90 = _build_heatmap_html(matrix_90, assets_used, "90-Day Correlation")

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Correlation View | {report_date}</title>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --border:#e0e3ed;
  --text:#2d3148; --muted:#7c8298;
  --primary:#F58220; --navy:#043B72; --up:#059669; --down:#dc2626;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Spoqa Han Sans Neo',-apple-system,sans-serif;
  background:var(--bg);color:var(--text);
  line-height:1.65;padding:0;
  max-width:none;margin:0
}}
.mono{{font-family:'JetBrains Mono',monospace}}
.muted{{color:var(--muted)}}

/* ── Header ─────────────────────────────────── */
.page-header{{
  display:flex;justify-content:space-between;align-items:flex-end;
  margin-bottom:28px;padding-bottom:18px;border-bottom:2px solid var(--border)
}}
.page-header h1{{font-size:24px;font-weight:700;color:#1a1d2e}}
.page-header .sub{{font-size:12px;color:var(--muted);margin-top:3px}}
.gen-time{{font-size:11px;color:var(--muted);text-align:right}}

/* ── Card base ──────────────────────────────── */
.card{{
  background:var(--card);border:1px solid var(--border);
  border-radius:14px;padding:22px 24px;margin-bottom:20px;
  box-shadow:0 1px 4px rgba(0,0,0,.05)
}}
.card-title{{
  font-size:15px;font-weight:600;color:#1a1d2e;
  margin-bottom:16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap
}}
.badge{{
  font-size:11px;padding:2px 8px;border-radius:10px;
  background:#f0f1f6;color:var(--muted);font-weight:500
}}

/* ── Key signal card ────────────────────────── */
.signal-card{{
  border:1px solid {signal_border};
  border-left:4px solid {signal_border};
  background:{signal_bg};
  border-radius:14px;padding:22px 24px;margin-bottom:20px;
  box-shadow:0 1px 4px rgba(0,0,0,.05)
}}
.signal-header{{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:14px}}
.signal-title{{font-size:14px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}}
.signal-label{{font-size:18px;font-weight:700;color:{signal_color};margin-top:4px}}
.signal-desc{{font-size:12px;color:var(--muted);margin-top:2px}}

.corr-pills{{display:flex;gap:10px;flex-wrap:wrap}}
.corr-pill{{
  display:flex;flex-direction:column;align-items:center;
  padding:8px 16px;border-radius:10px;min-width:72px;
  background:rgba(255,255,255,.7);border:1px solid var(--border)
}}
.corr-pill-label{{font-size:10px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.4px}}
.corr-pill-val{{font-size:16px;font-weight:700;font-family:'JetBrains Mono',monospace;margin-top:2px}}
.corr-pill-neg .corr-pill-val{{color:var(--up)}}
.corr-pill-pos .corr-pill-val{{color:var(--down)}}
.corr-pill-neutral .corr-pill-val{{color:var(--muted)}}

.regime-change-badge{{
  display:inline-block;padding:4px 12px;border-radius:8px;
  font-size:12px;font-weight:600;
  background:#fff8e6;color:#92400e;border:1px solid #f59e0b
}}

/* ── Heatmap layout ─────────────────────────── */
.heatmaps-row{{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:20px;
  margin-bottom:20px
}}
.heatmap-card{{
  background:var(--card);border:1px solid var(--border);
  border-radius:14px;padding:20px 22px;
  box-shadow:0 1px 4px rgba(0,0,0,.05);
  overflow:hidden
}}
.hm-title{{
  font-size:14px;font-weight:600;color:#1a1d2e;
  margin-bottom:14px
}}
.hm-scroll{{overflow-x:auto}}
.hm-table{{
  border-collapse:separate;border-spacing:3px;
  table-layout:fixed
}}
.hm-corner{{width:52px;min-width:52px}}
.hm-col-hdr{{
  font-size:10px;font-weight:700;color:var(--muted);
  text-align:center;padding:0 0 4px;
  min-width:60px;width:60px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis
}}
.hm-row-hdr{{
  font-size:10px;font-weight:700;color:var(--muted);
  text-align:right;padding-right:6px;
  white-space:nowrap;
  min-width:52px;width:52px
}}
.hm-cell{{
  min-width:60px;width:60px;
  height:50px;
  text-align:center;vertical-align:middle;
  font-size:11px;font-weight:600;
  font-family:'JetBrains Mono',monospace;
  border-radius:4px;
  cursor:default;
  transition:filter .15s
}}
.hm-cell:hover{{filter:brightness(.92)}}
.hm-diag{{opacity:.75}}

/* ── Legend ─────────────────────────────────── */
.legend-row{{
  display:flex;align-items:center;gap:10px;
  font-size:11px;color:var(--muted);
  margin-top:12px;flex-wrap:wrap
}}
.legend-bar{{
  width:160px;height:10px;border-radius:4px;flex-shrink:0;
  background:linear-gradient(to right,#3b6ee6,#ffffff,#d9304f)
}}
.legend-labels{{display:flex;justify-content:space-between;width:160px;font-size:10px}}

/* ── Meta footer ─────────────────────────────── */
.meta-section{{
  background:var(--card);border:1px solid var(--border);
  border-radius:14px;padding:16px 22px;margin-bottom:20px;
  font-size:12px;color:var(--muted)
}}
.meta-section b{{color:var(--text)}}

.page-footer{{
  text-align:center;font-size:11px;color:#94a3b8;
  padding:16px 0 4px;margin-top:8px;
  border-top:1px solid var(--border)
}}
.back-link{{
  display:inline-block;margin-bottom:20px;
  font-size:13px;color:var(--primary);text-decoration:none
}}
.back-link:hover{{text-decoration:underline}}

@media(max-width:900px){{
  .heatmaps-row{{grid-template-columns:1fr}}
}}
@media(max-width:600px){{
  .page-header{{flex-direction:column;align-items:flex-start;gap:8px}}
  .signal-header{{flex-direction:column}}
  .corr-pills{{gap:6px}}
}}
</style>
</head>
<body>
{_nav}
<div style="max-width:1400px;margin:0 auto;padding:28px 24px 48px">
<div class="page-header">
  <div>
    <h1>Correlation View</h1>
    <div class="sub">Rolling asset correlations — 30 / 60 / 90-day windows | View Agent</div>
  </div>
  <div class="gen-time">
    <div style="font-size:13px;font-weight:600;color:#1a1d2e;margin-bottom:3px">As of {report_date}</div>
    <div>Generated: {now}</div>
  </div>
</div>

<!-- Key signal card -->
<div class="signal-card">
  <div class="signal-header">
    <div>
      <div class="signal-title">Equity–Bond Correlation (S&amp;P 500 vs TLT)</div>
      <div class="signal-label">{signal}</div>
      <div class="signal-desc muted" style="margin-top:6px">
        음수 상관관계 = 분산 효과 정상 작동 &nbsp;|&nbsp; 양수 상관관계 = 주식·채권 동반 하락 위험
      </div>
      {regime_badge_html}
    </div>
    <div class="corr-pills">
      {_pill(corr_30, "30D")}
      {_pill(corr_60, "60D")}
      {_pill(corr_90, "90D")}
    </div>
  </div>
</div>

<!-- Heatmaps -->
<div class="heatmaps-row">
  {heatmap_30}
  {heatmap_90}
</div>

<!-- Color legend -->
<div class="card" style="padding:16px 22px">
  <div class="card-title" style="margin-bottom:10px">Color Legend</div>
  <div class="legend-row">
    <span>Deep Blue (−1.0)</span>
    <div>
      <div class="legend-bar"></div>
      <div class="legend-labels"><span>−1.0</span><span>0.0</span><span>+1.0</span></div>
    </div>
    <span>Deep Red (+1.0)</span>
    <span style="margin-left:16px">Diagonal = 자기 자신 (1.00, 회색)</span>
  </div>
</div>

<!-- Metadata -->
<div class="meta-section">
  <b>Assets used ({len(assets_used)}):</b> {assets_note}
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <b>Returns:</b> Log-return (ln(P_t / P_t-1))
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <b>Method:</b> Pearson correlation on trailing window
  &nbsp;&nbsp;|&nbsp;&nbsp;
  <b>Source:</b> history/market_data.csv
</div>

<div class="page-footer">
  Correlation View | Rolling 30/60/90-day correlations | View Agent
</div>
</div>
</body>
</html>'''


# ── Report entry point ────────────────────────────────────────────────

def generate_report(date: str, csv_path: Path = HISTORY_CSV) -> str:
    """Compute correlation view and save HTML report to OUTPUT_DIR.

    Args:
        date: Report date string in 'YYYY-MM-DD' format.
        csv_path: Path to market_data.csv. Defaults to HISTORY_CSV.

    Returns:
        Absolute path string to the generated HTML file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    view = compute_correlation_view(date, csv_path)
    html = generate_correlation_html(view)

    out_path = OUTPUT_DIR / f"{date}.html"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    return str(out_path)


def main() -> None:
    """CLI entry point.

    Examples::

        python -m portfolio.view.correlation_view --date 2026-04-13 --html
        python -m portfolio.view.correlation_view --date 2026-04-13
    """
    parser = argparse.ArgumentParser(
        description="Correlation view — rolling asset correlation heatmaps"
    )
    parser.add_argument("--date", required=True, help="Report date (YYYY-MM-DD)")
    parser.add_argument("--html", action="store_true", help="Generate and save HTML report")
    parser.add_argument("--csv", default=None, help="Override CSV path (default: HISTORY_CSV)")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else HISTORY_CSV

    if args.html:
        path = generate_report(args.date, csv_path)
        print(f"HTML report: {path}")
        return

    # Console summary
    view = compute_correlation_view(args.date, csv_path)

    if "error" in view:
        print(f"Error: {view['error']}", file=sys.stderr)
        sys.exit(1)

    eb = view["equity_bond_corr"]
    print(f"\n{'='*60}")
    print(f"  Correlation View as of {view['date']}")
    print(f"{'='*60}")
    print(f"\n  Equity-Bond (S&P500 vs TLT):")
    print(f"    30D: {_corr_value_display(eb['30d'])}")
    print(f"    60D: {_corr_value_display(eb['60d'])}")
    print(f"    90D: {_corr_value_display(eb['90d'])}")
    print(f"  Signal: {eb['signal']}")

    if view["regime_change"]:
        print("\n  [!] Regime Change detected: 30d vs 90d correlation sign differs")

    assets = view["assets"]
    print(f"\n  Assets used ({len(assets)}): {', '.join(ASSET_LABELS.get(a, a) for a in assets)}")

    matrix_30 = view.get("core_matrix_30d", {})
    if matrix_30 and assets:
        print(f"\n  30-Day Correlation Matrix:")
        header = f"{'':>10s}" + "".join(f"  {ASSET_LABELS.get(a, a):>8s}" for a in assets)
        print(f"  {header}")
        for row in assets:
            row_label = ASSET_LABELS.get(row, row)
            vals = "".join(
                f"  {matrix_30.get(row, {}).get(col, float('nan')):>+8.3f}"
                for col in assets
            )
            print(f"  {row_label:>10s}{vals}")
    print()


if __name__ == "__main__":
    main()
