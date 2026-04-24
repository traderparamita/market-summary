---
allowed-tools: Read, Edit, Bash(.venv/bin/python:*), Bash(grep:*), Bash(ls:*)
argument-hint: "[YYYY-MM-DD] [period: daily|weekly|monthly]  (둘 다 생략 시 전 영업일·daily)"
description: "market_summary PM Story 작성: 기존 Market Story + _data.json 을 바탕으로 지역·자산군별 6개 섹션(한국·매크로·아시아및중국·미국·유럽·채권) 매니저 브리프 생성"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 일간 Story: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/2026-*/2026-*-*_story.html 2>/dev/null | head -3`
- 최근 PM 산출물: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/2026-*/2026-*-*_pm.html 2>/dev/null | head -3`

---

## Your task

**Arguments**: $ARGUMENTS (형식: `YYYY-MM-DD [daily|weekly|monthly]`, 둘 다 생략 시 전 영업일·daily)

Load and follow `.claude/skills/market-summary/SKILL.md` 의 **"PM Story 작성 절차"** 섹션.

---

## 사전 점검

1. **날짜 결정**: 인자 없으면 전 영업일·daily.
2. **미래 날짜 금지**: 대상 날짜 > 오늘이면 즉시 중단.
3. **원본 Story 존재 확인**: 해당 기간의 `_story.html` 이 없으면 중단하고 사용자에게 "먼저 Market Story 를 작성해야 한다" 안내.
4. **탭 구조 확인**: 대상 HTML 에 `<div id="tab-pm">` 블록이 없으면 `generate.py {date}` (또는 `generate_periodic.py`) 로 탭 구조 최신화 후 진행.

---

## Step 1 — 원본 Story + Data 읽기

경로 (period 별):
- daily: `output/summary/YYYY-MM/YYYY-MM-DD_story.html` + `YYYY-MM-DD_data.json`
- weekly: `output/summary/weekly/YYYY-WNN_story.html`
- monthly: `output/summary/monthly/YYYY-MM_story.html`

일간은 `_data.json` 의 각 자산 daily/weekly/monthly/ytd 수치 + holiday 확인 필수.

---

## Step 2 — 6개 섹션 구성

SKILL.md "PM Story 작성 절차" Step 2·3 의 규칙을 적용:

고정 순서 — 🇰🇷 **한국** → 🌐 **매크로** → 🌏 **아시아 및 중국** → 🇺🇸 **미국** → 🇪🇺 **유럽** → 💵 **채권**

각 섹션 3~5 불릿. 수치(종가·변동률·WTD/MTD/YTD·bp·FX 레벨) 적극 포함. 매수/매도 직접 권유 금지. 원본 Story 의 사실관계·시간순·세션 규칙 그대로.

---

## Step 3 — HTML 주입

**방법**: Edit 도구로 `tab-pm` 블록 직접 치환. `_inject_existing_story()` 외부 호출 금지.

1. 대상 HTML Read (`{date}.html`)
2. `<div id="tab-pm" class="tab-panel">` ~ `</div><!-- /tab-pm -->` 블록을 SKILL.md 의 PM 골격(`pm-hero` + `pm-grid` + 6개 `pm-section`) 으로 Edit
3. 같은 내용으로 `{date}_pm.html` 파일을 Edit (두 파일 동기화)

**placeholder 만 있는 경우**: 정상. 치환하면 됨.
**tab-pm 블록 부재**: `generate.py {date}` 재실행 → 탭 구조 최신화 → 다시 Step 3.

---

## Step 4 — 주입 검증

```bash
grep -c 'id="tab-pm"\|PM_STORY_PLACEHOLDER\|<!DOCTYPE' {html_path}
```
- `<!DOCTYPE html>` 1개
- `id="tab-pm"` 1개
- `PM_STORY_PLACEHOLDER` **0개**

수치 존재 확인 (CS 와 반대):
```bash
grep -oE '[0-9]+\.[0-9]+%|[0-9]{3,}\.[0-9]{2}' {pm_file} | wc -l
```
10 건 미만이면 수치 보강 필요.

섹션 완비 확인:
```bash
grep -oE '🇰🇷 한국|🌐 매크로|🌏 아시아 및 중국|🇺🇸 미국|🇪🇺 유럽|💵 채권' {pm_file} | sort -u | wc -l
```
**6** 이어야 함.

---

## 완료 보고

- 대상: `{html_path}` + `{pm_file}` 동기화 완료
- 6개 섹션 모두 포함 여부
- 수치 건수 (퍼센트 / 가격 소수점 기준)
- period 가 daily 면 Story / CS / PM 세 탭이 모두 살아있는지 한 줄 확인

---

## 중단 규칙

- 원본 `_story.html` 없음 → 즉시 중단, 사용자에게 Market Story 선행 요청
- `tab-pm` 블록 없음 → generate.py 재실행 후 재시도
- 주입 검증 실패(`PM_STORY_PLACEHOLDER` 잔존) → 즉시 사용자 보고
- 6개 섹션 중 누락 → 재작성
- 수치 10 건 미만 → 재작성 (PM 은 "숫자를 담는" 브리프)
