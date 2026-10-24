"""Runtime-ranking evaluation (Fase 3.4) — deterministic runtime path, no LLM.

Memasukkan sampel berlabel dari test set synthetic v2 ke jalur runtime
produksi secara in-process: `pipeline.score_claims` (rule clinical +
XGBoost financial + relasional in-memory + tier floor RiskScore 0-85),
`include_behavioral_context=False` (jalur produksi P0, bukan ablation).

Lingkup jujur yang dilaporkan:
- Slice ENRICHED (prevalensi di-angkat sengaja); metrik budget kondisional
  pada prevalensi slice.
- Relasional dihitung hanya dalam sampel (populasi = sampel).
- Floor `high` untuk exact duplicate tidak aktif offline (berbasis DB).
- Jendela relasional produksi 45 hari vs mekanisme repeat v2 gap 46-60 hari.
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.app.evaluation.metrics import evaluate_ranking, latency_metrics
from backend.app.evaluation.pipeline import score_claims


def _prepare_row(row: dict, label_row: dict) -> dict:
    """v2 row -> dict untuk ClaimInput + label runtime (is_synthetic_anomaly)."""
    prepared = dict(row)
    meds = prepared.pop("medication_codes", []) or []
    prepared["medication"] = [{"name": m, "quantity": 1} for m in meds]
    prepared["is_synthetic_anomaly"] = int(label_row["is_anomaly"])
    prepared["anomaly_type"] = str(label_row["anomaly_type"])
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", default=r"C:\Users\Radith\AppData\Local\Temp\opencode\synthetic_v2_standard_final24")
    parser.add_argument("--models-dir", default=str(REPO / "backend" / "models_trained" / "synthetic_v2"))
    parser.add_argument("--n-per-type", type=int, default=50)
    parser.add_argument("--n-normals", type=int, default=350)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-json", default=str(REPO / "backend" / "models_trained" / "runtime_ranking_eval.json"))
    parser.add_argument("--report", default=None, help="markdown report path, e.g. docs/RUNTIME_EVALUATION.md")
    parser.add_argument("--from-json", default=None, help="skip scoring; re-render --report from a saved payload")
    args = parser.parse_args()

    if args.from_json:
        payload = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        if not args.report:
            raise SystemExit("--from-json requires --report")
        _render_markdown(Path(args.report), payload)
        print(f"markdown report re-rendered: {args.report}")
        return 0

    from backend.app.ml.train_synthetic_v2 import _read_split
    from backend.app.ml.v2_features import build_classifier_features, build_training_context
    import xgboost as xgb
    from sklearn.metrics import average_precision_score

    dataset_dir = Path(args.dataset_dir)
    claims, labels = _read_split(dataset_dir, "test")
    labels_by_id = {row["claim_id"]: row for row in labels}

    rng = random.Random(args.seed)
    by_type = defaultdict(list)
    normal_pool = []
    for row in claims:
        label = labels_by_id.get(row["claim_id"])
        if label is None:
            continue
        if int(label["is_anomaly"]):
            by_type[str(label["anomaly_type"])].append(row)
        else:
            normal_pool.append(row)

    sample = []
    per_type_counts = {}
    for anomaly_type in sorted(by_type):
        rows = sorted(by_type[anomaly_type], key=lambda r: r["claim_id"])
        picked = rows if len(rows) <= args.n_per_type else rng.sample(rows, args.n_per_type)
        per_type_counts[anomaly_type] = len(picked)
        sample.extend(_prepare_row(row, labels_by_id[row["claim_id"]]) for row in picked)

    normals = list(normal_pool)
    rng.shuffle(normals)
    sample.extend(_prepare_row(row, labels_by_id[row["claim_id"]]) for row in normals[: args.n_normals])

    n_total = len(sample)
    positives = sum(1 for row in sample if row["is_synthetic_anomaly"])
    print(f"sample: n={n_total} positives={positives} prevalence={positives / n_total:.3f}")
    print(f"per type: {json.dumps(per_type_counts)}")

    # --- jalur runtime produksi (deterministik; LLM tidak dipanggil) ---
    results = asyncio.run(score_claims(sample, population=sample, include_behavioral_context=False))

    k_budgets = sorted({max(1, round(q * n_total)) for q in (0.05, 0.10, 0.15, 0.20, 0.30)})
    ranking = evaluate_ranking(results, k_values=k_budgets)

    latencies = [row.latency_ms for row in results]
    warmup = latencies[0]
    latency = latency_metrics(latencies[1:])
    methods = dict(Counter(row.method for row in results))

    tier_all = dict(Counter(row.priority_tier for row in results))
    tier_types = sorted({row.anomaly_type for row in results})
    tiers_per_type = {
        anomaly_type: dict(Counter(row.priority_tier for row in results if row.anomaly_type == anomaly_type))
        for anomaly_type in tier_types
    }
    score_medians = {
        anomaly_type: float(statistics.median(row.score for row in results if row.anomaly_type == anomaly_type))
        for anomaly_type in tier_types
    }

    from backend.app.evaluation.pipeline import _fraud_assessment
    flag_counts = defaultdict(lambda: {"n": 0, "repeat": 0, "cloning": 0, "unbundling": 0})
    for raw in sample:
        fraud = _fraud_assessment(raw, sample, include_behavioral_context=False)
        entry = flag_counts[raw["anomaly_type"]]
        entry["n"] += 1
        entry["repeat"] += int(bool(fraud.repeat_billing_flag))
        entry["cloning"] += int(bool(fraud.cloning_flag))
        entry["unbundling"] += int(bool(fraud.unbundling_flag))
    flag_ratios = {
        anomaly_type: {key: round(entry[key] / entry["n"], 3) for key in ("repeat", "cloning", "unbundling")}
        for anomaly_type, entry in sorted(flag_counts.items()) if entry["n"]
    }

    # --- kandidat classifier pada slice yang sama (AP pembanding) ---
    train_claims, train_labels = _read_split(dataset_dir, "train")
    train_y = np.asarray([int(row["is_anomaly"]) for row in train_labels], dtype=np.int32)
    context = build_training_context(train_claims, train_y)
    matrix, features = build_classifier_features(sample, context=context)
    report_cc = json.loads((Path(args.models_dir) / "synthetic_v2_training_report.json").read_text(encoding="utf-8"))
    best_iter = int(report_cc["classifier_candidate_not_runtime"]["selection"]["selected"]["best_iteration"])
    booster = xgb.Booster()
    booster.load_model(Path(args.models_dir) / "xgboost_classifier_candidate_synthetic_v2.json")
    candidate_scores = booster.predict(xgb.DMatrix(matrix, feature_names=features), iteration_range=(0, best_iter))
    y_sample = np.asarray([row["is_synthetic_anomaly"] for row in sample], dtype=np.int32)
    candidate_ap = float(average_precision_score(y_sample, candidate_scores))

    payload = {
        "sample": {"n": n_total, "positives": positives, "prevalence": positives / n_total,
                   "n_per_type": args.n_per_type, "n_normals": args.n_normals, "seed": args.seed,
                   "per_type": per_type_counts},
        "population_note": "relational features computed within-sample only; exact-duplicate High floor is DB-gated and unreachable offline",
        "runtime_ranking": ranking,
        "latency": {"first_claim_ms": warmup, "post_warmup": latency, "financial_method_counts": methods},
        "tier_overall": tier_all,
        "tier_per_type": tiers_per_type,
        "score_median_per_type": score_medians,
        "fraud_flag_ratios_per_type": flag_ratios,
        "candidate_ap_same_slice": candidate_ap,
        "discipline": "deterministic runtime path; no LLM calls; synthetic demonstrator only, not BPJS validation",
    }
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("\n=== runtime ranking (enriched slice) ===")
    for key in k_budgets:
        p = ranking["precision_at_k"][str(key)].get("value")
        r = ranking["recall_at_k"][str(key)].get("value")
        print(f"K={key:4d} ({key / n_total:.0%}): precision={p:.3f} recall={r:.3f}" if p is not None else f"K={key}: not computable")
    print(f"runtime AP (slice)      = {ranking['average_precision'].get('value'):.4f}")
    print(f"candidate AP (same slice) = {candidate_ap:.4f}")
    print("tier overall:", tier_all)
    print(f"latency: first={warmup:.0f} ms; post-warmup p50={latency['p50_ms']:.0f} ms, p95={latency['p95_ms']:.0f} ms")
    print("financial methods:", methods)
    print("score median per type:")
    for anomaly_type, value in score_medians.items():
        print(f"  {anomaly_type:16s} {value:6.1f}  tiers={json.dumps(tiers_per_type[anomaly_type])}")
    print("flag ratios per type (diagnostic):")
    for anomaly_type, entry in flag_ratios.items():
        print(f"  {anomaly_type:16s} repeat={entry['repeat']} cloning={entry['cloning']} unbundling={entry['unbundling']}")

    if args.report:
        _render_markdown(Path(args.report), payload)
        print(f"markdown report: {args.report}")
    return 0


def _render_markdown(report_path: Path, payload: dict) -> None:
    ranking = payload["runtime_ranking"]
    n = payload["sample"]["n"]
    lines = [
        "# Runtime-ranking evaluation (Fase 3.4)",
        "",
        "> **Synthetic demonstrator only — not BPJS performance validation.**",
        "",
        "- Jalur yang diukur: **runtime produksi deterministik** (rule clinical + XGBoost financial + relasional in-memory + tier floors, RiskScore 0–85) via `evaluation.pipeline.score_claims`, **tanpa LLM**.",
        f"- Sampel slice enriched: {payload['sample']['positives']} anomali ({payload['sample']['n_per_type']} per tipe × 7) + {payload['sample']['n_normals']} normal, total {n}; prevalensi di-angkat sengaja ke {payload['sample']['prevalence']:.0%} — precision@K bersyarat pada prevalensi ini.",
        "- Test split seed-42 yang sama dengan training kanonik; metadata model: `backend/models_trained/synthetic_v2_training_report.json` (gitignored).",
        f"- Pembanding: kandidat ML (28 fitur) dijalankan pada slice yang sama — AP {payload['candidate_ap_same_slice']:.4f}.",
        "- Lingkup: relasional dihitung dalam-sampel saja; floor `high` exact-duplicate tidak aktif offline (DB-gated); jendela relasional produksi 45 hari vs mekanisme repeat v2 gap 46–60 hari.",
        "- Etika: hyperparameter/runtime diukur apa adanya; semua label sintetis.",
        "",
        "## Ranking budget (top-K pada slice)",
        "",
        "| K (porsi slice) | Precision@K | Recall@K |",
        "|---|---|---|",
    ]
    for key in sorted(ranking["precision_at_k"], key=int):
        p = ranking["precision_at_k"][key]["value"]
        r = ranking["recall_at_k"][key]["value"]
        lines.append(f"| {int(key):,} ({int(key) / n:.0%}) | {p:.3f} | {r:.3f} |")
    lines += [
        "",
        f"**AP slice**: runtime {ranking['average_precision']['value']:.4f} vs kandidat ML {payload['candidate_ap_same_slice']:.4f} pada slice identik — runtime tetap prioritas penyaring; kandidat ML tetap kandidat (tier runtime tidak berubah).",
        "",
        "## Latensi (path deterministik, tanpa LLM)",
        "",
        f"- klaim pertama (build model financial + SHAP sekali): {payload['latency']['first_claim_ms']:.0f} ms",
        f"- sesudah warmup: p50 {payload['latency']['post_warmup']['p50_ms']:.0f} ms, p95 {payload['latency']['post_warmup']['p95_ms']:.0f} ms (metode financial: {json.dumps(payload['latency']['financial_method_counts'])})",
        "- kontras: e2e produksi dengan LLM+SHAP p50 ≈ 7,3 s (probe live terpisah); angka ini membedakan komponen deterministik dari biaya narasi LLM.",
        "",
        "## Distribusi tier",
        "",
        f"- keseluruhan: {json.dumps(payload['tier_overall'])}",
        "",
        "| Tipe | median skor | tier medium+high |",
        "|---|---|---|",
    ]
    for anomaly_type in sorted(payload["score_median_per_type"]):
        med = payload["score_median_per_type"][anomaly_type]
        tiers = payload["tier_per_type"].get(anomaly_type, {})
        hits = tiers.get("medium", 0) + tiers.get("high", 0)
        lines.append(f"| {anomaly_type} | {med:.1f} | {hits} |")
    lines += [
        "",
        "## Rasio flag fraud per tipe (diagnostik, bukan field rapor)",
        "",
        "| Tipe | repeat | cloning | unbundling |",
        "|---|---|---|---|",
    ]
    for anomaly_type, entry in payload["fraud_flag_ratios_per_type"].items():
        lines.append(f"| {anomaly_type} | {entry['repeat']:.2f} | {entry['cloning']:.2f} | {entry['unbundling']:.2f} |")
    lines += [
        "",
        "## Limitations",
        "",
        "- Prevalensi slice di-angkat (enriched): precision@K bukan angka produksi; gunakan recall@K dan AP sebagai ukuran ranking relatif.",
        "- Konteks relasional = sampel 700 klaim; di produksi konteks berasal dari riwayat DB pasien/faskes (konsekuen: hitungan flag bisa berbeda).",
        "- Runtime memakai kartu tarif v1 (10 keluarga diagnosis) — sebagian besar diagnosis v2 jatuh ke fallback z-score financial; keterbatasan nyata, dilaporkan apa adanya.",
        "- Floor tier `high` exact-duplicate hanya aktif di jalur produksi berbasis DB (gate `validate_deterministic`).",
        "- Jendela 45 hari produksi vs mekanisme repeat v2 gap 46–60 hari menjelaskan rasio flag repeat yang rendah: rerancangan episode-linking ada di backlog, bukan kegagalan deteksi yang disembunyikan.",
        "- Semua claim/label sintetis; bukan validasi kinerja BPJS.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
