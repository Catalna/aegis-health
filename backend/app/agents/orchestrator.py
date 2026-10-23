"""
Orchestrator — pengatur alur pipeline (bukan agent, bukan LLM).

Sesuai AGENTS.md Section 0:
1. validate_deterministic() sebagai gerbang sebelum agent mana pun jalan.
2. 3 agent paralel dengan run_with_fallback — kegagalan satu agent TIDAK
   menjatuhkan pipeline; hasil tetap keluar dengan flag partial=True.
3. Provenance tiap agent dicatat (durasi nyata, status, model).
"""
import asyncio
import json
import logging
import time
from datetime import date

from sqlalchemy.future import select as sa_select

from backend.app.models.schemas import (
    ClaimInput, RiskAssessment, ValidationResult, AgentError,
)
from backend.app.agents.clinical_agent import analyze_clinical
from backend.app.agents.financial_engine import analyze_financial
from backend.app.agents.fraud_agent import analyze_fraud
from backend.app.agents.review_agent import synthesize_review
from backend.app.agents.risk_engine import calculate_risk_score
from backend.app.agents.explanation_agent import generate_explanation
from backend.app.models.database import (
    AsyncSessionLocal, RiskAnalysisRecord, AgentRunRecord, AuditLogRecord, ClaimRecord,
)
from backend.app.core.versions import ANALYSIS_VERSION
from backend.app.core.errors import (
    ANALYSIS_FAILURE_MESSAGE,
    VALIDATION_REJECTED_CODE,
    VALIDATION_REJECTED_MESSAGE,
    failure_for_exception,
    INTERNAL_ANALYSIS_FAILURE_REASON,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Validation — deterministic gate (AGENTS.md Section 1)
# ---------------------------------------------------------------------------

async def validate_deterministic(claim: ClaimInput, db) -> ValidationResult:
    result = ValidationResult(claim_id=claim.claim_id)

    # 1. Field wajib (Pydantic juga memvalidasi, tapi ini gerbang eksplisit)
    missing = [
        f for f, v in [
            ("claim_id", claim.claim_id),
            ("patient_id", claim.patient_id),
            ("provider_id", claim.provider_id),
            ("diagnosis_primary", claim.diagnosis_primary),
        ] if not v or not str(v).strip()
    ]
    if missing:
        result.hard_reject = True
        result.reject_reason = f"Field wajib kosong: {', '.join(missing)}"
        return result

    # 2. Urutan tanggal rawat
    if claim.admission_date and claim.discharge_date:
        if claim.discharge_date < claim.admission_date:
            result.hard_reject = True
            result.reject_reason = (
                f"Data corrupt: tanggal keluar ({claim.discharge_date}) lebih awal dari "
                f"tanggal masuk ({claim.admission_date})."
            )
            return result
        # Konsistensi LOS vs rentang tanggal (warning lunak)
        span_days = (claim.discharge_date - claim.admission_date).days
        if abs(span_days - claim.length_of_stay) > 1:
            result.warnings.append(
                f"Lama rawat ({claim.length_of_stay} hr) tidak konsisten dengan rentang "
                f"tanggal masuk-keluar ({span_days} hr)."
            )

    # 3. Severity range (Pydantic sudah, tapi tetap dicek defensif)
    if not (1 <= claim.severity_level <= 4):
        result.hard_reject = True
        result.reject_reason = f"Severity level {claim.severity_level} di luar rentang 1-4."
        return result

    # 4. Biaya & LOS masuk akal
    if claim.cost_claimed <= 0:
        result.hard_reject = True
        result.reject_reason = "Biaya klaim harus positif."
        return result

    # 5. Exact duplicate — semua field klinis identik dengan klaim lain di DB.
    #    Tanggal masuk WAJIB sama: pasangan pasien/diagnosis/prosedur/biaya yang
    #    identik tapi beda tanggal masuk adalah episode lain (repeat billing),
    #    bukan pengajuan ulang klaim yang sama.
    claim_admit = claim.admission_date.isoformat() if claim.admission_date else None
    db_result = await db.execute(
        sa_select(ClaimRecord).where(
            ClaimRecord.patient_id == claim.patient_id,
            ClaimRecord.diagnosis_primary == claim.diagnosis_primary,
            ClaimRecord.cost_claimed == claim.cost_claimed,
            ClaimRecord.claim_id != claim.claim_id,
            ClaimRecord.admission_date == claim_admit,
        )
    )
    for other in db_result.scalars():
        other_sec = {s.strip() for s in (other.diagnosis_secondary or "").split(",") if s.strip()}
        other_proc = {p.strip() for p in (other.procedure_codes or "").split(",") if p.strip()}
        if other_sec == set(claim.diagnosis_secondary) and other_proc == set(claim.procedure_codes):
            result.exact_duplicate_of = other.claim_id
            result.warnings.append(
                f"Klaim identik dengan {other.claim_id} (pasien, diagnosis, prosedur, biaya, dan tanggal masuk sama) — "
                "hanya Fraud Agent yang dijalankan sesuai protokol exact duplicate."
            )
            break

    return result


# ---------------------------------------------------------------------------
# Fallback wrapper + provenance logging
# ---------------------------------------------------------------------------

async def run_with_fallback(agent_name: str, coro_fn, claim: ClaimInput, fallback_factory):
    """
    Jalankan agent; jika exception → kembalikan hasil fallback + AgentError
    (pipeline tidak berhenti total; flag partial=True).
    """
    start = time.perf_counter()
    try:
        result = await coro_fn(claim)
        duration_ms = int((time.perf_counter() - start) * 1000)
        model_used = getattr(result, "model_used", None) or getattr(result, "method", None) or getattr(result, "generated_by", None)
        return result, AgentError(
            agent_name=agent_name, error_type="exception",
            raw_output=None, fallback_applied=False,
        ), duration_ms, model_used, "success"
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        failure = failure_for_exception(e)
        logger.exception("Agent fallback failed for agent=%s claim_id=%s", agent_name, claim.claim_id)
        fallback = fallback_factory(claim, failure.message)
        return fallback, AgentError(
            agent_name=agent_name, error_type="tool_failure",
            raw_output=None, fallback_applied=True,
        ), duration_ms, None, "fallback"


async def _save_agent_run(db, claim_id, agent_name, status, duration_ms, output, model_used=None):
    db.add(AgentRunRecord(
        claim_id=claim_id,
        agent_name=agent_name,
        status=status,
        duration_ms=duration_ms,
        model_used=model_used,
        output_json=output if isinstance(output, str) else json.dumps(output, default=str),
    ))


async def _audit(db, claim_id, agent_name, action, details=None):
    db.add(AuditLogRecord(
        claim_id=claim_id, agent_name=agent_name, action=action, details=details,
    ))


# ---------------------------------------------------------------------------
# Pipeline utama
# ---------------------------------------------------------------------------

# Versi engine analisis — di-stamp ke evidence_json. Hasil tersimpan dengan
# versi berbeda dianggap stale oleh frontend dan memicu analisis ulang otomatis
# (hasil lama tidak boleh ditampilkan karena skornya dihitung logika berbeda).
# v6: deterministic evidence contract, no tariff double-counting, no behavioral
# context score, and grounded explanation IDs.


async def process_claim(
    claim: ClaimInput,
    sse_queue: asyncio.Queue = None,
    analysis_generation: str | None = None,
    terminal_outcome: dict | None = None,
) -> RiskAssessment:
    async def emit(event_type: str, data: dict):
        if sse_queue:
            event = {"event": event_type, "data": data}
            try:
                sse_queue.put_nowait(event)
            except asyncio.QueueFull:
                # A disconnected/manual-less consumer must not hold the
                # analysis task open. Retain terminal errors when possible.
                if event_type in {"error", "rejected"}:
                    try:
                        sse_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        sse_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        pass

    await emit("status", {"message": f"Klaim {claim.claim_id} diterima, memulai validasi deterministik...", "step": "start"})

    agent_errors: list[AgentError] = []

    async with AsyncSessionLocal() as db:
        try:
            # ---------- Phase 0: Validasi deterministik ----------
            validation = await validate_deterministic(claim, db)

            if validation.warnings:
                for w in validation.warnings:
                    await emit("status", {"message": f"Peringatan validasi: {w}", "step": "validation"})

            if validation.hard_reject:
                await _audit(db, claim.claim_id, "orchestrator", "hard_reject", validation.reject_reason)
                await db.commit()
                assessment = RiskAssessment.create_rejected(
                    claim.claim_id,
                    VALIDATION_REJECTED_MESSAGE,
                    VALIDATION_REJECTED_CODE,
                )
                if terminal_outcome is not None:
                    terminal_outcome["assessment"] = assessment
                await emit("status", {"message": VALIDATION_REJECTED_MESSAGE, "step": "validation"})
                await emit("rejected", {"code": VALIDATION_REJECTED_CODE, "message": VALIDATION_REJECTED_MESSAGE})
                return assessment

            is_duplicate = validation.exact_duplicate_of is not None

            # ---------- Phase 1: Agent paralel (dengan fallback) ----------
            await emit("status", {"message": "Menjalankan Clinical, Financial, dan Fraud analysis (paralel)...", "step": "phase1"})

            def fb_clinical(c, err):
                from backend.app.models.schemas import ClinicalAssessment
                return ClinicalAssessment(
                    claim_id=c.claim_id, compatibility_status="no_data", plausibility="n/a",
                    evidence_text=f"Clinical agent gagal: {err}", confidence_level="low",
                    evidence_source="fallback_no_data",
                )

            def fb_financial(c, err):
                from backend.app.models.schemas import FinancialAssessment
                return FinancialAssessment(
                    claim_id=c.claim_id, predicted_cost_range=(0, 0), actual_cost=c.cost_claimed,
                    deviation_pct=0, shap_top_features=[], anomaly_score=0,
                    evidence_text=f"Financial engine gagal: {err}", method="zscore_peer_fallback",
                )

            def fb_fraud(c, err):
                from backend.app.models.schemas import FraudAssessment
                return FraudAssessment(
                    claim_id=c.claim_id, similarity_max_score=0, repeat_billing_flag=False,
                    graph_cluster_anomaly_score=0, evidence_text=f"Fraud agent gagal: {err}",
                )

            if is_duplicate:
                # Protokol exact duplicate: skip clinical & financial, langsung fraud
                await emit("status", {"message": f"Exact duplicate dari {validation.exact_duplicate_of} — hanya Fraud Agent dijalankan.", "step": "phase1"})
                clinical = fb_clinical(claim, "Dilewati: exact duplicate (protokol AGENTS.md Section 1)")
                financial = fb_financial(claim, "Dilewati: exact duplicate (protokol AGENTS.md Section 1)")
                fraud, fraud_err, fraud_ms, fraud_model, fraud_status = await run_with_fallback(
                    "fraud_agent", analyze_fraud, claim, fb_fraud
                )
                agent_errors.extend(e for e in [fraud_err] if e.fallback_applied)
                await _save_agent_run(db, claim.claim_id, "clinical_agent", "skipped", 0, clinical.model_dump_json())
                await _save_agent_run(db, claim.claim_id, "financial_agent", "skipped", 0, financial.model_dump_json())
                await _save_agent_run(db, claim.claim_id, "fraud_agent", fraud_status, fraud_ms, fraud.model_dump_json(), fraud_model)
            else:
                results = await asyncio.gather(
                    run_with_fallback("clinical_agent", analyze_clinical, claim, fb_clinical),
                    run_with_fallback("financial_agent", analyze_financial, claim, fb_financial),
                    run_with_fallback("fraud_agent", analyze_fraud, claim, fb_fraud),
                )
                (
                    (clinical, c_err, c_ms, c_model, c_status),
                    (financial, f_err, f_ms, f_model, f_status),
                    (fraud, fraud_err, fraud_ms, fraud_model, fraud_status),
                ) = results

                agent_errors.extend(e for e in [c_err, f_err, fraud_err] if e.fallback_applied)
                await _save_agent_run(db, claim.claim_id, "clinical_agent", c_status, c_ms, clinical.model_dump_json(), c_model)
                await _save_agent_run(db, claim.claim_id, "financial_agent", f_status, f_ms, financial.model_dump_json(), f_model)
                await _save_agent_run(db, claim.claim_id, "fraud_agent", fraud_status, fraud_ms, fraud.model_dump_json(), fraud_model)

                for err in agent_errors:
                    await emit("status", {"message": "Peringatan: satu pemeriksaan tidak tersedia; data cadangan digunakan.", "step": "phase1"})

            partial = any(e.fallback_applied for e in agent_errors)
            fraud.exact_duplicate = is_duplicate

            await emit("phase1_complete", {
                "clinical": clinical.model_dump(),
                "financial": financial.model_dump(),
                "fraud": fraud.model_dump(),
                "partial": partial,
            })

            # ---------- Phase 2: Review synthesis ----------
            await emit("status", {"message": "Menyintesis evidence (Review Agent)...", "step": "phase2"})
            start = time.perf_counter()
            review = await synthesize_review(claim, clinical, financial, fraud)
            review_ms = int((time.perf_counter() - start) * 1000)
            await _save_agent_run(db, claim.claim_id, "review_agent", "success" if review.reasoning_source != "rule_fallback" else "fallback", review_ms, review.model_dump_json(), review.model_used)
            await emit("phase2_complete", {"review": review.model_dump()})

            # ---------- Phase 3: Risk scoring ----------
            await emit("status", {"message": "Menghitung skor risiko final...", "step": "phase3"})
            start = time.perf_counter()
            risk = calculate_risk_score(clinical, financial, fraud, review)
            risk_ms = int((time.perf_counter() - start) * 1000)
            await _save_agent_run(db, claim.claim_id, "risk_engine", "success", risk_ms, risk.model_dump_json())
            await emit("phase3_complete", {"risk": risk.model_dump()})

            # ---------- Phase 4: Explanation ----------
            await emit("status", {"message": "Menyusun narasi penjelasan (Explanation Agent)...", "step": "phase4"})
            start = time.perf_counter()
            explanation = await generate_explanation(claim, clinical, financial, fraud, review, risk)
            expl_ms = int((time.perf_counter() - start) * 1000)
            await _save_agent_run(db, claim.claim_id, "explanation_agent", "success" if explanation.generated_by != "template_fallback" else "fallback", expl_ms, explanation.model_dump_json(), explanation.generated_by)
            await emit("phase4_complete", {"explanation": explanation.model_dump()})

            # ---------- Assemble & persist ----------
            final_assessment = RiskAssessment(
                claim_id=claim.claim_id,
                score=risk,
                evidence=review,
                narrative=explanation,
                partial=partial,
                agent_errors=agent_errors,
                exact_duplicate=is_duplicate,
            )

            persisted_evidence = {
                "analysis_version": ANALYSIS_VERSION,
                "assessment": final_assessment.model_dump(),
                "clinical": clinical.model_dump(),
                "financial": financial.model_dump(),
                "fraud": fraud.model_dump(),
                "review": review.model_dump(),
                "risk": risk.model_dump(),
                "explanation": explanation.model_dump(),
            }
            predicted_upper = financial.predicted_cost_range[1] if financial.predicted_cost_range else None
            analysis_record = RiskAnalysisRecord(
                claim_id=claim.claim_id,
                clinical_score=risk.breakdown.get("clinical_rule_flags", 0),
                financial_score=risk.breakdown.get("financial_anomaly", 0),
                fraud_score=risk.breakdown.get("similarity_fraud", 0) + risk.breakdown.get("isolation_forest_anomaly", 0),
                similarity_score=fraud.similarity_max_score,
                total_score=risk.total_score,
                priority_tier=risk.priority_tier,
                recommended_action=explanation.recommended_action,
                actual_cost=financial.actual_cost,
                predicted_cost_upper=predicted_upper,
                analysis_version=ANALYSIS_VERSION,
                evidence_json=json.dumps(persisted_evidence, default=str),
            )
            claim_query = sa_select(ClaimRecord).where(ClaimRecord.claim_id == claim.claim_id)
            if analysis_generation is not None:
                claim_query = claim_query.with_for_update()
            result_q = await db.execute(claim_query)
            claim_rec = result_q.scalar_one_or_none()
            if analysis_generation is not None and (
                claim_rec is None
                or claim_rec.status != "scanning"
                or claim_rec.analysis_generation != analysis_generation
            ):
                await db.rollback()
                return final_assessment

            await db.merge(analysis_record)
            if claim_rec:
                if analysis_generation is None:
                    claim_rec.status = "processed"
                claim_rec.risk_score = risk.total_score
                claim_rec.priority_tier = risk.priority_tier

            await _audit(db, claim.claim_id, "orchestrator", "analysis_complete",
                         f"score={risk.total_score}, tier={risk.priority_tier}, partial={partial}")
            await db.commit()

            # Index klaim ke LanceDB agar bisa ditemukan similarity check berikutnya
            try:
                from backend.app.ml.similarity import store_single_claim
                store_single_claim(claim.model_dump(mode="json"))
            except Exception as e:
                logger.exception("Similarity indexing failed for claim_id=%s", claim.claim_id)

            if terminal_outcome is not None:
                terminal_outcome["assessment"] = final_assessment
            await emit("status", {"message": "Analisis selesai." + (" (partial — beberapa agent fallback)" if partial else ""), "step": "complete"})
            return final_assessment

        except Exception as e:
            logger.exception("Analysis orchestration failed for claim_id=%s", claim.claim_id)
            await db.rollback()
            failure = failure_for_exception(e)
            assessment = RiskAssessment.create_rejected(claim.claim_id, failure.message, failure.code)
            if terminal_outcome is not None:
                terminal_outcome["assessment"] = assessment
            await emit("error", {"code": failure.code, "message": failure.message})
            return assessment
