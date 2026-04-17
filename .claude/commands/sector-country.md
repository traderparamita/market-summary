---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Bash(tail:*), Bash(awk:*), Bash(sort:*), Bash(cut:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD]  (날짜 생략 시 전 영업일)"
description: "섹터·국가 초보자 보고서: Data Dashboard 생성 → 오늘의 3개 주제(US섹터+KR섹터+국가) Tavily 검색 → Story 주입"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/sector-country/daily/**/*.html 2>/dev/null | head -3`
- market_data.csv 마지막 날짜: !`tail -5 /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/history/market_data.csv 2>/dev/null | cut -d',' -f1 | sort -u`

---

## Your task

Load and follow `.claude/skills/sector-country/SKILL.md`.

**Arguments**: $ARGUMENTS (형식: `YYYY-MM-DD`)

---

## 사전 점검

1. **날짜 결정**: 날짜 인자 없음 → 전 영업일 자동 선택.
2. **미래 날짜 금지**: 대상 날짜 > 오늘이면 즉시 중단하고 사용자에게 보고.
3. **데이터 가용성**: `market_data.csv` 마지막 날짜 < 대상 날짜이면 경고 후 사용자에게 확인.

---

## Step 0 — Telegram 시작 알림

사전 점검 통과 후 즉시 전송. 실패해도 계속 진행.

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && \
  .venv/bin/python notify_telegram.py {date} --start --label "섹터·국가"
```

---

## Step 1 — Data Dashboard 생성 + 오늘의 주제 확인

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python generate_sector_country.py {date}
```

CLI 출력에서 **섹터 Day N/11**, **국가 Day M/10**, **theme**, 3개 subjects를 기록한다.  
예: `섹터 Day 4/11 — 에너지·화학 (XLE + TIGER 200 에너지화학) | 국가 Day 3/10 — 중국`

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
print(f'=== 오늘의 주제 ===')
print(f'  섹터 Day {focus[\"sector_day\"]}/11 — {focus[\"theme\"]}')
print(f'  국가 Day {focus[\"country_day\"]}/10 — {focus[\"country_name\"]}')
print(f'  이전 섹터 사이클: {focus[\"prev_sector_date\"]}')
print(f'  이전 국가 사이클: {focus[\"prev_country_date\"]}')
for s in focus['subjects']:
    print(f'  [{s[\"code\"]}] {s[\"name\"]} | {s.get(\"etf\",\"\")} {s.get(\"ticker\",\"\")}')

print()
print('=== US 섹터 ===')
for s in sv['us_sectors']:
    mark = ' ★' if s['code'] in focus_codes else ''
    print(f\"{v(s['composite'])} | {s['name']:25s} {s['etf']:5s} | 1M={s.get('mom_1m','—')} 3M={s.get('mom_3m','—')}%{mark}\")

print()
print('=== KR 섹터 ===')
for s in sv['kr_sectors']:
    mark = ' ★' if s['code'] in focus_codes else ''
    print(f\"{v(s['composite'])} | {s['name']:15s} {s['etf']:30s} | 1M={s.get('mom_1m','—')} 3M={s.get('mom_3m','—')}%{mark}\")

print()
print('=== 국가 ===')
for c in cv['countries']:
    mark = ' ★' if c['code'] in focus_codes else ''
    print(f\"{c['view']} | {c['flag']} {c['name']:15s} | 3M={c.get('mom_3m','—')}%{mark}\")

"
```

---

## Step 3 — Tavily 뉴스 검색

**대상 날짜({date}) 이후 미래 데이터는 사용하지 않는다.**  
당일에 국한하지 않고 **최근 1~2주** 트렌드 뉴스를 참조해 포지셔닝 맥락을 설명한다.

> **KR 섹터 검색 원칙**: TIGER ETF는 업종 전체의 **proxy**다. ETF를 직접 검색하는 것이 아니라 해당 업종의 기업·정책·수요 뉴스를 검색한다. 수치는 `compute_sector_view()`에서 이미 산출되므로 검색은 **"왜 이 업종인가"** 맥락 파악에 집중한다.

> **대표주 검색 필수**: `SECTOR_REP_STOCKS` / `COUNTRY_REP_STOCKS`에 정의된 대표 기업의 최신 실적·뉴스를 반드시 검색한다. Story 본문에 해당 기업 동향을 포함할 것.

### 오늘의 3개 주제 검색 전략 (type: sector_country)

매일 **US 섹터 + KR 섹터 + 국가** 3개 주제를 검색한다. 순서: Subject 1(US) → Subject 2(KR) → Subject 3(국가) → 대표주 심층 → 비교/맥락.

| 순서 | 대상 | 검색 내용 | 키워드 예시 |
|------|------|---------|------------|
| 1 | Subject 1 (US 섹터) | 최근 1~2주 ETF 성과·흐름 + 핵심 드라이버 | `"XLE energy sector April 2026 ETF performance"` |
| 2 | Subject 1 (US 섹터) 대표주 | 섹터 대표 기업 최신 실적·뉴스 | `"Exxon Mobil Chevron earnings April 2026"` |
| 3 | Subject 2 (KR 섹터) | 최근 1~2주 국내 업종 뉴스 + 주요 기업 | `"Korea energy chemicals LG Chem Lotte Chemical 2026"` |
| 4 | Subject 2 (KR 섹터) 대표주 | KR 섹터 대표 기업 최신 뉴스 | `"LG화학 롯데케미칼 에너지화학 April 2026"` |
| 5 | Subject 3 (국가) | 주가지수 흐름 + 경제지표 + 정책 | `"China CSI300 Shanghai April 2026 market"` |
| 6 | Subject 3 (국가) 대표주 | 국가 대표 기업 최신 뉴스 | `"Alibaba Tencent China tech April 2026"` |
| 7 | 전체 맥락 (선택) | 이번 주 GICS 섹터 로테이션 흐름 | `"GICS sector rotation April 2026 winners"` |

#### 섹터별 대표주 검색 가이드

| US 섹터 | KR 섹터 | 대표주 검색 키워드 |
|---------|---------|-----------------|
| XLK (Technology) | TIGER 200 IT | `"NVIDIA Apple Microsoft Samsung SK Hynix LG Electronics 2026"` |
| XLC (Communication) | TIGER 200 커뮤니케이션서비스 | `"Alphabet Meta SK Telecom KT 2026"` |
| XLF (Financials) | TIGER 200 금융 | `"JPMorgan Bank of America Shinhan KB Hana 2026"` |
| XLE (Energy) | TIGER 200 에너지화학 | `"Exxon Chevron LG Chem Lotte Chemical 2026"` |
| XLV (Health Care) | TIGER 200 헬스케어 | `"UnitedHealth Johnson Celltrion Samsung Biologics 2026"` |
| XLI (Industrials) | TIGER 200 산업재 | `"Caterpillar Boeing HD Hyundai Doosan 2026"` |
| XLB (Materials) | TIGER 200 중공업 | `"Freeport Nucor Hanwha Aerospace Hyundai Rotem 2026"` |
| XLY (Consumer Discr.) | TIGER 200 경기소비재 | `"Amazon Tesla Hyundai Kia consumer 2026"` |
| XLP (Consumer Staples) | TIGER 200 생활소비비재 | `"Procter Gamble Coca-Cola CJ CheilJedang Orion 2026"` |
| XLU (Utilities) | TIGER 200 철강소재 | `"NextEra Duke Energy POSCO Hyundai Steel 2026"` |
| XLRE (Real Estate) | TIGER 200 건설 | `"Simon Property Prologis Hyundai Engineering GS Construction 2026"` |

---

## Step 4 — Story 작성

SKILL.md의 초보자 언어 변환 규칙 및 시간순 서술 원칙을 따른다.

**보고서 전체가 오늘의 3개 주제 중심이다.** 섹터와 국가는 독립적으로 서술하며 억지로 연결짓는 "연결 고리" 단락은 쓰지 않는다.  
일간/주간/월간 구분 없이 동일한 형식으로 작성한다.

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
  <!-- Subject 1: US 섹터 심층 분석 -->
  <h3 style="color:#F58220;margin-bottom:12px">🎯 {US섹터명} 심층 분석</h3>
  <p>현재 신호: {OW/N/UW} — <strong>{초보자 표현}</strong></p>

  <p><strong>최근 1~2주 흐름 (과거 → 현재)</strong></p>
  <p>{트렌드 배경 문단 1}</p>
  <p>{전개 문단 2}</p>
  <p>{현재 신호 이유 문단 3}</p>

  <p><strong>대표주 동향</strong></p>
  <p>{SECTOR_REP_STOCKS 기업 동향 — 2~3 문단으로 분리}</p>

  <!-- Subject 2: KR 섹터 심층 분석 -->
  <h3 style="color:#F58220;margin:16px 0 12px">🎯 {KR섹터명} 심층 분석</h3>
  <p>현재 신호: {OW/N/UW} — <strong>{초보자 표현}</strong></p>

  <p><strong>최근 1~2주 흐름 (과거 → 현재)</strong></p>
  <p>{국내 업종 트렌드 — 2~3 문단}</p>

  <p><strong>대표주 동향</strong></p>
  <p>{KR 대표 기업 최신 동향 — 2~3 문단}</p>

  <!-- Subject 3: 국가 심층 분석 -->
  <h3 style="color:#F58220;margin:16px 0 12px">🎯 {국가명} 시장 심층 분석</h3>
  <p>현재 신호: {OW/N/UW} — <strong>{초보자 표현}</strong></p>

  <p><strong>최근 1~2주 흐름 (과거 → 현재)</strong></p>
  <p>{주가지수 흐름 + 경제지표 + 정책 — 2~3 문단}</p>

  <p><strong>대표 지수·지표 동향</strong></p>
  <p>{COUNTRY_REP_STOCKS 기업 또는 지수 동향 — 2~3 문단}</p>

  <!-- 핵심 포인트 3가지 -->
  <h3 style="color:#F58220;margin:16px 0 12px">💡 핵심 포인트 3가지</h3>
  <p>① <strong>{US섹터 — 핵심 메시지}</strong></p>
  <p>{초보자 설명 1~2문장}</p>

  <p>② <strong>{KR섹터 — 핵심 메시지}</strong></p>
  <p>{초보자 설명 1~2문장}</p>

  <p>③ <strong>{국가 — 핵심 메시지}</strong></p>
  <p>{초보자 설명 1~2문장}</p>

  <div style="font-size:11px;color:#94a3b8;margin-top:16px;border-top:1px solid #e2e8f0;padding-top:8px">
    출처: Tavily 뉴스 검색 + 계량 신호 (history/market_data.csv) · {date} ({period}) · 섹터 Day {sector_day}/11 · 국가 Day {country_day}/10
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

경로: `output/sector-country/daily/YYYY-MM/{date}_story.html`

---

## Step 7 — Telegram 완료 알림

Story 주입 성공 후 전송. 실패해도 계속.

- `--focus`: 오늘의 주제 텍스트 (예: `"섹터 Day 4/11 — 에너지·화학 | 국가 Day 3/10 — 중국"`)
- `--ow`: OW 섹터/국가 목록 (Step 2 결과 기반, 없으면 생략)
- `--uw`: UW 섹터/국가 목록 (없으면 생략)

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && \
  .venv/bin/python notify_telegram.py {date} --sc-complete \
    --focus "섹터 Day N/11 — 오늘의 섹터 테마 | 국가 Day M/10 — 오늘의 국가" \
    --ow "XLK, TIGER 200 IT, 미국" \
    --uw "XLE"
```

---

## 완료 보고

- 생성된 HTML 경로
- 섹터 Day N/11 — 테마명 (US ETF + KR ETF)
- 국가 Day M/10 — 국가명
- OW 섹터 (US + KR), UW 섹터 (있다면)
- OW 국가, UW 국가 (있다면)
- Tavily 검색 건수 + 주요 뉴스 제목 2~3개

---

## 중단 규칙

- Step 1 실패: 즉시 중단 + 사용자 보고
- Step 5 주입 검증 실패 (`STORY_PLACEHOLDER` 잔존 또는 `<!DOCTYPE` 소실): 즉시 사용자 보고
