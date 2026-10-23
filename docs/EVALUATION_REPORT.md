# Synthetic v2 Model Training & Evaluation

> **Synthetic demonstrator only — not BPJS performance validation.**

- Dataset version: `synthetic-v2.4.0-demonstrator`
- Train / validation / test: 150,000 / 50,000 / 50,000
- Seed: `42`
- Config SHA-256: `335e07da7ee44537cdccb9e0cb42d481f704384707ff6862085211d488177855`
- Test set was not used for feature selection or hyperparameter tuning. Aggregate AP group-bootstrap 95% CI: 0.5217–0.5762 (groups=48,437, resamples=100).

## Cost benchmark regressor

- Training rows: normal train claims only
- Validation-only selected ablation: `severity_and_base_rate`
- Test normal n: 48,500
- Test MAPE: 12.830%; MedAE: 641,852.38
- Upper interval target coverage: 90%; measured: 90.179%

## Supervised classifier candidate (not runtime)

- Test n: 50,000; positive n: 1,500
- Average Precision: 0.5480
- Baseline Average Precision:
  - random: 0.0299 (n=50,000, positives=1,500)
  - absolute_benchmark_deviation: 0.1704 (n=50,000, positives=1,500)
  - logistic_regression_rule_flags: 0.1747 (n=50,000, positives=1,500)

### Natural test by anomaly type

- `cloning`: positives=214, AP=0.0038637806810738074
- `inflated_bill`: positives=214, AP=0.14029458813253137
- `phantom_billing`: positives=214, AP=0.03227090936269841
- `prolonged_los`: positives=214, AP=0.06386068019378126
- `repeat_billing`: positives=214, AP=0.21753097608294134
- `unbundling`: positives=215, AP=0.6377426436150567
- `upcoding`: positives=215, AP=0.014964421500968078

## test_enriched stress evaluation

- Overall AP: 0.8732 (n=2,100, positives=1,050).
- Group-bootstrap AP 95% CI: 0.8586–0.8864 (groups=1,652).

### By anomaly type

- `cloning`: positives=150, AP=0.0474; group CI 0.042–0.054
- `inflated_bill`: positives=150, AP=0.1634; group CI 0.134–0.200
- `phantom_billing`: positives=150, AP=0.0934; group CI 0.075–0.107
- `prolonged_los`: positives=150, AP=0.1142; group CI 0.090–0.133
- `repeat_billing`: positives=150, AP=0.2608; group CI 0.199–0.324
- `unbundling`: positives=150, AP=0.6393; group CI 0.553–0.733
- `upcoding`: positives=150, AP=0.0712; group CI 0.058–0.087

## ood stress evaluation

- Overall AP: 0.5037 (n=5,000, positives=150).
- Group-bootstrap AP 95% CI: 0.4125–0.5716 (groups=4,836).

### By anomaly type

- `cloning`: positives=22, AP=0.0044; group CI 0.002–0.007
- `inflated_bill`: positives=21, AP=0.1215; group CI 0.054–0.230
- `phantom_billing`: positives=21, AP=0.0297; group CI 0.016–0.051
- `prolonged_los`: positives=21, AP=0.0815; group CI 0.037–0.127
- `repeat_billing`: positives=21, AP=0.1293; group CI 0.057–0.278
- `unbundling`: positives=22, AP=0.7406; group CI 0.491–0.891
- `upcoding`: positives=22, AP=0.0173; group CI 0.010–0.036

## Limitations

- All claims and labels are synthetic; this does not validate BPJS performance.
- Test set was not used for feature or hyperparameter selection.
- Grouped bootstrap intervals are single-seed; multi-seed training/evaluation is still pending.
- Natural-test per-type confidence intervals are reported via the separate enriched and OOD slices, not as natural-prevalence estimates.
