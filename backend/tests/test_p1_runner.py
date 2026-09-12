import json

import pytest

from backend.app.evaluation.pipeline import EvaluationResult
from backend.app.evaluation.runner import P1Artifact, build_artifact, write_artifact


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
