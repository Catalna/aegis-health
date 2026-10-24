"""Train v2 candidate models with native XGBoost, using train/validation/test correctly.

The supervised classifier is a comparison candidate only; it is not injected into
the deterministic runtime risk score. Synthetic results are not BPJS validation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.ml.evaluation_plots import (
    ACCENT,
    AMBER,
    GRAY,
    VIOLET,
    ap_by_type_chart,
    confusion_matrix_chart,
    cost_scatter_chart,
    coverage_chart,
    metric_bar_chart,
    pr_curve_chart,
    precision_recall_curve,
    probability_scores,
    residual_histogram_chart,
    roc_auc,
    roc_curve,
    roc_curve_chart,
    score_distribution_chart,
    select_threshold,
    threshold_metrics,
    threshold_sweep,
    threshold_sweep_chart,
)
from backend.app.ml.svg_raster import render_svg_files
from backend.app.ml.v2_features import (
    build_classifier_features,
    build_cost_features,
    build_training_context,
)


def _read_split(input_dir: Path, split: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    claims_path = input_dir / f"{split}.csv"
    labels_path = input_dir / f"{split}_labels.csv"
    if claims_path.is_file() and labels_path.is_file():
        with claims_path.open(newline="", encoding="utf-8") as stream:
            claims = list(csv.DictReader(stream))
        with labels_path.open(newline="", encoding="utf-8") as stream:
            labels = list(csv.DictReader(stream))
    else:
        claims_path = input_dir / f"{split}.parquet"
        labels_path = input_dir / f"{split}_labels.parquet"
        if not claims_path.is_file() or not labels_path.is_file():
            raise FileNotFoundError(f"{split} needs claim and separate label CSV or Parquet files")
        try:
            import pandas as pd

            claims = pd.read_parquet(claims_path).to_dict(orient="records")
            labels = pd.read_parquet(labels_path).to_dict(orient="records")
        except Exception as exc:
            raise RuntimeError("Unable to load Parquet split; PyArrow must be available") from exc
    for claim in claims:
        for key in ("diagnosis_secondary", "procedure_codes", "medication_codes", "special_group_types"):
            if isinstance(claim[key], str):
                claim[key] = json.loads(claim[key])
            else:
                claim[key] = list(claim[key])
        for key in ("patient_age", "length_of_stay", "severity_level"):
            claim[key] = int(claim[key])
        for key in ("regional_base_rate", "cost_claimed"):
            claim[key] = float(claim[key])
        claim["outpatient"] = claim["outpatient"].lower() == "true" if isinstance(claim["outpatient"], str) else bool(claim["outpatient"])
        for key in ("icu_indicator", "ventilator_used", "surgical_indicator"):
            claim[key] = claim[key].lower() == "true" if isinstance(claim[key], str) else bool(claim[key])
    for label in labels:
        label["is_anomaly"] = label["is_anomaly"].lower() == "true" if isinstance(label["is_anomaly"], str) else bool(label["is_anomaly"])
        label["label_confidence"] = float(label["label_confidence"])
    return claims, labels


def _ap(labels: np.ndarray, scores: np.ndarray) -> float | None:
    positives = int(labels.sum())
    if not positives:
        return None
    order = np.lexsort((np.arange(len(scores)), -scores))
    ranked = labels[order]
    hit_count = 0
    total = 0.0
    for index, label in enumerate(ranked, start=1):
        if label:
            hit_count += 1
            total += hit_count / index
    return total / positives


def _group_bootstrap_ap(labels, scores, groups, seed: int = 42, replicates: int = 100) -> dict[str, Any]:
    labels = np.asarray(labels, dtype=np.int32)
    scores = np.asarray(scores, dtype=np.float64)
    groups = np.asarray(groups, dtype=object)
    if not (len(labels) == len(scores) == len(groups)):
        raise ValueError("labels, scores, and groups must have equal lengths")
    group_indices = {group: np.flatnonzero(groups == group) for group in sorted(set(groups.tolist()))}
    point = _ap(labels, scores)
    if point is None or len(group_indices) < 2 or replicates < 1:
        return {"status": "not_computable", "reason": "bootstrap needs positives, two groups, and one replicate"}
    rng = np.random.default_rng(seed)
    group_ids = list(group_indices)
    samples = []
    for _ in range(replicates):
        selected = rng.choice(group_ids, size=len(group_ids), replace=True)
        row_indices = np.concatenate([group_indices[group] for group in selected])
        value = _ap(labels[row_indices], scores[row_indices])
        if value is not None:
            samples.append(value)
    if not samples:
        return {"status": "not_computable", "reason": "no bootstrap replicate contained a positive label"}
    return {
        "status": "measured",
        "metric": "average_precision",
        "estimate": point,
        "ci95": [float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))],
        "group_n": len(group_indices),
        "replicates": replicates,
        "resampling_unit": "group_id",
    }


def _classification_slices(
    labels, scores, fields, seed: int, include_group_ci: bool = False, threshold: float | None = None
) -> dict[str, Any]:
    output = {}
    for field in fields:
        field_results = {}
        values = sorted({str(label[field]) for label in labels if label["is_anomaly"]})
        for value in values:
            targets = np.asarray([
                int(label["is_anomaly"] and str(label[field]) == value) for label in labels
            ], dtype=np.int32)
            result = _ranking_metrics(targets, scores)
            result["raw_positive_n"] = int(targets.sum())
            if threshold is not None:
                result["operating_point"] = threshold_metrics(targets, scores, threshold)
            if include_group_ci:
                result["average_precision_group_bootstrap_ci95"] = _group_bootstrap_ap(
                    targets, scores, [label["group_id"] for label in labels], seed=seed
                )
            field_results[value] = result
        output[field] = field_results
    return output


def _ranking_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    order = np.lexsort((np.arange(len(scores)), -scores))
    positives = int(labels.sum())
    output: dict[str, Any] = {
        "n": int(len(labels)),
        "positive_n": positives,
        "average_precision": _ap(labels, scores),
        "roc_auc": roc_auc(labels, scores),
    }
    for percent in (1, 5, 10, 20):
        k = max(1, math.ceil(len(labels) * percent / 100)) if len(labels) else 0
        hits = int(labels[order[:k]].sum()) if k else 0
        output[f"precision_at_{percent}pct"] = hits / k if k else None
        output[f"recall_at_{percent}pct"] = hits / positives if positives else None
        if k and positives:
            precision = hits / k
            recall = hits / positives
            output[f"f1_at_{percent}pct"] = (
                2 * precision * recall / (precision + recall) if precision + recall else 0.0
            )
        else:
            output[f"f1_at_{percent}pct"] = None
    return output


def render_training_report(artifact: dict[str, Any]) -> str:
    regressor = artifact["regressor"]
    reg_metrics = regressor["test_metrics"]
    classifier = artifact["classifier_candidate_not_runtime"]
    clf_metrics = classifier["test_metrics"]
    lines = [
        "# Synthetic v2 Model Training & Evaluation",
        "",
        "> **Synthetic demonstrator only — not BPJS performance validation.**",
        "",
        f"- Dataset version: `{artifact['dataset_version']}`",
        f"- Train / validation / test: {artifact['train_n']:,} / {artifact['validation_n']:,} / {artifact['test_n']:,}",
        f"- Seed: `{artifact['seed']}`",
        f"- Config SHA-256: `{artifact['config_sha256']}`",
        "- Test set was not used for feature selection or hyperparameter tuning.",
        "",
        "## Cost benchmark regressor",
        "",
        f"- Training rows: {regressor['trained_on']}",
        f"- Validation-only selected ablation: `{regressor['selected_config']}`",
        f"- Test normal n: {reg_metrics['normal_n']:,}",
        f"- Test MAPE: {reg_metrics['mape']:.3%}; MedAE: {reg_metrics['medae']:,.2f}",
        f"- Test MAE: {reg_metrics.get('mae', float('nan')):,.2f}; RMSE: {reg_metrics.get('rmse', float('nan')):,.2f}; "
        f"R²: {reg_metrics.get('r2', float('nan')):.4f}",
        f"- Upper interval target coverage: {reg_metrics['upper_interval_target_coverage']:.0%}; measured: {reg_metrics['upper_interval_coverage']:.3%}",
        "",
        "## Supervised classifier candidate (not runtime)",
        "",
        f"- Test n: {clf_metrics['n']:,}; positive n: {clf_metrics['positive_n']:,}",
        f"- Average Precision: {clf_metrics['average_precision']:.4f}",
        f"- ROC-AUC: {clf_metrics['roc_auc']:.4f}" if clf_metrics.get("roc_auc") is not None else "- ROC-AUC: n/a",
        "- Baseline Average Precision:",
    ]
    for name, metrics in classifier["baselines"].items():
        lines.append(f"  - {name}: {metrics['average_precision']:.4f} (n={metrics['n']:,}, positives={metrics['positive_n']:,})")
    selection = classifier.get("selection")
    if selection:
        lines.extend(["", "### Classifier configuration (selected on validation only)", ""])
        for item in selection["candidates"]:
            lines.append(
                f"- depth {item['max_depth']}, scale_pos_weight {item['scale_pos_weight']:.0f}: "
                f"validation AP {item['validation_average_precision']:.4f} @ iteration {item['best_iteration']}"
            )
        chosen = selection["selected"]
        lines.append(
            f"- Selected: depth {chosen['max_depth']}, scale_pos_weight {chosen['scale_pos_weight']:.0f}, "
            f"iteration {chosen['best_iteration']}; the test set played no part in this choice."
        )
    importance = classifier.get("feature_importance_gain_top10")
    if importance:
        lines.extend(["", "### Fitur paling berpengaruh (gain)", ""])
        lines.extend(f"- `{item['feature']}`: {item['gain']:,.0f}" for item in importance[:5])
    operating = clf_metrics.get("operating_point")
    if operating:
        lines.extend([
            "",
            f"### Operating point (threshold {operating['threshold']:.4f}, selected on validation)",
            "",
            f"- Accuracy: {operating['accuracy']:.4%}; Precision: {operating['precision']:.4%}; "
            f"Recall: {operating['recall']:.4%}; F1: {operating['f1']:.4f}",
            f"- Specificity: {operating['specificity']:.4%}; Balanced accuracy: {operating['balanced_accuracy']:.4%}; "
            f"MCC: {operating['mcc']:.4f}",
            f"- Brier score: {clf_metrics.get('brier_score', float('nan')):.4f}; "
            f"Log loss: {clf_metrics.get('log_loss', float('nan')):.4f}; "
            f"ECE: {clf_metrics.get('expected_calibration_error', float('nan')):.4f}",
            f"- Alerts: {operating['predicted_positive_n']:,} of {operating['n']:,} "
            f"({operating['alert_rate']:.3%}); TP={operating['true_positive']:,}, FP={operating['false_positive']:,}, "
            f"TN={operating['true_negative']:,}, FN={operating['false_negative']:,}",
            "- The threshold was fitted on validation only and then frozen for test; test labels never selected it.",
        ])
    lines.extend(["", "### Natural test by anomaly type", ""])
    for anomaly_type, item in clf_metrics.get("by_anomaly_type", {}).items():
        type_op = item.get("operating_point", {})
        f1_text = f", F1={type_op['f1']:.3f}" if type_op else ""
        ap_text = f"{item['average_precision']:.4f}" if item["average_precision"] is not None else "n/a"
        lines.append(
            f"- `{anomaly_type}`: positives={item['raw_positive_n']:,}, AP={ap_text}{f1_text}"
        )
    classifier_ci = clf_metrics.get("average_precision_group_bootstrap_ci95", {})
    if classifier_ci.get("status") == "measured":
        lines[lines.index("- Test set was not used for feature selection or hyperparameter tuning.")] += (
            f" Aggregate AP group-bootstrap 95% CI: {classifier_ci['ci95'][0]:.4f}–{classifier_ci['ci95'][1]:.4f} "
            f"(groups={classifier_ci['group_n']:,}, resamples={classifier_ci['replicates']})."
        )
    for split, result in artifact.get("stress_test_metrics", {}).items():
        metric = result["metrics"]
        split_label = {"ood": "OOD", "test_enriched": "Enriched"}.get(split, split.replace("_", " ").title())
        lines.extend([
            "",
            f"## {split_label} stress evaluation",
            "",
            f"- Overall AP: {metric['average_precision']:.4f} (n={metric['n']:,}, positives={metric['positive_n']:,}).",
        ])
        ci = result.get("group_bootstrap_ci95", {})
        if ci.get("status") == "measured":
            lines.append(f"- Group-bootstrap AP 95% CI: {ci['ci95'][0]:.4f}–{ci['ci95'][1]:.4f} (groups={ci['group_n']:,}).")
        if result.get("by_anomaly_type"):
            lines.extend(["", "### By anomaly type", ""])
            for anomaly_type, item in result.get("by_anomaly_type", {}).items():
                type_ci = item.get("average_precision_group_bootstrap_ci95", {})
                ci_text = f"; group CI {type_ci['ci95'][0]:.3f}–{type_ci['ci95'][1]:.3f}" if type_ci.get("status") == "measured" else ""
                type_op = item.get("operating_point", {})
                f1_text = f", F1={type_op['f1']:.3f}" if type_op else ""
                lines.append(f"- `{anomaly_type}`: positives={item['raw_positive_n']:,}, AP={item['average_precision']:.4f}{f1_text}{ci_text}")
    figures = artifact.get("figures", {})
    if figures:
        lines.extend(["", "## Figures", ""])
        for item in sorted(figures.values(), key=lambda figure: figure["path"]):
            lines.extend([f"### {item['title']}", "", f"![{item['title']}]({item['path']})", ""])
    lines.extend(["", "## Limitations", ""])
    lines.append(
        "- Accuracy is inflated by the synthetic 3% anomaly prevalence; F1, average precision and recall are the primary balanced metrics."
    )
    lines.extend(f"- {limitation}" for limitation in artifact["limitations"])
    lines.append("")
    return "\n".join(lines)


def _logistic_rule_baseline(train_claims, train_labels, test_claims) -> np.ndarray:
    def rule_matrix(claims):
        return np.asarray([
            [
                abs(float(c["cost_claimed"]) - float(c["regional_base_rate"])) / max(1.0, float(c["regional_base_rate"])),
                float(int(c["severity_level"]) >= 3 and not c["procedure_codes"]),
                float(int(c["length_of_stay"]) > 14),
                float(len(c["diagnosis_secondary"]) >= 2),
            ] for c in claims
        ], dtype=np.float64)

    x_train, x_test = rule_matrix(train_claims), rule_matrix(test_claims)
    center = x_train.mean(axis=0)
    scale = np.maximum(x_train.std(axis=0), 1e-6)
    x_train = np.column_stack((np.ones(len(x_train)), (x_train - center) / scale))
    x_test = np.column_stack((np.ones(len(x_test)), (x_test - center) / scale))
    y = np.asarray([int(label["is_anomaly"]) for label in train_labels], dtype=float)
    weights = np.zeros(x_train.shape[1], dtype=float)
    for _ in range(800):
        probability = 1.0 / (1.0 + np.exp(-np.clip(x_train @ weights, -30, 30)))
        gradient = x_train.T @ (probability - y) / len(y)
        gradient[1:] += 0.01 * weights[1:]
        weights -= 0.15 * gradient
    return 1.0 / (1.0 + np.exp(-np.clip(x_test @ weights, -30, 30)))


def train_synthetic_v2(
    input_dir: Path, output_dir: Path, seed: int = 42, report_path: Path | None = None
) -> dict[str, Any]:
    try:
        import xgboost as xgb
    except Exception as exc:
        raise RuntimeError("native XGBoost is unavailable") from exc
    metadata = json.loads((input_dir / "schema.json").read_text(encoding="utf-8"))
    train_claims, train_labels = _read_split(input_dir, "train")
    val_claims, val_labels = _read_split(input_dir, "validation")
    test_claims, test_labels = _read_split(input_dir, "test")
    train_y = np.asarray([int(label["is_anomaly"]) for label in train_labels], dtype=np.int32)
    val_y = np.asarray([int(label["is_anomaly"]) for label in val_labels], dtype=np.int32)
    test_y = np.asarray([int(label["is_anomaly"]) for label in test_labels], dtype=np.int32)

    train_normal = train_y == 0
    val_normal = val_y == 0
    test_normal = test_y == 0
    variants = []
    reg_params = {"objective": "reg:squarederror", "max_depth": 5, "eta": 0.05, "subsample": 0.8,
                  "colsample_bytree": 0.9, "tree_method": "hist", "nthread": 4, "seed": seed}
    for include_severity, include_base_rate, name in (
        (True, True, "severity_and_base_rate"),
        (False, True, "without_severity"),
        (True, False, "without_base_rate"),
    ):
        x_train, feature_names = build_cost_features(train_claims, include_severity=include_severity, include_base_rate=include_base_rate)
        x_val, _ = build_cost_features(val_claims, include_severity=include_severity, include_base_rate=include_base_rate)
        reg = xgb.train(reg_params, xgb.DMatrix(x_train[train_normal], label=np.asarray([c["cost_claimed"] for c in train_claims], dtype=np.float32)[train_normal]), num_boost_round=180)
        val_prediction = reg.predict(xgb.DMatrix(x_val[val_normal]))
        val_actual = np.asarray([c["cost_claimed"] for c in val_claims], dtype=np.float64)[val_normal]
        val_medae = float(np.median(np.abs(val_actual - val_prediction)))
        variants.append({
            "name": name,
            "include_severity": include_severity,
            "include_base_rate": include_base_rate,
            "feature_names": feature_names,
            "validation_medae": val_medae,
            "validation_mape": float(np.mean(np.abs(val_actual - val_prediction) / np.maximum(val_actual, 1.0))),
            "booster": reg,
        })

    selected = min(variants, key=lambda item: (item["validation_medae"], item["name"]))
    chosen = xgb.train(reg_params, xgb.DMatrix(
        build_cost_features(train_claims, include_severity=selected["include_severity"], include_base_rate=selected["include_base_rate"])[0][train_normal],
        label=np.asarray([c["cost_claimed"] for c in train_claims], dtype=np.float32)[train_normal],
    ), num_boost_round=180)
    x_val, _ = build_cost_features(val_claims, include_severity=selected["include_severity"], include_base_rate=selected["include_base_rate"])
    val_predictions = chosen.predict(xgb.DMatrix(x_val[val_normal]))
    val_actual = np.asarray([c["cost_claimed"] for c in val_claims], dtype=np.float64)[val_normal]
    residual_margin = float(np.quantile(np.maximum(0.0, val_actual - val_predictions), 0.90, method="higher"))

    # Final test is evaluated once after the validation-only feature decision.
    x_test, _ = build_cost_features(test_claims, include_severity=selected["include_severity"], include_base_rate=selected["include_base_rate"])
    test_cost = np.asarray([c["cost_claimed"] for c in test_claims], dtype=np.float64)
    test_predictions = chosen.predict(xgb.DMatrix(x_test[test_normal]))
    test_actual = test_cost[test_normal]
    test_upper = test_predictions + residual_margin
    absolute_error = np.abs(test_actual - test_predictions)
    signed_error = test_predictions - test_actual
    ss_residual = float(np.sum(signed_error ** 2))
    ss_total = float(np.sum((test_actual - test_actual.mean()) ** 2))
    relative_error = signed_error / np.maximum(test_actual, 1.0)
    decile_rows = []
    decile_order = np.argsort(test_predictions)
    for index, rows in enumerate(np.array_split(decile_order, 10), start=1):
        decile_rows.append({
            "decile": index,
            "n": int(len(rows)),
            "mean_prediction": float(test_predictions[rows].mean()),
            "coverage": float(np.mean(test_actual[rows] <= test_upper[rows])),
        })
    regressor_test = {
        "normal_n": int(test_normal.sum()),
        "mape": float(np.mean(absolute_error / np.maximum(test_actual, 1.0))),
        "medae": float(np.median(absolute_error)),
        "mdape": float(np.median(absolute_error / np.maximum(test_actual, 1.0))),
        "mae": float(np.mean(absolute_error)),
        "rmse": float(math.sqrt(np.mean(signed_error ** 2))),
        "r2": 1.0 - ss_residual / ss_total if ss_total else 0.0,
        "upper_interval_target_coverage": 0.90,
        "upper_interval_coverage": float(np.mean(test_actual <= test_upper)),
        "upper_residual_margin": residual_margin,
        "deciles": decile_rows,
    }

    classifier_context = build_training_context(train_claims, train_y)
    train_classifier_x, classifier_features = build_classifier_features(train_claims, context=classifier_context)
    validation_classifier_x, _ = build_classifier_features(val_claims, context=classifier_context)
    test_classifier_x, _ = build_classifier_features(test_claims, context=classifier_context)
    d_train = xgb.DMatrix(train_classifier_x, label=train_y, feature_names=classifier_features)
    d_validation = xgb.DMatrix(validation_classifier_x, label=val_y, feature_names=classifier_features)
    base_class_params = {
        "objective": "binary:logistic", "eval_metric": "aucpr", "eta": 0.05,
        "subsample": 0.8, "colsample_bytree": 0.9, "tree_method": "hist", "nthread": 4, "seed": seed,
    }
    grid = []
    for max_depth in (5, 6):
        for scale_pos_weight in (1.0, 3.0):
            booster = xgb.train(
                {**base_class_params, "max_depth": max_depth, "scale_pos_weight": scale_pos_weight},
                d_train,
                num_boost_round=400,
                evals=[(d_validation, "validation")],
                early_stopping_rounds=50,
                verbose_eval=False,
            )
            grid.append({
                "max_depth": max_depth,
                "scale_pos_weight": scale_pos_weight,
                "best_iteration": int(booster.best_iteration) + 1,
                "validation_average_precision": float(booster.best_score),
                "booster": booster,
            })
    candidate = max(
        grid,
        key=lambda item: (item["validation_average_precision"], -item["max_depth"], -item["scale_pos_weight"]),
    )
    classifier = candidate["booster"]
    prediction_range = (0, candidate["best_iteration"])

    def _booster_scores(features: np.ndarray) -> np.ndarray:
        return classifier.predict(
            xgb.DMatrix(features, feature_names=classifier_features), iteration_range=prediction_range
        )

    classifier_scores = _booster_scores(test_classifier_x)
    validation_classifier_scores = _booster_scores(validation_classifier_x)
    classifier_selection = {
        "objective": "validation AUCPR with early stopping; selection never touches the test set",
        "num_boost_round_cap": 400,
        "early_stopping_rounds": 50,
        "candidates": [
            {k: v for k, v in item.items() if k != "booster"}
            for item in sorted(grid, key=lambda i: (i["max_depth"], i["scale_pos_weight"]))
        ],
        "selected": {
            key: candidate[key]
            for key in ("max_depth", "scale_pos_weight", "best_iteration", "validation_average_precision")
        },
    }
    threshold_selection = select_threshold(val_y, validation_classifier_scores)
    operating_threshold = float(threshold_selection["threshold"])
    logistic_scores = _logistic_rule_baseline(train_claims, train_labels, test_claims)
    random_scores = np.random.default_rng(seed).random(len(test_y))
    benchmark_scores = np.asarray([
        abs(claim["cost_claimed"] - claim["regional_base_rate"]) / max(1.0, claim["regional_base_rate"])
        for claim in test_claims
    ])
    test_classifier_metrics = _ranking_metrics(test_y, classifier_scores)
    test_probability_metrics = probability_scores(test_y, classifier_scores)
    test_classifier_metrics.update(test_probability_metrics)
    natural_slices = _classification_slices(
        test_labels,
        classifier_scores,
        ("anomaly_type", "difficulty", "scenario_family"),
        seed=seed,
        threshold=operating_threshold,
    )
    test_classifier_metrics.update({
        f"by_{dimension}": values for dimension, values in natural_slices.items()
    })
    test_classifier_metrics["operating_point"] = {
        **threshold_metrics(test_y, classifier_scores, operating_threshold),
        "roc_auc": test_classifier_metrics["roc_auc"],
        "brier_score": test_probability_metrics["brier_score"],
        "log_loss": test_probability_metrics["log_loss"],
        "expected_calibration_error": test_probability_metrics["expected_calibration_error"],
        "threshold_selection": threshold_selection,
    }
    test_classifier_metrics["validation_operating_point"] = {
        **threshold_metrics(val_y, validation_classifier_scores, operating_threshold),
        **threshold_selection,
    }
    test_classifier_metrics["average_precision_group_bootstrap_ci95"] = _group_bootstrap_ap(
        test_y, classifier_scores, [label["group_id"] for label in test_labels], seed=seed
    )
    stress_test_metrics = {}
    for split in ("test_enriched", "ood"):
        stress_claims, stress_labels = _read_split(input_dir, split)
        stress_x, _ = build_classifier_features(stress_claims, context=classifier_context)
        stress_y = np.asarray([int(label["is_anomaly"]) for label in stress_labels], dtype=np.int32)
        stress_scores = _booster_scores(stress_x)
        anomaly_slices = _classification_slices(
            stress_labels,
            stress_scores,
            ("anomaly_type",),
            seed=seed,
            include_group_ci=True,
            threshold=operating_threshold,
        )["anomaly_type"]
        stress_test_metrics[split] = {
            "metrics": _ranking_metrics(stress_y, stress_scores),
            "operating_point": threshold_metrics(stress_y, stress_scores, operating_threshold),
            "group_bootstrap_ci95": _group_bootstrap_ap(
                stress_y, stress_scores, [label["group_id"] for label in stress_labels], seed=seed
            ),
            "by_anomaly_type": anomaly_slices,
            "by_difficulty": _classification_slices(
                stress_labels, stress_scores, ("difficulty",), seed=seed, threshold=operating_threshold
            )["difficulty"],
            "by_scenario_family": _classification_slices(
                stress_labels, stress_scores, ("scenario_family",), seed=seed, threshold=operating_threshold
            )["scenario_family"],
        }

    sweep = threshold_sweep(val_y, validation_classifier_scores)
    test_pr = precision_recall_curve(test_y, classifier_scores)
    pr_curves = [{
        "label": f"Model · AP {test_pr['ap']:.3f}",
        "recall": test_pr["recall"],
        "precision": test_pr["precision"],
        "ap": test_pr["ap"],
        "color": ACCENT,
        "primary": True,
    }]
    for label, scores, color, dash in (
        ("Acak", random_scores, GRAY, "5 5"),
        ("Benchmark", benchmark_scores, AMBER, None),
        ("Rule flags", logistic_scores, VIOLET, None),
    ):
        curve = precision_recall_curve(test_y, scores)
        pr_curves.append({
            "label": f"{label} · AP {curve['ap']:.3f}" if curve["ap"] is not None else label,
            "recall": curve["recall"],
            "precision": curve["precision"],
            "ap": curve["ap"],
            "color": color,
            "dash": dash,
        })
    roc = roc_curve(test_y, classifier_scores)
    operating = test_classifier_metrics["operating_point"]
    metric_items = [
        ("Accuracy", operating["accuracy"]),
        ("Precision", operating["precision"]),
        ("Recall", operating["recall"]),
        ("Specificity", operating["specificity"]),
        ("F1", operating["f1"]),
        ("Balanced accuracy", operating["balanced_accuracy"]),
        ("ROC-AUC", test_classifier_metrics["roc_auc"] or 0.0),
    ]
    figures = {
        "metric_bars": metric_bar_chart(metric_items),
        "confusion": confusion_matrix_chart(operating),
        "pr_curve": pr_curve_chart(pr_curves),
        "roc_curve": roc_curve_chart(roc["fpr"], roc["tpr"], roc["auc"]),
        "threshold_sweep": threshold_sweep_chart(sweep, operating_threshold),
        "score_distribution": score_distribution_chart(test_y, classifier_scores, operating_threshold),
        "ap_by_type": ap_by_type_chart(
            stress_test_metrics["test_enriched"]["by_anomaly_type"],
            "Average Precision per tipe anomali",
            "Enriched test: 150 positif per tipe plus volume normal seimbang; ambang ditransfer dari validation.",
        ),
        "cost_scatter": cost_scatter_chart(test_actual, test_predictions, seed=seed),
        "residuals": residual_histogram_chart(relative_error),
        "coverage": coverage_chart(regressor_test["deciles"]),
    }
    figure_files = {
        "metric_bars": ("06_ringkasan_metrik.png", "Ringkasan metrik klasifikasi"),
        "confusion": ("05_confusion_matrix.png", "Confusion matrix pada ambang terpilih"),
        "pr_curve": ("02_precision_recall.png", "Kurva Precision–Recall"),
        "roc_curve": ("03_roc_curve.png", "Kurva ROC"),
        "threshold_sweep": ("04_sapuan_ambang.png", "Sapuan ambang keputusan"),
        "score_distribution": ("01_distribusi_skor.png", "Distribusi skor model"),
        "ap_by_type": ("07_ap_per_tipe.png", "Average Precision per tipe anomali"),
        "cost_scatter": ("08_prediksi_biaya.png", "Prediksi vs biaya aktual"),
        "residuals": ("09_error_regressor.png", "Distribusi error relatif regressor"),
        "coverage": ("10_coverage_desil.png", "Coverage batas atas per desil"),
    }
    figure_metadata = {
        key: {"title": title, "path": f"figures/{filename}"}
        for key, (filename, title) in figure_files.items()
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    reg_path = output_dir / "xgboost_regressor_synthetic_v2.json"
    classifier_path = output_dir / "xgboost_classifier_candidate_synthetic_v2.json"
    chosen.save_model(reg_path)
    classifier.save_model(classifier_path)
    config_hash = hashlib.sha256(json.dumps({
        "regression": reg_params,
        "classifier": base_class_params,
        "classifier_grid": {"depths": [5, 6], "scale_pos_weight": [1.0, 3.0],
                            "num_boost_round_cap": 400, "early_stopping_rounds": 50},
        "seed": seed,
        "num_boost_round": 180,
        "dataset_config_sha256": metadata.get("config_sha256"),
        "dataset_version": metadata["dataset_version"],
    }, sort_keys=True).encode()).hexdigest()
    artifact = {
        "dataset_version": metadata["dataset_version"],
        "synthetic_only": True,
        "seed": seed,
        "config_sha256": config_hash,
        "dataset_config_sha256": metadata.get("config_sha256"),
        "train_n": len(train_claims),
        "validation_n": len(val_claims),
        "test_n": len(test_claims),
        "regressor": {
            "trained_on": "normal train claims only",
            "features": selected["feature_names"],
            "validation_ablation": [{key: value for key, value in item.items() if key != "booster"} for item in variants],
            "selected_config": selected["name"],
            "test_metrics": regressor_test,
            "model_file": reg_path.name,
        },
        "classifier_candidate_not_runtime": {
            "features": classifier_features,
            "selection": classifier_selection,
            "feature_importance_gain_top10": [
                {"feature": name, "gain": round(value, 2)}
                for name, value in sorted(
                    classifier.get_score(importance_type="gain").items(), key=lambda kv: -kv[1]
                )[:10]
            ],
            "test_metrics": test_classifier_metrics,
            "baselines": {
                "random": _ranking_metrics(test_y, random_scores),
                "absolute_benchmark_deviation": _ranking_metrics(test_y, benchmark_scores),
                "logistic_regression_rule_flags": _ranking_metrics(test_y, logistic_scores),
            },
            "model_file": classifier_path.name,
        },
        "stress_test_metrics": stress_test_metrics,
        "figures": figure_metadata,
        "limitations": [
            "All claims and labels are synthetic; this does not validate BPJS performance.",
            "Test set was not used for feature or hyperparameter selection; the classifier threshold was fitted on validation only.",
            "Precision depends strongly on the synthetic 3% prevalence and is not an operational alert budget.",
            "Relational features (duplicate groups, per-patient gaps, expected-LOS benchmark) are computed per dataset split; the runtime scorer does not use them.",
            "Repeat-billing and cloning AP is bounded by designed legit readmission/duplicate hard negatives that share the same relational pattern.",
            "Grouped bootstrap intervals are single-seed; multi-seed training/evaluation is still pending.",
            "Natural-test per-type confidence intervals are reported via the separate enriched and OOD slices, not as natural-prevalence estimates.",
        ],
    }
    artifact_path = output_dir / "synthetic_v2_training_report.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path = output_dir / "synthetic_v2_training_report.md"
    markdown_path.write_text(render_training_report(artifact), encoding="utf-8")
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        figures_dir = report_path.parent / "figures"
        render_svg_files(
            figures,
            {key: figures_dir / filename for key, (filename, _title) in figure_files.items()},
        )
        report_path.write_text(render_training_report(artifact), encoding="utf-8")
        print(f"Figures: {figures_dir}")
    print(f"Training report: {artifact_path}")
    print(f"Selected regressor: {selected['name']} (validation MedAE={selected['validation_medae']:.2f})")
    print(
        f"Selected classifier: depth {candidate['max_depth']}, scale_pos_weight {candidate['scale_pos_weight']}, "
        f"iteration {candidate['best_iteration']} (validation AP {candidate['validation_average_precision']:.4f})"
    )
    print(f"Classifier candidate test AP: {artifact['classifier_candidate_not_runtime']['test_metrics']['average_precision']}")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="directory with v2 split CSV/Parquet files and schema.json")
    parser.add_argument("--out", type=Path, default=Path("backend/models_trained/synthetic_v2"))
    parser.add_argument("--seed", type=int, default=42)
    root = Path(__file__).resolve().parents[3]
    parser.add_argument("--report", type=Path, default=root / "docs/EVALUATION_REPORT.md")
    args = parser.parse_args()
    train_synthetic_v2(args.dataset, args.out, seed=args.seed, report_path=args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
