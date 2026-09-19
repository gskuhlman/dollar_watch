from datetime import datetime, timezone

from dollar_dashboard.official_policy import _deterministic_statement_match, canonical_verification_leads, TREASURY_BESSENT_UEDA
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES


def _ovs():
    return {k:{'value':0,'verification_status':'UNVERIFIED','source_url':'','source_tier':'UNSOURCED'} for k in DEFAULT_OVERRIDES}


def _base():
    return {
        'market_summary': {
            'USDJPY': {'3m': -0.035}, 'EURUSD': {'3m': 0.025}, 'USDCHF': {'3m': -0.005},
            'DXY': {'last': 99, '1m': -0.01, '3m': -0.01},
        },
        'fred_summary': {},
        'component_confidence': {
            'market':100,'fred':100,'auction':90,'cftc':90,'tic':35,'tic_transactions':35,'cofer':35,
            'fiscal':65,'stablecoin':100,'news':0,'buyback_schedule':100,'buyback_results':90,'buyback':90,
        },
        'auction_stress_auto':0,'cftc_usd_downside_pressure':30,'fx_positioning_squeeze_risk':70,
        'tic_dedollarization_pressure':0,'cofer_dedollarization_pressure':0,'fiscal_flow_stress_auto':0,
        'stablecoin_dollar_support_auto':20,'treasury_buyback_meta':{'intensity':20,'intensity_status':'KNOWN'},
        'offshore_usd_funding_meta':{'coverage':55},
        'approved_verification_evidence':[],
    }


def _official(det=True):
    return {
        'japan_fx_intervention': {'ok':True,'intervention_occurred':True,'amount_trillion_yen':15.3993,'direction':'UNKNOWN','period_end':'2026-08-26','source_url':'https://www.mof.go.jp/x','fetch_mode':'LIVE'},
        'us_fx_intervention': {'ok':True,'finding':'NO_US_FX_INTERVENTION','source_url':'https://www.newyorkfed.org/x','period':'2026-Q2','fetch_mode':'LIVE'},
        'canonical_statements': [
            {'bucket':'Bilateral FX policy','claim':'Treasury supported Japan steps addressing yen undervaluation and volatility','effect_target':'fx_positioning_squeeze','effect_direction':1,'effect_weight':8,'action_class':'BILATERAL_FX_POLICY','deterministic_verified':det,'deterministic_validation':'PASS','final_url':TREASURY_BESSENT_UEDA,'fetch_mode':'LIVE_DIRECT','live_reachable':True},
            {'bucket':'Stablecoins','claim':'Treasury frames payment stablecoins as supporting the dollar reserve role','effect_target':'structural_dollar_support','effect_direction':1,'effect_weight':6,'action_class':'STRUCTURAL_DOLLAR_SUPPORT','deterministic_verified':det,'deterministic_validation':'PASS','final_url':'https://home.treasury.gov/sb0605','fetch_mode':'LIVE_DIRECT','live_reachable':True},
            {'bucket':'FX intervention','claim':'No US FX intervention in Q2','effect_target':'managed_devaluation','effect_direction':-1,'effect_weight':4,'action_class':'US_DIRECT_FX_INTERVENTION','deterministic_verified':det,'deterministic_validation':'PASS','final_url':'https://www.newyorkfed.org/q2','fetch_mode':'LIVE_DIRECT','live_reachable':True},
        ]
    }


def test_deterministic_anchor_validator_requires_all_groups():
    ok, missing = _deterministic_statement_match(
        'Treasury discussed yen undervaluation and excessive exchange-rate volatility.',
        (("yen",),("undervaluation",),("volatility",)),
    )
    assert ok and not missing
    ok2, missing2 = _deterministic_statement_match('Treasury discussed yen volatility.', (("yen",),("undervaluation",),("volatility",)))
    assert not ok2 and any('undervaluation' in x for x in missing2)


def test_canonical_deterministic_fact_skips_llm_queue_status():
    rows=canonical_verification_leads({'canonical_statements':[{
        'reachable':True,'deterministic_verified':True,'bucket':'Bilateral FX policy','claim':'x','effect_target':'fx_positioning_squeeze',
        'effect_direction':1,'effect_weight':8,'action_class':'BILATERAL_FX_POLICY','source_url':TREASURY_BESSENT_UEDA,'final_url':TREASURY_BESSENT_UEDA,
    }]})
    assert rows[0]['status']=='STRUCTURED_VERIFIED'
    assert rows[0]['verification_status']=='DETERMINISTIC_VERIFIED'
    assert rows[0]['structured_fact'] is True


def test_deterministic_facts_raise_coverage_but_keep_broad_intent_gate():
    s=_base(); s['official_policy_meta']=_official(True)
    out=score(s,{'scores':{}},_ovs())
    det=out['deterministic_verified_evidence']
    assert any(x['action_class']=='BILATERAL_FX_POLICY' for x in det)
    cov=out['regime_evidence_coverage_details']['Managed dollar devaluation']
    assert cov['direct_intervention_fact_coverage']==25.0
    assert cov['deterministic_policy_context_coverage']==20.0
    assert cov['human_approved_interpretive_coverage']==0.0
    assert cov['critical']==45.0  # better observed, but still below the 50% broad-intent language gate
    assert cov['broad_intent_human_gate'] is True


def test_deterministic_score_effect_is_smaller_than_human_approved_interpretation():
    det=_base(); det['official_policy_meta']=_official(True)
    a=score(det,{'scores':{}},_ovs())['regimes']['FX positioning squeeze']
    human=_base(); human['official_policy_meta']=_official(False)
    human['approved_verification_evidence']=[{
        'bucket':'Bilateral FX policy','effect_target':'fx_positioning_squeeze','effect_direction':1,'effect_weight':8,
        'action_class':'BILATERAL_FX_POLICY','claim':'supported yen adjustment'
    }]
    b=score(human,{'scores':{}},_ovs())['regimes']['FX positioning squeeze']
    assert b > a - 0.1  # full human effect is at least as large as the bounded deterministic effect


def test_spot_consistent_with_covering_does_not_confirm_cftc_unwind():
    s=_base(); s['official_policy_meta']=_official(False)
    today=datetime.now(timezone.utc).date().isoformat()
    s['cftc_summary']=[
        {'market':'Japanese Yen','report_date':today,'leveraged_net':-100000,'leveraged_weekly_change':-25000,'leveraged_3y_percentile':15},
        {'market':'Euro FX','report_date':today,'leveraged_net':-40000,'leveraged_weekly_change':-5000,'leveraged_3y_percentile':15},
        {'market':'Dollar Index','report_date':today,'leveraged_net':20000,'leveraged_weekly_change':1000,'leveraged_3y_percentile':80},
    ]
    out=score(s,{'scores':{}},_ovs())
    assert out['observed_position_unwind']['status']=='UNCONFIRMED'
    txt=' '.join(out['drivers']['fx_positioning_squeeze']).lower()
    assert 'consistent with short-covering' in txt
    assert 'are unwinding' not in txt


def test_newer_cftc_shrinking_multiple_crowded_shorts_confirms_unwind():
    s=_base(); s['official_policy_meta']=_official(False)
    today=datetime.now(timezone.utc).date().isoformat()
    s['cftc_summary']=[
        {'market':'Japanese Yen','report_date':today,'leveraged_net':-80000,'leveraged_weekly_change':20000,'leveraged_3y_percentile':18},
        {'market':'Euro FX','report_date':today,'leveraged_net':-30000,'leveraged_weekly_change':12000,'leveraged_3y_percentile':20},
        {'market':'Dollar Index','report_date':today,'leveraged_net':18000,'leveraged_weekly_change':-3000,'leveraged_3y_percentile':78},
    ]
    out=score(s,{'scores':{}},_ovs())
    assert out['observed_position_unwind']['status']=='CONFIRMED'
    assert len(out['observed_position_unwind']['foreign_short_covering_signals'])==2
    assert any('confirms shrinkage' in x.lower() for x in out['drivers']['fx_positioning_squeeze'])


if __name__=='__main__':
    test_deterministic_anchor_validator_requires_all_groups()
    test_canonical_deterministic_fact_skips_llm_queue_status()
    test_deterministic_facts_raise_coverage_but_keep_broad_intent_gate()
    test_deterministic_score_effect_is_smaller_than_human_approved_interpretation()
    test_spot_consistent_with_covering_does_not_confirm_cftc_unwind()
    test_newer_cftc_shrinking_multiple_crowded_shorts_confirms_unwind()
    print('v3.3.1 tests passed')
