"""
AEGIS-Health Feature Engineering
Extracts structured numerical features from raw claim dicts.
Used by XGBoost classifier, Isolation Forest, and financial engine.

Feature groups:
  - Clinical    (diagnosis/procedure/severity consistency)
  - Financial   (cost deviation, peer comparison)
  - Fraud/Behavioral (repeat patterns, temporal)
  - Provider    (frequency, cost variance)
"""

from __future__ import annotations
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Diagnosis → integer encoding
# ---------------------------------------------------------------------------
DIAG_MAP: dict[str, int] = {
    "J18": 1, "J44": 2,
    "I21": 3, "I10": 4,
    "E11": 5,
    "K35": 6,
    "O80": 7,
    "N18": 8,
    "C50": 9,
    "S72": 10,
}

# Peer baseline costs per CBG category (based on synthetic scenario baselines)
PEER_BASELINE: dict[str, float] = {
    "J18": 3_500_000,
    "J44": 4_200_000,
    "I21": 24_000_000,
    "I10": 5_000_000,
    "E11": 2_000_000,
    "K35": 7_500_000,
    "O80": 1_800_000,
    "N18": 8_500_000,
    "C50": 35_000_000,
    "S72": 28_000_000,
}

# Expected LOS ranges (days) per diagnosis category
EXPECTED_LOS: dict[str, tuple[int, int]] = {
    "J18": (3, 5), "J44": (4, 7),
    "I21": (5, 10), "I10": (2, 5),
    "E11": (1, 3),
    "K35": (3, 6),
    "O80": (2, 3),
    "N18": (2, 4),
    "C50": (5, 8),
    "S72": (7, 12),
}

# High-cost procedures (numeric flag)
HIGH_COST_PROCS = {"36.10", "81.51", "85.41", "39.95", "72.0"}
# Procedures commonly used in phantom billing
PHANTOM_RISK_PROCS = {"36.10", "81.51", "85.41"}
# Diagnoses commonly exploited in upcoding
UPCODING_RISK_DIAGS = {"A41.9", "Z87.39", "E46"}


def _get_primary_base(claim: dict) -> str:
    primary = claim.get("diagnosis_primary", "")
    return primary.split(".")[0] if "." in primary else primary


def extract_features(claim: dict) -> list[float]:
    """
    Extract a fixed-length numerical feature vector from a claim dict.
    Returns a list of 20 float values.
    
    Feature index map:
      0  primary_diag_encoded
      1  num_secondary_diags
      2  num_procedures
      3  num_medications
      4  severity_level
      5  length_of_stay
      6  cost_claimed (log-scaled)
      7  cost_vs_peer_ratio         (cost / peer_baseline)
      8  los_vs_expected_ratio      (LOS / expected_LOS_max)
      9  has_high_cost_proc         (0/1)
      10 has_phantom_risk_proc      (0/1)
      11 has_upcoding_risk_diag     (0/1)
      12 severity_proc_mismatch     (severity 3+4 but no procedures → 1)
      13 severity_med_mismatch      (severity 3+4 but < 2 medications → 1)
      14 los_outlier                (LOS > 2× expected max → 1)
      15 cost_outlier               (cost > 2× peer baseline → 1)
      16 num_total_codes            (diags + procs combined)
      17 cost_per_los               (cost / LOS)
      18 proc_count_ratio           (procs / (severity * 2))
      19 medication_count           (raw count)
    """
    primary_base = _get_primary_base(claim)
    primary_enc = float(DIAG_MAP.get(primary_base, 0))

    secondary_diags = claim.get("diagnosis_secondary", [])
    procedures = claim.get("procedure_codes", [])
    medications = claim.get("medication", [])
    severity = float(claim.get("severity_level", 1))
    los = float(claim.get("length_of_stay", 1))
    cost = float(claim.get("cost_claimed", 0))

    peer_baseline = float(PEER_BASELINE.get(primary_base, 5_000_000))
    expected_los_range = EXPECTED_LOS.get(primary_base, (2, 7))
    expected_los_max = float(expected_los_range[1])

    # Feature calculations
    cost_log = float(np.log1p(cost))
    cost_peer_ratio = cost / peer_baseline if peer_baseline > 0 else 1.0
    los_expected_ratio = los / expected_los_max if expected_los_max > 0 else 1.0

    has_high_cost_proc = 1.0 if any(p in HIGH_COST_PROCS for p in procedures) else 0.0
    has_phantom_risk_proc = 1.0 if any(p in PHANTOM_RISK_PROCS for p in procedures) else 0.0
    has_upcoding_diag = 1.0 if any(d in UPCODING_RISK_DIAGS for d in secondary_diags) else 0.0

    # Clinical mismatch flags
    is_high_severity = severity >= 3
    severity_proc_mismatch = 1.0 if (is_high_severity and len(procedures) == 0) else 0.0
    severity_med_mismatch = 1.0 if (is_high_severity and len(medications) < 2) else 0.0

    # Outlier flags
    los_outlier = 1.0 if (los > expected_los_max * 2.0) else 0.0
    cost_outlier = 1.0 if (cost > peer_baseline * 2.0) else 0.0

    # Composite features
    num_total_codes = float(1 + len(secondary_diags) + len(procedures))
    cost_per_los = cost / max(los, 1)
    proc_count_ratio = len(procedures) / max(severity * 2, 1)
    med_count = float(len(medications))

    return [
        primary_enc,           # 0
        float(len(secondary_diags)),  # 1
        float(len(procedures)),       # 2
        med_count,             # 3
        severity,              # 4
        los,                   # 5
        cost_log,              # 6
        cost_peer_ratio,       # 7
        los_expected_ratio,    # 8
        has_high_cost_proc,    # 9
        has_phantom_risk_proc, # 10
        has_upcoding_diag,     # 11
        severity_proc_mismatch,# 12
        severity_med_mismatch, # 13
        los_outlier,           # 14
        cost_outlier,          # 15
        num_total_codes,       # 16
        float(np.log1p(cost_per_los)),  # 17
        proc_count_ratio,      # 18
        med_count,             # 19
    ]


FEATURE_NAMES = [
    "primary_diag_encoded",
    "num_secondary_diags",
    "num_procedures",
    "num_medications",
    "severity_level",
    "length_of_stay",
    "cost_claimed_log",
    "cost_vs_peer_ratio",
    "los_vs_expected_ratio",
    "has_high_cost_proc",
    "has_phantom_risk_proc",
    "has_upcoding_risk_diag",
    "severity_proc_mismatch",
    "severity_med_mismatch",
    "los_outlier",
    "cost_outlier",
    "num_total_codes",
    "cost_per_los_log",
    "proc_count_ratio",
    "medication_count",
]

NUM_FEATURES = len(FEATURE_NAMES)

# Features allowed for the expected-cost model. Claimed cost and every value
# derived from it are intentionally excluded to prevent target leakage.
COST_FEATURE_NAMES = [
    "primary_diag_encoded",
    "num_secondary_diags",
    "num_procedures",
    "num_medications",
    "severity_level",
    "length_of_stay",
    "has_high_cost_proc",
    "has_phantom_risk_proc",
    "has_upcoding_risk_diag",
    "severity_proc_mismatch",
    "severity_med_mismatch",
    "los_outlier",
    "num_total_codes",
    "proc_count_ratio",
    "medication_count",
]

_COST_FEATURE_INDICES = [FEATURE_NAMES.index(name) for name in COST_FEATURE_NAMES]


def extract_cost_features(claim: dict) -> list[float]:
    """Return only claim facts available before the submitted cost is judged."""
    features = extract_features(claim)
    return [features[index] for index in _COST_FEATURE_INDICES]
