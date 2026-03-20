"""
Configuration settings for the Optimized EMA-ADX-ATR Framework.
"""

# Moving Averages
# Moving Averages (Weekly)
EMA_FAST_PERIOD = 20
EMA_SLOW_PERIOD = 50

# Volatility (Weekly)
ATR_PERIOD = 14

# Trend Strength (Weekly)
ADX_PERIOD = 14

# Volume (Weekly)
VOLUME_MA_PERIOD = 20

# Scoring Weights (Total 100)
SCORE_WEIGHTS = {
    'ema_proximity': 25,
    'adx_stage': 25,
    'volume_conviction': 20,
    'structure': 20,
    'risk_reward': 10
}

# =============================================================================
# FACTOR 1: EMA Proximity Scoring (0-25 pts)
# =============================================================================
# Distance thresholds (in ATR multiples) and corresponding scores
EMA_PROXIMITY_BUCKETS = [0.5, 1.0, 1.5, 2.0, 2.5]
EMA_PROXIMITY_SCORES = [25, 20, 15, 10, 5, 0]  # Last value is default for > 2.5

# Legacy format (kept for backwards compatibility)
EMA_PROXIMITY_THRESHOLDS = {
    0.5: 25,
    1.0: 20,
    1.5: 15,
    2.0: 10,
    2.5: 5
}

# =============================================================================
# FACTOR 2: ADX Stage Scoring (0-25 pts)
# =============================================================================
ADX_SCORE_RANGES = {
    'optimal': (25, 30),      # 25 pts when rising
    'good': (30, 35),         # 20 pts when rising
    'acceptable': (20, 25),   # 15 pts when rising
    'caution': (35, 40),      # 10 pts (any direction)
    'late': (40, 50),         # 5 pts
}
ADX_RANGE_SCORES = {
    'optimal': 25,
    'good': 20,
    'acceptable': 15,
    'caution': 10,
    'late': 5
}

# Legacy format
ADX_THRESHOLDS = {
    'optimal_low': 25,
    'optimal_high': 30,
    'good_high': 35,
    'caution_high': 40,
    'extreme': 50
}

# ADX lookback for "rising" determination
ADX_RISING_LOOKBACK = 4  # Compare current to 4 periods ago

# =============================================================================
# FACTOR 3: Volume Conviction Scoring (0-20 pts)
# =============================================================================
# Relative Volume (0-10 pts)
VOLUME_REL_THRESHOLDS = [2.0, 1.5, 1.2, 1.0]
VOLUME_REL_SCORES = [10, 8, 6, 4, 0]  # Last value is default

# Volume Trend (0-5 pts)
VOLUME_TREND_RISING_THRESHOLD = 0.0
VOLUME_TREND_STABLE_THRESHOLD = -0.1
VOLUME_TREND_SCORES = {'rising': 5, 'stable': 3, 'falling': 0}

# Up/Down Volume Ratio (0-5 pts)
VOLUME_UD_THRESHOLDS = [2.0, 1.5]
VOLUME_UD_SCORES = [5, 3, 0]  # Last value is default

# =============================================================================
# FACTOR 4: Structure Scoring (0-20 pts)
# =============================================================================
STRUCTURE_SLOPE_STRONG = 1.0      # EMA50 slope > 1% = strong
STRUCTURE_SLOPE_POSITIVE = 0.0    # EMA50 slope > 0% = positive
STRUCTURE_BARS_EXCELLENT = 5      # >5 bars above EMA20
STRUCTURE_BARS_GOOD = 3           # >3 bars above EMA20
STRUCTURE_EMA_SPREAD_CLOSE = 0.01 # EMAs within 1% = "close"

STRUCTURE_SCORES = {
    'excellent': 20,  # Stack + strong slope + >5 bars
    'good': 15,       # Stack + positive slope + >3 bars
    'valid': 10,      # Stack + flat slope + >3 bars
    'new': 10,        # Newly formed stack
    'close': 5        # Stack but EMAs converging
}

# =============================================================================
# FACTOR 5: Risk/Reward Scoring (0-10 pts)
# =============================================================================
STOP_DIST_ATR_DEFAULT = 1.75     # ATR multiplier for stop distance
STOP_DIST_ATR_CONSERVATIVE = 2.0
STOP_DIST_ATR_AGGRESSIVE = 1.5
TARGET_ATR_MULTIPLIER = 4.0      # ATR multiplier for target

RR_SCORE_THRESHOLDS = [4.0, 3.0, 2.0, 1.5]
RR_SCORES = [10, 8, 6, 3, 0]  # Last value is default

# =============================================================================
# Rating Display Thresholds
# =============================================================================
SCORE_RATING_THRESHOLDS = {
    'optimal': 90,
    'good': 75,
    'acceptable': 60,
    'marginal': 45
}

RATING_LABELS = {
    'optimal': 'OPTIMAL ENTRY (90-100)',
    'good': 'GOOD ENTRY (75-89)',
    'acceptable': 'ACCEPTABLE ENTRY (60-74)',
    'marginal': 'MARGINAL ENTRY (45-59)',
    'poor': 'POOR ENTRY (<45)'
}

# =============================================================================
# Volatility Regimes (Percentiles)
# =============================================================================
REGIME_PERCENTILES = {
    'low': 30,
    'high': 70
}
