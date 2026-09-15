import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend.app.agents.orchestrator import ANALYSIS_VERSION
from backend.app.api.claims import submit_decision
from backend.app.models.database import ClaimRecord, HumanDecisionRecord, RiskAnalysisRecord
from backend.app.models.schemas import HumanDecision


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DecisionSession:
    def __init__(self, claim, analysis):
        self.claim = claim
        self.analysis = analysis
        self.added = []
        self.commits = 0
        self.claim_query_locked = False
        self.current_decision = None

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is ClaimRecord:
            self.claim_query_locked = statement._for_update_arg is not None
            return _Result(self.claim)
        if entity is RiskAnalysisRecord:
            current = self.analysis and self.analysis.analysis_version == ANALYSIS_VERSION
            return _Result(self.analysis if current else None)
        if entity is HumanDecisionRecord:
            current = (
                self.current_decision
                and self.current_decision.analysis_generation == self.claim.analysis_generation
            )
            return _Result(self.current_decision if current else None)
        raise AssertionError(f"unexpected query entity: {entity}")

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


def _claim(status):
    return ClaimRecord(
        claim_id="DECISION-001",
        patient_id="PAT-001",
        provider_id="FAC-001",
        doctor_id="DR-001",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100.0,
        length_of_stay=1,
        status=status,
    )


def _analysis(version=ANALYSIS_VERSION):
    return RiskAnalysisRecord(
        claim_id="DECISION-001",
        total_score=20.0,
        priority_tier="low",
        recommended_action="low_priority",
        analysis_version=version,
        evidence_json=json.dumps({"analysis_version": version}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "scanning", "failed"])
async def test_decision_rejects_non_reviewable_claim_lifecycle(status):
    db = _DecisionSession(_claim(status), _analysis())

    with pytest.raises(HTTPException) as raised:
        await submit_decision(
            "DECISION-001",
            HumanDecision(claim_id="DECISION-001", decision="Verified Valid", reviewer="reviewer"),
            db,
        )

    assert raised.value.status_code == 409
    assert db.added == []
    assert db.commits == 0
    assert db.claim_query_locked


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["processed", "review_required"])
async def test_decision_accepts_current_analysis_for_reviewable_claim(status):
    claim = _claim(status)
    db = _DecisionSession(claim, _analysis())

    response = await submit_decision(
        "DECISION-001",
        HumanDecision(claim_id="DECISION-001", decision="Verified Valid", reviewer="reviewer"),
        db,
    )

    assert response["status"] == "success"
    assert claim.status == "verified"
    assert claim.human_decision == "Verified Valid"
    assert len(db.added) == 2
    assert isinstance(db.added[0], HumanDecisionRecord)
    assert db.commits == 1
    assert db.claim_query_locked


@pytest.mark.asyncio
async def test_decision_rejects_missing_or_stale_analysis():
    for analysis in (None, _analysis(ANALYSIS_VERSION - 1)):
        db = _DecisionSession(_claim("processed"), analysis)

        with pytest.raises(HTTPException) as raised:
            await submit_decision(
                "DECISION-001",
                HumanDecision(claim_id="DECISION-001", decision="Verified Valid", reviewer="reviewer"),
                db,
            )

        assert raised.value.status_code == 409
        assert db.added == []
        assert db.commits == 0


@pytest.mark.asyncio
async def test_verified_decision_update_requires_current_generation_and_preserves_verified_at():
    claim = _claim("verified")
    claim.analysis_generation = "generation-current"
    claim.verified_at = datetime.now(timezone.utc)
    db = _DecisionSession(claim, _analysis())
    db.current_decision = HumanDecisionRecord(
        claim_id=claim.claim_id,
        decision="Verified Valid",
        reviewer="reviewer-old",
        analysis_generation="generation-current",
    )
    verified_at = claim.verified_at

    response = await submit_decision(
        claim.claim_id,
        HumanDecision(
            claim_id=claim.claim_id,
            decision="Escalate",
            reviewer="reviewer-new",
        ),
        db,
    )

    assert response["status"] == "success"
    assert claim.status == "verified"
    assert claim.verified_at == verified_at
    saved_decision = next(item for item in db.added if isinstance(item, HumanDecisionRecord))
    assert saved_decision.decision == "Escalate"
    assert saved_decision.analysis_generation == "generation-current"


@pytest.mark.asyncio
async def test_verified_decision_update_rejects_mismatched_generation():
    claim = _claim("verified")
    claim.analysis_generation = "generation-current"
    db = _DecisionSession(claim, _analysis())
    db.current_decision = HumanDecisionRecord(
        claim_id=claim.claim_id,
        decision="Verified Valid",
        reviewer="reviewer-old",
        analysis_generation="generation-old",
    )

    with pytest.raises(HTTPException) as raised:
        await submit_decision(
            claim.claim_id,
            HumanDecision(claim_id=claim.claim_id, decision="Escalate", reviewer="reviewer-new"),
            db,
        )

    assert raised.value.status_code == 409
    assert db.added == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_verified_decision_with_missing_timestamp_is_repaired_without_overwriting_history():
    claim = _claim("verified")
    claim.analysis_generation = "generation-current"
    claim.verified_at = None
    db = _DecisionSession(claim, _analysis())
    db.current_decision = HumanDecisionRecord(
        claim_id=claim.claim_id,
        decision="Verified Valid",
        reviewer="reviewer-old",
        analysis_generation="generation-current",
    )

    response = await submit_decision(
        claim.claim_id,
        HumanDecision(
            claim_id=claim.claim_id,
            decision="Escalate",
            reviewer="reviewer-new",
        ),
        db,
    )

    assert response["status"] == "success"
    assert claim.verified_at is not None
    assert response["verified_at"] == claim.verified_at.isoformat()
    saved_decision = next(item for item in db.added if isinstance(item, HumanDecisionRecord))
    assert saved_decision.decision == "Escalate"


@pytest.mark.asyncio
async def test_legacy_verified_decision_with_null_generation_can_be_edited_safely():
    claim = _claim("verified")
    claim.analysis_generation = None
    claim.verified_at = datetime(2026, 9, 13, 10, 10, tzinfo=timezone.utc)
    db = _DecisionSession(claim, _analysis())
    db.current_decision = HumanDecisionRecord(
        claim_id=claim.claim_id,
        decision="Verified Valid",
        reviewer="legacy-reviewer",
        analysis_generation=None,
    )

    response = await submit_decision(
        claim.claim_id,
        HumanDecision(
            claim_id=claim.claim_id,
            decision="Request Clarification",
            reviewer="new-reviewer",
        ),
        db,
    )

    assert response["status"] == "success"
    assert claim.verified_at == datetime(2026, 9, 13, 10, 10, tzinfo=timezone.utc)
    saved_decision = next(item for item in db.added if isinstance(item, HumanDecisionRecord))
    assert saved_decision.decision == "Request Clarification"
    assert saved_decision.analysis_generation is None
