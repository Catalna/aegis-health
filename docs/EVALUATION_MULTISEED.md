# Multi-Seed Replikasi — Klasifikasi & Regressor Synthetic v2

> **Data sintetis demonstrator** (synthetic-v2.4.0-demonstrator). Seluruh angka di halaman ini adalah replikasi pada data sintetis dan **bukan validasi performa BPJS**. Tidak ada pemilihan/tuning terhadap test set: hyperparameter dipilih di validation pada tiap seed, test dievaluasi sekali per seed.

- **Seeds**: 42/43/44/45/46 (n=5 replikasi, dataset diregenerasi penuh per seed)
- **Split per seed**: train 150,000 · validation 50,000 · test 50,000
- **kandidat klasifikasi, bukan runtime** — RiskScore runtime tetap deterministik

## Metrik klasifikasi gabungan (test natural)

| Metrik | mean ± stdev [min–max] |
|---|---|
| Test AP | 0.6086 ± 0.0102 [0.6007–0.6258] (n=5) |
| ROC-AUC | 0.9085 ± 0.0119 [0.8882–0.9178] (n=5) |
| F1 @ operating point | 0.6376 ± 0.0077 [0.6305–0.6501] (n=5) |
| Precision | 0.7534 ± 0.0363 [0.7012–0.7948] (n=5) |
| Recall | 0.5535 ± 0.0122 [0.5393–0.5727] (n=5) |
| Accuracy | 0.9811 ± 0.0009 [0.9799–0.9822] (n=5) |
| Brier | 0.0166 ± 0.0002 [0.0165–0.0169] (n=5) |
| ECE | 0.0073 ± 0.0052 [0.0034–0.0163] (n=5) |
| F1@10% | 0.3437 ± 0.0044 [0.3394–0.3502] (n=5) |

## Stress slice gabungan

| Metrik | mean ± stdev [min–max] |
|---|---|
| Enriched AP | 0.8526 ± 0.0053 [0.8462–0.8604] (n=5) |
| OOD AP | 0.5982 ± 0.0304 [0.5457–0.6215] (n=5) |

## Per tipe anomali — test natural

Spread antar-seed; slice tipis (positif kecil per tipe) rentan berfluktuasi, lapor apa adanya.

| Tipe | AP mean ± stdev [min–max] | F1 mean ± stdev [min–max] |
|---|---|---|
| cloning | 0.0647 ± 0.0050 [0.0594–0.0720] (n=5) | 0.1639 ± 0.0085 [0.1515–0.1727] (n=5) |
| inflated_bill | 0.0722 ± 0.0053 [0.0678–0.0805] (n=5) | 0.1912 ± 0.0157 [0.1738–0.2157] (n=5) |
| phantom_billing | 0.0990 ± 0.0054 [0.0918–0.1047] (n=5) | 0.2325 ± 0.0169 [0.2071–0.2508] (n=5) |
| prolonged_los | 0.0510 ± 0.0056 [0.0449–0.0579] (n=5) | 0.1570 ± 0.0149 [0.1369–0.1765] (n=5) |
| repeat_billing | 0.1636 ± 0.0152 [0.1424–0.1807] (n=5) | 0.1838 ± 0.0118 [0.1696–0.1956] (n=5) |
| unbundling | 0.5857 ± 0.0189 [0.5602–0.6079] (n=5) | 0.3204 ± 0.0152 [0.2944–0.3320] (n=5) |
| upcoding | 0.0145 ± 0.0014 [0.0128–0.0163] (n=5) | 0.0121 ± 0.0076 [0.0032–0.0240] (n=5) |

## Regressor benchmark biaya (test natural, klaim normal)

| Metrik | mean ± stdev [min–max] |
|---|---|
| MAPE (%) | 12.86 ± 0.09 [12.75–12.99] (n=5) |
| MdAPE (%) | 10.36 ± 0.07 [10.30–10.46] (n=5) |
| MAE (Rp) | 881658 ± 13140 [863859–898605] (n=5) |
| RMSE (Rp) | 1199287 ± 17514 [1177734–1224009] (n=5) |
| R² | 0.8628 ± 0.0030 [0.8589–0.8664] (n=5) |
| Coverage upper bound (%) | 89.99 ± 0.26 [89.60–90.24] (n=5) |

## Beban acuans (baseline, test natural)

| Baseline | AP mean ± stdev [min–max] |
|---|---|
| absolute benchmark deviation | 0.1589 ± 0.0068 [0.1538–0.1704] (n=5) |
| logistic regression rule flags | 0.1678 ± 0.0047 [0.1621–0.1747] (n=5) |
| random | 0.0300 ± 0.0007 [0.0294–0.0312] (n=5) |

## Konfigurasi terpilih per seed (dari validation)

| Seed | depth | scale_pos_weight | best_iteration |
|---|---|---|---|
| 42 | 5 | 3.0 | 374 |
| 43 | 5 | 1.0 | 399 |
| 44 | 5 | 1.0 | 385 |
| 45 | 5 | 1.0 | 373 |
| 46 | 5 | 1.0 | 400 |

## Batasan

- 5 seed → statistik disebarkan lunak; interval sebaran bukan CI formal yang diuji signifikan.
- Prevalensi sintetis 3% membuat akurasi terlihat tinggi; AP/F1 per tipe lebih informatif.
- Slice repeat-billing dibatasi desain hard negative readmission (~AP 0.18).
- Ini replikasi stabilitas, bukan kepastian performa pada data riil BPJS.
