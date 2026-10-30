# Cek kelayakan — apakah sampel BPJS cukup untuk profil per-faskes (C1)?

**Status:** hasil ukur • **Dibuat:** 2026-10-26 • **Alat:** `scripts/bpjs/dump_labels.py` (label + dtype semua kolom, tanpa isi baris)

## 1. Temuan

Kedua file level-klaim **tidak menyimpan identitas faskes/dokter**:

- **FKTP** (`202402_fktpkapitasi`): prov/kab/kepemilikan/jenis/tipe/tingkat/poli (kode), diagnosis, destinasi rujukan (FKP16–21), jenis kunjungan (FKP22), PSTV01/02, bobot. **Tidak ada kode faskes atau dokter.**
- **FKRTL** (`202403_fkrtl`): sama polanya — prov/kab/kepemilikan/jenis/tipe (FKL05–FKL10), diagnosis/INACBG/komponen/biaya, rujukan asal (FKP02), PSTV01/02. **Tidak ada kode faskes atau dokter.**

Artinya: **profil per-faskes (roadmap C1) tidak bisa dieksekusi dari sampel ini** — hanya stratum-level (prov × tipe × kepemilikan × kelas). Ini memenuhi aturan admisi A1 (AD1): atribut *facility identity* punya sumber = hanya jalur payload E-Klaim riil, bukan sampel BPJS.

## 2. Konsekuensi & tindak lanjut

1. C1 (profil provider) **ditunda ke jalur A1 payload** — ID faskes RS/node E-Klaim selalu ada di system riil; kapan file riil per di aduan, namun demikian hal itu simpanan JSON.
2. Analisis perilaku yang tetap bisa berjalan dari sampel (Langkah 8): cadence antara-peserta, gap kunjungan, switch stratum (prov × tipe), rasio rujukan (FKP02 ↔ FKP02), casemix per stratum.
3. Laporan ini mengunci ekspektasi: jangan membawakan janji "profil per RS" srulowe SK anti defakto; semua pembacaan berbasis sampel harus stratum-level.

## 3. Kolom yang punya nilai jelajah lanjutan

| Kolom | Isi | Potensi |
|---|---|---|
| `FKP02` (FKRTL) | No Asal Rujukan = ID kunjungan FKTP | penutupan rujukan FKTP→FKRTL (relational) |
| `FKP22` | Jenis kunjungan FKTP | mix kunjungan biasa vs kontrol |
| `FKP16–21` | destinasi rujukan (prov/jenis/tipe) | pola rujuk lintas stratum |
