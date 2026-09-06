from __future__ import annotations

import math
from typing import Any

from .evidence import effective_evidence_value


def _v(d: dict, *path, default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _safe(x, default=0.0):
    try:
        x = float(x)
        return default if math.isnan(x) else x
    except Exception:
        return default


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def _points(value, bands):
    value = _safe(value, None)
    if value is None:
        return 0
    pts = 0
    for threshold, p in bands:
        if value >= threshold:
            pts = p
    return pts


def _conf(snapshot: dict, key: str, default=100.0) -> float:
    return _clamp(_v(snapshot, "component_confidence", key, default=default)) / 100.0


def _eff(value: float, conf: float) -> float:
    return _clamp(_safe(value)) * max(0.0, min(1.0, conf))


DEFAULT_OVERRIDES = {
    "broad_fx_intervention": 0,
    "fed_independence_pressure": 0,
    "treasury_auction_stress": 0,
    "foreign_official_selling": 0,
    "brics_payment_progress": 0,
    "central_bank_gold_rotation": 0,
    "stablecoin_dollar_support": 0,
    "commodity_dedollarization": 0,
    "geopolitical_cyber_stress": 0,
    "institutional_credibility_stress": 0,
    "capital_control_or_holder_fee_risk": 0,
}


def _verified_overrides(overrides: dict[str, dict]) -> tuple[dict[str, float], dict[str, dict]]:
    out = {}
    audit = {}
    for k, item in overrides.items():
        raw = float(item.get("value", 0) or 0)
        status = str(item.get("verification_status", "UNVERIFIED"))
        url = str(item.get("source_url", ""))
        effective = effective_evidence_value(raw, status, url)
        out[k] = effective
        audit[k] = {
            "raw": raw,
            "effective": round(effective, 1),
            "verification_status": status,
            "source_url": url,
            "source_tier": item.get("source_tier", ""),
        }
    return out, audit


def score(snapshot: dict, news_classification: dict, overrides: dict[str, dict]) -> dict:
    m = snapshot.get("market_summary", {})
    f = snapshot.get("fred_summary", {})
    n = news_classification.get("scores", {})
    ov, override_audit = _verified_overrides(overrides)

    market_conf = _conf(snapshot, "market")
    fred_conf = _conf(snapshot, "fred")
    auction_conf = _conf(snapshot, "auction")
    cftc_conf = _conf(snapshot, "cftc")
    tic_conf = _conf(snapshot, "tic")
    tic_tx_conf = _conf(snapshot, "tic_transactions", default=0.0)
    cofer_conf = _conf(snapshot, "cofer")
    fiscal_conf = _conf(snapshot, "fiscal")
    stable_conf = _conf(snapshot, "stablecoin")
    news_conf = _conf(snapshot, "news")

    dxy_last = _safe(_v(m, "DXY", "last"), None)
    dxy_1m = _safe(_v(m, "DXY", "1m"))
    dxy_3m = _safe(_v(m, "DXY", "3m"))
    gold_3m = _safe(_v(m, "Gold", "3m"))
    tlt_1m = _safe(_v(m, "Long Treasuries ETF", "1m"))
    eur_3m = _safe(_v(m, "EURUSD", "3m"))
    jpy_3m = _safe(_v(m, "USDJPY", "3m"))
    chf_3m = _safe(_v(m, "USDCHF", "3m"))

    y30 = _safe(_v(f, "30Y Treasury", "last"))
    y30_3m = _safe(_v(f, "30Y Treasury", "3m_change"))
    real10 = _safe(_v(f, "10Y TIPS real yield", "last"))
    breakeven = _safe(_v(f, "10Y breakeven inflation", "last"))
    breakeven_3m = _safe(_v(f, "10Y breakeven inflation", "3m_change"))
    fwd_infl = _safe(_v(f, "5Y5Y forward inflation", "last"))
    term_premium = _safe(_v(f, "10Y term premium", "last"))
    term_premium_3m = _safe(_v(f, "10Y term premium", "3m_change"))
    vix = _safe(_v(f, "VIX", "last"))
    hy = _safe(_v(f, "High-yield spread", "last"))
    nfci = _safe(_v(f, "Financial Conditions Index", "last"))
    swaps = _safe(_v(f, "Central bank liquidity swaps (millions)", "last"))
    fima_repo = _safe(_v(f, "FIMA repo - foreign official (millions)", "last"))
    swaps_1m = _safe(_v(f, "Central bank liquidity swaps (millions)", "1m_change"))
    sofr_iorb = _safe(_v(f, "SOFR-IORB spread", "last"), None)
    sofr99_iorb = _safe(_v(f, "SOFR99-IORB spread", "last"), None)
    sofr99_pct = _safe(_v(f, "SOFR99-IORB spread", "percentile_1y"), None)
    sofr99_z = _safe(_v(f, "SOFR99-IORB spread", "zscore_1y"), None)
    sofr99_recent10 = _safe(_v(f, "SOFR99-IORB spread", "recent_obs_ge_10bp"), 0)
    tgcr_disp = _safe(_v(f, "TGCR dispersion", "last"), None)
    reserves_3m = _safe(_v(f, "Reserve balances (billions)", "3m_change"))
    tga_3m = _safe(_v(f, "Treasury General Account (billions)", "3m_change"))
    foreign_custody_yoy = _safe(_v(f, "Foreign custody UST YoY change (millions)", "last"))
    foreign_official_3m = _safe(_v(f, "Foreign official Treasury holdings (millions)", "3m_change"))

    auction_raw = _safe(snapshot.get("auction_stress_auto"))
    cftc_raw = _safe(snapshot.get("cftc_usd_downside_pressure"))
    fx_squeeze_raw = _safe(snapshot.get("fx_positioning_squeeze_risk"))
    tic_raw = _safe(snapshot.get("tic_dedollarization_pressure"))
    cofer_raw = _safe(snapshot.get("cofer_dedollarization_pressure"))
    fiscal_flow_raw = _safe(snapshot.get("fiscal_flow_stress_auto"))
    stable_raw = _safe(snapshot.get("stablecoin_dollar_support_auto"))
    buyback_intensity = _safe(_v(snapshot, "treasury_buyback_meta", "intensity"))
    buyback_schedule_conf = _conf(snapshot, "buyback_schedule", default=0.0)
    buyback_results_conf = _conf(snapshot, "buyback_results", default=0.0)
    buyback_conf = _conf(snapshot, "buyback", default=0.0)
    offshore_funding_coverage = _clamp(_v(snapshot, "offshore_usd_funding_meta", "coverage", default=30.0))

    auction_auto = _eff(auction_raw, auction_conf)
    cftc_pressure = _eff(cftc_raw, cftc_conf)
    fx_squeeze_auto = _eff(fx_squeeze_raw, cftc_conf)
    tic_pressure = _eff(tic_raw, tic_conf)
    cofer_pressure = _eff(cofer_raw, cofer_conf)
    fiscal_flow = _eff(fiscal_flow_raw, fiscal_conf)
    stablecoin_auto = _eff(stable_raw, stable_conf)

    drivers = {
        "managed_devaluation": [],
        "fiscal_treasury": [],
        "inflation_debasement": [],
        "dollar_squeeze": [],
        "reserve_confidence": [],
        "fx_positioning_squeeze": [],
    }

    # Headline scores are triage only and intentionally weak; they cannot become high-impact evidence.
    policy_news = max(-6, min(8, 0.8 * n.get("policy_devaluation", 0) * news_conf))
    external_news = max(-5, min(7, 0.7 * n.get("external_dedollarization", 0) * news_conf))
    funding_news = max(0, min(6, 0.7 * n.get("funding_stress", 0) * news_conf))
    support_news = max(-5, min(6, 0.7 * n.get("dollar_support", 0) * news_conf))
    inst_news = max(0, min(6, 0.7 * n.get("institutional_stress", 0) * news_conf))

    policy_intent = 8.0
    policy_intent += 0.42 * ov.get("broad_fx_intervention", 0)
    policy_intent += 0.25 * ov.get("fed_independence_pressure", 0)
    policy_intent += 0.18 * ov.get("capital_control_or_holder_fee_risk", 0)
    policy_intent += policy_news
    policy_intent = _clamp(policy_intent)

    external = 0.36 * tic_pressure + 0.22 * cofer_pressure
    tic_tx_meta = snapshot.get("tic_transaction_meta", {}) or {}
    official_net_tx = _safe(_v(tic_tx_meta, "foreign_official", "net_transactions_mn"), None)
    total_net_tx = _safe(_v(tic_tx_meta, "grand_total", "net_transactions_mn"), None)
    if official_net_tx is not None:
        if official_net_tx < -25000: external += 8 * tic_tx_conf
        if official_net_tx < -50000: external += 6 * tic_tx_conf
        if official_net_tx > 25000: external -= 5 * tic_tx_conf
    if total_net_tx is not None:
        if total_net_tx < -50000: external += 8 * tic_tx_conf
        if total_net_tx > 50000: external -= 6 * tic_tx_conf
    external += 0.16 * ov.get("foreign_official_selling", 0)
    external += 0.20 * ov.get("brics_payment_progress", 0)
    external += 0.13 * ov.get("central_bank_gold_rotation", 0)
    external += 0.16 * ov.get("commodity_dedollarization", 0)
    external += external_news
    # FRED weekly custody is fresher than TIC and is confidence-weighted independently.
    if foreign_custody_yoy < -100000:
        external += 8 * fred_conf
    if foreign_custody_yoy < -300000:
        external += 8 * fred_conf
    if foreign_official_3m < -100000:
        external += 7 * fred_conf
    external = _clamp(external)

    support = 0.70 * stablecoin_auto + 0.25 * ov.get("stablecoin_dollar_support", 0) + support_news
    support = _clamp(support)

    fiscal_supply = 10.0
    fiscal_supply += fred_conf * _points(y30, [(4.5, 5), (5.0, 12), (5.5, 20), (6.0, 30)])
    if y30_3m > 0.25: fiscal_supply += 8 * fred_conf
    if y30_3m > 0.60: fiscal_supply += 8 * fred_conf
    if term_premium > 0.65: fiscal_supply += 8 * fred_conf
    if term_premium > 1.00: fiscal_supply += 10 * fred_conf
    if term_premium_3m > 0.20: fiscal_supply += 7 * fred_conf
    fiscal_supply += 0.30 * auction_auto
    fiscal_supply += 0.25 * fiscal_flow
    # Buybacks are a policy-response/liquidity-support signal, not proof of failed demand.
    # Keep the direct score contribution deliberately small; the auction channel remains primary.
    fiscal_supply += 0.05 * _eff(buyback_intensity, buyback_conf)
    fiscal_supply += 0.10 * ov.get("treasury_auction_stress", 0)
    fiscal_supply += 0.10 * ov.get("institutional_credibility_stress", 0)
    fiscal_supply = _clamp(fiscal_supply)

    inflation = 7.0
    if breakeven > 2.4: inflation += 8 * fred_conf
    if breakeven > 2.6: inflation += 10 * fred_conf
    if breakeven > 3.0: inflation += 12 * fred_conf
    if breakeven_3m > 0.20: inflation += 8 * fred_conf
    if fwd_infl > 2.5: inflation += 8 * fred_conf
    if fwd_infl > 2.8: inflation += 10 * fred_conf
    # Gold rising despite high real yields can indicate monetary/reserve demand, but do not double-count it as pure inflation.
    if gold_3m > 0.10 and real10 > 1.75:
        inflation += 5 * market_conf
    inflation += 0.14 * ov.get("fed_independence_pressure", 0)
    inflation += 0.12 * ov.get("institutional_credibility_stress", 0)
    inflation = _clamp(inflation)

    plumbing = 6.0
    plumbing += fred_conf * _points(vix, [(20, 8), (30, 18), (40, 30)])
    plumbing += fred_conf * _points(hy, [(4, 6), (5, 14), (7, 25)])
    plumbing += fred_conf * _points(nfci, [(0.0, 5), (0.5, 12), (1.0, 20)])
    if swaps > 1000: plumbing += 8 * fred_conf
    if swaps > 5000 or swaps_1m > 2500: plumbing += 12 * fred_conf
    if sofr_iorb is not None and sofr_iorb > 0.05: plumbing += 6 * fred_conf
    if sofr_iorb is not None and sofr_iorb > 0.10: plumbing += 10 * fred_conf
    # Repo-tail stress is distinct from median SOFR stress. A 99th-percentile print near 10bp
    # does not mean the median SOFR-IORB trigger is about to fire. Tail pressure contributes
    # modestly only when it is historically extreme/persistent.
    repo_tail_confirm = bool(sofr99_iorb is not None and sofr99_iorb >= 0.10 and ((sofr99_pct or 0) >= 95 or (sofr99_z or 0) >= 2.0) and sofr99_recent10 >= 2)
    repo_tail_watch = bool(sofr99_iorb is not None and sofr99_iorb >= 0.08 and ((sofr99_pct or 0) >= 85 or (sofr99_z or 0) >= 1.25))
    if repo_tail_confirm: plumbing += 8 * fred_conf
    elif repo_tail_watch: plumbing += 3 * fred_conf
    if tgcr_disp is not None and tgcr_disp > 0.10: plumbing += 6 * fred_conf
    if reserves_3m < -300 and tga_3m > 300: plumbing += 6 * fred_conf
    plumbing += 0.15 * auction_auto
    plumbing += 0.12 * ov.get("geopolitical_cyber_stress", 0)
    plumbing += funding_news
    plumbing = _clamp(plumbing)

    institutional = _clamp(
        5 + 0.40 * ov.get("institutional_credibility_stress", 0)
        + 0.25 * ov.get("fed_independence_pressure", 0)
        + 0.28 * ov.get("capital_control_or_holder_fee_risk", 0)
        + inst_news
    )

    # Market confirmation is price-derived and must not be confused with leading causal evidence.
    confirmation = 6.0
    toxic_legs = 0
    if dxy_3m < -0.03: confirmation += 12 * market_conf; toxic_legs += 1
    if dxy_3m < -0.07: confirmation += 8 * market_conf
    if y30_3m > 0.25: confirmation += 12 * fred_conf; toxic_legs += 1
    if gold_3m > 0.08: confirmation += 12 * market_conf; toxic_legs += 1
    if toxic_legs >= 2: confirmation += 8 * min(market_conf, fred_conf)
    if toxic_legs == 3: confirmation += 10 * min(market_conf, fred_conf)
    if eur_3m > 0.03: confirmation += 4 * market_conf
    if jpy_3m < -0.03: confirmation += 4 * market_conf
    if chf_3m < -0.03: confirmation += 4 * market_conf
    confirmation = _clamp(confirmation)

    early_warning = _clamp(
        0.17 * policy_intent + 0.10 * cftc_pressure + 0.16 * external
        + 0.18 * fiscal_supply + 0.12 * inflation + 0.12 * plumbing + 0.08 * institutional
        + 0.07 * fx_squeeze_auto - 0.08 * max(0, support - 50)
    )

    managed = _clamp(8 + 0.48 * policy_intent + 0.18 * cftc_pressure + 0.25 * confirmation - 0.10 * support)
    if dxy_3m < -0.03: drivers["managed_devaluation"].append("DXY down >3% over ~3 months")
    if cftc_pressure >= 60: drivers["managed_devaluation"].append("CFTC positioning supports broad USD downside")
    if policy_intent >= 50: drivers["managed_devaluation"].append("Verified policy-intent evidence is elevated")

    fiscal = _clamp(7 + 0.67 * fiscal_supply + 0.12 * institutional + 0.12 * confirmation)
    if term_premium > 0.65: drivers["fiscal_treasury"].append("10Y term premium is elevated")
    if auction_auto >= 35: drivers["fiscal_treasury"].append(f"Confidence-adjusted auction stress {auction_auto:.0f}/100")
    if fiscal_flow >= 30: drivers["fiscal_treasury"].append(f"Confidence-adjusted fiscal-flow stress {fiscal_flow:.0f}/100")

    debasement = _clamp(6 + 0.66 * inflation + 0.16 * institutional + 0.14 * confirmation)
    if breakeven > 2.6: drivers["inflation_debasement"].append("10Y breakeven inflation >2.6%")
    if fwd_infl > 2.5: drivers["inflation_debasement"].append("5Y5Y inflation expectations >2.5%")
    if gold_3m > 0.10 and real10 > 1.75: drivers["inflation_debasement"].append("Gold rising despite high real yields; investigate non-inflation reserve demand")

    squeeze = 6.0 + 0.70 * plumbing
    if dxy_1m > 0.03: squeeze += 12 * market_conf; drivers["dollar_squeeze"].append("DXY up >3% in ~1 month")
    if dxy_1m > 0.06: squeeze += 8 * market_conf
    if swaps > 1000: drivers["dollar_squeeze"].append("Central-bank USD liquidity swap usage is elevated")
    if fima_repo > 1000: drivers["dollar_squeeze"].append("FIMA foreign-official repo usage is elevated")
    if sofr_iorb is not None and sofr_iorb > 0.10: drivers["dollar_squeeze"].append("Median SOFR is >10bp above IORB")
    if repo_tail_confirm: drivers["dollar_squeeze"].append("SOFR 99th-percentile repo tail is persistently/historically stressed")
    elif repo_tail_watch: drivers["dollar_squeeze"].append("SOFR 99th-percentile repo tail is elevated; median SOFR remains a separate signal")
    if tlt_1m < -0.05: squeeze += 4 * market_conf
    squeeze = _clamp(squeeze)

    reserve = _clamp(4 + 0.34 * external + 0.18 * fiscal_supply + 0.15 * institutional + 0.29 * confirmation - 0.10 * support)
    if toxic_legs >= 2: drivers["reserve_confidence"].append("Multiple USD-down / long-yields-up / gold-up legs are active")
    if toxic_legs == 3: drivers["reserve_confidence"].append("Toxic trio active: USD down + long yields up + gold up")
    if tic_pressure >= 30: drivers["reserve_confidence"].append(f"Confidence-adjusted TIC pressure {tic_pressure:.0f}/100")
    if cofer_pressure >= 30: drivers["reserve_confidence"].append(f"COFER reserve-share pressure {cofer_pressure:.0f}/100")

    fx_squeeze = 5 + 0.70 * fx_squeeze_auto
    # Confirmation of a short-covering squeeze = crowded shorts plus foreign FX strengthening.
    if jpy_3m < -0.03: fx_squeeze += 8 * market_conf
    if eur_3m > 0.03: fx_squeeze += 5 * market_conf
    if chf_3m < -0.03: fx_squeeze += 5 * market_conf
    fx_squeeze = _clamp(fx_squeeze)
    if fx_squeeze_auto >= 55:
        drivers["fx_positioning_squeeze"].extend(snapshot.get("fx_positioning_squeeze_reasons", [])[:4])
    if fx_squeeze_auto >= 55 and (jpy_3m < -0.03 or chf_3m < -0.03 or eur_3m > 0.03):
        drivers["fx_positioning_squeeze"].append("Crowded foreign-currency shorts are unwinding into USD weakness")

    regimes = {
        "Managed dollar devaluation": round(managed, 1),
        "Fiscal / Treasury supply stress": round(fiscal, 1),
        "Inflation / monetary debasement": round(debasement, 1),
        "Dollar funding squeeze": round(squeeze, 1),
        "Reserve-confidence crisis": round(reserve, 1),
        "FX positioning squeeze": round(fx_squeeze, 1),
    }

    max_regime = max(regimes.values()) if regimes else 0
    if early_warning >= 55 and confirmation < 40:
        phase = "PRECONDITION / EARLY WARNING"
    elif early_warning >= 50 and confirmation >= 40:
        phase = "TRANSITION"
    elif confirmation >= 60 and max_regime >= 70:
        phase = "CONFIRMED STRESS"
    elif max_regime >= 50:
        phase = "WATCH / MIXED"
    else:
        phase = "QUIET / NORMAL"

    # Normalized mix is descriptive, NOT a probability. Only regimes above 35 contribute.
    active = {k: max(0.0, v - 35.0) for k, v in regimes.items()}
    denom = sum(active.values())
    mix = {k: round(100.0 * v / denom, 1) if denom else 0.0 for k, v in active.items()}

    confidence_audit = {
        "Auction stress": {"raw": round(auction_raw,1), "confidence": round(auction_conf*100,1), "effective": round(auction_auto,1)},
        "CFTC USD-downside": {"raw": round(cftc_raw,1), "confidence": round(cftc_conf*100,1), "effective": round(cftc_pressure,1)},
        "FX squeeze": {"raw": round(fx_squeeze_raw,1), "confidence": round(cftc_conf*100,1), "effective": round(fx_squeeze_auto,1)},
        "TIC de-dollarization": {"raw": round(tic_raw,1), "confidence": round(tic_conf*100,1), "effective": round(tic_pressure,1)},
        "TIC transaction demand": {"raw": round(total_net_tx or 0,1), "confidence": round(tic_tx_conf*100,1), "effective": round((total_net_tx or 0)*tic_tx_conf,1), "units":"$mn net transactions"},
        "COFER": {"raw": round(cofer_raw,1), "confidence": round(cofer_conf*100,1), "effective": round(cofer_pressure,1)},
        "Fiscal flows": {"raw": round(fiscal_flow_raw,1), "confidence": round(fiscal_conf*100,1), "effective": round(fiscal_flow,1)},
        "Stablecoin support": {"raw": round(stable_raw,1), "confidence": round(stable_conf*100,1), "effective": round(stablecoin_auto,1)},
        "Treasury buyback schedule": {"raw": round(buyback_intensity,1), "confidence": round(buyback_schedule_conf*100,1), "effective": round(_eff(buyback_intensity,buyback_schedule_conf),1)},
        "Treasury buyback results": {"raw": round(buyback_intensity,1), "confidence": round(buyback_results_conf*100,1), "effective": round(_eff(buyback_intensity,buyback_results_conf),1)},
    }

    # Evidence coverage is separate from risk. V2.6 distinguishes broad/generic coverage from
    # CRITICAL coverage. Plenty of market data cannot substitute for missing verified policy intent
    # in the managed-devaluation regime, and lots of spot data cannot substitute for stale reserve data.
    def _verified(keys):
        vals=[]
        for k in keys:
            a=override_audit.get(k,{})
            vals.append(100.0 if a.get("verification_status")=="VERIFIED" and a.get("source_tier") not in {"","UNSOURCED"} else 0.0)
        return sum(vals)/len(vals) if vals else 0.0

    policy_critical=_verified(["broad_fx_intervention","fed_independence_pressure","capital_control_or_holder_fee_risk"])
    reserve_policy_critical=_verified(["foreign_official_selling","brics_payment_progress","central_bank_gold_rotation","commodity_dedollarization"])
    generic_coverage = {
        "Managed dollar devaluation": _clamp(0.42*market_conf*100 + 0.20*cftc_conf*100 + 0.18*buyback_schedule_conf*100 + 0.20*news_conf*100),
        "Fiscal / Treasury supply stress": _clamp(0.28*fred_conf*100 + 0.28*auction_conf*100 + 0.24*fiscal_conf*100 + 0.10*tic_conf*100 + 0.05*buyback_schedule_conf*100 + 0.05*buyback_results_conf*100),
        "Inflation / monetary debasement": _clamp(0.62*fred_conf*100 + 0.28*market_conf*100 + 0.10*news_conf*100),
        "Dollar funding squeeze": _clamp(0.80*fred_conf*100 + 0.20*market_conf*100),
        "Reserve-confidence crisis": _clamp(0.20*market_conf*100 + 0.18*fred_conf*100 + 0.18*tic_conf*100 + 0.12*tic_tx_conf*100 + 0.16*cofer_conf*100 + 0.08*stable_conf*100 + 0.08*news_conf*100),
        "FX positioning squeeze": _clamp(0.72*cftc_conf*100 + 0.28*market_conf*100),
    }
    critical_coverage = {
        "Managed dollar devaluation": policy_critical,
        "Fiscal / Treasury supply stress": _clamp(0.40*auction_conf*100 + 0.35*fiscal_conf*100 + 0.25*fred_conf*100),
        "Inflation / monetary debasement": _clamp(0.75*fred_conf*100 + 0.25*market_conf*100),
        # Domestic repo/facility coverage is strong, but a global dollar squeeze can first appear
        # in cross-currency basis / FX swaps. Offshore coverage is therefore an explicit critical
        # subcomponent rather than silently calling the regime 100% observed.
        "Dollar funding squeeze": _clamp(0.62*fred_conf*100 + 0.08*market_conf*100 + 0.30*offshore_funding_coverage),
        "Reserve-confidence crisis": _clamp(0.24*tic_conf*100 + 0.20*tic_tx_conf*100 + 0.21*cofer_conf*100 + 0.18*fred_conf*100 + 0.10*reserve_policy_critical + 0.07*market_conf*100),
        "FX positioning squeeze": _clamp(0.78*cftc_conf*100 + 0.22*market_conf*100),
    }
    # Critical coverage gets half the weight. Thus a fully populated market tape with zero verified
    # devaluation-policy evidence cannot masquerade as ~70% coverage of policy intent.
    regime_coverage = {k: round(_clamp(0.50*generic_coverage[k] + 0.50*critical_coverage[k]),1) for k in generic_coverage}
    regime_coverage_details={k:{"effective":regime_coverage[k],"generic":round(generic_coverage[k],1),"critical":round(critical_coverage[k],1)} for k in regime_coverage}
    regime_coverage_details["Dollar funding squeeze"].update({
        "domestic_funding_coverage": round(_clamp(0.90*fred_conf*100 + 0.10*market_conf*100),1),
        "offshore_funding_coverage": round(offshore_funding_coverage,1),
        "offshore_gap": snapshot.get("offshore_usd_funding_meta",{}).get("reason",""),
    })

    return {
        "regimes": regimes,
        "regime_evidence_coverage": regime_coverage,
        "regime_evidence_coverage_details": regime_coverage_details,
        "regime_mix_not_probability": mix,
        "components": {
            "Policy intent / intervention": round(policy_intent, 1),
            "Fundamental USD-downside positioning": round(cftc_pressure, 1),
            "FX positioning squeeze risk": round(fx_squeeze_auto, 1),
            "External de-dollarization pressure": round(external, 1),
            "Structural dollar support": round(support, 1),
            "Fiscal / Treasury supply pressure": round(fiscal_supply, 1),
            "Inflation / debasement pressure": round(inflation, 1),
            "Treasury / repo / funding plumbing stress": round(plumbing, 1),
            "Institutional credibility stress": round(institutional, 1),
            "Treasury buyback policy-response intensity": round(_eff(buyback_intensity,buyback_conf),1),
        },
        "confidence_adjustments": confidence_audit,
        "fed_treasury_classification": snapshot.get("fed_treasury_classification", {}),
        "repo_tail_signal": {
            "status": "CONFIRM" if repo_tail_confirm else ("WATCH" if repo_tail_watch else "NORMAL"),
            "sofr99_iorb": sofr99_iorb, "percentile_1y": sofr99_pct, "zscore_1y": sofr99_z,
            "recent_obs_ge_10bp": int(sofr99_recent10 or 0),
            "note": "SOFR99 tail stress is separate from the median SOFR-IORB trigger."
        },
        "verified_override_audit": override_audit,
        "early_warning_index": round(early_warning, 1),
        "confirmation_index": round(confirmation, 1),
        "confidence": round(_safe(snapshot.get("data_confidence"), 50.0), 1),
        "phase": phase,
        "drivers": drivers,
        "toxic_trio_legs": toxic_legs,
        "note": "Regime scores are 0-100 risk indices, not probabilities. Normalized regime mix is descriptive only.",
    }
