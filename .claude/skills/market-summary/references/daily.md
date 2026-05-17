# 일간 Story 작성 절차

일간 Market Story 작성 전용 가이드. **공통 규칙(존댓말·forward-looking·세션 시각·인과방향·요일·고점 검증·표기)은 `SKILL.md` 본문 참조.**

---

## 일간 전용 추가 규칙

### Story Hero 세션 간 `<br><br>` 여백

- `<div class="story-hero">` 내부 `<div class="story-text">`에서 **아시아 → 유럽 → 미국 세션 문단을 `<br><br>`로 분리**
- 단일 `<br>`만 쓰면 세션이 한 덩어리로 붙어 가독성이 떨어진다
- 세션 도입부(서두 → 첫 세션)와 세션 종료 후(마지막 세션 → VIX/마무리 단락)에도 `<br><br>` 유지
- Session Grid 영역(`session-grid`)은 CSS로 이미 분리돼 있어 불필요. **Story Hero 텍스트 블록에만 해당**

### Story Hero 세션별 간결성

Story Hero의 **아시아/유럽/미국 세션 서술은 세션 수준의 핵심 요약만** 작성한다:

**금지 패턴** (시간별 micro-detail):
- ❌ "09:00 코스피 6,619.00 출발 → 11:00 장중 고점 6,702.38 → 15:30 마감 6,690.90"
- ❌ "아침 서울 외환시장에서 원/달러는 1,474원으로 출발해 UAE OPEC 탈퇴 발표에 일시 강세..."
- ❌ "삼성전자 +1.80%(226,000원), SK하이닉스 −0.54%(1,293,000원)는..."

**권장 패턴** (핵심 흐름 중심):
- ✅ "코스피는 에너지/화학 섹터 +5.03% 급등에 힘입어 3거래일 연속 사상 최고 종가 6,690.90(+0.75%)를 기록"
- ✅ "원/달러는 유가 상승 영향으로 1,479원 수준으로 약세 전환"
- ✅ "상하이 +0.71%, 항셍 +1.68%, 알리바바·메이퇀·텐센트 등 인터넷주 일제 강세"

**세션당 길이**: 3-5 문장 (현재 평균 10-12 문장 → 절반 축약)

**Session Grid와 역할 분담**:
- **Story Hero**: 세션별 핵심만 (why, what happened)
- **Session Grid**: 시간별 타임라인 상세 (`09:00`, `11:00`, `15:30` 이벤트)

---

## Step 1: 입력 확인

```
output/summary/{YYYY-MM}/{YYYY-MM-DD}_data.json  # 해당일 가격·변동률 데이터
output/summary/{YYYY-MM}/{YYYY-MM-DD}.html       # 주입 대상 HTML (이미 존재)
```

- `_data.json`의 `holiday` 필드, 각 자산의 종가/변동률 확인
- KOSPI/KOSDAQ 휴장일이면 해당 사실을 명시하고 Story 작성
- **`stocks` 카테고리 확인**: KR 50 + US 50 + ASIA 65 + ADR 1 = 약 166종 데이터 보유. 아시아 세션 서술 시 `references/stocks-asia.md`의 일본/중국/대만 대표 종목 일변동률을 본문에 1-2개 인용해 구체화

## Step 2: 시간순 웹 데이터 수집

**반드시 시간 순서로** 수집:

1. **아시아 세션** (09:00~15:30 KST): 한국/일본/중국 시장 + 경제지표 + 아시아 지정학
2. **유럽 세션** (16:00~01:30 KST): 유럽 시장 + ECB/BOE 발언 + 유럽 경제지표
3. **미국 세션** (22:30~06:00 KST): 미국 경제지표 + Fed 발언 + 기업 실적 + 장중 흐름

**검색 시 주의**:
- 쿼리에 **정확한 날짜**를 넣어 미래 데이터 차단 (`"April 7 2026"` 같은 식)
- 당일 09시 이후 장중 데이터 검색 금지
- 훅(`PreToolUse WebSearch|WebFetch`)이 자동 검증하므로 block되면 쿼리 수정

## Step 3: Story 작성 (6개 섹션 템플릿)

Story는 **정확히 6개 섹션**을 이 순서대로 구성합니다:
1. Story Hero · 2. Causal Chain · 3. Session Grid · 4. Insight Grid · 5. Risk Section · 6. WTD/MTD Progress

**제외된 섹션 (사용 금지)**: Cross-Asset Flow Map (`.cross-asset`, `.af-map`) — 억지 인과 유발로 제거됨.

기존 일간 `_story.html`을 Read로 확인해 구조 파악 후 작성.

### 템플릿: 일간 Story 구조

```html
<!-- ── 1. Story Hero ── -->
<div class="story-hero">
  <h2>오늘의 시장 이야기</h2>
  <div class="story-text">
    <strong>[한 줄 헤드라인: 오늘의 극단 이벤트 또는 테마]</strong><br><br>
    
    <strong>아시아 세션</strong>은 [시간 범위(09:00~15:30)] [주요 흐름을 한 문장으로]. 
    [지수/섹터별 상세 1-2 문장] [수치와 함께 전개] ... <br><br>
    
    <strong>유럽 세션</strong>은 [시간 범위(16:00~01:30)] [주요 이벤트].
    [지수·상품·통화 전개] ... <br><br>
    
    <strong>미국 세션</strong>은 [시간 범위(22:30~06:00)] [주요 이벤트].
    [지수·금리·상품 마감] ... [다음날 기대사항도 가능]
  </div>
</div>

<!-- ── 2. Causal Chain ── -->
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 핵심 흐름 — 하나의 체인으로 이해하기</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:16px;">[원인 1] → [중간 결과] → [최종 결과] 형태로 한 줄 요약</div>
<div class="causal-chain">
  <div class="cause-node">
    <div class="node-label">[카테고리: 지정학/거시/기업 등]</div>
    <div class="node-title">[핵심 이벤트]</div>
    <div class="node-detail">[상세 설명 1-2 문장]</div>
    <div class="node-impact up/down/flat">[영향 방향]</div>
  </div>
  <div class="cause-arrow">→</div>
  [2번째~5번째 노드 반복]
</div>

<!-- ── 3. Session Grid (3 세션) ── -->
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">세계 시장은 릴레이처럼 돌아갑니다</div>
<div style="font-size:12px;color:var(--muted);margin-bottom:16px;">[날짜 요약] — [3 세션을 한 문장으로 대조]</div>
<div class="session-grid">
  <!-- 아시아 블록 -->
  <div class="session-block asia">
    <div class="session-header">
      <div class="session-icon asia">🇰🇷</div>
      <div>
        <div class="session-name">아시아 세션</div>
        <div class="session-time">한국 09:00 ~ 15:30</div>
      </div>
    </div>
    <!-- ★ Verdict 배지 (필수) — 한 줄 평가 + 색상 (up/down/flat) -->
    <span class="session-verdict verdict-up/down">오늘의 아시아 시황 한 줄</span>
    <ul class="session-events">
      <li><span class="ev-time">09:00</span> [시간별 사건 1]</li>
      <li><span class="ev-time">12:00</span> [시간별 사건 2]</li>
      <li><span class="ev-time">15:30</span> [시간별 사건 3 + 마감]</li>
    </ul>
    <div class="session-kpi">
      <div class="s-kpi"><div class="s-kpi-label">KOSPI</div><div class="s-kpi-value up/down">+0.39% / −0.49%</div></div>
      <div class="s-kpi"><div class="s-kpi-label">[2번째 지수]</div><div class="s-kpi-value up/down">값</div></div>
      <div class="s-kpi"><div class="s-kpi-label">[3번째 지수]</div><div class="s-kpi-value up/down">값</div></div>
    </div>
  </div>
  
  <!-- 유럽 블록 (위와 동일 구조, class="session-block europe" 사용) -->
  <!-- 미국 블록 (위와 동일 구조, class="session-block us" 사용) -->
</div>

<!-- ── 4. Insight Grid (4개 카드) ── -->
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 핵심 학습</div>
<div class="insight-grid">
  <div class="insight-card">
    <div class="badge">인사이트 1</div>
    <div style="font-weight:600;margin-bottom:6px;">[제목]</div>
    <div style="font-size:13px;">[1-2 문장 설명]</div>
  </div>
  
  [2번째~4번째 카드 반복]
</div>
```

### Insight Grid 작성 원칙

1. **제목 배치**: `<div class="insight-grid">` **밖**에 제목 div 배치 (grid item 충돌 방지)
2. **카드 개수**: 정확히 4개 (2열 × 2행 배치)
3. **카드 내용**: badge + 제목(bold) + **본문 3-4문장**(투자자 관점 해설) + metric-row(핵심 수치 2개)
4. **Badge**: 해당 인사이트의 키워드 (예: "Apple", "BOJ", "UAE 탈퇴", "코스피 8위")
5. **metric-row 필수**: 각 카드 하단에 관련 핵심 수치 2개를 `metric-row` > `metric-item` 구조로 표시

**품질 기준 예시** (2026-04-28 참고):
```html
<div style="margin-bottom:12px;font-size:15px;font-weight:600;color:#1a1d2e;">오늘의 핵심 학습</div>
<div class="insight-grid">
  <div class="insight-card">
    <span class="badge">코스피 8위</span>
    <div style="font-weight:600;color:#1a1d2e;margin-bottom:8px;">코스피 6,700 첫 돌파 — 한국 시총 세계 8위 부상</div>
    <div style="font-size:13px;color:#2d3148;line-height:1.7;">장중 6,712.73까지 올라 사상 첫 6,700선 돌파. 종가 6,641.02로 다시 사상 최고 갱신. Bloomberg은 한국 시총이 $4조를 넘어 영국을 추월, 세계 8위로 올라섰다고 보도. 삼성전자·SK하이닉스 2사가 코스피 시총의 40%+ 차지.</div>
    <div class="metric-row"><div class="metric-item"><div class="metric-label">코스피 장중 최고</div><div class="metric-value up">6,712.73</div></div><div class="metric-item"><div class="metric-label">연초 대비</div><div class="metric-value up">+54.10%</div></div></div>
  </div>
  <!-- 2, 3, 4번 카드 동일 구조 반복 -->
</div>
```

**부실 카드 금지**: "1-2 문장으로 끝나는 얕은 설명"은 부실로 간주. 각 카드는 **왜 중요한지**(So what?)를 투자자 관점에서 설명해야 함.

**잘못된 구조 (금지)**:
```html
<!-- ❌ 제목을 grid 안에 넣으면 첫 번째 grid item이 되어 레이아웃 깨짐 -->
<div class="insight-grid">
  <div style="...">오늘의 핵심 학습</div>  <!-- 이것이 grid item 1 -->
  <div class="insight-card">...</div>      <!-- grid item 2 -->
  ...
</div>
```

### Risk Section + WTD/MTD Progress

```html
<!-- ── 5. Risk Section (2-3개) ── -->
<div class="risk-section" style="margin-top:20px;">
  <h3>⚠️ 이번 주 주목할 리스크</h3>
  <ul class="risk-items">
    <li class="risk-item">
      <span class="risk-tag high/med/low">[위험도]</span>
      <strong>[리스크 요인]:</strong> [설명 1-2 문장] — [대응 또는 전망]
    </li>
    <li class="risk-item">
      [2번째~3번째 리스크]
    </li>
  </ul>
</div>

<!-- ── 6. WTD / MTD Progress ── -->
<!-- 채권 bp 누적 줄은 의도적으로 제외. 일변동값을 WTD/MTD 자리에 재인용하는 패턴이 반복돼 verify gate 가 막아왔다.
     채권 누적 정보는 PM Story 의 💵 채권 섹션에서 충분히 다룬다. -->
<div style="margin-top:24px;display:grid;grid-template-columns:1fr 1fr;gap:16px;">
  <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
    <h3 style="font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border);">주간 누적 (W## · 전주 금요일 종가 대비 · MM/DD 기준)</h3>
    <ul style="font-size:13px;line-height:1.7;margin:0;padding-left:18px;">
      <li>핵심 지수: KOSPI [%], S&P500 [%], ...</li>
      <li>원자재: [상품] [%], [상품] [%], ...</li>
      <li>FX: DXY [%], 원/달러 [%]</li>
    </ul>
  </div>
  
  <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
    <h3 style="font-size:14px;font-weight:600;color:#1a1d2e;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border);">월간 누적 (#월 · 전월 말 종가 대비 · MM/DD 기준)</h3>
    <ul style="font-size:13px;line-height:1.7;margin:0;padding-left:18px;">
      <li>핵심 지수: KOSPI [%], S&P500 [%], ...</li>
      <li>원자재: [상품] [%], [상품] [%], ...</li>
      <li>FX: DXY [%], 원/달러 [%]</li>
    </ul>
  </div>
</div>
```

### WTD/MTD 카드 작성 원칙

1. **카드 스타일 적용**: 배경색, 테두리, 그림자로 시각적 구분
2. **제목 간결화**: "전주 금요일 종가 기준" 같은 중복 설명 제거
3. **데이터 정렬**: 핵심 지수 → 원자재 → FX 순서 유지 (채권 bp 누적은 PM Story 채권 섹션에서 다룬다)
4. **간격 개선**: `line-height:1.7`, `gap:16px`로 가독성 향상

**스타일 필수 요소**:
- 카드 배경: `background:var(--card)`
- 테두리: `border:1px solid var(--border)`
- 둥근 모서리: `border-radius:12px`
- 그림자: `box-shadow:0 1px 3px rgba(0,0,0,0.04)`
- 제목 하단선: `border-bottom:1px solid var(--border)`

### 작성 규칙 (템플릿 사용 시)

1. **모든 6개 섹션 필수** — 하나라도 빠지면 구조 검증 실패 (Cross-Asset Flow Map 제외)
2. **Verdict 배지 필수** (Session Grid 내 각 세션):
   - `verdict-up`: 강세/긍정적 흐름
   - `verdict-down`: 약세/부정적 흐름
   - `verdict-flat`: 보합/중립
3. **시간 정확성**:
   - 아시아: 09:00~15:30
   - 유럽: 16:00~01:30 (또는 17:00~00:30, 서머타임 차이)
   - 미국: 22:30~06:00 (또는 23:30~05:00, 서머타임 차이)
4. **세션 간 미래 참조 금지** (SKILL.md "세션별 마감 시각" 규칙 참조)
5. **WTD/MTD 수치 직접 계산** (아래 Step 3-2 참조)

### Step 3-1: 필수 섹션 체크리스트 (반드시 확인)

일간 Story는 **반드시 다음 6개 섹션을 모두 포함**해야 합니다. 하나라도 빠지면 구조 검증 실패.

- [ ] **1. Story Hero** — `<div class="story-hero">` + `<div class="story-text">`
  - 한 줄 헤드라인 (강조: 최고·최저·주요 이벤트)
  - 세션별 상세 서술 (아시아 → 유럽 → 미국, `<br><br>` 구분)
  
- [ ] **2. Causal Chain** — `<div class="causal-chain">` + `<div class="cause-node">` ×3~5
  - 원인→결과 체인 (3~5단계)
  - 각 노드: label, title, detail, node-impact(up/down/flat)
  
- [ ] **3. Session Grid** — `<div class="session-grid">` + `<div class="session-block">` ×3 (asia/europe/us)
  - 각 세션 블록: header(아이콘+시간대) + verdict 배지 + events + s-kpi 그리드
  - **Verdict 배지** (필수): `<span class="session-verdict verdict-up/down/flat">` (한 줄 평가)
  
- [ ] **4. Insight Grid** — `<div class="insight-grid">` + `<div class="insight-card">` ×4
  - 4개 교육 카드 (투자자 관점 핵심 학습)
  
- [ ] **5. Risk Section** — `<div class="risk-section">` + `<ul class="risk-items">` + `<li class="risk-item">` ×2~3
  - 2~3개 리스크 요인 (전망/가능성 표현)
  
- [ ] **6. WTD/MTD Progress** — `<h3>` + `<ul>` 2세트
  - WTD/MTD 누적 지수 + 테마 (별도 섹션)

### Step 3-2: Weekly & Monthly Progress 단락 작성

주간/월간 Story는 **마지막 영업일에만** 작성되므로, 일간 Story 안에 WTD(Week-to-Date)·MTD(Month-to-Date) 한 단락씩을 포함해 주 중간에도 누적 흐름을 볼 수 있게 한다.

**데이터 소스**: `_data.json`의 `weekly` 필드는 **ISO WTD** (전주 금요일 종가 대비), `monthly` 필드는 **Calendar MTD** (전월 말 종가 대비)입니다. `verify_report_numbers.py`와 동일 기준이므로 그대로 사용 가능합니다.

**WTD(Week-to-Date) 계산 규칙**:
- 기준선: **ISO 주의 전주 마지막 영업일 종가** (보통 전주 금요일)
- WTD = `(target_date 종가 / 전주 금요일 종가 - 1) × 100`
- 예: W17 화요일(4/21) 보고서 → 기준선 = 4/17 금요일 종가
- 직접 `history/market_data.csv` 에서 두 날짜 종가를 추출해 계산

```python
# 예시 스니펫 (Python)
import pandas as pd
df = pd.read_csv('history/market_data.csv')
df['DATE'] = pd.to_datetime(df['DATE'])
# 전주 금요일 찾기: target_date 의 ISO 주 1일(월) 의 전일(= 전주 일요일) 이전의 가장 가까운 영업일
# 간단히: target_date 의 weekday() + 3 을 빼면 바로 전주 금요일
import datetime as dt
t = dt.date(2026, 4, 21)                       # target = 화요일
prev_fri = t - dt.timedelta(days=t.weekday() + 3)  # → 4/17 금
fri_close = df[(df['INDICATOR_CODE']=='EQ_KOSPI') & (df['DATE']==str(prev_fri))]['CLOSE'].values[0]
tue_close = df[(df['INDICATOR_CODE']=='EQ_KOSPI') & (df['DATE']==str(t))]['CLOSE'].values[0]
wtd = (tue_close/fri_close - 1) * 100
```

**MTD(Month-to-Date) 계산 규칙**:
- 기준선: **전월 마지막 영업일 종가**
- MTD = `(target_date 종가 / 전월 마지막 영업일 종가 - 1) × 100`
- `_data.json` 의 `monthly` 필드도 롤링 30일 기준일 수 있어 직접 계산 권장

**작성 형식** (예시):

```html
<h3>주간 누적 (W15 · 3/5 영업일 경과 · 전주 금요일 종가 기준)</h3>
<ul>
  <li>핵심 지수 (Fri 4/17 → Wed 4/22): KOSPI +2.5%, S&amp;P500 −0.6%, NASDAQ −1.2%, DXY +0.4%</li>
  <li>이번 주 흐름: (시간순 사실 나열, 사후적 프레이밍 금지)</li>
</ul>

<h3>월간 누적 (4월 · 7/22 영업일 경과 · 3월 말 종가 기준)</h3>
<ul>
  <li>핵심 지수: KOSPI +3.2%, S&amp;P500 +0.4%, Gold +2.1%, WTI −5.8%</li>
  <li>월초 이후 테마: (시간순 서술)</li>
</ul>
```

**규칙**:
- **경과 영업일 수 표기 필수**: "3/5 영업일 경과" + **기준선 명시**("전주 금요일 종가 기준")
- **수치는 직접 계산**: `_data.json` 의 `weekly`/`monthly` 필드는 WTD/MTD 와 다른 롤링 값. 신뢰 금지.
- **테마 한 줄**: 일간 Narrative와 중복 피하며 주/월 전체 관점에서 한 문장 압축
- **Forward looking 금지**: 오늘 이후 이벤트 참조 금지
- **마지막 영업일의 일간 Story**: "W15, 5/5 영업일 경과 — 주간 마감" 표기. 주간 Story 가 같은 날 작성되므로 이 단락은 간결하게.

**작성 중 자가 검증**:
- 각 문장의 인과관계가 시간순인가?
- 세션별 서술에서 해당 세션 마감 이후 이벤트를 참조하지 않았는가?
- 요일·휴일이 `_data.json`과 일치하는가?

---

## Step 3-S: Sources 탭 주입 (필수 — 절대 생략 금지)

Story HTML 주입 직후, **같은 Edit 세션 안에서** `tab-sources` 탭을 채운다. Story 만 쓰고 Sources 를 비워두면 안 된다.

- 작성 규칙·HTML 구조는 `references/sources.md` 참조
- **최소 링크 수**: 일간 5건, 주간 10건, 월간 15건 (CSV/매크로 데이터 소스 라인은 별도)
- 사이블링 파일 `YYYY-MM-DD_sources.html` 도 동기 저장
- 검증: `scripts/verify_report_numbers.py` 가 자동으로 빈 sources 를 catch (Stop 훅). placeholder 만 남거나 링크 3건 미만이면 위반으로 보고
- 검증 통과 기준: `tab-sources` 블록 안에 `<a href` 링크가 3건 이상, `SOURCES_PLACEHOLDER` 텍스트 없음

## Step 4: HTML 주입

### (A) 신규 일간 생성 — `generate.py`가 자동 처리

`.venv/bin/python generate.py {date}` 실행 시 내부적으로 `_inject_existing_story()`가 호출되어 Story 탭 placeholder 처리와 `_story.html` 저장까지 모두 자동이다. **외부에서 이 함수를 직접 호출할 필요 없다.**

### (B) 이미 존재하는 Story를 수정할 때

**방법 1 (권장) — `tab-story` 블록 직접 Edit**:
1. `output/summary/YYYY-MM/YYYY-MM-DD.html`에서 `<div id="tab-story" class="tab-panel">` ~ `</div><!-- /tab-story -->` 사이 블록을 Edit 도구로 교체
2. 같은 내용으로 `output/summary/YYYY-MM/YYYY-MM-DD_story.html`도 Edit (두 파일 동기화)
- 장점: 대시보드·CSS·탭 구조 손상 위험 없음

**방법 2 — placeholder 복원 후 치환**:
1. `.venv/bin/python generate.py {date}` 실행 → 쉘 재생성 (기존 HTML이 건강하면 Story 보존됨)
2. `_story.html`을 수정한 뒤 짧은 Python 스니펫으로 daily HTML의 `<!-- STORY_CONTENT_PLACEHOLDER -->` 를 치환

### 함정: `_inject_existing_story()` 외부 직접 호출 금지

`_inject_existing_story(path, new_html)`의 두 번째 인자는 **반드시 `<!-- STORY_CONTENT_PLACEHOLDER -->` 마커를 포함한 "새 HTML 템플릿 전체"**여야 한다. Story fragment만 넘기면 함수는 placeholder를 찾지 못하고 **fragment 자체를 `path` 파일에 통째로 덮어써서 대시보드·CSS·탭이 모두 사라진다.** 이 함수는 `generate.py` 내부에서만 쓰고, 외부에서 Story를 수정할 때는 위의 (B) 방법 1 또는 2를 사용할 것.

**과거 사고 사례 (2026-04-08)**: `_inject_existing_story('.../2026-04-08.html', story_html)`을 외부에서 호출해 960줄 daily HTML이 345줄 fragment로 덮어써진 사고 발생. 복구를 위해 generate.py 재실행 + placeholder 치환이 필요했음.

---

## 주입 후 검증 필수 — 보고서 작성 끝에 항상 실행

### (1) 구조 검증
- `{date}.html`이 `<!DOCTYPE html>`, `tab-story`, `tab-data`, `<style>` 블록을 모두 포함하는지 확인
- `{date}_story.html` 파일이 생성/갱신되었는지 확인
- 두 파일의 Story 내용이 동일한지(동기화) 확인
- 이전 영업일 `{prev_date}.html` 과 라인 수 비교 (수백 줄 차이 시 의심)

### (2) 필수 섹션 체크 — 모든 섹션이 Story 에 있어야 한다
- [ ] `<div class="story-hero">` — Story Hero (헤드라인 + 세션별 내러티브)
- [ ] `<div class="causal-chain">` — Causal Chain (원인 → 결과 체인)
- [ ] `<div class="session-grid">` — Session Grid (아시아/유럽/미국 3카드)
- [ ] `<div class="insight-grid">` — Insight Grid (4개 교육 카드)
- [ ] `<div class="risk-section">` + `<ul class="risk-items">` — Risk Section
- [ ] WTD/MTD 블록 (grid 2-pane, `<h3>` + `<ul>`)

> 실제 검증 스니펫:
> ```bash
> .venv/bin/python -c "
> import re
> html = open('output/summary/YYYY-MM/YYYY-MM-DD.html').read()
> required = ['story-hero','causal-chain','session-grid','insight-grid','risk-section','risk-items']
> missing = [c for c in required if f'class=\"{c}' not in html and f'class=\"... {c}' not in html]
> print('missing:', missing if missing else 'none ✓')
> "
> ```

### (3) CSS 클래스 검증 — Story 에서 쓰는 클래스가 `<style>` 에 정의돼 있는가

**이것은 매번 필수**. 과거 사례(2026-04-21): Claude 가 임의로 `key-insights`, `insight-title`, `risk-cards`, `risk-card high/medium/low` 같은 **존재하지 않는 클래스**를 써서 CSS 가 적용 안 된 채 발행됨.

**허용된 Story 전용 클래스 화이트리스트** (이외는 금지):
```
story-hero, story-text
causal-chain, cause-node, cause-arrow, node-label, node-title, node-detail, node-impact (up|down|flat)
session-grid, session-block (asia|europe|us), session-header, session-icon, session-name, session-time,
  session-verdict (verdict-up|verdict-down|verdict-flat), session-events, ev-time, session-kpi, s-kpi, s-kpi-label, s-kpi-value
insight-grid, insight-card, badge, metric-row, metric-item, metric-label, metric-value (up|down)
risk-section, risk-items, risk-item, risk-tag (high|med|low)
hl-up, hl-down, hl-warn, hl-accent
```

**커스텀 클래스 도입 금지**. 새 클래스가 정말 필요하면 먼저 `<style>` 블록에 정의 추가 후 사용.

> 실제 검증 스니펫:
> ```bash
> .venv/bin/python -c "
> import re
> html = open('output/summary/YYYY-MM/YYYY-MM-DD.html').read()
> css_block = re.search(r'<style>(.*?)</style>', html, re.DOTALL).group(1)
> story_block = re.search(r'id=\"tab-story\"(.*?)</div><!-- /tab-story', html, re.DOTALL).group(1)
> used = set(re.findall(r'class=\"([^\"]+)\"', story_block))
> used_classes = set(c for cs in used for c in cs.split())
> defined = set(re.findall(r'\.([a-z][a-z0-9_-]*)', css_block))
> undefined = [c for c in sorted(used_classes) if c not in defined]
> print('undefined:', undefined if undefined else 'none ✓')
> "
> ```

### (4) WTD/MTD 수치 일치 검증
- `history/market_data.csv` 에서 전주 금요일 종가 + 오늘 종가 두 값을 뽑아 직접 계산
- Story 에 쓴 수치와 일치하는지 확인 (소수점 2자리 허용 오차)
