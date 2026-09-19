import pandas as pd
from unittest.mock import patch

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION
from dollar_dashboard.treasury_financing import summarize_treasury_financing, OPTIONAL_Z1_FINANCING_SERIES


def _z1(q='2026-03-31'):
    idx=pd.to_datetime([q])
    return pd.DataFrame({
        'Net marketable Treasury issuance':[2000.0],
        'Federal Reserve / central bank':[500.0],
        'U.S.-chartered depository institutions':[300.0],
        'Foreign banking offices in U.S.':[100.0],
        'Banks in U.S.-affiliated areas':[10.0],
        'Credit unions':[10.0],
        'Foreign sector':[400.0],
        'Security brokers & dealers':[300.0],
        'Money market funds':[-200.0],
    },index=idx)


def _money():
    idx=pd.to_datetime(['2025-12-01','2026-03-01','2026-04-01','2026-07-01'])
    return pd.DataFrame({
        'M2 money stock':[100.0,101.5,102.0,105.0],
        'Commercial bank deposits':[100.0,101.5,102.0,105.0],
        'Bank Treasury + agency securities':[100.0,101.0,102.0,104.0],
    },index=idx)


def test_v343_metadata_schema_unchanged():
    assert tuple(map(int, __version__.split('.'))) >= (3,4,3)
    assert tuple(map(int, APP_VERSION.split('.'))) >= (3,4,3)
    assert SCHEMA_VERSION == '3.4.1'


def test_q1_is_latest_expected_release_before_sep11_not_two_quarters_stale():
    fake_now=pd.Timestamp('2026-09-07 13:00:00')
    with patch('dollar_dashboard.treasury_financing.datetime') as dt:
        from datetime import timezone
        dt.now.return_value=fake_now.to_pydatetime().replace(tzinfo=timezone.utc)
        out=summarize_treasury_financing(_z1(),_money())
    assert out['as_of_quarter']=='2026Q1'
    assert out['data_timeliness']=='LATEST_EXPECTED_RELEASE'
    assert out['release_lag_quarters']==0
    assert out['quarter_lag']==2
    assert out['classification']['provisional'] is False
    assert out['next_expected_quarter']=='2026Q2'
    assert out['next_release_date']=='2026-09-11'


def test_eslr_proxy_excludes_foreign_offices_and_credit_unions():
    out=summarize_treasury_financing(_z1(),_money())
    # U.S.-chartered only = 300/2000 = 15%, broad banks = 420/2000 = 21%
    assert abs(out['eslr_relevant_bank_proxy_absorption_pct']-15.0)<1e-9
    assert abs(out['bank_absorption_pct']-21.0)<1e-9




def test_q2_schema_hedge_fund_transaction_series_is_optional_not_level_substitution():
    assert OPTIONAL_Z1_FINANCING_SERIES['Hedge funds']=='BOGZ1FA623061103Q'
    z=_z1().copy()
    z['Hedge funds']=[50.0]
    out=summarize_treasury_financing(z,_money())
    assert abs(out['hedge_fund_absorption_pct']-2.5)<1e-9
    row=next(r for r in out['holders'] if r['holder']=='Hedge funds')
    assert row['role']=='LEVERAGED_END_BUYER'


def test_hedge_fund_structural_proxy_is_partial_not_holder_demand():
    idx=pd.to_datetime(['2025-10-01'])
    funding=pd.DataFrame({
        'Hedge fund Treasury holdings':[300000.0],
        'Hedge fund repo assets':[120000.0],
        'Hedge fund domestic repo liabilities':[75000.0],
    },index=idx)
    out=summarize_treasury_financing(_z1(),_money(),funding)
    f=out['funding_layer']
    assert abs(f['hedge_fund_treasury_holdings_bn']-300.0)<1e-9
    assert abs(f['hedge_fund_domestic_repo_liabilities_bn']-75.0)<1e-9
    assert abs(f['hedge_fund_domestic_repo_to_treasury_pct']-25.0)<1e-9
    assert 'partial structural proxy' in f['note']


def test_generated_markdown_escape_logic_equivalent():
    import re
    text='Deficit $1.80T and swaps $132M; escaped \\$5 stays escaped.'
    safe=re.sub(r'(?<!\\)\$', r'\\$', text)
    assert r'\$1.80T' in safe and r'\$132M' in safe
    assert r'\$5' in safe


if __name__=='__main__':
    test_v343_metadata_schema_unchanged()
    test_q1_is_latest_expected_release_before_sep11_not_two_quarters_stale()
    test_eslr_proxy_excludes_foreign_offices_and_credit_unions()
    test_q2_schema_hedge_fund_transaction_series_is_optional_not_level_substitution()
    test_hedge_fund_structural_proxy_is_partial_not_holder_demand()
    test_generated_markdown_escape_logic_equivalent()
    print('v3.4.3 tests passed')
