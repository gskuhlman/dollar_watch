from __future__ import annotations

import json
import os
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import requests



from .evidence import summarize_verification_records, temporal_claim_source_mismatch


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
        keep={"timestamp","market_summary","fred_summary","auction_stress_auto","auction_summary","upcoming_auctions","treasury_auction_calendar_meta","cftc_usd_downside_pressure","cftc_summary","fx_positioning_squeeze_risk","tic_dedollarization_pressure","tic_meta","tic_transaction_meta","cofer_dedollarization_pressure","cofer_meta","fiscal_flow_stress_auto","fiscal_meta","stablecoin_dollar_support_auto","stablecoin_meta","treasury_buyback_meta","fed_treasury_classification","treasury_financing_meta","offshore_usd_funding_meta","official_policy_meta","data_confidence","component_confidence"}
        data["snapshot"]={k:v for k,v in data["snapshot"].items() if k in keep}
    raw=json.dumps(data,default=str)
    return raw

_MONTHS = {
    "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,
    "may":5,"jun":6,"june":6,"jul":7,"july":7,"aug":8,"august":8,
    "sep":9,"sept":9,"september":9,"oct":10,"october":10,"nov":11,"november":11,
    "dec":12,"december":12,
}
_DATE_TOKEN_RE = re.compile(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b", re.I)
_TERM_TOKEN_RE = re.compile(r"\b(2|3|5|7|10|20|30)\s*(?:[- ]?year|Y)\b", re.I)


def _treasury_local_date_from_payload(payload: dict | None) -> date | None:
    try:
        ts=((payload or {}).get("snapshot") or {}).get("timestamp")
        if not ts:
            return None
        dt=datetime.fromisoformat(str(ts).replace("Z","+00:00"))
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("America/New_York")).date()
    except Exception:
        return None


def _future_nominal_auction_claim_violations(text: str, payload: dict | None) -> list[str]:
    snap=(payload or {}).get("snapshot") or {}
    rows=snap.get("upcoming_auctions") or []
    asof=_treasury_local_date_from_payload(payload)
    if asof is None:
        return []
    allowed=set()
    for r in rows:
        key=str(r.get("term_key") or "").strip()
        cls=str(r.get("instrument_class") or "NOMINAL_COUPON").strip().upper()
        if cls not in {"", "NOMINAL_COUPON"} or key.endswith(" TIPS") or key.endswith(" FRN"):
            continue
        try:
            d=date.fromisoformat(str(r.get("auction_date"))[:10])
        except Exception:
            continue
        allowed.add((d, key.lower()))
    violations=[]
    for raw in str(text or "").splitlines():
        line=raw.strip(); low=line.lower()
        if "auction" not in low:
            continue
        if "today" in low or "tomorrow" in low:
            violations.append("Treasury auction calendar language used relative date words (today/tomorrow). Use the supplied absolute Treasury/New York auction date instead so UTC rollover cannot mislabel the event day.")
        dates=[]
        for m in _DATE_TOKEN_RE.finditer(line):
            mon=_MONTHS[m.group(1).lower().rstrip('.')]; day=int(m.group(2)); year=int(m.group(3) or asof.year)
            try:
                d=date(year,mon,day)
            except ValueError:
                continue
            if m.group(3) is None and d < asof - timedelta(days=180):
                d=date(asof.year+1,mon,day)
            dates.append((m.start(),d))
        term_matches=[]
        for m in _TERM_TOKEN_RE.finditer(line):
            term=f"{int(m.group(1))}-year"
            # Instrument identity belongs to the individual tenor, not the whole sentence.
            # This matters for mixed calendar prose such as "2Y FRN reopening + 5Y Sep 23".
            left=max(0,m.start()-14); right=min(len(line),m.end()+18)
            ctx=line[left:right].lower()
            explicit_non_nominal=("tips" in ctx or "frn" in ctx)
            term_matches.append((m.start(),term,explicit_non_nominal))
        if not dates or not term_matches:
            continue

        # A single date commonly applies to several tenors in compact prose (for example
        # "2Y FRN reopening + 5Y Sep 23"). Validate every tenor against that shared date.
        # When a line contains several semicolon-delimited calendar clauses, prefer the
        # date inside the same clause before falling back to nearest-token association.
        associations=[]
        semis=[i for i,ch in enumerate(line) if ch == ";"]
        for pos,term,explicit_non_nominal in term_matches:
            left=max([-1]+[i for i in semis if i < pos]) + 1
            right=min([len(line)]+[i for i in semis if i > pos])
            local_dates=[x for x in dates if left <= x[0] < right]
            if len(local_dates) == 1:
                d=local_dates[0][1]
            elif local_dates:
                d=min(local_dates,key=lambda x:abs(x[0]-pos))[1]
            elif len(dates) == 1:
                d=dates[0][1]
            else:
                d=min(dates,key=lambda x:abs(x[0]-pos))[1]
            associations.append((pos,term,explicit_non_nominal,d))

        for _pos,term,explicit_non_nominal,d in associations:
            if d < asof or explicit_non_nominal:
                continue
            if (d,term) not in allowed:
                violations.append(f"Future nominal Treasury auction claim {term} on {d.isoformat()} is not present in snapshot.upcoming_auctions. Do not infer auction dates from cadence or prior reports; use only the supplied exact nominal calendar. If the security is a TIPS or FRN, label it explicitly so it is not mistaken for a nominal coupon replacement.")
    return violations



def _cftc_date_semantics_violations(text: str, payload: dict | None) -> list[str]:
    """Catch prose that mistakes Tuesday CFTC position dates for publication/report dates.

    The dashboard carries both dates explicitly in scores.observed_position_unwind.  A line may
    mention a Tuesday position date when it is labeled as an as-of/position date; otherwise a
    phrase such as "Sep 15 CFTC report" is ambiguous/wrong and should be repaired to the
    expected Friday publication date.
    """
    unwind=((payload or {}).get("scores") or {}).get("observed_position_unwind") or {}
    asof_dates=[]
    for k in ("latest_position_asof_date","latest_cftc_report_date","next_position_asof_date"):
        v=unwind.get(k)
        if not v:
            continue
        try:
            d=date.fromisoformat(str(v)[:10])
        except Exception:
            continue
        if d not in asof_dates:
            asof_dates.append(d)
    if not asof_dates:
        return []

    def _line_dates(line: str) -> set[date]:
        out=set()
        # ISO dates are common in machine-oriented prose.
        for m in re.finditer(r"\b(20\d{2})-(\d{2})-(\d{2})\b", line):
            try: out.add(date(int(m.group(1)),int(m.group(2)),int(m.group(3))))
            except ValueError: pass
        # Human month/day dates are common in the generated red-team report.
        for m in _DATE_TOKEN_RE.finditer(line):
            mon=_MONTHS[m.group(1).lower().rstrip('.')]; day=int(m.group(2))
            year=int(m.group(3) or max(asof_dates).year)
            try: out.add(date(year,mon,day))
            except ValueError: pass
        return out

    violations=[]
    for raw in str(text or "").splitlines():
        line=raw.strip(); low=line.lower()
        if "cftc" not in low:
            continue
        hit=[d for d in asof_dates if d in _line_dates(line)]
        if not hit:
            continue
        # Position/as-of language makes the Tuesday date semantically explicit.
        labeled_asof=any(k in low for k in ["as-of","as of","position-as-of","position as-of","positions as-of","position date","positions date"])
        # "CFTC report" / "publication" / "print" attached to the Tuesday date without an as-of
        # label is the recurring error we want the repair pass to correct.
        reportish=any(k in low for k in ["cftc report","cftc publication","cftc print","report confirming","report due","publication due"])
        if reportish and not labeled_asof:
            ds=", ".join(d.isoformat() for d in hit)
            violations.append(
                f"CFTC Tuesday position-as-of date(s) {ds} were described as a report/publication date. "
                "Label Tuesday as the position-as-of date and use observed_position_unwind.latest/next_expected_publication_date for the expected public release (normally Friday)."
            )
    return violations


def _event_freshness_language_violations(text: str) -> list[str]:
    """Do not call event evidence fresh when the engine labels it aging/pending/expired."""
    violations=[]
    for raw in str(text or "").splitlines():
        low=raw.lower()
        if "fresh" not in low:
            continue
        stale_state=None
        if "aging" in low: stale_state="AGING"
        elif "pending_replacement" in low or "pending replacement" in low: stale_state="PENDING_REPLACEMENT"
        elif "expired" in low: stale_state="EXPIRED"
        if stale_state and not any(k in low for k in ["not fresh","no longer fresh","isn't fresh","is not fresh"]):
            violations.append(
                f"Event evidence labeled {stale_state} was also called fresh. Use the engine lifecycle literally: "
                "FRESH is fresh; AGING/PENDING_REPLACEMENT/EXPIRED are reduced/awaiting-replacement/expired evidence, not fresh evidence."
            )
    return violations

def _jpy_positioning_narrative_violations(text: str, payload: dict | None) -> list[str]:
    """Reject presenting an active crowded-JPY-short squeeze when CFTC says crowded LONG.

    Generic intervention direction mechanics remain correct for any open shorts.
    This guard targets *current positioning/reversal narratives* that mistakenly
    promote those counterfactual mechanics to today's dominant crowded position.
    """
    scores=(payload or {}).get("scores") or {}
    context=scores.get("fx_intervention_positioning_context") or {}
    state=str(context.get("observed_crowding_state") or "").upper()
    if not state:
        for row in (((payload or {}).get("snapshot") or {}).get("cftc_summary") or []):
            if str(row.get("market") or "") == "Japanese Yen":
                state=str(row.get("leveraged_crowding_state") or "").upper()
                break
    if state != "CROWDED_LONG":
        return []
    violations=[]
    for line in str(text or "").splitlines():
        low=line.lower().replace("–","-").replace("—","-").replace("‑","-")
        low=re.sub(r"\b(yen|jpy)[ -]buying\b",r"\1-buying",low)
        low=re.sub(r"\b(yen|jpy)[ -]selling\b",r"\1-selling",low)
        short_squeeze=bool(re.search(r"\b(?:(?:jpy|yen)[ -]short[ -]squeeze|short[ -](?:jpy|yen)[ -]squeeze)\b",low))
        if not short_squeeze:
            continue
        # An explicitly historical or conditional scenario is valid as long as
        # it is not promoted to the CURRENT crowded JPY positioning state.
        counterfactual=any(term in low for term in (
            "if shorts rebuild", "if jpy shorts rebuild", "if yen shorts rebuild",
            "if shorts become crowded", "if crowded shorts return", "historically crowded short",
            "not currently crowded short", "not the current crowded", "not an active short squeeze",
            "no current short squeeze", "short squeeze is unsupported", "short-squeeze framing is unsupported",
        ))
        if counterfactual:
            continue
        if re.search(r"\b(?:yen|jpy)-buying\b.{0,140}\b(?:intensif|amplif|trigger|fuel|sharpen|reinforc|accelerat)",low):
            violations.append("Current JPY CFTC positioning is CROWDED_LONG. Yen-buying may support those longs; do not present an active crowded-JPY-short squeeze as today's primary risk. Yen-selling would pressure the crowded longs and may prompt liquidation. Intervention direction remains UNKNOWN unless verified.")
        elif ("yen-selling" in low or "jpy-selling" in low) and ("yen-buying" in low or "jpy-buying" in low) and not ("crowded long" in low or "long liquidation" in low or "longs" in low):
            violations.append("Current JPY is CROWDED_LONG; bilateral yen-buying/yen-selling reversal prose discussed only JPY-short-squeeze mechanics and omitted exposure of currently crowded yen longs. State the current long-side risk and preserve intervention direction UNKNOWN.")
    return list(dict.fromkeys(violations))


def red_team_narrative_violations(text: str, payload: dict | None = None) -> list[str]:
    """Deterministic lint for repeatedly harmful causal/narrative/calendar errors."""
    violations: list[str] = []
    chunks = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    for line in chunks:
        low = line.lower()
        if "structural support" in low and any(k in low for k in ["bill accumulation", "mbs runoff", "reserve management", "reserve-management", "fed bill"]):
            if not any(k in low for k in ["not structural", "not a structural", "not part of structural", "excluded from structural"]):
                violations.append("Fed bill accumulation/MBS runoff was grouped under structural dollar support; it is reserve-management/composition only unless a separate supplied channel supports the label.")
        if any(k in low for k in ["record compensation", "record yield", "record real yield", "all-time high"]):
            if any(k in low for k in ["percentile", "term premium", "real yield", "tips", "10y", "30y"]):
                violations.append("A finite-window percentile was promoted to record/all-time language without supplied all-time evidence.")
    snap=(payload or {}).get("snapshot") or {}
    tic_tx_meta=snap.get("tic_transaction_meta") or {}
    tic_tx_conf=float((snap.get("component_confidence") or {}).get("tic_transactions",0) or 0)
    if (not tic_tx_meta or tic_tx_conf <= 0):
        for line in chunks:
            low=line.lower()
            if any(k in low for k in ["net transactions", "active selling", "active purchases", "active buying"]):
                if any(k in low for k in ["tic", "foreign official", "foreign-official", "treasury"]):
                    violations.append("TIC active-transaction language was used even though tic_transaction_meta is unavailable or has zero confidence. Do not infer active purchases/sales from FRED summary holdings or stale cached prose; state that TIC transaction evidence is unavailable.")
                    break
    violations.extend(_future_nominal_auction_claim_violations(text,payload))
    violations.extend(_cftc_date_semantics_violations(text,payload))
    violations.extend(_event_freshness_language_violations(text))
    violations.extend(_jpy_positioning_narrative_violations(text,payload))
    # Preserve order while deduplicating.
    return list(dict.fromkeys(violations))


def _repair_red_team_analysis(
    analysis: str, violations: list[str], *, base_url: str, model: str, api_key: str, timeout_seconds: int
) -> str:
    repair_system = (
        "You are a deterministic macro-analysis copy editor. Preserve the original section structure, numbers, "
        "recommendations, uncertainty, and all claims that are not listed as violations. Correct ONLY the listed "
        "violations. Do not add new facts. Return the complete corrected analysis, with no preamble."
    )
    repair_user = "Violations to correct:\n- " + "\n- ".join(violations) + "\n\nOriginal analysis:\n" + analysis
    rr = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role":"system","content":repair_system},{"role":"user","content":repair_user}], "temperature":0.0},
        timeout=(10, timeout_seconds),
    )
    rr.raise_for_status()
    return rr.json()["choices"][0]["message"]["content"]


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

    system = """You are the red-team macro analyst for dollar_watch V3.4.27.
Do not assume a dollar-collapse thesis is correct. Distinguish six regimes:
(1) managed dollar devaluation, (2) fiscal/Treasury supply stress,
(3) inflation/monetary debasement, (4) dollar funding squeeze,
(5) reserve-confidence crisis, and (6) FX positioning squeeze.

Evidence rules are strict:
- DATA-DERIVED values may be analyzed as supplied.
- VERIFIED analyst/news evidence may affect conclusions.
- HEADLINE TRIAGE and UNVERIFIED claims are discovery leads only; do not use them as factual support for a trade.
- Never convert a reachable URL or source reputation into verification of the claim itself.
- VERIFICATION COUNT RULE: verification_check_summary and verification_queue_state_summary are authoritative FULL-POPULATION database aggregates when complete_population=true. Detailed record lists are truncated samples and must never be recounted as totals. Use canonical verdict_counts for evidentiary outcomes; keep status_counts (workflow state) and relevance_counts (relevance gate) separate. raw_label_anomalies are data-hygiene audit metadata only: legacy typos/wrappers such as CONTRICTED or VERDICT:_INCONCLUSIVE canonicalize into the proper verdict and must never be presented as distinct evidence categories. If you print a complete-population breakdown, include every nonzero category (or an explicit OTHER/UNSET remainder) and honor verdict_count_sum/status_count_sum/relevance_count_sum plus the *_reconcile flags; never publish a partial list whose numbers do not add to total. Keep persisted source checks distinct from queue/candidate records.
- FED RESERVE-MANAGEMENT NEUTRALITY: BILL_ACCUMULATION_WITH_MBS_RUNOFF is reserve-management/composition evidence. It is not by itself structural dollar support, QE, fiscal rescue, monetization, devaluation, or a directional USD signal. Do not group it under "structural dollar supports" unless a separate supplied channel independently supports that label.
- INFLATION LANGUAGE RULE: when inflation/debasement risk is below its machine trigger but market-implied inflation measures are historically elevated, say "below trigger / not confirming debasement" rather than unqualified "contained," "benign," or "no inflation risk." Preserve both the absolute level and percentile context.
- MARKET-PRICING INFERENCE RULE: spot, yield, or asset-price moves may be described as consistent with a mechanism, but they do not by themselves prove what "the market is pricing," believes, expects, or is under/over-pricing. Use pricing-language only when a supplied instrument explicitly measures implied pricing/expectations.
- POSITIONING-DECAY RULE: normalization of crowded positions can reduce the positioning contribution to a squeeze, but do not call squeezes categorically "self-limiting." A catalyst or fundamental driver can persist after positioning changes.
- ANTI-CHASE LANGUAGE RULE: a large prior return is not itself "a chase." Say that adding exposure primarily because of a recent large move would risk chasing; keep the distinction between observed return and proposed action.
- FIXED-HORIZON SCORE-MODEL RULE: use a fixed-horizon delta only when its status is OK. INCOMPARABLE_SCORE_MODEL means the scoring formula lineage changed, so the score delta is N/A and must not be narrated as market/economic change.
- UPCOMING TREASURY AUCTION CALENDAR RULE: snapshot.upcoming_auctions is the authoritative calendar for FUTURE NOMINAL coupon-auction dates/tenors used in fiscal trigger lifecycle. Use exact term_key/date pairs from that list only; never infer the next auction from monthly cadence, a prior report, or a same-number TIPS/FRN security. A 10-Year TIPS reopening is not a nominal 10-Year note replacement. Use absolute dates rather than "today"/"tomorrow" because the snapshot timestamp is UTC while Treasury auction dates follow the U.S./New York calendar. If a future date/tenor is not supplied, call it unknown rather than inventing it.
- MIXED-INSTRUMENT AUCTION RULE: when mentioning TIPS or FRNs in the same sentence as nominal auctions, label each non-nominal instrument explicitly (for example "2-Year FRN reopening"). Never shorten an FRN/TIPS to a bare tenor such as "2Y reopening", because that reads as a nominal coupon claim. If one date is shared by several tenors in compact prose, every tenor/date pair must independently match the supplied calendar.
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
- TIC PATH-INDEPENDENCE RULE: direct TIC country holdings (tic_meta/tic_summary) and the FRED-hosted TIC transaction/valuation decomposition (tic_transaction_meta) are independent evidence paths. A direct TIC country-table failure does NOT invalidate a healthy tic_transaction_meta. Conversely, if tic_transaction_meta is empty or component_confidence.tic_transactions is 0, do not use FRED summary transaction numbers to claim active foreign purchases/sales; holdings changes alone are not transaction evidence. State which path is unavailable.
- HISTORICAL REPLAY V3.4.26 RULE: When fixed_horizon_changes.horizons[*].comparison_method is REPLAY_CURRENT_MODEL_SAVED_INPUTS, the historical regime score is a CURRENT-FORMULA RETROSPECTIVE ESTIMATE on SAVED point-in-time input summaries, not the originally published score and not a full re-run of old upstream collectors. Clearly identify it as a replay estimate, state actual_age_days and material source/collector limitations, and never call its change pure observed market movement. REPLAY_INPUTS_INCOMPLETE or UNAVAILABLE means N/A, not zero. Old snapshots and their original scores are immutable. Do not suggest 1M/3M/6M/1Y history exists before the first preserved snapshot date.
- FIXED-HORIZON DATA-QUALITY RULE: fixed_horizon_context.horizons[*].data_quality_status and material_data_quality_changes are authoritative. When DATA_QUALITY_AFFECTED, do not narrate the regime-score delta as a pure market/economic move. Explicitly state that source availability/confidence changed and separate the observed indicator changes from the measurement-quality change. A falling score caused partly by a failed source is not evidence that the underlying risk improved.
- Central-bank liquidity swaps and FIMA foreign-official repo are separate facilities. Never call SWPT "FIMA swaps".
- Use the supplied Fed Treasury-holdings classification. Bill accumulation with MBS runoff is not automatic QE or fiscal-rescue evidence.
- V3.4.23 Treasury financing has TWO layers. Z.1 holder flows answer who absorbed Treasury issuance; repo, hedge-fund structure and SLR capacity are funding/intermediation overlays. Never add the funding layer to holder flows or double-count the same Treasury.
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
- FIXED-HORIZON CHANGE RULE: analytical deltas come ONLY from fixed_horizon_changes (1D, 7D, 1M, 3M, 6M, 1Y). Do NOT use the immediately previous app run as the primary "What Changed" comparison. Re-running the app minutes later must not erase or manufacture a meaningful delta.
- For each fixed horizon, use only rows with status == OK and cite the supplied reference_timestamp/actual_age_days when useful. If a horizon is UNAVAILABLE or INCOMPARABLE_SCHEMA, say N/A/insufficient comparable history; never substitute a different run.
- previous_run_audit_only is operational/debug context only (version/source-transition lineage). It may identify a source recovery, trigger transition, or code/schema change, but it must not supply analytical regime deltas.
- Do not infer "what changed" solely from 1w/1m/3m market fields; those fields are indicator context, not substitutes for fixed-horizon dashboard snapshots.
- A 2Y Treasury yield above current SOFR is a carry/rate-path signal, NOT by itself proof that the market prices hikes; term/risk premia also matter.
- Tokenized Treasury/RWA products (for example accumulating-NAV structures) are not automatically $1-pegged stablecoins. Use the supplied asset classification.
- A FAILED source means missing evidence, not a benign zero reading.
- Median SOFR-IORB and SOFR99-IORB are different signals. Never describe SOFR99-IORB as distance to the median SOFR trigger. Use repo_tail_signal for upper-tail stress and repo_or_swap_stress for median/facility stress.
- Domestic repo/Fed-facility coverage is not full global-dollar-funding coverage. V3.4.23 may supply a front-futures/spot dislocation proxy; this is NOT cross-currency basis. Explicitly mention the remaining cross-currency-basis/FX-swap gap when Dollar Funding Squeeze coverage is discussed.
- Funding-stress trigger semantics are stateful. repo_stress_normalized can only KILL a funding overlay after repo_or_swap_stress was previously active and recovery persistence is satisfied. Never recommend reducing liquidity simply because SOFR-IORB is currently below the entry threshold.
- A large central-bank USD swap-line draw or FIMA draw is evidence FOR dollar-funding stress. It supports more T-bills/liquidity and less high-beta/non-USD risk; it is NEVER a reason to add non-USD exposure.
- FUNDING-FACILITY NON-NECESSITY RULE: swap-line/FIMA draws are positive evidence of funding stress when they occur, but they are NOT necessary conditions for a dollar shortage or funding squeeze. Zero/small draws are counterevidence only within the observed facility-eligible/domestic scope; they do not rule out private-market, offshore, eligibility-, stigma-, or timing-related stress. Never write that a funding shortage "would be expected" to produce facility draws as though their absence falsifies the shortage. Pair facility data with SOFR/repo/tail signals and explicitly retain the offshore basis/FX-swap blind spot.
- LIQUIDITY-BUFFER PREDICTION RULE: low-percentile reserve balances, a rebuilding TGA, and depleted ON RRP may indicate a thinner liquidity cushion and greater sensitivity to settlement/tax-date or balance-sheet shocks. They do NOT by themselves predict an impending repo event, establish a "classic setup" for one, or prove funding stress. Use words such as "reduced buffer", "greater sensitivity", or "watch condition" unless actual repo/SOFR/tail/facility/basis evidence confirms stress.
- VERIFIED-SOURCE SCOPE RULE: a SUPPORTED analyst/news item supports only the exact verified scope of that item. Country-specific evidence (for example PBoC/China gold purchases) must not be generalized into broad "central banks are rotating into gold" or reserve-diversification claims without broader verified evidence. Verification of an article's existence/metadata is not verification of every causal or market claim in the article.
- VERIFIED-FACT COHERENCE RULE: do not stitch month-specific quantities, streak lengths, rankings, or other numerical attributes from separate verification records into one synthetic fact. If a sentence says an entity bought X in a named month and also gives a streak/duration or superlative, those details must be jointly supported by the same same-period verified record/source. Otherwise separate the facts by date/source or omit the unsupported attribute.
- REGIME-DIRECTION LANGUAGE RULE: regime labels imply typical directional pressure, not guaranteed asset moves. A bilateral foreign-currency short squeeze can tend to weaken USD versus that currency; a dollar-funding squeeze can tend to strengthen USD through liquidity demand. Describe these as directional tendencies and scenario risks, not deterministic outcomes.
- In a dollar-funding squeeze, USD denomination alone is not a hedge. Treat T-bills as the clean direct hedge; TIPS and U.S. equities remain rate/market-sensitive; gold and CHF are conditional; BTC and unhedged ex-US equities are vulnerable.
- Policy evidence has two tiers. deterministic_verified_evidence contains exact official facts that passed domain-specific anchor validation; these may automatically raise evidence coverage and have only tightly bounded mechanical score effects, but NEVER establish motive. approved_policy_evidence contains human-approved, source-relevant, SUPPORTED interpretations and may receive the full bounded intent/motive-sensitive effect. Do not describe deterministic facts as "human approved" and do not require human approval merely to state an agency's exact reported fact.
- DETERMINISTIC FACT COUNT RULE: deterministic_evidence_summary is authoritative for the number and action-class breakdown of UNIQUE analyst-facing deterministic facts. Do not add or recount official_policy_meta.canonical_statements on top of deterministic_verified_evidence; canonical statement rows can be validator representations of the same structured fact. If duplicate_fact_keys_present is false, never report more deterministic facts than total_unique_facts.
- V3.4.23 official_policy_meta contains deterministic primary-source facts. Japan MOF monthly intervention totals are direct observations of occurrence/amount only. Do not infer yen-buying direction from monthly totals; direction requires detailed currencies-bought/sold data. They also do not prove broad U.S. dollar intent. NY Fed U.S. FX-operation reports may establish whether the U.S. intervened directly in the reported quarter.
- MOF RESERVE-ASSET INFERENCE: even if later detailed MOF data confirms yen-buying intervention, that establishes use/sale of foreign-currency reserves or cash to obtain yen; it does NOT by itself prove U.S. Treasury sales, Treasury-collateral liquidation, or broad "USD asset disposal." Name a specific reserve asset/instrument only when the supplied official detail identifies it or an independently verified transaction source does.
- CURRENT JPY POSITIONING RULE: scores.fx_intervention_positioning_context is the authoritative current-state companion to the generic fx_intervention_direction_semantics. When latest observed CFTC is CROWDED_LONG JPY, JPY-selling (if verified) pressures the crowded longs and can prompt long liquidation; JPY-buying supports those longs. Do NOT present an active crowded-JPY-short squeeze as today's principal risk. The generic short-side mechanics apply only to remaining shorts or a later documented crowded-short positioning state. CFTC is a dated position observation; no intervention direction or liquidation is established by a scenario. Apply this rule in ALL sections, including Reversal Triggers and Portfolio Actions.
- FX INTERVENTION DIRECTION RULE: use fx_intervention_direction_semantics exactly. JPY-buying / foreign-currency-selling supports the yen and tends to push USDJPY lower, which pressures remaining short-JPY positions; a crowded-JPY-short squeeze requires a currently crowded-short CFTC state, not merely yen-buying. JPY-selling / foreign-currency-buying weakens the yen and tends to push USDJPY higher, which benefits short-JPY positions but pressures JPY longs; with CROWDED_LONG JPY, long-side liquidation is the relevant conditional risk. Never say yen-selling would "squeeze JPY shorts the other way."
- Z.1 HOLDER-FLOW CAUSALITY RULE: Treasury-financing holder shares describe net acquisitions/absorption relative to net marketable issuance. They do NOT by themselves identify the marginal auction buyer, prove that an auction or quarter "cleared only with" a given holder, prove buyer dependency/fragility, or establish failed/private demand. Use auction bidder data for placement quality; use Z.1 only for ex-post financing mix unless separate verified evidence establishes causality.
- BUYBACK VOCABULARY RULE: offered/accepted or offered/capacity multiples in Treasury buybacks measure how much SELLER inventory was offered to Treasury relative to what Treasury accepted/could accept. Do not call that "well-subscribed" issuance, investor demand, or evidence that Treasury securities were strongly demanded. Say seller offers exceeded accepted/capacity by the supplied multiple.
- HUMAN INTENT GATE VOCABULARY: broad_intent_human_gate == true means human-approved evidence is REQUIRED for broad-USD motive effects. If broad_intent_human_gate_status == UNSATISFIED or human-approved interpretive coverage is zero, call the gate UNSATISFIED/closed to motive scoring—not "open." A SATISFIED gate permits bounded interpretation; it still does not make motive certain.
- V3.4.23 intervention_history is a quarter-level actor/currency/purpose timeline. A targeted Treasury/ESF intervention (for example Argentina stabilization) is not broad-dollar policy; always state actor, currency, direction/purpose, and broad-USD implication.
- V3.4.23 may include nyfed_lagged_basis_validation: an official quarterly cross-check of offshore FX-swap funding conditions. It is useful validation context but is too stale to fire a live funding trigger or raise live offshore coverage.
- Canonical official pages may be served from a transparent LAST_KNOWN_CACHE after transient 503/403 errors. Treat a dated cached copy as valid historical evidence for that fixed statement, but disclose that live reachability failed and do not imply a fresher statement.
- Policy evidence has an action taxonomy. BROAD_USD_DEVALUATION strengthens non-USD/devaluation hedges; BILATERAL_FX_POLICY or BILATERAL_FX_INTERVENTION raises pair-specific FX-squeeze catalyst confidence but does not automatically trade; USD_FUNDING_STRESS favors T-bills/liquidity and trims BTC/unhedged ex-US; RESERVE_CONFIDENCE_STRESS favors gold/CHF and avoiding long nominal duration; FISCAL_DEBT_MANAGEMENT is not itself a trade signal. Never collapse all intervention/devaluation evidence into "add T-bills."
- A verified Japanese intervention or U.S.-Japan yen-policy statement is evidence about the USD/JPY catalyst complex, not automatic proof of deliberate broad-dollar devaluation.
- CFTC DATE SEMANTICS: latest_cftc_report_date/report_date and latest_position_asof_date are the Tuesday POSITION-AS-OF date, not publication dates. latest_expected_publication_date is normally that Friday (+3 days). next_position_asof_date is the following Tuesday (+7); next_expected_publication_date (and backward-compatible expected_publication_date) is normally the following Friday (+10). Holiday shifts are possible. Never call a Tuesday as-of date the public release date and do not invent null calendar fields when these supplied derived dates exist.
- CFTC DATE NAMING RULE: never write a bare phrase such as "Sep 15 CFTC report" when Sep 15 is the Tuesday position-as-of date. Say "positions as of Sep 15, expected publication Sep 18" (using the supplied dates). A Friday publication may be called a report/publication date; a Tuesday must be labeled as-of/position date.
- EVENT FRESHNESS VOCABULARY: lifecycle labels are authoritative. FRESH may be called fresh. AGING, PENDING_REPLACEMENT, and EXPIRED must not be called fresh, even parenthetically (for example never write "fresh (AGING)"). Say active-but-aging / awaiting replacement / expired as appropriate.
- TENOR-SPECIFIC AUCTION TRIGGER RULE: exact tenors matter. Weak 2Y/5Y/7Y auctions may raise broad auction stress but cannot confirm `weak_10y_30y_pair`, substitute for 10Y/30Y evidence, or be described as a repeat of long-end 20Y weakness without explicitly distinguishing the tenor and the broader rationale.
- TGA SEMANTICS: a rising Treasury General Account is a Treasury cash-balance rebuild and, while funds remain in the TGA, a drain on reserve/liquidity balances. Do NOT call a TGA rebuild "prefunding future supply" or proof of future issuance unless supplied official cash-management/issuance evidence explicitly establishes that purpose.
- FUNDING-SCOPE LANGUAGE: if funding_observation_scope.status == PARTIAL_OFFSHORE or offshore funding coverage is below 70%, do not label the GLOBAL dollar-funding environment simply "benign", "clean", or "no crisis". Say observed domestic indicators do not confirm stress / are calm, then explicitly retain the cross-currency-basis and OTC FX-swap blind spot. A lagged NY Fed quarterly basis characterization cannot close the live gap.
- FX INDEX ATTRIBUTION RULE: a large move in one FX cross does not establish that a broad-dollar index move is "concentrated" in, "driven by", or mostly caused by that currency. Make index-contribution claims only when supplied weights/contribution decomposition support them; otherwise describe the cross as a notable coincident move.
- PERCENTILE/VALUATION RULE: an extreme yield, real-yield, spread, price, or term-premium percentile describes the observed level ONLY relative to the explicitly supplied lookback window (for example 1y or 3y). A 99th/100th percentile reading does NOT mean an all-time record, a historical record, or "record compensation" unless separate all-time evidence is supplied. Prefer "near the top of the 1-year/3-year lookback" or "extreme within the supplied lookback." It is not by itself an entry signal, proof of cheap/expensive valuation, or reason to add/trim an asset. For TIPS, explicitly retain duration/real-yield risk when discussing high starting real yields.
- CFTC CROWDING SEMANTICS: cftc_summary.leveraged_crowding_state is authoritative for whether a position is historically crowded. For EUR/JPY/CHF contracts, LOWER leveraged_3y_percentile means more unusually short and HIGHER percentile means relatively longer / less historically short. A negative net position or a large short share of open interest does NOT by itself make the position historically crowded. Never call a foreign-currency position "crowded short" when leveraged_crowding_state is SHORT_NOT_HISTORICALLY_CROWDED; describe it as net short but not historically crowded. CROWDED_SHORT is the strongest label; ELEVATED_SHORT is weaker. Example: a JPY net short at the 72nd percentile is a net short in absolute terms but is NOT a crowded short relative to its 3-year history.
- POSITION UNWIND LANGUAGE: observed_position_unwind is the only authority for saying CFTC positions actually unwound. Spot FX strengthening against crowded shorts may be described only as "consistent with short-covering" unless observed_position_unwind.status == CONFIRMED. PARTIAL means some report-over-report covering/liquidation evidence, not a confirmed broad unwind; UNCONFIRMED/STALE_UNCONFIRMED means do not say the shorts "are unwinding" as a factual statement.

Prioritize causal mechanisms, fiscal flows, policy actors, foreign actors, Treasury/repo plumbing,
positioning, structural dollar supports, and disconfirming evidence. Distinguish duration/supply stress
from inflation. Distinguish fundamental USD weakness from spot action consistent with short-covering in JPY/EUR/CHF, and separately state whether CFTC data confirms an observed position unwind.
Economic interests are not proof of motive. Do not fabricate facts beyond supplied data.
Give concrete portfolio implications, but respect the hard engine's minimum trade size and anti-chasing rules.
For each recommendation, state the machine/human evidence that would reverse it.
"""
    user = "Analyze this dashboard snapshot. Return sections: Evidence Quality, What Changed (fixed horizons), Causal Interpretation, Red-Team Case, Missing Factors, Portfolio Actions, Reversal Triggers, Unverified Claims To Check.\n\n" + _compact_analysis_payload(payload)
    r = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":user}], "temperature":0.2},
        timeout=(10, timeout_seconds),
    )
    r.raise_for_status()
    analysis = r.json()["choices"][0]["message"]["content"]
    violations = red_team_narrative_violations(analysis, payload)
    if violations:
        try:
            repaired = _repair_red_team_analysis(
                analysis, violations, base_url=base_url, model=model, api_key=api_key, timeout_seconds=timeout_seconds
            )
            # Prefer the repair if it removes at least one deterministic violation.
            if len(red_team_narrative_violations(repaired, payload)) < len(violations):
                analysis = repaired
        except Exception:
            # Analysis availability is more important than a second-pass style repair;
            # the primary prompt still contains the same hard guardrails.
            pass
    return analysis


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
    temporal_gate=temporal_claim_source_mismatch(claim,source_text)
    if temporal_gate.get("mismatch"):
        return (
            "INCONCLUSIVE\n"
            "Deterministic temporal-consistency gate: the claim names a specific period that does not match the period in the likely supporting source passage. "
            f"Claim months={temporal_gate.get('claim_months')}, source-support months={temporal_gate.get('source_support_months')}; "
            f"claim quarters={temporal_gate.get('claim_quarters')}, source-support quarters={temporal_gate.get('source_support_quarters')}. "
            "A source about a different month/quarter cannot verify this period-specific claim; publication-date or unrelated period mentions elsewhere do not cure the mismatch."
        )
    system="""You are a strict claim-to-source verifier. Use ONLY the supplied source text. Return exactly one first-line verdict: SUPPORTED, CONTRADICTED, or INCONCLUSIVE. Then give 2-5 concise sentences explaining what the source actually says and what part of the claim is unsupported or contradicted. Do not use outside knowledge. A source being reputable does not make a claim true. TEMPORAL RULE: a period-specific claim is SUPPORTED only when the source verifies that same material month/quarter/year. A July observation does not verify an August claim; a publication date or unrelated August mention elsewhere on the page does not satisfy the claim period."""
    user=f"CLAIM:\n{claim}\n\nSOURCE URL:\n{source_url}\n\nSOURCE TEXT:\n{source_text[:30000]}"
    r=requests.post(f"{base_url}/chat/completions",headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},json={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"temperature":0.0},timeout=(10,timeout_seconds))
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
