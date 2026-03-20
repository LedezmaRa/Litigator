"""
Shared scoring utilities for the EMA-ADX-ATR Framework.

Provides reusable functions for volume scoring used by both:
- src/scoring.py (Entry scoring)
- src/sectors/scoring.py (Composite scoring)
"""
from ..config import (
    VOLUME_REL_THRESHOLDS,
    VOLUME_REL_SCORES,
    VOLUME_TREND_RISING_THRESHOLD,
    VOLUME_TREND_STABLE_THRESHOLD,
    VOLUME_TREND_SCORES,
    VOLUME_UD_THRESHOLDS,
    VOLUME_UD_SCORES,
)


def calculate_relative_volume_score(rel_vol: float) -> float:
    """
    Calculate score based on relative volume ratio.

    Args:
        rel_vol: Current volume / average volume ratio

    Returns:
        Score (0-10 range for entry scoring)
    """
    if rel_vol is None or rel_vol < 0:
        return 0.0

    for i, threshold in enumerate(VOLUME_REL_THRESHOLDS):
        if rel_vol >= threshold:
            return float(VOLUME_REL_SCORES[i])
    return float(VOLUME_REL_SCORES[-1])


def calculate_volume_trend_score(trend_val: float) -> float:
    """
    Calculate score based on volume trend direction.

    Args:
        trend_val: Volume trend slope value

    Returns:
        Score (0-5 range)
    """
    if trend_val is None:
        return 0.0

    if trend_val > VOLUME_TREND_RISING_THRESHOLD:
        return float(VOLUME_TREND_SCORES['rising'])
    elif trend_val > VOLUME_TREND_STABLE_THRESHOLD:
        return float(VOLUME_TREND_SCORES['stable'])
    return float(VOLUME_TREND_SCORES['falling'])


def calculate_ud_ratio_score(ud_ratio: float) -> float:
    """
    Calculate score based on up/down volume ratio.

    Args:
        ud_ratio: Up volume / down volume ratio

    Returns:
        Score (0-5 range)
    """
    if ud_ratio is None or ud_ratio < 0:
        return 0.0

    for i, threshold in enumerate(VOLUME_UD_THRESHOLDS):
        if ud_ratio >= threshold:
            return float(VOLUME_UD_SCORES[i])
    return float(VOLUME_UD_SCORES[-1])


def calculate_composite_volume_score(
    rel_vol: float,
    trend_val: float = 0.0,
    ud_ratio: float = 1.0
) -> float:
    """
    Calculate full volume conviction score (0-20 points).

    Used by core scoring engine (src/scoring.py).

    Args:
        rel_vol: Current volume / average volume ratio
        trend_val: Volume trend slope value
        ud_ratio: Up volume / down volume ratio

    Returns:
        Composite score (0-20 range)
    """
    return (
        calculate_relative_volume_score(rel_vol) +
        calculate_volume_trend_score(trend_val) +
        calculate_ud_ratio_score(ud_ratio)
    )


def calculate_simple_volume_score(volume_ratio: float) -> float:
    """
    Calculate simple volume score (0-100 scale).

    Used by sector ranking (src/sectors/scoring.py).

    Args:
        volume_ratio: Current volume / average volume ratio

    Returns:
        Score on 0-100 scale
    """
    if volume_ratio is None:
        return 40.0

    if volume_ratio >= 1.5:
        return 100.0
    elif volume_ratio >= 1.0:
        return 70.0
    return 40.0
