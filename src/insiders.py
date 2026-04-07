"""
Insider transaction tracking from SEC EDGAR Form 4 filings.

Fetches Form 4 (Statement of Changes in Beneficial Ownership) filings via the
SEC EDGAR full-text search API. Open-market purchases (code 'P') and open-market
sales (code 'S') are the primary signals — these reflect insiders voluntarily
spending or receiving their own money at market prices.

All functions return a dict with at minimum 'explanation' and 'interpretation'
keys so callers can surface plain-English teaching alongside the raw numbers.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_SEC_HEADERS = {
    "User-Agent": "Research Framework research@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}

_EXPLANATION = (
    "Form 4 filings are public disclosures that corporate insiders (executives, "
    "directors, and >10% shareholders) must submit within 2 business days of buying "
    "or selling their company's stock. Open-market purchases — where insiders spend "
    "their own money at market price — are the most bullish signal because insiders "
    "have no incentive to buy unless they believe the stock is undervalued. Research "
    "shows companies with cluster buying (3+ insiders in 30 days) outperform the "
    "market by 6-8% over the following 6 months."
)

_DEFAULT_RESULT: Dict[str, Any] = {
    "buy_count": 0,
    "sell_count": 0,
    "unique_buyers": 0,
    "cluster_signal": False,
    "net_sentiment": "NEUTRAL",
    "signal_strength": "NONE",
    "recent_transactions": [],
    "explanation": _EXPLANATION,
    "interpretation": (
        "No insider transaction data could be retrieved at this time. "
        "This may be a temporary data availability issue with SEC EDGAR."
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _edgar_full_text_search(ticker: str, start_date: str, end_date: str) -> List[Dict]:
    """
    Query SEC EDGAR full-text search for Form 4 filings mentioning the ticker.

    Returns a list of hit dicts from the EDGAR search response, or an empty list
    on any failure.
    """
    url = (
        "https://efts.sec.gov/LATEST/search-index?"
        f"q=%22{ticker}%22"
        "&forms=4"
        "&dateRange=custom"
        f"&startdt={start_date}"
        f"&enddt={end_date}"
        "&hits.hits._source=period_of_report,entity_name,file_date,file_num"
    )
    try:
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=15)
        if not resp.ok:
            return []
        data = resp.json()
        return data.get("hits", {}).get("hits", [])
    except Exception:
        return []


def _edgar_submissions_api(ticker: str) -> Optional[Dict]:
    """
    Try to resolve a ticker to its CIK via the SEC EDGAR company tickers JSON,
    then fetch the submissions endpoint which contains recent filing history.
    """
    # Step 1: resolve ticker -> CIK
    try:
        tickers_url = "https://www.sec.gov/files/company_tickers.json"
        resp = requests.get(tickers_url, headers=_SEC_HEADERS, timeout=15)
        if not resp.ok:
            return None
        companies = resp.json()
        ticker_upper = ticker.upper()
        cik = None
        for _, info in companies.items():
            if info.get("ticker", "").upper() == ticker_upper:
                cik = str(info["cik_str"]).zfill(10)
                break
        if cik is None:
            return None
    except Exception:
        return None

    # Step 2: fetch submissions
    try:
        sub_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(sub_url, headers=_SEC_HEADERS, timeout=15)
        if not resp.ok:
            return None
        return resp.json()
    except Exception:
        return None


def _parse_submissions_for_form4(
    submissions: Dict, lookback_days: int
) -> List[Dict[str, str]]:
    """
    Extract Form 4 filing metadata from a submissions response dict.

    Returns list of dicts: {date, accession_number, entity_name}.
    """
    cutoff = datetime.now() - timedelta(days=lookback_days)
    results: List[Dict[str, str]] = []

    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    reporters = recent.get("reportingOwner", []) if "reportingOwner" in recent else []

    for i, form in enumerate(forms):
        if form != "4":
            continue
        file_date_str = dates[i] if i < len(dates) else ""
        try:
            file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff:
            continue
        accession = accessions[i] if i < len(accessions) else ""
        results.append(
            {
                "date": file_date_str,
                "accession_number": accession,
                "entity_name": "",  # populated below if reporter list exists
            }
        )

    # If submissions includes a list of files beyond the recent window, ignore them —
    # the recent dict covers 1,000 most-recent filings which is sufficient.
    return results


def _fetch_form4_xml(accession_number: str, cik_padded: str) -> Optional[str]:
    """
    Download the primary Form 4 XML document for a given accession number.
    Returns the raw XML string or None on failure.
    """
    acc_clean = accession_number.replace("-", "")
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik_padded)}/"
        f"{acc_clean}/{accession_number}.xml"
    )
    try:
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=10)
        if resp.ok:
            return resp.text
    except Exception:
        pass
    return None


def _parse_transaction_code_from_xml(xml_text: str) -> List[Dict[str, str]]:
    """
    Minimally parse a Form 4 XML to extract transaction codes and reporter name.
    Returns list of dicts: {transaction_code, reporter_name}.
    """
    transactions = []
    # Reporter name
    name_match = re.search(
        r"<rptOwnerName>(.*?)</rptOwnerName>", xml_text, re.IGNORECASE
    )
    reporter_name = name_match.group(1).strip() if name_match else "Unknown"

    # Transaction rows
    for tc_match in re.finditer(
        r"<transactionCode>(.*?)</transactionCode>", xml_text, re.IGNORECASE
    ):
        transactions.append(
            {"transaction_code": tc_match.group(1).strip(), "reporter_name": reporter_name}
        )
    return transactions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_insider_transactions(ticker: str, lookback_days: int = 90) -> dict:
    """
    Fetch and analyze SEC EDGAR Form 4 insider transactions for a ticker.

    Uses the SEC EDGAR submissions API as the primary source (reliable, structured).
    Falls back to the EDGAR full-text search endpoint if the submissions route fails.
    Transaction codes parsed:
      'P' = open-market purchase (most bullish)
      'S' = open-market sale

    Args:
        ticker: Stock symbol, e.g. 'AAPL'.
        lookback_days: How many calendar days back to search (default 90).

    Returns:
        dict with keys: buy_count, sell_count, unique_buyers, cluster_signal,
        net_sentiment, signal_strength, recent_transactions, explanation,
        interpretation.
    """
    ticker = ticker.upper().strip()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    start_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    buy_transactions: List[Dict[str, str]] = []
    sell_transactions: List[Dict[str, str]] = []
    recent_transactions: List[Dict[str, str]] = []

    # ------------------------------------------------------------------
    # Primary path: EDGAR submissions API  (gives structured data fast)
    # ------------------------------------------------------------------
    submissions = _edgar_submissions_api(ticker)

    if submissions:
        # Rebuild CIK for potential XML fetches later
        cik_raw = submissions.get("cik", "0")
        cik_padded = str(cik_raw).zfill(10)

        filings = _parse_submissions_for_form4(submissions, lookback_days)

        for filing in filings[:50]:  # cap to avoid rate-limit hammering
            xml_text = _fetch_form4_xml(filing["accession_number"], cik_padded)
            if not xml_text:
                continue
            txns = _parse_transaction_code_from_xml(xml_text)
            for txn in txns:
                code = txn["transaction_code"]
                name = txn["reporter_name"]
                date = filing["date"]
                record = {"date": date, "type": code, "filer_name": name}
                if code == "P":
                    buy_transactions.append(record)
                    recent_transactions.append({**record, "action": "BUY"})
                elif code == "S":
                    sell_transactions.append(record)
                    recent_transactions.append({**record, "action": "SELL"})
            time.sleep(0.1)  # polite crawl rate per SEC guidelines

    # ------------------------------------------------------------------
    # Fallback path: EDGAR full-text search (metadata only, no codes)
    # ------------------------------------------------------------------
    if not submissions:
        hits = _edgar_full_text_search(ticker, start_date, end_date)
        for hit in hits[:20]:
            source = hit.get("_source", {})
            record = {
                "date": source.get("file_date", source.get("period_of_report", "")),
                "type": "UNKNOWN",
                "filer_name": source.get("entity_name", "Unknown"),
                "action": "UNKNOWN",
            }
            recent_transactions.append(record)

    # ------------------------------------------------------------------
    # Aggregate metrics
    # ------------------------------------------------------------------
    buy_count = len(buy_transactions)
    sell_count = len(sell_transactions)

    unique_buyers = len({t["filer_name"] for t in buy_transactions})

    # Cluster signal: 2+ distinct insiders bought in last 30 days
    recent_buyers_30d = {
        t["filer_name"]
        for t in buy_transactions
        if t.get("date", "") >= start_30d
    }
    cluster_signal = len(recent_buyers_30d) >= 2

    # Net sentiment
    if buy_count > sell_count + 2:
        net_sentiment = "BULLISH"
    elif sell_count > buy_count + 2:
        net_sentiment = "BEARISH"
    else:
        net_sentiment = "NEUTRAL"

    # Signal strength
    if unique_buyers >= 3 and cluster_signal:
        signal_strength = "STRONG"
    elif unique_buyers >= 2 or buy_count >= 3:
        signal_strength = "MODERATE"
    elif buy_count >= 1:
        signal_strength = "WEAK"
    else:
        signal_strength = "NONE"

    # ------------------------------------------------------------------
    # Interpretation (dynamic)
    # ------------------------------------------------------------------
    if signal_strength == "STRONG" and net_sentiment == "BULLISH":
        interpretation = (
            f"Strong insider buying signal — {unique_buyers} insiders have made "
            f"open-market purchases in the last {lookback_days} days. This is one of "
            "the highest-conviction signals available because insiders are spending "
            "their own money at market prices."
        )
    elif signal_strength == "MODERATE" and net_sentiment == "BULLISH":
        interpretation = (
            f"Moderate insider buying activity — {buy_count} open-market purchase "
            f"transaction(s) from {unique_buyers} insider(s) over the past "
            f"{lookback_days} days. Not yet at cluster-buy threshold but worth "
            "monitoring for follow-through."
        )
    elif net_sentiment == "BEARISH":
        interpretation = (
            f"Insider selling is outpacing buying ({sell_count} sells vs "
            f"{buy_count} buys). Note: insiders sell for many reasons (diversification, "
            "taxes, personal needs) so selling alone is less meaningful than the "
            "absence of buying. Monitor for cluster selling across multiple insiders."
        )
    elif signal_strength == "WEAK":
        interpretation = (
            f"Minimal insider activity — {buy_count} purchase(s) recorded in the "
            f"past {lookback_days} days. A single buyer is suggestive but not "
            "statistically significant on its own."
        )
    else:
        interpretation = (
            f"No significant insider buying or selling activity detected in the past "
            f"{lookback_days} days. This is the most common reading — absence of "
            "signal, not a negative indicator."
        )

    # Sort recent by date descending, keep top 15
    recent_transactions.sort(key=lambda x: x.get("date", ""), reverse=True)
    recent_transactions = recent_transactions[:15]

    return {
        "buy_count": buy_count,
        "sell_count": sell_count,
        "unique_buyers": unique_buyers,
        "cluster_signal": cluster_signal,
        "net_sentiment": net_sentiment,
        "signal_strength": signal_strength,
        "recent_transactions": recent_transactions,
        "explanation": _EXPLANATION,
        "interpretation": interpretation,
    }
