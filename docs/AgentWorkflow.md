# AgentWorkflow.md — Multi-Agent Pipeline & Investigation Workflow

> **AEGIS-Health: Agentic Risk Engine & Intelligent Surveillance for Healthcare**  
> Nama Frontend: **AEGIS — Pusat Pemeriksaan Klaim**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 3.0  
> Status: Aktual — Disinkronkan dengan implementasi kode (`orchestrator.py`, `agents/`, `core/`, `workers/`) (Oktober 2026)

---

## 1. Overview Pipeline Multi-Agent

Pipeline analisis AEGIS-Health (`orchestrator.py`) mengimplementasikan arsitektur **hybrid multi-stage agent pipeline** yang menggabungkan validasi integritas deterministik, eksekusi agent spesialis paralel, sintesis lintas-sinyal berbasis LLM, skoring risiko matematis deterministik, serta penjabaran narasi investigasi dalam Bahasa Indonesia baku.

Arsitektur ini dirancang secara khusus untuk memenuhi standar keandalan tinggi operasional BPJS Kesehatan: **tidak pernah gagal total (zero unhandled exceptions)**, **sepenuhnya dapat diaudit (fully auditable)**, dan **skor risiko tidak dapat dihalusinasi oleh AI**.

```
[KLAIM INPUT / QUEUE WORKER]
            |
            v
POST /api/claims/analyze  -->  task_id (UUID4) + asyncio.Queue
            |
            +-------------------------------------------------------+
            |                  process_claim()                      |
            |                                                       |
            |   PHASE 0: Validasi Deterministik                     |
            |   (Schema, Tanggal, Severity, Biaya, Duplikasi DB)     |
            |            |                                          |
            |            +---> REJECTED (Emit event "rejected")     |
            |            |                                          |
            |            v VALID / DUPLICATE WARNING                |
            |   PHASE 1: Eksekusi Paralel (asyncio.gather)          |
            |   +-------------------+-------------------+           |
            |   | Clinical Agent    | Financial Engine  | Fraud     |
            |   | (INA-CBG Rule     | (XGBoost Regressor| Agent     |
            |   |  Heuristik +      |  + SHAP Tree-     | (LanceDB  |
            |   |  LLM Lapis 2)     |   Explainer)      |  Vector + |
            |   |                   |                   |  Graph)   |
            |   +---------+---------+---------+---------+-----+     |
            |             |                   |               |     |
            |             +-------------------+---------------+     |
            |                                 |                     |
            |                                 v                     |
            |   PHASE 2: Review Synthesis Agent (LLM)               |
            |   (Korelasi Lintas Sinyal, Tingkat Bukti, Narrative)  |
            |                                 |                     |
            |                                 v                     |
            |   PHASE 3: Deterministic Risk Score Engine            |
            |   (Formulasi Matematika Berbobot 0 - 100, Cap 85)     |
            |                                 |                     |
            |                                 v                     |
            |   PHASE 4: Indonesian Explanation & QA Agent          |
            |   (Ringkasan Eksekutif, Rekomendasi Verifier BI)      |
            |                                 |                     |
            |                                 v                     |
            |   PERSISTENCE & SSE EMISSION                          |
            |   (PostgreSQL Claims + Findings + Audit Logs)         |
            +-------------------------------------------------------+
```

---

## 2. Rincian Fase Eksekusi Pipeline

### Phase 0: Deterministic Validation Gate (`validate_deterministic`)
Sebelum model machine learning atau agen AI dijalankan, klaim diperiksa melalui gerbang validasi deterministik berbiaya komputasi nol:

1. **Kelengkapan Field Wajib**: Memastikan `claim_id`, `patient_id`, `provider_id`, `icd10_code`, `ina_cbg_code`, `cost_claimed`, `admission_date`, dan `discharge_date` terisi dan valid.
2. **Konsistensi Kronologis Tanggal**:
   - `discharge_date >= admission_date`.
   - `los = (discharge_date - admission_date).days`.
   - Jika rawat jalan (`los == 0`), memvalidasi bahwa klaim tidak ditagih dengan kode tindakan rawat inap intensif.
3. **Validasi Rentang Severity Level**: Memastikan `severity_level` berada dalam rentang valid 1 sampai 4.
4. **Validasi Biaya Medis**: Memastikan `cost_claimed > 0`. Nilai negatif atau nol langsung ditolak.
5. **Exact Duplicate Check**:
   - Query langsung ke database untuk mencari klaim dengan `patient_id`, `provider_id`, `admission_date`, dan `cost_claimed` yang persis sama.
   - Jika ditemukan identik: menghasilkan sinyal duplikasi kritis (`exact_duplicate_flag = True`).

> **Output Phase 0**: Objek `ValidationResult` (`is_valid: bool`, `errors: List[str]`, `duplicate_flag: bool`). Jika `is_valid == False`, proses langsung dihentikan dengan status `REJECTED` dan sinyal pelanggaran dicatat.

---

### Phase 1: Parallel Screening Agents (`asyncio.gather`)
Jika Phase 0 lolos, tiga agen spesialis dieksekusi secara konkuren menggunakan `asyncio.gather` yang dibungkus oleh protokol ketahanan `run_with_fallback`:

```python
clinical_task = run_with_fallback(clinical_agent.analyze, claim)
financial_task = run_with_fallback(financial_engine.analyze, claim)
fraud_task = run_with_fallback(fraud_agent.analyze, claim)

clinical_res, financial_res, fraud_res = await asyncio.gather(
    clinical_task, financial_task, fraud_task
)
```

#### 1. Clinical Agent (`agents/clinical_agent.py`)
- **Tugas**: Memeriksa kelayakan klinis dan kesesuaian koding diagnosis (ICD-10) terhadap tarif INA-CBG.
- **Arsitektur Dual-Layer**:
  - **Lapis 1 (Deterministik Rule Engine)**:
    - Memeriksa matriks inkompatibilitas diagnosis vs prosedur (misalnya tindakan katarak pada klaim rawat inap komprehensif, atau kemoterapi tanpa diagnosis onkologi primer/sekunder).
    - Memeriksa batas kewajaran Length of Stay (LOS) per kelompok diagnosis.
    - Memeriksa kesesuaian severity level terhadap riwayat diagnosis sekunder (deteksi *upcoding*).
  - **Lapis 2 (LLM Clinical Evaluator)**:
    - Diaktifkan hanya ketika ditemukan anomali ambivalen atau kasus kompleks yang memerlukan interpretasi catatan medis (*clinical justification notes*).
    - Menghasilkan analisis justifikasi klinis terstruktur.
- **Output**: `ClinicalFinding` (status, anomaly_detected, anomaly_type, severity, clinical_explanation, rule_violations).

#### 2. Financial Engine (`core/financial_engine.py`)
- **Tugas**: Menilai kewajaran finansial biaya klaim terhadap benchmark episode klinis sejenis.
- **Komponen Inti**:
  - **Model Supervised XGBoost Regressor**:
    - Input: 15 fitur klinis & faskes (`COST_FEATURE_NAMES`) tanpa `cost_claimed` (mencegah *target leakage*).
    - Output: `expected_reimbursement` (estimasi biaya wajar).
  - **Kalkulasi Deviasi Biaya**:
    - `cost_difference = cost_claimed - expected_reimbursement`
    - `cost_ratio = cost_claimed / expected_reimbursement`
    - Ambang batas deviasi tinggi (*inflated cost*): deviasi rasio $\ge 1.5$ atau selisih nominal signifikan.
  - **SHAP TreeExplainer (Explainability)**:
    - Mengurai kontribusi setiap variabel terhadap deviasi biaya.
    - Mengekstrak Top-3 *positive cost drivers* (fitur pendorong biaya berlebih) dan Top-3 *negative cost drivers*.
- **Output**: `FinancialFinding` (expected_cost, difference, ratio, is_outlier, top_shap_features).

#### 3. Fraud Agent (`agents/fraud_agent.py`)
- **Tugas**: Mendeteksi pola kecurangan relasional, anomali multi-klaim, dan perilaku kolektif.
- **Komponen Inti**:
  - **LanceDB Vector Search & Multi-Factor Composite Similarity**:
    - Embedding diagnostik 384 dimensi (`all-MiniLM-L6-v2`).
    - Pencarian tetangga terdekat dengan rumus similarity komposit:
      $$S_{composite} = 0.35 \times S_{semantic} + 0.25 \times S_{clinical} + 0.20 \times S_{temporal} + 0.20 \times S_{provider}$$
    - Mendeteksi *cloning klaim* ($S \ge 0.90$ pada waktu berdekatan) dan *unbundling tindakan*.
  - **Repeat Billing Verification**:
    - Query jendela waktu ke database untuk mendeteksi klaim pasien sama di faskes sama dalam radius 0–30 hari.
  - **Unsupervised Anomaly Context (Isolation Forest)**:
    - Memeriksa anomali multivariat perilaku klaim secara keseluruhan.
  - **Graph Network Metrics**:
    - Mengakses skor sentralitas provider & dokter dari graf relasi bipartite untuk mengidentifikasi anomali frekuensi konsentrasi rujukan.
- **Output**: `FraudFinding` (is_fraud_suspect, fraud_patterns, similarity_score, matched_claim_ids, graph_risk_score).

---

### Phase 2: Review Synthesis Agent (`agents/review_agent.py`)
Setelah Phase 1 selesai, seluruh temuan dikompilasi dan diserahkan ke **Review Agent**.

- **Tugas**:
  - Mengkorelasikan sinyal dari Clinical, Financial, dan Fraud agent.
  - Menentukan derajat kekuatan bukti (*evidence level*):
    - `CRITICAL`: Ditemukan bukti kuat cloning, exact duplicate, atau kolusi provider.
    - `STRONG`: Ditemukan konvergensi 2 sinyal kuat (misal: upcoding klinis terkonfirmasi + biaya outlier tinggi).
    - `MODERATE`: Satu sinyal mencurigakan tanpa anomali pendukung lain.
    - `WEAK`: Deviasi statistik minor dalam batas variansi normal.
  - Menyusun narasi sintesis investigasi (*reasoning narrative*) yang runtut dan obyektif.
- **LLM Backbone**: Utama `gemini-2.0-flash` via Google AI Studio; cascade otomatis ke model lokal Ollama (`qwen2.5:3b`, fallback `llama3.2:3b`) bila cloud gagal/tanpa key.

---

### Phase 3: Deterministic Risk Score Engine (`core/risk_engine.py`)
> **PRINSIP KRITIS**: Skor risiko AEGIS-Health dihitung **100% secara matematis dan deterministik**. LLM **DILARANG KERAS** menetapkan atau memodifikasi angka skor risiko. Hal ini menjamin auditabilitas hukum dan mencegah inkonsistensi penilaian.

- **Rentang Skor**: `0.0` sampai `100.0`.
- **Komposisi Bobot**:
  - **Clinical Weight (35%)**: Pelanggaran aturan INA-CBG, ketidaksesuaian diagnosis-prosedur, upcoding severity.
  - **Financial Weight (35%)**: Rasio deviasi terhadap prediksi XGBoost dan signifikansi SHAP positive driver.
  - **Fraud & Relational Weight (30%)**: Deteksi repeat billing, unbundling, kemiripan embedding LanceDB, dan graf risiko faskes.
- **Aturan Capping 85 Poin**:
  - Untuk anomali terisolasi (hanya satu dimensi yang bermasalah, tanpa konfirmasi dari dimensi lain), skor risiko **dibatasi maksimal 85**.
  - Skor $\ge 85$ hanya dapat dicapai apabila terjadi **konvergensi multi-sinyal** (misalnya deviasi biaya tinggi + upcoding klinis + riwayat klaim berulang).
- **Penetapan Priority Tier**:
  - **HIGH** ($\ge 70$): Klaim berisiko tinggi — direkomendasikan prioritas utama verifikasi manual.
  - **MEDIUM** ($40 - 69$): Klaim dengan anomali parsial — verifikasi sampel atau klarifikasi berkas.
  - **LOW** ($< 40$): Klaim sesuai kaidah — direkomendasikan *auto-pass* atau audit rutin acak.

---

### Phase 4: Indonesian Explanation & QA Agent (`agents/explanation_agent.py`)
Fase terakhir menyusun presentasi hasil pemeriksaan ke dalam Bahasa Indonesia yang formal, ringkas, dan mudah dicerna oleh verifier medis BPJS:

1. **Ringkasan Eksekutif (Executive Summary)**: Maksimal 2–3 kalimat ringkas menjelaskan profil risiko klaim.
2. **Poin-Poin Bukti (Key Findings)**: Disusun dalam butir-butir terstruktur berbasis data (bukan opini spekulatif).
3. **Rekomendasi Verifikasi (Actionable Verification Steps)**: Tindakan konkret bagi verifier (misal: "Minta rekam medis lembar operasi tindakan", "Klarifikasi billing farmasi rawat intensif", "Cek kesesuaian surat rujukan").
4. **Bilingual Disclaimer**: Pernyataan wajib kepatuhan hukum bahwa hasil merupakan rekomendasi penapisan AI dan bukan vonis fraud final.

---

## 3. Protokol Ketahanan & Fallback (`run_with_fallback`)

Dalam lingkungan produksi perasuransian publik, kegagalan salah satu model AI eksternal tidak boleh menghentikan proses verifikasi klaim.

```python
async def run_with_fallback(func, *args, fallback_factory=None, **kwargs):
    try:
        return await asyncio.wait_for(func(*args, **kwargs), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(f"Agent {func.__name__} timed out. Using fallback.")
        return fallback_factory() if fallback_factory else create_empty_finding()
    except Exception as exc:
        logger.error(f"Agent {func.__name__} failed: {exc}. Using fallback.")
        return fallback_factory() if fallback_factory else create_empty_finding()
```

### Jaminan Ketahanan (Resilience Guarantees):
1. **Ollama / LLM Down**: Jika LLM lokal atau API cloud gagal merespons dalam 15 detik, generator narasi beralih ke *heuristic rule template* berbasis fakta temuan terstruktur. Skor risiko tetap dihitung 100% akurat.
2. **XGBoost / ML Missing**: Jika model ML gagal diakses, sistem menggunakan *historical IQR cost benchmark* dari SQLite/PostgreSQL.
3. **LanceDB Unavailable**: Jika vector database gagal, agent fraud beralih ke exact matching query SQL.
4. **Zero-Crash Pipeline**: Setiap error diisolasi pada tingkat agent tanpa menyebabkan `HTTP 500` pada pipeline utama.

---

## 4. Server-Sent Events (SSE) Protocol Specifications

Frontend AEGIS menerima update timeline investigasi secara real-time melalui koneksi SSE di `/api/claims/stream/{task_id}`.

### 4.1 Struktur Payload Event

```json
{
  "event": "phase_completed",
  "data": {
    "task_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "phase": 1,
    "phase_name": "Parallel Screening",
    "status": "completed",
    "timestamp": "2026-10-21T14:30:15.123Z",
    "payload": {
      "clinical": {"anomaly_detected": true, "type": "UPCODING_SUSPECT"},
      "financial": {"expected_cost": 5400000, "difference": 3200000},
      "fraud": {"similarity_score": 0.88, "repeat_billing": false}
    }
  }
}
```

### 4.2 Urutan Event dalam Stream

| Urutan | Tipe Event | Deskripsi Konten |
|---|---|---|
| 1 | `claim_started` | Inisialisasi analisis, konfirmasi ID klaim & task ID |
| 2 | `phase_completed` (Phase 0) | Hasil validasi deterministik (passed / rejected) |
| 3 | `agent_finding` (Clinical) | Temuan awal spesialis clinical agent |
| 4 | `agent_finding` (Financial) | Temuan estimasi biaya & deviasi XGBoost/SHAP |
| 5 | `agent_finding` (Fraud) | Temuan vector similarity & network anomaly |
| 6 | `phase_completed` (Phase 1) | Rekapitulasi selesai skrining paralel |
| 7 | `phase_completed` (Phase 2) | Selesai sintesis bukti lintas sinyal (Review Agent) |
| 8 | `phase_completed` (Phase 3) | Skor risiko deterministik & priority tier terhitung |
| 9 | `phase_completed` (Phase 4) | Narasi penjelasan Bahasa Indonesia selesai dirangkai |
| 10 | `claim_analyzed` | Payload final lengkap tersimpan di database |
| 11 | `[DONE]` | Penutupan koneksi SSE stream oleh server |

---

## 5. Integrasi Auto-Scan Worker (FIFO Queue)

Untuk simulasi throughput operasional tinggi, sistem menyediakan modul **Auto-Scan Worker** (`backend/app/workers/auto_scan_worker.py`):

1. **Struktur FIFO Queue**: Memanfaatkan `asyncio.Queue` untuk menampung antrean klaim baru yang masuk secara kontinu.
2. **Asynchronous Consumer Loop**:
   - Worker mengambil klaim dari antrean secara FIFO.
   - Menjalankan `process_claim(claim, queue=None)`.
   - Mengupdate status `auto_scan_status` (klaim diproses, klaim tersisa, kecepatan pemrosesan, riwayat anomali).
3. **Dynamic Throttle Control**:
   - Operator dapat mengatur kecepatan scan antara `0.5 detik` hingga `10.0 detik` per klaim melalui endpoint `/api/autoscan/speed`.
4. **State Machine Auto-Scan**:
   - `STOPPED` $\rightarrow$ `RUNNING` $\leftrightarrow$ `PAUSED` $\rightarrow$ `RESET`.
5. **Synthetic Scenario Injection**:
   - Kemampuan menyuntikkan paket skenario klaim anomali (Upcoding, Phantom Billing, Unbundling, Cloning) untuk pengujian real-time verifier.

---

## 6. Interactive Copilot Agent (`backend/app/routers/copilot.py`)

Selain pipeline verifikasi otomatis, sistem menyertakan agen percakapan interaktif **AI Copilot** untuk mendampingi verifier saat menelaah klaim rumit:

1. **Context-Aware RAG Injection**:
   - Saat verifier membuka detail klaim tertentu, Copilot secara otomatis menyuntikkan ringkasan klaim aktif, rincian temuan Clinical/Financial/Fraud, profil faskes, serta benchmark INA-CBG terkait ke dalam *system prompt*.
2. **Kueri Verifier yang Didukung**:
   - Penjelasan terminologi kode ICD-10 dan INA-CBG.
   - Justifikasi mengapa biaya tertentu dianggap *outlier*.
   - Saran dokumen pembuktian tambahan yang perlu diminta ke RS.
   - Draft formulir permintaan klarifikasi resmi (*surat konfirmasi klaim*).
3. **Auditability**: Seluruh riwayat percakapan Copilot disimpan bersama tiket klaim dan dapat ditinjau ulang oleh supervisor verifikator.

---

## 7. Referensi Dokumen Terkait

- [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md): Definisi kebutuhan produk AEGIS-Health.
- [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md): Arsitektur teknis dan diagram infrastruktur sistem.
- [MODELS.md](file:///c:/Users/Radith/E-Jak/docs/MODELS.md): Spesifikasi lengkap model ML, SHAP, Vector LanceDB, dan LLM.
- [BusinessCore.md](file:///c:/Users/Radith/E-Jak/docs/BusinessCore.md): Logika domain perasuransian JKN dan INA-CBG.
- [API.md](file:///c:/Users/Radith/E-Jak/docs/API.md): Spesifikasi lengkap antarmuka REST API dan payload SSE.
