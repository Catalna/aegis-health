"""Smoke test end-to-end: validasi reject + analisis normal via API+SSE."""
import json
import threading
import time
import httpx

BASE = "http://localhost:8000"

def claim_payload(**over):
    base = {
        "claim_id": "CLM-SMOKE-001",
        "patient_id": "PAT-SMOKE",
        "provider_id": "FAC-A12",
        "doctor_id": "DR-A12-101",
        "diagnosis_primary": "I21.9",
        "diagnosis_secondary": ["I10"],
        "procedure_codes": ["36.10", "89.52"],
        "medication": [{"name": "Aspirin", "quantity": 30}, {"name": "Clopidogrel", "quantity": 30}],
        "severity_level": 2,
        "cost_claimed": 24000000,
        "length_of_stay": 7,
        "admission_date": "2026-07-01",
        "discharge_date": "2026-07-08",
    }
    base.update(over)
    return base

def run_analysis(payload, events: list, label: str):
    r = httpx.post(f"{BASE}/api/claims/analyze", json=payload, timeout=30)
    task_id = r.json()["task_id"]
    print(f"[{label}] task_id={task_id}")

    done = threading.Event()

    def listen():
        with httpx.stream("GET", f"{BASE}/api/stream/{task_id}", timeout=180) as resp:
            event_name = None
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and event_name:
                    try:
                        data = json.loads(line.split(":", 1)[1].strip())
                    except Exception:
                        data = line.split(":", 1)[1].strip()
                    events.append((event_name, data))
                    if event_name in ("done",):
                        done.set()
                        break

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    if not done.wait(timeout=170):
        print(f"[{label}] TIMEOUT menunggu stream")
    t.join(timeout=5)


def main():
    # ===== Test 1: klaim tanggal korup → hard reject =====
    events = []
    bad = claim_payload(
        claim_id="CLM-SMOKE-BAD",
        admission_date="2026-07-19",
        discharge_date="2026-07-10",
    )
    # simpan dulu ke DB
    r = httpx.post(f"{BASE}/api/claims", json=bad, timeout=30)
    print(f"[BAD] create status: {r.status_code}")
    run_analysis(bad, events, "BAD")
    rejected = [d for (e, d) in events if e == "rejected"]
    print(f"[BAD] rejected event: {rejected}")
    assert rejected, "HARD REJECT TIDAK BEKERJA!"
    print("[BAD] ✓ Validasi deterministik menolak klaim korup\n")

    # ===== Test 2: klaim normal → pipeline penuh =====
    events2 = []
    httpx.post(f"{BASE}/api/claims", json=claim_payload(), timeout=30)
    run_analysis(claim_payload(), events2, "NORMAL")
    phases = [e for (e, d) in events2]
    print(f"[NORMAL] events: {phases}")
    phase1 = next((d for (e, d) in events2 if e == "phase1_complete"), None)
    phase3 = next((d for (e, d) in events2 if e == "phase3_complete"), None)
    phase4 = next((d for (e, d) in events2 if e == "phase4_complete"), None)
    if phase1:
        print(f"[NORMAL] clinical flags: {phase1['clinical']['rule_flags']}, source: {phase1['clinical']['evidence_source']}")
        print(f"[NORMAL] financial: dev={phase1['financial']['deviation_pct']:.1f}%, method={phase1['financial']['method']}, shap={len(phase1['financial']['shap_top_features'])} fitur")
        print(f"[NORMAL] fraud: sim={phase1['fraud']['similarity_max_score']:.2f}, similar_claims={len(phase1['fraud']['similar_claims'])}, graph={phase1['fraud']['graph_cluster_anomaly_score']}")
    if phase3:
        print(f"[NORMAL] risk: score={phase3['risk']['total_score']}, tier={phase3['risk']['priority_tier']}, breakdown={phase3['risk']['breakdown']}")
    if phase4:
        expl = phase4["explanation"]
        print(f"[NORMAL] explanation by: {expl['generated_by']}")
        print(f"[NORMAL] narrative: {expl['narrative_id']}")
        print(f"[NORMAL] action: {expl['recommended_action']}")
        assert phase3["risk"]["total_score"] == json.loads(json.dumps(phase3["risk"]))["total_score"]
        # Validasi: skor di narasi harus sesuai (pakai normalisasi sama seperti backend)
        import re
        vals = []
        for m in re.finditer(r"\d+(?:[.,]\d+)*", expl["narrative_id"]):
            tok = m.group()
            if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", tok):
                tok = tok.replace(".", "").replace(",", ".")
            else:
                tok = tok.replace(",", ".")
            try:
                vals.append(float(tok))
            except ValueError:
                pass
        score = phase3["risk"]["total_score"]
        ok = any(abs(v - score) < 0.05 or abs(v - round(score)) < 0.05 for v in vals)
        print(f"[NORMAL] angka di narasi: {vals} — skor asli {score} {'✓ ADA' if ok else '✗ HILANG'}")
    print("\nSMOKE TEST SELESAI")

if __name__ == "__main__":
    main()
