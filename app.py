from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from dollar_dashboard.pipeline import collect_live_bundle
from dollar_dashboard.news import classify_news
from dollar_dashboard.scoring import DEFAULT_OVERRIDES, score
from dollar_dashboard.portfolio import recommend, scenario_stress_test, scenario_hedge_alignment, ASSETS
from dollar_dashboard.storage import (
    save_snapshot, save_snapshot_if_new, recent_snapshots, get_overrides, set_override, get_setting, set_setting,
    add_event, recent_events, save_alerts, recent_alerts, save_verification_check, recent_verification_checks,
    upsert_verification_queue, recent_verification_queue, update_verification_queue_check, update_verification_queue_approval,
)
from dollar_dashboard.alerts import generate_alerts
from dollar_dashboard.llm import analyze_with_local_llm, verify_claim_against_source, compact_previous_context
from dollar_dashboard.triggers import evaluate_triggers
from dollar_dashboard.evidence import classify_source, check_source_url, fetch_source_text
from dollar_dashboard.verification import primary_source_candidates, discover_primary_evidence
from dollar_dashboard.run_history import classify_snapshot_change

ROOT = Path(__file__).resolve().parent
DEFAULT_SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
ACTORS = json.loads((ROOT / "config" / "actors.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="dollar_watch V2.7", page_icon="💵", layout="wide")


def severity(v: float) -> str:
    if v < 30: return "LOW"
    if v < 50: return "WATCH"
    if v < 70: return "ELEVATED"
    if v < 85: return "HIGH"
    return "ACUTE"


def fmt_money(v):
    try: v=float(v)
    except Exception: return "—"
    if abs(v)>=1e12: return f"${v/1e12:.2f}T"
    if abs(v)>=1e9: return f"${v/1e9:.1f}B"
    if abs(v)>=1e6: return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"


PRIMARY_SOURCE_HINTS = {
    "Fed / Warsh": "federalreserve.gov / newyorkfed.org",
    "Treasury / Bessent": "home.treasury.gov / newyorkfed.org",
    "FX intervention": "home.treasury.gov / newyorkfed.org / mof.go.jp / boj.or.jp",
    "BRICS / de-dollarization": "official BRICS communiqué / member central bank or finance ministry",
    "China": "pbc.gov.cn / safe.gov.cn",
    "Central-bank gold": "relevant central bank; WGC as secondary research",
    "Funding stress": "federalreserve.gov / newyorkfed.org",
    "Stablecoins": "issuer reserve/attestation page + Treasury/Fed/SEC if policy-related",
}


def build_verification_queue(news_df: pd.DataFrame, max_rows: int = 30) -> pd.DataFrame:
    if news_df is None or news_df.empty:
        return pd.DataFrame()
    q = news_df.head(max_rows).copy()
    q["claim"] = q["title"].astype(str)
    priority_map = {"FX intervention":"P0","Treasury / Bessent":"P0","Fed / Warsh":"P0","Funding stress":"P0","BRICS / de-dollarization":"P1","China":"P1","Central-bank gold":"P1","Stablecoins":"P1"}
    q["priority"] = q["bucket"].astype(str).map(lambda b: priority_map.get(b,"P2"))
    q["source_tier"] = q["link"].astype(str).map(lambda u: classify_source(u).get("source_tier", "UNSOURCED"))
    q["preferred_verification_source"] = q["bucket"].astype(str).map(lambda b: PRIMARY_SOURCE_HINTS.get(b, "primary government/central-bank source if available"))
    q["verification_status"] = "UNVERIFIED"
    q["primary_source_candidates"] = q.apply(lambda r: "; ".join(x["url"] for x in primary_source_candidates(str(r.get("bucket","")),str(r.get("claim","")))),axis=1)
    # Queue integrity: reject partial/truncated records rather than feeding fragments to the verifier/LLM.
    required = ["bucket","claim","source","link"]
    mask = pd.Series(True,index=q.index)
    for c in required:
        mask &= q[c].notna() & q[c].astype(str).str.strip().ne("")
    mask &= q["link"].astype(str).str.startswith(("http://","https://"))
    mask &= q["claim"].astype(str).str.len().ge(10)
    q=q[mask].copy()
    q["integrity_status"]="COMPLETE"
    cols = [c for c in ["priority","bucket","claim","source","published","source_tier","preferred_verification_source","verification_status","integrity_status","primary_source_candidates","link"] if c in q.columns]
    return q.sort_values(["priority","published"],ascending=[True,False],na_position="last")[cols]


def deterministic_analysis(scores, portfolio_df, news_class, prev=None):
    lines=[]
    if prev and "scores" in prev:
        changes=[]
        for k,v in scores["regimes"].items():
            old=prev["scores"].get("regimes",{}).get(k)
            if old is not None: changes.append((k,v-float(old)))
        changes.sort(key=lambda x:abs(x[1]),reverse=True)
        if changes: lines.append("**Largest risk-index changes:** "+", ".join(f"{k} {d:+.1f}" for k,d in changes[:5])+".")
    dominant=max(scores["regimes"].items(),key=lambda kv:kv[1])
    lines.append(f"**Current phase:** {scores['phase']}. Early warning {scores['early_warning_index']:.0f}/100; confirmation {scores['confirmation_index']:.0f}/100; data-quality confidence {scores['confidence']:.0f}/100.")
    lines.append(f"**Highest absolute risk index:** {dominant[0]} at {dominant[1]:.1f}/100 ({severity(dominant[1])}). These are risk indices, not probabilities.")
    active=[]
    for regime,drivers in scores.get("drivers",{}).items():
        for d in drivers: active.append(f"{regime}: {d}")
    if active: lines.append("**Important causal drivers:** "+"; ".join(active[:12])+".")
    trades=portfolio_df[portfolio_df["Action"]!="HOLD"]
    if trades.empty:
        lines.append("**Hard portfolio recommendation:** HOLD. No change clears confidence, minimum-size, turnover and anti-chasing guardrails.")
    else:
        lines.append("**Hard portfolio recommendation:** "+"; ".join(f"{r['Action']} {r['Asset']} ${abs(r['Trade $']):,.0f}" for _,r in trades.iterrows())+".")
    ns=news_class.get("scores",{})
    if ns:
        lines.append(f"**Headline triage only:** policy {ns.get('policy_devaluation',0):+d}, external {ns.get('external_dedollarization',0):+d}, funding {ns.get('funding_stress',0):+d}, dollar support {ns.get('dollar_support',0):+d}, institutional {ns.get('institutional_stress',0):+d}. These are discovery leads, not verified evidence.")
    lines.append("**Red-team rule:** distinguish Treasury supply/duration stress from inflation, fundamental dollar weakness from FX short-covering, and dollar debasement from a global dollar-funding squeeze.")
    return "\n\n".join(lines)


@st.cache_data(ttl=900, show_spinner=False)
def load_live_data():
    return collect_live_bundle()


st.title("dollar_watch — Dollar Crisis Early Warning Dashboard V2.7")
st.caption("Evidence provenance + confidence-weighted leading indicators + six causal regimes + machine reversal triggers + bounded portfolio actions.")

with st.sidebar:
    st.header("Controls")
    if st.button("Refresh all live data", type="primary", width="stretch"):
        st.cache_data.clear()
    portfolio_value=st.number_input("Portfolio value ($)",1000.0,100_000_000.0,float(get_setting("portfolio_value",DEFAULT_SETTINGS["portfolio_value"])),step=5000.0)
    min_trade=st.slider("Minimum trade threshold (%)",0.5,10.0,float(DEFAULT_SETTINGS.get("allocation_change_threshold_pct",3.0)),0.5)
    min_position=st.slider("Minimum new position (%)",1.0,10.0,float(DEFAULT_SETTINGS.get("min_position_pct",2.0)),0.5)
    min_trade_dollars=st.number_input("Minimum actionable trade ($)",100.0,100_000.0,float(DEFAULT_SETTINGS.get("min_trade_dollars",1000)),step=500.0)
    max_turnover=st.slider("Max one-run turnover (%)",5.0,50.0,float(DEFAULT_SETTINGS.get("max_turnover_pct",25.0)),2.5)
    st.divider()
    st.subheader("Local LLM (optional)")
    lm_url=st.text_input("OpenAI-compatible base URL",value=str(get_setting("lm_url","")),placeholder="http://localhost:11434/v1")
    lm_model=st.text_input("Model (blank = first available)",value=str(get_setting("lm_model","")),placeholder="glm-5.3:cloud")
    lm_timeout=st.number_input("LLM response timeout (seconds)",min_value=30,max_value=1800,value=int(get_setting("lm_timeout",300)),step=30)
    auto_verify=st.checkbox("Auto-check new P0/P1 claims against primary sources",value=bool(get_setting("auto_verify",True)))
    auto_verify_limit=st.number_input("Max automatic claim checks per refresh",min_value=0,max_value=5,value=int(get_setting("auto_verify_limit",2)),step=1)
    if st.button("Save settings",width="stretch"):
        set_setting("portfolio_value",portfolio_value); set_setting("lm_url",lm_url); set_setting("lm_model",lm_model); set_setting("lm_timeout",int(lm_timeout)); set_setting("auto_verify",bool(auto_verify)); set_setting("auto_verify_limit",int(auto_verify_limit))
        st.success("Settings saved")

with st.spinner("Collecting markets, FRED/repo, Treasury auctions/fiscal flows, CFTC, TIC, COFER, stablecoins and news..."):
    bundle=load_live_data()

snapshot=bundle["snapshot"]
news_df=bundle.get("news",pd.DataFrame())
news_class=classify_news(news_df)
# V2.7: every complete discovered claim is persisted automatically. Primary-source/LLM checks
# can run automatically for a bounded number of new P0/P1 claims, but never become VERIFIED
# scoring evidence without explicit human promotion.
verification_queue_now=build_verification_queue(news_df,30)
if not verification_queue_now.empty:
    upsert_verification_queue(verification_queue_now.to_dict(orient="records"))
if auto_verify and lm_url and int(auto_verify_limit)>0:
    pending=[q for q in recent_verification_queue(100) if q.get("priority") in {"P0","P1"} and q.get("status") in {"QUEUED","NO_CANDIDATE","ERROR"}]
    for q in pending[:int(auto_verify_limit)]:
        try:
            cand=discover_primary_evidence(q.get("bucket",""),q.get("claim",""),max_candidates=5)
            good=next((c for c in cand if c.get("reachable") and c.get("relevance_status")=="RELEVANT"),None)
            if not good:
                best=next((c for c in cand if c.get("reachable")),None)
                if best:
                    update_verification_queue_check(q["id"],candidate_url=best.get("final_url",best.get("url","")),candidate_tier=best.get("source_tier",""),candidate_relevance=float(best.get("relevance_score") or 0),relevance_status=best.get("relevance_status","IRRELEVANT_SOURCE"),verdict="",explanation="Candidate rejected before LLM verification because it is not semantically relevant to the claim.",status="IRRELEVANT_SOURCE")
                else:
                    update_verification_queue_check(q["id"],status="NO_CANDIDATE")
                continue
            fetched=fetch_source_text(good.get("final_url") or good.get("url"),max_chars=30000)
            if not fetched.get("ok"):
                update_verification_queue_check(q["id"],candidate_url=good.get("url",""),candidate_tier=good.get("source_tier",""),candidate_relevance=float(good.get("relevance_score") or 0),relevance_status=good.get("relevance_status",""),status="ERROR"); continue
            result=verify_claim_against_source(q.get("claim",""),fetched.get("text",""),fetched.get("final_url",good.get("url","")),base_url=lm_url,model=lm_model or None,timeout_seconds=int(lm_timeout))
            verdict=(result.splitlines()[0].strip().upper() if result else "INCONCLUSIVE")
            update_verification_queue_check(q["id"],candidate_url=fetched.get("final_url",good.get("url","")),candidate_tier=fetched.get("source_tier",""),candidate_relevance=float(good.get("relevance_score") or 0),relevance_status=good.get("relevance_status",""),verdict=verdict,explanation=result,status="CHECKED")
            save_verification_check(q.get("claim",""),q.get("bucket",""),fetched.get("final_url",good.get("url","")),verdict,result,model=lm_model or "auto")
        except Exception as exc:
            update_verification_queue_check(q["id"],explanation=str(exc),status="ERROR")
overrides=get_overrides(DEFAULT_OVERRIDES)
scores=score(snapshot,news_class,overrides)
machine_triggers=evaluate_triggers(snapshot,scores)

baseline=get_setting("baseline_allocation",DEFAULT_SETTINGS["baseline_allocation"])
portfolio_df,portfolio_meta=recommend(
    scores["regimes"],baseline,portfolio_value,min_trade_pct=min_trade,
    market_summary=snapshot.get("market_summary",{}),confidence=scores.get("confidence",100),
    max_turnover_pct=max_turnover,min_position_pct=min_position,min_trade_dollars=min_trade_dollars,
    score_details=scores, machine_triggers=machine_triggers,
)
history=recent_snapshots(150); prev=next((h for h in history if h.get("timestamp") != snapshot.get("timestamp")), None)
current_alerts=generate_alerts(scores,portfolio_df,prev,float(DEFAULT_SETTINGS.get("alert_threshold_points",8)),triggers=machine_triggers)
change_classification=classify_snapshot_change(prev,snapshot,scores)
auto_payload={**snapshot,"scores":scores,"news_scores":news_class.get("scores",{}),"overrides":overrides,"machine_triggers":machine_triggers,"portfolio":portfolio_df.to_dict(orient="records"),"portfolio_meta":portfolio_meta,"alerts":current_alerts,"change_classification":change_classification}
auto_rid,auto_saved=save_snapshot_if_new(auto_payload,snapshot.get("timestamp"),run_kind="AUTO_STREAMLIT")

# Status: six regime indices, then meta indicators.
reg_cols=st.columns(6)
for col,(name,val) in zip(reg_cols,scores["regimes"].items()):
    delta=None
    if prev:
        old=prev.get("scores",{}).get("regimes",{}).get(name)
        if old is not None: delta=val-float(old)
    col.metric(name,f"{val:.0f}/100",None if delta is None else f"{delta:+.1f}",help=f"{severity(val)} — risk index, not probability")
meta_cols=st.columns(4)
meta_cols[0].metric("Early warning",f"{scores['early_warning_index']:.0f}/100")
meta_cols[1].metric("Market confirmation",f"{scores['confirmation_index']:.0f}/100")
meta_cols[2].metric("Data-quality confidence",f"{scores['confidence']:.0f}/100")
meta_cols[3].metric("Phase",scores["phase"])
st.info("**Interpretation:** regime values are absolute 0–100 risk indices. Evidence coverage is separate: a low risk score with low coverage means uncertainty, not proof of safety.")
cov_details=scores.get("regime_evidence_coverage_details",{})
coverage_df=pd.DataFrame([{"Regime":k,"Effective coverage %":v.get("effective"),"Critical coverage %":v.get("critical"),"Generic coverage %":v.get("generic")} for k,v in cov_details.items()])
if coverage_df.empty:
    coverage_df=pd.DataFrame({"Regime":list(scores.get("regime_evidence_coverage",{})),"Effective coverage %":list(scores.get("regime_evidence_coverage",{}).values())})
if not coverage_df.empty: st.dataframe(coverage_df,width="stretch",hide_index=True)

(exec_tab,market_tab,flows_tab,policy_tab,portfolio_tab,analysis_tab,hist_tab,health_tab,roadmap_tab)=st.tabs([
    "Executive","Markets / Repo / Fiscal","Positioning & Foreign Flows","Policy / Evidence","Portfolio","Analysis / Triggers","Alerts & History","Data Health","V2.7 Roadmap"
])

with exec_tab:
    left,right=st.columns([1.2,1])
    with left:
        r=pd.DataFrame({"Regime":list(scores["regimes"]),"Risk index":list(scores["regimes"].values())})
        st.plotly_chart(px.bar(r,x="Regime",y="Risk index",range_y=[0,100],text="Risk index",title="Six independent risk indices"),width="stretch")
    with right:
        comp=pd.DataFrame({"Component":list(scores["components"]),"Score":list(scores["components"].values())})
        st.plotly_chart(px.bar(comp,y="Component",x="Score",orientation="h",range_x=[0,100],text="Score",title="Causal / transmission components"),width="stretch")
    st.subheader("Normalized dominant-regime mix — NOT probability")
    mix=pd.DataFrame({"Regime":list(scores["regime_mix_not_probability"]),"Mix %":list(scores["regime_mix_not_probability"].values())})
    st.dataframe(mix,width="stretch",hide_index=True)

    st.subheader("Run lineage / change classification")
    st.json(change_classification)
    st.subheader("What matters now")
    drivers=[]
    for regime,ds in scores["drivers"].items():
        for d in ds: drivers.append((regime,d))
    if drivers: st.dataframe(pd.DataFrame(drivers,columns=["Regime","Driver"]),width="stretch",hide_index=True)
    else: st.success("No high-threshold automated causal driver is active.")

    c=st.columns(6)
    c[0].metric("Auction stress raw",f"{snapshot.get('auction_stress_auto',0):.0f}")
    c[1].metric("CFTC USD-down raw",f"{snapshot.get('cftc_usd_downside_pressure',0):.0f}")
    c[2].metric("FX squeeze raw",f"{snapshot.get('fx_positioning_squeeze_risk',0):.0f}")
    c[3].metric("TIC pressure raw",f"{snapshot.get('tic_dedollarization_pressure',0):.0f}")
    c[4].metric("COFER pressure raw",f"{snapshot.get('cofer_dedollarization_pressure',0):.0f}")
    c[5].metric("Fiscal-flow stress raw",f"{snapshot.get('fiscal_flow_stress_auto',0):.0f}")

    st.subheader("Machine trigger state")
    st.dataframe(pd.DataFrame(machine_triggers),width="stretch",hide_index=True)

    if current_alerts:
        st.subheader("Actionable alerts")
        for a in current_alerts[:10]: st.warning(f"[{a['severity']}] {a['message']}")
    else: st.success("No alert threshold is currently crossed versus the prior saved snapshot.")

    if st.button("Save complete V2.7 snapshot + alerts",width="stretch"):
        payload={**snapshot,"scores":scores,"news_scores":news_class.get("scores",{}),"overrides":overrides,"machine_triggers":machine_triggers,"portfolio":portfolio_df.to_dict(orient="records"),"portfolio_meta":portfolio_meta,"alerts":current_alerts}
        rid=save_snapshot(payload,run_kind="MANUAL"); save_alerts(current_alerts); st.success(f"Saved V2.7 manual snapshot #{rid}")

with market_tab:
    st.subheader("Market prices")
    market_summary=bundle.get("market_summary",pd.DataFrame())
    if market_summary.empty: st.warning("Market-price feed unavailable.")
    else:
        show=market_summary.copy()
        for col in ["1d","5d","1m","3m","1y"]:
            if col in show.columns: show[col]=show[col]*100
        st.dataframe(show.round(2),width="stretch")
        choices=st.multiselect("Chart normalized market series",list(bundle["market_hist"].columns),default=[x for x in ["DXY","Gold","Long Treasuries ETF","Developed ex-US Equities"] if x in bundle["market_hist"].columns])
        if choices:
            x=bundle["market_hist"][choices].dropna(how="all").ffill(); x=100*x/x.apply(lambda s:s.dropna().iloc[0] if not s.dropna().empty else 1)
            st.plotly_chart(px.line(x,x=x.index,y=choices,title="Normalized market performance (start=100)"),width="stretch")

    st.subheader("Rates / inflation / repo plumbing")
    fred=bundle.get("fred_summary",pd.DataFrame())
    if fred.empty: st.warning("FRED feed unavailable.")
    else:
        plumbing_rows=[x for x in ["SOFR","IORB","SOFR-IORB spread","SOFR99-IORB spread","Tri-Party General Collateral Rate","TGCR-IORB spread","TGCR dispersion","Reserve balances (billions)","Treasury General Account (billions)","Central bank liquidity swaps (millions)","FIMA repo - foreign official (millions)"] if x in fred.index]
        if plumbing_rows:
            st.write("**Repo / liquidity internals**")
            st.dataframe(fred.loc[plumbing_rows].round(3),width="stretch")
        fed_asset_rows=[x for x in ["Fed balance sheet (millions)","Fed Treasury holdings (millions)","Fed Treasury bills (millions)","Fed Treasury nominal notes/bonds (millions)","Fed Treasury TIPS principal (millions)","Fed MBS holdings (millions)","Fed liquidity-facility loans (millions)","Central bank liquidity swaps (millions)","Fed identified assets (millions)","Fed other assets residual (millions)"] if x in fred.index]
        if fed_asset_rows:
            st.write("**Fed H.4.1 asset decomposition**")
            st.dataframe(fred.loc[fed_asset_rows].round(1),width="stretch")
            st.caption("The residual is deliberate: it prevents unexplained WALCL changes from being mislabeled as QE. Treasury, MBS, lending and swap changes are shown separately.")
        fed_class=bundle.get("fed_treasury_classification",{})
        if fed_class:
            st.write("**Fed Treasury-holdings classification**")
            st.info(f"{fed_class.get('classification','UNKNOWN')} — {fed_class.get('interpretation','')} (data-classification confidence {fed_class.get('confidence',0):.0f}%)")
            st.json(fed_class)
        st.write("**Rates / inflation / term premium**")
        rate_rows=[x for x in ["2Y Treasury","10Y Treasury","30Y Treasury","5Y TIPS real yield","10Y TIPS real yield","10Y breakeven inflation","5Y5Y forward inflation","10Y term premium","Financial Conditions Index"] if x in fred.index]
        if rate_rows: st.dataframe(fred.loc[rate_rows].round(3),width="stretch")

    st.subheader("Treasury auction absorption & catalysts")
    st.metric("Automatic auction stress",f"{bundle.get('auction_stress',0):.0f}/100")
    upcoming=bundle.get("upcoming_auctions",pd.DataFrame())
    if upcoming is not None and not upcoming.empty:
        st.write("**Upcoming announced coupon auctions**")
        st.dataframe(upcoming,width="stretch",hide_index=True)
    if not bundle.get("auction_summary",pd.DataFrame()).empty:
        st.write("**Latest same-tenor absorption results**")
        st.dataframe(bundle["auction_summary"].round(2),width="stretch",hide_index=True)
        st.caption("Bid-to-cover and bidder mix are measured against prior same-tenor completed auctions only. Upcoming issue/settlement dates never enter results freshness.")
    st.subheader("Treasury buyback monitoring")
    bm=bundle.get("buyback_meta",{})
    if bm:
        bc=st.columns(7)
        bc[0].metric("Upcoming ops",bm.get("scheduled_operations",0))
        bc[1].metric("Completed results",bm.get("completed_operations",0))
        bc[2].metric("Long-end upcoming",bm.get("long_end_operations",0))
        bc[3].metric("Long-end max",fmt_money(bm.get("long_end_max_amount",0)))
        bc[4].metric("Offer / accept",("—" if bm.get("completed_offer_accept_ratio") is None else f"{bm.get('completed_offer_accept_ratio'):.2f}x"))
        bc[5].metric("Result completeness",("—" if bm.get("result_completeness_pct") is None else f"{bm.get('result_completeness_pct'):.0f}%"))
        bc[6].metric("Policy intensity",("UNKNOWN" if bm.get("intensity") is None else f"{bm.get('intensity'):.0f}/100"))
        st.caption("TreasuryDirect schedule and completed result XMLs are separate. Announced capacity, submitted offers and accepted amounts are shown distinctly. This is debt-management/liquidity-support evidence, not QE or automatic auction-rescue evidence.")
        if not bm.get("results_conclusions_allowed",False): st.warning(f"Buyback result set is {bm.get('result_classification','UNKNOWN')}; execution conclusions are gated. Missing operations are unknown, not zero. Max-amount parse: {bm.get('max_amount_parse_status','UNKNOWN')}.")
        if not bundle.get("buybacks",pd.DataFrame()).empty: st.dataframe(bundle["buybacks"],width="stretch",hide_index=True)
    else: st.warning("Treasury buyback monitoring unavailable; treat as missing policy evidence.")

    st.subheader("Treasury fiscal pipeline")
    fm=bundle.get("fiscal_meta",{})
    if not fm: st.warning("Monthly Treasury Statement fiscal-flow feed unavailable.")
    else:
        fc=st.columns(4)
        fc[0].metric("FYTD receipts",fmt_money((fm.get("fytd_receipts_mn") or 0)*1e6))
        fc[1].metric("FYTD outlays",fmt_money((fm.get("fytd_outlays_mn") or 0)*1e6))
        fc[2].metric("FYTD deficit",fmt_money((fm.get("fytd_deficit_mn") or 0)*1e6))
        fc[3].metric("Fiscal-flow stress",f"{fm.get('stress_score',0):.0f}/100")
        st.json(fm)

with flows_tab:
    st.subheader("CFTC FX positioning")
    cc=st.columns(2)
    cc[0].metric("Fundamental USD-downside positioning",f"{bundle.get('cftc_pressure',0):.0f}/100")
    cc[1].metric("Crowded foreign-FX short squeeze risk",f"{bundle.get('fx_positioning_squeeze',0):.0f}/100")
    if bundle.get("fx_positioning_squeeze_reasons"): st.write("**Squeeze drivers:** "+"; ".join(bundle["fx_positioning_squeeze_reasons"]))
    if bundle.get("cftc_summary",pd.DataFrame()).empty: st.warning("CFTC feed unavailable.")
    else: st.dataframe(bundle["cftc_summary"].round(2),width="stretch",hide_index=True)

    st.subheader("TIC major foreign Treasury holders")
    st.caption("TIC is confidence-weighted for freshness BEFORE entering the regime score.")
    st.metric("Raw TIC de-dollarization pressure",f"{bundle.get('tic_pressure',0):.0f}/100")
    if bundle.get("tic_summary",pd.DataFrame()).empty: st.warning("TIC feed unavailable.")
    else:
        st.dataframe(bundle["tic_summary"].round(2),width="stretch",hide_index=True)
        if bundle.get("tic_meta",{}).get("reasons"): st.write("**TIC drivers:** "+"; ".join(bundle["tic_meta"]["reasons"]))

    st.subheader("IMF COFER reserve composition")
    cm=bundle.get("cofer_meta",{})
    if not cm: st.warning("COFER API unavailable; this source is omitted rather than estimated.")
    else:
        co=st.columns(3)
        co[0].metric("USD reserve share",f"{cm.get('usd_share_pct',0):.2f}%")
        cchg=cm.get("approx_1y_change_pp")
        co[1].metric("~1y change", "—" if cchg is None else f"{cchg:+.2f} pp")
        co[2].metric("COFER pressure",f"{bundle.get('cofer_pressure',0):.0f}/100")
        if not bundle.get("cofer",pd.DataFrame()).empty: st.dataframe(bundle["cofer"].tail(12),width="stretch",hide_index=True)

    st.subheader("Digital dollars: transactional stablecoins vs tokenized Treasury/RWA")
    sm=bundle.get("stable_meta",{})
    sc=st.columns(5)
    sc[0].metric("Transactional stablecoins",fmt_money(sm.get("transactional_stablecoin_supply")))
    sc[1].metric("Tokenized Treasury/RWA",fmt_money(sm.get("tokenized_rwa_supply")))
    r90=sm.get("90d_growth"); sc[2].metric("Broad digital-USD ~90d","—" if r90 is None or pd.isna(r90) else f"{r90*100:+.1f}%")
    sc[3].metric("USD1 supply",fmt_money(sm.get("usd1_supply")))
    sc[4].metric("Max >$1B stablecoin peg deviation",f"{sm.get('max_large_stablecoin_deviation_pct',0):.2f}%")
    st.caption(sm.get("growth_universe_note","Transactional $1 stablecoins are peg-tested separately from yield-bearing/tokenized Treasury products."))
    if not bundle.get("stable_focus",pd.DataFrame()).empty:
        st.write("**Transactional / $1-intended stablecoins**")
        st.dataframe(bundle["stable_focus"].round(4),width="stretch",hide_index=True)
    if not bundle.get("stable_rwa",pd.DataFrame()).empty:
        st.write("**Tokenized Treasury / RWA dollar products — NAV above $1 is not automatically a depeg**")
        st.dataframe(bundle["stable_rwa"].round(4),width="stretch",hide_index=True)
    if sm.get("large_depeg_symbols"): st.error("Actual >1% large transactional-stablecoin depeg: "+", ".join(sm["large_depeg_symbols"]))

with policy_tab:
    st.subheader("Verified analyst evidence inputs")
    st.warning("V2.7 rule: an analyst slider changes hard regime math only when its verification status is VERIFIED and it has a classified source URL. Unverified inputs remain visible but effective value = 0.")
    labels={
        "broad_fx_intervention":"Broad U.S./coordinated FX intervention","fed_independence_pressure":"Pressure on Fed independence / rate path",
        "treasury_auction_stress":"Additional Treasury absorption stress","foreign_official_selling":"Additional foreign official reserve selling",
        "brics_payment_progress":"Concrete BRICS/non-dollar payment infrastructure progress","central_bank_gold_rotation":"Central-bank rotation into gold",
        "stablecoin_dollar_support":"Additional stablecoin-driven dollar/T-bill support","commodity_dedollarization":"Material non-dollar commodity invoicing/settlement",
        "geopolitical_cyber_stress":"Geopolitical/cyber financial-system stress","institutional_credibility_stress":"U.S. institutional/fiscal credibility stress",
        "capital_control_or_holder_fee_risk":"Capital controls/foreign holder fee/coercive restructuring risk",
    }
    with st.form("overrides_form"):
        pending={}
        for key,label in labels.items():
            item=overrides.get(key,{"value":0,"note":"","source_url":"","verification_status":"UNVERIFIED"})
            with st.expander(label,expanded=bool(item.get("value",0))):
                v=st.slider("Risk intensity",0,100,int(item.get("value",0)),5,key=f"slider_{key}")
                note=st.text_input("Evidence note",value=item.get("note",""),key=f"note_{key}")
                url=st.text_input("Source URL",value=item.get("source_url",""),key=f"url_{key}")
                status=st.selectbox("Verification",["UNVERIFIED","VERIFIED","DISPUTED"],index=["UNVERIFIED","VERIFIED","DISPUTED"].index(item.get("verification_status","UNVERIFIED") if item.get("verification_status","UNVERIFIED") in ["UNVERIFIED","VERIFIED","DISPUTED"] else "UNVERIFIED"),key=f"verify_{key}")
                pending[key]=(v,note,url,status)
        if st.form_submit_button("Save analyst evidence",width="stretch"):
            for k,(v,note,url,status) in pending.items(): set_override(k,v,note,url,status)
            st.success("Evidence saved. Refresh/re-run to recalculate effective values.")

    st.subheader("Effective analyst evidence audit")
    oa=pd.DataFrame([{"key":k,**v} for k,v in scores.get("verified_override_audit",{}).items()])
    if not oa.empty: st.dataframe(oa,width="stretch",hide_index=True,column_config={"source_url":st.column_config.LinkColumn("source_url")})

    st.subheader("Source verification utility")
    verify_url=st.text_input("Check source URL reachability/tier",key="verify_source_url")
    if st.button("Check source",width="stretch"):
        st.json(check_source_url(verify_url))
        st.caption("Reachability and source tier do NOT verify the factual claim; they are provenance checks only.")

    st.write("**Claim verification assistant**")
    st.caption("Fetches the cited page and asks your configured local LLM whether that specific page supports the claim. It never changes VERIFIED status automatically.")
    claim_check=st.text_area("Claim to check",key="claim_check_text",placeholder="Example: The Netherlands repatriated 86 tonnes of gold from the U.S. to the Netherlands.")
    claim_url=st.text_input("Cited source URL",key="claim_check_url")
    if st.button("Check claim against cited source",width="stretch"):
        if not claim_check.strip() or not claim_url.strip(): st.error("Enter both a claim and its cited source URL.")
        elif not lm_url: st.error("Configure the local LLM base URL in the sidebar first.")
        else:
            with st.spinner("Fetching source and comparing claim to source text..."):
                fetched=fetch_source_text(claim_url)
                if not fetched.get("ok"):
                    st.error(f"Could not fetch source: {fetched.get('error','unknown error')}")
                else:
                    try:
                        verdict=verify_claim_against_source(claim_check,fetched.get("text",""),fetched.get("final_url",claim_url),base_url=lm_url,model=lm_model or None,timeout_seconds=int(lm_timeout))
                        st.markdown(verdict)
                        st.caption(f"Source tier: {fetched.get('source_tier')} | This is LLM-assisted verification, not an automatic factual certification. Mark VERIFIED only after reviewing the source yourself.")
                    except Exception as exc: st.error(f"Claim verification LLM failed: {exc}")

    st.subheader("Key policymakers / actors")
    st.dataframe(pd.DataFrame(ACTORS),width="stretch",hide_index=True)

    st.subheader("Evidence journal")
    with st.form("event_form",clear_on_submit=True):
        ec1,ec2=st.columns(2)
        category=ec1.selectbox("Category",["Policy","Fed","Treasury","Foreign actor","Market plumbing","Stablecoin","Institutional","Geopolitical","Other"])
        actor=ec2.text_input("Actor")
        title=st.text_input("Event / evidence")
        source_url=st.text_input("Source URL")
        verification=st.selectbox("Verification status",["UNVERIFIED","VERIFIED","DISPUTED"])
        impact=st.slider("Directional risk impact (-100 supportive to +100 crisis pressure)",-100,100,0,5)
        note=st.text_area("Notes")
        if st.form_submit_button("Add evidence event") and title.strip():
            if verification=="VERIFIED" and not source_url.strip(): st.error("VERIFIED evidence requires a source URL.")
            else:
                add_event(category,actor,title,source_url,impact,note,verification_status=verification,provenance="ANALYST-ENTERED")
                st.success(f"Evidence event added ({classify_source(source_url).get('source_tier')}).")
    events=recent_events(100)
    if events: st.dataframe(pd.DataFrame(events),width="stretch",hide_index=True,column_config={"source_url":st.column_config.LinkColumn("source_url")})

    st.subheader("Automatic verification queue")
    st.caption("Headlines are converted into claims-to-check, prioritized with a suggested primary-source family. They remain UNVERIFIED until you review a source and explicitly promote the evidence.")
    verification_queue=build_verification_queue(news_df,30)
    persisted_queue=pd.DataFrame(recent_verification_queue(100))
    if not persisted_queue.empty:
        st.write("**Persistent auto-populated research queue**")
        st.caption("Queue rows expose candidate relevance and LLM verdict separately. IRRELEVANT_SOURCE means an official URL was found but rejected before factual verification.")
        st.dataframe(persisted_queue,width="stretch",hide_index=True)
        reviewable=persisted_queue[persisted_queue["status"].isin(["CHECKED","IRRELEVANT_SOURCE"])] if "status" in persisted_queue.columns else pd.DataFrame()
        if not reviewable.empty:
            labels={int(r["id"]):f"#{int(r['id'])} {str(r.get('priority',''))} | {str(r.get('claim',''))[:95]}" for _,r in reviewable.iterrows()}
            qid=st.selectbox("Human review queue item",list(labels),format_func=lambda x:labels[x],key="verification_human_review")
            rr=reviewable[reviewable["id"].eq(qid)].iloc[0]
            st.caption(f"Relevance: {rr.get('relevance_status','?')} ({rr.get('candidate_relevance','?')}) | LLM verdict: {rr.get('llm_verdict','?')} | Approval: {rr.get('approved_status','UNVERIFIED')}")
            if rr.get("candidate_url"):
                st.link_button("Open candidate primary source",str(rr.get("candidate_url")),width="stretch")
            ca,cb,cc=st.columns(3)
            if ca.button("Approve check",key=f"approve_check_{qid}",width="stretch"):
                if rr.get("relevance_status")!="RELEVANT":
                    st.error("Cannot approve: candidate failed the semantic relevance gate.")
                elif str(rr.get("llm_verdict","")) not in {"SUPPORTED","CONTRADICTED"}:
                    st.error("Approve only a clear SUPPORTED or CONTRADICTED source check; INCONCLUSIVE remains research-only.")
                else:
                    update_verification_queue_approval(int(qid),"APPROVED"); st.success("Source check approved. It remains non-scoring until explicitly promoted into analyst evidence.")
            if cb.button("Reject check",key=f"reject_check_{qid}",width="stretch"):
                update_verification_queue_approval(int(qid),"REJECTED"); st.success("Check rejected.")
            if cc.button("Mark disputed",key=f"dispute_check_{qid}",width="stretch"):
                update_verification_queue_approval(int(qid),"DISPUTED"); st.success("Check marked disputed.")
    if verification_queue.empty:
        st.info("No headline claims are available for verification.")
    else:
        st.dataframe(verification_queue,width="stretch",hide_index=True,column_config={"link":st.column_config.LinkColumn("headline link")})
        selected_claim=st.selectbox("Load a queued claim into the verifier",verification_queue["claim"].tolist(),key="queued_claim_select")
        selected_row=verification_queue[verification_queue["claim"].eq(selected_claim)].iloc[0]
        st.caption(f"Preferred source family: {selected_row.get('preferred_verification_source','primary source')} | Headline source tier: {selected_row.get('source_tier','?')}")
        st.code(str(selected_row.get("claim","")),language=None)
        claim_bucket=str(selected_row.get("bucket","")); claim_text=str(selected_row.get("claim",""))
        discovery_key=f"primary_discovery::{claim_bucket}::{claim_text}"
        if st.button("Discover primary-source evidence",width="stretch"):
            with st.spinner("Searching known official source families and ranking same-domain evidence pages..."):
                st.session_state[discovery_key]=discover_primary_evidence(claim_bucket,claim_text,max_candidates=8)
        candidates=st.session_state.get(discovery_key,[])
        if candidates:
            show=pd.DataFrame(candidates)
            show_cols=[c for c in ["name","source_tier","relevance_status","relevance_score","claim_overlap_ratio","bucket_anchor_overlap","anchor","excerpt","final_url","reachable","error"] if c in show.columns]
            st.dataframe(show[show_cols],width="stretch",hide_index=True,column_config={"final_url":st.column_config.LinkColumn("primary source")})
            st.caption("Discovery is not verification. V2.7 rejects IRRELEVANT_SOURCE candidates before the LLM sees them; only semantically relevant official pages are eligible for claim checking.")
            if st.button("LLM-check top primary candidates",width="stretch"):
                if not lm_url:
                    st.error("Configure the local LLM base URL first.")
                else:
                    checked=0
                    relevant_candidates=[x for x in candidates if x.get("reachable") and x.get("relevance_status")=="RELEVANT"]
                    if not relevant_candidates:
                        st.warning("No candidate passed the V2.7 semantic relevance gate; no LLM claim check was run.")
                    for c in relevant_candidates[:3]:
                        fetched=fetch_source_text(c.get("final_url") or c.get("url"),max_chars=30000,timeout=12)
                        if not fetched.get("ok"): continue
                        try:
                            result=verify_claim_against_source(claim_text,fetched.get("text",""),fetched.get("final_url",c.get("url")),base_url=lm_url,model=lm_model or None,timeout_seconds=int(lm_timeout))
                            first=(result.splitlines()[0].strip().upper() if result else "INCONCLUSIVE")
                            verdict=first if first in {"SUPPORTED","CONTRADICTED","INCONCLUSIVE"} else "INCONCLUSIVE"
                            save_verification_check(claim_text,claim_bucket,fetched.get("final_url",c.get("url")),verdict,result,model=lm_model or "auto")
                            checked+=1
                        except Exception as exc:
                            st.warning(f"Verification failed for {c.get('url')}: {exc}")
                    st.success(f"Saved {checked} LLM-assisted primary-source checks. They remain non-scoring until you explicitly verify/promote evidence.")
        prior_checks=[x for x in recent_verification_checks(100) if x.get("claim")==claim_text]
        if prior_checks:
            st.write("**Persisted checks for this claim**")
            pc=pd.DataFrame(prior_checks)
            st.dataframe(pc[[c for c in ["created_at","verdict","source_tier","source_url","explanation","model"] if c in pc.columns]],width="stretch",hide_index=True,column_config={"source_url":st.column_config.LinkColumn("source")})

    st.subheader("Current headline monitor — triage only")
    if news_df.empty: st.warning("News feed unavailable.")
    else:
        buckets=st.multiselect("Filter news topics",sorted(news_df["bucket"].unique()),default=[])
        nd=news_df[news_df["bucket"].isin(buckets)] if buckets else news_df
        cols=[x for x in ["bucket","title","source","published","age_hours","link"] if x in nd.columns]
        st.dataframe(nd[cols],width="stretch",hide_index=True,column_config={"link":st.column_config.LinkColumn("link")})
        st.caption("A headline never becomes verified evidence automatically, regardless of source reputation.")

with portfolio_tab:
    st.subheader("Current allocation")
    current=pd.DataFrame({"Asset":ASSETS,"Current %":[float(baseline.get(a,0)) for a in ASSETS]})
    edited=st.data_editor(current,width="stretch",hide_index=True,disabled=["Asset"],num_rows="fixed")
    total=float(edited["Current %"].sum())
    if abs(total-100)>0.05: st.error(f"Allocation must total 100%. Current total: {total:.1f}%")
    elif st.button("Save current allocation",width="stretch"):
        set_setting("baseline_allocation",dict(zip(edited["Asset"],edited["Current %"].astype(float)))); st.success("Allocation saved. Refresh to make it baseline.")

    st.subheader("Hard recommendation engine")
    st.dataframe(portfolio_df,width="stretch",hide_index=True)
    st.caption(f"Overlay {portfolio_meta['overlay_strength']*100:.1f}% • confidence scaling {portfolio_meta['confidence_scale']*100:.0f}% • one-way turnover {portfolio_meta['one_way_turnover_pct']:.1f}% • actionable threshold {portfolio_meta['actionable_threshold_pct']:.1f}% / ${portfolio_meta['minimum_trade_dollars']:,.0f} • min new position {portfolio_meta['minimum_position_pct']:.1f}%.")
    for note in portfolio_meta.get("chase_notes",[]): st.info(note)
    trades=portfolio_df[portfolio_df["Action"]!="HOLD"]
    if trades.empty: st.success("HOLD — no trade clears the configured confidence, size, anti-chasing and turnover guardrails.")
    else:
        for _,r in trades.iterrows():
            st.write(f"**{r['Action']} {r['Asset']}: ${abs(r['Trade $']):,.0f} → {r['Recommended %']:.1f}%**")
            st.caption(f"Why: {r['Why']} Reversal: {r['Reversal trigger']}")

    st.subheader("Scenario stress test")
    base_alloc={a:float(baseline.get(a,0)) for a in ASSETS}; rec_alloc=dict(zip(portfolio_df["Asset"],portfolio_df["Recommended %"]))
    s1=scenario_stress_test(base_alloc,portfolio_value).rename(columns={"Illustrative portfolio return %":"Current return %","Illustrative P/L $":"Current P/L $"})
    s2=scenario_stress_test(rec_alloc,portfolio_value).rename(columns={"Illustrative portfolio return %":"Recommended return %","Illustrative P/L $":"Recommended P/L $"})
    stress=s1.merge(s2,on="Scenario"); stress["Improvement % pts"]=stress["Recommended return %"]-stress["Current return %"]
    st.dataframe(stress,width="stretch",hide_index=True)
    st.subheader("Scenario hedge alignment — replaces misleading '% defensive' labels")
    align=scenario_hedge_alignment(base_alloc,portfolio_value)
    if not align.empty: st.dataframe(align,width="stretch",hide_index=True)

with analysis_tab:
    st.subheader("Deterministic analysis")
    st.markdown(deterministic_analysis(scores,portfolio_df,news_class,prev))

    st.subheader("Confidence weighting BEFORE regime math")
    cad=pd.DataFrame([{"Indicator":k,**v} for k,v in scores.get("confidence_adjustments",{}).items()])
    if not cad.empty: st.dataframe(cad,width="stretch",hide_index=True)

    st.subheader("Persistent machine reversal / confirmation triggers")
    td=pd.DataFrame(machine_triggers)
    st.dataframe(td,width="stretch",hide_index=True)
    triggered=td[td["status"]=="TRIGGERED"] if not td.empty else pd.DataFrame()
    aging=td[td["status"].isin(["AGING","PENDING_REPLACEMENT","EXPIRED"])] if not td.empty else pd.DataFrame()
    if triggered.empty: st.info("No fresh machine pre-commitment is currently triggered.")
    else:
        for _,t in triggered.iterrows(): st.warning(f"{t['side']} — {t['condition']} → {t['action']}")
    if not aging.empty:
        st.caption("Event-based evidence with reduced/expired weight:")
        for _,t in aging.iterrows(): st.write(f"{t['id']}: **{t['status']}** — {t.get('condition','')}")

    st.subheader("Local LLM red-team")
    st.caption("The model is told that regime scores are not probabilities, stale data are already discounted, and unverified claims cannot support trades.")
    if st.button("Run local LLM analysis",width="stretch"):
        if not lm_url: st.error("Configure the local LLM base URL first.")
        else:
            events=recent_events(30)
            verified_events=[e for e in events if e.get("verification_status")=="VERIFIED"]
            unverified_events=[e for e in events if e.get("verification_status")!="VERIFIED"]
            payload={
                "scores":scores,"machine_triggers":machine_triggers,
                "portfolio_recommendation":portfolio_df.to_dict(orient="records"),"portfolio_meta":portfolio_meta,
                "snapshot":snapshot,
                "previous_run":compact_previous_context(prev,snapshot,scores),
                "verified_analyst_evidence":[{k:v for k,v in e.items()} for e in verified_events],
                "unverified_evidence_discovery_only":unverified_events,
                "verification_queue_discovery_only":build_verification_queue(news_df,30).to_dict(orient="records") if not news_df.empty else [],
                "persisted_primary_source_checks":recent_verification_checks(50),
                "headline_scores_discovery_only":news_class.get("scores",{}),
                "headlines_discovery_only":news_df.head(50).to_dict(orient="records") if not news_df.empty else [],
            }
            try:
                text=analyze_with_local_llm(payload,base_url=lm_url,model=lm_model or None,timeout_seconds=int(lm_timeout)); st.markdown(text)
            except Exception as exc: st.error(f"Local LLM call failed: {exc}")

with hist_tab:
    st.subheader("Current alerts")
    if current_alerts: st.dataframe(pd.DataFrame(current_alerts),width="stretch",hide_index=True)
    else: st.success("No current alerts.")
    old_alerts=recent_alerts(100)
    if old_alerts:
        st.subheader("Saved alert history"); st.dataframe(pd.DataFrame(old_alerts),width="stretch",hide_index=True)
    st.subheader("Snapshot history")
    if not history: st.info("No saved snapshots yet.")
    else:
        rows=[]
        for h in reversed(history):
            row={"captured_at":h.get("_captured_at",h.get("timestamp")),"phase":h.get("scores",{}).get("phase"),"early_warning":h.get("scores",{}).get("early_warning_index"),"confirmation":h.get("scores",{}).get("confirmation_index"),"confidence":h.get("scores",{}).get("confidence")}
            row.update(h.get("scores",{}).get("regimes",{})); rows.append(row)
        hdf=pd.DataFrame(rows); hdf["captured_at"]=pd.to_datetime(hdf["captured_at"],errors="coerce")
        st.dataframe(hdf,width="stretch",hide_index=True)
        cols=[c for c in scores["regimes"] if c in hdf.columns]
        if cols: st.plotly_chart(px.line(hdf,x="captured_at",y=cols,markers=True,range_y=[0,100],title="Risk-index history"),width="stretch")

with health_tab:
    st.subheader("Source health / freshness")
    health=bundle.get("health",pd.DataFrame())
    if health.empty: st.warning("No source-health data available.")
    else: st.dataframe(health.round(2),width="stretch",hide_index=True)
    st.subheader("Raw → confidence → effective input")
    if not cad.empty: st.dataframe(cad,width="stretch",hide_index=True)
    fcd=scores.get("regime_evidence_coverage_details",{}).get("Dollar funding squeeze",{})
    if fcd:
        st.subheader("Dollar-funding observation coverage")
        fc1,fc2,fc3=st.columns(3)
        fc1.metric("Domestic funding coverage",f"{fcd.get('domestic_funding_coverage',0):.0f}%")
        fc2.metric("Offshore funding coverage",f"{fcd.get('offshore_funding_coverage',0):.0f}%")
        fc3.metric("Effective regime coverage",f"{fcd.get('effective',0):.0f}%")
        if fcd.get('offshore_gap'): st.warning(fcd.get('offshore_gap'))
    st.markdown("""
### V2.7 evidence rules
- **Data confidence is not thesis confidence.** It measures source availability/freshness.
- **Stale data are discounted before scoring.** TIC/COFER/CFTC no longer contribute their full raw score when stale.
- **Regime scores are not probabilities.** A 41/100 fiscal score means elevated fiscal-duration risk, not a 41% chance of crisis.
- **Headlines are triage.** They may guide research but cannot become verified evidence automatically.
- **Verified analyst evidence needs provenance.** A source being reachable does not prove the claim; verification is an explicit separate state.
- **Token trades are suppressed.** New positions below the minimum size and trades below the dollar/% threshold are not actionable.
- **Future-dated observations are hygiene warnings.** They are not treated as extra-fresh data and are confidence-discounted.
- **RWA tokens are not stablecoins.** Yield-accumulating tokenized Treasury products are separated before $1 peg tests.
- **Repo tail ≠ median funding stress.** SOFR99-IORB has its own percentile/persistence trigger and is never described as distance to the median SOFR-IORB threshold.
- **Domestic funding coverage ≠ global funding coverage.** Missing cross-currency-basis/FX-swap data explicitly lowers Dollar Funding Squeeze coverage.
- **Unknown ≠ absent.** When critical regime coverage is below 50%, narrative output must use unverified/unknown/insufficient-evidence language rather than asserting the factor is absent.
""")

with roadmap_tab:
    todo=ROOT/"TODO_V2.md"
    if todo.exists(): st.markdown(todo.read_text(encoding="utf-8"))
    else: st.info("Roadmap file missing.")
