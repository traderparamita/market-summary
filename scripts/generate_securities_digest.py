"""주간 증권 리서치 다이제스트 생성기.

이번 주 미래에셋증권 상세분석 보고서를 OpenAI GPT-4o로 분석해
3개 핵심 투자 테마를 선정하고, PDF 본문 기반 상세 분석과 출처를 포함한 HTML 리포트를 생성.

흐름:
  1. S3 스캔 → 이번 주 보고서 목록
  2. GPT-4o: 제목 기반 테마 3개 + 관련 보고서 인덱스 선정 (function calling)
  3. GPT-4o Vision: 테마별 PDF 앞 2페이지 이미지 →
     { overview, points: [...], insight } 구조 JSON 반환
  4. HTML 렌더링 → output/research/securities/

Output:
    output/research/securities/digest_YYYY-WXX.html
    output/research/securities/digest_latest.html
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from openai import OpenAI
from pdf2image import convert_from_path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

from generate_securities_index import scan_s3  # noqa: E402

OUTPUT_DIR = ROOT / "output" / "research" / "securities"
MODEL = "gpt-4o"
S3_BUCKET = "mai-life-fund-documents-533370893966-ap-northeast-2-an"
S3_REGION = "ap-northeast-2"
MAX_PDFS_PER_THEME = 4
PDF_PAGES = 4

# ── 변액보험 펀드 카탈로그 ────────────────────────────────────────────────────
# (code, name, category) — 테마 분석 시 관련 펀드 매칭에 사용
FUND_CATALOG = [
    # 국내주식
    ("N100", "주식성장형Ⅱ", "국내주식"),
    ("N110", "프리미엄포커스", "국내주식"),
    ("N120", "ETF국내신성장", "국내주식"),
    ("N130", "인덱스주식형", "국내주식"),
    ("N140", "가치주식형", "국내주식"),
    ("N150", "AI국내주식전략", "국내주식/AI"),
    ("N160", "ETF국내주식", "국내주식"),
    ("N1A0", "성장형", "국내혼합"),
    ("N1B0", "혼합형", "국내혼합"),
    ("N1C0", "안정형", "국내혼합"),
    ("N1D0", "주식형", "국내주식"),
    ("N1E0", "배당주식", "국내주식/배당"),
    ("N1F0", "가치주식", "국내주식/가치"),
    ("N1G0", "성장섹터배분", "국내주식/섹터"),
    ("N1H0", "삼성그룹주플러스", "국내주식/그룹주"),
    ("N1J0", "인덱스성장", "국내주식"),
    ("N1K0", "인덱스주식", "국내주식"),
    ("N1M0", "코리아인덱스", "국내주식"),
    ("N1N0", "액티브주식", "국내주식"),
    # 이머징/아시아
    ("N200", "이머징마켓주식", "이머징"),
    ("N210", "브릭스주식", "이머징/브릭스"),
    ("N220", "아시아그레이트컨슈머", "아시아/소비"),
    ("N230", "AP컨슈머", "아시아/소비"),
    ("N240", "중국본토주식", "중국"),
    ("N250", "차이나주식성장", "중국"),
    ("N260", "인도주식", "인도"),
    ("N270", "베트남주식", "베트남"),
    ("N2A0", "아시아주식", "아시아"),
    ("N2B0", "친디아주식", "중국/인도"),
    ("N2C0", "아시아인프라", "아시아/인프라"),
    ("N2D0", "이머징네비게이터", "이머징"),
    ("N2E0", "A+차이나", "중국"),
    # 선진국
    ("N300", "선진마켓주식", "선진국"),
    ("N310", "선진국인컴", "선진국/인컴"),
    ("N320", "일본주식", "일본"),
    ("N330", "유럽주식", "유럽"),
    ("N340", "ETF글로벌주식", "글로벌"),
    ("N380", "미국주식", "미국"),
    ("N390", "ETF글로벌AI테크", "글로벌/AI"),
    ("N3A0", "유럽주식", "유럽"),
    ("N3B0", "유럽주식(H)", "유럽"),
    ("N3C0", "미국인컴앤그로쓰", "미국/인컴"),
    ("N3D0", "미국인컴앤그로쓰(H)", "미국/인컴"),
    # 글로벌 테마
    ("N400", "글로벌성장주식", "글로벌"),
    ("N410", "글로벌컨슈머", "글로벌/소비"),
    ("N420", "글로벌인컴", "글로벌/인컴"),
    ("N430", "글로벌멀티전략", "글로벌"),
    ("N470", "글로벌헬스케어", "글로벌/헬스케어"),
    ("N480", "롱숏전략", "대안"),
    ("N490", "글로벌인덱스주식", "글로벌"),
    ("N4A0", "해외성장", "글로벌"),
    ("N4B0", "글로벌성장산업재", "글로벌/산업재"),
    ("N4C0", "글로벌멀티인컴", "글로벌/인컴"),
    ("N4D0", "글로벌신성장액티브", "글로벌"),
    ("N4F0", "글로벌IT소프트웨어", "글로벌/IT"),
    ("N4G0", "글로벌ESG", "글로벌/ESG"),
    ("N4H0", "[인덱스ETF]미국나스닥100", "미국/나스닥"),
    ("N4I0", "[인덱스 ETF] 미국S&P500", "미국/S&P"),
    ("N4J0", "[인덱스 ETF] 미국S&P500(H)", "미국/S&P"),
    # 국내채권
    ("N500", "국내채권", "국내채권"),
    ("N510", "MMF", "국내단기"),
    ("N520", "ETF국내채권", "국내채권"),
    ("N530", "장기국내채권", "국내채권/장기"),
    ("N5A0", "MMF형", "국내단기"),
    ("N5B0", "채권형", "국내채권"),
    # 글로벌채권
    ("N600", "글로벌채권형Ⅱ", "글로벌채권"),
    ("N610", "글로벌채권토탈리턴", "글로벌채권"),
    ("N620", "글로벌채권매크로전략", "글로벌채권"),
    ("N630", "이머징마켓채권형", "이머징채권"),
    ("N640", "이머징국채", "이머징채권"),
    ("N650", "글로벌하이일드", "하이일드"),
    ("N660", "미국하이일드", "하이일드"),
    ("N680", "단기하이일드", "하이일드"),
    ("N690", "선진국투자등급회사채권", "글로벌채권/IG"),
    ("N6A0", "미국채권", "미국채권"),
    ("N6B0", "글로벌토탈리턴", "글로벌채권"),
    ("N6C0", "글로벌하이일드", "하이일드"),
    ("N6D0", "이머징마켓채권", "이머징채권"),
    ("N6E0", "듀얼타겟", "글로벌채권"),
    ("N6F0", "글로벌메자닌채권", "글로벌채권"),
    ("N700", "ETF글로벌채권", "글로벌채권"),
    ("N720", "글로벌채권형Ⅱ(UH)", "글로벌채권/UH"),
    ("N730", "글로벌채권매크로전략(UH)", "글로벌채권/UH"),
    ("N740", "글로벌하이일드(UH)", "하이일드/UH"),
    ("N750", "달러MMF(UH)", "달러단기"),
    ("N760", "달러미국채(UH)", "미국채권/UH"),
    ("N770", "미국국채", "미국채권"),
    # 대안/실물
    ("N900", "글로벌커머더티주식", "원자재"),
    ("N910", "글로벌인프라부동산", "인프라/부동산"),
    ("N920", "골드투자형", "금"),
    ("N9A0", "TDF2035", "TDF"),
    ("N9B0", "라이프사이클2025", "라이프사이클"),
    ("N9C0", "라이프사이클2015", "라이프사이클"),
    ("N9F0", "글로벌커머더티", "원자재"),
    ("N9H0", "퓨쳐액세스 A형", "멀티에셋"),
    ("N9J0", "퓨쳐액세스 B형", "멀티에셋"),
    ("N9K0", "목표수익 추구형 M(중립)", "목표수익"),
    ("N9M0", "목표수익 추구형 A(적극)", "목표수익"),
    ("N9N0", "목표수익 추구형 S(안정)", "목표수익"),
    # ── 퇴직플랜 (B시리즈) ──
    ("B101", "퇴직플랜 국내채권", "퇴직/국내채권"),
    ("B102", "퇴직플랜 국내배당", "퇴직/국내배당"),
    ("B105", "퇴직플랜 국내배당안정(채혼)", "퇴직/채혼"),
    ("B107", "퇴직플랜 주식안정(채혼)", "퇴직/채혼"),
    ("B108", "퇴직플랜 친디아안정(채혼)", "퇴직/중국인도"),
    ("B109", "퇴직플랜 아시아퍼시픽안정(채혼)", "퇴직/아시아"),
    ("B113", "퇴직플랜 LifeCycle2030G", "퇴직/라이프사이클"),
    ("B114", "퇴직플랜 LifeCycle3040G", "퇴직/라이프사이클"),
    ("B115", "퇴직플랜 LifeCycle4050G", "퇴직/라이프사이클"),
    ("B120", "퇴직플랜 [인덱스ETF]미국나스닥100", "퇴직/미국나스닥"),
    ("B121", "퇴직플랜 [인덱스ETF]미국S&P500", "퇴직/미국S&P"),
    ("B122", "퇴직플랜 ETF글로벌신성장", "퇴직/글로벌"),
    ("B125", "퇴직플랜 글로벌성장", "퇴직/글로벌"),
    ("B126", "퇴직플랜 글로벌IT소프트웨어", "퇴직/IT"),
    ("B127", "퇴직플랜 인도주식", "퇴직/인도"),
    ("B128", "퇴직플랜 달러미국국채(UH)", "퇴직/미국채권"),
    ("B129", "퇴직플랜 달러MMF(UH)", "퇴직/달러단기"),
    # ── 유니버설 (U시리즈) ──
    ("U001", "채권형", "유니버설/채권"),
    ("U002", "단기채권", "유니버설/단기"),
    ("U102", "채권형", "유니버설/채권"),
    ("U104", "글로벌채권", "유니버설/글로벌채권"),
    ("U201", "혼합안정", "유니버설/혼합"),
    ("U202", "채권혼합", "유니버설/채혼"),
    ("U204", "친디아안정", "유니버설/중국인도"),
    ("U301", "혼합성장", "유니버설/혼합"),
    ("U302", "주식혼합", "유니버설/주식혼합"),
    ("U304", "인디아주식안정성장", "유니버설/인도"),
    ("U305", "배당주안정성장", "유니버설/배당"),
    ("U401", "MMF형", "유니버설/단기"),
    ("U402", "주식성장형", "유니버설/국내주식"),
    ("U404", "차이나주식안정성장", "유니버설/중국"),
    ("U405", "주식안정성장", "유니버설/국내주식"),
    ("U407", "글로벌컨슈머안정성장", "유니버설/글로벌소비"),
    ("U502", "인덱스혼합", "유니버설/인덱스"),
    ("U504", "친디아안정성장", "유니버설/중국인도"),
    ("U601", "글로벌멀티전략혼합형", "유니버설/글로벌"),
    ("U602", "AP 주식혼합", "유니버설/아시아"),
    ("U604", "AP Q펀드", "유니버설/아시아"),
    ("U605", "AP주식안정성장", "유니버설/아시아"),
    ("U606", "AP컨슈머주식안정성장", "유니버설/아시아소비"),
    ("U607", "코친디아포커스7", "유니버설/중국인도"),
    ("U608", "미래에셋글로벌인사이트", "유니버설/글로벌"),
    ("U609", "유브릭스주식안정성장", "유니버설/이머징"),
    ("U701", "글로벌채권매크로", "유니버설/글로벌채권"),
    ("U702", "이머징마켓채권", "유니버설/이머징채권"),
    ("U703", "글로벌하이일드채권", "유니버설/하이일드"),
    ("U704", "달러MMF형", "유니버설/달러단기"),
    # ── V시리즈 ──
    ("V001", "채권형", "V/채권"),
    ("V102", "채권형", "V/채권"),
    ("V201", "혼합형", "V/혼합"),
    ("V202", "주식안정", "V/국내주식"),
    ("V302", "배당주안정성장", "V/배당"),
    ("V402", "주식안정성장형", "V/국내주식"),
    ("V407", "글로벌컨슈머섹터안정성장", "V/글로벌소비"),
    ("V602", "AP주식안정성장", "V/아시아"),
    ("V603", "글로벌인사이트", "V/글로벌"),
    # ── W시리즈 ──
    ("W003", "단기채권", "W/단기"),
    ("W102", "채권형", "W/채권"),
    ("W103", "채권형", "W/채권"),
    ("W104", "안심채권", "W/채권"),
    ("W111", "글로벌채권", "W/글로벌채권"),
    ("W203", "채권혼합형", "W/채혼"),
    ("W204", "주식안정", "W/국내주식"),
    ("W210", "주식혼합", "W/주식혼합"),
    ("W211", "코리아블루칩", "W/국내대형"),
    ("W302", "주식혼합", "W/주식혼합"),
    ("W303", "주식혼합", "W/주식혼합"),
    ("W304", "배당주안정", "W/배당"),
    ("W306", "인디아주식안정", "W/인도"),
    ("W307", "AP컨슈머안정", "W/아시아소비"),
    ("W310", "글로벌인사이트혼합", "W/글로벌"),
    ("W311", "AP컨슈머혼합", "W/아시아소비"),
    ("W402", "주식성장", "W/국내주식"),
    ("W403", "주식성장", "W/국내주식"),
    ("W406", "차이나안정", "W/중국"),
    ("W407", "글로벌컨슈머혼합", "W/글로벌소비"),
    ("W410", "브릭스혼합", "W/이머징"),
    ("W502", "인덱스혼합", "W/인덱스"),
    ("W503", "인덱스혼합", "W/인덱스"),
    ("W506", "AP Q펀드", "W/아시아"),
    ("W510", "동유럽혼합", "W/유럽"),
    ("W602", "AP주식혼합", "W/아시아"),
    ("W603", "AP주식혼합", "W/아시아"),
    ("W604", "친디아안정", "W/중국인도"),
    ("W607", "AP주식안정", "W/아시아"),
    ("W608", "코친디아포커스7 주식안정", "W/중국인도"),
    ("W609", "AP부동산", "W/아시아부동산"),
    ("W610", "코친디아포커스7혼합", "W/중국인도"),
    ("W701", "글로벌채권매크로전략", "W/글로벌채권"),
    ("W702", "이머징마켓채권", "W/이머징채권"),
    ("W704", "달러MMF(UH)", "W/달러단기"),
    ("W710", "인덱스혼합50", "W/인덱스"),
    ("W801", "글로벌멀티전략혼합", "W/글로벌"),
]

FUND_CATALOG_TEXT = "\n".join(
    f"[{code}] {name} ({cat})" for code, name, cat in FUND_CATALOG
)

# ── 토큰 사용량 추적 ──────────────────────────────────────────────────────────
_token_totals: dict[str, int] = {"prompt": 0, "completion": 0}


def _track_usage(resp) -> None:
    usage = getattr(resp, "usage", None)
    if usage:
        _token_totals["prompt"] += getattr(usage, "prompt_tokens", 0)
        _token_totals["completion"] += getattr(usage, "completion_tokens", 0)


# ── function schemas ──────────────────────────────────────────────────────────

THEME_FUNCTION = {
    "name": "set_weekly_themes",
    "description": "이번 주 핵심 투자 테마 목록 설정",
    "parameters": {
        "type": "object",
        "properties": {
            "themes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "테마명 (15자 이내)"},
                        "report_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "관련 보고서 번호 (0-indexed, 최대 4개)",
                        },
                    },
                    "required": ["name", "report_indices"],
                },
            }
        },
        "required": ["themes"],
    },
}

DETAIL_FUNCTION = {
    "name": "set_theme_detail",
    "description": "테마 상세 분석 내용 설정",
    "parameters": {
        "type": "object",
        "properties": {
            "overview": {
                "type": "string",
                "description": "이번 주 시장 맥락에서 이 테마의 현황 요약 (3-4문장, 반드시 보고서의 구체적 수치·종목명 포함)",
            },
            "points": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 6,
                "description": "보고서에서 추출한 핵심 포인트 (각 1-2문장, 수치·목표가·종목명 필수 포함)",
            },
            "insight": {
                "type": "string",
                "description": "변액보험 상담사가 고객에게 전달할 수 있는 시사점 (3-4문장, 구체적 섹터·자산 방향성 포함)",
            },
            "related_funds": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "펀드 코드 (예: N150)"},
                        "relevance": {"type": "string", "description": "이 테마와 해당 펀드의 연관 이유 (15자 이내)"},
                    },
                    "required": ["code", "relevance"],
                },
                "minItems": 1,
                "maxItems": 8,
                "description": "이 테마와 직접 관련된 변액보험 펀드 코드 목록",
            },
        },
        "required": ["overview", "points", "insight", "related_funds"],
    },
}

# ── helpers ───────────────────────────────────────────────────────────────────


def get_week_range(ref_date: datetime | None = None) -> tuple[datetime, datetime]:
    today = ref_date or datetime.now()
    days_since_friday = (today.weekday() - 4) % 7 or 7
    friday = today - timedelta(days=days_since_friday)
    monday = friday - timedelta(days=4)
    return (
        monday.replace(hour=0, minute=0, second=0, microsecond=0),
        friday.replace(hour=23, minute=59, second=59, microsecond=0),
    )


def filter_week(rows: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [r for r in rows if r["date"] and start <= r["date"] <= end]


def pdf_to_images_b64(s3_client, s3_key: str, n_pages: int = PDF_PAGES) -> list[str]:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        s3_client.download_fileobj(S3_BUCKET, s3_key, f)
        tmp = f.name
    try:
        images = convert_from_path(tmp, dpi=150, first_page=1, last_page=n_pages)
        result = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
            result.append(base64.b64encode(buf.getvalue()).decode())
        return result
    finally:
        Path(tmp).unlink(missing_ok=True)


# ── GPT calls ─────────────────────────────────────────────────────────────────


def select_themes(client: OpenAI, reports: list[dict], week_label: str) -> list[dict]:
    """제목 목록 → 테마 3개 + 관련 보고서 인덱스."""
    lines = [f"이번 주({week_label}) 미래에셋증권 보고서 {len(reports)}건:\n"]
    for i, r in enumerate(reports):
        date_str = r["date"].strftime("%m/%d") if r["date"] else "??"
        lines.append(f"{i}. [{date_str}] {r['title']}")

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "증권 리서치 편집장으로서, 보고서 제목 목록을 보고 "
                    "이번 주 핵심 투자 테마를 최대 3개 선정하고 "
                    "각 테마에 가장 관련성 높은 보고서 번호를 최대 4개 지정하세요."
                ),
            },
            {"role": "user", "content": "\n".join(lines)},
        ],
        tools=[{"type": "function", "function": THEME_FUNCTION}],
        tool_choice={"type": "function", "function": {"name": "set_weekly_themes"}},
    )
    _track_usage(resp)
    msg = resp.choices[0].message
    if msg.tool_calls:
        return json.loads(msg.tool_calls[0].function.arguments).get("themes", [])
    return []


def _load_week_market_context(end_date: datetime) -> str:
    """해당 주 금요일 기준 _data.json에서 시장 컨텍스트를 추출."""
    friday = end_date.date() if hasattr(end_date, 'date') else end_date
    data_path = (
        ROOT / "output" / "summary"
        / friday.strftime("%Y-%m")
        / f"{friday}_data.json"
    )
    if not data_path.exists():
        # 금요일 데이터 없으면 목~수 순으로 탐색
        for offset in range(1, 5):
            alt = friday - timedelta(days=offset)
            alt_path = (
                ROOT / "output" / "summary"
                / alt.strftime("%Y-%m")
                / f"{alt}_data.json"
            )
            if alt_path.exists():
                data_path = alt_path
                break
        else:
            return ""

    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        eq = data.get("equity", {})
        comm = data.get("commodity", {})
        bond = data.get("bond", {})
        fx = data.get("fx", {})

        def _v(cat, key, field="close"):
            return cat.get(key, {}).get(field, "?")

        def _d(cat, key):
            v = cat.get(key, {}).get("daily", "?")
            return f"{v:+.2f}%" if isinstance(v, (int, float)) else str(v)

        lines = [
            f"[이번 주 시장 현황 — {data_path.stem} 기준]",
            f"KOSPI {_v(eq,'KOSPI')} ({_d(eq,'KOSPI')}), KOSDAQ {_v(eq,'KOSDAQ')} ({_d(eq,'KOSDAQ')})",
            f"S&P500 {_v(eq,'S&P500')} ({_d(eq,'S&P500')}), NASDAQ {_v(eq,'NASDAQ')} ({_d(eq,'NASDAQ')})",
            f"Nikkei {_v(eq,'NIKKEI225')} ({_d(eq,'NIKKEI225')}), HSI {_v(eq,'HSI')} ({_d(eq,'HSI')})",
            f"WTI ${_v(comm,'WTI')} ({_d(comm,'WTI')}), Gold ${_v(comm,'Gold')} ({_d(comm,'Gold')})",
            f"US 10Y {_v(bond,'US 10Y')}%, DXY {_v(fx,'DXY')} ({_d(fx,'DXY')})",
            f"USD/KRW {_v(fx,'USD/KRW')} ({_d(fx,'USD/KRW')})",
        ]
        return "\n".join(lines)
    except Exception:
        return ""


def analyze_theme_detail(
    client: OpenAI,
    theme_name: str,
    reports_subset: list[dict],
    s3_client,
    market_context: str = "",
) -> dict:
    """PDF Vision → { overview, points, insight } 구조 반환."""
    context_block = f"\n\n{market_context}\n\n" if market_context else ""
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"'{theme_name}' 테마 관련 미래에셋증권 분석 보고서입니다. "
                "각 보고서의 핵심 내용을 종합해 분석해 주세요. "
                "수치와 종목명이 보이면 구체적으로 언급하세요."
                f"{context_block}"
            ),
        }
    ]

    loaded = 0
    for r in reports_subset[:MAX_PDFS_PER_THEME]:
        try:
            images_b64 = pdf_to_images_b64(s3_client, r["key"])
            content.append({
                "type": "text",
                "text": f"\n[보고서: {r['title']} / {r['date'].strftime('%m/%d') if r['date'] else ''}]",
            })
            for b64 in images_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
                })
            loaded += 1
        except Exception as e:
            print(f"    WARN: PDF 로드 실패 ({r['title'][:30]}): {e}")

    if loaded == 0:
        return {
            "overview": "보고서 본문을 불러올 수 없었습니다.",
            "points": [],
            "insight": "",
        }

    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=2500,
        messages=[
            {
                "role": "system",
                "content": (
                    "변액보험 상담사가 고객에게 설명할 수 있도록, 이번 주 시장 맥락에서 "
                    "이 테마가 왜 중요한지 분석하세요.\n"
                    "규칙:\n"
                    "- 보고서에 나온 구체적 수치·종목명·목표가를 반드시 인용\n"
                    "- 일반론('지속적 성장이 예상됨', '주목해야 할 시기') 절대 금지\n"
                    "- 이번 주 특유의 이벤트·실적·정책과 연결하여 서술\n"
                    "- 투자 권유 표현('매수하세요', '추천합니다') 금지, 팩트와 인과관계만\n\n"
                    "추가 — related_funds 선정:\n"
                    "아래 변액보험 펀드 목록에서 이 테마에 직접 영향받는 펀드를 1~8개 선정하세요.\n"
                    "선정 기준: 테마의 투자 대상(국가·섹터·자산군)과 펀드의 투자 대상이 일치.\n"
                    "간접적·광범위한 연결(예: '글로벌 성장이니까 모든 주식 펀드')은 포함 금지.\n\n"
                    f"[변액보험 펀드 목록]\n{FUND_CATALOG_TEXT}"
                ),
            },
            {"role": "user", "content": content},
        ],
        tools=[{"type": "function", "function": DETAIL_FUNCTION}],
        tool_choice={"type": "function", "function": {"name": "set_theme_detail"}},
    )
    _track_usage(resp)
    msg = resp.choices[0].message
    if msg.tool_calls:
        return json.loads(msg.tool_calls[0].function.arguments)
    return {"overview": "", "points": [], "insight": ""}


# ── HTML rendering ────────────────────────────────────────────────────────────


def _render_detail(detail: dict) -> str:
    """{ overview, points, insight, related_funds } → HTML 블록."""
    overview = detail.get("overview", "")
    points = detail.get("points", [])
    insight = detail.get("insight", "")
    related_funds = detail.get("related_funds", [])

    point_items = "".join(f"<li>{p}</li>" for p in points)
    point_block = f'<ul class="point-list">{point_items}</ul>' if point_items else ""

    points_html = (
        f'<div class="detail-section">'
        f'<div class="detail-label">핵심 포인트</div>{point_block}</div>'
        if point_block else ""
    )
    insight_html = (
        f'<div class="detail-section detail-insight">'
        f'<div class="detail-label">투자 시사점</div>'
        f'<p class="detail-text">{insight}</p></div>'
        if insight else ""
    )

    # 관련 펀드 매칭 — FUND_CATALOG에 없는 코드는 hallucination으로 간주하고 제거
    fund_lookup = {code: name for code, name, _ in FUND_CATALOG}
    valid_codes = set(fund_lookup)
    dropped = [f.get("code", "") for f in related_funds if f.get("code", "") not in valid_codes]
    if dropped:
        print(f"    WARN: 카탈로그에 없는 펀드 코드 제거: {dropped}")
    fund_chips = []
    for f in related_funds:
        code = f.get("code", "")
        name = fund_lookup.get(code, "")
        if not name:
            continue
        relevance = f.get("relevance", "")
        fund_chips.append(
            f'<span class="fund-chip" title="{relevance}">[{code}] {name}</span>'
        )
    fund_html = ""
    if fund_chips:
        fund_html = (
            f'<div class="detail-section detail-funds">'
            f'<div class="detail-label">관련 펀드</div>'
            f'<div class="fund-chips">{"".join(fund_chips)}</div></div>'
        )

    return f"""
    <div class="detail-section">
      <div class="detail-label">현황</div>
      <p class="detail-text">{overview}</p>
    </div>
    {points_html}
    {insight_html}
    {fund_html}
"""


def render_html(
    reports: list[dict],
    themes: list[dict],
    week_label: str,
    week_range: tuple[datetime, datetime],
) -> str:
    start, end = week_range
    generated = datetime.now()
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]

    theme_cards = []
    for i, theme in enumerate(themes):
        source_rows = []
        for idx in theme.get("report_indices", []):
            if 0 <= idx < len(reports):
                r = reports[idx]
                date_str = r["date"].strftime("%m/%d") if r["date"] else ""
                source_rows.append(f"""
          <li class="source-item">
            <a href="{r['view_url']}" target="_blank" rel="noopener" class="source-link">{r['title']}</a>
            <span class="source-date">{date_str}</span>
          </li>""")

        detail_html = _render_detail(theme.get("detail", {}))

        theme_cards.append(f"""
  <div class="theme-card">
    <div class="theme-header">
      <span class="theme-badge">Theme {i + 1}</span>
      <h2 class="theme-name">{theme['name']}</h2>
    </div>
    <div class="theme-body">
{detail_html}
    </div>
    <div class="source-section">
      <div class="source-label">출처 보고서</div>
      <ul class="source-list">{"".join(source_rows)}
      </ul>
    </div>
  </div>""")

    body = (
        "\n".join(theme_cards)
        if theme_cards
        else '<p style="text-align:center;color:var(--muted);padding:48px">분석 결과가 없습니다.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Research Digest · {week_label} · Anthillia</title>
<meta name="description" content="미래에셋증권 주간 리서치 다이제스트">
<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{
  --bg: #f0f2f7;
  --card: #ffffff;
  --border: #e2e6f0;
  --text: #2d3148;
  --muted: #7c8298;
  --primary: #F58220;
  --primary-light: #fff3e8;
  --navy: #043B72;
  --green: #1a9e6e;
  --green-light: #edfaf5;
  --section-bg: #f8f9fc;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Spoqa Han Sans Neo', -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.75;
  padding: 48px 24px;
  max-width: 900px;
  margin: 0 auto;
}}

/* nav */
.nav {{
  display: flex; gap: 8px; align-items: center;
  font-size: 13px; color: var(--muted); margin-bottom: 24px;
}}
.nav a {{ color: var(--muted); text-decoration: none; }}
.nav a:hover {{ color: var(--primary); }}
.nav .sep {{ color: var(--border); }}

/* header */
.header {{
  margin-bottom: 36px;
  padding-bottom: 28px;
  border-bottom: 2px solid var(--border);
}}
.header-badge {{
  display: inline-block;
  background: var(--primary); color: #fff;
  font-size: 10px; font-weight: 700;
  padding: 3px 10px; border-radius: 20px;
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 12px;
}}
.header h1 {{ font-size: 28px; font-weight: 800; color: #1a1d2e; margin-bottom: 8px; }}
.header .meta {{ font-size: 14px; color: var(--muted); }}

/* theme card */
.theme-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 20px;
  margin-bottom: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.05);
  overflow: hidden;
  transition: box-shadow 0.2s;
}}
.theme-card:hover {{ box-shadow: 0 6px 24px rgba(0,0,0,0.09); }}

.theme-header {{
  display: flex; align-items: center; gap: 14px;
  padding: 24px 28px 20px;
  border-bottom: 1px solid var(--border);
}}
.theme-badge {{
  flex-shrink: 0;
  font-size: 10px; font-weight: 800;
  color: var(--primary);
  background: var(--primary-light);
  padding: 4px 10px; border-radius: 20px;
  text-transform: uppercase; letter-spacing: 0.06em;
}}
.theme-name {{ font-size: 20px; font-weight: 700; color: #1a1d2e; }}

/* detail body */
.theme-body {{ padding: 0 28px; }}

.detail-section {{
  padding: 20px 0;
  border-bottom: 1px solid var(--border);
}}
.detail-section:last-child {{ border-bottom: none; }}

.detail-label {{
  display: inline-block;
  font-size: 11px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--navy);
  background: #eef1f8;
  padding: 3px 10px; border-radius: 20px;
  margin-bottom: 10px;
}}
.detail-insight .detail-label {{
  color: var(--green);
  background: var(--green-light);
}}
.detail-funds .detail-label {{
  color: #6b21a8;
  background: #f3e8ff;
}}
.fund-chips {{
  display: flex; flex-wrap: wrap; gap: 8px;
}}
.fund-chip {{
  display: inline-block;
  font-size: 12px; font-weight: 600;
  color: #6b21a8;
  background: #f8f0ff;
  border: 1px solid #e9d5ff;
  padding: 4px 12px; border-radius: 16px;
  cursor: default;
  transition: background 0.15s;
}}
.fund-chip:hover {{
  background: #ede2ff;
}}

.detail-text {{
  font-size: 15px;
  color: var(--text);
  line-height: 1.85;
}}

.point-list {{
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
}}
.point-list li {{
  font-size: 15px;
  color: var(--text);
  line-height: 1.75;
  padding-left: 20px;
  position: relative;
}}
.point-list li::before {{
  content: '';
  position: absolute;
  left: 0; top: 10px;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--primary);
}}

/* source */
.source-section {{
  padding: 18px 28px 22px;
  background: var(--section-bg);
  border-top: 1px solid var(--border);
}}
.source-label {{
  font-size: 11px; font-weight: 700;
  color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.07em;
  margin-bottom: 10px;
}}
.source-list {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
.source-item {{
  display: flex; align-items: center;
  justify-content: space-between; gap: 12px;
}}
.source-link {{
  font-size: 13px; color: var(--navy); text-decoration: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}}
.source-link:hover {{ color: var(--primary); text-decoration: underline; }}
.source-date {{
  flex-shrink: 0;
  font-size: 12px; color: var(--muted);
  background: #ebebf0; padding: 2px 8px; border-radius: 10px;
}}

/* disclaimer */
.ai-disclaimer {{
  background: #fff8f0; border: 1px solid #f0d9b5; border-radius: 10px;
  padding: 14px 20px; margin-top: 24px;
  font-size: 12px; color: #8b6914; line-height: 1.7;
}}

/* footer */
.footer {{
  text-align: center; font-size: 12px;
  color: var(--muted); padding-top: 28px; margin-top: 8px;
}}
.footer a {{ color: var(--primary); text-decoration: none; }}

@media (max-width: 720px) {{
  body {{ padding: 24px 12px; }}
  .theme-header {{ padding: 18px 20px 16px; }}
  .theme-name {{ font-size: 17px; }}
  .theme-body {{ padding: 0 20px; }}
  .source-section {{ padding: 16px 20px 20px; }}
  .detail-text, .point-list li {{ font-size: 14px; }}
}}
</style>
</head>
<body>

<div class="nav">
  <a href="../index.html">&larr; Anthillia</a>
  <span class="sep">/</span>
  <a href="index.html">Securities Research</a>
  <span class="sep">/</span>
  <span>Research Digest</span>
</div>

<div class="header">
  <div class="header-badge">Research Digest</div>
  <h1>{week_label}</h1>
  <p class="meta">
    미래에셋증권 상세분석 보고서 <strong>{len(reports)}건</strong> 기반 &middot;
    {start.strftime('%Y/%m/%d')}({weekdays[start.weekday()]})
    ~ {end.strftime('%m/%d')}({weekdays[end.weekday()]})
  </p>
</div>

{body}

<div class="ai-disclaimer">⚠️ 본 보고서는 AI가 자동 생성한 참고 자료이며, 투자 권유가 아닙니다. 수치·해석에 오류가 포함될 수 있으므로 투자 판단 시 반드시 원본 데이터를 확인하시기 바랍니다.</div>

<div class="footer">
  AI 분석: OpenAI {MODEL} &middot; 출처: 미래에셋증권 상세분석 &middot;
  생성: {generated.strftime('%Y-%m-%d %H:%M KST')}
  &middot; <a href="index.html">전체 보고서 목록</a>
</div>

</body>
</html>
"""


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="주간 증권 리서치 다이제스트 생성")
    parser.add_argument("--week-of", help="기준 주의 월요일 날짜 (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="GPT 호출 없이 HTML 골격만 생성")
    args = parser.parse_args()

    if args.week_of:
        ref = datetime.strptime(args.week_of, "%Y-%m-%d")
        start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        end = (ref + timedelta(days=4)).replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        start, end = get_week_range()

    year, week_num, _ = start.isocalendar()
    week_label = f"{year}년 {week_num}주차 ({start.strftime('%m/%d')}~{end.strftime('%m/%d')})"
    week_id = f"{year}-W{week_num:02d}"

    print("=== 주간 리서치 다이제스트 생성 ===")
    print(f"기간: {week_label}")

    print("\n[1/4] S3 스캔 중...")
    all_rows = scan_s3()
    reports = filter_week(all_rows, start, end)
    print(f"  → {len(reports)}건 (이번 주) / {len(all_rows)}건 (전체)")

    if not reports:
        print("이번 주 보고서 없음. 종료.")
        return

    if args.dry_run:
        themes = [{
            "name": "테스트 테마",
            "report_indices": list(range(min(2, len(reports)))),
            "detail": {
                "overview": "[DRY-RUN] 실제 실행 시 GPT-4o가 PDF 본문을 분석합니다.",
                "points": ["포인트 1", "포인트 2"],
                "insight": "투자 시사점이 여기에 표시됩니다.",
            },
        }]
        print("\n[DRY-RUN] GPT 호출 생략")
    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # 리전 엔드포인트 + virtual-hosted 필수 (글로벌 엔드포인트 사용 시 SignatureDoesNotMatch)
        s3_client = boto3.client(
            "s3",
            region_name=S3_REGION,
            endpoint_url=f"https://s3.{S3_REGION}.amazonaws.com",
            config=Config(s3={"addressing_style": "virtual"}),
        )

        print(f"\n[2/4] 테마 선정 중... ({len(reports)}건 제목 분석)")
        themes = select_themes(client, reports, week_label)
        print(f"  → {len(themes)}개 테마:")
        for t in themes:
            print(f"     • {t['name']} (관련 {len(t.get('report_indices', []))}건)")

        market_context = _load_week_market_context(end)
        if market_context:
            print(f"\n  시장 컨텍스트 로드 완료")
        else:
            print(f"\n  ⚠ 시장 컨텍스트 없음 (data.json 미발견)")

        print(f"\n[3/4] PDF Vision 분석 중... (테마당 최대 {MAX_PDFS_PER_THEME}건)")
        for i, theme in enumerate(themes):
            print(f"  [{i+1}/{len(themes)}] {theme['name']}")
            indices = theme.get("report_indices", [])
            subset = [reports[idx] for idx in indices if 0 <= idx < len(reports)]
            theme["detail"] = analyze_theme_detail(
                client, theme["name"], subset, s3_client, market_context
            )
            pts = len(theme["detail"].get("points", []))
            print(f"    → 완료 (포인트 {pts}개)")

        t = _token_totals
        total = t["prompt"] + t["completion"]
        print(
            f"\n  [토큰] prompt={t['prompt']:,}  completion={t['completion']:,}  "
            f"total={total:,}  (gpt-4o 기준 ~${t['prompt']/1e6*2.5 + t['completion']/1e6*10:.4f})"
        )
        sys.path.insert(0, str(ROOT))
        import notify_telegram as _nt
        _nt.send(_nt.build_gpt_usage_message(
            "generate_securities_digest", week_label, t["prompt"], t["completion"]
        ))

    print("\n[4/4] HTML 생성 중...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    html = render_html(reports, themes, week_label, (start, end))
    digest_path = OUTPUT_DIR / f"digest_{week_id}.html"
    latest_path = OUTPUT_DIR / "digest_latest.html"

    digest_path.write_text(html, encoding="utf-8")
    shutil.copy2(digest_path, latest_path)

    print(f"  → {digest_path}")
    print(f"  → {latest_path} (최신본)")


if __name__ == "__main__":
    main()
