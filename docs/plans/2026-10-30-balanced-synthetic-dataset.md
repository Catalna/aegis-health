# Balanced Synthetic Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reproducible, separately stored calibrated dataset with 50:50 training labels, original natural evaluation splits, and per-label pattern profiles.

**Architecture:** Extend the v2 generator with an optional training-only anomaly prevalence while keeping its default behavior unchanged. A dedicated builder loads the calibrated source bundle, replaces only train with the requested generated train split, copies evaluation splits unchanged, computes profiles, validates, and writes to `data/synthetic_v2_calibrated_balanced`.

**Tech Stack:** Python, NumPy, pandas/PyArrow Parquet, pytest.

---

## File map

- Modify `backend/app/data/synthetic_v2/generator.py`: add validated `train_positive_fraction` parameter; default remains 0.03.
- Create `backend/app/data/synthetic_v2/profiling.py`: label-conditioned aggregate profiles without PII or raw row dumps.
- Create `scripts/build_balanced_synthetic_v2.py`: CLI to load source, generate train, retain evaluation splits, profile, and write new output.
- Modify `backend/app/data/synthetic_v2/io.py`: record balanced-training provenance and add profile summary to data card/schema where appropriate.
- Create `backend/tests/test_balanced_synthetic_v2.py`: reproducibility, class ratio, split immutability, profile contents, and label separation.
- Output only: `data/synthetic_v2_calibrated_balanced/` (gitignored generated Parquet/JSON/Markdown files).

### Task 1: Support configurable training prevalence

**Files:** Modify `backend/app/data/synthetic_v2/generator.py`; test `backend/tests/test_synthetic_v2.py`.

- [ ] Add optional `train_positive_fraction: float = 0.03` to `generate_synthetic_v2`; reject values outside `[0, 1]` with `ValueError`.
- [ ] Pass the configured fraction only to `_generate_split` for `train`; leave validation, test, enriched, and OOD generation at current behavior.
- [ ] Add tests that default output remains deterministic and a `dev` bundle with `train_positive_fraction=0.5` has exactly half positives (generator rounds to integer) while validation stays at 3%.
- [ ] Run `venv\Scripts\python.exe -m pytest backend/tests/test_synthetic_v2.py -q`; expect all tests pass.

### Task 2: Implement per-label profiling

**Files:** Create `backend/app/data/synthetic_v2/profiling.py`; test `backend/tests/test_balanced_synthetic_v2.py`.

- [ ] Implement `profile_labels(split: dict) -> dict` grouping claims joined by `claim_id` with labels grouped by `anomaly_type` and `scenario_family`.
- [ ] Include counts/prevalence, difficulty and confidence summaries, numeric quantiles (`patient_age`, `length_of_stay`, `cost_claimed`, `regional_base_rate`), and top category frequencies (`facility_type`, `service_type`, `diagnosis_primary`, `outpatient`).
- [ ] Add a `dev` fixture test asserting `none`, each anomaly family, and `hard_negative_*` appear, and that profile output contains aggregates only (no claim/patient/provider IDs).
- [ ] Run `venv\Scripts\python.exe -m pytest backend/tests/test_balanced_synthetic_v2.py -q`; expect initial failure then pass after implementation.

### Task 3: Build and persist the balanced bundle

**Files:** Create `scripts/build_balanced_synthetic_v2.py`; modify `backend/app/data/synthetic_v2/io.py`; test `backend/tests/test_balanced_synthetic_v2.py`.

- [ ] CLI defaults: `--input data/synthetic_v2_calibrated`, `--out data/synthetic_v2_calibrated_balanced`, `--seed 42`, `--train-positive-fraction 0.5`; call `load_synthetic_v2` and require all five source splits.
- [ ] Generate calibrated train with source profile and selected seed, then form output bundle by taking generated `train` and deep-copying source `validation`, `test`, `test_enriched`, and `ood`; set dataset version to `synthetic-v2.4.0-calibrated-balanced` and preserve source profile/metadata.
- [ ] Add `validate_balanced_bundle` checks for train anomaly rate within one-row rounding of target, every required split present, source evaluation splits exactly unchanged, and labels still separate from claims; run existing `validate_synthetic_v2` before any files are written.
- [ ] Write using `write_synthetic_v2(..., file_format="parquet")`; save aggregate profiles to `label_profile.json`, include balanced-train provenance and warning in `data_card.md`, and record fraction/source path/seed in `schema.json`.
- [ ] Test with `dev` source: exact evaluation split equality, 50:50 train, label/profile files written, and repeat seed yields identical train IDs/labels. Test the CLI's missing-input error returns nonzero without creating output.
- [ ] Run `venv\Scripts\python.exe -m pytest backend/tests/test_balanced_synthetic_v2.py backend/tests/test_synthetic_v2.py -q`; expect pass.

### Task 4: Generate and verify the standard output

**Files:** Generated output in `data/synthetic_v2_calibrated_balanced/`; no source files changed beyond above.

- [ ] Run `venv\Scripts\python.exe scripts\build_balanced_synthetic_v2.py --input data\synthetic_v2_calibrated --out data\synthetic_v2_calibrated_balanced --seed 42 --train-positive-fraction 0.5`.
- [ ] Run `venv\Scripts\python.exe scripts\validate_dataset.py --input data\synthetic_v2_calibrated_balanced`; expect status `valid` and all natural train/validation/test checks pass.
- [ ] Independently compare each evaluation claims/label table semantically with source after loading; confirm train contains 150,000 claims and 75,000 positive / 75,000 normal labels, label files contain no input features, and profile lists all seven anomaly types plus hard negatives.
- [ ] Run full backend tests with `venv\Scripts\python.exe -m pytest backend/tests -q`; report any unrelated pre-existing failures rather than masking them.
