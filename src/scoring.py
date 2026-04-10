"""
Scoring engine for the Data-Driven EMA-ADX-ATR Framework.

Calibrated against 2-year weekly backtest data (820 observations).
Scores the ideal entry: a QUIET PULLBACK in a proven trend.

5 factors:
- EMA Proximity (0-20 pts): Sweet spot at 1-2 ATR from EMA20
- ADX Value    (0-30 pts): ADX 25-30 is optimal (direction is noise)
- Volume       (0-25 pts): Low volume = bullish (selling exhaustion)
- Structure    (0-15 pts): EMA stack alignment
- Risk/Reward  (0-10 pts): Risk management gate
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .config import (
    SCORE_WEIGHTS,
    EMA_PROXIMITY_BUCKETS,
    EMA_PROXIMITY_SCORES,
    ADX_VALUE_RANGES,
    ADX_VALUE_SCORES,
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
    STRUCTURE_SCORES,
)

from .regime import VolatilityRegime

@dataclass
class ScoreResult:
    total_score: float
    breakdown: Dict[str, float]
    details: Dict[str, Any]
    regime: str

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
        Factor 1: EMA Proximity Score (0-20 points)

        Measures ABSOLUTE distance from EMA20 in ATR multiples.
        Peak score at 1-2 ATR (the pullback sweet spot).

        Backtest evidence:
          <0.5 ATR:  +1.73%, 53% win (too close — no pullback to buy)
          1-2 ATR:   +4.11%, 67% win (sweet spot — real dip)
          >3 ATR:    overextended
        """
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        atr = self.latest['ATR']

        if pd.isna(ema20) or pd.isna(atr) or atr == 0:
            return 0.0

        distance_atr = abs(price - ema20) / atr

        for i, threshold in enumerate(EMA_PROXIMITY_BUCKETS):
            if distance_atr <= threshold:
                return float(EMA_PROXIMITY_SCORES[i])
        return float(EMA_PROXIMITY_SCORES[-1])

    def calculate_adx_stage_score(self) -> float:
        """
        Factor 2: ADX Value Score (0-30 points)

        Scores ADX based on VALUE only — direction (rising/falling)
        has zero predictive edge per backtest (+2.76% vs +2.77%).

        Backtest evidence:
          ADX 25-30: +5.79%, 74% win (optimal — confirmed trend)
          ADX 15-20: +3.98%, 63% win (emerging trend)
          ADX <15:   -0.01%, 36% win (no trend — avoid)
        """
        adx = self.latest['ADX']
        if pd.isna(adx):
            return 0.0

        for label, (low, high) in ADX_VALUE_RANGES.items():
            if low <= adx < high:
                return float(ADX_VALUE_SCORES[label])

        return 0.0

    def calculate_volume_score(self) -> float:
        """
        Factor 3: Volume Conviction Score (0-25 points) — INVERTED

        Low relative volume = bullish (selling exhaustion, coiled spring).
        High volume = bearish (climax, panic, distribution).

        Backtest evidence:
          Vol <0.5x:  +9.44%, 88% win (strongest signal)
          Vol 0.5-0.8x: +2.93%, 61%
          Vol >1.5x:  +0.74%, 52% (worst signal)

        Sub-components:
          1. Relative Volume INVERTED (0-15): lower = better
          2. Volume Trend INVERTED (0-5): declining = better
          3. Up/Down Ratio (0-5): more buying = good (kept directional)
        """
        # 1. Relative Volume — INVERTED
        vol_curr = self.latest['Volume']
        vol_avg = self.latest['Vol_Avg']
        rv_score = 0.0

        if not pd.isna(vol_avg) and vol_avg > 0:
            rv = vol_curr / vol_avg
            if rv < 0.5:
                rv_score = 15.0
            elif rv < 0.8:
                rv_score = 12.0
            elif rv < 1.0:
                rv_score = 8.0
            elif rv < 1.5:
                rv_score = 5.0
            else:
                rv_score = 2.0

        # 2. Volume Trend — INVERTED (declining = bullish)
        vol_trend_val = self.latest.get('Vol_Trend', 0)
        if pd.isna(vol_trend_val):
            vol_trend_val = 0
        trend_score = 0.0
        if vol_trend_val < -0.1:
            trend_score = 5.0     # Falling — bullish (selling drying up)
        elif vol_trend_val <= 0:
            trend_score = 3.0     # Stable
        else:
            trend_score = 0.0     # Rising — bearish (potential distribution)

        # 3. Up/Down Volume Ratio — kept directional (buying > selling = good)
        ud_ratio = self.latest.get('Vol_UD_Ratio', 0)
        ud_score = 0.0
        if not pd.isna(ud_ratio):
            if ud_ratio > 2.0:
                ud_score = 5.0
            elif ud_ratio >= 1.5:
                ud_score = 3.0

        return rv_score + trend_score + ud_score

    def calculate_structure_score(self) -> float:
        """
        Factor 4: Structure Integrity Score (0-15 points)

        EMA stack alignment (Price > EMA20 > EMA50) is a prerequisite.
        Backtest shows small but real edge for stacked structures.
        """
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        ema50 = self.latest[f'EMA_{EMA_SLOW_PERIOD}']

        if not (price > ema20 > ema50):
            return 0.0

        if len(self.df) < 6:
            return 0.0
        ema50_5ago = self.df[f'EMA_{EMA_SLOW_PERIOD}'].iloc[-6]
        ema50_slope_pct = ((ema50 - ema50_5ago) / ema50_5ago) * 100

        # Consecutive bars above EMA20 (vectorized)
        above = (self.df['Close'] > self.df[f'EMA_{EMA_FAST_PERIOD}']).values
        false_indices = np.where(~above)[0]
        bars_above = len(above) if len(false_indices) == 0 else len(above) - false_indices[-1] - 1

        ema_spread = (ema20 - ema50) / ema50

        if ema50_slope_pct > STRUCTURE_SLOPE_STRONG and bars_above > STRUCTURE_BARS_EXCELLENT:
            return float(STRUCTURE_SCORES['excellent'])
        if ema50_slope_pct > STRUCTURE_SLOPE_POSITIVE and bars_above > STRUCTURE_BARS_GOOD:
            return float(STRUCTURE_SCORES['good'])
        if bars_above > STRUCTURE_BARS_GOOD:
            return float(STRUCTURE_SCORES['valid'])

        # New stack (just formed in last 5 periods)
        prev_ema20 = self.df[f'EMA_{EMA_FAST_PERIOD}'].iloc[-6]
        prev_ema50 = self.df[f'EMA_{EMA_SLOW_PERIOD}'].iloc[-6]
        if prev_ema20 <= prev_ema50:
            return float(STRUCTURE_SCORES['new'])

        if ema_spread < STRUCTURE_EMA_SPREAD_CLOSE:
            return float(STRUCTURE_SCORES['close'])

        return float(STRUCTURE_SCORES['valid'])

    def calculate_risk_reward_score(self) -> float:
        """
        Factor 5: Risk/Reward Score (0-10 points)
        Uses regime-aware stop distance when available, config defaults otherwise.
        """
        price = self.latest['Close']
        ema20 = self.latest[f'EMA_{EMA_FAST_PERIOD}']
        atr = self.latest['ATR']

        if pd.isna(atr) or atr == 0:
            return 0.0

        stop_dist = self.regime_params.stop_distance_atr if self.regime_params else STOP_DIST_ATR_DEFAULT
        stop_price = ema20 - (stop_dist * atr)

        risk = price - stop_price
        if risk <= 0:
            return 0.0

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
