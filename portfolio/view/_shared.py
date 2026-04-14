"""Shared design system for all View Agent HTML pages.

Mirae Asset Life Insurance brand guideline:
- Primary:  #F58220 (Mirae Asset Orange)
- Navy:     #043B72 (Mirae Asset Blue)
- Font:     Spoqa Han Sans Neo
"""

from __future__ import annotations

# ── All views keyed by their output subdirectory name ────────────────────

ALL_VIEWS = [
    # Phase 1
    ("price",       "가격신호",   "P1"),
    ("macro",       "거시지표",   "P1"),
    ("correlation", "상관관계",   "P1"),
    ("regime",      "국면해설",   "P1"),
    # Phase 2
    ("country",     "국가",       "P2"),
    ("sector",      "섹터",       "P2"),
    ("bond",        "채권",       "P2"),
    ("style",       "스타일",     "P2"),
    ("allocation",  "배분안",     "P2"),
    ("alternative", "대체자산",   "P2"),

]

# ── Base CSS ──────────────────────────────────────────────────────────────

BASE_CSS = """
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --bg:            #f4f5f9;
  --card:          #ffffff;
  --border:        #e0e3ed;
  --text:          #2d3148;
  --muted:         #7c8298;
  --primary:       #F58220;
  --primary-light: #fff3e6;
  --navy:          #043B72;
  --up:            #059669;
  --down:          #dc2626;
  --up-bg:         #ecfdf5;
  --down-bg:       #fef2f2;
  --neutral-bg:    #f3f4f6;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Spoqa Han Sans Neo', -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.65;
}

.mono { font-family: 'JetBrains Mono', monospace; }
.muted { color: var(--muted); }
.up    { color: var(--up); }
.down  { color: var(--down); }

/* ── Navigation ── */
.ma-nav {
  background: var(--navy);
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(4,59,114,.25);
}
.ma-nav-inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 0;
  height: 48px;
  overflow-x: auto;
  scrollbar-width: none;
}
.ma-nav-inner::-webkit-scrollbar { display: none; }

.ma-logo {
  color: #ffffff;
  font-weight: 700;
  font-size: 14px;
  text-decoration: none;
  white-space: nowrap;
  padding-right: 20px;
  border-right: 1px solid rgba(255,255,255,.2);
  margin-right: 16px;
  letter-spacing: -.2px;
}
.ma-logo span {
  display: inline-block;
  width: 8px;
  height: 8px;
  background: var(--primary);
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.ma-nav-group {
  font-size: 10px;
  font-weight: 700;
  color: var(--primary);
  letter-spacing: .8px;
  text-transform: uppercase;
  padding: 0 8px 0 4px;
  white-space: nowrap;
}
.ma-nav-link {
  color: rgba(255,255,255,.72);
  text-decoration: none;
  font-size: 13px;
  padding: 4px 10px;
  border-radius: 6px;
  white-space: nowrap;
  transition: all .15s;
}
.ma-nav-link:hover {
  color: #fff;
  background: rgba(255,255,255,.1);
}
.ma-nav-link.current {
  color: #fff;
  background: var(--primary);
  font-weight: 600;
}
.ma-nav-sep {
  width: 1px;
  height: 16px;
  background: rgba(255,255,255,.15);
  margin: 0 8px;
  flex-shrink: 0;
}

/* ── Page wrapper ── */
.ma-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 28px 24px 48px;
}

/* ── Page header ── */
.ma-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  padding-bottom: 18px;
  border-bottom: 3px solid var(--primary);
}
.ma-header h1 {
  font-size: 22px;
  font-weight: 700;
  color: var(--navy);
}
.ma-header .meta {
  font-size: 12px;
  color: var(--muted);
  margin-top: 4px;
}
.ma-header .date-badge {
  background: var(--primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 6px;
}

/* ── Card / Section ── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.05);
  position: relative;
}
.card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--primary), #FAAF72);
  border-radius: 12px 12px 0 0;
}
.card h2 {
  font-size: 15px;
  font-weight: 700;
  color: var(--navy);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.card h3 {
  font-size: 13px;
  font-weight: 700;
  color: var(--navy);
  margin-bottom: 12px;
}

/* ── Summary row of cards ── */
.stat-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  background: #f8f9fc;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 18px;
  min-width: 130px;
  flex: 1;
}
.stat-card .label {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 4px;
}
.stat-card .value {
  font-size: 20px;
  font-weight: 700;
  color: var(--navy);
  font-family: 'JetBrains Mono', monospace;
}
.stat-card .sub {
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
}

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; }
thead tr { background: #f0f3fa; }
th {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 700;
  color: var(--navy);
  text-align: left;
  border-bottom: 2px solid var(--border);
  letter-spacing: .4px;
}
td {
  padding: 8px 12px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
tbody tr:hover td { background: #fafbff; }

/* ── OW / N / UW badges ── */
.ow  { background: #dcfce7; color: #15803d; padding: 2px 10px; border-radius: 6px; font-weight: 700; font-size: 12px; }
.ow2 { background: #bbf7d0; color: #15803d; padding: 2px 10px; border-radius: 6px; font-weight: 700; font-size: 12px; }
.neutral-b { background: var(--neutral-bg); color: #6b7280; padding: 2px 10px; border-radius: 6px; font-weight: 600; font-size: 12px; }
.uw  { background: #fef3c7; color: #d97706; padding: 2px 10px; border-radius: 6px; font-weight: 700; font-size: 12px; }
.uw2 { background: var(--down-bg); color: var(--down); padding: 2px 10px; border-radius: 6px; font-weight: 700; font-size: 12px; }

/* ── Regime badges ── */
.regime-goldilocks { background: #dcfce7; color: #15803d; padding: 3px 12px; border-radius: 8px; font-weight: 700; font-size: 13px; }
.regime-reflation  { background: #fef3c7; color: #d97706; padding: 3px 12px; border-radius: 8px; font-weight: 700; font-size: 13px; }
.regime-stagflation{ background: var(--down-bg); color: var(--down); padding: 3px 12px; border-radius: 8px; font-weight: 700; font-size: 13px; }
.regime-deflation  { background: #dbeafe; color: #1d4ed8; padding: 3px 12px; border-radius: 8px; font-weight: 700; font-size: 13px; }

/* ── Utility ── */
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #f0f1f6; color: var(--muted); font-weight: 500; }
.section-label { font-size: 10px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .6px; }

/* ── Footer ── */
.ma-footer {
  text-align: center;
  font-size: 12px;
  color: var(--muted);
  padding: 24px 0 8px;
  border-top: 1px solid var(--border);
  margin-top: 32px;
}
.ma-footer a { color: var(--primary); text-decoration: none; }

/* ── Responsive ── */
@media (max-width: 768px) {
  .ma-page { padding: 16px; }
  .stat-grid { flex-direction: column; }
}

/* ── Drag selection ── */
::selection { background: #F58220; color: #fff; }
"""

# ── Nav-only CSS (self-contained; injected via nav_html for views with own CSS) ──

NAV_CSS = (
    ".ma-nav{background:var(--navy);padding:0 24px;position:sticky;top:0;z-index:100;"
    "box-shadow:0 2px 8px rgba(4,59,114,.25)}\n"
    ".ma-nav-inner{max-width:1400px;margin:0 auto;display:flex;align-items:center;"
    "gap:0;height:48px;overflow-x:auto;scrollbar-width:none}\n"
    ".ma-nav-inner::-webkit-scrollbar{display:none}\n"
    ".ma-logo{color:#fff;font-weight:700;font-size:14px;text-decoration:none;"
    "white-space:nowrap;padding-right:20px;border-right:1px solid rgba(255,255,255,.2);"
    "margin-right:16px;letter-spacing:-.2px}\n"
    ".ma-logo span{display:inline-block;width:8px;height:8px;background:var(--primary);"
    "border-radius:50%;margin-right:6px;vertical-align:middle}\n"
    ".ma-nav-group{font-size:10px;font-weight:700;color:var(--primary);letter-spacing:.8px;"
    "text-transform:uppercase;padding:0 8px 0 4px;white-space:nowrap}\n"
    ".ma-nav-link{color:rgba(255,255,255,.72);text-decoration:none;font-size:13px;"
    "padding:4px 10px;border-radius:6px;white-space:nowrap;transition:all .15s}\n"
    ".ma-nav-link:hover{color:#fff;background:rgba(255,255,255,.1)}\n"
    ".ma-nav-link.current{color:#fff;background:var(--primary);font-weight:600}\n"
    ".ma-nav-sep{width:1px;height:16px;background:rgba(255,255,255,.15);margin:0 8px;flex-shrink:0}"
)


# ── Nav HTML builder ──────────────────────────────────────────────────────

def nav_html(date_str: str, current: str = "") -> str:
    """Top navigation bar with links to all views for this date."""
    links = []
    last_phase = None
    for key, label, phase in ALL_VIEWS:
        if phase != last_phase:
            if last_phase is not None:
                links.append('<div class="ma-nav-sep"></div>')
            links.append(f'<span class="ma-nav-group">{phase}</span>')
            last_phase = phase
        cls = 'ma-nav-link current' if key == current else 'ma-nav-link'
        links.append(f'<a href="../{key}/{date_str}.html" class="{cls}">{label}</a>')

    links_html = "\n    ".join(links)
    return f"""<nav class="ma-nav">
  <div class="ma-nav-inner">
    <a href="../../index.html" class="ma-logo"><span></span>미래에셋생명</a>
    {links_html}
  </div>
</nav>"""


# ── Page header ───────────────────────────────────────────────────────────

def page_header(title: str, subtitle: str, date_str: str) -> str:
    return f"""<div class="ma-header">
  <div>
    <h1>{title}</h1>
    <div class="meta">{subtitle}</div>
  </div>
  <div class="date-badge">{date_str}</div>
</div>"""


# ── Footer ────────────────────────────────────────────────────────────────

def footer_html(source: str = "FRED · yfinance · ECOS") -> str:
    return f"""<div class="ma-footer">
  데이터: {source} | Mirae Asset Life Insurance — Investment View System
</div>"""


# ── Full page wrapper ─────────────────────────────────────────────────────

def html_page(title: str, date_str: str, body: str,
              current_view: str = "",
              extra_css: str = "",
              source: str = "FRED · yfinance · ECOS") -> str:
    """Wrap body HTML in a full HTML page with shared design."""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — {date_str}</title>
<style>
{BASE_CSS}
{extra_css}
</style>
</head>
<body>
{nav_html(date_str, current_view)}
<div class="ma-page">
{body}
{footer_html(source)}
</div>
</body>
</html>"""
