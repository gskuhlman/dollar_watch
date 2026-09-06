from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import requests

UA = {"User-Agent": "DollarCrisisDashboard/0.1"}

DEFAULT_QUERIES = {
    "US policy": 'Treasury Bessent dollar intervention OR dollar policy OR Treasury buyback',
    "Fed": 'Federal Reserve Warsh rates inflation dollar Fed independence',
    "Trump": 'Trump dollar interest rates tariffs stablecoin USD1',
    "Miran": 'Stephen Miran dollar reserve currency tariffs Treasury',
    "BRICS": 'BRICS de-dollarization local currency settlement payment system CBDC',
    "China": 'China Treasury holdings yuan internationalization CIPS dollar reserves',
    "Gold reserves": 'central bank gold purchases reserves dollar',
    "Funding stress": 'Treasury auction weak demand repo funding stress dollar shortage',
    "Stablecoins": 'stablecoin Treasury demand GENIUS Act USD1 USDT USDC reserves',
}

KEYWORDS = {
    "policy_devaluation": {
        "positive": ["weaker dollar", "dollar too strong", "fx intervention", "buy yen", "buy euro", "rate cuts", "currency realignment", "plaza", "exchange stabilization fund"],
        "negative": ["strong dollar", "rate hike", "hawkish", "price stability"],
    },
    "external_dedollarization": {
        "positive": ["de-dollarization", "dedollarization", "local currency", "cips", "brics payment", "cbdc", "gold reserves", "reduce treasury holdings", "yuan settlement", "non-dollar"],
        "negative": ["dollar reserves rise", "treasury purchases rise", "dollar dominance"],
    },
    "funding_stress": {
        "positive": ["repo stress", "funding stress", "auction tail", "weak auction", "liquidity stress", "margin call", "dollar shortage", "basis trade"],
        "negative": ["strong auction", "ample liquidity", "repo stable"],
    },
    "dollar_support": {
        "positive": ["stablecoin treasury demand", "dollar stablecoin", "dollar dominance", "capital inflow", "treasury demand", "rate hike", "hawkish fed"],
        "negative": ["capital outflow", "reserve diversification"],
    },
}


def _google_news_rss(query: str):
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    return feedparser.parse(r.content)


def fetch_news(queries: dict | None = None, per_query: int = 8) -> pd.DataFrame:
    queries = queries or DEFAULT_QUERIES
    records = []
    for bucket, q in queries.items():
        try:
            feed = _google_news_rss(q)
        except Exception:
            continue
        for e in feed.entries[:per_query]:
            source = ""
            if hasattr(e, "source") and getattr(e.source, "title", None):
                source = e.source.title
            published = getattr(e, "published", "")
            records.append({
                "bucket": bucket,
                "title": getattr(e, "title", ""),
                "source": source,
                "published": published,
                "link": getattr(e, "link", ""),
            })
    if not records:
        return pd.DataFrame(columns=["bucket", "title", "source", "published", "link"])
    df = pd.DataFrame(records).drop_duplicates(subset=["title"])
    return df.reset_index(drop=True)


def classify_news(df: pd.DataFrame) -> dict:
    scores = {k: 0 for k in KEYWORDS}
    hits = {k: [] for k in KEYWORDS}
    if df.empty:
        return {"scores": scores, "hits": hits}
    for _, row in df.iterrows():
        text = f"{row.get('title','')} {row.get('bucket','')}".lower()
        for category, vocab in KEYWORDS.items():
            delta = 0
            matched = []
            for kw in vocab["positive"]:
                if kw in text:
                    delta += 1
                    matched.append("+" + kw)
            for kw in vocab["negative"]:
                if kw in text:
                    delta -= 1
                    matched.append("-" + kw)
            if delta:
                scores[category] += delta
                hits[category].append({"title": row.get("title", ""), "delta": delta, "matched": matched})
    return {"scores": scores, "hits": hits}
