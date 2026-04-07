"""
Multi-source market sentiment aggregator.

Combines four independently sourced signals into a single composite reading:
  1. CBOE Equity Put/Call Ratio  — options market fear gauge
  2. VIX + VIX3M term structure  — implied volatility regime
  3. Fear & Greed proxy          — composite of normalized sub-indicators
  4. Risk-appetite proxy         — XLP/XLY sector-rotation indicator

All functions return a dict with 'explanation' and 'interpretation' keys so
callers can surface plain-English teaching alongside the raw numbers.
"""

from __future__ import annotations

import io
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXPLANATION = (
    "Sentiment indicators measure the collective emotional state of market "
    "participants. When fear is extreme (VIX >30, high put/call ratio), it often "
    "marks bottoms because everyone who wants to sell has already sold. When greed "
    "is extreme (VIX <12, low put/call, everything extended), it often marks tops "
    "because there are no buyers left. The contrarian insight: be greedy when others "
    "are fearful, fearful when others are greedy."
)

_CBOE_CSV_URL = (
    "https://cdn.cboe.com/api/global/us_indices/daily_prices/EQUITY_PC_RATIO_HIST.csv"
)

_DEFAULT: Dict[str, Any] = {
    "equity_pc_ratio": None,
    "pc_signal": "UNKNOWN",
    "vix_value": None,
    "vix_label": "UNKNOWN",
    "vix3m_value": None,
    "vix_contango_ratio": None,
    "vix_structure": "UNKNOWN",
    "fear_greed_score": 50,
    "fear_greed_label": "NEUTRAL",
    "risk_appetite_ratio": None,
    "overall_sentiment": "NEUTRAL",
    "overall_color": "var(--color-neutral, #888888)",
    "explanation": _EXPLANATION,
    "interpretation": (
        "Sentiment data could not be retrieved at this time. "
        "Default neutral reading applied."
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_equity_pc_ratio() -> Optional[float]:
    """
    Fetch the most recent CBOE equity-only put/call ratio.

    Primary: CBOE historical CSV hosted on their CDN.
    Fallback: SPY options chain via yfinance (crude proxy).
    """
    # -- Primary: CBOE CDN CSV -------------------------------------------
    try:
        resp = requests.get(
            _CBOE_CSV_URL,
            headers={"User-Agent": "Research Framework research@example.com"},
            timeout=15,
        )
        if resp.ok and len(resp.content) > 100:
            df = pd.read_csv(io.StringIO(resp.text), skiprows=0)
            # Column names vary; attempt common patterns
            date_col = None
            ratio_col = None
            for col in df.columns:
                lc = col.strip().lower()
                if "date" in lc:
                    date_col = col
                if "ratio" in lc or "p/c" in lc or "pc" in lc:
                    ratio_col = col
            if ratio_col is not None:
                df = df.dropna(subset=[ratio_col])
                val = float(df[ratio_col].iloc[-1])
                if 0.1 < val < 5.0:  # sanity range
                    return val
    except Exception:
        pass

    # -- Fallback: SPY options ratio via yfinance -------------------------
    try:
        spy = yf.Ticker("SPY")
        expiries = spy.options
        if not expiries:
            return None
        nearest = expiries[0]
        chain = spy.option_chain(nearest)
        put_vol = chain.puts["volume"].sum()
        call_vol = chain.calls["volume"].sum()
        if call_vol > 0:
            return float(put_vol / call_vol)
    except Exception:
        pass

    return None


def _fetch_vix_data() -> Dict[str, Optional[float]]:
    """
    Download current VIX and VIX3M values from yfinance.
    Returns dict with keys: vix, vix3m.
    """
    result: Dict[str, Optional[float]] = {"vix": None, "vix3m": None}
    try:
        raw = yf.download(
            ["^VIX", "^VIX3M"],
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            return result

        # yfinance multi-ticker returns MultiIndex columns (field, ticker)
        close = raw["Close"] if "Close" in raw.columns else raw.xs("Close", axis=1, level=0)

        if "^VIX" in close.columns:
            series = close["^VIX"].dropna()
            if not series.empty:
                result["vix"] = float(series.iloc[-1])

        if "^VIX3M" in close.columns:
            series = close["^VIX3M"].dropna()
            if not series.empty:
                result["vix3m"] = float(series.iloc[-1])
    except Exception:
        pass
    return result


def _fetch_spy_data(period: str = "9mo") -> Optional[pd.DataFrame]:
    """Download SPY daily OHLCV; return DataFrame or None."""
    try:
        df = yf.download(
            "SPY", period=period, interval="1d", progress=False, auto_adjust=True
        )
        if df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df
    except Exception:
        return None


def _fetch_sector_etfs() -> Dict[str, Optional[pd.DataFrame]]:
    """Download XLP and XLY daily data for the risk-appetite proxy."""
    result: Dict[str, Optional[pd.DataFrame]] = {"XLP": None, "XLY": None}
    for sym in ("XLP", "XLY"):
        try:
            df = yf.download(
                sym, period="6mo", interval="1d", progress=False, auto_adjust=True
            )
            if not df.empty:
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                result[sym] = df
        except Exception:
            pass
    return result


def _vix_label(vix: float) -> str:
    if vix < 15:
        return "CALM"
    if vix < 20:
        return "NORMAL"
    if vix < 30:
        return "ELEVATED"
    if vix <= 40:
        return "FEAR"
    return "PANIC"


def _pc_signal(ratio: float) -> str:
    if ratio > 0.8:
        return "FEARFUL"
    if ratio >= 0.6:
        return "NEUTRAL"
    return "COMPLACENT"


def _vix_structure(contango_ratio: float) -> str:
    if contango_ratio > 1.0:
        return "CONTANGO"
    if contango_ratio >= 0.95:
        return "FLAT"
    return "BACKWARDATION"


def _normalize_vix_to_score(vix: float) -> float:
    """
    Invert VIX to a 0-100 greed score.
    Low VIX -> high greed (100); High VIX -> high fear (0).
    Anchor points: VIX=10 -> 95, VIX=20 -> 50, VIX=40 -> 5.
    Uses linear interpolation between anchor bands.
    """
    if vix <= 10:
        return 95.0
    if vix <= 20:
        return 95.0 - (vix - 10) * 4.5  # 95 down to 50
    if vix <= 40:
        return 50.0 - (vix - 20) * 2.25  # 50 down to 5
    return max(0.0, 5.0 - (vix - 40) * 0.25)


def _spy_ma_score(spy_df: pd.DataFrame) -> Optional[float]:
    """
    Score based on SPY relative to its 125-day MA: 0-100.
    Well above MA = greed (high); well below = fear (low).
    """
    try:
        close = spy_df["Close"].dropna()
        if len(close) < 126:
            return None
        ma125 = close.rolling(125).mean().iloc[-1]
        current = close.iloc[-1]
        pct_diff = (current / ma125 - 1) * 100  # percent deviation
        # Map: -10% -> 10, 0% -> 50, +10% -> 90 (clipped)
        score = 50.0 + pct_diff * 4.0
        return float(max(0.0, min(100.0, score)))
    except Exception:
        return None


def _fear_greed_label(score: float) -> str:
    if score < 25:
        return "Extreme Fear"
    if score < 45:
        return "Fear"
    if score <= 55:
        return "Neutral"
    if score <= 75:
        return "Greed"
    return "Extreme Greed"


def _overall_sentiment_from_score(score: float) -> str:
    if score < 25:
        return "EXTREME_FEAR"
    if score < 45:
        return "FEAR"
    if score <= 55:
        return "NEUTRAL"
    if score <= 75:
        return "GREED"
    return "EXTREME_GREED"


def _overall_color(sentiment: str) -> str:
    colors = {
        "EXTREME_FEAR": "var(--color-bearish-strong, #c0392b)",
        "FEAR": "var(--color-bearish, #e74c3c)",
        "NEUTRAL": "var(--color-neutral, #f39c12)",
        "GREED": "var(--color-bullish, #27ae60)",
        "EXTREME_GREED": "var(--color-bullish-strong, #1e8449)",
    }
    return colors.get(sentiment, "var(--color-neutral, #888888)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_market_sentiment() -> dict:
    """
    Aggregate multi-source sentiment data into a single composite reading.

    Sources polled (all free, no API key required):
      1. CBOE equity put/call ratio CSV
      2. VIX + VIX3M via yfinance
      3. SPY vs 125-day MA greed component
      4. XLP/XLY sector rotation risk-appetite ratio

    Returns:
        dict with keys: equity_pc_ratio, pc_signal, vix_value, vix_label,
        vix3m_value, vix_contango_ratio, vix_structure, fear_greed_score,
        fear_greed_label, risk_appetite_ratio, overall_sentiment, overall_color,
        explanation, interpretation.
    """
    # -----------------------------------------------------------------------
    # 1. Put/Call ratio
    # -----------------------------------------------------------------------
    equity_pc_ratio = _fetch_equity_pc_ratio()
    pc_sig = _pc_signal(equity_pc_ratio) if equity_pc_ratio is not None else "UNKNOWN"

    # -----------------------------------------------------------------------
    # 2. VIX / VIX3M
    # -----------------------------------------------------------------------
    vix_data = _fetch_vix_data()
    vix_value = vix_data.get("vix")
    vix3m_value = vix_data.get("vix3m")

    vix_lbl = _vix_label(vix_value) if vix_value is not None else "UNKNOWN"

    contango_ratio: Optional[float] = None
    vix_struct = "UNKNOWN"
    if vix_value is not None and vix3m_value is not None and vix_value > 0:
        contango_ratio = round(vix3m_value / vix_value, 4)
        vix_struct = _vix_structure(contango_ratio)

    # -----------------------------------------------------------------------
    # 3. Fear & Greed composite
    # -----------------------------------------------------------------------
    score_components: list[float] = []

    if vix_value is not None:
        score_components.append(_normalize_vix_to_score(vix_value))

    spy_df = _fetch_spy_data()
    spy_score: Optional[float] = None
    if spy_df is not None:
        spy_score = _spy_ma_score(spy_df)
        if spy_score is not None:
            score_components.append(spy_score)

    # Put/call component: ratio 0.4 -> 90 (greed), 1.0 -> 10 (fear)
    pc_score: Optional[float] = None
    if equity_pc_ratio is not None:
        pc_score = float(max(0, min(100, 100 - (equity_pc_ratio - 0.4) / 0.8 * 100)))
        score_components.append(pc_score)

    fear_greed_score = round(float(np.mean(score_components)), 1) if score_components else 50.0
    fg_label = _fear_greed_label(fear_greed_score)

    # -----------------------------------------------------------------------
    # 4. Risk-appetite ratio (XLP/XLY)
    # -----------------------------------------------------------------------
    risk_appetite_ratio: Optional[float] = None
    ra_20d_change: Optional[float] = None

    sector_data = _fetch_sector_etfs()
    xlp_df = sector_data.get("XLP")
    xly_df = sector_data.get("XLY")

    if xlp_df is not None and xly_df is not None:
        try:
            xlp_close = xlp_df["Close"].dropna()
            xly_close = xly_df["Close"].dropna()
            # Align on common dates
            common_idx = xlp_close.index.intersection(xly_close.index)
            if len(common_idx) >= 21:
                xlp_aligned = xlp_close.loc[common_idx]
                xly_aligned = xly_close.loc[common_idx]
                ratio_series = xlp_aligned / xly_aligned
                risk_appetite_ratio = round(float(ratio_series.iloc[-1]), 4)
                ra_20d_change = round(
                    float(
                        (ratio_series.iloc[-1] / ratio_series.iloc[-21] - 1) * 100
                    ),
                    2,
                )
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Overall sentiment
    # -----------------------------------------------------------------------
    # Weight: VIX (40%), SPY MA (30%), put/call (20%), XLP/XLY (10%)
    weighted_components: list[tuple[float, float]] = []

    if vix_value is not None:
        weighted_components.append((_normalize_vix_to_score(vix_value), 0.40))
    if spy_score is not None:
        weighted_components.append((spy_score, 0.30))
    if pc_score is not None:
        weighted_components.append((pc_score, 0.20))

    # XLP/XLY: rising ratio (defensive) = fear; falling = greed
    if risk_appetite_ratio is not None and ra_20d_change is not None:
        # Invert: more defensive rotation -> lower greed score
        ra_score = float(max(0, min(100, 50 - ra_20d_change * 3)))
        weighted_components.append((ra_score, 0.10))

    if weighted_components:
        total_weight = sum(w for _, w in weighted_components)
        overall_score = sum(s * w for s, w in weighted_components) / total_weight
        overall_score = round(float(overall_score), 1)
    else:
        overall_score = fear_greed_score

    overall_sent = _overall_sentiment_from_score(overall_score)
    overall_col = _overall_color(overall_sent)

    # -----------------------------------------------------------------------
    # Dynamic interpretation
    # -----------------------------------------------------------------------
    vix_str = f"{vix_value:.1f}" if vix_value is not None else "N/A"
    pc_str = f"{equity_pc_ratio:.2f}" if equity_pc_ratio is not None else "N/A"

    if overall_sent == "EXTREME_FEAR":
        interpretation = (
            f"EXTREME FEAR — composite score {overall_score:.0f}/100. "
            f"VIX at {vix_str} ({vix_lbl.lower()}), equity put/call at {pc_str} "
            f"({pc_sig.lower()}). Historically, extreme fear readings have marked "
            "market bottoms within weeks. Contrarian risk/reward favors buyers "
            "with defined downside."
        )
    elif overall_sent == "FEAR":
        interpretation = (
            f"FEAR reading — composite score {overall_score:.0f}/100. "
            f"VIX at {vix_str} ({vix_lbl.lower()}), equity put/call at {pc_str}. "
            "Elevated fear but not at capitulation levels. Risk assets remain "
            "under pressure; high-quality setups offer better-than-average expected "
            "value as participants are positioned defensively."
        )
    elif overall_sent == "NEUTRAL":
        interpretation = (
            f"NEUTRAL sentiment — composite score {overall_score:.0f}/100. "
            f"VIX at {vix_str}, put/call ratio at {pc_str}. Markets are in a "
            "balanced state with no strong directional bias from sentiment. "
            "Price action and technical setups should drive positioning decisions."
        )
    elif overall_sent == "GREED":
        interpretation = (
            f"GREED reading — composite score {overall_score:.0f}/100. "
            f"VIX compressed to {vix_str}, put/call at {pc_str} ({pc_sig.lower()}). "
            "Elevated complacency warrants tighter stop placement. Avoid chasing "
            "extended breakouts; look for pullbacks to moving averages."
        )
    else:  # EXTREME_GREED
        interpretation = (
            f"EXTREME GREED — composite score {overall_score:.0f}/100. "
            f"VIX at a low {vix_str}, put/call at {pc_str} (complacent). "
            "This level of optimism has historically preceded mean-reversion events. "
            "Reduce leverage, trim extended winners, prioritize capital preservation."
        )

    return {
        "equity_pc_ratio": equity_pc_ratio,
        "pc_signal": pc_sig,
        "vix_value": vix_value,
        "vix_label": vix_lbl,
        "vix3m_value": vix3m_value,
        "vix_contango_ratio": contango_ratio,
        "vix_structure": vix_struct,
        "fear_greed_score": fear_greed_score,
        "fear_greed_label": fg_label,
        "risk_appetite_ratio": risk_appetite_ratio,
        "risk_appetite_20d_change_pct": ra_20d_change,
        "overall_sentiment": overall_sent,
        "overall_score": overall_score,
        "overall_color": overall_col,
        "explanation": _EXPLANATION,
        "interpretation": interpretation,
    }
