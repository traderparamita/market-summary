# PM Outlook 작성 절차

PM Outlook 은 PM Story (회고) 바로 아래에 붙는 **forward-looking 전망** 섹션입니다. 일간 PM 의 `pm-hero Watch` 와는 별개로, **주간 / 월간 / 분기 PM Story** 마지막에 통합 — 매니저가 한 페이지에서 회고 + 전망 모두 봅니다.

**선행 reference**: PM 회고 6 섹션은 `references/pm.md`. 본 파일은 그 위에 얹는 forward 블록만 다룬다.

---

## 전제

- **선행 조건**: 해당 기간 PM Story 회고 6섹션이 이미 작성됨 (또는 같은 작업 세션에 함께 작성)
- **대상 영역**: PM 탭 본문 마지막. 새 placeholder/탭 X — 회고 섹션 직후 신규 블록으로 추가
- **별도 파일 저장**: PM sibling 파일(`_pm.html`) 안에 회고 + Outlook 모두 포함. 별도 outlook sibling 만들지 않음
- **적용 범위**: 주간 / 월간 / 분기 (일간 제외 — 일간은 pm-hero Watch 활용)
- **Forward-looking 허용 영역**: PM 작성 컨텍스트 또는 `_pm.html` 편집 시점에는 forward 표현 통과 (settings.json 훅 조정 참조)

## Step 1: 사실 기반 수집

- 회고 PM Story 의 6섹션 수치·이벤트 Read
- 해당 시점 (보고서 작성일 기준) 까지 발표된 매크로 데이터·실적·지정학 이벤트만 사용
- 다음 기간 예정 이벤트 캘린더 WebSearch (FOMC, CPI, NFP, 한은 금통위, 대형주 실적, 지정학 일정)
- **금지**: 보고서 시점 이후 실제 발생한 사건 참조 (Q1 분기 보고서라면 4월 실제 발생 사건 X)

## Step 2: Hybrid 4 파트 구성

### Part 1 — 시나리오 헤로 (Bull / Base / Bear 3카드)

각 카드 8~12 줄, **가운데 Base 강조**(테두리·배경 진하게):
- 시나리오 라벨 (Bull · Base · Bear)
- **확률 정성 라벨** ("유력 / 중간 / 낮음" — 정량 확률 금지)
- **트리거 조건** 2~3개 (`if X happens` 식 조건문)
- **자산 함의** 4~5줄 — KOSPI · S&P500 · USD/KRW · 유가 · 금리 (10Y) 방향

### Part 2 — PM 6섹션 Watch & Trigger

🇰🇷 한국 · 🌐 매크로 · 🌏 아시아 및 중국 · 🇺🇸 미국 · 🇪🇺 유럽 · 💵 채권 — 각 섹션 4~6 불릿:
- **다음 기간 핵심 이벤트** (날짜 + 컨센서스/예상)
- **Watch points**: 가격·지표 레벨 (예: KOSPI 5,000 지지, 10Y-2Y 70bp 재침투, 유가 $110)
- **Trigger / If-Then**: 조건문 (예: "VIX 25 재돌파 → 방어자산 우위", "원/달러 1,520 돌파 → 한은 정책 부담")
- **금지**: "비중 확대 권장" 같은 직접 매수/매도 권유. 관점·트리거 서술만.

### Part 3 — 통합 리스크 (3~5개)

- 심각도 태그 (`risk-tag high|med|low`)
- 트리거 조건 + 자산군별 영향 한 줄
- 회고 PM Story 의 리스크와 다른 시점·관점 (회고 = "이미 발생한 우려", Outlook = "앞으로 닥칠 가능성")

### Part 4 — 포지셔닝 시사점 박스

- 지역·자산군별 OW / N / UW 한 줄씩 (Base 시나리오 하 합리적 포지션)
- "권유" 가 아닌 "Base 시나리오 하에서 합리적이라고 판단되는 포지션"
- **분기 Outlook 한정 추가**: 분기 테마 후보 2~3개 (예: "AI 인프라 후반전", "지정학 프리미엄 재가격")

## Step 3: HTML 골격

```html
<!-- ── Outlook 블록 시작 (PM Story 회고 6섹션 직후) ── -->
<div class="outlook-divider">
  <h2>📈 다음 {기간} Outlook</h2>
  <div class="cs-subtitle">{시나리오·Watch·리스크·포지셔닝 — 작성 시점 기준 forward 시각}</div>
</div>

<!-- Part 1: 시나리오 3카드 -->
<div class="scenario-grid">
  <div class="scenario-card bull">
    <h3>🟢 Bull</h3>
    <div class="scen-prob">확률: 낮음</div>
    <div class="scen-trigger">
      <strong>트리거:</strong>
      <ul>
        <li>{트리거 조건 1}</li>
        <li>{트리거 조건 2}</li>
      </ul>
    </div>
    <div class="scen-impact">
      <strong>자산 함의:</strong>
      <ul>
        <li>KOSPI ...</li>
        <li>S&amp;P500 ...</li>
        <li>USD/KRW ...</li>
        <li>유가·금리 ...</li>
      </ul>
    </div>
  </div>
  <div class="scenario-card base">
    <h3>🟡 Base (유력)</h3>
    ...
  </div>
  <div class="scenario-card bear">
    <h3>🔴 Bear</h3>
    ...
  </div>
</div>

<!-- Part 2: PM 6섹션 Watch & Trigger (회고 섹션과 동일 pm-grid 재사용) -->
<h3 class="outlook-section-title">📍 자산군별 Watch & Trigger</h3>
<div class="pm-grid">
  <div class="pm-section">
    <h3>🇰🇷 한국</h3>
    <ul>
      <li><strong>4/9 한은 금통위</strong> — 컨센서스 2.50% 동결</li>
      <li>Watch: KOSPI 5,000 지지, USD/KRW 1,500 라인</li>
      <li>Trigger: 외국인 5조+ 추가 매도 → 패닉 모드 재진입</li>
      ...
    </ul>
  </div>
  <!-- 나머지 5섹션 -->
</div>

<!-- Part 3: 통합 리스크 -->
<div class="risk-section">
  <h3>⚠ 주요 리스크</h3>
  <ul class="risk-items">
    <li class="risk-item"><span class="risk-tag high">High</span> {리스크 1} — {트리거 + 영향}</li>
    ...
  </ul>
</div>

<!-- Part 4: 포지셔닝 박스 -->
<div class="outlook-position">
  <h3>🎯 포지셔닝 시사점 (Base 시나리오)</h3>
  <ul>
    <li>한국 — N (Watch: KOSPI 5,000 지지)</li>
    <li>미국 — N (실적 시즌 결과 확인 후 판단)</li>
    <li>...</li>
  </ul>
  <!-- 분기 Outlook 한정 -->
  <div class="quarterly-themes">
    <strong>분기 테마 후보:</strong>
    <ul>
      <li>{테마 1}</li>
      <li>{테마 2}</li>
    </ul>
  </div>
</div>
<!-- ── Outlook 블록 끝 ── -->
```

## CSS 화이트리스트 (Outlook 신규 클래스)

기존 PM CSS 재사용 + 다음 신규:
```
outlook-divider, outlook-section-title, outlook-position
scenario-grid, scenario-card (bull|base|bear), scen-prob, scen-trigger, scen-impact
quarterly-themes
```

CSS 정의는 PM 본문 첫 머리에 인라인 `<style>` 으로 추가 (기존 PM `_pm.html` 의 인라인 CSS 패턴 재사용 — 과거 보고서에도 포터블 적용).

```css
.outlook-divider{border-top:2px solid #043B72;margin-top:32px;padding-top:24px;margin-bottom:20px}
.outlook-divider h2{font-size:18px;color:#043B72;margin-bottom:6px}

.scenario-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:24px}
@media (max-width:900px){.scenario-grid{grid-template-columns:1fr}}
.scenario-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px 22px}
.scenario-card.bull{border-left:4px solid #d92b2b}
.scenario-card.base{border-left:4px solid #F58220;background:linear-gradient(180deg,#fff5eb 0%,#fff 60%);box-shadow:0 2px 8px rgba(245,130,32,0.08)}
.scenario-card.bear{border-left:4px solid #1a5fb4}
.scenario-card h3{font-size:15px;font-weight:700;margin-bottom:8px}
.scen-prob{font-size:12px;color:var(--muted);margin-bottom:10px}
.scen-trigger,.scen-impact{font-size:13.5px;color:#2d3148;margin-bottom:8px;line-height:1.7}
.scen-trigger ul,.scen-impact ul{list-style:none;padding-left:0;margin:4px 0 0 0}
.scen-trigger li,.scen-impact li{padding-left:10px;position:relative;margin-bottom:3px}
.scen-trigger li::before,.scen-impact li::before{content:'·';position:absolute;left:0;color:#043B72}

.outlook-section-title{font-size:15px;font-weight:700;color:#043B72;margin:20px 0 12px}
.outlook-position{background:#eef4fb;border:1px solid var(--border);border-left:4px solid #043B72;border-radius:10px;padding:18px 24px;margin-top:20px}
.outlook-position h3{font-size:14px;color:#043B72;margin-bottom:10px}
.outlook-position ul{list-style:none;padding-left:0}
.outlook-position li{padding:4px 0;font-size:13.5px}
.quarterly-themes{margin-top:14px;padding-top:12px;border-top:1px dashed var(--border)}
```

## 주간 / 월간 / 분기 깊이 가이드

| 항목 | 주간 | 월간 | 분기 |
|------|------|------|------|
| 시나리오 카드 길이 | 6~8줄 | 8~10줄 | 10~14줄 |
| 6섹션 불릿 | 3~4 | 4~5 | 5~6 |
| 리스크 개수 | 3 | 4 | 5 |
| 포지셔닝 항목 | 4~5 | 6 (지역+자산) | 6 + 분기 테마 2~3 |
| 검색 쿼리 범위 | `next week W{N+1}` | `next month {YYYY-MM+1}` | `next quarter Q{N+1}` |

## 자가 검증 체크리스트

- [ ] 시나리오 3카드 모두 있는가? (Bull/Base/Bear, Base 강조)
- [ ] 각 카드에 트리거 조건 + 자산 함의 모두 있는가?
- [ ] 6섹션 Watch & Trigger 가 다음 기간 사건 기반인가? (회고 사건 반복 X)
- [ ] 리스크가 시각상 회고 PM 의 리스크와 차별되는가? (forward 시각인가)
- [ ] 포지셔닝 박스의 표현이 "권유" 가 아닌 "Base 시나리오 하 합리적 포지션" 인가?
- [ ] 분기 Outlook 이면 분기 테마 후보 2~3개 있는가?
- [ ] 보고서 시점 이후 실제 발생한 사건이 Outlook 에 들어가지 않았는가?
- [ ] `_pm.html` sibling 안에 회고 + Outlook 모두 있는가?
