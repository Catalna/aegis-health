import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.evaluation.pipeline import EvaluationResult
from backend.app.evaluation.runner import P1Artifact, build_artifact, write_artifact

ROOT = Path(__file__).resolve().parents[2]


def test_artifact_round_trip_contains_required_metadata(tmp_path):
    artifact = build_artifact(
        dataset={"version": "p1-test", "seed": 2026, "counts": {"none": 1}},
        metrics={"status": "measured"},
        ablation=[],
        errors=[],
        limitations=["synthetic data"],
    )
    path = tmp_path / "p1.json"
    write_artifact(path, artifact)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["engine"]["analysis_version"] >= 6
    assert payload["dataset"]["version"] == "p1-test"


def test_artifact_rejects_missing_dataset_metadata():
    with pytest.raises(ValueError, match="dataset metadata"):
        build_artifact(dataset={}, metrics={}, ablation=[], errors=[], limitations=[])


def test_p1_cli_smoke_writes_artifact(tmp_path):
    output = tmp_path / "p1-cli.json"
    command = [
        sys.executable,
        "scripts/evaluate_p1.py",
        "--output",
        str(output),
        "--num-normal",
        "3",
        "--num-upcoding",
        "1",
        "--num-cloning-pairs",
        "1",
        "--num-repeat-billing",
        "1",
        "--num-phantom",
        "1",
        "--num-prolonged-los",
        "1",
        "--num-inflated",
        "1",
        "--num-unbundling-groups",
        "1",
        "--allow-model-fallback",
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["engine"]["analysis_version"] >= 6
