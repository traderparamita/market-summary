---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Bash(tail:*), Bash(find:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD]  (날짜 생략 시 전 영업일)"
description: "주간 테마 리서치: 주간 OCR 브리핑을 바탕으로 이번 주 핵심 테마 1~2개를 선정해 심층 분석 보고서 작성"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 이번 주 OCR 파일: !`find output/summary -name "*_ocr.html" | sort | tail -7`
- 최근 리서치 보고서: !`ls -t output/research/daily/**/*.html 2>/dev/null | head -3`
- 최근 증권 다이제스트: !`ls -t output/research/securities/*.html 2>/dev/null | head -2`

---

## Your task

매주 일요일, 그 주 OCR 브리핑(`*_ocr.html`)을 읽고 **이번 주 시장을 관통한 핵심 테마 1~2개**를 선정해 심층 리서치 보고서를 작성한다.

**Arguments**: $ARGUMENTS (형식: `YYYY-MM-DD`)

---

## 사전 점검

1. **날짜 결정**: 날짜 인자 없음 → 전 영업일 자동 선택.
2. **미래 날짜 금지**: 대상 날짜 > 오늘이면 즉시 중단.
3. **OCR 파일 확인**: 이번 주 `*_ocr.html`이 1개 이상 있어야 진행.

---

## Step 0 — Telegram 시작 알림

```bash
.venv/bin/python notify_telegram.py {date} --start --label "테마 리서치"
```

---

## Step 1 — 이번 주 OCR 브리핑 읽기

대상 날짜 기준 직전 5영업일의 `*_ocr.html` 파일을 모두 읽는다.

각 파일에서 추출:
- 주요 시장 이벤트·섹터 움직임·매크로 키워드
- **반복 등장하거나 가장 강하게 부각된 테마** 1~2개 선정

테마 선정 예시:
- AI 인프라 투자 사이클 가속
- 달러 약세·신흥국 자금 유입
- 방산·조선 리레이팅
- 중국 경기부양 기대 vs 실망

---

## Step 2 — 테마별 Tavily 심층 검색

선정된 테마마다 **3~5회** 검색. 최근 1~2주 뉴스 중심.

검색 전략:
1. 테마 핵심 드라이버 (정책·수요·공급 변화)
2. 대표 기업·ETF 동향
3. 반론·리스크 요인
4. 글로벌 vs 한국 시장 파급

---

## Step 3 — 보고서 파일 생성

경로: `output/research/daily/{YYYY-MM}/{date}.html`

### HTML 골격

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Market Research | {date}</title>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root { --accent:#F58220; --accent2:#043B72; --border:#e0e3ed; --muted:#7c8298; }
body { font-family:'Spoqa Han Sans Neo',sans-serif; background:#f4f5f9; color:#2d3148; max-width:900px; margin:0 auto; padding:32px 24px; line-height:1.7; }
.header { border-bottom:2px solid var(--border); padding-bottom:16px; margin-bottom:28px; }
.header h1 { font-size:22px; font-weight:700; color:#1a1d2e; }
.header .meta { font-size:12px; color:var(--muted); margin-top:4px; }
.theme-badge { display:inline-block; font-size:11px; font-weight:600; color:var(--accent); background:#fff5eb; border:1px solid #fde0c0; border-radius:12px; padding:3px 12px; margin-bottom:20px; }
.section { background:#fff; border:1px solid var(--border); border-radius:12px; padding:24px 28px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,0.04); }
.section h2 { font-size:18px; font-weight:700; color:var(--accent2); margin-bottom:14px; padding-bottom:8px; border-bottom:1px solid var(--border); }
.section h3 { font-size:15px; font-weight:600; color:#1a1d2e; margin:14px 0 8px; }
.section p { font-size:14px; margin-bottom:10px; }
.risk-box { background:#fff5f5; border:1px solid #fecaca; border-radius:8px; padding:14px 18px; margin-top:14px; font-size:13px; }
.footer { font-size:11px; color:var(--muted); border-top:1px solid var(--border); padding-top:12px; margin-top:24px; }
</style>
</head>
<body>

<div class="header">
  <h1>Weekly Theme Research</h1>
  <div class="meta">{date} · 테마: {테마명}</div>
</div>

<!-- STORY_PLACEHOLDER -->

<div class="footer">출처: 미래에셋증권 OCR 브리핑 + Tavily 뉴스 검색 · {date}</div>
</body>
</html>
```

---

## Step 4 — Story 작성 및 주입

`STORY_PLACEHOLDER`를 아래 구조의 HTML로 교체한다.

```html
<span class="theme-badge">테마: {테마명}</span>

<!-- 테마 1 -->
<div class="section">
  <h2>🎯 {테마1 제목}</h2>

  <h3>배경 — 왜 지금 이 테마인가</h3>
  <p>{이번 주 OCR에서 포착된 계기 + 매크로 맥락 2~3 문단}</p>

  <h3>핵심 드라이버</h3>
  <p>{정책·수요·기술 등 구체적 드라이버 2~3 문단}</p>

  <h3>대표 기업·ETF 동향</h3>
  <p>{이번 주 실제 움직임 + 실적·뉴스 2~3 문단}</p>

  <h3>한국 시장 파급</h3>
  <p>{국내 관련 섹터·기업 동향 1~2 문단}</p>

  <div class="risk-box">
    ⚠ 리스크: {이 테마의 반전 시나리오 1~2 문장}
  </div>
</div>

<!-- 테마 2 (있는 경우) -->
<div class="section">
  <h2>🎯 {테마2 제목}</h2>
  ...
</div>

<!-- 종합 포인트 -->
<div class="section">
  <h2>💡 이번 주 핵심 포인트</h2>
  <p>① <strong>{테마1 한 줄 요약}</strong> — {초보자 설명 1문장}</p>
  <p>② <strong>{테마2 한 줄 요약 (있는 경우)}</strong> — {설명}</p>
  <p>③ <strong>다음 주 주목 변수</strong> — {캘린더 이벤트·지표 1~2개}</p>
</div>
```

---

## Step 5 — `_story.html` 저장

```bash
cp output/research/daily/{YYYY-MM}/{date}.html \
   output/research/daily/{YYYY-MM}/{date}_story.html
```

---

## Step 6 — Git commit + push

```bash
git add output/research/ && \
git commit -m "feat: {date} 테마 리서치 — {테마명}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" && \
git push origin main
```

---

## Step 7 — Telegram 완료 알림

```bash
.venv/bin/python notify_telegram.py {date} --sc-complete \
  --focus "테마 리서치 — {테마명}"
```

---

## 완료 보고

- 생성된 HTML 경로
- 선정 테마 (1~2개) + OCR에서 포착된 근거 키워드
- Tavily 검색 건수 + 주요 뉴스 제목 2~3개

---

## 중단 규칙

- OCR 파일이 0개: 사용자에게 보고 후 중단
- Step 6 git 실패: 즉시 중단하고 사용자에게 상태 보고