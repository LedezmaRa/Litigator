"""
Fundamental data fetching for individual stock narrative pages.

Uses yfinance with disk caching to avoid API spam.
Gracefully handles missing data - not all stocks have all fields.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

# Cache configuration
FUNDAMENTALS_CACHE_DIR = Path.home() / ".ema_adx_atr_cache" / "fundamentals"
DEFAULT_TTL_HOURS = 24  # Fundamentals don't change often


@dataclass
class ExecutiveInfo:
    """Executive/officer information."""
    name: str
    title: str
    age: Optional[int] = None
    total_pay: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AnalystRatings:
    """Analyst recommendation summary."""
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_buy: int = 0
    strong_sell: int = 0
    total_analysts: int = 0
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    target_current: Optional[float] = None
    recommendation: str = ""  # e.g., "Strong Buy"

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class UpgradeDowngrade:
    """Single analyst action."""
    date: str  # ISO format string
    firm: str
    to_grade: str
    from_grade: str = ""
    action: str = ""  # upgrade/downgrade/maintain

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NewsItem:
    """Single news article."""
    title: str
    publisher: str
    link: str
    published: str  # ISO format string
    summary: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class EarningsInfo:
    """Earnings-related information."""
    next_date: Optional[str] = None  # ISO format
    eps_estimate: Optional[float] = None
    revenue_estimate: Optional[float] = None
    days_until: Optional[int] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StockFundamentals:
    """Complete fundamental data for a stock."""
    ticker: str

    # Company Overview
    name: str = ""
    sector: str = ""
    industry: str = ""
    business_summary: str = ""
    website: str = ""
    employees: Optional[int] = None

    # Current Price
    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    day_change_pct: Optional[float] = None

    # Key Metrics - Valuation
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    enterprise_value: Optional[float] = None

    # Key Metrics - Growth & Profitability
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    profit_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None

    # Key Metrics - Risk & Other
    beta: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None

    # Leadership
    executives: List[ExecutiveInfo] = field(default_factory=list)

    # Analyst Data
    analyst_ratings: Optional[AnalystRatings] = None
    upgrades_downgrades: List[UpgradeDowngrade] = field(default_factory=list)

    # Catalysts
    earnings: Optional[EarningsInfo] = None
    news: List[NewsItem] = field(default_factory=list)

    # Metadata
    fetched_at: Optional[str] = None
    fetch_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        # Convert nested dataclasses
        d['executives'] = [e if isinstance(e, dict) else asdict(e) for e in self.executives]
        d['upgrades_downgrades'] = [u if isinstance(u, dict) else asdict(u) for u in self.upgrades_downgrades]
        d['news'] = [n if isinstance(n, dict) else asdict(n) for n in self.news]
        if self.analyst_ratings:
            d['analyst_ratings'] = asdict(self.analyst_ratings) if not isinstance(self.analyst_ratings, dict) else self.analyst_ratings
        if self.earnings:
            d['earnings'] = asdict(self.earnings) if not isinstance(self.earnings, dict) else self.earnings
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> 'StockFundamentals':
        """Create from dictionary (for cache loading)."""
        # Parse nested objects
        executives = [ExecutiveInfo(**e) for e in d.get('executives', [])]
        upgrades = [UpgradeDowngrade(**u) for u in d.get('upgrades_downgrades', [])]
        news = [NewsItem(**n) for n in d.get('news', [])]
        ratings = AnalystRatings(**d['analyst_ratings']) if d.get('analyst_ratings') else None
        earnings = EarningsInfo(**d['earnings']) if d.get('earnings') else None

        # Remove nested keys before passing to constructor
        d = {k: v for k, v in d.items() if k not in ['executives', 'upgrades_downgrades', 'news', 'analyst_ratings', 'earnings']}

        return cls(
            **d,
            executives=executives,
            upgrades_downgrades=upgrades,
            news=news,
            analyst_ratings=ratings,
            earnings=earnings
        )


def _get_cache_path(ticker: str) -> Path:
    """Get cache file path for a ticker."""
    return FUNDAMENTALS_CACHE_DIR / f"{ticker.upper()}_fundamentals.json"


def _is_cache_valid(cache_path: Path, ttl_hours: int = DEFAULT_TTL_HOURS) -> bool:
    """Check if cache file exists and is within TTL."""
    if not cache_path.exists():
        return False
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=ttl_hours)


def read_fundamentals_cache(ticker: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> Optional[StockFundamentals]:
    """Read cached fundamentals if valid."""
    cache_path = _get_cache_path(ticker)
    if _is_cache_valid(cache_path, ttl_hours):
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            return StockFundamentals.from_dict(data)
        except Exception:
            return None
    return None


def write_fundamentals_cache(ticker: str, data: StockFundamentals) -> bool:
    """Write fundamentals to cache."""
    FUNDAMENTALS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _get_cache_path(ticker)
    try:
        with open(cache_path, 'w') as f:
            json.dump(data.to_dict(), f, indent=2, default=str)
        return True
    except Exception as e:
        print(f"Cache write failed for {ticker}: {e}")
        return False


def _parse_executives(officers: List[Dict]) -> List[ExecutiveInfo]:
    """Parse companyOfficers list from yfinance info."""
    executives = []
    for officer in officers[:5]:  # Top 5 executives
        try:
            executives.append(ExecutiveInfo(
                name=officer.get('name', 'Unknown'),
                title=officer.get('title', 'Executive'),
                age=officer.get('age'),
                total_pay=officer.get('totalPay')
            ))
        except Exception:
            continue
    return executives


def _parse_analyst_ratings(ticker_obj: yf.Ticker) -> Optional[AnalystRatings]:
    """Parse recommendations and price targets."""
    try:
        # Get recommendation counts
        recs = ticker_obj.recommendations
        if recs is not None and not recs.empty:
            # Get most recent period (row 0)
            latest = recs.iloc[0]
            strong_buy = int(latest.get('strongBuy', 0))
            buy = int(latest.get('buy', 0))
            hold = int(latest.get('hold', 0))
            sell = int(latest.get('sell', 0))
            strong_sell = int(latest.get('strongSell', 0))
        else:
            strong_buy = buy = hold = sell = strong_sell = 0

        # Get price targets
        targets = ticker_obj.analyst_price_targets
        if targets:
            target_mean = targets.get('mean')
            target_high = targets.get('high')
            target_low = targets.get('low')
            target_current = targets.get('current')
        else:
            target_mean = target_high = target_low = target_current = None

        # Get recommendation text from info
        info = ticker_obj.info
        recommendation = info.get('recommendationKey', '').replace('_', ' ').title()

        total = strong_buy + buy + hold + sell + strong_sell

        return AnalystRatings(
            buy=buy,
            hold=hold,
            sell=sell,
            strong_buy=strong_buy,
            strong_sell=strong_sell,
            total_analysts=total,
            target_mean=target_mean,
            target_high=target_high,
            target_low=target_low,
            target_current=target_current,
            recommendation=recommendation
        )
    except Exception:
        return None


def _parse_upgrades_downgrades(ticker_obj: yf.Ticker, limit: int = 10) -> List[UpgradeDowngrade]:
    """Parse recent analyst actions."""
    upgrades = []
    try:
        ud = ticker_obj.upgrades_downgrades
        if ud is not None and not ud.empty:
            for idx, row in ud.head(limit).iterrows():
                try:
                    date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10]
                    upgrades.append(UpgradeDowngrade(
                        date=date_str,
                        firm=row.get('Firm', 'Unknown'),
                        to_grade=row.get('ToGrade', ''),
                        from_grade=row.get('FromGrade', ''),
                        action=row.get('Action', '')
                    ))
                except Exception:
                    continue
    except Exception:
        pass
    return upgrades


def _parse_news(ticker_obj: yf.Ticker, limit: int = 5) -> List[NewsItem]:
    """Parse recent news articles."""
    news_items = []
    try:
        news = ticker_obj.news
        if news:
            for article in news[:limit]:
                try:
                    content = article.get('content', {})
                    title = content.get('title', article.get('title', 'No title'))
                    publisher = content.get('provider', {}).get('displayName', 'Unknown')
                    link = content.get('canonicalUrl', {}).get('url', article.get('link', '#'))
                    pub_date = content.get('pubDate', '')
                    summary = content.get('summary', '')

                    # Parse date
                    if pub_date:
                        try:
                            dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                            pub_date = dt.strftime('%Y-%m-%d')
                        except Exception:
                            pub_date = pub_date[:10]

                    news_items.append(NewsItem(
                        title=title,
                        publisher=publisher,
                        link=link,
                        published=pub_date,
                        summary=summary[:200] if summary else ''
                    ))
                except Exception:
                    continue
    except Exception:
        pass
    return news_items


def _parse_earnings(ticker_obj: yf.Ticker) -> Optional[EarningsInfo]:
    """Parse earnings calendar data."""
    try:
        calendar = ticker_obj.calendar
        if calendar:
            # calendar can be a dict or DataFrame
            if isinstance(calendar, dict):
                earnings_dates = calendar.get('Earnings Date', [])
                if earnings_dates:
                    next_date = earnings_dates[0]
                    if hasattr(next_date, 'strftime'):
                        date_str = next_date.strftime('%Y-%m-%d')
                    else:
                        date_str = str(next_date)[:10]

                    # Calculate days until
                    try:
                        earnings_dt = datetime.strptime(date_str, '%Y-%m-%d')
                        days_until = (earnings_dt - datetime.now()).days
                    except Exception:
                        days_until = None

                    # Get estimates
                    eps_est = calendar.get('Earnings Average')
                    rev_est = calendar.get('Revenue Average')

                    return EarningsInfo(
                        next_date=date_str,
                        eps_estimate=eps_est,
                        revenue_estimate=rev_est,
                        days_until=days_until
                    )
    except Exception:
        pass
    return None


def fetch_stock_fundamentals(
    ticker: str,
    use_cache: bool = True,
    cache_ttl_hours: int = DEFAULT_TTL_HOURS
) -> StockFundamentals:
    """
    Fetch comprehensive fundamental data for a stock.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')
        use_cache: Whether to use disk cache
        cache_ttl_hours: Cache time-to-live (default 24 hours)

    Returns:
        StockFundamentals dataclass with all available data
    """
    ticker = ticker.upper()

    # Step 1: Check cache
    if use_cache:
        cached = read_fundamentals_cache(ticker, cache_ttl_hours)
        if cached:
            return cached

    errors = []

    # Step 2: Fetch from yfinance
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info
    except Exception as e:
        errors.append(f"Failed to fetch info: {e}")
        info = {}

    # Step 3: Parse company overview
    name = info.get('longName', info.get('shortName', ticker))
    sector = info.get('sector', info.get('sectorDisp', ''))
    industry = info.get('industry', info.get('industryDisp', ''))
    business_summary = info.get('longBusinessSummary', '')
    website = info.get('website', '')
    employees = info.get('fullTimeEmployees')

    # Step 4: Parse price data
    current_price = info.get('currentPrice', info.get('regularMarketPrice'))
    previous_close = info.get('previousClose', info.get('regularMarketPreviousClose'))
    if current_price and previous_close:
        day_change_pct = ((current_price - previous_close) / previous_close) * 100
    else:
        day_change_pct = None

    # Step 5: Parse key metrics
    market_cap = info.get('marketCap')
    pe_ratio = info.get('trailingPE')
    forward_pe = info.get('forwardPE')
    peg_ratio = info.get('pegRatio')
    price_to_book = info.get('priceToBook')
    price_to_sales = info.get('priceToSalesTrailing12Months')
    enterprise_value = info.get('enterpriseValue')

    revenue = info.get('totalRevenue')
    revenue_growth = info.get('revenueGrowth')
    earnings_growth = info.get('earningsGrowth')
    gross_margin = info.get('grossMargins')
    operating_margin = info.get('operatingMargins')
    profit_margin = info.get('profitMargins')
    roe = info.get('returnOnEquity')
    roa = info.get('returnOnAssets')

    beta = info.get('beta')
    debt_to_equity = info.get('debtToEquity')
    current_ratio = info.get('currentRatio')
    dividend_yield = info.get('dividendYield')
    fifty_two_week_high = info.get('fiftyTwoWeekHigh')
    fifty_two_week_low = info.get('fiftyTwoWeekLow')

    # Step 6: Parse executives
    try:
        executives = _parse_executives(info.get('companyOfficers', []))
    except Exception as e:
        errors.append(f"executives: {e}")
        executives = []

    # Step 7: Parse analyst data
    try:
        ratings = _parse_analyst_ratings(yf_ticker)
    except Exception as e:
        errors.append(f"ratings: {e}")
        ratings = None

    try:
        upgrades = _parse_upgrades_downgrades(yf_ticker)
    except Exception as e:
        errors.append(f"upgrades: {e}")
        upgrades = []

    # Step 8: Parse news
    try:
        news = _parse_news(yf_ticker)
    except Exception as e:
        errors.append(f"news: {e}")
        news = []

    # Step 9: Parse earnings
    try:
        earnings = _parse_earnings(yf_ticker)
    except Exception as e:
        errors.append(f"earnings: {e}")
        earnings = None

    # Step 10: Construct result
    result = StockFundamentals(
        ticker=ticker,
        name=name,
        sector=sector,
        industry=industry,
        business_summary=business_summary,
        website=website,
        employees=employees,
        current_price=current_price,
        previous_close=previous_close,
        day_change_pct=day_change_pct,
        market_cap=market_cap,
        pe_ratio=pe_ratio,
        forward_pe=forward_pe,
        peg_ratio=peg_ratio,
        price_to_book=price_to_book,
        price_to_sales=price_to_sales,
        enterprise_value=enterprise_value,
        revenue=revenue,
        revenue_growth=revenue_growth,
        earnings_growth=earnings_growth,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        profit_margin=profit_margin,
        roe=roe,
        roa=roa,
        beta=beta,
        debt_to_equity=debt_to_equity,
        current_ratio=current_ratio,
        dividend_yield=dividend_yield,
        fifty_two_week_high=fifty_two_week_high,
        fifty_two_week_low=fifty_two_week_low,
        executives=executives,
        analyst_ratings=ratings,
        upgrades_downgrades=upgrades,
        earnings=earnings,
        news=news,
        fetched_at=datetime.now().isoformat(),
        fetch_errors=errors
    )

    # Step 11: Cache result
    if use_cache:
        write_fundamentals_cache(ticker, result)

    return result


def fetch_fundamentals_parallel(
    tickers: List[str],
    max_workers: int = 10,
    use_cache: bool = True
) -> Dict[str, StockFundamentals]:
    """
    Fetch fundamentals for multiple tickers in parallel.

    Args:
        tickers: List of stock symbols
        max_workers: Maximum parallel threads
        use_cache: Whether to use disk cache

    Returns:
        Dict mapping ticker -> StockFundamentals
    """
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_stock_fundamentals, ticker, use_cache): ticker
            for ticker in tickers
        }

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                results[ticker] = future.result()
            except Exception as e:
                print(f"Failed to fetch fundamentals for {ticker}: {e}")
                results[ticker] = StockFundamentals(
                    ticker=ticker,
                    fetch_errors=[str(e)]
                )

    return results


def clear_fundamentals_cache() -> int:
    """Clear all cached fundamentals data."""
    count = 0
    if FUNDAMENTALS_CACHE_DIR.exists():
        for f in FUNDAMENTALS_CACHE_DIR.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
    return count
