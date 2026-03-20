import os
import json
import anthropic
from dotenv import load_dotenv

# Import shared UI components from the framework
from src.dashboard import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav

# Load environment variables from .env file
load_dotenv()

from src.config import DISCLAIMER_TOP, DISCLAIMER_BOTTOM

SYSTEM_PROMPT = """You are "Joe", Chief Market Strategist and Top-Tier Portfolio Manager with 25 years of experience. You previously ran a global macro fund and now focus on selecting the best individual equities across the S&P 500.

Your core philosophy is "making the fewest errors wins." You strictly look for asymmetric risk/reward profiles, confirmed technical setups, and strong fundamental narratives.

Critically: you write for intelligent generalist readers who are NOT quantitative experts. Your memos are famous on Wall Street for explaining BOTH the verdict AND the mechanism — you never state a stock pick without explaining exactly why the causal chain makes it a great setup.

You have been provided with data for the top stock candidates across 11 S&P sectors, which have already passed a rigorous quantitative screening framework (EMA/ADX/ATR).

Your task:
1. Review the provided candidate data.
2. Select the Top 5 stocks that you believe are poised for the most significant and safest growth over the next 12 months.
3. Start with a brief (2-3 sentences) executive summary of your overall market view based on the candidates that screened well.
4. For EACH of the 5 stocks, you MUST use the following exact structure:

### [1-5]. [Company Name] ([Ticker])

**The Setup**: Identify the primary technical driver from the data (e.g., ADX momentum, SMA crossover, ATR volatility compression) and what the price action suggests.

**The Catalyst**: Briefly explain the core fundamental narrative or macroeconomic tailwind driving this specific company.

**The Mechanism**: This is the most important part. Explain exactly WHY the technical setup aligns with the fundamental narrative. Connect the dots. (e.g., "The tightening ATR suggests institutional accumulation, which makes complete sense given their recent earnings beat and massive buyback program...")

**Hidden Risks**: Identify any divergences or sector-level risks.

Do not recommend more than 5 stocks. Be decisive and educational. Cite the actual data provided.
"""

def generate_investment_memo(candidates_data: list, output_dir: str = "reports"):
    """
    Calls the Anthropic API to generate an investment memo based on the top candidates,
    then formats the Markdown response into a styled HTML dashboard page.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in environment variables. Cannot generate AI Memo.")
        return

    print("Generating AI Investment Memo (this may take 15-30 seconds)...")

    # Serialize candidate data into a readable format for the AI
    prompt_data = json.dumps(candidates_data, indent=2)

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
                    "content": f"Here is the framework data for the top candidates:\n\n{prompt_data}\n\nPlease provide your Top 5 picks and investment memo."
                }
            ]
        )
        
        # The AI's response in markdown
        memo_markdown = response.content[0].text
        
        # In a real scenario we might use the 'markdown' library to convert robustly,
        # but for simplicity and avoiding another dependency, we can do a very basic 
        # html wrap, or we can use the python `markdown` library. Let's install and use `markdown`.
        import markdown
        memo_html_content = markdown.markdown(memo_markdown)
        
        # Build the final HTML using the framework's theme
        full_html = f'''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>AI Strategy Memo | Command Center</title>
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
            {generate_top_nav("ai_memo")}
            <div class="container">
                <header style="text-align: center; margin-bottom: 3rem;">
                    <h1 style="background: linear-gradient(to right, #38bdf8, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5rem;">
                        AI Investment Strategy Memo
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
                <p>AI Strategy Memo • Unified Intelligence Layer</p>
            </footer>
        </body>
        </html>
        '''

        # Clean up double braces introduced by f-string escaping
        full_html = full_html.replace("{CSS_DARK_THEME}", CSS_DARK_THEME)

        os.makedirs(output_dir, exist_ok=True)
        out_file = os.path.join(output_dir, "ai_memo.html")
        with open(out_file, "w") as f:
            f.write(full_html)
            
        print(f"✅ AI Investment Memo successfully generated at {out_file}")

    except Exception as e:
        print(f"Error generating AI Memo: {e}")
