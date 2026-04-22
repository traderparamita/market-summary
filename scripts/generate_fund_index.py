"""output/fund/index.html 생성기 — S3 Pre-signed URL 기반.

S3 prefix 를 스캔해 다운로드 가능한 목록 페이지를 만든다.
각 파일에 7일 만료 pre-signed URL 을 발급하여 HTML 에 박는다.
버킷은 비공개 상태로 유지.

Usage:
    .venv/bin/python scripts/generate_fund_index.py

권장: 주 1회 이상 재생성 (URL 7일 만료).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

FUND_DIR = ROOT / "output" / "fund"
INDEX_PATH = FUND_DIR / "index.html"

S3_BUCKET = "mai-life-fund-documents-533370893966-ap-northeast-2-an"
S3_PREFIX = "malife_var_dashboard/fund_reports/github/"
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


def scan_s3() -> list[dict]:
    s3 = boto3.client("s3", region_name=S3_REGION)
    expires = URL_EXPIRES_DAYS * 24 * 3600

    rows = []
    resp = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX)
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        # 빈 폴더 placeholder / 0-byte 건너뜀
        if key.endswith("/") or obj["Size"] == 0:
            continue
        filename = key.rsplit("/", 1)[-1]
        dt = parse_date(filename)

        # Pre-signed URL: 뷰어용 + 다운로드 강제용 두 버전
        view_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=expires,
        )
        dl_url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": S3_BUCKET,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires,
        )
        rows.append({
            "name": filename,
            "key": key,
            "size": obj["Size"],
            "size_human": human_size(obj["Size"]),
            "mtime": obj["LastModified"].replace(tzinfo=None),
            "date": dt,
            "ext": filename.rsplit(".", 1)[-1] if "." in filename else "",
            "view_url": view_url,
            "dl_url": dl_url,
        })
    rows.sort(key=lambda r: (r["date"] or r["mtime"]), reverse=True)
    return rows


def render_html(rows: list[dict]) -> str:
    generated = datetime.now()
    expires_at = generated + timedelta(days=URL_EXPIRES_DAYS)

    body_rows = []
    for r in rows:
        date_label = (r["date"] or r["mtime"]).strftime("%Y-%m-%d")
        ext_badge = r["ext"].upper() or "FILE"
        body_rows.append(f"""
    <tr>
      <td class="dt">{date_label}</td>
      <td class="nm"><span class="ext-badge">{ext_badge}</span> {r['name']}</td>
      <td class="sz">{r['size_human']}</td>
      <td class="act">
        <a href="{r['view_url']}" target="_blank" rel="noopener" class="btn btn-view">보기</a>
        <a href="{r['dl_url']}" class="btn btn-dl">다운로드</a>
      </td>
    </tr>""")

    table = "\n".join(body_rows) if body_rows else """
    <tr><td colspan="4" style="text-align:center;color:var(--muted);padding:32px">등록된 파일이 없습니다.</td></tr>"""

    expires_note = (
        f"""<div class="notice">
      <strong>⏱ 링크 만료 안내</strong> — 다운로드 URL 은 보안을 위해
      <strong>{expires_at.strftime("%Y-%m-%d %H:%M")}</strong> 까지 유효합니다
      (발급: {generated.strftime("%Y-%m-%d %H:%M")}, {URL_EXPIRES_DAYS}일).
      만료 후엔 이 페이지를 새로고침해도 갱신되지 않으며,
      <code>scripts/generate_fund_index.py</code> 를 재실행해 새 URL 을 발급해야 합니다.
    </div>"""
    )

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
.notice {{
  background:var(--warn-bg); border:1px solid var(--warn-border);
  color:var(--warn-text); padding:12px 18px; border-radius:10px;
  font-size:13px; line-height:1.6; margin-bottom:20px;
}}
.notice code {{
  background:rgba(0,0,0,0.06); padding:1px 6px; border-radius:4px;
  font-family:'JetBrains Mono',monospace; font-size:12px;
}}
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
.count {{ font-size:12px; color:var(--muted); background:#f0f1f6; padding:4px 10px; border-radius:12px; font-weight:600; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ padding:14px 20px; border-bottom:1px solid var(--border); font-size:14px; text-align:left; vertical-align:middle; }}
th {{ background:#fafbfe; font-weight:600; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:0.5px; }}
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
  text-decoration:none; border-radius:6px; margin-left:6px; transition:all 0.15s;
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
  .btn {{ padding:6px 10px; font-size:12px; margin-left:3px; }}
  .sz {{ display:none; }}
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

{expires_note}

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
  Powered by <a href="https://github.com/traderparamita/market-summary" target="_blank">market_summary</a>
  · S3: s3://{S3_BUCKET}/{S3_PREFIX}
  · 생성: {generated.strftime("%Y-%m-%d %H:%M KST")}
</div>

</body>
</html>
"""


def main() -> None:
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    rows = scan_s3()
    html = render_html(rows)
    INDEX_PATH.write_text(html, encoding="utf-8")
    print(f"✓ {INDEX_PATH} 생성 — S3 객체 {len(rows)}개 (pre-signed URL {URL_EXPIRES_DAYS}일 만료)")
    for r in rows:
        dt = r["date"].strftime("%Y-%m-%d") if r["date"] else "—"
        print(f"  {dt:<12} {r['name']:<40s} {r['size_human']}")


if __name__ == "__main__":
    main()
