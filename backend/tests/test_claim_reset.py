import asyncio
import pytest
from sqlalchemy.sql.dml import Delete
from datetime import datetime, timezone

from backend.app.api import claims as claims_api
from backend.app.agents.orchestrator import ANALYSIS_VERSION
from backend.app.models.database import AuditLogRecord, ClaimRecord, HumanDecisionRecord, RiskAnalysisRecord


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _ResetSession:
    def __init__(self, claim):
        self.claim = claim
        self.commits = 0
        self.deleted_tables = []

    async def execute(self, statement):
        if isinstance(statement, Delete):
            self.deleted_tables.append(statement.table.name)
            return _Result(None)
        entity = statement.column_descriptions[0].get("entity", None)
        if entity is ClaimRecord:
            return _Result(self.claim)
        return _Result(None)

    async def commit(self):
        self.commits += 1


class _DecisionSession:
    def __init__(self, claim):
        self.claim = claim
        self.decision = None
        self.analysis = RiskAnalysisRecord(
            claim_id=claim.claim_id,
            total_score=20.0,
            priority_tier="low",
            recommended_action="low_priority",
            analysis_version=ANALYSIS_VERSION,
            evidence_json='{"analysis_version": 6}',
        )
        self.added = []
        self.commits = 0
        self.claim_lookup_locked = False

    async def execute(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is ClaimRecord:
            return _Result(self.claim)
        if entity is RiskAnalysisRecord:
            return _Result(self.analysis)
        if entity is HumanDecisionRecord:
            if self.decision and self.decision.analysis_generation != self.claim.analysis_generation:
                return _Result(None)
            return _Result(self.decision)
        raise AssertionError(f"unexpected query entity: {entity}")

    async def scalar(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is ClaimRecord:
            self.claim_lookup_locked = statement._for_update_arg is not None
            return self.claim
        return (await self.execute(statement)).scalar_one_or_none()

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


def _claim():
    from datetime import datetime, timezone

    claim = ClaimRecord(
        claim_id="RESET-001",
        patient_id="PAT-RESET",
        provider_id="FAC-RESET",
        doctor_id="DR-RESET",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100.0,
        length_of_stay=1,
        status="failed",
        analysis_started_at=datetime.now(timezone.utc),
        analysis_heartbeat_at=datetime.now(timezone.utc),
        analyzed_at=datetime.now(timezone.utc),
        verified_at=datetime.now(timezone.utc),
        analysis_attempts=3,
        last_analysis_error="failed permanently",
    )
    claim.human_decision = "Escalate"
    claim.risk_score = 90.0
    claim.priority_tier = "high"
    return claim


@pytest.mark.asyncio
async def test_reset_clears_lifecycle_and_requeues_claim(monkeypatch):
    claim = _claim()
    old_generation = claim.analysis_generation
    db = _ResetSession(claim)
    notifications = []
    monkeypatch.setattr(claims_api, "enqueue_claim", notifications.append)

    response = await claims_api.reset_claim(claim.claim_id, db)

    assert response["status"] == "success"
    assert claim.status == "pending"
    assert claim.analysis_attempts == 0
    assert claim.last_analysis_error is None
    assert claim.analysis_started_at is None
    assert claim.analysis_heartbeat_at is None
    assert claim.analyzed_at is None
    assert claim.verified_at is None
    assert claim.risk_score is None
    assert claim.priority_tier is None
    assert claim.human_decision is None
    assert claim.analysis_generation != old_generation
    assert notifications == [claim.claim_id]
    assert "risk_analyses" in db.deleted_tables
    assert "human_decisions" not in db.deleted_tables


@pytest.mark.asyncio
async def test_submit_decision_sets_verified_at(monkeypatch):
    claim = _claim()
    claim.verified_at = None
    claim.status = "processed"
    db = _DecisionSession(claim)

    before = datetime.now(timezone.utc)
    response = await claims_api.submit_decision(
        claim.claim_id,
        claims_api.HumanDecision(
            claim_id=claim.claim_id,
            decision="Verified Valid",
            reviewer="VERIFIER-1",
        ),
        db,
    )
    after = datetime.now(timezone.utc)

    assert response["status"] == "success"
    assert before <= claim.verified_at <= after
    assert response["verified_at"] == claim.verified_at.isoformat()
    assert any(isinstance(item, HumanDecisionRecord) for item in db.added)
    saved_decision = next(item for item in db.added if isinstance(item, HumanDecisionRecord))
    assert saved_decision.analysis_generation == claim.analysis_generation
    assert any(isinstance(item, AuditLogRecord) for item in db.added)


@pytest.mark.asyncio
async def test_get_decision_returns_authoritative_verified_at():
    claim = _claim()
    claim.verified_at = datetime(2026, 9, 13, 10, 10, tzinfo=timezone.utc)
    db = _DecisionSession(claim)
    db.decision = HumanDecisionRecord(
        claim_id=claim.claim_id,
        decision="Verified Valid",
        reviewer="VERIFIER-1",
        timestamp=datetime(2026, 9, 13, 10, 11, tzinfo=timezone.utc),
    )

    response = await claims_api.get_claim_decision(claim.claim_id, db)

    assert response["status"] == "decided"
    assert response["verified_at"] == claim.verified_at.isoformat()
    assert db.claim_lookup_locked


@pytest.mark.asyncio
async def test_get_decision_hides_decision_from_previous_analysis_generation():
    claim = _claim()
    claim.analysis_generation = "generation-new"
    db = _DecisionSession(claim)
    db.decision = HumanDecisionRecord(
        claim_id=claim.claim_id,
        decision="Verified Valid",
        reviewer="VERIFIER-1",
        analysis_generation="generation-old",
        timestamp=datetime(2026, 9, 13, 10, 11, tzinfo=timezone.utc),
    )

    response = await claims_api.get_claim_decision(claim.claim_id, db)

    assert response["status"] == "no_decision"


@pytest.mark.asyncio
async def test_get_decision_returns_404_for_unknown_claim():
    class MissingClaimSession:
        async def scalar(self, statement):
            return None

        async def execute(self, statement):
            raise AssertionError("decision query should not run for an unknown claim")

    with pytest.raises(claims_api.HTTPException) as raised:
        await claims_api.get_claim_decision("MISSING-CLAIM", MissingClaimSession())

    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_get_decision_cannot_race_reset_between_claim_and_decision_reads():
    claim = _claim()
    claim.status = "verified"
    claim.analysis_generation = "generation-old"
    claim.verified_at = datetime(2026, 9, 13, 10, 10, tzinfo=timezone.utc)
    old_decision = HumanDecisionRecord(
        claim_id=claim.claim_id,
        decision="Verified Valid",
        reviewer="reviewer-old",
        analysis_generation="generation-old",
        timestamp=datetime(2026, 9, 13, 10, 11, tzinfo=timezone.utc),
    )

    class RaceSession:
        def __init__(self):
            self.row_lock = asyncio.Lock()
            self.claim_read = asyncio.Event()
            self.decision = old_decision
            self.reset_completed = False

        async def scalar(self, statement):
            entity = statement.column_descriptions[0].get("entity")
            assert entity is ClaimRecord
            if statement._for_update_arg is not None:
                await self.row_lock.acquire()
            self.claim_read.set()
            return claim

        async def execute(self, statement):
            entity = statement.column_descriptions[0].get("entity")
            assert entity is HumanDecisionRecord
            current = self.decision.analysis_generation == claim.analysis_generation
            return _Result(self.decision if current else None)

        async def reset_generation(self):
            await self.row_lock.acquire()
            try:
                claim.analysis_generation = "generation-new"
                claim.verified_at = None
                self.reset_completed = True
            finally:
                self.row_lock.release()

    db = RaceSession()
    read_task = asyncio.create_task(claims_api.get_claim_decision(claim.claim_id, db))
    await db.claim_read.wait()
    reset_task = asyncio.create_task(db.reset_generation())
    await asyncio.sleep(0)
    assert not reset_task.done()

    response = await read_task
    assert not reset_task.done()
    db.row_lock.release()
    await reset_task

    assert response["status"] == "decided"
    assert response["decision"] == "Verified Valid"
    assert response["verified_at"] == "2026-09-13T10:10:00+00:00"
    assert db.reset_completed
