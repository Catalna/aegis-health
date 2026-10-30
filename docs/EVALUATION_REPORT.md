# Indeks Report Model — AEGIS-Health Post-Model

Status portofolio: model biaya legacy masih menjalankan skoring runtime; kandidat biaya BPJS terbaru dievaluasi offline. Kandidat classifier sintetis tetap eksperimen historis tanpa validasi fraud BPJS. Visual aktif terbaru:

**Eksperimen kandidat biaya post-grouper terbaru (tanpa promosi runtime):** [`BPJS_COST_IMPROVEMENT_REPORT.md`](BPJS_COST_IMPROVEMENT_REPORT.md). Visual empat panel sudah diperbarui untuk kandidat log-XGBoost; penjelasan: [`BPJS_COST_TEMPORAL_VISUAL_REPORT.md`](BPJS_COST_TEMPORAL_VISUAL_REPORT.md).

[`BPJS_COST_TEMPORAL_VISUAL_REPORT.md`](BPJS_COST_TEMPORAL_VISUAL_REPORT.md) — Actual vs Predicted, Learning Curve, Residual Plot, dan TreeSHAP.

| Model | Fungsi | Dokumen per-model | Generator figur |
|---|---|---|---|
| **Kandidat biaya BPJS — audit temporal** | Estimasi biaya verifikasi; bukan keputusan klinis/fraud | [`BPJS_COST_TEMPORAL_AUDIT_REPORT.md`](BPJS_COST_TEMPORAL_AUDIT_REPORT.md) | `scripts/bpjs/cost_temporal_audit.py` |
| Kandidat biaya C lama (historis) | Benchmark biaya BPJS pada split subject acak | [`MODEL1_BIAYA_C_REPORT.md`](MODEL1_BIAYA_C_REPORT.md) | Figur lama dipensiunkan |
| Kandidat classifier sintetis v3 (historis) | Klasifikasi label generator sintetis; bukan fraud BPJS tervalidasi | [`MODEL2_KLASIFIER_V3_REPORT.md`](MODEL2_KLASIFIER_V3_REPORT.md) | Figur lama dipensiunkan |

**Tidak ada model ke-3.** Pilar aturan (deviation + cadence + cek identitas) bersifat *rule-based*, bukan model ML. Kandidat v2.4 klasifier dan varian A/B biaya adalah pembanding eksperimen, bukan model tambahan.

## Status runtime

- Backend runtime masih memakai model biaya **LEGACY** `backend/models_trained/xgboost_regressor.json` (kontrak `COST_FEATURE_NAMES`).
- Tidak ada model klasifikasi di runtime.
- Semua kandidat menunggu gate A3 pasca-1-Nov (`docs/MODELS.md` §2.6, evaluasi per-strata wajib) — penolakan di gate adalah hasil yang mungkin dan sah.

## Arsip v2.4 (kandidat klasifier sebelumnya + benchmark biaya sintetis)

- Evaluasi v2.4 seed-42: dataset `synthetic-v2.4.0-demonstrator` (config SHA `f088e5ff474c88ebdd1a8cbc1f012ac59dae2c38e5d09072ad0abebb1a9d04df`), AP test klasifier 0.7259 (CI95 0.7037–0.7464); benchmark biaya sintetis test MAPE 12.83%.
- Rekor lengkap tersimpan di `backend/models_trained/synthetic_v2/synthetic_v2_training_report.json` + riwayat git dokumen ini.
- Set figur v2.4 lama sudah dipensiunkan agar tidak tertukar dengan kandidat kini — semua figur aktif berlabel model eksplisit.


## Lapis inteligensi di luar portfolio — LLM Lokal (otak pemahaman & pelaporan)

Portfolio di atas adalah mesin risiko (scoring 100% deterministik). Di luar keduanya, **otak utama pemahaman & pelaporan** sistem adalah LLM yang dioperasikan **tersemat di local (self-hosted)** — model Pelapor terkunci `deepseek-r1:7b`. Kebijakan local-first dipilih eksplisit atas empat pertimbangan:

- **Privasi**: data kesehatan peserta JKN tidak pernah dikirim ke layanan cloud eksternal (UU PDP No. 27/2022; aturan privasi `docs/DECISIONS.md`).
- **Biaya & keberlanjutan**: tidak ada biaya per-token dan tidak bergantung rate-limit vendor; LLM tidak berada di jalur penilaian — worst case rantai jatuh ke template deterministik (biaya marginal Rp0 per klaim).
- **Efisiensi & keandalan offline**: faskes/internet tidak selalu stabil; pipeline tetap beroperasi penuh secara lokal.
- **Auditabilitas**: model disematkan + seed 42 + temperature 0.2 sehingga narasi reprodusibel (alias model cloud bergerak bisa berganti versi diam-diam).

Bukti kinerja (benchmark internal terukur, `backend/app/data/analysis/llm_bench_results.json`): 15–25 detik per laporan, JSON valid 6/6 panggilan terukur. Status jujur: komponen ini belum menjadi bagian runtime hingga integrasi pasca-1-Nov; rantai runtime saat ini memakai gemini hanya untuk kenyamanan pengembangan dengan data sintetis. Detail arsitektur: `docs/specs/2026-10-27-agent-hierarchy-design.md`.
