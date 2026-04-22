"""Sector-based Asset Allocation Research.

질문: 한국과 미국에 어떻게 비중 배분을 해야 할까?

방법론:
  1. 대표 지수 대신 세분화된 GICS 섹터 + 환율 데이터 활용
  2. 섹터 조합 (전체 / 상관 기반 축소 / 경제축) × FX 가중 조합 실험
  3. 2011-04-01 KRX 섹터 지수 공식 출시일 이후로 백테스트

엔트리포인트:
  python -m portfolio.strategy.sector_asset_allocation.experiment
"""
