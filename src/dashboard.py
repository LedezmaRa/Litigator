"""
Dashboard generation module using Plotly with a First Principles UI/UX Redesign.
Focus: Pleasure to the eye, Dark Mode, Glassmorphism, Information Hierarchy.
"""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import os
import json
from datetime import datetime
from .scoring import ScoreResult

# --- MODERN UI CONSTANTS & TEMPLATES ---

CSS_DARK_THEME = """
:root {
    --bg-color: #0f172a;
    --card-bg: rgba(30, 41, 59, 0.7);
    --card-border: 1px solid rgba(255, 255, 255, 0.1);
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
    --accent-optimal: #4ade80; /* Green-400 */
    --accent-good: #34d399;    /* Emerald-400 */
    --accent-marginal: #fbbf24; /* Amber-400 */
    --accent-poor: #f87171;    /* Red-400 */
    --accent-info: #38bdf8;    /* Sky-400 */
    --font-main: 'Inter', system-ui, -apple-system, sans-serif;
    --glass-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}

body {
    background-color: var(--bg-color);
    color: var(--text-primary);
    font-family: var(--font-main);
    margin: 0;
    padding: 0;
    line-height: 1.6;
    background-image: 
        radial-gradient(at 0% 0%, hsla(253,16%,7%,1) 0, transparent 50%), 
        radial-gradient(at 50% 0%, hsla(225,39%,30%,1) 0, transparent 50%), 
        radial-gradient(at 100% 0%, hsla(339,49%,30%,1) 0, transparent 50%);
    min-height: 100vh;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 2rem;
}

/* Glassmorphism Card */
.glass-card {
    background: var(--card-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: var(--card-border);
    border-radius: 1rem;
    padding: 1.5rem;
    box-shadow: var(--glass-shadow);
}

/* Typography */
h1, h2, h3, h4 { margin-top: 0; color: #fff; font-weight: 600; }
.text-muted { color: var(--text-secondary); }
.text-sm { font-size: 0.875rem; }
.text-xs { font-size: 0.75rem; }
.font-mono { font-family: 'JetBrains Mono', monospace; }

/* Status Badges */
.badge {
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.badge-optimal { background: rgba(74, 222, 128, 0.2); color: #4ade80; border: 1px solid rgba(74, 222, 128, 0.3); }
.badge-good { background: rgba(52, 211, 153, 0.2); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }
.badge-marginal { background: rgba(251, 191, 36, 0.2); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }
.badge-poor { background: rgba(248, 113, 113, 0.2); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.3); }
.badge-info { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }

/* Score Gauge Ring */
.score-ring-container {
    position: relative;
    width: 120px;
    height: 120px;
    display: flex;
    justify-content: center;
    align-items: center;
}
.score-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: #fff;
    z-index: 10;
}
.score-circle-bg { fill: none; stroke: rgba(255,255,255,0.1); stroke-width: 8; }
.score-circle-fg { 
    fill: none; 
    stroke-width: 8; 
    stroke-linecap: round; 
    transform: rotate(-90deg); 
    transform-origin: 50% 50%;
    transition: stroke-dashoffset 1s ease-out;
}

/* Grid Layouts */
.grid-cols-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; }
.grid-cols-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.5rem; }
@media (max-width: 1024px) {
    .grid-cols-3 { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 768px) {
    .grid-cols-3, .grid-cols-2 { grid-template-columns: 1fr; }
}

/* HUD Metrics */
.metric-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.metric-item:last-child { border-bottom: none; }
.progress-bar-bg {
    width: 100px;
    height: 6px;
    background: rgba(255,255,255,0.1);
    border-radius: 3px;
    overflow: hidden;
}
.progress-bar-fg {
    height: 100%;
    border-radius: 3px;
}

/* Table */
.modern-table { width: 100%; border-collapse: separate; border-spacing: 0 0.5rem; }
.modern-table th { padding: 1rem; color: var(--text-secondary); font-weight: 500; font-size: 0.875rem; text-align: left; }
.modern-table td { padding: 1rem; background: rgba(30, 41, 59, 0.5); border-top: 1px solid rgba(255,255,255,0.05); border-bottom: 1px solid rgba(255,255,255,0.05); }
.modern-table td:first-child { border-top-left-radius: 0.5rem; border-bottom-left-radius: 0.5rem; border-left: 1px solid rgba(255,255,255,0.05); }
.modern-table td:last-child { border-top-right-radius: 0.5rem; border-bottom-right-radius: 0.5rem; border-right: 1px solid rgba(255,255,255,0.05); }
.modern-table tr:hover td { background: rgba(30, 41, 59, 0.8); cursor: pointer; transform: scale(1.005); transition: all 0.2s; }

/* Links */
a { color: inherit; text-decoration: none; }
.back-link { 
    display: inline-flex; align-items: center; gap: 0.5rem; 
    color: var(--text-secondary); margin-bottom: 1.5rem; 
    transition: color 0.2s;
}
.back-link:hover { color: #fff; }

/* Sortable Table Headers */
.modern-table th.sortable {
    cursor: pointer;
    user-select: none;
    position: relative;
    padding-right: 1.5rem;
}
.modern-table th.sortable:hover {
    color: var(--text-primary);
}
.modern-table th.sortable::after {
    content: '⇅';
    position: absolute;
    right: 0.5rem;
    opacity: 0.4;
    font-size: 0.7rem;
}
.modern-table th.sortable.asc::after {
    content: '↑';
    opacity: 1;
    color: var(--accent-optimal);
}
.modern-table th.sortable.desc::after {
    content: '↓';
    opacity: 1;
    color: var(--accent-optimal);
}

/* Search Input */
.search-input {
    background: rgba(30, 41, 59, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    color: var(--text-primary);
    font-size: 1rem;
    width: 100%;
    max-width: 400px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.search-input:focus {
    border-color: var(--accent-info);
    box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.1);
}
.search-input::placeholder {
    color: var(--text-secondary);
}

/* Filter Controls */
.filter-bar {
    display: flex;
    gap: 1rem;
    align-items: center;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
}
.filter-btn {
    background: rgba(30, 41, 59, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    padding: 0.5rem 1rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
}
.filter-btn:hover {
    background: rgba(30, 41, 59, 0.9);
    color: var(--text-primary);
}
.filter-btn.active {
    background: rgba(74, 222, 128, 0.2);
    border-color: rgba(74, 222, 128, 0.3);
    color: var(--accent-optimal);
}

/* Chart Tooltip */
.chart-tooltip {
    position: fixed;
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    padding: 0.75rem;
    font-size: 0.75rem;
    color: var(--text-primary);
    pointer-events: none;
    z-index: 1000;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
    display: none;
}
.chart-tooltip.visible {
    display: block;
}

/* Stock Card Hover Enhancement */
.glass-card.stock-card {
    transition: transform 0.2s, box-shadow 0.2s;
}
.glass-card.stock-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
}

/* Hidden class for filtering */
.hidden {
    display: none !important;
}
/* Top Navigation Menu */
.top-nav {
    display: flex;
    justify-content: center;
    align-items: center;
    background: rgba(15, 23, 42, 0.8);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    padding: 1rem 2rem;
    position: sticky;
    top: 0;
    z-index: 1000;
    margin-bottom: 2rem;
}
.top-nav-list {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 1.5rem;
    list-style: none;
    margin: 0;
    padding: 0;
}
.nav-item {
    color: var(--text-secondary);
    text-decoration: none;
    font-weight: 500;
    font-size: 0.95rem;
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    transition: all 0.2s ease;
}
.nav-item:hover {
    color: var(--text-primary);
    background: rgba(255, 255, 255, 0.05);
}
.nav-item.active {
    color: var(--accent-optimal);
    background: rgba(74, 222, 128, 0.1);
    border: 1px solid rgba(74, 222, 128, 0.2);
}
"""

# Interactive JavaScript for sortable tables and search
INTERACTIVE_JS = """
<script>
// Sortable Tables
function initSortableTables() {
    document.querySelectorAll('.modern-table').forEach(table => {
        const headers = table.querySelectorAll('th.sortable');
        headers.forEach((header, colIndex) => {
            header.addEventListener('click', () => {
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const isAsc = header.classList.contains('asc');

                // Clear other headers
                headers.forEach(h => h.classList.remove('asc', 'desc'));
                header.classList.add(isAsc ? 'desc' : 'asc');

                rows.sort((a, b) => {
                    const aCell = a.cells[colIndex];
                    const bCell = b.cells[colIndex];
                    let aVal = aCell.textContent.trim();
                    let bVal = bCell.textContent.trim();

                    // Try numeric sort
                    const aNum = parseFloat(aVal.replace(/[^0-9.-]/g, ''));
                    const bNum = parseFloat(bVal.replace(/[^0-9.-]/g, ''));

                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        return isAsc ? bNum - aNum : aNum - bNum;
                    }
                    return isAsc ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal);
                });

                rows.forEach(row => tbody.appendChild(row));
            });
        });
    });
}

// Search/Filter for Stock Cards
function initSearch() {
    const searchInput = document.getElementById('stock-search');
    if (!searchInput) return;

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        document.querySelectorAll('.stock-card').forEach(card => {
            const ticker = card.dataset.ticker?.toLowerCase() || '';
            const name = card.dataset.name?.toLowerCase() || '';
            const matches = ticker.includes(query) || name.includes(query);
            card.classList.toggle('hidden', !matches);
        });

        // Update visible count
        const visible = document.querySelectorAll('.stock-card:not(.hidden)').length;
        const countEl = document.getElementById('visible-count');
        if (countEl) countEl.textContent = visible;
    });
}

// Filter Buttons
function initFilterButtons() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const filter = btn.dataset.filter;
            const isActive = btn.classList.contains('active');

            // Toggle active state
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            if (!isActive) btn.classList.add('active');

            // Apply filter
            document.querySelectorAll('.stock-card').forEach(card => {
                if (!filter || isActive) {
                    card.classList.remove('hidden');
                } else if (filter === 'top5') {
                    card.classList.toggle('hidden', parseInt(card.dataset.rank) > 5);
                } else if (filter === 'trade-ready') {
                    card.classList.toggle('hidden', card.dataset.tradeReady !== 'true');
                }
            });

            // Update count
            const visible = document.querySelectorAll('.stock-card:not(.hidden)').length;
            const countEl = document.getElementById('visible-count');
            if (countEl) countEl.textContent = visible;
        });
    });
}

// Chart Tooltip (for SVG charts)
function initChartTooltips() {
    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip';
    document.body.appendChild(tooltip);

    document.querySelectorAll('svg.interactive-chart').forEach(chart => {
        chart.addEventListener('mousemove', (e) => {
            const rect = chart.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const data = chart.dataset.values ? JSON.parse(chart.dataset.values) : null;

            if (data && data.length > 0) {
                const idx = Math.floor((x / rect.width) * data.length);
                const point = data[Math.min(idx, data.length - 1)];

                if (point) {
                    tooltip.innerHTML = `
                        <div><strong>${point.date || ''}</strong></div>
                        <div>Price: $${point.price?.toFixed(2) || 'N/A'}</div>
                        ${point.ema20 ? `<div style="color:#f59e0b">EMA20: $${point.ema20.toFixed(2)}</div>` : ''}
                        ${point.ema50 ? `<div style="color:#8b5cf6">EMA50: $${point.ema50.toFixed(2)}</div>` : ''}
                    `;
                    tooltip.style.left = (e.clientX + 15) + 'px';
                    tooltip.style.top = (e.clientY - 10) + 'px';
                    tooltip.classList.add('visible');
                }
            }
        });

        chart.addEventListener('mouseleave', () => {
            tooltip.classList.remove('visible');
        });
    });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initSortableTables();
    initSearch();
    initFilterButtons();
    initChartTooltips();
});
</script>
"""

def generate_top_nav(active_page: str = "command_center") -> str:
    """Generates the shared top navigation menu HTML."""
    pages = [
        {"id": "command_center", "name": "Command Center", "url": "index.html"},
        {"id": "sector_analysis", "name": "Sector Analysis", "url": "sector_analysis.html"},
        {"id": "macro_drivers", "name": "Macro Drivers", "url": "macro_drivers.html"},
        {"id": "market_news", "name": "Market News", "url": "market_news.html"},
        {"id": "ai_memo", "name": "AI Strategy", "url": "ai_memo.html"},
        {"id": "ai_macro_memo", "name": "Macro AI", "url": "ai_macro_memo.html"}
    ]
    
    links_html = ""
    for p in pages:
        active_class = " active" if p["id"] == active_page else ""
        links_html += f'<li><a href="{p["url"]}" class="nav-item{active_class}">{p["name"]}</a></li>'
    
    return f"""
    <nav class="top-nav">
        <ul class="top-nav-list">
            {links_html}
        </ul>
    </nav>
    """

def generate_gauge_svg(score: float, size: int = 120):
    """Generates an SVG circular gauge for the score."""
    radius = size // 2 - 4
    circumference = 2 * 3.14159 * radius
    offset = circumference - (score / 100) * circumference
    
    # Color logic
    color = "var(--accent-optimal)"
    if score < 75: color = "var(--accent-good)"
    if score < 60: color = "var(--accent-marginal)"
    if score < 45: color = "var(--accent-poor)"
    
    return f"""
    <div class="score-ring-container" style="width:{size}px; height:{size}px">
        <svg width="{size}" height="{size}">
            <circle class="score-circle-bg" cx="{size//2}" cy="{size//2}" r="{radius}"></circle>
            <circle class="score-circle-fg" cx="{size//2}" cy="{size//2}" r="{radius}" 
                    stroke="{color}" stroke-dasharray="{circumference}" stroke-dashoffset="{offset}"></circle>
        </svg>
        <div class="score-value">{score:.0f}</div>
    </div>
    """

def get_status_badge(val: float, type: str):
    """Helper to return badge HTML based on value and type."""
    if type == 'score':
        if val >= 90: return '<span class="badge badge-optimal">Optimal</span>'
        if val >= 75: return '<span class="badge badge-good">Good</span>'
        if val >= 60: return '<span class="badge badge-marginal">Acceptable</span>'
        return '<span class="badge badge-poor">Poor</span>'
    return ""

def generate_dashboard(ticker: str, df: pd.DataFrame, result: ScoreResult, weekly_trend: str, output_dir: str = "reports") -> str:
    """Generates a premium HTML dashboard for individual ticker."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # --- PLOTLY CHART DARK THEME ---
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, 
                        row_heights=[0.6, 0.2, 0.2])

    # 1. Price
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price'), row=1, col=1)
    
    # EMAs
    ema_cols = [c for c in df.columns if c.startswith('EMA_')]
    colors = ['#f59e0b', '#3b82f6', '#8b5cf6'] # Amber, Blue, Violet
    for i, col in enumerate(ema_cols):
        fig.add_trace(go.Scatter(x=df.index, y=df[col], line=dict(color=colors[i % len(colors)], width=1.5), name=col), row=1, col=1)

    # 2. ADX
    if 'ADX' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['ADX'], line=dict(color='#cbd5e1', width=1.5), name='ADX'), row=2, col=1)
        fig.add_hline(y=25, line_dash="dash", line_color="rgba(255,255,255,0.3)", row=2, col=1)

    # 3. Volume
    colors_vol = ['#22c55e' if row['Open'] - row['Close'] <= 0 else '#ef4444' for index, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors_vol, name='Volume'), row=3, col=1)

    # Dark Chart Styling
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        height=800,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        font=dict(family="Inter, sans-serif", color="#94a3b8")
    )
    fig.update_xaxes(rangeslider_visible=False, showgrid=True, gridcolor='rgba(255,255,255,0.05)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(255,255,255,0.05)')
    
    chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False})

    # --- SCORE BREAKDOWN ROWS ---
    score_rows = ""
    for k, v in result.breakdown.items():
        # Get max points for this factor (hardcoded logic based on known weights)
        max_pts = 25.0
        if 'volume' in k or 'structure' in k: max_pts = 20.0
        if 'risk' in k: max_pts = 10.0
        
        pct = (v / max_pts) * 100
        
        # Color bar
        bar_color = "var(--accent-optimal)"
        if pct < 60: bar_color = "var(--accent-marginal)"
        if pct < 40: bar_color = "var(--accent-poor)"
        
        score_rows += f"""
        <div class="metric-item">
            <span class="text-sm font-medium">{k.replace('_', ' ').title()}</span>
            <div style="display:flex; align-items:center; gap:1rem;">
                <div class="progress-bar-bg"><div class="progress-bar-fg" style="width:{pct}%; background:{bar_color};"></div></div>
                <span class="text-sm font-mono text-muted">{v:.1f}/{max_pts:.0f}</span>
            </div>
        </div>
        """

    # --- HTML ASSEMBLY ---
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{ticker} Analysis | Command Center</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>{CSS_DARK_THEME}</style>
    </head>
    <body>
        {generate_top_nav("")}
        <div class="container">
            <a href="index.html" class="back-link">
                <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
                Back to Dashboard
            </a>
            
            <div class="grid-cols-3" style="margin-bottom: 2rem;">
                <!-- Main Status Card -->
                <div class="glass-card" style="display:flex; align-items:center; gap: 2rem;">
                    {generate_gauge_svg(result.total_score, 100)}
                    <div>
                        <h1 style="font-size:3rem; line-height:1; margin-bottom:0.5rem;">{ticker}</h1>
                        <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:0.5rem;">
                            <span class="text-xl font-bold">${result.details['price']:.2f}</span>
                            {get_status_badge(result.total_score, 'score')}
                        </div>
                        <span class="text-sm text-muted">{weekly_trend.replace('_', ' ').title()}</span>
                    </div>
                </div>
                
                <!-- Score Breakdown -->
                <div class="glass-card">
                    <h3 class="text-sm text-muted" style="text-transform:uppercase; letter-spacing:0.05em; margin-bottom:1rem;">Score Breakdown</h3>
                    {score_rows}
                </div>
                
                <!-- Risk & Targets -->
                <div class="glass-card">
                    <h3 class="text-sm text-muted" style="text-transform:uppercase; letter-spacing:0.05em; margin-bottom:1rem;">Risk Management</h3>
                    <div class="grid-cols-2" style="gap:1rem;">
                        <div>
                            <span class="text-xs text-muted block">ATR (14)</span>
                            <span class="font-mono text-sm">${result.details['atr']:.2f}</span>
                        </div>
                        <div>
                            <span class="text-xs text-muted block">EMA (20) Support</span>
                            <span class="font-mono text-sm" style="color:var(--accent-info)">${result.details['ema20']:.2f}</span>
                        </div>
                    </div>
                    <div style="margin-top:1rem; padding-top:1rem; border-top:1px solid rgba(255,255,255,0.1);">
                        <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
                            <span class="text-sm text-muted">Stop (2.0x ATR)</span>
                            <span class="font-mono text-sm text-primary">${result.details['ema20'] - 2*result.details['atr']:.2f}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span class="text-sm text-muted">Target (5.0x ATR)</span>
                            <span class="font-mono text-sm" style="color:var(--accent-optimal)">${result.details['price'] + 5*result.details['atr']:.2f}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Chart Area -->
            <div class="glass-card" style="padding:1rem;">
                {chart_html}
            </div>
        </div>
    </body>
    </html>
    """
    
    file_path = os.path.join(output_dir, f"{ticker}_analysis.html")
    with open(file_path, "w") as f:
        f.write(html)
        
    return file_path

def generate_index(reports: list, output_dir: str = "reports"):
    """Generates the Main Dashboard Index."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    reports.sort(key=lambda x: x['score'], reverse=True)
    
    # Hero/Best Pick
    best_pick = reports[0] if reports else None
    hero_html = ""
    if best_pick:
        hero_html = f"""
        <div class="glass-card" style="margin-bottom:2rem; background: linear-gradient(135deg, rgba(30,41,59,0.8) 0%, rgba(15,23,42,0.9) 100%); border: 1px solid rgba(74, 222, 128, 0.2);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span class="badge badge-optimal" style="margin-bottom:0.5rem; display:inline-block;">Top Pick of the Week</span>
                    <h1 style="font-size:3.5rem; margin-bottom:0rem;">{best_pick['ticker']}</h1>
                    <p class="text-muted text-lg">Score: <span style="color:var(--accent-optimal); font-weight:bold;">{best_pick['score']:.0f}</span> • {best_pick['regime'].replace('_', ' ').title()}</p>
                </div>
                {generate_gauge_svg(best_pick['score'], 140)}
            </div>
            <div style="margin-top:1.5rem; display:flex; gap:2rem;">
                <div><span class="text-xs text-muted block">Price</span><span class="text-xl font-mono">${best_pick.get('close',0):.2f}</span></div>
                <div><span class="text-xs text-muted block">EMA20</span><span class="text-xl font-mono">${best_pick.get('ema20',0):.2f}</span></div>
                <div><span class="text-xs text-muted block">R:R</span><span class="text-xl font-mono">{best_pick.get('rr',0):.1f}</span></div>
            </div>
        </div>
        """
        
    # Table Rows
    rows = ""
    for r in reports:
        link = os.path.basename(r['path'])
        score = r['score']
        
        # Color logic
        score_color = "var(--text-primary)"
        if score >= 90: score_color = "var(--accent-optimal)"
        elif score >= 75: score_color = "var(--accent-good)"
        elif score < 45: score_color = "var(--accent-poor)"
        
        rows += f"""
        <tr onclick="window.location='{link}'">
            <td>
                <div style="display:flex; align-items:center; gap:1rem;">
                    <div style="width:40px; height:40px; background:rgba(255,255,255,0.05); border-radius:8px; display:flex; align-items:center; justify-content:center; font-weight:bold;">
                        {r['ticker'][0]}
                    </div>
                    <div>
                        <div class="font-bold">{r['ticker']}</div>
                        <div class="text-xs text-muted">${r.get('close',0):.2f}</div>
                    </div>
                </div>
            </td>
            <td>
                <span style="font-size:1.25rem; font-weight:700; color:{score_color}">{score:.0f}</span>
            </td>
            <td>{get_status_badge(score, 'score')}</td>
            <td class="font-mono text-sm">{r.get('adx',0):.1f}</td>
            <td class="font-mono text-sm">{r.get('rel_vol',0):.1f}x</td>
            <td class="font-mono text-sm">{r.get('rr',0):.1f}</td>
            <td><span class="badge" style="background:rgba(255,255,255,0.1); color:#cbd5e1;">{r['regime'].split('_')[0]}</span></td>
            <td><span class="text-muted">&rarr;</span></td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Command Center | Weekly Analysis</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>{CSS_DARK_THEME}</style>
    </head>
    <body>
        {generate_top_nav("command_center")}
        <div class="container">
            <header style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3rem;">
                <div>
                    <h1 style="margin-bottom:0.5rem; background: linear-gradient(to right, #60a5fa, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Command Center</h1>
                    <p class="text-muted">EMA-ADX-ATR Optimized Framework 2.0</p>
                </div>
                <div>
                  <span class="badge badge-avg">{datetime.now().strftime("%Y-%m-%d")}</span>
                </div>
            </header>
            
            {hero_html}
            
            <div class="glass-card" style="padding:0; overflow:hidden;">
                <table class="modern-table">
                    <thead>
                        <tr>
                            <th>Ticker</th>
                            <th>Score</th>
                            <th>Rating</th>
                            <th>ADX</th>
                            <th>Vol</th>
                            <th>R:R</th>
                            <th>Regime</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
            </div>
            
            <footer style="margin-top:3rem; text-align:center; color:var(--text-secondary); font-size:0.875rem;">
                <p>Generated by Antigravity Agent. Market data is delayed.</p>
            </footer>
        </div>
    </body>
    </html>
    """
    
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(html)
