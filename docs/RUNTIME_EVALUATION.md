# Runtime-ranking evaluation (Fase 3.4)

> **Synthetic demonstrator only — not BPJS performance validation.**

- Jalur yang diukur: **runtime produksi deterministik** (rule clinical + XGBoost financial + relasional in-memory + tier floors, RiskScore 0–85) via `evaluation.pipeline.score_claims`, **tanpa LLM**.
- Sampel slice enriched: 350 anomali (50 per tipe × 7) + 350 normal, total 700; prevalensi di-angkat sengaja ke 50% — precision@K bersyarat pada prevalensi ini.
- Test split seed-42 yang sama dengan training kanonik; metadata model: `backend/models_trained/synthetic_v2_training_report.json` (gitignored).
- Pembanding: kandidat ML (28 fitur) dijalankan pada slice yang sama — AP 0.9158.
- Lingkup: relasional dihitung dalam-sampel saja; floor `high` exact-duplicate tidak aktif offline (DB-gated); jendela relasional produksi 45 hari vs mekanisme repeat v2 gap 46–60 hari.
- Etika: hyperparameter/runtime diukur apa adanya; semua label sintetis.

## Ranking budget (top-K pada slice)

| K (porsi slice) | Precision@K | Recall@K |
|---|---|---|
| 35 (5%) | 0.829 | 0.083 |
| 70 (10%) | 0.657 | 0.131 |
| 105 (15%) | 0.610 | 0.183 |
| 140 (20%) | 0.607 | 0.243 |
| 210 (30%) | 0.586 | 0.351 |

**AP slice**: runtime 0.5964 vs kandidat ML 0.9158 pada slice identik — runtime tetap prioritas penyaring; kandidat ML tetap kandidat (tier runtime tidak berubah).

## Latensi (path deterministik, tanpa LLM)

- klaim pertama (build model financial + SHAP sekali): 18325 ms
- sesudah warmup: p50 75 ms, p95 845 ms (metode financial: {"xgboost_model": 700})
- kontras: e2e produksi dengan LLM+SHAP p50 ≈ 7,3 s (probe live terpisah); angka ini membedakan komponen deterministik dari biaya narasi LLM.

## Distribusi tier

> Catatan (2026-10-24): angka distribusi berikut diukur dengan ambang default lama (medium ≥ 25, high ≥ 60) — itu pendorong utama kalibrasi tier; ambang saat ini medium ≥ 48.7, high ≥ 55 (lihat `docs/TIER_CALIBRATION.md`).

- keseluruhan: {"medium": 609, "low": 78, "high": 13}

| Tipe | median skor | tier medium+high |
|---|---|---|
| cloning | 35.0 | 42 |
| inflated_bill | 35.0 | 45 |
| none | 35.0 | 305 |
| phantom_billing | 48.0 | 50 |
| prolonged_los | 35.0 | 44 |
| repeat_billing | 35.0 | 48 |
| unbundling | 35.0 | 42 |
| upcoding | 46.0 | 46 |

## Rasio flag fraud per tipe (diagnostik, bukan field rapor)

| Tipe | repeat | cloning | unbundling |
|---|---|---|---|
| cloning | 0.00 | 0.00 | 0.00 |
| inflated_bill | 0.00 | 0.00 | 0.00 |
| none | 0.00 | 0.00 | 0.00 |
| phantom_billing | 0.00 | 0.00 | 0.00 |
| prolonged_los | 0.00 | 0.00 | 0.00 |
| repeat_billing | 0.00 | 0.00 | 0.00 |
| unbundling | 0.26 | 0.00 | 0.08 |
| upcoding | 0.00 | 0.00 | 0.00 |

## Limitations

- Prevalensi slice di-angkat (enriched): precision@K bukan angka produksi; gunakan recall@K dan AP sebagai ukuran ranking relatif.
- Konteks relasional = sampel 700 klaim; di produksi konteks berasal dari riwayat DB pasien/faskes (konsekuen: hitungan flag bisa berbeda).
- Runtime memakai kartu tarif v1 (10 keluarga diagnosis) — sebagian besar diagnosis v2 jatuh ke fallback z-score financial; keterbatasan nyata, dilaporkan apa adanya.
- Floor tier `high` exact-duplicate hanya aktif di jalur produksi berbasis DB (gate `validate_deterministic`).
- Jendela 45 hari produksi vs mekanisme repeat v2 gap 46–60 hari menjelaskan rasio flag repeat yang rendah: rerancangan episode-linking ada di backlog, bukan kegagalan deteksi yang disembunyikan.
- Semua claim/label sintetis; bukan validasi kinerja BPJS.
