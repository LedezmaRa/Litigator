
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
import yfinance as yf

@dataclass
class DriverAnalysis:
    ticker: str
    name: str
    current_price: float
    change_1m: float
    change_3m: float
    change_ytd: float
    high_52w: float
    low_52w: float
    correlation_90d: float # Correlation to Sector ETF
    trend: str # BULLISH, BEARISH, NEUTRAL
    prices: pd.Series = None # For sparkline

def fetch_drivers(drivers: Dict[str, str], period="1y") -> Dict[str, pd.DataFrame]:
    """
    Fetch historical data for driver tickers.
    Returns dict of {ticker: dataframe}
    """
    data_map = {}
    if not drivers:
        return data_map
        
    tickers = list(drivers.keys())
    try:
        # Use yfinance to fetch
        # Note: Some futures tickers like CL=F might need special handling if yf fails, 
        # but yf usually handles them ok.
        raw_data = yf.download(tickers, period=period, interval="1d", progress=False, group_by='ticker')
        
        # If single ticker, structure is different
        if len(tickers) == 1:
            t = tickers[0]
            df = raw_data
            if not df.empty:
                df.columns = [c.lower() for c in df.columns]
                data_map[t] = df
        else:
            for t in tickers:
                if t in raw_data.columns.levels[0]:
                    df = raw_data[t].copy()
                    if not df.empty:
                        df.columns = [c.lower() for c in df.columns]
                        data_map[t] = df
                        
    except Exception as e:
        print(f"Error fetching drivers: {e}")
        
    return data_map

def calculate_correlations(sector_closes: pd.Series, driver_closes: pd.Series, window=90) -> float:
    """
    Calculate correlation between sector ETF and driver over the specified window (in days).
    Returns the most recent correlation value.
    """
    # Align dates
    df = pd.DataFrame({'sector': sector_closes, 'driver': driver_closes}).dropna()
    
    if len(df) < 2:
        return 0.0
        
    # Use date-based filtering because data might be weekly (e.g. len < 90 but covers > 90 days)
    cutoff_date = df.index[-1] - pd.Timedelta(days=window)
    recent_df = df[df.index >= cutoff_date]
    
    if len(recent_df) < 2:
        return 0.0
        
    corr = recent_df['sector'].corr(recent_df['driver'])
    return corr if not pd.isna(corr) else 0.0

def analyze_drivers(
    sector_etf: str, 
    sector_closes: pd.Series, 
    drivers_config: Dict[str, str],
    driver_data: Dict[str, pd.DataFrame]
) -> List[DriverAnalysis]:
    """
    Analyze all configured drivers for a sector.
    """
    results = []
    
    for ticker, name in drivers_config.items():
        if ticker not in driver_data:
            continue
            
        df = driver_data[ticker]
        if df.empty: continue

        # Drop any NaN rows in close to prevent bad calculations (some tickers have trailing NaN)
        close = df['close'].dropna()
        if close.empty: continue

        # Price & Change
        curr_price = close.iloc[-1]
        start_price_1m = close.iloc[-21] if len(close) > 21 else close.iloc[0]
        start_price_3m = close.iloc[-63] if len(close) > 63 else close.iloc[0]
        chg_1m = (curr_price / start_price_1m) - 1
        chg_3m = (curr_price / start_price_3m) - 1

        # YTD change: find the last close of the previous year
        try:
            import datetime
            current_year = close.index[-1].year
            prev_year_end = close[close.index.year < current_year]
            start_price_ytd = prev_year_end.iloc[-1] if not prev_year_end.empty else close.iloc[0]
        except Exception:
            start_price_ytd = close.iloc[0]
        chg_ytd = (curr_price / start_price_ytd) - 1

        # 52-week high/low
        high_52w = close.tail(252).max()
        low_52w = close.tail(252).min()


        # Trend (Simple EMA crossover or just Px > EMA50)
        ema_50 = close.ewm(span=50).mean().iloc[-1]
        trend = "BULLISH" if curr_price > ema_50 else "BEARISH"

        
        # Correlation
        corr = 0.0
        if sector_closes is not None and len(sector_closes) > 0:
             # Align data for correlation
             # Sector data is likely Weekly (from main.py config)
             # Driver data is Daily (from fetch_drivers)
             
             # 1. Resample driver to weekly to match sector? 
             # Or reindex sector to daily?
             # Easiest: Reindex driver to match sector dates (using 'asof' or ffill)
             
             # Ensure index is datetime
             if not isinstance(df.index, pd.DatetimeIndex):
                 df.index = pd.to_datetime(df.index)
                 
             # Reindex driver to sector dates
             # We use reindex with nearest or ffill to get the price at that week's close
             driver_aligned = df['close'].reindex(sector_closes.index, method='ffill')
             
             # Calculate correlation on the aligned series
             corr = calculate_correlations(sector_closes, driver_aligned)
             
        results.append(DriverAnalysis(
            ticker=ticker,
            name=name,
            current_price=curr_price,
            change_1m=chg_1m,
            change_3m=chg_3m,
            change_ytd=chg_ytd,
            high_52w=high_52w,
            low_52w=low_52w,
            correlation_90d=corr,
            trend=trend,
            prices=df['close']
        ))
        
    return results
