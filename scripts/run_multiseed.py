#!/usr/bin/env python
"""Multi-seed replication driver for the synthetic v2 evaluation.

For each requested seed:
1. Generate the standard dataset (train/val/test + enriched + OOD) with that
   seed. If the dataset for the seed already exists (deterministic generator),
   the regeneration step is skipped.
2. Train the v2 regressor + classifier candidate on it. No --report is passed:
   the run writes its JSON/MD report into its own output directory, so the
   canonical docs/EVALUATION_REPORT.md (seed 42) is never overwritten.

Sequential by design to limit memory pressure on the demo laptop.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMP_ROOT = Path(
    os.environ.get("OPENCODE_TEMP", Path(os.environ.get("TEMP", "/tmp")) / "opencode")
)
DEFAULT_OUT_ROOT = ROOT / "backend" / "models_trained" / "synthetic_v2_multiseed"


def _run(command: list[str]) -> None:
    print(f"\n$ {' '.join(str(part) for part in command)}", flush=True)
    started = time.perf_counter()
    subprocess.run(command, cwd=ROOT, check=True)
    elapsed = time.perf_counter() - started
    print(f"[driver] selesai dalam {elapsed:.1f}s", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-seed synthetic v2 replication")
    parser.add_argument("--seeds", type=int, nargs="+", default=[43, 44, 45, 46])
    parser.add_argument("--profile", default="standard", choices=("dev", "standard"))
    parser.add_argument("--format", default="parquet", choices=("parquet", "csv", "both"))
    parser.add_argument("--temp-root", type=Path, default=DEFAULT_TEMP_ROOT)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = parser.parse_args()

    args.temp_root.mkdir(parents=True, exist_ok=True)
    args.out_root.mkdir(parents=True, exist_ok=True)

    aggregate_start = time.perf_counter()
    for seed in args.seeds:
        dataset_dir = args.temp_root / f"synthetic_v2_ms_seed{seed}"
        out_dir = args.out_root / f"seed{seed}"
        marker = dataset_dir / "schema.json"
        if marker.exists():
            print(f"\n[driver] seed {seed}: dataset sudah ada, lewati generasi ({dataset_dir})", flush=True)
        else:
            _run([
                sys.executable,
                "scripts/generate_synthetic_v2.py",
                "--profile", args.profile,
                "--seed", str(seed),
                "--out", str(dataset_dir),
                "--format", args.format,
            ])
        _run([
            sys.executable,
            "-m", "backend.app.ml.train_synthetic_v2",
            "--dataset", str(dataset_dir),
            "--out", str(out_dir),
            "--seed", str(seed),
        ])

    total_minutes = (time.perf_counter() - aggregate_start) / 60.0
    print(f"\n[driver] total {len(args.seeds)} seed dalam {total_minutes:.1f} menit", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
