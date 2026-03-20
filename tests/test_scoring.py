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
        # Vol > 2x, Price > 3%
        self.df.loc[self.df.index[-1], 'Volume'] = 2500000 # 2.5x
        self.df.loc[self.df.index[-1], 'Vol_Avg'] = 1000000
        self.df.loc[self.df.index[-1], 'Close'] = 104.0 # 4% up from 100
        self.df.loc[self.df.index[-2], 'Close'] = 100.0
        
        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_volume_score(), 20.0)
        
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
        # Price = 100, EMA20 = 98, ATR = 2
        # Stop = 98 - (1.5*2) = 95
        # Risk = 100 - 95 = 5
        # Reward = 5 * 2 = 10
        # RR = 2.0 -> Score 3 (1.5 - 2.0 is 3 points? No, >2 is 6)
        # Logic: ratio > 2.0 gives 6. ratio 2.0 gives 3?
        # Code: if rr > 2.0: 6. Else if rr > 1.5: 3.
        # Here RR = 2.0. So 3 points.
        
        self.df.loc[self.df.index[-1], 'Close'] = 100.0
        self.df.loc[self.df.index[-1], f'EMA_{EMA_FAST_PERIOD}'] = 98.0
        self.df.loc[self.df.index[-1], 'ATR'] = 2.0
        
        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_risk_reward_score(), 3.0) 
        
        # Test > 4
        # Needs Risk < 2.5 (since Reward=10)
        # Stop = EMA20-3. Need Price-Stop < 2.5.
        # Price 100. Stop > 97.5.
        
        # EMA20 = 99.5. Stop = 99.5 - 3 = 96.5. Risk = 3.5. Ratio 2.8.
        # We need smaller risk.
        # Price near Stop?
        # Say Price = EMA20 = 100.
        # Stop = 100 - 3 = 97. Risk 3. Reward 10. Ratio 3.3. Score 8.
        
        self.df.loc[self.df.index[-1], 'Close'] = 100.0
        self.df.loc[self.df.index[-1], f'EMA_{EMA_FAST_PERIOD}'] = 100.0
        self.df.loc[self.df.index[-1], 'ATR'] = 2.0
        # Stop = 97. Risk 3. Reward 10. Ratio 3.33. Score 8.
        # Wait, calculate_risk_reward_score:
        # Stop = ema20 - 1.5*atr = 100 - 3 = 97.
        # Risk = 100 - 97 = 3.
        # Reward = 5 * 2 = 10.
        # Ratio = 3.33.
        # > 3.0: Score 8.
        
        scorer = EntryScorer(self.df)
        self.assertEqual(scorer.calculate_risk_reward_score(), 8.0)

if __name__ == '__main__':
    unittest.main()
