#!/usr/bin/env python3
"""PreToolUse hook for Edit|Write.

Deterministic path gate: only market story files get temporal-rule context
injection. All other files short-circuit to {"decision":"allow"} with no LLM
involvement. Replaces the former type:prompt hook that asked an LLM to make
path judgements (which caused prose-return failures on non-story edits).
"""
import json
import sys


def is_story_file(file_path: str) -> bool:
    return (
        ("/output/" in file_path and file_path.endswith(".html"))
        or file_path.endswith("generate_stories.py")
        or file_path.endswith("inject_stories.py")
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        print('{"decision":"allow"}')
        return

    file_path = (data.get("tool_input") or {}).get("file_path", "") or ""

    if not is_story_file(file_path):
        print('{"decision":"allow"}')
        return

    ctx = (
        "[TEMPORAL RULES - 반드시 준수] 지금 작성하려는 Market Story에 다음 시간 규칙을 적용하세요:\n\n"
        "1. 세션별 마감 시각 (KST 기준):\n"
        "   - 아시아: KOSPI 15:30, 닛케이 15:00, 상하이 16:00\n"
        "   - 유럽: STOXX/DAX/CAC 01:30 (서머타임 00:30)\n"
        "   - 미국: S&P/나스닥 06:00 (서머타임 05:00)\n\n"
        "2. 각 세션 서술 시 해당 세션 마감 이후 이벤트를 원인/맥락으로 절대 사용 금지:\n"
        "   - 아시아 서술: 유럽/미국 세션 이벤트 참조 금지\n"
        "   - 유럽 서술: 미국 세션 이벤트 참조 금지 (유럽 마감 후 발생한 미국 장중 이벤트 포함)\n"
        "   - 미국 서술: 아시아/유럽 참조 가능 (시간순 OK)\n\n"
        "3. 인과관계 방향: 항상 과거 → 현재. '~의 서막이었다', '~의 시작에 불과했다' 같은 사후적 표현 금지\n\n"
        "4. 주간/월간: 특정 날짜 설명 시 그 날짜 이후 이벤트를 원인으로 사용 금지\n\n"
        "작성 전에 각 문장의 인과관계가 시간순인지 스스로 확인하세요."
    )

    out = {
        "decision": "allow",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": ctx,
        },
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
