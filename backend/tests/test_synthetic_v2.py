import pytest

from backend.app.data.synthetic_v2.generator import PROFILES, generate_synthetic_v2
from backend.app.data.synthetic_v2.io import load_synthetic_v2, write_synthetic_v2
from backend.app.data.synthetic_v2.validation import validate_synthetic_v2


def test_synthetic_v2_profiles_have_the_planned_claim_counts():
    assert PROFILES["dev"]["claims"] == {"train": 5_000, "validation": 2_000, "test": 2_000}
    assert PROFILES["standard"]["claims"] == {
        "train": 150_000,
        "validation": 50_000,
        "test": 50_000,
    }
    assert PROFILES["large"]["claims"] == {
        "train": 500_000,
        "validation": 100_000,
        "test": 100_000,
    }


def test_v2_seeded_splits_are_reproducible_and_keep_truth_separate():
    first = generate_synthetic_v2(profile="dev", seed=42)
    second = generate_synthetic_v2(profile="dev", seed=42)

    assert first == second
    for split in ("train", "validation", "test"):
        claims = first[split]["claims"]
        labels = first[split]["labels"]
        assert len(claims) == len(labels)
        assert not {"is_anomaly", "anomaly_type", "difficulty", "scenario_family", "group_id"} & claims[0].keys()
        assert {"is_anomaly", "anomaly_type", "difficulty", "scenario_family", "group_id", "label_confidence"} <= labels[0].keys()
        assert len({claim["claim_id"] for claim in claims}) == len(claims)


def test_v2_relational_groups_are_kept_inside_their_split_and_hard_negatives_exist():
    bundle = generate_synthetic_v2(profile="dev", seed=7)
    group_ids = {
        split: {label["group_id"] for label in bundle[split]["labels"]}
        for split in ("train", "validation", "test")
    }

    assert group_ids["train"].isdisjoint(group_ids["validation"])
    assert group_ids["train"].isdisjoint(group_ids["test"])
    assert group_ids["validation"].isdisjoint(group_ids["test"])
    assert any(label["scenario_family"].startswith("hard_negative_") for label in bundle["train"]["labels"])


def test_v2_relational_anomalies_have_grouped_source_and_fragment_claims():
    split = generate_synthetic_v2(profile="dev", seed=42)["train"]
    labels = split["labels"]
    for anomaly_type in ("cloning", "repeat_billing", "unbundling"):
        groups = {}
        for label in labels:
            groups.setdefault(label["group_id"], []).append(label)
        assert any(
            len(group) >= 2 and any(item["anomaly_type"] == anomaly_type for item in group)
            for group in groups.values()
        ), anomaly_type


def test_v2_exact_clone_matches_source_except_synthetic_identity():
    split = generate_synthetic_v2(profile="dev", seed=42)["train"]
    claims = {claim["claim_id"]: claim for claim in split["claims"]}
    labels = {label["claim_id"]: label for label in split["labels"]}
    clone_label = next(
        label for label in split["labels"]
        if label["anomaly_type"] == "cloning" and label["scenario_family"] == "cloning:exact_copy"
    )
    grouped = [label for label in split["labels"] if label["group_id"] == clone_label["group_id"]]
    source_label = next(label for label in grouped if label["claim_id"] != clone_label["claim_id"])
    source, clone = claims[source_label["claim_id"]], claims[clone_label["claim_id"]]
    assert clone["patient_id"] != source["patient_id"]
    assert clone["admission_date"] == source["admission_date"]
    assert clone["cost_claimed"] == source["cost_claimed"]


def test_v2_contains_a_broad_diagnosis_catalog():
    from backend.app.data.synthetic_v2.generator import DIAGNOSIS_CATALOG

    assert len(DIAGNOSIS_CATALOG) >= 150
    assert all(len(code) == 3 for code in DIAGNOSIS_CATALOG)


def test_v2_claim_schema_covers_clinical_and_special_group_attributes():
    split = generate_synthetic_v2(profile="dev", seed=42)["train"]
    claims, labels = split["claims"], split["labels"]
    required = {"medication_codes", "icu_indicator", "ventilator_used", "surgical_indicator", "special_group_types", "service_type"}

    assert required <= claims[0].keys()
    assert all(not claim["ventilator_used"] or claim["icu_indicator"] for claim in claims)
    assert all(
        claim["length_of_stay"] == 0
        for claim, label in zip(claims, labels)
        if claim["outpatient"] and not label["is_anomaly"]
    )


def test_v2_includes_enriched_anomaly_test_and_ood_facility_stress_set():
    bundle = generate_synthetic_v2(profile="dev", seed=42)
    enriched = bundle["test_enriched"]
    positive_counts = {}
    for label in enriched["labels"]:
        positive_counts[label["anomaly_type"]] = positive_counts.get(label["anomaly_type"], 0) + int(label["is_anomaly"])
    train_facilities = {claim["provider_id"] for claim in bundle["train"]["claims"]}
    train_doctors = {claim["doctor_id"] for claim in bundle["train"]["claims"]}
    train_families = {label["scenario_family"] for label in bundle["train"]["labels"]}

    assert all(positive_counts.get(kind, 0) >= 150 for kind in (
        "upcoding", "unbundling", "cloning", "repeat_billing", "phantom_billing", "inflated_bill", "prolonged_los"
    ))
    assert len(enriched["claims"]) == 2_100
    assert not train_facilities.intersection(claim["provider_id"] for claim in bundle["ood"]["claims"])
    assert not train_doctors.intersection(claim["doctor_id"] for claim in bundle["ood"]["claims"])
    assert not train_families.intersection(
        label["scenario_family"] for label in bundle["ood"]["labels"] if label["is_anomaly"]
    )
    assert train_facilities == {claim["provider_id"] for claim in bundle["test"]["claims"]}
    assert len(train_facilities) == PROFILES["dev"]["facilities"]
    assert len(train_doctors) == PROFILES["dev"]["doctors"]


def test_v2_hard_negative_labels_have_matching_claim_characteristics():
    split = generate_synthetic_v2(profile="dev", seed=42)["train"]
    claims = {claim["claim_id"]: claim for claim in split["claims"]}
    labels = split["labels"]
    catastrophic = next(label for label in labels if label["scenario_family"] == "hard_negative_catastrophic_cost")
    prolonged = next(label for label in labels if label["scenario_family"] == "hard_negative_long_los")
    chronic = next(label for label in labels if label["scenario_family"] == "hard_negative_chronic_repeat_visit")
    readmission = next(label for label in labels if label["scenario_family"] == "hard_negative_readmission")

    assert claims[catastrophic["claim_id"]]["cost_claimed"] >= claims[catastrophic["claim_id"]]["regional_base_rate"] * 1.3
    assert claims[prolonged["claim_id"]]["length_of_stay"] >= 15
    assert claims[chronic["claim_id"]]["diagnosis_primary"] == "N18"
    assert sum(label["group_id"] == readmission["group_id"] for label in labels) >= 2


def test_v2_repeat_billing_mechanism_family_matches_its_day_window():
    split = generate_synthetic_v2(profile="dev", seed=42)["validation"]
    claims = {claim["claim_id"]: claim for claim in split["claims"]}
    labels = split["labels"]
    repeated = next(
        label for label in labels
        if label["scenario_family"] == "repeat_billing:days_31_45"
    )
    related = [label for label in labels if label["group_id"] == repeated["group_id"]]
    dates = sorted(claims[label["claim_id"]]["admission_date"] for label in related)
    from datetime import date
    gap = abs((date.fromisoformat(dates[1]) - date.fromisoformat(dates[0])).days)
    assert 31 <= gap <= 45


def test_v2_validator_accepts_a_generated_dev_bundle():
    report = validate_synthetic_v2(generate_synthetic_v2(profile="dev", seed=123))
    assert report["status"] == "valid"


def test_v2_validator_rejects_label_leakage_and_group_leakage():
    bundle = generate_synthetic_v2(profile="dev", seed=123)
    bundle["validation"]["claims"][0]["is_anomaly"] = False
    with pytest.raises(ValueError, match="label leakage"):
        validate_synthetic_v2(bundle)

    bundle = generate_synthetic_v2(profile="dev", seed=123)
    bundle["validation"]["labels"][0]["group_id"] = bundle["train"]["labels"][0]["group_id"]
    with pytest.raises(ValueError, match="group leakage"):
        validate_synthetic_v2(bundle)


def test_v2_csv_output_includes_schema_and_explicit_synthetic_data_card(tmp_path):
    bundle = generate_synthetic_v2(profile="dev", seed=123)
    result = write_synthetic_v2(bundle, tmp_path, file_format="csv")

    assert result["status"] == "valid"
    assert (tmp_path / "train.csv").is_file()
    assert (tmp_path / "train_labels.csv").is_file()
    assert (tmp_path / "schema.json").is_file()
    data_card = (tmp_path / "data_card.md").read_text(encoding="utf-8")
    assert "Synthetic demonstrator data only" in data_card
    assert "does not validate performance on real BPJS claims" in data_card
    assert validate_synthetic_v2(load_synthetic_v2(tmp_path))["status"] == "valid"
