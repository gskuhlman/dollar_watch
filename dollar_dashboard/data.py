from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Dict, Iterable

import numpy as np
import pandas as pd
import requests
try:
    import yfinance as yf
except ImportError:  # allows offline/unit tests of non-market collectors
    yf = None

UA = {"User-Agent": "dollar_watch/2.2 (+local research dashboard)"}

MARKET_TICKERS = {
    "DXY": "DX-Y.NYB",
    "Gold": "GC=F",
    "Bitcoin": "BTC-USD",
    "US Equities": "SPY",
    "Developed ex-US Equities": "EFA",
    "Long Treasuries ETF": "TLT",
    "TIPS ETF": "TIP",
    "Gold ETF": "GLD",
    "Broad Commodities": "DBC",
    "Swiss Franc ETF": "FXF",
    "USD ETF": "UUP",
    "Oil": "CL=F",
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "USDCHF": "CHF=X",
    "USDCNY": "CNY=X",
}

FRED_SERIES = {
    "Broad Dollar Index": "DTWEXBGS",
    "2Y Treasury": "DGS2",
    "10Y Treasury": "DGS10",
    "30Y Treasury": "DGS30",
    "5Y TIPS real yield": "DFII5",
    "10Y TIPS real yield": "DFII10",
    "10Y breakeven inflation": "T10YIE",
    "SOFR": "SOFR",
    "SOFR 99th percentile": "SOFR99",
    "IORB": "IORB",
    "Tri-Party General Collateral Rate": "TGCRRATE",
    "TGCR 99th percentile": "TGCR99THPERCENTILE",
    "Fed balance sheet (millions)": "WALCL",
    "Fed Treasury holdings (millions)": "TREAST",
    "Fed MBS holdings (millions)": "WSHOMCB",
    "Fed liquidity-facility loans (millions)": "WLCFLL",
    "ON RRP (billions)": "RRPONTSYD",
    "VIX": "VIXCLS",
    "High-yield spread": "BAMLH0A0HYM2",
    "10Y term premium": "THREEFYTP10",
    "5Y5Y forward inflation": "T5YIFR",
    "10Y-2Y curve": "T10Y2Y",
    "10Y-3M curve": "T10Y3M",
    "Financial Conditions Index": "NFCI",
    "Reserve balances (billions)": "WRESBAL",
    "Treasury General Account (billions)": "WTREGEN",
    "Central bank liquidity swaps (millions)": "SWPT",
    "Foreign official Treasury holdings (millions)": "FORTREASPOS99990",
    "Foreign custody UST weekly (millions)": "WMTSEC1",
    "Foreign custody UST YoY change (millions)": "RESH4FGXAWXCH52NWW",
    "Foreign custody UST WoW change (millions)": "RESH4FGXAWXCH1NWW",
}


def _returns(s: pd.Series) -> dict:
    s = s.dropna()
    if s.empty:
        return {k: np.nan for k in ["last", "1d", "5d", "1m", "3m", "1y"]}
    windows = {"1d": 1, "5d": 5, "1m": 21, "3m": 63, "1y": 252}
    out = {"last": float(s.iloc[-1])}
    for name, n in windows.items():
        if len(s) > n and s.iloc[-n - 1] != 0:
            out[name] = float(s.iloc[-1] / s.iloc[-n - 1] - 1)
        else:
            out[name] = np.nan
    return out


def fetch_market_history(period: str = "2y") -> tuple[pd.DataFrame, pd.DataFrame]:
    if yf is None:
        raise ImportError("yfinance is required for the market-price collector; install requirements.txt")
    tickers = list(MARKET_TICKERS.values())
    raw = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"].copy()
    else:
        close = raw[["Close"]].copy()
        close.columns = [tickers[0]]
    inverse = {v: k for k, v in MARKET_TICKERS.items()}
    close = close.rename(columns=inverse)
    summary = pd.DataFrame({name: _returns(close[name]) for name in close.columns}).T
    return close, summary


def fetch_fred_series(series_id: str, start: str | None = None) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    if start:
        url += f"&cosd={start}"
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    if len(df.columns) < 2:
        raise ValueError(f"Unexpected FRED response for {series_id}")
    date_col, value_col = df.columns[0], df.columns[1]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    # A source occasionally exposes a dated observation that is ahead of the machine clock.
    # Do not silently let a future row become the dashboard's 'latest' historical observation.
    # Data-health also flags any source-date-ahead condition that survives another collector.
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    df = df[df[date_col].isna() | (df[date_col] <= today)]
    s = df.dropna().set_index(date_col)[value_col].sort_index()
    s.name = series_id
    return s


def fetch_fred_bundle(start: str = "2024-01-01") -> tuple[pd.DataFrame, pd.DataFrame]:
    series: Dict[str, pd.Series] = {}
    for label, sid in FRED_SERIES.items():
        try:
            series[label] = fetch_fred_series(sid, start=start)
        except Exception:
            series[label] = pd.Series(dtype=float, name=sid)
    if not series:
        return pd.DataFrame(), pd.DataFrame()
    hist = pd.concat(series, axis=1).sort_index()
    # Repo-plumbing spreads. Percent units: 0.10 = 10bp.
    if "SOFR" in hist.columns and "IORB" in hist.columns:
        hist["SOFR-IORB spread"] = hist["SOFR"] - hist["IORB"]
    if "SOFR 99th percentile" in hist.columns and "IORB" in hist.columns:
        hist["SOFR99-IORB spread"] = hist["SOFR 99th percentile"] - hist["IORB"]
    if "Tri-Party General Collateral Rate" in hist.columns and "IORB" in hist.columns:
        hist["TGCR-IORB spread"] = hist["Tri-Party General Collateral Rate"] - hist["IORB"]
    if "TGCR 99th percentile" in hist.columns and "Tri-Party General Collateral Rate" in hist.columns:
        hist["TGCR dispersion"] = hist["TGCR 99th percentile"] - hist["Tri-Party General Collateral Rate"]
    # H.4.1 asset decomposition. This makes balance-sheet changes explainable instead of
    # treating WALCL as a monolith. Values are all millions of dollars. The residual is
    # deliberately labeled residual because it includes asset categories not modeled here.
    asset_cols = [
        "Fed Treasury holdings (millions)",
        "Fed MBS holdings (millions)",
        "Fed liquidity-facility loans (millions)",
        "Central bank liquidity swaps (millions)",
    ]
    if "Fed balance sheet (millions)" in hist.columns:
        available = [c for c in asset_cols if c in hist.columns]
        if available:
            hist["Fed identified assets (millions)"] = hist[available].sum(axis=1, min_count=1)
            hist["Fed other assets residual (millions)"] = hist["Fed balance sheet (millions)"] - hist["Fed identified assets (millions)"]
    rows = {}
    for label in hist.columns:
        s = hist[label].dropna()
        if s.empty:
            rows[label] = {"last": np.nan, "1w_change": np.nan, "1m_change": np.nan, "3m_change": np.nan, "1y_change": np.nan}
            continue
        def delta_days(days: int):
            # Calendar-based comparison works across daily, weekly and monthly FRED series.
            # Observation-count windows badly overstate the lookback on H.4.1 weekly series.
            target = s.index[-1] - pd.Timedelta(days=days)
            prior = s.loc[s.index <= target]
            if prior.empty:
                return np.nan
            return float(s.iloc[-1] - prior.iloc[-1])
        rows[label] = {
            "last": float(s.iloc[-1]),
            "1w_change": delta_days(7),
            "1m_change": delta_days(30),
            "3m_change": delta_days(91),
            "1y_change": delta_days(365),
        }
    return hist, pd.DataFrame(rows).T



TREASURY_AUCTIONS_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
TREASURY_UPCOMING_AUCTIONS_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/upcoming_auctions"

# FiscalData's auction table contains long-standing legacy spellings (for example
# announcemt_date) and has changed some display/data-dictionary names over time.
# V2.2 deliberately fetches the returned schema rather than sending a brittle fields= list
# that causes the entire request to fail with HTTP 400 when one name is wrong.
_AUCTION_ALIASES = {
    "record_date": ["record_date"],
    "cusip": ["cusip"],
    "security_type": ["security_type", "type"],
    "security_term": ["security_term", "security_term_week_year", "term"],
    "original_security_term": ["original_security_term"],
    "announcement_date": ["announcement_date", "announcemt_date"],
    "auction_date": ["auction_date"],
    "issue_date": ["issue_date"],
    "reopening": ["reopening"],
    "bid_to_cover_ratio": ["bid_to_cover_ratio"],
    "comp_accepted": ["comp_accepted", "competitive_accepted_amt", "competitive_accepted"],
    "total_accepted": ["total_accepted", "total_accepted_amt"],
    "primary_dealer_accepted": ["primary_dealer_accepted", "primary_dealer_accepted_amt"],
    "direct_bidder_accepted": ["direct_bidder_accepted", "direct_bidder_accepted_amt"],
    "indirect_bidder_accepted": ["indirect_bidder_accepted", "indirect_bidder_accepted_amt"],
    "dealer_share_api": ["primary_dealer_pct_accepted"],
    "direct_share_api": ["direct_bid_pct_accepted", "direct_bidder_pct_accepted"],
    "indirect_share_api": ["indirect_bid_pct_accepted", "indirect_bidder_pct_accepted"],
}


def _fiscaldata_pages(url: str, params: dict, page_size: int = 1000, max_pages: int = 20) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    meta: dict = {}
    page = 1
    while page <= max_pages:
        q = dict(params)
        q["page[size]"] = min(int(page_size), 10000)
        q["page[number]"] = page
        q.setdefault("format", "json")
        r = requests.get(url, params=q, headers=UA, timeout=25)
        if r.status_code == 400:
            # Return enough context to make a future schema/API change diagnosable from Data Health.
            body = (r.text or "")[:1200]
            raise requests.HTTPError(f"FiscalData HTTP 400 for {r.url}: {body}", response=r)
        r.raise_for_status()
        obj = r.json()
        batch = obj.get("data", []) or []
        meta = obj.get("meta", {}) or {}
        rows.extend(batch)
        total = meta.get("total-count", meta.get("total_count"))
        try:
            total = int(total)
        except Exception:
            total = None
        if not batch or len(batch) < q["page[size]"] or (total is not None and len(rows) >= total):
            break
        page += 1
    return rows, meta


def _first_existing(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    for name in aliases:
        if name in df.columns:
            return df[name]
    return pd.Series([np.nan] * len(df), index=df.index, dtype="object")


def _normalize_auction_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=raw.index)
    for canonical, aliases in _AUCTION_ALIASES.items():
        out[canonical] = _first_existing(raw, aliases)
    numeric = [
        "bid_to_cover_ratio", "comp_accepted", "total_accepted",
        "primary_dealer_accepted", "direct_bidder_accepted", "indirect_bidder_accepted",
        "dealer_share_api", "direct_share_api", "indirect_share_api",
    ]
    for c in numeric:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    for c in ["record_date", "announcement_date", "auction_date", "issue_date"]:
        out[c] = pd.to_datetime(out[c], errors="coerce")

    # Prefer direct percentage fields when FiscalData supplies them. Otherwise calculate
    # bidder shares against competitive accepted tenders, matching Treasury result PDFs.
    denom = out["comp_accepted"].replace(0, np.nan)
    out["dealer_share"] = out["dealer_share_api"]
    out["direct_share"] = out["direct_share_api"]
    out["indirect_share"] = out["indirect_share_api"]
    for share, accepted in [
        ("dealer_share", "primary_dealer_accepted"),
        ("direct_share", "direct_bidder_accepted"),
        ("indirect_share", "indirect_bidder_accepted"),
    ]:
        calc = 100.0 * out[accepted] / denom
        out[share] = out[share].where(out[share].notna(), calc)

    orig = out["original_security_term"].astype("string")
    term = out["security_term"].astype("string")
    out["term_key"] = orig.where(orig.notna() & orig.str.len().gt(0) & ~orig.str.lower().eq("null"), term)
    return out


def fetch_treasury_auctions(start: str = "2024-01-01", page_size: int = 1000) -> pd.DataFrame:
    """Fetch official Treasury auction results without a brittle fields= query.

    FiscalData returns the full auction schema; V2.2 normalizes legacy/current aliases locally.
    This prevents a single renamed or misspelled API field from turning the auction channel off.
    """
    params = {
        "filter": f"auction_date:gte:{start}",
        "sort": "-auction_date",
    }
    data, _meta = _fiscaldata_pages(TREASURY_AUCTIONS_URL, params, page_size=page_size)
    return _normalize_auction_frame(pd.DataFrame(data))


def fetch_upcoming_treasury_auctions(days: int = 35, page_size: int = 500) -> pd.DataFrame:
    """Fetch Treasury's dedicated upcoming-auctions table and normalize it for the UI."""
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    end = today + pd.Timedelta(days=days)
    params = {
        "filter": f"auction_date:gte:{today.date()},auction_date:lte:{end.date()}",
        "sort": "auction_date",
    }
    data, _meta = _fiscaldata_pages(TREASURY_UPCOMING_AUCTIONS_URL, params, page_size=page_size, max_pages=5)
    return _normalize_auction_frame(pd.DataFrame(data))


def summarize_auction_stress(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Compare the latest major coupon auction for each tenor with its prior 8 auctions.

    This is not an auction-tail measure because a live when-issued yield is not part of the
    FiscalData auction result. It measures demand/absorption using bid-to-cover and bidder mix.
    """
    if df.empty or "term_key" not in df.columns:
        return pd.DataFrame(), 0.0
    major = ["2-Year", "3-Year", "5-Year", "7-Year", "10-Year", "20-Year", "30-Year"]
    rows = []
    stress_values = []
    for term in major:
        g = df[df["term_key"].astype(str).eq(term)].sort_values("auction_date", ascending=False)
        if len(g) < 3:
            continue
        latest = g.iloc[0]
        prior = g.iloc[1:9]
        btc = latest.get("bid_to_cover_ratio")
        btc_avg = prior["bid_to_cover_ratio"].mean() if "bid_to_cover_ratio" in prior else np.nan
        indirect = latest.get("indirect_share")
        indirect_avg = prior["indirect_share"].mean() if "indirect_share" in prior else np.nan
        dealer = latest.get("dealer_share")
        dealer_avg = prior["dealer_share"].mean() if "dealer_share" in prior else np.nan
        stress = 0.0
        reasons = []
        if pd.notna(btc) and pd.notna(btc_avg):
            gap = btc - btc_avg
            if gap < -0.10: stress += 15; reasons.append(f"BTC {gap:.2f} below prior avg")
            if gap < -0.20: stress += 10
        if pd.notna(indirect) and pd.notna(indirect_avg):
            gap = indirect - indirect_avg
            if gap < -5: stress += 15; reasons.append(f"indirect share {gap:.1f}pp vs prior avg")
            if gap < -10: stress += 10
        if pd.notna(dealer) and pd.notna(dealer_avg):
            gap = dealer - dealer_avg
            if gap > 5: stress += 15; reasons.append(f"dealer share +{gap:.1f}pp vs prior avg")
            if gap > 10: stress += 10
        # Longer-tenor weak demand is more informative for fiscal-duration risk.
        multiplier = 1.25 if term in ["10-Year", "20-Year", "30-Year"] else 1.0
        stress = min(100.0, stress * multiplier)
        stress_values.append(stress)
        rows.append({
            "term": term,
            "auction_date": latest.get("auction_date"),
            "bid_to_cover": btc,
            "prior8_btc": btc_avg,
            "indirect_share_pct": indirect,
            "prior8_indirect_pct": indirect_avg,
            "dealer_share_pct": dealer,
            "prior8_dealer_pct": dealer_avg,
            "stress": stress,
            "reasons": "; ".join(reasons),
        })
    out = pd.DataFrame(rows)
    # Use a blend of mean and worst tenor to avoid one odd auction dominating while still flagging acute weakness.
    overall = 0.0 if not stress_values else min(100.0, 0.65*float(np.mean(stress_values)) + 0.35*float(np.max(stress_values)))
    return out, overall


def summarize_upcoming_auctions(df: pd.DataFrame, days: int = 21) -> pd.DataFrame:
    if df is None or df.empty or "auction_date" not in df.columns:
        return pd.DataFrame()
    today = pd.Timestamp.now(tz=None).normalize()
    end = today + pd.Timedelta(days=days)
    d = df.copy()
    d["auction_date"] = pd.to_datetime(d["auction_date"], errors="coerce").dt.tz_localize(None)
    d = d[(d["auction_date"] >= today) & (d["auction_date"] <= end)]
    if d.empty:
        return d
    major = ["2-Year", "3-Year", "5-Year", "7-Year", "10-Year", "20-Year", "30-Year"]
    if "term_key" in d.columns:
        d = d[d["term_key"].astype(str).isin(major)]
    cols = [c for c in ["announcement_date","auction_date","issue_date","term_key","security_type","reopening","cusip"] if c in d.columns]
    return d[cols].sort_values("auction_date").drop_duplicates(subset=[c for c in ["auction_date","term_key","cusip"] if c in cols])

def market_snapshot() -> dict:
    close, market = fetch_market_history()
    fred_hist, fred = fetch_fred_bundle()
    try:
        auctions = fetch_treasury_auctions()
        auction_table, auction_stress = summarize_auction_stress(auctions)
    except Exception:
        auction_table, auction_stress = pd.DataFrame(), 0.0
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_summary": market.replace({np.nan: None}).to_dict(orient="index") if not market.empty else {},
        "fred_summary": fred.replace({np.nan: None}).to_dict(orient="index") if not fred.empty else {},
        "auction_stress_auto": auction_stress,
        "auction_summary": auction_table.replace({np.nan: None}).to_dict(orient="records") if not auction_table.empty else [],
    }
