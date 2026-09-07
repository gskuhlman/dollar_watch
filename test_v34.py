import pandas as pd

from dollar_dashboard.treasury_financing import summarize_treasury_financing, classify_financing_regime, SLR_POLICY


def _q(vals):
    idx=pd.to_datetime(['2025-10-01','2026-01-01'])
    return pd.Series(vals,index=idx,dtype=float)


def test_q1_style_absorption_and_negative_mmf_preserved():
    z=pd.DataFrame({
        'Net marketable Treasury issuance':_q([1753904,2126003]),
        'Federal Reserve / central bank':_q([106632,624888]),
        'U.S.-chartered depository institutions':_q([55908,316092]),
        'Foreign banking offices in U.S.':_q([4160,43224]),
        'Banks in U.S.-affiliated areas':_q([300,4200]),
        'Credit unions':_q([2516,17972]),
        'Foreign sector':_q([110040,430923]),
        'Security brokers & dealers':_q([199116,324628]),
        'Money market funds':_q([916588,-484288]),
        'Households & nonprofits':_q([60932,241872]),
    })
    m=pd.DataFrame({
        'M2 money stock':pd.Series([22757,23218],index=pd.to_datetime(['2026-04-01','2026-07-01'])),
        'Commercial bank deposits':pd.Series([19083,19409],index=pd.to_datetime(['2026-04-01','2026-07-01'])),
        'Bank Treasury + agency securities':pd.Series([4736,4819],index=pd.to_datetime(['2026-04-01','2026-07-01'])),
    })
    out=summarize_treasury_financing(z,m)
    assert out['available']
    assert out['as_of_quarter']=='2026Q1'
    assert 47 < out['monetary_capable_absorption_pct'] < 48
    assert out['mmf_absorption_pct'] < 0
    assert out['classification']['state'] in {'ORANGE','RED'}
    mmf=next(x for x in out['holders'] if x['holder']=='Money market funds')
    assert mmf['share_of_issuance_pct'] < 0


def test_no_money_confirmation_prevents_orange_even_if_absorption_high():
    out=classify_financing_regime(45,None,20,20)
    assert out['state']=='YELLOW'


def test_red_requires_confirmation_factor():
    no_confirm=classify_financing_regime(55,7,5,25)
    assert no_confirm['state']!='RED'
    yes_confirm=classify_financing_regime(55,7,16,25)
    assert yes_confirm['state']=='RED'


def test_latest_headline_requires_common_core_quarter():
    idx=pd.to_datetime(['2025-10-01','2026-01-01'])
    z=pd.DataFrame({
        'Net marketable Treasury issuance':pd.Series([1000,1200],index=idx),
        'Federal Reserve / central bank':pd.Series([100,200],index=idx),
        'U.S.-chartered depository institutions':pd.Series([100,200],index=idx),
        'Foreign banking offices in U.S.':pd.Series([10,20],index=idx),
        'Banks in U.S.-affiliated areas':pd.Series([2,4],index=idx),
        # Credit unions intentionally lag one quarter. The headline must fall back
        # to Q4 2025 rather than combining Q1 issuance with an older CU flow.
        'Credit unions':pd.Series([20],index=idx[:1]),
    })
    out=summarize_treasury_financing(z,pd.DataFrame())
    assert out['available']
    assert out['as_of_quarter']=='2025Q4'
    assert abs(out['monetary_capable_absorption_pct']-23.2)<1e-9


def test_repo_funding_layer_is_separate_from_holder_math():
    idx=pd.to_datetime(['2025-10-01','2026-01-01'])
    z=pd.DataFrame({
        'Net marketable Treasury issuance':pd.Series([1000,1000],index=idx),
        'Federal Reserve / central bank':pd.Series([100,100],index=idx),
        'U.S.-chartered depository institutions':pd.Series([100,100],index=idx),
        'Foreign banking offices in U.S.':pd.Series([10,10],index=idx),
        'Banks in U.S.-affiliated areas':pd.Series([2,2],index=idx),
        'Credit unions':pd.Series([8,8],index=idx),
    })
    funding=pd.DataFrame({
        'Dealer repo liabilities':pd.Series([2800000,3000000],index=idx),
        'Dealer repo assets':pd.Series([1900000,2100000],index=idx),
        'MMF repo assets':pd.Series([2900000,2950000],index=idx),
    })
    out=summarize_treasury_financing(z,pd.DataFrame(),funding)
    assert abs(out['monetary_capable_absorption_pct']-22.0)<1e-9
    assert out['funding_layer']['available']
    assert out['funding_layer']['dealer_repo_gross_bn']==5100.0
    assert out['funding_layer']['dealer_repo_net_borrowing_bn']==900.0


def test_slr_is_relaxed_not_exempt():
    assert SLR_POLICY['regime']=='RELAXED'
    assert SLR_POLICY['effective_date']=='2026-04-01'
    assert SLR_POLICY['treasury_exemption'] is False
    assert SLR_POLICY['reserve_exemption'] is False


if __name__=='__main__':
    test_q1_style_absorption_and_negative_mmf_preserved()
    test_no_money_confirmation_prevents_orange_even_if_absorption_high()
    test_red_requires_confirmation_factor()
    test_latest_headline_requires_common_core_quarter()
    test_repo_funding_layer_is_separate_from_holder_math()
    test_slr_is_relaxed_not_exempt()
    print('v3.4 tests passed')
