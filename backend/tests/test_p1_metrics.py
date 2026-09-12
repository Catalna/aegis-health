from backend.app.evaluation.metrics import (
    calibration_metrics,
    evaluate_ranking,
    latency_metrics,
)
from backend.app.evaluation.pipeline import EvaluationResult


def result(claim_id, label, score, anomaly_type="none", latency=10.0):
    return EvaluationResult(claim_id, label, anomaly_type, score, "high" if score >= 60 else "low", {}, "test", latency)


def test_ranking_metrics_measure_top_k_and_slices():
    rows = [
        result("A", 1, 90, "upcoding"),
        result("B", 0, 80),
        result("C", 1, 70, "phantom_billing"),
        result("D", 0, 60),
    ]
    metrics = evaluate_ranking(rows, k_values=(2, 4))

    assert metrics["status"] == "measured"
    assert metrics["precision_at_k"]["2"]["value"] == 0.5
    assert metrics["recall_at_k"]["2"]["value"] == 0.5
    assert metrics["average_precision"]["value"] > 0.5
    assert metrics["by_anomaly_type"]["upcoding"]["true_positive_count"] == 1


def test_metrics_return_not_computable_for_insufficient_k_or_labels():
    rows = [result("A", 1, 90, "upcoding"), result("B", 0, 10)]
    metrics = evaluate_ranking(rows, k_values=(50,))
    assert metrics["precision_at_k"]["50"]["status"] == "not_computable"
    assert calibration_metrics(rows)["status"] == "not_computable"


def test_latency_metrics_report_percentiles():
    metrics = latency_metrics([1.0, 2.0, 3.0, 4.0])
    assert metrics["status"] == "measured"
    assert metrics["count"] == 4
    assert metrics["p50_ms"] == 2.5
