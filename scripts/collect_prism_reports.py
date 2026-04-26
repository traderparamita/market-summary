"""MVP PRISM 보고서를 S3에 수집.

https://miraeassetmvp.imweb.me/db 에서 PDF 다운로드 가능한 게시글을
스캔하여, S3에 없는 파일만 다운로드 후 업로드.

마지막 스캔 페이지 ID를 logs/prism_last_page.txt에 저장하여
다음 실행 시 그 이후부터만 스캔. --full 로 전체 재스캔 가능.

Target: s3://<BUCKET>/prism/<카테고리>/<YYYY>/<MM>/<filename>.pdf

Usage:
    .venv/bin/python scripts/collect_prism_reports.py            # 증분 스캔
    .venv/bin/python scripts/collect_prism_reports.py --full     # 전체 재스캔 (200~)
    .venv/bin/python scripts/collect_prism_reports.py --dry-run  # 업로드 없이 테스트
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import boto3
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

S3_BUCKET = "mai-life-fund-documents-533370893966-ap-northeast-2-an"
S3_PREFIX = "prism"
S3_REGION = "ap-northeast-2"

BASE_URL = "https://miraeassetmvp.imweb.me"
FULL_START = 200
SCAN_AHEAD = 50
STATE_FILE = ROOT / "logs" / "prism_last_page.txt"

CATEGORY_MAP = {
    "주간시황": "주간시황",
    "국내외_금융시장": "월간전망",
    "엔비디아_GTC": "INSIGHT/기타/00",
    "미국_이란": "INSIGHT/기타/00",
    "변액펀드": "주요변액펀드성과리뷰",
    "펀드성과": "주요변액펀드성과리뷰",
    "MVP": "MVP_LETTER",
}

DATE_RE = re.compile(r"(\d{8})")
FUND_PERIOD_RE = re.compile(r"_(\d{4})\.pdf$")


def classify(filename: str) -> tuple[str, str, str]:
    """파일명 → (카테고리, 연도, 월) 분류."""
    for prefix, category in CATEGORY_MAP.items():
        if prefix in filename:
            date_m = DATE_RE.search(filename)
            if date_m:
                d = date_m.group(1)
                return category, d[:4], d[4:6]
            period_m = FUND_PERIOD_RE.search(filename)
            if period_m:
                code = period_m.group(1)
                yy, mm = code[:2], code[2:]
                return category, f"20{yy}", mm
            return category, "0000", "00"
    return "기타", "0000", "00"


def load_last_page() -> int:
    """마지막 스캔 페이지 ID 로드. 없으면 FULL_START."""
    if STATE_FILE.exists():
        try:
            return int(STATE_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return FULL_START


def save_last_page(page_id: int) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(str(page_id))


def get_existing_keys(s3_client) -> set[str]:
    keys: set[str] = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + "/"):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def existing_filenames(keys: set[str]) -> set[str]:
    return {k.rsplit("/", 1)[-1] for k in keys}


def scan_page(page_id: int) -> dict | None:
    """게시글에서 다운로드 토큰 추출 (curl). PDF 없으면 None."""
    cookie_file = f"/tmp/imweb_prism_{page_id}.txt"
    try:
        r = subprocess.run(
            ["curl", "-s", "-b", "", "-c", cookie_file,
             f"{BASE_URL}/{page_id}"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return None
    except Exception:
        return None

    tk_match = re.search(r"/?download\.cm\?tk=([^\"'&\s]+)", r.stdout)
    if not tk_match:
        return None

    return {
        "page_id": page_id,
        "dl_path": f"/download.cm?tk={tk_match.group(1)}",
        "cookie_file": cookie_file,
    }


def get_filename_and_download(info: dict, dest: Path) -> str | None:
    """curl로 PDF 다운로드 + Content-Disposition에서 파일명 추출."""
    header_file = f"/tmp/imweb_prism_headers_{info['page_id']}.txt"
    try:
        r = subprocess.run(
            ["curl", "-s",
             "-b", info["cookie_file"],
             "-L",
             "-D", header_file,
             "-o", str(dest),
             f"{BASE_URL}{info['dl_path']}"],
            capture_output=True, timeout=60,
        )
        if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 500:
            return None
        with open(header_file, encoding="utf-8", errors="replace") as f:
            headers = f.read()
        m = re.search(r'filename="([^"]+)"', headers)
        return m.group(1) if m else None
    except Exception:
        return None


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids = [os.getenv("TELEGRAM_CHAT_ID"), os.getenv("ANTHILLIA_CHAT_ID")]
    if not token:
        return
    for chat_id in chat_ids:
        if not chat_id:
            continue
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="MVP PRISM 보고서 S3 수집")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full", action="store_true",
                        help="전체 재스캔 (200번부터)")
    args = parser.parse_args()

    if args.full:
        start_page = FULL_START
    else:
        start_page = load_last_page()

    print("=== MVP PRISM 보고서 수집 ===")
    print(f"S3: s3://{S3_BUCKET}/{S3_PREFIX}/")
    print(f"스캔 범위: {start_page}~\n")

    s3_client = None
    existing_names: set[str] = set()
    if not args.dry_run:
        s3_session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=S3_REGION,
        )
        s3_client = s3_session.client("s3")
        existing_keys = get_existing_keys(s3_client)
        existing_names = existing_filenames(existing_keys)
        print(f"S3 기존 파일: {len(existing_keys)}개\n")

    uploaded = 0
    skipped = 0
    failed = 0
    consecutive_miss = 0
    max_hit_page = start_page

    with tempfile.TemporaryDirectory(prefix="prism_") as tmpdir:
        for page_id in range(start_page, start_page + 500):
            info = scan_page(page_id)
            if not info:
                consecutive_miss += 1
                if consecutive_miss > SCAN_AHEAD:
                    break
                continue
            consecutive_miss = 0
            max_hit_page = page_id

            local_path = Path(tmpdir) / f"{page_id}.pdf"
            filename = get_filename_and_download(info, local_path)
            if not filename:
                continue

            if filename in existing_names:
                skipped += 1
                local_path.unlink(missing_ok=True)
                continue

            category, year, month = classify(filename)
            s3_key = f"{S3_PREFIX}/{category}/{year}/{month}/{filename}"
            size_kb = local_path.stat().st_size / 1024

            print(f"  [{page_id}] {filename[:70]}...", end=" ")

            if args.dry_run:
                print(f"[DRY-RUN] → {s3_key} ({size_kb:.0f}KB)")
                uploaded += 1
            else:
                try:
                    s3_client.upload_file(
                        str(local_path), S3_BUCKET, s3_key,
                        ExtraArgs={"ContentType": "application/pdf"},
                    )
                    uploaded += 1
                    print(f"OK ({size_kb:.0f}KB)")
                except Exception as e:
                    failed += 1
                    print(f"UPLOAD FAIL: {e}")

            existing_names.add(filename)
            local_path.unlink(missing_ok=True)
            time.sleep(0.3)

    if not args.dry_run:
        save_last_page(max_hit_page)

    print(f"\n완료: 업로드 {uploaded} / 스킵 {skipped} / 실패 {failed}")
    print(f"다음 스캔 시작: {max_hit_page}")

    if not args.dry_run and uploaded > 0:
        try:
            from generate_prism_index import main as regen_index
            print("\n인덱스 페이지 재생성...")
            regen_index()
        except Exception as e:
            print(f"  WARN: 인덱스 재생성 실패: {e}")

        send_telegram(
            f"📚 <b>MVP PRISM 보고서 수집 완료</b>\n"
            f"업로드: {uploaded}건 / 스킵: {skipped}건 / 실패: {failed}건"
        )


if __name__ == "__main__":
    main()
