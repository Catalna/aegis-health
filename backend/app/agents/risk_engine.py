"""
Risk Score Engine — fungsi scoring deterministik (AGENTS.md Section 6).
TIDAK ADA input LLM yang mengubah skor. Bobot terdokumentasi (MODELS.md Section 4):

| Komponen                | Bobot maks | Sumber angka (wajib traceable)                    |
|-------------------------|-----------|---------------------------------------------------|
| clinical_rule_flags     | 20        | Rule engine clinical_agent (rule_flags)            |
| financial_anomaly       | 30        | XGBoost deviation → anomaly_score (atau z-score)   |
| isolation_forest        | 15        | Isolation Forest normalized score                  |
| similarity_fraud        | 20        | LanceDB cosine + repeat billing flag               |
| provider_network        | (dalam IF)| graph metrics precomputed → memodulasi skor IF     |
| synthesis_confidence    | 15        | Review evidence_level (rule-count fallback/LLM)    |

Rincian clinical (total 20):
  - tariff_deviation_high  (>50%)  : +6
  - tariff_deviation_extreme(>100%): +10 (menggantikan +6)
  - severity_proc_mismatch         : +5
  - severity_med_mismatch          : +3
  - los_outlier                    : +2
  - upcoding_risk_diag             : +4
"""
from backend.app.models.schemas import ClinicalAssessment, FinancialAssessment, FraudAssessment, ReviewSynthesis, RiskScore

CLINICAL_FLAG_WEIGHTS = {
    "tariff_deviation_high": 6.0,
    "tariff_deviation_extreme": 10.0,
    "severity_proc_mismatch": 5.0,
    "severity_med_mismatch": 3.0,
    "los_outlier": 2.0,
    "upcoding_risk_diag": 4.0,
}


def calculate_risk_score(
    clinical: ClinicalAssessment,
    financial: FinancialAssessment,
    fraud: FraudAssessment,
    review: ReviewSynthesis,
) -> RiskScore:
    score = 0.0
    breakdown: dict[str, float] = {}

    # 1. Clinical — HANYA dari rule flags (bukan plausibility LLM)
    clin_score = 0.0
    if "tariff_deviation_extreme" in clinical.rule_flags:
        clin_score += CLINICAL_FLAG_WEIGHTS["tariff_deviation_extreme"]
    elif "tariff_deviation_high" in clinical.rule_flags:
        clin_score += CLINICAL_FLAG_WEIGHTS["tariff_deviation_high"]
    for flag, weight in CLINICAL_FLAG_WEIGHTS.items():
        if flag in ("tariff_deviation_high", "tariff_deviation_extreme"):
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

    # 3. Isolation Forest (max 15) — dimodulasi skor jaringan provider
    provider_factor = 0.7 + (0.3 * min(1.0, fraud.graph_cluster_anomaly_score))
    if_score = min(15.0, fraud.isolation_forest_score * 15.0 * provider_factor)
    score += if_score
    breakdown["isolation_forest_anomaly"] = round(if_score, 1)

    # 4. Similarity / repeat billing / cloning (max 20)
    # Prinsip: kemiripan pola penyakit yang wajar (antar-faskes berbeda) BUKAN sinyal fraud —
    # hanya repeat billing (pasien sama) atau cloning (faskes sama + pasien beda) yang berbobot penuh.
    if fraud.repeat_billing_flag:
        sim_score = 20.0
    elif fraud.cloning_flag:
        sim_score = min(20.0, fraud.similarity_max_score * 20.0)
    else:
        sim_score = min(8.0, fraud.similarity_max_score * 8.0)  # kemiripan wajar → bobot kecil
    score += sim_score
    breakdown["similarity_fraud"] = round(sim_score, 1)

    # 5. Review synthesis (max 15)
    review_score = {"strong_multi_signal": 15.0, "single_signal": 5.0, "weak": 0.0}.get(
        review.evidence_level, 0.0
    )
    score += review_score
    breakdown["synthesis_confidence"] = round(review_score, 1)

    total = min(100.0, score)

    tier = "low"
    if total >= 75:
        tier = "high"
    elif total >= 40:
        tier = "medium"

    return RiskScore(total_score=round(total, 1), breakdown=breakdown, priority_tier=tier)
