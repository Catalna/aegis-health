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

## LLM priority swap: Google AI Studio primary, Ollama backup (2026-10-24)

- `llm_client.py`: default provider `LLM_PROVIDER` flipped to `gemini` (Google AI Studio); added automatic cross-provider cascade in `structured_completion` via `_run_llm_with_fallback` (Gemini → Ollama → agent-level deterministic template). Both fail → `LLMError` reporting each provider's note. Provider choice is recorded in an asyncio-safe ContextVar; `resolve_model_name()` keeps `model_used`/`generated_by` provenance honest.
- Agents (clinical/review/explanation) now report the model that actually served the call (e.g., `gemini-2.0-flash` when Gemini answered; requested Ollama model when fallback ran).
- `.env` / `.env.example`: `LLM_PROVIDER=gemini`, empty `GEMINI_API_KEY=` placeholder (user pastes their Google AI Studio key); without a key or internet the cascade silently uses Ollama, so offline demo mode still works. Policy comment added: switch to `LLM_PROVIDER=ollama` before processing any real JKN participant data.
- Docs updated: `MODELS.md` §6.1/6.2, `PRD.md` NFR-2, `Architecture.md` client table + diagram, `AgentWorkflow.md` LLM backbone, `DECISIONS.md` (context/options/constraints).
- Tests: 5 new cascade tests in `test_llm_client.py` (chain order, primary succeeds, fallback to Ollama, all-fail raises, explicit provider skips cascade); targeted agent suites passed (75).

## Multi-seed replication, n=5 (2026-10-24)

- New tooling: `scripts/run_multiseed.py` (per seed: regenerate the standard dataset, then train; deterministic datasets are reused if present; reports go to `backend/models_trained/synthetic_v2_multiseed/seed{N}/` and never touch the canonical docs report) and `backend/app/ml/multiseed_summary.py` (aggregates headline classifier/regressor metrics, per-type AP/F1, stress slices, baselines, and per-seed selections into mean ± sample stdev + min–max), with 5 unit tests in `test_multiseed_summary.py`.
- Trainer CLI: `--report` default changed to `None` — the figures/canonical report path must be passed explicitly, so replication runs cannot silently overwrite `docs/EVALUATION_REPORT.md`.
- Ran seeds 43–46 (full regeneration, validator passed, distinct dataset config SHA-256 per seed) and reused the recorded seed-42 run → n = 5 replication reports. Aggregate committed as `docs/EVALUATION_MULTISEED.md` + `docs/EVALUATION_MULTISEED.json`.
- Headline (test natural, synthetic demonstrator): AP **0.6086 ± 0.0102** [0.6007–0.6258]; ROC-AUC 0.9085 ± 0.0119; operating F1 0.6376 ± 0.0077 [0.6305–0.6501]; enriched AP 0.8526 ± 0.0053; OOD AP 0.5982 ± 0.0304; regressor MAPE 12.86% ± 0.09, R² 0.8628 ± 0.003. Baselines: benchmark-deviation 0.1589 ± 0.0068, logistic rule flags 0.1678 ± 0.0047, random 0.0300.
- Honest read: the seed-42 headline (test AP 0.6258) is the top of the 5-seed range; a typical run lands ≈ 0.60–0.61. Each seed re-selected hyperparameters on its own validation — 4 of 5 seeds picked `scale_pos_weight` 1.0 while seed 42 picked 3.0; the selection *procedure* was replicated, not a single frozen config (freezing it across regenerated datasets would be tuning against the test set).
- Per-type ordering is stable across seeds: unbundling 0.586 ± 0.019 ≫ repeat_billing 0.164 ± 0.015 > phantom 0.099 ± 0.005 > inflated 0.072 / cloning 0.065 / prolonged 0.051 (± ~0.005) > upcoding 0.0145 ± 0.0014 — stably the worst slice, confirming the known gap.
- Per-seed trained model files stay gitignored under `models_trained/`; the committed evidence is the aggregate Markdown + JSON.

## E2E verification & runtime reliability fixes (2026-10-24)

- First full smoke E2E pass on a live stack (PostgreSQL :5432 + API :8000 + Ollama :11434): deterministic hard-reject of corrupted admission/discharge dates (`failed` + safe message), a normal claim completes the FIFO queue path to `low_priority` with a stored verifier decision, and duplicate intake returns 409. `scripts/smoke_test.py` passes end-to-end.
- Found and fixed a cascade-breaking bug (Gemini could never serve): `GeminiClient` deliberately sends list fields as strings in `responseSchema`, but `_validate_or_raise` never parsed them back — every structured call with a list field failed pydantic validation 3× (burning network retries), then the fallback-log `print()` containing '→' raised `UnicodeEncodeError` on the Windows cp1252 console *inside the cascade exception handler*, aborting the loop before Ollama and dropping every call to the template. Fixes: `_coerce_for_schema()` (string→list via JSON-list / comma / newline; one shared point used by both clients) and `_console_safe()` ASCII-degrading print. 3 regression tests added to `test_llm_client.py`.
- Verified live against the real API: provider=gemini, `model_used=gemini-flash-lite-latest`, 2.26 s, list fields coerced correctly.
- Found and fixed a severe event-loop blocker: `analyze_financial` ran SHAP `PermutationExplainer` synchronously inside the coroutine (19–49 s/it × 2 ≈ 38–100 s per claim), freezing ALL API requests during every analysis. The whole financial computation now runs via `asyncio.to_thread`; the live log shows HTTP 200 responses continuing mid-SHAP.
- Latency probe (6 sequential normal claims through the queue worker, POST→terminal): claim 1 is 60.7 s one-time (xgboost/SHAP explainer build), claims 2–6 p50 **7.29 s** (4.7–10.7 s) — faster than the pre-fix ~10 s calls that wasted 3 Gemini retries. `agent_runs` provenance: review_agent=success/gemini-flash-lite-latest. explanation_agent=template for low tier BY DESIGN (clean-claim narration stays deterministic); a medium-tier probe (score 43.0, review_required, 8.5 s) confirmed explanation_agent=success/gemini-flash-lite-latest.
- Auditability verified directly in PostgreSQL per claim: 6 `agent_runs`, 2 `audit_logs`, 1 `human_decisions`.

## Throwback figure reset (2026-10-24)

- User request: regenerate the evaluation visuals in the style of the earlier ML report document set — 8 plain-matplotlib 960×720 charts (feature importance, outcome distribution, train/val/test confusion matrices, testing PR curve with AP legend, testing ROC with AUC legend, validation log loss per boosting round) — and delete the previous 10-figure set to avoid confusion.
- Added committed script `scripts/visualize_evaluation.py` (rerunnable; defaults point at the seed-42 dataset directory, overridable via args). Deleted old `figures/01..10_*.png`; rewrote the `docs/EVALUATION_REPORT.md` Figures section to the new set with a provenance paragraph (threshold 0.5601 chosen on validation, applied uniformly).
- Sanity: recomputed Testing confusion [TN 48287, FP 213, FN 675, TP 825] is identical to the recorded operating point; PR AP 0.6258 and ROC-AUC 0.9178 match the report; validation logloss 0.2165 @ round 1 → 0.0779 @ 374. `matplotlib==3.10.9` added to `backend/requirements.txt`; all images synthetic-demonstrator-only.

## Commits made

- `a4585d1` — deterministic relational tier floors.
- `f720a64` — explicit raw 85-point risk scale.
- `6e6a870` — synthetic v2 generator/validator.
- `5bf7a9d` — signed benchmark deviation and upward exposure.
- `b4d569d` — native XGBoost training/evaluation path.
- `fbb413d` — synthetic v2 validation and training report.
- `244a1ab` — classification metrics and PNG evaluation figures.
- `a3968e3` — relational classifier features with validation-only tuning.

Latest verification: 333 passed / 2 skipped; full smoke E2E on the live stack passed (see the E2E section above). Frontend build passed earlier with the chunk-size warning above. Phases 4–7 and the remaining Fase 0–3 acceptance items are not claimed complete.
