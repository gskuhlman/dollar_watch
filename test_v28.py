import os, tempfile
from pathlib import Path
import pandas as pd

from dollar_dashboard.buybacks import _normalize_result_xml, summarize_buybacks
from dollar_dashboard.verification import source_relevance
from dollar_dashboard.data import summarize_offshore_fx_forward_proxy


def test_nested_buyback_max_amount():
    xml=b'''<buyback><operationDate>2026-09-03</operationDate><operationStatus>Results</operationStatus>
    <maturityBucket>Nominal Coupons 10Y to 20Y</maturityBucket>
    <maxParAmountToBeRedeemed><value>$4,000,000,000</value></maxParAmountToBeRedeemed>
    <totalParAmountOffered><value>$12,000,000,000</value></totalParAmountOffered>
    <totalParAmountAccepted><value>$4,000,000,000</value></totalParAmountAccepted></buyback>'''
    r=_normalize_result_xml(xml,'https://example.test/BBR.xml')
    assert float(r['max_amount'])==4_000_000_000
    assert float(r['total_offered'])==12_000_000_000
    assert float(r['total_accepted'])==4_000_000_000


def test_buyback_unknown_if_capacity_missing():
    df=pd.DataFrame([{'operation_date':'2026-09-03','maturity_bucket':'10Y to 20Y','has_result':True,'total_offered':10e9,'total_accepted':2e9,'max_amount':None}])
    m=summarize_buybacks(df,{'result_completeness_pct':100})
    assert m['intensity_status']=='UNKNOWN' and m['intensity'] is None


def test_stablecoin_sanctions_source_rejected():
    claim='Stablecoin regulation is about the dollar, not consumer protection'
    text='Treasury imposed sanctions on Iran and Türkiye banking channels and restricted access to dollars.'
    r=source_relevance('Stablecoins',claim,text,url='https://home.treasury.gov/news/press-releases/example')
    assert r['relevance_status']=='IRRELEVANT_SOURCE'


def test_offshore_proxy_is_labeled_proxy_not_basis():
    idx=pd.date_range('2026-01-01',periods=120,freq='B')
    eur=pd.Series(1.10,index=idx); usdjpy=pd.Series(150.0,index=idx); usdchf=pd.Series(0.82,index=idx)
    # small smooth carry gaps plus a modest final dislocation
    eurf=eur*1.002; jpyf=(1/usdjpy)*1.001; chff=(1/usdchf)*1.0015
    eurf.iloc[-1]*=1.004
    close=pd.DataFrame({'EURUSD':eur,'USDJPY':usdjpy,'USDCHF':usdchf,'EUR Front Future':eurf,'JPY Front Future':jpyf,'CHF Front Future':chff})
    m=summarize_offshore_fx_forward_proxy(close)
    assert m['available'] and len(m['pairs'])==3
    assert m['coverage']==55.0
    assert m['actual_cross_currency_basis_available'] is False
    assert 'cross-currency basis' in m['reason'].lower() and 'unavailable' in m['reason'].lower()


def test_legacy_mismatch_quarantined():
    tmp=Path(tempfile.mkdtemp())/'t.sqlite'
    os.environ['DOLLAR_DASHBOARD_DB']=str(tmp)
    import dollar_dashboard.storage as st
    con=st.connect()
    # Seed a queue row that current relevance rules reject.
    con.execute("INSERT INTO verification_queue(claim_key,created_at,updated_at,priority,bucket,claim,status,candidate_url,relevance_status,llm_verdict) VALUES(?,?,?,?,?,?,?,?,?,?)",
                ('k','2026-01-01','2026-01-01','P1','Stablecoins','Stablecoin regulation is about the dollar','IRRELEVANT_SOURCE','https://home.treasury.gov/sanctions','IRRELEVANT_SOURCE','INCONCLUSIVE'))
    con.execute("INSERT INTO verification_checks(created_at,claim,bucket,source_url,source_tier,verdict,explanation,model,provenance) VALUES(?,?,?,?,?,?,?,?,?)",
                ('2026-01-01','Stablecoin regulation is about the dollar','Stablecoins','https://home.treasury.gov/sanctions','PRIMARY','INCONCLUSIVE','mismatch','x','LLM-ASSISTED'))
    con.commit(); con.close()
    assert st.recent_verification_checks(20)==[]
    q=st.recent_quarantined_verification_checks(20)
    assert len(q)==1 and q[0]['quarantine_status']=='QUARANTINED'


if __name__=='__main__':
    test_nested_buyback_max_amount(); test_buyback_unknown_if_capacity_missing(); test_stablecoin_sanctions_source_rejected(); test_offshore_proxy_is_labeled_proxy_not_basis(); test_legacy_mismatch_quarantined()
    print('v2.8 tests passed')
