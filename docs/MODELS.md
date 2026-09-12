# Models.md — Machine Learning, Vector Store, Graph & LLM Models Specification

> **J-ARI: JKN Agentic Risk Intelligence**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 1.0  
> Status: Prototype Model Specification

---

## 1. Overview Ekosistem Model

J-ARI memanfaatkan arsitektur **Multi-Model Intelligence** yang menggabungkan model Machine Learning Supervised, Unsupervised Anomaly Detection, Vector Store Embedding Similarity, Graph Network Analytics, Rule Engine INA-CBG, serta Large Language Models (LLM).

```
                      +----------------------------------+
                      |         KLAIM MASUK (JSON)       |
                      +----------------+-----------------+
                                       |
          +----------------------------+----------------------------+
          |                            |                            |
          v                            v                            v
  [ Supervised ML ]            [ Unsupervised ML ]          [ Vector Store & Graph ]
  XGBoost Regressor            Isolation Forest             LanceDB (384-d Embedding)
  + SHAP TreeExplainer         + Graph Centrality           + Composite Similarity
   (Expected Reimbursement)     (Supporting Context)         (Repeat/Cloning/Unbundling)
          |                            |                            |
          +----------------------------+----------------------------+
                                       |
                                       v
                            [ Domain Rule Engine ]
                            INA-CBG Consistency Heuristic
                            + Severity & Benchmark Rules
                                       |
                                       v
                           [ Deterministic Risk Score ]
                           Pure Mathematical Weighting
                                       |
                                       v
                           [ Large Language Models ]
                           Ollama Local / Gemini API
                           (Sintesis Bukti & Narasi BI)
```

---

## 2. Supervised Machine Learning: Cost Anomaly Model (XGBoost + SHAP)

### 2.1 Deskripsi Model
- **Algoritma**: **XGBoost Regressor** (`xgboost.XGBRegressor`).
- **Tujuan**: Mengestimasi *expected reimbursement benchmark* untuk suatu episode klaim berdasarkan profil medis dan karakteristik fasilitas kesehatan. Model ini bukan official INA-CBG grouper dan tidak menyatakan biaya medis yang benar.
- **File Artifact**: `backend/app/models_trained/xgboost_cost_model.joblib`.

### 2.2 Feature Engineering Pipeline (`feature_engineering.py`)
Fitur-fitur yang diekstraksi dari data klaim terstruktur:

| Nama Fitur | Tipe Data | Deskripsi & Transformasi |
|---|---|---|
| `severity_level` | Integer | Tingkat keparahan rawat (1 - 4). |
| `length_of_stay` | Integer | Lama hari rawat inap. |
| `num_secondary_diag` | Integer | Jumlah diagnosis sekunder/komplikasi (`len(diagnosis_secondary)`). |
| `num_procedures` | Integer | Jumlah kode tindakan/prosedur (`len(procedure_codes)`). |
| `num_medications` | Integer | Jumlah jenis obat yang diresepkan (`len(medication)`). |
| `is_high_risk_diag` | Binary (0/1) | Flag jika diagnosis primer/sekunder mengandung kode risiko upcoding (A41.9, Z87.39, E46). |
| `is_high_cost_proc` | Binary (0/1) | Flag jika terdapat prosedur berbiaya tinggi. |
| `diagnosis_primary_enc` | Categorical | Target/Label Encoding untuk diagnosis utama ICD-10. |
| `provider_type_enc` | Categorical | One-Hot Encoding tipe Faskes (RS Tipe A/B/C/D, Klinik, Puskesmas). |

### 2.3 Pelatihan & Evaluasi Model (`train_xgboost.py`)
- **Fungsi Target**: `log1p(cost_claimed)` pada klaim normal sintetis. Ini adalah benchmark prototype terhadap claimed amount, bukan label harga medis yang benar.
- **Hyperparameter Utama**:
  - `n_estimators`: 200
  - `max_depth`: 6
  - `learning_rate`: 0.05
  - `subsample`: 0.8
  - `colsample_bytree`: 0.8
- **Metrik Performance (Evaluasi Held-Out Test Set)**:
  - **MAE (Mean Absolute Error)**: $\le 850.000$ IDR.
  - **RMSE**: Terukur pada skala logaritmik $\le 0.25$.
  - **$R^2$ Score**: $\ge 0.88$.

### 2.4 Explainability via SHAP (SHapley Additive exPlanations)
- **Explainer**: `shap.TreeExplainer(xgboost_model)`.
- **Penggunaan dalam Sistem**:
  - Menghitung kontribusi marginal setiap fitur terhadap deviasi estimasi biaya.
  - Mengambil 3 fitur dengan kontribusi absolut terbesar (`shap_top_features`).
  - Menyediakan terjemahan label ramah pengguna untuk Verifier (misal: `"length_of_stay"` $\rightarrow$ *"Lama rawat 12 hari meningkatkan estimasi biaya sebesar Rp 3.200.000"*).

---

## 3. Unsupervised Machine Learning: Isolation Forest & Provider Graph

### 3.1 Isolation Forest Model (`train_isolation_forest.py`)
- **Algoritma**: `sklearn.ensemble.IsolationForest`.
- **Tujuan**: Mendeteksi pencilan multidimensi (*multivariate outliers*) secara independen tanpa bergantung pada label historis.
- **File Artifact**: `backend/app/models_trained/isolation_forest.joblib`.
- **Hyperparameter**:
  - `n_estimators`: 150
  - `contamination`: 0.05 (asumsi 5% anomali pada populasi klaim)
  - `random_state`: 42
- **Normalisasi Skor**: Decision function di-scale ke rentang `0.0 - 1.0` (`isolation_forest_score`).

### 3.2 Provider Graph Network Metrics (`graph_metrics.py`)
- **Tujuan**: Memodulasi skor anomali klaim individual berdasarkan pola perilaku kolektif jaringan Faskes/Dokter.
- **Metrics yang Dikalkulasi**:
  1. **Degree Centrality**: Tingkat keterhubungan Faskes dengan dokter dan pasien.
  2. **Clustering Coefficient**: Kerapatan kluster klaim Faskes.
- **Faktor Pengali Risk Engine**:
  $$\text{provider\_factor} = 0.7 + \left(0.3 \times \min\left(1.0, \text{graph\_cluster\_anomaly\_score}\right)\right)$$
  Faskes dengan pola grafik mencurigakan menaikkan bobot anomali Isolation Forest hingga 30% lebih tinggi.

---

## 4. Vector Store & Multi-Factor Composite Similarity (LanceDB)

### 4.1 Vector Store Engine (`similarity.py`)
- **Teknologi**: **LanceDB** (Embedded Vector Database, file-based tanpa server terpisah).
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense vectors).
- **Lokasi Penyimpanan**: `backend/app/lancedb_data/claims_index`.

### 4.2 Formulasi Komposit Multi-Faktor Similarity Score
Untuk mendeteksi *cloning* dan *repeat billing* secara akurat, sistem **tidak hanya menggunakan cosine similarity vector**, melainkan menggabungkannya menjadi skor komposit:

$$\text{Similarity Komposit} = 0.40 \cdot S_{\text{code}} + 0.30 \cdot S_{\text{cost}} + 0.15 \cdot I_{\text{provider}} + 0.10 \cdot S_{\text{time}} + 0.05 \cdot I_{\text{patient}}$$

Di mana:
- $S_{\text{code}}$: Indeks Jaccard kemiripan kode diagnosis & prosedur ($0.0 - 1.0$).
- $S_{\text{cost}}$: Kedekatan rasio nilai biaya klaim ($\exp(-\frac{|\text{cost}_1 - \text{cost}_2|}{\text{cost}_1})$).
- $I_{\text{provider}}$: Matriks biner (1.0 jika Provider ID sama, 0.0 jika beda).
- $S_{\text{time}}$: Fungsi peluruhan waktu berdasarkan selisih hari tanggal pelayanan.
- $I_{\text{patient}}$: Matriks biner (1.0 jika Patient ID sama, 0.0 jika beda).

### 4.3 Logika Klasifikasi Kecurangan Fraud Agent
- **Cloning Flag**: Similarity Komposit $\ge 0.85$ **DAN** Provider SAMA **DAN** Pasien BERBEDA. *(Sangat mirip antar-pasien beda di RS yang sama menunjukkan indikasi penyalinan berkas klaim)*.
- **Repeat Billing Flag**: Match persis pada (Pasien, Prosedur, Rentang Waktu) yang sudah terbayar.
- **Unbundling Flag**: Deteksi klaim terpisah dari provider/pasien sama dalam kurun waktu `< 7 hari` dengan kombinasi prosedur yang seharusnya menyatu pada satu paket CBG.

---

## 5. Domain Rule Engine: INA-CBG Consistency Heuristic

### 5.1 Matriks Aturan Domain & Bobot Skor Risiko
Aturan deterministik berbasis domain kesehatan JKN yang dievaluasi oleh `clinical_agent.py`. Pemetaan ini adalah heuristic prototype dan harus divalidasi terhadap referensi grouper resmi sebelum operasional.

| Kode Rule Flag | Deskripsi Aturan | Bobot Skor (`risk_engine.py`) |
|---|---|---|
| `tariff_deviation_extreme` | Claimed amount $> 100\%$ di atas reimbursement benchmark | Evidence reimbursement, bukan clinical point |
| `unsupported_high_risk_proc` | Prosedur berbiaya tinggi tidak sesuai dengan diagnosis primer | +8.0 Poin |
| `tariff_deviation_high` | Claimed amount $> 50\%$ di atas reimbursement benchmark | Evidence reimbursement, bukan clinical point |
| `severity_proc_mismatch` | Severity Level $\ge 3$ tanpa ada prosedur tindakan pendukung | +5.0 Poin |
| `upcoding_risk_diag` | Diagnosis sekunder berisiko upcoding (A41.9, Z87.39, E46) pada Severity $\ge 3$ | +4.0 Poin |
| `severity_med_mismatch` | Severity Level $\ge 3$ dengan jumlah jenis obat $< 2$ | +3.0 Poin |
| `los_outlier` | Length of Stay $> 2\times$ batas atas rata-rata klinis diagnosis | +2.0 Poin |

### 5.2 Kontrak Scoring Deterministik

- `evidence_support` menggantikan `synthesis_confidence` dan dihitung dari keluarga evidence deterministik, bukan dari level atau narasi LLM.
- Deviasi tarif hanya masuk keluarga `reimbursement_benchmark`; deviasi tersebut tidak dihitung ulang sebagai clinical point.
- Isolation Forest dan provider context ditampilkan sebagai `behavioral_context` dan tidak menambah evidence support pada prototype ini.
- Similarity biasa tidak menambah skor. Hanya repeat billing, cloning, atau unbundling yang dapat menjadi `relational_pattern` evidence.
- Setiap evidence memiliki `evidence_id`, `source_family`, `signal_type`, nilai, dan penjelasan yang dapat ditelusuri.

---

## 6. Large Language Models (LLM) Ecosystem & Protocol

### 6.1 LLMClient Abstraction (`llm_client.py`)
Sistem menggunakan pola arsitektur **Protocol/Interface** untuk memungkinkan pertukaran model LLM secara transparan (*swappable LLM execution*):

```python
class LLMClient(Protocol):
    async def structured_call(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...
    async def list_models(self) -> list[str]: ...
```

### 6.2 Provider Implementations

#### 1. `OllamaClient` (Lokal - Primary Engine)
- **Koneksi**: REST API ke Ollama instance lokal (`http://localhost:11434`).
- **Skema Kuantisasi**: Q4_K_M (kebutuhan RAM/VRAM ~4.5 - 5.0 GB).
- **Retry Mechanism**: Maksimal 2x percobaan otomatis jika sintaks JSON/Pydantic schema mismatch.
- **Model Distribution**:
  - `qwen2.5:7b`: Explanation Agent — Penyusunan narasi Bahasa Indonesia & QA Panel.
  - `mistral:7b`: Clinical Agent Lapis 2 & Review Agent — Ekstraksi struktur & analisis implisit.
  - `deepseek-r1:7b`: Review Agent (Opsional) — Reasoning trace sintesis multi-bukti.
  - `qwen2.5:3b` / `llama3.2:3b`: Light Routing & Quick Validation.

#### 2. `GeminiClient` (API - Benchmark Baseline)
- **Koneksi**: Google Gemini REST API (`ai.google.dev`).
- **Penggunaan**: Evaluasi kualitas benchmark & pembanding narasi jalur produksi (*production-path narrative*). BUKAN menjadi ketergantungan wajib pada runtime demo lokal offline.

---

## 7. Referensi Dokumen Terkait
- [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md) — Spesifikasi kebutuhan produk.
- [AgentWorkflow.md](file:///c:/Users/Radith/E-Jak/docs/AgentWorkflow.md) — Alur kerja dan eksekusi pipeline multi-agent.
- [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md) — Cetak biru arsitektur teknis dan integrasi database.
- [BusinessCore.md](file:///c:/Users/Radith/E-Jak/docs/BusinessCore.md) — Aturan domain bisnis JKN dan penanganan upcoding.
