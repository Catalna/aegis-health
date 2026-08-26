import asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.models.database import engine, Base, ClaimRecord, AsyncSessionLocal
from backend.app.data.synthetic_generator import generate_dataset
from backend.app.ml.similarity import embed_and_store, get_table

async def seed_postgres_and_lancedb():
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        
    # Generate data — seed berbeda dari training (101/202/303) agar DB demo tidak identik dgn test set
    print("Generating synthetic data...")
    dataset = generate_dataset(num_normal=200, num_upcoding=20, num_cloning_pairs=5, seed=777, claim_prefix="CLM")

    # Store in Postgres
    print("Seeding PostgreSQL...")
    async with AsyncSessionLocal() as session:
        for claim in dataset:
            record = ClaimRecord(
                claim_id=claim["claim_id"],
                patient_id=claim["patient_id"],
                provider_id=claim["provider_id"],
                doctor_id=claim["doctor_id"],
                diagnosis_primary=claim["diagnosis_primary"],
                diagnosis_secondary=",".join(claim["diagnosis_secondary"]),
                procedure_codes=",".join(claim["procedure_codes"]),
                severity_level=claim["severity_level"],
                cost_claimed=claim["cost_claimed"],
                length_of_stay=claim["length_of_stay"],
                admission_date=claim["admission_date"].isoformat() if claim.get("admission_date") else None,
                discharge_date=claim["discharge_date"].isoformat() if claim.get("discharge_date") else None,
                medication_json=json.dumps(claim.get("medication", [])),
                cbg_group_claimed=None # Leave for grouper to process
            )
            session.add(record)
        await session.commit()
    print(f"Stored {len(dataset)} claims in PostgreSQL.")
    
    # Store in LanceDB
    print("Seeding LanceDB (Embeddings)...")
    try:
        table = get_table()
        table.delete("claim_id IS NOT NULL") # Clean existing
    except Exception:
        pass

    n = embed_and_store(dataset)
    print(f"LanceDB seeding complete — {n} vectors.")
    
    # Save the ground truth anomalies to a JSON file for testing/validation
    truth = [c for c in dataset if c.get("is_synthetic_anomaly")]
    with open("ground_truth_anomalies.json", "w") as f:
        # Need to handle date serialization
        def default_serializer(obj):
            from datetime import date
            if isinstance(obj, date):
                return obj.isoformat()
            raise TypeError("Type not serializable")
        json.dump(truth, f, default=default_serializer, indent=2)
    print(f"Saved {len(truth)} anomalous cases to ground_truth_anomalies.json.")

if __name__ == "__main__":
    asyncio.run(seed_postgres_and_lancedb())
