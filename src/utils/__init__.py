"""
Shared utilities for the EMA-ADX-ATR Framework.

Modules:
- scoring_utils: Shared scoring functions
- ui_utils: Score-to-color mapping and badge generation
"""

from .scoring_utils import (
    calculate_relative_volume_score,
    calculate_volume_trend_score,
    calculate_ud_ratio_score,
    calculate_composite_volume_score,
    calculate_simple_volume_score,
)

from .ui_utils import (
    get_score_color,
    get_score_rating,
    get_score_badge_class,
    get_status_badge_html,
    get_percent_bar_color,
    COLORS,
)

__all__ = [
    # Scoring utils
    'calculate_relative_volume_score',
    'calculate_volume_trend_score',
    'calculate_ud_ratio_score',
    'calculate_composite_volume_score',
    'calculate_simple_volume_score',
    # UI utils
    'get_score_color',
    'get_score_rating',
    'get_score_badge_class',
    'get_status_badge_html',
    'get_percent_bar_color',
    'COLORS',
]
