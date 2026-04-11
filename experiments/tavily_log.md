# Tavily MCP Story 실험 로그

**브랜치**: `experiment/tavily-story`
**시작일**: 2026-04-11
**목표 기간**: 5 영업일 (최소 5건의 일간 Story 비교)
**종료 조건**: 아래 "Discard 기준" 중 하나라도 충족되면 브랜치 폐기

## 실험 목적

내장 `WebSearch`/`WebFetch` 대신 **Tavily MCP**를 Story 작성용 1차 검색 도구로 사용했을 때 다음이 개선되는지 검증한다.

1. 시간 범위 필터링 (Tavily `days`/`published_date` vs WebSearch 최신성 편향)
2. 세션 귀속 정확성 (경제지표·뉴스 발생 시각 맞는 세션에 배치)
3. 주간·월간 Story의 과거 날짜 조회 품질
4. 작성 소요 시간
5. 훅 `block` 빈도 (쿼리 재작성 횟수)

## 평가 축

| 축 | 측정 | 합격 기준 |
|---|---|---|
| 시간 정확성 | 사후 수동 감사 | 위반 0건 |
| 세션 귀속 | 경제지표 발표 KST 시각 대조 | main 대비 명백히 개선 |
| 수치 정확성 | `_data.json` vs Story 내 수치 | 100% |
| 서사 품질 | 사용자 주관 평가 (★1~5) | main 대비 ≥ 동률 |
| 작성 시간 | 한 편당 경과 분 | main 대비 ≤ 동률 |
| Tavily 쿼리 수 | 일간 기준 | ≤ 10콜/일 |
| 훅 충돌 | matcher 오동작 | 0건 |

## Discard 기준 (셋 중 하나만 충족돼도 폐기)

1. 5 영업일 내에 "명확한 개선"이 관찰되지 않음 (main과 동률 = 실패, 복잡도만 증가)
2. 훅 연동 또는 MCP 안정성 이슈가 Story 작업 flow를 반복적으로 방해
3. Tavily API 한도(1000/월)가 실험 기간 중 소진

## 비교 방식

- 같은 날짜의 Story를 main 워크트리(`.../market_summary`)와 실험 워크트리(`.../market_summary_tavily`)에서 **각각 작성**
- 같은 파일 경로(`output/YYYY-MM/YYYY-MM-DD_story.html`)를 유지해 `git diff main experiment/tavily-story -- output/YYYY-MM/YYYY-MM-DD_story.html`로 직접 비교
- 실험 브랜치는 배포하지 않는다. main만 GitHub Pages에 올라간다. `/market-deploy` 가드가 이를 강제한다.

## 일별 기록

| 날짜 | 작성(분) | Tavily 콜 | 훅 block | 세션 귀속 | 수치 | 서사★ | 비고 |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

## 결론 (실험 종료 후 기입)

- [ ] main에 merge
- [ ] discard, 브랜치 삭제
- [ ] 추가 실험 필요 (사유: )
