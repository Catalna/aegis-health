# Scan karakteristik operasi sinyal deviasi-vs-peer (Langkah 9, pra-gate)

**Status:** hasil ukur • **Dibuat:** 2026-10-26 • **Skrip:** `scripts/bpjs/scan_peer_signal.py` • **Artefak:** `backend/app/data/analysis/peer_signal_scan.json` (ter-ignasi, tanpa PII)

**Framing wajib:** ini **bukan validasi fraud** — data riil tidak punya label fraud. Yang diukur: "kalau threshold X dipakai pada sinyal `biaya/median-peer`, berapa klaim yang akan ditandai dan di sel mana?" Ini masukan penetapan threshold **gate A3** pasca-1-Nov, tanpa mengubah runtime apa pun.

## 1. Cakupan pengukuran

- Baris wajar (`FKL47 = FKL48`): **1.697.588** — 0 baris tanpa sumber benchmark (main n≥10 → fallback n≥10 → global Rp 196.100).
- Rasio r = biaya ÷ median peer sel (prov × tipe × INACBG × sev).

## 2. Sebaran rasio (seluruh wajar)

| Band r | Share |
|---|---|
| <0,5 | 0,13% |
| 0,5–0,9 | 3,35% |
| **0,9–1,1** | **92,00%** |
| 1,1–1,25 | 2,59% |
| 1,25–1,5 | 1,30% |
| 1,5–2,0 | 0,36% |
| ≥2 | 0,27% |

Tarif disiplin luar-biasa: 92% klaim real ±10% dari median peer.

## 3. Per strata

| Band | Dialisis (47,1% FKRTL) | Non-dialisis |
|---|---|---|
| 0,9–1,1 | **99,30%** | 85,50% |
| ≥1,1 | 0,33% | 8,24% |
| ≥1,25 | 0,0%+ | 3,35% |

Dialisis **terkunci-tarif** (99,3% dalam ±10%) — konsisten dengan temuan retraining (`BPJS_RETRAINING_REPORT.md`: R² dialisis 0,102). Implikasi desain: komponen skor deviasi-finansial harus **mengecualikan stratum terkunci-tarif** — kalau tidak, skor di sana hampir selalu nol dan hanya menambah buffer noise.

Kwantil rasio non-dialisis: p50 = 1,000 · p90 = 1,050 · **p99 = 1,468** — distribusi bertumpu di r=1 dengan ekor kecil di atasnya.

## 4. Tabel ukuran antrean verifikasi

| Threshold naik | Klaim ditandai | Share |
|---|---|---|
| ≥1,10 | 76.608 | 4,51% |
| ≥1,25 | 32.714 | **1,93%** |
| ≥1,50 | 10.720 | 0,63% |
| ≥2,00 | 4.712 | 0,28% |

Skala analog: kalau RS RI ukuran ±1.000 klaim FKRTL/bulan, threshold 1,25 → ±19 klaim masuk antrean periksa per bulan — antrean supaya realistis.

## 5. Sel teratas (inacbg × sev, tanda ≥1,25, hanya non-dialisis)

| inacbg × sev | n_flag |
|---|---|
| N-3-15-0 × 1 | 4.610 |
| O-6-10-I × 2 | 3.795 |
| K-4-17-I × 2 | 3.472 |
| A-4-13-I × 2 | 3.230 |
| U-3-16-0 × 1 | 2.276 |
| A-4-14-I × 2 | 2.188 |
| K-4-18-I × 2 | 2.172 |
| J-4-16-I × 2 | 1.735 |
| O-6-13-I × 2 | 1.347 |
| J-4-21-I × 2 | 1.340 |
| U-4-13-I × 2 | 1.161 |
| E-4-10-I × 2 | 988 |
| L-1-40-I × 2 | 926 |
| W-4-16-I × 2 | 790 |
| D-4-13-I × 2 | 708 |

tanda **berkonsentrasi di sel sev-2 bedah kel-4 (suffix -I) dan kel-6 (O-)** — catatan: n_flag per sel juga bisa mencerminkan ukuran populasi sel; rate-per-sel akan dihitung saat evaluasi gate A3.

## 6. Implikasi & langkah lanjut

1. **Penetapan threshold di gate A3** kini berbasis data: 1,10 = volume triage besar; **1,25 = titik operasional** (±2% klaim); 1,50 = fokus 0,6%.
2. Stratum terkunci-tarif (dialisis, sel degenerat) → **kontribusi komponen deviasi di-nol-kan otomatis**; sinyal relevan hanya di sel n≥10 non-degenerat.
3. **Sinyal deviasi-peer nyata hanya punya massa di ekor non-dialisis sev-2** → tuning bobot skor finansial dilakukan saat evaluasi pasca-gate.
4. Data tidak punya label fraud → angka-angka ini dipakai sebagai **kalibrasi volume antrean**, bukan ukuran presisi/recall.
