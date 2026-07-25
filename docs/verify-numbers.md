# 보고서 수치 자동 검증 (verify_report_numbers.py)

`/market-full` 워크플로우와 Stop 훅이 turn 종료 시마다 자동 호출하는 결정론 검증 시스템. Story 본문에 박힌 종가·등락률·bp 변화가 `history/market_data.csv` ground truth와 일치하는지 자동 대조하고, 위반 발견 시 Telegram 알림을 보낸다.

## 한 줄 요약

> 보고서 본문의 표시 자릿수에 맞춰 반올림한 CSV 계산값과 **정확 일치**해야 한다. 일치하지 않으면 commit 차단 + Telegram 알림.

---

## 검증 대상

`output/summary/`, `output/report/` 아래의 변경된 보고서 파일 (`*.html`, `*.md`).

| 파일 종류 | 기간 추론 |
|---|---|
| `summary/YYYY-MM/YYYY-MM-DD.html` | 일간 + WTD + MTD + YTD |
| `summary/weekly/YYYY-WNN.html` | WTD (전주 금 → 그 주 금) |
| `summary/monthly/YYYY-MM.html` | MTD (전월 말 → 월말) |
| `report/*.md` | 마크다운 표 자체 일관성만 |

`--auto` 옵션은 `git diff --name-only HEAD` + `git ls-files --others`로 변경분 자동 감지.

---

## 검출 패턴 (7개)

| # | 패턴 | 매칭 예 | 신뢰도 |
|---|---|---|---|
| 1 | KPI 카드 | `<div class="s-kpi-label">KOSPI WTD</div><div class="s-kpi-value">+4.58%</div>` | ⭐⭐⭐ |
| 2 | 본문 명시 % | `KOSPI WTD +4.58%` | ⭐⭐⭐ |
| 3 | 본문 명시 bp | `US 10Y WTD +6.4bp` | ⭐⭐⭐ |
| 4 | HL span 인라인 | `US 10Y <span class="hl-up">+6.4bp</span>` | ⭐⭐ (컨텍스트 추론) |
| 5 | 마크다운 표 3컬럼 | `\| KOSPI \| 4,214 \| 5,052 \| +19.89% \|` | ⭐⭐⭐ (CSV 없이 산술 모순) |
| 6 | COMBO 묶음 | `삼성전자 +4.37%(186,200원)` / `KOSPI +2.74%(5,377)` | ⭐⭐ (일간 등락 + 종가 동시) |
| 7 | 종목 일변동률 (T1) | `Apple +3.24%` / `삼성전자 +5.44%` | ⭐⭐ (CITATION/forward/DAILY_HINT 가드) |

> 단독 종가 패턴 (`KOSPI 5,377` 단독)은 정밀도 부족(다른 일자 인용·시나리오 트리거 false positive)으로 **비활성화**. COMBO 형태로 작성 권장.

### 패턴 #7 — T1 종목 일변동률 (2026-05 추가)

`STOCK_DAILY_PATTERN` 은 종가 괄호 없이 `{종목} ±N%` 형식만 따로 잡는다. COMBO 패턴은 종가 괄호가 있어야 매칭하므로 본문 인라인의 `Apple +5.4% 급등` 같은 케이스를 놓치는 사각지대가 있었다 (2026-05-01 보고서의 Apple 변동률 오류 사고가 계기).

**검증 대상 화이트리스트 (14개 핵심 stocks)**: `_data.json` stocks 카테고리에 매일 들어오는 종목으로 한정 — Apple · MSFT · NVIDIA · Alphabet · Amazon · META · Tesla · Broadcom · Palantir · Samsung(삼성전자) · TSMC · Alibaba · Tencent · Meituan.

> **왜 14개로 제한하나?** 한국 KOSPI200 종목·미국 S&P500 종목 등 보고서에 등장하는 100+개 종목은 우리 CSV/RDS 에 없어 자동 검증 자료가 없다. 자료 있는 14개만 결정론적으로 검증하고, 그 외 종목은 출처 인용으로 신뢰도를 위임한다 (메인 Story 의 Sources 탭 / OCR 1차 자료).

**가드 (false positive 차단)**:
- `CITATION_KEYWORDS` (어제·전일·전주·돌파·치솟·급등·급락·최고치 등) 윈도우에 있으면 스킵
- `DAILY_HINT_PATTERN` (`4/8(수)` 같은 다른 일자 명시) 있으면 스킵
- `_is_in_forward_container` (scenario / outlook / risk-section) 안이면 스킵
- 종가 괄호가 뒤따르면 COMBO 가 처리하므로 negative lookahead 로 중복 회피

---

## 검증 산식 — 허용 오차 없음

```
expected_pct = (p_end / p_start - 1) * 100
expected_bp  = (yield_end - yield_start) * 100
expected_close = CSV[(target_date, code)]
```

보고서 표시 자릿수에 맞춰 반올림한 expected와 reported가 **정확 일치**해야 한다.

```
보고서 "+4.58%" → CSV 4.5807 → round(4.5807, 2) = 4.58 → 일치 ✓
보고서 "+1.51bp" → CSV 6.40bp → 4.89bp 차이 → 위반 ✗
```

마크다운 표만 정수 시작·종료 반올림 누적 흡수 위해 ±0.1%P 마진.

---

## False Positive 가드 (보수적 정책)

검증 시스템은 4중 가드로 false positive를 차단한다:

1. **단락 경계 자르기** ([:_trim_window_to_paragraph](../scripts/verify_report_numbers.py))
   - HL span 윈도우를 `<br><br>` / `</p>` / `</li>` / `</div>`에서 자른다
   - 다른 단락의 헤더(`"4월 MTD 결산"` 등)가 윈도우에 들어오지 않게
   - 헤더(`</h2>`/`</h3>`)는 자르지 않음 — 섹션 헤더의 "WTD" 라벨이 그 섹션 컨텍스트 제공

2. **CITATION_KEYWORDS 가드**
   - `어제`·`전일`·`전주`·`전월`·`→`·`vs`·`돌파`·`이탈`·`이상`·`미만`·`치솟`·`급등`·`급락`·`최고치`·`신고점`·`ATH` 등이 윈도우에 있으면 검증 스킵
   - 인용·비교·forward 표현은 보고서 기본 일자의 종가가 아닐 가능성 높음

3. **Forward 컨테이너 차단**
   - `class="scenario-card|outlook-position|outlook-divider|scen-trigger|scen-impact|risk-section|quarterly-themes"` 안의 가격은 시나리오 트리거 → 스킵

4. **target_date 보수적 정책**
   - 본문에 `4/8(수)` 같은 일자 명시(`\d{1,2}/\d{1,2}\([월화수목금토일]\)`) 있으면 그 일자로 검증
   - 윈도우에 여러 날짜가 공존하면(이벤트 테이블 등) 매칭 위치에 **가장 가까운** 날짜를 선택
   - 명시 없으면 **일간 보고서만** 그 날로 fallback. 주간/월간은 검증 스킵 (다른 일자 인용일 가능성)

---

## 자동화 통합

### `/market-full` Step 7.7
모든 Story 작성(일간/주간/월간 + CS + PM) 완료 후, Step 8 (Git Commit) 직전에 실행.

```bash
.venv/bin/python scripts/verify_report_numbers.py --auto --telegram
```

`✓ 위반 없음` 통과 후에만 Step 8 진행. 위반 발견 시 같은 turn에서 fix → 재검증 루프.

### Stop 훅 (`.claude/settings.json`)
turn 종료 시 자동 발동 — `/market-full` 누락이나 사용자가 수동으로 Edit한 경우의 안전망.

```json
"Stop": [{
  "hooks": [{
    "type": "command",
    "command": "cd $CLAUDE_PROJECT_DIR && .venv/bin/python scripts/verify_report_numbers.py --auto --telegram",
    "statusMessage": "보고서 수치 자동 검증 (CSV ground truth 대조)..."
  }]
}]
```

### Telegram 알림
위반 ≥1건일 때만 발송. `notify_telegram.send()` 재사용 (개인 + Anthillia 그룹 동시).

```
🚨 보고서 수치 검증 위반 N건 (대상 M개 파일)

`{file}` :: *{자산} {기간}*
  보고서 `{reported}`  →  실제 `{expected}`  (차이 `{diff}`)
...

→ Story 또는 보고서를 ground truth(history/market_data.csv)에 맞춰 수정 필요.
```

---

## 사용법 (CLI)

```bash
# git diff 변경분 자동 감지 (상세 로그 자동 기록)
.venv/bin/python scripts/verify_report_numbers.py --auto

# 특정 파일 명시
.venv/bin/python scripts/verify_report_numbers.py output/summary/weekly/2026-W17.html

# JSON 출력 (CI / 훅 용)
.venv/bin/python scripts/verify_report_numbers.py --auto --json

# 위반 시 Telegram 발송
.venv/bin/python scripts/verify_report_numbers.py --auto --telegram

# 위반 자동 수정 + 재검증
.venv/bin/python scripts/verify_report_numbers.py --auto --fix

# 상세 로그만 남기기 (수동 실행 시)
.venv/bin/python scripts/verify_report_numbers.py --log output/summary/2026-04/2026-04-29.html
```

Exit code: 0 = pass, 1 = violation, 2 = CSV missing.

### 상세 로그 (`logs/verify_numbers.log`)

`--auto` 또는 `--log` 사용 시 타임스탬프와 함께 누적 기록:
- 대상 파일 목록
- 1차 검증 위반 내역
- 자동 수정 결과 (--fix 사용 시)
- 최종 잔여 위반 (문맥 포함)

---

## 자산 매핑

`ASSET_ALIASES` 사전에 35개 alias → INDICATOR_CODE.

- 지수: KOSPI, KOSDAQ, S&P500, NASDAQ, Nikkei225, TWSE, HSI, DAX, CAC40, FTSE100, STOXX50, Russell2K, NIFTY50, Shanghai
- 종목: Samsung/삼성전자, Apple/AAPL, Microsoft/MSFT, Alphabet/Google/GOOGL, Amazon/AMZN, Meta/META, NVIDIA/NVDA, Tesla/TSLA, TSMC, Broadcom/AVGO, Alibaba/BABA, Tencent, Meituan, Palantir/PLTR
- 원자재: WTI, Brent, Gold, Silver, Copper, Nat Gas
- FX: DXY, USD/KRW, USD/JPY, EUR/USD, AUD/USD, GBP/USD
- 변동성: VIX
- 채권: US 10Y, US 2Y, US 30Y, KR 3Y, KR 10Y

`PRICE_RANGE` 사전에 자산별 합리적 종가 범위 — 거래량·시총 등 false positive 차단.

새 종목/지수가 본문에 자주 등장하면 `ASSET_ALIASES` + `PRICE_RANGE` 둘 다 추가해야 함 (CSV에 INDICATOR_CODE가 있어야 검증 가능).

---

## 커버리지 / 한계

### ✅ 잡는 것
- KPI 박스 안 % / bp 오류 (W17 `+1.51bp` 같은 케이스 100% 잡음)
- 명시 `{자산} (WTD|MTD|YTD)` 패턴
- 채권 yield bp 변화
- 마크다운 표 시작/종료/등락 자체 산술 모순 (Q1 확장판 케이스)
- 일간 보고서의 COMBO `{자산} ±N%(종가)` 묶음 (일간 등락 + 종가 동시)

### ❌ 놓치는 것 (의도적 trade-off)
- 본문 자유서술 (`KOSPI가 2.74% 올랐다`) — 패턴 미정의
- 단독 종가 (`KOSPI 5,377`) — 정밀도 부족으로 비활성
- 인용·비교 컨텍스트 가격 (`어제(4/2)`, `→`, `>$105`) — 가드로 스킵
- PM Outlook 시나리오 트리거 — forward 컨테이너 스킵
- 거래량·시총·외국인 순매수 — CSV에 없음
- Alias 사전 외 종목 (SK하이닉스, 현대차 등 — 필요 시 매핑 추가)

---

## 운영 가이드

1. **매일 자동 실행**: 일 18:50 + 화~금 06:50 KST `auto_market.py` → `/market-full` → Step 7.7 → Stop 훅까지 2중 검증.
2. **위반 알림 받으면**: Telegram 메시지의 `보고서 vs 실제 vs 차이` 확인 → 해당 파일을 직접 Edit → `/market-deploy` 또는 다음 자동 실행 대기.
3. **새 자산 alias 필요 시**: `scripts/verify_report_numbers.py`의 `ASSET_ALIASES` + `PRICE_RANGE` 사전 보강.
4. **자유서술 검증 필요 시 (Phase 2-B 후속)**: 본문 작성을 표준 패턴(`{자산} ±N%(종가)`)으로 통일 + 인용 표기 시 `어제(M/D)` 같은 명시.
5. **검증력 vs 정밀도**: 가드를 약화하면 검증력 ↑ but false positive ↑. 현재는 "헛알림 0"을 우선 — 진짜 박스/표 오류는 KPI 카드 + 명시 패턴이 99% 잡음.

---

## 후속 개선 후보 (Phase 2-B+)

- 단독 종가 검증 재활성화 (인용 컨텍스트 정밀 분리)
- 본문 자유서술 패턴 (`KOSPI가 2.74% 상승`)
- 한국 종목 alias 확장 (CSV에 코드 추가 + 매핑)
- 외국인 순매수 / 거래대금 검증 (별도 데이터 소스 필요)
- W17/Q1 같은 검증 통과 사례를 회귀 테스트 픽스처로 보존
