from scripts.populate_performance_dataset import build_performance_claims


def test_performance_dataset_has_fifty_related_claims_with_clean_controls():
    claims = build_performance_claims(seed=20261003, claim_prefix="LIVE-TEST")

    assert len(claims) == 50
    assert len({claim["claim_id"] for claim in claims}) == 50
    assert all(claim["claim_id"].startswith("LIVE-TEST-") for claim in claims)
    assert sum(not claim["is_synthetic_anomaly"] for claim in claims) == 28
    assert sum(claim["anomaly_type"] == "upcoding" for claim in claims) == 4
    assert sum(claim["anomaly_type"] == "cloning" for claim in claims) == 4
    assert sum(claim["anomaly_type"] == "repeat_billing" for claim in claims) == 4
    assert sum(claim["anomaly_type"] == "phantom_billing" for claim in claims) == 4
    assert sum(claim["anomaly_type"] == "prolonged_los" for claim in claims) == 3
    assert sum(claim["anomaly_type"] == "inflated_bill" for claim in claims) == 3

    clone_pairs = {}
    for claim in claims:
        if claim["evaluation_group_id"].startswith("cloning:"):
            clone_pairs.setdefault(claim["evaluation_group_id"], []).append(claim)

    assert len(clone_pairs) == 4
    for pair in clone_pairs.values():
        assert len(pair) == 2
        assert len({claim["provider_id"] for claim in pair}) == 1
        assert len({claim["patient_id"] for claim in pair}) == 2
        assert len({tuple(claim["procedure_codes"]) for claim in pair}) == 1


def test_performance_dataset_submits_relational_references_before_alert_claims():
    claims = build_performance_claims(seed=20261003, claim_prefix="LIVE-TEST")
    positions = {claim["claim_id"]: index for index, claim in enumerate(claims)}

    for repeat_claim in (claim for claim in claims if claim["anomaly_type"] == "repeat_billing"):
        originals = [
            claim for claim in claims
            if claim["evaluation_group_id"] == repeat_claim["evaluation_group_id"]
            and claim["anomaly_type"] == "none"
        ]
        assert len(originals) == 1
        assert positions[originals[0]["claim_id"]] < positions[repeat_claim["claim_id"]]

    for pair in {
        claim["evaluation_group_id"]
        for claim in claims
        if claim["evaluation_group_id"].startswith("cloning:")
    }:
        source, alert = sorted(
            (claim for claim in claims if claim["evaluation_group_id"] == pair),
            key=lambda claim: claim["is_synthetic_anomaly"],
        )
        assert positions[source["claim_id"]] < positions[alert["claim_id"]]
