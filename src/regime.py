"""
Volatility Regime Logic.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Literal

from .config import REGIME_PERCENTILES

@dataclass
class RegimeParams:
    name: Literal["LOW_VOLATILITY", "NORMAL_VOLATILITY", "HIGH_VOLATILITY"]
    extension_limit_atr: float
    stop_distance_atr: float
    adx_threshold: int

class VolatilityRegime:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        
    def get_regime(self) -> RegimeParams:
        """
        Determines the current volatility regime based on ATR percentile rank.
        """
        if 'ATR' not in self.df.columns or len(self.df) < 60:
            # Fallback if not enough data
            return RegimeParams(
                name="NORMAL_VOLATILITY",
                extension_limit_atr=2.0,
                stop_distance_atr=2.0,
                adx_threshold=25
            )
            
        current_atr = self.df['ATR'].iloc[-1]
        
        # Calculate percentile vs last 60 days
        atr_window = self.df['ATR'].iloc[-60:]
        percentile = (atr_window < current_atr).mean() * 100
        
        if percentile < REGIME_PERCENTILES['low']: # < 30
            return RegimeParams(
                name="LOW_VOLATILITY",
                extension_limit_atr=1.5,
                stop_distance_atr=1.5,
                adx_threshold=20
            )
        elif percentile < REGIME_PERCENTILES['high']: # < 70
            return RegimeParams(
                name="NORMAL_VOLATILITY",
                extension_limit_atr=2.0,
                stop_distance_atr=2.0,
                adx_threshold=25
            )
        else:
            return RegimeParams(
                name="HIGH_VOLATILITY",
                extension_limit_atr=2.5,
                stop_distance_atr=2.5,
                adx_threshold=30
            )
