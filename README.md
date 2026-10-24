# J-ARI — Pusat Pemeriksaan Klaim (AEGIS)

Sistem penyaring dan prioritisasi klaim berbasis **pipeline multi-agent** untuk membantu
verifikator menentukan klaim mana yang perlu diperiksa lebih dahulu. Backend FastAPI,
frontend React (Vite), PostgreSQL, LanceDB, dan model biaya XGBoost + Isolation Forest.

> **SYNTHETIC DEMONSTRATOR ONLY.** Seluruh data dalam proyek ini data sintetis — *bukan*
> validasi kinerja BPJS dan tidak memuat data peserta JKN asli. Dilarang memuat data
> peserta asli ke sistem ini. Sebelum memproses data di luar seed sintetis, wajib set
> `LLM_PROVIDER=ollama` pada `.env` (aturan privasi; lihat `docs/DECISIONS.md`).

---

## Alur pemeriksaan (agent pipeline)

```
POST klaim → FIFO worker → Validasi → Klinis → Finansial → Fraud → Review → Risiko → Penjelasan
                                                    │
                                              LanceDB (similarity)
```

- Skor risiko adalah **poin mentah 0–85** (bukan probabilitas):
  klinis ≤20 + finansial ≤30 + relasional ≤20 + bukti ≤15 — ditampilkan apa adanya
  (`max_score=85`).
- Band tier terkalibrasi: **medium ≥ 48,7 · high ≥ 55,0** (seleksi pada slice validasi,
  test dibaca sekali — `docs/TIER_CALIBRATION.md`).
- Floor relasional: *exact duplicate* → lantai High; *repeat/cloning/unbundling* kuat →
  lantai Medium. Lantai tidak mengubah poin mentah, dijelaskan di bukti.
- **Keputusan akhir tetap di tangan verifier manusia** (Approve/Reject/Clarify
  di-log pada `human_decisions` + `audit_logs`); LLM tidak pernah mengubah skor, tier,
  atau bukti.
- Narasi LLM dengan kaskade: Gemini (AI Studio) → Ollama lokal → template deterministik;
  penyedia aktif tercatat per tugas (`model_used`/`generated_by`).

## Mulai cepat

Prasyarat: Python 3.10+ (venv), PostgreSQL, Node 20.19+ (Vite 8).

```bat
:: 1) konfigurasi
copy .env.example .env      :: isi DATABASE_URL dgn PostgreSQL lokal Anda

:: 2) backend + frontend (dua jendela)
start.bat                   :: uvicorn :8000 (reload) + vite dev server
:: atau backend-only, stabil saat seeding:
venv\Scripts\python.exe -m uvicorn backend.app.api.main:app --port 8000 --loop backend.app.core.windows_loop:selector_event_loop

:: 3) cek kesehatan
curl http://localhost:8000/api/health

:: 4) isi database demonstrator (sekali; waktu pertama ~20-40 mnt)
venv\Scripts\python.exe scripts\demo_seed.py --dry-run   :: verifikasi desain seed offline
venv\Scripts\python.exe scripts\demo_reset.py --yes      :: kosongkan DB + vector store
venv\Scripts\python.exe scripts\demo_seed.py             :: 220 klaim sintetis via REST

:: 5) uji asap
venv\Scripts\python.exe scripts\smoke_test.py
```

Frontend: `cd frontend && npm install && npm run dev` → buka `http://localhost:5173`.

Model biaya/pola (`backend/models_trained/`, gitignored) hilang? Jalankan
`venv\Scripts\python.exe scripts\train_all.py`.

## Struktur

| Folder | Isi |
|---|---|
| `backend/app/agents/` | pipeline agent (klinis, finansial, fraud, orchestration, risk engine) |
| `backend/app/api/` | endpoint REST (klaim, analitik, stream SSE, keputusan) |
| `backend/app/ml/` | model biaya, fitur, similarity scoring |
| `backend/app/evaluation/` | dataset & metrik evaluasi kandidat |
| `frontend/src/pages/` | Dashboard, Daftar Klaim, Input Klaim, Evaluasi Ketepatan, dst. |
| `scripts/` | generator dataset, kalibrasi tier, evaluasi, seed demo |
| `docs/` | PRD, arsitektur, model card, laporan evaluasi, runbook demo |
| `docs/figures/` | 8 PNG matplotlib — satu-satunya artefak visual |
| `deploy/`, `compose.yaml`, `DOCKER.md` | penempatan Docker |

## Dokumentasi utama

- `docs/DEMO_RUNBOOK.md` — cara menyiapkan & merekam demo (storyboard 8 menit).
- `docs/PRD.md` · `docs/Architecture.md` · `docs/BusinessCore.md` — kebutuhan & desain.
- `docs/EVALUATION_REPORT.md` · `docs/RUNTIME_EVALUATION.md` · `docs/TIER_CALIBRATION.md`
  — metrik kandidat klasifikasi (disclaimer synthetic demonstrator menyertai semua angka).
- `docs/MODELS.md` — kontrak model & aturan promosi artefak.
- `docs/DECISIONS.md` · `docs/CHANGELOG-agent.md` — catatan keputusan engineering & log.

## Pengembangan

```bat
venv\Scripts\python.exe -m pytest backend\tests -q     :: test suite (334 passed / 2 skipped terakhir)
venv\Scripts\python.exe scripts\generate_synthetic_v2.py --help  :: regenerasi dataset sintetis
```

Proyek internal — dikerjakan tim 2 orang (backend + frontend).
