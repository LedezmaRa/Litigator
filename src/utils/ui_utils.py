"""
UI utilities for consistent styling across dashboards.

Provides unified score-to-color mapping and badge generation
used by both src/dashboard.py and src/sectors/dashboard.py.
"""
from ..config import SCORE_RATING_THRESHOLDS


# CSS variable names for theme colors
COLORS = {
    'optimal': 'var(--accent-optimal)',
    'good': 'var(--accent-good)',
    'marginal': 'var(--accent-marginal)',
    'poor': 'var(--accent-poor)',
    'info': 'var(--accent-info)',
    'primary': 'var(--text-primary)',
    'secondary': 'var(--text-secondary)',
}


def get_score_color(score: float, include_primary: bool = False) -> str:
    """
    Get CSS color variable for a given score.

    Args:
        score: Score value (0-100)
        include_primary: If True, returns 'primary' color for mid-range scores

    Returns:
        CSS variable string (e.g., 'var(--accent-optimal)')
    """
    if score is None:
        return COLORS['poor']

    if score >= SCORE_RATING_THRESHOLDS['optimal']:
        return COLORS['optimal']
    elif score >= SCORE_RATING_THRESHOLDS['good']:
        return COLORS['good']
    elif score >= SCORE_RATING_THRESHOLDS['acceptable']:
        return COLORS['primary'] if include_primary else COLORS['marginal']
    elif score >= SCORE_RATING_THRESHOLDS['marginal']:
        return COLORS['marginal']
    return COLORS['poor']


def get_score_rating(score: float) -> str:
    """
    Get rating text for a score.

    Args:
        score: Score value (0-100)

    Returns:
        Rating string (e.g., 'Optimal', 'Good', 'Acceptable', 'Marginal', 'Poor')
    """
    if score is None:
        return 'Poor'

    if score >= SCORE_RATING_THRESHOLDS['optimal']:
        return 'Optimal'
    elif score >= SCORE_RATING_THRESHOLDS['good']:
        return 'Good'
    elif score >= SCORE_RATING_THRESHOLDS['acceptable']:
        return 'Acceptable'
    elif score >= SCORE_RATING_THRESHOLDS['marginal']:
        return 'Marginal'
    return 'Poor'


def get_score_badge_class(score: float) -> str:
    """
    Get CSS badge class for a score.

    Args:
        score: Score value (0-100)

    Returns:
        CSS class string (e.g., 'badge-optimal')
    """
    rating = get_score_rating(score).lower()
    if rating == 'acceptable':
        rating = 'marginal'  # Map to existing CSS class
    return f'badge-{rating}'


def get_status_badge_html(score: float, show_text: bool = True) -> str:
    """
    Generate HTML badge for a score.

    Args:
        score: Score value (0-100)
        show_text: Whether to show rating text in badge

    Returns:
        HTML string for badge element
    """
    rating = get_score_rating(score)
    badge_class = get_score_badge_class(score)
    text = rating if show_text else f'{score:.0f}'
    return f'<span class="badge {badge_class}">{text}</span>'


def get_percent_bar_color(pct: float) -> str:
    """
    Get color for percentage-based progress bars.

    Args:
        pct: Percentage value (0-100)

    Returns:
        CSS variable string
    """
    if pct is None:
        return COLORS['poor']

    if pct >= 60:
        return COLORS['optimal']
    elif pct >= 40:
        return COLORS['marginal']
    return COLORS['poor']


def format_score_cell(score: float, label: str = '') -> str:
    """
    Format a score for table cell display with color.

    Args:
        score: Score value
        label: Optional sublabel text

    Returns:
        HTML string for table cell content
    """
    color = get_score_color(score)
    label_html = f'<br><span class="text-xs text-muted">{label}</span>' if label else ''
    return f'<span style="color:{color};"><b>{score:.0f}</b></span>{label_html}'
