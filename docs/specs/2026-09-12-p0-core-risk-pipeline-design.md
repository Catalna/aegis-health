# P0 Core Risk Pipeline Design

**Status:** Approved for implementation

## Goal

Make J-ARI's risk result deterministic, domain-consistent, traceable, and safe to explain to a BPJS verifier without changing the broader security, database, or data-generation architecture.

## Scope

- Rename the user-facing meaning of `synthesis_confidence` to `evidence_support`.
- Calculate evidence support only from deterministic evidence families.
- Prevent tariff deviation from being counted as both clinical and financial risk.
- Keep ordinary similarity out of risk scoring; only concrete repeat, cloning, or unbundling relationships contribute.
- Treat Isolation Forest and provider context as supporting evidence, not independent confirmation, in this batch.
- Use `expected reimbursement benchmark` and `claimed amount` in user-facing output.
- Validate LLM summaries against structured evidence references.
- Bump the analysis version so stale persisted results are not reused.

## Non-goals

- Authentication and RBAC.
- Full database normalization or migration.
- Blind/stress dataset generation.
- Official INA-CBG integration.
- Full UI redesign or external BPJS integration.

## Data flow

```text
claim input
  -> deterministic clinical and reimbursement evidence
  -> deterministic relational evidence
  -> evidence aggregation
  -> deterministic risk score and tier
  -> grounded explanation summary
```

The LLM may summarize evidence that already exists. It may not create a new signal, alter a score, alter a tier, or determine a recommended action.

## Scoring rules

- Clinical score contains clinical consistency and coding flags, excluding tariff deviation flags.
- Financial score contains the reimbursement benchmark deviation.
- Similarity score is non-zero only for repeat billing, cloning, or unbundling.
- Isolation Forest and provider context remain visible as behavioral context but do not add independent evidence support.
- `evidence_support` is derived from the number of independent deterministic evidence families, not from the Review Agent output.

## Versioning and compatibility

`ANALYSIS_VERSION` is incremented. Stored results from older versions are stale and must be re-run. Existing internal fields may remain temporarily where persisted data and frontend contracts require them, but labels and new evidence output use the corrected terminology.

## Verification

Tests will prove that LLM review text cannot change the score, tariff deviation is not double-counted, ordinary similarity scores zero, concrete relational findings score, stale analysis is rejected, and explanations do not cite unsupported evidence.
