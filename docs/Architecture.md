# Architecture.md — J-ARI System Architecture

> **J-ARI: JKN Agentic Risk Intelligence**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 1.0  
> Status: System Architecture Specification  

---

## 1. Tech Stack Summary

### Backend

| Komponen | Teknologi | Versi | Peran |
|---|---|---|---|
| Framework API | FastAPI | 0.141.1 | REST API + SSE streaming |
| ASGI Server | Uvicorn (standard) | 0.52.3 | HTTP server + WebSocket |
| ORM / DB Driver | SQLAlchemy (asyncio) | 2.0.52 | Async ORM |
| DB Driver Async | asyncpg | 0.31.0 | PostgreSQL async driver |
| Schema Validation | Pydantic | 2.13.4 | I/O validation semua agent |
| SSE | sse-starlette | 3.4.8 | Server-Sent Events untuk investigation timeline |
| HTTP Client | httpx | 0.28.1 | Panggil Ollama API & Gemini API |
| Env Config | python-dotenv | 1.2.3 | Load .env |

### Machine Learning & Vector Store

| Komponen | Teknologi | Versi | Peran |
|---|---|---|---|
| Cost Anomaly | XGBoost | 3.2.0 | Prediksi biaya wajar vs peer group |
| Explainability | SHAP | 0.49.1 | Feature attribution (TreeExplainer) |
| Unsupervised Anomaly | scikit-learn (Isolation Forest) | 1.7.2 | Sinyal anomali kedua (independen) |
| Feature Engineering | pandas + numpy | 2.3.3 / 2.2.6 | Feature pipeline |
| Model Serialization | joblib | 1.5.3 | Save/load model artifacts |
| Data I/O | pyarrow | 25.0.1 | Format interchange LanceDB |
| Vector DB | LanceDB (embedded) | 0.37.1 | Similarity search tanpa server terpisah |
| Embedding Model | sentence-transformers | 5.7.0 | Encode klaim jadi vektor (`all-MiniLM-L6-v2`) |

### LLM (Swappable via LLMClient Protocol)

| Client | Model Target | Peran |
|---|---|---|
| OllamaClient (lokal) | qwen2.5:7b | Explanation Agent — narasi Bahasa Indonesia |
| OllamaClient (lokal) | mistral:7b | Clinical Agent Lapis 2 & Review Agent |
| OllamaClient (lokal) | qwen2.5:3b / llama3.2:3b | Routing sederhana & quick validation |
| OllamaClient (lokal) | deepseek-r1:7b | Review Agent — reasoning trace |
| GeminiClient (API) | Gemini Flash | Benchmark baseline + production-path narrative |

*Hardware Target Specification*: Intel Core 5 215H, 16GB RAM, RTX 5050 8GB VRAM. Model max 7B (Q4_K_M ~4.5-5GB VRAM + KV cache).

### Database & Storage

| Komponen | Teknologi | Peran |
|---|---|---|
| Relational DB | PostgreSQL | Tabel klaim, analisis, audit, keputusan manusia |
| Vector Store | LanceDB (file-based) | Embedding vektor 384-d untuk similarity search |
| Cache | Redis (opsional) | Tidak di-deploy default (hanya jika butuh profiling) |

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
├── backend/
│   ├── app/
│   │   ├── agents/              # Multi-Agent Pipeline (Python functions)
│   │   │   ├── orchestrator.py  # Pipeline controller utama (Phase 0 - Phase 4)
│   │   │   ├── clinical_agent.py# INA-CBG Rule Engine + LLM Lapis 2
│   │   │   ├── financial_engine.py # XGBoost Regressor + SHAP TreeExplainer
│   │   │   ├── fraud_agent.py   # LanceDB Similarity + Isolation Forest + Graph Metrics
│   │   │   ├── review_agent.py  # Cross-signal Synthesis (deepseek-r1 / mistral)
│   │   │   ├── risk_engine.py   # Perhitungan skor risiko deterministik (0-100)
│   │   │   └── explanation_agent.py # Narasi Bahasa Indonesia + QA Panel (qwen2.5)
│   │   ├── api/
│   │   │   ├── main.py          # FastAPI app + SSE stream + analytics
│   │   │   └── claims.py        # CRUD endpoints klaim & keputusan manusia
│   │   ├── core/
│   │   │   └── llm_client.py    # Protocol LLMClient + OllamaClient + GeminiClient
│   │   ├── data/
│   │   │   └── synthetic_generator.py # Dataset sintetis & ground truth anomalies
│   │   ├── ml/
│   │   │   ├── feature_engineering.py
│   │   │   ├── similarity.py    # LanceDB + sentence-transformers (all-MiniLM-L6-v2)
│   │   │   ├── graph_metrics.py # Precomputed provider graph metrics
│   │   │   ├── train_xgboost.py
│   │   │   └── train_isolation_forest.py
│   │   └── models/
│   │       ├── database.py      # SQLAlchemy ORM models (5 tabel utama)
│   │       └── schemas.py       # Pydantic schemas (I/O validasi agent)
│   ├── models_trained/          # Artifact model (joblib + eval JSON)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx              # Router + Layout Sidebar
│       ├── api.js               # Axios API wrapper
│       ├── pages/
│       │   ├── Dashboard.jsx
│       │   ├── ClaimsList.jsx
│       │   ├── ClaimIntake.jsx
│       │   ├── Investigation.jsx
│       │   ├── Assessment.jsx
│       │   ├── Monitoring.jsx
│       │   ├── DemoLoader.jsx
│       │   └── MLEvaluation.jsx
│       └── components/
├── scripts/
│   ├── train_all.py             # Script training semua model ML
│   └── smoke_test.py
├── docs/
│   ├── PRD.md                   # Spesifikasi Produk
│   ├── Architecture.md          # (Dokumen ini — Cetak Biru Arsitektur)
│   ├── BusinessCore.md          # Logika Bisnis & Domain INA-CBG
│   ├── AgentWorkflow.md         # Detail Pipeline Agent & SSE Protocol
│   └── Models.md                # Spesifikasi Model ML, Vector & LLM
├── seed_db.py
├── start.bat
└── .env
```

---

## 3. Database Schema (PostgreSQL & LanceDB)

### Tabel Relasional (SQLAlchemy ORM)

```
claims (ClaimRecord)
  claim_id          VARCHAR  PK
  patient_id        VARCHAR  (indexed)
  provider_id       VARCHAR  (indexed)
  doctor_id         VARCHAR
  diagnosis_primary VARCHAR
  diagnosis_secondary VARCHAR  (comma-separated)
  procedure_codes   VARCHAR  (comma-separated)
  severity_level    INTEGER  (1-4)
  cost_claimed      FLOAT
  length_of_stay    INTEGER
  cbg_group_claimed VARCHAR  (nullable)
  admission_date    VARCHAR  (ISO date string, nullable)
  discharge_date    VARCHAR  (ISO date string, nullable)
  medication_json   VARCHAR  (JSON list, nullable)
  referral_json     VARCHAR  (JSON ReferralInfo, nullable)
  status            VARCHAR  (pending | processed | verified)
  risk_score        FLOAT    (nullable)
  priority_tier     VARCHAR  (high | medium | low, nullable)
  human_decision    VARCHAR  (nullable)

risk_analyses (RiskAnalysisRecord)
  claim_id              VARCHAR  PK
  clinical_score        FLOAT
  financial_score       FLOAT
  fraud_score           FLOAT
  similarity_score      FLOAT
  total_score           FLOAT
  priority_tier         VARCHAR
  recommended_action    VARCHAR
  actual_cost           FLOAT    (nullable)
  predicted_cost_upper  FLOAT    (nullable)
  evidence_json         VARCHAR  (full analysis blob JSON)
  created_at            DATETIME

agent_runs (AgentRunRecord)
  id           INTEGER  PK (autoincrement)
  claim_id     VARCHAR  (indexed)
  agent_name   VARCHAR
  status       VARCHAR  (success | error | fallback | skipped)
  duration_ms  INTEGER
  model_used   VARCHAR  (nullable)
  output_json  VARCHAR
  timestamp    DATETIME

audit_logs (AuditLogRecord)
  id           INTEGER  PK (autoincrement)
  claim_id     VARCHAR  (indexed)
  agent_name   VARCHAR
  action       VARCHAR
  details      VARCHAR  (nullable)
  timestamp    DATETIME

human_decisions (HumanDecisionRecord)
  id           INTEGER  PK (autoincrement)
  claim_id     VARCHAR  (indexed)
  decision     VARCHAR  (Verified Valid | Needs Further Review | Escalate | Request Clarification)
  reviewer     VARCHAR
  timestamp    DATETIME
```

### Vector Store (LanceDB)

```
lancedb_data/claims_index
  claim_id     STRING
  vector       FIXED_SIZE_LIST[FLOAT, 384]   (all-MiniLM-L6-v2 embedding)
  provider_id  STRING
  diagnosis    STRING
  procedures   STRING
```

---

## 4. End-to-End System Topography

```
                        +-----------------+
                        |   BPJS Verifier  |
                        |   (Browser UI)   |
                        +--------+--------+
                                 |
              React SPA (Vite, port 5173)
                                 |
                    +------------+-------------+
                    |                          |
              REST API Calls              SSE Stream
              (Axios)                    (EventSource)
                    |                          |
              +-----------+           +-----------------+
              | FastAPI   |           | /api/stream/    |
              | Backend   |           | {task_id}       |
              | port 8000 |           +-----------------+
              +-----+-----+
                    |
     +--------------+--------------+
     |              |              |
PostgreSQL      LanceDB         Ollama
(klaim,         (vektor         (LLM lokal,
 analisis,       similarity)     port 11434)
 audit)
```

---

## 5. API Endpoints Summary

### Claims CRUD (`/api/claims`)

| Method | Path | Deskripsi |
|---|---|---|
| GET | `/api/claims` | List klaim dengan filter status, tier, search query, sorting, & paginasi |
| POST | `/api/claims` | Simpan klaim baru dari intake manual |
| GET | `/api/claims/{claim_id}` | Detail klaim tunggal |
| GET | `/api/claims/{claim_id}/analysis` | Hasil analisis tersimpan dari `risk_analyses` |
| DELETE | `/api/claims/{claim_id}` | Reset status klaim ke pending & hapus analisis |
| GET | `/api/claims/{claim_id}/decision` | Keputusan verifikasi manusia terbaru |
| POST | `/api/claims/{claim_id}/decision` | Submit keputusan verifikasi manusia |

### Investigation & SSE Stream

| Method | Path | Deskripsi |
|---|---|---|
| POST | `/api/claims/analyze` | Trigger analisis klaim — mengembalikan `task_id` UUID |
| GET | `/api/stream/{task_id}` | EventSource SSE stream progress investigasi real-time |

### Analytics & System Health

| Method | Path | Deskripsi |
|---|---|---|
| GET | `/api/health` | Status komponen nyata (PostgreSQL, Ollama, XGBoost, LanceDB, Graph) |
| GET | `/api/ml/eval` | Hasil evaluasi model riil pada held-out test set |
| GET | `/api/analytics/dashboard` | Agregat statistik (total klaim, distribusi tier, pending, potential savings) |
| POST | `/api/demo/generate` | Injeksi batch data sintetis ke DB |
| GET | `/api/demo/stream` | SSE stream progress generasi data sintetis |

---

## 6. Frontend Routing Specifications

| Path | Komponen | Deskripsi Page |
|---|---|---|
| `/` | `Dashboard.jsx` | Agregat statistik klaim, ringkasan tier risiko, & health status komponen. |
| `/claims` | `ClaimsList.jsx` | Priority Queue — daftar klaim berurutan risiko dengan filter lengkap. |
| `/investigate/:claimId` | `Investigation.jsx` | Real-time AI Investigation timeline (SSE event stream). |
| `/assessment/:claimId` | `Assessment.jsx` | Hasil Risk Score + Evidence breakdown + SHAP Chart + QA Panel + Form Keputusan. |
| `/monitoring` | `Monitoring.jsx` | Health monitoring komponen sistem (DB, Ollama, ML models). |
| `/ml-eval` | `MLEvaluation.jsx` | Halaman evaluasi metrik model ML riil (Precision, Recall, F1, PR-AUC, MAE, RMSE). |
| `/intake` | `ClaimIntake.jsx` | Form penginputan klaim manual. |
| `/demo-loader` | `DemoLoader.jsx` | Utility injector data demo sintetis. |

---

## 7. Referensi Dokumen Terkait
- [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md) — Product Requirement Document J-ARI.
- [BusinessCore.md](file:///c:/Users/Radith/E-Jak/docs/BusinessCore.md) — Logika Bisnis & Domain INA-CBG.
- [AgentWorkflow.md](file:///c:/Users/Radith/E-Jak/docs/AgentWorkflow.md) — Alur Pipeline Multi-Agent & Protokol SSE.
- [Models.md](file:///c:/Users/Radith/E-Jak/docs/Models.md) — Spesifikasi Model Machine Learning, Vector Store & LLM.
