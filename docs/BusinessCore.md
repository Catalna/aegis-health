# BusinessCore.md — Logika Bisnis Inti J-ARI

> **J-ARI: JKN Agentic Risk Intelligence**  
> Nama Frontend: **AEGIS — Pusat Pemeriksaan Klaim**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 3.0  
> Status: Aktual — Disinkronkan dengan domain operasional JKN dan implementasi sistem (Oktober 2026)

Dokumen ini menjelaskan logika bisnis inti yang mengikat seluruh keputusan teknis, arsitektur data, dan pengalaman pengguna J-ARI/AEGIS. Berbeda dari [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md) (apa yang dibangun) dan [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md) (bagaimana dibangun secara teknis), BusinessCore.md menjawab: **mengapa setiap keputusan arsitektur, desain, dan data dibuat demikian — dari perspektif domain perasuransian sosial JKN dan keberlanjutan Dana Jaminan Sosial (DJS) BPJS Kesehatan**.

---

## 1. Problem Domain — Sistem Klaim JKN

### 1.1 Alur Klaim JKN (Konteks Operasional)

```
Pasien Berobat ke Faskes (RS / Klinik / Puskesmas)
                     |
                     v
Faskes Menginput Klaim melalui Sistem BPJS
(VClaim / SEP / E-Klaim INA-CBG)
                     |
                     v
Klaim Masuk ke Pipeline BPJS Kesehatan
                     |
                     v
+---------------------------------------------------+
|               [ J-ARI / AEGIS ]                   |
|       Screening & Prioritisasi Risiko Cerdas      |
|    Multi-Agent • Multi-Model • Zero-Hallucination |
+---------------------------------------------------+
                     |
                     v
Verifier BPJS Menerima Daftar Klaim Berdasarkan Prioritas
                     |
                     +---------------------------------------+
                     |                                       |
                     v                                       v
               TIER HIGH / MEDIUM                        TIER LOW
             (Review Bukti Lengkap)              (Jalur Cepat / Audit Acak)
                     |                                       |
                     v                                       v
     Keputusan: Klarifikasi / Penolakan                  Persetujuan Bayar
```

**J-ARI tidak menggantikan sistem inti BPJS yang telah ada** — melainkan beroperasi sebagai lapisan inteligensi penapisan (*Screening & Risk Intelligence Layer*) di atas data klaim yang masuk. Sistem ini membantu verifikator mengalokasikan waktu kerja mereka pada kelompok klaim dengan potensi anomali finansial atau klinis paling signifikan.

### 1.2 Skala Tantangan Operasional
Volume klaim bulanan JKN mencapai puluhan juta episode pelayanan di ribuan fasilitas kesehatan mitra di seluruh Indonesia:
- **Kapasitas Manusia Terbatas**: Jumlah verifikator medis BPJS berbanding terbalik dengan pertumbuhan eksponensial volume klaim.
- **Kelelahan Verifikasi (Verifier Fatigue)**: Meninjau ratusan berkas klaim manual setiap hari secara merata meningkatkan risiko lolosnya anomali biaya besar.
- **Pola Risiko Non-Lokal**: Anomali terorganisir (seperti *repeat billing* antar cabang atau *cloning rekam medis*) mustahil terdeteksi jika pemeriksa hanya meneliti klaim secara individual tanpa visibilitas lintas fasilitas.

---

## 2. Mekanisme Pembayaran INA-CBG — Inti Domain

### 2.1 Cara Kerja INA-CBG
INA-CBG (*Indonesia Case Base Groups*) adalah sistem pembayaran prospektif berbasis kasus (*case-mix*). Berbeda dari sistem *fee-for-service* di mana setiap item obat dan tindakan dibayar terpisah, dalam INA-CBG rumah sakit dibayar berdasarkan tarif paket standar per episode rawat:

```
Variabel Input Grouper INA-CBG:
  1. Diagnosis Primer (ICD-10)
  2. Diagnosis Sekunder / Komplikasi (ICD-10 CC/MCC)
  3. Tindakan / Prosedur Medis (ICD-9-CM)
  4. Severity Level (Tingkat Keparahan Kasus: 1 = Ringan, 2 = Sedang, 3 = Berat, 4 = Katastropik)
  5. Tipe & Regional Fasilitas (RS Tipe A, B, C, D, Wilayah Regional Tarif)
             |
             v
Tarif Paket Tetap yang Disepakati (Reimbursement Amount)
```

### 2.2 Mengapa Pemahaman INA-CBG Sangat Kritis bagi J-ARI
Sistem INA-CBG mengubah struktur insentif finansial di fasilitas kesehatan:
1. **Risiko Efisiensi Rumah Sakit**: Jika biaya perawatan aktual lebih rendah dari tarif paket, RS memperoleh surplus efisiensi; jika lebih tinggi, RS menanggung defisit.
2. **Insentif Upcoding**: Terdapat godaan struktural untuk menambahkan diagnosis sekunder artifisial atau menaikkan severity level agar klaim masuk ke kelompok tarif paket yang jauh lebih tinggi tanpa dasar klinis memadai.
3. **Insentif Unbundling**: Memecah satu episode perawatan menyeluruh menjadi beberapa klaim terpisah (misal rawat jalan berturut-turut) untuk menagih beberapa paket sekaligus.

Oleh karena itu, aturan logika domain J-ARI dibangun di sekitar matriks verifikasi aturan tarif INA-CBG, bukan sekadar detektor anomali statistik umum.

---

## 3. Tujuh Tipologi Anomali dalam JKN yang Ditargetkan

J-ARI secara khusus memodelkan dan mendeteksi 7 bentuk anomali klaim perasuransian kesehatan:

| No | Jenis Anomali | Mekanisme & Karakteristik | Deteksi dalam J-ARI | Implikasi Bisnis bagi BPJS |
|---|---|---|---|---|
| 1 | **Upcoding** | Penggelembungan derajat keparahan (severity level) atau pemilihan kode ICD-10 dengan tarif paket lebih tinggi tanpa dukungan rekam medis. | Aturan Heuristik INA-CBG (`clinical_agent.py`) + SHAP driver analysis | Pembayaran berlebih (*overpayment*) sistematis pada episode perawatan standar. |
| 2 | **Phantom Billing** | Penagihan biaya atas prosedur medis, pemeriksaan laboratorium, atau obat-obatan yang secara faktual tidak pernah diberikan kepada pasien. | Validasi Konsistensi Tanggal/LOS + Vector Search anomali deskripsi klinis | Kerugian langsung 100% pada item fiktif yang dibayarkan. |
| 3 | **Medical Record Cloning** | Penyalinan ringkasan medis, tindakan, dan rincian klaim secara identik dari pasien satu ke pasien lain dalam periode berdekatan. | LanceDB Multi-Factor Composite Similarity ($S_{composite} \ge 0.90$) | Indikasi klaim massal buatan (*batch fraudulent submissions*). |
| 4 | **Repeat Billing** | Pengajuan klaim ganda untuk episode pelayanan yang sama terhadap satu pasien di faskes yang sama dalam jendela waktu $< 30$ hari. | Verifikasi Jendela Waktu Database (`fraud_agent.py`) + Exact Duplicate Check Phase 0 | Duplikasi pembayaran untuk satu siklus penyembuhan penyakit. |
| 5 | **Unbundling** | Pemecahan paket pelayanan komprehensif menjadi beberapa klaim terpisah untuk memicu pembayaran berkali-kali. | Analisis Temporal & Relasional Prosedur Medis (`fraud_agent.py`) | Melanggar prinsip tarif paket prospektif INA-CBG. |
| 6 | **Prolonged LOS** | Perpanjangan hari rawat inap secara tidak wajar tanpa justifikasi medis perburukan kondisi pasien. | XGBoost Expected Cost vs Actual LOS deviasi batas kendali | Inefisiensi alokasi tempat tidur RS dan pembengkakan biaya rawat. |
| 7 | **Inflated Bill** | Penagihan biaya medis yang melampaui rentang interkuartil (IQR) dan deviasi prediksi wajar untuk episode sejenis. | Model Supervised XGBoost Regressor + SHAP Positive Cost Drivers | Risiko kebocoran dana akibat tarif anomali pada klaim non-standar. |

---

## 4. Prinsip Bisnis: Rekomendasi, Bukan Vonis

### 4.1 Mengapa Sistem Tidak Menyatakan "Fraud"
Dalam ranah hukum dan administrasi negara, istilah **Fraud (Kecurangan)** mensyaratkan adanya unsur niat sengaja (*intent*) dan pembuktian hukum formal yang hanya dapat ditetapkan oleh audit investigasi bersertifikat atau otoritas pengadilan.

Oleh sebab itu, J-ARI/AEGIS menganut doktrin: **Rekomendasi Penapisan Risiko, Bukan Vonis Hukum**:
1. Sistem memberi label **"Potential Risk / Anomaly Suspect"**, bukan "Fraudster".
2. Menghindari polarisasi hubungan kemitraan antara BPJS Kesehatan dan fasilitas kesehatan mitra. Anomali administratif sering kali disebabkan oleh kesalahan input kode petugas koding (*coding clerical errors*), bukan niat kriminal terorganisir.
3. Menjamin perlindungan hukum bagi verifikator BPJS yang menggunakan sistem, karena keputusan formal verifikasi tetap diambil dan ditandatangani oleh petugas manusia dengan audit trail yang jelas.

---

## 5. Nilai Bisnis J-ARI bagi BPJS Kesehatan

### 5.1 Efisiensi Alokasi Sumber Daya Verifikasi (Prinsip 80/20)
- **Tantangan Lama**: Seluruh klaim masuk ke antrean verifikasi acak dengan perhatian yang terbagi rata.
- **Dengan J-ARI**:
  - **70–80% Klaim Risiko Rendah (Low Risk)**: Dapat disaring cepat (*fast-track review*) atau diproses otomatis dengan audit berkala.
  - **15–20% Klaim Risiko Tinggi (High Risk)**: Disajikan kepada verifikator senior lengkap dengan ringkasan temuan bukti, grafik deviasi biaya, dan saran tindak lanjut spesifik.
  - Verifikator menghemat hingga **65% waktu review berkas** per klaim berisiko tinggi karena tidak perlu membaca rekam medis mentah dari awal.

### 5.2 Deteksi Multi-Sinyal Terpadu (Anti False Positive)
Model anomali tunggal (misal hanya melihat rasio biaya) sering kali menghasilkan peringatan palsu (*false positive*) pada kasus-kasus medis komplikasi berat yang memang membutuhkan biaya mahal secara sah.

J-ARI mengatasi ini dengan **Konvergensi Tiga Lapis**:
1. Klinis (apakah diagnosis masuk akal?)
2. Finansial (apakah deviasi biaya didukung tingkat keparahan?)
3. Relasional/Fraud (apakah ada pola pengulangan atau pencucian klaim?)

Skor risiko tinggi hanya diberikan jika terdapat bukti konvergen, menjaga tingkat akurasi verifikasi tetap tinggi.

### 5.3 Explainability sebagai Kebutuhan Operasional
Verifier BPJS tidak dapat menolak klaim atau meminta klarifikasi ke rumah sakit hanya dengan alasan *"algoritma AI menandai skor klaim Anda 85"*.

Rumah sakit berhak menerima penjelasan teknis yang berdasar. Melalui **SHAP TreeExplainer** dan **Indonesian Explanation Agent**, J-ARI menyediakan argumen substantif berbasis fakta:
> *"Klaim ditandai berisiko karena biaya rawat mencapai Rp 12.500.000 (deviasi +85% dari estimasi wajar Rp 6.750.000 untuk kasus Appendicitis Akut Severity 1), sementara tidak tercatat adanya diagnosis komorbiditas mayor atau penggunaan ruang ICU yang membenarkan perbedaan biaya tersebut."*

### 5.4 Estimasi Paparan Finansial (Potential Financial Exposure)
Setiap klaim yang diperiksa menghitung metrik `potential_exposure` (selisih antara biaya yang diajukan dan estimasi wajar). Metrik ini memungkinkan manajemen BPJS memprioritaskan antrean tidak hanya berdasarkan probabilitas risiko, tetapi juga berdasarkan **nilai nominal rupiah yang dapat diselamatkan bagi Dana Jaminan Sosial (DJS)**.

---

## 6. Segmentasi Risiko dan Alur Tindakan Manusia

```
+---------------------------------------------------------------------------------+
| TIER RISIKO  | SKOR RISIKO | REKOMENDASI SISTEM            | TINDAKAN VERIFIKATOR       |
+--------------+-------------+-------------------------------+----------------------------+
| HIGH         | >= 70       | Prioritas Utama Investigasi   | 1. Request Clarification   |
|              |             | Penangguhan Pembayaran        | 2. Escalate ke Tim Audit   |
|              |             | Pemeriksaan Rekam Medis Utuh  | 3. Reject jika Pelanggaran |
+--------------+-------------+-------------------------------+----------------------------+
| MEDIUM       | 40 - 69     | Review Selektif               | 1. Cek Kelengkapan Resume  |
|              |             | Klarifikasi Administrasi      | 2. Setujui Pasca Koreksi   |
+--------------+-------------+-------------------------------+----------------------------+
| LOW          | < 40        | Auto-Pass Rekomendasi         | 1. Approve / Bayar         |
|              |             | Audit Rutin Acak (Sampling)   |                            |
+--------------+-------------+-------------------------------+----------------------------+
```

### Opsi Keputusan Verifikator Manusia (`POST /api/claims/{claim_id}/decision`):
1. **Verify / Approve**: Menyetujui pembayaran klaim (baik karena klaim terbukti valid atau hasil klarifikasi faskes memuaskan).
2. **Request Clarification**: Mengirimkan surat pemberitahuan verifikasi ke fasilitas kesehatan meminta berkas pendukung tambahan (misal lembar laporan operasi atau bukti hasil lab).
3. **Escalate**: Mengeskalasi berkas ke Tim Audit Investigasi Khusus BPJS Kesehatan karena indikasi kecurangan terorganisir.
4. **Reject**: Menolak pembayaran klaim berdasarkan bukti pelanggaran aturan kepatuhan administrasi atau INA-CBG yang sah.

Setiap keputusan wajib menyertakan catatan verifikator (`verifier_notes`) dan dicatat dalam tabel `audit_logs` untuk memastikan akuntabilitas penuh.

---

## 7. Strategi Data dan Kepatuhan Etika

### 7.1 Penggunaan Data Sintetis Realistis
J-ARI dikembangkan menggunakan dataset sintetis yang dimodelkan secara ketat mengikuti distribusi epidemiologi, struktur kode tarif INA-CBG, dan pola klaim historis JKN:
- **Kepatuhan Privasi (UU PDP No. 27/2022 & Standar HIPAA)**: Nol risiko kebocoran data rekam medis pribadi pasien (*Personally Identifiable Information - PII*).
- **Injeksi Skenario Terkontrol**: Memungkinkan pengujian menyeluruh terhadap pola anomali langka yang jarang ditemui dalam sampel data audit kecil.

### 7.2 Integritas Evaluasi (Anti-Tautologi)
Model prediktif XGBoost dan aturan heuristik dievaluasi pada dataset independen yang terisolasi dari proses pembentukan fitur (*feature engineering*). Evaluasi kinerja model memastikan tidak ada ketergantungan melingkar (*circular reasoning*) di mana aturan yang mendeteksi anomali adalah aturan yang sama yang mendefinisikannya secara sepihak.

---

## 8. Referensi Dokumen Terkait

- [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md): Dokumen Kebutuhan Produk J-ARI / AEGIS.
- [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md): Arsitektur Teknis dan Desain Database.
- [AgentWorkflow.md](file:///c:/Users/Radith/E-Jak/docs/AgentWorkflow.md): Alur Investigasi Multi-Agent dan Protokol SSE.
- [MODELS.md](file:///c:/Users/Radith/E-Jak/docs/MODELS.md): Spesifikasi Teknis Model ML, SHAP, LanceDB, dan LLM.
- [API.md](file:///c:/Users/Radith/E-Jak/docs/API.md): Spesifikasi Antarmuka REST API dan Integrasi Antrean.
