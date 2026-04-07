"""
Macro Regime Module
===================
Fetches and scores key macroeconomic indicators from FRED (Federal Reserve
Economic Data) and CBOE volatility data via yfinance to produce an overall
macro regime score and label.

Data sources
------------
- FRED (via fredapi if FRED_API_KEY env var is set, or pandas_datareader as
  keyless fallback): yield curve, HY credit spread, breakeven inflation, NFCI.
- yfinance: VIX (^VIX) and 3-month VIX (^VIX3M) for term-structure ratio.

Design notes
------------
- Every function returns a plain dict so callers never have to import special
  types from this module.
- All errors are caught and result in a graceful 'UNKNOWN' / None fallback so
  the rest of the dashboard still renders.
- Signals and scores follow the spec in the framework design document.
"""

from __future__ import annotations

import os
import warnings
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FRED_START = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")

_SERIES_IDS = {
    "yield_curve": "T10Y2Y",
    "hy_spread": "BAMLH0A0HYM2",
    "inflation": "T5YIE",
    "nfci": "NFCI",
}

_REGIME_EXPLANATION = (
    "The macro regime tells you the ocean your trades are swimming in. "
    "A RISK_ON environment means credit markets are calm, the yield curve is "
    "healthy, and volatility is low — technical setups have a higher "
    "probability of working. A RISK_OFF environment means even great technical "
    "entries will fight headwinds because institutions are reducing exposure "
    "across the board. Never fight a RISK_OFF regime with aggressive entries."
)

_INDICATOR_EXPLANATIONS = {
    "yield_curve": (
        "The yield curve (10-year minus 2-year Treasury spread) is one of the "
        "most reliable leading indicators in finance. When long-term rates are "
        "higher than short-term rates, banks can borrow cheap and lend dear — "
        "the economy is healthy. When the curve inverts (short-term rates > "
        "long-term rates), credit creation slows and recessions historically "
        "follow within 6–18 months."
    ),
    "hy_spread": (
        "High-yield (junk bond) credit spreads measure the extra yield "
        "investors demand to hold risky corporate debt vs risk-free Treasuries. "
        "Tight spreads signal that credit markets are calm and companies can "
        "borrow easily (risk-on). Widening spreads signal stress — either "
        "recession fears, credit events, or liquidity withdrawals — and "
        "historically lead equity drawdowns."
    ),
    "inflation": (
        "The 5-year breakeven inflation rate is the bond market's consensus "
        "forecast for average inflation over the next five years, derived from "
        "the spread between nominal and inflation-protected Treasuries (TIPS). "
        "When breakevens are near the Fed's 2% target, rate policy is "
        "predictable. Elevated breakevens (>2.5%) signal that the Fed may need "
        "to keep rates higher for longer — a headwind for valuations."
    ),
    "vix": (
        "The VIX term structure ratio (VIX3M / VIX) reveals the shape of "
        "implied-volatility expectations. Contango (ratio > 1) means the "
        "market expects calm near-term conditions — a hallmark of risk-on "
        "environments. Backwardation (ratio < 1) means near-term fear exceeds "
        "longer-term fear — a sign that traders are pricing in imminent stress "
        "and institutions are buying protection aggressively."
    ),
    "nfci": (
        "The Chicago Fed National Financial Conditions Index (NFCI) aggregates "
        "105 measures of risk, credit, and leverage across money markets, debt "
        "markets, and equity markets. Values below zero indicate financial "
        "conditions that are looser than the historical average — accommodative "
        "for risk assets. Values above +0.5 indicate meaningfully restrictive "
        "conditions and have historically coincided with equity stress."
    ),
}


# ---------------------------------------------------------------------------
# FRED helpers
# ---------------------------------------------------------------------------

def _fetch_fred_series(series_id: str, start: str) -> pd.Series | None:
    """
    Fetch a FRED time series, trying fredapi first (requires FRED_API_KEY env
    var) then falling back to pandas_datareader (no key required).

    Returns a pandas Series indexed by date, or None on failure.
    """
    # ---- Attempt 1: fredapi ------------------------------------------------
    api_key = os.environ.get("FRED_API_KEY")
    if api_key:
        try:
            from fredapi import Fred  # type: ignore
            fred = Fred(api_key=api_key)
            series = fred.get_series(series_id, observation_start=start)
            if series is not None and not series.empty:
                return series.dropna()
        except Exception:
            pass  # Fall through to pandas_datareader

    # ---- Attempt 2: pandas_datareader (keyless) ----------------------------
    try:
        import pandas_datareader.data as web  # type: ignore
        series = web.get_data_fred(series_id, start=start)
        if series is not None and not series.empty:
            col = series.columns[0] if hasattr(series, "columns") else series_id
            s = series[col] if hasattr(series, "columns") else series
            return s.dropna()
    except Exception:
        pass

    return None


def _latest_fred_value(series: pd.Series | None) -> float | None:
    """Return the most-recent non-NaN value from a FRED series, or None."""
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    return float(val) if pd.notna(val) else None


# ---------------------------------------------------------------------------
# VIX helpers
# ---------------------------------------------------------------------------

def _fetch_vix_values() -> tuple[float | None, float | None]:
    """
    Download the latest closing prices for ^VIX and ^VIX3M from yfinance.
    Returns (vix, vix3m) floats or (None, None) on failure.
    """
    try:
        raw = yf.download(
            ["^VIX", "^VIX3M"],
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        # yfinance >=0.2 returns MultiIndex columns
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]
        else:
            close = raw

        vix = float(close["^VIX"].dropna().iloc[-1]) if "^VIX" in close.columns else None
        vix3m = (
            float(close["^VIX3M"].dropna().iloc[-1])
            if "^VIX3M" in close.columns
            else None
        )
        return vix, vix3m
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Signal classifiers
# ---------------------------------------------------------------------------

def _yield_curve_signal(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value > 0.5:
        return "NORMAL"
    if value >= -0.5:
        return "FLATTENING"
    return "INVERTED"


def _hy_spread_signal(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 4.0:
        return "TIGHT"
    if value < 6.0:
        return "NORMAL"
    if value < 8.0:
        return "WIDE"
    return "STRESS"


def _inflation_signal(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 2.0:
        return "BELOW_TARGET"
    if value <= 2.5:
        return "ON_TARGET"
    if value <= 3.0:
        return "ELEVATED"
    return "HIGH"


def _vix_signal(ratio: float | None) -> str:
    if ratio is None:
        return "UNKNOWN"
    if ratio > 1.05:
        return "CONTANGO"
    if ratio >= 0.95:
        return "FLAT"
    return "BACKWARDATION"


def _nfci_signal(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < 0.0:
        return "LOOSE"
    if value <= 0.5:
        return "NEUTRAL"
    return "TIGHT"


# ---------------------------------------------------------------------------
# Regime score computation
# ---------------------------------------------------------------------------

def _compute_regime_score(
    yc_signal: str,
    hy_signal: str,
    inf_signal: str,
    vix_sig: str,
    nfci_sig: str,
) -> int:
    """
    Composite regime score 0-100 based on five components, each worth 20pts.

    Yield curve:   NORMAL=20, FLATTENING=10, INVERTED=0
    HY spread:     TIGHT=20, NORMAL=20, WIDE=5, STRESS=0
    Inflation:     ON_TARGET=20, BELOW_TARGET=15, ELEVATED=10, HIGH=5
    VIX structure: CONTANGO=20, FLAT=10, BACKWARDATION=0
    NFCI:          LOOSE=20, NEUTRAL=15, TIGHT=5
    """
    score = 0

    # Yield curve (20 pts)
    score += {"NORMAL": 20, "FLATTENING": 10, "INVERTED": 0}.get(yc_signal, 10)

    # HY spread (20 pts)
    score += {"TIGHT": 20, "NORMAL": 20, "WIDE": 5, "STRESS": 0}.get(hy_signal, 10)

    # Inflation (20 pts)
    score += {"BELOW_TARGET": 15, "ON_TARGET": 20, "ELEVATED": 10, "HIGH": 5}.get(
        inf_signal, 10
    )

    # VIX term structure (20 pts)
    score += {"CONTANGO": 20, "FLAT": 10, "BACKWARDATION": 0}.get(vix_sig, 10)

    # NFCI (20 pts)
    score += {"LOOSE": 20, "NEUTRAL": 15, "TIGHT": 5}.get(nfci_sig, 10)

    return int(score)


def _regime_label(score: int) -> str:
    if score >= 80:
        return "RISK_ON"
    if score >= 50:
        return "CAUTIOUS"
    return "RISK_OFF"


def _regime_color(label: str) -> str:
    return {
        "RISK_ON": "var(--color-bull)",
        "CAUTIOUS": "var(--color-neutral)",
        "RISK_OFF": "var(--color-bear)",
    }.get(label, "var(--color-neutral)")


def _signal_color(signal: str) -> str:
    """Map a generic signal keyword to a CSS variable colour."""
    _green = "var(--color-bull)"
    _yellow = "var(--color-neutral)"
    _red = "var(--color-bear)"
    _map: dict[str, str] = {
        # Yield curve
        "NORMAL": _green,
        "FLATTENING": _yellow,
        "INVERTED": _red,
        # HY spread
        "TIGHT": _green,
        "WIDE": _red,
        "STRESS": _red,
        # Inflation
        "BELOW_TARGET": _yellow,
        "ON_TARGET": _green,
        "ELEVATED": _yellow,
        "HIGH": _red,
        # VIX
        "CONTANGO": _green,
        "FLAT": _yellow,
        "BACKWARDATION": _red,
        # NFCI
        "LOOSE": _green,
        "NEUTRAL": _yellow,
        "TIGHT": _red,
        # Fallback
        "UNKNOWN": _yellow,
    }
    return _map.get(signal, _yellow)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_macro_regime() -> dict[str, Any]:
    """
    Fetch and score the current macro regime from FRED + yfinance.

    Returns
    -------
    dict with keys:
        yield_curve_value       float | None  — T10Y2Y spread in %
        yield_curve_signal      str           — 'NORMAL' / 'FLATTENING' / 'INVERTED'
        yield_curve_color       str           — CSS variable
        yield_curve_explanation str
        hy_spread_value         float | None  — BofA HY OAS in %
        hy_spread_signal        str
        hy_spread_color         str
        hy_spread_explanation   str
        inflation_value         float | None  — 5Y breakeven in %
        inflation_signal        str
        inflation_color         str
        inflation_explanation   str
        vix_value               float | None  — 30-day VIX level
        vix3m_value             float | None  — 90-day VIX level
        vix_ratio               float | None  — VIX3M / VIX
        vix_signal              str
        vix_color               str
        vix_explanation         str
        nfci_value              float | None
        nfci_signal             str
        nfci_color              str
        nfci_explanation        str
        regime_score            int  — 0-100
        regime_label            str  — 'RISK_ON' / 'CAUTIOUS' / 'RISK_OFF'
        regime_color            str  — CSS variable
        regime_explanation      str  — educational narrative
        last_updated            str  — ISO date string
        explanation             str  — brief one-liner purpose of module
        interpretation          str  — how to act on the regime score
        errors                  list[str]  — any non-fatal data errors
    """
    errors: list[str] = []

    # ------------------------------------------------------------------ #
    # 1. Yield Curve
    # ------------------------------------------------------------------ #
    yc_series = None
    try:
        yc_series = _fetch_fred_series(_SERIES_IDS["yield_curve"], _FRED_START)
    except Exception as exc:
        errors.append(f"yield_curve fetch error: {exc}")

    yc_val = _latest_fred_value(yc_series)
    yc_sig = _yield_curve_signal(yc_val)

    # ------------------------------------------------------------------ #
    # 2. High-Yield Credit Spread
    # ------------------------------------------------------------------ #
    hy_series = None
    try:
        hy_series = _fetch_fred_series(_SERIES_IDS["hy_spread"], _FRED_START)
    except Exception as exc:
        errors.append(f"hy_spread fetch error: {exc}")

    hy_val = _latest_fred_value(hy_series)
    hy_sig = _hy_spread_signal(hy_val)

    # ------------------------------------------------------------------ #
    # 3. Breakeven Inflation
    # ------------------------------------------------------------------ #
    inf_series = None
    try:
        inf_series = _fetch_fred_series(_SERIES_IDS["inflation"], _FRED_START)
    except Exception as exc:
        errors.append(f"inflation fetch error: {exc}")

    inf_val = _latest_fred_value(inf_series)
    inf_sig = _inflation_signal(inf_val)

    # ------------------------------------------------------------------ #
    # 4. VIX Term Structure
    # ------------------------------------------------------------------ #
    vix_val, vix3m_val = None, None
    try:
        vix_val, vix3m_val = _fetch_vix_values()
    except Exception as exc:
        errors.append(f"VIX fetch error: {exc}")

    if vix_val and vix3m_val and vix_val > 0:
        vix_ratio: float | None = round(vix3m_val / vix_val, 4)
    else:
        vix_ratio = None
    vix_sig = _vix_signal(vix_ratio)

    # ------------------------------------------------------------------ #
    # 5. NFCI
    # ------------------------------------------------------------------ #
    nfci_series = None
    try:
        nfci_series = _fetch_fred_series(_SERIES_IDS["nfci"], _FRED_START)
    except Exception as exc:
        errors.append(f"nfci fetch error: {exc}")

    nfci_val = _latest_fred_value(nfci_series)
    nfci_sig = _nfci_signal(nfci_val)

    # ------------------------------------------------------------------ #
    # 6. Composite Regime Score
    # ------------------------------------------------------------------ #
    score = _compute_regime_score(yc_sig, hy_sig, inf_sig, vix_sig, nfci_sig)
    label = _regime_label(score)
    color = _regime_color(label)

    # ------------------------------------------------------------------ #
    # 7. Interpretation string (data-driven)
    # ------------------------------------------------------------------ #
    active_risks: list[str] = []
    active_tailwinds: list[str] = []

    if yc_sig == "INVERTED":
        active_risks.append("an inverted yield curve (recession warning)")
    elif yc_sig == "NORMAL":
        active_tailwinds.append("a healthy yield curve")

    if hy_sig in ("WIDE", "STRESS"):
        active_risks.append("wide credit spreads (credit stress)")
    elif hy_sig in ("TIGHT", "NORMAL"):
        active_tailwinds.append("tight credit spreads (risk appetite intact)")

    if vix_sig == "BACKWARDATION":
        active_risks.append("VIX backwardation (near-term fear elevated)")
    elif vix_sig == "CONTANGO":
        active_tailwinds.append("VIX contango (volatility market is calm)")

    if nfci_sig == "TIGHT":
        active_risks.append("tight financial conditions (credit restrictive)")
    elif nfci_sig == "LOOSE":
        active_tailwinds.append("loose financial conditions (credit accommodative)")

    if inf_sig in ("ELEVATED", "HIGH"):
        active_risks.append("elevated inflation expectations (rate headwind)")
    elif inf_sig == "ON_TARGET":
        active_tailwinds.append("inflation near the Fed's 2% target")

    risk_str = (
        "Key risks: " + "; ".join(active_risks) + ". "
        if active_risks
        else "No major macro risk flags active. "
    )
    tail_str = (
        "Tailwinds: " + "; ".join(active_tailwinds) + "."
        if active_tailwinds
        else "Few macro tailwinds identified."
    )

    interpretation = (
        f"Current macro regime is {label} (score {score}/100). "
        f"{risk_str}{tail_str} "
        f"{'Favor high-conviction trend-following entries.' if label == 'RISK_ON' else ''}"
        f"{'Reduce size, tighten stops, avoid new speculative longs.' if label == 'RISK_OFF' else ''}"
        f"{'Be selective — take only the highest-quality setups.' if label == 'CAUTIOUS' else ''}"
    ).strip()

    return {
        # --- Yield Curve ---
        "yield_curve_value": round(yc_val, 4) if yc_val is not None else None,
        "yield_curve_signal": yc_sig,
        "yield_curve_color": _signal_color(yc_sig),
        "yield_curve_explanation": _INDICATOR_EXPLANATIONS["yield_curve"],
        # --- HY Spread ---
        "hy_spread_value": round(hy_val, 4) if hy_val is not None else None,
        "hy_spread_signal": hy_sig,
        "hy_spread_color": _signal_color(hy_sig),
        "hy_spread_explanation": _INDICATOR_EXPLANATIONS["hy_spread"],
        # --- Inflation ---
        "inflation_value": round(inf_val, 4) if inf_val is not None else None,
        "inflation_signal": inf_sig,
        "inflation_color": _signal_color(inf_sig),
        "inflation_explanation": _INDICATOR_EXPLANATIONS["inflation"],
        # --- VIX ---
        "vix_value": round(vix_val, 2) if vix_val is not None else None,
        "vix3m_value": round(vix3m_val, 2) if vix3m_val is not None else None,
        "vix_ratio": vix_ratio,
        "vix_signal": vix_sig,
        "vix_color": _signal_color(vix_sig),
        "vix_explanation": _INDICATOR_EXPLANATIONS["vix"],
        # --- NFCI ---
        "nfci_value": round(nfci_val, 4) if nfci_val is not None else None,
        "nfci_signal": nfci_sig,
        "nfci_color": _signal_color(nfci_sig),
        "nfci_explanation": _INDICATOR_EXPLANATIONS["nfci"],
        # --- Overall Regime ---
        "regime_score": score,
        "regime_label": label,
        "regime_color": color,
        "regime_explanation": _REGIME_EXPLANATION,
        # --- Metadata ---
        "last_updated": date.today().isoformat(),
        "explanation": (
            "Macro regime module: fetches five key macro indicators from FRED "
            "and CBOE to assess whether the broad market environment is "
            "conducive (RISK_ON), cautious (CAUTIOUS), or hostile (RISK_OFF) "
            "for long equity entries."
        ),
        "interpretation": interpretation,
        "errors": errors,
    }
