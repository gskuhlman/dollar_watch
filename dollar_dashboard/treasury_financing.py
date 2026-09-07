from __future__ import annotations

"""Treasury financing / bank-balance-sheet transmission for dollar_watch V3.4.

Two layers are deliberately kept separate:

1. Holder layer -- who acquired marketable Treasury securities (Federal Reserve
   Z.1 table F3.2.t, quarterly SAAR transaction flows).
2. Funding layer -- repo balance-sheet capacity used by banks, dealers and cash
   pools (Z.1 table F4.1.s, quarterly levels).

Funding-layer values are never added to holder flows.  This prevents a common
error in which a Treasury held by a levered investor is counted once as a
Treasury purchase and again as repo financing.
"""

from datetime import datetime, timezone
from typing import Callable

import numpy as np
import pandas as pd

from .data import fetch_fred_series


# Z.1 F3.2.t marketable Treasury-security transactions. Quarterly observations
# are seasonally adjusted annual rates (SAAR), millions of dollars.
Z1_FINANCING_SERIES = {
    "Net marketable Treasury issuance": "BOGZ1FA313161105Q",
    "Federal Reserve / central bank": "BOGZ1FA713061103Q",
    "U.S.-chartered depository institutions": "BOGZ1FA763061100Q",
    "Foreign banking offices in U.S.": "BOGZ1FA753061103Q",
    "Banks in U.S.-affiliated areas": "BOGZ1FA743061103Q",
    "Credit unions": "BOGZ1FA473061105Q",
    "Foreign sector": "ROWTSAQ027S",
    "Security brokers & dealers": "BOGZ1FA663061105Q",
    "Money market funds": "BOGZ1FA633061105Q",
    "Households & nonprofits": "HNOTSBQ027S",
    "Nonfinancial corporate business": "NCBTSAQ027S",
    "Nonfinancial noncorporate business": "NNBGSAQ027S",
    "State & local governments": "BOGZ1FA213061103Q",
    "Property-casualty insurance": "BOGZ1FA513061105Q",
    "Life insurance": "BOGZ1FA543061105Q",
    "Private pension funds": "BOGZ1FA573061105Q",
    "Federal government pension funds": "BOGZ1FA343061105Q",
    "State & local government pension funds": "BOGZ1FA223061143Q",
    "Mutual funds": "BOGZ1FA653061105Q",
    "Closed-end funds": "BOGZ1FA553061103Q",
    "Exchange-traded funds": "BOGZ1FA563061103Q",
    "Government-sponsored enterprises": "BOGZ1FA403061105Q",
    "ABS issuers": "BOGZ1FA673061103Q",
    "Holding companies": "BOGZ1FA733061103Q",
    "Other financial business": "BOGZ1FA503061123Q",
}

# The Aug. 28, 2026 Z.1 preview adds hedge funds as an explicit F3.2.t
# Treasury-holder transaction row (FA623061103). The preview contains no values,
# so we only attempt the corresponding FRED series on/after the scheduled Q2
# release date. Failure is optional metadata and does not lower core coverage.
OPTIONAL_Z1_FINANCING_SERIES = {
    "Hedge funds": "BOGZ1FA623061103Q",
}
OPTIONAL_Z1_ACTIVATION_DATE = pd.Timestamp("2026-09-11")

# Higher-frequency confirmation data. These are levels and are not added to Z.1
# holder transactions.
MONEY_CONFIRMATION_SERIES = {
    "M2 money stock": "M2SL",                       # billions, monthly
    "Commercial bank deposits": "DPSACBM027SBOG",  # billions, monthly
    "Bank Treasury + agency securities": "USGSEC",  # billions, monthly; H.8 proxy only
}

# Z.1 F4.1.s repo levels. These describe funding/intermediation, not Treasury
# ownership, and repo collateral is not Treasury-only.
FUNDING_LAYER_SERIES = {
    "Dealer repo liabilities": "BOGZ1FL662151003Q",
    "Dealer repo assets": "BOGZ1FL662051003Q",
    "MMF repo assets": "BOGZ1FL632051000Q",
    "U.S. bank repo liabilities": "BOGZ1FL762151005Q",
    "U.S. bank repo assets": "BOGZ1FL762051005Q",
    "Foreign-bank repo liabilities": "BOGZ1FL752151005Q",
    "Foreign-bank repo assets": "BOGZ1FL752051005Q",
    # Hedge-fund structural overlays. These are deliberately not treated as
    # Treasury-holder transaction flows or direct basis-trade leverage.
    "Hedge fund Treasury holdings": "BOGZ1FL623061103Q",
    "Hedge fund repo assets": "BOGZ1FL622051003Q",
    "Hedge fund domestic repo liabilities": "BOGZ1FL622151013Q",
}

# Known official Z.1 release dates used to distinguish normal publication lag
# from an actually stale/missed release. Unlisted future quarters fall back to
# an approximate 75-day post-quarter publication lag.
Z1_KNOWN_RELEASE_DATES = {
    "2026Q1": "2026-06-11",
    "2026Q2": "2026-09-11",
}
Z1_TYPICAL_RELEASE_LAG_DAYS = 75

SLR_POLICY = {
    "regime": "RELAXED",
    "effective_date": "2026-04-01",
    "early_adoption_date": "2026-01-01",
    "treasury_exemption": False,
    "reserve_exemption": False,
    "description": (
        "Enhanced SLR recalibration is effective April 1, 2026 (early adoption permitted "
        "January 1, 2026). Treasuries and Federal Reserve balances remain in total leverage "
        "exposure; the final rule lowers the enhanced leverage constraint rather than excluding them."
    ),
    "scope_note": (
        "The rule applies to covered large U.S. banking organizations. The dashboard's broader "
        "banking-system holder bucket also includes foreign banking offices, affiliated-area banks "
        "and credit unions, so the SLR overlay must not be interpreted as applying identically to every dollar in that bucket."
    ),
    "source": "Federal Reserve / FDIC / OCC final eSLR rule, Nov. 25, 2025",
}


def _safe_float(v, default=None):
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _period_label(ts) -> str | None:
    try:
        return str(pd.Timestamp(ts).to_period("Q"))
    except Exception:
        return None


def _annualized_growth(series: pd.Series, days: int = 91) -> float | None:
    """Calendar-lookback annualized growth rate from level data, in percent."""
    s = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if len(s) < 2 or s.iloc[-1] <= 0:
        return None
    target = s.index[-1] - pd.Timedelta(days=days)
    prior = s.loc[s.index <= target]
    if prior.empty or prior.iloc[-1] <= 0:
        return None
    elapsed = max(1.0, float((s.index[-1] - prior.index[-1]).days))
    ratio = float(s.iloc[-1] / prior.iloc[-1])
    try:
        return (ratio ** (365.25 / elapsed) - 1.0) * 100.0
    except Exception:
        return None


def _annualized_growth_asof(series: pd.Series, asof=None, days: int = 91) -> float | None:
    """Approximate calendar-window annualized growth ending on/before *asof*.

    Monthly FRED series are usually timestamped on the first of the month.  The
    prior observation nearest the calendar target is therefore preferable to
    forcing a strictly-before target that can accidentally turn a 3-month
    comparison into four months.
    """
    s = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if asof is not None:
        s = s.loc[s.index <= pd.Timestamp(asof)]
    if len(s) < 2 or s.iloc[-1] <= 0:
        return None
    latest_date = s.index[-1]
    target = latest_date - pd.Timedelta(days=days)
    candidates = s.iloc[:-1]
    if candidates.empty:
        return None
    prior_date = min(candidates.index, key=lambda x: abs((pd.Timestamp(x) - target).days))
    if abs((pd.Timestamp(prior_date) - target).days) > 45:
        return None
    prior_val = float(candidates.loc[prior_date])
    if prior_val <= 0:
        return None
    elapsed = max(1.0, float((latest_date - prior_date).days))
    ratio = float(s.iloc[-1] / prior_val)
    try:
        return (ratio ** (365.25 / elapsed) - 1.0) * 100.0
    except Exception:
        return None


def _series_value(df: pd.DataFrame, label: str, when) -> float | None:
    if df is None or df.empty or label not in df.columns:
        return None
    s = pd.to_numeric(df[label], errors="coerce")
    if when not in s.index or pd.isna(s.loc[when]):
        return None
    return float(s.loc[when])


def _sum_complete(vals: list[float | None]) -> float | None:
    return None if any(v is None for v in vals) else float(sum(vals))


def classify_financing_regime(
    monetary_share: float | None,
    money_confirmation: float | None,
    dealer_share: float | None,
    foreign_share: float | None,
) -> dict:
    """Heuristic financing-pressure state; explicitly not a probability."""
    m = _safe_float(monetary_share)
    g = _safe_float(money_confirmation)
    d = _safe_float(dealer_share, 0.0)
    f = _safe_float(foreign_share)
    confirms = []
    if d is not None and d >= 15:
        confirms.append("dealer net Treasury absorption >=15% of issuance")
    if f is not None and f < 15:
        confirms.append("foreign absorption <15% of issuance")

    if m is None:
        return {
            "state": "UNKNOWN",
            "score": None,
            "reason": "Latest Z.1 monetary-capable absorption is unavailable.",
            "confirmations": confirms,
        }

    # Interpretable pressure index only; not a probability or causal estimate.
    score = min(
        100.0,
        max(0.0, m * 1.35 + (0 if g is None else max(0.0, g - 2.0) * 2.5) + (8 if d >= 15 else 0)),
    )
    if m >= 50 and g is not None and g >= 6 and confirms:
        state = "RED"
        reason = (
            "Monetary-capable absorption exceeds 50%, same-quarter money/deposit growth is >6% annualized, "
            "and a market-structure confirmation is active. This is a pressure classification, not causal attribution."
        )
    elif m >= 35 and g is not None and g >= 5:
        state = "ORANGE"
        reason = (
            "Monetary-capable absorption is >=35% and same-quarter broad-money/deposit growth shows a concurrent monetary backdrop; attribution remains unproven."
        )
    elif m >= 20:
        state = "YELLOW"
        reason = "Fed/bank absorption is elevated but does not yet meet the monetization-like confirmation test."
    else:
        state = "GREEN"
        reason = "Private/foreign market financing dominates relative to monetary-capable institutions."
    return {"state": state, "score": round(score, 1), "reason": reason, "confirmations": confirms}


def _summarize_money(money_hist: pd.DataFrame | None, matched_quarter=None) -> dict:
    out = {
        "m2_3m_annualized_pct": None,
        "deposits_3m_annualized_pct": None,
        "confirmation_3m_annualized_pct": None,
        "matched_m2_3m_annualized_pct": None,
        "matched_deposits_3m_annualized_pct": None,
        "matched_confirmation_3m_annualized_pct": None,
        "matched_as_of": None,
        "bank_treasury_agency_3m_change_bn": None,
        "bank_treasury_agency_since_slr_bn": None,
        "bank_treasury_agency_since_slr_pct": None,
        "as_of": None,
    }
    if money_hist is None or money_hist.empty:
        return out
    m2 = money_hist["M2 money stock"] if "M2 money stock" in money_hist else pd.Series(dtype=float)
    dep = money_hist["Commercial bank deposits"] if "Commercial bank deposits" in money_hist else pd.Series(dtype=float)
    sec = money_hist["Bank Treasury + agency securities"] if "Bank Treasury + agency securities" in money_hist else pd.Series(dtype=float)

    mg = _annualized_growth_asof(m2, None, 91)
    dg = _annualized_growth_asof(dep, None, 91)
    vals_g = [x for x in [mg, dg] if x is not None]
    confirmation = sum(vals_g) / len(vals_g) if vals_g else None

    mmg = mdg = mconfirm = None
    matched_asof = None
    if matched_quarter is not None:
        qend = pd.Timestamp(matched_quarter).to_period("Q").end_time.normalize()
        mmg = _annualized_growth_asof(m2, qend, 91)
        mdg = _annualized_growth_asof(dep, qend, 91)
        mv = [x for x in [mmg, mdg] if x is not None]
        mconfirm = sum(mv) / len(mv) if mv else None
        dates=[]
        for ser in [m2,dep]:
            ss=pd.to_numeric(ser,errors="coerce").dropna().sort_index()
            ss=ss.loc[ss.index<=qend]
            if not ss.empty: dates.append(ss.index[-1])
        matched_asof=str(max(dates).date()) if dates else None

    sec_change = None
    slr_change = slr_pct = None
    ssec = pd.to_numeric(sec, errors="coerce").dropna().sort_index()
    if not ssec.empty:
        latest=ssec.index[-1]
        target=latest-pd.Timedelta(days=91)
        prev=ssec.iloc[:-1]
        if not prev.empty:
            pdate=min(prev.index,key=lambda x:abs((pd.Timestamp(x)-target).days))
            if abs((pd.Timestamp(pdate)-target).days)<=45:
                sec_change=float(ssec.iloc[-1]-prev.loc[pdate])
        slr_start=pd.Timestamp(SLR_POLICY["effective_date"])
        before=ssec.loc[ssec.index<=slr_start]
        if not before.empty and latest>=slr_start:
            base=float(before.iloc[-1])
            slr_change=float(ssec.iloc[-1]-base)
            slr_pct=None if base==0 else slr_change/base*100.0

    latest_dates = [
        ser.dropna().index[-1]
        for ser in [m2, dep, sec]
        if isinstance(ser, pd.Series) and not ser.dropna().empty
    ]
    return {
        "m2_3m_annualized_pct": mg,
        "deposits_3m_annualized_pct": dg,
        "confirmation_3m_annualized_pct": confirmation,
        "matched_m2_3m_annualized_pct": mmg,
        "matched_deposits_3m_annualized_pct": mdg,
        "matched_confirmation_3m_annualized_pct": mconfirm,
        "matched_as_of": matched_asof,
        "bank_treasury_agency_3m_change_bn": sec_change,
        "bank_treasury_agency_since_slr_bn": slr_change,
        "bank_treasury_agency_since_slr_pct": slr_pct,
        "as_of": str(max(latest_dates).date()) if latest_dates else None,
    }


def _summarize_funding(funding_hist: pd.DataFrame | None) -> dict:
    """Latest repo/hedge-fund structure levels; never counted as Treasury demand."""
    if funding_hist is None or funding_hist.empty:
        return {"available": False, "rows": [], "as_of_quarter": None}
    latest_dates = []
    rows = []
    for label in FUNDING_LAYER_SERIES:
        if label not in funding_hist:
            continue
        s = pd.to_numeric(funding_hist[label], errors="coerce").dropna().sort_index()
        if s.empty:
            continue
        latest_dates.append(s.index[-1])
        latest = float(s.iloc[-1]) / 1000.0
        qoq = None if len(s) < 2 else float(s.iloc[-1] - s.iloc[-2]) / 1000.0
        rows.append({"metric": label, "level_bn": latest, "qoq_change_bn": qoq, "date": str(pd.Timestamp(s.index[-1]).date())})

    by = {r["metric"]: r["level_bn"] for r in rows}
    byrow = {r["metric"]: r for r in rows}
    dealer_liab, dealer_asset = by.get("Dealer repo liabilities"), by.get("Dealer repo assets")
    dealer_gross = None if dealer_liab is None or dealer_asset is None else dealer_liab + dealer_asset
    dealer_net_borrow = None if dealer_liab is None or dealer_asset is None else dealer_liab - dealer_asset

    hf_tsy = by.get("Hedge fund Treasury holdings")
    hf_repo_assets = by.get("Hedge fund repo assets")
    hf_repo_liab = by.get("Hedge fund domestic repo liabilities")
    hf_ratio = None
    hf_ratio_asof = None
    if hf_tsy not in (None, 0) and hf_repo_liab is not None:
        d1 = (byrow.get("Hedge fund Treasury holdings") or {}).get("date")
        d2 = (byrow.get("Hedge fund domestic repo liabilities") or {}).get("date")
        if d1 and d1 == d2:
            hf_ratio = hf_repo_liab / hf_tsy * 100.0
            hf_ratio_asof = d1

    return {
        "available": bool(rows),
        "as_of_quarter": _period_label(max(latest_dates)) if latest_dates else None,
        "rows": rows,
        "dealer_repo_gross_bn": dealer_gross,
        "dealer_repo_net_borrowing_bn": dealer_net_borrow,
        "mmf_repo_assets_bn": by.get("MMF repo assets"),
        "hedge_fund_treasury_holdings_bn": hf_tsy,
        "hedge_fund_repo_assets_bn": hf_repo_assets,
        "hedge_fund_domestic_repo_liabilities_bn": hf_repo_liab,
        "hedge_fund_domestic_repo_to_treasury_pct": hf_ratio,
        "hedge_fund_ratio_asof": hf_ratio_asof,
        "note": (
            "Repo and hedge-fund structure are funding/intermediation overlays, not Treasury-holder transaction buckets. "
            "Z.1 repo collateral is not Treasury-only. Hedge-fund domestic repo liabilities cover domestic counterparties only, "
            "and the repo/Treasury ratio is a partial structural proxy—not gross leverage and not direct basis-trade exposure."
        ),
    }


def _expected_latest_z1_quarter(now=None) -> tuple[pd.Period, str | None]:
    """Return the latest quarter whose Z.1 release should be available by *now*.

    Known official release dates take precedence. For quarters not in the small
    calendar map, use a conservative ~75-day post-quarter-end release lag.
    """
    now_ts = pd.Timestamp(now or datetime.now(timezone.utc)).tz_localize(None)
    # Check known release dates first.
    known = []
    for qlabel, d in Z1_KNOWN_RELEASE_DATES.items():
        dt = pd.Timestamp(d)
        if dt <= now_ts.normalize():
            known.append((pd.Period(qlabel, freq="Q"), dt))
    # Generic candidate from typical lag.
    current_q = now_ts.to_period("Q")
    generic = []
    for offset in range(0, 8):
        q = current_q - offset
        due = q.end_time.normalize() + pd.Timedelta(days=Z1_TYPICAL_RELEASE_LAG_DAYS)
        if due <= now_ts.normalize():
            generic.append((q, due))
            break
    candidates = known + generic
    if not candidates:
        q = current_q - 1
        return q, None
    q, due = max(candidates, key=lambda x: x[0].ordinal)
    return q, str(pd.Timestamp(due).date())


def _next_z1_release_after(data_q: pd.Period) -> tuple[str, str | None]:
    nq = data_q + 1
    label = str(nq).replace("Q", "Q")
    # pd.Period string is already e.g. 2026Q2.
    known = Z1_KNOWN_RELEASE_DATES.get(str(nq))
    if known:
        return str(nq), known
    due = nq.end_time.normalize() + pd.Timedelta(days=Z1_TYPICAL_RELEASE_LAG_DAYS)
    return str(nq), str(due.date())


def summarize_treasury_financing(
    z1_hist: pd.DataFrame,
    money_hist: pd.DataFrame | None = None,
    funding_hist: pd.DataFrame | None = None,
) -> dict:
    if z1_hist is None or z1_hist.empty or "Net marketable Treasury issuance" not in z1_hist.columns:
        return {
            "available": False,
            "classification": {"state": "UNKNOWN", "score": None},
            "slr_policy": SLR_POLICY.copy(),
            "funding_layer": _summarize_funding(funding_hist),
        }

    issue_s = pd.to_numeric(z1_hist["Net marketable Treasury issuance"], errors="coerce").dropna()
    issue_s = issue_s[issue_s.abs() > 1e-9]
    if issue_s.empty:
        return {
            "available": False,
            "classification": {"state": "UNKNOWN", "score": None},
            "slr_policy": SLR_POLICY.copy(),
            "funding_layer": _summarize_funding(funding_hist),
        }

    # Headline monetary-capable absorption uses the latest quarter shared by all
    # depository components. Never mix a newer issuance observation with an older
    # bank flow merely to produce a number.
    bank_components = [
        "U.S.-chartered depository institutions",
        "Foreign banking offices in U.S.",
        "Banks in U.S.-affiliated areas",
        "Credit unions",
    ]
    core_labels = ["Net marketable Treasury issuance", "Federal Reserve / central bank", *bank_components]
    common_index = None
    for label in core_labels:
        if label not in z1_hist.columns:
            common_index = pd.Index([])
            break
        idx = pd.to_numeric(z1_hist[label], errors="coerce").dropna().index
        common_index = idx if common_index is None else common_index.intersection(idx)
    if common_index is None or len(common_index) == 0:
        return {
            "available": False,
            "classification": {"state": "UNKNOWN", "score": None},
            "slr_policy": SLR_POLICY.copy(),
            "funding_layer": _summarize_funding(funding_hist),
            "reason": "No common Z.1 quarter exists for issuance, Fed, and depository-sector flows.",
        }

    q = common_index.max()
    issuance = _series_value(z1_hist, "Net marketable Treasury issuance", q)
    if issuance is None or abs(issuance) <= 1e-9:
        return {
            "available": False,
            "classification": {"state": "UNKNOWN", "score": None},
            "slr_policy": SLR_POLICY.copy(),
            "funding_layer": _summarize_funding(funding_hist),
        }

    vals = {label: _series_value(z1_hist, label, q) for label in Z1_FINANCING_SERIES if label != "Net marketable Treasury issuance"}
    for label in OPTIONAL_Z1_FINANCING_SERIES:
        if label in z1_hist.columns:
            vals[label] = _series_value(z1_hist, label, q)
    fed = vals.get("Federal Reserve / central bank")
    bank_system = _sum_complete([vals.get(x) for x in bank_components])
    monetary = None if fed is None or bank_system is None else fed + bank_system

    insurance_pensions = _sum_complete([
        vals.get("Property-casualty insurance"), vals.get("Life insurance"), vals.get("Private pension funds"),
        vals.get("Federal government pension funds"), vals.get("State & local government pension funds"),
    ])
    investment_funds = _sum_complete([vals.get("Mutual funds"), vals.get("Closed-end funds"), vals.get("Exchange-traded funds")])
    nonfinancial_business = _sum_complete([vals.get("Nonfinancial corporate business"), vals.get("Nonfinancial noncorporate business")])
    other_financial = _sum_complete([
        vals.get("Government-sponsored enterprises"), vals.get("ABS issuers"),
        vals.get("Holding companies"), vals.get("Other financial business"),
    ])

    display = [
        ("Federal Reserve / central bank", fed, "MONETARY_CAPABLE"),
        ("Banking system / depositories", bank_system, "MONETARY_CAPABLE"),
        ("Foreign sector", vals.get("Foreign sector"), "END_BUYER"),
        ("Security brokers & dealers", vals.get("Security brokers & dealers"), "INTERMEDIARY_INVENTORY"),
        ("Money market funds", vals.get("Money market funds"), "END_BUYER_CASH_POOL"),
        ("Households & nonprofits", vals.get("Households & nonprofits"), "END_BUYER"),
        ("Mutual funds + ETFs + CEFs", investment_funds, "END_BUYER"),
        ("Hedge funds", vals.get("Hedge funds"), "LEVERAGED_END_BUYER"),
        ("Insurance + pensions", insurance_pensions, "END_BUYER"),
        ("State & local governments", vals.get("State & local governments"), "END_BUYER"),
        ("Nonfinancial business", nonfinancial_business, "END_BUYER"),
        ("GSE/ABS/holding/other financial", other_financial, "OTHER_FINANCIAL"),
    ]

    holder_rows = []
    known_sum = 0.0
    for label, value, role in display:
        share = None if value is None else value / issuance * 100.0
        if value is not None:
            known_sum += value
        holder_rows.append({"holder": label, "flow_saar_mn": value, "share_of_issuance_pct": share, "role": role})
    residual = issuance - known_sum
    holder_rows.append({
        "holder": "Unattributed / table residual",
        "flow_saar_mn": residual,
        "share_of_issuance_pct": residual / issuance * 100.0,
        "role": "RESIDUAL",
    })

    monetary_share = None if monetary is None else monetary / issuance * 100.0
    dealer = vals.get("Security brokers & dealers")
    foreign = vals.get("Foreign sector")
    mmf = vals.get("Money market funds")
    dealer_share = None if dealer is None else dealer / issuance * 100.0
    foreign_share = None if foreign is None else foreign / issuance * 100.0
    mmf_share = None if mmf is None else mmf / issuance * 100.0
    hedge = vals.get("Hedge funds")
    hedge_share = None if hedge is None else hedge / issuance * 100.0
    intermediated_share = None if monetary is None or dealer is None else (monetary + dealer) / issuance * 100.0

    money = _summarize_money(money_hist, q)
    funding = _summarize_funding(funding_hist)
    classification = classify_financing_regime(
        monetary_share, money.get("matched_confirmation_3m_annualized_pct"), dealer_share, foreign_share
    )

    # Historical headline shares use the same broad bank definition. Any missing
    # component stays NaN; it is never silently coerced to zero.
    hist_rows = []
    for idx, issue in issue_s.items():
        if not np.isfinite(issue) or abs(issue) < 1e-9:
            continue

        def at(label):
            v = _series_value(z1_hist, label, idx)
            return np.nan if v is None else v

        f = at("Federal Reserve / central bank")
        bank_vals = [at(x) for x in bank_components]
        bank = sum(bank_vals) if all(np.isfinite(x) for x in bank_vals) else np.nan
        dealer_h, foreign_h, mmf_h = at("Security brokers & dealers"), at("Foreign sector"), at("Money market funds")
        hedge_h = at("Hedge funds") if "Hedge funds" in z1_hist.columns else np.nan
        mon = f + bank if np.isfinite(f) and np.isfinite(bank) else np.nan
        hist_rows.append({
            "quarter": _period_label(idx),
            "date": idx,
            "issuance_saar_mn": float(issue),
            "fed_share_pct": None if not np.isfinite(f) else f / issue * 100,
            "bank_share_pct": None if not np.isfinite(bank) else bank / issue * 100,
            "monetary_capable_share_pct": None if not np.isfinite(mon) else mon / issue * 100,
            "dealer_share_pct": None if not np.isfinite(dealer_h) else dealer_h / issue * 100,
            "foreign_share_pct": None if not np.isfinite(foreign_h) else foreign_h / issue * 100,
            "mmf_share_pct": None if not np.isfinite(mmf_h) else mmf_h / issue * 100,
            "hedge_fund_share_pct": None if not np.isfinite(hedge_h) else hedge_h / issue * 100,
        })

    now_ts = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
    current_q = now_ts.to_period("Q")
    data_q = pd.Timestamp(q).to_period("Q")
    current_quarter_gap = max(0, current_q.ordinal - data_q.ordinal)
    expected_q, expected_release_due = _expected_latest_z1_quarter(now_ts)
    release_lag_quarters = max(0, expected_q.ordinal - data_q.ordinal)
    if release_lag_quarters == 0:
        timeliness = "LATEST_EXPECTED_RELEASE"
    elif release_lag_quarters == 1:
        timeliness = "ONE_RELEASE_LATE"
    else:
        timeliness = "TWO_PLUS_RELEASES_LATE"
    next_q, next_release_date = _next_z1_release_after(data_q)
    classification["provisional"] = bool(release_lag_quarters > 0)
    classification["historical_period"] = bool(data_q < current_q)
    classification["data_timeliness"] = timeliness
    classification["quarter_lag"] = int(current_quarter_gap)  # backward-compatible: distance from current calendar quarter
    classification["release_lag_quarters"] = int(release_lag_quarters)
    classification["expected_latest_quarter"] = str(expected_q)
    classification["next_expected_quarter"] = next_q
    classification["next_release_date"] = next_release_date
    if release_lag_quarters > 0:
        classification["reason"] += " The holder data are behind the latest Z.1 release that should already be available, so treat this state as provisional."
    elif data_q < current_q:
        classification["reason"] += " This is the latest expected official quarterly Z.1 observation, but it is historical and should not be described as the current quarter's financing mix."

    slr_effect_q = pd.Period("2026Q2", freq="Q")
    if data_q < slr_effect_q:
        slr_test = {
            "status": "FULL_EFFECT_NOT_YET_TESTABLE",
            "reason": "The latest Z.1 financing quarter predates the April 1, 2026 full effective date. Early adoption was permitted January 1, so Q1 cannot isolate the rule's effect.",
        }
    else:
        slr_test = {
            "status": "POST_EFFECT_QUARTER_AVAILABLE",
            "reason": "A post-April-1 Z.1 quarter is available, but any change remains correlation unless bank/dealer balance-sheet evidence independently supports the transmission channel.",
        }

    detail_rows = [
        {"sector": label, "flow_saar_mn": vals.get(label), "share_of_issuance_pct": None if vals.get(label) is None else vals[label] / issuance * 100.0}
        for label in vals
    ]

    return {
        "available": True,
        "as_of_quarter": _period_label(q),
        "quarter_date": str(pd.Timestamp(q).date()),
        "issuance_saar_mn": issuance,
        "holders": holder_rows,
        "holder_detail": detail_rows,
        "monetary_capable_absorption_pct": monetary_share,
        "fed_absorption_pct": None if fed is None else fed / issuance * 100.0,
        "bank_absorption_pct": None if bank_system is None else bank_system / issuance * 100.0,
        "domestic_chartered_bank_absorption_pct": None if vals.get("U.S.-chartered depository institutions") is None else vals["U.S.-chartered depository institutions"] / issuance * 100.0,
        "eslr_relevant_bank_proxy_absorption_pct": None if vals.get("U.S.-chartered depository institutions") is None else vals["U.S.-chartered depository institutions"] / issuance * 100.0,
        "foreign_bank_office_absorption_pct": None if vals.get("Foreign banking offices in U.S.") is None else vals["Foreign banking offices in U.S."] / issuance * 100.0,
        "foreign_absorption_pct": foreign_share,
        "dealer_absorption_pct": dealer_share,
        "dealer_warehousing_pct": dealer_share,  # backward-compatible alias; do not infer involuntary warehousing
        "mmf_absorption_pct": mmf_share,
        "hedge_fund_absorption_pct": hedge_share,
        "monetary_plus_dealer_pct": intermediated_share,
        "money_confirmation": money,
        "funding_layer": funding,
        "classification": classification,
        "slr_policy": SLR_POLICY.copy(),
        "slr_transmission_test": slr_test,
        "data_timeliness": timeliness,
        "quarter_lag": int(current_quarter_gap),
        "release_lag_quarters": int(release_lag_quarters),
        "expected_latest_quarter": str(expected_q),
        "expected_release_due": expected_release_due,
        "next_expected_quarter": next_q,
        "next_release_date": next_release_date,
        "history": hist_rows,
        "methodology": {
            "holder_layer": "Z.1 F3.2.t quarterly marketable-Treasury transactions, SAAR; negative shares are preserved.",
            "funding_layer": "Z.1 repo levels plus hedge-fund Treasury/repo structure are overlays only and are never added to Treasury-holder flows; repo collateral is not Treasury-only and hedge-fund domestic repo liabilities are only a partial borrowing measure.",
            "bank_definition": "U.S.-chartered depository institutions + foreign banking offices in U.S. + affiliated-area banks + credit unions.",
            "slr_scope": "The eSLR change applies to covered large U.S. banking organizations, not identically to every institution in the broad banking-system holder bucket. Use U.S.-chartered depository absorption only as a broad proxy for the potentially eSLR-relevant bank channel; it is still wider than the GSIB-only population.",
            "monetary_capable": "Fed/central-bank + broad banking-system absorption; this measures monetary capacity/transmission, not proven money creation.",
            "money_confirmation": "Classification uses M2 and commercial-bank-deposit growth aligned to the same Z.1 quarter. A separate current-money reading is displayed as context only.",
            "h8_proxy": "Bank Treasury + agency securities is a high-frequency proxy and is not treated as Treasury-only ownership.",
            "dealer_rule": "Dealer net Treasury acquisition is inventory/intermediation exposure, not proof that securities were unsold or involuntarily warehoused.",
            "hedge_fund_holder_rule": "The 2026:Q2 Z.1 schema adds an explicit hedge-fund Treasury transaction row. It is included only when the official/FRED transaction series is actually available; market-value Treasury levels are never substituted for transaction flows.",
            "stablecoin_rule": "Stablecoin/tokenized-Treasury exposure is look-through context and is not added if the underlying security is already represented by a Z.1 holder.",
            "residual": "Residual is issuance minus displayed non-overlapping F3.2.t sectors; it remains unattributed rather than forced into a named buyer.",
        },
    }


def fetch_treasury_financing(
    start: str = "2006-01-01", fetcher: Callable = fetch_fred_series
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    errors = {}

    z1 = {}
    for label, sid in Z1_FINANCING_SERIES.items():
        try:
            z1[label] = fetcher(sid, start=start)
        except Exception as exc:
            z1[label] = pd.Series(dtype=float, name=sid)
            errors[f"holder:{label}"] = str(exc)
    optional_holder_errors = {}
    if pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None).normalize() >= OPTIONAL_Z1_ACTIVATION_DATE:
        for label, sid in OPTIONAL_Z1_FINANCING_SERIES.items():
            try:
                z1[label] = fetcher(sid, start=start)
            except Exception as exc:
                optional_holder_errors[label] = str(exc)

    z1_hist = pd.concat(z1, axis=1).sort_index() if z1 else pd.DataFrame()

    money = {}
    for label, sid in MONEY_CONFIRMATION_SERIES.items():
        try:
            money[label] = fetcher(sid, start="2018-01-01")
        except Exception as exc:
            money[label] = pd.Series(dtype=float, name=sid)
            errors[f"money:{label}"] = str(exc)
    money_hist = pd.concat(money, axis=1).sort_index() if money else pd.DataFrame()

    funding = {}
    for label, sid in FUNDING_LAYER_SERIES.items():
        try:
            funding[label] = fetcher(sid, start="2012-01-01")
        except Exception as exc:
            funding[label] = pd.Series(dtype=float, name=sid)
            errors[f"funding:{label}"] = str(exc)
    funding_hist = pd.concat(funding, axis=1).sort_index() if funding else pd.DataFrame()

    summary = summarize_treasury_financing(z1_hist, money_hist, funding_hist)
    summary["source_errors"] = errors
    summary["holder_series_ok"] = sum(1 for c in Z1_FINANCING_SERIES if c in z1_hist and not z1_hist[c].dropna().empty)
    summary["holder_series_total"] = len(Z1_FINANCING_SERIES)
    summary["holder_coverage_pct"] = 100.0 * summary["holder_series_ok"] / max(1, summary["holder_series_total"])
    summary["optional_holder_series"] = {
        "available": [label for label in OPTIONAL_Z1_FINANCING_SERIES if label in z1_hist and not z1_hist[label].dropna().empty],
        "errors": optional_holder_errors,
        "activation_date": str(OPTIONAL_Z1_ACTIVATION_DATE.date()),
    }
    summary["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    return z1_hist, money_hist, funding_hist, summary
