from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .data import (
    fetch_market_history, fetch_fred_bundle, fetch_treasury_auctions, fetch_upcoming_treasury_auctions,
    summarize_auction_stress, summarize_upcoming_auctions, summarize_offshore_fx_forward_proxy,
)
from .intelligence import (
    fetch_cftc_tff, summarize_cftc_fx, summarize_fx_positioning_squeeze,
    fetch_tic_major_holders, summarize_tic, summarize_tic_transactions,
    fetch_stablecoins, summarize_stablecoins,
    fetch_imf_cofer_usd_share, summarize_cofer,
    build_data_health, period_last_date,
)
from .fiscal import fetch_fiscal_pipeline
from .news import fetch_news
from .buybacks import fetch_buyback_schedule, summarize_buybacks
from .fed_policy import classify_fed_treasury_change
from .official_policy import collect_official_policy_bundle
from .treasury_financing import fetch_treasury_financing




def _last_index(df: pd.DataFrame):
    if df is None or df.empty:
        return None
    try:
        return df.index.max()
    except Exception:
        return None


def _records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    return df.where(pd.notnull(df), None).to_dict(orient="records")


def _index_dict(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    return df.where(pd.notnull(df), None).to_dict(orient="index")


def collect_live_bundle() -> dict[str, Any]:
    status: dict[str, dict[str, Any]] = {}
    bundle: dict[str, Any] = {}

    try:
        market_hist, market_summary = fetch_market_history()
        bundle["market_hist"] = market_hist; bundle["market_summary"] = market_summary
        bundle["offshore_fx_proxy"] = summarize_offshore_fx_forward_proxy(market_hist)
        status["Market prices"] = {"ok": not market_summary.empty, "weight": 1.3, "last_date": _last_index(market_hist), "notes": "Yahoo Finance / exchange proxies"}
        status["Offshore FX forward proxy"] = {"ok": bool(bundle["offshore_fx_proxy"].get("available")), "weight": 0.35, "last_date": _last_index(market_hist), "confidence_cap": 55.0, "notes": "Front currency futures vs spot anomaly proxy only; not true cross-currency basis"}
    except Exception as e:
        bundle["market_hist"] = pd.DataFrame(); bundle["market_summary"] = pd.DataFrame(); bundle["offshore_fx_proxy"] = {"available":False,"coverage":30.0,"actual_cross_currency_basis_available":False,"pairs":[],"reason":"Market proxy unavailable"}
        status["Market prices"] = {"ok": False, "weight": 1.3, "error": str(e)}
        status["Offshore FX forward proxy"] = {"ok": False, "weight": 0.35, "error": str(e)}

    try:
        fred_hist, fred_summary = fetch_fred_bundle()
        bundle["fred_hist"] = fred_hist; bundle["fred_summary"] = fred_summary
        bundle["fed_treasury_classification"] = classify_fed_treasury_change(_index_dict(fred_summary))
        status["FRED rates / funding"] = {"ok": not fred_summary.empty, "weight": 1.5, "last_date": _last_index(fred_hist), "notes": "Rates, inflation, repo spreads, funding, foreign custody, and H.4.1 Treasury maturity composition"}
    except Exception as e:
        bundle["fred_hist"] = pd.DataFrame(); bundle["fred_summary"] = pd.DataFrame(); bundle["fed_treasury_classification"] = {"classification":"INSUFFICIENT_DATA","confidence":0.0}
        status["FRED rates / funding"] = {"ok": False, "weight": 1.5, "error": str(e)}

    try:
        tf_z1, tf_money, tf_funding, tf_meta = fetch_treasury_financing()
        bundle["treasury_financing_z1"] = tf_z1
        bundle["treasury_financing_money"] = tf_money
        bundle["treasury_financing_funding"] = tf_funding
        bundle["treasury_financing_meta"] = tf_meta
        status["Treasury financing / Z.1"] = {
            "ok": bool(tf_meta.get("available")), "weight": 1.15,
            "last_date": _last_index(tf_z1),
            "confidence_cap": min(90.0, float(tf_meta.get("holder_coverage_pct", 0.0) or 0.0)),
            "notes": f"Quarterly Z.1 holder transactions + M2/deposit/H.8 confirmation + repo funding overlay. Holder coverage={tf_meta.get('holder_coverage_pct',0):.0f}%; holder and funding layers are kept separate to prevent double counting.",
        }
    except Exception as e:
        bundle["treasury_financing_z1"] = pd.DataFrame(); bundle["treasury_financing_money"] = pd.DataFrame(); bundle["treasury_financing_funding"] = pd.DataFrame()
        bundle["treasury_financing_meta"] = {"available":False,"classification":{"state":"UNKNOWN","score":None},"source_errors":{"collector":str(e)}}
        status["Treasury financing / Z.1"] = {"ok":False,"weight":1.15,"error":str(e),"notes":"Missing financing data is uncertainty, not benign private demand."}

    try:
        auctions = fetch_treasury_auctions()
        auction_summary, auction_stress = summarize_auction_stress(auctions)
        bundle["auctions"] = auctions; bundle["auction_summary"] = auction_summary; bundle["auction_stress"] = auction_stress
        last = auctions["auction_date"].max() if not auctions.empty and "auction_date" in auctions else None
        status["Treasury auctions"] = {
            "ok": not auctions.empty, "weight": 1.2, "last_date": last,
            "notes": "Historical results via schema-normalized FiscalData: bid-to-cover and bidder mix",
        }
    except Exception as e:
        bundle["auctions"] = pd.DataFrame(); bundle["auction_summary"] = pd.DataFrame(); bundle["auction_stress"] = 0.0
        status["Treasury auctions"] = {"ok": False, "weight": 1.2, "error": str(e), "notes": "Absence of auction data is NOT benign-auction evidence"}

    try:
        upcoming_raw = fetch_upcoming_treasury_auctions(days=35)
        upcoming = summarize_upcoming_auctions(upcoming_raw, days=35)
        bundle["upcoming_auctions"] = upcoming
        status["Treasury upcoming auctions"] = {
            "ok": not upcoming.empty, "weight": 0.35,
            # This is a calendar feed, so retrieval freshness matters; future auction/issue dates
            # are intentionally not used as observation dates.
            "last_date": pd.Timestamp.now(tz="UTC"),
            "notes": "Dedicated upcoming_auctions endpoint; future calendar only and excluded from historical auction freshness/stress",
        }
    except Exception as e:
        bundle["upcoming_auctions"] = pd.DataFrame()
        status["Treasury upcoming auctions"] = {"ok": False, "weight": 0.35, "error": str(e), "notes": "Historical auction scoring can still operate if this calendar feed fails"}


    try:
        buybacks, buyback_source = fetch_buyback_schedule()
        buyback_meta = summarize_buybacks(buybacks, buyback_source)
        bundle["buybacks"] = buybacks; bundle["buyback_meta"] = buyback_meta
        schedule_ok = int(buyback_meta.get("schedule_operations",0) or 0) > 0
        results_ok = bool(buyback_meta.get("results_available"))
        latest_result = pd.to_datetime(buyback_meta.get("latest_completed_operation"), errors="coerce", utc=True)
        schedule_cap = 100.0 if buyback_meta.get("max_amount_parse_status") == "OK" else 70.0
        status["Treasury buyback schedule"] = {
            "ok": schedule_ok, "weight": 0.45, "last_date": pd.Timestamp.now(tz="UTC"), "confidence_cap": schedule_cap,
            "notes": (f"Official tentative capacity/calendar only; schedule-rows={buyback_meta.get('schedule_operations',0)}, "
                      f"long-end scheduled={buyback_meta.get('long_end_operations',0)}. Announced capacity is not execution."),
        }
        result_cap = buyback_meta.get("result_completeness_pct")
        if result_cap is None: result_cap = 55.0 if results_ok else 0.0
        status["Treasury buyback results"] = {
            "ok": results_ok, "weight": 0.65, "confidence_cap": result_cap,
            "last_date": latest_result if pd.notna(latest_result) else None,
            "notes": (f"Completed result XMLs; attempted={buyback_meta.get('result_urls_attempted',0)}, "
                      f"completed={buyback_meta.get('completed_operations',0)}, strategy={buyback_meta.get('result_discovery_strategy','?')}. "
                      "Missing results are unknown execution, not zero buyback activity."),
            **({} if results_ok else {"error":"No completed TreasuryDirect result XML was ingested"}),
        }
    except Exception as e:
        bundle["buybacks"] = pd.DataFrame(); bundle["buyback_meta"] = {}
        status["Treasury buyback schedule"] = {"ok": False, "weight": 0.45, "error": str(e), "notes": "Buyback schedule unavailable; missing evidence, not zero policy capacity"}
        status["Treasury buyback results"] = {"ok": False, "weight": 0.65, "error": str(e), "notes": "Buyback execution unavailable; missing evidence, not zero activity"}

    try:
        cftc = fetch_cftc_tff()
        cftc_summary, cftc_pressure = summarize_cftc_fx(cftc)
        fx_squeeze, fx_squeeze_reasons = summarize_fx_positioning_squeeze(cftc_summary)
        bundle["cftc"] = cftc; bundle["cftc_summary"] = cftc_summary; bundle["cftc_pressure"] = cftc_pressure
        bundle["fx_positioning_squeeze"] = fx_squeeze; bundle["fx_positioning_squeeze_reasons"] = fx_squeeze_reasons
        last = cftc["report_date"].max() if not cftc.empty and "report_date" in cftc else None
        status["CFTC FX positioning"] = {"ok": not cftc_summary.empty, "weight": 1.0, "last_date": last, "notes": "TFF leveraged money and asset managers; also detects crowded foreign-FX shorts"}
    except Exception as e:
        bundle["cftc"] = pd.DataFrame(); bundle["cftc_summary"] = pd.DataFrame(); bundle["cftc_pressure"] = 0.0
        bundle["fx_positioning_squeeze"] = 0.0; bundle["fx_positioning_squeeze_reasons"] = []
        status["CFTC FX positioning"] = {"ok": False, "weight": 1.0, "error": str(e)}

    try:
        tic = fetch_tic_major_holders()
        tic_summary, tic_pressure, tic_meta = summarize_tic(tic)
        bundle["tic"] = tic; bundle["tic_summary"] = tic_summary; bundle["tic_pressure"] = tic_pressure; bundle["tic_meta"] = tic_meta
        bundle["tic_transaction_meta"] = summarize_tic_transactions(bundle.get("fred_hist", pd.DataFrame()))
        last = tic["date"].max() if not tic.empty and "date" in tic else None
        status["TIC country Treasury holdings"] = {"ok": not tic_summary.empty, "weight": 1.1, "last_date": last, "notes": "Monthly; structurally lagged and confidence-weighted before scoring"}
        tx_date = pd.to_datetime((bundle.get("tic_transaction_meta",{}).get("grand_total",{}) or {}).get("date"), errors="coerce", utc=True)
        status["TIC Treasury transactions / valuation"] = {"ok": bool(bundle.get("tic_transaction_meta")), "weight": 1.0, "last_date": tx_date, "notes": "Active net transactions are separated from position changes, LT valuation and residual/custody effects."}
    except Exception as e:
        bundle["tic"] = pd.DataFrame(); bundle["tic_summary"] = pd.DataFrame(); bundle["tic_pressure"] = 0.0; bundle["tic_meta"] = {}; bundle["tic_transaction_meta"] = {}
        status["TIC country Treasury holdings"] = {"ok": False, "weight": 1.1, "error": str(e)}
        status["TIC Treasury transactions / valuation"] = {"ok": False, "weight": 1.0, "error": str(e)}

    try:
        cofer = fetch_imf_cofer_usd_share()
        cofer_meta, cofer_pressure = summarize_cofer(cofer)
        bundle["cofer"] = cofer; bundle["cofer_meta"] = cofer_meta; bundle["cofer_pressure"] = cofer_pressure
        # Quarter strings are not guaranteed parseable. The API retrieval itself is fresh; the observation date is carried separately.
        status["IMF COFER"] = {"ok": not cofer.empty, "weight": 1.0, "last_date": period_last_date(cofer_meta.get("latest_period")), "notes": f"Quarterly reserve composition; freshness is based on observation quarter {cofer_meta.get('latest_period','?')}, not retrieval time"}
    except Exception as e:
        bundle["cofer"] = pd.DataFrame(); bundle["cofer_meta"] = {}; bundle["cofer_pressure"] = 0.0
        status["IMF COFER"] = {"ok": False, "weight": 1.0, "error": str(e), "notes": "Quarterly reserve-composition confirmation"}

    try:
        fiscal_raw, fiscal_meta, fiscal_stress = fetch_fiscal_pipeline()
        bundle["fiscal_raw"] = fiscal_raw; bundle["fiscal_meta"] = fiscal_meta; bundle["fiscal_stress"] = fiscal_stress
        last = pd.to_datetime(fiscal_meta.get("record_date"), errors="coerce", utc=True)
        status["Treasury fiscal flows"] = {"ok": bool(fiscal_meta), "weight": 1.1, "last_date": last, "notes": "Monthly Treasury Statement: receipts, outlays and deficit"}
    except Exception as e:
        bundle["fiscal_raw"] = pd.DataFrame(); bundle["fiscal_meta"] = {}; bundle["fiscal_stress"] = 0.0
        status["Treasury fiscal flows"] = {"ok": False, "weight": 1.1, "error": str(e)}

    try:
        stable_assets, stable_hist = fetch_stablecoins()
        stable_focus, stable_meta, stable_support = summarize_stablecoins(stable_assets, stable_hist)
        bundle["stable_assets"] = stable_assets; bundle["stable_hist"] = stable_hist; bundle["stable_focus"] = stable_focus
        bundle["stable_rwa"] = pd.DataFrame(stable_meta.get("rwa_products", []))
        bundle["stable_meta"] = stable_meta; bundle["stable_support"] = stable_support
        last = stable_hist["date"].max() if not stable_hist.empty and "date" in stable_hist else pd.Timestamp.now(tz="UTC")
        status["Stablecoin supply"] = {
            "ok": not stable_assets.empty, "weight": 0.8, "last_date": last,
            "notes": "Transactional stablecoins are peg-tested separately from tokenized Treasury/RWA products",
        }
    except Exception as e:
        bundle["stable_assets"] = pd.DataFrame(); bundle["stable_hist"] = pd.DataFrame(); bundle["stable_focus"] = pd.DataFrame(); bundle["stable_rwa"] = pd.DataFrame()
        bundle["stable_meta"] = {}; bundle["stable_support"] = 0.0
        status["Stablecoin supply"] = {"ok": False, "weight": 0.8, "error": str(e)}

    try:
        news = fetch_news()
        bundle["news"] = news
        last = news["published_dt"].max() if not news.empty and "published_dt" in news else None
        status["News discovery"] = {"ok": not news.empty, "weight": 0.5, "last_date": last, "notes": "Headline triage only; cannot directly become verified evidence"}
    except Exception as e:
        bundle["news"] = pd.DataFrame()
        status["News discovery"] = {"ok": False, "weight": 0.5, "error": str(e)}

    try:
        official_policy = collect_official_policy_bundle(timeout=12)
        bundle["official_policy"] = official_policy
        jp=official_policy.get("japan_fx_intervention",{}) or {}
        usfx=official_policy.get("us_fx_intervention",{}) or {}
        basis=official_policy.get("nyfed_basis_validation",{}) or {}
        stmt_ok=sum(1 for x in official_policy.get("canonical_statements",[]) if x.get("reachable"))
        stmt_live=sum(1 for x in official_policy.get("canonical_statements",[]) if x.get("live_reachable"))
        live_policy = bool(jp.get("live_reachable") or stmt_live or basis.get("live_reachable"))
        status["Official FX / policy feeds"] = {
            "ok": bool(jp.get("ok") or usfx.get("ok") or stmt_ok or basis.get("ok")), "weight": 0.8,
            "last_date": pd.Timestamp.now(tz="UTC"),
            "confidence_cap": 100.0 if live_policy else 85.0,
            "notes": f"Deterministic official feeds: Japan MOF intervention={bool(jp.get('ok'))}; NY Fed US FX={bool(usfx.get('ok'))}; canonical sources available={stmt_ok}/4 (live={stmt_live}); lagged NY Fed basis validation={bool(basis.get('ok'))}; cached fallbacks are auditable and capped when no live official source is reachable",
        }
    except Exception as e:
        bundle["official_policy"] = {"japan_fx_intervention":{"ok":False},"us_fx_intervention":{"ok":False},"canonical_statements":[]}
        status["Official FX / policy feeds"] = {"ok":False,"weight":0.8,"error":str(e),"notes":"Missing official-policy data is uncertainty, not benign evidence"}

    health_df, confidence = build_data_health(status)
    bundle["health"] = health_df
    bundle["data_confidence"] = confidence
    source_confidence = {str(r["source"]): float(r["confidence"]) for _, r in health_df.iterrows()} if not health_df.empty else {}
    component_confidence = {
        "market": source_confidence.get("Market prices", 0.0),
        "fred": source_confidence.get("FRED rates / funding", 0.0),
        "treasury_financing": source_confidence.get("Treasury financing / Z.1", 0.0),
        "auction": source_confidence.get("Treasury auctions", 0.0),
        "cftc": source_confidence.get("CFTC FX positioning", 0.0),
        "tic": source_confidence.get("TIC country Treasury holdings", 0.0),
        "tic_transactions": source_confidence.get("TIC Treasury transactions / valuation", 0.0),
        "cofer": source_confidence.get("IMF COFER", 0.0),
        "fiscal": source_confidence.get("Treasury fiscal flows", 0.0),
        "stablecoin": source_confidence.get("Stablecoin supply", 0.0),
        "buyback_schedule": source_confidence.get("Treasury buyback schedule", 0.0),
        "buyback_results": source_confidence.get("Treasury buyback results", 0.0),
        # Scoring confidence for *intensity* is zero when maximum authorized amounts are unknown,
        # even though schedule/results data may otherwise be healthy and useful descriptively.
        "buyback": (0.55*source_confidence.get("Treasury buyback schedule", 0.0) + 0.45*source_confidence.get("Treasury buyback results", 0.0))
                   if (bundle.get("buyback_meta",{}).get("intensity_status") == "KNOWN") else 0.0,
        "news": source_confidence.get("News discovery", 0.0),
        "official_policy": source_confidence.get("Official FX / policy feeds", 0.0),
    }

    # V2.9: a free front-futures/spot anomaly proxy adds modest visibility, but it is
    # explicitly NOT cross-currency basis.  True institutional basis remains a gap.
    offshore_proxy=bundle.get("offshore_fx_proxy",{}) or {}
    lagged_basis=(bundle.get("official_policy",{}) or {}).get("nyfed_basis_validation",{}) or {}
    offshore_funding_meta = {
        **offshore_proxy,
        # Do not inflate live coverage with a quarterly report.  The NY Fed report is a lagged
        # validation layer for the proxy, not a live institutional basis feed.
        "coverage": float(offshore_proxy.get("coverage",30.0) or 30.0),
        "desired_metrics": ["EURUSD cross-currency basis","JPYUSD cross-currency basis","CHFUSD cross-currency basis","OTC FX-swap dollar premium"],
        "nyfed_lagged_basis_validation": lagged_basis,
        "lagged_official_validation_available": bool(lagged_basis.get("ok")),
    }


    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_summary": _index_dict(bundle["market_summary"]),
        "fred_summary": _index_dict(bundle["fred_summary"]),
        "auction_stress_auto": float(bundle.get("auction_stress", 0) or 0),
        "auction_summary": _records(bundle.get("auction_summary", pd.DataFrame())),
        "upcoming_auctions": _records(bundle.get("upcoming_auctions", pd.DataFrame())),
        "cftc_usd_downside_pressure": float(bundle.get("cftc_pressure", 0) or 0),
        "cftc_summary": _records(bundle.get("cftc_summary", pd.DataFrame())),
        "fx_positioning_squeeze_risk": float(bundle.get("fx_positioning_squeeze", 0) or 0),
        "fx_positioning_squeeze_reasons": bundle.get("fx_positioning_squeeze_reasons", []),
        "tic_dedollarization_pressure": float(bundle.get("tic_pressure", 0) or 0),
        "tic_summary": _records(bundle.get("tic_summary", pd.DataFrame())),
        "tic_meta": bundle.get("tic_meta", {}),
        "tic_transaction_meta": bundle.get("tic_transaction_meta", {}),
        "cofer_dedollarization_pressure": float(bundle.get("cofer_pressure", 0) or 0),
        "cofer_meta": bundle.get("cofer_meta", {}),
        "fiscal_flow_stress_auto": float(bundle.get("fiscal_stress", 0) or 0),
        "fiscal_meta": bundle.get("fiscal_meta", {}),
        "stablecoin_dollar_support_auto": float(bundle.get("stable_support", 0) or 0),
        "stablecoin_summary": _records(bundle.get("stable_focus", pd.DataFrame())),
        "stablecoin_meta": bundle.get("stable_meta", {}),
        "treasury_buyback_meta": bundle.get("buyback_meta", {}),
        "treasury_buybacks": _records(bundle.get("buybacks", pd.DataFrame())),
        "fed_treasury_classification": bundle.get("fed_treasury_classification", {}),
        "treasury_financing_meta": bundle.get("treasury_financing_meta", {}),
        "offshore_usd_funding_meta": offshore_funding_meta,
        "official_policy_meta": bundle.get("official_policy", {}),
        "data_confidence": float(confidence),
        "source_confidence": source_confidence,
        "component_confidence": component_confidence,
        "data_health": _records(health_df),
    }
    bundle["snapshot"] = snapshot
    return bundle
