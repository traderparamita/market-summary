#!/usr/bin/env python3
"""scripts/verify_report_numbers.py — 보고서 수치 결정론 검증

CSV ground truth (history/market_data.csv) 와 보고서 본문에 명시된
WTD/MTD/YTD 등락률 + 채권 bp 변화를 정규식으로 추출하여 자동 대조한다.

Phase 1 범위 (이번 W17 오류 케이스):
  - 주간 보고서 (output/summary/weekly/*.html / *_story.html)
  - 일간 보고서 (output/summary/YYYY-MM/YYYY-MM-DD.html)
  - 월간 보고서 (output/summary/monthly/YYYY-MM.html)
  - 분기/임시 보고서 (output/report/*.md)

검증 항목 (본문/표 자동 추출):
  1. {자산} WTD ±N% / ±Nbp
  2. {자산} MTD ±N% / ±Nbp
  3. {자산} YTD ±N% / ±Nbp
  4. KPI 카드 HTML (s-kpi-label / s-kpi-value)
  5. 마크다운 표 시작값·종료값·등락 자체 모순 (Q1 확장판 케이스)

허용 오차:
  - 등락률 : ±0.05 %P
  - bp     : ±0.5 bp
  - 종가   : ±0.05 % (1‰ 이내 반올림 허용)

Usage:
    .venv/bin/python scripts/verify_report_numbers.py [files...]
    .venv/bin/python scripts/verify_report_numbers.py --auto           # git diff 기반 자동
    .venv/bin/python scripts/verify_report_numbers.py --auto --fix     # 자동 감지 + 자동 수정 + 재검증
    .venv/bin/python scripts/verify_report_numbers.py --json           # JSON (hooks 용)

Exit code: 0 = pass, 1 = violation (--fix 사용 시 수정 후 재검증 기준)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "history" / "market_data.csv"

# 허용 오차 없음 — 보고서 표시 자릿수에 맞춰 반올림한 CSV 계산값과 정확 일치 요구.
# (예: 보고서 "+4.58%" → CSV 계산 4.581%를 둘째 자리 반올림한 +4.58% 과 비교)
# 표 자체 산술 모순 검증만 약간의 마진(반올림 누적) 허용.
TABLE_SELF_TOL = 0.1    # %P, 마크다운 표 시작/종료/등락 자체 모순 (시작·종료 정수 반올림 누적 흡수)


# ── 자산 별칭 → INDICATOR_CODE ─────────────────────────────────
ASSET_ALIASES: dict[str, str] = {
    # 주가 지수
    "KOSPI": "EQ_KOSPI",
    "KOSDAQ": "EQ_KOSDAQ",
    "S&P500": "EQ_SP500",
    "S&amp;P500": "EQ_SP500",
    "SPX": "EQ_SP500",
    "NASDAQ": "EQ_NASDAQ",
    "Nikkei225": "EQ_NIKKEI225",
    "Nikkei": "EQ_NIKKEI225",
    "TWSE": "EQ_TWSE",
    "HSI": "EQ_HSI",
    "DAX": "EQ_DAX",
    "CAC40": "EQ_CAC40",
    "CAC": "EQ_CAC40",
    "FTSE100": "EQ_FTSE100",
    "FTSE": "EQ_FTSE100",
    "STOXX50": "EQ_EUROSTOXX50",
    "Russell2K": "EQ_RUSSELL2000",
    "Russell 2K": "EQ_RUSSELL2000",
    "RUT": "EQ_RUSSELL2000",
    "NIFTY50": "EQ_NIFTY50",
    "NIFTY": "EQ_NIFTY50",
    "Shanghai": "EQ_SHANGHAI",
    # 원자재
    "WTI": "CM_WTI",
    "Brent": "CM_BRENT",
    "Gold": "CM_GOLD",
    "Silver": "CM_SILVER",
    "Copper": "CM_COPPER",
    "Nat Gas": "CM_NATGAS",
    "NatGas": "CM_NATGAS",
    # FX
    "DXY": "FX_DXY",
    "USD/KRW": "FX_USDKRW",
    "USD/JPY": "FX_USDJPY",
    "EUR/USD": "FX_EURUSD",
    "AUD/USD": "FX_AUDUSD",
    "GBP/USD": "FX_GBPUSD",
    # 변동성
    "VIX": "RK_VIX",
    # 채권 (yield)
    "US 10Y": "BD_US_10Y",
    "US 2Y": "BD_US_2Y",
    "US 30Y": "BD_US_30Y",
    "KR 3Y": "BD_KR_3Y",
    "KR 10Y": "BD_KR_10Y",
    # 종목
    "Samsung": "ST_SAMSUNG",
    "삼성전자": "ST_SAMSUNG",
    "Apple": "ST_AAPL",
    "AAPL": "ST_AAPL",
    "Microsoft": "ST_MSFT",
    "MSFT": "ST_MSFT",
    "Alphabet": "ST_GOOGL",
    "Google": "ST_GOOGL",
    "GOOGL": "ST_GOOGL",
    "Amazon": "ST_AMZN",
    "AMZN": "ST_AMZN",
    "Meta": "ST_META",
    "Meta Platforms": "ST_META",
    "META": "ST_META",
    "NVIDIA": "ST_NVDA",
    "NVDA": "ST_NVDA",
    "Tesla": "ST_TSLA",
    "TSLA": "ST_TSLA",
    "TSMC": "ST_TSMC",
    "Broadcom": "ST_AVGO",
    "AVGO": "ST_AVGO",
    "Alibaba": "ST_BABA",
    "BABA": "ST_BABA",
    "Tencent": "ST_TENCENT",
    "Meituan": "ST_MEITUAN",
    "Palantir": "ST_PLTR",
    "PLTR": "ST_PLTR",
    # ── KR50 신규 (2026-05-07 시총 상위 50, 005930 삼성전자는 위에 ST_SAMSUNG) ──
    # 한글명·영문명·6자리 코드 매칭. 단독 알파벳 약어("SK","HD"등)는 일반 SK/HD 와 충돌해 제외.
    "SK Hynix": "ST_KR_000660", "SK하이닉스": "ST_KR_000660", "000660": "ST_KR_000660",
    "SK Square": "ST_KR_402340", "SK스퀘어": "ST_KR_402340", "402340": "ST_KR_402340",
    "LG Energy Solution": "ST_KR_373220", "LG에너지솔루션": "ST_KR_373220", "373220": "ST_KR_373220",
    "Hyundai Motor": "ST_KR_005380", "현대차": "ST_KR_005380", "005380": "ST_KR_005380",
    "Doosan Enerbility": "ST_KR_034020", "두산에너빌리티": "ST_KR_034020", "034020": "ST_KR_034020",
    "Hanwha Aerospace": "ST_KR_012450", "한화에어로스페이스": "ST_KR_012450", "012450": "ST_KR_012450",
    "Samsung Biologics": "ST_KR_207940", "삼성바이오로직스": "ST_KR_207940", "207940": "ST_KR_207940",
    "Samsung Electro-Mechanics": "ST_KR_009150", "삼성전기": "ST_KR_009150", "009150": "ST_KR_009150",
    "HD Hyundai Heavy": "ST_KR_329180", "HD Hyundai Heavy Industries": "ST_KR_329180",
    "HD현대중공업": "ST_KR_329180", "329180": "ST_KR_329180",
    "Samsung C&T": "ST_KR_028260", "삼성물산": "ST_KR_028260", "028260": "ST_KR_028260",
    "Kia": "ST_KR_000270", "기아": "ST_KR_000270", "000270": "ST_KR_000270",
    "Samsung Life": "ST_KR_032830", "Samsung Life Insurance": "ST_KR_032830",
    "삼성생명": "ST_KR_032830", "032830": "ST_KR_032830",
    "KB Financial": "ST_KR_105560", "KB Financial Group": "ST_KR_105560",
    "KB금융": "ST_KR_105560", "105560": "ST_KR_105560",
    "Samsung SDI": "ST_KR_006400", "삼성SDI": "ST_KR_006400", "006400": "ST_KR_006400",
    "HD Hyundai Electric": "ST_KR_267260", "HD현대일렉트릭": "ST_KR_267260", "267260": "ST_KR_267260",
    "LS ELECTRIC": "ST_KR_010120", "LS Electric": "ST_KR_010120", "010120": "ST_KR_010120",
    "Mirae Asset Securities": "ST_KR_006800", "미래에셋증권": "ST_KR_006800", "006800": "ST_KR_006800",
    "Shinhan Financial": "ST_KR_055550", "Shinhan Financial Group": "ST_KR_055550",
    "신한지주": "ST_KR_055550", "055550": "ST_KR_055550",
    "Celltrion": "ST_KR_068270", "셀트리온": "ST_KR_068270", "068270": "ST_KR_068270",
    "Hyosung Heavy": "ST_KR_298040", "Hyosung Heavy Industries": "ST_KR_298040",
    "효성중공업": "ST_KR_298040", "298040": "ST_KR_298040",
    "POSCO Holdings": "ST_KR_005490", "POSCO홀딩스": "ST_KR_005490", "005490": "ST_KR_005490",
    "Hanwha Ocean": "ST_KR_042660", "한화오션": "ST_KR_042660", "042660": "ST_KR_042660",
    "Hyundai Mobis": "ST_KR_012330", "현대모비스": "ST_KR_012330", "012330": "ST_KR_012330",
    "SK Inc": "ST_KR_034730", "034730": "ST_KR_034730",   # "SK" 단독 alias 는 충돌로 제외
    "Hanmi Semiconductor": "ST_KR_042700", "한미반도체": "ST_KR_042700", "042700": "ST_KR_042700",
    "Korea Zinc": "ST_KR_010130", "고려아연": "ST_KR_010130", "010130": "ST_KR_010130",
    "Hana Financial": "ST_KR_086790", "Hana Financial Group": "ST_KR_086790",
    "하나금융지주": "ST_KR_086790", "086790": "ST_KR_086790",
    "NAVER": "ST_KR_035420", "Naver": "ST_KR_035420", "035420": "ST_KR_035420",
    "HD Korea Shipbuilding": "ST_KR_009540",
    "HD Korea Shipbuilding & Offshore Engineering": "ST_KR_009540",
    "HD한국조선해양": "ST_KR_009540", "009540": "ST_KR_009540",
    "LG Chem": "ST_KR_051910", "LG화학": "ST_KR_051910", "051910": "ST_KR_051910",
    "Doosan": "ST_KR_000150", "두산": "ST_KR_000150", "000150": "ST_KR_000150",
    "KEPCO": "ST_KR_015760", "Korea Electric Power": "ST_KR_015760",
    "한국전력": "ST_KR_015760", "015760": "ST_KR_015760",
    "Hyundai Rotem": "ST_KR_064350", "현대로템": "ST_KR_064350", "064350": "ST_KR_064350",
    "Samsung Heavy": "ST_KR_010140", "Samsung Heavy Industries": "ST_KR_010140",
    "삼성중공업": "ST_KR_010140", "010140": "ST_KR_010140",
    "POSCO Future M": "ST_KR_003670", "포스코퓨처엠": "ST_KR_003670", "003670": "ST_KR_003670",
    "LG Electronics": "ST_KR_066570", "LG전자": "ST_KR_066570", "066570": "ST_KR_066570",
    "SK Innovation": "ST_KR_096770", "SK이노베이션": "ST_KR_096770", "096770": "ST_KR_096770",
    "Woori Financial": "ST_KR_316140", "Woori Financial Group": "ST_KR_316140",
    "우리금융지주": "ST_KR_316140", "316140": "ST_KR_316140",
    "Hanwha Systems": "ST_KR_272210", "한화시스템": "ST_KR_272210", "272210": "ST_KR_272210",
    "HD Hyundai": "ST_KR_267250", "HD현대": "ST_KR_267250", "267250": "ST_KR_267250",
    "LIG Defense": "ST_KR_079550", "LIG Defense and Aerospace": "ST_KR_079550",
    "LIG디펜스앤에어로스페이스": "ST_KR_079550", "079550": "ST_KR_079550",
    "Samsung Fire": "ST_KR_000810", "Samsung Fire & Marine": "ST_KR_000810",
    "삼성화재": "ST_KR_000810", "000810": "ST_KR_000810",
    "SK Telecom": "ST_KR_017670", "SK텔레콤": "ST_KR_017670", "017670": "ST_KR_017670",
    "Kakao": "ST_KR_035720", "카카오": "ST_KR_035720", "035720": "ST_KR_035720",
    "KT&G": "ST_KR_033780", "033780": "ST_KR_033780",
    "HMM": "ST_KR_011200", "011200": "ST_KR_011200",
    "Meritz Financial": "ST_KR_138040", "Meritz Financial Group": "ST_KR_138040",
    "메리츠금융지주": "ST_KR_138040", "138040": "ST_KR_138040",
    "Hyundai E&C": "ST_KR_000720", "Hyundai Engineering & Construction": "ST_KR_000720",
    "현대건설": "ST_KR_000720", "000720": "ST_KR_000720",
    "IBK": "ST_KR_024110", "Industrial Bank of Korea": "ST_KR_024110",
    "기업은행": "ST_KR_024110", "024110": "ST_KR_024110",
    # ── US S&P50 신규 (2026-05-07 — 기존 9 ST_* 제외 41개) ──
    # 단독 1글자 티커 (C, V) 와 시간/약어 충돌 (PM, KO, GE, MS, GS, HD, MA, PG) 는 회피.
    "Walmart": "ST_WMT", "WMT": "ST_WMT",
    "Berkshire": "ST_BRK_B", "Berkshire Hathaway": "ST_BRK_B", "BRK-B": "ST_BRK_B",
    "Eli Lilly": "ST_LLY", "LLY": "ST_LLY",
    "JPMorgan": "ST_JPM", "JPMorgan Chase": "ST_JPM", "JPM": "ST_JPM",
    "Micron": "ST_MU", "Micron Technology": "ST_MU", "MU": "ST_MU",
    "AMD": "ST_AMD", "Advanced Micro Devices": "ST_AMD",
    "Exxon Mobil": "ST_XOM", "ExxonMobil": "ST_XOM", "XOM": "ST_XOM",
    "Visa": "ST_V",
    "Intel": "ST_INTC", "INTC": "ST_INTC",
    "Oracle": "ST_ORCL", "ORCL": "ST_ORCL",
    "Johnson & Johnson": "ST_JNJ", "JNJ": "ST_JNJ",
    "Costco": "ST_COST", "COST": "ST_COST",
    "Mastercard": "ST_MA",
    "Caterpillar": "ST_CAT", "CAT": "ST_CAT",
    "Bank of America": "ST_BAC", "BAC": "ST_BAC",
    "Netflix": "ST_NFLX", "NFLX": "ST_NFLX",
    "Lam Research": "ST_LRCX", "LRCX": "ST_LRCX",
    "Chevron": "ST_CVX", "CVX": "ST_CVX",
    "AbbVie": "ST_ABBV", "ABBV": "ST_ABBV",
    "Cisco": "ST_CSCO", "Cisco Systems": "ST_CSCO", "CSCO": "ST_CSCO",
    "P&G": "ST_PG", "Procter & Gamble": "ST_PG",
    "Coca-Cola": "ST_KO",
    "Applied Materials": "ST_AMAT", "AMAT": "ST_AMAT",
    "UnitedHealth": "ST_UNH", "UNH": "ST_UNH",
    "Home Depot": "ST_HD",
    "GE Aerospace": "ST_GE",
    "Morgan Stanley": "ST_MS",
    "GE Vernova": "ST_GEV", "GEV": "ST_GEV",
    "Goldman Sachs": "ST_GS",
    "Merck": "ST_MRK", "MRK": "ST_MRK",
    "Philip Morris": "ST_PM", "Philip Morris International": "ST_PM",
    "Texas Instruments": "ST_TXN", "TXN": "ST_TXN",
    "Wells Fargo": "ST_WFC", "WFC": "ST_WFC",
    "RTX": "ST_RTX",
    "KLA": "ST_KLAC", "KLAC": "ST_KLAC",
    "Linde": "ST_LIN", "LIN": "ST_LIN",
    "American Express": "ST_AXP", "AXP": "ST_AXP",
    "Citigroup": "ST_C",
    "PepsiCo": "ST_PEP", "PEP": "ST_PEP",
    "IBM": "ST_IBM",
    "T-Mobile": "ST_TMUS", "T-Mobile US": "ST_TMUS", "TMUS": "ST_TMUS",
    # ── ASIA Top 65 + ADR 1종 신규 (2026-05-14) ──
    # 일본 — 영문 + 한글 음역 + yfinance ticker
    "Toyota": "ST_AS_7203_T", "토요타": "ST_AS_7203_T", "7203.T": "ST_AS_7203_T",
    "Sony": "ST_AS_6758_T", "소니": "ST_AS_6758_T", "6758.T": "ST_AS_6758_T",
    "Keyence": "ST_AS_6861_T", "키엔스": "ST_AS_6861_T", "6861.T": "ST_AS_6861_T",
    "Tokyo Electron": "ST_AS_8035_T", "도쿄일렉트론": "ST_AS_8035_T", "8035.T": "ST_AS_8035_T",
    "Advantest": "ST_AS_6857_T", "어드밴테스트": "ST_AS_6857_T", "6857.T": "ST_AS_6857_T",
    "Mizuho FG": "ST_AS_8411_T", "미즈호": "ST_AS_8411_T", "8411.T": "ST_AS_8411_T",
    "Hitachi": "ST_AS_6501_T", "히타치": "ST_AS_6501_T", "6501.T": "ST_AS_6501_T",
    "Lasertec": "ST_AS_6920_T", "레이저텍": "ST_AS_6920_T", "6920.T": "ST_AS_6920_T",
    "Renesas": "ST_AS_6723_T", "르네사스": "ST_AS_6723_T", "6723.T": "ST_AS_6723_T",
    "Takeda": "ST_AS_4502_T", "다케다": "ST_AS_4502_T", "4502.T": "ST_AS_4502_T",
    "Resonac": "ST_AS_4004_T", "레조낙": "ST_AS_4004_T", "4004.T": "ST_AS_4004_T",
    "Seven & i": "ST_AS_3382_T", "세븐앤아이": "ST_AS_3382_T", "3382.T": "ST_AS_3382_T",
    "SCREEN": "ST_AS_7735_T", "스크린홀딩스": "ST_AS_7735_T", "7735.T": "ST_AS_7735_T",
    "Rohm": "ST_AS_6963_T", "롬": "ST_AS_6963_T", "6963.T": "ST_AS_6963_T",
    "SUMCO": "ST_AS_3436_T", "섬코": "ST_AS_3436_T", "3436.T": "ST_AS_3436_T",
    "Kokusai Electric": "ST_AS_6525_T", "고쿠사이일렉트릭": "ST_AS_6525_T", "6525.T": "ST_AS_6525_T",
    "Mitsubishi Electric": "ST_AS_6503_T", "미쓰비시전기": "ST_AS_6503_T", "6503.T": "ST_AS_6503_T",
    "Mitsubishi Estate": "ST_AS_8802_T", "미쓰비시지소": "ST_AS_8802_T", "8802.T": "ST_AS_8802_T",
    "Disco": "ST_AS_6146_T", "디스코": "ST_AS_6146_T", "6146.T": "ST_AS_6146_T",
    "IHI": "ST_AS_7013_T", "7013.T": "ST_AS_7013_T",
    # 중국 (HK · A주). Tencent/Alibaba/Meituan 은 위쪽에 이미 등록 — 새 ST_AS_ 코드 추가만.
    "Baidu": "ST_AS_9888_HK", "바이두": "ST_AS_9888_HK", "9888.HK": "ST_AS_9888_HK",
    "NetEase": "ST_AS_9999_HK", "넷이즈": "ST_AS_9999_HK", "9999.HK": "ST_AS_9999_HK",
    "Zijin Gold Intl": "ST_AS_2259_HK", "쯔진광업": "ST_AS_2259_HK", "2259.HK": "ST_AS_2259_HK",
    "BYD": "ST_AS_1211_HK", "비야디": "ST_AS_1211_HK", "1211.HK": "ST_AS_1211_HK",
    "CATL": "ST_AS_300750_SZ", "닝더스다이": "ST_AS_300750_SZ", "300750.SZ": "ST_AS_300750_SZ",
    "SMIC": "ST_AS_0981_HK", "0981.HK": "ST_AS_0981_HK",
    "Xiaomi": "ST_AS_1810_HK", "샤오미": "ST_AS_1810_HK", "1810.HK": "ST_AS_1810_HK",
    "Ping An Insurance": "ST_AS_2318_HK", "핑안보험": "ST_AS_2318_HK", "2318.HK": "ST_AS_2318_HK",
    "Hua Hong Semi": "ST_AS_1347_HK", "화훙반도체": "ST_AS_1347_HK", "1347.HK": "ST_AS_1347_HK",
    "Cambricon Tech": "ST_AS_688256_SS", "캄브리콘": "ST_AS_688256_SS", "688256.SS": "ST_AS_688256_SS",
    "NAURA Tech": "ST_AS_002371_SZ", "북방화창": "ST_AS_002371_SZ", "002371.SZ": "ST_AS_002371_SZ",
    "Hygon Info Tech": "ST_AS_688041_SS", "688041.SS": "ST_AS_688041_SS",
    "GigaDevice": "ST_AS_603986_SS", "603986.SS": "ST_AS_603986_SS",
    "AMEC": "ST_AS_688012_SS", "688012.SS": "ST_AS_688012_SS",
    "Montage Tech": "ST_AS_688008_SS", "688008.SS": "ST_AS_688008_SS",
    "Zhongji Innolight": "ST_AS_300308_SZ", "300308.SZ": "ST_AS_300308_SZ",
    "Sieyuan Electric": "ST_AS_002028_SZ", "002028.SZ": "ST_AS_002028_SZ",
    "Futu Holdings": "ST_AS_FUTU", "푸투": "ST_AS_FUTU",
    "Biwin Storage": "ST_AS_688525_SS", "688525.SS": "ST_AS_688525_SS",
    "Hangzhou Chang Chuan": "ST_AS_300604_SZ", "300604.SZ": "ST_AS_300604_SZ",
    "Horizon Robotics": "ST_AS_9660_HK", "9660.HK": "ST_AS_9660_HK",
    "Piotech": "ST_AS_688072_SS", "688072.SS": "ST_AS_688072_SS",
    "Yangtze Optical": "ST_AS_601869_SS", "601869.SS": "ST_AS_601869_SS",
    "Longsys": "ST_AS_301308_SZ", "301308.SZ": "ST_AS_301308_SZ",
    "TongFu": "ST_AS_002156_SZ", "002156.SZ": "ST_AS_002156_SZ",
    "Hwatsing": "ST_AS_688120_SS", "688120.SS": "ST_AS_688120_SS",
    "Jingsheng Mech": "ST_AS_300316_SZ", "300316.SZ": "ST_AS_300316_SZ",
    # 대만 — TSMC TW (대만 상장) 와 TSMC (ADR, 위쪽 ST_TSMC) 분리
    "TSMC TW": "ST_AS_2330_TW", "TSMC 대만": "ST_AS_2330_TW", "2330.TW": "ST_AS_2330_TW",
    "Hon Hai/Foxconn": "ST_AS_2317_TW", "Hon Hai": "ST_AS_2317_TW", "폭스콘": "ST_AS_2317_TW", "2317.TW": "ST_AS_2317_TW",
    "Delta Electronics": "ST_AS_2308_TW", "델타전자": "ST_AS_2308_TW", "2308.TW": "ST_AS_2308_TW",
    "ASE Tech": "ST_AS_3711_TW", "ASE": "ST_AS_3711_TW", "3711.TW": "ST_AS_3711_TW",
    "AVC": "ST_AS_3017_TW", "3017.TW": "ST_AS_3017_TW",
    # 인도
    "HDFC Bank": "ST_AS_HDFCBANK_NS", "HDFC뱅크": "ST_AS_HDFCBANK_NS", "HDFCBANK.NS": "ST_AS_HDFCBANK_NS",
    "ICICI Bank": "ST_AS_ICICIBANK_NS", "ICICI뱅크": "ST_AS_ICICIBANK_NS", "ICICIBANK.NS": "ST_AS_ICICIBANK_NS",
    "Reliance": "ST_AS_RELIANCE_NS", "릴라이언스": "ST_AS_RELIANCE_NS", "RELIANCE.NS": "ST_AS_RELIANCE_NS",
    "Infosys": "ST_AS_INFY_NS", "인포시스": "ST_AS_INFY_NS", "INFY.NS": "ST_AS_INFY_NS",
    "Bharti Airtel": "ST_AS_BHARTIARTL_NS", "바티에어텔": "ST_AS_BHARTIARTL_NS", "BHARTIARTL.NS": "ST_AS_BHARTIARTL_NS",
    "Titan": "ST_AS_TITAN_NS", "타이탄": "ST_AS_TITAN_NS", "TITAN.NS": "ST_AS_TITAN_NS",
    "Power Grid": "ST_AS_POWERGRID_NS", "파워그리드": "ST_AS_POWERGRID_NS", "POWERGRID.NS": "ST_AS_POWERGRID_NS",
    "Axis Bank": "ST_AS_AXISBANK_NS", "악시스뱅크": "ST_AS_AXISBANK_NS", "AXISBANK.NS": "ST_AS_AXISBANK_NS",
    "Apollo Hospitals": "ST_AS_APOLLOHOSP_NS", "아폴로병원": "ST_AS_APOLLOHOSP_NS", "APOLLOHOSP.NS": "ST_AS_APOLLOHOSP_NS",
    "SBI Life": "ST_AS_SBILIFE_NS", "SBI생명": "ST_AS_SBILIFE_NS", "SBILIFE.NS": "ST_AS_SBILIFE_NS",
}

# 채권 = bp 단위, 그 외 = % 단위
BOND_CODES = {v for k, v in ASSET_ALIASES.items() if v.startswith("BD_")}

# 자산별 종가 합리적 범위 — 단독 종가 매칭의 false positive(거래량·시총 등) 차단용
# (lo, hi) 범위 밖 숫자는 "종가가 아니다" 라고 보고 검증 스킵
PRICE_RANGE: dict[str, tuple[float, float]] = {
    # 지수
    "EQ_KOSPI": (2000, 9000),
    "EQ_KOSDAQ": (500, 2000),
    "EQ_SP500": (3000, 9000),
    "EQ_NASDAQ": (10000, 35000),
    "EQ_NIKKEI225": (20000, 80000),
    "EQ_TWSE": (15000, 50000),
    "EQ_HSI": (15000, 35000),
    "EQ_NIFTY50": (15000, 30000),
    "EQ_DAX": (10000, 35000),
    "EQ_CAC40": (5000, 12000),
    "EQ_FTSE100": (6000, 13000),
    "EQ_EUROSTOXX50": (3000, 8000),
    "EQ_RUSSELL2000": (1500, 4000),
    "EQ_SHANGHAI": (2500, 5500),
    # 종목
    "ST_SAMSUNG": (50000, 350000),
    "ST_AAPL": (100, 500),
    "ST_MSFT": (200, 700),
    "ST_GOOGL": (100, 600),
    "ST_AMZN": (100, 400),
    "ST_META": (200, 1200),
    "ST_NVDA": (50, 500),
    "ST_TSLA": (100, 700),
    "ST_TSMC": (100, 500),
    "ST_AVGO": (100, 600),
    "ST_BABA": (50, 300),
    "ST_TENCENT": (200, 800),
    "ST_MEITUAN": (50, 300),
    "ST_PLTR": (10, 200),
    # ── KR50 신규 49종 (history min/max × 0.7~1.5, 2026-05-07) ──
    "ST_KR_000660": (9412, 2401500), "ST_KR_402340": (22400, 1633500),
    "ST_KR_373220": (187600, 936000), "ST_KR_005380": (36812, 1011000),
    "ST_KR_034020": (1555, 193800), "ST_KR_012450": (10739, 2305500),
    "ST_KR_207940": (151226, 2947500), "ST_KR_009150": (24726, 1377000),
    "ST_KR_329180": (62918, 1035000), "ST_KR_028260": (46660, 563250),
    "ST_KR_000270": (8255, 296006), "ST_KR_032830": (17402, 447000),
    "ST_KR_105560": (12825, 248973), "ST_KR_006400": (51511, 1214194),
    "ST_KR_267260": (3270, 2083500), "ST_KR_010120": (3250, 473250),
    "ST_KR_006800": (2183, 125700), "ST_KR_055550": (11564, 156467),
    "ST_KR_068270": (8095, 503861), "ST_KR_298040": (5928, 6895500),
    "ST_KR_005490": (77146, 918616), "ST_KR_042660": (6814, 595652),
    "ST_KR_012330": (79311, 784273), "ST_KR_034730": (23869, 780000),
    "ST_KR_042700": (447, 591750), "ST_KR_010130": (78583, 3172500),
    "ST_KR_086790": (7888, 194815), "ST_KR_035420": (26374, 662751),
    "ST_KR_009540": (35239, 718500), "ST_KR_051910": (100459, 1463108),
    "ST_KR_000150": (16481, 2685000), "ST_KR_015760": (10408, 101850),
    "ST_KR_064350": (6139, 403500), "ST_KR_010140": (2057, 51730),
    "ST_KR_003670": (2789, 895228), "ST_KR_066570": (25235, 264820),
    "ST_KR_096770": (37313, 443040), "ST_KR_316140": (3097, 60007),
    "ST_KR_272210": (2707, 243157), "ST_KR_267250": (15595, 465750),
    "ST_KR_079550": (10247, 1530000), "ST_KR_000810": (64819, 907393),
    "ST_KR_017670": (8120, 150750), "ST_KR_035720": (8605, 252842),
    "ST_KR_033780": (19219, 269400), "ST_KR_011200": (1283, 359576),
    "ST_KR_138040": (894, 219300), "ST_KR_000720": (12377, 283050),
    "ST_KR_024110": (2757, 40919),
    # ── US S&P50 신규 41종 ──
    "ST_WMT": (8, 200), "ST_BRK_B": (45, 810), "ST_LLY": (15, 1662),
    "ST_JPM": (13, 499), "ST_MU": (3, 1000), "ST_AMD": (1, 632),
    "ST_XOM": (17, 257), "ST_V": (10, 557), "ST_INTC": (8, 170),
    "ST_ORCL": (12, 489), "ST_JNJ": (25, 373), "ST_COST": (27, 1604),
    "ST_MA": (12, 894), "ST_CAT": (24, 1390), "ST_BAC": (3, 85),
    "ST_NFLX": (0.5, 201), "ST_LRCX": (2, 446), "ST_CVX": (25, 317),
    "ST_ABBV": (14, 358), "ST_CSCO": (6, 141), "ST_PG": (26, 259),
    "ST_KO": (11, 122), "ST_AMAT": (6, 643), "ST_UNH": (15, 905),
    "ST_HD": (13, 627), "ST_GE": (19, 518), "ST_MS": (6, 290),
    "ST_GEV": (86, 1724), "ST_GS": (47, 1456), "ST_MRK": (12, 188),
    "ST_PM": (14, 282), "ST_TXN": (10, 434), "ST_WFC": (11, 144),
    "ST_RTX": (19, 318), "ST_KLAC": (11, 2903), "ST_LIN": (38, 766),
    "ST_AXP": (20, 574), "ST_C": (12, 199), "ST_PEP": (25, 266),
    "ST_IBM": (47, 470), "ST_TMUS": (6, 402),
    # ── ASIA Top 65 + ADR 1종 (2026-05-14) — history min × 0.7 ~ max × 1.5 ──
    # 일본 (JPY)
    "ST_AS_7203_T": (218, 5829),       # Toyota
    "ST_AS_6758_T": (101, 7022),       # Sony
    "ST_AS_6861_T": (2601, 126255),    # Keyence
    "ST_AS_8035_T": (527, 78675),      # Tokyo Electron
    "ST_AS_6857_T": (97, 47250),       # Advantest
    "ST_AS_8411_T": (383, 11666),      # Mizuho FG
    "ST_AS_6501_T": (146, 8677),       # Hitachi
    "ST_AS_6920_T": (46, 68655),       # Lasertec
    "ST_AS_6723_T": (137, 5625),       # Renesas
    "ST_AS_4502_T": (1179, 8835),      # Takeda
    "ST_AS_4004_T": (501, 26722),      # Resonac
    "ST_AS_3382_T": (311, 3822),       # Seven & i
    "ST_AS_7735_T": (258, 17621),      # SCREEN
    "ST_AS_6963_T": (289, 6000),       # Rohm
    "ST_AS_3436_T": (275, 5640),       # SUMCO
    "ST_AS_6525_T": (1207, 11037),     # Kokusai Electric
    "ST_AS_6503_T": (293, 9702),       # Mitsubishi Electric
    "ST_AS_8802_T": (656, 7920),       # Mitsubishi Estate
    "ST_AS_6146_T": (593, 119321),     # Disco
    "ST_AS_7013_T": (97, 6730),        # IHI
    # 중국 HK (HKD)
    "ST_AS_9888_HK": (52.6, 378.0),    # Baidu
    "ST_AS_9999_HK": (58.8, 368.9),    # NetEase
    "ST_AS_2259_HK": (84.4, 379.8),    # Zijin Gold Intl
    "ST_AS_1211_HK": (2.4, 230.1),     # BYD
    "ST_AS_0981_HK": (1.7, 136.6),     # SMIC
    "ST_AS_1810_HK": (5.8, 90.2),      # Xiaomi
    "ST_AS_2318_HK": (8.6, 117.3),     # Ping An Insurance
    "ST_AS_1347_HK": (3.6, 212.1),     # Hua Hong Semi
    "ST_AS_9660_HK": (2.3, 16.2),      # Horizon Robotics
    # 중국 A주 (CNY)
    "ST_AS_300750_SZ": (12.9, 690.0),  # CATL
    "ST_AS_688256_SS": (22, 1975),     # Cambricon
    "ST_AS_002371_SZ": (4.9, 872.2),   # NAURA
    "ST_AS_688041_SS": (26.4, 523.8),  # Hygon
    "ST_AS_603986_SS": (4.1, 547.5),   # GigaDevice
    "ST_AS_688012_SS": (42.8, 608.4),  # AMEC
    "ST_AS_688008_SS": (29.5, 388.2),  # Montage
    "ST_AS_300308_SZ": (1, 1573),      # Zhongji Innolight
    "ST_AS_002028_SZ": (4.1, 350.3),   # Sieyuan
    "ST_AS_688525_SS": (10.9, 492.7),  # Biwin
    "ST_AS_300604_SZ": (1.7, 342.0),   # Hangzhou Chang Chuan
    "ST_AS_688072_SS": (42.3, 772.5),  # Piotech
    "ST_AS_601869_SS": (14.3, 618.0),  # Yangtze Optical
    "ST_AS_301308_SZ": (33.5, 917.8),  # Longsys
    "ST_AS_002156_SZ": (1.8, 91.8),    # TongFu
    "ST_AS_688120_SS": (46.4, 376.1),  # Hwatsing
    "ST_AS_300316_SZ": (1.2, 120.8),   # Jingsheng Mech
    "ST_AS_FUTU": (5.6, 293.9),        # Futu (US ADR USD)
    # 대만 (TWD)
    "ST_AS_2330_TW": (24, 3465),       # TSMC TW
    "ST_AS_2308_TW": (29, 3420),       # Delta Electronics
    "ST_AS_2317_TW": (21.0, 393.0),    # Hon Hai/Foxconn
    "ST_AS_3711_TW": (12.8, 832.5),    # ASE Tech
    "ST_AS_3017_TW": (6, 4417),        # AVC
    # 인도 (INR)
    "ST_AS_HDFCBANK_NS": (48, 1519),
    "ST_AS_ICICIBANK_NS": (71, 2215),
    "ST_AS_BHARTIARTL_NS": (142, 3244),
    "ST_AS_RELIANCE_NS": (97, 2388),
    "ST_AS_TITAN_NS": (45, 6788),
    "ST_AS_INFY_NS": (132, 2913),
    "ST_AS_POWERGRID_NS": (21.0, 517.3),
    "ST_AS_AXISBANK_NS": (103, 2104),
    "ST_AS_APOLLOHOSP_NS": (209, 12145),
    "ST_AS_SBILIFE_NS": (352, 3160),
    # 원자재
    "CM_WTI": (20, 250),
    "CM_BRENT": (20, 250),
    "CM_GOLD": (1500, 7000),
    "CM_SILVER": (15, 150),
    "CM_COPPER": (2, 12),
    "CM_NATGAS": (1, 15),
    # FX
    "FX_DXY": (85, 120),
    "FX_USDKRW": (1000, 1700),
    "FX_USDJPY": (90, 200),
    "FX_EURUSD": (0.8, 1.5),
    "FX_AUDUSD": (0.4, 1.0),
    "FX_GBPUSD": (0.9, 1.7),
    # 변동성
    "RK_VIX": (5, 90),
    # 채권 (yield, %)
    "BD_US_10Y": (0.5, 8.0),
    "BD_US_2Y": (0.5, 8.0),
    "BD_US_30Y": (0.5, 8.0),
    "BD_KR_3Y": (0.5, 7.0),
    "BD_KR_10Y": (0.5, 7.0),
}

# 정렬: 긴 alias 먼저 (e.g. "Russell 2K" 가 "RUT"보다 우선)
_ALIAS_ALT = "|".join(
    re.escape(k) for k in sorted(ASSET_ALIASES.keys(), key=len, reverse=True)
)


@dataclass
class Violation:
    file: str
    asset: str
    period: str        # WTD / MTD / YTD / 표일관성
    reported: str
    expected: str
    diff: str
    context: str
    # 파일 내 매칭 위치 (--fix 용, 직렬화 제외)
    match_start: int = -1
    match_end: int = -1
    match_text: str = ""   # 원본 매칭 텍스트 (reported 값 부분만 교체하는 데 사용)

    def to_dict(self):
        d = asdict(self)
        d.pop("match_start", None)
        d.pop("match_end", None)
        d.pop("match_text", None)
        return d


# ── CSV 로더 ────────────────────────────────────────────────────
def load_prices(csv_path: Path) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    with csv_path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                out[(row["DATE"], row["INDICATOR_CODE"])] = float(row["CLOSE"])
            except (ValueError, KeyError):
                pass
    return out


def get_close(prices, date_str: str, code: str, lookback: int = 7) -> float | None:
    """그 날짜에 없으면 직전 영업일 종가 (주말/공휴일 폴백)."""
    if (date_str, code) in prices:
        return prices[(date_str, code)]
    d = date.fromisoformat(date_str)
    for i in range(1, lookback + 1):
        prev = (d - timedelta(days=i)).isoformat()
        if (prev, code) in prices:
            return prices[(prev, code)]
    return None


# ── 파싱 헬퍼 ────────────────────────────────────────────────────
_NEG = "−–-"  # U+2212 / U+2013 / ASCII

def parse_pct(s: str) -> float:
    s = s.strip().replace("%", "")
    for ch in _NEG:
        s = s.replace(ch, "-") if ch != "-" else s
    s = s.replace("+", "").strip()
    return float(s)


def parse_bp(s: str) -> float:
    s = s.strip().replace("bp", "")
    for ch in _NEG:
        s = s.replace(ch, "-") if ch != "-" else s
    s = s.replace("+", "").strip()
    return float(s)


def parse_num(s: str) -> float:
    s = s.replace(",", "").replace("원", "").strip()
    return float(s)


def _decimals_in(reported_str: str) -> int:
    """보고서 문자열의 소수 자릿수 추출 ('+4.58%' → 2, '+18bp' → 0)."""
    s = reported_str.replace("%", "").replace("bp", "")
    s = s.lstrip("+−–-").strip()
    if "." in s:
        frac = s.split(".", 1)[1]
        m = re.match(r"\d+", frac)
        return len(m.group(0)) if m else 0
    return 0


# ── 기간 시작/종료일 계산 ───────────────────────────────────────
def weekly_dates(year: int, week: int) -> tuple[str, str]:
    """ISO 주: WTD = 직전 주 금요일 종가 → 해당 주 금요일 종가."""
    monday = date.fromisocalendar(year, week, 1)
    friday = date.fromisocalendar(year, week, 5)
    return ((monday - timedelta(days=3)).isoformat(), friday.isoformat())


def monthly_dates(year: int, month: int) -> tuple[str, str]:
    """MTD = 직전 월 마지막 영업일 → 해당 월 마지막 영업일.
    실제 종료일은 CSV 폴백으로 처리."""
    first = date(year, month, 1)
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    end = next_first - timedelta(days=1)
    start = first - timedelta(days=1)  # prev month last calendar day
    return (start.isoformat(), end.isoformat())


def ytd_dates(year: int, end_iso: str) -> tuple[str, str]:
    """YTD = 직전 연 마지막 영업일 → end_iso."""
    return (date(year - 1, 12, 31).isoformat(), end_iso)


# ── 패턴 ────────────────────────────────────────────────────────
# "{자산} WTD +1.51bp" / "{자산} WTD −2.84%"
# span 태그 감싼 형태도 허용: "WTI MTD <span class="pm-dn">−1.43%</span>"
_SPAN_OPEN = r'(?:<span[^>]*>)?'
_SPAN_CLOSE = r'(?:</span>)?'
PCT_PATTERN = re.compile(
    rf"\b({_ALIAS_ALT})\s+(WTD|MTD|YTD)\s*[:：]?\s*{_SPAN_OPEN}\s*([+\-−–]?\d+\.?\d*)\s*%\s*{_SPAN_CLOSE}"
)
BP_PATTERN = re.compile(
    rf"\b({_ALIAS_ALT})\s+(WTD|MTD|YTD)\s*[:：]?\s*{_SPAN_OPEN}\s*([+\-−–]?\d+\.?\d*)\s*bp\s*{_SPAN_CLOSE}"
)
# "{자산} ... · MTD ±N%" — 자산과 MTD 사이에 종가·일간등락 span이 끼어있는 경우
# 예: "Gold <span ...>$4,609</span> <span ...>−2.01%</span> · MTD <span ...>+2.24%</span>"
# 조건: 같은 <li>/<p> 블록 안, 자산명과 MTD 사이에 다른 자산명·세미콜론이 없어야 함
# → 단순 수치/span/구두점(·,공백)만 허용, 최대 120자
_LI_CONTENT = r'(?:<span[^>]*>[^<]*</span>|[ \t\$·,\./\(\)%─—−–+\d]){0,120}'
PCT_INLINE_PATTERN = re.compile(
    rf"\b({_ALIAS_ALT})"
    rf"(?:\s*{_LI_CONTENT})"
    rf"\bMTD\s*[:：]?\s*{_SPAN_OPEN}\s*([+\-−–]?\d+\.?\d*)\s*%\s*{_SPAN_CLOSE}"
)
BP_INLINE_PATTERN = re.compile(
    rf"\b({_ALIAS_ALT})"
    rf"(?:\s*{_LI_CONTENT})"
    rf"\bMTD\s*[:：]?\s*{_SPAN_OPEN}\s*([+\-−–]?\d+\.?\d*)\s*bp\s*{_SPAN_CLOSE}"
)
# HTML KPI: <div class="s-kpi-label">{asset} WTD</div>...<div class="s-kpi-value ...">+X.XX%</div>
KPI_HTML_PATTERN = re.compile(
    rf'<div class="s-kpi-label">({_ALIAS_ALT})\s+(WTD|MTD|YTD)</div>\s*'
    rf'<div class="s-kpi-value[^"]*">([+\-−–]?\d+\.?\d*)\s*%</div>',
    re.MULTILINE,
)
# HTML span 인라인: "KOSPI <span class="hl-up">+4.58%</span>"
HL_SPAN_PATTERN = re.compile(
    rf'\b({_ALIAS_ALT})\s+<span class="hl-(?:up|down)">\s*([+\-−–]?\d+\.?\d*)\s*(%|bp)\s*</span>'
)
# 마크다운 표 라인: "| KOSPI | 4,309 | 5,052 | **+19.89%** |" — 3컬럼 시작/종료/등락
# 일관성 자체 검증 (CSV 없이도 산술 모순 잡음)
MD_TABLE_3COL = re.compile(
    rf'^\|\s*({_ALIAS_ALT})[^\|]*\|\s*\*?\*?([\d,\.]+)원?\*?\*?\s*\|\s*\*?\*?([\d,\.]+)원?\*?\*?\s*\|\s*'
    rf'\*?\*?([+\-−–]?\d+\.?\d*)\s*%\*?\*?\s*\|',
    re.MULTILINE,
)

# COMBO: "{자산} <span class="hl-up">+4.37%</span>(186,200원)" / "{자산} +2.74%(5,377)" / "WTI -0.81%($111.5)"
# → 일간 등락 + 종가 묶음 (가장 흔한 본문 패턴)
COMBO_PATTERN = re.compile(
    rf'\b({_ALIAS_ALT})\s*'
    rf'(?:<span[^>]*>)?\s*([+\-−–]?\d+\.?\d*)\s*%\s*(?:</span>)?\s*'
    rf'\(\s*\$?([\d,]+\.?\d*)\s*원?\s*\)'
)

# 단독 종가: "{자산} 5,377" / "{자산} 5,377원" / "WTI $111.5" — 자산명 직후 명백한 숫자 토큰
# (콤마 포함 또는 4자리 이상 정수, 또는 소수점 2자리 이상)
STANDALONE_CLOSE_PATTERN = re.compile(
    rf'\b({_ALIAS_ALT})\s+'
    rf'\$?(\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d{{4,}}(?:\.\d+)?|\d+\.\d{{2,}})'
    rf'\s*원?'
)

# T1 종목 일변동률: 14개 핵심 stocks 만 — "Apple +3.24%" / "삼성전자 +5.44%" 형식
# COMBO 가 종가 괄호가 있는 경우만 잡으므로 그 외 케이스 보강 (negative lookahead 로 COMBO 와 중복 방지)
_STOCK_ALIASES = {k: v for k, v in ASSET_ALIASES.items() if v.startswith("ST_")}
_STOCK_ALIAS_ALT = "|".join(
    re.escape(k) for k in sorted(_STOCK_ALIASES.keys(), key=len, reverse=True)
)
STOCK_DAILY_PATTERN = re.compile(
    rf'\b({_STOCK_ALIAS_ALT})\s*'
    rf'(?:<span[^>]*>)?\s*([+\-−–]?\d+\.?\d*)\s*%\s*(?:</span>)?'
    rf'(?!\s*\(\s*\$?[\d,])'   # 종가 괄호 뒤따르면 COMBO 가 처리
)

# 본문 인라인 일자 (다른 일자 인용 — 4/8(수), 4/15(수), 등)
DATE_INLINE_PATTERN = re.compile(r'(\d{1,2})/(\d{1,2})\s*\([월화수목금토일]\)')

# 인용·조건·비교 키워드 — 윈도우에 있으면 종가/일간 등락 검증 스킵 (forward / 다른 일자 인용 가능성)
CITATION_KEYWORDS = (
    "어제", "전일", "전주", "전월", "직전", "이전", "지난주", "지난달", "마감이",
    "→", "←", "vs", "대비",
    "돌파", "이탈", "재돌파", "이상이면", "미만이면", "이상 시", "미만 시",
    "재진입", "넘으면", "내려가면", "회복",
    " > ", " < ", "&gt;", "&lt;",  # 부등호 비교
    "치솟", "급등", "급락", "최고치", "신고점", "ATH", "고점", "저점",
    "재가동", "재돌파",
    # 누적 변동률 가드 — 단일일 일변동률이 아닌 다세션 누적 표기 (예: "닛케이 3세션분 호재")
    "누적", "세션분", "주간 누적", "월간 누적",
)

# Outlook / scenario / forecast 컨테이너 클래스 — 이 안의 가격은 forward 시나리오 트리거
FORWARD_CONTAINER_CLASSES = (
    "scenario-card", "outlook-position", "outlook-divider",
    "scen-trigger", "scen-impact", "quarterly-themes",
    "risk-section",  # risk 본문도 forward 표현 다수
)


def _is_in_forward_container(text: str, position: int) -> bool:
    """주어진 위치가 outlook/scenario/risk 컨테이너 안에 있는지 — 안에 있으면 검증 스킵."""
    # 직전 1500자에서 컨테이너 open 태그가 있고, 그 이후 close 태그가 안 닫혔으면 안에 있음
    backward = text[max(0, position - 4000): position]
    for cls in FORWARD_CONTAINER_CLASSES:
        # 가장 최근 open 태그
        open_idx = backward.rfind(f'class="{cls}')
        if open_idx == -1:
            open_idx = backward.rfind(f"class='{cls}")
        if open_idx == -1:
            continue
        # 그 open 이후로 같은 div가 닫혔는지 — 단순히 </div> 카운트
        after_open = backward[open_idx:]
        # 단순 휴리스틱: open 태그 이후 </div> 등장 횟수가 적으면 안에 있다고 판정
        # 정확한 균형 체크는 복잡하므로 단순화: 직전 컨테이너 open 이후 같은 컨테이너의 다음 등장이 없으면 안에 있다고 봄
        return True
    return False


def _is_in_macro_block(text: str, position: int) -> bool:
    """주어진 위치가 <div class="macro-block"> 안에 있는지.

    Macro 탭은 직전 주(W##) narrative 로 주간 단위로 작성되어 일간 보고서에
    그대로 주입된다. 따라서 일간 보고서의 macro-block 내부 WTD/MTD/bp 수치는
    일간 rolling 값과 일치하지 않는 것이 정상 — 검증 대상에서 제외.

    균형 카운트: macro-block 시작부터 position 까지 <div / </div> 갯수를 비교해
    아직 닫히지 않은 상태이면 안에 있다고 판정.
    """
    backward = text[:position]
    open_idx = backward.rfind('<div class="macro-block"')
    if open_idx == -1:
        open_idx = backward.rfind("<div class='macro-block'")
    if open_idx == -1:
        return False
    segment = text[open_idx:position]
    open_count = segment.count("<div")
    close_count = segment.count("</div>")
    # macro-block 자기 자신의 <div 가 1개 포함되어 있으므로 open_count > close_count 면 내부
    return open_count > close_count


def _is_daily_report_file(file_path: Path) -> bool:
    """파일이 일간 보고서인지 — 2026-05-12.html / 2026-05-12_macro.html 등. weekly/monthly 제외."""
    full = str(file_path)
    name = file_path.name
    if re.search(r"\d{4}-W\d{2}", full):
        return False
    if "monthly" in full and re.search(r"\d{4}-\d{2}(?:_|\.|$)", name):
        return False
    return bool(re.search(r"\d{4}-\d{2}-\d{2}", full))

# 단락 경계 — HL_SPAN 윈도우를 다른 단락에서 차단
# (heading 태그 </h1>~</h6>는 제외 — 헤더의 "WTD" 같은 라벨이 그 섹션의 컨텍스트를 제공해야 하므로)
# `<br>` 단독도 경계로 사용 — 의미적으로 줄 바꿈 = 단락 구분이며, 다음 항목의 키워드("MTD" 등)가
# 윈도우에 끼어들면 false positive 발생 (NVIDIA 일변동률을 다음 라인 "NVIDIA MTD" 와 묶어버린 사례)
PARA_BOUNDARIES = ('<br><br>', '<br /><br />', '<br/><br/>', '<br>', '<br/>', '<br />',
                   '</p>', '</li>', '</div>')

# 일간 컨텍스트 시그널 — "4/8(수)" 같이 일자+한글요일 명시. 매칭되면 그 span은 일간 등락으로 간주 → 검증 스킵
DAILY_HINT_PATTERN = re.compile(r'\d{1,2}/\d{1,2}\s*\([월화수목금토일]\)')

# <h1>~<h6> 헤더 본문 추출 (PARA_BOUNDARIES 가 단락 경계로 헤더를 잘라버려도, span 직전 가장 가까운
# 헤더의 텍스트는 그 섹션 컨텍스트로 보고 PERIOD_HINTS 검색에 추가 — "주간 누적", "월간 누적" 같은
# h3 라벨이 채권 bp WTD/MTD 인식의 키.
HEADING_TAG_RE = re.compile(r'<h[1-6][^>]*>(.*?)</h[1-6]>', re.IGNORECASE | re.DOTALL)


def _nearest_heading_text(text: str, position: int, max_back: int = 2500) -> str:
    """span 직전 가장 가까운 <h1>~<h6> 헤더 본문 (HTML 태그·엔티티는 그대로 반환).
    PERIOD_HINTS 키워드("주간", "월간" 등) 매칭 용도로만 쓰이므로 마크업 제거 불필요."""
    backward = text[max(0, position - max_back): position]
    last_match = None
    for m in HEADING_TAG_RE.finditer(backward):
        last_match = m
    return last_match.group(1) if last_match else ""


def _trim_window_to_paragraph(text: str, span_start: int, span_end: int,
                               max_back: int = 400, max_forward: int = 80) -> str:
    """span 직전·직후 가장 가까운 단락 경계까지 윈도우를 자른다."""
    win_start = max(0, span_start - max_back)
    seg_back = text[win_start:span_start]
    last_b = -1
    for b in PARA_BOUNDARIES:
        idx = seg_back.rfind(b)
        if idx > last_b:
            last_b = idx + len(b)
    if last_b > 0:
        win_start = win_start + last_b

    win_end = min(len(text), span_end + max_forward)
    seg_fwd = text[span_end:win_end]
    first_b = len(seg_fwd)
    for b in PARA_BOUNDARIES:
        idx = seg_fwd.find(b)
        if 0 <= idx < first_b:
            first_b = idx
    win_end = span_end + first_b
    return text[win_start:win_end]


# ── 검증 본체 ────────────────────────────────────────────────────
def _check_pct(
    asset: str, period: str, reported_str: str, context: str,
    start_d: str, end_d: str, prices, file_path: Path,
    match_start: int = -1, match_end: int = -1, match_text: str = "",
) -> Violation | None:
    code = ASSET_ALIASES.get(asset)
    if not code or code in BOND_CODES:
        return None
    p_start = get_close(prices, start_d, code)
    p_end = get_close(prices, end_d, code)
    if p_start is None or p_end is None or p_start == 0:
        return None
    expected = (p_end / p_start - 1) * 100
    reported = parse_pct(reported_str)
    decimals = _decimals_in(reported_str)
    expected_rounded = round(expected, decimals)
    if abs(expected_rounded - reported) >= 10 ** (-decimals) / 2:
        diff = reported - expected
        return Violation(
            file=str(file_path),
            asset=asset,
            period=period,
            reported=f"{reported:+.{max(decimals,2)}f}%",
            expected=f"{expected:+.{max(decimals,2)}f}%",
            diff=f"{diff:+.{max(decimals,2)}f}%P",
            context=context.strip()[:160],
            match_start=match_start,
            match_end=match_end,
            match_text=match_text,
        )
    return None


def _check_close(
    asset: str, target_date: str, reported_str: str, context: str,
    prices, file_path: Path,
) -> Violation | None:
    """종가 검증 — 보고서 표시 자릿수에 맞춰 반올림한 CSV 종가와 정확 일치."""
    code = ASSET_ALIASES.get(asset)
    if not code:
        return None
    # 종가 합리적 범위 체크 (거래량·시총 등 false positive 차단)
    try:
        reported = parse_num(reported_str)
    except ValueError:
        return None
    lo, hi = PRICE_RANGE.get(code, (0, float("inf")))
    if not (lo <= reported <= hi):
        return None  # 범위 밖 → 종가 아님 (거래량 등으로 간주, 스킵)

    csv_close = get_close(prices, target_date, code)
    if csv_close is None:
        return None

    # 표시 자릿수에 맞춰 반올림한 CSV 값과 비교
    if "." in reported_str:
        decimals = len(reported_str.split(".")[1].rstrip("원").rstrip("$"))
    else:
        decimals = 0
    expected_rounded = round(csv_close, decimals)
    # 콤마 무시한 정수부 비교 (5,377 = 5377)
    if abs(expected_rounded - reported) >= 10 ** (-decimals) / 2:
        return Violation(
            file=str(file_path),
            asset=asset,
            period=f"종가({target_date})",
            reported=f"{reported:,.{max(decimals,0)}f}",
            expected=f"{csv_close:,.{max(decimals,2)}f}",
            diff=f"{(reported - csv_close):+,.{max(decimals,2)}f}",
            context=context.strip()[:160],
        )
    return None


def _check_bp(
    asset: str, period: str, reported_str: str, context: str,
    start_d: str, end_d: str, prices, file_path: Path,
    match_start: int = -1, match_end: int = -1, match_text: str = "",
) -> Violation | None:
    code = ASSET_ALIASES.get(asset)
    if not code or code not in BOND_CODES:
        return None
    p_start = get_close(prices, start_d, code)
    p_end = get_close(prices, end_d, code)
    if p_start is None or p_end is None:
        return None
    expected = (p_end - p_start) * 100  # yield Δbp
    reported = parse_bp(reported_str)
    decimals = _decimals_in(reported_str)
    expected_rounded = round(expected, decimals)
    if abs(expected_rounded - reported) >= 10 ** (-decimals) / 2:
        diff = reported - expected
        return Violation(
            file=str(file_path),
            asset=asset,
            period=period,
            reported=f"{reported:+.{max(decimals,2)}f}bp",
            expected=f"{expected:+.{max(decimals,2)}f}bp",
            diff=f"{diff:+.{max(decimals,2)}f}bp",
            context=context.strip()[:160],
            match_start=match_start,
            match_end=match_end,
            match_text=match_text,
        )
    return None


def _resolve_target_date(window: str, file_path: Path,
                          periods: dict[str, tuple[str, str]],
                          match_offset_in_window: int | None = None) -> str | None:
    """본문 윈도우에서 일자 명시(`4/8(수)`)가 있으면 그 일자.
    match_offset_in_window이 주어지면 매칭 위치에 가장 가까운 날짜를 선택한다.
    (테이블에서 여러 행의 날짜가 윈도우에 공존할 때 인접 행 날짜 오인 방지)
    명시 없으면 *일간 보고서만* 그 날로 fallback. 주간/월간은 None 반환(검증 스킵)."""
    matches = list(DATE_INLINE_PATTERN.finditer(window))
    if matches:
        my = re.search(r"(\d{4})", str(file_path))
        if my:
            year = int(my.group(1))
            if match_offset_in_window is not None and len(matches) > 1:
                # 매칭 위치에 가장 가까운 날짜 선택 (같은 <tr> 행 우선)
                best = min(matches, key=lambda dm: abs(dm.start() - match_offset_in_window))
            else:
                best = matches[0]
            try:
                return date(year, int(best.group(1)), int(best.group(2))).isoformat()
            except ValueError:
                pass
    # 일자 명시 없을 때: 일간 보고서만 그 날로 fallback
    if "일간" in periods:
        return periods["일간"][1]
    return None  # 주간/월간 본문은 일자 명시 안 됐으면 검증 안 함 (다른 일자 인용일 수 있음)


def _check_daily_pct(
    asset: str, target_date: str, reported_str: str, context: str,
    prices, file_path: Path,
) -> Violation | None:
    """일간 등락 검증 — target_date 종가 / 직전 영업일 종가."""
    code = ASSET_ALIASES.get(asset)
    if not code or code in BOND_CODES:
        return None
    end_close = get_close(prices, target_date, code)
    if end_close is None:
        return None
    # 직전 영업일
    d = date.fromisoformat(target_date)
    prev_close = None
    for i in range(1, 8):
        prev = (d - timedelta(days=i)).isoformat()
        if (prev, code) in prices:
            prev_close = prices[(prev, code)]
            break
    if prev_close is None or prev_close == 0:
        return None
    expected = (end_close / prev_close - 1) * 100
    reported = parse_pct(reported_str)
    decimals = _decimals_in(reported_str)
    expected_rounded = round(expected, decimals)
    if abs(expected_rounded - reported) >= 10 ** (-decimals) / 2:
        return Violation(
            file=str(file_path),
            asset=asset,
            period=f"일간({target_date})",
            reported=f"{reported:+.{max(decimals,2)}f}%",
            expected=f"{expected:+.{max(decimals,2)}f}%",
            diff=f"{(reported - expected):+.{max(decimals,2)}f}%P",
            context=context.strip()[:160],
        )
    return None


def _periods_for_file(file_path: Path) -> dict[str, tuple[str, str]]:
    """파일명/경로 → 기간별 (start_date, end_date) 사전.
    Phase 1은 주간만 정확, 일간/월간은 베스트-에포트."""
    full = str(file_path)
    name = file_path.name
    out: dict[str, tuple[str, str]] = {}

    # 주간: 2026-W17.html / 2026-W17_story.html
    m = re.search(r"(\d{4})-W(\d{2})", full)
    if m:
        y, w = int(m.group(1)), int(m.group(2))
        out["WTD"] = weekly_dates(y, w)
        return out

    # 일간: 2026-04-24.html (8자리 날짜가 파일명/경로에 있으면 일간 우선)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", full)
    if m:
        d_iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        d_obj = date.fromisoformat(d_iso)
        prev = (d_obj - timedelta(days=1)).isoformat()
        out["일간"] = (prev, d_iso)
        # 일간 보고서의 WTD/MTD end_date 는 보고서 일자로 cap — 그렇지 않으면 weekly_dates/
        # monthly_dates 가 W/M 마지막 영업일을 반환하고 lookback 으로 미래 종가까지 가져와
        # "현재 시점에서 작성된 본문 +9.30% MTD" 가 "월말 +10.42% MTD" 와 충돌하는 false positive 발생.
        wtd_start, _ = weekly_dates(*d_obj.isocalendar()[:2])
        mtd_start, _ = monthly_dates(d_obj.year, d_obj.month)
        out["WTD"] = (wtd_start, d_iso)
        out["MTD"] = (mtd_start, d_iso)
        out["YTD"] = ytd_dates(d_obj.year, d_iso)
        return out

    # 월간: monthly/2026-04.html
    m = re.search(r"(\d{4})-(\d{2})(?:_|\.|$)", name)
    if m and "monthly" in full:
        y, mo = int(m.group(1)), int(m.group(2))
        out["MTD"] = monthly_dates(y, mo)
        return out

    return out


# ── 빈 Sources 탭 검출 ────────────────────────────────────────────
# 일간/주간/월간 메인 HTML 의 tab-sources 블록이 비어있거나 placeholder/링크 3건 미만이면 위반.
# 사이블링(_story/_pm/_cs/_macro/_sources)은 건너뛴다.
_SOURCES_BLOCK_RE = re.compile(
    r'<div\s+id=["\']tab-sources["\'][^>]*>(.*?)</div><!--\s*/tab-sources\s*-->',
    re.DOTALL,
)
_SOURCES_LINK_RE = re.compile(r'<a\s+href=', re.IGNORECASE)
_MIN_SOURCES_LINKS = 3


def _is_main_report_html(file_path: Path) -> bool:
    name = file_path.name
    if not name.endswith(".html"):
        return False
    SIBLING_SUFFIXES = ("_story.html", "_pm.html", "_cs.html",
                        "_macro.html", "_sources.html", "_ocr.html",
                        "_no-data.pdf", "_no-data.html")
    if any(name.endswith(s) for s in SIBLING_SUFFIXES):
        return False
    parts = file_path.parts
    return "summary" in parts  # only output/summary/* daily/weekly/monthly


def _check_sources_empty(file_path: Path, text: str) -> list[Violation]:
    """tab-sources 가 비어있거나 링크 3건 미만이면 Violation 반환."""
    if not _is_main_report_html(file_path):
        return []
    m = _SOURCES_BLOCK_RE.search(text)
    if not m:
        return []  # 탭 자체가 없는 보고서 (예: 일부 레거시) — 강제하지 않음
    inner = m.group(1)
    inner_stripped = re.sub(r'<!--.*?-->', '', inner, flags=re.DOTALL).strip()
    link_count = len(_SOURCES_LINK_RE.findall(inner))
    if not inner_stripped or "SOURCES_PLACEHOLDER" in inner or link_count < _MIN_SOURCES_LINKS:
        ctx = (inner_stripped[:120] + "...") if inner_stripped else "(empty)"
        return [Violation(
            file=str(file_path),
            asset="tab-sources",
            period="빈 Sources",
            reported=f"링크 {link_count}건",
            expected=f"링크 ≥ {_MIN_SOURCES_LINKS}건 (skill: references/sources.md)",
            diff=f"부족 {_MIN_SOURCES_LINKS - link_count}건",
            context=ctx,
        )]
    return []


def verify(file_path: Path, prices) -> list[Violation]:
    if not file_path.exists():
        return []
    text = file_path.read_text(errors="replace")
    periods = _periods_for_file(file_path)
    violations: list[Violation] = []

    # 0. 빈 Sources 탭 검출 (메인 HTML 만; 사이블링 제외)
    violations.extend(_check_sources_empty(file_path, text))

    # 1. 표 자체 일관성 (마크다운, 3컬럼: 시작/종료/등락) — CSV 없이 산술 검증
    for m in MD_TABLE_3COL.finditer(text):
        asset, start_v, end_v, chg_v = m.group(1), m.group(2), m.group(3), m.group(4)
        try:
            s, e = parse_num(start_v), parse_num(end_v)
            chg = parse_pct(chg_v)
            if s == 0:
                continue
            arithmetic = (e / s - 1) * 100
            if abs(arithmetic - chg) > TABLE_SELF_TOL:  # 정수 시작/종료 반올림 누적 흡수
                violations.append(Violation(
                    file=str(file_path),
                    asset=asset,
                    period="표일관성",
                    reported=f"{chg:+.2f}%",
                    expected=f"{arithmetic:+.2f}% (시작 {s} → 종료 {e})",
                    diff=f"{(chg - arithmetic):+.2f}%P",
                    context=m.group(0).strip()[:160],
                ))
        except (ValueError, ZeroDivisionError):
            continue

    if not periods:
        return violations  # 파일 종류 인식 못 하면 표 검증만 수행

    # 2. KPI 카드
    for m in KPI_HTML_PATTERN.finditer(text):
        asset, period, val = m.group(1), m.group(2), m.group(3)
        if period not in periods:
            continue
        s, e = periods[period]
        ctx = text[max(0, m.start() - 40): m.end() + 40]
        v = _check_pct(asset, period, val, ctx, s, e, prices, file_path,
                       match_start=m.start(), match_end=m.end(), match_text=m.group(0))
        if v:
            violations.append(v)

    # 3. 본문 인라인 — % 패턴
    for m in PCT_PATTERN.finditer(text):
        asset, period, val = m.group(1), m.group(2), m.group(3)
        if period not in periods:
            continue
        s, e = periods[period]
        ctx = text[max(0, m.start() - 40): m.end() + 40]
        v = _check_pct(asset, period, val, ctx, s, e, prices, file_path,
                       match_start=m.start(), match_end=m.end(), match_text=m.group(0))
        if v:
            violations.append(v)

    # 4. 본문 인라인 — bp 패턴
    for m in BP_PATTERN.finditer(text):
        asset, period, val = m.group(1), m.group(2), m.group(3)
        if period not in periods:
            continue
        s, e = periods[period]
        ctx = text[max(0, m.start() - 40): m.end() + 40]
        v = _check_bp(asset, period, val, ctx, s, e, prices, file_path,
                      match_start=m.start(), match_end=m.end(), match_text=m.group(0))
        if v:
            violations.append(v)

    # 4b. 인라인 패턴 — "Gold ... · MTD +2.24%" 처럼 자산과 기간 키워드 사이에 span 등이 끼어있는 경우
    # 이미 위에서 잡힌 위치는 중복 스킵
    seen_positions: set[int] = {v.match_start for v in violations if v.match_start >= 0}
    for m in PCT_INLINE_PATTERN.finditer(text):
        if m.start() in seen_positions:
            continue
        asset, val = m.group(1), m.group(2)
        period = "MTD"
        if period not in periods:
            continue
        s, e = periods[period]
        ctx = text[max(0, m.start() - 40): m.end() + 40]
        v = _check_pct(asset, period, val, ctx, s, e, prices, file_path,
                       match_start=m.start(), match_end=m.end(), match_text=m.group(0))
        if v:
            violations.append(v)
            seen_positions.add(m.start())
    for m in BP_INLINE_PATTERN.finditer(text):
        if m.start() in seen_positions:
            continue
        asset, val = m.group(1), m.group(2)
        period = "MTD"
        if period not in periods:
            continue
        s, e = periods[period]
        ctx = text[max(0, m.start() - 40): m.end() + 40]
        v = _check_bp(asset, period, val, ctx, s, e, prices, file_path,
                      match_start=m.start(), match_end=m.end(), match_text=m.group(0))
        if v:
            violations.append(v)
            seen_positions.add(m.start())

    # 5. HTML <span class="hl-up/down"> 인라인 — 자산명이 span 바로 앞에 있는 케이스
    #    윈도우(직전 300자)에 *명시* period 키워드가 있을 때만 검증.
    #    채권 bp는 명시 키워드 없어도 파일 종류에 따른 default 허용 (yield 변화는 무조건 기간 변화).
    #    % 단위는 명시 키워드 없으면 스킵 → 일간 등락 본문 인용 같은 false positive 회피.
    #
    # 본문(window) 매칭은 엄격 — "주간"/"월간" 단독은 본문 인용("주간 실업수당", "월간 PMI") 으로
    # 자주 등장하므로 PERIOD_HINTS 에서 제외. 헤더(heading) 매칭은 관대 — <h3>주간 누적</h3> 같은
    # 섹션 라벨은 그 박스 전체의 기간 컨텍스트.
    PERIOD_HINTS = {
        "WTD": ("WTD", "주간 누적", "Weekly", "전주 금요일", "5/5 영업일",
                "주간 수익률", "주간 통계", "주간 변동률", "주간 등락"),
        "MTD": ("MTD", "월간 누적", "Monthly", "월초 대비", "월말 대비",
                "월간 수익률", "월간 변동률", "월간 등락"),
        "YTD": ("YTD", "연초 대비", "Year-to-Date", "YearToDate", "연간 누적", "연초 이후"),
    }
    HEADING_PERIOD_HINTS = {
        "WTD": ("WTD", "주간", "Weekly"),
        "MTD": ("MTD", "월간", "Monthly"),
        "YTD": ("YTD", "연초", "Year-to-Date", "YearToDate"),
    }

    full = str(file_path)
    if "weekly/" in full:
        bp_default = "WTD"
    elif "monthly/" in full:
        bp_default = "MTD"
    elif "일간" in periods:
        bp_default = "일간"
    elif "WTD" in periods:
        bp_default = "WTD"
    else:
        bp_default = None

    # WTD/MTD 누적 박스 헤더 — % 변동률은 _data.json.weekly/monthly (롤링 5/21영업일) 를
    # 그대로 표시하는 보고서가 많아 verifier 의 ISO WTD/MTD 정의와 다른 case 가 흔함.
    # 박스 헤더에 이 키워드가 있으면 % 검증 스킵 (채권 bp 는 % → bp 환산 정확도가 높아 계속 검증).
    ROLLING_BOX_HEADING_KEYWORDS = ("주간 누적", "월간 누적", "WTD Progress", "MTD Progress")

    for m in HL_SPAN_PATTERN.finditer(text):
        asset, val, unit = m.group(1), m.group(2), m.group(3)
        # 단락 경계로 자른 윈도우 — 다른 단락의 키워드가 들어오지 않도록
        window = _trim_window_to_paragraph(text, m.start(), m.end())

        # 일간 컨텍스트 시그널 ("4/8(수)" 같은 일자+요일) — 일간 등락 인용으로 보고 검증 스킵
        if DAILY_HINT_PATTERN.search(window):
            continue

        # WTD/MTD 박스 안 % 변동률 — _data.json 롤링 정의 vs ISO 정의 차이로 false-positive 폭증. 스킵.
        if unit == "%":
            heading_full = _nearest_heading_text(text, m.start())
            if heading_full and any(kw in heading_full for kw in ROLLING_BOX_HEADING_KEYWORDS):
                continue

        # 명시 period 키워드: 본문(window) 은 엄격, 헤더(heading) 는 bp 단위에만 관대.
        # 헤더 추가 사유: <h3>주간 누적</h3> 다음 <li>채권: ... <span>+0.9bp</span></li> 형태에서
        # </h3>가 PARA_BOUNDARIES 의 </div> 등으로 차단되어 윈도우에 헤더가 들어오지 않으면 WTD/MTD 인식 불가.
        # % 단위는 헤더 매칭 미적용 — _data.json.weekly 가 롤링 5영업일이라 verifier 의 ISO WTD 와
        # 정의 차이가 있어 false positive 폭증 (4/29 등 회귀 보고서에서 확인).
        heading = _nearest_heading_text(text, m.start()) if unit == "bp" else ""
        period = None
        for p, hints in PERIOD_HINTS.items():
            if p not in periods:
                continue
            if any(h in window for h in hints):
                period = p
                break
            if heading and any(h in heading for h in HEADING_PERIOD_HINTS[p]):
                period = p
                break

        # 채권 bp는 명시 키워드 없어도 파일 default 허용
        if period is None and unit == "bp":
            period = bp_default

        if period is None or period not in periods:
            continue
        s, e = periods[period]
        v = (_check_bp if unit == "bp" else _check_pct)(
            asset, period, val, window, s, e, prices, file_path,
            match_start=m.start(), match_end=m.end(), match_text=m.group(0),
        )
        if v:
            violations.append(v)

    # 5b. T1 종목 일변동률 — Apple/삼성전자 등 14개 핵심 stocks (괄호 종가 없는 케이스)
    #     COMBO 와 중복 방지를 위해 STOCK_DAILY_PATTERN 자체에 negative lookahead 적용
    #     윈도우(직전 300자) 내 인용/forward 키워드 있으면 스킵
    PERIOD_BOX_HEADING_KEYWORDS = ("주간", "월간", "WTD", "MTD", "Weekly", "Monthly", "누적")
    if "일간" in periods:
        _, target_iso = periods["일간"]
        for m in STOCK_DAILY_PATTERN.finditer(text):
            if m.start() in seen_positions:
                continue
            asset, val = m.group(1), m.group(2)
            window = _trim_window_to_paragraph(text, m.start(), m.end())
            # 인용/비교/forward 키워드 가드
            if any(kw in window for kw in CITATION_KEYWORDS):
                continue
            # 다른 일자 인용 (4/8(수) 형식)
            if DAILY_HINT_PATTERN.search(window):
                continue
            # outlook/scenario/risk 컨테이너 안이면 스킵
            if _is_in_forward_container(text, m.start()):
                continue
            # WTD/MTD 박스(<h3>월간 누적</h3>) 안이면 스킵 — 일변동률이 아닌 누적 변동률
            heading = _nearest_heading_text(text, m.start())
            if heading and any(kw in heading for kw in PERIOD_BOX_HEADING_KEYWORDS):
                continue
            v = _check_daily_pct(asset, target_iso, val, window, prices, file_path)
            if v:
                v.match_start = m.start()
                v.match_end = m.end()
                v.match_text = m.group(0)
                violations.append(v)
                seen_positions.add(m.start())

    # 6. COMBO 패턴 — "{자산} ±N%(종가)" 일간 등락 + 종가 묶음
    #    인용/비교/forward 키워드(어제, 전일, →, 이상, 돌파 등)가 윈도우에 있으면 스킵 (false positive 차단)
    for m in COMBO_PATTERN.finditer(text):
        asset, pct_str, close_str = m.group(1), m.group(2), m.group(3)
        window = _trim_window_to_paragraph(text, m.start(), m.end())
        # 인용·비교·forward 키워드 가드
        if any(kw in window for kw in CITATION_KEYWORDS):
            continue
        # forward 컨테이너 (outlook/scenario/risk) 안이면 스킵
        if _is_in_forward_container(text, m.start()):
            continue
        # 윈도우 내 매칭 오프셋 계산 (가장 가까운 날짜 선택용)
        combo_text = m.group(0)
        match_offset_in_window = window.find(combo_text)
        if match_offset_in_window < 0:
            match_offset_in_window = len(window) // 2
        target_date = _resolve_target_date(window, file_path, periods, match_offset_in_window)
        if not target_date:
            continue
        # 일간 등락 검증
        v_pct = _check_daily_pct(asset, target_date, pct_str, window, prices, file_path)
        if v_pct:
            violations.append(v_pct)
        # 종가 검증
        v_close = _check_close(asset, target_date, close_str, window, prices, file_path)
        if v_close:
            violations.append(v_close)

    # NOTE: STANDALONE_CLOSE_PATTERN 은 정밀도 부족(누적 인용·시나리오 트리거·다른 일자 인용을
    # 모두 잡아 false positive 폭증)으로 Phase 2 에서 비활성. COMBO 형태로 작성 권장.

    # 일간 보고서에서는 macro-block 내부 수치를 검증 대상에서 제외 — macro 탭은 주간 단위 narrative
    if _is_daily_report_file(file_path):
        violations = [
            v for v in violations
            if v.match_start < 0 or not _is_in_macro_block(text, v.match_start)
        ]

    return violations


# ── 변경 파일 자동 감지 ─────────────────────────────────────────
def find_changed_files() -> list[Path]:
    """git status / diff 기반 변경 보고서 파일 추출."""
    out: list[Path] = []
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            p = ROOT / line
            if p.suffix in {".html", ".md"} and (
                "output/summary" in line or "output/report" in line
            ):
                out.append(p)
        # 신규 파일 (untracked)
        r2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        for line in r2.stdout.splitlines():
            if not line.strip():
                continue
            p = ROOT / line
            if p.suffix in {".html", ".md"} and (
                "output/summary" in line or "output/report" in line
            ):
                out.append(p)
    except subprocess.CalledProcessError:
        pass
    # 중복 제거
    seen, unique = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


# ── 출력 ────────────────────────────────────────────────────────
def format_human(violations: list[Violation], n_files: int) -> str:
    if not violations:
        return f"[verify] ✓ 위반 없음 (대상 {n_files}개 파일)"
    lines = [f"[verify] ✗ {len(violations)}건 위반 (대상 {n_files}개 파일)", ""]
    for v in violations:
        lines.append(f"  ✗ {Path(v.file).name} :: {v.asset} {v.period}")
        lines.append(f"      보고서: {v.reported}  실제: {v.expected}  차이: {v.diff}")
        lines.append(f"      문맥: {v.context}")
        lines.append("")
    return "\n".join(lines)


def auto_fix(violations: list[Violation]) -> dict[str, int]:
    """위반 항목을 파일에서 직접 교정한다.

    전략:
    - match_start/match_end 가 있는 항목: 원본 match_text 안에서 reported 값을
      expected 값으로 교체 후 파일에 기록.
    - 위치 정보가 없는 항목(표 일관성 등): 스킵 (수동 수정 필요).

    Returns:
        {"fixed": N, "skipped": M}  — 수정/스킵 건수
    """
    # 파일별로 묶어서 처리 (오프셋 shift 방지 위해 뒤에서부터 교체)
    by_file: dict[str, list[Violation]] = {}
    for v in violations:
        if v.match_start < 0 or not v.match_text:
            continue
        by_file.setdefault(v.file, []).append(v)

    fixed = 0
    skipped = len(violations) - sum(len(vs) for vs in by_file.values())

    for fpath_str, vs in by_file.items():
        fpath = Path(fpath_str)
        if not fpath.exists():
            skipped += len(vs)
            continue

        text = fpath.read_text(encoding="utf-8", errors="replace")

        # 뒤에서부터 교체해야 앞쪽 오프셋이 밀리지 않음
        vs_sorted = sorted(vs, key=lambda x: x.match_start, reverse=True)

        for v in vs_sorted:
            orig = v.match_text
            # expected 에서 숫자만 추출 ("+4.58%" → "4.58", "-1.47%" → "-1.47")
            # reported 와 같은 형식(부호+숫자+단위)으로 재조립
            is_bp = v.expected.endswith("bp")
            unit = "bp" if is_bp else "%"

            # expected 문자열에서 순수 숫자 추출
            raw_exp = v.expected.replace("%", "").replace("bp", "").replace("P", "").strip()
            # 부호 표준화 (−/– → -)
            for ch in "−–":
                raw_exp = raw_exp.replace(ch, "-")
            try:
                exp_val = float(raw_exp)
            except ValueError:
                skipped += 1
                print(f"[fix] ⚠ expected 파싱 실패: {v.expected!r} — 스킵 ({Path(fpath_str).name} :: {v.asset} {v.period})")
                continue

            # reported 문자열에서 순수 숫자 추출 (부호 포함)
            raw_rep = v.reported.replace("%", "").replace("bp", "").replace("P", "").strip()
            for ch in "−–":
                raw_rep = raw_rep.replace(ch, "-")
            try:
                rep_val = float(raw_rep)
            except ValueError:
                skipped += 1
                continue

            # 소수 자릿수: reported 기준 유지
            decimals = _decimals_in(v.reported)

            # 새 값 문자열 (부호 포함, 단위 없음 — match_text 안의 숫자 부분만 교체)
            sign = "+" if exp_val >= 0 else ""
            new_val_str = f"{sign}{exp_val:.{decimals}f}"
            # reported 의 부호+숫자 부분 (단위 제외)
            rep_sign = "+" if rep_val >= 0 else ""
            # 부호 문자는 보고서에서 −(U+2212) 또는 -(ASCII) 혼용 가능 → 원본 그대로 찾아야 함
            # match_text 안에서 reported 숫자 값 토큰을 new_val_str 로 교체
            # 안전하게: 원본 텍스트에서 match_text 전체를 new_match_text 로 교체
            old_num_pattern = re.compile(
                r'([+\-−–]?\s*' + re.escape(f"{abs(rep_val):.{decimals}f}") + r')'
            )
            new_match = old_num_pattern.sub(new_val_str, orig, count=1)
            if new_match == orig:
                # 부호 없는 숫자로도 시도
                old_num_pattern2 = re.compile(re.escape(f"{abs(rep_val):.{decimals}f}"))
                new_match = old_num_pattern2.sub(new_val_str, orig, count=1)

            if new_match == orig:
                skipped += 1
                print(f"[fix] ⚠ 교체 패턴 불일치 — 스킵 ({Path(fpath_str).name} :: {v.asset} {v.period}  reported={v.reported!r})")
                continue

            # 파일 텍스트에서 해당 위치의 원본을 교체
            # match_start/end 는 검증 시점 텍스트 기준 — 뒤에서부터 처리하므로 오프셋 유효
            if text[v.match_start:v.match_end] == orig:
                text = text[:v.match_start] + new_match + text[v.match_end:]
                fixed += 1
                print(f"[fix] ✓ {Path(fpath_str).name} :: {v.asset} {v.period}  {v.reported} → {v.expected}")
            else:
                # 오프셋 drift — 전체 텍스트에서 첫 번째 매치로 교체 시도
                idx = text.find(orig)
                if idx >= 0:
                    text = text[:idx] + new_match + text[idx + len(orig):]
                    fixed += 1
                    print(f"[fix] ✓ {Path(fpath_str).name} :: {v.asset} {v.period}  {v.reported} → {v.expected}  (오프셋 drift — 텍스트 검색으로 교체)")
                else:
                    skipped += 1
                    print(f"[fix] ⚠ 원본 텍스트 위치 불일치 — 스킵 ({Path(fpath_str).name} :: {v.asset} {v.period})")
                    continue

        fpath.write_text(text, encoding="utf-8")

    return {"fixed": fixed, "skipped": skipped}


def _send_telegram(violations: list[Violation], n_files: int) -> None:
    """위반 발견 시 Telegram 알림. notify_telegram.send() 재사용."""
    try:
        sys.path.insert(0, str(ROOT))
        from notify_telegram import send as tg_send  # type: ignore
    except ImportError:
        print("[verify] ! notify_telegram 모듈 import 실패 — Telegram 발송 스킵")
        return

    n_show = min(len(violations), 10)
    lines = [
        f"🚨 *보고서 수치 검증 위반 {len(violations)}건* (대상 {n_files}개 파일)",
        "",
    ]
    for v in violations[:n_show]:
        fname = Path(v.file).name
        lines.append(f"`{fname}` :: *{v.asset} {v.period}*")
        lines.append(f"  보고서 `{v.reported}`  →  실제 `{v.expected}`  (차이 `{v.diff}`)")
    if len(violations) > n_show:
        lines.append(f"\n_... 외 {len(violations) - n_show}건_")
    lines.append("")
    lines.append("→ Story 또는 보고서를 ground truth(`history/market_data.csv`)에 맞춰 수정 필요.")
    msg = "\n".join(lines)
    try:
        tg_send(msg)
    except Exception as e:
        print(f"[verify] ! Telegram 발송 실패: {e}")


def _write_log(files: list[Path], violations_before: list[Violation],
               fix_result: dict | None, violations_after: list[Violation]) -> None:
    """상세 검증 로그를 logs/verify_numbers.log에 추가."""
    from datetime import datetime
    log_path = ROOT / "logs" / "verify_numbers.log"
    log_path.parent.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"\n{'='*60}",
        f"  수치 검증 — {ts}",
        f"{'='*60}",
        f"",
        f"대상 파일 ({len(files)}개):",
    ]
    for f in files:
        lines.append(f"  • {f.name}")

    lines.append(f"")
    lines.append(f"[1차 검증] 위반 {len(violations_before)}건")
    for v in violations_before:
        lines.append(f"  ✗ {Path(v.file).name} :: {v.asset} {v.period}")
        lines.append(f"      보고서: {v.reported}  실제: {v.expected}  차이: {v.diff}")

    if fix_result:
        lines.append(f"")
        lines.append(f"[자동 수정] 수정 {fix_result['fixed']}건 / 스킵 {fix_result['skipped']}건")

    lines.append(f"")
    if violations_after:
        lines.append(f"[최종 결과] ✗ 잔여 위반 {len(violations_after)}건")
        for v in violations_after:
            lines.append(f"  ✗ {Path(v.file).name} :: {v.asset} {v.period}")
            lines.append(f"      보고서: {v.reported}  실제: {v.expected}  차이: {v.diff}")
            lines.append(f"      문맥: {v.context}")
    else:
        lines.append(f"[최종 결과] ✓ 위반 없음")

    lines.append("")

    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--auto", action="store_true",
                    help="git diff 기반 변경 파일 자동 감지")
    ap.add_argument("--fix", action="store_true",
                    help="위반 발견 시 CSV ground truth 값으로 자동 수정 후 재검증")
    ap.add_argument("--json", action="store_true",
                    help="JSON 출력 (hooks/CI 용)")
    ap.add_argument("--telegram", action="store_true",
                    help="위반 발견 시 Telegram 알림 발송 (notify_telegram.send 재사용)")
    ap.add_argument("--log", action="store_true",
                    help="상세 로그를 logs/verify_numbers.log에 기록")
    args = ap.parse_args()

    files = list(args.files)
    if args.auto or not files:
        files = find_changed_files()

    if not files:
        if args.json:
            print(json.dumps({"checked": 0, "violations": []}))
        else:
            print("[verify] 검증 대상 파일 없음")
        return 0

    if not CSV_PATH.exists():
        msg = f"[verify] ! CSV 없음: {CSV_PATH}"
        if args.json:
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        return 2

    prices = load_prices(CSV_PATH)
    all_v: list[Violation] = []
    for f in files:
        all_v.extend(verify(f, prices))

    violations_before = list(all_v)
    fix_result = None

    if all_v and args.fix:
        print(f"[fix] 위반 {len(all_v)}건 — 자동 수정 시작")
        fix_result = auto_fix(all_v)
        print(f"[fix] 완료: 수정 {fix_result['fixed']}건 / 스킵 {fix_result['skipped']}건")
        # 재검증
        all_v = []
        for f in files:
            all_v.extend(verify(f, prices))
        if all_v:
            print(f"[fix] ⚠ 재검증 후 잔여 위반 {len(all_v)}건 (수동 확인 필요)")
        else:
            print(f"[verify] ✓ 위반 없음 (자동 수정 후 재검증, 대상 {len(files)}개 파일)")

    if args.json:
        print(json.dumps(
            {"checked": len(files),
             "files": [str(f) for f in files],
             "violations": [v.to_dict() for v in all_v]},
            ensure_ascii=False, indent=2,
        ))
    elif not args.fix or all_v:
        # --fix 성공 시엔 위 메시지로 충분, 실패 잔여분만 출력
        print(format_human(all_v, len(files)))

    if all_v and args.telegram:
        _send_telegram(all_v, len(files))

    # 상세 로그 기록 (--log 또는 --auto 시 자동)
    if args.log or args.auto:
        _write_log(files, violations_before, fix_result, all_v)

    return 1 if all_v else 0


if __name__ == "__main__":
    sys.exit(main())
