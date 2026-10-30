# AEGIS-Health Demo Runbook (Fase 6)

> **Synthetic demonstrator only.** Seluruh database demo adalah data sintetis terkurasi
> (`scripts/demo_seed.py`, 220 klaim). Bukan validasi kinerja BPJS. Jangan pernah memuat
> data JKN asli ke dalam sistem ini. Sebelum memproses data di luar seed sintetis,
> set `LLM_PROVIDER=ollama` (lihat bagian Degradasi).

Target: rekaman video 1 November. Semua langkah berupa perintah nyata yang bisa diulang.

---

## 1. Prasyarat satu kali

| Komponen | Cara cek | Catatan |
|---|---|---|
| Python venv + dependensi | `venv\Scripts\python.exe -m pytest backend\tests -q` harus hijau | langsung lihat jumlah yang passed |
| PostgreSQL jalan | `GET /api/health` → `database.status == ok` | URL di `.env` (`DATABASE_URL`) |
| Model runtime tersaji | `backend/models_trained/xgboost_regressor.json` + `isolation_forest.pkl` | gitignored; jika hilang: `python scripts/train_all.py` |
| Kunci LLM (opsional utk demo narrasi) | `LLM_PROVIDER=gemini` + `GEMINI_API_KEY` di `.env` | tanpa kunci → Ollama → template (tetap demoable) |
| Frontend | `frontend` folder, `npm run dev` | video memakai UI (dikerjakan dev lain) |

## 2. Mulai dari kondisi bersih (satu siklus)

```bat
:: 1) reset database demo + vector store (HANYA pada data sintetis)
venv\Scripts\python.exe scripts\demo_reset.py --yes

:: 2) jalankan backend + frontend (window terpisah)
start.bat
```

`start.bat` menjalankan: backend `uvicorn backend.app.api.main:app --reload --port 8000
--loop backend.app.core.windows_loop:selector_event_loop` dan frontend `npm run dev`.
Atau backend-only (tanpa `--reload`, stabil saat seeding):

```bat
venv\Scripts\python.exe -m uvicorn backend.app.api.main:app --port 8000 --loop backend.app.core.windows_loop:selector_event_loop
```

3) Tunggu server hijau lalu isi database demo (220 klaim; ~20–40 menit pertama kali
   karena narasi LLM; sekali saja — DB dipakai ulang untuk rekaman):

```bat
:: 3a) cek desain seed dry-run dulu (mirror engine runtime, offline):
::     venv\Scripts\python.exe scripts\demo_seed.py --dry-run
::     harus "220/220 sesuai target; gagal 0" + "peringatan: bersih"
venv\Scripts\python.exe scripts\demo_seed.py
```

4) Verifikasi hasil seed (output skrip mencetak):
   - `/api/analytics/dashboard`: total klaim, distribusi tier, potential exposure.
   - `GET /api/claims?tier=high` → bucket HIGH berisi showcase (exact duplicate,
     unbundling berbiaya naik, upcoding+repeat, cloning berbiaya naik, dll).
   - `GET /api/claims?tier=medium`, `?tier=low` untuk kontras.

Smoke endpoint cepat: `venv\Scripts\python.exe scripts\smoke_test.py`
(bad-date ditolak → klaim normal diproses → keputusan verifier → duplicate 409).

## 3. Alur demo untuk video (storyboard ~8 menit)

1. **Dashboard (±1 mnt)** — total klaim, distribusi tier HEAL (buang band lama yang 87% medium),
   `potential_financial_exposure`.
2. **Antrean verifier (±1,5 mnt)** — daftar klaim urut `sort=priority`:
   HIGH di atas (semua anomali), medium jarang, low tenang. Sorot angka tier
   `high(≥55) / medium(≥48,7) / low` + floor relasional (exact_duplicate→High,
   repeat/cloning/unbundling→Medium).
3. **Detail klaim HIGH (±2 mnt, pilih `DEMO-DU1-2` atau `DEMO-UB0-F2`)** —
   timeline agent (validasi → klinis → finansial → fraud → review → risiko → penjelasan),
   bukti relasional (repeat/cloning/unbundling dengan matched claim id + hari),
   SHAP top-5 finansial, `max_score=85` (poin mentah, bukan probabilitas),
   tier floor ditampilkan di bukti.
4. **Proses klaim baru live (±2 mnt)** — dua varian:
   - *otomatis*: POST klaim baru → worker FIFO mengambil (`pending → scanning →
     review_required`(HIGH/MEDIUM) / `processed`(LOW)) dengan perubahan status yang terlihat
     di daftar klaim; tombol "Analyze" di UI dapat memicu jalur manual.
   - *dengan SSE per fase*: `POST /api/claims/analyze` `{claim_id}` → `task_id` →
     `GET /api/stream/{task_id}` menampilkan event fase 0–8 real-time.
   Ekspektasi latency: klaim pertama ~60 s (build model+SHAP one-time), berikutnya
   p50 ≈ 7 s (deterministik 75 ms + narasi LLM).
5. **Keputusan verifier (±1 mnt)** — buka klaim HIGH → tombol keputusan
   (`Verified Valid` / `Needs Further Review` / `Escalate` / `Request Clarification`)
   → status `verified`, kap `human_decisions` + `audit_logs`.
6. **Degradasi (±1,5 mnt)** — lihat bagian 4; tunjukkan halaman tetap berfungsi
   dengan narasi Ollama lalu template.

## 4. Degradasi (cerita ketahanan, lakukan di tahap 6 storyboard)

```bat
:: a) LLM utama gemini: default (.env LLM_PROVIDER=gemini) -> narasi "model_used" menunjukkan gemini
:: b) matikan gemini (ganti LLM_PROVIDER=ollama, restart server) -> narasi lanjut via Ollama lokal
:: c) matikan ollama juga -> tetap jalan: review = rule-fallback, penjelasan = template deterministik
```

- Provenance ditulis per tugas (`model_used`/`generated_by`), low tier MEMANG selalu template
  (desain: klaim bersih tidak butuh narasi LLM).
- LLM tidak pernah mengubah skor/tier/evidence (kontrak deterministik). Skalanya 0–85.
- Komponen `/api/health` menunjukkan status per-subsistem (`status=ok` | `degraded`).

## 5. Angka referensi untuk narasi video

- Skor runtime: poin deterministik (klinis ≤20 + finansial ≤30 + relasional ≤20 + evidence ≤15).
- Kompresi tier LAMA (25/60): 87% klaim medium → sudut cerita "mengapa kita kalibrasi".
- Kalibrasi baru: alert 5,7% @precision 0,80; tier HIGH precision 1,00 pada slice uji
  (`docs/TIER_CALIBRATION.md`), dari kalibrasi atas slice validation, test dibaca sekali.
- Batasan jujur yang boleh disebut: jendela repeat produksi 45 hari (generator v2 memakai
  46–60 hari), peta tariff v1 10 keluarga diagnosis, konteks relasional in-sample.
- Dataset & metrik ML kandidat lihat `docs/EVALUATION_REPORT.md` (AP 0.7259; recall 0.6793)
  — selalu dengan disclaimer synthetic demonstrator.

### Hasil seed terkurasi (live, siklus resi 2026-10-24)

- Submit **220/220** (ok=220, skip=0, err=0, 54,8 s) via alur produksi; drain penuh ~28 menit
  (narasi LLM termasuk); `failed=0`; LanceDB terindeks pada saat intake POST.
- Tier live: **high 4 · medium 86 · low 130** — persis desain `--dry-run`; status:
  processed 130 / review_required 90; `verified=0` (belum ada keputusan verifier — matang untuk video).
- Verifikasi per-skenario (`demo_snapshot.py`): **220/220 sesuai harapan** — 10/10 grup:
  normal 90 · unbundling 18 · upcoding 32 · repeat 14 · cloning 12 · phantom 12 ·
  prolonged 12 · inflated 16 · near_window 10 · exact_dup 4.
- Dashboard: `potential_financial_exposure` **Rp 462.306.032**; showcase HIGH = pasangan
  exact-duplicate `DEMO-DU0-1/-2` (raw 42,0) dan `DEMO-DU1-1/-2` (raw 37,0) naik ke high
  via lantai exact-duplicate — bukti relasional live (matched claim id + hari) tampil.
- Semua tier medium live bersandar bukti relasional (lantai repeat/cloning/unbundling)
  atau komposisi skor desain — nol false-positif presentasional pada run ini.

## 6. Checklist "sebelum merekam"

- [ ] `/api/health` = ok semua komponen
- [ ] `/api/analytics/dashboard` menghitung 220 klaim, tier bervariasi (bukan 87% medium)
- [ ] `GET /api/claims?tier=high` mengisi showcase (≥1 exact duplicate, ≥1 unbundling/upcoding/clone)
- [ ] Banner PRIORITAS UTAMA tampil (muncul otomatis setelah ≥1 klaim HIGH diproses — data-driven dari `/api/analytics/trend`)
- [ ] Chip pengguna topbar (avatar "RA • Verifikator" pada mockup) — belum ada di implementasi `frontend/src`; konfirmasi ke dev frontend apakah sengaja ditunda
- [ ] satu klaim contoh untuk alur live POST tersedia (id `DEMO-LIVE-1` kosong/tidak ada)
- [ ] `smoke_test.py` hijau di run sebelum rekaman
- [ ] LLM_PROVIDER sesuai kebutuhan (gemini utk narasi terbaik; ollama bila tampilan offline)

## 7. Troubleshooting

| Gejala | Sabab umum | Langkah |
|---|---|---|
| Port 8000 dipakai | server lama masih hidup | `netstat -ano \| findstr :8000` → taskkill PID; pastikan satu instance |
| Semua klaim `failed` | Postgres mati / model hilang | cek log startup ("Financial model loaded"); `scripts/train_all.py` |
| Relasional tidak menyala | klaim rujukan belum berada/di-index | seed selalu kirim klaim sumber lebih dulu (FIFO); jangan reset di tengah |
| Vector store komponen error | folder LanceDB terhapus saat hidup | Restart server (backfill dari DB) |
| Narasi lambat | LLM pertama + warmup | klaim pertama 60 s adalah one-time; klaim berikutnya ~7 s |
