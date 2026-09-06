from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .data import fetch_market_history, fetch_fred_bundle, fetch_treasury_auctions, summarize_auction_stress
from .intelligence import (
    fetch_cftc_tff, summarize_cftc_fx, fetch_tic_major_holders, summarize_tic,
    fetch_stablecoins, summarize_stablecoins, build_data_health,
)
from .news import fetch_news


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

    # Market data
    try:
        market_hist, market_summary = fetch_market_history()
        bundle["market_hist"] = market_hist; bundle["market_summary"] = market_summary
        status["Market prices"] = {"ok": not market_summary.empty, "weight": 1.3, "last_date": _last_index(market_hist), "notes": "Yahoo Finance / exchange proxies"}
    except Exception as e:
        bundle["market_hist"] = pd.DataFrame(); bundle["market_summary"] = pd.DataFrame()
        status["Market prices"] = {"ok": False, "weight": 1.3, "error": str(e)}

    # FRED
    try:
        fred_hist, fred_summary = fetch_fred_bundle()
        bundle["fred_hist"] = fred_hist; bundle["fred_summary"] = fred_summary
        status["FRED rates / funding"] = {"ok": not fred_summary.empty, "weight": 1.5, "last_date": _last_index(fred_hist), "notes": "Rates, inflation, term premium, funding and foreign custody"}
    except Exception as e:
        bundle["fred_hist"] = pd.DataFrame(); bundle["fred_summary"] = pd.DataFrame()
        status["FRED rates / funding"] = {"ok": False, "weight": 1.5, "error": str(e)}

    # Treasury auctions
    try:
        auctions = fetch_treasury_auctions()
        auction_summary, auction_stress = summarize_auction_stress(auctions)
        bundle["auctions"] = auctions; bundle["auction_summary"] = auction_summary; bundle["auction_stress"] = auction_stress
        last = auctions["auction_date"].max() if not auctions.empty and "auction_date" in auctions else None
        status["Treasury auctions"] = {"ok": not auctions.empty, "weight": 1.2, "last_date": last, "notes": "Bid-to-cover and bidder-mix absorption"}
    except Exception as e:
        bundle["auctions"] = pd.DataFrame(); bundle["auction_summary"] = pd.DataFrame(); bundle["auction_stress"] = 0.0
        status["Treasury auctions"] = {"ok": False, "weight": 1.2, "error": str(e)}

    # CFTC positioning
    try:
        cftc = fetch_cftc_tff()
        cftc_summary, cftc_pressure = summarize_cftc_fx(cftc)
        bundle["cftc"] = cftc; bundle["cftc_summary"] = cftc_summary; bundle["cftc_pressure"] = cftc_pressure
        last = cftc["report_date"].max() if not cftc.empty and "report_date" in cftc else None
        status["CFTC FX positioning"] = {"ok": not cftc_summary.empty, "weight": 1.0, "last_date": last, "notes": "TFF leveraged money and asset managers"}
    except Exception as e:
        bundle["cftc"] = pd.DataFrame(); bundle["cftc_summary"] = pd.DataFrame(); bundle["cftc_pressure"] = 0.0
        status["CFTC FX positioning"] = {"ok": False, "weight": 1.0, "error": str(e)}

    # TIC country holdings
    try:
        tic = fetch_tic_major_holders()
        tic_summary, tic_pressure, tic_meta = summarize_tic(tic)
        bundle["tic"] = tic; bundle["tic_summary"] = tic_summary; bundle["tic_pressure"] = tic_pressure; bundle["tic_meta"] = tic_meta
        last = tic["date"].max() if not tic.empty and "date" in tic else None
        status["TIC country Treasury holdings"] = {"ok": not tic_summary.empty, "weight": 1.1, "last_date": last, "notes": "Monthly; naturally lagged"}
    except Exception as e:
        bundle["tic"] = pd.DataFrame(); bundle["tic_summary"] = pd.DataFrame(); bundle["tic_pressure"] = 0.0; bundle["tic_meta"] = {}
        status["TIC country Treasury holdings"] = {"ok": False, "weight": 1.1, "error": str(e)}

    # Stablecoins
    try:
        stable_assets, stable_hist = fetch_stablecoins()
        stable_focus, stable_meta, stable_support = summarize_stablecoins(stable_assets, stable_hist)
        bundle["stable_assets"] = stable_assets; bundle["stable_hist"] = stable_hist; bundle["stable_focus"] = stable_focus
        bundle["stable_meta"] = stable_meta; bundle["stable_support"] = stable_support
        last = stable_hist["date"].max() if not stable_hist.empty and "date" in stable_hist else pd.Timestamp.now(tz="UTC")
        status["Stablecoin supply"] = {"ok": not stable_assets.empty, "weight": 0.8, "last_date": last, "notes": "Digital-dollar structural demand proxy"}
    except Exception as e:
        bundle["stable_assets"] = pd.DataFrame(); bundle["stable_hist"] = pd.DataFrame(); bundle["stable_focus"] = pd.DataFrame()
        bundle["stable_meta"] = {}; bundle["stable_support"] = 0.0
        status["Stablecoin supply"] = {"ok": False, "weight": 0.8, "error": str(e)}

    # Headlines
    try:
        news = fetch_news()
        bundle["news"] = news
        last = news["published_dt"].max() if not news.empty and "published_dt" in news else None
        status["News discovery"] = {"ok": not news.empty, "weight": 0.7, "last_date": last, "notes": "Headline triage only; not a primary factual source"}
    except Exception as e:
        bundle["news"] = pd.DataFrame()
        status["News discovery"] = {"ok": False, "weight": 0.7, "error": str(e)}

    health_df, confidence = build_data_health(status)
    bundle["health"] = health_df
    bundle["data_confidence"] = confidence

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_summary": _index_dict(bundle["market_summary"]),
        "fred_summary": _index_dict(bundle["fred_summary"]),
        "auction_stress_auto": float(bundle.get("auction_stress", 0) or 0),
        "auction_summary": _records(bundle.get("auction_summary", pd.DataFrame())),
        "cftc_usd_downside_pressure": float(bundle.get("cftc_pressure", 0) or 0),
        "cftc_summary": _records(bundle.get("cftc_summary", pd.DataFrame())),
        "tic_dedollarization_pressure": float(bundle.get("tic_pressure", 0) or 0),
        "tic_summary": _records(bundle.get("tic_summary", pd.DataFrame())),
        "tic_meta": bundle.get("tic_meta", {}),
        "stablecoin_dollar_support_auto": float(bundle.get("stable_support", 0) or 0),
        "stablecoin_summary": _records(bundle.get("stable_focus", pd.DataFrame())),
        "stablecoin_meta": bundle.get("stable_meta", {}),
        "data_confidence": float(confidence),
        "data_health": _records(health_df),
    }
    bundle["snapshot"] = snapshot
    return bundle
