from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "dollar_watch/2.8 (+local research dashboard)"}

CFTC_DATASET = "gpe5-46if"  # Traders in Financial Futures - futures only
CFTC_ENDPOINTS = [
    f"https://publicreporting.cftc.gov/resource/{CFTC_DATASET}.json",
    f"https://publicreportinghub.cftc.gov/resource/{CFTC_DATASET}.json",
]

TIC_MFH_URL = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.txt"
STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoins"
STABLECOIN_CHART_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
IMF_COFER_URLS = [
    "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/COFER/+/G001.AFXRA.CI_USD.SHRO_PT.Q",
    "https://api.imf.org/external/sdmx/2.1/data/COFER/G001.AFXRA.CI_USD.SHRO_PT.Q",
]

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


TOKENIZED_RWA_SYMBOLS = {
    # Conservative known set. Name heuristics catch additional Treasury/money-market products;
    # avoid a broad symbol denylist that could misclassify a genuine transactional stablecoin.
    "USYC", "USDY", "OUSG", "BUIDL", "BENJI", "USTB",
}
TOKENIZED_RWA_NAME_HINTS = (
    "treasury", "government securities", "government money", "money market",
    "short duration", "yield coin", "institutional digital liquidity",
)


def _digital_dollar_class(row: pd.Series) -> str:
    symbol = str(row.get("symbol", "")).upper().strip()
    name = str(row.get("name", "")).lower().strip()
    if symbol in TOKENIZED_RWA_SYMBOLS or any(h in name for h in TOKENIZED_RWA_NAME_HINTS):
        return "TOKENIZED_TREASURY_RWA"
    return "TRANSACTIONAL_STABLECOIN"


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
    if not asset_df.empty:
        asset_df["asset_class"] = asset_df.apply(_digital_dollar_class, axis=1)

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
    """Summarize digital-dollar demand without treating accumulating Treasury tokens as $1 pegs.

    DefiLlama's USD-pegged universe can contain yield-bearing/tokenized-RWA products such as
    USDY or USYC. Those products are economically relevant to dollar/Treasury demand, but a
    price above $1 can be intentional NAV accumulation rather than a depeg. V2.7 therefore
    separates transactional stablecoins from tokenized Treasury/RWA products before applying
    any peg-stability rule.
    """
    if assets.empty:
        return pd.DataFrame(), {}, 0.0
    usd = assets[assets["peg_type"].astype(str).str.contains("USD", case=False, na=False)].copy()
    if usd.empty:
        usd = assets.copy()
    if "asset_class" not in usd.columns:
        usd["asset_class"] = usd.apply(_digital_dollar_class, axis=1)

    transactional = usd[usd["asset_class"].eq("TRANSACTIONAL_STABLECOIN")].copy()
    rwa = usd[usd["asset_class"].eq("TOKENIZED_TREASURY_RWA")].copy()
    transactional = transactional.sort_values("circulating_usd", ascending=False)
    rwa = rwa.sort_values("circulating_usd", ascending=False)

    focus_symbols = ["USDT", "USDC", "USD1", "DAI", "PYUSD", "FDUSD", "USDS", "USDE", "FRAX", "USDP"]
    focus = transactional[transactional["symbol"].astype(str).str.upper().isin(focus_symbols)].copy()
    if focus.empty:
        focus = transactional.head(10).copy()

    transactional_supply = float(pd.to_numeric(transactional["circulating_usd"], errors="coerce").sum())
    rwa_supply = float(pd.to_numeric(rwa["circulating_usd"], errors="coerce").sum())
    digital_usd_supply = transactional_supply + rwa_supply

    # Historical aggregate is a broad DefiLlama USD-pegged universe. It may include RWA products,
    # so label it broad digital-dollar growth rather than pure transactional-stablecoin growth.
    r30 = _hist_return(hist, 30)
    r90 = _hist_return(hist, 90)
    r365 = _hist_return(hist, 365)
    support = 20.0
    reasons = []
    if pd.notna(r90):
        if r90 > 0.05:
            support += 12; reasons.append("Broad digital-dollar supply up >5% over ~3 months")
        if r90 > 0.10:
            support += 10; reasons.append("Broad digital-dollar supply up >10% over ~3 months")
        if r90 < -0.05:
            support -= 10; reasons.append("Broad digital-dollar supply down >5% over ~3 months")
    if pd.notna(r365) and r365 > 0.20:
        support += 12; reasons.append("Broad digital-dollar supply up >20% YoY")
    if rwa_supply > 1e9:
        support += 3; reasons.append("Tokenized Treasury/RWA dollar products exceed $1B")

    # Only transactional $1-intended stablecoins are eligible for peg warnings. Yield-accumulating
    # RWA products are shown separately and NEVER interpreted as a depeg solely from price != $1.
    prices = pd.to_numeric(transactional["price"], errors="coerce")
    circ = pd.to_numeric(transactional["circulating_usd"], errors="coerce").fillna(0)
    eligible = (circ > 1e9) & prices.notna()
    deviations = prices[eligible].sub(1).abs()
    max_depeg = float(deviations.max()) if not deviations.empty else 0.0
    depeg = eligible & (prices.sub(1).abs() > 0.01)
    depeg_symbols = transactional.loc[depeg, "symbol"].astype(str).tolist() if depeg.any() else []
    if depeg.any():
        support -= min(15.0, 5.0 * int(depeg.sum()))
        reasons.append(f">$1B transactional stablecoin depeg >1%: {', '.join(depeg_symbols)}")

    support = float(max(0, min(100, support)))
    usd1 = focus[focus["symbol"].astype(str).str.upper().eq("USD1")]
    rwa_cols = [c for c in ["name", "symbol", "circulating_usd", "price", "asset_class"] if c in rwa.columns]
    meta = {
        "usd_stablecoin_supply": transactional_supply,
        "transactional_stablecoin_supply": transactional_supply,
        "tokenized_rwa_supply": rwa_supply,
        "broad_digital_usd_supply": digital_usd_supply,
        "30d_growth": r30,
        "90d_growth": r90,
        "1y_growth": r365,
        "growth_universe_note": "DefiLlama broad USD-pegged history; may include tokenized RWA products",
        "usd1_supply": None if usd1.empty else float(usd1.iloc[0]["circulating_usd"]),
        "max_large_stablecoin_deviation_pct": 100.0 * max_depeg,
        "large_depeg_symbols": depeg_symbols,
        "rwa_products": rwa[rwa_cols].head(20).where(pd.notnull(rwa[rwa_cols].head(20)), None).to_dict(orient="records") if not rwa.empty else [],
        "reasons": reasons,
    }
    return focus, meta, support



def summarize_fx_positioning_squeeze(cftc_summary: pd.DataFrame) -> tuple[float, list[str]]:
    """Detect crowded foreign-currency shorts that can create mechanical USD weakness on unwind.

    Low leveraged-net percentiles in EUR/JPY/CHF imply unusually large shorts in those currencies.
    This is classified separately from fundamental USD-downside conviction.
    """
    if cftc_summary is None or cftc_summary.empty:
        return 0.0, []
    parts = []
    reasons = []
    weights = {"Japanese Yen": 1.35, "Euro FX": 1.0, "Swiss Franc": 0.8}
    for _, row in cftc_summary.iterrows():
        market = str(row.get("market", ""))
        if market not in weights:
            continue
        pct = _num(row.get("leveraged_3y_percentile"))
        weekly = _num(row.get("leveraged_weekly_change"))
        if pd.isna(pct):
            continue
        # 0th percentile = most crowded short in the sample.
        crowded_short = max(0.0, min(100.0, 100.0 - pct))
        if pct < 20:
            reasons.append(f"{market} leveraged net at {pct:.0f}th percentile (crowded short)")
        if pd.notna(weekly) and weekly < 0:
            crowded_short = min(100.0, crowded_short + 5.0)
        parts.append((crowded_short, weights[market]))
    if not parts:
        return 0.0, reasons
    score = sum(v*w for v,w in parts) / sum(w for _,w in parts)
    return float(max(0, min(100, score))), reasons


def fetch_imf_cofer_usd_share(start: str = "2020") -> pd.DataFrame:
    """Fetch IMF COFER world USD reserve share via current SDMX endpoints.

    The IMF API has moved versions; try SDMX 3.0 then 2.1 and accept CSV/JSON variants.
    Failure is isolated by the pipeline and never blocks the dashboard.
    """
    errors=[]
    for url in IMF_COFER_URLS:
        try:
            params={"startPeriod": start}
            headers={**UA, "Accept": "text/csv,application/vnd.sdmx.data+csv;version=2.0.0,application/json"}
            r=requests.get(url, params=params, headers=headers, timeout=25)
            r.raise_for_status()
            text=r.text.strip()
            # CSV responses contain TIME_PERIOD and OBS_VALUE columns.
            if text and ("," in text or ";" in text):
                try:
                    df=pd.read_csv(StringIO(text))
                except Exception:
                    df=pd.DataFrame()
                if not df.empty:
                    cols={c.upper():c for c in df.columns}
                    tcol=cols.get("TIME_PERIOD") or cols.get("TIME_PERIOD_START")
                    vcol=cols.get("OBS_VALUE") or cols.get("VALUE")
                    if tcol and vcol:
                        out=pd.DataFrame({"period":df[tcol].astype(str),"usd_share_pct":pd.to_numeric(df[vcol],errors="coerce")})
                        return out.dropna().reset_index(drop=True)
            # Try SDMX JSON common shape.
            obj=r.json()
            datasets=obj.get("data", obj).get("dataSets", []) if isinstance(obj,dict) else []
            struct=obj.get("data", obj).get("structure", {}) if isinstance(obj,dict) else {}
            if datasets:
                obs=[]
                # Generic flatten; periods may be supplied in structure observation values.
                periods=[]
                try:
                    periods=[x.get("id") or x.get("name") for x in struct.get("dimensions",{}).get("observation",[])[0].get("values",[])]
                except Exception:
                    periods=[]
                series=datasets[0].get("series",{})
                for _,sv in series.items():
                    for oi,ov in sv.get("observations",{}).items():
                        val=ov[0] if isinstance(ov,list) else ov
                        period=periods[int(oi)] if periods and str(oi).isdigit() and int(oi)<len(periods) else str(oi)
                        obs.append({"period":period,"usd_share_pct":_num(val)})
                out=pd.DataFrame(obs).dropna()
                if not out.empty:
                    return out
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("IMF COFER unavailable: " + "; ".join(errors[-2:]))


def summarize_cofer(df: pd.DataFrame) -> tuple[dict[str, Any], float]:
    if df is None or df.empty:
        return {}, 0.0
    d=df.copy(); d["usd_share_pct"]=pd.to_numeric(d["usd_share_pct"],errors="coerce"); d=d.dropna(subset=["usd_share_pct"])
    if d.empty: return {},0.0
    last=float(d.iloc[-1]["usd_share_pct"])
    q4=float(d.iloc[-5]["usd_share_pct"]) if len(d)>=5 else np.nan
    change=np.nan if pd.isna(q4) else last-q4
    pressure=15.0
    reasons=[]
    if not pd.isna(change):
        if change < -1.0: pressure += 12; reasons.append("USD COFER share down >1pp over ~1y")
        if change < -2.0: pressure += 12; reasons.append("USD COFER share down >2pp over ~1y")
        if change > 1.0: pressure -= 8; reasons.append("USD COFER share up >1pp over ~1y")
    if last < 55: pressure += 8
    if last < 50: pressure += 12
    meta={"latest_period":str(d.iloc[-1]["period"]),"usd_share_pct":last,"approx_1y_change_pp":None if pd.isna(change) else float(change),"reasons":reasons}
    return meta,float(max(0,min(100,pressure)))

def period_last_date(period: str | None):
    """Convert common quarterly/monthly period labels to an observation-end timestamp."""
    if not period:
        return None
    text=str(period).strip().upper()
    try:
        import re
        m=re.search(r"(\d{4}).*?Q0?([1-4])", text)
        if m:
            year=int(m.group(1)); q=int(m.group(2)); month=q*3
            return pd.Timestamp(year=year, month=month, day=1, tz="UTC") + pd.offsets.MonthEnd(0)
        ts=pd.to_datetime(text, utc=True, errors="coerce")
        return None if pd.isna(ts) else ts
    except Exception:
        return None


def build_data_health(source_status: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, float]:
    """Create auditable source-health table and overall confidence score.

    Future-dated source observations are a data-hygiene warning, not evidence of extraordinary
    freshness. They are age-clamped to zero, explicitly flagged, and confidence-discounted.
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
        hygiene_flag = ""
        if pd.notna(last_date):
            raw_age_days = float((now - last_date).total_seconds() / 86400)
            if raw_age_days < -0.5:
                age_days = 0.0
                freshness = "source date ahead"
                freshness_factor = 0.75 if ok else 0.0
                hygiene_flag = f"SOURCE_DATE_AHEAD by {abs(raw_age_days):.1f}d"
            else:
                age_days = max(0.0, raw_age_days)
                if age_days <= 2:
                    freshness = "fresh"; freshness_factor = 1.0
                elif age_days <= 10:
                    freshness = "normal lag"; freshness_factor = 0.9
                elif age_days <= 45:
                    freshness = "stale"; freshness_factor = 0.65
                else:
                    freshness = "very stale"; freshness_factor = 0.35
        score = 100.0 * freshness_factor if ok else 0.0
        cap = info.get("confidence_cap")
        if cap is not None:
            try: score = min(score, max(0.0, min(100.0, float(cap))))
            except Exception: pass
        weighted += weight * score
        total_w += weight
        notes = str(info.get("notes", "") or "")
        if hygiene_flag:
            notes = (notes + " | " if notes else "") + hygiene_flag
        rows.append({
            "source": name, "status": "OK" if ok else "FAILED", "last_date": last_date,
            "age_days": age_days, "freshness": freshness, "confidence": score,
            "data_hygiene_flag": hygiene_flag,
            "error": info.get("error", ""), "notes": notes,
        })
    overall = weighted / total_w if total_w else 0.0
    return pd.DataFrame(rows), float(overall)



def summarize_tic_transactions(fred_hist: pd.DataFrame) -> dict[str, Any]:
    """Decompose reported foreign Treasury position changes into transactions and non-transaction effects.

    Holdings include all maturities, while published valuation-change series cover long-term Treasuries.
    Therefore the residual is deliberately called ``non_transaction_residual`` rather than pure valuation.
    This prevents holdings changes from being mislabeled as demand.
    """
    if fred_hist is None or fred_hist.empty:
        return {}
    specs = {
        "grand_total": {
            "holdings": "Foreign Treasury holdings grand total (millions)",
            "transactions": "Foreign Treasury net transactions grand total (millions)",
            "valuation_lt": "Foreign LT Treasury valuation change grand total (millions)",
        },
        "foreign_official": {
            "holdings": "Foreign official Treasury holdings (millions)",
            "transactions": "Foreign Treasury net transactions official (millions)",
            "valuation_lt": "Foreign LT Treasury valuation change official (millions)",
        },
    }
    out = {}
    for key, sp in specs.items():
        needed=[sp["holdings"],sp["transactions"]]
        if any(c not in fred_hist.columns for c in needed):
            continue
        h=fred_hist[sp["holdings"]].dropna()
        t=fred_hist[sp["transactions"]].dropna()
        if len(h)<2 or t.empty:
            continue
        common=h.index.intersection(t.index)
        if len(common)==0:
            continue
        d=common[-1]
        h_now=float(h.loc[d])
        prev_h=h.loc[h.index<d]
        if prev_h.empty:
            continue
        h_prev=float(prev_h.iloc[-1])
        pos_change=h_now-h_prev
        net_tx=float(t.loc[d])
        val=None
        vcol=sp.get("valuation_lt")
        if vcol in fred_hist.columns:
            vv=fred_hist[vcol].dropna()
            if d in vv.index:
                val=float(vv.loc[d])
        residual=pos_change-net_tx-(val or 0.0)
        out[key]={
            "date": str(pd.Timestamp(d).date()),
            "ending_holdings_mn": h_now,
            "monthly_position_change_mn": pos_change,
            "net_transactions_mn": net_tx,
            "long_term_valuation_change_mn": val,
            "non_transaction_residual_mn": residual,
            "transaction_share_of_position_change": None if abs(pos_change)<1e-9 else net_tx/pos_change,
            "note": "Transactions measure active net purchases/sales. Long-term valuation is price effect on LT Treasuries; residual also captures short-term valuation/custody/reclassification/other changes.",
        }
    # private net transactions are directly published and useful even without a private holdings decomposition.
    c="Foreign Treasury net transactions private (millions)"
    if c in fred_hist.columns and not fred_hist[c].dropna().empty:
        ss=fred_hist[c].dropna(); out["foreign_private"]={"date":str(ss.index[-1].date()),"net_transactions_mn":float(ss.iloc[-1])}
    return out
