"""The *current* JPY CFTC position must govern intervention narratives."""
from datetime import datetime, timezone

from dollar_dashboard import __version__
from dollar_dashboard import llm
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard.scoring import score
from test_v3424 import snapshot


def _cftc_payload(state='CROWDED_LONG'):
    if state == 'CROWDED_LONG':
        net, pct = 23170, 91.4
    elif state == 'CROWDED_SHORT':
        net, pct = -49098, 9.8
    else:
        net, pct = 150, 53.0
    row={
        'market': 'Japanese Yen', 'report_date': '2026-09-15',
        'leveraged_net': net, 'leveraged_3y_percentile': pct,
        'leveraged_weekly_change': 72268,
        'leveraged_crowding_state': state,
    }
    snap=snapshot('2026-09-19T12:57:00Z')
    snap['cftc_summary']=[row]
    res=score(snap, {'scores': {}}, {}, as_of=datetime(2026, 9, 19, tzinfo=timezone.utc))
    return {'snapshot':snap, 'scores':res}


def test_version_only_narrative_no_formula_or_schema_bump():
    assert __version__ == APP_VERSION == '3.4.25'
    assert SCHEMA_VERSION == '3.4.1'
    assert SCORE_MODEL_VERSION == '3.4.3'


def test_current_crowded_long_context_follows_cftc_position():
    context=_cftc_payload()['scores']['fx_intervention_positioning_context']
    assert context['observed_crowding_state'] == 'CROWDED_LONG'
    assert context['position_asof_date'] == '2026-09-15'
    assert 'crowded JPY longs' in context['JPY_SELL_FX_BUY']
    assert 'crowded longs' in context['JPY_BUY_FX_SELL']
    assert 'not an observed liquidation' in context['JPY_SELL_FX_BUY']


def test_previous_short_state_retains_valid_short_covering_mechanics():
    context=_cftc_payload('CROWDED_SHORT')['scores']['fx_intervention_positioning_context']
    assert context['observed_crowding_state'] == 'CROWDED_SHORT'
    assert 'currently crowded JPY shorts' in context['JPY_BUY_FX_SELL']


def test_incorrect_current_long_reversal_trigger_is_flagged():
    payload=_cftc_payload()
    text='Human reversals: MOF detail confirming yen-buying (would intensify JPY-short-squeeze dynamics; yen-selling works against them).'
    bad=llm.red_team_narrative_violations(text, payload)
    assert any('CROWDED_LONG' in problem for problem in bad)


def test_two_branch_short_squeeze_only_narrative_is_flagged():
    payload=_cftc_payload()
    text='If MOF shows yen-selling, it works against a JPY-short squeeze; yen-buying would do the opposite.'
    bad=llm.red_team_narrative_violations(text, payload)
    assert any('crowded yen longs' in problem for problem in bad)


def test_correct_long_side_scenario_is_allowed():
    payload=_cftc_payload()
    text='Direction UNKNOWN: verified yen-selling would pressure crowded JPY longs and could prompt long liquidation; yen-buying would support the crowded longs.'
    assert llm.red_team_narrative_violations(text, payload) == []


def test_counterfactual_short_rebuild_is_allowed():
    payload=_cftc_payload()
    text='If shorts rebuild to a crowded JPY short position in a later CFTC report, yen-buying may intensify a JPY-short squeeze; currently CFTC shows crowded longs.'
    assert llm.red_team_narrative_violations(text, payload) == []


def test_short_position_does_not_trigger_long_side_lint():
    payload=_cftc_payload('CROWDED_SHORT')
    text='Yen-buying can intensify a JPY-short squeeze when the observed shorts are crowded.'
    assert llm.red_team_narrative_violations(text, payload) == []


def test_prompt_has_state_guardrail_in_all_sections():
    literals='\n'.join(str(x) for x in llm.analyze_with_local_llm.__code__.co_consts if isinstance(x,str))
    assert 'CURRENT JPY POSITIONING RULE' in literals
    assert 'Reversal Triggers and Portfolio Actions' in literals
