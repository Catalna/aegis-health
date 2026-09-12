from backend.app.data.synthetic_generator import (
    generate_cloning_case,
    generate_normal_claim,
    generate_repeat_billing_case,
    generate_unbundling_case,
)


def test_generated_claims_preserve_relationship_groups():
    normal = generate_normal_claim("P1-NORMAL")
    clone_a, clone_b = generate_cloning_case("P1-CLN-A", "P1-CLN-B")
    repeat = generate_repeat_billing_case("P1-RPT", normal)
    fragments = generate_unbundling_case("P1-UNB")

    assert normal["evaluation_group_id"]
    assert clone_a["evaluation_group_id"] == clone_b["evaluation_group_id"]
    assert repeat["evaluation_group_id"] == normal["evaluation_group_id"]
    assert len({claim["evaluation_group_id"] for claim in fragments}) == 1
