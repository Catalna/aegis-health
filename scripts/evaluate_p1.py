"""Run the offline P1 model validation evaluator."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.evaluation.runner import run_evaluation  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate J-ARI risk ranking on synthetic held-out claims.")
    parser.add_argument("--output", type=Path, default=ROOT / "backend/models_trained/p1_evaluation_results.json")
    parser.add_argument("--train-seed", type=int, default=42)
    parser.add_argument("--holdout-seed", type=int, default=2026)
    parser.add_argument("--allow-model-fallback", action="store_true")
    parser.add_argument("--num-normal", type=int, default=50)
    parser.add_argument("--num-upcoding", type=int, default=5)
    parser.add_argument("--num-cloning-pairs", type=int, default=3)
    parser.add_argument("--num-repeat-billing", type=int, default=3)
    parser.add_argument("--num-phantom", type=int, default=3)
    parser.add_argument("--num-prolonged-los", type=int, default=3)
    parser.add_argument("--num-inflated", type=int, default=3)
    parser.add_argument("--num-unbundling-groups", type=int, default=2)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    counts = {
        key: getattr(args, key)
        for key in (
            "num_normal", "num_upcoding", "num_cloning_pairs", "num_repeat_billing",
            "num_phantom", "num_prolonged_los", "num_inflated", "num_unbundling_groups",
        )
    }
    try:
        run_evaluation(
            args.output,
            train_seed=args.train_seed,
            holdout_seed=args.holdout_seed,
            generator_counts=counts,
            allow_model_fallback=args.allow_model_fallback,
        )
    except Exception as exc:
        print(f"P1 evaluation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
