"""
Technical indicators calculation module.
"""
import pandas as pd
import numpy as np

def calculate_ema(df: pd.DataFrame, period: int, column: str = 'Close') -> pd.Series:
    """Calculates Exponential Moving Average."""
    return df[column].ewm(span=period, adjust=False).mean()

def calculate_sma(df: pd.DataFrame, period: int, column: str = 'Close') -> pd.Series:
    """Calculates Simple Moving Average."""
    return df[column].rolling(window=period).mean()

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculates Average True Range (ATR).
    """
    high = df['High']
    low = df['Low']
    close = df['Close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()
    
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    
    # Wilder's Smoothing for ATR
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculates Average Directional Index (ADX) using Wilder's Smoothing.
    """
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    
    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    pos_dm = pd.Series(pos_dm, index=df.index)
    neg_dm = pd.Series(neg_dm, index=df.index)
    
    # Wilder's Smoothing
    alpha = 1/period
    tr_smooth = tr.ewm(alpha=alpha, adjust=False).mean()
    pos_dm_smooth = pos_dm.ewm(alpha=alpha, adjust=False).mean()
    neg_dm_smooth = neg_dm.ewm(alpha=alpha, adjust=False).mean()
    
    # Directional Indicators
    pos_di = 100 * (pos_dm_smooth / tr_smooth)
    neg_di = 100 * (neg_dm_smooth / tr_smooth)
    
    # ADX
    dx = 100 * (abs(pos_di - neg_di) / (pos_di + neg_di))
    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    
    return adx

def calculate_volume_price_correlation(df: pd.DataFrame, period: int = 10) -> pd.Series:
    """
    Calculates correlation between Volume and Absolute Price Change.
    """
    price_change_abs = df['Close'].diff().abs()
    return df['Volume'].rolling(window=period).corr(price_change_abs)

def calculate_up_down_volume_ratio(df: pd.DataFrame, period: int = 5) -> pd.Series:
    """
    Calculates Ratio of Up Volume to Down Volume over period.
    """
    close_change = df['Close'].diff()
    
    up_vol = pd.Series(0.0, index=df.index)
    down_vol = pd.Series(0.0, index=df.index)
    
    up_vol[close_change > 0] = df['Volume'][close_change > 0]
    down_vol[close_change < 0] = df['Volume'][close_change < 0]
    
    # Rolling sum
    up_sum = up_vol.rolling(window=period).sum()
    down_sum = down_vol.rolling(window=period).sum()
    
    # Avoid division by zero
    ratio = up_sum / down_sum.replace(0, 1)
    return ratio

def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates all necessary indicators for the strategy and appends them to the DataFrame.
    """
    df = df.copy()
    
    # Import config here to avoid circular dependency if config imports this later (though it acts as base)
    # Using hardcoded defaults or safe imports is better.
    # We will assume config values are passed or used defaults.
    from .config import EMA_FAST_PERIOD, EMA_SLOW_PERIOD, ATR_PERIOD, ADX_PERIOD, VOLUME_MA_PERIOD
    
    df[f'EMA_{EMA_FAST_PERIOD}'] = calculate_ema(df, EMA_FAST_PERIOD)
    df[f'EMA_{EMA_SLOW_PERIOD}'] = calculate_ema(df, EMA_SLOW_PERIOD)
    df['ATR'] = calculate_atr(df, ATR_PERIOD)
    df['ADX'] = calculate_adx(df, ADX_PERIOD)
    df['Vol_Avg'] = calculate_sma(df, VOLUME_MA_PERIOD, column='Volume')
    
    # Advanced Volume Indicators
    df['Vol_VPC'] = calculate_volume_price_correlation(df)
    df['Vol_UD_Ratio'] = calculate_up_down_volume_ratio(df)
    df['Vol_Trend'] = calculate_volume_trend(df)
    
    return df

def calculate_volume_trend(df: pd.DataFrame, period: int = 4) -> pd.Series:
    """
    Calculates the trend of volume over the last N periods.
    Returns the slope of the linear regression line for volume.
    """
    if len(df) < period:
        return pd.Series(0.0, index=df.index)

    if period == 4:
        # Optimized vectorized calculation for default period=4
        v = df['Volume']
        v0, v1, v2, v3 = v.shift(3), v.shift(2), v.shift(1), v
        sum_y = v0 + v1 + v2 + v3
        sum_xy = 0*v0 + 1*v1 + 2*v2 + 3*v3
        slope = (4 * sum_xy - 6 * sum_y) / 20.0
        return slope.fillna(0.0)

    # Helper for rolling slope
    def calc_slope(y):
        n = len(y)
        if n < 2: return 0.0
        x = np.arange(n)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_xx = np.sum(x * x)
        
        denom = (n * sum_xx - sum_x * sum_x)
        if denom == 0: return 0.0
        
        slope = (n * sum_xy - sum_x * sum_y) / denom
        return slope

    # Use raw=True for performance with numpy arrays
    res = df['Volume'].rolling(window=period).apply(calc_slope, raw=True)
    return res.fillna(0.0)
