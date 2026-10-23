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
- Classifier operating point (threshold 0.2396 fitted on validation, frozen before test): accuracy 97.97%, precision 80.25%, recall 42.80%, F1 0.5583, specificity 99.67%, balanced accuracy 71.24%, MCC 0.5775, ROC-AUC 0.8488, Brier 0.0180, and ECE 0.0039 on 50,000 test claims.
- Regressor test metrics: MAPE 12.83%, MedAE Rp641,852, MAE Rp863,859, RMSE Rp1,177,734, R² 0.8640, upper-bound coverage 90.18%. Coverage falls to 79–85% in the highest predicted-cost deciles.
- Ten PNG figures are written to `docs/figures/` and embedded in `docs/EVALUATION_REPORT.md`; the trainer no longer emits an HTML page.
- Remaining: at least five independently regenerated seeds, grouped CIs for every natural-test slice, broader runtime-ranking evaluation, and investigation of low-performing anomaly families.

## Commits made

- `a4585d1` — deterministic relational tier floors.
- `f720a64` — explicit raw 85-point risk scale.
- `6e6a870` — synthetic v2 generator/validator.
- `5bf7a9d` — signed benchmark deviation and upward exposure.
- `b4d569d` — native XGBoost training/evaluation path.
- `fbb413d` — synthetic v2 validation and training report.
- `244a1ab` — classification metrics and PNG evaluation figures.

Latest verification: 314 passed / 2 skipped; frontend build passed with the chunk-size warning above. Phases 4–7 and the remaining Fase 0–3 acceptance items are not claimed complete.
