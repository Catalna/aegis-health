"""Persistence and synthetic data card generation for v2 bundles."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .generator import PROFILES
from .validation import validate_synthetic_v2


INPUT_SCHEMA = {
    "claim_id": "synthetic string identifier",
    "patient_id": "synthetic string identifier",
    "provider_id": "synthetic string identifier",
    "doctor_id": "synthetic string identifier",
    "facility_type": "category",
    "facility_class": "category",
    "region": "category",
    "patient_age": "integer years",
    "patient_sex": "synthetic category",
    "diagnosis_primary": "ICD-10 3-character demonstrator category",
    "diagnosis_secondary": "list[ICD-10 demonstrator category]",
    "procedure_codes": "list[ICD-9-CM demonstrator code]",
    "length_of_stay": "integer days",
    "severity_level": "internal ordinal 1-4; not an official INA-CBG code",
    "ina_cbg_code": "SIM-prefixed demonstrator code, not an official grouper result",
    "ina_cbg_severity": "0 outpatient; I/II/III inpatient demonstrator mapping",
    "outpatient": "boolean",
    "regional_base_rate": "demonstrator currency amount",
    "cost_claimed": "demonstrator currency amount including synthetic noise",
    "special_group_cost": "demonstrator special-group component amount",
    "admission_date": "ISO date within split window",
    "discharge_date": "ISO date",
}
LABEL_SCHEMA = {
    "claim_id": "synthetic claim identifier; join key",
    "is_anomaly": "boolean synthetic ground truth",
    "anomaly_type": "synthetic anomaly type or none",
    "difficulty": "easy/medium/hard/none",
    "scenario_family": "synthetic scenario family",
    "group_id": "group kept wholly within one split",
    "label_confidence": "synthetic confidence weight, not a probability of real-world fraud",
}


def _data_card(bundle: dict[str, Any], config_hash: str, report: dict[str, Any]) -> str:
    lines = [
        "# Synthetic Dataset v2 — Data Card",
        "",
        "> **Synthetic demonstrator data only. This dataset does not validate performance on real BPJS claims.**",
        "",
        f"- Generator: `synthetic-v2-demonstrator`",
        f"- Profile: `{bundle['profile']}`",
        f"- Seed: `{bundle['seed']}`",
        f"- Configuration SHA-256: `{config_hash}`",
        "- Calibration: illustrative INA-CBG-like demonstrator amounts; not official tariffs or a production grouper.",
        "- Splitting: train months 0–17, validation months 18–20, natural test months 21–23; related cases share a label-side group ID.",
        "- Known limitations: synthetic rules create the labels; out-of-family cases assess generator transfer only, not real-world generalization.",
        "",
        "## Split counts",
        "",
        "| Split | Claims | Anomalies | Prevalence |",
        "|---|---:|---:|---:|",
    ]
    for split in ("train", "validation", "test"):
        labels = bundle[split]["labels"]
        anomalies = sum(bool(label["is_anomaly"]) for label in labels)
        total = len(labels)
        lines.append(f"| {split} | {total} | {anomalies} | {anomalies / total:.2%} |" if total else f"| {split} | 0 | 0 | n/a |")
    lines.extend(["", "## Ground truth by split", ""])
    for split in ("train", "validation", "test"):
        lines.append(f"### {split}")
        for label, n in sorted(Counter(item["anomaly_type"] for item in bundle[split]["labels"]).items()):
            lines.append(f"- `{label}`: {n}")
        lines.append("")
    lines.extend([
        "## Validation",
        "",
        f"- Status: `{report['status']}`",
        f"- Group count: {report['group_count']}",
        "- KS comparisons: " + ", ".join(f"`{key}`={'pass' if value['passed'] else 'fail'}" for key, value in report["distribution_checks"].items()),
        "- Synthetic labels are kept in separate `*_labels` files and must not be used as model input features.",
        "",
    ])
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})


def write_synthetic_v2(bundle: dict[str, Any], out_dir: Path, file_format: str = "parquet") -> dict[str, Any]:
    if file_format not in {"parquet", "csv", "both"}:
        raise ValueError(f"unsupported output format: {file_format}")
    report = validate_synthetic_v2(bundle)
    out_dir.mkdir(parents=True, exist_ok=True)
    config_json = json.dumps({"profile": bundle["profile"], "seed": bundle["seed"], "profiles": PROFILES}, sort_keys=True)
    config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
    for split in ("train", "validation", "test"):
        claims = bundle[split]["claims"]
        labels = bundle[split]["labels"]
        if file_format in {"csv", "both"}:
            _write_csv(out_dir / f"{split}.csv", claims)
            _write_csv(out_dir / f"{split}_labels.csv", labels)
        if file_format in {"parquet", "both"}:
            try:
                import pandas as pd

                pd.DataFrame.from_records(claims).to_parquet(out_dir / f"{split}.parquet", index=False)
                pd.DataFrame.from_records(labels).to_parquet(out_dir / f"{split}_labels.parquet", index=False)
            except Exception as exc:
                raise RuntimeError(
                    "Parquet output requires a working PyArrow installation; "
                    "use --format csv until the environment can load PyArrow."
                ) from exc
    metadata = {
        "dataset_version": bundle["dataset_version"],
        "seed": bundle["seed"],
        "profile": bundle["profile"],
        "config_sha256": config_hash,
        "input_schema": INPUT_SCHEMA,
        "label_schema": LABEL_SCHEMA,
        "synthetic_only": True,
        "tariff_table": "demonstrator; not official INA-CBG tariff/grouper",
    }
    (out_dir / "schema.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "data_card.md").write_text(_data_card(bundle, config_hash, report), encoding="utf-8")
    return {**report, "config_sha256": config_hash, "output_dir": str(out_dir)}


def load_synthetic_v2(input_dir: Path) -> dict[str, Any]:
    """Load generated CSV or Parquet splits for validation; labels remain separate."""
    schema_path = input_dir / "schema.json"
    if not schema_path.is_file():
        raise FileNotFoundError(f"missing synthetic-v2 schema metadata: {schema_path}")
    metadata = json.loads(schema_path.read_text(encoding="utf-8"))
    bundle: dict[str, Any] = {
        "dataset_version": metadata["dataset_version"],
        "profile": metadata["profile"],
        "seed": metadata["seed"],
    }
    for split in ("train", "validation", "test"):
        input_path = input_dir / f"{split}.parquet"
        label_path = input_dir / f"{split}_labels.parquet"
        if not input_path.exists():
            input_path, label_path = input_dir / f"{split}.csv", input_dir / f"{split}_labels.csv"
        if not input_path.is_file() or not label_path.is_file():
            raise FileNotFoundError(f"missing {split} claims or separate ground-truth file")
        if input_path.suffix == ".csv":
            with input_path.open(newline="", encoding="utf-8") as stream:
                claims = list(csv.DictReader(stream))
            with label_path.open(newline="", encoding="utf-8") as stream:
                labels = list(csv.DictReader(stream))
            for claim in claims:
                for field in ("diagnosis_secondary", "procedure_codes"):
                    claim[field] = json.loads(claim[field])
                for field in ("patient_age", "length_of_stay", "severity_level"):
                    claim[field] = int(claim[field])
                for field in ("regional_base_rate", "cost_claimed", "special_group_cost"):
                    claim[field] = float(claim[field])
            for label in labels:
                label["is_anomaly"] = label["is_anomaly"].lower() == "true"
                label["label_confidence"] = float(label["label_confidence"])
        else:
            try:
                import pandas as pd

                claims = pd.read_parquet(input_path).to_dict(orient="records")
                labels = pd.read_parquet(label_path).to_dict(orient="records")
            except Exception as exc:
                raise RuntimeError("Unable to read Parquet: PyArrow must be installed and allowed by the OS policy") from exc
        bundle[split] = {"claims": claims, "labels": labels}
    return bundle
