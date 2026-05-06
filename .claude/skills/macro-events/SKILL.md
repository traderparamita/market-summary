# Macro & Events Skill

주간/월간 보고서의 **Macro & Events** 탭 콘텐츠 작성 규칙과 절차.
이 탭은 **초보 투자자**를 위한 매크로 이벤트 해설 + 다음 기간 캘린더다.

---

## 핵심 규칙

1. **Forward Looking 금지**: 이미 지난 이벤트는 "리뷰"에, 아직 안 온 이벤트는 "캘린더"에만 넣는다. 섞지 말 것.
2. **초보자 친화**: 전문용어(CPI, FOMC, NFP 등) 사용 시 괄호 안에 한 문장 설명을 반드시 붙인다.
3. **수치 출처**: 실제 발표값은 `history/macro_indicators.csv` 또는 웹 검색 결과 기준. 추정·예상값을 실제값으로 쓰지 않는다.
4. **웹 검색은 Tavily MCP 우선**: `mcp__tavily__search` 도구를 사용. WebSearch는 폴백.
5. **날짜 정확성**: 주간 = ISO 주차 기준 월~금. 월간 = 해당 월 1일~말일.

---

## 탭 콘텐츠 구조

### A. 이번 기간 주요 이벤트 리뷰

각 이벤트 카드:
- 발표 날짜 + 이벤트명 (국기 이모지 + 국가 명시)
- 실제값 vs 예상치 vs 이전값 (macro_indicators.csv 또는 웹 검색으로 확인)
- "이게 왜 중요한가?" — 초보자용 1~2문장
- 시장 반응 — 해당 일간 `_story.html`에서 참조 가능하면 참조

**월간**: FOMC, CPI, NFP, GDP 등 핵심 이벤트만 선별 (최대 8~10개)

### B. 다음 기간 이벤트 캘린더

요일/날짜별 표:
- 날짜, 이벤트명, 예상치(있으면), 중요도(★~★★★)
- "이게 뭔가요?" 한 줄 설명

중요도 기준:
- ★★★: FOMC 결정, CPI, NFP, GDP, 중앙은행 금리결정
- ★★: PPI, PCE, 소매판매, 실업수당, 소비자심리
- ★: 주택지표, 소규모 지역 지표

---

## 공통 작성 절차 (주간 / 월간 동일)

### 주간 vs 월간 차이

| | 주간 | 월간 |
|---|---|---|
| 날짜 범위 | ISO 주차 월~금 (`{WEEK_START}` ~ `{WEEK_END}`) | 해당 월 1일~말일 (`{YYYY}-{MM}`) |
| CSV grep 패턴 | `^{WEEK_START}` ~ `^{WEEK_END}` | `^{YYYY}-{MM}` |
| 검색 키워드 | "이번 주 {WEEK_START}~{WEEK_END}" | "YYYY년 MM월" |
| 리뷰 제목 | 이번 주 주요 이벤트 리뷰 (날짜 범위) | 이번 달 주요 이벤트 리뷰 (YYYY년 MM월) |
| 캘린더 제목 | 다음 주 주목할 이벤트 (날짜 범위) | 다음 달 주목할 이벤트 (YYYY년 MM+1월) |
| 출력 파일 | `YYYY-WNN.html` + `YYYY-WNN_macro.html` | `YYYY-MM.html` + `YYYY-MM_macro.html` |

---

### Step 0 — 사전 준비: macro_indicators.csv 최신화

```bash
cd .
.venv/bin/python -m collectors.macro
```

수집 확인: 출력 결과에서 각 지표의 날짜 범위가 최신인지 확인.
예: `US_CPI_YOY: 2011-01-01 ~ 2026-03-01` → 3월 데이터 수집 완료.

주요 수집 지표:

| 지표코드 | 설명 | 소스 |
|---------|------|------|
| US_CPI_YOY | 미국 CPI (YoY) | FRED CPIAUCSL |
| US_CORE_CPI_YOY | 미국 Core CPI (YoY) | FRED CPILFESL |
| US_PCE_YOY | 미국 PCE 물가 (YoY) | FRED PCEPI |
| US_CORE_PCE_YOY | 미국 Core PCE (YoY) | FRED PCEPILFE |
| US_NFP_MOM | 미국 비농업 고용 변화 (MoM) | FRED PAYEMS |
| US_UNEMP_RATE | 미국 실업률 | FRED UNRATE |
| US_FED_RATE | 미국 연방기금금리 | FRED FEDFUNDS |
| KR_CPI_YOY | 한국 CPI (YoY) | ECOS |
| KR_BASE_RATE | 한국 기준금리 | ECOS |
| EU_POLICY_RATE | 유럽 ECB 예금금리 | FRED ECBDFR |

---

### Step 1 — 날짜 범위 확인

대상 기간의 시작일·종료일을 파악한다.
예: 2026-W16 → `{WEEK_START}` = 2026-04-13, `{WEEK_END}` = 2026-04-17

### Step 2 — macro_indicators.csv 조회

```bash
grep "^{DATE_PATTERN}" history/macro_indicators.csv | sort
```

`{DATE_PATTERN}` 예시:
- 주간: `"^2026-04-1[3-7]"` (월~금 범위)
- 월간: `"^2026-04"`

### Step 3 — Tavily 검색: 이번 기간 주요 이벤트

```
mcp__tavily__search: "이번 {주/달} 주요 경제지표 발표 결과 {날짜범위} CPI FOMC NFP"
mcp__tavily__search: "{날짜범위} economic data releases results"
```

### Step 4 — Tavily 검색: 다음 기간 캘린더

```
mcp__tavily__search: "다음 {주/달} 경제지표 캘린더 {다음 기간 날짜범위}"
mcp__tavily__search: "next {week/month} economic calendar {next period range}"
```

### Step 5 — HTML 작성 → 보고서 주입

아래 "보고서 주입 방법" 참조.

### Step 6 — `_macro.html` 저장

`output/summary/{weekly or monthly}/YYYY-WNN_macro.html` (또는 `YYYY-MM_macro.html`) 동일 내용으로 Write/Edit.

### Step 7 — Sources 탭 주입

Step 3~4에서 사용한 Tavily 검색 결과의 출처를 `tab-sources` 탭에 추가한다.

**수집 대상**: Step 3(이번 기간 이벤트 검색) + Step 4(다음 기간 캘린더 검색)에서 참조한 URL·제목·매체·날짜.

**작성 규칙**:
- 섹션 2개: "이번 기간 이벤트 출처" + "다음 기간 캘린더 출처"
- 각 출처: `<a href="URL">제목</a> — 매체, 날짜`
- URL이 없는 출처(macro_indicators.csv 등 로컬 데이터)는 "내부 데이터" 표기
- 최소 4건 이상

**주입 방법**: 해당 보고서의 `<div id="tab-sources">` ~ `</div><!-- /tab-sources -->` 블록을 Edit.
`_sources.html` sibling 파일도 동기화 (기존 Story Sources와 병합 — Macro 섹션 append).

---

## 보고서 주입 방법

`<div id="tab-macro">` ~ `</div><!-- /tab-macro -->` 블록 전체를 Edit으로 교체:

```
old_string:
<div id="tab-macro" class="tab-panel">
<!-- MACRO_EVENTS_PLACEHOLDER -->
</div><!-- /tab-macro -->

new_string:
<div id="tab-macro" class="tab-panel">
[작성한 HTML 콘텐츠]
</div><!-- /tab-macro -->
```

`_macro.html` 파일도 반드시 동일 내용으로 Write/Edit.
(generate_periodic.py 재실행 시 `_inject_existing_macro()`가 자동 보존하므로,
직접 수정할 때는 `_macro.html`도 함께 갱신해야 한다.)

---

## HTML 표준 구조

```html
<div id="tab-macro" class="tab-panel">

  <!-- ── 이번 기간 주요 이벤트 리뷰 ── -->
  <div class="macro-section">
    <h2>이번 주 주요 이벤트 리뷰 (YYYY-MM-DD ~ YYYY-MM-DD)</h2>
    <!-- 월간이면: <h2>이번 달 주요 이벤트 리뷰 (YYYY년 MM월)</h2> -->
    <div class="macro-cards">

      <div class="macro-card">
        <div class="macro-date">MM/DD (요일)</div>
        <div class="macro-title">🇺🇸 이벤트명</div>
        <div class="macro-values">
          실제 <span class="hl-up">X.X%</span> · 예상 X.X% · 이전 X.X%
        </div>
        <div class="macro-explain">
          [지표명(한국어 설명)]: 이게 왜 중요한지 초보자 눈높이 설명.
        </div>
        <div class="macro-reaction">시장 반응: [발표 후 주요 시장 움직임]</div>
      </div>
      <!-- 추가 카드 반복 -->

    </div>
  </div>

  <!-- ── 다음 기간 이벤트 캘린더 ── -->
  <div class="macro-section">
    <h2>다음 주 주목할 이벤트 (YYYY-MM-DD ~ YYYY-MM-DD)</h2>
    <!-- 월간이면: <h2>다음 달 주목할 이벤트 (YYYY년 MM+1월)</h2> -->
    <table class="macro-calendar">
      <thead>
        <tr><th>날짜</th><th>이벤트</th><th>예상</th><th>중요도</th><th>한 줄 설명</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>MM/DD (요일)</td>
          <td>🇺🇸 이벤트명</td>
          <td>X.X%</td>
          <td><span class="macro-importance">★★★</span></td>
          <td>초보자용 한 줄 설명.</td>
        </tr>
        <!-- 추가 행 반복 -->
      </tbody>
    </table>
  </div>

</div><!-- /tab-macro -->
```

### hl-up / hl-down 사용 기준

- `hl-up`: 실제값이 예상치 상회 + 경제에 긍정적 (ex. 고용 증가)
- `hl-down`: 실제값이 예상치 하회 + 경제에 긍정적 (ex. 인플레이션 하락)
- 문맥에 따라 반전 적용: CPI 예상 상회 → `hl-down` (인플레이션 우려)

---

## 최소 품질 기준 (필수 섹션)

W17 Macro 탭(`2026-W17_macro.html`)을 품질 기준 예시로 삼는다. 아래 **5개 블록**이 모두 있어야 완성:

| # | 블록 | 필수 요소 |
|---|------|----------|
| 1 | **KPI 카드 그리드** (`.macro-kpi-grid`) | 4개 핵심 지표 카드: 지표명 + 값 + 한 줄 설명. 예: US CPI, 기준금리, 10Y Breakeven, HY Spread |
| 2 | **이번 주/달 핵심 거시지표 리뷰** | 불릿 8~12개. 지표별: **지표 코드 + 값** (bold) → 맥락 해설 1~2문장. WTD/MTD 변화 포함 |
| 3 | **이번 주/달 이벤트 테이블** (`event-table`) | 날짜·지역·이벤트·결과/예상·중요도 5컬럼. 최소 8행 이상. `.imp-high/.imp-med/.imp-low` 배지 |
| 4 | **다음 주/달 이벤트 캘린더** (`event-table`) | 동일 5컬럼 형식. 최소 8행. 하단에 "W{N+1} 최대 변수" 불릿 3~4개 |
| 5 | **주요 금리·스프레드 현황** | 불릿 7~10개: Fed/BOK/ECB 기준금리, 10Y, 2Y, Curve, HY/IG Spread, Breakeven/Real Yield. 수치+WTD 변화+한 줄 해설 |

**품질 검증**: 위 5블록 중 하나라도 빠지면 미완성으로 간주. 작성 후 블록 수를 세어 확인할 것.

---

## 자가 검증 체크리스트

- [ ] **5개 블록 모두 존재하는가?** (KPI 카드 + 지표 리뷰 + 이벤트 테이블 + 다음 기간 캘린더 + 금리·스프레드)
- [ ] 이벤트 카드에 실제 발표값을 사용했는가? (추정값 금지)
- [ ] 해당 기간 이벤트만 리뷰 섹션에, 다음 기간 예정만 캘린더 섹션에 있는가?
- [ ] 모든 전문용어에 괄호 설명이 붙어있는가?
- [ ] `_macro.html` 파일이 저장되었는가?
- [ ] 수치 출처가 macro_indicators.csv 또는 신뢰할 수 있는 웹 소스인가?
- [ ] 이벤트 테이블이 최소 8행 이상인가?
- [ ] Sources 탭에 Tavily 검색 출처가 4건 이상 기록되었는가?
