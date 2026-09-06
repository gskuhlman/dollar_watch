from __future__ import annotations

import json
import os
import requests


def analyze_with_local_llm(payload: dict, base_url: str | None = None, model: str | None = None, api_key: str | None = None) -> str:
    base_url = (base_url or os.getenv("LMSTUDIO_BASE_URL", "")).rstrip("/")
    model = model or os.getenv("LMSTUDIO_MODEL", "")
    api_key = api_key or os.getenv("LMSTUDIO_API_KEY", "lm-studio")
    if not base_url:
        raise ValueError("LM Studio base URL is not configured")
    if not model:
        # Query OpenAI-compatible model list when possible.
        r = requests.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=8)
        r.raise_for_status()
        models = r.json().get("data", [])
        if not models:
            raise ValueError("No model specified and no models returned by /models")
        model = models[0]["id"]

    system = """You are the red-team macro analyst for a U.S. dollar crisis dashboard.
Do not assume the dollar-collapse thesis is correct. Distinguish: managed devaluation,
fiscal/inflation crisis, dollar funding squeeze, and reserve-confidence crisis.
Prioritize causal mechanisms, policy actors, foreign actors, positioning, Treasury plumbing,
structural dollar supports, and disconfirming evidence. Economic interests are not proof of motive.
Give concrete portfolio implications but explicitly identify what evidence would reverse each recommendation.
Do not fabricate facts beyond the supplied data."""
    user = "Analyze this dashboard snapshot. Return sections: What Changed, Causal Interpretation, Red-Team Case, Missing Factors, Portfolio Actions, Reversal Triggers.\n\n" + json.dumps(payload, default=str)[:50000]
    r = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":user}], "temperature":0.2},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
