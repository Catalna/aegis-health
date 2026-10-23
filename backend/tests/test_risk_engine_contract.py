from backend.app.agents.risk_engine import calculate_risk_score
from backend.app.models.schemas import (
    ClinicalAssessment,
    FinancialAssessment,
    FraudAssessment,
    ReviewSynthesis,
)


def clinical(flags=None):
    return ClinicalAssessment(
        claim_id="X",
        compatibility_status="match_table",
        plausibility="questionable" if flags else "plausible",
        evidence_text="",
        confidence_level="high",
        rule_flags=flags or [],
    )


def financial(anomaly=0.0, deviation=0.0):
    return FinancialAssessment(
        claim_id="X",
        predicted_cost_range=(1_000_000, 1_200_000),
        actual_cost=1_100_000,
        deviation_pct=deviation,
        shap_top_features=[],
        anomaly_score=anomaly,
        evidence_text="",
    )


def fraud(similarity=0.0, repeat=False, cloning=False, unbundling=False, isolation=0.0, graph=0.0, exact_duplicate=False):
    return FraudAssessment(
        claim_id="X",
        similarity_max_score=similarity,
        repeat_billing_flag=repeat,
        cloning_flag=cloning,
        unbundling_flag=unbundling,
        exact_duplicate=exact_duplicate,
        graph_cluster_anomaly_score=graph,
        isolation_forest_score=isolation,
        is_isolation_forest_outlier=isolation > 0.7,
        evidence_text="",
    )


def review(level):
    return ReviewSynthesis(
        claim_id="X",
        evidence_level=level,
        corroborating_signals=["unsupported LLM claim"],
        reasoning_narrative="",
        reasoning_source="llm_direct",
        model_used="test-model",
    )


def test_tariff_deviation_is_not_double_counted_as_clinical_risk():
    result = calculate_risk_score(
        clinical(["tariff_deviation_extreme"]),
        financial(),
        fraud(),
        review("strong_multi_signal"),
    )

    assert result.breakdown["clinical_rule_flags"] == 0.0
    assert result.breakdown["financial_anomaly"] == 0.0
    assert result.total_score == 0.0


def test_review_output_cannot_change_deterministic_evidence_support():
    inputs = (clinical(["severity_proc_mismatch"]), financial(anomaly=0.8), fraud())

    weak = calculate_risk_score(*inputs, review("weak"))
    strong = calculate_risk_score(*inputs, review("strong_multi_signal"))

    assert weak.breakdown == strong.breakdown
    assert weak.breakdown["evidence_support"] == 10.0


def test_behavioral_context_does_not_count_as_independent_evidence():
    result = calculate_risk_score(
        clinical(), financial(), fraud(isolation=0.95, graph=0.9), review("strong_multi_signal")
    )

    assert result.breakdown["isolation_forest_anomaly"] == 0.0
    assert result.breakdown["evidence_support"] == 0.0
    assert result.total_score == 0.0


def test_concrete_relational_signal_creates_traceable_evidence():
    result = calculate_risk_score(
        clinical(), financial(), fraud(repeat=True), review("weak")
    )

    assert result.breakdown["similarity_fraud"] == 20.0
    assert result.breakdown["evidence_support"] == 5.0
    assert any(item.signal_type == "repeat_billing" for item in result.evidence)


def test_strong_cloning_evidence_has_medium_tier_floor():
    result = calculate_risk_score(
        clinical(), financial(), fraud(similarity=0.23, cloning=True), review("weak")
    )

    assert result.total_score < 25.0
    assert result.priority_tier == "medium"
    assert any(item.signal_type == "cloning" for item in result.evidence)


def test_exact_duplicate_evidence_has_high_tier_floor():
    result = calculate_risk_score(
        clinical(), financial(), fraud(repeat=True, exact_duplicate=True), review("weak")
    )

    assert result.priority_tier == "high"
    assert any(item.signal_type == "exact_duplicate" for item in result.evidence)
