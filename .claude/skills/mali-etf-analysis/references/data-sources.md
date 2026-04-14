# Data Sources & Fallback Chains — 데이터 소스 및 폴백 체인

---

## 데이터 소스 우선순위 원칙

1. **Morningstar MCP 우선**: 연결 시 가장 정확하고 구조화된 데이터 제공
2. **WebSearch 보완**: Morningstar에 없는 센티먼트, 뉴스, 커뮤니티 데이터
3. **yfinance 최후 수단**: 가격 시계열과 기본 재무 데이터 (무료, 신뢰도 낮음)
4. **한국 ETF 특수 경로**: KRX/운용사 → Naver Finance → Morningstar → yfinance

---

## Agent별 데이터 소스 매핑

### Agent 1: ETF Profile

| 데이터 항목 | 소스 1 (우선) | 소스 2 (폴백) | 소스 3 (최후) |
|---|---|---|---|
| 정식 명칭, 티커, ISIN | Morningstar id-lookup | WebSearch (etf.com) | yfinance .info |
| AUM | Morningstar data-tool (OF009) | WebSearch (etfdb.com) | yfinance .info["totalAssets"] |
| 설정일 | Morningstar data-tool | etf.com / 운용사 사이트 | yfinance |
| 보수율(TER) | Morningstar data-tool | etf.com | yfinance .info["expenseRatio"] |
| 추적 지수 | Morningstar data-tool | 운용사 factsheet | WebSearch |
| 일별 종가 시계열 | yfinance (가장 편리) | Morningstar HS793 | — |
| NAV vs 시장가 괴리 | Morningstar | etf.com premium/discount | — |
| 거래량/거래대금 | yfinance | — | — |

**한국 ETF 추가 소스:**
- KRX ETF 포털: `etf.krx.co.kr`
- 운용사 사이트: 삼성자산운용, 미래에셋자산운용, KB자산운용 등
- Naver Finance: `finance.naver.com/item/main.naver?code={6자리코드}`

### Agent 2: Holdings

| 데이터 항목 | 소스 1 | 소스 2 | 소스 3 | 소스 4 |
|---|---|---|---|---|
| 보유종목 전체 | Morningstar fund-holdings-tool | SEC EDGAR N-PORT | 운용사 factsheet | yfinance (top 10만) |
| 섹터 분포 | Morningstar | 운용사 factsheet | 수동 GICS 매핑 | — |
| 지역 분포 | Morningstar | 운용사 factsheet | — | — |

**한국 ETF Holdings 폴백 체인:**
1. Morningstar fund-holdings-tool → 한국 ETF도 일부 커버
2. 운용사 PDF factsheet (WebSearch → WebFetch로 PDF 다운로드)
   - 검색: `"{ETF명}" 월간리포트 OR factsheet site:{운용사도메인}`
3. Naver Finance 종목 구성: `finance.naver.com/item/coinfo.naver?code={코드}`
4. yfinance: `yf.Ticker("{코드}.KS").institutional_holders` (제한적)

**SEC EDGAR N-PORT (미국 ETF 보완):**
- 검색: `site:sec.gov N-PORT "{fund name}" OR "{CIK}"`
- 분기별 전체 보유종목 공시 — Morningstar보다 최신일 수 있음

### Agent 3: Sector/Theme

| 데이터 항목 | 소스 |
|---|---|
| 테마 ETF 자금 흐름 | WebSearch: etf.com, etftrends.com, etfdb.com |
| 테마 성숙도 판단 | WebSearch: 업계 리포트, 뉴스 트렌드 |
| 밸류체인 분석 | Holdings 데이터 + WebSearch |
| 규제/정책 리스크 | WebSearch: 정부기관, 규제당국 사이트 |

### Agent 4: Fundamental

| 데이터 항목 | 소스 1 | 소스 2 | 소스 3 |
|---|---|---|---|
| PER, PBR, PSR | Morningstar data-tool | yfinance .info | WebSearch |
| EPS 성장률 | Morningstar | yfinance | WebSearch (consensus) |
| ROE, ROA, 마진 | Morningstar | yfinance | — |
| 어닝 서프라이즈 | WebSearch (earnings whispers, macrotrends) | — | — |
| 컨센서스 수정 | WebSearch (marketbeat, tipranks) | — | — |

### Agent 5: Sentiment/Flow ★

→ 아래 "Sentiment/Flow 웹서치 매트릭스" 섹션 참조

### Agent 6: Performance

| 데이터 항목 | 소스 |
|---|---|
| 수익률 (모든 기간) | yfinance 종가 시계열 → Python 계산 |
| 변동성, MDD, VaR | yfinance 종가 → Python 계산 |
| Sharpe, Sortino, Calmar | Python 계산 (무위험이자율: ^TNX) |
| 추적오차, IR, R² | yfinance (ETF + 벤치마크) → Python 계산 |

### Agent 7: Regime/Macro

| 데이터 항목 | 소스 |
|---|---|
| 시장 국면 수익률 | yfinance 종가 → 기간별 슬라이싱 |
| 매크로 변수 시계열 | yfinance: ^TNX, DX-Y.NYB, CL=F, ^VIX |
| 현재 매크로 환경 | WebSearch: Fed 정책, 경제지표 |
| 금리/환율 전망 | WebSearch: CME FedWatch, 이코노미스트 전망 |

### Agent 8: Peer Comparison

| 데이터 항목 | 소스 1 | 소스 2 |
|---|---|---|
| 피어 ETF 리스트 | Morningstar screener-tool | WebSearch: etfdb.com 카테고리 |
| 피어 비교 데이터 | 위 Agent 1~7과 동일 소스를 피어에도 적용 | — |

---

## Sentiment/Flow 웹서치 매트릭스 ★핵심

이 매트릭스는 Agent 5 (Sentiment/Flow)가 반드시 수행해야 하는 웹서치 목록이다.

### ★ 핵심 원칙: Top 10 보유종목 기업 기준 검색

ETF 티커/명칭이 아닌, **Top 10 보유종목의 개별 기업 티커와 이름**으로 검색한다.
예: ETF가 GE Vernova(8.1%), Vertiv(7.6%), Bloom Energy(7.1%)를 보유하면,
"GEV", "VRT", "BE" 각각에 대해 모든 소스를 검색한다.

**검색 루프:**
```
for each stock in top_10_holdings:
    search Reddit for "{stock.ticker}" OR "{stock.name}"
    search Seeking Alpha for "{stock.ticker}"
    search X/Twitter for "{stock.ticker}"
    search Bloomberg/Reuters for "{stock.name}"
    search Morningstar articles for stock
    calculate stock_sentiment_score (1-10)

ETF_sentiment = weighted_average(stock_sentiments, weights=stock_weights)
```

### 1. Reddit (리테일 센티먼트) — 종목별 검색

**검색 쿼리 패턴 (Top 10 종목 각각):**

| 서브레딧 | 검색 쿼리 패턴 | 특성 |
|---|---|---|
| r/investing | `site:reddit.com/r/investing "{종목티커}" OR "{종목명}"` | 중장기 투자 관점 |
| r/stocks | `site:reddit.com/r/stocks "{종목티커}" earnings outlook` | 개별 종목 분석 |
| r/wallstreetbets | `site:reddit.com/r/wallstreetbets "{종목티커}"` | 투기적 센티먼트 |

**테마별 서브레딧 (종목 섹터에 따라 선택):**

| 종목 섹터 | 서브레딧 | 검색 키워드 예시 |
|---|---|---|
| 유틸리티/전력 | r/energy, r/utilities | "{종목명}" OR "power infrastructure" |
| 원자력/우라늄 | r/nuclear, r/uraniumsqueeze | "{종목명}" OR "nuclear energy" |
| 반도체/네트워크 | r/semiconductor, r/networking | "{종목명}" OR "optical networking" |
| 건설/인프라 | r/infrastructure | "{종목명}" OR "data center construction" |
| 스토리지 | r/datahoarder, r/hardware | "{종목명}" OR "enterprise storage" |

**Reddit 분석 포인트 (종목별):**
- 최근 3개월 포스트 빈도 (관심도)
- 긍정/부정/중립 비율 (센티먼트)
- 반복되는 핵심 논점
- 갑작스러운 멘션 급증 (바이럴 시그널)
- 어닝 전후 댓글 톤 변화

### 2. Seeking Alpha (전문 개인투자자) — 종목별 검색

| 검색 유형 | 쿼리 패턴 (Top 10 종목 각각) |
|---|---|
| 종목 분석 | `site:seekingalpha.com "{종목티커}" analysis outlook` |
| 어닝 전망 | `site:seekingalpha.com "{종목티커}" earnings 2026` |
| Quant Rating | `site:seekingalpha.com "{종목티커}" quant rating` |
| 밸류에이션 | `site:seekingalpha.com "{종목티커}" valuation fair value` |

**분석 포인트 (종목별):**
- 투자 의견 분포 (Strong Buy/Buy/Hold/Sell/Strong Sell)
- 핵심 Bull/Bear 논거 요약
- Quant Rating + Wall Street 컨센서스 vs SA 저자 의견 괴리

### 3. X/Twitter (핀트위터) — 종목별 검색

| 검색 유형 | 쿼리 패턴 (Top 10 종목 각각) |
|---|---|
| 종목 영어 | `site:x.com "${종목티커}" OR "${종목명}" lang:en` |
| 어닝 반응 | `site:x.com "${종목티커}" earnings lang:en` |
| 한국어 (ETF 보조) | `site:x.com "${한국ETF명}" lang:ko` |

**분석 포인트 (종목별):**
- 종목별 KOL 의견 트렌드
- 어닝 발표 전후 멘션 톤 변화
- 기관/애널리스트 계정의 목표가 코멘트

### 4. Morningstar (기관급 리서치)

| 도구 | 용도 |
|---|---|
| morningstar-articles-tool | 해당 ETF/테마 관련 기사 검색 |
| morningstar-analyst-research-tool | 애널리스트 등급, 보고서 |
| morningstar-data-tool | 수급 데이터 (AUM 변화 등) |

### 5. Bloomberg/Reuters (기관 뷰) — 종목별 검색

| 검색 유형 | 쿼리 패턴 (Top 10 종목 각각) |
|---|---|
| 종목 전망 | `"{종목명}" outlook 2026 site:bloomberg.com OR site:reuters.com` |
| 어닝/가이던스 | `"{종목명}" earnings guidance site:bloomberg.com` |
| 테마 (보조) | `"{테마}" trend site:bloomberg.com OR site:reuters.com` |

### 6. 전문 ETF 미디어

| 사이트 | 쿼리 패턴 |
|---|---|
| ETF.com | `"{ticker}" site:etf.com` |
| ETF Trends | `"{ticker}" OR "{theme}" site:etftrends.com` |
| ETF Database | `"{ticker}" site:etfdb.com` |

### 7. 한국 소스 (한국 ETF 전용)

| 소스 | 쿼리 패턴 |
|---|---|
| Naver 종목토론방 | `site:finance.naver.com "{종목명}" OR "{코드}"` |
| 한국경제 | `"{ETF명}" 전망 site:hankyung.com` |
| 매일경제 | `"{ETF명}" 분석 site:mk.co.kr` |
| 조선비즈 | `"{ETF명}" site:biz.chosun.com` |
| thebell | `"{ETF명}" OR "{운용사}" site:thebell.co.kr` |

---

## 센티먼트 스코어 산출 기준

### Step 1: 종목별 센티먼트 (Top 10 각각)

각 종목에 대해 6개 소스의 센티먼트를 1~10 척도로 평가한 뒤 소스별 가중평균:

| 소스 | 가중치 | 이유 |
|---|---|---|
| Seeking Alpha | 25% | 종목별 체계적 분석, 투자의견 명시 |
| Bloomberg/Reuters | 20% | 기관 컨센서스, 목표가 |
| Morningstar | 20% | Fair Value, Moat 등급 |
| Reddit | 15% | 리테일 심리의 선행지표 |
| X/Twitter | 10% | 속보성, 어닝 반응 |
| 어닝 센티먼트 | 10% | 서프라이즈/미스 + 리비전 방향 |

→ 각 종목의 **종목_센티먼트_스코어** (1~10) 산출

### Step 2: ETF 전체 센티먼트 = 비중 가중 집계

```
ETF_sentiment = Σ (종목_센티먼트 × 종목_비중) / Σ (Top10_비중)
```

예: GE Vernova(8.09%, 점수 8.2) + Vertiv(7.64%, 점수 7.5) + ... → 가중평균 7.3

### Step 3: ETF 수급 보정

ETF 자체의 자금 유입/유출, 기관 매매 동향으로 ±0.5점 보정:
- 순유입 가속 → +0.5
- 순유출 가속 → -0.5
- 중립 → 보정 없음

### 스코어 해석:
- 8~10: 극도 긍정 (과열 경고 필요)
- 6~7: 긍정적
- 4~5: 중립/혼재
- 2~3: 부정적
- 1: 극도 부정 (역발상 매수 검토)

---

## 수급 데이터 수집

### ETF 설정/환매 (자금 유출입)

| 데이터 | 소스 |
|---|---|
| 미국 ETF 자금흐름 | WebSearch: etf.com fund flows, etfdb.com flows |
| 글로벌 ETF 흐름 | WebSearch: Morningstar global flows report |
| 한국 ETF 순자산 변동 | KRX ETF 포털, Naver Finance |

### 기관 매매 동향

| 데이터 | 소스 |
|---|---|
| 13F filings (미국) | WebSearch: SEC EDGAR 13F, whalewisdom.com |
| 기관/외인 매매 (한국) | KRX 투자자별 매매동향, Naver Finance |

---

## yfinance 사용 가이드

```python
import yfinance as yf

# 기본 정보
etf = yf.Ticker("QQQ")
info = etf.info  # AUM, 보수율, 설정일 등

# 가격 시계열
hist = etf.history(period="5y")  # 5년
hist = etf.history(start="2020-01-01", end="2025-04-01")  # 기간 지정

# 한국 ETF (A 접두사 제거, .KS 추가)
kr_etf = yf.Ticker("005930.KS")  # 삼성전자
kr_etf = yf.Ticker("069500.KS")  # KODEX 200

# 매크로 변수
tnx = yf.Ticker("^TNX")    # 미국 10Y 금리
dxy = yf.Ticker("DX-Y.NYB") # 달러 인덱스
wti = yf.Ticker("CL=F")     # WTI 유가
vix = yf.Ticker("^VIX")     # VIX

# 벤치마크
spy = yf.Ticker("SPY")      # S&P 500
qqq = yf.Ticker("QQQ")      # Nasdaq 100
efa = yf.Ticker("EFA")      # MSCI EAFE
acwi = yf.Ticker("ACWI")    # MSCI ACWI
```

**yfinance 제한 사항:**
- Holdings는 top 10만 제공 — 전체 리스트가 필요하면 Morningstar 또는 SEC 사용
- 한국 ETF의 info 필드 일부 누락될 수 있음
- API 호출 빈도 제한 있으므로 배치 처리 권장
- 장중 실시간 데이터는 15분 지연

---

## 한국 ETF 티커 변환 규칙

```python
import re

def normalize_korean_ticker(ticker):
    """한국 ETF 티커 정규화: A접두사 제거 + .KS/.KQ 추가"""
    # A 접두사 제거
    ticker = re.sub(r"^A(\d{6})$", r"\1", ticker)
    
    # 6자리 숫자면 한국 종목
    if re.match(r"^\d{6}$", ticker):
        # KOSDAQ: 코스닥 ETF는 .KQ (거의 없음, 대부분 .KS)
        return f"{ticker}.KS"
    
    return ticker
```
