"""
Dark Pool & Institutional Flow Proxy module.

First-principles explanation:
  Dark pools are private trading venues where institutional investors
  (hedge funds, mutual funds, pension funds) execute large orders without
  revealing their intentions to the public market. They represent ~35-40%
  of all US equity volume daily.

  When a large institution wants to buy millions of shares without moving
  the price, they work orders quietly through dark pools over days or weeks.
  The signature they leave in public data: HIGH volume days where price
  barely moves — the institution is absorbing all available supply without
  letting price run away from them.

  We track three signals as proxies:
  1. Quiet accumulation days: high volume + narrow price range
  2. Volume-price correlation: sustained buying pressure vs selling pressure
  3. Block volume concentration: what % of recent volume came from the top
     decile days (institutional-sized sessions)
"""

import pandas as pd
import numpy as np
import yfinance as yf
import requests
from typing import Dict, Any, List
from datetime import datetime, timedelta


def _get_finra_short_volume(ticker: str, lookback_days: int = 10) -> Dict[str, Any]:
    """
    Attempts to fetch FINRA REGSHO short volume data (free, daily).
    FINRA publishes consolidated short volume data via their API.
    Returns empty dict on failure — this is purely additive signal.
    """
    try:
        # FINRA equity short volume API
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days + 5)

        # Try FINRA's OTC bulletin board API
        url = (
            f"https://api.finra.org/data/group/otcMarket/name/weeklySummary"
            f"?limit=4&offset=0"
        )
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'MarketAnalysis research@example.com',
        }
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.ok:
            data = resp.json()
            return {'available': True, 'raw': data}
    except Exception:
        pass
    return {'available': False}


def fetch_darkpool_data(ticker: str, lookback_days: int = 20) -> Dict[str, Any]:
    """
    Compute dark pool / institutional flow proxy signals from public OHLCV data.

    Args:
        ticker: Stock symbol
        lookback_days: Number of trading days to analyze (default 20 = ~1 month)

    Returns:
        Dict with proxy signals, labels, and educational context.
    """
    result: Dict[str, Any] = {
        'quiet_accumulation_days': None,
        'block_volume_pct': None,
        'institutional_correlation': None,
        'signal': 'NEUTRAL',
        'signal_strength': 'WEAK',
        'signal_color': 'var(--accent-marginal)',
        'top_volume_days': [],
        'short_volume_ratio': None,
        'data_source': 'VOLUME_PROXY',
        'explanation': (
            "Dark pools are private trading venues where institutional investors execute "
            "large orders without tipping off the public market. They handle ~35-40% of all "
            "US equity volume. When a fund wants to accumulate a position over days or weeks, "
            "they leave a signature in the public data: high-volume sessions where the price "
            "range is unusually narrow — the institution is absorbing all available supply "
            "without letting price run. We track three proxy signals: (1) Quiet accumulation "
            "days (high vol + narrow range), (2) Block volume concentration (top-decile "
            "sessions), and (3) Volume-direction correlation (is sustained volume driving "
            "price up or down?)."
        ),
        'interpretation': 'Insufficient data to compute dark pool proxy.',
        'error': None,
    }

    try:
        # Fetch 3 months of daily data for ATR baseline
        df = yf.download(
            ticker,
            period='3mo',
            interval='1d',
            progress=False,
            multi_level_index=False,
        )

        if df is None or df.empty or len(df) < lookback_days + 10:
            result['error'] = 'Insufficient daily data'
            return result

        df.columns = [c.capitalize() for c in df.columns]
        df = df.dropna(subset=['Close', 'Volume', 'High', 'Low'])

        # --- Baseline metrics (full 3-month window) ---
        avg_volume = df['Volume'].rolling(20).mean()
        daily_range = df['High'] - df['Low']
        avg_range = daily_range.rolling(20).mean()

        # --- Restrict analysis to lookback window ---
        recent = df.iloc[-lookback_days:].copy()
        recent_avg_vol = avg_volume.iloc[-lookback_days:]
        recent_avg_range = avg_range.iloc[-lookback_days:]

        # ---- Signal 1: Quiet Accumulation Days ----
        # High volume (>1.5x avg) AND narrow range (<0.6x avg range)
        vol_ratio = recent['Volume'] / recent_avg_vol
        range_ratio = (recent['High'] - recent['Low']) / recent_avg_range

        quiet_acc_mask = (vol_ratio > 1.5) & (range_ratio < 0.6)
        quiet_accumulation_days = int(quiet_acc_mask.sum())

        # ---- Signal 2: Block Volume Concentration ----
        # What % of the period's total volume came from top-decile sessions?
        total_vol = recent['Volume'].sum()
        top_decile_threshold = recent['Volume'].quantile(0.90)
        block_vol = recent.loc[recent['Volume'] >= top_decile_threshold, 'Volume'].sum()
        block_volume_pct = float((block_vol / total_vol) * 100) if total_vol > 0 else 0.0

        # ---- Signal 3: Institutional Correlation ----
        # Correlation between volume and signed price move
        # Positive = volume consistently accompanies price gains (buying)
        # Negative = volume consistently accompanies price drops (selling)
        price_change = recent['Close'].diff()
        signed_vol = recent['Volume'] * np.sign(price_change)
        corr = float(
            signed_vol.corr(price_change)
        ) if len(signed_vol.dropna()) > 5 else 0.0
        if np.isnan(corr):
            corr = 0.0

        # ---- Signal 4: Short Volume Ratio (via FINRA proxy) ----
        # Use the put/call proxy: fraction of down-volume days
        down_days = (price_change < 0).sum()
        up_days = (price_change > 0).sum()
        short_vol_ratio = float(down_days / (up_days + down_days)) if (up_days + down_days) > 0 else 0.5

        # ---- Top Volume Days for display ----
        top_days = recent.nlargest(3, 'Volume')[['Close', 'Volume', 'High', 'Low']].copy()
        top_vol_list: List[Dict] = []
        for idx, row in top_days.iterrows():
            day_range_pct = float((row['High'] - row['Low']) / row['Close'] * 100)
            top_vol_list.append({
                'date': str(idx.date()),
                'volume': int(row['Volume']),
                'range_pct': round(day_range_pct, 2),
                'close': round(float(row['Close']), 2),
                'type': 'Quiet Absorption' if day_range_pct < 1.5 else 'High Activity',
            })

        # ---- Composite Signal ----
        acc_score = 0
        # Quiet accumulation days: 3+ = strong signal
        if quiet_accumulation_days >= 3:
            acc_score += 3
        elif quiet_accumulation_days >= 2:
            acc_score += 2
        elif quiet_accumulation_days >= 1:
            acc_score += 1

        # Volume-price correlation
        if corr > 0.4:
            acc_score += 2
        elif corr > 0.2:
            acc_score += 1
        elif corr < -0.4:
            acc_score -= 2
        elif corr < -0.2:
            acc_score -= 1

        # Block concentration
        if block_volume_pct > 40:
            acc_score += 1

        if acc_score >= 4:
            signal, strength, color = 'ACCUMULATION', 'STRONG', 'var(--accent-optimal)'
        elif acc_score >= 2:
            signal, strength, color = 'ACCUMULATION', 'MODERATE', 'var(--accent-good)'
        elif acc_score <= -3:
            signal, strength, color = 'DISTRIBUTION', 'STRONG', 'var(--accent-poor)'
        elif acc_score <= -1:
            signal, strength, color = 'DISTRIBUTION', 'MODERATE', 'var(--accent-poor)'
        else:
            signal, strength, color = 'NEUTRAL', 'WEAK', 'var(--accent-marginal)'

        # ---- Interpretation (educational) ----
        if signal == 'ACCUMULATION' and strength == 'STRONG':
            interpretation = (
                f"🟢 Strong institutional accumulation pattern detected — "
                f"{quiet_accumulation_days} quiet absorption session(s) in the last {lookback_days} days. "
                f"Volume-price correlation of {corr:.2f} confirms buying pressure is driving volume. "
                f"Large institutions appear to be building a position. This type of pattern often "
                f"precedes significant price moves once the accumulation is complete."
            )
        elif signal == 'ACCUMULATION':
            interpretation = (
                f"🔵 Moderate accumulation signal — {quiet_accumulation_days} high-volume, "
                f"narrow-range session(s) detected. Some evidence of institutional buying, "
                f"but not yet a definitive pattern. Watch for this to develop further over "
                f"the next 1-2 weeks."
            )
        elif signal == 'DISTRIBUTION' and strength == 'STRONG':
            interpretation = (
                f"🔴 Distribution pattern detected — volume is concentrated on down days "
                f"(correlation: {corr:.2f}). Large holders appear to be selling into any "
                f"strength. This is a warning sign for any long entry — institutions are "
                f"exiting, not building positions."
            )
        elif signal == 'DISTRIBUTION':
            interpretation = (
                f"🟡 Mild distribution signal. Volume behavior leans toward selling pressure. "
                f"Not a definitive signal, but suggests caution before adding long exposure."
            )
        else:
            interpretation = (
                f"No clear institutional accumulation or distribution pattern over the last "
                f"{lookback_days} sessions. Volume behavior is consistent with normal retail "
                f"participation. Absence of signal is neutral — not bullish, not bearish."
            )

        result.update({
            'quiet_accumulation_days': quiet_accumulation_days,
            'block_volume_pct': round(block_volume_pct, 1),
            'institutional_correlation': round(corr, 3),
            'short_volume_ratio': round(short_vol_ratio, 3),
            'signal': signal,
            'signal_strength': strength,
            'signal_color': color,
            'top_volume_days': top_vol_list,
            'interpretation': interpretation,
            'error': None,
        })

    except Exception as e:
        result['error'] = str(e)

    return result
