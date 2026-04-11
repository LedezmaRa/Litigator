# EMA-ADX-ATR Framework

A data-driven weekly stock analysis framework that scores equity entry points using technical indicators calibrated against 2-year backtest data. Generates interactive HTML dashboards and deploys them automatically to GitHub Pages.

## How It Works

The scoring engine evaluates each ticker on 5 factors (100 points total), targeting the **quiet pullback in a proven trend** — the setup with the best historical risk/reward:

| Factor | Weight | Signal Logic |
|---|---|---|
| EMA Proximity | 20 pts | Sweet spot: 1–2 ATR from EMA20 |
| ADX Value | 30 pts | ADX 25–30 is optimal (74% win rate in backtest) |
| Volume Conviction | 25 pts | **Inverted** — low volume = coiled spring (88% win at <0.5x avg) |
| Structure | 15 pts | EMA20 > EMA50 stack alignment |
| Risk/Reward | 10 pts | ATR-based stop vs. 4x ATR target |

**Rating scale:**
- `85–100` — Optimal Entry
- `65–84` — Good Entry
- `50–64` — Acceptable Entry
- `35–49` — Marginal Entry
- `<35` — Poor Entry

## Dashboards Generated

| Report | Description |
|---|---|
| `index.html` | Command center — all tickers ranked by score with basket macro context |
| `stock_<TICKER>.html` | Per-ticker deep-dive with 13+ intelligence panels |
| `sector_analysis.html` | Sector rotation & relative strength overview |
| `sentiment.html` | Market breadth, VIX, put/call ratio |
| `market_news.html` | Thematic news filtered by macro themes |
| `macro_drivers.html` | AI-generated macro driver memos per sector |

## Intelligence Panels (Per-Ticker)

Each stock dashboard includes:
- EMA/ADX/ATR score breakdown
- Relative Strength (RS) rating vs. S&P 500
- Earnings risk calendar
- Options flow (unusual activity, put/call)
- Dark pool prints
- Volume profile (POC, value area)
- Insider transactions
- Short interest / squeeze score
- Factor scores (momentum, value, quality, low-vol)
- Macro basket membership context
- AI-generated investment narrative

## Macro Basket System

10 macro baskets act as economic sensors rather than stock picks:

- **Risk Appetite** — Growth vs. defensive bifurcation
- **Financial & Credit** — Credit cycle expansion/contraction
- **Consumer Health** — High-end vs. low-end consumer bifurcation
- **Industrial / Capex** — Real economy capital spending
- **Semiconductor Cycle** — Leading indicator for tech capex
- **Housing / Rate Sensitivity** — Fed expectations proxy
- **Energy & Inflation** — Inflation re-acceleration signal
- **AI Infrastructure** — Data center build-out momentum
- **Defense / Geopolitical** — Risk premium gauge
- **China / Global Demand** — Non-US economic recovery proxy

## Setup

**Requirements:** Python 3.9+

```bash
# Clone the repo
git clone <repo-url>
cd ema-adx-atr-framework

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Set your Anthropic API key (required for AI memos)
export ANTHROPIC_API_KEY=your_key_here
```

## Usage

```bash
# Run full pipeline (sectors + watchlist tickers + sentiment + news)
python src/main.py

# Analyze specific tickers
python src/main.py AAPL NVDA MSFT

# Sector analysis only
python src/main.py --sectors

# Focus on a single sector
python src/main.py --sectors --sector XLK

# Generate AI investment memo for top candidates
python src/main.py --ai-memo

# Generate AI macro strategy memo
python src/main.py --ai-macro-memo

# Sentiment & breadth dashboard only
python src/main.py --sentiment

# Thematic news dashboard only
python src/main.py --news

# Refresh ETF holdings → update sector stock universe
python src/main.py --update-universe
```

## Watchlist Configuration

The default watchlist is derived from `src/watchlist_baskets.yaml`. Edit that file to customize the macro baskets and the tickers analyzed by default. Tickers appearing in multiple baskets are deduplicated automatically.

## GitHub Pages Deployment

The included workflow (`.github/workflows/pages.yml`) automatically:
1. Runs `python src/main.py` on every push to `main`/`master`
2. Publishes the `reports/` folder to GitHub Pages
3. Runs on a schedule every weekday at 6 PM UTC

**Required secret:** Add `ANTHROPIC_API_KEY` to your repository's GitHub Actions secrets.

## Backtest Calibration Notes

Scoring weights are calibrated against 820 weekly observations (2-year lookback):

- **ADX direction is noise** — rising vs. falling ADX has zero edge (+2.76% vs +2.77%). Only the value range matters.
- **Low volume outperforms** — stocks with vol <0.5x average return +9.44% with 88% win rate vs. +0.74% for high-volume setups.
- **EMA proximity sweet spot** — 1–2 ATR from EMA20 returns +4.11% at 67% win rate. Being too close (<0.5 ATR) underperforms.

## Disclaimer

This tool is for informational and educational purposes only. Nothing generated constitutes investment advice. Past performance does not guarantee future results. Always consult a licensed financial professional before making investment decisions.
