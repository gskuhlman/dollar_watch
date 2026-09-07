import os
import tempfile
from pathlib import Path

from dollar_dashboard.official_policy import _parse_yen_intervention_amount, canonical_verification_leads, TREASURY_BESSENT_UEDA, TREASURY_GENIUS_20260817, NYFED_Q2_2026_FX
from dollar_dashboard.verification import canonical_source_candidates
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES


def _ovs():
    return {k:{'value':0,'verification_status':'UNVERIFIED','source_url':'','source_tier':'UNSOURCED'} for k in DEFAULT_OVERRIDES}


def _snap():
    return {
      'market_summary':{},'fred_summary':{},
      'component_confidence':{'market':100,'fred':100,'auction':90,'cftc':90,'tic':35,'tic_transactions':35,'cofer':35,'fiscal':65,'stablecoin':100,'news':0,'buyback_schedule':100,'buyback_results':90,'buyback':90,'official_policy':100},
      'auction_stress_auto':0,'cftc_usd_downside_pressure':0,'fx_positioning_squeeze_risk':60,
      'tic_dedollarization_pressure':0,'cofer_dedollarization_pressure':0,'fiscal_flow_stress_auto':0,'stablecoin_dollar_support_auto':20,
      'treasury_buyback_meta':{'intensity':20,'intensity_status':'KNOWN'},'offshore_usd_funding_meta':{'coverage':55},
    }


def test_japan_mof_amount_parser():
    assert _parse_yen_intervention_amount('外国為替平衡操作額 15兆3,993億円') == 15_399_300_000_000


def test_canonical_topic_routes_precede_generic_search():
    c=canonical_source_candidates('Bilateral FX policy','Treasury supported Japan steps addressing yen undervaluation and exchange-rate volatility')
    assert any(x['url']==TREASURY_BESSENT_UEDA for x in c)
    c=canonical_source_candidates('Stablecoins','Treasury says stablecoin policy supports the dollar reserve currency role')
    assert any(x['url']==TREASURY_GENIUS_20260817 for x in c)
    c=canonical_source_candidates('FX intervention','The Federal Reserve and U.S. Treasury did not intervene in FX markets in Q2 2026')
    assert any(x['url']==NYFED_Q2_2026_FX for x in c)


def test_structured_japan_intervention_is_fx_catalyst_not_broad_devaluation():
    base=_snap(); neutral=score(base,{'scores':{}},_ovs())
    cur=_snap(); cur['official_policy_meta']={
      'japan_fx_intervention':{'ok':True,'intervention_occurred':True,'amount_trillion_yen':15.3993,'period_end':'2026-08-26'},
      'us_fx_intervention':{'ok':True,'finding':'NO_US_FX_INTERVENTION'},
    }
    out=score(cur,{'scores':{}},_ovs())
    assert out['regimes']['FX positioning squeeze'] > neutral['regimes']['FX positioning squeeze']
    assert out['components']['Japan MOF intervention catalyst'] > 0
    # No-U.S.-direct-intervention finding is modest counterevidence, not proof of broad policy.
    assert out['regimes']['Managed dollar devaluation'] <= neutral['regimes']['Managed dollar devaluation']
    assert out['regime_evidence_coverage_details']['Managed dollar devaluation']['critical'] >= 25


def test_approved_bilateral_policy_targets_fx_not_managed():
    base=_snap(); neutral=score(base,{'scores':{}},_ovs())
    cur=_snap(); cur['approved_verification_evidence']=[{
      'bucket':'Bilateral FX policy','effect_target':'fx_positioning_squeeze','effect_direction':1,'effect_weight':8,
      'action_class':'BILATERAL_FX_POLICY','claim':'supported yen adjustment'
    }]
    out=score(cur,{'scores':{}},_ovs())
    assert out['regimes']['FX positioning squeeze'] > neutral['regimes']['FX positioning squeeze']
    assert out['regimes']['Managed dollar devaluation'] == neutral['regimes']['Managed dollar devaluation']


def test_canonical_queue_rows_keep_action_class_and_exact_candidate():
    b={'japan_fx_intervention':{'ok':True,'intervention_occurred':True,'amount_trillion_yen':15.3993,'source_url':'https://www.mof.go.jp/example'},
       'canonical_statements':[{'reachable':True,'bucket':'Bilateral FX policy','claim':'x'*20,'effect_target':'fx_positioning_squeeze','effect_direction':1,'effect_weight':8,'action_class':'BILATERAL_FX_POLICY','source_url':TREASURY_BESSENT_UEDA,'final_url':TREASURY_BESSENT_UEDA}]}
    rows=canonical_verification_leads(b)
    assert any(r.get('structured_fact') and r.get('action_class')=='BILATERAL_FX_INTERVENTION' for r in rows)
    exact=next(r for r in rows if not r.get('structured_fact'))
    assert exact['candidate_url']==TREASURY_BESSENT_UEDA and exact['status']=='SOURCE_FOUND'


def test_storage_persists_action_class_and_does_not_reset_checked_source():
    tmp=Path(tempfile.mkdtemp())/'v31.sqlite'
    os.environ['DOLLAR_DASHBOARD_DB']=str(tmp)
    import dollar_dashboard.storage as st
    row={'priority':'P0','bucket':'Bilateral FX policy','claim':'Treasury supports yen stabilization policy','source':'canonical','link':TREASURY_BESSENT_UEDA,
         'preferred_verification_source':TREASURY_BESSENT_UEDA,'status':'SOURCE_FOUND','candidate_url':TREASURY_BESSENT_UEDA,'candidate_tier':'PRIMARY','candidate_relevance':100,'relevance_status':'RELEVANT',
         'effect_target':'fx_positioning_squeeze','effect_direction':1,'effect_weight':8,'action_class':'BILATERAL_FX_POLICY'}
    st.upsert_verification_queue([row]); q=st.recent_verification_queue(10)[0]
    assert q['action_class']=='BILATERAL_FX_POLICY' and q['status']=='SOURCE_FOUND'
    st.update_verification_queue_check(q['id'],candidate_url=TREASURY_BESSENT_UEDA,candidate_tier='PRIMARY',candidate_relevance=100,relevance_status='RELEVANT',verdict='SUPPORTED',explanation='supported',status='CHECKED')
    st.upsert_verification_queue([row])
    q2=st.recent_verification_queue(10)[0]
    assert q2['status']=='CHECKED'


if __name__=='__main__':
    test_japan_mof_amount_parser(); test_canonical_topic_routes_precede_generic_search(); test_structured_japan_intervention_is_fx_catalyst_not_broad_devaluation(); test_approved_bilateral_policy_targets_fx_not_managed(); test_canonical_queue_rows_keep_action_class_and_exact_candidate(); test_storage_persists_action_class_and_does_not_reset_checked_source()
    print('v3.1 tests passed')
