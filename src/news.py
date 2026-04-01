import requests
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Dict
from bs4 import BeautifulSoup
import urllib.parse

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1

@dataclass
class ThematicNewsItem:
    title: str
    link: str
    pub_date: str
    source: str

def fetch_thematic_news(themes: List[str], max_items: int = 5) -> Dict[str, List[ThematicNewsItem]]:
    """
    Fetches thematic news from Google News RSS.
    Returns a dictionary mapping each theme to a list of ThematicNewsItem objects.
    """
    results = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    for theme in themes:
        query = urllib.parse.quote_plus(theme)
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        items = []
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()

                root = ET.fromstring(response.content)
                for item in root.findall('./channel/item')[:max_items]:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    pub_date_elem = item.find('pubDate')
                    source_elem = item.find('source')

                    title = title_elem.text if title_elem is not None else "No Title"
                    title = BeautifulSoup(title, "html.parser").get_text()

                    link = link_elem.text if link_elem is not None else ""
                    pub_date = pub_date_elem.text if pub_date_elem is not None else ""
                    source = source_elem.text if source_elem is not None else "Unknown"

                    items.append(ThematicNewsItem(title=title, link=link, pub_date=pub_date, source=source))
                break  # Success — exit retry loop
            except Exception as e:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                else:
                    print(f"Failed to fetch news for theme '{theme}' after {MAX_RETRIES} attempts: {e}")
            
        results[theme] = items
        
    return results

if __name__ == "__main__":
    # Test script to verify the RSS scraper locally
    res = fetch_thematic_news(["Stagflation"])
    for t, articles in res.items():
        print(f"Theme: {t}")
        for a in articles:
            print(f" - {a.title} ({a.source})")
