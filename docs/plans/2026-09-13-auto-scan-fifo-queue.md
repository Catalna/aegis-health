# Automatic Claim Scanning and FIFO Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically scan every incoming claim, preserve FIFO ordering by server receipt time, and give verifiers a risk-prioritized review queue with date tracking.

**Architecture:** Claim intake writes immutable receipt and queue metadata. A database-backed worker claims the oldest queued item, runs the existing orchestrator, and records analysis timestamps/status. The verifier queue sorts high-risk items first, then FIFO within each risk tier; no claim is auto-approved without human verification.

**Scope boundary:** Verifier authentication and authorization are not part of this queue change; access control remains a separate deployment/integration concern.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, asyncio worker, existing orchestrator/SSE, React/Vite.

---

## File Map

- Modify `backend/app/models/database.py`: claim timestamps, queue sequence, retry/error fields, and migration statements.
- Modify `backend/app/models/schemas.py`: API status and date filter schemas.
- Create `backend/app/services/claim_queue.py`: FIFO claim worker and retry handling.
- Modify `backend/app/api/claims.py`: enqueue on intake, date/status filters, verifier transitions.
- Modify `backend/app/api/main.py`: start and stop the worker with application lifespan.
- Modify `frontend/src/api.js`: queue/date query helpers.
- Modify `frontend/src/pages/ClaimsList.jsx`: status, queue age, date filters, and review ordering.
- Modify `frontend/src/pages/Monitoring.jsx` and `frontend/src/pages/Dashboard.jsx`: queue and SLA summaries.
- Create `scripts/generate_claims.py`: deterministic pending dataset generator with a minimum count of 8, `--count`, `--seed`, `--analyze[=true|false]`, and explicit prefix-scoped `--cleanup --yes`.
- Extend `backend/tests/test_frontend_contract.py` and add queue/date API tests.

## Task 1: Persist Queue and Lifecycle Metadata

- [ ] Write failing tests for immutable `received_at`, monotonic `queue_sequence`, and lifecycle timestamps.
- [ ] Add `received_at`, `queue_sequence`, `analysis_started_at`, `analyzed_at`, `verified_at`, `analysis_attempts`, and `last_analysis_error` to `ClaimRecord`.
- [ ] Extend the existing startup migration path and set `received_at`/`queue_sequence` server-side during claim creation.
- [ ] Run the focused model/API tests and verify existing records receive safe backfill values.

## Task 2: Implement Automatic FIFO Scanning

- [ ] Write a failing worker test proving the oldest queued claim is selected first and locked against duplicate workers.
- [ ] Create `claim_queue.py` with `SELECT ... FOR UPDATE SKIP LOCKED ORDER BY queue_sequence`, one default worker, bounded retries, and failure status.
- [ ] Start the worker in `main.py` lifespan and cancel it cleanly on shutdown.
- [ ] Enqueue claims after the intake transaction commits; keep manual analyze as an idempotent retry path.
- [ ] Run worker tests with a fake orchestrator and verify status transitions: `pending` → `scanning` → `processed`/`review_required`/`failed`.

## Task 3: Add Date-Aware Queue and Verification APIs

- [ ] Add `received_from`, `received_to`, `admission_from`, `admission_to`, and status/tier filters to the claims list endpoint.
- [ ] Sort scanning by `queue_sequence`; sort verifier review by risk tier, then `received_at`, then `queue_sequence`.
- [ ] Set `verified_at` and verifier identity on approval/rejection, preserving the original receipt time.
- [ ] Add tests for date boundaries, FIFO tie-breaking, pending age, and verifier transitions.

## Task 4: Update Frontend Queue Experience

- [ ] Show `received_at`, queue age, scan status, risk tier, and last error in the claims table.
- [ ] Add date-range and lifecycle filters while preserving the current pagination and search behavior.
- [ ] Add clear states for queued, scanning, processed, review required, failed, empty, and stale data.
- [ ] Keep the verifier action separate from AI scanning; show that AI results are recommendations pending human decision.
- [ ] Add frontend contract tests and Playwright checks for FIFO display, date filtering, and retry states.

## Task 5: Add Repeatable Dataset Generation

- [ ] Create `scripts/generate_claims.py` with at least 8 claims and deterministic relationship groups: same facility/diagnosis with different costs, same diagnosis across facilities, same facility across diagnoses, and mixed controls.
- [ ] Default to pending-only generation; accept both bare `--analyze` and explicit `--analyze=true|false`, requiring an explicit true value before running analysis.
- [ ] Add confirmation-gated cleanup by generated prefix using only individual API reset/delete calls, and print the generated count/pattern summary.
- [ ] Verify generated data through the API, not direct database inserts.

## Verification

- [ ] Run `python -m pytest backend/tests -q`.
- [ ] Run `python -m compileall -q backend/app`.
- [ ] Run `npm run build` in `frontend`.
- [ ] Start Docker Compose and verify health reports Ollama, PostgreSQL, vector store, and queue worker status.
- [ ] Insert claims with staggered receipt times and verify the oldest claim is scanned first.
- [ ] Verify a high-risk claim appears first in the verifier queue while same-tier claims remain FIFO.
- [ ] Verify restart recovery re-queues claims left in `scanning` without duplicating analysis records.
