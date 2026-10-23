"""Validate synthetic-v2 split, label separation, IDs, and normal distributions."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.data.synthetic_v2.io import load_synthetic_v2  # noqa: E402
from backend.app.data.synthetic_v2.validation import validate_synthetic_v2  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        bundle = load_synthetic_v2(args.input)
        report = validate_synthetic_v2(bundle)
    except Exception as exc:
        print(f"Synthetic dataset invalid: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
