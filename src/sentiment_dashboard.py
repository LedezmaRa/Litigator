"""
Sentiment & Breadth Dashboard generator.

Aggregates:
  - Market sentiment (VIX, Put/Call ratio, Fear & Greed proxy)
  - Market breadth (% above MAs, new highs/lows)
  - FRED macro regime
  - Basket context (GVIP vs SPY)

Navigation: accessible via the top nav "Sentiment" tab.
Run via:  python3 -m src.main --sentiment
"""
import os
from datetime import datetime
from src.utils.html_utils import CSS_DARK_THEME, INTERACTIVE_JS, generate_top_nav
from src.sentiment import fetch_market_sentiment
from src.breadth import fetch_market_breadth
from src.macro_fred import fetch_macro_regime
from src.baskets import fetch_basket_context


def _gauge_svg(value: float, max_val: float, color: str, size: int = 100) -> str:
    """Mini circular gauge for a 0–max value."""
    pct = min(1.0, max(0.0, value / max_val))
    import math
    r = size // 2 - 6
    circ = 2 * math.pi * r
    offset = circ * (1 - pct)
    return f"""
    <svg width="{size}" height="{size}" style="display:block; margin:0 auto;">
        <circle cx="{size//2}" cy="{size//2}" r="{r}" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="8"/>
        <circle cx="{size//2}" cy="{size//2}" r="{r}" fill="none"
            stroke="{color}" stroke-width="8" stroke-linecap="round"
            stroke-dasharray="{circ:.1f}" stroke-dashoffset="{offset:.1f}"
            transform="rotate(-90 {size//2} {size//2})"/>
        <text x="{size//2}" y="{size//2 + 6}" text-anchor="middle"
            font-size="18" font-weight="700" fill="#e2e8f0">{value:.0f}</text>
    </svg>"""


def _metric_card(label: str, value: str, sub: str, color: str, expl: str = "") -> str:
    return f"""
    <div style="padding:1.25rem; background:rgba(255,255,255,.04); border-radius:10px;
        border:1px solid rgba(255,255,255,.08);">
        <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase;
            letter-spacing:.07em; margin-bottom:6px;">{label}</div>
        <div style="font-size:1.4rem; font-weight:700; color:{color};">{value}</div>
        <div style="font-size:.75rem; color:{color}; margin-top:2px;">{sub}</div>
        {f'<p style="font-size:.7rem; color:var(--text-secondary); margin:.5rem 0 0 0; line-height:1.4;">{expl}</p>' if expl else ''}
    </div>"""


def generate_sentiment_dashboard(output_dir: str = "reports") -> str:
    """Fetch all sentiment/breadth data and write reports/sentiment.html."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("Fetching sentiment data...")
    sent = fetch_market_sentiment()
    print("Fetching breadth data...")
    breadth = fetch_market_breadth(use_cache=True)
    print("Fetching macro regime (FRED)...")
    macro = fetch_macro_regime()
    print("Fetching basket context (GVIP vs SPY)...")
    basket = fetch_basket_context()

    nav_html = generate_top_nav("sentiment")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── SENTIMENT SECTION ────────────────────────────────────────────────────
    fg_score = sent.get('fear_greed_score', 50)
    fg_label = sent.get('fear_greed_label', 'Neutral')
    fg_color = (sent.get('overall_color', 'var(--accent-marginal)'))
    vix_val  = sent.get('vix_value', 0)
    vix_label= sent.get('vix_label', 'N/A')
    vix3m    = sent.get('vix3m_value')
    contango = sent.get('vix_contango_ratio')
    vix_struct=sent.get('vix_structure','N/A')
    pc_ratio = sent.get('equity_pc_ratio')
    pc_label = sent.get('pc_signal', 'N/A')
    ov_sent  = sent.get('overall_sentiment', 'NEUTRAL')
    sent_expl= sent.get('explanation', '')
    sent_interp = sent.get('interpretation', '')

    vix_color  = ('#4ade80' if vix_val < 15 else '#fbbf24' if vix_val < 20 else '#f87171' if vix_val < 30 else '#ef4444')
    fg_gauge   = _gauge_svg(fg_score, 100, fg_color, 120)
    border_sent= ('rgba(74,222,128,.3)' if ov_sent in ('GREED','EXTREME_GREED')
                  else 'rgba(248,113,113,.3)' if ov_sent in ('FEAR','EXTREME_FEAR')
                  else 'rgba(251,191,36,.15)')

    vix_contango_str = f"{contango:.2f}" if contango else "N/A"
    pc_str = f"{pc_ratio:.2f}" if pc_ratio else "N/A"
    vix3m_str = f"{vix3m:.1f}" if vix3m else "N/A"

    sentiment_section = f"""
    <section class="glass-card" style="margin-bottom:2rem; border:1px solid {border_sent};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1.5rem; margin-bottom:1.5rem;">
            <div>
                <h2 style="margin:0 0 .4rem 0;">Market Sentiment</h2>
                <p class="text-muted" style="margin:0; font-size:.85em; max-width:520px;">{sent_expl}</p>
            </div>
            <div style="text-align:center;">
                {fg_gauge}
                <div style="font-size:.85rem; font-weight:600; color:{fg_color}; margin-top:4px;">{fg_label}</div>
                <div style="font-size:.7rem; color:var(--text-secondary);">Fear &amp; Greed Score</div>
            </div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(175px,1fr)); gap:1rem; margin-bottom:1rem;">
            {_metric_card("VIX (30-day)", f"{vix_val:.1f}", vix_label, vix_color,
                "Below 15 = calm markets. Above 30 = fear. Above 40 = panic (historic buy signals).")}
            {_metric_card("VIX3M (90-day)", vix3m_str, vix_struct, vix_color,
                "Contango (VIX3M > VIX) = normal structure. Backwardation = acute near-term fear.")}
            {_metric_card("VIX Contango Ratio", vix_contango_str, "VIX3M ÷ VIX", vix_color,
                ">1.0 = normal/calm. <1.0 = inverted = market stress.")}
            {_metric_card("Equity Put/Call Ratio", pc_str, pc_label, '#e2e8f0',
                ">0.8 = fearful (traders buying puts for protection). <0.5 = complacent (too many calls).")}
        </div>
        <div style="padding:1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
            <p style="margin:0; font-size:.85em; color:var(--text-secondary);">{sent_interp}</p>
        </div>
    </section>"""

    # ── BREADTH SECTION ───────────────────────────────────────────────────────
    b_health = breadth.get('health_score', 50)
    b_label  = breadth.get('health_label', 'MIXED')
    b_color  = breadth.get('health_color', 'var(--accent-marginal)')
    pct20    = breadth.get('pct_above_20wk', 0) or 0
    pct40    = breadth.get('pct_above_40wk', 0) or 0
    net_hl   = breadth.get('net_new_highs', 0) or 0
    ad_trend = breadth.get('ad_trend', 0) or 0
    n_stocks = breadth.get('stocks_analyzed', 0)
    b_expl   = breadth.get('explanation', '')
    b_interp = breadth.get('interpretation', '')

    b_gauge  = _gauge_svg(b_health, 100, b_color, 120)
    b_border = ('rgba(74,222,128,.3)' if b_health >= 65
                else 'rgba(248,113,113,.3)' if b_health < 35
                else 'rgba(251,191,36,.15)')

    def _bar(pct, col):
        return (f'<div style="width:100%; height:10px; background:rgba(255,255,255,.1); border-radius:5px; overflow:hidden; margin:4px 0;">'
                f'<div style="width:{pct:.0f}%; height:100%; background:{col}; border-radius:5px;"></div></div>')

    p20c = 'var(--accent-optimal)' if pct20 >= 60 else 'var(--accent-marginal)' if pct20 >= 40 else 'var(--accent-poor)'
    p40c = 'var(--accent-optimal)' if pct40 >= 50 else 'var(--accent-marginal)' if pct40 >= 30 else 'var(--accent-poor)'
    hlc  = 'var(--accent-optimal)' if net_hl >= 0 else 'var(--accent-poor)'
    adc  = 'var(--accent-optimal)' if ad_trend >= 0 else 'var(--accent-poor)'

    breadth_section = f"""
    <section class="glass-card" style="margin-bottom:2rem; border:1px solid {b_border};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1.5rem; margin-bottom:1.5rem;">
            <div>
                <h2 style="margin:0 0 .4rem 0;">Market Breadth <span class="text-muted" style="font-size:.75rem;">({n_stocks} S&amp;P 500 stocks)</span></h2>
                <p class="text-muted" style="margin:0; font-size:.85em; max-width:520px;">{b_expl}</p>
            </div>
            <div style="text-align:center;">
                {b_gauge}
                <div style="font-size:.85rem; font-weight:600; color:{b_color}; margin-top:4px;">{b_label.replace('_',' ')}</div>
                <div style="font-size:.7rem; color:var(--text-secondary);">Breadth Health</div>
            </div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:1rem; margin-bottom:1rem;">
            <div style="padding:1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; margin-bottom:6px;">% Above 20-Week MA</div>
                {_bar(pct20, p20c)}
                <div style="font-size:1.3rem; font-weight:700; color:{p20c};">{pct20:.1f}%</div>
                <div style="font-size:.7rem; color:var(--text-secondary);">Healthy: &gt;60% · Washed out: &lt;30%</div>
            </div>
            <div style="padding:1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; margin-bottom:6px;">% Above 40-Week MA (≈200d)</div>
                {_bar(pct40, p40c)}
                <div style="font-size:1.3rem; font-weight:700; color:{p40c};">{pct40:.1f}%</div>
                <div style="font-size:.7rem; color:var(--text-secondary);">Bull market: &gt;50% · Bear: &lt;30%</div>
            </div>
            <div style="padding:1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; margin-bottom:6px;">Net New 52-Week Highs</div>
                <div style="font-size:1.3rem; font-weight:700; color:{hlc};">{net_hl:+d}</div>
                <div style="font-size:.7rem; color:var(--text-secondary);">Positive = more new highs than lows</div>
            </div>
            <div style="padding:1rem; background:rgba(255,255,255,.03); border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:.65rem; color:var(--text-secondary); text-transform:uppercase; margin-bottom:6px;">Breadth Trend (4-Week A/D)</div>
                <div style="font-size:1.3rem; font-weight:700; color:{adc};">{ad_trend:+.1f}</div>
                <div style="font-size:.7rem; color:var(--text-secondary);">Positive = improving participation</div>
            </div>
        </div>
        <div style="padding:1rem; background:rgba(255,255,255,.03); border-radius:8px;">
            <p style="margin:0; font-size:.85em; color:var(--text-secondary);">{b_interp}</p>
        </div>
    </section>"""

    # ── MACRO REGIME SECTION ──────────────────────────────────────────────────
    m_score = macro.get('regime_score', 50)
    m_label = macro.get('regime_label', 'CAUTIOUS')
    m_color = macro.get('regime_color', 'var(--accent-marginal)')
    m_expl  = macro.get('regime_explanation', '')
    m_interp= macro.get('interpretation', '')
    m_gauge = _gauge_svg(m_score, 100, m_color, 120)
    m_border= ('rgba(74,222,128,.3)' if m_label == 'RISK_ON'
               else 'rgba(248,113,113,.3)' if m_label == 'RISK_OFF'
               else 'rgba(251,191,36,.15)')

    macro_section = f"""
    <section class="glass-card" style="margin-bottom:2rem; border:1px solid {m_border};">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1.5rem; margin-bottom:1.5rem;">
            <div>
                <h2 style="margin:0 0 .4rem 0;">Macro Regime (FRED)</h2>
                <p class="text-muted" style="margin:0; font-size:.85em; max-width:520px;">{m_expl}</p>
            </div>
            <div style="text-align:center;">
                {m_gauge}
                <div style="font-size:.85rem; font-weight:600; color:{m_color}; margin-top:4px;">{m_label.replace('_',' ')}</div>
                <div style="font-size:.7rem; color:var(--text-secondary);">Regime Score</div>
            </div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:1rem; margin-bottom:1rem;">
            {_metric_card("Yield Curve (10Y–2Y)", f"{macro.get('yield_curve_value') or 0:.2f}%", macro.get('yield_curve_signal') or 'N/A', '#e2e8f0',
                "Positive = healthy. Negative = inverted = recession historically follows within 12–18 months.")}
            {_metric_card("HY Credit Spread", f"{macro.get('hy_spread_value') or 0:.2f}%", macro.get('hy_spread_signal') or 'N/A', '#e2e8f0',
                "High yield spread is the credit market's fear gauge. Wide spreads mean institutions price in defaults and credit stress.")}
            {_metric_card("5Y Inflation Break-even", f"{macro.get('inflation_value') or 0:.2f}%", macro.get('inflation_signal') or 'N/A', '#e2e8f0',
                "Market-implied inflation expectation. Above 2.5% creates headwinds for long-duration and growth stocks.")}
            {_metric_card("NFCI (Financial Conditions)", f"{macro.get('nfci_value') or 0:.3f}", macro.get('nfci_signal') or 'N/A', '#e2e8f0',
                "Chicago Fed index of 105 financial indicators. Negative = loose/supportive. Positive = tight = headwind.")}
        </div>
        <div style="padding:1rem; background:rgba(255,255,255,.03); border-radius:8px;">
            <p style="margin:0; font-size:.85em; color:var(--text-secondary);">{m_interp}</p>
        </div>
    </section>"""

    # ── BASKET CONTEXT ────────────────────────────────────────────────────────
    bc = basket
    bc_signal = bc.get('signal', 'NEUTRAL')
    bc_label  = bc.get('signal_label', 'Neutral')
    bc_color  = bc.get('signal_color', 'var(--accent-marginal)')
    bc_error  = bc.get('error')
    if bc_error or bc.get('relative_5d') is None:
        basket_section = ""
    else:
        gvip_5d = bc['gvip_5d']
        spy_5d  = bc['spy_5d']
        rel_5d  = bc['relative_5d']
        rel_20d = bc['relative_20d']
        def _pctc(v): return 'var(--accent-optimal)' if v >= 0 else 'var(--accent-poor)'
        if bc_signal == 'SHORT_SQUEEZE_REGIME':
            bc_interp = ("GVIP is lagging SPY — the rally is being driven by mechanical short covering, "
                         "not genuine fundamental buying. Treat current market strength with caution.")
        elif bc_signal == 'LONG_BASKET_LEADING':
            bc_interp = ("Hedge fund VIP longs are leading the market. Rallies are fundamentally driven "
                         "— technical setups have higher follow-through probability in this environment.")
        else:
            bc_interp = ("No significant divergence between hedge fund longs and SPY. "
                         "Evaluate entries on their individual technical merit.")
        bc_border = ('rgba(74,222,128,.3)' if bc_signal == 'LONG_BASKET_LEADING'
                     else 'rgba(248,113,113,.3)' if bc_signal == 'SHORT_SQUEEZE_REGIME'
                     else 'rgba(251,191,36,.15)')
        basket_section = f"""
        <section class="glass-card" style="margin-bottom:2rem; border:1px solid {bc_border};">
            <h2 style="margin:0 0 .5rem 0;">Basket Intelligence — GVIP vs SPY</h2>
            <p class="text-muted" style="font-size:.85em; margin:0 0 1rem 0;">
                GVIP tracks the 50 most widely held hedge fund stocks. When GVIP lags SPY,
                the rally is likely short-squeeze driven rather than fundamentally led.
            </p>
            <div style="display:flex; align-items:center; gap:1rem; flex-wrap:wrap; margin-bottom:1rem;">
                <span style="font-size:1.2rem; font-weight:600; color:{bc_color};">{bc_label}</span>
            </div>
            <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:1rem; margin-bottom:1rem;">
                {_metric_card("GVIP 5D", f"{gvip_5d:+.1f}%", f"${bc.get('gvip_price',0):.2f}", _pctc(gvip_5d))}
                {_metric_card("SPY 5D", f"{spy_5d:+.1f}%", f"${bc.get('spy_price',0):.2f}", _pctc(spy_5d))}
                {_metric_card("Relative 5D (GVIP−SPY)", f"{rel_5d:+.1f}%", "Key signal", bc_color)}
                {_metric_card("Relative 20D trend", f"{rel_20d:+.1f}%", "Longer trend", _pctc(rel_20d))}
            </div>
            <div style="padding:1rem; background:rgba(255,255,255,.03); border-radius:8px;">
                <p style="margin:0; font-size:.85em; color:var(--text-secondary);">{bc_interp}</p>
            </div>
        </section>"""

    # ── ASSEMBLE PAGE ─────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sentiment & Breadth | Framework</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>{CSS_DARK_THEME}</style>
</head>
<body>
    {nav_html}
    <div class="container">
        <header style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2.5rem;">
            <div>
                <h1 style="margin:0 0 .4rem 0; background:linear-gradient(to right,#60a5fa,#a78bfa);
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                    Sentiment &amp; Market Health
                </h1>
                <p class="text-muted">Fear, greed, breadth, and macro regime — the ocean your trades swim in.</p>
            </div>
            <span class="badge badge-info">{now}</span>
        </header>

        <!-- Educational intro -->
        <div class="glass-card" style="margin-bottom:2rem; padding:1.25rem 1.5rem; background:rgba(56,189,248,.05); border:1px solid rgba(56,189,248,.2);">
            <h3 style="margin:0 0 .5rem 0; color:#38bdf8; font-size:1rem;">📖 How to Read This Page</h3>
            <p style="margin:0; font-size:.85em; color:var(--text-secondary); line-height:1.6;">
                <strong style="color:#e2e8f0;">Sentiment</strong> tells you the emotional state of market participants — when fear is extreme, nearly everyone who wants to sell has already sold (contrarian buy signal). When greed is extreme, there are no buyers left to push prices higher (caution signal).
                <br><br>
                <strong style="color:#e2e8f0;">Breadth</strong> tells you whether the market move is broad (sustainable) or narrow (risky). A market where only 30% of stocks are above their 50-week MA while the index hits highs is a house built on a crumbling foundation.
                <br><br>
                <strong style="color:#e2e8f0;">Macro Regime</strong> is the context above everything else. Technical setups that form in a RISK_OFF macro environment fail at a much higher rate — you are fighting the tide. Never force entries when the macro is against you.
            </p>
        </div>

        {sentiment_section}
        {breadth_section}
        {macro_section}
        {basket_section}

        <footer style="margin-top:3rem; text-align:center; color:var(--text-secondary); font-size:.875rem; border-top:1px solid rgba(255,255,255,.05); padding-top:2rem;">
            <p>Sentiment &amp; Breadth Dashboard · Generated {now}</p>
        </footer>
    </div>
    {INTERACTIVE_JS}
</body>
</html>"""

    out_path = os.path.join(output_dir, "sentiment.html")
    with open(out_path, "w") as f:
        f.write(html)

    print(f"Sentiment dashboard saved to {out_path}")
    return out_path
