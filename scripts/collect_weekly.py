"""주간 보고서 수집 러너 — 매주 일요일 19:30 KST 실행.

1. 미래에셋증권 상세분석 보고서 (collect_securities_reports.py)
2. MVP PRISM 보고서 (collect_prism_reports.py)
3. 주간 리서치 다이제스트 (generate_securities_digest.py)
4. Securities Index 재생성 (generate_securities_index.py) — pre-signed URL 7일 갱신
5. Fund Index 재생성 (generate_fund_index.py) — pre-signed URL 7일 갱신
6. Research Index 갱신 (_update_sc_index) — digest 새 URL을 research/index.html에 반영
7. Git push — 갱신된 파일 자동 배포

주의: 테마 리서치(generate_research.py)는 일간으로 전환되어 auto_market.py에서 실행.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from _utils import telegram_send

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PYTHON = sys.executable
KST = ZoneInfo("Asia/Seoul")

COLLECTORS = [
    ("미래에셋증권 상세분석", "collect_securities_reports.py"),
    ("MVP PRISM", "collect_prism_reports.py"),
    ("주간 리서치 다이제스트", "generate_securities_digest.py"),
    ("Securities Index 재생성", "generate_securities_index.py"),
    ("Fund Index 재생성", "generate_fund_index.py"),
]


def _send_telegram(text: str) -> None:
    telegram_send(text, parse_mode="HTML")


def main() -> None:
    start_dt = datetime.now(KST)
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S KST")

    print("=" * 52)
    print("  주간 보고서 수집")
    print(f"  시작: {start_str}")
    print("=" * 52)

    results: list[tuple[str, bool, str]] = []  # (label, ok, summary)

    for label, script in COLLECTORS:
        print(f"\n[{label}]")
        try:
            result = subprocess.run(
                [PYTHON, str(ROOT / "scripts" / script)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=600,
            )
            print(result.stdout[-3000:])
            if result.stderr:
                print(result.stderr[-500:])
            ok = result.returncode == 0
            if not ok:
                print(f"  [WARN] {label} exit {result.returncode}")
            # 업로드/스킵 숫자 추출 (요약용)
            summary = ""
            for line in result.stdout.splitlines():
                if "업로드" in line or "완료" in line:
                    summary = line.strip()
                    break
            results.append((label, ok, summary))
        except Exception as e:
            print(f"  [ERROR] {label}: {e}")
            results.append((label, False, str(e)))

    # research/index.html 갱신 — digest 새 URL 반영
    print("\n[Research Index 갱신]")
    try:
        sys.path.insert(0, str(ROOT))
        from generate_sector_country import _update_sc_index
        _update_sc_index()
        print("  ✓ research/index.html 갱신 완료")
        results.append(("Research Index 갱신", True, ""))
    except Exception as e:
        print(f"  [ERROR] research/index.html 갱신 실패: {e}")
        results.append(("Research Index 갱신", False, str(e)))

    # git push — 갱신된 파일 자동 배포
    print("\n[Git Push]")
    try:
        subprocess.run(
            ["git", "add",
             "output/research/index.html",
             "output/research/securities/",
             "output/fund/index.html"],
            cwd=str(ROOT), check=True, capture_output=True
        )
        commit_result = subprocess.run(
            ["git", "commit", "-m",
             f"chore: 주간 수집 완료 — research/securities/fund 갱신 ({start_dt.strftime('%Y-%m-%d')})"],
            cwd=str(ROOT), capture_output=True, text=True
        )
        if commit_result.returncode == 0:
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=str(ROOT), check=True, capture_output=True
            )
            print("  ✓ git push 완료")
            results.append(("Git Push", True, ""))
        else:
            print("  ⊘ 변경사항 없음 (push 스킵)")
            results.append(("Git Push", True, "변경사항 없음"))
    except Exception as e:
        print(f"  [ERROR] git push 실패: {e}")
        results.append(("Git Push", False, str(e)))

    end_dt = datetime.now(KST)
    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S KST")
    elapsed = int((end_dt - start_dt).total_seconds())

    print(f"\n완료. (종료: {end_str}, 소요: {elapsed}s)")

    # 텔레그램 알림
    all_ok = all(ok for _, ok, _ in results)
    status_icon = "✅" if all_ok else "⚠️"
    lines = [
        f"{status_icon} <b>주간 보고서 수집 {'완료' if all_ok else '일부 실패'}</b>",
        f"🕐 시작: {start_str}",
        f"🕑 종료: {end_str}  ({elapsed}s)",
        "",
    ]
    for label, ok, summary in results:
        icon = "✅" if ok else "❌"
        lines.append(f"{icon} {label}" + (f"  {summary}" if summary else ""))
    _send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
