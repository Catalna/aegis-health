"""
Risk Score Engine — fungsi scoring deterministik (AGENTS.md Section 6).
 TIDAK ADA input LLM yang mengubah skor. Bobot terdokumentasi (MODELS.md Section 5):

| Komponen                | Bobot maks | Sumber angka (wajib traceable)                    |
|-------------------------|-----------|---------------------------------------------------|
| clinical_rule_flags     | 20        | Rule engine clinical_agent (rule_flags)            |
| financial_anomaly       | 30        | XGBoost deviation → anomaly_score (atau z-score)   |
| behavioral_context      | 0         | Isolation Forest/provider context, supporting only |
| similarity_fraud        | 20        | Relasi repeat, cloning, atau pemecahan klaim       |
| evidence_support        | 15        | Keluarga evidence deterministik, bukan output LLM |

Rincian clinical (maksimal 20; tariff deviation berada di reimbursement evidence):
  - severity_proc_mismatch         : +5
  - severity_med_mismatch          : +3
  - los_outlier                    : +2
  - upcoding_risk_diag             : +4
"""
from backend.app.models.schemas import (
    ClinicalAssessment,
    EvidenceItem,
    FinancialAssessment,
    FraudAssessment,
    ReviewSynthesis,
    RiskScore,
)
from backend.app.core.human_language import humanize_rule, humanize_signal

CLINICAL_FLAG_WEIGHTS = {
    "tariff_deviation_high": 6.0,
    "tariff_deviation_extreme": 10.0,
    "severity_proc_mismatch": 5.0,
    "severity_med_mismatch": 3.0,
    "los_outlier": 2.0,
    "upcoding_risk_diag": 4.0,
    "unsupported_high_risk_proc": 8.0,
}


def _deterministic_signal_sources(clinical, financial, fraud) -> int:
    """Count independent evidence sources without consulting the review LLM."""
    clinical_signal = any(
        flag not in {"tariff_deviation_high", "tariff_deviation_extreme"}
        for flag in clinical.rule_flags
    )
    financial_signal = financial.anomaly_score > 0.4 or financial.deviation_pct > 30
    fraud_signal = any((
        fraud.exact_duplicate,
        fraud.repeat_billing_flag,
        fraud.cloning_flag,
        fraud.unbundling_flag,
    ))
    return sum((clinical_signal, financial_signal, fraud_signal))


def _evidence_items(clinical, financial, fraud) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for flag in clinical.rule_flags:
        family = (
            "reimbursement_benchmark"
            if flag in {"tariff_deviation_high", "tariff_deviation_extreme"}
            else "clinical_rule"
        )
        items.append(EvidenceItem(
            evidence_id=f"{family}:{flag}",
            source_family=family,
            signal_type=flag,
            value=clinical.tariff_deviation_pct if flag.startswith("tariff_") else True,
            explanation=f"Temuan berdasarkan aturan pemeriksaan: {humanize_rule(flag)}.",
        ))

    if financial.anomaly_score > 0.4 or financial.deviation_pct > 30:
        items.append(EvidenceItem(
            evidence_id="reimbursement_benchmark:benchmark_deviation",
            source_family="reimbursement_benchmark",
            signal_type="benchmark_deviation",
            value=financial.deviation_pct,
            explanation=financial.evidence_text or "Deviasi terhadap reimbursement benchmark.",
        ))

    for signal_type, active in (
        ("exact_duplicate", fraud.exact_duplicate),
        ("repeat_billing", fraud.repeat_billing_flag),
        ("cloning", fraud.cloning_flag),
        ("unbundling", fraud.unbundling_flag),
    ):
        if active:
            tier_note = (
                " Bukti exact duplicate menetapkan tier minimum High."
                if signal_type == "exact_duplicate"
                else " Bukti relasional kuat menetapkan tier minimum Medium."
                if signal_type in {"repeat_billing", "cloning"}
                else ""
            )
            items.append(EvidenceItem(
                evidence_id=f"relational_pattern:{signal_type}",
                source_family="relational_pattern",
                signal_type=signal_type,
                value=True,
                explanation=f"Temuan pola klaim: {humanize_signal(signal_type)}.{tier_note}",
            ))

    if fraud.is_isolation_forest_outlier or fraud.graph_cluster_anomaly_score > 0.5:
        items.append(EvidenceItem(
            evidence_id="behavioral_context:behavioral_context",
            source_family="behavioral_context",
            signal_type="behavioral_context",
            value=max(fraud.isolation_forest_score, fraud.graph_cluster_anomaly_score),
            explanation="Pola ini menjadi catatan tambahan dan bukan dasar penilaian yang berdiri sendiri.",
        ))
    return items


def calculate_risk_score(
    clinical: ClinicalAssessment,
    financial: FinancialAssessment,
    fraud: FraudAssessment,
    review: ReviewSynthesis,
) -> RiskScore:
    score = 0.0
    breakdown: dict[str, float] = {}

    # 1. Clinical consistency — tariff deviation belongs to reimbursement.
    clin_score = 0.0
    for flag, weight in CLINICAL_FLAG_WEIGHTS.items():
        if flag in {"tariff_deviation_high", "tariff_deviation_extreme"}:
            continue
        if flag in clinical.rule_flags:
            clin_score += weight
    clin_score = min(20.0, clin_score)
    score += clin_score
    breakdown["clinical_rule_flags"] = round(clin_score, 1)

    # 2. Financial — anomaly_score dari model ML (XGBoost/z-score), bukan LLM
    fin_score = min(30.0, financial.anomaly_score * 30.0)
    score += fin_score
    breakdown["financial_anomaly"] = round(fin_score, 1)

    # 3. Behavioral context is visible evidence, not an independent score yet.
    breakdown["isolation_forest_anomaly"] = 0.0

    # 4. Similarity / repeat billing / cloning (max 20)
    # Prinsip: kemiripan pola penyakit yang wajar (antar-faskes berbeda) BUKAN sinyal fraud —
    # hanya repeat billing, cloning, atau pemecahan klaim yang berbobot penuh.
    if fraud.exact_duplicate or fraud.unbundling_flag or fraud.repeat_billing_flag:
        sim_score = 20.0
    elif fraud.cloning_flag:
        sim_score = min(20.0, fraud.similarity_max_score * 20.0)
    else:
        sim_score = 0.0
    score += sim_score
    breakdown["similarity_fraud"] = round(sim_score, 1)

    # 5. Evidence support (max 15), derived from deterministic families only.
    source_count = _deterministic_signal_sources(clinical, financial, fraud)
    evidence_support = 15.0 if source_count >= 3 else 10.0 if source_count == 2 else 5.0 if source_count == 1 else 0.0
    score += evidence_support
    breakdown["evidence_support"] = round(evidence_support, 1)

    total = min(85.0, score)

    tier = "low"
    if total >= 60:
        tier = "high"
    elif total >= 25:
        tier = "medium"

    if fraud.exact_duplicate:
        tier = "high"
    elif fraud.repeat_billing_flag or fraud.cloning_flag:
        if tier == "low":
            tier = "medium"

    return RiskScore(
        total_score=round(total, 1),
        max_score=85,
        breakdown=breakdown,
        priority_tier=tier,
        evidence=_evidence_items(clinical, financial, fraud),
    )
