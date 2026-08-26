# MODELS.md — Teknik ML, Sumber Data, dan Skema Dataset J-ARI

## 0. Prinsip modeling

Tidak ada satu model yang menjawab semua jenis risiko. Sistem ini secara sengaja memisahkan task per jenis sinyal (lihat `AGENTS.md`), karena mencampur semuanya ke satu classifier besar menghilangkan explainability per-jenis-anomali yang justru jadi nilai jual utama (lihat PRD Section 12). Bagian ini membahas: **(1)** apakah XGBoost cukup atau ada alternatif yang lebih pas per task, **(2)** dari mana data berasal, **(3)** skema variabel dataset final.

> **Scope:** dokumen ini fokus ke model ML non-generatif (XGBoost, similarity, rule engine). Untuk strategi LLM (Ollama vs Gemini API, model per role, prosedur benchmark), lihat `PRD.md` Section 7 — itu keputusan arsitektur LLM, terpisah dari pembahasan teknik ML di sini.

---

## 1. Financial/Cost Anomaly — XGBoost cukup, tapi ini bukan keputusan default

### Kenapa XGBoost jadi pilihan utama

Task-nya: memprediksi rentang biaya wajar untuk suatu kombinasi diagnosis+prosedur+severity+tipe faskes, lalu bandingkan dengan biaya yang diklaim. Ini regression/anomaly problem pada data tabular dengan fitur campuran (numerik + kategorikal kardinalitas tinggi seperti kode diagnosis). XGBoost cocok karena: menangani missing value native, robust terhadap fitur kategorikal ber-cardinality tinggi (lewat encoding yang tepat), dan yang paling penting — SHAP value untuk XGBoost sudah sangat matang tooling-nya (`shap.TreeExplainer` cepat dan eksak, bukan approximation seperti kernel SHAP untuk model lain).

### Tapi ada alternatif yang layak dipertimbangkan, bukan diabaikan

| Teknik | Kapan lebih unggul dari XGBoost | Kenapa tidak dipilih untuk MVP ini |
|---|---|---|
| **LightGBM** | Dataset sangat besar (>1M baris), butuh training lebih cepat | Dataset sintetis hackathon jauh di bawah skala itu; keunggulan speed tidak relevan, sementara tooling SHAP untuk XGBoost lebih matang dan lebih banyak dokumentasi/contoh untuk tim yang belajar cepat |
| **CatBoost** | Banyak fitur kategorikal dengan cardinality sangat tinggi (ratusan ribu kategori) tanpa encoding manual | Kode diagnosis/prosedur JKN jumlahnya terbatas (ratusan-ribuan), masih terkelola dengan target/frequency encoding manual di XGBoost — tidak butuh keunggulan native categorical CatBoost |
| **Isolation Forest** | Deteksi anomali tanpa label (unsupervised) — cocok kalau tidak yakin definisi "normal" | Layak sebagai **pelengkap**, bukan pengganti — lihat sub-section di bawah |
| **Autoencoder (neural)** | Dataset besar, pola anomali kompleks non-linear yang sulit ditangkap tree-based model | Dataset sintetis MVP terlalu kecil untuk melatih autoencoder yang generalize dengan baik; risiko overfitting tinggi, dan hasilnya tidak lebih explainable dari XGBoost+SHAP |
| **Rule-based scorecard manual** | Waktu sangat terbatas, butuh sesuatu yang instan tanpa training | Kita sudah eksplisit hindari ini di PRD (Section 8.3 versi awal) — scorecard manual gampang dituduh "bukan ML sungguhan" oleh juri teknis |

### Ide menarik yang layak dieksplorasi: unsupervised ensemble sebagai sinyal tambahan (bukan pengganti XGBoost)

Riset terkait mendeteksi fraud pada data claims Medicare sintetis (CMS DE-SynPUF) memakai kombinasi metode unsupervised — <cite index="19-1">isolation forest, CBLOF, ECOD, dan OCSVM — dievaluasi dengan silhouette scoring, dengan CBLOF mencatat skor tertinggi diikuti isolation forest.</cite> Ide yang bisa diadopsi murah: setelah XGBoost supervised (dilatih dengan label fraud/normal dari data sintetis Anda), tambahkan **satu** model unsupervised sederhana (Isolation Forest dari scikit-learn, bukan CBLOF/ECOD yang butuh library `pyod` tambahan) sebagai sinyal independen kedua — kalau XGBoost dan Isolation Forest **sepakat** suatu klaim anomali, itu sinyal lebih kuat daripada satu model saja. Ini murah untuk diimplementasi (beberapa baris kode, scikit-learn sudah pasti ada di stack), dan memberi argumen tambahan ke juri: "kami tidak hanya bergantung pada satu model."

**Catatan:** ini tetap dicatat sebagai *Should Have*, bukan *Must Have* — jangan tambahkan sebelum XGBoost+SHAP inti benar-benar solid dan dievaluasi dengan baik.

---

## 2. Clinical Compatibility — bukan ML sama sekali di lapis utama

Ini **rule engine** (lookup table diagnosis-prosedur-severity → grouper), bukan model yang di-training. LLM lokal dipakai hanya untuk kasus di luar tabel referensi (lihat `AGENTS.md` Section 2). Ini keputusan sadar: mencoba melatih classifier ML untuk "apakah kombinasi ini valid secara medis" dari data sintetis buatan sendiri akan mengulang masalah tautologi yang sudah kita bahas panjang di PRD — model akan belajar aturan yang kita tanam sendiri, bukan belajar kedokteran.

---

## 3. Similarity/Cloning Detection — sentence-transformers, dengan alternatif yang perlu diuji

**Default:** embed representasi teks klaim (gabungan diagnosis+prosedur+catatan singkat) dengan sentence-transformers, similarity via cosine di LanceDB.

**Alternatif yang layak dibandingkan, bukan diasumsikan menang:** karena data JKN sebagian besar berupa **kode terstruktur** (bukan free-text panjang), similarity berbasis **Jaccard/overlap set** pada kombinasi kode diagnosis+prosedur bisa jadi lebih interpretable dan lebih murah komputasinya daripada embedding neural — dua klaim dengan kode identik akan punya Jaccard = 1.0 secara eksak, sementara embedding bisa memberi similarity tinggi walau ada perbedaan kode karena kemiripan makna semantik (yang sebenarnya kita mau untuk kasus tertentu, tapi tidak untuk kasus lain). **Rekomendasi:** implementasikan keduanya sebagai dua sinyal terpisah di `FraudAssessment` (bukan pilih satu) — Jaccard untuk "exact code overlap" (kuat untuk phantom/repeat billing), embedding untuk "semantic similarity" (kuat untuk cloning dengan variasi kecil). Biayanya rendah karena keduanya cepat dihitung.

---

## 4. Pengumpulan Data — apa yang tersedia di Kaggle, dan batasannya

**Peringatan penting di awal:** tidak ada dataset publik yang benar-benar merepresentasikan struktur klaim JKN/INA-CBG — semua dataset Kaggle yang relevan berbasis sistem asuransi AS (Medicare) atau generik, dengan struktur kode diagnosis (ICD-9/10 versi AS) dan logika pembayaran yang **berbeda** dari INA-CBG. Dataset ini berguna sebagai **referensi struktural** (bentuk tabel, jenis fitur, pola distribusi fraud) untuk mendesain generator data sintetis Anda sendiri — bukan untuk dipakai langsung sebagai data training.

### Dataset yang ditemukan dan relevansinya

| Dataset | Isi | Kegunaan untuk J-ARI |
|---|---|---|
| **Healthcare Provider Fraud Detection Analysis** (Kaggle, rohitrox) | <cite index="12-1">Data klaim inpatient/outpatient serta info beneficiary dari beberapa pasien dan provider, dengan label fraud per-provider (bukan per-klaim)</cite>. <cite index="26-1">Termasuk kolom demografis (gender, state), kondisi kronis (ChronicCond_Diabetes, dsb.), provider ID, dan target fraud Yes/No.</cite> Dataset paling banyak dipakai/dicontohkan untuk task ini. | **Paling relevan secara struktural** — pola pemisahan tabel Beneficiary/Inpatient/Outpatient/Target bisa langsung jadi inspirasi skema Anda (Section 5 di bawah) |
| **NHIS Healthcare Claims and Fraud Dataset** (Kaggle, bonifacechosen) | <cite index="11-1">Data klaim NHIS riil dan simulasi untuk riset fraud detection</cite> | Berguna sebagai pembanding kedua untuk validasi asumsi distribusi biaya |
| **Healthcare Fraud Detection Dataset** (Kaggle, nudratabbas) | <cite index="14-1">10.000 klaim asuransi kesehatan yang dirancang meniru pola billing dan fraud dunia nyata, dengan campuran fitur pasien, provider, dan finansial untuk task klasifikasi</cite> | Sudah dirancang sebagai dataset sintetis siap pakai — cocok untuk **benchmark cepat** algoritma sebelum dataset JKN-sintetis Anda sendiri selesai |
| **CMS DE-SynPUF** (public, bukan Kaggle — dari Centers for Medicare & Medicaid Services) | <cite index="19-1">Data sintetis publik 2008-2010 dipakai riset association rule mining + unsupervised anomaly detection (Isolation Forest, CBLOF, ECOD, OCSVM) untuk deteksi fraud</cite> | Referensi metodologi unsupervised ensemble (lihat Section 1) — bukan untuk data langsung |

### Rekomendasi konkret

Jangan pakai dataset AS ini langsung untuk melatih model final (struktur kode diagnosis dan logika pembayarannya beda dari INA-CBG — model yang dilatih di atasnya tidak akan valid untuk konteks JKN). Gunakan untuk: **(1)** validasi struktur skema (Section 5), **(2)** sanity-check distribusi statistik (berapa persen klaim biasanya anomali, seberapa skewed biayanya) untuk membuat generator sintetis Anda realistis, **(3)** benchmark cepat pipeline model sebelum data JKN-sintetis final siap.

---

## 5. Skema Dataset J-ARI (Sintetis)

Terinspirasi struktur multi-tabel dataset referensi di atas, disesuaikan untuk konteks INA-CBG.

### Tabel `claims`

| Variabel | Tipe | Keterangan |
|---|---|---|
| `claim_id` | string (PK) | Unique ID klaim |
| `patient_id` | string (FK) | Referensi ke `patients` |
| `provider_id` | string (FK) | Referensi ke `providers` |
| `attending_doctor_id` | string (FK) | Dokter penanggung jawab |
| `operating_doctor_id` | string (FK, nullable) | Dokter tindakan (jika ada operasi) |
| `admission_date` | date | Tanggal masuk |
| `discharge_date` | date | Tanggal keluar |
| `length_of_stay` | int | Turunan, tapi disimpan untuk kemudahan query |
| `diagnosis_primary` | string | Kode diagnosis utama (simplified ICD-10) |
| `diagnosis_secondary` | list[string] | Diagnosis sekunder/komplikasi |
| `procedure_codes` | list[string] | Kode tindakan |
| `severity_level` | int (1-4) | Proxy CC/MCC sederhana |
| `cbg_group_claimed` | string | Grup INA-CBG yang diklaim |
| `cost_claimed` | float | Biaya yang diklaim |
| `cost_reference` | float | Tarif referensi hasil grouper simplified (dihitung, bukan input) |
| `claim_type` | enum | `inpatient` / `outpatient` |
| `referral_source` | string (nullable) | Faskes/dokter perujuk |

### Tabel `patients`

| Variabel | Tipe | Keterangan |
|---|---|---|
| `patient_id` | string (PK) | |
| `age_band` | enum | Kelompok umur (bukan tanggal lahir eksak — hindari data granular tidak perlu) |
| `gender` | enum | |
| `chronic_conditions` | list[string] | Kondisi kronis terdaftar (diabetes, jantung, dsb.) |
| `region_code` | string | Kode wilayah (bukan alamat lengkap) |
| `membership_duration_months` | int | Lama kepesertaan |

### Tabel `providers`

| Variabel | Tipe | Keterangan |
|---|---|---|
| `provider_id` | string (PK) | |
| `facility_type` | enum | RS Tipe A/B/C/D, Puskesmas, Klinik |
| `region_code` | string | |
| `claim_volume_monthly` | int | Turunan agregat, untuk fitur peer group |
| `avg_severity_reported` | float | Turunan agregat — proxy untuk deteksi provider yang sistematis melaporkan severity tinggi |

### Tabel `doctors`

| Variabel | Tipe | Keterangan |
|---|---|---|
| `doctor_id` | string (PK) | |
| `provider_id` | string (FK) | Afiliasi utama |
| `specialty` | string | |

### Label untuk training (hanya di held-out/training set, bukan di data "live" yang diproses sistem)

| Variabel | Tipe | Keterangan |
|---|---|---|
| `is_synthetic_anomaly` | bool | Flag ground truth apakah klaim ini sengaja di-inject sebagai anomali |
| `anomaly_type` | enum (nullable) | `upcoding` / `phantom_billing` / `cloning` / `repeat_billing` / `none` — dipakai untuk evaluasi per-jenis, TIDAK dipakai sebagai fitur model (itu akan jadi data leakage) |

**Pengingat metodologi (lihat PRD Section 10):** field `is_synthetic_anomaly` dan `anomaly_type` hanya boleh dilihat oleh anggota tim yang membuat dataset dan yang menjalankan evaluasi akhir — bukan oleh anggota yang men-tuning detector, supaya held-out test tetap jujur.

---

## Referensi

- Healthcare Provider Fraud Detection Analysis (Kaggle): https://www.kaggle.com/datasets/rohitrox/healthcare-provider-fraud-detection-analysis
- NHIS Healthcare Claims and Fraud Dataset (Kaggle): https://www.kaggle.com/datasets/bonifacechosen/nhis-healthcare-claims-and-fraud-dataset
- Healthcare Fraud Detection Dataset (Kaggle): https://www.kaggle.com/datasets/nudratabbas/healthcare-fraud-detection-dataset
- Healthcare insurance fraud detection using data mining (CMS DE-SynPUF, unsupervised ensemble methodology): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11046758/
---

## 4. Risk Score Engine — Bobot Final (Terimplementasi)

Semua bobot di bawah ini terdokumentasi sesuai mandat AGENTS.md Section 6 — tidak ada angka yang muncul tanpa jejak. Implementasi: ackend/app/agents/risk_engine.py.

| Komponen | Bobot maks | Sumber angka (traceable) |
|---|---|---|
| clinical_rule_flags | 20 | Rule engine clinical agent — flag deterministik, BUKAN plausibility LLM |
| inancial_anomaly | 30 | nomaly_score dari XGBoost (deviasi vs prediksi) atau z-score peer saat fallback |
| isolation_forest_anomaly | 15 | Isolation Forest normalized, dimodulasi skor jaringan faskes (0.7–1.0×) |
| similarity_fraud | 20 | Repeat billing (SQL pasien+prosedur+tanggal) = 20 penuh; cosine >0.95 antar-pasien = scaled; kemiripan biasa dibatasi 15 |
| synthesis_confidence | 15 | evidence_level dari Review Agent (LLM dengan guard rule-count, atau fallback rule-count) |

Rincian clinical flags (total 20):

| Flag | Poin | Definisi |
|---|---|---|
| 	ariff_deviation_extreme | 10 | Biaya > 100% di atas tarif referensi CBG |
| 	ariff_deviation_high | 6 | Biaya > 50% di atas tarif referensi |
| severity_proc_mismatch | 5 | Severity ≥3 tanpa prosedur pendukung |
| severity_med_mismatch | 3 | Severity ≥3 dengan obat <2 jenis |
| los_outlier | 2 | LOS > 2× batas atas rentang klinis |
| upcoding_risk_diag | 4 | Diagnosis sekunder berisiko upcoding (A41.9, Z87.39, E46) pada severity ≥3 |

**Prinsip yang dijaga:** plausibility dari LLM (Lapis 2 Clinical Agent) tidak pernah masuk rumus skor — LLM hanya boleh mengeskalasi label (questionable→implausible), tidak menghapus flag rule. Angka skor selalu traceable ke flag/SHAP/model.

**Metodologi evaluasi (anti-tautologi):** training set digenerate dengan seed 101, held-out test set dengan seed 202 (panggilan generator terpisah), Isolation Forest dengan seed 303. Hasil evaluasi held-out tersimpan di ackend/models_trained/evaluation_results.json dan ditampilkan apa adanya di halaman Evaluasi Model ML (endpoint /api/ml/eval) — tanpa angka simulasi.
