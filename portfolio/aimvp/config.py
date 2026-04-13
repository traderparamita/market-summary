# Faber TAA config — ported from market-strategy/riskon/config.py
# indicator_code mappings for market_data.csv

STOCK_CODE = "EQ_MSCI_ACWI"   # ACWI ETF (iShares MSCI ACWI)
BOND_CODE  = "BD_AGG"          # AGG ETF (iShares US Aggregate Bond)
CASH_CODE  = "BD_US_2Y"        # BIL proxy via 2Y yield
VIX_CODE   = "RK_VIX"

TREND_WINDOW      = 10   # months
MOMENTUM_WINDOW   = 12   # months
VIX_LOW           = 20   # VIX <= this -> Risk-ON (+1)
VIX_HIGH          = 30   # VIX >= this -> Risk-OFF (-1)

RISK_ON_THRESHOLD  =  1
RISK_OFF_THRESHOLD = -1

# 3-asset allocation: (stock, bond, cash)
ALLOC_RISK_ON  = (0.90, 0.00, 0.10)
ALLOC_NEUTRAL  = (0.75, 0.15, 0.10)
ALLOC_RISK_OFF = (0.60, 0.25, 0.15)

TRANSACTION_COST = 0.003  # 30bp
