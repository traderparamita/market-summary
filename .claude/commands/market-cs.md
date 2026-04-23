---
allowed-tools: Read, Edit, Bash(.venv/bin/python:*), Bash(grep:*), Bash(ls:*)
argument-hint: "[YYYY-MM-DD] [period: daily|weekly|monthly]  (둘 다 생략 시 전 영업일·daily)"
description: "market_summary CS Story 작성: 기존 Story에서 수치를 최대한 제거하고 맥락 중심으로 재작성 (Story 탭과 병행 운영되는 CS 탭)"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 일간 Story: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/2026-*/2026-*-*_story.html 2>/dev/null | head -3`
- 최근 CS 산출물: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/2026-*/2026-*-*_cs.html 2>/dev/null | head -3`

---

## Your task

**Arguments**: $ARGUMENTS (형식: `YYYY-MM-DD [daily|weekly|monthly]`, 둘 다 생략 시 전 영업일·daily)

Load and follow `.claude/skills/market-summary/SKILL.md` 의 **"CS Story 작성 절차"** 섹션.

---

## 사전 점검

1. **날짜 결정**: 인자 없으면 전 영업일·daily.
2. **미래 날짜 금지**: 대상 날짜 > 오늘이면 즉시 중단.
3. **원본 Story 존재 확인**: 해당 기간의 `_story.html` 이 없으면 중단하고 사용자에게 "먼저 일반 Story 를 작성해야 한다" 안내.

---

## Step 1 — 원본 Story Read

경로 (period 별):
- daily: `output/summary/YYYY-MM/YYYY-MM-DD_story.html`
- weekly: `output/summary/weekly/YYYY-WNN_story.html`
- monthly: `output/summary/monthly/YYYY-MM_story.html`

파일을 Read 하여 구조(h2/h3/br)·사실관계·시간순 인과를 파악한다.

---

## Step 2 — 수치 제거 + 맥락 재작성

SKILL.md "CS Story 작성 절차" Step 2·3 의 규칙을 적용:

**제거**: 퍼센트·가격·지수·거래량·시가총액·섹터 퍼센트 나열·KPI 블록 내부 숫자  
**유지**: 종목명·지수명·ETF·이벤트·정책·날짜·요일·심리 앵커(정수 이정표만)  
**톤**: 고객에게 설명하는 관찰·서술 톤. 의사결정 권유 금지.

HTML 골격은 **cs-hero + cs-section 블록 조합** 을 사용한다. Market Story 탭의 `.story-hero` / `.story-text` 와 시각적으로 구분되는 오렌지 계열 박스. CSS 는 `<style>` 인라인으로 tab-cs 블록 안에 포함시킨다 (HTML 헤드 CSS 변경 없이 과거 보고서에도 포터블 적용 가능).

```html
<style>
  .cs-hero{background:linear-gradient(135deg,#fff5eb,#fde9d3);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:12px;padding:28px 32px;margin-bottom:24px}
  .cs-hero h2{font-size:13px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}
  .cs-hero .cs-subtitle{font-size:12px;color:var(--muted);margin-bottom:16px}
  .cs-text{font-size:16px;color:#2d3148;line-height:1.9}
  .cs-text p{margin-bottom:14px}
  .cs-text p:last-child{margin-bottom:0}
  .cs-section{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px 28px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
  .cs-section h3{font-size:17px;font-weight:600;color:#1a1d2e;margin-bottom:10px}
  .cs-section p{font-size:15px;color:#2d3148;line-height:1.85;margin-bottom:10px}
  .cs-section p:last-child{margin-bottom:0}
  .cs-footer{font-size:12px;color:var(--muted);border-top:1px solid var(--border);padding-top:12px;margin-top:8px}
</style>

<div class="cs-hero">
  <h2>CS Story — 고객 설명용</h2>
  <div class="cs-subtitle">{date} ({요일}) · 수치 대신 맥락·흐름 중심</div>
  <div class="cs-text">
    <p>{아시아 세션 흐름 — 수치 없이}</p>
    <p>{유럽 세션 흐름}</p>
    <p>{미국 세션 흐름}</p>
  </div>
</div>

<div class="cs-section">
  <h3>{주요 테마 1 — 국기 이모지 + 제목}</h3>
  <p>{맥락·배경·의미 — 숫자 대신 방향·강도 어휘}</p>
</div>

<div class="cs-section">
  <h3>{주요 테마 2}</h3>
  <p>{...}</p>
</div>

<div class="cs-section">
  <h3>📅 이번 주·이번 달 관점</h3>
  <p>{WTD/MTD 맥락 서술 — "주간 기준으로도 상승 흐름이 이어지고 있습니다"}</p>
  <p class="cs-footer">CS Story 는 Market Story 를 수치 대신 맥락·흐름 중심으로 재구성한 고객 설명용 버전입니다. 구체적 수치는 Market Story / Data Dashboard 탭을 참고하세요.</p>
</div>
```

- `var(--accent)` / `var(--border)` / `var(--card)` / `var(--muted)` 는 Market Summary HTML 의 `:root` 에서 이미 선언돼 있어 그대로 참조 가능.
- h2·h3 구조는 생략해도 되지만, Hero 박스 1개 + Section 박스 N개 조합이 기본.

원본 Story 와 사실관계·시간순·세션 간 규칙은 동일하게 유지. 의심스러운 사실(예: 미래 참조)이 원본에 있으면 CS 에서 임의로 바로잡지 말고 사용자에게 보고.

---

## Step 3 — HTML 주입

**방법**: Edit 도구로 `tab-cs` 블록 직접 치환 (Skill 의 "Step 4: HTML 주입" 규칙 준수. `_inject_existing_story()` 외부 호출 금지).

1. 대상 HTML Read (`{date}.html`)
2. `<div id="tab-cs" class="tab-panel">` ~ `</div><!-- /tab-cs -->` 사이 블록을 새 CS 본문으로 Edit
3. 같은 내용으로 `{date}_cs.html` 파일을 Edit (두 파일 동기화)

**placeholder 가 있는 경우** (`<!-- CS_STORY_PLACEHOLDER -->` 만 있는 상태): 정상. 이 블록을 CS 본문으로 치환하면 된다.

**tab-cs 블록이 아예 없는 경우** (이전 버전 템플릿으로 생성된 HTML): `.venv/bin/python generate.py {date}` 로 먼저 재생성 → 탭 구조 최신화 → 다시 Step 3 로 돌아온다.

---

## Step 4 — 주입 검증

```bash
grep -c 'id="tab-cs"\|CS_STORY_PLACEHOLDER\|<!DOCTYPE' {html_path}
```

- `<!DOCTYPE html>` 1개
- `id="tab-cs"` 1개
- `CS_STORY_PLACEHOLDER` **0개** (치환 완료)

주입 후 brave check:
```bash
grep -oE '[0-9]+\.[0-9]+%|[0-9]{3,},[0-9]{3}' {cs_file} | head -10
```
퍼센트·가격 숫자가 과도하게 남아있으면 재작성 필요.

---

## 완료 보고

- 대상: `{html_path}` + `{cs_file}` 동기화 완료
- 원본 Story 대비 제거한 수치 종류 (퍼센트, 가격, 거래량 …)
- 유지한 심리 앵커 1~2개 (있다면)
- period 가 daily 면 Story 탭과 CS 탭 모두 살아있는지 한 줄 확인

---

## 중단 규칙

- 원본 `_story.html` 없음 → 즉시 중단, 사용자에게 일반 Story 선행 요청
- `tab-cs` 블록 없음 → generate.py 재실행 후 재시도
- 주입 검증 실패(`CS_STORY_PLACEHOLDER` 잔존) → 즉시 사용자 보고
- 수치 제거 불충분 (grep 결과 5건 이상 남음) → 재작성
