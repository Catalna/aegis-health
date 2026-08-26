"""Test narasi LLM untuk klaim NORMAL — pastikan tidak over-claim fraud."""
import json
import sys
import threading
import httpx

sys.path.insert(0, ".")

BASE = "http://localhost:8000"

# Klaim normal wajar: pneumonia severity 1, biaya sesuai peer
payload = {
    "claim_id": "CLM-NORM-CHECK",
    "patient_id": "PAT-NORM-99",
    "provider_id": "FAC-B77",
    "doctor_id": "DR-B77-555",
    "diagnosis_primary": "J18.9",
    "diagnosis_secondary": [],
    "procedure_codes": ["89.52"],
    "medication": [{"name": "Amoxicillin", "quantity": 14}],
    "severity_level": 1,
    "cost_claimed": 3500000,
    "length_of_stay": 4,
    "admission_date": "2026-07-01",
    "discharge_date": "2026-07-05",
}

r = httpx.post(f"{BASE}/api/claims", json=payload, timeout=30)
print("create:", r.status_code)

r = httpx.post(f"{BASE}/api/claims/analyze", json=payload, timeout=30)
task_id = r.json()["task_id"]

done = threading.Event()
events = []


def listen():
    with httpx.stream("GET", f"{BASE}/api/stream/{task_id}", timeout=200) as resp:
        ev = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and ev:
                try:
                    data = json.loads(line.split(":", 1)[1].strip())
                except Exception:
                    data = line.split(":", 1)[1].strip()
                events.append((ev, data))
                if ev == "done":
                    done.set()
                    break


t = threading.Thread(target=listen, daemon=True)
t.start()
done.wait(190)

for ev, d in events:
    if ev == "phase3_complete":
        print(f"SKOR: {d['risk']['total_score']} tier={d['risk']['priority_tier']} breakdown={d['risk']['breakdown']}")
    if ev == "phase4_complete":
        expl = d["explanation"]
        print(f"NARASI ({expl['generated_by']}):")
        print(f"  {expl['narrative_id']}")
        print(f"REASONS: {expl['ranked_reasons']}")
        print(f"QA why: {expl['qa_panel']['why_top_priority']}")
        print(f"QA similar: {expl['qa_panel']['most_similar_claim']}")
        print(f"QA fraud: {expl['qa_panel']['is_this_fraud'][:80]}...")
    if ev == "rejected":
        print("REJECTED:", d)
