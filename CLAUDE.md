# Market Summary

일일/주간/월간 글로벌 시장 요약 보고서를 자동 생성하는 프로젝트.

## 실행 방법

```
/market-full [YYYY-MM-DD]    # 데이터 수집 → Dashboard → Story → 배포
/market-data [YYYY-MM-DD]    # 데이터 수집 + Data Dashboard만
/market-deploy               # output/ 변경분 commit + push
/research [YYYY-MM-DD]       # 일간 테마 리서치
/asia-weekly [YYYY-MM-DD]    # 아시아 주간 시황 (xlsx 180종목, 6탭)
```

## 필수 규칙

- **미래 날짜 보고서 생성 금지**
- **요일 추측 금지** — Story에 요일 쓰기 전 반드시:
  ```bash
  .venv/bin/python scripts/calendar_check.py YYYY-MM-DD [--month | --week WNN]
  ```
- Story 작성 규칙은 `market-summary` 스킬에 있다 (작업 시 자동 로드)

## 환경

- Python 3.12 (`.venv/` 로컬 venv, 시스템 python 금지)
- 환경변수 (`.env`): `ECOS_API_KEY`, `FRED_API_KEY`, `RDS_*` (5개), `AWS_*` (4개), `TELEGRAM_*` (3개)
- 새 환경 1회 셋업: `.venv/bin/python rds_loader.py --download`

## 보고서 구성

일간 HTML 보고서 **7개 탭**: CS Story · PM Story · Market Story · Stocks · Data Dashboard · Macro & Events · Sources

- **Stocks 탭**: `generate.py`가 KR Top20 + US Top20 + Asia Top20 표 자동 생성. `STOCKS_STORY_PLACEHOLDER`를 Claude가 3~5단락으로 채움
- **데이터 정본**: RDS PostgreSQL `mkt100_market_daily`. 모든 reader는 `market_source` 경유. CSV는 fallback
- `generate.py`의 RDS 통합 upsert는 `--start` 없는 일간 수집에만 작동. 전체 재수집은 `rds_loader.py --truncate`

## 상세 문서

- [docs/structure.md](docs/structure.md) — 파일 구조·핵심 함수·설정·로그
- [docs/operations.md](docs/operations.md) — 자동화 스케줄·운영·복구 절차
- [docs/data-sources.md](docs/data-sources.md) — 수집 대상·CSV 스키마·RDS 연동
- [docs/research.md](docs/research.md) — 일간 테마 리서치 파이프라인
- [docs/asia-weekly.md](docs/asia-weekly.md) — Asia Weekly Brief
- [docs/verify-numbers.md](docs/verify-numbers.md) — 수치 자동 검증
- [docs/output-structure.md](docs/output-structure.md) — output/ 디렉터리 구조
- [docs/fund-analysis.md](docs/fund-analysis.md) — Fund S3 저장소
- [docs/VISION.md](docs/VISION.md) — 프로젝트 비전
