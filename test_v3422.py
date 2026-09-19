from __future__ import annotations

from dollar_dashboard import __version__
from dollar_dashboard.run_history import APP_VERSION, SCHEMA_VERSION, SCORE_MODEL_VERSION
from dollar_dashboard import llm


def _payload():
    return {
        "scores": {
            "observed_position_unwind": {
                "latest_position_asof_date": "2026-09-08",
                "latest_expected_publication_date": "2026-09-11",
                "next_position_asof_date": "2026-09-15",
                "next_expected_publication_date": "2026-09-18",
            }
        },
        "snapshot": {"timestamp": "2026-09-18T19:16:00Z", "upcoming_auctions": []},
    }


def test_v3422_version_lineage_unchanged_score_model():
    assert __version__ == "3.4.25"
    assert APP_VERSION == "3.4.25"
    assert SCHEMA_VERSION == "3.4.1"
    assert SCORE_MODEL_VERSION == "3.4.3"


def test_cftc_tuesday_cannot_be_called_report_date():
    violations=llm.red_team_narrative_violations(
        "A Sep 15 CFTC report confirming unwind would change the stance.", _payload()
    )
    assert any("position-as-of" in v and "2026-09-15" in v for v in violations)


def test_cftc_asof_plus_expected_publication_is_allowed():
    text="CFTC positions as of Sep 15 are expected to publish Sep 18; that publication will test the unwind."
    assert llm.red_team_narrative_violations(text,_payload()) == []


def test_aging_evidence_cannot_be_called_fresh():
    violations=llm.red_team_narrative_violations(
        "Do not escalate while the clean 10Y/30Y KILL evidence remains fresh (AGING).", _payload()
    )
    assert any("AGING" in v and "fresh" in v for v in violations)


def test_aging_evidence_can_be_described_as_active_but_aging():
    text="The clean 10Y/30Y KILL remains active but AGING, with reduced evidentiary weight."
    assert llm.red_team_narrative_violations(text,_payload()) == []


def test_prompt_contains_tenor_specific_and_date_rules():
    src=llm.analyze_with_local_llm.__code__.co_consts
    joined="\n".join(str(x) for x in src if isinstance(x,str))
    assert "CFTC DATE NAMING RULE" in joined
    assert "EVENT FRESHNESS VOCABULARY" in joined
    assert "TENOR-SPECIFIC AUCTION TRIGGER RULE" in joined
