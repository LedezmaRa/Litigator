"""
Configuration settings for the Data-Driven EMA-ADX-ATR Framework.

Scoring calibrated against 2-year weekly backtest data (820 observations).
Key insight: the ideal entry is a QUIET PULLBACK in a proven trend —
stock with ADX 25-30, price 1-2 ATR from EMA20, on declining volume.
"""

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
# Weights reflect backtest predictive power:
#   ADX value → strongest signal (+5.79%, 74% win at 25-30)
#   Volume (inverted) → strong contrarian signal (low vol = +9.44%, 88% win)
#   EMA proximity → moderate edge (1-2 ATR sweet spot)
#   Structure → small but real edge
#   R/R → risk management gate (no consistent return edge, but prudent)
SCORE_WEIGHTS = {
    'ema_proximity': 20,
    'adx_stage': 30,
    'volume_conviction': 25,
    'structure': 15,
    'risk_reward': 10
}

# =============================================================================
# FACTOR 1: EMA Proximity Scoring (0-20 pts)
# =============================================================================
# Backtest: 1-2 ATR distance = best returns (+4.11%, 67% win)
# Being too close (<0.5 ATR) actually underperforms (+1.73%, 53% win)
# Score peaks at 1-2 ATR (the pullback sweet spot)
EMA_PROXIMITY_BUCKETS = [0.5, 1.0, 1.5, 2.0, 3.0]
EMA_PROXIMITY_SCORES = [10, 15, 20, 20, 10, 0]  # Peak at 1.0-2.0 ATR

# =============================================================================
# FACTOR 2: ADX Value Scoring (0-30 pts)
# =============================================================================
# Backtest: ADX VALUE is the strongest predictor. Direction (rising/falling)
# has zero edge (+2.76% vs +2.77%). Scored purely on value range.
#   ADX 25-30: +5.79%, 74% win (optimal)
#   ADX 15-20: +3.98%, 63% win (emerging)
#   ADX <15:   -0.01%, 36% win (no trend — avoid)
ADX_VALUE_RANGES = {
    'optimal':  (25, 30),   # 30 pts — strongest signal
    'strong':   (20, 25),   # 24 pts — solid emerging trend
    'good':     (30, 35),   # 20 pts — proven trend, slight maturity risk
    'moderate': (15, 20),   # 12 pts — early/weak trend
    'extended': (35, 45),   # 8 pts  — overheated, late-stage
    'extreme':  (45, 100),  # 4 pts  — extreme trend, reversal risk
}
ADX_VALUE_SCORES = {
    'optimal':  30,
    'strong':   24,
    'good':     20,
    'moderate': 12,
    'extended': 8,
    'extreme':  4,
}

# Legacy — kept for backward compatibility but no longer used in scoring
ADX_SCORE_RANGES = ADX_VALUE_RANGES
ADX_RANGE_SCORES = ADX_VALUE_SCORES
ADX_RISING_LOOKBACK = 4

# =============================================================================
# FACTOR 3: Volume Conviction Scoring (0-25 pts) — INVERTED
# =============================================================================
# Backtest: LOW relative volume predicts BETTER returns.
#   Vol <0.5x:  +9.44%, 88% win (selling exhaustion — strongest signal)
#   Vol 0.5-0.8x: +2.93%, 61%
#   Vol >1.5x:  +0.74%, 52% (climax / panic volume — worst signal)
# Interpretation: quiet pullback = coiled spring; high volume = climax

# Relative Volume — INVERTED (0-15 pts): lower volume = higher score
VOLUME_REL_THRESHOLDS = [0.5, 0.8, 1.0, 1.5]
VOLUME_REL_SCORES = [15, 12, 8, 5, 2]  # <0.5x=15, 0.5-0.8=12, 0.8-1.0=8, 1.0-1.5=5, >1.5=2

# Volume Trend — INVERTED (0-5 pts): declining volume = bullish
VOLUME_TREND_RISING_THRESHOLD = 0.0
VOLUME_TREND_STABLE_THRESHOLD = -0.1
VOLUME_TREND_SCORES = {'falling': 5, 'stable': 3, 'rising': 0}

# Up/Down Volume Ratio (0-5 pts) — kept directional (more buying = good)
VOLUME_UD_THRESHOLDS = [2.0, 1.5]
VOLUME_UD_SCORES = [5, 3, 0]

# =============================================================================
# FACTOR 4: Structure Scoring (0-15 pts)
# =============================================================================
# Backtest: small but real edge for EMA stack alignment.
# Reduced from 20pts to 15pts to match its predictive weight.
STRUCTURE_SLOPE_STRONG = 1.0      # EMA50 slope > 1% = strong
STRUCTURE_SLOPE_POSITIVE = 0.0    # EMA50 slope > 0% = positive
STRUCTURE_BARS_EXCELLENT = 5      # >5 bars above EMA20
STRUCTURE_BARS_GOOD = 3           # >3 bars above EMA20
STRUCTURE_EMA_SPREAD_CLOSE = 0.01 # EMAs within 1% = "close"

STRUCTURE_SCORES = {
    'excellent': 15,  # Stack + strong slope + >5 bars
    'good': 12,       # Stack + positive slope + >3 bars
    'valid': 8,       # Stack + flat slope + >3 bars
    'new': 8,         # Newly formed stack
    'close': 4        # Stack but EMAs converging
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
    'optimal': 85,
    'good': 65,
    'acceptable': 50,
    'marginal': 35
}

RATING_LABELS = {
    'optimal': 'OPTIMAL ENTRY (85-100)',
    'good': 'GOOD ENTRY (65-84)',
    'acceptable': 'ACCEPTABLE ENTRY (50-64)',
    'marginal': 'MARGINAL ENTRY (35-49)',
    'poor': 'POOR ENTRY (<35)'
}

# =============================================================================
# Volatility Regimes (Percentiles)
# =============================================================================
REGIME_PERCENTILES = {
    'low': 30,
    'high': 70
}

# =============================================================================
# AI Model Configuration
# =============================================================================
AI_MODEL = "claude-sonnet-4-20250514"
AI_MAX_TOKENS = 8000
AI_TEMPERATURE = 0.3

# =============================================================================
# Thematic Market News Context
# =============================================================================
MARKET_THEMES = [
    "War in Middle East",
    "Private Credit Concerns",
    "Stagflation",
    "Global Stock Market Trends"
]

# =============================================================================
# Legal Disclaimers
# =============================================================================
DISCLAIMER_TOP = """This content, which contains security-related opinions and/or information, is provided for informational purposes only and should not be relied upon in any manner as professional advice, or an endorsement of any practices, products or services. There can be no guarantees or assurances that the views expressed here will be applicable for any particular facts or circumstances, and should not be relied upon in any manner. You should consult your own advisers as to legal, business, tax, and other related matters concerning any investment."""

DISCLAIMER_BOTTOM = """The commentary in this report reflects the personal opinions, viewpoints, and analyses of the author(s), and should not be regarded as official investment advice or relied upon in any manner as professional advice.

Any opinions expressed herein do not constitute or imply endorsement, sponsorship, or recommendation by the author or its affiliates. The author and its affiliates may invest in any technology company or asset discussed. The views reflected in the commentary are subject to change at any time without notice.

Nothing on this website or report constitutes investment advice, performance data or any recommendation that any particular security, portfolio of securities, transaction or investment strategy is suitable for any specific person. It also should not be construed as an offer soliciting the purchase or sale of any security mentioned.

Any mention of a particular security and related performance data is not a recommendation to buy or sell that security. Investments in securities involve the risk of loss. Past performance is no guarantee of future results.

Any charts provided here are for informational purposes only, and should also not be relied upon when making any investment decision. Any indices referenced for comparison are unmanaged and cannot be invested into directly. As always please remember investing involves risk and possible loss of principal capital; please seek advice from a licensed professional. Any projections, estimates, forecasts, targets, prospects and/or opinions expressed in these materials are subject to change without notice and may differ or be contrary to opinions expressed by others. Information in charts have been obtained from third-party sources and data. While taken from sources believed to be reliable, the author has not independently verified such information and makes no representations about the enduring accuracy of the information or its appropriateness for a given situation. All content speaks only as of the date indicated."""
