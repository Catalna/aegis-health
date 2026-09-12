# AgentWorkflow.md — Multi-Agent Pipeline & Investigation Workflow

> **J-ARI: JKN Agentic Risk Intelligence**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 1.0  
> Status: Production Architecture Specification  

---

## 1. Overview Pipeline Agent

Pipeline analisis J-ARI (`orchestrator.py`) mengadopsi arsitektur **hybrid multi-stage agent pipeline** yang menggabungkan validasi deterministik, eksekusi agent paralel, sintesis lintas-sinyal, perhitungan skor deterministik, serta penjabaran narasi Bahasa Indonesia.

```
REQUEST: POST /api/claims/analyze  {ClaimInput}
                    |
                    v
          [task_id UUID dibuat]
          [asyncio.Queue dibuat]
          [Task background dimulai]
                    |
                    v
         process_claim(claim, sse_queue)
                    |
          +---------+---------+
          |                   |
    Phase 0: Validasi Deterministik (validate_deterministic)
          |
    mandatory fields check
    date sequence check
    severity range check
    cost > 0 check
    exact duplicate check (DB query)
          |
    +-----+------+
    |            |
  REJECT       PASS (atau DUPLICATE FLAG)
    |            |
  emit         Phase 1: Paralel (asyncio.gather via run_with_fallback)
  "rejected"     |
          +------+------+------+
          |             |      |
    Clinical         Financial  Fraud
    Agent            Engine     Agent
          |             |      |
    Rule Engine      XGBoost    LanceDB Vector
    INA-CBG          + SHAP     Similarity
    Grouper          Tree       + Repeat Billing
    + LLM Lapis 2    Explainer  + Cloning & Unbundling
    (mistral:7b)                + Isolation Forest x Graph
          |             |      |
          +------+------+------+
                 |
          Phase 2: Review Agent (synthesize_review)
          LLM: deepseek-r1:7b / mistral:7b
          Output: evidence_level + corroborating_signals + reasoning_narrative
                 |
          Phase 3: Risk Score Engine (calculate_risk_score)
          Deterministik (non-LLM) — Bobot 0 - 100
          Output: total_score + breakdown + priority_tier
                 |
          Phase 4: Explanation Agent (generate_explanation)
          LLM: qwen2.5:7b (Indonesian Narrative)
          Output: narrative_id + ranked_reasons + qa_panel
                 |
          Persist ke PostgreSQL (risk_analyses, agent_runs, audit_logs)
          Update claims.status = "processed" & Index ke LanceDB
                 |
          emit "done" -> Stream SSE Selesai
```

---

## 2. Rincian Fase Eksekusi Pipeline

### Phase 0: Deterministic Validation Gate (`validate_deterministic`)
Sebelum agent berbasis ML/LLM diaktifkan, klaim melewati gerbang deterministik untuk menyaring kesalahan data dasar atau duplikasi sempurna:
1. **Field Mandatory Check**: `claim_id`, `patient_id`, `provider_id`, `diagnosis_primary`.
2. **Date Sequence Check**: `discharge_date >= admission_date`.
3. **Severity & Cost Bounds Check**: `1 <= severity_level <= 4` dan `cost_claimed > 0`.
4. **Exact Duplicate Lookup**: Memeriksa apakah terdapat klaim lain di PostgreSQL dengan `patient_id`, `diagnosis_primary`, `cost_claimed`, `diagnosis_secondary`, dan `procedure_codes` yang 100% identik.
   - Jika *exact duplicate* terdeteksi: Klaim **TIDAK ditolak**, melainkan ditandai `exact_duplicate=True` dan langsung mengaktifkan Fraud Agent untuk penanganan khusus repeat/cloning billing.

### Phase 1: Parallel Screening Agents (`asyncio.gather`)
Tiga agent utama dijalankan secara paralel asynchronously untuk efisiensi waktu respon:

#### 1. Clinical Agent (`clinical_agent.py`)
- **Fungsi**: Memeriksa konsistensi medis dan kesesuaian tarif prospektif INA-CBG.
- **Logika Deterministik (Lapis 1)**:
  - Mengonsultasikan diagnosis & prosedur ke *INA-CBG Simplified Grouper*.
  - Pengecekan aturan `rule_flags`:
    - `tariff_deviation_extreme`: Biaya diklaim `> 100%` di atas tarif referensi.
    - `tariff_deviation_high`: Biaya diklaim `> 50%` di atas tarif referensi.
    - `severity_proc_mismatch`: Severity level `>= 3` tanpa prosedur tindakan pendukung.
    - `severity_med_mismatch`: Severity level `>= 3` dengan jumlah jenis obat `< 2`.
    - `upcoding_risk_diag`: Diagnosis sekunder berisiko upcoding (misal: A41.9, Z87.39, E46) pada severity `>= 3`.
    - `los_outlier`: LOS `> 2x` batas atas rata-rata klinis.
    - `unsupported_high_risk_proc`: Prosedur berbiaya tinggi yang tidak mendukung konteks diagnosis.
- **Analisis LLM (Lapis 2 - `mistral:7b`)**: Jika data klaim tidak ditemukan pada tabel grouper statis, LLM Lapis 2 dipanggil untuk menilai plausibilitas klinis secara kontekstual.

#### 2. Financial Engine (`financial_engine.py`)
- **Fungsi**: Memprediksi biaya wajar (*fair cost baseline*) dan mendeteksi anomali finansial.
- **Model ML**: Regresi **XGBoost** terlatih (menggunakan fitur diagnosis, severity, LOS, tipe provider).
- **SHAP Feature Attribution**: Menggunakan **SHAP TreeExplainer** untuk mengidentifikasi 3 fitur teratas yang menaikkan/menurunkan perkiraan biaya (`shap_top_features`).
- **Deviasi & Anomali**:
  - `deviation_pct` = `((cost_claimed - predicted_cost) / predicted_cost) * 100`.
  - `anomaly_score` = fungsi sigmoid terukur dari `deviation_pct`.
- **Fallback**: Menggunakan kalkulasi **Z-Score Peer Group** berdasarkan rata-rata biaya Faskes sejenis jika model XGBoost tidak tersedia.

#### 3. Fraud Agent (`fraud_agent.py`)
- **Fungsi**: Mendeteksi pola kecurangan relasional, duplikasi, dan pencilan jaringan.
- **Vector Similarity (LanceDB)**:
  - Meng-encode profil klaim menggunakan `sentence-transformers` (`all-MiniLM-L6-v2`).
  - Menghitung **Komposit Multi-Faktor Similarity Score** (bukan hanya cosine embedding):
    - 40% Jaccard kode diagnosis & prosedur.
    - 30% Kedekatan nilai biaya klaim.
    - 15% Provider sama.
    - 10% Jarak tanggal pelayanan.
    - 5% Pasien sama.
- **Pola Kecurangan**:
  - **Repeat Billing**: Pasien, prosedur, dan rentang tanggal berdekatan yang diklaim berulang.
  - **Cloning**: Similarity komposit tinggi (`>= 0.85`) dengan pasien BERBEDA dari provider SAMA.
  - **Unbundling**: Prosedur terpisah pada window waktu singkat yang seharusnya berada dalam satu paket INA-CBG.
- **Unsupervised Anomaly & Graph**:
  - **Isolation Forest**: Menilai pencilan multidimensi pada profil medis.
  - **Graph Network Metrics**: Memodulasi skor Isolation Forest menggunakan *degree centrality* dan *clustering coefficient* provider yang terkomputasi.

---

### Phase 2: Review Synthesis Agent (`review_agent.py`)
- **Fungsi**: Mengonsolidasi dan menyintesis temuan dari Phase 1 menjadi satu kesimpulan bukti.
- **Model LLM**: `deepseek-r1:7b` (dengan *reasoning trace*) atau `mistral:7b`.
- **Output**:
  - `evidence_level`: `strong_multi_signal` (>= 2 sinyal independen atau fraud terkonfirmasi), `single_signal`, atau `weak`.
  - `corroborating_signals`: Daftar string sinyal yang saling mengonfirmasi (misal: "Upcoding severity 3 diidentifikasi oleh Clinical Agent DAN Deviasi biaya +145% dikonfirmasi Financial Engine").
  - `reasoning_narrative`: Narasi penalar terperinci mengenai korelasi antar-bukti.

---

### Phase 3: Risk Score Engine (`risk_engine.py`)
- **Prinsip Utama**: **Non-LLM & Purely Deterministic Scoring**. LLM tidak pernah mengubah atau memanipulasi angka skor risiko secara langsung.
- **Formula Bobot (Total Maksimal 100 Poin)**:

  $$\text{Total Risk Score} = \text{Clinical} + \text{Financial} + \text{Isolation Forest} + \text{Similarity Fraud} + \text{Synthesis Confidence}$$

| Komponen Breakdown | Bobot Maksimal | Sumber Angka (Traceable) |
|---|---|---|
| `clinical_rule_flags` | 20.0 | Jumlah & bobot `rule_flags` klinis (`tariff_deviation_extreme`: +10, `unsupported_high_risk_proc`: +8, `severity_proc_mismatch`: +5, `upcoding_risk_diag`: +4, `severity_med_mismatch`: +3, `los_outlier`: +2). |
| `financial_anomaly` | 30.0 | $\min(30.0, \text{financial.anomaly\_score} \times 30.0)$. |
| `isolation_forest_anomaly` | 15.0 | $\min(15.0, \text{isolation\_forest\_score} \times 15.0 \times \text{provider\_factor})$. |
| `similarity_fraud` | 20.0 | 20.0 jika `unbundling_flag` / `repeat_billing_flag` True; atau $\min(20.0, \text{similarity\_max\_score} \times 20.0)$ jika `cloning_flag` True; 0.0 untuk kemiripan wajar. |
| `synthesis_confidence` | 15.0 | 15.0 jika terdapat `>= 2` sinyal independen atau fraud relasional; 5.0 jika 1 sinyal; 0.0 jika tidak ada. |

- **Tiering Prioritas**:
  - **High Priority** ($\ge 60.0$)
  - **Medium Priority** ($25.0 - 59.9$)
  - **Low Priority** ($< 25.0$)

---

### Phase 4: Indonesian Explanation & QA Agent (`explanation_agent.py`)
- **Fungsi**: Memformulasikan hasil analisis teknis menjadi bahasa alami Indonesia yang mudah dipahami oleh Verifier BPJS Kesehatan.
- **Model LLM**: `qwen2.5:7b` (Ollama lokal) atau `GeminiClient`.
- **Komponen Output**:
  1. `narrative_id`: Ringkasan eksekutif posisi risiko klaim dalam Bahasa Indonesia.
  2. `ranked_reasons`: 3 alasan utama prioritisasi yang diurutkan berdasarkan kontribusi skor tertinggi.
  3. `recommended_action`: `verify_immediately` (High), `review_when_available` (Medium), atau `low_priority` (Low).
  4. `qa_panel`: Panel tanya-jawab otomatis untuk verifier:
     - *Mengapa klaim ini menjadi prioritas utama?*
     - *Klaim historis mana yang paling mirip?*
     - *Apa bukti paling kuat yang ditemukan?*
     - *Apakah sistem ini menentukan fraud?* (Jawaban standar: Tidak, keputusan akhir di tangan verifier).
- **Template Fallback**: Jika LLM lokal mengalami kendala, generator berbasis template siap menghasilkan narasi terstruktur tanpa menggagalkan respon.

---

## 3. Protokol Ketahanan & Fallback (`run_with_fallback`)

Setiap panggilan agent dibungkus oleh fungsi pembungkus `run_with_fallback()`:

```python
async def run_with_fallback(agent_name: str, coro_fn, claim: ClaimInput, fallback_factory):
    start = time.perf_counter()
    try:
        result = await coro_fn(claim)
        duration_ms = int((time.perf_counter() - start) * 1000)
        return result, AgentError(agent_name=agent_name, error_type="exception", raw_output=None, fallback_applied=False), duration_ms, model_used, "success"
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        fallback = fallback_factory(claim, str(e))
        return fallback, AgentError(agent_name=agent_name, error_type="tool_failure", raw_output=str(e)[:500], fallback_applied=True), duration_ms, None, "fallback"
```

### Jaminan Ketahanan (Resilience Guarantees):
1. **Non-Crashing Pipeline**: Kegagalan satu agent (misal: timeout LLM atau error model ML) **tidak akan membatalkan** seluruh proses investigasi.
2. **Partial Result Tagging**: Hasil analisis tetap dikembalikan dengan flag `partial=True`.
3. **Audit Error Logging**: Detail kegagalan dicatat pada objek `agent_errors[]` dan disimpan di tabel `agent_runs` untuk transparansi audit.

---

## 4. Server-Sent Events (SSE) Protocol Specifications

Untuk memberikan pengalaman pengguna yang responsif (*interactive investigation timeline*), sistem menggunakan protokol SSE pada endpoint `/api/stream/{task_id}`.

### 4.1 Event Payload Structure

```json
event: phase1_complete
data: {
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "step": "phase1",
  "message": "Phase 1: Analisis paralel 3 agent selesai",
  "data": {
    "clinical": { ... },
    "financial": { ... },
    "fraud": { ... }
  }
}
```

### 4.2 Tipe Event dalam Stream

| Event Type | Deskripsi Payload | Trigger Timing |
|---|---|---|
| `status` | Pesan indikator progress pipeline (`step`, `message`). | Awal pipeline & perpindahan fase. |
| `phase1_complete` | Object JSON gabungan dari Clinical, Financial, & Fraud Agent. | Setelah `asyncio.gather` Phase 1 selesai. |
| `phase2_complete` | Object `ReviewSynthesis` (sintesis bukti & reasoning trace). | Setelah Review Agent selesai. |
| `phase3_complete` | Object `RiskScore` (total score, breakdown, priority tier). | Setelah Risk Engine selesai. |
| `phase4_complete` | Object `ClaimExplanation` (narasi BI & QA Panel). | Setelah Explanation Agent selesai. |
| `rejected` | Alasan penolakan deterministik (`reject_reason`). | Jika Phase 0 gagal / Hard Reject. |
| `error` | Detail exception jika terjadi fatal unhandled error. | Saat uncaught pipeline error. |
| `done` | Event penutup (*sentinel event*), stream ditutup secara bersih. | Setelah seluruh data tersimpan di DB. |

---

## 5. Persistence & Data Flow Architecture

Setelah Phase 4 selesai, `orchestrator.py` secara otomatis melakukan transaksi database:
1. Menyimpan data analisis lengkap ke tabel `risk_analyses`.
2. Mencatat durasi nyata, status, dan model yang digunakan ke tabel `agent_runs`.
3. Menulis jejak audit eksekusi ke tabel `audit_logs`.
4. Mengubah `claims.status` dari `"pending"` menjadi `"processed"`.
5. Memasukkan embedding profil klaim baru ke indeks vektor **LanceDB** secara idempotent untuk memperkaya referensi similarity klaim berikutnya.

---

## 6. Referensi Dokumen Terkait
- [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md) — Spesifikasi kebutuhan produk J-ARI.
- [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md) — Arsitektur teknis dan schema database.
- [Models.md](file:///c:/Users/Radith/E-Jak/docs/Models.md) — Detail spesifikasi model XGBoost, SHAP, Isolation Forest, dan LLM.
- [BusinessCore.md](file:///c:/Users/Radith/E-Jak/docs/BusinessCore.md) — Aturan bisnis INA-CBG dan mitigasi upcoding.
