import xml.etree.ElementTree as ET

import numpy as np

from backend.app.ml.evaluation_plots import (
    average_precision,
    confusion_matrix_chart,
    metric_bar_chart,
    precision_recall_curve,
    probability_scores,
    roc_auc,
    roc_curve,
    score_distribution_chart,
    select_threshold,
    threshold_metrics,
    threshold_sweep,
)
from backend.app.ml.svg_raster import svg_dimensions


def test_threshold_metrics_match_hand_computed_confusion_matrix():
    metrics = threshold_metrics([1, 1, 0, 0, 0], [0.9, 0.4, 0.8, 0.2, 0.1], 0.5)

    assert (metrics["true_positive"], metrics["false_negative"]) == (1, 1)
    assert (metrics["false_positive"], metrics["true_negative"]) == (1, 2)
    assert metrics["accuracy"] == 3 / 5
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["specificity"] == 2 / 3
    assert metrics["f1"] == 0.5
    assert abs(metrics["balanced_accuracy"] - (0.5 + 2 / 3) / 2) < 1e-12


def test_threshold_selection_maximizes_f1_on_supplied_scores_only():
    selection = select_threshold([1, 0, 0, 0], [0.9, 0.8, 0.2, 0.1])

    assert selection["status"] == "measured"
    assert selection["selection_rule"] == "max_f1_on_validation"
    assert selection["threshold"] == 0.9
    assert selection["validation_f1"] == 1.0


def test_ranking_metrics_handle_perfect_reversed_and_tied_scores():
    labels = [1, 1, 0, 0]
    assert roc_auc(labels, [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert roc_auc(labels, [0.1, 0.2, 0.8, 0.9]) == 0.0
    assert roc_auc([1, 0], [0.5, 0.5]) == 0.5
    assert roc_auc([1, 1], [0.2, 0.8]) is None

    curve = roc_curve(labels, [0.9, 0.8, 0.2, 0.1])
    assert curve["fpr"][0] == 0.0 and curve["tpr"][0] == 0.0
    assert curve["fpr"][-1] == 1.0 and curve["tpr"][-1] == 1.0


def test_precision_recall_curve_reports_the_same_average_precision():
    labels = [1, 0, 1, 0, 0, 1]
    scores = [0.9, 0.8, 0.7, 0.4, 0.3, 0.2]

    curve = precision_recall_curve(labels, scores)
    ap = average_precision(labels, scores)

    assert curve["ap"] == ap
    assert curve["recall"][0] == 0.0 and curve["precision"][0] == 1.0
    assert curve["recall"][-1] == 1.0


def test_probability_metrics_are_sane_for_confident_correct_scores():
    metrics = probability_scores([1, 1, 0, 0], [0.99, 0.9, 0.1, 0.01])

    assert metrics["brier_score"] < 0.01
    assert metrics["log_loss"] < 0.06
    assert metrics["expected_calibration_error"] <= 1.0
    assert metrics["prevalence"] == 0.5
    assert sum(item["count"] for item in metrics["calibration_bins"]) == 4


def test_threshold_sweep_is_monotonic_and_bounded():
    sweep = threshold_sweep([1, 0, 1, 0, 0], [0.9, 0.7, 0.4, 0.2, 0.1], points=21)

    assert len(sweep["thresholds"]) == 21
    assert all(left < right for left, right in zip(sweep["thresholds"], sweep["thresholds"][1:]))
    assert all(0.0 <= value <= 1.0 for value in sweep["f1"])


def test_svg_charts_are_well_formed_and_contain_no_nan_values():
    labels = [0] * 90 + [1] * 10
    scores = list(np.linspace(0.0, 1.0, 100))
    charts = [
        score_distribution_chart(labels, scores, 0.8),
        confusion_matrix_chart(threshold_metrics(labels, scores, 0.8)),
        metric_bar_chart([("Accuracy", 0.9), ("F1", 0.4)]),
    ]

    for chart in charts:
        root = ET.fromstring(chart)
        assert root.tag.endswith("svg")
        assert "nan" not in chart.lower()


def test_svg_dimensions_are_declared_for_rasterisation():
    chart = score_distribution_chart([0, 1], [0.1, 0.9], 0.5)
    assert svg_dimensions(chart) == (880, 470)
