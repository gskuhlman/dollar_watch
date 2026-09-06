"""Headless snapshot collector for cron / Windows Task Scheduler.

Usage:
    python collector.py

It fetches live data, scores the four regimes, calculates the model portfolio,
saves the result to SQLite, and prints a concise change/alert summary.
"""
from __future__ import annotations

import json
from pathlib import Path

from dollar_dashboard.data import market_snapshot
from dollar_dashboard.news import fetch_news, classify_news
from dollar_dashboard.scoring import DEFAULT_OVERRIDES, score
from dollar_dashboard.portfolio import recommend
from dollar_dashboard.storage import get_overrides, get_setting, recent_snapshots, save_snapshot

ROOT = Path(__file__).resolve().parent
DEFAULT_SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text())


def main():
    prior = recent_snapshots(1)
    prior = prior[0] if prior else None
    snap = market_snapshot()
    news = fetch_news()
    news_class = classify_news(news)
    overrides = get_overrides(DEFAULT_OVERRIDES)
    scores = score(snap, news_class, overrides)
    portfolio_value = float(get_setting("portfolio_value", DEFAULT_SETTINGS["portfolio_value"]))
    baseline = get_setting("baseline_allocation", DEFAULT_SETTINGS["baseline_allocation"])
    min_trade = float(DEFAULT_SETTINGS.get("allocation_change_threshold_pct", 3.0))
    portfolio, meta = recommend(scores["regimes"], baseline, portfolio_value, min_trade_pct=min_trade)
    payload = {
        **snap,
        "scores": scores,
        "news_scores": news_class.get("scores", {}),
        "overrides": {k:v["value"] for k,v in overrides.items()},
        "portfolio": portfolio.to_dict(orient="records"),
    }
    rid = save_snapshot(payload)
    print(f"Saved snapshot #{rid}")
    for name, val in scores["regimes"].items():
        old = None if not prior else prior.get("scores",{}).get("regimes",{}).get(name)
        delta = "" if old is None else f" ({val-float(old):+.1f})"
        print(f"{name}: {val:.1f}/100{delta}")
    trades = portfolio[portfolio["Action"] != "HOLD"]
    if trades.empty:
        print("Portfolio: HOLD — no modeled trade clears the minimum threshold.")
    else:
        print("Portfolio actions:")
        for _, r in trades.iterrows():
            print(f"  {r['Action']:6} {r['Asset']}: ${abs(r['Trade $']):,.0f} -> {r['Recommended %']:.1f}%")


if __name__ == "__main__":
    main()
