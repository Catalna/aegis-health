import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.evaluation.pipeline import EvaluationResult
from backend.app.evaluation.runner import P1Artifact, _score_population, build_ablation_delta, build_artifact, write_artifact

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


@pytest.mark.asyncio
async def test_p1_artifact_errors_are_safe(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("SECRET_PERSISTED_EXCEPTION")

    _, errors = await _score_population(fail, [{"claim_id": "P1-SECRET"}], False)

    assert errors == [{"claim_id": "P1-SECRET", "error_code": "analysis_retryable", "error": "Pemeriksaan gagal sementara. Silakan coba lagi."}]
    assert "SECRET_PERSISTED_EXCEPTION" not in json.dumps(errors)


def test_ablation_delta_compares_only_measured_metrics():
    baseline = {
        "average_precision": {"status": "measured", "value": 0.40},
        "precision_at_k": {"50": {"status": "measured", "value": 0.50}},
        "recall_at_k": {"50": {"status": "not_computable", "reason": "small"}},
    }
    candidate = {
        "average_precision": {"status": "measured", "value": 0.55},
        "precision_at_k": {"50": {"status": "measured", "value": 0.60}},
        "recall_at_k": {"50": {"status": "measured", "value": 0.80}},
    }

    delta = build_ablation_delta(baseline, candidate)

    assert delta["average_precision"] == 0.15
    assert delta["precision_at_k"]["50"] == 0.10
    assert delta["recall_at_k"]["50"]["status"] == "not_computable"


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
    assert payload["dataset"]["profile"] == "challenge"
    assert payload["dataset"]["profile_config"]["hard_negative_fraction"] == 0.1
    candidate = next(item for item in payload["ablation"] if item["config_version"] == "behavioral-context-candidate")
    assert "delta_vs_p0_core" in candidate
