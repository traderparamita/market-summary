# Sources 탭 작성 절차

Story 작성 시 참조한 뉴스·데이터 소스를 `tab-sources` 탭에 기록한다. 팩트체크 추적성 확보가 목적.

## 수집 시점

Story 작성을 위한 웹 검색(Tavily/WebSearch) 수행 시, 각 결과의 **URL · 제목 · 매체명 · 발행일**을 즉시 기록한다. Story 완성 후 한꺼번에 주입.

## HTML 구조

**인라인 스타일 사용 금지** — 모든 스타일은 아래 CSS 클래스로 처리한다. `generate.py` 글로벌 CSS에 정의되어 있음.

```html
<div id="tab-sources" class="tab-panel">
  <div class="sources-header">
    <h2>참조 출처 — YYYY-MM-DD 일간</h2>
    <div class="sources-sub">본 보고서 작성에 참조된 뉴스 및 데이터 소스 목록입니다.</div>
  </div>

  <div class="sources-section">
    <h3>🌏 아시아 세션</h3>
    <ul class="sources-list">
      <li><a href="URL" target="_blank">기사 제목</a> — <span class="source-meta">매체명 · YYYY-MM-DD</span></li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>🇪🇺 유럽 세션</h3>
    <ul class="sources-list">
      <li><a href="URL" target="_blank">기사 제목</a> — <span class="source-meta">매체명 · YYYY-MM-DD</span></li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>🇺🇸 미국 세션</h3>
    <ul class="sources-list">
      <li><a href="URL" target="_blank">기사 제목</a> — <span class="source-meta">매체명 · YYYY-MM-DD</span></li>
    </ul>
  </div>

  <div class="sources-section">
    <h3>📊 데이터 소스</h3>
    <ul class="sources-list">
      <li>history/market_data.csv — Snowflake MKT100_MARKET_DAILY</li>
      <li>history/macro_indicators.csv — FRED · ECOS</li>
      <li>output/summary/YYYY-MM/YYYY-MM-DD_data.json — generate.py 산출 메트릭</li>
    </ul>
  </div>
</div><!-- /tab-sources -->
```

**허용 CSS 클래스** (이외 커스텀 클래스·인라인 스타일 금지):
- `.sources-header` — 그라디언트 헤더 + 파란색 border-left
- `.sources-sub` — 헤더 부제목 (muted 색상)
- `.sources-section` — 각 섹션 카드 (border, radius)
- `.sources-list` — 링크 목록 (list-style:none, padding-left:0)
- `.source-meta` — 매체명·날짜 메타데이터 (muted, 12px)

## 작성 규칙

1. **세션별 그룹**: 아시아 → 유럽 → 미국 → 데이터 소스 순서
2. **주간/월간**: 요일별 또는 주요 이벤트별 그룹 (세션 구분 대신 날짜별 구분 가능)
3. **URL 필수**: 링크 없는 출처는 매체명+날짜+제목으로 텍스트 기재
4. **데이터 소스 고정**: 매 보고서마다 CSV/Snowflake 기본 소스 표기
5. **최소 건수**: 일간 5건 이상, 주간 10건 이상, 월간 15건 이상
6. 저장 파일: `YYYY-MM-DD_sources.html` (일간) / `YYYY-WNN_sources.html` (주간) / `YYYY-MM_sources.html` (월간)
