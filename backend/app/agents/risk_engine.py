"""
Risk Score Engine — fungsi scoring deterministik (AGENTS.md Section 6).
TIDAK ADA input LLM yang mengubah skor. Bobot terdokumentasi (MODELS.md Section 4):

| Komponen                | Bobot maks | Sumber angka (wajib traceable)                    |
|-------------------------|-----------|---------------------------------------------------|
| clinical_rule_flags     | 20        | Rule engine clinical_agent (rule_flags)            |
| financial_anomaly       | 30        | XGBoost deviation → anomaly_score (atau z-score)   |
| isolation_forest        | 15        | Isolation Forest normalized score                  |
| similarity_fraud        | 20        | Relasi repeat, cloning, atau pemecahan klaim       |
| provider_network        | (dalam IF)| graph metrics precomputed → memodulasi skor IF     |
| synthesis_confidence    | 15        | Jumlah sumber sinyal deterministik, bukan output LLM |

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
    "unsupported_high_risk_proc": 8.0,
}


def _deterministic_signal_sources(clinical, financial, fraud) -> int:
    """Count independent evidence sources without consulting the review LLM."""
    clinical_signal = bool(clinical.rule_flags)
    financial_signal = financial.anomaly_score > 0.4 or financial.deviation_pct > 30
    fraud_signal = any((
        fraud.repeat_billing_flag,
        fraud.cloning_flag,
        fraud.unbundling_flag,
        fraud.is_isolation_forest_outlier,
        fraud.graph_cluster_anomaly_score > 0.5,
    ))
    return sum((clinical_signal, financial_signal, fraud_signal))


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
    # hanya repeat billing, cloning, atau pemecahan klaim yang berbobot penuh.
    if fraud.unbundling_flag:
        sim_score = 20.0
    elif fraud.repeat_billing_flag:
        sim_score = 20.0
    elif fraud.cloning_flag:
        sim_score = min(20.0, fraud.similarity_max_score * 20.0)
    else:
        sim_score = 0.0
    score += sim_score
    breakdown["similarity_fraud"] = round(sim_score, 1)

    # 5. Evidence support (max 15). The review LLM can explain the result but
    # cannot change the numeric score.
    source_count = _deterministic_signal_sources(clinical, financial, fraud)
    strong_single_signal = fraud.repeat_billing_flag or fraud.cloning_flag or fraud.unbundling_flag
    review_score = 15.0 if source_count >= 2 or strong_single_signal else 5.0 if source_count == 1 else 0.0
    score += review_score
    breakdown["synthesis_confidence"] = round(review_score, 1)

    total = min(100.0, score)

    tier = "low"
    if total >= 60:
        tier = "high"
    elif total >= 25:
        tier = "medium"

    return RiskScore(total_score=round(total, 1), breakdown=breakdown, priority_tier=tier)
