from __future__ import annotations

from datetime import datetime, timezone
import uuid

APP_VERSION='2.3.0'
SCHEMA_VERSION='2.3'


def classify_snapshot_change(previous:dict|None,current:dict,current_scores:dict)->dict:
    if not previous:
        return {"kind":"BASELINE","items":[],"previous_run_id":None}
    items=[]
    prev_scores=previous.get('scores',{}) or {}
    prev_reg=prev_scores.get('regimes',{}) or {}
    cur_reg=current_scores.get('regimes',{}) or {}
    if set(prev_reg)!=set(cur_reg):
        items.append({"kind":"MODEL_TAXONOMY_CHANGE","detail":f"regime keys {len(prev_reg)} -> {len(cur_reg)}"})
    prev_comp=((previous.get('component_confidence') or {}))
    cur_comp=((current.get('component_confidence') or {}))
    for k in sorted(set(cur_comp)-set(prev_comp)):
        items.append({"kind":"NEW_DATA_SOURCE","detail":k})
    # Revision detection: values that changed while the reported observation date did not.
    for section in ['market_summary','fred_summary']:
        a=previous.get(section,{}) or {}; b=current.get(section,{}) or {}
        for key in set(a)&set(b):
            av=a.get(key,{}); bv=b.get(key,{})
            if isinstance(av,dict) and isinstance(bv,dict):
                old=av.get('last'); new=bv.get('last')
                try:
                    if old is not None and new is not None and float(old)!=float(new):
                        items.append({"kind":"MARKET_OR_SOURCE_UPDATE","detail":f"{section}:{key} {old} -> {new}"})
                except Exception: pass
    kind='NO_MATERIAL_CHANGE' if not items else 'MIXED_CHANGES'
    return {"kind":kind,"items":items[:50],"previous_run_id":previous.get('_run_id') or previous.get('_id')}


def lineage(parent_run_id=None,run_kind='ANALYSIS')->dict:
    return {
        "run_id":str(uuid.uuid4()),
        "parent_run_id":parent_run_id,
        "app_version":APP_VERSION,
        "schema_version":SCHEMA_VERSION,
        "run_kind":run_kind,
        "captured_at":datetime.now(timezone.utc).isoformat(),
    }
