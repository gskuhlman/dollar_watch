import pandas as pd

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard.intelligence import summarize_cftc_fx, summarize_fx_positioning_squeeze
from dollar_dashboard import llm


def _jpy_history():
    # Last observation remains net short, but is much less short than most of its
    # history, so its net-position percentile is high and must NOT be called a
    # historically crowded short.
    nets = [-300, -260, -220, -180, -160, -140, -120, -110, -140, -90]
    rows=[]
    for i, net in enumerate(nets):
        oi=1000
        # long-short = net
        long=200
        short=long-net
        rows.append({
            'report_date': pd.Timestamp('2026-07-07') + pd.Timedelta(days=7*i),
            'commodity_name':'JAPANESE YEN',
            'contract_market_name':'JAPANESE YEN',
            'cftc_contract_market_code':'097741',
            'open_interest_all':oi,
            'lev_money_positions_long':long,
            'lev_money_positions_short':short,
            'asset_mgr_positions_long':200,
            'asset_mgr_positions_short':200,
        })
    return pd.DataFrame(rows)


def test_v3416_version_lineage_unchanged_scoring():
    assert __version__ == '3.4.25'
    assert APP_VERSION == '3.4.25'
    assert SCHEMA_VERSION == '3.4.1'
    assert SCORE_MODEL_VERSION == '3.4.3'


def test_negative_net_high_percentile_is_not_crowded_short():
    table, _ = summarize_cftc_fx(_jpy_history())
    row = table.loc[table['market'].eq('Japanese Yen')].iloc[0]
    assert row['leveraged_net'] < 0
    assert row['leveraged_3y_percentile'] > 50
    assert row['leveraged_crowding_state'] == 'SHORT_NOT_HISTORICALLY_CROWDED'
    assert row['leveraged_short_crowding_score'] < 50
    assert row['leveraged_percentile_semantics'] == 'LOW_PERCENTILE_MORE_SHORT; HIGH_PERCENTILE_MORE_LONG'


def test_fx_squeeze_reasons_do_not_call_high_percentile_short_crowded():
    table, _ = summarize_cftc_fx(_jpy_history())
    _, reasons = summarize_fx_positioning_squeeze(table)
    assert not any('Japanese Yen' in r and 'crowded short' in r for r in reasons)


def test_llm_contains_cftc_crowding_semantics_guardrail():
    src = open(llm.__file__, encoding='utf-8').read()
    assert 'CFTC CROWDING SEMANTICS' in src
    assert '72nd percentile' in src
    assert 'SHORT_NOT_HISTORICALLY_CROWDED' in src
