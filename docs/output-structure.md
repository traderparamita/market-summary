# 출력 구조

```
output/
├── index.html                   # 메인 허브 (Summary + Portfolio + View)
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
├── sector-country/              # 섹터·국가 초보자 포지셔닝 보고서 (11일 사이클)
│   └── daily/
│       └── YYYY-MM/
│           ├── YYYY-MM-DD.html
│           └── YYYY-MM-DD_story.html
├── fund/                        # Fund Analysis — S3 기반 다운로드 페이지
│   └── index.html
├── portfolio/                   # Portfolio Agent
│   ├── aimvp/
│   │   └── YYYY-MM-DD.html
│   └── strategy/
│       ├── YYYY-MM-DD.html
│       └── YYYY-MM-DD_signals.csv
└── view/                        # View Agent (9개 뷰)
    ├── index.html
    ├── price/          → YYYY-MM-DD.html
    ├── macro/          → YYYY-MM-DD.html
    ├── correlation/    → YYYY-MM-DD.html
    ├── regime/         → YYYY-MM-DD.html
    ├── country/        → YYYY-MM-DD.html
    ├── sector/         → YYYY-MM-DD.html
    ├── bond/           → YYYY-MM-DD.html
    ├── style/          → YYYY-MM-DD.html
    └── allocation/     → YYYY-MM-DD.html
```

GitHub Pages 자동 배포 (main 브랜치 push 시 `output/` 폴더).

## 보고서 탭 구성

- 일일: Data + Market Story + CS Story + PM Story
- 주간/월간: Data + Market/CS/PM/Macro Story
- 분기: Data + Market/CS/PM/Macro Story (PM = 회고 + 다음 분기 Outlook)
- 섹터·국가: Data + Story (섹터 Day N/11 · 국가 Day M/11)
