# Scenario Framework — Bull/Base/Bear 시나리오 구조

---

## 개요

가중 투표 결과를 바탕으로 3개월/6개월 시점의 Bull·Base·Bear 시나리오를 구성한다.
각 시나리오는 단순한 숫자가 아니라 **스토리라인**을 갖춰야 한다.
"왜 Bull인지" → "어떤 조건이 필요한지" → "무엇을 모니터링할지" → "언제 무효화되는지"

---

## 시나리오 구조 (3개월/6개월 각각)

### Bull Case

```json
{
  "scenario": "Bull",
  "timeframe": "3M",
  "probability_pct": 40,
  "return_range": "+8% ~ +15%",
  
  "narrative": "AI 인프라 투자 사이클 가속 + 빅테크 어닝 서프라이즈 연속. 금리 안정화와 맞물려 Tech 멀티플 확장.",
  
  "prerequisites": [
    "다음 분기 빅테크 어닝 서프라이즈 (NVDA, MSFT, GOOGL 중 2개 이상)",
    "미국 10Y 금리 4.5% 이하 안정",
    "AI CapEx 가이던스 상향 (NVDA, AMD 등)",
    "달러 약세 전환 (DXY 103 이하)"
  ],
  
  "catalyst_timeline": [
    {"event": "NVDA 어닝 발표", "expected_date": "2025-05-28", "impact": "AI 수요 확인"},
    {"event": "Fed FOMC", "expected_date": "2025-06-18", "impact": "금리 인하 시그널"}
  ],
  
  "monitoring_indicators": [
    {"indicator": "NVDA 어닝 서프라이즈율", "threshold": "> +10%", "frequency": "분기"},
    {"indicator": "10Y 금리", "threshold": "< 4.5%", "frequency": "주간"},
    {"indicator": "ETF 자금유입", "threshold": "> $500M/주", "frequency": "주간"},
    {"indicator": "VIX", "threshold": "< 18", "frequency": "일간"}
  ],
  
  "invalidation_triggers": [
    "빅테크 어닝 미스 2개 이상",
    "10Y 금리 5% 돌파",
    "VIX 30 이상 급등",
    "AI 규제 입법 통과"
  ]
}
```

### Base Case

```json
{
  "scenario": "Base",
  "timeframe": "3M",
  "probability_pct": 35,
  "return_range": "+2% ~ +8%",
  
  "narrative": "현 수준에서 완만한 상승. 어닝 성장은 유지되나 금리 불확실성이 상방을 제한. 박스권 등락 후 점진적 우상향.",
  
  "prerequisites": [
    "어닝 성장률 한자릿수 유지",
    "금리 현 수준 횡보 (4.2%~4.6%)",
    "특별한 매크로 이벤트 없음"
  ],
  
  "monitoring_indicators": [
    {"indicator": "어닝 리비전 비율", "threshold": "상향 50%~60%", "frequency": "월간"},
    {"indicator": "10Y 금리", "threshold": "4.2%~4.6% 횡보", "frequency": "주간"},
    {"indicator": "ETF 자금흐름", "threshold": "순유입 유지", "frequency": "주간"}
  ],
  
  "transition_triggers": {
    "to_bull": "어닝 서프라이즈 + 금리 하락 동시 발생",
    "to_bear": "어닝 미스 + 금리 상승 동시 발생"
  }
}
```

### Bear Case

```json
{
  "scenario": "Bear",
  "timeframe": "3M",
  "probability_pct": 25,
  "return_range": "-5% ~ -15%",
  
  "narrative": "금리 재인상 우려 + 어닝 하향 사이클 진입. Tech 멀티플 압축과 수급 악화가 동시 진행.",
  
  "prerequisites": [
    "CPI 재가속 또는 고용 과열 지속",
    "Fed 금리 인하 연기 또는 인상 시사",
    "빅테크 CapEx 축소 시그널"
  ],
  
  "catalyst_timeline": [
    {"event": "CPI 발표", "expected_date": "2025-05-13", "impact": "인플레이션 방향 확인"},
    {"event": "Fed 의사록", "expected_date": "2025-05-28", "impact": "정책 방향 확인"}
  ],
  
  "monitoring_indicators": [
    {"indicator": "CPI YoY", "threshold": "> 3.5%", "frequency": "월간"},
    {"indicator": "10Y 금리", "threshold": "> 4.8%", "frequency": "주간"},
    {"indicator": "ETF 자금유출", "threshold": "> $300M/주", "frequency": "주간"},
    {"indicator": "VIX", "threshold": "> 25", "frequency": "일간"},
    {"indicator": "공매도 잔고", "threshold": "상승 추세", "frequency": "주간"}
  ],
  
  "invalidation_triggers": [
    "CPI 급락 + Fed 비둘기파 선회",
    "빅테크 어닝 대규모 서프라이즈"
  ],
  
  "downside_protection": {
    "support_levels": "200일 이동평균, 전저점",
    "hedging_options": "VIX 콜, 인버스 ETF"
  }
}
```

---

## 시나리오 작성 원칙

### 1. 확률은 투표 결과 기반

가중 투표에서 나온 Bull/Base/Bear 확률을 그대로 사용한다.
단, Orchestrator가 투표 결과와 시나리오를 연결할 때 아래를 확인:

- 3개 시나리오 확률 합 = 100%
- 가장 높은 확률의 시나리오가 "winner"
- 확률 차이가 5% 이내면 "Too close to call" 표기

### 2. 서술은 인과관계 중심

나쁜 예: "AI가 잘 되면 오를 것"
좋은 예: "NVDA 데이터센터 매출이 컨센서스 $28B 대비 +15% 서프라이즈 시, AI CapEx 사이클 재가속 확인 → 관련 ETF 멀티플 확장 기대. 과거 유사 서프라이즈(2024Q1) 때 +12% 상승 선례."

### 3. 전제 조건은 검증 가능해야

나쁜 예: "경기가 좋아지면"
좋은 예: "ISM 제조업 PMI 52 이상 + Non-Farm Payroll 15만~25만명 레인지"

### 4. 모니터링 지표는 구체적 임계값 포함

각 지표에 반드시 포함:
- 지표명 (정확한 데이터 소스)
- 임계값 (방향 + 수치)
- 체크 빈도 (일간/주간/월간/분기)

### 5. 전환 트리거는 양방향

Bull → Bear 뿐 아니라 Bear → Bull 전환 조건도 명시.
이를 통해 투자자가 포지션 재검토 시점을 판단할 수 있다.

---

## 수익률 레인지 산정 기준

수익률 레인지는 아래 요소를 종합하여 산정:

1. **과거 유사 국면 수익률**: Agent 7(Regime/Macro)의 국면별 성과 데이터
2. **밸류에이션 업사이드/다운사이드**: Agent 4(Fundamental)의 밸류에이션 밴드
3. **어닝 성장률 × 멀티플 변화**: 수익률 = 어닝성장률 + 멀티플변화율 + 배당수익률
4. **피어 ETF 과거 수익률 분포**: Agent 8(Peer)의 비교 데이터

```
예상 수익률 = EPS 성장률 기여 + PER 변화 기여 + 배당 수익률
Bull: 낙관적 EPS × 멀티플 확장
Base: 컨센서스 EPS × 멀티플 유지
Bear: 하향 EPS × 멀티플 수축
```

---

## 시나리오 매트릭스 (보고서용)

보고서에 포함될 시나리오 요약 테이블:

| 항목 | Bull | Base | Bear |
|---|---|---|---|
| **확률** | XX% | XX% | XX% |
| **수익률 레인지** | +X%~+X% | +X%~+X% | -X%~-X% |
| **핵심 동인** | (1줄 요약) | (1줄 요약) | (1줄 요약) |
| **전제 조건** | (1~2개) | (1~2개) | (1~2개) |
| **무효화 조건** | (1개) | — | (1개) |
| **투표 합의** | Strong/Moderate/Mixed | — | — |
| **소수 의견** | (있다면 요약) | — | — |

---

## 모니터링 대시보드 (보고서 부록)

분석 시점의 각 모니터링 지표 현재값을 기록하여,
향후 리뷰 시 변화를 추적할 수 있도록 한다:

```json
{
  "snapshot_date": "2025-04-12",
  "indicators": [
    {"name": "US 10Y Yield", "current": "4.35%", "bull_threshold": "< 4.2%", "bear_threshold": "> 4.8%"},
    {"name": "VIX", "current": "16.2", "bull_threshold": "< 15", "bear_threshold": "> 25"},
    {"name": "DXY", "current": "104.5", "bull_threshold": "< 103", "bear_threshold": "> 107"},
    {"name": "ETF Weekly Flow ($M)", "current": "+320", "bull_threshold": "> +500", "bear_threshold": "< -300"}
  ]
}
```
