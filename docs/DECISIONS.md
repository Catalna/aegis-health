# Engineering Decisions — Synthetic v2 / Risk Evaluation

## Real BPJS sample-data usage rules (2026-10-26)

- **Decision:** The licensed BPJS "Data Sampel 2025" (`backend/app/data/2025/`, gitignored) is used ONLY for offline analysis and retraining, through aggregate outputs. Raw rows, row dumps, or participant identifiers (`PSTV01`, `FKL02`, DOB, names) never leave the machine and are never committed. All derived artefacts remain under the gitignored `backend/app/data/analysis/`.
- **Benchmark training ground truth:** the fully-accepted subset `FKL47 == FKL48` (claims handed over without verification reductions; 99.90% of FKRTL rows). Splits are subject-based (crc32(PSTV01) % 10) so one participant never crosses train→test; the `ina_cbg_base_rate` feature is a train-only median table; feature provenance (real / derivation / constant-gap) is recorded in the model artifact folder. No supervised fraud training exists or is attempted (the dataset carries no fraud labels); candidate classifier metrics remain gated behind the synthetic-label evaluation.
- **Declared-at-training-time gaps fill with fixed constants, never invented values:** `icu_indicator=0`, `ventilator_used=0`, `num_medications=0` (the Reguler package has no drug item detail and the SA sub-acute component is effectively empty). These gaps are hooks for the A1 intake pathways, not defaults to hide.
- **Runtime freeze discipline:** everything derived from real data is a candidate artifact; promotion into scoring happens exclusively through the A3 gate after the 1 Nov demo video. Nothing real-data-derived touches runtime code, demo numbers, or tier bands before that gate.
- **Narration over real data:** force `LLM_PROVIDER=ollama` before any LLM task that reads real BPJS content — extends the 2026-10-24 privacy rule from "processing" to every real-data-touching task (translation, summarization, explanations). Synthetic demonstrator data only for the Gemini path.

## Curated demo database is presentational, not evaluation truth (2026-10-24)

- **Decision:** The demo database (220 claims, `scripts/demo_seed.py`) is a **presentational seed only**. Its scenario tags and expected tiers exist so the recorded demo stays legible; they are checked offline against the runtime engine via a `--dry-run` mirror before any POST. The seeded corpus is never used as an evaluation, validation, or calibration set for any model, threshold, or tier band.
- **Reason:** Seeded claims are built with deliberate content design (shared providers/code sets/time windows) and costs calibrated against the in-process financial model (`claimed = predicted × multiplier`) so runtime financial scores are deterministic per scenario. Tuning anything on this corpus would fit the seed's construction conventions, not generalize; it would also create label leakage into the runtime path.
- **Constraints kept:** seeding goes through the production flow only (POST → FIFO worker → orchestrator → LanceDB, never direct DB writes); no runtime label-based overrides — every score/tier/evidence is the engine's honest raw output (points, floors, relational evidence); claims-of-performance numbers stay exclusively with the evaluation slices (`docs/TIER_CALIBRATION.md`, `docs/EVALUATION_REPORT.md`, `docs/RUNTIME_EVALUATION.md`), always with the synthetic-demonstrator disclaimer.

## Runtime tier band recalibration (2026-10-24)

- **Decision:** Replace the inherited, never-calibrated tier bands (medium ≥ 25, high ≥ 60) with calibrated bands **medium ≥ 48.7, high ≥ 55.0**, selected on a 700-claim validation slice through the deterministic runtime path and verified once on a 700-claim test slice. Applied in `risk_engine.calculate_risk_score` and mirrored in `evaluation.pipeline._priority_tier`. The relational Medium floor now also covers **unbundling**, aligning code with the engine's own evidence narrative.
- **Reason:** Fase 3.4 exposed hard tier compression — 87% of the enriched test slice landed medium+high (609/700), normals' median score (35.0) equal to most anomaly types' — making the verifier queue useless and the UI unhealthy. The calibrated bands restore separation: high tier = 18 claims with **precision 1.000** (13 unbundling + 5 upcoding), alert (medium+high) 5.7% at precision 0.800 (vs 88.9% at precision 0.510 with old bands). Engine scores are quantized (clumps at 35/48); the 10–22% alert window was empty so the pre-registered fallback (minimize |alert_frac − 0.20|) picked the nearest available band just above the 48-clump, where no normal claims sit.
- **Discipline:** selection on validation only; test read once; full grid, histogram, and fallback history in `docs/TIER_CALIBRATION.md` + `backend/models_trained/tier_band_calibration.json` (gitignored). Test suite 334 passed / 2 skipped after the change.
- **Trade-off recorded:** alert recall on the enriched slice drops to ~9% — the tier is a capacity-triage label, not the detection instrument; detection remains runtime ranking (AP 0.5964) and the candidate ML. Restoring engine recall is the engine-repair backlog (repeat window 46–60 days, v2 cloning thresholds, v1 tariff map), not a threshold problem.

## Score and relational tier floors

- **Decision:** Keep the runtime score as raw deterministic points on a maximum-85 scale; do not normalize it into a probability. UI and API expose `max_score=85`.
- **Reason:** Actual runtime component caps are 20 + 30 + 20 + 15; Isolation Forest has zero runtime weight. Normalizing would obscure the existing points and require retuning all tier thresholds.
- **Decision:** Exact duplicates have a High tier floor; strong cloning and repeat billing have a Medium floor. Floors do not alter raw points and are explained in evidence. (2026-10-24: the Medium floor additionally covers unbundling alongside the tier-band recalibration, matching the engine's own "strong relational evidence" narrative.)

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
