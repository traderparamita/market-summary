"""output/prism/index.html 생성기 — S3 Pre-signed URL 기반.

MVP PRISM 보고서(prism/) 를 스캔해 카테고리별 목록 페이지를 생성한다.

Usage:
    .venv/bin/python scripts/generate_prism_index.py

권장: 주 1회 이상 재생성 (URL 7일 만료).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OUTPUT_DIR = ROOT / "output" / "prism"
INDEX_PATH = OUTPUT_DIR / "index.html"

S3_BUCKET = "mai-life-fund-documents-533370893966-ap-northeast-2-an"
S3_PREFIX = "prism"
S3_REGION = "ap-northeast-2"
URL_EXPIRES_DAYS = 7

DATE_RE = re.compile(r"(\d{8})")
YEARMONTH_RE = re.compile(r"/(\d{4})/(\d{2})/")

CATEGORY_LABELS = {
    "주간시황": "주간시황",
    "월간전망": "월간전망",
    "MVP_LETTER": "MVP Letter",
    "주요변액펀드성과리뷰": "변액펀드 성과리뷰",
    "INSIGHT": "Insight",
}
CATEGORY_ORDER = ["주간시황", "월간전망", "MVP_LETTER", "주요변액펀드성과리뷰", "INSIGHT"]


def parse_date_from_key(key: str, filename: str) -> datetime | None:
    m = DATE_RE.search(filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d")
        except ValueError:
            pass
    m2 = YEARMONTH_RE.search(key)
    if m2:
        try:
            return datetime.strptime(f"{m2.group(1)}-{m2.group(2)}-01", "%Y-%m-%d")
        except ValueError:
            pass
    return None


def human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} B"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def clean_title(filename: str) -> str:
    name = filename
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    name = name.replace("_", " ")
    return name


def extract_category(key: str) -> str:
    # prism/<category>/...
    parts = key.split("/")
    if len(parts) >= 2:
        return parts[1]
    return "기타"


def scan_s3() -> list[dict]:
    s3 = boto3.client("s3", region_name=S3_REGION)
    expires = URL_EXPIRES_DAYS * 24 * 3600

    rows = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + "/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/") or obj["Size"] == 0:
                continue
            filename = key.rsplit("/", 1)[-1]
            dt = parse_date_from_key(key, filename)
            category = extract_category(key)

            view_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": key},
                ExpiresIn=expires,
            )
            filename_encoded = quote(filename.encode("utf-8"))
            dl_url = s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": S3_BUCKET,
                    "Key": key,
                    "ResponseContentDisposition": (
                        f'attachment; filename="report.pdf"; '
                        f"filename*=UTF-8''{filename_encoded}"
                    ),
                },
                ExpiresIn=expires,
            )
            rows.append({
                "name": filename,
                "title": clean_title(filename),
                "key": key,
                "category": category,
                "size": obj["Size"],
                "size_human": human_size(obj["Size"]),
                "mtime": obj["LastModified"].replace(tzinfo=None),
                "date": dt,
                "view_url": view_url,
                "dl_url": dl_url,
            })
    rows.sort(key=lambda r: (r["date"] or r["mtime"]), reverse=True)
    return rows


def render_html(rows: list[dict]) -> str:
    generated = datetime.now()
    expires_at = generated + timedelta(days=URL_EXPIRES_DAYS)

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    tab_buttons = []
    tab_contents = []
    for i, cat_key in enumerate(CATEGORY_ORDER):
        if cat_key not in by_cat:
            continue
        items = by_cat[cat_key]
        label = CATEGORY_LABELS.get(cat_key, cat_key)
        active = " active" if i == 0 else ""

        tab_buttons.append(
            f'<button class="tab-btn{active}" data-tab="{cat_key}">'
            f'{label} <span class="tab-count">{len(items)}</span></button>'
        )

        item_rows = []
        for r in items:
            date_label = (r["date"] or r["mtime"]).strftime("%Y-%m-%d")
            item_rows.append(f"""
        <tr>
          <td class="dt">{date_label}</td>
          <td class="nm">{r['title']}</td>
          <td class="sz">{r['size_human']}</td>
          <td class="act">
            <a href="{r['view_url']}" target="_blank" rel="noopener" class="btn btn-view">보기</a>
            <a href="{r['dl_url']}" class="btn btn-dl">PDF</a>
          </td>
        </tr>""")

        tab_contents.append(f"""
  <div class="tab-content{active}" id="tab-{cat_key}">
    <table>
      <thead>
        <tr>
          <th style="width:12%">날짜</th>
          <th>제목</th>
          <th style="width:8%">크기</th>
          <th style="width:16%;text-align:right">액션</th>
        </tr>
      </thead>
      <tbody>{"".join(item_rows)}
      </tbody>
    </table>
  </div>""")

    # 미분류 카테고리
    for cat_key, items in by_cat.items():
        if cat_key in CATEGORY_ORDER:
            continue
        label = CATEGORY_LABELS.get(cat_key, cat_key)
        tab_buttons.append(
            f'<button class="tab-btn" data-tab="{cat_key}">'
            f'{label} <span class="tab-count">{len(items)}</span></button>'
        )
        item_rows = []
        for r in items:
            date_label = (r["date"] or r["mtime"]).strftime("%Y-%m-%d")
            item_rows.append(f"""
        <tr>
          <td class="dt">{date_label}</td>
          <td class="nm">{r['title']}</td>
          <td class="sz">{r['size_human']}</td>
          <td class="act">
            <a href="{r['view_url']}" target="_blank" rel="noopener" class="btn btn-view">보기</a>
            <a href="{r['dl_url']}" class="btn btn-dl">PDF</a>
          </td>
        </tr>""")
        tab_contents.append(f"""
  <div class="tab-content" id="tab-{cat_key}">
    <table>
      <thead><tr><th style="width:12%">날짜</th><th>제목</th><th style="width:8%">크기</th><th style="width:16%;text-align:right">액션</th></tr></thead>
      <tbody>{"".join(item_rows)}</tbody>
    </table>
  </div>""")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PRISM · Anthillia</title>
<meta name="description" content="MVP PRISM 보고서 아카이브">
<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{
  --bg:#f4f5f9; --card:#fff; --border:#e0e3ed; --text:#2d3148;
  --muted:#7c8298; --primary:#F58220; --primary-light:#fff3e6; --navy:#043B72;
  --warn-bg:#fff7e6; --warn-border:#ffd591; --warn-text:#ad6800;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family:'Spoqa Han Sans Neo',-apple-system,sans-serif;
  background:var(--bg); color:var(--text); line-height:1.6;
  padding:48px 24px; max-width:1100px; margin:0 auto;
}}
.nav {{ display:flex; gap:8px; align-items:center; font-size:13px; color:var(--muted); margin-bottom:20px; }}
.nav a {{ color:var(--muted); text-decoration:none; }}
.nav a:hover {{ color:var(--primary); }}
.nav .sep {{ color:var(--border); }}
.header {{ text-align:center; margin-bottom:24px; padding-bottom:24px; border-bottom:2px solid var(--border); }}
.header h1 {{ font-size:30px; font-weight:700; color:#1a1d2e; margin-bottom:6px; }}
.header .tagline {{ font-size:15px; color:var(--muted); }}
.header .stats {{ font-size:13px; color:var(--muted); margin-top:8px; }}
.notice {{
  background:var(--warn-bg); border:1px solid var(--warn-border);
  color:var(--warn-text); padding:12px 18px; border-radius:10px;
  font-size:13px; line-height:1.6; margin-bottom:20px;
}}
.tabs {{
  display:flex; gap:6px; margin-bottom:20px; flex-wrap:wrap;
}}
.tab-btn {{
  padding:8px 16px; font-size:13px; font-weight:600;
  background:var(--card); border:1px solid var(--border); border-radius:8px;
  cursor:pointer; color:var(--muted); transition:all 0.15s;
  font-family:inherit;
}}
.tab-btn:hover {{ color:var(--navy); border-color:var(--navy); }}
.tab-btn.active {{ background:var(--navy); color:#fff; border-color:var(--navy); }}
.tab-count {{
  display:inline-block; font-size:11px; background:rgba(255,255,255,0.2);
  padding:1px 6px; border-radius:8px; margin-left:4px;
}}
.tab-btn.active .tab-count {{ background:rgba(255,255,255,0.25); }}
.tab-content {{ display:none; }}
.tab-content.active {{ display:block; }}
.tab-content {{
  background:var(--card); border:1px solid var(--border); border-radius:16px;
  box-shadow:0 2px 8px rgba(0,0,0,0.04); overflow:hidden;
}}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ padding:12px 20px; border-bottom:1px solid var(--border); font-size:14px; text-align:left; vertical-align:middle; }}
th {{ background:#fafbfe; font-weight:600; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}
tr:last-child td {{ border-bottom:none; }}
tr:hover td {{ background:#fafbfe; }}
.dt {{ color:var(--navy); font-weight:600; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.nm {{ color:#1a1d2e; }}
.sz {{ color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }}
.act {{ white-space:nowrap; text-align:right; }}
.btn {{
  display:inline-block; padding:6px 12px; font-size:12px; font-weight:600;
  text-decoration:none; border-radius:6px; margin-left:4px; transition:all 0.15s;
}}
.btn-view {{ background:#f0f1f6; color:var(--navy); border:1px solid var(--border); }}
.btn-view:hover {{ background:#e8eaf3; }}
.btn-dl {{ background:var(--primary); color:#fff; }}
.btn-dl:hover {{ background:#d96e18; }}
.footer {{ text-align:center; font-size:12px; color:var(--muted); padding-top:24px; margin-top:32px; }}
.footer a {{ color:var(--primary); text-decoration:none; }}
@media (max-width:720px) {{
  body {{ padding:24px 12px; }}
  th, td {{ padding:10px 12px; font-size:12px; }}
  .btn {{ padding:5px 8px; font-size:11px; margin-left:3px; }}
  .sz {{ display:none; }}
  .tabs {{ gap:4px; }}
  .tab-btn {{ padding:6px 10px; font-size:12px; }}
}}
</style>
</head>
<body>

<div class="nav">
  <a href="../index.html">&larr; Anthillia</a>
  <span class="sep">/</span>
  <span>PRISM</span>
</div>

<div class="header">
  <h1>PRISM</h1>
  <p class="tagline">MVP PRISM 보고서 아카이브</p>
  <p class="stats">{len(rows)}건 &middot; {len(by_cat)}개 카테고리</p>
</div>

<div class="notice">
  <strong>&CircleTimes;</strong> 다운로드 링크 유효기간 <strong>{URL_EXPIRES_DAYS}일</strong>
  &middot; 만료 시 페이지 재생성 필요 (~{expires_at.strftime("%m-%d")})
</div>

<div class="tabs">
  {"".join(tab_buttons)}
</div>

{"".join(tab_contents)}

<div class="footer">
  Powered by <a href="https://github.com/traderparamita/market-summary" target="_blank">market_summary</a>
  &middot; 생성: {generated.strftime("%Y-%m-%d %H:%M KST")}
</div>

<script>
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  }});
}});
</script>

</body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = scan_s3()
    html = render_html(rows)
    INDEX_PATH.write_text(html, encoding="utf-8")
    print(f"  {INDEX_PATH} — {len(rows)}건 (pre-signed URL {URL_EXPIRES_DAYS}일 만료)")


if __name__ == "__main__":
    main()
