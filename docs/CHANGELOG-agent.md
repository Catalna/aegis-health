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

## Classifier recall upgrade: grouper-consistency features (2026-10-24)

- User target: raise anomaly recall from ~55% into the 60–70% band. First an **operating-policy sweep** (`scripts/sweep_operating_policy.py`; policies selected on validation, single test read) quantified the policy-only ceiling: forcing validation target recall 0.80 still yields test recall 0.585 @ precision 0.724 — the wall is **per-type blindness**, mainly upcoding (recall ≈0.009; 14.3% of positives).
- Feature development answered the wall: 3 grouper-consistency features from existing columns (`ina_grouper_severity`, `grouper_severity_gap`, `cost_to_sev_factor_ratio`; see DECISIONS entry) + unit tests (7 in `test_v2_features.py`). Retrained seed 42 on the identical dataset (same config SHA); promoted to canonical `backend/models_trained/synthetic_v2/`, legacy 25-feature artifacts preserved at `synthetic_v2_25feat_legacy/` (gitignored).
- New canonical headline (test natural, synthetic demonstrator): **AP 0.6258 → 0.7259** (group bootstrap CI 0.7037–0.7464), ROC-AUC 0.9178 → 0.9446, operating point threshold 0.3173: **recall 0.5500 → 0.6793**, precision 0.7948 → 0.8049, F1 0.6501 → 0.7368; alerts 1,266/50,000 (2.53%); ECE 0.0163 → 0.0058; enriched AP 0.8462 → 0.8905; OOD AP 0.6078 → 0.7269. Upcoding: AP 0.0156 → 0.0899 with recall 0.009 → **0.651**; recall per type at the operating threshold documented in `docs/EVALUATION_REPORT.md`.
- Figures regenerated (8 throwback PNGs via `scripts/visualize_evaluation.py`): testing confusion TP=1,019 FP=247 FN=481 identical to the new operating point; PR legend AP=0.7259; validation logloss 0.1156@1 → 0.0601@306. `docs/EVALUATION_REPORT.md` rewritten with the v3 feature-set section, per-type recall table, and updated limitations.
- Multi-seed replication (n=5) rerun with the new feature set: test AP **0.7153 ± 0.0104** [0.7038–0.7259] (was 0.6086 ± 0.0102); operating recall **0.6667 ± 0.0122** [0.6533–0.6793] — every seed clears the 60% target; precision 0.8095 ± 0.0199; enriched AP 0.8872 ± 0.0051; OOD 0.7069 ± 0.0254; upcoding AP 0.0967 ± 0.0164 (was 0.0145 ± 0.0014). Aggregates committed in `docs/EVALUATION_MULTISEED.md` + `.json`.

## Deck PPTX dihapus; 8-PNG figure set menjadi satu-satunya visualisasi (2026-10-24)

- User decision: hentikan jalur update/rebuild deck presentasi; seluruh folder `deck_redesign/` dihapus dari repo (2 PPTX + 2 PDF proposal, deck alur kerja, renderer Python `build_full_deck.py`/`build_slide.py`/`deck_kit.py`, render PNG s01–s18 + preview). Alasan: deck menyandang angka evaluasi mini-run lama (3.464 sampel, "Precision@50 0,5, prevalensi 32%", "MAPE 5,2%") yang tidak lagi merepresentasikan model; memelihara dua sumber angka kontraproduktif di depan juri.
- One valid deliverable: the 8 throwback PNGs in `docs/figures/` regenerated from the promoted seed-42 model (AP 0.7259 / recall 0.6793 @ precision 0.8049, threshold 0.3173) — testing confusion identical to the operating point (TP=1,019 FP=247 FN=481); these images are presentation-ready (video/proposal material).
- `python-pptx` uninstall check: venv cukup bersih; tidak ada perubahan `backend/requirements.txt`.

## Runtime-ranking eval, Fase 3.4 (2026-10-24)

- New committed tooling: `scripts/runtime_ranking_eval.py` (deterministic runtime path in-process via `evaluation.pipeline.score_claims`, no LLM; configurable enriched sample; re-render mode from saved JSON). First run: 700-claim labeled slice (50 per anomaly type + 350 normal, prevalence 50% documented as enriched — budget metrics are prevalence-conditional), test split seed-42 as the canonical run.
- Headline finding — **runtime lags the candidate by 30 pp AP on the identical slice: runtime 0.5964 vs candidate 0.9158** (candidate stays a candidate; runtime tiers unchanged). Runtime budgets: precision@10% 0.657 with recall@10% only 0.131; recall reaches 0.351 at a 30% slice budget.
- **Tier compression exposed:** 609/700 medium (87%), e.g. normals median score 35.0 = same value as most anomaly types; only phantom_billing (median 48) and upcoding (46) separate. This is hard evidence for the leftover Fase 2 item (tier-threshold/component recalibration).
- Relational flags almost never fire on v2: repeat/cloning ratios 0.00 for every type including `repeat_billing` and `cloning` slices (production 45-day window vs v2 repeat gap 46–60 days; v2 cloning pairs do not meet the offline investigation-candidate thresholds); only the unbundling slice shows repeat 0.26 / unbundling 0.08. The runtime's separating power on this slice came from the financial component (all 700 rows classified via `xgboost_model`) plus clinical severity flags — recorded as the honest diagnosis of where to invest next.
- Latency of the deterministic path (post one-time 18.3 s financial-model+SHAP build): **p50 75 ms, p95 845 ms** per claim — clean separation from the e2e 7.3 s p50 that includes LLM narration.
- Scope notes recorded in the doc: relational context = sample only; exact-duplicate `high` floor is DB-gated (unreachable offline); v1 tariff table covers 10 diagnosis families so most v2 diagnoses fall back to the z-score financial path (known limitation).
- Artifacts: `docs/RUNTIME_EVALUATION.md` committed; JSON payload at `backend/models_trained/runtime_ranking_eval.json` (gitignored).

## Fase 2 — Tier-band recalibration on validation (2026-10-24)

- Calibration script `scripts/calibrate_tier_bands.py`: pre-registered discipline written in the docstring — score a 700-claim validation slice (50/type + 350 normals) through the deterministic runtime path (`pipeline.score_claims`, no LLM); grid from **observed score values** (rule v3 after two infeasible pre-registered windows against the quantized score distribution); select band maximizing alert precision inside the constraint window, fallback = minimize `|alert_frac − 0.20|`; **test read once** for transfer verification.
- Finding: runtime scores clump at 35 (136 normal/99 anomaly) and 48 (111/123); zero normals ≥ 48.7 in validation; the pre-registered 10–22% alert window is empty (alert share jumps 0.80 → 0.46 → 0.049 between clumps) — fallback applied and documented.
- Chosen bands: **medium ≥ 48.7, high ≥ 55.0**. Test verification: alert 5.7% at precision 0.800 (old bands: 88.9% at 0.510); high tier 18 claims, precision 1.000 (13 unbundling + 5 upcoding); tier split 660 low / 22 medium / 18 high (was 609 medium / 78 low / 13 high).
- Code lands in the same commit: `risk_engine.py` bands 55.0/48.7 + `pipeline.py::_priority_tier` mirror; relational Medium floor extended to **unbundling** (aligns with the engine's own evidence-note narrative; keeps unbundling above the new medium threshold). Report `docs/TIER_CALIBRATION.md`, JSON artifact `backend/models_trained/tier_band_calibration.json` (gitignored), `docs/MODELS.md` §5.2 + `docs/Architecture.md` updated; `RUNTIME_EVALUATION.md` carries a provenance note on the measured-with-default-bands distribution.
- Honest caveat recorded: alert recall on the enriched slice drops to ~9% — the tier is a capacity-triage label, not the detection instrument; detection stays with runtime ranking (AP 0.5964) and the candidate ML; engine recall recovery is the repair backlog (repeat window 46–60 days, v2 cloning thresholds, v1 tariff map).

## Demo seeding & runbook (Fase 6, 2026-10-24)

- Tooling: `scripts/demo_seed.py` — 220 curated synthetic claims seeded via the production flow only (POST → FIFO worker → orchestrator → LanceDB; no direct DB writes), `scripts/demo_reset.py` (5-table truncate + LanceDB wipe), `docs/DEMO_RUNBOOK.md` (prereqs, one-cycle reset→seed→verify, ~8-minute storyboard, degradation show, pre-record checklist, troubleshooting).
- Seed design honesty: costs calibrated offline against the in-process runtime financial model (`claimed = predicted × multiplier`) so the financial agent's deviation is deterministic per scenario; relational flags (repeat/cloning/unbundling/exact-duplicate) are engineered via content design (patients, providers, code sets, ≤45-day windows) — no runtime label-based overrides, every tier is the engine's honest raw output incl. floors. `--dry-run` simulates the full engine with the repo's own functions before any POST.
- Dry-run verified before seeding: 220/220 targets hit, "peringatan flag di luar desain: bersih". Scenario families: 90 normals, 18 unbundling fragments (6 groups × 3, non-high-cost shared procedures), 14 repeat pairs (incl. UPC repeat overlap), 10 near-window pairs, 12 cloning pairs, 4 exact duplicates, 32 upcoding (16 bumped + 16 repeat overlays expecting low), 12 phantom, 16 inflated (8 clean + 8 LOS-outlier), 12 prolonged-LOS (6 low + 6 flagged).
- Live verified (siklus resi 2026-10-24): submit 220/220 (ok 220, skip 0, err 0), drain penuh
  `failed=0`; tier live **high 4 / medium 86 / low 130** = desain dry-run persis; snapshot
  per-skenario **220/220 sesuai** (10/10 grup); status processed 130 / review_required 90;
  exposure agregat Rp 462,3 jt. Tag DU diselaraskan `expect_high` → `expect>=high`
  (parser harapan sebelumnya tak membacanya); `--dry-run` & snapshot sepenuhnya hijau.

- Hash commit gelombang ini: `8dd1406` (bersih: hapus mockup + skrip legacy + tambah README) dan `6e5d516` (tooling seed/reset + RUNBOOK + DECISIONS + ENTRY CHANGELOG).

## Windows setup README + Docker removal (2026-10-25)

- README rewritten as the canonical end-to-end local Windows guide (clone →
  PostgreSQL `CREATE DATABASE aegis_health_db` → `.env` from a credential-free template →
  venv + requirements → `npm ci` → runtime models → `start.bat` → health check →
  optional synthetic seed/reset → stop; troubleshooting table included).
- `start.bat` made repository-location independent (`%~dp0`, direct
  `venv\Scripts\python.exe` call, no hardcoded developer path).
- `.env.example` converted to a local Windows template with `<password-lokal>`
  placeholder; no real credentials, no Docker-only hostnames.
- Docker deployment setup removed: `compose.yaml`, `DOCKER.md`, `.dockerignore`,
  `deploy/backend.Dockerfile`, `deploy/frontend.Dockerfile`, `deploy/nginx.conf`;
  active `docs/Architecture.md` entry dropped (historical plan text kept).
- Verification: README link check green; no active Docker references in tracked
  files; frontend production build green; no runtime code touched (`/api/health`
  not re-run — stack offline).

## Commits made

- `a4585d1` — deterministic relational tier floors.
- `f720a64` — explicit raw 85-point risk scale.
- `6e6a870` — synthetic v2 generator/validator.
- `5bf7a9d` — signed benchmark deviation and upward exposure.
- `b4d569d` — native XGBoost training/evaluation path.
- `fbb413d` — synthetic v2 validation and training report.
- `244a1ab` — classification metrics and PNG evaluation figures.
- `a3968e3` — relational classifier features with validation-only tuning.
- `2974bf5` — Gemini schema coercion + thread-offloaded SHAP + throwback evaluation figures.
- `d069dad` (re-rebased) — classifier features 25→28 (grouper-consistency trio); test AP 0.7259, recall 0.6793.
- `72391b8` — multiseed aggregate rewrite (n=5, new features; AP 0.7153 ± 0.0104).
- `2682368` — deck artifacts removed (single-visual policy: docs/figures PNGs only).
- `1cd0762` — Fase 3.4 runtime ranking evaluation (`scripts/runtime_ranking_eval.py` + `docs/RUNTIME_EVALUATION.md`).
- `20b38d2` — (teman dev) dashboard redesign + `GET /api/analytics/trend` (dipull; basis rebase).
- `68ab4b2` — spesifikasi windows README + penghapusan Docker (gate persetujuan).
- `48fd161` — plan implementasi 6-task untuk pekerjaan ini.
- `6cf5a98` — drop entri compose.yaml dari tree arsitektur.
- `80e424b` — `.env.example` template lokal Windows (kredensial placeholder).
- `3bb875e` — `start.bat` portabel (`%~dp0`).
- `7aa1309` — README ditulis-ulang sebagai panduan setup end-to-end.
- `23b5cbe` — hapus setup penerapan Docker (6 berkas).

Latest verification: **334 passed / 2 skipped** (after tier-band recalibration); live demo cycle 2026-10-24 — reset → seed 220/220 → drain `failed=0` → per-scenario snapshot **220/220** (tier high 4 / medium 86 / low 130). Full smoke E2E on the live stack passed earlier (see the E2E section above). Frontend build passed earlier with the chunk-size warning above. Docs/config verification 2026-10-25 (README rewrite + Docker removal): README link check green, active Docker refs zero, frontend build green (same chunk warning), `/api/health` not re-run (stack offline). Phases 4–7 and the remaining Fase 0–3 acceptance items are not claimed complete.
- b486135 � catatan changelog pekerjaan README/Docker (2026-10-25).
- 4b7dbae � README restyle mengikuti layout wumpus (badge/daftar isi/mermaid/tabel skor/dokumentasi/batasan); isi setup tetap akurat.

## 2026-10-26 — Gelombang data riil BPJS (Langkah 1-6, post-model roadmap)

- Eksekusi enam langkah eksploitasi sampel BPJS Reguler 2025 (ackend/app/data/2025/, gitignored) tanpa menyentuh skoring runtime (freeze 1-Nov tetap utuh); promosi hanya lewat gate A3.
- L1 profiling: scripts/bpjs/profile_reguler.py + docs/BPJS_SAMPLE_PROFILING.md (5 file, 10,5 jt baris; temuan: 99,9% tagih==verifikasi, 899 kode INACBG dgn dominasi hemodialisis 47,1%, SA 0% = gap ICU, LOS p50=0).
- L2 peer baseline real: scripts/bpjs/extract_peer_baseline.py + docs/BPJS_PEER_BASELINE.md (main/fallback/kelas; fallback nasional menutup 100% baris; sel dense = tabel tarif implisit).
- L3 spesifikasi A1/A2: docs/specs/2026-10-26-A1-A2-intake-attributes.md (no-new-input, jalur J1/J2/J3, admisi AD1-AD3, adapter tipis dikunci saat file E-Klaim riil pertama).
- L4 retraining benchmark: scripts/bpjs/retrain_cost_benchmark.py + docs/BPJS_RETRAINING_REPORT.md (split subjek crc32; A runtime legacy MAPE 1285% R2 -0.61; B kontrak legacy retrain 51,5% R2 0.43; C kontrak v2+konteks **MAPE 8,59% R2 0.8184, within-10% 80,1%**; strata dialysis medAPE 1,58% R2 0,10; 7/9 input hilang kini riil; ICU+ventilator gap konstanta 0).
- L5 visual final (arsip, digantikan 2026-10-26): visual benchmark biaya A/B/C; artefak sumber tetap di `backend/app/data/analysis/` (gitignored).
- L6 aturan data riil: docs/DECISIONS.md + entri 2026-10-26 (no-PII in git, subset wajar + split subjek + konstanta gap eksplisit, force LLM_PROVIDER=ollama untuk LLM yang menyentuh data riil, freeze gate A3).
- Log status semua langkah: docs/specs/2026-10-25-post-model-roadmap-design.md paragraf 8.

## 2026-10-26 — Gelombang data riil BPJS lanjutan (Langkah 7-9, disetujui user)

- L7 cek kelayakan per-faskes: `scripts/bpjs/dump_labels.py` + `docs/BPJS_FASKES_ID_CHECK.md` (verdict: FKTP & FKRTL TIDAK menyimpan ID faskes/dokter → profil per-RS (C1) tertunda ke jalur A1 payload; analisis tetap stratum-level).
- L8 profil perilaku: `scripts/bpjs/profile_behavioral.py` + `docs/BPJS_BEHAVIORAL_PROFILING.md` + artefak `profile_behavioral.json` (FKRTL gap p50=8 d, FKTP p50=24 d, dialisis p50=20 d dengan share band 12-16 d hanya 13,84% → asumsi dwi-mingguan 14 d tidak valid langsung; rujukan FKP02 ada di 58,96% FKRTL dan 100% ter-match ke FKTP; hari-sama FKTP→FKRTL 7,65%; switch stratum FKTP 8,71%) → threshold relasional era-sintetis (repeat window 46-60 d) harus dikalibrasi per-stratum di gate A3.
- L9 pra-gate scan sinyal: `scripts/bpjs/scan_peer_signal.py` + `docs/BPJS_PEER_SIGNAL_SCAN.md` + artefak `peer_signal_scan.json` (1.697.588 klaim wajar; **92,00% dalam band r 0,9-1,1**; dialisis 99,3% = terkunci-tarif → komponen deviasi harus di-nol-kan untuk stratum terkunci; threshold naik 1,25 → 32.714 klaim = 1,93% = titik operasional antrean; flag berkonsentrasi di sel sev-2 bedah/kel-I). Framing tegas: karakteristik operasi sinyal, BUKAN validasi fraud (tanpa label).
- Artefak JSON di `backend/app/data/analysis/` (tetap gitignored); runtime/demo/skoring tidak disentuh (freeze 1-Nov utuh); log eksekusi: `docs/specs/2026-10-25-post-model-roadmap-design.md` §8 baris 7-9.
- Komit: `fcf5edd` (L7), `36bc3a4` (L8), `49474b8` (L9).

## 2026-10-26 — Gelombang pengembangan model (Langkah 10-12, closing ML-development)

- Pernyataan user dikonfirmasi: masih di tahap develop ML; dilanjutkan sampai selesai. Keputusan arsitektur Q&A: **2 model + pilar rule-based sudah cukup** — bottleneck-nya data (ICU/vent, ID faskes, label), bukan jumlah model; "model ke-3 ML" ditolak (cadence = rule + baseline per-strata, bukan ML).
- L10 kalibrasi generator: `backend/app/data/synthetic_v2/generator.py` tambah jalur opsi `calibration` (default v2.4 murni): bucket repeat L8, cadence hard-negative dialisis L8, derau biaya = campuran terkunci-tarif 47% + invers-CDF kuantil L9; dataset kandidat v3 `data/synthetic_v2_calibrated` 257.100 klaim valid (`--calibrated`; gitignored, `data/` masuk .gitignore).
- L11 retrain kandidat v3: kontrak 28 fitur identik, seed 42 — test AP **0.6609** (CI95 grup [0.635-0.683]) vs v2.4 0.7259; ~0.73→0.66 dibaca sebagai dunia-latihan yang lebih real (44,6% pasangan ≤7 h legit; inti derau rapat), bukan degradasi; kandidat tetap ≥4× baseline aturan (0.15); fitur identitas tetap dominan (`exact_copy_group_size`). Laporan: `docs/BPJS_SYNTH_CALIBRATION_REPORT.md`; artefak `backend/models_trained/synthetic_v2_v3/`.
- L12 scan cadence per-strata: `docs/BPJS_CADENCE_SIGNAL_SCAN.md` (non-dialisis repeat p50 6 h; dialisis p50 21 h, 25% >60 h; hari-sama <0,7%) → kandidat kalibrasi pilar relasional: baseline relatif per-strata + prioritas identitas kode×faskes×tanggal di atas jendela absolut.
- Portofolio pra-gate siap untuk gate A3 (per-strata, `MODELS.md §2.6`): biaya-C + klasifier v2.4 + klasifier v3. Runtime/demo/skoring tidak disentuh; freeze 1-Nov tetap utuh.
- Komit: `c3a1cf6` (L10), `02f1595` (L12), `173f323` (L11). Penutup gelombang: suite backend 331 passed / 2 skipped / **3 failed** — ketiganya `test_frontend_contract` (berkas frontend terakhir disentuh `c3b4201` 2026-10-23, sebelum gelombang; tidak ada artefak gelombang yang menyentuhnya). Tes lingkup gelombang (generator/fitur/trainer/multiseed) **29 passed penuh**.

## 2026-10-28 - Spec maksimisasi flow agentic (kontrak envelope terpadu + checker generik + observability)

- Keputusan pemilik: hasil review flow `orchestrator.py` (Phase 0-4, provenance, fallback, generation-lock) dituangkan ke spec baru `docs/specs/2026-10-28-flow-maximization-design.md` (docs-only, aman freeze). Kesimpulan: tulang punggung kokoh, tidak ditukar; lever = **kontrak + checker + observability**, bukan lebih banyak agent.
- Isi inti: F1 kontrak envelope terpadu untuk 3 titik LLM runtime + Pelapor; F2 checker anti-halusinasi generik (whitelist konversi satuan, guard nama fiktif); F3 benchmark per-slot peran (slot `.env` kini warisan tak terukur); F4 koordinator portofolio deterministik (lintas-klaim, prioritas skor x dampak); F5 flow health digest dari data `agent_runs`; F6 prefix-cache Ollama (opsional, ambang manfaat >=10%). Anti-sasaran eksplisit: tanpa debate/self-critique loop, tanpa PII, angka turunan data riil menunggu gate A3.
- Jadwal masuk di sela ordo roadmap (A3 -> payload A1/C1 -> integrasi Pelapor) tanpa membalik urutan; roadmap baris 18 ditambahkan.

## 2026-10-28 — Narasi "otak utama = LLM Lokal" diparalelkan ke dokumen laporan

- Keputusan pemilik: laporan menulis eksplisit bahwa otak utama inteligensi (pemahaman sinyal, sintesis lintas-agent, penulisan laporan) menggunakan **LLM Lokal** — menghindari isu privasi dan menyajikan perhitungan biaya/efisiensi/kinerja secara sengaja.
- Implementasi docs-only: `docs/AgentWorkflow.md` (LLM Backbone diganti kebijakan local-first), `docs/Architecture.md` (catatan rantai produksi resmi + status runtime yang jujur), `docs/EVALUATION_REPORT.md` (bagian baru "Lapis inteligensi di luar portfolio — LLM Lokal"). Angka yang disebut identik dengan bukti terukur internal (15–25 detik/laporan, JSON 6/6) tanpa klaim baru.
- Tidak ada kode/konfigurasi runtime yang disentuh; `docs/DECISIONS.md` sudah memuat keputusan 2026-10-27, tidak diulang.

## 2026-10-27 - Kebijakan LLM lokal-first didokumentasikan (flip runtime ditangguhkan)

- Keputusan: rantai produksi resmi = **Ollama lokal (`deepseek-r1:7b` LLM Pelapor) -> Gemini -> template deterministik**; Gemini diturunkan jadi backup + opsi pengembang (data sintetis). Alasan: privasi data kesehatan peserta (UU PDP No. 27/2022), cost/keberlanjutan (LLM di luar jalur penilaian; worst case template = Rp0 per klaim), keandalan offline faskes, audit/repro.
- Implementasi docs-only: blok komentar `.env.example`, README (Batasan), `docs/DECISIONS.md` (2026-10-27), roadmap baris 16. Nilai `LLM_PROVIDER` pada `.env` live/template TIDAK diubah - flip default runtime menjadi bagian integrasi Pelapor post-1-Nov dengan benchmark ulang wajib (3x2x6).
- Tidak ada kode/konfigurasi runtime yang disentuh (aman freeze).

## 2026-10-27 — Rebranding proyek: nama resmi AEGIS-Health (tim E-JAK)

- Keputusan pemilik proyek: nama resmi **AEGIS-Health — Agentic Risk Engine & Intelligent Surveillance for Healthcare**, dibuat oleh **tim E-JAK**; antarmuka pengguna tetap memakai nama **AEGIS**.
- Penggantian menyeluruh 37 artefak terlacak: prose & header dokumen (ekspansi nama baru), docstring/judul kode, judul FastAPI (`AEGIS-Health API`), paket frontend (`aegis-health-frontend`), string test database, `start.bat`, plus rename `docs/plans/AEGIS-Health-Strategic-Alignment-Healthkathon-2026.md`. Seluruh grep pola lama bersih.
- Database lokal direname AMAN via `ALTER DATABASE` (operasi metadata; data demo 220 klaim utuh) menjadi `aegis_health_db`; ikut diseragamkan: `.env` live, `.env.example`, `README`, default `backend/app/models/database.py` (password dev default diganti netral). Test identitas database lulus (1 passed) setelah rename.
- Tidak ada logika runtime/skoring yang berubah; laporan roadmap baris 15 ditambahkan.

## 2026-10-27 — Riset LLM pelapor lokal + desain arsitektur agent

- Benchmark A/B Ollama lokal oleh `scripts/agent/llm_bench.py` (3 fixture envelope dari artefak sumber × 2 mode × 6 panggilan terukur): `deepseek-r1:7b` dipilih sebagai LLM Pelapor tunggal — 15–25 dtk/laporan vs qwen3.5:9b 128–213 dtk (berpikir 4,5–7 rb token per panggilan), JSON valid 6/6 keduanya, gaya r1 menyusun narasi vs qwen menyalin key-value. Dugaan awal pro-qwen terbukti salah oleh data.
- Design doc `docs/specs/2026-10-27-agent-hierarchy-design.md`: koordinator deterministik di atas, LLM pelapor di daun (bukan juri), kontrak envelope JSON antar divisi, checker anti-halusinasi (menerima konversi satuan ×100×10⁶, menolak angka buatan/laporan dibuang ulang).
- Milestone roadmap baris 14. Tidak menyentuh runtime/demo (freeze utuh); implementasi ditahapkan pasca-1-Nov setelah gate A3 + payload A1. Hasil mentah benchmark gitignored di analysis.

## 2026-10-27 — Visualisasi per-model: 8 figur × 2 model (set pembanding dipensiunkan)

- Keputusan user: report visual kelola per-model tanpa grafik pembanding — 8 figur × 2 model (klasifier kandidat v3 + model biaya kandidat C) = 16 PNG di `docs/figures/`.
- Klasifier v3: `scripts/plot_classifier_v3_report.py` menghitung ulang skor dari model final + dataset training yang sama (threshold 0.3475 validation-selected dipakai seragam). Replay terverifikasi: confusion test identik operasi point report (TP 976/FP 366/FN 524/TN 48.134). Set: feature importance, label distribution, confusion train/val/test, PR, ROC, validation logloss. Dokumen per-model model 2: `docs/MODEL2_KLASIFIER_V3_REPORT.md`.
- Model biaya C: `scripts/bpjs/eval_cost_candidate_c.py` membangkitkan ulang prediksi test dari pipeline retrain (parity check LOLOS: MAPE 8.59% / medAPE 3.42% / R² 0.8184, keempat view identik `retrain_results.json`) → artefak `eval_cost_c_test.parquet` (tanpa PII) + `eval_cost_c_parity.json`. `scripts/plot_cost_c_report.py` merender 8 figur: pred-vs-aktual, distribusi APE, coverage curve, stratum metrics, sebaran APE stratum, medAPE per INACBG, feature importance, bias per desil.
- Dokumen per-model model 1: `docs/MODEL1_BIAYA_C_REPORT.md` (ringkasan test + strata + provenance fitur + 8 figur). Dokumen eksperimen/kalibrasi kini menunjuk dokumen per-model. Skrip pembanding `scripts/plot_model_portfolio.py` dihapus; wrapper `visualize_evaluation.py`/`bpjs/plot_retraining_results.py` diarahkan ke generator per-model yang sesuai.
- Revisi umpan balik user: setiap judul 16 gambar diberi awalan label model ('Model 1 · Biaya (kandidat C)' / 'Model 2 · Klasifier anomali (kandidat v3)'); judul panjang dipindah ke figure-level agar tidak terpotong. `docs/EVALUATION_REPORT.md` diubah jadi indeks portofolio (2 model + status runtime + arsip v2.4) — tidak ada model ke-3: pilar aturan itu rule-based.
- Tidak ada runtime/model/threshold yang diubah; freeze 1-Nov utuh; kandidat tetap menunggu gate A3.

## 2026-10-28 — Gelombang maksimisasi flow (F1–F5): offline di main + wiring terflag di cabang

- Keputusan eksekusi (user): takut bug krusial → penguatan **End-to-End menyeluruh** sebelum sentuh main. Struktur: main hanya menerima bagian nol-perilaku (F1–F3); seluruh wiring runtime dieksekusi tuntas di worktree cabang `flow-max` (merge pasca-1-Nov). Empat lapis proteksi: isolasi cabang, flag default-OFF (`AEGIS_FLOW_GUARD`), parity skor via suite OFF/ON, dan re-run suite penuh di kedua status flag.
- **F1 kontrak envelope** `backend/app/core/envelope.py` + 26 unit test (commit `b66fb29`): `to_envelope/is_envelope/canonical_json/envelope_digest` — fail-fast "angka harus angka", nol PII di kunci kedalaman manapun, kunci privat `_` ditolak, digest kanonik idempoten.
- **F2 checker anti-halusinasi** `backend/app/core/llm_guard.py` + 27 unit test (commit `3ec75b7`): parsing angka Indonesia deterministik (ribuan/koma-desimal/pemisah campuran), harvest target (nilai + token teks), padanan mentah atau konversi ×100/÷100/×10⁶/÷10⁶ dengan toleransi dua-desimal (0,5% rel; 0,06 abs), guard sapaan fiktif ("Enyi") + mode strict tervocab, `guard_report` (strict|numbers).
- **F3 baseline per-slot** `scripts/agent/role_bench.py`: slot warisan (REVIEW/EXPLANATION dari .env = qwen2.5:3b, fallback llama3.2:3b) vs kandidat deepseek-r1:7b, 2 peran (review_sintesis, explanation), lapis2_klinis sengaja ditunda (fixture klinis menunggu payload A1 — anti-fabrikasi). Hasil terukur (seed 42, gitignored): qwen2.5:3b melanggar angka **1×** pada peran explanation (tertangkap checker), llama3.2:3b bersih & tercepat (4,2–4,7 s), r1:7b bersih (13–20 s). Keputusan slot formal tetap pasca-gate A3.
- **Wiring di cabang `flow-max`** (tidak menyentuh main): envelope + guard generik aditif di 3 titik LLM — `review_agent` (narasi sintesis), `explanation_agent` (lapis kedua di atas validasi warisan `_validate_narrative`), `clinical_agent` Lapis-2 (evidence; kunci kode medis diizinkan via `code_keys`). Gagal checker → jalur fallback deterministik yang sudah ada (rule_fallback/template_fallback/no_data) — LLM tidak pernah "memperbaiki keluaran sendiri".
- **Bug kontrak tertangkap langsung saat wiring #1**: `env_version: 1` ternyata jadi target angka (1→×100=100) sehingga angka fiktif dekat 100 lolos checker — `harvest_numbers` kini mengecualikan kunci metadata (`env_version`, `satuan`); test regresi ditambat. Envelope versi cabang juga menerima `code_keys` untuk kode medis sah ("36.10").
- **Penyelarasan checker saat wiring #2**: validasi warisan menerima tampilan bulat ("77" untuk 77.4) sedangkan checker baru lebih ketat → `check_numbers` kini menerima kandidat display pembulatan bilangan bulat, sehingga narasi "dari 100" tetap diwajibkan dari `skala_maks` di envelope (konstanta sistem yang jujur).
- **F5 endpoint** `/api/system/agent-health` (cabang): agregat baca-saja `agent_runs` (total/fallback/error, p50/p95 durasi, distribusi model) — logika agregasi fungsi murni `core/agent_health.py` yang diuji unit tanpa DB.
- Test wiring `backend/tests/test_flow_wiring.py` (12 test): flag ON menolak angka fiktif pada ketiga titik (99.9 / LOS 99 / "1,23 juta") → fallback; flag OFF perilaku identik pre-wiring; agregator F5 murni. **Sertifikasi suite penuh dua kali di cabang: flag OFF 398 lulus / 3 gagalan lama pre-existing (test_frontend_contract) / 2 skip — IDENTIK dengan flag ON 398 / 3 / 2** → parity skor terbukti nol-regresi. Runtime main tidak berubah; rencana aktivasi: merge pasca-1-Nov + flip flag (komit `2911f70` di cabang `flow-max`).
