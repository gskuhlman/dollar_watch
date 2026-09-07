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
    "Nonfinancial corporate business": "BOGZ1FA103061103Q",
    "Nonfinancial noncorporate business": "BOGZ1FA113061003Q",
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
}

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
        confirms.append("dealer warehousing >=15% of issuance")
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
            "Monetary-capable absorption exceeds 50%, money/deposit growth is >6% annualized, "
            "and a market-structure confirmation is active."
        )
    elif m >= 35 and g is not None and g >= 5:
        state = "ORANGE"
        reason = (
            "Monetary-capable absorption is >=35% and broad-money/deposit growth confirms a monetary backdrop."
        )
    elif m >= 20:
        state = "YELLOW"
        reason = "Fed/bank absorption is elevated but does not yet meet the monetization-like confirmation test."
    else:
        state = "GREEN"
        reason = "Private/foreign market financing dominates relative to monetary-capable institutions."
    return {"state": state, "score": round(score, 1), "reason": reason, "confirmations": confirms}


def _summarize_money(money_hist: pd.DataFrame | None) -> dict:
    out = {
        "m2_3m_annualized_pct": None,
        "deposits_3m_annualized_pct": None,
        "confirmation_3m_annualized_pct": None,
        "bank_treasury_agency_3m_change_bn": None,
        "as_of": None,
    }
    if money_hist is None or money_hist.empty:
        return out
    m2 = money_hist["M2 money stock"] if "M2 money stock" in money_hist else pd.Series(dtype=float)
    dep = money_hist["Commercial bank deposits"] if "Commercial bank deposits" in money_hist else pd.Series(dtype=float)
    sec = money_hist["Bank Treasury + agency securities"] if "Bank Treasury + agency securities" in money_hist else pd.Series(dtype=float)
    mg, dg = _annualized_growth(m2, 91), _annualized_growth(dep, 91)
    vals_g = [x for x in [mg, dg] if x is not None]
    confirmation = sum(vals_g) / len(vals_g) if vals_g else None

    sec_change = None
    ssec = pd.to_numeric(sec, errors="coerce").dropna().sort_index()
    if not ssec.empty:
        prior = ssec.loc[ssec.index <= ssec.index[-1] - pd.Timedelta(days=91)]
        if not prior.empty:
            sec_change = float(ssec.iloc[-1] - prior.iloc[-1])
    latest_dates = [
        s.dropna().index[-1]
        for s in [m2, dep, sec]
        if isinstance(s, pd.Series) and not s.dropna().empty
    ]
    return {
        "m2_3m_annualized_pct": mg,
        "deposits_3m_annualized_pct": dg,
        "confirmation_3m_annualized_pct": confirmation,
        "bank_treasury_agency_3m_change_bn": sec_change,
        "as_of": str(max(latest_dates).date()) if latest_dates else None,
    }


def _summarize_funding(funding_hist: pd.DataFrame | None) -> dict:
    """Latest repo levels and one-quarter changes; never counted as Treasury demand."""
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
    dealer_liab, dealer_asset = by.get("Dealer repo liabilities"), by.get("Dealer repo assets")
    dealer_gross = None if dealer_liab is None or dealer_asset is None else dealer_liab + dealer_asset
    dealer_net_borrow = None if dealer_liab is None or dealer_asset is None else dealer_liab - dealer_asset
    return {
        "available": bool(rows),
        "as_of_quarter": _period_label(max(latest_dates)) if latest_dates else None,
        "rows": rows,
        "dealer_repo_gross_bn": dealer_gross,
        "dealer_repo_net_borrowing_bn": dealer_net_borrow,
        "mmf_repo_assets_bn": by.get("MMF repo assets"),
        "note": (
            "Repo is a funding/intermediation overlay, not a Treasury-holder bucket. Z.1 repo collateral is not Treasury-only, "
            "so these levels diagnose balance-sheet leverage/capacity rather than direct deficit absorption."
        ),
    }


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
    intermediated_share = None if monetary is None or dealer is None else (monetary + dealer) / issuance * 100.0

    money = _summarize_money(money_hist)
    funding = _summarize_funding(funding_hist)
    classification = classify_financing_regime(
        monetary_share, money.get("confirmation_3m_annualized_pct"), dealer_share, foreign_share
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
        })

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
        "foreign_bank_office_absorption_pct": None if vals.get("Foreign banking offices in U.S.") is None else vals["Foreign banking offices in U.S."] / issuance * 100.0,
        "foreign_absorption_pct": foreign_share,
        "dealer_warehousing_pct": dealer_share,
        "mmf_absorption_pct": mmf_share,
        "monetary_plus_dealer_pct": intermediated_share,
        "money_confirmation": money,
        "funding_layer": funding,
        "classification": classification,
        "slr_policy": SLR_POLICY.copy(),
        "history": hist_rows,
        "methodology": {
            "holder_layer": "Z.1 F3.2.t quarterly marketable-Treasury transactions, SAAR; negative shares are preserved.",
            "funding_layer": "Z.1 F4.1.s repo levels are overlays only and are never added to Treasury-holder flows; repo collateral is not Treasury-only.",
            "bank_definition": "U.S.-chartered depository institutions + foreign banking offices in U.S. + affiliated-area banks + credit unions.",
            "slr_scope": "The eSLR change applies to covered large U.S. banking organizations, not identically to every institution in the broad banking-system holder bucket.",
            "monetary_capable": "Fed/central-bank + broad banking-system absorption; this measures monetary capacity/transmission, not proven money creation.",
            "money_confirmation": "Average of 3-month annualized M2 and commercial-bank-deposit growth when available.",
            "h8_proxy": "Bank Treasury + agency securities is a high-frequency proxy and is not treated as Treasury-only ownership.",
            "dealer_rule": "Dealer Treasury holdings are warehousing/intermediation, not final end-buyer demand.",
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
    summary["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    return z1_hist, money_hist, funding_hist, summary
