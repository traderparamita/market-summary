---
allowed-tools: Read, Edit, Write, Bash(.venv/bin/python:*), Bash(grep:*), Bash(ls:*), Bash(mkdir:*), WebSearch, WebFetch, mcp__tavily__*
argument-hint: "[YYYY-MM-DD]  (생략 시 오늘 — 보통 금요일 발행)"
description: "Weekly PM Brief: 그 주 월~목 4영업일 누적 + Today Residual + W+1 Outlook 매니저 브리프 작성 후 HTML + PDF 2종 생성"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 weekly-pm 산출물: !`ls -t output/weekly-pm/*.html 2>/dev/null | head -3`
- 데이터 최신일: !`.venv/bin/python -c "from market_source import load_long; print(load_long()['DATE'].astype(str).max())" 2>/dev/null | tail -1`

---

## Your task

**Arguments**: $ARGUMENTS (형식: `YYYY-MM-DD`, 생략 시 오늘 — 보통 금요일 오전 발행)

Load and follow `.claude/skills/weekly-pm/SKILL.md` 의 작성 절차 5 단계.

PM Story 본문 톤·6 섹션 구조는 `.claude/skills/market-summary/references/pm.md` + forward Outlook 블록은 `.claude/skills/market-summary/references/pm-outlook.md` 를 그대로 적용 (공통 규칙은 `.claude/skills/market-summary/SKILL.md`).

---

## 사전 점검 (생략 금지)

1. **발행일 결정**: 인자 없으면 오늘. 미래 날짜면 즉시 중단.
2. **영업일 검증**:
   ```bash
   .venv/bin/python scripts/calendar_check.py {date} --week W{NN}
   ```
   그 주 월~목에 한국 공휴일 끼어있는지 (예: 어린이날 5/5) 확인 — 자동 제외됨.
3. **데이터 최신성**: `market_source.load_long()` 의 latest DATE 가 D-1(목) 이상이어야 함.
   - 미만이면 `auto_market.py` 또는 `collect_market.py` 먼저 실행 후 재시도.
4. **이전 회차 보존**: `output/weekly-pm/{date}.html` 이 이미 있으면 PM 탭은 자동 보존됨 (덮어쓰기 X).

---

## 5 단계 절차 요약

| Step | 작업 | 명령 |
|------|------|------|
| 1 | 사전 점검 | calendar_check + load_long |
| 2 | HTML skeleton | `.venv/bin/python generate_weekly_pm.py {date}` |
| 3 | PM 6 섹션 + Outlook 작성 | Read `_data` + 웹 검색 → 본문 작성 |
| 4 | HTML 주입 + sibling 동기화 | Edit + `save_story_files()` |
| 5 | PDF 2종 생성 | `html_to_pdf.py {html}` + `--exclude data` |

상세 절차·검증·CSS 클래스 화이트리스트는 SKILL.md 참고.

---

## 완료 보고

```
✅ Weekly PM Brief — {date} ({weekday})
   윈도우: {first} ~ {last} ({n}영업일)
   회고 6 섹션 / Outlook 5 블록 / 수치 {N}건

📄 산출물:
   - output/weekly-pm/{date}.html
   - output/weekly-pm/{date}_pm.html
   - output/weekly-pm/{date}.pdf          ({p_full}p)
   - output/weekly-pm/{date}_no-data.pdf  ({p_brief}p)
```

---

## 중단 규칙

- 발행일 > 오늘 → 즉시 중단
- 데이터 최신일 < D-1 → 사용자에게 "수집 먼저" 안내
- 주입 후 placeholder 잔존 → 재작성
- 6 섹션 중 누락 → 재작성
- PDF 페이지 비정상 (with-data > 18p / < 6p, no-data > 8p / < 3p) → 콘텐츠 점검
