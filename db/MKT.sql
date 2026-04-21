-- ============================================================
-- 시장·매크로 데이터 스키마 (Anthillia)
-- Database: FDE_DB   Schema: PUBLIC
--
-- V004: 누락 지표 시드 보완 + 매크로 스키마 추가
--
-- 네이밍 규칙:
--   MKT000  : 시장 지표 마스터
--   MKT001  : 매크로 지표 마스터
--   MKT100  : 시장 데이터 일간 시계열
--   MKT200  : 매크로 데이터 시계열 (D/M/Q)
--
-- 데이터 파이프라인:
--   backend/collectors/market.py  → backend/data/market/market_data.csv  → MKT100_MARKET_DAILY
--   backend/collectors/macro.py   → backend/data/macro/macro_indicators.csv → MKT200_MACRO_DAILY
--   backend/loaders/market_loader.py  : Snowflake 적재 담당
--
-- 식별자 체계:
--   지표코드 (VARCHAR(50))  — 내부 정규 ID (EQ_KOSPI, BD_US_10Y ...)
--   (카테고리, 티커)        — collectors/market.py TICKERS 자연키 (UNIQUE)
--
-- 한글 컬럼명은 Snowflake에서 큰따옴표("")로 감싸서 사용.
-- ============================================================


-- ============================================================
-- 0. 기존 MARKET 관련 오브젝트 제거
-- ============================================================
DROP VIEW  IF EXISTS V_MACRO_LATEST;
DROP VIEW  IF EXISTS V_MARKET_MONITORING;
DROP VIEW  IF EXISTS V_MARKET_TREND;
DROP TABLE IF EXISTS MKT200_MACRO_DAILY;
DROP TABLE IF EXISTS MKT001_MACRO_INDICATOR;
DROP TABLE IF EXISTS MARKET_DAILY;
DROP TABLE IF EXISTS DIM_MARKET_INDICATOR;


-- ============================================================
-- 1. MKT000_MARKET_INDICATOR — 시장 지표 마스터
--    PK: 지표코드 (정규 내부 ID)
--    UNIQUE: (카테고리, 티커) — collectors/market.py TICKERS 자연키
-- ============================================================
CREATE TABLE IF NOT EXISTS MKT000_MARKET_INDICATOR (
    "지표코드"        VARCHAR(50)     NOT NULL,   -- 정규 ID (EQ_KOSPI, BD_US_10Y, ...)
    "카테고리"        VARCHAR(20)     NOT NULL,   -- EQUITY / BOND / FX / COMMODITY / RISK / STOCK
    "티커"            VARCHAR(50)     NOT NULL,   -- collectors/market.py TICKERS 키 ("KOSPI", "US 10Y", ...)
    "지표명"          VARCHAR(200),               -- 한글 표시명
    "지표명_EN"       VARCHAR(200),               -- 영문명
    "하위카테고리"    VARCHAR(50),                -- Korea / US / Europe / Japan 등
    "단위"            VARCHAR(20),                -- pt / pct / USD / KRW ...
    "변동단위"        VARCHAR(20),                -- pct 또는 bp
    "소스"            VARCHAR(30),                -- yfinance / investiny / ECOS ...
    "소스_티커"       VARCHAR(100),               -- 1차 소스 기준 티커/코드
    "소스_폴백"       VARCHAR(200),               -- 폴백 소스/티커 메모
    "비고"            VARCHAR(500),
    "정렬순서"        NUMBER(5),
    "사용여부"        BOOLEAN         DEFAULT TRUE,
    "등록시각"        TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT PK_MKT000_MARKET_INDICATOR PRIMARY KEY ("지표코드"),
    CONSTRAINT UQ_MKT000_MARKET_INDICATOR UNIQUE ("카테고리", "티커")
);


-- ============================================================
-- 2. MKT100_MARKET_DAILY — 시장 데이터 일간 시계열
--    PK: (일자, 지표코드)
--    카테고리/티커는 조회 편의를 위한 중복 컬럼
-- ============================================================
CREATE TABLE IF NOT EXISTS MKT100_MARKET_DAILY (
    "일자"            DATE            NOT NULL,
    "지표코드"        VARCHAR(50)     NOT NULL,   -- FK → MKT000_MARKET_INDICATOR.지표코드
    "카테고리"        VARCHAR(20),                -- 조회 편의용 중복 컬럼
    "티커"            VARCHAR(50),                -- 조회 편의용 중복 컬럼
    "종가"            NUMBER(18,3),                -- 3 decimal places
    "시가"            NUMBER(18,3),
    "고가"            NUMBER(18,3),
    "저가"            NUMBER(18,3),
    "거래량"          NUMBER(20),
    "소스"            VARCHAR(30),                -- 실제 수집 소스 (yfinance / investiny / FDR / ECOS)
    "수집시각"        TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT PK_MKT100_MARKET_DAILY PRIMARY KEY ("일자", "지표코드")
)
CLUSTER BY ("일자");


-- ============================================================
-- 뷰 (Views)
-- ============================================================

-- ============================================================
-- 3. V_MARKET_MONITORING — Bloomberg 일일 모니터링 시트 재현
--    종가 + 전일/전주/전월/전년 변동률. 조인 키: 지표코드
-- ============================================================
CREATE OR REPLACE VIEW V_MARKET_MONITORING AS
WITH latest AS (
    SELECT MAX("일자") AS "최신일자" FROM MKT100_MARKET_DAILY
),
ref_dates AS (
    SELECT
        l."최신일자",
        (SELECT MAX("일자") FROM MKT100_MARKET_DAILY WHERE "일자" <  l."최신일자")                        AS "전일",
        (SELECT MAX("일자") FROM MKT100_MARKET_DAILY WHERE "일자" <= DATEADD('day',   -7, l."최신일자")) AS "전주기준일",
        (SELECT MAX("일자") FROM MKT100_MARKET_DAILY WHERE "일자" <= DATEADD('month', -1, l."최신일자")) AS "전월기준일",
        (SELECT MAX("일자") FROM MKT100_MARKET_DAILY WHERE "일자" <= DATEADD('year',  -1, l."최신일자")) AS "전년기준일"
    FROM latest l
)
SELECT
    d."지표코드",
    d."카테고리",
    d."하위카테고리",
    d."티커",
    d."지표명",
    d."지표명_EN",
    d."단위",
    m."일자",
    m."종가",
    CASE d."변동단위"
        WHEN 'pct' THEN ROUND((m."종가" / NULLIF(p_d."종가", 0) - 1) * 100, 2)
        WHEN 'bp'  THEN ROUND((m."종가" - p_d."종가") * 100, 1)
    END AS "전일비",
    CASE d."변동단위"
        WHEN 'pct' THEN ROUND((m."종가" / NULLIF(p_w."종가", 0) - 1) * 100, 2)
        WHEN 'bp'  THEN ROUND((m."종가" - p_w."종가") * 100, 1)
    END AS "전주비",
    CASE d."변동단위"
        WHEN 'pct' THEN ROUND((m."종가" / NULLIF(p_m."종가", 0) - 1) * 100, 2)
        WHEN 'bp'  THEN ROUND((m."종가" - p_m."종가") * 100, 1)
    END AS "전월비",
    CASE d."변동단위"
        WHEN 'pct' THEN ROUND((m."종가" / NULLIF(p_y."종가", 0) - 1) * 100, 2)
        WHEN 'bp'  THEN ROUND((m."종가" - p_y."종가") * 100, 1)
    END AS "전년비",
    d."정렬순서"
FROM MKT100_MARKET_DAILY m
JOIN MKT000_MARKET_INDICATOR d ON m."지표코드" = d."지표코드"
CROSS JOIN ref_dates r
LEFT JOIN MKT100_MARKET_DAILY p_d ON p_d."지표코드" = m."지표코드" AND p_d."일자" = r."전일"
LEFT JOIN MKT100_MARKET_DAILY p_w ON p_w."지표코드" = m."지표코드" AND p_w."일자" = r."전주기준일"
LEFT JOIN MKT100_MARKET_DAILY p_m ON p_m."지표코드" = m."지표코드" AND p_m."일자" = r."전월기준일"
LEFT JOIN MKT100_MARKET_DAILY p_y ON p_y."지표코드" = m."지표코드" AND p_y."일자" = r."전년기준일"
WHERE m."일자" = r."최신일자"
  AND d."사용여부" = TRUE
ORDER BY d."정렬순서";


-- ============================================================
-- 4. V_MARKET_TREND — 개별 지표 시계열 조회용 (대시보드 차트)
-- ============================================================
CREATE OR REPLACE VIEW V_MARKET_TREND AS
SELECT
    m."일자",
    m."지표코드",
    d."카테고리",
    d."하위카테고리",
    d."티커",
    d."지표명",
    d."지표명_EN",
    d."단위",
    m."종가",
    m."시가",
    m."고가",
    m."저가",
    m."거래량"
FROM MKT100_MARKET_DAILY m
JOIN MKT000_MARKET_INDICATOR d ON m."지표코드" = d."지표코드"
WHERE d."사용여부" = TRUE;


-- ============================================================
-- 5. MKT000_MARKET_INDICATOR 시드 데이터
--    구성: collectors/market.py TICKERS 전체 + FRED spreads
-- ============================================================
INSERT INTO MKT000_MARKET_INDICATOR (
    "지표코드", "카테고리", "티커", "지표명", "지표명_EN",
    "하위카테고리", "단위", "변동단위",
    "소스", "소스_티커", "소스_폴백", "비고",
    "정렬순서", "사용여부"
) VALUES
    -- ── EQUITY (17): 13 indices + MSCI 4 ──
    ('EQ_KOSPI',        'EQUITY', 'KOSPI',       'KOSPI',          'KOSPI Index',                  'Korea',  'pt', 'pct', 'yfinance', '^KS11',      'FDR:KS11',       NULL,                                     1,  TRUE),
    ('EQ_KOSDAQ',       'EQUITY', 'KOSDAQ',      'KOSDAQ',         'KOSDAQ Index',                 'Korea',  'pt', 'pct', 'yfinance', '^KQ11',      'FDR:KQ11',       NULL,                                     2,  TRUE),
    ('EQ_SP500',        'EQUITY', 'S&P500',      'S&P500',         'S&P 500 Index',                'US',     'pt', 'pct', 'yfinance', '^GSPC',      NULL,             NULL,                                     3,  TRUE),
    ('EQ_NASDAQ',       'EQUITY', 'NASDAQ',      '나스닥종합',      'NASDAQ Composite',             'US',     'pt', 'pct', 'yfinance', '^IXIC',      NULL,             NULL,                                     4,  TRUE),
    ('EQ_RUSSELL2000',  'EQUITY', 'Russell2K',   '러셀2000',        'Russell 2000 Index',           'US',     'pt', 'pct', 'yfinance', '^RUT',       NULL,             NULL,                                     5,  TRUE),
    ('EQ_EUROSTOXX50',  'EQUITY', 'STOXX50',     'EURO STOXX50',   'EURO STOXX 50 Index',          'Europe', 'pt', 'pct', 'yfinance', '^STOXX50E',  'investiny:175',  NULL,                                     6,  TRUE),
    ('EQ_DAX',          'EQUITY', 'DAX',         '독일 DAX',        'DAX Index',                    'Europe', 'pt', 'pct', 'yfinance', '^GDAXI',     'investiny:172',  NULL,                                     7,  TRUE),
    ('EQ_CAC40',        'EQUITY', 'CAC40',       '프랑스 CAC40',    'CAC 40 Index',                 'Europe', 'pt', 'pct', 'yfinance', '^FCHI',      'investiny:167',  NULL,                                     8,  TRUE),
    ('EQ_FTSE100',      'EQUITY', 'FTSE100',     '영국 FTSE100',    'FTSE 100 Index',               'Europe', 'pt', 'pct', 'yfinance', '^FTSE',      'investiny:27',   NULL,                                     9,  TRUE),
    ('EQ_NIKKEI225',    'EQUITY', 'Nikkei225',   '니케이225',       'Nikkei 225 Index',             'Japan',  'pt', 'pct', 'yfinance', '^N225',      'FDR:N225,investiny:178', NULL,                             10, TRUE),
    ('EQ_SHANGHAI',     'EQUITY', 'Shanghai',    '상해종합',        'SSE Composite Index',          'China',  'pt', 'pct', 'yfinance', '000001.SS',  'FDR:SSEC,investiny:40820', NULL,                           11, TRUE),
    ('EQ_HSI',          'EQUITY', 'HSI',         '항셍',            'Hang Seng Index',              'China',  'pt', 'pct', 'yfinance', '^HSI',       'FDR:HSI,investiny:179', NULL,                              12, TRUE),
    ('EQ_NIFTY50',      'EQUITY', 'NIFTY50',     'NIFTY 50',       'NIFTY 50 Index',               'India',  'pt', 'pct', 'yfinance', '^NSEI',      'investiny:17940', NULL,                                    13, TRUE),
    ('EQ_MSCI_WORLD',   'EQUITY', 'MSCI World',  'MSCI World',     'MSCI World Index (ETF proxy)', 'MSCI',   'pt', 'pct', 'yfinance', 'URTH',       NULL,             'iShares MSCI World ETF proxy',           14, TRUE),
    ('EQ_MSCI_ACWI',    'EQUITY', 'MSCI ACWI',   'MSCI ACWI',      'MSCI ACWI Index (ETF proxy)',  'MSCI',   'pt', 'pct', 'yfinance', 'ACWI',       NULL,             'iShares MSCI ACWI ETF',                  15, TRUE),
    ('EQ_MSCI_LATAM',   'EQUITY', 'MSCI LATAM',  'MSCI LATAM',     'MSCI LatAm Index (ETF proxy)', 'MSCI',   'pt', 'pct', 'yfinance', 'ILF',        NULL,             'iShares Latin America 40 ETF',           16, TRUE),
    ('EQ_MSCI_EMEA',    'EQUITY', 'MSCI EMEA',   'MSCI EMEA',      'MSCI EMEA Index (ETF proxy)',  'MSCI',   'pt', 'pct', 'yfinance', 'EZA',        NULL,             'iShares South Africa ETF (EM proxy)',    17, TRUE),

    -- ── BOND (10): US Treasuries + Bond ETFs + KR rates ──
    ('BD_US_2Y',        'BOND', 'US 2Y',     '미국 2Y',    'US Treasury 2Y',   'US',    'pct', 'bp',  'yfinance', '^IRX',    NULL, '13W T-Bill proxy', 30, TRUE),
    ('BD_US_10Y',       'BOND', 'US 10Y',    '미국 10Y',   'US Treasury 10Y',  'US',    'pct', 'bp',  'yfinance', '^TNX',    NULL, NULL,               31, TRUE),
    ('BD_US_30Y',       'BOND', 'US 30Y',    '미국 30Y',   'US Treasury 30Y',  'US',    'pct', 'bp',  'yfinance', '^TYX',    NULL, NULL,               32, TRUE),
    ('BD_TLT',          'BOND', 'TLT',       'TLT',       'iShares 20+Y Treasury ETF', 'US', 'pt', 'pct', 'yfinance', 'TLT', NULL, 'Long Treasury ETF', 33, TRUE),
    ('BD_HYG',          'BOND', 'HYG',       'HYG',       'iShares iBoxx HY ETF',      'US', 'pt', 'pct', 'yfinance', 'HYG', NULL, 'High Yield ETF',    34, TRUE),
    ('BD_LQD',          'BOND', 'LQD',       'LQD',       'iShares iBoxx IG ETF',      'US', 'pt', 'pct', 'yfinance', 'LQD', NULL, 'Investment Grade ETF', 35, TRUE),
    ('BD_EMB',          'BOND', 'EMB',       'EMB',       'iShares JPM EM Bond ETF',   'EM', 'pt', 'pct', 'yfinance', 'EMB', NULL, 'EM Bond ETF',        36, TRUE),
    ('BD_AGG',          'BOND', 'AGG',       'AGG',       'iShares Core US Aggregate Bond ETF', 'US', 'pt', 'pct', 'yfinance', 'AGG', NULL, 'US Aggregate Bond ETF (total return proxy)', 37, TRUE),
    ('BD_KR_CD91D',     'BOND', 'KR CD 91D', '한국 CD 91일', 'Korea CD 91D Rate',    'Korea', 'pct', 'bp', 'ECOS', '817Y002', '010502000', 'ECOS stat=817Y002, item=010502000', 40, TRUE),
    ('BD_KR_3Y',        'BOND', 'KR 3Y',     '한국 3Y',    'Korea Treasury 3Y', 'Korea', 'pct', 'bp', 'ECOS',  '817Y002', '010200000', 'ECOS stat=817Y002, item=010200000', 41, TRUE),
    ('BD_KR_10Y',       'BOND', 'KR 10Y',    '한국 10Y',   'Korea Treasury 10Y','Korea', 'pct', 'bp', 'ECOS',  '817Y002', '010200001', 'ECOS stat=817Y002, item=010200001', 42, TRUE),

    -- ── FX (7) ──
    ('FX_DXY',          'FX', 'DXY',      '달러인덱스',    'US Dollar Index (DXY)', 'Index', 'pt',  'pct', 'investiny', 'DX-Y.NYB', 'FDR,yfinance',  NULL, 50, TRUE),
    ('FX_USDKRW',       'FX', 'USD/KRW',  'USD/KRW',    'USD/KRW Exchange Rate', 'KRW',   'KRW', 'pct', 'investiny', 'KRW=X',    'FDR:USD/KRW',   NULL, 51, TRUE),
    ('FX_EURUSD',       'FX', 'EUR/USD',  'EUR/USD',    'EUR/USD Exchange Rate', 'Major', 'USD', 'pct', 'investiny', 'EURUSD=X', 'FDR:EUR/USD',   NULL, 52, TRUE),
    ('FX_USDJPY',       'FX', 'USD/JPY',  'USD/JPY',    'USD/JPY Exchange Rate', 'Major', 'JPY', 'pct', 'investiny', 'JPY=X',    'FDR:USD/JPY',   NULL, 53, TRUE),
    ('FX_USDCNY',       'FX', 'USD/CNY',  'USD/CNY',    'USD/CNY Exchange Rate', 'Major', 'CNY', 'pct', 'investiny', 'CNY=X',    'FDR:USD/CNY',   NULL, 54, TRUE),
    ('FX_AUDUSD',       'FX', 'AUD/USD',  'AUD/USD',    'AUD/USD Exchange Rate', 'Major', 'USD', 'pct', 'investiny', 'AUDUSD=X', 'FDR',           NULL, 55, TRUE),
    ('FX_GBPUSD',       'FX', 'GBP/USD',  'GBP/USD',    'GBP/USD Exchange Rate', 'Major', 'USD', 'pct', 'investiny', 'GBPUSD=X', 'FDR',           NULL, 56, TRUE),

    -- ── COMMODITY (6) ──
    ('CM_WTI',          'COMMODITY', 'WTI',     'NYMEX WTI',      'WTI Crude Oil Futures',   'Energy', 'USD', 'pct', 'investiny', 'CL=F', 'yfinance', NULL, 70, TRUE),
    ('CM_BRENT',        'COMMODITY', 'Brent',   'ICE Brent',      'Brent Crude Oil Futures', 'Energy', 'USD', 'pct', 'investiny', 'BZ=F', 'yfinance', NULL, 71, TRUE),
    ('CM_GOLD',         'COMMODITY', 'Gold',    '금 선물',        'Gold Futures',            'Metal',  'USD', 'pct', 'investiny', 'GC=F', 'yfinance', NULL, 72, TRUE),
    ('CM_SILVER',       'COMMODITY', 'Silver',  '은 선물',        'Silver Futures',          'Metal',  'USD', 'pct', 'investiny', 'SI=F', 'yfinance', NULL, 73, TRUE),
    ('CM_COPPER',       'COMMODITY', 'Copper',  '구리 선물',      'Copper Futures (COMEX)',  'Metal',  'USD', 'pct', 'investiny', 'HG=F', 'yfinance', NULL, 74, TRUE),
    ('CM_NATGAS',       'COMMODITY', 'Nat Gas', '천연가스',       'Natural Gas Futures (HH)', 'Energy', 'USD', 'pct', 'investiny', 'NG=F', 'yfinance', NULL, 75, TRUE),

    -- ── BOND (추가): Bond ETF 3종 + KR 5Y/30Y ──
    ('BD_US_1_3Y',      'BOND', 'SHY',       'SHY',       'iShares 1-3Y Treasury ETF',         'US',    'pt', 'pct', 'yfinance', 'SHY',  NULL, '1-3Y Treasury ETF', 38, TRUE),
    ('BD_US_3_7Y',      'BOND', 'IEI',       'IEI',       'iShares 3-7Y Treasury ETF',         'US',    'pt', 'pct', 'yfinance', 'IEI',  NULL, '3-7Y Treasury ETF', 39, TRUE),
    ('BD_US_TIPS',      'BOND', 'TIP',       'TIP',       'iShares TIPS Bond ETF',             'US',    'pt', 'pct', 'yfinance', 'TIP',  NULL, 'TIPS ETF',          43, TRUE),
    ('BD_KR_5Y',        'BOND', 'KR 5Y',     '한국 5Y',    'Korea Treasury 5Y',  'Korea', 'pct', 'bp', 'ECOS', '817Y002', '010200002', 'ECOS stat=817Y002, item=010200002', 44, TRUE),
    ('BD_KR_30Y',       'BOND', 'KR 30Y',    '한국 30Y',   'Korea Treasury 30Y', 'Korea', 'pct', 'bp', 'ECOS', '817Y002', '010200003', 'ECOS stat=817Y002, item=010200003', 45, TRUE),

    -- ── FX (추가): USD/INR ──
    ('FX_USDINR',       'FX', 'USD/INR',  'USD/INR',    'USD/INR Exchange Rate', 'EM',    'INR', 'pct', 'yfinance', 'USDINR=X', NULL, NULL, 57, TRUE),

    -- ── RISK (3): VIX + VIX3M + FRED Spreads ──
    ('RK_VIX',          'RISK', 'VIX',       'VIX',       'CBOE VIX Index',                    'US', 'pt',  'pct', 'yfinance', '^VIX',           NULL, NULL, 90, TRUE),
    ('RK_VIX3M',        'RISK', 'VIX3M',     'VIX3M',     'CBOE 3-Month VIX Index',            'US', 'pt',  'pct', 'yfinance', '^VIX3M',         NULL, NULL, 91, TRUE),
    ('BD_SPD_HY',       'RISK', 'HY Spread', 'HY Spread', 'ICE BofA US High Yield OAS',        'US', 'bp',  'bp',  'FRED',     'BAMLH0A0HYM2',   NULL, NULL, 92, TRUE),
    ('BD_SPD_IG',       'RISK', 'IG Spread', 'IG Spread', 'ICE BofA US Corporate OAS',         'US', 'bp',  'bp',  'FRED',     'BAMLC0A0CM',     NULL, NULL, 93, TRUE),

    -- ── US SECTOR ETF (11): SPDR ──
    ('SC_US_TECH',      'SECTOR_US', 'SPDR Tech',      'SPDR 기술',      'SPDR Technology Select Sector ETF',        'US', 'pt', 'pct', 'yfinance', 'XLK',  NULL, NULL, 200, TRUE),
    ('SC_US_FIN',       'SECTOR_US', 'SPDR Fin',       'SPDR 금융',      'SPDR Financial Select Sector ETF',         'US', 'pt', 'pct', 'yfinance', 'XLF',  NULL, NULL, 201, TRUE),
    ('SC_US_ENERGY',    'SECTOR_US', 'SPDR Energy',    'SPDR 에너지',    'SPDR Energy Select Sector ETF',            'US', 'pt', 'pct', 'yfinance', 'XLE',  NULL, NULL, 202, TRUE),
    ('SC_US_HEALTH',    'SECTOR_US', 'SPDR Health',    'SPDR 헬스케어',  'SPDR Health Care Select Sector ETF',       'US', 'pt', 'pct', 'yfinance', 'XLV',  NULL, NULL, 203, TRUE),
    ('SC_US_INDU',      'SECTOR_US', 'SPDR Indu',      'SPDR 산업재',    'SPDR Industrial Select Sector ETF',        'US', 'pt', 'pct', 'yfinance', 'XLI',  NULL, NULL, 204, TRUE),
    ('SC_US_DISCR',     'SECTOR_US', 'SPDR ConsDiscr', 'SPDR 임의소비재','SPDR Consumer Discretionary Select ETF',   'US', 'pt', 'pct', 'yfinance', 'XLY',  NULL, NULL, 205, TRUE),
    ('SC_US_STAPLES',   'SECTOR_US', 'SPDR ConsStap',  'SPDR 필수소비재','SPDR Consumer Staples Select Sector ETF',  'US', 'pt', 'pct', 'yfinance', 'XLP',  NULL, NULL, 206, TRUE),
    ('SC_US_UTIL',      'SECTOR_US', 'SPDR Util',      'SPDR 유틸리티',  'SPDR Utilities Select Sector ETF',         'US', 'pt', 'pct', 'yfinance', 'XLU',  NULL, NULL, 207, TRUE),
    ('SC_US_MATL',      'SECTOR_US', 'SPDR Matl',      'SPDR 소재',      'SPDR Materials Select Sector ETF',         'US', 'pt', 'pct', 'yfinance', 'XLB',  NULL, NULL, 208, TRUE),
    ('SC_US_REIT',      'SECTOR_US', 'SPDR REIT',      'SPDR 리츠',      'SPDR Real Estate Select Sector ETF',       'US', 'pt', 'pct', 'yfinance', 'XLRE', NULL, NULL, 209, TRUE),
    ('SC_US_COMM',      'SECTOR_US', 'SPDR Comm',      'SPDR 커뮤니케이션','SPDR Communication Services Select ETF', 'US', 'pt', 'pct', 'yfinance', 'XLC',  NULL, NULL, 210, TRUE),

    -- ── US STYLE/FACTOR ETF (5): iShares ──
    ('FA_US_GROWTH',    'STYLE_US', 'iShares Growth',   '성장',    'iShares S&P 500 Growth ETF',       'US', 'pt', 'pct', 'yfinance', 'IVW',  NULL, NULL, 220, TRUE),
    ('FA_US_VALUE',     'STYLE_US', 'iShares Value',    '가치',    'iShares S&P 500 Value ETF',        'US', 'pt', 'pct', 'yfinance', 'IVE',  NULL, NULL, 221, TRUE),
    ('FA_US_QUALITY',   'STYLE_US', 'iShares Quality',  '퀄리티',  'iShares MSCI USA Quality Factor',  'US', 'pt', 'pct', 'yfinance', 'QUAL', NULL, NULL, 222, TRUE),
    ('FA_US_MOMENTUM',  'STYLE_US', 'iShares Momentum', '모멘텀',  'iShares MSCI USA Momentum Factor', 'US', 'pt', 'pct', 'yfinance', 'MTUM', NULL, NULL, 223, TRUE),
    ('FA_US_LOWVOL',    'STYLE_US', 'iShares LowVol',   '저변동성','iShares MSCI USA Min Vol Factor',  'US', 'pt', 'pct', 'yfinance', 'USMV', NULL, NULL, 224, TRUE),

    -- ── KR SECTOR ETF (11): TIGER 200 GICS — sector_report.py SECTOR_ROTATION 기준 ──
    -- US SPDR 11개와 1:1 페어링. 소스_티커=pykrx 6자리, 소스_폴백=yfinance .KS 티커
    ('SC_KR_IT',        'SECTOR_KR', 'TIGER IT',       'TIGER 200 IT',           'TIGER 200 IT ETF',               'Korea', 'KRW', 'pct', 'pykrx', '364980', NULL, '364980.KS', 230, TRUE),
    ('SC_KR_COMM',      'SECTOR_KR', 'TIGER Comm',     'TIGER 200 커뮤니케이션서비스', 'TIGER 200 커뮤니케이션서비스 ETF', 'Korea', 'KRW', 'pct', 'pykrx', '364990', NULL, '364990.KS', 231, TRUE),
    ('SC_KR_FIN',       'SECTOR_KR', 'TIGER Fin',      'TIGER 200 금융',         'TIGER 200 금융 ETF',             'Korea', 'KRW', 'pct', 'pykrx', '435420', NULL, '435420.KS', 232, TRUE),
    ('SC_KR_ENERGY',    'SECTOR_KR', 'TIGER Energy',   'TIGER 200 에너지화학',    'TIGER 200 에너지화학 ETF',        'Korea', 'KRW', 'pct', 'pykrx', '472170', NULL, '472170.KS', 233, TRUE),
    ('SC_KR_HLTH',      'SECTOR_KR', 'TIGER Health',   'TIGER 200 헬스케어',     'TIGER 200 헬스케어 ETF',         'Korea', 'KRW', 'pct', 'pykrx', '227570', NULL, '227570.KS', 234, TRUE),
    ('SC_KR_INDU',      'SECTOR_KR', 'TIGER Indu',     'TIGER 200 산업재',       'TIGER 200 산업재 ETF',           'Korea', 'KRW', 'pct', 'pykrx', '227560', NULL, '227560.KS', 235, TRUE),
    ('SC_KR_HEAVY',     'SECTOR_KR', 'TIGER Heavy',    'TIGER 200 중공업',       'TIGER 200 중공업 ETF',           'Korea', 'KRW', 'pct', 'pykrx', '157490', NULL, '157490.KS', 236, TRUE),
    ('SC_KR_DISCR',     'SECTOR_KR', 'TIGER Discr',    'TIGER 200 경기소비재',   'TIGER 200 경기소비재 ETF',       'Korea', 'KRW', 'pct', 'pykrx', '227540', NULL, '227540.KS', 237, TRUE),
    ('SC_KR_STAPLES',   'SECTOR_KR', 'TIGER Staples',  'TIGER 200 생활소비재',   'TIGER 200 생활소비재 ETF',       'Korea', 'KRW', 'pct', 'pykrx', '227550', NULL, '227550.KS', 238, TRUE),
    ('SC_KR_STEEL',     'SECTOR_KR', 'TIGER Steel',    'TIGER 200 철강소재',     'TIGER 200 철강소재 ETF',         'Korea', 'KRW', 'pct', 'pykrx', '494840', NULL, '494840.KS', 239, TRUE),
    ('SC_KR_CONSTR',    'SECTOR_KR', 'TIGER Constr',   'TIGER 200 건설',         'TIGER 200 건설 ETF',             'Korea', 'KRW', 'pct', 'pykrx', '139270', NULL, '139270.KS', 240, TRUE),

    -- ── STOCK (14) ──
    ('ST_NVDA',         'STOCK', 'NVIDIA',    'NVIDIA',           'NVIDIA Corp',            'US',    'USD', 'pct', 'yfinance', 'NVDA',      NULL, NULL, 300, TRUE),
    ('ST_AVGO',         'STOCK', 'Broadcom',  'Broadcom',         'Broadcom Inc',           'US',    'USD', 'pct', 'yfinance', 'AVGO',      NULL, NULL, 301, TRUE),
    ('ST_GOOGL',        'STOCK', 'Alphabet',  'Alphabet',         'Alphabet Inc',           'US',    'USD', 'pct', 'yfinance', 'GOOGL',     NULL, NULL, 302, TRUE),
    ('ST_AMZN',         'STOCK', 'Amazon',    'Amazon',           'Amazon.com Inc',         'US',    'USD', 'pct', 'yfinance', 'AMZN',      NULL, NULL, 303, TRUE),
    ('ST_META',         'STOCK', 'META',      'META',             'Meta Platforms Inc',     'US',    'USD', 'pct', 'yfinance', 'META',      NULL, NULL, 304, TRUE),
    ('ST_AAPL',         'STOCK', 'Apple',     'Apple',            'Apple Inc',              'US',    'USD', 'pct', 'yfinance', 'AAPL',      NULL, NULL, 305, TRUE),
    ('ST_MSFT',         'STOCK', 'Microsoft', 'Microsoft',        'Microsoft Corp',         'US',    'USD', 'pct', 'yfinance', 'MSFT',      NULL, NULL, 306, TRUE),
    ('ST_TSLA',         'STOCK', 'Tesla',     'Tesla',            'Tesla Inc',              'US',    'USD', 'pct', 'yfinance', 'TSLA',      NULL, NULL, 307, TRUE),
    ('ST_TSMC',         'STOCK', 'TSMC',      'TSMC',             'TSMC ADR',               'TW',    'USD', 'pct', 'yfinance', 'TSM',       NULL, NULL, 308, TRUE),
    ('ST_SAMSUNG',      'STOCK', 'Samsung',   '삼성전자',          'Samsung Electronics',    'Korea', 'KRW', 'pct', 'yfinance', '005930.KS', NULL, NULL, 309, TRUE),
    ('ST_PLTR',         'STOCK', 'Palantir',  'Palantir',         'Palantir Technologies',  'US',    'USD', 'pct', 'yfinance', 'PLTR',      NULL, NULL, 310, TRUE),
    ('ST_BABA',         'STOCK', 'Alibaba',   'Alibaba(HKD)',     'Alibaba Group (HK)',     'HK',    'HKD', 'pct', 'yfinance', '9988.HK',   NULL, NULL, 311, TRUE),
    ('ST_MEITUAN',      'STOCK', 'Meituan',   'Meituan(HKD)',     'Meituan (HK)',           'HK',    'HKD', 'pct', 'yfinance', '3690.HK',   NULL, NULL, 312, TRUE),
    ('ST_TENCENT',      'STOCK', 'Tencent',   'Tencent(HKD)',     'Tencent Holdings (HK)',  'HK',    'HKD', 'pct', 'yfinance', '0700.HK',   NULL, NULL, 313, TRUE);


-- ============================================================
-- 5-B. V005 확장 시드 — CSV 에 이미 수집중인 보조 지표 정식 등록
--      (IX_KR_*: KOSPI200 GICS 섹터 지수, VAL_KR_*: KOSPI 밸류에이션,
--       EQ_TWSE: 대만 가권, SC_KR_* 확장: TIGER/KODEX 테마 ETF)
-- ============================================================
INSERT INTO MKT000_MARKET_INDICATOR (
    "지표코드", "카테고리", "티커", "지표명", "지표명_EN",
    "하위카테고리", "단위", "변동단위",
    "소스", "소스_티커", "소스_폴백", "비고",
    "정렬순서", "사용여부"
) VALUES
    -- ── EQUITY 확장 (1): 대만 가권 ──
    ('EQ_TWSE',         'EQUITY', 'TAIEX',      '대만 가권',       'Taiwan Weighted Index',     'Taiwan', 'pt', 'pct', 'yfinance', '^TWII',  NULL, NULL,                                     18, TRUE),

    -- ── SECTOR_KR_INDEX (11): KOSPI200 GICS 지수 (pykrx, 2010~) ──
    ('IX_KR_IT',        'SECTOR_KR_INDEX', 'KOSPI200 IT',      'KOSPI200 정보기술',    'KOSPI200 Information Technology Index', 'Korea', 'pt', 'pct', 'pykrx', '1155', NULL, 'pykrx stock.get_index_ohlcv_by_date', 250, TRUE),
    ('IX_KR_COMM',      'SECTOR_KR_INDEX', 'KOSPI200 Comm',    'KOSPI200 커뮤니케이션', 'KOSPI200 Communication Services Index', 'Korea', 'pt', 'pct', 'pykrx', '1150', NULL, NULL, 251, TRUE),
    ('IX_KR_FIN',       'SECTOR_KR_INDEX', 'KOSPI200 Fin',     'KOSPI200 금융',        'KOSPI200 Financials Index',             'Korea', 'pt', 'pct', 'pykrx', '1156', NULL, NULL, 252, TRUE),
    ('IX_KR_ENERGY',    'SECTOR_KR_INDEX', 'KOSPI200 Energy',  'KOSPI200 에너지/화학', 'KOSPI200 Energy/Chemicals Index',       'Korea', 'pt', 'pct', 'pykrx', '1154', NULL, NULL, 253, TRUE),
    ('IX_KR_HEALTH',    'SECTOR_KR_INDEX', 'KOSPI200 Health',  'KOSPI200 헬스케어',    'KOSPI200 Health Care Index',            'Korea', 'pt', 'pct', 'pykrx', '1160', NULL, NULL, 254, TRUE),
    ('IX_KR_INDU',      'SECTOR_KR_INDEX', 'KOSPI200 Indu',    'KOSPI200 산업재',      'KOSPI200 Industrials Index',            'Korea', 'pt', 'pct', 'pykrx', '1159', NULL, NULL, 255, TRUE),
    ('IX_KR_HEAVY',     'SECTOR_KR_INDEX', 'KOSPI200 Heavy',   'KOSPI200 중공업',      'KOSPI200 Heavy Industry Index',         'Korea', 'pt', 'pct', 'pykrx', '1152', NULL, NULL, 256, TRUE),
    ('IX_KR_DISCR',     'SECTOR_KR_INDEX', 'KOSPI200 Discr',   'KOSPI200 경기소비재',  'KOSPI200 Consumer Discretionary Index', 'Korea', 'pt', 'pct', 'pykrx', '1158', NULL, NULL, 257, TRUE),
    ('IX_KR_STAPLES',   'SECTOR_KR_INDEX', 'KOSPI200 Staples', 'KOSPI200 생활소비재',  'KOSPI200 Consumer Staples Index',       'Korea', 'pt', 'pct', 'pykrx', '1157', NULL, NULL, 258, TRUE),
    ('IX_KR_STEEL',     'SECTOR_KR_INDEX', 'KOSPI200 Steel',   'KOSPI200 철강/소재',   'KOSPI200 Steel/Materials Index',        'Korea', 'pt', 'pct', 'pykrx', '1153', NULL, NULL, 259, TRUE),
    ('IX_KR_CONSTR',    'SECTOR_KR_INDEX', 'KOSPI200 Constr',  'KOSPI200 건설',        'KOSPI200 Construction Index',           'Korea', 'pt', 'pct', 'pykrx', '1151', NULL, NULL, 260, TRUE),

    -- ── VALUATION (3): KOSPI 밸류에이션 지표 (pykrx) ──
    ('VAL_KR_PER',      'VALUATION', 'KOSPI PER',  'KOSPI PER',       'KOSPI PER',               'Korea', 'x',   'pct', 'pykrx', 'KOSPI:PER', NULL, 'pykrx stock.get_index_fundamental', 270, TRUE),
    ('VAL_KR_PBR',      'VALUATION', 'KOSPI PBR',  'KOSPI PBR',       'KOSPI PBR',               'Korea', 'x',   'pct', 'pykrx', 'KOSPI:PBR', NULL, NULL, 271, TRUE),
    ('VAL_KR_DY',       'VALUATION', 'KOSPI DY',   'KOSPI 배당수익률', 'KOSPI Dividend Yield',    'Korea', '%',   'pct', 'pykrx', 'KOSPI:DY',  NULL, NULL, 272, TRUE),

    -- ── SECTOR_KR 확장 (14): TIGER/KODEX 테마 ETF (sector_country 사이클 미사용, 참조용) ──
    ('SC_KR_SEMI',      'SECTOR_KR', 'TIGER Semi',     'TIGER 반도체',          'TIGER Semiconductor ETF',         'Korea', 'KRW', 'pct', 'yfinance', '277630.KS', NULL, NULL, 241, TRUE),
    ('SC_KR_BIO',       'SECTOR_KR', 'TIGER Bio',      'TIGER 헬스케어',         'TIGER Health Care ETF',           'Korea', 'KRW', 'pct', 'yfinance', '166400.KS', NULL, NULL, 242, TRUE),
    ('SC_KR_BATTERY',   'SECTOR_KR', 'TIGER Battery',  'TIGER 2차전지테마',      'TIGER Battery Theme ETF',         'Korea', 'KRW', 'pct', 'yfinance', '137610.KS', NULL, NULL, 243, TRUE),
    ('SC_KR_BANK',      'SECTOR_KR', 'TIGER Bank',     'TIGER 은행',             'TIGER Banks ETF',                 'Korea', 'KRW', 'pct', 'yfinance', '261140.KS', NULL, NULL, 244, TRUE),
    ('SC_KR_HEALTH',    'SECTOR_KR', 'TIGER MedDev',   'TIGER 의료기기',         'TIGER Medical Devices ETF',       'Korea', 'KRW', 'pct', 'yfinance', '400970.KS', NULL, 'TIGER 200 헬스케어와 구별 (SC_KR_HLTH)', 245, TRUE),
    ('SC_KR_AUTO',      'SECTOR_KR', 'KODEX Auto',     'KODEX 자동차',           'KODEX Auto ETF',                  'Korea', 'KRW', 'pct', 'yfinance', '091180.KS', NULL, NULL, 246, TRUE),
    ('SC_KR_TELECOM',   'SECTOR_KR', 'KODEX Telecom',  'KODEX 통신',             'KODEX Telecom ETF',               'Korea', 'KRW', 'pct', 'yfinance', '098560.KS', NULL, NULL, 247, TRUE),
    ('SC_KR_INSUR',     'SECTOR_KR', 'KODEX Insur',    'KODEX 보험',             'KODEX Insurance ETF',             'Korea', 'KRW', 'pct', 'yfinance', '140700.KS', NULL, NULL, 248, TRUE),
    ('SC_KR_TRANSPORT', 'SECTOR_KR', 'KODEX Trans',    'KODEX 운송',             'KODEX Transport ETF',             'Korea', 'KRW', 'pct', 'yfinance', '140710.KS', NULL, NULL, 249, TRUE),
    ('SC_KR_MEDIA',     'SECTOR_KR', 'KODEX Media',    'KODEX 미디어&엔터',      'KODEX Media/Entertainment ETF',    'Korea', 'KRW', 'pct', 'yfinance', '108590.KS', NULL, NULL, 261, TRUE),
    ('SC_KR_DEFENSE',   'SECTOR_KR', 'TIGER Defense',  'TIGER 경기방어',          'TIGER Defensive ETF',              'Korea', 'KRW', 'pct', 'yfinance', '174360.KS', NULL, NULL, 262, TRUE),
    ('SC_KR_GAME',      'SECTOR_KR', 'KODEX Game',     'KODEX 게임&엔터',         'KODEX Game/Entertainment ETF',     'Korea', 'KRW', 'pct', 'yfinance', '228800.KS', NULL, NULL, 263, TRUE),
    ('SC_KR_BIOTECH',   'SECTOR_KR', 'KODEX Biotech',  'KODEX 바이오테크',        'KODEX Biotech ETF',                'Korea', 'KRW', 'pct', 'yfinance', '278530.KS', NULL, NULL, 264, TRUE),
    ('SC_KR_COSDAQ_IT', 'SECTOR_KR', 'KODEX KOSDAQ IT','KODEX 코스닥150IT',      'KODEX KOSDAQ150 IT ETF',           'Korea', 'KRW', 'pct', 'yfinance', '261240.KS', NULL, NULL, 265, TRUE);


-- ============================================================
-- 6. MKT200_MACRO_DAILY — 거시경제 지표 시계열
--    주기: D(일간) / M(월간) / Q(분기)
--    소스: FRED / ECOS
-- ============================================================
DROP TABLE IF EXISTS MKT200_MACRO_DAILY;

CREATE TABLE IF NOT EXISTS MKT200_MACRO_DAILY (
    "일자"            DATE            NOT NULL,   -- 발표/관측 기준일 (월간=월초, 분기=분기말)
    "지표코드"        VARCHAR(50)     NOT NULL,   -- e.g. US_CPI_YOY
    "카테고리"        VARCHAR(50),                -- Growth / Inflation / Labor / Interest Rate / Credit Spread
    "지역"            VARCHAR(10),                -- US / KR
    "값"              NUMBER(18,4),
    "단위"            VARCHAR(20),                -- % / bp
    "주기"            CHAR(1),                    -- D / M / Q
    "소스"            VARCHAR(20),                -- FRED / ECOS
    "소스_시리즈"     VARCHAR(50),                -- FRED series_id or ECOS stat_code
    "수집시각"        TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT PK_MKT200_MACRO_DAILY PRIMARY KEY ("일자", "지표코드")
)
CLUSTER BY ("일자");


-- ============================================================
-- 7. MKT001_MACRO_INDICATOR — 매크로 지표 마스터
-- ============================================================
DROP TABLE IF EXISTS MKT001_MACRO_INDICATOR;

CREATE TABLE IF NOT EXISTS MKT001_MACRO_INDICATOR (
    "지표코드"        VARCHAR(50)     NOT NULL,
    "지표명"          VARCHAR(200),
    "지표명_EN"       VARCHAR(200),
    "카테고리"        VARCHAR(50),
    "지역"            VARCHAR(10),
    "단위"            VARCHAR(20),
    "주기"            CHAR(1),                    -- D / M / Q
    "소스"            VARCHAR(20),
    "소스_시리즈"     VARCHAR(50),
    "변환"            VARCHAR(30),                -- value / pct_change_yoy / diff
    "비고"            VARCHAR(500),
    "사용여부"        BOOLEAN         DEFAULT TRUE,
    "등록시각"        TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT PK_MKT001_MACRO_INDICATOR PRIMARY KEY ("지표코드")
);

INSERT INTO MKT001_MACRO_INDICATOR (
    "지표코드", "지표명", "지표명_EN", "카테고리", "지역",
    "단위", "주기", "소스", "소스_시리즈", "변환", "비고", "사용여부"
) VALUES
    ('US_GDP_GROWTH',   '미국 GDP 성장률',    'US Real GDP Growth (QoQ, SAAR)',   'Growth',        'US', '%',  'Q', 'FRED', 'A191RL1Q225SBEA', 'value',           NULL, TRUE),
    ('US_CPI_YOY',      '미국 CPI YoY',       'US CPI Inflation YoY',             'Inflation',     'US', '%',  'M', 'FRED', 'CPIAUCSL',        'pct_change_yoy',  NULL, TRUE),
    ('US_UNEMPLOYMENT', '미국 실업률',         'US Unemployment Rate',             'Labor',         'US', '%',  'M', 'FRED', 'UNRATE',          'value',           NULL, TRUE),
    ('US_FED_FUNDS',    '미국 기준금리',       'US Fed Funds Rate',                'Interest Rate', 'US', '%',  'M', 'FRED', 'FEDFUNDS',        'value',           NULL, TRUE),
    ('US_10Y_YIELD',    '미국 10Y 국채',       'US 10Y Treasury Yield',            'Interest Rate', 'US', '%',  'D', 'FRED', 'DGS10',           'value',           NULL, TRUE),
    ('US_HY_SPREAD',    'HY 스프레드',         'US HY Credit Spread (OAS)',        'Credit Spread', 'US', 'bp', 'D', 'FRED', 'BAMLH0A0HYM2',   'value',           NULL, TRUE),
    ('US_IG_SPREAD',    'IG 스프레드',         'US IG Credit Spread (OAS)',        'Credit Spread', 'US', 'bp', 'D', 'FRED', 'BAMLC0A0CM',     'value',           NULL, TRUE),
    ('KR_GDP_GROWTH',   '한국 GDP 성장률',    'Korea Real GDP Growth (YoY)',      'Growth',        'KR', '%',  'Q', 'ECOS', '901Y009',         'pct_change_yoy',  'item=10101', TRUE),
    ('KR_CPI_YOY',      '한국 CPI YoY',       'Korea CPI Inflation YoY',          'Inflation',     'KR', '%',  'M', 'ECOS', '901Y009',         'pct_change_yoy',  'item=01',    TRUE),
    ('KR_UNEMPLOYMENT', '한국 실업률',         'Korea Unemployment Rate',          'Labor',         'KR', '%',  'M', 'ECOS', '901Y009',         'value',           'item=19',    TRUE),
    ('KR_BASE_RATE',    '한국 기준금리',       'Korea Base Rate (BOK)',            'Interest Rate', 'KR', '%',  'M', 'ECOS', '722Y001',         'value',           'item=0101000', TRUE);


-- ============================================================
-- 8. V_MACRO_LATEST — 매크로 지표 최신값 모니터링 뷰
-- ============================================================
CREATE OR REPLACE VIEW V_MACRO_LATEST AS
WITH ranked AS (
    SELECT
        m."지표코드",
        m."일자",
        m."값",
        m."단위",
        m."주기",
        m."소스",
        ROW_NUMBER() OVER (PARTITION BY m."지표코드" ORDER BY m."일자" DESC) AS rn
    FROM MKT200_MACRO_DAILY m
)
SELECT
    i."지표코드",
    i."카테고리",
    i."지역",
    i."지표명",
    i."지표명_EN",
    r."일자",
    r."값",
    i."단위",
    i."주기",
    i."소스"
FROM ranked r
JOIN MKT001_MACRO_INDICATOR i ON r."지표코드" = i."지표코드"
WHERE r.rn = 1
  AND i."사용여부" = TRUE
ORDER BY i."지역", i."카테고리", i."지표코드";
