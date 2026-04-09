"""
UI utilities for consistent styling across dashboards.

Provides:
  - Score → color / rating / badge helpers (used in all dashboards)
  - format_optional()  — safe display of values that may be None/NaN
  - format_date()      — consistent date formatting across all reports
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional, Union

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
        CSS class string (e.g., 'badge-optimal', 'badge-acceptable')
        Each rating maps 1-to-1 to a CSS class defined in CSS_DARK_THEME so
        badge text and badge colour always stay in sync.
    """
    rating = get_score_rating(score).lower()
    return f'badge-{rating}'


def get_status_badge_html(score: float, show_text: bool = True, tooltip: str = "") -> str:
    """
    Generate HTML badge for a score.

    Args:
        score:     Score value (0-100)
        show_text: If True show rating text; if False show the numeric score.
        tooltip:   Optional override for the title= attribute shown on hover.
                   When empty a default like "Score: 78 — Good (≥75)" is used.

    Returns:
        HTML string for badge element with a descriptive title= tooltip.
    """
    rating = get_score_rating(score)
    badge_class = get_score_badge_class(score)
    text = rating if show_text else f'{score:.0f}'

    _THRESHOLD_LABELS = {
        'Optimal':    f'\u226580 \u2014 top-tier setup',
        'Good':       f'\u226565 \u2014 strong setup',
        'Acceptable': f'\u226550 \u2014 moderate setup',
        'Marginal':   f'\u226535 \u2014 weak setup',
        'Poor':       f'<35 \u2014 avoid',
    }
    default_tooltip = f"Score: {score:.0f} \u2014 {rating} ({_THRESHOLD_LABELS.get(rating, '')})"
    title_attr = tooltip if tooltip else default_tooltip

    return f'<span class="badge {badge_class}" title="{title_attr}">{text}</span>'


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


# ---------------------------------------------------------------------------
# Data formatting helpers
# ---------------------------------------------------------------------------

def format_optional(
    value: object,
    fallback: str = "—",
    fmt: Optional[str] = None,
    precision: int = 2,
) -> str:
    """Safely format a value that may be None, NaN, or a missing sentinel.

    Returns *fallback* (default ``"—"``) when the value is not usable so
    the UI never renders raw "None" or "N/A" strings.

    Args:
        value:     The value to format.  Accepts int, float, str, or None.
        fallback:  String to return when value is absent/invalid.
        fmt:       Named format preset:
                     ``'pct'``      → ``"12.3%"``
                     ``'currency'`` → ``"$1,234.56"``
                     ``'int'``      → ``"42"``
                     ``None``       → generic float with *precision* decimals.
        precision: Decimal places used when fmt is None or ``'pct'``.

    Examples::

        format_optional(None)            # "—"
        format_optional(float('nan'))    # "—"
        format_optional(12.3, fmt='pct') # "12.3%"
        format_optional(1500, fmt='currency')  # "$1,500.00"
        format_optional(0, fmt='int')    # "0"  (zero is a valid value)
    """
    # Guard: None
    if value is None:
        return fallback
    # Guard: NaN / Inf floats
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return fallback
    # Guard: sentinel strings sometimes used when data is unavailable
    if isinstance(value, str) and value.strip().upper() in {"N/A", "NA", "NONE", ""}:
        return fallback

    try:
        v = float(value)
    except (TypeError, ValueError):
        # Non-numeric — return as-is (e.g. a label string that happens to be valid)
        return str(value)

    if fmt == 'pct':
        return f"{v:.{precision}f}%"
    if fmt == 'currency':
        return f"${v:,.{precision}f}"
    if fmt == 'int':
        return f"{int(round(v))}"
    return f"{v:.{precision}f}"


def format_date(
    dt: Union[datetime, date, str, None],
    fmt: str = "%b %d, %Y",
) -> str:
    """Normalise a date/datetime/ISO-string to a consistent display format.

    All date output in generated HTML should go through this function so the
    format is uniform across pages.

    Args:
        dt:  A ``datetime``, ``date``, ISO-8601 string (``"2025-01-15"``), or
             ``None``.
        fmt: ``strftime`` format string.  Default is ``"%b %d, %Y"``
             (e.g. ``"Jan 15, 2025"``).

    Returns:
        Formatted string, or ``"—"`` if input is None or unparseable.

    Examples::

        format_date(datetime(2025, 3, 31))        # "Mar 31, 2025"
        format_date("2025-03-31")                 # "Mar 31, 2025"
        format_date(None)                          # "—"
        format_date("2025-03-31", "%Y-%m-%d")     # "2025-03-31"
    """
    if dt is None:
        return "—"
    if isinstance(dt, datetime):
        return dt.strftime(fmt)
    if isinstance(dt, date):
        return dt.strftime(fmt)
    if isinstance(dt, str):
        dt = dt.strip()
        if not dt:
            return "—"
        # Try common ISO formats
        for iso_fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(dt, iso_fmt).strftime(fmt)
            except ValueError:
                continue
    return "—"
