---
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Bash(git push:*), Bash(cd:*)
description: "market_summary 보고서 git commit + push → GitHub Pages 자동 배포"
---

## Context

- 작업 디렉토리: /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary
- 현재 git status: !`cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && git status --short`
- 현재 브랜치: !`cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && git branch --show-current`
- 최근 커밋 5개: !`cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && git log --oneline -5`
- output/ 변경분: !`cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && git status --short output/ history/`

## Your task

`market_summary` 보고서 변경분을 git commit + push하여 GitHub Pages에 자동 배포한다.

### 사전 안전 가드 (experiment/tavily-story 브랜치 필독)

**이 커맨드는 `main` 브랜치에서만 실행한다.** 실험 브랜치(`experiment/tavily-story` 등)에서는 즉시 중단하고 사용자에게 "현재 브랜치는 실험용이므로 배포하지 않는다"라고 보고할 것.

```bash
git branch --show-current
```

위 결과가 `main`이 아니면 **이후 단계를 진행하지 않는다**. 실험 브랜치의 워크트리는 `/Users/lifesailor/Desktop/kosmos/ai/investment/market_summary_tavily`이고, 실험 결과는 `experiments/tavily_log.md`에만 기록할 것.

### 절차

1. 위 context의 변경분 확인. 변경이 없으면 "배포할 변경사항 없음"만 보고하고 종료.
2. 변경 파일이 어떤 날짜·기간의 보고서인지 파악 (일간/주간/월간, 날짜 범위).
3. `output/`, `history/market_data.csv` 경로의 변경분만 `git add`. **`_data.json`은 `.gitignore`로 자동 제외됨.**
4. 커밋 메시지 작성 규칙:
   - 형식: `market: YYYY-MM-DD daily report` 또는 `market: YYYY-WNN weekly report` 또는 `market: YYYY-MM monthly report`
   - 여러 보고서 동시 배포 시: `market: update reports (YYYY-MM-DD ~ YYYY-MM-DD)`
   - 최근 커밋 스타일을 따라가되, 차이가 크면 기존 스타일 우선
5. commit 후 `git push origin main` (또는 현재 브랜치).
6. push 완료 후 git status 다시 확인해서 깨끗한지 보고.

### 주의

- **`.gitignore`에 포함된 파일을 강제로 추가하지 않는다** (`_data.json`, `data/` 등)
- **force push 절대 금지**
- pre-commit hook 실패 시: `--no-verify` 사용 금지. 원인 수정 후 재커밋.
- push 전 `git diff --cached` 한 번 확인해서 의도하지 않은 파일이 섞이지 않았는지 점검
- main이 아닌 브랜치면 사용자에게 브랜치 확인 후 진행