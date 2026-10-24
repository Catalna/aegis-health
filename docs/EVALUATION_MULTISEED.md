# Multi-Seed Replikasi — Klasifikasi & Regressor Synthetic v2

> **Data sintetis demonstrator** (synthetic-v2.4.0-demonstrator). Seluruh angka di halaman ini adalah replikasi pada data sintetis dan **bukan validasi performa BPJS**. Tidak ada pemilihan/tuning terhadap test set: hyperparameter dipilih di validation pada tiap seed, test dievaluasi sekali per seed.

- **Seeds**: 42/43/44/45/46 (n=5 replikasi, dataset diregenerasi penuh per seed)
- **Split per seed**: train 150,000 · validation 50,000 · test 50,000
- **kandidat klasifikasi, bukan runtime** — RiskScore runtime tetap deterministik

## Metrik klasifikasi gabungan (test natural)

| Metrik | mean ± stdev [min–max] |
|---|---|
| Test AP | 0.7153 ± 0.0104 [0.7038–0.7259] (n=5) |
| ROC-AUC | 0.9447 ± 0.0032 [0.9395–0.9482] (n=5) |
| F1 @ operating point | 0.7310 ± 0.0089 [0.7187–0.7416] (n=5) |
| Precision | 0.8095 ± 0.0199 [0.7924–0.8398] (n=5) |
| Recall | 0.6667 ± 0.0122 [0.6533–0.6793] (n=5) |
| Accuracy | 0.9853 ± 0.0006 [0.9846–0.9861] (n=5) |
| Brier | 0.0131 ± 0.0004 [0.0127–0.0137] (n=5) |
| ECE | 0.0051 ± 0.0007 [0.0040–0.0058] (n=5) |
| F1@10% | 0.3807 ± 0.0029 [0.3772–0.3849] (n=5) |

## Stress slice gabungan

| Metrik | mean ± stdev [min–max] |
|---|---|
| Enriched AP | 0.8872 ± 0.0051 [0.8784–0.8911] (n=5) |
| OOD AP | 0.7069 ± 0.0254 [0.6736–0.7298] (n=5) |

## Per tipe anomali — test natural

Spread antar-seed; slice tipis (positif kecil per tipe) rentan berfluktuasi, lapor apa adanya.

| Tipe | AP mean ± stdev [min–max] | F1 mean ± stdev [min–max] |
|---|---|---|
| cloning | 0.0519 ± 0.0030 [0.0479–0.0549] (n=5) | 0.1485 ± 0.0042 [0.1446–0.1543] (n=5) |
| inflated_bill | 0.0692 ± 0.0064 [0.0606–0.0782] (n=5) | 0.1799 ± 0.0093 [0.1701–0.1932] (n=5) |
| phantom_billing | 0.0936 ± 0.0096 [0.0830–0.1060] (n=5) | 0.2115 ± 0.0097 [0.1973–0.2229] (n=5) |
| prolonged_los | 0.0440 ± 0.0049 [0.0388–0.0493] (n=5) | 0.1296 ± 0.0152 [0.1086–0.1440] (n=5) |
| repeat_billing | 0.2444 ± 0.0293 [0.1980–0.2751] (n=5) | 0.2142 ± 0.0101 [0.2003–0.2286] (n=5) |
| unbundling | 0.5194 ± 0.0349 [0.4851–0.5775] (n=5) | 0.2938 ± 0.0082 [0.2838–0.3041] (n=5) |
| upcoding | 0.0967 ± 0.0164 [0.0707–0.1087] (n=5) | 0.2020 ± 0.0148 [0.1864–0.2227] (n=5) |

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
| 42 | 6 | 1.0 | 306 |
| 43 | 6 | 1.0 | 393 |
| 44 | 6 | 1.0 | 280 |
| 45 | 6 | 1.0 | 344 |
| 46 | 5 | 1.0 | 398 |

## Batasan

- 5 seed → statistik disebarkan lunak; interval sebaran bukan CI formal yang diuji signifikan.
- Prevalensi sintetis 3% membuat akurasi terlihat tinggi; AP/F1 per tipe lebih informatif.
- Slice repeat-billing dibatasi desain hard negative readmission (~AP 0.18).
- Ini replikasi stabilitas, bukan kepastian performa pada data riil BPJS.
