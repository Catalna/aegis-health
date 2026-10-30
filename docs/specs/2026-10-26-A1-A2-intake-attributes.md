# Spesifikasi A1/A2 — skema atribut intake & adapter masuk (target)

**Status:** target (arahan desain; integrasi runtime pasca-1-Nov) • **Dibuat:** 2026-10-26 • Merujuk: roadmap `2026-10-25-post-model-roadmap-design.md` §A.

## 1. Prinsip (terkunci dari arahan pemilik produk)

1. **AEGIS-Health bukan sistem input.** RS tetap memasukkan klaim lewat E-Klaim sebagaimana adanya — TIDAK ada formulir/isian baru untuk RS.
2. E-Jak bekerja sebagai lapisan **baca + perkaya**: memperkaya klaim yang masuk dengan atribut konteks via tiga jalur:
   - **J1 — Payload**: diambil langsung dari isi klaim E-Klaim (file export / record) yang sudah ada.
   - **J2 — Lookup**: master data yang AEGIS-Health ambil/pegang (identitas faskes, tarif regional, segmen peserta via API BPJS bila tersedia).
   - **J3 — Derivation**: diturunkan secara deterministik dari kolom payload lain (umur dari tanggal lahir, LOS dari tanggal masuk/keluar, severitas dari digit-4 INACBG, ratio vs peer baseline).
3. Format export E-Klaim yang riil **belum pernah kami lihat** — daftar kolom lengkapnya masih belum dikonfirmasi. Karena itu A2 dirancang tipis (mapping adapter), dan pemetaan final **dikunci begitu satu file export E-Klaim riil diperoleh**; sampai saat itu semua nama kolom payload pada tabel ini adalah ekspektasi, bukan kesepakatan.

## 2. Proses admisi atribut (aturan lalu-lalang atribut baru)

Sebuah atribut boleh masuk ke skema *context* jika & hanya jika memenuhi MINIMUM tiga kriteria:

| # | Kriteria | Ambang |
|---|---|---|
| AD1 | Sumber konkret dari J1/J2/J3 terdokumentasi | wajib |
| AD2 | Siapa mengisinya jelas (RS via payload, atau AEGIS-Health otomatis) | wajib — AEGIS-Health TIDAK pernah meminta isi manual dari RS |
| AD3 | Cakupan ≥ 90% pada sampel riil batch pertama (atribut inti) / ≥ 70% (atribut opsional, berpasangan dengan indikator tersedia) | terukur |

Atribut yang hanya memenuhi sebagian = **gap terdeklarasi** (dicatat di sini + di `MODELS.md`/`DECISIONS.md`), tidak boleh tiba-tiba diisikan di skoring.

## 3. Tabel atribut inti target (A1)

| Atribut | Jalur | Siapa mengisi | Ekspektasi cakupan | Status |
|---|---|---|---|---|
| `inacbg_code` + digit severitas (digit-4) | J1 payload | RS (melalui E-Klaim); severitas dari derivation digit-4 | ~100% (klaim final selalu ber-kode DRG) | siap desain; cakupan dicek saat file riil |
| `hospital_region` (prov / grup tarif regional 1–5) | J2 lookup (master faskes; kode grup 1–5 juga bisa dari tabel tarif) | AEGIS-Health otomatis | ~100% (identitas faskes selalu ada di export) | siap desain |
| `facility_type` (tipe faskes) | J2 lookup master faskes | AEGIS-Health otomatis | ~100% | siap desain |
| `class_of_care` (kelas rawat 1/2/3) | J1 payload (klaim mulai kolom kelas) atau J2 (kelas faskes sebagai dekat) | RS via payload / AEGIS-Health fallback | tinggi; persisnya diukur dari file riil | siap desain |
| `age_years` | J3 derivation dari tanggal lahir (payload) − tanggal layanan | AEGIS-Health otomatis | ~100% bila tgl lahir terisi (biasanya di berkas SEP/klaim) | siap desain |
| `sex` | J1 payload | RS via payload | tinggi (didukung di kepesertaan BPJS) | siap desain |
| `los_days` | J3 derivation tanggal masuk−keluar | AEGIS-Health otomatis | ~100% untuk rawat inap; 0 untuk day-care | siap desain |
| `n_diagnosis`, `n_procedures`, daftar ICD | J1 payload | RS via payload | tinggi | siap desain |
| `regional_tariff_group` (1–5, konteks, bukan rupiah) | J2 lookup | AEGIS-Health otomatis | ~100% | siap desain |
| `icu_ventilator_days` / biaya icu | J1 payload | RS via payload E-Klaim (bidang icu/vent. pada klaim INACBG) | **tidak diketahui** — TIDAK dijamin ada di export | **gap; diukur dari file riil pertama**, jangan diandalkan |
| `segment` peserta (PBI dll) & kelas kepesertaan | J2 lookup API BPJS (VClaim peserta) | AEGIS-Health otomatis | bergantung ketersediaan API di jaringan RS; offline demo → tidak | opsi, tidak dijamin |
| `peer_ratio` (tagih vs median peer real) | J3 derivation vs tabel `peer_baseline_reguler*` | AEGIS-Health otomatis | ~100% (fallback nasional n≥30 menutup 99,8%) | siap desain (penerapan pasca-gate) |

Cakupan dan ramping dijalankan di batch riil pertama: laporan cakupan aktual per atribut (≥90% inti; else status tetap "gap").

## 4. Desain A2 — adapter masuk (tipis)

- Adapter = penerjemah **satu arah** file masuk (CSV/E-Klaim export/kerangka FHIR kelak) → struktur klaim internal (pydantic model / dict J1) yang dikenali E-Jak; TIDAK menulis ke proses RS apa pun.
- Pemetaan disimpan sebagai tabel konfigurasi (`mapping_eclaim.yaml`-style) BUKAN kode hard-coded, sehingga variasi format per RS tak memerlukan redesign.
- Yang TIDAK ada di export: diisi jalur J2/J3; bila keduanya tak mampu → kolom `null` + flag provenance `unavailable` (silang dengan konteks B1: label provenance per nilai).
- Uji penerimaan adapter: (a) satu file riil diproses utuh tanpa baris gagal; (b) cakupan atribut dihitung otomatis — laporan AD3; (c) jejak: baris gagal/list kolom mapping disalurkan ke log, bukan GUI.
- **Eksplisit jujur:** daftar kolom riil E-Klaim export dipetakan tegas saat file diperoleh. Blok tabel §3 kolom "ekspektasi cakupan" adalah hipotesis yang akan diperiksa, bukan keputusan.

## 5. Yang eksplisit tidak dilakukan

- Tidak ada supervised fraud training (tidak ada label di data apa pun) — tetap benchmark + sinyal.
- Tidak ada penulisan ke sistem RS / pengubahan nilai klaim — E-Jak hanya membaca dan memperkaya.
- Tidak ada penambahan dependensi/teknologi baru (aturan freeze: hanya P0 sampai 1 Nov).
