"""Test Fraud Agent components + Similarity (tanpa DB/LanceDB live)."""
import pytest

from backend.app.ml.similarity import compute_jaccard_similarity, _parse_text_content, generate_claim_text
from backend.app.models.schemas import SimilarClaim, FraudAssessment
from conftest import make_claim


# ---------------------------------------------------------------------------
# Jaccard — cloning jelas >0.9, klaim beda <0.9
# ---------------------------------------------------------------------------

def test_jaccard_identical_claims_above_09():
    c1 = {"diagnosis_primary": "I21.9", "diagnosis_secondary": ["I10"], "procedure_codes": ["36.10", "89.52"]}
    c2 = {"diagnosis_primary": "I21.9", "diagnosis_secondary": ["I10"], "procedure_codes": ["36.10", "89.52"]}
    assert compute_jaccard_similarity(c1, c2) > 0.9


def test_jaccard_different_claims_low():
    c1 = {"diagnosis_primary": "I21.9", "diagnosis_secondary": ["I10"], "procedure_codes": ["36.10"]}
    c2 = {"diagnosis_primary": "O80", "diagnosis_secondary": [], "procedure_codes": ["72.0"]}
    assert compute_jaccard_similarity(c1, c2) < 0.5


def test_jaccard_empty_sets_zero():
    assert compute_jaccard_similarity({}, {}) == 0.0


# ---------------------------------------------------------------------------
# Text content round-trip (untuk rekonstruksi klaim historis dari LanceDB)
# ---------------------------------------------------------------------------

def test_claim_text_roundtrip():
    claim = {
        "diagnosis_primary": "S72.0",
        "diagnosis_secondary": ["I10"],
        "procedure_codes": ["81.51"],
        "medication": [{"name": "Enoxaparin", "quantity": 10}],
    }
    text = generate_claim_text(claim)
    parsed = _parse_text_content(text)
    assert parsed["diagnosis_primary"] == "S72.0"
    assert "I10" in parsed["diagnosis_secondary"]
    assert "81.51" in parsed["procedure_codes"]


# ---------------------------------------------------------------------------
# SimilarClaim schema — panel frontend harus terisi (audit finding 8.2)
# ---------------------------------------------------------------------------

def test_similar_claim_schema_complete():
    sc = SimilarClaim(
        claim_id="CLM-A", similarity=0.97, jaccard=0.95, provider_id="FAC-1",
        patient_id="PAT-9", diagnosis_primary="I21.9", cost_claimed=24_000_000, same_patient=False,
    )
    fraud = FraudAssessment(
        claim_id="X", similarity_max_score=0.97, repeat_billing_flag=False,
        graph_cluster_anomaly_score=0.1, evidence_text="", similar_claims=[sc],
    )
    dumped = fraud.model_dump()
    assert len(dumped["similar_claims"]) == 1
    assert dumped["similar_claims"][0]["diagnosis_primary"] == "I21.9"


# ---------------------------------------------------------------------------
# Repeat billing DB check — logika pencocokan pasien+prosedur+tanggal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repeat_billing_check_no_procedures():
    from backend.app.agents.fraud_agent import _check_repeat_billing_db
    claim = make_claim(procedure_codes=[])
    result = await _check_repeat_billing_db(claim)
    assert result is None  # tanpa prosedur, tidak mungkin repeat billing
