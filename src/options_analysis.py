"""
Options-based volatility and sentiment analysis module.

The options market is the most direct window into what professional traders
expect from a stock.  Three signals dominate:

  1. IV Rank (IVR) — is volatility cheap or expensive vs its own history?
     Buy options when IVR is low; sell/avoid when IVR is high.

  2. IV/HV Ratio  — is the options market pricing MORE movement than has
     actually occurred? >1.3 = options expensive; <0.8 = options cheap.

  3. Put/Call Ratio — are traders buying protection (bearish) or speculation
     (bullish)? P/C >1.2 = fear; <0.7 = complacency.

These three together define whether to use options as offense, defense,
or leave them alone entirely.
"""
from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

_yf_lock = threading.Lock()

_EXPLANATION = (
    "The options market prices in the expected range of price movement. "
    "IV Rank (IVR) shows where current volatility sits relative to its 52-week range "
    "\u2014 0 is the calmest it's been, 100 is the most fearful. "
    "The Put/Call Ratio measures whether traders are buying more protective puts "
    "(bearish) or speculative calls (bullish)."
)

# Thresholds
_IVR_HIGH   = 70
_IVR_LOW    = 30
_IV_HV_EXPENSIVE = 1.30
_IV_HV_CHEAP     = 0.80
_PC_FEARFUL      = 1.20
_PC_COMPLACENT   = 0.70

# Minimum days out for expiration selection
_MIN_DAYS_TO_EXPIRY = 7

# Lookback periods
_HV_SHORT_PERIOD  = 20    # days — recent realized vol
_HV_ANNUAL_PERIOD = 252   # days — for annualisation


def _default_result(ticker: str, error: Optional[str] = None) -> dict:
    """Return a safe all-None result when data cannot be fetched."""
    return {
        "iv_rank":          None,
        "iv_hv_ratio":      None,
        "put_call_ratio":   None,
        "implied_move_pct": None,
        "iv_label":         "N/A",
        "iv_signal":        "FAIR",
        "sentiment_label":  "Neutral",
        "explanation":      _EXPLANATION,
        "interpretation":   (
            f"Options data for {ticker} could not be retrieved. "
            "Verify ticker symbol and check market hours."
            + (f" ({error})" if error else "")
        ),
        "error": error,
    }


def _find_nearest_expiration(expirations: tuple, min_days: int = _MIN_DAYS_TO_EXPIRY) -> Optional[str]:
    """
    Select the nearest option expiration that is at least min_days away.

    Args:
        expirations: Tuple of expiration date strings from yf.Ticker.options.
        min_days:    Minimum calendar days required before expiry.

    Returns:
        Expiration date string (e.g., '2024-01-19') or None.
    """
    today = date.today()
    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            if (exp_date - today).days >= min_days:
                return exp_str
        except ValueError:
            continue
    return None


def _option_mid(row: pd.Series) -> Optional[float]:
    """
    Extract the mid-point price from an option row.

    Prefers (ask + bid) / 2 when both are positive; falls back to lastPrice.
    """
    try:
        ask  = float(row.get("ask",  0) or 0)
        bid  = float(row.get("bid",  0) or 0)
        last = float(row.get("lastPrice", 0) or 0)

        if ask > 0 and bid >= 0:
            return (ask + bid) / 2.0
        if last > 0:
            return last
    except Exception:
        pass
    return None


def _atm_strike(strikes: pd.Series, current_price: float) -> Optional[float]:
    """Return the strike closest to the current price."""
    try:
        idx = (strikes - current_price).abs().idxmin()
        return float(strikes.loc[idx])
    except Exception:
        return None


def _compute_current_price(ticker_obj: yf.Ticker) -> Optional[float]:
    """Fetch current market price with fallback paths."""
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


def _compute_historical_volatility(
    ticker_obj: yf.Ticker,
    period_days: int = _HV_SHORT_PERIOD,
) -> Optional[float]:
    """
    Compute annualised historical volatility using log returns.

    Uses 14 months of daily data to support both HV-20 and rolling HV
    calculations needed for IVR estimation.

    Args:
        ticker_obj: yfinance Ticker object.
        period_days: Rolling window for HV calculation (default 20).

    Returns:
        Annualised HV as a decimal (e.g., 0.30 = 30%) or None.
    """
    try:
        with _yf_lock:
            hist = yf.download(
                ticker_obj.ticker,
                period="14mo",
                interval="1d",
                progress=False,
                multi_level_index=False,
                auto_adjust=True,
            )

        if hist is None or hist.empty:
            return None

        hist.columns = [c.capitalize() for c in hist.columns]
        if "Close" not in hist.columns:
            return None

        closes = hist["Close"].dropna()
        if len(closes) < period_days + 5:
            return None

        log_returns = np.log(closes / closes.shift(1)).dropna()
        hv = float(log_returns.tail(period_days).std() * np.sqrt(_HV_ANNUAL_PERIOD))
        return hv if hv > 0 else None

    except Exception:
        return None


def _compute_iv_rank_and_implied_vol(
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    current_price: float,
    ticker_obj: yf.Ticker,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Estimate IV Rank (IVR) and current ATM IV using the options chain.

    IVR Methodology:
      We cannot retrieve historical daily IV from yfinance, so we use a
      proxy approach based on historical volatility percentiles:

        1. Download 14 months of daily closes.
        2. Compute a 20-day rolling historical volatility series.
        3. Extract the current ATM IV from the options chain.
        4. The 252-day range of the HV series serves as the min/max proxy
           for IV's 52-week range.
        5. IVR = (current_atm_iv - min_hv) / (max_hv - min_hv) × 100

      This is not identical to a true IV Rank but is the best available
      approximation without a paid data feed.

    Returns:
        (iv_rank, current_atm_iv, implied_move_pct) — all may be None.
    """
    if current_price <= 0:
        return None, None, None

    # --- ATM strike ---
    strike = _atm_strike(calls["strike"], current_price)
    if strike is None:
        return None, None, None

    call_row = calls[calls["strike"] == strike]
    put_row  = puts[puts["strike"] == strike]

    if call_row.empty or put_row.empty:
        return None, None, None

    # --- Implied move from ATM straddle ---
    call_price = _option_mid(call_row.iloc[0])
    put_price  = _option_mid(put_row.iloc[0])

    implied_move_pct: Optional[float] = None
    if call_price is not None and put_price is not None and current_price > 0:
        implied_move_pct = round((call_price + put_price) / current_price * 100.0, 2)
        if implied_move_pct <= 0:
            implied_move_pct = None

    # --- Current ATM IV ---
    # Prefer the call-side IV; put-side as fallback (both should be close)
    current_iv: Optional[float] = None
    iv_col = "impliedVolatility"
    if iv_col in call_row.columns:
        iv_val = call_row.iloc[0].get(iv_col)
        if iv_val is not None and not pd.isna(iv_val) and float(iv_val) > 0:
            current_iv = float(iv_val)

    if current_iv is None and iv_col in put_row.columns:
        iv_val = put_row.iloc[0].get(iv_col)
        if iv_val is not None and not pd.isna(iv_val) and float(iv_val) > 0:
            current_iv = float(iv_val)

    if current_iv is None:
        return None, None, implied_move_pct

    # --- IVR via HV rolling-range proxy ---
    iv_rank: Optional[float] = None
    try:
        with _yf_lock:
            hist = yf.download(
                ticker_obj.ticker,
                period="14mo",
                interval="1d",
                progress=False,
                multi_level_index=False,
                auto_adjust=True,
            )

        if hist is not None and not hist.empty:
            hist.columns = [c.capitalize() for c in hist.columns]
            closes = hist["Close"].dropna()

            if len(closes) >= _HV_ANNUAL_PERIOD + _HV_SHORT_PERIOD:
                log_ret = np.log(closes / closes.shift(1)).dropna()
                rolling_hv = log_ret.rolling(_HV_SHORT_PERIOD).std() * np.sqrt(_HV_ANNUAL_PERIOD)
                rolling_hv = rolling_hv.dropna()

                # Use the last 252 values for the 52-week range
                hv_range = rolling_hv.tail(_HV_ANNUAL_PERIOD)
                min_hv   = float(hv_range.min())
                max_hv   = float(hv_range.max())

                if max_hv > min_hv:
                    raw_ivr = (current_iv - min_hv) / (max_hv - min_hv) * 100.0
                    iv_rank = round(max(0.0, min(100.0, raw_ivr)), 1)

    except Exception:
        pass

    return iv_rank, current_iv, implied_move_pct


def _compute_put_call_ratio(calls: pd.DataFrame, puts: pd.DataFrame) -> Optional[float]:
    """
    Compute the put/call ratio by volume from the options chain.

    Sums total volume across all strikes for both legs and divides.
    Handles zero call volume by returning None instead of infinity.
    """
    try:
        call_vol = calls["volume"].dropna().sum() if "volume" in calls.columns else 0
        put_vol  = puts["volume"].dropna().sum()  if "volume" in puts.columns  else 0

        call_vol = float(call_vol)
        put_vol  = float(put_vol)

        if call_vol <= 0:
            return None

        return round(put_vol / call_vol, 3)

    except Exception:
        return None


def _iv_label(iv_rank: Optional[float]) -> str:
    if iv_rank is None:
        return "N/A"
    if iv_rank > _IVR_HIGH:
        return "High"
    if iv_rank >= _IVR_LOW:
        return "Normal"
    return "Low"


def _iv_signal(iv_hv_ratio: Optional[float]) -> str:
    if iv_hv_ratio is None:
        return "FAIR"
    if iv_hv_ratio > _IV_HV_EXPENSIVE:
        return "EXPENSIVE"
    if iv_hv_ratio < _IV_HV_CHEAP:
        return "CHEAP"
    return "FAIR"


def _sentiment_label(put_call_ratio: Optional[float]) -> str:
    if put_call_ratio is None:
        return "Neutral"
    if put_call_ratio > _PC_FEARFUL:
        return "Fearful"
    if put_call_ratio < _PC_COMPLACENT:
        return "Complacent"
    return "Neutral"


def _build_interpretation(
    ticker: str,
    iv_rank: Optional[float],
    iv_signal: str,
    sentiment: str,
    put_call_ratio: Optional[float],
    implied_move_pct: Optional[float],
) -> str:
    """Construct a dynamic, human-readable interpretation of the options signals."""

    move_str = (
        f" The market is pricing a {implied_move_pct:.1f}% move."
        if implied_move_pct is not None
        else ""
    )

    pc_str = (
        f" P/C ratio: {put_call_ratio:.2f}."
        if put_call_ratio is not None
        else ""
    )

    ivr_str = (
        f" IVR: {iv_rank:.0f}/100."
        if iv_rank is not None
        else " IVR: N/A."
    )

    # High IVR + fearful sentiment
    if iv_signal == "EXPENSIVE" and sentiment == "Fearful":
        return (
            f"Options are expensive and traders are buying protection.{ivr_str}{pc_str}"
            f" The market is fearful about {ticker} \u2014 this can mean a hedging "
            f"opportunity or a potential contrarian buy signal.{move_str}"
        )

    # Low IVR + complacent sentiment
    if iv_signal == "CHEAP" and sentiment == "Complacent":
        return (
            f"Options are cheap and complacency is high.{ivr_str}{pc_str}"
            f" This is the calm before potential volatility in {ticker} "
            f"\u2014 consider using cheap options for protection or defined-risk plays.{move_str}"
        )

    # High IVR + bullish (complacent put/call)
    if iv_signal == "EXPENSIVE" and sentiment == "Complacent":
        return (
            f"Options are expensive but the crowd is not buying puts.{ivr_str}{pc_str}"
            f" Elevated IV with bullish sentiment in {ticker} suggests call-buying "
            f"speculation \u2014 premium is rich on both sides.{move_str}"
        )

    # Low IVR + fearful
    if iv_signal == "CHEAP" and sentiment == "Fearful":
        return (
            f"Options are cheap yet traders are buying puts.{ivr_str}{pc_str}"
            f" Low IV with defensive positioning in {ticker} is unusual \u2014 "
            f"puts may be mispriced; look for a catalyst before fading.{move_str}"
        )

    # Neutral / mixed
    return (
        f"Options on {ticker} show normal conditions.{ivr_str}{pc_str}"
        f" No extreme fear or complacency detected \u2014 standard position sizing applies.{move_str}"
    )


def fetch_options_data(ticker: str) -> dict:
    """
    Fetch options-based volatility and sentiment analysis for a ticker.

    Calculates IV Rank, IV/HV Ratio, Put/Call Ratio, and implied move
    from the nearest eligible options expiration.

    Args:
        ticker: Stock symbol (e.g., 'TSLA').

    Returns:
        dict with keys:
          iv_rank          (float 0–100 or None)
          iv_hv_ratio      (float or None)  — ATM IV / 20-day HV
          put_call_ratio   (float or None)  — put volume / call volume
          implied_move_pct (float or None)  — ATM straddle / price * 100
          iv_label         ('High' / 'Normal' / 'Low' / 'N/A')
          iv_signal        ('EXPENSIVE' / 'FAIR' / 'CHEAP')
          sentiment_label  ('Fearful' / 'Neutral' / 'Complacent')
          explanation      (str) — educational tooltip text
          interpretation   (str) — dynamic reading for this ticker
          error            (str or None)
    """
    ticker = ticker.upper().strip()

    try:
        with _yf_lock:
            yf_ticker = yf.Ticker(ticker)

        # --- 1. Current price ---
        current_price = _compute_current_price(yf_ticker)
        if current_price is None:
            return _default_result(ticker, "Could not determine current price")

        # --- 2. Find nearest usable expiration ---
        expirations = yf_ticker.options
        if not expirations:
            return _default_result(ticker, "No options expirations available")

        target_exp = _find_nearest_expiration(expirations, _MIN_DAYS_TO_EXPIRY)
        if target_exp is None:
            return _default_result(ticker, "No expiration far enough out to use")

        # --- 3. Download the options chain ---
        try:
            with _yf_lock:
                chain = yf_ticker.option_chain(target_exp)
            calls = chain.calls.copy() if chain.calls is not None else pd.DataFrame()
            puts  = chain.puts.copy()  if chain.puts  is not None else pd.DataFrame()
        except Exception as exc:
            return _default_result(ticker, f"Could not download options chain: {exc}")

        if calls.empty or puts.empty:
            return _default_result(ticker, "Options chain returned empty data")

        # Normalise column names
        calls.columns = [c.lower().replace(" ", "_") for c in calls.columns]
        puts.columns  = [c.lower().replace(" ", "_") for c in puts.columns]

        # Rename 'lastprice' -> 'lastPrice' for _option_mid compatibility
        for df in (calls, puts):
            if "lastprice" in df.columns and "lastPrice" not in df.columns:
                df.rename(columns={"lastprice": "lastPrice"}, inplace=True)

        # --- 4. IV Rank, current IV, implied move ---
        iv_rank, current_iv, implied_move_pct = _compute_iv_rank_and_implied_vol(
            calls, puts, current_price, yf_ticker
        )

        # --- 5. Historical volatility (20-day) ---
        hv_20 = _compute_historical_volatility(yf_ticker, _HV_SHORT_PERIOD)

        # --- 6. IV/HV Ratio ---
        iv_hv_ratio: Optional[float] = None
        if current_iv is not None and hv_20 is not None and hv_20 > 0:
            iv_hv_ratio = round(current_iv / hv_20, 3)

        # --- 7. Put/Call Ratio ---
        put_call_ratio = _compute_put_call_ratio(calls, puts)

        # --- 8. Derived labels and signals ---
        label     = _iv_label(iv_rank)
        signal    = _iv_signal(iv_hv_ratio)
        sentiment = _sentiment_label(put_call_ratio)

        # --- 9. Interpretation ---
        interpretation = _build_interpretation(
            ticker=ticker,
            iv_rank=iv_rank,
            iv_signal=signal,
            sentiment=sentiment,
            put_call_ratio=put_call_ratio,
            implied_move_pct=implied_move_pct,
        )

        return {
            "iv_rank":          iv_rank,
            "iv_hv_ratio":      iv_hv_ratio,
            "put_call_ratio":   put_call_ratio,
            "implied_move_pct": implied_move_pct,
            "iv_label":         label,
            "iv_signal":        signal,
            "sentiment_label":  sentiment,
            "explanation":      _EXPLANATION,
            "interpretation":   interpretation,
            "error":            None,
        }

    except Exception as exc:
        return _default_result(ticker, str(exc))
