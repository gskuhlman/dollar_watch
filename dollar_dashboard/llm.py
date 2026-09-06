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
        "treasury_buyback_meta": current_snapshot.get("treasury_buyback_meta",{}),
    }

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

    system = """You are the red-team macro analyst for dollar_watch V2.3.
Do not assume a dollar-collapse thesis is correct. Distinguish six regimes:
(1) managed dollar devaluation, (2) fiscal/Treasury supply stress,
(3) inflation/monetary debasement, (4) dollar funding squeeze,
(5) reserve-confidence crisis, and (6) FX positioning squeeze.

Evidence rules are strict:
- DATA-DERIVED values may be analyzed as supplied.
- VERIFIED analyst/news evidence may affect conclusions.
- HEADLINE TRIAGE and UNVERIFIED claims are discovery leads only; do not use them as factual support for a trade.
- Never convert a reachable URL or source reputation into verification of the claim itself.
- If you introduce a factual claim not present in the supplied verified evidence, label it UNVERIFIED and exclude it from the recommendation.
- Explicitly discount stale components using confidence_adjustments.
- Regime scores are 0-100 risk indices, NOT probabilities. regime_mix_not_probability is descriptive only.
- regime_evidence_coverage is separate from risk: low risk + low coverage means uncertainty, not safety.
- Treasury buybacks are liquidity/policy-response evidence, not by themselves proof of weak demand or QE.
- If previous_run is supplied, use it for true run-to-run comparisons; do not infer "what changed" solely from 1w/1m/3m market fields.
- A 2Y Treasury yield above current SOFR is a carry/rate-path signal, NOT by itself proof that the market prices hikes; term/risk premia also matter.
- Tokenized Treasury/RWA products (for example accumulating-NAV structures) are not automatically $1-pegged stablecoins. Use the supplied asset classification.
- A FAILED source means missing evidence, not a benign zero reading.

Prioritize causal mechanisms, fiscal flows, policy actors, foreign actors, Treasury/repo plumbing,
positioning, structural dollar supports, and disconfirming evidence. Distinguish duration/supply stress
from inflation. Distinguish fundamental USD weakness from short-covering in JPY/EUR/CHF.
Economic interests are not proof of motive. Do not fabricate facts beyond supplied data.
Give concrete portfolio implications, but respect the hard engine's minimum trade size and anti-chasing rules.
For each recommendation, state the machine/human evidence that would reverse it.
"""
    user = "Analyze this dashboard snapshot. Return sections: Evidence Quality, What Changed, Causal Interpretation, Red-Team Case, Missing Factors, Portfolio Actions, Reversal Triggers, Unverified Claims To Check.\n\n" + json.dumps(payload, default=str)[:50000]
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
