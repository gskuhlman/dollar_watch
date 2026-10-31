from pathlib import Path

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION
from dollar_dashboard.scoring import score


def test_v3410_version():
    assert __version__ == "3.4.27"
    assert APP_VERSION == "3.4.27"


def test_navigation_is_immediately_below_title_before_results():
    src = Path("app.py").read_text(encoding="utf-8")
    title = src.index('st.title("dollar_watch — Dollar Crisis Early Warning Dashboard V3.4.27")')
    tabs = src.index('=st.tabs([')
    spinner = src.index('with st.spinner(')
    executive = src.index('with exec_tab:')
    status = src.index('# Status: six regime indices. Delta is fixed 1D')
    assert title < tabs < spinner < executive < status
    assert src.count('=st.tabs([') == 1
    assert '"V3.4.27 Roadmap"' in src


def test_human_intent_gate_has_explicit_status():
    out = score({}, {"scores": {}}, {})
    gate = out["regime_evidence_coverage_details"]["Managed dollar devaluation"]
    assert gate["broad_intent_human_gate"] is True
    assert gate["broad_intent_human_gate_status"] == "UNSATISFIED"

    approved = {
        "approved_verification_evidence": [
            {
                "bucket": "Broad USD intent",
                "effect_target": "managed_devaluation",
                "effect_direction": 1,
                "effect_weight": 2,
            }
        ]
    }
    out2 = score(approved, {"scores": {}}, {})
    gate2 = out2["regime_evidence_coverage_details"]["Managed dollar devaluation"]
    assert gate2["broad_intent_human_gate_status"] == "SATISFIED"


def test_intervention_direction_semantics_are_explicit():
    out = score({}, {"scores": {}}, {})
    sem = out["fx_intervention_direction_semantics"]
    assert "lower USDJPY" in sem["JPY_BUY_FX_SELL"]
    assert "short-JPY squeeze" in sem["JPY_BUY_FX_SELL"]
    assert "raise USDJPY" in sem["JPY_SELL_FX_BUY"]
    assert "favorable to short-JPY" in sem["JPY_SELL_FX_BUY"]


def test_llm_has_holder_buyback_and_direction_guardrails():
    src = Path("dollar_dashboard/llm.py").read_text(encoding="utf-8")
    assert "Z.1 HOLDER-FLOW CAUSALITY RULE" in src
    assert '"cleared only with"' in src
    assert "BUYBACK VOCABULARY RULE" in src
    assert '"well-subscribed"' in src
    assert "FX INTERVENTION DIRECTION RULE" in src
    assert "Never say yen-selling would \"squeeze JPY shorts the other way.\"" in src
    assert "HUMAN INTENT GATE VOCABULARY" in src
