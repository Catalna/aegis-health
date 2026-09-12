import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.future import select
from sqlalchemy import func, and_, case

from backend.app.models.schemas import ClaimInput
from backend.app.agents.orchestrator import process_claim
from backend.app.models.database import (
    init_db, AsyncSessionLocal, ClaimRecord, RiskAnalysisRecord,
)
from backend.app.api.claims import router as claims_router, get_db


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
    yield
    # Shutdown (tidak ada state persisten yang perlu dibersihkan)


app = FastAPI(title="J-ARI Agentic Risk Intelligence API", lifespan=lifespan)

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


@app.post("/api/claims/analyze")
async def analyze_claim(claim: ClaimInput):
    """Trigger analisis penuh klaim. Mengembalikan task_id untuk stream SSE."""
    task_id = str(uuid.uuid4())
    investigation_queues[task_id] = asyncio.Queue()
    asyncio.create_task(_run_and_cleanup(claim, task_id))
    return {"task_id": task_id, "status": "started"}


async def _run_and_cleanup(claim: ClaimInput, task_id: str):
    queue = investigation_queues.get(task_id)
    try:
        await process_claim(claim, sse_queue=queue)
    except Exception as e:
        if queue:
            await queue.put({"event": "error", "data": {"message": str(e)}})
    finally:
        if queue:
            await queue.put(None)  # sentinel end-of-stream


@app.get("/api/stream/{task_id}")
async def stream_investigation(request: Request, task_id: str):
    queue = investigation_queues.get(task_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan atau sudah selesai")

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
                yield {"event": event["event"], "data": json.dumps(event["data"], default=str)}
        finally:
            investigation_queues.pop(task_id, None)

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Health check — status komponen NYATA (dipakai halaman Monitoring)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    components = {}

    # Database
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
        components["database"] = {"status": "ok", "detail": "PostgreSQL terhubung"}
    except Exception as e:
        components["database"] = {"status": "error", "detail": str(e)[:120]}

    # Ollama + models
    try:
        from backend.app.core.llm_client import _ollama_client
        models = await _ollama_client.list_models()
        components["llm_ollama"] = {
            "status": "ok" if models else "warn",
            "detail": f"{len(models)} model tersedia",
            "models": models[:8],
        }
    except Exception as e:
        components["llm_ollama"] = {"status": "error", "detail": str(e)[:120]}

    # Financial model
    try:
        from backend.app.agents.financial_engine import get_financial_model
        get_financial_model()
        components["ml_financial"] = {"status": "ok", "detail": "XGBoost + SHAP termuat"}
    except Exception as e:
        components["ml_financial"] = {"status": "error", "detail": str(e)[:120]}

    # Isolation Forest
    try:
        from backend.app.agents.fraud_agent import load_isolation_forest
        m = load_isolation_forest()
        components["ml_isolation_forest"] = {
            "status": "ok" if m else "error",
            "detail": "termuat" if m else "model tidak ditemukan",
        }
    except Exception as e:
        components["ml_isolation_forest"] = {"status": "error", "detail": str(e)[:120]}

    # LanceDB + embedding model
    try:
        from backend.app.ml.similarity import get_table, model as st_model
        table = get_table()
        count = table.count_rows()
        components["vector_store"] = {
            "status": "ok" if st_model else "error",
            "detail": f"LanceDB {count} vektor" + ("" if st_model else " (embedding model gagal)"),
        }
    except Exception as e:
        components["vector_store"] = {"status": "error", "detail": str(e)[:120]}

    # Graph metrics
    try:
        from backend.app.ml.graph_metrics import graph_stats
        stats = graph_stats()
        components["graph_metrics"] = {
            "status": "ok" if stats.get("providers_cached", 0) > 0 else "warn",
            "detail": f"{stats.get('providers_cached', 0)} provider terindeks",
        }
    except Exception as e:
        components["graph_metrics"] = {"status": "error", "detail": str(e)[:120]}

    overall = "ok" if all(c["status"] == "ok" for c in components.values()) else (
        "degraded" if any(c["status"] == "error" for c in components.values()) else "ok"
    )
    return {"status": overall, "components": components}


# ---------------------------------------------------------------------------
# ML evaluation — angka RIIL dari hasil training (bukan simulasi)
# ---------------------------------------------------------------------------

_EVAL_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models_trained", "evaluation_results.json"))

@app.get("/api/ml/eval")
async def ml_evaluation():
    if not os.path.exists(_EVAL_PATH):
        raise HTTPException(status_code=404, detail="Hasil evaluasi belum tersedia. Jalankan scripts/train_all.py.")
    with open(_EVAL_PATH, "r") as f:
        data = json.load(f)
    data["generated_from"] = "backend/models_trained/evaluation_results.json"
    return data


# ---------------------------------------------------------------------------
# Analytics — agregasi via SQL (tanpa full-scan JSON di Python)
# ---------------------------------------------------------------------------

@app.get("/api/analytics/dashboard")
async def get_dashboard_stats(db: AsyncSessionLocal = Depends(get_db)):
    total_claims = await db.scalar(select(func.count(ClaimRecord.claim_id)))
    processed_claims = await db.scalar(select(func.count(RiskAnalysisRecord.claim_id)))
    high_risk = await db.scalar(
        select(func.count(RiskAnalysisRecord.claim_id)).where(RiskAnalysisRecord.priority_tier == "high")
    )
    medium_risk = await db.scalar(
        select(func.count(RiskAnalysisRecord.claim_id)).where(RiskAnalysisRecord.priority_tier == "medium")
    )
    low_risk = await db.scalar(
        select(func.count(RiskAnalysisRecord.claim_id)).where(RiskAnalysisRecord.priority_tier == "low")
    )
    verified_claims = await db.scalar(
        select(func.count(ClaimRecord.claim_id)).where(ClaimRecord.status == "verified")
    )
    pending_claims = await db.scalar(
        select(func.count(ClaimRecord.claim_id)).where(ClaimRecord.status == "pending")
    )

    # Potensi penghematan via SQL: SUM(GREATEST(0, actual_cost - predicted_cost_upper))
    from sqlalchemy import literal_column
    savings_expr = func.coalesce(func.sum(
        func.greatest(literal_column("0"), RiskAnalysisRecord.actual_cost - RiskAnalysisRecord.predicted_cost_upper)
    ), 0.0)
    potential_savings = await db.scalar(
        select(savings_expr).where(RiskAnalysisRecord.priority_tier.in_(["high", "medium"]))
    )

    return {
        "total_claims": total_claims or 0,
        "processed_claims": processed_claims or 0,
        "high_risk_claims": high_risk or 0,
        "medium_risk_claims": medium_risk or 0,
        "low_risk_claims": low_risk or 0,
        "verified_claims": verified_claims or 0,
        "pending_claims": pending_claims or 0,
        "potential_savings": round(float(potential_savings or 0)),
    }
