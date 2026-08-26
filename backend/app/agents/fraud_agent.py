"""
Fraud/Pattern Investigation Agent — tanpa LLM (AGENTS.md Section 4).

Sinyal:
1. Isolation Forest (unsupervised behavioral anomaly)
2. Similarity (LanceDB cosine) → cloning antar pasien
3. Repeat billing → SQL: pasien sama + prosedur tumpang tindih + rentang tanggal dekat
4. Provider network anomaly → metrik graph precomputed (graph_metrics.py)
"""
import json
import joblib
import numpy as np
import os
from datetime import date, timedelta

from sqlalchemy.future import select as sa_select

from backend.app.models.schemas import ClaimInput, FraudAssessment, SimilarClaim
from backend.app.models.database import AsyncSessionLocal, ClaimRecord
from backend.app.ml.similarity import find_similar_claims
from backend.app.ml.feature_engineering import extract_features
from backend.app.ml.graph_metrics import get_provider_metrics

_MODELS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models_trained"))

iso_forest = None


def load_isolation_forest():
    global iso_forest
    if iso_forest is None:
        path = os.path.join(_MODELS_DIR, "isolation_forest.pkl")
        if os.path.exists(path):
            iso_forest = joblib.load(path)
    return iso_forest


async def _check_repeat_billing_db(claim: ClaimInput) -> str | None:
    """
    Repeat billing sesuai spek: pasien SAMA, prosedur tumpang tindih,
    tanggal rawat berdekatan (±45 hari), klaim berbeda. Return claim_id kembaran.
    """
    if not claim.procedure_codes:
        return None
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_select(ClaimRecord).where(
                    ClaimRecord.patient_id == claim.patient_id,
                    ClaimRecord.claim_id != claim.claim_id,
                )
            )
            candidates = result.scalars().all()
    except Exception as e:
        print(f"[fraud] Repeat-billing DB check gagal: {e}")
        return None

    claim_proc = set(claim.procedure_codes)
    admit = claim.admission_date

    for cand in candidates:
        cand_procs = {p.strip() for p in (cand.procedure_codes or "").split(",") if p.strip()}
        if not cand_procs or not (claim_proc & cand_procs):
            continue
        # Cek tanggal bila keduanya tersedia
        if admit and cand.admission_date:
            try:
                cand_admit = date.fromisoformat(str(cand.admission_date)[:10])
                if (admit - cand_admit).days > 45 or (cand_admit - admit).days > 45:
                    continue
            except ValueError:
                pass
        return cand.claim_id
    return None


async def analyze_fraud(claim: ClaimInput) -> FraudAssessment:
    claim_dict = claim.model_dump(mode="json")

    # ---------- 1. Isolation Forest ----------
    model = load_isolation_forest()
    if_score_normalized = 0.0
    is_if_outlier = False
    if model:
        features = np.array([extract_features(claim_dict)])
        raw_score = model.decision_function(features)[0]
        pred = model.predict(features)[0]
        is_if_outlier = (pred == -1)
        if_score_normalized = float(max(0.0, min(1.0, 0.5 - (raw_score * 2))))

    # ---------- 2. Similarity (LanceDB, skor komposit multi-faktor) ----------
    similar_raw = find_similar_claims(claim.claim_id, claim_dict, limit=3)
    similar_claims = [
        SimilarClaim(
            claim_id=s["claim_id"],
            similarity=s["similarity"],
            code_similarity=s.get("code_similarity", 0.0),
            cost_proximity=s.get("cost_proximity", 0.0),
            same_provider=s.get("same_provider", False),
            same_patient=s.get("same_patient", False),
            days_apart=s.get("days_apart"),
            profile_cosine=s.get("profile_cosine", 0.0),
            jaccard=s.get("jaccard", 0.0),
            provider_id=s.get("provider_id", ""),
            patient_id=s.get("patient_id", ""),
            diagnosis_primary=s.get("diagnosis_primary", ""),
            cost_claimed=s.get("cost_claimed", 0.0),
        )
        for s in similar_raw
    ]

    similarity_max = max((s["similarity"] for s in similar_raw), default=0.0)
    matched_id = next((s["claim_id"] for s in similar_raw if s["similarity"] == similarity_max), None)

    # Cloning sungguhan: faskes SAMA + pasien BERBEDA + kode medis hampir identik
    # + biaya hampir persis (klaim hasil cloning menyalin nominal). Kemiripan
    # profil medis saja (penyakit sama) BUKAN cloning.
    cloning_flag = any(
        s["same_provider"] and not s["same_patient"]
        and s.get("code_similarity", 0) > 0.9
        and s.get("cost_proximity", 0) > 0.95
        for s in similar_raw
    )

    # ---------- 3. Repeat billing (SQL, pasien sama) ----------
    repeat_matched_id = await _check_repeat_billing_db(claim)
    repeat_billing = repeat_matched_id is not None

    # ---------- 4. Provider network metrics (precomputed) ----------
    provider_metrics = get_provider_metrics(claim.provider_id)
    graph_score = float(provider_metrics.get("anomaly_score", 0.0))

    # ---------- Evidence text ----------
    parts = []
    if repeat_billing:
        parts.append(
            f"Indikasi repeat billing: pasien yang sama ({claim.patient_id}) memiliki klaim "
            f"{repeat_matched_id} dengan prosedur tumpang tindih dan rentang tanggal berdekatan."
        )
    if cloning_flag:
        top_clone = similar_raw[0] if similar_raw else {}
        parts.append(
            f"Indikasi cloning: klaim sangat mirip dengan {top_clone.get('claim_id', matched_id)} "
            f"dari faskes yang sama untuk pasien berbeda — kode medis "
            f"{top_clone.get('code_similarity', 0)*100:.0f}% identik dan biaya hampir persis "
            f"(Rp {top_clone.get('cost_claimed', 0):,.0f} vs Rp {claim.cost_claimed:,.0f})."
        )

    if is_if_outlier:
        parts.append(
            f"Profil klaim menyimpang dari pola historis (skor anomali perilaku: {if_score_normalized:.2f})."
        )

    if graph_score > 0.5:
        parts.append(
            f"Faskes {claim.provider_id} memiliki profil jaringan klaim menyimpang "
            f"(skor anomali jaringan: {graph_score:.2f}, rasio pasien/klaim "
            f"{provider_metrics.get('patients_per_claim', 0):.2f})."
        )

    if not parts:
        # Jelaskan bahwa kemiripan profil medis saja bukan temuan
        if similar_raw and similar_raw[0]["similarity"] > 0.4:
            top = similar_raw[0]
            ctx = []
            if top.get("same_provider"):
                ctx.append("faskes sama")
            else:
                ctx.append("faskes berbeda")
            parts.append(
                f"Terdapat klaim dengan pola medis serupa ({top['claim_id']}, {ctx[0]}) "
                "namun tidak memenuhi kriteria cloning/repeat billing — kemiripan pola penyakit "
                "diantar faskes berbeda adalah pola wajar."
            )
        else:
            parts.append("Tidak terdeteksi pola duplikasi, cloning, atau anomali jaringan yang signifikan.")

    return FraudAssessment(
        claim_id=claim.claim_id,
        similarity_max_score=float(similarity_max),
        similarity_matched_claim_id=matched_id,
        repeat_billing_flag=repeat_billing,
        repeat_billing_matched_claim_id=repeat_matched_id,
        cloning_flag=cloning_flag,
        graph_cluster_anomaly_score=graph_score,
        isolation_forest_score=if_score_normalized,
        is_isolation_forest_outlier=is_if_outlier,
        evidence_text=" ".join(parts),
        similar_claims=similar_claims,
    )
