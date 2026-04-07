"""
Relative Rotation Graph (RRG) module.

First-principles explanation:
  An RRG plots each sector on a 2-axis chart:
    X-axis = Relative Strength vs benchmark (is it outperforming?)
    Y-axis = RS Momentum (is that outperformance accelerating or decelerating?)

  This creates four quadrants that sectors rotate through clockwise:
    LEADING    (top-right):  strong RS + rising momentum  → buy/hold sector
    WEAKENING  (bottom-right): strong RS + falling momentum → watch for exit
    LAGGING    (bottom-left): weak RS + falling momentum  → avoid/short
    IMPROVING  (top-left):   weak RS + rising momentum   → early accumulate

  The rotation is clockwise because strength precedes momentum which precedes decay.
  Most institutional sector strategists watch this weekly to manage allocation.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, List, Any
import json

SECTOR_ETFS = {
    'XLK':  'Technology',
    'XLF':  'Financials',
    'XLV':  'Health Care',
    'XLE':  'Energy',
    'XLI':  'Industrials',
    'XLY':  'Consumer Disc.',
    'XLP':  'Consumer Staples',
    'XLB':  'Materials',
    'XLRE': 'Real Estate',
    'XLU':  'Utilities',
    'XLC':  'Communication',
}

BENCHMARK = 'SPY'
RRG_SMOOTHING = 10      # periods for JdK RS-Ratio smoothing
RRG_MOMENTUM_PERIOD = 4  # periods for momentum calculation


def _calculate_jdk_rs(price_series: pd.Series, benchmark: pd.Series) -> pd.Series:
    """
    JdK RS-Ratio: smoothed relative strength normalized to 100.
    RS = (price / benchmark) normalised so that 100 = benchmark level.
    """
    # Raw relative strength
    rs_raw = (price_series / benchmark) * 100

    # Normalise to 100-centered (JdK approach uses a longer smoothing)
    rs_smoothed = rs_raw.rolling(window=RRG_SMOOTHING, min_periods=1).mean()

    # Normalise so the mean over the period = 100
    rs_mean = rs_smoothed.mean()
    if rs_mean == 0:
        return rs_smoothed
    rs_ratio = (rs_smoothed / rs_mean) * 100
    return rs_ratio


def _calculate_rs_momentum(rs_ratio: pd.Series) -> pd.Series:
    """
    JdK RS-Momentum: rate of change of the RS-Ratio.
    Normalised to 100 in the same way.
    """
    momentum_raw = rs_ratio.pct_change(periods=RRG_MOMENTUM_PERIOD) * 100
    # Normalise around 100
    momentum_smoothed = momentum_raw.rolling(window=RRG_SMOOTHING, min_periods=1).mean()
    momentum_mean = momentum_smoothed.mean()
    if momentum_mean == 0 or np.isnan(momentum_mean):
        return momentum_smoothed + 100  # center at 100
    return (momentum_smoothed / abs(momentum_mean)) * 100 + 100


def _quadrant(rs_ratio: float, rs_momentum: float) -> Dict[str, str]:
    """Assign quadrant label, color and interpretation."""
    above_rs = rs_ratio >= 100
    above_mom = rs_momentum >= 100

    if above_rs and above_mom:
        return {
            'name': 'LEADING',
            'label': 'Leading',
            'color': '#4ade80',
            'action': 'Overweight — sector showing both strength and acceleration',
            'icon': '🟢',
        }
    elif above_rs and not above_mom:
        return {
            'name': 'WEAKENING',
            'label': 'Weakening',
            'color': '#fbbf24',
            'action': 'Watch — outperforming but momentum fading, prepare to reduce',
            'icon': '🟡',
        }
    elif not above_rs and not above_mom:
        return {
            'name': 'LAGGING',
            'label': 'Lagging',
            'color': '#f87171',
            'action': 'Underweight — weak performance and still decelerating',
            'icon': '🔴',
        }
    else:  # below RS, above momentum
        return {
            'name': 'IMPROVING',
            'label': 'Improving',
            'color': '#38bdf8',
            'action': 'Watch for entry — underperforming but momentum turning up',
            'icon': '🔵',
        }


def calculate_rrg(period: str = '1y') -> Dict[str, Any]:
    """
    Calculate Relative Rotation Graph data for all 11 S&P 500 sector ETFs vs SPY.

    Returns a dict with:
      sectors: list of sector dicts with rs_ratio, rs_momentum, quadrant, trail
      leading / weakening / lagging / improving: lists of sector names by quadrant
      dominant_quadrant: which quadrant has the most sectors
      explanation: educational text
      interpretation: current market read
      chart_data: JSON-serialisable data for Plotly scatter
    """
    result: Dict[str, Any] = {
        'sectors': [],
        'leading': [],
        'weakening': [],
        'lagging': [],
        'improving': [],
        'dominant_quadrant': 'MIXED',
        'explanation': (
            "The Relative Rotation Graph (RRG) shows where each market sector sits in "
            "its performance cycle. The X-axis measures whether a sector is outperforming "
            "the S&P 500 (right = stronger). The Y-axis measures whether that "
            "outperformance is accelerating (up = gaining momentum). Sectors rotate "
            "clockwise: Leading → Weakening → Lagging → Improving → back to Leading. "
            "The best time to buy a sector is when it moves from Improving into Leading. "
            "The best time to reduce exposure is when it rolls from Leading into Weakening."
        ),
        'interpretation': 'Data unavailable',
        'chart_data': [],
        'error': None,
    }

    try:
        all_tickers = list(SECTOR_ETFS.keys()) + [BENCHMARK]
        raw = yf.download(
            all_tickers, period=period, interval='1wk',
            progress=False, multi_level_index=False,
        )

        # Handle single vs multi-ticker column structure
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw['Close'].dropna(how='all')
        else:
            # Single ticker fallback (shouldn't happen here but be safe)
            prices = pd.DataFrame({'SPY': raw['Close']})

        if BENCHMARK not in prices.columns:
            result['error'] = 'Could not fetch SPY benchmark data'
            return result

        benchmark_prices = prices[BENCHMARK].dropna()

        # Trail length: last 8 weeks for the rotation path
        TRAIL_WEEKS = 8

        sector_data = []
        for etf, name in SECTOR_ETFS.items():
            if etf not in prices.columns:
                continue

            sector_prices = prices[etf].dropna()
            if len(sector_prices) < 30:
                continue

            # Align to common index
            common_idx = sector_prices.index.intersection(benchmark_prices.index)
            if len(common_idx) < 30:
                continue

            sp = sector_prices.loc[common_idx]
            bp = benchmark_prices.loc[common_idx]

            rs_ratio = _calculate_jdk_rs(sp, bp)
            rs_momentum = _calculate_rs_momentum(rs_ratio)

            if rs_ratio.empty or rs_momentum.empty:
                continue

            # Current position
            current_rs = float(rs_ratio.iloc[-1])
            current_mom = float(rs_momentum.iloc[-1])

            # Trail: last TRAIL_WEEKS positions
            trail_rs = rs_ratio.iloc[-TRAIL_WEEKS:].tolist()
            trail_mom = rs_momentum.iloc[-TRAIL_WEEKS:].tolist()
            trail = [
                {'x': float(x), 'y': float(y)}
                for x, y in zip(trail_rs, trail_mom)
                if not (np.isnan(x) or np.isnan(y))
            ]

            quadrant = _quadrant(current_rs, current_mom)

            # 4-week RS change for trend direction
            rs_4w_change = float(rs_ratio.iloc[-1] - rs_ratio.iloc[-5]) if len(rs_ratio) >= 5 else 0.0

            sector_data.append({
                'etf': etf,
                'name': name,
                'rs_ratio': round(current_rs, 2),
                'rs_momentum': round(current_mom, 2),
                'rs_4w_change': round(rs_4w_change, 2),
                'quadrant': quadrant['name'],
                'quadrant_label': quadrant['label'],
                'quadrant_color': quadrant['color'],
                'quadrant_action': quadrant['action'],
                'quadrant_icon': quadrant['icon'],
                'trail': trail,
            })

        if not sector_data:
            result['error'] = 'No sector data computed'
            return result

        # Tally quadrants
        for s in sector_data:
            q = s['quadrant'].lower()
            result.setdefault(q, []).append(s['etf'])

        result['sectors'] = sector_data

        # Dominant quadrant
        counts = {
            'LEADING': len(result.get('leading', [])),
            'WEAKENING': len(result.get('weakening', [])),
            'LAGGING': len(result.get('lagging', [])),
            'IMPROVING': len(result.get('improving', [])),
        }
        result['dominant_quadrant'] = max(counts, key=counts.get)

        # Overall interpretation
        leading_names = [s['name'] for s in sector_data if s['quadrant'] == 'LEADING']
        lagging_names = [s['name'] for s in sector_data if s['quadrant'] == 'LAGGING']
        improving_names = [s['name'] for s in sector_data if s['quadrant'] == 'IMPROVING']

        if leading_names:
            result['interpretation'] = (
                f"Currently leading sectors (overweight): {', '.join(leading_names)}. "
                + (f"Sectors to watch for entry (improving momentum): {', '.join(improving_names)}. " if improving_names else "")
                + (f"Avoid or underweight: {', '.join(lagging_names[:3])}." if lagging_names else "")
            )
        else:
            result['interpretation'] = (
                "No clearly dominant leading sectors currently. "
                "Market rotation is mixed — focus on individual stock RS rather than sector tailwinds."
            )

        # Chart data for Plotly
        result['chart_data'] = [
            {
                'etf': s['etf'],
                'name': s['name'],
                'x': s['rs_ratio'],
                'y': s['rs_momentum'],
                'color': s['quadrant_color'],
                'quadrant': s['quadrant_label'],
                'trail': s['trail'],
                'action': s['quadrant_action'],
            }
            for s in sector_data
        ]

    except Exception as e:
        result['error'] = str(e)

    return result


def generate_rrg_html(rrg_data: Dict[str, Any]) -> str:
    """
    Generates an interactive Plotly RRG chart as an HTML string.
    """
    if rrg_data.get('error') or not rrg_data.get('chart_data'):
        return f"""
        <div class="glass-card" style="padding:2rem; text-align:center; opacity:0.6;">
            <h3>Sector Rotation Map (RRG)</h3>
            <p class="text-muted">Data unavailable — {rrg_data.get('error', 'run --sectors to populate')}</p>
        </div>"""

    sectors = rrg_data['chart_data']
    quadrant_bg = {
        'LEADING':   'rgba(74,222,128,0.05)',
        'WEAKENING': 'rgba(251,191,36,0.05)',
        'LAGGING':   'rgba(248,113,113,0.05)',
        'IMPROVING': 'rgba(56,189,248,0.05)',
    }

    # Build Plotly traces
    import json

    traces = []
    # Quadrant background rectangles (invisible scatter for labels)
    center_x = 100
    center_y = 100

    # Main scatter trace per quadrant
    quadrant_groups = {}
    for s in sectors:
        q = s['quadrant']
        quadrant_groups.setdefault(q, []).append(s)

    quadrant_colors = {
        'Leading':   '#4ade80',
        'Weakening': '#fbbf24',
        'Lagging':   '#f87171',
        'Improving': '#38bdf8',
    }

    for q_label, q_sectors in quadrant_groups.items():
        xs = [s['x'] for s in q_sectors]
        ys = [s['y'] for s in q_sectors]
        names = [s['etf'] for s in q_sectors]
        hover = [f"<b>{s['name']} ({s['etf']})</b><br>RS Ratio: {s['x']:.1f}<br>Momentum: {s['y']:.1f}<br>{s['action']}" for s in q_sectors]
        color = quadrant_colors.get(q_label, '#94a3b8')

        traces.append({
            'type': 'scatter',
            'x': xs, 'y': ys,
            'mode': 'markers+text',
            'name': q_label,
            'text': names,
            'textposition': 'top center',
            'hovertext': hover,
            'hoverinfo': 'text',
            'marker': {
                'size': 18,
                'color': color,
                'opacity': 0.9,
                'line': {'width': 2, 'color': 'rgba(255,255,255,0.3)'},
            },
            'textfont': {'size': 11, 'color': '#e2e8f0'},
        })

    # Trail traces for each sector
    for s in sectors:
        if s.get('trail') and len(s['trail']) > 1:
            trail_x = [p['x'] for p in s['trail']]
            trail_y = [p['y'] for p in s['trail']]
            traces.append({
                'type': 'scatter',
                'x': trail_x, 'y': trail_y,
                'mode': 'lines',
                'showlegend': False,
                'hoverinfo': 'skip',
                'line': {'color': s['color'], 'width': 1, 'dash': 'dot'},
                'opacity': 0.35,
            })

    # Determine axis range
    all_x = [s['x'] for s in sectors]
    all_y = [s['y'] for s in sectors]
    x_range = [min(all_x) - 3, max(all_x) + 3]
    y_range = [min(all_y) - 3, max(all_y) + 3]
    # Ensure center (100) is visible
    x_range[0] = min(x_range[0], 97)
    x_range[1] = max(x_range[1], 103)
    y_range[0] = min(y_range[0], 97)
    y_range[1] = max(y_range[1], 103)

    layout = {
        'template': 'plotly_dark',
        'paper_bgcolor': 'rgba(0,0,0,0)',
        'plot_bgcolor': 'rgba(15,23,42,0.6)',
        'height': 520,
        'margin': {'l': 50, 'r': 20, 't': 20, 'b': 50},
        'showlegend': True,
        'legend': {
            'orientation': 'h', 'x': 0, 'y': -0.12,
            'font': {'color': '#94a3b8', 'size': 11},
        },
        'font': {'family': 'Inter, sans-serif', 'color': '#94a3b8'},
        'xaxis': {
            'title': 'JdK RS-Ratio (Relative Strength vs SPY)',
            'range': x_range,
            'showgrid': True, 'gridcolor': 'rgba(255,255,255,0.05)',
            'zeroline': False,
        },
        'yaxis': {
            'title': 'JdK RS-Momentum (Acceleration)',
            'range': y_range,
            'showgrid': True, 'gridcolor': 'rgba(255,255,255,0.05)',
            'zeroline': False,
        },
        # Quadrant divider lines
        'shapes': [
            # Vertical line at RS=100
            {'type': 'line', 'x0': 100, 'x1': 100, 'y0': y_range[0], 'y1': y_range[1],
             'line': {'color': 'rgba(255,255,255,0.25)', 'width': 1.5, 'dash': 'dash'}},
            # Horizontal line at momentum=100
            {'type': 'line', 'x0': x_range[0], 'x1': x_range[1], 'y0': 100, 'y1': 100,
             'line': {'color': 'rgba(255,255,255,0.25)', 'width': 1.5, 'dash': 'dash'}},
        ],
        'annotations': [
            {'x': x_range[1]-0.5, 'y': y_range[1]-0.5, 'xanchor': 'right', 'yanchor': 'top',
             'text': '🟢 LEADING', 'showarrow': False, 'font': {'color': '#4ade80', 'size': 10}},
            {'x': x_range[1]-0.5, 'y': y_range[0]+0.5, 'xanchor': 'right', 'yanchor': 'bottom',
             'text': '🟡 WEAKENING', 'showarrow': False, 'font': {'color': '#fbbf24', 'size': 10}},
            {'x': x_range[0]+0.5, 'y': y_range[0]+0.5, 'xanchor': 'left', 'yanchor': 'bottom',
             'text': '🔴 LAGGING', 'showarrow': False, 'font': {'color': '#f87171', 'size': 10}},
            {'x': x_range[0]+0.5, 'y': y_range[1]-0.5, 'xanchor': 'left', 'yanchor': 'top',
             'text': '🔵 IMPROVING', 'showarrow': False, 'font': {'color': '#38bdf8', 'size': 10}},
        ],
    }

    fig_json = json.dumps({'data': traces, 'layout': layout})

    # Summary table
    summary_rows = ''
    for s in sorted(rrg_data['sectors'], key=lambda x: x['rs_ratio'], reverse=True):
        icon = s['quadrant_icon']
        color = s['quadrant_color']
        rs_arrow = '▲' if s['rs_4w_change'] >= 0 else '▼'
        rs_arrow_color = '#4ade80' if s['rs_4w_change'] >= 0 else '#f87171'
        summary_rows += f"""
        <tr>
            <td class="font-mono text-sm font-bold">{s['etf']}</td>
            <td class="text-sm">{s['name']}</td>
            <td style="color:{color}; font-weight:600;">{icon} {s['quadrant_label']}</td>
            <td class="font-mono text-sm">{s['rs_ratio']:.1f}</td>
            <td class="font-mono text-sm" style="color:{rs_arrow_color};">{rs_arrow} {abs(s['rs_4w_change']):.1f}</td>
            <td class="text-xs text-muted">{s['quadrant_action']}</td>
        </tr>"""

    return f"""
    <section style="margin-bottom:3rem;">
        <div style="margin-bottom:1rem;">
            <h3 style="margin:0 0 0.25rem 0;">Sector Rotation Map (RRG)</h3>
            <p class="text-muted" style="font-size:0.85em; margin:0;">
                Clockwise rotation: Leading → Weakening → Lagging → Improving.
                Best entries: sectors moving <strong>into the Leading quadrant</strong>.
            </p>
        </div>
        <div class="glass-card" style="padding:1rem; margin-bottom:1.5rem;">
            <div id="rrg-chart"></div>
        </div>
        <div class="glass-card" style="padding:0; overflow:hidden;">
            <table class="modern-table">
                <thead>
                    <tr>
                        <th>ETF</th><th>Sector</th><th>Quadrant</th>
                        <th>RS Ratio</th><th>4W Change</th><th>Guidance</th>
                    </tr>
                </thead>
                <tbody>{summary_rows}</tbody>
            </table>
        </div>
    </section>
    <script>
    (function() {{
        var figData = {fig_json};
        if (typeof Plotly !== 'undefined') {{
            Plotly.newPlot('rrg-chart', figData.data, figData.layout,
                {{displayModeBar: false, responsive: true}});
        }}
    }})();
    </script>"""
