import json

import pytest

from scripts.generate_claims import (
    DEFAULT_SEED,
    MIN_COUNT,
    build_parser,
    cleanup_claims,
    generate_claims,
    main,
)


def test_generate_claims_is_deterministic_and_preserves_relationship_invariants():
    claims = generate_claims(count=100, seed=1234, prefix="TEST")
    repeat = generate_claims(count=100, seed=1234, prefix="TEST")

    assert claims == repeat
    assert len(claims) == 100
    assert len({claim["claim_id"] for claim in claims}) == 100
    assert all(claim["claim_id"].startswith("TEST-") for claim in claims)

    same_facility_diagnosis = claims[:25]
    assert len({claim["provider_id"] for claim in same_facility_diagnosis}) == 1
    assert len({claim["diagnosis_primary"] for claim in same_facility_diagnosis}) == 1
    assert len({claim["cost_claimed"] for claim in same_facility_diagnosis}) > 1

    same_diagnosis = claims[25:50]
    assert len({claim["diagnosis_primary"] for claim in same_diagnosis}) == 1
    assert len({claim["provider_id"] for claim in same_diagnosis}) > 1

    same_facility = claims[50:75]
    assert len({claim["provider_id"] for claim in same_facility}) == 1
    assert len({claim["diagnosis_primary"] for claim in same_facility}) > 1

    mixed_controls = claims[75:]
    assert len({(claim["provider_id"], claim["diagnosis_primary"]) for claim in mixed_controls}) == len(mixed_controls)


def test_parser_defaults_to_pending_only_and_deterministic_seed():
    args = build_parser().parse_args([])

    assert args.analyze is False
    assert args.dry_run is False
    assert args.seed == DEFAULT_SEED
    assert args.count == 100


@pytest.mark.parametrize(
    ("argument", "expected"),
    [("--analyze", True), ("--analyze=true", True), ("--analyze=false", False)],
)
def test_parser_accepts_bare_and_explicit_analyze_values(argument, expected):
    assert build_parser().parse_args([argument]).analyze is expected


def test_parser_rejects_counts_below_relationship_minimum():
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(["--count", str(MIN_COUNT - 1)])

    assert raised.value.code == 2


def test_invalid_small_count_cannot_run_dry_run():
    with pytest.raises(SystemExit) as raised:
        main(["--count", str(MIN_COUNT - 1), "--dry-run"])

    assert raised.value.code == 2


def test_cleanup_dry_run_is_rejected_before_any_http_request(monkeypatch):
    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("cleanup dry-run must not construct an HTTP client")

    monkeypatch.setattr("scripts.generate_claims.httpx.Client", UnexpectedClient)

    with pytest.raises(SystemExit) as raised:
        main(["--cleanup", "--dry-run", "--prefix", "TASK5"])

    assert raised.value.code == 2


def test_cleanup_requires_confirmation_and_resets_only_matching_claim_ids():
    class Response:
        status_code = 200
        text = ""

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class Client:
        def __init__(self):
            self.deleted = []

        def get(self, path, params):
            assert path == "/api/claims"
            assert params == {"q": "TASK5-", "skip": 0, "limit": 1000, "sort": "id"}
            return Response({
                "total": 2,
                "items": [
                    {"claim_id": "TASK5-AAA"},
                    {"claim_id": "OTHER-CLAIM"},
                ],
            })

        def delete(self, path):
            self.deleted.append(path)
            return Response({"status": "success"})

    client = Client()
    pending = cleanup_claims("TASK5", base_url="http://localhost:8000", confirm=False, timeout=1, client=client)
    assert pending["confirmation_required"] is True
    assert pending["matched"] == 1
    assert client.deleted == []

    confirmed = cleanup_claims("TASK5", base_url="http://localhost:8000", confirm=True, timeout=1, client=client)
    assert confirmed["reset"] == 1
    assert confirmed["failed"] == 0
    assert client.deleted == ["/api/claims/TASK5-AAA"]


def test_dry_run_does_not_construct_an_http_client(monkeypatch, capsys):
    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("dry-run must not connect to the API")

    monkeypatch.setattr("scripts.generate_claims.httpx.Client", UnexpectedClient)

    assert main(["--count", "8", "--seed", "7", "--prefix", "DRY", "--dry-run"]) == 0

    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["mode"] == "dry-run"
    assert summary["generated"] == 8
    assert summary["analyze_requested"] is False
