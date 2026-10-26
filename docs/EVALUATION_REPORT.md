# Synthetic v2.4 Model Training & Evaluation — Historical Baseline

> This document preserves the v2.4 seed-42 evaluation record. For the current
> cross-model portfolio (real-data cost benchmark A/B/C and synthetic classifier
> candidates v2.4/v3), see [`BPJS_SYNTH_CALIBRATION_REPORT.md`](BPJS_SYNTH_CALIBRATION_REPORT.md)
> and the portfolio figure below. Classifier results remain synthetic-only.

> **Synthetic demonstrator only — not BPJS performance validation.**

- Dataset version: `synthetic-v2.4.0-demonstrator`
- Train / validation / test: 150,000 / 50,000 / 50,000
- Seed: `42`
- Config SHA-256: `f088e5ff474c88ebdd1a8cbc1f012ac59dae2c38e5d09072ad0abebb1a9d04df`
- Test set was not used for feature selection or hyperparameter tuning. Aggregate AP group-bootstrap 95% CI: 0.7037–0.7464 (groups=48,437, resamples=100).

## Cost benchmark regressor

- Training rows: normal train claims only
- Validation-only selected ablation: `severity_and_base_rate`
- Test normal n: 48,500
- Test MAPE: 12.830%; MedAE: 641,852.38
- Test MAE: 863,858.85; RMSE: 1,177,733.96; R²: 0.8640
- Upper interval target coverage: 90%; measured: 90.179%

## Supervised classifier candidate (not runtime)

- Test n: 50,000; positive n: 1,500
- Average Precision: 0.7259
- ROC-AUC: 0.9446
- Baseline Average Precision:
  - random: 0.0299 (n=50,000, positives=1,500)
  - absolute_benchmark_deviation: 0.1704 (n=50,000, positives=1,500)
  - logistic_regression_rule_flags: 0.1747 (n=50,000, positives=1,500)

### Feature set v3 (grouper-consistency upgrade)

28 fitur (sebelumnya 25) — tiga fitur baru dibentuk dari kolom dataset yang
sudah ada (tanpa regenerasi dataset), terinspirasi keluaran grouper INA-CBG
yang dapat berkontradiksi dengan klaim faskes:

- `ina_grouper_severity`: severitas versi grouper ('0'/'I'/'II'/'III') sebagai angka
- `grouper_severity_gap`: selisih severitas diklaim vs grouper (rawat inap saja)
- `cost_to_sev_factor_ratio`: biaya diklaim / (tarif regional × faktor severitas klaim)

### Classifier configuration (selected on validation only)

- depth 5, scale_pos_weight 1: validation AP 0.7152 @ iteration 346
- depth 5, scale_pos_weight 3: validation AP 0.7082 @ iteration 400
- depth 6, scale_pos_weight 1: validation AP 0.7220 @ iteration 306
- depth 6, scale_pos_weight 3: validation AP 0.7128 @ iteration 346
- Selected: depth 6, scale_pos_weight 1, iteration 306; the test set played no part in this choice.

### Fitur paling berpengaruh (gain)

- `exact_copy_group_size`: 189
- `surgical_indicator`: 71
- `cost_to_sev_factor_ratio`: 67
- `grouper_severity_gap`: 54
- `unsupported_procedure_8151_flag`: 37

### Operating point (threshold 0.3173, selected on validation)

- Accuracy: 98.5440%; Precision: 80.4897%; Recall: 67.9333%; F1: 0.7368
- Specificity: 99.4907%; Balanced accuracy: 83.7120%; MCC: 0.7321
- Brier score: 0.0129; Log loss: 0.0601; ECE: 0.0058
- Alerts: 1,266 of 50,000 (2.532%); TP=1,019, FP=247, TN=48,253, FN=481
- The threshold was fitted on validation only and then frozen for test; test labels never selected it.

### Natural test by anomaly type

- `cloning`: positives=214, AP=0.0479, F1=0.145
- `inflated_bill`: positives=214, AP=0.0782, F1=0.193
- `phantom_billing`: positives=214, AP=0.0955, F1=0.218
- `prolonged_los`: positives=214, AP=0.0452, F1=0.130
- `repeat_billing`: positives=214, AP=0.2751, F1=0.215
- `unbundling`: positives=215, AP=0.4851, F1=0.288
- `upcoding`: positives=215, AP=0.0899, F1=0.189

Recall per tipe pada ambang 0.3173 (sweep kebijakan, pengukuran sekali di test):
unbundling 0.991, phantom_billing 0.752, repeat_billing 0.743, inflated_bill
0.668, upcoding 0.651, cloning 0.500, prolonged_los 0.449. Lompatan recall
aggregate (0.5500 → 0.6793) terutama dari slice upcoding yang sebelumnya
praktis buta (~0.009) dan kini tertangkap lewat kedua fitur grouper.

## Enriched stress evaluation

- Overall AP: 0.8905 (n=2,100, positives=1,050).
- Group-bootstrap AP 95% CI: 0.8754–0.9047 (groups=1,652).

### By anomaly type

- `cloning`: positives=150, AP=0.0806, F1=0.160; group CI 0.069–0.091
- `inflated_bill`: positives=150, AP=0.0959, F1=0.186; group CI 0.080–0.117
- `phantom_billing`: positives=150, AP=0.1160, F1=0.235; group CI 0.092–0.133
- `prolonged_los`: positives=150, AP=0.0764, F1=0.137; group CI 0.063–0.087
- `repeat_billing`: positives=150, AP=0.3133, F1=0.239; group CI 0.240–0.384
- `unbundling`: positives=150, AP=0.4768, F1=0.316; group CI 0.388–0.579
- `upcoding`: positives=150, AP=0.1345, F1=0.241; group CI 0.109–0.169

## OOD stress evaluation

- Overall AP: 0.7269 (n=5,000, positives=150).
- Group-bootstrap AP 95% CI: 0.6474–0.7923 (groups=4,836).

### By anomaly type

- `cloning`: positives=22, AP=0.0607, F1=0.148; group CI 0.030–0.117
- `inflated_bill`: positives=21, AP=0.0629, F1=0.149; group CI 0.027–0.122
- `phantom_billing`: positives=21, AP=0.1140, F1=0.257; group CI 0.077–0.184
- `prolonged_los`: positives=21, AP=0.0437, F1=0.135; group CI 0.022–0.072
- `repeat_billing`: positives=21, AP=0.2877, F1=0.230; group CI 0.113–0.445
- `unbundling`: positives=22, AP=0.4648, F1=0.295; group CI 0.250–0.712
- `upcoding`: positives=22, AP=0.1377, F1=0.228; group CI 0.083–0.210

## Current model portfolio visualization

The former seed-42 v2.4-only figures have been retired. The replacement below
shows the current cost-regression comparisons on real BPJS FKRTL test data and
classifier candidate comparisons on synthetic test data. These domains are
separate; no classifier performance on BPJS is implied and no candidate is
promoted to runtime.

![Current ML model portfolio: cost benchmark and classifier candidates](figures/model_performance_portfolio.png)


## Limitations

- Accuracy is inflated by the synthetic 3% anomaly prevalence; F1, average precision and recall are the primary balanced metrics.
- All claims and labels are synthetic; this does not validate BPJS performance.
- Test set was not used for feature or hyperparameter selection; the classifier threshold was fitted on validation only.
- Precision depends strongly on the synthetic 3% prevalence and is not an operational alert budget.
- Relational features (duplicate groups, per-patient gaps, expected-LOS benchmark) are computed per dataset split; the runtime scorer does not use them.
- Repeat-billing and cloning AP is bounded by designed legit readmission/duplicate hard negatives that share the same relational pattern.
- Grouper-consistency features (severity gap, cost-to-severity ratio) lifted recall everywhere; AP slices for cloning (0.0479) and prolonged_los (0.0452) remain weak and `prolonged_los` recall 0.449 keeps them on the feature-development backlog.
- Grouped bootstrap intervals are single-seed; multi-seed training/evaluation is still pending.
- Natural-test per-type confidence intervals are reported via the separate enriched and OOD slices, not as natural-prevalence estimates.
