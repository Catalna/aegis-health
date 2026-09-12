"""Test Review Agent fallback + Explanation Agent validasi angka (AGENTS.md Section 5 & 7)."""
import pytest

from backend.app.models.schemas import (
    ClinicalAssessment, FinancialAssessment, FraudAssessment,
    EvidenceItem, ReviewSynthesis, RiskScore, ClaimExplanation,
)
from backend.app.agents.review_agent import synthesize_review, compute_rule_signals, deterministic_source_count
from backend.app.agents.explanation_agent import (
    _validate_narrative, _normalize_tokens, _template_explanation, generate_explanation,
    TIER_TO_ACTION, build_priority_reason,
)
from conftest import make_claim


def _clinical(flags=None):
    return ClinicalAssessment(
        claim_id="X", compatibility_status="match_table", plausibility="plausible",
        evidence_text="ok", confidence_level="high", rule_flags=flags or [],
    )


def _financial(anomaly=0.0, dev=0.0):
    return FinancialAssessment(
        claim_id="X", predicted_cost_range=(1_000_000, 1_500_000), actual_cost=1_200_000,
        deviation_pct=dev, shap_top_features=[], anomaly_score=anomaly,
        evidence_text="deviasi +129.6%",
    )


def _fraud(sim=0.0, repeat=False):
    return FraudAssessment(
        claim_id="X", similarity_max_score=sim, repeat_billing_flag=repeat,
        graph_cluster_anomaly_score=0.1, isolation_forest_score=0.2,
        evidence_text="ok",
    )


def _review(level="weak"):
    return ReviewSynthesis(
        claim_id="X", evidence_level=level, corroborating_signals=[],
        reasoning_narrative="ok", reasoning_source="rule_fallback",
    )


# ---------------------------------------------------------------------------
# Review: rule signals + fallback
# ---------------------------------------------------------------------------

def test_rule_signals_3_strong():
    signals = compute_rule_signals(
        _clinical(["tariff_deviation_extreme", "severity_proc_mismatch"]),
        _financial(anomaly=0.9, dev=100), _fraud(repeat=True),
    )
    assert len(signals) >= 3


def test_rule_signals_weak_case():
    signals = compute_rule_signals(_clinical(), _financial(), _fraud(sim=0.3))
    assert len(signals) <= 1


def test_review_source_count_does_not_double_count_one_agent():
    assert deterministic_source_count(
        _clinical(["tariff_deviation_extreme", "severity_proc_mismatch"]),
        _financial(),
        _fraud(),
    ) == 1


@pytest.mark.asyncio
async def test_review_fallback_on_llm_error(monkeypatch):
    """LLM error → rule-count fallback: 3/3 sinyal → strong_multi_signal (AGENTS.md)."""
    async def boom(*a, **k):
        raise Exception("LLM down")
    import backend.app.agents.review_agent as ra
    monkeypatch.setattr(ra, "structured_completion", boom)
    monkeypatch.setattr(ra, "get_available_model", lambda *a: _async("mistral:7b"))

    from conftest import make_claim as mc
    review = await synthesize_review(
        mc(), _clinical(["tariff_deviation_extreme", "severity_proc_mismatch"]),
        _financial(anomaly=0.9, dev=100), _fraud(repeat=True),
    )
    assert review.evidence_level == "strong_multi_signal"
    assert review.reasoning_source == "rule_fallback"


async def _async(x):
    return x


@pytest.mark.asyncio
async def test_review_weak_case(monkeypatch):
    async def boom(*a, **k):
        raise Exception("LLM down")
    import backend.app.agents.review_agent as ra
    monkeypatch.setattr(ra, "structured_completion", boom)
    monkeypatch.setattr(ra, "get_available_model", lambda *a: _async("mistral:7b"))

    from conftest import make_claim as mc
    review = await synthesize_review(mc(), _clinical(), _financial(), _fraud(sim=0.3))
    assert review.evidence_level in ("weak", "single_signal")


@pytest.mark.asyncio
async def test_review_discards_unsupported_evidence_ids(monkeypatch):
    class FakeResp:
        evidence_level = "strong_multi_signal"
        evidence_ids = ["relational_pattern:phantom_billing"]
        corroborating_signals = ["Tindakan tidak terbukti"]
        reasoning_narrative = "Klaim memiliki phantom billing."

    async def fake_llm(*a, **k):
        return FakeResp()

    import backend.app.agents.review_agent as ra
    monkeypatch.setattr(ra, "structured_completion", fake_llm)
    monkeypatch.setattr(ra, "get_available_model", lambda *a: _async("mistral:7b"))

    review = await synthesize_review(make_claim(), _clinical(), _financial(), _fraud())

    assert review.evidence_ids == []
    assert review.corroborating_signals == []
    assert review.evidence_level == "weak"


# ---------------------------------------------------------------------------
# Explanation: validasi angka anti-halusinasi
# ---------------------------------------------------------------------------

def test_normalize_numbers_basic():
    nums = _normalize_tokens("Skor 77.4 dari 100, deviasi +129.6%, biaya Rp 1.769.964")
    assert 77.4 in [n for n in nums if abs(n - 77.4) < 0.01] or any(abs(n - 77.4) < 0.01 for n in nums)
    assert any(abs(n - 129.6) < 0.01 for n in nums)
    assert any(n == 1769964 for n in nums)


def test_validate_narrative_passes_with_correct_score():
    facts = {"score": 77.4, "deviation_pct": 129.6, "similarity_pct": None}
    errors = _validate_narrative(
        "Klaim ini mendapat skor 77.4 dari 100 dengan deviasi biaya 129.6%.",
        facts,
    )
    assert errors == []


def test_validate_narrative_passes_rounded_score():
    """Skor dibulatkan wajar (77 dari 77.4) tetap dianggap valid."""
    facts = {"score": 77.4, "deviation_pct": None, "similarity_pct": None}
    errors = _validate_narrative("Klaim ini mendapat skor 77 dari 100.", facts)
    assert errors == []


def test_validate_narrative_fails_wrong_score():
    facts = {"score": 77.4, "deviation_pct": None, "similarity_pct": None}
    errors = _validate_narrative("Klaim ini mendapat skor 45 dari 100.", facts)
    assert len(errors) > 0


def test_validate_narrative_fails_missing_deviation():
    facts = {"score": 77.4, "deviation_pct": 129.6, "similarity_pct": None}
    errors = _validate_narrative("Klaim ini mendapat skor 77 dari 100.", facts)
    assert any("deviasi" in e.lower() for e in errors)


def test_template_explanation_always_accurate():
    claim = make_claim()
    risk = RiskScore(total_score=77.4, breakdown={"financial_anomaly": 30.0, "clinical_rule_flags": 10.0}, priority_tier="high")
    explanation = _template_explanation(
        claim, _clinical(), _financial(anomaly=1.0, dev=129.6), _fraud(sim=0.73), _review("strong_multi_signal"), risk,
        facts={"score": 77.4, "deviation_pct": 129.6, "similarity_pct": 73.0, "actual_cost": claim.cost_claimed, "tier": "high"},
    )
    assert "77" in explanation.narrative_id
    assert explanation.recommended_action == "verify_immediately"
    assert explanation.qa_panel.is_this_fraud.startswith("Sistem ini tidak")
    # Validasi angka template harus lolos validasi sendiri
    facts = {"score": 77.4, "deviation_pct": 129.6, "similarity_pct": 73.0}
    assert not [e for e in _validate_narrative(explanation.narrative_id, facts) if "skor" in e.lower()]


@pytest.mark.asyncio
async def test_explanation_rejects_unsupported_evidence_id(monkeypatch):
    import backend.app.agents.explanation_agent as ea

    class FakeResp:
        narrative_id = "Klaim X mendapat skor 77 dari 100 dengan deviasi biaya 129.6%."
        ranked_reasons = ["Tindakan tidak terbukti"]
        why_top_priority = "Tindakan tidak terbukti"
        strongest_evidence = "Tindakan tidak terbukti"
        evidence_ids = ["relational_pattern:phantom_billing"]

    async def fake_llm(*a, **k):
        return FakeResp()

    monkeypatch.setattr(ea, "structured_completion", fake_llm)
    monkeypatch.setattr(ea, "get_available_model", lambda *a: _async("qwen2.5:7b"))

    risk = RiskScore(
        total_score=77.4,
        breakdown={"financial_anomaly": 30.0},
        priority_tier="high",
        evidence=[EvidenceItem(
            evidence_id="reimbursement_benchmark:benchmark_deviation",
            source_family="reimbursement_benchmark",
            signal_type="benchmark_deviation",
            value=129.6,
            explanation="Deviasi benchmark.",
        )],
    )
    explanation = await generate_explanation(
        make_claim(), _clinical(), _financial(anomaly=1.0, dev=129.6),
        _fraud(), _review("strong_multi_signal"), risk,
    )

    assert explanation.generated_by == "template_fallback"
    assert "tindakan tidak terbukti" not in explanation.narrative_id.lower()


@pytest.mark.asyncio
async def test_generate_explanation_action_from_tier_not_llm(monkeypatch):
    """recommended_action WAJIB mengikuti tier, meski LLM mengusulkan lain."""
    import backend.app.agents.explanation_agent as ea

    class FakeResp:
        narrative_id = "Klaim X mendapat skor 77 dari 100 dengan deviasi biaya 130%."
        ranked_reasons = ["deviasi 130%"]
        why_top_priority = "deviasi 130%"
        strongest_evidence = "deviasi 130%"
        evidence_ids = ["reimbursement_benchmark:benchmark_deviation"]

    async def fake_llm(*a, **k):
        return FakeResp()

    monkeypatch.setattr(ea, "structured_completion", fake_llm)
    monkeypatch.setattr(ea, "get_available_model", lambda *a: _async("qwen2.5:7b"))

    risk = RiskScore(
        total_score=77.4,
        breakdown={"financial_anomaly": 30.0},
        priority_tier="high",
        evidence=[EvidenceItem(
            evidence_id="reimbursement_benchmark:benchmark_deviation",
            source_family="reimbursement_benchmark",
            signal_type="benchmark_deviation",
            value=129.6,
            explanation="Deviasi benchmark.",
        )],
    )
    explanation = await generate_explanation(
        make_claim(), _clinical(), _financial(anomaly=1.0, dev=129.6), _fraud(sim=0.0), _review("strong_multi_signal"), risk,
    )
    assert explanation.recommended_action == "verify_immediately"  # dari tier high
    assert explanation.generated_by == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_generate_explanation_rejects_wrong_numbers(monkeypatch):
    """LLM salah kutip angka → retry gagal → fallback template (angka tetap benar)."""
    import backend.app.agents.explanation_agent as ea

    class BadResp:
        narrative_id = "Klaim X mendapat skor 42 dari 100."  # SALAH (harus 77)
        ranked_reasons = ["x"]
        why_top_priority = "x"
        strongest_evidence = "x"

    async def fake_llm(*a, **k):
        return BadResp()

    monkeypatch.setattr(ea, "structured_completion", fake_llm)
    monkeypatch.setattr(ea, "get_available_model", lambda *a: _async("qwen2.5:7b"))

    risk = RiskScore(total_score=77.4, breakdown={"financial_anomaly": 30.0}, priority_tier="high")
    explanation = await generate_explanation(
        make_claim(), _clinical(), _financial(anomaly=1.0, dev=129.6), _fraud(sim=0.0), _review("weak"), risk,
    )
    # Harus fallback ke template dengan skor BENAR
    assert explanation.generated_by == "template_fallback"
    assert "77" in explanation.narrative_id
    assert "42" not in explanation.narrative_id


@pytest.mark.asyncio
async def test_low_risk_explanation_ignores_hallucinated_fraud_finding(monkeypatch):
    """Klaim low-risk harus memakai narasi deterministik, bukan tuduhan dari LLM."""
    import backend.app.agents.explanation_agent as ea

    class HallucinatedResp:
        narrative_id = "Klaim X mendapat skor 3.7 dari 100 dan terdapat indikasi phantom billing."
        ranked_reasons = ["indikasi phantom billing"]
        why_top_priority = "indikasi phantom billing"
        strongest_evidence = "indikasi phantom billing"

    async def fake_llm(*a, **k):
        return HallucinatedResp()

    monkeypatch.setattr(ea, "structured_completion", fake_llm)
    monkeypatch.setattr(ea, "get_available_model", lambda *a: _async("qwen2.5:7b"))

    risk = RiskScore(total_score=3.7, breakdown={"isolation_forest_anomaly": 3.7}, priority_tier="low")
    explanation = await generate_explanation(
        make_claim(), _clinical(), _financial(), _fraud(), _review("weak"), risk,
    )

    assert explanation.generated_by == "template_fallback"
    assert "phantom billing" not in explanation.narrative_id.lower()


def test_tier_action_mapping():
    assert TIER_TO_ACTION["high"] == "verify_immediately"
    assert TIER_TO_ACTION["medium"] == "review_when_available"
    assert TIER_TO_ACTION["low"] == "low_priority"


def test_low_priority_reason_describes_absence_of_irregularity_not_change():
    risk = RiskScore(total_score=0.0, breakdown={"clinical_rule_flags": 0.0}, priority_tier="low")
    text = build_priority_reason(risk)
    assert "tidak menemukan ketidakwajaran" in text.lower()
    assert "perubahan" not in text.lower()


def test_low_priority_template_uses_indonesian_tier_without_double_period():
    claim = make_claim()
    risk = RiskScore(total_score=3.7, breakdown={"isolation_forest_anomaly": 3.7}, priority_tier="low")
    explanation = _template_explanation(
        claim, _clinical(), _financial(), _fraud(), _review("weak"), risk,
        facts={"score": 3.7, "deviation_pct": 0.0, "similarity_pct": None, "actual_cost": claim.cost_claimed, "tier": "low"},
    )
    assert "prioritas rendah" in explanation.narrative_id.lower()
    assert ".." not in explanation.narrative_id


def test_sanitize_jargon_replaces_keys():
    from backend.app.agents.explanation_agent import _sanitize_jargon
    text = "Kontributor terbesar similarity_fraud 8.0 poin via isolation_forest_anomaly."
    clean = _sanitize_jargon(text)
    assert "similarity_fraud" not in clean
    assert "isolation_forest" not in clean
    assert "kemiripan riwayat klaim" in clean
    assert "anomali pola perilaku" in clean
