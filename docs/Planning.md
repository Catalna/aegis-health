# MASTER PROMPT — AEGIS-Health: Perbaikan Menyeluruh (Healthkathon 2026)

> Cara pakai: tempel seluruh dokumen ini ke agent, atau tempel **bagian "KONTEKS & ATURAN" + satu FASE** per sesi. Fase dirancang berurutan; setelah tiap fase aplikasi lama harus tetap berjalan.

---

## 0. KONTEKS & ATURAN (wajib dibaca di setiap sesi)

**Proyek.** AEGIS-Health (Agentic Risk Engine & Intelligent Surveillance for Healthcare), tampil sebagai AEGIS. Lapisan *risk prioritization* untuk verifier klaim BPJS Kesehatan. Stack: FastAPI + PostgreSQL + LanceDB + XGBoost + Isolation Forest + Ollama (LLM lokal) + React/Vite. Repo: `aegis-health-main`. Dokumen acuan di `docs/` (PRD, MODELS, Architecture, AgentWorkflow, BusinessCore) dan `docs/plans/2026-10-23-engineering-audit-next-steps.md`. **Verifikasi sendiri path file** sebelum mengedit; beberapa path di dokumen tidak cocok dengan struktur repo.

**Tenggat.** Submit video + demo BPJS Healthkathon: **1 November 2026** (video maks. 10 menit). Seleksi 20 finalis 2–4 November. Utamakan hal yang membuat demo stabil dan evaluasi jujur; tunda sisanya.

**Prinsip yang tidak boleh dilanggar**
1. Risk score & tier **deterministik**. LLM hanya menulis narasi dan tidak boleh mengubah skor/tier/evidence.
2. Output bukan "fraud confirmed" dan bukan penolakan klaim. Gunakan "High Risk — Requires Verification".
3. Data sintetis harus **selalu berlabel sintetis** di dataset version, UI, dan dokumen. Dilarang menyajikan hasil sintetis sebagai validasi BPJS.
4. Jangan pernah memasukkan data peserta JKN riil ke repo. Raw Data Sample BPJS masuk `.gitignore`; hanya output agregat yang boleh dikeluarkan.
5. **Jangan mengarang angka.** Setiap metrik di UI/dokumen harus berasal dari run evaluator dan tercatat (dataset version, seed, config hash, tanggal). Angka target diberi label "target".
6. **Jangan tuning terhadap test set.** Tuning bobot/threshold/hyperparameter hanya pada train+validation. Test dibuka sekali per konfigurasi final dan hasilnya dilaporkan apa adanya, termasuk yang buruk.
7. Jangan menambah agent, framework, database, atau LLM baru. Skop = memperkuat yang ada.

**Cara kerja**
- Satu branch per fase, commit kecil, jalankan test setelah tiap perubahan. Fase dianggap selesai hanya jika acceptance criteria-nya terpenuhi.
- Jika ada keputusan ambigu, pilih default yang paling konservatif, catat di `docs/DECISIONS.md` (konteks, opsi, alasan), lalu lanjut.
- Jika sesuatu tidak bisa diverifikasi di lingkungan Anda (mis. Ollama/GPU/PostgreSQL tidak tersedia), katakan terus terang di laporan akhir; jangan menandainya "selesai".
- Di akhir tiap fase, tulis ringkasan di `docs/CHANGELOG-agent.md`: apa yang diubah, test yang dijalankan (dan hasilnya), apa yang belum selesai.

---

## FASE 0 — Baseline yang bisa dijalankan (P0)

Tujuan: tahu kondisi sebenarnya sebelum mengubah apa pun.

1. Instal dependensi backend dan frontend sesuai lock file. Pastikan `requirements.txt` memuat semua paket yang dipakai (audit menemukan `asyncpg` dan `sse_starlette` hilang di lingkungan uji).
2. Jalankan `pytest -q` penuh. Catat setiap kegagalan; perbaiki masalah dependensi/lingkungan. Jangan menghapus test agar lulus.
3. Jalankan `scripts/smoke_test.py` dan alur end-to-end: PostgreSQL → API `/api/health` → load batch klaim sintetis → screening satu klaim → stream investigasi (SSE) → simpan keputusan manusia → verifikasi baris `audit_logs`.
4. Build frontend (`npm ci && npm run build`).
5. Jalankan evaluator P1 yang ada dan simpan hasilnya sebagai `docs/baselines/baseline-pre-v2.json` (dipakai pembanding sebelum/sesudah).

**Acceptance:** `docs/RUNBOOK.md` berisi langkah instalasi + satu perintah demo (perbarui `start.bat`; tambahkan `Makefile` atau script setara untuk Linux/macOS); laporan baseline (apa yang lulus/gagal) di CHANGELOG.

---

## FASE 1 — Data sintetis v2 (P0, bagian terbesar)

**Masalah saat ini (terverifikasi):** generator hanya ±10 diagnosis; biaya normal = `cost_base × uniform(0.9, 1.1)`; anomali dikali 2–8×; test set hanya ±79 klaim dengan 3 kasus per tipe. Metrik di atas data seperti ini terutama mengukur konsistensi dengan generator, bukan kemampuan model. Tujuan fase ini: dataset **besar, beragam, sulit, dan terpisah secara metodologis** dari detector.

Buat modul baru `backend/app/data/synthetic_v2/` (jangan menimpa generator lama; pertahankan agar test lama tetap berjalan) dan CLI `scripts/generate_synthetic_v2.py --profile {dev,standard,large} --seed N --out data/synthetic_v2/`.

### 1.1 Skala (parameter lewat config, bukan hard-code)
| Profile | Klaim train | Validation | Test (natural) | Faskes | Dokter | Pasien |
|---|---:|---:|---:|---:|---:|---:|
| dev | 5.000 | 2.000 | 2.000 | 30 | 150 | 3.000 |
| standard (default untuk evaluasi) | 150.000 | 50.000 | 50.000 | 300 | 2.500 | 60.000 |
| large | 500.000 | 100.000 | 100.000 | 600 | 5.000 | 150.000 |

Generator harus vectorized/chunked (pandas/numpy), deterministik per seed, dan profile `standard` selesai dalam waktu wajar di laptop (ukur dan catat). Output Parquet (+ CSV opsional) bersama `schema.json`.

### 1.2 Realisme struktur (semua parameter di satu file `calibration_profile.json` yang nanti bisa diganti hasil profiling Data Sample BPJS)
- **Katalog diagnosis ≥ 150** kode ICD-10 (3 karakter) lintas bab, dengan proporsi kasus bergaya "100 penyakit terbanyak", diagnosis sekunder yang masuk akal (struktur komorbid, mis. diabetes↔hipertensi↔CKD), prosedur ICD-9-CM terkait, dan indikator ICU/ventilator/bedah.
- **Distribusi per diagnosis:** LOS (lognormal/gamma, berbeda tiap diagnosis & rawat jalan vs inap), umur dan jenis kelamin bergantung diagnosis, jumlah diagnosis sekunder, jumlah prosedur.
- **Tarif:** biaya klaim mengikuti logika paket INA-CBG: `tarif = f(kelompok CBG, tingkat severity, regional, kelas/tipe faskes) × noise kecil` + komponen special groups (obat/prosedur/investigasi/prostesis) pada subset kasus. Biaya **tidak boleh** sekadar konstanta per diagnosis ± 10%. Beri label jelas bahwa tabel tarif adalah *demonstrator*, bukan grouper/tarif resmi.
- **Severity:** simpan **kode INA-CBG mentah** terpisah dari fitur internal. Jangan memperlakukan `severity_level` 1–4 sebagai karakter ke-4 kode resmi. Mengacu Permenkes 26/2021: rawat jalan `0`, rawat inap `I/II/III`. Buat pemetaan eksplisit di satu modul dan dokumentasikan.
- **Entitas:** faskes heterogen (tipe/kelas, wilayah, ukuran, case mix berbeda), dokter terikat faskes, pasien dengan riwayat kunjungan berulang. Rentang waktu ≥ 24 bulan dengan musiman ringan.
- **Hard negative yang sah (wajib ada, ±5–10% dari klaim normal):** readmisi legitimate, rawat berulang untuk penyakit kronis (dialisis, kemoterapi), kasus katastropik berbiaya tinggi yang wajar (kanker, infark, fraktur), LOS panjang yang wajar, dua prosedur berbeda yang sah di hari berdekatan, klaim mirip antar pasien karena protokol standar.

### 1.3 Injeksi anomali — beragam, berjenjang, dan punya "keluarga skenario"
Tipe: upcoding, unbundling, cloning, repeat billing, phantom billing, inflated bill, prolonged LOS.
- Tiap tipe punya **≥ 3 mekanisme** dan **3 tingkat kesulitan** (easy/medium/hard) dengan parameter berbeda. Contoh upcoding: naik severity tanpa prosedur pendukung; diagnosis sekunder fiktif; tambahan prosedur tak didukung. Contoh cloning: salinan persis; salinan dengan biaya ±1–5% dan tanggal bergeser; lintas dokter di faskes yang sama. Contoh repeat billing: jendela 1–60 hari termasuk kasus batas (44/45/46 hari). Contoh unbundling: pecah 2–4 bagian dengan fraksi biaya bervariasi.
- **Keluarga skenario terpisah:** sebagian mekanisme hanya muncul di validation/test dan **tidak ada di train** (out-of-family). Catat keluarga tiap kasus di metadata.
- **Prevalensi natural** anomali kecil (default 3%; konfigurasi) pada split utama; sediakan juga **test enriched** (mis. ≥ 150 kasus per tipe) untuk membandingkan antartipe. Laporan wajib menyebut prevalensi yang dipakai.
- **Positif lunak** (sinyal biaya lemah) dan **label noise** terkontrol (opsi 0/5/10%) untuk uji ketahanan.
- Beberapa faskes ber-"propensity" risiko tinggi (untuk menguji metrik graf), tetapi label tetap pada level klaim.
- Ground truth (`is_anomaly`, `anomaly_type`, `difficulty`, `scenario_family`, `group_id`, `label_confidence`) disimpan di **file terpisah** (`labels.parquet`); file klaim input tidak boleh memuatnya.

### 1.4 Split yang bebas kebocoran
- Split **berbasis waktu** (mis. bulan 1–18 train, 19–21 validation, 22–24 test) **dan** berbasis grup (pasangan cloning, sumber+klon repeat, seluruh grup unbundling tidak boleh terbelah).
- Tambahkan **stress set OOD**: faskes dan dokter yang tidak ada di train + keluarga skenario baru.
- Validator otomatis (`validate_dataset.py`) yang gagal keras jika: ada kebocoran grup, label ada di file input, distribusi klaim normal antara split berbeda signifikan (uji KS pada biaya/LOS/umur), atau ada ID yang mengandung pola PII.

### 1.5 Dokumentasi data
Hasilkan `data_card.md` otomatis: versi generator, seed, hash config, ukuran, prevalensi per tipe/kesulitan/keluarga, asumsi, keterbatasan, dan pernyataan eksplisit bahwa data ini sintetis dan tidak memvalidasi performa pada data nyata.

**Acceptance Fase 1:** `generate_synthetic_v2.py --profile standard --seed 42` berjalan reproducible (dua run → hash file sama); `validate_dataset.py` lulus; test unit untuk group-split, tidak ada label di input, hard negative hadir, keluarga skenario terpisah; statistik ringkas (jumlah per tipe/kesulitan/split) tercetak. Test lama generator v1 tetap lulus.

---

## FASE 2 — Semantik skor, aturan tier, dan konsistensi domain (P0)

1. **Rentang skor.** Komponen saat ini 20+30+20+15 = maks. 85 tetapi dipotong 100 dan tier memakai ambang seperti skala 0–100. Pilih satu: (a) normalisasi resmi ke 0–100 dengan rumus terdokumentasi, atau (b) tampilkan poin mentah dengan maksimum sebenarnya. Terapkan konsisten di backend, UI, dan dokumen. Skor **bukan probabilitas**.
2. **Arah financial anomaly.** Jalur model memakai `abs(deviation_pct)`, jalur fallback z-score hanya menandai deviasi ke atas. Simpan **signed deviation** sebagai evidence dan pisahkan *upward exposure* dari *downward deviation*; samakan perilaku model dan fallback; dokumentasikan keputusan. Label di UI: "deviasi dari benchmark", bukan "overbilling terbukti".
3. **Lantai tier deterministik untuk bukti relasional kuat.** Observasi: skor cloning pada evaluasi saat ini 24,6–29,8 sehingga sebagian jatuh ke tier Low (`processed`, tidak masuk antrean review) karena similarity maks. 20 poin dan *evidence support* butuh ≥ 2 sinyal. Implementasikan aturan: jika syarat cloning/repeat billing/exact duplicate terpenuhi penuh, tier minimum = Medium (atau High untuk exact duplicate), apa pun jumlah poinnya. Aturan tetap deterministik, tercatat di evidence, dan diuji. **Verifikasi dulu** dengan membaca `risk_engine.py` bahwa penyebabnya memang itu.
4. **Ambang tier berbasis kapasitas.** Tentukan ambang High/Medium dari **validation set** berdasarkan kapasitas review (mis. High ≈ 5% teratas, Medium ≈ 20% teratas dari volume harian) dan target precision/recall yang dilaporkan; bukan angka tetap warisan. Versi-kan di `config_version`.
5. **Rule screening klinis.** Pisahkan label `domain-backed rule` (punya dasar regulasi/coding/referensi) dari `prototype screening signal` (heuristik). Tampilkan label itu di evidence.
6. **Konsistensi dokumen:** satukan bobot similarity (PRD: 0,40/0,30/0,15/0,10/0,05 vs MODELS.md: 0,35/0,25/0,20/0,20) dengan nilai yang benar-benar dipakai kode; perbaiki path file yang salah; perjelas bahwa classifier XGBoost **bukan** model runtime.

**Acceptance:** test kontrak untuk skor (rentang, tier, lantai), test per subtipe relasional (cloning/repeat/unbundling, termasuk kasus batas jendela), tidak ada perbedaan perilaku model vs fallback yang tidak terdokumentasi.

---

## FASE 3 — Model ML dan evaluasi (P0)

Latih ulang dan evaluasi di dataset v2. Semua keputusan desain dicatat di `docs/DECISIONS.md`.

### 3.1 Benchmark biaya (regressor)
- Latih pada klaim **normal saja** atau dengan estimator robust; jangan belajar dari anomali tanpa kontrol.
- Fitur tanpa `cost_claimed`. **Uji ablation:** dengan vs tanpa `severity_level` dan `ina_cbg_base_rate` (hipotesis: fitur ini ikut naik saat upcoding sehingga menyembunyikan sinyal). Pilih berdasarkan validation, laporkan hasilnya.
- Tambahkan **interval prediksi terkalibrasi** (quantile regression atau conformal) untuk `predicted_cost_upper`; laporkan coverage empiris (target 90%) per segmen. Ganti ambang fixed "50%/100%" dengan interval ini bila hasilnya lebih baik di validation.
- Metrik: MAPE, MedAE, per diagnosis, per tipe/kelas faskes, per regional; time-aware split. Ingat: MAPE rendah pada data sintetis bukan bukti akurasi tarif riil.

### 3.2 Model supervised pembanding (classifier)
- Posisikan jelas sebagai **kandidat** pada ablation, bukan komponen runtime, kecuali terbukti menambah nilai pada ranking runtime.
- Hyperparameter search dengan **group k-fold** hanya di train; kalibrasi probabilitas (isotonic/Platt) di validation; laporkan PR-AUC, Brier, ECE.
- Baseline wajib: ranking acak, deviasi biaya saja, regresi logistik di atas rule flags.

### 3.3 Isolation Forest, similarity, graf
- Ablation sebagai sinyal pendukung; `contamination` diatur dari validation. Pertahankan bobot 0 kecuali ablation di dataset besar dengan interval kepercayaan menunjukkan nilai tambah yang material.
- Similarity: pastikan perbandingan hanya memakai riwayat **sebelum** tanggal klaim (tidak ada kebocoran masa depan); uji deterministik terhadap kasus batas. Untuk evaluasi massal, jika embedding LanceDB terlalu lambat pada 50k+ klaim, gunakan similarity terstruktur (kode/biaya/faskes/waktu) dan **catat perbedaan itu**; embedding tetap dipakai di demo.
- Metrik graf dinormalisasi terhadap ukuran peer; volume tinggi bukan otomatis mencurigakan.

### 3.4 Evaluasi ranking pada jalur runtime yang sama dengan aplikasi
Laporan wajib (JSON + `docs/EVALUATION_REPORT.md` yang dibangkitkan otomatis):
- Precision@K dan Recall@K pada Top 1/5/10/20% klaim, baseline acak, dan *lift*; AP/PR-AUC; kurva *gain* (berapa % anomali tertangkap bila verifier hanya memeriksa X% teratas).
- **Per tipe, per tingkat kesulitan, dan per keluarga skenario** (in-family vs out-of-family), dengan jumlah kasus mentah dan **bootstrap CI berbasis grup**. Jangan melaporkan persentase tanpa n.
- **Prevalensi natural dan test enriched** dilaporkan terpisah.
- **Multi-seed:** regenerasi *seluruh* dataset untuk ≥ 5 seed (bukan hanya mengganti seed ranking) dan laporkan rata-rata ± sebaran.
- Ablation pada ranking final: financial saja → + klinis → + relasional → + Isolation Forest → full.
- Robustness: field hilang, noise, label noise 5/10%, stress set OOD.
- Latency per klaim (p50/p95) tanpa LLM dan dengan LLM.
- **Tandai kegagalan:** subtipe dengan recall nol atau tidak lebih baik dari acak harus muncul eksplisit di laporan dan UI, bukan tersembunyi dalam rata-rata.

**Acceptance:** `scripts/evaluate_p1.py --dataset synthetic_v2 --seeds 5` menghasilkan artefak versi-ed yang memuat dataset version, analysis version, config hash, seed, batasan; reproducibility test lulus; tidak ada pemanggilan LLM di evaluator; test set tidak dipakai untuk memilih konfigurasi (tambahkan test yang memeriksa alur pemilihan hanya membaca validation).

---

## FASE 4 — Kesiapan Data Sample BPJS (P1; siapkan sekarang, jalankan saat data tersedia)

Raw data belum ada. Bangun alatnya dengan **fixture fiktif** yang meniru skema, bukan data nyata.
1. Pelajari `scripts/profile_bpjs_sample.py` dan `backend/app/data/bpjs_sample_profile.py` yang sudah ada; lengkapi hingga menghasilkan laporan **agregat saja** (tanpa ID baris): distribusi diagnosis/CBG, LOS, `FKL47`, `FKL48`, missingness, relasi antar-file.
2. Buat adapter ke skema klaim kanonik: pemetaan variabel FKL/FKP/PSTV (mis. `FKL19–23` kode INA-CBG, `FKL18/FKL24` diagnosis primer/sekunder, `FKL31–32` tarif, `FKL33–46` special groups, `FKP02` tautan FKTP→FKRTL, `PSTV15` bobot). Variabel yang tidak ada di sampel (ID faskes, ID dokter, daftar obat — **verifikasi** terhadap data dictionary) harus menyebabkan **degradasi anggun**: sinyal terkait (graf dokter, cloning "same_provider", rule obat) dinonaktifkan dan dicatat, bukan error.
3. Eksperimen label lemah `FKL47 > FKL48` (penyesuaian turun saat verifikasi): baseline aturan sederhana/regresi logistik, split berbasis grup/waktu, **larangan** memakai `FKL48` atau turunannya sebagai fitur. Sebut selalu sebagai "koreksi klaim", bukan fraud.
4. Modul peer-severity: proporsi severity/CBG per diagnosis × tipe faskes × wilayah dibanding peer; gunakan `PSTV15` hanya setelah arti statistiknya dikonfirmasi.
5. Hook kalibrasi: keluaran profiling dapat menggantikan `calibration_profile.json` generator v2 (LOS, severity share, jumlah diagnosis sekunder).
6. Tambahkan `.gitignore` untuk path data mentah dan test yang gagal jika file data mentah terdeteksi di repo.

**Acceptance:** pipeline berjalan end-to-end pada fixture fiktif; laporan agregat dihasilkan; tidak ada ID baris dalam output.

---

## FASE 5 — Alur produk dan UI (P1, kecil dan terfokus)

- Ubah `/intake` menjadi **Demo Data Loader** (simulator kiriman Faskes/E-Klaim); halaman utama = **Incoming Claims** → Priority Review → Investigation → Assessment.
- Assessment **evidence-first:** skor + komponen + evidence + peer comparison + klaim serupa tampil sebelum narasi LLM; tampilkan evidence coverage/ketidakpastian dan disclaimer "perlu verifikasi, bukan fraud".
- Halaman Evaluasi menampilkan metrik **dari artefak evaluasi**, lengkap dengan n, CI, banner "Data sintetis", dan tabel kegagalan per tipe (lihat 3.4).
- Istilah: "potential financial exposure" (bukan "savings"); "benchmark deviation" (bukan "overbilling").
- Jangan menambah halaman atau dashboard baru.

---

## FASE 6 — Keandalan demo (P0 sebelum 1 November)

- Satu perintah menjalankan seluruh demo dari kondisi bersih (Docker Compose atau script), dengan artefak model terlatih dan **database demo ter-seed** (±200 klaim terkurasi yang memuat tiap tipe anomali, hard negative, dan satu skenario cloning yang sekarang terlewat setelah perbaikan lantai tier).
- Mode degradasi: tanpa Ollama/GPU, narasi memakai template dan UI menandai "narasi template"; tanpa koneksi internet demo tetap jalan.
- Uji kegagalan: satu agent gagal, LLM timeout; pipeline mengembalikan hasil parsial dan mencatatnya di audit log.
- Smoke test otomatis end-to-end (termasuk keputusan manusia dan audit record) di CI/skrip.
- Ukur latency aktual pada perangkat target dan catat.

---

## FASE 7 — Dokumentasi dan laporan akhir (P0)

- Sinkronkan `README`, `PRD`, `MODELS`, `Architecture`, `AgentWorkflow`, `BusinessCore` dengan kode (bobot, path, rentang skor, model runtime vs kandidat).
- Tambahkan `docs/MODEL_CARD.md` (tujuan, data, metrik dengan n dan CI, batasan, bias/kegagalan yang diketahui), `docs/DATA_CARD.md`, `docs/LIMITATIONS.md`.
- Laporan akhir agent (`docs/AGENT_FINAL_REPORT.md`): daftar fase selesai / sebagian / tidak dikerjakan, test yang dijalankan dan hasilnya, hal yang **tidak bisa diverifikasi** di lingkungan agent, dan tiga risiko terbesar yang tersisa.

---

## DI LUAR SKOP (jangan dikerjakan)
Agent/orchestrator framework baru, Neo4j/Qdrant/DB kedua, fine-tuning IndoBERT atau deep learning kustom, server FHIR penuh, integrasi VClaim/SATUSEHAT produksi tanpa akses API resmi, estimasi penghematan nasional dari data sintetis, dashboard baru yang hanya untuk pamer teknologi.

## URUTAN JIKA WAKTU TERBATAS
Fase 0 → Fase 2 (tier floor + semantik skor) → Fase 1 (profile `standard`) → Fase 3 (3.1 dan 3.4 dulu) → Fase 6 → Fase 7 → Fase 5 → Fase 4. Jika harus memotong, potong ablation Isolation Forest, search hyperparameter, dan sebagian Fase 5 — **bukan** reproduksibilitas, laporan kegagalan per tipe, atau demo yang stabil.

## DEFINITION OF DONE
1. Demo berjalan dari kondisi bersih dengan satu perintah; full test suite lulus.
2. Dataset sintetis v2 (profile `standard`) reproducible, tervalidasi, dan terdokumentasi sebagai sintetis.
3. Skor, tier, dan evidence konsisten antara kode, UI, dan dokumen; cloning/repeat billing yang kuat tidak lagi jatuh ke tier Low.
4. Laporan evaluasi multi-seed dengan n, CI, baseline acak, hasil per tipe dan per keluarga skenario, termasuk kegagalan, tanpa tuning terhadap test.
5. Tidak ada klaim angka yang tidak berasal dari artefak evaluasi.
