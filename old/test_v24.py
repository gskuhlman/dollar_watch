from __future__ import annotations
import json, os, tempfile
import pandas as pd

from dollar_dashboard.buybacks import _normalize_result_xml, _normalize_schedule_record, summarize_buybacks
from dollar_dashboard.fed_policy import classify_fed_treasury_change
from dollar_dashboard.triggers import evaluate_triggers
from dollar_dashboard.scoring import score, DEFAULT_OVERRIDES
from dollar_dashboard.portfolio import scenario_hedge_alignment
from dollar_dashboard.llm import _compact_analysis_payload
from dollar_dashboard.storage import recent_snapshots


def _ovs():
    return {k:{'value':0,'verification_status':'UNVERIFIED','source_url':'','source_tier':'UNSOURCED'} for k in DEFAULT_OVERRIDES}


def test_buyback_result_parser_and_summary():
    xml=b'''<buyback><operationStatus>Results</operationStatus><operationDate>2026-04-22</operationDate><operationStartDtm>2026-04-22T13:40:00-04:00</operationStartDtm><operationType>Liquidity Support</operationType><maturityBucket>1-3 Year</maturityBucket><maxParAmountToBeRedeemed>15000000000</maxParAmountToBeRedeemed><totalParAmountOffered>37841000000</totalParAmountOffered><totalParAmountAccepted>15000000000</totalParAmountAccepted><noIssueEligible>49</noIssueEligible><noIssuesAccepted>26</noIssuesAccepted></buyback>'''
    r=_normalize_result_xml(xml,'https://example/BBR.xml')
    assert r['total_offered']==37841000000
    assert r['total_accepted']==15000000000
    df=pd.DataFrame([{**r,'has_result':True,'max_amount':15000000000}])
    meta=summarize_buybacks(df,{})
    assert meta['completed_operations']==1
    assert meta['results_available'] is True
    assert abs(meta['completed_offer_accept_ratio']-2.523)<0.01


def test_schedule_record_normalization():
    rec={'operationStartDtm':'2026-09-09T13:40:00-04:00','maturityBucket':'20-30 Year','maxParAmountToBeRedeemed':'$4,000,000,000','operationType':'Liquidity Support'}
    out=_normalize_schedule_record(rec)
    assert str(out['operation_start']).startswith('2026-09-09 17:40:00')
    assert out['max_amount']==4000000000


def test_fed_treasury_composition_classification():
    fred={
      'Fed Treasury holdings (millions)':{'1y_change':347000},
      'Fed Treasury bills (millions)':{'1y_change':353000},
      'Fed Treasury nominal notes/bonds (millions)':{'1y_change':18000},
      'Fed Treasury TIPS principal (millions)':{'1y_change':-25000},
      'Fed MBS holdings (millions)':{'1y_change':-189000},
      'Fed balance sheet (millions)':{'1y_change':134000},
    }
    out=classify_fed_treasury_change(fred)
    assert out['classification']=='BILL_ACCUMULATION_WITH_MBS_RUNOFF'
    assert 'not by itself evidence of QE' in out['interpretation']


def test_auction_trigger_aging_and_pending_replacement():
    snap={
      'timestamp':'2026-09-06T16:00:00Z',
      'auction_summary':[
        {'term':'10-Year','auction_date':'2026-08-12','bid_to_cover':2.55,'prior8_btc':2.47,'dealer_share_pct':10,'indirect_share_pct':77},
        {'term':'30-Year','auction_date':'2026-08-13','bid_to_cover':2.82,'prior8_btc':2.46,'dealer_share_pct':8,'indirect_share_pct':84},
      ],
      'upcoming_auctions':[
        {'term_key':'10-Year','auction_date':'2026-09-09'},
        {'term_key':'30-Year','auction_date':'2026-09-10'},
      ],
      'fred_summary':{'10Y term premium':{'last':0.88},'10Y breakeven inflation':{'last':2.35},'Central bank liquidity swaps (millions)':{'last':132},'SOFR-IORB spread':{'last':0.01}},
      'market_summary':{'DXY':{'last':99.2,'3m':0.0},'Gold':{'3m':0.03}},'cftc_usd_downside_pressure':30,
    }
    by={x['id']:x for x in evaluate_triggers(snap,{})}
    assert by['clean_10y_30y_pair']['status'] in {'PENDING_REPLACEMENT','EXPIRED'}
    assert by['clean_10y_30y_pair']['status']!='TRIGGERED'


def test_managed_devaluation_critical_coverage_penalty():
    snap={'market_summary':{},'fred_summary':{},'component_confidence':{'market':100,'fred':100,'auction':90,'cftc':90,'tic':35,'cofer':35,'fiscal':65,'stablecoin':100,'news':100,'buyback':90},'data_confidence':85,'auction_stress_auto':0,'cftc_usd_downside_pressure':0,'fx_positioning_squeeze_risk':0,'tic_dedollarization_pressure':0,'cofer_dedollarization_pressure':0,'fiscal_flow_stress_auto':0,'stablecoin_dollar_support_auto':20,'treasury_buyback_meta':{'intensity':20}}
    out=score(snap,{'scores':{}},_ovs())
    d=out['regime_evidence_coverage_details']['Managed dollar devaluation']
    assert d['critical']==0
    assert d['effective'] < d['generic']
    assert d['effective'] <= 50


def test_scenario_alignment_not_single_defensive_percent():
    alloc={'T-bills / cash equivalents':25,'TIPS':20,'Gold':15,'Developed ex-US equities (unhedged)':17.5,'US real-asset / value equities':10,'Broad commodities / energy':0,'CHF / defensive FX':7.5,'Bitcoin':5}
    out=scenario_hedge_alignment(alloc)
    assert len(out)==6
    assert 'Dollar funding squeeze' in set(out['Scenario'])
    assert 'Hedge alignment' in out.columns


def test_llm_payload_compaction_never_breaks_json():
    payload={'scores':{'regimes':{'x':1}},'verification_queue_discovery_only':[{'claim':'c'+str(i),'link':'https://x','blob':'z'*5000} for i in range(30)],'headlines_discovery_only':[{'t':'x'*5000} for _ in range(30)],'snapshot':{'timestamp':'x','market_summary':{},'fred_summary':{}}}
    raw=_compact_analysis_payload(payload,max_chars=12000)
    obj=json.loads(raw)
    assert isinstance(obj,dict)
    assert len(raw) < 20000


def test_legacy_snapshot_labeling():
    with tempfile.TemporaryDirectory() as d:
        os.environ['DOLLAR_DASHBOARD_DB']=os.path.join(d,'x.sqlite')
        import sqlite3
        con=sqlite3.connect(os.environ['DOLLAR_DASHBOARD_DB'])
        con.execute('CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT,captured_at TEXT NOT NULL,payload TEXT NOT NULL,run_id TEXT,parent_run_id TEXT,app_version TEXT,schema_version TEXT,run_kind TEXT)')
        con.execute('INSERT INTO snapshots(captured_at,payload) VALUES (?,?)',('2026-01-01',json.dumps({'timestamp':'2026-01-01'})))
        con.commit(); con.close()
        row=recent_snapshots(1)[0]
        assert row['_legacy_lineage'] is True
        assert row['_run_kind']=='LEGACY_BASELINE'
        assert row['_run_id'].startswith('legacy-')


if __name__=='__main__':
    test_buyback_result_parser_and_summary(); test_schedule_record_normalization(); test_fed_treasury_composition_classification(); test_auction_trigger_aging_and_pending_replacement(); test_managed_devaluation_critical_coverage_penalty(); test_scenario_alignment_not_single_defensive_percent(); test_llm_payload_compaction_never_breaks_json(); test_legacy_snapshot_labeling(); print('v2.4 tests passed')
