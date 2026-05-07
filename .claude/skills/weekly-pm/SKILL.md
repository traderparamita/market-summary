---
name: weekly-pm
description: "금요일 오전 발행용 Weekly PM Brief 스킬. 그 주 월~목 4영업일(휴장 포함 시 3영업일) 누적 데이터로 매니저 브리프(6 섹션 + Today Residual + Next Week Outlook) 작성 후 HTML + PDF 2종(전체 / Data 제외) 생성. 사용 시점: '금요일 PM 브리프 만들어줘', '5/8 weekly-pm', '/weekly-pm YYYY-MM-DD'."
argument-hint: "[YYYY-MM-DD]  (생략 시 오늘 — 보통 금요일 발행)"
metadata:
  author: lifesailor
  version: "1.0.0"
---

# Weekly PM Brief 작성 스킬

매주 **금요일 오전(보통 08:00 KST 전후)** 에 발행하는 PM 브리프. 그 주 월~목 4영업일 누적 변동을 매니저 톤으로 정리하고, 오늘(금) 잔여 변수 + 다음 주(W+1) Outlook 까지 포함한다.

PM Story 본문은 `.claude/skills/market-summary/SKILL.md` 의 **"PM Story 작성 절차"** + **"PM Outlook 작성 절차"** 를 그대로 따른다. 이 스킬은 그 위에 **4영업일 윈도우 특수성** + **PDF 2종 산출** 을 얹는다.

## When to Use

- 사용자가 금요일 오전(또는 임의 시점)에 "이번 주 월~목 PM 브리프" 를 요청할 때
- `/weekly-pm YYYY-MM-DD` 슬래시 명령으로 호출될 때
- 정식 weekly Summary (월~금 5영업일, 일요일 발행) 와는 별개의 산출물

**When NOT to use**:
- 정식 weekly Summary 작성 → `market-summary` 스킬 + 일요일 발행
- 일간 PM 작성 → `/market-pm`
- Data Dashboard 만 필요 → `/market-data`

## 산출물

```
output/weekly-pm/YYYY-MM-DD.html              # 풀 보고서 (Data + PM)
output/weekly-pm/YYYY-MM-DD_pm.html           # PM 탭만 sibling
output/weekly-pm/YYYY-MM-DD.pdf               # 전체 PDF (12p 내외)
output/weekly-pm/YYYY-MM-DD_no-data.pdf       # Data Dashboard 제외 PDF (5p 내외)
```

`YYYY-MM-DD` = 발행일 (보통 그 주 금요일).

---

## 핵심 규칙

### 1. 발행일·윈도우 결정

- 인자 없으면 오늘 (`date.today()`).
- **미래 날짜 금지**: 발행일 > 오늘 이면 즉시 중단.
- 윈도우는 **그 주 ISO 주차의 월~목 영업일**. 한국 공휴일이 끼면 자동 제외 (예: 어린이날 5/5 → 4영업일이 3영업일 됨).
- 항상 `.venv/bin/python scripts/calendar_check.py YYYY-MM-DD --week WNN` 로 영업일 사전 검증.

### 2. 4영업일 누적 기준

- "Weekly" 컬럼 = **직전 금요일 종가 → 그 주 목요일 종가** (4영업일 누적)
- WTD 가 아님을 본문에 명시 (Hero/Subtitle 에 "월~목 4영업일 누적" 표기)
- 5영업일 정식 WTD 와 헷갈리지 않도록 — Hero 첫 단락에 반드시 "Mon-Thu" 표시

### 3. 시간 정확성 (PM 본문)

- 발행일이 D=금이면 D-1=목 까지의 데이터만 사용 (목요일 美 마감 = D 06:00 KST 까지)
- 금요일 당일 잔여 이벤트(NFP·ECB·Apple 갭 등)는 **"Today Residual" 박스** 에서만 forward-looking 으로 다룬다 (회고 6 섹션에는 절대 미반영)
- 다음 주(W+1) Outlook 도 forward-looking 화이트리스트 — `outlook-divider` / `scenario-grid` 클래스 사용 시 PostToolUse 훅이 자동 면제

### 4. 6 섹션 + Outlook 구조 (고정)

회고 6 섹션 (PM Story):
1. 🇰🇷 한국
2. 🌐 매크로
3. 🌏 아시아 및 중국
4. 🇺🇸 미국
5. 🇪🇺 유럽
6. 💵 채권

Outlook 5 블록 (회고 직후 `outlook-divider` 안):
1. ⏰ Today (D금) Residual — 한국·유럽 휴장 여부, 美 NFP·ECB·어닝 잔여 변수
2. 🐂📊🐻 W+1 Bull/Base/Bear 시나리오 (확률 합 100%)
3. 🗓 W+1 핵심 이벤트 캘린더 (KR·아시아 / US·매크로 / 유럽 / 채권·원자재)
4. ⚠️ 통합 리스크 Top 3
5. 📐 포지셔닝 시사점 (W+1 Base 시나리오, OW/N/UW 7~8 행)

각 회고 섹션 5~6 불릿, 수치 적극 포함 (종가·변동률·bp·MTD·YTD).

---

## 작성 절차

### Step 1 — 사전 점검

```bash
# 영업일 검증
.venv/bin/python scripts/calendar_check.py {date} --week W{NN}

# 데이터 최신성 확인 (전 영업일까지 들어왔는지)
.venv/bin/python -c "
from market_source import load_long
df = load_long()
print('latest:', df['DATE'].astype(str).max())
"
```

- 데이터 최신일이 D-1(목) 보다 이전이면 `auto_market.py` 또는 `collect_market.py` 먼저 실행

### Step 2 — HTML Skeleton 생성

```bash
.venv/bin/python generate_weekly_pm.py {date}
```

산출:
- `output/weekly-pm/{date}.html` — Data Dashboard 채워짐, PM/Story/CS/Sources 탭은 placeholder
- `inject_existing_story()` 가 자동 호출되어 **이전 회차의 PM 이 있으면 보존**

### Step 3 — PM Story 6 섹션 + Outlook 작성

`market-summary` 스킬의 **"PM Story 작성 절차"** Step 1~3 + **"PM Outlook 작성 절차"** 그대로 적용.

추가 4영업일 특수성:
- **수치 직접 검증**: `history/market_data.csv` 또는 `market_source.load_long()` 으로 D-4(금) → D-1(목) 종가 조회. `_data.json` 의 weekly 는 롤링 5영업일이라 사용 금지.
- **Best/Worst Day**: 4영업일 중 단일일 최대 상승률·하락률 (sparkline 보조)
- **이벤트 시점**: FOMC·CPI·어닝 등 발생 시각이 D-4 ~ D-1 범위 내인지 재확인

Today Residual 박스는 발행일 당일(D=금)의 한국 시간 기준 아직 발생 안 한 이벤트만:
- 美 NFP, CPI, ISM 등 D 21:30+ KST 발표
- ECB·BoE 등 D 21:00+ KST 결정
- D 한국·일본·중국·홍콩·EU 휴장 여부 (May Day, Children's Day 등)

### Step 4 — HTML 주입

`output/weekly-pm/{date}.html` 의 `<div id="tab-pm">` 블록을 Edit 으로 직접 치환.

골격:
```html
<div id="tab-pm" class="tab-panel">
<div class="pm-hero">
  <h2>PM BRIEF — W{NN} Mon-Thu ({first} ~ {last})</h2>
  <p>...4영업일 누적 핵심 메시지 (3~4 문장, 수치 포함)...</p>
</div>

<div class="pm-grid">
  <div class="pm-section"><h3>🇰🇷 한국</h3><ul>...</ul></div>
  <div class="pm-section"><h3>🌐 매크로</h3><ul>...</ul></div>
  ... 4개 더 ...
</div>

<div class="outlook-divider">
  <h2>📍 Today ({date}) Residual + W{NN+1} Outlook ({W+1 first} ~ {W+1 last})</h2>
  <!-- ⏰ Today Residual (yellow box) -->
  <!-- 🐂📊🐻 Bull/Base/Bear scenario-grid -->
  <!-- 🗓 핵심 이벤트 캘린더 (2x2 grid) -->
  <!-- ⚠️ 통합 리스크 Top 3 (red box) -->
  <!-- 📐 포지셔닝 시사점 (orange-bordered table) -->
</div>
</div><!-- /tab-pm -->
```

CSS 클래스 화이트리스트는 `post_edit_write_structure_guard.py` 의 PM Outlook 클래스 (`outlook-divider`, `scenario-grid`, `scenario-card`, `bull/base/bear` 등) 사용. 인라인 style 도 허용되지만 클래스 우선.

주입 후 sibling 동기화:
```bash
.venv/bin/python -c "
from report_utils import save_story_files, PERIODIC_TAB_SPECS
path = 'output/weekly-pm/{date}.html'
with open(path) as f: html = f.read()
save_story_files(path, html, PERIODIC_TAB_SPECS, log_fn=print)
"
```

### Step 5 — PDF 2종 생성

```bash
# 전체 (Data Dashboard 포함)
.venv/bin/python scripts/html_to_pdf.py output/weekly-pm/{date}.html

# Data 제외 (PM 중심 5p 내외)
.venv/bin/python scripts/html_to_pdf.py output/weekly-pm/{date}.html --exclude data
```

산출:
- `output/weekly-pm/{date}.pdf` (12p 내외)
- `output/weekly-pm/{date}_no-data.pdf` (5p 내외)

PDF 검증:
```bash
.venv/bin/python -c "
from pypdf import PdfReader
for f in ['output/weekly-pm/{date}.pdf','output/weekly-pm/{date}_no-data.pdf']:
    r = PdfReader(f)
    print(f, len(r.pages), 'pages')
"
```

---

## 주입 검증

```bash
# placeholder 잔존 체크 (0 이어야 함)
grep -c 'PM_STORY_PLACEHOLDER' output/weekly-pm/{date}.html

# 6 섹션 전부 들어갔는지 (6 이어야 함)
grep -oE '🇰🇷 한국|🌐 매크로|🌏 아시아 및 중국|🇺🇸 미국|🇪🇺 유럽|💵 채권' output/weekly-pm/{date}.html | sort -u | wc -l

# Outlook 블록 (1 이상)
grep -c 'outlook-divider\|scenario-grid' output/weekly-pm/{date}.html

# 수치 적극 포함 (PM 은 숫자 브리프, 30+ 권장)
grep -oE '[0-9]+\.[0-9]+%|[0-9]{3,}\.[0-9]{2}|[+-][0-9]+ ?bp' output/weekly-pm/{date}_pm.html | wc -l
```

---

## 완료 보고 형식

```
✅ Weekly PM Brief 발행 완료 — {date} ({weekday})
   윈도우: {first} ~ {last} ({n}영업일)
   회고: 6 섹션 (한국·매크로·아시아·미국·유럽·채권) · 수치 {N}건
   Outlook: Today Residual + W{NN+1} Bull/Base/Bear ({prob}%) + 캘린더 + 리스크 Top 3 + 포지셔닝 8행

📄 산출물:
   - output/weekly-pm/{date}.html         (HTML 풀)
   - output/weekly-pm/{date}_pm.html      (PM 탭 sibling)
   - output/weekly-pm/{date}.pdf          ({pages_full}p, Data Dashboard 포함)
   - output/weekly-pm/{date}_no-data.pdf  ({pages_brief}p, PM 중심 권장)
```

---

## 중단 규칙

- 발행일 > 오늘 → 즉시 중단
- 데이터 최신일 < D-1 → "데이터 수집 먼저" 안내
- 6 섹션 중 누락 → 재작성
- 수치 검증 실패 (CSV 와 본문 불일치) → 재작성
- PDF 페이지 수가 비정상 (with-data > 18p 또는 < 6p, no-data > 8p 또는 < 3p) → 콘텐츠 길이 점검

---

## 관련 파일

- `generate_weekly_pm.py` — 4영업일 윈도우 + HTML skeleton 생성기
- `scripts/html_to_pdf.py` — Playwright Chromium PDF 변환 (`--exclude` 옵션 포함)
- `.claude/hooks/post_edit_write_structure_guard.py` — `/weekly-pm/` 경로 Story 섹션 검증 자동 면제
- `.claude/skills/market-summary/SKILL.md` — PM Story / PM Outlook 작성 절차 (재사용)