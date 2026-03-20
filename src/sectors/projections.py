"""
Projection Engine for Macro Watch 2.1 (Unified)

ATR-based target calculation with confidence scoring.

First Principles Approach:
- ATR represents the stock's natural daily movement range
- Targets are multiples of this volatility measure (1R, 2R, 3R)
- Confidence is derived from signal alignment (regime + strength + volume)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional


class ConfidenceLevel(Enum):
    """Confidence level classification."""
    HIGH = "HIGH"       # 80-100%
    MEDIUM = "MEDIUM"   # 50-79%
    LOW = "LOW"         # 20-49%
    NONE = "NONE"       # <20%


# ATR multiplier for stop distance (risk unit)
STOP_ATR_MULTIPLIER = 1.5


@dataclass
class ProjectionResult:
    """
    ATR-based projection result with targets and confidence.

    All monetary values are in the stock's currency (typically USD).
    """
    ticker: str
    name: str

    # Price levels
    current_price: float
    stop_price: float
    stop_distance: float

    # Targets
    target_1r: float
    target_2r: float
    target_3r: float

    # Risk metrics
    risk_reward_1r: float  # Always 1.0 by definition
    risk_reward_2r: float  # Always 2.0 by definition
    risk_reward_3r: float  # Always 3.0 by definition

    # Confidence
    confidence_score: float      # 0-100
    confidence_level: str        # HIGH/MEDIUM/LOW/NONE

    # Supporting metrics
    atr: float
    atr_percent: float           # ATR as % of price
    regime: str
    signal_strength: str
    volume_confirms: bool

    # Composite score (from Stage 1/2)
    composite_score: float = 0.0
    sector: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


def calculate_confidence_score(
    regime: str,
    signal_strength: str,
    volume_confirms: bool
) -> float:
    """
    Calculate confidence score based on signal alignment.
    Using string matching for regime and signal to handle various input formats.
    """
    regime = str(regime).upper()
    signal = str(signal_strength).upper()

    # CHOPPING regime = no reliable projection
    if "CHOPPING" in regime or "SIDEWAYS" in regime:
        return 15.0  # Very low confidence

    if "UNDEFINED" in regime:
        return 10.0

    # Base score for TRENDING regime
    score = 30.0

    # Signal strength contribution
    if "STRONG" in signal:
        score += 40.0
    elif "MODERATE" in signal:
        score += 25.0
    elif "WEAK" in signal:
        score += 10.0
    # NONE adds nothing

    # Volume confirmation
    if volume_confirms:
        score += 20.0

    # Bonus for perfect alignment
    if "STRONG" in signal and volume_confirms:
        score += 10.0  # Perfect setup bonus

    return min(score, 100.0)


def get_confidence_level(score: float) -> ConfidenceLevel:
    """Convert score to confidence level."""
    if score >= 80:
        return ConfidenceLevel.HIGH
    elif score >= 50:
        return ConfidenceLevel.MEDIUM
    elif score >= 20:
        return ConfidenceLevel.LOW
    else:
        return ConfidenceLevel.NONE


def calculate_projection(
    ticker: str,
    name: str,
    current_price: float,
    atr: float,
    signal_strength: str,
    regime: str,
    volume_confirms: bool,
    composite_score: float = 0.0,
    sector: str = ""
) -> ProjectionResult:
    """
    Calculate ATR-based price targets with confidence scoring.

    First Principles:
    - Stop distance = ATR * 1.5 (defines 1 unit of risk "R")
    - Target 1R = Entry + R (1:1 risk/reward)
    - Target 2R = Entry + 2R (2:1 risk/reward)
    - Target 3R = Entry + 3R (3:1 risk/reward)
    """
    # Calculate stop distance (1R = risk unit)
    stop_distance = atr * STOP_ATR_MULTIPLIER
    stop_price = current_price - stop_distance

    # Calculate targets
    target_1r = current_price + stop_distance
    target_2r = current_price + (stop_distance * 2)
    target_3r = current_price + (stop_distance * 3)

    # Calculate confidence
    confidence_score = calculate_confidence_score(regime, signal_strength, volume_confirms)
    confidence_level = get_confidence_level(confidence_score)

    # ATR as percentage of price
    atr_percent = (atr / current_price * 100) if current_price > 0 else 0

    return ProjectionResult(
        ticker=ticker,
        name=name,
        current_price=current_price,
        stop_price=stop_price,
        stop_distance=stop_distance,
        target_1r=target_1r,
        target_2r=target_2r,
        target_3r=target_3r,
        risk_reward_1r=1.0,
        risk_reward_2r=2.0,
        risk_reward_3r=3.0,
        confidence_score=confidence_score,
        confidence_level=confidence_level.value,
        atr=atr,
        atr_percent=atr_percent,
        regime=regime,
        signal_strength=signal_strength,
        volume_confirms=volume_confirms,
        composite_score=composite_score,
        sector=sector,
    )


def rank_projections(
    projections: List[ProjectionResult],
    min_confidence: float = 20.0
) -> List[ProjectionResult]:
    """
    Rank projections by confidence and composite score.

    Ranking formula:
    - Primary: Confidence score (higher = better)
    - Secondary: Composite score (higher = better)
    """
    # Filter by minimum confidence
    filtered = [p for p in projections if p.confidence_score >= min_confidence]

    # Sort by confidence (primary) and composite score (secondary)
    ranked = sorted(
        filtered,
        key=lambda p: (p.confidence_score, p.composite_score),
        reverse=True
    )

    return ranked


def filter_trade_ready(
    projections: List[ProjectionResult]
) -> List[ProjectionResult]:
    """
    Filter to only trade-ready candidates.

    Trade-ready criteria:
    - Regime = TRENDING (String check)
    - Confidence >= 50 (MEDIUM or higher)
    """
    return [
        p for p in projections
        if "TRENDING" in str(p.regime).upper() and p.confidence_score >= 50
    ]
