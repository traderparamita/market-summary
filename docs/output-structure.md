# 출력 구조

```
output/
├── index.html                   # 메인 허브 (Summary · Research · MiraeAsset Securities · MVP Prism)
├── assets/                      # 브랜드 에셋 (favicon, OG 이미지)
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
│   │   └── YYYY-WNN_{story,cs,pm,macro,asia}.html
│   ├── monthly/
│   │   ├── YYYY-MM.html
│   │   └── YYYY-MM_{story,cs,pm,macro}.html
│   └── quarterly/
│       ├── YYYY-QN.html
│       └── YYYY-QN_{story,pm,macro}.html
├── research/                    # 일간 테마 리서치 허브
│   ├── index.html              # 최신 일간 리서치 직접 표시 (generate_sector_country._update_sc_index)
│   └── daily/
│       └── YYYY-MM/
│           ├── YYYY-MM-DD.html
│           └── YYYY-MM-DD_story.html
├── securities/                  # 미래에셋증권 상세분석 보고서
│   ├── index.html              # S3 pre-signed URL 목록 (generate_securities_index.py)
│   └── digest/                 # 주간 리서치 다이제스트 (generate_securities_digest.py)
│       ├── digest_YYYY-WNN.html
│       └── digest_latest.html
├── prism/                       # MVP PRISM 보고서 S3 인덱스 (5개 카테고리 탭)
│   └── index.html
└── fund/                        # Fund Analysis — S3 기반 다운로드 페이지
    └── index.html
```

GitHub Pages 자동 배포 (main 브랜치 push 시 `output/` 폴더).

## 보고서 탭 구성

- 일일: Data + Market Story + CS Story + PM Story
- 주간/월간: Data + Market/CS/PM/Macro Story
- 분기: Data + Market/CS/PM/Macro Story (PM = 회고 + 다음 분기 Outlook)
- 섹터·국가: Data + Story (섹터 Day N/11 · 국가 Day M/11)
