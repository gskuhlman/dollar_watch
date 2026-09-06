from __future__ import annotations

import os, tempfile
from unittest.mock import patch
import pandas as pd

from dollar_dashboard.buybacks import _result_url_from_operation_date, fetch_buyback_results
from dollar_dashboard.triggers import evaluate_triggers
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES
from dollar_dashboard.storage import save_verification_check, recent_verification_checks
from dollar_dashboard.verification import _anchor_score, _tokens


def _ovs():
    return {k:{'value':0,'verification_status':'UNVERIFIED','source_url':'','source_tier':'UNSOURCED'} for k in DEFAULT_OVERRIDES}


def test_buyback_filename_dst_conversion():
    # Sep 3 is EDT -> 13:40 ET = 17:40 UTC, matching TreasuryDirect BBR naming.
    u=_result_url_from_operation_date('2026-09-03')
    assert u.endswith('/2026/BBR_20260903174000.xml')
    # Feb 25 is EST -> 18:40 UTC.
    u2=_result_url_from_operation_date('2026-02-25')
    assert u2.endswith('/2026/BBR_20260225184000.xml')


def test_buyback_results_fallback_attempts_urls_when_schedule_future_only():
    schedule=pd.DataFrame([{'operation_date':pd.Timestamp('2099-09-09',tz='UTC'),'operation_start':pd.NaT}])
    class Resp:
        status_code=404; url='x'; text=''; content=b''; headers={}
        def raise_for_status(self): return None
    with patch('dollar_dashboard.buybacks._discover_result_links',return_value=[]), patch('dollar_dashboard.buybacks.requests.get',return_value=Resp()):
        df,meta=fetch_buyback_results(schedule,lookback_days=14,max_operations=8)
    assert df.empty
    assert meta['result_urls_attempted'] > 0
    assert 'bounded-regular-date-probe' in meta['result_discovery_strategy']


def test_repo_tail_is_separate_from_median_trigger():
    snap={
      'timestamp':'2026-09-06T16:00:00Z','auction_summary':[],'upcoming_auctions':[],
      'fred_summary':{
        '10Y term premium':{'last':0.88},'10Y breakeven inflation':{'last':2.35},
        'Central bank liquidity swaps (millions)':{'last':100},
        'SOFR-IORB spread':{'last':0.01},
        'SOFR99-IORB spread':{'last':0.10,'percentile_1y':97,'zscore_1y':2.2,'recent_obs_ge_10bp':2},
      },
      'market_summary':{'DXY':{'last':99,'3m':0},'Gold':{'3m':0.02}},'cftc_usd_downside_pressure':20,
    }
    by={x['id']:x for x in evaluate_triggers(snap,{})}
    assert by['repo_or_swap_stress']['status']=='NOT_TRIGGERED'
    assert by['repo_tail_stress']['status']=='TRIGGERED'


def test_global_funding_coverage_not_100_without_offshore_basis():
    snap={
      'market_summary':{},'fred_summary':{},'component_confidence':{'market':100,'fred':100,'auction':90,'cftc':90,'tic':35,'cofer':35,'fiscal':65,'stablecoin':100,'news':100,'buyback_schedule':100,'buyback_results':0,'buyback':55},
      'data_confidence':85,'auction_stress_auto':0,'cftc_usd_downside_pressure':0,'fx_positioning_squeeze_risk':0,'tic_dedollarization_pressure':0,'cofer_dedollarization_pressure':0,'fiscal_flow_stress_auto':0,'stablecoin_dollar_support_auto':20,'treasury_buyback_meta':{'intensity':20},
      'offshore_usd_funding_meta':{'available':False,'coverage':30,'reason':'basis unavailable'},
    }
    out=score(snap,{'scores':{}},_ovs())
    d=out['regime_evidence_coverage_details']['Dollar funding squeeze']
    assert d['domestic_funding_coverage']==100
    assert d['offshore_funding_coverage']==30
    assert d['critical'] < 80
    assert d['effective'] < 90


def test_verification_check_persistence():
    with tempfile.TemporaryDirectory() as d:
        os.environ['DOLLAR_DASHBOARD_DB']=os.path.join(d,'v.sqlite')
        rid=save_verification_check('Treasury did X','Treasury / Bessent','https://home.treasury.gov/test','SUPPORTED','source says X','glm')
        rows=recent_verification_checks(10)
        assert rid>0 and len(rows)==1
        assert rows[0]['verdict']=='SUPPORTED'
        assert rows[0]['source_tier']=='PRIMARY'


def test_primary_link_relevance_prefers_claim_terms():
    toks=_tokens('Treasury Secretary Bessent yen intervention September')
    high=_anchor_score(toks,'Bessent discusses yen intervention','/news/yen-intervention-september')
    low=_anchor_score(toks,'Budget forms','/forms/budget')
    assert high > low


if __name__=='__main__':
    test_buyback_filename_dst_conversion()
    test_buyback_results_fallback_attempts_urls_when_schedule_future_only()
    test_repo_tail_is_separate_from_median_trigger()
    test_global_funding_coverage_not_100_without_offshore_basis()
    test_verification_check_persistence()
    test_primary_link_relevance_prefers_claim_terms()
    print('v2.5 tests passed')
