# Agent Profiles — 각 에이전트 역할·도구·프롬프트 가이드

---

## Agent 1: ETF Profile Agent

**역할**: ETF의 기본 신원 정보와 가격 시계열 수집
**도구**: Morningstar (id-lookup, data-tool), WebSearch, WebFetch, Bash (yfinance)
**한국 ETF**: WebSearch로 KRX ETF 포털 또는 운용사 사이트에서 수집

수집 항목:
- 정식 명칭, 티커, ISIN, 운용사
- AUM, 설정일, 보수율(TER)
- 추적 지수(벤치마크), 복제 방식(물리적/합성)
- 일별 종가 시계열 (Lookback 기간)
- NAV vs 시장가 괴리율 (프리미엄/디스카운트)
- 일평균 거래량, 거래대금

출력: `profile.json` (구조화)

---

## Agent 2: Holdings Agent

**역할**: ETF 보유 종목 전체 리스트, 섹터·지역 분포, 집중도 분석
**도구**: Morningstar (fund-holdings-tool), WebSearch, WebFetch, Bash

**데이터 소스 폴백 체인 (→ data-sources.md 참조):**
1. Morningstar fund-holdings-tool (해외 ETF)
2. SEC EDGAR N-PORT (미국 ETF 보완)
3. KRX/운용사 PDF (한국 ETF)
4. Naver Finance 크롤링 (한국 ETF 보완)
5. yfinance (최후 수단, top 10만 제공)

분석 항목:
- 전체 보유 종목 리스트 (종목명, 비중, 섹터, 국가)
- 상위 10/20/50 종목 비중 합계
- 섹터 분포 (GICS 기준)
- 지역 분포
- HHI (Herfindahl-Hirschman Index) — 집중도
- 회전율 (가용 시)

출력: `holdings.json` (구조화)

---

## Agent 3: Sector/Theme Agent

**역할**: ETF가 노출된 섹터·테마의 글로벌 트렌드와 성숙도 판단
**도구**: WebSearch, Morningstar (screener-tool), Bash

분석 항목:
1. **테마 식별**: holdings 데이터 기반으로 ETF의 핵심 테마 추출
   (예: "AI 인프라", "2차전지 밸류체인", "미국 헬스케어 혁신")
2. **글로벌 자금 흐름**: 해당 테마 ETF들의 자금 유입/유출 트렌드
   - WebSearch: `"{theme}" ETF flows 2025 site:etf.com OR site:etftrends.com`
3. **테마 성숙도 판단**:
   - 초기(Early): 아직 메인스트림 아님, 소수 ETF만 존재
   - 성장(Growth): 자금 유입 가속, 새 ETF 출시 활발
   - 과열(Overheated): 밸류에이션 극단, 레버리지 ETF 출시, 리테일 과열
   - 쇠퇴(Decline): 자금 유출, 테마 피로감
4. **밸류체인 내 포지셔닝**: ETF가 밸류체인의 어느 단계에 집중하는지
5. **규제·정책 리스크**: 해당 테마에 영향을 줄 정책 변화

출력: `sector_theme.json` + 의견서

---

## Agent 4: Fundamental Agent

**역할**: **Top 10 보유종목 기업별** 펀더멘털 분석 + 비중 가중 집계
**도구**: Morningstar (data-tool), WebSearch, Bash (yfinance)

### ★ 핵심 원칙: Top 10 종목 기업별 분석 후 비중 가중 집계

ETF의 집계 PER/PBR은 Morningstar에서 제공하지만, 실질적인 펀더멘털 판단은
**Top 10 종목 각각의 어닝 전망, 밸류에이션, 성장성**을 개별 분석한 뒤 집계해야 한다.

### 종목별 분석 (Top 10 각각):

1. **개별 밸류에이션**: PER, PBR, PSR, EV/EBITDA, FCF Yield
2. **성장 전망**: 매출성장률, EPS 성장률 (컨센서스 향후 2년)
   - WebSearch: `"{종목명}" revenue earnings outlook 2026 2027`
3. **수익성**: ROE, 영업이익률, 순이익률
4. **어닝 트렌드**:
   - 최근 분기 어닝 서프라이즈/미스
   - 컨센서스 EPS 수정 방향 (상향/하향)
   - WebSearch: `"{종목명}" earnings surprise revision consensus`
5. **밸류에이션 밴드**: 현재 PER의 5년 백분위 위치
6. **백로그/수주 잔고**: 인프라 기업 특성상 백로그가 핵심
   - WebSearch: `"{종목명}" backlog order book 2026`

### 비중 가중 집계:
```
ETF_weighted_PER = Σ (종목_PER × 종목_비중) / Σ (Top10_비중)
ETF_weighted_growth = Σ (종목_EPS_growth × 종목_비중) / Σ (Top10_비중)
```

### ETF 레벨 보조:
- Morningstar data-tool의 ETF 집계 밸류에이션 (PER, PBR, ROE)으로 교차 검증

출력: `fundamentals.json` + 의견서

---

## Agent 5: Sentiment/Flow Agent ★핵심

**역할**: **Top 10 보유종목 기업 기준** 센티먼트/수급 분석 + ETF 수급 보조
**도구**: WebSearch, WebFetch, Morningstar (articles-tool), Bash

이 에이전트는 이 스킬의 핵심 차별점이다.
ETF 자체가 아닌, **편입 기업들의 센티먼트와 수급**이 실제 가격을 결정한다.

→ `data-sources.md`의 "Sentiment/Flow 웹서치 매트릭스" 반드시 참조

### ★ 핵심 원칙: Top 10 종목 기업별 분석

Phase 1 Holdings에서 Top 10 종목을 추출한 뒤, **각 종목별**로 아래 분석을 수행:

**각 종목별 검색 (Top 10 × 6개 소스 = 60회+ 검색):**

1. **Reddit**: `site:reddit.com "{종목티커}" OR "{종목명}" investing`
   - r/investing, r/stocks, r/wallstreetbets + 테마별 서브레딧
   - 최근 3개월 포스트·댓글 트렌드, 긍정/부정/중립 비율

2. **Seeking Alpha**: `site:seekingalpha.com "{종목티커}" analysis outlook 2026`
   - 투자의견(Buy/Hold/Sell), Quant Rating, 핵심 논거

3. **X/Twitter**: `site:x.com "{종목티커}" OR "{종목명}" lang:en`
   - 핀트위터 KOL 의견, 멘션 급증 여부

4. **Morningstar**: morningstar-articles-tool로 각 종목 관련 기사
   - 애널리스트 등급, Fair Value 대비 현재가

5. **Bloomberg/Reuters**: `"{종목명}" outlook site:bloomberg.com OR site:reuters.com`
   - 기관 목표가, 컨센서스 방향

6. **어닝 센티먼트**: `"{종목명}" earnings surprise revision consensus`
   - 최근 어닝 서프라이즈/미스, 컨센서스 수정 방향

**종목별 센티먼트 스코어 산출:**
각 종목에 1~10점 부여 (1=극도 부정, 5=중립, 10=극도 긍정)

**ETF 전체 센티먼트 = 비중 가중 집계:**
```
ETF_sentiment = Σ (종목_sentiment × 종목_비중) / Σ (Top10_비중)
```

### ETF 레벨 수급 (보조 지표):
- ETF 설정/환매 추이, AUM 변화 (주간/월간)
- 기관·외인 매매 동향 (한국 ETF)
- 공매도/대차잔고 (해당 시)
- 한국 소스: Naver Finance, 한경/매경

### 출력 포맷:

```json
{
  "stock_sentiments": [
    {"name": "GE Vernova", "ticker": "GEV", "weight": 8.09, "score": 8.2,
     "reddit": 7.5, "seeking_alpha": 8.5, "twitter": 7.0, "bloomberg": 8.5,
     "earnings_sentiment": "positive", "key_finding": "..."},
    ...
  ],
  "weighted_etf_sentiment": 7.3,
  "etf_flow_sentiment": 6.5,
  "overall_score": 7.1
}
```

출력: `sentiment_flow.json` + 의견서

---

## Agent 6: Performance Agent

**역할**: 정량적 성과·리스크 분석
**도구**: Bash (yfinance + Python 계산), Morningstar (data-tool)

분석 항목:
1. **수익률**: 1M, 3M, 6M, YTD, 1Y, 3Y, 5Y (누적 + 연환산)
2. **리스크**: 연환산 변동성, 최대 낙폭(MDD), VaR (95%), CVaR
3. **리스크 조정 수익률**: Sharpe, Sortino, Calmar
4. **추적 지표**: 추적오차(Tracking Error), 정보비율(IR), R²
5. **롤링 분석**: 롤링 12M 수익률, 롤링 12M 변동성
6. **드로다운 분석**: 최대 드로다운 기간, 회복 소요 기간, 드로다운 빈도

출력: `performance.json` + 의견서

---

## Agent 7: Regime/Macro Agent

**역할**: **Top 10 보유종목 기업 기준** 매크로 민감도 분석 + 시장 국면별 성과 분해
**도구**: Bash (Python 계산), WebSearch, yfinance

### ★ 핵심 원칙: Top 10 종목 기업별 매크로 민감도 분석

ETF 자체의 히스토리가 짧거나 없을 수 있으므로, **Top 10 보유종목의 개별 주가**를
기준으로 매크로 변수와의 민감도를 분석한다.

### 종목별 매크로 분석 (Top 10 각각):

1. **금리 민감도**: 각 종목의 주가 vs 10Y 금리 변화 상관계수/베타
   - 유틸리티(GE Vernova, Vistra 등): 금리 역상관 예상
   - 건설(MasTec, Quanta): 경기 순환 민감
   - 반도체/네트워크(Ciena, Lumentum): 성장주 금리 민감도 높음

2. **달러 민감도**: 각 종목의 해외 매출 비중에 따른 DXY 민감도
   - 글로벌 매출 기업 vs 미국 내수 기업 구분

3. **에너지 가격 민감도**: 유가/전력가격 변동이 각 종목에 미치는 영향
   - 에너지 생산기업(Bloom Energy): 수혜
   - 에너지 소비기업(데이터센터 인프라): 비용 압박

4. **관세/무역정책 민감도**: 각 종목의 공급망 노출도
   - 해외 제조(Kioxia, Fujikura): 관세 직접 영향
   - 미국 내 건설(MasTec, Quanta): 자재비 간접 영향

### 비중 가중 ETF 매크로 민감도:
```
ETF_rate_sensitivity = Σ (종목_rate_beta × 종목_비중) / Σ (Top10_비중)
```

### ETF 레벨 국면 분석:

1. **시장 국면별 성과** (ETF 또는 Top 10 종목 합성 포트폴리오):
   - COVID Crash / Recovery / 2022 Bear / 2023 AI Rally / Rate Hike Cycle
   - 각 국면의 수익률, 변동성, MDD
2. **방어력 점수**: 하락장 MDD / 벤치마크 MDD
3. **현재 매크로 환경 판단**: 어떤 국면과 유사한지
4. **금리·환율 시나리오별 예상 영향**

### 출력 포맷:

```json
{
  "stock_macro_sensitivity": [
    {"name": "GE Vernova", "ticker": "GEV", "weight": 8.09,
     "rate_beta": -0.45, "dxy_beta": -0.20, "oil_beta": 0.15, "tariff_exposure": "low",
     "key_macro_risk": "금리 상승 시 유틸리티 멀티플 압축"},
    ...
  ],
  "weighted_etf_sensitivity": {
    "rate_beta": -0.32, "dxy_beta": -0.15, "oil_beta": 0.08
  },
  "current_regime": "Stalled Growth + Energy Shock",
  "regime_implication": "..."
}
```

출력: `regime_macro.json` + 의견서

---

## Agent 8: Peer Comparison Agent

**역할**: 동일 카테고리 ETF 비교 분석
**도구**: Morningstar (screener-tool), WebSearch, Bash

분석 항목:
1. **피어 선정**: 동일 카테고리/테마/추적지수의 ETF 5~10개 자동 선정
2. **비교 매트릭스**:
   - 보수율(TER)
   - AUM, 일평균 거래대금 (유동성)
   - 1Y/3Y/5Y 수익률
   - 변동성, MDD
   - 추적오차
   - 보유종목 수, 상위 10종목 집중도
3. **비용 효율성**: 보수 대비 성과 (수익률/TER)
4. **순위표**: 종합 점수 기반 순위

출력: `peer_comparison.json`
