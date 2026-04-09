"""
Basket Renderer — HTML generation for the market diagnostic panel.

Produces three insertable HTML fragments for generate_index():
    render_regime_summary_bar()  — sticky strip below the top-nav
    render_basket_cards_section() — collapsible 2-column basket grid
    render_basket_card()          — individual basket card (called by above)
    render_ticker_mini_row()      — one ticker row inside a basket card

Design constraints:
  - Returns plain HTML strings; no I/O, no network calls.
  - All CSS classes are defined in html_utils.CSS_DARK_THEME.
  - Dynamic colors (score tiers) use get_score_color() from ui_utils.
  - Never crashes on missing data — every field has a safe fallback.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .basket_engine import BasketSignal, OverallRegime
from .utils.ui_utils import get_score_color


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def render_regime_summary_bar(overall_regime: OverallRegime,
                               basket_signals: Dict[str, BasketSignal],
                               basket_order: Optional[List[str]] = None) -> str:
    """
    Render the sticky regime bar that sits below the top-nav.

    Shows:
      Left  — "Market Regime" label + verdict + key insight
      Middle — bullish/neutral/bearish count badges
      Right  — one pill per basket with a colored dot
    """
    r = overall_regime

    # Count badges
    count_html = (
        f'<span class="badge badge-optimal" style="font-size:0.65rem;">'
        f'{r.bullish_count} Bullish</span>'
        f'<span class="badge badge-marginal" style="font-size:0.65rem;">'
        f'{r.neutral_count} Neutral</span>'
        f'<span class="badge badge-poor" style="font-size:0.65rem;">'
        f'{r.bearish_count} Bearish</span>'
    )

    # Basket pills — one per basket in config order
    order = basket_order or list(basket_signals.keys())
    pills_html = ""
    for bid in order:
        if bid not in basket_signals:
            continue
        bs = basket_signals[bid]
        dot_color = bs.signal_color
        warning = " ⚠" if bs.low_coverage else ""
        pills_html += (
            f'<span class="regime-pill" title="{_esc(bs.macro_question)}">'
            f'<span class="pill-dot" style="background:{dot_color};"></span>'
            f'{_esc(bs.name)}{warning}'
            f'</span>'
        )

    return f"""
<div class="regime-bar" role="banner" aria-label="Market regime summary">
    <div class="regime-left">
        <span class="regime-label">Market Regime</span>
        <span class="regime-verdict" style="color:{r.verdict_color};">{_esc(r.verdict_label)}</span>
        <span class="regime-insight">{_esc(r.key_insight)}</span>
    </div>
    <div class="regime-counts">
        {count_html}
    </div>
    <div class="regime-pills">
        {pills_html}
    </div>
</div>"""


def render_basket_cards_section(basket_signals: Dict[str, BasketSignal],
                                 basket_order: Optional[List[str]] = None) -> str:
    """
    Render the collapsible section containing all basket cards in a 2-column grid.
    """
    order = basket_order or list(basket_signals.keys())
    cards_html = "".join(
        render_basket_card(basket_signals[bid])
        for bid in order
        if bid in basket_signals
    )

    return f"""
<details class="basket-section mb-4" open>
    <summary class="basket-section-header">
        <div>
            <span class="font-600">Macro Basket Diagnostics</span>
            <span class="text-xs text-muted" style="margin-left:0.75rem;">
                {len(basket_signals)} baskets · click to collapse
            </span>
        </div>
        <span class="basket-section-toggle">▾</span>
    </summary>
    <div class="basket-grid">
        {cards_html}
    </div>
</details>"""


def render_basket_card(bs: BasketSignal) -> str:
    """
    Render a single basket card.

    Structure (top to bottom):
      1. Header row: basket name + macro question + signal badge
      2. Three-metric stat row: Avg Score / Avg ADX / % > EMA20
      3. Divider
      4. Ticker rows (covered tickers)
      5. Placeholder row (no data case)
      6. Missing-tickers footnote
    """
    # ── Header ────────────────────────────────────────────────────────────────
    low_cov_warning = (
        '<span class="text-xs text-muted" title="Fewer than 2 tickers analyzed">'
        ' ⚠ low coverage</span>'
        if bs.low_coverage else ""
    )

    header_html = f"""
        <div class="flex-between mb-1">
            <div>
                <div class="font-600" style="font-size:0.9rem;">{_esc(bs.name)}{low_cov_warning}</div>
                <div class="text-xs text-muted" style="margin-top:2px; line-height:1.4;">
                    {_esc(bs.macro_question)}
                </div>
            </div>
            <span class="badge {bs.signal_badge_class}" style="flex-shrink:0; margin-left:0.75rem;">
                {bs.signal}
            </span>
        </div>"""

    # ── Stat row ──────────────────────────────────────────────────────────────
    score_color = get_score_color(bs.avg_score)
    breadth_color = (
        "var(--accent-optimal)" if bs.pct_above_ema20 >= 0.5
        else "var(--accent-poor)"
    )
    adx_color = (
        "var(--accent-optimal)" if bs.avg_adx >= 25
        else "var(--text-secondary)"
    )

    stat_row_html = f"""
        <div class="basket-meta-row">
            <div class="basket-meta-item">
                <span class="basket-meta-label">Avg Score</span>
                <span class="basket-meta-value" style="color:{score_color};">
                    {bs.avg_score:.0f}
                </span>
            </div>
            <div class="basket-meta-item">
                <span class="basket-meta-label">Avg ADX</span>
                <span class="basket-meta-value" style="color:{adx_color};">
                    {bs.avg_adx:.1f}
                </span>
            </div>
            <div class="basket-meta-item">
                <span class="basket-meta-label">% &gt; EMA20</span>
                <span class="basket-meta-value" style="color:{breadth_color};">
                    {bs.pct_above_ema20 * 100:.0f}%
                </span>
            </div>
            <div class="basket-meta-item">
                <span class="basket-meta-label">Coverage</span>
                <span class="basket-meta-value" style="color:var(--text-secondary);">
                    {bs.ticker_count}/{bs.ticker_count + len(bs.missing_tickers)}
                </span>
            </div>
        </div>"""

    # ── Ticker rows ───────────────────────────────────────────────────────────
    if bs.ticker_details:
        # Sort by score descending within the card
        sorted_details = sorted(
            bs.ticker_details, key=lambda r: _safe_float(r.get("score")), reverse=True
        )
        ticker_rows_html = "".join(
            render_ticker_mini_row(r) for r in sorted_details
        )
    else:
        ticker_rows_html = (
            '<div class="basket-no-data">No tickers analyzed for this basket</div>'
        )

    # ── Missing footnote ──────────────────────────────────────────────────────
    missing_html = ""
    if bs.missing_tickers:
        missing_html = (
            f'<div class="basket-missing">'
            f'Not analyzed: {", ".join(bs.missing_tickers)}'
            f'</div>'
        )

    return f"""
    <div class="basket-card {bs.signal_card_class}" data-basket="{_esc(bs.basket_id)}">
        {header_html}
        {stat_row_html}
        <hr class="basket-divider">
        {ticker_rows_html}
        {missing_html}
    </div>"""


def render_ticker_mini_row(report: dict) -> str:
    """
    Render one ticker row inside a basket card.

    Layout: [TICKER]  [score]  [WoW%]  [regime chip]  [→]
    The entire row is an anchor linking to the stock report page.
    """
    ticker  = _esc(report.get("ticker", "?"))
    score   = _safe_float(report.get("score"))
    wow_pct = _safe_float(report.get("price_change_pct"))
    regime  = str(report.get("regime") or report.get("trend") or "")

    score_color = get_score_color(score)
    wow_color   = "var(--accent-optimal)" if wow_pct >= 0 else "var(--accent-poor)"
    wow_sign    = "▲" if wow_pct >= 0 else "▼"
    regime_label = regime.replace("_", " ").replace("VOLATILITY", "VOL").title()[:12]

    return (
        f'<a href="stock_{ticker}.html" class="basket-ticker-row">'
        f'<span class="basket-ticker-symbol">{ticker}</span>'
        f'<span class="basket-ticker-score" style="color:{score_color};">{score:.0f}</span>'
        f'<span class="basket-ticker-chg" style="color:{wow_color};">'
        f'{wow_sign}{abs(wow_pct):.1f}%</span>'
        f'<span class="basket-ticker-regime">{_esc(regime_label)}</span>'
        f'<span style="color:var(--text-secondary); font-size:0.7rem;">→</span>'
        f'</a>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _esc(value: object) -> str:
    """HTML-escape any value for safe embedding in attributes and text."""
    from html import escape
    return escape(str(value)) if value is not None else ""


def _safe_float(value: object, default: float = 0.0) -> float:
    """Return float(value) or default on any error."""
    try:
        import math
        f = float(value)  # type: ignore[arg-type]
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default
