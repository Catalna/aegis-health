"""Visualisasi ulang hasil model ML v2 (kandidat klasifikasi) dengan gaya "throwback".

Delapan PNG polos (matplotlib default, 960x720) mengikuti pola dokumen lama:
  1) feature_importance.png       — Feature Importance (bar horizontal, gain share)
  2) label_distribution.png       — Label Outcome Distribution (bar per kelas label)
  3) confusion_train.png          — Training Confusion Matrix (2x2)
  4) confusion_validation.png     — Validation Confusion Matrix (2x2)
  5) confusion_test.png           — Testing Confusion Matrix (2x2)
  6) pr_curve_test.png            — Testing Precision-Recall Curve (AP di legend)
  7) roc_curve_test.png           — Testing ROC Curve (ROC-AUC di legend)
  8) validation_logloss.png       — Validation Log Loss per Boosting Round

Semua angka dihitung dari model final seed-42 + dataset split yang sama persis
dengan training (context relasional dibangun per-split, identik trainer).
Ambang keputusan = operating point yang tercatat di report (dipilih di
validation dengan max-F1, lalu diterapkan seragam ke train/val/test).

Pemakaian:
    .\\venv\\Scripts\\python.exe scripts\\visualize_evaluation.py
    (opsional) --dataset-dir ... --models-dir ... --out-dir ...

Catatan: hasil ini berlaku untuk demonstrator sintetis, bukan validasi BPJS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, log_loss, precision_recall_curve, roc_auc_score, roc_curve

REPO = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO))

from backend.app.ml.train_synthetic_v2 import _read_split
from backend.app.ml.v2_features import build_classifier_features, build_training_context

FIG_KW = dict(figsize=(9.6, 7.2), dpi=100)  # 960x720 px, seperti referensi


def _img(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, format="png")
    plt.close()


def _confusion(y_true: np.ndarray, y_score: np.ndarray, threshold: float) -> np.ndarray:
    pred = (y_score >= threshold).astype(int)
    tn = int(np.sum((pred == 0) & (y_true == 0)))
    fp = int(np.sum((pred == 1) & (y_true == 0)))
    fn = int(np.sum((pred == 0) & (y_true == 1)))
    tp = int(np.sum((pred == 1) & (y_true == 1)))
    return np.array([[tn, fp], [fn, tp]])


def _plot_confusion(matrix: np.ndarray, title: str, out: Path) -> None:
    labels = ["Normal", "Anomaly"]
    fig, ax = plt.subplots(**FIG_KW)
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks([0, 1], labels)
    ax.set_yticks([0, 1], labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    for i in range(2):
        for j in range(2):
            v = int(matrix[i, j])
            ax.text(j, i, str(v), ha="center", va="center", color="black", fontsize=12)
    _img(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerasi figur evaluasi gaya throwback")
    parser.add_argument("--dataset-dir", default=r"C:\Users\Radith\AppData\Local\Temp\opencode\synthetic_v2_standard_final24")
    parser.add_argument("--models-dir", default=str(REPO / "backend" / "models_trained" / "synthetic_v2"))
    parser.add_argument("--out-dir", default=str(REPO / "docs" / "figures"))
    parser.add_argument("--feature-top", type=int, default=14)
    parser.add_argument("--logloss-step", type=int, default=3)
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    models_dir = Path(args.models_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = models_dir / "synthetic_v2_training_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cc = report["classifier_candidate_not_runtime"]
    best_iteration = int(cc["selection"]["selected"]["best_iteration"])
    threshold = float(cc["test_metrics"]["operating_point"]["threshold"])
    print(f"model: best_iteration={best_iteration}, operating threshold={threshold:.6f}")

    classifier = xgb.Booster()
    classifier.load_model(models_dir / "xgboost_classifier_candidate_synthetic_v2.json")

    # --- Muat split + fitur (context relasional dari train, identik trainer) ---
    train_claims, train_labels = _read_split(dataset_dir, "train")
    train_y = np.asarray([int(row["is_anomaly"]) for row in train_labels], dtype=np.int32)
    context = build_training_context(train_claims, train_y)

    splits: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    matrix_val = None
    for name in ("train", "validation", "test"):
        if name == "train":
            claims, labels = train_claims, train_labels
        else:
            claims, labels = _read_split(dataset_dir, name)
        y = np.asarray([int(row["is_anomaly"]) for row in labels], dtype=np.int32)
        matrix, feats = build_classifier_features(claims, context=context)
        scores = classifier.predict(xgb.DMatrix(matrix, feature_names=feats), iteration_range=(0, best_iteration))
        splits[name] = (y, scores)
        if name == "validation":
            matrix_val = matrix  # dipakai lagi untuk kurva logloss per round
            feats_val = feats
        print(f"{name}: n={len(y)}, pos={int(y.sum())}")
        if name != "validation":
            del matrix, claims, labels
        else:
            del claims, labels

    # 1) Feature Importance (gain, dinormalisasi jadi share)
    gain = classifier.get_score(importance_type="gain")
    items = sorted(gain.items(), key=lambda kv: kv[1], reverse=True)[: args.feature_top]
    share = np.asarray([v for _, v in items], dtype=float)
    share = share / share.sum()
    fig, ax = plt.subplots(**FIG_KW)
    ax.barh([k for k, _ in items][::-1], share[::-1])
    ax.set_title("Feature Importance")
    ax.set_xlabel("Importance")
    _img(out_dir / "feature_importance.png")

    # 2) Label Outcome Distribution (semua split digabung, dataset sintetis v2)
    counts: dict[str, int] = {}
    for table in ("train", "validation", "test"):
        frame = pd.read_parquet(dataset_dir / f"{table}_labels.parquet")
        for label, n in frame["anomaly_type"].value_counts().items():
            counts[str(label)] = counts.get(str(label), 0) + int(n)
    order = ["none"] + sorted(k for k in counts if k != "none")
    values = [counts[k] for k in order]
    names = ["Normal" if k == "none" else k for k in order]
    colors = ["seagreen"] + ["#d62728"] * (len(order) - 2) + ["goldenrod"] if len(order) >= 2 else ["seagreen"]
    fig, ax = plt.subplots(**FIG_KW)
    bars = ax.bar(np.arange(len(order)), values, color=colors[: len(order)])
    ax.set_xticks(np.arange(len(order)), names, rotation=90 if max(len(n) for n in names) > 8 else 0)
    ax.set_title("Label Outcome Distribution")
    ax.set_ylabel("Rows")
    ax.set_xlabel("outcome")
    ax.bar_label(bars, fmt="%d", fontsize=9)
    _img(out_dir / "label_distribution.png")

    # 3-5) Confusion matrices train/validation/test pada ambang terpilih
    for split, title in (("train", "Training Confusion Matrix"),
                         ("validation", "Validation Confusion Matrix"),
                         ("test", "Testing Confusion Matrix")):
        y, scores = splits[split]
        matrix = _confusion(y, scores, threshold)
        _plot_confusion(matrix, title, out_dir / f"confusion_{split}.png")
        print(f"confusion {split}: {matrix.ravel().tolist()}")

    # 6) Testing Precision-Recall Curve
    y_test, s_test = splits["test"]
    prec, rec, _ = precision_recall_curve(y_test, s_test)
    ap = average_precision_score(y_test, s_test)
    fig, ax = plt.subplots(**FIG_KW)
    ax.plot(rec, prec, label=f"AP={ap:.4f}")
    ax.set_title("Testing Precision-Recall Curve")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.legend()
    _img(out_dir / "pr_curve_test.png")

    # 7) Testing ROC Curve
    fpr, tpr, _ = roc_curve(y_test, s_test)
    auc = roc_auc_score(y_test, s_test)
    fig, ax = plt.subplots(**FIG_KW)
    ax.plot(fpr, tpr, label=f"ROC-AUC={auc:.4f}")
    ax.plot([0, 1], [0, 1], "--", color="gray")
    ax.set_title("Testing ROC Curve")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.legend()
    _img(out_dir / "roc_curve_test.png")

    # 8) Validation Log Loss per Boosting Round (re-evaluasi model final per k pohon)
    y_val, _ = splits["validation"]
    d_val = xgb.DMatrix(matrix_val, feature_names=feats_val)
    rounds: list[int] = list(range(1, best_iteration + 1, args.logloss_step))
    if rounds[-1] != best_iteration:
        rounds.append(best_iteration)
    losses: list[float] = []
    for k in rounds:
        p = classifier.predict(d_val, iteration_range=(0, k))
        losses.append(float(log_loss(y_val, p, labels=[0, 1])))
    fig, ax = plt.subplots(**FIG_KW)
    ax.plot(rounds, losses)
    ax.set_title("Validation Log Loss")
    ax.set_xlabel("Boosting Round")
    ax.set_ylabel("Validation Log Loss")
    _img(out_dir / "validation_logloss.png")
    print(f"validation logloss: {losses[0]:.4f} @1 -> {losses[-1]:.4f} @{best_iteration}")

    print(f"selesai: 8 PNG di {out_dir}")


if __name__ == "__main__":
    main()
