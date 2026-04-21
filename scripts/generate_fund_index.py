"""output/fund/index.html 생성기.

output/fund/ 폴더 안의 파일을 스캔해 다운로드 가능한 목록 페이지를 만든다.
파일명 패턴 '펀드현황_YYYYMMDD.html' 처럼 날짜가 있으면 날짜를 추출해 정렬·표기.

Usage:
    .venv/bin/python scripts/generate_fund_index.py
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUND_DIR = ROOT / "output" / "fund"
INDEX_PATH = FUND_DIR / "index.html"

# '펀드현황_20260417.html' 같은 패턴에서 날짜 추출
DATE_RE = re.compile(r"(\d{8})")


def parse_date(name: str) -> datetime | None:
    m = DATE_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        return None


def human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} B"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def scan_files() -> list[dict]:
    rows = []
    for p in FUND_DIR.iterdir():
        if p.name == "index.html" or p.name.startswith("."):
            continue
        if not p.is_file():
            continue
        dt = parse_date(p.name)
        rows.append({
            "name": p.name,
            "size": p.stat().st_size,
            "size_human": human_size(p.stat().st_size),
            "mtime": datetime.fromtimestamp(p.stat().st_mtime),
            "date": dt,
            "ext": p.suffix.lstrip("."),
        })
    # 날짜 있으면 우선, 없으면 mtime
    rows.sort(key=lambda r: (r["date"] or r["mtime"]), reverse=True)
    return rows


def render_html(rows: list[dict]) -> str:
    body_rows = []
    for r in rows:
        date_label = r["date"].strftime("%Y-%m-%d") if r["date"] else r["mtime"].strftime("%Y-%m-%d")
        ext_badge = r["ext"].upper() if r["ext"] else "FILE"
        body_rows.append(f"""
    <tr>
      <td class="dt">{date_label}</td>
      <td class="nm"><span class="ext-badge">{ext_badge}</span> {r['name']}</td>
      <td class="sz">{r['size_human']}</td>
      <td class="act">
        <a href="{r['name']}" target="_blank" class="btn btn-view">보기</a>
        <a href="{r['name']}" download class="btn btn-dl">다운로드</a>
      </td>
    </tr>""")

    table = "\n".join(body_rows) if body_rows else """
    <tr><td colspan="4" style="text-align:center;color:var(--muted);padding:32px">등록된 파일이 없습니다.</td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fund · Anthillia</title>
<meta name="description" content="미래에셋 AI Investment Agent — 펀드 자료 목록">
<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{
  --bg:#f4f5f9; --card:#fff; --border:#e0e3ed; --text:#2d3148;
  --muted:#7c8298; --primary:#F58220; --primary-light:#fff3e6; --navy:#043B72;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family:'Spoqa Han Sans Neo',-apple-system,sans-serif;
  background:var(--bg); color:var(--text); line-height:1.6;
  padding:48px 24px; max-width:1100px; margin:0 auto;
}}
.nav {{
  display:flex; gap:8px; align-items:center; font-size:13px; color:var(--muted);
  margin-bottom:20px;
}}
.nav a {{ color:var(--muted); text-decoration:none; }}
.nav a:hover {{ color:var(--primary); }}
.nav .sep {{ color:var(--border); }}
.header {{
  text-align:center; margin-bottom:36px; padding-bottom:24px;
  border-bottom:2px solid var(--border);
}}
.header h1 {{ font-size:30px; font-weight:700; color:#1a1d2e; margin-bottom:6px; }}
.header .tagline {{ font-size:15px; color:var(--muted); }}
.card {{
  background:var(--card); border:1px solid var(--border); border-radius:16px;
  padding:0; box-shadow:0 2px 8px rgba(0,0,0,0.04); overflow:hidden;
}}
.card-head {{
  padding:20px 28px; border-bottom:1px solid var(--border);
  display:flex; align-items:center; justify-content:space-between;
  background:linear-gradient(180deg,#fff,#fafbfe);
}}
.card-title {{ font-size:17px; font-weight:700; color:#1a1d2e; display:flex; align-items:center; gap:10px; }}
.card-title .icon {{ font-size:22px; }}
.count {{
  font-size:12px; color:var(--muted); background:#f0f1f6;
  padding:4px 10px; border-radius:12px; font-weight:600;
}}
table {{ width:100%; border-collapse:collapse; }}
th, td {{
  padding:14px 20px; border-bottom:1px solid var(--border);
  font-size:14px; text-align:left; vertical-align:middle;
}}
th {{
  background:#fafbfe; font-weight:600; color:var(--muted); font-size:12px;
  text-transform:uppercase; letter-spacing:0.5px;
}}
tr:last-child td {{ border-bottom:none; }}
tr:hover td {{ background:#fafbfe; }}
.dt {{ color:var(--navy); font-weight:600; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.nm {{ color:#1a1d2e; word-break:break-all; }}
.ext-badge {{
  display:inline-block; font-size:10px; font-weight:700; padding:2px 6px;
  background:var(--primary-light); color:var(--primary); border-radius:4px;
  margin-right:6px; letter-spacing:0.3px;
}}
.sz {{ color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }}
.act {{ white-space:nowrap; text-align:right; }}
.btn {{
  display:inline-block; padding:7px 14px; font-size:13px; font-weight:600;
  text-decoration:none; border-radius:6px; margin-left:6px;
  transition:all 0.15s;
}}
.btn-view {{
  background:#f0f1f6; color:var(--navy);
  border:1px solid var(--border);
}}
.btn-view:hover {{ background:#e8eaf3; }}
.btn-dl {{
  background:var(--primary); color:#fff;
}}
.btn-dl:hover {{ background:#d96e18; }}
.footer {{
  text-align:center; font-size:12px; color:var(--muted);
  padding-top:24px; margin-top:32px;
}}
@media (max-width:720px) {{
  body {{ padding:24px 12px; }}
  th, td {{ padding:10px 12px; font-size:12px; }}
  .btn {{ padding:6px 10px; font-size:12px; margin-left:3px; }}
  .sz {{ display:none; }}  /* 모바일: 크기 컬럼 숨김 */
}}
</style>
</head>
<body>

<div class="nav">
  <a href="../index.html">← Anthillia</a>
  <span class="sep">/</span>
  <span>Fund</span>
</div>

<div class="header">
  <h1>Fund</h1>
  <p class="tagline">펀드 자료 · 다운로드</p>
</div>

<div class="card">
  <div class="card-head">
    <div class="card-title"><span class="icon">💼</span> 파일 목록</div>
    <span class="count">{len(rows)}개</span>
  </div>
  <table>
    <thead>
      <tr>
        <th style="width:14%">날짜</th>
        <th>파일명</th>
        <th style="width:10%">크기</th>
        <th style="width:22%;text-align:right">액션</th>
      </tr>
    </thead>
    <tbody>{table}
    </tbody>
  </table>
</div>

<div class="footer">
  Powered by <a href="https://github.com/traderparamita/market-summary" target="_blank" style="color:var(--primary);text-decoration:none">market_summary</a>
  · 생성: {datetime.now().strftime("%Y-%m-%d %H:%M KST")}
</div>

</body>
</html>
"""


def main() -> None:
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    rows = scan_files()
    html = render_html(rows)
    INDEX_PATH.write_text(html, encoding="utf-8")
    print(f"✓ {INDEX_PATH} 생성 — {len(rows)}개 파일")
    for r in rows:
        print(f"  {r['date'].strftime('%Y-%m-%d') if r['date'] else '—':<12} {r['name']:<40s} {r['size_human']}")


if __name__ == "__main__":
    main()
