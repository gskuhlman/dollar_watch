from unittest.mock import patch

from dollar_dashboard.official_policy import (
    _parse_yen_intervention_amount, _parse_jp_period, cached_official_source_text,
    intervention_history_seed, parse_nyfed_basis_validation_text,
    TREASURY_BESSENT_UEDA, MOF_FX_20260828, fetch_japan_mof_intervention, fetch_nyfed_basis_validation,
)
from dollar_dashboard.evidence import fetch_source_text


def test_mof_japanese_units_normalize_fullwidth_and_spacing():
    assert _parse_yen_intervention_amount('外国為替平衡操作額 １５兆３，９９３億円') == 15_399_300_000_000
    assert _parse_yen_intervention_amount('外国為替平衡操作額\n15 兆 3,993 億 円') == 15_399_300_000_000
    assert _parse_yen_intervention_amount('外国為替平衡操作額 3,993億円') == 399_300_000_000


def test_mof_period_parse_reiwa_and_unicode_wave_dash():
    a,b=_parse_jp_period('令和8年7月30日〜令和8年8月26日')
    assert a=='2026-07-30' and b=='2026-08-26'


def test_packaged_mof_seed_is_parseable():
    row=cached_official_source_text(MOF_FX_20260828)
    assert row['ok'] and row.get('packaged_seed')
    assert _parse_yen_intervention_amount(row['text']) == 15_399_300_000_000


def test_canonical_treasury_fetch_can_fall_back_to_dated_official_cache():
    with patch('dollar_dashboard.evidence.requests.get', side_effect=RuntimeError('temporary 503')):
        row=fetch_source_text(TREASURY_BESSENT_UEDA)
    assert row['ok'] is True and row.get('cache_fallback') is True
    text=row['text'].lower()
    assert 'yen' in text and ('undervaluation' in text or 'exchange-rate volatility' in text)


def test_intervention_history_preserves_actor_currency_and_purpose():
    hist=intervention_history_seed()
    q4=next(x for x in hist if x['period']=='2025-Q4')
    q1=next(x for x in hist if x['period']=='2026-Q1')
    q2=next(x for x in hist if x['period']=='2026-Q2')
    assert q4['treasury_intervened'] is True and q4['fed_intervened'] is False
    assert q4['currency']=='ARS' and q4['broad_usd_implication']=='LOW'
    assert 'Argentina' in q4['purpose']
    assert q1['treasury_intervened'] is False and q2['treasury_intervened'] is False



def test_offline_canonical_fallback_still_produces_structured_mof_and_lagged_basis():
    with patch('dollar_dashboard.official_policy._get', side_effect=RuntimeError('offline')):
        jp=fetch_japan_mof_intervention(timeout=1)
        basis=fetch_nyfed_basis_validation(timeout=1)
    assert jp['ok'] and jp['amount_trillion_yen']==15.3993 and jp['fetch_mode']=='LAST_KNOWN_CACHE'
    assert basis['ok'] and basis['status']=='STABLE' and basis['basis_characterization']=='HISTORICALLY_TIGHT'
    assert basis['lagged_validation_only'] is True

def test_nyfed_lagged_basis_parser_is_context_not_live_trigger():
    text=('OFFSHORE U.S. DOLLAR FUNDING CONDITIONS REMAIN STABLE. '
          'Global offshore dollar funding conditions were stable. '
          'Three-month basis spreads in euro-dollar and dollar-yen traded at historically tight levels. '
          'Aggregate swaps outstanding increased to $250 million at quarter end.')
    out=parse_nyfed_basis_validation_text(text)
    assert out['status']=='STABLE'
    assert out['basis_characterization']=='HISTORICALLY_TIGHT'
    assert out['central_bank_swaps_million']==250


if __name__=='__main__':
    test_mof_japanese_units_normalize_fullwidth_and_spacing()
    test_mof_period_parse_reiwa_and_unicode_wave_dash()
    test_packaged_mof_seed_is_parseable()
    test_canonical_treasury_fetch_can_fall_back_to_dated_official_cache()
    test_intervention_history_preserves_actor_currency_and_purpose()
    test_offline_canonical_fallback_still_produces_structured_mof_and_lagged_basis()
    test_nyfed_lagged_basis_parser_is_context_not_live_trigger()
    print('v3.2 tests passed')
