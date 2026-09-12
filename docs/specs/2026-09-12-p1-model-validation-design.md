# P1 Model Validation & Evaluation Design

> **J-ARI: JKN Agentic Risk Intelligence**
> Status: Proposed
> Scope: Offline backend evaluation only; UI evaluation is explicitly deferred.

## 1. Goal

Membuktikan apakah risk score J-ARI dapat meranking klaim anomali di posisi teratas secara reproducible, tanpa leakage, dan tanpa ketergantungan pada output LLM.

P1 tidak mengubah formula P0 secara diam-diam. Semua perubahan bobot atau threshold diperlakukan sebagai kandidat konfigurasi yang dibandingkan melalui evaluasi dan diberi versi.

## 2. Success Criteria

- Evaluasi dapat dijalankan ulang dengan command tunggal dan seed eksplisit.
- Train/reference data dan held-out evaluation data dibuat dari seed berbeda.
- Klaim yang termasuk pasangan atau kelompok anomaly tidak terbelah antar split.
- Hasil memuat metrik agregat dan per `anomaly_type`.
- Setiap angka yang belum berasal dari evaluator diberi label target, bukan hasil.
- Artifact hasil memuat dataset version, analysis version, engine/model version, seed, konfigurasi, dan batasan.
- UI tidak diubah pada batch ini.

## 3. Non-Goals

- Tidak menggunakan data pasien nyata atau koneksi BPJS eksternal.
- Tidak melakukan deployment, retraining production, atau threshold rollout otomatis.
- Tidak mengoptimalkan skor terhadap held-out test set.
- Tidak menjadikan LLM sebagai labeler, scorer, atau komponen wajib evaluator.

## 4. Evaluation Architecture

P1 memakai tiga lapisan terpisah:

1. **Dataset builder** menghasilkan claim fixture dan metadata label dari synthetic generator.
2. **Pipeline adapter** mengubah setiap claim menjadi deterministic assessments yang diperlukan oleh `calculate_risk_score()`.
3. **Evaluator** menghitung ranking metrics, calibration, latency, dan ablation dari output final.

LLM tidak dipanggil dalam jalur scoring evaluator. Review synthesis dapat disediakan sebagai rule fallback untuk memenuhi signature risk engine, tetapi nilai numerik hanya berasal dari clinical, financial, dan fraud assessments.

Output utama adalah JSON versioned, bukan database row dan bukan UI payload.

Pipeline adapter tidak menjalankan orchestrator, SSE, atau database persistence. Adapter memakai `ClaimInput`, model artifact yang sudah ada, dan relation index in-memory untuk menghasilkan assessment. Jika agent production belum memiliki pure seam, P1 menambahkan seam kecil yang dapat di-inject tanpa mengubah kontrak production. Semua dependency jaringan dan LLM dilarang pada evaluator default.

## 5. Dataset Protocol

Dataset menggunakan generator yang sudah memiliki label `is_synthetic_anomaly` dan `anomaly_type`. Builder P1 harus menambahkan metadata split tanpa mengubah label generator.

- Reference/train split memakai seed `42`.
- Held-out split memakai seed `2026`.
- Claim IDs diberi prefix berbeda, misalnya `P1-TRAIN-*` dan `P1-HOLDOUT-*`.
- Cloning pair, repeat-billing source/clone, dan seluruh unbundling group diperlakukan sebagai satu evaluation group.
- Satu group tidak boleh muncul pada dua split.
- Distribusi anomaly type dicatat agar hasil tidak hanya mencerminkan kelas normal.
- Dataset output disimpan sebagai artifact reproducible dengan jumlah row, seed, generator version, dan class counts.

Label evaluasi biner adalah `is_synthetic_anomaly`. Label multiclass `anomaly_type` dipakai untuk slice analysis, bukan untuk mengubah risk score.

## 6. Metrics

Evaluator mengurutkan claim berdasarkan `RiskScore.total_score` descending dan memakai label held-out.

- **Precision@K** untuk K yang eksplisit, minimal `K=50` dan `K=100` jika ukuran split mencukupi.
- **Recall@K** untuk K yang sama.
- **Average Precision / PR-AUC** pada seluruh ranking held-out.
- **Calibration** melalui reliability bins dan Brier score hanya jika output dikonversi menjadi probability dengan aturan yang terdokumentasi. Raw risk score tidak disebut probability.
- **Latency**: wall-clock per claim dan aggregate p50/p95, dipisahkan antara dataset preparation dan scoring.
- **Per anomaly type**: count, score distribution, top-K hit count, dan false-negative count untuk setiap type.

Jika jumlah anomaly atau K tidak memadai, evaluator mengembalikan `not_computable` dengan alasan, bukan angka nol yang menyesatkan.

## 7. Ablation Design

Semua konfigurasi menggunakan held-out set dan ordering yang sama. Hasil dibandingkan, bukan dipakai untuk memilih konfigurasi berdasarkan test set.

1. **Core**: clinical consistency + reimbursement anomaly + relational patterns.
2. **Core plus behavioral context**: menambahkan Isolation Forest/provider context sebagai candidate signal untuk mengukur nilai tambah, tanpa mengubah production P0 score.
3. **Weight sensitivity**: menguji konfigurasi bobot yang sudah ditentukan sebelum run; tidak melakukan arbitrary search di held-out set.

Ablation report wajib menyebutkan apakah behavioral context meningkatkan Precision@K/Recall@K secara material, netral, atau menambah false positives. Hasil ablation tidak otomatis mengubah production contract.

## 8. Result Artifact

Evaluator menulis satu artifact JSON dengan bentuk konseptual berikut:

```json
{
  "schema_version": 1,
  "dataset": {"version": "p1-synthetic-v1", "seed": 2026, "counts": {}},
  "engine": {"analysis_version": 6, "config_version": "p0-default"},
  "metrics": {"aggregate": {}, "by_anomaly_type": {}, "latency": {}},
  "ablation": [],
  "limitations": []
}
```

Artifact tidak boleh memuat PII. Setiap run juga menghasilkan summary terminal singkat dengan path artifact dan status metrik (`measured` atau `not_computable`).

## 9. Failure Handling

- Input claim yang gagal validasi dicatat sebagai rejected fixture dengan alasan dan tidak diam-diam dihitung sebagai true negative.
- Error scoring per claim dicatat bersama claim ID dan dikeluarkan dari metrik utama; jumlah error wajib muncul di summary.
- Error dataset split menghentikan run sebelum scoring jika group leakage terdeteksi.
- Missing model artifact menggunakan fallback yang sudah ada hanya jika konfigurasi run mengizinkannya; method yang digunakan wajib dicatat.
- Evaluator gagal dengan exit code non-zero jika artifact tidak dapat ditulis atau metadata wajib hilang.

## 10. Verification

- Unit tests untuk group-aware split, metric edge cases, dan artifact schema.
- Regression test untuk memastikan evaluator tidak memanggil LLM.
- Reproducibility test: dua run dengan seed/config yang sama menghasilkan labels, ranking, dan metric JSON yang sama selain field runtime yang eksplisit.
- Full backend test suite dan evaluator command dijalankan sebelum P1 dianggap selesai.

## 11. Deferred Work

- Halaman `MLEvaluation` dan visualisasi metrics.
- Calibration/threshold rollout ke production.
- Validasi label bersama domain expert BPJS.
- Benchmark data berizin dan external pilot.
