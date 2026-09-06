from __future__ import annotations
import os, tempfile
import pandas as pd

from dollar_dashboard.data import _normalize_auction_frame
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES
from dollar_dashboard.storage import save_snapshot_if_new, recent_snapshots


def test_completed_auction_filter_logic():
    raw=pd.DataFrame([
        {"auction_date":"2026-08-27","record_date":"2026-08-27","security_term":"10-Year","original_security_term":"10-Year","bid_to_cover_ratio":"2.55"},
        {"auction_date":"2026-09-09","record_date":"2026-09-15","security_term":"10-Year","original_security_term":"10-Year","bid_to_cover_ratio":None},
    ])
    out=_normalize_auction_frame(raw)
    today=pd.Timestamp('2026-09-06')
    completed=out[(out.auction_date<=today)&out.bid_to_cover_ratio.notna()]
    assert len(completed)==1
    assert str(completed.iloc[0].auction_date.date())=='2026-08-27'


def test_run_deduplication():
    with tempfile.TemporaryDirectory() as d:
        os.environ['DOLLAR_DASHBOARD_DB']=os.path.join(d,'t.sqlite')
        payload={'timestamp':'2026-09-06T15:00:00Z','scores':{'regimes':{}}}
        a,new1=save_snapshot_if_new(payload,payload['timestamp'])
        b,new2=save_snapshot_if_new(payload,payload['timestamp'])
        assert new1 is True and new2 is False and a==b
        rows=recent_snapshots(10)
        assert len(rows)==1 and rows[0]['_app_version']=='2.6.0'


def test_regime_coverage_separate_from_risk():
    snap={
        'market_summary':{},'fred_summary':{},'component_confidence':{
            'market':100,'fred':100,'auction':100,'cftc':90,'tic':35,'cofer':35,'fiscal':65,'stablecoin':100,'news':50,'buyback':90
        },
        'data_confidence':80,
        'auction_stress_auto':0,'cftc_usd_downside_pressure':0,'fx_positioning_squeeze_risk':0,
        'tic_dedollarization_pressure':0,'cofer_dedollarization_pressure':0,'fiscal_flow_stress_auto':0,
        'stablecoin_dollar_support_auto':20,'treasury_buyback_meta':{'intensity':20},
    }
    ovs={k:{'value':0,'verification_status':'UNVERIFIED','source_url':'','source_tier':'UNSOURCED'} for k in DEFAULT_OVERRIDES}
    out=score(snap,{'scores':{}},ovs)
    assert 'regime_evidence_coverage' in out
    assert out['regime_evidence_coverage']['Managed dollar devaluation'] < out['regime_evidence_coverage']['Dollar funding squeeze']

if __name__=='__main__':
    test_completed_auction_filter_logic(); test_run_deduplication(); test_regime_coverage_separate_from_risk()
    print('v2.3 tests passed')
