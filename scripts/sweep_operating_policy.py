"""Sweep kebijakan ambang operasi untuk model kandidat seed-42.

Etika seleksi: ambang kebijakan dipilih HANYA dari validation (target recall);
test dibaca sekali sebagai pelaporan — sama seperti protokol trainer. Tanpa
retraining. Skema laporan per kebijakan: precision/recall/F1/jumlah alert.

Pemakaian:
    python scripts/sweep_operating_policy.py [--models-dir PATH] [--dataset-dir PATH] [--out PATH]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import f1_score, precision_score, recall_score

REPO = Path(__file__).resolve().parents[1]
TARGETS = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


def _prf(y: np.ndarray, scores: np.ndarray, thr: float) -> tuple[float, float, float, int]:
    pred = scores >= thr
    return (
        float(precision_score(y, pred)),
        float(recall_score(y, pred)),
        float(f1_score(y, pred)),
        int(pred.sum()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", default=str(REPO / "backend" / "models_trained" / "synthetic_v2"))
    parser.add_argument("--dataset-dir", default=r"C:\Users\Radith\AppData\Local\Temp\opencode\synthetic_v2_standard_final24")
    parser.add_argument("--out", default=None, help="optional JSON output path")
    args = parser.parse_args()

    sys.path.insert(0, str(REPO))
    from backend.app.ml.train_synthetic_v2 import _read_split
    from backend.app.ml.v2_features import build_classifier_features, build_training_context

    models_dir = Path(args.models_dir)
    report = json.loads((models_dir / "synthetic_v2_training_report.json").read_text(encoding="utf-8"))
    cc = report["classifier_candidate_not_runtime"]
    best_iter = int(cc["selection"]["selected"]["best_iteration"])
    f1_point = float(cc["test_metrics"]["operating_point"]["threshold"])

    booster = xgb.Booster()
    booster.load_model(models_dir / "xgboost_classifier_candidate_synthetic_v2.json")

    dataset_dir = Path(args.dataset_dir)
    train_claims, train_labels = _read_split(dataset_dir, "train")
    train_y = np.asarray([int(row["is_anomaly"]) for row in train_labels], dtype=np.int32)
    context = build_training_context(train_claims, train_y)

    payloads: dict[str, dict[str, object]] = {}
    for split in ("validation", "test"):
        claims, labels = _read_split(dataset_dir, split)
        y = np.asarray([int(row["is_anomaly"]) for row in labels], dtype=np.int32)
        matrix, features = build_classifier_features(claims, context=context)
        scores = booster.predict(xgb.DMatrix(matrix, feature_names=features), iteration_range=(0, best_iter))
        payloads[split] = {"y": y, "scores": scores, "types": [row.get("anomaly_type") for row in labels]}
        del matrix, claims, labels

    y_val = payloads["validation"]["y"]
    y_test = payloads["test"]["y"]
    s_val = payloads["validation"]["scores"]
    s_test = payloads["test"]["scores"]

    p, r, f1, n = _prf(y_test, s_test, f1_point)
    print(f"sanity F1-max @thr={f1_point:.5f}: test P={p:.4f} R={r:.4f} "
          f"(laporan R={cc['test_metrics']['operating_point'].get('recall')})")

    k_pos = int(y_val.sum())
    rows = []
    print(f"\n{'policy':>6} | {'threshold':>9} | val P/R/F1/alert | test P/R/F1/alert")
    for target in TARGETS:
        k = int(np.ceil(target * k_pos))
        thr = float(np.sort(s_val)[::-1][min(k - 1, len(s_val) - 1)])
        pv, rv, fv, nv = _prf(y_val, s_val, thr)
        pt, rt, ft, nt = _prf(y_test, s_test, thr)
        rows.append({
            "target_recall": target, "threshold_validation": thr,
            "val_recall": rv, "val_precision": pv, "val_f1": fv, "n_alert_validation": nv,
            "test_recall": rt, "test_precision": pt, "test_f1": ft, "n_alert_test": nt,
        })
        print(f"{target:.2f} | {thr:9.5f} | {pv:.3f}/{rv:.3f}/{fv:.3f}/{nv} | {pt:.3f}/{rt:.3f}/{ft:.3f}/{nt}")

    types_test = payloads["test"]["types"]
    pred = s_test >= f1_point
    print(f"\nRecall per tipe pada ambang F1-max ({f1_point:.5f}):")
    for anomaly in sorted({t for t in types_test if t != "none"}):
        mask = np.asarray([t == anomaly for t in types_test])
        positives = int(y_test[mask].sum())
        recall = float((pred & (y_test == 1) & mask).sum() / positives) if positives else float("nan")
        print(f"  {anomaly:16s} pos={positives:5d} recall={recall:.3f}")

    payload = {
        "models_dir": str(models_dir),
        "f1_max_threshold": f1_point,
        "policies": rows,
        "per_type_recall_at_f1_max": {},
    }
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"\nsaved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
