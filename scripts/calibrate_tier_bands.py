"""Kalibrasi ambang tier runtime (Fase 2 leftover) — disiplin label terpisah.

Aturan PRA-REGISTRASI (ditulis sebelum melihat hasil):
1. Skor sampel slice VALIDATION (50 per tipe + 350 normal) via jalur runtime
   deterministik (`pipeline.score_claims`, tanpa LLM).
2. Grid ambang (medium_m, high_h), h > m; untuk tiap pasangan hitung di slice
   validation: alert_frac (share klaim medium+high), high_frac, precision_/
   recall_pos pada alert dan high.
3. Kandidat dipilih HANYA dari pasangan dengan 0.10 <= alert_frac <= 0.22 dan
   high_frac <= 0.08; pemilihnya: precision_pos tertinggi, tie-break recall_pos.
4. Ambang terpilih diterapkan SEKALI ke slice TEST untuk verifikasi transfer
   (distribusi tier + precision/recall). Tidak ada grid, tidak ada tuning di test.
5. RULE v2 (pra-terdaftar 2026-10-24): bila rule v1 kosong, tambah titik medium 48
   dan floor alert 5%. RULE v3 (pra-terdaftar 2026-10-24 sebelum run ke-4): skor
   runtime terkuantisasi (gumpalan ~35/48/60, gap kosong), maka (a) grid medium/
   high diambil dari NILAI SKOR YANG ADA di data (bukan grid reguler), (b)
   pemilihan band = minimalkan |alert_frac - 0.20| (target kapasitas verifier),
   tie-break precision_pos; high = nilai skor terkecil > medium dengan
   high_frac <= 0.10; (c) pelanggaran diarahkan TRANSPARAN paling dekat kapasitas
   (exit error dihapus). Verifikasi test tetap satu kali.
6. Skrip melaporkan; perubahan konstanta `risk_engine`/`pipeline` dilakukan
   manual terpisah dengan test penuh setelah hasil terverifikasi.
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from backend.app.evaluation.pipeline import score_claims
from runtime_ranking_eval import _prepare_row

DEFAULT_MEDIUM = 25.0
DEFAULT_HIGH = 60.0


def _build_sample(dataset_dir: Path, split: str, n_per_type: int, n_normals: int, seed: int):
    from backend.app.ml.train_synthetic_v2 import _read_split
    claims, labels = _read_split(dataset_dir, split)
    labels_by_id = {row["claim_id"]: row for row in labels}
    rng = random.Random(seed)
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
    sample, per_type = [], {}
    for anomaly_type in sorted(by_type):
        rows = sorted(by_type[anomaly_type], key=lambda r: r["claim_id"])
        picked = rows if len(rows) <= n_per_type else rng.sample(rows, n_per_type)
        per_type[anomaly_type] = len(picked)
        sample.extend(_prepare_row(row, labels_by_id[row["claim_id"]]) for row in picked)
    normals = list(normal_pool)
    rng.shuffle(normals)
    sample.extend(_prepare_row(row, labels_by_id[row["claim_id"]]) for row in normals[:n_normals])
    return sample, per_type


def _score(sample):
    return asyncio.run(score_claims(sample, population=sample, include_behavioral_context=False))


def _band_metrics(results, medium_th: float, high_th: float):
    n = len(results)
    alerts = [r for r in results if r.score >= medium_th]
    highs = [r for r in results if r.score >= high_th]
    positives = [r for r in results if r.label]
    hit_alert = sum(1 for r in alerts if r.label)
    hit_high = sum(1 for r in highs if r.label)
    tiers = dict(Counter(
        "high" if r.score >= high_th else ("medium" if r.score >= medium_th else "low") for r in results))
    return {
        "alert_frac": len(alerts) / n,
        "high_frac": len(highs) / n,
        "precision_alert": hit_alert / len(alerts) if alerts else 0.0,
        "recall_pos_alert": hit_alert / len(positives) if positives else 0.0,
        "precision_high": hit_high / len(highs) if highs else 0.0,
        "recall_pos_high": hit_high / len(positives) if positives else 0.0,
        "tier_counts": tiers,
    }


def _quantiles(values, qs=(0.25, 0.5, 0.75, 0.9)):
    hundredths = statistics.quantiles(values, n=100, method="inclusive")
    return {f"{q:.2f}".rstrip("0").rstrip("."): hundredths[int(q * 100) - 1] for q in qs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", default=r"C:\Users\Radith\AppData\Local\Temp\opencode\synthetic_v2_standard_final24")
    parser.add_argument("--models-dir", default=str(REPO / "backend" / "models_trained" / "synthetic_v2"))
    parser.add_argument("--n-per-type", type=int, default=50)
    parser.add_argument("--n-normals", type=int, default=350)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--grid-medium", type=float, nargs="+", default=[30, 35, 40, 45, 50])
    parser.add_argument("--grid-high", type=float, nargs="+", default=[55, 60, 65, 70])
    parser.add_argument("--max-alert-frac", type=float, default=0.22)
    parser.add_argument("--max-high-frac", type=float, default=0.08)
    parser.add_argument("--min-alert-frac", type=float, default=0.10)
    parser.add_argument("--out-json", default=str(REPO / "backend" / "models_trained" / "tier_band_calibration.json"))
    parser.add_argument("--report", default=None)
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    validation_sample, per_type_val = _build_sample(dataset_dir, "validation", args.n_per_type, args.n_normals, args.seed)
    val_results = _score(validation_sample)
    print(f"validation slice scored: n={len(val_results)} prevalence="
          f"{sum(1 for r in val_results if r.label) / len(val_results):.3f}")

    val_norm_scores = sorted(r.score for r in val_results if not r.label)
    val_pos_scores = sorted(r.score for r in val_results if r.label)
    q_normal = _quantiles(val_norm_scores)
    q_anomaly = _quantiles(val_pos_scores)
    print("score quantiles NORMAL  :", {k: round(v, 1) for k, v in q_normal.items()})
    print("score quantiles ANOMALY :", {k: round(v, 1) for k, v in q_anomaly.items()})

    hist = defaultdict(lambda: {"normal": 0, "anomaly": 0})
    for r in val_results:
        hist[r.score]["anomaly" if r.label else "normal"] += 1
    print("\nscore histogram validation (score: normal/anomaly):")
    for value in sorted(hist):
        print(f"  {value:6.1f}: {hist[value]['normal']:3d}/{hist[value]['anomaly']:3d}")

    # RULE v3: grid mengikuti nilai skor yang benar-benar ada di data (skor terkuantisasi).
    val_scores = sorted({r.score for r in val_results})
    medium_opts = sorted({s for s in val_scores if 30.0 <= s <= 55.0})
    high_opts = sorted({s for s in val_scores if s >= 55.0})
    if not medium_opts:
        medium_opts = [30.0, 35.0, 40.0, 45.0, 50.0]
    if not high_opts:
        high_opts = [60.0]
    grid = []
    for medium in medium_opts:
        for high in high_opts:
            if high <= medium:
                continue
            metrics = _band_metrics(val_results, float(medium), float(high))
            grid.append({"medium": float(medium), "high": float(high), **metrics})

    rule_version = 3
    eligible = [g for g in grid
                if args.min_alert_frac <= g["alert_frac"] <= args.max_alert_frac and g["high_frac"] <= args.max_high_frac]
    violated = not eligible
    if not eligible:
        # RULE v3 fallback: window kosong karena skor terkuantisasi; pilih band
        # terdekat ke target kapasitas verifier 20%, tie-break precision.
        print("pre-registered window empty (quantized scores) -> rule v3 fallback: "
              "minimize |alert_frac - 0.20|, tie-break precision")
        chosen = min(grid, key=lambda g: (abs(g["alert_frac"] - 0.20), -g["precision_alert"], -g["recall_pos_alert"]))
    else:
        chosen = max(eligible, key=lambda g: (g["precision_alert"], g["recall_pos_alert"]))

    print(f"\ngrid rule v3 (medium/high = nilai skor nyata; "
          f"{'WINDOW KOSONG - fallback terdekat kapasitas' if violated else 'dalam window pra-registrasi'}):")
    for g in grid:
        mark = "  ==> SELECTED" if g is chosen else ""
        star = " " if g in eligible else "x"
        print(f"{star} medium>={g['medium']:5.1f} high>={g['high']:5.1f} | alert={g['alert_frac']:.3f} "
              f"high={g['high_frac']:.3f} | prec={g['precision_alert']:.3f} rec={g['recall_pos_alert']:.3f} "
              f"| h_prec={g['precision_high']:.3f} h_rec={g['recall_pos_high']:.3f}{mark}")

    baseline_val = _band_metrics(val_results, DEFAULT_MEDIUM, DEFAULT_HIGH)
    print(f"\nDEFAULT lama (25/60) di validation: {json.dumps({k: v for k, v in baseline_val.items() if k != 'tier_counts'})}")
    print("tier_counts default (validation):", baseline_val["tier_counts"])

    test_sample, per_type_test = _build_sample(dataset_dir, "test", args.n_per_type, args.n_normals, args.seed)
    test_results = _score(test_sample)
    chosen_test = _band_metrics(test_results, chosen["medium"], chosen["high"])
    baseline_test = _band_metrics(test_results, DEFAULT_MEDIUM, DEFAULT_HIGH)
    tiers_per_type_test = {}
    for anomaly_type in sorted({r.anomaly_type for r in test_results}):
        rows = [r for r in test_results if r.anomaly_type == anomaly_type]
        tiers_per_type_test[anomaly_type] = dict(Counter(
            "high" if r.score >= chosen["high"] else ("medium" if r.score >= chosen["medium"] else "low")
            for r in rows))

    payload = {
        "selection_discipline": {
            "split_for_band_selection": "validation",
            "split_for_verification": "test (single read)",
            "rule": (f"v3: grid from observed score values; "
                     f"window {args.min_alert_frac:.2f}<=alert_frac<={args.max_alert_frac:.2f} AND "
                     f"high_frac<={args.max_high_frac:.2f}; maximize precision_pos on alerts; tie-break recall_pos; "
                     f"empty window -> minimize |alert_frac-0.20|, tie-break precision"),
            "rule_version": rule_version,
        },
        "default_bands": {"medium": DEFAULT_MEDIUM, "high": DEFAULT_HIGH},
        "validation": {
            "n": len(val_results),
            "prevalence": sum(1 for r in val_results if r.label) / len(val_results),
            "quantiles": {"normal": q_normal, "anomaly": q_anomaly},
            "baseline_metrics": baseline_val,
            "grid": grid,
            "chosen": chosen,
        },
        "test_verification": {
            "n": len(test_results),
            "prevalence": sum(1 for r in test_results if r.label) / len(test_results),
            "chosen_bands_metrics": chosen_test,
            "default_bands_metrics": baseline_test,
            "tier_counts_per_type_chosen": tiers_per_type_test,
        },
        "discipline": "deterministic runtime path; no LLM calls; synthetic demonstrator only, not BPJS validation",
    }
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("\n=== verification on test (single read) ===")
    print(f"chosen bands: medium>={chosen['medium']} high>={chosen['high']}")
    print("chosen :", json.dumps({k: v for k, v in chosen_test.items() if k != 'tier_counts'}))
    print("tier test (chosen):", chosen_test["tier_counts"])
    print("default:", json.dumps({k: v for k, v in baseline_test.items() if k != 'tier_counts'}))
    print("tier test (default):", baseline_test["tier_counts"])
    for anomaly_type, tiers in tiers_per_type_test.items():
        print(f"  {anomaly_type:16s} {json.dumps(tiers)}")

    if args.report:
        _render_markdown(Path(args.report), payload)
        print(f"markdown report: {args.report}")
    return 0


def _render_markdown(report_path: Path, payload: dict) -> None:
    grid = payload["validation"]["grid"]
    chosen = payload["validation"]["chosen"]
    b_val = {k: v for k, v in payload["validation"]["baseline_metrics"].items() if k != "tier_counts"}
    b_test = {k: v for k, v in payload["test_verification"]["default_bands_metrics"].items() if k != "tier_counts"}
    c_test = {k: v for k, v in payload["test_verification"]["chosen_bands_metrics"].items() if k != "tier_counts"}
    lines = [
        "# Kalibrasi ambang tier runtime (Fase 2 leftover)",
        "",
        "> **Synthetic demonstrator only — not BPJS performance validation.**",
        "",
        f"- Ambang lama: medium ≥ {payload['default_bands']['medium']:.0f}, high ≥ {payload['default_bands']['high']:.0f}. Kalibrasi memakai slice **validation**; verifikasi transfer **sekali** di slice test.",
        f"- Aturan pra-registrasi: {payload['selection_discipline']['rule']}",
        f"- Slice: {payload['validation']['n']} klaim validation (prevalensi {payload['validation']['prevalence']:.0%}); slice test {payload['test_verification']['n']} (prevalensi {payload['test_verification']['prevalence']:.0%}).",
        "",
        "## Kuantil skor (validation)",
        "",
        "| Label | p25 | p50 | p75 | p90 |",
        "|---|---|---|---|---|",
    ]
    for label, q in payload["validation"]["quantiles"].items():
        lines.append(f"| {label} | {q['0.25']:.1f} | {q['0.5']:.1f} | {q['0.75']:.1f} | {q['0.9']:.1f} |")
    lines += [
        "",
        "## Laporan grid singkat (kolom kunci: precision & recall_pos pada alert, di validation)",
        "",
        "| medium ≥ | high ≥ | alert_frac | precision | recall_pos |",
        "|---|---|---|---|---|",
    ]
    for g in grid:
        mark = " **(terpilih)**" if g is chosen else ""
        lines.append(f"| {g['medium']:.1f} | {g['high']:.1f} | {g['alert_frac']:.3f} | {g['precision_alert']:.3f} | {g['recall_pos_alert']:.3f}{mark} |")
    lines += [
        "",
        "## Baseline lama vs ambang terpilih",
        "",
        "| Metrik | default (25/60) validation | default test | terpilih test (verifikasi) |",
        "|---|---|---|---|",
        f"| alert_frac | {b_val['alert_frac']:.3f} | {b_test['alert_frac']:.3f} | {c_test['alert_frac']:.3f} |",
        f"| precision (alert) | {b_val['precision_alert']:.3f} | {b_test['precision_alert']:.3f} | {c_test['precision_alert']:.3f} |",
        f"| recall_pos (alert) | {b_val['recall_pos_alert']:.3f} | {b_test['recall_pos_alert']:.3f} | {c_test['recall_pos_alert']:.3f} |",
        f"| high_frac | {b_val['high_frac']:.3f} | {b_test['high_frac']:.3f} | {c_test['high_frac']:.3f} |",
        "",
        f"**Ambang terpilih: medium ≥ {chosen['medium']:.0f}, high ≥ {chosen['high']:.0f}** — dipilih dari grid di validation dengan aturan pra-registrasi; test diverifikasi sekali dan angkanya dilaporkan apa adanya.",
        "",
        "## Distribusi tier test (ambang terpilih) per tipe",
        "",
        "| Tipe | low | medium | high |",
        "|---|---|---|---|",
    ]
    for anomaly_type, tiers in payload["test_verification"]["tier_counts_per_type_chosen"].items():
        lines.append(f"| {anomaly_type} | {tiers.get('low', 0)} | {tiers.get('medium', 0)} | {tiers.get('high', 0)} |")
    lines += [
        "",
        "## Limitations",
        "",
        "- Prevalensi slice 50% (enriched): fraksi alert di produksi (~3% prevalensi) akan berbeda; angka fraksi di sini relevan sebagai ordering band, bukan volume absolut.",
        "- Konteks relasional = sampel; floor exact-duplicate `high` tetap DB-gated.",
        "- Perubahan konstanta band diterapkan dalam land terpisah dengan test suite penuh; test yang menyandera batas lama diperbarui sebagai bagian land tersebut.",
        "- Semua label sintetis; bukan validasi BPJS.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
