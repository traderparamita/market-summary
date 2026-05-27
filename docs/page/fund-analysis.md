# Fund Analysis (S3 기반 다운로드 페이지)

펀드 리서치 HTML 문서를 비공개 S3 버킷에서 직접 내려받게 하는 메인 인덱스 카드 #3.

## S3 저장소

- Bucket: `mai-life-fund-documents-533370893966-ap-northeast-2-an`
- Prefix: `malife_var_dashboard/fund_reports/github/`
- Region: `ap-northeast-2`
- Block Public Access 4개 모두 True (해제 금지 — Mirae Asset 보안 정책)

## 접근 방식

Pre-signed URL (GetObject 서명, **7일 만료**):
- 보기용: 그대로 브라우저 오픈
- 다운로드용: `ResponseContentDisposition=attachment` 로 강제 다운로드
- 한글 파일명: RFC 5987 (`filename*=UTF-8''<percent-encoded>`) + ASCII fallback 병기

## 재생성

### 자동 (권장)

S3 업로드 책임은 상위 프로젝트 `malife_var_dashboard` 에 있음.
`scripts/upload_share_reports.py` 가 업로드 성공 후 post-upload hook 으로
이 레포의 `generate_fund_index.py` 를 subprocess 호출 → git commit + push → Telegram 알림.

- 상위 스크립트: `/Users/lifesailor/Desktop/kosmos/미래에셋생명/project/malife_var_dashboard/scripts/upload_share_reports.py`
- 경로 설정: 상위 `.env` 의 `MARKET_SUMMARY_ROOT=...`
- hook 은 실패해도 S3 업로드 자체엔 영향 없음 (격리됨)
- 업로드 시점마다 URL 7일 full 윈도우 확보

### 수동 (fallback)

```bash
.venv/bin/python scripts/generate_fund_index.py
```

`/market-full` 워크플로우에 포함 안 함 (의도적 분리).

## 파일 흐름

- 원본 HTML 은 S3 에만. `output/fund/*` 는 `.gitignore` 로 git 비추적 (`!output/fund/index.html` 예외)
- `output/fund/index.html` 자체는 git 에 커밋 (pre-signed URL 박힘)
- 주의: index.html 이 git 에 올라가면 URL 이 7일간 세계 공개됨
