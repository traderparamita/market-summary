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
    .venv/bin/python scripts/verify_report_numbers.py --auto      # git diff 기반 자동
    .venv/bin/python scripts/verify_report_numbers.py --json      # JSON (hooks 용)

Exit code: 0 = pass, 1 = violation
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

    def to_dict(self):
        return asdict(self)


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
PCT_PATTERN = re.compile(
    rf"\b({_ALIAS_ALT})\s+(WTD|MTD|YTD)\s*[:：]?\s*([+\-−–]?\d+\.?\d*)\s*%"
)
BP_PATTERN = re.compile(
    rf"\b({_ALIAS_ALT})\s+(WTD|MTD|YTD)\s*[:：]?\s*([+\-−–]?\d+\.?\d*)\s*bp"
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

# 단락 경계 — HL_SPAN 윈도우를 다른 단락에서 차단
# (heading 태그 </h1>~</h6>는 제외 — 헤더의 "WTD" 같은 라벨이 그 섹션의 컨텍스트를 제공해야 하므로)
PARA_BOUNDARIES = ('<br><br>', '<br /><br />', '<br/><br/>', '</p>', '</li>', '</div>')

# 일간 컨텍스트 시그널 — "4/8(수)" 같이 일자+한글요일 명시. 매칭되면 그 span은 일간 등락으로 간주 → 검증 스킵
DAILY_HINT_PATTERN = re.compile(r'\d{1,2}/\d{1,2}\s*\([월화수목금토일]\)')


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
        # 표시 자릿수에 맞춰 반올림한 CSV 값과 정확 일치 안 함
        diff = reported - expected
        return Violation(
            file=str(file_path),
            asset=asset,
            period=period,
            reported=f"{reported:+.{max(decimals,2)}f}%",
            expected=f"{expected:+.{max(decimals,2)}f}%",
            diff=f"{diff:+.{max(decimals,2)}f}%P",
            context=context.strip()[:160],
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
) -> Violation | None:
    code = ASSET_ALIASES.get(asset)
    if not code or code not in BOND_CODES:
        return None
    p_start = get_close(prices, start_d, code)
    p_end = get_close(prices, end_d, code)
    if p_start is None or p_end is None:
        return None
    expected = (p_end - p_start) * 100  # yield ΔbpYY
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
        )
    return None


def _resolve_target_date(window: str, file_path: Path,
                          periods: dict[str, tuple[str, str]]) -> str | None:
    """본문 윈도우에서 일자 명시(`4/8(수)`)가 있으면 그 일자.
    명시 없으면 *일간 보고서만* 그 날로 fallback. 주간/월간은 None 반환(검증 스킵)."""
    m = DATE_INLINE_PATTERN.search(window)
    if m:
        my = re.search(r"(\d{4})", str(file_path))
        if my:
            try:
                return date(int(my.group(1)), int(m.group(1)), int(m.group(2))).isoformat()
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
        out["WTD"] = weekly_dates(*d_obj.isocalendar()[:2])
        out["MTD"] = monthly_dates(d_obj.year, d_obj.month)
        out["YTD"] = ytd_dates(d_obj.year, d_iso)
        return out

    # 월간: monthly/2026-04.html
    m = re.search(r"(\d{4})-(\d{2})(?:_|\.|$)", name)
    if m and "monthly" in full:
        y, mo = int(m.group(1)), int(m.group(2))
        out["MTD"] = monthly_dates(y, mo)
        return out

    return out


def verify(file_path: Path, prices) -> list[Violation]:
    if not file_path.exists():
        return []
    text = file_path.read_text(errors="replace")
    periods = _periods_for_file(file_path)
    violations: list[Violation] = []

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
        v = _check_pct(asset, period, val, ctx, s, e, prices, file_path)
        if v:
            violations.append(v)

    # 3. 본문 인라인 — % 패턴
    for m in PCT_PATTERN.finditer(text):
        asset, period, val = m.group(1), m.group(2), m.group(3)
        if period not in periods:
            continue
        s, e = periods[period]
        ctx = text[max(0, m.start() - 40): m.end() + 40]
        v = _check_pct(asset, period, val, ctx, s, e, prices, file_path)
        if v:
            violations.append(v)

    # 4. 본문 인라인 — bp 패턴
    for m in BP_PATTERN.finditer(text):
        asset, period, val = m.group(1), m.group(2), m.group(3)
        if period not in periods:
            continue
        s, e = periods[period]
        ctx = text[max(0, m.start() - 40): m.end() + 40]
        v = _check_bp(asset, period, val, ctx, s, e, prices, file_path)
        if v:
            violations.append(v)

    # 5. HTML <span class="hl-up/down"> 인라인 — 자산명이 span 바로 앞에 있는 케이스
    #    윈도우(직전 300자)에 *명시* period 키워드가 있을 때만 검증.
    #    채권 bp는 명시 키워드 없어도 파일 종류에 따른 default 허용 (yield 변화는 무조건 기간 변화).
    #    % 단위는 명시 키워드 없으면 스킵 → 일간 등락 본문 인용 같은 false positive 회피.
    PERIOD_HINTS = {
        "WTD": ("WTD", "주간", "Weekly", "전주 금요일", "5/5 영업일", "주간 수익률", "주간 통계"),
        "MTD": ("MTD", "월간", "Monthly", "월초", "월말", "월간 수익률"),
        "YTD": ("YTD", "연초", "Year-to-Date", "YearToDate", "연간 누적"),
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

    for m in HL_SPAN_PATTERN.finditer(text):
        asset, val, unit = m.group(1), m.group(2), m.group(3)
        # 단락 경계로 자른 윈도우 — 다른 단락의 키워드가 들어오지 않도록
        window = _trim_window_to_paragraph(text, m.start(), m.end())

        # 일간 컨텍스트 시그널 ("4/8(수)" 같은 일자+요일) — 일간 등락 인용으로 보고 검증 스킵
        if DAILY_HINT_PATTERN.search(window):
            continue

        # 명시 period 키워드 (잘린 단락 안에서)
        period = None
        for p, hints in PERIOD_HINTS.items():
            if p not in periods:
                continue
            if any(h in window for h in hints):
                period = p
                break

        # 채권 bp는 명시 키워드 없어도 파일 default 허용
        if period is None and unit == "bp":
            period = bp_default

        if period is None or period not in periods:
            continue
        s, e = periods[period]
        v = (_check_bp if unit == "bp" else _check_pct)(
            asset, period, val, window, s, e, prices, file_path
        )
        if v:
            violations.append(v)

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
        target_date = _resolve_target_date(window, file_path, periods)
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--auto", action="store_true",
                    help="git diff 기반 변경 파일 자동 감지")
    ap.add_argument("--json", action="store_true",
                    help="JSON 출력 (hooks/CI 용)")
    ap.add_argument("--telegram", action="store_true",
                    help="위반 발견 시 Telegram 알림 발송 (notify_telegram.send 재사용)")
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

    if args.json:
        print(json.dumps(
            {"checked": len(files),
             "files": [str(f) for f in files],
             "violations": [v.to_dict() for v in all_v]},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(format_human(all_v, len(files)))

    if all_v and args.telegram:
        _send_telegram(all_v, len(files))

    return 1 if all_v else 0


if __name__ == "__main__":
    sys.exit(main())
