# Asia Weekly Brief

일요일 오후 발행. 아시아 종목 유니버스 **180개** (중국·일본·인도·대만·홍콩·베트남·호주·인니) 주간 시황.  
`/asia-weekly YYYY-MM-DD` 한 줄로 발행.

`history/아시아종목.xlsx`가 운용 유니버스의 단일 정본.

## 산출물

`output/summary/weekly/YYYY-WNN_asia.{html, _data.json}`

| 파일 | 구성 |
|------|------|
| `{week}_asia.html` | 메인 6탭 보고서 (~720줄) |
| `{week}_asia_data.json` | 추출 데이터 (Claude 입력용) |

## 6탭 구성

1. **Asia Story** — Hero 3단락 + 인과체인 5노드 + 인사이트 6카드
2. **Country Drilldown** — 중·일·대만·인도·홍콩·한국 6섹션
3. **Themes** — 횡단 주제 4~5개 (반도체 디커플링·달러 강세·AI 인프라·정책 리스크·지정학)
4. **Data** — 지수 8 + 환율 5 + 종목 TOP/BOTTOM 20 + 국가별 종합
5. **Outlook** — Bull/Base/Bear 시나리오 + 리스크 TOP 5 + W+1 캘린더
6. **Sources** — 데이터 출처·증권사 다이제스트 4건·외부 자료·산출 방법론

## 워크플로우 (스킬: `asia-weekly`)

1. 캘린더 검증 (`calendar_check.py --week W##`)
2. 스켈레톤 + 데이터 자동 생성 (`generate_asia_weekly.py {date}`) — Data 탭 + KPI 자동 채움
3. 미래에셋증권 다이제스트 4건 (W##-3 ~ W##) 읽기
4. 5탭 본문 작성 (Story·Country·Themes·Outlook·Sources)
5. 검증 (`post_edit_write_structure_guard.py` + `verify_report_numbers.py`)

## 유니버스 매칭

- xlsx 종목명 ↔ `market_data.csv` TICKER 컬럼 정확 매칭
- 매칭 종목만 WTD% 계산 + 국가별 단순·가중 평균
- 미매칭 종목은 Sources 탭에 한계 명시
- 2026-05-18 기준 매칭률: 133/180 (74%) — 대만·호주·인니·베트남 100%, 인도 79%, 중국·일본 73%, 홍콩 11%
- 미매칭 47종목: xlsx에 티커 없음 45 + yfinance 미지원 2 (Tata Motors `TATAMOTORS.NS`, Orient Overseas `OOIL`)

## 자동화

`MarketSummary-AsiaWeekly` 태스크가 매주 토요일 20:00 KST 호출 (collect_weekly 30분 마진).  
데이터 준비만 자동, Story 본문은 Claude 수동.
