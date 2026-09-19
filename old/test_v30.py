import os
import tempfile
from pathlib import Path
import pandas as pd

from dollar_dashboard.verification import _route_score, systematic_policy_leads
from dollar_dashboard.buybacks import summarize_buybacks
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES
from dollar_dashboard.triggers import evaluate_triggers
from dollar_dashboard.portfolio import scenario_hedge_alignment, recommend


def _snapshot_base():
    return {
        'market_summary': {}, 'fred_summary': {},
        'component_confidence': {'market':100,'fred':100,'auction':100,'cftc':100,'tic':100,'tic_transactions':100,'cofer':100,'fiscal':100,'stablecoin':100,'news':100,'buyback_schedule':100,'buyback_results':100,'buyback':100},
        'auction_stress_auto':0,'cftc_usd_downside_pressure':0,'fx_positioning_squeeze_risk':0,'tic_dedollarization_pressure':0,'cofer_dedollarization_pressure':0,'fiscal_flow_stress_auto':0,'stablecoin_dollar_support_auto':0,
        'treasury_buyback_meta':{'intensity':0,'intensity_status':'KNOWN'},
        'offshore_usd_funding_meta':{'coverage':55},
    }


def _overrides():
    return {k:{'value':0,'verification_status':'UNVERIFIED','source_url':'','source_tier':'UNSOURCED'} for k in DEFAULT_OVERRIDES}


def test_route_blocks_generic_treasury_pages():
    ok,_,reason=_route_score('Treasury / Bessent','https://home.treasury.gov/privacy-policy')
    assert not ok and 'blocked-route' in reason
    ok,bonus,reason=_route_score('Treasury / Bessent','https://home.treasury.gov/news/press-releases/sb0605')
    assert ok and bonus>0 and 'preferred-route' in reason


def test_systematic_claims_are_narrow_and_bidirectional():
    rows=systematic_policy_leads(max_rows=20)
    pro=[r for r in rows if r.get('effect_target')=='managed_devaluation' and float(r.get('effect_direction',0))>0]
    anti=[r for r in rows if r.get('effect_target')=='managed_devaluation' and float(r.get('effect_direction',0))<0]
    stable=[r for r in rows if r.get('bucket')=='Stablecoins']
    assert pro and anti and stable
    assert 'reserve-currency role' in stable[0]['claim']


def test_approved_policy_evidence_moves_score_both_directions():
    base=_snapshot_base(); news={'scores':{}}
    neutral=score(dict(base),news,_overrides())
    up=dict(base); up['approved_verification_evidence']=[{'bucket':'Treasury / Bessent','effect_target':'managed_devaluation','effect_direction':1,'effect_weight':10,'claim':'x'}]
    down=dict(base); down['approved_verification_evidence']=[{'bucket':'Treasury / Bessent','effect_target':'managed_devaluation','effect_direction':-1,'effect_weight':8,'claim':'y'}]
    su=score(up,news,_overrides()); sd=score(down,news,_overrides())
    assert su['regimes']['Managed dollar devaluation'] > neutral['regimes']['Managed dollar devaluation']
    assert sd['regimes']['Managed dollar devaluation'] < neutral['regimes']['Managed dollar devaluation']
    assert su['regime_evidence_coverage_details']['Managed dollar devaluation']['critical'] >= 35


def _trigger_snapshot(sofr=0.01, swaps=0, fima=0, le3=3, count=5):
    return {
      'timestamp':'2026-09-06T18:00:00Z','auction_summary':[],'upcoming_auctions':[],
      'market_summary':{},
      'fred_summary':{
        'SOFR-IORB spread':{'last':sofr,'recent_obs_le_3bp':le3,'recent_obs_count_5':count},
        'Central bank liquidity swaps (millions)':{'last':swaps},
        'FIMA repo - foreign official (millions)':{'last':fima},
      }
    }


def test_repo_recovery_requires_prior_active_state():
    cur=_trigger_snapshot()
    t=evaluate_triggers(cur,{},previous_triggers=[])
    by={x['id']:x for x in t}
    assert by['repo_stress_normalized']['status']=='NOT_TRIGGERED'
    prev=[{'id':'repo_or_swap_stress','status':'TRIGGERED'}]
    t=evaluate_triggers(cur,{},previous_triggers=prev)
    by={x['id']:x for x in t}
    assert by['repo_stress_normalized']['status']=='TRIGGERED'
    notyet=_trigger_snapshot(le3=1,count=5)
    t=evaluate_triggers(notyet,{},previous_triggers=prev)
    by={x['id']:x for x in t}
    assert by['repo_stress_normalized']['status']=='RECOVERING'


def test_buyback_legacy_long_end_capacity_is_reconciled():
    df=pd.DataFrame([{
        'operation_date':'2026-08-11','maturity_bucket':'Nominal Coupons 10Y to 20Y','security_type':'Nominal Coupons','has_result':True,
        'max_amount':2_000_000_000,'total_offered':5_000_000_000,'total_accepted':2_000_000_000,
    }])
    m=summarize_buybacks(df,{'result_completeness_pct':100})
    assert m['long_end_completed_capacity']==2_000_000_000
    assert m['long_end_max_amount']==2_000_000_000
    assert m['long_end_max_amount_scope']=='COMPLETED_RESULTS'


def test_funding_alignment_does_not_count_all_usd_assets_as_hedges():
    alloc={'T-bills / cash equivalents':25,'TIPS':20,'Gold':15,'Developed ex-US equities (unhedged)':17.5,'US real-asset / value equities':10,'Broad commodities / energy':0,'CHF / defensive FX':7.5,'Bitcoin':5}
    df=scenario_hedge_alignment(alloc)
    r=df[df['Scenario'].eq('Dollar funding squeeze')].iloc[0]
    assert r['Direct hedge %']==25.0
    assert r['USD-denominated rate-sensitive %']==20.0
    assert r['Vulnerable %']>=32.5



def test_funding_trigger_moves_toward_bills_not_nonusd():
    baseline={'T-bills / cash equivalents':25,'TIPS':20,'Gold':15,'Developed ex-US equities (unhedged)':17.5,'US real-asset / value equities':10,'Broad commodities / energy':0,'CHF / defensive FX':7.5,'Bitcoin':5}
    regimes={'Managed dollar devaluation':20,'Fiscal / Treasury supply stress':25,'Inflation / monetary debasement':15,'Dollar funding squeeze':80,'Reserve-confidence crisis':20,'FX positioning squeeze':20}
    trig=[{'id':'repo_or_swap_stress','status':'TRIGGERED'}]
    df,_=recommend(regimes,baseline,100000,min_trade_pct=1.0,min_trade_dollars=500,min_position_pct=2,confidence=100,machine_triggers=trig)
    r=dict(zip(df['Asset'],df['Recommended %']))
    assert r['T-bills / cash equivalents']>25
    assert r['Developed ex-US equities (unhedged)']<17.5
    assert r['Bitcoin']<5

def test_approved_queue_storage_gate():
    tmp=Path(tempfile.mkdtemp())/'v30.sqlite'
    os.environ['DOLLAR_DASHBOARD_DB']=str(tmp)
    import dollar_dashboard.storage as st
    row=systematic_policy_leads(max_rows=1)[0]
    st.upsert_verification_queue([row])
    q=st.recent_verification_queue(10)[0]
    st.update_verification_queue_check(q['id'],candidate_url='https://home.treasury.gov/news/press-releases/example',candidate_tier='PRIMARY',candidate_relevance=80,relevance_status='RELEVANT',verdict='SUPPORTED',explanation='supported',status='CHECKED')
    st.update_verification_queue_approval(q['id'],'APPROVED')
    ev=st.approved_verification_evidence(10)
    assert len(ev)==1 and ev[0]['effect_target']=='managed_devaluation' and ev[0]['effect_direction']!=0


if __name__=='__main__':
    test_route_blocks_generic_treasury_pages(); test_systematic_claims_are_narrow_and_bidirectional(); test_approved_policy_evidence_moves_score_both_directions(); test_repo_recovery_requires_prior_active_state(); test_buyback_legacy_long_end_capacity_is_reconciled(); test_funding_alignment_does_not_count_all_usd_assets_as_hedges(); test_funding_trigger_moves_toward_bills_not_nonusd(); test_approved_queue_storage_gate()
    print('v3.0 tests passed')
