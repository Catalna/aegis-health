# AGENTS.md — Spesifikasi Detail J-ARI Agent Pipeline

Dokumen ini adalah referensi implementasi untuk tiap "agent" di pipeline. Rujuk `PRD.md` Section 6-8 untuk konteks arsitektur; dokumen ini masuk lebih dalam ke logika, schema, dan failure handling tiap agent.

## Prinsip yang berlaku ke semua agent (jangan dilanggar saat implementasi)

1. **Skor numerik tidak pernah datang dari LLM.** Kalau sebuah agent perlu menghasilkan angka yang dipakai untuk ranking/prioritas, angka itu harus berasal dari rule eksplisit atau model ML (dengan SHAP/feature importance). LLM boleh membaca angka itu dan menjelaskannya, tidak boleh menciptakannya.
2. **Semua I/O antar-agent adalah Pydantic model**, bukan string bebas. Kalau LLM gagal menghasilkan output valid, agent harus retry dengan pesan error yang jelas (maks 2x), lalu fallback ke status `NEEDS_HUMAN_REVIEW` — bukan mengarang default value.
3. **Setiap agent mencatat provenance-nya sendiri**: model/rule apa yang dipanggil, versi/threshold yang dipakai, dan waktu eksekusi — untuk audit log (lihat PRD Section 12, Auditability).
4. **Tidak ada agent yang punya akses tulis ke database produksi klaim.** Semua agent read-only terhadap data klaim; satu-satunya "write" adalah menyimpan hasil analisis ke tabel terpisah (`risk_assessments`).
5. **Semua sebutan "LLM lokal" di dokumen ini berarti dipanggil lewat `LLMClient` interface (`OllamaClient` untuk jalur demo).** `GeminiClient` (Gemini API free tier) tersedia sebagai baseline benchmark/fallback — lihat PRD Section 7 untuk kapan masing-masing dipakai. Model spesifik yang disebut tiap agent (mis. `mistral:7b`, `qwen2.5:7b`) adalah kandidat jalur demo, bukan satu-satunya opsi valid.

---

## 0. Orchestrator (bukan agent, tapi pengatur alur)

**Bukan LLM, bukan agent** — ini fungsi Python murni (lihat PRD Section 6). Tugasnya cuma dua: (1) jalankan validasi deterministik, (2) panggil 3 agent paralel lalu 2 agent berurutan, tangani exception per-agent supaya kegagalan satu agent tidak menjatuhkan seluruh pipeline.

```python
class ClaimInput(BaseModel):
    claim_id: str
    patient_id: str
    provider_id: str
    doctor_id: str
    diagnosis_primary: str          # kode ICD-10 disederhanakan
    diagnosis_secondary: list[str]
    procedure_codes: list[str]
    medication: list[MedicationLine]
    severity_level: int             # 1-4, proxy CC/MCC sederhana
    cost_claimed: float
    length_of_stay: int
    admission_date: date
    discharge_date: date
    referral_info: ReferralInfo | None

class AgentError(BaseModel):
    agent_name: str
    error_type: Literal["schema_invalid", "timeout", "tool_failure"]
    raw_output: str | None
    fallback_applied: bool

async def process_claim(claim: ClaimInput) -> RiskAssessment:
    validation = validate_deterministic(claim)
    if validation.hard_reject:
        return RiskAssessment.rejected(claim.claim_id, validation.reason)

    results = await asyncio.gather(
        run_with_fallback(clinical_agent.analyze, claim),
        run_with_fallback(financial_engine.analyze, claim),
        run_with_fallback(fraud_agent.analyze, claim),
        return_exceptions=True,
    )
    clinical, financial, fraud = unpack_or_flag_partial(results)

    review = review_agent.synthesize(clinical, financial, fraud)
    risk_score = risk_engine.compute(clinical, financial, fraud)  # deterministik, bukan LLM
    explanation = explanation_agent.narrate(risk_score, review, claim)

    return RiskAssessment(
        claim_id=claim.claim_id,
        score=risk_score,
        evidence=review,
        narrative=explanation,
        partial=any(isinstance(r, AgentError) for r in results),
    )
```

**Perilaku saat satu agent gagal:** pipeline tidak boleh berhenti total. Hasil tetap dikembalikan dengan flag `partial=True` dan catatan agent mana yang gagal — verifier tetap bisa melihat evidence yang berhasil dikumpulkan, dengan disclaimer eksplisit bahwa satu sumber evidence tidak tersedia.

---

## 1. Data Validation (deterministic, sebelum agent apa pun jalan)

**Bukan agent** — rule check murni, tidak pakai LLM/ML sama sekali.

| Cek | Aksi jika gagal |
|---|---|
| Field wajib kosong (claim_id, patient_id, provider_id, diagnosis_primary) | Hard reject, tidak masuk pipeline |
| Duplicate exact (semua field identik dengan klaim lain) | Flag `EXACT_DUPLICATE`, skip ke Fraud Agent langsung (tidak perlu clinical/financial re-analysis) |
| `discharge_date < admission_date` | Hard reject, data corrupt |
| `severity_level` di luar range 1-4 | Hard reject |

## 2. Clinical Reasoning Agent

**Tujuan:** menilai apakah diagnosis-prosedur-obat-severity level konsisten secara klinis, dan apakah severity level yang diklaim sesuai kondisi yang terdokumentasi (inti deteksi upcoding — lihat PRD Section 2).

**Alur internal (2 lapis, bukan 1 langkah):**

```
Lapis 1 — Rule engine (selalu jalan, deterministik):
  1. Lookup: apakah kombinasi diagnosis_primary + procedure_codes ada di
     tabel referensi kompatibilitas (built dari dokumentasi publik)?
  2. Lookup grouper: diagnosis + severity_level + CC/MCC flag → CBG group
     simplified → tarif referensi
  3. Bandingkan tarif referensi vs cost_claimed → deviation flag

Lapis 2 — LLM lokal (mistral:7b), HANYA untuk kasus yang tidak match
  persis di Lapis 1 (kombinasi diagnosis-prosedur tidak ada di tabel
  referensi, atau ambigu):
  1. LLM diberi diagnosis + prosedur + severity level + reasoning singkat
     dari tabel referensi terdekat
  2. LLM diminta output terstruktur: apakah kombinasi ini "plausible",
     "questionable", atau "implausible" — DENGAN alasan tekstual
  3. Output ini TIDAK mengubah skor numerik langsung — hanya menambah
     evidence_text dan menaikkan/menurunkan confidence_level (bukan skor)
```

**Kenapa 2 lapis, bukan LLM langsung untuk semua kasus:** rule engine untuk kasus yang sudah terdokumentasi jelas lebih cepat, lebih murah, 100% konsisten, dan tidak berisiko halusinasi. LLM dipanggil hemat — hanya untuk long-tail kasus di luar tabel referensi.

```python
class ClinicalAssessment(BaseModel):
    claim_id: str
    grouper_result: CBGLookupResult       # dari rule engine
    tariff_deviation_pct: float           # dari rule engine
    compatibility_status: Literal["match_table", "llm_assessed", "no_data"]
    plausibility: Literal["plausible", "questionable", "implausible", "n/a"]
    evidence_text: str                    # dari rule ATAU LLM, label sumbernya jelas
    confidence_level: Literal["high", "medium", "low"]
```

**Tools:** rule engine internal (Python dict/lookup table), `mistral:7b` via Ollama untuk Lapis 2.
**Fallback jika LLM gagal/timeout:** `compatibility_status = "no_data"`, `plausibility = "n/a"`, evidence_text menjelaskan bahwa penilaian klinis tidak lengkap — bukan menebak.

## 3. Financial Risk Engine

**Tujuan:** deteksi cost anomaly relatif terhadap peer group (klaim sejenis: diagnosis+severity+tipe faskes yang sama).

**Bukan agent LLM sama sekali** — murni ML pipeline. Detail model, feature, dan alternatif teknik ada di `MODELS.md` Section 1.

```python
class FinancialAssessment(BaseModel):
    claim_id: str
    predicted_cost_range: tuple[float, float]  # dari XGBoost quantile atau peer stats
    actual_cost: float
    deviation_pct: float
    shap_top_features: list[SHAPFeature]       # WAJIB ada, bukan opsional
    anomaly_score: float                       # 0-1, dari model
```

**Tools:** XGBoost model (pre-trained), SHAP explainer.
**Fallback jika model gagal load/predict:** turun ke perbandingan statistik sederhana (z-score terhadap peer group mean/std) — tetap deterministik, tetap ada angka, hanya lebih kasar. Tidak pernah fallback ke "no score".

## 4. Fraud/Pattern Investigation Agent

**Tujuan:** deteksi cloning (klaim disalin), repeat billing, dan pola relasional mencurigakan (provider-dokter-pasien).

```
1. Similarity check: embed claim (sentence-transformers) → cosine
   similarity via LanceDB terhadap klaim historis dari provider yang
   sama dan provider lain
   - similarity > threshold_high → flag CLONING_SUSPECTED
2. Repeat billing check: query exact/near-match pada
   (patient_id, procedure_codes, date_range) yang sudah pernah dibayar
3. Relational check: precomputed graph metrics (degree centrality,
   clustering coefficient) dari static graph view — BUKAN live query
   Neo4j (lihat PRD Section 9) — untuk deteksi cluster provider-dokter
   yang tidak wajar
```

```python
class FraudAssessment(BaseModel):
    claim_id: str
    similarity_max_score: float
    similarity_matched_claim_id: str | None
    repeat_billing_flag: bool
    graph_cluster_anomaly_score: float  # dari precomputed metrics
    evidence_text: str                  # rule-generated, bukan LLM
```

**Tools:** LanceDB query, SQL exact-match query, precomputed graph metrics (dihitung batch, bukan real-time). **Tidak pakai LLM sama sekali di agent ini** — semua sinyalnya numerik/rule-based, tidak butuh reasoning tekstual.

## 5. Review Agent

**Tujuan:** sintesis 3 hasil di atas jadi satu kesimpulan tingkat evidence — ini satu-satunya agent yang benar-benar butuh *reasoning* lintas-sumber, karena itu pakai LLM.

```
Input: ClinicalAssessment + FinancialAssessment + FraudAssessment
Proses (LLM lokal, opsional deepseek-r1:7b untuk reasoning trace):
  - LLM diberi ringkasan terstruktur dari 3 hasil (BUKAN raw data klaim)
  - Diminta identifikasi: apakah sinyal-sinyal ini saling menguatkan
    (mis. severity di-upcode DAN cost jauh di atas peer DAN mirip klaim
    lain) atau saling independen/lemah?
  - Output: evidence_level terstruktur, BUKAN skor baru
```

```python
class ReviewSynthesis(BaseModel):
    claim_id: str
    evidence_level: Literal["strong_multi_signal", "single_signal", "weak"]
    corroborating_signals: list[str]     # daftar sinyal yang saling menguatkan
    reasoning_narrative: str             # dari LLM, boleh dari reasoning trace
    reasoning_source: Literal["llm_direct", "llm_reasoning_trace"]  # transparansi wajib
```

**Kenapa `reasoning_source` wajib ada:** kalau pakai `deepseek-r1`, trace-nya harus dilabeli beda dari output LLM biasa — supaya di dashboard, verifier tahu ini "penjelasan pendukung", bukan kesimpulan otoritatif setara SHAP value.

**Fallback jika LLM gagal:** turun ke rule sederhana — hitung berapa dari 3 agent yang flag anomaly di atas threshold masing-masing; ≥2 dari 3 → `strong_multi_signal` otomatis tanpa narasi LLM (evidence_level tetap terisi, hanya `reasoning_narrative` kosong dengan catatan "LLM synthesis unavailable, fallback ke rule count").

## 6. Risk Score Engine

**Bukan agent, bukan LLM** — fungsi scoring deterministik.

```python
def compute_risk_score(
    clinical: ClinicalAssessment,
    financial: FinancialAssessment,
    fraud: FraudAssessment,
) -> RiskScore:
    # Bobot dari feature importance SHAP (Financial) + rule weight tetap
    # (Clinical, Fraud) — SEMUA bobot didokumentasikan, tidak ada yang
    # hardcoded tanpa justifikasi tertulis di MODELS.md
    ...
    return RiskScore(
        total_score=...,          # 0-100
        breakdown={
            "clinical_deviation": ...,
            "financial_anomaly": ...,
            "similarity_signal": ...,
        },
        priority_tier=...,        # "high" / "medium" / "low"
    )
```

Ini bagian yang **wajib** bisa ditelusuri utuh ke SHAP value atau rule tertulis untuk memenuhi klaim "explainable" di PRD Section 12 — kalau ada bagian breakdown yang angkanya tidak bisa dijelaskan asalnya, itu bug, bukan detail implementasi yang boleh dilewati.

## 7. Explanation Agent

**Tujuan:** ubah `RiskScore` + `ReviewSynthesis` jadi laporan Bahasa Indonesia yang bisa langsung dibaca verifier.

```
Input: RiskScore (angka+breakdown) + ReviewSynthesis (evidence_level+narrative)
Proses (LLM lokal, qwen2.5:7b atau qwen3:8b):
  - Prompt eksplisit melarang LLM mengubah/membulatkan angka skor
  - LLM hanya merangkai: "Klaim ini mendapat skor X karena [breakdown],
    didukung oleh [corroborating_signals]. Rekomendasi: [priority_tier]."
  - Output WAJIB Bahasa Indonesia (lihat PRD Section 7.2)
```

```python
class ClaimExplanation(BaseModel):
    claim_id: str
    narrative_id: str          # Bahasa Indonesia
    ranked_reasons: list[str]  # diurutkan berdasarkan kontribusi skor
    recommended_action: Literal["verify_immediately", "review_when_available", "low_priority"]
    qa_panel: QAPanel           # lihat sub-section di bawah — pengganti "Investigator Copilot"
```

**Validasi wajib sebelum output diterima:** parse angka apa pun yang disebut LLM di narasi, cross-check terhadap `RiskScore.total_score` asli. Kalau ada mismatch (LLM "salah kutip" angka), reject output dan retry — ini pengaman konkret terhadap silent hallucination pada angka.

**Fallback jika LLM gagal:** template string sederhana yang mengisi breakdown apa adanya tanpa narasi mengalir — lebih kaku tapi tetap akurat, lebih baik daripada tidak ada output sama sekali.

### 7.1 QA Panel — pengganti "Investigator Copilot" terpisah

**Keputusan:** fitur tanya-jawab interaktif ("Ask Investigator") **tidak dibangun sebagai agent/chat terpisah**. Alasan: chat bebas dengan LLM live saat demo punya risiko halusinasi di depan juri yang tidak proporsional dengan manfaatnya — pertanyaan yang paling mungkin ditanyakan juri sebenarnya sudah terjawab oleh data yang *sudah* dihasilkan pipeline. Daripada bangun agent baru, **4 pertanyaan paling umum dijawab dari field yang sudah ada**, dihitung sekali saat `process_claim()` selesai, bukan LLM call baru saat tombol diklik:

```python
class QAPanel(BaseModel):
    why_top_priority: str      # = ranked_reasons digabung, sudah ada
    most_similar_claim: str    # = dari FraudAssessment.similarity_matched_claim_id, sudah ada
    strongest_evidence: str    # = evidence dengan kontribusi skor tertinggi di RiskScore.breakdown
    is_this_fraud: str         # = STRING TETAP, tidak pernah dari LLM (lihat di bawah)
```

`is_this_fraud` **wajib hard-coded**, bukan hasil generate LLM sama sekali — ini pertanyaan paling sensitif secara reputasi, jawabannya harus 100% konsisten setiap saat:

```python
FRAUD_QUESTION_ANSWER = (
    "Sistem ini tidak menentukan status fraud. Skor dan evidence yang "
    "ditampilkan adalah rekomendasi prioritas untuk verifikasi manusia — "
    "keputusan akhir selalu berada di tangan verifier BPJS."
)
```

Tiga field lain (`why_top_priority`, `most_similar_claim`, `strongest_evidence`) bersumber dari field yang **sudah dihitung** oleh agent lain (Explanation, Fraud, Risk Score Engine) — tidak ada LLM call tambahan saat tombol diklik di UI, sehingga **nol risiko halusinasi live** karena tidak ada generasi baru terjadi saat demo, hanya menampilkan data yang sudah divalidasi sebelumnya.

**Kalau nanti ada kapasitas lebih (bukan MVP):** baru pertimbangkan buka ke free-text dengan guardrail (deteksi pertanyaan di luar 4 kategori ini → jawab template "tidak bisa dijawab dari evidence yang tersedia", bukan mengarang) — dicatat di PRD sebagai item masa depan, bukan scope 4 minggu ini.

---

## Ringkasan Tools per Agent

| Agent | LLM? | Model/Rule | Bisa Gagal Tanpa Menjatuhkan Pipeline? |
|---|---|---|---|
| Data Validation | Tidak | Rule | Tidak — ini gerbang wajib |
| Clinical Reasoning | Kadang (Lapis 2) | Rule + `mistral:7b` | Ya, fallback ke `no_data` |
| Financial Risk Engine | Tidak | XGBoost + SHAP | Ya, fallback ke z-score |
| Fraud/Pattern | Tidak | LanceDB + rule + precomputed graph | Ya, fallback ke similarity-only |
| Review | Ya | `deepseek-r1:7b` (opsional) / LLM lain | Ya, fallback ke rule count |
| Risk Score Engine | Tidak | Deterministic function | Tidak — ini jantung sistem |
| Explanation | Ya | `qwen2.5:7b`/`qwen3:8b` | Ya, fallback ke template |

## Testing per agent (wajib sebelum integrasi penuh)

Setiap agent harus punya unit test dengan **input sintetis yang hasilnya sudah diketahui** (bukan cuma "jalan tanpa error"):
- Clinical: 1 kasus match table, 1 kasus butuh LLM, 1 kasus severity di-upcode jelas
- Financial: 1 kasus normal, 1 kasus cost 3x lipat peer average
- Fraud: 1 kasus cloning jelas (similarity >0.95), 1 kasus normal
- Review: 1 kasus 3/3 sinyal kuat, 1 kasus cuma 1 sinyal lemah
- Explanation: cross-check angka di narasi vs RiskScore asli tidak boleh mismatch di semua kasus test