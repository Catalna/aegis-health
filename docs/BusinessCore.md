# BusinessCore.md — Logika Bisnis Inti J-ARI

> **J-ARI: JKN Agentic Risk Intelligence**  
> Healthkathon 2026 BPJS Kesehatan  
> Versi Dokumen: 1.0  
> Status: Business Core Specification  

Dokumen ini menjelaskan logika bisnis inti yang mengikat seluruh keputusan teknis dan produk J-ARI. Berbeda dari [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md) (apa yang dibangun) dan [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md) (bagaimana dibangun secara teknis), BusinessCore.md menjawab: **mengapa setiap keputusan arsitektur, desain, dan data dibuat demikian — dari perspektif domain JKN dan nilai bisnis bagi BPJS Kesehatan**.

---

## 1. Problem Domain — Sistem Klaim JKN

### Alur Klaim JKN (Konteks Operasional)

```
Pasien berobat ke Faskes (RS/Klinik/Puskesmas)
       |
       v
Faskes input klaim melalui sistem BPJS
(Vclaim / SEP / e-klaim)
       |
       v
Klaim masuk ke sistem BPJS Kesehatan
       |
       v
[J-ARI beroperasi di sini]
Screening & prioritisasi risiko
       |
       v
Verifier BPJS review klaim berisiko tinggi
       |
       v
Pembayaran / klarifikasi / penolakan
```

**J-ARI tidak menggantikan sistem klaim BPJS yang ada** — ia beroperasi sebagai lapisan inteligensi screening (*Screening & Risk Intelligence Layer*) di atas data klaim yang sudah masuk, membantu verifier memfokuskan waktu terbatas mereka pada klaim yang paling berisiko.

### Skala Masalah

Volume klaim JKN yang masif menyebabkan verifikasi manual menjadi tidak efisien:
- Tidak semua klaim bisa diperiksa dengan kedalaman yang sama.
- Sumber daya verifikasi terbatas harus dialokasikan secara prioritas.
- Pola risiko tidak terlihat dari satu klaim tunggal — butuh perbandingan antar klaim, antar provider, dan antar periode waktu.

---

## 2. Mekanisme Pembayaran INA-CBG — Inti Domain

### Cara Kerja INA-CBG

INA-CBG (Indonesia Case Base Groups) adalah sistem pembayaran prospektif BPJS Kesehatan:

```
Input ke Grouper INA-CBG:
  - Diagnosis primer (ICD-10)
  - Diagnosis sekunder / komplikasi (CC/MCC)
  - Prosedur tindakan
  - Severity level (tingkat keparahan 1-4)
  - Tipe fasilitas (RS Tipe A/B/C/D, Puskesmas, Klinik)
       |
       v
Grouper menghasilkan CBG Group
       |
       v
CBG Group menentukan TARIF TETAP yang dibayar BPJS
(bukan berdasarkan biaya aktual yang diklaim Faskes)
```

### Mengapa INA-CBG Kritis untuk J-ARI

Upcoding dalam konteks JKN bukan sekadar "manipulasi angka" — melainkan memanipulasi **input spesifik ke grouper** agar klaim jatuh ke CBG group dengan tarif lebih tinggi:

| Strategi Upcoding | Mekanisme | Dampak |
|---|---|---|
| Severity inflation | Menaikkan severity level 2 -> 3 atau 3 -> 4 tanpa bukti klinis | Tarif CBG naik signifikan karena CC/MCC |
| Diagnosis creep | Menambah diagnosis sekunder (komplikasi fiktif) seperti A41.9, Z87.39, E46 | Memenuhi syarat CC/MCC untuk severity lebih tinggi |
| Procedure upcoding | Mengklaim prosedur yang lebih kompleks dari yang dilakukan | Grouper masuk ke CBG group lebih mahal |
| Unbundling | Memecah satu paket tindakan jadi beberapa klaim terpisah | Pembayaran lebih dari tarif CBG yang seharusnya |

**Implikasi untuk desain J-ARI:** Clinical Agent harus secara eksplisit memodelkan logika grouper — verifikasi "apakah severity level konsisten dengan prosedur dan diagnosis yang diklaim" — bukan sekadar memeriksa konsistensi klinis generik.

---

## 3. Jenis Anomali dan Implikasi Bisnis

### 3.1 Upcoding — Anomali Utama yang Difokuskan

**Definisi operasional:** Klaim di mana severity level atau diagnosis sekunder yang dilaporkan tidak konsisten dengan prosedur dan obat yang diklaim, menghasilkan pembayaran CBG yang lebih tinggi dari yang seharusnya.

**Sinyal yang dicari J-ARI:**
- Severity >= 3 tanpa prosedur pendukung yang sesuai.
- Diagnosis sekunder "berisiko upcoding" (A41.9 sepsis, Z87.39 riwayat infeksi, E46 malnutrisi) pada severity tinggi.
- Biaya yang diklaim jauh di atas tarif referensi CBG simplified grouper.
- Obat yang diklaim tidak konsisten dengan tingkat keparahan yang dilaporkan.

### 3.2 Phantom Billing

**Definisi:** Klaim untuk tindakan atau layanan yang tidak pernah dilakukan.

**Sinyal:** Cost anomaly ekstrem; prosedur berbiaya tinggi tanpa bukti klinis lain yang konsisten.

### 3.3 Cloning

**Definisi:** Menyalin klaim pasien lain (atau klaim lama) dengan sedikit modifikasi untuk menghasilkan tagihan baru.

**Sinyal:** Similarity score komposit tinggi (>= 0.85) antara klaim dengan claim_id berbeda, terutama dari provider yang sama untuk pasien berbeda.

### 3.4 Repeat Billing

**Definisi:** Menagih layanan yang sama untuk pasien yang sama lebih dari sekali dalam periode yang berdekatan.

**Sinyal:** Exact/near-match pada (patient_id, procedure_codes, date_range) yang sudah pernah dibayar.

### 3.5 Unbundling

**Definisi:** Memecah satu paket tindakan (yang seharusnya masuk satu CBG group) menjadi beberapa klaim terpisah untuk memaksimalkan pembayaran.

**Sinyal:** Multiple klaim dari provider/pasien yang sama dalam window waktu pendek dengan procedure_codes saling tumpang tindih.

---

## 4. Prinsip Bisnis: Rekomendasi, Bukan Vonis

### Mengapa Sistem Tidak Memutuskan "Fraud"

Ini keputusan bisnis yang disengaja, bukan keterbatasan teknis:

1. **Konteks klinis tidak sepenuhnya terlihat di data klaim** — kondisi pasien yang sebenarnya mungkin memang membenarkan severity tinggi meski tidak terlihat di kode prosedur.
2. **Kesalahan administratif ≠ fraud** — banyak anomali klaim adalah error coding, bukan manipulasi disengaja.
3. **Legal liability** — sistem yang secara otomatis melabeli "fraud" tanpa verifikasi manusia menimbulkan risiko hukum.
4. **Kepercayaan faskes** — sistem yang terlalu agresif menolak klaim menciptakan disinsentif untuk faskes yang legitimate.

**Posisi J-ARI:**
- Output tertinggi: "High Risk — Requires Verification" (prioritas investigasi).
- Keputusan akhir selalu di tangan verifier BPJS.
- Evidence yang disediakan untuk mendukung investigasi manusia, bukan menggantikannya.

---

## 5. Nilai Bisnis J-ARI

### 5.1 Efisiensi Alokasi Sumber Daya Verifikasi

Tanpa J-ARI, verifier harus memeriksa semua klaim dengan prioritas yang sama atau menggunakan heuristik manual sederhana (biaya tertinggi, dll.) yang tidak mempertimbangkan sinyal klinis dan relasional.

Dengan J-ARI:
- Verifier dapat fokus pada top-K klaim dengan risiko tertinggi dan evidence terkuat.
- Skor dan breakdown yang transparan mengurangi waktu yang dibutuhkan per investigasi.
- Perbandingan similar claims mempercepat identifikasi pola cloning.

### 5.2 Deteksi Multi-Sinyal yang Terintegrasi

Nilai utama J-ARI bukan dari satu model atau satu sinyal, melainkan dari **integrasi tiga jenis sinyal yang saling menguatkan**:

```
Sinyal Clinical      Sinyal Financial      Sinyal Fraud/Pattern
(INA-CBG grouper)   (XGBoost + SHAP)      (LanceDB similarity)
       |                   |                      |
       +-------------------+----------------------+
                           |
                    Review Agent
              (sintesis cross-sinyal)
                           |
                    Risk Score Engine
              (prioritisasi deterministik)
```

Klaim yang hanya punya satu sinyal lemah (biaya sedikit di atas rata-rata) berbeda secara kualitatif dari klaim yang punya tiga sinyal kuat sekaligus (severity inflated + biaya 200% di atas peer + identik dengan klaim lain dari provider yang sama).

### 5.3 Explainability sebagai Kebutuhan Operasional

Verifier tidak bisa menindaklanjuti skor tanpa konteks. Evidence yang bisa langsung dikutip dalam proses klarifikasi/penolakan klaim adalah syarat operasional, bukan fitur tambahan:

- SHAP breakdown menunjukkan fitur mana yang paling berkontribusi ke skor.
- Evidence text menjelaskan mengapa masing-masing agent menandai risiko.
- Similar claims memberikan preseden konkret untuk investigasi.

### 5.4 Estimasi Potensi Penghematan

J-ARI menghitung potensi penghematan dana klaim abnormal melalui formula:
$$\text{Potential Savings} = \sum \max(0, \text{cost\_claimed} - \text{predicted\_cost\_upper})$$
untuk seluruh klaim pada tier *High* dan *Medium*.

Ini bukan angka definitif (tidak semua klaim anomali terbukti fraud), tetapi memberi gambaran order-of-magnitude dari nilai finansial yang dipertaruhkan dalam klaim berisiko yang terdeteksi.

---

## 6. Segmentasi Risiko dan Tindakan

### Tier Risiko dan Rekomendasi

| Tier | Skor | Recommended Action | Interpretasi Bisnis |
|---|---|---|---|
| High | >= 60 | `verify_immediately` | Klaim dengan multiple sinyal kuat — verifier harus prioritaskan untuk investigasi segera |
| Medium | 25-59.9 | `review_when_available` | Sinyal ada tapi tidak konklusif — perlu review tapi tidak mendesak |
| Low | < 25 | `low_priority` | Klaim tampak normal berdasarkan semua sinyal — proses normal |

### Human Decision Options

| Keputusan | Makna Bisnis |
|---|---|
| Verified Valid | Verifier menyimpulkan klaim sah setelah investigasi — proses pembayaran dilanjutkan |
| Needs Further Review | Butuh informasi tambahan dari faskes sebelum keputusan |
| Escalate | Indikasi kuat yang perlu ditangani tim investigasi fraud khusus |
| Request Clarification | Minta faskes memberikan klarifikasi atau dokumen pendukung |

Semua keputusan ini dicatat di `audit_logs` dan `human_decisions` dengan timestamp dan nama reviewer — memenuhi persyaratan auditability yang diwajibkan dalam sistem pengendalian klaim.

---

## 7. Hubungan Antar Entitas Bisnis

```
PROVIDER (RS/Klinik/Puskesmas)
    |
    | 1:N
    v
DOCTOR (dokter attending / operating)
    |
    | 1:N
    v
CLAIM (klaim per episod perawatan)
    |
    | N:1
    v
PATIENT (peserta JKN)
```

**Relevansi untuk deteksi:** Pola risiko sering muncul di level provider atau dokter, bukan hanya di level klaim individual:
- Provider yang secara konsisten melaporkan severity lebih tinggi dari rata-rata peer group.
- Dokter dengan cluster klaim berisiko yang tidak proporsional.
- Network provider-dokter-pasien yang menunjukkan pola koordinasi mencurigakan.

Graph metrics yang dikomputasi secara batch (*degree centrality*, *clustering coefficient* per provider) dipakai sebagai faktor pengali pada komponen `isolation_forest_anomaly` di risk engine — provider dengan centrality tidak wajar mendapat bobot anomali lebih tinggi.

---

## 8. Strategi Data dan Etika

### Mengapa Synthetic Data

- Dataset klaim JKN riil tidak tersedia publik (data kesehatan sensitif).
- Hackathon environment: tidak ada jalur yang sah untuk akses data riil dalam kurun waktu terbatas.
- Synthetic data dengan metodologi yang tepat cukup untuk demonstrasi konsep.

### Anti-Tautologi — Integritas Evaluasi

Tautologi data sintetis adalah risiko bisnis: jika tim yang membuat anomali di data juga yang membangun detector, sistem dijamin "berhasil" tapi tidak terbukti bisa mendeteksi pola yang belum pernah dilihat.

Mitigasi:
- Peran pembuat data dan pembuat detector dipisahkan (*rule separation*).
- Held-out test set dibuat dengan seed berbeda, tidak pernah dilihat selama tuning.
- Evaluasi metrik (Precision, Recall, F1, PR-AUC, MAE, RMSE) dihitung dan dipublikasikan apa adanya di halaman ML Evaluation — tanpa angka simulasi.

### Prinsip PII Minimization

Skema data menggunakan:
- `age_band` (kelompok umur) bukan tanggal lahir eksak.
- `region_code` bukan alamat lengkap.
- Patient ID pseudonim, bukan nama asli.

Ini konsisten dengan prinsip data minimal yang diperlukan untuk deteksi risiko — tidak lebih.

---

## 9. Pembeda dari Fraud Detector Generik

| Dimensi | Generic Fraud Detector | J-ARI |
|---|---|---|
| Domain knowledge | Deteksi anomali statistik generik | Logika INA-CBG grouper: diagnosis+severity+prosedur -> CBG group -> tarif |
| Sinyal | Satu atau dua sinyal (biasanya financial) | Tiga sinyal terintegrasi: clinical, financial, similarity/pattern |
| Explainability | Black box atau skor tunggal | SHAP breakdown + evidence per agent + narasi Bahasa Indonesia |
| Output | "Fraud" / "Not Fraud" | Prioritas verifikasi + evidence untuk human investigator |
| Transparansi | Skor tanpa konteks | Setiap angka traceable ke rule/SHAP value yang didokumentasikan |
| Bahasa | Bahasa Inggris default | Narasi dan evidence dalam Bahasa Indonesia untuk verifier BPJS |

---

## 10. Roadmap Pasca-Hackathon

Fitur yang sengaja di-scope-out dari MVP tetapi logis untuk pengembangan lanjutan:

| Fitur | Nilai Bisnis | Prasyarat |
|---|---|---|
| Neo4j live graph query | Query network real-time untuk investigasi mendalam relasi provider-dokter | Data volume yang justifies graph DB; tim yang familiar |
| Feedback loop dari keputusan verifier ke model | Continuous learning dari keputusan manusia untuk meningkatkan akurasi | Volume keputusan yang cukup untuk retraining bermakna |
| IndoBERT / clinical NER | Jika ada free-text clinical notes — NER untuk ekstraksi kondisi klinis | Data dengan free-text clinical notes |
| Provider risk profiling | Dashboard risiko per provider berdasarkan riwayat klaim | Akumulasi data historis dalam sistem |
| What-if simulation | "Jika biaya di peer range, skor berapa?" — membantu verifier memahami threshold | Risk engine yang sudah stabil di produksi |
| LangGraph untuk audit trail | Retry logic + step-by-step audit per node yang lebih granular | Kapasitas tim yang familiar dengan framework |
| Integration dengan sistem BPJS existing | J-ARI menerima klaim langsung dari Vclaim/SEP secara real-time | API resmi BPJS + negosiasi integrasi |

---

## 11. Referensi Dokumen Terkait
- [PRD.md](file:///c:/Users/Radith/E-Jak/docs/PRD.md) — Spesifikasi Kebutuhan Produk.
- [Architecture.md](file:///c:/Users/Radith/E-Jak/docs/Architecture.md) — Cetak Biru Arsitektur Teknis.
- [AgentWorkflow.md](file:///c:/Users/Radith/E-Jak/docs/AgentWorkflow.md) — Detail Pipeline Agent & SSE Protocol.
- [Models.md](file:///c:/Users/Radith/E-Jak/docs/Models.md) — Spesifikasi Model ML, Vector Database & LLM.
