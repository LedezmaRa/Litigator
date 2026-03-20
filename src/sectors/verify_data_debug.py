
import yfinance as yf
import pandas as pd
import sys

print("Python Executable:", sys.executable)
print("Pandas Version:", pd.__version__)
print("YFinance Version:", yf.__version__)

ticker = "XRT"
print(f"\nFetching {ticker} (1y, 1d)...")
data = yf.download(ticker, period="1y", interval="1d", progress=False)

if isinstance(data.columns, pd.MultiIndex):
    print("MultiIndex detected, flattening...")
    data.columns = [c[0] for c in data.columns] # or c[1] depending on shape, usually Ticker is level 0 if grouped?
    # Actually if single ticker + period, yf might return just OHLC cols.
    # Group_by='ticker' (used in drivers.py) changes structure. Let's start simple.

print("\nData Head:")
print(data.head())
print("\nData Tail:")
print(data.tail())

print("\nNaN Count:")
print(data.isna().sum())

print("\nChecking last 5 'Close' values:")
try:
    if "Close" in data.columns:
        print(data["Close"].tail(10))
    elif "close" in data.columns:
        print(data["close"].tail(10))
    else:
        # If MultiIndex columns like (Close, XRT)
        print(data.iloc[:, :].tail())
except Exception as e:
    print(f"Error accessing Close: {e}")
