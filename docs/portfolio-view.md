# Portfolio Agent & View Agent

## 1. Portfolio Agent (aimvp)

AIMVP RiskOn 전략. Faber TAA 3-Signal Model.

- Trend / Momentum / VIX 기반 3-신호 체계
- 동적 자산배분 (Stock/Bond/Cash)
- 월간 수익률 히트맵 (vs 75/25 초과수익)
- 누적 수익률 + 드로다운 차트
- 성과 비교 (Dynamic vs 75/25 vs 60/40 vs ACWI vs AGG)

```bash
python -m portfolio.aimvp.generate --date 2026-04-09        # 백테스트 리포트
python -m portfolio.aimvp.backfill --snowflake               # 장기 히스토리 백필 (2010~)
```

출력: `output/portfolio/aimvp/{date}.html`

## 2. View Agent (9개 뷰)

현재 시점 분석 뷰. 백테스트 없음.

### Phase 1 — 진단

| 뷰 | 모듈 | 설명 |
|----|------|------|
| Price | `portfolio.view.price_view` | Market Pulse (VIX/Yield Curve/Breadth/DXY/Sentiment), 자산군별 OW/N/UW, 레짐 감지 |
| Macro | `portfolio.view.macro_view` | US/KR 거시지표, 2x2 Regime 헤더, FED Implied Rate, Liquidity |
| Correlation | `portfolio.view.correlation_view` | Core 8 자산 30/90일 롤링 상관관계 히트맵 |
| Regime | `portfolio.view.regime_view` | 3개 뷰 통합, 규칙 기반 한국어 투자 해설 자동 생성 |

### Phase 2 — 의사결정

| 뷰 | 모듈 | 설명 |
|----|------|------|
| Country | `portfolio.view.country_view` | 8개국 OW/N/UW (모멘텀+FX+매크로+KRW 환헤지) |
| Sector | `portfolio.view.sector_view` | US 11섹터 + KR 4섹터 로테이션 |
| Bond | `portfolio.view.bond_view` | 채권 커브·크레딧·ALM 포지셔닝 |
| Style | `portfolio.view.style_view` | Growth/Value/Quality/Momentum/LowVol 팩터 |
| Allocation | `portfolio.view.allocation_view` | 변액보험 펀드 배분안 (K-ICS 체크, KR+US 2-패널) |

```bash
python -m portfolio.view.<name>_view --date YYYY-MM-DD --html
```

출력: `output/view/{name}/{date}.html`

### 디자인 시스템

`portfolio/view/_shared.py` — Mirae Asset 브랜드:
- `BASE_CSS`, `NAV_CSS`, `nav_html()`, `html_page()` 제공
- Spoqa Han Sans Neo 서체, #F58220 (Orange), #043B72 (Navy)
- NAV CSS 주입: P1/country/sector 뷰는 자체 `<head>` 에 `{NAV_CSS}` 주입. P2 bond/style/allocation은 `html_page()` → `BASE_CSS` 로 자동 포함

## 3. Sector Rotation Strategy (KR vs US)

멀티에이전트 신호로 한국/미국 시장 중 다음 달 베팅 결정.

- Momentum Agent (40%): 11개 KR+US 섹터 ETF 1M/3M/6M 평균 수익률 비교
- Breadth Agent (30%): MA200 상회 섹터 비율 (KR vs US)
- Relative Strength Agent (30%): KOSPI vs S&P500 1M/3M/6M 상대 수익률
- 월간 리밸런싱, 임계값 ±0.08

```bash
python -m portfolio.strategy.sector_rotation --date 2026-04-20
```

출력: `output/portfolio/strategy/{date}.html` + `{date}_signals.csv`

## 데이터 소스

- Portfolio Agent / Price View / Sector Rotation: **Snowflake MKT100** 단일 정본 (via `portfolio.market_source`). 시뮬레이션 모드에서만 CSV
- Macro View: `history/macro_indicators.csv` (FRED + ECOS 수집)
