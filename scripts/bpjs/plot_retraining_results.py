"""Compatibility entrypoint: render the per-model cost candidate C report (8 figures).

The standalone comparison PNG was retired; the maintained deliverable is one
figure-set per model. Generator: scripts/plot_cost_c_report.py (requires the
parity-checked test artifact from scripts/bpjs/eval_cost_candidate_c.py).
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.plot_cost_c_report import main  # noqa: E402

if __name__ == "__main__":
    main()
