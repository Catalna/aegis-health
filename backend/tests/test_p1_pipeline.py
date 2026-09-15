import asyncio
import subprocess
import sys

from backend.app.models.schemas import FinancialAssessment
from backend.app.data.synthetic_generator import generate_cloning_case
from backend.app.evaluation import pipeline
from conftest import make_claim


async def _fake_financial(claim):
    return FinancialAssessment(
        claim_id=claim.claim_id,
        predicted_cost_range=(1_000_000, 1_200_000),
        actual_cost=claim.cost_claimed,
        deviation_pct=0.0,
        shap_top_features=[],
        anomaly_score=0.0,
        evidence_text="Evaluation benchmark.",
        method="zscore_peer_fallback",
    )


def test_pipeline_scores_without_llm_database_or_vector_store(monkeypatch):
    monkeypatch.setattr(pipeline, "analyze_financial", _fake_financial)
    monkeypatch.setattr(pipeline, "_load_isolation_model", lambda: None)

    claim = make_claim(claim_id="P1-NORMAL")
    result = asyncio.run(pipeline.score_claims([claim.model_dump(mode="json")]))[0]

    assert result.claim_id == "P1-NORMAL"
    assert result.score == 0.0
    assert result.breakdown["isolation_forest_anomaly"] == 0.0
    assert result.method == "zscore_peer_fallback"


def test_evaluation_pipeline_does_not_load_embedding_model():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import backend.app.evaluation.runner; print('sentence_transformers' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "False"


def test_similarity_module_defers_huggingface_model_load():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import backend.app.ml.similarity; print('sentence_transformers' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == "False"


def test_pipeline_is_reproducible_and_detects_in_memory_cloning(monkeypatch):
    monkeypatch.setattr(pipeline, "analyze_financial", _fake_financial)
    monkeypatch.setattr(pipeline, "_load_isolation_model", lambda: None)
    first, second = generate_cloning_case("P1-CLN-A", "P1-CLN-B", "FAC-P1")

    results_a = asyncio.run(pipeline.score_claims([first, second]))
    results_b = asyncio.run(pipeline.score_claims([first, second]))

    assert [r.score for r in results_a] == [r.score for r in results_b]
    assert any(r.breakdown["similarity_fraud"] > 0 for r in results_a)
    assert all(r.breakdown == s.breakdown for r, s in zip(results_a, results_b))


def test_behavioral_context_is_candidate_only(monkeypatch):
    monkeypatch.setattr(pipeline, "analyze_financial", _fake_financial)

    class OutlierModel:
        def decision_function(self, features):
            return [-0.25]

        def predict(self, features):
            return [-1]

    monkeypatch.setattr(pipeline, "_load_isolation_model", lambda: OutlierModel())
    claim = make_claim(claim_id="P1-BEHAVIOR")
    raw = [claim.model_dump(mode="json")]

    core = asyncio.run(pipeline.score_claims(raw, include_behavioral_context=False))[0]
    candidate = asyncio.run(pipeline.score_claims(raw, include_behavioral_context=True))[0]

    assert core.score == 0.0
    assert candidate.score == 15.0
    assert candidate.breakdown["behavioral_context_candidate"] == 15.0
