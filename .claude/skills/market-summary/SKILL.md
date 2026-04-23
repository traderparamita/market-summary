---
name: market-summary
description: "market_summary 프로젝트의 Market Story(일간/주간/월간 시장 해설) 작성 스킬. 해당 날짜의 _data.json과 웹 검색을 기반으로 시간순 인과관계가 정확한 시장 해설을 작성하고 HTML에 주입한다. 사용 시점: 일간/주간/월간 보고서의 Story 탭을 작성·수정할 때, '4/8 스토리 써줘', '이번 주 주간 스토리 작성', '3월 월간 스토리' 같은 요청이 들어올 때."
argument-hint: "[target_date: YYYY-MM-DD] [period: daily|weekly|monthly]"
metadata:
  author: lifesailor
  version: "1.1.0"
---

# Market Story 작성 스킬

`market_summary` 프로젝트의 일간/주간/월간 Market Story를 작성한다. **Data Dashboard는 `generate.py`가 만들고, Story만 Claude가 작성한다.** 이 스킬은 작성 규칙·절차·주입 방법을 담는다.

## When to Use

- 사용자가 특정 날짜의 일간/주간/월간 **Market Story** 작성을 요청할 때
- `/market-full` 커맨드의 일부로 호출될 때 (Step 3, 5, 7)
- 기존 Story를 검증·수정할 때

**When NOT to use**: 데이터 수집이나 HTML 대시보드 생성만 필요한 경우 → `/market-data` 커맨드 사용

## 프로젝트 위치

```
/Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/
├── output/summary/YYYY-MM/YYYY-MM-DD.html          # 일간 보고서 (Story 주입 대상)
├── output/summary/YYYY-MM/YYYY-MM-DD_data.json     # 일간 원시 데이터 (Story 입력)
├── output/summary/YYYY-MM/YYYY-MM-DD_story.html    # 일간 Story 별도 저장
├── output/summary/weekly/YYYY-WNN.html             # 주간 보고서
├── output/summary/weekly/YYYY-WNN_story.html       # 주간 Story
├── output/summary/monthly/YYYY-MM.html             # 월간 보고서
└── output/summary/monthly/YYYY-MM_story.html       # 월간 Story
```

---

## 핵심 규칙 (반드시 준수)

### 1. Forward Looking 금지

- **일간**: 보고서 날짜 다음날 08:00 KST 이전까지의 정보만 사용
- **주간**: 해당 주 금요일(또는 마지막 영업일)까지의 정보만 사용
- **월간**: 해당 월 마지막 영업일까지의 정보만 사용
- 이후 날짜의 사건/데이터/결과를 **절대** 참조하지 않는다
- 허용: "~할 수 있다", "~가능성이 있다" (분석·전망)
- 금지: "이후 실제로 ~했다", "~의 서막이었다" (사후 참조)

### 2. 08:00 KST 생성 시점 기준

- 보고서는 **매일 08:00 KST**에 생성된다고 가정
- 예: 2026-04-07 보고서 → **2026-04-08 08:00 KST**에 생성
- 이 시점 기준으로 사용 가능한 데이터:
  - 4/7 아시아·유럽·미국 세션 전체 (이미 마감)
  - 4/8 아시아 프리마켓 뉴스 (08시 이전만)
  - 4/7까지의 가격 데이터 (`_data.json`)
- **사용 불가**: 4/8 09시 이후 아시아 장중, 유럽/미국 세션 데이터

### 3. 세션별 마감 시각 (KST) — 세션 간 미래 참조 금지

| 세션 | 시장 | 마감 시각 |
|------|------|----------|
| 아시아 | KOSPI | 15:30 |
| 아시아 | Nikkei | 15:00 |
| 아시아 | Shanghai | 16:00 |
| 유럽 | STOXX/DAX/CAC | 01:30 (서머타임 00:30) |
| 미국 | S&P/NASDAQ | 06:00 (서머타임 05:00) |

- **아시아 세션 서술**: 같은 날 유럽/미국 이벤트 참조 금지
- **유럽 세션 서술**: 유럽 마감 이후 발생한 미국 이벤트 참조 금지
- **미국 세션 서술**: 같은 날 아시아/유럽 참조 가능 (시간순 OK)

**흔한 위반**:
- "유럽 시장은 유가 급락을 소화하며 하락" — 유가 급락이 미국 세션에 일어났다면 위반
- "KOSPI는 트럼프 관세 유예 소식에 반등" — 발표가 미국 세션이었다면 KOSPI 마감 이후

### 4. 인과관계 방향 (과거 → 현재)

- **금지**: "월요일의 하락은 수요일 대반등의 서막이었다" (월요일 시점에서 수요일을 알 수 없음)
- **금지**: "이 하락은 시작에 불과했다" (미래 하락 암시)
- **금지**: "~의 전초전이었다", "~을 예고하는 듯했다" (사후적 프레이밍)
- **허용**: "수요일은 월·화요일의 과매도를 되돌리는 반등이었다" (과거 참조)
- **허용**: "이 수준이 지속될 경우 추가 조정 가능성" (전망)

### 5. 주간/월간 내 일간 간 미래 참조 금지

- 전체 기간 요약은 허용 (예: "롤러코스터 같은 한 주")
- **특정 날짜를 설명할 때 그 날짜 이후 이벤트를 원인·맥락으로 사용 금지**
- 금지: "4/2의 유가 폭등을 고려하면 3/30의 하락은 시작에 불과했다"
- 허용: 전체 주를 시간순으로 나열하며 각 날짜의 팩트를 기술

### 6. 요일·휴일 정확성

- **날짜와 요일이 정확히 일치하는지 반드시 검증**. Claude는 요일을 자주 틀린다.
- `_data.json`의 `holiday` 필드로 KOSPI/KOSDAQ 휴장일 확인
- 한국 공휴일: 삼일절, 광복절, 추석, 설날, 대체공휴일
  - 예: 2026-03-01은 일요일 → 대체공휴일은 3/2 월요일
- 미국 공휴일: Presidents' Day, Memorial Day, Thanksgiving, Independence Day 등
- **금지**: "금요일 발표된 고용지표"라고 쓰기 전에 실제 금요일인지 확인

### 7. 고점·저점 표현 전 반드시 CSV 검증

"사상 최고치", "연내 신고점", "YTD 최고", "52주 고점" 등 **기간 고점·저점 표현은 `history/market_data.csv`를 직접 조회해 검증한 후에만** 사용한다.

**검증 절차** (고점 주장 전 필수 실행):

```bash
# 예: KOSPI 연내 신고점 주장 전
grep "EQ_KOSPI" history/market_data.csv | grep "^2026" | sort | awk -F',' '{print $1, $5}' | sort -k2 -rn | head -5
```

- 해당일 종가가 조회 결과 **1위**일 때만 "연내 신고점" 사용
- 1위가 아니면 **"4월 신고점"**, **"월간 최고치"**, **"최근 N일 최고치"** 등 실제로 맞는 범위로 축약
- `_data.json`의 spark·YTD·weekly·monthly 필드는 **상대 변동률**이므로 고점 증명 불가
- verdict 배지·causal node·헤드라인 어디에 쓰든 동일 규칙 적용

**흔한 오류 패턴**:
- KOSPI +2%대 랠리 → "연내 신고점" (❌ — 2월 고점이 더 높을 수 있음)
- YTD +8% → "사상 최고치" (❌ — YTD 수익률과 절대 고점은 무관)
- 최근 급등 → "역대 최고" (❌ — 반드시 전체 시계열 확인)

### 8. Story Hero 세션 간 `<br><br>` 여백

- `<div class="story-hero">` 내부 `<div class="story-text">`에서 **아시아 → 유럽 → 미국 세션 문단을 `<br><br>`로 분리**
- 단일 `<br>`만 쓰면 세션이 한 덩어리로 붙어 가독성이 떨어진다
- 세션 도입부(서두 → 첫 세션)와 세션 종료 후(마지막 세션 → VIX/마무리 단락)에도 `<br><br>` 유지
- Session Grid 영역(`session-grid`)은 CSS로 이미 분리돼 있어 불필요. **Story Hero 텍스트 블록에만 해당**

---

## 일간 Story 작성 절차

### Step 1: 입력 확인

```
output/summary/{YYYY-MM}/{YYYY-MM-DD}_data.json  # 해당일 가격·변동률 데이터
output/summary/{YYYY-MM}/{YYYY-MM-DD}.html       # 주입 대상 HTML (이미 존재)
```

- `_data.json`의 `holiday` 필드, 각 자산의 종가/변동률 확인
- KOSPI/KOSDAQ 휴장일이면 해당 사실을 명시하고 Story 작성

### Step 2: 시간순 웹 데이터 수집

**반드시 시간 순서로** 수집:

1. **아시아 세션** (09:00~15:30 KST): 한국/일본/중국 시장 + 경제지표 + 아시아 지정학
2. **유럽 세션** (16:00~01:30 KST): 유럽 시장 + ECB/BOE 발언 + 유럽 경제지표
3. **미국 세션** (22:30~06:00 KST): 미국 경제지표 + Fed 발언 + 기업 실적 + 장중 흐름

**검색 시 주의**:
- 쿼리에 **정확한 날짜**를 넣어 미래 데이터 차단 (`"April 7 2026"` 같은 식)
- 당일 09시 이후 장중 데이터 검색 금지
- 훅(`PreToolUse WebSearch|WebFetch`)이 자동 검증하므로 block되면 쿼리 수정

### Step 3: Story 작성

Story는 HTML 섹션으로 구성된다. 기존 일간 `_story.html`을 Read로 확인해 구조 파악 후 작성.

표준 섹션:
- **Headline**: 하루를 한 문장으로
- **Narrative**: 아시아 → 유럽 → 미국 순서의 시간순 서사
- **Causal Chain**: 선행 세션이 후행 세션에 어떤 영향을 미쳤는지
- **Weekly & Monthly Progress (WTD/MTD)**: 주간·월간 누적 진행 상황 요약 (아래 Step 3-1 참조)
- **Key Insights**: 2~4개의 핵심 관찰
- **Risks**: 2~3개의 리스크 요인 (전망 OK, 사후 참조 X)

#### Step 3-1: Weekly & Monthly Progress 단락 작성

주간/월간 Story는 **마지막 영업일에만** 작성되므로, 일간 Story 안에 WTD(Week-to-Date)·MTD(Month-to-Date) 한 단락씩을 포함해 주 중간에도 누적 흐름을 볼 수 있게 한다.

**데이터 소스**: ⚠ `_data.json`의 `weekly` 필드는 **롤링 7일** 기준이라 WTD 와 다릅니다. **직접 계산해야** 합니다.

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

### Step 4: HTML 주입

#### (A) 신규 일간 생성 — `generate.py`가 자동 처리

`.venv/bin/python generate.py {date}` 실행 시 내부적으로 `_inject_existing_story()`가 호출되어 Story 탭 placeholder 처리와 `_story.html` 저장까지 모두 자동이다. **외부에서 이 함수를 직접 호출할 필요 없다.**

#### (B) 이미 존재하는 Story를 수정할 때

**방법 1 (권장) — `tab-story` 블록 직접 Edit**:
1. `output/summary/YYYY-MM/YYYY-MM-DD.html`에서 `<div id="tab-story" class="tab-panel">` ~ `</div><!-- /tab-story -->` 사이 블록을 Edit 도구로 교체
2. 같은 내용으로 `output/summary/YYYY-MM/YYYY-MM-DD_story.html`도 Edit (두 파일 동기화)
- 장점: 대시보드·CSS·탭 구조 손상 위험 없음

**방법 2 — placeholder 복원 후 치환**:
1. `.venv/bin/python generate.py {date}` 실행 → 쉘 재생성 (기존 HTML이 건강하면 Story 보존됨)
2. `_story.html`을 수정한 뒤 짧은 Python 스니펫으로 daily HTML의 `<!-- STORY_CONTENT_PLACEHOLDER -->` 를 치환

#### 함정: `_inject_existing_story()` 외부 직접 호출 금지

`_inject_existing_story(path, new_html)`의 두 번째 인자는 **반드시 `<!-- STORY_CONTENT_PLACEHOLDER -->` 마커를 포함한 "새 HTML 템플릿 전체"**여야 한다. Story fragment만 넘기면 함수는 placeholder를 찾지 못하고 **fragment 자체를 `path` 파일에 통째로 덮어써서 대시보드·CSS·탭이 모두 사라진다.** 이 함수는 `generate.py` 내부에서만 쓰고, 외부에서 Story를 수정할 때는 위의 (B) 방법 1 또는 2를 사용할 것.

**과거 사고 사례 (2026-04-08)**: `_inject_existing_story('.../2026-04-08.html', story_html)`을 외부에서 호출해 960줄 daily HTML이 345줄 fragment로 덮어써진 사고 발생. 복구를 위해 generate.py 재실행 + placeholder 치환이 필요했음.

### 주입 후 검증 필수 — 보고서 작성 끝에 항상 실행

#### (1) 구조 검증
- `{date}.html`이 `<!DOCTYPE html>`, `tab-story`, `tab-data`, `<style>` 블록을 모두 포함하는지 확인
- `{date}_story.html` 파일이 생성/갱신되었는지 확인
- 두 파일의 Story 내용이 동일한지(동기화) 확인
- 이전 영업일 `{prev_date}.html` 과 라인 수 비교 (수백 줄 차이 시 의심)

#### (2) 필수 섹션 체크 — 모든 섹션이 Story 에 있어야 한다
- [ ] `<div class="story-hero">` — Story Hero (헤드라인 + 세션별 내러티브)
- [ ] `<div class="causal-chain">` — Causal Chain (원인 → 결과 체인)
- [ ] `<div class="session-grid">` — Session Grid (아시아/유럽/미국 3카드)
- [ ] `<div class="cross-asset">` + `<div class="af-map">` — **Cross-Asset Flow Map (자산 간 연결)**
- [ ] `<div class="insight-grid">` — Insight Grid (4개 교육 카드)
- [ ] `<div class="risk-section">` + `<ul class="risk-items">` — Risk Section
- [ ] WTD/MTD 블록 (grid 2-pane, `<h3>` + `<ul>`)

> 실제 검증 스니펫:
> ```bash
> .venv/bin/python -c "
> import re
> html = open('output/summary/YYYY-MM/YYYY-MM-DD.html').read()
> required = ['story-hero','causal-chain','session-grid','cross-asset','af-map','insight-grid','risk-section','risk-items']
> missing = [c for c in required if f'class=\"{c}' not in html and f'class=\"... {c}' not in html]
> print('missing:', missing if missing else 'none ✓')
> "
> ```

#### (3) CSS 클래스 검증 — Story 에서 쓰는 클래스가 `<style>` 에 정의돼 있는가

**이것은 매번 필수**. 과거 사례(2026-04-21): Claude 가 임의로 `key-insights`, `insight-title`, `risk-cards`, `risk-card high/medium/low` 같은 **존재하지 않는 클래스**를 써서 CSS 가 적용 안 된 채 발행됨.

**허용된 Story 전용 클래스 화이트리스트** (이외는 금지):
```
story-hero, story-text
causal-chain, cause-node, cause-arrow, node-label, node-title, node-detail, node-impact (up|down|flat)
session-grid, session-block (asia|europe|us), session-header, session-icon, session-name, session-time,
  session-verdict (verdict-up|verdict-down|verdict-flat), session-events, ev-time, session-kpi, s-kpi, s-kpi-label, s-kpi-value
cross-asset, sub, af-map, af-node, af-arrow, af-node-title, af-node-value, af-node-chg (up|down), arr, lbl
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

#### (4) WTD/MTD 수치 일치 검증
- `history/market_data.csv` 에서 전주 금요일 종가 + 오늘 종가 두 값을 뽑아 직접 계산
- Story 에 쓴 수치와 일치하는지 확인 (소수점 2자리 허용 오차)

---

## 주간 Story 작성 절차

### Step 1: 해당 주 일간 Story 수집

- ISO 주차 → 해당 주의 영업일 나열 (월~금, 공휴일 제외)
- 각 날짜의 `output/summary/YYYY-MM/YYYY-MM-DD_story.html`을 **모두 Read**
- 각 날짜의 `_data.json`도 필요 시 참조 (수치 확인)

### Step 2: 주간 관점 종합

- 한 주를 관통하는 테마 추출 (예: "관세 불확실성에 휩쓸린 한 주")
- 각 날짜의 주요 이벤트를 시간순으로 배치
- 주간 누적 수익률, 고점·저점, 최대 변동일 식별
- **주의**: 특정 날짜 서술 시 그 날짜 이후 이벤트로 설명하지 말 것

### Step 3: HTML 주입

- 대상: `output/summary/weekly/YYYY-WNN.html`
- 주간 보고서가 아직 없으면 먼저 `.venv/bin/python generate_periodic.py {year}`로 생성
- 일간과 동일하게 `_inject_existing_story()` 사용, `_story.html` 저장 확인

---

## 월간 Story 작성 절차

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

### Step 3: HTML 주입

- 대상: `output/summary/monthly/YYYY-MM.html`
- 월간 보고서가 없으면 `.venv/bin/python generate_periodic.py {year}` 선행
- 일간·주간과 동일한 주입 방식

---

## CS Story 작성 절차

CS(Customer Success) 관점 스토리는 **기존 Market Story를 재작성** 하여 수치를 최대한 제거하고 맥락·흐름 위주로 서술한다. 일반 Story가 투자 의사결정용이라면 CS Story 는 고객에게 시장 상황을 "이야기로" 전달하는 용도다.

### 전제

- **선행 조건**: 해당 날짜의 일반 Story 가 이미 `_story.html` 에 존재
- **대상 탭**: `<div id="tab-cs">` / placeholder `<!-- CS_STORY_PLACEHOLDER -->`
- **별도 파일 저장**: `YYYY-MM-DD_cs.html` (generate.py 가 sibling 으로 자동 저장)
- **적용 범위**: 일간·주간·월간 모두 동일 패턴

### Step 1: 기존 Story 읽기

`output/summary/YYYY-MM/YYYY-MM-DD_story.html` 을 Read. 사실관계(이벤트·종목·정책·인과)는 그대로 유지한다. 시간순 인과·세션 간 forward-looking 금지 규칙은 일반 Story 와 동일하게 적용된다.

### Step 2: 수치 제거 규칙

**제거 대상**:
- 퍼센트 수치 (`+0.46%`, `-1.22%`)
- 가격·지수 숫자 (`1,224,000원`, `6,417.93`, `59,586`)
- 시가총액·거래량·OHLC 숫자
- 섹터별 · 종목별 퍼센트 나열 (`중공업 +4.05%, 산업재 +2.34%`)
- KPI 테이블·metric-item 블록 내부 숫자 (UI 블록 자체를 들어내고 서술로 대체)

**유지 가능** (맥락상 필수일 때만):
- 심리적 앵커가 되는 정수 이정표: "10거래일 연속", "5,000조 돌파", "사상 최고치" (숫자 없는 표현 OK)
- 날짜·요일
- 종목명·지수명·ETF 티커·이벤트명·정책 키워드·인명

**대체 표현 가이드**:
| 수치 중심 (원본) | 맥락 중심 (CS) |
|-----------------|---------------|
| KOSPI +0.46%(6,417.93)로 사상 최고치 | KOSPI 가 사상 최고치를 이틀째 경신 |
| SK하이닉스 +4.97%(1,224,000원) 급등 | SK하이닉스가 다시 강하게 반등하며 주도주 입지를 굳혔습니다 |
| 닛케이 +0.40%, 상하이 +0.52%, 항셍 -1.22% | 닛케이·상하이는 강세, 항셍은 약세로 아시아 내 차별화 |
| VIX 18.3 → 16.5 (-9.8%) | VIX 가 한 단계 내려앉으며 변동성 경보가 풀렸습니다 |

### Step 3: 톤 조정

- **흐름-앵커로 문장 연결**: "전일 상승세를 이어받아 아시아 장에서 한국이 다시 앞장섰습니다"
- **비유·스토리텔링 허용**: "랠리가 반도체에서 전통 산업으로 바통을 넘기는 모습"
- **전문 용어는 짧은 풀이**: "브레드스(breadth, 상승 종목 수)", "레인지 상단(최근 고점 부근)"
- **의사결정 권유 금지**: "비중 확대 권장", "매수 타이밍" 같은 표현은 쓰지 않는다. 관찰·설명만.

### Step 4: HTML 주입

**HTML 골격 — cs-hero + cs-section 조합** (Market Story 의 `.story-hero` 와 시각적으로 구분되는 오렌지 계열, CSS 는 tab-cs 블록 안에 인라인 포함해 과거 보고서에도 포터블):

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
  <h3>{국기 + 주요 테마 1}</h3>
  <p>{맥락·배경·의미}</p>
</div>

<!-- 필요한 만큼 cs-section 블록 반복 -->

<div class="cs-section">
  <h3>📅 이번 주·이번 달 관점</h3>
  <p>{WTD/MTD 맥락 서술}</p>
  <p class="cs-footer">CS Story 는 Market Story 를 수치 대신 맥락·흐름 중심으로 재구성한 고객 설명용 버전입니다. 구체적 수치는 Market Story / Data Dashboard 탭을 참고하세요.</p>
</div>
```

**절대 쓰지 말 것**: `.story-section`, `.story-content` — Market Summary HTML 에 정의돼 있지 않은 클래스 (sector-country 보고서의 CSS 이므로 여기선 무스타일 상태가 된다).

**주입 단계**:

1. **일간**: `output/summary/YYYY-MM/YYYY-MM-DD.html` Read → `<div id="tab-cs" class="tab-panel">` ~ `</div><!-- /tab-cs -->` 블록 Edit → 같은 내용으로 `YYYY-MM-DD_cs.html` Edit (동기화)
2. **주간/월간**: 같은 패턴 (`weekly/YYYY-WNN.html` + `_cs.html`, `monthly/YYYY-MM.html` + `_cs.html`).

placeholder (`<!-- CS_STORY_PLACEHOLDER -->`) 가 남아있는 HTML 이면 `generate.py` / `generate_periodic.py` 를 한 번 재실행해 탭 구조를 최신화한 뒤 주입한다. `_inject_existing_story()` 외부 직접 호출은 여전히 금지 — Story 탭 규칙과 동일.

### 자가 검증 체크리스트

- [ ] 기존 Story 원본의 사실관계(이벤트·인과·시간순)를 그대로 전달하는가?
- [ ] 퍼센트·가격·거래량·OHLC 숫자가 본문에서 사라졌는가? (의도적 심리 앵커는 예외)
- [ ] 종목명·지수명·날짜·요일·이벤트명은 유지되었는가?
- [ ] 세션 간 forward-looking 금지 규칙을 그대로 지켰는가? (원본에 있다면 그 부분이 잘못된 것 — 원본부터 수정)
- [ ] 톤이 "설명·관찰" 인가, "권유·전망" 인가? 후자면 다시 작성.
- [ ] `_cs.html` sibling 파일이 생성·갱신되었는가?

---

## 훅(Hook) 연동

`.claude/settings.json`에 세 가지 훅이 이미 설정되어 있다:

1. **PreToolUse WebSearch|WebFetch**: 시간순 수집 규칙 강제, forward-looking 쿼리 block
2. **PreToolUse Edit|Write**: Story 작성 전 시간 규칙 주입
3. **PostToolUse Write|Edit**: 작성 후 4단계 검증 (forward-looking, 세션 간 참조, 인과방향, 기간 내 참조)

**훅이 block하면**: 사유를 읽고 해당 문장을 수정. 훅과 싸우지 말 것 — 훅이 틀렸다고 느끼면 사용자에게 확인 요청.

---

## 자가 검증 체크리스트 (작성 완료 전 실행)

- [ ] `_data.json`의 holiday 필드와 휴장일 서술이 일치하는가?
- [ ] 날짜와 요일이 달력 기준으로 정확한가?
- [ ] 아시아 세션 서술에 같은 날 유럽/미국 이벤트가 섞이지 않았는가?
- [ ] 유럽 세션 서술에 유럽 마감 이후 미국 이벤트가 섞이지 않았는가?
- [ ] 인과관계가 모두 과거 → 현재 방향인가?
- [ ] "서막", "시작에 불과", "전초전" 같은 사후적 표현이 없는가?
- [ ] (주간/월간) 특정 날짜 설명에 그 날짜 이후 이벤트가 원인으로 쓰이지 않았는가?
- [ ] (일간) WTD/MTD 단락에 "N/M 영업일 경과" 표기가 있고, 수치가 `_data.json`의 `weekly`/`monthly` 필드와 일치하는가?
- [ ] "연내 신고점", "YTD 최고", "52주 고점", "사상 최고" 등 기간 고점 표현을 쓴 경우, `history/market_data.csv`를 실제 조회해 해당일 종가가 해당 기간 1위인지 확인했는가?
- [ ] `_story.html` 파일이 정상 생성·갱신되었는가?