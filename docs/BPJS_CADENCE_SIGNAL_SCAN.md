# Scan sinyal cadence per-strata — baseline relasional dari FKRTL riil (Langkah 12)

**Status:** hasil ukur • **Dibuat:** 2026-10-26 • **Skrip:** `scripts/bpjs/scan_cadence_signal.py` • **Artefak:** `backend/app/data/analysis/cadence_signal_scan.json` (ter-ignasi, tanpa PII)

Framing: pra-gate, evaluasi saja. Mengukur **pasangan kunjungan FKRTL berurutan per peserta** (terurut tanggal, 1.699.219 baris → 306.710 pasien → **1.392.509 pasangan**), terstrata menurut komposisi pasangan: dialisis-keduanya / non-dialisis-keduanya / campuran.

## 1. Tabel utama per strata

| Metrik | Dialisis-keduanya | Non-dialisis-keduanya | Campuran |
|---|---|---|---|
| n pasangan (share) | 478.892 (34,39%) | 501.573 (36,02%) | 412.044 (29,59%) |
| Gap p10 · p25 · p50 · p75 · p90 · p99 (hari) | 5 · 7 · **21** · 32 · 37 · 134 | 2 · 3 · **6** · 11 · 31 · 191 | 1 · 4 · **8** · 16 · 35 · 194 |
| Bucket 1–3 | 3,44% | 6,16% | 10,28% |
| Bucket 4–7 | 6,45% | **37,71%** | 17,81% |
| Bucket 8–14 | 19,29% | **24,09%** | 25,80% |
| Bucket 15–30 | 16,49% | 13,27% | 20,73% |
| Bucket 31–60 | **29,26%** | 8,25% | 13,19% |
| Bucket >60 | 25,05% | 9,84% | 11,87% |
| Hari-sama (0) | 0,02% | 0,68% | 0,31% |

## 2. Share kumulatif "near-repeat" per ambang (dari tabel di atas)

| Ambang gap ≤ | Dialisis | Non-dialisis | Campuran |
|---|---|---|---|
| ≤3 hari | ~3,5% | ~6,8% | ~10,6% |
| ≤7 hari | ~9,9% | **~44,6%** | ~28,4% |
| ≤14 hari | ~29,2% | ~68,6% | ~54,2% |
| ≤30 hari | ~45,7% | ~82% | ~75% |

## 3. Bacaan engineer

1. **Repeat ketat itu normal-nya rawat jalan non-dialisis** — 44,6% pasangan real berjarak ≤7 hari (kunjungan kontrol). Aturan era-sintetis "pengulangan ≤30 hari = mencurigakan" akan menandai mayoritas klaim sehat; **window absolut tidak boleh jadi sinyal**.
2. **Dialisis adalah strata paling lambat**: p50 21 hari, mass utama di 31–60, dan 25% pasangan >60 hari (tail penuh; catatan: tabel L8 berkondisional ≤60, tabel ini tanpa pemangkasan) → proposal baseline cadence dialisis pakai p50/p90 = 21/37 hari.
3. **Kombinasi yang benar untuk pilar relasional (kandidat gate A3)**: bukan jendela gap sendirian, tapi `gap strata-baseline × identitas kode × faskes × tanggal` (fitur `copy_group_size`/`exact_copy_group_size` sudah memuat sisi itu); gap dipakai **relatif** — mis. dialisis gap <4 hari (≈3,5% total) = jarang → layak review; ≤14 hari = normal; non-dialisis gap ≥2×p90 (>62 hari) yang justru out-of-pattern.
4. Hari-sama intra-FKRTL <0,7% di semua strata → tanda "klaim ganda hari-sama" tetap bermassa dropdown-relevan kecil tapi real (0,68% non-dialisis ≈ 3.400 klaim).

## 4. Status keterbatasan

- Pasangan dihitung dalam sampel saja (perpasien; jendela sampel tak penuh — p50 dialisis perpeserta L8 = 2 paket).
- Strata pasangan memakai kode INACBG baris (Q-5-44-0); cross-episode medik tak tersedia di sampel.
- Bukan validasi fraud: ini kalibrasi volume/skala, tanpa label.
