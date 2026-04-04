"""
Composite Scoring Module for Macro Watch 2.0 (Integrated)

Calculates weighted composite scores for ranking stocks within their sectors.
Components:
- Relative Strength (50%): 3-month relative return vs sector ETF
- Trend Score (30%): Based on trend classification (Accelerating/Steady/etc.)
- Volume Score (20%): Based on volume ratio characteristics
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from enum import Enum

import pandas as pd
import numpy as np


class TrendType(Enum):
    ACCELERATING = "Accelerating"
    STEADY = "Steady"
    DECELERATING = "Decelerating"
    REVERSING = "Reversing"
    NA = "NA"


# Scoring weights
WEIGHT_RELATIVE_STRENGTH = 0.50
WEIGHT_TREND = 0.30
WEIGHT_VOLUME = 0.20

# Trend score mappings
TREND_SCORES = {
    TrendType.ACCELERATING: 100,
    TrendType.STEADY: 60,
    TrendType.DECELERATING: 30,
    TrendType.REVERSING: 10,
    TrendType.NA: 0,
}


@dataclass
class StockMetrics:
    """Raw metrics for a single stock."""
    ticker: str
    name: str
    sector: str
    sector_etf: str

    # Price data
    price: Optional[float] = None

    # Absolute returns
    ret_1w: Optional[float] = None
    ret_1m: Optional[float] = None
    ret_3m: Optional[float] = None

    # Relative returns (vs sector ETF)
    rel_1w: Optional[float] = None
    rel_1m: Optional[float] = None
    rel_3m: Optional[float] = None

    # Volume
    volume_ratio: float = 1.0

    # Trend classification
    trend: TrendType = TrendType.NA

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['trend'] = self.trend.value
        return d


@dataclass
class CompositeScore:
    """Composite score for ranking stocks within a sector."""
    ticker: str
    name: str
    sector: str
    sector_etf: str

    # Component scores (0-100 scale)
    relative_strength_score: float
    trend_score: float
    volume_score: float

    # Weighted composite
    composite_score: float

    # Ranking
    rank_in_sector: int = 0

    # Pass-through metrics for display
    price: Optional[float] = None
    ret_3m: Optional[float] = None
    rel_3m: Optional[float] = None
    trend: str = "NA"
    volume_ratio: float = 1.0

    def to_dict(self) -> Dict:
        return asdict(self)


def classify_trend(rel_1w: Optional[float], rel_1m: Optional[float], rel_3m: Optional[float]) -> TrendType:
    """
    Classify trend based on relative performance momentum.

    - Reversing: 1W and 3M have opposite signs
    - Accelerating: 1W > 1M > 3M (all improving)
    - Decelerating: 1W < 1M < 3M (all declining)
    - Steady: Otherwise
    """
    if rel_1w is None or rel_1m is None or rel_3m is None:
        return TrendType.NA

    # Check for reversal (opposite signs on 1W vs 3M)
    if (rel_1w > 0 and rel_3m < 0) or (rel_1w < 0 and rel_3m > 0):
        return TrendType.REVERSING

    # Check for acceleration (improving momentum)
    if rel_1w > rel_1m > rel_3m:
        return TrendType.ACCELERATING

    # Check for deceleration (declining momentum)
    if rel_1w < rel_1m < rel_3m:
        return TrendType.DECELERATING

    return TrendType.STEADY


def calculate_volume_score(volume_ratio: float) -> float:
    """
    Score volume characteristics using continuous piecewise-linear interpolation.

    Breakpoints: 0.5→20, 1.0→40, 1.5→70, 2.5→100 (capped at both ends).
    This gives proportional credit throughout the range instead of 3 hard buckets.
    """
    if volume_ratio is None or np.isnan(float(volume_ratio)):
        return 20.0
    xp = [0.5, 1.0, 1.5, 2.5]
    fp = [20.0, 40.0, 70.0, 100.0]
    return float(np.clip(np.interp(float(volume_ratio), xp, fp), 20.0, 100.0))


def calculate_relative_strength_percentile(
    ticker: str,
    rel_3m: Optional[float],
    all_rel_3m: Dict[str, Optional[float]]
) -> float:
    """
    Calculate percentile rank of a stock's relative strength within its cohort.

    Returns 0-100 score where 100 = best performer.
    """
    if rel_3m is None:
        return 0.0

    # Filter valid values
    valid_values = [v for v in all_rel_3m.values() if v is not None]

    if not valid_values:
        return 50.0  # Default to middle if no comparison

    # Count how many values are below this stock's value
    below_count = sum(1 for v in valid_values if v < rel_3m)

    # Percentile = (number below / total) * 100
    percentile = (below_count / len(valid_values)) * 100

    return percentile


def calculate_composite_score(
    metrics: StockMetrics,
    sector_rel_3m_values: Dict[str, Optional[float]]
) -> CompositeScore:
    """
    Calculate weighted composite score for a stock.

    Components:
    - Relative Strength (50%): Percentile rank within sector
    - Trend (30%): Based on trend classification
    - Volume (20%): Based on volume ratio
    """
    # Component 1: Relative strength percentile
    rs_score = calculate_relative_strength_percentile(
        metrics.ticker,
        metrics.rel_3m,
        sector_rel_3m_values
    )

    # Component 2: Trend score
    trend_score = float(TREND_SCORES.get(metrics.trend, 0))

    # Component 3: Volume score
    vol_score = calculate_volume_score(metrics.volume_ratio)

    # Weighted composite
    composite = (
        rs_score * WEIGHT_RELATIVE_STRENGTH +
        trend_score * WEIGHT_TREND +
        vol_score * WEIGHT_VOLUME
    )

    return CompositeScore(
        ticker=metrics.ticker,
        name=metrics.name,
        sector=metrics.sector,
        sector_etf=metrics.sector_etf,
        relative_strength_score=round(rs_score, 1),
        trend_score=round(trend_score, 1),
        volume_score=round(vol_score, 1),
        composite_score=round(composite, 1),
        price=metrics.price,
        ret_3m=metrics.ret_3m,
        rel_3m=metrics.rel_3m,
        trend=metrics.trend.value,
        volume_ratio=metrics.volume_ratio,
    )


def rank_stocks_in_sector(
    stocks: List[StockMetrics]
) -> List[CompositeScore]:
    """
    Rank all stocks within a sector by composite score.

    Returns list sorted by composite score (descending) with ranks assigned.
    """
    if not stocks:
        return []

    # Build dict of rel_3m values for percentile calculation
    rel_3m_values = {s.ticker: s.rel_3m for s in stocks}

    # Calculate composite scores
    scored = [calculate_composite_score(s, rel_3m_values) for s in stocks]

    # Sort by composite score descending
    scored.sort(key=lambda x: x.composite_score, reverse=True)

    # Assign ranks
    for i, score in enumerate(scored):
        score.rank_in_sector = i + 1

    return scored


def select_top_n(
    ranked_stocks: List[CompositeScore],
    n: int = 5
) -> List[CompositeScore]:
    """
    Select top N stocks from a ranked list.
    """
    return ranked_stocks[:n]


def rank_all_sectors(
    sector_stocks: Dict[str, List[StockMetrics]]
) -> Dict[str, List[CompositeScore]]:
    """
    Rank stocks within each sector.

    Args:
        sector_stocks: Dict mapping sector ETF -> list of StockMetrics

    Returns:
        Dict mapping sector ETF -> list of CompositeScore (sorted by rank)
    """
    result = {}

    for sector_etf, stocks in sector_stocks.items():
        result[sector_etf] = rank_stocks_in_sector(stocks)

    return result


def get_trade_candidates(
    ranked_sectors: Dict[str, List[CompositeScore]],
    top_n: int = 5
) -> List[CompositeScore]:
    """
    Extract top N stocks from each sector for Stage 2 analysis.

    Returns flat list of all trade candidates sorted by composite score.
    """
    candidates = []

    for sector_etf, ranked in ranked_sectors.items():
        candidates.extend(select_top_n(ranked, top_n))

    # Sort all candidates by composite score
    candidates.sort(key=lambda x: x.composite_score, reverse=True)

    return candidates


def build_stock_metrics(
    ticker: str,
    name: str,
    sector_name: str,
    sector_etf: str,
    all_closes: pd.DataFrame,
    data_map: Dict[str, pd.DataFrame]
) -> StockMetrics:
    """
    Construct a StockMetrics object from raw market data.
    """
    # 1. Get Stock Data
    if ticker not in data_map:
        return StockMetrics(ticker, name, sector_name, sector_etf)
    
    df = data_map[ticker]
    if df.empty:
        return StockMetrics(ticker, name, sector_name, sector_etf)
        
    current_price = df['close'].iloc[-1]
    
    # 2. Calculate Absolute Returns
    # 1W = 5 days, 1M = 21 days, 3M = 63 days
    def get_ret(series, days):
        if len(series) <= days: return None
        return (series.iloc[-1] / series.iloc[-1-days]) - 1
        
    ret_1w = get_ret(df['close'], 5)
    ret_1m = get_ret(df['close'], 21)
    ret_3m = get_ret(df['close'], 63)
    
    # 3. Calculate Relative Returns vs Sector ETF
    rel_1w, rel_1m, rel_3m = None, None, None
    
    if sector_etf in all_closes.columns:
        etf_closes = all_closes[sector_etf]
        
        etf_ret_1w = get_ret(etf_closes, 5)
        etf_ret_1m = get_ret(etf_closes, 21)
        etf_ret_3m = get_ret(etf_closes, 63)
        
        if ret_1w is not None and etf_ret_1w is not None: rel_1w = ret_1w - etf_ret_1w
        if ret_1m is not None and etf_ret_1m is not None: rel_1m = ret_1m - etf_ret_1m
        if ret_3m is not None and etf_ret_3m is not None: rel_3m = ret_3m - etf_ret_3m

    # 4. Classify Trend
    trend = classify_trend(rel_1w, rel_1m, rel_3m)
    
    # 5. Volume Ratio
    # Avg volume last 20 days
    vol_ratio = 1.0
    if len(df) >= 20:
        avg_vol = df['volume'].iloc[-21:-1].mean()
        curr_vol = df['volume'].iloc[-1]
        if avg_vol > 0:
            vol_ratio = curr_vol / avg_vol
            
    return StockMetrics(
        ticker=ticker,
        name=name,
        sector=sector_name,
        sector_etf=sector_etf,
        price=current_price,
        ret_1w=ret_1w,
        ret_1m=ret_1m,
        ret_3m=ret_3m,
        rel_1w=rel_1w,
        rel_1m=rel_1m,
        rel_3m=rel_3m,
        volume_ratio=vol_ratio,
        trend=trend
    )
