# Windows Setup README and Docker Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the README a complete end-to-end local Windows setup guide and remove the unused Docker deployment setup without touching application code.

**Architecture:** Documentation-only change plus launcher and environment-template fixes. The README becomes the canonical local setup guide (clone → PostgreSQL → `.env` → dependencies → models → start → verify → optional synthetic seed → stop). Docker deployment files (`compose.yaml`, `DOCKER.md`, `.dockerignore`, `deploy/` Dockerfiles + nginx.conf) are deleted; `docs/Architecture.md` loses its active Docker entry; `.env.example` becomes a local Windows template with no real credentials; `start.bat` becomes repository-location independent.

**Tech Stack:** Markdown docs, Windows batch launcher, PostgreSQL 16 (local service), Python 3.10+ venv, Node 20.19+ (Vite 8).

**Spec:** `docs/specs/2026-10-25-windows-readme-and-remove-docker-design.md`

---

## File structure map

| Task | File(s) | Responsibility |
|---|---|---|
| 1 | `docs/Architecture.md` | remove active Docker entry from the file-structure diagram |
| 2 | `.env.example` | local Windows environment template, no real credentials |
| 3 | `start.bat` | portable launcher (own directory, no dev-specific path) |
| 4 | `README.md` | canonical end-to-end local setup guide (Indonesian) |
| 5 | `.dockerignore`, `compose.yaml`, `DOCKER.md`, `deploy/*` | removal of Docker deployment setup |
| 6 | `docs/CHANGELOG-agent.md` | record the doc/cleanup commits; final verification |

Not in scope: application code, frontend pages, scoring/endpoints/schema, historical docs (`docs/plans/*`), changelog history text, user-owned untracked files (`docs/Planning.md`, `docs/docs_competition/` — keep untracked).

Facts verified in repo (used verbatim below):
- `backend/requirements.txt` exists with pinned deps (fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, xgboost, shap, scikit-learn, numpy, pandas, pyarrow, matplotlib, opencv-python-headless, joblib, sentence-transformers, httpx, python-dotenv, lancedb, sse-starlette, pytest, pytest-asyncio).
- `.env` is loaded via `python-dotenv` (`load_dotenv()`) in `backend/app/models/database.py`, `backend/app/core/llm_client.py`, `backend/app/ml/similarity.py`.
- Local defaults in code: `DATABASE_URL` default `postgresql+asyncpg://postgres:aegis_2026@localhost/aegis_health_db` (existing dev default inside `backend/app/models/database.py`; do NOT copy this password into tracked templates), `OLLAMA_BASE_URL` default `http://localhost:11434`, `LLM_PROVIDER` default `gemini`, allowed origins default `http://localhost:5173,http://127.0.0.1:5173`.
- Runtime model artifacts: `backend/models_trained/xgboost_regressor.json` + `isolation_forest.pkl` (gitignored; recovery via `scripts/train_all.py`).
- Schema creation is automatic at startup (`Base.metadata.create_all` in `backend/app/models/database.py`).
- Health endpoint: `http://localhost:8000/api/health`; frontend dev URL: `http://localhost:5173`.
- Vite dev/build verified with Node v20.20.2.

---

### Task 1: Remove active Docker entry from `docs/Architecture.md`

**Files:**
- Modify: `docs/Architecture.md` (line 129 area, file-tree block)

- [x] **Step 1: Edit the tree**

Replace:

```text
+-- docs/                            # Dokumentasi produk
+-- scripts/                         # Utility scripts (training, data generation)
+-- compose.yaml                     # Docker Compose (PostgreSQL)
+-- start.bat                        # Windows startup script
```

with:

```text
+-- docs/                            # Dokumentasi produk
+-- scripts/                         # Utility scripts (training, data generation)
+-- start.bat                        # Windows startup script
```

- [x] **Step 2: Verify no other active reference**

Run: `git grep -n -i "compose.yaml" -- docs/Architecture.md README.md`
Expected: no output (historical plans in `docs/plans/*` may keep old context; leave them).

- [x] **Step 3: Commit**

```bat
git add docs/Architecture.md
git commit -m "docs: drop docker compose entry from architecture tree"
```

---

### Task 2: Local Windows `.env.example`

**Files:**
- Modify (replace content): `.env.example`

- [x] **Step 1: Replace content with the local template**

Full new content (verbatim):

```text
# Konfigurasi lokal Windows AEGIS-Health.
# Salin berkas ini ke .env lalu sesuaikan. Jangan commit .env (sudah gitignored).

# PostgreSQL lokal (wajib). Buat database aegis_health_db terlebih dahulu (lihat README).
DATABASE_URL=postgresql+asyncpg://postgres:<password-lokal>@localhost:5432/aegis_health_db

# LLM narasi: gemini (Google AI Studio) dengan cascade Ollama lokal -> template.
# Tanpa GEMINI_API_KEY atau tanpa internet, narasi otomatis turun ke Ollama lalu
# template deterministik. LLM tidak pernah mengubah skor/tier/bukti.
# PENTING privasi: saat memproses data peserta JKN riil, set LLM_PROVIDER=ollama.
LLM_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash

# Ollama lokal (backup narasi; wajib hidup bila tampilan tanpa kunci Gemini).
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=mistral:7b
CLINICAL_MODEL=mistral:7b
REVIEW_MODEL=deepseek-r1:7b
REVIEW_MODEL_FALLBACK=mistral:7b
EXPLANATION_MODEL=qwen2.5:7b
EXPLANATION_MODEL_FALLBACK=mistral:7b

# Opsional: token HuggingFace untuk batas unduhan model lebih tinggi.
# Simpan token asli hanya di .env lokal; jangan pernah di-commit.
HF_TOKEN=
```

- [x] **Step 2: Safety check**

Run: `git grep -n "aegis_2026\|host.docker.internal" -- .env.example`
Expected: no output. Also confirm it contains `<password-lokal>` placeholder exactly once.

- [x] **Step 3: Commit**

```bat
git add .env.example
git commit -m "docs: local windows env template with placeholder credentials"
```

---

### Task 3: Portable `start.bat`

**Files:**
- Modify (replace content): `start.bat`

- [x] **Step 1: Replace content (verbatim)**

Full new content:

```bat
@echo off
rem Portable launcher: works from any directory the repo is placed in.
setlocal
cd /d "%~dp0"

echo Starting AEGIS-Health Backend...
start cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m uvicorn backend.app.api.main:app --reload --port 8000 --loop backend.app.core.windows_loop:selector_event_loop"

echo Starting AEGIS-Health Frontend...
start cmd /k "cd /d %~dp0frontend && npm run dev"

echo AEGIS-Health System started!
```

- [x] **Step 2: Static verification**

Run: `Select-String -Path start.bat -Pattern "%~dp0|C:\\Users"`
Expected: `%~dp0` present in cd and both start lines; no `C:\Users` absolute path.

- [x] **Step 3: Commit**

```bat
git add start.bat
git commit -m "fix: make start.bat portable to any repo location"
```

---

### Task 4: Rewrite `README.md` — canonical end-to-end local setup guide

**Files:**
- Modify (full rewrite, two passes): `README.md`

- [x] **Step 1: Write part 1 (title → setup step 7)**

Replace the whole file with:

````markdown
# AEGIS-Health — Pusat Pemeriksaan Klaim (AEGIS)

Sistem penyaring dan prioritisasi klaim berbasis **pipeline multi-agent** untuk membantu
verifikator menentukan klaim mana yang perlu diperiksa lebih dahulu.
Backend FastAPI + PostgreSQL + LanceDB, frontend React (Vite), model biaya
XGBoost + Isolation Forest, dengan penjelasan SHAP dan narasi LLM.

> **SYNTHETIC DEMONSTRATOR ONLY.** Seluruh data dalam proyek ini data sintetis —
> *bukan* validasi kinerja BPJS dan tidak memuat data peserta JKN asli. Dilarang
> memuat data peserta asli ke sistem ini. Sebelum memproses data di luar seed
> sintetis, wajib set `LLM_PROVIDER=ollama` pada `.env` (aturan privasi;
> lihat `docs/DECISIONS.md`).

## Isi utama

- **Alur pemeriksaan per klaim**: Validasi → Klinis → Finansial → Fraud → Review →
  Risiko → Penjelasan, dari antrean FIFO.
- **Skor risiko mentah 0–85**: klinis ≤20 + finansial ≤30 + relasional ≤20 + bukti ≤15
  (bukan probabilitas).
- **Tier terkalibrasi**: medium ≥ 48,7 · high ≥ 55,0; lantai relasional
  (exact-duplicate → High; repeat/cloning/unbundling kuat → Medium).
- **Keputusan akhir tetap verifier manusia** (ter-log di `human_decisions` +
  `audit_logs`); LLM tidak pernah mengubah skor/tier/bukti.

## Prasyarat

| Alat | Versi | Catatan |
|---|---|---|
| Windows | 10/11 | perintah untuk PowerShell/CMD |
| Python | 3.10+ | venv bawaan di folder `venv` |
| PostgreSQL | 16 | service lokal berjalan |
| Node.js | 20.19+ | untuk Vite 8 (dites dengan 20.20.2) |
| Git | — | untuk clone repo |

Narasi LLM itu **opsional**: tanpa kunci Gemini, sistem otomatis turun ke Ollama
lokal lalu ke template deterministik; aplikasi tetap jalan penuh. Jangan mengirim
data peserta JKN asli ke Gemini — set `LLM_PROVIDER=ollama` (detail: `docs/DECISIONS.md`).

## Setup pertama (end-to-end)

Jalankan PowerShell di folder tempat repo Anda. Ganti `<password-lokal>` dengan
password PostgreSQL pilihan Anda.

### 1) Clone + konfigurasi

```bat
git clone https://github.com/Catalna/aegis-health.git
cd aegis-health
copy .env.example .env
```

Buka `.env` dan isi `DATABASE_URL`:

```
DATABASE_URL=postgresql+asyncpg://postgres:<password-lokal>@localhost:5432/aegis_health_db
```

### 2) Buat database

```bat
psql -U postgres -c "CREATE DATABASE aegis_health_db;"
```

Skema tabel dibuat otomatis saat backend pertama kali berjalan.

### 3) Dependensi backend

```bat
python -m venv venv
venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 4) Dependensi frontend

```bat
cd frontend
npm ci
cd ..
```

### 5) Model runtime

Backend membutuhkan `backend/models_trained/xgboost_regressor.json` dan
`isolation_forest.pkl` (folder ini gitignored). Jika belum ada:

```bat
venv\Scripts\python.exe scripts\train_all.py
```

### 6) Jalankan aplikasi

```bat
start.bat
```

Dua jendela CMD terbuka: backend (uvicorn :8000, reload) dan frontend (vite :5173).
Alternatif backend-only tanpa reload:

```bat
venv\Scripts\python.exe -m uvicorn backend.app.api.main:app --port 8000 --loop backend.app.core.windows_loop:selector_event_loop
```

### 7) Verifikasi

```bat
curl http://localhost:8000/api/health
```

`status` boleh `ok` atau `degraded` (komponen LLM opsional); yang menentukan:
`database`, `queue_worker`, `vector_store`, `ml_*`. UI di `http://localhost:5173`.
````

- [x] **Step 2: Append part 2 (step 8 → footer)**

Edit `README.md` — append after the health-verification line block:

````markdown

### 8) Isi database demonstrator (opsional, data sintetis)

```bat
:: 1) cek desain seed offline (mirror engine, harus "220/220 sesuai target; gagal 0")
venv\Scripts\python.exe scripts\demo_seed.py --dry-run

:: 2) KOSONGKAN database demo + vector store (HANYA data demo sintetis)
venv\Scripts\python.exe scripts\demo_reset.py --yes

:: 3) 220 klaim via alur produksi REST (pertama ~20-40 menit)
venv\Scripts\python.exe scripts\demo_seed.py
```

`demo_reset.py` HANYA untuk database demo sintetis — jangan pernah dipakai pada data lain.

### 9) Menghentikan aplikasi

Tekan `Ctrl+C` di jendela backend dan jendela frontend (atau tutup kedua jendela CMD).

### 10) Uji cepat

```bat
venv\Scripts\python.exe scripts\smoke_test.py
venv\Scripts\python.exe -m pytest backend\tests -q
```

## Permasalahan umum

| Gejala | Penyebab umum | Solusi |
|---|---|---|
| Port 8000 dipakai | backend lama masih hidup | `netstat -ano \| findstr :8000` lalu `taskkill /PID <pid> /F` |
| `database.status` bukan `ok` | PostgreSQL mati / URL salah | pastikan PostgreSQL jalan; cek `DATABASE_URL` di `.env` |
| Model hilang saat startup | `models_trained/` kosong | jalankan `scripts\train_all.py` |
| `npm ci` gagal | Node < 20.19 | perbarui Node.js |
| ImportError saat startup | dependensi backend belum terpasang | ulangi langkah `pip install -r backend\requirements.txt` |

## Struktur

| Folder | Isi |
|---|---|
| `backend/app/agents/` | pipeline agent (klinis, finansial, fraud, orchestration, risk engine) |
| `backend/app/api/` | endpoint REST (klaim, analitik, stream SSE, keputusan) |
| `backend/app/ml/` | model biaya, fitur, similarity scoring |
| `backend/app/models/` | ORM database + pembuatan skema |
| `frontend/src/pages/` | Dashboard, Daftar Klaim, Input Klaim, Evaluasi Ketepatan, dst. |
| `scripts/` | generator dataset, kalibrasi tier, evaluasi, seed demo |
| `docs/` | PRD, arsitektur, model card, laporan evaluasi, runbook demo |
| `docs/figures/` | 8 PNG matplotlib — satu-satunya artefak visual |

## Dokumentasi utama

- `docs/DEMO_RUNBOOK.md` — menyiapkan & merekam demo (storyboard 8 menit).
- `docs/PRD.md` · `docs/Architecture.md` · `docs/BusinessCore.md` — kebutuhan & desain.
- `docs/EVALUATION_REPORT.md` · `docs/RUNTIME_EVALUATION.md` · `docs/TIER_CALIBRATION.md`
  — metrik kandidat klasifikasi (disclaimer synthetic demonstrator selalu menyertai).
- `docs/MODELS.md` — kontrak model & aturan promosi artefak.
- `docs/DECISIONS.md` · `docs/CHANGELOG-agent.md` — keputusan engineering & log.
- `docs/specs/` · `docs/plans/` — arsip spesifikasi & rencana implementasi.

## Pengembangan

Prosedur artefak model mengikuti `docs/MODELS.md` (verifikasi angka dulu, baru promosi);
data riil tidak diizinkan di repositori ini.
````

- [x] **Step 3: Read the whole README and fix inconsistencies (duplicate spacing, broken tables)**

- [x] **Step 4: Link check — every referenced doc exists**

Run: `git ls-files docs/PRD.md docs/Architecture.md docs/BusinessCore.md docs/EVALUATION_REPORT.md docs/RUNTIME_EVALUATION.md docs/TIER_CALIBRATION.md docs/MODELS.md docs/DECISIONS.md docs/CHANGELOG-agent.md docs/DEMO_RUNBOOK.md scripts/demo_seed.py scripts/demo_reset.py scripts/train_all.py scripts/smoke_test.py`
Expected: every path listed (no missing).

Run: `git grep -n -i "docker" -- README.md`
Expected: no output.

- [x] **Step 5: Commit**

```bat
git add README.md
git commit -m "docs: rewrite README as end-to-end local Windows setup guide"
```

---

### Task 5: Delete Docker deployment files

**Files:**
- Delete: `.dockerignore`, `compose.yaml`, `DOCKER.md`, `deploy/backend.Dockerfile`, `deploy/frontend.Dockerfile`, `deploy/nginx.conf`

- [x] **Step 1: Remove tracked Docker files**

```bat
git rm .dockerignore compose.yaml DOCKER.md deploy/backend.Dockerfile deploy/frontend.Dockerfile deploy/nginx.conf
```

(`deploy/` becomes empty and disappears from the working tree.)

- [x] **Step 2: Verify no active tracked references remain**

Run: `git grep -n -i "docker\|compose.yaml" -- "*.py" "*.md" "*.yaml" "*.bat" README.md .env.example`
Expected: only historical `docs/plans/*` and `docs/CHANGELOG-agent.md` mentions; nothing in README, setup docs, launchers, or code.

- [x] **Step 3: Confirm nothing sensitive/artifact staged**

Run: `git status -sb`
Expected: staged deletions are exactly the six Docker files; `docs/Planning.md` and `docs/docs_competition/` remain untracked; `.env` and `backend/models_trained/` never appear.

- [x] **Step 4: Commit**

```bat
git commit -m "chore: remove unused docker deployment setup"
```

---

### Task 6: Final verification, changelog entry

**Files:**
- Modify: `docs/CHANGELOG-agent.md` (append entry)

- [x] **Step 1: Frontend production build**

Run: `cd frontend && npm run build`
Expected: `✓ built` (chunk-size warning acceptable; record it).

- [x] **Step 2: Runtime health (if local stack is up)**

Run: `curl http://localhost:8000/api/health`
Expected: `database/queue_worker/vector_store/ml_*` `ok` — confirms docs/config changes touched nothing runtime.

- [x] **Step 3: Workspace review**

Run: `git status -sb` and `git log --oneline -6`
Expected: working tree clean except intentionally untracked user files; history shows the six task commits.

- [x] **Step 4: Append changelog entry (no self-hash inside the same commit)**

Add to `docs/CHANGELOG-agent.md` before the report tail:

```markdown

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
- Verification: README link check green; no active Docker references; frontend
  production build green; `/api/health` unchanged.
```

- [x] **Step 5: Commit changelog, then record hashes in a follow-up docs commit**

```bat
git add docs/CHANGELOG-agent.md
git commit -m "docs: record windows readme + docker removal work"
```

Then append the two new commit hashes (README/setup + docker removal) to the changelog hash list and commit once more:

```bat
git add docs/CHANGELOG-agent.md
git commit -m "docs: record commit hashes for readme and docker cleanup"
```

- [x] **Step 6: Stop — do not push**

Per spec: commit locally; push only if the user separately asks for it.

---

## Self-review checklist (run after editing)

- [x] Every spec bullet maps to a task above (README flow, verified baseline, privacy note, models recovery note, seed scoping, portable start.bat, local `.env.example`, six Docker deletions, Architecture.md entry, no runtime changes).
- [x] No placeholders — all commands and file contents are verbatimRunnable.
- [x] No real credential anywhere in tracked content (`aegis_2026` only appears in the code-default mention inside this plan header, never in README/.env.example).
- [x] Task numbering and anchors match the actual file states.


