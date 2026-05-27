---
name: asia-weekly
description: "market_summary 프로젝트의 아시아 중심 주간 시황 보고서 작성 스킬. history/아시아종목.xlsx 유니버스(중국·일본·인도·대만·홍콩·베트남·호주·인니 180종목)와 history/market_data.csv를 기반으로, 주간(월~금) 변동률·국가별 가중평균·반도체 디커플링·통화·매크로를 분석하여 6탭 HTML 보고서를 생성한다. 사용 시점: 'W21 아시아 주간 보고서 만들어줘', '아시아 시황 주간', '/asia-weekly YYYY-MM-DD' 같은 요청이 들어올 때."
argument-hint: "[target_date: YYYY-MM-DD] (해당 주 임의의 영업일. 생략 시 직전 금요일)"
metadata:
  author: lifesailor
  version: "1.0.0"
---

# Asia Weekly Brief 작성 스킬

`market_summary` 프로젝트의 **아시아 중심 주간 시황 보고서**를 작성한다. 기존 `market-summary` 스킬(글로벌 일·주·월간)과 별도로 운영되며, **아시아 종목 유니버스(history/아시아종목.xlsx) + 국가별 디스퍼션**에 초점을 맞춘다.

## 출력물

```
output/summary/weekly/YYYY-WNN_asia.html       # 메인 보고서 (6탭)
```

탭 구성: **Asia Story · Country Drilldown · Themes · Data · Outlook (다음 주) · Sources**

## 기준 데이터

| 데이터 | 위치 | 역할 |
|---|---|---|
| `history/아시아종목.xlsx` | 종목 유니버스 (180개, 9개 시트) | 종목명·티커·국가·비중 |
| `history/market_data.csv` | 일별 가격 시계열 (185지표) | 주간 변동률 계산 |
| `output/securities/digest/digest_*.html` | 미래에셋증권 주간 다이제스트 | 중국·일본·아시아 인사이트 보강 |
| `output/summary/weekly/YYYY-WNN.html` | 글로벌 주간 보고서 | 매크로·환율·금리 일관성 참조 |

---

## When to Use

- 사용자가 **"아시아 주간 보고서"**, **"W## 아시아"**, **"아시아 시황 주간"** 요청 시
- `/asia-weekly YYYY-MM-DD` 슬래시 명령으로 호출될 때
- launchd 자동화에서 매주 일요일 19:30 KST 호출될 때 (collect_weekly 직후)

**When NOT to use**:
- 글로벌 주간 보고서(WTD 전체) → `market-summary` 스킬 + `/market-full`
- 일간 보고서 → `/market-data` + `market-summary`
- 단일 종목 분석 → `mali-etf-analysis` 또는 `finance-report`

---

## 워크플로우 — 4 단계

### Step 0. 캘린더 검증 (필수)

```bash
.venv/bin/python scripts/calendar_check.py $ARGUMENTS --week W##
```

대상 주의 영업일 5개를 출력해 검증한다. 절대로 요일·주차를 추측하지 않는다. **공휴일이 끼면 영업일 윈도우가 단축**된다 (예: 어린이날 5/5 → 4영업일).

### Step 1. 스크립트로 데이터 + HTML 스켈레톤 생성

```bash
.venv/bin/python scripts/generate_asia_weekly.py YYYY-MM-DD
```

이 스크립트가 자동으로 처리:
- xlsx ↔ CSV 종목명 매칭 (현재 65종목 매칭, W21부터 180종목 풀 커버 목표)
- 5/8(직전 금) → 5/15(주 마지막 영업일) WTD % 계산
- 국가별 단순·가중 평균
- 지수 8개·환율 5개·MSCI EM 변동률
- KPI 스트립·Data 탭 표 자동 채움
- Story·Country·Themes·Outlook·Sources 탭은 **placeholder만 삽입**
- 부산물: `output/summary/weekly/YYYY-WNN_asia_data.json` (Claude가 Story 작성 시 참조)

### Step 2. Claude가 본문 5탭 작성 (서술 부분)

`_data.json`을 읽어 다음 5탭에 본문을 주입한다. **각 탭의 작성 규칙은 `references/story-template.md`** 참조.

**작성 순서 권장**: Story(메인 hero + 인과체인 + 인사이트) → Country(국가별 드릴다운) → Themes(횡단 주제) → Outlook(다음 주 시나리오) → Sources(미래에셋증권 디지스트 링크 + 외부 참고).

### Step 3. 검증 + 배포

```bash
# 1) 구조 검증
echo '{"tool_input":{"file_path":"output/summary/weekly/YYYY-WNN_asia.html","content":""}}' | \
  .venv/bin/python .claude/hooks/post_edit_write_structure_guard.py

# 2) 수치 검증
.venv/bin/python scripts/verify_report_numbers.py output/summary/weekly/YYYY-WNN_asia.html

# 3) 인덱스 갱신 (필요 시)
.venv/bin/python scripts/generate_weekly_index.py  # 있을 경우

# 4) 배포 (사용자 승인 후)
/market-deploy
```

---

## 핵심 규칙 (반드시 준수)

### 0. 문체: 존댓말(합니다체)

market-summary 스킬과 동일. **"~했습니다, ~됐습니다, ~입니다"**. 반말 금지.

### 1. Forward Looking 금지

- 보고서는 해당 주 **마지막 영업일(금요일 또는 단축 시 목요일) 종가 이후, 다음 주 첫 영업일 08:00 KST 이전까지의 정보**만 사용
- 다음 주 발생할 이벤트의 **결과**를 사후 참조 금지
- 허용: "~할 수 있다", "~가능성이 있다", "**Outlook 탭**의 시나리오/리스크 (forward 화이트리스트)"
- 금지: "이후 실제로 ~했다", "~의 서막이었다"

### 2. 인과관계 방향

- **금지**: "월요일의 하락은 금요일 폭락의 서막이었다" (월요일 시점에서 금요일을 알 수 없음)
- **허용**: "수요일 반등은 월·화의 과매도를 되돌리는 회복이었다" (과거 참조)

### 3. 종목명 표기 — xlsx ↔ CSV 매칭

- 보고서 본문에서는 **xlsx의 종목명**을 그대로 사용 (예: "TSMC TW", "Cambricon Tech", "Mizuho FG")
- 한자/현지어 종목은 영문명 + 괄호 보조 (예: "비야디(BYD)", "캠브리콘(Cambricon Tech)")
- 미매칭 종목은 본문에 등장하더라도 **수치 인용 금지** (Sources 탭에 한계 명시)

### 4. 국가별 가중평균 계산

```
weighted_avg = Σ(비중 × WTD%) / Σ(비중)
simple_avg = mean(WTD%)
```

두 값 모두 보고서에 명시 (예: "중국: 가중 +1.02%, 단순 +3.15%"). 디스퍼션이 큰 한 주는 두 값이 크게 갈리므로 함께 보여주는 게 중요.

### 5. 한국 처리 — 컨텍스트만 (Top 50은 별도 시스템)

아시아종목.xlsx 유니버스에는 **한국이 포함되지 않는다**. 하지만 한국 시장의 큰 이벤트(코스피 폭락, 정책 충격 등)는 아시아 자금 흐름의 1차 변수이므로 **참고용 컨텍스트로 1개 섹션 (`country-section kr`)**을 둔다. 한국 종목 변동률은 글로벌 weekly 보고서(`2026-W##.html`)를 참조.

### 6. CSS 화이트리스트 (구조 검증 통과 필수)

`tab-story` 블록 안에서는 다음 클래스만 사용 가능:
- **Story Hero**: `story-hero`, `story-text`, `hl-up`, `hl-down`, `hl-warn`, `hl-accent`
- **Causal Chain**: `causal-chain`, `cause-node`, `cause-arrow`, `node-label`, `node-title`, `node-detail`, `node-impact`, `up`, `down`, `flat`
- **Insight Grid**: `insight-grid`, `insight-card`, `badge`, `metric-row`, `metric-item`, `metric-label`, `metric-value`
- 그 외 layout: `tab-panel`, `tab-content`, `tab-nav`, `tab-btn`, `card`, `metric`, `kpi`, `active`

**다른 탭(country, themes, data, outlook, sources)**에서는 자유로운 클래스 사용 가능 (구조 검증은 tab-story 블록만 검사).

### 7. 필수 섹션 (구조 검증)

전체 파일에 다음 5개 마커가 반드시 존재:
- `class="story-hero"` (탭 story)
- `class="causal-chain"` (탭 story)
- `class="insight-grid"` (탭 story)
- `class="risk-section"` (탭 outlook의 리스크 박스)
- `class="risk-items"` (탭 outlook의 리스크 목록)

주간이므로 `session-grid`는 **불필요** (skip 대상).

---

## 라우팅 — 작업별 references

| 작업 | 참조 파일 |
|---|---|
| 국가별 컨텍스트·핵심 종목 정보 | `references/countries.md` |
| 6탭 HTML 구조·Story 작성 톤 | `references/story-template.md` |
| 시간 정확성·인과관계 규칙 | `../market-summary/SKILL.md` §1~§6 (공통 적용) |

---

## 자동화 (launchd)

- 매주 **일요일 19:30 KST** `com.lifesailor.asia-weekly.plist` 가 `collect_weekly` 완료 후 트리거
- 스크립트: `scripts/generate_asia_weekly.py {지난 주 금요일}`
- 출력: `output/summary/weekly/YYYY-WNN_asia.html` (스켈레톤 + 데이터)
- **Story 본문 작성은 Claude 수동** (또는 별도 `launchd_claude_invoke` 후속 작업)

---

## 한계 / 알려진 이슈

- **xlsx ↔ CSV 매칭율 36%** (현재) → W21부터 collectors 확장으로 100% 목표
- 홍콩·베트남·인니·호주는 비중이 작아 한 국가 섹션 < 10종목인 경우 다수
- USD/HKD·USD/IDR·USD/VND·USD/AUD 환율은 CSV에 없음 (USD/CNY·JPY·INR만 추적)
- 미·중 정상회담 등 매크로 이벤트 정보는 미래에셋증권 디지스트로 보강 (웹 검색은 훅 차단 빈번)

---

## 참고: market-summary와의 차이

| 항목 | market-summary | asia-weekly |
|---|---|---|
| **유니버스** | 글로벌 (KR50 + US50 + 매크로) | 아시아 180종목 (xlsx) |
| **기간** | 일/주/월 | 주 (월~금) |
| **초점** | 매크로·세션 인과·시간순 서술 | 국가별 디스퍼션·종목 디커플링·테마 |
| **탭 구성** | CS·PM·Weekly·Data·Macro·Sources | Story·Country·Themes·Data·Outlook·Sources |
| **자동화** | 일 18:50 + 화~금 06:50 KST | 일 19:30 KST (collect_weekly 직후) |
