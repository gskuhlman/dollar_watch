from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
import re
import requests

PRIMARY_DOMAINS = {
    "treasury.gov", "home.treasury.gov", "fiscaldata.treasury.gov", "ticdata.treasury.gov", "treasurydirect.gov",
    "federalreserve.gov", "newyorkfed.org", "stlouisfed.org", "fred.stlouisfed.org",
    "imf.org", "data.imf.org", "api.imf.org", "bis.org", "cftc.gov", "publicreporting.cftc.gov",
    "whitehouse.gov", "commerce.gov", "ustr.gov", "sec.gov", "cbo.gov", "gao.gov",
    "mof.go.jp", "boj.or.jp", "ecb.europa.eu", "snb.ch", "bankofengland.co.uk", "dnb.nl",
    "pbc.gov.cn", "safe.gov.cn", "rbi.org.in", "brics2026.gov.in", "brics.br",
}
MAJOR_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "ft.com", "wsj.com", "bloomberg.com", "economist.com",
    "nytimes.com", "washingtonpost.com", "nikkei.com", "japantimes.co.jp",
}
RESEARCH_DOMAINS = {
    "gold.org", "worldbank.org", "oecd.org", "brookings.edu", "piie.com", "nber.org",
}


def canonical_verification_label(value: object, *, default: str = "UNKNOWN") -> str:
    """Normalize legacy/LLM verification labels to canonical evidence outcomes.

    Raw variants remain available to callers for audit, but analytical counts should use
    these canonical labels so typos such as ``CONTRICTED`` do not become a separate
    evidentiary category.
    """
    raw=str(value or "").strip().upper()
    if not raw:
        return default
    # Legacy/LLM outputs sometimes wrap the actual category, e.g.
    # ``VERDICT:_INCONCLUSIVE`` or ``RESULT: CONTRADICTED``. Strip only
    # recognized leading wrappers before punctuation compaction so the
    # evidence outcome is canonicalized rather than becoming a new category.
    unwrapped=raw
    wrapper_re=re.compile(r"^(?:VERDICT|RESULT|OUTCOME|LABEL|CLASSIFICATION)\s*[:=_-]+\s*", re.I)
    for _ in range(3):
        nxt=wrapper_re.sub("",unwrapped, count=1)
        if nxt == unwrapped:
            break
        unwrapped=nxt.strip()
    compact="".join(ch for ch in unwrapped if ch.isalnum())
    aliases={
        "SUPPORTED":"SUPPORTED",
        "STRUCTUREDVERIFIED":"STRUCTURED_VERIFIED",
        "CONTRADICTED":"CONTRADICTED",
        "CONTRICTED":"CONTRADICTED",
        "CONTRADICT":"CONTRADICTED",
        "INCONCLUSIVE":"INCONCLUSIVE",
        "UNKNOWN":"UNKNOWN",
    }
    if compact in aliases:
        return aliases[compact]
    normalized="_".join(unwrapped.replace("-"," ").split())
    return normalized or default


_MONTH_NAMES = {
    "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,"may":5,
    "jun":6,"june":6,"jul":7,"july":7,"aug":8,"august":8,"sep":9,"sept":9,"september":9,
    "oct":10,"october":10,"nov":11,"november":11,"dec":12,"december":12,
}
_MONTH_RE = re.compile(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b", re.I)
_QUARTER_RE = re.compile(r"\b(?:20\d{2}\s*)?Q([1-4])\b|\bQ([1-4])\s*(?:20\d{2})?\b", re.I)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_WORD_RE = re.compile(r"[A-Za-z0-9$%]+")
_TEMPORAL_STOP = {
    "the","and","for","with","from","that","this","into","says","said","claim","claims","report","reports",
    "source","according","official","officials","market","markets","month",
}


def _period_markers(text: str) -> dict:
    months={_MONTH_NAMES[m.group(1).lower().rstrip('.')] for m in _MONTH_RE.finditer(str(text or ''))}
    quarters={int(m.group(1) or m.group(2)) for m in _QUARTER_RE.finditer(str(text or ''))}
    years={int(x) for x in _YEAR_RE.findall(str(text or ''))}
    return {"months":months,"quarters":quarters,"years":years}


def _content_tokens_for_temporal_match(text: str) -> set[str]:
    toks={x.lower() for x in _WORD_RE.findall(str(text or ''))}
    month_words=set(_MONTH_NAMES)
    return {t for t in toks if len(t)>=3 and t not in _TEMPORAL_STOP and t not in month_words and not t.isdigit()}


def temporal_claim_source_mismatch(claim: str, source_text: str) -> dict:
    """Detect an explicit claim-period/source-period mismatch in likely supporting passages.

    This is intentionally conservative.  It only fires when the claim names a month/quarter,
    we can find source sentences with meaningful non-temporal claim overlap, and those candidate
    support sentences explicitly name a different period without naming the claimed period.
    Publication dates or unrelated month mentions elsewhere on the page are not enough.
    """
    cp=_period_markers(claim)
    if not cp["months"] and not cp["quarters"]:
        return {"mismatch":False,"reason":"NO_EXPLICIT_CLAIM_PERIOD"}
    core=_content_tokens_for_temporal_match(claim)
    nums=set(re.findall(r"\b\d+(?:\.\d+)?\s*(?:t|tonnes?|tons?|bn|billion|mn|million|%)?\b",str(claim or ''),re.I))
    segments=[x.strip() for x in re.split(r"[\n\r]+|(?<=[.!?])\s+",str(source_text or '')) if x.strip()]
    candidates=[]
    for seg in segments:
        stoks=_content_tokens_for_temporal_match(seg)
        overlap=core & stoks
        numeric=any(n.lower().replace(' ','') in seg.lower().replace(' ','') for n in nums) if nums else False
        if len(overlap)>=2 or (numeric and len(overlap)>=1):
            candidates.append((seg,overlap,_period_markers(seg)))
    if not candidates:
        return {"mismatch":False,"reason":"NO_SUPPORT_WINDOW"}
    src_months=set().union(*(x[2]["months"] for x in candidates))
    src_quarters=set().union(*(x[2]["quarters"] for x in candidates))
    month_mismatch=bool(cp["months"] and src_months and cp["months"].isdisjoint(src_months))
    quarter_mismatch=bool(cp["quarters"] and src_quarters and cp["quarters"].isdisjoint(src_quarters))
    mismatch=month_mismatch or quarter_mismatch
    return {
        "mismatch":mismatch,
        "reason":"CLAIM_SOURCE_PERIOD_MISMATCH" if mismatch else "PERIOD_COMPATIBLE_OR_AMBIGUOUS",
        "claim_months":sorted(cp["months"]),"source_support_months":sorted(src_months),
        "claim_quarters":sorted(cp["quarters"]),"source_support_quarters":sorted(src_quarters),
        "support_excerpt":candidates[0][0][:500],
    }


def summarize_verification_records(records: list[dict] | None, *, scope: str = "SUPPLIED_RECORD_SET", complete: bool = False) -> dict:
    """Deterministic verification accounting with canonical outcomes and raw-label audit.

    ``complete`` describes whether ``records`` covers the full intended population.
    Detailed prompt lists may be truncated while the storage-layer summaries use the full
    database population.
    """
    rows=list(records or [])
    verdict_counts={}
    raw_verdict_counts={}
    status_counts={}
    relevance_counts={}
    supported=[]
    contradicted=[]
    anomalies={}
    for r in rows:
        raw_verdict=str(r.get("verdict") or r.get("llm_verdict") or "UNKNOWN").strip().upper() or "UNKNOWN"
        verdict=canonical_verification_label(raw_verdict)
        raw_verdict_counts[raw_verdict]=raw_verdict_counts.get(raw_verdict,0)+1
        verdict_counts[verdict]=verdict_counts.get(verdict,0)+1
        if raw_verdict != verdict:
            anomalies[raw_verdict]={"canonical":verdict,"count":raw_verdict_counts[raw_verdict]}
        status=canonical_verification_label(r.get("status") or r.get("quarantine_status") or "UNKNOWN")
        relevance=canonical_verification_label(r.get("relevance_status") or "UNKNOWN")
        status_counts[status]=status_counts.get(status,0)+1
        relevance_counts[relevance]=relevance_counts.get(relevance,0)+1
        if verdict == "SUPPORTED":
            supported.append(str(r.get("claim") or ""))
        if verdict == "CONTRADICTED":
            contradicted.append(str(r.get("claim") or ""))
    total=len(rows)
    verdict_sum=sum(verdict_counts.values())
    status_sum=sum(status_counts.values())
    relevance_sum=sum(relevance_counts.values())
    return {
        "total":total,
        "scope":scope,
        "complete_population":bool(complete),
        "verdict_counts":verdict_counts,
        "raw_verdict_counts":raw_verdict_counts,
        "raw_label_anomalies":anomalies,
        "status_counts":status_counts,
        "relevance_counts":relevance_counts,
        "verdict_count_sum":verdict_sum,
        "status_count_sum":status_sum,
        "relevance_count_sum":relevance_sum,
        "verdict_counts_reconcile":verdict_sum == total,
        "status_counts_reconcile":status_sum == total,
        "relevance_counts_reconcile":relevance_sum == total,
        "accounting_reconciles":verdict_sum == total and status_sum == total and relevance_sum == total,
        "supported_claims":[c for c in supported if c][:10],
        "contradicted_claims":[c for c in contradicted if c][:10],
        "counting_policy":"canonical verdict/status/relevance counts each reconcile independently to the declared population; raw-label anomalies are audit metadata, not separate evidence categories",
    }


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _matches(host: str, domains: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def classify_source(url: str) -> dict:
    host = _host(url)
    if not host:
        return {"source_tier": "UNSOURCED", "source_weight": 0.0, "host": ""}
    if _matches(host, PRIMARY_DOMAINS):
        return {"source_tier": "PRIMARY", "source_weight": 1.0, "host": host}
    if _matches(host, MAJOR_NEWS_DOMAINS):
        return {"source_tier": "MAJOR_NEWS", "source_weight": 0.85, "host": host}
    if _matches(host, RESEARCH_DOMAINS):
        return {"source_tier": "RESEARCH", "source_weight": 0.75, "host": host}
    return {"source_tier": "OTHER", "source_weight": 0.45, "host": host}


def check_source_url(url: str, timeout: int = 8) -> dict:
    """Check reachability and classify a source. Reachability does NOT verify a claim."""
    info = classify_source(url)
    if not url:
        return {**info, "reachable": False, "http_status": None, "note": "No source URL supplied."}
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "dollar_watch/3.2"}, stream=True)
        ok = 200 <= r.status_code < 400
        return {
            **info,
            "reachable": ok,
            "http_status": int(r.status_code),
            "final_url": r.url,
            "note": "URL reachable; claim content still requires human/LLM verification." if ok else "URL returned an error status.",
        }
    except Exception as exc:
        return {**info, "reachable": False, "http_status": None, "note": str(exc)}


def effective_evidence_value(value: float, verification_status: str, source_url: str = "") -> float:
    """Only VERIFIED evidence alters regime math. Source quality scales its influence."""
    status = (verification_status or "UNVERIFIED").upper()
    if status != "VERIFIED":
        return 0.0
    weight = classify_source(source_url).get("source_weight", 0.0)
    # A human-verified unsourced claim should not silently alter hard scores.
    return float(value) * float(weight)


def provenance_label(kind: str) -> str:
    labels = {
        "data": "DATA-DERIVED",
        "analyst": "ANALYST-ENTERED",
        "ai": "AI-INFERRED",
        "verified_news": "VERIFIED NEWS",
        "headline": "HEADLINE TRIAGE",
    }
    return labels.get(kind, kind.upper())


def fetch_source_text(url: str, max_chars: int = 30000, timeout: int = 12) -> dict:
    """Fetch readable source text for claim-checking. This is evidence assistance, not verification."""
    if not url:
        return {"ok": False, "text": "", "error": "No URL supplied", **classify_source(url)}
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "dollar_watch/3.2"})
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        raw = r.text
        if "html" in ctype or "<html" in raw[:1000].lower():
            from html.parser import HTMLParser
            class _Text(HTMLParser):
                def __init__(self):
                    super().__init__(); self.parts=[]; self.skip=0
                def handle_starttag(self, tag, attrs):
                    if tag in {"script","style","noscript","svg"}: self.skip += 1
                def handle_endtag(self, tag):
                    if tag in {"script","style","noscript","svg"} and self.skip: self.skip -= 1
                def handle_data(self, data):
                    if not self.skip and data.strip(): self.parts.append(data.strip())
            parser=_Text(); parser.feed(raw)
            raw="\n".join(parser.parts)
        text="\n".join(line.strip() for line in raw.splitlines() if line.strip())[:max_chars]
        return {"ok": True, "text": text, "final_url": r.url, "http_status": r.status_code, **classify_source(r.url)}
    except Exception as exc:
        # V3.2: canonical official pages occasionally return transient 503/403 responses.
        # A dated last-known official cache is preferable to converting that network event into
        # "no evidence". The fallback is explicit and remains auditable in the UI.
        try:
            from .official_policy import cached_official_source_text
            cached = cached_official_source_text(url)
            if cached.get("ok"):
                text = str(cached.get("text") or "")[:max_chars]
                return {
                    "ok": True, "text": text, "final_url": cached.get("final_url") or url,
                    "http_status": None, "cache_fallback": True, "cache_kind": cached.get("cache_kind"),
                    "cached_at": cached.get("cached_at"), "live_fetch_error": str(exc),
                    **classify_source(cached.get("final_url") or url),
                }
        except Exception:
            pass
        return {"ok": False, "text": "", "error": str(exc), **classify_source(url)}
