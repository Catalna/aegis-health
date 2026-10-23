"""Hard-fail validation for synthetic-v2 outputs before training/evaluation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


_LABEL_FIELDS = {
    "is_anomaly", "anomaly_type", "difficulty", "scenario_family", "group_id", "label_confidence",
}
_ID_FIELDS = {"claim_id", "patient_id", "provider_id", "doctor_id"}
_SAFE_ID = re.compile(r"^[A-Z][A-Z0-9-]{2,48}$")
_PII_LIKE = re.compile(r"(?:\d{10,}|\b\d{6}-\d{4}-\d{4}\b)")
_NORMAL_FIELDS = ("cost_claimed", "length_of_stay", "patient_age")


def _ks_statistic(left: list[float], right: list[float]) -> tuple[float, float]:
    if not left or not right:
        raise ValueError("normal split distribution check needs normal rows in each split")
    left_sorted, right_sorted = sorted(left), sorted(right)
    points = sorted(set(left_sorted + right_sorted))
    i = j = 0
    distance = 0.0
    for value in points:
        while i < len(left_sorted) and left_sorted[i] <= value:
            i += 1
        while j < len(right_sorted) and right_sorted[j] <= value:
            j += 1
        distance = max(distance, abs(i / len(left_sorted) - j / len(right_sorted)))
    critical = 1.95 * ((len(left_sorted) + len(right_sorted)) / (len(left_sorted) * len(right_sorted))) ** 0.5
    return distance, critical


def validate_synthetic_v2(bundle: dict[str, Any]) -> dict[str, Any]:
    natural_splits = ("train", "validation", "test")
    if any(split not in bundle for split in natural_splits):
        raise ValueError("dataset is missing a required split")
    splits = (*natural_splits, *(split for split in ("test_enriched", "ood") if split in bundle))

    seen_groups: dict[str, str] = {}
    family_sets: dict[str, set[str]] = {}
    counts: dict[str, dict[str, int]] = {}
    normal_rows: dict[str, list[dict[str, Any]]] = {}
    for split in splits:
        data = bundle[split]
        claims = data.get("claims", [])
        labels = data.get("labels", [])
        if len(claims) != len(labels):
            raise ValueError(f"{split} claim/label count mismatch")
        claims_by_id = {claim.get("claim_id"): claim for claim in claims}
        labels_by_id = {label.get("claim_id"): label for label in labels}
        if None in claims_by_id or len(claims_by_id) != len(claims) or claims_by_id.keys() != labels_by_id.keys():
            raise ValueError(f"{split} claim IDs must be unique and align with separate labels")

        type_counts = Counter()
        family_sets[split] = set()
        normal_rows[split] = []
        for claim_id, claim in claims_by_id.items():
            leaked = _LABEL_FIELDS & claim.keys()
            if leaked:
                raise ValueError(f"label leakage in {split} claim input: {sorted(leaked)}")
            for field in _ID_FIELDS:
                value = str(claim.get(field, ""))
                if not _SAFE_ID.fullmatch(value) or _PII_LIKE.search(value):
                    raise ValueError(f"PII-like or invalid synthetic ID in {split}: {field}")
            label = labels_by_id[claim_id]
            if not label.get("group_id") or label.get("difficulty") is None or label.get("scenario_family") is None:
                raise ValueError(f"incomplete ground truth metadata in {split}")
            group = str(label["group_id"])
            if group in seen_groups and seen_groups[group] != split:
                raise ValueError(f"group leakage across {seen_groups[group]} and {split}: {group}")
            seen_groups[group] = split
            family_sets[split].add(str(label["scenario_family"]))
            type_counts[str(label["anomaly_type"])] += 1
            if not label["is_anomaly"] and not str(label["scenario_family"]).startswith("hard_negative_"):
                normal_rows[split].append(claim)
        counts[split] = dict(type_counts)

    train_families = family_sets["train"]
    if not any(family not in train_families for split in ("validation", "test") for family in family_sets[split]
               if not family.startswith("hard_negative_") and not family.endswith("_normal")):
        raise ValueError("validation/test must contain an out-of-family scenario absent from train")

    distribution_checks = {}
    for split in ("validation", "test", "test_enriched", "ood"):
        if split not in family_sets:
            continue
        for field in _NORMAL_FIELDS:
            if split in {"test_enriched", "ood"}:
                continue
            left = [float(row[field]) for row in normal_rows["train"]]
            right = [float(row[field]) for row in normal_rows[split]]
            statistic, critical = _ks_statistic(left, right)
            distribution_checks[f"train_vs_{split}:{field}"] = {
                "ks_statistic": statistic,
                "critical_value_alpha_0_001": critical,
                "passed": statistic <= critical,
            }
            if statistic > critical:
                raise ValueError(
                    f"normal {field} distribution differs significantly between train and {split} "
                    f"(KS={statistic:.4f}, critical={critical:.4f})"
                )
    return {
        "status": "valid",
        "dataset_version": bundle.get("dataset_version", "unknown"),
        "seed": bundle.get("seed"),
        "counts": counts,
        "group_count": len(seen_groups),
        "distribution_checks": distribution_checks,
    }
