"""Compatibility entrypoint: render the per-model classifier v3 report (8 figures).

The comparison-style figure set was retired; the maintained deliverable is one
figure-set per model. Generator: scripts/plot_classifier_v3_report.py.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.plot_classifier_v3_report import main  # noqa: E402

if __name__ == "__main__":
    main()
