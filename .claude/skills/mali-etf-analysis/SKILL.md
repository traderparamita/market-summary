---
name: mali-etf-analysis
description: >
  Swarm 멀티에이전트 기반 ETF 심층 분석 스킬.
  8개 전문 에이전트(ETF Profile, Holdings, Sector/Theme, Fundamental, Sentiment/Flow,
  Performance, Regime/Macro, Peer Comparison)가 독립 분석 후 교차 검토·토론·가중 투표를 거쳐
  3개월/6개월 Bull·Base·Bear 시나리오를 도출한다.

  Reddit(r/investing, r/ETFs, r/wallstreetbets, 테마별 서브레딧), Seeking Alpha, X/Twitter,
  Morningstar, Bloomberg/Reuters 등 전문가 네트워크와 커뮤니티를 집중 서치하여
  센티먼트·수급 분석을 수행한다.

  한국 ETF의 경우 KRX/운용사 PDF → Naver Finance → Morningstar → yfinance 폴백 체인으로
  데이터 한계를 보완한다.

  다음 요청이 들어올 때 이 스킬을 사용하라:
  - 특정 ETF의 심층 분석 또는 투자 보고서 작성
  - ETF의 Bull/Base/Bear 케이스 시나리오 분석
  - ETF 관련 센티먼트, 수급, 테마 트렌드 분석
  - ETF 편입 종목의 펀더멘털 집계 분석
  - ETF의 시장 국면별 성과·매크로 민감도 분석
  - "이 ETF 사도 돼?", "이 ETF 전망은?", "ETF 분석해줘" 같은 일반적 ETF 분석 요청
  - 여러 ETF 비교 분석 (피어 비교)

compatibility: "Required: WebSearch, WebFetch, Agent (subagent parallel execution), bash_tool. Optional: Morningstar MCP tools (id-lookup, data, fund-holdings, analyst-research, screener, articles)"
---

# MALI ETF Swarm Analysis — 멀티에이전트 심층 분석

## 핵심 개념

이 스킬은 단일 모델이 순차적으로 분석하는 방식이 아니라, **8개 전문 에이전트가 독립 분석 → 교차 검토 → 토론 → 가중 투표**를 거쳐 합의를 형성하는 Swarm 패턴을 사용한다.
각 에이전트는 자신의 전문 영역에서만 의견을 내고, 다른 에이전트의 의견과 충돌할 때 명시적으로 반박하거나 수정한다. 이를 통해 단일 관점의 편향을 줄이고, 시각 충돌을 투명하게 드러낸다.

최종 산출물은 **3개월/6개월 시점의 Bull·Base·Bear 시나리오** + **DOCX 보고서** + **XLSX 데이터 시트**이다.

References:
- `references/agent-profiles.md` — 각 에이전트 역할, 도구, 프롬프트 템플릿
- `references/debate-protocol.md` — 교차 검토·토론·투표 프로토콜
- `references/data-sources.md` — 데이터 소스 폴백 체인, 웹서치 패턴
- `references/scenario-framework.md` — Bull/Base/Bear 시나리오 구조
- `references/report-template.md` — DOCX 보고서 섹션 구성

---

## 전체 워크플로우

```
사용자 입력: ETF 티커(들) + 분석 목적 (선택)
    │
    ▼
PHASE 0: Orchestrator — 티커 유효성 확인, ETF 분류, 분석 범위 결정
    │
    ▼
PHASE 1: 데이터 수집 (2개 에이전트 병렬)
    ├── Agent 1: ETF Profile — 기본정보, AUM, 보수, 추적지수, 가격 시계열
    └── Agent 2: Holdings — 보유종목 전체, 섹터·지역 분포, 집중도(HHI)
    │
    ▼
PHASE 2: 심층 분석 (5개 에이전트 병렬, Phase 1 결과를 입력)
    ├── Agent 3: Sector/Theme — 테마 식별, 글로벌 자금 흐름, 테마 성숙도
    ├── Agent 4: Fundamental — 편입기업 집계 펀더멘털, 어닝 트렌드, 밸류에이션 밴드
    ├── Agent 5: Sentiment/Flow — Reddit·SA·X·전문가 센티먼트 + ETF 수급
    ├── Agent 6: Performance — 수익률·변동성·샤프·MDD·추적오차
    └── Agent 7: Regime/Macro — 국면별 성과, 매크로 민감도
    │
    ▼
PHASE 3: 토론 & 투표 (Debate & Vote)
    ├── Step 1: 각 에이전트 독립 의견서 제출 (3개월/6개월 Bull/Base/Bear 확률)
    ├── Step 2: 교차 검토 — 다른 에이전트 의견 읽고 동의/반박, 자기 의견 수정 가능
    └── Step 3: 최종 가중 투표 → 합의 판정
    │
    ▼
PHASE 4: 피어 비교 (Phase 3 결론 반영)
    └── Agent 8: Peer Comparison — 동일 카테고리 ETF 5~10개 비교
    │
    ▼
PHASE 5: 종합 보고서 (Orchestrator)
    ├── Bull/Base/Bear 시나리오 (3개월 + 6개월)
    ├── 에이전트 간 토론 하이라이트
    ├── 모니터링 트리거
    ├── DOCX 보고서
    └── XLSX 데이터 시트
```

---

## PHASE 0: Orchestrator — 초기 분류

사용자로부터 ETF 티커를 받으면:

1. **티커 유효성**: yfinance 또는 Morningstar로 티커 존재 확인
2. **ETF 분류**: 자산군(주식/채권/원자재/혼합), 지역(미국/글로벌/한국/신흥국), 테마(AI/반도체/에너지/ESG 등), 패시브/액티브
3. **한국 ETF 여부 판단**: 티커가 숫자 6자리 또는 .KS/.KQ 접미사 → 한국 ETF 데이터 폴백 체인 활성화
4. **분석 범위 결정**: Lookback 기간 (기본 5년, 한국 ETF는 설정일~현재)

이 정보를 `etf_context` 객체에 담아 모든 에이전트에 전달한다.

---

## PHASE 1: 데이터 수집 (병렬)

→ `references/agent-profiles.md` 의 Agent 1, Agent 2 참조
→ `references/data-sources.md` 의 폴백 체인 참조

Agent 1 (ETF Profile)과 Agent 2 (Holdings)를 **동시에** 서브에이전트로 실행.
각 에이전트에 `etf_context`를 전달하고, 결과를 JSON으로 수집한다.

---

## PHASE 2: 심층 분석 (5개 에이전트 병렬)

→ `references/agent-profiles.md` 의 Agent 3~7 참조

Phase 1 결과(profile + holdings)를 포함하여 Agent 3~7을 **동시에** 서브에이전트로 실행.
각 에이전트는 독립적으로 분석하되, Phase 1 데이터를 공통 입력으로 사용한다.

**Sentiment/Flow Agent (Agent 5) 웹서치 전략:**

이 에이전트가 이 스킬의 핵심 차별점이다.
→ `references/data-sources.md` 의 "Sentiment/Flow 웹서치 매트릭스" 참조

**★ 핵심 원칙: ETF 레벨이 아닌 Top 10 보유종목 기업 기준으로 검색한다.**
ETF 자체의 센티먼트/수급은 보조 지표일 뿐이며, 실제 가격을 움직이는 것은
편입 기업들의 센티먼트와 수급이다. Phase 1에서 확보한 Top 10 종목 각각에 대해
아래 소스를 모두 검색해야 한다:

- Reddit: 각 Top 10 종목명/티커로 r/investing, r/stocks, r/wallstreetbets + 테마별 서브레딧
- Seeking Alpha: 각 Top 10 종목의 분석 기사, 투자의견, Quant Rating
- X/Twitter: 각 종목의 핀트위터 키 오피니언 리더 의견
- Morningstar: articles tool (연결 시) — 각 종목 관련 기사
- Bloomberg/Reuters: 각 종목의 기관 뷰, 어닝 전망
- 한국 ETF 추가: Naver Finance 종목토론방 (ETF 자체)

각 종목별 센티먼트를 비중 가중 집계하여 ETF 전체 센티먼트 스코어를 산출한다.

---

## PHASE 3: 토론 & 투표 ★핵심

→ `references/debate-protocol.md` 전체 참조

이 Phase가 이 스킬의 가장 중요한 단계이다. 단순 병렬 분석을 합치는 것이 아니라,
에이전트 간 시각 충돌을 명시적으로 드러내고 토론을 통해 합의를 형성한다.

### Step 1: 독립 의견서 (5개 에이전트)

Phase 2의 Agent 3~7 각각이 자기 분석만으로 아래 포맷의 의견서를 제출:

```json
{
  "agent": "Fundamental",
  "outlook_3m": {"bull": 40, "base": 35, "bear": 25},
  "outlook_6m": {"bull": 50, "base": 30, "bear": 20},
  "reasoning_3m": "어닝 성장 +12% YoY, PER 15x로 5년 평균 대비 -1σ...",
  "reasoning_6m": "...",
  "key_catalyst": "다음 분기 어닝 서프라이즈 가능성",
  "key_risk": "금리 인상 지속 시 멀티플 압축",
  "conviction": 4
}
```

### Step 2: 교차 검토 (Cross-Review)

각 에이전트가 다른 4개 의견서를 읽고:
- 동의/반박 포인트 명시
- 시각 충돌 드러내기 (예: "Fundamental은 Bull인데 Sentiment는 Bear인 이유")
- 자기 의견 수정 가능 (수정 시 이유 명시, 변경 이력 보존)

교차 검토는 Orchestrator가 모든 의견서를 취합한 뒤,
각 에이전트에게 "다른 에이전트들의 의견은 이렇다. 반박하거나 수정하라"는 프롬프트로 다시 호출.

### Step 3: 최종 가중 투표

각 에이전트의 최종 투표를 아래 가중치로 집계:

| Agent | 가중치 | 이유 |
|---|---|---|
| Fundamental | 25% | 기업 가치의 근간 |
| Sentiment/Flow | 25% | 단기 가격 동인 |
| Sector/Theme | 20% | 구조적 트렌드 |
| Regime/Macro | 20% | 시장 환경 |
| Performance | 10% | 후행지표이므로 낮게 |

합의 판정:
- **Strong conviction**: 4개 이상 동일 방향 + 평균 확신도 ≥ 4
- **Moderate conviction**: 3:2 분열 또는 평균 확신도 3~4
- **Mixed signal**: 확신도 낮거나 극단적 분열 → 양측 논거 모두 보고서에 수록

---

## PHASE 4: 피어 비교

→ `references/agent-profiles.md` 의 Agent 8 참조

Phase 3의 투표 결과를 참조하여, 동일 카테고리 ETF 5~10개와 비교.
비용, 유동성, 성과, 추적오차, 보유종목 차이를 매트릭스로 정리.

---

## PHASE 5: 종합 보고서

→ `references/report-template.md` 참조
→ `references/scenario-framework.md` 참조

### Bull/Base/Bear 시나리오 구조 (3개월 + 6개월 각각):

각 시나리오에 반드시 포함할 항목:
1. **시나리오 서술**: 어떤 일이 일어나야 하는지
2. **예상 수익률 레인지**: 예) Bull +8%~+15%
3. **확률**: 가중 투표 기반 (예: Bull 45%, Base 35%, Bear 20%)
4. **핵심 전제 조건**: 이것이 틀리면 시나리오 무효
5. **모니터링 지표**: 매주/매월 체크할 데이터 포인트
6. **전환 트리거**: 어떤 조건이면 Bull→Bear (또는 반대) 전환

### 산출물:
- **DOCX**: 기관 투자자용 한국어 보고서 (15~20페이지)
  → docx 스킬 사용하여 생성
- **XLSX**: 원본 데이터 + 센티먼트 로그 + 피어 비교표 + 투표 매트릭스
  → xlsx 스킬 사용하여 생성

---

## 에이전트 실행 패턴

각 에이전트는 Agent tool로 서브에이전트로 실행한다.

**Phase 1 (병렬 2개):**
```
Agent 1: ETF Profile → prompt에 etf_context + data-sources.md 내용 포함
Agent 2: Holdings → prompt에 etf_context + data-sources.md 내용 포함
```

**Phase 2 (병렬 5개):**
```
Agent 3~7: 각각 prompt에 etf_context + Phase 1 결과 + agent-profiles.md 해당 섹션 포함
```

**Phase 3 (순차):**
```
Step 1: Phase 2 결과에서 각 에이전트 의견서 추출 (Phase 2 프롬프트에 의견서 제출 포함)
Step 2: 5개 에이전트 교차 검토 (병렬 5개) — 전체 의견서 세트를 각 에이전트에 전달
Step 3: Orchestrator가 투표 집계
```

**서브에이전트 프롬프트 작성 원칙:**
- 각 에이전트에게 역할(persona), 사용할 도구, 분석 범위를 명확히 지정
- Phase 1 데이터는 프롬프트에 직접 포함 (파일 경로가 아닌 텍스트)
- 의견서 JSON 포맷을 프롬프트에 포함하여 구조화된 출력 유도
- 웹서치 에이전트는 검색 쿼리 목록을 미리 제시하되, 결과에 따라 추가 검색 허용
