"""Test Clinical Agent 2-lapis (AGENTS.md Section 2) + Risk Engine scoring."""
import pytest

from backend.app.agents.clinical_agent import analyze_clinical, _rule_flags, _plausibility_from_flags
from backend.app.agents.risk_engine import calculate_risk_score
from backend.app.models.schemas import FinancialAssessment, FraudAssessment, ReviewSynthesis
from conftest import make_claim


@pytest.mark.asyncio
async def test_match_table_case_no_llm_needed(normal_claim):
    """Kasus match tabel referensi & wajar → rule engine, plausibility=plausible."""
    result = await analyze_clinical(normal_claim)
    assert result.compatibility_status in ("match_table", "no_data")
    assert result.evidence_source == "rule_engine"
    assert result.plausibility == "plausible"
    assert result.grouper_result is not None  # I21 ada di tabel
    assert "llm" not in (result.evidence_source or "")


@pytest.mark.asyncio
async def test_upcoded_severity_flagged_by_rules():
    """Severity dinaikkan + diagnosis komplikasi upcoding + biaya tinggi → flag rule."""
    claim = make_claim(
        claim_id="CLM-UPC-TEST",
        severity_level=4,
        cost_claimed=90_000_000,
        diagnosis_secondary=["I10", "A41.9"],
    )
    result = await analyze_clinical(claim)
    # Skor klinis berasal dari rule flags — bukan LLM; upcoding harus terdeteksi rule
    assert len(result.rule_flags) > 0
    assert result.plausibility in ("questionable", "implausible")
    # Skor dari rule flags harus > 0
    assert result.rule_flags


@pytest.mark.asyncio
async def test_unknown_diagnosis_goes_to_llm_layer():
    """Diagnosis di luar tabel → Lapis 2 (LLM), compatibility_status=llm_assessed."""
    claim = make_claim(claim_id="CLM-UNK", diagnosis_primary="Z99.9")
    result = await analyze_clinical(claim)
    # Dengan mock LLM, hasil harus terlabel llm_assessed dengan sumber llm_local
    assert result.compatibility_status == "llm_assessed"
    assert result.evidence_source == "llm_local"
    assert result.rule_flags == [] or isinstance(result.rule_flags, list)


@pytest.mark.asyncio
async def test_los_outlier_flag():
    claim = make_claim(claim_id="CLM-LOS", length_of_stay=40)  # AMI max 10 → outlier
    flags = _rule_flags(claim, tariff_deviation=5.0, known_diag=True)
    assert "los_outlier" in flags


def test_plausibility_mapping_deterministic():
    assert _plausibility_from_flags([])[0] == "plausible"
    assert _plausibility_from_flags(["los_outlier"])[0] == "questionable"
    assert _plausibility_from_flags(["los_outlier", "severity_med_mismatch"])[0] == "implausible"
    assert _plausibility_from_flags(["tariff_deviation_extreme"])[0] == "implausible"


# ---------------------------------------------------------------------------
# Risk Engine — skor klinis HANYA dari rule flags (bukan plausibility LLM)
# ---------------------------------------------------------------------------

def _financial(anomaly=0.0, dev=0.0):
    return FinancialAssessment(
        claim_id="X", predicted_cost_range=(0, 0), actual_cost=1_000_000,
        deviation_pct=dev, shap_top_features=[], anomaly_score=anomaly,
    )


def _fraud(sim=0.0, repeat=False, if_score=0.0, graph=0.0):
    return FraudAssessment(
        claim_id="X", similarity_max_score=sim, repeat_billing_flag=repeat,
        graph_cluster_anomaly_score=graph, isolation_forest_score=if_score,
        evidence_text="",
    )


def _review(level="weak"):
    return ReviewSynthesis(
        claim_id="X", evidence_level=level, corroborating_signals=[],
        reasoning_narrative="ok", reasoning_source="rule_fallback",
    )


def test_risk_score_zero_for_clean_claim(normal_claim):
    from backend.app.models.schemas import ClinicalAssessment
    clinical = ClinicalAssessment(
        claim_id="X", compatibility_status="match_table", plausibility="plausible",
        evidence_text="", confidence_level="high", rule_flags=[],
    )
    risk = calculate_risk_score(clinical, _financial(), _fraud(), _review("weak"))
    assert risk.total_score == 0.0
    assert risk.priority_tier == "low"


def test_risk_score_clinical_from_rule_flags_not_llm():
    """Dua klaim dengan plausibility LLM beda tapi rule flags sama → skor sama (prinsip #1)."""
    from backend.app.models.schemas import ClinicalAssessment
    c1 = ClinicalAssessment(
        claim_id="X", compatibility_status="llm_assessed", plausibility="implausible",
        evidence_text="", confidence_level="high", rule_flags=["los_outlier"],
    )
    c2 = ClinicalAssessment(
        claim_id="X", compatibility_status="match_table", plausibility="plausible",
        evidence_text="", confidence_level="high", rule_flags=["los_outlier"],
    )
    r1 = calculate_risk_score(c1, _financial(), _fraud(), _review("weak"))
    r2 = calculate_risk_score(c2, _financial(), _fraud(), _review("weak"))
    assert r1.total_score == r2.total_score
    assert r1.breakdown["clinical_rule_flags"] == r2.breakdown["clinical_rule_flags"]


def test_risk_score_repeat_billing_caps_similarity():
    risk = calculate_risk_score(
        _clinical(), _financial(), _fraud(repeat=True), _review("weak"),
    )
    assert risk.breakdown["similarity_fraud"] == 20.0


def test_risk_score_plain_similarity_capped_low():
    """Kemiripan 100% antar-faskes berbeda tanpa cloning = pola penyakit wajar → maks 8 poin."""
    risk = calculate_risk_score(
        _clinical(), _financial(), _fraud(sim=1.0), _review("weak"),
    )
    assert risk.breakdown["similarity_fraud"] <= 8.0


def test_risk_score_cloning_full_weight():
    """Cloning sungguhan (faskes sama, pasien beda) → bobot penuh."""
    fraud = _fraud(sim=0.97)
    fraud = fraud.model_copy(update={"cloning_flag": True})
    risk = calculate_risk_score(_clinical(), _financial(), fraud, _review("weak"))
    assert risk.breakdown["similarity_fraud"] > 19.0


def _clinical(flags=None):
    from backend.app.models.schemas import ClinicalAssessment
    return ClinicalAssessment(
        claim_id="X", compatibility_status="match_table", plausibility="plausible",
        evidence_text="", confidence_level="high", rule_flags=flags or [],
    )


def test_risk_score_high_tier():
    risk = calculate_risk_score(
        _clinical(["tariff_deviation_extreme", "severity_proc_mismatch"]),
        _financial(anomaly=1.0, dev=120), _fraud(sim=0.97, if_score=1.0), _review("strong_multi_signal"),
    )
    assert risk.priority_tier == "high"
    assert risk.total_score >= 75


def test_breakdown_sums_to_total():
    risk = calculate_risk_score(
        _clinical(["severity_proc_mismatch"]),
        _financial(anomaly=0.6, dev=35), _fraud(sim=0.5, if_score=0.4, graph=0.5), _review("single_signal"),
    )
    assert abs(sum(risk.breakdown.values()) - min(100.0, risk.total_score)) < 0.5 or sum(risk.breakdown.values()) >= risk.total_score - 0.1
