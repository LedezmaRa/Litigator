import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.agent.investor import generate_investment_memo

data = [
    {"ticker": "AAPL", "sector": "XLK", "price": 150.0, "composite_score": 85.0, "rank_in_sector": 1, "relative_strength_3m": 5.0, "trend": "UP", "regime": "BULL", "signal_strength": "STRONG", "adx_momentum": 40.0, "atr_volatility": 3.0},
    {"ticker": "MSFT", "sector": "XLK", "price": 300.0, "composite_score": 80.0, "rank_in_sector": 2, "relative_strength_3m": 4.0, "trend": "UP", "regime": "BULL", "signal_strength": "STRONG", "adx_momentum": 35.0, "atr_volatility": 5.0}
]

generate_investment_memo(data, "reports")
