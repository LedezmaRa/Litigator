"""
Main CLI entry point for the Optimized EMA-ADX-ATR Framework.
"""
import argparse
import sys
import os
import webbrowser
from datetime import datetime
import pandas as pd

# Adjust path to allow imports if running from top level
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.data import fetch_data, validate_data
from src.indicators import calculate_all_indicators
from src.scoring import EntryScorer
from src.config import EMA_FAST_PERIOD, EMA_SLOW_PERIOD
from src.dashboard import generate_dashboard, generate_index

DEFAULT_WATCHLIST = ["HAL", "AVGO", "AMZN", "NVDA", "GOOGL", "NEE", "NTFX", "HLT", "USAR", "UUUU", "MP"]

def analyze_ticker(ticker: str, generate_html: bool = True) -> dict:
    """
    Analyzes a single ticker and prints the report.
    Returns a dict with summary info if successful.
    """
    try:
        # 1. Fetch Data (PRIMARY: WEEKLY)
        # Framework 2.0 Focus: Weekly Timeframe
        # Need ~50-100 weeks for proper EMA50 and ADX stability
        df = fetch_data(ticker, period="2y", interval="1wk")
        validate_data(df, min_records=52) # Ensure at least 1 year of data
        
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
            path = generate_dashboard(ticker, df, result, "WEEKLY")
            print(f"Dashboard generated: {path}")
            
            # Helper metrics
            ema_dist = (price - ema20) / atr if atr > 0 else 0
            rel_vol = df['Volume'].iloc[-1] / df['Vol_Avg'].iloc[-1] if df['Vol_Avg'].iloc[-1] > 0 else 0
            
            # Recalculate R:R for conservative stop
            risk = price - stop_conservative
            reward = target_5r - price
            rr_ratio = reward / risk if risk > 0 else 0
            
            return {
                'ticker': ticker,
                'score': result.total_score,
                'trend': "WEEKLY",
                'regime': result.regime,
                'path': path,
                # Rich Dashboard fields
                'close': price,
                'ema20': ema20,
                'ema50': result.details['ema50'],
                'ema_dist': ema_dist,
                'adx': result.details['adx'],
                'rel_vol': rel_vol,
                'rr': rr_ratio
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

    args = parser.parse_args()

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
    summary_reports = []
    
    print(f"Analyzing {len(tickers)} tickers...")
    
    for t in tickers:
        res = analyze_ticker(t, generate_html=True)
        if res:
            summary_reports.append(res)
            
    if summary_reports:
        generate_index(summary_reports)
        index_path = os.path.abspath("reports/index.html")
        print(f"\nAnalysis Complete. Index generated at: {index_path}")
        # Try to open automatically
        webbrowser.open(f"file://{index_path}")
    else:
        print("No reports generated.")

if __name__ == "__main__":
    main()
