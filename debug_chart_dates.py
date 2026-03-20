
import yfinance as yf
import pandas as pd

# 1. Fetch Data mimicking main.py and drivers.py
print("Fetching XLY (2y, 1wk)...")
sector_data = yf.download("XLY", period="2y", interval="1wk", progress=False)
sector_close = sector_data["Close"]
if isinstance(sector_close, pd.DataFrame):
     sector_close = sector_close.iloc[:, 0] # Handle multi-index if needed

print(f"Sector Range: {sector_close.index[0]} to {sector_close.index[-1]}")
print(sector_close.tail())

print("\nFetching XRT (1y, 1d)...")
driver_data = yf.download("XRT", period="1y", interval="1d", progress=False)
driver_close = driver_data["Close"]
if isinstance(driver_close, pd.DataFrame):
     driver_close = driver_close.iloc[:, 0]

print(f"Driver Range: {driver_close.index[0]} to {driver_close.index[-1]}")
print(driver_close.tail())

# 2. Test Intersection (Logic from charts.py)
print("\nTesting Intersection...")
prices = driver_close
sector_prices = sector_close

# Ensure timezones match (remove if present)
if prices.index.tz is not None:
    prices.index = prices.index.tz_localize(None)
if sector_prices.index.tz is not None:
    sector_prices.index = sector_prices.index.tz_localize(None)

common_idx = prices.index.intersection(sector_prices.index)
print(f"Intersection Length: {len(common_idx)}")
if len(common_idx) > 0:
    print(f"Intersection Range: {common_idx[0]} to {common_idx[-1]}")
    print("Last 5 common dates:")
    print(common_idx[-5:])
else:
    print("No intersection found!")

# 3. Test Alignment Strategy
print("\nTesting Alignment Strategy (Reindex)...")
# Logic from drivers.py
driver_aligned = driver_close.reindex(sector_close.index, method='ffill')
print(f"Aligned Length: {len(driver_aligned)}")
print(driver_aligned.tail())
