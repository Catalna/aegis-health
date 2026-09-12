"""Reproducible, group-aware synthetic datasets for P1 evaluation."""

from collections import Counter
from dataclasses import dataclass

from backend.app.data.synthetic_generator import generate_dataset


@dataclass(frozen=True)
class EvaluationDataset:
    version: str
    seed: int
    claims: list[dict]
    counts: dict[str, int]
    group_ids: set[str]


def _make_dataset(seed: int, prefix: str, version: str, **generator_counts: int) -> EvaluationDataset:
    claims = generate_dataset(seed=seed, claim_prefix=prefix, **generator_counts)
    counts = dict(Counter(claim.get("anomaly_type", "none") for claim in claims))
    group_ids = {claim["evaluation_group_id"] for claim in claims}
    if len(group_ids) != len({claim["claim_id"] for claim in claims}):
        # Shared groups are expected for relational anomalies; missing metadata is not.
        if any(not claim.get("evaluation_group_id") for claim in claims):
            raise ValueError("evaluation dataset contains a claim without group metadata")
    return EvaluationDataset(version=version, seed=seed, claims=claims, counts=counts, group_ids=group_ids)


def validate_group_disjointness(left: set[str], right: set[str]) -> None:
    overlap = sorted(left & right)
    if overlap:
        raise ValueError(f"group leakage detected across evaluation splits: {overlap[:5]}")


def build_evaluation_datasets(
    train_seed: int = 42,
    holdout_seed: int = 2026,
    **generator_counts: int,
) -> tuple[EvaluationDataset, EvaluationDataset]:
    train = _make_dataset(train_seed, "P1-TRAIN", "p1-synthetic-v1", **generator_counts)
    holdout = _make_dataset(holdout_seed, "P1-HOLDOUT", "p1-synthetic-v1", **generator_counts)
    validate_group_disjointness(train.group_ids, holdout.group_ids)
    return train, holdout
