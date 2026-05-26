# Market Summary

일일/주간/월간 글로벌 시장 요약 보고서를 자동 생성하는 프로젝트.

## 실행 방법

```
/market-full [YYYY-MM-DD]    # 데이터 수집 → Dashboard → Story(일/주/월) → 배포
/market-data [YYYY-MM-DD]    # 데이터 수집 + Data Dashboard만
/market-deploy               # output/ 변경분 commit + push
/research [YYYY-MM-DD]       # 주간 테마 리서치 (일요일 수동 발행, OCR 기반)
/weekly-pm [YYYY-MM-DD]      # 금요일 오전 발행용 Mon-Thu PM 브리프 + PDF 2종
/asia-weekly [YYYY-MM-DD]    # 아시아 주간 시황 브리프 (xlsx 180종목 유니버스, 6탭)
```

Story 작성 규칙은 `market-summary` 스킬에 있다 (Story 작업 시 자동 로드).

**주의**: 미래 날짜의 보고서를 미리 생성하지 않는다.

**필수**: 날짜-요일 매핑을 절대 추측하지 않는다. Story/보고서에 요일을 쓰기 전 반드시:
```bash
.venv/bin/python scripts/calendar_check.py YYYY-MM-DD [--month | --week WNN]
```

## 구조

```
generate.py               # HTML 보고서 생성 (collect_market import + Snowflake dual-write)
generate_periodic.py      # 주간/월간/분기 집계 (--only {weekly|monthly|quarterly} --quarter N)
generate_weekly_pm.py     # 금요일 오전 PM 브리프 (월~목 4영업일 윈도우 + Today Residual + W+1 Outlook)
generate_sector_country.py # 섹터·국가 보고서 (레거시 — 2026-05-26 폐기, 참조용 보존)
scripts/generate_asia_weekly.py  # 아시아 주간 브리프 (xlsx 180종목 ↔ market_data.csv 매칭 + 6탭 스켈레톤)
market_source.py         # Snowflake MKT100/MKT200 리더 (CSV fallback) — 모든 reader 의 단일 진입점
snowflake_loader.py       # CSV ↔ Snowflake 적재 유틸
notify_telegram.py       # Telegram 알림 (개인 + 그룹 동시 발송)
simulate.py               # 과거 날짜 시뮬레이션
gen_assets.py             # 브랜드 에셋 생성 (favicon, OG image)
history/market_data.csv       # 일별 시계열 (10컬럼 대문자)
history/macro_indicators.csv  # 거시지표 시계열 (7컬럼 대문자)
history/아시아종목.xlsx       # 아시아 운용 유니버스 180종목 (asia-weekly 입력)

collectors/
├── collect_market.py             # 메인 시장 데이터 수집 (TICKERS/INDICATOR_CODES + fetch_data/build_report_data)
├── io_utils.py                   # CSV 공통 유틸 (load_csv_dedup, append_save_csv)
├── macro_indicators.yaml         # FRED + ECOS 매크로 지표 코드 정의
├── macro.py                      # 거시지표 수집 (FRED + ECOS)
├── sector_etfs.py                # US 섹터/스타일/채권 ETF 이력 백필 (KR 섹터 ETF는 2026-05-07 제거)
├── krx_sectors.py                # KOSPI 200 GICS 섹터 지수 (IX_KR_*, KR 섹터 단일 정본)
├── stocks_universe.py            # KR Top50 + US S&P500 Top50 + ASIA_TOP 130종목 (중국·일본·인도·대만·베트남·호주·홍콩·인니) 백필·dim 시드 (--seed-dim)
└── valuation.py                  # KOSPI PER/PBR/배당수익률

scripts/
├── auto_market.py                    # 일일 자동화 (일 18:50 + 화~금 06:50 KST, 한국 공휴일 반영)
├── collect_weekly.py                 # 주간 수집 러너 (일 19:30 KST)
├── collect_securities_reports.py     # 미래에셋증권 상세분석 보고서 → S3
├── collect_prism_reports.py          # MVP PRISM 보고서 → S3 (증분 스캔)
├── generate_ocr_story.py             # 일일 브리핑 PDF → 1차 자료 보존 HTML (PDF 본문 = 발간 전일 미국 마감, 메인 Market Story 와 시점·역할 분리)
├── generate_securities_digest.py     # 증권 보고서 Claude 분석 → 주간 다이제스트
├── verify_report_numbers.py          # 보고서 수치 결정론 검증 (상세 로그: logs/verify_numbers.log)
├── verify_snowflake_drift.py         # Snowflake ↔ CSV 정합성 비교
├── calendar_check.py                 # 영업일 검증·날짜 포맷터
├── backfill_us_yields.py             # US 수익률 곡선 백필 (investiny)
├── generate_fund_index.py            # output/fund/index.html (S3 pre-signed URL)
├── generate_securities_index.py      # output/research/securities/index.html
├── generate_prism_index.py           # output/prism/index.html (5개 카테고리 탭)
├── html_to_pdf.py                    # HTML → PDF 변환 (Playwright Chromium, --tab/--exclude 옵션)
├── windows/                          # Windows Task Scheduler 자동화
│   ├── run_auto_market.ps1           # 일일 보고서 PS1 래퍼
│   ├── run_ocr_story.ps1             # OCR Story PS1 래퍼
│   ├── run_collect_weekly.ps1        # 주간 수집 PS1 래퍼
│   ├── run_asia_weekly.ps1           # 아시아 주간 PS1 래퍼
│   ├── market_summary_task.xml       # 태스크 정의: 일 18:50 + 화~금 06:50
│   ├── market_ocr_task.xml           # 태스크 정의: 월~금 08:30
│   ├── securities_reports_task.xml   # 태스크 정의: 일 19:30
│   ├── asia_weekly_task.xml          # 태스크 정의: 일 20:00
│   └── setup_windows_tasks.ps1       # 4개 태스크 일괄 등록 스크립트
└── macos/                            # macOS launchd 자동화 (레거시 참고용 — 현재 운영은 Windows Task Scheduler)
    ├── com.lifesailor.market-summary.plist       # launchd: 일일 보고서
    ├── com.lifesailor.market-ocr.plist           # launchd: 일일 OCR Story
    ├── com.lifesailor.securities-reports.plist   # launchd: 주간 수집
    └── com.lifesailor.asia-weekly.plist          # launchd: 주간 아시아 브리프

db/
├── MKT.sql              # Snowflake MKT100/MKT200 DDL (정본)
├── FND.sql              # Snowflake FND 계열 DDL (market-strategy 참조용)
└── migrate.py           # 스키마 생성/마이그레이션 유틸

views/                   # 섹터·국가 분석 엔진 (레거시 — generate_sector_country.py 전용)
                         #   ※ sector_view, country_view, _shared. 나머지 8개 의사결정 뷰는 market-strategy/ 로 이관
```

> **2026-04 리팩토링**: `portfolio/` 디렉터리는 `market-strategy/` (별도 리포)로 이관. market_summary 는 summary/research 만 담당.
> 자세한 매핑은 [docs/data-sources.md](docs/data-sources.md). market-strategy 코드: `/Users/lifesailor/Desktop/kosmos/ai/investment/market-strategy`.

## 데이터

- **Snowflake MKT100_MARKET_DAILY 가 단일 정본**. CSV 는 legacy mirror + simulate.py fallback
- 모든 reader 는 `market_source` 경유
- Macro View 만 `history/macro_indicators.csv` 사용
- 파생 지표: US 10-2 Spread (`BD_US_10_2_SPREAD`), KR 10-3 Spread (`BD_KR_10_3_SPREAD`) — 수집 시 자동 계산·적재

### Clone 후 1회 셋업 (2026-05-14~)
`history/market_data.csv` 는 git 추적 제외 (GitHub 50MB 한계). 새 환경에서는 Snowflake 에서 재생성:
```
.venv/bin/python snowflake_loader.py --download
```
일일 자동화는 dual-write 로 CSV/Snowflake 동기 유지되므로 1회만 실행하면 됨.

### 데이터 규모 (2026-05-18 기준)

| 파일 | 행수 | 지표 수 | 기간 |
|------|------|--------|------|
| `history/market_data.csv` | 약 80만 행 | 315개 | 2010~현재 |
| `history/macro_indicators.csv` | 약 5만 7천 행 | 43개 | 2010~현재 |
| `history/아시아종목.xlsx` | 180행 | 8개 시트 (국가별) | 운용 유니버스 (정적) |

**market_data 카테고리 (315개 지표)**:
- stocks(234) · equity(19) · bond(16) · sector_us(11) · index_kr(11) · fx(8) · commodity(6) · style_us(5) · valuation(3) · risk(2)
- `stocks` (234종목, 약 58만 행):
  - KR Top50 (KOSPI 시총 상위, `collectors/stocks_universe.KR_TOP50`)
  - US Top50 (S&P500 시총 상위, `US_TOP50`)
  - ASIA_TOP 130종목 (`ASIA_TOP`) — 2026-05-18 asia-weekly 확장으로 65 → 130개로 증가
    - 중국 52 · 일본 32 · 인도 28 · 베트남 10 · 대만 5 · 호주 2 · 인도네시아 1 · 홍콩 1 · ADR 1
  - ADR/HK 4종 (TSMC·BABA·MEITUAN·TENCENT)
- KR 섹터는 `index_kr` (KRX GICS 11종) 으로 일원화. 종전 `sector_kr` (TIGER/KODEX ETF 25종) 는 2026-05-07 제거.
- Dashboard 표시 (2026-05-07 부): **한국 주식 Top 20** + **미국 주식 Top 20** + ADR/HK 4종으로 분리, 각각 시가총액 순 (`report_utils.KR_STOCK_ORDER` / `US_STOCK_ORDER` — `collectors/stocks_universe.KR_TOP50` / `US_TOP50` 직접 import). 표시 갯수는 `KR_STOCK_TOP_N` / `US_STOCK_TOP_N` 상수.
- YTD 계산: 글로벌 ye_date(전년 마지막 영업일) 에 ticker 데이터가 없으면 그 ticker 가 가졌던 마지막 전년도 종가로 자동 fallback (예: KR Top50 백필이 2025-12-31 누락 시 2025-12-30 사용).
- 신규 종목 추가: `collectors/stocks_universe.py` 의 `KR_TOP50` / `US_TOP50` / `ASIA_TOP` 수정 후 `--seed-dim` 으로 dim 등록, `--start` 로 백필.

**아시아종목.xlsx 매칭률 (2026-05-18 기준)**:
- 180종목 중 CSV 매칭 133종목 (74%) — 대만·호주·인니·베트남 100%, 인도 79%, 중국 73%, 일본 73%, 홍콩 11%
- 미매칭 47종목: xlsx에 티커 없음 45 + yfinance 미지원 2 (Tata Motors `TATAMOTORS.NS`, Orient Overseas `OOIL`)
- 보강 계획: xlsx 티커 컬럼 채우기 → ASIA_TOP 추가 → 백필

**macro_indicators 카테고리 (43개 지표)**:
- inflation · employment · growth · policy · rates · credit · activity · liquidity · sentiment · fx · risk

자세한 소스·스키마·수집 대상: [docs/data-sources.md](docs/data-sources.md)

## 핵심 함수

- `_inject_existing_story(path, new_html)`: 보고서 재생성 시 기존 Story 보존
- `_save_story_file(html_path, html_content)`: HTML에서 Story 추출 → `_story.html` 별도 저장

## 환경

- Python 3.12 (`.venv/` 로컬 venv 사용, 시스템 python 금지)
- 환경변수 (`.env`): `ECOS_API_KEY`, `FRED_API_KEY`, `SNOWFLAKE_*` (6개), `AWS_*` (4개), `TELEGRAM_*` (3개)

## 주의사항

- 일간 HTML 보고서는 **7개 탭** 구성: CS Story · PM Story · Market Story · **Stocks (신규)** · Data Dashboard · Macro & Events · Sources
- **Stocks 탭**: `generate.py` 가 한국 Top 20 + 미국 Top 20 + 아시아 Top 20 + 기타 4섹션 표를 자동 생성. 그 위에 `STOCKS_STORY_PLACEHOLDER` 영역을 Claude 가 3~5 단락 종목 해설로 채움. Major Stocks 10종은 Data 탭에서 제거되어 Stocks 탭으로 이관 (2026-05-19)
- Story 없으면 placeholder 유지
- `generate.py` dual-write 는 `--start` 없이 실행한 일간 수집에만 작동. 전체 재수집은 `snowflake_loader.py --truncate`

## 주간 테마 리서치 (일요일 수동 발행)

`/research [YYYY-MM-DD]` 한 줄로 발행. 해당 주 OCR 브리핑(`*_ocr.html`)을 읽고 핵심 테마 1~2개를 선정해 심층 분석 보고서를 작성한다.

산출물: `output/research/daily/YYYY-MM/YYYY-MM-DD.html`

> **이전 섹터·국가 11일 순환 사이클** (`generate_sector_country.py`)은 2026-05-26 폐기. `generate_sector_country.py` 파일은 참조용으로 보존.

## Weekly PM Brief (금요일 오전 발행)

정식 weekly Summary (월~금 5영업일, 일요일 발행) 와 별개로, **그 주 월~목 4영업일 누적**을 매니저 톤으로 정리한 금요일 오전 브리프. `/weekly-pm YYYY-MM-DD` 한 줄로 발행.

**산출물 (`output/weekly-pm/YYYY-MM-DD.{html,pdf,_no-data.pdf,_pm.html}`)**

| 파일 | 구성 |
|------|------|
| `{date}.html` | Data Dashboard + PM Brief (회고 6 섹션 + Outlook) |
| `{date}_pm.html` | PM 탭 sibling (PM 본문만) |
| `{date}.pdf` | 풀 PDF (12p 내외, Data Dashboard 포함) |
| `{date}_no-data.pdf` | PM 중심 PDF (5p 내외, Data 제외) |

**워크플로우 5 단계** (스킬: `weekly-pm`)
1. 영업일 검증 (`calendar_check.py` + 한국 공휴일 자동 제외)
2. HTML skeleton 생성 (`generate_weekly_pm.py {date}`)
3. PM Story 6 섹션 (한국·매크로·아시아·미국·유럽·채권) + Outlook 5 블록 (Today Residual / Bull·Base·Bear / 캘린더 / 리스크 Top 3 / 포지셔닝)
4. HTML 주입 + `_pm.html` sibling 동기화
5. PDF 2종 (`scripts/html_to_pdf.py {html}` + `--exclude data`)

**4영업일 윈도우 특수성**
- "Weekly" 컬럼 = 직전 금요일 종가 → 그 주 목요일 종가 (정식 5영업일 WTD 와 다름)
- 한국 공휴일 끼면 자동 3영업일로 단축 (예: W19 어린이날 5/5 → 5/4·5/6·5/7)
- Today Residual 박스만 forward-looking 허용 (당일 NFP·ECB·어닝 등 잔여 변수)
- W+1 Outlook 도 forward-looking 화이트리스트 (`outlook-divider` / `scenario-grid` 클래스)

**PDF 변환** (`scripts/html_to_pdf.py`)
- Playwright headless Chromium (Chart.js·Spoqa 한글 폰트 호환)
- 빈 탭(placeholder only) 자동 hide / 카드 page-break-inside 보호 / 마지막 가시 탭 break-after 해제
- 옵션: `--tab pm` (특정 탭만), `--exclude data,sources` (탭 제외, 쉼표 구분), `--out PATH`

## 자동화 스케줄

| 시간 | 스크립트 | 태스크 (Windows) | 내용 |
|------|----------|-----------------|------|
| 일 18:50 KST | `auto_market.py` | `MarketSummary-Daily` ✅ | 금요일 보고서 (market-full + Snowflake drift 검증) |
| 화~금 06:50 KST | `auto_market.py` | `MarketSummary-Daily` ✅ | 전날 보고서 (한국 공휴일 자동 건너뜀, `holidays` 라이브러리) |
| 월~금 08:30 KST | `generate_ocr_story.py` | `MarketSummary-OCR` ✅ | 미래에셋 PDF → `_ocr.html` 1차 자료 보존 (월요일은 금요일 발간분 처리, 메인 Market Story 와 별트랙) |
| 일 19:30 KST | `collect_weekly.py` | `MarketSummary-WeeklyCollect` ✅ | ① 미래에셋증권 상세분석 → S3 ② MVP PRISM → S3 ③ Securities/Fund Index 재생성 (pre-signed URL 7일 갱신) |
| 일 20:00 KST | `generate_asia_weekly.py` | `MarketSummary-AsiaWeekly` ✅ | 아시아 주간 브리프 스켈레톤 + 데이터 자동 생성 (`collect_weekly` 30분 마진). Story 본문은 Claude 수동 작성 |

**Windows Task Scheduler 상태** (2026-05-26 기준):
- ✅ Active 4개: `MarketSummary-Daily`, `MarketSummary-OCR`, `MarketSummary-WeeklyCollect`, `MarketSummary-AsiaWeekly`
- 태스크 정의: `scripts/windows/*.xml` / PS1 래퍼: `scripts/windows/run_*.ps1`
- 상태 확인: `Get-ScheduledTask | Where-Object { $_.TaskName -like "MarketSummary*" } | Get-ScheduledTaskInfo`

**기타 운영 정보**:
- 증권 보고서: `anthillia/miraeasset-securities/YYYY-MM/` (직전 영업주 스크래핑)
- PRISM 보고서: `prism/<카테고리>/YYYY/MM/` (증분 스캔, `logs/prism_last_page.txt` 추적)
- 수동: `--week-of YYYY-MM-DD` (증권), `--full` (PRISM 전체 재스캔)
- Windows Task Scheduler DaysOfWeek 비트마스크: Sun=1, Mon=2, Tue=4, Wed=8, Thu=16, Fri=32, Sat=64

## Asia Weekly Brief (일요일 오후 발행)

글로벌 weekly Summary 와 별개로, **아시아 종목 유니버스 180개**(중국·일본·인도·대만·홍콩·베트남·호주·인니)에 초점을 둔 주간 시황. `history/아시아종목.xlsx` 가 운용 유니버스의 단일 정본.

**산출물 (`output/summary/weekly/YYYY-WNN_asia.{html, _data.json}`)**

| 파일 | 구성 |
|------|------|
| `{week}_asia.html` | 메인 6탭 보고서 (~720 줄) |
| `{week}_asia_data.json` | 추출 데이터 (Claude 입력용) |

**6탭 구성**
1. **Asia Story** — Hero 3단락 + 인과체인 5노드 + 인사이트 6카드
2. **Country Drilldown** — 🇨🇳·🇯🇵·🇹🇼·🇮🇳·🇭🇰·🇰🇷 6 섹션
3. **Themes** — 횡단 주제 4~5개 (반도체 디커플링·달러 강세·AI 인프라·정책 리스크·지정학)
4. **Data** — 지수 8 + 환율 5 + 종목 TOP/BOTTOM 20 + 국가별 종합
5. **Outlook** — Bull/Base/Bear 시나리오 + 리스크 TOP 5 + W+1 캘린더
6. **Sources** — 데이터 출처·증권사 디지스트 4건·외부 자료·산출 방법론

**워크플로우 5 단계** (스킬: `asia-weekly`, 커맨드: `/asia-weekly`)
1. 캘린더 검증 (`calendar_check.py --week W##`)
2. 스켈레톤 + 데이터 자동 생성 (`generate_asia_weekly.py {date}`) — Data 탭 + KPI 자동 채움
3. 미래에셋증권 디지스트 4건 (W##-3 ~ W##) 읽기
4. 5탭 본문 작성 (Story·Country·Themes·Outlook·Sources)
5. 검증 (`post_edit_write_structure_guard.py` + `verify_report_numbers.py`)

**유니버스 매칭 메커니즘**
- xlsx 종목명 ↔ `market_data.csv` TICKER 컬럼 정확 매칭
- 매칭 종목만 WTD% 계산 + 국가별 단순·가중 평균
- 미매칭 종목 (xlsx 티커 없음 또는 yfinance 미지원) 은 Sources 탭에 한계 명시
- 2026-05-18 기준 매칭률: 133/180 (74%) — collectors 확장 후

**자동화**: `MarketSummary-AsiaWeekly` 태스크가 매주 일요일 20:00 KST 호출 (collect_weekly 30분 마진). 데이터 준비만 자동, Story 본문은 Claude 수동.

## 품질 자동 검증 (이중 구조)

market-full 워크플로우는 두 개의 독립 검증 레이어를 거친다:

### 1. Story 시간 정확성 검증 (PostToolUse 훅, type: "prompt")

Story 작성 중 Edit/Write 직후 자동 실행. 검증 실패 시 `reason`을 Claude에게 피드백 → **자동 수정 재시도 루프** (사용자 개입 없이 자동 교정, Task Scheduler 완전 자동화 가능).

- Check 1: Forward-looking 금지 (D+1 08:00 KST 이후 데이터 사용 금지)
- Check 2: 세션 간 시간 정확성 (아시아 서술에 유럽 데이터 사용 금지 등)
- Check 3: 인과관계 방향 ("월요일 하락이 수요일 반등의 서막" 표현 금지)
- Check 4: 주간/월간 내 일간 간 참조 순서

### 2. 보고서 수치 결정론 검증 (Stop 훅)

turn 종료 시마다 자동 호출. Story 본문의 종가·등락률·bp 변화를 `history/market_data.csv` ground truth와 대조.

검증 패턴 7개: KPI 카드 / 본문 명시 % / 본문 명시 bp / HL span 인라인 / 마크다운 표 3컬럼 / COMBO 묶음(자산 ±N%(종가)) / **종목 일변동률(T1, 14개 핵심 stocks — Apple·NVIDIA·Samsung·TSMC 등)**.

```bash
.venv/bin/python scripts/verify_report_numbers.py --auto --telegram
```

`--auto` 실행 시 상세 로그가 `logs/verify_numbers.log`에 자동 누적 기록된다.

상세: [docs/verify-numbers.md](docs/verify-numbers.md)

## 로깅

모든 Step 진행 상태가 `logs/market-full-YYYY-MM-DD.log`에 자동 기록된다.

```
logs/
├── market-full-YYYY-MM-DD.log   # generate.py Step 메시지
├── auto_market.log              # Task Scheduler 자동 실행 로그
├── ocr_story.log                # OCR Story 생성 로그
├── verify_numbers.log           # 수치 검증 상세 로그
└── securities_reports.log       # 증권 보고서 수집 로그
```

- `[SNOWFLAKE] OK/FAILED/SKIP` 마커로 Snowflake 적재 결과 추적
- `✅ [Step X]`, `⚠ [Step X]`, `⊘ [Step X]` 마커로 Step별 결과 확인

## 관련 설정

- `.claude/settings.json`: Story 시간 정확성 검증 훅 (PreToolUse/PostToolUse, type: "prompt") + Stop 훅 (수치 자동 검증)
- `.claude/hooks/post_edit_write_structure_guard.py`: HTML 구조·CSS 화이트리스트 검증 (필수 섹션 5개 + tab-story 블록 클래스 검사; `index.html` 자동 제외)
- `.claude/skills/`: `market-summary` (+ **`references/stocks.md`** 신규), `macro-events`, `mali-etf-analysis`, `weekly-pm`, **`asia-weekly`** (신규) ※ `sector-country` 스킬은 레거시
- `.claude/commands/`: `/market-data`, `/market-deploy`, `/market-full` (**Step 3-D Stocks Story** 신규), `/market-pm`, `/market-cs`, `/research` (**OCR 기반 주간 테마 리서치**), `/review-story`, `/weekly-pm`, **`/asia-weekly`** (신규)

## 상세 문서

- [docs/operations.md](docs/operations.md) — 운영 매뉴얼·자동화 스케줄·누락 시 수동 복구 절차
- [docs/data-sources.md](docs/data-sources.md) — 수집 대상·소스·CSV 스키마·Snowflake 연동
- [docs/verify-numbers.md](docs/verify-numbers.md) — 보고서 수치 자동 검증 (패턴·가드·운영 가이드)
- [docs/fund-analysis.md](docs/fund-analysis.md) — Fund S3 저장소·pre-signed URL·재생성
- Portfolio Agent / View Agent / Sector Rotation 문서는 [market-strategy](file:///Users/lifesailor/Desktop/kosmos/ai/investment/market-strategy) 리포로 이전
- [docs/output-structure.md](docs/output-structure.md) — output/ 디렉터리 트리·보고서 탭 구성
- [docs/VISION.md](docs/VISION.md) — 3단계 비전 (도구 → 협업 에이전트 → 자율 운용)
