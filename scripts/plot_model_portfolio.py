"""Render the current ML model portfolio from the committed/ignored eval artifacts.

Output: docs/figures/model_performance_portfolio.png
The visualization is an offline candidate comparison; no runtime model is promoted.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
COST_JSON = ROOT / "backend/app/data/analysis/retrain_results.json"
CLASSIFIER_JSONS = {
    "v2.4 · baseline": ROOT / "backend/models_trained/synthetic_v2/synthetic_v2_training_report.json",
    "v3 · calibrated": ROOT / "backend/models_trained/synthetic_v2_v3/synthetic_v2_training_report.json",
}
OUT = ROOT / "docs/figures/model_performance_portfolio.png"

INK = "#18252F"
MUTED = "#62717A"
GRID = "#DEE5E7"
PAPER = "#F7F8F5"
TEAL = "#087E83"
GOLD = "#D18A35"
GRAY = "#9AA7AA"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"required evaluation artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def style_axis(ax, title: str) -> None:
    ax.set_facecolor(PAPER)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=14)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def main() -> None:
    cost = load_json(COST_JSON)
    models = [
        ("A · legacy runtime", "A_runtime_legacy", GRAY),
        ("B · retrained real", "B_legacy_real", GOLD),
        ("C · v2 + context", "C_v2_real", TEAL),
    ]
    c_reports = {name: load_json(path) for name, path in CLASSIFIER_JSONS.items()}
    classifier = {
        label: report["classifier_candidate_not_runtime"]["test_metrics"]
        for label, report in c_reports.items()
    }

    fig = plt.figure(figsize=(14, 9.2), dpi=180, facecolor=PAPER)
    grid = fig.add_gridspec(2, 2, left=0.075, right=0.965, top=0.755, bottom=0.16,
                            hspace=0.47, wspace=0.30)
    ax1 = fig.add_subplot(grid[0, 0])
    ax2 = fig.add_subplot(grid[0, 1])
    ax3 = fig.add_subplot(grid[1, 0])
    ax4 = fig.add_subplot(grid[1, 1])

    # 1) Real-data cost regression error (log scale because runtime legacy is far worse).
    style_axis(ax1, "01  COST BENCHMARK · REAL BPJS TEST · n=340,518")
    vals = [cost[key]["test_semua"]["mape_pct"] for _, key, _ in models]
    bars = ax1.bar(range(3), vals, color=[color for _, _, color in models], width=0.58)
    ax1.set_yscale("log")
    ax1.minorticks_off()
    ax1.set_ylim(5, max(vals) * 3.2)
    ax1.set_ylabel("MAPE · % (log scale)", color=MUTED, fontsize=9)
    ax1.set_xticks(range(3), [label for label, _, _ in models], fontsize=8)
    ax1.grid(axis="y", which="major", color=GRID, linewidth=0.8)
    for bar, val in zip(bars, vals):
        ax1.text(bar.get_x() + bar.get_width() / 2, val * 1.2, f"{val:,.2f}%",
                 ha="center", va="bottom", fontsize=9, color=INK, fontweight="bold")

    # 2) Error band and R² for cost variants.
    style_axis(ax2, "02  COST BENCHMARK · PREDICTION QUALITY")
    within = [cost[key]["test_semua"]["within10_pct"] for _, key, _ in models]
    bars = ax2.bar(range(3), within, color=[color for _, _, color in models], width=0.58)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("Claims within ±10% · %", color=MUTED, fontsize=9)
    ax2.set_xticks(range(3), [label for label, _, _ in models], fontsize=8)
    for i, (bar, (_, key, _)) in enumerate(zip(bars, models)):
        r2 = cost[key]["test_semua"]["r2"]
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                 f"{bar.get_height():.1f}%\nR² {r2:.3f}", ha="center", va="bottom",
                 fontsize=8.5, color=INK, fontweight="bold")

    # 3) Classifier AP with group-bootstrap confidence intervals.
    style_axis(ax3, "03  ANOMALY CLASSIFIER · SYNTHETIC TEST")
    labels = list(classifier)
    aps = [classifier[label]["average_precision"] for label in labels]
    cis = [classifier[label]["average_precision_group_bootstrap_ci95"]["ci95"] for label in labels]
    err = np.asarray([[ap - ci[0] for ap, ci in zip(aps, cis)],
                      [ci[1] - ap for ap, ci in zip(aps, cis)]])
    colors = [GRAY, TEAL]
    bars = ax3.bar(range(2), aps, color=colors, width=0.52, zorder=3)
    ax3.errorbar(range(2), aps, yerr=err, fmt="none", ecolor=INK, elinewidth=1.4,
                 capsize=5, capthick=1.4, zorder=4)
    ax3.set_ylim(0, 0.84)
    ax3.set_ylabel("Average precision · group-bootstrap 95% CI", color=MUTED, fontsize=9)
    ax3.set_xticks(range(2), labels, fontsize=9)
    for bar, ap, ci in zip(bars, aps, cis):
        ax3.text(bar.get_x() + bar.get_width() / 2, ci[1] + 0.025,
                 f"{ap:.3f}\n[{ci[0]:.3f}, {ci[1]:.3f}]", ha="center", va="bottom",
                 fontsize=8.5, color=INK, fontweight="bold")
    ax3.axhline(0.03, color=GOLD, linewidth=1.2, linestyle=(0, (3, 3)))
    ax3.text(0.02, 0.065, "random baseline · 3% prevalence", color=MUTED,
             fontsize=7.5, transform=ax3.get_yaxis_transform())

    # 4) Same fixed alert budget, compare precision and recall.
    style_axis(ax4, "04  CLASSIFIER · FIXED 5% ALERT BUDGET")
    x = np.arange(2)
    width = 0.34
    precision = [classifier[label]["precision_at_5pct"] * 100 for label in labels]
    recall = [classifier[label]["recall_at_5pct"] * 100 for label in labels]
    b1 = ax4.bar(x - width / 2, precision, width, label="Precision", color=GOLD)
    b2 = ax4.bar(x + width / 2, recall, width, label="Recall", color=TEAL)
    ax4.set_ylim(0, 100)
    ax4.set_ylabel("% of claims / anomalies", color=MUTED, fontsize=9)
    ax4.set_xticks(x, labels, fontsize=9)
    ax4.legend(frameon=False, ncol=2, loc="upper left", fontsize=8)
    for bars in (b1, b2):
        for bar in bars:
            ax4.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                     f"{bar.get_height():.1f}%", ha="center", va="bottom", fontsize=8,
                     color=INK, fontweight="bold")

    fig.text(0.075, 0.93, "J-ARI  /  MODEL PERFORMANCE PORTFOLIO", fontsize=9,
             color=TEAL, fontweight="bold", family="DejaVu Sans")
    fig.text(0.075, 0.875, "Current candidates, measured on their declared test domains",
             fontsize=21, color=INK, fontweight="bold")
    fig.text(0.075, 0.842,
             "COST: real BPJS FKRTL holdout     /     CLASSIFIER: synthetic only · candidates are not runtime models",
             fontsize=9, color=MUTED)
    fig.text(0.075, 0.075,
             "Cost test: 340,518 claims · subject split · FKL48 target.  Classifier: 50,000 synthetic claims · seed 42 · 3% prevalence.\n"
             "v2.4 → v3 reflects a harder, calibrated synthetic domain; AP values are not BPJS performance.  No model promotion implied.",
             fontsize=8, color=MUTED, va="bottom", linespacing=1.5)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=180, facecolor=PAPER)
    plt.close(fig)
    print(f"[ok] saved {OUT}")
    print(f"[size] {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
