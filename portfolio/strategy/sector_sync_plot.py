"""
KR vs US GICS 섹터 동조화 시각화 (matplotlib → base64 → 자체 포함 HTML)
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import base64, io, json
from pathlib import Path

# ── 섹터 매핑 ────────────────────────────────────────────────────────────────
SECTOR_MAP = [
    ("IT / Technology",    "SC_US_TECH",    "IX_KR_IT"),
    ("커뮤니케이션",          "SC_US_COMM",    "IX_KR_COMM"),
    ("경기소비재",            "SC_US_DISCR",   "IX_KR_DISCR"),
    ("필수소비재",            "SC_US_STAPLES", "IX_KR_STAPLES"),
    ("헬스케어",             "SC_US_HEALTH",  "IX_KR_HEALTH"),
    ("금융",                "SC_US_FIN",     "IX_KR_FIN"),
    ("산업재",              "SC_US_INDU",    "IX_KR_INDU"),
    ("에너지",              "SC_US_ENERGY",  "IX_KR_ENERGY"),
    ("소재 / 철강",          "SC_US_MATL",    "IX_KR_STEEL"),
    ("유틸 ↔ 중공업",        "SC_US_UTIL",    "IX_KR_HEAVY"),
    ("REIT ↔ 건설",         "SC_US_REIT",    "IX_KR_CONSTR"),
]

PALETTE = [
    "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f",
    "#edc948","#b07aa1","#ff9da7","#9c755f","#bab0ac","#a0cbe8",
]

import matplotlib.font_manager as fm
_kr_font = fm.FontProperties(fname="/System/Library/Fonts/AppleSDGothicNeo.ttc")
plt.rcParams.update({
    "figure.facecolor":  "#0f1117",
    "axes.facecolor":    "#1a2236",
    "axes.edgecolor":    "#2d3748",
    "axes.labelcolor":   "#94a3b8",
    "xtick.color":       "#64748b",
    "ytick.color":       "#64748b",
    "text.color":        "#e2e8f0",
    "grid.color":        "#1e2535",
    "grid.linewidth":    0.6,
    "legend.facecolor":  "#1a2236",
    "legend.edgecolor":  "#2d3748",
    "font.size":          9,
    "font.family":       "Apple SD Gothic Neo",
})
fm.fontManager.addfont("/System/Library/Fonts/AppleSDGothicNeo.ttc")


def load_prices(csv: str, start: str) -> pd.DataFrame:
    df = pd.read_csv(csv, parse_dates=["DATE"])
    codes = [c for _, us, kr in SECTOR_MAP for c in [us, kr]]
    df = df[df["INDICATOR_CODE"].isin(codes) & (df["DATE"] >= start)]
    piv = df.pivot_table(index="DATE", columns="INDICATOR_CODE", values="CLOSE", aggfunc="last")
    return piv.sort_index().ffill()


def cum_ret(prices: pd.DataFrame) -> pd.DataFrame:
    return (prices / prices.iloc[0] - 1) * 100


def rolling_corr(p: pd.DataFrame, us: str, kr: str, w: int) -> pd.Series:
    return p[us].pct_change().rolling(w).corr(p[kr].pct_change())


def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def make_sector_card(prices: pd.DataFrame, cum: pd.DataFrame,
                     name: str, us_code: str, kr_code: str,
                     color: str) -> str:
    """Returns base64 PNG for one sector (cum-ret + rolling corr)."""
    dates = prices.index

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.5, 3.8),
                                   facecolor="#1a2236", sharex=True)
    fig.subplots_adjust(hspace=0.08, left=0.08, right=0.97, top=0.88, bottom=0.1)

    # ── 누적수익률 ─────────────────────────────────────
    ax1.plot(dates, cum[us_code], color="#60a5fa", lw=1.4, label="US")
    ax1.plot(dates, cum[kr_code], color=color,    lw=1.4, label="KR")
    ax1.axhline(0, color="#475569", lw=0.8, ls="--")
    ax1.set_ylabel("누적수익률 (%)", fontsize=8)
    ax1.legend(fontsize=8, loc="upper left")
    ax1.grid(True, axis="y")

    # ── 롤링 상관관계 ──────────────────────────────────
    c60  = rolling_corr(prices, us_code, kr_code, 60)
    c120 = rolling_corr(prices, us_code, kr_code, 120)
    ax2.plot(dates, c60,  color="#fbbf24", lw=1.2, label="60일")
    ax2.plot(dates, c120, color="#818cf8", lw=1.2, ls="--", label="120일")
    ax2.axhline(0,   color="#475569", lw=0.8, ls="--")
    ax2.axhline(0.6, color="#34d399", lw=0.6, ls=":", alpha=0.6)
    ax2.set_ylim(-1, 1)
    ax2.set_ylabel("롤링 상관관계", fontsize=8)
    ax2.legend(fontsize=8, loc="lower left")
    ax2.grid(True, axis="y")

    # ── 최신 상관 값 표시 ──────────────────────────────
    lc60  = c60.dropna().iloc[-1] if not c60.dropna().empty  else None
    lc120 = c120.dropna().iloc[-1] if not c120.dropna().empty else None
    tag = ""
    if lc60 is not None:
        tag += f"60일: {lc60:.3f}"
    if lc120 is not None:
        tag += f"  |  120일: {lc120:.3f}"
    fig.suptitle(f"{name}  —  {tag}", fontsize=10, color="#f1f5f9", fontweight="bold")

    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


def make_summary_fig(prices: pd.DataFrame, cum: pd.DataFrame) -> str:
    """4×3 grid overview: all sectors cumulative returns."""
    fig, axes = plt.subplots(4, 3, figsize=(15, 10), facecolor="#0f1117")
    fig.suptitle("KR vs US 섹터 누적수익률 Overview", fontsize=14,
                 color="#f8fafc", fontweight="bold", y=0.98)

    all_axes = axes.flatten()
    for i, (name, us_code, kr_code) in enumerate(SECTOR_MAP):
        ax = all_axes[i]
        color = PALETTE[i]
        dates = prices.index
        ax.set_facecolor("#1a2236")
        ax.plot(dates, cum[us_code], color="#60a5fa", lw=1.3, label="US")
        ax.plot(dates, cum[kr_code], color=color,    lw=1.3, label="KR")
        ax.axhline(0, color="#475569", lw=0.7, ls="--")
        ax.set_title(name, fontsize=8.5, color="#f1f5f9", pad=3)
        ax.tick_params(labelsize=7)
        ax.grid(True, axis="y", color="#1e2535")
        ax.set_ylabel("%", fontsize=7)
        # 최신 corr
        c = prices[us_code].pct_change().rolling(60).corr(prices[kr_code].pct_change())
        lc = c.dropna().iloc[-1] if not c.dropna().empty else None
        if lc is not None:
            clr = "#34d399" if lc >= 0.6 else ("#fbbf24" if lc >= 0.3 else "#f87171")
            ax.text(0.99, 0.04, f"r={lc:.2f}", transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=8, color=clr, fontweight="bold")
        leg = ax.legend(fontsize=7, loc="upper left",
                        facecolor="#1a2236", edgecolor="#2d3748")
        for t in leg.get_texts(): t.set_color("#94a3b8")

    # 마지막 빈 칸 숨기기
    all_axes[-1].set_visible(False)

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


def make_corr_heatmap(prices: pd.DataFrame) -> str:
    """현재 시점 60일 상관 히트맵 (11 섹터 쌍)."""
    names, corrs = [], []
    for name, us_code, kr_code in SECTOR_MAP:
        c = prices[us_code].pct_change().rolling(60).corr(prices[kr_code].pct_change())
        lc = c.dropna().iloc[-1] if not c.dropna().empty else np.nan
        names.append(name)
        corrs.append(lc)
    corrs = np.array(corrs)

    fig, ax = plt.subplots(figsize=(9, 3.5), facecolor="#0f1117")
    ax.set_facecolor("#1a2236")
    colors_bar = ["#f87171" if v < 0.3 else ("#fbbf24" if v < 0.6 else "#34d399") for v in corrs]
    bars = ax.barh(names[::-1], corrs[::-1], color=colors_bar[::-1], height=0.6)
    ax.axvline(0,   color="#475569", lw=0.8, ls="--")
    ax.axvline(0.6, color="#34d399", lw=0.8, ls=":", alpha=0.7)
    ax.axvline(0.3, color="#fbbf24", lw=0.8, ls=":", alpha=0.7)
    ax.set_xlim(-1, 1)
    ax.set_xlabel("60일 롤링 상관계수 (최신)", fontsize=9)
    ax.set_title("섹터별 KR–US 동조화 현황 (60일)", fontsize=11, color="#f8fafc",
                 fontweight="bold", pad=8)
    for bar, v in zip(bars[::-1], corrs):
        ax.text(v + 0.02 if v >= 0 else v - 0.02, bar.get_y() + bar.get_height()/2,
                f"{v:.3f}", va="center", ha="left" if v >= 0 else "right",
                fontsize=8.5, color="#f1f5f9")
    ax.grid(True, axis="x", color="#1e2535")
    fig.tight_layout()
    b64 = fig_to_b64(fig)
    plt.close(fig)
    return b64


def render_html(prices: pd.DataFrame, out_path: str):
    cum = cum_ret(prices)

    overview_b64  = make_summary_fig(prices, cum)
    heatmap_b64   = make_corr_heatmap(prices)
    card_b64s     = [
        make_sector_card(prices, cum, name, us, kr, PALETTE[i])
        for i, (name, us, kr) in enumerate(SECTOR_MAP)
    ]

    # summary table data
    rows = []
    for i, (name, us, kr) in enumerate(SECTOR_MAP):
        c60  = prices[us].pct_change().rolling(60).corr(prices[kr].pct_change())
        c120 = prices[us].pct_change().rolling(120).corr(prices[kr].pct_change())
        lc60  = round(c60.dropna().iloc[-1],  3) if not c60.dropna().empty  else None
        lc120 = round(c120.dropna().iloc[-1], 3) if not c120.dropna().empty else None
        us_ret = round(cum[us].iloc[-1], 1)
        kr_ret = round(cum[kr].iloc[-1], 1)
        rows.append((name, us, kr, lc60, lc120, us_ret, kr_ret))

    def corr_style(v):
        if v is None: return "color:#64748b"
        if v >= 0.6:  return "color:#34d399;font-weight:600"
        if v >= 0.3:  return "color:#fbbf24"
        return "color:#f87171"

    def ret_style(v):
        return "color:#34d399" if v >= 0 else "color:#f87171"

    table_rows = ""
    for name, us, kr, c60, c120, us_ret, kr_ret in rows:
        table_rows += f"""<tr>
          <td style="font-weight:600;text-align:left">{name}</td>
          <td style="color:#64748b;font-size:11px">{us}</td>
          <td style="color:#64748b;font-size:11px">{kr}</td>
          <td style="{corr_style(c60)}">{c60 if c60 is not None else '-'}</td>
          <td style="{corr_style(c120)}">{c120 if c120 is not None else '-'}</td>
          <td style="{ret_style(us_ret)}">{'+' if us_ret>=0 else ''}{us_ret}%</td>
          <td style="{ret_style(kr_ret)}">{'+' if kr_ret>=0 else ''}{kr_ret}%</td>
        </tr>"""

    cards_html = ""
    for i, (name, us, kr) in enumerate(SECTOR_MAP):
        cards_html += f"""
        <div class="card">
          <div class="card-title">{name}</div>
          <div class="card-meta">{us} (SPDR) &nbsp;vs&nbsp; {kr} (KOSPI200)</div>
          <img src="data:image/png;base64,{card_b64s[i]}" style="width:100%;border-radius:6px">
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>KR vs US 섹터 동조화 분석</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Pretendard', sans-serif; background: #0f1117; color: #e2e8f0; }}
  h1 {{ text-align:center; padding:28px 0 4px; font-size:22px; color:#f8fafc; }}
  .subtitle {{ text-align:center; color:#94a3b8; font-size:13px; margin-bottom:28px; }}
  h2 {{ font-size:15px; color:#94a3b8; margin:28px 20px 12px; border-left:3px solid #4e79a7; padding-left:10px; }}
  .overview-wrap {{ max-width:1260px; margin:0 auto; padding:0 16px 8px; text-align:center; }}
  .overview-wrap img {{ width:100%; border-radius:10px; }}
  .heatmap-wrap {{ max-width:820px; margin:0 auto; padding:0 16px 8px; text-align:center; }}
  .heatmap-wrap img {{ width:100%; border-radius:10px; }}
  .table-wrap {{ max-width:920px; margin:0 auto 12px; padding:0 16px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ background:#1e2535; color:#94a3b8; padding:9px 12px; text-align:center; border-bottom:1px solid #2d3748; }}
  td {{ padding:7px 12px; text-align:center; border-bottom:1px solid #1e2535; }}
  tr:hover td {{ background:#1a2236; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(580px,1fr)); gap:20px; padding:0 20px 48px; max-width:1300px; margin:0 auto; }}
  .card {{ background:#1a2236; border-radius:12px; padding:16px; border:1px solid #2d3748; }}
  .card-title {{ font-size:14px; font-weight:700; margin-bottom:3px; color:#f1f5f9; }}
  .card-meta  {{ font-size:11px; color:#64748b; margin-bottom:10px; }}
</style>
</head>
<body>
<h1>KR vs US 섹터 동조화 분석</h1>
<p class="subtitle">US: SPDR Sector ETF &nbsp;|&nbsp; KR: KOSPI200 섹터지수 &nbsp;|&nbsp; 기준: 2020-01-01</p>

<h2>Overview — 11개 섹터 누적수익률</h2>
<div class="overview-wrap">
  <img src="data:image/png;base64,{overview_b64}">
</div>

<h2>동조화 현황 — 60일 롤링 상관계수</h2>
<div class="heatmap-wrap">
  <img src="data:image/png;base64,{heatmap_b64}">
</div>

<h2>Summary 테이블</h2>
<div class="table-wrap">
  <table>
    <thead><tr>
      <th>섹터</th><th>US 코드</th><th>KR 코드</th>
      <th>상관 60일</th><th>상관 120일</th>
      <th>US 누적수익률</th><th>KR 누적수익률</th>
    </tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>

<h2>섹터별 상세 — 누적수익률 + 롤링 상관관계</h2>
<div class="grid">{cards_html}</div>
</body>
</html>"""

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--out",   default="output/sector_sync.html")
    args = ap.parse_args()

    prices = load_prices("history/market_data.csv", start=args.start)
    print(f"Loaded {len(prices)} days × {len(prices.columns)} series")
    render_html(prices, args.out)
