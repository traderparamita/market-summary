"""
08:10 KST 자동 실행 — 미래에셋증권 AI 데일리 글로벌 마켓 브리핑 PDF를 찾아
OpenAI Vision OCR로 Market Story를 생성하고 기존 _story.html + 메인 .html 을 덮어쓴다.

PDF 탐색 규칙:
  - target_date = 장 기준일 (06:50 generate.py 와 동일한 날짜)
  - 보고서는 target_date 미국장 마감 후 익영업일 새벽에 사이트 게시
  - 사이트 row_date = target_date + 1영업일
  - 보고서 제목의 한글 날짜(예: "4월 29일") = target_date

Usage:
    .venv/bin/python scripts/generate_ocr_story.py [--date YYYY-MM-DD] [--dry-run]
    (--date 생략 시 직전 영업일 자동 계산)
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import boto3
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

S3_BUCKET = os.getenv("S3_BUCKET_NAME", "mai-life-fund-documents-533370893966-ap-northeast-2-an")
S3_PDF_PREFIX = "anthillia/miraeasset-daily"
S3_REGION = os.getenv("AWS_REGION", "ap-northeast-2")

import notify_telegram

LOG_DIR = ROOT / "logs"


def _log_and_notify_usage(resp, label: str) -> None:
    """GPT 응답에서 토큰 사용량을 추출해 로그 출력 + 텔레그램 전송."""
    usage = getattr(resp, "usage", None)
    if not usage:
        return
    prompt = getattr(usage, "prompt_tokens", 0)
    completion = getattr(usage, "completion_tokens", 0)
    log.info(f"[GPT tokens] {label}: prompt={prompt:,} completion={completion:,} total={prompt+completion:,}")
    msg = notify_telegram.build_gpt_usage_message("generate_ocr_story", label, prompt, completion)
    notify_telegram.send(msg)
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "ocr_story.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── 미래에셋증권 스크래핑 ────────────────────────────────────────────────────

BASE_URL = "https://securities.miraeasset.com"
LIST_URL = f"{BASE_URL}/bbs/board/message/list.do"
CATEGORY_ID = "1521"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
DOWNLOAD_RE = re.compile(r"downConfirm\('([^']+)'\s*,\s*'(\d+)'")
DAILY_KEYWORDS = ["AI 데일리", "AI데일리", "글로벌 마켓 브리핑", "데일리 글로벌"]


def prev_business_day(d: date) -> date:
    """d 직전 영업일."""
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_business_day(d: date) -> date:
    """d 다음 영업일."""
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def find_daily_briefing_pdf(target_date: date) -> dict | None:
    """target_date 장 기준 AI 데일리 브리핑 PDF를 찾는다.

    게시일 패턴:
      - 대부분: 미국장 마감 당일 새벽(한국시간) → row_date == target_date
      - 가끔:   익영업일 새벽 → row_date == next_business_day(target_date)
    따라서 row_date 조건 대신 제목의 한글 날짜(예: "4월 28일")로만 식별한다.
    탐색은 최대 10페이지, row_date 가 target_date -3일 이전이면 중단.
    """
    session = requests.Session()
    title_date_ko = f"{target_date.month}월 {target_date.day}일"
    cutoff = (target_date - timedelta(days=3)).strftime("%Y-%m-%d")
    log.info(f"PDF 탐색: 장 기준일={target_date}, 제목 키워드='{title_date_ko}'")

    for page in range(1, 11):
        params = {"categoryId": CATEGORY_ID, "curPage": str(page)}
        try:
            resp = session.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
            resp.encoding = "euc-kr"
        except Exception as e:
            log.warning(f"스크래핑 오류 (page {page}): {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        tables = soup.find_all("table")
        if len(tables) < 2:
            break

        rows = tables[1].find_all("tr")[1:]
        if not rows:
            break

        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            row_date = tds[0].get_text(strip=True)
            title_a = tds[1].find("a")
            title = title_a.get_text(strip=True) if title_a else ""

            # target_date -3일 이전이면 더 볼 필요 없음
            if row_date < cutoff:
                log.info(f"탐색 범위 초과({row_date} < {cutoff}) → 중단")
                return None

            if not any(kw in title for kw in DAILY_KEYWORDS):
                continue

            # 제목의 한글 날짜로 target_date 검증
            if title_date_ko not in title:
                log.debug(f"날짜 불일치 스킵: '{title[:60]}'")
                continue

            down_a = tds[2].find("a", href=re.compile(r"downConfirm"))
            if not down_a:
                continue
            m = DOWNLOAD_RE.search(down_a["href"])
            if not m:
                continue

            pdf_url, attach_id = m.group(1), m.group(2)
            log.info(f"PDF 발견: {title[:60]} | attachId={attach_id}")
            return {"title": title, "pdf_url": pdf_url, "attach_id": attach_id, "date": row_date}

    log.info("AI 데일리 브리핑 PDF 미발견")
    return None


# ── PDF → OCR ────────────────────────────────────────────────────────────────

OCR_SYSTEM = """당신은 미래에셋증권 'AI 데일리 글로벌 마켓 브리핑' PDF를 구조화된 텍스트로 변환하는 전문가입니다.

아래 형식으로 정확히 추출해주세요:

## 제목
(보고서 제목과 부제)

## Summary
(요약 섹션 전문)

## 주요 이벤트
(각 이벤트 제목 + 본문)

## 특징종목
(각 카테고리별 종목 및 수치)

## 채권/외환/상품
(금리, 환율, 원자재 데이터)

규칙:
- 모든 수치(지수, 등락률, 금리, 환율)를 빠짐없이 추출
- 종목명과 등락률을 정확히 매칭
- 원문 그대로 추출 (요약하지 말 것)
"""

STORY_SYSTEM = """당신은 글로벌 시장 해설 전문가입니다.
미래에셋증권 브리핑 원문(이벤트·맥락)과 시장 데이터(ground truth 수치)를 결합해
Market Story HTML 섹션들을 작성합니다.

### 핵심 원칙
- 수치는 반드시 [시장 데이터] 의 값만 사용 (보고서 수치 대신)
- 이벤트 맥락·종목 스토리·배경 설명은 [브리핑 원문] 에서 가져옴
- 아시아→유럽→미국 시간 순서 엄수 (미래 세션 데이터를 이전 세션에 사용 금지)

### 색상 규칙
- 상승/긍정: <span class="hl-up">+X%</span>  (빨간색)
- 하락/부정: <span class="hl-down">−X%</span>  (파란색)
- 보합/경고: <span class="hl-warn">±X%</span>  (주황색)

### ★ 품질 기준 (반드시 준수)

1. **session-events 리스트 항목**: 단순 한 줄 요약 금지. 수치·종목명·원인을 포함한 1~2문장.
   ❌ BAD:  <li><span class="ev-time">09:00</span> KOSPI 상승 시작</li>
   ✅ GOOD: <li><span class="ev-time">09:00</span> KOSPI 강세 출발 &mdash; 전일 미국장 약보합에도 삼성전자 <span class="hl-up">+1.80%</span>(226,000원) 주도로 반도체·대형주 강세. SK하이닉스 동반 상승</li>

2. **session-verdict**: 단순 "혼조세" 금지. 오늘의 핵심 사건·원인을 담는다.
   ❌ BAD:  <span class="session-verdict verdict-mixed">혼조세</span>
   ✅ GOOD: <span class="session-verdict verdict-up">KOSPI·항셍 강세 &middot; 유가 우려는 아직 미반영</span>

3. **af-node 구조**: 반드시 af-node-title / af-node-value / af-node-chg 3개 내부 div 사용.
   ❌ BAD:  <div class="af-node">유가 상승</div>
   ✅ GOOD:
   <div class="af-node">
     <div class="af-node-title">Brent / WTI</div>
     <div class="af-node-value">$113.37 / $106.88</div>
     <div class="af-node-chg up">+8.69% / +6.95%</div>
   </div>

4. **insight-card `<p>`**: 반드시 3단락 구성. 각 3~5문장.
   - 1단락: 오늘 사건이 왜 중요한지 (초보자 눈높이)
   - 2단락: 작동 메커니즘 (인과 경로)
   - 3단락: 투자 시사점 / 관련 지표 해석
   단락 구분은 <br><br>

5. **risk-item**: `<strong>리스크 제목</strong><br>` 뒤에 2~3문장 시나리오.
   ❌ BAD:  <span>중동 지역의 지정학적 리스크가 에너지 시장에 미치는 영향</span>
   ✅ GOOD: <span><strong>유가 $120 돌파 가능성 &mdash; 이란 봉쇄 장기화 시나리오</strong><br>
     브렌트유가 장중 $119대를 터치한 뒤 $113에 마감했습니다. 이란 핵 합의 진전이 없는 한 봉쇄는 유지될 전망이며, 추가 공급 차질 시 $120 → $130 시나리오까지 열립니다.</span>

6. **출력 형식**: HTML만 출력. 마크다운 코드 블록(```html ... ```) 절대 사용 금지. 섹션 외 텍스트 없이.

7. **투자 권유 표현 절대 금지**: "투자자들은 ~해야 합니다", "~에 주목할 필요가 있습니다", "~을 추천합니다" 등 매수·매도를 직·간접으로 유도하는 표현 사용 금지. 시장 사실과 인과관계만 서술할 것.

### 출력할 섹션 (순서 고정)

1. Story Hero
<div class="story-hero">
  <h2>오늘의 시장 이야기</h2>
  <div class="story-text">
    <strong>[핵심 이벤트를 담은 한 줄 헤드라인 — 숫자·종목·사건 포함]</strong><br><br>
    [아시아 세션 서술 — KOSPI·HSI·TWSE 수치와 주도 종목 포함, 2~3문장]<br><br>
    <strong>유럽 세션</strong>[유럽 서술 — 주요 지수 수치·원인 포함, 2~3문장]<br><br>
    <strong>미국 세션</strong>[미국 서술 — 지수 수치·핵심 이벤트·장 후 실적 포함, 3~4문장]
  </div>
</div>

2. Causal Chain (4노드)
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 핵심 흐름 &mdash; 하나의 체인으로 이해하기</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:16px;">[인과 흐름을 한 문장으로]</div>
<div class="causal-chain">
  <div class="cause-node">
    <div class="node-label">아시아 오전</div>
    <div class="node-title">[지수명 수치 포함 제목]</div>
    <div class="node-detail">[주도 종목·수치·원인 2줄]</div>
    <div class="node-impact up|down|mixed">[영향 한 줄]</div>
  </div>
  <div class="cause-arrow">&rarr;</div>
  ... (총 4노드 + 3화살표)
</div>

3. Session Grid
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">세계 시장은 릴레이처럼 돌아갑니다</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:16px;">[오늘 릴레이의 핵심 줄기 한 문장]</div>
<div class="session-grid">
  <div class="session-block asia">
    <div class="session-header">
      <div class="session-icon asia">&#127472;&#127479;</div>
      <div><div class="session-name">아시아 세션</div><div class="session-time">한국 09:00 ~ 15:30</div></div>
    </div>
    <span class="session-verdict verdict-up|down|mixed|flat">[핵심 사건 포함 판정 문구]</span>
    <ul class="session-events">
      <li><span class="ev-time">09:00</span> [종목명+수치+원인 포함 이벤트]</li>
      <li><span class="ev-time">10:30</span> [종목명+수치+원인 포함 이벤트]</li>
      <li><span class="ev-time">13:00</span> [종목명+수치+원인 포함 이벤트]</li>
      <li><span class="ev-time">15:30</span> [마감 수치 + 주요 지표]</li>
    </ul>
    <div class="session-kpi">
      <div class="s-kpi"><div class="s-kpi-label">KOSPI</div><div class="s-kpi-value up|down|flat">±X%</div></div>
      <div class="s-kpi"><div class="s-kpi-label">HSI</div><div class="s-kpi-value ...">±X%</div></div>
      <div class="s-kpi"><div class="s-kpi-label">TWSE</div><div class="s-kpi-value ...">±X%</div></div>
    </div>
  </div>
  <!-- 유럽·미국 블록도 동일 구조 -->
</div>

4. Insight Grid (4카드)
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">알아두면 좋은 시장 상식 4가지</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:16px;">오늘의 뉴스를 이해하기 위해 꼭 알아야 할 개념들을 쉽게 설명합니다.</div>
<div class="insight-grid">
  <div class="insight-card">
    <span class="badge" style="background:rgba(...);color:...">[카테고리]</span>
    <h3>[오늘 사건과 직결된 개념 제목]</h3>
    <p>
      [1단락: 오늘 왜 이 개념이 중요한지 — 오늘 수치 인용]<br><br>
      [2단락: 메커니즘 — 인과 경로 설명]<br><br>
      [3단락: 투자 시사점 / 관련 자산·섹터 영향]
    </p>
    <div class="metric-row">
      <div class="metric-item"><div class="metric-label">[지표1]</div><div class="metric-value up|down">[수치]</div></div>
      <div class="metric-item"><div class="metric-label">[지표2]</div><div class="metric-value up|down">[수치]</div></div>
      <div class="metric-item"><div class="metric-label">[지표3]</div><div class="metric-value up|down">[수치]</div></div>
    </div>
  </div>
  <!-- 4카드 총 -->
</div>

5. Risk Section
<div class="risk-section">
  <h2>앞으로 주의해야 할 점</h2>
  <div style="font-size:12px;color:var(--muted);margin-bottom:16px;">[현재 시장 압력 요약]</div>
  <ul class="risk-items">
    <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>[리스크 제목 — 임계치 포함]</strong><br>[2~3문장 시나리오·근거]</span></li>
    <li class="risk-item"><span class="risk-tag high">높음</span><span><strong>[리스크 제목]</strong><br>[2~3문장]</span></li>
    <li class="risk-item"><span class="risk-tag med">보통</span><span><strong>[리스크 제목]</strong><br>[2~3문장]</span></li>
  </ul>
</div>
"""


def ocr_pdf(pdf_path: Path) -> str:
    from pdf2image import convert_from_path
    from openai import OpenAI

    client = OpenAI()
    images = convert_from_path(str(pdf_path), dpi=200)
    log.info(f"PDF → {len(images)}페이지 변환")

    content = []
    for i, img in enumerate(images):
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp.name, "PNG")
        with open(tmp.name, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        content.append({"type": "text", "text": f"[페이지 {i+1}/{len(images)}]"})
        content.append({"type": "image_url", "image_url": {
            "url": f"data:image/png;base64,{b64}", "detail": "high"
        }})

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": OCR_SYSTEM},
            {"role": "user", "content": content},
        ],
        max_tokens=4096,
        temperature=0,
    )
    _log_and_notify_usage(resp, "ocr_pdf")
    return resp.choices[0].message.content


def generate_story_html(ocr_text: str, data_json: dict, target_date: date) -> str:
    from openai import OpenAI

    client = OpenAI()

    def _fmt(cat: str, keys: list) -> str:
        lines = []
        for k in keys:
            v = data_json.get(cat, {}).get(k, {})
            if not v:
                continue
            chg = v.get("daily", "?")
            chg_str = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else str(chg)
            lines.append(f"  {k}: {v.get('close', '?')} ({chg_str})")
        return "\n".join(lines) if lines else "  (데이터 없음)"

    eq   = ["KOSPI","KOSDAQ","TWSE","NIKKEI225","SSE","HSI","S&P500","NASDAQ","DOW","RUSSELL2K","DAX","CAC40","FTSE100","STOXX50"]
    bond = ["US 10Y","US 2Y","KR 10Y","KR 3Y","US 30Y","US 10-2 Spread"]
    fx   = ["DXY","USD/KRW","USD/JPY","EUR/USD","AUD/USD"]
    comm = ["WTI","Brent","Gold","Silver","Copper","NatGas"]
    stk  = list(data_json.get("stocks", {}).keys())
    sec  = list(data_json.get("sector_us", {}).keys())
    vix  = data_json.get("risk", {}).get("VIX", {})
    vix_str = f"  VIX: {vix.get('close','?')} ({vix.get('daily','?')}%)" if vix else ""

    market_data = f"""=== {target_date} 시장 데이터 (ground truth — 수치는 이것만 사용) ===

[주요 지수]
{_fmt('equity', eq)}

[채권 금리]
{_fmt('bond', bond)}

[외환]
{_fmt('fx', fx)}

[원자재]
{_fmt('commodity', comm)}

[개별 종목]
{_fmt('stocks', stk)}

[미국 섹터 ETF]
{_fmt('sector_us', sec)}

[변동성]
{vix_str}
"""

    user_msg = f"""아래 미래에셋증권 브리핑 원문과 시장 데이터를 바탕으로 Market Story HTML 섹션 1~5를 순서대로 작성하세요.
섹션 외 다른 텍스트는 출력하지 마세요.

--- 브리핑 원문 ---
{ocr_text}

--- 시장 데이터 ---
{market_data}
"""

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STORY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=8192,
        temperature=0.3,
    )
    _log_and_notify_usage(resp, "generate_story_html")
    story = resp.choices[0].message.content
    # GPT가 ```html ... ``` 코드블록으로 감싸는 경우 제거
    story = re.sub(r'^```(?:html)?\s*', '', story.strip())
    story = re.sub(r'\s*```$', '', story)
    return story.strip()


# ── 독립 OCR HTML 파일 생성 ──────────────────────────────────────────────────

OCR_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Story (OCR) | {date}</title>
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
.story-hero{{border-left-color:#3b6ee6!important}}
.story-hero h2{{color:#3b6ee6!important}}
.story-text .hl-accent{{color:#3b6ee6!important}}
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
.story-hero{{background:linear-gradient(135deg,#eef1f8,#e8e5f3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:32px}}
.story-hero h2{{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}}
.story-text{{font-size:16px;color:#2d3148;line-height:1.9}}
.story-text strong{{color:#1a1d2e}}.story-text .hl-up{{color:var(--up);font-weight:600}}.story-text .hl-down{{color:var(--down);font-weight:600}}.story-text .hl-warn{{color:var(--warn);font-weight:600}}
.causal-chain{{display:flex;align-items:stretch;gap:0;margin-bottom:28px;overflow-x:auto;padding-bottom:8px}}
.cause-node{{flex:1;min-width:160px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 14px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.cause-node .node-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
.cause-node .node-title{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:4px}}
.cause-node .node-detail{{font-size:12px;color:var(--text)}}
.cause-node .node-impact{{margin-top:8px;font-size:17px;font-weight:700}}
.cause-arrow{{display:flex;align-items:center;padding:0 4px;color:var(--muted);font-size:18px;flex-shrink:0}}
.session-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:32px}}
.session-block{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;position:relative;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.session-block::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px}}
.session-block.asia::before{{background:linear-gradient(90deg,#d48b07,#e06818)}}
.session-block.europe::before{{background:linear-gradient(90deg,#F58220,#043B72)}}
.session-block.us::before{{background:linear-gradient(90deg,#043B72,#7F9FC3)}}
.session-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.session-icon{{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px}}
.session-icon.asia{{background:rgba(212,139,7,0.1)}}.session-icon.europe{{background:rgba(59,110,230,0.1)}}.session-icon.us{{background:rgba(107,92,231,0.1)}}
.session-name{{font-size:15px;font-weight:600;color:#1a1d2e}}
.session-time{{font-size:11px;color:var(--muted)}}
.session-verdict{{display:inline-block;padding:3px 10px;border-radius:16px;font-size:11px;font-weight:600;margin-bottom:10px}}
.verdict-up{{background:rgba(13,155,106,0.1);color:var(--up)}}.verdict-down{{background:rgba(217,48,79,0.1);color:var(--down)}}.verdict-mixed{{background:rgba(212,139,7,0.1);color:var(--warn)}}.verdict-flat{{background:rgba(124,130,152,0.1);color:var(--muted)}}
.session-events{{list-style:none}}.session-events li{{font-size:12px;padding:6px 0 6px 12px;border-bottom:1px solid #f3f4f8;position:relative}}
.session-events li:last-child{{border:none}}.session-events li::before{{content:'';position:absolute;left:0;top:12px;width:4px;height:4px;border-radius:50%;background:var(--muted)}}
.session-events .ev-time{{color:var(--muted);font-size:10px;font-weight:600}}
.session-kpi{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:10px;padding-top:10px;border-top:1px solid var(--border)}}
.s-kpi{{text-align:center;padding:6px;border-radius:6px;background:var(--card2)}}
.s-kpi-label{{font-size:10px;color:var(--muted)}}.s-kpi-value{{font-size:15px;font-weight:700}}
.insight-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:32px}}
.insight-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:22px;position:relative;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.insight-card .badge{{position:absolute;top:14px;right:14px;padding:2px 10px;border-radius:16px;font-size:11px;font-weight:600}}
.insight-card h3{{font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:10px;padding-right:50px}}
.insight-card p{{font-size:13px;color:var(--text);line-height:1.8}}
.insight-card .metric-row{{display:flex;gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}}
.metric-item{{flex:1;text-align:center}}.metric-label{{font-size:10px;color:var(--muted)}}.metric-value{{font-size:16px;font-weight:700;font-family:'JetBrains Mono',monospace}}
.cross-asset{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:28px;margin-bottom:28px;box-shadow:0 2px 6px rgba(0,0,0,0.04)}}
.cross-asset h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:6px}}
.cross-asset .sub{{font-size:12px;color:var(--muted);margin-bottom:18px}}
.af-map{{display:grid;grid-template-columns:auto 1fr auto 1fr auto;align-items:center;gap:10px 6px}}
.af-node{{background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:12px 14px;text-align:center;min-width:120px}}
.af-node-title{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}}
.af-node-value{{font-size:18px;font-weight:700;color:#1a1d2e;font-family:'JetBrains Mono',monospace}}
.af-node-chg{{font-size:12px;font-weight:600}}
.af-arrow{{text-align:center;color:var(--muted);font-size:12px;line-height:1.3}}
.af-arrow .arr{{font-size:16px;display:block}}.af-arrow .lbl{{font-size:10px}}
.risk-section{{background:linear-gradient(135deg,#fdf2f4,#f8f5ff);border:1px solid rgba(217,48,79,0.12);border-radius:12px;padding:28px;margin-bottom:28px}}
.risk-section h2{{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:16px}}
.risk-items{{list-style:none;display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.risk-item{{display:flex;align-items:flex-start;gap:8px;padding:10px 14px;border-radius:8px;background:rgba(255,255,255,0.6);font-size:12px;line-height:1.6}}
.risk-tag{{flex-shrink:0;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;margin-top:1px}}
.risk-tag.high{{background:rgba(217,48,79,0.15);color:var(--down)}}.risk-tag.med{{background:rgba(212,139,7,0.15);color:var(--warn)}}
.up{{color:var(--up)}}.down{{color:var(--down)}}.flat{{color:var(--muted)}}
.footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:40px;padding-top:20px;border-top:1px solid var(--border)}}
.ai-disclaimer{{text-align:center;color:var(--muted);font-size:11px;margin-top:24px;padding:12px 16px;background:rgba(0,0,0,0.03);border-radius:8px;line-height:1.6}}
@media(max-width:900px){{
  .session-grid,.insight-grid{{grid-template-columns:1fr}}
  .causal-chain{{flex-direction:column}}.cause-arrow{{transform:rotate(90deg);padding:4px 0}}
  .af-map{{grid-template-columns:1fr}}.risk-items{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <h1>Daily Market Story</h1>
    <div class="date">{date_long}</div>
  </div>
  <div class="header-right">
    <span class="source-badge">PDF OCR &rarr; Story</span>
  </div>
</div>
{story_html}
<div class="footer">Market Summary &mdash; AI-generated from Mirae Asset Securities PDF (OCR) + market data</div>
<div class="ai-disclaimer">⚠️ 본 보고서는 AI가 자동 생성한 참고 자료이며, <strong>투자 권유가 아닙니다.</strong> 미래에셋증권 AI 데일리 글로벌 마켓 브리핑 PDF를 OpenAI Vision API로 추출·재구성한 내부 검토용 자료로, 수치·해석에 오류가 포함될 수 있습니다. 투자 판단 시 반드시 원본 데이터를 확인하시기 바랍니다.</div>
</body>
</html>
"""

_DOW_KO = ["월", "화", "수", "목", "금", "토", "일"]


def upload_pdf_to_s3(pdf_path: Path, target_date: date) -> str | None:
    """PDF를 S3에 업로드하고 S3 키를 반환. 실패 시 None (non-fatal)."""
    s3_key = f"{S3_PDF_PREFIX}/{target_date.strftime('%Y-%m')}/{target_date}_briefing.pdf"
    try:
        session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=S3_REGION,
        )
        client = session.client("s3", endpoint_url=f"https://s3.{S3_REGION}.amazonaws.com")
        client.upload_file(
            str(pdf_path),
            S3_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": "application/pdf"},
        )
        log.info(f"S3 업로드 완료: s3://{S3_BUCKET}/{s3_key}")
        return s3_key
    except Exception as e:
        log.warning(f"S3 업로드 실패 (non-fatal): {e}")
        return None


def save_ocr_html(out_dir: Path, target_date: date, story_html: str) -> Path:
    """독립 _ocr.html 파일 저장 — 기존 .html / _story.html 은 건드리지 않는다."""
    dow = _DOW_KO[target_date.weekday()]
    date_long = f"{target_date.strftime('%Y-%m-%d')} ({dow})"
    html = OCR_HTML_TEMPLATE.format(
        date=str(target_date),
        date_long=date_long,
        story_html=story_html,
    )
    ocr_path = out_dir / f"{target_date}_ocr.html"
    ocr_path.write_text(html, encoding="utf-8")
    log.info(f"_ocr.html 저장: {ocr_path.name}")
    return ocr_path


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None,
                        help="장 기준일 YYYY-MM-DD (기본: 직전 영업일)")
    parser.add_argument("--dry-run", action="store_true",
                        help="파일 저장 없이 흐름만 확인")
    args = parser.parse_args()

    if args.date:
        target_date = date.fromisoformat(args.date)
    else:
        target_date = prev_business_day(date.today())

    log.info(f"=== OCR Story 시작: {target_date} ===")

    # _data.json 로드
    data_path = (ROOT / "output" / "summary"
                 / target_date.strftime("%Y-%m")
                 / f"{target_date}_data.json")
    if not data_path.exists():
        log.error(f"_data.json 없음: {data_path}  →  먼저 generate.py 를 실행하세요")
        sys.exit(1)
    with open(data_path, encoding="utf-8") as f:
        data_json = json.load(f)
    log.info(f"_data.json 로드: {data_path.name}")

    out_dir = ROOT / "output" / "summary" / target_date.strftime("%Y-%m")

    # ── PDF 탐색 ──
    pdf_info = find_daily_briefing_pdf(target_date)
    if not pdf_info:
        msg = f"⚠️ *OCR Story 스킵* — {target_date}\n미래에셋증권 AI 데일리 브리핑 PDF를 찾지 못했습니다.\n_ocr.html 미생성."
        log.info("PDF 없음 → _ocr.html 생성 건너뜀, 텔레그램 알림 발송")
        notify_telegram.send(msg)
        print(f"[SKIP] {target_date} PDF 미발견")
        sys.exit(0)

    # ── PDF 다운로드 ──
    log.info(f"PDF 다운로드: {pdf_info['pdf_url']}")
    resp = requests.get(pdf_info["pdf_url"], headers=HEADERS, timeout=60)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(resp.content)
        pdf_path = Path(tmp.name)
    log.info(f"다운로드 완료: {len(resp.content)//1024}KB")

    # ── S3 업로드 ──
    s3_key = upload_pdf_to_s3(pdf_path, target_date)
    if s3_key:
        log.info(f"PDF S3 보관: s3://{S3_BUCKET}/{s3_key}")
        notify_telegram.send(
            f"📥 *브리핑 PDF 저장* — {target_date}\n"
            f"`s3://{S3_BUCKET}/{s3_key}`"
        )

    # ── OCR ──
    log.info("OCR 시작 (gpt-4o Vision)...")
    ocr_text = ocr_pdf(pdf_path)
    ocr_cache = LOG_DIR / f"{target_date}_briefing_ocr.txt"
    ocr_cache.write_text(ocr_text, encoding="utf-8")
    log.info(f"OCR 완료: {len(ocr_text)}자 → {ocr_cache.name}")

    # ── Story HTML 생성 ──
    log.info("Story HTML 생성 중 (gpt-4o)...")
    story_html = generate_story_html(ocr_text, data_json, target_date)
    log.info(f"Story 생성 완료: {len(story_html)}자")

    if args.dry_run:
        print("[DRY-RUN] Story HTML 미리보기 (앞 500자):")
        print(story_html[:500])
        sys.exit(0)

    # ── _ocr.html 저장 (기존 .html / _story.html 은 건드리지 않음) ──
    ocr_path = save_ocr_html(out_dir, target_date, story_html)
    log.info(f"=== 완료: {target_date} ===")
    print(f"✅ OCR HTML 생성: {ocr_path}")


if __name__ == "__main__":
    main()
