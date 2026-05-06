"""sector·country 보고서 카드(1M/3M/6M) 자동 정합성 검증.

대상: output/research/daily/YYYY-MM/YYYY-MM-DD.html
검증: TIGER 200 GICS 11개 + COUNTRY 카드 모멘텀 vs CSV 재계산
판정: |reported - recomputed| > tol → 위반

generate_sector_country.py 가 사용하는 views.sector_view.compute_sector_view 와
views.country_view.compute_country_view 를 그대로 호출해 동일 로직으로 비교한다.

Usage:
    .venv/bin/python scripts/verify_sector_country_cards.py            # 전체 검증
    .venv/bin/python scripts/verify_sector_country_cards.py --date 2026-04-29
    .venv/bin/python scripts/verify_sector_country_cards.py --year-month 2026-04
"""
from __future__ import annotations

import argparse
import glob
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from views.sector_view import compute_sector_view, KR_SECTORS, US_SECTORS
from views.country_view import compute_country_view, COUNTRIES

TOL_PP = 0.5  # 허용 오차(percentage point)

CARD_PATTERN = re.compile(
    r'<div class="sc-etf">([^<]+)</div>\s*'
    r'<div class="sc-metrics"[^>]*>\s*'
    r'<div class="sc-metric"><span class="mk">1개월</span>([^<]*<span[^>]*>[^<]+</span>[^<]*|[^<]+)</div>\s*'
    r'<div class="sc-metric"><span class="mk">3개월</span>([^<]*<span[^>]*>[^<]+</span>[^<]*|[^<]+)</div>\s*'
    r'<div class="sc-metric"><span class="mk">6개월</span>([^<]*<span[^>]*>[^<]+</span>[^<]*|[^<]+)</div>',
    re.DOTALL,
)
COUNTRY_CARD_PATTERN = re.compile(
    r'<span class="cc-name">([^<]+)</span>.*?'
    r'<div class="sc-metric"><span class="mk">3개월</span>([^<]*<span[^>]*>[^<]+</span>[^<]*|[^<]+)</div>\s*'
    r'<div class="sc-metric"><span class="mk">6개월</span>([^<]*<span[^>]*>[^<]+</span>[^<]*|[^<]+)</div>',
    re.DOTALL,
)
PCT_RX = re.compile(r'([+\-]?\d+(?:\.\d+)?)\s*%')


@dataclass
class CardViolation:
    file: str
    label: str
    period: str
    reported: float | None
    expected: float | None
    diff: str

    def fmt(self) -> str:
        rep = "N/A" if self.reported is None else f"{self.reported:+.2f}%"
        exp = "N/A" if self.expected is None else f"{self.expected:+.2f}%"
        return f"  ✗ {Path(self.file).name} :: {self.label} {self.period}  보고서:{rep}  실제:{exp}  Δ:{self.diff}"


def _parse_pct(s: str) -> float | None:
    """span 안의 N/A 또는 +N.NN% 추출."""
    if not s:
        return None
    if "N/A" in s or "—" in s:
        return None
    m = PCT_RX.search(s)
    if not m:
        return None
    return float(m.group(1))


def _build_sector_lookup(sv_data: dict) -> dict[str, dict]:
    """ETF 라벨 → {mom_1m, mom_3m, mom_6m}."""
    out: dict[str, dict] = {}
    for s in sv_data["us_sectors"]:
        out[s["etf"]] = s
    for s in sv_data["kr_sectors"]:
        out[s["etf"]] = s
    return out


def _build_country_lookup(cv_data: dict) -> dict[str, dict]:
    """국가명 → {mom_3m, mom_6m}."""
    return {c["name"]: c for c in cv_data["countries"]}


def verify_file(path: Path) -> list[CardViolation]:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if not m:
        return []
    date_str = m.group(1)
    text = path.read_text(errors="replace")

    sv = compute_sector_view(date_str)
    cv = compute_country_view(date_str)
    sec_lookup = _build_sector_lookup(sv)
    cty_lookup = _build_country_lookup(cv)

    violations: list[CardViolation] = []

    # Sector cards (sc-etf 라벨로 매칭)
    for cm in CARD_PATTERN.finditer(text):
        etf_line = cm.group(1).strip()
        # "TIGER 200 헬스케어 (227570.KS)" → "TIGER 200 헬스케어"
        etf_label = etf_line.split("(")[0].strip()
        # XLV ETF 라벨처럼 ETF 코드만 있는 경우는 US 섹터 lookup 에서 그대로 매칭
        sec = sec_lookup.get(etf_label)
        if sec is None:
            # US 섹터: "Technology" / "Health Care" 처럼 etf 필드가 ETF 코드 — 라벨이 다를 수 있음
            continue
        for period_key, group_idx in [("1M", 2), ("3M", 3), ("6M", 4)]:
            reported = _parse_pct(cm.group(group_idx))
            field = f"mom_{period_key.lower()}"
            expected_raw = sec.get(field)
            # NaN 처리
            try:
                expected = float(expected_raw) if expected_raw == expected_raw else None  # NaN check
            except (TypeError, ValueError):
                expected = None
            # 둘 다 None 이면 OK
            if reported is None and expected is None:
                continue
            # 한쪽만 None → 위반
            if reported is None or expected is None:
                violations.append(CardViolation(
                    file=str(path), label=etf_label, period=period_key,
                    reported=reported, expected=expected,
                    diff="없음" if reported is None else "N/A 누락",
                ))
                continue
            d = reported - expected
            if abs(d) > TOL_PP:
                violations.append(CardViolation(
                    file=str(path), label=etf_label, period=period_key,
                    reported=reported, expected=expected,
                    diff=f"{d:+.2f}pp",
                ))

    # Country cards (cc-name 라벨로 매칭)
    for cm in COUNTRY_CARD_PATTERN.finditer(text):
        cname = cm.group(1).strip()
        cty = cty_lookup.get(cname)
        if cty is None:
            continue
        for period_key, group_idx in [("3M", 2), ("6M", 3)]:
            reported = _parse_pct(cm.group(group_idx))
            field = f"mom_{period_key.lower()}"
            expected_raw = cty.get(field)
            try:
                expected = float(expected_raw) if expected_raw == expected_raw else None
            except (TypeError, ValueError):
                expected = None
            if reported is None and expected is None:
                continue
            if reported is None or expected is None:
                violations.append(CardViolation(
                    file=str(path), label=cname, period=period_key,
                    reported=reported, expected=expected,
                    diff="없음" if reported is None else "N/A 누락",
                ))
                continue
            d = reported - expected
            if abs(d) > TOL_PP:
                violations.append(CardViolation(
                    file=str(path), label=cname, period=period_key,
                    reported=reported, expected=expected,
                    diff=f"{d:+.2f}pp",
                ))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--year-month", help="YYYY-MM")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.date:
        files = list((ROOT / "output" / "research" / "daily" / args.date[:7]).glob(f"{args.date}.html"))
    elif args.year_month:
        files = sorted((ROOT / "output" / "research" / "daily" / args.year_month).glob("*.html"))
    else:
        files = sorted(glob.glob(str(ROOT / "output/research/daily/*/2*.html")))
        files = [Path(f) for f in files]
    files = [f for f in files if f.exists() and "_story" not in f.name]

    all_violations: list[CardViolation] = []
    for f in files:
        v = verify_file(f)
        all_violations.extend(v)

    if not all_violations:
        print(f"[verify-cards] ✓ 위반 없음 (대상 {len(files)}개 파일)")
        return 0

    print(f"[verify-cards] ✗ {len(all_violations)}건 위반 (대상 {len(files)}개 파일)")
    if not args.quiet:
        for v in all_violations:
            print(v.fmt())
    # 파일별 집계
    from collections import Counter
    by_file = Counter(Path(v.file).name for v in all_violations)
    print(f"\n파일별 위반 수 (Top 15):")
    for name, n in by_file.most_common(15):
        print(f"  {name}: {n}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
