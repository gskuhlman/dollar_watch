from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
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
        r = requests.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "dollar_watch/2.6"}, stream=True)
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
        r = requests.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "dollar_watch/2.6"})
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
        return {"ok": False, "text": "", "error": str(exc), **classify_source(url)}
