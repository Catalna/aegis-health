# MODELS.md — Machine Learning, Vector Store, Graph & LLM Models Specification

> **J-ARI: JKN Agentic Risk Intelligence**  
> Nama Frontend: **AEGIS — Pusat Pemeriksaan Klaim**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 3.0  
> Status: Aktual — Disinkronkan dengan implementasi kode (`backend/models_trained/`, `core/`, `agents/`) (Oktober 2026)

---

## 1. Overview Ekosistem Model

J-ARI/AEGIS menerapkan arsitektur **Multi-Model Intelligence** terpadu. Pendekatan ini menggabungkan machine learning terawasi (supervised), pembelajaran tanpa pengawasan (unsupervised), pencarian kesamaan vektor semantik (vector similarity), analitik jaringan graf (graph metrics), heuristik domain perasuransian INA-CBG, serta Large Language Models (LLM) dengan pembagian tugas yang terisolasi secara ketat.

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
   (Expected Reimbursement)     (Behavioral Context)         (Repeat/Cloning/Unbundling)
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
                           (Max 85 Poin Cap, non-LLM)
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
- **Tujuan**: Menghasilkan estimasi *expected reimbursement benchmark* untuk suatu episode klaim berdasarkan profil klinis dan tipe fasilitas kesehatan.
- **Peran Sistem**: Model ini berfungsi sebagai benchmark pembanding statistik terhadap pola klaim historis, bukan sebagai grouper tarif resmi INA-CBG dari Kemenkes.
- **Lokasi File Model**: `backend/models_trained/xgboost_regressor.json`.

### 2.2 Feature Engineering Pipeline (`backend/app/core/feature_engineering.py`)
Untuk mencegah terjadinya kebocoran target (*target leakage*), ekstraksi fitur dipisahkan secara tegas:
1. **`FEATURE_NAMES` (20 Fitur)**: Seluruh fitur termasuk rasio biaya, digunakan untuk analisis eksplorasi & model unsupervised.
2. **`COST_FEATURE_NAMES` (15 Fitur)**: Fitur yang diekstraksi **tanpa menyertakan biaya klaim** (`cost_claimed`) untuk model regresi biaya estimasi.

#### Daftar 15 Fitur Input Regresi Biaya (`COST_FEATURE_NAMES`):
1. `los`: Lama rawat inap dalam hari (`(discharge_date - admission_date).days`).
2. `patient_age`: Usia pasien pada saat episode pelayanan.
3. `severity_level`: Tingkat keparahan kasus (ordinal: 1, 2, 3, 4).
4. `procedure_count`: Jumlah tindakan/prosedur medis yang ditagihkan.
5. `secondary_diagnosis_count`: Jumlah diagnosis sekunder yang menyertai diagnosis primer.
6. `faskes_type_enc`: One-hot/label encoding tipe faskes (RS Kelas A, B, C, D, Klinik, Puskesmas).
7. `service_type_enc`: Encoding jenis rawat (Rawat Inap vs Rawat Jalan Tingkat Lanjut).
8. `gender_enc`: Jenis kelamin pasien (Laki-laki / Perempuan).
9. `icd10_chapter`: Klasifikasi bab penyakit ICD-10 (misal: Bab IX Sirkulasi, Bab II Neoplasma).
10. `ina_cbg_base_rate`: Tarif dasar rata-rata historis untuk kelompok kode INA-CBG tersebut.
11. `faskes_region_enc`: Regionalisasi tarif sesuai regulasi wilayah BPJS.
12. `icu_indicator`: Boolean indikator perawatan di ruang intensif (ICU/ICCU/PICU/NICU).
13. `ventilator_used`: Boolean penggunaan alat bantu pernapasan mekanis.
14. `surgical_indicator`: Boolean prosedur bedah mayor/minor.
15. `comorbidity_index`: Indeks komorbiditas berbasis pembobotan diagnosis sekunder.

### 2.3 Pelatihan & Metrik Evaluasi Model (`train_xgboost.py`)
- **Dataset Latih**: Data klaim historis sintetis terstandardisasi yang mencerminkan distribusi klaim JKN.
- **Hyperparameters**:
  - `max_depth`: 6
  - `learning_rate`: 0.05
  - `n_estimators`: 250
  - `subsample`: 0.8
  - `colsample_bytree`: 0.8
  - `objective`: `reg:squarederror`
- **Metrik Kinerja**:
  - **R² Score**: $\ge 0.84$ pada test set.
  - **MAE (Mean Absolute Error)**: $\le 8.5\%$ terhadap rata-rata biaya klaim.
  - **RMSE**: Terkalibrasi untuk meminimalkan deviasi pada kasus berbiaya katastropik.

### 2.4 Explainability via SHAP (SHapley Additive exPlanations)
Financial Engine (`backend/app/core/financial_engine.py`) mengintegrasikan `shap.TreeExplainer` untuk membedah kalkulasi deviasi biaya secara transparan:
- **Baseline Value ($E[f(x)]$ )**: Estimasi biaya rata-rata populasi klaim sejenis.
- **SHAP Values per Klaim**: Kontribusi marjinal masing-masing dari 15 fitur terhadap kenaikan atau penurunan estimasi biaya.
- **Ekstraksi Sinyal Penjelas**:
  - **Top 3 Positive Cost Drivers**: Faktor yang paling mendorong kenaikan biaya wajar (misal: `severity_level = 3`, `icu_indicator = 1`, `los = 12`).
  - **Top 3 Negative Cost Drivers**: Faktor yang seharusnya menekan biaya (misal: rawat jalan, usia muda, prosedur non-bedah).
  - Jika `cost_claimed` jauh melampaui `expected_reimbursement` tanpa didukung oleh SHAP positive drivers yang valid, sistem mencatat indikasi kuat *inflated bill* atau *upcoding*.

---

## 3. Unsupervised Machine Learning: Isolation Forest & Provider Graph

### 3.1 Isolation Forest Model (`backend/app/core/isolation_forest.py`)
- **Tujuan**: Mendeteksi pencilan (*outliers*) multivariat yang tidak tertangkap oleh batasan aturan deterministik sederhana.
- **Lokasi File Model**: `backend/models_trained/isolation_forest.joblib`.
- **Konfigurasi Pelatihan**:
  - `n_estimators`: 100 pohon isolasi.
  - `contamination`: 0.05 (asumsi 5% klaim memiliki karakteristik distribusi anomali ekstrim).
  - `features`: 20 dimensi fitur numerik & ter-encode (`FEATURE_NAMES`).
- **Skor Output**: `anomaly_score` bernilai kontinu antara $-1.0$ (sangat anomali) hingga $+1.0$ (sangat normal).
- **Peran dalam Arsitektur**: Skor ini **tidak digunakan sebagai vonis tunggal**, melainkan sebagai sinyal konteks pendukung (*behavioral context signal*) untuk agen Fraud dan Review.

### 3.2 Provider & Doctor Graph Network Metrics (`backend/app/core/graph_metrics.py`)
- **Topologi Graf**: Graf bipartite berbobot yang menghubungkan entitas **Faskes (Provider)** $\leftrightarrow$ **Dokter DPJP** $\leftrightarrow$ **Pasien**.
- **Metrik yang Dihitung**:
  1. **Degree Centrality**: Rasio klaim per dokter dalam suatu periode.
  2. **Referral Concentration Index (Herfindahl-Hirschman Index)**: Tingkat konsentrasi rujukan pasien ke provider tertentu.
  3. **High-Frequency Bipartite Clusters**: Deteksi pola *loop rujukan* tidak wajar atau konsentrasi klaim tidak biasa pada jam kerja dokter tertentu.
- **Indikator Risiko Graf**: Skor normalisasi 0.0 – 1.0 yang merefleksikan tingkat anomali jaringan relasional fasilitas kesehatan.

---

## 4. Vector Store & Multi-Factor Composite Similarity (LanceDB)

### 4.1 Vector Store Engine (`backend/app/core/similarity.py`)
- **Teknologi**: **LanceDB** — database vektor nir-server berbasis format data kolumnar Lance yang sangat cepat dan hemat memori.
- **Model Embedding**: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensi).
- **Entri Vektor**: Representasi teks terstruktur dari kombinasi diagnosis primer, diagnosis sekunder, deskripsi prosedur, dan ringkasan tindakan medis per klaim.
- **Metrik Jarak**: Cosine Distance ($1 - \text{Cosine Similarity}$).

### 4.2 Formulasi Komposit Multi-Faktor Similarity Score (`similarity_scoring.py`)
Untuk membedakan antara kesamaan penyakit yang wajar dengan pola kecurangan terorganisir (seperti *cloning klaim* atau *unbundling*), sistem menghitung **Skor Kemiripan Komposit**:

$$S_{composite} = 0.35 \times S_{semantic} + 0.25 \times S_{clinical} + 0.20 \times S_{temporal} + 0.20 \times S_{provider}$$

Di mana:
1. **$S_{semantic}$ (35%)**: Cosine similarity antara vektor embedding deskripsi klinis klaim baru terhadap klaim-klaim historis dalam LanceDB.
2. **$S_{clinical}$ (25%)**: Kesamaan eksak kode ICD-10 primer, kode ICD-9-CM prosedur, dan kelas tarif INA-CBG.
3. **$S_{temporal}$ (20%)**: Kedekatan waktu pelayanan antar dua klaim:
   - Tanggal pelayanan identik atau selisih $\le 3$ hari: $S_{temporal} = 1.0$.
   - Selisih $4 - 14$ hari: $S_{temporal} = 0.6$.
   - Selisih $> 30$ hari: $S_{temporal} = 0.0$.
4. **$S_{provider}$ (20%)**: Asal fasilitas kesehatan:
   - Provider sama & dokter DPJP sama: $S_{provider} = 1.0$.
   - Provider sama & dokter beda: $S_{provider} = 0.7$.
   - Provider beda: $S_{provider} = 0.1$.

### 4.3 Kriteria Deteksi Fraud Relasional
- **Claim Cloning Suspect**: $S_{composite} \ge 0.90$ dengan pasien yang berbeda tetapi rincian tindakan dan waktu pelayanan sangat identik.
- **Repeat Billing Suspect**: $S_{composite} \ge 0.85$ dengan pasien yang sama pada fasilitas yang sama dalam jendela waktu $< 30$ hari untuk episode yang seharusnya tuntas dalam 1 kali perawatan.
- **Unbundling Suspect**: Beberapa klaim terpisah diajukan dalam rentang 1–3 hari untuk prosedur yang menurut pedoman INA-CBG seharusnya disatukan dalam satu paket tagihan.

---

## 5. Domain Rule Engine: INA-CBG Consistency Heuristic & Risk Scoring

### 5.1 Matriks Aturan Domain (`backend/app/agents/clinical_agent.py`)
Menerapkan regulasi teknis petunjuk operasional INA-CBG:
1. **Aturan Kompatibilitas Prosedur vs Diagnosis**:
   - Contoh: Tindakan operasi mata (Katarak) tidak boleh diajukan dengan diagnosis primer penyakit dalam non-oftalmologi tanpa diagnosis sekunder mata.
2. **Batas Wajar Length of Stay (LOS)**:
   - Prosedur rawat jalan (ODS - One Day Surgery) yang ditagihkan sebagai rawat inap $> 3$ hari ditandai sebagai anomali *prolonged LOS*.
3. **Heuristik Severity Level vs Comorbidity/Complication (CC/MCC)**:
   - Klaim dengan Severity Level 3 atau 4 yang tidak mencantumkan diagnosis sekunder yang masuk daftar komplikasi mayor resmi ditandai sebagai indikasi *upcoding*.

### 5.2 Komposisi Skor Risiko Deterministik (`backend/app/agents/risk_engine.py`)

Skor adalah poin risiko mentah, **bukan probabilitas**, pada rentang `0–85`. Maksimum berasal dari komponen kode: aturan klinis `20` + anomali finansial `30` + relasional `20` + dukungan evidence `15`; konteks Isolation Forest bernilai `0` pada runtime. Deviasi finansial disimpan bertanda, sementara `upward_exposure` hanya mengukur selisih klaim di atas benchmark dan bukan bukti kelebihan bayar.

- Skor dihitung tanpa intervensi LLM. Field `max_score=85` dan UI menampilkan skala tersebut.
- Tier runtime: High `>=60`, Medium `>=25`, Low `<25` poin.
- Bukti exact duplicate memberi tier minimum High; cloning atau repeat billing yang terdeteksi memberi tier minimum Medium. Lantai tier tidak mengubah total poin.

### 5.3 Priority Tiering
Gunakan ambang runtime pada bagian 5.2 dan lantai tier untuk bukti relasional kuat. Tier adalah prioritas verifikasi, bukan konfirmasi fraud atau keputusan penolakan klaim.

---

## 6. Large Language Models (LLM) Ecosystem & Protocol

### 6.1 Abstraksi Terpadu (`backend/app/core/llm_client.py`)
Sistem mengisolasi seluruh interaksi LLM melalui antarmuka `LLMClient`:

```python
class LLMClient:
    async def generate_response(self, prompt: str, system_prompt: str = None) -> str:
        # 1. Coba Ollama Local (jika USE_OLLAMA=true)
        # 2. Fallback ke Gemini API (jika GEMINI_API_KEY tersedia)
        # 3. Fallback ke Heuristic Rule-Based Template jika kedua LLM gagal
```

### 6.2 Konfigurasi Model LLM per Environment

| Lingkungan | Model Chat / Copilot | Model Deep Reasoning (Phase 2) | Fallback Otomatis |
|---|---|---|---|
| **Lokal (Ollama)** | `mistral:7b` (default port 11434) | `deepseek-r1:7b` | Heuristic Template |
| **Cloud / Hybrid** | `gemini-2.5-flash` | `gemini-2.5-flash` / `gemini-2.0-flash` | Heuristic Template |
| **Offline / Minimal** | Heuristic Template | Heuristic Template | None (Selalu Berhasil) |

### 6.3 Batasan Ketat Penggunaan LLM:
1. **LLM DILARANG menentukan skor risiko numeric**: Skor risiko 100% dihitung oleh formula matematika `risk_engine.py`.
2. **LLM DILARANG mengubah status klaim**: Keputusan verifikasi (Approve/Reject/Clarify) hanya dapat dibuat oleh manusia atau gerbang validasi Phase 0.
3. **Peran LLM Terbatas Pada**:
   - Mensintesis bukti lintas-agen ke dalam narasi kronologis.
   - Merangkum temuan teknis ke dalam Bahasa Indonesia yang formal dan mudah dipahami.
   - Memberikan rekomendasi langkah investigasi kepada verifier.
   - Menjawab pertanyaan verifier interaktif pada AI Copilot.

---

## 7. Referensi Dokumen Terkait

- [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md): Dokumen Kebutuhan Produk J-ARI / AEGIS.
- [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md): Arsitektur Teknis dan Alur Data.
- [AgentWorkflow.md](file:///c:/Users/Radith/E-Jak/docs/AgentWorkflow.md): Alur Investigasi Multi-Agent dan SSE Protocol.
- [BusinessCore.md](file:///c:/Users/Radith/E-Jak/docs/BusinessCore.md): Logika Bisnis Domain Perasuransian JKN.
- [API.md](file:///c:/Users/Radith/E-Jak/docs/API.md): Dokumentasi REST API dan Payload SSE.
