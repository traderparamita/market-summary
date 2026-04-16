---
name: sector-country
description: "섹터·국가 초보자 보고서 작성 스킬. Tavily 뉴스 검색 전략, 초보자 언어 변환 규칙, 품질 기준을 담는다."
type: skill
---

# Sector-Country Report Skill

섹터·국가 포지셔닝 보고서는 **"지금 어느 섹터·국가를 담을 것인가"** 를 초보자에게 설명하는 구조적 포지셔닝 문서다.

시황 보고서(market-summary)와 달리 세션 순서나 당일 인과 서사가 중심이 아니다. 1M/3M/6M 모멘텀 기반 신호에 **최근 1~2주 트렌드 맥락**을 붙여 설명한다.

---

## 1. Tavily 검색 전략

### 검색 범위

- 당일에 국한하지 않고 **최근 1~2주** 뉴스를 참조해 섹터·국가 포지셔닝의 배경을 설명한다
- 단, {date} 이후 미래 뉴스는 사용하지 않는다

### 검색 키워드 예시

| 대상 | 키워드 예시 |
|------|-----------|
| US 섹터 OW | `"XLK technology sector April 2026 ETF performance trend"` |
| US 섹터 전체 | `"GICS sector rotation April 2026 winners losers"` |
| KR 반도체 | `"TIGER 반도체 277630 semiconductor Korea HBM DRAM 2026"` |
| KR 2차전지 | `"TIGER 2차전지 137610 battery EV Korea CATL 2026"` |
| KR 헬스케어 | `"TIGER 헬스케어 166400 healthcare pharma Korea 2026"` |
| KR 금융·은행 | `"TIGER 은행 금융 Korea interest rate financial 2026"` |
| KR 철강소재 | `"TIGER 철강소재 494840 steel POSCO Korea 2026"` |
| KR 에너지화학 | `"TIGER 에너지화학 472170 energy chemicals LG Chem Korea 2026"` |
| KR 의료기기 | `"TIGER 의료기기 400970 medical device Korea 2026"` |
| KR 건설 | `"TIGER 200건설 139270 construction Korea real estate 2026"` |
| KR 산업재 | `"TIGER 200산업재 227560 industrials Hyundai auto Korea 2026"` |
| 국가 | `"Korea KOSPI April 2026 market outlook"` |
| 주간 전체 | `"sector rotation week April 2026 MSCI performance"` |
| 월간 전체 | `"GICS sector monthly performance April 2026 ETF"` |

### GICS 표준 키워드 (US)

검색 시 반드시 GICS 공식 섹터명 사용:
`Information Technology` / `Financials` / `Energy` / `Health Care` / `Industrials` / `Consumer Discretionary` / `Consumer Staples` / `Utilities` / `Materials` / `Real Estate` / `Communication Services`

---

## 2. 초보자 언어 변환 규칙

### 투자 의견

| 전문 용어 | 초보자 표현 |
|----------|-----------|
| OW (Overweight) | "지금 담으면 좋은 섹터/국가" |
| N (Neutral) | "지켜보는 섹터/국가" |
| UW (Underweight) | "줄이거나 피하는 섹터/국가" |

### 지표

| 전문 용어 | 초보자 표현 |
|----------|-----------|
| 3M +8% | "최근 3개월 동안 8% 올랐어요" |
| MA200 이상 | "200일 평균보다 위 = 장기 상승 추세" |
| MA200 이하 | "200일 평균보다 아래 = 장기 하락 구간" |
| YTD | "올해 들어" |
| 52W High | "52주 신고점 (1년 중 가장 높은 가격)" |

### 매크로 국면

| 국면 | 초보자 설명 |
|------|-----------|
| Goldilocks | "성장도 좋고 물가도 안정된 이상적 경제 환경 → 기술주·성장주 유리" |
| Reflation | "경제가 살아나면서 물가도 오르는 구간 → 금융·에너지·소재 유리" |
| Stagflation | "경기는 나쁜데 물가만 오르는 가장 어려운 환경 → 방어주 위주" |
| Deflation | "경기와 물가 모두 위축 → 채권·헬스케어·유틸리티 유리" |

### 경기 사이클

| 사이클 | 초보자 설명 |
|-------|-----------|
| Early (회복 초기) | "경기가 바닥을 찍고 올라오는 단계 → 금융·소비재·산업재 유리" |
| Mid (확장 중반) | "경기가 안정적으로 성장하는 단계 → 기술주·반도체 유리" |
| Late (확장 후기) | "경기 정점 부근, 물가 상승 → 에너지·소재 유리" |
| Recession (침체) | "경기가 꺼지는 단계 → 헬스케어·유틸리티·채권 선호" |

---

## 3. 시간순 서술 원칙

섹터·국가 보고서는 **세션별 귀속(아시아/유럽/미국)은 불필요**하지만, 트렌드 맥락을 설명할 때는 반드시 **과거 → 현재 순서**로 서술한다.

- 허용: "지난주 관세 우려로 기술주가 약세를 보인 후, 이번 주 반도체 수출 호조 확인으로 반등했다"
- 금지: "이번 주 반도체 반등은 지난주 약세가 과매도였음을 보여준다" (사후적 프레이밍)
- 금지: "이 하락은 시작에 불과했다", "~의 전초전이었다" (미래 암시)

**보고서별 시간 흐름**:
- **daily**: 최근 1~2주 트렌드 흐름 → 현재 신호 → 포지셔닝 근거
- **weekly**: 주초 → 주중 → 주말 흐름 → 다음 주 주목 포인트
- **monthly**: 월초 → 월중 → 월말 흐름 → 다음 달 전망

---

## 4. 보고서별 작성 방향

### 일간 (daily)

- OW/UW 섹터·국가 각 1~2문장 + 종합 3~5문장
- **"왜 지금 이 섹터인가"** — 최근 1~2주 트렌드를 시간순으로 추적해 모멘텀 배경 설명
- 당일 시황 세션 서사 불필요. 구조적 이유 중심

### 주간 (weekly)

- 주초 → 주말 흐름을 시간순으로 서술 (이번 주 섹터 로테이션 흐름)
- 1위·꼴찌 섹터/국가 비교 스토리
- 다음 주 주목 포인트 (1~2개)

### 월간 (monthly)

- 월초 → 월말 흐름을 시간순으로 서술 (GICS 로테이션 흐름)
- 매크로 국면 변화 여부 (있다면)
- 한국 섹터의 미국 섹터 대비 특징
- 다음 달 주목 섹터·국가 (2~3개)

---

## 4. 품질 기준

1. **날짜 이후 데이터 금지**: {date} 이후 결과를 신호 근거로 사용하지 않는다
2. **고점 표현 전 CSV 검증**: "YTD 신고점", "52주 고점" 등은 `history/market_data.csv` 직접 확인 후 사용
3. **날짜·요일 정확성**: 달력 기준으로 일치하는지 확인. KR 섹터 ETF는 KOSPI 휴장일에 데이터 없음 → 명시
4. **수치 출처**: 수익률·수치는 `compute_sector_view()` / `compute_country_view()` 기준. Tavily 수치와 충돌 시 CSV 우선
5. **내부 코드 노출 금지**: `SC_US_TECH` 같은 코드 사용 금지. ETF명(XLK) 또는 섹터명(Technology) 사용
6. **Tavily 기반**: 뉴스 맥락은 반드시 Tavily 검색 결과 기반. 미검색 추론 금지