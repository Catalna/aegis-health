import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.future import select
from sqlalchemy import func, and_, case, update, desc, asc, nulls_last

from backend.app.models.schemas import ClaimInput, RiskAssessment
from backend.app.agents.orchestrator import process_claim, ANALYSIS_VERSION
from backend.app.core.versions import is_current_analysis
from backend.app.core.errors import (
    ANALYSIS_FAILURE_MESSAGE,
    ANALYSIS_RETRYABLE_CODE,
    DEPENDENCY_UNAVAILABLE_CODE,
    DEPENDENCY_UNAVAILABLE_MESSAGE,
    VALIDATION_REJECTED_CODE,
    VALIDATION_REJECTED_MESSAGE,
    failure_for_exception,
    failure_for_rejection,
    safe_failure,
)
from backend.app.core.public_analysis import public_analysis_projection
from backend.app.models.database import (
    init_db, AsyncSessionLocal, ClaimRecord, RiskAnalysisRecord,
)
from backend.app.api.claims import router as claims_router, get_db
from backend.app.services.claim_queue import (
    ClaimQueueWorker,
    DEFAULT_MAX_ATTEMPTS,
    record_to_claim,
    status_for_tier,
)


# ---------------------------------------------------------------------------
# Lifespan (pengganti on_event deprecated)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    try:
        from backend.app.agents.financial_engine import get_financial_model
        get_financial_model()
        print("[startup] Financial model loaded.")
    except Exception as e:
        print(f"[startup] Warning: financial model belum termuat: {e}")
    try:
        from backend.app.agents.fraud_agent import load_isolation_forest
        load_isolation_forest()
        print("[startup] Isolation Forest loaded.")
    except Exception as e:
        print(f"[startup] Warning: isolation forest belum termuat: {e}")
    try:
        from backend.app.ml.graph_metrics import refresh_graph_metrics
        stats = await refresh_graph_metrics()
        print(f"[startup] Graph metrics: {stats}")
    except Exception as e:
        print(f"[startup] Warning: graph metrics gagal: {e}")
    try:
        # Backfill index LanceDB dari DB — idempotent (klaim yang sudah ter-index
        # dilewati). Menyembuhkan tabel vektor yang kosong/versi lama secara otomatis.
        from backend.app.ml.similarity import get_table, embed_and_store
        table = get_table()
        vector_count = table.count_rows()
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(ClaimRecord))).scalars().all()

        def _record_to_claim(r) -> dict:
            try:
                meds = json.loads(r.medication_json or "[]")
            except json.JSONDecodeError:
                meds = []
            return {
                "claim_id": r.claim_id,
                "patient_id": r.patient_id or "",
                "provider_id": r.provider_id or "",
                "doctor_id": r.doctor_id or "",
                "diagnosis_primary": r.diagnosis_primary or "",
                "diagnosis_secondary": [s.strip() for s in (r.diagnosis_secondary or "").split(",") if s.strip()],
                "procedure_codes": [p.strip() for p in (r.procedure_codes or "").split(",") if p.strip()],
                "medication": meds,
                "cost_claimed": float(r.cost_claimed or 0),
                "admission_date": str(r.admission_date or ""),
            }

        claims = [_record_to_claim(r) for r in rows]
        indexed = await asyncio.to_thread(embed_and_store, claims)
        print(f"[startup] LanceDB: {vector_count} vektor existing, {indexed} klaim di-index dari DB.")
    except Exception as e:
        print(f"[startup] Warning: backfill LanceDB gagal: {e}")
    queue_worker = ClaimQueueWorker()
    app.state.claim_queue_worker = queue_worker
    await queue_worker.start()
    print("[startup] Claim queue worker started.")
    yield
    await queue_worker.stop()
    app.state.claim_queue_worker = None
    print("[shutdown] Claim queue worker stopped.")


app = FastAPI(title="AEGIS-Health API", lifespan=lifespan)
logger = logging.getLogger(__name__)

# CORS — origin eksplisit dari env (bukan wildcard + credentials)
_allowed = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(claims_router)


# ---------------------------------------------------------------------------
# Investigation SSE — task queue per-analisis (task_id UUID, bukan claim_id
# agar dua klien yang menganalisis klaim sama tidak saling mencuri event)
# ---------------------------------------------------------------------------

investigation_queues: dict[str, asyncio.Queue] = {}
manual_tasks_by_claim: dict[str, str] = {}
manual_tasks: dict[str, asyncio.Task] = {}
manual_consumers: set[str] = set()
manual_completed: set[str] = set()
manual_orphan_handles: dict[str, asyncio.TimerHandle] = {}
manual_grace_handles: dict[str, asyncio.TimerHandle] = {}
MANUAL_HEARTBEAT_INTERVAL = 30.0
MANUAL_QUEUE_MAXSIZE = 64
MANUAL_SSE_ATTACH_TIMEOUT = 5.0
MANUAL_SSE_GRACE_PERIOD = 5.0


def _has_current_analysis(analysis: RiskAnalysisRecord | None) -> bool:
    return analysis is not None and is_current_analysis(
        analysis.analysis_version, analysis.evidence_json
    )


def _safe_claim_payload(claim: ClaimRecord) -> dict:
    """Serialize claims without trusting legacy error text already in storage."""
    payload = {
        key: value
        for key, value in vars(claim).items()
        if not key.startswith("_")
    }
    if claim.last_analysis_error:
        failure = safe_failure(claim.last_analysis_error_code)
        payload["last_analysis_error"] = failure.message
        payload["last_analysis_error_code"] = failure.code
    else:
        payload["last_analysis_error"] = None
        payload["last_analysis_error_code"] = None
    return payload


async def _finalize_manual_claim(
    claim_id: str, generation: str | None, assessment
) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ClaimRecord)
            .where(
                ClaimRecord.claim_id == claim_id,
                ClaimRecord.status == "scanning",
                ClaimRecord.analysis_generation == generation,
            )
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return

        now = datetime.now(timezone.utc)
        if assessment.rejected:
            record.status = "failed"
            record.analysis_started_at = None
            record.analysis_heartbeat_at = None
            record.verified_at = None
            record.human_decision = None
            record.analyzed_at = now
            failure = failure_for_rejection(assessment.error_code, assessment.reject_reason)
            record.last_analysis_error = failure.message
            record.last_analysis_error_code = failure.code
        elif assessment.score is None:
            record.status = "failed"
            record.analysis_started_at = None
            record.analysis_heartbeat_at = None
            record.verified_at = None
            record.human_decision = None
            record.analyzed_at = now
            record.last_analysis_error = ANALYSIS_FAILURE_MESSAGE
            record.last_analysis_error_code = ANALYSIS_RETRYABLE_CODE
        else:
            record.status = status_for_tier(assessment.score.priority_tier)
            record.analysis_heartbeat_at = None
            record.verified_at = None
            record.human_decision = None
            record.risk_score = assessment.score.total_score
            record.priority_tier = assessment.score.priority_tier
            record.analyzed_at = now
            record.last_analysis_error = None
            record.last_analysis_error_code = None
        await db.commit()


async def _requeue_manual_claim(claim_id: str, generation: str | None) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ClaimRecord)
            .where(
                ClaimRecord.claim_id == claim_id,
                ClaimRecord.status == "scanning",
                ClaimRecord.analysis_generation == generation,
            )
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return
        next_attempts = max((record.analysis_attempts or 1) - 1, 0)
        exhausted = next_attempts >= DEFAULT_MAX_ATTEMPTS
        record.status = "failed" if exhausted else "pending"
        record.analysis_started_at = None
        record.analysis_heartbeat_at = None
        record.analyzed_at = datetime.now(timezone.utc) if exhausted else None
        record.verified_at = None
        record.human_decision = None
        record.analysis_attempts = next_attempts
        record.last_analysis_error = ANALYSIS_FAILURE_MESSAGE
        record.last_analysis_error_code = ANALYSIS_RETRYABLE_CODE
        record.risk_score = None
        record.priority_tier = None
        record.analysis_generation = str(uuid.uuid4())
        await db.commit()


async def _manual_heartbeat_loop(claim_id: str, generation: str) -> None:
    while True:
        await asyncio.sleep(MANUAL_HEARTBEAT_INTERVAL)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(ClaimRecord)
                .where(
                    ClaimRecord.claim_id == claim_id,
                    ClaimRecord.status == "scanning",
                    ClaimRecord.analysis_generation == generation,
                )
                .values(analysis_heartbeat_at=datetime.now(timezone.utc))
            )
            await db.commit()


async def _stop_manual_heartbeat(task: asyncio.Task | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _offer_manual_event(queue: asyncio.Queue | None, event) -> None:
    """Keep manual streams bounded and preserve terminal events when full."""
    if queue is None:
        return
    try:
        queue.put_nowait(event)
        return
    except asyncio.QueueFull:
        pass
    if event is None or event.get("event") in {"error", "rejected", "done"}:
        with suppress(asyncio.QueueEmpty):
            queue.get_nowait()
        with suppress(asyncio.QueueFull):
            queue.put_nowait(event)


def _cleanup_manual_state(task_id: str) -> None:
    handle = manual_orphan_handles.pop(task_id, None)
    if handle is not None:
        handle.cancel()
    handle = manual_grace_handles.pop(task_id, None)
    if handle is not None:
        handle.cancel()
    investigation_queues.pop(task_id, None)
    manual_tasks.pop(task_id, None)
    manual_consumers.discard(task_id)
    manual_completed.discard(task_id)
    for claim_id, mapped_task_id in list(manual_tasks_by_claim.items()):
        if mapped_task_id == task_id:
            manual_tasks_by_claim.pop(claim_id, None)


def _schedule_manual_grace_cleanup(task_id: str) -> None:
    handle = manual_grace_handles.pop(task_id, None)
    if handle is not None:
        handle.cancel()
    manual_grace_handles[task_id] = asyncio.get_running_loop().call_later(
        MANUAL_SSE_GRACE_PERIOD,
        _cleanup_manual_state,
        task_id,
    )


def _cancel_unconsumed_manual_task(task_id: str) -> None:
    if task_id in manual_consumers:
        return
    task = manual_tasks.get(task_id)
    if task is None or task.done():
        _cleanup_manual_state(task_id)
        return
    task.cancel()


async def _cancel_manual_task(task_id: str) -> None:
    task = manual_tasks.get(task_id)
    if task is None:
        _cleanup_manual_state(task_id)
        return
    if not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    _cleanup_manual_state(task_id)


@app.post("/api/claims/analyze")
async def analyze_claim(
    claim: ClaimInput,
    db=Depends(get_db),
    retry: bool = Query(False, description="Retry an explicitly failed claim"),
):
    """Start one manual scan, or return the existing scan/analysis state."""
    claim_record = await db.scalar(
        select(ClaimRecord).where(ClaimRecord.claim_id == claim.claim_id).with_for_update()
    )
    existing_analysis = None
    if claim_record is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    existing_analysis = await db.scalar(
        select(RiskAnalysisRecord).where(
            RiskAnalysisRecord.claim_id == claim.claim_id
        )
    )
    if _has_current_analysis(existing_analysis):
        if claim_record.status != "verified":
            claim_record.status = status_for_tier(existing_analysis.priority_tier)
            claim_record.risk_score = existing_analysis.total_score
            claim_record.priority_tier = existing_analysis.priority_tier
            claim_record.analyzed_at = claim_record.analyzed_at or datetime.now(timezone.utc)
            claim_record.last_analysis_error = None
            claim_record.last_analysis_error_code = None
            await db.commit()
        return {
            "status": "already_processed",
            "claim_id": claim.claim_id,
            "analysis_url": f"/api/claims/{claim.claim_id}/analysis",
            "message": "Klaim sudah memiliki analisis terbaru.",
        }
    if claim_record.status == "scanning":
        return {
            "status": "already_running",
            "claim_id": claim.claim_id,
            "task_id": None,
            "message": "Klaim sedang diproses oleh antrean analisis.",
        }
    if claim_record.status == "pending":
        return {
            "status": "queued",
            "claim_id": claim.claim_id,
            "task_id": None,
            "message": "Klaim berada dalam antrean analisis FIFO.",
        }
    if claim_record.status == "failed" and not retry:
        safe_error = _safe_claim_payload(claim_record)
        return {
            "status": "failed",
            "claim_id": claim.claim_id,
            "retry_available": True,
            "message": "Analisis sebelumnya gagal. Kirim retry=true untuk mencoba lagi.",
            "last_analysis_error": safe_error["last_analysis_error"],
            "last_analysis_error_code": safe_error["last_analysis_error_code"],
        }
    if claim_record.status in {"processed", "review_required", "verified"} and not retry:
        return {
            "status": "stale",
            "claim_id": claim.claim_id,
            "retry_available": True,
            "message": "Hasil analisis klaim sudah usang atau belum tersedia. Kirim retry=true untuk mencoba lagi.",
        }

    claim_record.status = "scanning"
    claim_record.analysis_started_at = datetime.now(timezone.utc)
    claim_record.analysis_heartbeat_at = claim_record.analysis_started_at
    claim_record.analyzed_at = None
    claim_record.verified_at = None
    claim_record.human_decision = None
    claim_record.analysis_attempts = (claim_record.analysis_attempts or 0) + 1
    claim_record.last_analysis_error = None
    claim_record.last_analysis_error_code = None
    claim_record.risk_score = None
    claim_record.priority_tier = None
    claim_record.analysis_generation = str(uuid.uuid4())
    persisted_claim = record_to_claim(claim_record)
    generation = claim_record.analysis_generation
    await db.commit()

    task_id = str(uuid.uuid4())
    investigation_queues[task_id] = asyncio.Queue(maxsize=MANUAL_QUEUE_MAXSIZE)
    manual_tasks_by_claim[claim.claim_id] = task_id
    task = asyncio.create_task(
        _run_and_cleanup(persisted_claim, task_id, claim.claim_id, generation)
    )
    manual_tasks[task_id] = task
    loop = asyncio.get_running_loop()
    manual_orphan_handles[task_id] = loop.call_later(
        MANUAL_SSE_ATTACH_TIMEOUT,
        _cancel_unconsumed_manual_task,
        task_id,
    )
    return {"task_id": task_id, "status": "started"}


async def _run_and_cleanup(
    claim: ClaimInput,
    task_id: str,
    claim_id: str | None = None,
    generation: str | None = None,
):
    queue = investigation_queues.get(task_id)
    claim_id = claim_id or claim.claim_id
    heartbeat_task = (
        asyncio.create_task(
            _manual_heartbeat_loop(claim_id, generation),
            name=f"manual-claim-heartbeat-{claim_id}-{generation}",
        )
        if generation
        else None
    )
    terminal_outcome = {}
    assessment = None
    try:
        assessment = await process_claim(
            claim,
            sse_queue=queue,
            analysis_generation=generation,
            terminal_outcome=terminal_outcome,
        )
        await _finalize_manual_claim(claim_id, generation, assessment)
    except asyncio.CancelledError:
        await _stop_manual_heartbeat(heartbeat_task)
        terminal_assessment = assessment or terminal_outcome.get("assessment")
        if terminal_assessment is not None:
            await _finalize_manual_claim(claim_id, generation, terminal_assessment)
        else:
            await _requeue_manual_claim(claim_id, generation)
            _offer_manual_event(queue, {
                "event": "error",
                "data": {"message": "Manual scan cancelled and requeued."},
            })
        raise
    except Exception as e:
        logger.exception("Manual analysis failed for claim_id=%s", claim_id)
        failure = failure_for_exception(e)
        try:
            await _finalize_manual_claim(
                claim_id,
                generation,
                RiskAssessment.create_rejected(claim_id, failure.message, failure.code),
            )
        except Exception:
            pass
        _offer_manual_event(queue, {"event": "error", "data": {"code": failure.code, "message": failure.message}})
    finally:
        await _stop_manual_heartbeat(heartbeat_task)
        _offer_manual_event(queue, None)  # sentinel end-of-stream
        manual_completed.add(task_id)
        if task_id not in manual_consumers:
            _schedule_manual_grace_cleanup(task_id)


@app.get("/api/stream/{task_id}")
async def stream_investigation(request: Request, task_id: str):
    queue = investigation_queues.get(task_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan atau sudah selesai")
    manual_consumers.add(task_id)
    handle = manual_orphan_handles.pop(task_id, None)
    if handle is not None:
        handle.cancel()
    handle = manual_grace_handles.pop(task_id, None)
    if handle is not None:
        handle.cancel()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=600.0)
                except asyncio.TimeoutError:
                    break
                if event is None:
                    yield {"event": "done", "data": "Investigation complete"}
                    break
                yield {
                    "event": event["event"],
                    "data": json.dumps(public_analysis_projection(event["data"]), default=str),
                }
        finally:
            if task_id not in manual_completed:
                await _cancel_manual_task(task_id)
            _cleanup_manual_state(task_id)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Health check — status komponen NYATA (dipakai halaman Monitoring)
# ---------------------------------------------------------------------------

def overall_health_status(components: dict) -> str:
    return "ok" if all(component.get("status") == "ok" for component in components.values()) else "degraded"


@app.get("/api/health")
async def health():
    components = {}

    queue_worker = getattr(app.state, "claim_queue_worker", None)
    if queue_worker is not None:
        worker_health = queue_worker.health_status()
        components["queue_worker"] = {
            "status": worker_health.get("status"),
            "detail": "Antrean pemeriksaan aktif" if worker_health.get("running") else "Antrean pemeriksaan belum dimulai",
            "running": bool(worker_health.get("running")),
        }
    else:
        components["queue_worker"] = {
            "status": "warn",
            "detail": "Antrean pemeriksaan belum dimulai",
            "running": False,
        }

    # Database
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
        components["database"] = {"status": "ok", "detail": "Penyimpanan data klaim tersedia"}
    except Exception:
        components["database"] = {
            "status": "error",
            "error_code": DEPENDENCY_UNAVAILABLE_CODE,
            "detail": DEPENDENCY_UNAVAILABLE_MESSAGE,
        }

    # Ollama + models
    try:
        from backend.app.core.llm_client import _ollama_client
        models = await _ollama_client.list_models()
        components["llm_ollama"] = {
            "status": "ok" if models else "warn",
            "detail": "Pemeriksaan tambahan tersedia" if models else "Pemeriksaan tambahan belum tersedia",
        }
    except Exception:
        components["llm_ollama"] = {
            "status": "error",
            "error_code": DEPENDENCY_UNAVAILABLE_CODE,
            "detail": DEPENDENCY_UNAVAILABLE_MESSAGE,
        }

    # Financial model
    try:
        from backend.app.agents.financial_engine import get_financial_model
        get_financial_model()
        components["ml_financial"] = {"status": "ok", "detail": "Pemeriksaan biaya tersedia"}
    except Exception:
        components["ml_financial"] = {
            "status": "error",
            "error_code": DEPENDENCY_UNAVAILABLE_CODE,
            "detail": DEPENDENCY_UNAVAILABLE_MESSAGE,
        }

    # Isolation Forest
    try:
        from backend.app.agents.fraud_agent import load_isolation_forest
        m = load_isolation_forest()
        components["ml_isolation_forest"] = {
            "status": "ok" if m else "error",
            "detail": "Pemeriksaan pola tersedia" if m else "Pemeriksaan pola belum tersedia",
        }
    except Exception:
        components["ml_isolation_forest"] = {
            "status": "error",
            "error_code": DEPENDENCY_UNAVAILABLE_CODE,
            "detail": DEPENDENCY_UNAVAILABLE_MESSAGE,
        }

    # LanceDB + embedding model
    try:
        from backend.app.ml.similarity import get_embedding_model, get_table
        st_model = get_embedding_model()
        table = get_table()
        table.count_rows()
        components["vector_store"] = {
            "status": "ok" if st_model else "error",
            "detail": "Data pembanding tersedia" if st_model else "Data pembanding belum tersedia",
        }
    except Exception:
        components["vector_store"] = {
            "status": "error",
            "error_code": DEPENDENCY_UNAVAILABLE_CODE,
            "detail": DEPENDENCY_UNAVAILABLE_MESSAGE,
        }

    # Graph metrics
    try:
        from backend.app.ml.graph_metrics import graph_stats
        stats = graph_stats()
        components["graph_metrics"] = {
            "status": "ok" if stats.get("providers_cached", 0) > 0 else "warn",
            "detail": "Data fasilitas kesehatan tersedia" if stats.get("providers_cached", 0) > 0 else "Data fasilitas kesehatan belum tersedia",
        }
    except Exception:
        components["graph_metrics"] = {
            "status": "error",
            "error_code": DEPENDENCY_UNAVAILABLE_CODE,
            "detail": DEPENDENCY_UNAVAILABLE_MESSAGE,
        }

    overall = overall_health_status(components)
    return {"status": overall, "components": components}


# ---------------------------------------------------------------------------
# ML evaluation — angka RIIL dari hasil training (bukan simulasi)
# ---------------------------------------------------------------------------

_EVAL_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models_trained", "evaluation_results.json"))
_P1_EVAL_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models_trained", "p1_evaluation_results.json"))

@app.get("/api/ml/eval")
async def ml_evaluation():
    if not os.path.exists(_EVAL_PATH):
        raise HTTPException(status_code=404, detail="Hasil evaluasi belum tersedia. Jalankan scripts/train_all.py.")
    with open(_EVAL_PATH, "r") as f:
        data = json.load(f)
    data["generated_from"] = "backend/models_trained/evaluation_results.json"
    return data


@app.get("/api/ml/eval/p1")
async def ml_p1_evaluation():
    if not os.path.exists(_P1_EVAL_PATH):
        raise HTTPException(
            status_code=404,
            detail="Artifact evaluasi P1 belum tersedia. Jalankan scripts/evaluate_p1.py.",
        )
    with open(_P1_EVAL_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["generated_from"] = "backend/models_trained/p1_evaluation_results.json"
    return data


# ---------------------------------------------------------------------------
# Analytics — agregasi via SQL (tanpa full-scan JSON di Python)
# ---------------------------------------------------------------------------

CURRENT_ANALYSIS_CLAIM_STATUSES = ("processed", "review_required", "verified")


def current_analysis_evidence_conditions():
    parsed = func.parse_jsonb_or_null(RiskAnalysisRecord.evidence_json)
    version_node = func.jsonb_extract_path(parsed, "analysis_version")
    return [
        func.jsonb_typeof(version_node) == "number",
        func.jsonb_extract_path_text(parsed, "analysis_version") == str(ANALYSIS_VERSION),
    ]


def current_analysis_statement(expression, *conditions):
    return (
        select(expression)
        .join(ClaimRecord, ClaimRecord.claim_id == RiskAnalysisRecord.claim_id)
        .where(
            ClaimRecord.status.in_(CURRENT_ANALYSIS_CLAIM_STATUSES),
            RiskAnalysisRecord.analysis_version == ANALYSIS_VERSION,
            *current_analysis_evidence_conditions(),
            *conditions,
        )
    )


@app.get("/api/analytics/dashboard")
async def get_dashboard_stats(db: AsyncSessionLocal = Depends(get_db)):
    total_claims = await db.scalar(select(func.count(ClaimRecord.claim_id)))
    processed_claims = await db.scalar(
        current_analysis_statement(func.count(RiskAnalysisRecord.claim_id))
    )
    high_risk = await db.scalar(
        current_analysis_statement(
            func.count(RiskAnalysisRecord.claim_id),
            RiskAnalysisRecord.priority_tier == "high",
        )
    )
    medium_risk = await db.scalar(
        current_analysis_statement(
            func.count(RiskAnalysisRecord.claim_id),
            RiskAnalysisRecord.priority_tier == "medium",
        )
    )
    low_risk = await db.scalar(
        current_analysis_statement(
            func.count(RiskAnalysisRecord.claim_id),
            RiskAnalysisRecord.priority_tier == "low",
        )
    )
    verified_claims = await db.scalar(
        select(func.count(ClaimRecord.claim_id)).where(ClaimRecord.status == "verified")
    )
    pending_claims = await db.scalar(
        select(func.count(ClaimRecord.claim_id)).where(ClaimRecord.status == "pending")
    )
    scanning_claims = await db.scalar(
        select(func.count(ClaimRecord.claim_id)).where(ClaimRecord.status == "scanning")
    )
    review_required_claims = await db.scalar(
        select(func.count(ClaimRecord.claim_id)).where(ClaimRecord.status == "review_required")
    )
    processed_status_claims = await db.scalar(
        select(func.count(ClaimRecord.claim_id)).where(ClaimRecord.status == "processed")
    )
    failed_claims = await db.scalar(
        select(func.count(ClaimRecord.claim_id)).where(ClaimRecord.status == "failed")
    )

    # Potential financial exposure via SQL: SUM(GREATEST(0, actual_cost - predicted_cost_upper))
    from sqlalchemy import literal_column
    exposure_expr = func.coalesce(func.sum(
        func.greatest(literal_column("0"), RiskAnalysisRecord.actual_cost - RiskAnalysisRecord.predicted_cost_upper)
    ), 0.0)
    potential_financial_exposure = await db.scalar(
        current_analysis_statement(
            exposure_expr,
            RiskAnalysisRecord.priority_tier.in_(["high", "medium"]),
        )
    )

    return {
        "total_claims": total_claims or 0,
        "processed_claims": processed_claims or 0,
        "analyzed_claims": processed_claims or 0,
        "high_risk_claims": high_risk or 0,
        "medium_risk_claims": medium_risk or 0,
        "low_risk_claims": low_risk or 0,
        "verified_claims": verified_claims or 0,
        "pending_claims": pending_claims or 0,
        "scanning_claims": scanning_claims or 0,
        "review_required_claims": review_required_claims or 0,
        "processed_status_claims": processed_status_claims or 0,
        "failed_claims": failed_claims or 0,
        "potential_financial_exposure": round(float(potential_financial_exposure or 0)),
        # Deprecated additive compatibility key for older dashboard clients.
        "potential_savings": round(float(potential_financial_exposure or 0)),
    }


@app.get("/api/analytics/trend")
async def get_analytics_trend(db: AsyncSessionLocal = Depends(get_db)):
    """Agregasi harian untuk tren 7 hari, delta 'vs kemarin', klaim terbaru, dan preview prioritas."""
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    start = today - timedelta(days=6)
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    yesterday = today - timedelta(days=1)

    # Jumlah klaim per tanggal penerimaan (+ berapa yang masih pending)
    received_rows = await db.execute(
        select(
            func.date(ClaimRecord.received_at).label("day"),
            func.count().label("total"),
            func.sum(case((ClaimRecord.status == "pending", 1), else_=0)).label("pending"),
        )
        .where(ClaimRecord.received_at >= start_dt)
        .group_by(func.date(ClaimRecord.received_at))
    )
    received_map = {
        row.day: {"total": int(row.total or 0), "pending": int(row.pending or 0)}
        for row in received_rows
    }

    # Berisiko tinggi per tanggal penerimaan (dari hasil analisis berjalan)
    high_rows = await db.execute(
        select(func.date(ClaimRecord.received_at).label("day"), func.count().label("high"))
        .select_from(ClaimRecord)
        .join(RiskAnalysisRecord, RiskAnalysisRecord.claim_id == ClaimRecord.claim_id)
        .where(ClaimRecord.received_at >= start_dt, RiskAnalysisRecord.priority_tier == "high")
        .group_by(func.date(ClaimRecord.received_at))
    )
    high_map = {row.day: int(row.high or 0) for row in high_rows}

    # Selesai dianalisis per tanggal analisis
    done_rows = await db.execute(
        select(func.date(ClaimRecord.analyzed_at).label("day"), func.count().label("done"))
        .where(
            ClaimRecord.analyzed_at >= start_dt,
            ClaimRecord.status.in_(CURRENT_ANALYSIS_CLAIM_STATUSES),
        )
        .group_by(func.date(ClaimRecord.analyzed_at))
    )
    done_map = {row.day: int(row.done or 0) for row in done_rows}

    days_out = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        counts = received_map.get(day, {"total": 0, "pending": 0})
        days_out.append({
            "date": day.isoformat(),
            "total": counts["total"],
            "pending": counts["pending"],
            "high_risk": high_map.get(day, 0),
            "done": done_map.get(day, 0),
        })

    # Snapshot kemarin (basis delta badge 'vs. kemarin')
    y_counts = received_map.get(yesterday, {"total": 0, "pending": 0})
    y_high = high_map.get(yesterday, 0)
    y_verified = await db.scalar(
        select(func.count())
        .select_from(ClaimRecord)
        .where(ClaimRecord.status == "verified", func.date(ClaimRecord.verified_at) == yesterday)
    ) or 0
    t_verified = await db.scalar(
        select(func.count())
        .select_from(ClaimRecord)
        .where(ClaimRecord.status == "verified", func.date(ClaimRecord.verified_at) == today)
    ) or 0

    # Preview klaim prioritas tertinggi untuk banner 3-zona (ID, skor, alasan)
    priority_row = (
        await db.execute(
            select(ClaimRecord, RiskAnalysisRecord.evidence_json)
            .join(RiskAnalysisRecord, RiskAnalysisRecord.claim_id == ClaimRecord.claim_id)
            .where(ClaimRecord.priority_tier == "high")
            .order_by(desc(ClaimRecord.risk_score), asc(ClaimRecord.claim_id))
            .limit(1)
        )
    ).first()
    priority_claim = None
    if priority_row is not None:
        claim, evidence_raw = priority_row
        reason = None
        try:
            evidence = json.loads(evidence_raw or "{}")
            reasons = (evidence.get("explanation") or {}).get("ranked_reasons") or []
            if not reasons:
                risk_evidence = (evidence.get("risk") or {}).get("evidence") or []
                if risk_evidence:
                    reasons = [risk_evidence[0].get("explanation")]
            reason = next((str(r).rstrip(".") for r in reasons if r), None)
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            reason = None
        priority_claim = {
            "claim_id": claim.claim_id,
            "risk_score": round(claim.risk_score) if claim.risk_score is not None else None,
            "reason": reason,
        }

    # 5 klaim terakhir yang masuk untuk tabel "Klaim Terbaru"
    recent_rows = await db.execute(
        select(ClaimRecord).order_by(desc(ClaimRecord.received_at)).limit(5)
    )
    recent_claims = [
        {
            "claim_id": c.claim_id,
            "provider_id": c.provider_id,
            "diagnosis_primary": c.diagnosis_primary,
            "cost_claimed": c.cost_claimed,
            "risk_score": round(c.risk_score) if c.risk_score is not None else None,
            "priority_tier": c.priority_tier,
            "status": c.status,
        }
        for c in recent_rows.scalars()
    ]

    return {
        "days": days_out,
        "yesterday": {
            "date": yesterday.isoformat(),
            "total": y_counts["total"],
            "pending": y_counts["pending"],
            "high_risk": y_high,
            "verified": int(y_verified),
        },
        "today_verified": int(t_verified),
        "priority_claim": priority_claim,
        "recent_claims": recent_claims,
    }
