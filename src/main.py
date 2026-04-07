"""
Main CLI entry point for the Optimized EMA-ADX-ATR Framework.
"""
import argparse
import sys
import os
import re
import webbrowser
from datetime import datetime
import pandas as pd

# Adjust path to allow imports if running from top level
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.data import fetch_data, fetch_data_parallel, validate_data
from src.indicators import calculate_all_indicators
from src.scoring import EntryScorer
from src.config import EMA_FAST_PERIOD, EMA_SLOW_PERIOD
from src.dashboard import generate_dashboard, generate_index
from src.baskets import fetch_short_interest_parallel, fetch_basket_context

DEFAULT_WATCHLIST = ["HAL", "AVGO", "AMZN", "NVDA", "GOOGL", "NEE", "NFLX", "HLT", "USAR", "UUUU", "MP"]

def analyze_ticker(ticker: str, generate_html: bool = True, prefetched_df: pd.DataFrame = None, prefetched_si: dict = None) -> dict:
    """
    Analyzes a single ticker and prints the report.
    Returns a dict with summary info if successful.
    Uses prefetched_df if available (from parallel fetch), otherwise fetches on demand.
    """
    try:
        df = prefetched_df if prefetched_df is not None else fetch_data(ticker, period="2y", interval="1wk")
        validate_data(df, min_records=52)
        
        # 2. Calculate Indicators (Weekly)
        df = calculate_all_indicators(df)
        
        # 3. Score (Weekly)
        scorer = EntryScorer(df)
        result = scorer.score()
        
        # 4. Report
        print(f"\n{'='*50}")
        print(f"WEEKLY ANALYSIS REPORT: {ticker.upper()}")
        print(f"Date: {df.index[-1].strftime('%Y-%m-%d')}")
        print(f"Close: ${df['Close'].iloc[-1]:.2f}")
        print(f"Weekly Trend: {result.regime}") 
        print(f"{'='*50}")
        
        print(f"\nTOTAL SCORE: {result.total_score:.1f}/100")
        
        if result.total_score >= 90:
            rating = "OPTIMAL ENTRY (90-100)"
        elif result.total_score >= 75:
            rating = "GOOD ENTRY (75-89)"
        elif result.total_score >= 60:
            rating = "ACCEPTABLE ENTRY (60-74)"
        elif result.total_score >= 45:
            rating = "MARGINAL ENTRY (45-59)"
        else:
            rating = "POOR ENTRY (<45)"
            
        print(f"RATING: {rating}")
        
        print(f"\n--- SCORE BREAKDOWN (WEEKLY) ---")
        print(f"EMA Proximity:     {result.breakdown['ema_proximity']:>4.1f} / 25")
        print(f"ADX Stage:         {result.breakdown['adx_stage']:>4.1f} / 25")
        print(f"Volume Conviction: {result.breakdown['volume_conviction']:>4.1f} / 20")
        print(f"Structure:         {result.breakdown['structure']:>4.1f} / 20")
        print(f"Risk/Reward:       {result.breakdown['risk_reward']:>4.1f} / 10")
        
        print(f"\n--- RISK MANAGEMENT ---")
        atr = result.details['atr']
        price = result.details['price']
        ema20 = result.details['ema20']
        
        # Framework 2.0: Stop is 1.5-2.0x ATR below EMA20
        # We used 1.75x for scoring, let's display the range or conservative
        stop_conservative = ema20 - (2.0 * atr)
        stop_aggressive = ema20 - (1.5 * atr)
        
        print(f"Conservative Stop: ${stop_conservative:.2f} (2.0x ATR)")
        print(f"Aggressive Stop:   ${stop_aggressive:.2f} (1.5x ATR)")
        
        # Targets (3x - 5x ATR)
        target_3r = price + (3.0 * atr)
        target_5r = price + (5.0 * atr)
        print(f"Target (3R):       ${target_3r:.2f}")
        print(f"Target (5R):       ${target_5r:.2f}")

        if generate_html:
            si_data = prefetched_si or {}
            path = generate_dashboard(ticker, df, result, "WEEKLY", scorer=scorer, short_interest=si_data)
            print(f"Dashboard generated: {path}")

            # Helper metrics
            ema_dist = (price - ema20) / atr if atr > 0 else 0
            rel_vol = df['Volume'].iloc[-1] / df['Vol_Avg'].iloc[-1] if df['Vol_Avg'].iloc[-1] > 0 else 0

            # Regime-aware stop for R:R display
            stop_dist = scorer.regime_params.stop_distance_atr
            regime_stop = ema20 - (stop_dist * atr)
            risk = price - regime_stop
            reward = target_5r - price
            rr_ratio = reward / risk if risk > 0 else 0

            # Week-over-week deltas
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
            }
            
    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Analyze a ticker using the Optimized EMA-ADX-ATR Framework.')
    parser.add_argument('ticker', nargs='*', help='Ticker symbol(s) to analyze. If empty, runs default watchlist.')
    parser.add_argument('--sectors', action='store_true', help='Run full Sector Analysis (Macro Watch) dashboard.')
    parser.add_argument('--sector', type=str, help='Focus on a single sector (e.g., XLK, XLF, XLV). Use with --sectors.')
    parser.add_argument('--ai-memo', action='store_true', help='Generate AI Investment Strategy Memo of top candidates.')
    parser.add_argument('--ai-macro-memo', action='store_true', help='Generate Macro AI Strategy Memo of sector drivers.')
    parser.add_argument('--news', action='store_true', help='Generate Market Themes News Dashboard.')
    parser.add_argument('--update-universe', action='store_true',
                        help='Fetch current ETF top holdings and rewrite sectors.yaml stock lists.')

    args = parser.parse_args()

    if args.update_universe:
        from src.sectors.universe_updater import update_universe
        _config_path = os.path.join(os.path.dirname(__file__), 'sectors', 'config', 'sectors.yaml')
        print("Updating stock universe from ETF holdings…")
        update_universe(_config_path)
        print("Re-run with --sectors to generate an updated dashboard.")
        return

    if args.news:
        from src.news import fetch_thematic_news
        from src.news_dashboard import generate_news_dashboard
        from src.config import MARKET_THEMES
        print("Fetching thematic news...")
        news_data = fetch_thematic_news(MARKET_THEMES)
        path = generate_news_dashboard(news_data)
        print(f"Market News Dashboard generated at: {path}")
        webbrowser.open(f"file://{os.path.abspath(path)}")
        return

    if args.sectors or args.sector or args.ai_memo or args.ai_macro_memo:
        from src.sectors.dashboard import run_sector_analysis
        run_sector_analysis(focus_sector=args.sector, ai_memo=args.ai_memo, ai_macro_memo=args.ai_macro_memo)
        return
    
    tickers = args.ticker if args.ticker else DEFAULT_WATCHLIST

    # Validate ticker symbols at the boundary
    ticker_pattern = re.compile(r'^[A-Z0-9]{1,5}([.\-][A-Z]{1,2})?$')
    invalid = [t for t in tickers if not ticker_pattern.match(t.upper())]
    if invalid:
        print(f"Error: Invalid ticker symbol(s): {invalid}")
        print("Tickers must be 1-5 alphanumeric characters (e.g., AAPL, BRK.B)")
        sys.exit(1)
    tickers = [t.upper() for t in tickers]

    summary_reports = []

    print(f"Analyzing {len(tickers)} tickers...")

    # Pre-fetch all data in parallel (I/O bound), then score sequentially (CPU bound)
    data_map = fetch_data_parallel(tickers, period="2y", interval="1wk")
    si_map = fetch_short_interest_parallel(tickers)
    basket_context = fetch_basket_context()

    for t in tickers:
        res = analyze_ticker(t, generate_html=True, prefetched_df=data_map.get(t), prefetched_si=si_map.get(t))
        if res:
            summary_reports.append(res)

    if summary_reports:
        generate_index(summary_reports, basket_context=basket_context)
        index_path = os.path.abspath("reports/index.html")
        print(f"\nAnalysis Complete. Index generated at: {index_path}")
        # Try to open automatically
        webbrowser.open(f"file://{index_path}")
    else:
        print("No reports generated.")

if __name__ == "__main__":
    main()
