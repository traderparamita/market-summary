---
allowed-tools: Bash(.venv/bin/python:*), Bash(ls:*), Read
argument-hint: "[YYYY-MM-DD]  (생략 시 전 영업일)"
description: "market_summary 일간 데이터 수집 + Data Dashboard 생성 (generate.py → collect_market.py 실행)"
---

## Context

- 현재 날짜: !`date +%Y-%m-%d`
- 최근 생성된 보고서: !`ls -t /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/output/summary/2026-*/2026-*-*.html 2>/dev/null | head -5`
- history CSV 마지막 날짜: !`tail -5 /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary/history/market_data.csv 2>/dev/null | cut -d',' -f1 | sort -u`

## Your task

`market_summary` 프로젝트의 **일간 데이터 수집 + Data Dashboard 생성**을 실행한다.

### 실행

아래 명령 **하나만** 실행한다. 데이터 수집과 HTML 생성이 모두 이 안에서 처리된다.

인자로 받은 날짜($ARGUMENTS)가 있으면:

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python generate.py $ARGUMENTS
```

**인자가 없으면** 날짜 없이 실행 (전 영업일 자동 선택):

```bash
cd /Users/lifesailor/Desktop/kosmos/ai/investment/market_summary && .venv/bin/python generate.py
```

**내부 동작 (참고용 — 별도로 실행하지 않는다)**:
- `generate.py`가 `collect_market.py`의 `fetch_data()` / `build_report_data()`를 import해서 호출 → CSV 수집
- 이어서 HTML 생성 + `update_current_periodic()`으로 주간·월간 HTML도 자동 갱신

### 주의

- **미래 날짜는 절대 생성 금지**. 오늘 날짜보다 미래면 실행하지 말고 사용자에게 확인 요청.
- 이 커맨드는 **데이터 수집 + HTML 대시보드**까지만 수행한다. Market Story 작성은 포함되지 않는다.
- **`collect_market.py`를 별도로 실행하지 않는다.** `generate.py` 하나로 충분하다.
- 실행 후 출력 경로와 성공 여부를 한 줄로 보고. 긴 로그는 요약만.

### 실패 시

- yfinance/investiny 데이터 소스 일시 장애 → 오류 로그 확인 후 재시도 제안
- 이미 존재하는 보고서의 Story 탭은 `_inject_existing_story()`가 자동 보존한다 (덮어쓰기 걱정 X)