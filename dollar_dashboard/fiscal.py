from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "dollar_watch/2.7 (+local research dashboard)"}
BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
MTS_SUMMARY = f"{BASE}/v1/accounting/mts/mts_receipts_outlays_deficit_surplus"
MTS_TABLE2 = f"{BASE}/v1/accounting/mts/mts_table_2"
DEBT_URL = f"{BASE}/v2/accounting/od/debt_to_penny"


def _num(v):
    try:
        if v in (None, ""):
            return np.nan
        return float(str(v).replace(",", ""))
    except Exception:
        return np.nan


def _request(url: str, size: int = 200) -> pd.DataFrame:
    r = requests.get(url, params={"sort": "-record_date", "page[size]": size}, headers=UA, timeout=20)
    r.raise_for_status()
    return pd.DataFrame(r.json().get("data", []))


def fetch_fiscal_pipeline() -> tuple[pd.DataFrame, dict[str, Any], float]:
    """Fetch monthly budget flow data. Flexible parser tolerates FiscalData schema changes."""
    errors = []
    for url in [MTS_SUMMARY, MTS_TABLE2]:
        try:
            df = _request(url, 500)
            if not df.empty:
                summary = summarize_fiscal(df)
                if summary:
                    return df, summary, float(summary.get("stress_score", 0.0))
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors) if errors else "FiscalData MTS returned no usable rows")


def _first(row: dict, names: list[str]):
    for n in names:
        if n in row and row[n] not in (None, ""):
            x = _num(row[n])
            if not pd.isna(x):
                return x
    return np.nan


def summarize_fiscal(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {}
    d = df.copy()
    if "record_date" in d.columns:
        d["record_date"] = pd.to_datetime(d["record_date"], errors="coerce")
        latest_date = d["record_date"].max()
        latest = d[d["record_date"].eq(latest_date)].copy()
    else:
        latest_date = pd.NaT
        latest = d.head(20)

    # Direct summary datasets often expose receipts/outlays/deficit on a single row.
    for _, r in latest.iterrows():
        row = r.to_dict()
        receipts = _first(row, ["current_fytd_rcpt_amt", "current_fytd_net_rcpt_amt", "current_fytd_gross_rcpt_amt", "fytd_receipts_amt"])
        outlays = _first(row, ["current_fytd_outly_amt", "current_fytd_net_outly_amt", "fytd_outlays_amt"])
        deficit = _first(row, ["current_fytd_dfct_sur_amt", "current_fytd_deficit_surplus_amt", "fytd_deficit_surplus_amt"])
        prior_deficit = _first(row, ["prior_fytd_dfct_sur_amt", "prior_fytd_deficit_surplus_amt", "prior_fytd_budget_amt"])
        if not pd.isna(receipts) and not pd.isna(outlays):
            if pd.isna(deficit):
                deficit = outlays - receipts
            return _finish(latest_date, receipts, outlays, deficit, prior_deficit)

    # Table 2-style dataset: find aggregate classification rows.
    desc_col = next((c for c in ["classification_desc", "classification", "line_item_desc"] if c in latest.columns), None)
    if desc_col:
        rows = {str(r[desc_col]).strip().lower(): r.to_dict() for _, r in latest.iterrows()}
        def find(patterns):
            for name, row in rows.items():
                if all(p in name for p in patterns):
                    return row
            return None
        rr = find(["total", "receipts"])
        ro = find(["total", "outlays"])
        rd = find(["deficit"]) or find(["surplus"])
        receipts = _first(rr or {}, ["current_fytd_budget_amt", "current_fytd_gross_rcpt_amt", "current_fytd_net_rcpt_amt"])
        outlays = _first(ro or {}, ["current_fytd_budget_amt", "current_fytd_net_outly_amt", "current_fytd_gross_outly_amt"])
        deficit = _first(rd or {}, ["current_fytd_budget_amt", "current_fytd_dfct_sur_amt"])
        prior = _first(rd or {}, ["prior_fytd_budget_amt", "prior_fytd_dfct_sur_amt"])
        if not pd.isna(receipts) and not pd.isna(outlays):
            if pd.isna(deficit): deficit = outlays - receipts
            return _finish(latest_date, receipts, outlays, deficit, prior)
    return {}


def _finish(date, receipts, outlays, deficit, prior_deficit):
    # Treasury reports deficit sign conventions differently across tables. Compare magnitudes.
    deficit_mag = abs(float(deficit))
    prior_mag = abs(float(prior_deficit)) if not pd.isna(prior_deficit) else np.nan
    deficit_receipts = 100.0 * deficit_mag / receipts if receipts else np.nan
    yoy = np.nan if pd.isna(prior_mag) or prior_mag == 0 else 100.0 * (deficit_mag / prior_mag - 1.0)
    stress = 10.0
    if not pd.isna(deficit_receipts):
        if deficit_receipts > 20: stress += 12
        if deficit_receipts > 30: stress += 12
        if deficit_receipts > 40: stress += 12
    if not pd.isna(yoy):
        if yoy > 10: stress += 10
        if yoy > 25: stress += 12
    return {
        "record_date": None if pd.isna(date) else str(pd.Timestamp(date).date()),
        "fytd_receipts_mn": float(receipts),
        "fytd_outlays_mn": float(outlays),
        "fytd_deficit_mn": float(deficit_mag),
        "prior_fytd_deficit_mn": None if pd.isna(prior_mag) else float(prior_mag),
        "deficit_to_receipts_pct": None if pd.isna(deficit_receipts) else float(deficit_receipts),
        "deficit_yoy_pct": None if pd.isna(yoy) else float(yoy),
        "stress_score": float(max(0, min(100, stress))),
    }
