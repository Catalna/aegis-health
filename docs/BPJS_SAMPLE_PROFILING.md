# Profil Data Sampel BPJS 2025 — Paket Reguler

**Status:** hasil ukur dari sampel (bukan target/dugaan) • **Dibuat:** 2026-10-26 • **Skrip:** `scripts/bpjs/profile_reguler.py`

**Sumber:** `backend/app/data/2025/Data Sampel Reguler Edisi 2025/data/` (ter-ignasi — data riil tidak pernah masuk git).
**Cara jalankan ulang:** `venv\Scripts\python.exe scripts\bpjs\profile_reguler.py` → artefak tulis ke `backend/app/data/analysis/profile_reguler.json` (juga ter-ignasi).
**Prinsip:** membaca per-chunk, hanya kolom yang perlu; **output hanya agregat pola, tanpa nomor peserta/identifier apa pun.**

## 1. Inventaris paket Reguler

| File | Baris | Profil lengkap di langkah ini |
|---|---:|---|
| `2015202401_kepesertaan` | 2.590.751 | ✔ |
| `202402_fktpkapitasi` | 4.073.388 | ✔ |
| `202403_fkrtl` | 1.699.219 | ✔ |
| `202404_nonkapitasi` | 258.201 | ✔ |
| `202406_diagnosissekunder` | 1.967.670 | ✖ (dipakai nanti: jumlah dx sekunder per klaim via join `FKL02`) |

Paket tematik (DM, KIA Ibu/Anak, Kesehatan Jiwa, TB, COVID) + kamus ICD-10 belum diprofil — menyusul bila dibutuhkan untuk benchmark spesifik.

## 2. FKRTL (rawat lanjut/inap) — turunan utama benchmark biaya

| Metrik | Hasil |
|---|---|
| Provinsi | 38 kode (atas: `33` 281.873; `32` 249.554; `35` 224.825; penamaan mengikuti kode provinsi BPS) |
| Tipe faskes (kode) | `7` 536.307; `3` 311.956; `2` 259.425; `6` 135.968; `8` 112.473; `1` 92.364 |
| Kelas rawat | 1: 2,5% • 2: 2,7% • **3: 94,8%** |
| Severitas (digit-4 INACBG) | 1: **88,5%** • 2: 9,0% • 3: 1,9% • 4: 0,6% |
| Grup INACBG (`FKL20`) | 23 grup terisi utama (atas `17` 930.948; `13` 159.518; `23` 150.604) |
| **Kode INACBG utama (`FKL19`)** | **899 kode**; teratas `Q-5-44-0` (hemodialisis) **800.705 = 47,1%**; lanjut: `M-3-16-0` 139.605; `N-3-15-0` 94.903 |
| LOS (`FKL04 − FKL03`) | **p50 = 0, p90 = 1, p99 = 6 hari** → >50% kunjungan day-care/rawat jalan; rawat inap >6 hari <1% |
| Jenis prosedur (`FKL30`) | kosong 41,7%; berisi format `"kode - deskripsi"` (hemodialysis paling sering di antara yang isi) |
| Komponen (≠ `NONE`) | **SA sub-akut: 0%** • SP prosedur: 0,52% • SI investigasi: 0,11% • SD obat: 0,09% |
| Biaya | Tagih = Rp 1.536,0 miliar; Verifikasi = Rp 1.533,9 miliar; selisih Rp 2,07 miliar (**0,13% nilai**) |
| Tagih == Verifikasi | **1.697.588 dari 1.699.219 = 99,90%**; verifikasi kosong hanya 5 baris |

**Temuan penting verifikasi:** semua baris yang berbeda **100% arah tagih > verifikasi** (potongan verifikator). Dari sampel 200 rb baris: 141 baris beda, median gap ±Rp 300 rb. Sampel ini mayoritas klaim *diterima penuh* → sangat bagus untuk melatih benchmark "biaya wajar" (target = `FKL48`), sementara baris ber-potongan (0,10%) adalah populasi sinyal pengurangan yang alami.

**Temuan penting komposisi:** hampir separuh baris adalah `Q-5-44-0` (hemodialisis kronik, frekuensi tinggi & pasien berulang). Benchmark/novelty-score **wajib condition on kode INACBG** (dan idealnya rasio per pasien) — kalau tidak, semua klaim dialysis akan tampak "anomali" hanya karena harga terapinya tertinggi.

## 3. FKTP kapitasi (akses primer)

| Metrik | Hasil |
|---|---|
| Kunjungan | 4.073.388 baris; 38 provinsi (atas: `33` 615.655; `32` 573.040; `35` 526.003) |
| Jenis faskes (kode) | `1` 2.385.732; `2` 1.158.411; `3` 457.171; `5` 34.739; `4` 25.857; `7` 11.478 |
| Tipe faskes (kode) | `3` 1.388.255; `4` 997.477; `1` 917.509; `2` 457.171; `5` 238.520; `8` 34.739 |
| Diagnosa 3-digit (`FKP14A`) | **1.800 kode distinct**; kosong 36,3%; teratas `J06` 235.149; `J00` 161.065; `I10` 158.160; `E11` 127.043; `K30` 101.629 |

## 4. Non-kapitasi

258.201 baris; 38 prov; tipe terbanyak `8` (151.271). **Tagih == Verifikasi 100,0%** (258.201/258.198 positif; 3 baris tagih ≤0).

## 5. Kepesertaan (profil demografi peserta)

| Metrik | Hasil |
|---|---|
| Peserta | 2.590.751; provinsi 38 + beberapa baris tanpa kode (teratas `32` 334.775; `33` 319.803; `35` 283.801) |
| Kelas | 1: 19,2% • 2: 21,9% • **3: 58,8%** • `9`: 0,07% (keluar/meninggal?) |
| Segmen (kode) | `5` 825.994; `2` 796.022; `4` 527.977; `3` 326.646; `1` 114.035; `9` 77 |
| Umur (dari tahun lahir vs 2024) | **p50 = 35, p90 = 65** — distribusi dewasa; cohort `2000` terbanyak (peserta ~baru 24 th) |

## 6. Implikasi ke rencana (benchmark → retraining)

1. **Peer baseline (Langkah 2)**: tabel median `FKL48` per (provinsi × tipe faskes × INACBG `FKL19` × severitas `FKL23`) wajib — sampel dominasi hemodialisis membuat baseline agregat tidak berguna. Kelas rawat dapat ditambah sebagai dimensi opsional (94,8% kelas 3 → efektif 2 dimensi).
2. **Benchmark regressor (Langkah 4)**: subset "wajar" `FKL47 == FKL48` mencakup 99,9% baris → cukup besar; `FKL31` = kode grup tarif regional (1–5, **bukan** rupiah) → jangan dijadikan fitur nominal; nominal harga hanya dari `FKL47/48`.
3. **ICU/ventilator: gap resmi** — kolom komponen `SA` praktis tak pernah terisi (0%) pada paket Reguler; sesuai roadmap, ICU tetap tidak tersedia dari data ini (tunggu jalur A1: payload E-Klaim RS).
4. **Umur & LOS & prov & kelas & severitas tersedia** ✓ — menyediakan ~7–8 dari 9 masukan hilang trainer v2; cek `docs/MODELS.md`.
5. **Kualitas data**: baris yang kehilangan verifikasi 5; FKTP dx kosong 36,3% (diduga kunjungan tanpa diagnosis tercatat); kode prov/tipe/segmen masih numerik — pemetaan label mengikuti legenda resmi BPJS yang tersimpan di luar sampel, ditulis apa adanya (kode) sampai legenda dikonfirmasi.

## 7. Catatan teknis skrip

- Tanggal Stata sudah `datetime64[ns]` langsung — parser bisa lurus (perbaikan setelah run pertama yang salah menafsirkan nanosekon sebagai elapsed-days).
- Komponen `FKL33/35/41/44` berisi literal `"NONE"` — kehadiran komponen dihitung sebagai nilai non-NONE, bukan non-null.
- Tidak ada perluasan bobot sampel (PSTV15 tidak dibesar); semua angka = hitung mentah kejadian pada sampel.
