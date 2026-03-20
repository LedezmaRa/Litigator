import os
import json
import anthropic
import markdown
from dotenv import load_dotenv

# Import shared UI components from the framework
from src.dashboard import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav

# Load environment variables from .env file
load_dotenv()

from src.config import MARKET_THEMES, DISCLAIMER_TOP, DISCLAIMER_BOTTOM
from src.news import fetch_thematic_news

SYSTEM_PROMPT = """You are "Joe", Chief Macro Strategist with 25 years of experience — trained as a macroeconomist (former Federal Reserve research economist) and then spent 15 years running a global macro fund at a top-tier hedge fund.

Your core philosophy is "making the fewest errors wins." You look for asymmetric risk/reward, confirmed setups, and strong fundamental underpinnings. You think rigorously from first principles.

Critically: you write for intelligent generalist readers who are NOT macro experts. Your memos are famous on Wall Street for explaining BOTH the verdict AND the mechanism — you never state a conclusion without explaining exactly why the causal chain produces it. Think Ray Dalio's "How the Economic Machine Works" combined with Stanley Druckenmiller's decisiveness.

You have been provided with data detailing the top macro drivers for 11 S&P sectors, including their short-term trends, 1-month changes, and 90-day correlations, as well as a brief summary of recent thematic macro news to provide real-world context.

Your task:
1. Review the provided macro drivers, correlation data, and thematic news context across all sectors.
2. Provide a comprehensive, multi-paragraph state-of-the-market executive summary. Start from first principles — what does the rate regime, commodity signals, currency dynamics, recent global news themes, and credit conditions collectively tell us about where we are in the economic cycle? Explain the mechanisms clearly for a non-expert reader. What is the dominant narrative the data is telling us?
3. Provide a dedicated 'Deep-Dive' analysis for ALL 11 sectors (XLK, XLF, XLV, XLY, XLP, XLE, XLI, XLB, XLU, XLRE, XLC). For EACH sector you must:
   - Name the 1-2 most impactful macro drivers from the data
   - Explain the MECHANISM: why does this driver affect this sector? (e.g., "Rising yields compress P/E multiples because..." — always explain the 'because')
   - Identify any divergences, hidden risks, or asymmetric setups worth noting
   - Give a clear verdict: Bullish / Bearish / Neutral with conviction level (High / Moderate / Low)
4. End with a brief Summary Table of all 11 sectors and a "Final Word" paragraph.
5. Format in clear Markdown with headers. Bold tickers and key metrics.

Be decisive and educational. Cite the actual data provided. Never give generic advice — always tie your reasoning directly to the numbers in the data.
"""

def generate_macro_investment_memo(drivers_data: dict, output_dir: str = "reports"):
    """
    Calls the Anthropic API to generate a macro investment memo based on sector drivers,
    then formats the Markdown response into a styled HTML dashboard page.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in environment variables. Cannot generate AI Macro Memo.")
        return

    print("Generating AI Macro Investment Memo (this may take 15-30 seconds)...")

    print("Fetching recent socio-economic and market news context...")
    news_data = fetch_thematic_news(MARKET_THEMES)

    # Serialize candidate data into a readable format for the AI
    ai_context = {
        "macro_drivers_and_correlations": drivers_data,
        "recent_thematic_news": {
            theme: [{"title": a.title, "source": a.source} for a in articles]
            for theme, articles in news_data.items()
        }
    }
    prompt_data = json.dumps(ai_context, indent=2)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=8000,
            temperature=0.3,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Here is the framework data for the sector macro drivers and correlations:\n\n{prompt_data}\n\nPlease provide your state-of-the-market summary and key sector analysis."
                }
            ]
        )
        
        # The AI's response in markdown
        memo_markdown = response.content[0].text
        
        # Convert markdown to html using python-markdown
        memo_html_content = markdown.markdown(memo_markdown)
        
        # Build the final HTML using the framework's theme
        full_html = f'''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Macro AI Strategy | Command Center</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
            <style>
                {{CSS_DARK_THEME}}
                .memo-content {{
                    background: var(--card-bg);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: var(--card-border);
                    border-radius: 1rem;
                    padding: 2.5rem;
                    box-shadow: var(--glass-shadow);
                    max-width: 900px;
                    margin: 0 auto;
                    font-size: 1.1rem;
                    line-height: 1.8;
                }}
                .memo-content h1, .memo-content h2, .memo-content h3 {{
                    color: var(--accent-info);
                    margin-top: 2rem;
                    margin-bottom: 1rem;
                }}
                .memo-content p {{
                    margin-bottom: 1.5rem;
                    color: var(--text-primary);
                }}
                .memo-content strong {{
                    color: #fff;
                    font-weight: 600;
                }}
                .memo-content ul, .memo-content ol {{
                    margin-bottom: 1.5rem;
                    padding-left: 2rem;
                }}
                .memo-content li {{
                    margin-bottom: 0.5rem;
                }}
            </style>
        </head>
        <body>
            {generate_top_nav("ai_macro_memo")}
            <div class="container">
                <header style="text-align: center; margin-bottom: 3rem;">
                    <h1 style="background: linear-gradient(to right, #38bdf8, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5rem;">
                        Macro AI Strategy Memo
                    </h1>
                    <p class="text-muted" style="margin-bottom: 2rem;">Generated by "Joe" | Powered by Anthropic Claude Opus</p>
                    <div style="max-width: 800px; margin: 0 auto; padding: 1rem; background: rgba(255,100,100,0.1); border-left: 4px solid var(--accent-poor); text-align: left; font-size: 0.85rem; color: var(--text-secondary);">
                        <strong>DISCLAIMER:</strong> {DISCLAIMER_TOP}
                    </div>
                </header>

                <div class="memo-content">
                    {memo_html_content}
                </div>
                
                <div style="max-width: 900px; margin: 3rem auto 0; padding: 1.5rem; background: rgba(30, 41, 59, 0.5); border-radius: 0.5rem; border: 1px solid rgba(255,255,255,0.05); font-size: 0.8rem; color: var(--text-secondary); line-height: 1.6;">
                    {DISCLAIMER_BOTTOM.replace(chr(10), '<br>')}
                </div>
            </div>
            
            <footer style="margin-top:4rem; text-align:center; color:var(--text-secondary);">
                <p>Macro AI Strategy Memo • Unified Intelligence Layer</p>
            </footer>
        </body>
        </html>
        '''

        # Clean up double braces introduced by f-string escaping
        full_html = full_html.replace("{CSS_DARK_THEME}", CSS_DARK_THEME)

        os.makedirs(output_dir, exist_ok=True)
        out_file = os.path.join(output_dir, "ai_macro_memo.html")
        with open(out_file, "w") as f:
            f.write(full_html)
            
        print(f"✅ AI Macro Strategy Memo successfully generated at {out_file}")

    except Exception as e:
        print(f"Error generating AI Macro Memo: {e}")
