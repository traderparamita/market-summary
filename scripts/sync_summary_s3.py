"""scripts/sync_summary_s3.py — output/summary/ 변경분을 S3에 증분 업로드

git diff HEAD~1..HEAD 로 변경된 output/summary/ 파일만 업로드.
auto_market.py의 git push 성공 직후 호출된다.

Usage:
    python scripts/sync_summary_s3.py             # git diff 자동 감지
    python scripts/sync_summary_s3.py --all       # 전체 재업로드 (초기 세팅용)
    python scripts/sync_summary_s3.py 2026-06-02  # 특정 날짜 파일만
"""
from __future__ import annotations

import io
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import subprocess
from pathlib import Path

import boto3
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

import os
S3_BUCKET  = os.getenv("S3_BUCKET_NAME", "mai-life-fund-documents-533370893966-ap-northeast-2-an")
S3_PREFIX  = "market-summary"
S3_REGION  = "ap-northeast-2"
SUMMARY_DIR = ROOT / "output" / "summary"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript",
    ".json": "application/json",
    ".svg":  "image/svg+xml",
    ".png":  "image/png",
    ".ico":  "image/x-icon",
}


def _s3_key(local_path: Path) -> str:
    rel = local_path.relative_to(ROOT / "output")
    return S3_PREFIX + "/" + rel.as_posix()


def _upload(s3, files: list[Path]) -> tuple[int, int]:
    uploaded = errors = 0
    for f in files:
        if not f.exists():
            continue
        key = _s3_key(f)
        ct  = CONTENT_TYPES.get(f.suffix.lower(), "application/octet-stream")
        try:
            s3.upload_file(str(f), S3_BUCKET, key, ExtraArgs={"ContentType": ct})
            uploaded += 1
        except Exception as e:
            print(f"  [ERROR] {f.name}: {e}", file=sys.stderr)
            errors += 1
    return uploaded, errors


def files_from_git_diff() -> list[Path]:
    """직전 커밋 대비 변경된 output/summary/ 파일 목록."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=15,
        )
        paths = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("output/summary/"):
                p = ROOT / line
                if p.is_file():
                    paths.append(p)
        return paths
    except Exception as e:
        print(f"  [WARN] git diff 실패: {e}", file=sys.stderr)
        return []


def files_for_date(date_str: str) -> list[Path]:
    """특정 날짜 관련 파일 (일간 + index + 주간/월간 헤더)."""
    yyyy_mm = date_str[:7]
    day_dir = SUMMARY_DIR / yyyy_mm
    files = list(day_dir.glob(f"{date_str}*")) if day_dir.exists() else []
    # index.html, 주간/월간도 포함
    for extra in [
        SUMMARY_DIR / "index.html",
        SUMMARY_DIR / "weekly",
        SUMMARY_DIR / "monthly",
    ]:
        if extra.is_file():
            files.append(extra)
        elif extra.is_dir():
            files.extend(extra.glob("*.html"))
    return files


def files_all() -> list[Path]:
    return [f for f in SUMMARY_DIR.rglob("*") if f.is_file()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("date", nargs="?", help="YYYY-MM-DD (옵션)")
    parser.add_argument("--all", action="store_true", help="전체 재업로드")
    args = parser.parse_args()

    s3 = boto3.client("s3", region_name=S3_REGION)

    if args.all:
        files = files_all()
        mode  = "전체"
    elif args.date:
        files = files_for_date(args.date)
        mode  = f"{args.date} 날짜"
    else:
        files = files_from_git_diff()
        mode  = "git diff 변경분"

    if not files:
        print(f"[s3-sync] 업로드할 파일 없음 ({mode})")
        return 0

    print(f"[s3-sync] {mode} → S3 {S3_PREFIX}/ ({len(files)}개 파일)")
    uploaded, errors = _upload(s3, files)
    print(f"[s3-sync] 완료: {uploaded}개 업로드 / {errors}개 오류")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
