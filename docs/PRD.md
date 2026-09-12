# PRD.md — Product Requirement Document (J-ARI)

> **J-ARI: JKN Agentic Risk Intelligence**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 1.0  
> Status: Production Specification  

---

## 1. Executive Summary

**J-ARI (JKN Agentic Risk Intelligence)** adalah sistem inteligensi risiko multi-agent berbasis kecerdasan buatan (AI & ML) yang dirancang khusus untuk memprioritaskan dan menganalisis klaim kesehatan berisiko tinggi pada program Jaminan Kesehatan Nasional (JKN) BPJS Kesehatan.

Sistem ini tidak menggantikan peran verifier manusia, melainkan berfungsi sebagai **lapisan inteligensi screening (Screening & Risk Intelligence Layer)** yang mengintegrasikan aturan deterministik INA-CBG, model machine learning supervised (XGBoost + SHAP) dan unsupervised (Isolation Forest + Graph Metrics), similarity search berbasis vector store (LanceDB), serta Large Language Models (LLM) swappable (Ollama lokal / Gemini API) untuk sintesis bukti investigasi dalam Bahasa Indonesia.

---

## 2. Problem Statement & Business Context

### 2.1 Tantangan Operasional BPJS Kesehatan
1. **Volume Klaim Masif**: Jutaan klaim diproses setiap bulan dari ribuan Fasilitas Kesehatan (Faskes) Tipe A, B, C, D, Klinik, dan Puskesmas di seluruh Indonesia.
2. **Kapasitas Verifikasi Terbatas**: Verifier BPJS Kesehatan menghadapi batasan waktu dalam meninjau setiap klaim dengan tingkat kedalaman yang sama.
3. **Kompleksitas Manipulasi Klaim (Upcoding & Fraud)**:
   - **Severity Inflation**: Menaikkan tingkat keparahan (severity level 2 ke 3/4) tanpa bukti klinis pendukung untuk mendapatkan pembayaran tarif INA-CBG yang lebih tinggi.
   - **Diagnosis Creep / Secondary Diagnosis Inflation**: Menambahkan diagnosis sekunder fiktif (seperti sepsis A41.9, malnutrisi E46, riwayat infeksi Z87.39) demi memenuhi syarat komplikasi (CC/MCC).
   - **Phantom Billing**: Klaim tindakan atau layanan fiktif.
   - **Cloning & Repeat Billing**: Duplikasi klaim antar-pasien atau klaim berulang untuk prosedur dan rentang waktu yang sama.
   - **Unbundling**: Memecah satu paket pelayanan prospektif INA-CBG menjadi beberapa tagihan terpisah.

### 2.2 Visi Produk
Memberikan **prioritisasi presisi berbasis bukti (Evidence-Based Priority Queue)** dan **ringkasan investigasi otomatis (AI Investigation Timeline)** sehingga verifier BPJS Kesehatan dapat memfokuskan 80% energi mereka pada 20% klaim paling berisiko tinggi, mempercepat siklus klarifikasi, serta menghemat potensi kerugian dana jaminan sosial kesehatan secara terukur.

---

## 3. Target Users & User Personas

| User Persona | Peran Utama | Kebutuhan Utama pada J-ARI |
|---|---|---|
| **BPJS Verifier (Klaim)** | Melakukan verifikasi harian atas klaim Faskes yang masuk. | Priority Queue (High/Medium/Low), ringkasan narasi Bahasa Indonesia, SHAP feature attribution, dan preseden klaim serupa (cloning check). |
| **Tim Investigasi Fraud** | Memeriksa pola kecurangan sistemik atau sindikat provider. | Analisis Graph Network (centrality), skor Isolation Forest, relasi unbundling/repeat billing, serta export audit trail. |
| **Manajemen / Auditor BPJS** | Memantau kinerja keuangan & efisiensi verifikasi. | Dashboard statistik agregat (potensi penghematan biaya, distribusi tier risiko) dan halaman evaluasi metrik ML riil. |

---

## 4. Functional Requirements

### FR-1: Claim Intake & Deterministic Validation Gate (Phase 0)
- **FR-1.1 Input Ingestion**: Menerima data klaim terstruktur (`claim_id`, `patient_id`, `provider_id`, `doctor_id`, `diagnosis_primary`, `diagnosis_secondary`, `procedure_codes`, `medication`, `severity_level`, `cost_claimed`, `length_of_stay`, `admission_date`, `discharge_date`, `referral_info`).
- **FR-1.2 Deterministic Gate**: Sebelum agent AI diaktifkan, sistem wajib menjalankan validasi deterministik:
  - Kelengkapan field wajib (`claim_id`, `patient_id`, `provider_id`, `diagnosis_primary`).
  - Validasi kronologi tanggal (`discharge_date >= admission_date`).
  - Rentang valid `severity_level` (1 hingga 4) dan `cost_claimed > 0`.
  - Pengecekan **Exact Duplicate** terhadap database (jika pasien, diagnosis, prosedur, dan biaya 100% identik dengan klaim sebelumnya).

### FR-2: Multi-Agent Parallel Screening (Phase 1)
- **FR-2.1 Clinical Agent**:
  - Pengecekan berbasis **INA-CBG Simplified Grouper**.
  - Pengecekan aturan deterministik: `tariff_deviation_high` (>50%), `tariff_deviation_extreme` (>100%), `severity_proc_mismatch`, `severity_med_mismatch`, `los_outlier`, `upcoding_risk_diag`, dan `unsupported_high_risk_proc`.
  - Dukungan LLM Lapis 2 (`mistral:7b`) untuk analisis plausible klinis jika data tidak tercakup penuh pada tabel grouper.
- **FR-2.2 Financial Engine**:
  - Model **XGBoost Regressor** untuk memprediksi kisaran biaya wajar klaim (*fair baseline cost*).
  - Menghitung persentase deviasi biaya (`deviation_pct`) dan `anomaly_score` (0.0 - 1.0).
  - Ekstraksi kontribusi fitur menggunakan **SHAP TreeExplainer** (*positive/negative impact*).
  - Fallback otomatis ke **Z-Score Peer Group** jika model XGBoost gagal/belum dilatih.
- **FR-2.3 Fraud Agent**:
  - Pencarian kemiripan klaim via **LanceDB Vector Store** menggunakan embedding `sentence-transformers` (`all-MiniLM-L6-v2`).
  - Menghitung **Komposit Multi-Faktor Similarity Score**: 40% kode medis (Jaccard) + 30% kedekatan biaya + 15% provider sama + 10% jarak tanggal + 5% pasien sama.
  - Deteksi **Repeat Billing**, **Cloning** (kemiripan tinggi + pasien BERBEDA + faskes SAMA), dan **Unbundling**.
  - Deteksi anomali **Isolation Forest** yang dimodulasi oleh **Precomputed Graph Network Metrics** (centrality & clustering coefficient provider).

### FR-3: Multi-Signal Synthesis & Review (Phase 2)
- **FR-3.1 Review Agent**:
  - Menyintesis sinyal dari Clinical Agent, Financial Engine, dan Fraud Agent.
  - Mengklasifikasikan `evidence_level` (`strong_multi_signal`, `single_signal`, `weak`).
  - Menyusun daftar `corroborating_signals` yang saling memperkuat.
  - Menghasilkan narasi penalaran (*reasoning trace*) menggunakan LLM (`deepseek-r1:7b` / `mistral:7b`).

### FR-4: Deterministic Risk Scoring Engine (Phase 3)
- **FR-4.1 Non-LLM Scoring**: Skor risiko (0 - 100) murni dihitung secara deterministik oleh `risk_engine.py` tanpa manipulasi angka dari LLM.
- **FR-4.2 Scoring Breakdown**:
  - `clinical_rule_flags`: Bobot maks 20 poin.
  - `financial_anomaly`: Bobot maks 30 poin.
  - `isolation_forest_anomaly`: Bobot maks 15 poin.
  - `similarity_fraud`: Bobot maks 20 poin.
  - `synthesis_confidence`: Bobot maks 15 poin.
- **FR-4.3 Priority Tiering**:
  - **High Priority** (Merah): Skor `>= 60.0`.
  - **Medium Priority** (Kuning): Skor `25.0 - 59.9`.
  - **Low Priority** (Hijau): Skor `< 25.0`.

### FR-5: Indonesian Explanation & QA Panel (Phase 4)
- **FR-5.1 Natural Language Narrative**: Menghasilkan narasi investigasi berstruktur dalam Bahasa Indonesia menggunakan LLM (`qwen2.5:7b`).
- **FR-5.2 Ranked Reasons**: Menyajikan 3 alasan utama prioritisasi risiko berdasarkan skor terbanyak.
- **FR-5.3 QA Panel**: Menyediakan panel Q&A otomatis untuk verifier ("Mengapa klaim ini prioritas tinggi?", "Klaim mana yang paling mirip?", "Apa bukti terkuat?").
- **FR-5.4 Safety Disclaimer**: Menyantumkan klausul eksplisit bahwa sistem tidak memvonis fraud, melainkan memberikan rekomendasi prioritas verifikasi.

### FR-6: Real-Time Event Streaming (SSE)
- **FR-6.1 Server-Sent Events**: Endpoint `/api/stream/{task_id}` menyalurkan status eksekusi agent secara real-time ke UI frontend.
- **FR-6.2 Isolated Task Queues**: Menggunakan `asyncio.Queue` per `task_id` untuk mencegah percampuran event antar-pengguna.

### FR-7: Human Verification & Audit Trail Logging
- **FR-7.1 Decision Submission**: Verifier dapat menginput keputusan manusia (`Verified Valid`, `Needs Further Review`, `Escalate`, `Request Clarification`).
- **FR-7.2 Audit Trail**: Setiap eksekusi agent, perubahan status, dan keputusan manusia dicatat pada tabel `agent_runs`, `risk_analyses`, `human_decisions`, dan `audit_logs`.

### FR-8: Dashboard Analytics & ML Evaluation
- **FR-8.1 Dashboard Metrics**: Menampilkan agregat klaim, distribusi tier risiko, jumlah klaim pending, dan estimasi potensi penghematan dana (`potential_savings`).
- **FR-8.2 Model Evaluation Page**: Menampilkan metrik evaluasi nyata (*held-out test set*) untuk model XGBoost dan Isolation Forest (Precision, Recall, F1-Score, PR-AUC, MAE, RMSE).

---

## 5. Non-Functional Requirements (NFR)

### NFR-1: Performance & Latency
- Eksekusi pipeline screening penuh (Phase 0 hingga Phase 4) diselesaikan dalam `< 3.5 detik` per klaim pada infrastruktur target.
- Streaming SSE merespons event pertama (`status: started`) dalam `< 100 ms`.

### NFR-2: Target Infrastructure & Offline-First Constraints
- Target Hardware Minimum: Intel Core 5 215H, RAM 16GB, GPU NVIDIA RTX 5050 (8GB VRAM).
- Model LLM lokal berjalan via **Ollama** dengan kuantisasi Q4_K_M (kebutuhan VRAM 4.5 GB - 5.0 GB termasuk KV cache).
- Sistem harus mampu beroperasi penuh secara **Offline / On-Premise** tanpa ketergantungan koneksi internet eksternal (menggunakan `OllamaClient`).

### NFR-3: Fault Tolerance & Non-Blocking Fallback Protocol
- Setiap agent dibungkus oleh handler `run_with_fallback()`.
- Jika salah satu agent mengalami error/timeout, pipeline **TIDAK Boleh Crash**.
- Hasil parsial dikembalikan dengan tag `partial=True`, serta error detail dicatat pada `agent_errors[]`.

### NFR-4: Privacy & PII Minimization
- Data klaim menggunakan pengelompokan rentang umur (`age_band`) dan kode wilayah (`region_code`).
- Patient ID dan Provider ID disamarkan/dipseudonimkan.

---

## 6. Key Business Metrics & Value Proposition

1. **Verification Efficiency**: Mengurangi waktu peninjauan awal klaim berisiko tinggi hingga 60%.
2. **Precision of High-Risk Tier**: Target PR-AUC `> 0.85` pada deteksi upcoding & anomaly klaim.
3. **Potential Cost Savings**: Mengkalkulasi potensi penyelamatan dana klaim abnormal melalui formula:
   $$\text{Savings} = \sum \max(0, \text{cost\_claimed} - \text{predicted\_cost\_upper})$$
   untuk seluruh klaim pada tier *High* dan *Medium*.

---

## 7. Referensi Dokumen Terkait
- [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md) — Cetak biru arsitektur teknis dan database schema.
- [BusinessCore.md](file:///c:/Users/Radith/E-Jak/docs/BusinessCore.md) — Logika domain bisnis JKN, INA-CBG, dan strategi mitigasi upcoding.
- [AgentWorkflow.md](file:///c:/Users/Radith/E-Jak/docs/AgentWorkflow.md) — Detail alur pipeline multi-agent dan protokol SSE.
- [Models.md](file:///c:/Users/Radith/E-Jak/docs/Models.md) — Spesifikasi teknis model ML, Vector Store, Graph Metrics, dan LLM.
