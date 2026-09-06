import os
import tempfile
from pathlib import Path

import pandas as pd

from dollar_dashboard.buybacks import _normalize_result_xml, summarize_buybacks
from dollar_dashboard.verification import systematic_policy_leads, verification_rows_from_news


def test_result_xml_infers_long_end_sector_from_maturity_dates():
    xml=b'''<buyback>
      <operationDate>2026-08-11</operationDate><operationStatus>Results</operationStatus>
      <securityType>Nominal Coupons</securityType>
      <maxParAmountToBeRedeemed><value>$2,000,000,000</value></maxParAmountToBeRedeemed>
      <totalParAmountOffered><value>$6,000,000,000</value></totalParAmountOffered>
      <totalParAmountAccepted><value>$2,000,000,000</value></totalParAmountAccepted>
      <securities>
        <security><maturityDate>2037-08-15</maturityDate></security>
        <security><maturityDate>2045-05-15</maturityDate></security>
      </securities>
    </buyback>'''
    r=_normalize_result_xml(xml,'https://example.test/BBR_20260811.xml')
    assert r['maturity_bucket']=='Nominal Coupons 10Y to 20Y'
    assert r['maturity_bucket_source']=='INFERRED_FROM_MATURITY_DATES'


def test_known_2026_long_end_operations_are_not_zero():
    # Official May-2026 quarterly-refunding tentative schedule: recurring nominal
    # 10Y-20Y / 20Y-30Y operations through June-August 2026.
    dates=['2026-06-03','2026-06-09','2026-06-25','2026-07-01','2026-07-16','2026-07-23','2026-07-28','2026-08-11']
    buckets=['Nominal Coupons 20Y to 30Y','Nominal Coupons 10Y to 20Y','Nominal Coupons 20Y to 30Y','Nominal Coupons 10Y to 20Y',
             'Nominal Coupons 20Y to 30Y','Nominal Coupons 10Y to 20Y','Nominal Coupons 20Y to 30Y','Nominal Coupons 10Y to 20Y']
    df=pd.DataFrame([{
        'operation_date':d,'maturity_bucket':b,'security_type':'Nominal Coupons','has_result':True,
        'max_amount':2_000_000_000,'total_offered':5_000_000_000,'total_accepted':2_000_000_000,
    } for d,b in zip(dates,buckets)])
    m=summarize_buybacks(df,{'result_completeness_pct':100})
    assert m['long_end_nominal_completed_operations']==8
    assert m['long_end_completed_capacity']==16_000_000_000
    assert m['long_end_completed_total_accepted']==16_000_000_000
    assert m['intensity_status']=='KNOWN' and m['intensity']>0


def test_systematic_policy_leads_keep_queue_alive_without_news():
    rows=systematic_policy_leads(max_rows=10)
    assert len(rows)>=8
    assert any(r['priority']=='P0' and r['bucket']=='Treasury / Bessent' for r in rows)
    assert any(r['bucket']=='Administration / White House' for r in rows)
    assert all(r['integrity_status']=='COMPLETE' and r['link'].startswith('http') for r in rows)


def test_qualifying_policy_news_maps_to_primary_verification_family():
    news=pd.DataFrame([{
        'bucket':'US policy','title':'Treasury discusses dollar policy and possible FX intervention','source':'Reuters',
        'published':'Sun, 06 Sep 2026 12:00:00 GMT','link':'https://news.example/policy'
    },{
        'bucket':'BRICS','title':'BRICS members discuss non-dollar payment settlement infrastructure','source':'Reuters',
        'published':'Sun, 06 Sep 2026 11:00:00 GMT','link':'https://news.example/brics'
    }])
    rows=verification_rows_from_news(news,10)
    assert len(rows)==2
    assert rows[0]['priority'] in {'P0','P1'}
    fx=next(r for r in rows if 'intervention' in r['claim'].lower())
    assert fx['bucket']=='FX intervention' and fx['priority']=='P0' and fx['primary_source_candidates']
    brics=next(r for r in rows if r['discovery_bucket']=='BRICS')
    assert brics['bucket']=='BRICS / de-dollarization' and brics['priority']=='P1' and brics['primary_source_candidates']


def test_standing_probes_persist_into_empty_queue_database():
    tmp=Path(tempfile.mkdtemp())/'v29.sqlite'
    os.environ['DOLLAR_DASHBOARD_DB']=str(tmp)
    import dollar_dashboard.storage as st
    n=st.upsert_verification_queue(systematic_policy_leads(max_rows=5))
    rows=st.recent_verification_queue(20)
    assert n==5 and len(rows)==5
    assert all(r['status']=='QUEUED' for r in rows)


if __name__=='__main__':
    test_result_xml_infers_long_end_sector_from_maturity_dates()
    test_known_2026_long_end_operations_are_not_zero()
    test_systematic_policy_leads_keep_queue_alive_without_news()
    test_qualifying_policy_news_maps_to_primary_verification_family()
    test_standing_probes_persist_into_empty_queue_database()
    print('v2.9 tests passed')
