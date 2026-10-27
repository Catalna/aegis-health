# AEGIS-Health — Strategic Alignment & Project Goals

**Agentic Risk Engine & Intelligent Surveillance for Healthcare**  
Dokumen arah produk untuk Healthkathon BPJS Kesehatan 2026  
Tanggal: 12 September 2026

## 1. Tujuan dokumen

Dokumen ini menyatukan arah bisnis, produk, teknis, evaluasi, dan tata kelola AEGIS-Health agar seluruh bagian project bergerak menuju tujuan yang sama. Dokumen ini menjadi acuan untuk proposal, prototype, demo, evaluasi model, dan pengembangan setelah kompetisi.

AEGIS-Health diposisikan sebagai **lapisan screening dan risk intelligence untuk membantu verifier BPJS memprioritaskan klaim yang perlu diperiksa lebih dahulu**. AEGIS-Health tidak menggantikan sistem klaim BPJS, tidak menggantikan verifier, dan tidak menetapkan bahwa suatu klaim adalah fraud.

## 2. Dasar alignment eksternal

Healthkathon 2026 menggunakan tema **“Detect Smarter, Protect JKN — Smarter Protection for a Stronger JKN: Efisiensi Risiko Program JKN.”** Tantangannya mendorong solusi digital yang dapat mengidentifikasi, mendeteksi, dan memitigasi risiko JKN dengan AI, machine learning, data analytics, atau teknologi relevan lainnya.

AEGIS-Health masuk ke kategori **Efisiensi Risiko pada Fasilitas Kesehatan**. Fokus utamanya adalah risiko pada klaim dan episode pelayanan, terutama:

- manipulasi diagnosis atau tindakan (*upcoding*);
- cloning atau penjiplakan klaim;
- phantom billing;
- inflated bills;
- repeat billing;
- services unbundling atau fragmentation;
- prolonged length of stay;
- readmisi dan klaim berulang;
- klaim obat, alat kesehatan, atau tindakan yang tidak didukung evidence.

AEGIS-Health sebaiknya memilih **upcoding dan unbundling sebagai fokus utama**, dengan cloning, repeat billing, dan financial anomaly sebagai sinyal pendukung. Scope ini cukup tajam untuk dinilai, tetapi tetap mencerminkan kemampuan multi-sinyal sistem.

BPJS menekankan bahwa Healthkathon diharapkan menghasilkan solusi yang relevan, aman, bertanggung jawab, dan berpotensi dikembangkan menjadi solusi nyata bagi JKN. Pemanfaatan AI diarahkan untuk mendukung analisis dan deteksi dini, sedangkan pemeriksaan dan keputusan akhir tetap memerlukan pertimbangan manusia. [BPJS/Healthkathon 2026 melalui pemberitaan resmi peluncuran](https://healthkathon.bpjs-kesehatan.go.id/landing-page.html) · [ringkasan tujuan dan arahan Healthkathon 2026](https://www.idntimes.com/news/indonesia/bpjs-kesehatan-gelar-healthkathon-2026-02-hs754-6165c3)

Kemenkes sedang memperkuat ekosistem kesehatan digital yang terintegrasi, interoperabel, aman, dan berbasis data. SATUSEHAT berfungsi sebagai platform penghubung ekosistem, bukan pengganti seluruh aplikasi yang sudah ada. Partner system diharapkan memperhatikan standardisasi proses bisnis, pertukaran data berbasis HL7 FHIR dan HTTPS REST API, autentikasi, serta enkripsi. [SATUSEHAT Platform](https://satusehat.kemkes.go.id/faq/platform/50c0fb80-1c3b-4bd2-bff1-119b51b96afe/apa-itu-satusehat-platform)

Kemenkes juga menekankan bahwa integrasi RME dan SATUSEHAT dapat memperkuat efisiensi klaim, transparansi, jejak audit, dan pencegahan penyimpangan. Arah ini membuat AEGIS-Health relevan sebagai lapisan analitik di atas data klaim dan clinical context yang terstruktur. [Kemenkes: tata kelola klaim JKN dan integrasi RME-SATUSEHAT](https://setjen.kemkes.go.id/news/kemenkes-perkuat-tata-kelola-klaim-jkn-melalui-integrasi-rekam-medis-elektronik-dengan-satusehat)

Untuk AI kesehatan, Kemenkes menyoroti kualitas data, keamanan, privasi, bias, manajemen risiko, dan kejelasan tanggung jawab sepanjang siklus hidup AI. [Kemenkes: tata kelola AI untuk transformasi kesehatan](https://setjen.kemkes.go.id/news/kementerian-kesehatan-perkuat-tata-kelola-ai-untuk-mendukung-transformasi-kesehatan)

## 3. Masalah yang ingin diselesaikan

Verifier menghadapi volume klaim yang besar, waktu terbatas, dan pola risiko yang tidak selalu terlihat dari satu klaim. Pemeriksaan manual dengan kedalaman yang sama untuk semua klaim dapat membuat klaim berisiko tinggi terlambat ditangani, sementara klaim valid dapat menghabiskan waktu review yang sama.

Masalah inti AEGIS-Health adalah:

> **Bagaimana membantu verifier BPJS menemukan klaim yang paling layak diperiksa lebih dahulu dan memahami alasan prioritasnya dari evidence yang dapat ditelusuri?**

AEGIS-Health tidak berusaha membuktikan niat fraud secara otomatis. Sistem mencari **indikator risiko**, menggabungkan evidence, lalu membantu manusia menentukan langkah berikutnya.

## 4. Tujuan utama AEGIS-Health

### Tujuan produk

Menyediakan priority queue klaim berbasis risiko yang membantu verifier:

1. menerima klaim yang telah diajukan dari sumber upstream seperti Faskes atau E-Klaim;
2. menyaring kesalahan data dan duplikasi awal;
3. menggabungkan sinyal clinical, finansial, dan pola historis;
4. melihat alasan dan evidence dalam satu halaman investigasi;
5. menetapkan keputusan manusia yang tercatat dan dapat diaudit.

### Tujuan kompetisi

Mendemonstrasikan bahwa solusi AI yang sederhana, terukur, dan bertanggung jawab dapat memperbaiki alokasi waktu verifikasi serta mempercepat deteksi dini risiko klaim dalam ekosistem JKN.

### Tujuan jangka panjang

Menjadi lapisan analitik yang dapat terhubung dengan ekosistem data kesehatan nasional dan sistem klaim terkait melalui adapter terstandar, tanpa mengklaim menggantikan sistem BPJS atau SATUSEHAT.

## 5. Nilai utama bagi pemangku kepentingan

### BPJS dan verifier

- mengurutkan klaim berdasarkan prioritas risiko;
- mempercepat pemeriksaan awal;
- menyediakan alasan yang mudah ditelusuri;
- mempermudah perbandingan dengan klaim sejenis;
- membuat keputusan verifier dan jejak audit lebih konsisten.

### Fasilitas kesehatan

- mengurangi klarifikasi yang tidak perlu melalui evidence yang lebih jelas;
- membantu menemukan inkonsistensi administratif atau coding sebelum menjadi sengketa;
- menjaga proses tetap berbasis evidence, bukan tuduhan otomatis.

### Peserta JKN dan program JKN

- memperkuat perlindungan dana jaminan sosial;
- mendukung layanan yang lebih efisien dan berintegritas;
- mengurangi risiko kebocoran tanpa mengorbankan klaim yang sah.

## 6. Boundary produk yang harus konsisten

### Sumber data

Faskes atau E-Klaim diperlakukan sebagai **sumber data**, bukan user utama AEGIS-Health pada MVP. Demo Data Loader hanya mensimulasikan klaim yang masuk dari upstream. Produk utama dimulai dari halaman **Incoming Claims**.

### Pengguna utama

BPJS Verifier adalah pengguna utama. Tim investigasi fraud dan manajemen/auditor merupakan pengguna lanjutan atau persona roadmap.

### Output

Output utama adalah:

- risk score;
- priority tier;
- ranked evidence;
- peer comparison;
- similar claims atau pattern findings;
- recommended next action;
- uncertainty dan evidence coverage;
- human verification decision.

Output bukan “fraud confirmed”, bukan “claim rejected” otomatis, dan bukan diagnosis medis.

## 7. Arsitektur produk yang disepakati

```text
Faskes / E-Klaim / Demo Data Source
                ↓
        Incoming Claims
                ↓
 Data Quality & Deterministic Validation
                ↓
 ┌──────────────┼──────────────┐
 ↓              ↓              ↓
Clinical      Financial      Pattern
Rules         Benchmark      Analysis
                ↓
    Deterministic Evidence Aggregator
                ↓
       Deterministic Risk Engine
                ↓
          Priority Review Queue
                ↓
       Evidence-First Investigation
                ↓
       AI Investigation Assistant
                ↓
         Human Verifier Decision
                ↓
             Audit Trail
```

Risk score harus dihitung secara deterministic. LLM hanya digunakan untuk merangkum evidence dan menjawab pertanyaan terarah berdasarkan data yang sudah tersedia. LLM tidak boleh menambah poin risiko, mengubah tier, atau menyimpulkan fraud.

## 8. Komponen teknis yang dipertahankan

### Clinical and domain rules

Pertahankan simplified grouper dan rule engine, tetapi pisahkan labelnya menjadi:

- **domain-backed rule:** memiliki dasar regulasi, coding, clinical pathway, atau referensi tarif yang terdokumentasi;
- **prototype screening signal:** heuristic yang masih memerlukan validasi domain.

Rule seperti severity tinggi tanpa procedure pendukung, ketidaksesuaian diagnosis-procedure, duplicate episode, dan prolonged stay harus dijelaskan melalui evidence. Jangan menyatakan diagnosis tertentu otomatis berarti fraud.

### Financial benchmark

Ganti istilah “fair medical cost” menjadi **peer-adjusted reimbursement benchmark** atau **expected claim benchmark**. Benchmark harus memperhitungkan diagnosis, procedure, severity, LOS, tipe fasilitas, periode, dan kelompok peer.

Model tidak boleh belajar dari klaim abnormal tanpa kontrol. Jika label valid belum tersedia, jelaskan bahwa model mengukur deviasi terhadap pola pembanding, bukan “harga medis yang benar”.

### Pattern and similarity engine

Structured matching menjadi inti:

- exact dan near-duplicate;
- kesamaan diagnosis dan procedure;
- provider dan patient relationship;
- rentang waktu;
- episode overlap;
- billing repetition.

Embedding adalah sinyal tambahan, bukan dasar tunggal. Semua threshold, bobot, dan window waktu harus dikalibrasi melalui evaluasi.

### Isolation Forest and graph

Isolation Forest hanya dipertahankan jika ablation study membuktikan nilai tambah pada top-K ranking. Graph metrics harus dinormalisasi terhadap ukuran dan karakteristik peer; volume relasi tinggi tidak boleh otomatis dianggap mencurigakan.

### LLM

Gunakan satu model utama untuk explanation dan guided Q&A, dengan template fallback. Review Agent dan Investigator Copilot disatukan menjadi **AI Investigation Assistant**. Komponen ini membaca evidence terstruktur dan menghasilkan narasi Bahasa Indonesia yang dapat ditelusuri kembali ke sumbernya.

## 9. Data strategy

MVP menggunakan synthetic data karena data peserta JKN riil tidak boleh digunakan tanpa izin resmi. Synthetic data harus dirancang agar tetap berguna untuk demonstrasi dan evaluasi:

1. generator data normal dipisahkan dari detector;
2. data training, blind test, dan stress test memakai skenario berbeda;
3. pola test tidak sekadar perubahan random seed dari pola training;
4. anomaly type dan tingkat kesulitan didokumentasikan;
5. ground truth disimpan terpisah dari input model;
6. hasil evaluasi ditampilkan apa adanya.

Canonical claim schema sebaiknya memiliki patient pseudonym, provider, facility, encounter, diagnoses, procedures, service items, dates, total, source, dan provenance. Adapter dapat disiapkan untuk CSV demo, E-Klaim, atau format FHIR/SATUSEHAT pada roadmap.

## 10. Metrik keberhasilan

Metrik utama bukan accuracy keseluruhan, karena kasus berisiko diperkirakan minoritas. Metrik yang perlu ditampilkan:

- Precision@K untuk top-50/top-100 klaim;
- Recall@K terhadap klaim anomaly pada test set;
- PR-AUC;
- false positive rate;
- false negative rate;
- calibration atau reliability score;
- latency per claim;
- pipeline completion rate dan fallback rate;
- data-quality coverage;
- waktu review sebelum dan sesudah bantuan AEGIS-Health pada simulasi pengguna.

Tambahkan ablation table:

| Konfigurasi | Tujuan |
|---|---|
| Financial baseline | Mengukur manfaat model biaya saja |
| Clinical + financial | Mengukur kontribusi domain rules |
| + pattern/similarity | Mengukur kontribusi relasional |
| + Isolation Forest | Menguji apakah unsupervised signal memberi nilai tambahan |
| Full system | Mengukur performa sistem final |

Semua angka yang belum diuji harus diberi label **target**, bukan hasil.

## 11. KPI dampak yang aman diklaim

AEGIS-Health boleh mengklaim tujuan berikut:

- mempercepat triage awal;
- membantu verifier memusatkan perhatian pada klaim berprioritas tinggi;
- meningkatkan keterlacakan alasan review;
- mengurangi waktu pencarian evidence;
- membantu mendeteksi potensi financial exposure lebih awal.

AEGIS-Health belum boleh mengklaim:

- telah membuktikan fraud;
- pasti menghemat nominal tertentu;
- pasti mengurangi fraud secara nasional;
- siap production tanpa pilot dan validasi eksternal;
- dapat menggantikan verifier atau investigator.

Gunakan istilah **potential financial exposure**, bukan potential savings, kecuali dampak penghematan telah dihitung dari keputusan manusia yang tervalidasi.

## 12. UI dan demo yang konsisten

Alur demo:

1. Demo Data Loader memuat synthetic claim batch dari simulated Faskes/E-Klaim.
2. Incoming Claims menampilkan klaim yang telah diterima.
3. AEGIS-Health menjalankan screening.
4. Priority Review menampilkan ranking risiko.
5. Verifier membuka satu klaim prioritas tinggi.
6. Investigation menampilkan timeline dan status agent.
7. Assessment menampilkan risk score, evidence coverage, uncertainty, SHAP, peer comparison, dan similar claims.
8. AI Investigation Assistant memberikan ringkasan dan pertanyaan preset.
9. Verifier memilih Verified Valid, Request Clarification, Needs Further Review, atau Escalate.
10. Sistem menyimpan keputusan dan audit trail.

UI harus evidence-first. Risk score dan alasan deterministik tampil sebelum narasi AI. Selalu tampilkan disclaimer bahwa high risk berarti perlu verifikasi, bukan fraud yang sudah terbukti.

## 13. Privacy, security, and responsible AI

Minimum governance yang harus terlihat dalam proposal dan prototype:

- synthetic atau pseudonymized data;
- minimisasi PII;
- pseudonymous patient/provider ID;
- role-based access untuk verifier dan auditor;
- enkripsi saat transit dan saat tersimpan pada implementasi lanjutan;
- audit log untuk pipeline dan keputusan manusia;
- provenance data dan model version;
- model version serta dataset version pada setiap analisis;
- monitoring missing features dan distribution shift;
- mekanisme human override;
- dokumentasi false positive dan false negative;
- proses klarifikasi ketika evidence tidak lengkap;
- larangan penggunaan output AI sebagai keputusan otomatis.

## 14. Roadmap yang realistis

### Fase 1 — Konsistensi domain dan produk

- tetapkan fokus utama upcoding dan unbundling;
- ubah Claim Intake menjadi Incoming Claims;
- ubah Demo Loader menjadi simulator upstream;
- rapikan istilah INA-CBG dan financial benchmark;
- pisahkan data source, model output, dan human decision.

### Fase 2 — Validasi model

- bangun blind test dan stress test;
- kalibrasi weights serta thresholds;
- jalankan Precision@K, Recall@K, PR-AUC, calibration, dan latency;
- lakukan ablation study;
- pilih satu model LLM utama.

### Fase 3 — Demo dan governance

- bangun satu alur demo end-to-end;
- tampilkan evidence coverage dan uncertainty;
- lengkapi audit trail dan model metadata;
- siapkan disclaimer serta batasan sistem;
- ukur waktu review pada skenario simulasi.

### Fase 4 — Pasca-Hackathon

- validasi bersama domain expert;
- pilot dengan data yang memiliki izin;
- adapter HL7 FHIR/SATUSEHAT atau interface resmi yang relevan;
- feedback loop dari keputusan verifier;
- provider risk profiling;
- live graph dan model monitoring yang lebih matang.

## 15. Project goals yang harus dijaga

Semua keputusan desain harus menjawab lima tujuan berikut:

1. **Problem-first:** teknologi dipilih karena membantu verifier menyelesaikan masalah nyata.
2. **Evidence-first:** setiap prioritas memiliki alasan yang dapat ditelusuri.
3. **Human-led:** AI membantu screening dan pemahaman; manusia mengambil keputusan.
4. **Data-responsible:** data sintetis atau berizin, aman, terstandar, dan dapat diaudit.
5. **Measurable and scalable:** manfaat diukur dengan ranking metrics, latency, usability, dan kesiapan integrasi.

## 16. Positioning final

### Satu kalimat

> **AEGIS-Health membantu verifier BPJS memprioritaskan klaim JKN yang paling perlu diperiksa dengan menggabungkan sinyal clinical, reimbursement, dan pola historis ke dalam risk score yang transparan serta evidence yang dapat ditelusuri.**

### Tagline

> **Detect the risk. Verify with evidence. Protect JKN.**

### Pernyataan batasan

> **AEGIS-Health tidak menentukan fraud dan tidak menggantikan verifier. AEGIS-Health membantu menentukan klaim mana yang perlu diperiksa lebih dahulu dan mengapa.**

## 17. Definition of done untuk Healthkathon

AEGIS-Health siap dipresentasikan apabila:

- fokus kategori dan anomaly type sudah jelas;
- workflow dimulai dari incoming claim, bukan input manual verifier;
- risk score tidak dipengaruhi LLM;
- data synthetic, ground truth, dan keterbatasan dijelaskan;
- hasil evaluasi nyata tersedia atau target diberi label jelas;
- top-K ranking dapat didemonstrasikan;
- evidence dapat ditelusuri ke rule/model output;
- human decision dan audit trail berfungsi;
- privacy dan responsible AI dijelaskan;
- demo end-to-end dapat selesai tanpa bergantung pada koneksi eksternal;
- proposal menunjukkan dampak, kelayakan, dan roadmap yang realistis.

## 18. Kesimpulan

AEGIS-Health paling kuat ketika diposisikan sebagai sistem **risk prioritization dan evidence intelligence** untuk membantu proses verifikasi klaim JKN. Kesesuaian dengan Healthkathon 2026 kuat karena project berhubungan langsung dengan efisiensi risiko Faskes dan penggunaan AI untuk deteksi dini.

Kunci keberhasilan project bukan menambah lebih banyak agent, model, atau framework. Kunci utamanya adalah memperkuat validitas domain, menjaga skor tetap deterministik, menguji ranking secara jujur, mengurangi scope, dan menunjukkan bahwa verifier dapat bekerja lebih cepat dengan evidence yang lebih jelas.

Dengan arah ini, AEGIS-Health dapat menjawab target kompetisi, mendukung agenda BPJS untuk deteksi risiko berbasis data, dan selaras dengan arah Kemenkes mengenai interoperabilitas, efisiensi klaim, keamanan data, serta responsible AI.

## Referensi utama

- [Healthkathon BPJS Kesehatan 2026](https://healthkathon.bpjs-kesehatan.go.id/landing-page.html)
- [BPJS Kesehatan](https://www.bpjs-kesehatan.go.id/)
- [Kementerian Kesehatan RI](https://www.kemkes.go.id/id/home)
- [SATUSEHAT Platform](https://satusehat.kemkes.go.id/faq/platform/50c0fb80-1c3b-4bd2-bff1-119b51b96afe/apa-itu-satusehat-platform)
- [Kemenkes: Tata kelola klaim JKN dan integrasi RME-SATUSEHAT](https://setjen.kemkes.go.id/news/kemenkes-perkuat-tata-kelola-klaim-jkn-melalui-integrasi-rekam-medis-elektronik-dengan-satusehat)
- [Kemenkes: Tata kelola AI untuk transformasi kesehatan](https://setjen.kemkes.go.id/news/kementerian-kesehatan-perkuat-tata-kelola-ai-untuk-mendukung-transformasi-kesehatan)
- [Kemenkes: Digitalisasi sebagai kunci pemerataan layanan kesehatan](https://kemkes.go.id/id/menkes-budi-digitalisasi-jadi-kunci-pemerataan-layanan-kesehatan-nasional-)
- [Peraturan Menteri Kesehatan No. 12 Tahun 2025](https://jdih.kemkes.go.id/storage/documents/pdfs/2025permenkes012.pdf)
