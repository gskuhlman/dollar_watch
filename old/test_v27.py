from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pandas as pd

from dollar_dashboard import buybacks, data, verification, storage


def test_buyback_result_max_amount_survives_merge_and_intensity_known():
    sched=pd.DataFrame([{
        'operation_date':pd.Timestamp('2026-09-03',tz='UTC'),
        'operation_start':pd.Timestamp('2026-09-03T17:40:00Z'),
        'maturity_bucket':'10-year to 20-year',
        'operation_type':'Liquidity Support',
        'max_amount':None,
        'source_kind':'SCHEDULE',
    }])
    results=pd.DataFrame([{
        'operation_date':pd.Timestamp('2026-09-03',tz='UTC'),
        'operation_start':pd.Timestamp('2026-09-03T17:40:00Z'),
        'maturity_bucket':'10-year to 20-year',
        'operation_type':'Liquidity Support',
        'max_amount':4_000_000_000,
        'total_offered':20_000_000_000,
        'total_accepted':4_000_000_000,
        'offer_accept_ratio':5.0,
        'result_url':'https://example.test/BBR.xml',
        'source_kind':'RESULT',
    }])
    old_s,old_r=buybacks.fetch_tentative_schedule,buybacks.fetch_buyback_results
    try:
        buybacks.fetch_tentative_schedule=lambda timeout=25:(sched.copy(),{'schedule_operations':1,'result_completeness_pct':100})
        buybacks.fetch_buyback_results=lambda schedule,timeout=15,lookback_days=180,max_operations=50:(results.copy(),{'result_completeness_pct':100,'result_operations':1,'result_urls_attempted':1})
        merged,meta=buybacks.fetch_buyback_schedule()
        assert float(merged.loc[0,'max_amount'])==4_000_000_000
        sm=buybacks.summarize_buybacks(merged,meta)
        assert sm['max_amount_parse_status']=='OK'
        assert sm['intensity_status']=='KNOWN'
        assert sm['total_max_amount']==4_000_000_000
    finally:
        buybacks.fetch_tentative_schedule,buybacks.fetch_buyback_results=old_s,old_r


def test_buyback_unknown_capacity_is_not_zero_intensity():
    df=pd.DataFrame([{
        'operation_date':pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=1),
        'maturity_bucket':'10-year to 20-year','max_amount':None,
        'total_offered':10_000_000_000,'total_accepted':2_000_000_000,
        'has_result':True,
    }])
    sm=buybacks.summarize_buybacks(df,{'result_completeness_pct':100})
    assert sm['intensity'] is None
    assert sm['intensity_status']=='UNKNOWN'
    assert sm['max_amount_parse_status']=='UNKNOWN_OR_PARSE_FAILED'


def test_semantic_relevance_rejects_unrelated_official_source():
    claim='Stablecoin regulation is about preserving dollar demand through payment stablecoins'
    bad='Treasury designated a foreign bank under Iran sanctions and discussed access to the U.S. financial system.'
    good='Treasury discusses payment stablecoins, dollar-denominated stablecoin reserves, and the GENIUS Act.'
    rb=verification.source_relevance('Stablecoins',claim,bad,url='https://home.treasury.gov/news/press-releases/sanctions')
    rg=verification.source_relevance('Stablecoins',claim,good,url='https://home.treasury.gov/stablecoins')
    assert rb['relevance_status']=='IRRELEVANT_SOURCE'
    assert rg['relevance_status']=='RELEVANT'
    assert rg['relevance_score'] > rb['relevance_score']


def test_reopening_term_canonicalization():
    raw=pd.DataFrame([
        {'security_type':'Note','security_term':'9-Year 11-Month','original_security_term':None,'auction_date':'2026-09-09'},
        {'security_type':'Bond','security_term':'29-Year 11-Month','original_security_term':None,'auction_date':'2026-09-10'},
        {'security_type':'TIPS','security_term':'9-Year 10-Month','original_security_term':None,'auction_date':'2026-09-17'},
    ])
    out=data._normalize_auction_frame(raw)
    assert out.iloc[0]['term_key']=='10-Year'
    assert out.iloc[1]['term_key']=='30-Year'
    assert out.iloc[2]['term_key']=='10-Year TIPS'


def test_generic_fred_distribution_context():
    idx=pd.date_range('2025-01-01',periods=80,freq='7D')
    series=pd.Series(range(80),index=idx,dtype=float)
    old_series,old_map=data.fetch_fred_series,data.FRED_SERIES
    try:
        data.FRED_SERIES={'Test indicator':'TEST'}
        data.fetch_fred_series=lambda sid,start=None:series
        hist,summary=data.fetch_fred_bundle(start='2025-01-01')
        row=summary.loc['Test indicator']
        assert pd.notna(row['percentile_1y'])
        assert pd.notna(row['zscore_1y'])
        assert int(row['history_obs_1y']) >= 12
    finally:
        data.fetch_fred_series,data.FRED_SERIES=old_series,old_map


def test_verification_queue_persists_relevance_and_approval():
    with tempfile.TemporaryDirectory() as td:
        old=os.environ.get('DOLLAR_DASHBOARD_DB')
        os.environ['DOLLAR_DASHBOARD_DB']=str(Path(td)/'test.sqlite')
        try:
            storage.upsert_verification_queue([{'priority':'P0','bucket':'Stablecoins','claim':'Stablecoin policy supports dollar demand through regulated reserves','source':'test','link':'https://example.test','preferred_verification_source':'Treasury'}])
            row=storage.recent_verification_queue(1)[0]
            storage.update_verification_queue_check(row['id'],candidate_url='https://home.treasury.gov/x',candidate_tier='TIER1_PRIMARY',candidate_relevance=72.0,relevance_status='RELEVANT',verdict='SUPPORTED',explanation='supported',status='CHECKED')
            storage.update_verification_queue_approval(row['id'],'APPROVED')
            row2=storage.recent_verification_queue(1)[0]
            assert row2['candidate_relevance']==72.0
            assert row2['relevance_status']=='RELEVANT'
            assert row2['approved_status']=='APPROVED'
        finally:
            if old is None: os.environ.pop('DOLLAR_DASHBOARD_DB',None)
            else: os.environ['DOLLAR_DASHBOARD_DB']=old


if __name__=='__main__':
    test_buyback_result_max_amount_survives_merge_and_intensity_known()
    test_buyback_unknown_capacity_is_not_zero_intensity()
    test_semantic_relevance_rejects_unrelated_official_source()
    test_reopening_term_canonicalization()
    test_generic_fred_distribution_context()
    test_verification_queue_persists_relevance_and_approval()
    print('v2.7 tests passed')
