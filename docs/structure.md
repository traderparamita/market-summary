# 프로젝트 구조

## 파일 트리

```
generate.py               # HTML 보고서 생성 (collect_market import + Snowflake dual-write)
generate_periodic.py      # 주간/월간/분기 집계 (--only {weekly|monthly|quarterly} --quarter N)
generate_sector_country.py # 섹터·국가 보고서 (레거시 — 2026-05-26 폐기, 참조용 보존)
scripts/generate_asia_weekly.py  # 아시아 주간 브리프 (xlsx 180종목 ↔ market_data.csv 매칭 + 6탭 스켈레톤)
market_source.py          # Snowflake MKT100/MKT200 리더 (CSV fallback) — 모든 reader의 단일 진입점
snowflake_loader.py       # CSV ↔ Snowflake 적재 유틸
notify_telegram.py        # Telegram 알림 (개인 + 그룹 동시 발송)
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
├── stocks_universe.py            # KR Top50 + US S&P500 Top50 + ASIA_TOP 130종목 백필·dim 시드 (--seed-dim)
└── valuation.py                  # KOSPI PER/PBR/배당수익률

scripts/
├── auto_market.py                    # 일일 자동화 (일 18:50 + 화~금 06:50 KST, 한국 공휴일 반영)
├── collect_weekly.py                 # 주간 수집 러너 (일 19:30 KST)
├── collect_securities_reports.py     # 미래에셋증권 상세분석 보고서 → S3
├── collect_prism_reports.py          # MVP PRISM 보고서 → S3 (증분 스캔)
├── generate_ocr_story.py             # 일일 브리핑 PDF → 1차 자료 보존 HTML
├── generate_securities_digest.py     # 증권 보고서 Claude 분석 → 주간 다이제스트
├── generate_research.py              # 일간 테마 리서치 자동 생성
├── verify_report_numbers.py          # 보고서 수치 결정론 검증 (logs/verify_numbers.log)
├── verify_snowflake_drift.py         # Snowflake ↔ CSV 정합성 비교
├── calendar_check.py                 # 영업일 검증·날짜 포맷터
├── backfill_us_yields.py             # US 수익률 곡선 백필 (investiny)
├── generate_fund_index.py            # output/fund/index.html (S3 pre-signed URL)
├── generate_securities_index.py      # output/securities/index.html
├── generate_prism_index.py           # output/prism/index.html (5개 카테고리 탭)
├── html_to_pdf.py                    # HTML → PDF 변환 (Playwright Chromium, --tab/--exclude 옵션)
├── windows/                          # Windows Task Scheduler 자동화
│   ├── run_auto_market.ps1
│   ├── run_ocr_story.ps1
│   ├── run_collect_weekly.ps1
│   ├── run_asia_weekly.ps1
│   ├── run_daily_research.ps1        # 월~금 18:50 KST 테마 리서치 래퍼
│   ├── market_summary_task.xml       # 일 18:50 + 화~금 06:50
│   ├── market_ocr_task.xml           # 월~금 08:30
│   ├── securities_reports_task.xml   # 일 19:30
│   ├── asia_weekly_task.xml          # 일 20:00
│   ├── daily_research_task.xml       # 월~금 18:50
│   └── setup_windows_tasks.ps1       # 5개 태스크 일괄 등록
└── macos/                            # macOS launchd (레거시 참고용)

db/
├── MKT.sql              # Snowflake MKT100/MKT200 DDL (정본)
├── FND.sql              # Snowflake FND 계열 DDL (market-strategy 참조용)
└── migrate.py           # 스키마 생성/마이그레이션 유틸

views/                   # 섹터·국가 분석 엔진 (레거시 — generate_sector_country.py 전용)
```

> **2026-04 리팩토링**: `portfolio/` 디렉터리는 `market-strategy/` (별도 리포)로 이관. market_summary는 summary/research만 담당.

## 핵심 함수

- `_inject_existing_story(path, new_html)` — 보고서 재생성 시 기존 Story 보존
- `_save_story_file(html_path, html_content)` — HTML에서 Story 추출 → `_story.html` 별도 저장

## 관련 설정

- `.claude/settings.json` — Story 시간 정확성 검증 훅 (PreToolUse/PostToolUse) + Stop 훅 (수치 검증)
- `.claude/hooks/post_edit_write_structure_guard.py` — HTML 구조·CSS 화이트리스트 검증 (필수 섹션 5개; `index.html` 자동 제외)
- `.claude/skills/` — `market-summary`, `macro-events`, `mali-etf-analysis`, `asia-weekly`, `sector-country` ※ `weekly-pm`은 제거됨
- `.claude/commands/` — `/market-data`, `/market-deploy`, `/market-full`, `/market-pm`, `/market-cs`, `/research`, `/review-story`, `/asia-weekly`

## 로깅

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
