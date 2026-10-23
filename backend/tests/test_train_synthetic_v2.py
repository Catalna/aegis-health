from backend.app.ml.train_synthetic_v2 import _group_bootstrap_ap, build_cost_features, render_training_report


def _claim(cost=10_000):
    return {
        "diagnosis_primary": "I21",
        "diagnosis_secondary": ["I10"],
        "procedure_codes": ["36.10"],
        "medication_codes": ["ASPIRIN"],
        "special_group_types": [],
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
        "icu_indicator": False,
        "ventilator_used": False,
        "surgical_indicator": True,
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
    assert {"num_medications", "icu_indicator", "ventilator_used", "surgical_indicator"} <= set(names)
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
        "regressor": {"trained_on": "normal train claims only", "selected_config": "severity_and_base_rate", "test_metrics": {"normal_n": 48_500, "mape": 0.13, "medae": 6.0, "mae": 8.0, "rmse": 12.0, "r2": 0.95, "upper_interval_target_coverage": 0.9, "upper_interval_coverage": 0.9}},
        "classifier_candidate_not_runtime": {
            "test_metrics": {
                "n": 50_000,
                "average_precision": 0.4,
                "positive_n": 1_500,
                "roc_auc": 0.9,
                "brier_score": 0.1,
                "log_loss": 0.2,
                "expected_calibration_error": 0.05,
                "operating_point": {
                    "threshold": 0.5, "n": 50_000, "predicted_positive_n": 2_000, "alert_rate": 0.04,
                    "accuracy": 0.97, "precision": 0.5, "recall": 0.67, "specificity": 0.98, "f1": 0.57,
                    "balanced_accuracy": 0.82, "mcc": 0.55, "false_positive_rate": 0.02,
                    "false_negative_rate": 0.33, "true_positive": 1_000, "false_positive": 1_000,
                    "true_negative": 47_500, "false_negative": 500,
                },
            },
            "baselines": {},
        },
        "limitations": ["synthetic only"],
    })

    assert "not BPJS performance validation" in report
    assert "50,000" in report
    assert "classifier candidate" in report.lower()
    assert "Accuracy: 97.0000%" in report
    assert "F1: 0.5700" in report


def test_group_bootstrap_ap_is_reproducible_and_reports_sample_size():
    result = _group_bootstrap_ap(
        labels=[1, 0, 1, 0],
        scores=[0.9, 0.8, 0.7, 0.1],
        groups=["g1", "g1", "g2", "g3"],
        seed=42,
        replicates=25,
    )
    repeated = _group_bootstrap_ap(
        labels=[1, 0, 1, 0],
        scores=[0.9, 0.8, 0.7, 0.1],
        groups=["g1", "g1", "g2", "g3"],
        seed=42,
        replicates=25,
    )
    assert result == repeated
    assert result["group_n"] == 3
    assert result["replicates"] == 25
    assert result["ci95"][0] <= result["ci95"][1]


def test_training_loader_reads_v2_parquet_splits(tmp_path):
    import pandas as pd
    from backend.app.ml.train_synthetic_v2 import _read_split

    claim = {
        **_claim(),
        "claim_id": "CLM-TEST-0001",
        "patient_id": "PAT-TEST-0001",
        "provider_id": "FAC-TEST-0001",
        "doctor_id": "DR-TEST-00001",
        "medication_codes": ["ASPIRIN"],
        "icu_indicator": False,
        "ventilator_used": False,
        "surgical_indicator": True,
    }
    pd.DataFrame([claim]).to_parquet(tmp_path / "train.parquet", index=False)
    pd.DataFrame([{
        "claim_id": claim["claim_id"], "is_anomaly": False, "anomaly_type": "none",
        "difficulty": "none", "scenario_family": "natural_normal", "group_id": "g1", "label_confidence": 1.0,
    }]).to_parquet(tmp_path / "train_labels.parquet", index=False)

    claims, labels = _read_split(tmp_path, "train")
    assert claims[0]["medication_codes"] == ["ASPIRIN"]
    assert claims[0]["icu_indicator"] is False
    assert labels[0]["group_id"] == "g1"
