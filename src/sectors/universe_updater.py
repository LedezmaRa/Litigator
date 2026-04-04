"""
Dynamic Stock Universe Updater.

Fetches the current top holdings for each sector ETF from yfinance and
rewrites the 'stocks' section of sectors.yaml. The 'drivers', 'name',
'description', and 'benchmark' keys are preserved unchanged.

Usage (CLI):
    python -m src.main --update-universe

This should be run occasionally (e.g., quarterly) to refresh the stock list
so the sector analysis reflects current ETF constituents.
"""

from typing import Dict, List


def update_universe(config_path: str, top_n: int = 25) -> Dict[str, List[str]]:
    """
    Fetch top ETF holdings via yfinance and rewrite sectors.yaml.

    Args:
        config_path: Absolute path to sectors.yaml
        top_n: Number of top holdings to keep per sector (default 25)

    Returns:
        Dict mapping ETF symbol -> list of updated ticker symbols
    """
    import yfinance as yf
    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f)

    sectors = config.get("sectors", {})
    results: Dict[str, List[str]] = {}

    for etf, info in sectors.items():
        try:
            ticker_obj = yf.Ticker(etf)
            # get_holdings() available in yfinance >= 0.2.x
            if not hasattr(ticker_obj, "get_holdings"):
                print(f"  {etf}: yfinance version too old for get_holdings(), keeping existing")
                continue

            holdings = ticker_obj.get_holdings()
            if holdings is None or holdings.empty:
                print(f"  {etf}: no holdings data returned, keeping existing")
                continue

            if "symbol" not in holdings.columns:
                print(f"  {etf}: unexpected holdings schema (no 'symbol' column), keeping existing")
                continue

            symbols = (
                holdings["symbol"]
                .dropna()
                .astype(str)
                .str.strip()
                .head(top_n)
                .tolist()
            )
            if not symbols:
                print(f"  {etf}: empty symbol list, keeping existing")
                continue

            # Preserve existing company names for tickers that carried over;
            # new tickers get the ticker as their name (dashboard handles this gracefully).
            old_stocks = info.get("stocks", {})
            info["stocks"] = {sym: old_stocks.get(sym, sym) for sym in symbols}
            results[etf] = symbols
            print(f"  {etf}: updated with {len(symbols)} holdings")

        except Exception as e:
            print(f"  {etf}: failed ({e}), keeping existing")

    # Write back — yaml.dump preserves all other top-level keys
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\nUniverse update complete. {len(results)} sector(s) updated.")
    return results
