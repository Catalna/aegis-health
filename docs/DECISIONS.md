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

## Classifier feature upgrade v3: grouper-consistency (2026-10-24)

- **Decision:** Extend the candidate classifier features 25 → 28 with three features derived from columns already present in the dataset (no dataset regeneration): `ina_grouper_severity` (grouper severity '0'/'I'/'II'/'III' as 0–3), `grouper_severity_gap` (claimed severity − grouper severity, inpatient only since outpatients always map '0'), and `cost_to_sev_factor_ratio` (cost_claimed ÷ (regional_base_rate × severity factor {0.82, 1.0, 1.27, 1.55})).
- **Reason:** Diagnostic sweep showed the recall wall was not the operating point: with validation-selected recall-target policies the test recall saturated ~0.585, while upcoding (14.3% of test positives) had recall ≈0.009. Product target from user discussion was 60–70% recall. The grouper-vs-claim severity disagreement is domain-plausible (an INA-CBG-style grouper produces its own severity from codes and can contradict the provider), reads only inference-time columns, and the cost ratio separates legit severity-4 claims (ratio ≈1) from bumped ones (≈0.8). Not label leakage; confirmed ML-only: `build_classifier_features` is referenced by training/evaluation code, not by runtime/agent-flow.
- **Selection discipline kept:** grid/policy on validation only; test read once. Selected depth 6, scale_pos_weight 1.0, iteration 306 (validation AP 0.7220). Test AP 0.6258 → 0.7259; operating recall 0.5500 → 0.6793 at precision 0.8049 (F1 0.7368); upcoding recall ≈0.009 → 0.651; ECE 0.0163 → 0.0058.
- **Trade-off honesty recorded:** per-type AP slipped slightly on cloning (0.0610→0.0479), prolonged_los (0.0508→0.0452), phantom (0.1041→0.0955), inflated (0.0805→0.0782); aggregate ranking improved. Both slicing improvement (prolonged/cloning) and upcoding AP remain on the feature-development backlog. Legacy 25-feature artifacts preserved (gitignored) at `backend/models_trained/synthetic_v2_25feat_legacy/`.
- New evaluation tooling: `scripts/sweep_operating_policy.py` (validation-selected recall-target policies + per-type recall table at the F1-max threshold).

## LLM provider priority (2026-10-24)

- **Decision:** Google AI Studio (Gemini API, `LLM_PROVIDER=gemini`) becomes the primary narration/synthesis model, with Ollama local (local `CLINICAL/REVIEW/EXPLANATION_MODEL` and their fallbacks) demoted to automatic backup, and the deterministic heuristic template as the last resort. Implemented as a cascade in `llm_client.structured_completion` (`_run_llm_with_fallback`); the serving provider is recorded in a per-task ContextVar and surfaced through `model_used`/`generated_by`.
- **Alternatives:** (a) keep Ollama primary — rejected per product direction, weaker narration for the demo; (b) Gemini only without backup — rejected: breaks the offline demo and the privacy posture.
- **Constraints kept:** LLM still never sets or changes scores/tiers/evidence; both providers are existing components (allowed to reorder, not add); without a `GEMINI_API_KEY` or internet the app degrades to Ollama and then templates, so a clean-machine demo keeps working.
- **Privacy rule activated by this change:** real JKN participant data must never leave the premise; before any real-data processing, force `LLM_PROVIDER=ollama` in `.env`. Synthetic demonstrator data only for the Google path.
