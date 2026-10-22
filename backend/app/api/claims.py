import asyncio
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.future import select
from sqlalchemy import func, delete, or_, asc, desc, case, nulls_last

from backend.app.models.schemas import ClaimInput, HumanDecision
from backend.app.models.database import (
    get_db, HumanDecisionRecord, ClaimRecord, RiskAnalysisRecord,
)
from backend.app.core.versions import ANALYSIS_VERSION, is_current_analysis
from backend.app.core.errors import safe_failure
from backend.app.core.public_analysis import public_analysis_projection
from backend.app.services.claim_queue import enqueue_claim

router = APIRouter(prefix="/api/claims", tags=["claims"])


ClaimStatus = Literal[
    "pending", "scanning", "processed", "review_required", "failed", "verified"
]
ClaimTier = Literal["high", "medium", "low"]
ClaimSort = Literal[
    "priority", "queue", "risk_desc", "risk_asc", "cost_desc", "cost_asc", "id"
]

_PUBLIC_CLAIM_FIELDS = (
    "claim_id",
    "patient_id",
    "provider_id",
    "doctor_id",
    "diagnosis_primary",
    "diagnosis_secondary",
    "procedure_codes",
    "severity_level",
    "cost_claimed",
    "length_of_stay",
    "cbg_group_claimed",
    "admission_date",
    "discharge_date",
    "medication_json",
    "referral_json",
    "status",
    "risk_score",
    "priority_tier",
    "human_decision",
    "received_at",
    "queue_sequence",
    "analysis_started_at",
    "analysis_heartbeat_at",
    "analyzed_at",
    "verified_at",
    "analysis_attempts",
    "last_analysis_error",
    "last_analysis_error_code",
)


def _safe_claim_payload(claim: ClaimRecord) -> dict:
    payload = {key: getattr(claim, key, None) for key in _PUBLIC_CLAIM_FIELDS}
    if claim.last_analysis_error:
        failure = safe_failure(claim.last_analysis_error_code)
        payload["last_analysis_error"] = failure.message
        payload["last_analysis_error_code"] = failure.code
    else:
        payload["last_analysis_error"] = None
        payload["last_analysis_error_code"] = None
    return payload


def claim_received_filters(
    received_from: date | None = None,
    received_to: date | None = None,
):
    filters = []
    if received_from:
        filters.append(
            ClaimRecord.received_at
            >= datetime.combine(received_from, time.min, tzinfo=timezone.utc)
        )
    if received_to:
        end = datetime.combine(received_to, time.min, tzinfo=timezone.utc) + timedelta(days=1)
        filters.append(ClaimRecord.received_at < end)
    return filters


def claim_admission_filters(
    admission_from: date | None = None,
    admission_to: date | None = None,
):
    filters = []
    if admission_from:
        filters.append(ClaimRecord.admission_date >= admission_from.isoformat())
    if admission_to:
        filters.append(ClaimRecord.admission_date <= admission_to.isoformat())
    return filters


def claim_priority_ordering():
    tier_order = case(
        (ClaimRecord.priority_tier == "high", 0),
        (ClaimRecord.priority_tier == "medium", 1),
        (ClaimRecord.priority_tier == "low", 2),
        else_=3,
    )
    status_order = case(
        (ClaimRecord.status == "review_required", 0),
        (ClaimRecord.status == "processed", 1),
        (ClaimRecord.status == "failed", 2),
        (ClaimRecord.status == "scanning", 3),
        (ClaimRecord.status == "pending", 4),
        (ClaimRecord.status == "verified", 5),
        else_=6,
    )
    return [
        asc(tier_order),
        asc(ClaimRecord.received_at),
        asc(ClaimRecord.queue_sequence),
        asc(status_order),
        asc(ClaimRecord.claim_id),
    ]


def claim_queue_ordering():
    return [
        asc(ClaimRecord.queue_sequence),
        asc(ClaimRecord.received_at),
        asc(ClaimRecord.status),
        asc(ClaimRecord.claim_id),
    ]


def claim_sorting(sort: str | None):
    return {
        "queue": claim_queue_ordering(),
        "priority": claim_priority_ordering(),
        "risk_desc": [
            nulls_last(desc(ClaimRecord.risk_score)),
            asc(ClaimRecord.queue_sequence),
            asc(ClaimRecord.claim_id),
        ],
        "risk_asc": [
            nulls_last(asc(ClaimRecord.risk_score)),
            asc(ClaimRecord.queue_sequence),
            asc(ClaimRecord.claim_id),
        ],
        "cost_desc": [
            desc(ClaimRecord.cost_claimed),
            asc(ClaimRecord.queue_sequence),
            asc(ClaimRecord.claim_id),
        ],
        "cost_asc": [
            asc(ClaimRecord.cost_claimed),
            asc(ClaimRecord.queue_sequence),
            asc(ClaimRecord.claim_id),
        ],
        "id": [asc(ClaimRecord.claim_id)],
    }.get(sort or "priority", claim_priority_ordering())


async def _index_claim_in_background(claim_data: dict) -> None:
    """Keep intake responsive while the local embedding model indexes the claim."""
    try:
        from backend.app.ml.similarity import store_single_claim
        from backend.app.ml.graph_metrics import refresh_sync_safe

        await asyncio.to_thread(store_single_claim, claim_data)
        refresh_sync_safe()
    except Exception as e:
        print(f"[claims] Peringatan index LanceDB: {e}")


# Route ganda (dengan & tanpa trailing slash) — hindari 307 redirect FastAPI yang
# mengarah ke host backend langsung dan diblokir CORS saat lewat proxy dev.
@router.get("")
@router.get("/")
async def list_claims(
    db=Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    status: ClaimStatus | None = Query(None, description="Filter status: pending|scanning|processed|review_required|failed|verified"),
    tier: ClaimTier | None = Query(None, description="Filter prioritas: high|medium|low"),
    q: str | None = Query(None, max_length=100, description="Cari claim_id/pasien/faskes/diagnosis"),
    received_from: date | None = Query(None, description="Tanggal penerimaan mulai"),
    received_to: date | None = Query(None, description="Tanggal penerimaan sampai"),
    admission_from: date | None = Query(None, description="Tanggal masuk mulai"),
    admission_to: date | None = Query(None, description="Tanggal masuk sampai"),
    sort: ClaimSort = Query("priority", description="priority|queue|risk_desc|risk_asc|cost_desc|cost_asc|id"),
):
    """Daftar klaim dengan pagination, filter, search, dan sorting."""
    query = select(ClaimRecord)
    count_query = select(func.count(ClaimRecord.claim_id))

    filters = []
    if status:
        filters.append(ClaimRecord.status == status)
    if tier:
        filters.append(ClaimRecord.priority_tier == tier)
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(
            ClaimRecord.claim_id.ilike(like),
            ClaimRecord.patient_id.ilike(like),
            ClaimRecord.provider_id.ilike(like),
            ClaimRecord.diagnosis_primary.ilike(like),
        ))
    filters.extend(claim_received_filters(received_from, received_to))
    filters.extend(claim_admission_filters(admission_from, admission_to))
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = await db.scalar(count_query)

    for col in claim_sorting(sort):
        query = query.order_by(col)

    result = await db.execute(query.offset(skip).limit(limit))
    claims = result.scalars().all()

    return {
        "total": total or 0,
        "items": [_safe_claim_payload(claim) for claim in claims],
        "skip": skip,
        "limit": limit,
    }


@router.post("")
@router.post("/")
async def create_claim(claim: ClaimInput, db=Depends(get_db)):
    """Simpan klaim baru dari intake — SEMUA field disimpan (tidak ada data loss)."""
    result = await db.execute(select(ClaimRecord).where(ClaimRecord.claim_id == claim.claim_id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Klaim dengan ID {claim.claim_id} sudah ada di sistem.")

    record = ClaimRecord(
        claim_id=claim.claim_id,
        patient_id=claim.patient_id,
        provider_id=claim.provider_id,
        doctor_id=claim.doctor_id,
        diagnosis_primary=claim.diagnosis_primary,
        diagnosis_secondary=",".join(claim.diagnosis_secondary) if claim.diagnosis_secondary else "",
        procedure_codes=",".join(claim.procedure_codes) if claim.procedure_codes else "",
        severity_level=claim.severity_level,
        cost_claimed=claim.cost_claimed,
        length_of_stay=claim.length_of_stay,
        admission_date=claim.admission_date.isoformat() if claim.admission_date else None,
        discharge_date=claim.discharge_date.isoformat() if claim.discharge_date else None,
        medication_json=json.dumps([m.model_dump() for m in claim.medication]) if claim.medication else None,
        referral_json=claim.referral_info.model_dump_json() if claim.referral_info else None,
        status="pending",
    )
    db.add(record)
    await db.commit()
    enqueue_claim(record.claim_id)

    # Embedding lokal dapat lambat; klaim sudah aman di DB dan akan tetap di-index
    # lagi saat analisis selesai. Jangan tahan respons intake untuk pekerjaan ini.
    asyncio.create_task(_index_claim_in_background(claim.model_dump(mode="json")))

    return {"status": "success", "claim_id": claim.claim_id, "message": "Klaim berhasil diterima dan menunggu pemeriksaan."}


@router.get("/{claim_id}")
async def get_claim(claim_id: str, db=Depends(get_db)):
    result = await db.execute(select(ClaimRecord).where(ClaimRecord.claim_id == claim_id))
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return _safe_claim_payload(claim)


@router.get("/{claim_id}/analysis")
async def get_claim_analysis(claim_id: str, db=Depends(get_db)):
    """Ambil hasil analisis AI yang sudah ada (hindari re-run pipeline tiap visit)."""
    claim = await db.scalar(select(ClaimRecord).where(ClaimRecord.claim_id == claim_id))
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    result = await db.execute(select(RiskAnalysisRecord).where(RiskAnalysisRecord.claim_id == claim_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        return {"status": "not_analyzed"}

    try:
        evidence = json.loads(analysis.evidence_json or "{}")
    except json.JSONDecodeError:
        evidence = {}

    from backend.app.agents.orchestrator import ANALYSIS_VERSION
    if not is_current_analysis(analysis.analysis_version, analysis.evidence_json):
        return {
            "status": "stale",
            "claim_id": claim_id,
            "analysis_version": evidence.get("analysis_version"),
            "current_analysis_version": ANALYSIS_VERSION,
        }

    return {
        "status": "analyzed",
        "claim_id": claim_id,
        "analysis_version": ANALYSIS_VERSION,
        "total_score": analysis.total_score,
        "priority_tier": analysis.priority_tier,
        "recommended_action": analysis.recommended_action,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "result": public_analysis_projection(evidence),
    }


@router.delete("/{claim_id}")
async def reset_claim(claim_id: str, db=Depends(get_db)):
    """Reset current analysis state while retaining the audited decision history."""
    result = await db.execute(
        select(ClaimRecord)
        .where(ClaimRecord.claim_id == claim_id)
        .with_for_update()
    )
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim.status = "pending"
    claim.human_decision = None
    claim.risk_score = None
    claim.priority_tier = None
    claim.analysis_started_at = None
    claim.analysis_heartbeat_at = None
    claim.analyzed_at = None
    claim.verified_at = None
    claim.analysis_attempts = 0
    claim.last_analysis_error = None
    claim.last_analysis_error_code = None
    claim.analysis_generation = str(uuid.uuid4())

    await db.execute(delete(RiskAnalysisRecord).where(RiskAnalysisRecord.claim_id == claim_id))

    await db.commit()
    enqueue_claim(claim_id)
    return {"status": "success", "message": f"Klaim {claim_id} akan diperiksa kembali."}


@router.get("/{claim_id}/decision")
async def get_claim_decision(claim_id: str, db=Depends(get_db)):
    """Keputusan verifier terbaru untuk klaim ini."""
    claim = await db.scalar(
        select(ClaimRecord)
        .where(ClaimRecord.claim_id == claim_id)
        .with_for_update()
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    generation_filter = (
        HumanDecisionRecord.analysis_generation.is_(None)
        if claim.analysis_generation is None
        else HumanDecisionRecord.analysis_generation == claim.analysis_generation
    )
    result = await db.execute(
        select(HumanDecisionRecord)
        .where(HumanDecisionRecord.claim_id == claim_id, generation_filter)
        .order_by(HumanDecisionRecord.timestamp.desc(), HumanDecisionRecord.id.desc())
        .limit(1)
    )
    decision = result.scalar_one_or_none()
    verified_at = claim.verified_at.isoformat() if claim and claim.verified_at else None
    if not decision:
        return {"status": "no_decision", "verified_at": verified_at}
    return {
        "status": "decided",
        "decision": decision.decision,
        "reviewer": decision.reviewer,
        "timestamp": decision.timestamp.isoformat(),
        "verified_at": verified_at,
    }


@router.post("/{claim_id}/decision")
async def submit_decision(claim_id: str, decision: HumanDecision, db=Depends(get_db)):
    """Simpan keputusan verifikasi manusia + catat audit log."""
    if decision.claim_id != claim_id:
        raise HTTPException(status_code=400, detail="Claim ID mismatch")

    claim_result = await db.execute(
        select(ClaimRecord)
        .where(ClaimRecord.claim_id == claim_id)
        .with_for_update()
    )
    claim_rec = claim_result.scalar_one_or_none()
    if not claim_rec:
        raise HTTPException(status_code=404, detail="Claim not found")
    is_update = claim_rec.status == "verified"
    if claim_rec.status not in ["processed", "review_required", "verified"]:
        raise HTTPException(
            status_code=409,
            detail="Keputusan hanya dapat disimpan untuk klaim yang selesai dianalisis.",
        )

    analysis_result = await db.execute(
        select(RiskAnalysisRecord)
        .where(
            RiskAnalysisRecord.claim_id == claim_id,
            RiskAnalysisRecord.analysis_version == ANALYSIS_VERSION,
        )
        .with_for_update()
    )
    analysis = analysis_result.scalar_one_or_none()
    if not analysis or not is_current_analysis(analysis.analysis_version, analysis.evidence_json):
        raise HTTPException(
            status_code=409,
            detail="Hasil analisis terbaru belum tersedia untuk klaim ini.",
        )

    current_decision = None
    if is_update:
        generation_filter = (
            HumanDecisionRecord.analysis_generation.is_(None)
            if claim_rec.analysis_generation is None
            else HumanDecisionRecord.analysis_generation == claim_rec.analysis_generation
        )
        decision_result = await db.execute(
            select(HumanDecisionRecord)
            .where(
                HumanDecisionRecord.claim_id == claim_id,
                generation_filter,
            )
            .order_by(HumanDecisionRecord.timestamp.desc(), HumanDecisionRecord.id.desc())
            .limit(1)
            .with_for_update()
        )
        current_decision = decision_result.scalar_one_or_none()
        if current_decision is None:
            raise HTTPException(
                status_code=409,
                detail="Keputusan tersimpan bukan bagian dari generasi analisis terbaru.",
            )

    db.add(HumanDecisionRecord(
        claim_id=claim_id,
        decision=decision.decision,
        reviewer=decision.reviewer,
        analysis_generation=claim_rec.analysis_generation,
    ))

    claim_rec.status = "verified"
    claim_rec.human_decision = decision.decision
    if claim_rec.verified_at is None:
        claim_rec.verified_at = datetime.now(timezone.utc)

    # Audit log (PRD Section 12 — keputusan manusia tercatat)
    from backend.app.models.database import AuditLogRecord
    db.add(AuditLogRecord(
        claim_id=claim_id,
        agent_name="human_verifier",
        action="decision_updated" if is_update else "decision_submitted",
        details=(
            f"{current_decision.decision} -> {decision.decision} by {decision.reviewer}"
            if is_update
            else f"{decision.decision} by {decision.reviewer}"
        ),
    ))

    await db.commit()
    return {
        "status": "success",
        "message": "Keputusan verifikasi berhasil disimpan",
        "verified_at": claim_rec.verified_at.isoformat() if claim_rec and claim_rec.verified_at else None,
    }
