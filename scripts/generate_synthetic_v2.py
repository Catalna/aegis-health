"""Generate a versioned synthetic-only J-ARI dataset."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.data.synthetic_v2.generator import generate_synthetic_v2  # noqa: E402
from backend.app.data.synthetic_v2.io import write_synthetic_v2  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("dev", "standard", "large"), default="standard")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "data/synthetic_v2")
    parser.add_argument("--format", choices=("parquet", "csv", "both"), default="parquet")
    args = parser.parse_args()
    try:
        bundle = generate_synthetic_v2(profile=args.profile, seed=args.seed)
        result = write_synthetic_v2(bundle, args.out, args.format)
    except Exception as exc:
        print(f"Synthetic v2 generation failed: {exc}", file=sys.stderr)
        return 1
    natural_count = sum(len(bundle[split]["claims"]) for split in ("train", "validation", "test"))
    stress_count = sum(bundle["stress_counts"].values())
    print(f"Synthetic v2 {args.profile}: {natural_count:,} natural-split claims")
    print(f"Additional stress sets: {stress_count:,}; total generated: {natural_count + stress_count:,}")
    print(f"Validation: {result['status']}; config SHA-256: {result['config_sha256']}")
    print(f"Output: {result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
