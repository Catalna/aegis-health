# API.md — REST API & SSE Streaming Protocol Specification

> **J-ARI: JKN Agentic Risk Intelligence**  
> Nama Frontend: **AEGIS — Pusat Pemeriksaan Klaim**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 3.0  
> Status: Aktual — Disinkronkan dengan implementasi router FastAPI (`backend/app/routers/`) (Oktober 2026)

---

## 1. Overview & Konvensi Umum

Backend J-ARI/AEGIS mengekspos antarmuka antarmuka terpadu berbasis **FastAPI** dengan format pertukaran data standar **JSON** serta **Server-Sent Events (SSE)** untuk pembaruan timeline investigasi multi-agent secara real-time.

- **Base URL**: `http://localhost:8000` (atau host API produksi).
- **Prefix Endpoint**: `/api`
- **Interactive Documentation**:
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`
- **Format Tanggal & Waktu**: ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ` atau `YYYY-MM-DD`).
- **Mata Uang**: Rupiah (IDR), dinyatakan sebagai integer atau float desimal.

---

## 2. Claims Management & Risk Pipeline API

### 2.1 Menganalisis Klaim Baru (Asynchronous Pipeline Trigger)
Memulai pipeline analisis multi-agent 5 fase (`Phase 0` s/d `Phase 4`).

- **Method**: `POST`
- **Path**: `/api/claims/analyze`
- **Headers**: `Content-Type: application/json`

#### Request Body (`ClaimInput`):
```json
{
  "claim_id": "CLM-2026-00412",
  "patient_id": "PAT-99120",
  "patient_age": 52,
  "patient_gender": "Laki-laki",
  "provider_id": "FASKES-0012",
  "provider_name": "RSUD Sehat Sentosa",
  "provider_type": "RS Tipe B",
  "doctor_id": "DOC-7712",
  "service_type": "Rawat Inap",
  "admission_date": "2026-10-10",
  "discharge_date": "2026-10-15",
  "icd10_code": "K35.8",
  "icd10_description": "Other and unspecified acute appendicitis",
  "secondary_diagnoses": ["E11.9"],
  "procedures": ["47.01"],
  "ina_cbg_code": "Q-5-18-I",
  "severity_level": 1,
  "cost_claimed": 14500000.0,
  "notes": "Pasien mengeluh nyeri perut kanan bawah 2 hari."
}
```

#### Response Success (`HTTP 202 Accepted`):
```json
{
  "status": "processing",
  "task_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "claim_id": "CLM-2026-00412",
  "stream_url": "/api/claims/stream/3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "message": "Pipeline analisis klaim berhasil dimulai di background."
}
```

---

### 2.2 Live Investigation Stream (Server-Sent Events)
Menerima update progress investigasi agent secara real-time.

- **Method**: `GET`
- **Path**: `/api/claims/stream/{task_id}`
- **Headers**: `Accept: text/event-stream`

#### Alur & Format Payload SSE:

```
event: claim_started
data: {"task_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "claim_id": "CLM-2026-00412", "phase": 0}

event: phase_completed
data: {"task_id": "3fa85f64-...", "phase": 0, "phase_name": "Deterministic Validation", "status": "passed"}

event: agent_finding
data: {"agent": "clinical", "status": "completed", "anomaly_detected": true, "type": "UPCODING_SUSPECT"}

event: agent_finding
data: {"agent": "financial", "expected_cost": 7200000, "difference": 7300000, "ratio": 2.01}

event: agent_finding
data: {"agent": "fraud", "similarity_score": 0.42, "repeat_billing": false, "cloning_suspect": false}

event: phase_completed
data: {"phase": 2, "phase_name": "Review Synthesis", "evidence_level": "STRONG"}

event: phase_completed
data: {"phase": 3, "phase_name": "Risk Scoring", "risk_score": 78.5, "priority_tier": "HIGH"}

event: phase_completed
data: {"phase": 4, "phase_name": "Indonesian Explanation", "summary": "Klaim menunjukkan indikasi biaya berlebih..."}

event: claim_analyzed
data: {"claim_id": "CLM-2026-00412", "risk_score": 78.5, "priority_tier": "HIGH", "status": "UNDER_REVIEW"}
```

---

### 2.3 Daftar Klaim & Filter Prioritas
Mengambil daftar seluruh klaim dengan paginasi, pencarian, dan penyaringan berbasis status risiko.

- **Method**: `GET`
- **Path**: `/api/claims/`
- **Query Parameters**:
  - `status` (opsional): `SUBMITTED`, `ANALYZING`, `UNDER_REVIEW`, `VERIFIED`, `CLARIFICATION_REQUESTED`, `ESCALATED`, `REJECTED`.
  - `priority` (opsional): `HIGH`, `MEDIUM`, `LOW`.
  - `risk_category` (opsional): `UPCODING`, `PHANTOM_BILLING`, `CLONING`, `REPEAT_BILLING`, `UNBUNDLING`, `PROLONGED_LOS`, `INFLATED_BILL`.
  - `page` (default: 1): Nomor halaman.
  - `per_page` (default: 20, max: 100): Jumlah item per halaman.
  - `search` (opsional): Pencarian berbasis `claim_id`, nama pasien, atau nama faskes.

#### Response (`HTTP 200 OK`):
```json
{
  "total": 1420,
  "page": 1,
  "per_page": 20,
  "pages": 71,
  "data": [
    {
      "claim_id": "CLM-2026-00412",
      "patient_id": "PAT-99120",
      "provider_name": "RSUD Sehat Sentosa",
      "icd10_code": "K35.8",
      "ina_cbg_code": "Q-5-18-I",
      "cost_claimed": 14500000.0,
      "expected_reimbursement": 7200000.0,
      "potential_exposure": 7300000.0,
      "risk_score": 78.5,
      "priority_tier": "HIGH",
      "status": "UNDER_REVIEW",
      "created_at": "2026-10-21T08:12:00Z"
    }
  ]
}
```

---

### 2.4 Statistik Klaim & Ringkasan Paparan Finansial
Digunakan oleh widget kartu metrik pada Executive Dashboard.

- **Method**: `GET`
- **Path**: `/api/claims/stats`

#### Response (`HTTP 200 OK`):
```json
{
  "total_claims": 1420,
  "high_risk_count": 182,
  "medium_risk_count": 420,
  "low_risk_count": 818,
  "total_financial_exposure": 1845000000.0,
  "pending_clarification_count": 45,
  "escalated_count": 12,
  "verified_count": 1181
}
```

---

### 2.5 Detail Klaim, Temuan Bukti & Audit Trail
Mengambil rincian investigasi komprehensif untuk satu klaim tertentu.

- **Method**: `GET`
- **Path**: `/api/claims/{claim_id}`

#### Response (`HTTP 200 OK`):
```json
{
  "claim_info": {
    "claim_id": "CLM-2026-00412",
    "patient_id": "PAT-99120",
    "provider_id": "FASKES-0012",
    "provider_name": "RSUD Sehat Sentosa",
    "cost_claimed": 14500000.0,
    "risk_score": 78.5,
    "priority_tier": "HIGH",
    "status": "UNDER_REVIEW"
  },
  "clinical_finding": {
    "anomaly_detected": true,
    "anomaly_type": "UPCODING_SUSPECT",
    "severity_level_matched": false,
    "violations": ["Severity Level 1 ditagihkan dengan tarif Level 3"]
  },
  "financial_finding": {
    "expected_reimbursement": 7200000.0,
    "cost_difference": 7300000.0,
    "cost_ratio": 2.01,
    "is_outlier": true,
    "top_shap_features": [
      {"feature": "severity_level", "contribution": 1200000.0},
      {"feature": "los", "contribution": 450000.0}
    ]
  },
  "fraud_finding": {
    "is_fraud_suspect": false,
    "similarity_score": 0.42,
    "repeat_billing_found": false
  },
  "synthesis": {
    "evidence_level": "STRONG",
    "executive_summary_id": "Ditemukan indikasi upcoding biaya dengan selisih Rp 7.300.000...",
    "actionable_recommendations": [
      "Minta rekam medis lengkap dan rincian obat farmasi",
      "Klarifikasi alasan penagihan tarif paket komplikasi"
    ]
  },
  "audit_trail": [
    {
      "action": "AUTO_ANALYZED",
      "user": "SYSTEM_AGENT",
      "timestamp": "2026-10-21T08:12:05Z",
      "notes": "Skor risiko 78.5 ditetapkan oleh Risk Engine."
    }
  ]
}
```

---

### 2.6 Submit Keputusan Verifikator (Human Decision)
Mencatat keputusan akhir verifikator manusia ke dalam audit trail.

- **Method**: `POST`
- **Path**: `/api/claims/{claim_id}/decision`
- **Headers**: `Content-Type: application/json`

#### Request Body:
```json
{
  "action": "REQUEST_CLARIFICATION",
  "verifier_id": "VRF-088",
  "verifier_name": "dr. Maya Indah",
  "verifier_notes": "Meminta berkas lembar laporan operasi dan rincian alkes ruang intensif dari RSUD Sehat Sentosa.",
  "clarification_deadline": "2026-10-28"
}
```

#### Valid Values for `action`:
- `VERIFY` (Menyetujui klaim / Approve)
- `REQUEST_CLARIFICATION` (Meminta konfirmasi faskes)
- `ESCALATE` (Eskalasi ke Tim Investigasi Khusus BPJS)
- `REJECT` (Menolak pembayaran klaim)

#### Response Success (`HTTP 200 OK`):
```json
{
  "status": "success",
  "claim_id": "CLM-2026-00412",
  "new_status": "CLARIFICATION_REQUESTED",
  "recorded_at": "2026-10-21T14:40:00Z"
}
```

---

### 2.7 Export Evidence Bundle (Audit Packet)
Mengunduh paket bukti lengkap klaim berformat JSON/PDF untuk arsip hukum.

- **Method**: `GET`
- **Path**: `/api/claims/{claim_id}/evidence-bundle`

---

## 3. Auto-Scan Worker API (FIFO Queue)

Mengontrol simulasi pemrosesan throughput batch klaim latar belakang (`auto_scan_worker.py`).

| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/api/autoscan/status` | Mengambil status worker (`state`, `processed`, `remaining`, `speed`, `logs`) |
| `POST` | `/api/autoscan/start` | Menjalankan consumer loop antrean FIFO |
| `POST` | `/api/autoscan/pause` | Menjeda pemrosesan sementara tanpa mengosongkan antrean |
| `POST` | `/api/autoscan/resume` | Melanjutkan pemrosesan klaim dari posisi terakhir |
| `POST` | `/api/autoscan/stop` | Menghentikan loop pemrosesan latar belakang |
| `POST` | `/api/autoscan/reset` | Mereset penghitung statistik dan mengosongkan antrean |
| `POST` | `/api/autoscan/inject` | Menyuntikkan batch klaim dengan skenario anomali tertentu |
| `POST` | `/api/autoscan/speed` | Mengatur jeda pemrosesan klaim (0.5s s/d 10.0s) |

#### Contoh Payload Injeksi Skenario (`POST /api/autoscan/inject`):
```json
{
  "scenario": "UPCODING_BATCH",
  "count": 25
}
```

#### Contoh Payload Penyesuaian Kecepatan (`POST /api/autoscan/speed`):
```json
{
  "delay_seconds": 1.5
}
```

---

## 4. AI Copilot API (`copilot.py`)

Asisten percakapan berbasis RAG untuk mendampingi verifikator menelaah klaim.

### 4.1 Kirim Pesan ke Copilot
- **Method**: `POST`
- **Path**: `/api/copilot/chat`
- **Request Body**:
```json
{
  "claim_id": "CLM-2026-00412",
  "message": "Mengapa klaim ini dikategorikan outlier biaya tinggi?",
  "history": [
    {"role": "user", "content": "Klaim ini dari RS mana?"},
    {"role": "assistant", "content": "Klaim ini diajukan oleh RSUD Sehat Sentosa (Tipe B)."}
  ]
}
```
- **Response**:
```json
{
  "reply": "Klaim ini ditandai sebagai outlier biaya karena biaya yang diajukan adalah Rp 14.500.000, sedangkan benchmark expected reimbursement untuk kasus appendicitis akut severity level 1 di RS Tipe B adalah Rp 7.200.000 (rasio 2.01x). Faktor pendorong utama berdasarkan analisis SHAP adalah penetapan severity level yang tidak didukung oleh diagnosis sekunder mayor.",
  "suggested_actions": [
    "Minta resume medis lembar verifikasi koder",
    "Bandingkan dengan riwayat klaim appendicitis lain di RSUD Sehat Sentosa"
  ]
}
```

### 4.2 Ambil Riwayat Chat Klaim
- **Method**: `GET`
- **Path**: `/api/copilot/history/{claim_id}`

---

## 5. Healthcare Provider Analytics API

### 5.1 Daftar Fasilitas Kesehatan & Profil Risiko
- **Method**: `GET`
- **Path**: `/api/providers/`
- **Query Params**: `type`, `region`, `min_risk_score`, `sort_by`

### 5.2 Detail Fasilitas Kesehatan & Network Graph
- **Method**: `GET`
- **Path**: `/api/providers/{provider_id}/graph`
- **Response**:
```json
{
  "provider_id": "FASKES-0012",
  "provider_name": "RSUD Sehat Sentosa",
  "degree_centrality": 0.45,
  "referral_concentration_index": 0.32,
  "top_referring_doctors": [
    {"doctor_id": "DOC-7712", "claims_count": 84, "anomaly_rate": 0.28}
  ],
  "graph_risk_tier": "ELEVATED"
}
```

---

## 6. Reports & Export API

### 6.1 Ringkasan Eksekutif
- **Method**: `GET`
- **Path**: `/api/reports/summary`

### 6.2 Unduh Dokumen Laporan Verifikasi
- **Method**: `GET`
- **Path**: `/api/reports/export/pdf`
- **Response**: Berkas biner `application/pdf` dengan header `Content-Disposition: attachment; filename="aegis_verification_report.pdf"`.

### 6.3 Export Data Klaim ke CSV
- **Method**: `GET`
- **Path**: `/api/reports/export/csv`
- **Response**: Berkas biner `text/csv`.

---

## 7. Penanganan Kesalahan (Error Handling Format)

Seluruh respons galat mengikuti format standar RFC 7807:

```json
{
  "error": {
    "code": "CLAIM_NOT_FOUND",
    "message": "Klaim dengan ID CLM-99999 tidak ditemukan di database.",
    "status_code": 404,
    "timestamp": "2026-10-21T14:42:10Z"
  }
}
```

| HTTP Status | Keterangan |
|---|---|
| `400 Bad Request` | Pelanggaran validasi schema atau field tanggal tidak logis |
| `404 Not Found` | ID klaim, task_id, atau faskes tidak terdaftar |
| `422 Unprocessable` | Pelanggaran aturan Pydantic pada input body |
| `500 Server Error` | Galat internal (terisolasi, tidak mematikan server) |
