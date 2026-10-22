# Architecture.md — J-ARI System Architecture

> **J-ARI: JKN Agentic Risk Intelligence**
> Nama Frontend: **AEGIS — Pusat Pemeriksaan Klaim**
> Healthkathon 2026 BPJS Kesehatan
> Versi Dokumen: 3.0
> Status: Aktual — Disinkronkan dengan implementasi kode (Oktober 2026)

---

## 1. Tech Stack Summary

### Backend

| Komponen | Teknologi | Versi | Peran |
|---|---|---|---|
| Framework API | FastAPI | 0.141.1 | REST API + SSE streaming |
| ASGI Server | Uvicorn (standard) | 0.52.3 | HTTP server |
| ORM / DB Driver | SQLAlchemy (asyncio) | 2.0.52 | Async ORM |
| DB Driver Async | asyncpg | 0.31.0 | PostgreSQL async driver |
| Schema Validation | Pydantic | 2.13.4 | I/O validation semua agent |
| SSE | sse-starlette | 3.4.8 | Server-Sent Events untuk investigation timeline |
| HTTP Client | httpx | 0.28.1 | Panggil Ollama API & Gemini API |
| Env Config | python-dotenv | 1.2.3 | Load .env |

### Machine Learning & Vector Store

| Komponen | Teknologi | Versi | Peran |
|---|---|---|---|
| Cost Anomaly | XGBoost | 3.2.0 | Prediksi expected reimbursement benchmark |
| Explainability | SHAP | 0.49.1 | Feature attribution (shap.Explainer) |
| Unsupervised Anomaly | scikit-learn (Isolation Forest) | 1.7.2 | Supporting context anomali (bukan skor utama) |
| Feature Engineering | numpy | 2.2.6 | Feature pipeline (20 fitur full, 15 fitur cost) |
| Model Serialization | joblib | 1.5.3 | Save/load Isolation Forest |
| Data I/O | pyarrow | 25.0.1 | Format interchange LanceDB |
| Vector DB | LanceDB (embedded) | 0.37.1 | Similarity search tanpa server terpisah |
| Embedding Model | sentence-transformers | 5.7.0 | Encode klaim jadi vektor (all-MiniLM-L6-v2, 384-d) |

### LLM (Swappable via LLMClient Protocol)

| Client | Model Default | Model Fallback | Peran |
|---|---|---|---|
| OllamaClient (lokal) | `qwen2.5:3b` (dari .env) | `llama3.2:3b` | Explanation Agent — narasi Bahasa Indonesia & QA Panel |
| OllamaClient (lokal) | `qwen2.5:3b` (dari .env) | `llama3.2:3b` | Review Agent (primary) — structured evidence summary |
| OllamaClient (lokal) | `qwen2.5:3b` (dari .env) | - | Clinical Agent Lapis 2 |
| GeminiClient (API) | `gemini-2.0-flash` | - | Benchmark baseline & production-path narrative (opsional) |

> Catatan: Default kode mendefinisikan mistral:7b/deepseek-r1:7b/qwen2.5:7b, namun file `.env` aktual menggunakan `qwen2.5:3b` dan `llama3.2:3b` untuk hardware yang lebih ringan. Provider dapat dikonfigurasi via `LLM_PROVIDER=ollama|gemini`.

*Hardware Target Specification*: Intel Core 5 215H, 16GB RAM, RTX 5050 8GB VRAM. Model max 7B (Q4_K_M ~4.5-5GB VRAM + KV cache).

### Database & Storage

| Komponen | Teknologi | Peran |
|---|---|---|
| Relational DB | PostgreSQL | Tabel klaim, analisis, audit, keputusan manusia |
| Vector Store | LanceDB (file-based) | Embedding vektor 384-d untuk similarity search |

### Frontend

| Komponen | Teknologi | Versi | Peran |
|---|---|---|---|
| Framework | React | 19.2.8 | SPA |
| Build Tool | Vite | 8.2.0 | Dev server + bundler |
| Routing | React Router DOM | 7.18.2 | Client-side routing |
| HTTP Client | Axios | 1.19.0 | API calls ke backend |
| Charts | Recharts | 3.10.1 | SHAP bar chart, analytics |
| Icons | Lucide React | 1.31.0 | UI icons |
| Styling | Vanilla CSS (`index.css`) | — | Design system custom |

---

## 2. Struktur Direktori Workspace

```
E-Jak/
+-- backend/
¦   +-- app/
¦   ¦   +-- agents/                  # Multi-Agent Pipeline
¦   ¦   ¦   +-- orchestrator.py      # Pipeline controller utama (Phase 0-4) + FIFO queue bridge
¦   ¦   ¦   +-- clinical_agent.py    # INA-CBG Rule Engine + LLM Lapis 2
¦   ¦   ¦   +-- financial_engine.py  # XGBoost Regressor + SHAP Explainer + z-score fallback
¦   ¦   ¦   +-- fraud_agent.py       # LanceDB Similarity + Repeat Billing + Unbundling + IF + Graph
¦   ¦   ¦   +-- review_agent.py      # Multi-signal synthesis via LLM + rule-count fallback
¦   ¦   ¦   +-- risk_engine.py       # Deterministic risk scoring (non-LLM, 0-100)
¦   ¦   ¦   +-- explanation_agent.py # Indonesian narrative + validation + jargon sanitizer
¦   ¦   +-- api/
¦   ¦   ¦   +-- main.py              # FastAPI app, lifespan, semua endpoint
¦   ¦   ¦   +-- claims.py            # Claims CRUD router
¦   ¦   +-- core/
¦   ¦   ¦   +-- llm_client.py        # OllamaClient + GeminiClient + retry logic
¦   ¦   ¦   +-- human_language.py    # Label mapping teknis -> Bahasa Indonesia
¦   ¦   ¦   +-- public_analysis.py   # SSE data projection filter (tidak bocorkan internal)
¦   ¦   ¦   +-- errors.py            # Error codes & safe failure messages
¦   ¦   ¦   +-- versions.py          # ANALYSIS_VERSION constant
¦   ¦   +-- data/
¦   ¦   ¦   +-- ina_cbg_rules.py     # INA-CBG diagnosis labels, CBG mapping, tariff lookup
¦   ¦   +-- ml/
¦   ¦   ¦   +-- feature_engineering.py # Feature extraction (20 fitur full, 15 fitur cost)
¦   ¦   ¦   +-- similarity.py           # LanceDB embed + store + find_similar_claims (v3)
¦   ¦   ¦   +-- similarity_scoring.py   # Composite similarity formula + investigation filter
¦   ¦   ¦   +-- graph_metrics.py        # Provider network metrics (precomputed)
¦   ¦   ¦   +-- train_xgboost.py        # Training script XGBoost regressor
¦   ¦   ¦   +-- train_isolation_forest.py # Training script Isolation Forest
¦   ¦   +-- models/
¦   ¦   ¦   +-- schemas.py           # Pydantic schemas semua input/output agent
¦   ¦   ¦   +-- database.py          # SQLAlchemy models + migrate_schema() + DB trigger
¦   ¦   +-- services/
¦   ¦   ¦   +-- claim_queue.py       # ClaimQueueWorker (FIFO, heartbeat, recovery)
¦   ¦   +-- evaluation/              # Pipeline evaluation framework (P1)
¦   +-- models_trained/
¦       +-- xgboost_regressor.json   # Artifact XGBoost trained model
¦       +-- isolation_forest.pkl     # Artifact Isolation Forest trained model
¦       +-- evaluation_results.json  # Metrik evaluasi (Precision@K, PR-AUC)
¦       +-- p1_evaluation_results.json # Metrik evaluasi P1
+-- frontend/
¦   +-- src/
¦       +-- App.jsx                  # Routing + sidebar AEGIS
¦       +-- api.js                   # API client (axios)
¦       +-- humanLanguage.js         # Label mapping frontend
¦       +-- pages/
¦           +-- Dashboard.jsx        # Statistik agregat
¦           +-- ClaimsList.jsx       # Daftar klaim + filter
¦           +-- ClaimIntake.jsx      # Form input klaim manual
¦           +-- Investigation.jsx    # SSE timeline investigasi
¦           +-- Assessment.jsx       # Hasil analisis lengkap + human decision
¦           +-- Monitoring.jsx       # Status komponen sistem
¦           +-- MLEvaluation.jsx     # Metrik evaluasi ML
+-- docs/                            # Dokumentasi produk
+-- scripts/                         # Utility scripts (training, data generation)
+-- compose.yaml                     # Docker Compose (PostgreSQL)
+-- start.bat                        # Windows startup script
```

---

## 3. Database Schema (PostgreSQL)

### 3.1 Tabel `claims`

Tabel utama klaim. `received_at` dan `queue_sequence` bersifat **immutable** setelah INSERT (dijaga oleh DB trigger `claims_metadata_immutable`).

| Kolom | Tipe | Keterangan |
|---|---|---|
| `claim_id` | VARCHAR PK | ID unik klaim |
| `patient_id` | VARCHAR | ID pasien (pseudonymized) |
| `provider_id` | VARCHAR | ID faskes |
| `doctor_id` | VARCHAR | ID dokter |
| `diagnosis_primary` | VARCHAR | Kode ICD-10 diagnosis primer |
| `diagnosis_secondary` | VARCHAR | Kode ICD-10 sekunder (CSV) |
| `procedure_codes` | VARCHAR | Kode ICD-9-CM prosedur (CSV) |
| `severity_level` | INTEGER | Tingkat keparahan (1-4) |
| `cost_claimed` | FLOAT | Biaya yang diklaim (Rupiah) |
| `length_of_stay` | INTEGER | Hari rawat inap |
| `admission_date` | VARCHAR | Tanggal masuk (ISO string) |
| `discharge_date` | VARCHAR | Tanggal keluar (ISO string) |
| `medication_json` | VARCHAR | JSON list [{name, quantity}] |
| `referral_json` | VARCHAR | JSON ReferralInfo opsional |
| `cbg_group_claimed` | VARCHAR | Kode CBG yang diklaim (nullable) |
| `status` | VARCHAR | `pending|scanning|processed|review_required|failed|verified` |
| `risk_score` | FLOAT | Skor risiko (0-100), nullable |
| `priority_tier` | VARCHAR | `high|medium|low`, nullable |
| `human_decision` | VARCHAR | Keputusan verifier terakhir |
| `received_at` | TIMESTAMPTZ | Waktu klaim diterima (immutable, server_default) |
| `queue_sequence` | BIGINT | Nomor urut FIFO (immutable, dari sequence DB) |
| `analysis_started_at` | TIMESTAMPTZ | Waktu mulai analisis scanning |
| `analysis_heartbeat_at` | TIMESTAMPTZ | Heartbeat terakhir (untuk lease recovery) |
| `analyzed_at` | TIMESTAMPTZ | Waktu analisis selesai |
| `verified_at` | TIMESTAMPTZ | Waktu verifier submit keputusan |
| `analysis_attempts` | INTEGER | Jumlah percobaan analisis (maks 3) |
| `last_analysis_error` | VARCHAR | Pesan error terakhir (safe) |
| `last_analysis_error_code` | VARCHAR | Kode error terakhir |
| `analysis_generation` | VARCHAR | UUID generasi analisis saat ini |

### 3.2 Tabel `risk_analyses`

Hasil analisis per klaim. Jika `analysis_version` tidak cocok dengan `ANALYSIS_VERSION` aktual, klaim di-requeue.

| Kolom | Tipe | Keterangan |
|---|---|---|
| `claim_id` | VARCHAR PK | FK ke `claims.claim_id` |
| `clinical_score` | FLOAT | Skor komponen clinical rule flags |
| `financial_score` | FLOAT | Skor komponen financial anomaly |
| `fraud_score` | FLOAT | Skor komponen similarity fraud + IF |
| `similarity_score` | FLOAT | Max similarity klaim serupa |
| `total_score` | FLOAT | Skor risiko total (0-100) |
| `priority_tier` | VARCHAR | `high|medium|low` |
| `recommended_action` | VARCHAR | `verify_immediately|review_when_available|low_priority` |
| `actual_cost` | FLOAT | Biaya yang diklaim |
| `predicted_cost_upper` | FLOAT | Batas atas prediksi model (untuk exposure calc) |
| `analysis_version` | INTEGER | Versi engine analisis saat artifact dibuat |
| `evidence_json` | VARCHAR | JSON lengkap semua output agent + assessment |
| `created_at` | TIMESTAMPTZ | Waktu artifact dibuat |

### 3.3 Tabel `agent_runs`

Log eksekusi per-agent per-klaim.

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `claim_id` | VARCHAR | FK ke `claims.claim_id` |
| `agent_name` | VARCHAR | `clinical_agent|financial_agent|fraud_agent|review_agent|risk_engine|explanation_agent` |
| `status` | VARCHAR | `success|fallback|skipped|error` |
| `duration_ms` | INTEGER | Durasi eksekusi (ms) |
| `model_used` | VARCHAR | Nama model LLM yang digunakan (nullable untuk non-LLM agents) |
| `output_json` | VARCHAR | Output JSON agent |
| `timestamp` | TIMESTAMPTZ | Waktu eksekusi |

### 3.4 Tabel `audit_logs`

Audit trail setiap aksi penting pipeline.

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `claim_id` | VARCHAR | FK ke `claims.claim_id` |
| `agent_name` | VARCHAR | Siapa yang melakukan aksi |
| `action` | VARCHAR | Jenis aksi (mis. `hard_reject`, `analysis_complete`) |
| `timestamp` | TIMESTAMPTZ | Waktu aksi |
| `details` | VARCHAR | Keterangan tambahan (score, tier, partial, dll.) |

### 3.5 Tabel `human_decisions`

Rekaman keputusan verifier manusia.

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `claim_id` | VARCHAR | FK ke `claims.claim_id` |
| `decision` | VARCHAR | `Verified Valid|Needs Further Review|Escalate|Request Clarification` |
| `reviewer` | VARCHAR | ID/nama verifier |
| `analysis_generation` | VARCHAR | UUID generasi analisis saat keputusan diambil |
| `timestamp` | TIMESTAMPTZ | Waktu keputusan |

---

## 4. API Endpoint Reference

### Claims Management

| Method | Endpoint | Deskripsi |
|---|---|---|
| GET | `/api/claims` | List klaim dengan pagination, filter status dan tier |
| POST | `/api/claims` | Intake klaim baru (auto-queue ke FIFO) |
| GET | `/api/claims/{claim_id}` | Detail klaim + status antrian |
| DELETE | `/api/claims/{claim_id}` | Hapus klaim dan semua data terkait |
| GET | `/api/claims/{claim_id}/analysis` | Hasil analisis risk assessment |
| POST | `/api/claims/{claim_id}/decision` | Submit keputusan verifier manusia |
| GET | `/api/claims/{claim_id}/decision` | Ambil keputusan verifier terakhir |
| POST | `/api/claims/{claim_id}/reanalyze` | Paksa analisis ulang klaim |

### Analysis & Streaming

| Method | Endpoint | Deskripsi |
|---|---|---|
| POST | `/api/claims/analyze` | Start manual scan dengan SSE (return task_id) |
| GET | `/api/stream/{task_id}` | SSE stream event pipeline real-time |

### Analytics & Monitoring

| Method | Endpoint | Deskripsi |
|---|---|---|
| GET | `/api/analytics/dashboard` | Statistik agregat klaim dan financial exposure |
| GET | `/api/health` | Status real-time semua komponen sistem |
| GET | `/api/ml/eval` | Metrik evaluasi ML (Precision@K, PR-AUC) |
| GET | `/api/ml/eval/p1` | Metrik evaluasi P1 pipeline |

---

## 5. Analysis Pipeline Flow

```
POST /api/claims/analyze
        |
        v
[ClaimRecord.status = "scanning"]
[analysis_generation = UUID]
[asyncio.Task dibuat]
        |
        v
process_claim(claim, sse_queue, analysis_generation)
        |
        v
Phase 0: validate_deterministic()
  - field wajib check
  - tanggal sequence check
  - severity range check
  - cost > 0 check
  - exact duplicate DB check
        |
   hard_reject? -> emit "rejected", return RiskAssessment(rejected=True)
   duplicate? -> set exact_duplicate_of flag
        |
        v
Phase 1: asyncio.gather (paralel, masing-masing dengan run_with_fallback)
  +------------------+------------------+------------------+
  | clinical_agent   | financial_engine | fraud_agent      |
  | Rule Engine Lapis 1 | XGBoost + SHAP | LanceDB search   |
  | + LLM Lapis 2   | z-score fallback | + Repeat Billing  |
  | (kasus ambigu)   |                  | + Cloning check  |
  |                  |                  | + Unbundling     |
  |                  |                  | + Isolation Forest|
  |                  |                  | + Graph Metrics  |
  +------------------+------------------+------------------+
        |
        v
emit "phase1_complete" {clinical, financial, fraud, partial}
        |
        v
Phase 2: synthesize_review(claim, clinical, financial, fraud)
  - LLM menyintesis evidence lintas agent
  - Guard: strong_multi_signal hanya jika >= 2 sumber sinyal
  - Evidence IDs dibatasi pada yang dihitung deterministik
  - Fallback: rule_fallback jika LLM gagal
        |
        v
emit "phase2_complete" {review}
        |
        v
Phase 3: calculate_risk_score(clinical, financial, fraud, review)
  - Murni deterministik, non-LLM
  - Score = clinical(0-20) + financial(0-30) + fraud(0-20) + evidence_support(0-15)
  - priority_tier: high(>=60) | medium(25-59) | low(<25)
        |
        v
emit "phase3_complete" {risk}
        |
        v
Phase 4: generate_explanation(claim, clinical, financial, fraud, review, risk)
  - Low tier -> template deterministic langsung
  - LLM narasi Bahasa Indonesia
  - Validasi wajib angka narasi vs fakta sumber
  - Jargon sanitizer deterministik
  - recommended_action dari tier, bukan LLM
        |
        v
emit "phase4_complete" {explanation}
        |
        v
Persist ke PostgreSQL:
  - RiskAnalysisRecord (evidence_json + analysis_version)
  - AgentRunRecord per agent
  - AuditLogRecord
  - Update ClaimRecord.status + risk_score + priority_tier
        |
Index ke LanceDB (idempotent, untuk find_similar_claims berikutnya)
        |
        v
emit "status" step=complete
return RiskAssessment
```

---

## 6. FIFO Queue Worker Architecture

`ClaimQueueWorker` (`services/claim_queue.py`) adalah database-backed asyncio worker yang memastikan klaim diproses satu per satu secara FIFO.

```
FastAPI startup (lifespan)
        |
        v
ClaimQueueWorker.start()
  - recover_startup_claims() -> reset semua "scanning" jadi "pending"
  - asyncio.Task(run()) dimulai
        |
        v
run() loop:
  - Setiap 30 detik: recover_expired_leases() + recover_invalid_terminal_analysis()
  - process_next():
      1. _claim_next(): SELECT status=pending ORDER BY queue_sequence LIMIT 1 FOR UPDATE SKIP LOCKED
      2. Update status="scanning", analysis_generation=UUID, analysis_attempts++
      3. asyncio.Task heartbeat setiap 30 detik (update analysis_heartbeat_at)
      4. _run_orchestrator(claim, generation) -> process_claim()
      5. Sukses: _finish_success() -> status = review_required | processed
      6. Gagal: _finish_failure() -> status = pending (retry) | failed (maks)
      7. Stop heartbeat task
```

**Recovery Mechanism**:
- `recover_startup_claims()`: Saat restart, semua klaim "scanning" direset ke "pending".
- `recover_expired_leases()`: Klaim "scanning" tanpa heartbeat > 15 menit direset ke "pending".
- `recover_invalid_terminal_analysis()`: Klaim "processed/review_required" tanpa artifact analisis versi terkini direset ke "pending".

---

## 7. LLM Client Architecture

`llm_client.py` mengimplementasikan Protocol `LLMClient` dengan dua implementasi:

```
LLMClient (Protocol)
    |
    +-- OllamaClient (default, lokal)
    |     - POST /api/generate ke Ollama server
    |     - structured_call() dengan retry 2x + feedback error
    |     - model_available() untuk fallback model check
    |
    +-- GeminiClient (opsional, via API key)
          - POST ke Google Generative Language API
          - responseSchema untuk structured output
          - retry 2x dengan feedback error
```

**Retry Logic**: Setiap kegagalan parse JSON atau validasi Pydantic menghasilkan retry dengan feedback pesan error ke LLM (maks 2 retry = 3 percobaan total).

**Per-Agent Model Config** (dari environment variables):
- `CLINICAL_MODEL`: Default `mistral:7b`, aktual `.env` = `qwen2.5:3b`
- `REVIEW_MODEL`: Default `deepseek-r1:7b`, aktual `.env` = `qwen2.5:3b`
- `REVIEW_MODEL_FALLBACK`: Default `mistral:7b`, aktual `.env` = `llama3.2:3b`
- `EXPLANATION_MODEL`: Default `qwen2.5:7b`, aktual `.env` = `qwen2.5:3b`
- `EXPLANATION_MODEL_FALLBACK`: Default `mistral:7b`, aktual `.env` = `llama3.2:3b`

---

## 8. Vector Store Architecture (LanceDB v3)

Tabel vektor: `claims_vectors_v3` di `backend/app/lancedb_data/`.

**Schema**:
- `claim_id` (str), `patient_id` (str), `provider_id` (str), `doctor_id` (str)
- `diagnosis_primary` (str), `cost_claimed` (float), `admission_date` (str)
- `vector` (Vector(384)), `text_content` (str)

**Embedding**: `all-MiniLM-L6-v2` mengubah teks medis klaim (diagnosis + prosedur + obat) menjadi 384-dimensional normalized vector.

**Startup Backfill**: Saat server startup, `embed_and_store()` dipanggil untuk semua klaim di DB (idempotent — klaim yang sudah ter-index dilewati).

---

## 9. Referensi Dokumen Terkait

- [PRD.md](./PRD.md) — Spesifikasi kebutuhan produk dan functional requirements.
- [BusinessCore.md](./BusinessCore.md) — Logika domain bisnis JKN, INA-CBG, dan strategi mitigasi.
- [AgentWorkflow.md](./AgentWorkflow.md) — Detail alur pipeline multi-agent dan protokol SSE.
- [MODELS.md](./MODELS.md) — Spesifikasi teknis model ML, Vector Store, Graph Metrics, dan LLM.
