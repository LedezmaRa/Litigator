"""
Earnings calendar and binary event risk assessment module.

Earnings events are the single largest source of overnight gap risk for any
position.  This module surfaces three things:

  1. When is the next earnings report?          (days_to_earnings)
  2. How much is the options market pricing in? (implied_move_pct)
  3. Has this stock historically surprised?     (eps_surprise_avg)

All three feed the risk_level classification so the caller can scale position
size and set appropriate expectations before entering a trade.
"""
from __future__ import annotations

import threading
from datetime import datetime, date
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

_yf_lock = threading.Lock()

_EXPLANATION = (
    "Earnings events are binary \u2014 the stock will gap significantly up or down "
    "regardless of your technical analysis. Knowing when the next report is lets you "
    "size your position appropriately and avoid accidental exposure to a catalyst "
    "you haven't evaluated."
)

# Risk level thresholds (days to earnings)
_HIGH_THRESHOLD   = 14   # < 14 days = HIGH
_MEDIUM_THRESHOLD = 30   # 14–30 days = MEDIUM
                         # > 30 days  = LOW

# CSS color variables matching the framework palette
_RISK_COLORS = {
    "HIGH":   "var(--accent-poor)",
    "MEDIUM": "var(--accent-marginal)",
    "LOW":    "var(--accent-acceptable)",
    "CLEAR":  "var(--accent-optimal)",
}

_RISK_LABELS = {
    "HIGH":   "Earnings Imminent",
    "MEDIUM": "Earnings Approaching",
    "LOW":    "Earnings Distant",
    "CLEAR":  "No Upcoming Earnings",
}


def _default_result(ticker: str, error: Optional[str] = None) -> dict:
    """Return a safe all-None result when data cannot be fetched."""
    return {
        "next_earnings_date":  None,
        "days_to_earnings":    None,
        "risk_level":          "CLEAR",
        "risk_color":          _RISK_COLORS["CLEAR"],
        "risk_label":          _RISK_LABELS["CLEAR"],
        "implied_move_pct":    None,
        "eps_surprise_avg":    None,
        "last_eps_actual":     None,
        "last_eps_estimate":   None,
        "explanation":         _EXPLANATION,
        "interpretation":      (
            f"Earnings data for {ticker} could not be retrieved. "
            "Treat as unknown risk until confirmed."
            + (f" ({error})" if error else "")
        ),
        "error": error,
    }


def _parse_next_earnings_date(calendar) -> Optional[date]:
    """
    Extract the next earnings date from yfinance calendar output.

    yfinance returns calendar as a dict (new API) or a DataFrame (legacy).
    We handle both shapes gracefully.
    """
    if calendar is None:
        return None

    try:
        # New API shape: dict with 'Earnings Date' key
        if isinstance(calendar, dict):
            raw = calendar.get("Earnings Date")
            if raw is None:
                return None
            # Could be a list of date-like objects or a single value
            if isinstance(raw, (list, tuple)):
                candidates = [r for r in raw if r is not None]
                raw = candidates[0] if candidates else None
            if raw is None:
                return None
            if isinstance(raw, (datetime, pd.Timestamp)):
                return raw.date()
            if isinstance(raw, date):
                return raw
            # Try parsing a string
            return pd.to_datetime(str(raw)).date()

        # Legacy API shape: DataFrame with 'Earnings Date' column or index
        if isinstance(calendar, pd.DataFrame):
            if "Earnings Date" in calendar.columns:
                val = calendar["Earnings Date"].dropna().iloc[0]
            elif "Earnings Date" in calendar.index:
                val = calendar.loc["Earnings Date"]
            else:
                return None
            return pd.to_datetime(val).date()

    except Exception:
        pass

    return None


def _classify_risk(days: Optional[int]) -> str:
    if days is None:
        return "CLEAR"
    if days < _HIGH_THRESHOLD:
        return "HIGH"
    if days < _MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def _build_interpretation(
    ticker: str,
    days: Optional[int],
    risk_level: str,
    implied_move_pct: Optional[float],
    eps_surprise_avg: Optional[float],
) -> str:
    """Build a dynamic, context-aware interpretation string."""
    implied_str = (
        f"With an implied move of {implied_move_pct:.1f}%, "
        if implied_move_pct is not None
        else "Implied move data unavailable. "
    )
    surprise_str = (
        f"The stock has averaged a {eps_surprise_avg:+.1f}% EPS surprise over the last 4 quarters."
        if eps_surprise_avg is not None
        else ""
    )

    if risk_level == "HIGH":
        return (
            f"\u26a0\ufe0f Earnings in {days} days. {implied_str}"
            "This is a high-risk period. Consider waiting for the event to pass "
            "or sizing down to 50% of normal. "
            + surprise_str
        )
    if risk_level == "MEDIUM":
        return (
            f"Earnings in {days} days \u2014 on the radar but not immediate. "
            "Begin preparing your earnings protocol: know your size, know your exit. "
            + surprise_str
        )
    if risk_level == "LOW":
        return (
            f"Next earnings is {days}+ days away. Clean runway for a technical entry to develop. "
            + surprise_str
        )
    # CLEAR
    return (
        f"No confirmed upcoming earnings date for {ticker}. "
        "Verify against primary sources before entering a position. "
        + surprise_str
    )


def _get_current_price(ticker_obj: yf.Ticker) -> Optional[float]:
    """Fetch current price with multiple fallback paths."""
    try:
        hist = ticker_obj.history(period="2d", auto_adjust=True)
        if hist is not None and not hist.empty and "Close" in hist.columns:
            return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        pass

    try:
        info = ticker_obj.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price:
            return float(price)
    except Exception:
        pass

    return None


def _compute_implied_move(
    ticker_obj: yf.Ticker,
    current_price: float,
) -> Optional[float]:
    """
    Estimate the expected earnings move from the ATM straddle.

    Method:
      1. Get available option expirations.
      2. Select the nearest expiration that is at least 7 calendar days out
         (avoids same-week weeklies which have minimal time value).
      3. Find the ATM strike (strike closest to current price).
      4. Implied move (%) = (ATM call ask + ATM put ask) / current price × 100

    Returns implied move as a percentage (e.g., 8.5 = 8.5%), or None.
    """
    if current_price is None or current_price <= 0:
        return None

    try:
        expirations = ticker_obj.options
        if not expirations:
            return None

        today = date.today()
        target_exp = None
        for exp_str in expirations:
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                if (exp_date - today).days >= 7:
                    target_exp = exp_str
                    break
            except ValueError:
                continue

        if target_exp is None:
            return None

        with _yf_lock:
            chain = ticker_obj.option_chain(target_exp)

        calls = chain.calls
        puts  = chain.puts

        if calls is None or puts is None or calls.empty or puts.empty:
            return None

        # Normalise column names to lowercase
        calls = calls.copy()
        puts  = puts.copy()
        calls.columns = [c.lower() for c in calls.columns]
        puts.columns  = [c.lower() for c in puts.columns]

        # Find the ATM strike — closest to current price
        if "strike" not in calls.columns:
            return None

        atm_strike = calls.loc[
            (calls["strike"] - current_price).abs().idxmin(), "strike"
        ]

        call_row = calls[calls["strike"] == atm_strike]
        put_row  = puts[puts["strike"] == atm_strike]

        if call_row.empty or put_row.empty:
            return None

        # Prefer mid-point (bid+ask)/2; fall back to lastPrice
        def _mid(row: pd.DataFrame, col_ask: str = "ask", col_bid: str = "bid",
                 col_last: str = "lastprice") -> Optional[float]:
            ask = row[col_ask].iloc[0] if col_ask in row.columns else None
            bid = row[col_bid].iloc[0] if col_bid in row.columns else None
            last = row[col_last].iloc[0] if col_last in row.columns else None

            if ask and bid and ask > 0 and bid >= 0:
                return (ask + bid) / 2.0
            if last and last > 0:
                return float(last)
            return None

        call_price = _mid(call_row)
        put_price  = _mid(put_row)

        if call_price is None or put_price is None:
            return None

        implied_move = (call_price + put_price) / current_price * 100.0
        return round(implied_move, 2) if implied_move > 0 else None

    except Exception:
        return None


def _compute_eps_surprise(ticker_obj: yf.Ticker) -> Tuple[
    Optional[float], Optional[float], Optional[float]
]:
    """
    Compute average EPS surprise % from the last 4 earnings reports.

    yfinance exposes earnings history via .earnings_history (DataFrame with
    columns: 'epsEstimate', 'epsActual', 'surprisePercent').

    Returns:
        (eps_surprise_avg, last_eps_actual, last_eps_estimate)
        All may be None if data is unavailable.
    """
    try:
        hist = ticker_obj.earnings_history
        if hist is None or (hasattr(hist, "empty") and hist.empty):
            return None, None, None

        # Normalise column names
        hist = hist.copy()
        hist.columns = [c.lower().replace(" ", "_") for c in hist.columns]

        # Look for recognised column shapes
        actual_col    = next((c for c in hist.columns if "actual" in c), None)
        estimate_col  = next((c for c in hist.columns if "estimate" in c), None)
        surprise_col  = next((c for c in hist.columns if "surprise" in c and "percent" in c), None)

        last_actual   = None
        last_estimate = None

        if actual_col:
            actuals = hist[actual_col].dropna()
            if not actuals.empty:
                last_actual = float(actuals.iloc[0])

        if estimate_col:
            estimates = hist[estimate_col].dropna()
            if not estimates.empty:
                last_estimate = float(estimates.iloc[0])

        # Compute average surprise %
        if surprise_col:
            surprises = hist[surprise_col].dropna().head(4)
            if not surprises.empty:
                avg = float(surprises.mean())
                return round(avg, 2), last_actual, last_estimate

        # Fall back: compute from actual / estimate if surprise column absent
        if actual_col and estimate_col:
            combined = hist[[actual_col, estimate_col]].dropna().head(4)
            if not combined.empty:
                actual_vals   = combined[actual_col]
                estimate_vals = combined[estimate_col]
                # Avoid division by zero
                with_est = estimate_vals[estimate_vals != 0]
                if not with_est.empty:
                    valid_idx   = with_est.index
                    pct_surprises = (
                        (actual_vals.loc[valid_idx] - estimate_vals.loc[valid_idx])
                        / estimate_vals.loc[valid_idx].abs()
                    ) * 100
                    avg = float(pct_surprises.mean())
                    return round(avg, 2), last_actual, last_estimate

    except Exception:
        pass

    return None, None, None


def fetch_earnings_data(ticker: str) -> dict:
    """
    Fetch earnings calendar and binary event risk data for a ticker.

    Uses yfinance to pull:
      - Next earnings date from .calendar
      - Historical EPS surprise from .earnings_history
      - Implied move from nearest options expiration ATM straddle

    Args:
        ticker: Stock symbol (e.g., 'AAPL').

    Returns:
        dict with keys:
          next_earnings_date (date str 'YYYY-MM-DD' or None)
          days_to_earnings   (int or None)
          risk_level         ('HIGH' / 'MEDIUM' / 'LOW' / 'CLEAR')
          risk_color         (CSS variable string)
          risk_label         (human-readable label)
          implied_move_pct   (float or None) — ATM straddle / price * 100
          eps_surprise_avg   (float or None) — avg % surprise last 4 quarters
          last_eps_actual    (float or None)
          last_eps_estimate  (float or None)
          explanation        (str) — educational tooltip text
          interpretation     (str) — dynamic reading for this ticker
          error              (str or None)
    """
    ticker = ticker.upper().strip()

    try:
        with _yf_lock:
            yf_ticker = yf.Ticker(ticker)

        # --- 1. Current price (needed for implied move) ---
        current_price = _get_current_price(yf_ticker)

        # --- 2. Next earnings date ---
        next_date: Optional[date] = None
        try:
            calendar = yf_ticker.calendar
            next_date = _parse_next_earnings_date(calendar)
        except Exception:
            pass

        # Calculate days to earnings
        days_to_earnings: Optional[int] = None
        if next_date is not None:
            today = date.today()
            delta = (next_date - today).days
            # Negative means date is in the past — treat as no upcoming date
            days_to_earnings = delta if delta >= 0 else None
            if days_to_earnings is None:
                next_date = None

        # --- 3. Risk classification ---
        risk_level = _classify_risk(days_to_earnings)

        # --- 4. Implied move from options ---
        implied_move_pct: Optional[float] = None
        if current_price is not None:
            implied_move_pct = _compute_implied_move(yf_ticker, current_price)

        # --- 5. EPS surprise history ---
        eps_surprise_avg, last_eps_actual, last_eps_estimate = _compute_eps_surprise(yf_ticker)

        # --- 6. Build interpretation ---
        interpretation = _build_interpretation(
            ticker=ticker,
            days=days_to_earnings,
            risk_level=risk_level,
            implied_move_pct=implied_move_pct,
            eps_surprise_avg=eps_surprise_avg,
        )

        return {
            "next_earnings_date":  next_date.isoformat() if next_date else None,
            "days_to_earnings":    days_to_earnings,
            "risk_level":          risk_level,
            "risk_color":          _RISK_COLORS[risk_level],
            "risk_label":          _RISK_LABELS[risk_level],
            "implied_move_pct":    implied_move_pct,
            "eps_surprise_avg":    eps_surprise_avg,
            "last_eps_actual":     last_eps_actual,
            "last_eps_estimate":   last_eps_estimate,
            "explanation":         _EXPLANATION,
            "interpretation":      interpretation,
            "error":               None,
        }

    except Exception as exc:
        return _default_result(ticker, str(exc))
