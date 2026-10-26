# Peer baseline biaya — dari sampel Reguler BPJS 2025

**Status:** hasil ukur dari sampel (bukan target) • **Dibuat:** 2026-10-26 • **Skrip:** `scripts/bpjs/extract_peer_baseline.py` • **Artefak:** `backend/app/data/analysis/peer_baseline_reguler_{main,fallback,kelas}.csv` (ter-ignasi)

## 1. Metode

- Populasi: FKRTL `202403_fkrtl.dta`, **subset wajar** = `FKL47 == FKL48` & `FKL48 > 0` → 1.697.588 baris (99,90% dari 1.699.219). Tidak ada identifier di artefak — hanya kunci kode + statistik.
- Statistik per sel: `n`, `mean`, `q25`, `median`, `q75`, `p90` dari nilai verifikasi `FKL48`.
- Tiga granularitas:
  | Tabel | Kunci | Sel | Cakupan (n≥5) |
  |---|---|---:|---:|
  | `main` | prov (`FKL05_NEW`) × tipe faskes (`FKL09`) × INACBG (`FKL19`) × severitas (`FKL23`) | 51.215 | 96,4% baris pada n≥5; 94,0% pada n≥10; 88,6% pada n≥30 |
  | `fallback` | INACBG × severitas (nasional) | 898 | **100,0%** baris (99,8% pada n≥30) |
  | `kelas` | INACBG × severitas × kelas (`FKL13`) | — | efek kelas rawat bila terisi |

- Rantai konsumsi yang direncanakan (target, tidak diintegrasikan sebelum gate): potong utama (min-n 10) → fallback nasional → median global. Ambang & rantai final ditetapkan di gate A3.

## 2. Temuan kunci

1. **Distribusi biaya pada sel dense hampir degenerasi (tarif persis).** Contoh 10 sel terbesar (semua `Q-5-44-0` sev 1):
   | prov | tipe | n | median | q25–q75 |
   |---|---:|---:|---:|---|
   | 33 | 7 | 58.413 | 196.100 | 196.100–196.100 |
   | 32 | 7 | 47.520 | 196.100 | sama |
   | 35 | 7 | 34.627 | 196.100 | sama |
   | 33 | 3 | 19.974 | 186.800 | sama |
   | 51 | 7 | 15.723 | 198.100 | sama |

   Artinya: klaim yang diterima penuh menempel **tepat** pada harga tarif INACBG per (grup tarif regional × tipe × kelas). Benchmark "biaya wajar" di sel-sel ini bukan hasil regresi probabilistik melainkan *tabel tarif implisit*.
2. **Konsekuensi untuk deteksi anomali:** skor menarik bukan pada sel biasa, melainkan pada klaim yang **menyimpang dari tarif petanya** (mis. klaim dialysis yang tagihannya melampaui tarif implisitnya). Regresor (Langkah 4) akan tampak super akurat di sel dense — angka `R²` harus dilaporkan per stratum, tidak hanya global, agar jujur.
3. **Cakupan sangat baik untuk MVP:** fallback nasional menutupi 100% baris wajar (n≥30: 99,8%) — tabel kecil (898 baris) muat di memori runtime dengan mudah; jauh lebih kaya dan realistis dibanding `PEER_BASELINE` sintetis saat ini (dikt kecil).
4. Severitas 1 mendominasi (88,5% baris), sel kontrol di `main` 4.386 (n≥30) mencakup 88,6% baris — granularitas prov×tipe punya data cukup di wilayah urban (`33`, `32`, `35`).

## 3. Cara pemakainya (target E-Jak)

- Per klaim (FKRTL), ambil `peer_median` dari rantai potongan → fitur `peer_ratio = tagih / peer_median` menggantikan sintesis `PEER_BASELINE` di `backend/app/ml/feature_engineering.py`.
- Integrasi runtime + perombakan `MODELS.md` **ditahan sampai setelah video 1 Nov** (freeze berlaku: menyentuh skoring = terlarang); untuk kini hanya artefak + spesifik.
- Penamaan konsumsi CSV oleh skoring baru harus melalui gate A3 (ablation vs runtime aktif).

## 4. Limitasi

- Kode tipe faskes/segmen tetap numerik (legenda resmi ada di luar sampel).
- Sel langka (n < 5, 3,6% baris) ditangani fallback nasional, bukan estimasi khusus.
- Nilai = hasil ukur dari sampel; tanpa pemberatan bobot sampel resmi BPJS.
