#!/usr/bin/env python3
"""OCR briefing → 4-tab consolidated HTML (Story + CS + PM + Macro).

기존 generate_ocr_story.py 는 Story 단일 탭만 생성. 본 스크립트는 동일 OCR 본문에서
CS / PM / Macro 3개 탭을 추가로 생성해 하나의 합본 HTML 로 묶는다.

사용:
  python scripts/generate_ocr_total.py --date 2026-05-12

산출:
  output/summary/{YYYY-MM}/{date}_ocr_total.html
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# Bedrock 인증·모델 (generate_ocr_story.py 와 동일)
os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", os.environ.get("BEDROCK_API_KEY", ""))
BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "jp.anthropic.claude-sonnet-4-5-20250929-v1:0")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")


def _get_bedrock_client():
    from anthropic import AnthropicBedrock
    return AnthropicBedrock(aws_region=BEDROCK_REGION)


# ── 시스템 프롬프트: CS / PM / Macro 각 탭의 출력 포맷 ────────────────────────

CS_SYSTEM = """\
당신은 미래에셋 자산운용 CS 팀의 시장 해설 작성자입니다. PDF OCR 원문(미래에셋증권 모닝 브리핑)을
기반으로 일반 고객 대상 "CS Story" 탭의 HTML 본문을 작성하세요.

작성 원칙:
- 수치 나열보다 맥락·흐름·"왜 그랬는가"를 중심으로 자연스러운 한국어 서술
- 전문 용어는 풀어쓰되 핵심 지표(코스피, 나스닥, WTI, 환율, CPI 등)는 그대로 사용
- 상승은 <span class="hl-up">키워드</span>, 하락은 <span class="hl-down">키워드</span> 강조
- 출력은 순수 HTML 본문 (DOCTYPE/head/body 태그 없이 바로 div 부터)
- ```html 코드블록 감싸지 말 것

필수 구조 (CSS 클래스 정확히 일치):
```
<div class="cs-hero">
  <h2>CS Story — 고객 설명용</h2>
  <div class="cs-subtitle">{YYYY-MM-DD} ({요일}) · 수치 대신 맥락·흐름 중심</div>
  <div class="cs-text">
    <p>{아시아 세션 흐름 — 3~5문장}</p>
    <p>{유럽 세션 흐름 — 2~3문장}</p>
    <p>{미국 세션 흐름 — 3~5문장}</p>
  </div>
</div>

<div class="cs-section">
  <h3>{이모지} {섹션 제목 — 그 날의 핵심 사건 1}</h3>
  <p>{1~3문장 해설}</p>
</div>
... (cs-section 4~6개)

<div class="cs-section">
  <h3>📅 이번 주 관전 포인트</h3>
  <p>{이번 주 핵심 이벤트 1~2문장}</p>
  <p class="cs-footer">CS Story 는 Market Story 를 수치 대신 맥락·흐름 중심으로 재구성한 고객 설명용 버전입니다. 구체적 수치는 Market Story / Data Dashboard 탭을 참고하세요.</p>
</div>
```
"""


PM_SYSTEM = """\
당신은 미래에셋 자산운용 포트폴리오 매니저용 시황 브리프 작성자입니다. PDF OCR 원문에서
지역·자산군별 핵심 수치와 드라이버를 추출해 "PM Story" 탭의 HTML 본문을 작성하세요.

작성 원칙:
- 수치 중심 — 종가·등락률·bp·달러 환산 모두 PDF 본문 그대로 인용
- 한국·매크로·아시아및중국·미국·유럽·채권 6개 섹션을 모두 작성
- 상승 수치는 <span class="pm-up">키워드</span>, 하락 수치는 <span class="pm-dn">키워드</span>
- 종가·수치 자체는 <span class="pm-num">키워드</span>
- 출력은 순수 HTML 본문 (DOCTYPE/head/body 태그 없이)
- ```html 코드블록 감싸지 말 것

필수 구조 (CSS 클래스 정확히 일치):
```
<div class="pm-hero">
  <h2>PM Story — 포트폴리오 매니저 브리프</h2>
  <div class="pm-subtitle">{YYYY-MM-DD} ({요일}) · 지역·자산군별 요지 + 핵심 수치</div>
  <div class="pm-tl">
    <p><strong>Top-line:</strong> {2~3문장 핵심 요약}</p>
    <p><strong>Key drivers:</strong> {3개 드라이버 세미콜론 구분}</p>
    <p><strong>Watch:</strong> {2~3개 관전 포인트}</p>
  </div>
</div>

<div class="pm-grid">
  <div class="pm-section">
    <h3>🇰🇷 한국</h3>
    <ul>
      <li>KOSPI <span class="pm-num">{종가}</span> <span class="pm-dn">{등락}</span> · ...</li>
      ... (4~6개 li)
    </ul>
    <div class="pm-note">{한국 시황 1줄 코멘트}</div>
  </div>

  <div class="pm-section"><h3>🌐 매크로</h3>...</div>
  <div class="pm-section"><h3>🌏 아시아·중국</h3>...</div>
  <div class="pm-section"><h3>🇺🇸 미국</h3>...</div>
  <div class="pm-section"><h3>🇪🇺 유럽</h3>...</div>
  <div class="pm-section"><h3>💵 채권·환율</h3>...</div>
</div>

<div class="pm-footer">PM Story 는 Market Story 를 PM 의사결정 관점에서 재구성한 6 섹션 브리프입니다.</div>
```
"""


# Macro 는 Bedrock 으로 생성하지 않고 기존 {date}_macro.html 을 그대로 붙여서 사용


# ── 합본 HTML 템플릿 ────────────────────────────────────────────────────────

# 4 탭 합본을 위한 추가 CSS (CS / PM / Macro 탭 별)
EXTRA_CSS = """
.tab-bar{display:flex;gap:0;margin-bottom:28px;border-bottom:2px solid var(--border)}
.tab-btn{padding:12px 28px;font-size:14px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s}
.tab-btn:hover{color:var(--text)}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-panel{display:none}
.tab-panel.active{display:block}

/* CS Story */
.cs-hero{background:linear-gradient(135deg,#fff5eb,#fde9d3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:24px}
.cs-hero h2{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}
.cs-hero .cs-subtitle{font-size:12px;color:var(--muted);margin-bottom:16px}
.cs-text{font-size:16px;color:#2d3148;line-height:1.9}
.cs-text p{margin-bottom:14px}.cs-text p:last-child{margin-bottom:0}
.cs-section{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px 28px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
.cs-section h3{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:10px}
.cs-section p{font-size:15px;color:#2d3148;line-height:1.85;margin-bottom:10px}
.cs-section p:last-child{margin-bottom:0}
.cs-footer{font-size:12px;color:var(--muted);border-top:1px solid var(--border);padding-top:12px;margin-top:8px}

/* PM Story */
.pm-hero{background:linear-gradient(135deg,#eef4fb,#dde9f6);border:1px solid var(--border);border-left:4px solid #043B72;border-radius:12px;padding:24px 28px;margin-bottom:20px}
.pm-hero h2{font-size:13px;color:#043B72;letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.pm-hero .pm-subtitle{font-size:12px;color:var(--muted);margin-bottom:14px}
.pm-tl{font-size:15px;color:#1a1d2e;line-height:1.8}
.pm-tl p{margin-bottom:8px}.pm-tl p:last-child{margin-bottom:0}
.pm-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-bottom:16px}
@media (max-width:800px){.pm-grid{grid-template-columns:1fr}}
.pm-section{background:var(--card);border:1px solid var(--border);border-left:3px solid #043B72;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
.pm-section h3{font-size:15px;font-weight:700;color:#043B72;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.pm-section ul{list-style:none;padding:0;margin:0}
.pm-section li{font-size:13.5px;color:#2d3148;line-height:1.75;margin-bottom:6px;padding-left:12px;position:relative}
.pm-section li::before{content:'·';position:absolute;left:0;color:#043B72;font-weight:700}
.pm-section li:last-child{margin-bottom:0}
.pm-section .pm-num{font-weight:600;color:#1a1d2e}
.pm-section .pm-up{color:#d92b2b;font-weight:600}
.pm-section .pm-dn{color:#1a5fb4;font-weight:600}
.pm-section .pm-note{font-size:12px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px dashed var(--border)}
.pm-footer{font-size:12px;color:var(--muted);border-top:1px solid var(--border);padding-top:10px;margin-top:12px;text-align:center}

/* Macro */
.macro-header{background:linear-gradient(135deg,#f0f4ff,#e8edf8);border:1px solid var(--border);border-left:4px solid #043B72;border-radius:12px;padding:18px 24px;margin-bottom:20px}
.macro-header h2{font-size:13px;color:#043B72;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}
.macro-header .mh-sub{font-size:12px;color:var(--muted)}
.macro-block{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px 24px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
.macro-block h3{font-size:15px;font-weight:700;color:#1a1d2e;margin-bottom:10px;padding-bottom:7px;border-bottom:1.5px solid var(--border)}
.macro-block ul{margin:0;padding-left:18px;font-size:13px;color:#2d3148;line-height:1.85}
.macro-block li{margin-bottom:3px}
.macro-kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.macro-kpi{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 14px;text-align:center}
.macro-kpi-label{font-size:11px;color:var(--muted);margin-bottom:4px}
.macro-kpi-value{font-size:16px;font-weight:700;color:#1a1d2e}
.macro-kpi-sub{font-size:11px;color:var(--muted);margin-top:2px}
.event-table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px}
.event-table th{background:#f7f8fc;font-size:12px;font-weight:600;color:var(--muted);padding:7px 10px;text-align:left;border-bottom:1px solid var(--border)}
.event-table td{padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#2d3148}
.event-table tr:last-child td{border-bottom:none}
.imp-high{color:var(--down);font-weight:700}.imp-med{color:#d47f00;font-weight:600}.imp-low{color:var(--muted)}
"""

TAB_BAR = """\
<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('cs')">CS Story</button>
  <button class="tab-btn" onclick="switchTab('pm')">PM Story</button>
  <button class="tab-btn" onclick="switchTab('story')">Market Story</button>
  <button class="tab-btn" onclick="switchTab('macro')">Macro &amp; Events</button>
</div>
"""

SWITCH_JS = """\
<script>
function switchTab(id){
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  event.target.classList.add('active');
}
</script>
"""


def _bedrock_generate(client, system: str, user: str, max_tokens: int = 8000) -> str:
    resp = client.messages.create(
        model=BEDROCK_MODEL,
        max_tokens=max_tokens,
        temperature=0.3,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(
        getattr(blk, "text", "") for blk in resp.content if getattr(blk, "type", "") == "text"
    )
    text = re.sub(r"^```(?:html)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    in_t = getattr(resp.usage, "input_tokens", 0)
    out_t = getattr(resp.usage, "output_tokens", 0)
    print(f"  [Bedrock] input={in_t:,} output={out_t:,} total={in_t+out_t:,}")
    return text.strip()


def _extract_body_inner(html: str) -> str:
    """기존 _ocr.html 에서 <body>...</body> 내부 + footer/disclaimer 까지 추출.
    header 와 disclaimer 는 합본에서 단일 인스턴스로 다시 배치하므로 본문 story 콘텐츠만 떼어낸다.
    """
    m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL)
    body = m.group(1) if m else html
    # header 와 footer/disclaimer 는 합본 wrapper 에서 별도 처리하므로 제거
    body = re.sub(r'<div class="header">.*?</div>\s*</div>', "", body, count=1, flags=re.DOTALL)
    body = re.sub(r'<div class="footer">.*?</div>', "", body, count=1, flags=re.DOTALL)
    body = re.sub(r'<div class="ai-disclaimer">.*?</div>', "", body, count=1, flags=re.DOTALL)
    return body.strip()


def _extract_ocr_style_block(html: str) -> str:
    """기존 _ocr.html 의 <style>...</style> 내부 CSS 추출 (story/causal-chain/session-grid 정의)."""
    m = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    return m.group(1) if m else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date)
    year_month = target_date.strftime("%Y-%m")
    out_dir = ROOT / "output" / "summary" / year_month
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. OCR 본문 로드
    ocr_path = ROOT / "logs" / f"{target_date}_briefing_ocr.txt"
    if not ocr_path.exists():
        print(f"[ERROR] OCR 본문 없음: {ocr_path}")
        sys.exit(1)
    ocr_text = ocr_path.read_text(encoding="utf-8")
    print(f"[1/5] OCR 본문 로드: {len(ocr_text):,}자")

    # 2. 기존 _ocr.html (Story 탭 소스) 로드
    story_path = out_dir / f"{target_date}_ocr.html"
    if not story_path.exists():
        print(f"[ERROR] Story HTML 없음: {story_path} — 먼저 generate_ocr_story.py 실행 필요")
        sys.exit(1)
    story_html = story_path.read_text(encoding="utf-8")
    story_inner = _extract_body_inner(story_html)
    story_css = _extract_ocr_style_block(story_html)
    print(f"[2/5] Story HTML 로드: {len(story_inner):,}자 (Story 탭 소스)")

    # 3. Bedrock 으로 CS / PM / Macro 본문 생성
    client = _get_bedrock_client()
    weekday_kr = "월화수목금토일"[target_date.weekday()]
    user_template = (
        f"날짜: {target_date} ({weekday_kr}요일)\n\n"
        f"--- PDF OCR 원문 (1차 자료) ---\n{ocr_text}\n"
    )

    print("[3/5] CS Story 생성 중 (Bedrock)...")
    cs_html = _bedrock_generate(client, CS_SYSTEM, user_template)
    print("[4/5] PM Story 생성 중 (Bedrock)...")
    pm_html = _bedrock_generate(client, PM_SYSTEM, user_template, max_tokens=10000)

    # Macro 는 기존 {date}_macro.html 을 그대로 사용 (Bedrock 생성 안 함)
    macro_path = out_dir / f"{target_date}_macro.html"
    if macro_path.exists():
        macro_html = macro_path.read_text(encoding="utf-8")
        print(f"[5/5] Macro 탭: 기존 {macro_path.name} 그대로 사용 ({len(macro_html):,}자)")
    else:
        macro_html = (
            f'<div class="macro-block"><h3>매크로 자료 없음</h3>'
            f'<p>{macro_path.name} 파일이 없습니다.</p></div>'
        )
        print(f"[5/5] Macro 탭: {macro_path.name} 없음 — placeholder 사용")

    # 4. 합본 HTML 조립
    page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Story (OCR Total) | {target_date}</title>
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');
:root {{
  --bg:#f4f5f9; --card:#fff; --card2:#f0f1f6;
  --border:#e0e3ed; --text:#2d3148; --muted:#7c8298;
  --accent:#F58220; --accent2:#043B72;
  --up:#d92b2b; --down:#1a5fb4; --warn:#CB6015;
  --gold:#b8860b; --oil:#d35400;
}}
::selection{{background:#F58220;color:#ffffff}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Spoqa Han Sans Neo','Spoqa Han Sans','Malgun Gothic',-apple-system,sans-serif;
  background:var(--bg);color:var(--text);
  line-height:1.65;padding:24px;max-width:1360px;margin:0 auto;
}}
.header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px;padding-bottom:20px;border-bottom:2px solid var(--border)}}
.header-left h1{{font-size:26px;font-weight:700;color:#1a1d2e;margin-bottom:2px}}
.header-left .date{{font-size:13px;color:var(--muted);letter-spacing:1px}}
.header-right .source-badge{{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600;background:rgba(245,130,32,0.1);color:var(--accent)}}
.footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:40px;padding-top:20px;border-top:1px solid var(--border)}}
.ai-disclaimer{{text-align:center;color:var(--muted);font-size:11px;margin-top:24px;padding:12px 16px;background:rgba(0,0,0,0.03);border-radius:8px;line-height:1.6}}
.hl-up{{color:var(--up);font-weight:600}}
.hl-down{{color:var(--down);font-weight:600}}
.hl-warn{{color:var(--warn);font-weight:600}}
{EXTRA_CSS}
{story_css}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <h1>🏛 미래에셋 모닝 브리핑 — OCR 합본 (Story · CS · PM · Macro)</h1>
    <div class="date">PDF 발간 기준 · 본문 시점 {target_date} ({weekday_kr}) 미국 마감</div>
  </div>
  <div class="header-right">
    <span class="source-badge">PDF 1차 자료 합본</span>
  </div>
</div>

{TAB_BAR}

<div id="tab-cs" class="tab-panel active">
{cs_html}
</div>

<div id="tab-pm" class="tab-panel">
{pm_html}
</div>

<div id="tab-story" class="tab-panel">
{story_inner}
</div>

<div id="tab-macro" class="tab-panel">
{macro_html}
</div>

<div class="footer">미래에셋증권 'AI 데일리 글로벌 마켓 브리핑' + '한국/중국 마켓 클로징' PDF &mdash; Bedrock Claude Sonnet 4.5 OCR + 4 탭(Story · CS · PM · Macro) 합본.</div>
<div class="ai-disclaimer">⚠️ 본 자료는 미래에셋증권 PDF 원본을 OCR 추출한 <strong>1차 자료 보존</strong>입니다. PDF 발간 시점(아침 KST) 기준으로 작성되어 메인 Market Story 와 시점·범위가 다릅니다. 수치는 PDF 본문 그대로이며, 투자 판단 시 PDF 원본을 확인하시기 바랍니다.</div>

{SWITCH_JS}
</body>
</html>
"""

    total_path = out_dir / f"{target_date}_ocr_total.html"
    total_path.write_text(page, encoding="utf-8")
    print(f"\n✅ 합본 HTML 저장: {total_path}")
    print(f"   크기: {len(page):,}자")


if __name__ == "__main__":
    main()
