"""Database-backed FIFO worker for automatic claim analysis."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import or_, select, update

from backend.app.agents.orchestrator import process_claim
from backend.app.core.versions import ANALYSIS_VERSION, is_current_analysis
from backend.app.core.errors import (
    ANALYSIS_RETRYABLE_CODE,
    ANALYSIS_RETRYABLE_MESSAGE,
    VALIDATION_REJECTED_CODE,
    failure_for_exception,
    failure_for_rejection,
    safe_failure,
)
from backend.app.models.database import AsyncSessionLocal, ClaimRecord, RiskAnalysisRecord
from backend.app.models.schemas import ClaimInput, RiskAssessment


DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_STALE_AFTER = timedelta(minutes=15)
DEFAULT_HEARTBEAT_INTERVAL = 30.0
DEFAULT_RECOVERY_INTERVAL = 30.0

_active_worker: "ClaimQueueWorker | None" = None
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_claim(_claim_id: str) -> None:
    """Wake the running worker after an intake transaction commits."""
    if _active_worker is not None:
        _active_worker.notify()


def _split_csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def record_to_claim(record: ClaimRecord) -> ClaimInput:
    try:
        medication = json.loads(record.medication_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid medication_json: {exc}") from exc

    try:
        referral_info = json.loads(record.referral_json) if record.referral_json else None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid referral_json: {exc}") from exc

    return ClaimInput.model_validate({
        "claim_id": record.claim_id,
        "patient_id": record.patient_id,
        "provider_id": record.provider_id,
        "doctor_id": record.doctor_id,
        "diagnosis_primary": record.diagnosis_primary,
        "diagnosis_secondary": _split_csv(record.diagnosis_secondary),
        "procedure_codes": _split_csv(record.procedure_codes),
        "medication": medication,
        "severity_level": record.severity_level,
        "cost_claimed": record.cost_claimed,
        "length_of_stay": record.length_of_stay,
        "admission_date": record.admission_date,
        "discharge_date": record.discharge_date,
        "referral_info": referral_info,
    })


def status_for_tier(tier: str | None) -> str:
    return "review_required" if tier in {"high", "medium"} else "processed"


def _has_current_analysis(analysis: RiskAnalysisRecord | None) -> bool:
    """The lifecycle invariant for terminal AI states is a current persisted artifact."""
    if analysis is None:
        return False
    return is_current_analysis(analysis.analysis_version, analysis.evidence_json)


class ClaimQueueWorker:
    """Process pending claims with one database-coordinated asyncio worker."""

    def __init__(
        self,
        session_factory=AsyncSessionLocal,
        orchestrator: Callable[[ClaimInput], Awaitable[RiskAssessment]] = process_claim,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
        recovery_interval: float = DEFAULT_RECOVERY_INTERVAL,
        clock: Callable[[], datetime] = _utcnow,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")
        if recovery_interval <= 0:
            raise ValueError("recovery_interval must be positive")
        if heartbeat_interval >= stale_after.total_seconds():
            raise ValueError("heartbeat_interval must be shorter than stale_after")
        self.session_factory = session_factory
        self.orchestrator = orchestrator or process_claim
        self.poll_interval = poll_interval
        self.max_attempts = max_attempts
        self.stale_after = stale_after
        self.heartbeat_interval = heartbeat_interval
        self.recovery_interval = recovery_interval
        self.clock = clock
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._active_claim_id: str | None = None
        self._active_generation: str | None = None
        self._last_error_code: str | None = None

    async def start(self) -> None:
        global _active_worker
        if self._task is not None:
            return
        try:
            await self.recover_startup_claims()
        except Exception as exc:
            self._mark_degraded(exc)
            logger.exception("Claim queue startup recovery failed")
        self._stopping.clear()
        _active_worker = self
        self._task = asyncio.create_task(self.run(), name="claim-queue-worker")

    async def stop(self) -> None:
        global _active_worker
        task = self._task
        self._task = None
        self._stopping.set()
        self.notify()
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self._active_claim_id is not None:
            await self._requeue_active_claim(
                self._active_claim_id, self._active_generation
            )
            self._active_claim_id = None
            self._active_generation = None
        if _active_worker is self:
            _active_worker = None

    def notify(self) -> None:
        self._wake_event.set()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_recovery = 0.0
        while not self._stopping.is_set():
            try:
                now = loop.time()
                if now >= next_recovery:
                    await self.recover_expired_leases()
                    await self.recover_invalid_terminal_analysis()
                    next_recovery = loop.time() + self.recovery_interval
                if await self.process_next():
                    self._last_error_code = None
                    continue
                self._last_error_code = None
                self._wake_event.clear()
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._mark_degraded(exc)
                logger.exception("Claim queue worker iteration failed")
                if not self._stopping.is_set():
                    await asyncio.sleep(max(self.poll_interval, 0.1))

    async def _recover_scanning_claims(self, *, only_expired: bool) -> int:
        recovered = 0
        stale_before = self.clock() - self.stale_after
        async with self.session_factory() as db:
            filters = [ClaimRecord.status == "scanning"]
            if only_expired:
                filters.append(
                    or_(
                        ClaimRecord.analysis_heartbeat_at.is_(None),
                        ClaimRecord.analysis_heartbeat_at <= stale_before,
                    )
                )
            result = await db.execute(
                select(ClaimRecord)
                .where(*filters)
                .with_for_update(skip_locked=True)
            )
            stale_claims = result.scalars().all()
            for claim in stale_claims:
                recovered += 1
                claim.analysis_started_at = None
                claim.analysis_heartbeat_at = None
                claim.analyzed_at = None
                claim.verified_at = None
                claim.human_decision = None
                claim.analysis_generation = str(uuid.uuid4())
                if (claim.analysis_attempts or 0) >= self.max_attempts:
                    claim.status = "failed"
                    claim.analyzed_at = self.clock()
                    claim.last_analysis_error = ANALYSIS_RETRYABLE_MESSAGE
                    claim.last_analysis_error_code = ANALYSIS_RETRYABLE_CODE
                else:
                    claim.status = "pending"
                    claim.last_analysis_error = ANALYSIS_RETRYABLE_MESSAGE
                    claim.last_analysis_error_code = ANALYSIS_RETRYABLE_CODE

            if stale_claims:
                await db.commit()
        return recovered

    async def recover_startup_claims(self) -> int:
        """Treat every existing scan as orphaned when a new process starts."""
        return (
            await self._recover_scanning_claims(only_expired=False)
            + await self.recover_invalid_terminal_analysis()
        )

    async def recover_expired_leases(self) -> int:
        """Recover only scans whose heartbeat lease has expired."""
        return await self._recover_scanning_claims(only_expired=True)

    async def recover_invalid_terminal_analysis(self) -> int:
        """Requeue terminal rows that lack a current persisted analysis artifact."""
        recovered = 0
        async with self.session_factory() as db:
            processed_result = await db.execute(
                select(ClaimRecord)
                .where(ClaimRecord.status.in_(["processed", "review_required"]))
                .with_for_update(skip_locked=True)
            )
            processed_claims = processed_result.scalars().all()
            for claim in processed_claims:
                analysis_result = await db.execute(
                    select(RiskAnalysisRecord).where(
                        RiskAnalysisRecord.claim_id == claim.claim_id
                    )
                )
                analysis = analysis_result.scalar_one_or_none()
                if _has_current_analysis(analysis):
                    continue
                # A processed/review_required row is recoverable only when this
                # invariant is false: its current analysis artifact is missing
                # or explicitly stamped with an older/malformed engine version.
                recovered += 1
                claim.status = "pending"
                claim.risk_score = None
                claim.priority_tier = None
                claim.analysis_started_at = None
                claim.analysis_heartbeat_at = None
                claim.analyzed_at = None
                claim.verified_at = None
                claim.human_decision = None
                claim.analysis_attempts = 0
                claim.last_analysis_error = ANALYSIS_RETRYABLE_MESSAGE
                claim.last_analysis_error_code = ANALYSIS_RETRYABLE_CODE
                claim.analysis_generation = str(uuid.uuid4())
            if processed_claims:
                await db.commit()
        return recovered

    async def recover_orphaned_claims(self) -> int:
        """Compatibility wrapper for callers that request periodic recovery."""
        return await self.recover_expired_leases() + await self.recover_invalid_terminal_analysis()

    async def recover_stale_scanning(self) -> int:
        """Compatibility name for periodic lease recovery and focused callers."""
        return await self.recover_orphaned_claims()

    def health_status(self) -> dict:
        task = self._task
        running = task is not None and not task.done() and not self._stopping.is_set()
        return {
            "status": "ok" if running and self._last_error_code is None else "warn",
            "detail": (
                "worker berjalan"
                if running and self._last_error_code is None
                else "worker mengalami gangguan sementara"
                if running
                else "worker tidak aktif"
            ),
            "running": running,
            "active_claim_id": self._active_claim_id,
            "error_code": self._last_error_code,
        }

    def _mark_degraded(self, exc: BaseException) -> None:
        self._last_error_code = failure_for_exception(exc).code

    async def _claim_next(self) -> ClaimRecord | None:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ClaimRecord)
                .where(
                    ClaimRecord.status == "pending",
                    ClaimRecord.analysis_attempts < self.max_attempts,
                )
                .order_by(ClaimRecord.queue_sequence)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            claim = result.scalar_one_or_none()
            if claim is None:
                return None

            claim.status = "scanning"
            claim.analysis_started_at = self.clock()
            claim.analysis_heartbeat_at = claim.analysis_started_at
            claim.analyzed_at = None
            claim.verified_at = None
            claim.human_decision = None
            claim.analysis_attempts = (claim.analysis_attempts or 0) + 1
            claim.last_analysis_error = None
            claim.last_analysis_error_code = None
            claim.risk_score = None
            claim.priority_tier = None
            claim.analysis_generation = str(uuid.uuid4())
            await db.commit()
            return claim

    async def _touch_claim_heartbeat(self, claim_id: str, generation: str) -> None:
        async with self.session_factory() as db:
            await db.execute(
                update(ClaimRecord)
                .where(
                    ClaimRecord.claim_id == claim_id,
                    ClaimRecord.status == "scanning",
                    ClaimRecord.analysis_generation == generation,
                )
                .values(analysis_heartbeat_at=self.clock())
            )
            await db.commit()

    async def _heartbeat_loop(self, claim_id: str, generation: str) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            await self._touch_claim_heartbeat(claim_id, generation)

    async def _stop_heartbeat(self, task: asyncio.Task | None) -> None:
        if task is None or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _existing_analysis(self, claim_id: str) -> RiskAnalysisRecord | None:
        async with self.session_factory() as db:
            result = await db.execute(
                select(RiskAnalysisRecord).where(RiskAnalysisRecord.claim_id == claim_id)
            )
            analysis = result.scalar_one_or_none()
            if analysis is None:
                return None
            return analysis if _has_current_analysis(analysis) else None

    async def _set_claim_state(self, claim_id: str, generation: str, **values) -> None:
        async with self.session_factory() as db:
            await db.execute(
                update(ClaimRecord)
                .where(
                    ClaimRecord.claim_id == claim_id,
                    ClaimRecord.status == "scanning",
                    ClaimRecord.analysis_generation == generation,
                )
                .values(**values)
            )
            await db.commit()

    async def _requeue_active_claim(self, claim_id: str, generation: str | None) -> None:
        async with self.session_factory() as db:
            result = await db.execute(
                select(ClaimRecord)
                .where(
                    ClaimRecord.claim_id == claim_id,
                    ClaimRecord.status == "scanning",
                    ClaimRecord.analysis_generation == generation,
                )
                .with_for_update(skip_locked=True)
            )
            claim = result.scalar_one_or_none()
            if claim is None:
                return
            claim.status = "pending"
            claim.analysis_started_at = None
            claim.analysis_heartbeat_at = None
            claim.analyzed_at = None
            claim.verified_at = None
            claim.human_decision = None
            claim.analysis_attempts = max((claim.analysis_attempts or 1) - 1, 0)
            claim.last_analysis_error = ANALYSIS_RETRYABLE_MESSAGE
            claim.last_analysis_error_code = ANALYSIS_RETRYABLE_CODE
            claim.risk_score = None
            claim.priority_tier = None
            claim.analysis_generation = str(uuid.uuid4())
            await db.commit()

    async def _finish_success(
        self,
        claim_id: str,
        generation: str,
        tier: str | None,
        risk_score: float | None = None,
    ) -> None:
        values = {
            "status": status_for_tier(tier),
            "analyzed_at": self.clock(),
            "analysis_heartbeat_at": None,
            "verified_at": None,
            "last_analysis_error": None,
            "last_analysis_error_code": None,
        }
        if risk_score is not None:
            values.update({"risk_score": risk_score, "priority_tier": tier})
        await self._set_claim_state(claim_id, generation, **values)

    async def _finish_failure(
        self, claim_id: str, generation: str, attempts: int, error_code: str | None = None
    ) -> None:
        terminal = attempts >= self.max_attempts
        failure = safe_failure(error_code)
        await self._set_claim_state(
            claim_id,
            generation,
            status="failed" if terminal else "pending",
            analyzed_at=self.clock() if terminal else None,
            analysis_started_at=None,
            analysis_heartbeat_at=None,
            verified_at=None,
            last_analysis_error=failure.message,
            last_analysis_error_code=failure.code,
        )

    async def _run_orchestrator(self, claim: ClaimInput, generation: str):
        parameters = inspect.signature(self.orchestrator).parameters
        accepts_generation = (
            "analysis_generation" in parameters
            or any(parameter.kind == parameter.VAR_KEYWORD for parameter in parameters.values())
        )
        if accepts_generation:
            return await self.orchestrator(claim, analysis_generation=generation)
        return await self.orchestrator(claim)

    async def process_next(self) -> bool:
        claim_record = await self._claim_next()
        if claim_record is None:
            return False

        claim_id = claim_record.claim_id
        attempts = claim_record.analysis_attempts or 0
        generation = claim_record.analysis_generation
        if generation is None:
            generation = str(uuid.uuid4())
            claim_record.analysis_generation = generation
        self._active_claim_id = claim_id
        self._active_generation = generation
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(claim_id, generation),
            name=f"claim-heartbeat-{claim_id}-{generation}",
        )
        try:
            existing_analysis = await self._existing_analysis(claim_id)
            if existing_analysis is not None:
                await self._finish_success(
                    claim_id,
                    generation,
                    existing_analysis.priority_tier,
                    existing_analysis.total_score,
                )
                return True

            claim = record_to_claim(claim_record)
            assessment = await self._run_orchestrator(claim, generation)
            if assessment.rejected:
                reason = assessment.reject_reason or "claim rejected by orchestrator"
                failure = failure_for_rejection(assessment.error_code, reason)
                if failure.code == VALIDATION_REJECTED_CODE:
                    await self._finish_failure(claim_id, generation, self.max_attempts, failure.code)
                else:
                    await self._finish_failure(claim_id, generation, attempts, failure.code)
            else:
                tier = assessment.score.priority_tier if assessment.score else None
                if tier is None:
                    raise ValueError("orchestrator returned no risk score")
                await self._finish_success(claim_id, generation, tier)
        except asyncio.CancelledError:
            await self._stop_heartbeat(heartbeat_task)
            await self._requeue_active_claim(claim_id, generation)
            raise
        except Exception as exc:
            await self._finish_failure(
                claim_id,
                generation,
                attempts,
                failure_for_exception(exc).code,
            )
        finally:
            await self._stop_heartbeat(heartbeat_task)
            if self._active_claim_id == claim_id:
                self._active_claim_id = None
                self._active_generation = None
        return True
