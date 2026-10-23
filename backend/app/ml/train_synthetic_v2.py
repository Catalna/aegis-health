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

from backend.app.data.synthetic_v2.generator import DIAGNOSIS_CATALOG


_FACILITY = {value: index for index, value in enumerate(("RS", "KLINIK", "PUSKESMAS"))}
_CLASS = {value: index for index, value in enumerate(("A", "B", "C", "D"))}
_REGION = {value: index for index, value in enumerate(("sumatra", "java", "kalimantan", "sulawesi", "bali_nusa", "maluku_papua"))}
_DIAGNOSIS = {value: index for index, value in enumerate(DIAGNOSIS_CATALOG)}


def build_cost_features(
    claims: list[dict[str, Any]], *, include_severity: bool = True, include_base_rate: bool = True
) -> tuple[np.ndarray, list[str]]:
    """Build cost-regression inputs without claimed cost or any derived target feature."""
    names = [
        "primary_diag_encoded", "num_secondary_diags", "num_procedures", "patient_age",
        "length_of_stay", "outpatient", "facility_type", "facility_class", "region",
    ]
    if include_severity:
        names.append("severity_level")
    if include_base_rate:
        names.append("ina_cbg_base_rate")
    matrix = []
    for claim in claims:
        row = [
            float(_DIAGNOSIS.get(claim["diagnosis_primary"], 0)),
            float(len(claim.get("diagnosis_secondary", []))),
            float(len(claim.get("procedure_codes", []))),
            float(claim.get("patient_age", 0)),
            float(claim.get("length_of_stay", 0)),
            float(bool(claim.get("outpatient", False))),
            float(_FACILITY.get(claim.get("facility_type"), -1)),
            float(_CLASS.get(claim.get("facility_class"), -1)),
            float(_REGION.get(claim.get("region"), -1)),
        ]
        if include_severity:
            row.append(float(claim.get("severity_level", 1)))
        if include_base_rate:
            row.append(float(claim.get("regional_base_rate", 0)))
        matrix.append(row)
    return np.asarray(matrix, dtype=np.float32), names


def build_classifier_features(claims: list[dict[str, Any]]) -> tuple[np.ndarray, list[str]]:
    base, names = build_cost_features(claims)
    extras = np.asarray([
        [
            math.log1p(max(0.0, float(claim.get("cost_claimed", 0)))),
            float(claim.get("cost_claimed", 0)) / max(1.0, float(claim.get("regional_base_rate", 0))),
            float(float(claim.get("length_of_stay", 0)) > 14),
            float(float(claim.get("severity_level", 1)) >= 3 and not claim.get("procedure_codes")),
        ]
        for claim in claims
    ], dtype=np.float32)
    return np.column_stack((base, extras)), [*names, "cost_claimed_log", "cost_vs_base_rate", "long_los_flag", "unsupported_severity_flag"]


def _read_csv_split(input_dir: Path, split: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    claims_path = input_dir / f"{split}.csv"
    labels_path = input_dir / f"{split}_labels.csv"
    if not claims_path.is_file() or not labels_path.is_file():
        raise FileNotFoundError(f"{split} CSV and separate labels CSV are required")
    with claims_path.open(newline="", encoding="utf-8") as stream:
        claims = list(csv.DictReader(stream))
    with labels_path.open(newline="", encoding="utf-8") as stream:
        labels = list(csv.DictReader(stream))
    for claim in claims:
        claim["diagnosis_secondary"] = json.loads(claim["diagnosis_secondary"])
        claim["procedure_codes"] = json.loads(claim["procedure_codes"])
        for key in ("patient_age", "length_of_stay", "severity_level"):
            claim[key] = int(claim[key])
        for key in ("regional_base_rate", "cost_claimed"):
            claim[key] = float(claim[key])
        claim["outpatient"] = claim["outpatient"].lower() == "true"
    for label in labels:
        label["is_anomaly"] = label["is_anomaly"].lower() == "true"
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


def _ranking_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    order = np.lexsort((np.arange(len(scores)), -scores))
    positives = int(labels.sum())
    output: dict[str, Any] = {"n": int(len(labels)), "positive_n": positives, "average_precision": _ap(labels, scores)}
    for percent in (1, 5, 10, 20):
        k = max(1, math.ceil(len(labels) * percent / 100)) if len(labels) else 0
        hits = int(labels[order[:k]].sum()) if k else 0
        output[f"precision_at_{percent}pct"] = hits / k if k else None
        output[f"recall_at_{percent}pct"] = hits / positives if positives else None
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
        f"- Upper interval target coverage: {reg_metrics['upper_interval_target_coverage']:.0%}; measured: {reg_metrics['upper_interval_coverage']:.3%}",
        "",
        "## Supervised classifier candidate (not runtime)",
        "",
        f"- Test n: {clf_metrics['n']:,}; positive n: {clf_metrics['positive_n']:,}",
        f"- Average Precision: {clf_metrics['average_precision']:.4f}",
        "- Baseline Average Precision:",
    ]
    for name, metrics in classifier["baselines"].items():
        lines.append(f"  - {name}: {metrics['average_precision']:.4f} (n={metrics['n']:,}, positives={metrics['positive_n']:,})")
    lines.extend(["", "## Limitations", ""])
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
    train_claims, train_labels = _read_csv_split(input_dir, "train")
    val_claims, val_labels = _read_csv_split(input_dir, "validation")
    test_claims, test_labels = _read_csv_split(input_dir, "test")
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
    regressor_test = {
        "normal_n": int(test_normal.sum()),
        "mape": float(np.mean(np.abs(test_actual - test_predictions) / np.maximum(test_actual, 1.0))),
        "medae": float(np.median(np.abs(test_actual - test_predictions))),
        "upper_interval_target_coverage": 0.90,
        "upper_interval_coverage": float(np.mean(test_actual <= test_upper)),
        "upper_residual_margin": residual_margin,
    }

    train_classifier_x, classifier_features = build_classifier_features(train_claims)
    test_classifier_x, _ = build_classifier_features(test_claims)
    class_params = {"objective": "binary:logistic", "eval_metric": "aucpr", "max_depth": 5, "eta": 0.05,
                    "subsample": 0.8, "colsample_bytree": 0.9, "tree_method": "hist", "nthread": 4, "seed": seed}
    classifier = xgb.train(
        class_params,
        xgb.DMatrix(train_classifier_x, label=train_y, feature_names=classifier_features),
        num_boost_round=180,
    )
    classifier_scores = classifier.predict(xgb.DMatrix(test_classifier_x, feature_names=classifier_features))
    logistic_scores = _logistic_rule_baseline(train_claims, train_labels, test_claims)
    random_scores = np.random.default_rng(seed).random(len(test_y))
    benchmark_scores = np.asarray([
        abs(claim["cost_claimed"] - claim["regional_base_rate"]) / max(1.0, claim["regional_base_rate"])
        for claim in test_claims
    ])

    output_dir.mkdir(parents=True, exist_ok=True)
    reg_path = output_dir / "xgboost_regressor_synthetic_v2.json"
    classifier_path = output_dir / "xgboost_classifier_candidate_synthetic_v2.json"
    chosen.save_model(reg_path)
    classifier.save_model(classifier_path)
    config_hash = hashlib.sha256(json.dumps({"regression": reg_params, "classifier": class_params, "seed": seed}, sort_keys=True).encode()).hexdigest()
    artifact = {
        "dataset_version": metadata["dataset_version"],
        "synthetic_only": True,
        "seed": seed,
        "config_sha256": config_hash,
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
            "test_metrics": _ranking_metrics(test_y, classifier_scores),
            "baselines": {
                "random": _ranking_metrics(test_y, random_scores),
                "absolute_benchmark_deviation": _ranking_metrics(test_y, benchmark_scores),
                "logistic_regression_rule_flags": _ranking_metrics(test_y, logistic_scores),
            },
            "model_file": classifier_path.name,
        },
        "limitations": [
            "All claims and labels are synthetic; this does not validate BPJS performance.",
            "Test set was not used for feature or hyperparameter selection.",
            "Multi-seed grouped bootstrap confidence intervals are not yet included.",
        ],
    }
    artifact_path = output_dir / "synthetic_v2_training_report.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path = output_dir / "synthetic_v2_training_report.md"
    markdown_path.write_text(render_training_report(artifact), encoding="utf-8")
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_training_report(artifact), encoding="utf-8")
    print(f"Training report: {artifact_path}")
    print(f"Selected regressor: {selected['name']} (validation MedAE={selected['validation_medae']:.2f})")
    print(f"Classifier candidate test AP: {artifact['classifier_candidate_not_runtime']['test_metrics']['average_precision']}")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="directory with v2 split CSVs and schema.json")
    parser.add_argument("--out", type=Path, default=Path("backend/models_trained/synthetic_v2"))
    parser.add_argument("--seed", type=int, default=42)
    root = Path(__file__).resolve().parents[3]
    parser.add_argument("--report", type=Path, default=root / "docs/EVALUATION_REPORT.md")
    args = parser.parse_args()
    train_synthetic_v2(args.dataset, args.out, seed=args.seed, report_path=args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
