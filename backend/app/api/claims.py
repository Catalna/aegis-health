import asyncio
import json
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.future import select
from sqlalchemy import func, delete, or_, asc, desc, case

from backend.app.models.schemas import ClaimInput, HumanDecision
from backend.app.models.database import (
    AsyncSessionLocal, HumanDecisionRecord, ClaimRecord, RiskAnalysisRecord,
)

router = APIRouter(prefix="/api/claims", tags=["claims"])


def is_current_analysis(evidence: dict) -> bool:
    """Return whether persisted analysis was produced by the current engine."""
    from backend.app.agents.orchestrator import ANALYSIS_VERSION

    return evidence.get("analysis_version") == ANALYSIS_VERSION


async def _index_claim_in_background(claim_data: dict) -> None:
    """Keep intake responsive while the local embedding model indexes the claim."""
    try:
        from backend.app.ml.similarity import store_single_claim
        from backend.app.ml.graph_metrics import refresh_sync_safe

        await asyncio.to_thread(store_single_claim, claim_data)
        refresh_sync_safe()
    except Exception as e:
        print(f"[claims] Peringatan index LanceDB: {e}")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# Route ganda (dengan & tanpa trailing slash) — hindari 307 redirect FastAPI yang
# mengarah ke host backend langsung dan diblokir CORS saat lewat proxy dev.
@router.get("")
@router.get("/")
async def list_claims(
    db=Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    status: str | None = Query(None, description="Filter status: pending|processed|verified"),
    tier: str | None = Query(None, description="Filter prioritas: high|medium|low"),
    q: str | None = Query(None, max_length=100, description="Cari claim_id/pasien/faskes/diagnosis"),
    sort: str = Query("priority", description="priority|risk_desc|risk_asc|cost_desc|cost_asc|id"),
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
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = await db.scalar(count_query)

    # Sorting: prioritas risiko dulu (pending → skor desc), atau pilihan user
    tier_order = case(
        (ClaimRecord.priority_tier == "high", 0),
        (ClaimRecord.priority_tier == "medium", 1),
        (ClaimRecord.priority_tier == "low", 2),
        else_=3,
    )
    status_order = case(
        (ClaimRecord.status == "pending", 0),
        (ClaimRecord.status == "processed", 1),
        else_=2,
    )
    sort_map = {
        "priority": [asc(status_order), desc(ClaimRecord.risk_score), asc(ClaimRecord.claim_id)],
        "risk_desc": [desc(ClaimRecord.risk_score)],
        "risk_asc": [asc(ClaimRecord.risk_score)],
        "cost_desc": [desc(ClaimRecord.cost_claimed)],
        "cost_asc": [asc(ClaimRecord.cost_claimed)],
        "id": [asc(ClaimRecord.claim_id)],
    }
    for col in sort_map.get(sort, sort_map["priority"]):
        query = query.order_by(col)

    result = await db.execute(query.offset(skip).limit(limit))
    claims = result.scalars().all()

    return {"total": total or 0, "items": claims, "skip": skip, "limit": limit}


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

    # Embedding lokal dapat lambat; klaim sudah aman di DB dan akan tetap di-index
    # lagi saat analisis selesai. Jangan tahan respons intake untuk pekerjaan ini.
    asyncio.create_task(_index_claim_in_background(claim.model_dump(mode="json")))

    return {"status": "success", "claim_id": claim.claim_id, "message": "Klaim berhasil disimpan ke sistem."}


@router.get("/{claim_id}")
async def get_claim(claim_id: str, db=Depends(get_db)):
    result = await db.execute(select(ClaimRecord).where(ClaimRecord.claim_id == claim_id))
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@router.get("/{claim_id}/analysis")
async def get_claim_analysis(claim_id: str, db=Depends(get_db)):
    """Ambil hasil analisis AI yang sudah ada (hindari re-run pipeline tiap visit)."""
    result = await db.execute(select(RiskAnalysisRecord).where(RiskAnalysisRecord.claim_id == claim_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        return {"status": "not_analyzed"}

    try:
        evidence = json.loads(analysis.evidence_json or "{}")
    except json.JSONDecodeError:
        evidence = {}

    from backend.app.agents.orchestrator import ANALYSIS_VERSION
    if not is_current_analysis(evidence):
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
        "result": evidence,
    }


@router.delete("/{claim_id}")
async def reset_claim(claim_id: str, db=Depends(get_db)):
    """Reset status klaim & hapus riwayat analisis/keputusan untuk proses ulang."""
    result = await db.execute(select(ClaimRecord).where(ClaimRecord.claim_id == claim_id))
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim.status = "pending"
    claim.human_decision = None
    claim.risk_score = None
    claim.priority_tier = None

    await db.execute(delete(RiskAnalysisRecord).where(RiskAnalysisRecord.claim_id == claim_id))
    await db.execute(delete(HumanDecisionRecord).where(HumanDecisionRecord.claim_id == claim_id))

    await db.commit()
    return {"status": "success", "message": f"Klaim {claim_id} telah di-reset."}


@router.get("/{claim_id}/decision")
async def get_claim_decision(claim_id: str, db=Depends(get_db)):
    """Keputusan verifier terbaru untuk klaim ini."""
    result = await db.execute(
        select(HumanDecisionRecord)
        .where(HumanDecisionRecord.claim_id == claim_id)
        .order_by(HumanDecisionRecord.timestamp.desc())
        .limit(1)
    )
    decision = result.scalar_one_or_none()
    if not decision:
        return {"status": "no_decision"}
    return {
        "status": "decided",
        "decision": decision.decision,
        "reviewer": decision.reviewer,
        "timestamp": decision.timestamp.isoformat(),
    }


@router.post("/{claim_id}/decision")
async def submit_decision(claim_id: str, decision: HumanDecision, db=Depends(get_db)):
    """Simpan keputusan verifikasi manusia + catat audit log."""
    if decision.claim_id != claim_id:
        raise HTTPException(status_code=400, detail="Claim ID mismatch")

    db.add(HumanDecisionRecord(
        claim_id=claim_id,
        decision=decision.decision,
        reviewer=decision.reviewer,
    ))

    result = await db.execute(select(ClaimRecord).where(ClaimRecord.claim_id == claim_id))
    claim_rec = result.scalar_one_or_none()
    if claim_rec:
        claim_rec.status = "verified"
        claim_rec.human_decision = decision.decision

    # Audit log (PRD Section 12 — keputusan manusia tercatat)
    from backend.app.models.database import AuditLogRecord
    db.add(AuditLogRecord(
        claim_id=claim_id,
        agent_name="human_verifier",
        action="decision_submitted",
        details=f"{decision.decision} by {decision.reviewer}",
    ))

    await db.commit()
    return {"status": "success", "message": "Keputusan verifikasi berhasil disimpan"}
