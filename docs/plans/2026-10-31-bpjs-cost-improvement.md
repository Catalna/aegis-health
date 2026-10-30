# BPJS Cost Model Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare honest post-grouper, pre-verification cost estimators on a subject-disjoint historical/temporal evaluation and report accuracy and deployment gates.

**Architecture:** Reuse the existing BPJS loader and split, exclude visits not discharged before the training cutoff, fit hierarchical tariff statistics using only fit labels, and cross-fit statistics for fit participants. Select models using validation only, score the reused late-2024 test once, and store only aggregate metrics/models offline; do not change runtime or expose identifiers.

**Tech Stack:** pandas, NumPy, XGBoost 3.2, pytest, BPJS Stata sample.

---

### Task 1: Tariff context and temporal safety

**Files:** Create `scripts/bpjs/cost_improvement_utils.py`; test `backend/tests/test_bpjs_cost_improvement.py`.

- [x] Write a failing test: two claims from one participant share a fold, a held-out participant cannot contribute to her own tariff feature, and a visit discharged on/after cutoff is excluded from fit.
- [x] Run `venv\Scripts\python.exe -m pytest backend/tests/test_bpjs_cost_improvement.py -q` and observe the expected failure (using source workspace's Python in worktree).
- [x] Implement fit-only granular and fallback medians with minimum cell count and discharge cutoff filtering; ensure no verified cost or billed cost appears in model features.
- [x] Run the same test and verify it passes.

### Task 2: Controlled offline comparison

**Files:** Create `scripts/bpjs/cost_improvement_experiment.py`; test `backend/tests/test_bpjs_cost_improvement.py`.

- [x] Add tests for validation-only selection, positive output policy, model feature exclusions, and artifact context.
- [x] Run tests to see the expected failure; implement two median benchmarks and raw/log XGBoost with fit-only granular tariff plus categorical INA-CBG. Choose by validation MAE while reporting MAPE and high-cost diagnostics.
- [x] Run tests; train candidates offline; record seeds, loss, train counts, and duration. Probe GPU and retain CPU fallback.

### Task 3: Audit evidence and report

**Files:** Create `docs/BPJS_COST_IMPROVEMENT_REPORT.md`.

- [x] Calculate matched-subject bootstrap CIs on the reused test for main and >Rp20 million strata; audit diagnosis rare/unseen and persist tariff lookup.
- [x] Document performance vs historical baseline, as-of label availability limitation, selection bias from accepted-full filter, no official grouper/tariff, and post-grouper conditional limitation.
- [x] Verify targeted tests, replay saved model/tariff context, and `git diff --check`. Full backend suite: 395 passed, 2 skipped, 3 pre-existing frontend contract failures unrelated to these files.
