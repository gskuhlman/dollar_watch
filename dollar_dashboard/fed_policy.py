from __future__ import annotations

import math


def _num(v, default=None):
    try:
        x=float(v)
        return default if math.isnan(x) else x
    except Exception:
        return default


def classify_fed_treasury_change(fred_summary: dict) -> dict:
    """Classify the composition of Fed Treasury holdings without inferring motive from totals alone.

    This is a data-derived taxonomy. It deliberately avoids calling bill accumulation QE, fiscal rescue,
    or reserve-management policy unless the balance-sheet composition supports that narrower description.
    Policy motive still requires primary-source verification.
    """
    def ch(label, window='1y_change'):
        return _num((fred_summary.get(label) or {}).get(window))

    total = ch('Fed Treasury holdings (millions)')
    bills = ch('Fed Treasury bills (millions)')
    nominal = ch('Fed Treasury nominal notes/bonds (millions)')
    tips = ch('Fed Treasury TIPS principal (millions)')
    mbs = ch('Fed MBS holdings (millions)')
    walcl = ch('Fed balance sheet (millions)')

    values={
        'treasury_change_1y_mn': total,
        'bills_change_1y_mn': bills,
        'nominal_notes_bonds_change_1y_mn': nominal,
        'tips_change_1y_mn': tips,
        'mbs_change_1y_mn': mbs,
        'total_assets_change_1y_mn': walcl,
    }
    known=[x for x in [total,bills,nominal,tips,mbs] if x is not None]
    if len(known)<3:
        return {**values,'classification':'INSUFFICIENT_DATA','confidence':25.0,'interpretation':'Fed holdings composition is incomplete; do not infer QE, reinvestment, or fiscal rescue.'}

    long_change=sum(x or 0.0 for x in [nominal,tips])
    classification='MIXED_PORTFOLIO_CHANGE'
    confidence=60.0
    interpretation='Treasury holdings changed across multiple maturity buckets; motive requires primary-source verification.'

    if bills is not None and bills > 50_000 and (total or 0) > 50_000 and abs(long_change) <= max(50_000, abs(bills)*0.35):
        if mbs is not None and mbs < -50_000:
            classification='BILL_ACCUMULATION_WITH_MBS_RUNOFF'
            confidence=90.0
            interpretation=('Treasury growth is concentrated in bills while MBS runs off. This composition is consistent with reserve-management purchases and/or MBS reinvestment into bills; it is not by itself evidence of QE or an auction-rescue program.')
        else:
            classification='BILL_HEAVY_TREASURY_ACCUMULATION'
            confidence=82.0
            interpretation=('Treasury growth is concentrated in bills rather than duration. Treat as reserve-management/liquidity implementation evidence unless primary sources establish another purpose; not automatic QE/fiscal-rescue evidence.')
    elif long_change > 100_000 and (walcl or 0) > 100_000:
        classification='DURATION_HOLDINGS_EXPANSION'
        confidence=78.0
        interpretation=('Fed holdings of longer-duration Treasuries and total assets are expanding materially. This warrants primary-source verification of the operating framework before assigning QE/fiscal-support intent.')
    elif (total or 0) <= 25_000 and (mbs or 0) < -50_000:
        classification='RUNOFF_OR_STABLE_TREASURIES'
        confidence=80.0
        interpretation='Treasury holdings are broadly stable while MBS declines; no data-derived evidence of broad Treasury purchase expansion.'

    bill_share=None
    if total not in (None,0) and bills is not None:
        bill_share=100.0*bills/total
    return {**values,'bill_share_of_treasury_change_pct':bill_share,'classification':classification,'confidence':confidence,'interpretation':interpretation}
