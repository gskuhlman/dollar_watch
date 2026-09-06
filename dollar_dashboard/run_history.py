from __future__ import annotations

from datetime import datetime, timezone
import uuid

APP_VERSION='3.0.0'
SCHEMA_VERSION='3.0'


def classify_snapshot_change(previous:dict|None,current:dict,current_scores:dict)->dict:
    if not previous:
        return {"kind":"BASELINE","items":[],"previous_run_id":None,"previous_schema":"NONE"}

    prev_app=previous.get('_app_version') or (previous.get('run_meta') or {}).get('app_version')
    prev_schema=previous.get('_schema_version') or (previous.get('run_meta') or {}).get('schema_version')
    prev_run=previous.get('_run_id') or (previous.get('run_meta') or {}).get('run_id') or previous.get('_id')
    if not prev_app or not prev_schema:
        return {
            "kind":"LEGACY_BASELINE",
            "items":[{"kind":"LEGACY_BASELINE","detail":"Previous snapshot predates reliable app/schema lineage; regime/taxonomy deltas are not treated as market changes."}],
            "previous_run_id":prev_run,
            "previous_schema":prev_schema or 'LEGACY',
        }

    items=[]
    prev_scores=previous.get('scores',{}) or {}
    prev_reg=prev_scores.get('regimes',{}) or {}
    cur_reg=current_scores.get('regimes',{}) or {}
    if prev_schema != SCHEMA_VERSION or set(prev_reg)!=set(cur_reg):
        items.append({"kind":"MODEL_TAXONOMY_CHANGE","detail":f"schema {prev_schema} -> {SCHEMA_VERSION}; regime keys {len(prev_reg)} -> {len(cur_reg)}"})

    prev_comp=(previous.get('component_confidence') or {})
    cur_comp=(current.get('component_confidence') or {})
    for k in sorted(set(cur_comp)-set(prev_comp)):
        items.append({"kind":"NEW_DATA_SOURCE","detail":k})

    # Revision/update detection. This deliberately says SOURCE UPDATE rather than pretending every
    # changed value is a market move; weekly/monthly sources are often revised.
    for section in ['market_summary','fred_summary']:
        a=previous.get(section,{}) or {}; b=current.get(section,{}) or {}
        for key in set(a)&set(b):
            av=a.get(key,{}); bv=b.get(key,{})
            if isinstance(av,dict) and isinstance(bv,dict):
                old=av.get('last'); new=bv.get('last')
                try:
                    if old is not None and new is not None and float(old)!=float(new):
                        kind='MARKET_UPDATE' if section=='market_summary' else 'SOURCE_UPDATE_OR_REVISION'
                        items.append({"kind":kind,"detail":f"{section}:{key} {old} -> {new}"})
                except Exception:
                    pass
    kind='NO_MATERIAL_CHANGE' if not items else 'MIXED_CHANGES'
    return {"kind":kind,"items":items[:75],"previous_run_id":prev_run,"previous_schema":prev_schema,"current_schema":SCHEMA_VERSION}


def lineage(parent_run_id=None,run_kind='ANALYSIS')->dict:
    return {
        "run_id":str(uuid.uuid4()),
        "parent_run_id":parent_run_id,
        "app_version":APP_VERSION,
        "schema_version":SCHEMA_VERSION,
        "run_kind":run_kind,
        "captured_at":datetime.now(timezone.utc).isoformat(),
    }
