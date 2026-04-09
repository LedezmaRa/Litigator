"""
Shared HTML/UI building blocks for all dashboard generators.

This is the single source of truth for:
  - CSS_DARK_THEME   — the global dark stylesheet (inline-embedded in every page)
  - INTERACTIVE_JS   — sortable tables, search, watchlist, chart tooltips
  - generate_top_nav()     — sticky nav bar shared by all top-level pages
  - generate_breadcrumb()  — contextual breadcrumb for stock/sector/macro pages
  - generate_page_shell()  — convenience wrapper that produces a full HTML document

Design decisions
----------------
* CSS and JS are embedded inline (not linked as external files) because the
  reports are opened directly in a browser with no web server — relative file
  URLs are unreliable across subdirectories.
* All color decisions flow through CSS custom properties defined in :root.
  Python code that needs a dynamic color should call get_score_color() from
  ui_utils.py, which returns 'var(--accent-*)' strings.
* Layout / spacing that appears in 3+ places lives as a CSS utility class here
  (e.g. .flex-between, .mb-1) so Python templates use class= not style=.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Global dark theme stylesheet
# ---------------------------------------------------------------------------
CSS_DARK_THEME = """
:root {
    --bg-color: #0f172a;
    --card-bg: rgba(30, 41, 59, 0.7);
    --card-border: 1px solid rgba(255, 255, 255, 0.1);
    --text-primary: #e2e8f0;
    --text-secondary: #a8b4c2;
    --accent-optimal: #4ade80;
    --accent-good: #34d399;
    --accent-marginal: #fbbf24;
    --accent-poor: #f87171;
    --accent-info: #38bdf8;
    --font-main: 'Inter', system-ui, -apple-system, sans-serif;
    --glass-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
}

/* ── Base ───────────────────────────────────────────────────────────────── */
body {
    background-color: var(--bg-color);
    color: var(--text-primary);
    font-family: var(--font-main);
    margin: 0;
    padding: 0;
    line-height: 1.6;
    background-image:
        radial-gradient(at 0%   0%, hsla(253,16%,7%,1) 0, transparent 50%),
        radial-gradient(at 50%  0%, hsla(225,39%,30%,1) 0, transparent 50%),
        radial-gradient(at 100% 0%, hsla(339,49%,30%,1) 0, transparent 50%);
    min-height: 100vh;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 2rem;
}

/* ── Glassmorphism Card ─────────────────────────────────────────────────── */
.glass-card {
    background: var(--card-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: var(--card-border);
    border-radius: 1rem;
    padding: 1.5rem;
    box-shadow: var(--glass-shadow);
}

/* ── Typography ─────────────────────────────────────────────────────────── */
h1, h2, h3, h4 { margin-top: 0; color: #fff; font-weight: 600; }
.text-muted   { color: var(--text-secondary); }
.text-sm      { font-size: 0.875rem; }
.text-xs      { font-size: 0.75rem; }
.font-mono    { font-family: 'JetBrains Mono', monospace; }

/* ── Status Badges ──────────────────────────────────────────────────────── */
.badge {
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.badge-optimal    { background: rgba(74,222,128,0.2);  color: #4ade80; border: 1px solid rgba(74,222,128,0.3); }
.badge-good       { background: rgba(52,211,153,0.2);  color: #34d399; border: 1px solid rgba(52,211,153,0.3); }
.badge-acceptable { background: rgba(251,191,36,0.15); color: #e2b84a; border: 1px solid rgba(251,191,36,0.4); }
.badge-marginal   { background: rgba(251,191,36,0.2);  color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }
.badge-poor       { background: rgba(248,113,113,0.2); color: #f87171; border: 1px solid rgba(248,113,113,0.3); }
.badge-info       { background: rgba(56,189,248,0.2);  color: #38bdf8; border: 1px solid rgba(56,189,248,0.3); }

/* ── Score Hero ─────────────────────────────────────────────────────────── */
/*
 * Add class="score-hero" (or .score-hero-card) to the primary status card to
 * give it a coloured glow matching the score tier.
 * Set --hero-color inline on the element: style="--hero-color:var(--accent-optimal)"
 *
 * .score-hero-value  — large standalone number (use when NOT embedding a gauge ring)
 * .score-hero-label  — small uppercase caption beneath the number
 *
 * NOTE: the existing .score-value class is used INSIDE .score-ring-container;
 * we intentionally avoid overriding it here to prevent gauge ring conflicts.
 */
.score-hero {
    border-color: var(--hero-color, rgba(74,222,128,0.25)) !important;
    background: linear-gradient(
        135deg,
        rgba(30,41,59,0.85) 0%,
        rgba(15,23,42,0.95) 100%
    ) !important;
    box-shadow: 0 0 0 1px var(--hero-color, rgba(74,222,128,0.2)),
                0 8px 32px rgba(0,0,0,0.3);
    position: relative;
}
/* Subtle coloured top-edge accent */
.score-hero::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--hero-color, var(--accent-optimal));
    border-radius: 1rem 1rem 0 0;
    opacity: 0.7;
}
.score-hero-value {
    font-size: 4rem;
    font-weight: 800;
    line-height: 1;
    color: var(--hero-color, var(--accent-optimal));
}
.score-hero-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-secondary);
}

/* ── Score Gauge Ring ───────────────────────────────────────────────────── */
.score-ring-container {
    position: relative;
    width: 120px;
    height: 120px;
    display: flex;
    justify-content: center;
    align-items: center;
}
.score-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: #fff;
    z-index: 10;
}
.score-circle-bg { fill: none; stroke: rgba(255,255,255,0.1); stroke-width: 8; }
.score-circle-fg {
    fill: none;
    stroke-width: 8;
    stroke-linecap: round;
    transform: rotate(-90deg);
    transform-origin: 50% 50%;
    transition: stroke-dashoffset 1s ease-out;
}

/* ── Grid Layouts ───────────────────────────────────────────────────────── */
.grid-cols-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 1.5rem; }
.grid-cols-2 { display: grid; grid-template-columns: repeat(2,1fr); gap: 1.5rem; }
@media (max-width: 1024px) { .grid-cols-3 { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 768px)  { .grid-cols-3, .grid-cols-2 { grid-template-columns: 1fr; } }

/* ── HUD Metrics ────────────────────────────────────────────────────────── */
.metric-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.metric-item:last-child { border-bottom: none; }
.progress-bar-bg {
    width: 100px;
    height: 6px;
    background: rgba(255,255,255,0.1);
    border-radius: 3px;
    overflow: hidden;
}
.progress-bar-fg { height: 100%; border-radius: 3px; }

/* ── Data Table ─────────────────────────────────────────────────────────── */
.modern-table { width: 100%; border-collapse: separate; border-spacing: 0 0.5rem; }
.modern-table th {
    padding: 1rem;
    color: var(--text-secondary);
    font-weight: 500;
    font-size: 0.875rem;
    text-align: left;
}
.modern-table td {
    padding: 1rem;
    background: rgba(30,41,59,0.5);
    border-top: 1px solid rgba(255,255,255,0.05);
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.modern-table td:first-child {
    border-top-left-radius: 0.5rem;
    border-bottom-left-radius: 0.5rem;
    border-left: 1px solid rgba(255,255,255,0.05);
}
.modern-table td:last-child {
    border-top-right-radius: 0.5rem;
    border-bottom-right-radius: 0.5rem;
    border-right: 1px solid rgba(255,255,255,0.05);
}
.modern-table tr:hover td {
    background: rgba(30,41,59,0.8);
    cursor: pointer;
    transform: scale(1.005);
    transition: all 0.2s;
}

/* ── Mobile-Responsive Table (stacks as cards below 720 px) ────────────── */
@media (max-width: 720px) {
    .modern-table thead { display: none; }
    .modern-table,
    .modern-table tbody,
    .modern-table tr,
    .modern-table td { display: block; width: 100%; }
    .modern-table tr {
        background: rgba(30,41,59,0.5);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 0.75rem;
        margin-bottom: 0.75rem;
        padding: 0.5rem;
    }
    .modern-table td {
        display: flex;
        justify-content: space-between;
        padding: 0.4rem 0.75rem;
        border: none;
        border-radius: 0;
    }
    /* Each <td data-label="Score"> shows its column label via pseudo-element */
    .modern-table td[data-label]::before {
        content: attr(data-label);
        font-size: 0.7rem;
        text-transform: uppercase;
        color: var(--text-secondary);
        font-weight: 600;
        letter-spacing: 0.05em;
        white-space: nowrap;
        margin-right: 0.5rem;
    }
    /* Reset first/last child border radius overrides from desktop */
    .modern-table td:first-child,
    .modern-table td:last-child {
        border-radius: 0;
        border: none;
    }
}

/* ── Links ──────────────────────────────────────────────────────────────── */
a { color: inherit; text-decoration: none; }
.back-link {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    margin-bottom: 1.5rem;
    transition: color 0.2s;
}
.back-link:hover { color: #fff; }

/* ── Breadcrumb ─────────────────────────────────────────────────────────── */
.breadcrumb {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
    font-size: 0.875rem;
}
.breadcrumb a {
    color: var(--text-secondary);
    text-decoration: none;
    transition: color 0.2s;
}
.breadcrumb a:hover { color: var(--text-primary); }
.breadcrumb .bc-sep { color: var(--text-secondary); opacity: 0.5; }
.breadcrumb .bc-current { color: var(--text-primary); font-weight: 500; }

/* ── Sortable Table Headers ─────────────────────────────────────────────── */
.modern-table th.sortable {
    cursor: pointer;
    user-select: none;
    position: relative;
    padding-right: 1.5rem;
}
.modern-table th.sortable:hover { color: var(--text-primary); }
.modern-table th.sortable::after      { content: '⇅'; position: absolute; right: 0.5rem; opacity: 0.4; font-size: 0.7rem; }
.modern-table th.sortable.asc::after  { content: '↑'; opacity: 1; color: var(--accent-optimal); }
.modern-table th.sortable.desc::after { content: '↓'; opacity: 1; color: var(--accent-optimal); }

/* ── Search Input ───────────────────────────────────────────────────────── */
.search-input {
    background: rgba(30,41,59,0.7);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    color: var(--text-primary);
    font-size: 1rem;
    width: 100%;
    max-width: 600px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.search-input:focus {
    border-color: var(--accent-info);
    box-shadow: 0 0 0 3px rgba(56,189,248,0.1);
}
.search-input::placeholder { color: var(--text-secondary); }

/* ── Filter Controls ────────────────────────────────────────────────────── */
.filter-bar { display: flex; gap: 1rem; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; }
.filter-btn {
    background: rgba(30,41,59,0.7);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 0.5rem;
    padding: 0.5rem 1rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
}
.filter-btn:hover { background: rgba(30,41,59,0.9); color: var(--text-primary); }
.filter-btn.active {
    background: rgba(74,222,128,0.2);
    border-color: rgba(74,222,128,0.3);
    color: var(--accent-optimal);
}

/* ── Chart Tooltip ──────────────────────────────────────────────────────── */
.chart-tooltip {
    position: fixed;
    background: rgba(15,23,42,0.95);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 0.5rem;
    padding: 0.75rem;
    font-size: 0.75rem;
    color: var(--text-primary);
    pointer-events: none;
    z-index: 1000;
    box-shadow: 0 10px 25px rgba(0,0,0,0.3);
    display: none;
}
.chart-tooltip.visible { display: block; }

/* ── Stock Card Hover ───────────────────────────────────────────────────── */
.glass-card.stock-card { transition: transform 0.2s, box-shadow 0.2s; }
.glass-card.stock-card:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.3); }

/* ── Utility ────────────────────────────────────────────────────────────── */
.hidden         { display: none !important; }
.text-positive  { color: var(--accent-optimal); }
.text-negative  { color: var(--accent-poor); }
.flex-between   { display: flex; justify-content: space-between; align-items: center; }
.flex-center    { display: flex; justify-content: center; align-items: center; }
.flex-wrap      { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.flex-col       { display: flex; flex-direction: column; }
.text-center    { text-align: center; }
.text-right     { text-align: right; }
.m-0            { margin: 0; }
.mb-0           { margin-bottom: 0 !important; }
.mb-1           { margin-bottom: 0.5rem; }
.mb-2           { margin-bottom: 1rem; }
.mb-3           { margin-bottom: 1.5rem; }
.mb-4           { margin-bottom: 2rem; }
.mb-6           { margin-bottom: 3rem; }
.mt-1           { margin-top: 0.5rem; }
.mt-2           { margin-top: 1rem; }
.mt-3           { margin-top: 1.5rem; }
.mt-4           { margin-top: 2rem; }
.mt-6           { margin-top: 3rem; }
.gap-1          { gap: 0.5rem; }
.gap-2          { gap: 1rem; }
.gap-3          { gap: 1.5rem; }
.gap-4          { gap: 2rem; }
.font-bold      { font-weight: 700; }
.font-600       { font-weight: 600; }
.overflow-hidden { overflow: hidden; }
.uppercase      { text-transform: uppercase; }
.tracking-wide  { letter-spacing: 0.05em; }

/* ── Stock Narrative Extras ─────────────────────────────────────────────── */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 0.75rem;
}
.metric-card {
    background: rgba(30,41,59,0.5);
    padding: 0.75rem;
    border-radius: 0.5rem;
    border: 1px solid rgba(255,255,255,0.05);
}
.hero-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 1rem;
}
@media (max-width: 768px) {
    .hero-header { flex-direction: column; }
    .metric-grid { grid-template-columns: repeat(2,1fr); }
}

/* ── Top Navigation Menu ────────────────────────────────────────────────── */
.top-nav {
    display: flex;
    justify-content: center;
    align-items: center;
    background: rgba(15,23,42,0.8);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding: 1rem 2rem;
    position: sticky;
    top: 0;
    z-index: 1000;
    margin-bottom: 2rem;
}
.top-nav-list {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 1.5rem;
    list-style: none;
    margin: 0;
    padding: 0;
}
.nav-item {
    color: var(--text-secondary);
    text-decoration: none;
    font-weight: 500;
    font-size: 0.95rem;
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    transition: all 0.2s ease;
}
.nav-item:hover {
    color: var(--text-primary);
    background: rgba(255,255,255,0.05);
}
.nav-item.active {
    color: var(--accent-optimal);
    background: rgba(74,222,128,0.1);
    border: 1px solid rgba(74,222,128,0.2);
}

/* ── Metrics Guide (collapsible help panel) ─────────────────────────────── */
.metrics-guide {
    margin-bottom: 1.5rem;
}
.metrics-guide > summary {
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 0.85rem;
    padding: 0.6rem 1rem;
    background: rgba(30,41,59,0.5);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 0.5rem;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: color 0.2s, background 0.2s;
    user-select: none;
}
.metrics-guide > summary:hover { color: var(--text-primary); background: rgba(30,41,59,0.8); }
.metrics-guide > summary::marker,
.metrics-guide > summary::-webkit-details-marker { display: none; }
.metrics-guide[open] > summary { border-bottom-left-radius: 0; border-bottom-right-radius: 0; color: var(--text-primary); }
.metrics-guide-body {
    background: rgba(30,41,59,0.4);
    border: 1px solid rgba(255,255,255,0.07);
    border-top: none;
    border-bottom-left-radius: 0.5rem;
    border-bottom-right-radius: 0.5rem;
    padding: 1rem 1.25rem;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px,1fr));
    gap: 0.75rem 1.5rem;
}
.metric-def dt {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--accent-info);
    margin-bottom: 0.15rem;
}
.metric-def dd {
    font-size: 0.78rem;
    color: var(--text-secondary);
    margin: 0;
    line-height: 1.5;
}

/* ── Empty State ────────────────────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 3rem 1.5rem;
    color: var(--text-secondary);
}
.empty-state .empty-icon {
    font-size: 2.5rem;
    margin-bottom: 0.75rem;
    opacity: 0.5;
}
.empty-state p { margin: 0 0 0.5rem; font-size: 0.95rem; }
.empty-state a { color: var(--accent-info); }

/* ── Regime Summary Bar ─────────────────────────────────────────────────── */
/*
 * Sticky strip that sits just below the top-nav (top:60px, z-index:900).
 * Shows the overall macro verdict + one pill per basket.
 * The JS in INTERACTIVE_JS sets --nav-height on :root so the offset is exact.
 */
.regime-bar {
    background: rgba(15,23,42,0.92);
    border-bottom: 1px solid rgba(255,255,255,0.07);
    padding: 0.6rem 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    position: sticky;
    top: var(--nav-height, 62px);
    z-index: 900;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
}
.regime-left {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-shrink: 0;
}
.regime-label {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: var(--text-secondary);
    white-space: nowrap;
}
.regime-verdict {
    font-size: 0.95rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    white-space: nowrap;
}
.regime-insight {
    font-size: 0.72rem;
    color: var(--text-secondary);
    max-width: 360px;
    line-height: 1.4;
}
.regime-counts {
    display: flex;
    gap: 0.4rem;
    align-items: center;
    flex-shrink: 0;
}
.regime-pills {
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
    align-items: center;
}
.regime-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.2rem 0.55rem;
    border-radius: 9999px;
    border: 1px solid rgba(255,255,255,0.1);
    background: rgba(30,41,59,0.6);
    color: var(--text-secondary);
    white-space: nowrap;
    cursor: default;
}
.regime-pill .pill-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
}
@media (max-width: 768px) {
    .regime-bar { top: 0; position: relative; }
    .regime-insight { display: none; }
    .regime-pills { display: none; }
}

/* ── Basket Cards ───────────────────────────────────────────────────────── */
.basket-section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    cursor: pointer;
    padding: 1rem 1.5rem;
    background: var(--card-bg);
    border: var(--card-border);
    border-radius: 1rem;
    user-select: none;
}
.basket-section-header:hover { background: rgba(30,41,59,0.85); }
.basket-section-toggle {
    font-size: 0.75rem;
    color: var(--text-secondary);
    transition: transform 0.2s;
}
details.basket-section[open] .basket-section-toggle { transform: rotate(180deg); }

.basket-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1.25rem;
    margin-bottom: 2rem;
}
@media (max-width: 960px) { .basket-grid { grid-template-columns: 1fr; } }

.basket-card {
    background: var(--card-bg);
    border: var(--card-border);
    border-radius: 1rem;
    padding: 1.25rem;
    box-shadow: var(--glass-shadow);
    position: relative;
    overflow: hidden;
    transition: transform 0.15s, box-shadow 0.15s;
}
.basket-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
}
/* Coloured top-edge accent — driven purely by class, no inline style needed */
.basket-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    border-radius: 1rem 1rem 0 0;
}
.basket-card.signal-bullish { border-color: rgba(74,222,128,0.25); }
.basket-card.signal-bullish::before { background: var(--accent-optimal); }
.basket-card.signal-neutral { border-color: rgba(251,191,36,0.2); }
.basket-card.signal-neutral::before { background: var(--accent-marginal); }
.basket-card.signal-bearish { border-color: rgba(248,113,113,0.25); }
.basket-card.signal-bearish::before { background: var(--accent-poor); }

.basket-meta-row {
    display: flex;
    gap: 1.25rem;
    margin: 0.6rem 0 0.75rem;
    flex-wrap: wrap;
}
.basket-meta-item {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
}
.basket-meta-label {
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--text-secondary);
}
.basket-meta-value {
    font-size: 0.85rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}
.basket-divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.06);
    margin: 0.5rem 0 0.6rem;
}
.basket-ticker-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.35rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 0.8rem;
    text-decoration: none;
    color: var(--text-primary);
    transition: background 0.1s;
    border-radius: 4px;
}
.basket-ticker-row:last-of-type { border-bottom: none; }
.basket-ticker-row:hover { background: rgba(255,255,255,0.04); padding-left: 0.3rem; }
.basket-ticker-symbol {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    font-size: 0.82rem;
    min-width: 56px;
}
.basket-ticker-score {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 0.85rem;
    min-width: 28px;
    text-align: right;
}
.basket-ticker-chg {
    font-size: 0.75rem;
    min-width: 52px;
    text-align: right;
}
.basket-ticker-regime {
    font-size: 0.68rem;
    color: var(--text-secondary);
    min-width: 60px;
    text-align: right;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.basket-missing {
    font-size: 0.7rem;
    color: var(--text-secondary);
    font-style: italic;
    margin-top: 0.5rem;
    line-height: 1.5;
}
.basket-no-data {
    font-size: 0.8rem;
    color: var(--text-secondary);
    text-align: center;
    padding: 1rem 0;
}
"""


# ---------------------------------------------------------------------------
# Metrics guide HTML (embedded once per page that needs it)
# ---------------------------------------------------------------------------
METRICS_GUIDE_HTML = """
<details class="metrics-guide glass-card" style="padding:0;">
  <summary>&#9432; Metrics Guide &mdash; what do these scores mean?</summary>
  <div class="metrics-guide-body">
    <dl class="metric-def">
      <dt>Composite Score (0&ndash;100)</dt>
      <dd>Weighted blend of trend strength, momentum, volume conviction, and fundamental quality. Higher = more favourable setup overall.</dd>
    </dl>
    <dl class="metric-def">
      <dt>Entry Score (0&ndash;100)</dt>
      <dd>Measures how close the stock is to an ideal low-risk entry point right now. Combines EMA proximity, ATR-based risk, and volume confirmation.</dd>
    </dl>
    <dl class="metric-def">
      <dt>RS Rating (0&ndash;99)</dt>
      <dd>Relative Strength vs. the S&amp;P 500 over the past 12 months. 99 = top 1% of all stocks. Derived from IBD&rsquo;s methodology.</dd>
    </dl>
    <dl class="metric-def">
      <dt>ADX (Average Directional Index)</dt>
      <dd>Measures trend <em>strength</em> (not direction). ADX &gt; 25 = trending; &gt; 40 = strong trend. Used to filter out choppy, non-directional markets.</dd>
    </dl>
    <dl class="metric-def">
      <dt>ATR (Average True Range)</dt>
      <dd>Average daily price range over 14 days &mdash; a volatility gauge. Used to size positions and set stop-loss distances proportional to the stock&rsquo;s natural movement.</dd>
    </dl>
    <dl class="metric-def">
      <dt>EMA Stack</dt>
      <dd>Price is above its 20-day EMA, which is above the 50-day, which is above the 200-day. When all three align this way, the stock is in a confirmed uptrend.</dd>
    </dl>
    <dl class="metric-def">
      <dt>Squeeze Score</dt>
      <dd>Measures volatility compression (Bollinger Bands inside Keltner Channels). High squeeze = coiled spring setup; a breakout from squeeze often produces large moves.</dd>
    </dl>
    <dl class="metric-def">
      <dt>Rel 3M</dt>
      <dd>3-month price return relative to SPY (S&amp;P 500 ETF). Positive = outperforming the market over 3 months.</dd>
    </dl>
    <dl class="metric-def">
      <dt>Days to Cover</dt>
      <dd>Short interest divided by average daily volume. How many trading days it would take all short sellers to buy back their positions. High = potential squeeze fuel.</dd>
    </dl>
    <dl class="metric-def">
      <dt>IV Rank</dt>
      <dd>Where today&rsquo;s implied volatility sits relative to its 52-week range (0&ndash;100%). High IV Rank = options are expensive; low = relatively cheap.</dd>
    </dl>
    <dl class="metric-def">
      <dt>Score Ratings</dt>
      <dd><strong style="color:#4ade80">Optimal</strong> &ge;80 &nbsp;
          <strong style="color:#34d399">Good</strong> &ge;65 &nbsp;
          <strong style="color:#e2b84a">Acceptable</strong> &ge;50 &nbsp;
          <strong style="color:#fbbf24">Marginal</strong> &ge;35 &nbsp;
          <strong style="color:#f87171">Poor</strong> &lt;35</dd>
    </dl>
  </div>
</details>
"""


# ---------------------------------------------------------------------------
# Interactive JavaScript (sortable tables, search, watchlist, chart tooltips)
# ---------------------------------------------------------------------------
INTERACTIVE_JS = """
<script>
// ── Sortable Tables ────────────────────────────────────────────────────────
function initSortableTables() {
    document.querySelectorAll('.modern-table').forEach(table => {
        const headers = table.querySelectorAll('th.sortable');
        headers.forEach((header, colIndex) => {
            header.addEventListener('click', () => {
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const isAsc = header.classList.contains('asc');
                headers.forEach(h => h.classList.remove('asc', 'desc'));
                header.classList.add(isAsc ? 'desc' : 'asc');
                rows.sort((a, b) => {
                    let aVal = a.cells[colIndex].textContent.trim();
                    let bVal = b.cells[colIndex].textContent.trim();
                    const aNum = parseFloat(aVal.replace(/[^0-9.-]/g, ''));
                    const bNum = parseFloat(bVal.replace(/[^0-9.-]/g, ''));
                    if (!isNaN(aNum) && !isNaN(bNum)) return isAsc ? bNum - aNum : aNum - bNum;
                    return isAsc ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal);
                });
                rows.forEach(row => tbody.appendChild(row));
            });
        });
    });
}

// ── Search / Filter ────────────────────────────────────────────────────────
function initSearch() {
    const searchInput = document.getElementById('stock-search');
    if (!searchInput) return;
    searchInput.addEventListener('input', e => {
        const query = e.target.value.toLowerCase();
        const items = document.querySelectorAll('.stock-card, .modern-table tbody tr');
        items.forEach(item => {
            const ticker = item.dataset.ticker?.toLowerCase() || item.textContent.toLowerCase();
            item.classList.toggle('hidden', !ticker.includes(query));
        });
        const visible = document.querySelectorAll('.stock-card:not(.hidden), .modern-table tbody tr:not(.hidden)').length;
        const countEl = document.getElementById('visible-count');
        if (countEl) countEl.textContent = visible;
        // Empty-state feedback
        const emptyState = document.getElementById('search-empty-state');
        if (emptyState) emptyState.classList.toggle('hidden', visible > 0);
    });
}

// ── Filter Buttons ─────────────────────────────────────────────────────────
function initFilterButtons() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const filter = btn.dataset.filter;
            const isActive = btn.classList.contains('active');
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            if (!isActive) btn.classList.add('active');
            document.querySelectorAll('.stock-card').forEach(card => {
                if (!filter || isActive)         { card.classList.remove('hidden'); }
                else if (filter === 'top5')       { card.classList.toggle('hidden', parseInt(card.dataset.rank) > 5); }
                else if (filter === 'trade-ready'){ card.classList.toggle('hidden', card.dataset.tradeReady !== 'true'); }
            });
            const visible = document.querySelectorAll('.stock-card:not(.hidden)').length;
            const countEl = document.getElementById('visible-count');
            if (countEl) countEl.textContent = visible;
        });
    });
}

// ── SVG Chart Tooltips ─────────────────────────────────────────────────────
function initChartTooltips() {
    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip';
    document.body.appendChild(tooltip);
    document.querySelectorAll('svg.interactive-chart').forEach(chart => {
        chart.addEventListener('mousemove', e => {
            const rect = chart.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const data = chart.dataset.values ? JSON.parse(chart.dataset.values) : null;
            if (data && data.length > 0) {
                const idx = Math.floor((x / rect.width) * data.length);
                const point = data[Math.min(idx, data.length - 1)];
                if (point) {
                    tooltip.innerHTML = `
                        <div><strong>${point.date || ''}</strong></div>
                        <div>Price: $${point.price?.toFixed(2) || '&mdash;'}</div>
                        ${point.ema20 ? `<div style="color:#f59e0b">EMA20: $${point.ema20.toFixed(2)}</div>` : ''}
                        ${point.ema50 ? `<div style="color:#8b5cf6">EMA50: $${point.ema50.toFixed(2)}</div>` : ''}
                    `;
                    tooltip.style.left = (e.clientX + 15) + 'px';
                    tooltip.style.top  = (e.clientY - 10) + 'px';
                    tooltip.classList.add('visible');
                }
            }
        });
        chart.addEventListener('mouseleave', () => tooltip.classList.remove('visible'));
    });
}

// ── Watchlist ──────────────────────────────────────────────────────────────
function initWatchlist() {
    const serverList = window.__SERVER_WATCHLIST__ || [];
    let watchlist = JSON.parse(localStorage.getItem('ema_watchlist') || '[]');
    serverList.forEach(t => { if (!watchlist.includes(t)) watchlist.push(t); });
    localStorage.setItem('ema_watchlist', JSON.stringify(watchlist));
    document.querySelectorAll('.watchlist-btn, .cand-watchlist-btn').forEach(btn => {
        if (watchlist.includes(btn.dataset.ticker)) {
            btn.textContent = '★';
            btn.style.color = '#fbbf24';
        }
    });
}

function toggleWatchlist(btn) {
    const ticker = btn.dataset.ticker;
    let watchlist = JSON.parse(localStorage.getItem('ema_watchlist') || '[]');
    const idx = watchlist.indexOf(ticker);
    if (idx === -1) {
        watchlist.push(ticker);
        btn.textContent = '★';
        btn.style.color = '#fbbf24';
    } else {
        watchlist.splice(idx, 1);
        btn.textContent = '☆';
        btn.style.color = 'rgba(255,255,255,0.2)';
    }
    localStorage.setItem('ema_watchlist', JSON.stringify(watchlist));
    document.querySelectorAll(`.watchlist-btn[data-ticker="${ticker}"], .cand-watchlist-btn[data-ticker="${ticker}"]`).forEach(b => {
        b.textContent = btn.textContent;
        b.style.color = btn.style.color;
    });
}

function exportWatchlist() {
    const watchlist = JSON.parse(localStorage.getItem('ema_watchlist') || '[]');
    const blob = new Blob([JSON.stringify(watchlist, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'watchlist.json';
    a.click();
    URL.revokeObjectURL(a.href);
}

// ── Advanced Filters ───────────────────────────────────────────────────────
function initAdvancedFilters() {
    const sectorSel = document.getElementById('cand-sector-filter');
    if (sectorSel) {
        const sectors = new Set();
        document.querySelectorAll('#candidates-table tbody tr').forEach(r => {
            if (r.dataset.sector) sectors.add(r.dataset.sector);
        });
        Array.from(sectors).sort().forEach(s => {
            const o = document.createElement('option');
            o.value = s; o.textContent = s; sectorSel.appendChild(o);
        });
    }

    function applyCandFilter() {
        const minScore = parseInt(document.getElementById('cand-score-filter')?.value || '0');
        const regime   = document.getElementById('cand-regime-filter')?.value || '';
        const sector   = document.getElementById('cand-sector-filter')?.value || '';
        let visible = 0;
        document.querySelectorAll('#candidates-table tbody tr').forEach(row => {
            const show = parseFloat(row.dataset.entryScore || '0') >= minScore
                && (regime === '' || (row.dataset.regime || '').toUpperCase().includes(regime))
                && (sector === '' || row.dataset.sector === sector);
            row.classList.toggle('hidden', !show);
            if (show) visible++;
        });
        const el = document.getElementById('cand-visible-count');
        if (el) el.textContent = visible;
    }

    ['cand-score-filter', 'cand-regime-filter', 'cand-sector-filter'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', applyCandFilter);
    });

    document.getElementById('proj-conf-filter')?.addEventListener('change', function() {
        const val = this.value;
        let vis = 0;
        document.querySelectorAll('#projections-table tbody tr').forEach(row => {
            const show = val === '' || row.dataset.confidence === val;
            row.classList.toggle('hidden', !show);
            if (show) vis++;
        });
        const el = document.getElementById('proj-visible-count');
        if (el) el.textContent = vis;
    });
}

// ── Bootstrap (guarded — each feature only runs if its DOM anchor exists) ──
document.addEventListener('DOMContentLoaded', () => {
    // Set --nav-height CSS variable so .regime-bar sticky offset is exact
    const nav = document.querySelector('.top-nav');
    if (nav) {
        document.documentElement.style.setProperty('--nav-height', nav.offsetHeight + 'px');
    }

    if (document.querySelector('.modern-table th.sortable')) {
        console.info('[EMA] initSortableTables');
        initSortableTables();
    }
    if (document.getElementById('stock-search')) {
        console.info('[EMA] initSearch');
        initSearch();
    }
    if (document.querySelectorAll('.filter-btn').length) {
        console.info('[EMA] initFilterButtons');
        initFilterButtons();
    }
    if (document.querySelectorAll('svg.interactive-chart').length) {
        console.info('[EMA] initChartTooltips');
        initChartTooltips();
    }
    if (document.getElementById('cand-score-filter') || document.getElementById('proj-conf-filter')) {
        console.info('[EMA] initAdvancedFilters');
        initAdvancedFilters();
    }
    if (document.querySelectorAll('.watchlist-btn, .cand-watchlist-btn').length) {
        console.info('[EMA] initWatchlist');
        initWatchlist();
    }
});
</script>
"""


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

_NAV_PAGES = [
    {"id": "command_center",  "name": "Command Center",  "url": "index.html"},
    {"id": "sector_analysis", "name": "Sector Analysis", "url": "sector_analysis.html"},
    {"id": "macro_drivers",   "name": "Macro Drivers",   "url": "macro_drivers.html"},
    {"id": "sentiment",       "name": "Sentiment",       "url": "sentiment.html"},
    {"id": "market_news",     "name": "Market News",     "url": "market_news.html"},
    {"id": "ai_memo",         "name": "AI Strategy",     "url": "ai_memo.html"},
    {"id": "ai_macro_memo",   "name": "Macro AI",        "url": "ai_macro_memo.html"},
]


def generate_top_nav(active_page: str = "command_center") -> str:
    """Return the sticky top-nav HTML shared by every page.

    Args:
        active_page: ID of the current page (one of the keys in _NAV_PAGES).
                     Pass '' for pages that aren't top-level nav items (e.g.
                     individual stock pages).
    """
    links_html = "".join(
        f'<li><a href="{p["url"]}" class="nav-item{"  active" if p["id"] == active_page else ""}">'
        f'{p["name"]}</a></li>'
        for p in _NAV_PAGES
    )
    return f"""
    <nav class="top-nav">
        <ul class="top-nav-list">
            {links_html}
        </ul>
    </nav>
    """


def generate_breadcrumb(crumbs: list[tuple[str, str | None]]) -> str:
    """Return a breadcrumb <nav> element.

    Args:
        crumbs: Ordered list of (label, url) pairs.  The last entry should
                have url=None — it represents the current page and is rendered
                as plain text, not a link.

    Example::

        generate_breadcrumb([
            ("Command Center", "index.html"),
            ("XLK Technology", "sector_XLK.html"),
            ("AAPL", None),
        ])
    """
    parts: list[str] = []
    for i, (label, url) in enumerate(crumbs):
        is_last = i == len(crumbs) - 1
        if is_last or url is None:
            parts.append(f'<span class="bc-current">{label}</span>')
        else:
            parts.append(f'<a href="{url}">{label}</a>')
        if not is_last:
            parts.append('<span class="bc-sep">/</span>')
    return f'<nav class="breadcrumb">{"".join(parts)}</nav>'


# ---------------------------------------------------------------------------
# Page shell convenience wrapper
# ---------------------------------------------------------------------------

_GOOGLE_FONTS = (
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
)


def generate_page_shell(
    title: str,
    body: str,
    active_nav: str = "",
    extra_css: str = "",
    extra_head: str = "",
) -> str:
    """Wrap *body* HTML in a complete <!DOCTYPE html> document.

    CSS_DARK_THEME and INTERACTIVE_JS are embedded inline so the page works
    when opened directly from the filesystem (no web server required).

    Args:
        title:      Browser <title> text.
        body:       HTML content placed inside <body> (after the top nav).
        active_nav: Nav page ID passed to generate_top_nav().
        extra_css:  Additional CSS appended inside <style> (page-specific rules).
        extra_head: Raw HTML inserted before </head> (e.g. extra <script> tags).
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    {_GOOGLE_FONTS}
    <style>
        {CSS_DARK_THEME}
        {extra_css}
    </style>
    {extra_head}
</head>
<body>
    {generate_top_nav(active_nav)}
    {body}
    {INTERACTIVE_JS}
</body>
</html>"""
