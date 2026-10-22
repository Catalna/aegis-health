"""Generate and submit a randomized, relational claim test run."""

from __future__ import annotations

import argparse
import random
import secrets
from collections import Counter
from typing import Any

import httpx

from backend.app.data.synthetic_generator import (
    generate_cloning_case,
    generate_inflated_bill_case,
    generate_normal_claim,
    generate_phantom_billing_case,
    generate_prolonged_los_case,
    generate_repeat_billing_case,
    generate_upcoding_case,
)


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_API_FIELDS = (
    "claim_id",
    "patient_id",
    "provider_id",
    "doctor_id",
    "diagnosis_primary",
    "diagnosis_secondary",
    "procedure_codes",
    "medication",
    "severity_level",
    "cost_claimed",
    "length_of_stay",
    "admission_date",
    "discharge_date",
)


def build_performance_claims(seed: int, claim_prefix: str) -> list[dict[str, Any]]:
    """Return an ordered 50-claim run with clean controls and linked anomalies."""
    random.seed(seed)

    normal_claims = [generate_normal_claim(f"{claim_prefix}-NORM-{index:02d}") for index in range(1, 25)]
    reference_claims = normal_claims[:4]
    event_groups: list[list[dict[str, Any]]] = [[claim] for claim in normal_claims[4:]]

    for index in range(1, 5):
        event_groups.append(list(generate_cloning_case(
            f"{claim_prefix}-CLONE-{index:02d}-A",
            f"{claim_prefix}-CLONE-{index:02d}-B",
        )))

    event_groups.extend(
        [generate_repeat_billing_case(f"{claim_prefix}-REPEAT-{index:02d}", reference_claims[index - 1])]
        for index in range(1, 5)
    )
    event_groups.extend(
        [generate_upcoding_case(f"{claim_prefix}-UPCODE-{index:02d}")]
        for index in range(1, 5)
    )
    event_groups.extend(
        [generate_phantom_billing_case(f"{claim_prefix}-PHANTOM-{index:02d}")]
        for index in range(1, 5)
    )
    event_groups.extend(
        [generate_prolonged_los_case(f"{claim_prefix}-LOS-{index:02d}")]
        for index in range(1, 4)
    )
    event_groups.extend(
        [generate_inflated_bill_case(f"{claim_prefix}-INFLATED-{index:02d}")]
        for index in range(1, 4)
    )

    # Referensi harus sudah tersimpan sebelum event repeat masuk ke pipeline.
    random.shuffle(reference_claims)
    random.shuffle(event_groups)
    claims = [*reference_claims]
    for event_group in event_groups:
        claims.extend(event_group)
    if len(claims) != 50:
        raise RuntimeError(f"Expected 50 claims, generated {len(claims)}")
    return claims


def claim_payload(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        field: value.isoformat() if hasattr(value := claim[field], "isoformat") else value
        for field in _API_FIELDS
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Submit a randomized 50-claim test run.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--seed", type=int, help="Seed to reproduce a prior generated run.")
    parser.add_argument("--claim-prefix", help="Unique prefix for the generated claim IDs.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    seed = args.seed if args.seed is not None else secrets.randbits(32)
    claim_prefix = args.claim_prefix or f"LIVE-{seed:08X}"
    claims = build_performance_claims(seed, claim_prefix)
    if args.dry_run:
        print({
            "generated": len(claims),
            "seed": seed,
            "claim_prefix": claim_prefix,
            "scenario_counts": dict(Counter(claim["anomaly_type"] for claim in claims)),
        })
        return 0

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30) as client:
        for claim in claims:
            response = client.post("/api/claims", json=claim_payload(claim))
            response.raise_for_status()
    print({"created": len(claims), "seed": seed, "claim_prefix": claim_prefix})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
