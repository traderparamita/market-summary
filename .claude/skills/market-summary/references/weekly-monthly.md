# 주간 / 월간 / 분기 Story 작성 절차

기간 단위 Story 가이드. **공통 규칙(존댓말·forward-looking·세션 시각·인과방향·요일·고점 검증·표기)은 `SKILL.md` 본문 참조.** 일간 Story 의 6 섹션 골격은 `references/daily.md`.

---

## 주간 Story (마지막 영업일 작성)

### 구조 (템플릿)

```html
<!-- 주간 Story는 일간과 달리 Session Grid 없음 — Narrative 중심 -->

<!-- ── 1. Story Hero (주간 관점) ── -->
<div class="story-hero">
  <h2>이번 주 시장 이야기</h2>
  <div class="story-text">
    <strong>[한 줄 주간 테마: 관통하는 하나의 내러티브]</strong><br><br>
    
    [월요일부터 금요일까지 시간순 서술]
    - 월요일: [주요 이벤트 + 영향]
    - 화요일: [연쇄 반응]
    - ...
    - 금요일: [주간 마감]
  </div>
</div>

<!-- ── 2. Causal Chain (주간 흐름) ── -->
<!-- 4~6개 노드로 한 주의 인과 표현 -->

<!-- ── 3. Weekly Snapshot (Region Grid 선택) ── -->
<!-- 선택: Top Movers 또는 Sector Rotation 카드 -->

<!-- ── 4. Insight Grid (주간 학습 4개) ── -->

<!-- ── 5. Risk Section (주간 이슈 2-3개) ── -->

<!-- ── 7. WTD Progress + 다음 주 전망 (선택) ── -->
```

### 주간 작성 규칙

- **일간 Story 5개 수집** (월~금, 공휴일 제외)
- **주간 관점**: 일간 세부를 거둬내고 한 주를 관통하는 테마 강조
- **특정 날짜 서술 금지**: "월요일의 하락은 수요일 랠리의 서막이었다" (사후 참조) ❌
- **허용**: "월요일 하락 후 수요일이 과매도를 되돌리며 반등" ✅
- **WTD 수치** (`references/daily.md` Step 3-2 참조): 전주 금요일 종가 기준 계산
- **선택 섹션**: Top Movers, Sector Rotation 등은 필요시만 추가

---

## 월간 Story (마지막 영업일 작성)

### Step 1: 해당 월 일간 Story 수집

- 해당 월의 모든 영업일 식별
- 각 날짜 `_story.html` Read
- 주차별 요약(각 주의 테마)을 중간 단위로 활용 가능

### Step 2: 월간 관점 종합

- 월 전체 테마 도출
- 월초·월중·월말 구분하여 흐름 서술
- 월간 누적 수익률, 최대 낙폭, 주요 터닝 포인트
- 월간 주요 이벤트(FOMC, 고용보고서, 실적 시즌 등) 맥락화
- **주의**: 월말 관점에서 월초를 설명할 때도 당시 시점에서 알 수 없던 정보 금지

### 구조 (템플릿)

```html
<!-- 월간 Story는 주간 Story와 유사하되, 더 거시적 관점 -->

<!-- ── 1. Story Hero (월간 관점) ── -->
<div class="story-hero">
  <h2>이번 달 시장 이야기</h2>
  <div class="story-text">
    <strong>[한 줄 월간 테마: 한 달을 관통하는 거시 내러티브]</strong><br><br>
    
    [월초 ~ 월말 시간순 서술]
    - 상반부(1~10일): [주요 이벤트]
    - 중반부(11~20일): [연쇄 반응]
    - 하반부(21~말): [마무리]
  </div>
</div>

<!-- ── 2. Causal Chain (월간 흐름) ── -->
<!-- 4~6개 노드로 한 달의 인과 표현 -->

<!-- ── 3. Insight Grid (월간 학습 4개) ── -->

<!-- ── 4. Risk Section (월간 이슈 2-3개) ── -->

<!-- ── 6. MTD Progress + 다음 달 전망 (선택) ── -->
```

### 월간 작성 규칙

- **일간 Story 20개+ 수집** (월초 ~ 월말, 공휴일 제외)
- **월간 관점**: 주간 이슈들을 거둬내고 달을 관통하는 거시 테마 강조
- **특정 주/날짜 서술 금지**: "초반 하락은 말미 반등의 기초였다" (사후 참조) ❌
- **허용**: "3주 연속 하락 후 4주째 반등" (팩트 나열) ✅
- **MTD 수치** (`references/daily.md` Step 3-2 참조): 전월 말 종가 기준 계산
- **섹터/국가 회전**: 월간에만 "S&P 톱 5/바텀 5 섹터" 추가 고려

---

## 분기 Story 작성 절차

분기(Quarterly) Story는 **월간 3개를 종합한 상위 서사**. 월간 절차의 확장판으로, 기간만 3개월로 확대.

### Step 1: 해당 분기 월간 Story 수집

- 3개월치 `output/summary/monthly/YYYY-MM_story.html` Read (분기 = 캘린더 기준 3개월: Q1=1~3월, Q2=4~6월 …)
- 3개월치 `_pm.html`, `_macro.html` 도 필요 시 참조 (사실·수치 정합)

### Step 2: 분기 관점 종합

- 분기 전체 테마 도출 ("1~2월 X 주도 → 3월 Y 반전" 같은 월별 리듬)
- 월별 흐름 요약 (3개월을 한 화면에): 각 월의 대표 이벤트 2~3개씩
- 분기 누적 수익률 (QoQ), 최대 낙폭, 분기 내 ATH/ATL, 자산 분화
- 분기 핵심 이벤트 맥락화 (FOMC 2~3회, 주요 고용 발표 3회, CPI 3회, 지정학 이벤트)
- **주의**: 분기 말 관점에서 분기 초를 설명할 때도 당시 시점에서 알 수 없던 정보 금지

### Step 3: HTML 주입

- 대상: `output/summary/quarterly/YYYY-QN.html` (파일명 `2026-Q1.html` 형식)
- 분기 보고서가 없으면 `.venv/bin/python generate_periodic.py {year} --only quarterly --quarter N` 선행
- 주입 방식은 일간·주간·월간과 동일 — sibling 파일(`_story.html`, `_pm.html`, `_macro.html`) 저장 후 `generate_periodic.py` 재실행하면 `_inject_existing_*()` 가 자동 주입

### 데이터 소스

- **Snowflake MKT100 / MKT200 단일 정본** (via `market_source.load_long` / `load_macro_long`). CSV (`history/market_data.csv`, `history/macro_indicators.csv`) 는 legacy fallback
- 분기 매크로 데이터 백필이 필요하면 `.venv/bin/python -m collectors.macro --start YYYY-MM-DD` 으로 FRED + ECOS 재수집 → MKT200 upsert

---

## 공통 규칙 (일간/주간/월간)

| 항목 | 일간 | 주간 | 월간 |
|------|------|------|------|
| 세션 구분 | ✅ 3 세션 (Asia/EU/US) | ❌ (통합) | ❌ (통합) |
| 시간별 상세 | ✅ ev-time | ❌ | ❌ |
| Causal Chain | ✅ 3~5 노드 | ✅ 4~6 노드 | ✅ 4~6 노드 |
| Insight Grid | ✅ 4개 | ✅ 4개 | ✅ 4개 |
| Risk Section | ✅ 2~3개 | ✅ 2~3개 | ✅ 2~3개 |
| 기간 진행 | ✅ WTD/MTD | ✅ WTD | ✅ MTD |

---

## 검증 체크리스트 (일간/주간/월간 공통)

작성 후 **반드시** 다음을 확인:

- [ ] **6개 섹션 확인**: Story Hero / Causal Chain / [Session Grid 일간만] / Insight / Risk / 기간 Progress
- [ ] **시간순 인과관계**: 각 문장이 시간순인가? 사후 참조 없는가?
- [ ] **요일·휴일 정확성**: 날짜와 요일이 일치하는가? (CSV 검증)
- [ ] **고점·저점 표현**: "사상 최고치" 주장 전 CSV 확인했는가?
- [ ] **CSS 클래스**: 사용한 모든 클래스가 화이트리스트에 있는가?
- [ ] **수치 일치**: WTD/MTD 직접 계산 결과와 일치하는가?
- [ ] **파일 동기화**: `YYYY-MM-DD.html` + `YYYY-MM-DD_story.html` 내용 동일한가?

---

## HTML 주입 (공통)

- **주간**: 대상 `output/summary/weekly/YYYY-WNN.html` — 없으면 `.venv/bin/python generate_periodic.py {year}` 로 생성
- **월간**: 대상 `output/summary/monthly/YYYY-MM.html` — 없으면 `.venv/bin/python generate_periodic.py {year}` 선행
- **분기**: 대상 `output/summary/quarterly/YYYY-QN.html` — 없으면 `.venv/bin/python generate_periodic.py {year} --only quarterly --quarter N` 선행
- 모두 일간과 동일 패턴 — `_inject_existing_story()` 외부 직접 호출 금지, sibling `_story.html` 저장 확인
