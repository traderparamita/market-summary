---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD]  (생략 시 전 영업일 — Part A와 동일 날짜)"
description: "market_summary Part B: CS·PM·Stocks Story → 주간/월간 Story → 수치 검증 → git push. /market-full(Part A) 완료 후 실행"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 대상 날짜 일간 파일: !`ls output/summary/2026-*/2026-*-*_story.html 2>/dev/null | sort | tail -3`
- 최근 주간 보고서: !`ls -t output/summary/weekly/*.html 2>/dev/null | head -3`
- 최근 월간 보고서: !`ls -t output/summary/monthly/*.html 2>/dev/null | head -3`

## Your task

`/market-full` (Part A) 완료 후 이어서 실행하는 **Part B 워크플로우**.

**대상 날짜**: $ARGUMENTS (비어있으면 전 영업일 — Part A와 반드시 동일)

Part A가 생성한 `YYYY-MM-DD_story.html` + `YYYY-MM-DD_data.json`을 바탕으로  
CS·PM·Stocks Story → 주간/월간 Story(해당일 기준) → 수치 검증 → git push를 순차 실행한다.

---

### 사전 점검

**캘린더 검증 (필수 — 요일 추측 금지)**:
```bash
.venv/bin/python scripts/calendar_check.py $ARGUMENTS
```
- 출력된 요일·영업일·공휴일 정보를 이후 모든 Step에서 참조한다
- "마지막 영업일" 판단(주간/월간 Story 생성 여부)도 이 출력 기준
- `YYYY-MM-DD_story.html`가 없으면 Part A가 미완료 — 즉시 중단하고 사용자에게 보고

---

## Step 3-B: 일간 CS Story 작성

`market-summary` 스킬 `references/cs.md` 규칙으로 CS 버전을 작성한다.

핵심:
1. `output/summary/YYYY-MM/YYYY-MM-DD_story.html` Read
2. 수치(퍼센트·가격·거래량·시가총액)를 맥락 어휘로 치환. 종목·이벤트·날짜는 유지.
3. 의사결정 권유 톤 금지 (설명·관찰만).
4. `YYYY-MM-DD.html` 의 `<div id="tab-cs">` ~ `</div><!-- /tab-cs -->` 블록을 Edit + `YYYY-MM-DD_cs.html` 동기화.

실패 시 경고 후 Step 3-C 로 계속 진행 (트랙 독립).

**완료 보고**: `✅ [Step 3-B] 일간 CS Story 작성 완료`

---

## Step 3-C: 일간 PM Story 작성

`market-summary` 스킬 `references/pm.md` 규칙으로 PM 버전을 작성한다. (Step 3-B와 독립)

핵심:
1. `YYYY-MM-DD_story.html` + `YYYY-MM-DD_data.json` Read
2. 6개 고정 섹션(🇰🇷 한국 · 🌐 매크로 · 🌏 아시아 및 중국 · 🇺🇸 미국 · 🇪🇺 유럽 · 💵 채권) 으로 재편집
3. 각 섹션 3~5 불릿, 종가·변동률·WTD/MTD/YTD·bp·FX 레벨 등 수치 적극 포함
4. 원본 Story의 사실관계·시간순·세션 규칙 그대로 유지. 매수/매도 직접 권유 금지.
5. `YYYY-MM-DD.html` 의 `<div id="tab-pm">` ~ `</div><!-- /tab-pm -->` 블록을 Edit + `YYYY-MM-DD_pm.html` 동기화.

실패 시 경고 후 Step 3-D 로 계속 진행 (트랙 독립).

**완료 보고**: `✅ [Step 3-C] 일간 PM Story 작성 완료`

---

## Step 3-D: 일간 Stocks Story 작성

`market-summary` 스킬 `references/stocks.md` 규칙으로 종목 단위 해설을 작성한다. (Step 3-B/3-C와 독립)

`tab-stocks` 탭은 두 영역으로 구성:
- **자동**: `generate.py` 가 한국 Top 20 + 미국 Top 20 + 아시아 Top 20 표 생성
- **수동**: Claude 가 `<!-- STOCKS_STORY_PLACEHOLDER -->` 위치에 Hero 1단락 + 4~5 단락 종목 해설 주입

핵심:
1. `YYYY-MM-DD_data.json` 의 stocks 섹션에서 폭등 Top 10 + 폭락 Top 10 식별
2. 총괄 1단락 → 🇯🇵 일본 → 🇨🇳 중국 → 🇰🇷🇹🇼 한국·대만 → (선택) 🇮🇳 인도 / 🇻🇳 베트남
3. 각 단락에 인과 채널 1개 명시 (실적·정책·매크로·테마·이벤트)
4. `YYYY-MM-DD.html` 의 `<div id="tab-stocks">` 블록 Edit + `YYYY-MM-DD_stocks.html` 동기화

실패 시 경고 후 Step 5 로 계속 진행 (트랙 독립).

**완료 보고**: `✅ [Step 3-D] 일간 Stocks Story 작성 완료`

---

## Step 5: 주간 Market Story (마지막 영업일만)

대상 날짜가 해당 주의 **마지막 영업일**(보통 금요일)인 경우에만 작성. 중간 영업일이면 **건너뛴다**.

- `market-summary` 스킬 `references/weekly-monthly.md` 의 주간 Story 절차 따름
- 해당 주의 일간 `_story.html`들을 모두 읽어 종합
- `output/summary/weekly/YYYY-WNN.html`에 주입
- **Sources 주입 (필수)**: 그 주의 일간 sources + 주간 추가 검색 출처 최소 10건. **빈 sources는 Step 7.7 검증에서 자동 실패.**

**완료 보고**:
- 마지막 영업일: `✅ [Step 5] 주간 Market Story 작성 완료 (Sources: N건)`
- 중간 영업일: `⊘ [Step 5] 스킵`

## Step 5-B: 주간 CS Story (마지막 영업일만)

Step 5 완료 직후. `references/cs.md` 의 주간 CS 적용 가이드 규칙.

핵심:
1. `output/summary/weekly/YYYY-WNN_story.html` Read
2. 5 영업일을 한 흐름으로 압축 + 수치 제거
3. `weekly/YYYY-WNN.html` 의 `<div id="tab-cs">` 블록 Edit + `_cs.html` sibling 동기화

실패 시 경고 후 Step 5-C 로 계속.

## Step 5-C: 주간 PM Story + Outlook (마지막 영업일만)

Step 5 완료 후 (Step 5-B와 독립). `references/pm.md` + `references/pm-outlook.md` 규칙.

핵심:
1. `YYYY-WNN_story.html` + 일간 5개 `_data.json` Read
2. 회고 PM Story 6 섹션 (각 4~6 불릿, WTD 수익률 + 주중 최대 상승·하락일 + 핵심 이벤트)
3. 회고 직후 Outlook 블록 (시나리오 3카드 · 6섹션 Watch & Trigger · 통합 리스크 · 포지셔닝 시사점)
4. `weekly/YYYY-WNN.html` 의 `<div id="tab-pm">` 블록 Edit + `_pm.html` sibling 동기화

실패 시 경고 후 Step 5.5 로 계속.

## Step 5.5: 매크로 데이터 수집 (마지막 영업일만)

```bash
.venv/bin/python -m collectors.macro
```

실패 시 경고 후 계속.

## Step 5.6: Macro & Events 탭 작성 (마지막 영업일만)

`macro-events` 스킬 절차 따름.

1. `history/macro_indicators.csv`에서 이번 주 날짜 범위 필터링
2. Tavily MCP(`mcp__tavily__search`)로 이번 주 주요 이벤트 수집·해설 + 다음 주 캘린더
3. `output/summary/weekly/YYYY-WNN.html`의 `tab-macro` 블록에 주입 + `YYYY-WNN_macro.html` 저장
4. **금요일 일간 보고서 backfill**:

```bash
.venv/bin/python -c "from generate import backfill_macro_to_daily; backfill_macro_to_daily('output/summary/weekly/YYYY-WNN_macro.html')"
```

---

## Step 7: 월간 Market Story (마지막 영업일만)

대상 날짜가 해당 월의 **마지막 영업일**인 경우에만 작성. 아니면 **건너뛴다**.

- `market-summary` 스킬 `references/weekly-monthly.md` 의 월간 Story 절차 따름
- `output/summary/monthly/YYYY-MM.html`에 주입
- **Sources 주입 (필수)**: 월 단위 핵심 출처 최소 15건.

**완료 보고**:
- 마지막 영업일: `✅ [Step 7] 월간 Market Story 작성 완료 (Sources: N건)`
- 중간 영업일: `⊘ [Step 7] 스킵`

## Step 7-B: 월간 CS Story (마지막 영업일만)

Step 7 완료 직후. `references/cs.md` 월간 CS 적용 가이드 규칙.

1. `output/summary/monthly/YYYY-MM_story.html` Read
2. 한 달 흐름 1~2 문단 헤로 + 5~7 cs-section으로 압축. 수치 제거.
3. `monthly/YYYY-MM.html` 의 `<div id="tab-cs">` 블록 Edit + `_cs.html` sibling 동기화

실패 시 경고 후 Step 7-C 로 계속.

## Step 7-C: 월간 PM Story + Outlook (마지막 영업일만)

Step 7 완료 후 (Step 7-B와 독립). `references/pm.md` + `references/pm-outlook.md` 규칙.

1. `YYYY-MM_story.html` + 일간 `_data.json` (해당 월) Read
2. 회고 PM Story 6 섹션 (각 5~7 불릿, 월말 종가 + MTD + YTD + 월간 최대 상승·하락일)
3. Outlook 블록 (시나리오 3카드 · 6섹션 Watch & Trigger · 통합 리스크 4개 · 포지셔닝 시사점)
4. `monthly/YYYY-MM.html` 의 `<div id="tab-pm">` 블록 Edit + `_pm.html` sibling 동기화

실패 시 경고 후 Step 7.5 로 계속.

## Step 7.5: 월간 매크로 데이터 수집 (마지막 영업일만)

```bash
.venv/bin/python -m collectors.macro
```

## Step 7.6: 월간 Macro & Events 탭 작성 (마지막 영업일만)

`macro-events` 스킬 절차. `output/summary/monthly/YYYY-MM.html`의 `tab-macro` 블록에 주입 + `YYYY-MM_macro.html` 저장.

---

## Step 7.7: Market Summary 수치 자동 검증

Part B에서 작성·갱신된 일간/주간/월간 보고서를 `history/market_data.csv` ground truth와 대조한다.

```bash
.venv/bin/python scripts/verify_report_numbers.py --auto --fix --telegram
```

**합격 기준**: `[verify] ✓ 위반 없음` 출력. 위반이 남아 있으면 **Step 8 진행 금지**.

---

## Step 8: Git Commit + Push

`output/summary/`, `output/index.html`, `history/market_data.csv`를 스테이징 후 커밋·푸시.  
**Step 7.7 통과 후에만 진행**.

- 커밋 메시지: `market: YYYY-MM-DD daily report` (주간/월간 포함 시 범위 표기)
- `git push origin main`

**완료 보고**:
- 성공: `✅ [Step 8] git push 완료 (커밋: abcd1ef)`
- 실패: `❌ [Step 8] git push 실패: <reason> — 즉시 중단`

---

## Step 9: Telegram 완료 알림

Step 8 성공 후 즉시 전송. 실패해도 계속.

```bash
.venv/bin/python notify_telegram.py $ARGUMENTS \
  [--weekly]   # 해당 주 마지막 영업일이면 추가 \
  [--monthly]  # 해당 월 마지막 영업일이면 추가
```

---

## 완료 보고 (Part B)

모든 단계 완료 후 Step별 실행 결과를 표 형식으로 보고:

```
Step 3-B:  일간 CS Story     — ✅ 성공 / ⚠ 실패(계속)
Step 3-C:  일간 PM Story     — ✅ 성공 / ⚠ 실패(계속)
Step 3-D:  일간 Stocks Story — ✅ 성공 / ⚠ 실패(계속)
Step 5:    주간 Story        — ✅ 성공 (Sources: N건) / ⏭ 스킵
Step 5-B:  주간 CS Story     — ✅ 성공 / ⏭ 스킵 / ⚠ 실패(계속)
Step 5-C:  주간 PM Story     — ✅ 성공 / ⏭ 스킵 / ⚠ 실패(계속)
Step 5.5:  매크로 수집       — ✅ 성공 / ⏭ 스킵 / ⚠ 실패(계속)
Step 5.6:  Macro 탭          — ✅ 성공 / ⏭ 스킵
Step 7:    월간 Story        — ✅ 성공 (Sources: N건) / ⏭ 스킵
Step 7-B:  월간 CS Story     — ✅ 성공 / ⏭ 스킵 / ⚠ 실패(계속)
Step 7-C:  월간 PM Story     — ✅ 성공 / ⏭ 스킵 / ⚠ 실패(계속)
Step 7.5:  월간 매크로       — ✅ 성공 / ⏭ 스킵
Step 7.6:  월간 Macro 탭     — ✅ 성공 / ⏭ 스킵
Step 7.7:  수치 검증         — ✅ 위반 없음 / ❌ 위반 N건(Step 8 차단)
Step 8:    Git Push          — ✅ 커밋해시 / ❌ 실패
Step 9:    Telegram          — ✅ 전송 / ⚠ 실패(계속)
```

---

## 중단 규칙

- Part A 미완료 (`_story.html` 없음): 즉시 중단하고 사용자에게 보고
- Step 7.7 위반 잔존: Step 8 진행 금지
- Step 8 git 실패: 즉시 중단하고 사용자에게 상태 보고
- Telegram 실패: 경고 로그만 출력하고 계속