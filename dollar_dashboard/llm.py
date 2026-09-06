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
        keep={"timestamp","market_summary","fred_summary","auction_stress_auto","auction_summary","upcoming_auctions","cftc_usd_downside_pressure","cftc_summary","fx_positioning_squeeze_risk","tic_dedollarization_pressure","tic_meta","tic_transaction_meta","cofer_dedollarization_pressure","cofer_meta","fiscal_flow_stress_auto","fiscal_meta","stablecoin_dollar_support_auto","stablecoin_meta","treasury_buyback_meta","fed_treasury_classification","offshore_usd_funding_meta","data_confidence","component_confidence"}
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

    system = """You are the red-team macro analyst for dollar_watch V2.8.
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
- Treasury buybacks are debt-management/liquidity-support evidence, not by themselves proof of weak demand or QE. Distinguish announced capacity, offers submitted, and amounts accepted. If buyback result completeness is <80% or max-amount parsing failed, do not conclude there were no long-end operations, low uptake, or low intensity.
- Do not call changes in foreign Treasury holdings "demand". Use TIC net transactions for active purchases/sales; distinguish valuation and residual/custody effects using tic_transaction_meta.
- Central-bank liquidity swaps and FIMA foreign-official repo are separate facilities. Never call SWPT "FIMA swaps".
- Use the supplied Fed Treasury-holdings classification. Bill accumulation with MBS runoff is not automatic QE or fiscal-rescue evidence.
- Event-based auction triggers age and expire. PENDING_REPLACEMENT, AGING, and EXPIRED are not equivalent to a fresh TRIGGERED signal.
- Do not describe a portfolio as a single percent defensive/hedged. Use scenario hedge alignment because the same asset can hedge devaluation and fail in a dollar-funding squeeze.
- If previous_run is supplied, use it for true run-to-run comparisons; do not infer "what changed" solely from 1w/1m/3m market fields.
- A 2Y Treasury yield above current SOFR is a carry/rate-path signal, NOT by itself proof that the market prices hikes; term/risk premia also matter.
- Tokenized Treasury/RWA products (for example accumulating-NAV structures) are not automatically $1-pegged stablecoins. Use the supplied asset classification.
- A FAILED source means missing evidence, not a benign zero reading.
- Median SOFR-IORB and SOFR99-IORB are different signals. Never describe SOFR99-IORB as distance to the median SOFR trigger. Use repo_tail_signal for upper-tail stress and repo_or_swap_stress for median/facility stress.
- Domestic repo/Fed-facility coverage is not full global-dollar-funding coverage. V2.8 may supply a front-futures/spot dislocation proxy; this is NOT cross-currency basis. Explicitly mention the remaining cross-currency-basis/FX-swap gap when Dollar Funding Squeeze coverage is discussed.

Prioritize causal mechanisms, fiscal flows, policy actors, foreign actors, Treasury/repo plumbing,
positioning, structural dollar supports, and disconfirming evidence. Distinguish duration/supply stress
from inflation. Distinguish fundamental USD weakness from short-covering in JPY/EUR/CHF.
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
