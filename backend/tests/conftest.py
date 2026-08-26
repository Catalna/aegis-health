"""
Shared pytest fixtures — LLM di-mock agar test deterministik & offline.
Unit test per agent sesuai mandat AGENTS.md (input sintetis hasil diketahui).
"""
import sys
import os
import asyncio
from datetime import date

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.app.models.schemas import ClaimInput, MedicationLine

# ---------------------------------------------------------------------------
# Mock LLM — structured_completion tidak pernah memanggil Ollama di test
# ---------------------------------------------------------------------------

class MockLLMResponse:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    """Semua panggilan LLM di-mock: balikkan nilai default yang valid per schema."""
    async def fake_structured(prompt, system_prompt, output_schema, model=None, temperature=0.0, provider="ollama"):
        defaults = {
            "plausibility": "plausible",
            "evidence_text": "mock evidence",
            "confidence_level": "medium",
            "evidence_level": "weak",
            "corroborating_signals": [],
            "reasoning_narrative": "mock narrative",
            "narrative_id": "mock narrative",
            "ranked_reasons": ["mock reason"],
            "why_top_priority": "mock",
            "strongest_evidence": "mock",
        }
        fields = output_schema.model_fields
        data = {k: defaults.get(k, "mock") for k in fields}
        return output_schema.model_validate(data)

    import backend.app.core.llm_client as llm
    monkeypatch.setattr(llm, "structured_completion", fake_structured)
    # Patch juga referensi yang diimpor agent
    import backend.app.agents.clinical_agent as ca
    monkeypatch.setattr(ca, "structured_completion", fake_structured)
    import backend.app.agents.review_agent as ra
    monkeypatch.setattr(ra, "structured_completion", fake_structured)
    import backend.app.agents.explanation_agent as ea
    monkeypatch.setattr(ea, "structured_completion", fake_structured)
    yield


# ---------------------------------------------------------------------------
# Klaim contoh — hasil sudah diketahui
# ---------------------------------------------------------------------------

def make_claim(**overrides) -> ClaimInput:
    base = dict(
        claim_id="CLM-TEST-0001",
        patient_id="PAT-001",
        provider_id="FAC-A12",
        doctor_id="DR-A12-101",
        diagnosis_primary="I21.9",  # AMI
        diagnosis_secondary=["I10"],
        procedure_codes=["36.10", "89.52"],
        medication=[MedicationLine(name="Aspirin", quantity=30), MedicationLine(name="Clopidogrel", quantity=30)],
        severity_level=2,
        cost_claimed=24_000_000,
        length_of_stay=7,
        admission_date=date(2026, 7, 1),
        discharge_date=date(2026, 7, 8),
        referral_info=None,
    )
    base.update(overrides)
    return ClaimInput(**base)


@pytest.fixture
def normal_claim() -> ClaimInput:
    """Klaim wajar: AMI severity 2, biaya sesuai peer, LOS dalam rentang."""
    return make_claim()


@pytest.fixture
def upcoded_claim() -> ClaimInput:
    """Klaim upcode jelas: severity dinaikkan ke 4 + biaya 3x peer tanpa perubahan klinis."""
    return make_claim(
        claim_id="CLM-TEST-UPC",
        severity_level=4,
        cost_claimed=90_000_000,
        diagnosis_secondary=["I10", "A41.9"],
    )


@pytest.fixture
def inflated_claim() -> ClaimInput:
    """Biaya 3x lipat peer average, klinis normal (financial case)."""
    return make_claim(claim_id="CLM-TEST-INF", cost_claimed=72_000_000)


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
