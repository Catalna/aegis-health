"""Test Data Validation deterministik (AGENTS.md Section 1) — gerbang orchestrator."""
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from backend.app.agents.orchestrator import validate_deterministic
from conftest import make_claim


def _mock_db_with_existing(existing=None):
    db = MagicMock()
    scalars = MagicMock()
    scalars.scalars.return_value = existing or []
    db.execute = AsyncMock(return_value=scalars)
    return db


@pytest.mark.asyncio
async def test_valid_claim_passes(normal_claim):
    db = _mock_db_with_existing()
    result = await validate_deterministic(normal_claim, db)
    assert not result.hard_reject
    assert result.reject_reason is None
    assert result.exact_duplicate_of is None


@pytest.mark.asyncio
async def test_discharge_before_admission_hard_reject():
    claim = make_claim(
        admission_date=date(2026, 7, 19),
        discharge_date=date(2026, 7, 10),
    )
    db = _mock_db_with_existing()
    result = await validate_deterministic(claim, db)
    assert result.hard_reject
    assert "tanggal" in result.reject_reason.lower()


@pytest.mark.asyncio
async def test_missing_required_field_rejected_at_boundary():
    """Field wajib kosong ditolak di boundary Pydantic (gerbang pertama)."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_claim(patient_id="  ")


@pytest.mark.asyncio
async def test_severity_out_of_range_hard_reject():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_claim(severity_level=9)  # Pydantic boundary juga harus menolak


@pytest.mark.asyncio
async def test_negative_cost_rejected_at_boundary():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_claim(cost_claimed=-100)


@pytest.mark.asyncio
async def test_exact_duplicate_detected():
    existing = MagicMock()
    existing.claim_id = "CLM-ORIG"
    existing.patient_id = "PAT-001"
    existing.diagnosis_secondary = "I10"
    existing.procedure_codes = "36.10,89.52"
    db = _mock_db_with_existing([existing])

    claim = make_claim()  # field klinis identik dgn existing
    result = await validate_deterministic(claim, db)
    assert not result.hard_reject
    assert result.exact_duplicate_of == "CLM-ORIG"
    assert any("identik" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_los_inconsistent_with_dates_warns():
    claim = make_claim(length_of_stay=30)  # rentang tanggal cuma 7 hari
    db = _mock_db_with_existing()
    result = await validate_deterministic(claim, db)
    assert not result.hard_reject
    assert any("tidak konsisten" in w.lower() for w in result.warnings)
