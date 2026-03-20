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
    EMA_PROXIMITY_THRESHOLDS,
    ADX_THRESHOLDS,
    EMA_FAST_PERIOD,
    EMA_SLOW_PERIOD
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
        Formula: (Price - EMA20) / ATR
        """
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        atr = self.latest['ATR']
        
        if pd.isna(ema20) or pd.isna(atr) or atr == 0:
            return 0.0
            
        distance_atr = (price - ema20) / atr
        
        # NOTE on Regime: "Extension limit" changes by regime.
        # But the 0-25 SCORING BUCKETS are hardcoded in the doc?
        # Check doc PART 4 > OPTIMIZATION #2 > "LOW VOLATILITY REGIME uses Optimal < 1.0x ATR"
        # The doc has TWO sections:
        # 1. OPTIMIZATION #1: EXPLICIT ENTRY SCORING with fixed buckets (0-0.5, 0.5-1.0...)
        # 2. OPTIMIZATION #2: DYNAMIC ATR THRESHOLDS defines "Optimal/Good/Caution" zones per regime.
        #
        # Conflict? The Scoring System (Opt #1) seems to be the primary "Entry Score".
        # Opt #2 seems to be for WARNING/FILTERS or Risk Management.
        # "Filter based on score... (Score > 75)".
        #
        # However, let's adapt the SCORING buckets if the user wants "Complete System".
        # If High Volatility, 2.0x ATR might be "Optimal" (according to Opt #2).
        # But Opt #1 says >2.5x is 0 points.
        #
        # Let's keep Opt #1 buckets FIXED for consistency with the rubric, 
        # BUT update Risk/Reward and Stop Distance using Regime params.
        # AND maybe cap the score if "Violates Extension Limit"?
        #
        # Let's stick to Opt #1 for Scoring. Use Opt #2 for Stop Distance logic in Risk/Reward.
        
        if distance_atr < 0:
            distance_abs = abs(distance_atr)
            if distance_abs < 0.5:
                return 25.0
            return 0.0 
            
        if distance_atr <= 0.5: return 25.0
        if distance_atr <= 1.0: return 20.0
        if distance_atr <= 1.5: return 15.0
        if distance_atr <= 2.0: return 10.0
        if distance_atr <= 2.5: return 5.0
        return 0.0

    def calculate_adx_stage_score(self) -> float:
        """
        Factor 2: ADX Stage Score (0-25 points)
        Framework 2.0:
        - 25-30 Rising: 25 pts (Optimal)
        - 30-35 Rising: 20 pts (Good)
        - 20-25 Rising: 15 pts (Acceptable - Early)
        - 35-40 Any:    10 pts (Caution)
        - 40-50:        5 pts (Late)
        - >50 or <20:   0 pts
        """
        adx = self.latest['ADX']
        if pd.isna(adx): return 0.0

        # Determine if rising (compare to 4 weeks ago as per spec)
        if len(self.df) < 5: return 0.0
        adx_4ago = self.df['ADX'].iloc[-5]
        is_rising = adx > adx_4ago

        if 25 <= adx < 30 and is_rising: return 25.0
        if 30 <= adx < 35 and is_rising: return 20.0
        if 20 <= adx < 25 and is_rising: return 15.0
        if 35 <= adx < 40: return 10.0
        if 40 <= adx < 50: return 5.0
        
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
        Components: EMA stack, EMA50 slope, Bars above EMA20
        """
        # 1. EMA Stack: Price > EMA20 > EMA50
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        ema50 = self.latest[f'EMA_{EMA_SLOW_PERIOD}']
        
        if not (price > ema20 > ema50):
            # Check if it's just a pullback (Price < EMA20 but EMA20 > EMA50)
            if ema20 > ema50:
                 # "No clean stack" usually means EMAs crossed wrong way.
                 # If price dipped, maybe weak.
                 pass
            return 0.0
            
        # 2. EMA50 Slope
        if len(self.df) < 6: return 0.0
        ema50_5ago = self.df[f'EMA_{EMA_SLOW_PERIOD}'].iloc[-6]
        # % change of EMA50 over 5 days
        ema50_slope_pct = ((ema50 - ema50_5ago) / ema50_5ago) * 100
        
        # 3. Bars above EMA20 (vectorized)
        # Count consecutive closes > EMA20 from the end
        above = (self.df['Close'] > self.df[f'EMA_{EMA_FAST_PERIOD}']).values
        false_indices = np.where(~above)[0]
        if len(false_indices) == 0:
            bars_above = len(above)
        else:
            bars_above = len(above) - false_indices[-1] - 1
        
        # Scoring:
        # Stack + EMA50 > 1% + >5 bars: 20
        # Stack + EMA50 > 0 + >3 bars: 15
        # Stack + EMA50 flat + >3 bars: 10
        # New Stack: 10
        # Stack but EMAs close: 5
        
        # "EMAs close" definition? < 0.5% diff?
        ema_spread = (ema20 - ema50) / ema50
        
        if ema50_slope_pct > 1.0 and bars_above > 5: return 20.0
        if ema50_slope_pct > 0.0 and bars_above > 3: return 15.0
        if bars_above > 3: return 10.0 # Flat slope implicit
        
        # New stack (just formed)
        # Check if 5 days ago it wasn't stacked
        prev_ema20 = self.df[f'EMA_{EMA_FAST_PERIOD}'].iloc[-6]
        prev_ema50 = self.df[f'EMA_{EMA_SLOW_PERIOD}'].iloc[-6]
        was_stacked = prev_ema20 > prev_ema50
        
        if not was_stacked: return 10.0 # Newly formed
        
        if ema_spread < 0.01: return 5.0 # Close
        
        return 10.0 # Default fallback for valid stack

    def calculate_risk_reward_score(self) -> float:
        """
        Factor 5: Risk/Reward Score (0-10 points)
        Framework 2.0:
        - Stop: EMA20 - (1.5 to 2.0 * ATR)
        - Target: Entry + (4 * ATR) (Moderate)
        - Score: >4.0=10, 3-4=8, 2-3=6, 1.5-2=3, <1.5=0
        """
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        atr = self.latest['ATR']
        
        if pd.isna(atr) or atr == 0: return 0.0
        
        # Use Conservative Stop (2.0 ATR) for calculation safety
        # Framework says 1.5-2.0. Let's average to 1.75 for scoring estimation
        stop_dist_atr = 1.75 
        stop_price = ema20 - (stop_dist_atr * atr)
        
        risk = price - stop_price
        if risk <= 0: return 0.0 # Price is below stop (already broken structure)
        
        # Target (Moderate: 4x ATR)
        reward = 4.0 * atr
        
        rr_ratio = reward / risk
        
        if rr_ratio > 4.0: return 10.0
        if rr_ratio > 3.0: return 8.0
        if rr_ratio > 2.0: return 6.0
        if rr_ratio > 1.5: return 3.0
        return 0.0

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
