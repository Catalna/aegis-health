"""Compatibility entrypoint: render the current model portfolio figure.

The old v2.4-only figure set was retired; use scripts/plot_model_portfolio.py.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.plot_model_portfolio import main  # noqa: E402

if __name__ == "__main__":
    main()
