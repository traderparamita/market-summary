#!/usr/bin/env python3
"""PostToolUse hook for Edit|Write — deterministic structure guard.

Checks (Python regex, no LLM):
  1. Is this a Market Story file?
  2. Are all 6 required sections present?
  3. Are any CSS classes used that are not in the whitelist?

Non-story files short-circuit to {"decision":"allow"} immediately.
Temporal accuracy (forward-looking, session cross-reference, causal direction)
is handled by the separate type:prompt hook that runs after this one.
"""
import json
import re
import sys


def is_story_file(file_path: str) -> bool:
    # 절대경로("/output/") 또는 상대경로("output/") 모두 처리
    has_output = "/output/" in file_path or file_path.startswith("output/")
    return (
        (has_output and file_path.endswith(".html"))
        or file_path.endswith("generate_stories.py")
        or file_path.endswith("inject_stories.py")
    )


# 필수 섹션 — 6개 모두 있어야 함
REQUIRED_SECTIONS = [
    ("story-hero",   'class="story-hero"'),
    ("causal-chain", 'class="causal-chain"'),
    ("session-grid", 'class="session-grid"'),
    ("insight-grid", 'class="insight-grid"'),
    ("risk-section", 'class="risk-section"'),
    ("risk-items",   'class="risk-items"'),
]

# 주간/월간은 session-grid 없음 (SKILL.md: "주간 Story는 일간과 달리 Session Grid 없음 — Narrative 중심")
WEEKLY_MONTHLY_SKIP = {"session-grid"}

# CSS 화이트리스트 (SKILL.md 기준)
CSS_WHITELIST = {
    # Story Hero
    "story-hero", "story-text",
    # Causal Chain
    "causal-chain", "cause-node", "cause-arrow",
    "node-label", "node-title", "node-detail", "node-impact",
    # Session Grid
    "session-grid", "session-block", "session-header", "session-icon",
    "session-name", "session-time", "session-verdict",
    "verdict-up", "verdict-down", "verdict-flat",
    "session-events", "ev-time", "session-kpi",
    "s-kpi", "s-kpi-label", "s-kpi-value",
    # Insight Grid
    "insight-grid", "insight-card", "badge", "metric-row",
    "metric-item", "metric-label", "metric-value",
    # Risk Section
    "risk-section", "risk-items", "risk-item", "risk-tag",
    # Highlight spans
    "hl-up", "hl-down", "hl-warn", "hl-accent",
    # node-impact modifiers
    "up", "down", "flat",
    # session-block modifiers
    "asia", "europe", "us",
    # risk-tag modifiers
    "high", "med", "low",
    # metric-value modifiers (same as node-impact)
    # CS Story classes
    "cs-hero", "cs-text", "cs-section", "cs-subtitle", "cs-footer",
    # PM Story classes
    "pm-hero", "pm-tl", "pm-subtitle", "pm-grid", "pm-section",
    "pm-num", "pm-up", "pm-dn", "pm-note", "pm-footer",
    # PM Outlook classes
    "outlook-divider", "outlook-section-title", "outlook-position",
    "scenario-grid", "scenario-card", "bull", "base", "bear",
    "scen-prob", "scen-trigger", "scen-impact", "quarterly-themes",
    # Sources tab classes
    "sources-header", "sources-sub", "sources-section", "sources-list",
    "source-meta",
    # General layout (허용 — generate.py 생성 HTML의 기본 클래스)
    "tab-panel", "tab-content", "tab-nav", "tab-btn",
    "card", "metric", "kpi",
}

# story 섹션 블록 추출용 패턴
STORY_BLOCK_PATTERN = re.compile(
    r'id=["\']tab-story["\'].*?(?=</div><!--\s*/tab-story|$)',
    re.DOTALL,
)

# class 속성에서 클래스명 추출
CLASS_ATTR_PATTERN = re.compile(r'class=["\']([^"\']+)["\']')


def is_weekly_or_monthly(file_path: str) -> bool:
    return "/weekly/" in file_path or "/monthly/" in file_path


def needs_section_check(file_path: str) -> bool:
    """필수 섹션 체크 대상: 메인 일간 HTML + _story.html만.
    _pm.html / _cs.html / _sources.html / _macro.html 은 구조가 다르므로 제외."""
    name = file_path.rsplit("/", 1)[-1]
    return name.endswith("_story.html") or (
        name.endswith(".html")
        and not any(name.endswith(sfx) for sfx in (
            "_pm.html", "_cs.html", "_sources.html", "_macro.html"
        ))
    )


def check_required_sections(html: str, file_path: str) -> list[str]:
    """Returns list of missing section names."""
    if not needs_section_check(file_path):
        return []
    skip = WEEKLY_MONTHLY_SKIP if is_weekly_or_monthly(file_path) else set()
    missing = []
    for name, marker in REQUIRED_SECTIONS:
        if name in skip:
            continue
        if marker not in html:
            missing.append(name)
    return missing


def check_undefined_classes(html: str) -> list[str]:
    """Returns sorted list of CSS classes used in story block but not in whitelist."""
    # story 블록만 검사 (dashboard/CSS 정의 영역 제외)
    m = STORY_BLOCK_PATTERN.search(html)
    story_block = m.group(0) if m else html  # 블록 못 찾으면 전체 검사

    used: set[str] = set()
    for match in CLASS_ATTR_PATTERN.finditer(story_block):
        for cls in match.group(1).split():
            used.add(cls)

    undefined = sorted(used - CSS_WHITELIST)
    # 숫자·단일문자·콜론포함·특수문자 포함 클래스는 프레임워크 유틸이므로 무시
    undefined = [
        c for c in undefined
        if re.match(r'^[a-z][a-z0-9_-]{1,}$', c)
    ]
    return undefined


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        print('{"decision":"allow"}')
        return

    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path", "") or ""

    if not is_story_file(file_path):
        print('{"decision":"allow"}')
        return

    # 편집된 내용 가져오기 (Write: content, Edit: new_string)
    content = tool_input.get("content") or tool_input.get("new_string") or ""

    # Edit의 경우 변경 후 전체 파일을 읽어야 정확하지만,
    # new_string만으로도 클래스 검증은 가능. 섹션 검증은 파일 전체 필요.
    try:
        with open(file_path, encoding="utf-8") as f:
            full_html = f.read()
    except OSError:
        # 파일을 못 읽으면 content만으로 검사
        full_html = content

    reasons = []

    # 1. 필수 섹션 검증 (Write로 새로 쓴 경우만 — 전체 파일 기준)
    # Edit의 경우 기존 파일에 부분 수정이므로 전체 파일 기준으로 검사
    if content:  # 내용이 있는 작업만
        missing = check_required_sections(full_html, file_path)
        if missing:
            reasons.append(f"필수 섹션 누락: {', '.join(missing)}")

    # 2. CSS 화이트리스트 검증
    undefined = check_undefined_classes(content or full_html)
    if undefined:
        reasons.append(f"정의되지 않은 CSS 클래스: {', '.join(undefined)}")

    if reasons:
        reason_text = " | ".join(reasons)
        out = {"decision": "block", "reason": f"[구조 검증 실패] {reason_text}. SKILL.md의 CSS 화이트리스트와 필수 섹션 체크리스트를 확인하세요."}
        print(json.dumps(out, ensure_ascii=False))
    else:
        print('{"decision":"allow"}')


if __name__ == "__main__":
    main()
