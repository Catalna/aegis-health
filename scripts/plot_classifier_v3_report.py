"""Delapan figur evaluasi kandidat klasifier v3 (terkalibrasi) — satu model, tanpa pembanding.

Menghitung ulang skor dari model final + dataset yang sama persis dengan training
(`data/synthetic_v2_calibrated`, config SHA tercatat di report) memakai pipeline
fitur identik trainer (`build_training_context` dari train, per-split context).
Ambang keputusan = operating point report (dipilih di validation, diterapkan
seragam ke train/val/test). Semua angka demonstrator sintetis — BUKAN validasi BPJS.

Output `docs/figures/` (per-model prefix clf_v3_):
  1) clf_v3_feature_importance.png     — gain share 14 teratas
  2) clf_v3_label_distribution.png     — distribusi label outcome (semua split)
  3) clf_v3_confusion_train.png        — confusion matrix (ambang report)
  4) clf_v3_confusion_validation.png
  5) clf_v3_confusion_test.png
  6) clf_v3_pr_curve_test.png          — precision-recall (AP di legend)
  7) clf_v3_roc_curve_test.png         — ROC (AUC di legend)
  8) clf_v3_validation_logloss.png     — log loss validation per boosting round

Pemakaian: venv\\Scripts\\python.exe scripts\\plot_classifier_v3_report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (average_precision_score, log_loss, precision_recall_curve,
                             roc_auc_score, roc_curve)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.app.ml.train_synthetic_v2 import _read_split
from backend.app.ml.v2_features import build_classifier_features, build_training_context

DATASET_DIR = REPO / "data" / "synthetic_v2_calibrated"
MODELS_DIR = REPO / "backend" / "models_trained" / "synthetic_v2_v3"
OUT_DIR = REPO / "docs" / "figures"

INK, MUTED, GRID, PAPER = "#18252F", "#62717A", "#DEE5E7", "#F7F8F5"
TEAL, GOLD, RED, GREEN = "#087E83", "#D18A35", "#B85B4B", "#3E8E5A"
FIG_KW = dict(figsize=(9.6, 6.8), dpi=160)
MODEL_TAG = "Model 2 · Klasifier anomali (kandidat v3) — "


def _img(figure: plt.Figure, name: str, note: str = "") -> None:
    if note:
        figure.text(0.08, 0.02, note, color=MUTED, fontsize=8, va="bottom")
    figure.tight_layout(rect=(0.04, 0.055 if note else 0.03, 0.98, 0.97))
    figure.savefig(OUT_DIR / name, facecolor=PAPER)
    plt.close(figure)
    print(f"[ok] {name}")


def _ax(title: str, ylabel: str = "") -> tuple[plt.Figure, plt.axes.Axes]:
    fig, ax = plt.subplots(**FIG_KW)
    ax.set_facecolor(PAPER)
    fig.suptitle(f"{MODEL_TAG}{title}", x=0.02, ha="left", color=INK,
                 fontsize=13.5, fontweight="bold")
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, fontsize=10)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    return fig, ax


def _confmat(y_true: np.ndarray, score: np.ndarray, threshold: float) -> np.ndarray:
    pred = (score >= threshold).astype(int)
    tn = int(np.sum((pred == 0) & (y_true == 0)))
    fp = int(np.sum((pred == 1) & (y_true == 0)))
    fn = int(np.sum((pred == 0) & (y_true == 1)))
    tp = int(np.sum((pred == 1) & (y_true == 1)))
    return np.array([[tn, fp], [fn, tp]])


def _plot_confusion(matrix: np.ndarray, title: str, name: str, threshold: float) -> None:
    fig, ax = plt.subplots(**FIG_KW)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    from matplotlib.colors import LogNorm
    im = ax.imshow(matrix, cmap=mpl_blues(), norm=LogNorm(vmin=1, vmax=matrix.max()))
    ax.set_xticks([0, 1], ["Predicted normal", "Predicted anomaly"], fontsize=9, color=MUTED)
    ax.set_yticks([0, 1], ["Actual normal", "Actual anomaly"], fontsize=9, color=MUTED)
    fig.suptitle(f"{MODEL_TAG}{title}", x=0.02, ha="left", color=INK,
                 fontsize=13.5, fontweight="bold")
    log_mid = 0.5 * (np.log10(matrix.max()) + np.log10(max(matrix.min(), 1)))
    for i in range(2):
        for j in range(2):
            v = int(matrix[i, j])
            dark = np.log10(max(v, 1)) > log_mid
            ax.text(j, i, f"{v:,}", ha="center", va="center",
                    color="white" if dark else INK, fontsize=14, fontweight="bold")
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    _img(fig, name, f"threshold {threshold:.4f} · validation-selected, applied uniformly · synthetic test only")


def mpl_blues():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("ari_blues", [PAPER, "#7FB9C0", TEAL])


def main() -> None:
    report = json.loads((MODELS_DIR / "synthetic_v2_training_report.json").read_text(encoding="utf-8"))
    cc = report["classifier_candidate_not_runtime"]
    best_iteration = int(cc["selection"]["selected"]["best_iteration"])
    threshold = float(cc["test_metrics"]["operating_point"]["threshold"])
    ap_report = float(cc["test_metrics"]["average_precision"])
    auc_report = float(cc["test_metrics"]["roc_auc"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"model: best_iteration={best_iteration}, threshold={threshold:.6f} (report AP {ap_report:.4f})")

    classifier = xgb.Booster()
    classifier.load_model(MODELS_DIR / "xgboost_classifier_candidate_synthetic_v2.json")

    train_claims, train_labels = _read_split(DATASET_DIR, "train")
    train_y = np.asarray([int(row["is_anomaly"]) for row in train_labels], dtype=np.int32)
    context = build_training_context(train_claims, train_y)

    splits: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    matrix_val = feats_val = None
    for name in ("train", "validation", "test"):
        claims, labels = (train_claims, train_labels) if name == "train" else _read_split(DATASET_DIR, name)
        y = np.asarray([int(row["is_anomaly"]) for row in labels], dtype=np.int32)
        matrix, feats = build_classifier_features(claims, context=context)
        scores = classifier.predict(xgb.DMatrix(matrix, feature_names=feats),
                                    iteration_range=(0, best_iteration))
        splits[name] = (y, scores)
        print(f"{name}: n={len(y):,} pos={int(y.sum()):,}")
        if name == "validation":
            matrix_val, feats_val = matrix, feats
        del matrix
        if name != "train":
            del claims, labels

    # 1) Feature importance — gain share, 14 teratas
    gain = sorted(classifier.get_score(importance_type="gain").items(), key=lambda kv: kv[1], reverse=True)[:14]
    labels_x = [k for k, _ in gain]
    share = np.asarray([v for _, v in gain], dtype=float)
    share = share / share.sum()
    fig, ax = _ax("Feature Importance (gain share)",
                  "share of total gain · synthetic training")
    bars = ax.barh(labels_x, share, color=[TEAL if "copy" in k else GOLD for k in labels_x], height=0.68)
    ax.invert_yaxis()
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    for bar, val in zip(bars, share):
        ax.text(bar.get_width() + 0.004, bar.get_y() + bar.get_height() / 2, f"{val:.1%}",
                va="center", color=INK, fontsize=8.5, fontweight="bold")
    ax.set_xlim(0, share.max() * 1.15)
    _img(fig, "clf_v3_feature_importance.png",
         "28-feature contract · exact-copy identity signal leads · candidate, not runtime")

    # 2) Distribusi label outcome — semua split
    counts: dict[str, int] = {}
    for table in ("train", "validation", "test"):
        frame = pd.read_parquet(DATASET_DIR / f"{table}_labels.parquet")
        for label, n in frame["anomaly_type"].value_counts().items():
            counts[str(label)] = counts.get(str(label), 0) + int(n)
    order = ["none"] + sorted(k for k in counts if k != "none")
    values = [counts[k] for k in order]
    names = ["Normal" if k == "none" else k for k in order]
    fig, ax = _ax("Label Outcome Distribution (dataset terkalibrasi)",
                  f"rows · total {sum(values):,}")
    colors = [GREEN] + [RED] * (len(order) - 1)
    bars = ax.bar(np.arange(len(order)), values, color=colors)
    ax.set_xticks(np.arange(len(order)), names,
                  rotation=90 if max(len(n) for n in names) > 9 else 0, fontsize=8.5)
    ax.bar_label(bars, fmt="%d", fontsize=7.5, color=INK)
    _img(fig, "clf_v3_label_distribution.png",
         "train + validation + test combined · calibrated generator (v2.4.0-calibrated, seed 42)")

    # 3-5) Confusion matrices, satu ambang seragam
    for split, title in (("train", "Confusion Matrix — Training"),
                         ("validation", "Confusion Matrix — Validation"),
                         ("test", "Confusion Matrix — Testing")):
        y, scores = splits[split]
        _plot_confusion(_confmat(y, scores, threshold), title, f"clf_v3_confusion_{split}.png", threshold)

    # 6) Precision-recall curve (test)
    y_test, s_test = splits["test"]
    prec, rec, _ = precision_recall_curve(y_test, s_test)
    ap = average_precision_score(y_test, s_test)
    fig, ax = _ax("Precision-Recall Curve (test)",
                  "precision")
    ax.plot(rec, prec, color=TEAL, lw=2.2, label=f"AP = {ap:.4f} (report {ap_report:.4f})")
    ax.axhline(0.03, color=GOLD, ls=(0, (3, 3)), lw=1.2)
    ax.text(0.02, 0.031, "random baseline · 3% prevalence", color=MUTED, fontsize=7.5)
    ax.set_xlabel("Recall", color=MUTED, fontsize=10)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.01)
    ax.legend(frameon=False, fontsize=9)
    _img(fig, "clf_v3_pr_curve_test.png",
         "50,000 synthetic test claims · seed 42 · not BPJS validation")

    # 7) ROC curve (test)
    fpr, tpr, _ = roc_curve(y_test, s_test)
    auc = roc_auc_score(y_test, s_test)
    fig, ax = _ax("ROC Curve (test)", "true positive rate")
    ax.plot(fpr, tpr, color=TEAL, lw=2.2, label=f"ROC-AUC = {auc:.4f} (report {auc_report:.4f})")
    ax.plot([0, 1], [0, 1], "--", color="#9AA7AA", lw=1.1)
    ax.set_xlabel("False positive rate", color=MUTED, fontsize=10)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.01)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    _img(fig, "clf_v3_roc_curve_test.png",
         "same scores as PR figure · threshold-independent view")

    # 8) Validation log loss per boosting round
    y_val, _ = splits["validation"]
    d_val = xgb.DMatrix(matrix_val, feature_names=feats_val)
    rounds = list(range(1, best_iteration + 1, 3))
    if rounds[-1] != best_iteration:
        rounds.append(best_iteration)
    losses = [float(log_loss(y_val, classifier.predict(d_val, iteration_range=(0, k)), labels=[0, 1]))
              for k in rounds]
    fig, ax = _ax("Validation Log Loss per Boosting Round",
                  "log loss")
    ax.plot(rounds, losses, color=TEAL, lw=2)
    ax.scatter([best_iteration], [losses[-1]], color=RED, zorder=4, s=36)
    ax.annotate(f"selected {best_iteration}\n{losses[-1]:.4f}",
                (best_iteration, losses[-1]), textcoords="offset points", xytext=(-8, 10),
                ha="right", fontsize=8.5, color=INK, fontweight="bold")
    ax.set_xlabel("boosting round", color=MUTED, fontsize=10)
    _img(fig, "clf_v3_validation_logloss.png",
         "early stopping recomputed model-final per k trees · depth 5, spw 1.0")

    print("selesai: 8 PNG clf_v3_* di docs/figures")


if __name__ == "__main__":
    main()
