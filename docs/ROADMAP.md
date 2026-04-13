# market_summary → 자산배분 운용 플랫폼 확장 로드맵

> 2026-04-11 합의. 사용자: 운영자 / 1차 독자: PM·리서치 + PB·영업

## 현재 상태 (2026-04-13 업데이트)

### 완료

**인프라 / 구조**
- ✅ **3-tier 출력 구조**: `output/summary/`, `output/portfolio/aimvp/`, `output/view/` 분리
- ✅ **Commands/Skills 경로 정합**: `/market-full`, `/market-data`, `/market-deploy`, `market-summary` 스킬 모두 업데이트

**Portfolio Agent (Phase 0 일부 + AIMVP)**
- ✅ `portfolio/universe.yaml` — 자산 유니버스 정의
- ✅ `portfolio/backtest.py` — 공통 백테스트 엔진
- ✅ `portfolio/aimvp/` — AIMVP RiskOn (Faber TAA 3-Signal), 전체 백테스트 + 히트맵
  - `output/portfolio/aimvp/{date}.html`

**View Agent — Allocation View (Phase 1 partial)**
- ✅ `portfolio/view/scoring.py` — 자산별 모멘텀/트렌드/변동성/복합 점수
- ✅ `portfolio/view/allocation_view.py` — TAA 레짐 + 자산군별 OW/N/UW + 개별 자산 점수
  - `output/view/allocation/{date}.html`

**View Agent — Macro View (Phase 4 선행 구현)**

> ROADMAP의 Phase 4(FRED 데이터 통합)를 Phase 1보다 먼저 진행.
> 기존 allocation_view가 "Macro View"로 잘못 명명된 것을 발견하고 분리 결정.

- ✅ `portfolio/macro_indicators.yaml` — 21개 거시지표 정의
- ✅ `portfolio/collect_macro.py` — FRED + ECOS API 수집기
- ✅ `history/macro_indicators.csv` — 14,206행 (2020~2026.04)
  - 🇺🇸 US (14): GDP, CPI/Core CPI/PCE/Core PCE, 실업률, NFP, 연준금리, 10Y/2Y, Yield Curve, IG/HY Spread
  - 🇰🇷 KR (5): GDP QoQ/YoY, CPI YoY, 실업률, 기준금리
  - 🌍 Global (2): VIX, DXY
- ✅ `portfolio/view/macro_view.py` — 거시지표 HTML 뷰 (US/KR/Global 3-섹션)
  - `output/view/macro/{date}.html`

**미해결 이슈**:
- ❌ `KR_CORE_CPI_YOY` — ECOS item_code X0 확인 필요
- ❌ `KR_MFG_BSI` — ECOS 다층 item_code (C0000/AA) 구현 필요
- ❌ `US_ISM_MFG/SVC` — FRED series_id NAPM/NAPMNOI 오류 (대체 코드 필요)
- ❌ Snowflake `MKT200_PORTFOLIO_DAILY` DDL 미작성

### 다음 단계

- Phase 1 완성: Macro View에 Claude 해설 + HTML Allocation 탭 통합
- Phase 2: 모델 포트폴리오 + 리밸런싱 시그널

## Context

현재 market_summary는 56개 글로벌 지표를 매일 수집하고 Data 대시보드 + Claude가 쓴 Market Story를 산출하는 "모닝미팅 시황 보고서" 수준이다. 사용자는 이 위에 **증권사 애널리스트 업무(매크로 전략 + 섹터/테마 로테이션)를 자동화**하고, 이어서 **실제 자산배분 운용**까지 발전시키고자 한다.

핵심 결정:
- **MVP(8주)**: 매일 자산배분 view + 모델 포트폴리오 산출
- **독자**: PM/리서치 + PB/영업 (이중 페르소나)
- **데이터**: 무료 소스 최대 활용 (FRED, yfinance, investpy, FMP free, RSS, FDR)
- **그 다음**: 같은 시그널/PF 위에 paper-trading → 실제 자산배분 운용 레이어

기존 인프라 강점: [history/market_data.csv](../history/market_data.csv) 가 15개월(2025-01 ~ 2026-04) 일별 시계열을 보유 → 백테스트 가능. `_data.json` 이 카테고리별 dict로 이미 정규화돼 있어 자산배분 엔진 입력으로 그대로 사용 가능. [inject_stories.py](../inject_stories.py) 의 placeholder 치환 패턴은 새 'Allocation' 탭에 그대로 재사용 가능.

---

## Phased Roadmap

### Phase 0 — 토대 ✅ 완료 (일부)

- ✅ **`portfolio/universe.yaml`**: 투자 가능 ETF 매핑 (asset_class → ticker → indicator_code)
- ✅ **`portfolio/view/scoring.py`**: 자산별 시그널 계산 (모멘텀 12-1/6-1, 추세 MA200, 변동성, 복합 점수)
- ✅ **`portfolio/backtest.py`**: 미니 백테스트 엔진 (일일 비중 → NAV → CAGR/Sharpe/MDD)
- ❌ **Snowflake DDL**: `MKT200_PORTFOLIO_DAILY` 미작성 — `snowflake_loader.py` 패턴 재사용 예정

### Phase 1 — 매크로 자산배분 View (MVP 핵심 ①) — 진행 중

자산군별 OW/N/UW view + 거시지표 현황을 매일 자동 생성.

**1-A. Allocation View** (가격 기반 TAA)
- ✅ **`portfolio/view/allocation_view.py`**: 자산군별 OW/N/UW 뷰 (모멘텀 z-score, 추세 필터, 매크로 overlay)
  - `output/view/allocation/{date}.html` 독립 HTML 생성 완료

**1-B. Macro View** (거시지표 현황)
- ✅ **`portfolio/macro_indicators.yaml`** + **`portfolio/collect_macro.py`**: FRED + ECOS 수집 (21개 지표, `history/macro_indicators.csv`)
- ✅ **`portfolio/view/macro_view.py`**: 거시지표 HTML 뷰 (US/KR/Global 3-섹션)
  - `output/view/macro/{date}.html` 독립 HTML 생성 완료
- ❌ **미해결**: KR_CORE_CPI_YOY, KR_MFG_BSI, US_ISM_MFG/SVC series_id 수정 필요

**1-C. 통합 (미완)**
- ❌ **Claude 해설 생성**: Allocation + Macro 시그널 dict → 한국어 해설 1-2문단. `_data.json` + scoring 결과 컨텍스트로 주입
- ❌ **HTML 'Allocation' 탭**: `generate.py` 탭 추가 + `<!-- ALLOCATION_CONTENT_PLACEHOLDER -->` 섹션. `inject_stories.py`의 치환 함수를 `inject_block(html, placeholder, content)`으로 일반화하여 재사용

### Phase 2 — 모델 포트폴리오 + 리밸런싱 시그널 (Week 3-4, MVP 핵심 ②)
View → 실제 비중.

- **`portfolio/strategies/`** 디렉터리: 전략별 정의 파일.
  - `static_60_40.yaml` — 베이스라인
  - `risk_parity.yaml` — 변동성 기반
  - `taa_macro_tilt.yaml` — 베이스 60/40 ± 매크로 view tilt (±10%p 캡)
- **`portfolio/builder.py`** 신규: 전략 yaml + Phase 1 view → 일일 목표 비중 dict.
- **`portfolio/rebalance.py`** 신규: 직전 비중 vs 신규 목표 → 리밸런싱 신호. 트리거: 캘린더(월말) + threshold(자산별 절대편차 ≥3%).
- **`output/YYYY-MM/YYYY-MM-DD_portfolio.json`** 신규: 전략별 비중·시그널 저장. `_data.json` 옆에. gitignore.
- **Snowflake dual-write**: [generate.py:1510](../generate.py#L1510) `upsert_rows` 호출 직후에 portfolio 결과도 동일 패턴으로 적재.

### Phase 3 — 섹터/테마 로테이션 레이어 (Week 5)
주식 내부 한 단계 더.

- **유니버스 확장**: `universe.yaml` 에 SPDR 11개 섹터 ETF(XLK/XLF/XLE/XLV/XLI/XLY/XLP/XLU/XLB/XLRE/XLC) + 테마 묶음(반도체, AI, 신재생, 헬스케어 — 한국 ETF 코드 포함) 추가. 새 [`_emit_rows`](../generate.py#L344) 호출로 일별 수집에 편입.
- **`portfolio/sector_rotation.py`**: 동일한 모멘텀/추세/breadth 파이프라인을 섹터·테마에 적용. Phase 1 view 안의 `equity_dm` OW일 때만 활성.
- **Allocation 탭에 섹터 서브섹션 추가**: 동일 placeholder 패턴.

### Phase 4 — 무료 데이터 소스 통합 — 일부 선행 완료

매크로 view 정확도 + 이벤트 대응 능력.

- ✅ **`portfolio/collect_macro.py`**: FRED + ECOS API 수집. `history/macro_indicators.csv` 저장 (14,206행, 2020~)
- ✅ **`portfolio/macro_indicators.yaml`**: 21개 지표 정의 (US/KR/Global)
- ✅ **`portfolio/view/macro_view.py`**: 거시지표 HTML 뷰 (US/KR/Global 3-섹션)
- ❌ **미해결**: US_ISM series_id 오류, KR_CORE_CPI/KR_MFG_BSI 구현 필요
- ❌ **`fetchers/calendar.py`**: 경제 캘린더 (향후 7일 이벤트)
- ❌ **`fetchers/news.py`**: Reuters/Bloomberg/연합 RSS 헤드라인
- ❌ **`fetchers/earnings.py`**: 14개 stock earnings calendar
- ❌ **Allocation 탭 연결**: `macro_view.py` 룰셋이 FRED 거시지표를 명시적 입력으로 받도록

### Phase 5 — 백테스트 + 검증 + 주간/월간 통합 (Week 7)
신뢰성 레이어. PM이 보려면 백테스트 결과가 필수.

- **`portfolio/backtest.py` 강화**: Phase 0 미니 엔진 → 전략 yaml들에 대한 walk-forward. 결과: equity curve, drawdown, exposure, turnover, hit rate(view 적중률 — OW 자산이 N/UW 자산을 outperform 했는가).
- **백테스트 결과를 Allocation 탭 하단에 시각화**: 누적수익 라인, 월별 hit rate 표.
- **주간/월간 보고서 통합**: [generate_periodic.py:67](../generate_periodic.py#L67) `aggregate_period` 가 반환하는 dict 에 `allocation` 키 추가, [generate_periodic.py:173](../generate_periodic.py#L173) `generate_periodic_html` 에 섹션 렌더 추가. 주간/월간은 일간 view를 평균/말일 기준으로 요약하고 기간 백테스트 성과를 함께 표시.

### Phase 6 — 이중 페르소나 narrative (Week 8)
같은 시그널을 두 톤으로.

- **PM/리서치 톤**: 점수, z-score, 신뢰도, 리스크 시나리오, 백테스트 metric. 이미 Phase 1-5 에서 산출된 정량 정보 그대로.
- **PB/영업 톤**: 시장 내러티브 중심, 한국 증권사 모닝코멘트 톤. Claude 가 동일 시그널 dict 를 받아 다른 톤으로 재작성. `market-summary` 스킬에 `--audience pm|pb` 옵션 추가.
- **HTML 토글**: Allocation 탭 안에 PM ⇄ PB 토글 버튼. 두 narrative 모두 임베드.
- **8주 MVP 도달 지점**: 매일 매크로 view + 모델 PF + 섹터 view + 백테스트 카드 + 두 가지 톤의 해설.

---

## Phase 7+ — 자산배분 운용으로의 진화 (MVP 이후)

사용자가 명시적으로 언급한 "그 정보를 기반으로 자산배분 운용으로 이어진다" 단계.

1. **Paper trading**: 모델 PF 별로 가상 NAV 일일 추적. 포지션 변화 히스토리, 실현/미실현 손익. Snowflake `MKT201_PORTFOLIO_NAV` 신규.
2. **운용 의사결정 워크플로우**: 매일 아침 리밸런싱 시그널이 있으면 슬랙/이메일 알림. 사람이 승인 → 실행 기록.
3. **위험 모니터링**: VaR, vol target 위반, drawdown 임계, 단일자산 익스포저 한도. 위반 시 알림.
4. **이벤트 트리거 액션**: FOMC/CPI 직후 자동 view 재산출 → 의견 변경 시 PB 알림.
5. **(장기) Live 운용 어댑터**: 증권사 API(KIS, 키움 등) 연동. 단, MVP 아키텍처가 paper/live 구분만으로 갈리도록 처음부터 분리 인터페이스로 작성.

---

## 핵심 파일 구조

```
market_summary/
├── generate.py              # 기존 — 일부 수정 예정 (Allocation 탭 placeholder)
├── generate_periodic.py     # 기존 — allocation 섹션 추가 예정
├── inject_stories.py        # 기존 — inject_block(...) 일반화 예정
├── snowflake_loader.py      # 기존 — 테이블명 매개변수화 예정
├── history/
│   ├── market_data.csv           # ✅ 시장 가격 시계열 (56개 지표, 일별)
│   └── macro_indicators.csv      # ✅ 거시지표 시계열 (21개 지표, 14,206행)
├── portfolio/
│   ├── universe.yaml             # ✅
│   ├── backtest.py               # ✅
│   ├── macro_indicators.yaml     # ✅ 21개 지표 정의
│   ├── collect_macro.py          # ✅ FRED + ECOS 수집기
│   ├── aimvp/                    # ✅ AIMVP RiskOn 전략
│   │   ├── generate.py
│   │   ├── backfill.py
│   │   ├── signals.py
│   │   ├── model.py
│   │   ├── config.py
│   │   └── data_adapter.py
│   ├── view/
│   │   ├── allocation_view.py    # ✅ TAA 기반 자산배분 뷰
│   │   ├── macro_view.py         # ✅ 거시지표 뷰 (US/KR/Global)
│   │   └── scoring.py            # ✅ 자산 점수 계산
│   ├── builder.py                # ❌ Phase 2
│   ├── rebalance.py              # ❌ Phase 2
│   ├── sector_rotation.py        # ❌ Phase 3
│   └── strategies/               # ❌ Phase 2
│       ├── static_60_40.yaml
│       ├── risk_parity.yaml
│       └── taa_macro_tilt.yaml
├── fetchers/                     # ❌ Phase 4 (calendar/news/earnings)
├── output/
│   ├── index.html                # ✅ 메인 허브 (Summary 전용)
│   ├── summary/                  # ✅ Market Summary 일/주/월간
│   ├── portfolio/aimvp/          # ✅ AIMVP 백테스트 리포트
│   └── view/
│       ├── allocation/           # ✅ Allocation View
│       └── macro/                # ✅ Macro View
└── .claude/
    ├── commands/                 # ✅ /market-full, /market-data, /market-deploy
    └── skills/market-summary/    # ✅ Story 작성 규칙
```

---

## 검증 전략

각 Phase는 다음 방법으로 end-to-end 동작 확인:

- **Phase 0**: `python -m portfolio.scoring --date 2026-04-09` → 자산별 점수 표 출력. `python -m portfolio.backtest --strategy static_60_40` → 15개월 백테스트 metric 출력.
- **Phase 1**: `/market-data 2026-04-09` 실행 후 출력 HTML 의 Allocation 탭에 view 표 + 해설 렌더 확인. 기존 Data/Story 탭이 깨지지 않는지 확인.
- **Phase 2**: `_portfolio.json` 생성 + Snowflake `MKT200_PORTFOLIO_DAILY` 에 적재 확인 (`SELECT * FROM MKT200_PORTFOLIO_DAILY WHERE DATE='2026-04-09'`).
- **Phase 3**: 섹터 ETF 가 `history/market_data.csv` 에 추가됐는지 + Allocation 탭 섹터 서브섹션 렌더 확인.
- **Phase 4**: FRED 호출 결과가 `_data.json` 의 새 키에 저장 + 매크로 view 룰이 실제로 그 값을 사용하는지 (`scoring.py` 단위 테스트 추가).
- **Phase 5**: 백테스트 결과 카드 렌더 + `/market-full 2026-04-13` (월요일) 실행해 주간/월간 보고서 Allocation 섹션이 함께 갱신되는지.
- **Phase 6**: PM ⇄ PB 토글 동작 + 두 톤이 시그널은 동일하게 인용하는지 spot check.

각 Phase 종료 시 `history/market_data.csv` 와 기존 일일/주간/월간 보고서가 깨지지 않았다는 회귀 확인을 함께 한다.

---

## 우선순위 결정 가이드

8주가 부족하면 다음 우선순위로 컷:
1. **유지**: Phase 0, 1, 2 (MVP 핵심 — 매일 view + 모델 PF)
2. **유지**: Phase 5의 백테스트 (PM 신뢰 확보용)
3. **컷 후순위**: Phase 3 섹터 (주식 view 안에 OW 일 때만 실효)
4. **컷 후순위**: Phase 4 의 news/earnings (FRED 만 우선)
5. **컷 후순위**: Phase 6 의 PB 톤 (Phase 1 의 PM 톤만으로 시작)

Phase 7 운용 레이어는 Phase 1-5 가 안정화된 후에만 시작.