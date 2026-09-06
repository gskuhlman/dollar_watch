from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from dollar_dashboard.data import fetch_market_history, fetch_fred_bundle, fetch_treasury_auctions, summarize_auction_stress
from dollar_dashboard.news import fetch_news, classify_news
from dollar_dashboard.scoring import DEFAULT_OVERRIDES, score
from dollar_dashboard.portfolio import recommend, ASSETS
from dollar_dashboard.storage import save_snapshot, recent_snapshots, get_overrides, set_override, get_setting, set_setting
from dollar_dashboard.llm import analyze_with_local_llm

ROOT = Path(__file__).resolve().parent
DEFAULT_SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text())
ACTORS = json.loads((ROOT / "config" / "actors.json").read_text())

st.set_page_config(page_title="Dollar Crisis Early Warning Dashboard", page_icon="💵", layout="wide")


def severity(score_value: float) -> str:
    if score_value < 30: return "LOW"
    if score_value < 50: return "WATCH"
    if score_value < 70: return "ELEVATED"
    if score_value < 85: return "HIGH"
    return "ACUTE"


def deterministic_analysis(scores, portfolio_df, news_class, prev=None):
    lines = []
    if prev and "scores" in prev:
        changes = []
        for k, v in scores["regimes"].items():
            old = prev["scores"].get("regimes", {}).get(k)
            if old is not None:
                changes.append((k, v-float(old)))
        changes.sort(key=lambda x: abs(x[1]), reverse=True)
        if changes:
            top = ", ".join([f"{k} {d:+.1f}" for k,d in changes[:3]])
            lines.append(f"**Largest regime-score changes:** {top} points since the prior saved snapshot.")
    highest = max(scores["regimes"].items(), key=lambda kv: kv[1])
    lines.append(f"**Dominant current risk:** {highest[0]} at {highest[1]:.1f}/100 ({severity(highest[1])}).")
    active_drivers = []
    for regime, drivers in scores.get("drivers", {}).items():
        for d in drivers:
            active_drivers.append(f"{regime}: {d}")
    if active_drivers:
        lines.append("**Market-derived drivers:** " + "; ".join(active_drivers[:8]) + ".")
    trades = portfolio_df[portfolio_df["Action"] != "HOLD"].copy()
    if trades.empty:
        lines.append("**Portfolio action:** HOLD current strategic allocation; no modeled change clears the minimum-trade threshold.")
    else:
        parts = [f"{r['Action']} {r['Asset']} {abs(r['Trade $']):,.0f} dollars" for _, r in trades.iterrows()]
        lines.append("**Modeled trades:** " + "; ".join(parts) + ".")
    if news_class.get("scores"):
        ns = news_class["scores"]
        lines.append(f"**Headline heuristic:** policy-devaluation {ns.get('policy_devaluation',0):+d}, external de-dollarization {ns.get('external_dedollarization',0):+d}, funding stress {ns.get('funding_stress',0):+d}, dollar support {ns.get('dollar_support',0):+d}. Treat these as triage signals, not facts until source articles are reviewed.")
    lines.append("**Red-team rule:** do not treat a falling dollar alone as a crisis. A reserve-confidence warning becomes much stronger when the dollar falls while long yields and gold rise together, foreign demand weakens, and funding/auction stress worsens.")
    return "\n\n".join(lines)


@st.cache_data(ttl=900, show_spinner=False)
def load_live_data():
    mh, ms = fetch_market_history()
    fh, fs = fetch_fred_bundle()
    try:
        auctions = fetch_treasury_auctions()
        auction_summary, auction_stress = summarize_auction_stress(auctions)
    except Exception:
        auctions, auction_summary, auction_stress = pd.DataFrame(), pd.DataFrame(), 0.0
    news = fetch_news()
    return mh, ms, fh, fs, auctions, auction_summary, auction_stress, news


def build_snapshot(ms: pd.DataFrame, fs: pd.DataFrame, auction_summary: pd.DataFrame, auction_stress: float):
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "market_summary": ms.where(pd.notnull(ms), None).to_dict(orient="index") if not ms.empty else {},
        "fred_summary": fs.where(pd.notnull(fs), None).to_dict(orient="index") if not fs.empty else {},
        "auction_stress_auto": float(auction_stress),
        "auction_summary": auction_summary.where(pd.notnull(auction_summary), None).to_dict(orient="records") if not auction_summary.empty else [],
    }


st.title("Dollar Crisis Early Warning Dashboard")
st.caption("Regime detection + policy/foreign-actor monitoring + portfolio decision engine. Designed to challenge, not merely confirm, a dollar-crisis thesis.")

with st.sidebar:
    st.header("Controls")
    refresh = st.button("Refresh live data", type="primary", use_container_width=True)
    if refresh:
        st.cache_data.clear()
    portfolio_value = st.number_input("Portfolio value ($)", min_value=1000.0, max_value=100_000_000.0, value=float(get_setting("portfolio_value", DEFAULT_SETTINGS["portfolio_value"])), step=5000.0)
    min_trade = st.slider("Minimum trade threshold (%)", 0.5, 10.0, float(DEFAULT_SETTINGS.get("allocation_change_threshold_pct", 3.0)), 0.5)
    st.divider()
    st.subheader("Local LLM (optional)")
    lm_url = st.text_input("OpenAI-compatible base URL", value=str(get_setting("lm_url", "")), placeholder="http://192.168.x.x:1234/v1")
    lm_model = st.text_input("Model (blank = first available)", value=str(get_setting("lm_model", "")))
    if st.button("Save app settings", use_container_width=True):
        set_setting("portfolio_value", portfolio_value)
        set_setting("lm_url", lm_url)
        set_setting("lm_model", lm_model)
        st.success("Settings saved")

try:
    market_hist, market_summary, fred_hist, fred_summary, auctions_df, auction_summary, auction_stress, news_df = load_live_data()
    data_error = None
except Exception as e:
    market_hist, market_summary, fred_hist, fred_summary, auctions_df, auction_summary, news_df = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    auction_stress = 0.0
    data_error = str(e)

snapshot = build_snapshot(market_summary, fred_summary, auction_summary, auction_stress)
news_class = classify_news(news_df)
overrides = get_overrides(DEFAULT_OVERRIDES)
scores = score(snapshot, news_class, overrides)

baseline = get_setting("baseline_allocation", DEFAULT_SETTINGS["baseline_allocation"])
portfolio_df, portfolio_meta = recommend(scores["regimes"], baseline, portfolio_value, min_trade_pct=min_trade)

history = recent_snapshots(100)
prev = history[0] if history else None

if data_error:
    st.error(f"One or more live data feeds failed: {data_error}. The app still opens so analyst inputs/history can be reviewed.")

# Top score cards
cols = st.columns(4)
for col, (name, val) in zip(cols, scores["regimes"].items()):
    delta = None
    if prev and "scores" in prev:
        old = prev["scores"].get("regimes", {}).get(name)
        if old is not None:
            delta = val - float(old)
    col.metric(name, f"{val:.0f}/100", delta=f"{delta:+.1f}" if delta is not None else None, help=severity(val))

st.caption("Scores are evidence-weighted risk indicators, not statistical probabilities. Their main value is trend/change detection and forcing consistent analysis.")

ov_tab, market_tab, policy_tab, portfolio_tab, analysis_tab, history_tab, methodology_tab = st.tabs([
    "Overview", "Markets & Rates", "Policy / Foreign Actors", "Portfolio", "Analysis", "History", "Methodology"
])

with ov_tab:
    c1, c2 = st.columns([1.25, 1])
    with c1:
        regime_df = pd.DataFrame({"Regime": list(scores["regimes"].keys()), "Score": list(scores["regimes"].values())})
        st.plotly_chart(px.bar(regime_df, x="Regime", y="Score", range_y=[0,100], text="Score", title="Current regime risks"), use_container_width=True)
    with c2:
        comp_df = pd.DataFrame({"Component": list(scores["components"].keys()), "Score": list(scores["components"].values())})
        st.plotly_chart(px.bar(comp_df, x="Score", y="Component", orientation="h", range_x=[0,100], text="Score", title="Structural / transmission components"), use_container_width=True)
    st.subheader("Active market drivers")
    any_driver = False
    for regime, drivers in scores["drivers"].items():
        if drivers:
            any_driver = True
            st.markdown(f"**{regime}:** " + "; ".join(drivers))
    if not any_driver:
        st.info("No high-threshold market triggers are active in the automated rules. Analyst inputs and news may still raise risk scores.")
    st.metric("Automatic Treasury auction absorption stress", f"{auction_stress:.0f}/100")

    if st.button("Save this snapshot as baseline/history", use_container_width=True):
        payload = {
            "timestamp": snapshot["timestamp"], "market_summary": snapshot["market_summary"], "fred_summary": snapshot["fred_summary"],
            "auction_stress_auto": snapshot.get("auction_stress_auto", 0), "auction_summary": snapshot.get("auction_summary", []),
            "scores": scores, "news_scores": news_class.get("scores", {}), "overrides": {k:v["value"] for k,v in overrides.items()},
            "portfolio": portfolio_df.to_dict(orient="records")
        }
        rid = save_snapshot(payload)
        st.success(f"Saved snapshot #{rid}")

with market_tab:
    st.subheader("Market prices and trend returns")
    if market_summary.empty:
        st.warning("Market price feed unavailable.")
    else:
        show = market_summary.copy()
        for c in ["1d", "5d", "1m", "3m", "1y"]:
            if c in show.columns:
                show[c] = show[c] * 100
        st.dataframe(show.round(2), use_container_width=True)
        choices = st.multiselect("Chart market series", list(market_hist.columns), default=[x for x in ["DXY", "Gold", "Long Treasuries ETF"] if x in market_hist.columns])
        if choices:
            norm = market_hist[choices].dropna(how="all").copy()
            for c in norm.columns:
                first = norm[c].dropna().iloc[0] if not norm[c].dropna().empty else None
                if first:
                    norm[c] = 100 * norm[c] / first
            st.plotly_chart(px.line(norm, title="Normalized price index (start = 100)"), use_container_width=True)

    st.subheader("Fed / rates / liquidity series")
    if fred_summary.empty:
        st.warning("FRED feed unavailable.")
    else:
        st.dataframe(fred_summary.round(3), use_container_width=True)
        rate_choices = st.multiselect("Chart FRED series", list(fred_hist.columns), default=[x for x in ["10Y Treasury", "30Y Treasury", "10Y breakeven inflation", "10Y TIPS real yield"] if x in fred_hist.columns])
        if rate_choices:
            st.plotly_chart(px.line(fred_hist[rate_choices], title="Rates / liquidity history"), use_container_width=True)

    st.subheader("Treasury auction absorption")
    st.caption("Official Treasury FiscalData auction results. Stress compares the latest major coupon auction with the prior eight auctions of the same tenor using bid-to-cover and bidder mix; it is not a when-issued auction-tail calculation.")
    st.metric("Automatic auction stress", f"{auction_stress:.0f}/100")
    if not auction_summary.empty:
        st.dataframe(auction_summary.round(2), use_container_width=True, hide_index=True)
    else:
        st.warning("Treasury auction feed unavailable.")

with policy_tab:
    st.subheader("Analyst adjustments — add verified evidence the automated feeds do not capture")
    st.caption("0 = benign/absent; 50 = clearly material; 100 = acute/systemic. Save only after reviewing source evidence.")
    labels = {
        "broad_fx_intervention": "Broad U.S./coordinated FX intervention",
        "fed_independence_pressure": "Pressure on Fed independence / rates",
        "treasury_auction_stress": "Additional Treasury auction / market-absorption stress (manual override)",
        "foreign_official_selling": "Additional foreign official selling / reserve reduction (manual override)",
        "brics_payment_progress": "Concrete BRICS / non-dollar payment progress",
        "central_bank_gold_rotation": "Central-bank rotation into gold",
        "stablecoin_dollar_support": "Stablecoin-driven structural dollar/T-bill support",
        "geopolitical_cyber_stress": "Geopolitical / cyber financial-system stress",
        "institutional_credibility_stress": "U.S. institutional / fiscal credibility stress",
    }
    with st.form("overrides_form"):
        pending = {}
        notes = {}
        for key, label in labels.items():
            pending[key] = st.slider(label, 0, 100, int(overrides[key]["value"]), 5, key=f"slider_{key}")
            notes[key] = st.text_input(f"Evidence note — {label}", value=overrides[key].get("note", ""), key=f"note_{key}")
        submit = st.form_submit_button("Save analyst inputs", use_container_width=True)
        if submit:
            for k, v in pending.items():
                set_override(k, v, notes[k])
            st.success("Analyst inputs saved. Refresh/rerun to recalculate scores.")

    st.divider()
    st.subheader("Policy people / actors to monitor")
    st.dataframe(pd.DataFrame(ACTORS), use_container_width=True, hide_index=True)

    st.subheader("Current headline monitor")
    if news_df.empty:
        st.warning("News RSS feed unavailable.")
    else:
        bucket = st.multiselect("Filter topics", sorted(news_df["bucket"].unique()), default=[])
        nd = news_df[news_df["bucket"].isin(bucket)] if bucket else news_df
        st.dataframe(nd[["bucket","title","source","published","link"]], use_container_width=True, hide_index=True, column_config={"link": st.column_config.LinkColumn("link")})
        st.caption("Headline scoring is deliberately weak evidence. Open primary/source reporting before changing analyst inputs or making trades.")

with portfolio_tab:
    st.subheader("Current strategic allocation")
    current_df = pd.DataFrame({"Asset": ASSETS, "Current %": [float(baseline.get(a,0)) for a in ASSETS]})
    edited = st.data_editor(current_df, use_container_width=True, hide_index=True, disabled=["Asset"], num_rows="fixed")
    total = float(edited["Current %"].sum())
    if abs(total - 100) > 0.05:
        st.error(f"Allocation must total 100%. Current total: {total:.1f}%")
    else:
        if st.button("Save current allocation", use_container_width=True):
            new_base = dict(zip(edited["Asset"], edited["Current %"].astype(float)))
            set_setting("baseline_allocation", new_base)
            st.success("Current allocation saved. Rerun/refresh to use it as the new starting portfolio.")

    st.subheader("Recommendation engine")
    st.dataframe(portfolio_df, use_container_width=True, hide_index=True)
    st.caption(f"Crisis overlay strength: {portfolio_meta['overlay_strength']*100:.1f}%. The engine only shifts from the current allocation when regime scores exceed 35, and caps crisis-driven reallocation at 75% so it does not make an all-in macro bet.")
    trades = portfolio_df[portfolio_df["Action"] != "HOLD"]
    if trades.empty:
        st.success("HOLD — no recommended trade clears the configured minimum threshold.")
    else:
        for _, r in trades.iterrows():
            verb = "Buy" if r["Trade $"] > 0 else "Reduce"
            st.write(f"**{verb} {r['Asset']}: ${abs(r['Trade $']):,.0f}** → target {r['Recommended %']:.1f}%")

with analysis_tab:
    st.subheader("Rule-based analysis")
    st.markdown(deterministic_analysis(scores, portfolio_df, news_class, prev))
    st.divider()
    st.subheader("Local LLM red-team analysis")
    st.caption("Optional. Sends the current dashboard data and headlines only to the OpenAI-compatible endpoint you configure; no cloud LLM is required.")
    if st.button("Run local LLM analysis", use_container_width=True):
        if not lm_url:
            st.error("Configure a local LLM base URL in the sidebar first.")
        else:
            llm_payload = {
                "scores": scores,
                "portfolio_recommendation": portfolio_df.to_dict(orient="records"),
                "market_summary": snapshot["market_summary"],
                "fred_summary": snapshot["fred_summary"],
                "auction_stress_auto": snapshot.get("auction_stress_auto", 0),
                "auction_summary": snapshot.get("auction_summary", []),
                "analyst_inputs": {k:v["value"] for k,v in overrides.items()},
                "headline_scores": news_class.get("scores", {}),
                "headlines": news_df.head(35).to_dict(orient="records") if not news_df.empty else [],
            }
            try:
                with st.spinner("Analyzing with local model..."):
                    text = analyze_with_local_llm(llm_payload, base_url=lm_url, model=lm_model or None)
                st.markdown(text)
            except Exception as e:
                st.error(f"Local LLM call failed: {e}")

with history_tab:
    if not history:
        st.info("No saved snapshots yet. Use the Overview tab to save today's baseline.")
    else:
        hist_rows = []
        for h in reversed(history):
            row = {"captured_at": h.get("_captured_at", h.get("timestamp"))}
            row.update(h.get("scores", {}).get("regimes", {}))
            row.update(h.get("scores", {}).get("components", {}))
            hist_rows.append(row)
        hdf = pd.DataFrame(hist_rows)
        hdf["captured_at"] = pd.to_datetime(hdf["captured_at"], errors="coerce")
        st.dataframe(hdf, use_container_width=True, hide_index=True)
        regime_cols = [c for c in scores["regimes"] if c in hdf.columns]
        if regime_cols:
            st.plotly_chart(px.line(hdf, x="captured_at", y=regime_cols, markers=True, range_y=[0,100], title="Regime score history"), use_container_width=True)

with methodology_tab:
    st.markdown("""
### Design principles

- **No single crisis score.** The app separately detects managed devaluation, fiscal/inflation stress, a global dollar funding squeeze, and a reserve-confidence crisis.
- **Causal combinations matter.** The strongest reserve warning is not simply a falling DXY; it is a falling dollar combined with rising long yields, rising gold, weaker foreign demand and worsening Treasury/funding conditions.
- **Disconfirming evidence is required.** Hawkish Fed policy, strong Treasury demand, stablecoin/T-bill growth and relative weakness in alternative reserve systems should lower conviction.
- **Price data is not enough.** Analyst inputs explicitly capture policy interventions, foreign official behavior, BRICS infrastructure, institutional credibility and geopolitical risk.
- **Portfolio changes are bounded.** The engine blends crisis-regime target portfolios into the user's existing allocation and avoids all-in changes based on a single macro thesis.

### Automated public feeds

- Yahoo Finance via `yfinance`: DXY proxy, gold, Bitcoin, U.S. equities, long Treasuries and major FX crosses.
- Federal Reserve Economic Data (FRED CSV): Treasury yields, TIPS real yields, inflation breakevens, SOFR, Fed balance sheet, reverse repo, VIX, high-yield spread, foreign-official Treasury holdings and weekly foreign custody changes.
- U.S. Treasury FiscalData API: recent auction bid-to-cover and primary/direct/indirect bidder take-down for major coupon tenors.
- Google News RSS: headline discovery only. Headlines are triage signals and should be verified against primary/authoritative reporting.

### High-value data to add in later versions

Auction-tail/when-issued data, detailed TIC country flows, repo fails and market depth, CFTC FX positioning, options risk reversals, cross-currency basis, central-bank gold purchases, stablecoin market-cap/reserve changes, commodity invoicing and sanctions/payment-network changes.

**Investment note:** This is a research and decision-support tool. The scores are not mathematically calibrated probabilities and the allocation engine is not individualized fiduciary advice.
""")
