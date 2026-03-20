"""
Macro Drivers Dashboard Generator
Aggregates all sector drivers into a single high-level view with Cross-Sector Correlation Analysis and Economic Insights.
"""

import os
import pandas as pd
import numpy as np
from typing import Dict, List
from src.dashboard import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav
from src.sectors.charts import generate_detailed_driver_chart_svg
from src.sectors.drivers import DriverAnalysis

def generate_economic_insights_sidebar() -> str:
    """
    Generates the HTML for the Economic Insights sidebar.
    """
    return """
    <aside class="insights-sidebar">
        <div class="insight-card">
            <h3 style="color: #60a5fa; margin-top:0;">
                <span style="font-size:1.2em;">🎓</span> Economic Insights
            </h3>
            
            <div class="insight-item">
                <h4>🏭 Dr. Copper &amp; Industrials</h4>
                <p><strong>Copper (COPX)</strong> is the "Ph.D. of Economics." Rising copper signals strong demand for buildings and machines.</p>
                <div class="insight-stat">Positive Correlation (+0.80+)</div>
                <p class="insight-desc">Boosting <strong>Industrials (XLI)</strong> and <strong>Materials (XLB)</strong>.</p>
            </div>
            
            <div class="insight-item">
                <h4>🛢️ The "Oil Tax" on Consumers</h4>
                <p>Rising <strong>Oil (CL=F)</strong> acts like a tax, leaving less money for discretionary spending.</p>
                <div class="insight-stat negative">Negative Correlation (-0.40)</div>
                <p class="insight-desc">High oil hurts <strong>Consumer Discretionary (XLY)</strong> stocks (Retail, Autos).</p>
            </div>
            
            <div class="insight-item">
                <h4>📉 Yields vs. Tech &amp; Growth</h4>
                <p><strong>10Y Yields (^TNX)</strong> represent the risk-free rate. High rates hurt long-duration growth assets.</p>
                <div class="insight-stat negative">Inverse Relationship</div>
                <p class="insight-desc">When yields spike, <strong>Technology (XLK)</strong> and <strong>Comms (XLC)</strong> valuations compress.</p>
            </div>

            <div class="insight-item">
                <h4>🏦 Yield Curve &amp; Banks</h4>
                <p>Banks profit from the <em>spread</em> between short (^IRX) and long (^TNX) rates — a steeper curve = more profit.</p>
                <div class="insight-stat">Positive Correlation</div>
                <p class="insight-desc">Rising long rates generally lift <strong>Financials (XLF)</strong> via wider net interest margins.</p>
            </div>
            
            <div class="insight-item">
                <h4>🏠 Rates vs. REITs</h4>
                <p><strong>REITs (XLRE)</strong> are priced like bonds. When rates rise, their dividend yields look less attractive.</p>
                <div class="insight-stat negative">Strong Negative (-0.70+)</div>
                <p class="insight-desc">The <strong>^TNX → XLRE</strong> correlation is one of the most reliable in the market.</p>
            </div>

            <div class="insight-item">
                <h4>💊 Biotech as Risk Barometer</h4>
                <p><strong>Biotech (XBI)</strong> is the high-beta, speculative edge of Health Care. It leads the sector in risk-on/off moves.</p>
                <div class="insight-stat">Leading Indicator</div>
                <p class="insight-desc">When XBI rallies, broader <strong>Health Care (XLV)</strong> often follows with a lag.</p>
            </div>

            <div class="insight-item">
                <h4>💵 King Dollar</h4>
                <p>A strong <strong>US Dollar (DXY)</strong> makes US exports more expensive globally.</p>
                <p class="insight-desc">Headwind for multi-nationals in <strong>Tech (XLK)</strong>, <strong>Materials (XLB)</strong>, and <strong>Comms (XLC)</strong>.</p>
            </div>
        </div>
    </aside>
    """

def generate_correlation_heatmap(
    sector_drivers_map: Dict[str, List[DriverAnalysis]],
    sector_closes: pd.DataFrame,
    window: int = 90
) -> str:
    """
    Generates an HTML Heatmap of Correlations:
    Rows: Unique Drivers
    Cols: Sectors
    Values: Correlation Coefficient (last 'window' days)
    """
    # 1. Collect all unique drivers and their prices
    unique_drivers = {} # {ticker: (name, price_series)}
    
    for drivers in sector_drivers_map.values():
        for d in drivers:
            if d.ticker not in unique_drivers:
                unique_drivers[d.ticker] = (d.name, d.prices)
    
    if not unique_drivers:
        return ""
        
    sorted_driver_tickers = sorted(unique_drivers.keys())
    sorted_sectors = sorted(sector_drivers_map.keys())
    
    # 2. Build combined DataFrame for correlation calc
    data_dict = {}
    
    # Add Sector Closes
    for sector in sorted_sectors:
        if sector in sector_closes.columns:
            data_dict[sector] = sector_closes[sector]
            
    # Add Driver Closes
    for ticker in sorted_driver_tickers:
        _, prices = unique_drivers[ticker]
        data_dict[ticker] = prices
        
    df = pd.DataFrame(data_dict)
    
    # Filter to last 'window' days
    df = df.tail(window)
    
    # Correlation Matrix
    corr_matrix = df.corr()
    
    # 3. Generate HTML Table
    # Header Row
    html = '<div style="overflow-x: auto; margin-bottom: 2rem;">'
    html += '<table style="width:100%; border-collapse: collapse; font-size: 0.85em;">'
    html += '<thead><tr>'
    html += '<th style="text-align: left; padding: 10px; border-bottom: 2px solid var(--grid-color); color: var(--text-muted); min-width: 140px;">Driver</th>'
    
    for sector in sorted_sectors:
        html += f'<th style="padding: 10px; border-bottom: 2px solid var(--grid-color); color: var(--text-primary); text-align: center;">{sector}</th>'
    html += '</tr></thead><tbody>'
    
    # Data Rows
    for ticker in sorted_driver_tickers:
        name, _ = unique_drivers[ticker]
        label = f"{name} <span style='font-size:0.8em; color:var(--text-muted)'>({ticker})</span>"
        
        html += f'<tr><td style="padding: 8px; border-bottom: 1px solid var(--grid-color); font-weight: 500; color: var(--text-primary);">{label}</td>'
        
        for sector in sorted_sectors:
            if ticker in corr_matrix.index and sector in corr_matrix.columns:
                val = corr_matrix.loc[ticker, sector]
                
                # Determine Color (Green for positive, Red for negative)
                abs_val = abs(val)
                alpha = max(0.1, abs_val * 0.8) # Min opacity 0.1
                
                if val >= 0:
                    bg_color = f"rgba(74, 222, 128, {alpha})" # Green
                    text_col = "#0f172a" if alpha > 0.5 else "#e2e8f0"
                else:
                    bg_color = f"rgba(248, 113, 113, {alpha})" # Red
                    text_col = "#0f172a" if alpha > 0.5 else "#e2e8f0"
                
                if pd.isna(val):
                     html += '<td style="padding: 8px; border-bottom: 1px solid var(--grid-color); text-align: center; color: var(--text-muted);">-</td>'
                else:
                    html += f'<td style="padding: 8px; border-bottom: 1px solid var(--grid-color); text-align: center; background: {bg_color}; color: {text_col}; font-weight: bold;">{val:.2f}</td>'
            else:
                html += '<td style="padding: 8px; border-bottom: 1px solid var(--grid-color); text-align: center; color: var(--text-muted);">N/A</td>'
                
        html += '</tr>'
        
    html += '</tbody></table></div>'
    return html

def generate_macro_page(
    config: Dict,
    sector_drivers_map: Dict[str, List[DriverAnalysis]],
    sector_closes: pd.DataFrame,
    output_dir: str
):
    """
    Generates the reports/macro_drivers.html page.
    """
    
    # 1. Generate Correlation Heatmap
    heatmap_html = generate_correlation_heatmap(sector_drivers_map, sector_closes)
    
    # 2. Generate Insights Sidebar
    sidebar_html = generate_economic_insights_sidebar()
    
    # 3. Grid of charts (Main Content)
    chart_grid = ""
    
    for etf, drivers in sector_drivers_map.items():
        if not drivers:
            continue
            
        sector_name = config['sectors'][etf]['name']
        
        # Sector Section
        sector_section = f"""
        <div class="sector-group" style="margin-bottom: 3rem;">
            <h2 style="border-bottom: 1px solid var(--grid-color); padding-bottom: 0.5rem; margin-bottom: 1.5rem; color: var(--text-primary); display: flex; align-items: center; gap: 10px;">
                <span style="background: rgba(96, 165, 250, 0.2); color: #60a5fa; padding: 4px 8px; border-radius: 4px; font-size: 0.8em;">{etf}</span>
                {sector_name}
            </h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem;">
        """
        
        for d in drivers:
            # Generate large chart (slightly smaller width to fit grid with sidebar)
            sector_price_series = sector_closes[etf] if etf in sector_closes.columns else None
            
            chart_svg = generate_detailed_driver_chart_svg(
                d.prices, 
                d.name, 
                d.ticker + " • 1Y",
                sector_prices=sector_price_series,
                sector_name=etf,
                width=380, 
                height=250
            )
            
            # Context info
            trend_color = "#4ade80" if d.trend == "BULLISH" else "#f87171" if d.trend == "BEARISH" else "#94a3b8"

            # Format current value — yields are small floats (< 20), show 2 decimals; prices show 2 decimals
            curr_val_str = f"{d.current_price:.2f}"

            # Change formatting helpers
            def fmt_chg(v):
                color = "#4ade80" if v >= 0 else "#f87171"
                sign = "+" if v >= 0 else ""
                return f'<span style="color:{color};font-weight:600;">{sign}{v*100:.1f}%</span>'

            chg_1m_html  = fmt_chg(d.change_1m)
            chg_3m_html  = fmt_chg(d.change_3m)
            chg_ytd_html = fmt_chg(d.change_ytd)

            # 52W range bar
            rng = d.high_52w - d.low_52w
            pct_in_range = ((d.current_price - d.low_52w) / rng * 100) if rng > 0 else 50
            pct_in_range = max(0, min(100, pct_in_range))
            pct_off_high = ((d.current_price / d.high_52w) - 1) * 100 if d.high_52w else 0
            off_high_html = fmt_chg(pct_off_high / 100)

            card = f"""
            <div class="driver-card glass-card">
                <div style="margin-bottom: 10px;">
                    {chart_svg}
                </div>

                <!-- Current Value Stats Row -->
                <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:6px; padding: 10px 0; border-top: 1px solid var(--grid-color); border-bottom: 1px solid var(--grid-color); margin-bottom:8px; text-align:center;">
                    <div>
                        <div style="font-size:0.7em; color:var(--text-muted); margin-bottom:2px;">CURRENT</div>
                        <div style="font-size:1.1em; font-weight:700; color:#e2e8f0;">{curr_val_str}</div>
                    </div>
                    <div>
                        <div style="font-size:0.7em; color:var(--text-muted); margin-bottom:2px;">52W HIGH</div>
                        <div style="font-size:0.95em; font-weight:600; color:#94a3b8;">{d.high_52w:.2f}</div>
                    </div>
                    <div>
                        <div style="font-size:0.7em; color:var(--text-muted); margin-bottom:2px;">52W LOW</div>
                        <div style="font-size:0.95em; font-weight:600; color:#94a3b8;">{d.low_52w:.2f}</div>
                    </div>
                </div>

                <!-- 52W Range Bar -->
                <div style="padding: 4px 0 8px 0;">
                    <div style="display:flex; justify-content:space-between; font-size:0.7em; color:var(--text-muted); margin-bottom:3px;">
                        <span>52W Range</span>
                        <span>{off_high_html} from high</span>
                    </div>
                    <div style="background:rgba(255,255,255,0.08); border-radius:4px; height:5px; position:relative;">
                        <div style="position:absolute; left:0; top:0; height:100%; width:{pct_in_range:.0f}%; background: linear-gradient(to right, #f87171, #60a5fa); border-radius:4px;"></div>
                        <div style="position:absolute; top:-3px; left:{pct_in_range:.0f}%; transform:translateX(-50%); width:10px; height:10px; border-radius:50%; background:#e2e8f0; border:2px solid #1e293b;"></div>
                    </div>
                </div>

                <!-- Performance Changes Row -->
                <div style="display:grid; grid-template-columns: repeat(3,1fr); gap:4px; margin-bottom:8px; text-align:center;">
                    <div style="font-size:0.75em;">
                        <div style="color:var(--text-muted); margin-bottom:1px;">1M</div>
                        {chg_1m_html}
                    </div>
                    <div style="font-size:0.75em;">
                        <div style="color:var(--text-muted); margin-bottom:1px;">3M</div>
                        {chg_3m_html}
                    </div>
                    <div style="font-size:0.75em;">
                        <div style="color:var(--text-muted); margin-bottom:1px;">YTD</div>
                        {chg_ytd_html}
                    </div>
                </div>

                <!-- Correlation & Trend -->
                <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 8px; border-top: 1px solid var(--grid-color);">
                    <div style="font-size: 0.85em; color: var(--text-muted);">
                        Corr to {etf}: <span style="color: #e2e8f0; font-weight: bold;">{d.correlation_90d:.2f}</span>
                    </div>
                    <div style="font-size: 0.8em; font-weight: bold; padding: 2px 8px; border-radius: 4px; border: 1px solid {trend_color}; color: {trend_color}; text-transform: uppercase;">
                        {d.trend}
                    </div>
                </div>
            </div>
            """
            sector_section += card
            
        sector_section += "</div></div>"

        chart_grid += sector_section

    # 4. Assemble Full Page
    full_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Macro Drivers | Macro Watch 2.1</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
            {CSS_DARK_THEME}
            
            /* Main Layout Grid */
            .dashboard-layout {{
                display: grid;
                grid-template-columns: 1fr 300px;
                gap: 2rem;
            }}
            
            @media (max-width: 1000px) {{
                .dashboard-layout {{
                    grid-template-columns: 1fr;
                }}
            }}
            
            /* Insights Sidebar Styling */
            .insight-card {{
                background: linear-gradient(135deg, rgba(30, 41, 59, 0.4), rgba(15, 23, 42, 0.6));
                border: 1px solid var(--grid-color);
                border-radius: 8px;
                padding: 1.5rem;
                position: sticky;
                top: 2rem;
                backdrop-filter: blur(10px);
            }}
            
            .insight-item {{
                margin-bottom: 2rem;
                border-bottom: 1px solid rgba(255,255,255,0.05);
                padding-bottom: 1.5rem;
            }}
            .insight-item:last-child {{
                border-bottom: none;
                margin-bottom: 0;
                padding-bottom: 0;
            }}
            
            .insight-item h4 {{
                color: var(--text-primary);
                margin: 0 0 0.5rem 0;
                font-size: 1rem;
            }}
            .insight-item p {{
                color: var(--text-secondary);
                font-size: 0.9em;
                margin: 0 0 0.5rem 0;
                line-height: 1.5;
            }}
            
            .insight-stat {{
                display: inline-block;
                background: rgba(74, 222, 128, 0.1);
                color: #4ade80;
                border: 1px solid rgba(74, 222, 128, 0.3);
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 0.8em;
                font-weight: bold;
                margin-bottom: 0.5rem;
            }}
            .insight-stat.negative {{
                background: rgba(248, 113, 113, 0.1);
                color: #f87171;
                border: 1px solid rgba(248, 113, 113, 0.3);
            }}
            
            .driver-card {{
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .driver-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
                border-color: var(--accent-info);
            }}
            
            .nav-link {{
                color: var(--text-muted);
                fill: var(--text-muted);
                text-decoration: none;
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 8px 12px;
                border-radius: 6px;
                transition: all 0.2s;
            }}
            .nav-link:hover {{
                background: rgba(255, 255, 255, 0.05);
                color: var(--text-primary);
                fill: var(--text-primary);
            }}
            
            h3 {{ color: var(--text-primary); margin-bottom: 1rem; margin-top: 0; }}
        </style>
    </head>
    <body>
        {generate_top_nav("macro_drivers")}
        <div class="container" style="max-width: 1600px;">
            <header style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--grid-color);">
                <div>
                    <h1 style="margin: 0; background: linear-gradient(to right, #60a5fa, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Macro Drivers Analysis</h1>
                    <p class="text-muted" style="margin-top: 0.5rem;">Cross-Sector Economic Indicators & Commodities</p>
                </div>
                <div>
                    <div style="text-align: right; font-size: 0.8em; color: var(--text-muted);">
                        Heatmap: 90-Day Correlation<br>
                        Updates Weekly
                    </div>
                </div>
            </header>

            <main class="dashboard-layout">
                <div class="main-content">
                    <section style="margin-bottom: 3rem;">
                        <h3>Cross-Sector Correlation Matrix ("Optimizer")</h3>
                        <p class="text-muted" style="margin-bottom: 1.5rem; font-size: 0.9em;">
                            This heatmap visualizes how each macro driver affects every sector. 
                            <span style="color: #4ade80;">Green</span> indicates positive correlation (move together), 
                            <span style="color: #f87171;">Red</span> indicates negative correlation (inverse).
                        </p>
                        {heatmap_html}
                    </section>
                    
                    {chart_grid}
                </div>
                
                {sidebar_html}
            </main>
            
            <footer style="margin-top: 4rem; text-align: center; color: var(--text-secondary); border-top: 1px solid var(--grid-color); padding-top: 2rem;">
                <p>Macro Watch 2.1 • Unified Intelligence Layer</p>
            </footer>
        </div>
        {INTERACTIVE_JS}
    </body>
    </html>
    """
    
    out_path = os.path.join(output_dir, "macro_drivers.html")
    with open(out_path, "w") as f:
        f.write(full_html)
        
    print(f"Macro Drivers Page saved to {out_path}")
