"""일간 테마 리서치 생성기.

오늘의 Naver 테마 수익률 × 7일 지속성 × Tavily 글로벌 트리거
3개 신호로 핵심 테마 1~2개를 선정하고 일간 심층 리서치 보고서 생성.

흐름:
  1. Naver theme_history.json  → 오늘 수익률 + 7일 지속성
  2. _data.json                → KOSPI 등락·주요 종목 (배경 맥락)
  3. Tavily REST API           → 글로벌 트리거 (상위 테마 대상)
  4. Claude Bedrock            → 테마 1~2개 선정
  5. Claude Bedrock            → 보고서 본문 작성 (토킹포인트·Q&A 포함)
  6. HTML 렌더링               → output/research/daily/YYYY-MM/YYYY-MM-DD.html

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
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# FUND_CATALOG — 변액보험 펀드 목록 (generate_securities_digest 경유)
try:
    from generate_securities_digest import FUND_CATALOG, FUND_CATALOG_TEXT  # noqa: E402
    if not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
except Exception:
    FUND_CATALOG = []
    FUND_CATALOG_TEXT = "(펀드 카탈로그 로드 실패)"

OUTPUT_BASE = ROOT / "output" / "research" / "daily"

THEME_HISTORY_PATH = Path(
    r"C:\Users\user\Desktop\kosmos\crescent\screener\data\v2\theme_history.json"
)

BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL", "jp.anthropic.claude-sonnet-4-5-20250929-v1:0")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_ENDPOINT = "https://api.tavily.com/search"

_token_totals: dict[str, int] = {"prompt": 0, "completion": 0}


def _get_bedrock_client():
    from anthropic import AnthropicBedrock
    return AnthropicBedrock(aws_region=BEDROCK_REGION)


def _track_usage(resp) -> None:
    usage = getattr(resp, "usage", None)
    if usage:
        _token_totals["prompt"] += getattr(usage, "input_tokens", 0)
        _token_totals["completion"] += getattr(usage, "output_tokens", 0)


# ── Tool schemas ───────────────────────────────────────────────────────────────

THEME_SELECT_TOOL = {
    "name": "select_research_themes",
    "description": "오늘 수익률·7일 지속성·Tavily 글로벌 트리거를 교차해 핵심 테마 선정",
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
                        "name": {
                            "type": "string",
                            "description": "테마명 (20자 이내, 상담사가 고객에게 설명할 수 있는 명칭)",
                        },
                        "naver_theme": {
                            "type": "string",
                            "description": "매핑된 Naver 테마명 (정확히 일치)",
                        },
                        "naver_today_return": {
                            "type": "number",
                            "description": "오늘 Naver 테마 수익률 (%)",
                        },
                        "naver_persistence_7d": {
                            "type": "integer",
                            "description": "최근 7거래일 지속성 (%)",
                        },
                        "global_trigger": {
                            "type": "string",
                            "description": "Tavily에서 확인된 글로벌 트리거 (1~2문장, 없으면 빈 문자열)",
                        },
                        "selection_reason": {
                            "type": "string",
                            "description": "선정 근거 — 오늘 수익률·지속성·글로벌 트리거 교차 설명 (2~3문장)",
                        },
                    },
                    "required": [
                        "name", "naver_theme", "naver_today_return",
                        "naver_persistence_7d", "global_trigger", "selection_reason",
                    ],
                },
            }
        },
        "required": ["themes"],
    },
}

RESEARCH_REPORT_TOOL = {
    "name": "write_research_report",
    "description": "일간 테마 리서치 보고서 본문 작성 (상담사 실무 특화)",
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
                        "today_move": {
                            "type": "string",
                            "description": (
                                "오늘의 움직임 — 구체적 수치 포함 한 문단 "
                                "(예: '금융 섹터 +1.8%로 KOSPI +0.3% 대비 +1.5%p 아웃퍼폼. "
                                "삼성생명 +2.1%, DB손해보험 +1.9% 급등. "
                                "오전부터 외국인 순매수 유입.')"
                            ),
                        },
                        "background": {
                            "type": "string",
                            "description": (
                                "배경 — 왜 오늘 이 테마가 움직였나 + 더 큰 그림 "
                                "(2~3 문단, 최근 맥락과 오늘 이벤트 연결)"
                            ),
                        },
                        "global_link": {
                            "type": "string",
                            "description": (
                                "글로벌 연결고리 — 어떤 글로벌 이벤트·흐름이 "
                                "한국 시장에 이 방향으로 영향을 줬나 (1~2 문단)"
                            ),
                        },
                        "advisor_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 3,
                            "maxItems": 4,
                            "description": (
                                "상담사 토킹포인트 — 고객에게 바로 쓸 수 있는 문장 3~4개. "
                                "전문 용어 최소화, 원인·결과 중심. "
                                "예: '금리가 내려갈 것 같다는 기대감이 커지면서 "
                                "보험사가 갖고 있는 채권 가치가 올라가기 때문입니다.'"
                            ),
                        },
                        "client_qa": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "q": {
                                        "type": "string",
                                        "description": "고객이 실제로 물어볼 법한 질문",
                                    },
                                    "a": {
                                        "type": "string",
                                        "description": (
                                            "상담사 답변 — 2~3 문장, 쉬운 언어, "
                                            "투자 권유 없이 팩트·인과관계만"
                                        ),
                                    },
                                },
                                "required": ["q", "a"],
                            },
                            "minItems": 2,
                            "maxItems": 3,
                            "description": "고객 Q&A 2~3쌍",
                        },
                        "risk": {
                            "type": "string",
                            "description": "반전 시나리오 — 이 테마가 꺾일 수 있는 조건 (1~2 문장)",
                        },
                        "related_funds": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "펀드 코드 (예: N150)",
                                    },
                                    "relevance": {
                                        "type": "string",
                                        "description": "관련 이유 (15자 이내)",
                                    },
                                },
                                "required": ["code", "relevance"],
                            },
                            "minItems": 1,
                            "maxItems": 5,
                            "description": "이 테마와 직접 관련된 변액보험 펀드 (카탈로그에서만 선택)",
                        },
                    },
                    "required": [
                        "name", "today_move", "background", "global_link",
                        "advisor_points", "client_qa", "risk", "related_funds",
                    ],
                },
            },
            "daily_summary": {
                "type": "object",
                "properties": {
                    "one_line": {
                        "type": "string",
                        "description": "오늘 시장을 한 문장으로 — 상담사가 고객에게 문자 보낼 때 쓸 수 있는 문장",
                    },
                    "tomorrow_watch": {
                        "type": "string",
                        "description": "내일·이번 주 주목 변수 1~2개 (경제지표·이벤트·발표 일정)",
                    },
                    "naver_watch": {
                        "type": "string",
                        "description": (
                            "Naver 상위 중 오늘 선정되지 않은 주목 테마 1개 + "
                            "왜 주목해야 하는지 한 문장"
                        ),
                    },
                },
                "required": ["one_line", "tomorrow_watch", "naver_watch"],
            },
        },
        "required": ["themes", "daily_summary"],
    },
}


# ── Step 1: Naver theme data ───────────────────────────────────────────────────


def load_naver_themes(ref_date_str: str, n_days: int = 7) -> tuple[list[dict], list[dict]]:
    """오늘 수익률 목록 + 7일 지속성 목록 반환.

    Returns:
        today_themes: 오늘 수익률 기준 정렬 [{theme, today_return}]
        persistence_top: 7일 지속성 상위 [{theme, persistence, avg_return, ...}]
    """
    if not THEME_HISTORY_PATH.exists():
        print(f"  WARN: theme_history.json 없음: {THEME_HISTORY_PATH}")
        return [], []

    with open(THEME_HISTORY_PATH, encoding="utf-8") as f:
        history = json.load(f)

    all_dates = sorted(d for d in history if d <= ref_date_str)
    if not all_dates:
        print("  WARN: theme_history.json에 해당 날짜 이전 데이터 없음")
        return [], []

    # 오늘 (ref_date 또는 가장 최근일)
    today_key = ref_date_str if ref_date_str in history else all_dates[-1]
    today_data = history.get(today_key, {})
    print(f"  → 오늘 기준: {today_key}  테마 수 {len(today_data)}개")

    today_themes = sorted(
        [
            {"theme": t, "today_return": v.get("today", 0)}
            for t, v in today_data.items()
        ],
        key=lambda x: x["today_return"],
        reverse=True,
    )

    # 7일 지속성
    dates_7d = all_dates[-n_days:]
    scores: dict[str, dict] = defaultdict(
        lambda: {"positive_days": 0, "total_days": 0, "returns": []}
    )
    for d in dates_7d:
        for theme, v in history[d].items():
            scores[theme]["total_days"] += 1
            scores[theme]["returns"].append(v.get("today", 0))
            if v.get("today", 0) > 0:
                scores[theme]["positive_days"] += 1

    persistence_list = []
    for theme, s in scores.items():
        if s["total_days"] >= 4:
            p = s["positive_days"] / s["total_days"] * 100
            avg = sum(s["returns"]) / len(s["returns"]) if s["returns"] else 0.0
            persistence_list.append(
                {
                    "theme": theme,
                    "persistence": round(p),
                    "avg_return": round(avg, 2),
                    "total_days": s["total_days"],
                    "positive_days": s["positive_days"],
                    "score": round(p * avg, 2),
                }
            )

    persistence_top = sorted(
        persistence_list,
        key=lambda x: (x["persistence"], x["avg_return"]),
        reverse=True,
    )

    return today_themes, persistence_top


# ── Step 2: Market context from _data.json ────────────────────────────────────


def load_market_context(date_str: str) -> dict:
    """_data.json에서 KOSPI 등락, 상위 종목 등 맥락 데이터 로드."""
    yyyy_mm = date_str[:7]
    data_json = ROOT / "output" / "summary" / yyyy_mm / f"{date_str}_data.json"
    if not data_json.exists():
        print(f"  WARN: _data.json 없음 ({data_json.name}) — 맥락 없이 진행")
        return {}

    with open(data_json, encoding="utf-8") as f:
        data = json.load(f)

    eq = data.get("equity", {})
    kospi = eq.get("KOSPI", {})
    kosdaq = eq.get("KOSDAQ", {})
    sp500 = eq.get("S&P500", {})

    # 상위 종목 (status=ok, 오늘 수익률 기준)
    stocks = data.get("stocks", {})
    ranked = sorted(
        [
            (name, v.get("daily", 0), v.get("close"))
            for name, v in stocks.items()
            if v.get("data_status") == "ok" and v.get("daily") is not None
        ],
        key=lambda x: x[1],
        reverse=True,
    )
    top_stocks = [{"name": n, "daily": r, "close": c} for n, r, c in ranked[:10]]
    bot_stocks = [{"name": n, "daily": r, "close": c} for n, r, c in ranked[-5:]]

    return {
        "kospi_daily": kospi.get("daily"),
        "kospi_close": kospi.get("close"),
        "kosdaq_daily": kosdaq.get("daily"),
        "sp500_daily": sp500.get("daily"),
        "top_stocks": top_stocks,
        "bot_stocks": bot_stocks,
    }


# ── Step 3: Tavily ─────────────────────────────────────────────────────────────


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


def search_global_triggers(
    today_themes: list[dict],
    date_str: str,
) -> dict[str, list[dict]]:
    """오늘 수익률 상위 테마별 글로벌 트리거 검색 (최대 6개)."""
    results: dict[str, list[dict]] = {}
    top = [t for t in today_themes if t["today_return"] > 0][:6]
    for t in top:
        name = t["theme"]
        print(f"    검색: {name}")
        hits = _tavily_search(
            f"Korea stock market {name} sector news today {date_str[:7]}",
            max_results=4,
        )
        results[name] = hits
    return results


# ── Step 4: Claude — theme selection ──────────────────────────────────────────


def select_themes(
    client,
    today_themes: list[dict],
    persistence_top: list[dict],
    tavily_results: dict[str, list[dict]],
    market_ctx: dict,
    date_str: str,
) -> list[dict]:
    # 오늘 수익률 상위 20개 텍스트
    today_text = "\n".join(
        f"- {t['theme']}: 오늘 {t['today_return']:+.2f}%"
        for t in today_themes[:20]
    ) or "없음"

    # 7일 지속성 상위 15개 텍스트
    persistence_text = "\n".join(
        f"- {t['theme']}: 지속성 {t['persistence']}%"
        f" ({t['positive_days']}/{t['total_days']}일), 7일 평균 {t['avg_return']:+.2f}%"
        for t in persistence_top[:15]
    ) or "없음"

    # Tavily 요약
    tavily_lines = []
    for theme_name, hits in tavily_results.items():
        if hits:
            answer = hits[0].get("answer", "")
            summary = answer[:150] if answer else ", ".join(h.get("title", "") for h in hits[:2])
            tavily_lines.append(f"- {theme_name}: {summary}")
    tavily_text = "\n".join(tavily_lines) if tavily_lines else "없음"

    # 시장 맥락
    ctx_lines = []
    if market_ctx.get("kospi_daily") is not None:
        ctx_lines.append(f"KOSPI: {market_ctx['kospi_daily']:+.2f}%"
                         f" (종가 {market_ctx['kospi_close']:,.0f})")
    if market_ctx.get("sp500_daily") is not None:
        ctx_lines.append(f"S&P500(전날): {market_ctx['sp500_daily']:+.2f}%")
    if market_ctx.get("top_stocks"):
        tops = ", ".join(
            f"{s['name']} {s['daily']:+.2f}%" for s in market_ctx["top_stocks"][:5]
        )
        ctx_lines.append(f"오늘 상위 종목: {tops}")
    ctx_text = "\n".join(ctx_lines) if ctx_lines else "없음"

    resp = client.messages.create(
        model=BEDROCK_MODEL,
        max_tokens=1500,
        system=(
            "변액보험 상담사를 위한 일간 테마 리서치 편집장입니다.\n"
            "오늘 실제로 움직인 수급(Naver 테마 수익률) + 지속성 + 뉴스(Tavily)를 교차해\n"
            "가장 설명력 있는 테마 1~2개를 선정하세요.\n\n"
            "선정 기준 (우선순위):\n"
            "① 오늘 수익률 양수 + 7일 지속성 >= 60% → 최우선\n"
            "② 오늘 수익률 상위 + Tavily 글로벌 트리거 확인 → 우선\n"
            "③ 오늘 수익률 상위 (지속성·글로벌 미확인) → 참고\n\n"
            "상담사가 오늘 고객 전화를 받았을 때 바로 설명할 수 있는 테마를 선정하세요.\n"
            "오늘 수익률이 마이너스이거나 거의 0인 테마는 선정하지 마세요."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"오늘({date_str}) 한국 주식시장 핵심 테마를 선정해주세요.\n\n"
                    f"[시장 개요]\n{ctx_text}\n\n"
                    f"[Naver 테마 오늘 수익률 상위 20개]\n{today_text}\n\n"
                    f"[Naver 7일 지속성 상위 15개]\n{persistence_text}\n\n"
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


# ── Step 5: Claude — report writing ───────────────────────────────────────────


def write_report(
    client,
    selected: list[dict],
    today_themes: list[dict],
    persistence_top: list[dict],
    tavily_results: dict[str, list[dict]],
    market_ctx: dict,
    date_str: str,
) -> dict:
    theme_ctx_parts = []
    for t in selected:
        naver_name = t.get("naver_theme", t["name"])
        hits = tavily_results.get(naver_name, [])
        naver_today = next(
            (n for n in today_themes if n["theme"] == naver_name), {}
        )
        naver_persist = next(
            (p for p in persistence_top if p["theme"] == naver_name), {}
        )
        news_lines = "\n".join(
            f"  [{i+1}] {h.get('title', '')}: {h.get('content', '')[:250]}"
            for i, h in enumerate(hits[:4])
        )
        theme_ctx_parts.append(
            f"[테마: {t['name']}]\n"
            f"선정 근거: {t.get('selection_reason', '')}\n"
            f"글로벌 트리거: {t.get('global_trigger', '없음')}\n"
            f"오늘 Naver 수익률: {naver_today.get('today_return', 0):+.2f}%\n"
            f"7일 지속성: {naver_persist.get('persistence', '-')}%"
            f" ({naver_persist.get('positive_days', '-')}/{naver_persist.get('total_days', '-')}일)\n"
            f"7일 평균 수익률: {naver_persist.get('avg_return', 0):+.2f}%\n\n"
            f"Tavily 최신 뉴스:\n{news_lines or '없음'}"
        )

    # 시장 맥락 요약
    ctx_summary = ""
    if market_ctx.get("kospi_daily") is not None:
        ctx_summary = (
            f"오늘 KOSPI {market_ctx['kospi_daily']:+.2f}%"
            f" (종가 {market_ctx['kospi_close']:,.0f})"
        )
        if market_ctx.get("sp500_daily") is not None:
            ctx_summary += f", 전날 S&P500 {market_ctx['sp500_daily']:+.2f}%"
    if market_ctx.get("top_stocks"):
        tops = ", ".join(
            f"{s['name']} {s['daily']:+.2f}%" for s in market_ctx["top_stocks"][:5]
        )
        ctx_summary += f"\n오늘 상위 종목: {tops}"

    resp = client.messages.create(
        model=BEDROCK_MODEL,
        max_tokens=6000,
        system=(
            "변액보험 상담사를 위한 일간 테마 리서치 작성자입니다.\n\n"
            "핵심 원칙:\n"
            "- today_move: 오늘 실제 수치(%, 종목명, 등락)를 반드시 포함한 한 문단\n"
            "- background: '왜 오늘 이 테마가 움직였나'를 오늘 이벤트 + 더 큰 그림으로 설명\n"
            "- global_link: 글로벌 이벤트 → 한국 시장 파급 경로를 명확히\n"
            "- advisor_points: 고객에게 바로 쓸 수 있는 문장. '밸류에이션' 같은 전문 용어 금지.\n"
            "  예시 좋음: '금리가 내려갈 것 같다는 기대가 커지면서 보험사 채권 가치가 올랐습니다.'\n"
            "  예시 나쁨: '금리 민감 섹터의 밸류에이션 리레이팅이 진행 중입니다.'\n"
            "- client_qa: 고객이 실제로 물어볼 법한 질문과 솔직한 답변.\n"
            "  투자 권유 표현('매수하세요') 금지. 팩트와 인과관계만.\n"
            "- '지속적 성장이 예상됨' 같은 막연한 일반론 금지. 구체적 수치·이벤트 중심.\n\n"
            f"related_funds: 아래 카탈로그에서 이 테마에 직접 해당하는 펀드만 선정.\n\n"
            f"[변액보험 펀드 카탈로그]\n{FUND_CATALOG_TEXT}"
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"오늘({date_str}) 선정된 테마 보고서를 작성해주세요.\n\n"
                    f"[오늘 시장 개요]\n{ctx_summary or '없음'}\n\n"
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
    return {"themes": [], "daily_summary": {}}


# ── HTML rendering ─────────────────────────────────────────────────────────────


def _theme_card_html(theme_body: dict, meta: dict) -> str:
    name = theme_body.get("name", "")
    today_move = theme_body.get("today_move", "")
    background = theme_body.get("background", "")
    global_link = theme_body.get("global_link", "")
    advisor_points = theme_body.get("advisor_points", [])
    client_qa = theme_body.get("client_qa", [])
    risk = theme_body.get("risk", "")
    related_funds = theme_body.get("related_funds", [])

    naver_return = meta.get("naver_today_return", 0)
    naver_persist = meta.get("naver_persistence_7d", 0)
    global_trigger = meta.get("global_trigger", "")
    selection_reason = meta.get("selection_reason", "")

    # signal chips
    ret_color = "chip-pos" if naver_return >= 0 else "chip-neg"
    naver_chip = (
        f'<span class="chip {ret_color}">Naver 오늘 {naver_return:+.2f}%</span>'
        f'<span class="chip chip-persist">지속성 {naver_persist}%</span>'
    )
    tavily_chip = '<span class="chip chip-tavily">글로벌뉴스</span>' if global_trigger else ""

    # advisor points
    points_html = "".join(f"<li>{p}</li>" for p in advisor_points)
    points_block = (
        f'<div class="section">'
        f'<div class="section-label">상담사 토킹포인트</div>'
        f'<ul class="talking-points">{points_html}</ul>'
        f'</div>'
    ) if advisor_points else ""

    # client Q&A
    qa_blocks = "".join(
        f'<div class="qa-block">'
        f'<div class="qa-q">Q. {qa.get("q","")}</div>'
        f'<div class="qa-a">A. {qa.get("a","")}</div>'
        f'</div>'
        for qa in client_qa
    )
    qa_section = (
        f'<div class="section">'
        f'<div class="section-label">고객 Q&amp;A</div>'
        f'<div class="qa-list">{qa_blocks}</div>'
        f'</div>'
    ) if client_qa else ""

    # fund chips
    valid_funds = {code: nm for code, nm, _ in FUND_CATALOG} if FUND_CATALOG else {}
    fund_html = ""
    valid = [f for f in related_funds if f.get("code", "") in valid_funds]
    if valid:
        chips = "".join(
            f'<span class="fund-chip" title="{f.get("relevance","")}">'
            f'[{f["code"]}] {valid_funds[f["code"]]}</span>'
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
    <div class="signal-bar">{naver_chip}{tavily_chip}</div>
  </div>
  <div class="theme-body">
    <div class="selection-reason"><strong>선정 근거</strong>: {selection_reason}</div>

    <div class="today-move">
      <div class="move-label">오늘의 움직임</div>
      <div class="move-text">{today_move}</div>
    </div>

    <div class="section">
      <div class="section-label">배경 — 왜 오늘 이 테마인가</div>
      <div class="section-text">{background}</div>
    </div>
    <div class="section">
      <div class="section-label">글로벌 연결고리</div>
      <div class="section-text">{global_link}</div>
    </div>

    {points_block}
    {qa_section}

    <div class="risk-box">
      <strong>리스크</strong>: {risk}
    </div>
    {fund_html}
  </div>
</div>"""


def render_html(
    selected: list[dict],
    report_data: dict,
    today_themes: list[dict],
    persistence_top: list[dict],
    market_ctx: dict,
    date_str: str,
) -> str:
    generated = datetime.now()

    report_themes = report_data.get("themes", [])
    cards_html = "\n".join(
        _theme_card_html(report_themes[i], selected[i])
        for i in range(min(len(selected), len(report_themes)))
    ) or "<p>테마 분석 결과 없음</p>"

    summary = report_data.get("daily_summary", {})
    one_line = summary.get("one_line", "")
    tomorrow_watch = summary.get("tomorrow_watch", "")
    naver_watch = summary.get("naver_watch", "")

    theme_names = " · ".join(t.get("name", "") for t in selected)

    # 오늘 Naver 테이블 (상위/하위 포함, 20개)
    _max_abs = max((abs(t["today_return"]) for t in today_themes[:20]), default=1) or 1

    def _bar(val: float) -> str:
        w = min(int(abs(val) / _max_abs * 60), 60)
        color = "#047857" if val >= 0 else "#dc2626"
        cls = "pos" if val >= 0 else "neg"
        return (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:{w}px;height:8px;border-radius:4px;'
            f'background:{color};min-width:2px"></div>'
            f'<span class="{cls}">{val:+.2f}%</span>'
            f'</div>'
        )

    # 지속성 맵 (표에 병기용)
    persist_map = {p["theme"]: p["persistence"] for p in persistence_top}

    naver_rows = "".join(
        f"<tr>"
        f"<td>{i+1}</td>"
        f"<td>{t['theme']}</td>"
        f"<td>{_bar(t['today_return'])}</td>"
        f"<td style='color:#7c8298;font-size:12px'>{persist_map.get(t['theme'], '-')}%</td>"
        f"</tr>"
        for i, t in enumerate(today_themes[:20])
        if t["today_return"] != 0
    )

    # 시장 개요 KPI 박스
    kpi_items = []
    if market_ctx.get("kospi_daily") is not None:
        chg = market_ctx["kospi_daily"]
        cls = "kpi-pos" if chg > 0 else ("kpi-neg" if chg < 0 else "")
        kpi_items.append(
            f'<div class="kpi-item">'
            f'<span class="kpi-label">KOSPI</span>'
            f'<span class="kpi-val {cls}">{chg:+.2f}%</span>'
            f'<span class="kpi-sub">{market_ctx["kospi_close"]:,.0f}</span>'
            f'</div>'
        )
    if market_ctx.get("kosdaq_daily") is not None:
        chg = market_ctx["kosdaq_daily"]
        cls = "kpi-pos" if chg > 0 else ("kpi-neg" if chg < 0 else "")
        kpi_items.append(
            f'<div class="kpi-item">'
            f'<span class="kpi-label">KOSDAQ</span>'
            f'<span class="kpi-val {cls}">{chg:+.2f}%</span>'
            f'</div>'
        )
    if market_ctx.get("sp500_daily") is not None:
        chg = market_ctx["sp500_daily"]
        cls = "kpi-pos" if chg > 0 else ("kpi-neg" if chg < 0 else "")
        kpi_items.append(
            f'<div class="kpi-item">'
            f'<span class="kpi-label">S&amp;P500</span>'
            f'<span class="kpi-val {cls}">{chg:+.2f}%</span>'
            f'<span class="kpi-sub">전날</span>'
            f'</div>'
        )
    kpi_bar = (
        f'<div class="kpi-bar">{"".join(kpi_items)}</div>'
        if kpi_items else ""
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Theme Research · {date_str} · Anthillia</title>
<link rel="icon" href="../../assets/favicon.svg" type="image/svg+xml">
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root {{
  --bg:#f0f2f7; --card:#fff; --border:#e2e6f0;
  --text:#2d3148; --muted:#7c8298;
  --primary:#F58220; --primary-light:#fff3e8;
  --navy:#043B72;
  --green:#1a9e6e; --green-bg:#edfaf5; --green-border:#a7f3d0;
  --red:#dc2626; --red-bg:#fff5f5; --red-border:#fecaca;
  --blue-bg:#f0f7ff; --blue-border:#bfdbfe;
  --yellow-bg:#fffbeb; --yellow-border:#fde68a;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Spoqa Han Sans Neo',-apple-system,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.75;
  padding:48px 24px;max-width:960px;margin:0 auto;
}}
/* nav */
.nav{{display:flex;gap:8px;align-items:center;font-size:13px;color:var(--muted);margin-bottom:24px}}
.nav a{{color:var(--muted);text-decoration:none}}.nav a:hover{{color:var(--primary)}}
.nav .sep{{color:var(--border)}}
/* header */
.header{{margin-bottom:32px;padding-bottom:24px;border-bottom:2px solid var(--border)}}
.header-badge{{
  display:inline-block;background:var(--primary);color:#fff;
  font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px;
  text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px;
}}
.header h1{{font-size:26px;font-weight:800;color:#1a1d2e;margin-bottom:6px}}
.header .meta{{font-size:13px;color:var(--muted)}}
/* KPI bar */
.kpi-bar{{
  display:flex;flex-wrap:wrap;gap:12px;
  margin-top:16px;padding:14px 18px;
  background:var(--card);border:1px solid var(--border);border-radius:12px;
}}
.kpi-item{{display:flex;flex-direction:column;align-items:flex-start;min-width:80px}}
.kpi-label{{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
.kpi-val{{font-size:18px;font-weight:800;line-height:1.2}}
.kpi-pos{{color:var(--green)}} .kpi-neg{{color:var(--red)}}
.kpi-sub{{font-size:11px;color:var(--muted)}}
/* theme card */
.theme-card{{
  background:var(--card);border:1px solid var(--border);border-radius:20px;
  margin-bottom:24px;box-shadow:0 2px 12px rgba(0,0,0,.05);overflow:hidden;
}}
.theme-header{{padding:24px 28px 18px;border-bottom:1px solid var(--border)}}
.theme-name{{font-size:22px;font-weight:800;color:#1a1d2e;margin-bottom:12px}}
.signal-bar{{display:flex;flex-wrap:wrap;gap:8px}}
.chip{{font-size:11px;font-weight:700;padding:3px 12px;border-radius:20px}}
.chip-pos{{color:#047857;background:#d1fae5;border:1px solid #6ee7b7}}
.chip-neg{{color:var(--red);background:var(--red-bg);border:1px solid var(--red-border)}}
.chip-persist{{color:var(--navy);background:#dbeafe;border:1px solid #93c5fd}}
.chip-tavily{{color:#6b21a8;background:#f3e8ff;border:1px solid #d8b4fe}}
.theme-body{{padding:0 28px 28px}}
/* selection reason */
.selection-reason{{
  margin:18px 0 0;padding:12px 16px;
  background:#f8f9fc;border-radius:10px;border-left:3px solid var(--primary);
  font-size:13px;color:var(--muted);
}}
/* today move */
.today-move{{
  margin:18px 0;padding:16px 20px;
  background:var(--green-bg);border:1px solid var(--green-border);border-radius:12px;
}}
.move-label{{
  font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;
  color:var(--green);margin-bottom:6px;
}}
.move-text{{font-size:14px;font-weight:500;line-height:1.7;color:#1a2e25}}
/* sections */
.section{{padding:16px 0;border-bottom:1px solid var(--border)}}
.section:last-of-type{{border-bottom:none}}
.section-label{{
  display:inline-block;font-size:10px;font-weight:800;
  text-transform:uppercase;letter-spacing:.08em;
  color:var(--navy);background:#eef1f8;padding:3px 10px;border-radius:20px;margin-bottom:10px;
}}
.section-text{{font-size:14px;line-height:1.85;white-space:pre-wrap}}
/* talking points */
.talking-points{{
  list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:10px;
}}
.talking-points li{{
  font-size:14px;line-height:1.7;padding:10px 16px;
  background:var(--blue-bg);border:1px solid var(--blue-border);border-radius:10px;
  position:relative;padding-left:36px;
}}
.talking-points li::before{{
  content:"💬";position:absolute;left:12px;top:10px;font-size:13px;
}}
/* Q&A */
.qa-list{{display:flex;flex-direction:column;gap:14px}}
.qa-block{{
  border:1px solid var(--border);border-radius:12px;overflow:hidden;
}}
.qa-q{{
  background:#f8f9fc;padding:10px 16px;font-size:13px;font-weight:600;
  color:var(--navy);border-bottom:1px solid var(--border);
}}
.qa-a{{
  padding:12px 16px;font-size:13px;line-height:1.75;background:var(--card);
}}
/* risk / fund */
.risk-box{{
  margin:16px 0;padding:14px 18px;
  background:var(--red-bg);border:1px solid var(--red-border);border-radius:10px;font-size:13px;
}}
.fund-section{{margin-top:16px}}
.fund-chips{{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}}
.fund-chip{{
  font-size:12px;font-weight:600;color:#6b21a8;background:#f8f0ff;
  border:1px solid #e9d5ff;padding:4px 12px;border-radius:16px;cursor:default;
}}
.fund-chip:hover{{background:#ede2ff}}
/* summary card */
.summary-card{{
  background:var(--card);border:1px solid var(--border);border-radius:20px;
  padding:28px;box-shadow:0 2px 12px rgba(0,0,0,.05);margin-bottom:24px;
}}
.summary-card h2{{
  font-size:17px;font-weight:700;color:var(--navy);
  margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border);
}}
.one-line{{
  font-size:16px;font-weight:700;line-height:1.6;color:#1a1d2e;
  padding:14px 18px;background:var(--primary-light);
  border:1px solid #fde0c0;border-radius:10px;margin-bottom:18px;
}}
.summary-item{{
  font-size:13px;margin-bottom:10px;line-height:1.75;
  padding:10px 14px;border-radius:8px;background:#f8f9fc;
}}
/* naver table */
.naver-table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:20px}}
.naver-table th{{
  background:#f8f9fc;color:var(--muted);font-weight:600;
  padding:8px 12px;text-align:left;border-bottom:2px solid var(--border);
}}
.naver-table td{{padding:8px 12px;border-bottom:1px solid var(--border)}}
.naver-table tr:last-child td{{border-bottom:none}}
.naver-table .pos{{color:#047857;font-weight:600}}
.naver-table .neg{{color:var(--red);font-weight:600}}
/* disclaimer */
.ai-disclaimer{{
  background:var(--yellow-bg);border:1px solid var(--yellow-border);border-radius:10px;
  padding:14px 20px;margin-top:24px;font-size:12px;color:#92400e;line-height:1.7;
}}
.footer{{text-align:center;font-size:12px;color:var(--muted);padding-top:28px;margin-top:8px}}
.footer a{{color:var(--primary);text-decoration:none}}
@media(max-width:720px){{
  body{{padding:24px 12px}}
  .theme-header,.theme-body{{padding-left:20px;padding-right:20px}}
  .theme-name{{font-size:18px}}
  .kpi-bar{{gap:16px}}
}}
</style>
</head>
<body>

<div class="nav">
  <a href="../../../index.html">&larr; Anthillia</a>
  <span class="sep">/</span>
  <a href="../../index.html">Research</a>
  <span class="sep">/</span>
  <span>Daily Theme Research</span>
</div>

<div class="header">
  <div class="header-badge">Daily Theme Research</div>
  <h1>{date_str} 오늘의 테마</h1>
  <p class="meta">
    Naver 테마 × Tavily 글로벌 트리거 &middot;
    테마: <strong>{theme_names}</strong>
  </p>
  {kpi_bar}
</div>

{cards_html}

<div class="summary-card">
  <h2>오늘 요약</h2>
  <div class="one-line">{one_line}</div>
  <div class="summary-item"><strong>내일·이번 주 주목 변수</strong> — {tomorrow_watch}</div>
  <div class="summary-item"><strong>Naver 주목 테마</strong> — {naver_watch}</div>

  <table class="naver-table">
    <thead>
      <tr>
        <th>#</th>
        <th>Naver 테마</th>
        <th>오늘 수익률</th>
        <th>7일 지속성</th>
      </tr>
    </thead>
    <tbody>{naver_rows}</tbody>
  </table>
</div>

<div class="ai-disclaimer">
  ⚠️ 본 보고서는 AI가 자동 생성한 참고 자료이며, 투자 권유가 아닙니다.
  Naver 테마 데이터 및 글로벌 뉴스를 교차 분석했으나 수치·해석에 오류가 포함될 수 있으므로
  투자 판단 시 반드시 원본 데이터를 확인하시기 바랍니다.
</div>

<div class="footer">
  AI 분석: Bedrock Claude &middot; Naver 테마 지속성 &middot; Tavily 뉴스 &middot;
  생성: {generated.strftime('%Y-%m-%d %H:%M KST')}
  &middot; <a href="../index.html">보고서 목록</a>
</div>

</body>
</html>
"""


# ── main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="일간 테마 리서치 생성")
    parser.add_argument("--date", help="기준 날짜 (YYYY-MM-DD, 기본: 오늘)")
    parser.add_argument("--dry-run", action="store_true", help="Claude 호출 없이 구조 확인")
    parser.add_argument("--force", action="store_true", help="이미 생성된 보고서가 있어도 덮어쓰기")
    args = parser.parse_args()

    ref_date = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    ref_date_str = ref_date.strftime("%Y-%m-%d")

    if ref_date.date() > datetime.now().date():
        print(f"오류: 미래 날짜 ({ref_date_str}) — 실행 불가")
        sys.exit(1)

    print("=== 일간 테마 리서치 생성 ===")
    print(f"기준 날짜: {ref_date_str}")

    month_dir = OUTPUT_BASE / ref_date.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    output_path = month_dir / f"{ref_date_str}.html"
    story_path = month_dir / f"{ref_date_str}_story.html"

    if output_path.exists() and not args.force and not args.dry_run:
        print(f"  이미 존재: {output_path}")
        print("  재생성하려면 --force 옵션을 사용하세요.")
        sys.exit(0)

    # ── 1. Naver 테마 ─────────────────────────────────────────────────────────
    print("\n[1/4] Naver 테마 로드...")
    today_themes, persistence_top = load_naver_themes(ref_date_str)
    if not today_themes:
        print("  WARN: Naver 데이터 없음")
    else:
        positive = [t for t in today_themes if t["today_return"] > 0]
        print(f"  오늘 수익률 양수 테마: {len(positive)}개")
        print("  상위 5개:")
        for t in today_themes[:5]:
            print(f"    {t['theme']}: {t['today_return']:+.2f}%")

    # ── 2. 시장 맥락 ──────────────────────────────────────────────────────────
    print("\n[2/4] 시장 맥락 로드...")
    market_ctx = load_market_context(ref_date_str)
    if market_ctx.get("kospi_daily") is not None:
        print(f"  KOSPI: {market_ctx['kospi_daily']:+.2f}%")

    # ── 3. Tavily ─────────────────────────────────────────────────────────────
    print("\n[3/4] Tavily 글로벌 트리거 검색...")
    if args.dry_run or not TAVILY_API_KEY:
        tavily_results: dict[str, list[dict]] = {}
        print("  [SKIP]" + (" DRY-RUN" if args.dry_run else " TAVILY_API_KEY 없음"))
    else:
        tavily_results = search_global_triggers(today_themes, ref_date_str)
        print(f"  → {sum(len(v) for v in tavily_results.values())}건 수집")

    if args.dry_run:
        print("\n[DRY-RUN] Claude 호출 스킵")
        selected = [
            {
                "name": today_themes[0]["theme"] if today_themes else "DRY-RUN 테마",
                "naver_theme": today_themes[0]["theme"] if today_themes else "",
                "naver_today_return": today_themes[0]["today_return"] if today_themes else 0,
                "naver_persistence_7d": 60,
                "global_trigger": "테스트 트리거",
                "selection_reason": "DRY-RUN 확인용",
            }
        ]
        report_data: dict = {
            "themes": [
                {
                    "name": selected[0]["name"],
                    "today_move": "DRY-RUN: 오늘의 움직임",
                    "background": "DRY-RUN: 배경 서술",
                    "global_link": "DRY-RUN: 글로벌 연결고리",
                    "advisor_points": ["DRY-RUN: 토킹포인트 1", "DRY-RUN: 토킹포인트 2"],
                    "client_qa": [
                        {"q": "DRY-RUN 질문?", "a": "DRY-RUN 답변."},
                    ],
                    "risk": "DRY-RUN: 리스크",
                    "related_funds": [{"code": "N150", "relevance": "AI 국내주식"}],
                }
            ],
            "daily_summary": {
                "one_line": "DRY-RUN: 오늘 요약 한 줄",
                "tomorrow_watch": "DRY-RUN: 내일 주목 변수",
                "naver_watch": "DRY-RUN: Naver 주목 테마",
            },
        }
    else:
        client = _get_bedrock_client()

        # ── 4-A: 테마 선정 ────────────────────────────────────────────────────
        print("\n[4/4-A] Claude 테마 선정...")
        selected = select_themes(
            client, today_themes, persistence_top, tavily_results, market_ctx, ref_date_str
        )
        if not selected:
            print("  오류: 테마 선정 실패 - 종료")
            sys.exit(1)
        print(f"  -> {len(selected)}개 선정:")
        for t in selected:
            print(
                f"    - {t['name']}  (오늘 {t.get('naver_today_return', 0):+.2f}%,"
                f" 7일 지속성 {t.get('naver_persistence_7d')}%)"
            )

        # ── 4-B: 보고서 본문 ─────────────────────────────────────────────────
        print("\n[4/4-B] Claude 보고서 작성...")
        report_data = write_report(
            client, selected, today_themes, persistence_top,
            tavily_results, market_ctx, ref_date_str,
        )

        tok = _token_totals
        cost = tok["prompt"] / 1e6 * 3.0 + tok["completion"] / 1e6 * 15.0
        print(
            f"\n  [토큰] input={tok['prompt']:,}  output={tok['completion']:,}"
            f"  (Sonnet ~${cost:.4f})"
        )
        try:
            sys.path.insert(0, str(ROOT))
            import notify_telegram as _nt
            _nt.send(
                _nt.build_gpt_usage_message(
                    "generate_research", ref_date_str, tok["prompt"], tok["completion"]
                )
            )
        except Exception:
            pass

    # ── 5. HTML 저장 ──────────────────────────────────────────────────────────
    print("\n[5/5] HTML 저장...")
    html = render_html(
        selected, report_data, today_themes, persistence_top, market_ctx, ref_date_str
    )
    output_path.write_text(html, encoding="utf-8")
    shutil.copy2(output_path, story_path)
    print(f"  -> {output_path}")
    print(f"  -> {story_path}")

    theme_names = " - ".join(t.get("name", "") for t in selected)

    # ── 6. Git push ───────────────────────────────────────────────────────────
    if not args.dry_run:
        print("\n[6/6] Git push...")
        try:
            import subprocess as _sp
            _sp.run(
                ["git", "add",
                 str(output_path.relative_to(ROOT)),
                 str(story_path.relative_to(ROOT))],
                cwd=str(ROOT), check=True, capture_output=True,
            )
            commit = _sp.run(
                ["git", "commit", "-m",
                 f"feat: {ref_date_str} 일간 테마 리서치 — {theme_names}"],
                cwd=str(ROOT), capture_output=True, text=True,
            )
            if commit.returncode == 0:
                _sp.run(["git", "push", "origin", "main"],
                        cwd=str(ROOT), check=True, capture_output=True)
                print("  -> git push 완료")
            else:
                print("  => 변경사항 없음 (push 스킵)")
        except Exception as e:
            print(f"  [WARN] git push 실패: {e}")

    print(f"\n완료. 테마: {theme_names}")


if __name__ == "__main__":
    main()
