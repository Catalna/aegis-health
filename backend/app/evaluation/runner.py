"""Artifact and execution runner for the offline P1 evaluator."""

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable

from backend.app.agents.orchestrator import ANALYSIS_VERSION
from backend.app.evaluation.dataset import build_evaluation_datasets
from backend.app.evaluation.metrics import calibration_metrics, evaluate_ranking, latency_metrics
from backend.app.evaluation.pipeline import EvaluationResult, score_claims


@dataclass(frozen=True)
class P1Artifact:
    schema_version: int
    dataset: dict
    engine: dict
    metrics: dict
    ablation: list[dict]
    errors: list[dict]
    limitations: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def build_artifact(dataset: dict, metrics: dict, ablation: list[dict], errors: list[dict], limitations: list[str]) -> P1Artifact:
    required = {"version", "seed", "counts"}
    if not required.issubset(dataset):
        raise ValueError(f"dataset metadata missing: {sorted(required - set(dataset))}")
    return P1Artifact(
        schema_version=1,
        dataset=dataset,
        engine={
            "analysis_version": ANALYSIS_VERSION,
            "config_version": "p0-default",
            "model_version": {
                "xgboost": "xgboost_regressor.json",
                "isolation_forest": "isolation_forest.pkl",
            },
        },
        metrics=metrics,
        ablation=ablation,
        errors=errors,
        limitations=limitations,
    )


def write_artifact(path: Path, artifact: P1Artifact) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


async def _score_population(scorer, claims: list[dict], include_behavioral_context: bool):
    results: list[EvaluationResult] = []
    errors: list[dict] = []
    for claim in claims:
        try:
            results.extend(await scorer([claim], claims, include_behavioral_context=include_behavioral_context))
        except Exception as exc:
            errors.append({"claim_id": claim.get("claim_id"), "error": str(exc)[:500]})
    return results, errors


def run_evaluation(
    output_path: Path,
    *,
    train_seed: int = 42,
    holdout_seed: int = 2026,
    generator_counts: dict[str, int] | None = None,
    allow_model_fallback: bool = False,
    scorer: Callable[..., Awaitable[list[EvaluationResult]]] = score_claims,
) -> P1Artifact:
    train, holdout = build_evaluation_datasets(train_seed, holdout_seed, **(generator_counts or {}))
    baseline, baseline_errors = asyncio.run(_score_population(scorer, holdout.claims, False))
    candidate, candidate_errors = asyncio.run(_score_population(scorer, holdout.claims, True))
    errors = baseline_errors + candidate_errors
    if errors and len(errors) == len(holdout.claims) * 2:
        raise RuntimeError("all P1 claim scores failed")
    if not allow_model_fallback and any(row.method == "zscore_peer_fallback" for row in baseline + candidate):
        raise RuntimeError("financial model fallback used; rerun with allow_model_fallback=True")

    metrics = evaluate_ranking(baseline)
    metrics["calibration"] = calibration_metrics(baseline)
    metrics["latency"] = latency_metrics([row.latency_ms for row in baseline])
    candidate_metrics = evaluate_ranking(candidate)
    ablation = [
        {"config_version": "p0-core", "metrics": metrics},
        {"config_version": "behavioral-context-candidate", "metrics": candidate_metrics},
    ]
    dataset_meta = {
        "version": holdout.version,
        "seed": holdout.seed,
        "train_seed": train.seed,
        "counts": holdout.counts,
        "train_counts": train.counts,
    }
    artifact = build_artifact(
        dataset=dataset_meta,
        metrics=metrics,
        ablation=ablation,
        errors=errors,
        limitations=["synthetic labels; external domain validation is deferred"],
    )
    write_artifact(output_path, artifact)
    print(f"P1 artifact: {output_path}")
    print(f"Ranking status: {metrics['status']}; latency status: {metrics['latency']['status']}")
    return artifact
