from __future__ import annotations

from typing import Any
import math
import pandas as pd


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


def _asof(snapshot: dict, rows: list[dict]) -> pd.Timestamp:
    ts = pd.to_datetime(snapshot.get("timestamp"), errors="coerce", utc=True)
    if pd.notna(ts):
        return ts
    dates = [pd.to_datetime(r.get("auction_date"), errors="coerce", utc=True) for r in rows if r]
    dates = [x for x in dates if pd.notna(x)]
    return (max(dates) + pd.Timedelta(days=1)) if dates else pd.Timestamp.now(tz="UTC")


def _next_auction(snapshot: dict, term: str, asof: pd.Timestamp) -> pd.Timestamp | pd.NaT:
    dates=[]
    for row in snapshot.get("upcoming_auctions", []) or []:
        key=str(row.get("term_key") or row.get("security_term") or row.get("term") or "").strip().lower()
        want=str(term).strip().lower()
        import re
        key_num=(re.search(r"(\d+)\s*[- ]?year",key) or re.search(r"^(\d+)$",key))
        want_num=(re.search(r"(\d+)\s*[- ]?year",want) or re.search(r"^(\d+)$",want))
        if key_num and want_num:
            if key_num.group(1) != want_num.group(1): continue
        elif key != want:
            continue
        d=pd.to_datetime(row.get("auction_date"), errors="coerce", utc=True)
        if pd.notna(d) and d >= asof.normalize():
            dates.append(d)
    return min(dates) if dates else pd.NaT


def _auction_lifecycle(snapshot: dict, row: dict | None, term: str, asof: pd.Timestamp) -> dict:
    if not row:
        return {"age_days": None, "next_auction": None, "days_to_next": None, "effect_weight": 0.0, "lifecycle": "NO_RESULT"}
    d=pd.to_datetime(row.get("auction_date"), errors="coerce", utc=True)
    if pd.isna(d):
        return {"age_days": None, "next_auction": None, "days_to_next": None, "effect_weight": 0.0, "lifecycle": "NO_DATE"}
    age=max(0.0, (asof-d).total_seconds()/86400.0)
    if age <= 7: weight=1.0; life="FRESH"
    elif age <= 14: weight=0.70; life="AGING"
    elif age <= 21: weight=0.40; life="AGING"
    else: weight=0.0; life="EXPIRED"
    nxt=_next_auction(snapshot,term,asof)
    days_to=None
    if pd.notna(nxt):
        days_to=(nxt-asof).total_seconds()/86400.0
        if -0.5 <= days_to <= 3.5:
            life="PENDING_REPLACEMENT"
            weight=min(weight,0.40)
    return {
        "age_days": round(age,1),
        "next_auction": None if pd.isna(nxt) else nxt.isoformat(),
        "days_to_next": None if days_to is None else round(days_to,1),
        "effect_weight": round(weight,2),
        "lifecycle": life,
    }


def _condition_status(condition: bool, lifecycle: dict, partial: bool=False) -> str:
    if not condition:
        return "PARTIAL" if partial else "NOT_TRIGGERED"
    life=lifecycle.get("lifecycle")
    weight=float(lifecycle.get("effect_weight") or 0)
    if life == "PENDING_REPLACEMENT": return "PENDING_REPLACEMENT"
    if life == "EXPIRED" or weight <= 0: return "EXPIRED"
    if weight < 0.7: return "AGING"
    return "TRIGGERED"


def evaluate_triggers(snapshot: dict, scores: dict, previous_triggers: list[dict] | None = None) -> list[dict]:
    """Machine-readable pre-commitments with age/expiration for event-based evidence."""
    f = snapshot.get("fred_summary", {})
    m = snapshot.get("market_summary", {})
    ten = _latest_auction(snapshot, "10-Year")
    thirty = _latest_auction(snapshot, "30-Year")
    asof=_asof(snapshot,[ten,thirty])
    life10=_auction_lifecycle(snapshot,ten,"10-Year",asof)
    life30=_auction_lifecycle(snapshot,thirty,"30-Year",asof)
    pair_life={
        "age_days": max([x for x in [life10.get('age_days'),life30.get('age_days')] if x is not None], default=None),
        "next_auction": ", ".join([x for x in [life10.get('next_auction'),life30.get('next_auction')] if x]) or None,
        "days_to_next": min([x for x in [life10.get('days_to_next'),life30.get('days_to_next')] if x is not None], default=None),
        "effect_weight": min(float(life10.get('effect_weight') or 0),float(life30.get('effect_weight') or 0)),
        "lifecycle": "FRESH",
    }
    lives={life10.get('lifecycle'),life30.get('lifecycle')}
    if 'PENDING_REPLACEMENT' in lives: pair_life['lifecycle']='PENDING_REPLACEMENT'
    elif 'EXPIRED' in lives: pair_life['lifecycle']='EXPIRED'
    elif 'AGING' in lives: pair_life['lifecycle']='AGING'

    term = _safe(_v(f, "10Y term premium", "last"))
    be = _safe(_v(f, "10Y breakeven inflation", "last"))
    dxy = _safe(_v(m, "DXY", "last"))
    dxy_3m = _safe(_v(m, "DXY", "3m"))
    custody_yoy = _safe(_v(f, "Foreign custody UST YoY change (millions)", "last"))
    swaps = _safe(_v(f, "Central bank liquidity swaps (millions)", "last"), 0)
    fima = _safe(_v(f, "FIMA repo - foreign official (millions)", "last"), 0)
    sofr_iorb = _safe(_v(f, "SOFR-IORB spread", "last"))
    sofr_recent_le3 = int(_safe(_v(f, "SOFR-IORB spread", "recent_obs_le_3bp"),0) or 0)
    sofr_recent_count = int(_safe(_v(f, "SOFR-IORB spread", "recent_obs_count_5"),0) or 0)
    sofr99_iorb = _safe(_v(f, "SOFR99-IORB spread", "last"))
    sofr99_pct = _safe(_v(f, "SOFR99-IORB spread", "percentile_1y"))
    sofr99_z = _safe(_v(f, "SOFR99-IORB spread", "zscore_1y"))
    sofr99_recent10 = _safe(_v(f, "SOFR99-IORB spread", "recent_obs_ge_10bp"),0)
    gold_3m = _safe(_v(m, "Gold", "3m"))
    cftc_down = _safe(snapshot.get("cftc_usd_downside_pressure"), 0)

    out: list[dict] = []

    weak10,weak30=_weak_auction(ten),_weak_auction(thirty)
    weak_pair = weak10 and weak30
    clean_pair = _clean_auction(ten) and _clean_auction(thirty)
    base_meta={"auction_lifecycle":pair_life,"10Y_lifecycle":life10,"30Y_lifecycle":life30}
    stress_flavor = "INFLATIONARY_FISCAL" if (be is not None and be >= 2.60) else "REAL_YIELD_FISCAL"
    weak_action = (
        "Inflationary fiscal stress: +2pp TIPS / +1pp gold funded from T-bills, subject to guardrails."
        if stress_flavor == "INFLATIONARY_FISCAL" else
        "Real-yield fiscal stress: preserve/add T-bills, consider +1pp gold, and reduce rate-sensitive risk rather than mechanically adding TIPS."
    )
    out.append({
        "id": "weak_10y_30y_pair", "side": "CONFIRM",
        "status": _condition_status(weak_pair,pair_life,partial=weak10 or weak30),
        "condition": "10Y and 30Y: BTC >0.15 below prior-8 average, dealer >14%, indirect <65%",
        "action": weak_action,
        "stress_flavor": stress_flavor,
        "breakeven": be,
        **base_meta,
    })
    out.append({
        "id": "clean_10y_30y_pair", "side": "KILL",
        "status": _condition_status(clean_pair,pair_life),
        "condition": "10Y and 30Y BTC >= prior-8 average and indirect >=65%",
        "action": "Stand down auction-driven hedge escalation while the clean-auction evidence remains fresh.",
        **base_meta,
    })

    inflation_join = term is not None and be is not None and term > 1.0 and be > 2.6
    out.append({"id":"fiscal_plus_inflation","side":"CONFIRM","status":"TRIGGERED" if inflation_join else "NOT_TRIGGERED","condition":"10Y term premium >1.0% AND 10Y breakeven >2.6%","action":"Treat inflation/debasement as joining fiscal-duration stress; favor TIPS/real assets over long nominal duration."})

    fresh_weak_pair=weak_pair and pair_life.get('effect_weight',0)>=0.7 and pair_life.get('lifecycle') not in {'PENDING_REPLACEMENT','EXPIRED'}
    reserve_break = custody_yoy is not None and custody_yoy < -300000 and fresh_weak_pair
    out.append({"id":"foreign_demand_break","side":"CONFIRM","status":"TRIGGERED" if reserve_break else "NOT_TRIGGERED","condition":"Foreign custody YoY < -$300B and fresh weak 10Y/30Y auctions","action":"Raise reserve-confidence risk and reduce long nominal-dollar duration.","auction_lifecycle":pair_life})

    dxy_break = dxy is not None and dxy < 96 and cftc_down >= 60
    out.append({"id":"dxy_positioning_break","side":"CONFIRM","status":"TRIGGERED" if dxy_break else "NOT_TRIGGERED","condition":"DXY <96 and CFTC USD-downside pressure >=60","action":"Treat dollar weakness as positioning-confirmed rather than spot noise."})

    prev_by={str(t.get("id")):t for t in (previous_triggers or [])}
    prev_repo_status=str((prev_by.get("repo_or_swap_stress") or {}).get("status") or "NOT_TRIGGERED")
    prev_norm_status=str((prev_by.get("repo_stress_normalized") or {}).get("status") or "NOT_TRIGGERED")
    prior_repo_active = prev_repo_status in {"TRIGGERED","RECOVERING"} or prev_norm_status=="RECOVERING"
    repo_break = (sofr_iorb is not None and sofr_iorb > 0.10) or swaps >= 1000 or fima >= 1000
    repo_recovery = bool(prior_repo_active and sofr_recent_count>=3 and sofr_recent_le3>=3 and swaps < 250 and fima < 250)
    repo_status = "TRIGGERED" if repo_break else ("RECOVERING" if prior_repo_active and not repo_recovery else "NOT_TRIGGERED")
    out.append({"id":"repo_or_swap_stress","side":"CONFIRM","status":repo_status,"condition":"Median SOFR-IORB >10bp OR central-bank liquidity swaps >=$1B OR FIMA foreign-official repo >=$1B","action":"Raise dollar-funding-squeeze risk; favor T-bills/liquidity and trim BTC/unhedged ex-US risk. A swap/FIMA draw is not a signal to add non-USD exposure.","central_bank_swaps_mn":swaps,"fima_repo_mn":fima,"prior_active":prior_repo_active})
    out.append({"id":"repo_stress_normalized","side":"KILL","status":"TRIGGERED" if repo_recovery else ("RECOVERING" if prior_repo_active and not repo_break else "NOT_TRIGGERED"),"condition":"Only after prior funding stress: SOFR-IORB <=3bp on >=3 recent observations AND swaps < $250M AND FIMA < $250M","action":"Only after a previously active funding-stress episode has normalized, step down the funding overlay gradually; do not cut liquidity merely because current SOFR-IORB is below the entry threshold.","prior_active":prior_repo_active,"recent_obs_le_3bp":sofr_recent_le3,"recent_obs_count":sofr_recent_count})

    tail_confirm = bool(sofr99_iorb is not None and sofr99_iorb >= 0.10 and ((sofr99_pct or 0)>=95 or (sofr99_z or 0)>=2.0) and sofr99_recent10>=2)
    tail_watch = bool(sofr99_iorb is not None and sofr99_iorb >= 0.08 and ((sofr99_pct or 0)>=85 or (sofr99_z or 0)>=1.25))
    tail_status = "TRIGGERED" if tail_confirm else ("WATCH" if tail_watch else "NOT_TRIGGERED")
    out.append({
        "id":"repo_tail_stress","side":"WATCH","status":tail_status,
        "condition":"SOFR 99th-percentile minus IORB >=10bp with >=2/3 persistence and >=95th historical percentile (WATCH from 8bp/extreme tail)",
        "action":"Investigate repo distribution/dealer capacity. Tail stress alone is not the median SOFR funding-squeeze trigger.",
        "sofr99_iorb":sofr99_iorb,"percentile_1y":sofr99_pct,"zscore_1y":sofr99_z,"recent_obs_ge_10bp":sofr99_recent10,
    })

    term_kill = term is not None and term < 0.70
    out.append({"id":"term_premium_normalizes","side":"KILL","status":"TRIGGERED" if term_kill else "NOT_TRIGGERED","condition":"10Y term premium <0.70%","action":"Reduce fiscal-duration stress score if auctions and fiscal flows are also benign."})

    dollar_kill = dxy is not None and dxy > 101 and (dxy_3m or 0) > 0
    out.append({"id":"dollar_strength_reversal","side":"KILL","status":"TRIGGERED" if dollar_kill else "NOT_TRIGGERED","condition":"DXY >101 with positive 3-month momentum","action":"Reduce managed-devaluation/reserve-confidence overlays unless policy evidence strengthens materially."})

    gold_confirm = gold_3m is not None and gold_3m > 0.08 and term is not None and term > 0.80
    out.append({"id":"gold_real_yield_anomaly","side":"WATCH","status":"TRIGGERED" if gold_confirm else "NOT_TRIGGERED","condition":"Gold +8% over ~3m while term premium >0.80%","action":"Investigate official-sector/reserve diversification rather than automatically adding gold after the move."})
    return out
