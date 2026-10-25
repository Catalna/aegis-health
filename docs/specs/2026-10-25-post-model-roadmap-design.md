# Post-model development roadmap — J-ARI

> **Synthetic demonstrator only — not BPJS performance validation.**
> Semua angka di dokumen ini dikutip dari laporan repo yang ada; semua rencana berstatus **target**, bukan hasil (disiplin §10 Strategic Alignment).

Tanggal: 2026-10-25
Status: spesifikasi arahan pengembangan pasca-model (belum ada implementasi).
Dokumen acuan: `docs/plans/J-ARI-Strategic-Alignment-Healthkathon-2026.md` (Fase 4, §8, §9, §10, §13), `docs/MODELS.md`, `docs/RUNTIME_EVALUATION.md`, `docs/TIER_CALIBRATION.md`, `docs/DECISIONS.md`.

---

## 1. Premis dan prinsip kerja

1. Benchmark biaya runtime dan ambang tier sudah stabil dan terdokumentasi. Titik-terbesar pengembangan berpindah **dari model ke: akses data konteks, umpan balik verifier, dan tata kelola**.
2. **Frozen demo**: sampai video demo 1 Nov 2026 beres, item di dokumen ini tidak boleh menyentuh kode scoring (`risk_engine.py`, `financial_engine.py`), angka demo (220 klaim), atau seed — kecuali bug P0.
3. Promosi model/konfigurasi apapun ke runtime hanya lewat **gerbang ablation** (kandidat vs runtime pada slice identik, metrik top-K, disebut di §10 Strategic Alignment) dan **prosedur promosi `MODELS.md`**.
4. Setiap hasil baru wajib menyebut: versi model, versi dataset, dan sumber angka. Klaim yang belum diuji tetap berlabel *target*.
5. Non-goals (tidak boleh diklaim oleh item apapun): bukti fraud otomatis, penghematan nominal tertentu, validasi kinerja BPJS, integrasi SATUSEHAT live, kesiapan produksi tanpa pilot.

## 2. Fakta dasar (snapshot 2026-10-25 — semuanya "hasil")

| Fakta | Nilai | Sumber |
|---|---|---|
| Runtime ranking AP | 0,5964 (P@5% 0,829 · R@30% 0,351) | `RUNTIME_EVALUATION.md` (slice 700, prevalensi 50%) |
| Kandidat classifier 28 fitur | AP 0,9158 pada slice identik | `RUNTIME_EVALUATION.md` |
| Regressor biaya v2 | MAPE 12,83% · R² 0,8640 · coverage 90,18% | `MODELS.md` §Okt-2026 |
| Ambang tier | medium ≥ 48,7 · high ≥ 55,0 (kalibrasi validasi, tes sekali) | `TIER_CALIBRATION.md` |
| Latency deterministik | p50 75 ms · p95 845 ms (e2e dengan LLM ~7,3 s) | `RUNTIME_EVALUATION.md` |
| Gap schema | 9 field trainer v2 (`facility_type/class`, `region`, ICU, umur, dst.) tidak ada di `ClaimInput` | `MODELS.md` (keputusan "no file swap") |
| Sisi blind-spot benchmark | tidak ada fitur identitas RS/regionalitas/periode → provider-blind | `feature_engineering.py` (15 fitur klaim saja) |

Implikasi: kandidat yang lebih kuat **sudah ada tapi ter-block schema**; kerja data-akses adalah leverage tertinggi.

## 3. Item pengembangan (status: target)

Bobot kerja: S = 1–2 hari, M = 3–5 hari, L = lebih dari satu minggu (pengembangan penuh, bukan spike).

### A. Akses data & promosi model (paling strategis)

| ID | Item | Deliverable | Definition of done | Bobot |
|---|---|---|---|---|
| A1 | Perluasan canonical claim schema: field konteks fasilitas (tipe/kelas, regionalitas, periode, indikator ICU, umur peserta) | Draft skema + perubahan `ClaimInput` + migrasi (opset terkontrol) | Field baru dinilai lengkap di `ClaimInput` dan generator v2; demo matrix lama tak putus; test suite hijau | M |
| A2 | Adapter upstream: CSV demo dulu, kerangka E-Klaim/FHIR | Adapter CSV berfungsi + dokumen mapping field (tabel pemetaan), tanpa integrasi live | Klaim dari CSV demo masuk pipeline identik dengan POST; mapping table direview | M |
| A3 | Gerbang ablation promosi kandidat | Laporan ablation 5-konfigurasi (financial → +klinis → +relasional → +IF → full) + keputusan promosi tertulis | Diproses mengikuti prosedur `MODELS.md`; hasil disebut dengan CI/dataset besar; IF hanya dipertahankan bila top-K membuktikan nilai | L |

### B. Umpan balik verifier & transparansi (murah, nilai juri tinggi)

| ID | Item | Deliverable | Definition of done | Bobot |
|---|---|---|---|---|
| B1 | Provenance UI: label "aturan domain-backed vs sinyal prototype" per bukti | Label pada kartu evidence (Investigation/Assessment) | Setiap item bukti membawa asal-aturanya; konsisten dengan antar-frontend dev (dashboard milik `20b38d2`) | S |
| B2 | Feedback loop verifier: laporan konflik skor-vs-keputusan mingguan | Script laporan dari `human_decisions` + `audit_logs` | Satu laporan contoh dihasilkan dari DB demo; definisi sinyal tertulis | S–M |

### C. Profil risiko faskes

| ID | Item | Deliverable | Definition of done | Bobot |
|---|---|---|---|---|
| C1 | Provider risk profiling + normalisasi peer | Agregat risiko per fasilitas dari sinyal yang ada (grafik, repeat/clone density, deviasi) dengan normalisasi ukuran peer | "Volume tinggi ≠ mencurigakan" dinormalisasi dan terdokumentasi; laporan contoh dari demo DB | M |

### D. Monitoring, tata kelola, alur klarifikasi

| ID | Item | Deliverable | Definition of done | Bobot |
|---|---|---|---|---|
| D1 | Model monitoring ringan: distribusi skor, fallback rate, missing-feature rate, versi model/dataset | Dashboard/endpoint monitoring mingguan | Metrik muncul dari data runtime; fallback rate terlaporkan (`zscore_peer_fallback` terhitung) | S–M |
| D2 | Kesiapan pilot: RBAC + enkripsi transit/at-rest (doc-level; implementasi lanjutan) | Dokumen keamanan + rencana RBAC verifier/auditor | Bukan untuk demo; masuk proposal sebagai pilot readiness | S |
| D3 | Jalur klarifikasi terstruktur | "Request Clarification" menghasilkan draft pertanyaan + tautan bukti | Draf dapat dikirim/direview; menutup ruang loop verifier–faskes | M |

### E. Bukti dampak

| ID | Item | Deliverable | Definition of done | Bobot |
|---|---|---|---|---|
| E1 | Simulasi waktu review sebelum/sesudah (3–5 tester × 10 klaim) | Satu angka usability + protokol ujian | Protokol tertulis; hasil dilaporkan apa adanya sebagai target→hasil; disclaimer sintetis menyertai | S |

## 4. Fase dan urutan

| Fase | Item | Rasional |
|---|---|---|
| Fase 1 — pasca-video 1 Nov | B1, D1, E1 | Murah, memperkuat proposal, menyentuh nol kode scoring |
| Fase 2 — unlock model terbaik | A1, A2, A3 | Kandidat AP 0,9158 hanya bisa masuk runtime lewat schema+adapter+gerbang ablation |
| Fase 3 — dampak & tata kelola | B2, C1, D2, D3 | Butuh pola pemakaian/data dan koordinasi; align Fase 4 Strategic Alignment |

Urutan dalam Fase 2: A1 → A2 → A3 (gerbang tidak bisa jalan sebelum data konteks masuk).

## 5. Definition of done dokumen ini

- Setiap fase menyelesaikan definition of done per item (Tabel 3).
- Setiap laporan hasil baru menyertai disclaimer sintetis + sumber angka + versi model/dataset.
- Tidak ada item yang menimpa runtime tanpa gerbang A3.

## 6. Pertanyaan terbuka (perlu konfirmasi pemilik produk)

1. Prioritas Fase 2 vs Fase 3 jika waktu sempit setelah 1 Nov?
2. Format adapter yang didukung lebih dulu: CSV demo, E-Klaim, atau kerangka FHIR?
3. Penempatan label provenance (B1) di halaman dari frontend dev teman — koordinasi diperlukan.
4. E1: siapa tester (3–5 orang) dan apakah pakai DB demo yang sama?

## 7. Larangan sementara (sampai video 1 Nov)

Menyunting `risk_engine.py`, `financial_engine.py`, `demo_seed.py`/`demo_reset.py`, angka tier/skor, atau halaman PAGE demo; mengganti model/apar; menambah dependensi baru tanpa alasan P0.
