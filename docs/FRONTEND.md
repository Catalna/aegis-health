# FRONTEND.md — Alur Demo & Spesifikasi UI J-ARI

Dokumen ini merinci flow `Klaim Masuk → AI Screening → Priority Queue → Investigation → Human Decision` yang dirancang agar juri bisa melihat sistem bekerja end-to-end, bukan cuma dashboard hasil akhir. Setiap elemen di sini mengikat ke schema yang sudah didefinisikan di `AGENTS.md` — tidak ada elemen UI yang datanya belum punya sumber.

## Koreksi penting terhadap draf awal ide ini

1. **Agent timeline TIDAK butuh LangGraph.** Kita pakai sequential/paralel Python functions (PRD Section 6). Timeline tetap bisa menampilkan timestamp asli — orchestrator emit event ber-timestamp ke log/stream setiap agent selesai, frontend render sebagai timeline. Ini justru argumen lebih kuat ke juri: timestamp yang tampil adalah **eksekusi asli**, bukan animasi.
2. **"Similar Claims" bukan dari IndoBERT.** Sumbernya `sentence-transformers` + LanceDB (dan Jaccard overlap untuk exact code match, lihat MODELS.md Section 3). IndoBERT sudah di-drop dari scope — jangan disebut di narasi/demo.
3. **Graph View pakai static precomputed JSON**, bukan Neo4j live (PRD Section 9). Visual akhir bisa identik, sumbernya beda — jangan tergoda instal Neo4j "biar lebih real" di tengah development.
4. **Investigator Copilot digabung ke Explanation Agent** (lihat AGENTS.md Section 7.1) — bukan agent/fitur terpisah. UI-nya tetap ada (QA Panel dengan 4 tombol pertanyaan), tapi tidak ada LLM call baru saat tombol diklik — semua jawaban sudah dihitung sebelumnya, ditampilkan dari field yang sudah ada.
5. **Tidak ada sistem login/role 2-pihak (Faskes + BPJS).** Faskes bukan user J-ARI — di alur JKN nyata faskes submit klaim lewat sistem BPJS yang sudah ada, J-ARI beroperasi setelah data itu masuk. Faskes muncul di UI hanya sebagai atribut data (Data Sources checklist), bukan role login. Satu-satunya tampilan sistem adalah untuk BPJS Verifier — tanpa autentikasi sungguhan sama sekali untuk kebutuhan demo 4 minggu (lihat PRD Section 4).
6. **Verifier BUKAN operator yang mengetik klaim dari nol — ini kesalahan yang sempat lolos ke build.** Versi sebelumnya membuat halaman `/intake` sebagai form input manual (Patient ID, Diagnosis, Prosedur, Obat, dsb.) yang harus diisi verifier — itu bertentangan langsung dengan koreksi #5: kalau Faskes bukan user, dan klaim seharusnya sudah ada saat masuk ke J-ARI, maka verifier tidak boleh jadi orang yang "membuat" klaim tersebut. Halaman itu direstrukturisasi jadi **Incoming Claims** (Section 1 di bawah) — daftar klaim yang sudah ada, bukan formulir kosong. Kebutuhan mengisi data sintetis tetap ada, tapi dipindah jadi **Demo Data Loader** terpisah (Section 2) — tool simulasi untuk kebutuhan hackathon, bukan bagian workflow verifier yang didemokan sebagai use case utama. Narasi AI juga digeser: **"AI membantu menentukan prioritas verifikasi"**, bukan "AI memutuskan" — lihat catatan di Section 4.

## Alur layar

```
INCOMING CLAIMS (Priority Queue)
  → klik klaim → AI INVESTIGATION (auto-trigger jika belum discreening)
  → RISK ASSESSMENT → EVIDENCE → HUMAN DECISION

[terpisah, BUKAN bagian alur verifier di atas]
DEMO DATA LOADER → inject klaim sintetis ke Incoming Claims (untuk simulasi hackathon)
```

> Tidak ada layar LOGIN sungguhan (lihat koreksi #5). Kalau ingin ada "kesan" masuk aplikasi untuk framing demo, cukup landing screen sederhana tanpa validasi kredensial — bukan sistem auth, murni transisi visual.

---

## 1. Incoming Claims (Priority Queue)

**Ini pengganti "Dashboard" + "Claim Intake" versi sebelumnya — digabung jadi satu halaman**, bukan dua, supaya tidak menambah halaman tanpa alasan struktural (Dashboard dan daftar klaim masuk pada dasarnya menampilkan data yang sama: klaim + statusnya).

Tabel/list klaim dengan kolom: `claim_id`, `facility` (dengan badge kecil "via Integrasi Faskes (simulasi)" — ini yang menjawab pertanyaan "dari mana klaim ini berasal" tanpa perlu role login terpisah), `submitted_date`, **status**:
- Belum discreening → badge abu-abu "Menunggu Screening"
- Sudah discreening → badge warna sesuai `priority_tier` + skor (mis. "🔴 92 — High")

Klaim yang sudah discreening otomatis terurut berdasarkan `RiskScore.total_score` descending (priority queue sungguhan); klaim yang belum discreening dikelompokkan terpisah (mis. tab "Menunggu Screening" vs "Sudah Discreening", atau section terpisah di atas/bawah list).

**Klik satu baris klaim** → buka halaman AI Investigation (Section 3):
- Kalau klaim **belum pernah discreening** → `process_claim()` otomatis ter-trigger saat halaman dibuka, timeline live berjalan (nilai demo yang sama seperti draf awal — lihat Section 3, tidak hilang, cuma titik masuknya beda)
- Kalau klaim **sudah pernah discreening** → langsung tampilkan hasil yang sudah tersimpan (tanpa re-run), dengan opsi kecil "Jalankan ulang analisis" untuk kebutuhan demo (bukan workflow normal verifier — verifier normal tidak perlu re-run klaim yang sudah selesai diperiksa)

**Data Sources panel** (checklist statis enam item: Claim, Clinical Context, Provider History, Peer Benchmark, Historical Claims, Clinical Pathway) — dipindah jadi bagian dari detail klaim/Investigation, bukan bagian form input, karena sekarang tidak ada lagi "form" untuk ditempeli panel ini.

**Prioritas:** Must Have — pengganti langsung dari Dashboard yang sebelumnya sudah Must Have.

## 2. Demo Data Loader (Tool Terpisah, Bukan Bagian Alur Verifier)

**Ini bukan halaman yang didemokan sebagai "cara BPJS Verifier bekerja"** — ini tool internal tim untuk mengisi Incoming Claims queue dengan skenario sintetis saat demo/testing. UI yang sudah dibangun sebelumnya (form dua-mode Form/Raw JSON + tombol isi-otomatis "Klaim Normal (Wajar)", "Indikasi Upcoding", "Indikasi Cloning") **tidak perlu dibuang** — cukup dipindah ke bagian terpisah dari navigasi utama (mis. menu kecil "Demo Data Loader" atau "Simulasi Data", bukan sejajar dengan "Incoming Claims" di sidebar utama), dan narasi saat demo diubah eksplisit: *"Ini tool simulasi kami untuk hackathon, merepresentasikan data yang seharusnya datang dari integrasi sistem faskes — bukan bagian dari aplikasi yang akan dipakai BPJS Verifier."*

Submit dari tool ini **menambah klaim baru ke tabel `claims`** dengan status "Menunggu Screening" — lalu klaim itu muncul di Incoming Claims (Section 1) seperti klaim lain, tidak ada jalur pintas ke Investigation langsung dari sini. Ini penting supaya mental model tetap konsisten: bahkan klaim yang baru di-inject tetap melalui alur normal (masuk antrian dulu, baru diperiksa), bukan diproses instan dari form.

**Prioritas:** Must Have (tim butuh cara mengisi data test), tapi **eksplisit di luar workflow verifier utama** — kalau ditanya juri, jawabannya "ini tool development kami," bukan dipresentasikan sebagai fitur produk.

## 3. AI Investigation (Timeline)

Live log event dari eksekusi `process_claim()` asli:

```
13:42:01  Case Manager       Case received, validasi lolos
13:42:02  Clinical Agent     Grouper lookup dimulai
13:42:02  Financial Engine   Peer comparison dimulai
13:42:02  Fraud Agent        Similarity search dimulai
13:42:03  Clinical Agent     Selesai — grouper match_table
13:42:03  Financial Engine   Selesai — deviation +43%
13:42:04  Fraud Agent        Selesai — 6 klaim mirip ditemukan
13:42:04  Review Agent       Sintesis evidence dimulai
13:42:05  Review Agent       Selesai — strong_multi_signal
13:42:05  Risk Score Engine  Skor dihitung: 92
13:42:06  Explanation Agent  Laporan dihasilkan
```

**Implementasi:** orchestrator emit event via callback/queue setiap agent mulai & selesai (timestamp `datetime.now()` asli, bukan di-mock), frontend consume via Server-Sent Events atau polling interval pendek. Karena Clinical/Financial/Fraud jalan paralel (`asyncio.gather`), timestamp mereka akan overlap secara alami — ini justru menunjukkan paralelisme sungguhan ke juri, bukan sesuatu yang perlu disembunyikan.

**Trigger:** otomatis saat verifier membuka klaim berstatus "Menunggu Screening" dari Incoming Claims (Section 1) — bukan tombol "Analyze" yang berdiri sendiri dari sebuah form. Titik masuknya berubah, tapi mekanisme live timeline-nya tidak — nilai demo yang sama tetap ada.

**Prioritas:** Must Have untuk versi log sederhana (list timestamped, bukan animasi mewah). Progress bar visual dengan ikon berjalan (✓/⟳/○): Should Have — nilai tambahnya kosmetik, bukan struktural.

## 4. Risk Assessment — Executive Result

Kartu skor besar: `RiskScore.total_score` / 100, badge warna sesuai `priority_tier` (merah=high, kuning=medium, hijau=low), `recommended_action` dari `ClaimExplanation`.

**Banner framing wajib** di bagian atas halaman ini (dan halaman Evidence): **"AI membantu menentukan prioritas verifikasi — keputusan akhir tetap di tangan verifier BPJS."** Ini bukan sekadar disclaimer kosmetik — ini penegasan mental model yang sama dengan koreksi #6: sistem tidak "memvonis," ia membantu mengurutkan mana yang perlu diperiksa duluan. Konsisten dengan jawaban `is_this_fraud` yang sudah hard-coded di QA Panel (AGENTS.md Section 7.1) — sekarang pesan yang sama muncul di tempat yang lebih terlihat, bukan cuma tersembunyi di satu tombol Q&A.

**Prioritas:** Must Have — ini output inti sistem. Banner framing: Must Have juga (murah, satu baris teks, tapi krusial untuk mental model yang benar ke juri).

## 5. Evidence

### 5a. Risk Contribution (SHAP)

Bar chart horizontal dari `RiskScore.breakdown`, label eksplisit **"Model attribution (SHAP)"** di atasnya — label ini wajib ada supaya juri tahu ini dari model, bukan LLM (prinsip inti PRD Section 5).

### 5b. Evidence List

List dari `evidence_text` tiap agent (Clinical, Financial, Fraud), masing-masing dengan baris "Source: [nama agent/model + versi]" — provenance yang sudah didesain wajib ada di AGENTS.md prinsip #3.

### 5c. Similar Claims

List dari hasil similarity Fraud Agent, sorted descending. Klik satu item → side-by-side comparison sederhana (dua `ClaimInput` ditampilkan berdampingan, field yang beda di-highlight).

**Prioritas:** Must Have (5a, 5b, 5c list). Side-by-side comparison saat diklik: Should Have.

### 5d. Graph View

Render dari static precomputed JSON (bukan Neo4j live) — node provider/doctor/patient, edge dari klaim yang menghubungkan mereka. Highlight visual kalau `graph_cluster_anomaly_score` di atas threshold.

**Prioritas:** Should Have (sudah disepakati di PRD sejak revisi tech stack — bukan Must Have karena bergantung precompute batch yang perlu waktu implementasi tersendiri).

### 5e. AI Explanation + QA Panel

Narasi dari `ClaimExplanation.narrative_id`, dengan label eksplisit di bawahnya:

> **"Dihasilkan dari evidence yang telah diverifikasi — tidak digunakan untuk menghitung skor risiko numerik."**

Badge kecil di pojok panel menunjukkan model yang menghasilkan narasi (mis. `Generated by: qwen2.5:7b (local)` atau `Generated by: Gemini Flash (benchmark)`) — konsisten dengan prinsip provenance yang sudah dipakai di seluruh sistem (label "Model attribution (SHAP)" di 5a, label source di 5b). Murah untuk ditambahkan karena `LLMClient` sudah tahu implementasi mana yang dipanggil (PRD Section 7).

Di bawahnya, **4 tombol pertanyaan pra-set** (bukan free-text box):

```
[ Kenapa klaim ini prioritas tinggi? ]
[ Klaim mana yang paling mirip? ]
[ Apa evidence terkuat? ]
[ Apakah sistem menganggap ini fraud? ]
```

Klik tombol → tampilkan field yang sesuai dari `QAPanel` (AGENTS.md Section 7.1) — **tidak ada LLM call saat diklik**, murni menampilkan data yang sudah dihitung sebelumnya. Ini penting disampaikan sebagai keunggulan teknis saat demo, bukan disembunyikan: "jawaban ini instan karena sudah dihitung di tahap investigasi, bukan generate ulang saat Anda tanya" — itu argumen reliability yang solid.

**Prioritas:** Must Have untuk narasi + disclaimer. Must Have untuk QA Panel (karena sekarang murah — tidak ada risiko baru dibanding versi copilot terpisah).

## 6. Human Decision

Radio button: Verified Valid / Needs Further Review / Escalate / Request Clarification. Submit → catat ke audit log (reviewer, action, timestamp) sesuai PRD Section 12.

**Prioritas:** Must Have — requirement inti sejak awal.

---

## Ringkasan Prioritas (MoSCoW, gabungan seluruh layar)

| Elemen | Prioritas | Catatan |
|---|---|---|
| Incoming Claims — list + status + priority sort | Must | Pengganti Dashboard + Claim Intake lama, digabung jadi satu halaman |
| Demo Data Loader — Form + Raw JSON + quick-fill | Must (tapi di luar alur verifier) | Reuse UI yang sudah dibangun, cuma direposisi & dipindah dari nav utama |
| AI Investigation — timeline log (list) | Must | Timestamp asli dari orchestrator; trigger dari klik klaim di Incoming Claims, bukan tombol form berdiri sendiri |
| AI Investigation — progress bar animasi | Should | Nilai tambah kosmetik |
| Risk Assessment — Executive Result + banner framing | Must | Output inti + penegasan "AI membantu prioritas, bukan memutuskan" |
| Evidence — SHAP bar chart | Must | Data sudah ada di RiskScore.breakdown |
| Evidence — Evidence list + source | Must | Data sudah ada di tiap agent |
| Evidence — Similar Claims list | Must | Data sudah ada di FraudAssessment |
| Evidence — Similar Claims comparison view | Should | Interaksi tambahan |
| Evidence — Graph View | Should | Bergantung precompute batch terpisah |
| Evidence — AI Explanation + disclaimer | Must | Prinsip inti desain |
| Evidence — QA Panel (4 tombol) | Must | Murah — tidak ada LLM call baru |
| Human Decision panel + audit log | Must | Requirement inti |
| Investigator Copilot free-text | **Cut dari MVP** | Digabung QA Panel; free-text dicatat sebagai future work |
| Sistem login 2-role (Faskes+BPJS) | **Cut dari MVP** | Faskes bukan user, cuma atribut data (koreksi #5) |
| Form input manual klaim sebagai workflow verifier utama | **Cut, direposisi** | Jadi Demo Data Loader terpisah, bukan halaman utama verifier (koreksi #6) |

---

*Rujuk `AGENTS.md` untuk schema data setiap elemen di atas, dan `PRD.md` Section 11 untuk requirement level produk.*