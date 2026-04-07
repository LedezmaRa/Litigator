"""
Market Breadth Module
=====================
Calculates S&P 500 market breadth metrics to determine whether a rally is
broad-based (healthy) or narrow and concentrated (a warning sign).

Metrics computed
----------------
- % of S&P 500 stocks above their 20-week moving average  (~50-day proxy)
- % of S&P 500 stocks above their 40-week moving average  (~200-day proxy)
- Net new 52-week highs minus new 52-week lows
- Advance/Decline trend: 4-week change in breadth participation

Overall health label
--------------------
BROAD_BULL  (80-100) — broad, sustained participation
HEALTHY     (60-79)  — solid majority above key MAs
MIXED       (40-59)  — split market, leadership narrowing
WEAKENING   (20-39)  — majority below key MAs, deteriorating
BEAR_MARKET (0-19)   — extreme market stress

Caching
-------
S&P 500 constituent data is expensive to fetch (500 tickers × 52 weeks).
Results are cached to /tmp/breadth_cache.pkl with a 24-hour TTL so repeated
calls within the same trading session are instant.

Design notes
------------
- The Wikipedia list of S&P 500 companies is used to source tickers — it is
  publicly maintained and reliably formatted.
- yfinance batch downloads are used to minimize round trips.
- All errors are caught; partial data is used wherever possible.
"""

from __future__ import annotations

import os
import pickle
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_PATH = Path("/tmp/breadth_cache.pkl")
_CACHE_TTL_HOURS = 24
_WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

_EXPLANATION = (
    "Market breadth measures whether a stock market rally is being driven by "
    "all stocks rising together (healthy, sustainable) or just a handful of "
    "large-caps dragging the index higher while most stocks decline (unhealthy, "
    "dangerous). A market where only 30% of stocks are above their 50-day "
    "moving average while the index makes new highs is a warning sign — the "
    "foundation is eroding. The biggest crashes in history were preceded by "
    "deteriorating breadth."
)

_HEALTH_COLORS: dict[str, str] = {
    "BROAD_BULL": "var(--color-bull)",
    "HEALTHY": "var(--color-bull)",
    "MIXED": "var(--color-neutral)",
    "WEAKENING": "var(--color-bear)",
    "BEAR_MARKET": "var(--color-bear)",
}


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _is_cache_valid() -> bool:
    """Return True if the breadth cache file exists and is under 24 hours old."""
    if not _CACHE_PATH.exists():
        return False
    mtime = datetime.fromtimestamp(_CACHE_PATH.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=_CACHE_TTL_HOURS)


def _read_cache() -> dict[str, Any] | None:
    """Read and return the cached breadth result, or None on failure."""
    try:
        with open(_CACHE_PATH, "rb") as fh:
            return pickle.load(fh)
    except Exception:
        return None


def _write_cache(result: dict[str, Any]) -> None:
    """Write a breadth result dict to the disk cache; silently ignore errors."""
    try:
        with open(_CACHE_PATH, "wb") as fh:
            pickle.dump(result, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# S&P 500 ticker list
# ---------------------------------------------------------------------------

def _get_sp500_tickers() -> list[str]:
    """
    Fetch the current S&P 500 constituent list from Wikipedia.

    Returns a list of yfinance-compatible ticker strings (dots replaced with
    hyphens, e.g. 'BRK-B').  Falls back to a short hard-coded emergency list
    of 30 large-caps if the Wikipedia request fails.
    """
    try:
        sp500 = pd.read_html(_WIKIPEDIA_SP500_URL)[0]
        tickers = (
            sp500["Symbol"]
            .str.strip()
            .str.replace(".", "-", regex=False)
            .tolist()
        )
        return tickers
    except Exception:
        # Fallback: representative 30-stock list so the module still runs
        return [
            "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "BRK-B",
            "JPM", "V", "UNH", "XOM", "MA", "LLY", "HD", "CVX",
            "PG", "MRK", "ABBV", "PEP", "KO", "COST", "ADBE", "AVGO",
            "TMO", "MCD", "WMT", "CSCO", "ACN", "BAC", "CRM",
        ]


# ---------------------------------------------------------------------------
# Core breadth calculation
# ---------------------------------------------------------------------------

def _calculate_breadth_from_prices(close: pd.DataFrame) -> dict[str, Any]:
    """
    Given a DataFrame of weekly close prices (columns = tickers, index = dates),
    compute all breadth metrics and return them as a plain dict.

    Parameters
    ----------
    close : pd.DataFrame
        Wide-format weekly close prices, at least 52 rows, many ticker columns.

    Returns
    -------
    dict with all breadth metrics and educational strings.
    """
    errors: list[str] = []
    n_tickers = close.shape[1]

    if n_tickers == 0:
        return _empty_result("No price data available after download.")

    # ------------------------------------------------------------------ #
    # Moving averages for the LATEST week
    # ------------------------------------------------------------------ #
    ma20 = close.rolling(20).mean()
    ma40 = close.rolling(40).mean()

    latest_close = close.iloc[-1]
    latest_ma20 = ma20.iloc[-1]
    latest_ma40 = ma40.iloc[-1]

    above_20 = (latest_close > latest_ma20).sum()
    above_40 = (latest_close > latest_ma40).sum()

    valid_20 = latest_ma20.notna().sum()
    valid_40 = latest_ma40.notna().sum()

    pct_above_20 = round(float(above_20) / max(valid_20, 1) * 100, 2)
    pct_above_40 = round(float(above_40) / max(valid_40, 1) * 100, 2)

    # ------------------------------------------------------------------ #
    # New 52-week highs and lows
    # ------------------------------------------------------------------ #
    # Use the last 52 weekly bars as the 52-week window
    window_52 = close.iloc[-52:] if len(close) >= 52 else close

    high_52 = window_52.max()
    low_52 = window_52.min()

    # A stock is at a new high if its latest close equals (≈) its 52w high
    tolerance = 0.005  # 0.5% tolerance to account for rounding
    at_high = ((latest_close >= high_52 * (1 - tolerance)) & latest_close.notna()).sum()
    at_low = ((latest_close <= low_52 * (1 + tolerance)) & latest_close.notna()).sum()
    net_new_highs = int(at_high - at_low)

    # ------------------------------------------------------------------ #
    # A/D Trend: 4-week change in pct_above_20
    # ------------------------------------------------------------------ #
    if len(close) >= 24:  # need at least 24 weeks for MA20 + 4-week lookback
        # pct above MA20 four weeks ago
        close_4w_ago = close.iloc[-5]   # index -5 = 4 bars before -1
        ma20_4w_ago = ma20.iloc[-5]
        valid_4w = ma20_4w_ago.notna().sum()
        above_20_4w = (close_4w_ago > ma20_4w_ago).sum()
        pct_above_20_4w = float(above_20_4w) / max(valid_4w, 1) * 100
        ad_trend = round(pct_above_20 - pct_above_20_4w, 2)
    else:
        ad_trend = 0.0
        errors.append("Insufficient history for A/D trend (< 24 weeks).")

    # ------------------------------------------------------------------ #
    # Health Score (0-100)
    # ------------------------------------------------------------------ #
    score = 0

    # Component 1: % above 20wk MA (40pts max)
    if pct_above_20 > 70:
        score += 40
    elif pct_above_20 >= 50:
        score += 25
    elif pct_above_20 >= 30:
        score += 10
    # else 0

    # Component 2: % above 40wk MA (30pts max)
    if pct_above_40 > 60:
        score += 30
    elif pct_above_40 >= 40:
        score += 20
    elif pct_above_40 >= 20:
        score += 10
    # else 0

    # Component 3: Net new highs (20pts max)
    if net_new_highs > 50:
        score += 20
    elif net_new_highs >= 0:
        score += 10
    # else 0

    # Component 4: A/D trend (10pts max)
    if ad_trend > 5:
        score += 10
    elif ad_trend >= 0:
        score += 5
    # else 0

    health_score = int(score)

    # ------------------------------------------------------------------ #
    # Health Label
    # ------------------------------------------------------------------ #
    if health_score >= 80:
        health_label = "BROAD_BULL"
    elif health_score >= 60:
        health_label = "HEALTHY"
    elif health_score >= 40:
        health_label = "MIXED"
    elif health_score >= 20:
        health_label = "WEAKENING"
    else:
        health_label = "BEAR_MARKET"

    health_color = _HEALTH_COLORS.get(health_label, "var(--color-neutral)")

    # ------------------------------------------------------------------ #
    # Interpretation (data-driven)
    # ------------------------------------------------------------------ #
    trend_word = "improving" if ad_trend > 0 else ("flat" if ad_trend == 0 else "deteriorating")
    interp = (
        f"{pct_above_20:.1f}% of S&P 500 stocks are above their 20-week MA and "
        f"{pct_above_40:.1f}% are above their 40-week MA. "
        f"Net new 52-week highs: {net_new_highs:+d}. "
        f"Breadth trend over 4 weeks is {trend_word} ({ad_trend:+.1f} pp). "
        f"Market breadth is classified as {health_label} (score {health_score}/100). "
    )

    if health_label == "BROAD_BULL":
        interp += (
            "Broad participation confirms the trend — most stocks are rising "
            "together. Technical breakouts have a high probability of follow-through."
        )
    elif health_label == "HEALTHY":
        interp += (
            "The majority of stocks are trending above key MAs. "
            "The environment supports trend-following setups."
        )
    elif health_label == "MIXED":
        interp += (
            "Participation is split. Be selective: favor stocks in strong sectors "
            "and avoid chasing laggards. Index gains may mask individual-stock weakness."
        )
    elif health_label == "WEAKENING":
        interp += (
            "Most stocks are below key moving averages. Reduce position size "
            "and increase selectivity. Many technical setups will fail."
        )
    else:  # BEAR_MARKET
        interp += (
            "Extreme weakness: the vast majority of stocks are in downtrends. "
            "Defensive posture recommended. Only the highest-conviction entries "
            "in the strongest sectors should be considered."
        )

    return {
        "pct_above_20wk": pct_above_20,
        "pct_above_40wk": pct_above_40,
        "net_new_highs": net_new_highs,
        "ad_trend": ad_trend,
        "health_score": health_score,
        "health_label": health_label,
        "health_color": health_color,
        "stocks_analyzed": n_tickers,
        "explanation": _EXPLANATION,
        "interpretation": interp,
        "errors": errors,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _empty_result(reason: str) -> dict[str, Any]:
    """Return a safe fallback breadth dict when data is unavailable."""
    return {
        "pct_above_20wk": None,
        "pct_above_40wk": None,
        "net_new_highs": None,
        "ad_trend": None,
        "health_score": None,
        "health_label": "UNKNOWN",
        "health_color": "var(--color-neutral)",
        "stocks_analyzed": 0,
        "explanation": _EXPLANATION,
        "interpretation": f"Breadth data unavailable: {reason}",
        "errors": [reason],
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_market_breadth(use_cache: bool = True) -> dict[str, Any]:
    """
    Compute S&P 500 market breadth metrics.

    Parameters
    ----------
    use_cache : bool
        When True (default), reads from a 24-hour disk cache at
        /tmp/breadth_cache.pkl so that repeated calls within the same day
        do not re-download 500 tickers.  Pass False to force a fresh fetch.

    Returns
    -------
    dict with keys:
        pct_above_20wk   float  — % of S&P 500 stocks above their 20-week MA
        pct_above_40wk   float  — % above their 40-week MA
        net_new_highs    int    — count of new 52-week highs minus new lows
        ad_trend         float  — 4-week change in pct_above_20 (percentage points)
        health_score     int    — 0-100 composite breadth health score
        health_label     str    — 'BROAD_BULL' / 'HEALTHY' / 'MIXED' /
                                  'WEAKENING' / 'BEAR_MARKET'
        health_color     str    — CSS variable string
        stocks_analyzed  int    — number of tickers with valid price data
        explanation      str    — educational context
        interpretation   str    — data-driven current-state summary
        errors           list   — non-fatal data issues encountered
        last_updated     str    — timestamp of computation
    """
    # ---- Cache check -------------------------------------------------------
    if use_cache and _is_cache_valid():
        cached = _read_cache()
        if cached is not None:
            return cached

    # ---- Fetch tickers -----------------------------------------------------
    tickers = _get_sp500_tickers()
    if not tickers:
        return _empty_result("Could not retrieve S&P 500 ticker list.")

    # ---- Batch download weekly closes --------------------------------------
    print(f"[breadth] Downloading weekly data for {len(tickers)} S&P 500 tickers...")

    close: pd.DataFrame | None = None
    download_errors: list[str] = []

    try:
        raw = yf.download(
            tickers,
            period="1y",
            interval="1wk",
            progress=False,
            auto_adjust=True,
        )
        # yfinance >=0.2 returns MultiIndex columns when multiple tickers
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"].copy()
        else:
            # Single-ticker edge case (shouldn't happen here but be safe)
            close = raw[["Close"]].copy() if "Close" in raw.columns else raw.copy()

        # Drop all-NaN columns (tickers that returned no data)
        close = close.dropna(axis=1, how="all")

        if close.empty:
            return _empty_result("yfinance returned empty data for S&P 500 tickers.")

    except Exception as exc:
        return _empty_result(f"yfinance batch download failed: {exc}")

    if len(close) < 20:
        return _empty_result(
            f"Insufficient weekly bars ({len(close)}); need at least 20."
        )

    # ---- Compute metrics ---------------------------------------------------
    result = _calculate_breadth_from_prices(close)
    result["errors"] = download_errors + result.get("errors", [])

    # ---- Persist to cache --------------------------------------------------
    if use_cache:
        _write_cache(result)

    return result
