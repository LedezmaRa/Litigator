"""
Tests for src/basket_engine.py — Phase 1 & 2 coverage.

Phase 1: Config loading (load_watchlist_baskets, get_all_basket_tickers)
Phase 2: Signal computation (compute_basket_signals, compute_overall_regime)
"""

import os
import sys
import math
import tempfile
import pytest

# Ensure the project root is on the path so `src` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.basket_engine import (
    load_watchlist_baskets,
    get_all_basket_tickers,
    compute_basket_signals,
    compute_overall_regime,
    BasketSignal,
    OverallRegime,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_report(ticker: str, score: float, adx: float = 20.0,
                 close: float = 100.0, ema20: float = 95.0) -> dict:
    """Create a minimal report dict matching the shape returned by analyze_ticker."""
    return {
        "ticker": ticker,
        "score": score,
        "adx": adx,
        "close": close,
        "ema20": ema20,
        "ema50": ema20 * 0.9,
        "trend": "NORMAL_VOLATILITY",
        "regime": "NORMAL_VOLATILITY",
        "price_change_pct": 1.5,
        "rs_score": 60.0,
        "darkpool_signal": "NEUTRAL",
        "earnings_risk": "LOW",
        "squeeze_score": 10.0,
    }


MINIMAL_YAML = """
baskets:
  basket_a:
    name: "Basket A"
    macro_question: "Question A?"
    description: "Description A"
    tickers:
      AAPL: "Apple"
      MSFT: "Microsoft"
      GOOG: "Alphabet"

  basket_b:
    name: "Basket B"
    macro_question: "Question B?"
    description: "Description B"
    tickers:
      JPM: "JPMorgan"
      BAC: "Bank of America"
"""


def _write_yaml(content: str) -> str:
    """Write YAML content to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Config loading
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadWatchlistBaskets:

    def test_loads_real_yaml(self):
        """The real watchlist_baskets.yaml loads without error."""
        baskets = load_watchlist_baskets()
        assert isinstance(baskets, dict)
        assert len(baskets) >= 1

    def test_has_ten_baskets(self):
        """Production YAML defines exactly 10 baskets."""
        baskets = load_watchlist_baskets()
        assert len(baskets) == 10, (
            f"Expected 10 baskets, got {len(baskets)}: {list(baskets.keys())}"
        )

    def test_required_keys_present(self):
        """Every basket has name, macro_question, description, tickers."""
        baskets = load_watchlist_baskets()
        for basket_id, cfg in baskets.items():
            for key in ("name", "macro_question", "description", "tickers"):
                assert key in cfg, f"Basket '{basket_id}' missing key '{key}'"

    def test_no_empty_ticker_lists(self):
        """No basket has an empty tickers dict."""
        baskets = load_watchlist_baskets()
        for basket_id, cfg in baskets.items():
            assert cfg["tickers"], f"Basket '{basket_id}' has empty tickers"

    def test_ticker_values_are_strings(self):
        """Every ticker label is a non-empty string."""
        baskets = load_watchlist_baskets()
        for basket_id, cfg in baskets.items():
            for ticker, label in cfg["tickers"].items():
                assert isinstance(label, str) and label, (
                    f"Basket '{basket_id}' ticker '{ticker}' has bad label: {label!r}"
                )

    def test_custom_yaml_path(self):
        """load_watchlist_baskets accepts a custom config path."""
        path = _write_yaml(MINIMAL_YAML)
        try:
            baskets = load_watchlist_baskets(config_path=path)
            assert set(baskets.keys()) == {"basket_a", "basket_b"}
            assert baskets["basket_a"]["name"] == "Basket A"
            assert "AAPL" in baskets["basket_a"]["tickers"]
        finally:
            os.unlink(path)

    def test_missing_file_raises(self):
        """FileNotFoundError raised for a non-existent path."""
        with pytest.raises(FileNotFoundError):
            load_watchlist_baskets(config_path="/nonexistent/path/baskets.yaml")

    def test_invalid_yaml_raises(self):
        """YAMLError raised for malformed YAML."""
        import yaml
        path = _write_yaml("baskets: [this: is: bad: yaml")
        try:
            with pytest.raises(yaml.YAMLError):
                load_watchlist_baskets(config_path=path)
        finally:
            os.unlink(path)

    def test_missing_required_key_raises(self):
        """ValueError raised when a basket is missing a required key."""
        bad_yaml = """
baskets:
  basket_x:
    name: "Basket X"
    tickers:
      AAPL: "Apple"
"""
        path = _write_yaml(bad_yaml)
        try:
            with pytest.raises(ValueError, match="missing required key"):
                load_watchlist_baskets(config_path=path)
        finally:
            os.unlink(path)


class TestGetAllBasketTickers:

    def test_returns_list_of_strings(self):
        baskets = load_watchlist_baskets()
        tickers = get_all_basket_tickers(baskets)
        assert isinstance(tickers, list)
        assert all(isinstance(t, str) for t in tickers)

    def test_no_duplicates(self):
        baskets = load_watchlist_baskets()
        tickers = get_all_basket_tickers(baskets)
        assert len(tickers) == len(set(tickers)), "Duplicate tickers in get_all_basket_tickers"

    def test_nvda_present(self):
        """NVDA is a cross-basket sensor and must appear exactly once."""
        baskets = load_watchlist_baskets()
        tickers = get_all_basket_tickers(baskets)
        assert "NVDA" in tickers

    def test_custom_baskets(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            baskets = load_watchlist_baskets(config_path=path)
            tickers = get_all_basket_tickers(baskets)
            assert set(tickers) == {"AAPL", "MSFT", "GOOG", "JPM", "BAC"}
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Signal computation
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeBasketSignals:

    def _two_basket_config(self):
        path = _write_yaml(MINIMAL_YAML)
        baskets = load_watchlist_baskets(config_path=path)
        os.unlink(path)
        return baskets

    def test_covered_tickers_correct(self):
        """Tickers present in reports appear in covered_tickers."""
        baskets = self._two_basket_config()
        reports = [
            _make_report("AAPL", score=70.0),
            _make_report("MSFT", score=72.0),
        ]
        signals = compute_basket_signals(reports, baskets)
        assert set(signals["basket_a"].covered_tickers) == {"AAPL", "MSFT"}

    def test_missing_tickers_correct(self):
        """Tickers absent from reports appear in missing_tickers."""
        baskets = self._two_basket_config()
        reports = [_make_report("AAPL", score=70.0)]
        signals = compute_basket_signals(reports, baskets)
        assert "MSFT" in signals["basket_a"].missing_tickers
        assert "GOOG" in signals["basket_a"].missing_tickers

    def test_avg_score_is_mean(self):
        """avg_score is the arithmetic mean of covered ticker scores."""
        baskets = self._two_basket_config()
        reports = [
            _make_report("AAPL", score=60.0),
            _make_report("MSFT", score=80.0),
        ]
        signals = compute_basket_signals(reports, baskets)
        assert math.isclose(signals["basket_a"].avg_score, 70.0, rel_tol=1e-5)

    def test_high_score_above_ema20_is_bullish(self):
        """avg_score≥65 with >50% above EMA20 → BULLISH."""
        baskets = self._two_basket_config()
        reports = [
            _make_report("AAPL", score=70.0, close=110.0, ema20=100.0),
            _make_report("MSFT", score=68.0, close=105.0, ema20=100.0),
        ]
        signals = compute_basket_signals(reports, baskets)
        assert signals["basket_a"].signal == "BULLISH"

    def test_high_score_below_ema20_degrades_to_neutral(self):
        """avg_score≥65 but all tickers below EMA20 → NEUTRAL (breadth override)."""
        baskets = self._two_basket_config()
        reports = [
            _make_report("AAPL", score=70.0, close=90.0, ema20=100.0),
            _make_report("MSFT", score=68.0, close=88.0, ema20=100.0),
        ]
        signals = compute_basket_signals(reports, baskets)
        assert signals["basket_a"].signal == "NEUTRAL"

    def test_low_score_is_bearish(self):
        """avg_score<45 → BEARISH (or NEUTRAL if breadth is strong)."""
        baskets = self._two_basket_config()
        reports = [
            _make_report("AAPL", score=35.0, close=90.0, ema20=100.0),
            _make_report("MSFT", score=38.0, close=88.0, ema20=100.0),
        ]
        signals = compute_basket_signals(reports, baskets)
        assert signals["basket_a"].signal == "BEARISH"

    def test_low_score_high_breadth_upgrades_to_neutral(self):
        """avg_score<45 but >70% above EMA20 → upgraded to NEUTRAL."""
        baskets = self._two_basket_config()
        reports = [
            _make_report("AAPL", score=40.0, close=110.0, ema20=100.0),
            _make_report("MSFT", score=38.0, close=105.0, ema20=100.0),
            _make_report("GOOG", score=42.0, close=108.0, ema20=100.0),
        ]
        signals = compute_basket_signals(reports, baskets)
        assert signals["basket_a"].signal == "NEUTRAL"

    def test_zero_coverage_gives_neutral(self):
        """A basket with no reports defaults to NEUTRAL with low_coverage=True."""
        baskets = self._two_basket_config()
        reports = []  # nothing analyzed
        signals = compute_basket_signals(reports, baskets)
        assert signals["basket_a"].signal == "NEUTRAL"
        assert signals["basket_a"].low_coverage is True
        assert signals["basket_a"].ticker_count == 0

    def test_all_baskets_returned(self):
        """compute_basket_signals returns a signal for every basket in config."""
        baskets = self._two_basket_config()
        reports = [_make_report("AAPL", score=60.0)]
        signals = compute_basket_signals(reports, baskets)
        assert set(signals.keys()) == set(baskets.keys())

    def test_pct_above_ema20_range(self):
        """pct_above_ema20 is always in [0.0, 1.0]."""
        baskets = self._two_basket_config()
        reports = [
            _make_report("AAPL", score=60.0, close=105.0, ema20=100.0),
            _make_report("MSFT", score=55.0, close=95.0,  ema20=100.0),
        ]
        signals = compute_basket_signals(reports, baskets)
        pct = signals["basket_a"].pct_above_ema20
        assert 0.0 <= pct <= 1.0


class TestComputeOverallRegime:

    def _make_signal(self, basket_id: str, signal: str, avg_score: float) -> BasketSignal:
        from src.basket_engine import _SIGNAL_CSS
        color, badge, card = _SIGNAL_CSS[signal]
        return BasketSignal(
            basket_id=basket_id,
            name=basket_id,
            macro_question="?",
            description="",
            signal=signal,
            signal_color=color,
            signal_badge_class=badge,
            signal_card_class=card,
            avg_score=avg_score,
            avg_adx=20.0,
            pct_above_ema20=0.5,
            ticker_count=2,
            covered_tickers=[],
            missing_tickers=[],
            ticker_details=[],
        )

    def _make_signals(self, mapping: dict) -> dict:
        """mapping: {basket_id: (signal, avg_score)}"""
        return {
            bid: self._make_signal(bid, sig, score)
            for bid, (sig, score) in mapping.items()
        }

    def test_all_bullish_is_risk_on(self):
        signals = self._make_signals({
            f"b{i}": ("BULLISH", 75.0) for i in range(10)
        })
        regime = compute_overall_regime(signals)
        assert regime.verdict == "RISK_ON"

    def test_all_bearish_is_risk_off(self):
        signals = self._make_signals({
            f"b{i}": ("BEARISH", 30.0) for i in range(10)
        })
        regime = compute_overall_regime(signals)
        assert regime.verdict == "RISK_OFF"

    def test_fifty_fifty_is_mixed(self):
        signals = self._make_signals({
            **{f"bull_{i}": ("BULLISH", 70.0) for i in range(5)},
            **{f"bear_{i}": ("BEARISH", 35.0) for i in range(5)},
        })
        regime = compute_overall_regime(signals)
        assert regime.verdict == "MIXED"

    def test_semiconductor_bearish_caps_risk_on(self):
        """Even if 80% of baskets are bullish, a BEARISH semiconductor_cycle → MIXED."""
        signals = self._make_signals({
            f"b{i}": ("BULLISH", 75.0) for i in range(9)
        })
        # Override one basket with the sentinel id
        signals["semiconductor_cycle"] = self._make_signal(
            "semiconductor_cycle", "BEARISH", 35.0
        )
        regime = compute_overall_regime(signals)
        assert regime.verdict == "MIXED", (
            "semiconductor_cycle BEARISH should cap RISK_ON to MIXED"
        )

    def test_financial_credit_bearish_caps_risk_on(self):
        """financial_credit BEARISH caps RISK_ON to MIXED."""
        signals = self._make_signals({
            f"b{i}": ("BULLISH", 75.0) for i in range(9)
        })
        signals["financial_credit"] = self._make_signal(
            "financial_credit", "BEARISH", 35.0
        )
        regime = compute_overall_regime(signals)
        assert regime.verdict == "MIXED"

    def test_counts_correct(self):
        signals = self._make_signals({
            "b1": ("BULLISH", 70.0),
            "b2": ("BULLISH", 68.0),
            "b3": ("NEUTRAL", 50.0),
            "b4": ("BEARISH", 35.0),
        })
        regime = compute_overall_regime(signals)
        assert regime.bullish_count == 2
        assert regime.neutral_count == 1
        assert regime.bearish_count == 1
        assert regime.total_baskets == 4

    def test_empty_signals_returns_mixed(self):
        regime = compute_overall_regime({})
        assert regime.verdict == "MIXED"
        assert regime.total_baskets == 0

    def test_key_insight_is_non_empty_string(self):
        signals = self._make_signals({"b1": ("NEUTRAL", 50.0)})
        regime = compute_overall_regime(signals)
        assert isinstance(regime.key_insight, str)
        assert len(regime.key_insight) > 0

    def test_verdict_label_matches_verdict(self):
        signals = self._make_signals({f"b{i}": ("BULLISH", 75.0) for i in range(10)})
        regime = compute_overall_regime(signals)
        assert regime.verdict_label == "Risk On"

        signals = self._make_signals({f"b{i}": ("BEARISH", 30.0) for i in range(10)})
        regime = compute_overall_regime(signals)
        assert regime.verdict_label == "Risk Off"


# ─────────────────────────────────────────────────────────────────────────────
# Integration smoke test against the real YAML
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrationRealYaml:

    def test_pipeline_with_synthetic_reports(self):
        """
        Full pipeline: load real YAML → compute signals with synthetic data
        → compute regime. Should not raise.
        """
        baskets = load_watchlist_baskets()
        tickers = get_all_basket_tickers(baskets)

        # Create a synthetic report for every ticker in the config
        reports = [_make_report(t, score=55.0) for t in tickers]

        signals = compute_basket_signals(reports, baskets)
        assert len(signals) == len(baskets)

        regime = compute_overall_regime(signals)
        assert regime.verdict in ("RISK_ON", "MIXED", "RISK_OFF")
        assert 0.0 <= regime.bullish_pct <= 1.0
        assert regime.bullish_count + regime.neutral_count + regime.bearish_count == regime.total_baskets
