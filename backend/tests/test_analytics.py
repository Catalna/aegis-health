from pathlib import Path

import pytest

from backend.app.api import main
from backend.app.models.database import _backfill_analysis_versions
from backend.app.core.versions import ANALYSIS_VERSION, is_current_analysis


@pytest.mark.asyncio
async def test_dashboard_analysis_metrics_join_current_claim_lifecycle_statuses():
    statements = []

    class FakeSession:
        async def scalar(self, statement):
            statements.append(statement)
            return 0

    payload = await main.get_dashboard_stats(FakeSession())

    assert payload["processed_claims"] == 0
    analysis_statements = [
        statement
        for statement in statements
        if "JOIN claims" in str(statement.compile(compile_kwargs={"literal_binds": True}))
    ]
    for statement in analysis_statements:
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "JOIN claims" in sql
        assert "claims.status IN ('processed', 'review_required', 'verified')" in sql
        assert f"risk_analyses.analysis_version = {ANALYSIS_VERSION}" in sql
        assert "risk_analyses.evidence_json" in sql


@pytest.mark.asyncio
async def test_dashboard_exposes_mutually_exclusive_lifecycle_counts():
    class FakeSession:
        async def scalar(self, statement):
            return 0

    payload = await main.get_dashboard_stats(FakeSession())

    for field in (
        "pending_claims",
        "scanning_claims",
        "review_required_claims",
        "processed_status_claims",
        "verified_claims",
        "failed_claims",
    ):
        assert field in payload


def test_analysis_version_is_persisted_and_migrated_for_existing_databases():
    root = Path(__file__).resolve().parents[2]
    source = (root / "backend/app/models/database.py").read_text(encoding="utf-8")
    orchestrator = (root / "backend/app/agents/orchestrator.py").read_text(encoding="utf-8")
    assert "analysis_version: Mapped[Optional[int]]" in source
    assert '"analysis_version INTEGER NULL"' in source
    assert "analysis_version=ANALYSIS_VERSION" in orchestrator


@pytest.mark.asyncio
async def test_analysis_version_migration_backfills_only_valid_json_versions():
    updates = []

    class FakeResult:
        def __iter__(self):
            return iter([
                ("current", '{"analysis_version": 6}'),
                ("old", '{"analysis_version": 5}'),
                ("malformed", '{not-json'),
                ("empty", ""),
                ("wrong-type", '{"analysis_version": "6"}'),
            ])

    class FakeConnection:
        async def execute(self, statement, params=None):
            if "SELECT claim_id, evidence_json" in str(statement):
                return FakeResult()
            if "UPDATE risk_analyses" in str(statement):
                updates.append(params)
                return None
            raise AssertionError(f"unexpected SQL: {statement}")

    await _backfill_analysis_versions(FakeConnection())

    assert updates == [
        {"claim_id": "current", "analysis_version": 6},
        {"claim_id": "old", "analysis_version": 5},
    ]


def test_current_analysis_requires_matching_column_and_evidence_versions():
    assert is_current_analysis(ANALYSIS_VERSION, '{"analysis_version": 6}')
    assert not is_current_analysis(ANALYSIS_VERSION - 1, '{"analysis_version": 6}')
    assert not is_current_analysis(ANALYSIS_VERSION, '{"analysis_version": 5}')
    assert not is_current_analysis(ANALYSIS_VERSION, "")
    assert not is_current_analysis(ANALYSIS_VERSION, '{"nested": {"analysis_version": 6}}')
    assert not is_current_analysis(ANALYSIS_VERSION, 'text "analysis_version": 6')


def test_dashboard_analysis_filter_uses_exact_safe_top_level_json_lookup():
    source = Path(__file__).resolve().parents[2] / "backend/app/api/main.py"
    text = source.read_text(encoding="utf-8")
    assert "parse_jsonb_or_null" in text
    assert "jsonb_typeof" in text
    assert '.op("~")' not in text
