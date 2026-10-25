# J-ARI — Pusat Pemeriksaan Klaim (AEGIS)

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
DATABASE_URL=postgresql+asyncpg://postgres:<password-lokal>@localhost:5432/jari_db
```

### 2) Buat database

```bat
psql -U postgres -c "CREATE DATABASE jari_db;"
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
