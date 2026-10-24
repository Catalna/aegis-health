"""Multi-seed aggregation for synthetic v2 training reports.

Reads the JSON trainer reports (one per seed), aggregates headline classifier /
regressor metrics and per-type natural-test metrics into mean ± sample stdev
and min–max across independently regenerated datasets, and renders a Markdown
summary plus a JSON evidence file.

Aggregation only: no training happens here, nothing is selected or tuned on the
test set, and every number is taken verbatim from recorded trainer artifacts.
All results remain synthetic demonstrator figures — never BPJS validation.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

_METRIC_KEYS_CLASSIFIER = (
    "average_precision",
    "roc_auc",
    "brier_score",
    "expected_calibration_error",
)

_CLASSIFIER_SLICE_KEY = "classifier_candidate_not_runtime"


def _mean_std_range(values: list[float]) -> dict[str, Any]:
    return {
        "mean": statistics.fmean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "values_by_seed": values,  # ordered same as the reports
    }


def _operating_f1(entry: dict[str, Any]) -> float | None:
    operating = entry.get("operating_point") or {}
    if "f1" in operating:
        return float(operating["f1"])
    if "f1_at_10pct" in entry:
        return float(entry["f1_at_10pct"])
    return None


def _stress_ap(stress: dict[str, Any]) -> float | None:
    metrics = stress.get("metrics") or {}
    value = metrics.get("average_precision")
    return float(value) if value is not None else None


def aggregate_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate one trainer report per seed into mean ± stdev + min–max tables."""
    if not reports:
        raise ValueError("aggregate_reports requires at least one training report")
    reports = sorted(reports, key=lambda r: int(r.get("seed", 0)))
    seeds = [int(r.get("seed", 0)) for r in reports]

    def headline_operations(extractor) -> dict[str, Any]:
        collected: dict[str, list[float | None]] = {}
        for report in reports:
            row = extractor(report)
            for key, value in row.items():
                collected.setdefault(key, []).append(value)
        aggregated: dict[str, dict[str, Any]] = {}
        for key, values in collected.items():
            present = [float(v) for v in values if v is not None]
            if present:
                aggregated[key] = _mean_std_range(present)
        return aggregated

    def classifier_row(report: dict[str, Any]) -> dict[str, float | None]:
        tm = report[_CLASSIFIER_SLICE_KEY]["test_metrics"]
        operating = tm.get("operating_point") or {}
        return {
            "average_precision": tm.get("average_precision"),
            "roc_auc": tm.get("roc_auc"),
            "brier_score": tm.get("brier_score"),
            "expected_calibration_error": tm.get("expected_calibration_error"),
            "operating_f1": operating.get("f1"),
            "precision_at_operating": operating.get("precision"),
            "recall_at_operating": operating.get("recall"),
            "accuracy_at_operating": operating.get("accuracy"),
            **{f"f1_at_{p}_pct": tm.get(f"f1_at_{p}pct") for p in (1, 5, 10, 20)},
        }

    def regressor_row(report: dict[str, Any]) -> dict[str, float | None]:
        tm = report["regressor"]["test_metrics"]
        # Trainer menyimpan mape/mdape/coverage sebagai fraksi (0.1283 = 12.83%).
        def _pct(key: str) -> float | None:
            value = tm.get(key)
            return float(value) * 100.0 if value is not None else None

        return {
            "regressor_mape_pct": _pct("mape"),
            "regressor_mdae_pct": _pct("mdape"),
            "regressor_medae": tm.get("medae"),
            "regressor_mae": tm.get("mae"),
            "regressor_rmse": tm.get("rmse"),
            "regressor_r2": tm.get("r2"),
            "regressor_upper_interval_coverage_pct": _pct("upper_interval_coverage"),
        }

    def stressed_row(report: dict[str, Any]) -> dict[str, float | None]:
        stress = report.get("stress_test_metrics") or {}
        return {
            "enriched_average_precision": _stress_ap(stress.get("test_enriched") or {}),
            "ood_average_precision": _stress_ap(stress.get("ood") or {}),
        }

    def baseline_row(report: dict[str, Any]) -> dict[str, float | None]:
        baselines = report[_CLASSIFIER_SLICE_KEY].get("baselines") or {}
        row: dict[str, float | None] = {}
        for name, payload in baselines.items():
            ap = (payload or {}).get("average_precision")
            row[f"baseline_{name}_ap"] = float(ap) if ap is not None else None
        return row

    # Per anomaly type on the natural test split.
    per_type: dict[str, dict[str, dict[str, Any]]] = {}
    type_names: set[str] = set()
    for report in reports:
        by_type = report[_CLASSIFIER_SLICE_KEY]["test_metrics"].get("by_anomaly_type") or {}
        type_names.update(by_type.keys())
    for type_name in sorted(type_names):
        ap_values: list[float] = []
        f1_values: list[float] = []
        for report in reports:
            entry = (report[_CLASSIFIER_SLICE_KEY]["test_metrics"].get("by_anomaly_type") or {}).get(type_name)
            if not entry:
                continue
            if entry.get("average_precision") is not None:
                ap_values.append(float(entry["average_precision"]))
            f1 = _operating_f1(entry)
            if f1 is not None:
                f1_values.append(f1)
        per_type[type_name] = {}
        if ap_values:
            per_type[type_name]["average_precision"] = _mean_std_range(ap_values)
        if f1_values:
            per_type[type_name]["operating_f1"] = _mean_std_range(f1_values)

    selections = [
        {
            "seed": seeds[i],
            "selected": (reports[i].get(_CLASSIFIER_SLICE_KEY, {}).get("selection") or {}).get("selected"),
            "dataset_config_sha256": reports[i].get("dataset_config_sha256"),
            "config_sha256": reports[i].get("config_sha256"),
        }
        for i in range(len(reports))
    ]

    return {
        "seeds": seeds,
        "n_seeds": len(reports),
        "dataset_versions": sorted({str(r.get("dataset_version")) for r in reports}),
        "train_n": [r.get("train_n") for r in reports],
        "validation_n": [r.get("validation_n") for r in reports],
        "test_n": [r.get("test_n") for r in reports],
        "classifier": headline_operations(classifier_row),
        "per_type": per_type,
        "stress": headline_operations(stressed_row),
        "baselines": headline_operations(baseline_row),
        "regressor": headline_operations(regressor_row),
        "selections": selections,
        "synthetic_only": all(bool(r.get("synthetic_only")) for r in reports),
    }


def _fmt_agg(agg: dict[str, Any], digits: int = 4) -> str:
    return (
        f"{agg['mean']:.{digits}f} ± {agg['stdev']:.{digits}f} "
        f"[{agg['min']:.{digits}f}–{agg['max']:.{digits}f}] (n={len(agg['values_by_seed'])})"
    )


TITLE_ROWS_CLASSIFIER = (
    ("average_precision", "Test AP", 4),
    ("roc_auc", "ROC-AUC", 4),
    ("operating_f1", "F1 @ operating point", 4),
    ("precision_at_operating", "Precision", 4),
    ("recall_at_operating", "Recall", 4),
    ("accuracy_at_operating", "Accuracy", 4),
    ("brier_score", "Brier", 4),
    ("expected_calibration_error", "ECE", 4),
    ("f1_at_10_pct", "F1@10%", 4),
)

TITLE_ROWS_REGRESSOR = (
    ("regressor_mape_pct", "MAPE (%)", 2),
    ("regressor_mdae_pct", "MdAPE (%)", 2),
    ("regressor_mae", "MAE (Rp)", 0),
    ("regressor_rmse", "RMSE (Rp)", 0),
    ("regressor_r2", "R²", 4),
    ("regressor_upper_interval_coverage_pct", "Coverage upper bound (%)", 2),
)


def render_markdown(summary: dict[str, Any]) -> str:
    """Render the multi-seed summary as a standalone Markdown report."""
    lines: list[str] = []
    seeds_label = "/".join(str(s) for s in summary["seeds"])
    lines.append("# Multi-Seed Replikasi — Klasifikasi & Regressor Synthetic v2")
    lines.append("")
    lines.append(
        "> **Data sintetis demonstrator** ("
        + ", ".join(summary["dataset_versions"])
        + "). Seluruh angka di halaman ini adalah replikasi pada data sintetis dan "
        "**bukan validasi performa BPJS**. Tidak ada pemilihan/tuning terhadap test set: "
        "hyperparameter dipilih di validation pada tiap seed, test dievaluasi sekali per seed."
    )
    lines.append("")
    lines.append(f"- **Seeds**: {seeds_label} (n={summary['n_seeds']} replikasi, dataset diregenerasi penuh per seed)")
    lines.append(f"- **Split per seed**: train {summary['train_n'][0]:,} · validation {summary['validation_n'][0]:,} · test {summary['test_n'][0]:,}")
    lines.append(f"- **kandidat klasifikasi, bukan runtime** — RiskScore runtime tetap deterministik")
    lines.append("")
    lines.append("## Metrik klasifikasi gabungan (test natural)")
    lines.append("")
    lines.append("| Metrik | mean ± stdev [min–max] |")
    lines.append("|---|---|")
    for key, label, digits in TITLE_ROWS_CLASSIFIER:
        agg = summary["classifier"].get(key)
        if agg:
            lines.append(f"| {label} | {_fmt_agg(agg, digits)} |")
    lines.append("")
    lines.append("## Stress slice gabungan")
    lines.append("")
    lines.append("| Metrik | mean ± stdev [min–max] |")
    lines.append("|---|---|")
    for key, label in (
        ("enriched_average_precision", "Enriched AP"),
        ("ood_average_precision", "OOD AP"),
    ):
        agg = summary["stress"].get(key)
        if agg:
            lines.append(f"| {label} | {_fmt_agg(agg)} |")
    lines.append("")
    lines.append("## Per tipe anomali — test natural")
    lines.append("")
    lines.append("Spread antar-seed; slice tipis (positif kecil per tipe) rentan berfluktuasi, lapor apa adanya.")
    lines.append("")
    lines.append("| Tipe | AP mean ± stdev [min–max] | F1 mean ± stdev [min–max] |")
    lines.append("|---|---|---|")
    for type_name in sorted(summary["per_type"]):
        row = summary["per_type"][type_name]
        ap = row.get("average_precision")
        f1 = row.get("operating_f1")
        lines.append(
            f"| {type_name} "
            f"| {_fmt_agg(ap) if ap else 'n/a'} "
            f"| {_fmt_agg(f1) if f1 else 'n/a'} |"
        )
    lines.append("")
    lines.append("## Regressor benchmark biaya (test natural, klaim normal)")
    lines.append("")
    lines.append("| Metrik | mean ± stdev [min–max] |")
    lines.append("|---|---|")
    for key, label, digits in TITLE_ROWS_REGRESSOR:
        agg = summary["regressor"].get(key)
        if agg:
            lines.append(f"| {label} | {_fmt_agg(agg, digits)} |")
    lines.append("")
    lines.append("## Beban acuans (baseline, test natural)")
    lines.append("")
    lines.append("| Baseline | AP mean ± stdev [min–max] |")
    lines.append("|---|---|")
    for key, agg in sorted(summary["baselines"].items()):
        label = key.replace("baseline_", "").replace("_ap", "").replace("_", " ")
        lines.append(f"| {label} | {_fmt_agg(agg)} |")
    lines.append("")
    lines.append("## Konfigurasi terpilih per seed (dari validation)")
    lines.append("")
    lines.append("| Seed | depth | scale_pos_weight | best_iteration |")
    lines.append("|---|---|---|---|")
    for selection in summary["selections"]:
        chosen = selection.get("selected") or {}
        lines.append(
            f"| {selection['seed']} "
            f"| {chosen.get('max_depth', 'n/a')} "
            f"| {chosen.get('scale_pos_weight', 'n/a')} "
            f"| {chosen.get('best_iteration', 'n/a')} |"
        )
    lines.append("")
    lines.append("## Batasan")
    lines.append("")
    lines.append("- 5 seed → statistik disebarkan lunak; interval sebaran bukan CI formal yang diuji signifikan.")
    lines.append("- Prevalensi sintetis 3% membuat akurasi terlihat tinggi; AP/F1 per tipe lebih informatif.")
    lines.append("- Slice repeat-billing dibatasi desain hard negative readmission (~AP 0.18).")
    lines.append("- Ini replikasi stabilitas, bukan kepastian performa pada data riil BPJS.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate multi-seed synthetic v2 training reports")
    parser.add_argument("reports", nargs="+", type=Path, help="paths to synthetic_v2_training_report.json (one per seed)")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()

    reports = [json.loads(p.read_text(encoding="utf-8")) for p in args.reports]
    summary = aggregate_reports(reports)

    output_md = args.output or Path("docs/EVALUATION_MULTISEED.md")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(summary), encoding="utf-8")
    print(f"Markdown summary: {output_md}")

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON summary: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
