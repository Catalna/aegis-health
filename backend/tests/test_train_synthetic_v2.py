from backend.app.ml.train_synthetic_v2 import build_cost_features, render_training_report


def _claim(cost=10_000):
    return {
        "diagnosis_primary": "I21",
        "diagnosis_secondary": ["I10"],
        "procedure_codes": ["36.10"],
        "patient_age": 67,
        "length_of_stay": 5,
        "severity_level": 2,
        "ina_cbg_severity": "II",
        "ina_cbg_code": "SIM-I-42",
        "regional_base_rate": 20_000,
        "facility_type": "RS",
        "facility_class": "B",
        "region": "java",
        "outpatient": False,
        "cost_claimed": cost,
    }


def test_cost_model_features_exclude_claimed_cost_but_support_ablation():
    normal, changed_cost = _claim(), _claim(cost=900_000)
    features, names = build_cost_features([normal])
    changed_features, changed_names = build_cost_features([changed_cost])
    without_severity, no_severity_names = build_cost_features([normal], include_severity=False)
    without_rate, no_rate_names = build_cost_features([normal], include_base_rate=False)

    assert names == changed_names
    assert features.tolist() == changed_features.tolist()
    assert "severity_level" in names and "ina_cbg_base_rate" in names
    assert "severity_level" not in no_severity_names
    assert "ina_cbg_base_rate" not in no_rate_names
    assert without_severity.shape[1] == len(no_severity_names)
    assert without_rate.shape[1] == len(no_rate_names)


def test_training_report_discloses_synthetic_data_and_test_sample_counts():
    report = render_training_report({
        "dataset_version": "synthetic-v2-demonstrator",
        "synthetic_only": True,
        "seed": 42,
        "config_sha256": "abc123",
        "train_n": 150_000,
        "validation_n": 50_000,
        "test_n": 50_000,
        "regressor": {"trained_on": "normal train claims only", "selected_config": "severity_and_base_rate", "test_metrics": {"normal_n": 48_500, "mape": 0.13, "medae": 6.0, "upper_interval_target_coverage": 0.9, "upper_interval_coverage": 0.9}},
        "classifier_candidate_not_runtime": {"test_metrics": {"n": 50_000, "average_precision": 0.4, "positive_n": 1_500}, "baselines": {}},
        "limitations": ["synthetic only"],
    })

    assert "not BPJS performance validation" in report
    assert "50,000" in report
    assert "classifier candidate" in report.lower()
