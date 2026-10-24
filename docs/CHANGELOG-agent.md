# Agent Execution Changelog — Planning.md (Fase 0–3)

Scope requested: execute through ML training. Phases after training (BPJS sample preparation, remaining product/demo work) were not executed.

## Fase 0 — Baseline (partial)

- Full backend suite: **314 passed, 2 skipped** (`venv` Python 3.10.11, `python -m pytest -q`).
- Frontend production build: passed; Vite warns the minified JS chunk is larger than 500 kB.
- `python -m compileall -q backend scripts`: passed.
- Existing P1 v1 evaluator ran to a JSON artifact in the approved temp directory; it was not used as a v2 comparison baseline.
- End-to-end smoke was not run: `GET http://localhost:8000/api/health` was refused because no API service was listening. PostgreSQL/SSE/human-decision flow is therefore unverified in this session.
- `asyncpg` and `sse-starlette` are already present in `backend/requirements.txt`.

## Fase 1 — Synthetic v2 (implemented; domain validation partial)

- Added versioned generator `synthetic-v2.4.0-demonstrator`, separate label files, schema/data-card generation, CSV/Parquet output, and strict dataset validation.
- Standard natural splits: 150,000 train + 50,000 validation + 50,000 test = **250,000**. Additional test sets: 2,100 enriched + 5,000 OOD = **257,100 total generated rows**.
- Standard Parquet generation, seed 42, ran twice (67.50 s and 66.39 s); output-file SHA-256 comparisons had no differences.
- `scripts/validate_dataset.py` passed on the standard Parquet output. Group leakage, separate labels, synthetic ID checks, and normal-distribution KS checks all passed.
- Data and trained model artifacts were kept outside source control / in ignored paths; no real participant data was used.
- Limitations: the 188 ICD-10-style category values and INA-CBG-like codes/tariffs are demonstrators, not an officially audited catalogue/grouper/tariff table. Large profile and multi-seed generation were not run.

## Fase 2 — Score semantics (partial)

- Runtime score is explicitly raw `0–85` points (`max_score=85`), not a probability; Assessment/Investigation UI and docs use that scale.
- Strong cloning/repeat evidence floors tier at Medium; exact duplicate floors at High, with deterministic evidence text.
- Model and fallback financial paths now preserve signed deviation, calculate separate upward exposure, and use the same absolute-deviation anomaly formula.
- Similarity formula and implementation path were synchronized in `docs/MODELS.md`.
- Remaining: capacity-based tier threshold calibration on validation and separate UI provenance labels for domain-backed rules vs prototype signals.

## Fase 3 — Model training/evaluation (partial)

- Added native XGBoost v2 training for Parquet/CSV. Cost regressor trains on normal train claims only; feature ablation is selected on validation; held-out test is evaluated once. The classifier remains a candidate and is not runtime.
- Standard run: seed 42, 150k/50k/50k. Results are in `docs/EVALUATION_REPORT.md`; all results are synthetic-only.
- Trained model files and JSON/Markdown artifacts are in the ignored local path `backend/models_trained/synthetic_v2/`. They are not promoted over the legacy runtime model.
- The evaluation includes random, benchmark-deviation, and logistic-rule baselines; aggregate group-bootstrap CIs and enriched/OOD slices. Natural per-type results expose poor slices including cloning and upcoding.
- Classifier v2 adds six split-level relational features (duplicate group keys, per-patient minimum gap, train-normal expected-LOS ratio) and two supported-code flags on top of the 19 per-claim features; hyperparameters are chosen on validation only (depth 5 × scale_pos_weight 3.0, early stopping 50 rounds, 400-round cap), then evaluated once on test.
- Test results: AP 0.6258 (was 0.5480 before relational features), ROC-AUC 0.9178, operating point F1 0.6501 with precision 79.48% and recall 55.00% at threshold 0.5601; OOD stress AP 0.6078. `exact_copy_group_size` is the highest-gain feature, which finally makes cloned claims rankable (AP 0.0610 vs 0.0039 previously).
- Trade-off noted in the report: unbundling and repeat-billing slice APs moved down (0.5731/0.1753) because flagged groups now contain the designed legit readmission/duplicate hard negatives; repeat-billing AP is capped around the designed tie-group prevalence (~0.18).
- Regressor test metrics: MAPE 12.83%, MedAE Rp641,852, MAE Rp863,859, RMSE Rp1,177,734, R² 0.8640, upper-bound coverage 90.18%. Coverage falls to 79–85% in the highest predicted-cost deciles.
- Ten PNG figures are written to `docs/figures/` and embedded in `docs/EVALUATION_REPORT.md`; the trainer no longer emits an HTML page.
- Remaining: at least five independently regenerated seeds, grouped CIs for every natural-test slice, broader runtime-ranking evaluation, and investigation of low-performing anomaly families.

## Artifact cleanup & promotion decision (2026-10-24)

- User request "delete the old models, use the new ones" was investigated, not executed blindly. The v2 regressor needs nine source inputs (`patient_age`, `outpatient`, `icu_indicator`, `ventilator_used`, `surgical_indicator`, `facility_type`, `facility_class`, `region`, `regional_base_rate`) that do not exist in the runtime `ClaimInput` schema or DB; a file swap would feed neutral defaults far outside the training distribution.
- Decision: runtime keeps `backend/models_trained/xgboost_regressor.json` (Financial Agent) and `isolation_forest.pkl` (Fraud Agent). The synthetic v2 models remain candidates; promotion requirements are documented in `docs/MODELS.md` §2.6.
- Deleted `backend/models_trained/xgboost_classifier.json` (legacy v1 classifier, 311 KB): grep confirmed no runtime agent, evaluation pipeline, or test loads it; only `train_xgboost.py` writes it and can regenerate it on demand.
- Kept `evaluation_results.json` and `p1_evaluation_results.json`: they are read by API evaluation endpoints in `app/api/main.py`.
- Fixed a stale artifact name in `docs/MODELS.md` §3.1 (Isolation Forest file is `isolation_forest.pkl`, trainer confirmed; doc said `.joblib`).

## Commits made

- `a4585d1` — deterministic relational tier floors.
- `f720a64` — explicit raw 85-point risk scale.
- `6e6a870` — synthetic v2 generator/validator.
- `5bf7a9d` — signed benchmark deviation and upward exposure.
- `b4d569d` — native XGBoost training/evaluation path.
- `fbb413d` — synthetic v2 validation and training report.
- `244a1ab` — classification metrics and PNG evaluation figures.
- `a3968e3` — relational classifier features with validation-only tuning.

Latest verification: 320 passed / 2 skipped; frontend build passed with the chunk-size warning above. Phases 4–7 and the remaining Fase 0–3 acceptance items are not claimed complete.
