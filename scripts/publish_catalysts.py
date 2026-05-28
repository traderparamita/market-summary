"""completed.jsonl ledger publisher — market-summary → Avalon hook4 권위 소스.

Usage:
    # stdin (JSON array)
    echo '[{"date":"2026-05-27",...}]' | .venv/bin/python scripts/publish_catalysts.py

    # CLI argument
    .venv/bin/python scripts/publish_catalysts.py --data '[{"date":"2026-05-27",...}]'

    # dry-run (로컬 파일만, S3 업로드 스킵)
    .venv/bin/python scripts/publish_catalysts.py --data '...' --dry-run

Exit: 0 = 성공, 1 = 실패 (경고 후 계속 진행해도 됨)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# --- 경로 설정 ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_LEDGER = REPO_ROOT / "output" / "catalysts" / "completed.jsonl"
S3_KEY = "anthillia/catalysts/completed.jsonl"

REQUIRED_FIELDS = {"date", "type", "session", "name", "source", "logged_at"}
VALID_TYPES = {"earnings", "macro", "fomc", "ipo", "other"}
VALID_SESSIONS = {"pre_open", "regular", "after_close", "scheduled"}


# --- 유효성 검사 --------------------------------------------------------------

def _validate(entry: dict) -> None:
    missing = REQUIRED_FIELDS - entry.keys()
    if missing:
        raise ValueError(f"필수 필드 누락: {missing}")
    if entry["type"] not in VALID_TYPES:
        raise ValueError(f"type 값 오류: {entry['type']!r} (허용: {VALID_TYPES})")
    if entry["session"] not in VALID_SESSIONS:
        raise ValueError(f"session 값 오류: {entry['session']!r} (허용: {VALID_SESSIONS})")


# --- 로컬 append --------------------------------------------------------------

def _append_local(entries: list[dict]) -> int:
    LOCAL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL_LEDGER.open("ab") as f:
        for entry in entries:
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            f.write(line.encode("utf-8"))
    return len(entries)


# --- S3 append-only (download → append → upload) -----------------------------

def _append_s3(entries: list[dict]) -> bool:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("[publish_catalysts] ⚠ boto3 미설치 — S3 업로드 스킵", file=sys.stderr)
        return False

    # 환경변수: S3_BUCKET_NAME (기존) 또는 KOSMOS_S3_BUCKET (신규)
    bucket = os.environ.get("KOSMOS_S3_BUCKET") or os.environ.get("S3_BUCKET_NAME")
    if not bucket:
        print("[publish_catalysts] ⚠ S3_BUCKET_NAME / KOSMOS_S3_BUCKET 미설정 — S3 업로드 스킵", file=sys.stderr)
        return False

    region = os.environ.get("AWS_REGION", "ap-northeast-2")
    s3 = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )

    # 기존 파일 다운로드 (없으면 빈 상태)
    existing_content = b""
    try:
        resp = s3.get_object(Bucket=bucket, Key=S3_KEY)
        existing_content = resp["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("NoSuchKey", "404"):
            print(f"[publish_catalysts] ⚠ S3 get 실패: {e}", file=sys.stderr)
            return False

    # append
    new_lines = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    updated = existing_content + new_lines.encode("utf-8")

    # re-upload
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl") as tmp:
        tmp.write(updated)
        tmp_path = tmp.name
    try:
        s3.upload_file(
            tmp_path, bucket, S3_KEY,
            ExtraArgs={"ContentType": "application/x-ndjson"},
        )
    finally:
        os.unlink(tmp_path)

    print(f"[publish_catalysts] ✓ S3 업로드 완료: s3://{bucket}/{S3_KEY} (+{len(entries)}건)", file=sys.stderr)
    return True


# --- git sha 조회 (source 필드용) --------------------------------------------

def _git_sha() -> str:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# --- 메인 --------------------------------------------------------------------

def publish(raw_data: str, dry_run: bool = False) -> int:
    try:
        entries = json.loads(raw_data)
    except json.JSONDecodeError as e:
        print(f"[publish_catalysts] ❌ JSON 파싱 실패: {e}", file=sys.stderr)
        return 1

    if isinstance(entries, dict):
        entries = [entries]

    if not isinstance(entries, list) or len(entries) == 0:
        print("[publish_catalysts] ⚠ 발행할 catalyst 없음 — 스킵", file=sys.stderr)
        return 0

    sha = _git_sha()
    now_iso = datetime.now(timezone.utc).astimezone(
        timezone(datetime.now(timezone.utc).astimezone().utcoffset())
    ).isoformat(timespec="seconds")

    processed: list[dict] = []
    for entry in entries:
        # source / logged_at 자동 주입 (미설정 시)
        if not entry.get("source"):
            entry["source"] = f"market-summary@{sha}"
        if not entry.get("logged_at"):
            entry["logged_at"] = now_iso

        try:
            _validate(entry)
        except ValueError as e:
            print(f"[publish_catalysts] ❌ 검증 실패: {e} — entry={entry}", file=sys.stderr)
            return 1

        processed.append(entry)

    # 로컬 append
    n = _append_local(processed)
    print(f"[publish_catalysts] ✓ 로컬 append: {LOCAL_LEDGER} (+{n}건)", file=sys.stderr)

    if dry_run:
        print("[publish_catalysts] ⊘ dry-run — S3 스킵", file=sys.stderr)
        return 0

    # S3 append (실패해도 exit 0 — 로컬 성공이면 OK)
    _append_s3(processed)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="completed.jsonl ledger publisher")
    parser.add_argument("--data", help="JSON array string (생략 시 stdin)")
    parser.add_argument("--dry-run", action="store_true", help="로컬만, S3 스킵")
    args = parser.parse_args()

    if args.data:
        raw = args.data
    else:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()
        if not raw:
            print("[publish_catalysts] ⚠ 입력 없음 — 스킵", file=sys.stderr)
            sys.exit(0)

    sys.exit(publish(raw, dry_run=args.dry_run))


if __name__ == "__main__":
    # .env 로드 (프로젝트 루트의 .env)
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            pass
    main()
