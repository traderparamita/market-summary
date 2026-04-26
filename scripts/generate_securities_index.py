"""output/securities/index.html 생성기 — S3 Pre-signed URL 기반.

미래에셋증권 상세분석 보고서(anthillia/miraeasset-securities/) 를 스캔해
날짜별 그룹핑된 목록 페이지를 생성한다.

Usage:
    .venv/bin/python scripts/generate_securities_index.py

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

OUTPUT_DIR = ROOT / "output" / "securities"
INDEX_PATH = OUTPUT_DIR / "index.html"

S3_BUCKET = "mai-life-fund-documents-533370893966-ap-northeast-2-an"
S3_PREFIX = "anthillia/miraeasset-securities"
S3_REGION = "ap-northeast-2"
URL_EXPIRES_DAYS = 7

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


def clean_title(filename: str) -> str:
    """파일명에서 날짜 prefix와 attachmentId suffix, 확장자를 제거해 제목 추출."""
    name = filename
    if name.endswith(".pdf"):
        name = name[:-4]
    # 앞쪽 YYYYMMDD_ 제거
    name = re.sub(r"^\d{8}_", "", name)
    # 끝쪽 _숫자(attachmentId) 제거
    name = re.sub(r"_\d{5,}$", "", name)
    return name


def scan_s3() -> list[dict]:
    s3 = boto3.client("s3", region_name=S3_REGION)
    expires = URL_EXPIRES_DAYS * 24 * 3600

    rows = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/") or obj["Size"] == 0:
                continue
            filename = key.rsplit("/", 1)[-1]
            dt = parse_date(filename)

            view_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": key},
                ExpiresIn=expires,
            )
            filename_encoded = quote(filename.encode("utf-8"))
            fallback_match = DATE_RE.search(filename)
            fallback_name = (
                f"report_{fallback_match.group(1)}.pdf"
                if fallback_match
                else "report.pdf"
            )
            dl_url = s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": S3_BUCKET,
                    "Key": key,
                    "ResponseContentDisposition": (
                        f'attachment; filename="{fallback_name}"; '
                        f"filename*=UTF-8''{filename_encoded}"
                    ),
                },
                ExpiresIn=expires,
            )
            rows.append({
                "name": filename,
                "title": clean_title(filename),
                "key": key,
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

    # 날짜별 그룹핑
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        date_label = (r["date"] or r["mtime"]).strftime("%Y-%m-%d")
        by_date[date_label].append(r)

    date_sections = []
    for date_label in sorted(by_date.keys(), reverse=True):
        items = by_date[date_label]
        weekday = ["월", "화", "수", "목", "금", "토", "일"]
        dt = datetime.strptime(date_label, "%Y-%m-%d")
        day_name = weekday[dt.weekday()]

        item_rows = []
        for r in items:
            item_rows.append(f"""
      <tr>
        <td class="nm">{r['title']}</td>
        <td class="sz">{r['size_human']}</td>
        <td class="act">
          <a href="{r['view_url']}" target="_blank" rel="noopener" class="btn btn-view">보기</a>
          <a href="{r['dl_url']}" class="btn btn-dl">PDF</a>
        </td>
      </tr>""")

        date_sections.append(f"""
  <div class="date-group">
    <div class="date-header">
      <span class="date-label">{date_label} ({day_name})</span>
      <span class="date-count">{len(items)}건</span>
    </div>
    <table>
      <tbody>{"".join(item_rows)}
      </tbody>
    </table>
  </div>""")

    body = "\n".join(date_sections) if date_sections else """
  <div style="text-align:center;color:var(--muted);padding:48px">등록된 보고서가 없습니다.</div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Securities Research · Anthillia</title>
<meta name="description" content="미래에셋증권 상세분석 보고서">
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
.date-group {{
  background:var(--card); border:1px solid var(--border); border-radius:16px;
  margin-bottom:16px; box-shadow:0 2px 8px rgba(0,0,0,0.04); overflow:hidden;
}}
.date-header {{
  padding:16px 24px; border-bottom:1px solid var(--border);
  display:flex; align-items:center; justify-content:space-between;
  background:linear-gradient(180deg,#fff,#fafbfe);
}}
.date-label {{ font-size:15px; font-weight:700; color:var(--navy); }}
.date-count {{ font-size:12px; color:var(--muted); background:#f0f1f6; padding:3px 10px; border-radius:12px; font-weight:600; }}
table {{ width:100%; border-collapse:collapse; }}
td {{ padding:12px 24px; border-bottom:1px solid var(--border); font-size:14px; text-align:left; vertical-align:middle; }}
tr:last-child td {{ border-bottom:none; }}
tr:hover td {{ background:#fafbfe; }}
.nm {{ color:#1a1d2e; }}
.sz {{ color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; width:80px; }}
.act {{ white-space:nowrap; text-align:right; width:160px; }}
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
  td {{ padding:10px 12px; font-size:12px; }}
  .btn {{ padding:5px 8px; font-size:11px; margin-left:3px; }}
  .sz {{ display:none; }}
}}
</style>
</head>
<body>

<div class="nav">
  <a href="../index.html">&larr; Anthillia</a>
  <span class="sep">/</span>
  <span>Securities Research</span>
</div>

<div class="header">
  <h1>Securities Research</h1>
  <p class="tagline">미래에셋증권 상세분석 보고서</p>
  <p class="stats">{len(rows)}건 &middot; {len(by_date)}일</p>
</div>

<div class="notice">
  <strong>&CircleTimes;</strong> 다운로드 링크 유효기간 <strong>{URL_EXPIRES_DAYS}일</strong>
  &middot; 만료 시 페이지 재생성 필요 (~{expires_at.strftime("%m-%d")})
</div>

{body}

<div class="footer">
  Powered by <a href="https://github.com/traderparamita/market-summary" target="_blank">market_summary</a>
  &middot; 생성: {generated.strftime("%Y-%m-%d %H:%M KST")}
</div>

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
