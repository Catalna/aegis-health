import asyncio

import pytest

from backend.app.agents import orchestrator
from backend.app.models.database import ClaimRecord
from backend.app.models.schemas import (
    ClaimExplanation,
    ClinicalAssessment,
    FinancialAssessment,
    FraudAssessment,
    RiskScore,
    ReviewSynthesis,
    ValidationResult,
)
from backend.app.core.errors import ANALYSIS_FAILURE_MESSAGE


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return []


class _PersistenceSession:
    def __init__(self, claim):
        self.claim = claim
        self.merged = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        if statement.column_descriptions[0].get("entity") is ClaimRecord:
            return _Result(self.claim)
        return _Result([])

    def add(self, value):
        self.added.append(value)

    async def merge(self, value):
        self.merged.append(value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _claim():
    return ClaimRecord(
        claim_id="ORCH-GENERATION",
        patient_id="PAT-ORCH",
        provider_id="FAC-ORCH",
        doctor_id="DR-ORCH",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100.0,
        length_of_stay=1,
        status="pending",
        analysis_generation="reset-generation",
    )


@pytest.mark.asyncio
async def test_orchestrator_does_not_persist_result_after_reset_generation(monkeypatch, normal_claim):
    claim = _claim()
    db = _PersistenceSession(claim)
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", lambda: db)

    async def valid(*_):
        return ValidationResult(claim_id="ORCH-GENERATION")

    async def clinical(*_):
        return _clinical()

    async def financial(*_):
        return _financial()

    async def fraud(*_):
        return _fraud()

    async def review(*_):
        return _review()

    async def explanation(*_):
        return _explanation()

    monkeypatch.setattr(orchestrator, "validate_deterministic", valid)
    monkeypatch.setattr(orchestrator, "analyze_clinical", clinical)
    monkeypatch.setattr(orchestrator, "analyze_financial", financial)
    monkeypatch.setattr(orchestrator, "analyze_fraud", fraud)
    monkeypatch.setattr(orchestrator, "synthesize_review", review)
    monkeypatch.setattr(orchestrator, "calculate_risk_score", lambda *_: _risk())
    monkeypatch.setattr(orchestrator, "generate_explanation", explanation)

    result = await orchestrator.process_claim(
        normal_claim.model_copy(update={"claim_id": claim.claim_id}),
        analysis_generation="old-generation",
    )

    assert result.score is not None
    assert db.merged == []
    assert db.commits == 0
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_orchestrator_sse_error_is_stable_while_raw_exception_is_logged(monkeypatch, normal_claim, caplog):
    db = _PersistenceSession(_claim())
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", lambda: db)

    async def invalid(*_):
        raise RuntimeError("secret backend connection details")

    monkeypatch.setattr(orchestrator, "validate_deterministic", invalid)
    queue = asyncio.Queue()
    terminal_outcome = {}

    with caplog.at_level("ERROR"):
        result = await orchestrator.process_claim(
            normal_claim,
            sse_queue=queue,
            terminal_outcome=terminal_outcome,
        )

    events = [queue.get_nowait() for _ in range(queue.qsize())]
    error_event = next(event for event in events if event["event"] == "error")
    assert error_event["data"]["message"] == ANALYSIS_FAILURE_MESSAGE
    assert result.reject_reason == ANALYSIS_FAILURE_MESSAGE
    assert result.error_code == "analysis_retryable"
    assert terminal_outcome["assessment"] == result
    assert "secret backend connection details" not in error_event["data"]["message"]
    assert "secret backend connection details" in caplog.text


@pytest.mark.asyncio
async def test_orchestrator_agent_run_output_does_not_persist_fallback_exception(monkeypatch, normal_claim):
    db = _PersistenceSession(_claim())
    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", lambda: db)

    async def valid(*_):
        return ValidationResult(claim_id="ORCH-GENERATION")

    async def fail(*_):
        raise RuntimeError("SECRET_PERSISTED_EXCEPTION")

    async def financial(*_):
        return _financial()

    async def fraud(*_):
        return _fraud()

    async def review(*_):
        return _review()

    async def explanation(*_):
        return _explanation()

    monkeypatch.setattr(orchestrator, "validate_deterministic", valid)
    monkeypatch.setattr(orchestrator, "analyze_clinical", fail)
    monkeypatch.setattr(orchestrator, "analyze_financial", financial)
    monkeypatch.setattr(orchestrator, "analyze_fraud", fraud)
    monkeypatch.setattr(orchestrator, "synthesize_review", review)
    monkeypatch.setattr(orchestrator, "calculate_risk_score", lambda *_: _risk())
    monkeypatch.setattr(orchestrator, "generate_explanation", explanation)

    await orchestrator.process_claim(normal_claim)

    persisted = " ".join(getattr(record, "output_json", "") or "" for record in db.added)
    assert "SECRET_PERSISTED_EXCEPTION" not in persisted
    evidence = " ".join(getattr(record, "evidence_json", "") or "" for record in db.merged)
    assert "SECRET_PERSISTED_EXCEPTION" not in evidence


def _clinical():
    return ClinicalAssessment(
        claim_id="ORCH-GENERATION",
        compatibility_status="no_data",
        plausibility="n/a",
        evidence_text="test",
        confidence_level="low",
    )


def _financial():
    return FinancialAssessment(
        claim_id="ORCH-GENERATION",
        predicted_cost_range=(100.0, 120.0),
        actual_cost=100.0,
        deviation_pct=0.0,
        shap_top_features=[],
        anomaly_score=0.0,
    )


def _fraud():
    return FraudAssessment(
        claim_id="ORCH-GENERATION",
        similarity_max_score=0.0,
        repeat_billing_flag=False,
        graph_cluster_anomaly_score=0.0,
        evidence_text="test",
    )


def _review():
    return ReviewSynthesis(
        claim_id="ORCH-GENERATION",
        evidence_level="weak",
        corroborating_signals=[],
        reasoning_narrative="test",
        reasoning_source="rule_fallback",
    )


def _risk():
    return RiskScore(total_score=10.0, breakdown={}, priority_tier="low")


def _explanation():
    return ClaimExplanation(
        claim_id="ORCH-GENERATION",
        narrative_id="test",
        ranked_reasons=[],
        recommended_action="low_priority",
        qa_panel={
            "why_top_priority": "test",
            "most_similar_claim": "none",
            "strongest_evidence": "none",
        },
    )
