"""4-pair variant — 경제축 4쌍만 사용 (IT·FIN·ENERGY·STAPLES).

기존 sector_rs_sync + sector_rs_fx 로직 재사용.
SECTOR_PAIRS 를 monkey-patch 로 4쌍 버전으로 교체한 뒤 동일 sweep 실행.

경제축 매핑:
  IT      ↔ 성장 / Duration   (금리 민감 장기자산)
  FIN     ↔ 가치 / Curve      (예대마진, 크레딧 사이클)
  ENERGY  ↔ 커머디티 / 인플레 (유가, 인플레 헤지)
  STAPLES ↔ 방어 / Consumer   (저베타, 배당)

Usage:
    python -m portfolio.strategy.sector_rs_4pairs --date 2026-04-21
"""

from __future__ import annotations

from pathlib import Path

# 1) Monkey-patch SECTOR_PAIRS BEFORE 하위 로직 호출
import portfolio.strategy.sector_rs.sector_rs_sync as _sync
import portfolio.strategy.sector_rs.sector_rs_fx as _fx

PAIRS_4 = [
    ("IX_KR_IT",      "SC_US_TECH",    "IT / Tech"),
    ("IX_KR_FIN",     "SC_US_FIN",     "금융 / Financials"),
    ("IX_KR_ENERGY",  "SC_US_ENERGY",  "에너지 / Energy"),
    ("IX_KR_STAPLES", "SC_US_STAPLES", "생활소비재 / ConsStap"),
]

_sync.SECTOR_PAIRS = PAIRS_4
_fx.SECTOR_PAIRS   = PAIRS_4
_fx.PAIR_LABELS    = ["IT", "FIN", "ENERGY", "STAPLES"]
_fx.PAIR_EXPORT_EXPOSURE = {
    "IT": 1.0, "FIN": 0.0, "ENERGY": 0.4, "STAPLES": 0.1,
}
_fx.MIN_PAIRS = 3  # 4쌍 중 최소 3쌍 확보 시 시그널 생성

# 2) Output dir 분리
ROOT = Path(__file__).resolve().parents[2]
_fx.OUTPUT_DIR = ROOT / "output" / "portfolio" / "strategy" / "rs_fx_4pairs"


def main() -> None:
    # 경제축 4쌍 + FX sweep 전체 실행 (기존 main 로직)
    _fx.main()


if __name__ == "__main__":
    main()
