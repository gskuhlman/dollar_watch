from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin

import pandas as pd
import requests

UA={"User-Agent":"dollar_watch/2.3 (+local research dashboard)"}
REFUNDING_PAGE="https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/most-recent-quarterly-refunding-documents"


def _local(tag:str)->str:
    return tag.split('}',1)[-1].lower()


def _text(el):
    return (el.text or '').strip() if el is not None else ''


def _find_buyback_xml(html:str, base_url:str)->str|None:
    # Prefer the anchor whose visible text explicitly says Buyback Schedule: XML Format.
    pat=re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>\s*Buyback Schedule:\s*XML Format\s*</a>',re.I|re.S)
    m=pat.search(html)
    if m: return urljoin(base_url,m.group(1))
    # Fallback: any XML-ish href near the words buyback schedule.
    for m in re.finditer(r'href=["\']([^"\']+)["\']',html,re.I):
        href=m.group(1)
        window=html[max(0,m.start()-250):m.end()+250].lower()
        if 'buyback' in window and ('xml' in href.lower() or 'xml' in window):
            return urljoin(base_url,href)
    return None


def fetch_buyback_schedule(timeout:int=25)->tuple[pd.DataFrame,dict]:
    r=requests.get(REFUNDING_PAGE,headers=UA,timeout=timeout); r.raise_for_status()
    xml_url=_find_buyback_xml(r.text,r.url)
    if not xml_url:
        raise ValueError('Could not locate Treasury Buyback Schedule XML link on most-recent-refunding page')
    x=requests.get(xml_url,headers=UA,timeout=timeout); x.raise_for_status()
    root=ET.fromstring(x.content)
    records=[]
    # Treasury XML format can evolve. Flatten leaf values for each repeated operation-like node.
    candidates=[]
    for el in root.iter():
        leaves=[c for c in list(el) if len(list(c))==0]
        names={_local(c.tag) for c in leaves}
        if len(leaves)>=3 and any('date' in n for n in names) and any(('amount' in n or 'maximum' in n or 'sector' in n or 'bucket' in n) for n in names):
            candidates.append(el)
    # choose smallest operation records; remove ancestors by using the common deepest-ish candidates
    seen=set()
    for el in candidates:
        rec={}
        for c in list(el):
            if len(list(c))==0:
                rec[_local(c.tag)]=_text(c)
        key=tuple(sorted(rec.items()))
        if key in seen: continue
        seen.add(key); records.append(rec)
    df=pd.DataFrame(records)
    meta={"source_url":xml_url,"retrieved_at":datetime.now(timezone.utc).isoformat(),"operations":len(df)}
    if df.empty:
        return df,meta
    # Best-effort normalized fields without discarding raw columns.
    def first(cols):
        for c in cols:
            if c in df.columns: return df[c]
        return pd.Series([None]*len(df),index=df.index)
    out=df.copy()
    out['operation_date']=pd.to_datetime(first(['operationdate','operation_date','date']),errors='coerce')
    out['maturity_sector']=first(['maturitysector','maturity_sector','bucket','sector'])
    out['operation_type']=first(['operationtype','operation_type','type'])
    amt=first(['maximumparamount','maximum_par_amount','maximumamount','maximum_amount','purchaseamount','purchase_amount'])
    out['max_amount']=pd.to_numeric(amt.astype(str).str.replace(r'[$,]','',regex=True),errors='coerce')
    return out,meta


def summarize_buybacks(df:pd.DataFrame, meta:dict)->dict:
    if df is None or df.empty:
        return {**meta,"scheduled_operations":0,"long_end_operations":0,"long_end_max_amount":0.0,"intensity":0.0}
    sector=df.get('maturity_sector',pd.Series('',index=df.index)).astype(str).str.lower()
    long_mask=sector.str.contains('10')|sector.str.contains('20')|sector.str.contains('30')|sector.str.contains('long')
    long_df=df[long_mask]
    total_amt=float(pd.to_numeric(df.get('max_amount'),errors='coerce').fillna(0).sum()) if 'max_amount' in df else 0.0
    long_amt=float(pd.to_numeric(long_df.get('max_amount'),errors='coerce').fillna(0).sum()) if 'max_amount' in long_df else 0.0
    intensity=0.0
    if len(long_df): intensity=min(100.0,20.0+8.0*len(long_df))
    if total_amt>0 and long_amt/total_amt>0.35: intensity=min(100.0,intensity+15.0)
    return {**meta,"scheduled_operations":int(len(df)),"long_end_operations":int(len(long_df)),"total_max_amount":total_amt,"long_end_max_amount":long_amt,"intensity":round(intensity,1)}
