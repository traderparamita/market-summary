-- ==========================================================
-- 변액펀드 AI Assistant — Snowflake 전체 테이블 스키마
-- V0003: 정규화 + 번호 재배치
--
-- 네이밍: FND{대분류}{순번}_{영문명}
--   FND000~  : 마스터 (펀드, 하위펀드, 종목)
--   FND100~  : 펀드(모펀드) 팩트 (기준가, 보유, 매매, 헷지)
--   FND200~  : 하위펀드 팩트 (구성종목)
--   FND300~  : 펀드 특성/등급
--   FND400~  : Peer 비교 (외부 공시)
--   FND900~  : 참조/코드 테이블 (BROKER, TRADE_TYPE 등)
-- ==========================================================

-- ==========================================================
-- 마스터 테이블 (Dimension)
-- ==========================================================

-- FND000: 펀드(모펀드) 마스터
CREATE TABLE IF NOT EXISTS FND000_FUND (
    ID                  CHAR(26)     NOT NULL PRIMARY KEY,
    FUND_CD             VARCHAR(10)     NOT NULL UNIQUE,
    FUND_NM             VARCHAR(200),
    BM_NM               VARCHAR(300),                     -- 벤치마크명
    FUND_TYPE           VARCHAR(30),                      -- 주식형/채권형/혼합형/대안형
    OFFER_TYPE          VARCHAR(30),                      -- 공모/사모
    PM_NAME             VARCHAR(50),                      -- 운용역
    INCEPTION_DT        DATE,                             -- 설정일
    IS_ACTIVE           BOOLEAN DEFAULT TRUE,             -- 운용 중 여부
    LOADED_AT           TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9)))
);

-- FND001: 하위펀드 마스터 (ETF, 수익증권 등)
CREATE TABLE IF NOT EXISTS FND001_SUB_FUND (
    ID                  CHAR(26)     NOT NULL PRIMARY KEY,
    SUB_FUND_CD         VARCHAR(20)     NOT NULL UNIQUE,
    SUB_FUND_NM         VARCHAR(200),
    STD_CD              VARCHAR(20),                      -- 표준코드 (ISIN/KFIA)
    TICKER              VARCHAR(20),
    SUB_FUND_TYPE       VARCHAR(30),                      -- 국내ETF/해외ETF/국내수익증권/해외수익증권
    SEC_ATTR            VARCHAR(50),                      -- 종목속성
    ASSET_MGR           VARCHAR(100),                     -- 운용회사
    CCY                 VARCHAR(10),                      -- 종목통화
    DOMICILE            VARCHAR(30),                      -- 설정국가
    LOADED_AT           TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9)))
);

-- FND002: 종목 마스터 (주식, 채권, 현금성 등) — 정적 속성만
CREATE TABLE IF NOT EXISTS FND002_SECURITY (
    ID                  CHAR(26)     NOT NULL PRIMARY KEY,
    SECURITY_CD         VARCHAR(20)     NOT NULL UNIQUE,
    SECURITY_NM         VARCHAR(200),
    TICKER              VARCHAR(30),                      -- 티커
    ISIN                VARCHAR(20)     UNIQUE,                      -- ISIN 코드
    SECURITY_TYPE       VARCHAR(30),                      -- 주식/채권/현금성/파생
    SECTOR              VARCHAR(50),                      -- 업종/섹터
    INDUSTRY            VARCHAR(100),                     -- 산업 (Semiconductors 등)
    COUNTRY             VARCHAR(30),                      -- 국가
    CCY                 VARCHAR(10),                      -- 통화
    EXCHANGE            VARCHAR(30),                      -- 거래소
    LOADED_AT           TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9)))
);

-- ==========================================================
-- 100대: 팩트 — 일별 측정치
-- ==========================================================

-- FND100: 펀드 기준가 (원본: R2101)
CREATE TABLE IF NOT EXISTS FND100_FUND_NAV (
    ID                  CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT             DATE            NOT NULL,
    FUND_ID             CHAR(26)     NOT NULL REFERENCES FND000_FUND(ID),
    BM_INDEX            NUMBER(18,4),                     -- 벤치마크 지수값
    CUM_NAV             NUMBER(18,4),                     -- 누적기준가
    NAV                 NUMBER(18,4),                     -- 기준가
    TAX_NAV             NUMBER(18,4),                     -- 과표기준가
    FX_NAV              NUMBER(18,4),                     -- 외화기준가
    FX_CUM_NAV          NUMBER(18,4),                     -- 외화누적기준가
    LOADED_AT           TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9))),
    UNIQUE (BASE_DT, FUND_ID)
);

-- FND101: 펀드별 보유종목 상세 (원본: R2301 + R7622_DETAIL + R4202 통합)
-- 종목 속성(종목명, 티커, 표준코드, 통화, 국가 등)은 FND001_SUB_FUND 마스터 참조
CREATE TABLE IF NOT EXISTS FND101_FUND_HOLDING (
    ID                  CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT             DATE            NOT NULL,
    FUND_ID             CHAR(26)     NOT NULL REFERENCES FND000_FUND(ID),
    SUB_FUND_ID         CHAR(26)     NOT NULL REFERENCES FND001_SUB_FUND(ID),

    -- 자산 분류
    ASSET_TYPE          VARCHAR(50),                      -- 자산구분
    ASSET_CLASS_1       VARCHAR(50),                      -- (신)자산구분1
    ASSET_CLASS_2       VARCHAR(50),                      -- (신1)자산구분2

    -- 보유 측정치 (공통)
    TRADE_TYPE          VARCHAR(30),                      -- 매매구분
    FACE_QTY            NUMBER(18,4),                     -- 액면(수량)
    BOOK_VALUE          NUMBER(18,0),                     -- 취득가(장부평가)
    MKT_VALUE           NUMBER(18,0),                     -- 평가금액
    UNREALIZED_PL       NUMBER(18,0),                     -- 평가손익
    FX_PL               NUMBER(18,0),                     -- 외화환산손익
    DAILY_UNREALIZED_PL NUMBER(18,0),                     -- 당일평가손익
    DAILY_FX_PL         NUMBER(18,0),                     -- 당일외화환산손익
    ACQ_PRICE           NUMBER(18,6),                     -- 취득단가
    EVAL_PRICE          NUMBER(18,6),                     -- 평가단가
    NAV_WEIGHT_PCT      NUMBER(10,6),                     -- 순자산비
    FX_RATE             NUMBER(18,6),                     -- 종가환율
    FC_ACQ_PRICE        NUMBER(18,6),                     -- 외화기준취득단가

    -- 채권 전용
    ISSUE_DT            DATE,                             -- (최초)발행일
    MATURITY_DT         DATE,                             -- 만기일
    ACCRUED_INT         NUMBER(18,0),                     -- 미수이자
    DAILY_ACCRUED_INT   NUMBER(18,0),                     -- 당일미수이자
    REDEMPTION_PL       NUMBER(18,0),                     -- 상환손익
    BUY_YIELD           NUMBER(10,6),                     -- 매입수익율
    MKT_YIELD           NUMBER(10,6),                     -- 시장수익율
    CREDIT_RATING       VARCHAR(20),                      -- 신용등급
    COUPON_RATE         NUMBER(10,6),                     -- 표면이율
    COUNTER_SEC         VARCHAR(200),                     -- 상대종목

    -- 거래 이력
    FIRST_TRADE_DT      DATE,                             -- 최초거래일
    FIRST_BROKER_ID     CHAR(26) REFERENCES FND900_BROKER(ID),  -- 최초중개기관
    BOOK_VALUE_PRE      NUMBER(18,0),                     -- 장부가(결산전)
    UNREALIZED_PL_PRE   NUMBER(18,0),                     -- 평가손익(결산전)

    -- 펀드/수익증권 전용 (R4202 유래)
    DIVIDEND            NUMBER(18,0),                     -- 배당금
    UNREALIZED_PL_TAX   NUMBER(18,0),                     -- 평가손익(과세)
    UNREALIZED_PL_NONTAX  NUMBER(18,0),                   -- 평가손익(비과세)
    UNREALIZED_PL_NONTAX2 NUMBER(18,0),                   -- 평가손익(비과세2)
    REBATE_AMT          NUMBER(18,0),                     -- 리베이트금액
    REBATE_FX_AMT       NUMBER(18,0),                     -- 리베이트환산금액
    REBATE_FX_PL        NUMBER(18,0),                     -- 리베이트환산손익
    REBATE_CCY          VARCHAR(10),                      -- 리베이트통화
    REBATE_RATE         NUMBER(10,6),                     -- 리베이트율
    ISSUE_TOTAL_PCT     NUMBER(10,6),                     -- 발행총수비

    LOADED_AT           TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9))),
    UNIQUE (BASE_DT, FUND_ID, SUB_FUND_ID)
);

-- FND102: 주식 매매내역 (원본: R3101)
-- 종목 속성(종목명, 티커, 표준코드, 통화)은 FND001_SUB_FUND 마스터 참조
CREATE TABLE IF NOT EXISTS FND102_STOCK_TRADE (
    ID              CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT         DATE            NOT NULL,
    FUND_ID         CHAR(26)     NOT NULL REFERENCES FND000_FUND(ID),
    SUB_FUND_ID     CHAR(26)     NOT NULL REFERENCES FND001_SUB_FUND(ID),
    ASSET_MGR       VARCHAR(50),                          -- 운용역
    TRADE_TYPE      VARCHAR(30),                          -- 구분
    BROKER_ID       CHAR(26) REFERENCES FND900_BROKER(ID),  -- 거래처
    UNIT_PRICE      NUMBER(18,4),                         -- 단가
    QTY             NUMBER(18,0),                         -- 수량
    AMOUNT          NUMBER(18,0),                         -- 금액
    COMMISSION      NUMBER(18,0),                         -- 수수료
    SETTLE_AMOUNT   NUMBER(18,0),                         -- 결제금액
    REALIZED_PL     NUMBER(18,0),                         -- 매매손익
    REALIZED_GAIN   NUMBER(18,0),                         -- 매매이익
    REALIZED_LOSS   NUMBER(18,0),                         -- 매매손실
    TRADE_CLASS     VARCHAR(30),                          -- 매매구분
    TRADE_SUBTYPE   VARCHAR(30),                          -- 매매유형
    LOADED_AT       TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9)))
);

-- FND103: 수익증권/펀드 매매내역 (원본: R4102)
-- 종목 속성(종목명, 표준코드)은 FND001_SUB_FUND 마스터 참조
CREATE TABLE IF NOT EXISTS FND103_FUND_TRADE (
    ID                      CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT                 DATE            NOT NULL,
    FUND_ID                 CHAR(26)     NOT NULL REFERENCES FND000_FUND(ID),
    SUB_FUND_ID             CHAR(26)     NOT NULL REFERENCES FND001_SUB_FUND(ID),
    TRADE_CD                NUMBER(10,0),                 -- 매매코드
    TRADE_NM                VARCHAR(50),                  -- 매매명
    QTY                     NUMBER(18,0),                 -- 수량
    AMOUNT                  NUMBER(18,0),                 -- 금액
    UNIT_PRICE              NUMBER(18,4),                 -- 매매단가
    REALIZED_PL             NUMBER(18,0),                 -- 매매손익
    BROKER_ID               CHAR(26) REFERENCES FND900_BROKER(ID),  -- 매매처
    PARENT_FUND_SET_QTY     NUMBER(18,0),                 -- 모수익증권일반설정좌수
    PARENT_FUND_SET_AMT     NUMBER(18,0),                 -- 모수익증권일반설정금액
    REALIZED_GAIN           NUMBER(18,0),                 -- 매매이익
    REALIZED_LOSS           NUMBER(18,0),                 -- 매매손실
    LOADED_AT               TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9)))
);

-- ==========================================================
-- 200대: 하위펀드 팩트
-- ==========================================================

-- FND200: 하위펀드→종목 보유현황 (ETF/수익증권 내부 구성종목)
-- 종목 속성(종목명, 섹터, 국가)은 FND002_SECURITY 마스터 참조
CREATE TABLE IF NOT EXISTS FND200_SUB_FUND_HOLDING (
    ID                  CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT             DATE            NOT NULL,
    SUB_FUND_ID         CHAR(26)     NOT NULL REFERENCES FND001_SUB_FUND(ID),
    SECURITY_ID         CHAR(26)     NOT NULL REFERENCES FND002_SECURITY(ID),
    RANK                NUMBER(5,0),                      -- 비중 순위
    HOLD_QTY            NUMBER(18,4),                     -- 보유수량
    MKT_VALUE           NUMBER(18,0),                     -- 평가금액
    WEIGHT_PCT          NUMBER(8,4),                      -- 비중 (%)
    RETURN_PCT          NUMBER(8,4),                      -- 수익률 (%)
    SOURCE              VARCHAR(30),                      -- 데이터 출처 (운용사 API명)
    LOADED_AT           TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9))),
    UNIQUE (BASE_DT, SUB_FUND_ID, SECURITY_ID)
);

-- FND201: 주식 종목 밸류에이션 (사무수탁사 제공, 주식 전용)
-- 종목 마스터는 FND002_SECURITY 참조 (SECURITY_TYPE = '주식' 인 종목 대상)
CREATE TABLE IF NOT EXISTS FND201_EQUITY_VALUATION (
    ID                  CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT             DATE            NOT NULL,
    SECURITY_ID         CHAR(26)     NOT NULL REFERENCES FND002_SECURITY(ID),

    -- 가격
    CLOSE_PRICE         NUMBER(18,4),                     -- 종가
    CHANGE_PCT          NUMBER(8,4),                      -- 등락률(%)
    HIGH_52W            NUMBER(18,4),                     -- 52주 최고가
    LOW_52W             NUMBER(18,4),                     -- 52주 최저가
    VOLUME              NUMBER(20,0),                     -- 거래량

    -- 밸류에이션
    PER                 NUMBER(10,2),                     -- PER
    PBR                 NUMBER(10,2),                     -- PBR
    PSR                 NUMBER(10,2),                     -- PSR
    EV_EBITDA           NUMBER(10,2),                     -- EV/EBITDA
    DIV_YIELD           NUMBER(8,4),                      -- 배당수익률(%)

    -- 수익성/재무
    EPS                 NUMBER(18,4),                     -- 주당순이익
    BPS                 NUMBER(18,4),                     -- 주당순자산
    MARKET_CAP          NUMBER(20,0),                     -- 시가총액
    ROE                 NUMBER(10,4),                     -- 자기자본이익률(%)
    ROA                 NUMBER(10,4),                     -- 총자산이익률(%)
    DEBT_RATIO          NUMBER(10,4),                     -- 부채비율(%)
    BETA                NUMBER(8,4),                      -- 베타

    SOURCE              VARCHAR(20),                      -- 데이터 소스 (KFP 등)
    LOADED_AT           TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9))),
    UNIQUE (BASE_DT, SECURITY_ID)
);

-- FND105: 펀드 헷지현황 (원본: R5302)
CREATE TABLE IF NOT EXISTS FND105_FUND_HEDGE (
    ID                      CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT                 DATE            NOT NULL,
    FUND_ID                 CHAR(26)     NOT NULL REFERENCES FND000_FUND(ID),
    CCY                     VARCHAR(10),                  -- 통화종류
    EXPOSURE_T1             NUMBER(18,0),                 -- 익스포져(T-1)
    EXPOSURE_CHG            NUMBER(18,0),                 -- 익스포저변화
    TRADE_DT_T1             DATE,                         -- 매매일(T-1)
    TRADE_AMT_T             NUMBER(18,0),                 -- 매매금액(T)
    EXPOSURE_T              NUMBER(18,0),                 -- 익스포저(T)
    EXPOSURE_T5             NUMBER(18,0),                 -- 익스포저(T+5)
    RECEIVABLE_T            NUMBER(18,0),                 -- 미수입금(T)
    PAYABLE_T               NUMBER(18,0),                 -- 미지급금(T)
    NET_RECEIVABLE_T        NUMBER(18,0),                 -- 미수입금-미지급금(T)
    AVAIL_CASH_T1           NUMBER(18,0),                 -- 가용현금(T+1)
    TOTAL_HEDGE_AMT         NUMBER(18,0),                 -- 총헷지금액
    FWD_CONTRACT_AMT        NUMBER(18,0),                 -- 선도계약금액
    FUT_CONTRACT_AMT        NUMBER(18,0),                 -- 선물계약금액
    HEDGE_RATIO_T1          NUMBER(10,6),                 -- 헷지비율(T-1)
    HEDGE_RATIO_T           NUMBER(10,6),                 -- 헷지비율(T)
    HEDGE_RATIO_T5          NUMBER(10,6),                 -- 헷지비율(T+5)
    FWD_DAILY_PL            NUMBER(18,0),                 -- 선도일일손익
    FUT_DAILY_PL            NUMBER(18,0),                 -- 선물일일손익
    FWD_CUM_PL              NUMBER(18,0),                 -- 선도누적손익
    FUT_CUM_PL              NUMBER(18,0),                 -- 선물누적손익
    FX_RATE                 NUMBER(18,6),                 -- 당일환율
    TOTAL_HEDGE_RATIO_T1    NUMBER(10,6),                 -- 총헷지비율(T-1)
    TOTAL_HEDGE_RATIO_T     NUMBER(10,6),                 -- 총헷지비율(T)
    REP_CCY                 VARCHAR(10),                  -- 대표통화
    STOCK_MKT_T             NUMBER(18,0),                 -- 주식평가금액(T)
    STOCK_MKT_T1            NUMBER(18,0),                 -- 주식평가금액(T-1)
    STOCK_CHG               NUMBER(18,0),                 -- 주식평가금액증감분
    FUT_MARGIN_T            NUMBER(18,0),                 -- 선물증거금(T)
    FUT_MARGIN_T1           NUMBER(18,0),                 -- 선물증거금(T-1)
    FUT_MARGIN_CHG          NUMBER(18,0),                 -- 선물증거금증감분(T-1)
    CASH_T                  NUMBER(18,0),                 -- 현금(T)
    CASH_T1                 NUMBER(18,0),                 -- 현금(T-1)
    CASH_CHG                NUMBER(18,0),                 -- 현금증감분(T-1)
    BOND_T                  NUMBER(18,0),                 -- 채권(T)
    BOND_T1                 NUMBER(18,0),                 -- 채권(T-1)
    BOND_CHG                NUMBER(18,0),                 -- 채권증감분(T-1)
    FUND_T                  NUMBER(18,0),                 -- 수익증권(T)
    FUND_T1                 NUMBER(18,0),                 -- 수익증권(T-1)
    FUND_CHG                NUMBER(18,0),                 -- 수익증권증감분(T-1)
    FC_LENDING              NUMBER(18,0),                 -- 외화대여금
    UNREF_FX_AMT            NUMBER(18,0),                 -- 미반영환전금액
    CASH_T8                 NUMBER(18,0),                 -- CASH(T+8)
    TRADE_AMT_SUM_T1        NUMBER(18,0),                 -- 매매대금합(T+1)
    LOADED_AT               TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9)))
);

-- ==========================================================
-- 300대: 펀드 특성/등급
-- ==========================================================

-- FND300: 펀드위험등급 (원본: R8103)
CREATE TABLE IF NOT EXISTS FND300_FUND_RISK_GRADE (
    ID                      CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT                 DATE            NOT NULL,
    FUND_ID                 CHAR(26)     NOT NULL REFERENCES FND000_FUND(ID),
    OFFER_TYPE              VARCHAR(30),                  -- 모집유형
    INCEPTION_DT            DATE,                         -- 설정일
    SETTLE_DT               DATE,                         -- 결산일
    CALC_BASE_DT            DATE,                         -- 산출기준일
    VOL_3Y                  NUMBER(10,6),                 -- 최근 3년 변동성
    RISK_GRADE              NUMBER(2,0),                  -- 현재등급
    -- 직전 값은 LAG() 윈도우 함수로 조회 가능하므로 저장하지 않음
    KFIA_CLASS              VARCHAR(100),                 -- 협회14차분류
    LOADED_AT               TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9))),
    UNIQUE (BASE_DT, FUND_ID)
);

-- ==========================================================
-- 400대: Peer 비교 (외부 공시)
-- ==========================================================

-- FND400: 생보협회 변액보험 펀드 공시 (peer 비교용)
CREATE TABLE IF NOT EXISTS FND400_PEER_FUND (
    ID                  CHAR(26)     NOT NULL PRIMARY KEY,
    BASE_DT             DATE            NOT NULL,
    INSURER             VARCHAR(50)     NOT NULL,             -- 보험사명
    FUND_CD             VARCHAR(20)     NOT NULL,             -- 펀드코드
    FUND_NM             VARCHAR(200),                         -- 펀드명
    INCEPTION_DT        DATE,                                 -- 설정일
    NAV                 NUMBER(18,4),                         -- 기준가격(원)
    RET_1Y              NUMBER(10,4),                         -- 수익률 1년(%)
    RET_3Y              NUMBER(10,4),                         -- 수익률 3년(%)
    RET_5Y              NUMBER(10,4),                         -- 수익률 5년(%)
    RET_7Y              NUMBER(10,4),                         -- 수익률 7년(%)
    RET_10Y             NUMBER(10,4),                         -- 수익률 10년(%)
    RET_15Y             NUMBER(10,4),                         -- 수익률 15년(%)
    RET_CUM             NUMBER(10,4),                         -- 수익률 누적(%)
    FEE_MGMT            NUMBER(8,4),                          -- 보수 운영(%)
    FEE_MANDATE         NUMBER(8,4),                          -- 보수 일임(%)
    FEE_CUSTODY         NUMBER(8,4),                          -- 보수 수탁(%)
    FEE_ADMIN           NUMBER(8,4),                          -- 보수 사무(%)
    FEE_TOTAL           NUMBER(8,4),                          -- 보수 합계(%)
    ALLOC_STOCK         NUMBER(8,4),                          -- 자산구성 주식(%)
    ALLOC_BOND          NUMBER(8,4),                          -- 자산구성 채권(%)
    ALLOC_FUND          NUMBER(8,4),                          -- 자산구성 수익증권(%)
    ALLOC_CASH          NUMBER(8,4),                          -- 자산구성 유동성(%)
    ALLOC_ETC           NUMBER(8,4),                          -- 자산구성 기타(%)
    CLASS_CD            VARCHAR(30),                          -- 펀드분류코드
    CLASS_LARGE         VARCHAR(30),                          -- 대유형
    CLASS_SMALL         VARCHAR(30),                          -- 소유형
    NET_ASSET           NUMBER(18,4),                         -- 순자산액(억원)
    ASSET_MGR           VARCHAR(300),                         -- 운용사
    CUSTODIAN           VARCHAR(50),                          -- 수탁사
    FEE_ETC             NUMBER(8,4),                          -- 기타비용(%)
    FEE_FOF             NUMBER(8,4),                          -- 재간접펀드비용(%)
    LOADED_AT           TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9))),
    UNIQUE (BASE_DT, FUND_CD)
);

-- ==========================================================
-- 900대: 참조/코드 테이블
-- ==========================================================

-- FND900: 거래처(증권사/은행/운용사) 마스터
CREATE TABLE IF NOT EXISTS FND900_BROKER (
    ID              CHAR(26)     NOT NULL PRIMARY KEY,
    BROKER_CD       VARCHAR(10)     NOT NULL UNIQUE,
    BROKER_NM       VARCHAR(100),
    BROKER_TYPE     VARCHAR(20),                              -- 증권사/은행/운용사
    LOADED_AT       TIMESTAMP_TZ(9) DEFAULT CONVERT_TIMEZONE('Asia/Seoul', CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_TZ(9)))
);
