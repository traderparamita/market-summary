# Debate & Vote Protocol — 토론·투표 프로토콜

---

## 개요

이 프로토콜은 5개 분석 에이전트(Agent 3~7)가 독립 의견을 내고,
상호 검토를 통해 시각 충돌을 드러낸 뒤, 가중 투표로 합의를 형성하는 과정을 정의한다.

핵심 원칙:
- **독립성 우선**: 각 에이전트는 먼저 자기 데이터만으로 판단한다
- **충돌은 가치**: 에이전트 간 의견 불일치는 숨기지 않고 명시적으로 드러낸다
- **근거 기반 수정**: 의견을 바꿀 때는 반드시 어떤 근거 때문인지 기록한다
- **소수 의견 보존**: 투표에서 진 의견도 보고서에 "소수 의견"으로 수록한다

---

## Step 1: 독립 의견서 제출

Phase 2 완료 후, 각 에이전트(3~7)가 아래 JSON 포맷의 의견서를 제출한다.
이 의견서는 Phase 2 분석 결과의 마지막 부분에 포함되어야 한다.

```json
{
  "agent_name": "Fundamental",
  "agent_id": 4,

  "outlook_3m": {
    "bull_pct": 40,
    "base_pct": 35,
    "bear_pct": 25,
    "reasoning": "어닝 성장 +12% YoY, PER 15x로 5년 평균 대비 -1σ. 다만 금리 불확실성으로 단기 상방 제한."
  },

  "outlook_6m": {
    "bull_pct": 50,
    "base_pct": 30,
    "bear_pct": 20,
    "reasoning": "어닝 성장세 유지 + 밸류에이션 리레이팅 기대. AI 테마 구조적 수요 지속."
  },

  "key_catalyst": "다음 분기 빅테크 어닝 서프라이즈",
  "key_risk": "10Y 금리 5% 돌파 시 멀티플 압축",
  "conviction": 4,
  "suggested_action": "매수",
  "price_target_range_3m": "+5% ~ +12%",
  "price_target_range_6m": "+8% ~ +20%"
}
```

**conviction 척도:**
- 5: 매우 확신 (데이터가 일관되게 한 방향)
- 4: 상당히 확신 (대부분 지표가 지지)
- 3: 보통 (혼재 신호)
- 2: 낮은 확신 (불확실성 높음)
- 1: 매우 낮은 확신 (데이터 부족 또는 극도의 혼재)

---

## Step 2: 교차 검토 (Cross-Review)

Orchestrator가 5개 의견서를 모두 취합한 뒤,
각 에이전트에게 다른 4개 의견서를 보여주며 교차 검토를 요청한다.

**교차 검토 프롬프트 템플릿:**

```
당신은 {agent_name} Agent입니다.
당신의 원래 의견서는 다음과 같습니다:
{own_opinion}

다른 에이전트들의 의견서는 다음과 같습니다:
{other_opinions}

아래 포맷으로 교차 검토 결과를 제출하세요:

1. 동의하는 포인트 (어떤 에이전트의 어떤 근거에 동의하는지)
2. 반박하는 포인트 (어떤 에이전트의 어떤 근거에 반박하는지, 이유와 함께)
3. 핵심 시각 충돌 (가장 큰 의견 불일치가 무엇이고, 왜 발생하는지)
4. 수정된 의견서 (다른 에이전트의 의견을 반영해 수정한 경우, 원본과 차이를 명시)
   수정하지 않을 경우 원본 유지, 이유 명시
```

**교차 검토 출력 포맷:**

```json
{
  "agent_name": "Fundamental",
  "agreements": [
    {"with_agent": "Regime/Macro", "point": "금리 민감도 높다는 진단에 동의"}
  ],
  "rebuttals": [
    {
      "against_agent": "Sentiment/Flow",
      "their_claim": "Reddit 부정 센티먼트 급증으로 Bear 우세",
      "my_rebuttal": "리테일 센티먼트는 후행적. 어닝 서프라이즈가 센티먼트를 반전시킬 가능성 높음.",
      "evidence": "과거 3번의 어닝 서프라이즈 후 센티먼트 반전 사례"
    }
  ],
  "key_conflict": "Fundamental vs Sentiment: 밸류에이션 매력 vs 수급 악화",
  "revised_opinion": {
    "changed": true,
    "change_reason": "매크로 에이전트의 금리 시나리오를 반영해 Bull 확률 하향 조정",
    "outlook_3m": {"bull_pct": 35, "base_pct": 40, "bear_pct": 25},
    "outlook_6m": {"bull_pct": 45, "base_pct": 35, "bear_pct": 20},
    "conviction": 3
  }
}
```

---

## Step 3: 최종 가중 투표

교차 검토 완료 후, 각 에이전트의 최종 의견(수정 의견 또는 원본 유지)에서
투표를 집계한다.

### 가중치 테이블:

| Agent | 가중치 | 근거 |
|---|---|---|
| Fundamental (Agent 4) | 25% | 기업 가치의 근간, 장기 수익률의 핵심 동인 |
| Sentiment/Flow (Agent 5) | 25% | 단기 가격 변동의 직접적 동인, 수급이 가격을 만든다 |
| Sector/Theme (Agent 3) | 20% | 구조적 트렌드, 중기 방향성 결정 |
| Regime/Macro (Agent 7) | 20% | 시장 환경이 개별 ETF 성과를 지배하는 경우 많음 |
| Performance (Agent 6) | 10% | 후행지표, 미래보다 과거를 반영 |

### 집계 방식:

```python
# 3개월 전망 집계 예시
weighted_bull_3m = sum(agent.outlook_3m.bull_pct * weight for agent, weight in agents_weights)
weighted_base_3m = sum(agent.outlook_3m.base_pct * weight for agent, weight in agents_weights)
weighted_bear_3m = sum(agent.outlook_3m.bear_pct * weight for agent, weight in agents_weights)
# 정규화
total = weighted_bull_3m + weighted_base_3m + weighted_bear_3m
final_bull_3m = weighted_bull_3m / total * 100
final_base_3m = weighted_base_3m / total * 100
final_bear_3m = weighted_bear_3m / total * 100
```

### 합의 판정:

```
if max(final_bull, final_base, final_bear) >= 55 and avg_conviction >= 4:
    verdict = "Strong Conviction"
elif max(final_bull, final_base, final_bear) >= 45 and avg_conviction >= 3:
    verdict = "Moderate Conviction"
else:
    verdict = "Mixed Signal"
```

### 최종 투표 결과 포맷:

```json
{
  "vote_result": {
    "outlook_3m": {
      "bull_pct": 38.5,
      "base_pct": 37.0,
      "bear_pct": 24.5,
      "winner": "Bull",
      "conviction_level": "Moderate",
      "avg_conviction": 3.4
    },
    "outlook_6m": {
      "bull_pct": 46.0,
      "base_pct": 32.5,
      "bear_pct": 21.5,
      "winner": "Bull",
      "conviction_level": "Moderate",
      "avg_conviction": 3.6
    },
    "dissenting_opinions": [
      {
        "agent": "Sentiment/Flow",
        "position": "Bear (3m)",
        "key_argument": "Reddit/SA 부정 센티먼트 + 기관 자금 유출 3주 연속"
      }
    ],
    "key_debate_points": [
      "Fundamental vs Sentiment: 밸류에이션 매력 vs 수급 악화 — 결론: 어닝 시즌이 분기점",
      "Theme vs Macro: AI 테마 구조적 성장 vs 금리 환경 역풍 — 결론: 금리 안정 시 테마 승"
    ]
  }
}
```

---

## 토론 로그 보존

전체 토론 과정(Step 1 원본 의견서 → Step 2 교차 검토 → Step 3 투표)을
`debate_log.json`으로 저장하여 DOCX 보고서 부록에 포함한다.
투자자가 "왜 이런 결론이 나왔는지" 역추적할 수 있어야 한다.
