# VIEW AGENT 강화 마스터 PLAN

> 작성일: 2026-04-13  
> 기반: 9개 뷰 에이전트 병렬 리서치 (백테스트 검증 + 데이터 확장 + 로직 정교화)  
> 목표: 각 뷰를 진단 도구에서 **예측력 있는 투자 의사결정 엔진**으로 격상

---

## 0. 전략 요약 (Executive Summary)

| 구분 | 현재 수준 | 목표 수준 | 핵심 개선 |
|------|-----------|-----------|-----------|
| 백테스트 | 없음 (시각화만) | 히트율 >55%, Sharpe +0.3↑ | Forward return 검증 + Walk-forward |
| 데이터 | CSV 2종 (OHLCV + Macro) | +4개 소스 (FRED확장/CFTC/센티먼트/팩터밸류) | FRED API 확장, COT 리포트 |
| 로직 | 규칙 기반 단순 레짐 | 확률적 다층 레짐 (HMM + Fuzzy) | 12-셀 매트릭스, 확률적 추정 |

**공통 원칙**:
1. 모든 신호는 **Forward Return 검증** 후 채택 (IC ≥ 0.05, Hit Rate ≥ 55%)
2. **Walk-Forward Validation** (훈련 3년 / 테스트 1년) 필수
3. **레짐 조건부** 파라미터 - 레짐별 가중치 분리
4. 확률 기반 포지셔닝 (hard binary → soft probability)

---

## 1. 공통 강화 인프라 (Cross-View)

### 1.1 백테스트 검증 프레임워크 (`portfolio/backtest_signals.py` 신규)

```python
# 모든 뷰 신호에 공통 적용
def validate_signal(signal_series, forward_returns, periods=[5, 21, 63]):
    """
    signal_series: 일별 시그널 값 (-1 ~ +1)
    forward_returns: 대상 자산 N일 선행 수익률
    returns: IC, Hit_Rate, t-stat
    """
    results = {}
    for n in periods:
        fwd = forward_returns.shift(-n)
        ic = signal_series.corr(fwd, method='spearman')
        hit = (np.sign(signal_series) == np.sign(fwd)).mean()
        results[f'{n}d'] = {'IC': ic, 'HitRate': hit}
    return results
```

**검증 기준**:
- IC(Information Coefficient) ≥ 0.05 (Spearman)
- Hit Rate ≥ 55%
- t-통계 ≥ 1.96 (95% 신뢰수준)

### 1.2 Walk-Forward 엔진 (`portfolio/walk_forward.py` 신규)

```
[2010-2012] Train → [2013] Test
[2010-2013] Train → [2014] Test
...
[2010-2023] Train → [2024] Test
```

- 각 구간에서 파라미터 최적화 + OOS 성과 기록
- 총 성과 = OOS 구간 합산 (과적합 방지)

### 1.3 레짐 분류기 (`portfolio/view/regime_classifier.py` 신규)

```python
# 3-state HMM (RiskON / Neutral / RiskOFF)
from hmmlearn import hmm

features = ['vix_norm', 'yield_curve', 'breadth_ma200', 'credit_spread']
model = hmm.GaussianHMM(n_components=3, covariance_type='full', n_iter=100)
# → P(regime | 현재 지표) 확률 벡터 반환
```

### 1.4 데이터 수집 확장 (`portfolio/macro_indicators.yaml`에 통합 완료)

> `collect_extended.py`는 삭제되었고 모든 지표는 `macro_indicators.yaml`에 흡수됨.
> `python -m portfolio.collectors.macro` 단일 명령으로 수집.

| 데이터 | 소스 | INDICATOR_CODE | 활용 뷰 |
|--------|------|----------------|---------|
| HY Credit Spread | FRED: BAMLH0A0HYM2 | US_HY_SPREAD | Regime, Bond, Allocation |
| TED Spread | FRED: TEDRATE | CREDIT_TED_SPREAD | Regime, Bond |
| MOVE Index | FRED: MOVE | BOND_MOVE_INDEX | Bond, Style |
| Real Yield (10Y) | FRED: DFII10 | BOND_REAL_YIELD_10Y | Bond, Allocation |
| Term Premium | FRED: ACMTP10 | BOND_TERM_PREMIUM | Bond, Regime |
| Consumer Sentiment | FRED: UMCSENT | MACRO_US_CONSUMER_SENT | Macro, Regime |
| JOLTS | FRED: JTSJOL | MACRO_US_JOLTS | Macro |
| Industrial Production | FRED: INDPRO | MACRO_US_INDPRO | Macro |
| Retail Sales | FRED: RSXFS | MACRO_US_RETAIL_SALES | Macro |

---

## 2. Phase 1 뷰 강화 계획

### 2.1 Price View (`price_view.py`)

**현재**: 5개 신호 (모멘텀 3종 + MA추세 2종)  
**목표**: 기술적 + 센티먼트 + 검증된 멀티팩터로 확장

#### 백테스트 검증
```
검증 대상: 현재 composite_score vs S&P500 21일 선행 수익률
목표: IC ≥ 0.08, Hit Rate ≥ 57%
현재 추정 IC: ~0.04 (신호 부족)
```

#### 추가 신호 (IC ≥ 0.05 검증 후 채택)

| 신호 | 공식 | 방향 |
|------|------|------|
| RSI(14) | 과매도 ≤30 = 반등, 과매수 ≥70 = 조정 | 역방향(단기) |
| Bollinger %B | (P - Lower) / (Upper - Lower) | 역방향(단기) |
| MACD 히스토그램 부호 | EMA12 - EMA26 방향 | 순방향(추세) |
| Put/Call Ratio | CBOE P/C 5일 MA | 역방향(극단값) |
| 52주 신고가 비율 | 신고가 종목수 / 전체 | 순방향 |

#### 로직 정교화
```python
# 현재: 단순 레짐 분기 (RiskON/OFF/Neutral)
# 개선: 신호 IC 기반 동적 가중치

signal_weights = {
    'RiskOFF': {'trend': 0.50, 'momentum': 0.20, 'rsi_contrarian': 0.30},
    'Neutral':  {'trend': 0.30, 'momentum': 0.35, 'rsi_contrarian': 0.20, 'macd': 0.15},
    'RiskON':   {'trend': 0.15, 'momentum': 0.55, 'nearness': 0.20, 'macd': 0.10},
}
```

#### 신규 기능: Dual Momentum Filter
```python
# GEM(Global Equity Momentum) 방식
absolute_mom = (spy_12m > tbill_12m)   # 절대 모멘텀
relative_mom = np.argmax([eq_mom, bond_mom, intl_mom])  # 상대 모멘텀
dual_signal = absolute_mom * relative_mom_weight
```

---

### 2.2 Macro View (`macro_view.py`)

**현재**: 23개 지표 (US 16 + KR 5 + Global 2), 레짐 헤더 카드  
**목표**: Nowcasting + HMM 레짐 분류 + 미구현 지표 수집

#### 백테스트 검증
```
검증: Goldilocks 레짐 → S&P500 6개월 수익률
목표: 레짐 분류 정확도 ≥ 70% (vs NBER 사이클 기준)
```

#### 미구현 지표 수정 (즉시 적용 가능)

| 지표 | 문제 | 해결책 |
|------|------|--------|
| US_ISM_MFG | FRED series_id 오류 | → FRED: ISM001 (NAPM) 또는 MANEMP+IPMAN 합성 |
| US_ISM_SVC | FRED series_id 오류 | → FRED: NMFCI (NMI) |
| KR_CORE_CPI | ECOS item_code 미확인 | → ECOS: 901Y011/19 (core CPI) |

#### 추가 수집 지표

```python
FRED_NEW = {
    'US_PMI_MFG':    'MANEMP',   # Manufacturing PMI 대리변수
    'US_CONSUMER_CONF': 'UMCSENT',  # U Michigan Consumer Sentiment
    'US_REAL_YIELD':  'DFII10',  # 10Y 실질금리 (TIPS)
    'US_TERM_PREM':   'ACMTP10', # ACM Term Premium
    'US_CREDIT_HY':   'BAMLH0A0HYM2',  # HY 스프레드
    'US_FED_BS':      'WALCL',   # Fed 대차대조표
    'US_JOLTS':       'JTSJOL',  # Job Openings (노동시장 선행)
}
```

#### 로직 정교화: Nowcasting 모델

```python
def nowcast_gdp(macro_df, date):
    """
    주간 지표(PMI, 실업보험청구, 소매판매)로 분기 GDP 조기 추정
    Bridge Equation: GDP_t = β0 + β1*PMI + β2*NFP + β3*Retail + ε
    """
    features = ['US_PMI_MFG', 'US_NFP', 'US_RETAIL_SALES']
    # OLS → GDP 성장률 예측값 + 불확실성 구간
```

#### 레짐 헤더 고도화: 4-Cell 매트릭스 강화

```
현재: Goldilocks/Reflation/Stagflation/Deflation (4개)
개선: 확률 % 표시 + 현재 위치 + 방향 화살표

예시:
┌─────────────────────────────────────────┐
│  성장↑ + 인플↓: Goldilocks   [72%] ←현재 │
│  성장↑ + 인플↑: Reflation    [15%]       │
│  성장↓ + 인플↑: Stagflation  [ 8%]       │
│  성장↓ + 인플↓: Deflation    [ 5%]       │
└─────────────────────────────────────────┘
```

---

### 2.3 Correlation View (`correlation_view.py`)

**현재**: Core 8 자산, 30/60/90일 롤링 피어슨 상관  
**목표**: DCC-GARCH + 꼬리 의존성 + 네트워크 분석

#### 백테스트 검증
```
검증: 주식-채권 상관 음수 → 포트폴리오 분산 효과 실현 검증
목표: 상관 체제 전환 감지 정확도 (음→양 전환 후 주식 MDD 상승 여부)
```

#### DCC-GARCH 구현 (핵심 업그레이드)

```python
# arch 라이브러리 활용
from arch import arch_model
from arch.univariate import GARCH

def compute_dcc(returns_df, p=1, q=1):
    """
    Dynamic Conditional Correlation
    1단계: 각 자산 GARCH(1,1) 표준화 잔차
    2단계: 잔차 간 동적 상관 추정
    → 정적 롤링 상관보다 변동성 군집 포착 우수
    """
    standardized = {}
    for col in returns_df.columns:
        garch = arch_model(returns_df[col], vol='GARCH', p=p, q=q)
        res = garch.fit(disp='off')
        standardized[col] = returns_df[col] / res.conditional_volatility
    return pd.DataFrame(standardized).corr()
```

#### 꼬리 의존성 (Tail Dependence)

```python
def tail_dependence_coeff(x, y, threshold=0.05):
    """
    Lower tail: P(X < VaR_5% | Y < VaR_5%)
    → 위기 시 동반 급락 확률 (분산 효과 붕괴 위험)
    """
    q_x = np.percentile(x, threshold*100)
    q_y = np.percentile(y, threshold*100)
    joint = ((x < q_x) & (y < q_y)).mean()
    marginal = (x < q_x).mean()
    return joint / marginal if marginal > 0 else np.nan
```

#### 네트워크 분석 (신규 섹션)

```python
import networkx as nx

def build_correlation_network(corr_matrix, threshold=0.6):
    """
    |상관계수| > threshold 인 자산 쌍을 엣지로
    → 중심성(Centrality) 높은 자산 = 시장 충격 전파 허브
    """
    G = nx.Graph()
    for i in corr_matrix.columns:
        for j in corr_matrix.columns:
            if i != j and abs(corr_matrix.loc[i,j]) > threshold:
                G.add_edge(i, j, weight=abs(corr_matrix.loc[i,j]))
    return nx.betweenness_centrality(G)
```

---

### 2.4 Regime View (`regime_view.py`)

**현재**: 규칙 기반 3-상태 레짐 + 한국어 투자 해설  
**목표**: HMM 확률 기반 + 12-셀 매트릭스 + 동적 NLG

#### 백테스트 검증
```
검증: 레짐 분류 → 다음 레짐 전환 예측 (AUC ≥ 0.70)
검증: 레짐별 최적 전략 vs 벤치마크 초과수익
목표: RiskOFF 감지 후 방어 포트 -> MDD -10%p 감소
```

#### HMM 기반 레짐 감지 (핵심 업그레이드)

```python
from hmmlearn import hmm
import numpy as np

class RegimeHMM:
    def __init__(self, n_states=3):
        self.model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type='full',
            n_iter=200,
            random_state=42
        )
        self.state_names = {0: 'RiskOFF', 1: 'Neutral', 2: 'RiskON'}
    
    def fit(self, features_df):
        """
        features: [vix_norm, yield_curve, breadth_ma200, hy_spread, dxy_chg]
        """
        X = features_df.values
        self.model.fit(X)
        # 상태 순서를 VIX 평균 기준으로 정렬 (낮은 VIX = RiskON)
        return self
    
    def predict_proba(self, features_df):
        """
        returns: DataFrame with columns ['RiskOFF', 'Neutral', 'RiskON']
        각 날짜의 레짐 확률 (합=1.0)
        """
        posteriors = self.model.predict_proba(features_df.values)
        return pd.DataFrame(posteriors, 
                           columns=['RiskOFF', 'Neutral', 'RiskON'],
                           index=features_df.index)
```

#### 12-셀 매트릭스 (Macro × Market)

```
         │  RiskON  │  Neutral │  RiskOFF │
─────────┼──────────┼──────────┼──────────┤
Goldilocks│  ◎ 공세 │  ○ 중립  │  △ 주의  │
Reflation │  ○ 원자재│  △ 혼합  │  ▲ 방어  │
Stagflat. │  ▲ 방어  │  ▲ 방어  │  ✕ 리스크│
Deflation │  △ 채권  │  ▲ 방어  │  ✕ 위기  │
```

#### 자연어 생성 고도화

```python
# 현재: 정적 템플릿 → 개선: 맥락 기반 동적 생성
REGIME_TEMPLATES = {
    ('Goldilocks', 'RiskON'): {
        'headline': "경기와 시장이 동시에 우호적 — 공세적 포지셔닝 권고",
        'risk_prefix': "현재 레짐에서 주요 다운사이드 리스크는",
        'action_verb': "비중 확대",
    },
    ('Stagflation', 'RiskOFF'): {
        'headline': "스태그플레이션 + 리스크오프 — 최대 방어 모드",
        'risk_prefix': "복합 리스크 환경: 인플레이션 + 성장 둔화 + 시장 위험",
        'action_verb': "비중 축소",
    },
    # ... 12개 셀 전부
}

def generate_regime_commentary(macro_regime, market_regime, signals):
    template = REGIME_TEMPLATES.get((macro_regime, market_regime), DEFAULT_TEMPLATE)
    risk_factors = rank_risk_factors(signals)  # 심각도 순 정렬
    return format_commentary(template, risk_factors, signals)
```

---

## 3. Phase 2 뷰 강화 계획

### 3.1 Country View (`country_view.py`)

**현재**: 8개국, 모멘텀+FX+매크로 복합점수  
**목표**: 멀티팩터 (Momentum+Value+Carry) + CFTC 포지셔닝

#### 백테스트 검증
```
검증: OW국 포트폴리오 vs 동일가중 MSCI ACWI
목표: 연간 초과수익 +2%p, 히트율 ≥ 57% (월간 기준)
검증 기간: 2012-2024 (12년 Walk-forward)
```

#### 멀티팩터 신호 확장

```python
# 현재: 모멘텀(12-1M) 중심
# 개선: 3팩터 복합

country_signals = {
    'momentum': {
        'weight_riskon': 0.50,
        'weight_riskoff': 0.20,
        'calc': lambda px: px.pct_change(252).shift(22)  # 12-1 momentum
    },
    'value': {
        'weight_riskon': 0.20,
        'weight_riskoff': 0.40,
        'calc': lambda pe_ratios: -pe_ratios  # 낮은 P/E = 가치
    },
    'carry': {
        'weight_riskon': 0.30,
        'weight_riskoff': 0.40,
        'calc': lambda rates: rates  # 금리 수준 = 캐리
    }
}
```

#### CFTC 포지셔닝 통합 (신규)

```python
# COT 리포트: 투기적 포지션 (Large Speculator Net)
CFTC_CODES = {
    'ES': '13874+',   # S&P500 E-mini
    'NK': '240743+',  # Nikkei 225
    'EC': '099741+',  # EUR/USD (유로존 프록시)
    '6J': '097741+',  # USD/JPY (일본 프록시)
}

def get_cftc_positioning(code, date):
    """
    CFTC는 화요일 데이터를 금요일 공개
    → 주간 업데이트, 역방향 신호 (극단 롱 = 매수 소진)
    """
    url = f"https://www.cftc.gov/dea/futures/deahistfo.htm"
    # ... 파싱 로직
    net_position = long - short
    z_score = (net_position - net_position.rolling(52).mean()) / net_position.rolling(52).std()
    return z_score  # 극단 (+2 이상 = 과매수, -2 이하 = 과매도)
```

#### 동적 환헤지 비율

```python
def dynamic_hedge_ratio(fx_vol, fx_carry, correlation):
    """
    최적 헤지비율 = f(FX 변동성, 캐리 비용, 주식-FX 상관)
    기준: 연간 FX 변동성 > 10% → 헤지 권장
    """
    carry_cost = abs(fx_carry)       # 헤지 비용 (금리차)
    hedge_benefit = fx_vol * 0.68    # 1σ 리스크 감소
    
    if hedge_benefit > carry_cost:
        return min(1.0, hedge_benefit / (carry_cost + hedge_benefit))
    return 0.0
```

---

### 3.2 Sector View (`sector_view.py`)

**현재**: US 11섹터 + KR 4섹터, 상대 모멘텀  
**목표**: 경기사이클 + P/E 밸류에이션 + 이익수정 통합

#### 백테스트 검증
```
검증: Sector OW 포트 vs S&P500 Equal-weight
목표: IC ≥ 0.06 (1M forward), 히트율 ≥ 55% (3M forward)
검증: 경기사이클 국면별 섹터 우세 패턴 재현 여부
```

#### 경기사이클 × 섹터 매트릭스

```python
CYCLE_SECTOR_MAP = {
    'Early_Recovery': {  # 성장 바닥 → 반등
        'OW': ['Technology', 'ConsumerDiscretionary', 'Industrials'],
        'UW': ['Utilities', 'ConsumerStaples', 'Energy']
    },
    'Mid_Expansion': {   # 성장 가속
        'OW': ['Industrials', 'Materials', 'Energy', 'Financials'],
        'UW': ['Utilities', 'REITs']
    },
    'Late_Cycle': {      # 성장 고점 → 둔화
        'OW': ['Energy', 'Materials', 'Healthcare'],
        'UW': ['Technology', 'ConsumerDiscretionary']
    },
    'Recession': {       # 성장 수축
        'OW': ['Utilities', 'ConsumerStaples', 'Healthcare'],
        'UW': ['Financials', 'Industrials', 'Technology']
    }
}
```

#### 이익수정 지표 (신규)

```python
def earnings_revision_ratio(sector, lookback=90):
    """
    ERR = (상향수정 - 하향수정) / 총수정 (지난 lookback일)
    → 양수 = 이익 모멘텀 상승, 음수 = 이익 하향
    데이터: 회사 Bloomberg/Refinitiv (현재 없음 → yfinance earnings 부분 대체)
    """
    # Phase 2 구현 예정 (데이터 확보 후)
    pass

def sector_pe_relative(sector_pe, spx_pe):
    """
    상대 P/E = 섹터 P/E / S&P500 P/E
    역사적 백분위 → 가치(저평가) 신호
    """
    relative = sector_pe / spx_pe
    percentile = stats.percentileofscore(historical_relative_pe[sector], relative)
    return percentile  # 낮을수록 저평가
```

---

### 3.3 Bond View (`bond_view.py`)

**현재**: 듀레이션/커브/크레딧 포지셔닝  
**목표**: 실질금리 + 기간프리미엄 + Nelson-Siegel 분해

#### 백테스트 검증
```
검증: 듀레이션 포지션 → 금리 방향 예측 정확도
목표: 금리 방향 히트율 ≥ 57% (3개월 선행)
검증: 크레딧 스프레드 → HY 채권 초과수익 예측
```

#### 실질금리 분해 (핵심 업그레이드)

```python
def decompose_nominal_yield(nominal_10y, tips_10y, breakeven):
    """
    명목금리 = 실질금리 + 기대인플레이션 + 기간프리미엄
    FRED: DGS10 (명목), DFII10 (실질 TIPS), T10YIE (손익분기점)
    """
    real_yield = tips_10y           # DFII10
    expected_inflation = breakeven  # T10YIE (= 명목 - TIPS)
    term_premium = nominal_10y - real_yield - expected_inflation  # 근사치
    
    return {
        'real_yield': real_yield,
        'expected_inflation': expected_inflation, 
        'term_premium': term_premium,
        'interpretation': interpret_yield_decomposition(real_yield, term_premium)
    }

def interpret_yield_decomposition(real_yield, term_premium):
    if real_yield > 2.0 and term_premium > 0.5:
        return "금리 상승 원인: 긴축 통화정책 + 공급 우려 → 듀레이션 축소"
    elif real_yield < 0 and term_premium < 0:
        return "실질금리 음수 + 기간프리미엄 축소 → 유동성 장세, 주식 우호"
    # ... 추가 해석
```

#### Nelson-Siegel 커브 분해

```python
def nelson_siegel(maturities, beta0, beta1, beta2, tau):
    """
    YTM(T) = β0 + β1*(1-e^(-T/τ))/(T/τ) + β2*[(1-e^(-T/τ))/(T/τ) - e^(-T/τ)]
    β0: 장기금리 수준 (Level)
    β1: 단기 기울기 (Slope)  
    β2: 곡률 (Curvature)
    """
    ...

def fit_ns_curve(yield_data: dict) -> dict:
    """
    yield_data = {0.25: 5.2, 2: 4.8, 5: 4.5, 10: 4.3, 30: 4.4}
    → Level/Slope/Curvature 추출 + 과거 대비 해석
    """
```

#### MOVE Index 통합 (채권 변동성)

```python
# FRED: MOVE (Merrill Lynch Option Volatility Estimate)
# → 채권 시장의 VIX 역할
def bond_vol_regime(move_index):
    if move_index > 130:
        return "채권 변동성 극도 위험 — 듀레이션 최소화"
    elif move_index > 100:
        return "채권 변동성 경계 — 단기 포지션 집중"
    else:
        return "채권 변동성 안정 — 정상 듀레이션 운용"
```

---

### 3.4 Style View (`style_view.py`)

**현재**: 5팩터 (Growth/Value/Quality/Momentum/LowVol)  
**목표**: 팩터 타이밍 백테스트 + P/E 스프레드 + 밸류×모멘텀 인터랙션

#### 백테스트 검증
```
검증: 팩터 신호 → 해당 팩터 ETF 21일 선행 수익률
목표: IC ≥ 0.06, 히트율 ≥ 55%
팩터 타이밍 vs 동일가중 팩터 포트: 연간 초과수익 +1.5%p 목표
```

#### 팩터 밸류에이션 스프레드 (핵심 신호)

```python
def factor_spread_signal(factor_name, lookback_years=10):
    """
    현재 팩터 스프레드의 역사적 백분위
    → 가치 팩터 스프레드가 역사적으로 낮으면 = 가치 과매도 = 매수 신호
    
    데이터 출처:
    - AQR 팩터 밸류에이션 데이터 (공개 데이터셋)
    - Research Affiliates RAFI 스프레드
    - 현재 구현: IVW(성장)/IVE(가치) 상대 P/E 비율
    """
    growth_pe = get_etf_pe('IVW')   # iShares S&P500 Growth
    value_pe  = get_etf_pe('IVE')   # iShares S&P500 Value
    spread = growth_pe / value_pe
    
    hist_percentile = percentile_rank(spread, historical_spreads[factor_name])
    if hist_percentile < 20:
        return ('Value', 'OW', f"가치 스프레드 역사적 저점({hist_percentile:.0f}%ile) — 가치 반등 기대")
    elif hist_percentile > 80:
        return ('Growth', 'OW', f"성장 프리미엄 역사적 고점({hist_percentile:.0f}%ile) — 모멘텀 추종")
    return ('Neutral', 'N', "팩터 스프레드 중립 구간")
```

#### Value × Momentum 인터랙션

```python
def value_momentum_interaction(value_z, momentum_z):
    """
    AQR 연구: 가치 + 모멘텀 동시 신호 = 가장 강한 결합
    1. High Value + High Momentum = 최강 매수 신호
    2. High Value + Low Momentum = 역추세 (Value Trap 위험)
    3. Low Value + High Momentum = 성장주 추세 추종
    4. Low Value + Low Momentum = 기피
    """
    interaction = value_z * momentum_z
    if interaction > 1.0:
        return 2.0  # 강한 양방향 신호
    elif interaction < -0.5:
        return -0.5  # 신호 상충 → 완화
    return interaction
```

#### 레짐별 팩터 우세 패턴

```python
FACTOR_REGIME_MAP = {
    'RiskON':   ['Momentum', 'Growth', 'Quality'],
    'Neutral':  ['Quality', 'LowVol', 'Value'],
    'RiskOFF':  ['LowVol', 'Quality', 'Value'],
    'Goldilocks': ['Momentum', 'Growth'],
    'Stagflation': ['Value', 'LowVol'],
}
```

---

### 3.5 Allocation View (`allocation_view.py`)

**현재**: K-ICS 제약 하 배분 (주식 30% 한도)  
**목표**: Black-Litterman + 리스크 패리티 + 기대수익 추정

#### 백테스트 검증
```
검증: 현재 배분 방식 vs Risk Parity vs BL vs 동일가중
목표: Sharpe Ratio 기준 현재 대비 +0.3 이상
검증 기간: 2015-2024 (K-ICS 도입 이후)
```

#### Black-Litterman 구현

```python
import numpy as np
from scipy.optimize import minimize

class BlackLittermanOptimizer:
    """
    BL = 시장 균형 수익률 + 투자자 뷰 반영
    → 추정 오차에 강건한 포트폴리오 최적화
    """
    def __init__(self, risk_aversion=2.5, tau=0.05):
        self.delta = risk_aversion
        self.tau = tau
    
    def market_equilibrium(self, sigma, weights_market, rf=0.04):
        """역최적화: 시장 포트에서 균형 수익률 추출"""
        pi = self.delta * sigma @ weights_market
        return pi
    
    def posterior_return(self, pi, sigma, P, Q, omega):
        """
        P: 뷰 선택 행렬 (k×n)
        Q: 뷰 기대수익 벡터 (k×1)
        omega: 뷰 불확실성 행렬 (k×k)
        → 사후 기대수익 = BL 공식
        """
        tau_sigma = self.tau * sigma
        M = np.linalg.inv(np.linalg.inv(tau_sigma) + P.T @ np.linalg.inv(omega) @ P)
        mu_bl = M @ (np.linalg.inv(tau_sigma) @ pi + P.T @ np.linalg.inv(omega) @ Q)
        return mu_bl
    
    def views_from_signals(self, scoring_df):
        """
        scoring.py composite_score → BL 뷰로 변환
        상위 자산: +α% 초과수익 기대
        하위 자산: -α% 열위 기대
        """
        top3 = scoring_df.nlargest(3, 'composite_score')
        bot3 = scoring_df.nsmallest(3, 'composite_score')
        # P, Q, Omega 행렬 구성
        ...
```

#### 리스크 패리티

```python
def risk_parity_weights(sigma, target_vol=0.10):
    """
    Risk Parity: 각 자산의 Risk Contribution을 동일하게
    → 변동성 낮은 자산(채권)이 자동으로 고비중
    K-ICS 제약과 병행 (주식 30% 상한 하 Risk Parity)
    """
    n = len(sigma)
    
    def risk_contribution_error(w):
        port_vol = np.sqrt(w @ sigma @ w)
        rc = (sigma @ w) * w / port_vol
        target_rc = port_vol / n
        return np.sum((rc - target_rc)**2)
    
    constraints = [
        {'type': 'eq', 'fun': lambda w: np.sum(w) - 1},
        # K-ICS: 주식 총합 ≤ 30%
        {'type': 'ineq', 'fun': lambda w: 0.30 - sum(w[i] for i in equity_indices)}
    ]
    bounds = [(0.02, 0.40)] * n
    result = minimize(risk_contribution_error, x0=[1/n]*n, 
                     method='SLSQP', bounds=bounds, constraints=constraints)
    return result.x
```

#### 기대수익 추정 모델

```python
def estimate_expected_returns(scoring_df, prices_df, macro_df):
    """
    3가지 기대수익 추정 방식 앙상블:
    1. 역사적 평균 (장기)
    2. CAPM 기반 (시장 베타 × 시장 프리미엄)
    3. 복합 점수 기반 (scoring.py composite_score 선형 변환)
    
    앙상블 = 0.3×역사 + 0.3×CAPM + 0.4×신호기반
    """
    hist_returns = prices_df.pct_change(252).mean() * 252
    capm_returns = compute_capm(prices_df, macro_df)
    signal_returns = scoring_df.set_index('etf')['composite_score'] * 0.15  # 스케일
    
    return 0.3*hist_returns + 0.3*capm_returns + 0.4*signal_returns
```

---

## 4. 구현 로드맵

### Phase 0 — 기반 인프라 (Week 1-2)
> 모든 뷰에 공통 적용되는 기반을 먼저 구축

| 작업 | 파일 | 우선순위 |
|------|------|---------|
| 백테스트 신호 검증 함수 | `portfolio/backtest_signals.py` | ★★★ |
| Walk-Forward 엔진 | `portfolio/walk_forward.py` | ★★★ |
| FRED 데이터 확장 수집 | `portfolio/macro_indicators.yaml` (통합 완료 ✅) | ★★★ |
| HMM 레짐 분류기 | `portfolio/view/regime_classifier.py` | ★★☆ |

```bash
# 새 의존성 설치
.venv/bin/pip install hmmlearn arch networkx scipy
```

### Phase 1A — 즉시 수익 (Week 2-3)
> 현재 코드 수정으로 즉시 개선 가능한 항목

| 작업 | 파일 | 예상 효과 |
|------|------|---------|
| Macro View 미구현 지표 수정 (ISM, KR Core CPI) | `macro_view.py` | 지표 커버리지 +3개 |
| Bond View 실질금리 (DFII10) + MOVE Index 추가 | `bond_view.py` | 채권 신호 품질 ↑ |
| Regime View 12-셀 매트릭스 UI | `regime_view.py` | 사용자 이해도 ↑ |
| Price View RSI/MACD 추가 | `price_view.py` | 기술적 신호 다양화 |

### Phase 1B — 핵심 로직 강화 (Week 3-5)
> 주요 알고리즘 개선

| 작업 | 파일 | 예상 효과 |
|------|------|---------|
| HMM 확률 기반 레짐 (3상태) | `regime_view.py`, `scoring.py` | 레짐 전환 조기 감지 +2주 |
| DCC-GARCH 상관 | `correlation_view.py` | 위기 상관 포착 정확도 ↑ |
| 멀티팩터 국가 신호 (Momentum+Value+Carry) | `country_view.py` | IC +0.03~0.05 예상 |
| 팩터 밸류에이션 스프레드 | `style_view.py` | 팩터 타이밍 개선 |

### Phase 2 — 고급 최적화 (Week 5-8)
> 계량 모델 통합

| 작업 | 파일 | 예상 효과 |
|------|------|---------|
| Black-Litterman 최적화 | `allocation_view.py` | 추정 오차 강건성 ↑ |
| Risk Parity (K-ICS 제약) | `allocation_view.py` | Sharpe +0.3 예상 |
| Nelson-Siegel 커브 분해 | `bond_view.py` | 커브 구조 이해 ↑ |
| CFTC 포지셔닝 데이터 | `country_view.py`, `style_view.py` | 역방향 신호 추가 |
| Nowcasting GDP 모델 | `macro_view.py` | GDP 조기 추정 |
| 네트워크 중심성 분석 | `correlation_view.py` | 위기 전파 허브 식별 |

### Phase 3 — 통합 & 검증 (Week 8-10)
> 모든 개선 사항 통합 후 전체 시스템 검증

| 작업 | 설명 |
|------|------|
| 전체 Walk-Forward 검증 | 2015-2024 10년 OOS 성과 확인 |
| 뷰 간 일관성 체크 | Regime → Country/Sector/Bond 신호 정합성 |
| View Agent 허브 업데이트 | `output/view/index.html` 새 지표 반영 |
| 성과 리포트 생성 | 각 뷰별 IC/Hit Rate/Sharpe 요약 |

---

## 5. 성과 목표 (KPI)

| 뷰 | 현재 (추정) | 목표 (6개월 후) | 핵심 측정 지표 |
|----|------------|----------------|----------------|
| Price | IC ~0.04 | IC ≥ 0.08 | 21일 선행 S&P500 수익률 IC |
| Macro | 레짐 정확도 ~60% | ≥ 72% | vs NBER 사이클 기준 분류 정확도 |
| Correlation | 정적 롤링 | 동적 DCC | 위기 상관 포착 적시성 (일수 단축) |
| Regime | 이진 분류 | 확률 추정 | AUC ≥ 0.70 (전환 예측) |
| Country | IC ~0.03 | IC ≥ 0.07 | 월간 국가 순환 포트 초과수익 |
| Sector | IC ~0.04 | IC ≥ 0.07 | 사이클 연동 히트율 ≥ 55% |
| Bond | 방향성 히트율 ~52% | ≥ 57% | 3개월 금리 방향 히트율 |
| Style | IC ~0.03 | IC ≥ 0.06 | 팩터 타이밍 연간 초과수익 +1.5%p |
| Allocation | Sharpe ~0.6 | ≥ 0.9 | K-ICS 제약 하 연간 Sharpe |

---

## 6. 의존성 및 데이터 소스 요약

### 신규 Python 패키지
```bash
.venv/bin/pip install hmmlearn arch networkx scipy statsmodels
```

### 신규 FRED 데이터 (수집 스크립트 추가 필요)
```
BAMLH0A0HYM2  HY Credit Spread
TEDRATE       TED Spread  
DFII10        10Y TIPS Real Yield
ACMTP10       ACM Term Premium
WALCL         Fed Balance Sheet
UMCSENT       U Michigan Consumer Sentiment
JTSJOL        JOLTS Job Openings
T10YIE        10Y Breakeven Inflation
```

### 신규 외부 데이터 (수집 구현 필요)
```
CFTC COT 리포트  - https://www.cftc.gov/MarketReports
AQR 팩터 데이터  - https://www.aqr.com/Insights/Datasets
```

---

## 7. 구현 원칙

1. **검증 우선**: 모든 신호는 IC/Hit Rate 검증 후 production 적용
2. **레짐 조건부**: 신호 가중치는 레짐별로 분리 (단일 파라미터 금지)
3. **점진적 배포**: 뷰별 독립 배포, 기존 뷰 파괴 없음
4. **데이터 안정성**: 신규 FRED 지표 수집 실패 시 graceful fallback (기존 로직 유지)
5. **성과 추적**: 매월 IC/Hit Rate 업데이트 → PLAN 재검토

---

*VIEW_AGENT_MASTER_PLAN.md | 2026-04-13 | 9개 뷰 에이전트 강화 전략 종합*
