"""
AEGIS-Health Synthetic Claim Generator
Generates JKN-aligned synthetic claim data for training and testing.
All data is entirely synthetic — no real patient data.

Fraud types covered:
1. upcoding        — inflated severity/cost without clinical justification
2. cloning         — near-identical claim for different patient, same provider
3. repeat_billing  — same claim submitted multiple times
4. phantom_billing — procedures that weren't actually performed
5. prolonged_los   — length of stay far exceeding clinical norm
6. inflated_bill   — cost inflated without changing diagnosis/procedure
7. unbundling      — multiple fragmented claims instead of one package
"""

import random
import copy
from datetime import date, timedelta

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

def generate_random_patient_id():
    return f"PAT-{random.randint(10000, 99999)}"

def generate_random_provider_id():
    return f"FAC-{random.choice(['A', 'B', 'C', 'D', 'E', 'F'])}{random.randint(10, 99)}"

def generate_random_doctor_id(provider_id):
    return f"DR-{provider_id.split('-')[1]}-{random.randint(100, 999)}"

def random_date_in_past(days_back_min=30, days_back_max=365):
    return date.today() - timedelta(days=random.randint(days_back_min, days_back_max))


# ---------------------------------------------------------------------------
# BASE SCENARIOS — 9 JKN-aligned diagnoses
# ---------------------------------------------------------------------------
BASE_SCENARIOS = [
    {
        "primary": "J18.9",   # Pneumonia
        "secondary": [],
        "procs": ["89.52"],
        "meds": [{"name": "Amoxicillin", "qty": 14}],
        "los_range": (3, 5),
        "severity": 1,
        "cost_base": 3_500_000,
    },
    {
        "primary": "I21.9",   # AMI (serangan jantung)
        "secondary": ["I10"],
        "procs": ["36.10", "89.52"],
        "meds": [{"name": "Aspirin", "qty": 30}, {"name": "Clopidogrel", "qty": 30}],
        "los_range": (5, 10),
        "severity": 2,
        "cost_base": 24_000_000,
    },
    {
        "primary": "E11.9",   # Diabetes Mellitus Tipe 2
        "secondary": [],
        "procs": [],
        "meds": [{"name": "Metformin", "qty": 30}],
        "los_range": (1, 3),
        "severity": 1,
        "cost_base": 2_000_000,
    },
    {
        "primary": "K35.8",   # Appendicitis akut
        "secondary": [],
        "procs": ["47.01"],
        "meds": [{"name": "Ceftriaxone", "qty": 5}, {"name": "Ketorolac", "qty": 10}],
        "los_range": (3, 6),
        "severity": 1,
        "cost_base": 7_500_000,
    },
    {
        "primary": "O80",     # Persalinan spontan tunggal
        "secondary": [],
        "procs": [],
        "meds": [{"name": "Oxytocin", "qty": 2}],
        "los_range": (2, 3),
        "severity": 1,
        "cost_base": 1_800_000,
    },
    {
        "primary": "N18.3",   # Chronic Kidney Disease stage 3
        "secondary": ["I10", "E11.9"],
        "procs": [],
        "meds": [{"name": "Erythropoietin", "qty": 4}, {"name": "Bicarbonate", "qty": 10}],
        "los_range": (2, 4),
        "severity": 2,
        "cost_base": 8_500_000,
    },
    {
        "primary": "J44.1",   # COPD exacerbation
        "secondary": [],
        "procs": ["93.94"],   # Nebulisasi
        "meds": [{"name": "Salbutamol", "qty": 10}, {"name": "Ipratropium", "qty": 10}],
        "los_range": (4, 7),
        "severity": 2,
        "cost_base": 4_200_000,
    },
    {
        "primary": "C50.9",   # Breast Cancer
        "secondary": [],
        "procs": ["85.41"],   # Mastektomi
        "meds": [{"name": "Paclitaxel", "qty": 1}, {"name": "Carboplatin", "qty": 1}],
        "los_range": (5, 8),
        "severity": 3,
        "cost_base": 35_000_000,
    },
    {
        "primary": "S72.0",   # Hip Fracture
        "secondary": ["I10"],
        "procs": ["81.51"],   # Total hip replacement
        "meds": [{"name": "Enoxaparin", "qty": 10}, {"name": "Paracetamol", "qty": 20}],
        "los_range": (7, 12),
        "severity": 2,
        "cost_base": 28_000_000,
    },
]


def _build_base_claim(claim_id: str, scenario: dict, admit_date: date = None) -> dict:
    if admit_date is None:
        admit_date = random_date_in_past()
    los = random.randint(*scenario["los_range"])
    discharge_date = admit_date + timedelta(days=los)
    provider_id = generate_random_provider_id()
    return {
        "claim_id": claim_id,
        "patient_id": generate_random_patient_id(),
        "provider_id": provider_id,
        "doctor_id": generate_random_doctor_id(provider_id),
        "diagnosis_primary": scenario["primary"],
        "diagnosis_secondary": list(scenario["secondary"]),
        "procedure_codes": list(scenario["procs"]),
        "medication": [{"name": m["name"], "quantity": m["qty"]} for m in scenario["meds"]],
        "severity_level": scenario["severity"],
        "cost_claimed": round(scenario["cost_base"] * random.uniform(0.9, 1.1)),
        "length_of_stay": los,
        "admission_date": admit_date,
        "discharge_date": discharge_date,
        "is_synthetic_anomaly": False,
        "anomaly_type": "none",
        "evaluation_group_id": f"claim:{claim_id}",
    }


def generate_normal_claim(claim_id: str, scenario: dict = None) -> dict:
    if scenario is None:
        scenario = random.choice(BASE_SCENARIOS)
    return _build_base_claim(claim_id, scenario)


# ---------------------------------------------------------------------------
# FRAUD GENERATORS
# ---------------------------------------------------------------------------

def generate_upcoding_case(claim_id: str) -> dict:
    """Severity and cost inflated; clinical justification is thin."""
    scenario = random.choice(BASE_SCENARIOS)
    claim = _build_base_claim(claim_id, scenario)
    claim["is_synthetic_anomaly"] = True
    claim["anomaly_type"] = "upcoding"
    original_severity = claim["severity_level"]
    claim["severity_level"] = random.choice([3, 4])
    inflation = claim["severity_level"] / max(original_severity, 1)
    claim["cost_claimed"] = round(claim["cost_claimed"] * inflation * random.uniform(1.1, 1.3))
    if "A41.9" not in claim["diagnosis_secondary"]:
        claim["diagnosis_secondary"].append("A41.9")
    return claim


def generate_cloning_case(claim_id1: str, claim_id2: str, fixed_provider_id: str = None) -> tuple:
    """Two near-identical claims, same provider, different patients."""
    scenario = random.choice(BASE_SCENARIOS)
    admit_date = random_date_in_past(7, 60)
    claim1 = _build_base_claim(claim_id1, scenario, admit_date)
    if fixed_provider_id:
        claim1["provider_id"] = fixed_provider_id
        claim1["doctor_id"] = generate_random_doctor_id(fixed_provider_id)

    group_id = f"cloning:{claim_id1}"
    claim1["evaluation_group_id"] = group_id
    claim2 = copy.deepcopy(claim1)
    claim2["claim_id"] = claim_id2
    claim2["patient_id"] = generate_random_patient_id()
    claim2["cost_claimed"] = claim1["cost_claimed"] + random.randint(-5000, 5000)
    claim2["is_synthetic_anomaly"] = True
    claim2["anomaly_type"] = "cloning"
    claim1["is_synthetic_anomaly"] = False
    claim1["anomaly_type"] = "none"
    return claim1, claim2


def generate_repeat_billing_case(claim_id: str, original_claim: dict) -> dict:
    """Same claim submitted again as a separate episode (10-25 days apart)."""
    clone = copy.deepcopy(original_claim)
    clone["claim_id"] = claim_id
    clone["evaluation_group_id"] = original_claim.get("evaluation_group_id", f"claim:{original_claim['claim_id']}")
    shift = timedelta(days=random.randint(10, 25))
    clone["admission_date"] = original_claim["admission_date"] + shift
    # Tanggal keluar ikut digeser agar episode tetap masuk akal (LOS sama) —
    # kalau tidak, keluar lebih awal dari masuk menjadi ditolak validator.
    clone["discharge_date"] = original_claim["discharge_date"] + shift
    clone["is_synthetic_anomaly"] = True
    clone["anomaly_type"] = "repeat_billing"
    return clone


def generate_phantom_billing_case(claim_id: str) -> dict:
    """Procedures billed that were never performed."""
    scenario = next(s for s in BASE_SCENARIOS if s["severity"] == 1)
    claim = _build_base_claim(claim_id, scenario)
    claim["is_synthetic_anomaly"] = True
    claim["anomaly_type"] = "phantom_billing"
    phantom_procs = random.sample(["36.10", "81.51", "85.41", "39.95"], k=2)
    claim["procedure_codes"] = phantom_procs
    claim["cost_claimed"] = round(claim["cost_claimed"] * random.uniform(4.0, 8.0))
    return claim


def generate_prolonged_los_case(claim_id: str) -> dict:
    """Length of stay far beyond clinical norm."""
    scenario = random.choice(BASE_SCENARIOS)
    claim = _build_base_claim(claim_id, scenario)
    claim["is_synthetic_anomaly"] = True
    claim["anomaly_type"] = "prolonged_los"
    normal_los = claim["length_of_stay"]
    claim["length_of_stay"] = round(normal_los * random.uniform(3.0, 5.0))
    claim["discharge_date"] = claim["admission_date"] + timedelta(days=claim["length_of_stay"])
    claim["cost_claimed"] = round(claim["cost_claimed"] * random.uniform(2.5, 4.0))
    return claim


def generate_inflated_bill_case(claim_id: str) -> dict:
    """Cost inflated without changing clinical facts."""
    scenario = random.choice(BASE_SCENARIOS)
    claim = _build_base_claim(claim_id, scenario)
    claim["is_synthetic_anomaly"] = True
    claim["anomaly_type"] = "inflated_bill"
    claim["cost_claimed"] = round(claim["cost_claimed"] * random.uniform(2.0, 3.5))
    return claim


def generate_unbundling_case(claim_id_prefix: str) -> list:
    """One procedure split into multiple partial claims."""
    scenario = random.choice([s for s in BASE_SCENARIOS if len(s["procs"]) >= 1])
    admit_date = random_date_in_past(30, 180)
    provider_id = generate_random_provider_id()
    patient_id = generate_random_patient_id()
    doctor_id = generate_random_doctor_id(provider_id)
    num_fragments = random.randint(2, 3)
    group_id = f"unbundling:{claim_id_prefix}"
    claims = []
    for i in range(num_fragments):
        los_frag = random.randint(1, 3)
        cost_frag = round(scenario["cost_base"] * random.uniform(0.4, 0.6))
        claim = {
            "claim_id": f"{claim_id_prefix}-{i+1}",
            "patient_id": patient_id,
            "provider_id": provider_id,
            "doctor_id": doctor_id,
            "diagnosis_primary": scenario["primary"],
            "diagnosis_secondary": list(scenario["secondary"]),
            "procedure_codes": [random.choice(scenario["procs"])] if scenario["procs"] else [],
            "medication": [{"name": m["name"], "quantity": m["qty"]} for m in scenario["meds"][:1]],
            "severity_level": scenario["severity"],
            "cost_claimed": cost_frag,
            "length_of_stay": los_frag,
            "admission_date": admit_date + timedelta(days=i * los_frag),
            "discharge_date": admit_date + timedelta(days=(i + 1) * los_frag),
            "is_synthetic_anomaly": True,
            "anomaly_type": "unbundling",
            "evaluation_group_id": group_id,
        }
        claims.append(claim)
    return claims


# ---------------------------------------------------------------------------
# DATASET BUILDER
# ---------------------------------------------------------------------------

def generate_dataset(
    num_normal: int = 700,
    num_upcoding: int = 60,
    num_cloning_pairs: int = 30,
    num_repeat_billing: int = 30,
    num_phantom: int = 30,
    num_prolonged_los: int = 25,
    num_inflated: int = 30,
    num_unbundling_groups: int = 15,
    seed: int | None = 42,
    claim_prefix: str = "CLM",
) -> list:
    """
    Generates a complete synthetic JKN dataset.
    Default: ~700 normal + ~300 fraud = ~1000 total.

    `seed` mengontrol reproduksibilitas — dataset training dan held-out test
    HARUS memakai seed berbeda (metodologi anti-tautologi, PRD Section 10).
    `claim_prefix` membedakan ID antar dataset (mis. TRAIN / HOLD).
    """
    if seed is not None:
        random.seed(seed)
    dataset = []

    for i in range(num_normal):
        dataset.append(generate_normal_claim(f"{claim_prefix}-NORM-{i:04d}"))

    for i in range(num_upcoding):
        dataset.append(generate_upcoding_case(f"{claim_prefix}-UPC-{i:04d}"))

    for i in range(num_cloning_pairs):
        c1, c2 = generate_cloning_case(f"{claim_prefix}-CLN-{i:04d}A", f"{claim_prefix}-CLN-{i:04d}B")
        dataset.append(c1)
        dataset.append(c2)

    normal_sample = [d for d in dataset if not d["is_synthetic_anomaly"]]
    for i in range(min(num_repeat_billing, len(normal_sample))):
        dataset.append(generate_repeat_billing_case(f"{claim_prefix}-RPT-{i:04d}", normal_sample[i]))

    for i in range(num_phantom):
        dataset.append(generate_phantom_billing_case(f"{claim_prefix}-PHT-{i:04d}"))

    for i in range(num_prolonged_los):
        dataset.append(generate_prolonged_los_case(f"{claim_prefix}-LOS-{i:04d}"))

    for i in range(num_inflated):
        dataset.append(generate_inflated_bill_case(f"{claim_prefix}-INF-{i:04d}"))

    for i in range(num_unbundling_groups):
        dataset.extend(generate_unbundling_case(f"{claim_prefix}-UNB-{i:04d}"))

    random.shuffle(dataset)
    return dataset
