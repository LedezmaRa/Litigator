"""
Sector Funnel Dashboard - Macro Watch 2.1 (Unified)

Four-Stage Stock Screening System:
- Benchmarks: Market context (SPY, QQQ, IWM, VIX)
- Stage 1: Sector Overview with all stocks ranked by composite score
- Stage 2: Trade Candidates with charts and EMA-ADX-ATR analysis
- Stage 3: Projections with ATR-based targets

Output: Single HTML dashboard (sector_analysis.html)
"""
import json
import math
import os
import yaml
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

# Internal Framework Imports
from src.data import fetch_data_parallel
import src.scoring as core_scoring
from src.indicators import calculate_all_indicators
from src.utils.html_utils import CSS_DARK_THEME, INTERACTIVE_JS, METRICS_GUIDE_HTML, generate_top_nav, generate_breadcrumb  # Shared Theme + JS
from src.sectors.scoring import (
    StockMetrics, CompositeScore, build_stock_metrics, 
    rank_all_sectors, get_trade_candidates
)
from src.agent.investor import generate_investment_memo
from src.agent.macro_investor import generate_macro_investment_memo
from src.sectors.charts import (
    generate_sparkline_svg, generate_price_chart_svg,
    generate_projection_chart_svg, generate_benchmark_chart_svg,
    generate_confidence_bar_svg, generate_price_with_adx_chart_svg,
    generate_driver_chart_svg
)
from src.sectors.projections import (
    ProjectionResult, calculate_projection, rank_projections
)
from src.sectors.drivers import (
    fetch_drivers, analyze_drivers, DriverAnalysis
)
from src.sectors.macro_dashboard import generate_macro_page


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "sectors.yaml")
LOOKBACKS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126}


@dataclass
class SectorMetrics:
    """Aggregate metrics for a sector."""
    etf: str
    name: str
    stock_count: int
    avg_composite_score: float
    top5_avg_score: float
    pct_trending_up: float  # % of stocks with positive 3M relative return
    trade_ready_count: int  # Stocks with Entry Score >= 60
    etf_ret_1w: Optional[float] = None
    etf_ret_1m: Optional[float] = None
    etf_ret_3m: Optional[float] = None
    rotation_status: str = "UNKNOWN"


@dataclass
class TradeCandidateAnalysis:
    ticker: str
    name: str
    sector: str
    sector_etf: str
    composite_score: float
    rank_in_sector: int
    price: Optional[float]
    rel_3m: Optional[float]
    trend: str
    regime: str = "NA"
    signal_strength: str = "NA"
    entry_score: float = 0.0  # EMA-ADX-ATR Entry Score (0-100)
    adx: float = 0.0
    atr: float = 0.0
    volume_ratio: float = 1.0
    ema_stack_ok: bool = False
    ema_slope_ok: bool = False
    adx_ok: bool = False
    stop_price: float = 0.0
    stop_dist_pct: float = 0.0
    stop_dist_atr: float = 1.5   # regime-aware ATR multiplier used for stop
    is_trade_ready: bool = False
    score_breakdown: Optional[Dict] = None  # {ema_proximity, adx_stage, volume_conviction, structure, risk_reward}


def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)


def get_all_tickers(config: Dict) -> List[str]:
    tickers = set()
    for etf, info in config.get('sectors', {}).items():
        tickers.add(etf)
        tickers.update(info.get('stocks', {}).keys())
    
    tickers.update(config.get('benchmarks', {}).keys())
    if 'watchlists' in config:
        for wl in config['watchlists'].values():
            tickers.update(wl.get('stocks', {}).keys())
            
    # Add benchmark indices
    tickers.add("^VIX")
    tickers.add("^TNX")   # 10Y Treasury yield (for yield curve)
    tickers.add("^IRX")   # 13-week T-Bill yield (for yield curve spread)
    return sorted(list(tickers))


# --- HTML HELPERS ---

def fmt_pct(x) -> str:
    if x is None or pd.isna(x): return "NA"
    return f"{x*100:+.1f}%"

def fmt_num(x, d=2) -> str:
    if x is None or pd.isna(x): return "NA"
    return f"{x:,.{d}f}"

def _color_class(val) -> str:
    if val is None or pd.isna(val): return ""
    return "text-optimal" if val > 0 else "text-poor" if val < 0 else ""

def _pill_class(val: str) -> str:
    v = str(val).lower()
    if "strong" in v or "accelerating" in v or "trending" in v or "low_vol" in v: return "badge badge-optimal"
    if "moderate" in v or "steady" in v or "normal_vol" in v: return "badge badge-good"
    if "weak" in v or "decelerating" in v: return "badge badge-marginal"
    if "high_vol" in v: return "badge badge-marginal"
    return "badge badge-poor"

_REGIME_LABEL = {
    "LOW_VOLATILITY": "Low Vol",
    "NORMAL_VOLATILITY": "Normal Vol",
    "HIGH_VOLATILITY": "High Vol",
}

def _regime_display(regime: str) -> str:
    """Return a short human-readable label for the volatility regime."""
    return _REGIME_LABEL.get(regime, regime)


# --- SECTOR METRICS ---

def classify_rotation_status(ret_1w, ret_1m) -> str:
    """
    Classify sector rotation phase based on short vs medium-term momentum.
    ENTERING:  both positive and 1W > 1M (accelerating)
    HOLDING:   1M positive but 1W <= 1M (still up, slowing)
    EXITING:   1W negative but 1M positive (short-term crack)
    AVOIDING:  both negative (broad weakness)
    """
    if ret_1w is None or ret_1m is None:
        return "UNKNOWN"
    if ret_1w > 0 and ret_1m > 0 and ret_1w > ret_1m:
        return "ENTERING"
    if ret_1m > 0 and ret_1w <= ret_1m:
        return "HOLDING"
    if ret_1w <= 0 and ret_1m > 0:
        return "EXITING"
    return "AVOIDING"


def calculate_sector_metrics(
    config: Dict,
    ranked_sectors: Dict,
    closes: pd.DataFrame,
    candidates: List
) -> List[SectorMetrics]:
    """Calculate aggregate metrics for each sector."""
    metrics_list = []

    for etf, info in config.get('sectors', {}).items():
        ranked = ranked_sectors.get(etf, [])
        if not ranked:
            continue

        name = info.get('name', etf)
        stock_count = len(ranked)

        # Average composite score
        avg_score = sum(s.composite_score for s in ranked) / len(ranked) if ranked else 0

        # Top 5 average
        top5 = ranked[:5]
        top5_avg = sum(s.composite_score for s in top5) / len(top5) if top5 else 0

        # % trending up (positive 3M relative return)
        up_count = sum(1 for s in ranked if s.rel_3m is not None and s.rel_3m > 0)
        pct_up = (up_count / stock_count * 100) if stock_count > 0 else 0

        # Trade ready count (from candidates with entry_score >= 60)
        trade_ready = sum(1 for c in candidates if c.sector_etf == etf and c.entry_score >= 60)

        # ETF returns
        etf_ret_1w, etf_ret_1m, etf_ret_3m = None, None, None
        if etf in closes.columns:
            prices = closes[etf]
            if len(prices) > 5:
                etf_ret_1w = (prices.iloc[-1] / prices.iloc[-6]) - 1
            if len(prices) > 21:
                etf_ret_1m = (prices.iloc[-1] / prices.iloc[-22]) - 1
            if len(prices) > 63:
                etf_ret_3m = (prices.iloc[-1] / prices.iloc[-64]) - 1

        rotation = classify_rotation_status(etf_ret_1w, etf_ret_1m)
        metrics_list.append(SectorMetrics(
            etf=etf,
            name=name,
            stock_count=stock_count,
            avg_composite_score=avg_score,
            top5_avg_score=top5_avg,
            pct_trending_up=pct_up,
            trade_ready_count=trade_ready,
            etf_ret_1w=etf_ret_1w,
            etf_ret_1m=etf_ret_1m,
            etf_ret_3m=etf_ret_3m,
            rotation_status=rotation,
        ))

    # Sort by top5 average score descending
    metrics_list.sort(key=lambda x: x.top5_avg_score, reverse=True)
    return metrics_list


_ROTATION_BADGE_CLASS = {
    "ENTERING": "badge-optimal",
    "HOLDING": "badge-good",
    "EXITING": "badge-marginal",
    "AVOIDING": "badge-poor",
    "UNKNOWN": "",
}
_ROTATION_TOOLTIP = {
    "ENTERING": "1W > 1M > 0: momentum accelerating. Consider adding exposure.",
    "HOLDING":  "1M > 0 but 1W slowing: still healthy, watch for continuation.",
    "EXITING":  "1W < 0 but 1M > 0: short-term crack in an uptrend. Caution.",
    "AVOIDING": "Both 1W and 1M negative: broad weakness. Avoid new longs.",
    "UNKNOWN":  "Insufficient data.",
}


def generate_sector_leaderboard_html(sector_metrics: List[SectorMetrics], closes: pd.DataFrame = None) -> str:
    """Generate HTML for sector comparison leaderboard with sparklines and links to detail pages."""
    rows = ""

    for i, m in enumerate(sector_metrics):
        rank_color = "var(--accent-optimal)" if i < 3 else "var(--accent-good)" if i < 6 else "var(--text-secondary)"
        ready_badge = f'<span class="badge badge-optimal">{m.trade_ready_count}</span>' if m.trade_ready_count > 0 else '<span class="badge badge-poor">0</span>'

        # ETF sparkline
        sparkline = ""
        if closes is not None and m.etf in closes.columns:
            sparkline = generate_sparkline_svg(closes[m.etf], width=80, height=28)

        # % Up context: color-code against rough market average (50% = neutral)
        pct_up_color = "var(--accent-optimal)" if m.pct_trending_up >= 60 else \
                       "var(--accent-marginal)" if m.pct_trending_up >= 40 else "var(--accent-poor)"

        rot_badge_cls = _ROTATION_BADGE_CLASS.get(m.rotation_status, "")
        rot_tooltip = _ROTATION_TOOLTIP.get(m.rotation_status, "")
        rotation_cell = f'<span class="badge {rot_badge_cls}" title="{rot_tooltip}" style="cursor:help;">{m.rotation_status}</span>'

        rows += f"""
        <tr>
            <td data-label="Rank" style="color:{rank_color}; font-weight:bold;">#{i+1}</td>
            <td data-label="Sector">
                <div style="display:flex; align-items:center; gap:0.75rem;">
                    {sparkline}
                    <div>
                        <a href="sector_{m.etf}.html" style="color:var(--text-primary); text-decoration:none; font-weight:600;">
                            {m.name} →
                        </a>
                        <br><span class="text-xs text-muted">{m.etf}</span>
                    </div>
                </div>
            </td>
            <td data-label="Top-5 Score" style="text-align:center;">
                <b>{m.top5_avg_score:.0f}</b>
                <br><span class="text-xs text-muted">top 5</span>
            </td>
            <td data-label="Avg Score" style="text-align:center;">{m.avg_composite_score:.0f}</td>
            <td data-label="% Up" style="text-align:center; color:{pct_up_color}; font-weight:600;">{m.pct_trending_up:.0f}%</td>
            <td data-label="Ready" style="text-align:center;">{ready_badge}</td>
            <td data-label="Rotation" style="text-align:center;">{rotation_cell}</td>
            <td data-label="1W" class="{_color_class(m.etf_ret_1w)}">{fmt_pct(m.etf_ret_1w)}</td>
            <td data-label="1M" class="{_color_class(m.etf_ret_1m)}">{fmt_pct(m.etf_ret_1m)}</td>
            <td data-label="3M" class="{_color_class(m.etf_ret_3m)}">{fmt_pct(m.etf_ret_3m)}</td>
        </tr>
        """

    return f"""
    <h2 style="margin-top:2rem;">Sector Leaderboard</h2>
    <p class="text-muted mb-2">
        Ranked by Top 5 Average Composite Score (RS 50% + Trend 30% + Volume 20%, percentile within sector, 0–100) •
        % Up = share of stocks with positive 3M relative return vs sector ETF •
        Rotation = ENTERING/HOLDING/EXITING/AVOIDING based on 1W vs 1M momentum •
        Click sector name for full charts
    </p>
    <div class="glass-card">
        <table class="modern-table">
            <thead>
                <tr>
                    <th class="sortable">#</th>
                    <th>Sector ETF</th>
                    <th class="sortable" style="text-align:center;">Top 5 Score</th>
                    <th class="sortable" style="text-align:center;">All Avg</th>
                    <th class="sortable" style="text-align:center;">% Up</th>
                    <th class="sortable" style="text-align:center;">Trade Ready</th>
                    <th style="text-align:center;">Rotation</th>
                    <th class="sortable">1W</th>
                    <th class="sortable">1M</th>
                    <th class="sortable">3M</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


# --- HTML GENERATORS ---

# Educational descriptions for each benchmark card
BENCHMARK_INFO = {
    "SPY": (
        "S&P 500",
        "Tracks the 500 largest U.S. companies by market cap. The primary gauge of U.S. large-cap equity market health. When SPY trends up, the broad market is healthy."
    ),
    "QQQ": (
        "Nasdaq-100",
        "Top 100 non-financial Nasdaq stocks, heavily weighted toward tech and growth. Very sensitive to interest rates — rising rates compress growth valuations."
    ),
    "IWM": (
        "Russell 2000",
        "2,000 U.S. small-cap stocks. A risk-on barometer: small-caps lead in early bull markets and crack first during credit stress or recession fears. IWM/SPY ratio signals market breadth."
    ),
    "^VIX": (
        "VIX — Fear Gauge",
        "Expected 30-day S&P 500 volatility derived from options pricing. Below 15 = calm complacency, 15–25 = normal uncertainty, above 30 = elevated stress, above 40 = panic."
    ),
}

# Lookback periods for multi-period return display
PERIOD_LOOKBACKS = [("1W", 5), ("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252)]


def _range_bar_html(curr: float, low: float, high: float, is_vix: bool = False) -> str:
    """Horizontal range bar showing where current value sits within the 52-week range."""
    if high <= low:
        return ""
    pct = max(0.0, min(100.0, (curr - low) / (high - low) * 100))
    # For VIX: low percentile = good (calm). For price: high percentile = good (uptrend).
    if is_vix:
        bar_color = "var(--accent-optimal)" if pct < 30 else "var(--accent-marginal)" if pct < 60 else "var(--accent-poor)"
    else:
        bar_color = "var(--accent-optimal)" if pct >= 70 else "var(--accent-marginal)" if pct >= 40 else "var(--accent-poor)"
    return f"""<div style="margin:0.4rem 0 0.5rem;">
        <div style="display:flex; justify-content:space-between; font-size:0.68rem; color:var(--text-secondary); margin-bottom:3px;">
            <span>52W: {low:.2f} – {high:.2f}</span>
            <span style="color:{bar_color}; font-weight:600;">{pct:.0f}th %ile of 52W range</span>
        </div>
        <div style="height:4px; background:rgba(255,255,255,0.08); border-radius:2px; overflow:hidden;">
            <div style="height:100%; width:{pct:.1f}%; background:{bar_color}; border-radius:2px;"></div>
        </div>
    </div>"""


def _returns_cells_html(prices: pd.Series) -> str:
    """5-period return grid: 1W / 1M / 3M / 6M / 1Y."""
    curr = prices.iloc[-1]
    cells = ""
    for label, bars in PERIOD_LOOKBACKS:
        if len(prices) > bars:
            val = curr / prices.iloc[-(bars + 1)] - 1
            cls = _color_class(val)
            formatted = fmt_pct(val)
        else:
            cls = ""
            formatted = "–"
        cells += (
            f'<div style="text-align:center; background:rgba(255,255,255,0.03); border-radius:4px; padding:3px 0;">'
            f'<div style="font-size:0.62rem; color:var(--text-secondary);">{label}</div>'
            f'<div class="{cls}" style="font-size:0.78rem; font-weight:600;">{formatted}</div>'
            f'</div>'
        )
    return f'<div style="display:grid; grid-template-columns:repeat(5,1fr); gap:3px; margin-bottom:0.4rem;">{cells}</div>'


def _spread_returns_cells_html(spread: pd.Series) -> str:
    """5-period absolute-change grid for a yield spread (in basis points)."""
    curr = spread.iloc[-1]
    cells = ""
    for label, bars in PERIOD_LOOKBACKS:
        if len(spread) > bars:
            delta = curr - spread.iloc[-(bars + 1)]  # change in pct points
            bps = delta * 100                         # convert to basis points
            cls = _color_class(delta)
            formatted = f"{bps:+.0f}bps"
        else:
            cls = ""
            formatted = "–"
        cells += (
            f'<div style="text-align:center; background:rgba(255,255,255,0.03); border-radius:4px; padding:3px 0;">'
            f'<div style="font-size:0.62rem; color:var(--text-secondary);">{label}</div>'
            f'<div class="{cls}" style="font-size:0.78rem; font-weight:600;">{formatted}</div>'
            f'</div>'
        )
    return f'<div style="display:grid; grid-template-columns:repeat(5,1fr); gap:3px; margin-bottom:0.4rem;">{cells}</div>'


def generate_benchmarks_html(closes: pd.DataFrame, data_dict: Dict) -> str:
    """Generate Market Benchmarks section with educational context and historical comparison."""
    cards = ""

    for b, (name, desc) in BENCHMARK_INFO.items():
        if b not in closes.columns:
            continue
        prices = closes[b].dropna()
        if len(prices) < 5:
            continue

        curr = prices.iloc[-1]
        is_vix = b == "^VIX"
        val_display = f"{curr:.2f}" if is_vix else f"${curr:.2f}"

        # 1W change for header badge
        chg_1w = (curr / prices.iloc[-6] - 1) if len(prices) > 5 else None
        chg_color = _color_class(chg_1w) if chg_1w is not None else ""
        chg_display = fmt_pct(chg_1w) if chg_1w is not None else "–"

        # 52W range context
        prices_52w = prices.tail(252)
        low_52w = prices_52w.min()
        high_52w = prices_52w.max()
        range_bar = _range_bar_html(curr, low_52w, high_52w, is_vix=is_vix)
        returns_html = _returns_cells_html(prices)
        chart = generate_benchmark_chart_svg(prices)

        cards += f"""
        <div class="glass-card" style="min-width:0; display:flex; flex-direction:column; gap:0.6rem;">
            <!-- Header: ticker + price -->
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <div style="font-size:0.7rem; font-weight:700; letter-spacing:0.07em; color:var(--text-secondary); text-transform:uppercase;">{b}</div>
                    <div style="font-size:1rem; font-weight:700; color:var(--text-primary); margin-top:1px;">{name}</div>
                </div>
                <div style="text-align:right; flex-shrink:0; margin-left:0.75rem;">
                    <div style="font-size:1.6rem; font-weight:bold; line-height:1;">{val_display}</div>
                    <div class="{chg_color}" style="font-size:0.78rem; margin-top:3px;">1W: {chg_display}</div>
                </div>
            </div>
            <!-- Chart — full width, prominent -->
            <div style="margin:0 -0.1rem;">{chart}</div>
            <!-- Description -->
            <div style="font-size:0.72rem; color:var(--text-secondary); line-height:1.5; border-left:2px solid rgba(255,255,255,0.12); padding-left:0.5rem;">{desc}</div>
            <!-- 52W range bar -->
            {range_bar}
            <!-- Multi-period returns -->
            {returns_html}
        </div>
        """

    # --- Yield Curve Card (10Y − 3M Treasury spread) ---
    if "^TNX" in closes.columns and "^IRX" in closes.columns:
        tnx = closes["^TNX"].dropna()
        irx = closes["^IRX"].dropna()
        spread_df = pd.DataFrame({"tnx": tnx, "irx": irx}).dropna()

        if len(spread_df) >= 10:
            spread = spread_df["tnx"] - spread_df["irx"]
            curr_spread = spread.iloc[-1]
            curr_10y = spread_df["tnx"].iloc[-1]
            curr_3m = spread_df["irx"].iloc[-1]

            is_inverted = curr_spread < 0
            spread_color = "var(--accent-poor)" if is_inverted else "var(--accent-optimal)"
            status_label = "INVERTED ⚠" if is_inverted else "NORMAL"

            spread_52w = spread.tail(252)
            low_52w = spread_52w.min()
            high_52w = spread_52w.max()
            spread_range_bar = _range_bar_html(curr_spread, low_52w, high_52w, is_vix=False)
            spread_returns = _spread_returns_cells_html(spread)
            spread_chart = generate_benchmark_chart_svg(spread)

            # 1W delta in basis points
            chg_1w_bps = (curr_spread - spread.iloc[-6]) * 100 if len(spread) > 5 else None
            chg_1w_display = f"{chg_1w_bps:+.0f}bps" if chg_1w_bps is not None else "–"
            chg_1w_color = _color_class(chg_1w_bps) if chg_1w_bps is not None else ""

            desc_yc = (
                f"10Y minus 3M Treasury yield spread. When negative (inverted), it has historically "
                f"preceded U.S. recessions within 6–18 months — short-term rates exceed long-term, "
                f"signaling market expects rate cuts ahead. "
                f"10Y: {curr_10y:.2f}% | 3M: {curr_3m:.2f}%"
            )

            cards += f"""
            <div class="glass-card" style="min-width:0; display:flex; flex-direction:column; gap:0.6rem;">
                <!-- Header -->
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <div style="font-size:0.7rem; font-weight:700; letter-spacing:0.07em; color:var(--text-secondary); text-transform:uppercase;">^TNX − ^IRX</div>
                        <div style="font-size:1rem; font-weight:700; color:var(--text-primary); margin-top:1px;">Yield Curve (10Y−3M)</div>
                    </div>
                    <div style="text-align:right; flex-shrink:0; margin-left:0.75rem;">
                        <div style="font-size:1.6rem; font-weight:bold; line-height:1; color:{spread_color};">{curr_spread:+.2f}%</div>
                        <div style="font-size:0.78rem; color:{spread_color}; font-weight:600; margin-top:3px;">{status_label} · 1W: {chg_1w_display}</div>
                    </div>
                </div>
                <!-- Chart -->
                <div style="margin:0 -0.1rem;">{spread_chart}</div>
                <!-- Description -->
                <div style="font-size:0.72rem; color:var(--text-secondary); line-height:1.5; border-left:2px solid rgba(255,255,255,0.12); padding-left:0.5rem;">{desc_yc}</div>
                <!-- Range bar -->
                {spread_range_bar}
                <!-- Returns -->
                {spread_returns}
            </div>
            """

    return f"""
    <h2 style="margin-top:2rem;">Market Benchmarks</h2>
    <p class="text-muted mb-2">Key market indicators with historical context — where are we today vs. the past 52 weeks?</p>
    <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:1.5rem; margin-bottom:2rem;">
        {cards}
    </div>
    """


def generate_sector_html(config: Dict, ranked_sectors: Dict, closes: pd.DataFrame, sector_drivers_map: Dict) -> str:
    html = ""
    for etf, info in config.get('sectors', {}).items():
        name = info.get('name', etf)
        ranked = ranked_sectors.get(etf, [])
        if not ranked: continue

        # Sparkline
        sparkline = ""
        if etf in closes.columns:
            sparkline = generate_sparkline_svg(closes[etf])
            
        # Drivers Card
        drivers_html = ""
        if etf in sector_drivers_map and sector_drivers_map[etf]:
            drivers = sector_drivers_map[etf]
            driver_rows = ""
            for d in drivers:
                # Generate mini chart
                chart = generate_driver_chart_svg(d.prices, width=60, height=20)
                
                corr_color = _color_class(d.correlation_90d)
                driver_rows += f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; font-size:0.8rem;">
                    <div style="flex:1.5;"><b>{d.name}</b> <span style="font-size:0.7em; color:#666;">({d.ticker})</span></div>
                    <div style="width:70px; margin-right:10px;">{chart}</div>
                    <div style="flex:1; text-align:right;" class="{_color_class(d.change_1m)}">{fmt_pct(d.change_1m)}</div>
                    <div style="flex:1; text-align:right;">Corr: <span class="{corr_color}">{d.correlation_90d:.2f}</span></div>
                    <div style="flex:0.8; text-align:right;"><span class="{_pill_class(d.trend)}">{d.trend}</span></div>
                </div>
                """
            
            drivers_html = f"""
            <div style="background:rgba(255,255,255,0.03); padding:0.5rem; border-radius:4px; margin-bottom:1rem; border:1px solid var(--grid-color);">
                <div style="font-size:0.7em; text-transform:uppercase; letter-spacing:1px; color:var(--text-muted); margin-bottom:0.5rem;">Macro Drivers (90d Correlation)</div>
                {driver_rows}
            </div>
            """

        rows = ""
        for i, stock in enumerate(ranked[:25]):
            trend_badge = _pill_class(stock.trend)
            is_stage2 = i < 5
            row_style = 'background: rgba(74, 222, 128, 0.08); border-left: 3px solid var(--accent-optimal);' if is_stage2 else ''
            stage2_marker = ' <span style="color:var(--accent-optimal); font-size:0.75rem;">→S2</span>' if is_stage2 else ''

            # Composite score mini-bar (fill width proportional to 0-100)
            bar_pct = min(100, max(0, stock.composite_score))
            if bar_pct >= 70:
                bar_color = "var(--accent-optimal)"
            elif bar_pct >= 45:
                bar_color = "var(--accent-marginal)"
            else:
                bar_color = "var(--accent-poor)"
            score_bar = (
                f'<div style="height:3px; background:rgba(255,255,255,0.08); border-radius:2px; margin-top:2px;">'
                f'<div style="height:100%; width:{bar_pct:.0f}%; background:{bar_color}; border-radius:2px;"></div>'
                f'</div>'
            )
            price_display = f"${stock.price:.2f}" if stock.price else "—"

            rows += f"""
            <tr style="{row_style}">
                <td data-label="#" style="color:var(--text-secondary);">#{i+1}</td>
                <td data-label="Ticker"><b>{stock.ticker}</b>{stage2_marker}<br><span class="text-xs text-muted">{price_display}</span></td>
                <td data-label="Score" style="min-width:60px;">
                    <span style="font-weight:600;">{stock.composite_score:.0f}</span>
                    {score_bar}
                </td>
                <td data-label="Rel 3M" class="{_color_class(stock.rel_3m)}">{fmt_pct(stock.rel_3m)}</td>
                <td data-label="Trend"><span class="{trend_badge}">{stock.trend}</span></td>
            </tr>
            """

        html += f"""
        <div class="glass-card" style="max-height: 600px; overflow: hidden; display: flex; flex-direction: column;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; flex-shrink: 0;">
                <div>
                    <h3 style="margin:0;">{name} ({etf})</h3>
                    <span class="text-xs text-muted">Top 5 advance → Stage 2</span>
                </div>
                {sparkline}
            </div>
            {drivers_html}
            <div style="overflow-y: auto; flex: 1;">
                <table class="modern-table" style="font-size:0.8rem;">
                    <thead style="position: sticky; top: 0; background: var(--card-bg);">
                        <tr>
                            <th>#</th>
                            <th>Ticker / Price</th>
                            <th>Score</th>
                            <th>Rel 3M</th>
                            <th>Trend</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>
        """

    return f"""
    <h2 style="margin-top:2rem;">Sector Analysis (Stage 1)</h2>
    <p class="text-muted mb-2">25 stocks per sector ranked by Composite Score (Relative Strength 50% + Trend 30% + Volume 20%)</p>
    <div class="grid-cols-3" style="display:grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap:1.5rem;">
        {html}
    </div>
    """


_FACTOR_TOOLTIPS = {
    "EMA": "EMA Proximity (0-25): Ideal = price within 0.5 ATR of EMA20, just above it. Penalised if >2.5 ATR away (overextended).",
    "ADX": "ADX Stage (0-25): Ideal = ADX 20-40, rising. Confirms trend strength with room to run. Full 25 pts when ADX 25-30 and rising.",
    "Vol": "Volume Conviction (0-20): Ideal = >2x average volume, rising weekly trend, more up-volume than down. All 3 sub-factors required for max.",
    "Str": "Structure Integrity (0-20): Ideal = price > EMA20 > EMA50, EMA50 slope rising. Clean EMA stack is the prerequisite for any trend trade.",
    "R:R": "Risk/Reward (0-10): Ideal = stop <5% away with reward >3R. Uses regime-aware stop (1.5-2x ATR below EMA20). R:R >4.0 = max points.",
}


def _score_breakdown_html(breakdown: Optional[Dict]) -> str:
    """Compact 5-component breakdown bar showing score/max with educational tooltips."""
    if not breakdown:
        return ""
    components = [
        ("EMA", breakdown.get('ema_proximity', 0), 25),
        ("ADX", breakdown.get('adx_stage', 0),     25),
        ("Vol", breakdown.get('volume_conviction', 0), 20),
        ("Str", breakdown.get('structure', 0),     20),
        ("R:R", breakdown.get('risk_reward', 0),   10),
    ]
    cells = ""
    for label, score, max_score in components:
        pct = (score / max_score * 100) if max_score > 0 else 0
        if pct >= 70:
            color = "rgba(74,222,128,0.35)"
        elif pct >= 40:
            color = "rgba(251,191,36,0.35)"
        else:
            color = "rgba(248,113,113,0.25)"
        tooltip = _FACTOR_TOOLTIPS.get(label, "")
        cells += (
            f'<div title="{tooltip}" style="text-align:center; background:{color}; border-radius:2px; padding:1px 2px; cursor:help;">'
            f'<div style="font-size:0.55rem; color:var(--text-secondary);">{label}</div>'
            f'<div style="font-size:0.60rem; font-weight:600;">{score:.0f}<span style="opacity:0.5">/{max_score}</span></div>'
            f'</div>'
        )
    return f'<div style="display:grid; grid-template-columns:repeat(5,1fr); gap:2px; margin-top:3px;">{cells}</div>'


def _hit_rate_bar_svg(pct: float, width: int = 120, height: int = 10) -> str:
    """Horizontal bar for hit-rate visualization."""
    fill = max(0.0, min(100.0, pct))
    color = "var(--accent-optimal)" if fill >= 60 else "var(--accent-marginal)" if fill >= 40 else "var(--accent-poor)"
    fill_w = fill / 100 * width
    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{width}" height="{height}" rx="3" fill="rgba(255,255,255,0.08)"/>'
        f'<rect width="{fill_w:.1f}" height="{height}" rx="3" fill="{color}"/>'
        f'</svg>'
    )


def generate_signal_performance_html(backtest: Dict) -> str:
    """
    Renders the Signal Performance section from backtesting results.
    Shows 'Building history...' placeholder until 5+ projections are evaluated.
    """
    if not backtest or backtest.get("status") == "building":
        evaluated = backtest.get("total_evaluated", 0) if backtest else 0
        return f"""
    <h2 style="margin-top:2rem;">Signal Performance</h2>
    <div class="glass-card" style="padding:1.5rem; text-align:center; color:var(--text-secondary);">
        <p style="font-size:1.1rem; margin-bottom:0.5rem;">📊 Building signal history…</p>
        <p>{evaluated} projection{'' if evaluated == 1 else 's'} recorded so far.</p>
        <p style="font-size:0.8rem; margin-top:0.5rem;">
            Requires 5+ projection snapshots from different days to calculate hit rates.
            Run the dashboard daily — each run saves a snapshot automatically.
        </p>
    </div>
    """

    total = backtest["total_evaluated"]
    hit_1r_pct = backtest["hit_1r_pct"]
    hit_2r_pct = backtest["hit_2r_pct"]
    hit_3r_pct = backtest["hit_3r_pct"]

    def _stat_card(label: str, hits: int, pct: float, desc: str) -> str:
        bar = _hit_rate_bar_svg(pct, width=140, height=8)
        color = "var(--accent-optimal)" if pct >= 60 else "var(--accent-marginal)" if pct >= 40 else "var(--accent-poor)"
        return f"""
        <div class="glass-card" style="padding:1.25rem; text-align:center;">
            <div class="text-xs text-muted mb-1">{label}</div>
            <div style="font-size:2rem; font-weight:bold; color:{color};">{pct:.0f}%</div>
            <div class="text-xs text-muted">{hits} of {total} signals</div>
            <div style="margin:0.5rem auto; display:inline-block;">{bar}</div>
            <div style="font-size:0.72rem; color:var(--text-secondary); margin-top:0.25rem;">{desc}</div>
        </div>
        """

    cards = (
        _stat_card("1R Target Hit", backtest["hit_1r"], hit_1r_pct, "Price reached 1× risk reward") +
        _stat_card("2R Target Hit", backtest["hit_2r"], hit_2r_pct, "Price reached 2× risk reward") +
        _stat_card("3R Target Hit", backtest["hit_3r"], hit_3r_pct, "Price reached 3× risk reward")
    )

    return f"""
    <h2 style="margin-top:2rem;">Signal Performance</h2>
    <p class="text-muted mb-2">
        Historical hit rates based on {total} past projection{'' if total == 1 else 's'} (last 60 days, evaluated after 5-day lag).
        Hit = price reached target within 20 trading bars (≈4 weeks) of signal date.
    </p>
    <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:1.5rem; max-width:700px;">
        {cards}
    </div>
    """


def generate_global_leaderboard_html(candidates: List[TradeCandidateAnalysis]) -> str:
    """
    Cross-sector leaderboard: top 30 stocks across all sectors ranked by
    combined score = 50% composite (Stage 1 breadth) + 50% entry score (Stage 2 quality).
    """
    if not candidates:
        return ""

    scored = sorted(
        candidates,
        key=lambda c: c.composite_score * 0.5 + c.entry_score * 0.5,
        reverse=True,
    )[:30]

    rows = ""
    for i, c in enumerate(scored):
        combined = round(c.composite_score * 0.5 + c.entry_score * 0.5, 1)
        if combined >= 75:
            combined_color = "var(--accent-optimal)"
        elif combined >= 60:
            combined_color = "var(--accent-good)"
        elif combined >= 45:
            combined_color = "var(--accent-marginal)"
        else:
            combined_color = "var(--accent-poor)"

        ready_star = '<span style="color:var(--accent-optimal);">★</span>' if c.is_trade_ready else '<span style="color:var(--text-secondary);">–</span>'
        rank_style = "color:var(--accent-optimal); font-weight:bold;" if i < 3 else "color:var(--text-secondary);"
        breakdown_html = _score_breakdown_html(c.score_breakdown)
        entry_color = "var(--accent-optimal)" if c.entry_score >= 75 else \
                      "var(--accent-good)" if c.entry_score >= 60 else \
                      "var(--accent-marginal)" if c.entry_score >= 45 else "var(--accent-poor)"

        rows += f"""
        <tr data-entry-score="{c.entry_score:.0f}" data-regime="{c.regime}" data-sector="{c.sector_etf}">
            <td data-label="Rank" style="{rank_style}">#{i+1}</td>
            <td data-label="Ticker">
                <b>{c.ticker}</b>
                <br><span class="text-xs text-muted">{c.name}</span>
            </td>
            <td data-label="Sector" style="text-align:center;">
                <span class="badge badge-info" style="font-size:0.65rem;">{c.sector_etf}</span>
            </td>
            <td data-label="Combined" style="text-align:center; font-size:1.1rem; font-weight:bold; color:{combined_color};">{combined}</td>
            <td data-label="Composite" style="text-align:center;">{c.composite_score:.0f}</td>
            <td data-label="Entry Score" style="text-align:center;">
                <b style="color:{entry_color};">{c.entry_score:.0f}</b>
                {breakdown_html}
            </td>
            <td data-label="Trend / Regime">
                <span class="{_pill_class(c.trend)}">{c.trend}</span>
                <br><span class="{_pill_class(c.regime)}" style="margin-top:2px; display:inline-block;">{_regime_display(c.regime)}</span>
            </td>
            <td data-label="Ready" style="text-align:center;">{ready_star}</td>
        </tr>
        """

    return f"""
    <h2 style="margin-top:2rem;">Global Stock Leaderboard</h2>
    <p class="text-muted mb-2">
        Top 30 stocks across all sectors ranked by <b>Combined Score</b> = 50% Composite (breadth) + 50% Entry Score (quality).
        Use this view to find the best setups regardless of sector.
        Hover breakdown cells for factor explanations.
    </p>
    <div class="glass-card">
        <table class="modern-table" id="global-leaderboard-table">
            <thead>
                <tr>
                    <th class="sortable">#</th>
                    <th class="sortable">Ticker / Name</th>
                    <th class="sortable" style="text-align:center;">Sector</th>
                    <th class="sortable" style="text-align:center;">Combined</th>
                    <th class="sortable" style="text-align:center;">Composite</th>
                    <th class="sortable" style="text-align:center;">Entry Score</th>
                    <th class="sortable">Trend / Regime</th>
                    <th style="text-align:center;">Ready</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


def generate_candidates_html(candidates: List[TradeCandidateAnalysis], data_dict: Dict) -> str:
    rows = ""
    ready_count = 0

    for c in candidates:
        if c.is_trade_ready:
            ready_count += 1

        # Mini Chart — slightly larger so EMA structure is readable
        chart = ""
        if c.ticker in data_dict:
            df = data_dict[c.ticker]
            chart = generate_price_chart_svg(
                df['close'], df['ema_20'], df['ema_50'],
                width=220, height=70, show_markers=False, show_grid=False
            )

        # Entry score coloring
        if c.entry_score >= 75:
            entry_color = "var(--accent-optimal)"
        elif c.entry_score >= 60:
            entry_color = "var(--accent-good)"
        elif c.entry_score >= 45:
            entry_color = "var(--accent-marginal)"
        else:
            entry_color = "var(--accent-poor)"

        # Stop distance as % of price
        stop_pct = ((c.price - c.stop_price) / c.price * 100) if c.price and c.price > 0 else 0

        # Why not trade ready? (show the missing condition)
        not_ready_hint = ""
        if not c.is_trade_ready:
            reasons = []
            if c.entry_score < 60:
                reasons.append(f"score {c.entry_score:.0f}<60")
            if c.regime != "TRENDING":
                reasons.append(f"regime={c.regime}")
            not_ready_hint = f'<div style="font-size:0.62rem; color:var(--accent-poor); margin-top:2px;">✗ {" · ".join(reasons)}</div>'

        breakdown_html = _score_breakdown_html(c.score_breakdown)
        ready_star = '<span style="color:var(--accent-optimal); font-size:1.1rem;">★</span>' if c.is_trade_ready else '<span style="color:var(--text-secondary); font-size:0.8rem;">–</span>'
        price_display = f"${c.price:.2f}" if c.price else "N/A"

        rows += f"""
        <tr data-entry-score="{c.entry_score:.0f}" data-regime="{c.regime}" data-sector="{c.sector_etf}">
            <td data-label="Ready" style="text-align:center;">{ready_star}{not_ready_hint}</td>
            <td data-label="Ticker">
                <b>{c.ticker}</b>
                <br><span class="text-xs text-muted">{c.name}</span>
            </td>
            <td data-label="Sector" style="text-align:center;">
                <span class="text-xs text-muted">{c.sector_etf}</span>
            </td>
            <td data-label="Price / ADX" style="text-align:center;">
                {price_display}
                <br><span class="text-xs text-muted">ADX {c.adx:.0f}</span>
            </td>
            <td data-label="Composite" style="text-align:center;">
                <b>{c.composite_score:.0f}</b>
                <br><span class="text-xs text-muted">Stage 1</span>
            </td>
            <td data-label="Entry Score" style="text-align:center;">
                <b style="color:{entry_color};">{c.entry_score:.0f}</b>
                {breakdown_html}
            </td>
            <td data-label="Trend / Regime">
                <span class="{_pill_class(c.trend)}">{c.trend}</span>
                <br><span class="{_pill_class(c.regime)}" style="margin-top:3px; display:inline-block;">{_regime_display(c.regime)}</span>
            </td>
            <td data-label="Stop" style="color:var(--accent-poor); font-size:0.8rem;">
                ${c.stop_price:.2f}
                <br><span class="text-xs">−{stop_pct:.1f}% · {c.stop_dist_atr:.1f}×ATR</span>
            </td>
            <td data-label="Chart">{chart}</td>
        </tr>
        """

    return f"""
    <h2 style="margin-top:2rem;">Trade Candidates (Stage 2)</h2>
    <p class="text-muted mb-2">
        Top 5 per sector scored by EMA-ADX-ATR Entry System (EMA Proximity 25 + ADX Stage 25 + Volume 20 + Structure 20 + R:R 10 = 100).
        ★ = Entry ≥60 <em>and</em> TRENDING regime.
    </p>
    <div class="glass-card">
        <div style="margin-bottom:1rem; display:flex; gap:0.75rem; flex-wrap:wrap; align-items:center;">
            <select id="cand-score-filter" class="search-input" style="width:auto; padding:0.35rem 0.65rem; font-size:0.8rem;">
                <option value="0">All Scores</option>
                <option value="75">75+ (Good+)</option>
                <option value="60">60+ (Acceptable+)</option>
                <option value="45">45+ (Marginal+)</option>
            </select>
            <select id="cand-regime-filter" class="search-input" style="width:auto; padding:0.35rem 0.65rem; font-size:0.8rem;">
                <option value="">All Regimes</option>
                <option value="LOW_VOLATILITY">Low Volatility</option>
                <option value="NORMAL_VOLATILITY">Normal Volatility</option>
                <option value="HIGH_VOLATILITY">High Volatility</option>
            </select>
            <select id="cand-sector-filter" class="search-input" style="width:auto; padding:0.35rem 0.65rem; font-size:0.8rem;">
                <option value="">All Sectors</option>
            </select>
            <span class="badge badge-optimal">{ready_count} Trade Ready</span>
            <span class="text-xs text-muted">
                Showing <span id="cand-visible-count">{len(candidates)}</span> of {len(candidates)} ·
                breakdown: green ≥70% · amber 40–69% · red &lt;40%
            </span>
        </div>
        <table class="modern-table" id="candidates-table">
            <thead>
                <tr>
                    <th style="width:60px;">Ready</th>
                    <th class="sortable">Ticker</th>
                    <th class="sortable" style="text-align:center;">Sector</th>
                    <th class="sortable" style="text-align:center;">Price / ADX</th>
                    <th class="sortable" style="text-align:center;">Composite</th>
                    <th class="sortable" style="text-align:center;">Entry Score</th>
                    <th class="sortable">Trend / Regime</th>
                    <th class="sortable">Stop / Risk</th>
                    <th>Chart</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


def generate_projections_html(ranked_projections: List[ProjectionResult]) -> str:
    rows = ""
    for i, p in enumerate(ranked_projections[:20]):
        conf_bar = generate_confidence_bar_svg(p.confidence_score)

        # Risk metrics
        risk_pct = (p.stop_distance / p.current_price * 100) if p.current_price > 0 else 0
        gain_3r_pct = (p.target_3r / p.current_price - 1) * 100 if p.current_price > 0 else 0

        # Confidence color
        if p.confidence_score >= 80:
            conf_color = "var(--accent-optimal)"
        elif p.confidence_score >= 50:
            conf_color = "var(--accent-good)"
        else:
            conf_color = "var(--accent-marginal)"

        rows += f"""
        <tr data-confidence="{p.confidence_level}">
            <td style="color:var(--text-secondary);">#{i+1}</td>
            <td>
                <b>{p.ticker}</b>
                <br><span class="text-xs text-muted">{p.sector}</span>
            </td>
            <td>${p.current_price:.2f}</td>
            <td style="text-align:center; color:var(--text-secondary);">
                {p.atr:.2f}
                <br><span class="text-xs" style="color:var(--text-secondary);">{p.atr_percent:.1f}%</span>
            </td>
            <td style="color:var(--accent-poor);">
                ${p.stop_price:.2f}
                <br><span class="text-xs">−{risk_pct:.1f}%</span>
            </td>
            <td style="color:var(--accent-optimal);">${p.target_2r:.2f}</td>
            <td style="color:var(--accent-optimal); font-weight:bold;">
                ${p.target_3r:.2f}
                <br><span class="text-xs">+{gain_3r_pct:.1f}%</span>
            </td>
            <td>
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    {conf_bar}
                    <span style="color:{conf_color}; font-weight:600;">{p.confidence_score:.0f}%</span>
                </div>
            </td>
        </tr>
        """

    return f"""
    <h2 style="margin-top:2rem;">Projections &amp; Targets (Stage 3)</h2>
    <p class="text-muted mb-2">ATR-based targets for trade-ready setups. Stop = regime-aware ATR multiple below EMA20. Targets = 2R and 3R multiples of that risk unit.</p>
    <div class="glass-card">
        <div style="margin-bottom:1rem; display:flex; gap:0.75rem; flex-wrap:wrap; align-items:center;">
            <select id="proj-conf-filter" class="search-input" style="width:auto; padding:0.35rem 0.65rem; font-size:0.8rem;">
                <option value="">All Confidence</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
            </select>
            <span class="text-xs text-muted">Showing <span id="proj-visible-count">{len(ranked_projections[:20])}</span> projections</span>
        </div>
        <table class="modern-table" id="projections-table">
            <thead>
                <tr>
                    <th class="sortable">#</th>
                    <th class="sortable">Ticker / Sector</th>
                    <th class="sortable">Price</th>
                    <th class="sortable" style="text-align:center;">ATR / ATR%</th>
                    <th class="sortable">Stop / Risk%</th>
                    <th class="sortable">2R Target</th>
                    <th class="sortable">3R Target / Gain%</th>
                    <th class="sortable">Confidence</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


def generate_sector_detail_page(
    etf: str,
    sector_name: str,
    ranked_stocks: List[CompositeScore],
    data_map: Dict,
    closes: pd.DataFrame,
    candidates: List[TradeCandidateAnalysis],
    output_dir: str = "reports",
    score_history: Optional[Dict] = None,
    watchlist_tickers: Optional[List[str]] = None,
) -> str:
    """
    Generate a detailed sector page with full charts for each stock.

    Args:
        etf: Sector ETF symbol (e.g., 'XLK')
        sector_name: Human-readable sector name
        ranked_stocks: List of CompositeScore objects for stocks in this sector
        data_map: Dict mapping ticker -> DataFrame with price/indicator data
        closes: DataFrame of close prices
        candidates: List of TradeCandidateAnalysis for trade-ready info
        output_dir: Output directory for HTML

    Returns:
        Path to the generated HTML file
    """
    # Build candidate lookup for this sector
    sector_candidates = {c.ticker: c for c in candidates if c.sector_etf == etf}

    # ETF Chart (large) with ADX panel
    etf_chart = ""
    if etf in data_map:
        df = data_map[etf]
        etf_chart = generate_price_with_adx_chart_svg(
            df['close'], df.get('ema_20'), df.get('ema_50'), df.get('adx'),
            width=900, height=350, show_markers=True
        )

    # Stock cards with individual charts
    stock_cards = ""
    for i, stock in enumerate(ranked_stocks[:25]):
        # Get candidate info if available
        cand = sector_candidates.get(stock.ticker)

        # Generate chart with ADX panel
        chart = ""
        if stock.ticker in data_map:
            df = data_map[stock.ticker]
            chart = generate_price_with_adx_chart_svg(
                df['close'], df.get('ema_20'), df.get('ema_50'), df.get('adx'),
                width=500, height=260, show_markers=True
            )

        # Score badges
        composite_color = "var(--accent-optimal)" if stock.composite_score >= 70 else \
                         "var(--accent-good)" if stock.composite_score >= 50 else \
                         "var(--accent-marginal)" if stock.composite_score >= 30 else "var(--accent-poor)"

        # Trade ready badge
        trade_badge = ""
        entry_info = ""
        if cand:
            if cand.is_trade_ready:
                trade_badge = '<span class="badge badge-optimal">Trade Ready</span>'
            breakdown_html = _score_breakdown_html(cand.score_breakdown)
            entry_info = f"""
                <div style="margin-top:0.5rem; padding-top:0.5rem; border-top:1px solid var(--border);">
                    <div style="display:flex; align-items:center; gap:1rem; flex-wrap:wrap;">
                        <span class="text-xs text-muted">Entry Score:</span>
                        <b style="color:{'var(--accent-optimal)' if cand.entry_score >= 60 else 'var(--text-primary)'};">{cand.entry_score:.0f}/100</b>
                        <span class="text-xs text-muted">ADX:</span> <b>{cand.adx:.0f}</b>
                        <span class="text-xs text-muted">Regime:</span>
                        <span class="{_pill_class(cand.regime)}">{_regime_display(cand.regime)}</span>
                    </div>
                    {breakdown_html}
                </div>
            """

        # Score history sparkline
        score_history_html = ""
        if score_history and stock.ticker in score_history:
            hist_scores = [d['entry_score'] for d in score_history[stock.ticker]]
            if len(hist_scores) >= 2:
                from src.sectors.history import build_score_sparkline_svg, get_score_trend
                sparkline_svg = build_score_sparkline_svg(hist_scores)
                trend = get_score_trend(hist_scores)
                trend_color = {
                    "IMPROVING": "var(--accent-optimal)",
                    "WORSENING": "var(--accent-poor)",
                }.get(trend, "var(--text-secondary)")
                score_history_html = (
                    f'<div style="display:flex; align-items:center; gap:4px; margin-top:4px;">'
                    f'{sparkline_svg}'
                    f'<span style="font-size:0.62rem; color:{trend_color};">{trend}</span>'
                    f'</div>'
                )

        # Watchlist star
        _wl = watchlist_tickers or []
        is_watchlisted = stock.ticker in _wl
        star_color = "#fbbf24" if is_watchlisted else "rgba(255,255,255,0.2)"
        star_char = "★" if is_watchlisted else "☆"
        watchlist_btn = (
            f'<button class="watchlist-btn" data-ticker="{stock.ticker}" onclick="toggleWatchlist(this)" '
            f'style="background:none; border:none; cursor:pointer; font-size:1.3rem; color:{star_color}; '
            f'padding:0; line-height:1;" aria-label="Toggle watchlist">{star_char}</button>'
        )

        # Highlight top 5
        card_border = "border-left: 4px solid var(--accent-optimal);" if i < 5 else ""
        rank_badge = f'<span style="color:var(--accent-optimal);">★ #{i+1}</span>' if i < 5 else f'#{i+1}'
        price_display = f"${stock.price:.2f}" if stock.price else "N/A"
        is_trade_ready = "true" if cand and cand.is_trade_ready else "false"

        stock_cards += f"""
        <div class="glass-card stock-card" style="{card_border}; position:relative;" data-ticker="{stock.ticker}" data-name="{stock.name}" data-rank="{i+1}" data-trade-ready="{is_trade_ready}">
            <div style="position:absolute; top:0.75rem; right:0.75rem; display:flex; align-items:center; gap:0.5rem;">
                {watchlist_btn}
                <a href="stock_{stock.ticker}.html" style="text-decoration:none;">
                    <span class="badge badge-info" style="font-size:0.65rem;">Company Info</span>
                </a>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1rem; padding-right:8rem;">
                <div>
                    <h3 style="margin:0;">{stock.ticker}</h3>
                    <span class="text-xs text-muted">{stock.name}</span>
                    <div style="margin-top:0.5rem;">
                        <span class="text-xs text-muted">Rank:</span> {rank_badge}
                        {trade_badge}
                    </div>
                    {score_history_html}
                </div>
                <div style="text-align:right;">
                    <div style="font-size:1.5rem; font-weight:bold;">{price_display}</div>
                    <div class="{_color_class(stock.rel_3m)}">{fmt_pct(stock.rel_3m)} vs {etf}</div>
                </div>
            </div>

            <div class="mb-2">
                {chart}
            </div>

            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:1rem; text-align:center;">
                <div>
                    <div class="text-xs text-muted">Composite</div>
                    <div style="font-size:1.25rem; font-weight:bold; color:{composite_color};">{stock.composite_score:.0f}</div>
                </div>
                <div>
                    <div class="text-xs text-muted">RS Score</div>
                    <div style="font-size:1.25rem; font-weight:bold;">{stock.relative_strength_score:.0f}</div>
                </div>
                <div>
                    <div class="text-xs text-muted">Trend</div>
                    <span class="{_pill_class(stock.trend)}">{stock.trend}</span>
                </div>
                <div>
                    <div class="text-xs text-muted">Volume</div>
                    <div style="font-size:1.25rem; font-weight:bold;">{stock.volume_ratio:.1f}x</div>
                </div>
            </div>
            {entry_info}
        </div>
        """

    # Full HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{sector_name} ({etf}) | Sector Analysis</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
            {CSS_DARK_THEME}
            .text-optimal {{ color: var(--accent-optimal); }}
            .text-poor {{ color: var(--accent-poor); }}
            .stock-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(550px, 1fr)); gap: 1.5rem; }}
        </style>
        <script>window.__SERVER_WATCHLIST__ = {json.dumps(watchlist_tickers or [])};</script>
    </head>
    <body>
        {generate_top_nav("")}
        <div class="container">
            {generate_breadcrumb([("Command Center", "index.html"), ("Sector Analysis", "sector_analysis.html"), (sector_name, None)])}

            <header class="mb-4">
                <h1>{sector_name}</h1>
                <p class="text-muted">{etf} • Top 25 Stocks with EMA/ADX/ATR Indicators</p>
            </header>

            <section class="mb-6">
                <h2>Sector ETF: {etf}</h2>
                <div class="glass-card">
                    {etf_chart}
                </div>
            </section>

            {METRICS_GUIDE_HTML}

            <section>
                <h2>Stocks by Composite Score</h2>
                <div class="filter-bar">
                    <input type="text" id="stock-search" class="search-input" placeholder="Search by ticker or name...">
                    <button class="filter-btn" data-filter="top5">Top 5 Only</button>
                    <button class="filter-btn" data-filter="trade-ready">Trade Ready</button>
                    <span class="text-muted text-sm">Showing <span id="visible-count">25</span> stocks • ★ = Stage 2 candidates</span>
                </div>
                <div class="stock-grid">
                    {stock_cards}
                </div>
                <div id="search-empty-state" class="hidden empty-state glass-card" style="margin-top:1rem;">
                    <div class="empty-icon">🔍</div>
                    <p>No stocks match your search.</p>
                    <p class="text-xs">Try a different ticker symbol or clear the search field.</p>
                </div>
            </section>

            <footer style="margin-top:4rem; text-align:center; color:var(--text-secondary);">
                <p>Macro Watch 2.1 • {sector_name} Sector Detail</p>
            </footer>
        </div>
        {INTERACTIVE_JS}
    </body>
    </html>
    """

    # Write file
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    out_path = os.path.join(output_dir, f"sector_{etf}.html")
    with open(out_path, "w") as f:
        f.write(html)

    return out_path


def run_sector_analysis(output_dir="reports", focus_sector: Optional[str] = None, ai_memo: bool = False, ai_macro_memo: bool = False):
    """
    Run sector analysis dashboard.

    Args:
        output_dir: Output directory for HTML
        focus_sector: Optional sector ETF to focus on (e.g., 'XLK')
        ai_memo: Generate top candidates AI memo
        ai_macro_memo: Generate macro drivers AI memo
    """
    print("Running Sector Analysis...")
    config = load_config()

    # Filter to single sector if specified
    if focus_sector:
        focus_sector = focus_sector.upper()
        if focus_sector in config.get('sectors', {}):
            print(f"Focusing on sector: {focus_sector}")
            config['sectors'] = {focus_sector: config['sectors'][focus_sector]}
        else:
            available = list(config.get('sectors', {}).keys())
            print(f"Error: Sector '{focus_sector}' not found. Available: {available}")
            return None
    tickers = get_all_tickers(config)
    
    # 1. Fetch Data (Parallel)
    raw_data = fetch_data_parallel(tickers, period="2y", interval="1wk", max_workers=10)

    # Process fetched data
    data_map = {}
    closes_dict = {}

    for t, df in raw_data.items():
        try:
            # Make a copy to avoid modifying the cached data
            df = df.copy()
            # Normalize columns to lowercase
            df.columns = [c.lower() for c in df.columns]
            # Calculate indicators needed for scoring/charts
            df['ema_20'] = df['close'].ewm(span=20).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()

            # Calculate ADX for charts
            high = df['high']
            low = df['low']
            close = df['close']

            # True Range
            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            # Directional Movement
            plus_dm = high.diff()
            minus_dm = -low.diff()
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

            # Smoothed averages (14 period)
            atr = tr.ewm(span=14, adjust=False).mean()
            plus_di = 100 * (plus_dm.ewm(span=14, adjust=False).mean() / atr)
            minus_di = 100 * (minus_dm.ewm(span=14, adjust=False).mean() / atr)

            # ADX
            dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 0.0001))
            df['adx'] = dx.ewm(span=14, adjust=False).mean()

            data_map[t] = df
            closes_dict[t] = df['close']
        except Exception as e:
            print(f"Error processing {t}: {e}")
            
    closes = pd.DataFrame(closes_dict)
    
    # 2. Stage 1: Analyze & Rank within Sectors
    print("Stage 1: Sector Ranking...")
    ranked_sectors = {}
    
    for etf, info in config.get('sectors', {}).items():
        # ETF data
        etf_metrics = None # Placeholder if needed
        
        # Stock metrics
        stock_metrics_list = []
        for symbol, name in info.get('stocks', {}).items():
            if symbol not in data_map: continue
            
            # Build metrics (manually recreating build_stock_metrics logic here using df)
            # Need strict alignment
            metrics = build_stock_metrics(
                symbol, name, info['name'], etf, closes, data_map
            )
            stock_metrics_list.append(metrics)
            
        # Rank logic
        ranked_sectors[etf] = rank_all_sectors({etf: stock_metrics_list})[etf]

    # --- DRIVER ANALYSIS ---
    print("Analyzing Drivers...")
    sector_drivers_map = {} # {etf: [DriverAnalysis]}
    
    # Identify unique drivers to fetch
    all_drivers = {} # {ticker: name}
    for etf, info in config.get('sectors', {}).items():
        if 'drivers' in info:
            all_drivers.update(info['drivers'])
            
    # Fetch drivers
    driver_data = fetch_drivers(all_drivers, period="1y")
    
    # Analyze per sector
    for etf, info in config.get('sectors', {}).items():
        if 'drivers' in info and etf in closes:
            sector_closes = closes[etf]
            # Analyze
            res = analyze_drivers(etf, sector_closes, info['drivers'], driver_data)
            sector_drivers_map[etf] = res

    # 3. Stage 2: Trade Candidates (Integration with Core Logic)
    print("Stage 2: Core Analysis...")
    candidates = []
    flat_ranked = get_trade_candidates(ranked_sectors, top_n=5) # Top 5 per sector
    
    for c in flat_ranked:
        # Run Core Analysis using src.scoring
        if c.ticker not in data_map: continue
        
        # We need to map the dataframe back to what core_scoring expects (Capitalized columns)
        df_core = data_map[c.ticker].copy()
        df_core.columns = [col.title() for col in df_core.columns] # Open, High, Low, Close...
        
        # Analyze using framework 2.0 logic
        try:
            # Calculate Indicators
            df_core = calculate_all_indicators(df_core)
            
            # Score
            scorer = core_scoring.EntryScorer(df_core)
            res = scorer.score() # Returns ScoreResult
            
            # Map ScoreResult to Analysis Object
            # Logic: Trade Ready if Score > 70? Or Regime matches?
            # Using new framework's score as proxy for "Signal Strength"
            
            signal_str = "WEAK"
            if res.total_score >= 80: signal_str = "STRONG"
            elif res.total_score >= 60: signal_str = "MODERATE"

            # Derive trend-readiness from score + volatility regime.
            # EntryScorer returns volatility regime (HIGH/NORMAL/LOW_VOLATILITY), not
            # a trend regime — checking == "TRENDING" was always False.
            # Trade-ready = acceptable entry score AND not in extreme volatility.
            is_ready = res.total_score >= 60 and res.regime != "HIGH_VOLATILITY"

            # Derive a trend-regime string for the projection confidence scorer,
            # which expects "TRENDING" / "CHOPPING" / "SIDEWAYS".
            trend_regime = "TRENDING" if signal_str in ("STRONG", "MODERATE") else "CHOPPING"

            # Regime-aware stop: use the same multiplier the scorer used
            stop_dist_atr = scorer.regime_params.stop_distance_atr
            stop_price = res.details['ema20'] - stop_dist_atr * res.details['atr']

            # Real volume confirmation — compute from DataFrame (not in res.details)
            vol_avg = df_core['Vol_Avg'].iloc[-1]
            vol_curr = df_core['Volume'].iloc[-1]
            if vol_avg and not math.isnan(float(vol_avg)) and float(vol_avg) > 0:
                vol_ratio = float(vol_curr) / float(vol_avg)
            else:
                vol_ratio = 1.0
            volume_confirms = vol_ratio >= 1.0

            # Create Candidate Analysis
            # Store volatility regime for display; trend_regime used for projections.
            cand = TradeCandidateAnalysis(
                ticker=c.ticker, name=c.name, sector=c.sector, sector_etf=c.sector_etf,
                composite_score=c.composite_score, rank_in_sector=c.rank_in_sector,
                price=res.details['price'], rel_3m=c.rel_3m, trend=c.trend,
                regime=res.regime, signal_strength=signal_str,
                entry_score=res.total_score,
                adx=res.details.get('adx', 0),
                atr=res.details['atr'],
                volume_ratio=vol_ratio,
                is_trade_ready=is_ready,
                stop_price=stop_price,
                stop_dist_atr=stop_dist_atr,
                score_breakdown=res.breakdown if hasattr(res, 'breakdown') else None,
            )
            candidates.append(cand)
            
        except Exception as e:
            print(f"Analysis failed for {c.ticker}: {e}")

    candidates.sort(key=lambda x: x.composite_score, reverse=True)

    # 3b. Save history snapshot and load prior history
    from src.sectors.history import (
        save_daily_snapshot, load_history, evaluate_past_projections,
        build_score_sparkline_svg, get_score_trend,
    )

    # 4. Stage 3: Projections
    print("Stage 3: Projections...")
    projections = []
    for cand in candidates:
        if not cand.is_trade_ready: continue

        # Convert volatility regime → trend regime expected by projection confidence scorer
        proj_regime = "TRENDING" if cand.signal_strength in ("STRONG", "MODERATE") else "CHOPPING"

        proj = calculate_projection(
            cand.ticker, cand.name, cand.price, cand.atr,
            cand.signal_strength, proj_regime,
            volume_confirms=(cand.volume_ratio >= 1.0),
            composite_score=cand.composite_score, sector=cand.sector,
            stop_price=cand.stop_price,
        )
        projections.append(proj)
        
    ranked_projections = rank_projections(projections)

    # 4b. Persist snapshot (after projections are known) and load history
    save_daily_snapshot(candidates, ranked_projections, output_dir)
    score_history_map = load_history(output_dir, days=30)
    backtest_results = evaluate_past_projections(output_dir, closes)

    # Load watchlist for star pre-population
    watchlist_tickers: List[str] = []
    _watchlist_path = os.path.join(output_dir, "watchlist.json")
    if os.path.exists(_watchlist_path):
        try:
            with open(_watchlist_path) as _wf:
                watchlist_tickers = json.load(_wf)
        except Exception:
            pass

    # 5. Calculate Sector Metrics for Leaderboard
    print("Calculating Sector Metrics...")
    sector_metrics = calculate_sector_metrics(config, ranked_sectors, closes, candidates)

    # 6. Generate HTML
    print("Generating Dashboard...")

    benchmarks_html_str = generate_benchmarks_html(closes, data_map)
    leaderboard_html_str = generate_sector_leaderboard_html(sector_metrics, closes=closes)
    global_leaderboard_html_str = generate_global_leaderboard_html(candidates)
    sectors_html_str = generate_sector_html(config, ranked_sectors, closes, sector_drivers_map)
    candidates_html_str = generate_candidates_html(candidates, data_map)
    projections_html_str = generate_projections_html(ranked_projections)
    signal_perf_html_str = generate_signal_performance_html(backtest_results)

    full_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sector Analysis | Macro Watch 2.1</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
            {CSS_DARK_THEME}
            .text-optimal {{ color: var(--accent-optimal); }}
            .text-poor {{ color: var(--accent-poor); }}
            .grid-cols-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.5rem; }}
        </style>
        <script>window.__SERVER_WATCHLIST__ = {__import__('json').dumps(watchlist_tickers)};</script>
    </head>
    <body>
        {generate_top_nav("sector_analysis")}
        <div class="container">
            {generate_breadcrumb([("Command Center", "index.html"), ("Sector Analysis", None)])}

            <header class="mb-4">
                <h1>Sector Analysis Dashboard</h1>
                <p class="text-muted">Top 25 Stocks per Sector • 4-Stage Screening</p>
                <div style="margin-top: 1rem; display:flex; gap:0.75rem; flex-wrap:wrap; align-items:center;">
                    <button onclick="exportWatchlist()" class="filter-btn" style="font-size:0.8rem;">
                        ★ Export Watchlist
                    </button>
                    <span class="text-xs text-muted">Click ★/☆ on any stock card or use sector detail pages to manage your watchlist</span>
                </div>
            </header>

            {METRICS_GUIDE_HTML}
            {benchmarks_html_str}
            {leaderboard_html_str}
            {global_leaderboard_html_str}
            {sectors_html_str}
            {candidates_html_str}
            {projections_html_str}
            {signal_perf_html_str}
            
            <footer style="margin-top:4rem; text-align:center; color:var(--text-secondary);">
                <p>Macro Watch 2.1 • Unified Intelligence Layer</p>
            </footer>
        </div>
        {INTERACTIVE_JS}
    </body>
    </html>
    """
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    out_path = os.path.join(output_dir, "sector_analysis.html")
    with open(out_path, "w") as f:
        f.write(full_html)

    print(f"Sector Dashboard saved to {out_path}")

    # 6b. Generate Macro Drivers Page
    print("Generating Macro Drivers Page...")
    generate_macro_page(config, sector_drivers_map, closes, output_dir)

    # 7. Generate Individual Sector Detail Pages
    print("Generating Sector Detail Pages...")
    full_config = load_config()  # Reload full config for all sectors
    for etf, info in full_config.get('sectors', {}).items():
        ranked = ranked_sectors.get(etf, [])
        if not ranked:
            continue

        detail_path = generate_sector_detail_page(
            etf=etf,
            sector_name=info.get('name', etf),
            ranked_stocks=ranked,
            data_map=data_map,
            closes=closes,
            candidates=candidates,
            output_dir=output_dir,
            score_history=score_history_map,
            watchlist_tickers=watchlist_tickers,
        )
        print(f"  - {etf}: {detail_path}")

    # 8. Generate Individual Stock Narrative Pages
    print("Generating Stock Narrative Pages...")
    from src.stocks.narrative import generate_all_stock_pages

    # Build candidates lookup for entry scores
    candidates_lookup = {c.ticker: c for c in candidates}

    stock_pages = generate_all_stock_pages(
        ranked_sectors=ranked_sectors,
        sector_config={etf: {'name': info.get('name', etf)} for etf, info in full_config.get('sectors', {}).items()},
        candidates_lookup=candidates_lookup,
        output_dir=output_dir,
        max_workers=10
    )
    print(f"Stock narrative pages: {len(stock_pages)} generated")

    if ai_memo:
        print("Gathering data for AI Strategy Memo...")
        top_candidates = candidates[:30]
        json_data = []
        for c in top_candidates:
            json_data.append({
                "ticker": c.ticker,
                "name": c.name,
                "sector": c.sector,
                "price": round(c.price, 2) if hasattr(c, 'price') else None,
                "composite_score": round(c.composite_score, 1),
                "rank_in_sector": c.rank_in_sector,
                "relative_strength_3m": round(c.rel_3m, 2),
                "trend": getattr(c, 'trend', 'N/A'),
                "regime": getattr(c, 'regime', 'N/A'),
                "signal_strength": getattr(c, 'signal_strength', 'N/A'),
                "adx_momentum": round(c.adx, 1) if hasattr(c, 'adx') else None,
                "atr_volatility": round(c.atr, 2) if hasattr(c, 'atr') else None
            })
        generate_investment_memo(json_data, output_dir=output_dir)

    if ai_macro_memo:
        print("Gathering data for AI Macro Strategy Memo...")
        macro_json_data = {}
        # Serialize the sector_drivers_map for the AI prompt
        for sector, drivers in sector_drivers_map.items():
            macro_json_data[sector] = []
            if drivers:
                for d in drivers:
                    pct_off_high = round(((d.current_price / d.high_52w) - 1) * 100, 1) if d.high_52w else None
                    macro_json_data[sector].append({
                        "driver_ticker": d.ticker,
                        "driver_name": d.name,
                        "current_value": round(d.current_price, 2),
                        "52w_high": round(d.high_52w, 2),
                        "52w_low": round(d.low_52w, 2),
                        "pct_off_52w_high": pct_off_high,
                        "1m_change_pct": round(d.change_1m * 100, 2),
                        "3m_change_pct": round(d.change_3m * 100, 2),
                        "ytd_change_pct": round(d.change_ytd * 100, 2),
                        "90d_correlation_to_sector": round(d.correlation_90d, 2),
                        "short_term_trend": d.trend
                    })
        generate_macro_investment_memo(macro_json_data, output_dir=output_dir)


    print(f"\nAll pages generated in {output_dir}/")
    return out_path

