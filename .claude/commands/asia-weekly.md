---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD]  (해당 주 임의의 영업일. 생략 시 직전 금요일)"
description: "아시아 주간 시황 보고서: 종목 유니버스 추출 → 스켈레톤 생성 → Story 5탭 작성 → 검증 → 배포"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 아시아 주간 보고서: !`ls -t output/summary/weekly/*_asia.html 2>/dev/null | head -3`
- 최근 글로벌 주간 보고서: !`ls -t output/summary/weekly/2026-W*.html 2>/dev/null | grep -v "_asia\|_story\|_macro\|_pm\|_cs\|_sources" | head -3`
- 미래에셋증권 다이제스트: !`ls -t output/research/securities/digest_*.html 2>/dev/null | head -3`

## Your task

`market_summary` 프로젝트의 **아시아 중심 주간 시황 보고서** 생성 워크플로우를 순차 실행한다.

**대상 날짜**: $ARGUMENTS (생략 시 직전 금요일)

`asia-weekly` 스킬을 활성화해 작업을 수행한다. 상세 글쓰기 규칙·CSS 화이트리스트·국가별 컨텍스트는 스킬의 `references/` 디렉터리를 참조한다.

---

### Step 0. 캘린더 검증 (필수)

```bash
.venv/bin/python scripts/calendar_check.py $ARGUMENTS --week W##
```

- 출력된 영업일 5개를 확인. 절대 요일·주차를 추측하지 않는다.
- 한국 공휴일 끼면 영업일 단축 (예: 5/5 어린이날 → 4영업일)
- 결과를 메모리에 저장: 주차 번호, 시작일(월), 종료일(금), 영업일 수

### Step 1. 데이터 + HTML 스켈레톤 생성

```bash
.venv/bin/python scripts/generate_asia_weekly.py $ARGUMENTS
```

이 스크립트가 자동 처리:
- 아시아종목.xlsx ↔ market_data.csv 매칭 + WTD% 계산
- 국가별 단순·가중 평균
- 지수·환율·MSCI EM 변동률
- KPI 스트립, Header 뱃지, Data 탭 표 자동 채움
- 부산물: `output/summary/weekly/YYYY-WNN_asia_data.json`

**확인 사항**: 매칭 종목 수와 국가별 분포를 출력 로그에서 확인. 매칭률이 낮으면 (예: <50%) `collectors/stocks_universe.py` 확장 권장.

### Step 2. 미래에셋증권 디지스트 4건 읽기

```bash
ls output/research/securities/digest_2026-W*.html | tail -4
```

W##-3, W##-2, W##-1, W## 4건의 디지스트를 읽고:
- 중국·일본·아시아 관련 인사이트 추출
- W##의 핵심 매크로 이벤트 메모
- 시계열로 누적되는 테마 파악 (반도체 자립, AI 인프라 등)

### Step 3. Story 5탭 본문 작성

`output/summary/weekly/YYYY-WNN_asia.html` 의 placeholder 5탭에 본문을 주입한다. **각 탭의 작성 규칙은 `.claude/skills/asia-weekly/references/story-template.md`** 참조.

**작성 순서**:
1. **Asia Story** (메인) — Hero 3단락 + 인과체인 5노드 + 인사이트 6카드
2. **Country Drilldown** — 국가별 (중국·일본·대만·인도·홍콩·한국) 6 섹션
3. **Themes** — 횡단 주제 4~5개 (반도체 디커플링, 달러 강세, AI 인프라, 정책 리스크, 지정학)
4. **Outlook** — Bull/Base/Bear 시나리오 + 리스크 TOP 5 + 데이터 캘린더
5. **Sources** — 5개 섹션 (데이터·미래에셋·외부·방법론)

**핵심 톤 (반드시 준수)**:
- 존댓말 (~합니다, ~됐습니다, ~입니다)
- 사용자 선호: 자세한 서술 (각 섹션 본문 2~4 단락)
- Forward-looking 금지 (Outlook 탭만 예외)
- 인과관계: 과거 → 현재 (사후 참조 금지)
- 종목명: xlsx 매칭 종목만 수치 인용

### Step 4. 검증

```bash
# 1) 구조 검증 (CSS 화이트리스트 + 필수 섹션)
echo '{"tool_input":{"file_path":"output/summary/weekly/YYYY-WNN_asia.html","content":""}}' | \
  .venv/bin/python .claude/hooks/post_edit_write_structure_guard.py

# 2) 수치 검증 (CSV ground truth 대조)
.venv/bin/python scripts/verify_report_numbers.py output/summary/weekly/YYYY-WNN_asia.html
```

둘 다 `{"decision":"allow"}` 또는 `[verify] ✓ 위반 없음` 출력되어야 한다.

### Step 5. (선택) 배포

사용자에게 배포 여부 확인 후:
```bash
# git commit + push (사용자 명시 승인 시)
/market-deploy
```

또는 사용자가 검토만 원하면:
```bash
open output/summary/weekly/YYYY-WNN_asia.html
```

---

## 완료 보고 형식

다음 형식으로 사용자에게 결과를 보고:

```
## 산출물
- output/summary/weekly/YYYY-WNN_asia.html — 메인 보고서

## W## 핵심 발견
1. [가장 큰 디스퍼션]
2. [국가별 헤드라인]
3. [통화·매크로]

## Step 결과
- ✅ Step 0 캘린더 검증 (5영업일 또는 N영업일)
- ✅ Step 1 데이터 스켈레톤 (매칭 N/M, M개 국가)
- ✅ Step 2 디지스트 4건 읽음
- ✅ Step 3 Story 5탭 작성 완료
- ✅ Step 4 구조·수치 검증 통과
- (사용자 승인 후) Step 5 배포

## 데이터 한계 (있다면)
- xlsx ↔ CSV 매칭률
- 미커버 국가/종목
- 외부 검색 차단 사항
```

---

## 주의사항

- **미래 날짜 금지**: 대상 날짜가 오늘보다 미래면 즉시 중단.
- **공휴일 처리**: 5/5(어린이날), 5/15(부처님오신날), 10/3(개천절) 등 한국 공휴일이 끼면 영업일 단축. `calendar_check.py` 가 자동 감지.
- **이미 존재하는 보고서**: 같은 주차 파일이 이미 있으면 덮어쓰기 전에 사용자 확인.
- **collect_weekly 의존성**: launchd 자동 실행 시에는 `collect_weekly.py` 가 먼저 완료되어야 한다 (15분 마진).

---

## 자동화 (launchd)

`com.lifesailor.asia-weekly.plist` 가 매주 **일요일 19:30 KST** 호출:
1. `generate_asia_weekly.py` 실행 → 스켈레톤 + 데이터 채움
2. 결과를 Telegram 으로 알림 ("아시아 W## 스켈레톤 준비됨")
3. **Story 본문은 Claude 수동 작성** (또는 별도 `launchd_claude_invoke` 후속 작업)

→ launchd 자동화는 데이터 준비까지만, Story 본문은 사용자가 다음 날 아침에 `/asia-weekly` 한 줄로 트리거.
