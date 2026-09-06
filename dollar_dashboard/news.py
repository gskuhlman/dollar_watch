from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import requests

UA = {"User-Agent": "DollarCrisisDashboard/2.0"}

DEFAULT_QUERIES = {
    "US policy": 'Treasury Bessent dollar intervention OR dollar policy OR Treasury buyback OR Exchange Stabilization Fund',
    "Fed": 'Federal Reserve Warsh rates inflation dollar Fed independence balance sheet',
    "Trump": 'Trump dollar interest rates tariffs stablecoin USD1 World Liberty Financial',
    "Miran": 'Stephen Miran dollar reserve currency tariffs Treasury currency adjustment',
    "Treasury market": 'Treasury auction weak demand repo basis trade market liquidity term premium',
    "BRICS": 'BRICS de-dollarization local currency settlement payment system CBDC cross border payments',
    "China": 'China Treasury holdings yuan internationalization CIPS dollar reserves gold',
    "Japan": 'Japan Treasury holdings yen intervention BOJ dollar reserves',
    "Gold reserves": 'central bank gold purchases reserves dollar World Gold Council',
    "Funding stress": 'repo funding stress dollar shortage swap lines basis trade margin call Treasury liquidity',
    "Stablecoins": 'stablecoin Treasury demand GENIUS Act USD1 USDT USDC reserves market cap',
    "Commodity settlement": 'oil yuan settlement non dollar commodity invoicing Saudi China currency',
    "Institutional risk": 'Fed independence Treasury default debt ceiling capital controls foreign asset tax dollar',
}

KEYWORDS = {
    "policy_devaluation": {
        "positive": ["weaker dollar", "dollar too strong", "fx intervention", "buy yen", "buy euro", "rate cuts", "currency realignment", "plaza", "exchange stabilization fund", "currency adjustment"],
        "negative": ["strong dollar", "rate hike", "hawkish", "price stability", "balance sheet reduction"],
    },
    "external_dedollarization": {
        "positive": ["de-dollarization", "dedollarization", "local currency", "cips", "brics payment", "cbdc", "gold reserves", "reduce treasury holdings", "yuan settlement", "non-dollar", "alternative payment"],
        "negative": ["dollar reserves rise", "treasury purchases rise", "dollar dominance", "dollar settlement rises"],
    },
    "funding_stress": {
        "positive": ["repo stress", "funding stress", "auction tail", "weak auction", "liquidity stress", "margin call", "dollar shortage", "basis trade", "swap line", "market depth"],
        "negative": ["strong auction", "ample liquidity", "repo stable", "market depth improves"],
    },
    "dollar_support": {
        "positive": ["stablecoin treasury demand", "dollar stablecoin", "dollar dominance", "capital inflow", "treasury demand", "rate hike", "hawkish fed", "dollar funding shortage"],
        "negative": ["capital outflow", "reserve diversification", "treasury selling"],
    },
    "institutional_stress": {
        "positive": ["fed independence", "default risk", "debt ceiling", "capital controls", "foreign asset tax", "treasury user fee", "constitutional crisis", "fiscal dominance"],
        "negative": ["institutional stability", "credible fiscal", "independent fed"],
    },
}

HIGH_QUALITY_SOURCES = {
    "Reuters": 1.7, "Bloomberg": 1.6, "Financial Times": 1.6, "The Wall Street Journal": 1.5,
    "U.S. Department of the Treasury": 1.8, "Federal Reserve": 1.8, "Board of Governors of the Federal Reserve System": 1.8,
    "International Monetary Fund": 1.7, "Bank for International Settlements": 1.7, "World Gold Council": 1.4,
    "Associated Press": 1.4,
}


def _google_news_rss(query: str):
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    return feedparser.parse(r.content)


def _published_dt(text: str):
    if not text:
        return pd.NaT
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return pd.Timestamp(dt)
    except Exception:
        return pd.to_datetime(text, utc=True, errors="coerce")


def fetch_news(queries: dict | None = None, per_query: int = 10) -> pd.DataFrame:
    queries = queries or DEFAULT_QUERIES
    records = []
    now = pd.Timestamp.now(tz="UTC")
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
            dt = _published_dt(published)
            age_hours = None if pd.isna(dt) else max(0.0, float((now - dt).total_seconds() / 3600))
            records.append({
                "bucket": bucket,
                "title": getattr(e, "title", ""),
                "source": source,
                "published": published,
                "published_dt": dt,
                "age_hours": age_hours,
                "link": getattr(e, "link", ""),
            })
    if not records:
        return pd.DataFrame(columns=["bucket", "title", "source", "published", "published_dt", "age_hours", "link"])
    df = pd.DataFrame(records).drop_duplicates(subset=["title"])
    return df.sort_values("published_dt", ascending=False, na_position="last").reset_index(drop=True)


def _source_weight(source: str) -> float:
    if not source:
        return 1.0
    for name, weight in HIGH_QUALITY_SOURCES.items():
        if name.lower() in source.lower():
            return weight
    return 1.0


def _recency_weight(age_hours) -> float:
    if age_hours is None or pd.isna(age_hours):
        return 0.8
    if age_hours <= 72:
        return 1.4
    if age_hours <= 168:
        return 1.15
    if age_hours <= 24 * 30:
        return 0.8
    return 0.45


def classify_news(df: pd.DataFrame) -> dict:
    raw_scores = {k: 0.0 for k in KEYWORDS}
    hits = {k: [] for k in KEYWORDS}
    if df.empty:
        return {"scores": {k: 0 for k in KEYWORDS}, "weighted_scores": raw_scores, "hits": hits}
    for _, row in df.iterrows():
        text = f"{row.get('title','')} {row.get('bucket','')}".lower()
        quality = _source_weight(str(row.get("source", "")))
        recency = _recency_weight(row.get("age_hours"))
        weight = quality * recency
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
                weighted = delta * weight
                raw_scores[category] += weighted
                hits[category].append({
                    "title": row.get("title", ""), "source": row.get("source", ""),
                    "delta": delta, "weighted_delta": round(weighted, 2), "matched": matched,
                })
    # Compress to a range similar to V1 so one week of headlines cannot dominate hard market data.
    scores = {k: int(round(max(-10, min(10, v)))) for k, v in raw_scores.items()}
    return {"scores": scores, "weighted_scores": {k: round(v, 2) for k, v in raw_scores.items()}, "hits": hits}
