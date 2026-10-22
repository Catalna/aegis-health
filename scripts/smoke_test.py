"""Smoke test end-to-end terhadap sistem yang berjalan (backend + Postgres + Ollama):

  Test 1: klaim dengan tanggal discharge < admission → validasi deterministik
          menolak (hard reject) → status "failed" + pesan kegagalan yang aman.
  Test 2: klaim normal → antrean FIFO memproses → hasil low-risk → keputusan
          verifier tersimpan.

Catatan arsitektur: sejak auto-scan FIFO queue, analisis otomatis berjalan
lewat worker database (bukan task_id SSE per klaim baru). Alur SSE manual
(POST /api/claims/analyze + GET /api/stream/{task_id}) diuji oleh
backend/tests/test_manual_analysis.py dan frontend/tests/sse_transport_smoke.py.
"""
import time
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = "http://localhost:8000"
POLL_TIMEOUT_S = 300
POLL_INTERVAL_S = 3


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


def create_claim(payload):
    r = httpx.post(f"{BASE}/api/claims", json=payload, timeout=30)
    assert r.status_code == 200, f"Create gagal: {r.status_code} {r.text}"
    return r.json()


def poll_status(claim_id, terminal_statuses, timeout=POLL_TIMEOUT_S):
    """Poll GET /api/claims/{id} sampai status terminal atau timeout."""
    deadline = time.monotonic() + timeout
    data = {}
    while time.monotonic() < deadline:
        r = httpx.get(f"{BASE}/api/claims/{claim_id}", timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") in terminal_statuses:
            return data
        time.sleep(POLL_INTERVAL_S)
    raise AssertionError(
        f"[{claim_id}] TIMEOUT {timeout}s menunggu status {terminal_statuses}; status terakhir: {data.get('status')!r}"
    )


def reset_claim(claim_id):
    r = httpx.delete(f"{BASE}/api/claims/{claim_id}", timeout=30)
    print(f"[CLEANUP] reset {claim_id}: {r.status_code} {r.json().get('message', '')}")


def main():
    run_id = uuid.uuid4().hex[:8].upper()

    # ===== Test 1: klaim tanggal korup → validasi deterministik menolak =====
    bad = claim_payload(
        claim_id=f"CLM-SMOKE-BAD-{run_id}",
        admission_date="2026-07-19",
        discharge_date="2026-07-10",
    )
    created = create_claim(bad)
    print(f"[BAD] created: {created['status']}")
    final = poll_status(bad["claim_id"], {"failed"})
    assert final["status"] == "failed", final
    assert final.get("last_analysis_error"), "Hard reject tanpa pesan kegagalan!"
    print(f"[BAD] OK: validasi deterministik menolak -> '{final['last_analysis_error']}'")
    reset_claim(bad["claim_id"])

    # ===== Test 2: klaim normal → pipeline penuh → low risk → keputusan =====
    normal = claim_payload(
        claim_id=f"CLM-SMOKE-{run_id}",
        patient_id=f"PAT-SMOKE-{run_id}",
        provider_id=f"FAC-SMOKE-{run_id}",
        doctor_id=f"DR-SMOKE-{run_id}",
    )
    created = create_claim(normal)
    print(f"[NORMAL] created: {created['status']}")
    final = poll_status(normal["claim_id"], {"processed", "review_required", "failed"})
    assert final["status"] in {"processed", "review_required"}, f"Klaim normal gagal: {final}"

    analysis = httpx.get(f"{BASE}/api/claims/{normal['claim_id']}/analysis", timeout=30).json()
    result = analysis["result"]
    risk = result["risk"]
    fraud = result["fraud"]
    explanation = result["explanation"]
    print(f"[NORMAL] analysis_version={analysis['analysis_version']}, tier={analysis['priority_tier']}, score={analysis['total_score']}")
    assert risk["breakdown"].get("similarity_fraud") == 0.0
    assert not fraud.get("repeat_billing_flag")
    assert not fraud.get("cloning_flag")
    assert len(risk["breakdown"]) >= 4
    assert risk["total_score"] < 25, f"Klaim benchmark normal seharusnya low risk: {risk['total_score']}"
    print(f"[NORMAL] action: {explanation.get('recommended_action')}")
    assert explanation.get("qa_panel"), "qa_panel hilang dari penjelasan"

    decision = httpx.post(
        f"{BASE}/api/claims/{normal['claim_id']}/decision",
        json={
            "claim_id": normal["claim_id"],
            "decision": "Verified Valid",
            "reviewer": "SMOKE-VERIFIER",
            "note": "Smoke test holder",
        },
        timeout=30,
    )
    assert decision.status_code == 200, decision.text
    print(f"[NORMAL] keputusan tersimpan: {decision.json()['message']}")

    reset_claim(normal["claim_id"])

    # ===== Test 3: duplikat intake ditolak (409) =====
    dup = claim_payload(
        claim_id=f"CLM-SMOKE-DUP-{run_id}",
        patient_id=f"PAT-SMOKE-DUP-{run_id}",
        provider_id=f"FAC-SMOKE-{run_id}",
        doctor_id=f"DR-SMOKE-{run_id}",
    )
    first = create_claim(dup)
    assert first["status"] == "success"
    second = httpx.post(f"{BASE}/api/claims", json=dup, timeout=30)
    assert second.status_code == 409, f"Klaim ganda diterima?! {second.status_code} {second.text}"
    print("[DUP] OK: duplikat intake ditampakkan 409")
    reset_claim(dup["claim_id"])

    print("\nSMOKE TEST SELESAI — semua alur inti bekerja")


if __name__ == "__main__":
    main()
