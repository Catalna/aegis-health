# Laporan kalibrasi generator + kandidat klasifier v3 (Langkah 10–11)

**Status:** hasil ukur • **Dibuat:** 2026-10-26 • **Seed:** 42 (pasang tunggal, pra-gate) • **Artefak:** `backend/models_trained/synthetic_v2_v3/` + dataset `data/synthetic_v2_calibrated/` (keduanya gitignored)

## 1. Apa yang dikalibrasi (Langkah 10)

Jalur opsi `--calibrated` pada generator (default **v2.4 murni tidak berubah** — kontrak & dataset lama tetap):

| Sisi | Kalibrasi ke | Sumber |
|---|---|---|
| Mekanisme `repeat_billing` | bucket gap FKRTL L8: days_1_3 (20,2%) / days_4_14 (45,7%) / days_15_30 (15,4%) / days_31_60 (13,4%), desain out-of-family val/test dipertahankan | `profile_behavioral.json` |
| Cadence hard-negative (chronic repeat) | sampel dari bucket dialisis L8 (1–3: 6,9% / 4–14: 36,6% / 15–30: 27,3% / 31–60: 29,1%) | `profile_behavioral.json` |
| Komponen derau biaya pasien normal | campuran terkunci-tarif 47% (±0,3%) + invers-CDF kuantil L9 non-dialisis (p50=1,00 · p90=1,05 · p99=1,468) menggantikan lognormal σ=0,12 | `peer_signal_scan.json` |

Dataset hasil: **257.100 klaim**, validasi `valid`, versi `synthetic-v2.4.0-calibrated`, SHA-256 `dc4b3ecc…`.

**Batas jujur surrogate:** rasio `cost/regional_base_rate` sintetis tetap didominasi sebaran struktural grouper (severity × faskes) — di data riil, efek itu ternetralkan median peer per sel. Yang dikalibrasi adalah **bentuk derau + cadence**, bukan universe kode.

## 2. Hasil A/B kandidat (uji seed yang sama, split keseluruhan 50.000)

| Metrik | Kandidat v2.4 (dunia-sintetis-lama) | **Kandidat v3 (terkalibrasi)** |
|---|---|---|
| Test AP | 0.7259 | **0.6609** (CI95 grup [0.635, 0.683]) |
| Validation AP | ~0.73 | 0.6399 (depth 5, spw 1.0, iter 399) |
| Baseline aturan (logistic rule flags) | ~0.15 | 0.154 |
| Baseline deviasi-benchmark absolut | — | 0.149 |
| Random | 0.03 | 0.030 |

**Kandidat tetap ≥4× baseline aturan di kedua dunia.**

Fitur penting (gain) v3: `exact_copy_group_size` (220) ≫ `surgical_indicator` (81) > `unsupported_procedure_8151_flag` (80) > `cost_to_sev_factor_ratio` (74) > `grouper_severity_gap` (59) … `min_same_patient_gap_days` (31).

## 3. Membaca turunnya AP dengan jujur

AP 0.7259 → 0.6609 **karena dunia latihan-ujinya kini mendekati real**, bukan degradasi model (model & kontrak fitur identik):

1. **Pilar relasional gratis-beruntung jadi riil.** Di v2.4, repeat/kloning mudah dipisah karena gap legit terutama 30–60 hari. L12 membuktikan realita sebaliknya (44,6% pasangan non-dialisis ≤7 hari) → kandidat v3 harus belajar membedakan di dunia 44,6%-legit-yang-tumpang — sinyal jauh lebih informatif untuk transfer gate A3.
2. **Inti derau dua arah mengetat** → `inflated_bill` kini bergeser di atas ekor lebih rapat; separabilitas turun di slice biaya-murni tapi presisi-ekor menaik.
3. **Fitur identitas tetap raja**: `exact_copy_group_size` menyendiri di atas — pesan konsisten dengan L12: jalur **identitas** (kode×faskes×tanggal) > jalur jendela-tanggal murni. Ini menyusun kalibrasi pilar relasional: baseline relatif per strata, bukan threshold absolut.
4. OOD stress (cloning): AP 0.065 — hard-negative design tetap membatasi slice ini (dokumentasi lama, tidak berubah).

## 4. Status portofolio kandidat (pra-gate)

| Kandidat | Dunia latihan | Titik primer | Siap diuji gate A3 |
|---|---|---|---|
| Benchmark biaya C | riil (retrain) | MAPE 8,59% … | ✅ artefak ada |
| Klasifier v2.4 | sintetis murni | test AP 0.7259 | ✅ |
| **Klasifier v3** | **sintetis terkalibrasi L8/L9** | **test AP 0.6609 (CI [0.635–0.683])** | ✅ |

Gate A3 (pasca-1-Nov, `MODELS.md §2.6`, evaluasi per-strata wajib) memilih dari portofolio ini — tidak ada promosi runtime sekarang; freeze demo tetap utuh.

## 5. Rekomendasi

1. Masukkan **kedua** kandidat klasifier ke daftar evaluasi gate (v3 sebagai calon utama pasal dunia-latihan yang lebih real; v2.4 sebagai pembanding).
2. Kalibrasi pilar relasional di gate pakai tabel L12 (baseline relatif per strata) + prioritas fitur identitas.
3. Pasca-payload: ulang kalibrasi penuh (ICU/vent + ID faskes + label) — itulah penguat segera berikutnya.
