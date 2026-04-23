---
allowed-tools: Read, Bash(ls:*), Bash(grep:*), Bash(head:*), Bash(tail:*), Bash(awk:*), Bash(sort:*), Bash(cut:*), Bash(date:*), Bash(.venv/bin/python:*), Agent
argument-hint: "[YYYY-MM-DD] [period: daily|weekly|monthly]  (둘 다 생략 시 전 영업일·daily)"
description: "market_summary Story 사후 점검: _data.json·CSV 와 본문 수치·종목·날짜 교차 대조. code-reviewer 서브에이전트로 체크리스트 리포트 생성 (수정은 승인 후 별도 진행)"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 일간 Story: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/2026-*/2026-*-*_story.html 2>/dev/null | head -3`
- CSV 최종일: !`tail -3 /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/history/market_data.csv 2>/dev/null | cut -d',' -f1 | sort -u | tail -1`

---

## Your task

**Arguments**: $ARGUMENTS — `YYYY-MM-DD [daily|weekly|monthly]`, 둘 다 생략 시 **전 영업일·daily**.

market_summary Story 가 `_data.json`·`history/market_data.csv` 실제 데이터와 일치하는지 사후 점검한다. **리뷰만 수행하고 파일 수정은 하지 않는다.** 발견된 이슈는 체크리스트 + 제안 diff 형태로 사용자에게 제시하고, 수정 여부는 사용자가 결정.

---

## 사전 점검

1. 날짜·period 결정. 인자 없으면 전 영업일·daily.
2. 대상 파일 경로 식별:
   - daily: `output/summary/YYYY-MM/YYYY-MM-DD.html` + `YYYY-MM-DD_story.html` + `YYYY-MM-DD_data.json`
   - weekly: `output/summary/weekly/YYYY-WNN.html` + `YYYY-WNN_story.html`
   - monthly: `output/summary/monthly/YYYY-MM.html` + `YYYY-MM_story.html`
3. Story 파일이 없으면 즉시 중단하고 사용자에게 보고.

---

## Step 1 — 원천 데이터 수집

bash 로 다음을 추출해 둔다 (에이전트 컨텍스트에 전달):

```bash
# 1) data.json 주요 필드
DATE={date}
DATA_JSON=output/summary/{year-month}/{date}_data.json

# 2) 해당일 CSV 전체 행
grep "^{date}" history/market_data.csv

# 3) 주간/월간 비교용 — 해당 범위 CSV 슬라이스
# (weekly) 해당 주 월~금 영업일 필터
# (monthly) 해당 월 전체 영업일 필터
```

---

## Step 2 — code-reviewer 서브에이전트 호출

`Agent` 도구에 `subagent_type: code-reviewer` 로 위임. 프롬프트 구성:

```
작업: market_summary {period} Story 사후 점검 ({date}).

읽을 파일:
- {story_path}
- {data_json_path}
- 필요 시 history/market_data.csv (grep "^{date}" 로 추출한 범위)
- 필요 시 해당 기간 다른 _story.html (주간·월간일 때)

점검 항목:
1. [수치 일치] Story 본문에 등장하는 모든 퍼센트(+1.23%)·가격(6,417.93·1,224,000원)·지수값이 data.json 또는 CSV 와 일치하는가? 불일치면 해당 문장과 실제 값을 모두 제시.
2. [종목·지수명] 본문에 언급된 모든 종목/지수/ETF 가 실제 수집된 티커 데이터에 존재하는가? 예: data.json 에 "Samsung" 만 있는데 본문에 "삼성전기" 가 +5%로 나오면 플래그.
3. [날짜·요일 정확성] Story 헤더·본문의 날짜와 요일이 실제 달력과 일치하는가? (예: 4/22 → 수요일)
4. [휴일 표기] data.json 의 holiday/holiday_note 와 본문의 휴장 서술이 일치하는가?
5. [고점·저점 검증] "사상 최고", "YTD 최고", "52주 고점", "연내 신고점" 표현 사용 시, CSV 에서 해당 지표의 해당 기간 실제 1위 날짜가 보고서 날짜인지 확인.
6. [세션 시간순] 아시아 서술에 같은 날 유럽/미국 이벤트가 원인으로 섞이지 않았는가? 유럽 서술에 유럽 마감 이후 미국 이벤트는? (market-summary SKILL.md 의 세션 마감 시각 표 참조)
7. [WTD/MTD 일관성] 일간이면 WTD/MTD 수치가 data.json 의 `weekly`/`monthly` 필드와 일치하는가?
8. [허구 수치 탐지] CSV·data.json 에 없는데 본문에만 등장하는 정량 수치 (예: 거래량 수치, 시가총액 수치, 외국인 순매수 금액 등)는 출처 불명이므로 ⚠ 표기.

출력 형식 — Markdown:

## Story 점검 리포트: {date} ({period})

### ✅ 통과 항목
- (통과 항목 나열)

### ⚠ 주의 항목
- 파일:line — 현재 문장 | 실제 값 | 제안 수정

### ❌ 수정 필수 항목
- 파일:line — 현재 문장 | 실제 값 | 제안 diff (이전/이후)

### 📊 요약
- 검증 수치 N개 중 M개 불일치 / K개 허구 의심
- 세션 시간순 규칙 위반 N건
- 고점 표현 미검증 N건

수정은 하지 말 것. 발견만 하면 된다. 파일·라인 번호를 반드시 명시할 것.
```

---

## Step 3 — 결과 표시

서브에이전트 리포트를 사용자에게 그대로 전달한다. 추가로:

- ❌ 항목이 1개 이상이면 "수정하려면 `/market-cs` 는 원본 Story 의존이므로 원본 Story 부터 고치셔야 합니다" 안내
- ⚠ 만 있고 ❌ 없으면 "리뷰만 기록해두고 넘어갈지" 사용자에게 확인
- 수치 일치 100% 면 "✅ 모든 수치·종목·날짜 검증 통과" 한 줄 보고

---

## 중단 규칙

- 원본 Story 없음 → 즉시 중단
- `_data.json` 없음 → 일간이면 중단 (주간/월간은 data.json 없이도 CSV 로 진행 가능)
- 서브에이전트 실패 → 사용자에게 에러 전달 후 수동 검증 권고

---

## 주의

- 이 커맨드는 **읽기 전용**. Edit/Write 절대 사용하지 않는다.
- "수정해줘" 요청을 받으면 별도 작업으로 분리 — 현재 커맨드 범위 밖.
- 서브에이전트가 수정을 시도하면 프롬프트에 명시한 "수정 금지" 를 다시 강조해 재실행.