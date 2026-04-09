import os
from datetime import datetime
from typing import Dict, List
from src.news import ThematicNewsItem
from src.utils.html_utils import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav

def generate_news_dashboard(themes_news: Dict[str, List[ThematicNewsItem]], output_dir: str = "reports") -> str:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Build the HTML content for themes
    themes_html = ""
    for theme, articles in themes_news.items():
        articles_html = ""
        if not articles:
            articles_html = '<p class="text-muted">No recent news found for this theme.</p>'
        else:
            for article in articles:
                date_str = article.pub_date.replace(" GMT", "") if article.pub_date else "Recent"
                articles_html += f"""
                <div style="margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <div style="display:flex; justify-content:space-between; margin-bottom: 0.5rem;">
                        <span class="text-xs text-muted font-mono">{date_str}</span>
                        <span class="badge badge-info">{article.source}</span>
                    </div>
                    <a href="{article.link}" target="_blank" style="display: block; text-decoration: none;">
                        <h3 style="font-size: 1.1rem; line-height: 1.4; color: var(--text-primary); transition: color 0.2s;" onmouseover="this.style.color='var(--accent-info)'" onmouseout="this.style.color='var(--text-primary)'">{article.title}</h3>
                    </a>
                </div>
                """

        themes_html += f"""
        <div class="glass-card" style="margin-bottom: 2rem;">
            <h2 style="font-size: 1.5rem; border-left: 4px solid var(--accent-optimal); padding-left: 1rem; margin-bottom: 1.5rem;">{theme}</h2>
            {articles_html}
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Market Themes News | Command Center</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>{CSS_DARK_THEME}</style>
    </head>
    <body>
        {generate_top_nav("market_news")}
        <div class="container">
            <header style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3rem;">
                <div>
                    <h1 style="margin-bottom:0.5rem; background: linear-gradient(to right, #60a5fa, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Market Themes News</h1>
                    <p class="text-muted">Key Drivers & Macro Themes Tracker</p>
                </div>
                <div>
                  <span class="badge badge-info">{datetime.now().strftime("%Y-%m-%d")}</span>
                </div>
            </header>

            <div class="grid-cols-2" style="gap: 2rem; align-items: start;">
                {themes_html}
            </div>

            <footer style="margin-top:3rem; text-align:center; color:var(--text-secondary); font-size:0.875rem;">
                <p>Curated by Antigravity Agent. Market data and news are delayed.</p>
            </footer>
        </div>
        {INTERACTIVE_JS}
    </body>
    </html>
    """

    file_path = os.path.join(output_dir, "market_news.html")
    with open(file_path, "w") as f:
        f.write(html)

    return file_path
