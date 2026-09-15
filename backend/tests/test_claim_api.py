from datetime import date, datetime, timezone
from inspect import signature
from typing import Literal, get_args, get_type_hints
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BooleanClauseList, BindParameter, Case, Grouping, UnaryExpression

from backend.app.api.claims import (
    _safe_claim_payload,
    claim_admission_filters,
    claim_queue_ordering,
    claim_priority_ordering,
    claim_received_filters,
    claim_sorting,
    get_claim,
    get_claim_analysis,
    list_claims,
)
from backend.app.models.database import ClaimRecord, RiskAnalysisRecord


class _ClaimResult:
    def __init__(self, claim):
        self.claim = claim

    def scalar_one_or_none(self):
        return self.claim


class _ClaimSession:
    def __init__(self, claim):
        self.claim = claim

    async def execute(self, _statement):
        return _ClaimResult(self.claim)


class _AnalysisSession:
    def __init__(self, analysis):
        self.analysis = analysis
        self.claim = ClaimRecord(claim_id=analysis.claim_id)

    async def scalar(self, _statement):
        return self.claim

    async def execute(self, _statement):
        return _ClaimResult(self.analysis)


class _ListResult:
    def __init__(self, claims):
        self.claims = claims

    def scalars(self):
        return self

    def all(self):
        return self.claims


def _expression_value(expression, claim):
    if isinstance(expression, Grouping):
        return _expression_value(expression.element, claim)
    if isinstance(expression, BindParameter):
        return expression.value
    if hasattr(expression, "table") and hasattr(expression, "name"):
        return getattr(claim, expression.name)
    if isinstance(expression, Case):
        for condition, result in expression.whens:
            if _expression_matches(condition, claim):
                return _expression_value(result, claim)
        return _expression_value(expression.else_, claim)
    if isinstance(expression, UnaryExpression):
        return _expression_value(expression.element, claim)
    return expression


def _expression_matches(expression, claim):
    if isinstance(expression, Grouping):
        return _expression_matches(expression.element, claim)
    if isinstance(expression, BooleanClauseList):
        values = [_expression_matches(clause, claim) for clause in expression.clauses]
        return all(values) if expression.operator is operators.and_ else any(values)

    left = _expression_value(expression.left, claim)
    right = _expression_value(expression.right, claim)
    if expression.operator is operators.eq:
        return left == right
    if expression.operator is operators.ge:
        return left >= right
    if expression.operator is operators.gt:
        return left > right
    if expression.operator is operators.le:
        return left <= right
    if expression.operator is operators.lt:
        return left < right
    if expression.operator is operators.is_:
        return left is right
    if expression.operator is operators.ilike_op:
        pattern = str(right).casefold().replace("%", "")
        return pattern in str(left).casefold()
    raise AssertionError(f"unsupported predicate operator: {expression.operator}")


class _InMemoryListSession:
    def __init__(self, claims):
        self.claims = list(claims)

    @staticmethod
    def _matches(statement, claim):
        return all(_expression_matches(criteria, claim) for criteria in statement._where_criteria)

    async def scalar(self, statement):
        return sum(self._matches(statement, claim) for claim in self.claims)

    async def execute(self, statement):
        claims = [claim for claim in self.claims if self._matches(statement, claim)]
        for ordering in reversed(statement._order_by_clauses):
            if isinstance(ordering, UnaryExpression) and ordering.modifier in {
                operators.nulls_last_op,
                operators.nulls_first_op,
            }:
                nulls_last = ordering.modifier is operators.nulls_last_op
                ordering = ordering.element
            else:
                nulls_last = False
            descending = ordering.modifier is operators.desc_op
            expression = ordering.element
            non_null = [claim for claim in claims if _expression_value(expression, claim) is not None]
            nulls = [claim for claim in claims if _expression_value(expression, claim) is None]
            non_null.sort(
                key=lambda claim: _expression_value(expression, claim),
                reverse=descending,
            )
            claims = non_null + nulls if nulls_last else nulls + non_null

        offset = statement._offset_clause.value if statement._offset_clause is not None else 0
        limit = statement._limit_clause.value if statement._limit_clause is not None else None
        return _ListResult(claims[offset:None if limit is None else offset + limit])


def _list_claim(
    claim_id,
    *,
    received_day,
    admission_day,
    queue_sequence,
    tier,
    status="processed",
    risk_score=50.0,
    cost_claimed=100.0,
):
    return ClaimRecord(
        claim_id=claim_id,
        patient_id=f"PAT-{claim_id}",
        provider_id="FAC-LIST",
        doctor_id="DR-LIST",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=cost_claimed,
        length_of_stay=1,
        admission_date=admission_day.isoformat(),
        status=status,
        received_at=datetime.combine(received_day, datetime.min.time(), tzinfo=timezone.utc),
        queue_sequence=queue_sequence,
        priority_tier=tier,
        risk_score=risk_score,
    )


async def _call_list_claims(db, **overrides):
    params = {
        "skip": 0,
        "limit": 50,
        "status": None,
        "tier": None,
        "q": None,
        "received_from": None,
        "received_to": None,
        "admission_from": None,
        "admission_to": None,
        "sort": "priority",
    }
    params.update(overrides)
    return await list_claims(db=db, **params)


@pytest.mark.asyncio
async def test_get_claim_sanitizes_legacy_persisted_error_details():
    claim = ClaimRecord(
        claim_id="CLAIM-SECRET",
        patient_id="PATIENT-1",
        provider_id="FACILITY-1",
        doctor_id="DOCTOR-1",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100,
        length_of_stay=1,
        last_analysis_error="secret database hostname and password",
        last_analysis_error_code=None,
    )

    payload = await get_claim(claim.claim_id, _ClaimSession(claim))

    assert payload["last_analysis_error_code"] == "analysis_retryable"
    assert payload["last_analysis_error"] == "Pemeriksaan gagal sementara. Silakan coba lagi."
    assert "secret database" not in str(payload)


@pytest.mark.asyncio
async def test_get_claim_analysis_omits_persisted_raw_exception_fields():
    analysis = RiskAnalysisRecord(
        claim_id="CLAIM-SECRET",
        total_score=10,
        priority_tier="low",
        recommended_action="low_priority",
        analysis_version=6,
        evidence_json='{"analysis_version": 6, "agent_errors": [{"raw_output": "secret stack trace"}], "clinical": {"evidence_text": "Clinical agent gagal: secret database path"}, "financial": {"evidence_text": "[Fallback z-score peer - model ML tidak tersedia: SECRET_PERSISTED_EXCEPTION]"}, "review": {"reasoning_narrative": "[Fallback rule-count - LLM synthesis tidak tersedia: SECRET_PERSISTED_EXCEPTION]"}, "fraud": {"evidence_text": "Safe fraud evidence"}, "last_analysis_error": "secret database path"}',
    )

    payload = await get_claim_analysis(analysis.claim_id, _AnalysisSession(analysis))

    assert "SECRET_PERSISTED_EXCEPTION" not in str(payload)
    assert "raw_output" not in str(payload)
    assert payload["result"]["financial"]["evidence_text"] == "Pemeriksaan gagal sementara. Silakan coba lagi."
    assert payload["result"]["review"]["reasoning_narrative"] == "Pemeriksaan gagal sementara. Silakan coba lagi."
    assert payload["result"]["fraud"]["evidence_text"] == "Safe fraud evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record_shape", "financial_text", "review_text"),
    [
        (
            "current",
            "SECRET_PERSISTED_EXCEPTION",
            "Traceback (most recent call last): RuntimeError: SECRET_PERSISTED_EXCEPTION",
        ),
        (
            "legacy",
            "Financial engine failed - SECRET_PERSISTED_EXCEPTION",
            "[review-agent internal-error] SECRET_PERSISTED_EXCEPTION",
        ),
    ],
)
async def test_get_claim_analysis_sanitizes_unwrapped_and_variant_exception_text(
    record_shape, financial_text, review_text
):
    evidence = {
        "analysis_version": 6,
        "record_shape": record_shape,
        "financial": {"evidence_text": financial_text},
        "review": {"reasoning_narrative": review_text},
        "risk": {"total_score": 10, "priority_tier": "low"},
        "explanation": {"recommended_action": "low_priority"},
    }
    analysis = RiskAnalysisRecord(
        claim_id=f"CLAIM-{record_shape.upper()}",
        total_score=10,
        priority_tier="low",
        recommended_action="low_priority",
        analysis_version=6,
        evidence_json=json.dumps(evidence),
    )

    payload = await get_claim_analysis(analysis.claim_id, _AnalysisSession(analysis))

    assert "SECRET_PERSISTED_EXCEPTION" not in json.dumps(payload)
    assert payload["result"]["financial"]["evidence_text"] == "Pemeriksaan gagal sementara. Silakan coba lagi."
    assert payload["result"]["review"]["reasoning_narrative"] == "Pemeriksaan gagal sementara. Silakan coba lagi."


@pytest.mark.asyncio
async def test_get_claim_analysis_preserves_normal_financial_and_review_text():
    evidence = {
        "analysis_version": 6,
        "financial": {"evidence_text": "Biaya klaim 12% di atas median peer."},
        "review": {"reasoning_narrative": "Temuan biaya perlu diverifikasi terhadap dokumen pendukung."},
        "risk": {"total_score": 10, "priority_tier": "low"},
        "explanation": {"recommended_action": "low_priority"},
    }
    analysis = RiskAnalysisRecord(
        claim_id="CLAIM-NORMAL-TEXT",
        total_score=10,
        priority_tier="low",
        recommended_action="low_priority",
        analysis_version=6,
        evidence_json=json.dumps(evidence),
    )

    payload = await get_claim_analysis(analysis.claim_id, _AnalysisSession(analysis))

    assert payload["result"]["financial"]["evidence_text"] == evidence["financial"]["evidence_text"]
    assert payload["result"]["review"]["reasoning_narrative"] == evidence["review"]["reasoning_narrative"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record_shape", "clinical_text", "fraud_text"),
    [
        (
            "current",
            "SECRET_PERSISTED_EXCEPTION",
            "Traceback (most recent call last): RuntimeError: SECRET_PERSISTED_EXCEPTION",
        ),
        (
            "legacy",
            "Clinical agent failed - SECRET_PERSISTED_EXCEPTION",
            "[fraud-agent internal-error] SECRET_PERSISTED_EXCEPTION",
        ),
    ],
)
async def test_get_claim_analysis_sanitizes_clinical_and_fraud_exception_text(
    record_shape, clinical_text, fraud_text
):
    evidence = {
        "analysis_version": 6,
        "record_shape": record_shape,
        "clinical": {"evidence_text": clinical_text},
        "fraud": {"evidence_text": fraud_text},
        "risk": {"total_score": 10, "priority_tier": "low"},
        "explanation": {"recommended_action": "low_priority"},
    }
    analysis = RiskAnalysisRecord(
        claim_id=f"CLAIM-{record_shape.upper()}-CLINICAL-FRAUD",
        total_score=10,
        priority_tier="low",
        recommended_action="low_priority",
        analysis_version=6,
        evidence_json=json.dumps(evidence),
    )

    payload = await get_claim_analysis(analysis.claim_id, _AnalysisSession(analysis))

    assert "SECRET_PERSISTED_EXCEPTION" not in json.dumps(payload)
    assert payload["result"]["clinical"]["evidence_text"] == "Pemeriksaan gagal sementara. Silakan coba lagi."
    assert payload["result"]["fraud"]["evidence_text"] == "Pemeriksaan gagal sementara. Silakan coba lagi."


@pytest.mark.asyncio
async def test_get_claim_analysis_preserves_normal_clinical_and_fraud_text():
    evidence = {
        "analysis_version": 6,
        "clinical": {"evidence_text": "Durasi rawat sesuai dengan diagnosis utama."},
        "fraud": {"evidence_text": "Tidak ada kemiripan bermakna dengan klaim pembanding."},
        "risk": {"total_score": 10, "priority_tier": "low"},
        "explanation": {"recommended_action": "low_priority"},
    }
    analysis = RiskAnalysisRecord(
        claim_id="CLAIM-NORMAL-CLINICAL-FRAUD",
        total_score=10,
        priority_tier="low",
        recommended_action="low_priority",
        analysis_version=6,
        evidence_json=json.dumps(evidence),
    )

    payload = await get_claim_analysis(analysis.claim_id, _AnalysisSession(analysis))

    assert payload["result"]["clinical"]["evidence_text"] == evidence["clinical"]["evidence_text"]
    assert payload["result"]["fraud"]["evidence_text"] == evidence["fraud"]["evidence_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("record_shape", ["current", "legacy"])
async def test_get_claim_analysis_sanitizes_nested_public_analysis_fields(record_shape):
    marker = "RAW_EXCEPTION_MARKER"
    secret_marker = "SECRET_PERSISTED_EXCEPTION"
    nested = {
        "risk": {"evidence": [{"explanation": marker}]},
        "explanation": {
            "narrative_id": f"InternalError: {secret_marker}",
            "ranked_reasons": [f"Traceback: {marker}"],
            "qa_panel": {
                "why_top_priority": f"database.internal.local:5432 {secret_marker}",
                "strongest_evidence": r"C:\app\backend\trace.py:12",
                "most_similar_claim": f"{secret_marker}",
                "is_this_fraud": f"/srv/app/backend/{marker}",
            },
        },
        "clinical": {"evidence_text": f"Clinical agent failed: {secret_marker}"},
        "fraud": {"evidence_text": f"[fraud-agent internal-error] {marker}"},
        "agent_errors": [{"error_type": "exception", "raw_output": secret_marker}],
    }
    evidence = {"analysis_version": 6, **nested}
    if record_shape == "legacy":
        evidence["assessment"] = {
            "score": {"evidence": [{"explanation": marker}]},
            "narrative": {
                "narrative_id": f"legacy traceback {marker}",
                "ranked_reasons": [marker],
                "qa_panel": {"why_top_priority": marker},
            },
        }

    analysis = RiskAnalysisRecord(
        claim_id=f"CLAIM-NESTED-{record_shape.upper()}",
        total_score=10,
        priority_tier="low",
        recommended_action="low_priority",
        analysis_version=6,
        evidence_json=json.dumps(evidence),
    )

    payload = await get_claim_analysis(analysis.claim_id, _AnalysisSession(analysis))
    serialized = json.dumps(payload)

    assert marker not in serialized
    assert secret_marker not in serialized
    assert "raw_output" not in serialized
    assert "agent_errors" not in serialized
    assert payload["result"]["risk"]["evidence"][0]["explanation"] == "Pemeriksaan gagal sementara. Silakan coba lagi."
    assert payload["result"]["explanation"]["narrative_id"] == "Pemeriksaan gagal sementara. Silakan coba lagi."
    assert payload["result"]["explanation"]["ranked_reasons"] == ["Pemeriksaan gagal sementara. Silakan coba lagi."]
    assert payload["result"]["explanation"]["qa_panel"]["why_top_priority"] == "Pemeriksaan gagal sementara. Silakan coba lagi."


def test_verifier_ordering_is_tier_then_receipt_then_fifo_then_status():
    ordering = claim_priority_ordering()
    assert len(ordering) == 5
    tier_sql = str(ordering[0].element.compile(compile_kwargs={"literal_binds": True}))
    status_sql = str(ordering[3].element.compile(compile_kwargs={"literal_binds": True}))
    assert "high" in tier_sql
    assert "medium" in tier_sql
    assert "low" in tier_sql
    assert ordering[1].element.compare(ClaimRecord.__table__.c.received_at)
    assert ordering[2].element.compare(ClaimRecord.__table__.c.queue_sequence)
    assert "review_required" in status_sql
    assert "verified" in status_sql


def test_default_verifier_ordering_is_priority_then_receipt_then_fifo():
    ordering = claim_sorting("priority")

    assert "high" in str(ordering[0].element.compile(compile_kwargs={"literal_binds": True}))
    assert ordering[1].element.compare(ClaimRecord.__table__.c.received_at)
    assert ordering[2].element.compare(ClaimRecord.__table__.c.queue_sequence)


def test_fifo_ordering_remains_explicit_for_scanner_sort():
    ordering = claim_sorting("queue")

    assert ordering[0].element.compare(ClaimRecord.__table__.c.queue_sequence)


def test_claim_list_api_defaults_to_verifier_ordering():
    assert signature(list_claims).parameters["sort"].default.default == "priority"


def test_alternate_risk_sorts_put_unscored_claims_last():
    assert "NULLS LAST" in str(claim_sorting("risk_desc")[0]).upper()
    assert "NULLS LAST" in str(claim_sorting("risk_asc")[0]).upper()


@pytest.mark.parametrize("sort", ["risk_desc", "risk_asc", "cost_desc", "cost_asc"])
def test_metric_sorts_have_stable_queue_and_claim_tie_breakers(sort):
    ordering = claim_sorting(sort)

    assert len(ordering) == 3
    assert ordering[1].element.compare(ClaimRecord.__table__.c.queue_sequence)
    assert ordering[2].element.compare(ClaimRecord.__table__.c.claim_id)


def test_admission_date_filters_are_inclusive_and_separate_from_received_filters():
    filters = claim_admission_filters(date(2026, 9, 1), date(2026, 9, 13))
    statement = select(ClaimRecord).where(*filters)
    sql = str(statement)

    assert "claims.admission_date" in sql
    assert len(filters) == 2


def test_received_date_filters_bound_the_claim_list_query():
    filters = claim_received_filters(date(2026, 9, 1), date(2026, 9, 13))
    statement = select(ClaimRecord).where(*filters)
    compiled = statement.compile()

    assert "claims.received_at" in str(compiled)
    assert sorted(value.isoformat() for value in compiled.params.values()) == [
        "2026-09-01T00:00:00+00:00",
        "2026-09-14T00:00:00+00:00",
    ]


def test_admission_date_filter_boundaries_are_inclusive():
    filters = claim_admission_filters(date(2026, 9, 1), date(2026, 9, 13))
    statement = select(ClaimRecord).where(*filters)
    compiled = statement.compile()

    assert sorted(compiled.params.values()) == ["2026-09-01", "2026-09-13"]


def test_claim_list_filters_reject_unknown_values_at_the_api_boundary():
    hints = get_type_hints(list_claims)

    def literal_values(annotation):
        values = set()
        for item in get_args(annotation):
            values.update(get_args(item) if getattr(item, "__origin__", None) is Literal else {item})
        return values

    assert literal_values(hints["status"]) >= {
        "pending", "scanning", "processed", "review_required", "failed", "verified",
    }
    assert literal_values(hints["tier"]) >= {"high", "medium", "low"}
    assert literal_values(hints["sort"]) >= {
        "priority", "queue", "risk_desc", "risk_asc", "cost_desc", "cost_asc", "id",
    }


def test_safe_claim_payload_exposes_queue_metadata_without_internal_attributes():
    claim = ClaimRecord(
        claim_id="CLAIM-PUBLIC",
        patient_id="PATIENT-1",
        provider_id="FACILITY-1",
        doctor_id="DOCTOR-1",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100,
        length_of_stay=1,
        status="pending",
        analysis_attempts=2,
        last_analysis_error="private traceback",
        last_analysis_error_code="unknown-internal-code",
    )
    claim.internal_secret = "must not be serialized"

    payload = _safe_claim_payload(claim)

    assert payload["status"] == "pending"
    assert payload["analysis_attempts"] == 2
    assert "received_at" in payload
    assert "analysis_started_at" in payload
    assert "analyzed_at" in payload
    assert "verified_at" in payload
    assert payload["last_analysis_error_code"] == "analysis_retryable"
    assert payload["last_analysis_error"] == "Pemeriksaan gagal sementara. Silakan coba lagi."
    assert "internal_secret" not in payload


@pytest.mark.asyncio
async def test_get_claim_analysis_returns_404_for_unknown_claim():
    class MissingClaimSession:
        async def scalar(self, _statement):
            return None

    with pytest.raises(HTTPException) as raised:
        await get_claim_analysis("MISSING-CLAIM", MissingClaimSession())

    assert raised.value.status_code == 404
    assert raised.value.detail == "Claim not found"


@pytest.mark.asyncio
async def test_list_claims_applies_inclusive_date_filters_and_total_count():
    claims = [
        _list_claim(
            "DATE-IN",
            received_day=date(2026, 9, 10),
            admission_day=date(2026, 9, 12),
            queue_sequence=1,
            tier="low",
        ),
        _list_claim(
            "DATE-OUT-RECEIVED",
            received_day=date(2026, 9, 11),
            admission_day=date(2026, 9, 12),
            queue_sequence=2,
            tier="low",
        ),
        _list_claim(
            "DATE-OUT-ADMISSION",
            received_day=date(2026, 9, 10),
            admission_day=date(2026, 9, 13),
            queue_sequence=3,
            tier="low",
        ),
    ]

    response = await _call_list_claims(
        _InMemoryListSession(claims),
        received_from=date(2026, 9, 10),
        received_to=date(2026, 9, 10),
        admission_from=date(2026, 9, 12),
        admission_to=date(2026, 9, 12),
        sort="queue",
    )

    assert response["total"] == 1
    assert [item["claim_id"] for item in response["items"]] == ["DATE-IN"]


@pytest.mark.asyncio
async def test_list_claims_orders_tiers_by_receipt_then_fifo_and_paginates():
    claims = [
        _list_claim("HIGH-NEW", received_day=date(2026, 9, 10), admission_day=date(2026, 9, 1), queue_sequence=20, tier="high"),
        _list_claim("HIGH-OLD", received_day=date(2026, 9, 10), admission_day=date(2026, 9, 1), queue_sequence=10, tier="high"),
        _list_claim("MEDIUM", received_day=date(2026, 9, 9), admission_day=date(2026, 9, 1), queue_sequence=1, tier="medium"),
        _list_claim("LOW", received_day=date(2026, 9, 8), admission_day=date(2026, 9, 1), queue_sequence=2, tier="low"),
    ]

    response = await _call_list_claims(
        _InMemoryListSession(claims),
        skip=1,
        limit=2,
        sort="priority",
    )

    assert response["total"] == 4
    assert [item["claim_id"] for item in response["items"]] == ["HIGH-NEW", "MEDIUM"]
    assert response["skip"] == 1
    assert response["limit"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", ["risk_desc", "risk_asc", "cost_desc", "cost_asc"])
async def test_list_claims_metric_ties_use_queue_then_claim_id(sort):
    claims = [
        _list_claim("TIE-B", received_day=date(2026, 9, 10), admission_day=date(2026, 9, 1), queue_sequence=7, tier="low"),
        _list_claim("TIE-A", received_day=date(2026, 9, 10), admission_day=date(2026, 9, 1), queue_sequence=7, tier="low"),
    ]

    response = await _call_list_claims(_InMemoryListSession(claims), sort=sort)

    assert [item["claim_id"] for item in response["items"]] == ["TIE-A", "TIE-B"]
