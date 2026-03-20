"""
Stock narrative page generator.

Creates individual HTML pages for each stock with fundamental data,
leadership information, analyst sentiment, and catalysts.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .fundamentals import fetch_stock_fundamentals, StockFundamentals
from .templates import (
    generate_overview_section,
    generate_leadership_section,
    generate_metrics_section,
    generate_analyst_section,
    generate_catalysts_section,
    generate_technical_section,
)

# Import shared theme and JS from main dashboard
from src.dashboard import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav


# Additional CSS for stock narrative pages
STOCK_PAGE_CSS = """
/* Stock Narrative Page Specific Styles */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.75rem;
}

.metric-card {
    background: rgba(30, 41, 59, 0.5);
    padding: 0.75rem;
    border-radius: 0.5rem;
    border: 1px solid rgba(255,255,255,0.05);
}

.text-positive { color: var(--accent-optimal); }
.text-negative { color: var(--accent-poor); }

.breadcrumb {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
}

.breadcrumb a {
    color: var(--text-secondary);
    text-decoration: none;
}

.breadcrumb a:hover {
    color: var(--text-primary);
}

.breadcrumb span {
    color: var(--text-secondary);
}

.hero-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 1rem;
}

@media (max-width: 768px) {
    .grid-cols-2 {
        grid-template-columns: 1fr !important;
    }
    .hero-header {
        flex-direction: column;
    }
    .metric-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}
"""


def generate_stock_narrative_page(
    ticker: str,
    sector_etf: str,
    sector_name: str,
    composite_score: Optional[float] = None,
    entry_score: Optional[float] = None,
    trend: Optional[str] = None,
    output_dir: str = "reports"
) -> str:
    """
    Generate a comprehensive narrative HTML page for a single stock.

    Args:
        ticker: Stock symbol
        sector_etf: Parent sector ETF (for navigation)
        sector_name: Human-readable sector name
        composite_score: Composite score from sector analysis
        entry_score: Entry score from trade candidate analysis
        trend: Trend classification string
        output_dir: Output directory for HTML files

    Returns:
        Path to generated HTML file
    """
    # Fetch fundamental data
    fundamentals = fetch_stock_fundamentals(ticker)

    # Get current price from fundamentals or use None
    current_price = fundamentals.current_price

    # Day change badge
    day_change_html = ""
    if fundamentals.day_change_pct is not None:
        change_color = "var(--accent-optimal)" if fundamentals.day_change_pct >= 0 else "var(--accent-poor)"
        change_sign = "+" if fundamentals.day_change_pct >= 0 else ""
        day_change_html = f'<span style="color: {change_color}; font-size: 1rem;">{change_sign}{fundamentals.day_change_pct:.2f}%</span>'

    # Price display
    price_display = f"${current_price:.2f}" if current_price else "N/A"

    # Generate sections
    overview_section = generate_overview_section(fundamentals)
    leadership_section = generate_leadership_section(fundamentals.executives)
    metrics_section = generate_metrics_section(fundamentals)
    analyst_section = generate_analyst_section(
        fundamentals.analyst_ratings,
        fundamentals.upgrades_downgrades
    )
    catalysts_section = generate_catalysts_section(
        fundamentals.earnings,
        fundamentals.news
    )
    technical_section = generate_technical_section(
        current_price,
        composite_score,
        entry_score,
        trend,
        sector_etf
    )

    # Build full HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{ticker} | {fundamentals.name} | Stock Analysis</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
            {CSS_DARK_THEME}
            {STOCK_PAGE_CSS}
        </style>
    </head>
    <body>
        {generate_top_nav("")}
        <div class="container">
            <!-- Breadcrumb Navigation -->
            <nav class="breadcrumb">
                <a href="sector_analysis.html">Sector Overview</a>
                <span>/</span>
                <a href="sector_{sector_etf}.html">{sector_name}</a>
                <span>/</span>
                <span style="color: var(--text-primary);">{ticker}</span>
            </nav>

            <!-- Hero Header -->
            <header class="glass-card" style="margin-bottom: 2rem;">
                <div class="hero-header">
                    <div>
                        <h1 style="margin-bottom: 0.5rem;">{fundamentals.name or ticker}</h1>
                        <div style="display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;">
                            <span class="text-xl font-mono">{ticker}</span>
                            <span class="badge badge-good">{fundamentals.sector or sector_name}</span>
                            <span class="text-muted">{fundamentals.industry or ''}</span>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 2rem; font-weight: bold;">{price_display}</div>
                        {day_change_html}
                    </div>
                </div>
            </header>

            <!-- Two-Column Layout -->
            <div class="grid-cols-2" style="display: grid; gap: 2rem; margin-bottom: 2rem;">
                <!-- Left Column: Company Story -->
                <div>
                    {overview_section}
                    {leadership_section}
                </div>

                <!-- Right Column: Metrics & Data -->
                <div>
                    {metrics_section}
                    {analyst_section}
                </div>
            </div>

            <!-- Catalysts Section (Full Width) -->
            {catalysts_section}

            <!-- Technical Context Section -->
            {technical_section}

            <!-- Footer -->
            <footer style="margin-top: 3rem; text-align: center; color: var(--text-secondary);">
                <p>Macro Watch 2.1 · Stock Narrative Page</p>
                <p class="text-xs">Fundamental data via yfinance · Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
            </footer>
        </div>
        {INTERACTIVE_JS}
    </body>
    </html>
    """

    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Write file
    out_path = os.path.join(output_dir, f"stock_{ticker}.html")
    with open(out_path, "w") as f:
        f.write(html)

    return out_path


def generate_all_stock_pages(
    ranked_sectors: Dict,
    sector_config: Dict,
    candidates_lookup: Optional[Dict] = None,
    output_dir: str = "reports",
    max_workers: int = 10
) -> List[str]:
    """
    Generate narrative pages for all stocks in ranked sectors.

    Args:
        ranked_sectors: Dict mapping ETF -> List[CompositeScore]
        sector_config: Dict with sector name mappings
        candidates_lookup: Optional dict mapping ticker -> TradeCandidateAnalysis
        output_dir: Output directory
        max_workers: Max parallel workers for fundamentals fetching

    Returns:
        List of generated file paths
    """
    # Build list of all stocks to process
    stocks_to_process = []

    for etf, ranked_stocks in ranked_sectors.items():
        sector_name = sector_config.get(etf, {}).get('name', etf)

        for stock in ranked_stocks:
            # Get candidate info if available
            candidate = candidates_lookup.get(stock.ticker) if candidates_lookup else None
            entry_score = candidate.entry_score if candidate else None
            regime = candidate.regime if candidate else None

            stocks_to_process.append({
                'ticker': stock.ticker,
                'sector_etf': etf,
                'sector_name': sector_name,
                'composite_score': stock.composite_score,
                'entry_score': entry_score,
                'trend': stock.trend if hasattr(stock, 'trend') else regime,
            })

    print(f"  Generating {len(stocks_to_process)} stock narrative pages...")

    # Generate pages in parallel
    generated_paths = []

    def generate_page(stock_info: Dict) -> Optional[str]:
        try:
            return generate_stock_narrative_page(
                ticker=stock_info['ticker'],
                sector_etf=stock_info['sector_etf'],
                sector_name=stock_info['sector_name'],
                composite_score=stock_info['composite_score'],
                entry_score=stock_info['entry_score'],
                trend=stock_info['trend'],
                output_dir=output_dir
            )
        except Exception as e:
            print(f"  Error generating page for {stock_info['ticker']}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_page, stock): stock['ticker']
            for stock in stocks_to_process
        }

        completed = 0
        for future in as_completed(futures):
            ticker = futures[future]
            completed += 1
            try:
                path = future.result()
                if path:
                    generated_paths.append(path)
            except Exception as e:
                print(f"  Failed {ticker}: {e}")

            # Progress indicator every 25 stocks
            if completed % 25 == 0:
                print(f"  Progress: {completed}/{len(stocks_to_process)} pages generated")

    print(f"  Completed: {len(generated_paths)} stock pages generated")
    return generated_paths
