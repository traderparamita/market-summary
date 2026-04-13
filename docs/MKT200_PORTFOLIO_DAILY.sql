-- MKT200_PORTFOLIO_DAILY: 전략별 일일 포트폴리오 비중·NAV·시그널
-- FDE_DB.PUBLIC (MKT100_MARKET_DAILY 와 동일 스키마에 공존)
-- snowflake_loader.py 의 upsert_rows 패턴으로 적재

CREATE TABLE IF NOT EXISTS FDE_DB.PUBLIC.MKT200_PORTFOLIO_DAILY (
    "일자"       DATE          NOT NULL,
    "전략코드"   VARCHAR(30)   NOT NULL,   -- static_60_40, risk_parity, taa_macro_tilt
    "자산코드"   VARCHAR(30)   NOT NULL,   -- ETF ticker: SPY, AGG, TLT, ...
    "지표코드"   VARCHAR(30),              -- FK → MKT000_MARKET_INDICATOR.지표코드
    "목표비중"   NUMBER(8,4),              -- target weight (0.0000 ~ 1.0000)
    "실행비중"   NUMBER(8,4),              -- actual weight after drift
    "시그널점수" NUMBER(8,3),              -- composite score from scoring.py
    "NAV"        NUMBER(18,6),             -- cumulative NAV (base=1.0)
    PRIMARY KEY ("일자", "전략코드", "자산코드")
);

COMMENT ON TABLE FDE_DB.PUBLIC.MKT200_PORTFOLIO_DAILY IS
    'Phase 0: 자산배분 전략별 일일 목표비중·NAV. market_summary portfolio/ 엔진 산출.';
