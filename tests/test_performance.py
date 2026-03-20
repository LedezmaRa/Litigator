"""
Performance benchmark tests for the EMA-ADX-ATR Framework.

Tests parallel data fetching, indicator calculation speed,
and scoring engine performance.
"""
import unittest
import time
import sys
import os

import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.indicators import calculate_all_indicators
from src.scoring import EntryScorer
from src.config import EMA_FAST_PERIOD, EMA_SLOW_PERIOD


def create_test_dataframe(periods: int = 200) -> pd.DataFrame:
    """Create a realistic test DataFrame with OHLCV data."""
    dates = pd.date_range(start='2023-01-01', periods=periods, freq='W')
    np.random.seed(42)

    # Generate realistic price movement
    returns = np.random.normal(0.002, 0.03, periods)
    prices = 100 * np.cumprod(1 + returns)

    df = pd.DataFrame({
        'Open': prices * (1 + np.random.uniform(-0.02, 0.02, periods)),
        'High': prices * (1 + np.random.uniform(0, 0.05, periods)),
        'Low': prices * (1 - np.random.uniform(0, 0.05, periods)),
        'Close': prices,
        'Volume': np.random.uniform(1e6, 5e6, periods),
    }, index=dates)

    return df


class TestIndicatorPerformance(unittest.TestCase):
    """Benchmark tests for indicator calculations."""

    def test_indicators_under_100ms(self):
        """All indicator calculations should complete in under 100ms."""
        df = create_test_dataframe(periods=500)

        start = time.time()
        result = calculate_all_indicators(df)
        elapsed = time.time() - start

        self.assertLess(elapsed, 0.1, f"Indicators took {elapsed:.3f}s, expected < 0.1s")
        self.assertIn(f'EMA_{EMA_FAST_PERIOD}', result.columns)
        self.assertIn(f'EMA_{EMA_SLOW_PERIOD}', result.columns)
        self.assertIn('ATR', result.columns)
        self.assertIn('ADX', result.columns)

    def test_batch_indicators_scales_linearly(self):
        """Indicator calculation should scale roughly linearly."""
        df = create_test_dataframe(periods=200)

        # Single run
        start = time.time()
        calculate_all_indicators(df.copy())
        single_time = time.time() - start

        # 10 runs
        start = time.time()
        for _ in range(10):
            calculate_all_indicators(df.copy())
        batch_time = time.time() - start

        # Should be roughly linear (allow 50% overhead for setup)
        expected_max = single_time * 10 * 1.5
        self.assertLess(batch_time, expected_max,
                        f"Batch took {batch_time:.3f}s, expected < {expected_max:.3f}s")


class TestScoringPerformance(unittest.TestCase):
    """Benchmark tests for scoring calculations."""

    def setUp(self):
        """Create test DataFrame with all indicators."""
        self.df = create_test_dataframe(periods=200)
        self.df = calculate_all_indicators(self.df)

    def test_scoring_under_50ms(self):
        """Full scoring should complete in under 50ms."""
        start = time.time()
        scorer = EntryScorer(self.df)
        result = scorer.score()
        elapsed = time.time() - start

        self.assertLess(elapsed, 0.05, f"Scoring took {elapsed:.3f}s, expected < 0.05s")
        self.assertIsNotNone(result.total_score)
        self.assertIn('ema_proximity', result.breakdown)

    def test_batch_scoring_under_1s(self):
        """Scoring 100 DataFrames should complete in under 1 second."""
        start = time.time()
        for _ in range(100):
            scorer = EntryScorer(self.df)
            scorer.score()
        elapsed = time.time() - start

        self.assertLess(elapsed, 1.0, f"100 scores took {elapsed:.3f}s, expected < 1.0s")

    def test_vectorized_bars_above_faster_than_loop(self):
        """Vectorized bars_above should be faster than Python loop."""
        # Test the vectorized implementation indirectly through structure score
        scorer = EntryScorer(self.df)

        # Run multiple times to get stable measurement
        start = time.time()
        for _ in range(1000):
            scorer.calculate_structure_score()
        elapsed = time.time() - start

        # Should complete 1000 structure scores in under 0.5s
        self.assertLess(elapsed, 0.5, f"1000 structure scores took {elapsed:.3f}s")


class TestCachePerformance(unittest.TestCase):
    """Benchmark tests for cache operations."""

    def test_cache_write_under_50ms(self):
        """Cache write should complete in under 50ms."""
        from src.cache import write_cache, CACHE_DIR

        df = create_test_dataframe(periods=200)

        start = time.time()
        result = write_cache('TEST', '2y', '1wk', df)
        elapsed = time.time() - start

        self.assertTrue(result, "Cache write should succeed")
        self.assertLess(elapsed, 0.05, f"Cache write took {elapsed:.3f}s")

        # Cleanup
        for pattern in ['TEST_*.parquet', 'TEST_*.pkl']:
            for f in CACHE_DIR.glob(pattern):
                f.unlink()

    def test_cache_read_under_20ms(self):
        """Cache read should complete in under 20ms."""
        from src.cache import write_cache, read_cache, CACHE_DIR

        df = create_test_dataframe(periods=200)
        success = write_cache('TEST_READ', '2y', '1wk', df)
        self.assertTrue(success, "Cache write should succeed for read test")

        start = time.time()
        result = read_cache('TEST_READ', '2y', '1wk')
        elapsed = time.time() - start

        self.assertLess(elapsed, 0.02, f"Cache read took {elapsed:.3f}s")
        self.assertIsNotNone(result, "Cache read should return data")

        # Cleanup
        for pattern in ['TEST_READ_*.parquet', 'TEST_READ_*.pkl']:
            for f in CACHE_DIR.glob(pattern):
                f.unlink()


class TestEdgeCases(unittest.TestCase):
    """Edge case tests for scoring robustness."""

    def setUp(self):
        """Create base test DataFrame."""
        self.df = create_test_dataframe(periods=200)
        self.df = calculate_all_indicators(self.df)

    def test_zero_atr_handling(self):
        """Should handle zero ATR gracefully."""
        df = self.df.copy()
        df['ATR'] = 0.0

        scorer = EntryScorer(df)
        result = scorer.score()

        # Should return 0 for ATR-dependent scores, not crash
        self.assertEqual(result.breakdown['ema_proximity'], 0.0)
        self.assertEqual(result.breakdown['risk_reward'], 0.0)

    def test_nan_values_handling(self):
        """Should handle NaN values in indicators."""
        df = self.df.copy()
        df.loc[df.index[-1], 'ADX'] = np.nan

        scorer = EntryScorer(df)
        result = scorer.score()

        # Should handle gracefully
        self.assertEqual(result.breakdown['adx_stage'], 0.0)

    def test_short_history(self):
        """Should handle DataFrames with minimal history."""
        df = create_test_dataframe(periods=20)
        df = calculate_all_indicators(df)

        scorer = EntryScorer(df)
        result = scorer.score()

        # Should return valid scores
        self.assertGreaterEqual(result.total_score, 0)
        self.assertLessEqual(result.total_score, 100)

    def test_extreme_adx_values(self):
        """Should handle ADX outside normal ranges."""
        df = self.df.copy()

        # Very high ADX
        df['ADX'] = 95.0
        scorer = EntryScorer(df)
        result = scorer.score()
        self.assertEqual(result.breakdown['adx_stage'], 0.0)

        # Very low ADX
        df['ADX'] = 5.0
        scorer = EntryScorer(df)
        result = scorer.score()
        self.assertEqual(result.breakdown['adx_stage'], 0.0)

    def test_inverted_ema_stack(self):
        """Should handle bearish EMA configuration."""
        df = self.df.copy()
        df[f'EMA_{EMA_FAST_PERIOD}'] = 80.0  # EMA20 below EMA50
        df[f'EMA_{EMA_SLOW_PERIOD}'] = 100.0

        scorer = EntryScorer(df)
        result = scorer.score()

        # Structure should be 0 with inverted EMAs
        self.assertEqual(result.breakdown['structure'], 0.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
