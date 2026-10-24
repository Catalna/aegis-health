# Windows setup README and Docker setup removal

**Status:** approved for specification review; implementation has not started.  
**Date:** 2026-10-25

## Goal

Make the repository approachable for a new Windows developer by documenting one reliable, end-to-end local setup and removing the unused Docker deployment setup. The README is the canonical setup guide; `docs/DEMO_RUNBOOK.md` remains the detailed guide for preparing and recording the synthetic demo.

## Scope

### README and local startup

- Rewrite `README.md` in Indonesian with a clear order: project purpose and synthetic-data warning; prerequisites; clone and environment setup; PostgreSQL database creation; Python virtual environment and backend dependencies; frontend dependencies; runtime model availability; starting backend and frontend; health-check; optional synthetic seed/reset; tests; stop instructions; common setup failures; links to deeper docs.
- State the verified baseline: Windows, Python 3.10+, Node 20.19+ for Vite 8, PostgreSQL 16. Ollama and Gemini are optional narration providers, not startup prerequisites; explain privacy-safe local-provider configuration and that real JKN participant data must not be sent to Gemini.
- Explain that `backend/models_trained/` is local/ignored; give the existing training command only as a recovery path when required runtime artifacts are absent.
- Keep synthetic demo seeding explicitly optional and destructive reset clearly scoped to the synthetic demo database/vector store.
- Make `start.bat` repository-location independent using its own directory rather than a developer-specific absolute path. It starts the backend and frontend in separate terminals and documents that database setup and dependencies must already be complete.

### Environment template and Docker removal

- Replace Docker-specific `.env.example` contents with a local Windows template including an explicit placeholder `DATABASE_URL`, local Ollama URL/provider defaults, optional empty Gemini/Hugging Face values only if still useful to the local app, and comments that explain secrets stay in ignored `.env`.
- Remove only Docker deployment files: `.dockerignore`, `compose.yaml`, `DOCKER.md`, `deploy/backend.Dockerfile`, `deploy/frontend.Dockerfile`, and `deploy/nginx.conf` (remove `deploy/` if empty).
- Remove the current Docker deployment entry from `docs/Architecture.md`; retain historical plan/changelog references rather than rewriting project history.
- Keep application code, frontend/backend behavior, model artifacts policy, demo scripts, evaluation assets, and untracked user files unchanged.

## Setup flow to document

1. Clone repo and install Python 3.10+, Node 20.19+, PostgreSQL 16.
2. Copy `.env.example` to `.env`; set a local PostgreSQL password in `DATABASE_URL`; create the `jari_db` database using local PostgreSQL tools.
3. Create `venv`, activate it, install `backend/requirements.txt`.
4. Run `npm ci` in `frontend/`.
5. Confirm runtime model artifacts exist; if absent, run `scripts/train_all.py` as documented recovery.
6. Run `start.bat` (or provide explicit backend/frontend commands), verify `/api/health`, and open the frontend at `http://localhost:5173`.
7. Optionally run the synthetic seed dry-run, reset only an empty/demo database, seed via the production REST path, and run backend tests.
8. Stop the two terminal processes with Ctrl+C; do not imply that reset is a normal shutdown operation.

## Safety and non-goals

- Never include a real password, API key, database dump, trained model, or real JKN data in tracked files. `.env` and `backend/models_trained/` remain ignored.
- Do not remove code or dependencies merely because Docker is removed; only deployment-only files listed above are in scope.
- Do not change runtime scoring, endpoints, schema, database models, or the teammate's frontend implementation.
- Do not claim the synthetic demonstrator validates BPJS performance.

## Verification

- Review README commands against actual repository scripts, dependency files, `.env` loading, `start.bat`, and PostgreSQL defaults.
- Search tracked files for active references to removed Docker files; historical plans may retain old context.
- Confirm `.env`, runtime models, database data, and user-owned untracked directories are not staged.
- Run `git diff --check`, verify `start.bat` uses `%~dp0` and launches both services, run frontend production build, and run a focused health check if the local stack is available.
- Stage/commit only the approved README/setup changes and listed Docker removals; do not push unless separately requested.

## Acceptance criteria

- A new Windows contributor can follow the README from clone to healthy API and running UI without guessing commands or relying on a machine-specific path.
- Local `.env.example` is safe to copy and has no real credentials or Docker-only hostnames.
- No Docker deployment files remain tracked and no current architecture/README setup instructions point to them.
- Docker removal does not change the runtime application or include sensitive local artifacts.
