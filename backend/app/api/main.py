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
from backend.app.data.synthetic_generator import generate_dataset
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
# Demo generation — subscriber queue per-klien + index LanceDB + refresh graph
# ---------------------------------------------------------------------------

_demo_subscribers: list[asyncio.Queue] = []
_demo_status = {"is_running": False}


async def _broadcast(event: dict):
    for q in list(_demo_subscribers):
        await q.put(event)


@app.post("/api/demo/generate")
async def start_demo_generation():
    """Generate klaim sintetis + simpan ke DB + index LanceDB (background)."""
    if _demo_status["is_running"]:
        return {"status": "already_running"}

    _demo_status["is_running"] = True
    asyncio.create_task(_generate_and_save_demo())
    return {"status": "started"}


async def _generate_and_save_demo():
    try:
        await _broadcast({"event": "status", "data": "Menghasilkan data sintetis..."})
        # seed=None + prefix khusus → setiap klik menambah klaim BARU (tanpa bentrok ID seed awal)
        data = generate_dataset(
            num_normal=100,
            num_upcoding=10,
            num_cloning_pairs=5,
            num_repeat_billing=5,
            num_phantom=5,
            num_prolonged_los=5,
            num_inflated=5,
            num_unbundling_groups=2,
            seed=None,
            claim_prefix="DEMO",
        )

        await _broadcast({"event": "status", "data": f"Menyimpan {len(data)} klaim ke database..."})

        async with AsyncSessionLocal() as db:
            existing = await db.execute(select(ClaimRecord.claim_id))
            existing_ids = {r[0] for r in existing.all()}

            added = 0
            for i, claim_dict in enumerate(data):
                if claim_dict["claim_id"] in existing_ids:
                    continue
                db.add(ClaimRecord(
                    claim_id=claim_dict["claim_id"],
                    patient_id=claim_dict["patient_id"],
                    provider_id=claim_dict["provider_id"],
                    doctor_id=claim_dict["doctor_id"],
                    diagnosis_primary=claim_dict["diagnosis_primary"],
                    diagnosis_secondary=",".join(claim_dict["diagnosis_secondary"]),
                    procedure_codes=",".join(claim_dict["procedure_codes"]),
                    severity_level=claim_dict["severity_level"],
                    cost_claimed=claim_dict["cost_claimed"],
                    length_of_stay=claim_dict["length_of_stay"],
                    admission_date=claim_dict.get("admission_date").isoformat() if claim_dict.get("admission_date") else None,
                    discharge_date=claim_dict.get("discharge_date").isoformat() if claim_dict.get("discharge_date") else None,
                    medication_json=json.dumps(claim_dict.get("medication", [])),
                ))
                added += 1
                if i % 25 == 0:
                    await _broadcast({"event": "progress", "data": {"current": i, "total": len(data)}})
                    await db.commit()
            await db.commit()

        await _broadcast({"event": "status", "data": f"{added} klaim baru disimpan. Meng-index ke LanceDB..."})

        # Index semua klaim ke LanceDB agar similarity check mengenali data baru
        try:
            from backend.app.ml.similarity import embed_and_store
            n = embed_and_store(data)
            await _broadcast({"event": "status", "data": f"{n} vektor baru di-index ke LanceDB."})
        except Exception as e:
            await _broadcast({"event": "status", "data": f"Peringatan: LanceDB index gagal: {e}"})

        # Refresh provider graph metrics
        try:
            from backend.app.ml.graph_metrics import refresh_graph_metrics
            stats = await refresh_graph_metrics()
            await _broadcast({"event": "status", "data": f"Graph metrics di-refresh: {stats}"})
        except Exception as e:
            await _broadcast({"event": "status", "data": f"Peringatan: graph metrics gagal: {e}"})

        await _broadcast({"event": "done", "data": f"Generasi selesai — {added} klaim baru."})
    except Exception as e:
        await _broadcast({"event": "error", "data": str(e)})
    finally:
        _demo_status["is_running"] = False
        for q in list(_demo_subscribers):
            await q.put(None)


@app.get("/api/demo/stream")
async def stream_demo_generation(request: Request):
    """Stream progress generasi — tiap klien punya queue sendiri (tanpa race)."""
    queue: asyncio.Queue = asyncio.Queue()
    _demo_subscribers.append(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                event = await queue.get()
                if event is None:
                    break
                yield {"event": event["event"], "data": json.dumps(event["data"], default=str)}
        finally:
            if queue in _demo_subscribers:
                _demo_subscribers.remove(queue)

    return EventSourceResponse(event_generator())


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
