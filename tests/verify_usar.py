"""
Verification script to reproduce the USAR case study from the framework document.
"""
import pandas as pd
import numpy as np
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.scoring import EntryScorer
from src.config import EMA_FAST_PERIOD, EMA_SLOW_PERIOD

def create_mock_df(price, atr, adx, vol_mult, structure_good, rr_good):
    """
    Creates a DataFrame with specific technical conditions.
    """
    # Create valid timestamp
    dates = pd.date_range(end='2026-01-26', periods=100)
    df = pd.DataFrame(index=dates)
    
    # Defaults
    df['Close'] = price
    df['Open'] = price # Minimal movement
    df['High'] = price 
    df['Low'] = price 
    df['Volume'] = 1000000
    df['Vol_Avg'] = 1000000
    df[f'EMA_{EMA_FAST_PERIOD}'] = price # Reset later
    df[f'EMA_{EMA_SLOW_PERIOD}'] = price * 0.9
    df['ATR'] = atr
    df['ADX'] = adx
    
    # 1. EMA Proximity Setup
    # Doc: "25 points (0.5x ATR distance)" for Jan 5
    # If Price=15.80, Distance=0.5ATR. 
    # Distance = (Price - EMA20) / ATR. 
    # 0.5 = (15.80 - EMA20) / ATR. 
    # EMA20 = 15.80 - 0.5*ATR.
    # Let's verify logic.
    
    # 2. ADX Setup
    # "ADX 25-27, rising"
    # Current ADX is passed. Need slope > 0.
    # Set historical ADX lower.
    df.loc[df.index[-6], 'ADX'] = adx - 2.0
    
    # 3. Volume Setup
    # "Volume > 1.5x average"
    # Price > 2% up needed for 15 points? 
    # Doc Jan 5: "Volume: 15 points (>1.5x average)"
    # Code (mine) requires Price > 2% for 1.5x.
    # So Open should be lower.
    df.loc[df.index[-1], 'Volume'] = 1000000 * vol_mult
    if vol_mult > 1.5:
        # Assume price up > 2%
        df.loc[df.index[-1], 'Open'] = price * 0.97
        df.loc[df.index[-2], 'Close'] = price * 0.97
        
        # ADVANCED VOLUME:
        # 1. RV > 1.5 -> Score 8 or 10
        # 2. VPC
        df['Vol_VPC'] = 0.8 # High correlation -> Score 10
        # 3. Ratio
        df['Vol_UD_Ratio'] = 2.5 # Buyers dominating -> Score 10
        # Avg Score: (10 + 10 + 10) / 3 * 2 = 20. (Or 8+10+10 if RV < 2).
        
        # If vol_mult = 1.6 (Jan 5), RV=1.6 -> Score 8.
        # VPC=10. Ratio=10. Avg=9.33. Final=18.6 -> 19?
        # WAIT. Opt #3 scale outputs 0-10 avg. Mapped to 0-20.
        # Jan 5 had "15 points".
        # If I get 18.6, I am OVER-scoring compared to original Doc?
        # Or did original Doc use simple logic?
        # "Week 3-4 ... Integrate into overall scoring".
        # So the New Score might be different.
        # I should try to tune mock to match "Optimal" rating even if exact number shifts.
        pass
        
    elif vol_mult > 1.2:
        df.loc[df.index[-1], 'Open'] = price * 0.985 # 1.5%
        df.loc[df.index[-2], 'Close'] = price * 0.985
        df['Vol_VPC'] = 0.5 # Moderate -> 6
        df['Vol_UD_Ratio'] = 1.2 # Balanced -> 4
        # Avg: (6 + 6 + 4) / 3 = 5.33. Final = 10.6.
    else:
        df['Vol_VPC'] = 0.2
        df['Vol_UD_Ratio'] = 0.8
    
    # 4. Structure Setup
    # "20 points (clean, new formation)"
    # Needs stack + EMA50 slope > 1% + bars > 5
    if structure_good:
        # VALID STACK: Close > EMA20 > EMA50
        # Ensure this condition holds for last 6 days
        # First set baseline for all days
        for i in range(1, 7):
            df.loc[df.index[-i], f'EMA_{EMA_SLOW_PERIOD}'] = price * 0.8
            # EMA20 needs to be below previous close (which might be lower due to volume dip)
            # We'll set EMA20 generic first
            df.loc[df.index[-i], f'EMA_{EMA_FAST_PERIOD}'] = price - (0.6 * atr) 
            df.loc[df.index[-i], 'Close'] = price # Default
        
        # EMA50 Rising > 1% compared to 5 days ago
        ema50_curr = df[f'EMA_{EMA_SLOW_PERIOD}'].iloc[-1]
        df.loc[df.index[-6], f'EMA_{EMA_SLOW_PERIOD}'] = ema50_curr * 0.98 # 2% rise
        
        # NOW apply Volume Adjustments (Price Change impact)
        # Verify if we need price change > 2%
        if vol_mult > 1.5:
             # Need ~3% rise.
             prev_close_target = price * 0.97
             df.loc[df.index[-2], 'Close'] = prev_close_target
             df.loc[df.index[-1], 'Open'] = prev_close_target
             
             # Ensure index[-2] is still > EMA20
             # EMA20 is price - 0.6*atr.
             # e.g. 15.80 - 0.6 = 15.20.
             # PrevClose = 15.32.
             # 15.32 > 15.20. OK!
        elif vol_mult > 1.2:
             # Need ~1.5% rise
             prev_close_target = price * 0.985
             df.loc[df.index[-2], 'Close'] = prev_close_target
             df.loc[df.index[-1], 'Open'] = prev_close_target
        
        # Finally Set TODAY's Proximity exactly
        # Doc: "0.5x ATR distance". 
        # Price - EMA = 0.5 * ATR
        # EMA = Price - 0.5 * ATR
        df.loc[df.index[-1], f'EMA_{EMA_FAST_PERIOD}'] = price - (0.5 * atr)

    else:
        # "Valid but stretched" (15 points?)
        # Structure score: Good (15) = Stack + Rising + >3 bars.
        # Jan 26: 15 points.
        
        # Setup history for valid stack
        for i in range(1, 7):
           df.loc[df.index[-i], f'EMA_{EMA_SLOW_PERIOD}'] = price * 0.6
           df.loc[df.index[-i], f'EMA_{EMA_FAST_PERIOD}'] = price - (3.6 * atr)
           df.loc[df.index[-i], 'Close'] = price
           
        # EMA50 slope minimal (< 1%) or flat?
        # Make it rising < 1%
        ema50_curr = df[f'EMA_{EMA_SLOW_PERIOD}'].iloc[-1]
        df.loc[df.index[-6], f'EMA_{EMA_SLOW_PERIOD}'] = ema50_curr * 0.995 # 0.5% rise
        
        # Apply Volume logic if any (Jan 26 has vol_mult 1.3, so >1.2 rule applies)
        if vol_mult > 1.2:
             prev_close_target = price * 0.985
             df.loc[df.index[-2], 'Close'] = prev_close_target
             df.loc[df.index[-1], 'Open'] = prev_close_target



    # 5. R:R Setup
    # "10 points (4:1+)"
    # My code uses ratio = 5*ATR / (Price - (EMA20 - 1.5*ATR))
    # For Jan 5: Price 15.80. EMA20 near 15.80 (prox 0.5).
    # Stop = EMA20 - 1.5ATR.
    # Risk approx 2 ATR. Reward 5 ATR. Ratio 2.5?
    # Wait, if Proximity is 0.5, Price=EMA+0.5ATR. Stop=EMA-1.5ATR. Risk=2ATR.
    # Ratio = 5 / 2 = 2.5. Score would be 6.
    # Doc says 10 points.
    # Doc calculation: `R:R_ratio = potential_move / stop_distance`.
    # It implies Potential > 8-10 ATR? Or Stop is tighter?
    # Maybe Stop is just below 20MA?
    # In Jan 5 example: "Entry at 15.80... initial stop 13.00". Risk = 2.80.
    # Gain was 77% ($28). Move was $12.20. Ratio = 4.35.
    # Ah, the "Potential" was analyzed as big.
    # My automated system assumes 5ATR.
    # To reproduce SCORE, I might need to override the R:R logic or manually inject R:R for this test if `EntryScorer` allowed it.
    # But `EntryScorer` calculates it.
    # To get 10 points, R:R > 4.
    # Assume 5ATR reward. Risk must be < 1.25 ATR.
    # Risk = Price - Stop. Stop = EMA - 1.5ATR.
    # Risk = (EMA + Dist) - (EMA - 1.5ATR) = Dist + 1.5ATR.
    # So Dist + 1.5ATR < 1.25 ATR?? Impossible if Dist >= 0.
    # CONCLUSION: The Doc's R:R of 4:1 assumes a target MUCH larger than 5 ATR, OR a tighter stop.
    # Or Proximity was 0.
    # If I want to match the doc score 95, I need R:R to be 10.
    # This reveals a discrepancy in my automation assumption vs manual analysis.
    # I will stick to my code's logic. If it scores 91 instead of 95, that's fine, as long as it's "Optimal".
    
    return df

def run_verification():
    print("Running USAR Verification...\n")
    
    # JAN 5 CASE
    # Proximity: 0.5 ATR (25 pts)
    # ADX: 25-27 Rising (25 pts)
    # Volume: >1.5x (15 pts) in doc. My code: Needs >1.5x + >2% price.
    # Structure: 20 pts.
    # R:R: 10 pts.
    # Total Doc: 95.
    
    # My assumptions might give:
    # Prox: 25.
    # ADX: 25.
    # Vol: 15.
    # Str: 20.
    # RR: If Risk ~2ATR, Reward 5ATR -> Ratio 2.5 -> Score 6.
    # Total: 91. Still Optimal (>90).
    
    df_jan5 = create_mock_df(
        price=15.80, 
        atr=1.0, 
        adx=26.0, 
        vol_mult=1.6, 
        structure_good=True, 
        rr_good=True
    )
    scorer5 = EntryScorer(df_jan5)
    res5 = scorer5.score()
    
    print(f"JAN 5 PREDICTION:")
    print(f"Total Score: {res5.total_score} (Expected ~95)")
    print(res5.breakdown)
    print("-" * 30)

    # JAN 26 CASE
    # Price $28.00.
    # Prox: 3.6 ATR (0 pts)
    # ADX: 38 (10 pts)
    # Volume: Moderate (10 pts). Code: >1.2x? Or just avg. Doc says 10 pts.
    # Structure: 15 pts.
    # R:R: 0 pts.
    # Total Doc: 35.
    
    df_jan26 = create_mock_df(
        price=28.00, 
        atr=2.0, 
        adx=38.0, 
        vol_mult=1.3, # 1.2-1.5 -> 10 pts
        structure_good=False, 
        rr_good=False
    )
    scorer26 = EntryScorer(df_jan26)
    res26 = scorer26.score()
    
    print(f"JAN 26 PREDICTION:")
    print(f"Total Score: {res26.total_score} (Expected ~35)")
    print(res26.breakdown)
    
if __name__ == "__main__":
    run_verification()
