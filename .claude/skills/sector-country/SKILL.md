---
name: sector-country
description: "섹터·국가 초보자 보고서 작성 스킬. Tavily 뉴스 검색 전략, 초보자 언어 변환 규칙, 품질 기준을 담는다."
type: skill
---

# Sector-Country Report Skill

섹터·국가 포지셔닝 보고서는 **"지금 어느 섹터·국가를 담을 것인가"** 를 초보자에게 설명하는 구조적 포지셔닝 문서다.

시황 보고서(market-summary)와 달리 세션 순서나 당일 인과 서사가 중심이 아니다. 1M/3M/6M 모멘텀 기반 신호에 **최근 1~2주 트렌드 맥락**을 붙여 설명한다.

---

## 0. 사이클 구조

매일 아침 **섹터 2개(US + KR) + 국가 1개 = 3개 주제**를 심층 분석한다.  
섹터 사이클(11일)과 국가 사이클(10일)은 **독립적으로** 순환한다.

### 섹터 11일 사이클 (기준일: 2026-01-05)

| 섹터 Day | 테마 | US 섹터 (SPDR) | KR 섹터 (TIGER 200) |
|---------|------|--------------|-------------------|
| 1 | 기술·IT | XLK (Technology) | TIGER 200 IT (364980.KS) |
| 2 | 통신·커뮤니케이션 | XLC (Communication) | TIGER 200 커뮤니케이션서비스 (364990.KS) |
| 3 | 금융 | XLF (Financials) | TIGER 200 금융 (435420.KS) |
| 4 | 에너지·화학 | XLE (Energy) | TIGER 200 에너지화학 (472170.KS) |
| 5 | 헬스케어 | XLV (Health Care) | TIGER 200 헬스케어 (227570.KS) |
| 6 | 산업재 | XLI (Industrials) | TIGER 200 산업재 (227560.KS) |
| 7 | 소재·중공업 | XLB (Materials) | TIGER 200 중공업 (157490.KS) |
| 8 | 경기소비재 | XLY (Consumer Discr.) | TIGER 200 경기소비재 (227540.KS) |
| 9 | 생활소비재 | XLP (Consumer Staples) | TIGER 200 생활소비재 (227550.KS) |
| 10 | 유틸리티·철강소재 | XLU (Utilities) | TIGER 200 철강소재 (494840.KS) |
| 11 | 부동산·건설 | XLRE (Real Estate) | TIGER 200 건설 (139270.KS) |

### 국가 11일 사이클 (섹터와 독립, 기준일: 2026-01-05)

| 국가 Day | 국가 |
|---------|------|
| 1 | 🇰🇷 한국 |
| 2 | 🇺🇸 미국 |
| 3 | 🇨🇳 중국 |
| 4 | 🇯🇵 일본 |
| 5 | 🇪🇺 유럽 |
| 6 | 🇬🇧 영국 |
| 7 | 🇩🇪 독일 |
| 8 | 🇫🇷 프랑스 |
| 9 | 🇮🇳 인도 |
| 10 | 🇹🇼 대만 |
| 11 | 🌍 신흥국(EM) |

**오늘의 Day는 `generate_sector_country.py`의 `get_focus(date)` 가 자동 계산한다.**  
반환 형식: `{ sector_day, country_day, theme, country_name, subjects: [us_sector, kr_sector, country] }`

---

## 1. Tavily 검색 전략

### 검색 범위

- 당일에 국한하지 않고 **최근 1~2주** 뉴스를 참조해 섹터·국가 포지셔닝의 배경을 설명한다
- 단, {date} 이후 미래 뉴스는 사용하지 않는다

### KR 섹터 검색 원칙: TIGER ETF = 업종 proxy

**TIGER ETF는 그 업종 전체의 proxy다.** ETF 자체를 분석하는 것이 아니라, ETF가 대표하는 **업종·산업의 동향**을 검색한다.

- 검색 키워드에 TIGER ETF 이름/티커를 포함시켜도 되지만, 핵심은 **업종 키워드**다
- ETF 수치(모멘텀 신호)는 `compute_sector_view()`에서 이미 계산됨 → 검색은 **"왜 이 업종인가"** 맥락 파악에 집중
- 예: TIGER 2차전지테마(137610.KS) 검색 시 → LG에너지솔루션·삼성SDI 실적, EV/ESS 수요, 소재 가격 등 업종 내 기업·정책·수요 뉴스가 핵심

### 검색 키워드 예시

| 대상 | 검색 핵심 | 키워드 예시 |
|------|---------|-----------|
| US 섹터 | ETF 성과 + 업종 드라이버 | `"XLK technology sector April 2026 ETF performance trend"` |
| KR IT | 반도체·IT 업종 (삼성전자·SK하이닉스) | `"Korea IT semiconductor Samsung SK Hynix 2026"` |
| KR 커뮤니케이션 | 통신 업종 (SKT·KT·LGU+) | `"Korea telecom SKT KT LG Uplus 2026"` |
| KR 금융 | 은행·금융 업종 (신한·KB·하나) | `"Korea financial Shinhan KB Hana bank 2026"` |
| KR 에너지화학 | 에너지·화학 업종 (LG화학·롯데케미칼) | `"Korea energy chemicals LG Chem 2026"` |
| KR 헬스케어 | 바이오·의약 업종 (셀트리온·삼성바이오) | `"Korea healthcare biotech Celltrion Samsung Biologics 2026"` |
| KR 산업재 | 조선·방산 업종 (HD현대·한화오션) | `"Korea industrials shipbuilding defense HD Hyundai 2026"` |
| KR 중공업 | 중공업·방산 (한화에어로·현대로템) | `"Korea heavy industry defense Hanwha Aerospace 2026"` |
| KR 경기소비재 | 자동차 업종 (현대차·기아) | `"Korea consumer discretionary Hyundai Kia auto 2026"` |
| KR 생활소비재 | 식음료·유통 업종 (CJ·오리온·농심) | `"Korea consumer staples food CJ Orion Nongshim 2026"` |
| KR 철강소재 | 철강·소재 업종 (POSCO·현대제철) | `"Korea steel POSCO Hyundai Steel materials 2026"` |
| KR 건설 | 건설·부동산 업종 (현대건설·대우건설) | `"Korea construction Hyundai Engineering Daewoo E&C 2026"` |
| 국가 | 주가지수 + 경제지표 | `"Korea KOSPI April 2026 market outlook"` |
| 대표주 | 개별 종목 최신 뉴스 | `"NVIDIA earnings April 2026"` |

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

## 4. 보고서 작성 방향

섹터·국가 보고서는 **항상 오늘의 3개 주제(US 섹터 + KR 섹터 + 국가)를 중심으로** 작성한다.

- **오늘의 3개 주제가 보고서의 전부다.**
- **"왜 지금 이 섹터·국가인가"** — 최근 1~2주 트렌드를 시간순으로 추적해 모멘텀 배경 설명
- 당일 시황 세션 귀속(아시아/유럽/미국) 서사 불필요. 구조적 포지셔닝 이유 중심
- **섹터와 국가는 독립적으로 서술한다.** US 섹터·KR 섹터·국가 각각을 별개의 심층 분석 단락으로 작성하며, 섹터↔국가를 억지로 연결짓는 "연결 고리" 단락은 쓰지 않는다.
- 각 주제별 핵심 포인트:
  - **US 섹터**: 글로벌 업종 트렌드 + 대표주(SECTOR_REP_STOCKS) 동향
  - **KR 섹터**: 국내 업종 기업 뉴스 + 대표주(SECTOR_REP_STOCKS) 동향. KR·US 같은 업종이면 간단히 비교 가능하나, 섹터와 국가를 교차 연결하지 않는다
  - **국가**: 해당 국가의 주가지수·경제지표·정책 흐름 중심. 섹터 내용과 교차 서술하지 않는다
- **대표주 검색 필수**: `SECTOR_REP_STOCKS`에 정의된 대표 기업들의 최신 실적·뉴스를 반드시 검색한다

---

## 4. 품질 기준

1. **날짜 이후 데이터 금지**: {date} 이후 결과를 신호 근거로 사용하지 않는다
2. **고점 표현 전 CSV 검증**: "YTD 신고점", "52주 고점" 등은 `history/market_data.csv` 직접 확인 후 사용
3. **날짜·요일 정확성**: 달력 기준으로 일치하는지 확인. KR 섹터 ETF는 KOSPI 휴장일에 데이터 없음 → 명시
4. **수치 출처**: 수익률·수치는 `compute_sector_view()` / `compute_country_view()` 기준. Tavily 수치와 충돌 시 CSV 우선
5. **내부 코드 노출 금지**: `SC_US_TECH` 같은 코드 사용 금지. ETF명(XLK) 또는 섹터명(Technology) 사용
6. **Tavily 기반**: 뉴스 맥락은 반드시 Tavily 검색 결과 기반. 미검색 추론 금지