from backend.app.data.synthetic_generator import (
    generate_cloning_case,
    generate_normal_claim,
    generate_repeat_billing_case,
    generate_unbundling_case,
)
from backend.app.evaluation.dataset import (
    build_evaluation_datasets,
    validate_group_disjointness,
)
import pytest


def test_generated_claims_preserve_relationship_groups():
    normal = generate_normal_claim("P1-NORMAL")
    clone_a, clone_b = generate_cloning_case("P1-CLN-A", "P1-CLN-B")
    repeat = generate_repeat_billing_case("P1-RPT", normal)
    fragments = generate_unbundling_case("P1-UNB")

    assert normal["evaluation_group_id"]
    assert clone_a["evaluation_group_id"] == clone_b["evaluation_group_id"]
    assert repeat["evaluation_group_id"] == normal["evaluation_group_id"]
    assert len({claim["evaluation_group_id"] for claim in fragments}) == 1


def test_evaluation_datasets_are_reproducible_and_group_disjoint():
    counts = {
        "num_normal": 8,
        "num_upcoding": 2,
        "num_cloning_pairs": 1,
        "num_repeat_billing": 1,
        "num_phantom": 1,
        "num_prolonged_los": 1,
        "num_inflated": 1,
        "num_unbundling_groups": 1,
    }
    train, holdout = build_evaluation_datasets(**counts)
    train_again, holdout_again = build_evaluation_datasets(**counts)

    assert train.claims == train_again.claims
    assert holdout.claims == holdout_again.claims
    assert train.seed == 42
    assert holdout.seed == 2026
    assert train.group_ids.isdisjoint(holdout.group_ids)
    assert train.counts["none"] == 9
    assert holdout.counts["upcoding"] == 2


def test_group_overlap_is_rejected_before_scoring():
    with pytest.raises(ValueError, match="group leakage"):
        validate_group_disjointness({"shared-group"}, {"shared-group"})
