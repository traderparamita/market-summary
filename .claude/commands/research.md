---
allowed-tools: Bash(.venv/bin/python:*), Bash(git:*), Bash(ls:*), Bash(grep:*), Bash(tail:*), Bash(find:*), Read, Edit, Write, WebSearch, WebFetch, mcp__tavily__search
argument-hint: "[YYYY-MM-DD]  (날짜 생략 시 전 영업일)"
description: "주간 테마 리서치: Naver 지속성 + 미래에셋 증권 보고서 + Tavily 검색을 교차해 핵심 테마 1~2개 선정, 펀드·보고서 매칭까지 포함한 심층 리서치 작성"
---

## Context

- 오늘 날짜: !`date +%Y-%m-%d`
- 최근 증권 다이제스트: !`ls -t output/securities/digest/digest_*.html 2>/dev/null | head -3`
- 최근 리서치 보고서: !`ls -t output/research/daily/**/*.html 2>/dev/null | head -3`
- 펀드 인덱스: `output/fund/index.html`

---

## Your task

매주 일요일, **Naver 테마 지속성 × 미래에셋 증권 주간 보고서 × Tavily 뉴스**를 교차 분석해
**핵심 테마 1~2개**를 선정하고, 각 테마에 투자 가능한 **펀드·ETF 및 관련 증권 보고서**까지 매칭한 심층 리서치 보고서를 작성한다.

**Arguments**: $ARGUMENTS (형식: `YYYY-MM-DD`)

---

## 사전 점검

1. **날짜 결정**: 날짜 인자 없음 → 전 영업일 자동 선택.
2. **미래 날짜 금지**: 대상 날짜 > 오늘이면 즉시 중단.

---

## Step 0 — Telegram 시작 알림

```bash
.venv/bin/python notify_telegram.py {date} --start --label "테마 리서치"
```

---

## Step 0.5 — Naver 테마 지속성 계산

`C:\Users\user\Desktop\kosmos\crescent\screener\data\v2\theme_history.json`을 읽어
대상 날짜 기준 **직전 7거래일** 지속성을 계산한다.

```python
import json
from collections import defaultdict

path = r"C:\Users\user\Desktop\kosmos\crescent\screener\data\v2\theme_history.json"
with open(path, encoding="utf-8") as f:
    history = json.load(f)

# 대상 날짜 직전 7거래일
dates = sorted(d for d in history if d <= "{date}")[-7:]

scores = defaultdict(lambda: {"positive_days": 0, "total_days": 0, "returns": []})
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
        avg = sum(s["returns"]) / len(s["returns"])
        results.append({"theme": theme, "persistence": round(persistence), "avg": round(avg, 2)})

top = sorted(results, key=lambda x: (x["persistence"], x["avg"]), reverse=True)[:15]
for t in top:
    print(f"{t['theme']}: 지속성 {t['persistence']}%, 평균 {t['avg']}%")
```

결과를 `_naver_top15` 목록으로 메모한다.

---

## Step 0.7 — 당일 시장 지수 실제값 로드 (할루시네이션 방지)

보고서 본문의 **지수·등락률은 반드시 CSV ground truth에서 읽은 수치만 사용**한다. 수치를 추측·창작하지 않는다.

```python
import pandas as pd

df = pd.read_csv('history/market_data.csv')
target = "{date}"

# 직전 거래일 자동 탐색
prev_dates = sorted(df[df['DATE'] < target]['DATE'].unique())
if not prev_dates:
    print("이전 날짜 없음 — 지수 수치 생략")
else:
    prev_day = prev_dates[-1]
    for ticker in ['KOSPI', 'KOSDAQ', 'S&P500', 'NASDAQ', 'NIKKEI225']:
        curr = df[(df['DATE'] == target) & (df['TICKER'] == ticker)]['CLOSE'].values
        prev = df[(df['DATE'] == prev_day) & (df['TICKER'] == ticker)]['CLOSE'].values
        if len(curr) and len(prev) and prev[0]:
            chg = (curr[0] - prev[0]) / prev[0] * 100
            print(f"{ticker}: {curr[0]:,.2f} ({'+'if chg>=0 else ''}{chg:.2f}%)")
        else:
            print(f"{ticker}: 데이터 없음 — 본문에서 생략")
```

출력된 수치를 `_market_indices` 로 메모한다.

> **규칙**: CSV에 없는 날짜·티커는 본문에서 해당 지수 수치를 **완전히 생략**한다. "약 N%" 같은 추정 표현도 금지.

---

## Step 1 — 미래에셋 증권 주간 다이제스트 읽기

`collect_weekly.py`가 매주 일요일 19:30에 자동 생성한 다이제스트를 읽는다.
(`/research`는 `collect_weekly.py` 완료 후인 20:00 이후에 실행할 것)

```bash
ls output/securities/digest/digest_*.html | sort | tail -3
```

파일이 없으면 → 사용자에게 보고 후 중단.
(`collect_weekly.py`가 아직 미실행이므로 19:30 이후 재시도 요청)

파일이 있으면 → 가장 최근 `digest_YYYY-WNN.html`을 읽어 다음을 추출한다:
- 이번 주 애널리스트가 가장 많이 다룬 **섹터·테마·종목**
- **Buy/Overweight 의견**이 집중된 섹터
- **목표주가 상향** 종목이 많은 섹터

→ 이것을 `_securities_signals` 목록으로 메모한다.

---

## Step 2 — Tavily 퀵 검색 (글로벌 트리거 탐색)

`_naver_top15` 중 지속성 ≥ 60%인 테마를 대상으로, 테마당 **1~2회** 검색해 글로벌 트리거를 찾는다.

검색 목적: "이 테마가 왜 이번 주에 올랐는가?" — 뉴스 촉매 확인.

예시 검색:
- `"{테마명} 관련주 급등 이유 최근"`
- `"한국 {테마명} 테마 글로벌 이슈"`

→ 글로벌 트리거가 확인된 테마를 `_triggered` 목록으로 메모한다.

---

## Step 3 — 테마 선정

3가지 신호를 교차해 **테마 1~2개**를 최종 선정한다.

| 신호 조합 | 판정 | 처리 |
|-----------|------|------|
| Naver ≥ 60% + 증권 보고서 언급 + Tavily 트리거 확인 | ✅ 1순위 | 메인 테마 선정 |
| Naver ≥ 70% + Tavily 트리거 확인 (보고서 미언급) | ⚡ 2순위 | "시장이 먼저 움직인 테마" |
| Naver ≥ 60% + 보고서 언급 (Tavily 트리거 불명확) | 📋 3순위 | 보조 테마 또는 다음 주 후보 |

선정 후 근거를 한 줄로 명시:
> 예) "방산·조선 — Naver 86%/avg+2.1%, 미래에셋 4건 언급, 트리거: 중동 확전 우려"

---

## Step 4 — 선정 테마 Tavily 심층 검색

선정된 테마마다 **3~5회** 검색. 최근 1~2주 뉴스 중심.

검색 전략:
1. 테마 핵심 드라이버 (정책·수요·공급 변화)
2. 대표 기업·ETF 동향 및 실적
3. 반론·리스크 요인
4. 글로벌 → 한국 시장 파급 경로

---

## Step 5 — 펀드 & 보고서 매칭

### 5-A. 관련 펀드·ETF 매칭

`output/fund/index.html`을 읽어 선정된 테마와 관련된 펀드·ETF를 추출한다.

- 테마 키워드로 펀드명·운용사·투자 전략 텍스트 검색
- 매칭된 펀드 최대 5개 목록 작성 (펀드명, 운용사, 전략 한 줄 요약)
- 매칭 결과가 없으면 해당 섹션 생략

### 5-B. 관련 증권 보고서 매칭

```bash
grep -rl "{테마 키워드}" output/securities/digest/ | head -5
```

매칭된 보고서 파일명과 제목을 목록으로 정리한다.

---

## Step 6 — 보고서 파일 생성

경로: `output/research/daily/{YYYY-MM}/{date}.html`

### HTML 골격

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Market Research | {date}</title>
<style>
@import url('https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/css/SpoqaHanSansNeo.css');
:root { --accent:#F58220; --accent2:#043B72; --border:#e0e3ed; --muted:#7c8298; }
body { font-family:'Spoqa Han Sans Neo',sans-serif; background:#f4f5f9; color:#2d3148; max-width:900px; margin:0 auto; padding:32px 24px; line-height:1.7; }
.header { border-bottom:2px solid var(--border); padding-bottom:16px; margin-bottom:28px; }
.header h1 { font-size:22px; font-weight:700; color:#1a1d2e; }
.header .meta { font-size:12px; color:var(--muted); margin-top:4px; }
.signal-bar { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:24px; }
.signal-chip { font-size:11px; font-weight:600; padding:4px 12px; border-radius:20px; }
.chip-naver { background:#fff5eb; border:1px solid #fde0c0; color:var(--accent); }
.chip-report { background:#f0f7ff; border:1px solid #bfdbfe; color:#1d4ed8; }
.chip-tavily { background:#f0fdf4; border:1px solid #bbf7d0; color:#15803d; }
.theme-badge { display:inline-block; font-size:11px; font-weight:600; color:var(--accent); background:#fff5eb; border:1px solid #fde0c0; border-radius:12px; padding:3px 12px; margin-bottom:20px; }
.section { background:#fff; border:1px solid var(--border); border-radius:12px; padding:24px 28px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,0.04); }
.section h2 { font-size:18px; font-weight:700; color:var(--accent2); margin-bottom:14px; padding-bottom:8px; border-bottom:1px solid var(--border); }
.section h3 { font-size:15px; font-weight:600; color:#1a1d2e; margin:14px 0 8px; }
.section p { font-size:14px; margin-bottom:10px; }
.fund-list { list-style:none; padding:0; margin:10px 0; }
.fund-list li { font-size:13px; padding:8px 12px; border:1px solid var(--border); border-radius:6px; margin-bottom:6px; background:#f8f9fc; }
.fund-list li strong { color:#1a1d2e; }
.report-list { list-style:none; padding:0; margin:10px 0; }
.report-list li { font-size:13px; padding:6px 12px; border-left:3px solid var(--accent2); margin-bottom:4px; background:#f8f9fc; }
.advisor-box { background:#f0f7ff; border:1px solid #bfdbfe; border-radius:8px; padding:14px 18px; margin-top:14px; font-size:13px; }
.risk-box { background:#fff5f5; border:1px solid #fecaca; border-radius:8px; padding:14px 18px; margin-top:14px; font-size:13px; }
.signal-table { width:100%; border-collapse:collapse; font-size:13px; margin:12px 0; }
.signal-table th { background:#f4f5f9; padding:8px 12px; text-align:left; font-weight:600; border-bottom:2px solid var(--border); }
.signal-table td { padding:8px 12px; border-bottom:1px solid var(--border); }
.footer { font-size:11px; color:var(--muted); border-top:1px solid var(--border); padding-top:12px; margin-top:24px; }
</style>
</head>
<body>

<div class="header">
  <h1>Weekly Theme Research</h1>
  <div class="meta">{date} · {W##} · 테마: {테마명}</div>
</div>

<!-- STORY_PLACEHOLDER -->

<div class="footer">출처: Naver Finance 테마 지속성 · 미래에셋증권 주간 보고서 · Tavily 뉴스 검색 · {date}</div>
</body>
</html>
```

---

## Step 7 — Story 작성 및 주입

**수치 사용 규칙 (필수)**:
- 지수 등락률(KOSPI, KOSDAQ, S&P500 등)은 **Step 0.7의 `_market_indices` 수치만** 사용한다.
- `_market_indices`에 없는 지수는 수치 없이 방향(상승/하락/보합)으로만 서술하거나 생략한다.
- "약 N%", "N% 내외" 같은 추정 표현 금지. 수치가 없으면 쓰지 않는다.

`STORY_PLACEHOLDER`를 아래 구조의 HTML로 교체한다.

```html
<!-- 신호 요약 바 -->
<div class="signal-bar">
  <span class="signal-chip chip-naver">Naver {테마}: {지속성}%/avg {avg}%</span>
  <span class="signal-chip chip-report">증권 보고서 {N}건</span>
  <span class="signal-chip chip-tavily">트리거: {글로벌 촉매 한 단어}</span>
</div>

<span class="theme-badge">테마 1 — {테마명}</span>

<div class="section">
  <h2>🎯 {테마1 제목}</h2>

  <h3>배경 — 왜 지금 이 테마인가</h3>
  <p>{Naver 지속성 + Tavily 트리거 + 증권 보고서 키워드를 엮은 배경 2~3 문단}</p>

  <h3>핵심 드라이버</h3>
  <p>{정책·수요·기술 등 구체적 드라이버 2~3 문단}</p>

  <h3>대표 기업·ETF 동향</h3>
  <p>{이번 주 실제 움직임 + 실적·뉴스 2~3 문단}</p>

  <h3>한국 시장 파급</h3>
  <p>{국내 관련 섹터·기업 동향 1~2 문단}</p>

  <h3>📦 투자 가능 펀드·ETF</h3>
  <ul class="fund-list">
    <li><strong>{펀드명}</strong> — {운용사} · {전략 한 줄}</li>
    <!-- 매칭된 펀드 최대 5개 -->
  </ul>

  <h3>📄 관련 증권 보고서</h3>
  <ul class="report-list">
    <li>{보고서 제목} — {날짜}</li>
    <!-- 매칭된 보고서 최대 3개 -->
  </ul>

  <div class="advisor-box">
    💬 <strong>상담사 한 줄 설명</strong>: "{글로벌 트리거 한 문장}. 한국 시장에서는 {테마명} 섹터 수급으로 연결되고 있으며, 투자는 {대표 펀드/ETF} 통해 접근 가능합니다."
  </div>

  <div class="risk-box">
    ⚠ 리스크: {이 테마의 반전 시나리오 1~2 문장}
  </div>
</div>

<!-- 테마 2 (있는 경우) — 동일 구조 반복 -->

<!-- 종합 포인트 -->
<div class="section">
  <h2>💡 이번 주 핵심 포인트</h2>
  <p>① <strong>{테마1 한 줄 요약}</strong> — {초보자도 이해할 수 있는 1문장}</p>
  <p>② <strong>{테마2 한 줄 요약}</strong> — {설명}</p>
  <p>③ <strong>다음 주 주목 변수</strong> — {캘린더 이벤트·지표 1~2개}</p>
  <p>④ <strong>Naver 지속성 주목 신호</strong> — {선정되지 않은 상위 테마 1개 + 다음 주 관찰 포인트}</p>
</div>

<!-- 테마 선정 근거 테이블 -->
<div class="section" style="background:#f8f9fc;">
  <h2>📋 테마 선정 근거</h2>
  <table class="signal-table">
    <thead>
      <tr><th>테마</th><th>Naver 지속성</th><th>증권 보고서</th><th>Tavily 트리거</th><th>판정</th></tr>
    </thead>
    <tbody>
      <tr><td>{테마1}</td><td>{지속성}%/avg {avg}%</td><td>{N}건</td><td>{트리거}</td><td>✅ 1순위</td></tr>
      <tr><td>{테마2}</td><td>...</td><td>...</td><td>...</td><td>✅ 1순위</td></tr>
    </tbody>
  </table>
</div>
```

---

## Step 8 — `_story.html` 저장

```bash
cp output/research/daily/{YYYY-MM}/{date}.html \
   output/research/daily/{YYYY-MM}/{date}_story.html
```

---

## Step 9 — Git commit + push

```bash
git add output/research/ && \
git commit -m "feat: {date} 테마 리서치 — {테마명}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" && \
git push origin main
```

---

## Step 10 — Telegram 완료 알림

```bash
.venv/bin/python notify_telegram.py {date} --sc-complete \
  --focus "테마 리서치 — {테마명}"
```

---

## 완료 보고

- 생성된 HTML 경로
- 선정 테마 (1~2개) + 3가지 신호 요약
  - 예) "방산·조선 — Naver 86%/avg+2.1%, 미래에셋 4건, 트리거: 중동 확전"
- 매칭된 펀드 수 + 보고서 수
- Tavily 검색 건수

---

## 중단 규칙

- 증권 다이제스트 없음: 사용자에게 보고 후 중단 (`collect_weekly.py`가 19:30에 실행되므로 이후 재시도 요청)
- Step 9 git 실패: 즉시 중단 후 사용자에게 상태 보고