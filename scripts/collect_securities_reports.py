"""미래에셋증권 상세분석 보고서를 S3에 주간 수집.

매주 일요일 실행 — 직전 영업주(월~금)의 보고서 PDF를 스크래핑하여 S3 업로드.

Source: https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1521
Target: s3://<BUCKET>/anthillia/miraeasset-securities/YYYY-MM/<filename>.pdf

Usage:
    .venv/bin/python scripts/collect_securities_reports.py            # 직전 주
    .venv/bin/python scripts/collect_securities_reports.py --week-of 2026-04-21  # 특정 주
    .venv/bin/python scripts/collect_securities_reports.py --dry-run  # 실제 업로드 없이 테스트
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import boto3
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

S3_BUCKET = "mai-life-fund-documents-533370893966-ap-northeast-2-an"
S3_PREFIX = "anthillia/miraeasset-securities"
S3_REGION = "ap-northeast-2"

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
VIEW_RE = re.compile(r"view\('(\d+)'")


def get_week_range(ref_date: datetime | None = None) -> tuple[datetime, datetime]:
    """직전 영업주의 월~금 날짜 범위."""
    today = ref_date or datetime.now()
    # 일요일(6) 실행 기준 → 직전 금요일 = today - 2
    days_since_friday = (today.weekday() - 4) % 7 or 7
    friday = today - timedelta(days=days_since_friday)
    monday = friday - timedelta(days=4)
    return monday, friday


def scrape_page(session: requests.Session, start: datetime, end: datetime,
                page: int) -> list[dict]:
    """게시판 한 페이지에서 보고서 메타 추출."""
    params = {
        "categoryId": CATEGORY_ID,
        "searchType": "2",
        "searchStartYear": str(start.year),
        "searchStartMonth": f"{start.month:02d}",
        "searchStartDay": f"{start.day:02d}",
        "searchEndYear": str(end.year),
        "searchEndMonth": f"{end.month:02d}",
        "searchEndDay": f"{end.day:02d}",
        "curPage": str(page),
    }
    resp = session.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
    resp.encoding = "euc-kr"
    soup = BeautifulSoup(resp.text, "lxml")

    tables = soup.find_all("table")
    if len(tables) < 2:
        return []

    items = []
    for tr in tables[1].find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue

        date_str = tds[0].get_text(strip=True)
        title_a = tds[1].find("a", href=re.compile(r"javascript:view"))
        if not title_a:
            continue
        title = title_a.get_text(strip=True)
        msg_match = VIEW_RE.search(title_a["href"])
        msg_id = msg_match.group(1) if msg_match else ""

        down_a = tds[2].find("a", href=re.compile(r"downConfirm"))
        pdf_url = ""
        attach_id = ""
        if down_a:
            dl_match = DOWNLOAD_RE.search(down_a["href"])
            if dl_match:
                pdf_url = dl_match.group(1)
                attach_id = dl_match.group(2)

        author = tds[3].get_text(strip=True)

        if pdf_url:
            items.append({
                "date": date_str,
                "title": title,
                "msg_id": msg_id,
                "attach_id": attach_id,
                "pdf_url": pdf_url,
                "author": author,
            })
    return items


def scrape_all(session: requests.Session, start: datetime,
               end: datetime) -> list[dict]:
    """날짜 범위 전체 보고서 목록 수집."""
    all_items: list[dict] = []
    for page in range(1, 100):
        items = scrape_page(session, start, end, page)
        if not items:
            break
        all_items.extend(items)
        if len(items) < 10:
            break
        time.sleep(0.3)
    return all_items


def sanitize_filename(date_str: str, title: str, attach_id: str) -> str:
    """S3 키에 쓸 안전한 파일명 생성."""
    date_compact = date_str.replace("-", "")
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
    safe_title = re.sub(r"\s+", " ", safe_title).strip()
    if len(safe_title) > 80:
        safe_title = safe_title[:80].rstrip()
    return f"{date_compact}_{safe_title}_{attach_id}.pdf"


def download_pdf(session: requests.Session, pdf_url: str,
                 dest: Path) -> bool:
    """PDF 다운로드. 성공 시 True."""
    try:
        resp = session.get(pdf_url, headers=HEADERS, timeout=60, stream=True)
        if resp.status_code != 200:
            print(f"  WARN: HTTP {resp.status_code} for {pdf_url}")
            return False
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        if dest.stat().st_size < 100:
            dest.unlink()
            return False
        return True
    except Exception as e:
        print(f"  ERROR downloading: {e}")
        return False


def upload_to_s3(s3_client, local_path: Path, s3_key: str,
                 dry_run: bool = False) -> bool:
    """S3 업로드. dry_run이면 로그만."""
    if dry_run:
        print(f"  [DRY-RUN] Would upload → s3://{S3_BUCKET}/{s3_key}")
        return True
    try:
        s3_client.upload_file(
            Filename=str(local_path),
            Bucket=S3_BUCKET,
            Key=s3_key,
            ExtraArgs={
                "ContentType": "application/pdf",
                "CacheControl": "max-age=86400",
            },
        )
        return True
    except Exception as e:
        print(f"  ERROR uploading {s3_key}: {e}")
        return False


def get_existing_keys(s3_client, prefix: str) -> set[str]:
    """S3 prefix 아래 기존 키 목록."""
    keys: set[str] = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids = [
        os.getenv("TELEGRAM_CHAT_ID"),
        os.getenv("ANTHILLIA_CHAT_ID"),
    ]
    if not token:
        return
    for chat_id in chat_ids:
        if not chat_id:
            continue
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="미래에셋증권 보고서 S3 수집")
    parser.add_argument(
        "--week-of",
        help="수집 대상 주의 월요일 날짜 (YYYY-MM-DD). 생략 시 직전 주.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="S3 업로드 없이 스크래핑만 테스트",
    )
    args = parser.parse_args()

    if args.week_of:
        ref_monday = datetime.strptime(args.week_of, "%Y-%m-%d")
        start = ref_monday
        end = ref_monday + timedelta(days=4)
    else:
        start, end = get_week_range()

    print(f"=== 미래에셋증권 상세분석 보고서 수집 ===")
    print(f"기간: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    print(f"S3:   s3://{S3_BUCKET}/{S3_PREFIX}/")
    print()

    session = requests.Session()

    # 1) 보고서 목록 스크래핑
    print("[1/3] 게시판 스크래핑...")
    items = scrape_all(session, start, end)
    print(f"  → {len(items)}건 발견")
    if not items:
        print("수집 대상 없음. 종료.")
        return

    # 2) S3 기존 키 확인 (중복 방지)
    month_prefix = f"{S3_PREFIX}/{start.strftime('%Y-%m')}"
    s3_client = None
    existing_keys: set[str] = set()
    if not args.dry_run:
        s3_session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=S3_REGION,
        )
        s3_client = s3_session.client("s3")
        existing_keys = get_existing_keys(s3_client, month_prefix)
        print(f"  S3 기존 파일: {len(existing_keys)}개 ({month_prefix}/)")

    # 3) 다운로드 + 업로드
    print(f"\n[2/3] PDF 다운로드 + S3 업로드...")
    uploaded = 0
    skipped = 0
    failed = 0

    with tempfile.TemporaryDirectory(prefix="miraeasset_") as tmpdir:
        for i, item in enumerate(items, 1):
            filename = sanitize_filename(
                item["date"], item["title"], item["attach_id"]
            )
            month_str = item["date"][:7]  # YYYY-MM
            s3_key = f"{S3_PREFIX}/{month_str}/{filename}"

            if s3_key in existing_keys:
                skipped += 1
                continue

            local_path = Path(tmpdir) / filename
            print(f"  [{i}/{len(items)}] {filename[:60]}...", end=" ")

            if not download_pdf(session, item["pdf_url"], local_path):
                failed += 1
                print("FAIL")
                continue

            size_kb = local_path.stat().st_size / 1024
            if upload_to_s3(s3_client, local_path, s3_key, args.dry_run):
                uploaded += 1
                print(f"OK ({size_kb:.0f}KB)")
            else:
                failed += 1
                print("UPLOAD FAIL")

            local_path.unlink(missing_ok=True)
            time.sleep(0.2)

    # 4) 결과
    print(f"\n[3/3] 완료")
    print(f"  업로드: {uploaded}건")
    print(f"  스킵(중복): {skipped}건")
    print(f"  실패: {failed}건")

    if not args.dry_run and uploaded > 0:
        # 인덱스 페이지 재생성
        try:
            from generate_securities_index import main as regen_index
            print("\n[4/4] 인덱스 페이지 재생성...")
            regen_index()
        except Exception as e:
            print(f"  WARN: 인덱스 재생성 실패: {e}")

        week_label = f"{start.strftime('%m/%d')}~{end.strftime('%m/%d')}"
        msg = (
            f"<b>미래에셋증권 보고서 수집 완료</b>\n"
            f"기간: {week_label}\n"
            f"업로드: {uploaded}건 / 스킵: {skipped}건 / 실패: {failed}건\n"
            f"S3: {S3_PREFIX}/{start.strftime('%Y-%m')}/"
        )
        send_telegram(msg)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
