from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import pandas as pd
import requests

UA = {"User-Agent": "dollar_watch/2.5 (+local research dashboard)"}
BUYBACK_PAGE = "https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
SCHEDULE_XML_URL = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.xml"
RESULT_DIR = "https://www.treasurydirect.gov/instit/annceresult/press/preanre/{year}/"


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _local(name).lower())


def _money(v):
    if v is None:
        return None
    s = re.sub(r"[^0-9.\-]", "", str(v))
    return pd.to_numeric(s, errors="coerce")


def _first(rec: dict, aliases: list[str], default=None):
    nr = {_norm(k): v for k, v in rec.items()}
    for a in aliases:
        k = _norm(a)
        if k in nr and str(nr[k]).strip() not in {"", "None", "nan"}:
            return nr[k]
    return default


def _leaf_record(el: ET.Element) -> dict:
    rec = {}
    for c in el.iter():
        if len(list(c)) == 0:
            txt = (c.text or "").strip()
            if txt:
                rec[_local(c.tag)] = txt
    return rec


def _candidate_records(root: ET.Element) -> list[dict]:
    """Find repeated operation-like records without depending on one Treasury XML schema."""
    out, seen = [], set()
    for el in root.iter():
        rec = _leaf_record(el)
        keys = {_norm(k) for k in rec}
        has_date = any(k in keys for k in {"operationdate", "operationstartdtm", "operationstartdatetime", "operationstartdate"})
        has_bucket = any(k in keys for k in {"maturitybucket", "maturitysector", "maturitydaterange", "operationtype"})
        has_amount = any("amount" in k or "par" in k for k in keys)
        if has_date and (has_bucket or has_amount) and len(rec) >= 3:
            ident = tuple(sorted(rec.items()))
            if ident not in seen:
                seen.add(ident)
                out.append(rec)
    # Prefer smaller, row-like records over ancestors that contain many duplicate child fields.
    if not out:
        return []
    sizes = [len(x) for x in out]
    cutoff = max(8, min(sizes) + 12)
    compact = [x for x in out if len(x) <= cutoff]
    return compact or out


def _to_et_datetime(v) -> pd.Timestamp | pd.NaT:
    if v is None or str(v).strip() == "":
        return pd.NaT
    s = str(v).strip()
    ts = pd.to_datetime(s, errors="coerce", utc=True)
    if pd.notna(ts):
        return ts
    # Treasury schedule strings can omit an offset while documenting Eastern Time.
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return pd.NaT
    try:
        if ts.tzinfo is None:
            py = ts.to_pydatetime().replace(tzinfo=ZoneInfo("America/New_York"))
            return pd.Timestamp(py).tz_convert("UTC")
        return pd.Timestamp(ts).tz_convert("UTC")
    except Exception:
        return pd.NaT


def _normalize_schedule_record(rec: dict) -> dict:
    start = _first(rec, ["operationStartDtm", "operationStartDatetime", "operationStartDateTime", "operationStart"])
    op_date = _first(rec, ["operationDate", "operationDt"])
    start_ts = _to_et_datetime(start)
    op_ts = _to_et_datetime(op_date)
    if pd.isna(op_ts) and pd.notna(start_ts):
        op_ts = start_ts.normalize()
    return {
        "operation_date": op_ts,
        "operation_start": start_ts,
        "settlement_date": _to_et_datetime(_first(rec, ["settlementDate", "settlementDt"])),
        "operation_type": _first(rec, ["operationType", "buybackType", "type"], ""),
        "security_type": _first(rec, ["securityType"], ""),
        "maturity_bucket": _first(rec, ["maturityBucket", "maturitySector", "maturityDateRange"], ""),
        "max_amount": _money(_first(rec, ["maxParAmountToBeRedeemed", "maximumParAmount", "maxParAmount", "maximumAmount"])),
        "operation_status": _first(rec, ["operationStatus"], "SCHEDULED"),
        "announcement_type": _first(rec, ["announcementType"], ""),
        "source_kind": "SCHEDULE",
    }


def fetch_tentative_schedule(timeout: int = 25) -> tuple[pd.DataFrame, dict]:
    r = requests.get(SCHEDULE_XML_URL, headers=UA, timeout=timeout)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    rows = [_normalize_schedule_record(x) for x in _candidate_records(root)]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.dropna(subset=["operation_date"], how="all").drop_duplicates(
            subset=["operation_date", "operation_start", "maturity_bucket", "operation_type"], keep="last"
        ).sort_values(["operation_date", "operation_start"], na_position="last")
    return df, {
        "schedule_source_url": SCHEDULE_XML_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "schedule_operations": int(len(df)),
    }


def _result_url_from_start(start_ts) -> str | None:
    ts = pd.to_datetime(start_ts, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    stamp = ts.strftime("%Y%m%d%H%M%S")
    return urljoin(RESULT_DIR.format(year=ts.year), f"BBR_{stamp}.xml")


def _result_url_from_operation_date(operation_date, local_hour: int = 13, local_minute: int = 40) -> str | None:
    """Construct the official BBR result filename from the operation date.

    TreasuryDirect documents that BBR filenames contain operation date + start time in GMT.
    Current regular buyback operations normally start at 1:40 p.m. ET.  This fallback is
    used only when the tentative schedule does not expose a usable operation-start field.
    """
    ts = pd.to_datetime(operation_date, errors="coerce")
    if pd.isna(ts):
        return None
    d = ts.date()
    et = datetime(d.year, d.month, d.day, local_hour, local_minute, tzinfo=ZoneInfo("America/New_York"))
    utc = pd.Timestamp(et).tz_convert("UTC")
    return urljoin(RESULT_DIR.format(year=utc.year), f"BBR_{utc.strftime('%Y%m%d%H%M%S')}.xml")


def _recent_standard_result_probe_urls(lookback_days: int = 70, max_urls: int = 36) -> list[str]:
    """Bounded fallback discovery for recent regular operations.

    Treasury generally conducts liquidity-support buybacks once or twice per week.  When the
    quarterly tentative XML contains only future rows, probe the official 1:40 p.m. ET result
    filename on recent Tue/Wed/Thu operation dates.  404s are normal and ignored.
    """
    today = pd.Timestamp.now(tz="America/New_York").normalize()
    urls=[]
    for days in range(0, lookback_days + 1):
        d = today - pd.Timedelta(days=days)
        if d.weekday() not in {1,2,3}:  # Tue/Wed/Thu
            continue
        u=_result_url_from_operation_date(d)
        if u:
            urls.append(u)
        if len(urls) >= max_urls:
            break
    return urls


def _discover_result_links(timeout: int = 20) -> list[str]:
    """Fallback for TreasuryDirect page changes: collect any result XML links exposed in page HTML."""
    try:
        r = requests.get(BUYBACK_PAGE, headers=UA, timeout=timeout)
        r.raise_for_status()
    except Exception:
        return []
    links = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', r.text, re.I):
        full = urljoin(r.url, href)
        if re.search(r"/BBR_\d{14}\.xml(?:$|\?)", full, re.I):
            links.append(full.split("?", 1)[0])
        elif re.search(r"/BBR_\d{14}\.pdf(?:$|\?)", full, re.I):
            links.append(re.sub(r"\.pdf(?:\?.*)?$", ".xml", full, flags=re.I))
    return sorted(set(links))


def _normalize_result_xml(content: bytes, source_url: str) -> dict:
    root = ET.fromstring(content)
    rec = _leaf_record(root)
    op = _to_et_datetime(_first(rec, ["operationDate", "operationDt"]))
    start = _to_et_datetime(_first(rec, ["operationStartDtm", "operationStartDatetime", "operationStartDateTime"]))
    if pd.isna(op) and pd.notna(start):
        op = start.normalize()
    return {
        "operation_date": op,
        "operation_start": start,
        "settlement_date": _to_et_datetime(_first(rec, ["settlementDate", "settlementDt"])),
        "operation_type": _first(rec, ["operationType", "buybackType"], ""),
        "security_type": _first(rec, ["securityType"], ""),
        "maturity_bucket": _first(rec, ["maturityBucket", "maturitySector", "maturityDateRange"], ""),
        "max_amount": _money(_first(rec, ["maxParAmountToBeRedeemed", "maximumParAmount", "maxParAmount"])),
        "total_offered": _money(_first(rec, ["totalParAmountOffered", "totalAmountOffered"])),
        "total_accepted": _money(_first(rec, ["totalParAmountAccepted", "totalAmountAccepted"])),
        "issues_eligible": pd.to_numeric(_first(rec, ["noIssueEligible", "numberIssuesEligible", "numberOfIssuesEligible"]), errors="coerce"),
        "issues_accepted": pd.to_numeric(_first(rec, ["noIssuesAccepted", "numberIssuesAccepted", "numberOfIssuesAccepted"]), errors="coerce"),
        "operation_status": _first(rec, ["operationStatus"], "Results"),
        "announcement_type": _first(rec, ["announcementType"], ""),
        "result_url": source_url,
        "source_kind": "RESULT",
    }


def fetch_buyback_results(schedule: pd.DataFrame, timeout: int = 15, lookback_days: int = 180, max_operations: int = 50) -> tuple[pd.DataFrame, dict]:
    now = pd.Timestamp.now(tz="UTC")
    urls = []
    strategies=[]
    if schedule is not None and not schedule.empty:
        s = schedule.copy()
        s["operation_date"] = pd.to_datetime(s["operation_date"], errors="coerce", utc=True)
        s = s[(s["operation_date"] <= now) & (s["operation_date"] >= now - pd.Timedelta(days=lookback_days))]
        for _, row in s.tail(max_operations).iterrows():
            u = _result_url_from_start(row.get("operation_start"))
            if not u:
                u = _result_url_from_operation_date(row.get("operation_date"))
            if u:
                urls.append(u)
        if urls: strategies.append("schedule-derived")
    # Static HTML occasionally exposes direct BBR links; retain this cheap discovery path.
    discovered=_discover_result_links(timeout=min(timeout, 20))
    if discovered:
        urls.extend(discovered); strategies.append("page-links")
    # The TreasuryDirect table is client-rendered and can expose zero links to requests.  If the
    # schedule contains only future rows, probe a bounded set of recent regular operation dates.
    if len(urls) < 5:
        urls.extend(_recent_standard_result_probe_urls(lookback_days=min(lookback_days,70),max_urls=min(max_operations,36)))
        strategies.append("bounded-regular-date-probe")
    urls = list(dict.fromkeys(urls))[-max_operations:]

    rows, failures, not_found = [], [], 0
    for u in urls:
        try:
            r = requests.get(u, headers=UA, timeout=timeout)
            if r.status_code == 404:
                not_found += 1
                continue
            r.raise_for_status()
            row=_normalize_result_xml(r.content, u)
            # Only accept files that identify themselves as completed results or contain aggregate
            # offered/accepted amounts. This prevents a guessed URL from silently ingesting an
            # announcement XML under an unexpected server redirect.
            status=str(row.get("operation_status") or "").lower()
            if status == "results" or row.get("total_offered") is not None or row.get("total_accepted") is not None:
                rows.append(row)
        except Exception as exc:
            failures.append({"url": u, "error": str(exc)})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.dropna(subset=["operation_date"], how="all").drop_duplicates(subset=["operation_date","maturity_bucket"], keep="last")
        df["offer_accept_ratio"] = pd.to_numeric(df["total_offered"], errors="coerce") / pd.to_numeric(df["total_accepted"], errors="coerce").replace(0, pd.NA)
        df = df.sort_values("operation_date")
    return df, {
        "result_urls_attempted": len(urls),
        "result_operations": int(len(df)),
        "result_not_found": int(not_found),
        "result_failures": failures[:10],
        "result_discovery_strategy": "+".join(strategies) if strategies else "none",
        "results_source_url": BUYBACK_PAGE,
    }


def fetch_buyback_schedule(timeout: int = 25) -> tuple[pd.DataFrame, dict]:
    """V2.5 buyback collector.

    The official tentative schedule and completed TreasuryDirect result XMLs are separate evidence
    surfaces. A result-XML failure does not erase a successfully retrieved schedule, and a schedule
    is never treated as evidence that a buyback was actually executed.
    """
    schedule, meta = fetch_tentative_schedule(timeout=timeout)
    try:
        results, rmeta = fetch_buyback_results(schedule, timeout=min(timeout, 20))
    except Exception as exc:
        results, rmeta = pd.DataFrame(), {"result_operations": 0, "result_error": str(exc)}
    meta.update(rmeta)

    # Merge result fields onto scheduled operations when possible, but retain completed orphan
    # result rows if the current quarterly schedule no longer contains an older operation.
    if schedule.empty:
        merged = results.copy()
    else:
        merged = schedule.copy()
        if not results.empty:
            key = ["operation_date"]
            rcols = ["operation_date", "total_offered", "total_accepted", "issues_eligible", "issues_accepted", "offer_accept_ratio", "result_url"]
            rsmall = results[[c for c in rcols if c in results.columns]].drop_duplicates("operation_date", keep="last")
            merged = merged.merge(rsmall, on="operation_date", how="outer", suffixes=("", "_result"))
            merged["has_result"] = merged.get("result_url").notna()
        else:
            merged["has_result"] = False
    if not merged.empty:
        merged["operation_date"] = pd.to_datetime(merged["operation_date"], errors="coerce", utc=True)
        merged = merged.sort_values("operation_date")
    return merged, meta


def summarize_buybacks(df: pd.DataFrame, meta: dict) -> dict:
    now = pd.Timestamp.now(tz="UTC")
    if df is None or df.empty:
        return {
            **meta,
            "scheduled_operations": 0,
            "completed_operations": 0,
            "long_end_operations": 0,
            "long_end_max_amount": 0.0,
            "intensity": 0.0,
            "results_available": False,
        }
    work = df.copy()
    work["operation_date"] = pd.to_datetime(work.get("operation_date"), errors="coerce", utc=True)
    sector = work.get("maturity_bucket", pd.Series("", index=work.index)).astype(str).str.lower()
    long_mask = sector.str.contains(r"10|20|30|long", regex=True, na=False)
    upcoming = work[work["operation_date"] > now]
    completed = work[work.get("has_result", pd.Series(False, index=work.index)).fillna(False).astype(bool)]
    long_upcoming = upcoming[long_mask.reindex(upcoming.index, fill_value=False)]
    long_completed = completed[long_mask.reindex(completed.index, fill_value=False)]

    max_amount = pd.to_numeric(work.get("max_amount"), errors="coerce") if "max_amount" in work else pd.Series(dtype=float)
    total_max = float(max_amount.fillna(0).sum()) if len(max_amount) else 0.0
    long_max = float(pd.to_numeric(long_upcoming.get("max_amount"), errors="coerce").fillna(0).sum()) if not long_upcoming.empty and "max_amount" in long_upcoming else 0.0

    offered = float(pd.to_numeric(completed.get("total_offered"), errors="coerce").fillna(0).sum()) if not completed.empty and "total_offered" in completed else 0.0
    accepted = float(pd.to_numeric(completed.get("total_accepted"), errors="coerce").fillna(0).sum()) if not completed.empty and "total_accepted" in completed else 0.0
    offer_accept = (offered / accepted) if accepted > 0 else None

    # Policy-response intensity measures announced/used capacity, not market stress or QE.
    intensity = 0.0
    if len(long_upcoming):
        intensity += min(35.0, 8.0 * len(long_upcoming))
    if long_max >= 4_000_000_000:
        intensity += 15.0
    if not long_completed.empty:
        intensity += min(25.0, 5.0 * len(long_completed))
    intensity = min(100.0, intensity)

    latest_completed = None
    if not completed.empty:
        latest_completed = completed["operation_date"].max()
    return {
        **meta,
        "scheduled_operations": int(len(upcoming)),
        "completed_operations": int(len(completed)),
        "long_end_operations": int(len(long_upcoming)),
        "long_end_completed_operations": int(len(long_completed)),
        "total_max_amount": total_max,
        "long_end_max_amount": long_max,
        "completed_total_offered": offered,
        "completed_total_accepted": accepted,
        "completed_offer_accept_ratio": None if offer_accept is None else round(offer_accept, 3),
        "latest_completed_operation": None if latest_completed is None else latest_completed.isoformat(),
        "results_available": bool(len(completed)),
        "intensity": round(intensity, 1),
        "interpretation": "Treasury debt-management/liquidity-support activity. Not QE and not proof of failed auction demand.",
    }
