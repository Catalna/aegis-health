"""Classifier feature engineering for the synthetic v2 evaluation candidate.

The supervised classifier is an evaluation candidate only; it never enters the
deterministic runtime risk score. Two feature families are provided:

1. Per-claim features (the original 17): raw row content plus two flags.
2. Split-level relational features: duplicate-group sizes, the minimum gap to
   another claim of the same patient, and a train-only expected-LOS benchmark.
   Relational counts are computed inside the current split only, which mirrors
   how a payer reviews one processing batch; no claim data crosses the
   train/validation/test boundary, and the expected-LOS map is fitted on train
   normals alone.

The two "unsupported" service flags key on reference codes (E46 secondary
diagnosis, procedure 81.51). A real payer keeps such support tables; here the
generator flags unfounded patterns with these codes, so carrying them as
features is domain knowledge, not label leakage.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date
from typing import Any

import numpy as np

from backend.app.data.synthetic_v2.generator import DIAGNOSIS_CATALOG

_RATIO_BUCKET = 0.05
_NO_PAIR_SENTINEL = 10_000.0

_FACILITY = {value: index for index, value in enumerate(("RS", "KLINIK", "PUSKESMAS"))}
_CLASS = {value: index for index, value in enumerate(("A", "B", "C", "D"))}
_REGION = {
    value: index
    for index, value in enumerate(
        ("sumatra", "java", "kalimantan", "sulawesi", "bali_nusa", "maluku_papua")
    )
}
_DIAGNOSIS = {value: index for index, value in enumerate(DIAGNOSIS_CATALOG)}

CLASSIFIER_FEATURE_NAMES = [
    "primary_diag_encoded", "num_secondary_diags", "num_procedures", "patient_age",
    "num_medications", "length_of_stay", "outpatient", "icu_indicator", "ventilator_used",
    "surgical_indicator", "facility_type", "facility_class", "region",
    "severity_level", "ina_cbg_base_rate",
    "cost_claimed_log", "cost_vs_base_rate", "long_los_flag", "unsupported_severity_flag",
    "copy_group_size", "exact_copy_group_size", "min_same_patient_gap_days",
    "los_vs_expected", "unsupported_secondary_E46_flag", "unsupported_procedure_8151_flag",
]


def build_cost_features(
    claims: list[dict[str, Any]], *, include_severity: bool = True, include_base_rate: bool = True
) -> tuple[np.ndarray, list[str]]:
    """Cost-regression inputs without claimed cost or any derived target feature."""
    names = [
        "primary_diag_encoded", "num_secondary_diags", "num_procedures", "patient_age",
        "num_medications", "length_of_stay", "outpatient", "icu_indicator", "ventilator_used",
        "surgical_indicator", "facility_type", "facility_class", "region",
    ]
    if include_severity:
        names.append("severity_level")
    if include_base_rate:
        names.append("ina_cbg_base_rate")
    matrix = []
    for claim in claims:
        row = [
            float(_DIAGNOSIS.get(claim["diagnosis_primary"], 0)),
            float(len(claim.get("diagnosis_secondary", []))),
            float(len(claim.get("procedure_codes", []))),
            float(claim.get("patient_age", 0)),
            float(len(claim.get("medication_codes", []))),
            float(claim.get("length_of_stay", 0)),
            float(bool(claim.get("outpatient", False))),
            float(bool(claim.get("icu_indicator", False))),
            float(bool(claim.get("ventilator_used", False))),
            float(bool(claim.get("surgical_indicator", False))),
            float(_FACILITY.get(claim.get("facility_type"), -1)),
            float(_CLASS.get(claim.get("facility_class"), -1)),
            float(_REGION.get(claim.get("region"), -1)),
        ]
        if include_severity:
            row.append(float(claim.get("severity_level", 1)))
        if include_base_rate:
            row.append(float(claim.get("regional_base_rate", 0)))
        matrix.append(row)
    return np.asarray(matrix, dtype=np.float32), names


def build_training_context(train_claims: list[dict[str, Any]], train_y: np.ndarray) -> dict[str, Any]:
    """Fit evaluation context on normal train rows only (no validation/test data)."""
    stays: dict[tuple[str, bool], list[int]] = defaultdict(list)
    for claim, label in zip(train_claims, train_y):
        if int(label) == 0:
            stays[(str(claim["diagnosis_primary"]), bool(claim.get("outpatient")))].append(
                int(claim["length_of_stay"])
            )
    expected_los = {
        key: max(1.0, float(np.median(values))) for key, values in stays.items() if values
    }
    return {"expected_los": expected_los}


def _codes_key(claim: dict[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    return (
        str(claim["diagnosis_primary"]),
        tuple(sorted(str(code) for code in claim.get("diagnosis_secondary", []))),
        tuple(sorted(str(code) for code in claim.get("procedure_codes", []))),
    )


def _ratio_bucket(claim: dict[str, Any]) -> int:
    ratio = float(claim.get("cost_claimed", 0.0)) / max(1.0, float(claim.get("regional_base_rate", 1.0)))
    return round(ratio / _RATIO_BUCKET)


def _min_same_patient_gaps(claims: list[dict[str, Any]]) -> np.ndarray:
    visits: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for index, claim in enumerate(claims):
        visits[str(claim["patient_id"])].append((str(claim["admission_date"]), index))
    gaps = np.full(len(claims), _NO_PAIR_SENTINEL, dtype=np.float32)
    for entries in visits.values():
        if len(entries) < 2:
            continue
        entries.sort()
        for position in range(len(entries) - 1):
            left_date, _ = entries[position]
            right_date, _ = entries[position + 1]
            gap = float(abs((date.fromisoformat(right_date) - date.fromisoformat(left_date)).days))
            for _, index in (entries[position], entries[position + 1]):
                gaps[index] = min(gaps[index], gap)
    return gaps


def _relational_columns(claims: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """Duplicate-group sizes within the split only."""
    copy_groups: Counter[tuple] = Counter()
    exact_groups: Counter[tuple] = Counter()
    for claim in claims:
        codes = _codes_key(claim)
        copy_groups[(str(claim["provider_id"]), *codes, _ratio_bucket(claim))] += 1
        exact_groups[(str(claim["provider_id"]), str(claim["admission_date"]), *codes)] += 1
    copy_counts = np.empty(len(claims), dtype=np.float32)
    exact_counts = np.empty(len(claims), dtype=np.float32)
    for index, claim in enumerate(claims):
        codes = _codes_key(claim)
        copy_counts[index] = copy_groups[(str(claim["provider_id"]), *codes, _ratio_bucket(claim))]
        exact_counts[index] = exact_groups[(str(claim["provider_id"]), str(claim["admission_date"]), *codes)]
    return copy_counts, exact_counts


def build_classifier_features(
    claims: list[dict[str, Any]], *, context: dict[str, Any]
) -> tuple[np.ndarray, list[str]]:
    """Full classifier matrix: per-claim plus split-level relational features."""
    if context is None:
        raise ValueError("classifier features require a train-fitted context")
    base, _ = build_cost_features(claims)
    expected_los: dict[tuple[str, bool], float] = context["expected_los"]
    copy_counts, exact_counts = _relational_columns(claims)
    patient_gaps = _min_same_patient_gaps(claims)
    extras = np.asarray(
        [
            [
                math.log1p(max(0.0, float(claim.get("cost_claimed", 0)))),
                float(claim.get("cost_claimed", 0)) / max(1.0, float(claim.get("regional_base_rate", 0))),
                float(float(claim.get("length_of_stay", 0)) > 14),
                float(float(claim.get("severity_level", 1)) >= 3 and not claim.get("procedure_codes")),
            ]
            for claim in claims
        ],
        dtype=np.float32,
    )
    relational = np.asarray(
        [
            [
                copy_counts[index],
                exact_counts[index],
                patient_gaps[index],
                float(claim.get("length_of_stay", 0))
                / expected_los.get((str(claim["diagnosis_primary"]), bool(claim.get("outpatient"))), 1.0),
                float("E46" in (claim.get("diagnosis_secondary") or [])),
                float("81.51" in (claim.get("procedure_codes") or [])),
            ]
            for index, claim in enumerate(claims)
        ],
        dtype=np.float32,
    )
    matrix = np.column_stack((base, extras, relational))
    return matrix, CLASSIFIER_FEATURE_NAMES
