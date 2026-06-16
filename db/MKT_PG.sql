-- ============================================================
-- 시장·매크로 데이터 스키마 (PostgreSQL / RDS)
-- Database: anthillia   Schema: public
--
-- 네이밍 규칙 (lowercase, MKT prefix):
--   mkt000_*  : 시장 지표 마스터
--   mkt001_*  : 매크로 지표 마스터
--   mkt100_*  : 시장 데이터 일간 시계열
--   mkt200_*  : 매크로 데이터 시계열 (D/M/Q)
--
-- Snowflake 버전(MKT.sql)과의 차이:
--   - 테이블명/컬럼명: 소문자 snake_case + 영어
--   - NUMBER → NUMERIC, TIMESTAMP_NTZ → TIMESTAMP
--   - CLUSTER BY → CREATE INDEX
--   - CURRENT_TIMESTAMP() → CURRENT_TIMESTAMP
-- ============================================================


-- ============================================================
-- 0. 기존 오브젝트 제거
-- ============================================================
DROP VIEW  IF EXISTS v_macro_latest;
DROP VIEW  IF EXISTS v_market_monitoring;
DROP VIEW  IF EXISTS v_market_trend;
DROP TABLE IF EXISTS mkt200_macro_daily;
DROP TABLE IF EXISTS mkt001_macro_indicator;
DROP TABLE IF EXISTS mkt100_market_daily;
DROP TABLE IF EXISTS mkt000_market_indicator;

-- RDS 초기 버전 구형 테이블
DROP TABLE IF EXISTS macro_daily;
DROP TABLE IF EXISTS market_daily;


-- ============================================================
-- 1. mkt000_market_indicator — 시장 지표 마스터
--    PK: indicator_code
--    UNIQUE: (category, ticker)
-- ============================================================
CREATE TABLE mkt000_market_indicator (
    indicator_code   VARCHAR(50)   NOT NULL,
    category         VARCHAR(20)   NOT NULL,
    ticker           VARCHAR(50)   NOT NULL,
    name_kr          VARCHAR(200),
    name_en          VARCHAR(200),
    sub_category     VARCHAR(50),
    unit             VARCHAR(20),
    change_unit      VARCHAR(20),              -- pct / bp
    source           VARCHAR(30),
    source_ticker    VARCHAR(100),
    source_fallback  VARCHAR(200),
    note             VARCHAR(500),
    sort_order       SMALLINT,
    is_active        BOOLEAN       DEFAULT TRUE,
    created_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_mkt000 PRIMARY KEY (indicator_code),
    CONSTRAINT uq_mkt000 UNIQUE (category, ticker)
);


-- ============================================================
-- 2. mkt100_market_daily — 시장 데이터 일간 시계열
--    PK: (date, indicator_code)
-- ============================================================
CREATE TABLE mkt100_market_daily (
    date             DATE          NOT NULL,
    indicator_code   VARCHAR(50)   NOT NULL,
    category         VARCHAR(20),
    ticker           VARCHAR(50),
    close            NUMERIC(18,3),
    open             NUMERIC(18,3),
    high             NUMERIC(18,3),
    low              NUMERIC(18,3),
    volume           BIGINT,
    source           VARCHAR(30),
    collected_at     TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_mkt100 PRIMARY KEY (date, indicator_code)
);

CREATE INDEX idx_mkt100_date      ON mkt100_market_daily (date DESC);
CREATE INDEX idx_mkt100_indicator ON mkt100_market_daily (indicator_code);


-- ============================================================
-- 3. mkt001_macro_indicator — 매크로 지표 마스터
--    PK: indicator_code
-- ============================================================
CREATE TABLE mkt001_macro_indicator (
    indicator_code   VARCHAR(50)   NOT NULL,
    name_kr          VARCHAR(200),
    name_en          VARCHAR(200),
    category         VARCHAR(50),
    region           VARCHAR(10),
    unit             VARCHAR(20),
    period           CHAR(1),                  -- D / M / Q
    source           VARCHAR(20),
    source_series    VARCHAR(50),
    transform        VARCHAR(30),              -- value / pct_change_yoy / diff
    note             VARCHAR(500),
    is_active        BOOLEAN       DEFAULT TRUE,
    created_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_mkt001 PRIMARY KEY (indicator_code)
);


-- ============================================================
-- 4. mkt200_macro_daily — 거시경제 지표 시계열
--    PK: (date, indicator_code)
-- ============================================================
CREATE TABLE mkt200_macro_daily (
    date             DATE          NOT NULL,
    indicator_code   VARCHAR(50)   NOT NULL,
    category         VARCHAR(50),
    region           VARCHAR(10),
    value            NUMERIC(18,4),
    unit             VARCHAR(20),
    period           CHAR(1),                  -- D / M / Q
    source           VARCHAR(20),
    source_series    VARCHAR(50),
    collected_at     TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_mkt200 PRIMARY KEY (date, indicator_code)
);

CREATE INDEX idx_mkt200_date      ON mkt200_macro_daily (date DESC);
CREATE INDEX idx_mkt200_indicator ON mkt200_macro_daily (indicator_code);


-- ============================================================
-- 5. Views
-- ============================================================

-- v_market_monitoring: Bloomberg 일일 모니터링 시트 재현
CREATE OR REPLACE VIEW v_market_monitoring AS
WITH latest AS (
    SELECT MAX(date) AS latest_date FROM mkt100_market_daily
),
ref_dates AS (
    SELECT
        l.latest_date,
        (SELECT MAX(date) FROM mkt100_market_daily WHERE date <  l.latest_date)                             AS prev_day,
        (SELECT MAX(date) FROM mkt100_market_daily WHERE date <= l.latest_date - INTERVAL '7 days')         AS prev_week,
        (SELECT MAX(date) FROM mkt100_market_daily WHERE date <= l.latest_date - INTERVAL '1 month')        AS prev_month,
        (SELECT MAX(date) FROM mkt100_market_daily WHERE date <= l.latest_date - INTERVAL '1 year')         AS prev_year
    FROM latest l
)
SELECT
    d.indicator_code,
    d.category,
    d.sub_category,
    d.ticker,
    d.name_kr,
    d.name_en,
    d.unit,
    m.date,
    m.close,
    CASE d.change_unit
        WHEN 'pct' THEN ROUND((m.close / NULLIF(pd.close, 0) - 1) * 100, 2)
        WHEN 'bp'  THEN ROUND((m.close - pd.close) * 100, 1)
    END AS chg_1d,
    CASE d.change_unit
        WHEN 'pct' THEN ROUND((m.close / NULLIF(pw.close, 0) - 1) * 100, 2)
        WHEN 'bp'  THEN ROUND((m.close - pw.close) * 100, 1)
    END AS chg_1w,
    CASE d.change_unit
        WHEN 'pct' THEN ROUND((m.close / NULLIF(pm.close, 0) - 1) * 100, 2)
        WHEN 'bp'  THEN ROUND((m.close - pm.close) * 100, 1)
    END AS chg_1m,
    CASE d.change_unit
        WHEN 'pct' THEN ROUND((m.close / NULLIF(py.close, 0) - 1) * 100, 2)
        WHEN 'bp'  THEN ROUND((m.close - py.close) * 100, 1)
    END AS chg_1y,
    d.sort_order
FROM mkt100_market_daily m
JOIN  mkt000_market_indicator d  ON m.indicator_code = d.indicator_code
CROSS JOIN ref_dates r
LEFT JOIN mkt100_market_daily pd ON pd.indicator_code = m.indicator_code AND pd.date = r.prev_day
LEFT JOIN mkt100_market_daily pw ON pw.indicator_code = m.indicator_code AND pw.date = r.prev_week
LEFT JOIN mkt100_market_daily pm ON pm.indicator_code = m.indicator_code AND pm.date = r.prev_month
LEFT JOIN mkt100_market_daily py ON py.indicator_code = m.indicator_code AND py.date = r.prev_year
WHERE m.date = r.latest_date
  AND d.is_active = TRUE
ORDER BY d.sort_order;


-- v_market_trend: 개별 지표 시계열 조회용 (대시보드 차트)
CREATE OR REPLACE VIEW v_market_trend AS
SELECT
    m.date,
    m.indicator_code,
    d.category,
    d.sub_category,
    d.ticker,
    d.name_kr,
    d.name_en,
    d.unit,
    m.close,
    m.open,
    m.high,
    m.low,
    m.volume
FROM mkt100_market_daily m
JOIN mkt000_market_indicator d ON m.indicator_code = d.indicator_code
WHERE d.is_active = TRUE;


-- v_macro_latest: 매크로 지표 최신값 모니터링
CREATE OR REPLACE VIEW v_macro_latest AS
WITH ranked AS (
    SELECT
        indicator_code, date, value, unit, period, source,
        ROW_NUMBER() OVER (PARTITION BY indicator_code ORDER BY date DESC) AS rn
    FROM mkt200_macro_daily
)
SELECT
    i.indicator_code,
    i.category,
    i.region,
    i.name_kr,
    i.name_en,
    r.date,
    r.value,
    i.unit,
    i.period,
    i.source
FROM ranked r
JOIN mkt001_macro_indicator i ON r.indicator_code = i.indicator_code
WHERE r.rn = 1
  AND i.is_active = TRUE
ORDER BY i.region, i.category, i.indicator_code;


-- ============================================================
-- 6. mkt000_market_indicator 시드 데이터
-- ============================================================
INSERT INTO mkt000_market_indicator (
    indicator_code, category, ticker, name_kr, name_en,
    sub_category, unit, change_unit,
    source, source_ticker, source_fallback, note,
    sort_order, is_active
) VALUES
    -- ── EQUITY (18) ──
    ('EQ_KOSPI',       'EQUITY', 'KOSPI',      'KOSPI',         'KOSPI Index',                  'Korea',  'pt', 'pct', 'yfinance', '^KS11',      'FDR:KS11',               NULL,                                  1,  TRUE),
    ('EQ_KOSDAQ',      'EQUITY', 'KOSDAQ',     'KOSDAQ',        'KOSDAQ Index',                 'Korea',  'pt', 'pct', 'yfinance', '^KQ11',      'FDR:KQ11',               NULL,                                  2,  TRUE),
    ('EQ_SP500',       'EQUITY', 'S&P500',     'S&P500',        'S&P 500 Index',                'US',     'pt', 'pct', 'yfinance', '^GSPC',      NULL,                     NULL,                                  3,  TRUE),
    ('EQ_NASDAQ',      'EQUITY', 'NASDAQ',     '나스닥종합',    'NASDAQ Composite',             'US',     'pt', 'pct', 'yfinance', '^IXIC',      NULL,                     NULL,                                  4,  TRUE),
    ('EQ_RUSSELL2000', 'EQUITY', 'Russell2K',  '러셀2000',      'Russell 2000 Index',           'US',     'pt', 'pct', 'yfinance', '^RUT',       NULL,                     NULL,                                  5,  TRUE),
    ('EQ_EUROSTOXX50', 'EQUITY', 'STOXX50',    'EURO STOXX50',  'EURO STOXX 50 Index',          'Europe', 'pt', 'pct', 'yfinance', '^STOXX50E',  'investiny:175',          NULL,                                  6,  TRUE),
    ('EQ_DAX',         'EQUITY', 'DAX',        '독일 DAX',      'DAX Index',                    'Europe', 'pt', 'pct', 'yfinance', '^GDAXI',     'investiny:172',          NULL,                                  7,  TRUE),
    ('EQ_CAC40',       'EQUITY', 'CAC40',      '프랑스 CAC40', 'CAC 40 Index',                  'Europe', 'pt', 'pct', 'yfinance', '^FCHI',      'investiny:167',          NULL,                                  8,  TRUE),
    ('EQ_FTSE100',     'EQUITY', 'FTSE100',    '영국 FTSE100', 'FTSE 100 Index',                'Europe', 'pt', 'pct', 'yfinance', '^FTSE',      'investiny:27',           NULL,                                  9,  TRUE),
    ('EQ_NIKKEI225',   'EQUITY', 'Nikkei225',  '니케이225',     'Nikkei 225 Index',             'Japan',  'pt', 'pct', 'yfinance', '^N225',      'FDR:N225,investiny:178', NULL,                                  10, TRUE),
    ('EQ_SHANGHAI',    'EQUITY', 'Shanghai',   '상해종합',      'SSE Composite Index',          'China',  'pt', 'pct', 'yfinance', '000001.SS',  'FDR:SSEC,investiny:40820', NULL,                                11, TRUE),
    ('EQ_HSI',         'EQUITY', 'HSI',        '항셍',          'Hang Seng Index',              'China',  'pt', 'pct', 'yfinance', '^HSI',       'FDR:HSI,investiny:179',  NULL,                                  12, TRUE),
    ('EQ_NIFTY50',     'EQUITY', 'NIFTY50',    'NIFTY 50',      'NIFTY 50 Index',               'India',  'pt', 'pct', 'yfinance', '^NSEI',      'investiny:17940',        NULL,                                  13, TRUE),
    ('EQ_MSCI_WORLD',  'EQUITY', 'MSCI World', 'MSCI World',    'MSCI World Index (ETF proxy)', 'MSCI',   'pt', 'pct', 'yfinance', 'URTH',       NULL,                     'iShares MSCI World ETF proxy',        14, TRUE),
    ('EQ_MSCI_ACWI',   'EQUITY', 'MSCI ACWI',  'MSCI ACWI',    'MSCI ACWI Index (ETF proxy)',   'MSCI',   'pt', 'pct', 'yfinance', 'ACWI',       NULL,                     'iShares MSCI ACWI ETF',               15, TRUE),
    ('EQ_MSCI_LATAM',  'EQUITY', 'MSCI LATAM', 'MSCI LATAM',   'MSCI LatAm Index (ETF proxy)',  'MSCI',   'pt', 'pct', 'yfinance', 'ILF',        NULL,                     'iShares Latin America 40 ETF',        16, TRUE),
    ('EQ_MSCI_EMEA',   'EQUITY', 'MSCI EMEA',  'MSCI EMEA',    'MSCI EMEA Index (ETF proxy)',   'MSCI',   'pt', 'pct', 'yfinance', 'EZA',        NULL,                     'iShares South Africa ETF (EM proxy)', 17, TRUE),
    ('EQ_TWSE',        'EQUITY', 'TAIEX',      '대만 가권',     'Taiwan Weighted Index',        'Taiwan', 'pt', 'pct', 'yfinance', '^TWII',      NULL,                     NULL,                                  18, TRUE),

    -- ── BOND (16) ──
    ('BD_US_2Y',    'BOND', 'US 2Y',     '미국 2Y',      'US Treasury 2Y',                     'US',    'pct', 'bp',  'yfinance', '^IRX',  NULL,        '13W T-Bill proxy',           30, TRUE),
    ('BD_US_10Y',   'BOND', 'US 10Y',    '미국 10Y',     'US Treasury 10Y',                    'US',    'pct', 'bp',  'yfinance', '^TNX',  NULL,        NULL,                         31, TRUE),
    ('BD_US_30Y',   'BOND', 'US 30Y',    '미국 30Y',     'US Treasury 30Y',                    'US',    'pct', 'bp',  'yfinance', '^TYX',  NULL,        NULL,                         32, TRUE),
    ('BD_TLT',      'BOND', 'TLT',       'TLT',          'iShares 20+Y Treasury ETF',          'US',    'pt',  'pct', 'yfinance', 'TLT',   NULL,        'Long Treasury ETF',          33, TRUE),
    ('BD_HYG',      'BOND', 'HYG',       'HYG',          'iShares iBoxx HY ETF',               'US',    'pt',  'pct', 'yfinance', 'HYG',   NULL,        'High Yield ETF',             34, TRUE),
    ('BD_LQD',      'BOND', 'LQD',       'LQD',          'iShares iBoxx IG ETF',               'US',    'pt',  'pct', 'yfinance', 'LQD',   NULL,        'Investment Grade ETF',       35, TRUE),
    ('BD_EMB',      'BOND', 'EMB',       'EMB',          'iShares JPM EM Bond ETF',            'EM',    'pt',  'pct', 'yfinance', 'EMB',   NULL,        'EM Bond ETF',                36, TRUE),
    ('BD_AGG',      'BOND', 'AGG',       'AGG',          'iShares Core US Aggregate Bond ETF', 'US',    'pt',  'pct', 'yfinance', 'AGG',   NULL,        'US Aggregate Bond ETF',      37, TRUE),
    ('BD_US_1_3Y',  'BOND', 'SHY',       'SHY',          'iShares 1-3Y Treasury ETF',          'US',    'pt',  'pct', 'yfinance', 'SHY',   NULL,        '1-3Y Treasury ETF',          38, TRUE),
    ('BD_US_3_7Y',  'BOND', 'IEI',       'IEI',          'iShares 3-7Y Treasury ETF',          'US',    'pt',  'pct', 'yfinance', 'IEI',   NULL,        '3-7Y Treasury ETF',          39, TRUE),
    ('BD_KR_CD91D', 'BOND', 'KR CD 91D','한국 CD 91일', 'Korea CD 91D Rate',                   'Korea', 'pct', 'bp',  'ECOS', '817Y002', '010502000', 'ECOS stat=817Y002, item=010502000', 40, TRUE),
    ('BD_KR_3Y',    'BOND', 'KR 3Y',    '한국 3Y',      'Korea Treasury 3Y',                   'Korea', 'pct', 'bp',  'ECOS', '817Y002', '010200000', 'ECOS stat=817Y002, item=010200000', 41, TRUE),
    ('BD_KR_10Y',   'BOND', 'KR 10Y',   '한국 10Y',     'Korea Treasury 10Y',                  'Korea', 'pct', 'bp',  'ECOS', '817Y002', '010200001', 'ECOS stat=817Y002, item=010200001', 42, TRUE),
    ('BD_US_TIPS',  'BOND', 'TIP',       'TIP',          'iShares TIPS Bond ETF',              'US',    'pt',  'pct', 'yfinance', 'TIP',   NULL,        'TIPS ETF',                   43, TRUE),
    ('BD_KR_5Y',    'BOND', 'KR 5Y',    '한국 5Y',      'Korea Treasury 5Y',                   'Korea', 'pct', 'bp',  'ECOS', '817Y002', '010200002', NULL,                          44, TRUE),
    ('BD_KR_30Y',   'BOND', 'KR 30Y',   '한국 30Y',     'Korea Treasury 30Y',                  'Korea', 'pct', 'bp',  'ECOS', '817Y002', '010200003', NULL,                          45, TRUE),

    -- ── FX (8) ──
    ('FX_DXY',    'FX', 'DXY',     '달러인덱스', 'US Dollar Index (DXY)',  'Index', 'pt',  'pct', 'investiny', 'DX-Y.NYB', 'FDR,yfinance', NULL, 50, TRUE),
    ('FX_USDKRW', 'FX', 'USD/KRW', 'USD/KRW',   'USD/KRW Exchange Rate',  'KRW',   'KRW', 'pct', 'investiny', 'KRW=X',    'FDR:USD/KRW',  NULL, 51, TRUE),
    ('FX_EURUSD', 'FX', 'EUR/USD', 'EUR/USD',   'EUR/USD Exchange Rate',  'Major', 'USD', 'pct', 'investiny', 'EURUSD=X', 'FDR:EUR/USD',  NULL, 52, TRUE),
    ('FX_USDJPY', 'FX', 'USD/JPY', 'USD/JPY',   'USD/JPY Exchange Rate',  'Major', 'JPY', 'pct', 'investiny', 'JPY=X',    'FDR:USD/JPY',  NULL, 53, TRUE),
    ('FX_USDCNY', 'FX', 'USD/CNY', 'USD/CNY',   'USD/CNY Exchange Rate',  'Major', 'CNY', 'pct', 'investiny', 'CNY=X',    'FDR:USD/CNY',  NULL, 54, TRUE),
    ('FX_AUDUSD', 'FX', 'AUD/USD', 'AUD/USD',   'AUD/USD Exchange Rate',  'Major', 'USD', 'pct', 'investiny', 'AUDUSD=X', 'FDR',          NULL, 55, TRUE),
    ('FX_GBPUSD', 'FX', 'GBP/USD', 'GBP/USD',   'GBP/USD Exchange Rate',  'Major', 'USD', 'pct', 'investiny', 'GBPUSD=X', 'FDR',          NULL, 56, TRUE),
    ('FX_USDINR', 'FX', 'USD/INR', 'USD/INR',   'USD/INR Exchange Rate',  'EM',    'INR', 'pct', 'yfinance',  'USDINR=X', NULL,           NULL, 57, TRUE),

    -- ── COMMODITY (6) ──
    ('CM_WTI',    'COMMODITY', 'WTI',     'NYMEX WTI',  'WTI Crude Oil Futures',    'Energy', 'USD', 'pct', 'investiny', 'CL=F', 'yfinance', NULL, 70, TRUE),
    ('CM_BRENT',  'COMMODITY', 'Brent',   'ICE Brent',  'Brent Crude Oil Futures',  'Energy', 'USD', 'pct', 'investiny', 'BZ=F', 'yfinance', NULL, 71, TRUE),
    ('CM_GOLD',   'COMMODITY', 'Gold',    '금 선물',    'Gold Futures',             'Metal',  'USD', 'pct', 'investiny', 'GC=F', 'yfinance', NULL, 72, TRUE),
    ('CM_SILVER', 'COMMODITY', 'Silver',  '은 선물',    'Silver Futures',           'Metal',  'USD', 'pct', 'investiny', 'SI=F', 'yfinance', NULL, 73, TRUE),
    ('CM_COPPER', 'COMMODITY', 'Copper',  '구리 선물',  'Copper Futures (COMEX)',   'Metal',  'USD', 'pct', 'investiny', 'HG=F', 'yfinance', NULL, 74, TRUE),
    ('CM_NATGAS', 'COMMODITY', 'Nat Gas', '천연가스',   'Natural Gas Futures (HH)', 'Energy', 'USD', 'pct', 'investiny', 'NG=F', 'yfinance', NULL, 75, TRUE),

    -- ── RISK (4) ──
    ('RK_VIX',    'RISK', 'VIX',       'VIX',       'CBOE VIX Index',             'US', 'pt', 'pct', 'yfinance', '^VIX',         NULL, NULL, 90, TRUE),
    ('RK_VIX3M',  'RISK', 'VIX3M',     'VIX3M',     'CBOE 3-Month VIX Index',     'US', 'pt', 'pct', 'yfinance', '^VIX3M',       NULL, NULL, 91, TRUE),
    ('BD_SPD_HY', 'RISK', 'HY Spread', 'HY Spread', 'ICE BofA US High Yield OAS', 'US', 'bp', 'bp',  'FRED',     'BAMLH0A0HYM2', NULL, NULL, 92, TRUE),
    ('BD_SPD_IG', 'RISK', 'IG Spread', 'IG Spread', 'ICE BofA US Corporate OAS',  'US', 'bp', 'bp',  'FRED',     'BAMLC0A0CM',   NULL, NULL, 93, TRUE),

    -- ── SECTOR_US (11) ──
    ('SC_US_TECH',    'SECTOR_US', 'SPDR Tech',      'SPDR 기술',        'SPDR Technology Select Sector ETF',       'US', 'pt', 'pct', 'yfinance', 'XLK',  NULL, NULL, 200, TRUE),
    ('SC_US_FIN',     'SECTOR_US', 'SPDR Fin',       'SPDR 금융',        'SPDR Financial Select Sector ETF',        'US', 'pt', 'pct', 'yfinance', 'XLF',  NULL, NULL, 201, TRUE),
    ('SC_US_ENERGY',  'SECTOR_US', 'SPDR Energy',    'SPDR 에너지',      'SPDR Energy Select Sector ETF',           'US', 'pt', 'pct', 'yfinance', 'XLE',  NULL, NULL, 202, TRUE),
    ('SC_US_HEALTH',  'SECTOR_US', 'SPDR Health',    'SPDR 헬스케어',    'SPDR Health Care Select Sector ETF',      'US', 'pt', 'pct', 'yfinance', 'XLV',  NULL, NULL, 203, TRUE),
    ('SC_US_INDU',    'SECTOR_US', 'SPDR Indu',      'SPDR 산업재',      'SPDR Industrial Select Sector ETF',       'US', 'pt', 'pct', 'yfinance', 'XLI',  NULL, NULL, 204, TRUE),
    ('SC_US_DISCR',   'SECTOR_US', 'SPDR ConsDiscr', 'SPDR 임의소비재',  'SPDR Consumer Discretionary Select ETF',  'US', 'pt', 'pct', 'yfinance', 'XLY',  NULL, NULL, 205, TRUE),
    ('SC_US_STAPLES', 'SECTOR_US', 'SPDR ConsStap',  'SPDR 필수소비재',  'SPDR Consumer Staples Select Sector ETF', 'US', 'pt', 'pct', 'yfinance', 'XLP',  NULL, NULL, 206, TRUE),
    ('SC_US_UTIL',    'SECTOR_US', 'SPDR Util',      'SPDR 유틸리티',    'SPDR Utilities Select Sector ETF',        'US', 'pt', 'pct', 'yfinance', 'XLU',  NULL, NULL, 207, TRUE),
    ('SC_US_MATL',    'SECTOR_US', 'SPDR Matl',      'SPDR 소재',        'SPDR Materials Select Sector ETF',        'US', 'pt', 'pct', 'yfinance', 'XLB',  NULL, NULL, 208, TRUE),
    ('SC_US_REIT',    'SECTOR_US', 'SPDR REIT',      'SPDR 리츠',        'SPDR Real Estate Select Sector ETF',      'US', 'pt', 'pct', 'yfinance', 'XLRE', NULL, NULL, 209, TRUE),
    ('SC_US_COMM',    'SECTOR_US', 'SPDR Comm',      'SPDR 커뮤니케이션','SPDR Communication Services Select ETF',  'US', 'pt', 'pct', 'yfinance', 'XLC',  NULL, NULL, 210, TRUE),

    -- ── STYLE_US (5) ──
    ('FA_US_GROWTH',   'STYLE_US', 'iShares Growth',   '성장',    'iShares S&P 500 Growth ETF',       'US', 'pt', 'pct', 'yfinance', 'IVW',  NULL, NULL, 220, TRUE),
    ('FA_US_VALUE',    'STYLE_US', 'iShares Value',    '가치',    'iShares S&P 500 Value ETF',        'US', 'pt', 'pct', 'yfinance', 'IVE',  NULL, NULL, 221, TRUE),
    ('FA_US_QUALITY',  'STYLE_US', 'iShares Quality',  '퀄리티',  'iShares MSCI USA Quality Factor',  'US', 'pt', 'pct', 'yfinance', 'QUAL', NULL, NULL, 222, TRUE),
    ('FA_US_MOMENTUM', 'STYLE_US', 'iShares Momentum', '모멘텀',  'iShares MSCI USA Momentum Factor', 'US', 'pt', 'pct', 'yfinance', 'MTUM', NULL, NULL, 223, TRUE),
    ('FA_US_LOWVOL',   'STYLE_US', 'iShares LowVol',   '저변동성','iShares MSCI USA Min Vol Factor',  'US', 'pt', 'pct', 'yfinance', 'USMV', NULL, NULL, 224, TRUE),

    -- ── SECTOR_KR_INDEX (11) ──
    ('IX_KR_IT',      'SECTOR_KR_INDEX', 'KOSPI200 IT',      'KOSPI200 정보기술',     'KOSPI200 Information Technology Index', 'Korea', 'pt', 'pct', 'pykrx', '1155', NULL, NULL, 250, TRUE),
    ('IX_KR_COMM',    'SECTOR_KR_INDEX', 'KOSPI200 Comm',    'KOSPI200 커뮤니케이션', 'KOSPI200 Communication Services Index', 'Korea', 'pt', 'pct', 'pykrx', '1150', NULL, NULL, 251, TRUE),
    ('IX_KR_FIN',     'SECTOR_KR_INDEX', 'KOSPI200 Fin',     'KOSPI200 금융',         'KOSPI200 Financials Index',             'Korea', 'pt', 'pct', 'pykrx', '1156', NULL, NULL, 252, TRUE),
    ('IX_KR_ENERGY',  'SECTOR_KR_INDEX', 'KOSPI200 Energy',  'KOSPI200 에너지/화학',  'KOSPI200 Energy/Chemicals Index',       'Korea', 'pt', 'pct', 'pykrx', '1154', NULL, NULL, 253, TRUE),
    ('IX_KR_HEALTH',  'SECTOR_KR_INDEX', 'KOSPI200 Health',  'KOSPI200 헬스케어',     'KOSPI200 Health Care Index',            'Korea', 'pt', 'pct', 'pykrx', '1160', NULL, NULL, 254, TRUE),
    ('IX_KR_INDU',    'SECTOR_KR_INDEX', 'KOSPI200 Indu',    'KOSPI200 산업재',       'KOSPI200 Industrials Index',            'Korea', 'pt', 'pct', 'pykrx', '1159', NULL, NULL, 255, TRUE),
    ('IX_KR_HEAVY',   'SECTOR_KR_INDEX', 'KOSPI200 Heavy',   'KOSPI200 중공업',       'KOSPI200 Heavy Industry Index',         'Korea', 'pt', 'pct', 'pykrx', '1152', NULL, NULL, 256, TRUE),
    ('IX_KR_DISCR',   'SECTOR_KR_INDEX', 'KOSPI200 Discr',   'KOSPI200 경기소비재',   'KOSPI200 Consumer Discretionary Index', 'Korea', 'pt', 'pct', 'pykrx', '1158', NULL, NULL, 257, TRUE),
    ('IX_KR_STAPLES', 'SECTOR_KR_INDEX', 'KOSPI200 Staples', 'KOSPI200 생활소비재',   'KOSPI200 Consumer Staples Index',       'Korea', 'pt', 'pct', 'pykrx', '1157', NULL, NULL, 258, TRUE),
    ('IX_KR_STEEL',   'SECTOR_KR_INDEX', 'KOSPI200 Steel',   'KOSPI200 철강/소재',    'KOSPI200 Steel/Materials Index',        'Korea', 'pt', 'pct', 'pykrx', '1153', NULL, NULL, 259, TRUE),
    ('IX_KR_CONSTR',  'SECTOR_KR_INDEX', 'KOSPI200 Constr',  'KOSPI200 건설',         'KOSPI200 Construction Index',           'Korea', 'pt', 'pct', 'pykrx', '1151', NULL, NULL, 260, TRUE),

    -- ── VALUATION (3) ──
    ('VAL_KR_PER', 'VALUATION', 'KOSPI PER', 'KOSPI PER',        'KOSPI PER',            'Korea', 'x', 'pct', 'pykrx', 'KOSPI:PER', NULL, NULL, 270, TRUE),
    ('VAL_KR_PBR', 'VALUATION', 'KOSPI PBR', 'KOSPI PBR',        'KOSPI PBR',            'Korea', 'x', 'pct', 'pykrx', 'KOSPI:PBR', NULL, NULL, 271, TRUE),
    ('VAL_KR_DY',  'VALUATION', 'KOSPI DY',  'KOSPI 배당수익률', 'KOSPI Dividend Yield', 'Korea', '%', 'pct', 'pykrx', 'KOSPI:DY',  NULL, NULL, 272, TRUE),

    -- ── STOCK (14) ──
    ('ST_NVDA',    'STOCK', 'NVIDIA',    'NVIDIA',       'NVIDIA Corp',           'US',    'USD', 'pct', 'yfinance', 'NVDA',      NULL, NULL, 300, TRUE),
    ('ST_AVGO',    'STOCK', 'Broadcom',  'Broadcom',     'Broadcom Inc',          'US',    'USD', 'pct', 'yfinance', 'AVGO',      NULL, NULL, 301, TRUE),
    ('ST_GOOGL',   'STOCK', 'Alphabet',  'Alphabet',     'Alphabet Inc',          'US',    'USD', 'pct', 'yfinance', 'GOOGL',     NULL, NULL, 302, TRUE),
    ('ST_AMZN',    'STOCK', 'Amazon',    'Amazon',       'Amazon.com Inc',        'US',    'USD', 'pct', 'yfinance', 'AMZN',      NULL, NULL, 303, TRUE),
    ('ST_META',    'STOCK', 'META',      'META',         'Meta Platforms Inc',    'US',    'USD', 'pct', 'yfinance', 'META',      NULL, NULL, 304, TRUE),
    ('ST_AAPL',    'STOCK', 'Apple',     'Apple',        'Apple Inc',             'US',    'USD', 'pct', 'yfinance', 'AAPL',      NULL, NULL, 305, TRUE),
    ('ST_MSFT',    'STOCK', 'Microsoft', 'Microsoft',    'Microsoft Corp',        'US',    'USD', 'pct', 'yfinance', 'MSFT',      NULL, NULL, 306, TRUE),
    ('ST_TSLA',    'STOCK', 'Tesla',     'Tesla',        'Tesla Inc',             'US',    'USD', 'pct', 'yfinance', 'TSLA',      NULL, NULL, 307, TRUE),
    ('ST_TSMC',    'STOCK', 'TSMC',      'TSMC',         'TSMC ADR',              'TW',    'USD', 'pct', 'yfinance', 'TSM',       NULL, NULL, 308, TRUE),
    ('ST_SAMSUNG', 'STOCK', 'Samsung',   '삼성전자',     'Samsung Electronics',   'Korea', 'KRW', 'pct', 'yfinance', '005930.KS', NULL, NULL, 309, TRUE),
    ('ST_PLTR',    'STOCK', 'Palantir',  'Palantir',     'Palantir Technologies', 'US',    'USD', 'pct', 'yfinance', 'PLTR',      NULL, NULL, 310, TRUE),
    ('ST_BABA',    'STOCK', 'Alibaba',   'Alibaba(HKD)', 'Alibaba Group (HK)',    'HK',    'HKD', 'pct', 'yfinance', '9988.HK',   NULL, NULL, 311, TRUE),
    ('ST_MEITUAN', 'STOCK', 'Meituan',   'Meituan(HKD)', 'Meituan (HK)',          'HK',    'HKD', 'pct', 'yfinance', '3690.HK',   NULL, NULL, 312, TRUE),
    ('ST_TENCENT', 'STOCK', 'Tencent',   'Tencent(HKD)', 'Tencent Holdings (HK)', 'HK',    'HKD', 'pct', 'yfinance', '0700.HK',   NULL, NULL, 313, TRUE);


-- ============================================================
-- 7. mkt001_macro_indicator 시드 데이터
-- ============================================================
INSERT INTO mkt001_macro_indicator (
    indicator_code, name_kr, name_en, category, region,
    unit, period, source, source_series, transform, note, is_active
) VALUES
    ('US_GDP_GROWTH',   '미국 GDP 성장률', 'US Real GDP Growth (QoQ, SAAR)',  'Growth',        'US', '%',  'Q', 'FRED', 'A191RL1Q225SBEA', 'value',          NULL,           TRUE),
    ('US_CPI_YOY',      '미국 CPI YoY',    'US CPI Inflation YoY',            'Inflation',     'US', '%',  'M', 'FRED', 'CPIAUCSL',        'pct_change_yoy', NULL,           TRUE),
    ('US_UNEMPLOYMENT', '미국 실업률',      'US Unemployment Rate',            'Labor',         'US', '%',  'M', 'FRED', 'UNRATE',          'value',          NULL,           TRUE),
    ('US_FED_FUNDS',    '미국 기준금리',    'US Fed Funds Rate',               'Interest Rate', 'US', '%',  'M', 'FRED', 'FEDFUNDS',        'value',          NULL,           TRUE),
    ('US_10Y_YIELD',    '미국 10Y 국채',    'US 10Y Treasury Yield',           'Interest Rate', 'US', '%',  'D', 'FRED', 'DGS10',           'value',          NULL,           TRUE),
    ('US_HY_SPREAD',    'HY 스프레드',      'US HY Credit Spread (OAS)',       'Credit Spread', 'US', 'bp', 'D', 'FRED', 'BAMLH0A0HYM2',   'value',          NULL,           TRUE),
    ('US_IG_SPREAD',    'IG 스프레드',      'US IG Credit Spread (OAS)',       'Credit Spread', 'US', 'bp', 'D', 'FRED', 'BAMLC0A0CM',     'value',          NULL,           TRUE),
    ('KR_GDP_GROWTH',   '한국 GDP 성장률', 'Korea Real GDP Growth (YoY)',     'Growth',        'KR', '%',  'Q', 'ECOS', '901Y009',         'pct_change_yoy', 'item=10101',   TRUE),
    ('KR_CPI_YOY',      '한국 CPI YoY',    'Korea CPI Inflation YoY',         'Inflation',     'KR', '%',  'M', 'ECOS', '901Y009',         'pct_change_yoy', 'item=01',      TRUE),
    ('KR_UNEMPLOYMENT', '한국 실업률',      'Korea Unemployment Rate',         'Labor',         'KR', '%',  'M', 'ECOS', '901Y009',         'value',          'item=19',      TRUE),
    ('KR_BASE_RATE',    '한국 기준금리',    'Korea Base Rate (BOK)',           'Interest Rate', 'KR', '%',  'M', 'ECOS', '722Y001',         'value',          'item=0101000', TRUE);
