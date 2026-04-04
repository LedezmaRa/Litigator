"""
Historical Score Tracking for EMA-ADX-ATR Framework.

Persists daily snapshots of candidate scores and projections to
reports/history/YYYY-MM-DD.json. Provides helpers to load history,
render score-trend sparklines, and evaluate past projection accuracy.
"""

import datetime
import json
import os
from typing import Dict, List, Optional

SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------

def save_daily_snapshot(candidates, projections, output_dir: str = "reports") -> str:
    """
    Persist today's candidate scores and projections to
    reports/history/YYYY-MM-DD.json.

    Returns the path of the written file.
    """
    today = datetime.date.today().isoformat()
    hist_dir = os.path.join(output_dir, "history")
    os.makedirs(hist_dir, exist_ok=True)

    data = {
        "version": SCHEMA_VERSION,
        "date": today,
        "stocks": {
            c.ticker: {
                "composite_score": round(float(c.composite_score), 2),
                "entry_score": round(float(c.entry_score), 2),
                "regime": c.regime,
                "sector": c.sector_etf,
                "rank_in_sector": c.rank_in_sector,
                "is_trade_ready": c.is_trade_ready,
            }
            for c in candidates
        },
        "projections": [
            {
                "ticker": p.ticker,
                "entry_price": round(float(p.current_price), 4),
                "stop_price": round(float(p.stop_price), 4),
                "target_1r": round(float(p.target_1r), 4),
                "target_2r": round(float(p.target_2r), 4),
                "target_3r": round(float(p.target_3r), 4),
                "confidence_level": p.confidence_level,
            }
            for p in (projections or [])
        ],
    }

    path = os.path.join(hist_dir, f"{today}.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save history snapshot: {e}")
    return path


# ---------------------------------------------------------------------------
# History loading
# ---------------------------------------------------------------------------

def load_history(output_dir: str = "reports", days: int = 30) -> Dict[str, List[Dict]]:
    """
    Load the most recent `days` snapshots from reports/history/.

    Returns:
        { ticker: [ {date, entry_score, composite_score, regime}, ... ] }
        sorted oldest-first per ticker.
    """
    hist_dir = os.path.join(output_dir, "history")
    if not os.path.exists(hist_dir):
        return {}

    # ISO date filenames sort correctly lexicographically
    files = sorted(
        f for f in os.listdir(hist_dir)
        if f.endswith(".json") and len(f) == 15  # YYYY-MM-DD.json
    )[-days:]

    result: Dict[str, List] = {}
    for fname in files:
        try:
            with open(os.path.join(hist_dir, fname)) as f:
                snap = json.load(f)
            date = snap.get("date", fname[:10])
            for ticker, info in snap.get("stocks", {}).items():
                if ticker not in result:
                    result[ticker] = []
                result[ticker].append({
                    "date": date,
                    "entry_score": float(info.get("entry_score", 0)),
                    "composite_score": float(info.get("composite_score", 0)),
                    "regime": info.get("regime", ""),
                })
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# Score-trend helpers
# ---------------------------------------------------------------------------

def build_score_sparkline_svg(scores: List[float], width: int = 60, height: int = 18) -> str:
    """
    Return a tiny inline SVG polyline of recent entry scores.
    Green if last value ≥ first, red otherwise.
    Returns empty string if fewer than 2 data points.
    """
    if len(scores) < 2:
        return ""
    mn, mx = min(scores), max(scores)
    if mx == mn:
        mx = mn + 1  # avoid division by zero
    color = "#4ade80" if scores[-1] >= scores[0] else "#f87171"
    pad = 2
    pts = []
    for i, v in enumerate(scores):
        x = pad + i / (len(scores) - 1) * (width - 2 * pad)
        y = height - pad - (v - mn) / (mx - mn) * (height - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    points_str = " ".join(pts)
    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="vertical-align:middle; flex-shrink:0;">'
        f'<polyline points="{points_str}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def get_score_trend(scores: List[float]) -> str:
    """
    Returns 'IMPROVING', 'WORSENING', 'STABLE', or 'NEW'.
    Compares the latest value against the mean of all prior values.
    ±5 point threshold to call a directional change.
    """
    if len(scores) < 2:
        return "NEW"
    prior_mean = sum(scores[:-1]) / len(scores[:-1])
    delta = scores[-1] - prior_mean
    if delta > 5:
        return "IMPROVING"
    if delta < -5:
        return "WORSENING"
    return "STABLE"


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------

def evaluate_past_projections(output_dir: str, closes) -> Dict:
    """
    Check past projection snapshots against subsequent actual price data.

    Requires a pandas DataFrame `closes` with ticker columns and a DatetimeIndex.
    Only evaluates projections from 5–60 days ago (recent ones haven't had time to play out).

    Returns a dict with hit-rate stats, or {"status": "building", ...} if insufficient data.
    """
    hist_dir = os.path.join(output_dir, "history")
    if not os.path.exists(hist_dir):
        return {"status": "building", "total_evaluated": 0}

    today = datetime.date.today()
    cutoff_recent = (today - datetime.timedelta(days=5)).isoformat()
    cutoff_old = (today - datetime.timedelta(days=60)).isoformat()

    files = sorted(
        f for f in os.listdir(hist_dir)
        if f.endswith(".json") and len(f) == 15
    )

    total = hit_1r = hit_2r = hit_3r = 0

    for fname in files:
        date_str = fname[:10]
        # Only evaluate snapshots old enough to have had time to play out
        if date_str >= cutoff_recent or date_str < cutoff_old:
            continue
        try:
            with open(os.path.join(hist_dir, fname)) as f:
                snap = json.load(f)
            for proj in snap.get("projections", []):
                ticker = proj.get("ticker")
                if not ticker or ticker not in closes.columns:
                    continue
                col = closes[ticker].dropna()
                # Get closes strictly after the projection date
                future = col[col.index.astype(str) > date_str]
                if len(future) < 2:
                    continue
                future_high = float(future.iloc[:20].max())
                total += 1
                if future_high >= proj["target_1r"]:
                    hit_1r += 1
                if future_high >= proj["target_2r"]:
                    hit_2r += 1
                if future_high >= proj["target_3r"]:
                    hit_3r += 1
        except Exception:
            continue

    if total < 5:
        return {"status": "building", "total_evaluated": total}

    return {
        "status": "ready",
        "total_evaluated": total,
        "hit_1r": hit_1r,
        "hit_1r_pct": round(hit_1r / total * 100, 1),
        "hit_2r": hit_2r,
        "hit_2r_pct": round(hit_2r / total * 100, 1),
        "hit_3r": hit_3r,
        "hit_3r_pct": round(hit_3r / total * 100, 1),
    }
