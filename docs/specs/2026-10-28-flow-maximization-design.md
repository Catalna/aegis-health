# Desain Maksimisasi Flow Agentic — Kontrak Envelope Terpadu + Checker Generik + Observability

**Status:** design (belum implementasi) • **Dibuat:** 2026-10-28
**Sumber penilaian:** review flow sungguhan `backend/app/agents/orchestrator.py` (Phase 0–4, provenance, fallback, generation-lock) + lapisan desain terkunci `2026-10-27-agent-hierarchy-design.md`
**Disiplin:** docs-only saat ini (freeze sampai 1 Nov — tidak menyentuh skoring/demo/runtime). Seluruh implementasi bermula pasca-1-Nov dan **masuk di sela ordo roadmap (A3 → payload A1/C1 → integrasi Pelapor) tanpa mengganti urutannya**.

## 0. Kesimpulan review flow (dasar penilaian)

Flow runtime kini sudah kokoh: deterministik-dulu (Phase 0 hard-reject + protokol exact-duplicate), 3 spesialis paralel dengan fallback per-agent + flag `partial`, provenance tiap fase (`agent_runs` status/durasi/`model_used`, audit trail, `analysis_version`, generation-lock), scoring terisolasi non-LLM (FR-4.2/4.3/4.4), QA Panel deterministik (0 LLM call), SSE timeline, dan LanceDB indexing pasca-analisis. **Tulang punggung tidak perlu ditukar.** Lever maksimisasi bukan "tambah agent", melainkan: **kontrak + checker + observability**.

## F1 — Kontrak envelope terpadu untuk semua permukaan LLM

**Kini:** envelope JSON (§2 design 2026-10-27) matang hanya di jalur Pelapor (fixture benchmark). Runtime mengirim pydantic dump ke 3 titik LLM yang ada: `clinical_agent.py:187` (Lapis 2), `review_agent.py:193`, `explanation_agent.py:315`. Guard tiap titik bersifat ad-hoc.

**Sasaran:** modul baru `backend/app/core/envelope.py`.

- `to_envelope(divisi, catatan_domain, data, unit_labels) -> dict` dengan `env_version: 1`.
- Aturan kontrak diwarisi design §2: angka = angka (bukan string), kunci berlabel satuan (`*_pct`, `*_rupiah`), `catatan_domain` wajib, agregat saja (0 PII — tanpa PSTV01), regenerasi idempoten.
- Setiap divisi spesialis (klinis, finansial, fraud/aturan) memproyeksikan assessment-nya ke envelope **sebelum** prompt LLM apa pun; envelope tersimpan di output `agent_runs` (kolom JSON ada) → provenance ganda.
- Review, Explanation, QA, dan Pelapor ke depannya **hanya boleh membaca envelope**, tidak pernah membaca benda mentah pydantic.
- Manfaat: satu sumber kebenaran angka untuk narasi dan checker; fixture benchmark yang sama dengan jalur Pelapor.

**Kapan:** kontrak/spec + fixture bisa dibangun offline kini (dari artefak kandidat, gitignored); pengujian runtime menyusul pada gelombang integrasi Pelapor.

## F2 — Checker anti-halusinasi generik (bukan hanya Pelapor)

**Kini:** desain checker (§4 design 2026-10-27) hanya membungkus Pelapor; Review dan Explanation dijaga guard granular (FR-4.2/4.3/4.4) tapi tidak ada pemisahan angka seragam.

**Sasaran:** modul `backend/app/core/llm_guard.py` — satu implementasi, dipakai semua titik.

1. Tarik angka dari teks output: regex `\d+(?:[.,]\d+)*`.
2. Tiap angka wajib berpadanan di envelope — mentah **atau** konversi satuan sah (×100 persen, ÷100, ×10⁶/÷10⁶ juta) dengan toleransi 0,5% rel / 0,06 absolut untuk nilai <10 (dua-desimal).
3. Guard nama fiktif: entitas yang tak terlacak di envelope → tolak (sejarah: sapaan "Enyi" pada r1).
4. Gagal apa pun → **tolak output**; jalan deterministik (template) menggantikan, tidak pernah LLM "memperbaiki" kembali.
5. Mode per peran: Pelapor `strict`; Review/Explanation memeriksa angka yang dikutip; QA Panel lolos (deterministik murni).

**Kapan:** bersama gelombang integrasi Pelapor (ordo design §6 langkah 3), tetapi spesifikasi & unit-test checker bisa ditulis offline kini.

## F3 — Benchmark per-slot peran (model per divisi belum pernah diukur)

**Kini:** keputusan r1:7b terukur hanya untuk peran Pelapor. Slot Review/Explanation/Lapis-2 di `.env` (`qwen2.5:3b`, fallback `llama3.2:3b`) adalah warisan konfigurasi, bukan hasil ukur. Kerangka `reasoning_source` di review_agent menyambut r1 bila A/B mendukung.

**Sasaran:** perluas pola `scripts/agent/llm_bench.py`:

- Fixture envelope per peran (dari F1) × kandidat lokal sama (`qwen2.5:3b`, `mistral:7b`, `llama3.2:3b`, `deepseek-r1:7b`, `qwen3.5:9b`).
- Metrik: latensi, validitas schema, tingkat lolos checker, guard-hit, panel gaya.
- Wajib dijalankan: setiap pergeseran model/provider slot (aturan yang sama seperti pengujian 3×2×6 Pelapor); pertama kali pasca-gate A3.
- Artefak: `backend/app/data/analysis/role_bench_results.json` (gitignored).

## F4 — Lapisan Koordinator tingkat portofolio

**Kini:** orkestrasi per-klaim sudah matang; lapisan lintas-klaim dari desain (prioritas lintas-klaim deterministik) belum ada.

**Sasaran:** `backend/app/core/portfolio_coordinator.py` — deterministik murni, nol LLM:

- Input: himpunan klaim terproses dalam horizon laporan.
- Prioritas: `total_score × band dampak finansial` (pakai `actual_cost`/`predicted_cost_upper` yang sudah disimpan), dedup lintas klaim (graf exact-duplicate), penuh budget verifier; dasar keputusan terekam.
- Output: envelope portofolio (distribusi tier, top-N, dasar prioritas per butir) → Pelapor hanya menaruh narasi di atasnya.
- Disiplin: pada DB demo (220 klaim) ini **presentational** — tidak pernah dipakai penyetelan/kalibrasi (aturan DECISIONS 2026-10-24).

**Kapan:** pasca payload A1 → C1 (perlu data riil per-faskes); laporan portofolio demo presentational boleh lebih dini (hardcoded, tanpa apa pun yang di-tuning).

## F5 — Flow health digest (observability)

**Kini:** data sudah lengkap di `agent_runs` (status, durasi, fallback, `model_used`) tapi tak pernah diagregasi.

**Sasaran:** endpoint kecil `GET /api/system/agent-health` (backend, pasca-1-Nov): tingkat fallback per agent (7 hari), p50/p95 durasi per fase, distribusi `model_used`, `partial` rate, jumlah kejadian fallback & `error` pada timeline SSE. Peran: bukti keandalan langsung untuk pemantik/penilai, peringatan dini degradasi model lokal.

## F6 — Mikro: prefix-cache Ollama (opsional)

System prompt + blok header stabil (Pelapor memakai prompt terkunci) → persistent prefix mempercepat token berulang di Ollama. Hanya diadopsi bila pengukuran menunjukkan manfaat ≥10%; tak ada semantik yang berubah.

## Anti-sasaran (dinyatakan eksplisit)

- **Tidak menambah** loop multi-agent debate / self-critique per fase / arbitrase LLM antar agent — menggerus determinisme, menambah latensi, menyimpang dari "LLM = pelapor".
- **Tidak menambah agent baru** selain 3 spesialis + Review + Explanation + Pelapor.
- Envelope tidak pernah memuat angka turunan data riil sebelum gate A3; tanpa PII selamanya.
- Tidak mengurangi lapisan deterministik apa pun demi LLM.

## Jadwal tanpa membalik urutan roadmap

| Item | Gelombang | Keterangan |
|---|---|---|
| F1 kontrak + F2 checker (spec & unit-test offline) | kini (docs) → ikut integrasi Pelapor pasca-1-Nov | ordo design §6 langkah 3 |
| F3 benchmark per-slot | pasca-gate A3; ulang tiap pergeseran provider | menggantikan pemilihan warisan `.env` |
| F4 koordinator portofolio | pasca payload A1 → C1 | demo presentational boleh lebih awal |
| F5 flow health | backend kecil pasca-1-Nov | endpoint baca-saja, tidak menyentuh scoring |
| F6 prefix-cache | opsional, setelah F1 | ambang: manfaat terukur ≥10% |

## Bukti pendukung

- Flow: `backend/app/agents/orchestrator.py` (process_claim, run_with_fallback, `_save_agent_run`, `_audit`, generation-lock `analysis_generation`).
- Titik LLM runtime: `clinical_agent.py:187`, `review_agent.py:193`, `explanation_agent.py:315` (+ Pelapor menjadi titik ke-4).
- Desain induk: `docs/specs/2026-10-27-agent-hierarchy-design.md` (envelope §2, checker §4, ordo §6).
- Pengukuran induk: `scripts/agent/llm_bench.py` + `backend/app/data/analysis/llm_bench_results.json` (r1:7b 15–25 detik/laporan, JSON 6/6).
