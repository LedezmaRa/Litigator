"""
Scoring engine for the Optimized EMA-ADX-ATR Framework.

Calculates entry scores based on 5 factors:
- EMA Proximity (0-25 pts)
- ADX Stage (0-25 pts)
- Volume Conviction (0-20 pts)
- Structure (0-20 pts)
- Risk/Reward (0-10 pts)
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .config import (
    SCORE_WEIGHTS,
    EMA_PROXIMITY_BUCKETS,
    EMA_PROXIMITY_SCORES,
    ADX_SCORE_RANGES,
    ADX_RANGE_SCORES,
    ADX_RISING_LOOKBACK,
    STOP_DIST_ATR_DEFAULT,
    TARGET_ATR_MULTIPLIER,
    RR_SCORE_THRESHOLDS,
    RR_SCORES,
    EMA_FAST_PERIOD,
    EMA_SLOW_PERIOD,
    STRUCTURE_SLOPE_STRONG,
    STRUCTURE_SLOPE_POSITIVE,
    STRUCTURE_BARS_EXCELLENT,
    STRUCTURE_BARS_GOOD,
    STRUCTURE_EMA_SPREAD_CLOSE,
)

from .regime import VolatilityRegime

@dataclass
class ScoreResult:
    total_score: float
    breakdown: Dict[str, float]
    details: Dict[str, Any]
    regime: str  # Added

class EntryScorer:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.latest = df.iloc[-1]
        self.prev = df.iloc[-2]
        
        # Calculate Regime
        self.regime_logic = VolatilityRegime(df)
        self.regime_params = self.regime_logic.get_regime()
    
    def calculate_ema_proximity_score(self) -> float:
        """
        Factor 1: EMA Proximity Score (0-25 points)
        Measures distance from EMA20 in ATR multiples using config buckets.
        """
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        atr = self.latest['ATR']

        if pd.isna(ema20) or pd.isna(atr) or atr == 0:
            return 0.0

        distance_atr = abs(price - ema20) / atr

        # Price below EMA20 by more than the tightest bucket = overextended down
        if price < ema20 and distance_atr >= EMA_PROXIMITY_BUCKETS[0]:
            return 0.0

        for i, threshold in enumerate(EMA_PROXIMITY_BUCKETS):
            if distance_atr <= threshold:
                return float(EMA_PROXIMITY_SCORES[i])
        return float(EMA_PROXIMITY_SCORES[-1])

    def calculate_adx_stage_score(self) -> float:
        """
        Factor 2: ADX Stage Score (0-25 points)
        Uses ADX_RISING_LOOKBACK to determine trend direction.
        """
        adx = self.latest['ADX']
        if pd.isna(adx): return 0.0

        min_len = ADX_RISING_LOOKBACK + 1
        if len(self.df) < min_len: return 0.0
        adx_prev = self.df['ADX'].iloc[-(ADX_RISING_LOOKBACK + 1)]
        is_rising = adx > adx_prev

        for label, (low, high) in ADX_SCORE_RANGES.items():
            if low <= adx < high:
                if label in ('caution', 'late'):
                    return float(ADX_RANGE_SCORES[label])
                if is_rising:
                    return float(ADX_RANGE_SCORES[label])
                return 0.0

        return 0.0

    def calculate_volume_score(self) -> float:
        """
        Factor 3: Volume Conviction Score (0-20 points)
        Framework 2.0:
        1. Rel Vol (0-10): >2.0=10, 1.5-2.0=8, 1.2-1.5=6, 1.0-1.2=4
        2. Vol Trend (0-5): Rising=5, Stable=3, Falling=0
        3. U/D Ratio (0-5): >2.0=5, 1.5-2.0=3, <1.5=0
        """
        # 1. Relative Volume
        vol_curr = self.latest['Volume']
        vol_avg = self.latest['Vol_Avg']
        rv_score = 0.0
        
        if not pd.isna(vol_avg) and vol_avg > 0:
            rv = vol_curr / vol_avg
            if rv > 2.0: rv_score = 10.0
            elif rv >= 1.5: rv_score = 8.0
            elif rv >= 1.2: rv_score = 6.0
            elif rv >= 1.0: rv_score = 4.0
            
        # 2. Volume Trend (Slope of last 4 weeks)
        # We calculated 'Vol_Trend' in indicators
        vol_trend_val = self.latest.get('Vol_Trend', 0)
        trend_score = 0.0
        if vol_trend_val > 0: trend_score = 5.0 # Rising
        elif vol_trend_val > -0.1: trend_score = 3.0 # Stable (allow slight drift)
        else: trend_score = 0.0 # Declining
            
        # 3. Up/Down Volume Ratio
        ud_ratio = self.latest.get('Vol_UD_Ratio', 0)
        ud_score = 0.0
        if not pd.isna(ud_ratio):
            if ud_ratio > 2.0: ud_score = 5.0
            elif ud_ratio >= 1.5: ud_score = 3.0
            
        return rv_score + trend_score + ud_score

    def calculate_structure_score(self) -> float:
        """
        Factor 4: Structure Integrity Score (0-20 points)
        Components: EMA stack, EMA50 slope, Bars above EMA20.
        """
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        ema50 = self.latest[f'EMA_{EMA_SLOW_PERIOD}']

        if not (price > ema20 > ema50):
            return 0.0

        if len(self.df) < 6: return 0.0
        ema50_5ago = self.df[f'EMA_{EMA_SLOW_PERIOD}'].iloc[-6]
        ema50_slope_pct = ((ema50 - ema50_5ago) / ema50_5ago) * 100

        # Consecutive bars above EMA20 (vectorized)
        above = (self.df['Close'] > self.df[f'EMA_{EMA_FAST_PERIOD}']).values
        false_indices = np.where(~above)[0]
        bars_above = len(above) if len(false_indices) == 0 else len(above) - false_indices[-1] - 1

        ema_spread = (ema20 - ema50) / ema50

        if ema50_slope_pct > STRUCTURE_SLOPE_STRONG and bars_above > STRUCTURE_BARS_EXCELLENT:
            return 20.0
        if ema50_slope_pct > STRUCTURE_SLOPE_POSITIVE and bars_above > STRUCTURE_BARS_GOOD:
            return 15.0
        if bars_above > STRUCTURE_BARS_GOOD:
            return 10.0

        # New stack (just formed in last 5 periods)
        prev_ema20 = self.df[f'EMA_{EMA_FAST_PERIOD}'].iloc[-6]
        prev_ema50 = self.df[f'EMA_{EMA_SLOW_PERIOD}'].iloc[-6]
        if prev_ema20 <= prev_ema50:
            return 10.0

        if ema_spread < STRUCTURE_EMA_SPREAD_CLOSE:
            return 5.0

        return 10.0

    def calculate_risk_reward_score(self) -> float:
        """
        Factor 5: Risk/Reward Score (0-10 points)
        Uses regime-aware stop distance when available, config defaults otherwise.
        """
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        atr = self.latest['ATR']

        if pd.isna(atr) or atr == 0: return 0.0

        stop_dist = self.regime_params.stop_distance_atr if self.regime_params else STOP_DIST_ATR_DEFAULT
        stop_price = ema20 - (stop_dist * atr)

        risk = price - stop_price
        if risk <= 0: return 0.0

        reward = TARGET_ATR_MULTIPLIER * atr
        rr_ratio = reward / risk

        for i, threshold in enumerate(RR_SCORE_THRESHOLDS):
            if rr_ratio > threshold:
                return float(RR_SCORES[i])
        return float(RR_SCORES[-1])

    def score(self) -> ScoreResult:
        """Calculates the total score and breakdown."""
        s1 = self.calculate_ema_proximity_score()
        s2 = self.calculate_adx_stage_score()
        s3 = self.calculate_volume_score()
        s4 = self.calculate_structure_score()
        s5 = self.calculate_risk_reward_score()
        
        total = s1 + s2 + s3 + s4 + s5
        
        return ScoreResult(
            total_score=total,
            breakdown={
                'ema_proximity': s1,
                'adx_stage': s2,
                'volume_conviction': s3,
                'structure': s4,
                'risk_reward': s5
            },
            details={
                'price': self.latest['Close'],
                'atr': self.latest['ATR'],
                'adx': self.latest['ADX'],
                'ema20': self.latest[f'EMA_{EMA_FAST_PERIOD}'],
                'ema50': self.latest[f'EMA_{EMA_SLOW_PERIOD}']
            },
            regime=self.regime_params.name
        )
