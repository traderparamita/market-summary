---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD]  (생략 시 전 영업일)"
description: "market_summary 전체 워크플로우: 데이터 수집 → Dashboard → Story(일/주/월) → 배포"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 일간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/2026-*/2026-*-*.html 2>/dev/null | head -3`
- 최근 주간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/weekly/*.html 2>/dev/null | head -3`
- 최근 월간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/monthly/*.html 2>/dev/null | head -3`

## Your task

`market_summary` 프로젝트의 **일일 영업일 08:00 KST 전체 워크플로우**를 순차 실행한다. CLAUDE.md 8단계를 모두 수행.

**대상 날짜**: $ARGUMENTS (비어있으면 전 영업일)

### 사전 점검

1. 대상 날짜가 **오늘보다 미래가 아닌지 확인**. 미래면 즉시 중단하고 사용자에게 보고.
2. 대상 날짜가 주말이거나 한국·미국 공휴일이면 사용자에게 "해당일 보고서를 생성할지" 확인.

### Step 1~2: 데이터 수집 + Data Dashboard

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python generate.py $ARGUMENTS
```

- 이 명령 하나로 일간 데이터 수집 + 일간 HTML + 주간·월간 HTML 자동 갱신까지 수행된다.
- 실패 시 재시도 또는 사용자에게 보고 후 중단.

### Step 3: 일간 Market Story 작성

`market-summary` **스킬**의 "일간 Story 작성 절차"를 따른다.

핵심:
1. `output/summary/YYYY-MM/YYYY-MM-DD_data.json` Read → 수치·holiday 확인
2. 시간순 웹 검색 (아시아 → 유럽 → 미국)
3. Story 작성 (훅이 forward-looking·세션 간 참조 등 자동 검증)
4. `output/summary/YYYY-MM/YYYY-MM-DD.html`의 Story 탭에 주입 + `_story.html` 저장

### Step 4: 주간 Data Dashboard

Step 1~2에서 이미 `update_current_periodic()`이 자동 실행되었으므로 **별도 실행 불필요**. `output/summary/weekly/` 해당 주 파일이 존재하는지만 확인.

### Step 5: 주간 Market Story

대상 날짜가 해당 주의 **마지막 영업일**(보통 금요일)인 경우에만 주간 Story를 작성한다. 중간 영업일이면 이 단계를 **건너뛴다**.

- `market-summary` 스킬의 "주간 Story 작성 절차" 따름
- 해당 주의 일간 `_story.html`들을 모두 읽어 종합
- `output/summary/weekly/YYYY-WNN.html`에 주입

### Step 5.5: 매크로 데이터 수집 (마지막 영업일만)

대상 날짜가 해당 주의 **마지막 영업일**(보통 금요일)인 경우에만 실행:

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python -m portfolio.collect_macro
```

실패 시 경고 후 계속 진행 (보고서 생성은 기존 CSV로 진행).

### Step 5.6: Macro & Events 탭 작성 (마지막 영업일만)

대상 날짜가 해당 주의 **마지막 영업일**인 경우에만 `macro-events` **스킬**의 작성 절차를 따른다.

핵심:
1. `history/macro_indicators.csv` 에서 이번 주 날짜 범위 필터링 (bash grep)
2. Tavily MCP(`mcp__tavily__search`)로 이번 주 주요 이벤트 수집·해설
3. Tavily MCP로 다음 주 이벤트 캘린더 수집
4. `output/summary/weekly/YYYY-WNN.html`의 `tab-macro` 블록에 주입
5. `YYYY-WNN_macro.html` 저장 확인

### Step 6: 월간 Data Dashboard

Step 1~2에서 자동 갱신됨. 별도 실행 불필요.

### Step 7: 월간 Market Story

대상 날짜가 해당 월의 **마지막 영업일**인 경우에만 작성. 아니면 **건너뛴다**.

- `market-summary` 스킬의 "월간 Story 작성 절차" 따름
- `output/summary/monthly/YYYY-MM.html`에 주입

### Step 8: Git Commit + Push

변경된 모든 보고서를 커밋·푸시한다. `/market-deploy` 커맨드와 동일한 규칙 적용:

- `output/` 및 `history/market_data.csv`만 스테이징 (`.gitignore` 준수)
- 커밋 메시지: `market: YYYY-MM-DD daily report` (주간/월간도 같이 포함되면 범위 표기)
- `git push origin main`

### 완료 보고

모든 단계 완료 후 한 번에 요약:

- 생성·갱신된 보고서 목록 (일간/주간/월간)
- 스킵한 단계 (있다면 이유 명시)
- 커밋 해시와 푸시 결과
- 다음 영업일 실행 권장 시각

### 중단 규칙

- Step 1~2 실패: 즉시 중단
- Step 3/5/7 훅 block: 사유 읽고 수정 재시도 (2회까지), 계속 실패 시 사용자에게 보고
- Step 8 git 실패: 중단하고 사용자에게 상태 보고