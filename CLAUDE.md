# Market Summary

일일/주간/월간 글로벌 시장 요약 보고서를 자동 생성하는 프로젝트.

## 구조

```
generate.py          # 핵심 엔진 - 데이터 수집 + HTML 보고서 생성 (1170줄)
generate_stories.py  # Story 탭 콘텐츠 - 날짜별 CONTEXT dict에 해설/인사이트/리스크 저장
generate_periodic.py # 주간/월간 집계 보고서 생성 (generate.py의 함수 재사용)
extract_data.py      # _data.json에서 주요 지표 추출/출력 (디버그/분석용)
batch_*.py           # 과거 날짜 일괄 생성 스크립트
prompt.md            # 원래 보고서 작성 가이드라인 (참고용)
```

## 데이터 흐름

1. `generate.py fetch_data()` → yfinance + FinanceDataReader(한국지수 fallback) + 한국은행 ECOS API(한국 금리)
2. 수집 데이터 → `output/YYYY-MM/YYYY-MM-DD_data.json` 저장
3. `generate_html()` → 히트맵/스파크라인/차트 포함 HTML 보고서 생성
4. Story 탭: `generate_stories.py`의 CONTEXT dict에서 해당 날짜 콘텐츠 주입
5. 주간/월간: `generate_periodic.py`가 일간 JSON 집계하여 별도 보고서 생성

## 수집 대상

- **Equity**: KOSPI, KOSDAQ, S&P500, NASDAQ, Russell2K, STOXX50, DAX, CAC40, FTSE100, Nikkei225, Shanghai, HSI, NIFTY50
- **Bond**: US 2Y/10Y/30Y, TLT, HYG, LQD, EMB, KR CD91D/3Y/5Y/10Y/30Y
- **FX**: DXY, USD/KRW, EUR/USD, USD/JPY, USD/CNY, AUD/USD, GBP/USD
- **Commodity**: WTI, Brent, Gold, Silver, Copper, Natural Gas
- **Risk**: VIX, VKOSPI
- **Stocks**: NVIDIA, Broadcom, Alphabet, Amazon, META, Apple, Microsoft, Tesla, TSMC, Samsung

## 실행

```bash
# 특정 날짜 보고서 생성
python3.12 generate.py 2026-04-03

# 인자 없으면 오늘 날짜
python3.12 generate.py
```

## 출력

- `output/YYYY-MM/YYYY-MM-DD.html` - 일일 보고서 (Data 탭 + Story 탭)
- `output/YYYY-MM/YYYY-MM-DD_data.json` - 원시 데이터
- `output/weekly/`, `output/monthly/` - 주간/월간 집계 보고서
- `output/index.html` - 전체 인덱스 페이지
- GitHub Pages로 자동 배포 (main 브랜치 push 시 output/ 폴더)

## 환경

- Python 3.12
- 의존성: yfinance, FinanceDataReader, requests
- 환경변수: `BOK_API_KEY` (한국은행 API, 없으면 sample 키로 제한 동작)

## Market Story 작성 규칙

### Forward Looking 금지 (일간/주간/월간 모두 적용)
- 일간, 주간, 월간 보고서 모두 **해당 기간 마지막 날까지만 알 수 있는 정보**로 작성
- 이후 날짜의 사건/데이터/결과를 절대 참조하지 않는다
- 주간 보고서: 해당 주 금요일(또는 마지막 영업일)까지의 정보만 사용
- 월간 보고서: 해당 월 마지막 영업일까지의 정보만 사용
- "~할 수 있다", "~가능성이 있다" 같은 전망은 허용 (분석), "이후 실제로 ~했다" 같은 사후 참조는 금지 (바이어스)

### 보고서 생성 시점 기준 데이터 제한
- 보고서는 매일 08:00 KST에 생성된다고 가정
- 예: 2026-04-07 보고서 → 2026-04-07 08:00 KST 이전에 확정된 데이터만 사용
- 이 시점 기준으로 사용 가능한 데이터:
  - 전일(4/6) 아시아·유럽·미국 세션 전체 (이미 마감)
  - 당일(4/7) 아시아 프리마켓 뉴스 (08시 이전 것만)
  - 전일까지의 가격 데이터 (_data.json)
- 사용 불가: 당일 09시 이후 아시아 장중 데이터, 유럽/미국 세션 데이터

### 시간순 데이터 수집 및 작성
- 웹 검색 시 해당 날짜의 이벤트를 **시간 순서대로** 수집한다
- 수집 순서: 아시아 세션(09:00~15:30 KST) → 유럽 세션(16:00~22:00 KST) → 미국 세션(22:30~05:00 KST)
- 각 세션별로 발생한 경제지표 발표, 중앙은행 발언, 지정학 이벤트, 기업 실적을 시간순 정리
- narrative와 causal_chain도 이 시간 흐름을 반영하여 작성 (아시아 → 유럽 → 미국 순)
- 선행 세션의 결과가 후행 세션에 어떤 영향을 미쳤는지 인과관계를 명확히 서술

## 주의사항

- `generate_stories.py`의 CONTEXT dict는 수천 줄 규모. 날짜별로 headline, narrative, causal_chain, insights, risks 구조
- HTML 보고서는 Data 탭과 Story 탭 2개로 구성. Story가 없으면 placeholder 유지
- `_inject_existing_story()`: 데이터 재생성 시 기존 Story 콘텐츠 보존
- `.gitignore`에 `_data.json`과 `data/` 포함 - 원시 데이터는 커밋하지 않음
