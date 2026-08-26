"""Test Financial Engine — fallback z-score (bukan anomaly maksimum semu)."""
import pytest

from backend.app.agents.financial_engine import _zscore_fallback, analyze_financial, get_financial_model
from conftest import make_claim


def test_zscore_fallback_never_max_score_for_normal_cost():
    """Klaim biaya wajar + model gagal → skor rendah, BUKAN 1.0 (audit finding 2.3)."""
    claim = make_claim(cost_claimed=24_000_000)  # sesuai peer AMI
    result = _zscore_fallback(claim, "mock model error")
    assert result.method == "zscore_peer_fallback"
    assert result.anomaly_score < 0.3
    assert "fallback" in result.evidence_text.lower()


def test_zscore_fallback_high_score_for_inflated_cost():
    """Klaim 3x peer → z-score tinggi."""
    claim = make_claim(cost_claimed=72_000_000)  # 3x peer AMI
    result = _zscore_fallback(claim, "mock model error")
    assert result.anomaly_score > 0.5
    assert result.deviation_pct > 150


def test_zscore_fallback_predicted_range_sane():
    claim = make_claim(cost_claimed=24_000_000)
    result = _zscore_fallback(claim, "mock")
    lo, hi = result.predicted_cost_range
    assert 0 < lo < hi
    assert abs(hi - 24_000_000 * 1.15) < 1  # peer AMI 24jt ±15%


@pytest.mark.asyncio
async def test_analyze_financial_with_model_or_fallback(normal_claim):
    """Dengan atau tanpa model, hasil selalu ada angka (tidak pernah no-score)."""
    result = await analyze_financial(normal_claim)
    assert result.actual_cost == normal_claim.cost_claimed
    assert 0.0 <= result.anomaly_score <= 1.0
    assert result.evidence_text  # selalu ada evidence
    assert result.method in ("xgboost_model", "zscore_peer_fallback")


@pytest.mark.asyncio
async def test_analyze_financial_inflated_claim_scores_higher():
    normal = await analyze_financial(make_claim(cost_claimed=24_000_000))
    inflated = await analyze_financial(make_claim(claim_id="X2", cost_claimed=90_000_000))
    assert inflated.anomaly_score >= normal.anomaly_score


def test_model_loads_if_available():
    """Model hasil training harus bisa dimuat (kalau file ada)."""
    import os
    path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "models_trained", "xgboost_regressor.json"))
    if os.path.exists(path):
        model, explainer = get_financial_model()
        assert model is not None
