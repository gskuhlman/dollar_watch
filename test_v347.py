from pathlib import Path
import pandas as pd

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION
from dollar_dashboard.intelligence import summarize_tic_transactions


def _sample():
    idx=pd.to_datetime(['2026-05-01','2026-06-01'])
    h=pd.DataFrame(index=idx)
    h['Foreign Treasury holdings grand total (millions)']=[10000,9927.9]  # -72.1
    h['Foreign Treasury net transactions grand total (millions)']=[0,-22.25]
    h['Foreign LT Treasury valuation change grand total (millions)']=[0,-39.15]
    h['Foreign official Treasury holdings (millions)']=[5000,4927.9]       # -72.1
    h['Foreign Treasury net transactions official (millions)']=[0,-45.4]
    h['Foreign LT Treasury valuation change official (millions)']=[0,-13.3]
    h['Foreign Treasury net transactions private (millions)']=[0,23.15]
    return h


def test_version_and_schema():
    assert __version__ == '3.4.8'
    assert APP_VERSION == '3.4.8'
    assert SCHEMA_VERSION == '3.4.1'


def test_tic_sector_reconciliation_is_self_contained():
    out=summarize_tic_transactions(_sample())
    gt=out['grand_total']; off=out['foreign_official']
    assert gt['sector']=='grand_total' and off['sector']=='foreign_official'
    assert round(gt['transaction_share_of_position_change_pct'],1)==30.9
    assert round(off['transaction_share_of_position_change_pct'],1)==63.0
    assert gt['reconciles'] and off['reconciles']
    assert abs(gt['reconciliation_error_mn']) < 1e-9
    assert abs(off['reconciliation_error_mn']) < 1e-9
    # The two sectors deliberately have different transaction shares; the UI/LLM must not mix them.
    assert gt['transaction_share_of_position_change_pct'] != off['transaction_share_of_position_change_pct']


def test_llm_has_tic_sector_integrity_guardrail():
    txt=Path('dollar_dashboard/llm.py').read_text(encoding='utf-8')
    assert 'TIC SECTOR-INTEGRITY RULE' in txt
    assert 'NEVER combine' in txt
    assert 'transaction_share_of_position_change_pct' in txt


def test_app_displays_deterministic_tic_decomposition():
    txt=Path('app.py').read_text(encoding='utf-8')
    assert 'TIC transaction / valuation decomposition' in txt
    assert 'Transactions / change %' in txt
    assert 'Reconciles' in txt


if __name__ == '__main__':
    test_version_and_schema(); test_tic_sector_reconciliation_is_self_contained(); test_llm_has_tic_sector_integrity_guardrail(); test_app_displays_deterministic_tic_decomposition()
    print('v3.4.8 tests passed')
