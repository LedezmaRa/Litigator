"""
Disk caching module for market data.

Provides caching with configurable TTL to avoid redundant yfinance API calls.
Uses parquet format if pyarrow is available, otherwise falls back to pickle.
"""
import hashlib
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Cache configuration
CACHE_DIR = Path.home() / ".ema_adx_atr_cache"
DEFAULT_TTL_HOURS = 4  # Cache valid for 4 hours

# Check for parquet support
try:
    import pyarrow
    PARQUET_AVAILABLE = True
    CACHE_EXT = ".parquet"
except ImportError:
    PARQUET_AVAILABLE = False
    CACHE_EXT = ".pkl"


def get_cache_path(ticker: str, period: str, interval: str) -> Path:
    """
    Generate unique cache file path for a ticker/period/interval combination.

    Args:
        ticker: Stock symbol
        period: Data period (e.g., '2y')
        interval: Data interval (e.g., '1wk')

    Returns:
        Path object for the cache file
    """
    key = f"{ticker}_{period}_{interval}"
    hash_key = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{ticker}_{hash_key}{CACHE_EXT}"


def is_cache_valid(cache_path: Path, ttl_hours: int = DEFAULT_TTL_HOURS) -> bool:
    """
    Check if cache file exists and is within TTL.

    Args:
        cache_path: Path to cache file
        ttl_hours: Time-to-live in hours

    Returns:
        True if cache is valid, False otherwise
    """
    if not cache_path.exists():
        return False
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=ttl_hours)


def read_cache(ticker: str, period: str, interval: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> Optional[pd.DataFrame]:
    """
    Read cached data if valid.

    Args:
        ticker: Stock symbol
        period: Data period
        interval: Data interval
        ttl_hours: Cache TTL in hours

    Returns:
        DataFrame if cache hit, None otherwise
    """
    cache_path = get_cache_path(ticker, period, interval)
    if is_cache_valid(cache_path, ttl_hours):
        try:
            if PARQUET_AVAILABLE:
                df = pd.read_parquet(cache_path)
            else:
                df = pd.read_pickle(cache_path)
            return df
        except Exception:
            return None
    return None


def write_cache(ticker: str, period: str, interval: str, df: pd.DataFrame) -> bool:
    """
    Write data to cache.

    Args:
        ticker: Stock symbol
        period: Data period
        interval: Data interval
        df: DataFrame to cache

    Returns:
        True if successful, False otherwise
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = get_cache_path(ticker, period, interval)
    try:
        if PARQUET_AVAILABLE:
            df.to_parquet(cache_path)
        else:
            df.to_pickle(cache_path)
        return True
    except Exception as e:
        print(f"Cache write failed for {ticker}: {e}")
        return False


def clear_cache() -> int:
    """
    Clear all cached data.

    Returns:
        Number of files deleted
    """
    count = 0
    if CACHE_DIR.exists():
        for pattern in ["*.parquet", "*.pkl"]:
            for f in CACHE_DIR.glob(pattern):
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
    return count


def get_cache_stats() -> dict:
    """
    Get cache statistics.

    Returns:
        Dictionary with cache stats
    """
    if not CACHE_DIR.exists():
        return {'files': 0, 'size_mb': 0, 'oldest': None, 'newest': None}

    files = list(CACHE_DIR.glob("*.parquet")) + list(CACHE_DIR.glob("*.pkl"))
    if not files:
        return {'files': 0, 'size_mb': 0, 'oldest': None, 'newest': None}

    total_size = sum(f.stat().st_size for f in files)
    mtimes = [datetime.fromtimestamp(f.stat().st_mtime) for f in files]

    return {
        'files': len(files),
        'size_mb': round(total_size / (1024 * 1024), 2),
        'oldest': min(mtimes),
        'newest': max(mtimes)
    }
