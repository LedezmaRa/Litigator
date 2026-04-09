"""
Macro Drivers Dashboard Generator
Aggregates all sector drivers into a single high-level view with Cross-Sector Correlation Analysis and Economic Insights.
"""

import os
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from src.utils.html_utils import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav, generate_breadcrumb
from src.baskets import fetch_basket_context
from src.breadth import fetch_market_breadth
from src.macro_fred import fetch_macro_regime
from src.sectors.rrg import calculate_rrg, generate_rrg_html
from src.sectors.charts import generate_detailed_driver_chart_svg
from src.sectors.drivers import DriverAnalysis

# ---------------------------------------------------------------------------
# Improvement 1: Macro Scorecard
# ---------------------------------------------------------------------------

def _sector_macro_signal(drivers: List[DriverAnalysis]) -> tuple:
    """
    Returns (label, color, score) for a sector based on net correlation-weighted trend signal.
    trend_signal = +1 (BULLISH) or -1 (BEARISH); multiply by correlation to sector.
    Positive net → TAILWIND, negative → HEADWIND, near-zero → NEUTRAL.
    """
    if not drivers:
        return ("NEUTRAL", "var(--text-secondary)", 0.0)
    total = 0.0
    for d in drivers:
        signal = 1.0 if d.trend == "BULLISH" else -1.0
        # Weight by absolute correlation so stronger correlations count more
        total += signal * abs(d.correlation_90d)
    avg = total / len(drivers)
    if avg > 0.15:
        return ("TAILWIND", "var(--accent-optimal)", avg)
    elif avg < -0.15:
        return ("HEADWIND", "var(--accent-poor)", avg)
    else:
        return ("NEUTRAL", "var(--accent-marginal)", avg)


def generate_macro_scorecard_html(
    sector_drivers_map: Dict[str, List[DriverAnalysis]],
    config: Dict
) -> str:
    """Compact per-sector TAILWIND / HEADWIND / NEUTRAL scorecard strip."""
    cards = []
    for etf in sorted(sector_drivers_map.keys()):
        drivers = sector_drivers_map[etf]
        label, color, score = _sector_macro_signal(drivers)
        sector_name = config['sectors'][etf]['name'] if etf in config.get('sectors', {}) else etf

        bg_alpha = 0.15
        if label == "TAILWIND":
            bg = f"rgba(74,222,128,{bg_alpha})"
            border = "rgba(74,222,128,0.35)"
        elif label == "HEADWIND":
            bg = f"rgba(248,113,113,{bg_alpha})"
            border = "rgba(248,113,113,0.35)"
        else:
            bg = f"rgba(251,191,36,{bg_alpha})"
            border = "rgba(251,191,36,0.35)"

        bar_width = min(100, abs(score) * 200)  # scale: ±0.5 fills bar
        bar_dir = "right" if score >= 0 else "left"

        cards.append(f"""
        <div onclick="filterSector('{etf}')" title="Click to filter to {etf}" style="
            background:{bg}; border:1px solid {border}; border-radius:10px;
            padding:10px 14px; cursor:pointer; transition:transform 0.15s;
            min-width:110px; text-align:center;
        " onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform=''">
            <div style="font-size:0.7rem; color:var(--text-secondary); margin-bottom:3px;">{etf}</div>
            <div style="font-size:0.75rem; color:{color}; font-weight:700; letter-spacing:0.04em;">{label}</div>
            <div style="margin-top:5px; background:rgba(255,255,255,0.08); border-radius:3px; height:3px; position:relative; overflow:hidden;">
                <div style="position:absolute; {'left' if score >= 0 else 'right'}:0; top:0; height:100%;
                    width:{bar_width:.0f}%; background:{color}; border-radius:3px;"></div>
            </div>
        </div>""")

    return f"""
    <section class="glass-card" style="margin-bottom:2rem; padding:1.25rem 1.5rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
            <div>
                <h3 style="margin:0; font-size:1rem;">Macro Scorecard</h3>
                <p class="text-muted" style="font-size:0.8em; margin:2px 0 0 0;">
                    Net driver signal per sector — sum of correlation-weighted BULLISH/BEARISH trends
                </p>
            </div>
            <button onclick="filterSector('')" style="
                background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.15);
                color:var(--text-secondary); padding:5px 14px; border-radius:6px;
                cursor:pointer; font-size:0.8rem; transition:background 0.15s;
            " onmouseover="this.style.background='rgba(255,255,255,0.12)'" onmouseout="this.style.background='rgba(255,255,255,0.07)'">
                Show All
            </button>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:0.65rem;">
            {''.join(cards)}
        </div>
    </section>"""


# ---------------------------------------------------------------------------
# Improvement 2: Macro Regime Panel
# ---------------------------------------------------------------------------

_REGIME_TICKERS = {
    "^TNX":     ("10Y Yield",  "Rates"),
    "DX-Y.NYB": ("US Dollar",  "Dollar"),
    "CL=F":     ("Oil",        "Oil"),
    "XBI":      ("Biotech",    "Risk"),
    "^IRX":     ("3M T-Bill",  "Credit"),
    "GLD":      ("Gold",       "Gold"),
}


def generate_macro_regime_panel_html(sector_drivers_map: Dict[str, List[DriverAnalysis]]) -> str:
    """Compact 5-signal strip: yields, dollar, oil, risk appetite, credit."""
    # Collect all unique drivers into a flat map
    all_drivers: Dict[str, DriverAnalysis] = {}
    for drivers in sector_drivers_map.values():
        for d in drivers:
            if d.ticker not in all_drivers:
                all_drivers[d.ticker] = d

    def _arrow(v: float) -> str:
        return "↑" if v >= 0 else "↓"

    def _chg_color(v: float) -> str:
        return "var(--accent-optimal)" if v >= 0 else "var(--accent-poor)"

    signal_cells = []
    for ticker, (long_name, short_name) in _REGIME_TICKERS.items():
        d = all_drivers.get(ticker)
        if d is None:
            continue
        arr = _arrow(d.change_1m)
        col = _chg_color(d.change_1m)
        trend_col = "var(--accent-optimal)" if d.trend == "BULLISH" else "var(--accent-poor)"
        chg_1w_col = _chg_color(d.change_1w)
        chg_1w_arr = _arrow(d.change_1w)

        signal_cells.append(f"""
        <div style="text-align:center; padding:10px 16px; border-right:1px solid rgba(255,255,255,0.07); min-width:90px;">
            <div style="font-size:0.65rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.07em; margin-bottom:3px;">{short_name}</div>
            <div style="font-size:1.05rem; font-weight:700; color:#e2e8f0;">{d.current_price:.2f}</div>
            <div style="font-size:0.7rem; color:{col}; font-weight:600;">{arr} {abs(d.change_1m*100):.1f}% 1M</div>
            <div style="font-size:0.65rem; color:{chg_1w_col}; margin-top:1px;">{chg_1w_arr} {abs(d.change_1w*100):.1f}% 1W</div>
            <div style="margin-top:5px;">
                <span style="font-size:0.65rem; color:{trend_col}; border:1px solid {trend_col};
                    padding:1px 6px; border-radius:4px; text-transform:uppercase; letter-spacing:0.04em;">
                    {d.trend}
                </span>
            </div>
        </div>""")

    if not signal_cells:
        return ""

    return f"""
    <section class="glass-card" style="margin-bottom:2rem; padding:1.25rem 1.5rem;">
        <div style="margin-bottom:0.75rem;">
            <h3 style="margin:0; font-size:1rem;">Macro Regime</h3>
            <p class="text-muted" style="font-size:0.8em; margin:2px 0 0 0;">Key cross-market signals at a glance</p>
        </div>
        <div style="display:flex; flex-wrap:wrap; overflow-x:auto;">
            {''.join(signal_cells)}
        </div>
    </section>"""


# ---------------------------------------------------------------------------
# Improvement 3: Live-calibrated sidebar
# ---------------------------------------------------------------------------

def generate_economic_insights_sidebar(
    sector_drivers_map: Optional[Dict[str, List[DriverAnalysis]]] = None
) -> str:
    """Generates the Economic Insights sidebar with live-computed correlations where available."""

    def _live_corr(ticker: str, sector: str, fallback: str) -> str:
        """Return a formatted correlation string from live data, or fallback."""
        if sector_drivers_map and sector in sector_drivers_map:
            for d in sector_drivers_map[sector]:
                if d.ticker == ticker:
                    v = d.correlation_90d
                    col = "var(--accent-optimal)" if v > 0 else "var(--accent-poor)"
                    sign = "+" if v >= 0 else ""
                    status = "CONFIRMING" if abs(v) > 0.4 else "DIVERGING"
                    status_col = "var(--accent-optimal)" if abs(v) > 0.4 else "var(--accent-marginal)"
                    return (
                        f'<span style="color:{col}; font-weight:700;">{sign}{v:.2f}</span>'
                        f' <span style="font-size:0.7em; color:{status_col}; '
                        f'border:1px solid {status_col}; padding:1px 5px; border-radius:4px;">{status}</span>'
                    )
        return fallback

    copper_corr = _live_corr("COPX", "XLI", '<span style="color:var(--accent-optimal)">+0.80+</span>')
    oil_xly_corr = _live_corr("CL=F", "XLY", '<span style="color:var(--accent-poor)">−0.40</span>')
    tnx_xlk_corr = _live_corr("^TNX", "XLK", '<span style="color:var(--accent-poor)">Inverse</span>')
    tnx_xlf_corr = _live_corr("^TNX", "XLF", '<span style="color:var(--accent-optimal)">Positive</span>')
    tnx_xlre_corr = _live_corr("^TNX", "XLRE", '<span style="color:var(--accent-poor)">−0.70+</span>')

    return f"""
    <aside class="insights-sidebar">
        <div class="insight-card">
            <h3 style="color: #60a5fa; margin-top:0;">
                <span style="font-size:1.2em;">🎓</span> Economic Insights
            </h3>
            <p style="font-size:0.75em; color:var(--text-secondary); margin-top:-0.5rem; margin-bottom:1rem;">
                Correlations updated live from this run
            </p>

            <div class="insight-item">
                <h4>🏭 Dr. Copper &amp; Industrials</h4>
                <p><strong>Copper (COPX)</strong> is the "Ph.D. of Economics." Rising copper signals strong demand for buildings and machines.</p>
                <div class="insight-stat">Live Corr to XLI: {copper_corr}</div>
                <p class="insight-desc">Boosting <strong>Industrials (XLI)</strong> and <strong>Materials (XLB)</strong>.</p>
            </div>

            <div class="insight-item">
                <h4>🛢️ The "Oil Tax" on Consumers</h4>
                <p>Rising <strong>Oil (CL=F)</strong> acts like a tax, leaving less money for discretionary spending.</p>
                <div class="insight-stat negative">Live Corr to XLY: {oil_xly_corr}</div>
                <p class="insight-desc">High oil hurts <strong>Consumer Discretionary (XLY)</strong> stocks (Retail, Autos).</p>
            </div>

            <div class="insight-item">
                <h4>📉 Yields vs. Tech &amp; Growth</h4>
                <p><strong>10Y Yields (^TNX)</strong> represent the risk-free rate. High rates hurt long-duration growth assets.</p>
                <div class="insight-stat negative">Live Corr to XLK: {tnx_xlk_corr}</div>
                <p class="insight-desc">When yields spike, <strong>Technology (XLK)</strong> and <strong>Comms (XLC)</strong> valuations compress.</p>
            </div>

            <div class="insight-item">
                <h4>🏦 Yield Curve &amp; Banks</h4>
                <p>Banks profit from the <em>spread</em> between short (^IRX) and long (^TNX) rates — a steeper curve = more profit.</p>
                <div class="insight-stat">Live Corr to XLF: {tnx_xlf_corr}</div>
                <p class="insight-desc">Rising long rates generally lift <strong>Financials (XLF)</strong> via wider net interest margins.</p>
            </div>

            <div class="insight-item">
                <h4>🏠 Rates vs. REITs</h4>
                <p><strong>REITs (XLRE)</strong> are priced like bonds. When rates rise, their dividend yields look less attractive.</p>
                <div class="insight-stat negative">Live Corr to XLRE: {tnx_xlre_corr}</div>
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


# ---------------------------------------------------------------------------
# Improvement 7: Sortable Correlation Heatmap
# ---------------------------------------------------------------------------

def generate_correlation_heatmap(
    sector_drivers_map: Dict[str, List[DriverAnalysis]],
    sector_closes: pd.DataFrame,
    window: int = 90
) -> str:
    """
    Generates an HTML Heatmap of Correlations.
    Rows: Unique Drivers | Cols: Sectors | Values: 90-day correlation.
    Columns are sortable by clicking the header (JS).
    Cells with |corr| > 0.5 get a highlight ring.
    """
    unique_drivers = {}
    for drivers in sector_drivers_map.values():
        for d in drivers:
            if d.ticker not in unique_drivers:
                unique_drivers[d.ticker] = (d.name, d.prices)

    if not unique_drivers:
        return ""

    sorted_driver_tickers = sorted(unique_drivers.keys())
    sorted_sectors = sorted(sector_drivers_map.keys())

    data_dict = {}
    for sector in sorted_sectors:
        if sector in sector_closes.columns:
            data_dict[sector] = sector_closes[sector]
    for ticker in sorted_driver_tickers:
        _, prices = unique_drivers[ticker]
        data_dict[ticker] = prices

    df = pd.DataFrame(data_dict).tail(window)
    corr_matrix = df.corr()

    # Header row
    html = '<div id="macro-heatmap-wrap" style="overflow-x: auto; margin-bottom: 2rem;">'
    html += '<table id="macro-heatmap" style="width:100%; border-collapse: collapse; font-size: 0.85em;">'
    html += '<thead><tr>'
    html += ('<th style="text-align:left; padding:10px; border-bottom:2px solid var(--grid-color); '
             'color:var(--text-muted); min-width:140px;">Driver</th>')
    for i, sector in enumerate(sorted_sectors):
        html += (f'<th data-col="{i}" class="heatmap-th sortable" style="padding:10px; '
                 f'border-bottom:2px solid var(--grid-color); color:var(--text-primary); '
                 f'text-align:center; cursor:pointer; user-select:none;" '
                 f'title="Click to sort by |correlation| to {sector}">'
                 f'{sector} <span style="font-size:0.7em; color:var(--text-muted);">↕</span></th>')
    html += '</tr></thead><tbody>'

    for ticker in sorted_driver_tickers:
        name, _ = unique_drivers[ticker]
        label = (f"{name} <span style='font-size:0.8em; color:var(--text-muted)'>({ticker})</span>")
        html += (f'<tr><td style="padding:8px; border-bottom:1px solid var(--grid-color); '
                 f'font-weight:500; color:var(--text-primary);">{label}</td>')
        for sector in sorted_sectors:
            if ticker in corr_matrix.index and sector in corr_matrix.columns:
                val = corr_matrix.loc[ticker, sector]
                if pd.isna(val):
                    html += ('<td style="padding:8px; border-bottom:1px solid var(--grid-color); '
                             'text-align:center; color:var(--text-muted);">-</td>')
                else:
                    abs_val = abs(val)
                    alpha = max(0.1, abs_val * 0.8)
                    bg_color = (f"rgba(74,222,128,{alpha})" if val >= 0
                                else f"rgba(248,113,113,{alpha})")
                    text_col = "#0f172a" if alpha > 0.5 else "#e2e8f0"
                    # Highlight strong correlations with a ring border
                    ring = "box-shadow:inset 0 0 0 2px rgba(255,255,255,0.5);" if abs_val > 0.5 else ""
                    html += (f'<td data-val="{val:.4f}" style="padding:8px; border-bottom:1px solid var(--grid-color); '
                             f'text-align:center; background:{bg_color}; color:{text_col}; '
                             f'font-weight:bold; {ring}">{val:.2f}</td>')
            else:
                html += ('<td style="padding:8px; border-bottom:1px solid var(--grid-color); '
                         'text-align:center; color:var(--text-muted);">N/A</td>')
        html += '</tr>'

    html += '</tbody></table></div>'
    return html


# ---------------------------------------------------------------------------
# Sector filter pills JS
# ---------------------------------------------------------------------------

_SECTOR_FILTER_JS = """
<script>
function filterSector(etf) {
    const groups = document.querySelectorAll('.sector-group');
    if (!etf) {
        groups.forEach(g => g.style.display = '');
        document.querySelectorAll('.sector-pill').forEach(p => p.classList.remove('active'));
        return;
    }
    groups.forEach(g => {
        g.style.display = (g.dataset.sector === etf || !etf) ? '' : 'none';
    });
    document.querySelectorAll('.sector-pill').forEach(p => {
        p.classList.toggle('active', p.dataset.etf === etf);
    });
}

function initMacroHeatmap() {
    const table = document.getElementById('macro-heatmap');
    if (!table) return;
    table.querySelectorAll('th.heatmap-th').forEach(th => {
        th.addEventListener('click', () => {
            const col = parseInt(th.dataset.col) + 1; // +1 for driver label col
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const isAsc = th.dataset.dir === 'asc';
            th.dataset.dir = isAsc ? 'desc' : 'asc';

            // Reset other headers
            table.querySelectorAll('th.heatmap-th').forEach(h => {
                h.querySelector('span').textContent = ' ↕';
            });
            th.querySelector('span').textContent = isAsc ? ' ↓' : ' ↑';

            rows.sort((a, b) => {
                const av = parseFloat(a.cells[col]?.dataset.val || '0');
                const bv = parseFloat(b.cells[col]?.dataset.val || '0');
                // Sort by absolute correlation value
                return isAsc ? Math.abs(av) - Math.abs(bv) : Math.abs(bv) - Math.abs(av);
            });
            rows.forEach(r => tbody.appendChild(r));
        });
    });
}

document.addEventListener('DOMContentLoaded', function() {
    initMacroHeatmap();
});
</script>
"""


# ---------------------------------------------------------------------------
# FRED Macro Regime section
# ---------------------------------------------------------------------------

def _generate_fred_macro_html() -> str:
    """Renders the FRED macro regime panel with yield curve, credit spreads, VIX structure."""
    m = fetch_macro_regime()
    if m.get('error') and not m.get('yield_curve_value'):
        return f"""<section class="glass-card" style="margin-bottom:2rem; opacity:.6;">
            <h3 style="margin:0 0 .3rem 0; font-size:1rem;">Macro Regime (FRED)</h3>
            <p class="text-muted" style="font-size:.8em; margin:0;">Data unavailable — {m.get('error','check FRED connectivity')}</p>
        </section>"""

    score = m.get('regime_score', 50)
    label = m.get('regime_label', 'CAUTIOUS')
    color = m.get('regime_color', 'var(--accent-marginal)')
    border = ('rgba(74,222,128,.3)' if label == 'RISK_ON'
              else 'rgba(248,113,113,.3)' if label == 'RISK_OFF'
              else 'rgba(251,191,36,.15)')

    def _cell(name, value, signal, expl):
        sig_color = ('var(--accent-optimal)' if 'NORMAL' in str(signal) or 'TIGHT_' not in str(signal) and 'CONTANGO' in str(signal) or 'LOOSE' in str(signal) or 'ON_TARGET' in str(signal)
                     else 'var(--accent-poor)' if 'INVERTED' in str(signal) or 'STRESS' in str(signal) or 'BACKWARDATION' in str(signal) or 'HIGH' in str(signal) or 'TIGHT' in str(signal)
                     else 'var(--accent-marginal)')
        val_str = f"{value:.2f}" if isinstance(value, float) else str(value) if value else "N/A"
        return f"""<div style="padding:.75rem 1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
            <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.07em; margin-bottom:3px;">{name}</div>
            <div style="font-size:1rem; font-weight:700; color:#e2e8f0;">{val_str}</div>
            <div style="font-size:.7rem; color:{sig_color}; font-weight:600;">{signal}</div>
            <div style="font-size:.65rem; color:var(--text-secondary); margin-top:3px; line-height:1.4;">{expl}</div>
        </div>"""

    cells = [
        _cell("Yield Curve (10Y–2Y)", m.get('yield_curve_value'), m.get('yield_curve_signal',''),
              "Positive = healthy growth. Negative = recession warning."),
        _cell("HY Credit Spread", m.get('hy_spread_value'), m.get('hy_spread_signal',''),
              "Below 4% = calm markets. Above 6% = institutions pricing in stress."),
        _cell("5Y Inflation Break-even", m.get('inflation_value'), m.get('inflation_signal',''),
              "2–2.5% = on target. Above 3% = headwind for growth stocks."),
        _cell("VIX (30d)", m.get('vix_value'), m.get('vix_signal',''),
              "Below 15 = calm. Above 30 = fear. Term structure: VIX3M÷VIX."),
        _cell("Financial Conditions (NFCI)", m.get('nfci_value'), m.get('nfci_signal',''),
              "Below 0 = loose/accommodative. Above 0 = tighter = headwind."),
    ]
    cells_html = ''.join(cells)
    expl = m.get('regime_explanation', '')

    return f"""
    <section class="glass-card" style="margin-bottom:2rem; padding:1.5rem; border:1px solid {border};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1.5rem; margin-bottom:1.25rem;">
            <div>
                <div style="display:flex; align-items:center; gap:.75rem; margin-bottom:.4rem;">
                    <h3 style="margin:0; font-size:1rem;">Macro Regime Dashboard (FRED)</h3>
                    <span style="font-size:.7rem; border:1px solid {color}; color:{color}; padding:2px 8px; border-radius:4px; text-transform:uppercase; letter-spacing:.05em;">Regime Signal</span>
                </div>
                <p class="text-muted" style="font-size:.78em; margin:0 0 .5rem 0;">{expl}</p>
            </div>
            <div style="text-align:center; padding:.75rem 1.25rem; background:rgba(255,255,255,.04); border-radius:8px; border:1px solid {color}; min-width:120px;">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.07em; margin-bottom:4px;">Regime Score</div>
                <div style="font-size:1.8rem; font-weight:700; color:{color};">{score}/100</div>
                <div style="font-size:.75rem; font-weight:600; color:{color};">{label.replace('_',' ')}</div>
            </div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:.75rem;">
            {cells_html}
        </div>
    </section>"""


# ---------------------------------------------------------------------------
# Market Breadth section
# ---------------------------------------------------------------------------

def _generate_breadth_html() -> str:
    """Renders the Market Breadth panel with % above MAs and A/D trend."""
    b = fetch_market_breadth(use_cache=True)
    if b.get('health_score') is None:
        return f"""<section class="glass-card" style="margin-bottom:2rem; opacity:.6;">
            <h3 style="margin:0 0 .3rem 0; font-size:1rem;">Market Breadth (S&amp;P 500)</h3>
            <p class="text-muted" style="font-size:.8em; margin:0;">Data unavailable — breadth requires downloading S&amp;P 500 constituents.</p>
        </section>"""

    health   = b.get('health_score', 50)
    label    = b.get('health_label', 'MIXED')
    color    = b.get('health_color', 'var(--accent-marginal)')
    pct20    = b.get('pct_above_20wk', 0)
    pct40    = b.get('pct_above_40wk', 0)
    net_hl   = b.get('net_new_highs', 0)
    ad_trend = b.get('ad_trend', 0)
    n_stocks = b.get('stocks_analyzed', 0)
    expl     = b.get('explanation', '')
    interp   = b.get('interpretation', '')

    ad_color = 'var(--accent-optimal)' if ad_trend >= 0 else 'var(--accent-poor)'
    hl_color = 'var(--accent-optimal)' if net_hl >= 0 else 'var(--accent-poor)'
    border = ('rgba(74,222,128,.3)' if health >= 70
              else 'rgba(248,113,113,.3)' if health < 35
              else 'rgba(251,191,36,.15)')

    def _bar(pct, col):
        return (f'<div style="width:100%; height:8px; background:rgba(255,255,255,.1); border-radius:4px; overflow:hidden;">'
                f'<div style="width:{pct:.0f}%; height:100%; background:{col}; border-radius:4px;"></div></div>')

    pct20_col = 'var(--accent-optimal)' if pct20 >= 60 else 'var(--accent-marginal)' if pct20 >= 40 else 'var(--accent-poor)'
    pct40_col = 'var(--accent-optimal)' if pct40 >= 50 else 'var(--accent-marginal)' if pct40 >= 30 else 'var(--accent-poor)'

    return f"""
    <section class="glass-card" style="margin-bottom:2rem; padding:1.5rem; border:1px solid {border};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1.5rem; margin-bottom:1.25rem;">
            <div>
                <div style="display:flex; align-items:center; gap:.75rem; margin-bottom:.4rem;">
                    <h3 style="margin:0; font-size:1rem;">Market Breadth (S&amp;P 500 — {n_stocks} stocks)</h3>
                    <span style="font-size:.7rem; border:1px solid {color}; color:{color}; padding:2px 8px; border-radius:4px; text-transform:uppercase;">{label.replace('_',' ')}</span>
                </div>
                <p class="text-muted" style="font-size:.78em; margin:0 0 .5rem 0;">{expl}</p>
            </div>
            <div style="text-align:center; padding:.75rem 1.25rem; background:rgba(255,255,255,.04); border-radius:8px; border:1px solid {color}; min-width:120px;">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.07em; margin-bottom:4px;">Health Score</div>
                <div style="font-size:1.8rem; font-weight:700; color:{color};">{health}/100</div>
            </div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:1rem; margin-bottom:1rem;">
            <div style="padding:.75rem 1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; margin-bottom:6px;">% Above 20-Week MA</div>
                {_bar(pct20, pct20_col)}
                <div style="font-size:1.1rem; font-weight:700; color:{pct20_col}; margin-top:4px;">{pct20:.1f}%</div>
                <div style="font-size:.65rem; color:var(--text-secondary);">Target: &gt;60% for healthy market</div>
            </div>
            <div style="padding:.75rem 1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; margin-bottom:6px;">% Above 40-Week MA (200d equiv)</div>
                {_bar(pct40, pct40_col)}
                <div style="font-size:1.1rem; font-weight:700; color:{pct40_col}; margin-top:4px;">{pct40:.1f}%</div>
                <div style="font-size:.65rem; color:var(--text-secondary);">Bull market: &gt;50%. Bear: &lt;30%.</div>
            </div>
            <div style="padding:.75rem 1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; margin-bottom:6px;">Net New 52-Week Highs</div>
                <div style="font-size:1.1rem; font-weight:700; color:{hl_color}; margin-top:4px;">{net_hl:+d}</div>
                <div style="font-size:.65rem; color:var(--text-secondary);">Positive = more highs than lows</div>
            </div>
            <div style="padding:.75rem 1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; margin-bottom:6px;">A/D Breadth Trend (4W)</div>
                <div style="font-size:1.1rem; font-weight:700; color:{ad_color}; margin-top:4px;">{ad_trend:+.1f}</div>
                <div style="font-size:.65rem; color:var(--text-secondary);">Positive = improving participation</div>
            </div>
        </div>
        <p style="font-size:.8em; color:var(--text-secondary); margin:0;">{interp}</p>
    </section>"""


# ---------------------------------------------------------------------------
# Basket Intelligence section
# ---------------------------------------------------------------------------

def _generate_basket_intelligence_html() -> str:
    """
    Fetches GVIP vs SPY basket context and renders the Basket Intelligence panel.

    First-principles logic:
      GVIP tracks the 50 stocks most commonly held as top-10 positions by
      fundamentally-driven hedge funds (Goldman Sachs Hedge Fund VIP ETF).
      When GVIP underperforms SPY, the market rally is NOT being driven by
      genuine fundamental conviction — it's being led by mechanical short
      covering in crowded shorts. Sector-level signals should be interpreted
      with caution in a short-squeeze regime.
    """
    bc = fetch_basket_context()

    signal = bc.get('signal', 'NEUTRAL')
    signal_label = bc.get('signal_label', 'Neutral')
    signal_color = bc.get('signal_color', 'var(--accent-marginal)')
    error = bc.get('error')

    if error or bc.get('relative_5d') is None:
        return f"""
    <section class="glass-card" style="margin-bottom:2rem; padding:1.25rem 1.5rem; opacity:0.65;">
        <h3 style="margin:0 0 0.4rem 0; font-size:1rem;">Basket Intelligence</h3>
        <p class="text-muted" style="font-size:0.8em; margin:0;">Data unavailable &mdash; {error or 'run analysis to populate'}</p>
    </section>"""

    gvip_5d = bc['gvip_5d']
    spy_5d = bc['spy_5d']
    rel_5d = bc['relative_5d']
    rel_20d = bc['relative_20d']
    gvip_price = bc.get('gvip_price', 0)
    spy_price = bc.get('spy_price', 0)

    def _col(v):
        return "var(--accent-optimal)" if v >= 0 else "var(--accent-poor)"

    if signal == 'LONG_BASKET_LEADING':
        interpretation = (
            "Hedge fund VIP longs (GVIP) are outperforming the market. "
            "Rallies are being driven by genuine fundamental conviction — sector signals and technical entries have higher reliability."
        )
        border_color = "rgba(74,222,128,0.3)"
    elif signal == 'SHORT_SQUEEZE_REGIME':
        interpretation = (
            "GVIP longs are lagging SPY — the broader market rally is being driven by forced short covering in "
            "crowded shorts, not fundamental buying. Sector tailwinds may be overstated; treat breakouts with caution "
            "until GVIP catches up."
        )
        border_color = "rgba(248,113,113,0.3)"
    else:
        interpretation = (
            "No significant divergence between hedge fund longs and the broader market. "
            "Moves are consistent with normal participation. Evaluate sector signals on their own merit."
        )
        border_color = "rgba(251,191,36,0.15)"

    metrics = [
        ("GVIP 5D", f"{gvip_5d:+.1f}%", _col(gvip_5d), f"${gvip_price:.2f}"),
        ("SPY 5D",  f"{spy_5d:+.1f}%",  _col(spy_5d),  f"${spy_price:.2f}"),
    ]
    metric_cells = ""
    for label, val, col, sub in metrics:
        metric_cells += f"""
        <div style="text-align:center; padding:0.75rem 1rem;
            background:rgba(255,255,255,0.03); border-radius:8px;
            border:1px solid rgba(255,255,255,0.08);">
            <div style="font-size:0.65rem; color:var(--text-secondary); text-transform:uppercase;
                letter-spacing:0.07em; margin-bottom:4px;">{label}</div>
            <div style="font-size:1.1rem; font-weight:700; color:{col};">{val}</div>
            <div style="font-size:0.7rem; color:var(--text-secondary);">{sub}</div>
        </div>"""

    return f"""
    <section class="glass-card" style="margin-bottom:2rem; padding:1.5rem; border:1px solid {border_color};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1.5rem;">
            <div style="flex:1; min-width:260px;">
                <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem;">
                    <h3 style="margin:0; font-size:1rem;">Basket Intelligence</h3>
                    <span style="font-size:0.7rem; border:1px solid {signal_color}; color:{signal_color};
                        padding:2px 8px; border-radius:4px; text-transform:uppercase; letter-spacing:0.05em;">
                        Positioning Signal
                    </span>
                </div>
                <p class="text-muted" style="font-size:0.78em; margin:0 0 0.75rem 0;">
                    GVIP (Goldman Sachs Hedge Fund VIP ETF) vs SPY &mdash; proxy for hedge fund crowded-long conviction
                </p>
                <div style="font-size:1.05rem; font-weight:600; color:{signal_color}; margin-bottom:0.5rem;">
                    {signal_label}
                </div>
                <p style="font-size:0.8em; color:var(--text-secondary); margin:0; line-height:1.5;">
                    {interpretation}
                </p>
            </div>
            <div style="display:flex; gap:1rem; flex-wrap:wrap; align-items:center;">
                {metric_cells}
                <div style="text-align:center; padding:0.75rem 1.25rem;
                    background:rgba(255,255,255,0.04); border-radius:8px;
                    border:1px solid {signal_color}; min-width:110px;">
                    <div style="font-size:0.65rem; color:var(--text-secondary); text-transform:uppercase;
                        letter-spacing:0.07em; margin-bottom:4px;">Relative 5D</div>
                    <div style="font-size:1.4rem; font-weight:700; color:{signal_color};">{rel_5d:+.1f}%</div>
                    <div style="font-size:0.65rem; color:var(--text-secondary);">GVIP &minus; SPY</div>
                </div>
                <div style="text-align:center; padding:0.75rem 1rem;
                    background:rgba(255,255,255,0.03); border-radius:8px;
                    border:1px solid rgba(255,255,255,0.08);">
                    <div style="font-size:0.65rem; color:var(--text-secondary); text-transform:uppercase;
                        letter-spacing:0.07em; margin-bottom:4px;">Relative 20D</div>
                    <div style="font-size:1.1rem; font-weight:700; color:{_col(rel_20d)};">{rel_20d:+.1f}%</div>
                    <div style="font-size:0.65rem; color:var(--text-secondary);">Trend</div>
                </div>
            </div>
        </div>
    </section>"""


# ---------------------------------------------------------------------------
# Main page generator
# ---------------------------------------------------------------------------

def generate_macro_page(
    config: Dict,
    sector_drivers_map: Dict[str, List[DriverAnalysis]],
    sector_closes: pd.DataFrame,
    output_dir: str
):
    """Generates the reports/macro_drivers.html page."""

    # 1. Macro Scorecard
    scorecard_html = generate_macro_scorecard_html(sector_drivers_map, config)

    # 2. Macro Regime Panel
    regime_html = generate_macro_regime_panel_html(sector_drivers_map)

    # 3. Correlation Heatmap (sortable)
    heatmap_html = generate_correlation_heatmap(sector_drivers_map, sector_closes)

    # 4. Insights Sidebar (live correlations)
    sidebar_html = generate_economic_insights_sidebar(sector_drivers_map)

    # 4b. Basket Intelligence section
    basket_intel_html = _generate_basket_intelligence_html()

    # 4c. FRED Macro Regime panel
    fred_html = _generate_fred_macro_html()

    # 4d. Market Breadth panel
    breadth_html_section = _generate_breadth_html()

    # 4e. Sector Rotation Map (RRG)
    rrg_data = calculate_rrg()
    rrg_section_html = generate_rrg_html(rrg_data)

    # 5. Sector filter pills
    all_etfs = sorted(sector_drivers_map.keys())
    filter_pills_html = '<div id="sector-filter-pills" style="display:flex; flex-wrap:wrap; gap:0.5rem; margin-bottom:1.5rem;">'
    filter_pills_html += """<button class="sector-pill" data-etf="" onclick="filterSector('')" style="
        background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.2);
        color:var(--text-primary); padding:5px 14px; border-radius:20px;
        cursor:pointer; font-size:0.8rem; transition:all 0.15s;">All Sectors</button>"""
    for etf in all_etfs:
        sector_name = config['sectors'][etf]['name'] if etf in config.get('sectors', {}) else etf
        filter_pills_html += f"""<button class="sector-pill" data-etf="{etf}" onclick="filterSector('{etf}')" style="
            background:rgba(96,165,250,0.1); border:1px solid rgba(96,165,250,0.25);
            color:#60a5fa; padding:5px 14px; border-radius:20px;
            cursor:pointer; font-size:0.8rem; transition:all 0.15s;">{etf}</button>"""
    filter_pills_html += '</div>'

    # 6. Grid of driver cards
    chart_grid = filter_pills_html

    def fmt_chg(v: float) -> str:
        color = "var(--accent-optimal)" if v >= 0 else "var(--accent-poor)"
        sign = "+" if v >= 0 else ""
        return f'<span style="color:{color}; font-weight:600;">{sign}{v*100:.1f}%</span>'

    def arrow_chg(v: float) -> str:
        """Colored arrow + percent for 1W momentum."""
        color = "var(--accent-optimal)" if v >= 0 else "var(--accent-poor)"
        arrow = "↑" if v >= 0 else "↓"
        return f'<span style="color:{color}; font-weight:700;">{arrow} {abs(v*100):.1f}%</span>'

    for etf, drivers in sector_drivers_map.items():
        if not drivers:
            continue

        sector_name = config['sectors'][etf]['name']
        macro_label, macro_color, _ = _sector_macro_signal(drivers)

        sector_section = f"""
        <div class="sector-group" data-sector="{etf}" style="margin-bottom: 3rem;">
            <h2 style="border-bottom:1px solid var(--grid-color); padding-bottom:0.5rem;
                margin-bottom:1.5rem; color:var(--text-primary);
                display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
                <span style="background:rgba(96,165,250,0.2); color:#60a5fa;
                    padding:4px 8px; border-radius:4px; font-size:0.8em;">{etf}</span>
                {sector_name}
                <span style="font-size:0.75rem; color:{macro_color}; border:1px solid {macro_color};
                    padding:2px 10px; border-radius:12px; margin-left:4px;">{macro_label}</span>
            </h2>
            <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(350px, 1fr)); gap:1.5rem;">
        """

        for d in drivers:
            sector_price_series = sector_closes[etf] if etf in sector_closes.columns else None

            chart_svg = generate_detailed_driver_chart_svg(
                d.prices, d.name,
                d.ticker + " • 1Y",
                sector_prices=sector_price_series,
                sector_name=etf,
                width=380, height=250
            )

            trend_color = "var(--accent-optimal)" if d.trend == "BULLISH" else "var(--accent-poor)"
            curr_val_str = f"{d.current_price:.2f}"

            # Improvement 6: range context label
            rng = d.high_52w - d.low_52w
            pct_in_range = ((d.current_price - d.low_52w) / rng * 100) if rng > 0 else 50
            pct_in_range = max(0.0, min(100.0, pct_in_range))
            pct_off_high = ((d.current_price / d.high_52w) - 1) * 100 if d.high_52w else 0
            off_high_html = fmt_chg(pct_off_high / 100)

            if pct_in_range >= 85:
                range_context = '<span style="color:var(--accent-optimal); font-size:0.65rem; font-weight:600; margin-left:4px;">Near Highs</span>'
            elif pct_in_range <= 15:
                range_context = '<span style="color:var(--accent-poor); font-size:0.65rem; font-weight:600; margin-left:4px;">Near Lows</span>'
            else:
                range_context = f'<span style="color:var(--text-secondary); font-size:0.65rem; margin-left:4px;">{pct_in_range:.0f}th pctile</span>'

            # Improvement 4: driver alert badges
            alert_badges = []
            if pct_in_range >= 95:
                alert_badges.append('<span style="background:rgba(74,222,128,0.2); color:var(--accent-optimal); '
                                    'border:1px solid rgba(74,222,128,0.4); padding:1px 6px; '
                                    'border-radius:4px; font-size:0.6rem; font-weight:700;">52W HIGH</span>')
            elif pct_in_range <= 5:
                alert_badges.append('<span style="background:rgba(248,113,113,0.2); color:var(--accent-poor); '
                                    'border:1px solid rgba(248,113,113,0.4); padding:1px 6px; '
                                    'border-radius:4px; font-size:0.6rem; font-weight:700;">52W LOW</span>')
            if abs(d.change_1m) > 0.10:
                alert_badges.append('<span style="background:rgba(251,191,36,0.2); color:var(--accent-marginal); '
                                    'border:1px solid rgba(251,191,36,0.4); padding:1px 6px; '
                                    'border-radius:4px; font-size:0.6rem; font-weight:700;">EXTREME MOVE</span>')
            if d.change_1m * d.change_3m < 0:
                alert_badges.append('<span style="background:rgba(167,139,250,0.2); color:#a78bfa; '
                                    'border:1px solid rgba(167,139,250,0.4); padding:1px 6px; '
                                    'border-radius:4px; font-size:0.6rem; font-weight:700;">TREND FLIP</span>')

            alert_row = ''
            if alert_badges:
                alert_row = (f'<div style="display:flex; flex-wrap:wrap; gap:4px; '
                             f'margin-bottom:6px;">' + ''.join(alert_badges) + '</div>')

            card = f"""
            <div class="driver-card glass-card">
                {alert_row}
                <div style="margin-bottom:10px;">
                    {chart_svg}
                </div>

                <!-- Current Value Stats Row -->
                <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:6px;
                    padding:10px 0; border-top:1px solid var(--grid-color);
                    border-bottom:1px solid var(--grid-color); margin-bottom:8px; text-align:center;">
                    <div>
                        <div style="font-size:0.7em; color:var(--text-muted); margin-bottom:2px;">CURRENT</div>
                        <div style="font-size:1.1em; font-weight:700; color:#e2e8f0;">{curr_val_str}</div>
                    </div>
                    <div>
                        <div style="font-size:0.7em; color:var(--text-muted); margin-bottom:2px;">52W HIGH</div>
                        <div style="font-size:0.95em; font-weight:600; color:var(--text-secondary);">{d.high_52w:.2f}</div>
                    </div>
                    <div>
                        <div style="font-size:0.7em; color:var(--text-muted); margin-bottom:2px;">52W LOW</div>
                        <div style="font-size:0.95em; font-weight:600; color:var(--text-secondary);">{d.low_52w:.2f}</div>
                    </div>
                </div>

                <!-- 52W Range Bar (Improvement 6) -->
                <div style="padding:4px 0 8px 0;">
                    <div style="display:flex; justify-content:space-between; font-size:0.7em;
                        color:var(--text-muted); margin-bottom:3px; align-items:center;">
                        <span>52W Range {range_context}</span>
                        <span>{off_high_html} from high</span>
                    </div>
                    <div style="background:rgba(255,255,255,0.08); border-radius:4px; height:5px; position:relative;">
                        <div style="position:absolute; left:0; top:0; height:100%;
                            width:{pct_in_range:.0f}%; background:linear-gradient(to right,#f87171,#60a5fa);
                            border-radius:4px;"></div>
                        <div style="position:absolute; top:-3px; left:{pct_in_range:.0f}%;
                            transform:translateX(-50%); width:10px; height:10px;
                            border-radius:50%; background:#e2e8f0; border:2px solid #1e293b;"></div>
                    </div>
                </div>

                <!-- Performance Row: 1W (new) + 1M + 3M + YTD (Improvement 8) -->
                <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:4px;
                    margin-bottom:8px; text-align:center;">
                    <div style="font-size:0.75em;">
                        <div style="color:var(--text-muted); margin-bottom:1px;">1W</div>
                        {arrow_chg(d.change_1w)}
                    </div>
                    <div style="font-size:0.75em;">
                        <div style="color:var(--text-muted); margin-bottom:1px;">1M</div>
                        {fmt_chg(d.change_1m)}
                    </div>
                    <div style="font-size:0.75em;">
                        <div style="color:var(--text-muted); margin-bottom:1px;">3M</div>
                        {fmt_chg(d.change_3m)}
                    </div>
                    <div style="font-size:0.75em;">
                        <div style="color:var(--text-muted); margin-bottom:1px;">YTD</div>
                        {fmt_chg(d.change_ytd)}
                    </div>
                </div>

                <!-- Correlation & Trend -->
                <div style="display:flex; justify-content:space-between; align-items:center;
                    padding-top:8px; border-top:1px solid var(--grid-color);">
                    <div style="font-size:0.85em; color:var(--text-muted);">
                        Corr to {etf}: <span style="color:#e2e8f0; font-weight:bold;">{d.correlation_90d:.2f}</span>
                    </div>
                    <div style="font-size:0.8em; font-weight:bold; padding:2px 8px;
                        border-radius:4px; border:1px solid {trend_color};
                        color:{trend_color}; text-transform:uppercase;">
                        {d.trend}
                    </div>
                </div>
            </div>
            """
            sector_section += card

        sector_section += "</div></div>"
        chart_grid += sector_section

    # Assemble full page
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Macro Drivers | Macro Watch 2.1</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        {CSS_DARK_THEME}

        .dashboard-layout {{
            display: grid;
            grid-template-columns: 1fr 300px;
            gap: 2rem;
        }}
        @media (max-width: 1000px) {{
            .dashboard-layout {{ grid-template-columns: 1fr; }}
        }}

        .insight-card {{
            background: linear-gradient(135deg, rgba(30,41,59,0.4), rgba(15,23,42,0.6));
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
        .insight-item:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
        .insight-item h4 {{ color: var(--text-primary); margin: 0 0 0.5rem 0; font-size: 1rem; }}
        .insight-item p {{ color: var(--text-secondary); font-size: 0.9em; margin: 0 0 0.5rem 0; line-height: 1.5; }}
        .insight-stat {{
            display: inline-block;
            background: rgba(74,222,128,0.1);
            color: var(--accent-optimal);
            border: 1px solid rgba(74,222,128,0.3);
            padding: 2px 8px; border-radius: 4px;
            font-size: 0.8em; font-weight: bold; margin-bottom: 0.5rem;
        }}
        .insight-stat.negative {{
            background: rgba(248,113,113,0.1); color: var(--accent-poor);
            border: 1px solid rgba(248,113,113,0.3);
        }}

        .driver-card {{ transition: transform 0.2s, box-shadow 0.2s; }}
        .driver-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.3);
            border-color: var(--accent-info);
        }}

        .sector-pill.active {{
            background: rgba(96,165,250,0.25) !important;
            border-color: rgba(96,165,250,0.6) !important;
            color: #93c5fd !important;
        }}

        .heatmap-th:hover {{ background: rgba(255,255,255,0.05); }}

        .nav-link {{
            color: var(--text-muted); fill: var(--text-muted);
            text-decoration: none; display: flex; align-items: center;
            gap: 8px; padding: 8px 12px; border-radius: 6px; transition: all 0.2s;
        }}
        .nav-link:hover {{
            background: rgba(255,255,255,0.05);
            color: var(--text-primary); fill: var(--text-primary);
        }}
        :root {{ --grid-color: rgba(255,255,255,0.08); }}
        h3 {{ color: var(--text-primary); margin-bottom: 1rem; margin-top: 0; }}
    </style>
</head>
<body>
    {generate_top_nav("macro_drivers")}
    <div class="container" style="max-width:1600px;">
        {generate_breadcrumb([("Command Center", "index.html"), ("Macro Drivers", None)])}
        <header style="display:flex; justify-content:space-between; align-items:center;
            margin-bottom:2rem; padding-bottom:1rem; border-bottom:1px solid var(--grid-color);">
            <div>
                <h1 style="margin:0; background:linear-gradient(to right,#60a5fa,#a78bfa);
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                    Macro Drivers Analysis
                </h1>
                <p class="text-muted" style="margin-top:0.5rem;">Cross-Sector Economic Indicators &amp; Commodities</p>
            </div>
            <div style="text-align:right; font-size:0.8em; color:var(--text-muted);">
                Heatmap: 90-Day Correlation<br>Updates Weekly
            </div>
        </header>

        <!-- Macro Scorecard (Improvement 1) -->
        {scorecard_html}

        <!-- Macro Regime Panel (Improvement 2) -->
        {regime_html}

        <!-- FRED Macro Regime -->
        {fred_html}

        <!-- Market Breadth -->
        {breadth_html_section}

        <!-- Basket Intelligence -->
        {basket_intel_html}

        <main class="dashboard-layout">
            <div class="main-content">
                <!-- Sector Rotation Map (RRG) -->
                {rrg_section_html}
            </div>
        </main>
        <main class="dashboard-layout">
            <div class="main-content">
                <!-- Correlation Heatmap (Improvement 7) -->
                <section style="margin-bottom:3rem;">
                    <h3>Cross-Sector Correlation Matrix ("Optimizer")</h3>
                    <p class="text-muted" style="margin-bottom:1.5rem; font-size:0.9em;">
                        <span style="color:var(--accent-optimal);">Green</span> = positive correlation,
                        <span style="color:var(--accent-poor);">Red</span> = negative. Cells with <strong>|r| &gt; 0.50</strong>
                        have a highlight ring. <strong>Click any sector header</strong> to sort by strength.
                    </p>
                    {heatmap_html}
                </section>

                <!-- Sector Driver Cards (Improvements 4, 5, 6, 8) -->
                {chart_grid}
            </div>

            <!-- Sidebar (Improvement 3) -->
            {sidebar_html}
        </main>

        <footer style="margin-top:4rem; text-align:center; color:var(--text-secondary);
            border-top:1px solid var(--grid-color); padding-top:2rem;">
            <p>Macro Watch 2.1 • Unified Intelligence Layer</p>
        </footer>
    </div>
    {INTERACTIVE_JS}
    {_SECTOR_FILTER_JS}
</body>
</html>"""

    out_path = os.path.join(output_dir, "macro_drivers.html")
    with open(out_path, "w") as f:
        f.write(full_html)

    print(f"Macro Drivers Page saved to {out_path}")
