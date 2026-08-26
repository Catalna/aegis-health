# PRD — JKN Agentic Risk Intelligence (J-ARI)

**Kompetisi:** Healthkathon 2026 BPJS Kesehatan
**Kategori:** Efisiensi Risiko pada Fasilitas Kesehatan
**Fokus utama:** Upcoding (manipulasi diagnosis/tindakan, grounded di logika INA-CBG) & Tindakan Pengobatan Tidak Sesuai Indikasi Medis
**Sinyal pendukung:** Cloning, Repeat Billing, Cost Anomaly, Temporal/Behavioral Anomaly
**Tim:** 3 orang | **Durasi:** 4 minggu | **Status data:** dataset dibuat sendiri (sintetis, tidak ada data JKN riil)
**Kapasitas riil:** ~180–240 person-hours total (3 orang × ~15–20 jam/minggu × 4 minggu)

---

## 1. Problem Statement

Volume klaim JKN terlalu besar untuk diperiksa manual dengan kedalaman yang sama di setiap klaim. Risiko (fraud maupun ketidaksesuaian klaim) muncul dalam bentuk yang beragam dan seringkali baru terlihat ketika beberapa sumber data dibandingkan sekaligus — bukan dari satu sinyal tunggal.

**Bukan** yang ingin dibangun: "Fraud / Not Fraud" classifier biner.
**Yang ingin dibangun:** pipeline `Risk identification → evidence gathering → explanation → prioritization → human verification`.

## 2. Domain Grounding (Kritis — Bedanya dari Generic Fraud Detector)

Klaim JKN dibayar melalui **INA-CBG (Indonesia Case Base Groups)**: tarif ditentukan oleh diagnosis primer/sekunder, prosedur, dan **severity level (CC/MCC — complication & comorbidity)**. Upcoding pada konteks JKN secara spesifik umumnya berarti memanipulasi *input* grouper ini (menaikkan severity level atau menambah diagnosis komplikasi yang tidak sesuai kondisi riil) agar klaim jatuh ke CBG group bertarif lebih tinggi.

**Implikasi desain:** sistem tidak cukup menilai "apakah prosedur cocok dengan diagnosis" secara generik. Clinical Reasoning Agent dan Financial Risk Engine harus eksplisit memodelkan logika grouper (versi disederhanakan) — ini yang membedakan J-ARI dari fraud detector generik yang dibungkus istilah kesehatan.

Untuk MVP: **tidak** mereplikasi grouper INA-CBG resmi secara penuh. Cukup rule-based simplified grouper (diagnosis + prosedur + severity level → CBG group → tarif referensi) berdasarkan dokumentasi publik, dengan disclaimer eksplisit sebagai simplifikasi demonstrasi.

## 3. Goals & Non-Goals

### Goals (MVP harus membuktikan)
- Sistem dapat memprioritaskan klaim berisiko tinggi ke top-K queue dari kumpulan klaim campuran (normal + anomali yang disisipkan)
- Setiap skor risiko dapat ditelusuri ke evidence/fitur spesifik (bukan black box)
- Sistem membedakan minimal 3 jenis anomali: clinical (grounded di INA-CBG), financial, similarity
- Output berupa rekomendasi + evidence, **bukan** vonis "fraud confirmed"

### Non-Goals (eksplisit di luar scope)
- Bukan pengganti sistem anti-fraud internal BPJS
- Bukan replikasi penuh grouper INA-CBG resmi
- Bukan sistem produksi — MVP demonstrasi konsep
- **Bukan fine-tuning/training model custom (IndoBERT dsb.)** — dipertimbangkan lalu sengaja dibuang: fine-tuning encoder custom memperparah risiko tautologi data sintetis (model dijamin "berhasil" mengenali pola yang ditanam tim sendiri, jauh lebih sulit dipertanggungjawabkan dibanding XGBoost+SHAP yang feature importance-nya transparan), dan skema data saat ini tidak punya free-text clinical notes yang benar-benar butuh NER/encoder custom. Dicatat sebagai potensi roadmap lanjutan, bukan scope MVP.
- Tidak mengklaim performa lebih baik dari sistem internal BPJS (yang tidak diketahui publik)

## 4. Target User

**Verifier klaim BPJS** — pengguna utama dashboard, dan **satu-satunya role dengan akses sistem sungguhan**. Kebutuhan: mengetahui klaim mana yang paling perlu diperiksa dan mengapa, dalam waktu minimal, dengan evidence yang bisa langsung dipakai untuk investigasi lanjutan (bukan skor probabilitas tanpa konteks).

**Faskes bukan user J-ARI.** Dalam alur JKN nyata, faskes submit klaim lewat sistem BPJS yang sudah ada (Vclaim, SEP, e-klaim) — J-ARI beroperasi *setelah* klaim itu masuk data store, tugasnya menganalisis risiko, bukan jadi pintu masuk klaim baru. Faskes muncul di sistem hanya sebagai **atribut data** (mis. Data Sources checklist di Claim Intake — lihat `FRONTEND.md`), bukan sebagai role login. **Keputusan eksplisit: tidak ada sistem autentikasi/otorisasi multi-role di MVP** — satu tampilan verifier saja, tanpa login sungguhan sama sekali untuk kebutuhan demo 4 minggu ini. Kalau ditanya juri soal role Faskes, jawabannya ada di sini: itu sumber data, bukan pengguna sistem.

## 5. System Flow (End-to-End)

> **Titik masuk "CLAIM MASUK":** klaim sudah ada sebagai record di tabel `claims` (dari simulasi integrasi faskes — lihat `FRONTEND.md` Demo Data Loader untuk hackathon, atau integrasi sungguhan di produksi). Verifier **membuka** klaim yang sudah ada dari Incoming Claims queue, memicu `process_claim()` — bukan mengetik detail klaim dari nol. Lihat `FRONTEND.md` koreksi #6 untuk konteks kenapa penegasan ini penting.

```text
                       CLAIM MASUK
                            |
                            v
              DATA VALIDATION (deterministic)
              - mandatory field check
              - exact duplicate check
              - date/sequence contradiction
                            |
                            v
                 CASE MANAGER
          (fungsi Python, bukan LangGraph —
           lihat Section 6 untuk alasan)
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
 CLINICAL AGENT      FINANCIAL ENGINE      FRAUD/PATTERN AGENT
 - INA-CBG grouper    - XGBoost cost        - similarity (LanceDB +
   simplified            anomaly + SHAP       sentence-transformers)
 - diagnosis→proc→    - (Isolation Forest    - repeat billing check
   med compatibility    dicatat sebagai      - graph relations
   (LLM lokal, lihat      future work)         (static view, bukan
   Section 7)                                   Neo4j — lihat Sec. 7)
        |                   |                   |
        +-------------------+-------------------+
                            |
                            v
                    REVIEW AGENT
              (cross-check antar hasil,
               menyimpulkan tingkat evidence —
               LLM lokal, reasoning trace
               opsional jadi bahan audit)
                            |
                            v
              RISK SCORE ENGINE (SHAP-based,
                bukan bobot manual, BUKAN LLM)
                            |
                            v
                EXPLANATION AGENT
        (LLM — merangkai skor + evidence →
         narasi Bahasa Indonesia,
         TIDAK menentukan angka skor)
                            |
                            v
              PRIORITY QUEUE + EVIDENCE
                            |
                            v
                  HUMAN VERIFIER
           (keputusan akhir, hasil jadi
            feedback loop opsional)
```

### Prinsip non-negotiable
- **Rules** untuk hal deterministik (duplicate, missing field, INA-CBG grouper lookup)
- **ML (XGBoost + SHAP)** untuk scoring — skor numerik SELALU dari model/rule, bukan LLM
- **LLM** hanya untuk reasoning berbasis teks, sintesis evidence, dan penulisan narasi — tidak pernah jadi sumber skor numerik akhir
- **Manusia** selalu memegang keputusan akhir — output tertinggi sistem adalah "High Risk — Requires Verification", bukan "Confirmed Fraud"

## 6. Orkestrasi: Sequential Functions, Bukan LangGraph Penuh

**Keputusan:** 5 "agent" diimplementasikan sebagai **fungsi Python berurutan/paralel dengan I/O terstruktur (Pydantic)**, bukan state machine LangGraph penuh.

**Alasan:** untuk tim 3 orang dalam 4 minggu, LangGraph menambah learning curve dan permukaan kegagalan tanpa manfaat proporsional pada skala MVP ini — kompleksitas orchestration sesungguhnya (5 node dengan cabang dan sinkronisasi) bisa direpresentasikan dengan `asyncio.gather()` untuk 3 agent paralel (Clinical, Financial, Fraud) diikuti pemanggilan Review lalu Explanation secara berurutan. Ini secara fungsional setara, jauh lebih mudah di-debug oleh tim yang belum tentu fasih framework baru, dan tetap bisa disebut "agentic pipeline" secara jujur di narasi — karena yang membuat sesuatu "agentic" adalah pembagian tanggung jawab + reasoning per unit kerja, bukan framework orchestration spesifik yang dipakai.

```python
# orchestrator.py — kerangka konkret
async def process_claim(claim: ClaimInput) -> RiskAssessment:
    validate_deterministic(claim)  # exact duplicate, missing field

    clinical, financial, fraud = await asyncio.gather(
        clinical_agent.analyze(claim),   # rule engine + LLM lokal
        financial_engine.analyze(claim), # XGBoost + SHAP
        fraud_agent.analyze(claim),      # LanceDB similarity + rule
    )

    review = review_agent.synthesize(clinical, financial, fraud)  # LLM lokal
    risk_score = risk_engine.compute(clinical, financial, fraud)  # SHAP-based, bukan LLM
    explanation = explanation_agent.narrate(risk_score, review)   # LLM, output akhir

    return RiskAssessment(score=risk_score, evidence=review, narrative=explanation)
```

**Kapan LangGraph layak di-restore:** kalau ada anggota tim yang sudah fasih dan ingin menunjukkan audit-trail/retry logic sebagai differentiator eksplisit di 1-2 node saja (misal Clinical + Review) — bukan untuk seluruh pipeline.

## 7. Strategi LLM: Lokal via Ollama, dengan Abstraksi Swappable

### Keputusan inti

Bangun di atas **LLM lokal (Ollama)** sebagai jalur utama development — bukan API — karena:
1. Data sintetis tidak butuh privasi API, tapi laptop dev (Intel Core 5 215H, 16GB RAM, **RTX 5050 8GB VRAM**) sudah cukup untuk menjalankan model 7B penuh di GPU (Q4_K_M ~4.5–5GB weights + KV cache ≈ 5–6GB dari 8GB tersedia)
2. Reliabilitas demo offline — tidak bergantung uptime/koneksi API saat presentasi
3. Biaya nol untuk development iteratif intensif

**Tapi arsitektur harus tetap swappable** ke API lewat satu interface, supaya kalau kualitas structured output/reasoning model lokal ternyata tidak cukup di suatu role, tinggal ganti implementasi tanpa mengubah kode pemanggil:

```python
class LLMClient(Protocol):
    def structured_call(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...

class OllamaClient(LLMClient):   # jalur utama development & DEMO LIVE
    ...

class GeminiClient(LLMClient):   # Gemini API free tier — benchmark baseline & production-path narrative
    ...
```

> **Klarifikasi penting:** "Google AI Pro" (subscription $19.99/bulan) **bukan** sumber kuota untuk `GeminiClient` di atas — itu subscription konsumen yang menaikkan kuota di produk Google sendiri (app Gemini, Google Antigravity/Code Assist, Android Studio), bukan Gemini Developer API yang dipanggil dari backend. `GeminiClient` cukup pakai API key gratis dari Google AI Studio (Gemini API free tier), terpisah total dari keputusan berlangganan AI Pro atau tidak. Kalau tim memang sering mentok kuota gratis Antigravity untuk coding, AI Pro relevan untuk itu — tapi itu keputusan produktivitas development, bukan arsitektur LLM pipeline.

### Model per role (kandidat awal — wajib dibenchmark, lihat 7.3)

| Model (Ollama) | Role | Alasan awal |
|---|---|---|
| `qwen2.5:7b` | Explanation Agent (narasi Bahasa Indonesia) | Reputasi kuat untuk multibahasa termasuk Indonesia; kandidat upgrade: `qwen3:8b` bila sempat di-pull |
| `mistral:7b` | Clinical Agent, Financial Agent (bagian structured/JSON) | Instruction-following Mistral dikenal kuat untuk task ekstraksi/klasifikasi terstruktur |
| `qwen2.5:3b` atau `llama3.2:3b` | Case Manager / routing sederhana | Task-nya cuma menentukan sub-agent mana yang dipanggil — model kecil cukup, lebih cepat |
| `deepseek-r1:7b` | Opsional — Review Agent | Reasoning trace (`<think>...</think>`) bisa dobel fungsi sebagai bahan audit "kenapa Clinical Agent menyimpulkan X" — **tapi trace ini tetap narasi LLM, bukan ground truth**, harus diberi label sebagai bahan pendukung, bukan skor otoritatif. Trade-off: lebih lambat karena generate reasoning trace penuh. |

**Dibuang dari list Ollama:** `llama3.2-vision` — tidak relevan, semua input berupa data terstruktur/teks, bukan gambar; hapus untuk hemat storage.

**Batas hardware:** jangan pakai model 14B+ (butuh ~9GB+ Q4, overflow ke CPU offload, jadi lambat). Waspadai context panjang (>8K token) karena KV cache bisa mepet ke limit 8GB.

### 7.0 Kapan pakai lokal vs Gemini API — peran masing-masing, bukan pilih salah satu

| Kebutuhan | Client | Alasan |
|---|---|---|
| Live demo di depan juri | `OllamaClient` | Tidak bergantung wifi venue/kuota API saat momen paling kritis |
| Benchmark kualitas (Section 7.3) | `GeminiClient` sebagai baseline pembanding | Model cloud kemungkinan besar lebih kapabel dari 7B quantized lokal — mengukur gap ini memberi argumen rigor ke juri ("model lokal kami X% mendekati baseline cloud"), bukan cuma diasumsikan "lokal sudah cukup" |
| Development/iterasi harian | Bebas, mana yang nyaman saat itu | Arsitektur swappable, tidak ada cost pindah-pindah selama development |
| "Production path" narrative ke juri | `GeminiClient` sebagai opsi kedua yang sudah terbukti jalan | Menjawab kriteria Kesiapan & Skalabilitas — bukan klaim kosong karena sudah ada implementasi nyata, bukan cuma disebut di slide |

**Peringatan kuota:** Gemini API free tier punya rate limit (request/menit, request/hari) yang berubah dari waktu ke waktu — cek `ai.google.dev/gemini-api/docs/pricing` untuk angka terkini sebelum bergantung padanya untuk proses bulk (mis. evaluasi ratusan klaim sintetis sekaligus di Minggu 4). Jangan sampai baru sadar kena throttle saat butuh evaluasi cepat mendekati deadline.

**Yang harus dihindari:** mixing model per-agent tanpa alasan eksplisit (mis. Explanation pakai Gemini, Clinical pakai lokal, tanpa justifikasi). Kalau ditanya juri "kenapa hybrid begini," jawabannya harus lebih kuat dari "biar dicoba semua" — gunakan pembagian yang sudah jelas di tabel atas (demo=lokal, benchmark=cloud), bukan campur bebas per-agent.

### 7.1 Prinsip pemisahan skor vs narasi (tetap berlaku untuk semua LLM, lokal maupun Gemini)

Sama seperti keputusan sebelumnya: **skor numerik selalu dari model ML/rule (XGBoost+SHAP, grouper lookup), LLM (lokal ATAU Gemini) hanya untuk reasoning tekstual dan narasi.** Ini termasuk reasoning trace dari `deepseek-r1` — trace itu memperkaya evidence yang bisa dibaca manusia, tapi tidak pernah dipakai sebagai input ke Risk Score Engine. Prinsip ini tidak berubah berdasarkan client mana yang dipakai — itu justru alasan utama kenapa abstraksi `LLMClient` didesain dari awal.

### 7.2 Bahasa output

Explanation Agent harus menghasilkan output **Bahasa Indonesia** — verifier BPJS adalah pengguna akhir. Ini kriteria seleksi model, bukan detail kosmetik: kualitas Bahasa Indonesia model lokal kelas 7B bervariasi signifikan antar model, karena itu wajib dibenchmark (lihat 7.3), bukan diasumsikan dari reputasi umum. Gemini sebagai baseline juga diuji dengan kriteria yang sama.

### 7.3 Prosedur benchmark wajib sebelum commit model (Minggu 1, ~1–2 jam)

1. Siapkan 5–10 contoh kasus klaim sintetis (variasi normal + anomali yang sudah diketahui jenisnya)
2. Jalankan prompt + schema Pydantic yang sama ke `qwen2.5:7b` vs `mistral:7b` vs `qwen3:8b` (jika sempat di-pull) **vs Gemini Flash (free tier) sebagai baseline**
3. Ukur: **(a)** schema validity rate (% output valid tanpa retry), **(b)** kualitas Bahasa Indonesia narasi (evaluasi manual cepat), **(c)** latency per call di hardware dev (Gemini tidak perlu diukur latency-nya untuk keputusan demo, hanya untuk pembanding kualitas)
4. Pilih model per role untuk **jalur demo** berdasarkan angka model lokal — bukan reputasi model di internet. Catat gap kualitas terhadap Gemini sebagai baseline untuk narasi "production path" di proposal.

### 7.4 Distribusi development di tim

**Perlu diputuskan tim:** apakah 2 anggota lain develop terhadap Ollama server di laptop pemilik GPU lewat LAN (`OLLAMA_HOST=0.0.0.0`, panggil dari IP laptop tsb.), atau masing-masing setup Ollama sendiri. Kalau opsi pertama, laptop itu jadi single point of failure untuk development tim (bukan cuma demo hari-H) — perlu mitigasi (mis. semua juga install Ollama lokal sebagai fallback, sync model yang sama). `GeminiClient` bisa jadi fallback sementara untuk anggota yang belum sempat setup Ollama lokal, karena tidak butuh GPU sama sekali.

## 8. Agent Specifications

| Agent | Peran | Tools | Output |
|---|---|---|---|
| Case Manager | Routing — menentukan urutan/paralelisasi eksekusi | Fungsi Python (lihat Section 6) | Task plan untuk sub-agent |
| Clinical Reasoning | Cek kompatibilitas diagnosis-prosedur-obat + severity level vs INA-CBG grouper | Rule engine + grouper lookup + LLM lokal (`mistral:7b`) untuk kasus ambigu | Clinical risk score (dari rule, bukan LLM) + evidence text |
| Financial Risk Engine | Deteksi cost anomaly vs peer group | XGBoost + SHAP | Deviation % + feature importance |
| Fraud/Pattern Investigation | Similarity, repeat billing, temporal pattern, relasi provider-dokter-pasien | LanceDB + sentence-transformers, SQL, graph view statis | Similarity score, cluster info |
| Review | Cross-check hasil 3 agent di atas, simpulkan tingkat evidence gabungan | LLM lokal (`deepseek-r1:7b` opsional untuk reasoning trace) | Kesimpulan evidence level |
| Explanation | Ubah evidence teknis jadi laporan verifier Bahasa Indonesia | LLM lokal (`qwen2.5:7b`/`qwen3:8b`), structured output | Ranked reasons + rekomendasi |

Semua agent I/O menggunakan **Pydantic schema terstruktur** — bukan free-form text antar-agent — agar bisa divalidasi dan diaudit.

## 9. Tech Stack (Final)

| Layer | Pilihan | Alasan konsolidasi |
|---|---|---|
| Backend | Python + FastAPI | — |
| Database | **PostgreSQL polos** (bukan Supabase) — data relasional (claims, patients, providers, doctors) | Bukan Postgres+Redis+Qdrant terpisah untuk data relasional. Supabase dipertimbangkan lalu dibuang — fitur andalannya (Auth, Realtime) tidak dibutuhkan struktural (kita sudah putuskan tanpa sistem login, Section 4) atau sudah ada alternatif murah (polling/SSE untuk timeline), sementara backend developer belum familiar Supabase — menambah tool baru untuk dipelajari tanpa kompensasi manfaat sepadan |
| Cache | Redis (hanya jika terbukti perlu setelah profiling) | Jangan tambah service preventif |
| ML | XGBoost (+ SHAP) | 1 model untuk cost anomaly scoring. Isolation Forest & LightGBM/PyTorch dicatat sebagai future work, bukan dibangun — dataset sintetis tidak cukup besar untuk deep learning, dan 1 model per tugas lebih defensible daripada beberapa kandidat paralel |
| Similarity | sentence-transformers + **LanceDB** (bukan pgvector) | LanceDB dipilih: embedded vector store (file-based, tanpa server process terpisah) — konsisten dengan prinsip "jangan tambah service" yang sama seperti alasan drop Qdrant/FAISS; bedanya dengan konsolidasi ke pgvector di revisi sebelumnya adalah LanceDB kini jadi store terpisah dari PostgreSQL, tapi tetap tidak menambah proses server baru karena sifatnya embedded seperti SQLite untuk vector |
| Graph | **Static graph view (D3.js/vis.js) dari JSON precompute** — bukan Neo4j live | Neo4j di-drop dari build: nilai tambahnya (query graph live) tidak proporsional dengan waktu 1 orang menguasainya untuk MVP; visual relationship provider-doctor-patient tetap bisa didemonstrasikan tanpa infra tambahan. Neo4j dicatat sebagai roadmap produksi. |
| Agent orchestration | Sequential/paralel Python functions + Pydantic (Section 6) | LangGraph opsional untuk 1–2 node saja bila ada yang fasih; AutoGen/CrewAI tetap di-drop |
| LLM | **Ollama (lokal)** untuk demo — `qwen2.5:7b`, `mistral:7b`, `qwen2.5:3b`/`llama3.2:3b`, opsional `deepseek-r1:7b`; **Gemini API (free tier)** untuk benchmark baseline + production-path narrative | Lihat Section 7 untuk detail lengkap; arsitektur swappable via `LLMClient` interface — bukan pilih salah satu, keduanya punya peran berbeda |
| Frontend | React + Vite + Tailwind CSS | — |
| AI coding tools | Claude Code / Codex / Antigravity dsb. | Percepat boilerplate — bukan judgment arsitektur, debugging integrasi, atau validasi domain INA-CBG |

**Dibuang secara eksplisit (dipertimbangkan, sengaja tidak dipakai):**
- IndoBERT fine-tuning/training custom (Section 3 Non-Goals)
- Neo4j live, LangGraph penuh, AutoGen/CrewAI, LightGBM, PyTorch, FAISS/Qdrant terpisah, Redis default

## 10. Data Strategy

**Sumber:** synthetic/de-identified, dilabeli jelas "Synthetic data for demonstration."

**Metodologi anti-tautologi** (mencegah sistem hanya mendeteksi pola yang ditanam sendiri):
- Peran pembuat dataset (fraud pattern + noise acak) dipisah dari peran pembangun detector
- Held-out test set yang genuinely tidak dilihat saat tuning
- Variasi/noise acak dalam batas wajar (severity level, cost) agar tidak selalu identik polanya

**Skema minimum:** claim_id, diagnosis (primer+sekunder), procedure, medication, facility, doctor, cost, LOS, severity_level, referral_info, historical_claims. Skema saat ini **tidak** mencakup free-text clinical notes — jika nanti ditambahkan, itu jadi justifikasi baru untuk NER/encoder custom (lihat Section 3 Non-Goals).

## 11. Functional Requirements (MoSCoW)

**Must Have**
- Claim ingestion + validation (deterministic rules)
- INA-CBG grouper simplified + clinical compatibility check
- Cost anomaly scoring (XGBoost + SHAP)
- Similarity detection (LanceDB)
- Risk score gabungan + evidence
- Explanation narrative (Bahasa Indonesia, via LLM lokal)
- Dashboard: priority queue + evidence view
- Human verification state (accept/reject/escalate)
- Benchmark model lokal (Section 7.3) sebelum commit ke pipeline
- Claim Intake (Form + Raw JSON toggle), AI Investigation timeline (log, real timestamp dari orchestrator), Evidence panel (SHAP + evidence list + similar claims), QA Panel 4-tombol pra-set — detail lengkap di `FRONTEND.md`

**Should Have**
- Static graph view (provider-doctor-patient relationship)
- Reasoning trace dari `deepseek-r1` sebagai bahan audit tambahan di Review Agent
- AI Investigation progress bar animasi (versi kosmetik dari timeline)
- Data Sources checklist di Claim Intake
- Similar Claims side-by-side comparison view

**Nice to Have**
- What-if simulation (skor berubah jika biaya di peer range)
- Provider risk profile
- Feedback loop dari keputusan verifier ke model
- LangGraph untuk 1–2 node sebagai differentiator (jika ada kapasitas)
- `GeminiClient` sepenuhnya teruji sebagai fallback produksi (di luar sekadar benchmark Section 7.3)
- QA Panel versi free-text dengan guardrail (bukan tombol pra-set) — lihat `FRONTEND.md` untuk alasan ditunda

**Dipertimbangkan lalu dibuang dari scope**
- Investigator Copilot sebagai agent/fitur chat terpisah — digabung ke Explanation Agent sebagai QA Panel (AGENTS.md Section 7.1) karena free-text chat live saat demo berisiko halusinasi tanpa manfaat proporsional; 4 pertanyaan paling umum sudah terjawab dari data yang sudah dihitung pipeline

## 12. Non-Functional Requirements

- **Auditability:** setiap output agent tercatat (model/rule apa → feature/evidence apa → output → reviewer)
- **Security:** tool whitelist, read-only default untuk agent, no unrestricted DB access, PII minimization, prompt injection defense pada field teks bebas
- **Explainability:** skor numerik harus traceable ke SHAP value/rule, bukan black box; narasi LLM (termasuk reasoning trace) tidak boleh jadi satu-satunya sumber "kenapa"
- **Human oversight:** tidak ada keputusan fraud otomatis; output tertinggi adalah rekomendasi prioritas
- **Reliability infra:** minimalkan jumlah service berjalan saat demo (konsolidasi database, LLM lokal tanpa dependency internet) untuk mengurangi titik kegagalan
- **Bahasa:** output yang dibaca verifier (narasi, evidence) wajib Bahasa Indonesia

## 13. Evaluation Metrics

| Kategori | Metrik |
|---|---|
| Model | Precision, Recall, F1, PR-AUC, ROC-AUC, False Positive Rate — dihitung pada held-out set, bukan seluruh dataset training |
| Operasional | Top-K detection rate, estimasi pengurangan workload reviewer, rata-rata waktu investigasi |
| Explainability | Evidence completeness & traceability, kegunaan bagi human reviewer |
| Agent/LLM lokal | Schema validity rate, kualitas Bahasa Indonesia (manual eval), latency per call, task completion rate |

**Hindari** melaporkan "accuracy 95%" tanpa konteks — fraud/risk detection punya class imbalance signifikan; precision/recall pada held-out set jauh lebih meyakinkan.

## 14. Timeline (4 Minggu, Tim 3 Orang, ~180–240 Person-Hours Total)

| Minggu | Fokus |
|---|---|
| 1 | Skema data + INA-CBG grouper simplified + dataset sintetis (metodologi anti-tautologi) + rules baseline + **benchmark model lokal (Section 7.3)** |
| 2 | Clinical compatibility layer + XGBoost/SHAP + similarity engine (LanceDB) |
| 3 | Orchestration pipeline (Section 6) + static graph view + explanation layer (LLM lokal) + dashboard dasar |
| 4 | Evaluation harness pada held-out set + buffer debugging integrasi + polish + pitch |

**Pembagian kerja (asumsi 1 kuat ML):**

| Orang | Fokus utama |
|---|---|
| A (kuat ML) | INA-CBG grouper + clinical compatibility + XGBoost/SHAP |
| B | Backend FastAPI + PostgreSQL + LanceDB + similarity engine + orchestration pipeline |
| C | Frontend dashboard + integrasi LLM lokal (Explanation, Review) |

Tumpang tindih disengaja: A & B sinkron skema data di Minggu 1; C mulai dengan data dummy sejak Minggu 1 agar tidak menunggu backend selesai.

**Alokasi waktu hasil percepatan AI coding tools:** dialihkan ke evaluation harness dan validasi domain INA-CBG — bukan fitur tambahan baru.

## 15. Risks & Mitigations

| Risiko | Mitigasi |
|---|---|
| Tautologi data sintetis (detector mendeteksi pola yang ditanam sendiri) | Pemisahan peran pembuat data vs detector, held-out test set |
| Klaim "explainable ML" padahal rule-based hardcode | Pisahkan tegas: skor dari SHAP/model, narasi dari LLM |
| Overengineering tech stack untuk 3 orang/4 minggu | Konsolidasi database, 1 model per tugas, Neo4j & LangGraph penuh di-drop |
| Domain gap (tidak grounded ke INA-CBG) | Simplified grouper wajib ada di Clinical Agent, bukan opsional |
| Model lokal gagal schema-adherence/kualitas Bahasa Indonesia rendah | Benchmark wajib Minggu 1 (Section 7.3) sebelum commit; fallback ke `GeminiClient` via abstraksi `LLMClient` bila perlu |
| Kuota Gemini API free tier habis/throttle saat butuh evaluasi bulk | Cek limit terkini sebelum bergantung untuk proses volume besar; `OllamaClient` tetap jalur utama tidak bergantung kuota eksternal |
| Laptop dev (GPU 8GB) jadi single point of failure tim | Klarifikasi Section 7.4: semua anggota install Ollama + model yang sama sebagai fallback |
| Automation bias verifier (rubber-stamp top-K) | Transparansi bahwa ini rekomendasi bukan vonis; audit sampling acak dicatat sebagai future work |
| Kegagalan integrasi saat demo | Minimalkan jumlah service berjalan; LLM lokal = tidak bergantung internet; buffer Minggu 4 khusus debugging |
| Error propagation antar-agent | Pydantic schema terstruktur untuk validasi I/O tiap agent |

## 16. Open Questions (Perlu Diputuskan Tim)

- Siapa pemilik domain knowledge INA-CBG/clinical pathway di tim — atau semua belajar dari nol dari dokumentasi publik?
- Distribusi development LLM lokal: server tunggal via LAN atau tiap orang setup sendiri? (Section 7.4)
- Apakah 4 minggu ini murni fase development, atau termasuk waktu menyusun proposal itu sendiri?

---

*Dokumen ini adalah versi eksekusi dari proposal konsep lengkap (lihat `Healthkathon_2026_JKN_Agentic_Risk_Intelligence_Proposal.md`), difokuskan untuk keputusan yang bisa langsung dijalankan tim dalam 4 minggu. Untuk spesifikasi detail tiap agent lihat `AGENTS.md`, untuk teknik ML dan skema dataset lihat `MODELS.md`, untuk alur demo dan spesifikasi UI lihat `FRONTEND.md`.*