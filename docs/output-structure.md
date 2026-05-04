# 출력 구조

```
output/
├── index.html                   # 메인 허브 (Summary + Research + Fund)
├── summary/                     # Market Summary 일/주/월/분기 보고서
│   ├── index.html              # Summary 인덱스 (Daily/Weekly/Monthly/Quarterly 4개 탭)
│   ├── YYYY-MM/
│   │   ├── YYYY-MM-DD.html     # 일일 보고서 (Data + Market/CS/PM Story 탭)
│   │   ├── YYYY-MM-DD_story.html
│   │   ├── YYYY-MM-DD_cs.html
│   │   ├── YYYY-MM-DD_pm.html
│   │   └── YYYY-MM-DD_data.json
│   ├── weekly/
│   │   ├── YYYY-WNN.html
│   │   └── YYYY-WNN_{story,cs,pm,macro}.html
│   ├── monthly/
│   │   ├── YYYY-MM.html
│   │   └── YYYY-MM_{story,cs,pm,macro}.html
│   └── quarterly/
│       ├── YYYY-QN.html
│       └── YYYY-QN_{story,pm,macro}.html
├── research/                    # 통합 리서치 플랫폼 (섹터·국가·테마 + 증권보고서)
│   ├── daily/                  # 섹터·국가 초보자 포지셔닝 보고서 (11일 사이클)
│   │   └── YYYY-MM/
│   │       ├── YYYY-MM-DD.html
│   │       └── YYYY-MM-DD_story.html
│   └── securities/             # 미래에셋증권 상세분석 다이제스트 (주 1회)
│       ├── digest_YYYY-WNN.html
│       ├── digest_latest.html
│       └── index.html
├── fund/                        # Fund Analysis — S3 기반 다운로드 페이지
│   └── index.html
├── prism/                       # MVP PRISM 보고서 S3 인덱스 (5개 카테고리 탭)
│   └── index.html
├── portfolio/                   # (이관됨 → market-strategy/, 레거시 잔존)
└── view/                        # (이관됨 → market-strategy/, 레거시 잔존)
```

GitHub Pages 자동 배포 (main 브랜치 push 시 `output/` 폴더).

## 보고서 탭 구성

- 일일: Data + Market Story + CS Story + PM Story
- 주간/월간: Data + Market/CS/PM/Macro Story
- 분기: Data + Market/CS/PM/Macro Story (PM = 회고 + 다음 분기 Outlook)
- 섹터·국가: Data + Story (섹터 Day N/11 · 국가 Day M/11)
