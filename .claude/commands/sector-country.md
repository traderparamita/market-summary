---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Bash(tail:*), Bash(awk:*), Bash(sort:*), Bash(cut:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD] [daily|weekly|monthly]  (날짜 생략 시 전 영업일, 기간 생략 시 daily)"
description: "섹터·국가 초보자 보고서 (일간/주간/월간): Data Dashboard 생성 → Tavily 뉴스 검색 → Story 주입"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 일간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/sector-country/daily/**/*.html 2>/dev/null | head -3`
- 최근 주간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/sector-country/weekly/*.html 2>/dev/null | head -3`
- 최근 월간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/sector-country/monthly/*.html 2>/dev/null | head -3`
- market_data.csv 마지막 날짜: !`tail -5 /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/history/market_data.csv 2>/dev/null | cut -d',' -f1 | sort -u`

---

## Your task

Load and follow `.claude/skills/sector-country/SKILL.md`.

**Arguments**: $ARGUMENTS (형식: `YYYY-MM-DD [daily|weekly|monthly]`)

---

## 사전 점검

1. **날짜 결정**: 날짜 인자 없음 → 전 영업일 자동 선택. 기간 인자 없음 → `daily` 기본값.
2. **미래 날짜 금지**: 대상 날짜 > 오늘이면 즉시 중단하고 사용자에게 보고.
3. **데이터 가용성**: `market_data.csv` 마지막 날짜 < 대상 날짜이면 경고 후 사용자에게 확인.

---

## Step 1 — Data Dashboard 생성 + 오늘의 주제 확인

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python generate_sector_country.py {date} {period}
```

CLI 출력에서 **오늘의 주제(theme)** 와 대상 2개(subjects)를 기록한다.  
예: `Day 1/15: 기술·반도체 — XLK (Technology) + TIGER 반도체 (277630.KS)`

실패 시 오류 확인 후 재시도 또는 중단.

---

## Step 2 — 데이터 읽기

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python -c "
from generate_sector_country import get_focus
from portfolio.view.sector_view import compute_sector_view
from portfolio.view.country_view import compute_country_view
import math

focus = get_focus('{date}')
sv = compute_sector_view('{date}')
cv = compute_country_view('{date}')

def v(c):
    if c is None or (isinstance(c, float) and math.isnan(c)): return 'N'
    return 'OW' if c >= 0.25 else ('UW' if c <= -0.25 else 'N')

focus_codes = {s['code'] for s in focus['subjects']}
print(f'=== 오늘의 주제 (Day {focus[\"day\"]}/15): {focus[\"theme\"]} ===')
for s in focus['subjects']:
    print(f'  {s[\"name\"]} | {s.get(\"etf\",\"\")} {s.get(\"ticker\",\"\")}')

print()
print('=== US 섹터 ===')
for s in sv['us_sectors']:
    mark = ' ★' if s['code'] in focus_codes else ''
    print(f\"{v(s['composite'])} | {s['name']:25s} {s['etf']:5s} | 1M={s.get('mom_1m','—')} 3M={s.get('mom_3m','—')}%{mark}\")

print()
print('=== KR 섹터 ===')
for s in sv['kr_sectors']:
    mark = ' ★' if s['code'] in focus_codes else ''
    print(f\"{v(s['composite'])} | {s['name']:10s} {s['etf']:20s} | 1M={s.get('mom_1m','—')} 3M={s.get('mom_3m','—')}%{mark}\")

print()
print('=== 국가 ===')
for c in cv['countries']:
    mark = ' ★' if c['code'] in focus_codes else ''
    print(f\"{c['view']} | {c['flag']} {c['name']:15s} | 3M={c.get('mom_3m','—')}%{mark}\")

print()
print(f'Regime: {sv[\"us_regime\"]} | Cycle: {sv[\"cycle_phase\"]}')
"
```

---

## Step 3 — Tavily 뉴스 검색

**대상 날짜({date}) 이후 미래 데이터는 사용하지 않는다.**  
당일에 국한하지 않고 **최근 1~2주** 트렌드 뉴스를 참조해 포지셔닝 맥락을 설명한다.

### 검색 목록 — 오늘의 주제 2개에 집중 (5~7회)

SKILL.md의 검색 키워드 전략을 따른다.

**오늘 주제 Subject 1** (3회):
1. 심층 트렌드 — 최근 1~2주 흐름 + 핵심 드라이버
2. 관련 기업·섹터 뉴스 — 구체적 이유
3. vs 매크로 국면/사이클 연결

**오늘 주제 Subject 2** (3회):
4. 심층 트렌드 — 최근 1~2주 흐름
5. 관련 뉴스
6. Subject 1과의 비교·연계 포인트

**전체 컨텍스트** (1회, 선택):
7. 전체 섹터·국가 OW/UW 흐름 요약

---

## Step 4 — Story 작성

SKILL.md의 초보자 언어 변환 규칙 및 시간순 서술 원칙을 따른다.

**Story 초점: 오늘의 주제 2개를 심층 분석.** 나머지 섹터·국가는 현황 요약 1~2줄로 축소.

### 품질 규칙

**1. 날짜 이후 데이터 금지**  
{date} 이후 발생한 결과를 신호 설명의 근거로 사용하지 않는다.

**2. 고점·저점 표현 전 CSV 검증**  
"YTD 최고", "연내 신고점", "52주 고점" 사용 전 반드시 확인:

```bash
grep "{indicator_code}" history/market_data.csv | grep "^2026" | sort | awk -F',' '{print $1, $5}' | sort -k2 -rn | head -5
```

해당일 종가가 **1위**일 때만 사용. 아니면 "월간 최고치" 등 실제 범위로 표현.

**3. 날짜·요일 정확성**  
날짜와 요일이 실제 달력과 일치하는지 확인.

**4. 수치 출처**  
모든 수익률·수치는 `compute_sector_view()` / `compute_country_view()` 반환값 기준. Tavily 수치와 상충 시 CSV 우선.

**5. 섹터 내부 코드 금지**  
`SC_US_TECH` 같은 코드 노출 금지. ETF명(XLK) 또는 섹터명(Technology) 사용.

### Story HTML 형식

```html
<div class="story-content">
  <!-- 오늘의 주제 Subject 1 심층 분석 -->
  <h3 style="color:#F58220;margin-bottom:12px">🎯 {Subject1 이름} 심층 분석</h3>
  <p>현재 신호: {OW/N/UW} — {초보자 표현}<br>
  {최근 1~2주 트렌드를 시간순으로: 배경 → 전개 → 현재 신호 이유}</p>

  <!-- 오늘의 주제 Subject 2 심층 분석 -->
  <h3 style="color:#F58220;margin:16px 0 12px">🎯 {Subject2 이름} 심층 분석</h3>
  <p>현재 신호: {OW/N/UW} — {초보자 표현}<br>
  {최근 1~2주 트렌드를 시간순으로}</p>

  <!-- 두 주제 비교 (섹터 페어의 경우) -->
  <h3 style="color:#F58220;margin:16px 0 12px">🔍 비교 포인트</h3>
  <p>{두 주제의 공통점·차이점 — 글로벌 vs 국내 신호 비교 등}</p>

  <!-- 전체 현황 요약 -->
  <h3 style="color:#F58220;margin:16px 0 12px">📊 전체 현황 요약</h3>
  <p>{전체 OW/UW 섹터·국가 1~2줄 요약}</p>

  <!-- 핵심 포인트 -->
  <h3 style="color:#F58220;margin:16px 0 12px">💡 핵심 포인트</h3>
  <p>{초보자를 위한 핵심 메시지 2~3줄}</p>

  <div style="font-size:11px;color:#94a3b8;margin-top:16px;border-top:1px solid #e2e8f0;padding-top:8px">
    출처: Tavily 뉴스 검색 + 계량 신호 (history/market_data.csv) · {date} ({period}) · Day {focus_day}/15
  </div>
</div>
```

---

## Step 5 — Story 주입

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python -c "
from generate_sector_country import inject_story
inject_story('{html_path}', '''
{story_html}
''')
"
```

### 주입 후 검증

```bash
grep -c "story-content\|STORY_PLACEHOLDER\|<!DOCTYPE" {html_path}
```

- `<!DOCTYPE html>` 존재
- `STORY_PLACEHOLDER` **0개** (치환 완료)
- `story-content` **1개** 이상

---

## Step 6 — `_story.html` 저장

| 기간 | 경로 |
|------|------|
| daily | `output/sector-country/daily/YYYY-MM/{date}_story.html` |
| weekly | `output/sector-country/weekly/{YYYY-WNN}_story.html` |
| monthly | `output/sector-country/monthly/{YYYY-MM}_story.html` |

---

## 완료 보고

- 생성된 HTML 경로
- 매크로 국면 + 경기 사이클
- OW 섹터 (US + KR), UW 섹터 (있다면)
- OW 국가, UW 국가 (있다면)
- Tavily 검색 건수 + 주요 뉴스 제목 2~3개

---

## 중단 규칙

- Step 1 실패: 즉시 중단 + 사용자 보고
- Step 5 주입 검증 실패 (`STORY_PLACEHOLDER` 잔존 또는 `<!DOCTYPE` 소실): 즉시 사용자 보고