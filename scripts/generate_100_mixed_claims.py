"""
Generate 100 diverse and mixed JKN synthetic claims with direct DB insertion.
Includes normal controls, single anomalies, and compound/mixed anomalies:
- Normal controls (39 claims)
- Upcoding (12 claims)
- Repeat Billing (12 claims)
- Cloning (12 claims / 6 pairs)
- Phantom Billing (8 claims)
- Prolonged LOS (6 claims)
- Inflated Bill (6 claims)
- Compound: Repeat + Upcoding (2 claims)
- Compound: Prolonged LOS + Inflated Bill (1 claim)
- Compound: Cloning + Upcoding (1 pair = 2 claims)
Total = 100 claims.
"""

import asyncio
import copy
import json
import os
import random
import sys
from datetime import date, timedelta
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from backend.app.models.database import AsyncSessionLocal, ClaimRecord
from backend.app.ml.similarity import embed_and_store, db, TABLE_NAME
from backend.app.ml.graph_metrics import refresh_sync_safe
from backend.app.data.synthetic_generator import (
    BASE_SCENARIOS,
    _build_base_claim,
    generate_normal_claim,
    generate_upcoding_case,
    generate_cloning_case,
    generate_repeat_billing_case,
    generate_phantom_billing_case,
    generate_prolonged_los_case,
    generate_inflated_bill_case,
    generate_random_patient_id,
    generate_random_provider_id,
    generate_random_doctor_id,
    random_date_in_past,
)


def generate_repeat_and_upcoding_case(claim_id: str, original_claim: dict) -> dict:
    """Compound anomaly: Repeat billing on same patient PLUS upcoding."""
    clone = copy.deepcopy(original_claim)
    clone["claim_id"] = claim_id
    clone["evaluation_group_id"] = original_claim.get("evaluation_group_id", f"claim:{original_claim['claim_id']}")
    clone["admission_date"] = original_claim["admission_date"] + timedelta(days=random.randint(5, 20))
    clone["discharge_date"] = clone["admission_date"] + timedelta(days=clone["length_of_stay"])
    clone["severity_level"] = min(4, clone["severity_level"] + 2)
    clone["cost_claimed"] = round(clone["cost_claimed"] * random.uniform(2.2, 3.0))
    if "A41.9" not in clone["diagnosis_secondary"]:
        clone["diagnosis_secondary"].append("A41.9")
    clone["is_synthetic_anomaly"] = True
    clone["anomaly_type"] = "repeat_and_upcoding"
    return clone


def generate_los_and_inflated_case(claim_id: str) -> dict:
    """Compound anomaly: Prolonged length of stay PLUS heavily inflated bill."""
    scenario = random.choice(BASE_SCENARIOS)
    claim = _build_base_claim(claim_id, scenario)
    claim["is_synthetic_anomaly"] = True
    claim["anomaly_type"] = "prolonged_los_and_inflated"
    claim["length_of_stay"] = round(claim["length_of_stay"] * random.uniform(3.5, 5.0))
    claim["discharge_date"] = claim["admission_date"] + timedelta(days=claim["length_of_stay"])
    claim["cost_claimed"] = round(claim["cost_claimed"] * random.uniform(3.5, 5.0))
    return claim


def generate_cloning_and_upcoding_case(claim_id1: str, claim_id2: str) -> tuple[dict, dict]:
    """Compound anomaly: Cloning across patients in same provider PLUS inflated severity."""
    c1, c2 = generate_cloning_case(claim_id1, claim_id2)
    c2["severity_level"] = 3
    c2["cost_claimed"] = round(c2["cost_claimed"] * 1.8)
    if "Z87.39" not in c2["diagnosis_secondary"]:
        c2["diagnosis_secondary"].append("Z87.39")
    c2["anomaly_type"] = "cloning_and_upcoding"
    return c1, c2


def build_100_claims(prefix: str = "CLM") -> list[dict[str, Any]]:
    random.seed(20261003)
    claims: list[dict[str, Any]] = []

    # 1. Normal claims (39 claims)
    normal_claims = [generate_normal_claim(f"{prefix}-NORM-{i:02d}") for i in range(1, 40)]
    ref_claims = normal_claims[:15]
    claims.extend(normal_claims)

    # 2. Upcoding (12 claims)
    for i in range(1, 13):
        claims.append(generate_upcoding_case(f"{prefix}-UPCODE-{i:02d}"))

    # 3. Repeat Billing (12 claims linked to reference claims). Referensi wajib
    # memiliki procedure codes: aturan repeat billing didasarkan pada overlap
    # prosedur, sehingga klaim tanpa prosedur berada di luar cakupan aturan.
    repeat_refs = [c for c in ref_claims if c.get("procedure_codes")]
    for i in range(1, 13):
        claims.append(generate_repeat_billing_case(
            f"{prefix}-REPEAT-{i:02d}", repeat_refs[(i - 1) % len(repeat_refs)]
        ))

    # 4. Cloning (12 claims = 6 pairs)
    for i in range(1, 7):
        c1, c2 = generate_cloning_case(f"{prefix}-CLONE-{i:02d}-A", f"{prefix}-CLONE-{i:02d}-B")
        claims.extend([c1, c2])

    # 5. Phantom Billing (8 claims)
    for i in range(1, 9):
        claims.append(generate_phantom_billing_case(f"{prefix}-PHANTOM-{i:02d}"))

    # 6. Prolonged LOS (6 claims)
    for i in range(1, 7):
        claims.append(generate_prolonged_los_case(f"{prefix}-LOS-{i:02d}"))

    # 7. Inflated Bill (6 claims)
    for i in range(1, 7):
        claims.append(generate_inflated_bill_case(f"{prefix}-INFLATED-{i:02d}"))

    # 8. Compound / Mixed Anomalies (5 claims)
    # 8a. Repeat + Upcoding (2 claims) — referensi juga harus punya prosedur
    claims.append(generate_repeat_and_upcoding_case(f"{prefix}-MIX-RPT-UPC-01", repeat_refs[-2]))
    claims.append(generate_repeat_and_upcoding_case(f"{prefix}-MIX-RPT-UPC-02", repeat_refs[-1]))

    # 8b. LOS + Inflated (1 claim)
    claims.append(generate_los_and_inflated_case(f"{prefix}-MIX-LOS-INF-01"))

    # 8c. Cloning + Upcoding (1 pair = 2 claims)
    c1, c2 = generate_cloning_and_upcoding_case(f"{prefix}-MIX-CLN-01-A", f"{prefix}-MIX-CLN-01-B")
    claims.extend([c1, c2])

    print(f"Total claims generated: {len(claims)}")
    return claims


async def reset_and_populate():
    print("1. Resetting PostgreSQL database tables...")
    async with AsyncSessionLocal() as session:
        await session.execute(text("TRUNCATE TABLE human_decisions, risk_analyses, claims, agent_runs, audit_logs RESTART IDENTITY CASCADE;"))
        await session.commit()
    print("   -> PostgreSQL truncated successfully.")

    # Reset LanceDB table
    try:
        if db is not None:
            tables = db.table_names() if hasattr(db, "table_names") else db.list_tables()
            if TABLE_NAME in tables:
                print(f"2. Dropping LanceDB table '{TABLE_NAME}'...")
                db.drop_table(TABLE_NAME)
                print("   -> LanceDB table dropped.")
    except Exception as e:
        print(f"   -> LanceDB reset notice: {e}")

    # Build 100 claims
    claims_data = build_100_claims(prefix="CLM")

    # Insert into PostgreSQL
    print("3. Inserting 100 claims into PostgreSQL database...")
    async with AsyncSessionLocal() as session:
        records = []
        for c in claims_data:
            rec = ClaimRecord(
                claim_id=c["claim_id"],
                patient_id=c["patient_id"],
                provider_id=c["provider_id"],
                doctor_id=c["doctor_id"],
                diagnosis_primary=c["diagnosis_primary"],
                diagnosis_secondary=",".join(c["diagnosis_secondary"]) if c.get("diagnosis_secondary") else "",
                procedure_codes=",".join(c["procedure_codes"]) if c.get("procedure_codes") else "",
                severity_level=c["severity_level"],
                cost_claimed=float(c["cost_claimed"]),
                length_of_stay=int(c["length_of_stay"]),
                admission_date=c["admission_date"].isoformat() if hasattr(c["admission_date"], "isoformat") else str(c["admission_date"]),
                discharge_date=c["discharge_date"].isoformat() if hasattr(c["discharge_date"], "isoformat") else str(c["discharge_date"]),
                medication_json=json.dumps(c.get("medication", [])),
                referral_json=None,
                status="pending",
            )
            records.append(rec)
        session.add_all(records)
        await session.commit()
    print("   -> All 100 ClaimRecords inserted with status='pending'.")

    # Index into LanceDB
    print("4. Indexing claims into LanceDB vector store...")
    indexed_count = embed_and_store(claims_data)
    print(f"   -> LanceDB indexed: {indexed_count} vectors.")

    # Refresh graph metrics
    print("5. Refreshing provider graph metrics...")
    refresh_sync_safe()
    print("   -> Graph metrics refreshed.")

    print("\n[SELESAI] Database berhasil di-reset dan 100 klaim baru siap diperiksa!")


if __name__ == "__main__":
    asyncio.run(reset_and_populate())
