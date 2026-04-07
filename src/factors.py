"""
Factor Exposure Module
======================
Scores a single stock across three investment factors — Momentum, Quality, and
Value — each on a 0-100 scale, then synthesises a composite factor profile.

Why factors matter
------------------
Factor investing quantifies WHY a stock is moving and whether the move is
backed by business fundamentals.  Used correctly, factor scores help you:
  1. Avoid buying a stock that is rallying purely on speculation (low quality).
  2. Avoid overpaying for a great business (poor value).
  3. Confirm that institutions are already chasing the name (momentum).

Data sources
------------
- Price momentum: yfinance OHLCV weekly data (1 year), plus SPY as benchmark.
- Quality / Value: yfinance .info dict (balance-sheet and income-statement
  derived ratios supplied directly by Yahoo Finance).

Error handling
--------------
Every metric that cannot be computed returns 0 points rather than raising.
The function therefore always returns a complete dict regardless of API state.
"""

from __future__ import annotations

import warnings
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Module-level explanation (static educational text)
# ---------------------------------------------------------------------------

_EXPLANATION = (
    "Factor investing is the science of understanding WHY a stock is moving. "
    "Momentum tells you if institutions are already chasing it (trend "
    "confirmation). Quality tells you if the underlying business deserves the "
    "price (fundamental anchor). Value tells you if you are overpaying relative "
    "to earnings and cash flow (margin of safety). The strongest entries "
    "combine strong momentum (confirmation) with decent quality (sustainability) "
    "— paying a fair price for a high-quality business that is already trending."
)

_FACTOR_EXPLANATIONS = {
    "momentum": (
        "Momentum captures the tendency of stocks that have recently "
        "outperformed to continue outperforming over the next 3-12 months. "
        "The classic definition uses 12-month minus 1-month return to exclude "
        "short-term mean-reversion noise. Stocks scoring above 70 are being "
        "actively accumulated by institutional money — confirmation that the "
        "trend has broad support."
    ),
    "quality": (
        "Quality measures the financial health and durability of a business. "
        "High-quality companies earn strong returns on equity, carry manageable "
        "debt, generate fat gross margins, and convert revenue into profit "
        "reliably. In drawdowns, high-quality stocks typically fall less and "
        "recover faster. They also compound wealth over the long run."
    ),
    "value": (
        "Value captures whether the market is pricing a stock cheaply relative "
        "to its earnings power and cash generation. The PEG ratio (P/E divided "
        "by growth rate) is the most holistic single value metric — it combines "
        "price, earnings, and growth expectations. Low P/FCF indicates the "
        "stock generates real cash that isn't just an accounting artifact."
    ),
}


# ---------------------------------------------------------------------------
# Helpers: safe value extraction from yfinance .info
# ---------------------------------------------------------------------------

def _safe_get(info: dict, key: str, default: float | None = None) -> float | None:
    """
    Safely retrieve a numeric value from the yfinance info dict.

    Returns default if the key is missing, None, NaN, or non-numeric.
    """
    val = info.get(key, default)
    if val is None:
        return default
    try:
        f = float(val)
        return f if np.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Factor 1: Momentum Score (0-100)
# ---------------------------------------------------------------------------

def _calc_momentum_score(ticker: str) -> tuple[float, float, float, str]:
    """
    Calculate price momentum score.

    Returns (score, return_12m1m_pct, return_3m_pct, label).
    """
    try:
        # Fetch 1 year of weekly price data for the stock and SPY benchmark
        raw = yf.download(
            [ticker, "SPY"],
            period="1y",
            interval="1wk",
            progress=False,
            auto_adjust=True,
        )

        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]
        else:
            close = raw[["Close"]] if "Close" in raw.columns else raw

        if ticker not in close.columns or close[ticker].dropna().shape[0] < 20:
            return 0.0, 0.0, 0.0, "Neutral"

        stock_close = close[ticker].dropna()
        spy_close = close.get("SPY", pd.Series(dtype=float)).dropna()

        # 12M-1M return: price 252 calendar days ago vs 21 days ago (approx weekly)
        # In weekly bars: ~52 weeks back vs ~4 weeks back
        n = len(stock_close)
        idx_12m = max(0, n - 52)
        idx_1m = max(0, n - 4)

        price_12m_ago = float(stock_close.iloc[idx_12m])
        price_1m_ago = float(stock_close.iloc[idx_1m])
        price_now = float(stock_close.iloc[-1])

        if price_12m_ago <= 0 or price_1m_ago <= 0:
            return 0.0, 0.0, 0.0, "Neutral"

        # 12M-1M momentum (skip last month to remove reversion noise)
        ret_12m1m = (price_1m_ago - price_12m_ago) / price_12m_ago * 100.0

        # 3M momentum (secondary signal)
        idx_3m = max(0, n - 13)
        price_3m_ago = float(stock_close.iloc[idx_3m])
        ret_3m = (price_now - price_3m_ago) / price_3m_ago * 100.0 if price_3m_ago > 0 else 0.0

        # SPY benchmark for normalisation
        if len(spy_close) >= 52:
            spy_12m_ago = float(spy_close.iloc[max(0, len(spy_close) - 52)])
            spy_1m_ago = float(spy_close.iloc[max(0, len(spy_close) - 4)])
            spy_ret_12m1m = (
                (spy_1m_ago - spy_12m_ago) / spy_12m_ago * 100.0
                if spy_12m_ago > 0
                else 0.0
            )
        else:
            spy_ret_12m1m = 10.0  # Reasonable fallback

        # Normalise: score = 100 * clip( ret / (|spy_ret| * 3 + 0.01), 0, 1 )
        # Blended: 70% 12m1m, 30% 3m
        blended_ret = 0.70 * ret_12m1m + 0.30 * ret_3m
        denominator = abs(spy_ret_12m1m) * 3.0 + 0.01
        raw_score = blended_ret / denominator
        score = float(_clamp(raw_score * 100.0))

        # Label
        if score >= 70:
            label = "Strong Momentum"
        elif score >= 50:
            label = "Positive Momentum"
        elif score >= 30:
            label = "Neutral"
        else:
            label = "Negative Momentum"

        return round(score, 1), round(ret_12m1m, 2), round(ret_3m, 2), label

    except Exception:
        return 0.0, 0.0, 0.0, "Neutral"


# ---------------------------------------------------------------------------
# Factor 2: Quality Score (0-100)
# ---------------------------------------------------------------------------

def _calc_quality_score(info: dict) -> tuple[float, str]:
    """
    Calculate fundamental quality score from yfinance .info dict.

    Four sub-components each worth 0-25 points.  Returns (score, label).
    """
    score = 0.0

    # ---- Return on Equity (25 pts) ----------------------------------------
    roe = _safe_get(info, "returnOnEquity")
    if roe is not None:
        roe_pct = roe * 100.0  # yfinance returns as decimal
        if roe_pct >= 20.0:
            score += 25
        elif roe_pct >= 10.0:
            score += 15
        elif roe_pct >= 5.0:
            score += 8
        # else 0

    # ---- Gross Margin (25 pts) --------------------------------------------
    gm = _safe_get(info, "grossMargins")
    if gm is not None:
        gm_pct = gm * 100.0
        if gm_pct >= 40.0:
            score += 25
        elif gm_pct >= 25.0:
            score += 15
        elif gm_pct >= 10.0:
            score += 8
        # else 0

    # ---- Debt/Equity (25 pts, lower is better) ----------------------------
    de = _safe_get(info, "debtToEquity")
    if de is not None:
        # yfinance can return D/E as a percentage or as a ratio; values > 10
        # typically indicate it is a percentage — normalise if needed.
        de_ratio = de / 100.0 if de > 10 else de
        if de_ratio < 0.3:
            score += 25
        elif de_ratio < 1.0:
            score += 15
        elif de_ratio < 2.0:
            score += 8
        # else 0

    # ---- Profit Margin (25 pts) -------------------------------------------
    pm = _safe_get(info, "profitMargins")
    if pm is not None:
        pm_pct = pm * 100.0
        if pm_pct >= 15.0:
            score += 25
        elif pm_pct >= 8.0:
            score += 15
        elif pm_pct >= 3.0:
            score += 8
        # else 0

    score = _clamp(score, 0, 100)

    if score >= 70:
        label = "High Quality"
    elif score >= 50:
        label = "Good Quality"
    elif score >= 30:
        label = "Average Quality"
    else:
        label = "Low Quality"

    return round(score, 1), label


# ---------------------------------------------------------------------------
# Factor 3: Value Score (0-100)
# ---------------------------------------------------------------------------

def _calc_value_score(info: dict) -> tuple[float, str]:
    """
    Calculate valuation score from yfinance .info dict.

    Three sub-components:
    - Forward P/E  (35 pts)
    - Price/FCF    (35 pts)
    - PEG Ratio    (30 pts)

    Returns (score, label).
    """
    score = 0.0

    # ---- Forward P/E (35 pts) ---------------------------------------------
    fpe = _safe_get(info, "forwardPE")
    if fpe is not None and fpe > 0:
        if fpe < 15.0:
            score += 35
        elif fpe < 20.0:
            score += 25
        elif fpe < 30.0:
            score += 15
        elif fpe < 50.0:
            score += 5
        # else 0 (>50x)

    # ---- Price / Free Cash Flow (35 pts) ----------------------------------
    pfcf = _safe_get(info, "priceToFreeCashflow")
    if pfcf is None or pfcf <= 0:
        # Try to derive from market cap and freeCashflow
        mkt_cap = _safe_get(info, "marketCap")
        fcf = _safe_get(info, "freeCashflow")
        if mkt_cap and fcf and fcf > 0:
            pfcf = mkt_cap / fcf

    if pfcf is not None and pfcf > 0:
        if pfcf < 15.0:
            score += 35
        elif pfcf < 25.0:
            score += 20
        elif pfcf < 40.0:
            score += 10
        # else 0

    # ---- PEG Ratio (30 pts) -----------------------------------------------
    peg = _safe_get(info, "pegRatio")
    if peg is not None and peg > 0:
        if peg < 1.0:
            score += 30
        elif peg < 1.5:
            score += 20
        elif peg < 2.0:
            score += 10
        # else 0

    score = _clamp(score, 0, 100)

    if score >= 70:
        label = "Deep Value"
    elif score >= 50:
        label = "Fair Value"
    elif score >= 30:
        label = "Fairly Priced"
    else:
        label = "Expensive"

    return round(score, 1), label


# ---------------------------------------------------------------------------
# Composite factor profile
# ---------------------------------------------------------------------------

def _composite_profile(
    momentum_score: float,
    quality_score: float,
    value_score: float,
) -> tuple[str, str, str]:
    """
    Derive:
      - dominant_factor: which of the three scores is highest
      - profile_label:   human-readable profile name
      - alignment:       'ALIGNED' / 'MIXED' / 'CONFLICTED'

    Returns (dominant_factor, profile_label, alignment).
    """
    scores = {
        "Momentum": momentum_score,
        "Quality": quality_score,
        "Value": value_score,
    }
    dominant = max(scores, key=lambda k: scores[k])

    high = [k for k, v in scores.items() if v >= 60]
    n_high = len(high)

    if n_high >= 2:
        alignment = "ALIGNED"
    elif n_high == 1:
        alignment = "MIXED"
    else:
        alignment = "CONFLICTED"

    # Profile labels
    mom_high = momentum_score >= 60
    qual_high = quality_score >= 60
    val_high = value_score >= 60

    if mom_high and qual_high and val_high:
        profile = "Quality Growth at a Discount"
    elif mom_high and qual_high:
        profile = "Momentum + Quality Growth"
    elif mom_high and val_high:
        profile = "Momentum Value"
    elif qual_high and val_high:
        profile = "Quality Value"
    elif mom_high:
        profile = "Pure Momentum Play"
    elif qual_high:
        profile = "Quality at a Premium"
    elif val_high:
        if quality_score < 30:
            profile = "Value Trap Risk"
        else:
            profile = "Deep Value Opportunity"
    else:
        profile = "Speculative / No Clear Factor Edge"

    return dominant, profile, alignment


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_factor_scores(ticker: str) -> dict[str, Any]:
    """
    Calculate momentum, quality, and value factor scores for a single ticker.

    Parameters
    ----------
    ticker : str
        A valid yfinance ticker symbol (e.g., 'AAPL', 'NVDA').

    Returns
    -------
    dict with keys:
        momentum_score       float  — 0-100
        momentum_label       str    — 'Strong Momentum' / 'Positive Momentum' /
                                      'Neutral' / 'Negative Momentum'
        momentum_ret_12m1m   float  — raw 12M-1M price return in %
        momentum_ret_3m      float  — raw 3M price return in %
        momentum_explanation str
        quality_score        float  — 0-100
        quality_label        str    — 'High Quality' / ... / 'Low Quality'
        quality_roe          float | None  — Return on equity %
        quality_gross_margin float | None  — Gross margin %
        quality_de_ratio     float | None  — Debt/equity ratio
        quality_profit_margin float | None — Net profit margin %
        quality_explanation  str
        value_score          float  — 0-100
        value_label          str    — 'Deep Value' / ... / 'Expensive'
        value_forward_pe     float | None
        value_pfcf           float | None
        value_peg            float | None
        value_explanation    str
        composite_profile    str    — e.g. 'Momentum + Quality Growth'
        dominant_factor      str    — 'Momentum' / 'Quality' / 'Value'
        alignment            str    — 'ALIGNED' / 'MIXED' / 'CONFLICTED'
        alignment_color      str    — CSS variable
        explanation          str    — educational context
        interpretation       str    — data-driven summary for this stock
        ticker               str    — echo of input ticker
        last_updated         str    — ISO datetime
        errors               list[str]
    """
    errors: list[str] = []
    ticker = ticker.upper().strip()

    # ------------------------------------------------------------------ #
    # Fetch yfinance .info (fundamentals)
    # ------------------------------------------------------------------ #
    info: dict = {}
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}
        if not info or info.get("regularMarketPrice") is None:
            # Sometimes .info returns an empty or minimal dict — try fast_info
            try:
                fi = yf_ticker.fast_info
                info["regularMarketPrice"] = getattr(fi, "last_price", None)
            except Exception:
                pass
    except Exception as exc:
        errors.append(f"yfinance .info fetch failed: {exc}")

    # ------------------------------------------------------------------ #
    # Factor 1: Momentum
    # ------------------------------------------------------------------ #
    mom_score, ret_12m1m, ret_3m, mom_label = _calc_momentum_score(ticker)

    # ------------------------------------------------------------------ #
    # Factor 2: Quality
    # ------------------------------------------------------------------ #
    qual_score, qual_label = _calc_quality_score(info)

    # Raw quality metrics for display
    roe_raw = _safe_get(info, "returnOnEquity")
    gm_raw = _safe_get(info, "grossMargins")
    de_raw = _safe_get(info, "debtToEquity")
    pm_raw = _safe_get(info, "profitMargins")

    roe_pct = round(roe_raw * 100, 2) if roe_raw is not None else None
    gm_pct = round(gm_raw * 100, 2) if gm_raw is not None else None
    de_ratio = (
        round(de_raw / 100, 4) if (de_raw is not None and de_raw > 10)
        else (round(de_raw, 4) if de_raw is not None else None)
    )
    pm_pct = round(pm_raw * 100, 2) if pm_raw is not None else None

    # ------------------------------------------------------------------ #
    # Factor 3: Value
    # ------------------------------------------------------------------ #
    val_score, val_label = _calc_value_score(info)

    # Raw value metrics for display
    fpe_raw = _safe_get(info, "forwardPE")
    pfcf_raw = _safe_get(info, "priceToFreeCashflow")
    if pfcf_raw is None or pfcf_raw <= 0:
        mkt_cap = _safe_get(info, "marketCap")
        fcf = _safe_get(info, "freeCashflow")
        if mkt_cap and fcf and fcf > 0:
            pfcf_raw = round(mkt_cap / fcf, 2)
    peg_raw = _safe_get(info, "pegRatio")

    # ------------------------------------------------------------------ #
    # Composite profile
    # ------------------------------------------------------------------ #
    dominant, profile, alignment = _composite_profile(mom_score, qual_score, val_score)

    alignment_color = {
        "ALIGNED": "var(--color-bull)",
        "MIXED": "var(--color-neutral)",
        "CONFLICTED": "var(--color-bear)",
    }.get(alignment, "var(--color-neutral)")

    # ------------------------------------------------------------------ #
    # Interpretation (data-driven)
    # ------------------------------------------------------------------ #
    company_name = info.get("shortName") or info.get("longName") or ticker

    interp_parts: list[str] = [
        f"{company_name} ({ticker}) factor profile: {profile} | Alignment: {alignment}.",
        f"Momentum: {mom_label} ({mom_score:.0f}/100) — "
        f"12M-1M return {ret_12m1m:+.1f}%, 3M return {ret_3m:+.1f}%.",
        f"Quality: {qual_label} ({qual_score:.0f}/100) — "
        + (f"ROE {roe_pct:.1f}%" if roe_pct is not None else "ROE N/A")
        + ", "
        + (f"Gross Margin {gm_pct:.1f}%" if gm_pct is not None else "Gross Margin N/A")
        + ".",
        f"Value: {val_label} ({val_score:.0f}/100) — "
        + (f"Fwd P/E {fpe_raw:.1f}x" if fpe_raw is not None else "Fwd P/E N/A")
        + ", "
        + (f"P/FCF {pfcf_raw:.1f}x" if pfcf_raw is not None else "P/FCF N/A")
        + ".",
    ]

    # Actionable summary
    if alignment == "ALIGNED" and mom_score >= 60:
        interp_parts.append(
            "Multiple factors are aligned — the stock has both trend confirmation "
            "and fundamental support. A strong candidate for high-conviction entries."
        )
    elif alignment == "MIXED":
        if dominant == "Momentum" and qual_score < 40:
            interp_parts.append(
                "Strong momentum but weak quality signals — the move may lack "
                "fundamental backing. Manage risk carefully; momentum-only plays "
                "tend to be volatile."
            )
        elif dominant == "Value" and mom_score < 30:
            interp_parts.append(
                "Cheap on paper but no momentum — potential value trap. "
                "Wait for a catalyst or technical confirmation before entry."
            )
        elif dominant == "Quality" and val_score < 30:
            interp_parts.append(
                "High-quality business but expensive. Suitable for a core "
                "long-term hold; risky to chase short-term as a swing trade "
                "without a pullback entry."
            )
        else:
            interp_parts.append(
                "Mixed factor signals — the best approach is to wait for "
                "a clearer technical setup before entry."
            )
    else:
        interp_parts.append(
            "No factor is dominant. This name lacks both trend confirmation "
            "and clear fundamental support. Avoid unless a specific catalyst "
            "is identified."
        )

    return {
        # --- Momentum ---
        "momentum_score": mom_score,
        "momentum_label": mom_label,
        "momentum_ret_12m1m": ret_12m1m,
        "momentum_ret_3m": ret_3m,
        "momentum_explanation": _FACTOR_EXPLANATIONS["momentum"],
        # --- Quality ---
        "quality_score": qual_score,
        "quality_label": qual_label,
        "quality_roe": roe_pct,
        "quality_gross_margin": gm_pct,
        "quality_de_ratio": de_ratio,
        "quality_profit_margin": pm_pct,
        "quality_explanation": _FACTOR_EXPLANATIONS["quality"],
        # --- Value ---
        "value_score": val_score,
        "value_label": val_label,
        "value_forward_pe": round(fpe_raw, 2) if fpe_raw is not None else None,
        "value_pfcf": round(pfcf_raw, 2) if pfcf_raw is not None else None,
        "value_peg": round(peg_raw, 2) if peg_raw is not None else None,
        "value_explanation": _FACTOR_EXPLANATIONS["value"],
        # --- Composite ---
        "composite_profile": profile,
        "dominant_factor": dominant,
        "alignment": alignment,
        "alignment_color": alignment_color,
        # --- Metadata ---
        "explanation": _EXPLANATION,
        "interpretation": " ".join(interp_parts),
        "ticker": ticker,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "errors": errors,
    }
