"""
Volume Profile calculations from daily OHLCV data.

Volume Profile distributes each day's volume across the day's price range
(high to low) proportionally, then aggregates across all days to show where
the most volume transacted at each price level. This reveals:
  - Point of Control (POC): price of maximum institutional interest
  - Value Area (VAH/VAL): 70% of all volume — the institutional 'fair value' zone
  - VWAP from period start and anchored VWAP from 52-week low

All functions return a dict with 'explanation' and 'interpretation' keys so
callers can surface plain-English teaching alongside the raw numbers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXPLANATION = (
    "Volume Profile shows how much volume traded at each price level over a given "
    "period. The Point of Control (POC) is the price where the most volume traded — "
    "this is where institutions have the most money concentrated, and price tends to "
    "return to this level repeatedly. The Value Area is the price range containing "
    "70% of all volume — similar to one standard deviation — and acts as a fair-value "
    "zone. Entering near the POC or Value Area Low gives you a high-probability "
    "location with institutional backing."
)

_DEFAULT: Dict[str, Any] = {
    "poc_price": None,
    "poc_distance_pct": None,
    "value_area_high": None,
    "value_area_low": None,
    "position": "UNKNOWN",
    "vwap_period": None,
    "avwap_52wk_low": None,
    "volume_profile_data": [],
    "explanation": _EXPLANATION,
    "interpretation": (
        "Volume profile data could not be computed. "
        "Insufficient price history or data fetch failure."
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _download_ohlcv(ticker: str, period: str) -> Optional[pd.DataFrame]:
    """Download daily OHLCV; normalize column names to simple strings."""
    try:
        df = yf.download(
            ticker,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return None
        # Flatten MultiIndex columns produced by yfinance for single-ticker download
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        else:
            df.columns = [str(c) for c in df.columns]
        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        if len(df) < 10:
            return None
        return df
    except Exception:
        return None


def _build_volume_profile(
    df: pd.DataFrame, bins: int
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Distribute each day's volume uniformly across the day's high-low range,
    then sum across all days to produce a volume-at-price histogram.

    Args:
        df: OHLCV DataFrame with columns Open, High, Low, Close, Volume.
        bins: Number of price levels (buckets).

    Returns:
        (price_levels, volume_at_price) — both length `bins` numpy arrays.
        price_levels is the midpoint of each bucket.
    """
    period_low = float(df["Low"].min())
    period_high = float(df["High"].max())

    if period_high <= period_low:
        return np.array([]), np.array([])

    # Create bin edges; midpoints will be used as representative prices
    bin_edges = np.linspace(period_low, period_high, bins + 1)
    bin_midpoints = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    bucket_width = bin_edges[1] - bin_edges[0]

    volume_at_price = np.zeros(bins)

    for _, row in df.iterrows():
        day_low = float(row["Low"])
        day_high = float(row["High"])
        day_vol = float(row["Volume"])

        if day_vol <= 0 or day_high <= day_low:
            # Still credit the volume at the close price
            close_idx = int(
                np.clip(
                    (float(row["Close"]) - period_low) / (period_high - period_low) * bins,
                    0,
                    bins - 1,
                )
            )
            volume_at_price[close_idx] += day_vol
            continue

        # Find which bins overlap with [day_low, day_high]
        first_bin = int(
            max(0, np.floor((day_low - period_low) / bucket_width))
        )
        last_bin = int(
            min(bins - 1, np.floor((day_high - period_low) / bucket_width))
        )

        active_bins = last_bin - first_bin + 1
        if active_bins <= 0:
            active_bins = 1
            last_bin = first_bin

        vol_per_bin = day_vol / active_bins
        volume_at_price[first_bin : last_bin + 1] += vol_per_bin

    return bin_midpoints, volume_at_price


def _calculate_value_area(
    price_levels: np.ndarray,
    volume_at_price: np.ndarray,
    target_pct: float = 0.70,
) -> Tuple[float, float, float]:
    """
    Calculate Point of Control and Value Area.

    The Value Area is built by iteratively adding the next highest-volume
    bin (above or below POC) until 70% of total volume is enclosed.

    Returns:
        (poc_price, value_area_low, value_area_high)
    """
    total_volume = volume_at_price.sum()
    if total_volume == 0:
        mid = float(price_levels[len(price_levels) // 2])
        return mid, mid, mid

    poc_idx = int(np.argmax(volume_at_price))
    poc_price = float(price_levels[poc_idx])

    target_volume = total_volume * target_pct
    accumulated = float(volume_at_price[poc_idx])

    va_low_idx = poc_idx
    va_high_idx = poc_idx

    while accumulated < target_volume:
        # Candidate bins: one step up and one step down
        up_idx = va_high_idx + 1
        down_idx = va_low_idx - 1

        up_vol = float(volume_at_price[up_idx]) if up_idx < len(volume_at_price) else 0.0
        down_vol = float(volume_at_price[down_idx]) if down_idx >= 0 else 0.0

        if up_vol == 0 and down_vol == 0:
            break  # covered all bins

        if up_vol >= down_vol:
            va_high_idx = up_idx
            accumulated += up_vol
        else:
            va_low_idx = down_idx
            accumulated += down_vol

    return (
        poc_price,
        float(price_levels[va_low_idx]),
        float(price_levels[va_high_idx]),
    )


def _calculate_period_vwap(df: pd.DataFrame) -> Optional[float]:
    """Cumulative VWAP from the first bar of the period."""
    try:
        typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
        vol = df["Volume"]
        cum_tpv = (typical * vol).cumsum()
        cum_vol = vol.cumsum()
        vwap_series = cum_tpv / cum_vol
        return float(vwap_series.iloc[-1])
    except Exception:
        return None


def _calculate_avwap_from_date(
    df: pd.DataFrame, anchor_date: pd.Timestamp
) -> Optional[float]:
    """
    Anchored VWAP starting from anchor_date.
    Returns None if anchor_date is not in the DataFrame index.
    """
    try:
        # Locate the anchor date or the nearest date after it
        idx_after = df.index[df.index >= anchor_date]
        if idx_after.empty:
            return None
        start = idx_after[0]
        sub = df.loc[start:]
        if sub.empty:
            return None
        typical = (sub["High"] + sub["Low"] + sub["Close"]) / 3.0
        vol = sub["Volume"]
        cum_tpv = (typical * vol).cumsum()
        cum_vol = vol.cumsum()
        vwap_series = cum_tpv / cum_vol
        return float(vwap_series.iloc[-1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_volume_profile(
    ticker: str, period: str = "6mo", bins: int = 50
) -> dict:
    """
    Build a volume profile for the given ticker over the specified period.

    Uses daily OHLCV data. Each day's volume is distributed proportionally
    across the day's high-low range and accumulated into price buckets.

    Args:
        ticker: Stock symbol, e.g. 'AAPL'.
        period: yfinance period string (default '6mo'). Longer periods give
                more statistically significant profiles. '1y' recommended for
                mature uptrends; '6mo' for recent-bias analysis.
        bins:   Number of price levels in the histogram (default 50).
                More bins = higher resolution; fewer = clearer levels.

    Returns:
        dict with keys: poc_price, poc_distance_pct, value_area_high,
        value_area_low, position, vwap_period, avwap_52wk_low,
        volume_profile_data, explanation, interpretation.
    """
    ticker = ticker.upper().strip()

    # -----------------------------------------------------------------------
    # Download data — use 1y for the profile, extend to 13mo to cover
    # the 52-week low anchor even when period='6mo'.
    # -----------------------------------------------------------------------
    df = _download_ohlcv(ticker, period)
    if df is None:
        return {**_DEFAULT, "ticker": ticker}

    df_1y = _download_ohlcv(ticker, "13mo")
    df_for_anchor = df_1y if df_1y is not None else df

    current_price = float(df["Close"].iloc[-1])

    # -----------------------------------------------------------------------
    # Build volume profile over the requested period
    # -----------------------------------------------------------------------
    price_levels, volume_at_price = _build_volume_profile(df, bins)

    if price_levels.size == 0:
        return {**_DEFAULT, "ticker": ticker}

    poc_price, val, vah = _calculate_value_area(price_levels, volume_at_price)

    poc_distance_pct = round((current_price / poc_price - 1) * 100, 2) if poc_price else None

    # Position relative to value area
    if current_price > vah:
        position = "ABOVE_VALUE_AREA"
    elif current_price < val:
        position = "BELOW_VALUE_AREA"
    else:
        position = "IN_VALUE_AREA"

    # -----------------------------------------------------------------------
    # VWAP (cumulative from first bar of period)
    # -----------------------------------------------------------------------
    vwap_period = _calculate_period_vwap(df)

    # -----------------------------------------------------------------------
    # Anchored VWAP from 52-week low
    # -----------------------------------------------------------------------
    avwap_52wk_low: Optional[float] = None
    try:
        lows = df_for_anchor["Low"].dropna()
        if len(lows) >= 2:
            low_52wk_date = lows.idxmin()
            avwap_52wk_low = _calculate_avwap_from_date(df_for_anchor, low_52wk_date)
    except Exception:
        pass

    # -----------------------------------------------------------------------
    # Top 10 volume levels for chart data
    # -----------------------------------------------------------------------
    profile_pairs = sorted(
        zip(price_levels.tolist(), volume_at_price.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )
    volume_profile_data = [
        {"price": round(p, 2), "volume": round(v, 0)}
        for p, v in profile_pairs[:10]
    ]

    # -----------------------------------------------------------------------
    # Dynamic interpretation
    # -----------------------------------------------------------------------
    poc_str = f"${poc_price:.2f}" if poc_price else "N/A"
    val_str = f"${val:.2f}" if val else "N/A"
    vah_str = f"${vah:.2f}" if vah else "N/A"
    vwap_str = f"${vwap_period:.2f}" if vwap_period else "N/A"
    avwap_str = f"${avwap_52wk_low:.2f}" if avwap_52wk_low else "N/A"

    if position == "ABOVE_VALUE_AREA":
        interpretation = (
            f"Price is above the Value Area at ${current_price:.2f} — extended into "
            f"premium territory above {vah_str}. Institutions accumulated most of their "
            f"position at lower prices; the POC at {poc_str} and VAL at {val_str} are "
            "first meaningful support on a pullback. "
            f"Period VWAP is {vwap_str}; anchored VWAP from 52-week low is {avwap_str}."
        )
    elif position == "IN_VALUE_AREA":
        interpretation = (
            f"Price at ${current_price:.2f} is trading within the Value Area "
            f"({val_str} – {vah_str}) — the institutional 'fair value' zone. "
            f"POC support at {poc_str} is the high-volume magnetic level; expect "
            f"rotations between VAL and VAH until a breakout resolves direction. "
            f"Period VWAP {vwap_str}; AVWAP from 52-week low {avwap_str}."
        )
    else:  # BELOW_VALUE_AREA
        interpretation = (
            f"Price at ${current_price:.2f} is below the Value Area — in discount "
            f"territory beneath {val_str}. The POC at {poc_str} is the first "
            "meaningful resistance if price recovers into the value zone. "
            "Below-value positioning suggests either a buying opportunity near "
            "institutional cost basis or the early stage of a trend breakdown — "
            f"volume context determines which. VWAP {vwap_str}; AVWAP from 52-week "
            f"low {avwap_str}."
        )

    return {
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "poc_price": round(poc_price, 2) if poc_price else None,
        "poc_distance_pct": poc_distance_pct,
        "value_area_high": round(vah, 2) if vah else None,
        "value_area_low": round(val, 2) if val else None,
        "position": position,
        "vwap_period": round(vwap_period, 2) if vwap_period else None,
        "avwap_52wk_low": round(avwap_52wk_low, 2) if avwap_52wk_low else None,
        "volume_profile_data": volume_profile_data,
        "explanation": _EXPLANATION,
        "interpretation": interpretation,
    }
