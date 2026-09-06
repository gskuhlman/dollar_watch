from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from dollar_dashboard.pipeline import collect_live_bundle
from dollar_dashboard.news import classify_news
from dollar_dashboard.scoring import DEFAULT_OVERRIDES, score
from dollar_dashboard.portfolio import recommend, scenario_stress_test, ASSETS
from dollar_dashboard.storage import (
    save_snapshot, recent_snapshots, get_overrides, set_override, get_setting, set_setting,
    add_event, recent_events, save_alerts, recent_alerts,
)
from dollar_dashboard.alerts import generate_alerts
from dollar_dashboard.llm import analyze_with_local_llm

ROOT = Path(__file__).resolve().parent
DEFAULT_SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
ACTORS = json.loads((ROOT / "config" / "actors.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="Dollar Crisis Dashboard V2", page_icon="💵", layout="wide")


def severity(v: float) -> str:
    if v < 30: return "LOW"
    if v < 50: return "WATCH"
    if v < 70: return "ELEVATED"
    if v < 85: return "HIGH"
    return "ACUTE"


def fmt_money(v):
    try:
        v = float(v)
    except Exception:
        return "—"
    if abs(v) >= 1e12: return f"${v/1e12:.2f}T"
    if abs(v) >= 1e9: return f"${v/1e9:.1f}B"
    if abs(v) >= 1e6: return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"


def deterministic_analysis(scores, portfolio_df, news_class, prev=None):
    lines = []
    if prev and "scores" in prev:
        changes = []
        for k, v in scores["regimes"].items():
            old = prev["scores"].get("regimes", {}).get(k)
            if old is not None:
                changes.append((k, v - float(old)))
        changes.sort(key=lambda x: abs(x[1]), reverse=True)
        if changes:
            lines.append("**Largest regime changes:** " + ", ".join(f"{k} {d:+.1f}" for k, d in changes[:4]) + ".")
    dominant = max(scores["regimes"].items(), key=lambda kv: kv[1])
    lines.append(f"**Current phase:** {scores['phase']}. Early-warning {scores['early_warning_index']:.0f}/100; confirmation {scores['confirmation_index']:.0f}/100; data confidence {scores['confidence']:.0f}/100.")
    lines.append(f"**Dominant modeled regime:** {dominant[0]} at {dominant[1]:.1f}/100 ({severity(dominant[1])}).")
    active = []
    for regime, drivers in scores.get("drivers", {}).items():
        for d in drivers:
            active.append(f"{regime}: {d}")
    if active:
        lines.append("**Important causal drivers:** " + "; ".join(active[:10]) + ".")
    trades = portfolio_df[portfolio_df["Action"] != "HOLD"]
    if trades.empty:
        lines.append("**Hard portfolio recommendation:** HOLD. No model change clears the configured threshold after confidence, turnover, and anti-chasing guardrails.")
    else:
        lines.append("**Hard portfolio recommendation:** " + "; ".join(f"{r['Action']} {r['Asset']} ${abs(r['Trade $']):,.0f}" for _, r in trades.iterrows()) + ".")
    ns = news_class.get("scores", {})
    if ns:
        lines.append(f"**News triage:** policy {ns.get('policy_devaluation',0):+d}, external de-dollarization {ns.get('external_dedollarization',0):+d}, funding {ns.get('funding_stress',0):+d}, dollar support {ns.get('dollar_support',0):+d}, institutional {ns.get('institutional_stress',0):+d}. Headlines remain low-confidence until verified.")
    lines.append("**Red-team rule:** a falling dollar is not enough. Reserve-confidence risk becomes much stronger when USD weakness coexists with rising long yields/term premium, rising gold, weakening foreign Treasury demand, and worse funding/auction conditions. A global liquidity shock can instead produce a temporary dollar surge.")
    return "\n\n".join(lines)


@st.cache_data(ttl=900, show_spinner=False)
def load_live_data():
    return collect_live_bundle()


st.title("Dollar Crisis Early Warning Dashboard — V2")
st.caption("Leading indicators + market confirmation + policy/foreign actors + positioning/flows + hard but bounded portfolio recommendations.")

with st.sidebar:
    st.header("Controls")
    if st.button("Refresh all live data", type="primary", width="stretch"):
        st.cache_data.clear()
    portfolio_value = st.number_input(
        "Portfolio value ($)", 1000.0, 100_000_000.0,
        float(get_setting("portfolio_value", DEFAULT_SETTINGS["portfolio_value"])), step=5000.0,
    )
    min_trade = st.slider("Minimum trade threshold (%)", 0.5, 10.0, float(DEFAULT_SETTINGS.get("allocation_change_threshold_pct", 3.0)), 0.5)
    max_turnover = st.slider("Max one-run turnover (%)", 5.0, 50.0, float(DEFAULT_SETTINGS.get("max_turnover_pct", 25.0)), 2.5)
    st.divider()
    st.subheader("Local LLM (optional)")
    lm_url = st.text_input("OpenAI-compatible base URL", value=str(get_setting("lm_url", "")), placeholder="http://192.168.x.x:1234/v1")
    lm_model = st.text_input("Model (blank = first available)", value=str(get_setting("lm_model", "")))
    lm_timeout = st.number_input(
        "LLM response timeout (seconds)",
        min_value=30,
        max_value=1800,
        value=int(get_setting("lm_timeout", 300)),
        step=30,
        help="Ollama cloud-backed models can take longer than local models. 300 seconds is a reasonable starting point.",
    )
    if st.button("Save settings", width="stretch"):
        set_setting("portfolio_value", portfolio_value)
        set_setting("lm_url", lm_url)
        set_setting("lm_model", lm_model)
        set_setting("lm_timeout", int(lm_timeout))
        st.success("Settings saved")

with st.spinner("Collecting market, Treasury, CFTC, TIC, stablecoin and news signals..."):
    bundle = load_live_data()

snapshot = bundle["snapshot"]
news_df = bundle.get("news", pd.DataFrame())
news_class = classify_news(news_df)
overrides = get_overrides(DEFAULT_OVERRIDES)
scores = score(snapshot, news_class, overrides)

baseline = get_setting("baseline_allocation", DEFAULT_SETTINGS["baseline_allocation"])
portfolio_df, portfolio_meta = recommend(
    scores["regimes"], baseline, portfolio_value, min_trade_pct=min_trade,
    market_summary=snapshot.get("market_summary", {}), confidence=scores.get("confidence", 100), max_turnover_pct=max_turnover,
)
history = recent_snapshots(150)
prev = history[0] if history else None
current_alerts = generate_alerts(scores, portfolio_df, prev, float(DEFAULT_SETTINGS.get("alert_threshold_points", 8)))

# Header status row
c = st.columns(7)
for col, (name, val) in zip(c[:4], scores["regimes"].items()):
    delta = None
    if prev:
        old = prev.get("scores", {}).get("regimes", {}).get(name)
        if old is not None: delta = val - float(old)
    col.metric(name, f"{val:.0f}/100", None if delta is None else f"{delta:+.1f}", help=severity(val))
c[4].metric("Early warning", f"{scores['early_warning_index']:.0f}/100")
c[5].metric("Confirmation", f"{scores['confirmation_index']:.0f}/100")
c[6].metric("Data confidence", f"{scores['confidence']:.0f}/100")
st.info(f"**Phase: {scores['phase']}** — V2 deliberately separates leading evidence from price confirmation so the dashboard does not wait for DXY to break before reacting.")

(
    exec_tab, market_tab, flows_tab, policy_tab, portfolio_tab,
    analysis_tab, hist_tab, health_tab, roadmap_tab,
) = st.tabs([
    "Executive", "Markets & Funding", "Positioning & Foreign Flows", "Policy / Actors",
    "Portfolio", "Analysis", "Alerts & History", "Data Health", "V2 Roadmap",
])

with exec_tab:
    left, right = st.columns([1.15, 1])
    with left:
        r = pd.DataFrame({"Regime": list(scores["regimes"]), "Score": list(scores["regimes"].values())})
        st.plotly_chart(px.bar(r, x="Regime", y="Score", range_y=[0, 100], text="Score", title="Four independent risk regimes"), width="stretch")
    with right:
        components = pd.DataFrame({"Component": list(scores["components"]), "Score": list(scores["components"].values())})
        st.plotly_chart(px.bar(components, y="Component", x="Score", orientation="h", range_x=[0, 100], text="Score", title="Leading / transmission components"), width="stretch")

    st.subheader("What matters now")
    drivers = []
    for regime, ds in scores["drivers"].items():
        for d in ds: drivers.append((regime, d))
    if drivers:
        st.dataframe(pd.DataFrame(drivers, columns=["Regime", "Driver"]), width="stretch", hide_index=True)
    else:
        st.success("No high-threshold automated causal trigger is active.")

    a, b, d, e = st.columns(4)
    a.metric("Treasury auction stress", f"{snapshot.get('auction_stress_auto',0):.0f}/100")
    b.metric("CFTC USD-downside positioning", f"{snapshot.get('cftc_usd_downside_pressure',0):.0f}/100")
    d.metric("TIC de-dollarization pressure", f"{snapshot.get('tic_dedollarization_pressure',0):.0f}/100")
    e.metric("Stablecoin dollar support", f"{snapshot.get('stablecoin_dollar_support_auto',0):.0f}/100")

    if current_alerts:
        st.subheader("Actionable alerts")
        for a in current_alerts[:8]:
            st.warning(f"[{a['severity']}] {a['message']}")
    else:
        st.success("No alert threshold is currently crossed versus the prior saved snapshot.")

    if st.button("Save complete V2 snapshot + alerts", width="stretch"):
        payload = {
            **snapshot,
            "scores": scores,
            "news_scores": news_class.get("scores", {}),
            "overrides": {k: v["value"] for k, v in overrides.items()},
            "portfolio": portfolio_df.to_dict(orient="records"),
            "portfolio_meta": portfolio_meta,
            "alerts": current_alerts,
        }
        rid = save_snapshot(payload)
        save_alerts(current_alerts)
        st.success(f"Saved V2 snapshot #{rid}")

with market_tab:
    st.subheader("Market prices")
    market_summary = bundle.get("market_summary", pd.DataFrame())
    if market_summary.empty:
        st.warning("Market-price feed unavailable.")
    else:
        show = market_summary.copy()
        for col in ["1d", "5d", "1m", "3m", "1y"]:
            if col in show.columns: show[col] = show[col] * 100
        st.dataframe(show.round(2), width="stretch")
        choices = st.multiselect("Chart normalized market series", list(bundle["market_hist"].columns), default=[x for x in ["DXY", "Gold", "Long Treasuries ETF", "Developed ex-US Equities"] if x in bundle["market_hist"].columns])
        if choices:
            x = bundle["market_hist"][choices].dropna(how="all").ffill()
            x = 100 * x / x.apply(lambda s: s.dropna().iloc[0] if not s.dropna().empty else 1)
            fig = px.line(x, x=x.index, y=choices, title="Normalized market performance (start = 100)")
            st.plotly_chart(fig, width="stretch")

    st.subheader("Rates, term premium, inflation and funding")
    fred = bundle.get("fred_summary", pd.DataFrame())
    if fred.empty:
        st.warning("FRED feed unavailable.")
    else:
        st.dataframe(fred.round(3), width="stretch")
        focus = [x for x in ["2Y Treasury", "10Y Treasury", "30Y Treasury", "10Y TIPS real yield", "10Y breakeven inflation", "10Y term premium", "Financial Conditions Index", "Central bank liquidity swaps (millions)"] if x in bundle["fred_hist"].columns]
        selected = st.multiselect("Chart rates / funding series", list(bundle["fred_hist"].columns), default=focus[:5])
        if selected:
            fh = bundle["fred_hist"][selected].dropna(how="all")
            st.plotly_chart(px.line(fh, x=fh.index, y=selected, title="Rates / funding history"), width="stretch")

    st.subheader("Treasury auction absorption")
    st.metric("Automatic auction stress", f"{bundle.get('auction_stress',0):.0f}/100")
    if not bundle.get("auction_summary", pd.DataFrame()).empty:
        st.dataframe(bundle["auction_summary"].round(2), width="stretch", hide_index=True)
        st.caption("This compares bid-to-cover and bidder mix with prior same-tenor auctions. True when-issued auction tails remain a P1 roadmap item because a robust free live WI feed is not available.")

with flows_tab:
    st.subheader("CFTC FX positioning — early private-capital signal")
    st.caption("High USD-downside pressure means leveraged funds / asset managers are positioned unusually far toward foreign-currency strength versus their own recent history.")
    st.metric("Broad USD-downside positioning pressure", f"{bundle.get('cftc_pressure',0):.0f}/100")
    if bundle.get("cftc_summary", pd.DataFrame()).empty:
        st.warning("CFTC feed unavailable or monitored FX contracts were not found.")
    else:
        st.dataframe(bundle["cftc_summary"].round(2), width="stretch", hide_index=True)

    st.subheader("TIC major foreign Treasury holders")
    st.caption("Monthly data are structurally lagged, so V2 uses them as a structural-flow signal rather than a trading trigger.")
    st.metric("Country-level de-dollarization pressure", f"{bundle.get('tic_pressure',0):.0f}/100")
    tic_summary = bundle.get("tic_summary", pd.DataFrame())
    if tic_summary.empty:
        st.warning("TIC country feed unavailable.")
    else:
        st.dataframe(tic_summary.round(2), width="stretch", hide_index=True)
        reasons = bundle.get("tic_meta", {}).get("reasons", [])
        if reasons: st.write("**TIC drivers:** " + "; ".join(reasons))

    st.subheader("Stablecoins / digital-dollar structural demand")
    stable_meta = bundle.get("stable_meta", {})
    c1, c2, c3 = st.columns(3)
    c1.metric("USD stablecoin supply", fmt_money(stable_meta.get("usd_stablecoin_supply")))
    r90 = stable_meta.get("90d_growth")
    c2.metric("~90-day supply growth", "—" if r90 is None or pd.isna(r90) else f"{r90*100:+.1f}%")
    c3.metric("USD1 supply", fmt_money(stable_meta.get("usd1_supply")))
    if not bundle.get("stable_focus", pd.DataFrame()).empty:
        st.dataframe(bundle["stable_focus"].round(4), width="stretch", hide_index=True)
    st.caption("Stablecoin growth is treated as structural dollar support, not as a hedge against dollar purchasing-power loss. Reserve composition varies by issuer, so supply is not assumed to equal Treasury demand dollar-for-dollar.")

with policy_tab:
    st.subheader("Analyst evidence inputs")
    st.caption("Use these only for verified facts not captured well by public APIs. 0 = absent; 50 = material; 100 = acute/systemic.")
    labels = {
        "broad_fx_intervention": "Broad U.S./coordinated FX intervention",
        "fed_independence_pressure": "Pressure on Fed independence / rate path",
        "treasury_auction_stress": "Additional Treasury absorption stress",
        "foreign_official_selling": "Additional foreign official reserve selling",
        "brics_payment_progress": "Concrete BRICS / non-dollar payment infrastructure progress",
        "central_bank_gold_rotation": "Central-bank rotation into gold",
        "stablecoin_dollar_support": "Additional stablecoin-driven dollar/T-bill support",
        "commodity_dedollarization": "Material non-dollar commodity invoicing / settlement",
        "geopolitical_cyber_stress": "Geopolitical / cyber financial-system stress",
        "institutional_credibility_stress": "U.S. institutional / fiscal credibility stress",
        "capital_control_or_holder_fee_risk": "Capital controls / foreign Treasury holder fee / coercive restructuring risk",
    }
    with st.form("overrides_form"):
        pending, notes = {}, {}
        for key, label in labels.items():
            item = overrides.get(key, {"value": 0, "note": ""})
            pending[key] = st.slider(label, 0, 100, int(item.get("value", 0)), 5, key=f"slider_{key}")
            notes[key] = st.text_input(f"Evidence note — {label}", value=item.get("note", ""), key=f"note_{key}")
        if st.form_submit_button("Save analyst evidence", width="stretch"):
            for k, v in pending.items(): set_override(k, v, notes[k])
            st.success("Evidence saved. Refresh to recalculate.")

    st.subheader("Key policymakers / actors")
    st.dataframe(pd.DataFrame(ACTORS), width="stretch", hide_index=True)

    st.subheader("Evidence journal")
    with st.form("event_form", clear_on_submit=True):
        ec1, ec2 = st.columns(2)
        category = ec1.selectbox("Category", ["Policy", "Fed", "Treasury", "Foreign actor", "Market plumbing", "Stablecoin", "Institutional", "Geopolitical", "Other"])
        actor = ec2.text_input("Actor")
        title = st.text_input("Event / evidence")
        source_url = st.text_input("Source URL")
        impact = st.slider("Estimated directional risk impact (-100 supportive to +100 crisis pressure)", -100, 100, 0, 5)
        note = st.text_area("Notes")
        if st.form_submit_button("Add evidence event"):
            if title.strip():
                add_event(category, actor, title, source_url, impact, note)
                st.success("Evidence event added.")
    events = recent_events(100)
    if events:
        st.dataframe(pd.DataFrame(events), width="stretch", hide_index=True, column_config={"source_url": st.column_config.LinkColumn("source_url")})

    st.subheader("Current news monitor")
    if news_df.empty:
        st.warning("News feed unavailable.")
    else:
        buckets = st.multiselect("Filter news topics", sorted(news_df["bucket"].unique()), default=[])
        nd = news_df[news_df["bucket"].isin(buckets)] if buckets else news_df
        cols = [x for x in ["bucket", "title", "source", "published", "age_hours", "link"] if x in nd.columns]
        st.dataframe(nd[cols], width="stretch", hide_index=True, column_config={"link": st.column_config.LinkColumn("link")})
        st.caption("V2 weights newer headlines and higher-quality sources more heavily, but headline NLP remains triage—not verified evidence.")

with portfolio_tab:
    st.subheader("Current allocation")
    current = pd.DataFrame({"Asset": ASSETS, "Current %": [float(baseline.get(a, 0)) for a in ASSETS]})
    edited = st.data_editor(current, width="stretch", hide_index=True, disabled=["Asset"], num_rows="fixed")
    total = float(edited["Current %"].sum())
    if abs(total - 100) > 0.05:
        st.error(f"Allocation must total 100%. Current total: {total:.1f}%")
    elif st.button("Save current allocation", width="stretch"):
        new_base = dict(zip(edited["Asset"], edited["Current %"].astype(float)))
        set_setting("baseline_allocation", new_base)
        st.success("Allocation saved. Refresh to make it the baseline.")

    st.subheader("Hard recommendation engine")
    st.dataframe(portfolio_df, width="stretch", hide_index=True)
    st.caption(f"Crisis overlay {portfolio_meta['overlay_strength']*100:.1f}% • confidence scaling {portfolio_meta['confidence_scale']*100:.0f}% • one-way turnover {portfolio_meta['one_way_turnover_pct']:.1f}%.")
    if portfolio_meta.get("chase_notes"):
        for note in portfolio_meta["chase_notes"]: st.info(note)
    trades = portfolio_df[portfolio_df["Action"] != "HOLD"]
    if trades.empty:
        st.success("HOLD — no trade clears the threshold after confidence, anti-chasing and turnover guardrails.")
    else:
        for _, r in trades.iterrows():
            st.write(f"**{r['Action']} {r['Asset']}: ${abs(r['Trade $']):,.0f} → {r['Recommended %']:.1f}%**")
            st.caption(f"Why: {r['Why']} Reversal: {r['Reversal trigger']}")

    st.subheader("Scenario stress test")
    base_alloc = {a: float(baseline.get(a, 0)) for a in ASSETS}
    rec_alloc = dict(zip(portfolio_df["Asset"], portfolio_df["Recommended %"]))
    s1 = scenario_stress_test(base_alloc, portfolio_value).rename(columns={"Illustrative portfolio return %": "Current return %", "Illustrative P/L $": "Current P/L $"})
    s2 = scenario_stress_test(rec_alloc, portfolio_value).rename(columns={"Illustrative portfolio return %": "Recommended return %", "Illustrative P/L $": "Recommended P/L $"})
    stress = s1.merge(s2, on="Scenario")
    stress["Improvement % pts"] = stress["Recommended return %"] - stress["Current return %"]
    st.dataframe(stress, width="stretch", hide_index=True)
    st.caption("Scenario shocks are transparent model assumptions, not forecasts. Their purpose is to show which risks the recommended allocation is accepting or reducing.")

with analysis_tab:
    st.subheader("Deterministic analysis")
    st.markdown(deterministic_analysis(scores, portfolio_df, news_class, prev))
    st.subheader("Recommendation reversals")
    changed = portfolio_df[portfolio_df["Action"] != "HOLD"]
    if changed.empty:
        st.write("No active trades, so no new reversal triggers are required.")
    else:
        for _, r in changed.iterrows():
            st.write(f"**{r['Asset']}** — {r['Reversal trigger']}")

    st.divider()
    st.subheader("Local LLM red-team")
    st.caption("The local model receives the full V2 snapshot, data health, positioning/flows, recommendations and recent headlines. It is instructed to argue against the thesis as well as for it.")
    if st.button("Run local LLM analysis", width="stretch"):
        if not lm_url:
            st.error("Configure the local LLM base URL first.")
        else:
            payload = {
                "scores": scores,
                "portfolio_recommendation": portfolio_df.to_dict(orient="records"),
                "portfolio_meta": portfolio_meta,
                "snapshot": snapshot,
                "analyst_inputs": {k: v["value"] for k, v in overrides.items()},
                "headline_scores": news_class.get("scores", {}),
                "headlines": news_df.head(50).to_dict(orient="records") if not news_df.empty else [],
                "evidence_journal": recent_events(30),
            }
            try:
                text = analyze_with_local_llm(
                    payload,
                    base_url=lm_url,
                    model=lm_model or None,
                    timeout_seconds=int(lm_timeout),
                )
                st.markdown(text)
            except Exception as exc:
                st.error(f"Local LLM call failed: {exc}")

with hist_tab:
    st.subheader("Current alerts")
    if current_alerts:
        st.dataframe(pd.DataFrame(current_alerts), width="stretch", hide_index=True)
    else:
        st.success("No current alerts.")
    old_alerts = recent_alerts(100)
    if old_alerts:
        st.subheader("Saved alert history")
        st.dataframe(pd.DataFrame(old_alerts), width="stretch", hide_index=True)

    st.subheader("Snapshot history")
    if not history:
        st.info("No saved snapshots yet.")
    else:
        rows = []
        for h in reversed(history):
            row = {"captured_at": h.get("_captured_at", h.get("timestamp")), "phase": h.get("scores", {}).get("phase"), "early_warning": h.get("scores", {}).get("early_warning_index"), "confirmation": h.get("scores", {}).get("confirmation_index"), "confidence": h.get("scores", {}).get("confidence")}
            row.update(h.get("scores", {}).get("regimes", {}))
            rows.append(row)
        hdf = pd.DataFrame(rows)
        hdf["captured_at"] = pd.to_datetime(hdf["captured_at"], errors="coerce")
        st.dataframe(hdf, width="stretch", hide_index=True)
        cols = [c for c in scores["regimes"] if c in hdf.columns]
        if cols:
            st.plotly_chart(px.line(hdf, x="captured_at", y=cols, markers=True, range_y=[0,100], title="Regime history"), width="stretch")
        lead_cols = [c for c in ["early_warning", "confirmation", "confidence"] if c in hdf.columns]
        if lead_cols:
            st.plotly_chart(px.line(hdf, x="captured_at", y=lead_cols, markers=True, range_y=[0,100], title="Leading vs confirmation vs data confidence"), width="stretch")

with health_tab:
    st.subheader("Source health / recommendation confidence")
    health = bundle.get("health", pd.DataFrame())
    if health.empty:
        st.warning("No source-health data available.")
    else:
        st.dataframe(health.round(2), width="stretch", hide_index=True)
    st.markdown("""
### V2 interpretation rules

- **Confidence is not conviction.** It measures whether the feeds needed to support a recommendation are present and reasonably fresh.
- **Leading evidence and confirmation are separate.** Policy, positioning, foreign flows, term premium and market plumbing can raise early warning before spot USD confirms it.
- **Lagging data are down-weighted conceptually.** TIC is useful for structural direction, not same-day trading.
- **Hard recommendations are bounded.** Low data confidence automatically reduces portfolio overlay; one-run turnover is capped; large recent hedge gains trigger an anti-chasing limiter.
- **Manual evidence is auditable.** Policy or geopolitical facts that APIs cannot encode should be entered with a source/evidence note.
""")

with roadmap_tab:
    todo = ROOT / "TODO_V2.md"
    if todo.exists():
        st.markdown(todo.read_text(encoding="utf-8"))
    else:
        st.info("Roadmap file missing.")
