"""
Review Agent — sintesis lintas-sumber via LLM, fallback rule-count (AGENTS.md Section 5).
"""
from backend.app.models.schemas import (
    ClaimInput, ClinicalAssessment, FinancialAssessment, FraudAssessment, ReviewSynthesis,
)
from backend.app.core.llm_client import (
    structured_completion, LLMError, REVIEW_MODEL, REVIEW_MODEL_FALLBACK, get_available_model,
)


def compute_rule_signals(
    clinical: ClinicalAssessment,
    financial: FinancialAssessment,
    fraud: FraudAssessment,
) -> list[str]:
    """Hitung sinyal deterministik — dipakai untuk fallback DAN validasi LLM."""
    signals: list[str] = []
    if "tariff_deviation_extreme" in clinical.rule_flags:
        signals.append("Deviasi tarif CBG ekstrem (>100%)")
    elif "tariff_deviation_high" in clinical.rule_flags:
        signals.append(f"Deviasi tarif CBG tinggi ({clinical.tariff_deviation_pct:.1f}%)")
    if "severity_proc_mismatch" in clinical.rule_flags:
        signals.append("Severity tinggi tanpa prosedur pendukung")
    if "severity_med_mismatch" in clinical.rule_flags:
        signals.append("Severity tinggi dengan obat tidak lengkap")
    if "los_outlier" in clinical.rule_flags:
        signals.append("Lama rawat melebihi batas klinis")
    if "upcoding_risk_diag" in clinical.rule_flags:
        signals.append("Diagnosis sekunder berisiko upcoding")
    if financial.anomaly_score > 0.4:
        signals.append(f"Skor anomali finansial {financial.anomaly_score:.2f}")
    if financial.deviation_pct > 30:
        signals.append(f"Biaya melebihi prediksi model +{financial.deviation_pct:.1f}%")
    if fraud.repeat_billing_flag:
        signals.append("Repeat billing terdeteksi (pasien sama, prosedur sama)")
    if fraud.cloning_flag:
        signals.append(f"Indikasi cloning: kemiripan {fraud.similarity_max_score:.0%} dengan klaim faskes sama untuk pasien berbeda")
    if fraud.is_isolation_forest_outlier:
        signals.append(f"Outlier perilaku (skor {fraud.isolation_forest_score:.2f})")
    return signals


async def synthesize_review(
    claim: ClaimInput,
    clinical: ClinicalAssessment,
    financial: FinancialAssessment,
    fraud: FraudAssessment,
) -> ReviewSynthesis:
    model = await get_available_model(REVIEW_MODEL, REVIEW_MODEL_FALLBACK)
    reasoning_source = "llm_reasoning_trace" if "deepseek" in model else "llm_direct"

    rule_signals = compute_rule_signals(clinical, financial, fraud)

    context = f"""
Review klaim berikut dan tentukan apakah sinyal-sinyal ini saling menguatkan atau lemah/berdiri sendiri.

Claim ID: {claim.claim_id}
Diagnosis Primer: {claim.diagnosis_primary}
Biaya Diklaim: Rp {claim.cost_claimed:,.0f}
Lama Rawat: {claim.length_of_stay} hari
Severity Level: {claim.severity_level}

--- Agent 1 (Clinical — rule engine + LLM untuk kasus ambigu) ---
Plausibility: {clinical.plausibility}
Status: {clinical.compatibility_status} (sumber evidence: {clinical.evidence_source})
Deviasi Tarif CBG: {f"{clinical.tariff_deviation_pct:.1f}%" if clinical.tariff_deviation_pct is not None else "N/A"}
Flag rule: {", ".join(clinical.rule_flags) if clinical.rule_flags else "tidak ada"}
Evidence: {clinical.evidence_text}

--- Agent 2 (Financial — XGBoost + SHAP, tanpa LLM) ---
Metode: {financial.method}
Deviasi dari Prediksi: {financial.deviation_pct:.1f}%
Anomaly Score: {financial.anomaly_score:.2f}
Driver Utama (SHAP): {", ".join([f.feature_label for f in financial.shap_top_features]) or "N/A"}
Evidence: {financial.evidence_text}

--- Agent 3 (Fraud/Pattern — LanceDB + SQL + graph metrics, tanpa LLM) ---
Repeat Billing: {"YA" if fraud.repeat_billing_flag else "TIDAK"}
Max Similarity: {fraud.similarity_max_score:.2f}
Klaim Paling Mirip: {fraud.similarity_matched_claim_id or "Tidak ada"}
Skor Jaringan Faskes: {fraud.graph_cluster_anomaly_score:.2f}
Evidence: {fraud.evidence_text}

SINYAL RULE TERDETEKSI ({len(rule_signals)}): {"; ".join(rule_signals) if rule_signals else "tidak ada"}

Tentukan evidence_level keseluruhan. Nilai harus PERSIS salah satu dari:
"strong_multi_signal" (≥2 sinyal saling menguatkan), "single_signal" (1 sinyal kuat), "weak" (tidak ada sinyal kuat).
corroborating_signals: daftar sinyal yang saling menguatkan (kosongkan jika weak).
reasoning_narrative: 1-3 kalimat Bahasa Indonesia yang menjelaskan KENAPA level itu dipilih,
hanya merujuk fakta di atas — dilarang menambah fakta baru.
"""

    system_prompt = (
        "Kamu adalah senior medical claims auditor BPJS. Sintesis temuan secara objektif. "
        "Fokus pada sinyal yang saling menguatkan. Jangan mengarang fakta. Respons dalam Bahasa Indonesia."
    )

    from pydantic import BaseModel

    class LLMSynthesisResponse(BaseModel):
        evidence_level: str
        corroborating_signals: list[str]
        reasoning_narrative: str

    try:
        response = await structured_completion(
            prompt=context,
            system_prompt=system_prompt,
            output_schema=LLMSynthesisResponse,
            model=model,
            temperature=0.1,
        )

        valid_levels = ["strong_multi_signal", "single_signal", "weak"]
        level = response.evidence_level if response.evidence_level in valid_levels else (
            "strong_multi_signal" if len(rule_signals) >= 2 else "single_signal" if len(rule_signals) == 1 else "weak"
        )

        # Guard: LLM tidak boleh mengklaim multi-sinyal kuat tanpa sinyal rule
        if level == "strong_multi_signal" and len(rule_signals) < 2:
            level = "single_signal" if len(rule_signals) == 1 else "weak"

        return ReviewSynthesis(
            claim_id=claim.claim_id,
            evidence_level=level,
            corroborating_signals=response.corroborating_signals or rule_signals[:3],
            reasoning_narrative=response.reasoning_narrative.strip(),
            reasoning_source=reasoning_source,
            model_used=model,
        )

    except Exception as e:
        # Fallback rule-count sesuai AGENTS.md Section 5 (tangkap semua kegagalan)
        level = "strong_multi_signal" if len(rule_signals) >= 2 else "single_signal" if len(rule_signals) == 1 else "weak"
        return ReviewSynthesis(
            claim_id=claim.claim_id,
            evidence_level=level,
            corroborating_signals=rule_signals,
            reasoning_narrative=(
                f"[Fallback rule-count — LLM synthesis tidak tersedia: {e}] "
                f"Terdeteksi {len(rule_signals)} sinyal dari rule engine."
            ),
            reasoning_source="rule_fallback",
            model_used=None,
        )
