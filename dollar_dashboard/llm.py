from __future__ import annotations

import json
import os
import requests



def compact_previous_context(prev: dict | None, current_snapshot: dict, current_scores: dict) -> dict:
    """Compact prior-run context so a red-team model can make true run-to-run comparisons."""
    if not prev:
        return {}
    previous_scores = prev.get("scores", {}) or {}
    regime_delta = {}
    for name, value in current_scores.get("regimes", {}).items():
        old = previous_scores.get("regimes", {}).get(name)
        if old is not None:
            regime_delta[name] = round(float(value) - float(old), 2)
    return {
        "captured_at": prev.get("_captured_at", prev.get("timestamp")),
        "run_id": prev.get("_run_id", prev.get("_id")),
        "app_version": prev.get("_app_version", prev.get("run_meta",{}).get("app_version")),
        "schema_version": prev.get("_schema_version", prev.get("run_meta",{}).get("schema_version")),
        "scores": previous_scores,
        "machine_triggers": prev.get("machine_triggers", []),
        "portfolio": prev.get("portfolio", []),
        "market_summary": prev.get("market_summary", {}),
        "fred_summary": prev.get("fred_summary", {}),
        "auction_summary": prev.get("auction_summary", []),
        "cftc_summary": prev.get("cftc_summary", []),
        "tic_summary": prev.get("tic_summary", []),
        "regime_delta_to_current": regime_delta,
        "current_timestamp": current_snapshot.get("timestamp"),
        "current_regime_evidence_coverage": current_scores.get("regime_evidence_coverage",{}),
        "current_regime_evidence_coverage_details": current_scores.get("regime_evidence_coverage_details",{}),
        "treasury_buyback_meta": current_snapshot.get("treasury_buyback_meta",{}),
        "fed_treasury_classification": current_snapshot.get("fed_treasury_classification",{}),
        "treasury_financing_meta": current_snapshot.get("treasury_financing_meta",{}),
    }



def _compact_analysis_payload(payload: dict, max_chars: int = 60000) -> str:
    """Serialize the red-team payload without ever cutting JSON in the middle of a record."""
    import copy
    data=copy.deepcopy(payload)
    caps={
        "verified_analyst_evidence":20,
        "unverified_evidence_discovery_only":15,
        "verification_queue_discovery_only":15,
        "headlines_discovery_only":20,
        "persisted_primary_source_checks":20,
    }
    for k,n in caps.items():
        if isinstance(data.get(k),list): data[k]=data[k][:n]
    snap=data.get("snapshot")
    if isinstance(snap,dict):
        for k,n in {"auction_summary":10,"upcoming_auctions":12,"cftc_summary":8,"tic_summary":12,"stablecoin_summary":12,"treasury_buybacks":16,"data_health":20}.items():
            if isinstance(snap.get(k),list): snap[k]=snap[k][:n]
    raw=json.dumps(data,default=str)
    if len(raw)<=max_chars: return raw
    # Remove low-priority discovery material in whole-record units; never slice serialized JSON.
    for k in ["headlines_discovery_only","unverified_evidence_discovery_only","verification_queue_discovery_only"]:
        if k in data:
            data[k]=[]
            raw=json.dumps(data,default=str)
            if len(raw)<=max_chars: return raw
    # Final structured compaction: preserve causal summaries, current scores, triggers and portfolio.
    if isinstance(data.get("snapshot"),dict):
        keep={"timestamp","market_summary","fred_summary","auction_stress_auto","auction_summary","upcoming_auctions","cftc_usd_downside_pressure","cftc_summary","fx_positioning_squeeze_risk","tic_dedollarization_pressure","tic_meta","tic_transaction_meta","cofer_dedollarization_pressure","cofer_meta","fiscal_flow_stress_auto","fiscal_meta","stablecoin_dollar_support_auto","stablecoin_meta","treasury_buyback_meta","fed_treasury_classification","treasury_financing_meta","offshore_usd_funding_meta","official_policy_meta","data_confidence","component_confidence"}
        data["snapshot"]={k:v for k,v in data["snapshot"].items() if k in keep}
    raw=json.dumps(data,default=str)
    return raw

def analyze_with_local_llm(
    payload: dict,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    timeout_seconds: int | None = None,
) -> str:
    # Supports Ollama, LM Studio, and other OpenAI-compatible local endpoints.
    base_url = (
        base_url
        or os.getenv("LOCAL_LLM_BASE_URL", "")
        or os.getenv("OLLAMA_BASE_URL", "")
        or os.getenv("LMSTUDIO_BASE_URL", "")
    ).rstrip("/")
    model = (
        model
        or os.getenv("LOCAL_LLM_MODEL", "")
        or os.getenv("OLLAMA_MODEL", "")
        or os.getenv("LMSTUDIO_MODEL", "")
    )
    api_key = api_key or os.getenv("LOCAL_LLM_API_KEY", "") or os.getenv("LMSTUDIO_API_KEY", "ollama")
    timeout_seconds = max(30, int(timeout_seconds if timeout_seconds is not None else os.getenv("LOCAL_LLM_TIMEOUT", "300")))
    if not base_url:
        raise ValueError("Local LLM base URL is not configured")
    if not model:
        # Query OpenAI-compatible model list when possible.
        r = requests.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=(5, 20))
        r.raise_for_status()
        models = r.json().get("data", [])
        if not models:
            raise ValueError("No model specified and no models returned by /models")
        model = models[0]["id"]

    system = """You are the red-team macro analyst for dollar_watch V3.4.8.
Do not assume a dollar-collapse thesis is correct. Distinguish six regimes:
(1) managed dollar devaluation, (2) fiscal/Treasury supply stress,
(3) inflation/monetary debasement, (4) dollar funding squeeze,
(5) reserve-confidence crisis, and (6) FX positioning squeeze.

Evidence rules are strict:
- DATA-DERIVED values may be analyzed as supplied.
- VERIFIED analyst/news evidence may affect conclusions.
- HEADLINE TRIAGE and UNVERIFIED claims are discovery leads only; do not use them as factual support for a trade.
- Never convert a reachable URL or source reputation into verification of the claim itself.
- IRRELEVANT_SOURCE candidates failed the deterministic semantic relevance gate and may not be used as factual support or passed off as inconclusive verification.
- If you introduce a factual claim not present in the supplied verified evidence, label it UNVERIFIED and exclude it from the recommendation.
- Explicitly discount stale components using confidence_adjustments.
- Regime scores are 0-100 risk indices, NOT probabilities. regime_mix_not_probability is descriptive only.
- regime_evidence_coverage is separate from risk: low risk + low coverage means uncertainty, not safety. Critical coverage is more important than generic coverage; missing verified policy evidence cannot be replaced by abundant spot-market data.
- LANGUAGE GATE: when a regime's critical coverage is below 50%, never say the relevant factor is absent, nonexistent, or disproven. Say "no verified evidence is currently ingested", "unknown", or "insufficient evidence".
- With critical coverage below 50%, do not write categorical counterfactuals such as "a genuine crisis would not coexist with these readings." Say the observed high-confidence indicators argue against CURRENT CONFIRMATION while explicitly retaining the measured blind spot.
- Treasury buybacks are debt-management/liquidity-support evidence, not by themselves proof of weak demand or QE. Distinguish announced capacity, offers submitted, and amounts accepted. If buyback result completeness is <80% or max-amount parsing failed, do not conclude there were no long-end operations, low uptake, or low intensity.
- BUYBACK ARITHMETIC RULE: treasury_buyback_meta supplies deterministic aggregate ratios. For long-end completed operations, use long_end_offer_accept_ratio for offered/accepted and long_end_offer_to_capacity_ratio for offered/parsed-capacity. Never recompute an aggregate multiple from operation counts, a different scope, or another buyback field. If the relevant deterministic ratio is null, state the raw offered/accepted/capacity amounts without inventing a multiple.
- Do not call changes in foreign Treasury holdings "demand". Use TIC net transactions for active purchases/sales; distinguish valuation and residual/custody effects using tic_transaction_meta.
- TIC SECTOR-INTEGRITY RULE: tic_transaction_meta.grand_total and tic_transaction_meta.foreign_official are separate, self-contained decompositions. NEVER combine a holdings change, transaction amount, valuation amount, residual, or percentage from one sector with a value from the other sector. For a transaction-share statement, use that same sector's supplied transaction_share_of_position_change_pct; do not recompute it from fields in different nested objects. If reconciles is false, describe the decomposition as failed/unknown rather than repairing it yourself.
- Central-bank liquidity swaps and FIMA foreign-official repo are separate facilities. Never call SWPT "FIMA swaps".
- Use the supplied Fed Treasury-holdings classification. Bill accumulation with MBS runoff is not automatic QE or fiscal-rescue evidence.
- V3.4.8 Treasury financing has TWO layers. Z.1 holder flows answer who absorbed Treasury issuance; repo, hedge-fund structure and SLR capacity are funding/intermediation overlays. Never add the funding layer to holder flows or double-count the same Treasury.
- Hedge-fund Treasury holdings, repo assets, and domestic repo liabilities are structural proxies only. Domestic repo liabilities exclude non-domestic counterparties; repo can finance assets other than Treasuries; Treasury holdings are not all necessarily repo-financed. Never call the repo/Treasury ratio gross leverage or direct basis-trade exposure.
- The 2026:Q2 Z.1 schema adds a hedge-fund Treasury TRANSACTION holder row. Use hedge_fund_absorption_pct only when supplied. Never derive Treasury purchase flow from the hedge-fund Treasury market-value level.
- "Monetary-capable absorption" means Fed/central-bank plus broad banking/depository Treasury absorption. It is NOT automatically monetization. The financing classifier uses M2/deposit growth aligned to the SAME Z.1 quarter; newer current money growth is context only. Even when aligned, describe the relationship as a concurrent monetary backdrop, not causal proof of Treasury monetization.
- Dealer Treasury accumulation is inventory/intermediation exposure. It is not equivalent to final end-buyer demand, but it is also not proof of weak demand, failed placement, unsold securities, or involuntary warehousing. Say "dealer net absorption/acquisition" unless stronger evidence is supplied. Negative MMF/foreign/other holder flows are valid net selling and must not be clamped to zero. Z.1 MMF Treasury flows are not maturity-specific: never say "MMFs moved out of bills" unless a bill-specific series is supplied.
- The H.8 bank-security proxy includes agencies as well as Treasuries. It may confirm bank balance-sheet expansion but may not replace quarterly Treasury-only Z.1 flows.
- The April 1, 2026 eSLR recalibration reduces the enhanced leverage constraint but does NOT exclude Treasuries or Fed reserves from total leverage exposure. Do not describe it as a Treasury/reserve exemption.
- The broad "monetary-capable" bank bucket is NOT the eSLR-covered population. For eSLR transmission, use eslr_relevant_bank_proxy_absorption_pct / U.S.-chartered depository absorption only as a broad proxy, plus the H.8 proxy; even that is wider than the GSIB-only population. Never attribute foreign-bank-office or credit-union absorption to eSLR.
- Treasury-financing timeliness is release-aware. LATEST_EXPECTED_RELEASE means the quarter is the newest Z.1 observation reasonably expected to be published, even if the current calendar quarter is later. Do not call that source "two quarters stale" merely from calendar distance. Still call the reading historical and never present it as the current quarter's financing mix. ONE_RELEASE_LATE/TWO_PLUS_RELEASES_LATE or classification.provisional=true means the source is genuinely behind expected publication.
- If treasury_financing_meta.slr_transmission_test.status is FULL_EFFECT_NOT_YET_TESTABLE, do not claim the April 1, 2026 eSLR change caused observed Q1 bank/dealer Treasury absorption. Early adoption was permitted, but Q1 cannot isolate the full-effective-date effect.
- Event-based auction triggers age and expire. PENDING_REPLACEMENT, AGING, and EXPIRED are not equivalent to a fresh TRIGGERED signal.
- Do not describe a portfolio as a single percent defensive/hedged. Use scenario hedge alignment because the same asset can hedge devaluation and fail in a dollar-funding squeeze.
- If previous_run is supplied, use it for true run-to-run comparisons; do not infer "what changed" solely from 1w/1m/3m market fields.
- A 2Y Treasury yield above current SOFR is a carry/rate-path signal, NOT by itself proof that the market prices hikes; term/risk premia also matter.
- Tokenized Treasury/RWA products (for example accumulating-NAV structures) are not automatically $1-pegged stablecoins. Use the supplied asset classification.
- A FAILED source means missing evidence, not a benign zero reading.
- Median SOFR-IORB and SOFR99-IORB are different signals. Never describe SOFR99-IORB as distance to the median SOFR trigger. Use repo_tail_signal for upper-tail stress and repo_or_swap_stress for median/facility stress.
- Domestic repo/Fed-facility coverage is not full global-dollar-funding coverage. V3.4.8 may supply a front-futures/spot dislocation proxy; this is NOT cross-currency basis. Explicitly mention the remaining cross-currency-basis/FX-swap gap when Dollar Funding Squeeze coverage is discussed.
- Funding-stress trigger semantics are stateful. repo_stress_normalized can only KILL a funding overlay after repo_or_swap_stress was previously active and recovery persistence is satisfied. Never recommend reducing liquidity simply because SOFR-IORB is currently below the entry threshold.
- A large central-bank USD swap-line draw or FIMA draw is evidence FOR dollar-funding stress. It supports more T-bills/liquidity and less high-beta/non-USD risk; it is NEVER a reason to add non-USD exposure.
- In a dollar-funding squeeze, USD denomination alone is not a hedge. Treat T-bills as the clean direct hedge; TIPS and U.S. equities remain rate/market-sensitive; gold and CHF are conditional; BTC and unhedged ex-US equities are vulnerable.
- Policy evidence has two tiers. deterministic_verified_evidence contains exact official facts that passed domain-specific anchor validation; these may automatically raise evidence coverage and have only tightly bounded mechanical score effects, but NEVER establish motive. approved_policy_evidence contains human-approved, source-relevant, SUPPORTED interpretations and may receive the full bounded intent/motive-sensitive effect. Do not describe deterministic facts as "human approved" and do not require human approval merely to state an agency's exact reported fact.
- V3.4.8 official_policy_meta contains deterministic primary-source facts. Japan MOF monthly intervention totals are direct observations of occurrence/amount only. Do not infer yen-buying direction from monthly totals; direction requires detailed currencies-bought/sold data. They also do not prove broad U.S. dollar intent. NY Fed U.S. FX-operation reports may establish whether the U.S. intervened directly in the reported quarter.
- MOF RESERVE-ASSET INFERENCE: even if later detailed MOF data confirms yen-buying intervention, that establishes use/sale of foreign-currency reserves or cash to obtain yen; it does NOT by itself prove U.S. Treasury sales, Treasury-collateral liquidation, or broad "USD asset disposal." Name a specific reserve asset/instrument only when the supplied official detail identifies it or an independently verified transaction source does.
- V3.4.8 intervention_history is a quarter-level actor/currency/purpose timeline. A targeted Treasury/ESF intervention (for example Argentina stabilization) is not broad-dollar policy; always state actor, currency, direction/purpose, and broad-USD implication.
- V3.4.8 may include nyfed_lagged_basis_validation: an official quarterly cross-check of offshore FX-swap funding conditions. It is useful validation context but is too stale to fire a live funding trigger or raise live offshore coverage.
- Canonical official pages may be served from a transparent LAST_KNOWN_CACHE after transient 503/403 errors. Treat a dated cached copy as valid historical evidence for that fixed statement, but disclose that live reachability failed and do not imply a fresher statement.
- Policy evidence has an action taxonomy. BROAD_USD_DEVALUATION strengthens non-USD/devaluation hedges; BILATERAL_FX_POLICY or BILATERAL_FX_INTERVENTION raises pair-specific FX-squeeze catalyst confidence but does not automatically trade; USD_FUNDING_STRESS favors T-bills/liquidity and trims BTC/unhedged ex-US; RESERVE_CONFIDENCE_STRESS favors gold/CHF and avoiding long nominal duration; FISCAL_DEBT_MANAGEMENT is not itself a trade signal. Never collapse all intervention/devaluation evidence into "add T-bills."
- A verified Japanese intervention or U.S.-Japan yen-policy statement is evidence about the USD/JPY catalyst complex, not automatic proof of deliberate broad-dollar devaluation.
- CFTC DATE SEMANTICS: latest_cftc_report_date/report_date and latest_position_asof_date are the Tuesday POSITION-AS-OF date, not publication dates. latest_expected_publication_date is normally that Friday (+3 days). next_position_asof_date is the following Tuesday (+7); next_expected_publication_date (and backward-compatible expected_publication_date) is normally the following Friday (+10). Holiday shifts are possible. Never call a Tuesday as-of date the public release date and do not invent null calendar fields when these supplied derived dates exist.
- TGA SEMANTICS: a rising Treasury General Account is a Treasury cash-balance rebuild and, while funds remain in the TGA, a drain on reserve/liquidity balances. Do NOT call a TGA rebuild "prefunding future supply" or proof of future issuance unless supplied official cash-management/issuance evidence explicitly establishes that purpose.
- FUNDING-SCOPE LANGUAGE: if funding_observation_scope.status == PARTIAL_OFFSHORE or offshore funding coverage is below 70%, do not label the GLOBAL dollar-funding environment simply "benign", "clean", or "no crisis". Say observed domestic indicators do not confirm stress / are calm, then explicitly retain the cross-currency-basis and OTC FX-swap blind spot. A lagged NY Fed quarterly basis characterization cannot close the live gap.
- FX INDEX ATTRIBUTION RULE: a large move in one FX cross does not establish that a broad-dollar index move is "concentrated" in, "driven by", or mostly caused by that currency. Make index-contribution claims only when supplied weights/contribution decomposition support them; otherwise describe the cross as a notable coincident move.
- PERCENTILE/VALUATION RULE: an extreme yield, real-yield, spread, price, or term-premium percentile describes the observed level relative to history; it is not by itself an entry signal, proof of cheap/expensive valuation, or reason to add/trim an asset. For TIPS, explicitly retain duration/real-yield risk when discussing high starting real yields.
- POSITION UNWIND LANGUAGE: observed_position_unwind is the only authority for saying CFTC positions actually unwound. Spot FX strengthening against crowded shorts may be described only as "consistent with short-covering" unless observed_position_unwind.status == CONFIRMED. PARTIAL means some report-over-report covering/liquidation evidence, not a confirmed broad unwind; UNCONFIRMED/STALE_UNCONFIRMED means do not say the shorts "are unwinding" as a factual statement.

Prioritize causal mechanisms, fiscal flows, policy actors, foreign actors, Treasury/repo plumbing,
positioning, structural dollar supports, and disconfirming evidence. Distinguish duration/supply stress
from inflation. Distinguish fundamental USD weakness from spot action consistent with short-covering in JPY/EUR/CHF, and separately state whether CFTC data confirms an observed position unwind.
Economic interests are not proof of motive. Do not fabricate facts beyond supplied data.
Give concrete portfolio implications, but respect the hard engine's minimum trade size and anti-chasing rules.
For each recommendation, state the machine/human evidence that would reverse it.
"""
    user = "Analyze this dashboard snapshot. Return sections: Evidence Quality, What Changed, Causal Interpretation, Red-Team Case, Missing Factors, Portfolio Actions, Reversal Triggers, Unverified Claims To Check.\n\n" + _compact_analysis_payload(payload)
    r = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":user}], "temperature":0.2},
        timeout=(10, timeout_seconds),
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def verify_claim_against_source(
    claim: str,
    source_text: str,
    source_url: str,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    timeout_seconds: int | None = None,
) -> str:
    """LLM-assisted source comparison. Never changes evidence verification status automatically."""
    base_url = (base_url or os.getenv("LOCAL_LLM_BASE_URL", "") or os.getenv("OLLAMA_BASE_URL", "") or os.getenv("LMSTUDIO_BASE_URL", "")).rstrip("/")
    model = model or os.getenv("LOCAL_LLM_MODEL", "") or os.getenv("OLLAMA_MODEL", "") or os.getenv("LMSTUDIO_MODEL", "")
    api_key = api_key or os.getenv("LOCAL_LLM_API_KEY", "") or os.getenv("LMSTUDIO_API_KEY", "ollama")
    timeout_seconds = max(30, int(timeout_seconds if timeout_seconds is not None else os.getenv("LOCAL_LLM_TIMEOUT", "300")))
    if not base_url: raise ValueError("Local LLM base URL is not configured")
    if not model:
        rr=requests.get(f"{base_url}/models",headers={"Authorization":f"Bearer {api_key}"},timeout=(5,20)); rr.raise_for_status()
        models=rr.json().get("data",[])
        if not models: raise ValueError("No model specified and no models returned by /models")
        model=models[0]["id"]
    system="""You are a strict claim-to-source verifier. Use ONLY the supplied source text. Return exactly one first-line verdict: SUPPORTED, CONTRADICTED, or INCONCLUSIVE. Then give 2-5 concise sentences explaining what the source actually says and what part of the claim is unsupported or contradicted. Do not use outside knowledge. A source being reputable does not make a claim true."""
    user=f"CLAIM:\n{claim}\n\nSOURCE URL:\n{source_url}\n\nSOURCE TEXT:\n{source_text[:30000]}"
    r=requests.post(f"{base_url}/chat/completions",headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},json={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"temperature":0.0},timeout=(10,timeout_seconds))
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
