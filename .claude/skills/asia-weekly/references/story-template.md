# Asia Weekly — 6탭 HTML 구조 + Story 작성 톤

본 파일은 `_data.json` 을 받은 후 Claude 가 작성해야 할 **5개 탭의 본문 구조**와 **글쓰기 톤**을 정의한다. (Data 탭은 generate_asia_weekly.py 가 자동 채움)

---

## 탭 1: Asia Story (메인)

### 구조
```html
<div id="tab-story" class="tab-panel active">

  <!-- (1) Hero — 한 주 한 줄 요약 + 3 단락 -->
  <div class="story-hero">
    <h2>W## 한 줄 요약</h2>
    <div class="story-text">
      <p>핵심 내러티브 1단락 (가장 큰 그림)...</p>
      <p>국가별 명암 1단락 (어디가 강했고 어디가 약했나)...</p>
      <p>매크로 컨텍스트 1단락 (달러·금리·정상회담 등)...</p>
    </div>
  </div>

  <!-- (2) 인과 체인 — 5 노드 -->
  <h2 style="font-size:18px;...">한 주의 인과 체인 (Asia Causal Chain)</h2>
  <div class="causal-chain">
    <div class="cause-node">[월요일 트리거]</div>
    <div class="cause-arrow">→</div>
    <div class="cause-node">[화·수·목 핵심 흐름]</div>
    ...5 노드
  </div>

  <!-- (3) 핵심 인사이트 — 6 카드 -->
  <h2 style="font-size:18px;...">이번 주 핵심 인사이트</h2>
  <div class="insight-grid">
    <div class="insight-card">
      <span class="badge">Theme 1</span>
      <h3>인사이트 제목</h3>
      <p>본문...</p>
      <div class="metric-row">
        <div class="metric-item">
          <div class="metric-label">지표</div>
          <div class="metric-value up">+X.XX%</div>
        </div>
      </div>
    </div>
    ...6 카드
  </div>

  <!-- (4) 표면 vs 내부 — 4 인사이트 카드 (또는 단순 표) -->
  ...
</div>
```

### 톤 가이드

- **존댓말 (~했습니다, ~됐습니다, ~입니다)**
- 문장 길이는 길어도 OK (자세한 서술 선호) — **사용자 피드백: "최대한 자세하게"**
- 'hl-up' (빨강) = 상승 강조, 'hl-down' (파랑) = 하락 강조, 'hl-warn' (주황) = 경계
- 매크로 단위 표현: "한 주 누적 달러 +X.XX%", "주중 ±X.XX%", "단일일 ±X.XX%"
- 인사이트 카드 6개는 일반적으로:
  1. 가장 큰 주제 (예: 반도체 디커플링)
  2. 한국 또는 대형 단일 시장 이벤트
  3. 통화·매크로 흐름
  4. 두 번째 국가 이슈 (일본·인도)
  5. 세 번째 국가 이슈 (인도·대만)
  6. 보조 테마 또는 디스퍼션

### 인과 체인 5 노드 표준 패턴

```
[월요일 트리거] → [중반 핵심 흐름] → [목요일 고점·전환] → [금요일 충격·반전] → [주말 마감 결과]
```

각 노드는:
- `node-label`: 시점 (월요일·화·수·목·금)
- `node-title`: 이벤트 한 줄
- `node-detail`: 2~3줄 상세
- `node-impact`: 결과 (±X.XX%, 또는 상승/하락 마커)

---

## 탭 2: Country Drilldown

### 구조
```html
<div id="tab-country" class="tab-panel">

  <!-- 국가 1: 중국 -->
  <div class="country-section cn">
    <div class="country-head">
      <span class="country-flag">🇨🇳</span>
      <div>
        <div class="country-title">중국 (China)</div>
        <div>지수 변동률 · 통화 · 한 줄 평</div>
      </div>
      <div class="country-sub">유니버스 N종목 · CSV 매칭 M종목</div>
    </div>

    <p>국가 헤드라인 1~2 문단...</p>
    <p>핵심 촉매 1~2 문단 (정책·실적·매크로)...</p>

    <h4>🚀 W## 폭등주 TOP N</h4>
    <table class="stock-table">[8~10행]</table>

    <h4>📉 W## 약세주 TOP N</h4>
    <table class="stock-table">[8~10행]</table>

    <p>구조 분석·종합 평가...</p>
  </div>

  <!-- 국가 2: 일본 -->
  <div class="country-section jp">...</div>
  <!-- 국가 3~6: 대만·인도·홍콩·한국 -->
</div>
```

### 톤 가이드

- 각 국가당 길이: 본문 2~4 문단 + TOP/BOTTOM 표 1~2개
- 종목 표는 `stock-table` 클래스 (자유 클래스, tab-story 밖이라 OK)
- 종목 비고는 짧게 (해당 종목의 비즈니스 한 줄 — countries.md 참조)
- **종합 평가** 마지막 문단에 가중·단순 평균과 한 줄 평 포함

### 국가별 색상 (border-left-color)
- 🇨🇳 중국: `var(--cn)` = #d92b2b
- 🇯🇵 일본: `var(--jp)` = #043B72
- 🇹🇼 대만: `var(--tw)` = #0f7f5a
- 🇮🇳 인도: `var(--in)` = #7c4dff
- 🇭🇰 홍콩: `var(--hk)` = #9c27b0
- 🇰🇷 한국: `var(--kr)` = #F58220

---

## 탭 3: Themes (횡단 주제)

### 구조
```html
<div id="tab-themes" class="tab-panel">

  <div class="theme-card">
    <h3><span class="theme-tag">Theme #1</span> 주제 제목</h3>
    <p>주제 본문 1단락...</p>
    <p>핵심 촉매 1단락 (3개 요소로 구조화)...</p>

    <!-- (선택) 좌우 비교 그리드 -->
    <div class="theme-grid">
      <div class="theme-side" style="...">
        <h5 style="color:var(--up)">측면 A (예: 중국 폭등주)</h5>
        <ul>[종목 리스트]</ul>
      </div>
      <div class="theme-side" style="...">
        <h5 style="color:var(--down)">측면 B (예: 일본 폭락주)</h5>
        <ul>[종목 리스트]</ul>
      </div>
    </div>

    <p>해석·시사점·리스크...</p>
  </div>

  <!-- 4~5 theme-card -->
</div>
```

### 테마 선정 기준 (5개 권장)

1. **국가 간 디스퍼션** — 같은 산업, 정반대 방향 (중·일 반도체 등)
2. **통화·금리** — 광범위 달러 강세 vs 위안 안정 등
3. **AI 인프라** — 광통신·메모리·서버 전원 등 데이터센터 인프라
4. **정책 리스크** — 한국 정책, 중국 부양책 등
5. **지정학** — 미·중 정상회담·관세·반도체 통제

매주 비슷한 5개 테마 + 그 주의 특이 사항 추가/대체.

---

## 탭 4: Data (자동 생성)

`generate_asia_weekly.py` 가 자동으로 채움. Claude 는 **수정 금지**.

### 자동 채움 항목
1. 아시아 지수 W## 변동률 표 (8개)
2. 아시아 통화 W## 변동률 표 (5개)
3. TOP 20 종목 표
4. BOTTOM 20 종목 표
5. 국가별 종합 표

---

## 탭 5: Outlook (다음 주)

### 구조
```html
<div id="tab-outlook" class="tab-panel">

  <!-- (1) 시나리오 3종 -->
  <div class="outlook-card">
    <h3>W## (다음 주) 시나리오 분석</h3>
    <p>핵심 미해결 변수 3가지...</p>
    <div class="outlook-grid">
      <div class="scenario bull"><h4>🐂 Bull (확률 N%)</h4>...</div>
      <div class="scenario base"><h4>📊 Base (확률 N%)</h4>...</div>
      <div class="scenario bear"><h4>🐻 Bear (확률 N%)</h4>...</div>
    </div>
  </div>

  <!-- (2) 리스크 TOP 5 — 필수 섹션 -->
  <div class="risk-section">
    <h2>⚠️ W## 주목 리스크 TOP 5</h2>
    <ul class="risk-items">
      <li><span class="risk-tag high">高</span><div>리스크 1...</div></li>
      <li><span class="risk-tag high">高</span><div>리스크 2...</div></li>
      <li><span class="risk-tag high">高</span><div>리스크 3...</div></li>
      <li><span class="risk-tag med">中</span><div>리스크 4...</div></li>
      <li><span class="risk-tag med">中</span><div>리스크 5...</div></li>
    </ul>
  </div>

  <!-- (3) 데이터 캘린더 -->
  <div class="theme-card">
    <h3><span class="theme-tag">W## 모니터링</span> 데이터 캘린더</h3>
    <ul>[5~7개 이벤트]</ul>
  </div>
</div>
```

### Outlook 톤 가이드 (forward 화이트리스트)

- **Outlook 탭은 명시적 forward 영역** — "다음 주 ~할 가능성", "~시나리오에서 ~예상" 등 forward 표현 자유롭게
- 시나리오 확률은 보통 Bull 25-30% / Base 45-55% / Bear 20-25%
- 각 시나리오의 트리거 + 시장 반응을 함께 명시
- 리스크 5개는 모두 다음 주에 발생 가능한 구체 이벤트 (수치·날짜 포함)
- 데이터 캘린더는 **공개된 발표 일정**만 (결과는 미공개)

### 필수 마커 (구조 검증 통과)

- `class="risk-section"` 1회
- `class="risk-items"` 1회
- 둘 다 Outlook 탭 안에 있어야 함 (또는 다른 탭에서라도 1회 등장)

---

## 탭 6: Sources

### 구조
```html
<div id="tab-sources" class="tab-panel">

  <div class="sources-section">
    <h3>1. 시장 데이터 (Quotes)</h3>
    <ul class="sources-list">
      <li><strong>history/market_data.csv</strong> — Snowflake 정본 미러</li>
      <li><strong>history/아시아종목.xlsx</strong> — 운용 유니버스 180종목</li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>2. 미래에셋증권 W##~W## Research Digest</h3>
    <ul>
      <li><a href="../../research/securities/digest_2026-W##.html">W## Digest</a> — 핵심 키 인사이트</li>
      <li>...최소 4건 (W17 직전 4주)</li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>3. W## 핵심 단편 보고서 (원문)</h3>
    <ul>
      <li>「보고서명」 — 핵심 메시지 한 줄</li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>4. 외부 참고 자료 (웹 검색)</h3>
    <ul>
      <li><a href="URL">제목 — 출처</a></li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>5. 산출 방법론</h3>
    <ul>
      <li>기간 정의·WTD 계산·가중평균 공식·유니버스 매칭률·한계</li>
    </ul>
  </div>
</div>
```

### Sources 톤 가이드

- 최소 4개 섹션 (1~5번)
- 각 섹션마다 최소 3개 항목
- 미래에셋증권 디지스트는 **최근 4주** 링크 (W##-3 ~ W##)
- 외부 자료는 가능하면 hyperlink + 출처 명시
- 5번 산출 방법론에 매칭률·한계를 솔직하게 명시 ("CSV 매칭 65/180, 홍콩·베트남·인니·호주는 가중평균에서 제외")

---

## 헤더·KPI 스트립 (자동 생성)

generate_asia_weekly.py 가 자동 채우는 부분이므로 Claude 는 수정하지 않는다. 단, 헤더의 mood badge (위험 분위기) 는 **수동 조정 가능**:

```html
<div class="mood-badge">
  <span style="...;background:var(--down)"></span>
  아시아 광역 약세 — MSCI EM <span style="...">−4.22%</span>
</div>
```

- MSCI EM &lt; &minus;3% 이면 자동 risk-off (파랑)
- MSCI EM 0% 부근이면 mixed (주황)
- MSCI EM > +3% 이면 risk-on (빨강)
- 모든 지표의 단순 평균이 ±2% 안에 있으면 "Mixed" 표현 사용

---

## CSS 정의 — 비-화이트리스트 클래스 (tab-story 밖에서만 사용)

다음 클래스는 generate_asia_weekly.py 가 HTML `<style>` 에 미리 정의해두므로 Claude 는 본문에서 그대로 사용:

- `country-section`, `country-section.cn/jp/tw/in/hk/kr`, `country-head`, `country-flag`, `country-title`, `country-sub`
- `stock-table`, `gain`, `loss`
- `theme-card`, `theme-tag`, `theme-grid`, `theme-side`, `theme-side h5`
- `outlook-card`, `outlook-grid`, `scenario`, `scenario.bull/base/bear`
- `section-title` (사용 안 함 — h2 inline 스타일로 대체)
- `sources-section`, `sources-list`, `source-meta`
- `heatmap`, `name-cell`, `close-cell`, `heat-cell`, `spark-cell` (Data 탭 내부에서만)

**중요**: `tab-story` 블록 안에서는 이 클래스들을 **사용하지 말 것** (구조 검증 차단). Story 탭에서 표가 필요하면 `insight-card` 패턴으로 대체.

---

## 검증 체크리스트

작성 완료 후 다음을 확인:

- [ ] `class="story-hero"` `class="causal-chain"` `class="insight-grid"` `class="risk-section"` `class="risk-items"` 5개 마커 존재
- [ ] tab-story 블록 안에서 비-화이트리스트 클래스 사용 없음
- [ ] 모든 수치(±X.XX%, ±N bp)가 `_data.json` 또는 `history/market_data.csv` 와 일치
- [ ] forward-looking 위반 없음 (Outlook 탭 외)
- [ ] 인과관계 방향: 과거 → 현재 (미래 결과 사후 참조 없음)
- [ ] 종목명·티커가 xlsx 와 일치
- [ ] 미매칭 종목의 수치 인용 없음 (Sources에 한계 명시)
- [ ] 존댓말 (~합니다체) 일관성
- [ ] Sources 탭 최소 4개 섹션
