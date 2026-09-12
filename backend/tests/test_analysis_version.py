from backend.app.agents.orchestrator import ANALYSIS_VERSION
from backend.app.api.claims import is_current_analysis
from backend.app.models.schemas import EvidenceItem, RiskScore


def test_core_pipeline_analysis_version_is_newer_than_previous_contract():
    assert ANALYSIS_VERSION >= 6


def test_risk_score_serializes_traceable_evidence_items():
    score = RiskScore(
        total_score=20.0,
        breakdown={"evidence_support": 5.0},
        priority_tier="medium",
        evidence=[EvidenceItem(
            evidence_id="relational_pattern:repeat_billing",
            source_family="relational_pattern",
            signal_type="repeat_billing",
            value=True,
            explanation="Relasi klaim konkret terdeteksi.",
        )],
    )

    dumped = score.model_dump()
    assert dumped["evidence"][0]["evidence_id"] == "relational_pattern:repeat_billing"


def test_old_persisted_analysis_is_stale_at_api_boundary():
    assert is_current_analysis({"analysis_version": ANALYSIS_VERSION})
    assert not is_current_analysis({"analysis_version": ANALYSIS_VERSION - 1})
    assert not is_current_analysis({})
