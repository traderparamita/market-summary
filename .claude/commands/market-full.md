---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD]  (생략 시 전 영업일)"
description: "market_summary 전체 워크플로우: 데이터 수집 → Dashboard → Story(일/주/월) → 배포 → Sector-Country → 배포"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 일간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/2026-*/2026-*-*.html 2>/dev/null | head -3`
- 최근 주간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/weekly/*.html 2>/dev/null | head -3`
- 최근 월간 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/monthly/*.html 2>/dev/null | head -3`

## Your task

`market_summary` 프로젝트의 **일일 영업일 08:00 KST 전체 워크플로우**를 순차 실행한다.

**대상 날짜**: $ARGUMENTS (비어있으면 전 영업일)

워크플로우는 **두 블록**으로 나뉜다:
- **블록 A (Steps 0~9)**: Market Summary (일/주/월) → 커밋/푸시 → Telegram ①
- **블록 B (Steps 10~12)**: Sector-Country → 커밋/푸시 → Telegram ②

블록 A가 완료되면 블록 B 실패 여부와 무관하게 market-summary는 이미 배포된 상태다.

---

### 사전 점검

1. 대상 날짜가 **오늘보다 미래가 아닌지 확인**. 미래면 즉시 중단하고 사용자에게 보고.
2. 대상 날짜가 주말이거나 한국·미국 공휴일이면 사용자에게 "해당일 보고서를 생성할지" 확인.

---

## 블록 A — Market Summary

### Step 0: Telegram 시작 알림

사전 점검 통과 후 즉시 전송. 실패해도 계속 진행.

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && \
  .venv/bin/python notify_telegram.py $ARGUMENTS --start
```

### Step 1~2: Data Dashboard 생성

아래 명령 **하나만** 실행한다. 데이터 수집과 HTML 생성을 모두 처리한다.

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python generate.py $ARGUMENTS
```

**내부 동작 (참고용 — 별도로 실행하지 않는다)**:
- `generate.py` 파이프라인 (Snowflake 중심으로 재구성됨):
  - **Step 1a**: `collect_market.fetch_data()` — core 56+ 지표 수집 → CSV append
  - **Step 1b**: Aux collectors 일간 실행 (`_run_aux_collectors`)
    - `portfolio.collectors.sector_etfs` — SC_US_*, FA_US_*, SC_KR_* (yfinance)
    - `portfolio.collectors.krx_sectors` — IX_KR_* (pykrx KOSPI200 GICS)
    - `portfolio.collectors.valuation` — VAL_KR_* (pykrx KOSPI PER/PBR/DY)
    - 각 collector 가 CSV append 후 Snowflake 자체 upsert (`[SNOWFLAKE]` 마커)
  - **Step 1c**: 통합 Snowflake upsert — CSV 의 `target_date` 전체 행을 읽어 MKT100 에 upsert
  - **Step 2**: `build_report_data()` — **MKT100 (Snowflake)** 에서 읽어 메트릭 계산
  - HTML 생성 + 주간·월간 자동 갱신

- 데이터 소스: **Snowflake MKT100_MARKET_DAILY 가 단일 정본**. CSV 는 legacy fallback (simulate.py 시뮬레이션 모드에서만 활용, `SNOWFLAKE_DISABLE=1`).

실패 시 오류 로그 확인 후 재시도 또는 사용자에게 보고 후 **즉시 중단**. `collect_market.py`를 별도로 실행하지 않는다.

**Snowflake 적재 결과 확인 (필수)**:
- 실행 출력에서 `[SNOWFLAKE]` 로 시작하는 줄을 반드시 찾아 기록한다. 보통 여러 줄 출력됨:
  - `[SNOWFLAKE] OK source=collect_sector_etfs rows=N` (aux 각각)
  - `[SNOWFLAKE] OK source=collect_krx_sectors rows=N`
  - `[SNOWFLAKE] OK source=collect_valuation rows=N`
  - `[SNOWFLAKE] OK date=YYYY-MM-DD rows=N` (Step 1c 통합 upsert, 가장 중요)
- 완료 보고 Step 1~2 셀에 통합 upsert 행수(`Snowflake N행`)를 표기한다.
- `[SNOWFLAKE] FAILED` 가 있으면 완료 보고 셀에 `⚠ Snowflake 실패: <reason>` 표기 + 하단 경고 블록.
- `[AUX] FAILED collector=...` 은 보조 수집 실패 — core 데이터는 영향 없음, 경고 표기만.
- 이 필드는 **스킵·생략 불가**. `✅ 성공 (N rows)` 같은 모호한 표기만으로는 안 된다.

### Step 3: 일간 Market Story 작성

`market-summary` **스킬**의 "일간 Story 작성 절차"를 따른다.

핵심:
1. `output/summary/YYYY-MM/YYYY-MM-DD_data.json` Read → 수치·holiday 확인
2. 시간순 웹 검색 (아시아 → 유럽 → 미국)
3. Story 작성 (훅이 forward-looking·세션 간 참조 등 자동 검증)
4. `output/summary/YYYY-MM/YYYY-MM-DD.html`의 Story 탭에 주입 + `_story.html` 저장

### Step 3-B: 일간 CS Story 작성

Step 3 완료 **직후** `market-summary` 스킬의 **"CS Story 작성 절차"** 섹션 규칙으로 CS 버전을 작성한다.

핵심:
1. 방금 저장한 `YYYY-MM-DD_story.html` Read
2. 수치(퍼센트·가격·거래량·시가총액)를 맥락 어휘로 치환. 종목·이벤트·날짜는 유지.
3. 의사결정 권유 톤 금지 (설명·관찰만).
4. `YYYY-MM-DD.html` 의 `<div id="tab-cs">` ~ `</div><!-- /tab-cs -->` 블록을 Edit + `YYYY-MM-DD_cs.html` 동기화.

실패 시 경고 후 계속 진행 (Step 3-C / Step 4 중단 없음). CS 는 Story 탭과 독립된 고객용 트랙이므로 빠져도 Market Summary 배포는 가능.

### Step 3-C: 일간 PM Story 작성

Step 3 완료 **후** `market-summary` 스킬의 **"PM Story 작성 절차"** 섹션 규칙으로 PM 버전을 작성한다. (Step 3-B 와 독립 — CS 실패해도 PM 은 시도)

핵심:
1. `YYYY-MM-DD_story.html` + `YYYY-MM-DD_data.json` Read
2. 6개 고정 섹션(🇰🇷 한국 · 🌐 매크로 · 🌏 아시아 및 중국 · 🇺🇸 미국 · 🇪🇺 유럽 · 💵 채권) 으로 재편집
3. 각 섹션 3~5 불릿, 종가·변동률·WTD/MTD/YTD·bp·FX 레벨 등 수치 적극 포함
4. 원본 Story 의 사실관계·시간순·세션 규칙 그대로 유지. 매수/매도 직접 권유 금지.
5. `YYYY-MM-DD.html` 의 `<div id="tab-pm">` ~ `</div><!-- /tab-pm -->` 블록을 Edit + `YYYY-MM-DD_pm.html` 동기화.

실패 시 경고 후 계속 진행 (Step 4 중단 없음). PM 은 Story / CS 와 독립된 매니저용 트랙.

### Step 4: 주간 Data Dashboard

Step 1~2에서 이미 `update_current_periodic()`이 자동 실행됨. 별도 실행 불필요. `output/summary/weekly/` 해당 주 파일이 존재하는지만 확인.

### Step 5: 주간 Market Story

대상 날짜가 해당 주의 **마지막 영업일**(보통 금요일)인 경우에만 작성. 중간 영업일이면 **건너뛴다**.

- `market-summary` 스킬의 "주간 Story 작성 절차" 따름
- 해당 주의 일간 `_story.html`들을 모두 읽어 종합
- `output/summary/weekly/YYYY-WNN.html`에 주입

### Step 5.5: 매크로 데이터 수집 (마지막 영업일만)

대상 날짜가 해당 주의 **마지막 영업일**인 경우에만 실행:

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python -m portfolio.collectors.macro
```

실패 시 경고 후 계속 진행 (보고서 생성은 기존 CSV로 진행).

### Step 5.6: Macro & Events 탭 작성 (마지막 영업일만)

대상 날짜가 해당 주의 **마지막 영업일**인 경우에만 `macro-events` **스킬**의 작성 절차를 따른다.

핵심:
1. `history/macro_indicators.csv`에서 이번 주 날짜 범위 필터링 (bash grep)
2. Tavily MCP(`mcp__tavily__search`)로 이번 주 주요 이벤트 수집·해설
3. Tavily MCP로 다음 주 이벤트 캘린더 수집
4. `output/summary/weekly/YYYY-WNN.html`의 `tab-macro` 블록에 주입
5. `YYYY-WNN_macro.html` 저장 확인

### Step 6: 월간 Data Dashboard

Step 1~2에서 자동 갱신됨. 별도 실행 불필요.

### Step 7: 월간 Market Story

대상 날짜가 해당 월의 **마지막 영업일**인 경우에만 작성. 아니면 **건너뛴다**.

- `market-summary` 스킬의 "월간 Story 작성 절차" 따름
- `output/summary/monthly/YYYY-MM.html`에 주입

### Step 7.5: 월간 매크로 데이터 수집 (마지막 영업일만)

대상 날짜가 해당 월의 **마지막 영업일**인 경우에만 실행:

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python -m portfolio.collectors.macro
```

실패 시 경고 후 계속 진행.

### Step 7.6: 월간 Macro & Events 탭 작성 (마지막 영업일만)

대상 날짜가 해당 월의 **마지막 영업일**인 경우에만 `macro-events` **스킬**의 작성 절차를 따른다.

핵심:
1. `history/macro_indicators.csv`에서 이번 달 날짜 범위 필터링 (bash grep)
2. Tavily MCP(`mcp__tavily__search`)로 이번 달 주요 이벤트 수집·해설 (FOMC, CPI, GDP, NFP 등 핵심 중심)
3. Tavily MCP로 다음 달 주목할 이벤트 캘린더 수집
4. `output/summary/monthly/YYYY-MM.html`의 `tab-macro` 블록에 주입
5. `YYYY-MM_macro.html` 저장 확인

### Step 8: Git Commit + Push — Market Summary

`output/summary/`, `output/index.html`, `history/market_data.csv`를 스테이징 후 커밋·푸시.

- 커밋 메시지: `market: YYYY-MM-DD daily report` (주간/월간 포함 시 범위 표기)
- `git push origin main`

실패 시 즉시 중단하고 사용자에게 상태 보고.

### Step 9: Telegram ① — Market Summary 완료 알림

Step 8 성공 후 즉시 전송. 실패해도 블록 B로 계속 진행.

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && \
  .venv/bin/python notify_telegram.py $ARGUMENTS \
    [--weekly]   # 해당 주 마지막 영업일이면 추가 \
    [--monthly]  # 해당 월 마지막 영업일이면 추가
```

- `--weekly` / `--monthly` 플래그는 Step 5 / Step 7 실행 여부와 동일한 조건으로 붙인다

---

## 블록 B — Sector-Country

### Step 10: Sector-Country Data Dashboard 생성

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python generate_sector_country.py $ARGUMENTS
```

실패 시 경고 로그 후 **계속 진행** (Step 11 중단 없음).

### Step 11: Sector-Country Story 작성

`sector-country` **스킬**의 작성 절차를 따른다.

핵심:
1. `get_focus(date)` 결과로 오늘의 3개 주제(US 섹터 + KR 섹터 + 국가) 확인
2. 주제별 Tavily 검색 (최근 1~2주 트렌드 맥락)
3. Story 작성 후 `output/sector-country/daily/YYYY-MM/YYYY-MM-DD.html`에 주입
4. `YYYY-MM-DD_story.html` 저장 확인

### Step 12: Git Commit + Push — Sector-Country

**반드시 디렉터리 전체를 스테이징한다.** 개별 파일만 `git add` 하면 `output/sector-country/index.html` (Step 10에서 `_update_sc_index()` 가 갱신) 이 누락되어 목록 페이지가 다음 날 보고서로 업데이트되지 않는다.

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && \
  git add output/sector-country/ && \
  git status --short output/sector-country/ && \
  git commit -m "feat: $ARGUMENTS sector-country — 섹터 Day N/11 · 국가 Day M/11

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>" && \
  git push origin main
```

- 커밋 전 `git status --short` 출력에 `output/sector-country/index.html` 이 포함되는지 반드시 확인
- 커밋 메시지 N/M 은 Step 10 결과에서 얻은 실제 일자 대입

실패 시 즉시 중단하고 사용자에게 상태 보고.

### Step 13: Telegram ② — Sector-Country 완료 알림

Step 12 성공 후 즉시 전송. 실패해도 완료 보고로 계속.

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && \
  .venv/bin/python notify_telegram.py $ARGUMENTS --sc-complete \
    --focus "섹터 Day N/11 — 오늘의 섹터 테마 | 국가 Day M/11 — 오늘의 국가" \
    --ow "OW 섹터/국가 목록" \
    --uw "UW 섹터/국가 목록 (없으면 생략)"
```

- `--focus` 값은 Step 10 실행 결과에서 확인한 테마 텍스트
- `--ow` / `--uw`는 Step 10 데이터 읽기 결과 기반

---

## 완료 보고

모든 단계 완료 후 Step별 실행 결과를 표 형식으로 보고:

```
── 블록 A: Market Summary ──────────────────────
Step 0:    Telegram 시작    — ✅ 전송 / ⚠ 실패(계속)
Step 1~2:  Data Dashboard   — ✅ 성공 (CSV N행, Snowflake M행) / ⚠ CSV 저장 · Snowflake 실패(<reason>) / ❌ 실패(<reason>)
Step 3:    일간 Story        — ✅ 성공 / ❌ 실패
Step 3-B:  일간 CS Story     — ✅ 성공 / ⚠ 실패(계속)
Step 3-C:  일간 PM Story     — ✅ 성공 / ⚠ 실패(계속)
Step 4:    주간 Dashboard    — ✅ 자동 갱신
Step 5:    주간 Story        — ✅ 성공 / ⏭ 스킵
Step 5.5:  매크로 수집       — ✅ 성공 / ⏭ 스킵 / ⚠ 실패(계속)
Step 5.6:  Macro 탭          — ✅ 성공 / ⏭ 스킵
Step 6:    월간 Dashboard    — ✅ 자동 갱신
Step 7:    월간 Story        — ✅ 성공 / ⏭ 스킵
Step 7.5:  월간 매크로       — ✅ 성공 / ⏭ 스킵
Step 7.6:  월간 Macro 탭     — ✅ 성공 / ⏭ 스킵
Step 8:    Git Push (MS)     — ✅ 커밋해시
Step 9:    Telegram ①       — ✅ 전송 / ⚠ 실패(계속)

── 블록 B: Sector-Country ──────────────────────
Step 10:   SC Dashboard      — ✅ 성공 / ⚠ 실패(계속)
Step 11:   SC Story          — ✅ 성공 / ⚠ 실패(계속)
Step 12:   Git Push (SC)     — ✅ 커밋해시
Step 13:   Telegram ②       — ✅ 전송 / ⚠ 실패(계속)
```

- 다음 영업일 실행 권장 시각도 함께 표기

---

## 중단 규칙

- Step 1~2 실패: 즉시 중단 (블록 A/B 전체)
- Step 3/5/7 훅 block: 사유 읽고 수정 재시도 (2회까지), 계속 실패 시 사용자에게 보고
- Step 8 git 실패: 즉시 중단하고 사용자에게 상태 보고
- Step 10 실패: 경고 후 Step 11로 계속 진행
- Step 11 실패: 경고 후 Step 12로 계속 진행 (Dashboard만 배포)
- Step 12 git 실패: 즉시 중단하고 사용자에게 상태 보고
- Telegram 실패: 경고 로그만 출력하고 다음 단계로 계속