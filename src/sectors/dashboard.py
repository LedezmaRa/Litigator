"""
Sector Funnel Dashboard - Macro Watch 2.1 (Unified)

Four-Stage Stock Screening System:
- Benchmarks: Market context (SPY, QQQ, IWM, VIX)
- Stage 1: Sector Overview with all stocks ranked by composite score
- Stage 2: Trade Candidates with charts and EMA-ADX-ATR analysis
- Stage 3: Projections with ATR-based targets

Output: Single HTML dashboard (sector_analysis.html)
"""
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
from src.dashboard import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav  # Shared Theme + JS
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
    if "strong" in v or "accelerating" in v or "trending" in v: return "badge badge-optimal"
    if "moderate" in v or "steady" in v: return "badge badge-good"
    if "weak" in v or "decelerating" in v: return "badge badge-marginal"
    return "badge badge-poor"


# --- SECTOR METRICS ---

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
            etf_ret_3m=etf_ret_3m
        ))

    # Sort by top5 average score descending
    metrics_list.sort(key=lambda x: x.top5_avg_score, reverse=True)
    return metrics_list


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

        rows += f"""
        <tr>
            <td style="color:{rank_color}; font-weight:bold;">#{i+1}</td>
            <td>
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
            <td style="text-align:center;">
                <b>{m.top5_avg_score:.0f}</b>
                <br><span class="text-xs text-muted">top 5</span>
            </td>
            <td style="text-align:center;">{m.avg_composite_score:.0f}</td>
            <td style="text-align:center; color:{pct_up_color}; font-weight:600;">{m.pct_trending_up:.0f}%</td>
            <td style="text-align:center;">{ready_badge}</td>
            <td class="{_color_class(m.etf_ret_1w)}">{fmt_pct(m.etf_ret_1w)}</td>
            <td class="{_color_class(m.etf_ret_1m)}">{fmt_pct(m.etf_ret_1m)}</td>
            <td class="{_color_class(m.etf_ret_3m)}">{fmt_pct(m.etf_ret_3m)}</td>
        </tr>
        """

    return f"""
    <h2 style="margin-top:2rem;">Sector Leaderboard</h2>
    <p class="text-muted" style="margin-bottom:1rem;">
        Ranked by Top 5 Average Composite Score (RS 50% + Trend 30% + Volume 20%, percentile within sector, 0–100) •
        % Up = share of stocks with positive 3M relative return vs sector ETF •
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
        <div class="glass-card" style="min-width:0;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.2rem;">
                <div>
                    <div style="font-size:0.75rem; font-weight:700; letter-spacing:0.06em; color:var(--text-secondary); text-transform:uppercase;">{b}</div>
                    <div style="font-size:0.95rem; font-weight:600; color:var(--text-primary);">{name}</div>
                </div>
                <div style="text-align:right; flex-shrink:0; margin-left:0.5rem;">
                    <div style="font-size:1.3rem; font-weight:bold;">{val_display}</div>
                    <div class="{chg_color}" style="font-size:0.75rem;">1W: {chg_display}</div>
                </div>
            </div>
            <div style="font-size:0.7rem; color:var(--text-secondary); line-height:1.45; margin-bottom:0.5rem; border-left:2px solid rgba(255,255,255,0.1); padding-left:0.5rem;">{desc}</div>
            {range_bar}
            {returns_html}
            <div>{chart}</div>
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
            <div class="glass-card" style="min-width:0;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.2rem;">
                    <div>
                        <div style="font-size:0.75rem; font-weight:700; letter-spacing:0.06em; color:var(--text-secondary); text-transform:uppercase;">^TNX − ^IRX</div>
                        <div style="font-size:0.95rem; font-weight:600; color:var(--text-primary);">Yield Curve (10Y−3M)</div>
                    </div>
                    <div style="text-align:right; flex-shrink:0; margin-left:0.5rem;">
                        <div style="font-size:1.3rem; font-weight:bold; color:{spread_color};">{curr_spread:+.2f}%</div>
                        <div style="font-size:0.75rem; color:{spread_color}; font-weight:600;">1W: {chg_1w_display} · {status_label}</div>
                    </div>
                </div>
                <div style="font-size:0.7rem; color:var(--text-secondary); line-height:1.45; margin-bottom:0.5rem; border-left:2px solid rgba(255,255,255,0.1); padding-left:0.5rem;">{desc_yc}</div>
                {spread_range_bar}
                {spread_returns}
                <div>{spread_chart}</div>
            </div>
            """

    return f"""
    <h2 style="margin-top:2rem;">Market Benchmarks</h2>
    <p class="text-muted" style="margin-bottom:1rem;">Key market indicators with historical context — where are we today vs. the past 52 weeks?</p>
    <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(230px, 1fr)); gap:1.5rem; margin-bottom:2rem;">
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
                <td style="color:var(--text-secondary);">#{i+1}</td>
                <td><b>{stock.ticker}</b>{stage2_marker}<br><span class="text-xs text-muted">{price_display}</span></td>
                <td style="min-width:60px;">
                    <span style="font-weight:600;">{stock.composite_score:.0f}</span>
                    {score_bar}
                </td>
                <td class="{_color_class(stock.rel_3m)}">{fmt_pct(stock.rel_3m)}</td>
                <td><span class="{trend_badge}">{stock.trend}</span></td>
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
    <p class="text-muted" style="margin-bottom:1rem;">25 stocks per sector ranked by Composite Score (Relative Strength 50% + Trend 30% + Volume 20%)</p>
    <div class="grid-cols-3" style="display:grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap:1.5rem;">
        {html}
    </div>
    """


def _score_breakdown_html(breakdown: Optional[Dict]) -> str:
    """Compact 5-component breakdown bar for the entry score cell."""
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
        cells += (
            f'<div style="text-align:center; background:{color}; border-radius:2px; padding:1px 2px;">'
            f'<div style="font-size:0.58rem; color:var(--text-secondary);">{label}</div>'
            f'<div style="font-size:0.68rem; font-weight:600;">{score:.0f}</div>'
            f'</div>'
        )
    return f'<div style="display:grid; grid-template-columns:repeat(5,1fr); gap:2px; margin-top:3px;">{cells}</div>'


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
        <tr>
            <td style="text-align:center;">{ready_star}{not_ready_hint}</td>
            <td>
                <b>{c.ticker}</b>
                <br><span class="text-xs text-muted">{c.name}</span>
            </td>
            <td style="text-align:center;">
                <span class="text-xs text-muted">{c.sector_etf}</span>
            </td>
            <td style="text-align:center;">
                {price_display}
                <br><span class="text-xs text-muted">ADX {c.adx:.0f}</span>
            </td>
            <td style="text-align:center;">
                <b>{c.composite_score:.0f}</b>
                <br><span class="text-xs text-muted">Stage 1</span>
            </td>
            <td style="text-align:center;">
                <b style="color:{entry_color};">{c.entry_score:.0f}</b>
                {breakdown_html}
            </td>
            <td>
                <span class="{_pill_class(c.trend)}">{c.trend}</span>
                <br><span class="{_pill_class(c.regime)}" style="margin-top:3px; display:inline-block;">{c.regime}</span>
            </td>
            <td style="color:var(--accent-poor); font-size:0.8rem;">
                ${c.stop_price:.2f}
                <br><span class="text-xs">−{stop_pct:.1f}% · {c.stop_dist_atr:.1f}×ATR</span>
            </td>
            <td>{chart}</td>
        </tr>
        """

    return f"""
    <h2 style="margin-top:2rem;">Trade Candidates (Stage 2)</h2>
    <p class="text-muted" style="margin-bottom:1rem;">
        Top 5 per sector scored by EMA-ADX-ATR Entry System (EMA Proximity 25 + ADX Stage 25 + Volume 20 + Structure 20 + R:R 10 = 100).
        ★ = Entry ≥60 <em>and</em> TRENDING regime.
    </p>
    <div class="glass-card">
        <div style="margin-bottom:1rem; display:flex; gap:1rem; align-items:center; flex-wrap:wrap;">
            <span class="badge badge-optimal">{ready_count} Trade Ready</span>
            <span class="text-xs text-muted">Score breakdown: green ≥70% · amber 40–69% · red &lt;40% of component max</span>
        </div>
        <table class="modern-table">
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
        <tr>
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
    <p class="text-muted" style="margin-bottom:1rem;">ATR-based targets for trade-ready setups. Stop = regime-aware ATR multiple below EMA20. Targets = 2R and 3R multiples of that risk unit.</p>
    <div class="glass-card">
        <table class="modern-table">
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
    output_dir: str = "reports"
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
            entry_info = f"""
                <div style="margin-top:0.5rem; padding-top:0.5rem; border-top:1px solid var(--border);">
                    <span class="text-xs text-muted">Entry Score:</span>
                    <b style="color:{'var(--accent-optimal)' if cand.entry_score >= 60 else 'var(--text-primary)'};">{cand.entry_score:.0f}</b>
                    <span class="text-xs text-muted" style="margin-left:1rem;">ADX:</span> <b>{cand.adx:.0f}</b>
                    <span class="text-xs text-muted" style="margin-left:1rem;">Regime:</span>
                    <span class="{_pill_class(cand.regime)}">{cand.regime}</span>
                </div>
            """

        # Highlight top 5
        card_border = "border-left: 4px solid var(--accent-optimal);" if i < 5 else ""
        rank_badge = f'<span style="color:var(--accent-optimal);">★ #{i+1}</span>' if i < 5 else f'#{i+1}'
        price_display = f"${stock.price:.2f}" if stock.price else "N/A"
        is_trade_ready = "true" if cand and cand.is_trade_ready else "false"

        stock_cards += f"""
        <div class="glass-card stock-card" style="{card_border}; position:relative;" data-ticker="{stock.ticker}" data-name="{stock.name}" data-rank="{i+1}" data-trade-ready="{is_trade_ready}">
            <a href="stock_{stock.ticker}.html" style="position:absolute; top:0.75rem; right:0.75rem; text-decoration:none;">
                <span class="badge badge-info" style="font-size:0.65rem;">Company Info</span>
            </a>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1rem; padding-right:6rem;">
                <div>
                    <h3 style="margin:0;">{stock.ticker}</h3>
                    <span class="text-xs text-muted">{stock.name}</span>
                    <div style="margin-top:0.5rem;">
                        <span class="text-xs text-muted">Rank:</span> {rank_badge}
                        {trade_badge}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:1.5rem; font-weight:bold;">{price_display}</div>
                    <div class="{_color_class(stock.rel_3m)}">{fmt_pct(stock.rel_3m)} vs {etf}</div>
                </div>
            </div>

            <div style="margin-bottom:1rem;">
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
    </head>
    <body>
        {generate_top_nav("")}
        <div class="container">
            <a href="sector_analysis.html" class="back-link">&larr; Back to Sector Overview</a>

            <header style="margin-bottom:2rem;">
                <h1>{sector_name}</h1>
                <p class="text-muted">{etf} • Top 25 Stocks with EMA/ADX/ATR Indicators</p>
            </header>

            <section style="margin-bottom:3rem;">
                <h2>Sector ETF: {etf}</h2>
                <div class="glass-card">
                    {etf_chart}
                </div>
            </section>

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

            is_ready = res.total_score >= 60 and res.regime == "TRENDING"

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

    # 4. Stage 3: Projections
    print("Stage 3: Projections...")
    projections = []
    for cand in candidates:
        if not cand.is_trade_ready: continue
        
        proj = calculate_projection(
            cand.ticker, cand.name, cand.price, cand.atr,
            cand.signal_strength, cand.regime,
            volume_confirms=(cand.volume_ratio >= 1.0),
            composite_score=cand.composite_score, sector=cand.sector,
            stop_price=cand.stop_price,
        )
        projections.append(proj)
        
    ranked_projections = rank_projections(projections)

    # 5. Calculate Sector Metrics for Leaderboard
    print("Calculating Sector Metrics...")
    sector_metrics = calculate_sector_metrics(config, ranked_sectors, closes, candidates)

    # 6. Generate HTML
    print("Generating Dashboard...")

    benchmarks_html_str = generate_benchmarks_html(closes, data_map)
    leaderboard_html_str = generate_sector_leaderboard_html(sector_metrics, closes=closes)
    sectors_html_str = generate_sector_html(config, ranked_sectors, closes, sector_drivers_map)
    candidates_html_str = generate_candidates_html(candidates, data_map)
    projections_html_str = generate_projections_html(ranked_projections)

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
    </head>
    <body>
        {generate_top_nav("sector_analysis")}
        <div class="container">

            <header style="margin-bottom:2rem;">
                <h1>Sector Analysis Dashboard</h1>
                <p class="text-muted">Top 25 Stocks per Sector • 4-Stage Screening</p>
                <div style="margin-top: 1rem;">
                </div>
            </header>

            {benchmarks_html_str}
            {leaderboard_html_str}
            {sectors_html_str}
            {candidates_html_str}
            {projections_html_str}
            
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
            output_dir=output_dir
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

