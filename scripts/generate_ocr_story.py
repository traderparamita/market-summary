"""
08:10 KST 자동 실행 — 미래에셋증권 두 PDF를 OCR해 Market Story 1차 자료를 생성한다.

▶ 두 PDF 소스 (둘 다 같은 거래일 = target_date 를 다룸)
  ① 한국/중국 마켓 클로징 (아시아 세션)
     - target_date 당일 오후 (장 종료 후 ~15:30 KST 이후) 발간
     - row_date = target_date
     - 본문 = target_date KR/CN 아시아 장 마감 데이터
  ② AI 데일리 글로벌 마켓 브리핑 (미국 세션)
     - target_date 미국장 마감 후 익영업일 새벽 KST 발간
     - row_date = target_date + 1영업일
     - 본문 = target_date 미국 세션 마감 데이터

▶ 결과
  - 두 PDF 가 다 있으면: 아시아(①) + 미국(②) 풀 사이클 1차 자료 보존
  - 미국(②) 만 있으면: 종전처럼 미국 세션 중심 (아시아는 한 줄 안내)
  - 아시아(①) 만 있으면: 미국은 한 줄 안내 (target_date 이 오늘이라 아직 발간 전인 경우)
  - 둘 다 없으면: 텔레그램 스킵 알림 + _ocr.html 미생성

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

from _utils import S3_BUCKET, prev_business_day as _prev_biz, next_business_day as _next_biz
import notify_telegram

S3_PDF_PREFIX = "anthillia/miraeasset-daily"
S3_REGION = os.getenv("AWS_REGION", "ap-northeast-2")

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
KR_CN_KEYWORDS = ["한국/중국 마켓 클로징", "한국/중국마켓 클로징", "마켓 클로징"]




def _find_pdf_by_keywords(
    target_date: date,
    keywords: list[str],
    valid_row_dates: set[str],
    label: str,
    max_pages: int = 10,
) -> dict | None:
    """미래에셋증권 일일자료 게시판에서 keywords / 게시일 후보로 PDF 1건 찾기.

    매칭 기준 = 게시일(row_date) + 제목 키워드.
    cutoff = target_date - 3일. 그보다 더 이전 페이지까지 가면 탐색 중단.
    """
    session = requests.Session()
    cutoff = (target_date - timedelta(days=3)).strftime("%Y-%m-%d")
    log.info(f"PDF 탐색 [{label}]: 장 기준일={target_date}, 게시일 후보={sorted(valid_row_dates)}")

    for page in range(1, max_pages + 1):
        params = {"categoryId": CATEGORY_ID, "curPage": str(page)}
        try:
            resp = session.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
            resp.encoding = "euc-kr"
        except Exception as e:
            log.warning(f"[{label}] 스크래핑 오류 (page {page}): {e}")
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

            if row_date < cutoff:
                log.info(f"[{label}] 탐색 범위 초과({row_date} < {cutoff}) → 중단")
                return None

            if not any(kw in title for kw in keywords):
                continue

            if row_date not in valid_row_dates:
                log.debug(f"[{label}] 게시일 불일치 스킵: row_date={row_date} title='{title[:60]}'")
                continue

            down_a = tds[2].find("a", href=re.compile(r"downConfirm"))
            if not down_a:
                continue
            m = DOWNLOAD_RE.search(down_a["href"])
            if not m:
                continue

            pdf_url, attach_id = m.group(1), m.group(2)
            log.info(f"[{label}] PDF 발견: row_date={row_date} | {title[:60]} | attachId={attach_id}")
            return {"title": title, "pdf_url": pdf_url, "attach_id": attach_id, "date": row_date}

    log.info(f"[{label}] PDF 미발견")
    return None


def find_daily_briefing_pdf(target_date: date) -> dict | None:
    """target_date 미국 세션을 다루는 AI 데일리 브리핑 PDF.

    유효 row_date 후보:
      - target_date          : 미국장 마감 당일 새벽(한국시간) 발간
      - next_business_day    : 익영업일 새벽 발간 (가장 흔함)
      - target_date + 1day   : 캘린더 익일 (KR 휴장 끼는 경우 대비)
    """
    valid_row_dates = {
        target_date.strftime("%Y-%m-%d"),
        _next_biz(target_date).strftime("%Y-%m-%d"),
        (target_date + timedelta(days=1)).strftime("%Y-%m-%d"),
    }
    return _find_pdf_by_keywords(target_date, DAILY_KEYWORDS, valid_row_dates, label="AI 데일리(미국)")


def find_kr_cn_closing_pdf(target_date: date) -> dict | None:
    """target_date 아시아(KR/CN) 세션 마감을 다루는 한국/중국 마켓 클로징 PDF.

    유효 row_date = target_date (당일 오후 발간) 만 허용.
    KR/CN 휴장 등으로 발간이 다음 영업일로 밀리는 패턴은 관측되지 않아 단일 후보.
    """
    valid_row_dates = {target_date.strftime("%Y-%m-%d")}
    return _find_pdf_by_keywords(target_date, KR_CN_KEYWORDS, valid_row_dates, label="KR/CN 클로징(아시아)")


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

STORY_SYSTEM = """당신은 미래에셋증권의 두 PDF(① 한국/중국 마켓 클로징 = 아시아 세션,
② AI 데일리 글로벌 마켓 브리핑 = 미국 세션) 원본을 HTML로 재구성해 보존하는
1차 자료 편집자입니다. 이 보고서는 메인 Market Story 와 별개로 운영되며, 증권사
권위 있는 PDF 의 디테일(특히 종목별 정밀 변동률)을 빠짐없이 살리는 것이 최우선입니다.

### 출처와 본문 시점 (둘 다 같은 거래일 = target_date)
- 아시아 세션 = [PDF ① 한국/중국 마켓 클로징] 만 사용. target_date 당일 KR/CN 장 마감.
- 미국 세션  = [PDF ② AI 데일리 글로벌 마켓 브리핑] 만 사용. target_date 미국 장 마감.
- 유럽 세션 = 둘 중 어느 PDF 에 언급이 있으면 인용, 없으면 한 줄 안내로 처리.
- **세션별 출처를 절대 섞지 않습니다** — 미국 PDF 에 KOSPI 가 있어도 아시아 블록은
  ①에서만, ①에 미국 지수가 있어도 미국 블록은 ②에서만 인용.
- [PDF 시점 메타] 블록에 어느 PDF 가 들어왔는지 명시됩니다. 빠진 PDF 가 있으면 해당
  세션 블록은 "본 자료에 해당 PDF 가 포함되지 않았습니다" 한 줄로 처리.

### 핵심 원칙 (절대 위반 금지)
- **PDF 본문이 유일한 1차 자료**. 수치·종목·이벤트는 모두 [브리핑 원문]에서만 인용.
  외부 데이터로 추정·반올림·치환·보충하지 않습니다.
- **[필수 포함 종목·수치] 목록의 모든 종목 변동률을 PDF 그대로 인용** — 수치 한 자리도
  바꾸지 않고, 메인 Story 처럼 거시 일반론으로 압축하지 않습니다.
- 일변동률·종가·bp 변화는 PDF 표기 자릿수 그대로 (예: 애플 +3.24%, ISM 물가 +6.3pt).
- PDF 에 없는 사실(예: SK하이닉스 시총 1,000조 같은 PDF 발간 후 사건)은 절대 추가하지
  않습니다 — 이 자료는 PDF 사진을 찍어 보존하는 역할입니다.
- 아시아→유럽→미국 시간 순서 엄수.

### ★ 환각(hallucination) 절대 금지 — 가장 흔한 실수 패턴
- KR/CN PDF 가 없을 때: 아시아 지수 수치(KOSPI/HSI/SHCOMP/SZSE/CSI300) 를 **절대
  만들어내지 않습니다**. session-events 에 "본 자료에 한국/중국 마켓 클로징 PDF 가
  포함되지 않았습니다" 한 줄로 처리.
- AI Daily PDF 가 없을 때: 미국 지수 수치 (S&P/나스닥/다우) 를 **절대 만들어내지
  않습니다**. session-events 에 같은 패턴의 한 줄 안내.
- 유럽 PDF 본문에 데이터가 없을 때: FTSE/DAX/CAC 수치 만들지 말 것.
- PDF 본문에 없는 지수의 KPI 카드는 "본 PDF 미수록" 으로 표기하거나 카드 자체를 생략.

### ★ 시간대 표기 — 한국 KST 기준으로 통일
- session-time 은 한국 KST 기준으로 표기 (현지 시간 표기 금지).
  ✅ "한국 09:00 ~ 15:30" (아시아) / "한국 16:00 ~ 01:30" (유럽) / "한국 22:30 ~ 06:00" (미국)
  ❌ "런던 08:00 ~ 16:30" / "뉴욕 09:30 ~ 16:00"
- session-events 의 시각도 KST 기준 (예: 미국 NFP 8:30 ET = KST 22:30 로 환산).

### ★ 종목 인용 임계치 — PDF 정밀도 살리기
- [필수 포함 종목·수치] 에 나열된 종목 중 **최소 18개 이상**을 본문(Story Hero 또는
  Session Grid 또는 Insight Grid) 어딘가에 변동률과 함께 인용.
- session-events 의 미국 블록 4개 항목은 각각 다른 종목·테마를 다뤄 PDF 의 다양성
  (반도체 / 소프트웨어 / 제약 / 소비재 / 에너지 등) 을 압축하지 않고 보존.
- Insight Grid 4 카드는 PDF 의 핵심 분석 4개를 그대로 카드화 (PDF 의 "특징종목" /
  "ISM" / "외환·채권" / "유가" / "비만 치료제" 등 섹션 활용).

### 색상 규칙
- 상승/긍정: <span class="hl-up">+X%</span>  (빨간색)
- 하락/부정: <span class="hl-down">−X%</span>  (파란색)
- 보합/경고: <span class="hl-warn">±X%</span>  (주황색)

### ★ 품질 기준 (반드시 준수)

1. **session-events 리스트 항목**: 단순 한 줄 요약 금지. 브리핑 원문의 구체 사건을 인용해 수치·종목명·원인을 포함한 1~2문장.
   ❌ BAD:  <li><span class="ev-time">09:00</span> KOSPI 상승 시작</li>
   ✅ GOOD: <li><span class="ev-time">09:00</span> KOSPI 강세 출발 &mdash; 전일 미국장 약보합에도 삼성전자 <span class="hl-up">+1.80%</span>(226,000원) 주도로 반도체·대형주 강세. SK하이닉스 동반 상승</li>
   ※ 아시아·유럽 시장이 공휴일인 경우: "휴장 (노동절 등)" 처리, ±0.00% 채우기 금지

2. **session-verdict**: 단순 "혼조세" 금지. 오늘의 핵심 사건·원인을 담는다.
   ❌ BAD:  <span class="session-verdict verdict-mixed">혼조세</span>
   ✅ GOOD: <span class="session-verdict verdict-up">KOSPI·항셍 강세 &middot; 유가 우려는 아직 미반영</span>

3. **insight-card `<p>`**: 반드시 3단락 구성. 각 3~5문장.
   - 1단락: PDF 본문의 구체 사건·수치를 인용하며 왜 중요한지 (초보자 눈높이)
   - 2단락: 작동 메커니즘 (인과 경로) — PDF 본문의 설명을 활용
   - 3단락: 관련 자산·섹터에 미치는 파급 효과 (사실 기술만, PDF 에 있는 내용만)
   단락 구분은 <br><br>
   ❌ BAD: "투자자들은 ~에 주목할 필요가 있습니다" 같은 일반론
   ❌ BAD: "기술주는 AI 인프라 투자에도 비용 우려가 존재합니다" 같은 백과사전식 풀이
   ✅ GOOD: PDF 의 실제 수치·종목·이벤트를 직접 인용 (예: "애플 +3.24%·아마존 +2.12%·
       MSFT +1.63% 등 빅테크 일제 강세. AI capex 4사 합산 $7,250억으로 지난해 대비 77% 상향")

4. **risk-item**: `<strong>리스크 제목</strong><br>` 뒤에 2~3문장 시나리오. 오늘 브리핑에서 언급된 리스크 요인을 우선 사용.
   ❌ BAD:  <span>중동 지역의 지정학적 리스크가 에너지 시장에 미치는 영향</span>
   ✅ GOOD: <span><strong>유가 $120 돌파 가능성 &mdash; 이란 봉쇄 장기화 시나리오</strong><br>
     브렌트유가 장중 $119대를 터치한 뒤 $113에 마감했습니다. 이란 핵 합의 진전이 없는 한 봉쇄는 유지될 전망이며, 추가 공급 차질 시 $120 → $130 시나리오까지 열립니다.</span>

5. **출력 형식**: HTML만 출력. 마크다운 코드 블록(```html ... ```) 절대 사용 금지. 섹션 외 텍스트 없이.

6. **투자 권유 표현 절대 금지**: "투자자들은 ~해야 합니다", "~에 주목할 필요가 있습니다", "~을 추천합니다" 등 매수·매도를 직·간접으로 유도하는 표현 사용 금지. 시장 사실과 인과관계만 서술할 것.

### 출력할 섹션 (순서 고정)

1. Story Hero (★ 가장 풍부하게 작성 — 본 자료의 핵심 페이지)
   - 두 PDF 의 디테일을 압축하지 말고 풍부하게 살립니다.
   - 헤드라인은 [PDF ②] 1면 헤드라인 + 핵심 수치 2~3개를 메인으로 하되, [PDF ①]
     이 함께 있으면 아시아 핵심 1개를 한 줄로 덧붙입니다 (예: "S&P500·나스닥 사상
     최고치 재경신 — 애플 +3.24%·오라클 +6.47% / KOSPI +1.2% 반도체 주도").
   - 아시아 세션 단락 (PDF ①이 있을 때): **5~7 문장** — KOSPI/KOSDAQ/SHCOMP/HSI 등
     지수 마감 + 한국 주도주(삼성전자·SK하이닉스·현대차 등) 변동률 + 중국 정책·
     섹터 흐름 + 외환(원/달러, 위안화) + 한국·중국 거시 이벤트. ①이 없으면 한 줄
     안내로 처리 ("본 자료에 한국/중국 마켓 클로징 PDF 가 포함되지 않았습니다 —
     아시아 세션 데이터는 메인 Market Story 를 참고하세요").
   - 미국 세션 단락 (PDF ②가 있을 때): **6~9 문장**으로 가장 길게 — 지수 마감
     (다우/S&P/나스닥/러셀2K 모두) + 빅테크 실적·주도주(애플/MSFT/아마존/알파벳)
     + 반도체(엔비디아/마이크론/AMD/브로드컴/샌디스크) + 소프트웨어(오라클·
     아틀라시안·세일즈포스) + 제약(일라이릴리·노보노디스크·암젠) + 거시·정책
     (ISM/고용/물가/협상) + VIX/채권/외환 핵심. ②가 없으면 한 줄 안내.
   - 유럽 세션은 두 PDF 어느 쪽이라도 데이터가 있을 때만 작성, 없으면 한 줄 안내.
<div class="story-hero">
  <h2>오늘의 시장 이야기</h2>
  <div class="story-text">
    <strong>[PDF 1면 헤드라인을 살린 한 줄 + 핵심 수치 2~3개]</strong><br><br>
    [아시아 세션: PDF 에 있으면 4~6문장, 없으면 "본 브리핑은 ~을 별도 다루지 않습니다" 한 줄]<br><br>
    <strong>유럽 세션</strong> [PDF 에 있으면 4~6문장, 없으면 한 줄 안내]<br><br>
    <strong>미국 세션</strong> [6~9문장으로 가장 풍부하게 — PDF 본문의 종목·이벤트·
    수치·정책을 압축하지 말고 모두 살립니다. 빅테크·반도체·소프트웨어·제약·소비재·
    에너지·거시(ISM)·외환·채권·VIX 가 한 단락에 담기도록 길게 쓰되, 시간순(개장→
    중간→마감) 으로 정렬.]
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
    images = convert_from_path(str(pdf_path), dpi=300)  # 200 → 300: 소수점·소형 숫자 인식 개선
    log.info(f"PDF → {len(images)}페이지 변환 (dpi=300)")

    # gpt-4o가 이미지를 거부할 때 반환하는 패턴
    REFUSAL_PATTERNS = [
        "I'm sorry, I can't",
        "I'm sorry, I cannot",
        "I can't assist",
        "I cannot assist",
        "죄송하지만",
        "제공할 수 없습니다",
    ]

    page_texts: list[str] = []
    for i, img in enumerate(images):
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp.name, "PNG")
        try:
            with open(tmp.name, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
        finally:
            os.unlink(tmp.name)

        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": OCR_SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": (
                        f"[페이지 {i+1}/{len(images)}] "
                        "이 금융 보고서 페이지에 인쇄된 한국어·영어 텍스트와 수치를 있는 그대로 모두 추출하세요. "
                        "차트·그래프가 있으면 축 레이블·범례·수치만 텍스트로 옮기세요."
                    )},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
                ]},
            ],
            max_tokens=2048,
            temperature=0,
        )
        _log_and_notify_usage(resp, f"ocr_pdf_p{i+1}")
        page_text = resp.choices[0].message.content.strip()

        # 거부 응답이면 스킵
        if any(pat in page_text for pat in REFUSAL_PATTERNS) and len(page_text) < 200:
            log.warning(f"  페이지 {i+1}/{len(images)} 거부 응답 → 스킵")
            continue

        page_texts.append(f"=== 페이지 {i+1} ===\n{page_text}")
        log.info(f"  페이지 {i+1}/{len(images)} 완료: {len(page_text)}자")

    return "\n\n".join(page_texts)


def generate_story_html(
    ocr_text: str,
    data_json: dict,
    target_date: date,
    sources_present: dict[str, bool] | None = None,
) -> str:
    """PDF OCR 원문(두 소스 합본) → HTML 스토리.

    Args:
        ocr_text: 두 PDF (KR/CN 클로징 + AI 데일리) OCR 결과를 섹션 마커로 합친 본문.
        data_json: 호환성용 (현재 사용하지 않음 — PDF 가 단일 ground truth).
        target_date: 장 기준일.
        sources_present: {"kr_cn": bool, "us_daily": bool}. None 이면 둘 다 있다고 간주.
    """
    from openai import OpenAI

    if sources_present is None:
        sources_present = {"kr_cn": True, "us_daily": True}

    client = OpenAI()

    # OCR 원문에서 종목명+수치 패턴을 미리 추출해 "필수 포함" 목록으로 만든다
    import re as _re
    # "(종목명)(+/-수치%)" 패턴 — 줄넘김 방지: \s 대신 [ \t]
    ticker_hits = _re.findall(
        r'([A-Za-z가-힣·][ \tA-Za-z가-힣·]{1,18})\s*\(([+\-±][\d.]+%)\)',
        ocr_text,
    )
    # 종목명 좌측 노이즈 제거: 마지막 한글·영문 단어만 남김
    # 접속사·조사·부사·업종 설명어로 시작하는 경우 종목명만 남김
    _NOISE_PREFIXES = {
        "다만", "또한", "와", "과", "및", "등", "이어", "더해", "앞둔", "한편", "특히",
        "업체", "기업", "제약사", "플랫폼", "회사", "업종", "미국", "글로벌",
    }
    def _clean_name(s: str) -> str:
        s = s.strip()
        parts = s.split()
        # 첫 단어가 노이즈면 제거
        while len(parts) > 1 and parts[0] in _NOISE_PREFIXES:
            parts = parts[1:]
        # 종목명은 보통 1~2단어
        return " ".join(parts[-2:]) if len(parts) > 2 else " ".join(parts)
    ticker_hits = [(_clean_name(n), c) for n, c in ticker_hits]
    # 중복 제거 (같은 종목명 유지)
    seen: set[str] = set()
    deduped = []
    for n, c in ticker_hits:
        if n not in seen:
            seen.add(n)
            deduped.append((n, c))
    ticker_hits = deduped
    # 섹션 제목(## 또는 줄 앞 한글 제목) 추출 — 보고서 헤더 제외
    _skip = {"AI 데일리 글로벌 마켓 브리핑", "Summary", "특징종목", "Compliance Notice"}
    section_hits = _re.findall(r'^(?:##\s*)?([가-힣A-Za-z][가-힣A-Za-z\s\-\'·]{4,40})$', ocr_text, _re.MULTILINE)
    section_hits = [s.strip() for s in section_hits if len(s.strip()) > 4 and s.strip() not in _skip][:8]

    must_include_lines = []
    if ticker_hits:
        must_include_lines.append(
            "▶ 아래 종목·수치는 PDF 본문에 명시된 그대로 빠짐없이 Story 에 인용하세요"
            " (수치 변경·반올림·치환·일반화 금지). 가능하면 모두 포함하되, 최소 12개 이상:"
        )
        for name, chg in ticker_hits[:30]:
            must_include_lines.append(f"  - {name.strip()} ({chg})")
    if section_hits:
        must_include_lines.append("▶ PDF 본문의 주요 섹션 (해당 내용을 반드시 Story 어딘가에 반영):")
        for s in section_hits:
            must_include_lines.append(f"  - {s}")
    must_include_block = "\n".join(must_include_lines) if must_include_lines else "(자동 추출 없음 — PDF 원문 전체 참고)"

    # PDF 본문 시점 메타: target_date = 장 기준일(=본문 시점)
    target_dow   = _DOW_KO[target_date.weekday()]
    publish_date = _next_biz(target_date)
    publish_dow  = _DOW_KO[publish_date.weekday()]
    kr_cn_ok = sources_present.get("kr_cn", False)
    us_ok    = sources_present.get("us_daily", False)
    src_lines = []
    if kr_cn_ok:
        src_lines.append(
            f"[PDF ①] 한국/중국 마켓 클로징 — 발간 {target_date} ({target_dow}) 오후 KST · "
            f"본문 = {target_date} ({target_dow}) 아시아(KR/CN) 마감"
        )
    else:
        src_lines.append("[PDF ①] 한국/중국 마켓 클로징 — ❌ 본 자료에 포함되지 않음 (아시아 세션은 한 줄 안내)")
    if us_ok:
        src_lines.append(
            f"[PDF ②] AI 데일리 글로벌 마켓 브리핑 — 발간 {publish_date} ({publish_dow}) 아침 KST · "
            f"본문 = {target_date} ({target_dow}) 미국 세션 마감"
        )
    else:
        src_lines.append("[PDF ②] AI 데일리 글로벌 마켓 브리핑 — ❌ 본 자료에 포함되지 않음 (미국 세션은 한 줄 안내)")
    pdf_meta = "\n".join(src_lines)

    user_msg = f"""미래에셋증권 두 PDF(아시아 = 한국/중국 마켓 클로징, 미국 = AI 데일리 글로벌 마켓 브리핑)
원본을 보존하는 1차 자료를 작성합니다. PDF 본문에 있는 정보만 인용하세요.
외부 데이터·웹 검색·일반론 추가 절대 금지. 세션별 출처를 절대 섞지 마세요
(아시아 블록은 PDF ①만, 미국 블록은 PDF ②만).
출력은 Story HTML 섹션 1~5 만, 다른 텍스트 없이.

[PDF 시점 메타 — 헤로 헤드라인에 반드시 반영]
{pdf_meta}

[필수 포함 종목·수치 (PDF 그대로 인용)]
{must_include_block}

--- PDF 본문 (1차 자료, 유일한 ground truth — 섹션 마커로 출처 구분) ---
{ocr_text}
"""

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STORY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=12000,
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
    <h1>🏛 미래에셋 모닝 브리핑 (PDF 1차 자료)</h1>
    <div class="date">{date_long}</div>
  </div>
  <div class="header-right">
    <span class="source-badge">PDF 1차 자료 보존</span>
  </div>
</div>
{story_html}
<div class="footer">미래에셋증권 'AI 데일리 글로벌 마켓 브리핑' PDF &mdash; OpenAI Vision OCR 추출 후 HTML 재구성. 글로벌 풀 사이클 종합은 메인 Market Story 탭을 참고하세요.</div>
<div class="ai-disclaimer">⚠️ 본 자료는 미래에셋증권 PDF 원본을 OCR 추출한 <strong>1차 자료 보존</strong>입니다. PDF 발간 시점(아침 KST) 기준으로 작성되어 메인 Market Story 와 시점·범위가 다릅니다. 수치는 PDF 본문 그대로이며, 투자 판단 시 PDF 원본을 확인하시기 바랍니다.</div>
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
    """독립 _ocr.html 파일 저장 — 기존 .html / _story.html 은 건드리지 않는다.

    date_long 은 'PDF 본문 시점(=target_date 미국 마감)' 과 'PDF 발간일(=익영업일 아침 KST)'
    둘 다 표기해 메인 Market Story 와의 시점 차이를 사용자가 즉시 인지하도록 한다.
    """
    target_dow   = _DOW_KO[target_date.weekday()]
    publish_date = _next_biz(target_date)
    publish_dow  = _DOW_KO[publish_date.weekday()]
    date_long = (
        f"PDF 발간 {publish_date.strftime('%Y-%m-%d')} ({publish_dow}) 아침 KST "
        f"&middot; 본문 시점 {target_date.strftime('%Y-%m-%d')} ({target_dow}) 미국 마감"
    )
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

def _download_pdf_to_tmp(pdf_info: dict) -> Path:
    log.info(f"PDF 다운로드: {pdf_info['pdf_url']}")
    resp = requests.get(pdf_info["pdf_url"], headers=HEADERS, timeout=60)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(resp.content)
        path = Path(tmp.name)
    log.info(f"다운로드 완료: {len(resp.content)//1024}KB")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None,
                        help="장 기준일 YYYY-MM-DD (기본: 직전 영업일)")
    parser.add_argument("--attach-id", default=None,
                        help="AI 데일리 PDF attachId 직접 지정 (US PDF 탐색 건너뜀)")
    parser.add_argument("--kr-cn-attach-id", default=None,
                        help="한국/중국 마켓 클로징 PDF attachId 직접 지정 (KR/CN PDF 탐색 건너뜀)")
    parser.add_argument("--skip-kr-cn", action="store_true",
                        help="KR/CN 클로징 PDF 사용 안 함 (legacy 단일소스 모드)")
    parser.add_argument("--dry-run", action="store_true",
                        help="파일 저장 없이 흐름만 확인")
    args = parser.parse_args()

    if args.date:
        target_date = date.fromisoformat(args.date)
    else:
        target_date = _prev_biz(date.today())

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

    # ── PDF 탐색: ① KR/CN 클로징 (아시아) ──
    kr_cn_info: dict | None = None
    if not args.skip_kr_cn:
        if args.kr_cn_attach_id:
            kr_cn_info = {
                "title": f"직접 지정 attachId={args.kr_cn_attach_id}",
                "pdf_url": f"{BASE_URL}/bbs/download/{args.kr_cn_attach_id}.pdf?attachmentId={args.kr_cn_attach_id}",
                "attach_id": args.kr_cn_attach_id,
                "date": str(target_date),
            }
            log.info(f"KR/CN attachId 직접 지정: {args.kr_cn_attach_id}")
        else:
            kr_cn_info = find_kr_cn_closing_pdf(target_date)

    # ── PDF 탐색: ② AI 데일리 (미국) ──
    if args.attach_id:
        us_info: dict | None = {
            "title": f"직접 지정 attachId={args.attach_id}",
            "pdf_url": f"{BASE_URL}/bbs/download/{args.attach_id}.pdf?attachmentId={args.attach_id}",
            "attach_id": args.attach_id,
            "date": str(target_date),
        }
        log.info(f"AI Daily attachId 직접 지정: {args.attach_id}")
    else:
        us_info = find_daily_briefing_pdf(target_date)

    if not kr_cn_info and not us_info:
        msg = (
            f"⚠️ *OCR Story 스킵* — {target_date}\n"
            f"미래에셋증권 한국/중국 클로징 + AI 데일리 PDF 둘 다 찾지 못했습니다.\n_ocr.html 미생성."
        )
        log.info("두 PDF 모두 없음 → _ocr.html 생성 건너뜀, 텔레그램 알림 발송")
        notify_telegram.send(msg)
        print(f"[SKIP] {target_date} PDF 미발견 (둘 다)")
        sys.exit(0)

    found_labels = []
    if kr_cn_info: found_labels.append("KR/CN 클로징")
    if us_info:    found_labels.append("AI 데일리")
    log.info(f"PDF 발견 소스: {', '.join(found_labels)}")

    # ── PDF 다운로드 + OCR (있는 것만) ──
    ocr_sections: list[str] = []
    sources_present = {"kr_cn": False, "us_daily": False}

    if kr_cn_info:
        kr_cn_path = _download_pdf_to_tmp(kr_cn_info)
        # S3 업로드는 미국 PDF 위주로 운영 (KR/CN 은 일단 로컬 OCR 만)
        log.info("OCR 시작 [KR/CN 클로징] (gpt-4o Vision)...")
        kr_cn_text = ocr_pdf(kr_cn_path)
        ocr_sections.append(
            f"=== [PDF ① 한국/중국 마켓 클로징] 아시아 세션 {target_date} 마감 ===\n{kr_cn_text}"
        )
        sources_present["kr_cn"] = True
        log.info(f"OCR 완료 [KR/CN]: {len(kr_cn_text)}자")

    if us_info:
        us_path = _download_pdf_to_tmp(us_info)
        s3_key = upload_pdf_to_s3(us_path, target_date)
        if s3_key:
            log.info(f"PDF S3 보관: s3://{S3_BUCKET}/{s3_key}")
            notify_telegram.send(
                f"📥 *브리핑 PDF 저장* — {target_date}\n"
                f"`s3://{S3_BUCKET}/{s3_key}`"
            )
        log.info("OCR 시작 [AI 데일리 미국] (gpt-4o Vision)...")
        us_text = ocr_pdf(us_path)
        ocr_sections.append(
            f"=== [PDF ② AI 데일리 글로벌 마켓 브리핑] 미국 세션 {target_date} 마감 ===\n{us_text}"
        )
        sources_present["us_daily"] = True
        log.info(f"OCR 완료 [AI Daily]: {len(us_text)}자")

    ocr_text = "\n\n".join(ocr_sections)
    ocr_cache = LOG_DIR / f"{target_date}_briefing_ocr.txt"
    ocr_cache.write_text(ocr_text, encoding="utf-8")
    log.info(f"OCR 합본: {len(ocr_text)}자 → {ocr_cache.name}")

    # ── Story HTML 생성 ──
    log.info("Story HTML 생성 중 (gpt-4o)...")
    story_html = generate_story_html(ocr_text, data_json, target_date, sources_present)
    log.info(f"Story 생성 완료: {len(story_html)}자")

    if args.dry_run:
        print("[DRY-RUN] Story HTML 미리보기 (앞 500자):")
        print(story_html[:500])
        sys.exit(0)

    # ── _ocr.html 저장 (기존 .html / _story.html 은 건드리지 않음) ──
    ocr_path = save_ocr_html(out_dir, target_date, story_html)
    log.info(f"=== 완료: {target_date} (소스: {', '.join(found_labels)}) ===")
    print(f"✅ OCR HTML 생성: {ocr_path}")
    print(f"   소스: {', '.join(found_labels)}")


if __name__ == "__main__":
    main()
