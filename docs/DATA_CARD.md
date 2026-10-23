# Synthetic v2 Data Card

> **All generated records and labels are synthetic demonstrator data. They do not validate model performance on real BPJS claims.**

## Profile sizes

Natural time splits and additional stress sets are counted separately:

| Profile | Train | Validation | Natural test | Natural total | Enriched test | OOD stress | Total generated |
|---|---:|---:|---:|---:|---:|---:|---:|
| dev | 5,000 | 2,000 | 2,000 | 9,000 | 2,100 | 1,000 | 12,100 |
| standard | 150,000 | 50,000 | 50,000 | 250,000 | 2,100 | 5,000 | 257,100 |
| large | 500,000 | 100,000 | 100,000 | 700,000 | 2,100 | 10,000 | 712,100 |

The natural anomaly prevalence is configured at 3%. The enriched set has 150 positive claims for each of seven anomaly types plus an equal-volume normal comparison set. The OOD set holds out facility and doctor ID namespaces from the natural train split. OOD sizes are a documented demonstrator choice: 10% of natural test, bounded to 1,000–10,000 claims.

Entity pools by profile: dev 30 facilities / 150 doctors / 3,000 patients; standard 300 / 2,500 / 60,000; large 600 / 5,000 / 150,000. Natural splits share those synthetic entity namespaces to preserve repeated visits over time; OOD uses separate facility/doctor/patient namespaces.

## Claim input attributes

The exact field/type manifest is generated in each output directory as `schema.json`. Input claim rows include:

- IDs: `claim_id`, `patient_id`, `provider_id`, `doctor_id` (synthetic IDs only).
- Facility and patient context: `facility_type`, `facility_class`, `region`, `patient_age`, `patient_sex`, `service_type`.
- Clinical details: `diagnosis_primary`, `diagnosis_secondary`, `procedure_codes`, `medication_codes`, `length_of_stay`, `severity_level`, `outpatient`, `icu_indicator`, `ventilator_used`, `surgical_indicator`.
- CBG/tariff demonstrator fields: `ina_cbg_code`, `ina_cbg_severity`, `regional_base_rate`, `cost_claimed`, `special_group_cost`, `special_group_types`.
- Time: `admission_date`, `discharge_date`.

The generator currently emits 188 three-character ICD-10-style category values. This catalogue and all tariffs/CBG identifiers are **demonstrators**, not an officially validated ICD catalogue, grouper, or BPJS/Kemenkes tariff table. `severity_level` is an internal 1–4 feature; raw demonstrator `ina_cbg_severity` is stored separately (`0` outpatient; `I/II/III` inpatient).

## Separate ground truth

Each split has a distinct `*_labels` file keyed by `claim_id`, with `is_anomaly`, `anomaly_type`, `difficulty`, `scenario_family`, `group_id`, and `label_confidence`. Those columns are not present in claim input data and must not be used as model features. Relational sources and generated clones/repeats/fragments share a label-side `group_id`, and the validator rejects any group that crosses splits.

## Generation and validation

```powershell
python scripts/generate_synthetic_v2.py --profile standard --seed 42 --out data/synthetic_v2
python scripts/validate_dataset.py --input data/synthetic_v2
```

`--format csv` is available when Parquet is unavailable; the default output is Parquet plus separate labels. `data_card.md` and `schema.json` include the generator version, seed, configuration SHA-256, split counts, prevalences, assumptions, and validation checks.

## Known limitations

- Rules in the generator create both the synthetic data and its labels; results measure agreement with those rules, not detection of real-world misconduct.
- The current run is single-seed. Multi-seed grouped bootstrap evaluation remains outstanding.
- Some hard-negative patterns are deliberately legitimate, but domain review is needed before treating them as clinically or administratively representative.
- No real participant JKN data was read or written to the repository.
