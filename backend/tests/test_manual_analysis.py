import asyncio
import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.sql.dml import Update

from backend.app.agents.orchestrator import ANALYSIS_VERSION
from backend.app.api import main
from backend.app.models.database import ClaimRecord, RiskAnalysisRecord
from backend.app.models.schemas import RiskAssessment, RiskScore
from backend.app.services.claim_queue import record_to_claim


@pytest.fixture(autouse=True)
def isolate_manual_global_state():
    for handle in main.manual_orphan_handles.values():
        handle.cancel()
    for handle in main.manual_grace_handles.values():
        handle.cancel()
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()
    main.manual_tasks.clear()
    main.manual_consumers.clear()
    main.manual_completed.clear()
    main.manual_orphan_handles.clear()
    main.manual_grace_handles.clear()
    yield
    for handle in main.manual_orphan_handles.values():
        handle.cancel()
    for handle in main.manual_grace_handles.values():
        handle.cancel()
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()
    main.manual_tasks.clear()
    main.manual_consumers.clear()
    main.manual_completed.clear()
    main.manual_orphan_handles.clear()
    main.manual_grace_handles.clear()


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _ManualSession:
    def __init__(self, claim, analysis=None):
        self.claim = claim
        self.analysis = analysis
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        if isinstance(statement, Update):
            params = statement.compile().params
            generation = next(
                (value for key, value in params.items() if "analysis_generation" in key),
                None,
            )
            if generation is not None and self.claim.analysis_generation != generation:
                return _Result(None)
            for column, value in statement._values.items():
                setattr(self.claim, column.name, params.get(value.key, value.value))
            return _Result(None)
        entity = statement.column_descriptions[0].get("entity")
        if entity is ClaimRecord:
            params = statement.compile().params
            generation = next(
                (value for key, value in params.items() if "analysis_generation" in key),
                None,
            )
            if generation is not None and self.claim.analysis_generation != generation:
                return _Result(None)
            return _Result(self.claim)
        if entity is RiskAnalysisRecord:
            return _Result(self.analysis)
        raise AssertionError(f"unexpected query entity: {entity}")

    async def scalar(self, statement):
        if statement.column_descriptions[0].get("entity") is ClaimRecord:
            assert statement._for_update_arg is not None
        return (await self.execute(statement)).scalar_one_or_none()

    async def commit(self):
        self.commits += 1


def _claim(status="pending", attempts=0):
    return ClaimRecord(
        claim_id="MANUAL-001",
        patient_id="PAT-MANUAL-001",
        provider_id="FAC-MANUAL",
        doctor_id="DR-MANUAL",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100.0,
        length_of_stay=1,
        status=status,
        analysis_attempts=attempts,
    )


def _analysis(claim_id="MANUAL-001", tier="high"):
    return RiskAnalysisRecord(
        claim_id=claim_id,
        total_score=80.0,
        priority_tier=tier,
        recommended_action="verify_immediately",
        analysis_version=ANALYSIS_VERSION,
        evidence_json=json.dumps({"analysis_version": ANALYSIS_VERSION}),
    )


def _assessment(tier="low"):
    return RiskAssessment(
        claim_id="MANUAL-001",
        score=RiskScore(total_score=10.0, breakdown={}, priority_tier=tier),
    )


@pytest.mark.asyncio
async def test_repeated_manual_requests_leave_pending_claim_in_fifo_queue(monkeypatch, normal_claim):
    claim = _claim(status="pending")
    db = _ManualSession(claim)
    scheduled = []

    def capture_task(coro, **_kwargs):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", capture_task)
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()

    try:
        first = await main.analyze_claim(
            normal_claim.model_copy(update={"claim_id": claim.claim_id}), db, retry=False
        )
        second = await main.analyze_claim(
            normal_claim.model_copy(update={"claim_id": claim.claim_id}), db, retry=False
        )

        assert first["status"] == "queued"
        assert second["status"] == "queued"
        assert second["task_id"] is None
        assert len(scheduled) == 0
        assert claim.status == "pending"
        assert claim.analysis_attempts == 0
        assert claim.analysis_started_at is None
    finally:
        main.investigation_queues.clear()
        main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_request_does_not_duplicate_current_analysis(monkeypatch, normal_claim):
    claim = _claim(status="processed")
    db = _ManualSession(claim, _analysis())
    scheduled = []

    def capture_task(coro, **_kwargs):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", capture_task)
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()

    response = await main.analyze_claim(
        normal_claim.model_copy(update={"claim_id": claim.claim_id}), db, retry=False
    )

    assert response["status"] == "already_processed"
    assert response["claim_id"] == claim.claim_id
    assert response["analysis_url"].endswith(f"/claims/{claim.claim_id}/analysis")
    assert scheduled == []
    assert claim.status == "review_required"
    assert claim.analyzed_at is not None


@pytest.mark.asyncio
async def test_failed_manual_claim_requires_explicit_retry(monkeypatch, normal_claim):
    claim = _claim(status="failed", attempts=3)
    claim.last_analysis_error = "previous failure"
    claim.verified_at = datetime.now(timezone.utc)
    db = _ManualSession(claim)
    scheduled = []

    def capture_task(coro, **_kwargs):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", capture_task)
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()

    try:
        blocked = await main.analyze_claim(
            normal_claim.model_copy(update={"claim_id": claim.claim_id}), db, retry=False
        )
        retried = await main.analyze_claim(
            normal_claim.model_copy(update={"claim_id": claim.claim_id}),
            db,
            retry=True,
        )

        assert blocked["status"] == "failed"
        assert blocked["retry_available"] is True
        assert retried["status"] == "started"
        assert claim.status == "scanning"
        assert claim.analysis_attempts == 4
        assert claim.last_analysis_error is None
        assert claim.verified_at is None
        assert len(scheduled) == 1
    finally:
        main.investigation_queues.clear()
        main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_pending_manual_claim_is_left_for_fifo_worker(monkeypatch, normal_claim):
    claim = _claim(status="pending")
    db = _ManualSession(claim)
    scheduled = []

    def capture_task(coro, **_kwargs):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", capture_task)

    response = await main.analyze_claim(
        normal_claim.model_copy(update={"claim_id": claim.claim_id}), db, retry=False
    )

    assert response["status"] == "queued"
    assert response["claim_id"] == claim.claim_id
    assert response["task_id"] is None
    assert claim.status == "pending"
    assert claim.analysis_attempts == 0
    assert scheduled == []


@pytest.mark.asyncio
async def test_stale_manual_claim_requires_explicit_retry(monkeypatch, normal_claim):
    claim = _claim(status="processed", attempts=1)
    stale_analysis = _analysis()
    stale_analysis.analysis_version = ANALYSIS_VERSION - 1
    stale_analysis.evidence_json = json.dumps({"analysis_version": ANALYSIS_VERSION - 1})
    db = _ManualSession(claim, stale_analysis)
    scheduled = []

    def capture_task(coro, **_kwargs):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", capture_task)

    try:
        blocked = await main.analyze_claim(
            normal_claim.model_copy(update={"claim_id": claim.claim_id}), db, retry=False
        )
        retried = await main.analyze_claim(
            normal_claim.model_copy(update={"claim_id": claim.claim_id}), db, retry=True
        )

        assert blocked["status"] == "stale"
        assert blocked["retry_available"] is True
        assert retried["status"] == "started"
        assert claim.status == "scanning"
        assert len(scheduled) == 1
    finally:
        main.investigation_queues.clear()
        main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_task_finalizes_lifecycle_fields(monkeypatch, normal_claim):
    claim = _claim(status="scanning", attempts=1)
    claim.analysis_started_at = datetime.now(timezone.utc)
    db = _ManualSession(claim)
    task_id = "manual-task"
    queue = asyncio.Queue()
    main.investigation_queues[task_id] = queue
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        return _assessment("high")

    monkeypatch.setattr(main, "process_claim", fake_process)

    try:
        await main._run_and_cleanup(normal_claim, task_id)

        assert claim.status == "review_required"
        assert claim.analysis_started_at is not None
        assert claim.analyzed_at is not None
        assert claim.last_analysis_error is None
        assert await queue.get() is None
        assert task_id in main.investigation_queues
    finally:
        main.investigation_queues.clear()
        main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_terminal_failure_clears_analysis_started_at(monkeypatch, normal_claim):
    claim = _claim(status="scanning", attempts=1)
    claim.analysis_generation = "manual-failure-generation"
    claim.analysis_started_at = datetime.now(timezone.utc)
    db = _ManualSession(claim)
    task_id = "manual-failure-task"
    main.investigation_queues[task_id] = asyncio.Queue()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        return RiskAssessment.create_rejected("MANUAL-001", "terminal validation failure")

    monkeypatch.setattr(main, "process_claim", fake_process)

    try:
        await main._run_and_cleanup(
            normal_claim, task_id, claim.claim_id, claim.analysis_generation
        )

        assert claim.status == "failed"
        assert claim.analysis_started_at is None
        assert claim.analyzed_at is not None
    finally:
        main.investigation_queues.clear()
        main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_analysis_uses_persisted_claim_payload(monkeypatch, normal_claim):
    claim = _claim()
    claim.provider_id = "PERSISTED-FACILITY"
    claim.cost_claimed = 999.0
    db = _ManualSession(claim)
    task_id = "payload-task"
    main.investigation_queues[task_id] = asyncio.Queue()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)
    received = []

    async def fake_process(received_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        received.append(received_claim)
        return _assessment("low")

    monkeypatch.setattr(main, "process_claim", fake_process)
    mismatched = normal_claim.model_copy(update={
        "claim_id": claim.claim_id,
        "provider_id": "REQUEST-FACILITY",
        "cost_claimed": 1.0,
    })
    def capture_task(coro, **_kwargs):
        coro.close()
        return object()

    real_create_task = asyncio.create_task
    monkeypatch.setattr(main.asyncio, "create_task", capture_task)

    try:
        response = await main.analyze_claim(mismatched, db, retry=False)
        monkeypatch.setattr(main.asyncio, "create_task", real_create_task)
        await main._run_and_cleanup(
            record_to_claim(claim),
            response["task_id"],
            claim.claim_id,
            claim.analysis_generation,
        )
        assert received[0].provider_id == "PERSISTED-FACILITY"
        assert received[0].cost_claimed == 999.0
    finally:
        main.investigation_queues.clear()
        main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_task_cancellation_requeues_generation(monkeypatch, normal_claim):
    claim = _claim(status="scanning", attempts=1)
    claim.analysis_generation = "manual-generation"
    claim.analysis_started_at = datetime.now(timezone.utc)
    db = _ManualSession(claim)
    task_id = "cancel-task"
    main.investigation_queues[task_id] = asyncio.Queue()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        started.set()
        await release.wait()
        return _assessment("low")

    monkeypatch.setattr(main, "process_claim", fake_process)
    task = asyncio.create_task(main._run_and_cleanup(normal_claim, task_id, claim.claim_id))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert claim.status == "pending"
    assert claim.analysis_attempts == 0
    assert claim.analysis_generation != "manual-generation"
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_cancellation_of_exhausted_retry_is_terminal(monkeypatch, normal_claim):
    claim = _claim(status="scanning", attempts=4)
    claim.analysis_generation = "manual-exhausted-generation"
    claim.analysis_started_at = datetime.now(timezone.utc)
    db = _ManualSession(claim)
    task_id = "cancel-exhausted-task"
    main.investigation_queues[task_id] = asyncio.Queue()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        started.set()
        await release.wait()
        return _assessment("low")

    monkeypatch.setattr(main, "process_claim", fake_process)
    task = asyncio.create_task(
        main._run_and_cleanup(
            normal_claim, task_id, claim.claim_id, claim.analysis_generation
        )
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert claim.status == "failed"
    assert claim.analysis_attempts == 3
    assert claim.analyzed_at is not None
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_heartbeat_is_generation_scoped_and_stops_on_cancellation(monkeypatch, normal_claim):
    claim = _claim(status="scanning", attempts=1)
    claim.analysis_generation = "manual-heartbeat-generation"
    claim.analysis_started_at = datetime.now(timezone.utc)
    claim.analysis_heartbeat_at = claim.analysis_started_at
    db = _ManualSession(claim)
    task_id = "manual-heartbeat-task"
    main.investigation_queues[task_id] = asyncio.Queue()
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(main, "MANUAL_HEARTBEAT_INTERVAL", 0.01)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        started.set()
        await release.wait()
        return _assessment("low")

    monkeypatch.setattr(main, "process_claim", fake_process)
    task = asyncio.create_task(
        main._run_and_cleanup(
            normal_claim,
            task_id,
            claim.claim_id,
            claim.analysis_generation,
        )
    )
    await started.wait()
    initial_heartbeat = claim.analysis_heartbeat_at
    await asyncio.sleep(0.03)

    assert claim.analysis_heartbeat_at >= initial_heartbeat

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert claim.status == "pending"
    assert claim.analysis_heartbeat_at is None
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_task_without_sse_consumer_is_cancelled_and_cleaned(monkeypatch, normal_claim):
    claim = _claim(status="failed", attempts=1)
    claim.last_analysis_error = "previous failure"
    db = _ManualSession(claim)
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(main, "MANUAL_SSE_ATTACH_TIMEOUT", 0.01)
    monkeypatch.setattr(main, "MANUAL_SSE_GRACE_PERIOD", 0.01)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        started.set()
        await release.wait()
        return _assessment("low")

    monkeypatch.setattr(main, "process_claim", fake_process)
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()
    main.manual_tasks.clear()

    try:
        response = await main.analyze_claim(
            normal_claim.model_copy(update={"claim_id": claim.claim_id}), db, retry=True
        )
        await started.wait()
        task_id = response["task_id"]
        task = main.manual_tasks[task_id]
        await asyncio.sleep(0.03)

        assert task.done()
        assert task_id not in main.investigation_queues
        assert claim.status == "pending"
    finally:
        release.set()
        main.investigation_queues.clear()
        main.manual_tasks_by_claim.clear()
        main.manual_tasks.clear()


@pytest.mark.asyncio
async def test_manual_consumer_disconnect_cancels_owned_task(monkeypatch, normal_claim):
    claim = _claim(status="scanning", attempts=1)
    claim.analysis_generation = "disconnect-generation"
    db = _ManualSession(claim)
    task_id = "disconnect-task"
    main.investigation_queues[task_id] = asyncio.Queue(maxsize=2)
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        started.set()
        await release.wait()
        return _assessment("low")

    monkeypatch.setattr(main, "process_claim", fake_process)
    task = asyncio.create_task(
        main._run_and_cleanup(normal_claim, task_id, claim.claim_id, claim.analysis_generation)
    )
    main.manual_tasks[task_id] = task
    main.manual_consumers.add(task_id)
    await started.wait()

    await main._cancel_manual_task(task_id)

    assert claim.status == "pending"
    assert task_id not in main.investigation_queues
    assert task.done()
    main.manual_consumers.discard(task_id)


@pytest.mark.asyncio
async def test_disconnect_after_terminal_rejection_does_not_requeue(monkeypatch, normal_claim):
    claim = _claim(status="scanning", attempts=1)
    claim.analysis_generation = "rejected-disconnect-generation"
    db = _ManualSession(claim)
    task_id = "rejected-disconnect-task"
    queue = asyncio.Queue(maxsize=4)
    main.investigation_queues[task_id] = queue
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)
    terminal_emitted = asyncio.Event()
    continue_processing = asyncio.Event()

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        assessment = RiskAssessment.create_rejected(_claim.claim_id, "deterministic validation failure")
        if terminal_outcome is not None:
            terminal_outcome["assessment"] = assessment
        sse_queue.put_nowait({"event": "rejected", "data": {"reason": assessment.reject_reason}})
        terminal_emitted.set()
        await continue_processing.wait()
        return assessment

    monkeypatch.setattr(main, "process_claim", fake_process)
    task = asyncio.create_task(
        main._run_and_cleanup(normal_claim, task_id, claim.claim_id, claim.analysis_generation)
    )
    await terminal_emitted.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert claim.status == "failed"
    assert claim.analyzed_at is not None
    assert claim.last_analysis_error == main.VALIDATION_REJECTED_MESSAGE
    assert claim.last_analysis_error_code == main.VALIDATION_REJECTED_CODE
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_manual_exception_sends_stable_error_and_logs_raw_exception(monkeypatch, normal_claim, caplog):
    claim = _claim(status="scanning", attempts=1)
    claim.analysis_generation = "manual-error-generation"
    db = _ManualSession(claim)
    task_id = "manual-error-task"
    queue = asyncio.Queue(maxsize=4)
    main.investigation_queues[task_id] = queue
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        raise RuntimeError("secret internal database details")

    monkeypatch.setattr(main, "process_claim", fake_process)
    with caplog.at_level("ERROR"):
        await main._run_and_cleanup(normal_claim, task_id, claim.claim_id, claim.analysis_generation)

    events = [queue.get_nowait() for _ in range(queue.qsize())]
    error_event = next(event for event in events if event["event"] == "error")
    message = error_event["data"]["message"]
    assert message == main.ANALYSIS_FAILURE_MESSAGE
    assert "secret internal database details" not in message
    assert claim.last_analysis_error == main.ANALYSIS_FAILURE_MESSAGE
    assert claim.last_analysis_error_code == main.ANALYSIS_RETRYABLE_CODE
    assert "secret internal database details" in caplog.text
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()


@pytest.mark.asyncio
async def test_fast_manual_completion_retains_terminal_state_for_late_sse_consumer(monkeypatch, normal_claim):
    claim = _claim(status="scanning", attempts=1)
    claim.analysis_generation = "fast-completion-generation"
    db = _ManualSession(claim)
    task_id = "fast-completion-task"
    queue = asyncio.Queue(maxsize=2)
    main.investigation_queues[task_id] = queue
    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: db)

    async def fake_process(_claim, sse_queue=None, analysis_generation=None, terminal_outcome=None):
        return _assessment("low")

    monkeypatch.setattr(main, "process_claim", fake_process)

    try:
        await main._run_and_cleanup(
            normal_claim, task_id, claim.claim_id, claim.analysis_generation
        )

        assert task_id in main.investigation_queues
        assert main.manual_completed == {task_id}

        class _Request:
            async def is_disconnected(self):
                return False

        response = await main.stream_investigation(_Request(), task_id)
        terminal = await response.body_iterator.__anext__()
        assert terminal["event"] == "done"
        with pytest.raises(StopAsyncIteration):
            await response.body_iterator.__anext__()
        assert task_id not in main.investigation_queues
    finally:
        main._cleanup_manual_state(task_id)


@pytest.mark.asyncio
async def test_sse_projection_removes_nested_internal_analysis_data():
    task_id = "sse-sanitization-task"
    queue = asyncio.Queue()
    queue.put_nowait({
        "event": "phase3_complete",
        "data": {
            "risk": {"evidence": [{"explanation": "RAW_EXCEPTION_MARKER"}]},
            "explanation": {"narrative_id": "Traceback: SECRET_PERSISTED_EXCEPTION"},
            "agent_errors": [{"raw_output": "RAW_EXCEPTION_MARKER"}],
        },
    })
    queue.put_nowait(None)
    main.investigation_queues[task_id] = queue

    class _Request:
        async def is_disconnected(self):
            return False

    response = await main.stream_investigation(_Request(), task_id)
    event = await response.body_iterator.__anext__()
    payload = json.loads(event["data"])

    assert "RAW_EXCEPTION_MARKER" not in json.dumps(payload)
    assert "SECRET_PERSISTED_EXCEPTION" not in json.dumps(payload)
    assert "agent_errors" not in payload
    assert payload["risk"]["evidence"][0]["explanation"] == main.ANALYSIS_FAILURE_MESSAGE


def test_manual_terminal_event_replaces_queued_event_when_queue_is_full():
    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait({"event": "status", "data": {"message": "old"}})

    main._offer_manual_event(queue, {"event": "rejected", "data": {"reason": "invalid"}})

    assert queue.get_nowait()["event"] == "rejected"


@pytest.mark.asyncio
async def test_manual_analysis_rejects_missing_persisted_claim(monkeypatch, normal_claim):
    db = _ManualSession(None)
    scheduled = []

    def capture_task(coro, **_kwargs):
        scheduled.append(coro)
        coro.close()
        return object()

    monkeypatch.setattr(main.asyncio, "create_task", capture_task)
    main.investigation_queues.clear()
    main.manual_tasks_by_claim.clear()

    with pytest.raises(HTTPException) as error:
        await main.analyze_claim(normal_claim, db, retry=False)

    assert error.value.status_code == 404
    assert scheduled == []
