from __future__ import annotations
import os, tempfile
from pathlib import Path
import pandas as pd

from dollar_dashboard.intelligence import summarize_tic_transactions
from dollar_dashboard.buybacks import summarize_buybacks
from dollar_dashboard.triggers import evaluate_triggers
from dollar_dashboard.portfolio import recommend, ASSETS
from dollar_dashboard.storage import upsert_verification_queue, recent_verification_queue


def test_tic_transaction_decomposition_not_holdings_as_demand():
    idx=pd.to_datetime(['2026-05-01','2026-06-01'])
    h=pd.DataFrame(index=idx)
    h['Foreign Treasury holdings grand total (millions)']=[9000,9050]
    h['Foreign Treasury net transactions grand total (millions)']=[10,20]
    h['Foreign LT Treasury valuation change grand total (millions)']=[5,7]
    h['Foreign official Treasury holdings (millions)']=[4000,3970]
    h['Foreign Treasury net transactions official (millions)']=[-5,-20]
    h['Foreign LT Treasury valuation change official (millions)']=[0,-4]
    h['Foreign Treasury net transactions private (millions)']=[15,40]
    out=summarize_tic_transactions(h)
    assert out['grand_total']['monthly_position_change_mn']==50
    assert out['grand_total']['net_transactions_mn']==20
    assert out['grand_total']['long_term_valuation_change_mn']==7
    assert out['grand_total']['non_transaction_residual_mn']==23
    assert out['foreign_official']['net_transactions_mn']==-20
    assert out['foreign_private']['net_transactions_mn']==40


def test_buyback_incomplete_blocks_execution_conclusions():
    df=pd.DataFrame([{
        'operation_date':pd.Timestamp('2026-08-01',tz='UTC'),'maturity_bucket':'10-20 year',
        'has_result':True,'total_offered':10_000_000_000,'total_accepted':2_000_000_000,'max_amount':2_000_000_000,
    }])
    meta={'result_completeness_pct':40.0,'expected_result_urls':10,'expected_results_found':4}
    out=summarize_buybacks(df,meta)
    assert out['result_classification']=='INCOMPLETE'
    assert out['results_conclusions_allowed'] is False


def _base_snapshot():
    return {
      'timestamp':'2026-09-06T17:00:00+00:00',
      'auction_summary':[
        {'term':'10-Year','auction_date':'2026-08-12','bid_to_cover':2.0,'prior8_btc':2.3,'dealer_share_pct':16,'indirect_share_pct':60},
        {'term':'30-Year','auction_date':'2026-08-20','bid_to_cover':2.0,'prior8_btc':2.3,'dealer_share_pct':16,'indirect_share_pct':60},
      ],
      'upcoming_auctions':[
        {'term_key':'10-Year','auction_date':'2026-09-09'},
        {'term_key':'30-Year','auction_date':'2026-09-10'},
      ],
      'fred_summary':{
        '10Y breakeven inflation':{'last':2.35},'10Y TIPS real yield':{'last':2.42},
        'SOFR-IORB spread':{'last':0.01},'SOFR99-IORB spread':{'last':0.09,'percentile_1y':59,'zscore_1y':0,'recent_obs_ge_10bp':0},
        'Central bank liquidity swaps (millions)':{'last':132},'FIMA repo - foreign official (millions)':{'last':0},
        'Foreign custody UST YoY change (millions)':{'last':-228000},'10Y term premium':{'last':0.875},
      },
      'market_summary':{'DXY':{'last':99.16,'3m':-0.01},'Gold':{'3m':0.03}},
      'cftc_usd_downside_pressure':33.8,
    }


def test_upcoming_auction_linkage_and_fima_separation():
    snap=_base_snapshot(); out=evaluate_triggers(snap,{'regimes':{}}); by={x['id']:x for x in out}
    assert '2026-09-09' in (by['weak_10y_30y_pair'].get('auction_lifecycle',{}).get('next_auction') or '')
    assert by['repo_or_swap_stress']['status']=='NOT_TRIGGERED'
    snap['fred_summary']['FIMA repo - foreign official (millions)']['last']=1200
    out=evaluate_triggers(snap,{'regimes':{}}); by={x['id']:x for x in out}
    assert by['repo_or_swap_stress']['status']=='TRIGGERED'
    assert by['repo_or_swap_stress']['central_bank_swaps_mn']==132
    assert by['repo_or_swap_stress']['fima_repo_mn']==1200


def test_real_yield_weak_auction_precommitment_avoids_tips_add():
    base={a:0 for a in ASSETS}; base.update({
        'T-bills / cash equivalents':25,'TIPS':20,'Gold':15,'Developed ex-US equities (unhedged)':17.5,
        'US real-asset / value equities':10,'Broad commodities / energy':0,'CHF / defensive FX':7.5,'Bitcoin':5})
    trig=[{'id':'weak_10y_30y_pair','status':'TRIGGERED','stress_flavor':'REAL_YIELD_FISCAL'}]
    regimes={k:35 for k in ['Managed dollar devaluation','Fiscal / Treasury supply stress','Inflation / monetary debasement','Dollar funding squeeze','Reserve-confidence crisis','FX positioning squeeze']}
    df,meta=recommend(regimes,base,100000,min_trade_pct=0.5,min_trade_dollars=100,confidence=100,machine_triggers=trig)
    d=df.set_index('Asset')
    assert d.loc['T-bills / cash equivalents','Recommended %'] > 25
    assert d.loc['Gold','Recommended %'] > 15
    assert d.loc['TIPS','Recommended %'] < 20


def test_verification_queue_persists_deduplicated():
    with tempfile.TemporaryDirectory() as td:
        old=os.environ.get('DOLLAR_DASHBOARD_DB'); os.environ['DOLLAR_DASHBOARD_DB']=str(Path(td)/'t.sqlite')
        try:
            row={'priority':'P0','bucket':'FX intervention','claim':'Treasury conducted a coordinated FX operation','source':'Example','link':'https://example.com/a','preferred_verification_source':'Treasury'}
            upsert_verification_queue([row]); upsert_verification_queue([row])
            q=recent_verification_queue(10)
            assert len(q)==1 and q[0]['claim']==row['claim']
        finally:
            if old is None: os.environ.pop('DOLLAR_DASHBOARD_DB',None)
            else: os.environ['DOLLAR_DASHBOARD_DB']=old

if __name__=='__main__':
    test_tic_transaction_decomposition_not_holdings_as_demand()
    test_buyback_incomplete_blocks_execution_conclusions()
    test_upcoming_auction_linkage_and_fima_separation()
    test_real_yield_weak_auction_precommitment_avoids_tips_add()
    test_verification_queue_persists_deduplicated()
    print('v2.6 tests passed')
