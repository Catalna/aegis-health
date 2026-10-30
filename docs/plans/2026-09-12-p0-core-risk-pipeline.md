# P0 Core Risk Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AEGIS-Health's risk score, evidence aggregation, and explanation contract deterministic and domain-consistent.

**Architecture:** Keep the existing clinical, financial, and fraud agents, but insert a deterministic evidence contract between them and the explanation layer. Tariff deviation belongs to the reimbursement family, ordinary similarity is context only, and the LLM can summarize only validated evidence.

**Tech Stack:** Python, Pydantic, pytest, FastAPI response payloads, React labels.

---

## File Map

- Modify `backend/app/models/schemas.py`: add structured evidence and rename the risk breakdown contract.
- Modify `backend/app/agents/risk_engine.py`: implement deterministic family scoring and evidence support.
- Modify `backend/app/agents/review_agent.py`: constrain review output to structured deterministic signals.
- Modify `backend/app/agents/explanation_agent.py`: ground narrative reasons in validated evidence and corrected terminology.
- Modify `backend/app/agents/orchestrator.py`: persist the new contract and bump analysis version.
- Modify `backend/app/agents/financial_engine.py`: expose reimbursement benchmark terminology in evidence.
- Modify `backend/app/api/main.py`: expose financial exposure under an additive API key while preserving the deprecated compatibility key.
- Modify `frontend/src/pages/Assessment.jsx`, `Investigation.jsx`, and `Dashboard.jsx`: display corrected labels.
- Modify `docs/Models.md`, `docs/AgentWorkflow.md`, `docs/Architecture.md`, `docs/BusinessCore.md`, and `docs/PRD.md`: align specifications with implementation.
- Modify `backend/tests/test_clinical.py`, `backend/tests/test_financial.py`, and `backend/tests/test_review_explanation.py`; add contract tests.

### Task 1: Lock the deterministic scoring contract

**Files:** `backend/tests/test_risk_engine_contract.py`, `backend/app/agents/risk_engine.py`, `backend/app/models/schemas.py`

- [x] Write failing tests for tariff deviation not adding clinical points, ordinary similarity scoring zero, relational findings scoring non-zero, and review text not changing total score.
- [x] Run `pytest -q backend/tests/test_risk_engine_contract.py`; confirm the failures identify the old breakdown contract or double-counting behavior.
- [x] Add a typed `EvidenceItem` with source family, signal type, measured value, and explanation.
- [x] Rename the output breakdown key to `evidence_support` and calculate it from deterministic evidence families only.
- [x] Exclude `tariff_deviation_high` and `tariff_deviation_extreme` from the clinical point subtotal; retain them in reimbursement evidence.
- [x] Ensure ordinary similarity does not contribute to `similarity_fraud`.
- [x] Run the focused test file and confirm it passes.

### Task 2: Ground Review and Explanation output

**Files:** `backend/tests/test_review_explanation.py`, `backend/app/agents/review_agent.py`, `backend/app/agents/explanation_agent.py`

- [x] Add failing tests where an LLM returns an unsupported corroborating signal and where narrative text cites a signal absent from structured evidence.
- [x] Run the focused tests and confirm the failures are caused by unvalidated LLM strings.
- [x] Make Review Agent select deterministic signal IDs and fall back to rule-generated evidence when the response contains unknown signals.
- [x] Make Explanation Agent use validated evidence for ranked reasons and preserve the hardcoded human-decision disclaimer.
- [x] Replace user-facing `fair cost`, `actual cost`, and `potential savings` labels with reimbursement benchmark, claimed amount, and financial exposure terminology.
- [x] Run the focused tests and confirm they pass.

### Task 3: Persist and invalidate versioned results

**Files:** `backend/tests/test_validation.py`, `backend/app/agents/orchestrator.py`, `backend/app/models/schemas.py`

- [x] Add a failing test that expects a new analysis version and rejects an old persisted result as stale at the API contract boundary.
- [x] Bump `ANALYSIS_VERSION` and include it in the persisted result contract.
- [x] Ensure persisted evidence contains the deterministic evidence items and the new breakdown key.
- [x] Preserve old stored rows for inspection, but prevent the frontend from presenting them as current.
- [x] Run the focused tests and confirm they pass.

### Task 4: Align frontend labels and documentation

**Files:** `frontend/src/pages/Assessment.jsx`, `frontend/src/pages/Investigation.jsx`, `frontend/src/pages/Dashboard.jsx`, `docs/Models.md`, `docs/AgentWorkflow.md`, `docs/PRD.md`

- [x] Add a frontend test or static contract assertion for `evidence_support` and corrected reimbursement terminology.
- [x] Replace visible labels that imply medical fair cost or confirmed savings.
- [x] Display deterministic evidence before AI narrative and label behavioral signals as supporting context.
- [x] Update the specifications to state that LLM output cannot affect score, tier, or action.
- [x] Remove claims that the simplified grouper is an official INA-CBG grouper.
- [x] Run frontend build and the full relevant backend tests.

### Task 5: Final verification

- [x] Run `python -m compileall -q backend`.
- [x] Run `pytest -q backend/tests`.
- [x] Run `npm run build` from `frontend`.
- [x] Inspect `git diff --check` and verify no unrelated files changed.
- [x] Review all changed files against the approved design before reporting completion.
