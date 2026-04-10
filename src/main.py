"""
Main CLI entry point for the Optimized EMA-ADX-ATR Framework.
"""
import argparse
import sys
import os
import re
import webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

# Adjust path to allow imports if running from top level
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.data import fetch_data, fetch_data_parallel, validate_data
from src.indicators import calculate_all_indicators
from src.scoring import EntryScorer
from src.config import EMA_FAST_PERIOD, EMA_SLOW_PERIOD, TARGET_ATR_MULTIPLIER, SCORE_WEIGHTS, SCORE_RATING_THRESHOLDS, RATING_LABELS
from src.dashboard import generate_dashboard, generate_index
from src.baskets import fetch_short_interest_parallel, fetch_basket_context
from src.rs_rating import calculate_rs_rating
from src.earnings import fetch_earnings_data
from src.options_analysis import fetch_options_data
from src.factors import calculate_factor_scores
from src.darkpool import fetch_darkpool_data
from src.volume_profile import calculate_volume_profile
from src.insiders import fetch_insider_transactions

def _load_default_watchlist() -> list:
    """
    Derive the default watchlist by deduplicating all tickers across all
    baskets defined in src/watchlist_baskets.yaml.

    Falls back to the original hardcoded list if the YAML cannot be loaded
    (e.g. file missing, YAML parse error) so the CLI never breaks.
    """
    try:
        from src.basket_engine import get_all_basket_tickers
        tickers = get_all_basket_tickers()
        if tickers:
            return tickers
    except Exception as exc:
        print(f"[watchlist] Could not load basket config — using fallback list. ({exc})")
    # Original hardcoded fallback
    return ["HAL", "AVGO", "AMZN", "NVDA", "GOOGL", "NEE", "NFLX", "HLT", "USAR", "UUUU", "MP"]


DEFAULT_WATCHLIST = _load_default_watchlist()


def _fetch_ticker_enrichment(ticker: str) -> dict:
    """
    Fetches all per-ticker enrichment data in parallel sub-threads.
    Returns a dict keyed by data type.
    """
    enrichment = {
        'rs_rating': {},
        'earnings': {},
        'options': {},
        'factors': {},
        'darkpool': {},
        'volume_profile': {},
        'insiders': {},
    }

    tasks = {
        'rs_rating':      lambda: calculate_rs_rating(ticker),
        'earnings':       lambda: fetch_earnings_data(ticker),
        'options':        lambda: fetch_options_data(ticker),
        'factors':        lambda: calculate_factor_scores(ticker),
        'darkpool':       lambda: fetch_darkpool_data(ticker),
        'volume_profile': lambda: calculate_volume_profile(ticker),
        'insiders':       lambda: fetch_insider_transactions(ticker),
    }

    ex = ThreadPoolExecutor(max_workers=4)
    try:
        futures = {ex.submit(fn): key for key, fn in tasks.items()}
        try:
            for future in as_completed(futures, timeout=45):
                key = futures[future]
                try:
                    enrichment[key] = future.result(timeout=30) or {}
                except Exception:
                    enrichment[key] = {}
        except Exception:
            # Overall enrichment timed out — use whatever we collected so far
            pass
    finally:
        # Do NOT wait for stuck threads; daemon threads will be abandoned
        ex.shutdown(wait=False, cancel_futures=True)

    return enrichment


def analyze_ticker(
    ticker: str,
    generate_html: bool = True,
    prefetched_df: pd.DataFrame = None,
    prefetched_si: dict = None,
) -> dict:
    """
    Analyzes a single ticker: scores entry, fetches all enrichment data,
    generates HTML dashboard with every panel.
    """
    try:
        df = prefetched_df if prefetched_df is not None else fetch_data(ticker, period="2y", interval="1wk")
        validate_data(df, min_records=52)

        df = calculate_all_indicators(df)
        scorer = EntryScorer(df)
        result = scorer.score()

        # --- CLI report ---
        print(f"\n{'='*50}")
        print(f"WEEKLY ANALYSIS REPORT: {ticker.upper()}")
        print(f"Date: {df.index[-1].strftime('%Y-%m-%d')}")
        print(f"Close: ${df['Close'].iloc[-1]:.2f}")
        print(f"Weekly Trend: {result.regime}")
        print(f"{'='*50}")
        print(f"\nTOTAL SCORE: {result.total_score:.1f}/100")

        if result.total_score >= SCORE_RATING_THRESHOLDS['optimal']:
            rating = RATING_LABELS['optimal']
        elif result.total_score >= SCORE_RATING_THRESHOLDS['good']:
            rating = RATING_LABELS['good']
        elif result.total_score >= SCORE_RATING_THRESHOLDS['acceptable']:
            rating = RATING_LABELS['acceptable']
        elif result.total_score >= SCORE_RATING_THRESHOLDS['marginal']:
            rating = RATING_LABELS['marginal']
        else:
            rating = RATING_LABELS['poor']

        print(f"RATING: {rating}")
        print(f"\n--- SCORE BREAKDOWN (WEEKLY) ---")
        print(f"EMA Proximity:     {result.breakdown['ema_proximity']:>4.1f} / {SCORE_WEIGHTS['ema_proximity']}")
        print(f"ADX Value:         {result.breakdown['adx_stage']:>4.1f} / {SCORE_WEIGHTS['adx_stage']}")
        print(f"Volume (Inverted): {result.breakdown['volume_conviction']:>4.1f} / {SCORE_WEIGHTS['volume_conviction']}")
        print(f"Structure:         {result.breakdown['structure']:>4.1f} / {SCORE_WEIGHTS['structure']}")
        print(f"Risk/Reward:       {result.breakdown['risk_reward']:>4.1f} / {SCORE_WEIGHTS['risk_reward']}")

        print(f"\n--- RISK MANAGEMENT ---")
        atr = result.details['atr']
        price = result.details['price']
        ema20 = result.details['ema20']
        stop_conservative = ema20 - (2.0 * atr)
        stop_aggressive = ema20 - (1.5 * atr)
        target_3r = price + (3.0 * atr)
        target_5r = price + (5.0 * atr)
        print(f"Conservative Stop: ${stop_conservative:.2f} (2.0x ATR)")
        print(f"Aggressive Stop:   ${stop_aggressive:.2f} (1.5x ATR)")
        print(f"Target (3R):       ${target_3r:.2f}")
        print(f"Target (5R):       ${target_5r:.2f}")

        if generate_html:
            # Fetch all enrichment data concurrently
            print(f"  Enriching {ticker} with market intelligence...")
            enrichment = _fetch_ticker_enrichment(ticker)
            si_data = prefetched_si or {}

            path = generate_dashboard(
                ticker, df, result, "WEEKLY",
                scorer=scorer,
                short_interest=si_data,
                rs_rating=enrichment.get('rs_rating', {}),
                earnings=enrichment.get('earnings', {}),
                options=enrichment.get('options', {}),
                factors=enrichment.get('factors', {}),
                darkpool=enrichment.get('darkpool', {}),
                volume_profile=enrichment.get('volume_profile', {}),
                insiders=enrichment.get('insiders', {}),
            )
            print(f"Dashboard generated: {path}")

            ema_dist = (price - ema20) / atr if atr > 0 else 0
            rel_vol = df['Volume'].iloc[-1] / df['Vol_Avg'].iloc[-1] if df['Vol_Avg'].iloc[-1] > 0 else 0
            stop_dist = scorer.regime_params.stop_distance_atr
            regime_stop = ema20 - (stop_dist * atr)
            risk = price - regime_stop
            reward = TARGET_ATR_MULTIPLIER * atr
            rr_ratio = reward / risk if risk > 0 else 0
            prev_close = df['Close'].iloc[-2] if len(df) >= 2 else price
            price_change_pct = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else 0

            return {
                'ticker': ticker,
                'score': result.total_score,
                'trend': "WEEKLY",
                'regime': result.regime,
                'path': path,
                'close': price,
                'ema20': ema20,
                'ema50': result.details['ema50'],
                'ema_dist': ema_dist,
                'adx': result.details['adx'],
                'rel_vol': rel_vol,
                'rr': rr_ratio,
                'price_change_pct': price_change_pct,
                'stop_dist_atr': stop_dist,
                'rs_score': enrichment.get('rs_rating', {}).get('score'),
                'earnings_risk': enrichment.get('earnings', {}).get('risk_level', 'CLEAR'),
                'days_to_earnings': enrichment.get('earnings', {}).get('days_to_earnings'),
                'squeeze_score': si_data.get('squeeze_score'),
                'darkpool_signal': enrichment.get('darkpool', {}).get('signal', 'NEUTRAL'),
            }

    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")
        return None


def _generate_news():
    """Generate the Market Themes News Dashboard."""
    from src.news import fetch_thematic_news
    from src.news_dashboard import generate_news_dashboard
    from src.config import MARKET_THEMES
    print("Fetching thematic news...")
    news_data = fetch_thematic_news(MARKET_THEMES)
    path = generate_news_dashboard(news_data)
    print(f"Market News Dashboard generated at: {path}")
    return path


def _generate_sentiment():
    """Generate the Sentiment & Breadth Dashboard."""
    from src.sentiment_dashboard import generate_sentiment_dashboard
    print("Generating Sentiment & Breadth dashboard...")
    path = generate_sentiment_dashboard()
    print(f"Sentiment & Breadth dashboard generated at: {path}")
    return path


def _run_sectors(focus_sector=None, ai_memo=False, ai_macro_memo=False):
    """Run Sector Analysis (Macro Watch) dashboard."""
    from src.sectors.dashboard import run_sector_analysis
    run_sector_analysis(focus_sector=focus_sector, ai_memo=ai_memo, ai_macro_memo=ai_macro_memo)


def _run_tickers(tickers):
    """Run ticker analysis and generate index + stock dashboards."""
    ticker_pattern = re.compile(r'^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$')
    invalid = [t for t in tickers if not ticker_pattern.match(t.upper())]
    if invalid:
        print(f"Error: Invalid ticker symbol(s): {invalid}")
        print("Tickers must be 1-5 alphanumeric characters (e.g., AAPL, BRK.B)")
        sys.exit(1)
    tickers = [t.upper() for t in tickers]

    summary_reports = []
    print(f"Analyzing {len(tickers)} tickers...")

    # Phase 1: Parallel price data + short interest + basket context
    data_map = fetch_data_parallel(tickers, period="2y", interval="1wk")
    si_map = fetch_short_interest_parallel(tickers)
    basket_context = fetch_basket_context()

    # Phase 2: Score + enrich each ticker sequentially (each enrichment is internally parallel)
    for t in tickers:
        res = analyze_ticker(
            t,
            generate_html=True,
            prefetched_df=data_map.get(t),
            prefetched_si=si_map.get(t),
        )
        if res:
            summary_reports.append(res)

    if summary_reports:
        generate_index(summary_reports, basket_context=basket_context)
    else:
        print("No ticker reports generated.")

    return summary_reports


def main():
    parser = argparse.ArgumentParser(description='Analyze a ticker using the Optimized EMA-ADX-ATR Framework.')
    parser.add_argument('ticker', nargs='*', help='Ticker symbol(s) to analyze. If empty, runs default watchlist.')
    parser.add_argument('--sectors', action='store_true', help='Run full Sector Analysis (Macro Watch) dashboard.')
    parser.add_argument('--sector', type=str, help='Focus on a single sector (e.g., XLK, XLF, XLV). Use with --sectors.')
    parser.add_argument('--ai-memo', action='store_true', help='Generate AI Investment Strategy Memo of top candidates.')
    parser.add_argument('--ai-macro-memo', action='store_true', help='Generate Macro AI Strategy Memo of sector drivers.')
    parser.add_argument('--news', action='store_true', help='Generate only the Market Themes News Dashboard.')
    parser.add_argument('--update-universe', action='store_true',
                        help='Fetch current ETF top holdings and rewrite sectors.yaml stock lists.')
    parser.add_argument('--sentiment', action='store_true', help='Generate only the Sentiment & Breadth dashboard.')

    args = parser.parse_args()

    if args.update_universe:
        from src.sectors.universe_updater import update_universe
        _config_path = os.path.join(os.path.dirname(__file__), 'sectors', 'config', 'sectors.yaml')
        print("Updating stock universe from ETF holdings…")
        update_universe(_config_path)
        print("Re-run with --sectors to generate an updated dashboard.")
        return

    # Standalone mode: generate only news or only sentiment
    if args.news and not args.sectors and not args.ticker:
        _generate_news()
        webbrowser.open(f"file://{os.path.abspath('reports/market_news.html')}")
        return

    if args.sentiment and not args.sectors and not args.ticker:
        _generate_sentiment()
        webbrowser.open(f"file://{os.path.abspath('reports/sentiment.html')}")
        return

    # ── Full pipeline: sectors + tickers + sentiment + news ──

    # 1. Sector analysis (sector_analysis.html, sector_*.html, macro_drivers.html)
    _run_sectors(focus_sector=args.sector, ai_memo=args.ai_memo, ai_macro_memo=args.ai_macro_memo)

    # 2. Ticker analysis (index.html, stock_*.html)
    tickers = args.ticker if args.ticker else DEFAULT_WATCHLIST
    _run_tickers(tickers)

    # 3. Sentiment & Breadth (sentiment.html)
    _generate_sentiment()

    # 4. Market News (market_news.html)
    _generate_news()

    index_path = os.path.abspath("reports/index.html")
    print(f"\nFull pipeline complete. Opening index: {index_path}")
    webbrowser.open(f"file://{index_path}")


if __name__ == "__main__":
    main()
