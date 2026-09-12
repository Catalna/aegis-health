# Frontend Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task.

**Goal:** Merapikan seluruh UI J-ARI agar lebih jelas, konsisten, responsif, dan tetap dekat dengan DNA visual saat ini.

**Architecture:** Pertahankan React Router, Recharts, API, dan struktur halaman yang ada. Perkuat fondasi melalui token CSS, komponen visual bersama, serta copy yang berorientasi verifier tanpa istilah teknis.

**Tech Stack:** React, Vite, React Router, Recharts, Lucide React, CSS.

---

## File Structure

- Modify `frontend/src/index.css`: token, layout, components, responsive, focus states.
- Modify `frontend/src/App.jsx`: navigasi dan landmark yang lebih jelas.
- Modify `frontend/src/pages/Dashboard.jsx`: hierarchy dashboard, KPI, chart context, states.
- Modify `frontend/src/pages/ClaimsList.jsx`: labels, table semantics, filters, states.
- Modify `frontend/src/pages/ClaimIntake.jsx`: plain-language form and validation copy.
- Modify `frontend/src/pages/Investigation.jsx`: plain-language progress and result labels.
- Modify `frontend/src/pages/Assessment.jsx`: plain-language output and evidence sections.
- Modify `frontend/src/pages/DemoLoader.jsx`, `Monitoring.jsx`, `MLEvaluation.jsx`: remove visible technical jargon and align layout.
- Modify `frontend/src/api.js`: user-facing action labels and version comments only when needed.

## Tasks

### Task 1: Lock visual system
- [ ] Replace ad-hoc colors, spacing, radii, and transitions with a restrained token ramp.
- [ ] Preserve light canvas, white surfaces, green accent, risk colors, Inter body, and JetBrains Mono for IDs only.
- [ ] Add visible `:focus-visible`, disabled, active, reduced-motion, and mobile rules.

### Task 2: Refine shell and dashboard
- [ ] Add accessible skip target and labelled navigation.
- [ ] Standardize page header and dashboard KPI hierarchy.
- [ ] Give charts clear supporting text, empty state, and responsive sizing without changing API data.

### Task 3: Refine operational pages
- [ ] Simplify claims table/filter copy and preserve horizontal scrolling inside the table.
- [ ] Simplify intake labels, hints, error messages, and action wording.
- [ ] Simplify investigation and assessment labels; hide implementation names from verifier output.

### Task 4: Align secondary pages
- [ ] Apply the same page header, cards, states, and plain-language labels to monitoring, demo loader, and model evaluation.
- [ ] Ensure no visible technical implementation terms remain unless required for an explicit data field.

### Task 5: Verify
- [ ] Run `npm run build` from `frontend`.
- [ ] Render desktop and mobile views, check overflow and console errors.
- [ ] Run backend tests to ensure frontend-only changes did not affect shared contracts.
