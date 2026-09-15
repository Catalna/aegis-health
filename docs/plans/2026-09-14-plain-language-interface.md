# Plain-Language Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace technical labels and analysis wording with formal, human-readable Indonesian while preserving calculations and internal diagnostics.

**Architecture:** Add small shared translation helpers at the presentation boundaries. The backend will produce safe Indonesian findings from rule identifiers and benchmark data; the frontend will translate statuses, labels, health details, and remaining public payload values. Internal field names, logs, and calculations remain unchanged.

**Tech Stack:** FastAPI/Pydantic, React/Vite, existing pytest and Playwright smoke scripts.

---

## File Map

- Create `backend/app/core/human_language.py`: backend flag, status, and finding wording.
- Modify `backend/app/agents/clinical_agent.py`, `risk_engine.py`, `financial_engine.py`, `review_agent.py`, and `explanation_agent.py`: use human-facing findings and prompts.
- Modify `backend/app/core/public_analysis.py`: hide model/provenance implementation fields from public analysis payloads.
- Create `frontend/src/humanLanguage.js`: frontend labels, status text, and safe formatting helpers.
- Modify `frontend/src/api.js`, `ClaimsList.jsx`, `Assessment.jsx`, `Investigation.jsx`, `Dashboard.jsx`, `Monitoring.jsx`, `QueueSummary.jsx`, and `queueSummaryData.js`: consume the shared wording and remove technical labels.
- Create `backend/tests/test_human_language.py`: exact translations and prohibited leakage tests.
- Create `frontend/tests/plain_language_smoke.py`: rendered copy checks for representative statuses and analysis findings.

## Task 1: Backend human-readable findings

- [ ] Add failing tests for every supplied example and all active rule identifiers.
- [ ] Add deterministic maps and formatters in `human_language.py`.
- [ ] Replace rule, benchmark, fraud-pattern, fallback, and provenance wording at the backend presentation boundary.
- [ ] Keep internal `signal_type`, `evidence_id`, model names, and calculation fields unchanged internally.
- [ ] Run `python -m pytest backend/tests/test_human_language.py -q`.

## Task 2: Public payload safety

- [ ] Add tests proving `model_used`, `generated_by`, internal identifiers, and raw technical narrative strings are absent or rewritten from public analysis data.
- [ ] Extend the existing recursive public projection without changing stored records or internal logs.
- [ ] Verify the three supplied examples never appear in their technical form in a public payload.

## Task 3: Frontend copy migration

- [ ] Add shared maps for statuses, actions, risk components, service health, queue summaries, and error messages.
- [ ] Replace visible English/technical text including `SLA`, `AI`, `Worker`, `Database`, `Terproses`, `Review`, `Potential Financial Exposure`, and raw feature names.
- [ ] Keep URL query values and API field names unchanged; only visible labels change.
- [ ] Update `plainText` to translate rule identifiers and remove model/provenance display.
- [ ] Add accessible live-region messages for loading, partial, stale, and retry states using the same vocabulary.

## Task 4: Verification

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m compileall -q backend/app scripts`.
- [ ] Run `npm run build` in `frontend`.
- [ ] Run the frontend Playwright copy smoke at 390px and 1440px, checking console errors and the three representative findings.
- [ ] Run `git diff --check` and inspect the final rendered copy.

## Constraints

- Do not change risk scores, queue behavior, verifier decisions, API routes, or database schema.
- Do not expose rule codes, model names, HTTP codes, stack traces, or implementation terms to officers.
- Keep final-decision wording explicit: the system recommends review priority; the verifier decides.
