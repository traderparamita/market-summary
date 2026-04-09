# Market Summary

일일/주간/월간 글로벌 시장 요약 보고서를 자동 생성하는 프로젝트.

## 실행 방법

매일 영업일 08:00 KST 전체 워크플로우:

```
/market-full [YYYY-MM-DD]    # 데이터 수집 → Dashboard → Story(일/주/월) → 배포
```

개별 단계:

```
/market-data [YYYY-MM-DD]    # 데이터 수집 + Data Dashboard만
/market-deploy               # output/ 변경분 commit + push
```

Market Story 작성 규칙·절차는 **`market-summary` 스킬**에 있다 (Story 작업 시 자동 로드).

**주의**: 미래 날짜의 보고서를 미리 생성하지 않는다.

## 구조

```
generate.py          # 핵심 엔진 - 데이터 수집 + HTML 보고서 생성
generate_periodic.py # 주간/월간 집계 보고서 생성
simulate.py          # 과거 날짜 시뮬레이션
inject_stories.py    # 시뮬레이션 보고서에 Story 주입
history/market_data.csv  # 일별 종가 시계열 (date,category,ticker,close)
```

## 데이터 소스

| 섹션 | 1차 소스 | 폴백 |
|------|----------|------|
| Equity | yfinance | FinanceDataReader → investiny |
| Bonds & Rates | yfinance (US), ECOS API (KR) | — |
| Bond ETF | yfinance | — |
| FX | investiny | FinanceDataReader |
| Commodities | investiny | yfinance |
| Risk (VIX, VKOSPI) | yfinance | FinanceDataReader |
| Major Stocks | yfinance | — |

- FX/Commodity는 `needs_inv_fix = True`로 항상 FDR → investiny 순 보정 시도
- 모든 Data Dashboard: `history/market_data.csv`가 단일 소스 (Single Source of Truth)
- 모든 Market Story: Claude 작성. 주간/월간은 일간 `_story.html`들을 종합

## 수집 대상

- **Equity**: KOSPI, KOSDAQ, S&P500, NASDAQ, Russell2K, STOXX50, DAX, CAC40, FTSE100, Nikkei225, Shanghai, HSI, NIFTY50
- **Bond**: US 2Y/10Y/30Y, TLT, HYG, LQD, EMB, KR CD91D/3Y/5Y/10Y/30Y
- **FX**: DXY, USD/KRW, EUR/USD, USD/JPY, USD/CNY, AUD/USD, GBP/USD
- **Commodity**: WTI, Brent, Gold, Silver, Copper, Natural Gas
- **Risk**: VIX, VKOSPI
- **Stocks**: NVIDIA, Broadcom, Alphabet, Amazon, META, Apple, Microsoft, Tesla, TSMC, Samsung

## 핵심 함수

- `_inject_existing_story(path, new_html)`: 보고서 재생성 시 기존 Story 보존 + `_save_story_file()` 자동 호출
- `_save_story_file(html_path, html_content)`: HTML에서 Story 추출 → `_story.html` 별도 저장 (Story가 있을 때만)

## 출력

```
output/
├── YYYY-MM/
│   ├── YYYY-MM-DD.html          # 일일 보고서 (Data + Story 탭)
│   ├── YYYY-MM-DD_story.html    # 일일 Story 별도 저장
│   └── YYYY-MM-DD_data.json     # 원시 데이터 (gitignore)
├── weekly/
│   ├── YYYY-WNN.html
│   └── YYYY-WNN_story.html
├── monthly/
│   ├── YYYY-MM.html
│   └── YYYY-MM_story.html
└── index.html                   # 전체 인덱스
```

GitHub Pages로 자동 배포 (main 브랜치 push 시 `output/` 폴더)

## 환경

- Python 3.12
- 의존성: yfinance, FinanceDataReader, requests, python-dotenv, investiny
- 환경변수: `ECOS_API_KEY` (한국은행 API, 프로젝트 루트 `.env`에서 dotenv로 로딩)

## 주의사항

- HTML 보고서는 Data 탭과 Story 탭 2개로 구성. Story가 없으면 placeholder 유지
- Data 탭의 각 섹션 헤더에 데이터 소스 표시 (src-tag CSS 클래스)
- `history/market_data.csv`: 종가 시계열. git에 커밋됨. 보고서 재현의 단일 소스
- `.gitignore`: `_data.json`과 `data/` 포함 - 원시 데이터 미커밋
- investiny 소스가 주말 날짜 데이터를 반환할 수 있음 → 수집 시 자동 필터링

## 관련 설정

- `.claude/settings.json`: Market Story 시간 정확성 검증 훅 3개 (PreToolUse WebSearch, PreToolUse Edit, PostToolUse Write)
- `.claude/skills/market-summary/SKILL.md`: Story 작성 규칙·절차 (Story 작업 시 자동 로드)
- `.claude/commands/`: `/market-data`, `/market-deploy`, `/market-full`
