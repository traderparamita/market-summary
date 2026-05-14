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

# 아시아 시총 상위 50 (history/아시아종목.xlsx 2026-05-14 기준, 비중 0.23% 이상)
# 기존 ST_TSMC/ST_TENCENT/ST_BABA/ST_MEITUAN 4종은 ADR/HK 코드 재사용 (yf_ticker 도 기존 유지).
# 나머지 46종은 ST_AS_<safe_ticker> 신규 코드. .SH 거래소는 yfinance .SS 로 매핑.
ASIA_TOP50: list[tuple[str, str, str, int, str, str]] = [
    # (indicator_code, yf_ticker, ticker_name, display_order, country, name_en)
    ("ST_TSMC",            "TSM",          "TSMC",                  450, "Taiwan",    "Taiwan Semiconductor"),   # 기존 (ADR USD)
    ("ST_TENCENT",         "0700.HK",      "Tencent",               451, "China",     "Tencent Holdings"),       # 기존 (HK)
    ("ST_AS_688256_SS",    "688256.SS",    "Cambricon Tech",        452, "China",     "Cambricon Technologies"),
    ("ST_BABA",            "9988.HK",      "Alibaba",               453, "China",     "Alibaba Group"),          # 기존 (HK)
    ("ST_AS_0981_HK",      "0981.HK",      "SMIC",                  454, "China",     "Semiconductor Manufacturing International"),
    ("ST_AS_300750_SZ",    "300750.SZ",    "CATL",                  455, "China",     "Contemporary Amperex Technology"),
    ("ST_AS_1211_HK",      "1211.HK",      "BYD",                   456, "China",     "BYD Company"),
    ("ST_AS_2318_HK",      "2318.HK",      "Ping An Insurance",     457, "China",     "Ping An Insurance"),
    ("ST_AS_002371_SZ",    "002371.SZ",    "NAURA Tech",            458, "China",     "NAURA Technology Group"),
    ("ST_AS_688041_SS",    "688041.SS",    "Hygon Info Tech",       459, "China",     "Hygon Information Technology"),
    ("ST_AS_603986_SS",    "603986.SS",    "GigaDevice",            460, "China",     "GigaDevice Semiconductor"),
    ("ST_AS_688012_SS",    "688012.SS",    "AMEC",                  461, "China",     "Advanced Micro-Fabrication Equipment"),
    ("ST_AS_HDFCBANK_NS",  "HDFCBANK.NS",  "HDFC Bank",             462, "India",     "HDFC Bank"),
    ("ST_AS_ICICIBANK_NS", "ICICIBANK.NS", "ICICI Bank",            463, "India",     "ICICI Bank"),
    ("ST_AS_688008_SS",    "688008.SS",    "Montage Tech",          464, "China",     "Montage Technology"),
    ("ST_AS_1810_HK",      "1810.HK",      "Xiaomi",                465, "China",     "Xiaomi"),
    ("ST_AS_BHARTIARTL_NS","BHARTIARTL.NS","Bharti Airtel",         466, "India",     "Bharti Airtel"),
    ("ST_AS_1347_HK",      "1347.HK",      "Hua Hong Semi",         467, "China",     "Hua Hong Semiconductor"),
    ("ST_AS_RELIANCE_NS",  "RELIANCE.NS", "Reliance",               468, "India",     "Reliance Industries"),
    ("ST_AS_300308_SZ",    "300308.SZ",    "Zhongji Innolight",     469, "China",     "Zhongji Innolight"),
    ("ST_AS_TITAN_NS",     "TITAN.NS",     "Titan",                 470, "India",     "Titan Company"),
    ("ST_AS_002028_SZ",    "002028.SZ",    "Sieyuan Electric",      471, "China",     "Sieyuan Electric"),
    ("ST_AS_2308_TW",      "2308.TW",      "Delta Electronics",     472, "Taiwan",    "Delta Electronics"),
    ("ST_AS_FUTU",         "FUTU",         "Futu Holdings",         473, "China",     "Futu Holdings"),
    ("ST_AS_688525_SS",    "688525.SS",    "Biwin Storage",         474, "China",     "Biwin Storage Technology"),
    ("ST_AS_300604_SZ",    "300604.SZ",    "Hangzhou Chang Chuan",  475, "China",     "Hangzhou Chang Chuan Technology"),
    ("ST_AS_9660_HK",      "9660.HK",      "Horizon Robotics",      476, "China",     "Horizon Robotics"),
    ("ST_AS_8411_T",       "8411.T",       "Mizuho FG",             477, "Japan",     "Mizuho Financial Group"),
    ("ST_AS_INFY_NS",      "INFY.NS",      "Infosys",               478, "India",     "Infosys"),
    ("ST_AS_8035_T",       "8035.T",       "Tokyo Electron",        479, "Japan",     "Tokyo Electron"),
    ("ST_AS_BHP_AX",       "BHP.AX",       "BHP Group",             480, "Australia", "BHP Group"),
    ("ST_AS_6857_T",       "6857.T",       "Advantest",             481, "Japan",     "Advantest"),
    ("ST_AS_8802_T",       "8802.T",       "Mitsubishi Estate",     482, "Japan",     "Mitsubishi Estate"),
    ("ST_AS_6503_T",       "6503.T",       "Mitsubishi Electric",   483, "Japan",     "Mitsubishi Electric"),
    ("ST_AS_POWERGRID_NS", "POWERGRID.NS", "Power Grid",            484, "India",     "Power Grid Corporation of India"),
    ("ST_AS_688072_SS",    "688072.SS",    "Piotech",               485, "China",     "Piotech"),
    ("ST_AS_601869_SS",    "601869.SS",    "Yangtze Optical",       486, "China",     "Yangtze Optical Fibre and Cable"),
    ("ST_AS_AXISBANK_NS",  "AXISBANK.NS",  "Axis Bank",             487, "India",     "Axis Bank"),
    ("ST_AS_APOLLOHOSP_NS","APOLLOHOSP.NS","Apollo Hospitals",      488, "India",     "Apollo Hospitals Enterprise"),
    ("ST_AS_301308_SZ",    "301308.SZ",    "Longsys",               489, "China",     "Shenzhen Longsys Electronics"),
    ("ST_AS_SBILIFE_NS",   "SBILIFE.NS",   "SBI Life",              490, "India",     "SBI Life Insurance"),
    ("ST_AS_002156_SZ",    "002156.SZ",    "TongFu",                491, "China",     "Tongfu Microelectronics"),
    ("ST_AS_688120_SS",    "688120.SS",    "Hwatsing",              492, "China",     "Hwatsing Technology"),
    ("ST_AS_6146_T",       "6146.T",       "Disco",                 493, "Japan",     "Disco Corporation"),
    ("ST_AS_300316_SZ",    "300316.SZ",    "Jingsheng Mech",        494, "China",     "Zhejiang Jingsheng Mechanical & Electrical"),
    ("ST_AS_7013_T",       "7013.T",       "IHI",                   495, "Japan",     "IHI Corporation"),
    ("ST_MEITUAN",         "3690.HK",      "Meituan",               496, "China",     "Meituan"),                # 기존 (HK)
    ("ST_AS_MM_NS",        "M&M.NS",       "M&M",                   497, "India",     "Mahindra & Mahindra"),
    ("ST_AS_2317_TW",      "2317.TW",      "Hon Hai/Foxconn",       498, "Taiwan",    "Hon Hai Precision (Foxconn)"),
    ("ST_AS_ETERNAL_NS",   "ETERNAL.NS",   "Eternal/Zomato",        499, "India",     "Eternal (Zomato)"),
]


# yfinance 통화 매핑 (티커 접미사 → ISO 4217)
_SUFFIX_TO_CCY = {
    ".TW": "TWD", ".HK": "HKD", ".SS": "CNY", ".SZ": "CNY",
    ".NS": "INR", ".T":  "JPY", ".AX": "AUD",
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
    """KR + US + ASIA 신규 종목만. 기존 collect_market.py 가 다루는 14개는 제외.

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
    for code, ticker, name, _order, _country, _name_en in ASIA_TOP50:
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
    """MKT000_MARKET_INDICATOR 에 KR_TOP50 + US_TOP50 + ASIA_TOP50 신규 종목 dim 행 등록.

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
    for code, yf_ticker, name, order, country, name_en in ASIA_TOP50:
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
