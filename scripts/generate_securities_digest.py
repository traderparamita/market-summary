"""주간 증권 리서치 다이제스트 생성기.

이번 주 미래에셋증권 상세분석 보고서를 OpenAI GPT-4o로 분석해
3개 핵심 투자 테마를 선정하고, PDF 본문 기반 상세 분석과 출처를 포함한 HTML 리포트를 생성.

흐름:
  1. S3 스캔 → 이번 주 보고서 목록
  2. GPT-4o: 제목 기반 테마 3개 + 관련 보고서 인덱스 선정 (function calling)
  3. GPT-4o Vision: 테마별 PDF 앞 2페이지 이미지 →
     { overview, points: [...], insight } 구조 JSON 반환
  4. HTML 렌더링 → output/securities/

Output:
    output/securities/digest_YYYY-WXX.html
    output/securities/digest_latest.html
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import boto3
from dotenv import load_dotenv
from openai import OpenAI
from pdf2image import convert_from_path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

from generate_securities_index import scan_s3  # noqa: E402

OUTPUT_DIR = ROOT / "output" / "securities"
MODEL = "gpt-4o"
S3_BUCKET = "mai-life-fund-documents-533370893966-ap-northeast-2-an"
S3_REGION = "ap-northeast-2"
MAX_PDFS_PER_THEME = 2
PDF_PAGES = 2

# ── function schemas ──────────────────────────────────────────────────────────

THEME_FUNCTION = {
    "name": "set_weekly_themes",
    "description": "이번 주 핵심 투자 테마 목록 설정",
    "parameters": {
        "type": "object",
        "properties": {
            "themes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "테마명 (15자 이내)"},
                        "report_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "관련 보고서 번호 (0-indexed, 최대 4개)",
                        },
                    },
                    "required": ["name", "report_indices"],
                },
            }
        },
        "required": ["themes"],
    },
}

DETAIL_FUNCTION = {
    "name": "set_theme_detail",
    "description": "테마 상세 분석 내용 설정",
    "parameters": {
        "type": "object",
        "properties": {
            "overview": {
                "type": "string",
                "description": "현재 시장·업종 상황 요약 (2-3문장)",
            },
            "points": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 4,
                "description": "애널리스트가 강조한 핵심 투자 포인트 (각 1-2문장)",
            },
            "insight": {
                "type": "string",
                "description": "투자 판단에 도움이 되는 결론 (1-2문장)",
            },
        },
        "required": ["overview", "points", "insight"],
    },
}

# ── helpers ───────────────────────────────────────────────────────────────────


def get_week_range(ref_date: datetime | None = None) -> tuple[datetime, datetime]:
    today = ref_date or datetime.now()
    days_since_friday = (today.weekday() - 4) % 7 or 7
    friday = today - timedelta(days=days_since_friday)
    monday = friday - timedelta(days=4)
    return (
        monday.replace(hour=0, minute=0, second=0, microsecond=0),
        friday.replace(hour=23, minute=59, second=59, microsecond=0),
    )


def filter_week(rows: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [r for r in rows if r["date"] and start <= r["date"] <= end]


def pdf_to_images_b64(s3_client, s3_key: str, n_pages: int = PDF_PAGES) -> list[str]:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        s3_client.download_fileobj(S3_BUCKET, s3_key, f)
        tmp = f.name
    try:
        images = convert_from_path(tmp, dpi=150, first_page=1, last_page=n_pages)
        result = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            result.append(base64.b64encode(buf.getvalue()).decode())
        return result
    finally:
        Path(tmp).unlink(missing_ok=True)


# ── GPT calls ─────────────────────────────────────────────────────────────────


def select_themes(client: OpenAI, reports: list[dict], week_label: str) -> list[dict]:
    """제목 목록 → 테마 3개 + 관련 보고서 인덱스."""
    lines = [f"이번 주({week_label}) 미래에셋증권 보고서 {len(reports)}건:\n"]
    for i, r in enumerate(reports):
        date_str = r["date"].strftime("%m/%d") if r["date"] else "??"
        lines.append(f"{i}. [{date_str}] {r['title']}")

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "증권 리서치 편집장으로서, 보고서 제목 목록을 보고 "
                    "이번 주 핵심 투자 테마를 최대 3개 선정하고 "
                    "각 테마에 가장 관련성 높은 보고서 번호를 최대 4개 지정하세요."
                ),
            },
            {"role": "user", "content": "\n".join(lines)},
        ],
        tools=[{"type": "function", "function": THEME_FUNCTION}],
        tool_choice={"type": "function", "function": {"name": "set_weekly_themes"}},
    )
    msg = resp.choices[0].message
    if msg.tool_calls:
        return json.loads(msg.tool_calls[0].function.arguments).get("themes", [])
    return []


def analyze_theme_detail(
    client: OpenAI,
    theme_name: str,
    reports_subset: list[dict],
    s3_client,
) -> dict:
    """PDF Vision → { overview, points, insight } 구조 반환."""
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"'{theme_name}' 테마 관련 미래에셋증권 분석 보고서입니다. "
                "각 보고서의 핵심 내용을 종합해 분석해 주세요. "
                "수치와 종목명이 보이면 구체적으로 언급하세요."
            ),
        }
    ]

    loaded = 0
    for r in reports_subset[:MAX_PDFS_PER_THEME]:
        try:
            images_b64 = pdf_to_images_b64(s3_client, r["key"])
            content.append({
                "type": "text",
                "text": f"\n[보고서: {r['title']} / {r['date'].strftime('%m/%d') if r['date'] else ''}]",
            })
            for b64 in images_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
                })
            loaded += 1
        except Exception as e:
            print(f"    WARN: PDF 로드 실패 ({r['title'][:30]}): {e}")

    if loaded == 0:
        return {
            "overview": "보고서 본문을 불러올 수 없었습니다.",
            "points": [],
            "insight": "",
        }

    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=900,
        messages=[
            {
                "role": "system",
                "content": (
                    "자산운용사 리서치 애널리스트로서, 증권사 보고서 이미지를 분석해 "
                    "초보 투자자도 이해할 수 있는 명확하고 실용적인 한국어 분석을 작성하세요."
                ),
            },
            {"role": "user", "content": content},
        ],
        tools=[{"type": "function", "function": DETAIL_FUNCTION}],
        tool_choice={"type": "function", "function": {"name": "set_theme_detail"}},
    )
    msg = resp.choices[0].message
    if msg.tool_calls:
        return json.loads(msg.tool_calls[0].function.arguments)
    return {"overview": "", "points": [], "insight": ""}


# ── HTML rendering ────────────────────────────────────────────────────────────


def _render_detail(detail: dict) -> str:
    """{ overview, points, insight } → HTML 블록."""
    overview = detail.get("overview", "")
    points = detail.get("points", [])
    insight = detail.get("insight", "")

    point_items = "".join(f"<li>{p}</li>" for p in points)
    point_block = f'<ul class="point-list">{point_items}</ul>' if point_items else ""

    points_html = (
        f'<div class="detail-section">'
        f'<div class="detail-label">핵심 포인트</div>{point_block}</div>'
        if point_block else ""
    )
    insight_html = (
        f'<div class="detail-section detail-insight">'
        f'<div class="detail-label">투자 시사점</div>'
        f'<p class="detail-text">{insight}</p></div>'
        if insight else ""
    )
    return f"""
    <div class="detail-section">
      <div class="detail-label">현황</div>
      <p class="detail-text">{overview}</p>
    </div>
    {points_html}
    {insight_html}
"""


def render_html(
    reports: list[dict],
    themes: list[dict],
    week_label: str,
    week_range: tuple[datetime, datetime],
) -> str:
    start, end = week_range
    generated = datetime.now()
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]

    theme_cards = []
    for i, theme in enumerate(themes):
        source_rows = []
        for idx in theme.get("report_indices", []):
            if 0 <= idx < len(reports):
                r = reports[idx]
                date_str = r["date"].strftime("%m/%d") if r["date"] else ""
                source_rows.append(f"""
          <li class="source-item">
            <a href="{r['view_url']}" target="_blank" rel="noopener" class="source-link">{r['title']}</a>
            <span class="source-date">{date_str}</span>
          </li>""")

        detail_html = _render_detail(theme.get("detail", {}))

        theme_cards.append(f"""
  <div class="theme-card">
    <div class="theme-header">
      <span class="theme-badge">Theme {i + 1}</span>
      <h2 class="theme-name">{theme['name']}</h2>
    </div>
    <div class="theme-body">
{detail_html}
    </div>
    <div class="source-section">
      <div class="source-label">출처 보고서</div>
      <ul class="source-list">{"".join(source_rows)}
      </ul>
    </div>
  </div>""")

    body = (
        "\n".join(theme_cards)
        if theme_cards
        else '<p style="text-align:center;color:var(--muted);padding:48px">분석 결과가 없습니다.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Research Digest · {week_label} · Anthillia</title>
<meta name="description" content="미래에셋증권 주간 리서치 다이제스트">
<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{
  --bg: #f0f2f7;
  --card: #ffffff;
  --border: #e2e6f0;
  --text: #2d3148;
  --muted: #7c8298;
  --primary: #F58220;
  --primary-light: #fff3e8;
  --navy: #043B72;
  --green: #1a9e6e;
  --green-light: #edfaf5;
  --section-bg: #f8f9fc;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Spoqa Han Sans Neo', -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.75;
  padding: 48px 24px;
  max-width: 900px;
  margin: 0 auto;
}}

/* nav */
.nav {{
  display: flex; gap: 8px; align-items: center;
  font-size: 13px; color: var(--muted); margin-bottom: 24px;
}}
.nav a {{ color: var(--muted); text-decoration: none; }}
.nav a:hover {{ color: var(--primary); }}
.nav .sep {{ color: var(--border); }}

/* header */
.header {{
  margin-bottom: 36px;
  padding-bottom: 28px;
  border-bottom: 2px solid var(--border);
}}
.header-badge {{
  display: inline-block;
  background: var(--primary); color: #fff;
  font-size: 10px; font-weight: 700;
  padding: 3px 10px; border-radius: 20px;
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 12px;
}}
.header h1 {{ font-size: 28px; font-weight: 800; color: #1a1d2e; margin-bottom: 8px; }}
.header .meta {{ font-size: 14px; color: var(--muted); }}

/* theme card */
.theme-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 20px;
  margin-bottom: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.05);
  overflow: hidden;
  transition: box-shadow 0.2s;
}}
.theme-card:hover {{ box-shadow: 0 6px 24px rgba(0,0,0,0.09); }}

.theme-header {{
  display: flex; align-items: center; gap: 14px;
  padding: 24px 28px 20px;
  border-bottom: 1px solid var(--border);
}}
.theme-badge {{
  flex-shrink: 0;
  font-size: 10px; font-weight: 800;
  color: var(--primary);
  background: var(--primary-light);
  padding: 4px 10px; border-radius: 20px;
  text-transform: uppercase; letter-spacing: 0.06em;
}}
.theme-name {{ font-size: 20px; font-weight: 700; color: #1a1d2e; }}

/* detail body */
.theme-body {{ padding: 0 28px; }}

.detail-section {{
  padding: 20px 0;
  border-bottom: 1px solid var(--border);
}}
.detail-section:last-child {{ border-bottom: none; }}

.detail-label {{
  display: inline-block;
  font-size: 11px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--navy);
  background: #eef1f8;
  padding: 3px 10px; border-radius: 20px;
  margin-bottom: 10px;
}}
.detail-insight .detail-label {{
  color: var(--green);
  background: var(--green-light);
}}

.detail-text {{
  font-size: 15px;
  color: var(--text);
  line-height: 1.85;
}}

.point-list {{
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
}}
.point-list li {{
  font-size: 15px;
  color: var(--text);
  line-height: 1.75;
  padding-left: 20px;
  position: relative;
}}
.point-list li::before {{
  content: '';
  position: absolute;
  left: 0; top: 10px;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--primary);
}}

/* source */
.source-section {{
  padding: 18px 28px 22px;
  background: var(--section-bg);
  border-top: 1px solid var(--border);
}}
.source-label {{
  font-size: 11px; font-weight: 700;
  color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.07em;
  margin-bottom: 10px;
}}
.source-list {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
.source-item {{
  display: flex; align-items: center;
  justify-content: space-between; gap: 12px;
}}
.source-link {{
  font-size: 13px; color: var(--navy); text-decoration: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}}
.source-link:hover {{ color: var(--primary); text-decoration: underline; }}
.source-date {{
  flex-shrink: 0;
  font-size: 12px; color: var(--muted);
  background: #ebebf0; padding: 2px 8px; border-radius: 10px;
}}

/* footer */
.footer {{
  text-align: center; font-size: 12px;
  color: var(--muted); padding-top: 28px; margin-top: 8px;
}}
.footer a {{ color: var(--primary); text-decoration: none; }}

@media (max-width: 720px) {{
  body {{ padding: 24px 12px; }}
  .theme-header {{ padding: 18px 20px 16px; }}
  .theme-name {{ font-size: 17px; }}
  .theme-body {{ padding: 0 20px; }}
  .source-section {{ padding: 16px 20px 20px; }}
  .detail-text, .point-list li {{ font-size: 14px; }}
}}
</style>
</head>
<body>

<div class="nav">
  <a href="../index.html">&larr; Anthillia</a>
  <span class="sep">/</span>
  <a href="index.html">Securities Research</a>
  <span class="sep">/</span>
  <span>Research Digest</span>
</div>

<div class="header">
  <div class="header-badge">Research Digest</div>
  <h1>{week_label}</h1>
  <p class="meta">
    미래에셋증권 상세분석 보고서 <strong>{len(reports)}건</strong> 기반 &middot;
    {start.strftime('%Y/%m/%d')}({weekdays[start.weekday()]})
    ~ {end.strftime('%m/%d')}({weekdays[end.weekday()]})
  </p>
</div>

{body}

<div class="footer">
  AI 분석: OpenAI {MODEL} &middot; 출처: 미래에셋증권 상세분석 &middot;
  생성: {generated.strftime('%Y-%m-%d %H:%M KST')}
  &middot; <a href="index.html">전체 보고서 목록</a>
</div>

</body>
</html>
"""


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="주간 증권 리서치 다이제스트 생성")
    parser.add_argument("--week-of", help="기준 주의 월요일 날짜 (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="GPT 호출 없이 HTML 골격만 생성")
    args = parser.parse_args()

    if args.week_of:
        ref = datetime.strptime(args.week_of, "%Y-%m-%d")
        start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        end = (ref + timedelta(days=4)).replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        start, end = get_week_range()

    year, week_num, _ = start.isocalendar()
    week_label = f"{year}년 {week_num}주차 ({start.strftime('%m/%d')}~{end.strftime('%m/%d')})"
    week_id = f"{year}-W{week_num:02d}"

    print("=== 주간 리서치 다이제스트 생성 ===")
    print(f"기간: {week_label}")

    print("\n[1/4] S3 스캔 중...")
    all_rows = scan_s3()
    reports = filter_week(all_rows, start, end)
    print(f"  → {len(reports)}건 (이번 주) / {len(all_rows)}건 (전체)")

    if not reports:
        print("이번 주 보고서 없음. 종료.")
        return

    if args.dry_run:
        themes = [{
            "name": "테스트 테마",
            "report_indices": list(range(min(2, len(reports)))),
            "detail": {
                "overview": "[DRY-RUN] 실제 실행 시 GPT-4o가 PDF 본문을 분석합니다.",
                "points": ["포인트 1", "포인트 2"],
                "insight": "투자 시사점이 여기에 표시됩니다.",
            },
        }]
        print("\n[DRY-RUN] GPT 호출 생략")
    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        s3_client = boto3.client("s3", region_name=S3_REGION)

        print(f"\n[2/4] 테마 선정 중... ({len(reports)}건 제목 분석)")
        themes = select_themes(client, reports, week_label)
        print(f"  → {len(themes)}개 테마:")
        for t in themes:
            print(f"     • {t['name']} (관련 {len(t.get('report_indices', []))}건)")

        print(f"\n[3/4] PDF Vision 분석 중... (테마당 최대 {MAX_PDFS_PER_THEME}건)")
        for i, theme in enumerate(themes):
            print(f"  [{i+1}/{len(themes)}] {theme['name']}")
            indices = theme.get("report_indices", [])
            subset = [reports[idx] for idx in indices if 0 <= idx < len(reports)]
            theme["detail"] = analyze_theme_detail(client, theme["name"], subset, s3_client)
            pts = len(theme["detail"].get("points", []))
            print(f"    → 완료 (포인트 {pts}개)")

    print("\n[4/4] HTML 생성 중...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    html = render_html(reports, themes, week_label, (start, end))
    digest_path = OUTPUT_DIR / f"digest_{week_id}.html"
    latest_path = OUTPUT_DIR / "digest_latest.html"

    digest_path.write_text(html, encoding="utf-8")
    shutil.copy2(digest_path, latest_path)

    print(f"  → {digest_path}")
    print(f"  → {latest_path} (최신본)")


if __name__ == "__main__":
    main()
