"""미래에셋증권 'AI 데일리 글로벌 마켓 브리핑' PDF를 과거 일자까지 백필.

기존 `generate_ocr_story.py` 의 PDF 탐색·다운로드·S3 업로드 로직을 재사용하되,
단일 일자 대신 [start, end] 기간 전체를 월 단위 검색으로 훑어 모든 일자의 PDF
를 S3 에 보관한다 (OCR · Story 생성은 수행하지 않음).

PDF 의 본문 시점(target_date)은 다음 규칙으로 추론:
  1. 제목 "AI 데일리 글로벌 마켓 브리핑(M월 D일)..." 에서 한글 날짜 파싱
  2. row_date(게시일)의 연도 사용. 단, 1월 초 게시 + 제목이 12월/11월이면 -1년

S3 키: anthillia/miraeasset-daily/YYYY-MM/YYYY-MM-DD_briefing.pdf
       (generate_ocr_story.py 와 동일한 패턴)

Usage:
    .venv/bin/python scripts/backfill_daily_briefing.py                       # 2025-01-01 ~ 오늘
    .venv/bin/python scripts/backfill_daily_briefing.py --start 2025-01-01 --end 2025-12-31
    .venv/bin/python scripts/backfill_daily_briefing.py --dry-run             # 업로드 없이 목록만
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import boto3
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

from _utils import S3_BUCKET

S3_PDF_PREFIX = "anthillia/miraeasset-daily"
S3_REGION = os.getenv("AWS_REGION", "ap-northeast-2")

BASE_URL = "https://securities.miraeasset.com"
LIST_URL = f"{BASE_URL}/bbs/board/message/list.do"
CATEGORY_ID = "1521"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
DOWNLOAD_RE = re.compile(r"downConfirm\('([^']+)'\s*,\s*'(\d+)'")
TITLE_DATE_RE = re.compile(r"\((\d{1,2})월\s*(\d{1,2})일\)")
DAILY_KEYWORDS = ["AI 데일리", "AI데일리"]


def week_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """[start, end] 를 7일 단위로 분할 (검색 결과가 페이지 한계를 넘지 않게).

    카테고리 1521 검색 + curPage 페이지네이션은 ~11페이지에서 잘림. 페이지당 10건.
    1주일치 게시글은 ~30~50개라 1~5페이지 안에서 종료되어 누락 없음.
    """
    out = []
    cur = start
    while cur <= end:
        rng_end = min(cur + timedelta(days=6), end)
        out.append((cur, rng_end))
        cur = rng_end + timedelta(days=1)
    return out


def scrape_month(session: requests.Session, ms: date, me: date,
                 max_pages: int = 60) -> list[dict]:
    """특정 [ms, me] 월에 대해 검색 파라미터 + 페이지네이션.

    카테고리 단독 + curPage 는 11페이지에서 잘려 동작 안 함.
    검색 파라미터(searchStart*/End*)와 함께 쓸 때만 페이지네이션이 작동.

    종료 조건:
      - 페이지 행이 0개 (검색 결과 끝)
      - 페이지 행 < 10 (마지막 페이지)
    """
    items: list[dict] = []
    seen_attach: set[str] = set()
    for page in range(1, max_pages + 1):
        params = {
            "categoryId": CATEGORY_ID,
            "searchType": "2",
            "searchStartYear": str(ms.year),
            "searchStartMonth": f"{ms.month:02d}",
            "searchStartDay": f"{ms.day:02d}",
            "searchEndYear": str(me.year),
            "searchEndMonth": f"{me.month:02d}",
            "searchEndDay": f"{me.day:02d}",
            "curPage": str(page),
        }
        resp = session.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "lxml")
        tables = soup.find_all("table")
        if len(tables) < 2:
            break
        rows = tables[1].find_all("tr")[1:]
        if not rows:
            break

        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            row_date = tds[0].get_text(strip=True)
            title_a = tds[1].find("a")
            title = title_a.get_text(strip=True) if title_a else ""
            if not any(kw in title for kw in DAILY_KEYWORDS):
                continue
            down_a = tds[2].find("a", href=re.compile(r"downConfirm"))
            if not down_a:
                continue
            m = DOWNLOAD_RE.search(down_a["href"])
            if not m:
                continue
            pdf_url, attach_id = m.group(1), m.group(2)
            if attach_id in seen_attach:
                continue
            seen_attach.add(attach_id)
            items.append({
                "row_date": row_date,
                "title": title,
                "pdf_url": pdf_url,
                "attach_id": attach_id,
            })

        # 마지막 페이지 (검색 결과 < 10) 면 종료
        if len(rows) < 10:
            break
        time.sleep(0.15)
    return items


def infer_target_date(item: dict) -> date | None:
    """제목 한글 날짜 + row_date 연도로 target_date 추론."""
    m = TITLE_DATE_RE.search(item["title"])
    if not m:
        return None
    title_month = int(m.group(1))
    title_day = int(m.group(2))
    try:
        row_dt = datetime.strptime(item["row_date"], "%Y-%m-%d").date()
    except ValueError:
        return None
    year = row_dt.year
    # 1월 게시인데 제목이 11/12월 → 전년도
    if row_dt.month == 1 and title_month >= 11:
        year -= 1
    # 12월 게시인데 제목이 1월 → 다음해 (드물지만 가능)
    elif row_dt.month == 12 and title_month == 1:
        year += 1
    try:
        return date(year, title_month, title_day)
    except ValueError:
        return None


def list_existing_keys(s3_client) -> set[str]:
    keys: set[str] = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=f"{S3_PDF_PREFIX}/"):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def s3_key_for(target_date: date) -> str:
    return f"{S3_PDF_PREFIX}/{target_date.strftime('%Y-%m')}/{target_date}_briefing.pdf"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-01", help="시작일 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="종료일 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--dry-run", action="store_true", help="업로드 없이 목록만")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today()

    print(f"=== AI 데일리 브리핑 백필 ===")
    print(f"기간: {start} ~ {end}")
    print(f"S3:   s3://{S3_BUCKET}/{S3_PDF_PREFIX}/")
    print()

    # S3 기존 키 조회
    s3_client = None
    existing: set[str] = set()
    if not args.dry_run:
        s3_session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=S3_REGION,
        )
        s3_client = s3_session.client("s3")
        existing = list_existing_keys(s3_client)
        print(f"S3 기존 파일: {len(existing)}개")

    # 1) 주 단위 검색 + 페이지네이션 (페이지 한계 ~11 회피)
    session = requests.Session()
    all_items: list[dict] = []
    seen_attach: set[str] = set()
    weeks = week_ranges(start, end)
    for i, (ws, we) in enumerate(weeks, 1):
        items = scrape_month(session, ws, we)
        new_items = [it for it in items if it["attach_id"] not in seen_attach]
        for it in new_items:
            seen_attach.add(it["attach_id"])
        all_items.extend(new_items)
        if i % 4 == 0 or i == len(weeks):
            print(f"  [{i}/{len(weeks)}] {ws} ~ {we} 완료. 누적 {len(all_items)}건")
        time.sleep(0.15)
    print(f"\n총 발견: {len(all_items)}건")

    # 2) target_date 추론 + 중복 제거
    plan: list[tuple[date, dict, str]] = []
    skip_no_date = 0
    seen_target: set[date] = set()
    for it in all_items:
        td = infer_target_date(it)
        if td is None:
            skip_no_date += 1
            continue
        if td < start or td > end:
            continue
        if td in seen_target:
            continue
        seen_target.add(td)
        plan.append((td, it, s3_key_for(td)))

    plan.sort(key=lambda x: x[0])
    if skip_no_date:
        print(f"⚠ 제목에서 날짜 추출 실패: {skip_no_date}건 스킵")
    print(f"고유 일자: {len(plan)}건\n")

    if args.dry_run:
        for td, it, key in plan:
            mark = "EXISTS" if key in existing else "NEW"
            print(f"[{mark}] {td} | {it['title'][:55]} | attachId={it['attach_id']}")
        new_count = sum(1 for _, _, k in plan if k not in existing)
        print(f"\n[DRY-RUN] 신규 업로드 대상: {new_count}건")
        return

    # 3) 다운로드 + 업로드
    uploaded = 0
    skipped = 0
    failed = 0
    with tempfile.TemporaryDirectory(prefix="briefing_backfill_") as tmpdir:
        for i, (td, it, key) in enumerate(plan, 1):
            if key in existing:
                skipped += 1
                continue
            try:
                resp = requests.get(it["pdf_url"], headers=HEADERS, timeout=60)
                resp.raise_for_status()
                if len(resp.content) < 500:
                    print(f"  [{i}/{len(plan)}] {td} 빈 응답 → 실패")
                    failed += 1
                    continue
                tmp = Path(tmpdir) / f"{td}_briefing.pdf"
                tmp.write_bytes(resp.content)
                s3_client.upload_file(
                    str(tmp), S3_BUCKET, key,
                    ExtraArgs={"ContentType": "application/pdf"},
                )
                size_kb = len(resp.content) / 1024
                print(f"  [{i}/{len(plan)}] {td} ↑ {size_kb:.0f}KB  ({it['title'][:40]})")
                uploaded += 1
                tmp.unlink(missing_ok=True)
                time.sleep(0.25)
            except Exception as e:
                print(f"  [{i}/{len(plan)}] {td} 실패: {e}")
                failed += 1

    print(f"\n=== 완료 ===")
    print(f"  업로드: {uploaded}")
    print(f"  스킵(이미 있음): {skipped}")
    print(f"  실패: {failed}")


if __name__ == "__main__":
    main()
