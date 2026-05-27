"""output/research/index.html — 일간 테마 리서치 카드 인덱스 생성.

daily/YYYY-MM/YYYY-MM-DD.html 중 "Daily Theme Research" 마커가 있는 파일만
스캔하여 날짜순 카드 목록을 생성한다.

collect_weekly.py Step 6 및 generate_research.py 완료 후 호출.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_RESEARCH = ROOT / "output" / "research"
OUTPUT_INDEX = OUTPUT_RESEARCH / "index.html"
KST = ZoneInfo("Asia/Seoul")


def _parse_entries(n: int = 40) -> list[dict]:
    candidates = sorted(
        [p for p in glob.glob(str(OUTPUT_RESEARCH / "daily" / "????-??" / "????-??-??.html"))
         if "_story" not in p],
        reverse=True,
    )
    entries = []
    for path in candidates:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except Exception:
            continue
        if "Daily Theme Research" not in content:
            continue
        date_str = Path(path).stem
        themes = re.findall(r'<h2 class="theme-name">([^<]+)</h2>', content)
        chips = re.findall(r'class="chip chip-(?:pos|persist|tavily)[^"]*">([^<]+)</span>', content)
        # 칩 중복 제거, 최대 4개
        seen: set[str] = set()
        deduped = []
        for c in chips:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
            if len(deduped) >= 4:
                break
        entries.append({
            "date": date_str,
            "themes": themes,
            "chips": deduped,
            "href": f"daily/{date_str[:7]}/{date_str}.html",
        })
        if len(entries) >= n:
            break
    return entries


def _render(entries: list[dict]) -> str:
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    # JSON for JavaScript today-detection
    js_entries = json.dumps(
        [{"date": e["date"], "themes": e["themes"], "chips": e["chips"], "href": e["href"]} for e in entries],
        ensure_ascii=False,
    )

    # Card grid HTML (list view)
    cards = ""
    for e in entries:
        theme_html = " · ".join(e["themes"]) if e["themes"] else e["date"]
        chip_html = "".join(f'<span class="chip">{c}</span>' for c in e["chips"])
        cards += f"""
  <a class="card" href="{e['href']}">
    <div class="card-date">{e['date']}</div>
    <div class="card-title">{theme_html}</div>
    <div class="card-chips">{chip_html}</div>
  </a>"""

    empty = '<p class="empty">아직 리서치가 없습니다.</p>' if not cards else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Research — 일간 테마 리서치</title>
<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{
  --bg: #f4f5f9; --card: #fff; --border: #e0e3ed;
  --text: #2d3148; --muted: #7c8298;
  --orange: #F58220; --navy: #043B72;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Spoqa Han Sans Neo', -apple-system, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6;
  padding: 48px 24px; max-width: 1100px; margin: 0 auto;
}}
.nav {{ font-size: 13px; color: var(--muted); margin-bottom: 32px; }}
.nav a {{ color: var(--orange); text-decoration: none; }}
.nav a:hover {{ text-decoration: underline; }}
.header {{
  margin-bottom: 32px; display: flex;
  align-items: flex-start; justify-content: space-between;
  flex-wrap: wrap; gap: 16px;
}}
.header-left h1 {{ font-size: 28px; font-weight: 700; color: var(--navy); }}
.header-left .sub {{ font-size: 14px; color: var(--muted); margin-top: 4px; }}
.view-toggle {{ display: flex; gap: 8px; flex-shrink: 0; }}
.toggle-btn {{
  padding: 8px 18px; border-radius: 8px;
  border: 2px solid var(--orange);
  font-family: inherit; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.18s;
  background: #fff; color: var(--orange);
}}
.toggle-btn.active {{ background: var(--orange); color: #fff; }}
.toggle-btn:hover:not(.active) {{ background: #fff7f0; }}
.view {{ display: none; }}
.view.active {{ display: block; }}
/* featured card */
.featured-label {{
  font-size: 11px; font-weight: 700; letter-spacing: 1.2px;
  text-transform: uppercase; color: var(--orange); margin-bottom: 14px;
}}
.featured-card {{
  background: var(--card); border: 2px solid var(--orange);
  border-radius: 16px; padding: 32px 36px;
  text-decoration: none; color: var(--text);
  display: block; position: relative; overflow: hidden;
  transition: all 0.2s;
  box-shadow: 0 4px 24px rgba(245,130,32,0.10);
}}
.featured-card::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 5px;
  background: linear-gradient(90deg, var(--orange), #ff9d4d);
}}
.featured-card:hover {{
  transform: translateY(-3px);
  box-shadow: 0 10px 36px rgba(245,130,32,0.18);
}}
.featured-date {{ font-size: 13px; color: var(--muted); margin-bottom: 10px; }}
.featured-title {{
  font-size: 22px; font-weight: 700; color: var(--navy);
  margin-bottom: 16px; line-height: 1.4;
}}
.featured-chips {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 28px; }}
.featured-cta {{
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--orange); color: #fff;
  padding: 10px 22px; border-radius: 8px;
  font-size: 14px; font-weight: 700;
}}
.no-report {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 40px; color: var(--muted);
  text-align: center; font-size: 15px;
}}
/* list view */
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}}
.card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 22px;
  text-decoration: none; color: var(--text);
  transition: all 0.2s; display: block;
  position: relative; overflow: hidden;
}}
.card::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--orange), #ff9d4d);
}}
.card:hover {{
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  border-color: var(--orange);
}}
.card-date {{ font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
.card-title {{ font-size: 15px; font-weight: 700; margin-bottom: 10px; line-height: 1.4; }}
.card-chips {{ display: flex; gap: 5px; flex-wrap: wrap; }}
.chip {{
  background: #fff3e6; color: var(--orange);
  border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
.empty {{ color: var(--muted); font-size: 14px; margin-top: 16px; }}
.footer {{
  text-align: center; font-size: 12px; color: var(--muted);
  margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--border);
}}
@media (max-width: 640px) {{
  .grid {{ grid-template-columns: 1fr; }}
  .header {{ flex-direction: column; }}
  .featured-card {{ padding: 24px 20px; }}
  .featured-title {{ font-size: 18px; }}
}}
</style>
</head>
<body>
<div class="nav">
  <a href="../index.html">&larr; Anthillia</a> / Market Research
</div>
<div class="header">
  <div class="header-left">
    <h1>Market Research</h1>
    <p class="sub">Naver 테마 수익률 × Tavily 글로벌 트리거 × 상담사 토킹포인트</p>
  </div>
  <div class="view-toggle">
    <button class="toggle-btn active" id="btn-today" onclick="showView('today')">오늘의 리포트</button>
    <button class="toggle-btn" id="btn-list" onclick="showView('list')">보고서 목록</button>
  </div>
</div>

<div id="view-today" class="view active">
  <div id="today-content"></div>
</div>

<div id="view-list" class="view">
  <div class="grid">{cards}
  </div>
  {empty}
</div>

<div class="footer">갱신: {now_str}</div>

<script>
const ENTRIES = {js_entries};

function showView(name) {{
  document.getElementById('view-today').classList.toggle('active', name === 'today');
  document.getElementById('view-list').classList.toggle('active', name === 'list');
  document.getElementById('btn-today').classList.toggle('active', name === 'today');
  document.getElementById('btn-list').classList.toggle('active', name === 'list');
}}

(function () {{
  const today = new Date().toLocaleDateString('sv-SE', {{timeZone: 'Asia/Seoul'}});
  const entry = ENTRIES.find(function(e) {{ return e.date === today; }}) || ENTRIES[0];
  const container = document.getElementById('today-content');

  if (!entry) {{
    container.innerHTML = '<div class="no-report">아직 오늘의 리포트가 없습니다.</div>';
    return;
  }}

  const isToday = entry.date === today;
  const label = isToday ? '오늘의 리포트' : '최신 리포트 &nbsp;·&nbsp; ' + entry.date;
  const themeTitle = entry.themes.length ? entry.themes.join(' · ') : entry.date;
  const chipsHtml = entry.chips.map(function(c) {{
    return '<span class="chip">' + c + '</span>';
  }}).join('');

  container.innerHTML =
    '<div class="featured-label">' + label + '</div>' +
    '<a class="featured-card" href="' + entry.href + '">' +
      '<div class="featured-date">' + entry.date + '</div>' +
      '<div class="featured-title">' + themeTitle + '</div>' +
      '<div class="featured-chips">' + chipsHtml + '</div>' +
      '<div class="featured-cta">리포트 전체 보기 &rarr;</div>' +
    '</a>';
}})();
</script>
</body>
</html>"""


def main() -> None:
    entries = _parse_entries()
    html = _render(entries)
    OUTPUT_INDEX.write_text(html, encoding="utf-8")
    print(f"  [OK] research/index.html updated ({len(entries)} entries)")


if __name__ == "__main__":
    main()
