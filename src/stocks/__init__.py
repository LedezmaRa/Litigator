"""
Stock Narrative Page Module.

Provides fundamental data fetching and HTML page generation
for individual stock narrative pages.
"""
from .fundamentals import (
    fetch_stock_fundamentals,
    StockFundamentals,
    ExecutiveInfo,
    AnalystRatings,
    UpgradeDowngrade,
    NewsItem,
    EarningsInfo,
)
from .narrative import (
    generate_stock_narrative_page,
    generate_all_stock_pages,
)

__all__ = [
    'fetch_stock_fundamentals',
    'StockFundamentals',
    'ExecutiveInfo',
    'AnalystRatings',
    'UpgradeDowngrade',
    'NewsItem',
    'EarningsInfo',
    'generate_stock_narrative_page',
    'generate_all_stock_pages',
]
