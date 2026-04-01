"""
Tests for the Scoring Engine.
"""
import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scoring import EntryScorer
from src.config import EMA_FAST_PERIOD, EMA_SLOW_PERIOD

class TestEntryScorer(unittest.TestCase):
    
    def setUp(self):
        # Create a basic DataFrame structure
        dates = pd.date_range(start='2024-01-01', periods=100)
        self.df = pd.DataFrame(index=dates)
        
        # Populate with defaults that allow modification
        self.df['Open'] = 100.0
        self.df['High'] = 105.0
        self.df['Low'] = 95.0
        self.df['Close'] = 100.0
        self.df['Volume'] = 1000000
        
        # Indicators
        self.df[f'EMA_{EMA_FAST_PERIOD}'] = 100.0
        self.df[f'EMA_{EMA_SLOW_PERIOD}'] = 90.0
        self.df['ATR'] = 2.0
        self.df['ADX'] = 30.0
        self.df['Vol_Avg'] = 1000000
        
    def test_ema_proximity_optimal(self):
        # Price = 100, EMA20 = 100, ATR = 2
        # Distance = 0 / 2 = 0x ATR -> Score 25
        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_ema_proximity_score(), 25.0)

    def test_ema_proximity_good(self):
        # Price = 102, EMA20 = 100, ATR = 2
        # Distance = 2 / 2 = 1.0x ATR -> Score 20
        self.df.loc[self.df.index[-1], 'Close'] = 102.0
        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_ema_proximity_score(), 20.0)

    def test_ema_proximity_poor(self):
        # Price = 106, EMA20 = 100, ATR = 2
        # Distance = 6 / 2 = 3.0x ATR -> Score 0
        self.df.loc[self.df.index[-1], 'Close'] = 106.0
        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_ema_proximity_score(), 0.0)

    def test_adx_rising_optimal(self):
        # ADX = 27, rising
        self.df['ADX'] = 25.0 # Historical
        self.df.loc[self.df.index[-6], 'ADX'] = 24.0
        self.df.loc[self.df.index[-1], 'ADX'] = 27.0 # Slope +3
        
        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_adx_stage_score(), 25.0)
        
    def test_volume_score_strong(self):
        # Vol > 2x -> rv_score=10, Vol_Trend=0 -> trend_score=3 (stable), no Vol_UD_Ratio -> 0
        self.df.loc[self.df.index[-1], 'Volume'] = 2500000 # 2.5x
        self.df.loc[self.df.index[-1], 'Vol_Avg'] = 1000000
        self.df.loc[self.df.index[-1], 'Close'] = 104.0
        self.df.loc[self.df.index[-2], 'Close'] = 100.0

        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_volume_score(), 13.0)  # 10 + 3 + 0

    def test_volume_score_full(self):
        # Test with all volume sub-scores populated
        self.df.loc[self.df.index[-1], 'Volume'] = 2500000
        self.df.loc[self.df.index[-1], 'Vol_Avg'] = 1000000
        self.df['Vol_Trend'] = 1.0  # Rising
        self.df['Vol_UD_Ratio'] = 2.5  # Strong up/down ratio

        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_volume_score(), 20.0)  # 10 + 5 + 5
        
    def test_structure_score_perfect(self):
        # Stack valid, EMA50 rising > 1%, Bars > 5
        self.df[f'EMA_{EMA_FAST_PERIOD}'] = 100.0
        self.df[f'EMA_{EMA_SLOW_PERIOD}'] = 90.0
        self.df['Close'] = 105.0 # Above EMA20
        
        # Make EMA50 rise
        self.df.loc[self.df.index[-6], f'EMA_{EMA_SLOW_PERIOD}'] = 88.0 # 2/88 = 2.2% rise
        
        scorer = EntryScorer(self.df)
        # Note: logic loops to find bars above.
        # Since we just set Close=105 everywhere but EMA20=100 everywhere, 100 bars above.
        self.assertEqual(scorer.calculate_structure_score(), 20.0)

    def test_risk_reward_score(self):
        # Regime: All ATR=2.0 → LOW_VOLATILITY (percentile=0), stop_distance_atr=1.5
        # Target multiplier = 4.0 (from config)

        # Case 1: Price=100, EMA20=98, ATR=2
        # Stop = 98 - (1.5*2) = 95, Risk = 5, Reward = 4*2 = 8, RR = 1.6 → score 3
        self.df.loc[self.df.index[-1], 'Close'] = 100.0
        self.df.loc[self.df.index[-1], f'EMA_{EMA_FAST_PERIOD}'] = 98.0
        self.df.loc[self.df.index[-1], 'ATR'] = 2.0

        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_risk_reward_score(), 3.0)

        # Case 2: Price=100, EMA20=100, ATR=2
        # Stop = 100 - (1.5*2) = 97, Risk = 3, Reward = 8, RR = 2.67 → score 6
        self.df.loc[self.df.index[-1], f'EMA_{EMA_FAST_PERIOD}'] = 100.0

        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_risk_reward_score(), 6.0)

if __name__ == '__main__':
    unittest.main()
