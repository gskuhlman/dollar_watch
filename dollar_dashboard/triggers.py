from __future__ import annotations

from typing import Any
import math


def _safe(v, default=None):
    try:
        x = float(v)
        if math.isnan(x):
            return default
        return x
    except Exception:
        return default


def _v(d: dict, *path, default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _latest_auction(snapshot: dict, term: str) -> dict | None:
    rows = [r for r in snapshot.get("auction_summary", []) if str(r.get("term")) == term]
    if not rows:
        return None
    return sorted(rows, key=lambda r: str(r.get("auction_date") or ""), reverse=True)[0]


def _weak_auction(row: dict | None) -> bool:
    if not row:
        return False
    btc = _safe(row.get("bid_to_cover")); avg = _safe(row.get("prior8_btc"))
    dealer = _safe(row.get("dealer_share_pct")); indirect = _safe(row.get("indirect_share_pct"))
    return all(x is not None for x in [btc, avg, dealer, indirect]) and btc < avg - 0.15 and dealer > 14 and indirect < 65


def _clean_auction(row: dict | None) -> bool:
    if not row:
        return False
    btc = _safe(row.get("bid_to_cover")); avg = _safe(row.get("prior8_btc"))
    indirect = _safe(row.get("indirect_share_pct"))
    return btc is not None and avg is not None and indirect is not None and btc >= avg and indirect >= 65


def evaluate_triggers(snapshot: dict, scores: dict) -> list[dict]:
    """Machine-readable pre-commitments. Conditions are explicit and auditable."""
    f = snapshot.get("fred_summary", {})
    m = snapshot.get("market_summary", {})
    ten = _latest_auction(snapshot, "10-Year")
    thirty = _latest_auction(snapshot, "30-Year")

    term = _safe(_v(f, "10Y term premium", "last"))
    be = _safe(_v(f, "10Y breakeven inflation", "last"))
    dxy = _safe(_v(m, "DXY", "last"))
    dxy_3m = _safe(_v(m, "DXY", "3m"))
    custody_yoy = _safe(_v(f, "Foreign custody UST YoY change (millions)", "last"))
    swaps = _safe(_v(f, "Central bank liquidity swaps (millions)", "last"), 0)
    sofr_iorb = _safe(_v(f, "SOFR-IORB spread", "last"))
    gold_3m = _safe(_v(m, "Gold", "3m"))
    cftc_down = _safe(snapshot.get("cftc_usd_downside_pressure"), 0)

    out: list[dict] = []

    weak_pair = _weak_auction(ten) and _weak_auction(thirty)
    clean_pair = _clean_auction(ten) and _clean_auction(thirty)
    out.append({
        "id": "weak_10y_30y_pair",
        "side": "CONFIRM",
        "status": "TRIGGERED" if weak_pair else ("PARTIAL" if _weak_auction(ten) or _weak_auction(thirty) else "NOT_TRIGGERED"),
        "condition": "10Y and 30Y: BTC >0.15 below prior-8 average, dealer >14%, indirect <65%",
        "action": "Add +2pp TIPS / +1pp gold funded from cash, subject to portfolio guardrails.",
    })
    out.append({
        "id": "clean_10y_30y_pair",
        "side": "KILL",
        "status": "TRIGGERED" if clean_pair else "NOT_TRIGGERED",
        "condition": "10Y and 30Y BTC >= prior-8 average and indirect >=65%",
        "action": "Stand down auction-driven hedge escalation.",
    })

    inflation_join = term is not None and be is not None and term > 1.0 and be > 2.6
    out.append({
        "id": "fiscal_plus_inflation",
        "side": "CONFIRM",
        "status": "TRIGGERED" if inflation_join else "NOT_TRIGGERED",
        "condition": "10Y term premium >1.0% AND 10Y breakeven >2.6%",
        "action": "Treat inflation/debasement as joining fiscal-duration stress; favor TIPS/real assets over long nominal duration.",
    })

    reserve_break = custody_yoy is not None and custody_yoy < -300000 and _weak_auction(ten) and _weak_auction(thirty)
    out.append({
        "id": "foreign_demand_break",
        "side": "CONFIRM",
        "status": "TRIGGERED" if reserve_break else "NOT_TRIGGERED",
        "condition": "Foreign custody YoY < -$300B and both 10Y/30Y auctions weak",
        "action": "Raise reserve-confidence risk and reduce long nominal-dollar duration.",
    })

    dxy_break = dxy is not None and dxy < 96 and cftc_down >= 60
    out.append({
        "id": "dxy_positioning_break",
        "side": "CONFIRM",
        "status": "TRIGGERED" if dxy_break else "NOT_TRIGGERED",
        "condition": "DXY <96 and CFTC USD-downside pressure >=60",
        "action": "Treat dollar weakness as positioning-confirmed rather than spot noise.",
    })

    repo_break = (sofr_iorb is not None and sofr_iorb > 0.10) or swaps >= 1000
    out.append({
        "id": "repo_or_swap_stress",
        "side": "CONFIRM",
        "status": "TRIGGERED" if repo_break else "NOT_TRIGGERED",
        "condition": "SOFR-IORB >10bp or Fed foreign-central-bank swaps >=$1B",
        "action": "Raise dollar-funding-squeeze risk; favor T-bills/liquidity until plumbing normalizes.",
    })

    term_kill = term is not None and term < 0.70
    out.append({
        "id": "term_premium_normalizes",
        "side": "KILL",
        "status": "TRIGGERED" if term_kill else "NOT_TRIGGERED",
        "condition": "10Y term premium <0.70%",
        "action": "Reduce fiscal-duration stress score if auctions and fiscal flows are also benign.",
    })

    dollar_kill = dxy is not None and dxy > 101 and (dxy_3m or 0) > 0
    out.append({
        "id": "dollar_strength_reversal",
        "side": "KILL",
        "status": "TRIGGERED" if dollar_kill else "NOT_TRIGGERED",
        "condition": "DXY >101 with positive 3-month momentum",
        "action": "Reduce managed-devaluation/reserve-confidence overlays unless policy evidence strengthens materially.",
    })

    gold_confirm = gold_3m is not None and gold_3m > 0.08 and term is not None and term > 0.80
    out.append({
        "id": "gold_real_yield_anomaly",
        "side": "WATCH",
        "status": "TRIGGERED" if gold_confirm else "NOT_TRIGGERED",
        "condition": "Gold +8% over ~3m while term premium >0.80%",
        "action": "Investigate official-sector/reserve diversification rather than automatically adding gold after the move.",
    })
    return out
