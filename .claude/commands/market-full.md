---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD]  (생략 시 전 영업일)"
description: "market_summary Part A: 데이터 수집 → Dashboard → Market Story. 이후 /market-full-b 가 CS/PM/Stocks/검증/push 담당"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 일간 보고서: !`ls -t output/summary/2026-*/2026-*-*.html 2>/dev/null | head -3`
- 최근 주간 보고서: !`ls -t output/summary/weekly/*.html 2>/dev/null | head -3`
- 최근 월간 보고서: !`ls -t output/summary/monthly/*.html 2>/dev/null | head -3`

## Your task

`market_summary` 프로젝트의 **일일 영업일 08:00 KST 전체 워크플로우**를 순차 실행한다.

**대상 날짜**: $ARGUMENTS (비어있으면 전 영업일)

워크플로우는 **Steps 0~9** 단일 블록으로 구성된다.  
`generate_sector_country.py`는 2026-05-26 폐기 — 절대 호출하지 않는다.

---

### 사전 점검

0. **캘린더 검증 (필수 — 요일 추측 금지)**:
   ```bash
   .venv/bin/python scripts/calendar_check.py $ARGUMENTS
   ```
   출력된 요일·영업일·공휴일 정보를 **이후 모든 Step에서 참조**한다. 절대로 날짜-요일 매핑을 추측하지 않는다.
   - "마지막 영업일" 판단은 이 출력의 해당 주/월 영업일 목록 기준
   - 주간/월간 보고서 생성 여부도 이 데이터로 결정

1. 대상 날짜가 **오늘보다 미래가 아닌지 확인**. 미래면 즉시 중단하고 사용자에게 보고.
2. 대상 날짜가 주말이거나 한국·미국 공휴일이면 사용자에게 "해당일 보고서를 생성할지" 확인.

---

## 블록 A — Market Summary

### Step 0: Telegram 시작 알림

사전 점검 통과 후 즉시 전송. 실패해도 계속 진행.

```bash
  .venv/bin/python notify_telegram.py $ARGUMENTS --start
```

### Step 1~2: Data Dashboard 생성

아래 명령 **하나만** 실행한다. 데이터 수집과 HTML 생성을 모두 처리한다.

```bash
.venv/bin/python generate.py $ARGUMENTS
```

**내부 동작 (참고용 — 별도로 실행하지 않는다)**:
- `generate.py` 파이프라인 (Snowflake 중심으로 재구성됨):
  - **Step 1a**: `collect_market.fetch_data()` — core 56+ 지표 수집 → CSV append
  - **Step 1b**: Aux collectors 일간 실행 (`_run_aux_collectors`)
    - `collectors.sector_etfs` — SC_US_*, FA_US_*, US Bond ETFs (yfinance)
    - `collectors.krx_sectors` — IX_KR_* (pykrx KOSPI200 GICS)
    - `collectors.valuation` — VAL_KR_* (pykrx KOSPI PER/PBR/DY)
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

`market-summary` **스킬** (SKILL.md 공통 규칙) + `references/daily.md` (일간 Story 작성 절차) 를 따른다.

핵심:
1. `output/summary/YYYY-MM/YYYY-MM-DD_data.json` Read → 수치·holiday 확인
2. 시간순 웹 검색 (아시아 → 유럽 → 미국) — 검색 결과의 URL·제목·매체·날짜를 sources 용으로 수집
3. Story 작성 (훅이 forward-looking·세션 간 참조 등 자동 검증)
4. `output/summary/YYYY-MM/YYYY-MM-DD.html`의 Story 탭에 주입 + `_story.html` 저장
5. **Sources 주입 (필수, 절대 생략 금지)**: 수집한 출처를 `tab-sources` 탭에 주입 + `_sources.html` 사이블링 저장. 최소 5건. `references/sources.md` 형식. **Step 7.7 의 `verify_report_numbers.py` 가 빈 sources 자동 catch — 누락 시 검증 실패로 Step 8 진행 차단.**

**완료 보고**:
```
✅ [Step 3] 일간 Market Story 작성 완료 (Sources: N건 주입)
```

### Step 3-E: Completed Catalysts Ledger 발행 (매일)

Step 3 Market Story 작성 직후, 어제 완료된 catalyst를 `completed.jsonl` ledger에 기록한다.  
실패해도 경고 후 계속 진행 (Avalon Tavily fallback 사용).

**추출 대상**: Market Story에서 언급된 *완료된* 이벤트 (forward 이벤트 제외)
- 실적 발표 (earnings): 개별 종목 — 발표 직전까지의 서프라이즈·컨센서스 포함
- 매크로 지표 발표 (macro): CPI, PCE, NFP, GDP, PMI, 주택지표 등
- FOMC 결정/성명 (fomc)
- IPO 상장 (ipo)
- 기타 시장에 영향을 준 완료 이벤트 (other)

**출력 형식** — JSON array, 1건 이상일 때만 발행:

```json
[
  {
    "date": "YYYY-MM-DD",       // 실제 발표일 (어제 날짜)
    "ticker": "NVDA",           // 어닝이면 티커, macro/fomc는 null
    "type": "earnings",         // earnings | macro | fomc | ipo | other
    "session": "after_close",   // pre_open | regular | after_close | scheduled
    "name": "Nvidia Q1 FY2027 실적 발표",
    "result": {                 // optional — 알 수 있는 범위만
      "revenue": "$81.6B",
      "eps": 1.87,
      "surprise": "beat"        // beat | miss | in-line
    }
  }
]
```

**발행 절차**:
1. 위 JSON array를 구성 (이벤트가 없으면 발행 스킵)
2. 아래 명령으로 스크립트 호출:

```bash
.venv/bin/python scripts/publish_catalysts.py --data '<JSON_ARRAY>'
```

출력에서 `✓ 로컬 append` 및 `✓ S3 업로드 완료` 확인.

**완료 보고**:
```
✅ [Step 3-E] Catalysts 발행 완료 (N건) / ⊘ 발행할 catalyst 없음 / ⚠ 실패(계속)
```

### Step 4: 주간 Data Dashboard

Step 1~2에서 이미 `update_current_periodic()`이 자동 실행됨. `output/summary/weekly/` 해당 주 파일이 존재하는지만 확인.

### Step 6: 월간 Data Dashboard

Step 1~2에서 자동 갱신됨. 별도 실행 불필요.

---

## 완료 보고 (Part A)

Part A 완료 후 아래 표 형식으로 보고하고 **즉시 종료**한다.  
CS/PM/Stocks/검증/push 는 `/market-full-b` (Part B) 가 담당한다.

```
Step 0:    Telegram 시작    — ✅ 전송 / ⚠ 실패(계속)
Step 1~2:  Data Dashboard   — ✅ 성공 (CSV N행, Snowflake M행) / ❌ 실패(<reason>)
Step 3:    일간 Story        — ✅ 성공 (Sources: N건) / ❌ 실패
Step 3-E:  Catalysts Ledger  — ✅ N건 발행 / ⊘ 없음 / ⚠ 실패(계속)
Step 4/6:  주간·월간 Dashboard — ✅ 자동 갱신 확인
```

**Part A 종료 — Part B(`/market-full-b`)가 이어서 CS·PM·Stocks·검증·push를 처리합니다.**

---

## 중단 규칙

- Step 1~2 실패: 즉시 중단
- Step 3 훅 block: 사유 읽고 수정 재시도 (2회까지), 계속 실패 시 중단
- Telegram 실패: 경고 로그만 출력하고 다음 단계로 계속