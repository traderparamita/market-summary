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

**데이터 소스**: `_data.json`의 각 자산 `weekly`, `monthly` 필드 (이미 누적 수익률 계산되어 있음)

**작성 형식** (예시):

```html
<h3>주간 누적 (W15, 3/5 영업일 경과)</h3>
<ul>
  <li>핵심 지수: KOSPI +1.8%, S&amp;P500 −0.6%, NASDAQ −1.2%, DXY +0.4%</li>
  <li>이번 주 흐름: 월요일 중국 PMI 쇼크 이후 미국·유럽 약세 지속, 한국·일본은 반등 우위</li>
</ul>

<h3>월간 누적 (4월, 7/20 영업일 경과)</h3>
<ul>
  <li>핵심 지수: KOSPI +3.2%, S&amp;P500 +0.4%, Gold +2.1%, WTI −5.8%</li>
  <li>월초 이후 테마: 관세 불확실성 완화 기대 + 한국 반도체 실적 모멘텀 유입</li>
</ul>
```

**규칙**:
- **경과 영업일 수 표기 필수**: "3/5 영업일 경과", "7/20 영업일 경과" 같이 중간본임을 명시. 독자가 완결본으로 오해하지 않도록.
- **수치는 `_data.json`에서**: 직접 계산 말고 각 자산의 `weekly`/`monthly` 필드 그대로 사용
- **테마 한 줄**: 일간 Narrative와 중복 피하며 주/월 전체 관점에서 한 문장 압축
- **Forward looking 금지는 동일하게 적용**: 오늘 이후 이벤트 참조 금지
- **마지막 영업일의 일간 Story**: 이 단락을 작성하되 "마지막 영업일"임을 표기 (예: "W15, 5/5 영업일 경과 — 주간 마감"). 별도 주간 Story가 같은 날 작성되므로 이 단락은 간결하게 유지.

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

### 주입 후 검증 필수
- `{date}.html`이 `<!DOCTYPE html>`, `tab-story`, `tab-data`, `<style>` 블록을 모두 포함하는지 확인
- `{date}_story.html` 파일이 생성/갱신되었는지 확인
- 두 파일의 Story 내용이 동일한지(동기화) 확인
- 라인 수 감이 안 잡히면 이전 영업일 `{prev_date}.html`과 라인 수를 비교 (수백 줄 차이가 나면 의심)

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
- [ ] `_story.html` 파일이 정상 생성·갱신되었는가?