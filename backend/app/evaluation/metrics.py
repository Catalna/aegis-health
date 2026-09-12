"""JSON-serializable ranking and latency metrics for P1."""

from statistics import median

import numpy as np
from sklearn.metrics import average_precision_score

from backend.app.evaluation.pipeline import EvaluationResult


def _missing(reason: str) -> dict:
    return {"status": "not_computable", "reason": reason}


def _measured(value) -> dict:
    return {"status": "measured", "value": float(value)}


def _rank(rows: list[EvaluationResult]) -> list[EvaluationResult]:
    return sorted(rows, key=lambda row: (-row.score, row.claim_id))


def _slice_metrics(rows: list[EvaluationResult]) -> dict:
    output = {}
    for anomaly_type in sorted({row.anomaly_type for row in rows if row.label}):
        positives = [row for row in rows if row.anomaly_type == anomaly_type and row.label]
        ranked = _rank(rows)
        output[anomaly_type] = {
            "count": len(positives),
            "true_positive_count": sum(row.label for row in ranked if row.anomaly_type == anomaly_type),
            "top_rank": next((index + 1 for index, row in enumerate(ranked) if row.anomaly_type == anomaly_type), None),
        }
    return output


def evaluate_ranking(rows: list[EvaluationResult], k_values=(50, 100)) -> dict:
    if not rows:
        return {"status": "not_computable", "reason": "no evaluation rows"}
    ranked = _rank(rows)
    labels = np.asarray([row.label for row in ranked], dtype=int)
    positives = int(labels.sum())
    precision = {}
    recall = {}
    for k in k_values:
        key = str(k)
        if k <= 0 or k > len(ranked):
            precision[key] = _missing(f"K={k} exceeds row count {len(ranked)}")
            recall[key] = _missing(f"K={k} exceeds row count {len(ranked)}")
        elif positives == 0:
            precision[key] = _missing("no positive labels")
            recall[key] = _missing("no positive labels")
        else:
            hits = int(labels[:k].sum())
            precision[key] = _measured(hits / k)
            recall[key] = _measured(hits / positives)
    aggregate = {"status": "measured" if positives else "not_computable"}
    if positives:
        aggregate["value"] = float(average_precision_score(labels, [row.score for row in ranked]))
    else:
        aggregate["reason"] = "no positive labels"
    return {
        "status": "measured" if positives else "not_computable",
        "precision_at_k": precision,
        "recall_at_k": recall,
        "average_precision": aggregate,
        "by_anomaly_type": _slice_metrics(rows),
    }


def calibration_metrics(rows: list[EvaluationResult], probability_transform=None) -> dict:
    if probability_transform is None:
        return _missing("raw risk score is not a probability and no transform was supplied")
    if not rows or len({row.label for row in rows}) < 2:
        return _missing("calibration needs both positive and negative labels")
    probabilities = np.asarray([probability_transform(row.score) for row in rows], dtype=float)
    labels = np.asarray([row.label for row in rows], dtype=float)
    return _measured(float(np.mean((probabilities - labels) ** 2))) | {"metric": "brier_score"}


def latency_metrics(latencies_ms: list[float]) -> dict:
    if not latencies_ms:
        return _missing("no latency samples")
    values = sorted(float(value) for value in latencies_ms)
    return {
        "status": "measured",
        "count": len(values),
        "p50_ms": float(median(values)),
        "p95_ms": float(np.percentile(values, 95)),
    }
