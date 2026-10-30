# Profil perilaku peserta — sampel Reguler BPJS (Langkah 8)

**Status:** hasil ukur • **Dibuat:** 2026-10-26 • **Skrip:** `scripts/bpjs/profile_behavioral.py` • **Artefak:** `backend/app/data/analysis/profile_behavioral.json` (ter-ignasi, tanpa PII)

Pengukuran agregat lintas-jalur dari FKTP (4.073.388 kunjungan) + FKRTL (1.699.219 paket). Semua identifier di-hash crc32; tidak ada isi baris yang disimpan. Verdict identitas faskes lihat `BPJS_FASKES_ID_CHECK.md` (tidak ada ID faskes → analisis stratum-level saja).

## 1. Ringkasan angka

| Metrik | FKTP | FKRTL |
|---|---|---|
| Kunjungan | 4.073.388 | 1.699.219 |
| Pasien unik | 849.817 | 306.710 |
| Kunjungan/pasien p50 · p90 · p99 · max | 3 · 11 · 28 · 227 | 2 · 13 · 47 · 214 |
| Pasien dengan ≥2 kunjungan | 71,53% | 67,52% |
| Gap antar-kunjungan p10 · p50 · p90 · p99 (hari) | 2 · **24** · 93 · 222 | 2 · **8** · 35 · 176 |

Distribusi gap (bucket hari, % dari selisih):

| Bucket | FKTP | FKRTL |
|---|---|---|
| 0 (hari sama) | 3,32 | 0,35 |
| 1–3 | 11,08 | 20,16 |
| 4–14 | 23,24 | 45,66 |
| 15–30 | 22,77 | 15,39 |
| 31–60 | 20,68 | 13,38 |
| >60 | 18,91 | 5,07 |

**Bacaan:** kunjungan FKRTL tersangkut rapat (p50 8 hari, ~66% berjarak ≤14 hari — pola rujuk→kontrol), sedangkan FKTP tersebar lebar (p50 24 hari). Pengulangan FKRTL 1–3 hari itu **lumrah (20,16%)** — patokan "mengulang dekat = mencurigakan" era-sintetis pasti tidak akurat bila dipakai mentah.

## 2. Catatan hemodialisis (Q-5-44-0)

| Metrik | Nilai |
|---|---|
| Paket FKRTL | 800.705 = **47,12%** FKRTL |
| Pasien unik | 179.592 |
| Kunjungan/pasien p50 · p90 · p99 · max | **2** · 11 · 26 · 101 |
| Gap p10 · p50 · p90 · p99 (hari, kondisional ≤60) | 5 · **20** · 35 · 56 |
| Bucket 1–3 / 4–14 / 15–30 / 31–60 | 6,94 / 36,64 / 27,33 / 29,07 % |
| **Share gap 12–16 hari** (asumsi dwi-mingguan klasik) | **hanya 13,84%** |

Gap >60 hari dibuang (~7% dari gap potensial) → persentase kondisional. **Temuan penting:** pola 14-hari-presisi hanya menjelaskan ~14% jarak—isinya nyata p50 ≈ 20 hari. Jangan hardcode kelipatan 14 hari; kalibrasi ragam per stratum (p50/p90) adalah jalan yang benar untuk pilarnya relasional.

## 3. Penutupan rujukan (FKP02)

| Metrik | Nilai |
|---|---|
| Baris FKRTL dengan asal-rujukan | 1.001.914 (58,96%) |
| Origin unik | 345.028 |
| Origin ditemukan di FKTP | **100,0%** (integritas sempurna) |
| Share FKTP yang dipakai sebagai rujukan | 8,47% |

**Hari-sama FKTP→FKRTL dengan pasien yang sama:** 129.964 (7,65% FKRTL) — rujuk-dan-tindak-hari-sama itu pola normal, bukan anomali; baseline relasional harus menampungnya.

## 4. Switch stratum FKTP (aproksimasi multi-faskes)

Pasien yang mengunjungi >1 kombinasi (provinsi × tipe faskes) selama sampel: **8,71%**. Karena tidak ada ID faskes (lihat `BPJS_FASKES_ID_CHECK.md`), ini batas bawah kasar-ish, bukan ukuran multi-faskes sejati.

## 5. Implikasi desain basis-relasi (20 pts)

1. **Semua threshold relasional kini harus parametrik per-stratum** dengan kalibrasi dari tabel ini pada gate A3 pasca-demo (repeat window 46–60 d era-sintetis terbukti tidak berlaku dua arah: FKRTL nyata padat di ≤14 d, dialisis tersebar 4–60 d).
2. Baseline per stratum yang usulan: p50/p90 gap FKRTL & gap-dialisis dari tabel ini sebagai soft-floor/per-band; sinyal yang "mencurigakan" didefinisikan relatif ke baseline, bukan konstanta absolut.
3. Rujukan 100% terkunci-in ↔ FKTP → engine relasional boleh mengandalkan pasangan yang diberi payload; pola hari-sama 7,65% jadi baseline normal.

## 6. Keterbatasan & rule data

- **Jendela sampel per pasien tidak penuh** (p50 dialisis = 2 paket): gap hanya dihitung antar dua kunjungan yang keduanya tertangkap sampel → tendensi memotong gap panjang; angka AWS-p50 lebih kecil dari kondisi-riil tahun-penuh. Gunakan secara relatif, bukan absolut.
- Semua agregat, tanpa PII; identifier crc32 (kemungkinan tabrakan <0,1% — cukup untuk pembagian share).
- `jenis kunjungan` FKTP: kode 1 = 2.596.846 (63,8%), kode 2 = 1.476.542 (36,2%); semantik kode tidak diverifikasi dari kamus — hanya distribusi yang dilaporkan.
