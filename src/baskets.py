"""
Basket context and short interest module.

Provides:
1. Short interest data per ticker (from yfinance .info)
2. Squeeze Potential Score (0-100)
3. GVIP vs SPY relative performance — proxy for hedge fund crowded-long positioning

First-principles rationale:
  A market move has two possible causes:
  - Fundamental: genuine buying conviction — VIP long basket leads, most-shorted lags
  - Technical/mechanical: forced short covering — most-shorted basket surges, VIP lags

  Tracking GVIP (Goldman Sachs Hedge Fund VIP ETF) vs SPY lets us decompose
  whether the hedge fund community's crowded longs are leading or lagging the market.
  Short interest data per stock quantifies squeeze fuel and urgency.
"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

import pandas as pd
import yfinance as yf

# Separate lock for .info() calls (different yfinance code path from .download())
_yf_info_lock = threading.Lock()
_yf_download_lock = threading.Lock()


def fetch_short_interest(ticker: str) -> Dict[str, Any]:
    """
    Returns short interest context for a single ticker via yfinance.

    Keys returned:
      float_short      - shares short as % of float (0.0–1.0 decimal, e.g. 0.10 = 10%)
      days_to_cover    - short ratio (days at avg volume to cover entire short position)
      shares_short     - absolute shares currently short
      shares_short_prior - shares short prior month
      mom_change_pct   - month-over-month change in shares short (%)
      squeeze_score    - 0-100 composite score
      squeeze_label    - 'High' | 'Moderate' | 'Low'
    """
    data: Dict[str, Any] = {
        'float_short': None,
        'days_to_cover': None,
        'shares_short': None,
        'shares_short_prior': None,
        'mom_change_pct': None,
        'squeeze_score': None,
        'squeeze_label': 'N/A',
    }
    try:
        with _yf_info_lock:
            info = yf.Ticker(ticker).info

        float_short = info.get('shortPercentOfFloat')   # decimal, e.g. 0.05 = 5%
        days_to_cover = info.get('shortRatio')
        shares_short = info.get('sharesShort')
        shares_short_prior = info.get('sharesShortPriorMonth')

        data.update({
            'float_short': float_short,
            'days_to_cover': days_to_cover,
            'shares_short': shares_short,
            'shares_short_prior': shares_short_prior,
        })

        if shares_short and shares_short_prior and shares_short_prior > 0:
            data['mom_change_pct'] = (
                (shares_short - shares_short_prior) / shares_short_prior
            ) * 100

        # --- Squeeze Score (0-100) ---
        # Short fuel: how much compressed energy exists in the short book
        #   20% float short → 60 pts  (float_short * 300, capped at 60)
        # Cover urgency: how hard it would be to exit the position quickly
        #   10 days to cover → 40 pts  (days_to_cover * 4, capped at 40)
        score = 0.0
        if float_short is not None:
            score += min(60.0, float_short * 300.0)
        if days_to_cover is not None:
            score += min(40.0, days_to_cover * 4.0)

        sq = int(min(100, score))
        data['squeeze_score'] = sq
        data['squeeze_label'] = 'High' if sq >= 65 else ('Moderate' if sq >= 35 else 'Low')

    except Exception:
        pass

    return data


def fetch_short_interest_parallel(
    tickers: List[str],
    max_workers: int = 6,
) -> Dict[str, Dict[str, Any]]:
    """Fetches short interest for multiple tickers concurrently."""
    results: Dict[str, Dict[str, Any]] = {}
    print(f"Fetching short interest data for {len(tickers)} tickers...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_short_interest, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                results[ticker] = future.result()
            except Exception:
                results[ticker] = {
                    'float_short': None, 'days_to_cover': None,
                    'shares_short': None, 'shares_short_prior': None,
                    'mom_change_pct': None, 'squeeze_score': None,
                    'squeeze_label': 'N/A',
                }

    print(f"Short interest data fetched for {len(results)} tickers.")
    return results


def fetch_basket_context() -> Dict[str, Any]:
    """
    Fetches GVIP and SPY daily data to compute relative basket performance.

    GVIP = Goldman Sachs Hedge Industry VIP ETF — tracks the 50 stocks most
    commonly held as top-10 positions by fundamentally-driven hedge funds.
    When GVIP underperforms SPY, the market is being led by something other
    than genuine fundamental conviction (e.g., short covering in crowded shorts).

    Returns:
      gvip_5d / spy_5d     - 5-day returns for GVIP and SPY
      relative_5d          - GVIP 5D minus SPY 5D (key signal)
      gvip_20d / spy_20d   - 20-day returns for trend context
      relative_20d         - 20D relative performance
      signal               - 'LONG_BASKET_LEADING' | 'SHORT_SQUEEZE_REGIME' | 'NEUTRAL'
      signal_label         - human-readable label
      signal_color         - CSS color variable
      gvip_price / spy_price - latest close prices
      error                - None on success, error string on failure
    """
    result: Dict[str, Any] = {
        'gvip_5d': None,
        'spy_5d': None,
        'relative_5d': None,
        'gvip_20d': None,
        'spy_20d': None,
        'relative_20d': None,
        'signal': 'NEUTRAL',
        'signal_label': 'Neutral',
        'signal_color': 'var(--accent-marginal)',
        'gvip_price': None,
        'spy_price': None,
        'error': None,
    }
    try:
        print("Fetching basket context (GVIP, SPY)...")
        with _yf_download_lock:
            gvip_df = yf.download(
                'GVIP', period='3mo', interval='1d',
                progress=False, multi_level_index=False,
            )
        with _yf_download_lock:
            spy_df = yf.download(
                'SPY', period='3mo', interval='1d',
                progress=False, multi_level_index=False,
            )

        if gvip_df.empty or spy_df.empty:
            result['error'] = 'No data returned for GVIP or SPY'
            return result

        # Normalise column names
        gvip_df.columns = [c.capitalize() for c in gvip_df.columns]
        spy_df.columns = [c.capitalize() for c in spy_df.columns]

        gvip_close = gvip_df['Close'].dropna()
        spy_close = spy_df['Close'].dropna()

        if len(gvip_close) < 21 or len(spy_close) < 21:
            result['error'] = 'Insufficient data — need at least 21 trading days'
            return result

        def _ret(series: pd.Series, n: int) -> float:
            return float((series.iloc[-1] / series.iloc[-(n + 1)] - 1) * 100)

        gvip_5d = _ret(gvip_close, 5)
        spy_5d = _ret(spy_close, 5)
        gvip_20d = _ret(gvip_close, 20)
        spy_20d = _ret(spy_close, 20)
        relative_5d = round(gvip_5d - spy_5d, 2)
        relative_20d = round(gvip_20d - spy_20d, 2)

        result.update({
            'gvip_5d': round(gvip_5d, 2),
            'spy_5d': round(spy_5d, 2),
            'relative_5d': relative_5d,
            'gvip_20d': round(gvip_20d, 2),
            'spy_20d': round(spy_20d, 2),
            'relative_20d': relative_20d,
            'gvip_price': round(float(gvip_close.iloc[-1]), 2),
            'spy_price': round(float(spy_close.iloc[-1]), 2),
        })

        # Signal: >+2% → hedge fund longs leading (conviction), <-2% → squeeze regime
        if relative_5d > 2.0:
            result['signal'] = 'LONG_BASKET_LEADING'
            result['signal_label'] = 'Long Basket Leading'
            result['signal_color'] = 'var(--accent-optimal)'
        elif relative_5d < -2.0:
            result['signal'] = 'SHORT_SQUEEZE_REGIME'
            result['signal_label'] = 'Short Squeeze Regime'
            result['signal_color'] = 'var(--accent-poor)'

    except Exception as e:
        result['error'] = str(e)

    return result
