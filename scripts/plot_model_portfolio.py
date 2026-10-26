"""Render eight current model-performance figures from evaluation artifacts.

Outputs live in docs/figures. The classifiers are synthetic-only candidates;
the cost regressor is evaluated on the real BPJS FKRTL holdout.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "docs/figures"
COST_PATH = ROOT / "backend/app/data/analysis/retrain_results.json"
REPORT_PATHS = {
    "v2.4": ROOT / "backend/models_trained/synthetic_v2/synthetic_v2_training_report.json",
    "v3": ROOT / "backend/models_trained/synthetic_v2_v3/synthetic_v2_training_report.json",
}

INK, MUTED = "#18252F", "#62717A"
GRID, PAPER = "#DEE5E7", "#F7F8F5"
TEAL, GOLD, GRAY, RED = "#087E83", "#D18A35", "#9AA7AA", "#B85B4B"


def load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"evaluation artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def setup(title: str, ylabel: str = ""):
    fig, ax = plt.subplots(figsize=(9.6, 6.0), dpi=160, facecolor=PAPER)
    ax.set_facecolor(PAPER)
    ax.set_title(title, loc="left", color=INK, fontsize=15, fontweight="bold", pad=18)
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, fontsize=10)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    return fig, ax


def save(fig, filename: str, note: str = "") -> None:
    if note:
        fig.text(0.08, 0.035, note, color=MUTED, fontsize=8, va="bottom")
    fig.tight_layout(rect=(0.06, 0.08 if note else 0.04, 0.98, 0.96))
    path = FIG_DIR / filename
    fig.savefig(path, facecolor=PAPER)
    plt.close(fig)
    print(f"[ok] {path.relative_to(ROOT)}")


def main() -> None:
    cost = load(COST_PATH)
    reports = {version: load(path) for version, path in REPORT_PATHS.items()}
    cls = {v: r["classifier_candidate_not_runtime"] for v, r in reports.items()}
    metrics = {v: c["test_metrics"] for v, c in cls.items()}
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    # Retire the prior one-page composite; the maintained deliverable is an
    # eight-figure set with domain-specific detail.
    (FIG_DIR / "model_performance_portfolio.png").unlink(missing_ok=True)

    # 1. Cost regressor MAPE across legacy-runtime, retrained legacy, v2+context.
    variants = [("A · legacy runtime", "A_runtime_legacy", GRAY),
                ("B · legacy retrained", "B_legacy_real", GOLD),
                ("C · v2 + context", "C_v2_real", TEAL)]
    fig, ax = setup("01  COST BENCHMARK · REAL BPJS HOLDOUT", "MAPE · % (log scale)")
    vals = [cost[k]["test_semua"]["mape_pct"] for _, k, _ in variants]
    bars = ax.bar(range(3), vals, color=[c for _, _, c in variants], width=0.58)
    ax.set_yscale("log"); ax.minorticks_off(); ax.set_ylim(5, max(vals) * 3.0)
    ax.set_xticks(range(3), [x[0] for x in variants])
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x()+bar.get_width()/2, val*1.16, f"{val:,.2f}%", ha="center",
                color=INK, fontsize=10, fontweight="bold")
    save(fig, "cost_benchmark_mape.png", "n=340,518 · subject split · target FKL48 verifikasi · regresi biaya wajar")

    # 2. Cost C quality by stratum / recent-time slice.
    views = [("Dialisis", "test_dialisis"), ("Non-dialisis", "test_non_dialisis"),
             ("Test terbaru", "test_terbaru")]
    fig, ax = setup("02  COST MODEL C · STRATUM & RECENCY", "MAPE · %")
    mape = [cost["C_v2_real"][k]["mape_pct"] for _, k in views]
    bars = ax.bar(range(3), mape, color=[TEAL, GOLD, GRAY], width=0.58)
    ax.set_ylim(0, max(mape)*1.65); ax.set_xticks(range(3), [x[0] for x in views])
    for bar, (_, key) in zip(bars, views):
        q = cost["C_v2_real"][key]
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.14,
                f"{q['mape_pct']:.2f}%\nR² {q['r2']:.3f} · medAPE {q['medape_pct']:.2f}%",
                ha="center", color=INK, fontsize=8.5, fontweight="bold")
    save(fig, "cost_model_strata.png", "C: v2 + context · latest period is ≥2024-11-06")

    # 3. Synthetic classifier AP with group-bootstrap intervals.
    fig, ax = setup("03  CLASSIFIER CANDIDATES · SYNTHETIC TEST", "Average precision · group-bootstrap 95% CI")
    versions = ["v2.4", "v3"]
    aps = [metrics[v]["average_precision"] for v in versions]
    cis = [metrics[v]["average_precision_group_bootstrap_ci95"]["ci95"] for v in versions]
    err = np.array([[a-ci[0] for a,ci in zip(aps,cis)], [ci[1]-a for a,ci in zip(aps,cis)]])
    bars = ax.bar(range(2), aps, color=[GRAY, TEAL], width=0.52, zorder=3)
    ax.errorbar(range(2), aps, yerr=err, fmt="none", ecolor=INK, capsize=5, linewidth=1.4, zorder=4)
    ax.set_ylim(0, 0.84); ax.set_xticks(range(2), ["v2.4 · baseline", "v3 · calibrated"])
    ax.axhline(0.03, color=GOLD, ls=(0,(3,3)), lw=1.2)
    for bar, a, ci in zip(bars, aps, cis):
        ax.text(bar.get_x()+bar.get_width()/2, ci[1]+0.025, f"{a:.3f}\n[{ci[0]:.3f}, {ci[1]:.3f}]",
                ha="center", color=INK, fontsize=9, fontweight="bold")
    save(fig, "classifier_ap_comparison.png", "50,000 synthetic test claims · seed 42 · random AP = 0.03 · not BPJS validation")

    # 4. v3 feature importance.
    top = cls["v3"]["feature_importance_gain_top10"]
    fig, ax = setup("04  CLASSIFIER v3 · FEATURE IMPORTANCE", "XGBoost gain · top 10")
    names = [x["feature"].replace("_", " ") for x in reversed(top)]
    gains = [x["gain"] for x in reversed(top)]
    bars = ax.barh(range(len(top)), gains, color=[TEAL if "copy" in n else GRAY for n in names], height=0.68)
    ax.set_yticks(range(len(top)), names, fontsize=8.5); ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(gains)*1.22)
    for b,v in zip(bars,gains): ax.text(v+2, b.get_y()+b.get_height()/2, f"{v:.1f}", va="center", color=INK, fontsize=8)
    save(fig, "classifier_feature_importance.png", "Candidate only · 28-feature contract · exact-copy identity signal leads")

    # 5. AP by anomaly type, candidate comparison.
    types = sorted(set(metrics["v2.4"]["by_anomaly_type"]) & set(metrics["v3"]["by_anomaly_type"]))
    fig, ax = setup("05  CLASSIFIER · AVERAGE PRECISION BY ANOMALY TYPE", "Average precision · synthetic test")
    x = np.arange(len(types)); w = 0.37
    a = [metrics["v2.4"]["by_anomaly_type"][t]["average_precision"] for t in types]
    b = [metrics["v3"]["by_anomaly_type"][t]["average_precision"] for t in types]
    ax.bar(x-w/2, a, w, color=GRAY, label="v2.4")
    ax.bar(x+w/2, b, w, color=TEAL, label="v3 calibrated")
    ax.set_xticks(x, [t.replace("_", "\n") for t in types], fontsize=8)
    ax.set_ylim(0, max(max(a),max(b))*1.3); ax.legend(frameon=False, ncol=2, fontsize=8)
    save(fig, "classifier_anomaly_slices.png", "Same 7 scenario families; synthetic labels only")

    # 6. Precision/recall under fixed queue-size budgets.
    fig, ax = setup("06  CLASSIFIER · FIXED ALERT BUDGETS", "Precision / recall · %")
    budgets = [1,5,10,20]; x=np.arange(len(budgets)); w=0.19
    for j,(version,color) in enumerate((("v2.4",GRAY),("v3",TEAL))):
        prec=[metrics[version][f"precision_at_{k}pct"]*100 for k in budgets]
        rec=[metrics[version][f"recall_at_{k}pct"]*100 for k in budgets]
        ax.bar(x+(j*2-1.5)*w, prec, w, color=color, alpha=0.78 if j==0 else 1.0,
               label=f"{version} precision")
        ax.plot(x+(j*2-1.5)*w, rec, marker="o", color=INK if j==0 else TEAL,
                ls="--", lw=1.4, label=f"{version} recall")
    ax.set_xticks(x, [f"{k}%" for k in budgets]); ax.set_ylim(0,100)
    ax.set_xlabel("Alert budget"); ax.legend(frameon=False, ncol=2, fontsize=7.5)
    save(fig, "classifier_alert_budgets.png", "Threshold-independent top-k operating characteristics · 3% synthetic prevalence")

    # 7. v3 test confusion matrix at validation-selected threshold.
    op = metrics["v3"]["operating_point"]
    matrix=np.array([[op["true_negative"],op["false_positive"]],[op["false_negative"],op["true_positive"]]])
    fig, ax=plt.subplots(figsize=(7.2,6.0),dpi=160,facecolor=PAPER); ax.set_facecolor(PAPER)
    ax.set_title("07  CLASSIFIER v3 · TEST CONFUSION MATRIX",loc="left",color=INK,fontsize=14,fontweight="bold",pad=18)
    ax.imshow(matrix,cmap=plt.matplotlib.colors.LinearSegmentedColormap.from_list("ari",[PAPER,"#8CC6C3",TEAL]))
    ax.set_xticks([0,1],["Predicted normal","Predicted anomaly"]); ax.set_yticks([0,1],["Actual normal","Actual anomaly"])
    for (i,j),v in np.ndenumerate(matrix): ax.text(j,i,f"{v:,}",ha="center",va="center",color=INK,fontsize=14,fontweight="bold")
    ax.tick_params(length=0, labelsize=8, colors=MUTED)
    for s in ax.spines.values(): s.set_visible(False)
    save(fig,"classifier_confusion_v3.png",f"Validation-selected threshold {op['threshold']:.4f} · test n=50,000 · no runtime promotion")

    # 8. Calibration/reliability curve for v3.
    bins=metrics["v3"]["calibration_bins"]
    bins=[q for q in bins if q["count"]>0]
    fig,ax=setup("08  CLASSIFIER v3 · PROBABILITY CALIBRATION","Observed anomaly rate")
    xx=[q["mean_score"] for q in bins]; yy=[q["observed_rate"] for q in bins]
    ax.plot([0,1],[0,1],color=GRAY,ls="--",lw=1.2,label="Perfect calibration")
    ax.plot(xx,yy,color=TEAL,marker="o",lw=2,markersize=4,label="v3 · test bins")
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.set_xlabel("Mean predicted score"); ax.legend(frameon=False,fontsize=8)
    ax.text(0.04,0.92,f"Brier {metrics['v3']['brier_score']:.4f}  ·  ECE {metrics['v3']['expected_calibration_error']:.4f}",
            transform=ax.transAxes,color=INK,fontsize=9,fontweight="bold")
    save(fig,"classifier_calibration_v3.png","Synthetic test set · reliability bins weighted by claim count")


if __name__ == "__main__":
    main()
