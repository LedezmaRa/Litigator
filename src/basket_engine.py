"""
Basket Engine — Market Diagnostic Panel computation layer.

Responsibilities:
  1. Load basket configuration from src/watchlist_baskets.yaml
  2. Aggregate per-ticker scores into basket-level BULLISH/NEUTRAL/BEARISH signals
  3. Synthesize basket signals into an overall macro regime verdict

Design constraints:
  - Zero I/O beyond the initial YAML load (no yfinance, no network calls)
  - Pure computation on report dicts already produced by analyze_ticker()
  - Safe to import at module level — no heavy dependencies
  - All public functions have explicit return types and handle missing data gracefully
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Any

logger = logging.getLogger(__name__)

# Module-level cache so the YAML is only read once per process
_BASKETS_CACHE: Optional[Dict[str, dict]] = None

# Default YAML path — relative to this file so it works regardless of CWD
_DEFAULT_YAML_PATH = os.path.join(os.path.dirname(__file__), "watchlist_baskets.yaml")

# Baskets that act as early-warning sensors and count double in the regime vote
_DOUBLE_WEIGHT_BASKETS = {"semiconductor_cycle", "financial_credit"}

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BasketSignal:
    basket_id: str
    name: str
    macro_question: str
    description: str
    signal: Literal["BULLISH", "NEUTRAL", "BEARISH"]
    signal_color: str           # CSS var string, e.g. "var(--accent-optimal)"
    signal_badge_class: str     # e.g. "badge-optimal"
    signal_card_class: str      # e.g. "signal-bullish"  (for CSS ::before accent)
    avg_score: float
    avg_adx: float
    pct_above_ema20: float      # 0.0–1.0
    ticker_count: int           # number of covered tickers
    covered_tickers: List[str]  # tickers from config present in reports
    missing_tickers: List[str]  # tickers from config absent from reports
    ticker_details: List[dict]  # subset of report dicts for tickers in this basket
    low_coverage: bool = False  # True when fewer than 2 tickers covered


@dataclass
class OverallRegime:
    verdict: Literal["RISK_ON", "MIXED", "RISK_OFF"]
    verdict_label: str          # "Risk On" / "Mixed" / "Risk Off"
    verdict_color: str          # CSS var
    verdict_badge_class: str
    bullish_count: int
    neutral_count: int
    bearish_count: int
    total_baskets: int
    bullish_pct: float
    bearish_pct: float
    key_insight: str            # one-line human summary
    leading_baskets: List[str]  # top basket names driving the verdict


# ─────────────────────────────────────────────────────────────────────────────
# CSS mapping constants
# ─────────────────────────────────────────────────────────────────────────────

_SIGNAL_CSS: Dict[str, tuple] = {
    "BULLISH": ("var(--accent-optimal)",  "badge-optimal",  "signal-bullish"),
    "NEUTRAL": ("var(--accent-marginal)", "badge-marginal", "signal-neutral"),
    "BEARISH": ("var(--accent-poor)",     "badge-poor",     "signal-bearish"),
}

_VERDICT_CSS: Dict[str, tuple] = {
    "RISK_ON":  ("var(--accent-optimal)",  "badge-optimal",  "Risk On"),
    "MIXED":    ("var(--accent-marginal)", "badge-marginal", "Mixed"),
    "RISK_OFF": ("var(--accent-poor)",     "badge-poor",     "Risk Off"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def load_watchlist_baskets(config_path: Optional[str] = None) -> Dict[str, dict]:
    """
    Load basket configuration from watchlist_baskets.yaml.

    Returns a dict keyed by basket_id, each value containing:
        name, macro_question, description, tickers (dict of ticker -> label)

    Results are cached at module level — the file is read only once per process.
    Pass config_path to override the default location (useful for testing).
    """
    global _BASKETS_CACHE

    # Use cache unless a custom path is provided (testing scenario)
    if _BASKETS_CACHE is not None and config_path is None:
        return _BASKETS_CACHE

    import yaml  # deferred import — only needed here

    path = config_path or _DEFAULT_YAML_PATH

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("watchlist_baskets.yaml not found at %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("Failed to parse watchlist_baskets.yaml: %s", exc)
        raise

    baskets: Dict[str, dict] = {}
    for basket_id, config in raw.get("baskets", {}).items():
        # Validate required keys
        for required in ("name", "macro_question", "description", "tickers"):
            if required not in config:
                raise ValueError(
                    f"Basket '{basket_id}' is missing required key '{required}'"
                )
        if not config["tickers"]:
            raise ValueError(f"Basket '{basket_id}' has an empty tickers dict")

        baskets[basket_id] = {
            "name":           config["name"],
            "macro_question": config["macro_question"],
            "description":    config["description"],
            "tickers":        dict(config["tickers"]),  # ticker -> human label
        }

    if not baskets:
        raise ValueError("watchlist_baskets.yaml contains no baskets")

    logger.info("Loaded %d baskets from %s", len(baskets), path)

    # Cache only when using the default path
    if config_path is None:
        _BASKETS_CACHE = baskets

    return baskets


def get_all_basket_tickers(baskets_config: Optional[Dict[str, dict]] = None) -> List[str]:
    """
    Return a deduplicated, ordered list of all tickers across all baskets.
    Preserves first-seen basket order. Used by main.py to build DEFAULT_WATCHLIST.
    """
    if baskets_config is None:
        baskets_config = load_watchlist_baskets()
    seen: Dict[str, bool] = {}
    for basket in baskets_config.values():
        for ticker in basket["tickers"]:
            seen[ticker] = True
    return list(seen.keys())


def compute_basket_signals(
    reports: List[dict],
    baskets_config: Optional[Dict[str, dict]] = None,
) -> Dict[str, BasketSignal]:
    """
    Aggregate per-ticker report dicts into a BasketSignal for each basket.

    Args:
        reports:        List of report dicts from analyze_ticker(). Each dict
                        must have at minimum: ticker, score, adx, close, ema20.
        baskets_config: Output of load_watchlist_baskets(). Loaded automatically
                        if not provided.

    Returns:
        Dict mapping basket_id -> BasketSignal
    """
    if baskets_config is None:
        baskets_config = load_watchlist_baskets()

    # Build a fast lookup: ticker -> report dict
    report_lookup: Dict[str, dict] = {r["ticker"]: r for r in reports if "ticker" in r}

    basket_signals: Dict[str, BasketSignal] = {}

    for basket_id, config in baskets_config.items():
        config_tickers = list(config["tickers"].keys())

        # Split into covered (in reports) and missing (not run this session)
        covered = [report_lookup[t] for t in config_tickers if t in report_lookup]
        missing = [t for t in config_tickers if t not in report_lookup]

        if missing:
            logger.debug(
                "Basket '%s': %d tickers not analyzed: %s",
                basket_id, len(missing), missing
            )

        signal, avg_score, avg_adx, pct_above_ema20, low_coverage = _compute_signal(
            basket_id, covered
        )

        color, badge_class, card_class = _SIGNAL_CSS[signal]

        basket_signals[basket_id] = BasketSignal(
            basket_id=basket_id,
            name=config["name"],
            macro_question=config["macro_question"],
            description=config["description"],
            signal=signal,
            signal_color=color,
            signal_badge_class=badge_class,
            signal_card_class=card_class,
            avg_score=avg_score,
            avg_adx=avg_adx,
            pct_above_ema20=pct_above_ema20,
            ticker_count=len(covered),
            covered_tickers=[r["ticker"] for r in covered],
            missing_tickers=missing,
            ticker_details=covered,
            low_coverage=low_coverage,
        )

    return basket_signals


def compute_overall_regime(
    basket_signals: Dict[str, BasketSignal],
) -> OverallRegime:
    """
    Synthesize basket-level signals into a single macro regime verdict.

    Verdict thresholds (asymmetric — harder to call risk-on than risk-off):
        RISK_ON:  ≥60% BULLISH  AND  ≤20% BEARISH
        RISK_OFF: ≥50% BEARISH  AND  ≤20% BULLISH
        MIXED:    everything else

    Double-weight baskets: semiconductor_cycle, financial_credit.
    If either is BEARISH, a potential RISK_ON verdict is capped at MIXED.
    """
    if not basket_signals:
        return _empty_regime()

    total = len(basket_signals)
    bullish_count = sum(1 for bs in basket_signals.values() if bs.signal == "BULLISH")
    neutral_count = sum(1 for bs in basket_signals.values() if bs.signal == "NEUTRAL")
    bearish_count = sum(1 for bs in basket_signals.values() if bs.signal == "BEARISH")

    bullish_pct = bullish_count / total
    bearish_pct = bearish_count / total

    # Raw verdict
    if bullish_pct >= 0.60 and bearish_pct <= 0.20:
        verdict = "RISK_ON"
    elif bearish_pct >= 0.50 and bullish_pct <= 0.20:
        verdict = "RISK_OFF"
    else:
        verdict = "MIXED"

    # Double-weight early-warning override: if a sentinel basket is BEARISH,
    # cap a potential RISK_ON at MIXED
    if verdict == "RISK_ON":
        for sentinel_id in _DOUBLE_WEIGHT_BASKETS:
            if sentinel_id in basket_signals and basket_signals[sentinel_id].signal == "BEARISH":
                verdict = "MIXED"
                logger.info(
                    "Regime downgraded from RISK_ON to MIXED: sentinel basket '%s' is BEARISH",
                    sentinel_id,
                )
                break

    color, badge_class, label = _VERDICT_CSS[verdict]

    # Leading baskets: top 2 by avg_score (for BULLISH/MIXED) or bottom 2 (for RISK_OFF)
    reverse_sort = (verdict != "RISK_OFF")
    sorted_baskets = sorted(
        basket_signals.values(),
        key=lambda bs: bs.avg_score,
        reverse=reverse_sort,
    )
    leading_baskets = [bs.name for bs in sorted_baskets[:2]]

    key_insight = _build_key_insight(verdict, bullish_count, bearish_count, total, leading_baskets)

    return OverallRegime(
        verdict=verdict,
        verdict_label=label,
        verdict_color=color,
        verdict_badge_class=badge_class,
        bullish_count=bullish_count,
        neutral_count=neutral_count,
        bearish_count=bearish_count,
        total_baskets=total,
        bullish_pct=bullish_pct,
        bearish_pct=bearish_pct,
        key_insight=key_insight,
        leading_baskets=leading_baskets,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute_signal(
    basket_id: str,
    covered: List[dict],
) -> tuple:
    """
    Derive (signal, avg_score, avg_adx, pct_above_ema20, low_coverage)
    from the list of covered report dicts.
    """
    low_coverage = len(covered) < 2

    if not covered:
        return "NEUTRAL", 0.0, 0.0, 0.0, True

    # ── Step 1: Compute intermediate metrics ─────────────────────────────────
    scores = [_safe_float(r.get("score")) for r in covered]
    adx_vals = [_safe_float(r.get("adx")) for r in covered if _safe_float(r.get("adx")) > 0]
    ema20_positions = [
        1 if _safe_float(r.get("close")) > _safe_float(r.get("ema20")) else 0
        for r in covered
        if _safe_float(r.get("ema20")) > 0
    ]

    avg_score = sum(scores) / len(scores) if scores else 0.0
    avg_adx   = sum(adx_vals) / len(adx_vals) if adx_vals else 0.0
    pct_above_ema20 = sum(ema20_positions) / len(ema20_positions) if ema20_positions else 0.0

    # ── Step 2: Score-to-signal (primary) ────────────────────────────────────
    if avg_score >= 65:
        raw_signal = "BULLISH"
    elif avg_score >= 45:
        raw_signal = "NEUTRAL"
    else:
        raw_signal = "BEARISH"

    # ── Step 3: EMA20 breadth structural override ─────────────────────────────
    # High score means nothing if most of the basket is below its trend line
    signal = raw_signal
    if raw_signal == "BULLISH" and pct_above_ema20 < 0.50:
        signal = "NEUTRAL"
        logger.debug(
            "Basket '%s' downgraded BULLISH→NEUTRAL: avg_score=%.1f but pct_above_ema20=%.0f%%",
            basket_id, avg_score, pct_above_ema20 * 100,
        )
    elif raw_signal == "BEARISH" and pct_above_ema20 > 0.70:
        signal = "NEUTRAL"
        logger.debug(
            "Basket '%s' upgraded BEARISH→NEUTRAL: avg_score=%.1f but pct_above_ema20=%.0f%%",
            basket_id, avg_score, pct_above_ema20 * 100,
        )

    # ── Step 4: ADX conviction upgrade ───────────────────────────────────────
    # Strong trend + breadth = underlying NEUTRAL may actually be BULLISH
    if signal == "NEUTRAL" and avg_adx >= 28 and pct_above_ema20 >= 0.60:
        signal = "BULLISH"
        logger.debug(
            "Basket '%s' upgraded NEUTRAL→BULLISH: avg_adx=%.1f, pct_above_ema20=%.0f%%",
            basket_id, avg_adx, pct_above_ema20 * 100,
        )

    return signal, avg_score, avg_adx, pct_above_ema20, low_coverage


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Return float(value) or default if value is None/NaN/invalid."""
    try:
        f = float(value)
        import math
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _build_key_insight(
    verdict: str,
    bullish_count: int,
    bearish_count: int,
    total: int,
    leading_baskets: List[str],
) -> str:
    leaders = " & ".join(leading_baskets) if leading_baskets else "N/A"
    if verdict == "RISK_ON":
        return (
            f"Broad strength across {bullish_count}/{total} baskets. "
            f"{leaders} leading the advance."
        )
    elif verdict == "RISK_OFF":
        return (
            f"Deterioration across {bearish_count}/{total} baskets. "
            f"Reduce exposure — {leaders} weakest."
        )
    else:
        return (
            f"Rotation underway — {bullish_count} bullish, {bearish_count} bearish. "
            f"Watch {leaders} for direction confirmation."
        )


def _empty_regime() -> OverallRegime:
    """Return a safe MIXED regime when no basket signals exist."""
    color, badge_class, label = _VERDICT_CSS["MIXED"]
    return OverallRegime(
        verdict="MIXED",
        verdict_label=label,
        verdict_color=color,
        verdict_badge_class=badge_class,
        bullish_count=0,
        neutral_count=0,
        bearish_count=0,
        total_baskets=0,
        bullish_pct=0.0,
        bearish_pct=0.0,
        key_insight="No basket data available.",
        leading_baskets=[],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test (run directly: python -m src.basket_engine)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    print("Loading watchlist baskets...")
    baskets = load_watchlist_baskets()
    print(f"\nLoaded {len(baskets)} baskets:\n")
    for bid, cfg in baskets.items():
        tickers = list(cfg["tickers"].keys())
        print(f"  [{bid}]  {cfg['name']}")
        print(f"    Q: {cfg['macro_question']}")
        print(f"    Tickers ({len(tickers)}): {', '.join(tickers)}")
        print()

    all_tickers = get_all_basket_tickers(baskets)
    print(f"Unique tickers across all baskets ({len(all_tickers)}): {', '.join(all_tickers)}")
