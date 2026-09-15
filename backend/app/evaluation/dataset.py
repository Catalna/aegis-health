"""Reproducible, group-aware synthetic datasets for P1 evaluation."""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
import random

from backend.app.data.synthetic_generator import generate_dataset

CHALLENGE_PROFILE_CONFIG = {
    "hard_negative_fraction": 0.10,
    "soft_positive_fraction": 0.20,
    "hard_negative_cost_multiplier": [1.7, 2.2],
    "soft_positive_cost_multiplier": [0.55, 0.8],
}


@dataclass(frozen=True)
class EvaluationDataset:
    version: str
    seed: int
    claims: list[dict]
    counts: dict[str, int]
    group_ids: set[str]
    profile: str


def _apply_challenge_profile(claims: list[dict], seed: int) -> None:
    """Create realistic ambiguity without changing the adjudicated labels."""
    rng = random.Random(seed + 7919)
    normal_claims = sorted(
        (claim for claim in claims if not claim["is_synthetic_anomaly"]),
        key=lambda claim: claim["claim_id"],
    )
    hard_negative_count = max(1, round(len(normal_claims) * CHALLENGE_PROFILE_CONFIG["hard_negative_fraction"])) if normal_claims else 0
    for claim in normal_claims[:hard_negative_count]:
        low, high = CHALLENGE_PROFILE_CONFIG["hard_negative_cost_multiplier"]
        claim["cost_claimed"] = round(claim["cost_claimed"] * rng.uniform(low, high))
        claim["evaluation_case"] = "hard_negative_cost"

    soft_types = {"upcoding", "phantom_billing", "prolonged_los", "inflated_bill"}
    soft_candidates = sorted(
        (claim for claim in claims if claim["is_synthetic_anomaly"] and claim["anomaly_type"] in soft_types),
        key=lambda claim: claim["claim_id"],
    )
    soft_count = max(1, round(len(soft_candidates) * CHALLENGE_PROFILE_CONFIG["soft_positive_fraction"])) if soft_candidates else 0
    for claim in soft_candidates[:soft_count]:
        low, high = CHALLENGE_PROFILE_CONFIG["soft_positive_cost_multiplier"]
        claim["cost_claimed"] = round(claim["cost_claimed"] * rng.uniform(low, high))
        if claim["anomaly_type"] == "prolonged_los":
            claim["length_of_stay"] = max(1, round(claim["length_of_stay"] * 0.65))
            claim["discharge_date"] = claim["admission_date"] + timedelta(days=claim["length_of_stay"])
        claim["evaluation_case"] = "soft_positive"


def _make_dataset(seed: int, prefix: str, version: str, profile: str, **generator_counts: int) -> EvaluationDataset:
    claims = generate_dataset(seed=seed, claim_prefix=prefix, **generator_counts)
    if profile == "challenge":
        _apply_challenge_profile(claims, seed)
    counts = dict(Counter(claim.get("anomaly_type", "none") for claim in claims))
    group_ids = {claim["evaluation_group_id"] for claim in claims}
    if len(group_ids) != len({claim["claim_id"] for claim in claims}):
        # Shared groups are expected for relational anomalies; missing metadata is not.
        if any(not claim.get("evaluation_group_id") for claim in claims):
            raise ValueError("evaluation dataset contains a claim without group metadata")
    return EvaluationDataset(
        version=version,
        seed=seed,
        claims=claims,
        counts=counts,
        group_ids=group_ids,
        profile=profile,
    )


def validate_group_disjointness(left: set[str], right: set[str]) -> None:
    overlap = sorted(left & right)
    if overlap:
        raise ValueError(f"group leakage detected across evaluation splits: {overlap[:5]}")


def build_evaluation_datasets(
    train_seed: int = 42,
    holdout_seed: int = 2026,
    profile: str = "standard",
    **generator_counts: int,
) -> tuple[EvaluationDataset, EvaluationDataset]:
    if profile not in {"standard", "challenge"}:
        raise ValueError(f"unsupported evaluation profile: {profile}")
    train = _make_dataset(train_seed, "P1-TRAIN", "p1-synthetic-v1", "standard", **generator_counts)
    holdout_version = "p1-synthetic-v1" if profile == "standard" else "p1-synthetic-v1-challenge"
    holdout = _make_dataset(holdout_seed, "P1-HOLDOUT", holdout_version, profile, **generator_counts)
    validate_group_disjointness(train.group_ids, holdout.group_ids)
    return train, holdout
