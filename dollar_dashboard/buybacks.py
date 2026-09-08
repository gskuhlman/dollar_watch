from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import pandas as pd
import requests

UA = {"User-Agent": "dollar_watch/3.0 (+local research dashboard)"}
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




def _element_text(el: ET.Element) -> str:
    """Return the first useful scalar text under an XML element.

    Treasury buyback XML has changed shape over time. Some releases expose aggregate
    values as direct leaf text, while others wrap the scalar in a child node.  Flattening
    only leaf tags can therefore lose the semantic parent name (for example a generic
    ``<value>`` child under ``<maxParAmountToBeRedeemed>``).
    """
    direct=(el.text or "").strip()
    if direct:
        return direct
    for child in el.iter():
        if child is el:
            continue
        txt=(child.text or "").strip()
        if txt:
            return txt
    return ""


def _semantic_value(root: ET.Element, aliases: list[str], required_terms: tuple[str, ...] = ()):
    alias_norm={_norm(x) for x in aliases}
    for el in root.iter():
        tag=_norm(el.tag)
        alias_match=tag in alias_norm
        term_match=bool(required_terms) and all(term in tag for term in required_terms)
        if alias_match or term_match:
            txt=_element_text(el)
            if txt:
                return txt
    return None


def _semantic_money(root: ET.Element, aliases: list[str], required_terms: tuple[str, ...] = ()):
    return _money(_semantic_value(root, aliases, required_terms))


def _coalesced_money(rec: dict, root: ET.Element, aliases: list[str], required_terms: tuple[str, ...] = ()):
    v=_money(_first(rec, aliases))
    if v is not None and not pd.isna(v):
        return v
    v=_semantic_money(root, aliases, required_terms)
    return None if v is None or pd.isna(v) else v



def _all_tag_values(root: ET.Element, aliases: list[str]) -> list[str]:
    wanted={_norm(x) for x in aliases}
    out=[]
    for el in root.iter():
        if _norm(el.tag) in wanted:
            txt=_element_text(el)
            if txt:
                out.append(txt)
    return out


def _infer_maturity_bucket_from_xml(root: ET.Element, operation_date, security_type: str = "") -> tuple[str, str]:
    """Infer an operation sector from result-level security maturity dates when Treasury omits the bucket.

    Buyback result XMLs can contain repeated security rows while the operation-level maturity bucket is
    absent or lost by schema changes.  For long-end classification, the accepted/eligible securities'
    maturity dates are sufficient to distinguish the nominal 10Y-20Y and 20Y-30Y sectors.
    """
    vals=_all_tag_values(root,["maturityDate","securityMaturityDate","maturityDt"])
    dates=pd.to_datetime(pd.Series(vals,dtype='object'),errors='coerce',utc=True).dropna()
    base=pd.to_datetime(operation_date,errors='coerce',utc=True)
    if dates.empty or pd.isna(base):
        return "", "UNAVAILABLE"
    yrs=((dates-base).dt.total_seconds()/(365.25*86400)).sort_values()
    lo=float(yrs.min()); hi=float(yrs.max())
    st=(security_type or '').lower()
    prefix='TIPS' if 'tips' in st or 'inflation' in st else 'Nominal Coupons'
    if lo >= 18.0:
        return f"{prefix} 20Y to 30Y", "INFERRED_FROM_MATURITY_DATES"
    if lo >= 8.5 and hi > 10.0:
        return f"{prefix} 10Y to 20Y", "INFERRED_FROM_MATURITY_DATES"
    if lo >= 6.0 and hi <= 11.0:
        return f"{prefix} 7Y to 10Y", "INFERRED_FROM_MATURITY_DATES"
    if lo >= 4.0 and hi <= 8.0:
        return f"{prefix} 5Y to 7Y", "INFERRED_FROM_MATURITY_DATES"
    if lo >= 2.5 and hi <= 6.0:
        return f"{prefix} 3Y to 5Y", "INFERRED_FROM_MATURITY_DATES"
    if lo >= 1.5 and hi <= 4.0:
        return f"{prefix} 2Y to 3Y", "INFERRED_FROM_MATURITY_DATES"
    if hi <= 2.5:
        return f"{prefix} 1Mo to 2Y", "INFERRED_FROM_MATURITY_DATES"
    return "", "UNRESOLVED"


def _long_end_nominal_mask(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=bool)
    bucket=df.get('maturity_bucket',pd.Series('',index=df.index)).fillna('').astype(str).str.lower()
    stype=df.get('security_type',pd.Series('',index=df.index)).fillna('').astype(str).str.lower()
    long_sector=bucket.str.contains(r'(?:10\s*y.*20\s*y|20\s*y.*30\s*y|10\s*year.*20\s*year|20\s*year.*30\s*year)',regex=True,na=False)
    tips=bucket.str.contains('tips|inflation',regex=True,na=False) | stype.str.contains('tips|inflation',regex=True,na=False)
    return long_sector & ~tips

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
        "max_amount": _money(_first(rec, ["maxParAmountToBeRedeemed", "maxParAmtToBeRedeemed", "maximumParAmountToBeRedeemed", "maximumParAmtToBeRedeemed", "maximumParAmount", "maximumParAmt", "maxParAmount", "maxParAmt", "maximumAmount", "maxAmountToBeRedeemed"])),
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
    security_type=_first(rec, ["securityType"], "")
    maturity_bucket=_first(rec, ["maturityBucket", "maturitySector", "maturityDateRange"], "")
    bucket_source="RESULT_XML" if str(maturity_bucket).strip() else ""
    if not str(maturity_bucket).strip():
        maturity_bucket,bucket_source=_infer_maturity_bucket_from_xml(root, op if pd.notna(op) else start, security_type)
    return {
        "operation_date": op,
        "operation_start": start,
        "settlement_date": _to_et_datetime(_first(rec, ["settlementDate", "settlementDt"])),
        "operation_type": _first(rec, ["operationType", "buybackType"], ""),
        "security_type": security_type,
        "maturity_bucket": maturity_bucket,
        "maturity_bucket_source": bucket_source,
        "max_amount": _coalesced_money(rec, root, ["maxParAmountToBeRedeemed", "maxParAmtToBeRedeemed", "maximumParAmountToBeRedeemed", "maximumParAmtToBeRedeemed", "maximumParAmount", "maximumParAmt", "maxParAmount", "maxParAmt", "maxAmountToBeRedeemed"], ("par","redeem")),
        "total_offered": _coalesced_money(rec, root, ["totalParAmountOffered", "totalAmountOffered"], ("total","offered")),
        "total_accepted": _coalesced_money(rec, root, ["totalParAmountAccepted", "totalAmountAccepted"], ("total","accepted")),
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
    expected_urls = []
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
                urls.append(u); expected_urls.append(u)
        if expected_urls: strategies.append("schedule-derived")
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
    found_urls=set()
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
                rows.append(row); found_urls.add(u)
        except Exception as exc:
            failures.append({"url": u, "error": str(exc)})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.dropna(subset=["operation_date"], how="all").drop_duplicates(subset=["operation_date","maturity_bucket"], keep="last")
        df["offer_accept_ratio"] = pd.to_numeric(df["total_offered"], errors="coerce") / pd.to_numeric(df["total_accepted"], errors="coerce").replace(0, pd.NA)
        df = df.sort_values("operation_date")
    return df, {
        "result_urls_attempted": len(urls),
        "expected_result_urls": len(set(expected_urls)),
        "expected_results_found": len(set(expected_urls) & found_urls),
        "result_completeness_pct": (100.0 * len(set(expected_urls) & found_urls) / len(set(expected_urls))) if expected_urls else None,
        "result_operations": int(len(df)),
        "result_not_found": int(not_found),
        "result_failures": failures[:10],
        "result_discovery_strategy": "+".join(strategies) if strategies else "none",
        "results_source_url": BUYBACK_PAGE,
    }


def fetch_buyback_schedule(timeout: int = 25) -> tuple[pd.DataFrame, dict]:
    """V3.0 buyback collector.

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
        if not merged.empty:
            merged["has_result"] = True
    else:
        merged = schedule.copy()
        if not results.empty:
            key = ["operation_date"]
            rcols = ["operation_date", "operation_start", "operation_type", "security_type", "maturity_bucket", "maturity_bucket_source", "max_amount", "total_offered", "total_accepted", "issues_eligible", "issues_accepted", "offer_accept_ratio", "result_url"]
            rsmall = results[[c for c in rcols if c in results.columns]].drop_duplicates("operation_date", keep="last")
            merged = merged.merge(rsmall, on="operation_date", how="outer", suffixes=("", "_result"))
            # Completed result XMLs are authoritative for execution fields.  Coalesce result
            # maximum capacity and classification fields into the tentative-schedule row; V2.9
            # prevents dropped result max_amount here, creating a false zero-capacity signal.
            for col in ["operation_start", "operation_type", "security_type", "maturity_bucket", "maturity_bucket_source", "max_amount"]:
                rc=f"{col}_result"
                if rc in merged.columns:
                    if col not in merged.columns:
                        merged[col]=merged[rc]
                    else:
                        merged[col]=merged[col].where(merged[col].notna() & merged[col].astype(str).ne(""), merged[rc])
                    merged=merged.drop(columns=[rc])
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
            "long_end_max_amount": None,
            "intensity": None,
            "intensity_status": "UNKNOWN",
            "max_amount_parse_status": "UNKNOWN_OR_PARSE_FAILED",
            "results_available": False,
        }
    work = df.copy()
    work["operation_date"] = pd.to_datetime(work.get("operation_date"), errors="coerce", utc=True)
    long_mask = _long_end_nominal_mask(work)
    upcoming = work[work["operation_date"] > now]
    completed = work[work.get("has_result", pd.Series(False, index=work.index)).fillna(False).astype(bool)]
    long_upcoming = upcoming[long_mask.reindex(upcoming.index, fill_value=False)]
    long_completed = completed[long_mask.reindex(completed.index, fill_value=False)]

    max_amount = pd.to_numeric(work.get("max_amount"), errors="coerce") if "max_amount" in work else pd.Series(dtype=float)
    parsed_max_count = int(max_amount.notna().sum()) if len(max_amount) else 0
    result_max = pd.to_numeric(completed.get("max_amount"), errors="coerce") if not completed.empty and "max_amount" in completed else pd.Series(dtype=float)
    result_max_count = int(result_max.notna().sum()) if len(result_max) else 0
    total_max = float(max_amount.dropna().sum()) if parsed_max_count else None
    long_max_series = pd.to_numeric(long_upcoming.get("max_amount"), errors="coerce") if not long_upcoming.empty and "max_amount" in long_upcoming else pd.Series(dtype=float)
    long_max = float(long_max_series.dropna().sum()) if int(long_max_series.notna().sum()) else None

    offered = float(pd.to_numeric(completed.get("total_offered"), errors="coerce").fillna(0).sum()) if not completed.empty and "total_offered" in completed else 0.0
    accepted = float(pd.to_numeric(completed.get("total_accepted"), errors="coerce").fillna(0).sum()) if not completed.empty and "total_accepted" in completed else 0.0
    offer_accept = (offered / accepted) if accepted > 0 else None
    long_offered = float(pd.to_numeric(long_completed.get("total_offered"), errors="coerce").fillna(0).sum()) if not long_completed.empty and "total_offered" in long_completed else 0.0
    long_accepted = float(pd.to_numeric(long_completed.get("total_accepted"), errors="coerce").fillna(0).sum()) if not long_completed.empty and "total_accepted" in long_completed else 0.0
    long_completed_max_series = pd.to_numeric(long_completed.get("max_amount"), errors="coerce") if not long_completed.empty and "max_amount" in long_completed else pd.Series(dtype=float)
    long_completed_capacity = float(long_completed_max_series.dropna().sum()) if int(long_completed_max_series.notna().sum()) else None
    long_accept_capacity = (long_accepted / long_completed_capacity) if long_completed_capacity and long_completed_capacity > 0 else None
    long_offer_accept = (long_offered / long_accepted) if long_accepted > 0 else None
    long_offer_capacity = (long_offered / long_completed_capacity) if long_completed_capacity and long_completed_capacity > 0 else None
    completeness = meta.get("result_completeness_pct")
    result_classification = "COMPLETE" if completeness is not None and completeness >= 80 else ("INCOMPLETE" if completeness is not None else "UNKNOWN_EXPECTED_SET")
    conclusions_allowed = result_classification == "COMPLETE"

    # Policy-response intensity requires parsed maximum capacity.  Accepted/offered totals alone
    # do not reveal whether Treasury used 10%, 50% or 100% of its authorized operation size.
    # Unknown capacity is therefore UNKNOWN, never numeric zero.
    max_amount_known = parsed_max_count > 0 and (result_max_count > 0 or len(upcoming) > 0)
    intensity = None
    if max_amount_known:
        intensity = 0.0
        if len(long_upcoming):
            intensity += min(35.0, 8.0 * len(long_upcoming))
        if long_max is not None and long_max >= 4_000_000_000:
            intensity += 15.0
        if conclusions_allowed and not long_completed.empty:
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
        "long_end_nominal_completed_operations": int(len(long_completed)),
        "long_end_completed_total_offered": long_offered,
        "long_end_completed_total_accepted": long_accepted,
        "long_end_completed_capacity": long_completed_capacity,
        "long_end_acceptance_vs_capacity": None if long_accept_capacity is None else round(long_accept_capacity, 3),
        "long_end_offer_accept_ratio": None if long_offer_accept is None else round(long_offer_accept, 3),
        "long_end_offer_to_capacity_ratio": None if long_offer_capacity is None else round(long_offer_capacity, 3),
        "total_max_amount": total_max,
        # Legacy field retained for UI/LLM compatibility.  Prefer observed completed-operation
        # capacity; otherwise show upcoming announced capacity.  Separate scoped fields below
        # prevent a null legacy value from contradicting a known completed-capacity calculation.
        "long_end_max_amount": long_completed_capacity if long_completed_capacity is not None else long_max,
        "long_end_max_amount_scope": "COMPLETED_RESULTS" if long_completed_capacity is not None else ("UPCOMING_SCHEDULE" if long_max is not None else "UNKNOWN"),
        "long_end_upcoming_max_amount": long_max,
        "parsed_max_amount_rows": parsed_max_count,
        "parsed_result_max_amount_rows": result_max_count,
        "completed_total_offered": offered,
        "completed_total_accepted": accepted,
        "completed_offer_accept_ratio": None if offer_accept is None else round(offer_accept, 3),
        "latest_completed_operation": None if latest_completed is None else latest_completed.isoformat(),
        "results_available": bool(len(completed)),
        "result_classification": result_classification,
        "results_conclusions_allowed": conclusions_allowed,
        "result_completeness_pct": completeness,
        "max_amount_parse_status": "OK" if max_amount_known else "UNKNOWN_OR_PARSE_FAILED",
        "intensity_status": "KNOWN" if intensity is not None else "UNKNOWN",
        "intensity": None if intensity is None else round(intensity, 1),
        "forward_policy_event": {
            "status":"ANNOUNCED",
            "effective_start":"2026-09-09",
            "effective_end":"2026-11-04",
            "long_end_nominal_max_per_operation":4000000000,
            "minimum_language":True,
            "source_url":"https://home.treasury.gov/news/press-releases/sb0607",
            "description":"Treasury announced nominal 10Y-20Y and 20Y-30Y liquidity-support buyback maximums of at least $4B per operation beginning Sep 9 through Nov 4; schedule detail may arrive separately."
        },
        "interpretation": "Treasury debt-management/liquidity-support activity. Long-end means nominal 10Y-20Y and 20Y-30Y sectors only. Not QE and not proof of failed auction demand.",
    }
