"""
HTML templates for stock narrative page sections.

Uses glassmorphism dark theme consistent with existing dashboard.
All templates return HTML strings ready to embed in the page.
"""
from typing import Optional, List
from .fundamentals import (
    StockFundamentals, ExecutiveInfo, AnalystRatings,
    UpgradeDowngrade, NewsItem, EarningsInfo
)
from ..utils.ui_utils import format_date


def format_market_cap(value: Optional[float]) -> str:
    """Format market cap with B/T/M suffix."""
    if value is None:
        return "N/A"
    if value >= 1e12:
        return f"${value/1e12:.2f}T"
    elif value >= 1e9:
        return f"${value/1e9:.2f}B"
    elif value >= 1e6:
        return f"${value/1e6:.1f}M"
    else:
        return f"${value:,.0f}"


def format_revenue(value: Optional[float]) -> str:
    """Format revenue with B/M suffix."""
    if value is None:
        return "N/A"
    if value >= 1e9:
        return f"${value/1e9:.1f}B"
    elif value >= 1e6:
        return f"${value/1e6:.0f}M"
    else:
        return f"${value:,.0f}"


def format_percent(value: Optional[float], precision: int = 1, multiply: bool = True) -> str:
    """Format percentage with color coding."""
    if value is None:
        return "N/A"
    pct = value * 100 if multiply else value
    return f"{pct:.{precision}f}%"


def format_currency(value: Optional[float], precision: int = 2) -> str:
    """Format currency value."""
    if value is None:
        return "N/A"
    return f"${value:,.{precision}f}"


def format_number(value: Optional[float], precision: int = 2) -> str:
    """Format generic number."""
    if value is None:
        return "N/A"
    return f"{value:.{precision}f}"


def format_employees(value: Optional[int]) -> str:
    """Format employee count."""
    if value is None:
        return "N/A"
    if value >= 1000:
        return f"{value/1000:.0f}K"
    return f"{value:,}"


def format_compensation(value: Optional[float]) -> str:
    """Format executive compensation."""
    if value is None:
        return "N/A"
    if value >= 1e6:
        return f"${value/1e6:.1f}M"
    elif value >= 1e3:
        return f"${value/1e3:.0f}K"
    return f"${value:,.0f}"


def get_color_class(value: Optional[float], neutral: float = 0) -> str:
    """Get CSS color class based on value."""
    if value is None:
        return ""
    if value > neutral:
        return "text-positive"
    elif value < neutral:
        return "text-negative"
    return ""


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text with ellipsis."""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length].rsplit(' ', 1)[0] + "..."


def generate_overview_section(fundamentals: StockFundamentals) -> str:
    """
    Generate Company Overview section HTML.

    Includes:
    - Business summary
    - Website link
    - Employee count
    """
    summary = fundamentals.business_summary or "Company description not available."
    summary_display = truncate_text(summary, 600)

    website_link = ""
    if fundamentals.website:
        website_link = f'<a href="{fundamentals.website}" target="_blank" class="text-sm" style="color: var(--accent-info);">Visit Website</a>'

    employees = format_employees(fundamentals.employees)

    return f"""
    <section class="glass-card mb-3">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
            <h2 style="margin: 0;">Company Overview</h2>
            {website_link}
        </div>
        <p style="color: var(--text-secondary); line-height: 1.6; margin-bottom: 1rem;">{summary_display}</p>
        <div style="display: flex; gap: 2rem;">
            <div>
                <span class="text-xs text-muted">Employees</span><br>
                <b>{employees}</b>
            </div>
            <div>
                <span class="text-xs text-muted">Industry</span><br>
                <b>{fundamentals.industry or 'N/A'}</b>
            </div>
        </div>
    </section>
    """


def generate_leadership_section(executives: List[ExecutiveInfo]) -> str:
    """
    Generate Leadership section HTML.

    Shows top 5 executives with name, title, age, and compensation.
    """
    if not executives:
        return """
        <section class="glass-card">
            <h2>Leadership</h2>
            <p class="text-muted">Leadership information not available.</p>
        </section>
        """

    exec_cards = ""
    for exec in executives[:5]:
        age_display = f", Age {exec.age}" if exec.age else ""
        pay_display = f'<span class="text-xs text-muted">Compensation:</span> {format_compensation(exec.total_pay)}' if exec.total_pay else ""

        exec_cards += f"""
        <div style="padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 0.5rem; margin-bottom: 0.5rem;">
            <div style="font-weight: 600;">{exec.name}</div>
            <div class="text-sm text-muted">{exec.title}{age_display}</div>
            {pay_display}
        </div>
        """

    return f"""
    <section class="glass-card">
        <h2>Leadership</h2>
        {exec_cards}
    </section>
    """


def generate_metrics_section(fundamentals: StockFundamentals) -> str:
    """
    Generate Key Metrics section HTML.

    Organized into categories:
    - Valuation: Market Cap, P/E, Forward P/E, P/B
    - Growth: Revenue, Revenue Growth
    - Profitability: Gross/Operating/Net Margin, ROE
    - Risk: Beta, Debt/Equity
    """
    # Helper to create metric card
    def metric_card(label: str, value: str, color_class: str = "") -> str:
        return f"""
        <div class="metric-card">
            <span class="text-xs text-muted">{label}</span>
            <div class="text-lg font-bold {color_class}">{value}</div>
        </div>
        """

    # Valuation metrics
    valuation = f"""
    <div class="mb-3">
        <h3 class="text-sm text-muted" style="margin-bottom: 0.75rem;">Valuation</h3>
        <div class="metric-grid">
            {metric_card("Market Cap", format_market_cap(fundamentals.market_cap))}
            {metric_card("P/E Ratio", format_number(fundamentals.pe_ratio, 1))}
            {metric_card("Forward P/E", format_number(fundamentals.forward_pe, 1))}
            {metric_card("P/B Ratio", format_number(fundamentals.price_to_book, 1))}
            {metric_card("PEG Ratio", format_number(fundamentals.peg_ratio, 2))}
            {metric_card("EV", format_market_cap(fundamentals.enterprise_value))}
        </div>
    </div>
    """

    # Growth metrics
    rev_growth_class = get_color_class(fundamentals.revenue_growth)
    earn_growth_class = get_color_class(fundamentals.earnings_growth)

    growth = f"""
    <div class="mb-3">
        <h3 class="text-sm text-muted" style="margin-bottom: 0.75rem;">Growth</h3>
        <div class="metric-grid">
            {metric_card("Revenue", format_revenue(fundamentals.revenue))}
            {metric_card("Revenue Growth", format_percent(fundamentals.revenue_growth), rev_growth_class)}
            {metric_card("Earnings Growth", format_percent(fundamentals.earnings_growth), earn_growth_class)}
        </div>
    </div>
    """

    # Profitability metrics
    profitability = f"""
    <div class="mb-3">
        <h3 class="text-sm text-muted" style="margin-bottom: 0.75rem;">Profitability</h3>
        <div class="metric-grid">
            {metric_card("Gross Margin", format_percent(fundamentals.gross_margin))}
            {metric_card("Operating Margin", format_percent(fundamentals.operating_margin))}
            {metric_card("Net Margin", format_percent(fundamentals.profit_margin))}
            {metric_card("ROE", format_percent(fundamentals.roe))}
            {metric_card("ROA", format_percent(fundamentals.roa))}
        </div>
    </div>
    """

    # Risk & other metrics
    dividend = format_percent(fundamentals.dividend_yield) if fundamentals.dividend_yield else "N/A"
    risk = f"""
    <div>
        <h3 class="text-sm text-muted" style="margin-bottom: 0.75rem;">Risk & Other</h3>
        <div class="metric-grid">
            {metric_card("Beta", format_number(fundamentals.beta, 2))}
            {metric_card("Debt/Equity", format_number(fundamentals.debt_to_equity, 1))}
            {metric_card("Current Ratio", format_number(fundamentals.current_ratio, 2))}
            {metric_card("Dividend Yield", dividend)}
            {metric_card("52W High", format_currency(fundamentals.fifty_two_week_high))}
            {metric_card("52W Low", format_currency(fundamentals.fifty_two_week_low))}
        </div>
    </div>
    """

    return f"""
    <section class="glass-card mb-3">
        <h2>Key Metrics</h2>
        {valuation}
        {growth}
        {profitability}
        {risk}
    </section>
    """


def generate_analyst_section(
    ratings: Optional[AnalystRatings],
    actions: List[UpgradeDowngrade]
) -> str:
    """
    Generate Analyst Sentiment section HTML.

    Includes:
    - Buy/Hold/Sell distribution bar
    - Price target range
    - Recent upgrades/downgrades table
    """
    if not ratings and not actions:
        # Return empty string — caller skips rendering the section entirely.
        # An empty glass-card looks broken; a hidden section is cleaner.
        return ""

    # Ratings bar
    ratings_html = ""
    if ratings and ratings.total_analysts > 0:
        total = ratings.total_analysts
        buy_pct = ((ratings.strong_buy + ratings.buy) / total) * 100
        hold_pct = (ratings.hold / total) * 100
        sell_pct = ((ratings.sell + ratings.strong_sell) / total) * 100

        recommendation_badge = ""
        if ratings.recommendation:
            badge_class = "badge-optimal" if "buy" in ratings.recommendation.lower() else \
                         "badge-marginal" if "hold" in ratings.recommendation.lower() else "badge-poor"
            recommendation_badge = f'<span class="badge {badge_class}">{ratings.recommendation}</span>'

        ratings_html = f"""
        <div class="mb-3">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <span class="text-sm text-muted">Analyst Ratings ({total} analysts)</span>
                {recommendation_badge}
            </div>
            <div style="display: flex; height: 24px; border-radius: 4px; overflow: hidden;">
                <div style="width: {buy_pct:.1f}%; background: var(--accent-optimal);" title="Buy: {ratings.strong_buy + ratings.buy}"></div>
                <div style="width: {hold_pct:.1f}%; background: var(--accent-marginal);" title="Hold: {ratings.hold}"></div>
                <div style="width: {sell_pct:.1f}%; background: var(--accent-poor);" title="Sell: {ratings.sell + ratings.strong_sell}"></div>
            </div>
            <div style="display: flex; justify-content: space-between; margin-top: 0.5rem;">
                <span class="text-xs" style="color: var(--accent-optimal);">Buy {ratings.strong_buy + ratings.buy}</span>
                <span class="text-xs" style="color: var(--accent-marginal);">Hold {ratings.hold}</span>
                <span class="text-xs" style="color: var(--accent-poor);">Sell {ratings.sell + ratings.strong_sell}</span>
            </div>
        </div>
        """

    # Price targets
    targets_html = ""
    if ratings and ratings.target_mean:
        current = ratings.target_current or 0
        low = ratings.target_low or current
        high = ratings.target_high or current
        mean = ratings.target_mean

        # Calculate positions for visualization
        range_span = high - low if high > low else 1
        current_pct = ((current - low) / range_span) * 100 if current else 50
        mean_pct = ((mean - low) / range_span) * 100

        upside = ((mean - current) / current * 100) if current else 0
        upside_color = "var(--accent-optimal)" if upside > 0 else "var(--accent-poor)"

        targets_html = f"""
        <div class="mb-3">
            <h4 class="text-sm text-muted mb-1">Price Targets</h4>
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="font-mono text-sm">${low:.0f}</span>
                <div style="flex: 1; margin: 0 1rem; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; position: relative;">
                    <div style="position: absolute; left: {current_pct:.0f}%; width: 3px; height: 16px; background: var(--accent-info); top: -4px;" title="Current: ${current:.2f}"></div>
                    <div style="position: absolute; left: {mean_pct:.0f}%; width: 3px; height: 12px; background: var(--accent-optimal); top: -2px;" title="Mean: ${mean:.2f}"></div>
                </div>
                <span class="font-mono text-sm">${high:.0f}</span>
            </div>
            <div style="display: flex; justify-content: center; gap: 2rem; margin-top: 0.75rem;">
                <div style="text-align: center;">
                    <span class="text-xs text-muted">Mean Target</span><br>
                    <span class="font-bold" style="color: var(--accent-optimal);">${mean:.2f}</span>
                </div>
                <div style="text-align: center;">
                    <span class="text-xs text-muted">Upside</span><br>
                    <span class="font-bold" style="color: {upside_color};">{upside:+.1f}%</span>
                </div>
            </div>
        </div>
        """

    # Upgrades/Downgrades table
    actions_html = ""
    if actions:
        rows = ""
        for action in actions[:8]:
            action_badge = ""
            if "upgrade" in action.action.lower():
                action_badge = '<span class="badge badge-optimal" style="font-size: 0.65rem;">Upgrade</span>'
            elif "downgrade" in action.action.lower():
                action_badge = '<span class="badge badge-poor" style="font-size: 0.65rem;">Downgrade</span>'
            else:
                action_badge = '<span class="badge badge-marginal" style="font-size: 0.65rem;">Reiterate</span>'

            rows += f"""
            <tr>
                <td class="text-xs">{format_date(action.date)}</td>
                <td class="text-sm">{action.firm[:20]}</td>
                <td>{action_badge}</td>
                <td class="text-sm">{action.to_grade}</td>
            </tr>
            """

        actions_html = f"""
        <div>
            <h4 class="text-sm text-muted mb-1">Recent Analyst Actions</h4>
            <table class="modern-table" style="font-size: 0.8rem;">
                <thead>
                    <tr><th>Date</th><th>Firm</th><th>Action</th><th>Rating</th></tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        """

    return f"""
    <section class="glass-card">
        <h2>Analyst Sentiment</h2>
        {ratings_html}
        {targets_html}
        {actions_html}
    </section>
    """


def generate_catalysts_section(
    earnings: Optional[EarningsInfo],
    news: List[NewsItem]
) -> str:
    """
    Generate Catalysts section HTML.

    Includes:
    - Next earnings date with countdown
    - EPS/Revenue estimates
    - Recent news articles
    """
    # Earnings section
    earnings_html = ""
    if earnings and earnings.next_date:
        days_text = ""
        if earnings.days_until is not None:
            if earnings.days_until < 0:
                days_text = '<span class="badge badge-marginal">Past</span>'
            elif earnings.days_until == 0:
                days_text = '<span class="badge badge-optimal">Today</span>'
            elif earnings.days_until <= 7:
                days_text = f'<span class="badge badge-optimal">{earnings.days_until} days away</span>'
            else:
                days_text = f'<span class="text-sm text-muted">{earnings.days_until} days away</span>'

        eps_display = f"${earnings.eps_estimate:.2f}" if earnings.eps_estimate else "N/A"
        rev_display = format_revenue(earnings.revenue_estimate)

        earnings_html = f"""
        <div>
            <h3 class="text-sm text-muted mb-2">Next Earnings</h3>
            <div class="glass-card" style="background: rgba(56, 189, 248, 0.1); border-color: rgba(56, 189, 248, 0.2);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-size: 1.25rem; font-weight: bold;">{format_date(earnings.next_date)}</div>
                    {days_text}
                </div>
                <div style="margin-top: 1rem; display: flex; gap: 2rem;">
                    <div>
                        <span class="text-xs text-muted">EPS Estimate</span><br>
                        <b>{eps_display}</b>
                    </div>
                    <div>
                        <span class="text-xs text-muted">Revenue Estimate</span><br>
                        <b>{rev_display}</b>
                    </div>
                </div>
            </div>
        </div>
        """
    else:
        earnings_html = """
        <div>
            <h3 class="text-sm text-muted mb-2">Next Earnings</h3>
            <div class="glass-card" style="background: rgba(255,255,255,0.03);">
                <p class="text-muted">Earnings date not available</p>
            </div>
        </div>
        """

    # News section
    news_html = ""
    if news:
        news_items = ""
        for article in news[:5]:
            news_items += f"""
            <div style="padding: 0.75rem 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                <a href="{article.link}" target="_blank" style="color: var(--text-primary); text-decoration: none;">
                    <div style="font-weight: 500; margin-bottom: 0.25rem;">{truncate_text(article.title, 80)}</div>
                </a>
                <div class="text-xs text-muted">{article.publisher} · {format_date(article.published)}</div>
            </div>
            """

        news_html = f"""
        <div>
            <h3 class="text-sm text-muted mb-2">Recent News</h3>
            <div>{news_items}</div>
        </div>
        """
    else:
        news_html = """
        <div>
            <h3 class="text-sm text-muted mb-2">Recent News</h3>
            <p class="text-muted">No recent news available.</p>
        </div>
        """

    return f"""
    <section class="glass-card mb-4">
        <h2>Upcoming Catalysts</h2>
        <div class="grid-cols-2" style="gap: 2rem;">
            {earnings_html}
            {news_html}
        </div>
    </section>
    """


def generate_technical_section(
    current_price: Optional[float],
    composite_score: Optional[float],
    entry_score: Optional[float],
    trend: Optional[str],
    sector_etf: str
) -> str:
    """
    Generate Technical Context section HTML.

    Includes:
    - Current price
    - Composite score from sector analysis
    - Entry score
    - Trend status
    - Link back to sector charts
    """
    # Price display
    price_display = f"${current_price:.2f}" if current_price else "N/A"

    # Score colors
    def get_score_color(score: Optional[float]) -> str:
        if score is None:
            return "var(--text-secondary)"
        if score >= 70:
            return "var(--accent-optimal)"
        elif score >= 50:
            return "var(--accent-good)"
        elif score >= 30:
            return "var(--accent-marginal)"
        return "var(--accent-poor)"

    composite_color = get_score_color(composite_score)
    entry_color = get_score_color(entry_score)

    composite_display = f"{composite_score:.0f}" if composite_score else "N/A"
    entry_display = f"{entry_score:.0f}" if entry_score else "N/A"

    # Trend badge
    trend_badge = ""
    if trend:
        trend_lower = trend.lower()
        badge_class = "badge-optimal" if "accelerating" in trend_lower else \
                     "badge-good" if "steady" in trend_lower else \
                     "badge-marginal" if "decelerating" in trend_lower else "badge-poor"
        trend_badge = f'<span class="badge {badge_class}">{trend}</span>'
    else:
        trend_badge = '<span class="badge badge-marginal">Unknown</span>'

    return f"""
    <section class="glass-card">
        <h2>Technical Context</h2>
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
            <div style="display: flex; gap: 2rem; flex-wrap: wrap;">
                <div>
                    <span class="text-xs text-muted">Current Price</span>
                    <div style="font-size: 1.5rem; font-weight: bold;">{price_display}</div>
                </div>
                <div>
                    <span class="text-xs text-muted">Composite Score</span>
                    <div style="font-size: 1.5rem; font-weight: bold; color: {composite_color};">{composite_display}</div>
                </div>
                <div>
                    <span class="text-xs text-muted">Entry Score</span>
                    <div style="font-size: 1.5rem; font-weight: bold; color: {entry_color};">{entry_display}</div>
                </div>
                <div>
                    <span class="text-xs text-muted">Trend</span>
                    <div style="margin-top: 0.25rem;">{trend_badge}</div>
                </div>
            </div>
            <a href="sector_{sector_etf}.html" class="filter-btn" style="text-decoration: none;">
                View Full Chart in Sector Dashboard
            </a>
        </div>
    </section>
    """
