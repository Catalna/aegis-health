import numpy as np

from backend.app.ml.v2_features import (
    CLASSIFIER_FEATURE_NAMES,
    build_classifier_features,
    build_training_context,
)

_NO_PAIR_SENTINEL = 10_000.0


def _claim(**overrides):
    claim = {
        "diagnosis_primary": "I21",
        "diagnosis_secondary": ["I10"],
        "procedure_codes": ["36.10"],
        "medication_codes": ["ASPIRIN"],
        "special_group_types": [],
        "patient_id": "PAT-0001",
        "provider_id": "FAC-0001",
        "doctor_id": "DR-00001",
        "admission_date": "2025-03-01",
        "patient_age": 67,
        "length_of_stay": 5,
        "severity_level": 2,
        "regional_base_rate": 20_000,
        "facility_type": "RS",
        "facility_class": "B",
        "region": "java",
        "outpatient": False,
        "icu_indicator": False,
        "ventilator_used": False,
        "surgical_indicator": True,
        "cost_claimed": 25_000,
    }
    claim.update(overrides)
    return claim


def _matrix(claims, context=None):
    if context is None:
        context = {"expected_los": {}}
    features, names = build_classifier_features(claims, context=context)
    return features, names


def test_feature_matrix_matches_declared_names():
    features, names = _matrix([_claim()])
    assert len(names) == features.shape[1] == len(CLASSIFIER_FEATURE_NAMES)
    assert names == CLASSIFIER_FEATURE_NAMES
    assert len(set(names)) == len(names)


def test_single_claim_has_no_relational_signal():
    features, _ = _matrix([_claim()])
    row = features[0]
    copy_index = CLASSIFIER_FEATURE_NAMES.index("copy_group_size")
    exact_index = CLASSIFIER_FEATURE_NAMES.index("exact_copy_group_size")
    gap_index = CLASSIFIER_FEATURE_NAMES.index("min_same_patient_gap_days")
    assert row[copy_index] == 1.0
    assert row[exact_index] == 1.0
    assert row[gap_index] == _NO_PAIR_SENTINEL


def test_copy_group_sizes_flag_duplicates():
    claims = [
        _claim(),  # source
        _claim(patient_id="PAT-CLONE"),  # pure copy: same provider/codes/cost/date
        _claim(patient_id="PAT-SHIFT", admission_date="2025-04-10"),  # same copy key, later date
        _claim(provider_id="FAC-0002", cost_claimed=30_000),  # unrelated
    ]
    features, _ = _matrix(claims)
    copy_index = CLASSIFIER_FEATURE_NAMES.index("copy_group_size")
    exact_index = CLASSIFIER_FEATURE_NAMES.index("exact_copy_group_size")
    assert features[0][copy_index] == 3.0 and features[0][exact_index] == 2.0
    assert features[1][copy_index] == 3.0 and features[1][exact_index] == 2.0
    assert features[2][copy_index] == 3.0 and features[2][exact_index] == 1.0
    assert features[3][copy_index] == 1.0 and features[3][exact_index] == 1.0


def test_min_same_patient_gap_days_uses_patient_dates():
    claims = [
        _claim(patient_id="PAT-A", admission_date="2025-03-01"),
        _claim(patient_id="PAT-A", admission_date="2025-03-13"),
        _claim(patient_id="PAT-B", admission_date="2025-03-05"),
    ]
    features, _ = _matrix(claims)
    gap_index = CLASSIFIER_FEATURE_NAMES.index("min_same_patient_gap_days")
    # rows 0 and 1 belong to the same patient, 12 days apart; the single-visit patient is sentinel.
    assert features[0][gap_index] == 12.0
    assert features[1][gap_index] == 12.0
    assert features[2][gap_index] == _NO_PAIR_SENTINEL


def test_training_context_uses_normal_rows_only_and_scales_los():
    claims = [
        _claim(diagnosis_primary="I21", outpatient=False, length_of_stay=4, cost_claimed=10_000),
        _claim(diagnosis_primary="I21", outpatient=False, length_of_stay=6, cost_claimed=10_000),
        _claim(diagnosis_primary="I21", outpatient=False, length_of_stay=90, cost_claimed=10_000),
        _claim(diagnosis_primary="J18", outpatient=True, length_of_stay=7, cost_claimed=10_000),
    ]
    context = build_training_context(claims, np.asarray([0, 0, 1, 0]))
    index = CLASSIFIER_FEATURE_NAMES.index("los_vs_expected")
    features, _ = _matrix(claims, context=context)
    anomaly_row = features[2]
    benign_system_row = features[3]
    # median of normals is 5, so even the labelled anomaly is compared against 5 days.
    assert context["expected_los"][("I21", False)] == 5.0
    assert context["expected_los"][("J18", True)] == 7.0
    assert anomaly_row[index] == 90.0 / 5.0
    assert benign_system_row[index] == 1.0


def test_unsupported_service_flags_react_to_reference_codes():
    claims = [
        _claim(diagnosis_secondary=["I10", "E46"], procedure_codes=["36.10"]),
        _claim(procedure_codes=["36.10", "81.51"]),
    ]
    features, _ = _matrix(claims)
    e46_index = CLASSIFIER_FEATURE_NAMES.index("unsupported_secondary_E46_flag")
    code_index = CLASSIFIER_FEATURE_NAMES.index("unsupported_procedure_8151_flag")
    assert features[0][e46_index] == 1.0 and features[0][code_index] == 0.0
    assert features[1][e46_index] == 0.0 and features[1][code_index] == 1.0
