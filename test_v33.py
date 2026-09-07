from unittest.mock import patch, Mock
from dollar_dashboard.official_policy import (
    _parse_english_yen_intervention_amount, fetch_japan_mof_intervention,
    MOF_FX_20260828_EN,
)
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES
from dollar_dashboard.buybacks import summarize_buybacks
import pandas as pd


def test_english_mof_amount_parser():
    assert _parse_english_yen_intervention_amount('Total amount of foreign exchange intervention operations ¥ 15,399.3 billion') == 15_399_300_000_000


def test_live_english_mof_is_primary_and_direction_unknown():
    r=Mock(); r.status_code=200; r.url=MOF_FX_20260828_EN; r.content=b'<html><body>Total amount of foreign exchange intervention operations \xc2\xa5 15,399.3 billion</body></html>'
    r.encoding='utf-8'; r.apparent_encoding='utf-8'; r.headers={'content-type':'text/html'}
    with patch('dollar_dashboard.official_policy._get', return_value=r):
        out=fetch_japan_mof_intervention(timeout=1)
    assert out['ok'] and out['amount_trillion_yen']==15.3993
    assert out['direction']=='UNKNOWN' and out['fetch_mode']=='LIVE_ENGLISH_PRIMARY'


def test_unparseable_live_page_falls_back_to_validated_seed():
    r=Mock(); r.status_code=200; r.url=MOF_FX_20260828_EN; r.content=b'<html><body>page shell only</body></html>'
    r.encoding='utf-8'; r.apparent_encoding='utf-8'; r.headers={'content-type':'text/html'}
    with patch('dollar_dashboard.official_policy._get', return_value=r):
        out=fetch_japan_mof_intervention(timeout=1)
    assert out['ok'] and out['amount_trillion_yen']==15.3993
    assert out['fetch_mode']=='LAST_KNOWN_VALIDATED_CACHE'


def _snap(jpy3m):
    return {
      'market_summary': {'USDJPY':{'3m':jpy3m},'EURUSD':{'3m':0},'USDCHF':{'3m':0},'DXY':{'last':99,'1m':0,'3m':0}},
      'fred_summary':{}, 'confidence_adjustments':{'market':1,'fred':1,'auction':1,'cftc':1,'tic':1,'tic_transactions':1,'cofer':1,'fiscal':1,'stablecoin':1,'news':1},
      'official_policy_meta':{'japan_fx_intervention':{'ok':True,'intervention_occurred':True,'direction':'UNKNOWN','period_end':'2026-08-26'},'us_fx_intervention':{}},
      'fx_positioning_squeeze_score':50,'fx_positioning_squeeze_reasons':[], 'analyst_overrides':{},
      'approved_policy_evidence':[], 'verification_checks':[], 'auction_stress':0, 'buyback_meta':{}, 'stablecoin_meta':{},
    }


def test_spot_confirmation_is_smooth_not_cliff():
    ov={k:{'value':v,'note':''} for k,v in DEFAULT_OVERRIDES.items()}
    news={'scores':{}}
    a=score(_snap(-0.029),news,ov)['regimes']['FX positioning squeeze']
    b=score(_snap(-0.031),news,ov)['regimes']['FX positioning squeeze']
    assert 0 <= b-a < 2.0


def test_buyback_forward_policy_event_present():
    now=pd.Timestamp.now(tz='UTC')
    df=pd.DataFrame([{'operation_date':now-pd.Timedelta(days=1),'has_result':True,'maturity_bucket':'Nominal 10Y to 20Y','security_type':'Nominal','max_amount':2e9,'total_offered':5e9,'total_accepted':2e9}])
    out=summarize_buybacks(df,{'result_completeness_pct':100})
    ev=out['forward_policy_event']
    assert ev['effective_start']=='2026-09-09' and ev['long_end_nominal_max_per_operation']==4_000_000_000

if __name__=='__main__':
    test_english_mof_amount_parser(); test_live_english_mof_is_primary_and_direction_unknown(); test_unparseable_live_page_falls_back_to_validated_seed(); test_spot_confirmation_is_smooth_not_cliff(); test_buyback_forward_policy_event_present(); print('v3.3 tests passed')
