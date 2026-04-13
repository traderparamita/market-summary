"""Macro economic view — Real macro indicators analysis.

Analyzes macro indicators (GDP, inflation, employment, policy, credit)
from history/macro_indicators.csv.

NO asset allocation. For allocation view, see portfolio.view.allocation_view.

Generates standalone HTML report to output/view/macro/.

Usage:
    python -m portfolio.view.macro_view --date 2026-04-09 --html
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = ROOT / "output" / "view" / "macro"
HISTORY_CSV = ROOT / "history" / "macro_indicators.csv"


def load_macro_data(csv_path: Path = HISTORY_CSV) -> pd.DataFrame:
    """Load macro indicators CSV."""
    if not csv_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv_path, parse_dates=["DATE"])
    return df.sort_values("DATE")


def compute_macro_view(date: str, csv_path: Path = HISTORY_CSV) -> dict:
    """Compute macro view as of a given date."""
    df = load_macro_data(csv_path)
    if df.empty:
        return {"error": "No macro data available"}

    target = pd.Timestamp(date)
    df = df[df["DATE"] <= target]

    if df.empty:
        return {"error": f"No data available before {date}"}

    # Get latest value for each indicator
    latest = df.groupby("INDICATOR_CODE").last().reset_index()

    # Group by category/region
    us_growth = latest[(latest["CATEGORY"] == "growth") & (latest["REGION"] == "US")]
    us_inflation = latest[(latest["CATEGORY"] == "inflation") & (latest["REGION"] == "US")]
    us_employment = latest[(latest["CATEGORY"] == "employment") & (latest["REGION"] == "US")]
    us_sentiment = latest[(latest["CATEGORY"] == "sentiment") & (latest["REGION"] == "US")]
    us_policy = latest[(latest["CATEGORY"] == "policy") & (latest["REGION"] == "US")]
    us_credit = latest[(latest["CATEGORY"] == "credit") & (latest["REGION"] == "US")]

    kr_growth = latest[(latest["CATEGORY"] == "growth") & (latest["REGION"] == "KR")]
    kr_inflation = latest[(latest["CATEGORY"] == "inflation") & (latest["REGION"] == "KR")]
    kr_employment = latest[(latest["CATEGORY"] == "employment") & (latest["REGION"] == "KR")]
    kr_sentiment = latest[(latest["CATEGORY"] == "sentiment") & (latest["REGION"] == "KR")]
    kr_policy = latest[(latest["CATEGORY"] == "policy") & (latest["REGION"] == "KR")]

    global_indicators = latest[latest["REGION"] == "GLOBAL"]

    # Format indicator groups
    def format_group(group_df: pd.DataFrame) -> list:
        if group_df.empty:
            return []
        return [
            {
                "code": row["INDICATOR_CODE"],
                "value": float(row["VALUE"]) if not np.isnan(row["VALUE"]) else None,
                "unit": row["UNIT"],
                "date": row["DATE"].strftime("%Y-%m-%d"),
                "category": row["CATEGORY"],
            }
            for _, row in group_df.iterrows()
        ]

    return {
        "date": date,
        "us": {
            "growth": format_group(us_growth),
            "inflation": format_group(us_inflation),
            "employment": format_group(us_employment),
            "sentiment": format_group(us_sentiment),
            "policy": format_group(us_policy),
            "credit": format_group(us_credit),
        },
        "kr": {
            "growth": format_group(kr_growth),
            "inflation": format_group(kr_inflation),
            "employment": format_group(kr_employment),
            "sentiment": format_group(kr_sentiment),
            "policy": format_group(kr_policy),
        },
        "global": format_group(global_indicators),
    }


# ── HTML Generation ───────────────────────────────────────────────

def _indicator_row(ind: dict) -> str:
    """Format single indicator row."""
    val = ind["value"]
    if val is None:
        val_str = "—"
    elif ind["unit"] == "%":
        val_str = f"{val:.2f}%"
    elif ind["unit"] == "bp":
        val_str = f"{val:.0f}bp"
    elif ind["unit"] == "k":
        val_str = f"{val:.0f}k"
    else:
        val_str = f"{val:.2f}"

    return f"""
    <tr>
      <td class="mono">{ind['code']}</td>
      <td class="right mono value-cell">{val_str}</td>
      <td class="right muted">{ind['date']}</td>
    </tr>
    """


def _section_html(title: str, indicators: list) -> str:
    """Format section HTML."""
    if not indicators:
        return f"""
        <div class="section">
          <h3>{title}</h3>
          <p class="muted">No data available</p>
        </div>
        """

    rows = "".join([_indicator_row(ind) for ind in indicators])
    return f"""
    <div class="section">
      <h3>{title}</h3>
      <table class="indicator-table">
        <thead>
          <tr>
            <th style="text-align:left">Indicator</th>
            <th style="text-align:right">Value</th>
            <th style="text-align:right">As of</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>
    """


def generate_macro_html(view: dict) -> str:
    """Generate macro view HTML."""
    if "error" in view:
        return f"<html><body><h1>Error</h1><p>{view['error']}</p></body></html>"

    report_date = view["date"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    us = view["us"]
    kr = view["kr"]
    global_ind = view["global"]

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Macro Economic View | {report_date}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --border:#e0e3ed; --text:#2d3148; --muted:#7c8298;
  --primary:#3b6ee6; --up:#0d9b6a; --down:#d9304f;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans KR',-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.65;padding:28px 24px;max-width:1400px;margin:0 auto}}
.mono{{font-family:'JetBrains Mono',monospace}}
.muted{{color:var(--muted)}}
.right{{text-align:right}}

.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px;padding-bottom:20px;border-bottom:2px solid var(--border)}}
.header h1{{font-size:26px;font-weight:700;color:#1a1d2e}}
.header .meta{{font-size:13px;color:var(--muted);margin-top:4px}}
.header .gen{{font-size:12px;color:var(--muted);text-align:right}}

.region-title{{font-size:20px;font-weight:700;color:#1a1d2e;margin:28px 0 16px;padding-bottom:8px;border-bottom:2px solid var(--primary)}}

.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px;margin-bottom:28px}}

.section{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.04)}}
.section h3{{font-size:15px;font-weight:600;color:#1a1d2e;margin-bottom:14px}}

.indicator-table{{width:100%;border-collapse:collapse;font-size:13px}}
.indicator-table thead tr{{background:#f8fafc;border-bottom:1px solid var(--border)}}
.indicator-table th{{padding:8px 10px;font-size:12px;color:var(--muted);font-weight:600}}
.indicator-table td{{padding:8px 10px;border-bottom:1px solid #f1f5f9}}
.indicator-table tbody tr:hover{{background:#f8fafc}}
.value-cell{{font-weight:600;color:#1a1d2e}}

.footer{{text-align:center;font-size:11px;color:#94a3b8;padding:20px 0 4px;margin-top:32px;border-top:1px solid var(--border)}}
.back-link{{display:inline-block;margin-bottom:20px;font-size:13px;color:var(--primary);text-decoration:none}}
.back-link:hover{{text-decoration:underline}}

@media(max-width:768px){{
  .grid{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>

<a class="back-link" href="../../index.html">← Back to Index</a>

<div class="header">
  <div>
    <h1>Macro Economic View</h1>
    <div class="meta">Real macro indicators | View Agent</div>
  </div>
  <div class="gen">
    <div style="font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:4px">As of {report_date}</div>
    <div>Generated: {now}</div>
  </div>
</div>

<div class="region-title">🇺🇸 United States</div>
<div class="grid">
  {_section_html("Growth", us["growth"])}
  {_section_html("Inflation", us["inflation"])}
  {_section_html("Employment", us["employment"])}
  {_section_html("Sentiment", us["sentiment"])}
  {_section_html("Policy", us["policy"])}
  {_section_html("Credit", us["credit"])}
</div>

<div class="region-title">🇰🇷 Korea</div>
<div class="grid">
  {_section_html("Growth", kr["growth"])}
  {_section_html("Inflation", kr["inflation"])}
  {_section_html("Employment", kr["employment"])}
  {_section_html("Sentiment", kr["sentiment"])}
  {_section_html("Policy", kr["policy"])}
</div>

<div class="region-title">🌍 Global</div>
<div class="grid">
  {_section_html("Risk & FX", global_ind)}
</div>

<div class="footer">Macro Economic View | GDP, Inflation, Employment, Policy, Credit | View Agent</div>

</body>
</html>'''


def generate_report(date: str, csv_path: Path = HISTORY_CSV) -> str:
    """Generate macro view HTML report."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    view = compute_macro_view(date, csv_path)
    html = generate_macro_html(view)

    out_path = OUTPUT_DIR / f"{date}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(out_path)


def main():
    parser = argparse.ArgumentParser(description="Macro economic view")
    parser.add_argument("--date", required=True, help="View date (YYYY-MM-DD)")
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    args = parser.parse_args()

    if args.html:
        path = generate_report(args.date)
        print(f"HTML report: {path}")
        return

    view = compute_macro_view(args.date)

    if "error" in view:
        print(f"Error: {view['error']}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Macro Economic View as of {view['date']}")
    print(f"{'='*60}")

    print(f"\n🇺🇸 United States")
    for category, indicators in view["us"].items():
        if indicators:
            print(f"\n  {category.upper()}:")
            for ind in indicators:
                val = ind["value"]
                val_str = f"{val:.2f}" if val else "—"
                print(f"    {ind['code']:<20s} {val_str:>10s} {ind['unit']}")

    print(f"\n🇰🇷 Korea")
    for category, indicators in view["kr"].items():
        if indicators:
            print(f"\n  {category.upper()}:")
            for ind in indicators:
                val = ind["value"]
                val_str = f"{val:.2f}" if val else "—"
                print(f"    {ind['code']:<20s} {val_str:>10s} {ind['unit']}")

    if view["global"]:
        print(f"\n🌍 Global")
        for ind in view["global"]:
            val = ind["value"]
            val_str = f"{val:.2f}" if val else "—"
            print(f"  {ind['code']:<20s} {val_str:>10s} {ind['unit']}")

    print()


if __name__ == "__main__":
    main()
