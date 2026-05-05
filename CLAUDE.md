# Market Summary

일일/주간/월간 글로벌 시장 요약 보고서를 자동 생성하는 프로젝트.

## 실행 방법

```
/market-full [YYYY-MM-DD]    # 데이터 수집 → Dashboard → Story(일/주/월) → 배포
/market-data [YYYY-MM-DD]    # 데이터 수집 + Data Dashboard만
/market-deploy               # output/ 변경분 commit + push
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
generate_sector_country.py # 섹터·국가 보고서 (11일 사이클)
market_source.py         # Snowflake MKT100/MKT200 리더 (CSV fallback) — 모든 reader 의 단일 진입점
snowflake_loader.py       # CSV ↔ Snowflake 적재 유틸
notify_telegram.py       # Telegram 알림 (개인 + 그룹 동시 발송)
simulate.py               # 과거 날짜 시뮬레이션
gen_assets.py             # 브랜드 에셋 생성 (favicon, OG image)
history/market_data.csv       # 일별 시계열 (10컬럼 대문자)
history/macro_indicators.csv  # 거시지표 시계열 (7컬럼 대문자)

collectors/
├── collect_market.py             # 메인 시장 데이터 수집 (TICKERS/INDICATOR_CODES + fetch_data/build_report_data)
├── io_utils.py                   # CSV 공통 유틸 (load_csv_dedup, append_save_csv)
├── macro_indicators.yaml         # FRED + ECOS 매크로 지표 코드 정의
├── macro.py                      # 거시지표 수집 (FRED + ECOS)
├── sector_etfs.py                # 섹터/스타일 ETF 이력 백필
├── krx_sectors.py                # KOSPI 200 GICS 섹터 지수
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
├── com.lifesailor.market-summary.plist       # launchd: 일일 보고서
├── com.lifesailor.market-ocr.plist           # launchd: 일일 OCR Story
└── com.lifesailor.securities-reports.plist   # launchd: 주간 수집

db/
├── MKT.sql              # Snowflake MKT100/MKT200 DDL (정본)
├── FND.sql              # Snowflake FND 계열 DDL (market-strategy 참조용)
└── migrate.py           # 스키마 생성/마이그레이션 유틸

views/                   # 섹터·국가 분석 엔진 (sector_view, country_view, _shared)
                         #   ※ generate_sector_country.py 가 직접 import. 나머지 8개 의사결정 뷰는 market-strategy/ 로 이관
```

> **2026-04 리팩토링**: `portfolio/` 디렉터리는 `market-strategy/` (별도 리포)로 이관. market_summary 는 summary/research 만 담당.
> 자세한 매핑은 [docs/data-sources.md](docs/data-sources.md). market-strategy 코드: `/Users/lifesailor/Desktop/kosmos/ai/investment/market-strategy`.

## 데이터

- **Snowflake MKT100_MARKET_DAILY 가 단일 정본**. CSV 는 legacy mirror + simulate.py fallback
- 모든 reader 는 `market_source` 경유
- Macro View 만 `history/macro_indicators.csv` 사용
- 파생 지표: US 10-2 Spread (`BD_US_10_2_SPREAD`), KR 10-3 Spread (`BD_KR_10_3_SPREAD`) — 수집 시 자동 계산·적재

### 데이터 규모 (2026-04 기준)

| 파일 | 행수 | 지표 수 | 기간 |
|------|------|--------|------|
| `history/market_data.csv` | 약 30만 6천 행 | 120개 | 2010~현재 |
| `history/macro_indicators.csv` | 약 5만 7천 행 | 43개 | 2010~현재 |

**market_data 카테고리 (120개 지표)**:
- equity(19) · bond(16) · sector_kr(25) · sector_us(11) · index_kr(11) · stocks(14) · fx(8) · style_us(5) · commodity(6) · valuation(3) · risk(2)

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

- HTML 보고서는 Data 탭 + Story 탭 구성. Story 없으면 placeholder 유지
- `generate.py` dual-write 는 `--start` 없이 실행한 일간 수집에만 작동. 전체 재수집은 `snowflake_loader.py --truncate`

## 섹터·국가 사이클

`generate_sector_country.py`의 `get_focus(date)` 로 자동 계산. 기준일 2026-01-05, 영업일 기준 독립 순환.
국가: KR(1)·US(2)·CN(3)·JP(4)·EU(5)·UK(6)·DE(7)·FR(8)·IN(9)·TW(10)·EM(11)

## 자동화 스케줄

| 시간 | 스크립트 | 내용 |
|------|----------|------|
| 일 18:50 KST | `auto_market.py` | 금요일 보고서 (market-full + Snowflake drift 검증) |
| 화~금 06:50 KST | `auto_market.py` | 전날 보고서 (한국 공휴일 자동 건너뜀, `holidays` 라이브러리) |
| 일+화~금 08:30 KST | `generate_ocr_story.py` | 미래에셋 PDF → `_ocr.html` 1차 자료 보존 (메인 Market Story 와 별트랙) |
| 일 19:30 KST | `collect_weekly.py` | ① 미래에셋증권 상세분석 → S3 ② MVP PRISM → S3 |

- 증권 보고서: `anthillia/miraeasset-securities/YYYY-MM/` (직전 영업주 스크래핑)
- PRISM 보고서: `prism/<카테고리>/YYYY/MM/` (증분 스캔, `logs/prism_last_page.txt` 추적)
- 수동: `--week-of YYYY-MM-DD` (증권), `--full` (PRISM 전체 재스캔)

## 품질 자동 검증 (이중 구조)

market-full 워크플로우는 두 개의 독립 검증 레이어를 거친다:

### 1. Story 시간 정확성 검증 (PostToolUse 훅, type: "prompt")

Story 작성 중 Edit/Write 직후 자동 실행. 검증 실패 시 `reason`을 Claude에게 피드백 → **자동 수정 재시도 루프** (사용자 개입 없이 자동 교정, launchd 완전 자동화 가능).

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
├── market-full-YYYY-MM-DD.log   # generate.py + generate_sector_country.py Step 메시지
├── auto_market.log              # launchd 자동 실행 로그
├── ocr_story.log                # OCR Story 생성 로그
├── verify_numbers.log           # 수치 검증 상세 로그
└── securities_reports.log       # 증권 보고서 수집 로그
```

- `[SNOWFLAKE] OK/FAILED/SKIP` 마커로 Snowflake 적재 결과 추적
- `✅ [Step X]`, `⚠ [Step X]`, `⊘ [Step X]` 마커로 Step별 결과 확인

## 관련 설정

- `.claude/settings.json`: Story 시간 정확성 검증 훅 (PreToolUse/PostToolUse, type: "prompt") + Stop 훅 (수치 자동 검증)
- `.claude/skills/`: `market-summary`, `sector-country`, `macro-events`, `mali-etf-analysis`
- `.claude/commands/`: `/market-data`, `/market-deploy`, `/market-full`, `/market-pm`, `/market-cs`, `/research`, `/review-story`

## 상세 문서

- [docs/data-sources.md](docs/data-sources.md) — 수집 대상·소스·CSV 스키마·Snowflake 연동
- [docs/verify-numbers.md](docs/verify-numbers.md) — 보고서 수치 자동 검증 (패턴·가드·운영 가이드)
- [docs/fund-analysis.md](docs/fund-analysis.md) — Fund S3 저장소·pre-signed URL·재생성
- Portfolio Agent / View Agent / Sector Rotation 문서는 [market-strategy](file:///Users/lifesailor/Desktop/kosmos/ai/investment/market-strategy) 리포로 이전
- [docs/output-structure.md](docs/output-structure.md) — output/ 디렉터리 트리·보고서 탭 구성
- [docs/VISION.md](docs/VISION.md) — 3단계 비전 (도구 → 협업 에이전트 → 자율 운용)
