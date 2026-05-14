"""generate.py / generate_periodic.py 공통 상수·유틸·Story 함수."""
import os
import re


# ─── 포맷팅 ────────────────────────────────────────────────────────────────

def fmt(val, decimals=2):
    if abs(val) >= 1000:
        return f"{val:,.{decimals}f}"
    return f"{val:.{decimals}f}"

def chg_class(val):
    return "up" if val > 0 else ("down" if val < 0 else "flat")

def chg_sign(val):
    return f"+{val:.2f}%" if val > 0 else f"{val:.2f}%"

def heat_color(val):
    """변동폭에 따른 배경색 (한국식: 상승=빨간계열, 하락=파란계열)"""
    if val >= 3:    return "#fbd5d5"
    if val >= 1.5:  return "#fde8e8"
    if val >= 0.5:  return "#fef2f2"
    if val > 0:     return "#fff5f5"
    if val == 0:    return "#f7f8fa"
    if val > -0.5:  return "#eff6ff"
    if val > -1.5:  return "#dbeafe"
    if val > -3:    return "#bfdbfe"
    return "#93c5fd"

def heat_text(val):
    if val >= 1.5:  return "#991b1b"
    if val > 0:     return "#b91c1c"
    if val == 0:    return "#6b7280"
    if val > -1.5:  return "#1e40af"
    return "#1e3a5f"

def spark_svg(data, w=80, h=24, color="#F58220"):
    """미니 SVG 스파크라인"""
    if not data or len(data) < 2:
        return ""
    mn, mx = min(data), max(data)
    rng = mx - mn if mx != mn else 1
    pts = []
    step = w / (len(data) - 1)
    for i, v in enumerate(data):
        x = round(i * step, 1)
        y = round(h - (v - mn) / rng * (h - 2) - 1, 1)
        pts.append(f"{x},{y}")
    last_y = round(h - (data[-1] - mn) / rng * (h - 2) - 1, 1)
    end_color = "#d92b2b" if data[-1] >= 0 else "#1a5fb4"
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round"/>'
        f'<circle cx="{round((len(data)-1)*step,1)}" cy="{last_y}" r="2.5" fill="{end_color}"/>'
        f'</svg>'
    )


# ─── 한글 라벨 ──────────────────────────────────────────────────────────────

KO_LABELS = {
    "KOSPI": "코스피", "KOSDAQ": "코스닥",
    "S&P500": "S&P500", "NASDAQ": "나스닥", "Russell2K": "러셀2000",
    "STOXX50": "유로스톡스50", "FTSE100": "영국FTSE", "DAX": "독일DAX", "CAC40": "프랑스CAC",
    "Shanghai": "상해종합", "HSI": "항셍", "Nikkei225": "니케이225", "NIFTY50": "인도NIFTY",
    "MSCI EM": "MSCI 신흥국", "TWSE": "대만가권",
    "MSCI World": "MSCI 선진국", "MSCI ACWI": "MSCI 전세계",
    "MSCI LATAM": "MSCI 중남미", "MSCI EMEA": "MSCI 유럽중동",
    "KR CD 91D": "한국 CD 91일", "KR 3Y": "한국 국채3년", "KR 5Y": "한국 국채5년",
    "KR 10Y": "한국 국채10년", "KR 30Y": "한국 국채30년",
    "US 2Y": "미국 국채2년", "US 10Y": "미국 국채10년", "US 30Y": "미국 국채30년",
    "US 10-2 Spread": "미국 장단기 스프레드",
    "KR 10-3 Spread": "한국 장단기 스프레드",
    "AGG": "미국 종합채권", "TLT": "미국 장기국채", "IEI": "미국 중기국채",
    "SHY": "미국 단기국채", "TIP": "미국 물가연동채",
    "LQD": "투자등급 회사채", "HYG": "하이일드 채권", "EMB": "신흥국 채권",
    "DXY": "달러인덱스", "USD/KRW": "달러/원", "EUR/USD": "유로/달러",
    "GBP/USD": "파운드/달러", "AUD/USD": "호주달러", "USD/JPY": "달러/엔", "USD/CNY": "달러/위안",
    "WTI": "WTI유", "Brent": "브렌트유", "Gold": "금", "Silver": "은",
    "Copper": "구리", "Nat Gas": "천연가스",
    "NVIDIA": "엔비디아", "Broadcom": "브로드컴", "Alphabet": "구글", "Amazon": "아마존",
    "META": "메타", "Apple": "애플", "Microsoft": "마이크로소프트",
    "Tesla": "테슬라", "TSMC": "TSMC", "Samsung": "삼성전자",
}


# ─── 정렬 상수 (단일 정본) ──────────────────────────────────────────────────

EQUITY_ORDER = [
    "KOSPI", "KOSDAQ",
    "S&P500", "NASDAQ", "Russell2K",
    "STOXX50", "FTSE100", "DAX", "CAC40",
    "Shanghai", "HSI",
    "Nikkei225",
    "NIFTY50",
]
MSCI_ORDER = ["MSCI World", "MSCI ACWI", "MSCI EM", "MSCI LATAM", "MSCI EMEA"]
BOND_RATE_ORDER = [
    "KR CD 91D", "KR 3Y", "KR 5Y", "KR 10Y", "KR 30Y", "KR 10-3 Spread",
    "US 2Y", "US 10Y", "US 30Y", "US 10-2 Spread",
]
BOND_ETF_ORDER = ["AGG", "TLT", "IEI", "SHY", "TIP", "LQD", "HYG", "EMB"]
FX_ORDER = ["DXY", "USD/KRW", "EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY", "USD/CNY"]
CM_ORDER = ["WTI", "Brent", "Gold", "Silver", "Copper", "Nat Gas"]
ST_ORDER = [
    "NVIDIA", "Broadcom", "Alphabet", "Amazon", "META",
    "Apple", "Microsoft", "Tesla", "TSMC", "Samsung",
]

# ── 시가총액 순 (collectors/stocks_universe.py 의 KR_TOP50/US_TOP50/ASIA_TOP 순서) ──
# Lazy import 로 순환참조 회피
def _load_stock_orders():
    try:
        from collectors.stocks_universe import KR_TOP50, US_TOP50, ASIA_TOP
        kr = [t[2] for t in KR_TOP50]   # 'name' 필드 (data ticker)
        us = [t[2] for t in US_TOP50]
        asia = [t[2] for t in ASIA_TOP]
        kr_ko = {t[2]: t[4] for t in KR_TOP50}  # name → name_ko
        us_en = {t[2]: t[4] for t in US_TOP50}  # name → name_en
        return kr, us, asia, kr_ko, us_en
    except Exception:
        return [], [], [], {}, {}


KR_STOCK_ORDER, US_STOCK_ORDER, ASIA_STOCK_ORDER, _KR_KO_LABELS, _US_EN_LABELS = _load_stock_orders()
# 기본 표시 갯수 (시총 상위 N종)
KR_STOCK_TOP_N = 20
US_STOCK_TOP_N = 20
ASIA_STOCK_TOP_N = 20

# KO_LABELS 에 KR_TOP50 한글명 자동 등록 (덮어쓰지 않음)
for _en, _ko in _KR_KO_LABELS.items():
    KO_LABELS.setdefault(_en, _ko)


DATA_SOURCES = {
    "주식(Equity)":           "yfinance · FinanceDataReader · investiny",
    "MSCI 지수":              "yfinance (ETF proxy)",
    "채권·금리(Bonds & Rates)": "investing.com(US 2Y·10Y·Spread) · ECOS(한국은행)",
    "채권 ETF(Bond ETF)":     "yfinance",
    "환율(FX)":               "investiny(investing.com) · FinanceDataReader",
    "원자재(Commodities)":    "investiny(investing.com) · yfinance · NYMEX/COMEX/ICE front-month 선물",
    "주요 종목(Major Stocks)": "yfinance",
    "한국 주식": "FinanceDataReader · KOSPI 시총순",
    "미국 주식": "yfinance · S&P500 시총순",
    "기타 종목(ADR · HK)": "yfinance",
}


# ─── Story 탭 관리 ──────────────────────────────────────────────────────────

DAILY_TAB_SPECS = [
    ("story", "STORY_CONTENT_PLACEHOLDER", "_story"),
    ("cs",    "CS_STORY_PLACEHOLDER",      "_cs"),
    ("pm",    "PM_STORY_PLACEHOLDER",      "_pm"),
    ("macro", "MACRO_EVENTS_PLACEHOLDER",  "_macro"),
    ("sources", "SOURCES_PLACEHOLDER",     "_sources"),
]

PERIODIC_TAB_SPECS = [
    ("story", "STORY_CONTENT_PLACEHOLDER", "_story"),
    ("cs",    "CS_STORY_PLACEHOLDER",      "_cs"),
    ("pm",    "PM_STORY_PLACEHOLDER",      "_pm"),
    ("sources", "SOURCES_PLACEHOLDER",     "_sources"),
]

_TAB_RE = re.compile(
    r'<div id="tab-(?P<tab>[^"]+)" class="tab-panel(?:\s+active)?">\s*\n(?P<content>.*?)\n</div><!-- /tab-\1 -->',
    re.DOTALL,
)


def extract_tab(html: str, tab: str) -> str:
    """HTML에서 특정 탭의 내용을 추출. 없으면 빈 문자열."""
    m = re.search(
        rf'<div id="tab-{tab}" class="tab-panel(?:\s+active)?">\s*\n(.*?)\n</div><!-- /tab-{tab} -->',
        html, re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def save_story_files(html_path: str, html_content: str, tab_specs: list, *, log_fn=None):
    """Story/CS/PM 등 탭 내용을 sibling 파일로 저장. placeholder 상태면 skip."""
    base, ext = os.path.splitext(html_path)
    for tab, placeholder, suffix in tab_specs:
        content = extract_tab(html_content, tab)
        if not content or placeholder in content:
            continue
        target = f"{base}{suffix}{ext}"
        with open(target, "w") as f:
            f.write(content)
        if log_fn:
            log_fn(f"  Tab saved: {os.path.basename(target)}")


def inject_existing_story(path: str, new_html: str, tab_specs: list) -> str:
    """기존 파일의 탭 내용을 새 HTML placeholder에 주입. 변경된 HTML 반환."""
    old_content = ""
    if os.path.exists(path):
        with open(path) as f:
            old_content = f.read()

    for tab, placeholder, suffix in tab_specs:
        preserved = ""
        if old_content:
            content = extract_tab(old_content, tab)
            if content and placeholder not in content:
                preserved = content
        if not preserved:
            base, ext = os.path.splitext(path)
            sibling = f"{base}{suffix}{ext}"
            if os.path.exists(sibling):
                with open(sibling) as f:
                    sib = f.read().strip()
                if sib and placeholder not in sib:
                    preserved = sib
        if preserved:
            new_html = new_html.replace(f"<!-- {placeholder} -->", preserved)

    return new_html


def ordered(items: dict, order: list) -> list:
    """order 리스트 순서대로 정렬, 없는 항목은 뒤에 추가."""
    idx = {name: i for i, name in enumerate(order)}
    return sorted(items.items(), key=lambda x: idx.get(x[0], 999))
