---
name: market-summary
description: "market_summary 프로젝트의 Market Story(일간/주간/월간 시장 해설) 작성 스킬. 해당 날짜의 _data.json과 웹 검색을 기반으로 시간순 인과관계가 정확한 시장 해설을 작성하고 HTML에 주입한다. 사용 시점: 일간/주간/월간 보고서의 Story 탭을 작성·수정할 때, '4/8 스토리 써줘', '이번 주 주간 스토리 작성', '3월 월간 스토리' 같은 요청이 들어올 때."
argument-hint: "[target_date: YYYY-MM-DD] [period: daily|weekly|monthly]"
metadata:
  author: lifesailor
  version: "2.0.0"
---

# Market Story 작성 스킬

`market_summary` 프로젝트의 일간/주간/월간 Market Story를 작성한다. **Data Dashboard는 `generate.py`가 만들고, Story만 Claude가 작성한다.** 이 SKILL.md는 모든 Story 유형에 공통으로 적용되는 핵심 규칙과 라우팅을 담고, 워크플로우별 상세는 `references/` 에 분리되어 있다.

## When to Use

- 사용자가 특정 날짜의 일간/주간/월간 **Market Story** 작성을 요청할 때
- `/market-full` 커맨드의 일부로 호출될 때 (Step 3, 5, 7)
- 기존 Story를 검증·수정할 때

**When NOT to use**: 데이터 수집이나 HTML 대시보드 생성만 필요한 경우 → `/market-data` 커맨드 사용

## 프로젝트 위치

```
├── output/summary/YYYY-MM/YYYY-MM-DD.html          # 일간 보고서 (Story 주입 대상)
├── output/summary/YYYY-MM/YYYY-MM-DD_data.json     # 일간 원시 데이터 (Story 입력)
├── output/summary/YYYY-MM/YYYY-MM-DD_story.html    # 일간 Story 별도 저장
├── output/summary/weekly/YYYY-WNN.html             # 주간 보고서
├── output/summary/weekly/YYYY-WNN_story.html       # 주간 Story
├── output/summary/monthly/YYYY-MM.html             # 월간 보고서
└── output/summary/monthly/YYYY-MM_story.html       # 월간 Story
```

---

## 라우팅 — 작업별 references 가이드

| 작업 | 추가로 읽을 파일 |
|------|----------------|
| 일간 Story 작성/수정 | `references/daily.md` (+ 아시아 세션 종목 활용 시 `references/stocks-asia.md`) |
| 주간/월간/분기 Story 작성 | `references/weekly-monthly.md` (+ 일간 골격 참조 필요 시 `references/daily.md`) |
| CS Story 작성 (`tab-cs`) | `references/cs.md` |
| PM Story 회고 6 섹션 (`tab-pm`) | `references/pm.md` |
| PM Outlook (주간/월간/분기 forward 블록) | `references/pm-outlook.md` (+ `references/pm.md`) |
| Sources 탭 (`tab-sources`) | `references/sources.md` |

본 SKILL.md 의 핵심 규칙(아래 §1~§7) 은 **모든 워크플로우에 공통 적용** 되므로 어떤 references 를 읽든 함께 준수한다.

---

## 핵심 규칙 (반드시 준수, 모든 Story 공통)

### 0. 문체: 존댓말(합니다체)

- Market Story는 **항상 존댓말(~했습니다, ~됐습니다, ~입니다)**로 작성한다
- 반말(~했다, ~됐다, ~이다) 금지
- Session Grid의 `<li>` 이벤트 항목도 동일하게 존댓말 적용
- 예: "코스피는 +0.75%로 마감했습니다" (O) / "코스피는 +0.75%로 마감했다" (X)

### 1. Forward Looking 금지

- **일간**: 보고서 날짜 다음날 08:00 KST 이전까지의 정보만 사용
- **주간**: 해당 주 금요일(또는 마지막 영업일)까지의 정보만 사용
- **월간**: 해당 월 마지막 영업일까지의 정보만 사용
- 이후 날짜의 사건/데이터/결과를 **절대** 참조하지 않는다
- 허용: "~할 수 있다", "~가능성이 있다" (분석·전망)
- 금지: "이후 실제로 ~했다", "~의 서막이었다" (사후 참조)

> **예외**: PM Outlook 블록(`references/pm-outlook.md`) 은 forward 화이트리스트. 명시적 forward 영역 외에는 위 규칙 적용.

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

### 6. 요일·휴일 정확성 — 반드시 데이터로 검증

- **날짜와 요일이 정확히 일치하는지 반드시 검증**. Claude는 요일을 자주 틀린다.
- **Story 작성 전 필수 실행**:
  ```bash
  .venv/bin/python scripts/calendar_check.py YYYY-MM-DD
  ```
  출력에서 각 날짜의 요일·영업일·공휴일을 확인한 뒤에만 요일을 서술에 사용한다.
  주간 Story는 `--week W{N}`, 월간 Story는 `--month` 플래그를 추가한다.
- `_data.json`의 `holiday` 필드로 KOSPI/KOSDAQ 휴장일 확인
- 한국 공휴일: 삼일절, 광복절, 추석, 설날, 대체공휴일
  - 예: 2026-03-01은 일요일 → 대체공휴일은 3/2 월요일
- 미국 공휴일: Presidents' Day, Memorial Day, Thanksgiving, Independence Day 등
- **금지**: "금요일 발표된 고용지표"라고 쓰기 전에 실제 금요일인지 확인
- **금지**: 요일을 추측하는 것. 항상 `calendar_check.py` 출력 또는 `datetime.date` 결과에 기반

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

---

## 표기 규칙 (모든 Story 공통)

- 지수·종목·통화명은 한국어 단독 사용: `코스피`, `나스닥`, `금`, `달러/원`, `WTI유`
- 영문 약어도 한국어로: `사상 최고가`, `연초 대비`, `주간 대비`, `월간 대비`, `장단기 스프레드`
- 색상 컨벤션: 상승=빨간(`hl-up`), 하락=파란(`hl-down`) — 한국 주식창 기준

---

## 훅(Hook) 연동

`.claude/settings.json`에 세 가지 훅이 이미 설정되어 있다:

1. **PreToolUse WebSearch|WebFetch**: 시간순 수집 규칙 강제, forward-looking 쿼리 block
2. **PreToolUse Edit|Write**: Story 작성 전 시간 규칙 주입
3. **PostToolUse Write|Edit**: 작성 후 4단계 검증 (forward-looking, 세션 간 참조, 인과방향, 기간 내 참조)

**훅이 block하면**: 사유를 읽고 해당 문장을 수정. 훅과 싸우지 말 것 — 훅이 틀렸다고 느끼면 사용자에게 확인 요청.

---

## 글로벌 자가 검증 체크리스트 (작성 완료 전 실행)

워크플로우별 추가 체크리스트는 각 references 파일에 있다. 아래는 **모든 Story 에 공통 적용**되는 최종 점검:

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
