# Healthkathon 2026 — Proposal Konsep
# JKN Agentic Risk Intelligence

> **Tagline:** Detect Smarter, Protect JKN  
> **Working Title:** JKN Agentic Risk Intelligence (J-ARI)  
> **Focus:** AI-powered multi-agent pre-verification and claim risk intelligence for JKN  
> **Primary Category:** Efisiensi Risiko pada Fasilitas Kesehatan  
> **Primary Risk Focus:** Manipulasi Diagnosis/Tindakan (Upcoding) dan Tindakan Pengobatan Tidak Sesuai Indikasi Medis  
> **Supporting Risk Signals:** Cloning, Repeat Billing, Cost Anomaly, Temporal/Behavioral Anomaly  
> **Decision Principle:** AI recommends and explains; human verifier makes the final decision.

---

## 1. Ringkasan Eksekutif

Healthkathon 2026 BPJS Kesehatan mengangkat tema utama:

> **“Detect Smarter, Protect JKN - Smarter Protection for a Stronger JKN: Efisiensi Risiko Program JKN.”**

Kompetisi berfokus pada tiga kategori besar:

1. Efisiensi Risiko pada Peserta
2. Efisiensi Risiko pada Fasilitas Kesehatan
3. Efisiensi Risiko pada Pemberi Kerja

Setelah membandingkan ketiga kategori tersebut dengan kebutuhan dan arah transformasi digital BPJS Kesehatan yang terlihat secara publik pada 2025–2026, kategori yang paling strategis untuk dikembangkan adalah:

> **Efisiensi Risiko pada Fasilitas Kesehatan**

Alasan utamanya adalah area ini bersinggungan langsung dengan beberapa kebutuhan penting Program JKN: efisiensi dan ketepatan proses klaim, penguatan anti-fraud, deteksi dini berbasis teknologi, clinical pathway, pengurangan variasi pelayanan, dan pemanfaatan AI/data analytics.

Namun, project ini **tidak dimaksudkan untuk sekadar membuat “AI fraud detector”**. BPJS sudah memiliki proses dan pengembangan terkait anomaly analysis, claim analysis, smart analytics, dan anti-fraud. Karena itu, nilai tambah project diarahkan pada sebuah **intelligent pre-verification layer** yang:

- menggabungkan banyak variabel klaim secara bersamaan;
- memahami konteks klinis;
- menggunakan beberapa metode analitik dan AI yang saling melengkapi;
- menggunakan multi-agent workflow untuk investigasi multi-langkah;
- memberikan risk score yang reproducible;
- memberikan evidence dan alasan yang dapat diaudit;
- menentukan prioritas klaim untuk human verification;
- **tidak mengambil keputusan fraud secara otomatis.**

Konsep akhirnya:

> **JKN Agentic Risk Intelligence adalah sistem investigasi risiko klaim berbasis multi-agent yang memadukan clinical reasoning, machine learning, anomaly detection, similarity/graph analysis, explainable risk scoring, dan human-in-the-loop untuk membantu BPJS memprioritaskan klaim yang paling membutuhkan pemeriksaan.**

---

# 2. Tentang Healthkathon 2026

## Tema Utama

**Detect Smarter, Protect JKN - Smarter Protection for a Stronger JKN: Efisiensi Risiko Program JKN**

Healthkathon 2026 meminta peserta mengembangkan solusi berbasis teknologi terkini, termasuk AI dan analitik data, untuk:

- mengidentifikasi potensi risiko;
- mendeteksi potensi risiko;
- memitigasi potensi risiko;
- meningkatkan efisiensi;
- menjaga integritas Program JKN.

## Tiga Kategori Utama

### A. Efisiensi Risiko pada Peserta

Empat subkategori:

1. Pemalsuan data/identitas peserta
2. Penyalahgunaan identitas peserta
3. Pelayanan yang tidak perlu
4. Penyalahgunaan obat/alkes

### B. Efisiensi Risiko pada Fasilitas Kesehatan

Dua puluh subkategori:

1. Penyalahgunaan dana kapitasi/nonkapitasi
2. Manipulasi klaim nonkapitasi
3. Rujukan tidak sesuai
4. Manipulasi diagnosis dan/atau tindakan (upcoding)
5. Cloning (penjiplakan klaim)
6. Phantom billing (klaim palsu)
7. Inflated bills (penggelembungan tagihan)
8. Pemecahan episode
9. Services unbundling / fragmentation
10. Self-referral
11. Repeat billing
12. Prolonged length of stay
13. Manipulasi kelas perawatan
14. Menagihkan tindakan yang tidak dilakukan
15. Tindakan pengobatan tidak sesuai indikasi medis
16. Readmisi
17. Klaim fiktif obat/alkes/tindakan
18. Pengurangan jumlah obat
19. Inflated bills
20. Manipulasi hasil pemeriksaan

### C. Efisiensi Risiko pada Pemberi Kerja

Enam subkategori:

1. Pendaftaran Pekerja Sebagian (PDUK)
2. Pelaporan Upah Lebih Rendah
3. Penggelapan/Penundaan Setoran Iuran
4. Misklasifikasi Status Hubungan Kerja
5. Manipulasi Data Mutasi Karyawan
6. Kolusi Fasilitas Kesehatan / Surat Keterangan Fiktif

---

# 3. Mengapa Memilih Efisiensi Risiko pada Fasilitas Kesehatan?

## 3.1 Kesesuaian dengan kebutuhan BPJS

Dari riset publik 2026, terdapat beberapa sinyal yang kuat:

### Penguatan anti-fraud dan early detection

DJSN dan BPJS Kesehatan pada Juni 2026 membahas penguatan pengawasan, integritas JKN, mitigasi fraud, dan optimalisasi deteksi dini berbasis teknologi.

Ini sangat selaras dengan risk detection engine dan AI-assisted investigation.

### Claim efficiency

Laporan Kemenkes/Pusbikes yang dibahas pada 2026 menunjukkan besarnya nilai klaim yang diproses dan masih adanya klaim pending/dispute pada sampel rumah sakit.

Artinya ada kebutuhan yang tidak hanya terkait fraud, tetapi juga:

- ketepatan klaim;
- verifikasi;
- kualitas data;
- efisiensi proses;
- pengurangan pekerjaan manual.

### AI dan data analytics

BPJS pada 2026 telah menyampaikan bahwa mereka telah mengembangkan chatbot, analisis klaim, dan smart analytics, tetapi masih terdapat gap dalam pengembangan model dan pemanfaatan data. Salah satu poin yang menarik adalah analisis klaim belum mampu membaca banyak variabel.

Ini justru menjadi celah untuk project yang bersifat **multi-variable intelligence**.

### Clinical pathway

Clinical pathway menjadi bagian penting dari arah roadmap anti-fraud 2026.

Artinya evaluasi tidak cukup hanya menanyakan:

> “Apakah klaim ini pernah terjadi?”

tetapi harus mulai menuju:

> “Apakah diagnosis, tindakan, obat, dan episode pelayanan masuk akal secara klinis dalam konteks kasus tersebut?”

### Domain grounding: INA-CBG

Klaim JKN dibayar menggunakan sistem **INA-CBG (Indonesia Case Base Groups)** — grouper yang menentukan tarif berdasarkan diagnosis primer/sekunder, prosedur, dan **severity level (termasuk CC/MCC — complication & comorbidity)**. Ini bukan detail teknis pinggiran: definisi "upcoding" pada konteks JKN secara spesifik umumnya berarti memanipulasi input grouper — misalnya menaikkan severity level atau menambahkan diagnosis komplikasi yang tidak sesuai kondisi riil pasien — agar klaim jatuh ke CBG group dengan tarif lebih tinggi.

Sistem yang hanya menilai "apakah prosedur cocok dengan diagnosis" secara generik **tidak** menangkap pola upcoding yang paling umum terjadi di JKN, yaitu manipulasi pada level severity/CC-MCC, bukan pada level diagnosis-prosedur itu sendiri. Karena itu, versi sederhana dari logika grouper INA-CBG (mapping diagnosis+prosedur+severity → CBG group → tarif) harus menjadi bagian eksplisit dari Clinical Reasoning Agent dan Financial Risk Engine, bukan cuma "clinical pathway" generik.

> **Catatan implementasi:** untuk MVP, tidak perlu replikasi grouper INA-CBG secara penuh (itu sistem kompleks resmi Kemenkes). Cukup rule-based simplified grouper yang menangkap logika inti (severity level shift → tarif shift) berdasarkan dokumentasi publik yang tersedia, dengan disclaimer eksplisit bahwa ini adalah simplifikasi untuk demonstrasi.

---

# 4. Perbandingan Kategori

Alih-alih skor internal yang subjektif, perbandingan berikut menggunakan kriteria yang dapat diverifikasi secara eksternal:

| Kategori | Tersedia dokumentasi publik BPJS (INA-CBG, clinical pathway, dsb.)? | Sinyal berbasis data terstruktur (bukan investigasi lapangan)? | Jumlah subkategori dengan proxy data yang jelas |
|---|---|---|---|
| Fasilitas Kesehatan | Ya — INA-CBG grouper terdokumentasi publik | Ya, sebagian besar (diagnosis, prosedur, biaya, LOS) | Tinggi (mis. upcoding, cloning, repeat billing, cost anomaly) |
| Pemberi Kerja | Terbatas — data upah/kepesertaan tidak terbuka publik | Sebagian, butuh data payroll yang sensitif | Sedang |
| Peserta | Terbatas — identitas/pemalsuan butuh verifikasi lapangan | Rendah untuk sebagian besar subkategori | Rendah–sedang |

> Catatan: tabel skor "Penilaian Strategis" pada draf sebelumnya dibuang karena skornya ditetapkan sendiri tanpa kriteria eksternal yang bisa diverifikasi — berisiko terbaca sebagai justifikasi pasca-keputusan, bukan analisis. Kesimpulan (Fasilitas Kesehatan) tidak berubah, tapi alasannya sekarang dapat diperiksa: kategori ini satu-satunya yang punya standar teknis publik (INA-CBG) yang bisa dijadikan ground truth struktural.

---

# 5. Subkategori yang Diprioritaskan

## Prioritas Utama

### 1. Manipulasi Diagnosis dan/atau Tindakan (Upcoding)

Kenapa menarik:

- sangat cocok untuk AI/ML;
- dapat dikaitkan dengan clinical pathway;
- memiliki dimensi coding, diagnosis, procedure, dan cost;
- dapat dinilai menggunakan peer-group analysis;
- dapat dipadukan dengan anomaly detection;
- dapat dijelaskan dengan evidence.

### 2. Tindakan Pengobatan Tidak Sesuai Indikasi Medis

Kenapa menarik:

- sangat dekat dengan clinical pathway;
- membutuhkan clinical reasoning;
- dapat membandingkan diagnosis → tindakan → obat;
- cocok untuk retrieval + rule engine + ML + LLM reasoning;
- dapat dijadikan use case utama yang menunjukkan kecerdasan sistem.

## Supporting Signals

### 3. Cloning

Mencari kemiripan yang tidak wajar antara klaim:

- diagnosis;
- procedure;
- medication;
- chronology;
- medical record structure;
- provider;
- biaya.

### 4. Repeat Billing

Mencari klaim yang sebenarnya sudah ditagihkan/dibayar atau sangat mungkin merupakan episode yang sama.

### 5. Cost Anomaly

Membandingkan klaim dengan kasus sejenis:

- fasilitas sejenis;
- diagnosis sama;
- procedure sama;
- regional peer group;
- histori provider.

### 6. Temporal / Behavioral Anomaly

Menemukan pola seperti:

- jumlah tindakan tidak wajar;
- perubahan frekuensi mendadak;
- pola klaim yang terlalu teratur;
- cluster pasien/tindakan tertentu;
- perubahan perilaku provider.

---

# 6. Masalah yang Ingin Diselesaikan

## Problem Statement

Volume data pelayanan dan klaim JKN sangat besar. Pemeriksaan manual tidak ideal untuk menilai seluruh klaim dengan kedalaman yang sama.

Di sisi lain, risiko dapat muncul dalam berbagai bentuk:

- ketidaksesuaian diagnosis dan tindakan;
- tindakan yang tidak sejalan dengan clinical pathway;
- klaim dengan biaya tidak wajar;
- duplikasi/kemiripan klaim;
- pola provider yang abnormal;
- episode pelayanan yang berulang;
- kombinasi anomali yang baru terlihat ketika beberapa sumber data dibandingkan sekaligus.

Sistem yang hanya menjawab:

> **Fraud / Not Fraud**

terlalu sederhana.

Yang lebih dibutuhkan:

> **Risk identification → evidence gathering → explanation → prioritization → human verification**

---

# 7. Visi Produk

## JKN Agentic Risk Intelligence

Sebuah **AI-assisted claim investigation platform** yang bertindak seperti “tim investigator digital” bagi verifier BPJS.

Sistem tidak mengambil keputusan fraud secara otomatis.

Sistem membantu menjawab:

### “Klaim mana yang paling perlu diperiksa?”

dan

### “Kenapa klaim tersebut dianggap berisiko?”

---

# 8. Nilai Utama Produk

## 8.1 Multi-variable intelligence

Satu klaim dapat dianalisis dari banyak dimensi:

- pasien;
- diagnosis;
- tindakan;
- obat;
- dokter;
- fasilitas;
- biaya;
- LOS;
- rujukan;
- histori;
- clinical pathway;
- kemiripan klaim;
- pola waktu.

## 8.2 Clinical context

Sistem tidak hanya melihat angka.

Sistem mencoba memahami hubungan:

> Diagnosis → Procedure → Medication → Pathway → Episode

## 8.3 Explainable risk

Setiap risk score harus memiliki evidence — dan sumber evidence harus eksplisit dipisahkan menjadi dua lapisan agar klaim "explainable" tidak menyesatkan:

1. **Skor numerik** dihasilkan dari model ML (feature importance / SHAP value dari XGBoost, atau rule threshold untuk komponen deterministik). Ini bagian yang benar-benar "explainable" dalam arti teknis — bisa ditelusuri ke fitur dan bobot yang diverifikasi.
2. **Narasi/laporan** dihasilkan oleh LLM (Explanation Agent) yang **merangkai** hasil skor tsb menjadi bahasa manusia — LLM tidak menentukan angka, hanya menerjemahkan angka + evidence yang sudah ada menjadi kalimat.

Contoh breakdown (angka berasal dari SHAP value, bukan ditetapkan manual):

- Clinical deviation: +30
- Cost anomaly: +25
- Similarity: +20
- Provider pattern: +15
- Temporal anomaly: +10

> Jika breakdown ini pada praktiknya adalah bobot yang di-hardcode manual (bukan hasil model), maka harus disebut sebagai **rule-based scorecard**, bukan "ML explainable scoring" — dua klaim ini punya bobot kredibilitas yang berbeda di mata juri teknis.

## 8.4 Prioritization

Alih-alih memberikan ribuan alert tanpa urutan, sistem menyediakan:

> Priority Queue

Contoh:

| Rank | Claim | Risk Score | Status |
|---|---|---:|---|
| 1 | CLM-001 | 97 | High |
| 2 | CLM-019 | 94 | High |
| 3 | CLM-044 | 91 | High |
| 4 | CLM-132 | 81 | Medium |

## 8.5 Human-in-the-loop

AI tidak boleh menjadi hakim.

Output:

> **High Risk — Requires Verification**

Bukan:

> **Confirmed Fraud**

---

# 9. Konsep “AI Satpam BPJS”

Analogi sederhana:

BPJS memiliki sangat banyak klaim.

AI kita berperan seperti satpam pintar:

> “Aku tidak bilang klaim ini pasti fraud. Tapi aku menemukan beberapa hal aneh. Coba diperiksa dulu.”

Contoh:

> “Diagnosis X biasanya mengikuti pathway A-B-C, tetapi klaim ini memiliki tindakan Y yang membutuhkan evidence tambahan.”

> “Biaya 43% di atas peer group.”

> “Klaim memiliki similarity 93% dengan 6 klaim sebelumnya.”

Lalu manusia yang memutuskan tindakan berikutnya.

---

# 10. Mengapa Menggunakan AI Agent?

## Jawaban singkat

**Cocok, karena investigasi klaim bersifat multi-step, multi-domain, dan membutuhkan banyak tools.**

Satu model yang menerima semua data dan memberi satu angka tidak cukup menggambarkan proses investigasi.

AI Agent dapat:

- memiliki tujuan;
- memilih tools;
- mengambil data;
- meminta analisis specialist;
- membaca hasil;
- menggabungkan evidence;
- meminta pemeriksaan lanjutan;
- membuat laporan.

Dengan demikian agent lebih cocok untuk:

> **investigation workflow**

daripada sekadar:

> **single-shot prediction**

---

# 11. Kenapa Tidak Menjadikan Semua Komponen Sebagai Agent?

Karena tidak semua pekerjaan membutuhkan reasoning berbasis LLM.

Contoh:

### Duplicate exact match

Tidak perlu agent.

Gunakan deterministic matching.

### Cost anomaly

Tidak perlu LLM.

Gunakan:

- statistical model;
- XGBoost;
- Isolation Forest;
- peer benchmark.

### Similarity

Gunakan:

- embeddings;
- vector database;
- similarity score.

### Graph relationship

Gunakan:

- Neo4j / graph engine.

Agent hanya menggunakan hasil dari komponen tersebut dan melakukan reasoning/orchestration.

---

# 12. Arsitektur yang Direkomendasikan

## Hybrid Agentic Architecture

```text
                       CLAIM
                         |
                         v
                DATA VALIDATION
                / DETERMINISTIC
                         |
                         v
              CASE MANAGER AGENT
                         |
         +---------------+---------------+
         |               |               |
         v               v               v
   CLINICAL AGENT   FINANCIAL ENGINE   FRAUD AGENT
         |               |               |
         |            ML Models      Graph/Search
         |                               |
         |                               |
         +---------------+---------------+
                         |
                         v
                  REVIEW AGENT
                         |
                  Cross-check evidence
                         |
                         v
                 RISK SCORE ENGINE
                    / ML + Rules
                         |
                         v
               EXPLANATION AGENT
                         |
                         v
                  HUMAN REVIEWER
```

---

# 13. Agent yang Akan Dikembangkan

## 13.1 Case Manager Agent

### Peran

Orchestrator utama.

### Tugas

- menerima kasus;
- menentukan analisis yang dibutuhkan;
- memanggil agent/tool;
- mengelola workflow;
- memastikan semua evidence terkumpul.

### Contoh

> “Claim ini memiliki indikasi clinical deviation dan cost anomaly. Saya akan menjalankan Clinical Analysis dan Financial Analysis secara paralel.”

---

## 13.2 Clinical Reasoning Agent

### Peran

Spesialis clinical context.

### Tugas

- memeriksa diagnosis;
- procedure;
- medication;
- LOS;
- clinical pathway;
- indication;
- supporting evidence.

### Output

```text
Clinical Risk: 88/100

Evidence:
- Procedure Y is unusual for diagnosis X.
- Additional clinical justification may be required.
- Current episode deviates from expected pathway.
```

Agent ini tidak memberikan diagnosis medis baru kepada pasien. Fokusnya adalah **risk analysis terhadap klaim**.

---

## 13.3 Financial Risk Engine

Komponen ini sebaiknya bukan LLM Agent murni.

### Teknologi

- XGBoost;
- Isolation Forest;
- statistical benchmarking;
- peer-group analysis.

### Tugas

- menghitung cost anomaly;
- membandingkan provider;
- menemukan outlier;
- menghasilkan feature importance.

### Contoh

```text
Expected range: Rp4.8–6.1M
Actual claim: Rp8.9M
Deviation: +54%
```

Agent/LLM hanya dipakai jika dibutuhkan untuk menjelaskan hasil.

---

## 13.4 Fraud / Pattern Investigation Agent

### Tugas

- mencari duplicate;
- mencari similar claims;
- memeriksa repeat billing;
- mencari temporal patterns;
- menggunakan graph database;
- menggabungkan historical behavior.

### Tools

- SQL;
- vector database;
- graph database;
- similarity engine;
- anomaly model.

### Contoh output

```text
Similar claims found: 6
Maximum similarity: 96%
Same provider: 5/6
Same procedure: 6/6
```

---

## 13.5 Evidence Review Agent

Ini salah satu bagian paling penting.

### Peran

Cross-check antar hasil.

Contoh:

```text
Clinical Agent:
HIGH

Financial Engine:
HIGH

Fraud Agent:
MEDIUM
```

Review Agent menyimpulkan:

> “Evidence supports elevated risk, but current evidence is insufficient to conclude fraud.”

Output:

> **High Risk / Requires Human Verification**

Bukan:

> **Confirmed Fraud**

---

## 13.6 Explanation Agent

Mengubah evidence teknis menjadi laporan untuk verifier.

### Output

```text
RISK: 92/100 — HIGH

Primary reasons:
1. Clinical pathway deviation
2. Cost +43% vs peer cases
3. Similarity with 6 prior claims

Recommendation:
Prioritize for manual verification.
```

---

# 14. Komponen Non-Agent

## Rule Engine

Untuk:

- exact duplicate;
- date contradiction;
- impossible sequence;
- mandatory-field checking;
- threshold rules.

## ML Engine

Untuk:

- fraud risk;
- anomaly detection;
- cost anomaly;
- provider anomaly.

## Similarity Engine

Untuk:

- cloning;
- semantic similarity;
- claim matching.

## Graph Engine

Untuk:

- patient-provider-facility relationships;
- doctor-procedure clusters;
- repeated suspicious relationships;
- anomaly clusters.

## Vector Database

Untuk:

- embeddings;
- similar claims;
- semantic retrieval.

## Data Layer

Untuk:

- claims;
- patient metadata;
- provider metadata;
- diagnosis;
- procedure;
- medication;
- historical claim.

---

# 15. Contoh End-to-End Investigasi

Misalkan ada klaim:

```text
Claim ID: CLM-202608001

Diagnosis:
Pneumonia

Procedure:
Procedure X

Medication:
A + B + C

Facility:
Hospital ABC

Cost:
Rp8.9M
```

## Step 1 — Case Manager

Memulai investigasi.

## Step 2 — Clinical Agent

Menilai hubungan:

> Pneumonia → Procedure X → medication

Hasil:

> Clinical Risk = 90

## Step 3 — Financial Engine

Membandingkan dengan peer group:

> Average comparable case = Rp5.7M  
> Current = Rp8.9M

Hasil:

> Cost Risk = 87

## Step 4 — Fraud Agent

Mencari similarity:

> 6 claims similarity >90%

Hasil:

> Pattern Risk = 82

## Step 5 — Review Agent

Menggabungkan evidence:

> High Risk

Tetapi:

> Tidak cukup bukti untuk menyatakan confirmed fraud.

## Step 6 — Risk Engine

Contoh scoring:

```text
Clinical Risk      30%
Financial Risk     25%
Similarity Risk    20%
Provider Pattern   15%
Temporal Risk      10%
```

Output:

> **92/100 — HIGH**

## Step 7 — Explanation

> “Klaim menunjukkan kombinasi deviasi clinical pathway, biaya di atas peer group, dan kemiripan tinggi dengan beberapa klaim sebelumnya. Klaim direkomendasikan untuk prioritas verifikasi manusia.”

---

# 16. Tampilan Dashboard

Konsep UI:

```text
+-----------------------------------------------------+
| JKN AGENTIC RISK INTELLIGENCE                      |
+-----------------------------------------------------+
| Total Claims               128,420                 |
| High Risk                    3,396                 |
| Medium Risk                 14,201                 |
| Low Risk                   110,823                 |
+-----------------------------------------------------+
| PRIORITY CLAIM                                      |
|                                                     |
| Claim ID: CLM-202608001                             |
| Facility: Hospital ABC                              |
|                                                     |
| Risk Score: 92/100   [HIGH]                         |
|                                                     |
| Clinical deviation              HIGH               |
| Cost anomaly                    HIGH               |
| Claim similarity                HIGH               |
| Provider behavior               MEDIUM             |
|                                                     |
| [View Evidence]  [Investigate]                     |
+-----------------------------------------------------+
```

---

# 17. “Investigation Timeline”

Untuk menunjukkan bahwa agent benar-benar bekerja.

Contoh UI:

```text
19:21:01  Case Manager     Case received
19:21:02  Clinical Agent   Pathway analysis started
19:21:03  Financial Engine Cost benchmark completed
19:21:03  Fraud Agent      Similarity search started
19:21:04  Fraud Agent      6 similar claims found
19:21:05  Review Agent     Evidence reconciliation
19:21:06  Risk Engine      Score calculated: 92
19:21:07  Explanation      Report generated
```

Ini dapat menjadi salah satu “wow factor” demo.

---

# 18. Graph Intelligence

Salah satu fitur advanced yang potensial.

Contoh:

```text
Patient A
    |
  Claim
    |
Procedure X
    |
Doctor Y
    |
Hospital Z
    |
+---+---+---+
|   |   |   |
C1  C2  C3  C4
```

Sistem dapat menemukan:

- 4 pasien;
- dokter sama;
- rumah sakit sama;
- procedure sama;
- waktu berdekatan;
- struktur klaim sangat mirip.

Kemudian:

> **Potential Anomalous Cluster**

Graph bukan pengganti seluruh ML, tetapi alat untuk menemukan relationships yang sulit terlihat dari satu record.

---

# 19. Explainable AI

## Prinsip

Jangan hanya:

> Risk = 94

Tetapi:

> Risk = 94 karena...

Contoh:

```text
Clinical deviation     +30
Cost anomaly           +24
Claim similarity       +18
Provider pattern       +14
Temporal anomaly        +8
                       ----
                        94
```

Kemudian evidence:

> “Claim cost is 42% above comparable claims.”

> “Procedure frequency is 3.8× above peer group.”

> “Six historical claims have similarity above 90%.”

---

# 20. Human-in-the-Loop

Flow:

```text
AI detects
     |
     v
AI explains
     |
     v
AI prioritizes
     |
     v
HUMAN VERIFIER
     |
  +--+--+
  |     |
Verify  Reject
  |
Further investigation
```

AI tidak memiliki kewenangan untuk:

- menuduh fraud;
- otomatis menolak klaim;
- mengambil keputusan administratif final;
- memberikan keputusan klinis kepada pasien.

---

# 21. Kenapa Multi-Agent?

## Cocok karena:

### 1. Investigasi adalah multi-step

Satu kasus membutuhkan beberapa pemeriksaan.

### 2. Domain berbeda

Clinical, financial, behavioral, graph, dan claims tidak identik.

### 3. Tools berbeda

Masing-masing specialist dapat memakai tool yang sesuai.

### 4. Modular

Model dapat diganti tanpa mengganti seluruh system.

### 5. Explainability lebih jelas

Setiap evidence dapat ditelusuri ke sumber/komponen.

### 6. Demo lebih kuat

Juri dapat melihat “tim investigator digital” bekerja.

---

# 22. Kenapa Multi-Agent Bisa Tidak Cocok?

## Risiko 1 — Error propagation

Jika agent pertama salah dan agent berikutnya mempercayainya, kesalahan dapat merambat.

## Risiko 2 — Overengineering

Tidak semua masalah membutuhkan agent.

## Risiko 3 — Latency

Banyak agent yang dijalankan secara serial akan lambat.

Solusi:

- parallel execution;
- caching;
- model routing.

## Risiko 4 — Cost

Banyak LLM calls dapat meningkatkan inference cost.

Solusi:

- small model;
- rules;
- classical ML;
- hanya gunakan LLM untuk reasoning yang memang membutuhkan LLM.

## Risiko 5 — Security / privacy

Agent yang memiliki terlalu banyak akses berpotensi berbahaya.

Solusi:

- least privilege;
- read-only access;
- tool whitelist;
- audit logging;
- strict schema;
- no direct arbitrary SQL;
- PII minimization.

## Risiko 6 — Governance

Healthcare membutuhkan:

- human oversight;
- auditability;
- reproducibility;
- accountability.

---

# 23. Prinsip Arsitektur: Hybrid > Everything-Agent

Kesimpulan teknis:

> **Jangan membuat semua komponen menjadi Agent.**

Gunakan:

### Deterministic

Untuk hal yang pasti.

### ML

Untuk prediksi dan anomaly scoring.

### Retrieval / vector search

Untuk similarity.

### Graph

Untuk relationships.

### Agent

Untuk:

- orchestration;
- tool use;
- multi-step reasoning;
- evidence synthesis;
- explanation.

Ini adalah kompromi terbaik antara:

> reliability + intelligence + demo value.

---

# 24. Tech Stack (Final — Diputuskan, Bukan Daftar Opsi)

> Revisi kedua: tim dikonfirmasi **3 orang** (bukan 3–4), dan setelah eksplorasi teknis lebih lanjut, dua keputusan besar berubah dari revisi pertama: (1) LLM berjalan **lokal via Ollama**, bukan API, memanfaatkan hardware dev yang tersedia (RTX 5050 8GB VRAM); (2) orkestrasi agent memakai **fungsi Python sequential/paralel + Pydantic**, bukan LangGraph — untuk mengurangi learning curve pada tim sekecil ini. Neo4j didrop sepenuhnya dari build (bukan cuma "1 pemilik penuh" seperti revisi sebelumnya) karena risikonya tetap tidak proporsional untuk tim 3 orang.
>
> Revisi ketiga: LLM lokal tetap jalur utama untuk demo, tapi ditambah **Gemini API (free tier) sebagai baseline benchmark + bukti production-path** — bukan pengganti lokal. Investigator Copilot (fitur chat terpisah) dibatalkan, digabung ke Explanation Agent sebagai QA Panel 4-tombol pra-set (lihat `AGENTS.md` Section 7.1) untuk menghindari risiko halusinasi live saat demo. Flow demo diperkaya jadi `Incoming Claims → AI Investigation (timeline) → Risk Assessment → Evidence → Human Decision` — detail lengkap di `FRONTEND.md`.
>
> Revisi keempat: dua koreksi setelah review build pertama — **(1)** similarity search pindah dari pgvector ke **LanceDB** (embedded vector store, tanpa server process terpisah); **(2)** perbaikan mental model kritis — halaman input klaim sebelumnya salah memposisikan BPJS Verifier sebagai operator yang mengetik detail klaim manual (Patient ID, Diagnosis, dst.), padahal Faskes bukan user J-ARI (Section 4) dan klaim seharusnya sudah ada saat masuk sistem. Halaman itu direstrukturisasi jadi **Incoming Claims** (daftar klaim yang sudah ada, verifier memilih bukan membuat) dengan **Demo Data Loader** terpisah untuk kebutuhan simulasi hackathon. Narasi digeser dari "AI memutuskan" ke "AI membantu menentukan prioritas verifikasi" — lihat `FRONTEND.md` koreksi #6.

## Backend

- Python + FastAPI

## Data — satu database relasional, LanceDB terpisah untuk vector (keduanya tetap minim infra)

- **PostgreSQL polos** untuk data relasional (claims, patients, providers, doctors) — konsolidasi dari rencana awal Postgres+Redis+Qdrant terpisah. Alasan: mengurangi permukaan kegagalan infra saat demo, bukan soal kecepatan development. **Bukan Supabase** — dipertimbangkan, lalu dibuang: fitur andalan Supabase (Auth, Realtime) tidak dibutuhkan struktural (sudah diputuskan tanpa sistem login) atau sudah ada alternatif murah, sementara backend developer belum familiar Supabase — menambah tool baru tanpa kompensasi manfaat sepadan untuk tim 3 orang.
- Redis **hanya jika** caching terbukti perlu setelah profiling — jangan tambahkan preventif.

## ML — satu model per tugas, bukan tiga kandidat

- **XGBoost** untuk cost anomaly / risk scoring (feature importance via SHAP untuk explainability)
- ~~Isolation Forest, LightGBM, PyTorch~~ — dicatat sebagai future work, bukan dibangun di MVP. Satu model per tugas lebih defensible daripada beberapa kandidat paralel untuk tim sekecil ini.
- ~~IndoBERT fine-tuning/training custom~~ — dipertimbangkan secara serius, sengaja dibuang. Fine-tuning encoder custom pada data sintetis buatan sendiri memperparah risiko tautologi (Section 25): model dijamin "berhasil" mengenali pola yang ditanam tim sendiri, dan jauh lebih sulit dipertanggungjawabkan ke juri dibanding XGBoost+SHAP yang feature importance-nya transparan. Skema data saat ini juga tidak memuat free-text clinical notes yang benar-benar butuh NER/encoder custom — kalau nanti ditambahkan, itu justifikasi baru, bukan sekarang.

## Similarity

- sentence-transformers (embedding) + **LanceDB** (bukan pgvector, FAISS, atau Qdrant terpisah) — LanceDB dipilih karena embedded (file-based, tanpa server process terpisah), konsisten dengan prinsip "jangan tambah service" yang sama dengan alasan drop Qdrant. Bedanya dari pgvector: LanceDB jadi store terpisah dari PostgreSQL, tapi tetap tidak menambah proses server baru untuk dijalankan/dipelihara.

## Graph

- **Static graph view (D3.js/vis.js) dari JSON precompute** — Neo4j didrop sepenuhnya dari build. Nilai tambah query graph live tidak proporsional dengan waktu yang harus dikuasai 1 orang dari 3 anggota tim. Visualisasi relationship provider-doctor-patient tetap bisa didemonstrasikan secara meyakinkan tanpa infra tambahan. Neo4j dicatat sebagai item roadmap produksi, bukan MVP.

## Agent orchestration

- **Fungsi Python sequential/paralel (`asyncio.gather`) + Pydantic schema**, bukan LangGraph/AutoGen/CrewAI. Untuk tim 3 orang dalam 4 minggu, framework orchestration menambah learning curve tanpa manfaat proporsional pada skala MVP — 3 agent (Clinical, Financial, Fraud) berjalan paralel, diikuti Review lalu Explanation secara berurutan, dengan I/O Pydantic yang tervalidasi di setiap langkah. Ini tetap "agentic pipeline" yang jujur — yang membuat sesuatu agentic adalah pembagian tanggung jawab + reasoning per unit kerja, bukan framework spesifik.
- LangGraph tetap opsional untuk 1–2 node saja (mis. Clinical + Review) bila salah satu anggota tim sudah fasih dan ingin menjadikannya differentiator eksplisit — bukan untuk seluruh pipeline.

## LLM — lokal via Ollama untuk demo, Gemini API sebagai benchmark & production-path

- **Ollama (lokal)** sebagai jalur demo utama: `qwen2.5:7b` (Explanation, narasi Bahasa Indonesia), `mistral:7b` (Clinical/Financial, structured output), `qwen2.5:3b`/`llama3.2:3b` (Case Manager/routing), opsional `deepseek-r1:7b` (Review — reasoning trace jadi bahan audit tambahan, bukan sumber skor).
- Dipilih lokal untuk demo (bukan API) karena: data sintetis tidak butuh privasi API; hardware dev (RTX 5050 8GB VRAM) cukup untuk model 7B penuh di GPU; demo tidak bergantung uptime/koneksi internet saat momen presentasi; biaya nol untuk iterasi development intensif.
- **Gemini API (free tier) dipakai paralel, bukan alternatif eksklusif** — sebagai **(1)** baseline pembanding kualitas saat benchmark (Section di bawah), **(2)** bukti konkret "production path" untuk kriteria Kesiapan & Skalabilitas — implementasi nyata, bukan klaim kosong di slide. Klarifikasi penting: **Google AI Pro (subscription $19.99/bulan) bukan sumber kuota untuk Gemini API** yang dipanggil dari backend — itu menaikkan kuota di produk Google sendiri (app Gemini, Antigravity/Code Assist, Android Studio). Gemini API cukup API key gratis dari AI Studio, terpisah dari keputusan berlangganan AI Pro.
- Arsitektur **swappable** lewat satu interface (`LLMClient` protocol: `OllamaClient` dan `GeminiClient`) — kalau kualitas model lokal di suatu role ternyata tidak cukup, tinggal ganti implementasi tanpa mengubah kode pemanggil.
- **Wajib benchmark sebelum commit** (Minggu 1, ~1-2 jam): uji `qwen2.5:7b` vs `mistral:7b` vs `qwen3:8b` (bila sempat di-pull) **vs Gemini Flash sebagai baseline** pada 5-10 contoh klaim sintetis, ukur schema validity rate, kualitas Bahasa Indonesia, dan latency (Gemini tidak diukur latency untuk keputusan demo, hanya kualitas). Pilih model lokal untuk jalur demo berdasarkan angka, catat gap terhadap Gemini untuk narasi production-path.
- **Waspada kuota:** rate limit Gemini API free tier berubah dari waktu ke waktu — cek dokumentasi resmi sebelum bergantung untuk proses bulk (evaluasi ratusan klaim sekaligus). `OllamaClient` tetap jalur utama yang tidak bergantung kuota eksternal.
- Prinsip non-negotiable tetap berlaku: skor numerik SELALU dari model ML/rule (XGBoost+SHAP, grouper lookup), LLM (lokal maupun Gemini) hanya untuk reasoning tekstual dan narasi — termasuk reasoning trace `deepseek-r1`, yang tetap harus diberi label sebagai bahan pendukung, bukan skor otoritatif.

## Frontend

- React + Vite + Tailwind CSS

## Peran AI coding tools (Claude Code / Codex / Antigravity, dsb.)

AI tools mempercepat **penulisan kode untuk spesifikasi yang sudah jelas** — bukan judgment arsitektur, bukan debugging integrasi cross-service, dan bukan validasi kebenaran domain (INA-CBG, clinical pathway). Waktu yang dihemat dari boilerplate (endpoint API, dashboard component, orchestration function) harus dialokasikan ke:
1. Evaluation harness yang proper (precision/recall/PR-AUC dengan train/test split yang jujur — lihat Section 25 untuk metodologi data)
2. Validasi domain INA-CBG dengan dokumentasi publik
3. Buffer untuk debugging integrasi, bukan fitur tambahan baru

---

# 25. Dataset

## Ideal

Data yang tersedia dari panitia:

- claims;
- diagnosis;
- procedure;
- medication;
- provider;
- facility;
- cost;
- LOS;
- referral;
- historical claims.

## Jika data asli tidak tersedia

Gunakan:

> **Synthetic / de-identified data**

yang mempertahankan struktur problem nyata tanpa menggunakan data kesehatan pribadi.

Contoh synthetic record:

```json
{
  "claim_id": "CLM-001",
  "diagnosis": "DX_A",
  "procedure": "PROC_X",
  "medication": ["MED_A", "MED_B"],
  "facility": "FAC_12",
  "doctor": "DR_08",
  "cost": 8900000,
  "los": 6
}
```

Data sintetis harus diberi label jelas:

> “Synthetic data for demonstration.”

### Metodologi anti-tautologi

Risiko metodologis: jika tim yang sama membuat fraud pattern sekaligus men-tuning detector, sistem dijamin berhasil mendeteksi pola yang ditanam sendiri — ini bukan bukti generalisasi, hanya bukti konsistensi internal. Mitigasi untuk tim 3 orang:

- Pisahkan peran: 1 anggota membuat dataset (termasuk fraud pattern + noise/variasi acak) tanpa melihat desain detector; anggota lain membangun detector tanpa tahu persis pola apa yang ditanam di held-out test set.
- Sisipkan variasi/noise yang tidak diketahui oleh sisi detector (mis. severity level yang di-random dalam batas wajar, bukan pola upcoding yang selalu identik).
- Laporkan metrik pada held-out set yang genuinely tidak dilihat saat tuning, bukan seluruh dataset yang sama dipakai untuk training dan evaluasi.

---

# 26. Rencana MVP

## MVP Goal

Bukan membangun sistem produksi BPJS.

MVP harus membuktikan:

> **“AI dapat membantu menemukan dan menjelaskan risiko klaim secara multi-dimensional.”**

## MVP Features

### Must Have

- claim ingestion;
- validation;
- clinical risk;
- cost anomaly;
- similarity detection;
- risk score;
- explanation;
- dashboard;
- human verification state.

### Should Have

- graph view;
- multi-agent orchestration;
- agent activity timeline;
- priority queue.

### Nice to Have

- scenario simulation;
- what-if analysis;
- provider risk profile;
- cluster detection;
- feedback loop dari verifier.

---

# 27. Roadmap Pengembangan (4 Minggu, Tim 3 Orang)

> Diperbarui dari roadmap 6-fase generik. Diasumsikan dataset tidak disediakan panitia (kemungkinan besar bikin sendiri) dan tim bekerja paruh waktu (~15–20 jam/orang/minggu, total ~180–240 person-hours).

## Minggu 1 — Data Foundation + INA-CBG Grounding

- Skema data (claim, diagnosis, procedure, medication, provider, facility, cost, LOS)
- Simplified INA-CBG grouper logic (severity level, CC/MCC → tarif group) berdasarkan dokumentasi publik
- Dataset sintetis dengan metodologi anti-tautologi (Section 25): pemisahan peran pembuat data vs detector
- Rules/deterministic baseline (exact duplicate, mandatory-field check)

## Minggu 2 — Clinical Layer + Financial Engine

- Diagnosis→procedure→medication compatibility check, terhubung ke logika INA-CBG
- XGBoost cost anomaly model + SHAP untuk explainability
- Isolation Forest untuk anomaly baseline
- Similarity engine (sentence-transformers + pgvector)

## Minggu 3 — Orchestration Pipeline + Explanation

- Orchestration pipeline (Section 6 PRD): Case Manager, Clinical, Fraud/Pattern paralel via `asyncio.gather`, lalu Review, lalu Explanation — I/O Pydantic tervalidasi tiap langkah
- Static graph view (D3.js/vis.js) dari JSON precompute untuk relasi provider-doctor-patient
- Explanation layer via LLM lokal (Ollama), narasi Bahasa Indonesia
- Dashboard dasar: priority queue + evidence view

## Minggu 4 — Evaluation, Buffer, Pitch

- Evaluation harness pada held-out set (precision/recall/PR-AUC, bukan seluruh dataset yang sama dipakai training+eval)
- Buffer untuk debugging integrasi (bukan fitur baru)
- Investigation timeline / polish dashboard (nice-to-have, hanya jika waktu tersisa)
- Cerita pitch: problem → insight (INA-CBG grounding) → solution → impact

---

# 28. Metrik Evaluasi

Jangan hanya mengatakan:

> “accuracy 95%.”

Karena fraud/risk detection biasanya memiliki class imbalance.

Gunakan:

## Model metrics

- Precision
- Recall
- F1
- PR-AUC
- ROC-AUC
- False Positive Rate

## Operational metrics

- Top-K detection rate
- investigator workload reduction
- average investigation time
- percentage of high-risk cases correctly prioritized

## Explainability

- evidence completeness;
- evidence traceability;
- agreement with reference labels;
- human reviewer usefulness.

## Agent metrics

- task completion;
- tool-call success;
- hallucination/error rate;
- invalid action rate;
- average steps;
- latency.

---

# 29. Success Criteria MVP

Contoh target internal:

> Sistem mampu memprioritaskan sebagian besar contoh risiko tinggi ke dalam top-K queue.

> Sistem menghasilkan evidence yang dapat dilacak ke fitur/data.

> Sistem tidak membuat klaim “fraud confirmed” secara otomatis.

> Sistem dapat membedakan minimal:
> - clinical anomaly,
> - financial anomaly,
> - similarity anomaly.

> Sistem menunjukkan pengurangan workload reviewer pada skenario simulasi.

> Semua output agent tercatat dalam audit log.

Angka target final harus disesuaikan setelah dataset dan baseline tersedia.

---

# 30. Potensi Keunggulan Kompetitif

## Bukan AI biasa

Bukan:

> “We use an LLM to detect fraud.”

Tetapi:

> “We build an agentic investigation layer that orchestrates specialized AI and analytical engines.”

## Bukan hanya fraud detection

Tetapi:

> **risk intelligence**

## Bukan hanya prediction

Tetapi:

> **evidence + explanation + prioritization**

## Bukan menggantikan BPJS

Tetapi:

> **augmenting verifier BPJS**

## Bukan black box

Tetapi:

> **auditable workflow**

---

# 31. Positioning untuk Juri

## Problem

> Volume dan kompleksitas klaim JKN membuat pemeriksaan manual dan single-variable analysis tidak selalu cukup untuk menemukan pola risiko yang tersembunyi.

## Insight

> Risiko klaim bersifat multidimensional: clinical, financial, behavioral, temporal, dan relational.

## Solution

> JKN Agentic Risk Intelligence menggabungkan specialist AI agents, deterministic rules, machine learning, similarity search, graph analytics, dan explainable risk scoring.

## Impact

> Membantu verifier fokus pada klaim paling berisiko, mempercepat investigasi, mengurangi false alarm, dan mendukung integritas serta efisiensi Program JKN.

---

# 32. Pitch Satu Kalimat

> **“JKN Agentic Risk Intelligence adalah tim investigator digital berbasis AI yang menganalisis klaim JKN dari sisi klinis, finansial, dan pola perilaku untuk menemukan, menjelaskan, dan memprioritaskan risiko sebelum ditinjau oleh manusia.”**

---

# 33. Pitch Bahasa Sederhana

> “Bayangkan BPJS menerima jutaan klaim. AI kami bertindak seperti tim satpam pintar. Ada satu agent yang mengecek sisi medis, agent lain mengecek biaya, agent lain mencari pola klaim yang mencurigakan. Kemudian mereka saling memeriksa bukti, menghitung risk score, dan memberi tahu petugas BPJS klaim mana yang sebaiknya diperiksa lebih dulu — tanpa menggantikan keputusan manusia.”

---

# 34. Yang Tidak Akan Kita Klaim

Agar proposal tetap kredibel, kita **tidak** mengatakan:

- “AI kami bisa mengetahui fraud secara pasti.”
- “AI kami menggantikan verifier BPJS.”
- “Sistem kami lebih baik daripada sistem internal BPJS.”
- “BPJS belum memiliki anti-fraud system.”
- “BPJS tidak memiliki graph analytics internal.”
- “Semua fitur yang kita buat belum pernah dibuat BPJS.”

Framing yang benar:

> “Berdasarkan informasi publik yang tersedia, kami melihat opportunity untuk membangun complementary intelligence layer yang memperkaya multi-variable analysis, explainability, prioritization, dan agentic investigation workflow.”

---

# 35. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| False positive | Tinggi | Human review |
| False negative | Tinggi | Multi-model + monitoring |
| Hallucination | Tinggi | Structured output + RAG + tool grounding |
| Privacy leakage | Sangat tinggi | De-identification + least privilege |
| Bias | Tinggi | Dataset audit + subgroup evaluation |
| Agent loop | Sedang | Max step limit + state machine |
| Cost inference | Sedang | Model routing |
| Latency | Sedang | Parallel agent execution |
| Explainability rendah | Tinggi | Evidence-based report |
| Data tidak tersedia | Tinggi | Synthetic/de-identified dataset |

---

# 36. Arsitektur Keamanan Agent

Agent harus memiliki:

- tool whitelist;
- read-only default;
- structured arguments;
- schema validation;
- permission boundaries;
- timeout;
- max step;
- audit logs;
- no unrestricted DB access;
- PII minimization;
- prompt injection defense;
- source attribution.

---

# 37. Prinsip Ethical AI

Project harus mengikuti prinsip:

### Human Oversight

AI memberikan rekomendasi, bukan keputusan final.

### Transparency

Risk score harus memiliki evidence.

### Privacy

Gunakan data minimum yang diperlukan.

### Fairness

Evaluasi bias terhadap kelompok/fasilitas tertentu.

### Accountability

Setiap keputusan AI harus dapat dilacak:

> model → feature → evidence → output → reviewer.

---

# 38. Potential Future Development

Setelah MVP berhasil, sistem dapat dikembangkan menjadi:

## Provider Risk Profile

Profil risiko fasilitas kesehatan:

```text
Facility Risk Score
Clinical anomaly
Financial anomaly
Claim similarity
Temporal pattern
Historical trend
```

## Continuous Monitoring

Risk monitoring secara berkala, bukan hanya saat klaim diproses.

## QA Panel (dulu direncanakan sebagai "Investigator Copilot" terpisah)

Digabung ke Explanation Agent, bukan agent/fitur chat terpisah — lihat `AGENTS.md` Section 7.1 dan `FRONTEND.md`. Verifier bisa klik 4 tombol pra-set:

> “Kenapa klaim ini masuk top priority?”

> “Apa evidence terkuat?”

> “Tunjukkan klaim paling mirip.”

> “Apakah sistem menganggap ini fraud?”

Jawaban bersumber dari field yang **sudah dihitung** pipeline (bukan LLM call baru saat tombol diklik) — nol risiko halusinasi live saat demo. Versi free-text dengan guardrail dicatat sebagai Nice-to-have masa depan, bukan scope 4 minggu ini.

## What-if Simulation

> “Bagaimana risk score berubah jika biaya berada di peer range?”

## Feedback Loop

Keputusan verifier menjadi feedback untuk model.

## Cross-provider Network Analysis

Mencari pola risiko yang melibatkan:

- multiple facilities;
- multiple doctors;
- multiple procedures;
- recurring relationships.

---

# 39. Ide Pengembangan Jangka Panjang

Konsep dapat berkembang menjadi:

> **JKN Risk Intelligence Platform**

yang tidak hanya memproses klaim, tetapi juga membantu:

- fraud prevention;
- quality assurance;
- claim efficiency;
- provider monitoring;
- clinical pathway adherence;
- investigation support;
- policy analysis.

---

# 40. Kesimpulan Akhir

## Pilihan Kompetisi

> **Healthkathon 2026 BPJS Kesehatan**

## Tema

> **Detect Smarter, Protect JKN - Smarter Protection for a Stronger JKN: Efisiensi Risiko Program JKN**

## Kategori

> **Efisiensi Risiko pada Fasilitas Kesehatan**

## Fokus utama

> **Manipulasi Diagnosis/Tindakan (Upcoding) dan Tindakan Pengobatan Tidak Sesuai Indikasi Medis**

## Supporting risk patterns

> **Cloning + Repeat Billing + Cost Anomaly + Behavioral/Temporal Anomaly**

## Produk

> **JKN Agentic Risk Intelligence**

## Konsep

> **AI-powered multi-agent pre-verification and claim investigation system**

## Arsitektur

> **Hybrid: Rules + ML + Similarity + Graph + Specialist Agents + Human Review**

## Agent

> 1. Case Manager Agent  
> 2. Clinical Reasoning Agent  
> 3. Fraud/Pattern Investigation Agent  
> 4. Evidence Review Agent  
> 5. Explanation Agent

## Prinsip utama

> **Detect → Explain → Prioritize → Human Verify**

Bukan:

> **Detect → Accuse**

---

# 41. Sumber dan Dasar Riset

Dokumen ini dirangkum dari diskusi internal dan riset publik mengenai arah teknologi serta kebutuhan BPJS/JKN pada 2025–2026. Sumber berikut digunakan untuk memvalidasi konteks, bukan untuk mengklaim akses ke sistem internal BPJS.

### BPJS / Government / DJSN

- BPJS Kesehatan — informasi kepesertaan dan layanan:
  https://www.bpjs-kesehatan.go.id/
- DJSN — penguatan pengawasan dan integritas Program JKN, 2026:
  https://djsn.go.id/berita/djsn-dan-bpjs-kesehatan-perkuat-sinergi-pengawasan-dan-integritas-program-jkn
- DJSN — monitoring, kinerja JKN, dan isu penyelesaian klaim:
  https://djsn.go.id/berita/hasil-monev-triwulan-ii-djsn-tekankan-perbaikan-kinerja-jkn-prioritas-penyelesaian-klaim
- Kementerian Komunikasi dan Digital — pengembangan chatbot, claim analysis, smart analytics, dan gap AI/data BPJS:
  https://portal.komdigi.go.id/kanal-publik/berita-kini/10120
- Kementerian Kesehatan — transformasi digital dan integrasi pelayanan:
  https://keslan.kemkes.go.id/read/3515/rsup-dr-m-djamil-dan-bpjs-kesehatan-lakukan-monev-transformasi-digital
- Kementerian Kesehatan / Pusbikes — laporan terkait klaim JKN:
  https://setjen.kemkes.go.id/
- SATUSEHAT Platform — dokumentasi interoperabilitas klaim BPJS:
  https://satusehat.kemkes.go.id/platform/docs/id/interoperability/klaim-bpjs/

### AI / Healthcare / Research

- Nature — review mengenai AI agents untuk healthcare dan isu safety/governance:
  https://www.nature.com/articles/s44387-026-00076-4
- WHO — guidance mengenai ethics/governance AI for health:
  https://www.who.int/publications/i/item/B09667
- NIST — AI Agent Standards Initiative, 2026:
  https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure
- ACL 2026 — multi-agent collaboration untuk automated ICD coding:
  https://aclanthology.org/2026.acl-demo.26/

> **Catatan validasi:** informasi tentang kemampuan internal BPJS yang tidak dipublikasikan tidak dapat dipastikan. Karena itu, istilah seperti “belum ada” sebaiknya dibaca sebagai **“belum ditemukan bukti publik yang cukup”**, bukan kepastian bahwa capability tersebut tidak tersedia secara internal.

---

# 42. Proposed Final Product Statement

> **JKN Agentic Risk Intelligence is a human-supervised, multi-agent claim risk intelligence platform that combines clinical reasoning, machine learning, anomaly detection, similarity search, graph analytics, and explainable risk scoring to help BPJS identify and prioritize potentially risky JKN claims before deeper human verification.**

---

# 43. Final Strategic Recommendation

**Jangan mengejar “AI yang paling kompleks”.**

Keunggulan project harus berasal dari:

> **problem fit + evidence + explainability + workflow + responsible AI.**

Multi-agent digunakan karena proses investigasi memang multi-step dan multi-domain.

Tetapi:

> **Rules tetap untuk hal yang deterministik.**  
> **ML tetap untuk scoring.**  
> **Graph tetap untuk relationship analysis.**  
> **Vector search tetap untuk similarity.**  
> **Agent digunakan untuk orchestration, tool use, reasoning, synthesis, dan explanation.**  
> **Manusia tetap memegang keputusan akhir.**

Dengan struktur tersebut, project tidak hanya terlihat modern secara teknologi, tetapi juga lebih mudah dipertanggungjawabkan sebagai solusi yang dapat membantu **efisiensi, integritas, dan keberlanjutan Program JKN**.