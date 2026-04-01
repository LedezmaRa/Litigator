"""
Data fetching and validation module.

Provides functions for fetching market data from yfinance with:
- Disk caching to reduce API calls
- Parallel fetching for multiple tickers
- Retry logic for transient network failures
- Data validation
"""
import pandas as pd
import yfinance as yf
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
import threading

from .cache import read_cache, write_cache

# Lock to protect yfinance downloads (not fully thread-safe)
_yf_lock = threading.Lock()

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


def fetch_data(ticker: str, period: str = "2y", interval: str = "1d", use_cache: bool = True) -> pd.DataFrame:
    """
    Fetches OHLCV data for a given ticker using yfinance.

    Args:
        ticker: The stock symbol (e.g., 'SPY').
        period: Data period to fetch (default '2y' to ensure enough history for indicators).
        interval: Data interval (e.g., '1d', '1wk').
        use_cache: Whether to use disk cache (default True).

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume.
    """
    # Check cache first
    if use_cache:
        cached = read_cache(ticker, period, interval)
        if cached is not None:
            return cached

    print(f"Fetching {interval} data for {ticker}...")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with _yf_lock:
                df = yf.download(ticker, period=period, interval=interval, progress=False, multi_level_index=False)
                df = df.copy()

            if df.empty:
                raise ValueError(f"No data found for ticker {ticker}")

            df.columns = [c.capitalize() for c in df.columns]
            df = df.loc[:, ~df.columns.duplicated()]

            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            if use_cache:
                write_cache(ticker, period, interval, df)

            return df

        except ValueError:
            raise  # Bad ticker — don't retry
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS * attempt
                print(f"  Retry {attempt}/{MAX_RETRIES} for {ticker} in {wait}s...")
                time.sleep(wait)

    raise ConnectionError(f"Failed to fetch data for {ticker} after {MAX_RETRIES} attempts: {last_error}")


def fetch_data_parallel(
    tickers: List[str],
    period: str = "2y",
    interval: str = "1wk",
    max_workers: int = 10,
    use_cache: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    Fetches data for multiple tickers in parallel using ThreadPoolExecutor.

    Args:
        tickers: List of ticker symbols
        period: Data period (default '2y')
        interval: Data interval (default '1wk')
        max_workers: Maximum concurrent threads (default 10, yfinance rate-limit safe)
        use_cache: Whether to use disk cache (default True)

    Returns:
        Dict mapping ticker -> DataFrame (only successful fetches)
    """
    results: Dict[str, pd.DataFrame] = {}
    failed: List[str] = []

    def fetch_single(ticker: str) -> Tuple[str, Optional[pd.DataFrame]]:
        try:
            df = fetch_data(ticker, period, interval, use_cache)
            return ticker, df
        except Exception as e:
            return ticker, None

    print(f"Fetching data for {len(tickers)} tickers (parallel, {max_workers} workers)...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_single, t): t for t in tickers}

        for future in as_completed(futures):
            ticker, df = future.result()
            if df is not None and not df.empty:
                results[ticker] = df
            else:
                failed.append(ticker)

    if failed:
        print(f"Failed to fetch {len(failed)} tickers: {failed[:5]}{'...' if len(failed) > 5 else ''}")

    print(f"Successfully fetched {len(results)}/{len(tickers)} tickers")
    return results


def validate_data(df: pd.DataFrame, min_records: int = 100) -> bool:
    """
    Validates if the DataFrame has enough data for analysis.
    
    Args:
        df: The OHLCV DataFrame.
        min_records: Minimum required records (default 100 for 50-EMA + buffer).
        
    Returns:
        True if valid, raises ValueError otherwise.
    """
    if df is None or df.empty:
        raise ValueError("Data is empty")
        
    if len(df) < min_records:
        raise ValueError(f"Insufficient data points. Need {min_records}, got {len(df)}")
        
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
        
    return True
