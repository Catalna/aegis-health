# Plain-Language Interface and Analysis Output

## Goal

Make J-ARI understandable to BPJS claim officers who are not developers. The
interface and analysis output should explain what was found, why it matters,
and what the officer should do next, without exposing implementation details.

## Audience and Voice

- Formal Indonesian that sounds like a human-written work report.
- Use active voice, complete sentences, and sentence case.
- Prefer concrete facts and suggested action over internal labels.
- Do not make the system sound as if it has concluded fraud; the final decision
  remains with the human verifier.

## Terms That Stay Hidden

Do not show these in the primary interface or human-facing analysis output:

- Rule, flag, signal, or error identifiers such as `severity_med_mismatch`.
- Model names or versions such as `mistral:7b`.
- Developer terms such as queue, scanning, processed, stale, retry, API, JSON,
  vector, database, endpoint, or stack trace.
- Internal numeric codes, analysis versions, raw exception messages, or
  implementation-only metadata.

These values may remain in server logs, persisted internal fields, and
developer diagnostics.

## Preferred Vocabulary

| Internal or technical term | Human-facing term |
| --- | --- |
| queue | antrean pemeriksaan |
| pending | menunggu pemeriksaan |
| scanning | sedang diperiksa |
| processed | pemeriksaan selesai |
| review_required | perlu ditinjau petugas |
| failed | pemeriksaan belum berhasil |
| stale | pemeriksaan perlu diulang |
| retry | ulangi pemeriksaan |
| risk score | nilai risiko |
| priority tier | tingkat prioritas |
| SLA | target waktu pelayanan |
| deterministic signal / flag | temuan berdasarkan aturan pemeriksaan |
| severity_med_mismatch | perbedaan tingkat keparahan dengan biaya pengobatan |
| evidence | dasar penilaian |
| analysis | hasil pemeriksaan |

## Analysis Output Rules

Every finding should follow this order:

1. State the plain-language finding.
2. Give the relevant evidence and numbers.
3. Explain the practical meaning.
4. State that it is a recommendation when applicable.


Technical:

```text
Sinyal deterministik: severity_med_mismatch.
```

Human-facing:

```text
Temuan berdasarkan aturan pemeriksaan: tingkat keparahan yang tercatat tidak
sebanding dengan biaya pengobatan yang diajukan.
```

Technical:

```text
"severity_med_mismatch". Claimed amount Rp 4,000,000 berbanding
reimbursement benchmark perkiraan Rp 1,902,113 (perbedaan +110.3%). Faktor
utama perbedaan terhadap benchmark: jenis diagnosis.
```

Human-facing:

```text
Biaya yang diajukan sebesar Rp4.000.000 lebih tinggi 110,3% dibandingkan
perkiraan biaya penggantian sebesar Rp1.902.113. Perbedaan ini terutama
dipengaruhi oleh jenis diagnosis.
```

Technical:

```text
[Penilaian analisis tambahan (mistral:7b) — bukan sumber skor] Diagnosis
Sekunder W19 tidak biasa ditemukan bersama diagnosis utama S72.0 dan prosedur
79.35. (Flag aturan pemeriksaan tetap aktif: severity_med_mismatch)
```

Human-facing:

```text
Catatan tambahan: diagnosis sekunder W19 jarang ditemukan bersamaan dengan
diagnosis utama S72.0 dan prosedur 79.35. Pemeriksaan juga menemukan
ketidaksesuaian antara tingkat keparahan dan biaya pengobatan. Catatan ini
tidak mengubah nilai risiko.
```

## Error and Partial States

- Say what the officer can do next: “Pemeriksaan belum berhasil. Silakan ulangi
  pemeriksaan.”
- Do not show HTTP codes, exception names, model names, or raw provider errors.
- Preserve the claim data and display already available results when only one
  source or service is unavailable.
- Use “data belum lengkap” or “hasil pemeriksaan belum tersedia” instead of
  technical dependency terminology.

## Scope

- Update visible labels, statuses, buttons, empty states, notifications, error
  messages, dashboard summaries, and analysis narratives.
- Update public API messages that are rendered directly by the frontend.
- Keep database field names, route names, log messages, test fixtures, and
  internal developer documentation unchanged unless they leak to users.
- Do not change risk calculations, lifecycle transitions, or verifier decisions.

## Acceptance Criteria

- A non-developer can understand every visible status without knowing queues or
  software terminology.
- No primary UI or human-facing analysis contains rule identifiers or model
  names.
- Numeric findings retain their meaning, units, and precision appropriate for
  human reading.
- Analysis text clearly distinguishes a recommendation from a final verifier
  decision.
- Loading, empty, partial, error, retry, and stale states use the same formal,
  human-readable vocabulary.
- Existing backend behavior and frontend functionality remain unchanged.

## Verification

- Add copy contract tests for the vocabulary and prohibited technical terms.
- Test representative analysis payloads, including the three examples above.
- Run the existing backend test suite and frontend build.
- Run browser smoke checks at desktop and mobile widths and inspect the
  rendered analysis output.
