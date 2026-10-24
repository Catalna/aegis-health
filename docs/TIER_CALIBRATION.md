# Kalibrasi ambang tier runtime (Fase 2 leftover)

> **Synthetic demonstrator only — not BPJS performance validation.**

- Ambang lama: medium ≥ 25, high ≥ 60 (warisan, tidak pernah dikalibrasi). Kalibrasi memakai slice **validation**; verifikasi transfer **sekali** di slice test.
- Aturan pra-registrasi (rule v3): grid diambil dari **nilai skor yang ada di data** (skor runtime terkuantisasi); window `0.10 ≤ alert_frac ≤ 0.22` dan `high_frac ≤ 0.08`; pemilihan = maksimum precision pada alert, tie-break recall. Bila window kosong → fallback: minimalkan `|alert_frac − 0.20|` (target kapasitas verifier), tie-break precision; high = nilai skor terkecil di atas medium dengan `high_frac ≤ 0.10`.
- Slice: 700 klaim validation (prevalensi 50%); slice test 700 (prevalensi 50%), jalur runtime deterministik tanpa LLM.
- Artefak lengkap: `backend/models_trained/tier_band_calibration.json` (grid penuh + histogram), skrip `scripts/calibrate_tier_bands.py`.

## Distribusi skor (validation, ciri menggumpal)

| Label | p25 | p50 | p75 | p90 |
|---|---|---|---|---|
| normal | 35.0 | 35.0 | 48.0 | 48.0 |
| anomaly | 35.0 | 43.0 | 48.0 | 48.0 |

Skor runtime menggumpal di dua nilai dominan — **35** (136 normal / 99 anomali) dan **48** (111/123) — sisanya tersebar jarang. Di atas clump 48 penghuninya minim, dan **tidak ada satu pun klaim normal di skor ≥ 48.7** pada slice validation (6 normal di 51.0 adalah satu-satunya normal di atas 50; semua ≥ 52 murni anomali).

Grid dengan window pra-registrasi **kosong** karena diskontinuitas antar-clump (share alert lompat 0.80 → 0.46 → 0.049 tanpa nilai di antaranya) — sehingga rule v3 fallback aktif dan band dipilih sebagai terdekat kapasitas 20% yang tersedia. Titik-titik kunci:

| medium ≥ | high ≥ | alert_frac | precision (alert) | recall_pos (alert) |
|---|---|---|---|---|
| 25.0 (default) | 60.0 | 0.861 | 0.519 | 0.894 |
| 35.0 | 55.0 | 0.799 | 0.522 | 0.834 |
| 48.0 | 55.0 | 0.383 | 0.563 | 0.431 |
| **48.7** | **55.0** | **0.049** | **0.824** | **0.080** |
| 52.0 | 55.0 | 0.021 | 1.000 | 0.043 |

## Baseline lama vs ambang terpilih

| Metrik | default (25/60) validation | default test | terpilih (48.7/55) validation | terpilih (48.7/55) test |
|---|---|---|---|---|
| alert_frac (medium+high) | 0.861 | 0.889 | 0.049 | 0.057 |
| precision (alert) | 0.519 | 0.510 | 0.824 | 0.800 |
| recall_pos (alert) | 0.894 | 0.906 | 0.080 | 0.091 |
| high_frac | 0.009 | 0.019 | 0.017 | 0.026 |
| precision (high) | 1.000 | 1.000 | 1.000 | 1.000 |

**Ambang terpilih: medium ≥ 48.7, high ≥ 55.0** — dipilih oleh rule v3 fallback dari grid validation ("terdekat kapasitas yang tersedia"); test diverifikasi sekali dan angkanya dilaporkan apa adanya.

## Distribusi tier test (ambang terpilih) per tipe

| Tipe | low | medium | high |
|---|---|---|---|
| cloning | 49 | 1 | 0 |
| inflated_bill | 49 | 1 | 0 |
| none (normal) | 342 | 8 | 0 |
| phantom_billing | 46 | 4 | 0 |
| prolonged_los | 48 | 2 | 0 |
| repeat_billing | 49 | 1 | 0 |
| unbundling | 36 | 1 | 13 |
| upcoding | 41 | 4 | 5 |

## Implementasi (land ini)

- Konstanta diterapkan bersama land ini: `backend/app/agents/risk_engine.py` (band 55.0 / 48.7) dan mirror `backend/app/evaluation/pipeline.py::_priority_tier`.
- Floor relasional diperluas: **unbundling** kini juga menetapkan tier minimum Medium, selaras dengan narasi evidence engine sendiri ("bukti relasional kuat menetapkan tier minimum Medium") yang sebelumnya hanya mencakup repeat/cloning. Tanpa ini, klaim unbundling-saja (skor 25.0) akan jatuh ke Low di bawah ambang baru.
- Test suite penuh setelah perubahan: **334 passed / 2 skipped** (tidak ada test yang menyandera batas lama; floor menjaga kontrak tier).
- Caveat utama: band baru menurunkan recall alert runtime ke ~9% pada slice enriched — band adalah label kapasitas triase (siapa diprioritaskan verifikasi), bukan instrumen deteksi; instrumen deteksi tetap ranking skor runtime (AP 0.5964) dan kandidat ML. Recall engine pulih lewat backlog perbaikan mesin (jendela repeat 46–60 hari, ambang investigation-candidate v2 cloning, peta tariff v1→katalog v2) — bukan lewat ambang.

## Limitations

- Prevalensi slice 50% (enriched): fraksi alert di produksi (~3% prevalensi) akan lebih kecil; fraksi di sini relevan sebagai ordering band, bukan volume absolut.
- Konteks relasional = sampel passed; floor tier tipe `high` exact-duplicate tetap DB-gated (`validate_deterministic`).
- Skor terkuantisasi (clump 35/48) membuat ambang hanya dapat diletakkan di celah tersedia; granularitas komponen skor adalah kandidat perbaikan berikutnya.
- Semua label sintetis; bukan validasi BPJS.
