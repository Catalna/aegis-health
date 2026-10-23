# PRD.md � Product Requirement Document (J-ARI / AEGIS)

> **J-ARI: JKN Agentic Risk Intelligence**
> Nama Frontend: **AEGIS � Pusat Pemeriksaan Klaim**
> Healthkathon 2026 BPJS Kesehatan
> Versi Dokumen: 3.0
> Status: Aktual � Disinkronkan dengan implementasi kode (Oktober 2026)

---

## 1. Executive Summary

**J-ARI (JKN Agentic Risk Intelligence)**, yang ditampilkan kepada pengguna sebagai **AEGIS**, adalah sistem *risk prioritization & evidence intelligence* multi-agent berbasis AI dan ML yang dirancang untuk membantu verifier BPJS Kesehatan memprioritaskan klaim JKN yang paling perlu diperiksa lebih dahulu.

Sistem ini **tidak menggantikan verifier manusia** dan **tidak menyatakan sebuah klaim adalah fraud**. AEGIS berfungsi sebagai **lapisan screening deterministik** yang mengintegrasikan:

- Aturan domain INA-CBG (deterministik, skor utama)
- Model ML supervised (XGBoost + SHAP) untuk estimasi biaya wajar
- Model ML unsupervised (Isolation Forest) sebagai konteks perilaku pendukung
- Similarity search berbasis vector store (LanceDB) untuk deteksi cloning/repeat/unbundling
- Graph network metrics provider untuk anomali jaringan klaim
- LLM modular (Ollama lokal / Gemini API) **hanya** untuk sintesis narasi � tidak mengubah skor

Keputusan akhir selalu berada di tangan **verifier manusia**, dicatat dengan audit trail penuh.

---

## 2. Problem Statement & Business Context

### 2.1 Tantangan Operasional BPJS Kesehatan

1. **Volume Klaim Masif**: Jutaan klaim diproses setiap bulan dari ribuan Fasilitas Kesehatan (Faskes) di seluruh Indonesia.
2. **Kapasitas Verifikasi Terbatas**: Verifier menghadapi batasan waktu; pemeriksaan sama-rata membuat klaim berisiko tinggi terlambat ditangani.
3. **Pola Manipulasi Klaim yang Beragam**:
   - **Severity Inflation / Upcoding**: Menaikkan severity level tanpa bukti klinis untuk mendapat tarif INA-CBG lebih tinggi.
   - **Diagnosis Creep**: Menambahkan diagnosis sekunder fiktif (A41.9, E46, Z87.39) demi memenuhi syarat CC/MCC.
   - **Phantom Billing**: Klaim tindakan fiktif tanpa prosedur pendukung.
   - **Cloning & Repeat Billing**: Duplikasi klaim antar-pasien atau klaim berulang dalam rentang waktu berdekatan.
   - **Unbundling**: Memecah satu paket pelayanan INA-CBG menjadi beberapa tagihan terpisah.
   - **Prolonged LOS**: Length of Stay jauh di atas rentang klinis wajar untuk diagnosis tersebut.

### 2.2 Batasan Produk (Non-Negotiable)

AEGIS/J-ARI:
- **Tidak** menentukan status fraud secara definitif.
- **Tidak** menolak klaim secara otomatis.
- **Tidak** menggantikan sistem E-Klaim BPJS.
- **Tidak** membuat diagnosis medis.

Output utama adalah: risk score deterministik, priority tier, ranked evidence, peer comparison, similar claims, recommended action, dan decision slot untuk verifier.

---

## 3. Target Users & User Personas

| User Persona | Peran Utama | Kebutuhan Utama pada AEGIS |
|---|---|---|
| **BPJS Verifier (Klaim)** | Verifikasi harian klaim Faskes yang masuk. | Priority Queue (High/Medium/Low), narasi Bahasa Indonesia, SHAP feature attribution, dan klaim serupa. |
| **Tim Investigasi Fraud** | Memeriksa pola kecurangan sistemik. | Analisis Graph Network, skor Isolation Forest, relasi unbundling/repeat billing, export audit trail. |
| **Manajemen / Auditor BPJS** | Memantau kinerja keuangan & efisiensi. | Dashboard agregat (potential financial exposure, distribusi tier), evaluasi metrik ML riil. |

---

## 4. Functional Requirements

### FR-1: Claim Intake & FIFO Queue Worker

- **FR-1.1 Input Ingestion**: Menerima klaim terstruktur dengan field: `claim_id`, `patient_id`, `provider_id`, `doctor_id`, `diagnosis_primary`, `diagnosis_secondary[]`, `procedure_codes[]`, `medication[]`, `severity_level` (1-4), `cost_claimed`, `length_of_stay`, `admission_date`, `discharge_date`, `referral_info`.
- **FR-1.2 Auto-Queue Worker**: `ClaimQueueWorker` berjalan sebagai background task FastAPI. Setiap klaim yang masuk (`status=pending`) diproses secara FIFO berdasarkan `queue_sequence` (database sequence, immutable). Worker memiliki heartbeat setiap 30 detik dan recovery lease expired setiap 30 detik.
- **FR-1.3 Lifecycle States**: `pending -> scanning -> processed | review_required | failed | verified`. Status `review_required` untuk tier High/Medium, `processed` untuk tier Low.
- **FR-1.4 Retry & Fault Tolerance**: Maksimal 3 percobaan (`max_attempts=3`) per klaim. Klaim gagal dapat di-retry via `POST /api/claims/analyze?retry=true`.
- **FR-1.5 Manual Scan**: Endpoint `POST /api/claims/analyze` mendukung scan manual dengan SSE real-time per `task_id` UUID.

### FR-2: Phase 0 � Deterministic Validation Gate

Sebelum agent AI apapun diaktifkan, `validate_deterministic()` menjalankan:

- **FR-2.1** Kelengkapan field wajib: `claim_id`, `patient_id`, `provider_id`, `diagnosis_primary`.
- **FR-2.2** Kronologi tanggal: `discharge_date >= admission_date`. Pelanggaran => `hard_reject`.
- **FR-2.3** Konsistensi LOS vs rentang tanggal (warning lunak, selisih > 1 hari).
- **FR-2.4** Rentang valid `severity_level` (1-4) dan `cost_claimed > 0`.
- **FR-2.5** Exact Duplicate Check: Klaim dengan pasien, diagnosis, prosedur, biaya, dan tanggal masuk yang identik => `exact_duplicate_of` diset, hanya Fraud Agent yang dijalankan.

### FR-3: Phase 1 � Multi-Agent Parallel Screening

Tiga agent dijalankan paralel via `asyncio.gather` dengan `run_with_fallback()`:

**FR-3.1 Clinical Agent** (`clinical_agent.py`):
- **Lapis 1** (selalu): INA-CBG grouper lookup + rule consistency check. Menghasilkan `rule_flags[]` yang menjadi satu-satunya sumber skor klinis.
- **Lapis 2** (hanya kasus ambigu � diagnosis tidak dikenal atau hanya 1 flag questionable): LLM analisis plausibility klinis. LLM hanya menambah `evidence_text` dan `confidence_level`, tidak mengubah skor numerik.
- Rule flags: `tariff_deviation_high`, `tariff_deviation_extreme`, `severity_proc_mismatch`, `severity_med_mismatch`, `los_outlier`, `upcoding_risk_diag`, `unsupported_high_risk_proc`.

**FR-3.2 Financial Engine** (`financial_engine.py`):
- XGBoost Regressor (15 fitur, tanpa target leakage) memprediksi expected reimbursement benchmark.
- Menyimpan signed `deviation_pct`, menghitung `upward_exposure=max(0, claimed-benchmark)`, dan `anomaly_score` (0.0-1.0, capped di `abs(deviation_pct)/50`) secara konsisten pada jalur model dan fallback.
- SHAP attribution: top 5 fitur kontributor dengan label ramah verifier.
- Fallback otomatis ke Z-Score Peer Group Baseline jika model tidak tersedia.

**FR-3.3 Fraud Agent** (`fraud_agent.py`):
- LanceDB Vector Search: cosine embedding sebagai prefilter kandidat.
- Composite Multi-Factor Similarity Score: `0.40*code + 0.30*cost + 0.15*provider + 0.10*time + 0.05*patient`.
- Cloning: `same_provider=True AND same_patient=False AND code_sim>0.9 AND cost_prox>0.95 AND days<=45`.
- Repeat Billing: SQL � pasien sama, prosedur overlap, rentang 45 hari.
- Unbundling: SQL � pasien+provider+diagnosis sama, biaya gabungan mirip baseline.
- Isolation Forest: anomali perilaku multidimensi (20 fitur).
- Provider Graph Metrics: anomali jaringan klaim faskes (precomputed).

### FR-4: Phase 2 � Review Synthesis

- **FR-4.1 Review Agent** (`review_agent.py`): LLM (`deepseek-r1:7b` => fallback `mistral:7b`) menyintesis evidence dari tiga agent paralel.
- **FR-4.2** Guard deterministik: LLM tidak boleh mengklaim `strong_multi_signal` jika jumlah sumber sinyal deterministik < 2.
- **FR-4.3** Evidence IDs dibatasi hanya pada ID yang dihitung secara deterministik � LLM tidak bisa menciptakan evidence baru.
- **FR-4.4 Fallback**: Jika LLM gagal => `rule_fallback` dengan hitungan sumber sinyal deterministik.

### FR-5: Phase 3 � Deterministic Risk Scoring

- **FR-5.1** `calculate_risk_score()` murni matematis, tanpa input LLM. Skor adalah poin deterministik mentah, bukan probabilitas, dengan maksimum aktual 85 (`max_score=85`); UI menampilkan skala ini secara eksplisit.
- **FR-5.2 Scoring Breakdown**:

| Komponen | Bobot Maks | Sumber |
|---|---|---|
| `clinical_rule_flags` | 20 poin | Rule engine flags |
| `financial_anomaly` | 30 poin | `anomaly_score * 30` |
| `similarity_fraud` | 20 poin | Repeat/cloning/unbundling aktif |
| `evidence_support` | 15 poin | Jumlah sumber sinyal deterministik |
| `behavioral_context` | 0 poin | Isolation Forest/Graph (supporting only) |

- **FR-5.3 Priority Tiering**:
  - **High** (>= 60.0): `review_required`, `recommended_action=verify_immediately`
  - **Medium** (25.0-59.9): `review_required`, `recommended_action=review_when_available`
  - **Low** (< 25.0): `processed`, `recommended_action=low_priority`

### FR-6: Phase 4 � Indonesian Explanation & QA Panel

- **FR-6.1** LLM (`qwen2.5:7b` => fallback `mistral:7b`) menyusun narasi Bahasa Indonesia.
- **FR-6.2** Klaim prioritas Low => template deterministic langsung (tidak memanggil LLM).
- **FR-6.3 Validasi Wajib**: Semua angka di narasi LLM diparse dan dicocokkan dengan fakta sumber (skor, deviasi, kemiripan). Mismatch => retry maks 2x => template fallback.
- **FR-6.4 Narrative Sanitizer**: Jargon teknis (SHAP, XGBoost, Jaccard, isolation_forest, dll.) distrip deterministik sebelum ditampilkan ke verifier.
- **FR-6.5 QA Panel**: `why_top_priority`, `most_similar_claim`, `strongest_evidence`, `is_this_fraud` (hardcoded disclaimer).
- **FR-6.6** `recommended_action` diturunkan dari `priority_tier`, bukan dari LLM.

### FR-7: Real-Time Event Streaming (SSE)

- **FR-7.1** Endpoint `GET /api/stream/{task_id}` menyalurkan event pipeline real-time.
- **FR-7.2** Event types: `status`, `phase1_complete`, `phase2_complete`, `phase3_complete`, `phase4_complete`, `done`, `error`, `rejected`.
- **FR-7.3** Queue per `task_id` UUID (bukan per `claim_id`) untuk isolasi sesi.
- **FR-7.4** Orphan timeout 5 detik (task dibatalkan jika SSE consumer tidak attach dalam waktu itu).
- **FR-7.5** Data SSE difilter oleh `public_analysis_projection()` sebelum dikirim ke frontend (internal trace/error tidak bocor).

### FR-8: Human Verification & Audit Trail

- **FR-8.1** Verifier dapat memilih keputusan: `Verified Valid`, `Needs Further Review`, `Escalate`, `Request Clarification`.
- **FR-8.2** Keputusan disimpan di tabel `human_decisions` dan `audit_logs`.
- **FR-8.3** Semua eksekusi agent dicatat di `agent_runs` dengan `status`, `duration_ms`, dan `model_used`.
- **FR-8.4** Setiap perubahan status pipeline dicatat di `audit_logs`.

### FR-9: Dashboard Analytics & ML Evaluation

- **FR-9.1** `GET /api/analytics/dashboard`: Agregat klaim, distribusi tier, `potential_financial_exposure` via SQL (SUM(max(0, actual_cost - predicted_cost_upper)) untuk High/Medium tier).
- **FR-9.2** `GET /api/ml/eval`: Metrik evaluasi nyata dari `evaluation_results.json` (Precision@K, PR-AUC, latency).
- **FR-9.3** `GET /api/ml/eval/p1`: Evaluasi P1 pipeline (precision, recall, F1).
- **FR-9.4** `GET /api/health`: Status real-time semua komponen (DB, Ollama, XGBoost, Isolation Forest, LanceDB, Graph Metrics, Queue Worker).

---

## 5. Non-Functional Requirements (NFR)

### NFR-1: Performance & Latency
- Pipeline screening penuh (Phase 0-4) dengan Ollama lokal: target < 3.5 detik per klaim.
- SSE event pertama: < 100 ms dari commit POST `/api/claims/analyze`.

### NFR-2: Infrastructure & Offline-First
- Target minimum: Intel Core 5, 16GB RAM, GPU NVIDIA RTX 6-8GB VRAM.
- Model LLM via Ollama dengan kuantisasi Q4_K_M (default `qwen2.5:3b` sesuai `.env` aktual).
- Sistem beroperasi penuh **offline/on-premise** tanpa koneksi internet eksternal.
- Fallback ke Gemini API (opsional) jika `LLM_PROVIDER=gemini`.

### NFR-3: Fault Tolerance & Non-Blocking Fallback
- Setiap agent dibungkus `run_with_fallback()`.
- Kegagalan satu agent tidak menghentikan pipeline; hasil parsial dikembalikan dengan `partial=True`.
- LLM retry otomatis 2x dengan feedback error sebelum fallback ke template/rule.

### NFR-4: Data Integrity & Analysis Versioning
- Setiap analisis di-stamp dengan `ANALYSIS_VERSION` (integer).
- Klaim dengan analisis versi lama otomatis di-requeue oleh `recover_invalid_terminal_analysis()`.
- `received_at` dan `queue_sequence` klaim bersifat **immutable** (dijaga oleh DB trigger PostgreSQL).

### NFR-5: Privacy & PII Minimization
- Data klaim menggunakan pseudonymized ID (`patient_id`, `provider_id`, `doctor_id`).
- Kode ICD-10 dan ICD-9-CM sebagai identifier klinis.
- Teks error internal tidak bocor ke frontend (difilter oleh `safe_failure()` dan `public_analysis_projection()`).

---

## 6. Frontend Pages & Navigation

Aplikasi frontend (React + Vite, branding **AEGIS**) terdiri dari:

| Halaman | Route | Deskripsi |
|---|---|---|
| **Dashboard Utama** | `/` | Statistik agregat, distribusi tier, potential financial exposure |
| **Daftar Klaim** | `/claims` | Tabel klaim dengan filter status dan tier, FIFO queue summary |
| **Input Klaim** | `/intake` | Form pengajuan klaim manual (alat bantu demo) |
| **Pemantauan Sistem** | `/monitoring` | Status real-time semua komponen backend |
| **Evaluasi Ketepatan** | `/ml-eval` | Metrik evaluasi ML (Precision@K, PR-AUC, F1) |
| **Investigasi** | `/investigate/:claimId` | Timeline SSE real-time eksekusi pipeline per klaim |
| **Assessment** | `/assessment/:claimId` | Hasil analisis lengkap: skor, evidence, SHAP, klaim serupa, QA panel, decision form |

---

## 7. Key Business Metrics & Value Proposition

1. **Verification Efficiency**: Mengurangi waktu peninjauan awal dengan prioritisasi berbasis skor.
2. **Precision of High-Risk Tier**: Target PR-AUC > 0.85 pada deteksi deviasi dan upcoding.
3. **Potential Financial Exposure**: SUM(max(0, claimed - predicted_upper)) untuk klaim High/Medium. Nilai ini adalah indikasi awal, wajib divalidasi oleh keputusan verifier manusia.
4. **Audit Completeness**: 100% keputusan verifier tercatat dengan timestamp, reviewer ID, dan `analysis_generation`.

---

## 8. Referensi Dokumen Terkait

- [Architecture.md](./Architecture.md) � Cetak biru arsitektur teknis dan database schema.
- [BusinessCore.md](./BusinessCore.md) � Logika domain bisnis JKN, INA-CBG, dan strategi mitigasi.
- [AgentWorkflow.md](./AgentWorkflow.md) � Detail alur pipeline multi-agent dan protokol SSE.
- [MODELS.md](./MODELS.md) � Spesifikasi teknis model ML, Vector Store, Graph Metrics, dan LLM.
