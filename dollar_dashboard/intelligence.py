from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "DollarCrisisDashboard/2.0 (+local research dashboard)"}

CFTC_DATASET = "gpe5-46if"  # Traders in Financial Futures - futures only
CFTC_ENDPOINTS = [
    f"https://publicreporting.cftc.gov/resource/{CFTC_DATASET}.json",
    f"https://publicreportinghub.cftc.gov/resource/{CFTC_DATASET}.json",
]

TIC_MFH_URL = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.txt"
STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoins"
STABLECOIN_CHART_URL = "https://stablecoins.llama.fi/stablecoincharts/all"

CFTC_PATTERNS = {
    "Euro FX": ["EURO FX"],
    "Japanese Yen": ["JAPANESE YEN"],
    "Swiss Franc": ["SWISS FRANC"],
    "Dollar Index": ["DOLLAR INDEX", "USD INDEX"],
}


def _num(v: Any) -> float:
    try:
        if v is None or v == "":
            return np.nan
        return float(v)
    except Exception:
        return np.nan


def _percentile_rank(values: pd.Series, current: float) -> float:
    s = pd.to_numeric(values, errors="coerce").dropna()
    if s.empty or pd.isna(current):
        return np.nan
    return float((s <= current).mean() * 100.0)


def fetch_cftc_tff(years: int = 3, limit: int = 50000) -> pd.DataFrame:
    """Fetch recent CFTC Traders in Financial Futures positioning.

    The call intentionally uses the official public Socrata endpoint and no API key.
    If the public-reporting domain changes, a second official host is tried.
    """
    start = (datetime.now(timezone.utc) - timedelta(days=365 * years + 35)).date().isoformat()
    fields = [
        "report_date_as_yyyy_mm_dd", "commodity_group_name", "commodity_name",
        "contract_market_name", "cftc_contract_market_code", "open_interest_all",
        "dealer_positions_long_all", "dealer_positions_short_all",
        "asset_mgr_positions_long", "asset_mgr_positions_short",
        "lev_money_positions_long", "lev_money_positions_short",
    ]
    base_params = {
        "$select": ",".join(fields),
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": limit,
    }
    # Public CFTC vintages have used slightly different capitalization for the group field.
    # Try the narrow query first, then fall back to all recent TFF rows and filter locally.
    wheres = [
        f"report_date_as_yyyy_mm_dd >= '{start}T00:00:00.000' AND commodity_group_name='Financial'",
        f"report_date_as_yyyy_mm_dd >= '{start}T00:00:00.000'",
    ]
    last_err: Exception | None = None
    for url in CFTC_ENDPOINTS:
        for where in wheres:
            try:
                params = dict(base_params); params["$where"] = where
                r = requests.get(url, params=params, headers=UA, timeout=25)
                r.raise_for_status()
                data = r.json()
                df = pd.DataFrame(data)
                if df.empty:
                    continue
                if "commodity_group_name" in df.columns:
                    local = df[df["commodity_group_name"].astype(str).str.contains("financial", case=False, na=False)]
                    if not local.empty:
                        df = local
                df["report_date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"], errors="coerce")
                numeric = [
                    "open_interest_all", "dealer_positions_long_all", "dealer_positions_short_all",
                    "asset_mgr_positions_long", "asset_mgr_positions_short",
                    "lev_money_positions_long", "lev_money_positions_short",
                ]
                for c in numeric:
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                return df.sort_values("report_date")
            except Exception as exc:
                last_err = exc
    if last_err:
        raise last_err
    return pd.DataFrame()


def summarize_cftc_fx(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Summarize leveraged-money and asset-manager FX positioning.

    A high pressure score means positioning is more consistent with broad USD downside.
    Foreign-currency futures are quoted as foreign currency per dollar exposure, so long
    EUR/JPY/CHF futures are treated as dollar-bearish. Dollar-index longs are inverted.
    """
    if df.empty:
        return pd.DataFrame(), 0.0
    rows: list[dict[str, Any]] = []
    pressure_parts: list[float] = []
    for label, patterns in CFTC_PATTERNS.items():
        mask = pd.Series(False, index=df.index)
        text = (df.get("commodity_name", "").fillna("").astype(str) + " " + df.get("contract_market_name", "").fillna("").astype(str)).str.upper()
        for p in patterns:
            mask = mask | text.str.contains(p, regex=False)
        g = df[mask].copy()
        if g.empty:
            continue
        latest_date = g["report_date"].max()
        candidates = g[g["report_date"].eq(latest_date)].copy()
        if candidates.empty:
            continue
        if "open_interest_all" in candidates.columns:
            latest = candidates.sort_values("open_interest_all", ascending=False).iloc[0]
        else:
            latest = candidates.iloc[0]
        code = str(latest.get("cftc_contract_market_code", ""))
        hist = g[g["cftc_contract_market_code"].astype(str).eq(code)].copy() if code else g
        hist = hist.sort_values("report_date")
        hist["lev_net"] = hist["lev_money_positions_long"] - hist["lev_money_positions_short"]
        hist["asset_net"] = hist["asset_mgr_positions_long"] - hist["asset_mgr_positions_short"]
        oi = hist["open_interest_all"].replace(0, np.nan)
        hist["lev_net_pct_oi"] = 100.0 * hist["lev_net"] / oi
        hist["asset_net_pct_oi"] = 100.0 * hist["asset_net"] / oi
        last = hist.iloc[-1]
        lev_pctile = _percentile_rank(hist["lev_net_pct_oi"], last["lev_net_pct_oi"])
        asset_pctile = _percentile_rank(hist["asset_net_pct_oi"], last["asset_net_pct_oi"])
        if label == "Dollar Index":
            lev_pressure = 100.0 - lev_pctile if pd.notna(lev_pctile) else np.nan
            asset_pressure = 100.0 - asset_pctile if pd.notna(asset_pctile) else np.nan
        else:
            lev_pressure = lev_pctile
            asset_pressure = asset_pctile
        parts = [x for x in [lev_pressure, asset_pressure] if pd.notna(x)]
        market_pressure = float(np.mean(parts)) if parts else np.nan
        if pd.notna(market_pressure):
            pressure_parts.append(market_pressure)
        weekly_change = np.nan
        if len(hist) > 1:
            weekly_change = float(last["lev_net"] - hist.iloc[-2]["lev_net"])
        rows.append({
            "market": label,
            "report_date": last["report_date"],
            "cftc_code": code,
            "open_interest": last.get("open_interest_all"),
            "leveraged_net": last.get("lev_net"),
            "leveraged_net_pct_oi": last.get("lev_net_pct_oi"),
            "leveraged_weekly_change": weekly_change,
            "leveraged_3y_percentile": lev_pctile,
            "asset_manager_net": last.get("asset_net"),
            "asset_manager_net_pct_oi": last.get("asset_net_pct_oi"),
            "asset_manager_3y_percentile": asset_pctile,
            "usd_downside_positioning_pressure": market_pressure,
        })
    table = pd.DataFrame(rows)
    overall = float(np.mean(pressure_parts)) if pressure_parts else 0.0
    return table, overall


def parse_tic_mfh_text(text: str) -> pd.DataFrame:
    """Parse Treasury TIC Table 5 tab-delimited text into long format."""
    lines = [ln.rstrip("\r\n") for ln in text.splitlines()]
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("Country") and "\t" in ln:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not locate TIC Table 5 header")
    header = [x.strip() for x in lines[header_idx].split("\t")]
    dates = [x for x in header[1:] if x]
    records: list[dict[str, Any]] = []
    for ln in lines[header_idx + 1:]:
        if not ln.strip() or ln.strip().startswith("Notes:"):
            if ln.strip().startswith("Notes:"):
                break
            continue
        parts = [x.strip() for x in ln.split("\t")]
        if len(parts) < 2:
            continue
        country = parts[0]
        vals = parts[1:1 + len(dates)]
        if country.startswith("-"):
            continue
        for d, v in zip(dates, vals):
            val = pd.to_numeric(v.replace(",", ""), errors="coerce")
            if pd.notna(val):
                records.append({"country": country, "date": pd.to_datetime(d, format="%Y-%m", errors="coerce"), "holdings_bn": float(val)})
    return pd.DataFrame(records).dropna(subset=["date"]).sort_values(["country", "date"])


def fetch_tic_major_holders() -> pd.DataFrame:
    r = requests.get(TIC_MFH_URL, headers=UA, timeout=20)
    r.raise_for_status()
    return parse_tic_mfh_text(r.text)


def summarize_tic(df: pd.DataFrame) -> tuple[pd.DataFrame, float, dict[str, Any]]:
    if df.empty:
        return pd.DataFrame(), 0.0, {}
    tracked = [
        "Grand Total", "Of Which: Foreign Official", "Japan", "China, Mainland",
        "India", "Brazil", "Saudi Arabia", "United Arab Emirates", "Switzerland",
    ]
    rows = []
    for country in tracked:
        g = df[df["country"].eq(country)].sort_values("date")
        if g.empty:
            continue
        last = g.iloc[-1]
        prev = g.iloc[-2] if len(g) > 1 else None
        year_ago = g.iloc[-13] if len(g) > 12 else None
        rows.append({
            "country": country,
            "date": last["date"],
            "holdings_bn": last["holdings_bn"],
            "1m_change_bn": np.nan if prev is None else last["holdings_bn"] - prev["holdings_bn"],
            "12m_change_bn": np.nan if year_ago is None else last["holdings_bn"] - year_ago["holdings_bn"],
            "12m_change_pct": np.nan if year_ago is None or year_ago["holdings_bn"] == 0 else 100.0 * (last["holdings_bn"] / year_ago["holdings_bn"] - 1.0),
        })
    out = pd.DataFrame(rows)
    lookup = {r["country"]: r for _, r in out.iterrows()} if not out.empty else {}
    pressure = 15.0
    reasons = []
    china = lookup.get("China, Mainland")
    official = lookup.get("Of Which: Foreign Official")
    total = lookup.get("Grand Total")
    if china is not None and pd.notna(china["12m_change_pct"]):
        if china["12m_change_pct"] < -5:
            pressure += 12; reasons.append("China Treasury holdings down >5% YoY")
        if china["12m_change_pct"] < -10:
            pressure += 10; reasons.append("China Treasury holdings down >10% YoY")
    if official is not None and pd.notna(official["12m_change_bn"]):
        if official["12m_change_bn"] < -100:
            pressure += 10; reasons.append("Foreign-official TIC holdings down >$100B YoY")
        if official["12m_change_bn"] < -250:
            pressure += 10; reasons.append("Foreign-official TIC holdings down >$250B YoY")
    if total is not None and pd.notna(total["12m_change_pct"]):
        if total["12m_change_pct"] < 0:
            pressure += 8; reasons.append("Total foreign Treasury holdings down YoY")
        elif total["12m_change_pct"] > 3:
            pressure -= 7; reasons.append("Total foreign Treasury holdings up >3% YoY")
    pressure = float(max(0, min(100, pressure)))
    meta = {"reasons": reasons, "latest_date": None if out.empty else str(out["date"].max().date())}
    return out, pressure, meta


def _circulating_usd(asset: dict[str, Any]) -> float:
    circ = asset.get("circulating")
    if isinstance(circ, dict):
        for k in ["peggedUSD", "peggedEUR", "peggedVAR"]:
            if k in circ:
                return _num(circ.get(k))
        vals = [_num(v) for v in circ.values()]
        vals = [x for x in vals if pd.notna(x)]
        return vals[0] if vals else np.nan
    return _num(circ)


def fetch_stablecoins() -> tuple[pd.DataFrame, pd.DataFrame]:
    r = requests.get(STABLECOINS_URL, headers=UA, timeout=20)
    r.raise_for_status()
    obj = r.json()
    assets = obj.get("peggedAssets", obj if isinstance(obj, list) else [])
    rows = []
    for a in assets:
        rows.append({
            "name": a.get("name", ""),
            "symbol": a.get("symbol", ""),
            "peg_type": a.get("pegType", ""),
            "circulating_usd": _circulating_usd(a),
            "price": _num(a.get("price")),
        })
    asset_df = pd.DataFrame(rows)

    hist_df = pd.DataFrame()
    try:
        h = requests.get(STABLECOIN_CHART_URL, headers=UA, timeout=20)
        h.raise_for_status()
        data = h.json()
        hist_rows = []
        for item in data if isinstance(data, list) else []:
            total = item.get("totalCirculatingUSD", item.get("totalCirculating", item.get("circulating")))
            if isinstance(total, dict):
                total = total.get("peggedUSD", next(iter(total.values()), np.nan))
            hist_rows.append({"date": pd.to_datetime(int(item.get("date")), unit="s", errors="coerce"), "market_cap_usd": _num(total)})
        hist_df = pd.DataFrame(hist_rows).dropna().sort_values("date")
    except Exception:
        hist_df = pd.DataFrame(columns=["date", "market_cap_usd"])
    return asset_df, hist_df


def _hist_return(hist: pd.DataFrame, days: int) -> float:
    if hist.empty:
        return np.nan
    h = hist.dropna(subset=["date", "market_cap_usd"]).sort_values("date")
    if h.empty:
        return np.nan
    last = h.iloc[-1]
    cutoff = last["date"] - pd.Timedelta(days=days)
    prior = h[h["date"] <= cutoff]
    if prior.empty or prior.iloc[-1]["market_cap_usd"] == 0:
        return np.nan
    return float(last["market_cap_usd"] / prior.iloc[-1]["market_cap_usd"] - 1.0)


def summarize_stablecoins(assets: pd.DataFrame, hist: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any], float]:
    if assets.empty:
        return pd.DataFrame(), {}, 0.0
    usd = assets[assets["peg_type"].astype(str).str.contains("USD", case=False, na=False)].copy()
    if usd.empty:
        usd = assets.copy()
    usd = usd.sort_values("circulating_usd", ascending=False)
    focus = usd[usd["symbol"].astype(str).str.upper().isin(["USDT", "USDC", "USD1", "DAI", "PYUSD", "FDUSD", "USDS"])].copy()
    if focus.empty:
        focus = usd.head(10).copy()
    total = float(pd.to_numeric(usd["circulating_usd"], errors="coerce").sum())
    r30 = _hist_return(hist, 30)
    r90 = _hist_return(hist, 90)
    r365 = _hist_return(hist, 365)
    support = 20.0
    reasons = []
    if pd.notna(r90):
        if r90 > 0.05:
            support += 12; reasons.append("Stablecoin supply up >5% over ~3 months")
        if r90 > 0.10:
            support += 10; reasons.append("Stablecoin supply up >10% over ~3 months")
        if r90 < -0.05:
            support -= 10; reasons.append("Stablecoin supply down >5% over ~3 months")
    if pd.notna(r365) and r365 > 0.20:
        support += 12; reasons.append("Stablecoin supply up >20% YoY")
    # Peg instability reduces confidence in stablecoins as structural dollar support.
    prices = pd.to_numeric(usd["price"], errors="coerce")
    circ = pd.to_numeric(usd["circulating_usd"], errors="coerce").fillna(0)
    depeg = (prices.sub(1).abs() > 0.01) & (circ > 1e9)
    if depeg.any():
        support -= min(15.0, 5.0 * int(depeg.sum()))
        reasons.append("One or more >$1B USD stablecoins are >1% off peg")
    support = float(max(0, min(100, support)))
    usd1 = focus[focus["symbol"].astype(str).str.upper().eq("USD1")]
    meta = {
        "usd_stablecoin_supply": total,
        "30d_growth": r30,
        "90d_growth": r90,
        "1y_growth": r365,
        "usd1_supply": None if usd1.empty else float(usd1.iloc[0]["circulating_usd"]),
        "reasons": reasons,
    }
    return focus, meta, support


def build_data_health(source_status: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, float]:
    """Create auditable source-health table and overall confidence score.

    Expected status item fields: ok, weight, last_date, error, notes.
    """
    rows = []
    weighted = 0.0
    total_w = 0.0
    now = pd.Timestamp.now(tz="UTC")
    for name, info in source_status.items():
        weight = float(info.get("weight", 1.0))
        ok = bool(info.get("ok", False))
        last_date = pd.to_datetime(info.get("last_date"), utc=True, errors="coerce")
        freshness = "unknown"
        freshness_factor = 0.8 if ok else 0.0
        age_days = np.nan
        if pd.notna(last_date):
            age_days = float((now - last_date).total_seconds() / 86400)
            if age_days <= 2:
                freshness = "fresh"; freshness_factor = 1.0
            elif age_days <= 10:
                freshness = "normal lag"; freshness_factor = 0.9
            elif age_days <= 45:
                freshness = "stale"; freshness_factor = 0.65
            else:
                freshness = "very stale"; freshness_factor = 0.35
        score = 100.0 * freshness_factor if ok else 0.0
        weighted += weight * score
        total_w += weight
        rows.append({
            "source": name, "status": "OK" if ok else "FAILED", "last_date": last_date,
            "age_days": age_days, "freshness": freshness, "confidence": score,
            "error": info.get("error", ""), "notes": info.get("notes", ""),
        })
    overall = weighted / total_w if total_w else 0.0
    return pd.DataFrame(rows), float(overall)
