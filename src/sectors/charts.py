"""
Chart Generator Module for Macro Watch 2.1 (Unified)

Generates inline SVG charts for the dashboard:
- Sparklines (mini charts for sector cards)
- Price charts (1Y with 3M/6M markers, EMA overlays)
- Projection charts (target zones visualization)

All charts are pure SVG with no external dependencies.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


# -----------------------------
# Theme Colors (Dark Mode / Glassmorphism)
# -----------------------------
COLORS = {
    "bg": "#0f172a",          # Deep Navy
    "grid": "#334155",        # Slate-700
    "text": "#94a3b8",        # Slate-400
    "price": "#60a5fa",       # Blue-400
    "ema20": "#f59e0b",       # Amber-500
    "ema50": "#8b5cf6",       # Violet-500
    "green": "#4ade80",       # Green-400 (Optimal)
    "red": "#f87171",         # Red-400 (Poor)
    "target_1r": "rgba(74, 222, 128, 0.3)",
    "target_2r": "rgba(74, 222, 128, 0.2)",
    "target_3r": "rgba(74, 222, 128, 0.1)",
    "stop": "rgba(248, 113, 113, 0.3)",
    "marker": "rgba(148, 163, 184, 0.3)",
}


def _normalize_to_range(
    values: pd.Series,
    min_val: float,
    max_val: float,
    target_min: float,
    target_max: float
) -> pd.Series:
    """Normalize values from source range to target range."""
    if max_val == min_val:
        return pd.Series([target_min] * len(values), index=values.index)

    normalized = (values - min_val) / (max_val - min_val)
    return target_min + normalized * (target_max - target_min)


def _series_to_path(
    prices: pd.Series,
    width: float,
    height: float,
    padding: float = 10
) -> Tuple[str, float, float]:
    """
    Convert a price series to SVG path coordinates.

    Returns:
        - path_d: SVG path d attribute
        - y_min: Minimum price (for scale)
        - y_max: Maximum price (for scale)
    """
    prices = prices.dropna()
    if len(prices) < 2:
        return "", 0, 0

    y_min = prices.min()
    y_max = prices.max()

    # Add 5% padding to y range
    y_range = y_max - y_min
    if y_range == 0:
        y_range = y_max * 0.1 or 1
    y_min -= y_range * 0.05
    y_max += y_range * 0.05

    # Normalize x to width
    x_vals = np.linspace(padding, width - padding, len(prices))

    # Normalize y to height (invert because SVG y=0 is top)
    y_vals = _normalize_to_range(prices, y_min, y_max, height - padding, padding)

    # Build path
    path_parts = []
    for i, (x, y) in enumerate(zip(x_vals, y_vals)):
        cmd = "M" if i == 0 else "L"
        path_parts.append(f"{cmd}{x:.1f},{y:.1f}")

    return " ".join(path_parts), y_min, y_max


def generate_sparkline_svg(
    prices: pd.Series,
    width: int = 100,
    height: int = 30,
    color: str = None
) -> str:
    """
    Generate a mini sparkline chart.
    """
    prices = prices.dropna().tail(30)  # Last 30 days

    if len(prices) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'

    color = color or COLORS["price"]
    path_d, _, _ = _series_to_path(prices, width, height, padding=2)

    # Determine trend color
    trend_color = COLORS["green"] if prices.iloc[-1] >= prices.iloc[0] else COLORS["red"]

    return f'''<svg role="img" aria-label="Price sparkline" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
    <title>Price sparkline</title>
    <path d="{path_d}" fill="none" stroke="{trend_color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''


def generate_price_chart_svg(
    prices: pd.Series,
    ema_20: pd.Series = None,
    ema_50: pd.Series = None,
    width: int = 400,
    height: int = 200,
    show_markers: bool = True,
    show_grid: bool = True
) -> str:
    """
    Generate a 1-year price chart with EMA overlays.
    """
    # Use last 252 trading days (~1 year)
    prices = prices.dropna().tail(252)

    if len(prices) < 10:
        return f'<svg width="{width}" height="{height}"><text x="50%" y="50%" text-anchor="middle" fill="{COLORS["text"]}">Insufficient data</text></svg>'

    padding_left = 50
    padding_right = 10
    padding_top = 20
    padding_bottom = 30
    chart_width = width - padding_left - padding_right
    chart_height = height - padding_top - padding_bottom

    # Get price range
    all_prices = prices.copy()
    if ema_20 is not None:
        ema_20 = ema_20.reindex(prices.index).dropna()
        all_prices = pd.concat([all_prices, ema_20])
    if ema_50 is not None:
        ema_50 = ema_50.reindex(prices.index).dropna()
        all_prices = pd.concat([all_prices, ema_50])

    y_min = all_prices.min()
    y_max = all_prices.max()
    y_range = y_max - y_min
    if y_range == 0:
        y_range = y_max * 0.1 or 1
    y_min -= y_range * 0.05
    y_max += y_range * 0.05

    def price_to_y(p):
        return padding_top + chart_height - ((p - y_min) / (y_max - y_min) * chart_height)

    def idx_to_x(i, total):
        return padding_left + (i / (total - 1)) * chart_width

    svg_parts = [f'<svg role="img" aria-label="1-year price chart with EMA overlays" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    svg_parts.append('<title>1-year price chart with EMA overlays</title>')

    # Background
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="{COLORS["bg"]}" rx="8"/>')

    # Grid lines
    if show_grid:
        num_grid = 5
        for i in range(num_grid + 1):
            y = padding_top + (i / num_grid) * chart_height
            price_val = y_max - (i / num_grid) * (y_max - y_min)
            svg_parts.append(f'<line x1="{padding_left}" y1="{y:.1f}" x2="{width - padding_right}" y2="{y:.1f}" stroke="{COLORS["grid"]}" stroke-width="0.5"/>')
            svg_parts.append(f'<text x="{padding_left - 5}" y="{y:.1f}" text-anchor="end" font-size="10" fill="{COLORS["text"]}" dominant-baseline="middle">${price_val:.0f}</text>')

    # Time markers (3M, 6M)
    if show_markers and len(prices) > 63:
        markers = [
            (len(prices) - 63, "3M"),   # 3 months ago
            (len(prices) - 126, "6M"),  # 6 months ago
        ]
        for idx, label in markers:
            if 0 <= idx < len(prices):
                x = idx_to_x(idx, len(prices))
                svg_parts.append(f'<line x1="{x:.1f}" y1="{padding_top}" x2="{x:.1f}" y2="{height - padding_bottom}" stroke="{COLORS["marker"]}" stroke-width="1" stroke-dasharray="4,4"/>')
                svg_parts.append(f'<text x="{x:.1f}" y="{height - 10}" text-anchor="middle" font-size="9" fill="{COLORS["text"]}">{label}</text>')

    # EMA-50 (draw first, behind)
    if ema_50 is not None and len(ema_50) > 1:
        ema_50_aligned = ema_50.reindex(prices.index).dropna()
        if len(ema_50_aligned) > 1:
            path_parts = []
            for i, (date, val) in enumerate(ema_50_aligned.items()):
                idx = list(prices.index).index(date)
                x = idx_to_x(idx, len(prices))
                y = price_to_y(val)
                cmd = "M" if i == 0 else "L"
                path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
            svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="none" stroke="{COLORS["ema50"]}" stroke-width="1.5" stroke-dasharray="4,2" opacity="0.8"/>')

    # EMA-20
    if ema_20 is not None and len(ema_20) > 1:
        ema_20_aligned = ema_20.reindex(prices.index).dropna()
        if len(ema_20_aligned) > 1:
            path_parts = []
            for i, (date, val) in enumerate(ema_20_aligned.items()):
                idx = list(prices.index).index(date)
                x = idx_to_x(idx, len(prices))
                y = price_to_y(val)
                cmd = "M" if i == 0 else "L"
                path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
            svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="none" stroke="{COLORS["ema20"]}" stroke-width="1.5" opacity="0.8"/>')

    # Price line
    path_parts = []
    for i, (date, val) in enumerate(prices.items()):
        x = idx_to_x(i, len(prices))
        y = price_to_y(val)
        cmd = "M" if i == 0 else "L"
        path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
    svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="none" stroke="{COLORS["price"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')

    # Current price dot
    last_x = idx_to_x(len(prices) - 1, len(prices))
    last_y = price_to_y(prices.iloc[-1])
    svg_parts.append(f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="{COLORS["price"]}"/>')

    # Legend
    legend_y = padding_top + 12
    svg_parts.append(f'<line x1="{padding_left + 5}" y1="{legend_y}" x2="{padding_left + 20}" y2="{legend_y}" stroke="{COLORS["price"]}" stroke-width="2"/>')
    svg_parts.append(f'<text x="{padding_left + 25}" y="{legend_y}" font-size="9" fill="{COLORS["text"]}" dominant-baseline="middle">Price</text>')

    if ema_20 is not None:
        svg_parts.append(f'<line x1="{padding_left + 60}" y1="{legend_y}" x2="{padding_left + 75}" y2="{legend_y}" stroke="{COLORS["ema20"]}" stroke-width="1.5"/>')
        svg_parts.append(f'<text x="{padding_left + 80}" y="{legend_y}" font-size="9" fill="{COLORS["text"]}" dominant-baseline="middle">EMA20</text>')

    if ema_50 is not None:
        svg_parts.append(f'<line x1="{padding_left + 120}" y1="{legend_y}" x2="{padding_left + 135}" y2="{legend_y}" stroke="{COLORS["ema50"]}" stroke-width="1.5" stroke-dasharray="4,2"/>')
        svg_parts.append(f'<text x="{padding_left + 140}" y="{legend_y}" font-size="9" fill="{COLORS["text"]}" dominant-baseline="middle">EMA50</text>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def generate_price_with_adx_chart_svg(
    prices: pd.Series,
    ema_20: pd.Series = None,
    ema_50: pd.Series = None,
    adx: pd.Series = None,
    width: int = 500,
    height: int = 280,
    show_markers: bool = True
) -> str:
    """
    Generate a price chart with EMA overlays and an ADX sub-panel.

    Args:
        prices: Close price series
        ema_20: EMA 20 series
        ema_50: EMA 50 series
        adx: ADX indicator series
        width: Chart width
        height: Total height (price panel + ADX panel)
        show_markers: Show 3M/6M time markers

    Returns:
        SVG string with combined chart
    """
    prices = prices.dropna().tail(104)  # ~2 years weekly

    if len(prices) < 10:
        return f'<svg width="{width}" height="{height}"><text x="50%" y="50%" text-anchor="middle" fill="{COLORS["text"]}">Insufficient data</text></svg>'

    padding_left = 50
    padding_right = 10
    padding_top = 15
    padding_mid = 5  # Gap between panels
    padding_bottom = 20

    # Split height: 70% price, 30% ADX
    price_height = int((height - padding_top - padding_bottom - padding_mid) * 0.7)
    adx_height = height - padding_top - padding_bottom - padding_mid - price_height
    chart_width = width - padding_left - padding_right

    # Price panel bounds
    price_top = padding_top
    price_bottom = price_top + price_height

    # ADX panel bounds
    adx_top = price_bottom + padding_mid
    adx_bottom = adx_top + adx_height

    # Calculate price range
    all_prices = prices.copy()
    if ema_20 is not None:
        ema_20 = ema_20.reindex(prices.index).dropna()
        all_prices = pd.concat([all_prices, ema_20])
    if ema_50 is not None:
        ema_50 = ema_50.reindex(prices.index).dropna()
        all_prices = pd.concat([all_prices, ema_50])

    y_min = all_prices.min()
    y_max = all_prices.max()
    y_range = y_max - y_min
    if y_range == 0:
        y_range = y_max * 0.1 or 1
    y_min -= y_range * 0.05
    y_max += y_range * 0.05

    def price_to_y(p):
        return price_top + price_height - ((p - y_min) / (y_max - y_min) * price_height)

    def idx_to_x(i, total):
        return padding_left + (i / (total - 1)) * chart_width

    # ADX scale (0-100)
    def adx_to_y(val):
        val = max(0, min(100, val))
        return adx_top + adx_height - (val / 100 * adx_height)

    svg_parts = [f'<svg role="img" aria-label="Price chart with ADX indicator" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    svg_parts.append('<title>Price chart with ADX indicator</title>')

    # Background
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="{COLORS["bg"]}" rx="8"/>')

    # Price panel background
    svg_parts.append(f'<rect x="{padding_left}" y="{price_top}" width="{chart_width}" height="{price_height}" fill="rgba(255,255,255,0.02)" rx="4"/>')

    # ADX panel background
    svg_parts.append(f'<rect x="{padding_left}" y="{adx_top}" width="{chart_width}" height="{adx_height}" fill="rgba(255,255,255,0.02)" rx="4"/>')

    # Price grid lines
    for i in range(4):
        y = price_top + (i / 3) * price_height
        price_val = y_max - (i / 3) * (y_max - y_min)
        svg_parts.append(f'<line x1="{padding_left}" y1="{y:.1f}" x2="{width - padding_right}" y2="{y:.1f}" stroke="{COLORS["grid"]}" stroke-width="0.5"/>')
        svg_parts.append(f'<text x="{padding_left - 5}" y="{y:.1f}" text-anchor="end" font-size="9" fill="{COLORS["text"]}" dominant-baseline="middle">${price_val:.0f}</text>')

    # ADX threshold lines (25 = trending threshold)
    adx_25_y = adx_to_y(25)
    svg_parts.append(f'<line x1="{padding_left}" y1="{adx_25_y:.1f}" x2="{width - padding_right}" y2="{adx_25_y:.1f}" stroke="{COLORS["ema20"]}" stroke-width="1" stroke-dasharray="4,4" opacity="0.5"/>')
    svg_parts.append(f'<text x="{padding_left - 5}" y="{adx_25_y:.1f}" text-anchor="end" font-size="8" fill="{COLORS["ema20"]}" dominant-baseline="middle">25</text>')

    # ADX label
    svg_parts.append(f'<text x="{padding_left + 5}" y="{adx_top + 12}" font-size="9" fill="{COLORS["text"]}">ADX</text>')

    # Time markers (3M)
    if show_markers and len(prices) > 13:
        idx = len(prices) - 13  # ~3 months ago for weekly
        x = idx_to_x(idx, len(prices))
        svg_parts.append(f'<line x1="{x:.1f}" y1="{price_top}" x2="{x:.1f}" y2="{adx_bottom}" stroke="{COLORS["marker"]}" stroke-width="1" stroke-dasharray="4,4"/>')
        svg_parts.append(f'<text x="{x:.1f}" y="{height - 5}" text-anchor="middle" font-size="8" fill="{COLORS["text"]}">3M</text>')

    # EMA-50 (draw first, behind)
    if ema_50 is not None and len(ema_50) > 1:
        ema_50_aligned = ema_50.reindex(prices.index).dropna()
        if len(ema_50_aligned) > 1:
            path_parts = []
            for i, (date, val) in enumerate(ema_50_aligned.items()):
                idx = list(prices.index).index(date)
                x = idx_to_x(idx, len(prices))
                y = price_to_y(val)
                cmd = "M" if i == 0 else "L"
                path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
            svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="none" stroke="{COLORS["ema50"]}" stroke-width="1.5" stroke-dasharray="4,2" opacity="0.8"/>')

    # EMA-20
    if ema_20 is not None and len(ema_20) > 1:
        ema_20_aligned = ema_20.reindex(prices.index).dropna()
        if len(ema_20_aligned) > 1:
            path_parts = []
            for i, (date, val) in enumerate(ema_20_aligned.items()):
                idx = list(prices.index).index(date)
                x = idx_to_x(idx, len(prices))
                y = price_to_y(val)
                cmd = "M" if i == 0 else "L"
                path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
            svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="none" stroke="{COLORS["ema20"]}" stroke-width="1.5" opacity="0.8"/>')

    # Price line
    path_parts = []
    for i, (date, val) in enumerate(prices.items()):
        x = idx_to_x(i, len(prices))
        y = price_to_y(val)
        cmd = "M" if i == 0 else "L"
        path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
    svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="none" stroke="{COLORS["price"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')

    # Current price dot
    last_x = idx_to_x(len(prices) - 1, len(prices))
    last_y = price_to_y(prices.iloc[-1])
    svg_parts.append(f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="{COLORS["price"]}"/>')

    # ADX line
    if adx is not None and len(adx) > 1:
        adx_aligned = adx.reindex(prices.index).dropna()
        if len(adx_aligned) > 1:
            # Determine color based on current value
            current_adx = adx_aligned.iloc[-1]
            adx_color = COLORS["green"] if current_adx >= 25 else COLORS["red"]

            path_parts = []
            for i, (date, val) in enumerate(adx_aligned.items()):
                idx = list(prices.index).index(date)
                x = idx_to_x(idx, len(prices))
                y = adx_to_y(val)
                cmd = "M" if i == 0 else "L"
                path_parts.append(f"{cmd}{x:.1f},{y:.1f}")

            # Area fill under ADX line
            area_path = " ".join(path_parts) + f" L{last_x:.1f},{adx_bottom:.1f} L{idx_to_x(0, len(prices)):.1f},{adx_bottom:.1f} Z"
            svg_parts.append(f'<path d="{area_path}" fill="{adx_color}" opacity="0.15"/>')

            # ADX line
            svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="none" stroke="{adx_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')

            # Current ADX value
            adx_last_y = adx_to_y(current_adx)
            svg_parts.append(f'<circle cx="{last_x:.1f}" cy="{adx_last_y:.1f}" r="3" fill="{adx_color}"/>')
            svg_parts.append(f'<text x="{last_x + 8:.1f}" y="{adx_last_y:.1f}" font-size="10" font-weight="bold" fill="{adx_color}" dominant-baseline="middle">{current_adx:.0f}</text>')

    # Legend
    legend_y = price_top + 10
    svg_parts.append(f'<line x1="{padding_left + 5}" y1="{legend_y}" x2="{padding_left + 18}" y2="{legend_y}" stroke="{COLORS["price"]}" stroke-width="2"/>')
    svg_parts.append(f'<text x="{padding_left + 22}" y="{legend_y}" font-size="8" fill="{COLORS["text"]}" dominant-baseline="middle">Price</text>')

    if ema_20 is not None:
        svg_parts.append(f'<line x1="{padding_left + 55}" y1="{legend_y}" x2="{padding_left + 68}" y2="{legend_y}" stroke="{COLORS["ema20"]}" stroke-width="1.5"/>')
        svg_parts.append(f'<text x="{padding_left + 72}" y="{legend_y}" font-size="8" fill="{COLORS["text"]}" dominant-baseline="middle">EMA20</text>')

    if ema_50 is not None:
        svg_parts.append(f'<line x1="{padding_left + 110}" y1="{legend_y}" x2="{padding_left + 123}" y2="{legend_y}" stroke="{COLORS["ema50"]}" stroke-width="1.5" stroke-dasharray="4,2"/>')
        svg_parts.append(f'<text x="{padding_left + 127}" y="{legend_y}" font-size="8" fill="{COLORS["text"]}" dominant-baseline="middle">EMA50</text>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def generate_projection_chart_svg(
    recent_prices: pd.Series,
    current_price: float,
    stop_price: float,
    targets: Dict[str, float],
    confidence: float = 100,
    width: int = 400,
    height: int = 200
) -> str:
    """
    Generate a projection chart with target zones.
    """
    prices = recent_prices.dropna().tail(63)  # 3 months

    if len(prices) < 5:
        return f'<svg width="{width}" height="{height}"><text x="50%" y="50%" text-anchor="middle" fill="{COLORS["text"]}">Insufficient data</text></svg>'

    padding_left = 50
    padding_right = 80  # More room for target labels
    padding_top = 20
    padding_bottom = 25

    # Historical chart takes 70% width, projection zone 30%
    hist_width = (width - padding_left - padding_right) * 0.7
    proj_width = (width - padding_left - padding_right) * 0.3
    chart_height = height - padding_top - padding_bottom

    # Calculate y range including targets
    all_values = list(prices) + [current_price, stop_price] + list(targets.values())
    y_min = min(all_values)
    y_max = max(all_values)
    y_range = y_max - y_min
    y_min -= y_range * 0.05
    y_max += y_range * 0.05

    def price_to_y(p):
        return padding_top + chart_height - ((p - y_min) / (y_max - y_min) * chart_height)

    def idx_to_x(i, total):
        return padding_left + (i / (total - 1)) * hist_width

    proj_start_x = padding_left + hist_width
    proj_end_x = width - padding_right

    # Confidence affects opacity
    opacity = 0.3 + (confidence / 100) * 0.7

    svg_parts = [f'<svg role="img" aria-label="ATR-based price projection chart" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    svg_parts.append('<title>ATR-based price projection chart</title>')

    # Background
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="{COLORS["bg"]}" rx="8"/>')

    # Projection zone background
    svg_parts.append(f'<rect x="{proj_start_x}" y="{padding_top}" width="{proj_width + padding_right}" height="{chart_height}" fill="rgba(110, 168, 254, 0.05)"/>')

    # Grid lines
    for val in [stop_price, current_price] + list(targets.values()):
        y = price_to_y(val)
        if padding_top <= y <= height - padding_bottom:
            svg_parts.append(f'<line x1="{padding_left}" y1="{y:.1f}" x2="{proj_end_x}" y2="{y:.1f}" stroke="{COLORS["grid"]}" stroke-width="0.5" stroke-dasharray="2,2"/>')

    # Target zones (3R, 2R, 1R from top to bottom)
    target_3r = targets.get("3R", 0)
    target_2r = targets.get("2R", 0)
    target_1r = targets.get("1R", 0)

    if target_3r > target_2r:
        y_3r = price_to_y(target_3r)
        y_2r = price_to_y(target_2r)
        svg_parts.append(f'<rect x="{proj_start_x}" y="{y_3r:.1f}" width="{proj_width}" height="{y_2r - y_3r:.1f}" fill="{COLORS["target_3r"]}" opacity="{opacity}"/>')

    if target_2r > target_1r:
        y_2r = price_to_y(target_2r)
        y_1r = price_to_y(target_1r)
        svg_parts.append(f'<rect x="{proj_start_x}" y="{y_2r:.1f}" width="{proj_width}" height="{y_1r - y_2r:.1f}" fill="{COLORS["target_2r"]}" opacity="{opacity}"/>')

    if target_1r > current_price:
        y_1r = price_to_y(target_1r)
        y_curr = price_to_y(current_price)
        svg_parts.append(f'<rect x="{proj_start_x}" y="{y_1r:.1f}" width="{proj_width}" height="{y_curr - y_1r:.1f}" fill="{COLORS["target_1r"]}" opacity="{opacity}"/>')

    # Stop zone
    if stop_price < current_price:
        y_curr = price_to_y(current_price)
        y_stop = price_to_y(stop_price)
        svg_parts.append(f'<rect x="{proj_start_x}" y="{y_curr:.1f}" width="{proj_width}" height="{y_stop - y_curr:.1f}" fill="{COLORS["stop"]}" opacity="{opacity}"/>')

    # Historical price line
    path_parts = []
    for i, (date, val) in enumerate(prices.items()):
        x = idx_to_x(i, len(prices))
        y = price_to_y(val)
        cmd = "M" if i == 0 else "L"
        path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
    svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="none" stroke="{COLORS["price"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')

    # Current price marker
    curr_y = price_to_y(current_price)
    svg_parts.append(f'<circle cx="{proj_start_x:.1f}" cy="{curr_y:.1f}" r="5" fill="{COLORS["price"]}"/>')
    svg_parts.append(f'<line x1="{proj_start_x}" y1="{curr_y:.1f}" x2="{proj_end_x}" y2="{curr_y:.1f}" stroke="{COLORS["price"]}" stroke-width="1.5"/>')

    # Target labels
    label_x = proj_end_x + 5

    y_3r = price_to_y(target_3r)
    svg_parts.append(f'<text x="{label_x}" y="{y_3r:.1f}" font-size="10" fill="{COLORS["green"]}" dominant-baseline="middle">3R ${target_3r:.0f}</text>')

    y_2r = price_to_y(target_2r)
    svg_parts.append(f'<text x="{label_x}" y="{y_2r:.1f}" font-size="10" fill="{COLORS["green"]}" dominant-baseline="middle">2R ${target_2r:.0f}</text>')

    y_1r = price_to_y(target_1r)
    svg_parts.append(f'<text x="{label_x}" y="{y_1r:.1f}" font-size="10" fill="{COLORS["green"]}" dominant-baseline="middle">1R ${target_1r:.0f}</text>')

    svg_parts.append(f'<text x="{label_x}" y="{curr_y:.1f}" font-size="10" fill="{COLORS["price"]}" dominant-baseline="middle">Now ${current_price:.0f}</text>')

    y_stop = price_to_y(stop_price)
    svg_parts.append(f'<text x="{label_x}" y="{y_stop:.1f}" font-size="10" fill="{COLORS["red"]}" dominant-baseline="middle">Stop ${stop_price:.0f}</text>')

    # Y-axis labels
    svg_parts.append(f'<text x="{padding_left - 5}" y="{curr_y:.1f}" text-anchor="end" font-size="9" fill="{COLORS["text"]}" dominant-baseline="middle">${current_price:.0f}</text>')

    # Vertical divider
    svg_parts.append(f'<line x1="{proj_start_x}" y1="{padding_top}" x2="{proj_start_x}" y2="{height - padding_bottom}" stroke="{COLORS["grid"]}" stroke-width="1"/>')

    # Labels
    svg_parts.append(f'<text x="{padding_left + hist_width / 2}" y="{height - 8}" text-anchor="middle" font-size="9" fill="{COLORS["text"]}">Last 3 Months</text>')
    svg_parts.append(f'<text x="{proj_start_x + proj_width / 2}" y="{height - 8}" text-anchor="middle" font-size="9" fill="{COLORS["text"]}">Projection</text>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def generate_benchmark_chart_svg(
    prices: pd.Series,
    width: int = 500,
    height: int = 170,
    show_52w_levels: bool = True,
) -> str:
    """
    Responsive benchmark chart. Renders at 500×170 internally;
    the SVG scales to 100% of its container via style="width:100%".
    52W high/low shown as dashed reference lines (numbers are in the
    range bar below the chart). Time markers at 3M and 6M.
    """
    prices = prices.dropna().tail(252)

    if len(prices) < 10:
        return f'<svg width="100%" viewBox="0 0 {width} {height}" style="display:block;"></svg>'

    pad_h = 12
    pad_v = 18       # extra vertical room so top/bottom labels don't clip
    chart_w = width - pad_h * 2
    chart_h = height - pad_v * 2

    actual_min = prices.min()
    actual_max = prices.max()
    y_range = actual_max - actual_min
    if y_range == 0:
        y_range = actual_max * 0.1 or 1

    # Expand 10% above and below so H/L lines sit inside the chart area
    y_min = actual_min - y_range * 0.10
    y_max = actual_max + y_range * 0.10

    def price_to_y(p):
        return pad_v + chart_h - ((p - y_min) / (y_max - y_min) * chart_h)

    def idx_to_x(i, total):
        return pad_h + (i / (total - 1)) * chart_w

    trend_color = COLORS["green"] if prices.iloc[-1] >= prices.iloc[0] else COLORS["red"]

    # SVG is width="100%" so it fills its container; viewBox keeps the internal coordinate system
    svg_parts = [
        f'<svg role="img" aria-label="Benchmark performance chart" width="100%" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" style="display:block;"><title>Benchmark performance chart</title>'
    ]

    # Background
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="{COLORS["bg"]}" rx="6"/>')

    # Area fill
    path_parts = [f"M{pad_h},{price_to_y(prices.iloc[0]):.1f}"]
    for i, val in enumerate(prices):
        x = idx_to_x(i, len(prices))
        y = price_to_y(val)
        path_parts.append(f"L{x:.1f},{y:.1f}")
    path_parts.append(f"L{idx_to_x(len(prices) - 1, len(prices)):.1f},{height - pad_v}")
    path_parts.append(f"L{pad_h},{height - pad_v}")
    path_parts.append("Z")
    svg_parts.append(f'<path d="{" ".join(path_parts)}" fill="{trend_color}" opacity="0.12"/>')

    # Price line
    path_parts = []
    for i, val in enumerate(prices):
        x = idx_to_x(i, len(prices))
        y = price_to_y(val)
        cmd = "M" if i == 0 else "L"
        path_parts.append(f"{cmd}{x:.1f},{y:.1f}")
    svg_parts.append(
        f'<path d="{" ".join(path_parts)}" fill="none" stroke="{trend_color}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    )

    # 52W High / Low dashed reference lines (no text — numbers are in the range bar below)
    if show_52w_levels:
        y_52w_high = price_to_y(actual_max)
        y_52w_low  = price_to_y(actual_min)
        svg_parts.append(
            f'<line x1="{pad_h}" y1="{y_52w_high:.1f}" x2="{width - pad_h}" y2="{y_52w_high:.1f}" '
            f'stroke="{COLORS["green"]}" stroke-width="1" stroke-dasharray="4,3" opacity="0.45"/>'
        )
        svg_parts.append(
            f'<line x1="{pad_h}" y1="{y_52w_low:.1f}" x2="{width - pad_h}" y2="{y_52w_low:.1f}" '
            f'stroke="{COLORS["red"]}" stroke-width="1" stroke-dasharray="4,3" opacity="0.45"/>'
        )
        # Compact right-side labels that sit ON the lines (no clipping risk)
        label_x = width - pad_h - 3
        svg_parts.append(
            f'<text x="{label_x}" y="{y_52w_high - 3:.1f}" text-anchor="end" '
            f'font-size="9" fill="{COLORS["green"]}" opacity="0.8">H</text>'
        )
        svg_parts.append(
            f'<text x="{label_x}" y="{y_52w_low + 11:.1f}" text-anchor="end" '
            f'font-size="9" fill="{COLORS["red"]}" opacity="0.8">L</text>'
        )

    # Time markers: 3M and 6M ago
    time_markers = [(len(prices) - 63, "3M"), (len(prices) - 126, "6M")]
    for idx, label in time_markers:
        if 0 <= idx < len(prices):
            x = idx_to_x(idx, len(prices))
            svg_parts.append(
                f'<line x1="{x:.1f}" y1="{pad_v}" x2="{x:.1f}" y2="{height - pad_v}" '
                f'stroke="{COLORS["marker"]}" stroke-width="1" stroke-dasharray="2,3"/>'
            )
            svg_parts.append(
                f'<text x="{x:.1f}" y="{height - 4}" text-anchor="middle" '
                f'font-size="9" fill="{COLORS["text"]}">{label}</text>'
            )

    # Current value dot
    x_last = idx_to_x(len(prices) - 1, len(prices))
    y_last = price_to_y(prices.iloc[-1])
    svg_parts.append(f'<circle cx="{x_last:.1f}" cy="{y_last:.1f}" r="3" fill="{trend_color}"/>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def generate_confidence_bar_svg(
    confidence: float,
    width: int = 80,
    height: int = 12
) -> str:
    """
    Generate a confidence level bar.
    """
    filled_width = (confidence / 100) * width

    # Color based on confidence level
    if confidence >= 80:
        color = COLORS["green"]
    elif confidence >= 50:
        color = COLORS["ema50"]  # Violet usually, but using Amber/Gold for Medium makes sense? Let's stick to theme.
    else:
        color = COLORS["red"]

    return f'''<svg role="img" aria-label="Confidence level: {confidence:.0f}%" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
    <title>Confidence level: {confidence:.0f}%</title>
    <rect width="{width}" height="{height}" fill="{COLORS["grid"]}" rx="2"/>
    <rect width="{filled_width:.1f}" height="{height}" fill="{color}" rx="2"/>
</svg>'''


def generate_driver_chart_svg(prices: pd.Series, width=150, height=50) -> str:
    """
    Mini sparkle chart for macro drivers.
    Green if up over period, Red if down.
    """
    if prices is None or len(prices) < 2:
        return ""
        
    start_price = prices.iloc[0]
    end_price = prices.iloc[-1]
    color = COLORS['green'] if end_price >= start_price else COLORS['red']
    
    # Normalize
    min_p = prices.min()
    max_p = prices.max()
    rng = max_p - min_p if max_p > min_p else 1.0
    
    points = []
    for i, price in enumerate(prices):
        x = (i / (len(prices) - 1)) * width
        y = height - ((price - min_p) / rng) * height
        points.append(f"{x:.1f},{y:.1f}")
        
    polyline = f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2" />'
        
    return f"""
    <svg role="img" aria-label="Macro driver price trend" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
        <title>Macro driver price trend</title>
        <polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2" />
    </svg>
    """


def generate_detailed_driver_chart_svg(
    prices: pd.Series,
    name: str,
    ticker: str,
    sector_prices: pd.Series = None,
    sector_name: str = "Sector",
    width: int = 400,
    height: int = 250
) -> str:
    """
    Detailed chart for Macro Drivers Dashboard.
    Supports Dual-Line visualization (Driver vs Sector).
    """
    if prices is None:
        return f'<svg width="{width}" height="{height}"><text x="50%" y="50%" fill="#666" text-anchor="middle">No Data</text></svg>'
        
    valid_prices = prices.dropna()
    if len(valid_prices) < 2:
        return f'<svg width="{width}" height="{height}"><text x="50%" y="50%" fill="#666" text-anchor="middle">No Data</text></svg>'




    # Theme
    bg_color = "#1e293b" # Slate-800
    text_color = "#94a3b8"
    grid_color = "#334155"
    driver_color = "#60a5fa" # Blue
    sector_color = "#fbbf24" # Amber (for contrast)

    # 1. Align Data
    # Driver (prices) is Daily (High Res) -> KEEP as master index
    # Sector (sector_prices) is Weekly (Low Res) -> Reindex to Driver
    
    # Ensure indexes are DatetimeIndex for proper alignment
    if not isinstance(prices.index, pd.DatetimeIndex):
        try:
            prices.index = pd.to_datetime(prices.index)
        except:
             pass # Should be datetime already if from pandas/yfinance

    if sector_prices is not None:
        if not isinstance(sector_prices.index, pd.DatetimeIndex):
            try:
                sector_prices.index = pd.to_datetime(sector_prices.index)
            except:
                pass
                
        # Reindex sector to match driver dates (forward fill the weekly data)
        # Use a combination of ffill (past status) and limit checking
        # But simple reindex with method='ffill' is standard for "last known price"
        sector_prices = sector_prices.reindex(prices.index, method='ffill')
        
        # If the driver data starts BEFORE the sector data available, backfill slightly or drop?
        # Better to keep driver data and just have sector line start later.
        # But for the chart scaling, we need to handle NaNs in sector_prices
        pass
    else:
        sector_prices = None

    # 2. Dimensions & Padding
    padding_top = 50
    padding_bottom = 30
    padding_left = 60
    padding_right = 20
    
    chart_w = width - padding_left - padding_right
    chart_h = height - padding_top - padding_bottom

    # 3. Scale Driver (Primary)
    min_p = prices.min()
    max_p = prices.max()
    rng = max_p - min_p if max_p > min_p else 1.0
    
    # Expand range 5%
    min_p -= rng * 0.05
    max_p += rng * 0.05
    rng = max_p - min_p

    def get_y_driver(p):
        return padding_top + chart_h - ((p - min_p) / rng) * chart_h

    def get_x(i, total):
        return padding_left + (i / (total - 1)) * chart_w

    # 4. Scale Sector (Secondary) - Normalize to fit same visual range
    sector_points_svg = ""
    if sector_prices is not None:
        s_min = sector_prices.min()
        s_max = sector_prices.max()
        s_rng = s_max - s_min if s_max > s_min else 1.0
        
        # Expand range identically to driver to align visual proportions
        s_min -= s_rng * 0.05
        s_max += s_rng * 0.05
        s_rng = s_max - s_min
        
        def get_y_sector(p):
            return padding_top + chart_h - ((p - s_min) / s_rng) * chart_h
            
        s_points = []
        for i, p in enumerate(sector_prices):
            if pd.isna(p):
                continue
                
            x = get_x(i, len(sector_prices))
            y = get_y_sector(p)
            s_points.append(f"{x:.1f},{y:.1f}")
        
        if s_points:
            sector_points_svg = f'<polyline points="{" ".join(s_points)}" fill="none" stroke="{sector_color}" stroke-width="2" stroke-dasharray="4,2" opacity="0.8" />'

    # Driver Points
    points = []
    for i, p in enumerate(prices):
        if pd.isna(p):
            continue
            
        x = get_x(i, len(prices))
        y = get_y_driver(p)
        points.append(f"{x:.1f},{y:.1f}")
    
    polyline_points = " ".join(points)

    # 5. SVG Construction
    svg = [f'<svg role="img" aria-label="Detailed macro driver chart for {name}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="background:{bg_color}; border-radius:8px;">']
    svg.append(f'<title>Macro driver chart: {name} ({ticker})</title>')

    # Grid & Y-Axis Labels (Driver Price)
    for i in range(5):
        y = padding_top + (i/4) * chart_h
        price_val = max_p - (i/4) * rng
        svg.append(f'<line x1="{padding_left}" y1="{y}" x2="{width - padding_right}" y2="{y}" stroke="{grid_color}" stroke-width="1" stroke-dasharray="4,4" />')
        svg.append(f'<text x="{padding_left - 8}" y="{y}" fill="{text_color}" font-size="10" text-anchor="end" dominant-baseline="middle">${price_val:.2f}</text>')

    # X-Axis Labels (Dates)
    dates = prices.index
    date_markers = [0, len(dates)//2, len(dates)-1]
    for idx in date_markers:
        date_str = dates[idx].strftime('%b %d')
        x = get_x(idx, len(dates))
        anchor = "start" if idx == 0 else "end" if idx == len(dates)-1 else "middle"
        svg.append(f'<text x="{x}" y="{height - 10}" fill="{text_color}" font-size="10" text-anchor="{anchor}">{date_str}</text>')

    # Draw Lines
    if sector_points_svg:
        svg.append(sector_points_svg)
    svg.append(f'<polyline points="{polyline_points}" fill="none" stroke="{driver_color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />')

    # Legend & Title
    svg.append(f'<text x="{padding_left}" y="20" fill="#e2e8f0" font-size="14" font-weight="bold" font-family="sans-serif">{name} ({ticker})</text>')
    
    # Legend Items
    legend_y = 38
    # Driver Legend
    svg.append(f'<line x1="{padding_left}" y1="{legend_y}" x2="{padding_left+15}" y2="{legend_y}" stroke="{driver_color}" stroke-width="2.5" />')
    svg.append(f'<text x="{padding_left+20}" y="{legend_y}" fill="{text_color}" font-size="10" dominant-baseline="middle">Price</text>')
    
    # Sector Legend
    if sector_prices is not None:
        svg.append(f'<line x1="{padding_left+60}" y1="{legend_y}" x2="{padding_left+75}" y2="{legend_y}" stroke="{sector_color}" stroke-width="2" stroke-dasharray="4,2" />')
        svg.append(f'<text x="{padding_left+80}" y="{legend_y}" fill="{text_color}" font-size="10" dominant-baseline="middle">{sector_name}</text>')

    # Stats (Top Right)
    start_p = valid_prices.iloc[0]
    end_p = valid_prices.iloc[-1]
    pct = ((end_p - start_p) / start_p) * 100
    sign = "+" if pct >= 0 else ""
    color = "#4ade80" if pct >= 0 else "#f87171"
    
    svg.append(f'<text x="{width - padding_right}" y="20" fill="{color}" font-size="14" font-weight="bold" text-anchor="end">{sign}{pct:.1f}%</text>')

    svg.append('</svg>')
    return "\n".join(svg)

