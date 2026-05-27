"""주간 테마 리서치 생성기.

Naver 테마 지속성 × 미래에셋증권 증권 다이제스트 × Tavily 글로벌 트리거
3개 신호를 교차해 핵심 테마 1~2개를 선정하고 심층 리서치 보고서를 생성.

흐름:
  1. Naver theme_history.json → 7거래일 지속성 상위 15개
  2. digest_latest.html → 증권 애널리스트 테마
  3. Tavily REST API → 글로벌 트리거 (상위 7개 Naver 테마)
  4. Claude Bedrock: 3-신호 교차 → 테마 1~2개 선정
  5. Claude Bedrock: 보고서 본문 작성 (펀드 매칭 포함)
  6. HTML 렌더링 → output/research/daily/YYYY-MM/

Output:
    output/research/daily/YYYY-MM/YYYY-MM-DD.html
    output/research/daily/YYYY-MM/YYYY-MM-DD_story.html
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

from generate_securities_digest import FUND_CATALOG, FUND_CATALOG_TEXT  # noqa: E402

# generate_securities_digest 모듈 임포트 시 AWS_BEARER_TOKEN_BEDROCK="" 이 주입됨
# (BEDROCK_API_KEY 미설정 시) → AnthropicBedrock SigV4 인증 헤더 오류 방지
if not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

OUTPUT_BASE = ROOT / "output" / "research" / "daily"

THEME_HISTORY_PATH = Path(
    r"C:\Users\user\Desktop\kosmos\crescent\screener\data\v2\theme_history.json"
)

BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "jp.anthropic.claude-sonnet-4-5-20250929-v1:0")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_ENDPOINT = "https://api.tavily.com/search"

# ── Bedrock / token tracking ───────────────────────────────────────────────────

_token_totals: dict[str, int] = {"prompt": 0, "completion": 0}


def _get_bedrock_client():
    from anthropic import AnthropicBedrock
    return AnthropicBedrock(aws_region=BEDROCK_REGION)


def _track_usage(resp) -> None:
    usage = getattr(resp, "usage", None)
    if usage:
        _token_totals["prompt"] += getattr(usage, "input_tokens", 0)
        _token_totals["completion"] += getattr(usage, "output_tokens", 0)


# ── tool schemas ───────────────────────────────────────────────────────────────

THEME_SELECT_TOOL = {
    "name": "select_research_themes",
    "description": "3개 신호(Naver 지속성·증권 다이제스트·Tavily 글로벌 트리거)를 교차해 핵심 테마 선정",
    "input_schema": {
        "type": "object",
        "properties": {
            "themes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "테마명 (20자 이내)"},
                        "naver_theme": {"type": "string", "description": "매핑된 Naver 테마명 (정확히 일치)"},
                        "naver_persistence": {"type": "integer", "description": "Naver 지속성 (%)"},
                        "naver_avg_return": {"type": "number", "description": "Naver 평균 수익률 (%)"},
                        "in_digest": {"type": "boolean", "description": "증권 다이제스트 포함 여부"},
                        "digest_theme": {
                            "type": "string",
                            "description": "다이제스트 내 관련 테마명 (없으면 빈 문자열)",
                        },
                        "global_trigger": {
                            "type": "string",
                            "description": "Tavily에서 확인된 글로벌 트리거 (1~2문장, 없으면 빈 문자열)",
                        },
                        "selection_reason": {
                            "type": "string",
                            "description": "선정 근거 — Naver·다이제스트·Tavily 교차 설명 (2~3문장)",
                        },
                    },
                    "required": [
                        "name", "naver_theme", "naver_persistence", "naver_avg_return",
                        "in_digest", "digest_theme", "global_trigger", "selection_reason",
                    ],
                },
            }
        },
        "required": ["themes"],
    },
}

RESEARCH_REPORT_TOOL = {
    "name": "write_research_report",
    "description": "심층 리서치 보고서 본문 및 핵심 포인트 작성",
    "input_schema": {
        "type": "object",
        "properties": {
            "themes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "background": {
                            "type": "string",
                            "description": "배경 — 왜 지금 이 테마인가 (2~3문단, 구체적 수치·이벤트 포함)",
                        },
                        "key_drivers": {
                            "type": "string",
                            "description": "핵심 드라이버 (정책·수요·기술 변화, 2~3문단)",
                        },
                        "kr_stocks": {
                            "type": "string",
                            "description": "한국 관련 종목·섹터 동향 (1~2문단, 종목명 포함)",
                        },
                        "global_market": {
                            "type": "string",
                            "description": "글로벌 시장 파급 (ETF·지수, 1~2문단)",
                        },
                        "advisor_line": {
                            "type": "string",
                            "description": "상담사 한 줄 설명 — 고객에게 바로 쓸 수 있는 쉬운 문장 (글로벌 트리거 → 한국 섹터 연결)",
                        },
                        "risk": {
                            "type": "string",
                            "description": "리스크 — 반전 시나리오 (1~2문장)",
                        },
                        "related_funds": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "code": {"type": "string", "description": "펀드 코드 (예: N150)"},
                                    "relevance": {"type": "string", "description": "관련 이유 (15자 이내)"},
                                },
                                "required": ["code", "relevance"],
                            },
                            "minItems": 1,
                            "maxItems": 6,
                            "description": "이 테마와 직접 관련된 변액보험 펀드 (카탈로그에서만 선택)",
                        },
                    },
                    "required": [
                        "name", "background", "key_drivers", "kr_stocks",
                        "global_market", "advisor_line", "risk", "related_funds",
                    ],
                },
            },
            "weekly_summary": {
                "type": "object",
                "properties": {
                    "point1": {"type": "string", "description": "테마1 한 줄 요약 + 초보자도 이해할 수 있는 설명"},
                    "point2": {"type": "string", "description": "테마2 한 줄 요약 + 설명 (없으면 빈 문자열)"},
                    "next_week": {
                        "type": "string",
                        "description": "다음 주 주목 변수 (캘린더 이벤트·지표 1~2개)",
                    },
                    "naver_watch": {
                        "type": "string",
                        "description": "이번 주 Naver 지속성 상위 중 선정되지 않은 주목 테마 1개 + 이유",
                    },
                },
                "required": ["point1", "point2", "next_week", "naver_watch"],
            },
        },
        "required": ["themes", "weekly_summary"],
    },
}


# ── Step 1: Naver theme persistence ───────────────────────────────────────────


def load_naver_persistence(ref_date_str: str, n_days: int = 7) -> list[dict]:
    if not THEME_HISTORY_PATH.exists():
        print(f"  WARN: theme_history.json 없음: {THEME_HISTORY_PATH}")
        return []

    with open(THEME_HISTORY_PATH, encoding="utf-8") as f:
        history = json.load(f)

    all_dates = sorted(d for d in history if d <= ref_date_str)
    dates = all_dates[-n_days:]

    if not dates:
        print("  WARN: theme_history.json에 해당 날짜 데이터 없음")
        return []

    print(f"  → {len(dates)}거래일 사용: {dates[0]} ~ {dates[-1]}")

    scores: dict[str, dict] = defaultdict(
        lambda: {"positive_days": 0, "total_days": 0, "returns": []}
    )
    for d in dates:
        for theme, v in history[d].items():
            scores[theme]["total_days"] += 1
            scores[theme]["returns"].append(v.get("today", 0))
            if v.get("today", 0) > 0:
                scores[theme]["positive_days"] += 1

    results = []
    for theme, s in scores.items():
        if s["total_days"] >= 4:
            persistence = s["positive_days"] / s["total_days"] * 100
            avg = sum(s["returns"]) / len(s["returns"]) if s["returns"] else 0
            results.append(
                {
                    "theme": theme,
                    "persistence": round(persistence),
                    "avg_return": round(avg, 2),
                    "total_days": s["total_days"],
                    "positive_days": s["positive_days"],
                }
            )

    return sorted(results, key=lambda x: (x["persistence"], x["avg_return"]), reverse=True)


# ── Step 2: Securities digest ──────────────────────────────────────────────────


def load_securities_digest() -> list[dict]:
    digest_path = ROOT / "output" / "research" / "securities" / "digest_latest.html"
    if not digest_path.exists():
        print("  WARN: digest_latest.html 없음")
        return []

    soup = BeautifulSoup(digest_path.read_text(encoding="utf-8"), "html.parser")
    themes = []
    for card in soup.select(".theme-card"):
        name_el = card.select_one(".theme-name")
        overview_el = card.select_one(".detail-section .detail-text")
        insight_el = card.select_one(".detail-insight .detail-text")
        if name_el:
            themes.append(
                {
                    "name": name_el.get_text(strip=True),
                    "overview": overview_el.get_text(strip=True) if overview_el else "",
                    "insight": insight_el.get_text(strip=True) if insight_el else "",
                }
            )
    print(f"  → 증권 다이제스트 테마 {len(themes)}개 로드")
    return themes


# ── Step 3: Tavily search ──────────────────────────────────────────────────────


def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    if not TAVILY_API_KEY:
        return []
    try:
        resp = requests.post(
            TAVILY_ENDPOINT,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": True,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("answer", "")
        return [
            {
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", ""),
                "answer": answer,
            }
            for r in data.get("results", [])
        ]
    except Exception as e:
        print(f"  WARN: Tavily 검색 실패 ({query[:40]}): {e}")
        return []


def search_global_triggers(naver_top: list[dict]) -> dict[str, list[dict]]:
    """상위 Naver 테마별 글로벌 트리거 검색 (최대 7개)."""
    results = {}
    for t in naver_top[:7]:
        name = t["theme"]
        print(f"    검색: {name}")
        hits = _tavily_search(f"Korea stock {name} sector recent news catalyst", max_results=4)
        results[name] = hits
    return results


# ── Claude calls ───────────────────────────────────────────────────────────────


def select_themes(
    client,
    naver_top: list[dict],
    digest_themes: list[dict],
    tavily_results: dict[str, list[dict]],
    week_label: str,
) -> list[dict]:
    naver_text = "\n".join(
        f"- {t['theme']}: 지속성 {t['persistence']}%, 평균수익률 {t['avg_return']:+.2f}%"
        f" ({t['total_days']}거래일 중 {t['positive_days']}일 양봉)"
        for t in naver_top[:15]
    )

    digest_text = (
        "\n".join(f"- {t['name']}: {t['overview'][:100]}" for t in digest_themes)
        if digest_themes
        else "없음"
    )

    tavily_lines = []
    for theme_name, hits in tavily_results.items():
        if hits:
            answer = hits[0].get("answer", "")
            summary = answer[:120] if answer else ", ".join(h.get("title", "") for h in hits[:2])
            tavily_lines.append(f"- {theme_name}: {summary}")
    tavily_text = "\n".join(tavily_lines) if tavily_lines else "없음"

    resp = client.messages.create(
        model=BEDROCK_MODEL,
        max_tokens=1500,
        system=(
            "변액보험 상담사를 위한 주간 테마 리서치 편집장입니다.\n"
            "수급(Naver 지속성) + 증권 분석(다이제스트) + 뉴스(Tavily)를 교차해\n"
            "가장 설명력 있는 테마 1~2개를 선정하세요.\n\n"
            "선정 기준:\n"
            "- Naver 지속성 ≥ 60% + 다이제스트 언급 → 1순위\n"
            "- Naver 지속성 ≥ 70% (다이제스트 미언급) → 2순위 ('시장이 먼저 움직인 테마')\n"
            "- 다이제스트만 있고 Naver 낮음 → 참고만\n\n"
            "상담사가 고객에게 쉽게 설명할 수 있는 현실적 테마를 선정하세요."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"이번 주({week_label}) 한국 주식시장 핵심 테마를 선정해주세요.\n\n"
                    f"[Naver 테마 지속성 상위 15개]\n{naver_text}\n\n"
                    f"[미래에셋증권 증권 다이제스트 테마]\n{digest_text}\n\n"
                    f"[Tavily 글로벌 트리거]\n{tavily_text}"
                ),
            }
        ],
        tools=[THEME_SELECT_TOOL],
        tool_choice={"type": "tool", "name": "select_research_themes"},
    )
    _track_usage(resp)

    for block in resp.content:
        if getattr(block, "type", "") == "tool_use" and block.name == "select_research_themes":
            return block.input.get("themes", [])
    return []


def write_report(
    client,
    selected: list[dict],
    naver_top: list[dict],
    digest_themes: list[dict],
    tavily_results: dict[str, list[dict]],
    week_label: str,
) -> dict:
    theme_ctx_parts = []
    for t in selected:
        naver_name = t.get("naver_theme", t["name"])
        hits = tavily_results.get(naver_name, [])
        naver_data = next((n for n in naver_top if n["theme"] == naver_name), {})
        digest_match = next(
            (d for d in digest_themes if t.get("digest_theme", "") and t["digest_theme"] in d["name"]),
            {},
        )
        news_lines = "\n".join(
            f"  [{i+1}] {h.get('title', '')}: {h.get('content', '')[:200]}"
            for i, h in enumerate(hits[:4])
        )
        theme_ctx_parts.append(
            f"[테마: {t['name']}]\n"
            f"선정 근거: {t.get('selection_reason', '')}\n"
            f"글로벌 트리거: {t.get('global_trigger', '')}\n"
            f"Naver 지속성: {t.get('naver_persistence')}%, 평균 {t.get('naver_avg_return')}%\n\n"
            f"최근 뉴스:\n{news_lines or '없음'}\n\n"
            f"증권 다이제스트:\n{digest_match.get('overview', '없음')[:300]}"
        )

    resp = client.messages.create(
        model=BEDROCK_MODEL,
        max_tokens=5000,
        system=(
            "변액보험 상담사를 위한 주간 테마 리서치 작성자입니다.\n"
            "규칙:\n"
            "- 구체적 종목명·수치 반드시 포함\n"
            "- '지속적 성장이 예상됨' 같은 일반론 금지\n"
            "- 상담사가 고객에게 바로 설명할 수 있는 언어\n"
            "- 투자 권유 표현('매수하세요') 금지, 팩트와 인과관계만\n\n"
            "related_funds: 아래 카탈로그에서 테마에 직접 해당하는 펀드만 선정. "
            "광범위한 연결(예: 글로벌 성장이니 모든 주식 펀드)은 제외.\n\n"
            f"[변액보험 펀드 카탈로그]\n{FUND_CATALOG_TEXT}"
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"이번 주({week_label}) 선정된 테마 보고서를 작성해주세요.\n\n"
                    + "\n\n---\n\n".join(theme_ctx_parts)
                ),
            }
        ],
        tools=[RESEARCH_REPORT_TOOL],
        tool_choice={"type": "tool", "name": "write_research_report"},
    )
    _track_usage(resp)

    for block in resp.content:
        if getattr(block, "type", "") == "tool_use" and block.name == "write_research_report":
            return block.input
    return {"themes": [], "weekly_summary": {}}


# ── HTML rendering ─────────────────────────────────────────────────────────────


def _theme_card_html(theme_body: dict, meta: dict) -> str:
    name = theme_body.get("name", "")
    background = theme_body.get("background", "")
    key_drivers = theme_body.get("key_drivers", "")
    kr_stocks = theme_body.get("kr_stocks", "")
    global_market = theme_body.get("global_market", "")
    advisor_line = theme_body.get("advisor_line", "")
    risk = theme_body.get("risk", "")
    related_funds = theme_body.get("related_funds", [])

    naver_persistence = meta.get("naver_persistence", 0)
    in_digest = meta.get("in_digest", False)
    global_trigger = meta.get("global_trigger", "")
    selection_reason = meta.get("selection_reason", "")

    # signal chips
    naver_chip = f'<span class="chip chip-naver">Naver {naver_persistence}%</span>'
    digest_chip = '<span class="chip chip-report">증권보고서</span>' if in_digest else ""
    tavily_chip = '<span class="chip chip-tavily">글로벌뉴스</span>' if global_trigger else ""

    # fund chips — only codes that exist in FUND_CATALOG
    valid_funds = {code: nm for code, nm, _ in FUND_CATALOG}
    fund_html = ""
    valid = [f for f in related_funds if f.get("code", "") in valid_funds]
    if valid:
        chips = "".join(
            f'<span class="fund-chip" title="{f.get("relevance","")}">[{f["code"]}] {valid_funds[f["code"]]}</span>'
            for f in valid
        )
        fund_html = (
            f'<div class="fund-section">'
            f'<div class="section-label">관련 펀드</div>'
            f'<div class="fund-chips">{chips}</div></div>'
        )

    return f"""
<div class="theme-card">
  <div class="theme-header">
    <h2 class="theme-name">{name}</h2>
    <div class="signal-bar">{naver_chip}{digest_chip}{tavily_chip}</div>
  </div>
  <div class="theme-body">
    <div class="selection-reason"><strong>선정 근거</strong>: {selection_reason}</div>

    <div class="section">
      <div class="section-label">배경 — 왜 지금 이 테마인가</div>
      <div class="section-text">{background}</div>
    </div>
    <div class="section">
      <div class="section-label">핵심 드라이버</div>
      <div class="section-text">{key_drivers}</div>
    </div>
    <div class="section">
      <div class="section-label">한국 관련 종목·섹터</div>
      <div class="section-text">{kr_stocks}</div>
    </div>
    <div class="section">
      <div class="section-label">글로벌 시장 파급</div>
      <div class="section-text">{global_market}</div>
    </div>

    <div class="advisor-box">
      <strong>상담사 한 줄 설명</strong>: {advisor_line}
    </div>
    <div class="risk-box">
      <strong>리스크</strong>: {risk}
    </div>
    {fund_html}
  </div>
</div>"""


def render_html(
    selected: list[dict],
    report_data: dict,
    naver_top: list[dict],
    date_str: str,
    week_label: str,
) -> str:
    generated = datetime.now()
    fund_lookup = {code: nm for code, nm, _ in FUND_CATALOG}

    report_themes = report_data.get("themes", [])
    cards_html = "\n".join(
        _theme_card_html(report_themes[i], selected[i])
        for i in range(min(len(selected), len(report_themes)))
    ) or "<p>테마 분석 결과 없음</p>"

    summary = report_data.get("weekly_summary", {})
    pt1 = summary.get("point1", "")
    pt2 = summary.get("point2", "")
    next_week = summary.get("next_week", "")
    naver_watch = summary.get("naver_watch", "")
    pt2_html = f"<p>② {pt2}</p>" if pt2 else ""

    naver_rows = "".join(
        f"<tr><td>{t['theme']}</td>"
        f"<td>{t['persistence']}%</td>"
        f"<td class='{'pos' if t['avg_return'] >= 0 else 'neg'}'>{t['avg_return']:+.2f}%</td>"
        f"<td>{t['total_days']}일</td></tr>"
        for t in naver_top[:10]
    )

    theme_names = " · ".join(t.get("name", "") for t in selected)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Weekly Theme Research · {date_str} · Anthillia</title>
<link rel="icon" href="../../assets/favicon.svg" type="image/svg+xml">
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{
  --bg:#f0f2f7; --card:#fff; --border:#e2e6f0;
  --text:#2d3148; --muted:#7c8298;
  --primary:#F58220; --primary-light:#fff3e8;
  --navy:#043B72; --green:#1a9e6e; --green-light:#edfaf5;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Spoqa Han Sans Neo',-apple-system,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.75;
  padding:48px 24px;max-width:900px;margin:0 auto;
}}
.nav{{display:flex;gap:8px;align-items:center;font-size:13px;color:var(--muted);margin-bottom:24px}}
.nav a{{color:var(--muted);text-decoration:none}}.nav a:hover{{color:var(--primary)}}
.nav .sep{{color:var(--border)}}
.header{{margin-bottom:36px;padding-bottom:28px;border-bottom:2px solid var(--border)}}
.header-badge{{
  display:inline-block;background:var(--primary);color:#fff;
  font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px;
  text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px;
}}
.header h1{{font-size:28px;font-weight:800;color:#1a1d2e;margin-bottom:8px}}
.header .meta{{font-size:14px;color:var(--muted)}}
.theme-card{{
  background:var(--card);border:1px solid var(--border);border-radius:20px;
  margin-bottom:24px;box-shadow:0 2px 12px rgba(0,0,0,.05);overflow:hidden;
}}
.theme-header{{padding:24px 28px 20px;border-bottom:1px solid var(--border)}}
.theme-name{{font-size:22px;font-weight:800;color:#1a1d2e;margin-bottom:12px}}
.signal-bar{{display:flex;flex-wrap:wrap;gap:8px}}
.chip{{font-size:11px;font-weight:700;padding:3px 12px;border-radius:20px}}
.chip-naver{{color:#047857;background:#d1fae5;border:1px solid #6ee7b7}}
.chip-report{{color:var(--navy);background:#dbeafe;border:1px solid #93c5fd}}
.chip-tavily{{color:#6b21a8;background:#f3e8ff;border:1px solid #d8b4fe}}
.theme-body{{padding:0 28px 28px}}
.selection-reason{{
  margin:20px 0;padding:14px 18px;
  background:#f8f9fc;border-radius:10px;border-left:3px solid var(--primary);
  font-size:13px;color:var(--muted);
}}
.section{{padding:18px 0;border-bottom:1px solid var(--border)}}
.section:last-of-type{{border-bottom:none}}
.section-label{{
  display:inline-block;font-size:11px;font-weight:800;
  text-transform:uppercase;letter-spacing:.08em;
  color:var(--navy);background:#eef1f8;padding:3px 10px;border-radius:20px;margin-bottom:10px;
}}
.section-text{{font-size:15px;line-height:1.85;white-space:pre-wrap}}
.advisor-box{{
  margin:18px 0 12px;padding:14px 18px;
  background:#f0f7ff;border:1px solid #bfdbfe;border-radius:10px;font-size:14px;
}}
.risk-box{{
  margin:12px 0;padding:14px 18px;
  background:#fff5f5;border:1px solid #fecaca;border-radius:10px;font-size:14px;
}}
.fund-section{{margin-top:18px}}
.fund-chips{{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}}
.fund-chip{{
  font-size:12px;font-weight:600;color:#6b21a8;background:#f8f0ff;
  border:1px solid #e9d5ff;padding:4px 12px;border-radius:16px;cursor:default;
}}
.fund-chip:hover{{background:#ede2ff}}
.summary-card{{
  background:var(--card);border:1px solid var(--border);border-radius:20px;
  padding:28px;box-shadow:0 2px 12px rgba(0,0,0,.05);margin-bottom:24px;
}}
.summary-card h2{{
  font-size:18px;font-weight:700;color:var(--navy);
  margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border);
}}
.summary-card p{{font-size:14px;margin-bottom:10px;line-height:1.85}}
.naver-table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:20px}}
.naver-table th{{
  background:#f8f9fc;color:var(--muted);font-weight:600;
  padding:8px 12px;text-align:left;border-bottom:2px solid var(--border);
}}
.naver-table td{{padding:8px 12px;border-bottom:1px solid var(--border)}}
.naver-table tr:last-child td{{border-bottom:none}}
.naver-table .pos{{color:#047857;font-weight:600}}
.naver-table .neg{{color:#dc2626;font-weight:600}}
.ai-disclaimer{{
  background:#fff8f0;border:1px solid #f0d9b5;border-radius:10px;
  padding:14px 20px;margin-top:24px;font-size:12px;color:#8b6914;line-height:1.7;
}}
.footer{{text-align:center;font-size:12px;color:var(--muted);padding-top:28px;margin-top:8px}}
.footer a{{color:var(--primary);text-decoration:none}}
@media(max-width:720px){{
  body{{padding:24px 12px}}
  .theme-header,.theme-body{{padding-left:20px;padding-right:20px}}
  .theme-name{{font-size:18px}}
}}
</style>
</head>
<body>

<div class="nav">
  <a href="../../../index.html">&larr; Anthillia</a>
  <span class="sep">/</span>
  <a href="../../index.html">Research</a>
  <span class="sep">/</span>
  <span>Weekly Theme Research</span>
</div>

<div class="header">
  <div class="header-badge">Weekly Theme Research</div>
  <h1>{week_label}</h1>
  <p class="meta">
    Naver 테마 지속성 × 미래에셋증권 다이제스트 × Tavily 글로벌 트리거 &middot;
    테마: <strong>{theme_names}</strong>
  </p>
</div>

{cards_html}

<div class="summary-card">
  <h2>이번 주 핵심 포인트</h2>
  <p>① {pt1}</p>
  {pt2_html}
  <p>③ <strong>다음 주 주목 변수</strong> — {next_week}</p>
  <p>④ <strong>Naver 지속성 신호</strong> — {naver_watch}</p>

  <table class="naver-table">
    <thead>
      <tr><th>Naver 테마</th><th>지속성</th><th>평균수익률</th><th>데이터</th></tr>
    </thead>
    <tbody>{naver_rows}</tbody>
  </table>
</div>

<div class="ai-disclaimer">
  ⚠️ 본 보고서는 AI가 자동 생성한 참고 자료이며, 투자 권유가 아닙니다.
  Naver 테마 데이터·증권 분석·글로벌 뉴스를 교차 분석했으나 수치·해석에 오류가 포함될 수 있으므로
  투자 판단 시 반드시 원본 데이터를 확인하시기 바랍니다.
</div>

<div class="footer">
  AI 분석: Bedrock Claude &middot; Naver 테마 지속성 &middot; 미래에셋증권 다이제스트 &middot; Tavily 뉴스 &middot;
  생성: {generated.strftime('%Y-%m-%d %H:%M KST')}
  &middot; <a href="../index.html">보고서 목록</a>
</div>

</body>
</html>
"""


# ── main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    # Windows 콘솔 UTF-8 출력
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="주간 테마 리서치 생성")
    parser.add_argument("--date", help="기준 날짜 (YYYY-MM-DD, 기본: 오늘)")
    parser.add_argument("--dry-run", action="store_true", help="Claude 호출 없이 구조 확인")
    args = parser.parse_args()

    ref_date = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    ref_date_str = ref_date.strftime("%Y-%m-%d")

    if ref_date.date() > datetime.now().date():
        print(f"오류: 미래 날짜 ({ref_date_str}) — 실행 불가")
        sys.exit(1)

    year, week_num, _ = ref_date.isocalendar()
    week_label = f"{year}년 W{week_num:02d} 테마 리서치"

    print("=== 주간 테마 리서치 생성 ===")
    print(f"기준 날짜: {ref_date_str}  |  {week_label}")

    month_dir = OUTPUT_BASE / ref_date.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    output_path = month_dir / f"{ref_date_str}.html"
    story_path = month_dir / f"{ref_date_str}_story.html"

    # ── 1. Naver 지속성 ────────────────────────────────────────────────────────
    print("\n[1/5] Naver 테마 지속성 계산...")
    naver_top = load_naver_persistence(ref_date_str, n_days=7)
    if not naver_top:
        print("  WARN: Naver 데이터 없음 — Tavily + 다이제스트만으로 진행")
    else:
        print(f"  상위 5개:")
        for t in naver_top[:5]:
            print(f"    {t['theme']}: 지속성 {t['persistence']}%, 평균 {t['avg_return']:+.2f}%")

    # ── 2. 증권 다이제스트 ────────────────────────────────────────────────────
    print("\n[2/5] 증권 다이제스트 로드...")
    digest_themes = load_securities_digest()

    # ── 3. Tavily 검색 ────────────────────────────────────────────────────────
    print("\n[3/5] Tavily 글로벌 트리거 검색...")
    if args.dry_run or not TAVILY_API_KEY:
        tavily_results: dict[str, list[dict]] = {t["theme"]: [] for t in naver_top[:7]}
        if args.dry_run:
            print("  [DRY-RUN] 검색 스킵")
        else:
            print("  [SKIP] TAVILY_API_KEY 없음")
    else:
        tavily_results = search_global_triggers(naver_top)

    if args.dry_run:
        print("\n[DRY-RUN] Claude 호출 스킵 - 더미 출력 생성")
        selected = [
            {
                "name": f"[DRY-RUN] {naver_top[0]['theme']}" if naver_top else "DRY-RUN 테마",
                "naver_theme": naver_top[0]["theme"] if naver_top else "",
                "naver_persistence": 70,
                "naver_avg_return": 2.0,
                "in_digest": False,
                "digest_theme": "",
                "global_trigger": "테스트 트리거",
                "selection_reason": "DRY-RUN 확인용",
            }
        ]
        report_data = {
            "themes": [
                {
                    "name": selected[0]["name"],
                    "background": "DRY-RUN: 실제 실행 시 배경 서술이 여기에 생성됩니다.",
                    "key_drivers": "DRY-RUN: 핵심 드라이버가 여기에 표시됩니다.",
                    "kr_stocks": "DRY-RUN: 한국 종목 동향이 여기에 표시됩니다.",
                    "global_market": "DRY-RUN: 글로벌 파급 내용이 여기에 표시됩니다.",
                    "advisor_line": "DRY-RUN: 상담사 설명이 여기에 표시됩니다.",
                    "risk": "DRY-RUN: 리스크 내용이 여기에 표시됩니다.",
                    "related_funds": [{"code": "N150", "relevance": "AI 국내주식"}],
                }
            ],
            "weekly_summary": {
                "point1": "DRY-RUN 포인트 1",
                "point2": "",
                "next_week": "미국 CPI, FOMC",
                "naver_watch": "DRY-RUN 주목 테마",
            },
        }
    else:
        client = _get_bedrock_client()

        # ── 4-A: 테마 선정 ────────────────────────────────────────────────────
        print("\n[4/5] Claude 테마 선정...")
        selected = select_themes(client, naver_top, digest_themes, tavily_results, week_label)
        if not selected:
            print("  오류: 테마 선정 실패 — 종료")
            sys.exit(1)
        print(f"  → {len(selected)}개 선정:")
        for t in selected:
            print(
                f"    • {t['name']}  (Naver {t.get('naver_persistence')}%,"
                f" 다이제스트={'O' if t.get('in_digest') else 'X'})"
            )

        # ── 4-B: 보고서 본문 ─────────────────────────────────────────────────
        print("\n[4-B] Claude 보고서 작성...")
        report_data = write_report(
            client, selected, naver_top, digest_themes, tavily_results, week_label
        )

        t = _token_totals
        cost = t["prompt"] / 1e6 * 3.0 + t["completion"] / 1e6 * 15.0
        print(
            f"\n  [토큰] input={t['prompt']:,}  output={t['completion']:,}"
            f"  total={t['prompt']+t['completion']:,}  (Sonnet 기준 ~${cost:.4f})"
        )
        sys.path.insert(0, str(ROOT))
        try:
            import notify_telegram as _nt
            _nt.send(
                _nt.build_gpt_usage_message(
                    "generate_research", week_label, t["prompt"], t["completion"]
                )
            )
        except Exception:
            pass

    # ── 5. HTML 저장 ──────────────────────────────────────────────────────────
    print("\n[5/5] HTML 저장...")
    html = render_html(selected, report_data, naver_top, ref_date_str, week_label)
    output_path.write_text(html, encoding="utf-8")
    shutil.copy2(output_path, story_path)
    print(f"  → {output_path}")
    print(f"  → {story_path}")

    theme_names = " · ".join(t.get("name", "") for t in selected)
    print(f"\n완료. 테마: {theme_names}")


if __name__ == "__main__":
    main()
