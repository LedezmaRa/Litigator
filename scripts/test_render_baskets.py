"""
Dev script — test the basket renderer in isolation.

Generates a self-contained HTML file using synthetic data so you can
visually verify the regime bar and basket cards without running the
full analysis pipeline.

Usage (from project root):
    source .venv/bin/activate
    python scripts/test_render_baskets.py
    open /tmp/basket_test.html
"""

import sys
import os
import random

# Make `src` importable from anywhere
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.basket_engine import (
    load_watchlist_baskets,
    compute_basket_signals,
    compute_overall_regime,
    get_all_basket_tickers,
)
from src.basket_renderer import (
    render_regime_summary_bar,
    render_basket_cards_section,
)
from src.utils.html_utils import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav, generate_breadcrumb


# ─────────────────────────────────────────────────────────────────────────────
# Build synthetic reports that mimic a realistic market environment
# ─────────────────────────────────────────────────────────────────────────────

def _make_report(ticker: str, score: float, adx: float = 20.0,
                 close: float = 100.0, ema20: float = None,
                 wow_pct: float = None, regime: str = "NORMAL_VOLATILITY") -> dict:
    if ema20 is None:
        # Randomly above or below EMA20 to create realistic breadth
        ema20 = close * (0.97 if random.random() > 0.4 else 1.03)
    if wow_pct is None:
        wow_pct = random.uniform(-4.0, 6.0)
    return {
        "ticker": ticker,
        "score": score,
        "adx": adx,
        "close": close,
        "ema20": ema20,
        "ema50": ema20 * 0.92,
        "trend": regime,
        "regime": regime,
        "price_change_pct": wow_pct,
        "rs_score": score * 0.9,
        "darkpool_signal": random.choice(["ACCUMULATION", "NEUTRAL", "DISTRIBUTION"]),
        "earnings_risk": random.choice(["LOW", "MEDIUM", "HIGH"]),
        "squeeze_score": random.uniform(0, 100),
    }


# Simulate a MIXED/soft environment: tech weak, energy strong
SYNTHETIC_SCORES = {
    # Risk Appetite
    "NVDA": (38, 13.3, 182.0),
    "AMD":  (42, 15.1, 95.0),
    "JNJ":  (61, 22.4, 155.0),
    "PG":   (65, 19.8, 170.0),
    "GOOGL":(44, 16.2, 165.0),
    # Financial
    "JPM":  (58, 21.3, 220.0),
    "BAC":  (52, 18.7, 38.0),
    "GS":   (55, 20.1, 510.0),
    "BRK-B":(63, 24.5, 445.0),
    # Consumer
    "AMZN": (46, 14.9, 195.0),
    "COST": (70, 28.2, 900.0),
    "DG":   (48, 17.6, 78.0),
    "WMT":  (68, 26.4, 90.0),
    "NFLX": (52, 19.3, 910.0),
    # Industrial
    "CAT":  (55, 22.0, 320.0),
    "URI":  (61, 24.7, 740.0),
    "DE":   (49, 18.2, 370.0),
    "HON":  (58, 21.5, 230.0),
    # Semis
    "AMAT": (40, 14.5, 155.0),
    "LRCX": (38, 13.8, 70.0),
    "AVGO": (62, 23.1, 220.0),
    "TSM":  (55, 19.7, 155.0),
    # Housing
    "DHI":  (44, 16.3, 135.0),
    "LEN":  (42, 15.8, 120.0),
    "NEE":  (58, 20.9, 64.0),
    "HLT":  (60, 22.4, 250.0),
    # Energy
    "XOM":  (72, 30.1, 110.0),
    "HAL":  (68, 27.4, 28.0),
    "FANG": (74, 31.2, 185.0),
    "CVX":  (70, 29.3, 155.0),
    # AI Infra
    "SMCI": (35, 12.1, 32.0),
    "VST":  (78, 33.4, 145.0),
    "CEG":  (76, 31.8, 255.0),
    # Defense
    "LMT":  (71, 29.2, 480.0),
    "RTX":  (69, 27.8, 140.0),
    "NOC":  (73, 30.5, 530.0),
    "GD":   (66, 25.9, 295.0),
    # China / Global
    "MP":   (48, 17.3, 18.4),
    "UUUU": (48, 16.8, 18.4),
    "FSLR": (52, 19.1, 155.0),
    "ALB":  (43, 15.4, 78.0),
}


def build_synthetic_reports():
    random.seed(42)  # reproducible
    reports = []
    for ticker, (score, adx, close) in SYNTHETIC_SCORES.items():
        # Add some noise
        noisy_score = max(0, min(100, score + random.uniform(-3, 3)))
        reports.append(_make_report(ticker, noisy_score, adx, close))
    return reports


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("Loading basket config...")
    baskets = load_watchlist_baskets()
    basket_order = list(baskets.keys())

    print("Building synthetic reports...")
    reports = build_synthetic_reports()

    print("Computing basket signals...")
    basket_signals = compute_basket_signals(reports, baskets)

    print("Computing overall regime...")
    overall_regime = compute_overall_regime(basket_signals)

    print(f"\nOverall regime: {overall_regime.verdict_label}")
    print(f"  Bullish: {overall_regime.bullish_count}  "
          f"Neutral: {overall_regime.neutral_count}  "
          f"Bearish: {overall_regime.bearish_count}")
    print(f"  Insight: {overall_regime.key_insight}\n")
    for bid, bs in basket_signals.items():
        cov = f"{bs.ticker_count}/{bs.ticker_count + len(bs.missing_tickers)}"
        print(f"  [{bs.signal:7s}]  {bs.name:<30s}  "
              f"avg={bs.avg_score:.0f}  adx={bs.avg_adx:.1f}  "
              f"ema%={bs.pct_above_ema20*100:.0f}%  cov={cov}")

    print("\nRendering HTML...")
    regime_bar_html   = render_regime_summary_bar(overall_regime, basket_signals, basket_order)
    basket_cards_html = render_basket_cards_section(basket_signals, basket_order)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Basket Renderer Test</title>
    <style>{CSS_DARK_THEME}</style>
</head>
<body>
    {generate_top_nav("command_center")}
    {regime_bar_html}
    <div class="container">
        {generate_breadcrumb([("Command Center", "index.html")])}
        <header class="mb-4" style="margin-top:1.5rem;">
            <h1 style="background: linear-gradient(to right, #60a5fa, #a78bfa);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;">
                Command Center
            </h1>
            <p class="text-muted">Basket Renderer — Dev Test (Synthetic Data)</p>
        </header>
        {basket_cards_html}
        <div class="glass-card text-center" style="margin-top:2rem; padding:2rem;">
            <p class="text-muted text-sm">
                ↑ Basket cards rendered from synthetic data.<br>
                Ticker links will 404 — this is expected in the test render.
            </p>
        </div>
    </div>
    {INTERACTIVE_JS}
</body>
</html>"""

    out_path = "/tmp/basket_test.html"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"\n✓ Written to {out_path}")
    print("  Open with:  open /tmp/basket_test.html")


if __name__ == "__main__":
    main()
