# 일간 테마 리서치

장 마감 후 자동 발행. `/research [YYYY-MM-DD]` 한 줄로 수동 발행.  
자동은 `MarketSummary-DailyResearch` 태스크가 **월~금 18:50 KST**에 실행 (`scripts/windows/run_daily_research.ps1`).

**산출물**: `output/research/daily/YYYY-MM/YYYY-MM-DD.html` + `_story.html` sibling  
**허브**: `output/research/index.html` — `_update_sc_index()` 호출 시 최신 일간 HTML을 그대로 복사 (카드 목록 아님)

## 자동화 파이프라인 (`scripts/generate_research.py`)

3-Signal 교차 검증으로 테마를 선정한다.

| 신호 | 분류 | 처리 |
|------|------|------|
| Naver 오늘 수익률 양수 + 7일 지속성 ≥ 60% | ✅ 1순위 | 메인 테마로 선정 |
| Naver 오늘 수익률 상위 + Tavily 글로벌 트리거 확인 | ⚡ 2순위 | 글로벌 연결고리 있는 테마 |
| Naver 오늘 수익률 상위 (글로벌 미확인) | 📋 참고 | 국내 수급만 있는 테마 |

**데이터 소스**
- **Naver 테마 수익률**: `theme_history.json` — 오늘 수익률(primary) + 7거래일 지속성(secondary)
- **시장 맥락**: `output/summary/YYYY-MM/YYYY-MM-DD_data.json` — KOSPI 등락·주요 종목
- **Tavily 검색**: 오늘 수익률 상위 테마별 글로벌 뉴스 검색

## 보고서 구성 (테마 카드 1~2개)

- 오늘의 움직임 (Today's Move): 실제 수치·종목명 포함 한 문단
- 배경: 왜 오늘 이 테마가 움직였나
- 글로벌 연결고리: 글로벌 이벤트 → 한국 시장 파급 경로
- 상담사 토킹포인트: 고객에게 바로 쓸 수 있는 문장 3~4개
- 고객 Q&A: 실제 고객 질문 + 상담사 답변 2~3쌍
- 리스크, 관련 펀드

## 주요 플래그

- `--date YYYY-MM-DD`: 대상 날짜 (기본: 오늘)
- `--force`: 이미 보고서가 존재할 때 덮어쓰기 허용
- `--dry-run`: 파일 저장 없이 구조 확인만

## 주의사항

- `generate_securities_digest.py` import 시 `AWS_BEARER_TOKEN_BEDROCK=""` 환경변수 부작용 발생. import 후 즉시 해당 변수를 정리해 Anthropic SDK 인증 오류 방지.
- 증권 다이제스트는 선정 신호에서 제외 — 테마 카드 내 분석 풍부화에만 활용.
- `_update_sc_index()` 연동: `generate_research.py` 완료 후 자동 호출. `output/research/daily/` 최신 HTML을 경로 수정(depth 보정)해 `output/research/index.html`에 직접 덮어씀. 카드 목록이나 증권 다이제스트는 포함하지 않음.
- `collect_weekly.py` Step 6에서도 호출되어 주간 수집 완료 후 index를 최신 상태로 갱신.

> 이전 섹터·국가 11일 순환 사이클 (`generate_sector_country.py`)은 2026-05-26 폐기. 파일은 참조용 보존.
