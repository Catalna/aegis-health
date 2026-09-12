"""Offline deterministic adapter for P1 risk-score evaluation."""

import os
import time
from dataclasses import dataclass
from datetime import date

import joblib
import numpy as np

from backend.app.agents.clinical_agent import _plausibility_from_flags, _rule_flags
from backend.app.agents.financial_engine import analyze_financial
from backend.app.agents.risk_engine import calculate_risk_score
from backend.app.data.ina_cbg_rules import DIAGNOSIS_TO_CBG_MAPPING, calculate_expected_tariff
from backend.app.ml.feature_engineering import PEER_BASELINE, extract_features
from backend.app.ml.similarity import (
    RELATIONSHIP_WINDOW_DAYS,
    composite_similarity,
    compute_jaccard_similarity,
    cost_proximity,
    is_investigation_candidate,
)
from backend.app.models.schemas import (
    ClaimInput,
    ClinicalAssessment,
    FraudAssessment,
    ReviewSynthesis,
    SimilarClaim,
)


@dataclass(frozen=True)
class EvaluationResult:
    claim_id: str
    label: int
    anomaly_type: str
    score: float
    priority_tier: str
    breakdown: dict[str, float]
    method: str
    latency_ms: float


_MODELS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models_trained"))
_isolation_model = None
_isolation_loaded = False


def _load_isolation_model():
    global _isolation_model, _isolation_loaded
    if not _isolation_loaded:
        path = os.path.join(_MODELS_DIR, "isolation_forest.pkl")
        _isolation_model = joblib.load(path) if os.path.exists(path) else None
        _isolation_loaded = True
    return _isolation_model


def _deterministic_clinical(claim: ClaimInput) -> ClinicalAssessment:
    base = claim.diagnosis_primary.split(".")[0]
    known_diag = base in DIAGNOSIS_TO_CBG_MAPPING
    lookup = calculate_expected_tariff(claim.diagnosis_primary, claim.procedure_codes, claim.severity_level)
    tariff_deviation = None
    grouper_result = None
    if lookup:
        cbg_code, cbg_name, expected_tariff = lookup
        from backend.app.models.schemas import CBGLookupResult
        grouper_result = CBGLookupResult(cbg_code=cbg_code, cbg_name=cbg_name, base_tariff=expected_tariff)
        tariff_deviation = ((claim.cost_claimed - expected_tariff) / expected_tariff) * 100 if expected_tariff else None
    flags = _rule_flags(claim, tariff_deviation, known_diag)
    plausibility, confidence = _plausibility_from_flags(flags)
    return ClinicalAssessment(
        claim_id=claim.claim_id,
        grouper_result=grouper_result,
        tariff_deviation_pct=tariff_deviation,
        compatibility_status="match_table" if known_diag else "no_data",
        plausibility=plausibility if known_diag else "n/a",
        evidence_text="P1 deterministic rule assessment.",
        confidence_level=confidence if known_diag else "low",
        evidence_source="rule_engine",
        rule_flags=flags,
    )


def _days_apart(left: dict, right: dict) -> int | None:
    left_date = left.get("admission_date")
    right_date = right.get("admission_date")
    if not left_date or not right_date:
        return None
    try:
        return abs((date.fromisoformat(str(left_date)[:10]) - date.fromisoformat(str(right_date)[:10])).days)
    except ValueError:
        return None


def _relation_candidates(claim: dict, population: list[dict]) -> list[dict]:
    candidates = []
    for other in population:
        if other.get("claim_id") == claim.get("claim_id"):
            continue
        days = _days_apart(claim, other)
        code_similarity = compute_jaccard_similarity(claim, other)
        cost_score = cost_proximity(float(claim.get("cost_claimed", 0)), float(other.get("cost_claimed", 0)))
        same_provider = bool(claim.get("provider_id")) and claim.get("provider_id") == other.get("provider_id")
        same_patient = bool(claim.get("patient_id")) and claim.get("patient_id") == other.get("patient_id")
        if not is_investigation_candidate(code_similarity, cost_score, same_provider, same_patient, days):
            continue
        candidates.append({
            "claim_id": other["claim_id"],
            "similarity": composite_similarity(code_similarity, cost_score, same_provider, same_patient, days),
            "code_similarity": code_similarity,
            "cost_proximity": cost_score,
            "same_provider": same_provider,
            "same_patient": same_patient,
            "days_apart": days,
            "provider_id": other.get("provider_id", ""),
            "patient_id": other.get("patient_id", ""),
            "diagnosis_primary": other.get("diagnosis_primary", ""),
            "cost_claimed": float(other.get("cost_claimed", 0)),
        })
    return sorted(candidates, key=lambda item: (-item["similarity"], item["claim_id"]))


def _fraud_assessment(claim: dict, population: list[dict], include_behavioral_context: bool) -> FraudAssessment:
    candidates = _relation_candidates(claim, population)
    cloning = any(not item["same_patient"] and item["same_provider"] for item in candidates)
    repeat = any(item["same_patient"] for item in candidates)
    base = claim.get("diagnosis_primary", "").split(".")[0]
    peer_baseline = PEER_BASELINE.get(base, 5_000_000)
    related = [item for item in candidates if item["same_patient"] and item["same_provider"]]
    related_costs = [item["cost_claimed"] for item in related]
    current_cost = float(claim.get("cost_claimed", 0))
    unbundling = len(related_costs) > 0 and all(cost < peer_baseline * 0.8 for cost in [current_cost, *related_costs])
    unbundling = unbundling and peer_baseline * 0.75 <= current_cost + sum(related_costs) <= peer_baseline * 1.5

    isolation_score = 0.0
    is_outlier = False
    model = _load_isolation_model() if include_behavioral_context else None
    if model is not None:
        features = np.array([extract_features(claim)])
        raw_score = model.decision_function(features)[0]
        is_outlier = model.predict(features)[0] == -1
        isolation_score = float(max(0.0, min(1.0, 0.5 - (raw_score * 2))))

    similar_claims = [SimilarClaim(**item) for item in candidates[:3]]
    return FraudAssessment(
        claim_id=claim["claim_id"],
        similarity_max_score=candidates[0]["similarity"] if candidates else 0.0,
        similarity_matched_claim_id=candidates[0]["claim_id"] if candidates else None,
        repeat_billing_flag=repeat,
        repeat_billing_matched_claim_id=next((item["claim_id"] for item in candidates if item["same_patient"]), None),
        cloning_flag=cloning,
        unbundling_flag=unbundling,
        unbundling_matched_claim_ids=[item["claim_id"] for item in related] if unbundling else [],
        graph_cluster_anomaly_score=0.0,
        isolation_forest_score=isolation_score,
        is_isolation_forest_outlier=is_outlier,
        evidence_text="P1 in-memory relational assessment.",
        similar_claims=similar_claims,
    )


async def score_claims(
    claim_dicts: list[dict],
    include_behavioral_context: bool = True,
) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for raw_claim in claim_dicts:
        started = time.perf_counter()
        claim = ClaimInput.model_validate(raw_claim)
        clinical = _deterministic_clinical(claim)
        financial = await analyze_financial(claim)
        fraud = _fraud_assessment(raw_claim, claim_dicts, include_behavioral_context)
        review = ReviewSynthesis(
            claim_id=claim.claim_id,
            evidence_level="strong_multi_signal" if any((fraud.repeat_billing_flag, fraud.cloning_flag, fraud.unbundling_flag)) else "weak",
            corroborating_signals=[],
            reasoning_narrative="P1 rule fallback.",
            reasoning_source="rule_fallback",
            model_used=None,
        )
        risk = calculate_risk_score(clinical, financial, fraud, review)
        results.append(EvaluationResult(
            claim_id=claim.claim_id,
            label=int(bool(raw_claim.get("is_synthetic_anomaly", False))),
            anomaly_type=raw_claim.get("anomaly_type", "none"),
            score=risk.total_score,
            priority_tier=risk.priority_tier,
            breakdown=risk.breakdown,
            method=financial.method,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        ))
    return results
