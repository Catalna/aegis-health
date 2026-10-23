# Engineering Decisions — Synthetic v2 / Risk Evaluation

## Score and relational tier floors

- **Decision:** Keep the runtime score as raw deterministic points on a maximum-85 scale; do not normalize it into a probability. UI and API expose `max_score=85`.
- **Reason:** Actual runtime component caps are 20 + 30 + 20 + 15; Isolation Forest has zero runtime weight. Normalizing would obscure the existing points and require retuning all tier thresholds.
- **Decision:** Exact duplicates have a High tier floor; strong cloning and repeat billing have a Medium floor. Floors do not alter raw points and are explained in evidence.

## Financial deviation

- **Decision:** Preserve signed `deviation_pct`, calculate `upward_exposure=max(0, claimed-benchmark)`, and score either direction using `min(abs(deviation_pct)/50, 1)` on both model and peer fallback paths.
- **Reason:** A downward deviation is not upward exposure, but it may still be a benchmark deviation signal. Neither is proof of overbilling or savings.

## Synthetic v2 profile and output choices

- **Decision:** Natural splits use the planned profile sizes and 3% configured anomaly prevalence; label metadata is stored separately.
- **Decision:** Enriched test contains 150 positives per anomaly type plus the same number of normal records. OOD stress size is 10% of natural test, bounded to 1,000–10,000, with new entity namespaces.
- **Reason:** The plan required enriched/OOD sets but did not set sizes; these conservative sizes are useful for demonstrator coverage without inflating the natural test set.
- **Decision:** Share synthetic facility/doctor/patient namespaces across natural time splits; use new facility/doctor namespaces in OOD. Keep relationship group IDs in label files only.
- **Decision:** Keep tariff/CBG and ICD-like values explicitly demonstrative until verified against an authoritative catalog and permitted tariff source.

## ML training

- **Decision:** Use native XGBoost (no sklearn wrapper) for v2 training and the financial runtime adapter. Train cost regression on normal train claims only; compare severity/base-rate ablations using validation; report test once after selection.
- **Decision:** Train the supervised XGBoost classifier as a candidate and do not add it to the runtime risk score.
- **Reason:** The training/evaluation environment had initially failed to load PyArrow through scikit-learn; native XGBoost and NumPy ranking metrics avoid that unrelated optional import. PyArrow later loaded successfully and Parquet generation/validation were then verified.
- **Decision:** Save v2 models under `backend/models_trained/synthetic_v2/` without replacing legacy runtime artifacts. The v2 feature contract differs from the legacy runtime regressor contract.
