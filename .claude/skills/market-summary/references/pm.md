# PM Story 작성 절차

PM(Portfolio Manager) Story 는 **포트폴리오 매니저·운용역을 위한 지역·자산군별 브리프**. 일반 Market Story 가 시간순 내러티브라면 PM Story 는 **지역·자산 컷으로 재편집한 "오늘의 요지"**로, 수치를 적극적으로 포함해 의사결정 참고용으로 쓴다.

**공통 규칙(존댓말·forward-looking·세션 시각·인과방향·요일·고점 검증·표기)은 `SKILL.md` 본문 참조.** 주간/월간/분기 PM 의 forward-looking Outlook 블록은 `references/pm-outlook.md`.

---

## 전제

- **선행 조건**: 해당 날짜의 일반 Story(`_story.html`) + `_data.json` 존재. CS Story 는 필수 아님 (독립 작성).
- **대상 탭**: `<div id="tab-pm">` / placeholder `<!-- PM_STORY_PLACEHOLDER -->`
- **별도 파일 저장**: `YYYY-MM-DD_pm.html` (generate.py 가 sibling 으로 자동 저장)
- **적용 범위**: 일간·주간·월간 모두 동일 패턴
- **tab-pm 블록이 없는 이전 보고서**: `.venv/bin/python generate.py {date}` 로 먼저 탭 구조 최신화

## Step 1: 원본 Story + Data 읽기

1. `YYYY-MM-DD_story.html` — 사실관계·이벤트·인과 확인 (원본과 모순 금지)
2. `YYYY-MM-DD_data.json` — 각 자산 daily/weekly/monthly/ytd 수치 + holiday 확인
3. `history/market_data.csv` (필요 시) — 크레딧 스프레드·채권 ETF 실제 종가·YTD 범위 검증

## Step 2: 6개 섹션 구성

PM Story 는 **고정된 6개 섹션** 으로 구성된다 (순서·제목 변경 금지):

| 순서 | 섹션 | 제목 | 다루는 자산/지표 |
|------|------|------|------------------|
| 1 | 🇰🇷 한국 | **한국** | KOSPI, KOSDAQ, 주도주(삼성전자·SK하이닉스 등), USD/KRW, KR 금리, 외국인 수급 |
| 2 | 🌐 매크로 | **매크로** | Fed/한은/ECB 통화정책, US/KR 경제지표(GDP/CPI/고용), 원자재(WTI/Gold), DXY |
| 3 | 🌏 아시아 및 중국 | **아시아 및 중국** | Nikkei, Shanghai, HSI, NIFTY, 일본·중국 경제지표·정책, 인접 아시아 통화 |
| 4 | 🇺🇸 미국 | **미국** | S&P500, NASDAQ, Russell2K, 빅테크 실적·주가, VIX, 정책·Fed 관련 시장 반응 |
| 5 | 🇪🇺 유럽 | **유럽** | STOXX50, DAX, CAC40, FTSE100, ECB·BOE, EUR/USD·GBP/USD, 유럽 주요 테마 |
| 6 | 💵 채권 | **채권** | US 2Y/10Y/30Y, KR CD91D/3Y/10Y, Yield Curve, IG/HY 스프레드, TLT/AGG/HYG/LQD/EMB |

각 섹션은 **3~5개 불릿** 또는 짧은 문단으로 구성. 수치는 적극적으로 포함한다.

## Step 3: 작성 원칙

**포함 권장**:
- 종가 + 일변동률 (`KOSPI 6,417.93 (+0.46%)`)
- 주간/월간/YTD 누적 (`WTD +2.5%, MTD +3.2%, YTD +8.1%`)
- 스프레드·커브 (`10Y-2Y +48bp`, `IG spread 98bp`)
- FX 절대 레벨 + 변동 (`USD/KRW 1,392 (+0.3%)`)
- 주도주별 등락률 top 1~2개
- 수급·거래대금·외국인 순매수 (가능한 경우)

**피해야 할 것**:
- 의사결정 권유 금지 (`매수 권장`, `비중 확대 권장` 같은 직접 권유 — "OW/UW 관점에서 ~"는 허용)
- 미래 이벤트 참조 (Forward-looking 금지 — Market Story 와 동일 규칙)
- 세션 간 시간 역전 참조
- 원본 Story 에 없는 사실 창작

**톤**:
- 건조한 브리프 톤 (헤드라인 + 수치 + 한 줄 해석)
- "~에 반응", "~로 마감", "~로 상승" 같은 관찰 동사 위주
- 분석은 `스프레드 축소 국면 지속`, `금리 상승 압력` 수준의 짧은 레이블 허용

## Step 4: HTML 골격

PM 스타일은 **차가운 블루/네이비 계열** (CS 의 오렌지와 시각적으로 분리). CSS 는 tab-pm 블록에 인라인 포함해 과거 보고서에도 포터블 적용.

```html
<style>
  .pm-hero{background:linear-gradient(135deg,#eef4fb,#dde9f6);border:1px solid var(--border);border-left:4px solid #043B72;border-radius:12px;padding:24px 28px;margin-bottom:20px}
  .pm-hero h2{font-size:13px;color:#043B72;letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
  .pm-hero .pm-subtitle{font-size:12px;color:var(--muted);margin-bottom:14px}
  .pm-tl{font-size:15px;color:#1a1d2e;line-height:1.8}
  .pm-tl p{margin-bottom:8px}
  .pm-tl p:last-child{margin-bottom:0}
  .pm-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-bottom:16px}
  @media (max-width:800px){.pm-grid{grid-template-columns:1fr}}
  .pm-section{background:var(--card);border:1px solid var(--border);border-left:3px solid #043B72;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}
  .pm-section h3{font-size:15px;font-weight:700;color:#043B72;margin-bottom:10px;display:flex;align-items:center;gap:8px}
  .pm-section ul{list-style:none;padding:0;margin:0}
  .pm-section li{font-size:13.5px;color:#2d3148;line-height:1.75;margin-bottom:6px;padding-left:12px;position:relative}
  .pm-section li::before{content:'·';position:absolute;left:0;color:#043B72;font-weight:700}
  .pm-section li:last-child{margin-bottom:0}
  .pm-section .pm-num{font-weight:600;color:#1a1d2e}
  .pm-section .pm-up{color:#d92b2b;font-weight:600}
  .pm-section .pm-dn{color:#1a5fb4;font-weight:600}
  .pm-section .pm-note{font-size:12px;color:var(--muted);margin-top:8px;padding-top:8px;border-top:1px dashed var(--border)}
  .pm-footer{font-size:12px;color:var(--muted);border-top:1px solid var(--border);padding-top:10px;margin-top:12px;text-align:center}
</style>

<div class="pm-hero">
  <h2>PM Story — 포트폴리오 매니저 브리프</h2>
  <div class="pm-subtitle">{date} ({요일}) · 지역·자산군별 요지 + 핵심 수치</div>
  <div class="pm-tl">
    <p><strong>Top-line:</strong> {하루를 한 문장으로 + 핵심 수치 2~3개}</p>
    <p><strong>Key drivers:</strong> {시장을 움직인 원인 — 세미콜론 구분 1~2개}</p>
    <p><strong>Watch:</strong> {남은 모니터링 포인트 — 차주/익일 이벤트 또는 지속 관찰 지표}</p>
  </div>
</div>

<div class="pm-grid">
  <div class="pm-section">
    <h3>🇰🇷 한국</h3>
    <ul>
      <li>KOSPI <span class="pm-num">6,417.93</span> <span class="pm-up">+0.46%</span> · WTD <span class="pm-up">+2.5%</span> · YTD <span class="pm-up">+8.1%</span></li>
      <li>{주도주·수급·주요 테마 — 1~2줄}</li>
      <li>{USD/KRW, KR 금리, 외국인 순매수}</li>
    </ul>
    <div class="pm-note">{해석·코멘트 — 선택}</div>
  </div>

  <div class="pm-section">
    <h3>🌐 매크로</h3>
    <ul>
      <li>{Fed/한은/ECB 정책 or 경제지표 — 수치 포함}</li>
      <li>{원자재·DXY — WTI $XX.XX (±N%), Gold $X,XXX}</li>
      <li>{인플레이션·성장·고용 트렌드}</li>
    </ul>
  </div>

  <div class="pm-section">
    <h3>🌏 아시아 및 중국</h3>
    <ul>
      <li>Nikkei225 <span class="pm-num">XX,XXX</span> <span class="pm-up/pm-dn">±X.XX%</span>, Shanghai ..., HSI ...</li>
      <li>{일본·중국 정책·경제지표}</li>
      <li>{기타 아시아 — NIFTY, 대만 등}</li>
    </ul>
  </div>

  <div class="pm-section">
    <h3>🇺🇸 미국</h3>
    <ul>
      <li>S&amp;P500 <span class="pm-num">X,XXX.XX</span> <span class="pm-up/pm-dn">±X.XX%</span>, NASDAQ ..., Russell2K ...</li>
      <li>{빅테크 실적·주가 — NVIDIA, AAPL, MSFT 등}</li>
      <li>VIX <span class="pm-num">XX.X</span> {레짐 한 줄}</li>
    </ul>
  </div>

  <div class="pm-section">
    <h3>🇪🇺 유럽</h3>
    <ul>
      <li>STOXX50 / DAX / CAC40 / FTSE100 — 종가 + 변동률</li>
      <li>{ECB·BOE 코멘트 · 유럽 주요 테마}</li>
      <li>EUR/USD, GBP/USD — 레벨 + 변동</li>
    </ul>
  </div>

  <div class="pm-section">
    <h3>💵 채권</h3>
    <ul>
      <li>US 2Y <span class="pm-num">X.XX%</span> ({±Nbp}), US 10Y <span class="pm-num">X.XX%</span> ({±Nbp}), 10Y-2Y <span class="pm-num">±XXbp</span></li>
      <li>KR CD91D / 3Y / 10Y — 레벨 + 변동</li>
      <li>IG spread / HY spread / HYG·LQD·TLT·EMB 종가 + 변동</li>
    </ul>
    <div class="pm-note">{커브·크레딧 해석 — "불스팁/베어플랫" 류}</div>
  </div>
</div>

<div class="pm-footer">
  PM Story 는 Market Story 를 지역·자산군별로 재편집한 매니저용 브리프입니다. 상세 내러티브는 Market Story, 고객 설명은 CS Story 탭을 참고하세요.
</div>
```

**규칙**:
- `<style>` 블록은 인라인 포함 (과거 보고서에도 주입 가능하도록)
- 6개 섹션은 `<div class="pm-grid">` 안에 2열로 배치. 각 `pm-section` 은 `<h3>` + `<ul>` 필수.
- 수치는 `<span class="pm-num">` / `.pm-up` / `.pm-dn` 로 감싸 강조
- 섹션당 3~5 불릿. 과도하게 길어지면 압축.
- 해당일 휴장 섹션(예: 한국 공휴일)은 첫 불릿에 `{KOSPI 휴장 (공휴일)}` 명시 후 빈 자리 남기지 말고 FX·관련 이슈로 채움.

**색상 스팬 일관성 (반드시 준수)**:
- 같은 불릿 안의 수익률/등락률 수치는 **전부** `pm-up`/`pm-dn` 적용. 일부만 적용하는 혼용 금지.
- **bp 변화는 반드시 스팬 적용** — plain text `(약 +5bp)` 패턴 금지.
  ```html
  <!-- ✅ -->
  미국 10년물 <span class="pm-num">4.558%</span> (<span class="pm-dn">+5.2bp</span>)
  <!-- ❌ -->
  미국 10년물 4.558% (약 +5bp 상승)
  ```
- **채권 방향 컨벤션**: 금리 상승(bp+) → `pm-dn`(파란색), 금리 하락(bp−) → `pm-up`(빨간색). 주식과 반대 방향.
- 지수 줄 예시: `KOSPI <span class="pm-num">6,690</span> <span class="pm-up">+0.75%</span> · WTD <span class="pm-up">+3.1%</span>`

## Step 5: HTML 주입

1. `output/summary/YYYY-MM/YYYY-MM-DD.html` Read
2. `<div id="tab-pm" class="tab-panel">` ~ `</div><!-- /tab-pm -->` 사이 블록을 Edit 으로 새 PM 본문으로 치환
3. 같은 내용으로 `YYYY-MM-DD_pm.html` 를 Edit (동기화)
4. `_inject_existing_story()` 외부 직접 호출 금지

placeholder 만 있는 상태(`<!-- PM_STORY_PLACEHOLDER -->`): 정상. 이 블록을 PM 본문으로 치환하면 됨.
tab-pm 블록이 없는 이전 버전 HTML: `generate.py {date}` 재실행 후 재시도.

## Step 6: 주입 검증

```bash
grep -c 'id="tab-pm"\|PM_STORY_PLACEHOLDER' {html_path}
```
- `id="tab-pm"` 1개
- `PM_STORY_PLACEHOLDER` **0개**

수치 존재 확인 (CS 와 반대 — 수치 **있어야 함**):
```bash
grep -oE '[0-9]+\.[0-9]+%|[0-9]{3,}\.[0-9]{2}' {pm_file} | wc -l
```
10 건 미만이면 수치 보강 필요.

## 자가 검증 체크리스트

- [ ] 6개 섹션이 모두 있는가? (한국·매크로·아시아및중국·미국·유럽·채권)
- [ ] 각 섹션에 `<ul>` 불릿 3개 이상 있는가?
- [ ] 원본 Story 의 사실관계·시간순 규칙을 그대로 지켰는가? (forward-looking / 세션 간 참조 금지)
- [ ] 수치가 `_data.json` 값과 일치하는가? (소수점 2자리 허용 오차)
- [ ] `_pm.html` sibling 파일이 생성·갱신되었는가?
- [ ] 직접적 매수/매도 권유 표현이 없는가?
- [ ] 한국 휴장일이면 KOSPI/KOSDAQ 휴장 사실이 한국 섹션 첫 줄에 명시되었는가?

## 주간 / 월간 PM Story 적용 가이드

PM 의 6 섹션 구조(🇰🇷 한국 · 🌐 매크로 · 🌏 아시아 및 중국 · 🇺🇸 미국 · 🇪🇺 유럽 · 💵 채권)는 그대로 유지. 기간 단위에 따라 수치 스케일·맥락만 조정한다.

**주간 (해당 주 마지막 영업일 작성)**
- **pm-hero Top-line**: 한 주 흐름 1~2 문장 + 핵심 수치 2~3 개
- **pm-hero Key drivers**: 그 주의 인과 핵심 (NFP·CPI·금통위·이벤트)
- **pm-hero Watch**: 익주 또는 익월 모니터링 포인트
- **6 섹션 각 4~6 불릿**: 종가 + WTD 수익률 (전주 금요일 종가 기준) + 주중 최대 상승·하락일 + 주요 이벤트 (필요 시 MTD/YTD 보조)
- **채권 섹션**: 금리 +/− bp 변화 (주초 vs 주말), 커브 변형, 크레딧 스프레드 변화
- 본체(`weekly/YYYY-WNN.html`) + sibling(`_pm.html`) 동시 갱신

**월간 (해당 월 마지막 영업일 작성)**
- **pm-hero Top-line**: 한 달 흐름 2~3 문장 + 핵심 수치 3~4 개 (가장 큰 mover, 변동성, FX)
- **pm-hero Key drivers**: FOMC/한은/CPI/NFP/지정학 등 그 달의 큰 흐름
- **pm-hero Watch**: 익월·익분기 모니터링
- **6 섹션 각 5~7 불릿**: 월말 종가 + MTD + YTD + 월간 최대 상승·하락일 + 주차별 리듬 (W 주차로 짧게) + 주요 이벤트
- **채권 섹션**: 금리 +/− bp 변화 (월초 vs 월말), 커브 V/스팁/플랫 패턴, 크레딧 스프레드 월간 변화
- 본체(`monthly/YYYY-MM.html`) + sibling(`_pm.html`) 동시 갱신

**공통 — 주간/월간 모두**
- 일간 PM 과 동일 CSS(pm-hero, pm-grid, pm-section, pm-num, pm-up, pm-dn, pm-note, pm-footer) 재사용
- 수치 적극 포함 원칙은 동일 (검증 grep 임계값: 주간 30+, 월간 50+, 분기 80+)
- 기존 Market Story / Macro 탭과 사실관계 정합 — 수치 어긋나면 Market Story 가 정본
- 톤은 존댓말("~입니다/습니다") 또는 명사형 종결로 통일. 매수/매도 직접 권유 금지
- **주간/월간/분기 PM 본문은 [회고 6섹션] 직후 [Outlook 블록] 을 추가 작성한다** (→ `references/pm-outlook.md`)
