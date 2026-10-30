# Desain Arsitektur Agent — Koordinator Deterministik + LLM Pelapor

**Status:** design (belum implementasi) • **Dibuat:** 2026-10-27 • **Keputusan model:** TERKUNCI di `deepseek-r1:7b` (Ollama lokal) berdasarkan benchmark terukur
**Disiplin:** seluruh desain offline; TIDAK menyentuh skoring runtime / demo (freeze sampai 1 Nov); implementasi bermula pasca-1-Nov setelah gate A3 + payload A1. Tanpa PII di envelope (tak ada PSTV01).

## 1. Posisi lapisan LLM dalam portofolio

Portofolio ML **tetap tepat 2 model** + 1 pilar aturan:

```
                 ┌──────────────────────────────────────┐
                 │  KOORDINATOR (kode, deterministik)   │
                 │  kumpul envelope JSON antar divisi,  │
                 │  dedup, prioritas, jadwal            │
                 └──────┬───────────┬───────────┬──────┘
                        │           │           │
        ┌───────────────┴──┐  ┌─────┴──────┐  ┌─┴──────────────┐
        │ Divisi Aturan    │  │ Divisi Mod.1│  │ Divisi Mod.2   │
        │ (rule engine)    │  │ biaya/dev   │  │ anomali        │
        │ deviation/cadence│  │ kandidat C  │  │ kandidat v3    │
        │ /identitas       │  │ (pasca-gate)│  │ (pasca-gate)   │
        └───────┬──────────┘  └─────┬───────┘  └─┬──────────────┘
                └───────────┬───────┴────────────┘
                            ▼
              ┌─────────────────────────────┐
              │  LLM PELAPOR                │
              │  deepseek-r1:7b (Ollama)    │
              │  baca JSON → laporan        │
              └─────────────────────────────┘
```

Tiga prinsip keras:

1. **LLM = pelapor, bukan juri.** Routing, prioritas, dan agregasi semua dilakukan koordinator deterministik yang bisa diaudit. LLM tidak menghitung, tidak menskor, tidak memutus.
2. **Angka hanya berasal dari envelope.** LLM menafsirkan angka yang sudah dihitung kode; aturan prompt melarang aritmetika baru.
3. **Anti-halusinasi = lapisan pemeriksa (checker).** Output LLM yang mengandung angka/asal-usul tak terlacak dibuang — laporan dibuat ulang, tidak "diperbaiki" LLM.

## 2. Kontrak envelope JSON antar divisi

Setiap divisi menghasilkan satu envelope (bukti hidupnya: fixture benchmark `scripts/agent/llm_bench.py`):

```json
{
  "divisi": "model_biaya_kandidat_C",
  "catatan_domain": "data riil BPJS sampel 2025; parity penuh vs retrain_results.json",
  "views": {"test_semua": {"n": 340518, "mape_pct": 8.59, ...}},
  "konteks": {"r2_dialisis_rendah_karena": "tarif terkunci hampir-konstan; ..."}
}
```

Aturan kontrak: angka = angka (bukan string); kunci berlabel unit (`mape_pct`, `alert_rate_persen`); `catatan_domain` wajib (klaim dataset apa); agregat semua (tanpa PII); idempoten (regenerasi deterministik dari artefak).

## 3. LLM Pelapor — keputusan & bukti

### Keputusan: `deepseek-r1:7b`

| Metrik benchmark (6 panggilan terukur × 2 mode) | qwen3.5:9b | **deepseek-r1:7b** |
|---|---|---|
| Latensi per laporan | 128–213 s (berpikir 4.5 rb–7 rb token tiap kali) | **15–25 s** (~8× lebih cepat) |
| JSON valid (`format:"json"`) | 6/6 | 6/6 |
| Angka lewat checker ketat | 0–4/laporan | 0–4/laporan |
| Karakter pelaporan | menyalin daftar key-value | **menyusun narasi manajerial** |

Catatan jujur: dugaan awal (qwen lebih tepat) **terbukti salah** oleh data mesin lokal — keduanya sama kuat pada passthrough angka ketat, tetapi qwen ~2–3,5 menit per laporan karena berpikir tanpa henti dan gayanya dump data. Mayoritas "pelanggaran" kecil r1 ternyata konversi satuan (0,2142 → "21,4%"; 1.340.872 → "1,34 juta") — perilaku pelapor yang **lebih terbaca** untuk direktur, sehingga checker dikalibrasi menerima konversi satuan tetapi menolak angka yang benar-benar buatan. Kelemahan r1 lain yang muncul sekali: menulis sapaan fiktif ("Enyi") — ditangani checker (>Nama tidak terlacak di envelope → ditolak).

### Kontrak pemanggilan

- Endpoint: Ollama `POST /api/chat`, `stream:false`, `format:"json"` untuk mode terstruktur.
- Sampling: `temperature 0.2`, `top_p 0.8`, `num_ctx 8192`, `seed 42` (deterministis demi audit).
- System prompt (terkunci): peran *LLM Pelapor*; larangan menambah/mengubah/menghitung angka; Bahasa Indonesia; batas 120 kata; wajib menyebut divisi sumber tiap poin.

## 4. Checker anti-halusinasi (jalur kerja wajib)

1. Tarik semua angka dari laporan (regex `\d+(?:[.,]\d+)*`).
2. Setiap angka harus punya padanan di envelope, dalam bentuk mentah **atau** konversi satuan sah: ×100 (persen), ÷100, ×10⁶/÷10⁶ (juta) — toleransi (0,5% rel / 0,06 abs untuk nilai <10) untuk pembulatan dua desimal.
3. Gagal apa pun → resep: **tolak laporan**; koordinator boleh memakai templat ringkasan deterministik sebagai jaring pengaman (rangkuman dari kunci-kunci) daripada menampilkan LLM yang tak terverifikasi.

## 5. Divisi & envelope awal (sumber fixture v1)

| Divisi | Sumber envelope | Status |
|---|---|---|
| Aturan (cadence + peer) | `cadence_signal_scan.json`, `peer_signal_scan.json` | telah jadi (scan L12/L9) |
| Model 1 Biaya (C) | `eval_cost_c_parity.json` (+ views per msg tertentu) | telah jadi; runtime tetap legacy sampai gate A3 |
| Model 2 Anomali (v3) | subset report `synthetic_v2_v3` (headline, op point, per-tipe) | telah jadi; **hanya sintetis** — tak valid sebelum gate yang diperiksa |

## 6. Ordo implementasi (pasca-1-Nov)

1. Gate A3 sweep (kandidat C per-strata + go/no-go klasifier v3 — penolakan adalah hasil sah).
2. Payload A1 (E-Klaim riil pertama) → C1 profiling per-faskes → memperkaya envelope divisi aturan/model.
3. Integrasikan LLM Pelapor (r1:7b) + checker ke pipeline laporan; halaman demo LLM **setelah** kebingungan angka terverifikasi.
4. Multiseed & multi-model LLM (qwen3.5:9b sebagai kandidat analisis berat) mengikuti jalur `docs/MODELS.md` multiseed — setiap ganti penyedia model diuji ulang fixture benchmark yang sama.

## 7. Artefak bukti

- Skrip: `scripts/agent/llm_bench.py` (fixture dibangun dari artefak yang dihitung; 12 panggilan terukur + warmup + 2 sampel gaya).
- Hasil (priv ruang kerja gitignored): `backend/app/data/analysis/llm_bench_results.json`.
- Batas hasil: 3 fixture × 2 mode × 2 model pada mesin lokal dengan Ollama per 2026-10-27; bukan kesimpulan mutlak lintas tugas — angka LLM lain disetel ulang benchmark sampai ke model penyedia berbeda.
