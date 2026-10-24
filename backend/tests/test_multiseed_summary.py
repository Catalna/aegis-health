"""Unit tests untuk agregator multi-seed (pure function, tanpa I/O training)."""
import json
import math
from pathlib import Path

import pytest

from backend.app.ml.multiseed_summary import aggregate_reports, render_markdown


def _mini_report(
    seed: int,
    *,
    ap: float = 0.60,
    roc_auc: float = 0.90,
    operating_f1: float = 0.60,
) -> dict:
    return {
        "seed": seed,
        "dataset_version": "synthetic-v2.4.0-demonstrator",
        "synthetic_only": True,
        "train_n": 150_000,
        "validation_n": 50_000,
        "test_n": 50_000,
        "dataset_config_sha256": f"dataset-{seed}",
        "config_sha256": f"config-{seed}",
        "classifier_candidate_not_runtime": {
            "selection": {"selected": {"max_depth": 5, "scale_pos_weight": 3.0, "best_iteration": 300 + seed}},
            "baselines": {
                "logistic_regression_rule_flags": {"average_precision": 0.17},
            },
            "test_metrics": {
                "average_precision": ap,
                "roc_auc": roc_auc,
                "brier_score": 0.016,
                "expected_calibration_error": 0.016,
                "operating_point": {
                    "f1": operating_f1,
                    "precision": 0.80,
                    "recall": 0.50,
                    "accuracy": 0.98,
                },
                "f1_at_10pct": 0.30,
                "f1_at_5pct": 0.35,
                "f1_at_20pct": 0.25,
                "f1_at_1pct": 0.20,
                "by_anomaly_type": {
                    "cloning": {
                        "average_precision": ap / 10,
                        "operating_point": {"f1": 0.15},
                    },
                },
            },
        },
        "regressor": {
            "test_metrics": {
                "mape": 0.13,
                "mdape": 0.14,
                "medae": 600_000,
                "mae": 800_000,
                "rmse": 1_100_000,
                "r2": 0.86,
                "upper_interval_coverage": 0.90,
            }
        },
        "stress_test_metrics": {
            "test_enriched": {"metrics": {"average_precision": 0.83}},
            "ood": {"metrics": {"average_precision": 0.60}},
        },
    }


@pytest.mark.parametrize("num_reports", [1, 5])
def test_aggregate_reports_headline_values(num_reports):
    seeds = [42 + index for index in range(num_reports)]
    ap_values = [0.60, 0.62, 0.61, 0.63, 0.64][:num_reports]
    reports = [_mini_report(seed, ap=ap) for seed, ap in zip(seeds, ap_values)]

    summary = aggregate_reports(reports)
    assert summary["seeds"] == seeds
    assert summary["n_seeds"] == num_reports
    assert summary["synthetic_only"] is True

    ap_agg = summary["classifier"]["average_precision"]
    assert math.isclose(ap_agg["mean"], sum(ap_values) / num_reports)
    if num_reports == 5:
        assert math.isclose(ap_agg["max"], 0.64)
        assert math.isclose(ap_agg["min"], 0.60)
        assert ap_agg["stdev"] > 0.0
    else:
        assert ap_agg["stdev"] == 0.0

    # Per-tipe: nilai AP cloning efektif dikalikan 0.1 di mini-report
    per_type = summary["per_type"]["cloning"]["average_precision"]
    expected_mean = sum(v / 10 for v in ap_values) / num_reports
    assert math.isclose(per_type["mean"], expected_mean, abs_tol=1e-9)

    # Regressor + stress + baseline tersedia; fraksi regressor diskalakan ke persen
    assert math.isclose(summary["regressor"]["regressor_mape_pct"]["mean"], 13.0)
    assert math.isclose(summary["regressor"]["regressor_upper_interval_coverage_pct"]["mean"], 90.0)
    assert math.isclose(summary["stress"]["enriched_average_precision"]["mean"], 0.83)
    assert math.isclose(summary["baselines"]["baseline_logistic_regression_rule_flags_ap"]["mean"], 0.17)

    # Konfigurasi terpilih per seed dibawa kembali (provenance)
    assert len(summary["selections"]) == num_reports
    assert summary["selections"][0]["selected"]["max_depth"] == 5


def test_aggregate_reports_tolerates_missing_type_in_one_seed():
    r1 = _mini_report(42, ap=0.60)
    r2 = _mini_report(43, ap=0.62)
    del r2["classifier_candidate_not_runtime"]["test_metrics"]["by_anomaly_type"]

    summary = aggregate_reports([r1, r2])
    cloning = summary["per_type"]["cloning"]["average_precision"]
    assert len(cloning["values_by_seed"]) == 1
    assert math.isclose(cloning["mean"], 0.06)


def test_aggregate_reports_requires_at_least_one():
    with pytest.raises(ValueError):
        aggregate_reports([])


def test_render_markdown_contains_banner_and_spread():
    reports = [_mini_report(seed, ap=0.60 + i * 0.01) for i, seed in enumerate((42, 43, 44))]
    summary = aggregate_reports(reports)
    md = render_markdown(summary)

    assert "Data sintetis demonstrator" in md
    assert "bukan validasi performa BPJS" in md
    assert "42/43/44" in md
    assert "cloning" in md
    assert "±" in md  # mean ± stdev
    assert "| Seed | depth | scale_pos_weight | best_iteration |" in md
