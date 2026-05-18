"""한국 시총 상위 50 + 미국 S&P500 시총 상위 50 종목 백필 / 일간 수집.

기존 14개 ST_* (collect_market.py TICKERS["stocks"]) 와 함께 시계열은 통합 적재되지만
dashboard (data 탭) 에는 ST_ORDER 화이트리스트로 노출 통제 (generate.py) 한다.
검증·Story 본문 매칭은 verify_report_numbers.py 의 _STOCK_ALIASES 가 담당.

선정 기준: 2026-05-07 시점 시총 상위 50 (보통주 / 우선주 제외).
- 한국: FinanceDataReader StockListing("KOSPI") 의 Marcap 정렬 상위 50
- 미국: stockanalysis.com S&P500 시총 정렬 상위 50 (GOOGL/GOOG 같은 듀얼 클래스는 1개로)

기존 ST_* 와 중복되는 종목 (Samsung, NVIDIA, Apple 등) 은 기존 코드 재사용.

Usage:
    python -m collectors.stocks_universe --start 2010-01-01           # 전체 백필
    python -m collectors.stocks_universe --kr-only --start 2020-01-01 # 한국만
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

try:
    from .io_utils import load_csv_dedup, append_save_csv
except ImportError:
    from io_utils import load_csv_dedup, append_save_csv

ROOT = Path(__file__).resolve().parent.parent
MARKET_CSV = ROOT / "history" / "market_data.csv"


# ── 종목 유니버스 ─────────────────────────────────────────────────
# (indicator_code, yf_ticker, ticker_name, display_order, name_ko, name_en)
# ticker_name 은 CSV TICKER 컬럼 + result dict key 로 쓰임. 기존 ST_* 와 컨벤션 맞춤.
# 기존 ST_* (collect_market.py) 에 이미 있는 종목은 INDICATOR_CODE 재사용 표시.

# 한국 KOSPI 시총 상위 50 (보통주, 2026-05-07 기준)
# 기존: ST_SAMSUNG (005930) 만 중복 → 신규 49개. 신규 코드는 ST_KR_<6자리>.
KR_TOP50: list[tuple[str, str, str, int, str, str]] = [
    # (indicator_code, yf_ticker, ticker_name, display_order, name_ko, name_en)
    ("ST_SAMSUNG",     "005930.KS", "Samsung",         309, "삼성전자",            "Samsung Electronics"),  # 기존 유지
    ("ST_KR_000660",   "000660.KS", "SK Hynix",        380, "SK하이닉스",          "SK Hynix"),
    ("ST_KR_402340",   "402340.KS", "SK Square",       381, "SK스퀘어",            "SK Square"),
    ("ST_KR_373220",   "373220.KS", "LG Energy Solution", 382, "LG에너지솔루션",   "LG Energy Solution"),
    ("ST_KR_005380",   "005380.KS", "Hyundai Motor",   383, "현대차",              "Hyundai Motor"),
    ("ST_KR_034020",   "034020.KS", "Doosan Enerbility", 384, "두산에너빌리티",    "Doosan Enerbility"),
    ("ST_KR_012450",   "012450.KS", "Hanwha Aerospace",385, "한화에어로스페이스",  "Hanwha Aerospace"),
    ("ST_KR_207940",   "207940.KS", "Samsung Biologics", 386, "삼성바이오로직스",  "Samsung Biologics"),
    ("ST_KR_009150",   "009150.KS", "Samsung Electro-Mechanics", 387, "삼성전기",  "Samsung Electro-Mechanics"),
    ("ST_KR_329180",   "329180.KS", "HD Hyundai Heavy",388, "HD현대중공업",        "HD Hyundai Heavy Industries"),
    ("ST_KR_028260",   "028260.KS", "Samsung C&T",     389, "삼성물산",            "Samsung C&T"),
    ("ST_KR_000270",   "000270.KS", "Kia",             390, "기아",                "Kia"),
    ("ST_KR_032830",   "032830.KS", "Samsung Life",    391, "삼성생명",            "Samsung Life Insurance"),
    ("ST_KR_105560",   "105560.KS", "KB Financial",    392, "KB금융",              "KB Financial Group"),
    ("ST_KR_006400",   "006400.KS", "Samsung SDI",     393, "삼성SDI",             "Samsung SDI"),
    ("ST_KR_267260",   "267260.KS", "HD Hyundai Electric", 394, "HD현대일렉트릭",  "HD Hyundai Electric"),
    ("ST_KR_010120",   "010120.KS", "LS Electric",     395, "LS ELECTRIC",         "LS Electric"),
    ("ST_KR_006800",   "006800.KS", "Mirae Asset Securities", 396, "미래에셋증권", "Mirae Asset Securities"),
    ("ST_KR_055550",   "055550.KS", "Shinhan Financial",397, "신한지주",           "Shinhan Financial Group"),
    ("ST_KR_068270",   "068270.KS", "Celltrion",       398, "셀트리온",            "Celltrion"),
    ("ST_KR_298040",   "298040.KS", "Hyosung Heavy",   399, "효성중공업",          "Hyosung Heavy Industries"),
    ("ST_KR_005490",   "005490.KS", "POSCO Holdings",  400, "POSCO홀딩스",         "POSCO Holdings"),
    ("ST_KR_042660",   "042660.KS", "Hanwha Ocean",    401, "한화오션",            "Hanwha Ocean"),
    ("ST_KR_012330",   "012330.KS", "Hyundai Mobis",   402, "현대모비스",          "Hyundai Mobis"),
    ("ST_KR_034730",   "034730.KS", "SK Inc",          403, "SK",                  "SK Inc"),
    ("ST_KR_042700",   "042700.KS", "Hanmi Semiconductor", 404, "한미반도체",      "Hanmi Semiconductor"),
    ("ST_KR_010130",   "010130.KS", "Korea Zinc",      405, "고려아연",            "Korea Zinc"),
    ("ST_KR_086790",   "086790.KS", "Hana Financial",  406, "하나금융지주",        "Hana Financial Group"),
    ("ST_KR_035420",   "035420.KS", "NAVER",           407, "NAVER",               "Naver"),
    ("ST_KR_009540",   "009540.KS", "HD Korea Shipbuilding", 408, "HD한국조선해양", "HD Korea Shipbuilding & Offshore Engineering"),
    ("ST_KR_051910",   "051910.KS", "LG Chem",         409, "LG화학",              "LG Chem"),
    ("ST_KR_000150",   "000150.KS", "Doosan",          410, "두산",                "Doosan"),
    ("ST_KR_015760",   "015760.KS", "KEPCO",           411, "한국전력",            "Korea Electric Power"),
    ("ST_KR_064350",   "064350.KS", "Hyundai Rotem",   412, "현대로템",            "Hyundai Rotem"),
    ("ST_KR_010140",   "010140.KS", "Samsung Heavy",   413, "삼성중공업",          "Samsung Heavy Industries"),
    ("ST_KR_003670",   "003670.KS", "POSCO Future M",  414, "포스코퓨처엠",        "POSCO Future M"),
    ("ST_KR_066570",   "066570.KS", "LG Electronics",  415, "LG전자",              "LG Electronics"),
    ("ST_KR_096770",   "096770.KS", "SK Innovation",   416, "SK이노베이션",        "SK Innovation"),
    ("ST_KR_316140",   "316140.KS", "Woori Financial", 417, "우리금융지주",        "Woori Financial Group"),
    ("ST_KR_272210",   "272210.KS", "Hanwha Systems",  418, "한화시스템",          "Hanwha Systems"),
    ("ST_KR_267250",   "267250.KS", "HD Hyundai",      419, "HD현대",              "HD Hyundai"),
    ("ST_KR_079550",   "079550.KS", "LIG Defense",     420, "LIG디펜스앤에어로스페이스", "LIG Defense and Aerospace"),
    ("ST_KR_000810",   "000810.KS", "Samsung Fire",    421, "삼성화재",            "Samsung Fire & Marine"),
    ("ST_KR_017670",   "017670.KS", "SK Telecom",      422, "SK텔레콤",            "SK Telecom"),
    ("ST_KR_035720",   "035720.KS", "Kakao",           423, "카카오",              "Kakao"),
    ("ST_KR_033780",   "033780.KS", "KT&G",            424, "KT&G",                "KT&G"),
    ("ST_KR_011200",   "011200.KS", "HMM",             425, "HMM",                 "HMM"),
    ("ST_KR_138040",   "138040.KS", "Meritz Financial",426, "메리츠금융지주",      "Meritz Financial Group"),
    ("ST_KR_000720",   "000720.KS", "Hyundai E&C",     427, "현대건설",            "Hyundai Engineering & Construction"),
    ("ST_KR_024110",   "024110.KS", "IBK",             428, "기업은행",            "Industrial Bank of Korea"),
]

# 미국 S&P500 시총 상위 50 (2026-05-07 기준)
# 기존: NVDA, GOOGL, AAPL, MSFT, AMZN, AVGO, META, TSLA, PLTR (9개) → 코드 재사용.
US_TOP50: list[tuple[str, str, str, int, str]] = [
    # (indicator_code, yf_ticker, ticker_name, display_order, name_en)
    ("ST_NVDA",     "NVDA",  "NVIDIA",          300, "NVIDIA Corporation"),       # 기존
    ("ST_GOOGL",    "GOOGL", "Alphabet",        302, "Alphabet"),                  # 기존
    ("ST_AAPL",     "AAPL",  "Apple",           305, "Apple"),                     # 기존
    ("ST_MSFT",     "MSFT",  "Microsoft",       306, "Microsoft"),                 # 기존
    ("ST_AMZN",     "AMZN",  "Amazon",          303, "Amazon.com"),                # 기존
    ("ST_AVGO",     "AVGO",  "Broadcom",        301, "Broadcom"),                  # 기존
    ("ST_META",     "META",  "META",            304, "Meta Platforms"),            # 기존
    ("ST_TSLA",     "TSLA",  "Tesla",           307, "Tesla"),                     # 기존
    ("ST_PLTR",     "PLTR",  "Palantir",        310, "Palantir Technologies"),     # 기존
    ("ST_WMT",      "WMT",   "Walmart",         320, "Walmart"),
    ("ST_BRK_B",    "BRK-B", "Berkshire",       321, "Berkshire Hathaway"),
    ("ST_LLY",      "LLY",   "Eli Lilly",       322, "Eli Lilly"),
    ("ST_JPM",      "JPM",   "JPMorgan",        323, "JPMorgan Chase"),
    ("ST_MU",       "MU",    "Micron",          324, "Micron Technology"),
    ("ST_AMD",      "AMD",   "AMD",             325, "Advanced Micro Devices"),
    ("ST_XOM",      "XOM",   "ExxonMobil",      326, "Exxon Mobil"),
    ("ST_V",        "V",     "Visa",            327, "Visa"),
    ("ST_INTC",     "INTC",  "Intel",           328, "Intel"),
    ("ST_ORCL",     "ORCL",  "Oracle",          329, "Oracle"),
    ("ST_JNJ",      "JNJ",   "J&J",             330, "Johnson & Johnson"),
    ("ST_COST",     "COST",  "Costco",          331, "Costco"),
    ("ST_MA",       "MA",    "Mastercard",      332, "Mastercard"),
    ("ST_CAT",      "CAT",   "Caterpillar",     333, "Caterpillar"),
    ("ST_BAC",      "BAC",   "Bank of America", 334, "Bank of America"),
    ("ST_NFLX",     "NFLX",  "Netflix",         335, "Netflix"),
    ("ST_LRCX",     "LRCX",  "Lam Research",    336, "Lam Research"),
    ("ST_CVX",      "CVX",   "Chevron",         337, "Chevron"),
    ("ST_ABBV",     "ABBV",  "AbbVie",          338, "AbbVie"),
    ("ST_CSCO",     "CSCO",  "Cisco",           339, "Cisco Systems"),
    ("ST_PG",       "PG",    "P&G",             340, "Procter & Gamble"),
    ("ST_KO",       "KO",    "Coca-Cola",       341, "Coca-Cola"),
    ("ST_AMAT",     "AMAT",  "Applied Materials", 342, "Applied Materials"),
    ("ST_UNH",      "UNH",   "UnitedHealth",    343, "UnitedHealth"),
    ("ST_HD",       "HD",    "Home Depot",      344, "Home Depot"),
    ("ST_GE",       "GE",    "GE Aerospace",    345, "GE Aerospace"),
    ("ST_MS",       "MS",    "Morgan Stanley",  346, "Morgan Stanley"),
    ("ST_GEV",      "GEV",   "GE Vernova",      347, "GE Vernova"),
    ("ST_GS",       "GS",    "Goldman Sachs",   348, "Goldman Sachs"),
    ("ST_MRK",      "MRK",   "Merck",           349, "Merck"),
    ("ST_PM",       "PM",    "Philip Morris",   350, "Philip Morris International"),
    ("ST_TXN",      "TXN",   "Texas Instruments", 351, "Texas Instruments"),
    ("ST_WFC",      "WFC",   "Wells Fargo",     352, "Wells Fargo"),
    ("ST_RTX",      "RTX",   "RTX",             353, "RTX"),
    ("ST_KLAC",     "KLAC",  "KLA",             354, "KLA"),
    ("ST_LIN",      "LIN",   "Linde",           355, "Linde"),
    ("ST_AXP",      "AXP",   "American Express",356, "American Express"),
    ("ST_C",        "C",     "Citigroup",       357, "Citigroup"),
    ("ST_PEP",      "PEP",   "PepsiCo",         358, "PepsiCo"),
    ("ST_IBM",      "IBM",   "IBM",             359, "IBM"),
    ("ST_TMUS",     "TMUS",  "T-Mobile",        360, "T-Mobile US"),
]

# 아시아 종목 (history/아시아종목.xlsx 2026-05-14 기준).
# 국가별 시총 상위 N: 중국 30 + 일본 20 + 대만 5 + 인도 10 = 65종.
# - 기존 ST_TENCENT/ST_BABA/ST_MEITUAN 3종은 HK 코드 재사용 (yf_ticker .HK)
# - TSMC 대만 원본(2330.TW) 은 신규 코드 (ST_AS_2330_TW). TSM ADR(ST_TSMC) 는 ASIA_EXTRAS 로 별도 유지.
# - .SH 거래소 → yfinance .SS 로 매핑. "TSMC TW" 는 ST_ORDER 의 "TSMC"(ADR) 와 이름 충돌 방지.
ASIA_TOP: list[tuple[str, str, str, int, str, str]] = [
    # (indicator_code, yf_ticker, ticker_name, display_order, country, name_en)
    # --- China Top 30 (비중 24.67%) ---
    ("ST_TENCENT",         "0700.HK",      "Tencent",               500, "China",  "Tencent Holdings"),  # 기존 (HK)
    ("ST_AS_688256_SS",    "688256.SS",    "Cambricon Tech",        501, "China",  "Cambricon Technologies"),
    ("ST_BABA",            "9988.HK",      "Alibaba",               502, "China",  "Alibaba Group"),     # 기존 (HK)
    ("ST_AS_0981_HK",      "0981.HK",      "SMIC",                  503, "China",  "Semiconductor Manufacturing International"),
    ("ST_AS_300750_SZ",    "300750.SZ",    "CATL",                  504, "China",  "Contemporary Amperex Technology"),
    ("ST_AS_1211_HK",      "1211.HK",      "BYD",                   505, "China",  "BYD Company"),
    ("ST_AS_2318_HK",      "2318.HK",      "Ping An Insurance",     506, "China",  "Ping An Insurance"),
    ("ST_AS_002371_SZ",    "002371.SZ",    "NAURA Tech",            507, "China",  "NAURA Technology Group"),
    ("ST_AS_688041_SS",    "688041.SS",    "Hygon Info Tech",       508, "China",  "Hygon Information Technology"),
    ("ST_AS_603986_SS",    "603986.SS",    "GigaDevice",            509, "China",  "GigaDevice Semiconductor"),
    ("ST_AS_688012_SS",    "688012.SS",    "AMEC",                  510, "China",  "Advanced Micro-Fabrication Equipment"),
    ("ST_AS_688008_SS",    "688008.SS",    "Montage Tech",          511, "China",  "Montage Technology"),
    ("ST_AS_1810_HK",      "1810.HK",      "Xiaomi",                512, "China",  "Xiaomi"),
    ("ST_AS_1347_HK",      "1347.HK",      "Hua Hong Semi",         513, "China",  "Hua Hong Semiconductor"),
    ("ST_AS_300308_SZ",    "300308.SZ",    "Zhongji Innolight",     514, "China",  "Zhongji Innolight"),
    ("ST_AS_002028_SZ",    "002028.SZ",    "Sieyuan Electric",      515, "China",  "Sieyuan Electric"),
    ("ST_AS_FUTU",         "FUTU",         "Futu Holdings",         516, "China",  "Futu Holdings"),
    ("ST_AS_688525_SS",    "688525.SS",    "Biwin Storage",         517, "China",  "Biwin Storage Technology"),
    ("ST_AS_300604_SZ",    "300604.SZ",    "Hangzhou Chang Chuan",  518, "China",  "Hangzhou Chang Chuan Technology"),
    ("ST_AS_9660_HK",      "9660.HK",      "Horizon Robotics",      519, "China",  "Horizon Robotics"),
    ("ST_AS_688072_SS",    "688072.SS",    "Piotech",               520, "China",  "Piotech"),
    ("ST_AS_601869_SS",    "601869.SS",    "Yangtze Optical",       521, "China",  "Yangtze Optical Fibre and Cable"),
    ("ST_AS_301308_SZ",    "301308.SZ",    "Longsys",               522, "China",  "Shenzhen Longsys Electronics"),
    ("ST_AS_002156_SZ",    "002156.SZ",    "TongFu",                523, "China",  "Tongfu Microelectronics"),
    ("ST_AS_688120_SS",    "688120.SS",    "Hwatsing",              524, "China",  "Hwatsing Technology"),
    ("ST_AS_300316_SZ",    "300316.SZ",    "Jingsheng Mech",        525, "China",  "Zhejiang Jingsheng Mechanical & Electrical"),
    ("ST_MEITUAN",         "3690.HK",      "Meituan",               526, "China",  "Meituan"),           # 기존 (HK)
    ("ST_AS_9888_HK",      "9888.HK",      "Baidu",                 527, "China",  "Baidu"),
    ("ST_AS_9999_HK",      "9999.HK",      "NetEase",               528, "China",  "NetEase"),
    ("ST_AS_2259_HK",      "2259.HK",      "Zijin Gold Intl",       529, "China",  "Zijin Mining Group"),

    # --- Japan Top 20 (비중 4.26%) ---
    ("ST_AS_8411_T",       "8411.T",       "Mizuho FG",             530, "Japan",  "Mizuho Financial Group"),
    ("ST_AS_8035_T",       "8035.T",       "Tokyo Electron",        531, "Japan",  "Tokyo Electron"),
    ("ST_AS_6857_T",       "6857.T",       "Advantest",             532, "Japan",  "Advantest"),
    ("ST_AS_8802_T",       "8802.T",       "Mitsubishi Estate",     533, "Japan",  "Mitsubishi Estate"),
    ("ST_AS_6503_T",       "6503.T",       "Mitsubishi Electric",   534, "Japan",  "Mitsubishi Electric"),
    ("ST_AS_6146_T",       "6146.T",       "Disco",                 535, "Japan",  "Disco Corporation"),
    ("ST_AS_7013_T",       "7013.T",       "IHI",                   536, "Japan",  "IHI Corporation"),
    ("ST_AS_6723_T",       "6723.T",       "Renesas",               537, "Japan",  "Renesas Electronics"),
    ("ST_AS_6501_T",       "6501.T",       "Hitachi",               538, "Japan",  "Hitachi"),
    ("ST_AS_6920_T",       "6920.T",       "Lasertec",              539, "Japan",  "Lasertec"),
    ("ST_AS_4004_T",       "4004.T",       "Resonac",               540, "Japan",  "Resonac Holdings"),
    ("ST_AS_7203_T",       "7203.T",       "Toyota",                541, "Japan",  "Toyota Motor"),
    ("ST_AS_4502_T",       "4502.T",       "Takeda",                542, "Japan",  "Takeda Pharmaceutical"),
    ("ST_AS_3382_T",       "3382.T",       "Seven & i",             543, "Japan",  "Seven & i Holdings"),
    ("ST_AS_7735_T",       "7735.T",       "SCREEN",                544, "Japan",  "SCREEN Holdings"),
    ("ST_AS_6963_T",       "6963.T",       "Rohm",                  545, "Japan",  "Rohm"),
    ("ST_AS_3436_T",       "3436.T",       "SUMCO",                 546, "Japan",  "SUMCO"),
    ("ST_AS_6525_T",       "6525.T",       "Kokusai Electric",      547, "Japan",  "Kokusai Electric"),
    ("ST_AS_6861_T",       "6861.T",       "Keyence",               548, "Japan",  "Keyence"),
    ("ST_AS_6758_T",       "6758.T",       "Sony",                  549, "Japan",  "Sony Group"),

    # --- Taiwan Top 5 (비중 3.72%) — TSMC 대만 원본 (TSM ADR 은 ASIA_EXTRAS 참조) ---
    ("ST_AS_2330_TW",      "2330.TW",      "TSMC TW",               550, "Taiwan", "Taiwan Semiconductor (TW listing)"),
    ("ST_AS_2308_TW",      "2308.TW",      "Delta Electronics",     551, "Taiwan", "Delta Electronics"),
    ("ST_AS_2317_TW",      "2317.TW",      "Hon Hai/Foxconn",       552, "Taiwan", "Hon Hai Precision (Foxconn)"),
    ("ST_AS_3711_TW",      "3711.TW",      "ASE Tech",              553, "Taiwan", "ASE Technology Holding"),
    ("ST_AS_3017_TW",      "3017.TW",      "AVC",                   554, "Taiwan", "Asia Vital Components"),

    # --- India Top 10 (비중 4.89%) ---
    ("ST_AS_HDFCBANK_NS",  "HDFCBANK.NS",  "HDFC Bank",             555, "India",  "HDFC Bank"),
    ("ST_AS_ICICIBANK_NS", "ICICIBANK.NS", "ICICI Bank",            556, "India",  "ICICI Bank"),
    ("ST_AS_BHARTIARTL_NS","BHARTIARTL.NS","Bharti Airtel",         557, "India",  "Bharti Airtel"),
    ("ST_AS_RELIANCE_NS",  "RELIANCE.NS",  "Reliance",              558, "India",  "Reliance Industries"),
    ("ST_AS_TITAN_NS",     "TITAN.NS",     "Titan",                 559, "India",  "Titan Company"),
    ("ST_AS_INFY_NS",      "INFY.NS",      "Infosys",               560, "India",  "Infosys"),
    ("ST_AS_POWERGRID_NS", "POWERGRID.NS", "Power Grid",            561, "India",  "Power Grid Corporation of India"),
    ("ST_AS_AXISBANK_NS",  "AXISBANK.NS",  "Axis Bank",             562, "India",  "Axis Bank"),
    ("ST_AS_APOLLOHOSP_NS","APOLLOHOSP.NS","Apollo Hospitals",      563, "India",  "Apollo Hospitals Enterprise"),
    ("ST_AS_SBILIFE_NS",   "SBILIFE.NS",   "SBI Life",              564, "India",  "SBI Life Insurance"),

    # === asia-weekly 확장 (2026-05-18 기준) — 미매칭 65종목 추가 ============================
    # 출처: history/아시아종목.xlsx — 운용 유니버스 보강
    # yfinance test 통과 종목만 (Tata Motors TATAMOTORS.NS · OOIL 은 yf 미지원으로 제외)
    # --- Vietnam Top 10 (비중 ~0.36%) ---
    ("ST_AS_HPG_VN",       "HPG.VN",       "Hoa Phat",              600, "Vietnam",  "Hoa Phat Group"),
    ("ST_AS_CTG_VN",       "CTG.VN",       "Vietinbank",            601, "Vietnam",  "VietinBank"),
    ("ST_AS_MBB_VN",       "MBB.VN",       "MB Bank",               602, "Vietnam",  "Military Commercial Joint Stock Bank"),
    ("ST_AS_MWG_VN",       "MWG.VN",       "Mobile World",          603, "Vietnam",  "Mobile World Investment"),
    ("ST_AS_MSN_VN",       "MSN.VN",       "Masan Group",           604, "Vietnam",  "Masan Group"),
    ("ST_AS_TCB_VN",       "TCB.VN",       "Techcombank",           605, "Vietnam",  "Techcombank"),
    ("ST_AS_BVH_VN",       "BVH.VN",       "BaoViet",               606, "Vietnam",  "BaoViet Holdings"),
    ("ST_AS_VPB_VN",       "VPB.VN",       "VPBank",                607, "Vietnam",  "VPBank"),
    ("ST_AS_VPL_VN",       "VPL.VN",       "Vinpearl",              608, "Vietnam",  "Vinpearl"),
    ("ST_AS_VCB_VN",       "VCB.VN",       "Vietcombank",           609, "Vietnam",  "Vietcombank"),

    # --- India 확장 18종 (NIFTY 추가 + 컨슈머·자동차·인프라) ---
    ("ST_AS_INDHOTEL_NS",  "INDHOTEL.NS",  "Indian Hotels",         610, "India",  "Indian Hotels (Tata)"),
    ("ST_AS_HINDUNILVR_NS","HINDUNILVR.NS","HUL",                   611, "India",  "Hindustan Unilever"),
    ("ST_AS_MARUTI_NS",    "MARUTI.NS",    "Maruti Suzuki",         612, "India",  "Maruti Suzuki"),
    ("ST_AS_BAJAJ_AUTO_NS","BAJAJ-AUTO.NS","Bajaj Auto",            613, "India",  "Bajaj Auto"),
    ("ST_AS_VBL_NS",       "VBL.NS",       "Varun Beverages",       614, "India",  "Varun Beverages"),
    ("ST_AS_NESTLEIND_NS", "NESTLEIND.NS", "Nestle India",          615, "India",  "Nestle India"),
    ("ST_AS_EICHERMOT_NS", "EICHERMOT.NS", "Eicher Motors",         616, "India",  "Eicher Motors"),
    ("ST_AS_TVSMOTOR_NS",  "TVSMOTOR.NS",  "TVS Motor",             617, "India",  "TVS Motor"),
    ("ST_AS_TATACONSUM_NS","TATACONSUM.NS","Tata Consumer",         618, "India",  "Tata Consumer Products"),
    ("ST_AS_BRITANNIA_NS", "BRITANNIA.NS", "Britannia",             619, "India",  "Britannia Industries"),
    ("ST_AS_HEROMOTOCO_NS","HEROMOTOCO.NS","Hero MotoCorp",         621, "India",  "Hero MotoCorp"),
    ("ST_AS_BEL_NS",       "BEL.NS",       "Bharat Electronics",    622, "India",  "Bharat Electronics"),
    ("ST_AS_LT_NS",        "LT.NS",        "L&T",                   623, "India",  "Larsen & Toubro"),
    ("ST_AS_SBIN_NS",      "SBIN.NS",      "SBI",                   624, "India",  "State Bank of India"),
    ("ST_AS_MMYT",         "MMYT",         "MakeMyTrip",            625, "India",  "MakeMyTrip"),
    ("ST_AS_ITC_NS",       "ITC.NS",       "ITC",                   626, "India",  "ITC Limited"),
    ("ST_AS_KOTAKBANK_NS", "KOTAKBANK.NS", "Kotak Mahindra",        627, "India",  "Kotak Mahindra Bank"),
    ("ST_AS_BAJFINANCE_NS","BAJFINANCE.NS","Bajaj Finance",         628, "India",  "Bajaj Finance"),

    # --- Indonesia 1종 ---
    ("ST_AS_BMRI_JK",      "BMRI.JK",      "Bank Mandiri",          629, "Indonesia", "Bank Mandiri"),

    # --- Japan 확장 12종 (대형 산업·반도체·IT) ---
    ("ST_AS_6098_T",       "6098.T",       "Recruit",               630, "Japan",  "Recruit Holdings"),
    ("ST_AS_6981_T",       "6981.T",       "Murata",                631, "Japan",  "Murata Manufacturing"),
    ("ST_AS_7974_T",       "7974.T",       "Nintendo",              632, "Japan",  "Nintendo"),
    ("ST_AS_6701_T",       "6701.T",       "NEC",                   633, "Japan",  "NEC Corporation"),
    ("ST_AS_6954_T",       "6954.T",       "Fanuc",                 634, "Japan",  "Fanuc"),
    ("ST_AS_7011_T",       "7011.T",       "MHI",                   635, "Japan",  "Mitsubishi Heavy Industries"),
    ("ST_AS_6702_T",       "6702.T",       "Fujitsu",               636, "Japan",  "Fujitsu"),
    ("ST_AS_6752_T",       "6752.T",       "Panasonic",             637, "Japan",  "Panasonic"),
    ("ST_AS_6762_T",       "6762.T",       "TDK",                   638, "Japan",  "TDK Corporation"),
    ("ST_AS_7012_T",       "7012.T",       "Kawasaki Heavy",        639, "Japan",  "Kawasaki Heavy Industries"),
    ("ST_AS_8058_T",       "8058.T",       "Mitsubishi Corp",       640, "Japan",  "Mitsubishi Corporation"),
    ("ST_AS_8031_T",       "8031.T",       "Mitsui",                641, "Japan",  "Mitsui & Co"),

    # --- China 확장 22종 (HK + A주: 빅테크·EV·반도체) ---
    ("ST_AS_0992_HK",      "0992.HK",      "Lenovo",                642, "China",  "Lenovo Group"),
    ("ST_AS_9618_HK",      "9618.HK",      "JD.com",                643, "China",  "JD.com (HK listing)"),
    ("ST_AS_PDD",          "PDD",          "PDD Holdings",          644, "China",  "PDD Holdings (Pinduoduo)"),
    ("ST_AS_1024_HK",      "1024.HK",      "Kuaishou",              645, "China",  "Kuaishou Technology"),
    ("ST_AS_603019_SS",    "603019.SS",    "Dawning Info",          646, "China",  "Dawning Information Industry"),
    ("ST_AS_002008_SZ",    "002008.SZ",    "Han's Laser",           647, "China",  "Han's Laser Technology"),
    ("ST_AS_0020_HK",      "0020.HK",      "SenseTime",             648, "China",  "SenseTime Group"),
    ("ST_AS_1276_HK",      "1276.HK",      "Jiangsu Hengrui",       649, "China",  "Jiangsu Hengrui Pharma"),
    ("ST_AS_2359_HK",      "2359.HK",      "WuXi AppTec",           650, "China",  "WuXi AppTec"),
    ("ST_AS_9961_HK",      "9961.HK",      "Trip.com",              651, "China",  "Trip.com Group"),
    ("ST_AS_9868_HK",      "9868.HK",      "XPeng",                 652, "China",  "XPeng Motors"),
    ("ST_AS_2015_HK",      "2015.HK",      "Li Auto",               653, "China",  "Li Auto"),
    ("ST_AS_300502_SZ",    "300502.SZ",    "Eoptolink",             654, "China",  "Eoptolink Technology"),
    ("ST_AS_002475_SZ",    "002475.SZ",    "Luxshare",              655, "China",  "Luxshare Precision"),
    ("ST_AS_002415_SZ",    "002415.SZ",    "Hikvision",             656, "China",  "Hangzhou Hikvision"),
    ("ST_AS_000988_SZ",    "000988.SZ",    "Huagong Tech",          657, "China",  "Huagong Tech"),
    ("ST_AS_601100_SS",    "601100.SS",    "Hengli Hydraulic",      658, "China",  "Hengli Hydraulic"),
    ("ST_AS_002050_SZ",    "002050.SZ",    "Sanhua Intelligent",    659, "China",  "Sanhua Intelligent Controls"),
    ("ST_AS_002384_SZ",    "002384.SZ",    "Suzhou Dongshan",       660, "China",  "Suzhou Dongshan Precision"),
    ("ST_AS_000333_SZ",    "000333.SZ",    "Midea Group",           661, "China",  "Midea Group"),
    ("ST_AS_002230_SZ",    "002230.SZ",    "iFlytek",               662, "China",  "iFlytek"),
    ("ST_AS_300124_SZ",    "300124.SZ",    "Inovance",              663, "China",  "Inovance Technology"),

    # --- Australia / Hong Kong 추가 ---
    ("ST_AS_ANZ_AX",       "ANZ.AX",       "ANZ",                   664, "Australia", "ANZ Banking Group"),
    ("ST_AS_1299_HK",      "1299.HK",      "AIA",                   665, "HK",     "AIA Group"),
]

# ASIA 안전망 — TSM (TSMC ADR, USD, NYSE 상장) 은 ST_TSMC 코드 유지.
# ASIA_TOP 의 2330.TW (TWD, 아시아 시간대) 와 별개의 시계열로 보존된다.
ASIA_EXTRAS: list[tuple[str, str, str, int, str, str]] = [
    ("ST_TSMC", "TSM", "TSMC", 449, "Taiwan", "Taiwan Semiconductor (US ADR)"),
]


# yfinance 통화 매핑 (티커 접미사 → ISO 4217)
_SUFFIX_TO_CCY = {
    ".TW": "TWD", ".HK": "HKD", ".SS": "CNY", ".SZ": "CNY",
    ".NS": "INR", ".T":  "JPY", ".AX": "AUD",
    ".VN": "VND", ".JK": "IDR",
}


def _ccy_for(yf_ticker: str) -> str:
    """yfinance ticker 접미사로 통화 추론. 접미사 없으면 USD (US ADR)."""
    for suf, ccy in _SUFFIX_TO_CCY.items():
        if yf_ticker.endswith(suf):
            return ccy
    return "USD"


# 기존 collect_market.py TICKERS["stocks"] 에 이미 있어 stocks_universe 가 백필하지 않는 코드 set
EXISTING_IN_COLLECT_MARKET: set[str] = {
    "ST_NVDA", "ST_AVGO", "ST_GOOGL", "ST_AMZN", "ST_META",
    "ST_AAPL", "ST_MSFT", "ST_TSLA", "ST_TSMC", "ST_SAMSUNG",
    "ST_PLTR", "ST_BABA", "ST_MEITUAN", "ST_TENCENT",
}


def _backfill_targets() -> list[tuple[str, str, str]]:
    """KR + US + ASIA + ASIA_EXTRAS 신규 종목만. 기존 collect_market.py 의 14개는 제외.

    ASIA_EXTRAS (ST_TSMC=TSM) 는 EXISTING_IN_COLLECT_MARKET 에 들어있어 자동 skip 됨.
    returns: [(indicator_code, yf_ticker, ticker_name), ...]
    """
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for code, ticker, name, _order, _name_ko, _name_en in KR_TOP50:
        if code in EXISTING_IN_COLLECT_MARKET or code in seen:
            continue
        out.append((code, ticker, name))
        seen.add(code)
    for code, ticker, name, _order, _name_en in US_TOP50:
        if code in EXISTING_IN_COLLECT_MARKET or code in seen:
            continue
        out.append((code, ticker, name))
        seen.add(code)
    for code, ticker, name, _order, _country, _name_en in ASIA_TOP:
        if code in EXISTING_IN_COLLECT_MARKET or code in seen:
            continue
        out.append((code, ticker, name))
        seen.add(code)
    for code, ticker, name, _order, _country, _name_en in ASIA_EXTRAS:
        if code in EXISTING_IN_COLLECT_MARKET or code in seen:
            continue
        out.append((code, ticker, name))
        seen.add(code)
    return out


def fetch_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    try:
        raw = yf.download(ticker, start=start, end=end,
                          auto_adjust=True, progress=False)
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns={
            "Open": "OPEN", "High": "HIGH", "Low": "LOW",
            "Close": "CLOSE", "Volume": "VOLUME",
        })
        raw.index.name = "DATE"
        return raw[["CLOSE", "OPEN", "HIGH", "LOW", "VOLUME"]].dropna(subset=["CLOSE"])
    except Exception as e:
        print(f"    [ERR] yfinance {ticker}: {e}")
        return None


def collect_stocks_universe(
    start: str = "2010-01-01",
    end: str = "9999-12-31",
    kr_only: bool = False,
    us_only: bool = False,
    asia_only: bool = False,
) -> int:
    market_cols = ["DATE", "INDICATOR_CODE", "CATEGORY", "TICKER",
                   "CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "SOURCE"]
    existing, existing_set = load_csv_dedup(MARKET_CSV, market_cols, parse_dates=True)

    targets = _backfill_targets()
    if kr_only:
        targets = [t for t in targets if t[0].startswith("ST_KR_")]
    elif us_only:
        targets = [t for t in targets if not t[0].startswith(("ST_KR_", "ST_AS_"))]
    elif asia_only:
        targets = [t for t in targets if t[0].startswith("ST_AS_")]

    new_rows: list[dict] = []
    for code, ticker, name in targets:
        print(f"  {code:18s} ({ticker:12s}) ...", end=" ")
        raw = fetch_yfinance(ticker, start, end)
        if raw is None or raw.empty:
            print("no data")
            time.sleep(0.3)
            continue
        added = 0
        for d, row in raw.iterrows():
            key = (d.strftime("%Y-%m-%d"), code)
            if key in existing_set:
                continue
            new_rows.append({
                "DATE":           d.date(),
                "INDICATOR_CODE": code,
                "CATEGORY":       "stocks",
                "TICKER":         name,
                "CLOSE":          round(float(row["CLOSE"]), 4),
                "OPEN":           round(float(row["OPEN"]), 4)   if pd.notna(row["OPEN"])   else None,
                "HIGH":           round(float(row["HIGH"]), 4)   if pd.notna(row["HIGH"])   else None,
                "LOW":            round(float(row["LOW"]), 4)    if pd.notna(row["LOW"])    else None,
                "VOLUME":         int(row["VOLUME"])              if pd.notna(row["VOLUME"]) else None,
                "SOURCE":         "yfinance",
            })
            existing_set.add(key)
            added += 1
        print(f"{added}행")
        time.sleep(0.25)

    n = append_save_csv(MARKET_CSV, existing, new_rows, sort_cols=("INDICATOR_CODE", "DATE"))
    if n:
        print(f"\n  → market_data.csv: {n}행 추가")
    else:
        print("\n  → 신규 데이터 없음")

    try:
        from snowflake_loader import sync_new_rows
        sync_new_rows(new_rows, source="collect_stocks_universe")
    except Exception as e:
        try:
            from snowflake_loader import _alert_failure
            _alert_failure(source="collect_stocks_universe", reason=str(e)[:200])
        except Exception:
            print(f"[SNOWFLAKE] FAILED source=collect_stocks_universe reason={str(e)[:200]}")

    return len(new_rows)


def upsert_mkt000_seed() -> int:
    """MKT000_MARKET_INDICATOR 에 KR_TOP50 + US_TOP50 + ASIA_TOP 신규 종목 dim 행 등록.

    이미 등록된 코드는 건너뜀 (idempotent). 신규 환경 셋업·재현용.
    """
    try:
        from snowflake_loader import get_connection
    except Exception as e:
        print(f"[SEED] snowflake_loader import 실패: {e}")
        return 0

    rows: list[tuple] = []
    seen: set[str] = set()
    for code, yf_ticker, name, order, name_ko, name_en in KR_TOP50:
        if code in EXISTING_IN_COLLECT_MARKET or code in seen:
            continue
        rows.append((code, "STOCK", name, name_ko, name_en, "Korea", "KRW", "pct",
                     "yfinance", yf_ticker, None, None, order, True))
        seen.add(code)
    for code, yf_ticker, name, order, name_en in US_TOP50:
        if code in EXISTING_IN_COLLECT_MARKET or code in seen:
            continue
        rows.append((code, "STOCK", name, name, name_en, "US", "USD", "pct",
                     "yfinance", yf_ticker, None, None, order, True))
        seen.add(code)
    for code, yf_ticker, name, order, country, name_en in ASIA_TOP:
        if code in EXISTING_IN_COLLECT_MARKET or code in seen:
            continue
        rows.append((code, "STOCK", name, name, name_en, country, _ccy_for(yf_ticker), "pct",
                     "yfinance", yf_ticker, None, None, order, True))
        seen.add(code)
    for code, yf_ticker, name, order, country, name_en in ASIA_EXTRAS:
        if code in EXISTING_IN_COLLECT_MARKET or code in seen:
            continue
        rows.append((code, "STOCK", name, name, name_en, country, _ccy_for(yf_ticker), "pct",
                     "yfinance", yf_ticker, None, None, order, True))
        seen.add(code)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT "지표코드" FROM FDE_DB.PUBLIC.MKT000_MARKET_INDICATOR WHERE "카테고리" = \'STOCK\'')
    existing = {r[0] for r in cur.fetchall()}
    new_rows = [r for r in rows if r[0] not in existing]
    if not new_rows:
        cur.close(); conn.close()
        print(f"[SEED] 이미 등록됨 — 신규 0건 (existing STOCK={len(existing)})")
        return 0

    sql = ('INSERT INTO FDE_DB.PUBLIC.MKT000_MARKET_INDICATOR '
           '("지표코드","카테고리","티커","지표명","지표명_EN","하위카테고리","단위","변동단위",'
           ' "소스","소스_티커","소스_폴백","비고","정렬순서","사용여부") '
           'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)')
    cur.executemany(sql, new_rows)
    conn.commit()
    n = cur.rowcount
    cur.close(); conn.close()
    kr_n = sum(1 for r in new_rows if r[5] == "Korea")
    us_n = sum(1 for r in new_rows if r[5] == "US")
    as_n = sum(1 for r in new_rows if r[5] not in ("Korea", "US"))
    print(f"[SEED] MKT000 INSERT {n}행 (KR{kr_n} + US{us_n} + ASIA{as_n})")
    return n


def main():
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="KR Top50 + US S&P500 Top50 + ASIA Top50 종목 수집")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end",   default=today)
    parser.add_argument("--kr-only",   action="store_true")
    parser.add_argument("--us-only",   action="store_true")
    parser.add_argument("--asia-only", action="store_true")
    parser.add_argument("--seed-dim", action="store_true",
                        help="MKT000 dim seed 만 적재하고 종료 (백필 안 함)")
    args = parser.parse_args()

    if args.seed_dim:
        upsert_mkt000_seed()
        return

    print(f"Stocks Universe 수집: {args.start} ~ {args.end}")
    n = collect_stocks_universe(args.start, args.end,
                                kr_only=args.kr_only,
                                us_only=args.us_only,
                                asia_only=args.asia_only)
    print(f"완료: {n}행")


if __name__ == "__main__":
    main()
