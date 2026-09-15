from datetime import datetime, timedelta, timezone
import asyncio
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy.sql.dml import Update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select, text

from backend.app.agents.orchestrator import ANALYSIS_VERSION
from backend.app.core.errors import (
    ANALYSIS_RETRYABLE_CODE,
    ANALYSIS_RETRYABLE_MESSAGE,
    VALIDATION_REJECTED_CODE,
    VALIDATION_REJECTED_MESSAGE,
)
from backend.app.models.database import (
    Base,
    ClaimRecord,
    DATABASE_URL,
    RiskAnalysisRecord,
)
from backend.app.models.schemas import RiskAssessment, RiskScore
from backend.app.services.claim_queue import ClaimQueueWorker


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        values = self.value if isinstance(self.value, list) else [self.value]
        return _Scalars([value for value in values if value is not None])


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Session:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        if isinstance(statement, Update):
            params = statement.compile().params
            claim_id = next(
                value for value in params.values()
                if any(value == claim.claim_id for claim in self.store.claims)
            )
            claim = next(claim for claim in self.store.claims if claim.claim_id == claim_id)
            generation = next(
                (value for key, value in params.items() if "analysis_generation" in key),
                None,
            )
            if generation is not None and claim.analysis_generation != generation:
                return _Result(None)
            for column, value in statement._values.items():
                setattr(claim, column.name, params.get(value.key, value.value))
            return _Result(None)
        entity = statement.column_descriptions[0].get("entity")
        if entity is ClaimRecord:
            for_update = statement._for_update_arg
            assert for_update is not None
            if statement._order_by_clauses:
                assert for_update.skip_locked is True
                assert statement._order_by_clauses[0].compare(
                    ClaimRecord.__table__.c.queue_sequence
                )
                candidates = [
                    claim for claim in self.store.claims if claim.status == "pending"
                ]
            else:
                params = statement.compile().params
                status_values = next(
                    (
                        value
                        for value in params.values()
                        if isinstance(value, (list, tuple))
                        and any(item in {"processed", "review_required"} for item in value)
                    ),
                    None,
                )
                if status_values is None:
                    status_values = [
                        value
                        for value in params.values()
                        if isinstance(value, str)
                        and value in {"scanning", "processed", "review_required"}
                    ] or ["scanning"]
                candidates = [
                    claim for claim in self.store.claims if claim.status in status_values
                ]
                cutoff = next(
                    (value for value in params.values() if isinstance(value, datetime)),
                    None,
                )
                if cutoff is not None and "scanning" in status_values:
                    candidates = [
                        claim for claim in candidates
                        if claim.analysis_heartbeat_at is None
                        or claim.analysis_heartbeat_at <= cutoff
                    ]
                claim_id = next(
                    (value for value in params.values()
                     if isinstance(value, str)
                     and any(value == claim.claim_id for claim in self.store.claims)),
                    None,
                )
                generation = next(
                    (value for key, value in params.items()
                     if "analysis_generation" in key),
                    None,
                )
                if claim_id is not None:
                    candidates = [claim for claim in candidates if claim.claim_id == claim_id]
                if generation is not None:
                    candidates = [
                        claim for claim in candidates
                        if claim.analysis_generation == generation
                    ]
            candidates = sorted(
                candidates,
                key=lambda claim: claim.queue_sequence,
            )
            return _Result(candidates[0] if candidates else None)
        if entity is RiskAnalysisRecord:
            claim_id = next(iter(statement.compile().params.values()))
            return _Result(self.store.analyses.get(claim_id))
        raise AssertionError(f"unexpected query entity: {entity}")

    async def commit(self):
        self.store.commits += 1

    async def rollback(self):
        self.store.rollbacks += 1


class _Store:
    def __init__(self, claims, analyses=None):
        self.claims = claims
        self.analyses = analyses or {}
        self.commits = 0
        self.rollbacks = 0

    def session(self):
        return _Session(self)


class _IntakeSession:
    def __init__(self):
        self.record = None
        self.committed = False

    async def execute(self, _statement):
        return _Result(None)

    def add(self, record):
        self.record = record

    async def commit(self):
        self.committed = True


def _claim(claim_id, sequence, status="pending", attempts=0):
    return ClaimRecord(
        claim_id=claim_id,
        patient_id=f"PAT-{claim_id}",
        provider_id="FAC-TEST",
        doctor_id="DR-TEST",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100.0,
        length_of_stay=1,
        status=status,
        received_at=datetime.now(timezone.utc),
        queue_sequence=sequence,
        analysis_attempts=attempts,
    )


def _assessment(tier):
    return RiskAssessment(
        claim_id="unused",
        score=RiskScore(
            total_score=80.0 if tier == "high" else 10.0,
            breakdown={},
            priority_tier=tier,
        ),
    )


def _rejected(reason):
    return RiskAssessment(
        claim_id="unused",
        rejected=True,
        reject_reason=reason,
    )


@pytest.mark.asyncio
async def test_worker_claims_oldest_pending_row_with_skip_locked_and_fifo():
    claims = [_claim("new", 20), _claim("old", 10)]
    store = _Store(claims)
    seen = []

    async def orchestrator(claim):
        seen.append(claim.claim_id)
        return _assessment("low")

    worker = ClaimQueueWorker(
        session_factory=store.session,
        orchestrator=orchestrator,
        poll_interval=0,
    )

    assert await worker.process_next() is True
    assert await worker.process_next() is True
    assert seen == ["old", "new"]
    assert [claim.status for claim in claims] == ["processed", "processed"]
    assert all(claim.analysis_started_at is not None for claim in claims)
    assert all(claim.analyzed_at is not None for claim in claims)


@pytest.mark.asyncio
async def test_new_automatic_generation_clears_previous_verification():
    claim = _claim("verified-reanalysis", 1)
    claim.status = "pending"
    claim.verified_at = datetime.now(timezone.utc)
    claim.human_decision = "Verified Valid"
    store = _Store([claim])

    async def orchestrator(_claim):
        return _assessment("low")

    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=orchestrator)

    assert await worker.process_next() is True
    assert claim.verified_at is None
    assert claim.human_decision is None


@pytest.mark.asyncio
async def test_intake_notifies_worker_only_after_commit(monkeypatch, normal_claim):
    from backend.app.api import claims as claims_api

    db = _IntakeSession()
    notifications = []

    async def no_index(_claim_data):
        return None

    def notify(claim_id):
        assert db.committed is True
        notifications.append(claim_id)

    monkeypatch.setattr(claims_api, "enqueue_claim", notify)
    monkeypatch.setattr(claims_api, "_index_claim_in_background", no_index)

    result = await claims_api.create_claim(
        normal_claim.model_copy(update={"claim_id": "intake-queue"}), db
    )

    assert result["status"] == "success"
    assert notifications == ["intake-queue"]


@pytest.mark.asyncio
async def test_worker_marks_high_risk_claim_review_required():
    claim = _claim("high", 1)
    store = _Store([claim])

    async def orchestrator(_claim):
        return _assessment("high")

    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=orchestrator)

    assert await worker.process_next() is True
    assert claim.status == "review_required"
    assert claim.analysis_attempts == 1
    assert claim.last_analysis_error is None


@pytest.mark.asyncio
async def test_worker_does_not_rerun_claim_with_existing_analysis():
    claim = _claim("already-analyzed", 1)
    analysis = RiskAnalysisRecord(
        claim_id=claim.claim_id,
        total_score=90.0,
        priority_tier="high",
        recommended_action="verify_immediately",
        analysis_version=ANALYSIS_VERSION,
        evidence_json=json.dumps({"analysis_version": ANALYSIS_VERSION}),
    )
    store = _Store([claim], {claim.claim_id: analysis})
    calls = []

    async def orchestrator(_claim):
        calls.append(_claim.claim_id)
        return _assessment("high")

    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=orchestrator)

    assert await worker.process_next() is True
    assert calls == []
    assert claim.status == "review_required"
    assert claim.analyzed_at is not None
    assert claim.risk_score == 90.0
    assert claim.priority_tier == "high"


@pytest.mark.asyncio
async def test_recovery_leaves_processed_claim_with_current_analysis_artifact():
    claim = _claim("current-processed", 1, status="processed")
    claim.analyzed_at = datetime.now(timezone.utc)
    analysis = RiskAnalysisRecord(
        claim_id=claim.claim_id,
        total_score=10.0,
        priority_tier="low",
        recommended_action="low_priority",
        analysis_version=ANALYSIS_VERSION,
        evidence_json=json.dumps({"analysis_version": ANALYSIS_VERSION}),
    )
    store = _Store([claim], {claim.claim_id: analysis})
    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=None)

    assert await worker.recover_stale_scanning() == 0
    assert claim.status == "processed"


@pytest.mark.asyncio
async def test_worker_reruns_stale_analysis_instead_of_reusing_it():
    claim = _claim("stale-analysis", 1)
    analysis = RiskAnalysisRecord(
        claim_id=claim.claim_id,
        total_score=90.0,
        priority_tier="high",
        recommended_action="verify_immediately",
        evidence_json=json.dumps({"analysis_version": ANALYSIS_VERSION - 1}),
    )
    store = _Store([claim], {claim.claim_id: analysis})
    calls = []

    async def orchestrator(received_claim):
        calls.append(received_claim.claim_id)
        return _assessment("low")

    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=orchestrator)

    assert await worker.process_next() is True
    assert calls == [claim.claim_id]
    assert claim.status == "processed"


@pytest.mark.asyncio
async def test_worker_retries_then_marks_failure_after_bounded_attempts():
    claim = _claim("flaky", 1)
    store = _Store([claim])
    calls = 0

    async def orchestrator(_claim):
        nonlocal calls
        calls += 1
        raise RuntimeError("orchestrator unavailable")

    worker = ClaimQueueWorker(
        session_factory=store.session,
        orchestrator=orchestrator,
        max_attempts=2,
    )

    assert await worker.process_next() is True
    assert claim.status == "pending"
    assert claim.analysis_attempts == 1
    assert claim.last_analysis_error == ANALYSIS_RETRYABLE_MESSAGE
    assert claim.last_analysis_error_code == ANALYSIS_RETRYABLE_CODE
    assert "orchestrator unavailable" not in claim.last_analysis_error
    assert claim.analyzed_at is None

    assert await worker.process_next() is True
    assert claim.status == "failed"
    assert claim.analysis_attempts == 2
    assert claim.last_analysis_error == ANALYSIS_RETRYABLE_MESSAGE
    assert "orchestrator unavailable" not in claim.last_analysis_error
    assert claim.analyzed_at is not None
    assert calls == 2


@pytest.mark.asyncio
async def test_orchestration_rejection_is_retried_but_validation_rejection_is_terminal():
    transient_claim = _claim("transient", 1)
    transient_store = _Store([transient_claim])

    async def transient_orchestrator(_claim):
        return _rejected("Orchestration failed: temporary outage")

    transient_worker = ClaimQueueWorker(
        session_factory=transient_store.session,
        orchestrator=transient_orchestrator,
        max_attempts=2,
    )

    assert await transient_worker.process_next() is True
    assert transient_claim.status == "pending"
    assert transient_claim.analysis_attempts == 1
    assert await transient_worker.process_next() is True
    assert transient_claim.status == "failed"
    assert transient_claim.analysis_attempts == 2

    validation_claim = _claim("validation", 2)
    validation_store = _Store([validation_claim])

    async def validation_orchestrator(_claim):
        return _rejected("Validation failed: malformed claim")

    validation_worker = ClaimQueueWorker(
        session_factory=validation_store.session,
        orchestrator=validation_orchestrator,
        max_attempts=3,
    )

    assert await validation_worker.process_next() is True
    assert validation_claim.status == "failed", validation_claim.last_analysis_error
    assert validation_claim.analysis_attempts == 1
    assert validation_claim.last_analysis_error == VALIDATION_REJECTED_MESSAGE
    assert validation_claim.last_analysis_error_code == VALIDATION_REJECTED_CODE
    assert "malformed claim" not in validation_claim.last_analysis_error
    assert await validation_worker.process_next() is False


@pytest.mark.asyncio
async def test_worker_recovers_stale_scanning_rows_on_startup():
    claim = _claim("stale", 1, status="scanning", attempts=1)
    claim.analysis_started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    store = _Store([claim])
    worker = ClaimQueueWorker(
        session_factory=store.session,
        orchestrator=lambda _claim: _assessment("low"),
        stale_after=timedelta(minutes=10),
    )

    recovered = await worker.recover_stale_scanning()

    assert recovered == 1
    assert claim.status == "pending"
    assert claim.analysis_started_at is None


@pytest.mark.asyncio
async def test_worker_recovers_orphaned_scanning_claim_without_timestamp():
    claim = _claim("orphaned", 1, status="scanning", attempts=1)
    store = _Store([claim])
    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=None)

    recovered = await worker.recover_stale_scanning()

    assert recovered == 1
    assert claim.status == "pending"
    assert claim.analysis_started_at is None


@pytest.mark.asyncio
async def test_startup_requeues_recent_scanning_rows_as_orphans():
    claim = _claim("startup-recent", 1, status="scanning", attempts=1)
    claim.analysis_started_at = datetime.now(timezone.utc)
    claim.analysis_heartbeat_at = datetime.now(timezone.utc)
    store = _Store([claim])
    worker = ClaimQueueWorker(
        session_factory=store.session,
        orchestrator=None,
        stale_after=timedelta(minutes=10),
    )

    recovered = await worker.recover_startup_claims()

    assert recovered == 1
    assert claim.status == "pending"
    assert claim.analysis_heartbeat_at is None


@pytest.mark.asyncio
async def test_worker_start_uses_startup_recovery_before_periodic_leases():
    calls = []
    worker = ClaimQueueWorker(
        session_factory=lambda: None,
        poll_interval=1,
        recovery_interval=1,
    )

    async def startup():
        calls.append("startup")
        return 0

    async def periodic():
        calls.append("periodic")
        return 0

    async def no_terminal():
        return 0

    worker.recover_startup_claims = startup
    worker.recover_expired_leases = periodic
    worker.recover_invalid_terminal_analysis = no_terminal
    worker.process_next = lambda: asyncio.sleep(0, result=False)

    await worker.start()
    try:
        assert calls == ["startup"]
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_periodic_recovery_keeps_recent_scanning_rows_owned_by_live_worker():
    claim = _claim("periodic-recent", 1, status="scanning", attempts=1)
    claim.analysis_heartbeat_at = datetime.now(timezone.utc)
    store = _Store([claim])
    worker = ClaimQueueWorker(
        session_factory=store.session,
        orchestrator=None,
        stale_after=timedelta(minutes=10),
    )

    recovered = await worker.recover_expired_leases()

    assert recovered == 0
    assert claim.status == "scanning"


@pytest.mark.asyncio
async def test_worker_does_not_recover_recent_active_scanning_claim():
    claim = _claim("recent-active", 1, status="scanning", attempts=1)
    claim.analysis_started_at = datetime.now(timezone.utc) - timedelta(hours=1)
    claim.analysis_heartbeat_at = datetime.now(timezone.utc)
    store = _Store([claim])
    worker = ClaimQueueWorker(
        session_factory=store.session,
        orchestrator=None,
        stale_after=timedelta(minutes=10),
    )

    recovered = await worker.recover_stale_scanning()

    assert recovered == 0
    assert claim.status == "scanning"
    assert claim.analysis_started_at is not None


@pytest.mark.asyncio
async def test_worker_heartbeat_is_generation_scoped_and_stops_before_requeue():
    claim = _claim("heartbeat", 1)
    store = _Store([claim])
    started = asyncio.Event()
    release = asyncio.Event()

    async def orchestrator(_claim):
        started.set()
        await release.wait()
        return _assessment("low")

    worker = ClaimQueueWorker(
        session_factory=store.session,
        orchestrator=orchestrator,
        heartbeat_interval=0.01,
    )
    task = asyncio.create_task(worker.process_next())
    await started.wait()
    generation = claim.analysis_generation
    first_heartbeat = claim.analysis_heartbeat_at
    await asyncio.sleep(0.03)

    assert claim.analysis_heartbeat_at >= first_heartbeat
    await worker._touch_claim_heartbeat(claim.claim_id, "stale-generation")
    assert claim.analysis_generation == generation

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert claim.status == "pending"
    assert claim.analysis_heartbeat_at is None


@pytest.mark.asyncio
async def test_worker_runs_lease_recovery_periodically():
    recovery_calls = 0
    second_recovery = asyncio.Event()

    async def process_next():
        await asyncio.sleep(0)
        return False

    worker = ClaimQueueWorker(
        session_factory=lambda: None,
        poll_interval=0.001,
        recovery_interval=0.005,
    )
    worker.process_next = process_next

    async def recover():
        nonlocal recovery_calls
        recovery_calls += 1
        if recovery_calls >= 2:
            second_recovery.set()

    worker.recover_expired_leases = recover
    worker.recover_invalid_terminal_analysis = lambda: asyncio.sleep(0, result=0)
    task = asyncio.create_task(worker.run())
    await asyncio.wait_for(second_recovery.wait(), timeout=1.0)
    worker._stopping.set()
    worker.notify()
    await task

    assert recovery_calls >= 2


@pytest.mark.asyncio
async def test_worker_run_survives_transient_loop_failure_and_retries():
    worker = ClaimQueueWorker(
        session_factory=lambda: None,
        poll_interval=0,
        recovery_interval=60,
    )
    calls = 0
    saw_degraded_health = False
    degraded_error_code = None

    async def process_next():
        nonlocal calls, saw_degraded_health, degraded_error_code
        calls += 1
        if calls == 1:
            raise RuntimeError("secret transient database failure")
        health = worker.health_status()
        saw_degraded_health = health["status"] == "warn"
        degraded_error_code = health["error_code"]
        worker._stopping.set()
        return False

    worker.process_next = process_next
    worker.recover_expired_leases = lambda: asyncio.sleep(0, result=0)
    worker.recover_invalid_terminal_analysis = lambda: asyncio.sleep(0, result=0)

    await asyncio.wait_for(worker.run(), timeout=1.0)

    assert calls == 2
    assert saw_degraded_health is True
    assert degraded_error_code == ANALYSIS_RETRYABLE_CODE


@pytest.mark.asyncio
async def test_worker_requeues_processed_claim_with_stale_analysis():
    claim = _claim("stale-processed", 1, status="processed")
    claim.risk_score = 88.0
    claim.priority_tier = "high"
    analysis = RiskAnalysisRecord(
        claim_id=claim.claim_id,
        total_score=88.0,
        priority_tier="high",
        recommended_action="verify_immediately",
        evidence_json=json.dumps({"analysis_version": ANALYSIS_VERSION - 1}),
    )
    store = _Store([claim], {claim.claim_id: analysis})
    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=None)

    recovered = await worker.recover_stale_scanning()

    assert recovered == 1
    assert claim.status == "pending"
    assert claim.risk_score is None
    assert claim.priority_tier is None
    assert claim.analysis_attempts == 0


@pytest.mark.asyncio
async def test_worker_cancellation_requeues_active_claim_immediately():
    claim = _claim("cancelled", 1)
    store = _Store([claim])
    started = asyncio.Event()
    release = asyncio.Event()

    async def orchestrator(_claim):
        started.set()
        await release.wait()
        return _assessment("low")

    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=orchestrator)
    task = asyncio.create_task(worker.process_next())
    await started.wait()
    assert claim.status == "scanning"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert claim.status == "pending"
    assert claim.analysis_attempts == 0
    assert claim.analysis_started_at is None


@pytest.mark.asyncio
async def test_reset_generation_prevents_late_worker_completion():
    claim = _claim("generation-race", 1)
    store = _Store([claim])
    started = asyncio.Event()
    release = asyncio.Event()

    async def orchestrator(_claim):
        started.set()
        await release.wait()
        return _assessment("high")

    worker = ClaimQueueWorker(session_factory=store.session, orchestrator=orchestrator)
    task = asyncio.create_task(worker.process_next())
    await started.wait()
    old_generation = claim.analysis_generation
    claim.status = "pending"
    claim.analysis_generation = "reset-generation"
    claim.risk_score = None
    claim.priority_tier = None
    release.set()
    await task

    assert old_generation != claim.analysis_generation
    assert claim.status == "pending"
    assert claim.risk_score is None
    assert claim.priority_tier is None


def _integration_url_or_skip():
    if os.getenv("RUN_DB_INTEGRATION") != "1":
        pytest.skip("set RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests")
    url = os.getenv("QUEUE_METADATA_TEST_DATABASE_URL")
    if not url or not url.startswith("postgresql+asyncpg://"):
        pytest.skip(
            "set QUEUE_METADATA_TEST_DATABASE_URL to an isolated PostgreSQL database"
        )
    parsed = make_url(url)
    if not (parsed.database or "").lower().startswith(("test_", "queue_test_")):
        pytest.skip("dedicated PostgreSQL database name must start with test_ or queue_test_")
    app_url = make_url(DATABASE_URL)
    if (parsed.host, parsed.port or 5432, parsed.database) == (
        app_url.host,
        app_url.port or 5432,
        app_url.database,
    ):
        pytest.skip("integration database must not be the application database")
    return url


def _postgres_claim(claim_id, status="pending"):
    return ClaimRecord(
        claim_id=claim_id,
        patient_id=f"PAT-{claim_id}",
        provider_id="FAC-INTEGRATION",
        doctor_id="DR-INTEGRATION",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100.0,
        length_of_stay=1,
        status=status,
    )


@pytest.mark.asyncio
async def test_postgres_workers_lock_distinct_fifo_rows_and_recover_without_duplicate_analysis():
    test_url = _integration_url_or_skip()
    bootstrap_engine = create_async_engine(test_url, echo=False)
    schema_name = f"queue_test_{uuid4().hex}"
    test_engine = None
    schema_created = False
    prefix = f"__test_claim_queue_{uuid4().hex}"
    claim_ids = [f"{prefix}_old", f"{prefix}_new"]
    try:
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        schema_created = True
        test_engine = create_async_engine(
            test_url,
            connect_args={"server_settings": {"search_path": f'"{schema_name}"'}},
            echo=False,
        )
        session_factory = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            db.add_all([_postgres_claim(claim_ids[0]), _postgres_claim(claim_ids[1])])
            await db.commit()

        seen = []

        async def orchestrator(claim):
            seen.append(claim.claim_id)
            await asyncio.sleep(0.05)
            return _assessment("low")

        workers = [
            ClaimQueueWorker(session_factory=session_factory, orchestrator=orchestrator),
            ClaimQueueWorker(session_factory=session_factory, orchestrator=orchestrator),
        ]
        await asyncio.gather(*(worker.process_next() for worker in workers))
        assert seen == claim_ids

        async with session_factory() as db:
            rows = (
                await db.execute(
                    select(ClaimRecord)
                    .where(ClaimRecord.claim_id.in_(claim_ids))
                    .order_by(ClaimRecord.queue_sequence)
                )
            ).scalars().all()
            assert [row.status for row in rows] == ["processed", "processed"]
            assert all(row.analysis_attempts == 1 for row in rows)
            for row in rows:
                db.add(RiskAnalysisRecord(
                    claim_id=row.claim_id,
                    total_score=10.0,
                    priority_tier="low",
                    recommended_action="low_priority",
                    analysis_version=ANALYSIS_VERSION,
                    evidence_json=json.dumps({"analysis_version": ANALYSIS_VERSION}),
                ))
            await db.commit()

            stale = _postgres_claim(f"{prefix}_stale", status="scanning")
            stale.analysis_attempts = 1
            stale.analysis_started_at = datetime.now(timezone.utc) - timedelta(hours=1)
            stale.analysis_heartbeat_at = datetime.now(timezone.utc) - timedelta(hours=1)
            healthy = _postgres_claim(f"{prefix}_healthy", status="scanning")
            healthy.analysis_attempts = 1
            healthy.analysis_started_at = datetime.now(timezone.utc) - timedelta(hours=1)
            healthy.analysis_heartbeat_at = datetime.now(timezone.utc)
            db.add(stale)
            db.add(healthy)
            db.add(RiskAnalysisRecord(
                claim_id=stale.claim_id,
                total_score=90.0,
                priority_tier="high",
                recommended_action="verify_immediately",
                analysis_version=ANALYSIS_VERSION,
                evidence_json=json.dumps({"analysis_version": ANALYSIS_VERSION}),
            ))
            await db.commit()

        worker = ClaimQueueWorker(
            session_factory=session_factory,
            orchestrator=orchestrator,
            stale_after=timedelta(minutes=10),
        )
        assert await worker.recover_stale_scanning() == 1
        assert await worker.process_next() is True
        assert seen == claim_ids

        async with session_factory() as db:
            stale_row = await db.scalar(
                select(ClaimRecord).where(ClaimRecord.claim_id == stale.claim_id)
            )
            analysis_count = await db.scalar(
                select(text("count(*)")).select_from(RiskAnalysisRecord).where(
                    RiskAnalysisRecord.claim_id == stale.claim_id
                )
            )
            assert stale_row.status == "review_required"
            assert analysis_count == 1
            healthy_row = await db.scalar(
                select(ClaimRecord).where(ClaimRecord.claim_id == healthy.claim_id)
            )
            assert healthy_row.status == "scanning"
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        if schema_created:
            async with bootstrap_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
        await bootstrap_engine.dispose()
