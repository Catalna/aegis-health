"""Deterministic, split-aware synthetic claims generator (v2 demonstrator)."""

from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any

import numpy as np


PROFILES = {
    "dev": {
        "claims": {"train": 5_000, "validation": 2_000, "test": 2_000},
        "facilities": 30,
        "doctors": 150,
        "patients": 3_000,
    },
    "standard": {
        "claims": {"train": 150_000, "validation": 50_000, "test": 50_000},
        "facilities": 300,
        "doctors": 2_500,
        "patients": 60_000,
    },
    "large": {
        "claims": {"train": 500_000, "validation": 100_000, "test": 100_000},
        "facilities": 600,
        "doctors": 5_000,
        "patients": 150_000,
    },
}

_ICD_RANGES = (
    ("A", 0, 9), ("B", 15, 19), ("C", 0, 26), ("C", 30, 39),
    ("C", 43, 44), ("C", 50, 58), ("D", 50, 59), ("E", 10, 16),
    ("F", 0, 9), ("G", 0, 9), ("I", 10, 15), ("I", 20, 25),
    ("J", 9, 18), ("J", 40, 47), ("K", 20, 31), ("M", 0, 25),
    ("N", 10, 19), ("S", 0, 9),
)
DIAGNOSIS_CATALOG = tuple(
    f"{letter}{number:02d}"
    for letter, start, stop in _ICD_RANGES
    for number in range(start, stop + 1)
)

_PROCEDURES = ("00.66", "36.10", "39.95", "47.01", "81.51", "85.41", "93.94", "99.04")
_REGIONS = ("sumatra", "java", "kalimantan", "sulawesi", "bali_nusa", "maluku_papua")
_FACILITY_TYPES = ("RS", "KLINIK", "PUSKESMAS")
_FACILITY_CLASSES = ("A", "B", "C", "D")
_ANOMALY_TYPES = (
    "upcoding", "unbundling", "cloning", "repeat_billing", "phantom_billing",
    "inflated_bill", "prolonged_los",
)
_MECHANISMS = {
    "upcoding": ("severity_without_support", "unsupported_secondary_diagnosis", "unsupported_procedure"),
    "unbundling": ("two_fragments", "three_fragments", "four_fragments"),
    "cloning": ("exact_copy", "small_cost_shift", "date_shift_same_facility"),
    "repeat_billing": ("days_1_30", "days_31_45", "days_46_60"),
    "phantom_billing": ("unsupported_procedure", "extra_high_cost_procedure", "procedure_without_diagnosis"),
    "inflated_bill": ("mild_increase", "moderate_increase", "large_increase"),
    "prolonged_los": ("long_stay", "extreme_stay", "date_los_mismatch"),
}
_BASE_RATES = {"A": 2_000_000, "B": 3_000_000, "C": 8_000_000, "D": 4_000_000,
               "E": 3_500_000, "F": 4_500_000, "G": 5_000_000, "I": 12_000_000,
               "J": 5_500_000, "K": 6_500_000, "M": 9_000_000, "N": 7_000_000, "S": 10_000_000}


def _split_month_bounds(split: str) -> tuple[int, int]:
    return {"train": (0, 18), "validation": (18, 21), "test": (21, 24)}[split]


def _balanced_sample(population: int, size: int, rng: np.random.Generator, weights=None) -> np.ndarray:
    probabilities = np.full(population, 1 / population) if weights is None else np.asarray(weights, dtype=float)
    exact = probabilities * size
    counts = np.floor(exact).astype(int)
    remainder = size - int(counts.sum())
    if remainder:
        fractions = exact - counts
        counts[rng.choice(population, size=remainder, replace=False, p=fractions / fractions.sum())] += 1
    values = np.repeat(np.arange(population), counts)
    rng.shuffle(values)
    return values


def _generate_split(profile: str, split: str, count: int, seed: int) -> dict[str, list[dict[str, Any]]]:
    cfg = PROFILES[profile]
    split_seed = seed + {"train": 0, "validation": 1_000_003, "test": 2_000_033}[split]
    rng = np.random.default_rng(split_seed)
    facilities = cfg["facilities"]
    doctors = cfg["doctors"]
    patients = cfg["patients"]
    prefix = {"train": "TRN", "validation": "VAL", "test": "TST"}[split]
    calibration_rng = np.random.default_rng(seed + 8731)

    facility_idx = _balanced_sample(facilities, count, rng)
    patient_idx = rng.integers(0, patients, size=count)
    doctor_home = rng.integers(0, facilities, size=doctors)
    doctor_pool = [np.flatnonzero(doctor_home == idx) for idx in range(facilities)]
    doctor_idx = np.fromiter(
        [int(rng.choice(doctor_pool[fac])) if len(doctor_pool[fac]) else int(rng.integers(doctors))
         for fac in facility_idx], dtype=np.int32, count=count,
    )
    diag_idx = _balanced_sample(len(DIAGNOSIS_CATALOG), count, rng)
    severity_idx = _balanced_sample(4, count, rng, weights=[0.57, 0.29, 0.11, 0.03])
    severity = severity_idx + 1
    los = np.maximum(1, np.rint(rng.lognormal(mean=1.15, sigma=0.55, size=count))).astype(int)
    months_start, months_end = _split_month_bounds(split)
    month = rng.integers(months_start, months_end, size=count)
    date_offset = month * 30 + rng.integers(0, 28, size=count)
    base_date = date(2024, 1, 1)
    regions = calibration_rng.choice(_REGIONS, size=facilities)
    facility_types = calibration_rng.choice(_FACILITY_TYPES, size=facilities, p=[0.68, 0.17, 0.15])
    facility_classes = calibration_rng.choice(_FACILITY_CLASSES, size=facilities)
    region_rate = {region: calibration_rng.uniform(0.9, 1.14) for region in _REGIONS}
    facility_rate = calibration_rng.uniform(0.88, 1.18, size=facilities)
    diagnosis = np.asarray(DIAGNOSIS_CATALOG, dtype=object)[diag_idx]
    base_rate = np.asarray([_BASE_RATES[code[0]] for code in diagnosis], dtype=float)
    severity_factor = np.choose(severity - 1, [0.82, 1.0, 1.27, 1.55])
    regional_factor = np.asarray([region_rate[regions[idx]] for idx in facility_idx])
    claimed = base_rate * severity_factor * regional_factor * facility_rate[facility_idx]
    claimed *= rng.lognormal(mean=0, sigma=0.12, size=count)
    outpatient = rng.random(count) < 0.22
    ina_severity = np.where(outpatient, "0", np.choose(np.minimum(severity, 3) - 1, ["I", "II", "III"]))
    secondary_count = rng.choice([0, 1, 2, 3], size=count, p=[0.44, 0.36, 0.16, 0.04])
    procedure_count = rng.choice([0, 1, 2, 3], size=count, p=[0.38, 0.39, 0.18, 0.05])
    age = np.clip(rng.normal(51, 23, size=count), 0, 100).astype(int)
    sex = rng.choice(("F", "M"), size=count)
    claim_ids = [f"CLM-{prefix}-{idx:07d}" for idx in range(count)]
    admission_dates = [base_date + timedelta(days=int(day)) for day in date_offset]
    discharge_dates = [admit + timedelta(days=int(stay)) for admit, stay in zip(admission_dates, los)]

    claims: list[dict[str, Any]] = []
    for idx in range(count):
        facility = int(facility_idx[idx])
        primary = str(diagnosis[idx])
        sec = rng.choice(DIAGNOSIS_CATALOG, size=int(secondary_count[idx]), replace=False).tolist()
        procs = rng.choice(_PROCEDURES, size=int(procedure_count[idx]), replace=False).tolist()
        special_cost = float(rng.uniform(150_000, 2_500_000)) if rng.random() < 0.12 else 0.0
        raw_cost = float(claimed[idx] + special_cost)
        cbg_class = int(rng.integers(0, 100))
        claims.append({
            "claim_id": claim_ids[idx],
            "patient_id": f"PAT-{prefix}-{int(patient_idx[idx]):07d}",
            "provider_id": f"FAC-{prefix}-{facility:04d}",
            "doctor_id": f"DR-{prefix}-{int(doctor_idx[idx]):05d}",
            "facility_type": str(facility_types[facility]),
            "facility_class": str(facility_classes[facility]),
            "region": str(regions[facility]),
            "patient_age": int(age[idx]),
            "patient_sex": str(sex[idx]),
            "diagnosis_primary": primary,
            "diagnosis_secondary": sec,
            "procedure_codes": procs,
            "length_of_stay": int(los[idx]),
            "severity_level": int(severity[idx]),
            "ina_cbg_code": f"SIM-{primary[0]}-{cbg_class:02d}",
            "ina_cbg_severity": str(ina_severity[idx]),
            "outpatient": bool(outpatient[idx]),
            "regional_base_rate": round(float(base_rate[idx] * region_rate[str(regions[facility])]), 2),
            "cost_claimed": round(raw_cost, 2),
            "special_group_cost": round(special_cost, 2),
            "admission_date": admission_dates[idx].isoformat(),
            "discharge_date": discharge_dates[idx].isoformat(),
        })

    labels = [{
        "claim_id": claim_ids[idx],
        "is_anomaly": False,
        "anomaly_type": "none",
        "difficulty": "none",
        "scenario_family": "natural_normal",
        "group_id": f"{prefix}-GROUP-{idx:07d}",
        "label_confidence": 1.0,
    } for idx in range(count)]

    # 3% natural prevalence, with relational families represented as grouped cases.
    positive_count = max(1, round(count * 0.03)) if count else 0
    positive_idxs = rng.choice(count, size=min(positive_count, count), replace=False) if count else []
    positive_idx_set = set(int(idx) for idx in positive_idxs)
    normal_candidates = [idx for idx in range(count) if idx not in positive_idx_set]
    available_related_sources = normal_candidates.copy()
    related_source_idxs: set[int] = set()
    unbundling_templates: dict[int, dict[str, Any]] = {}
    for ordinal, idx in enumerate(positive_idxs):
        anomaly_type = _ANOMALY_TYPES[ordinal % len(_ANOMALY_TYPES)]
        mechanisms = _MECHANISMS[anomaly_type]
        # Validation/test contain a mechanism deliberately absent from train.
        mechanism_idx = 0 if split == "train" else 1 + ((ordinal + split_seed) % (len(mechanisms) - 1))
        mechanism = mechanisms[mechanism_idx]
        claim = claims[int(idx)]
        label = labels[int(idx)]
        label.update({
            "is_anomaly": True,
            "anomaly_type": anomaly_type,
            "difficulty": ("easy", "medium", "hard")[ordinal % 3],
            "scenario_family": f"{anomaly_type}:{mechanism}",
            "group_id": f"{prefix}-ANOMALY-GROUP-{ordinal:07d}",
            "label_confidence": 0.9,
        })
        if anomaly_type == "upcoding":
            claim["severity_level"] = min(4, claim["severity_level"] + 1)
            if mechanism == "unsupported_secondary_diagnosis":
                claim["diagnosis_secondary"].append("E46")
        elif anomaly_type == "unbundling":
            occurrence = ordinal // len(_ANOMALY_TYPES)
            group_number = occurrence // 3
            fragment_number = occurrence % 3
            group_id = f"{prefix}-UNBUNDLING-{group_number:05d}"
            template = unbundling_templates.get(group_number)
            if template is None:
                template = {
                    key: claim[key]
                    for key in ("patient_id", "provider_id", "doctor_id", "diagnosis_primary", "diagnosis_secondary", "procedure_codes")
                }
                unbundling_templates[group_number] = template
            else:
                claim.update(template)
            claim["cost_claimed"] = round(float(claim["regional_base_rate"]) * float(rng.uniform(0.3, 0.5)), 2)
            claim["admission_date"] = (
                date.fromisoformat(claim["admission_date"]) + timedelta(days=fragment_number)
            ).isoformat()
            claim["discharge_date"] = (
                date.fromisoformat(claim["admission_date"]) + timedelta(days=claim["length_of_stay"])
            ).isoformat()
            label["group_id"] = group_id
        elif anomaly_type == "cloning":
            source_idx = available_related_sources.pop(0) if available_related_sources else None
            if source_idx is not None:
                related_source_idxs.add(source_idx)
                source = claims[source_idx]
                claim.update({
                    key: copy.deepcopy(value)
                    for key, value in source.items()
                    if key not in {"claim_id", "patient_id"}
                })
                claim["patient_id"] = f"PAT-{prefix}-CLONE-{ordinal:07d}"
                label["group_id"] = f"{prefix}-CLONING-{min(idx, source_idx):07d}"
                labels[source_idx]["group_id"] = label["group_id"]
                if mechanism == "small_cost_shift":
                    claim["cost_claimed"] = round(claim["cost_claimed"] * float(rng.uniform(0.97, 1.03)), 2)
                elif mechanism == "date_shift_same_facility":
                    shifted_admission = date.fromisoformat(claim["admission_date"]) + timedelta(days=int(rng.integers(1, 4)))
                    claim["admission_date"] = shifted_admission.isoformat()
                    claim["discharge_date"] = (shifted_admission + timedelta(days=claim["length_of_stay"])).isoformat()
        elif anomaly_type == "repeat_billing":
            source_idx = available_related_sources.pop(0) if available_related_sources else None
            if source_idx is not None:
                related_source_idxs.add(source_idx)
                source = claims[source_idx]
                claim.update({key: source[key] for key in (
                    "patient_id", "provider_id", "doctor_id", "diagnosis_primary", "diagnosis_secondary",
                    "procedure_codes", "length_of_stay", "severity_level", "cost_claimed",
                )})
                gap = (ordinal % 60) + 1
                new_admit = date.fromisoformat(source["admission_date"]) + timedelta(days=gap)
                claim["admission_date"] = new_admit.isoformat()
                claim["discharge_date"] = (new_admit + timedelta(days=source["length_of_stay"])).isoformat()
                label["group_id"] = f"{prefix}-REPEAT-{min(idx, source_idx):07d}"
                labels[source_idx]["group_id"] = label["group_id"]
        elif anomaly_type == "phantom_billing":
            claim["procedure_codes"] = list(dict.fromkeys([*claim["procedure_codes"], "81.51"]))
            claim["cost_claimed"] = round(claim["cost_claimed"] * 1.35, 2)
        elif anomaly_type == "inflated_bill":
            claim["cost_claimed"] = round(claim["cost_claimed"] * float(rng.uniform(1.25, 2.5)), 2)
        elif anomaly_type == "prolonged_los":
            claim["length_of_stay"] = max(2, claim["length_of_stay"] * (2 + ordinal % 3))
            claim["discharge_date"] = (
                date.fromisoformat(claim["admission_date"]) + timedelta(days=claim["length_of_stay"])
            ).isoformat()

    # Legitimate hard negatives remain normal by ground truth and are represented only in labels.
    hard_negative_count = max(1, round(count * 0.05)) if count else 0
    hard_negative_candidates = [idx for idx in normal_candidates if idx not in related_source_idxs]
    for idx in rng.choice(hard_negative_candidates, size=min(hard_negative_count, len(hard_negative_candidates)), replace=False):
        label = labels[int(idx)]
        hard_case = ("readmission", "chronic_repeat_visit", "catastrophic_cost", "long_los", "standardized_protocol")[int(rng.integers(5))]
        label["scenario_family"] = f"hard_negative_{hard_case}"
        label["group_id"] = f"{prefix}-HARDNEG-{int(idx):07d}"
        label["label_confidence"] = 0.95

    return {"claims": claims, "labels": labels}


def generate_synthetic_v2(profile: str = "standard", seed: int = 42) -> dict[str, Any]:
    """Return independent time-window splits. Labels are stored outside claim rows."""
    if profile not in PROFILES:
        raise ValueError(f"unsupported synthetic-v2 profile: {profile}")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    splits = {
        split: _generate_split(profile, split, count, seed)
        for split, count in PROFILES[profile]["claims"].items()
    }
    return {
        "dataset_version": "synthetic-v2-demonstrator",
        "seed": seed,
        "profile": profile,
        **splits,
    }
