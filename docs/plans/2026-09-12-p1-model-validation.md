# P1 Model Validation & Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible offline evaluator that measures AEGIS-Health end-to-end risk ranking on held-out synthetic claims without UI, LLM, database, or external-service dependencies.

**Architecture:** Generate independent reference and held-out datasets with explicit relationship groups, adapt claims into deterministic clinical, financial, and in-memory relational assessments, then calculate ranked metrics and versioned JSON artifacts. The evaluator never calls the orchestrator and never writes application database rows.

**Tech Stack:** Python 3.10, Pydantic, NumPy, scikit-learn, pytest, existing AEGIS-Health synthetic generator and model artifacts.

---

## File Map

- Create `backend/app/evaluation/__init__.py`: evaluation package boundary.
- Create `backend/app/evaluation/dataset.py`: reproducible dataset generation, relationship groups, and split validation.
- Create `backend/app/evaluation/pipeline.py`: no-LLM/no-DB assessment adapter and per-claim scoring.
- Create `backend/app/evaluation/metrics.py`: ranking, slice, calibration, latency, and ablation metrics.
- Create `backend/app/evaluation/runner.py`: orchestration, artifact schema, JSON persistence, and exit-level failure handling.
- Create `scripts/evaluate_p1.py`: one-command CLI entry point.
- Modify `backend/app/data/synthetic_generator.py`: preserve source/group metadata for relational anomalies.
- Create `backend/tests/test_p1_dataset.py`: group and split contracts.
- Create `backend/tests/test_p1_pipeline.py`: deterministic adapter and no-LLM contracts.
- Create `backend/tests/test_p1_metrics.py`: metric edge cases and slices.
- Create `backend/tests/test_p1_runner.py`: artifact and reproducibility contracts.

## Contracts

The implementation uses these stable Python shapes across modules:

```python
@dataclass(frozen=True)
class EvaluationDataset:
    version: str
    seed: int
    claims: list[dict]
    counts: dict[str, int]
    group_ids: set[str]

@dataclass(frozen=True)
class EvaluationResult:
    claim_id: str
    label: int
    anomaly_type: str
    score: float
    priority_tier: str
    breakdown: dict[str, float]
    method: str
    latency_ms: float

def build_evaluation_datasets(
    train_seed: int = 42,
    holdout_seed: int = 2026,
    **generator_counts: int,
) -> tuple[EvaluationDataset, EvaluationDataset]: ...
```

Metric functions return JSON-serializable dictionaries. A computable metric has `status: "measured"`; an unavailable metric has `status: "not_computable"` and a non-empty `reason`.

## Task 1: Add Relationship Metadata

**Files:** `backend/app/data/synthetic_generator.py`, `backend/tests/test_p1_dataset.py`

- [x] Write tests requiring every generated claim to have a non-empty `evaluation_group_id`, normal claims to have unique groups, cloning pairs to share a group, repeat billing to share its source group, and unbundling fragments to share a group.
- [x] Run `pytest -q backend/tests/test_p1_dataset.py`; confirm the new metadata assertions fail because the generator has no relationship metadata.
- [x] Add `evaluation_group_id` to base claims and set shared IDs in cloning, repeat billing, and unbundling generators without changing `ClaimInput` fields or anomaly labels.
- [x] Run the focused dataset tests and confirm they pass.

## Task 2: Build Reproducible Dataset Splits

**Files:** `backend/app/evaluation/dataset.py`, `backend/tests/test_p1_dataset.py`

- [x] Write tests for different train/held-out seeds, distinct prefixes, deterministic repeated runs, disjoint group IDs, and class-count metadata.
- [x] Run the focused tests and confirm the missing evaluation module fails collection.
- [x] Implement `EvaluationDataset` and `build_evaluation_datasets()` using generator seeds `42` and `2026`, with explicit `dataset_version`, prefixes, raw claims, group IDs, and counts.
- [x] Implement `validate_group_disjointness()` to raise a descriptive `ValueError` before scoring if any group appears in both splits.
- [x] Run focused dataset tests and confirm they pass.

## Task 3: Create the Deterministic Assessment Adapter

**Files:** `backend/app/evaluation/pipeline.py`, `backend/tests/test_p1_pipeline.py`

- [x] Write tests proving scoring an evaluation claim does not call `structured_completion`, `AsyncSessionLocal`, or LanceDB, and that repeated scoring with the same inputs produces the same score and breakdown.
- [x] Run the focused tests and confirm the adapter is missing.
- [x] Implement deterministic clinical assessment from existing rule helpers and `calculate_expected_tariff`; ambiguous claims must use rule fallback, never clinical LLM fallback.
- [x] Implement financial assessment through the cached model/fallback path and record the selected method.
- [x] Implement an in-memory relation index using `compute_jaccard_similarity`, `cost_proximity`, `composite_similarity`, `is_investigation_candidate`, and `is_unbundling_candidate`; construct `FraudAssessment` without DB or vector-store calls.
- [x] Load Isolation Forest once when available, but keep it as behavioral context and never add it to the P0 score.
- [x] Call `calculate_risk_score()` with a rule-fallback `ReviewSynthesis`; return claim ID, label, anomaly type, risk score, breakdown, methods, and elapsed milliseconds.
- [x] Run focused pipeline tests and confirm they pass.

## Task 4: Implement Ranking Metrics

**Files:** `backend/app/evaluation/metrics.py`, `backend/tests/test_p1_metrics.py`

- [x] Write tests for Precision@K, Recall@K, average precision, `not_computable` when K/anomaly counts are insufficient, and per-anomaly-type slices.
- [x] Run focused metric tests and confirm the module is missing.
- [x] Implement stable score-descending ranking with claim ID tie-breaker, binary labels, explicit K values, and measured/not-computable status objects.
- [x] Implement aggregate and `anomaly_type` slice metrics without treating raw risk score as probability.
- [x] Implement optional reliability bins/Brier score only when a documented probability transform is supplied; otherwise return `not_computable`.
- [x] Implement p50/p95 latency summaries from measured per-claim durations.
- [x] Run focused metric tests and confirm they pass.

## Task 5: Add Ablation and Artifact Runner

**Files:** `backend/app/evaluation/runner.py`, `backend/tests/test_p1_runner.py`

- [x] Write tests for artifact schema metadata, JSON round-trip, deterministic output, and rejection of missing required metadata.
- [x] Run focused runner tests and confirm the module is missing.
- [x] Implement `P1Artifact` serialization containing schema version, dataset metadata, `ANALYSIS_VERSION`, config version, aggregate metrics, slices, latency, ablation results, errors, and limitations.
- [x] Implement baseline/core and candidate behavioral-context configurations using the same held-out ordering; do not mutate production P0 defaults.
- [x] Implement runner failure behavior: group leakage, unwritable artifact, and missing required metadata stop the run; per-claim scoring errors are recorded and excluded from primary metrics.
- [x] Add `run_evaluation()` that writes JSON and prints artifact path plus measured/not-computable statuses.
- [x] Run focused runner tests and confirm they pass.

## Task 6: Add the CLI and Full Verification

**Files:** `scripts/evaluate_p1.py`, all P1 tests

- [x] Write a CLI smoke test that invokes the evaluator with a temporary output path and asserts exit code zero, valid JSON, and no UI/database writes.
- [x] Run the smoke test before implementation and confirm the CLI is missing.
- [x] Implement CLI arguments for output path, train seed, held-out seed, dataset sizes, and `--allow-model-fallback`; default to the approved seeds and a small deterministic smoke size.
- [x] Run the CLI smoke test and confirm the artifact is valid.
- [x] Run `python -m compileall -q backend scripts`.
- [x] Run `pytest -q backend/tests`.
- [x] Run the default P1 evaluator command and inspect the artifact metadata and metric statuses.
- [x] Run `git diff --check` and verify no frontend files changed.
- [x] Commit the P1 implementation in task-scoped commits on `main`.
