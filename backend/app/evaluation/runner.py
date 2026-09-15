"""Artifact and execution runner for the offline P1 evaluator."""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable

from backend.app.core.versions import ANALYSIS_VERSION
from backend.app.evaluation.dataset import CHALLENGE_PROFILE_CONFIG, build_evaluation_datasets
from backend.app.evaluation.metrics import calibration_metrics, evaluate_ranking, latency_metrics
from backend.app.evaluation.pipeline import EvaluationResult, score_claims
from backend.app.core.errors import failure_for_exception

logger = logging.getLogger(__name__)


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


def build_ablation_delta(baseline: dict, candidate: dict) -> dict:
    delta = {}
    baseline_ap = baseline.get("average_precision", {})
    candidate_ap = candidate.get("average_precision", {})
    if baseline_ap.get("status") == candidate_ap.get("status") == "measured":
        delta["average_precision"] = round(candidate_ap["value"] - baseline_ap["value"], 6)
    else:
        delta["average_precision"] = {"status": "not_computable", "reason": "one or both AP values are unavailable"}
    for metric_name in ("precision_at_k", "recall_at_k"):
        metric_delta = {}
        keys = set(baseline.get(metric_name, {})) | set(candidate.get(metric_name, {}))
        for key in sorted(keys, key=int):
            base_value = baseline.get(metric_name, {}).get(key, {})
            candidate_value = candidate.get(metric_name, {}).get(key, {})
            if base_value.get("status") == candidate_value.get("status") == "measured":
                metric_delta[key] = round(candidate_value["value"] - base_value["value"], 6)
            else:
                metric_delta[key] = {"status": "not_computable", "reason": "one or both values are unavailable"}
        delta[metric_name] = metric_delta
    return delta


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
            logger.exception("P1 scoring failed for claim_id=%s", claim.get("claim_id"))
            failure = failure_for_exception(exc)
            errors.append({
                "claim_id": claim.get("claim_id"),
                "error_code": failure.code,
                "error": failure.message,
            })
    return results, errors


def run_evaluation(
    output_path: Path,
    *,
    train_seed: int = 42,
    holdout_seed: int = 2026,
    profile: str = "challenge",
    generator_counts: dict[str, int] | None = None,
    allow_model_fallback: bool = False,
    scorer: Callable[..., Awaitable[list[EvaluationResult]]] = score_claims,
) -> P1Artifact:
    train, holdout = build_evaluation_datasets(
        train_seed,
        holdout_seed,
        profile=profile,
        **(generator_counts or {}),
    )
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
        {
            "config_version": "behavioral-context-candidate",
            "metrics": candidate_metrics,
            "delta_vs_p0_core": build_ablation_delta(metrics, candidate_metrics),
        },
    ]
    dataset_meta = {
        "version": holdout.version,
        "seed": holdout.seed,
        "train_seed": train.seed,
        "profile": holdout.profile,
        "profile_config": CHALLENGE_PROFILE_CONFIG if holdout.profile == "challenge" else {},
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
