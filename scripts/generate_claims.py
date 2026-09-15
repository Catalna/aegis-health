"""Generate a repeatable claim dataset through the claims HTTP API.

The default mode only creates claims. Use ``--analyze`` explicitly to also
request analysis for claims created during this run.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import date, timedelta
from typing import Any, Iterable
from urllib.parse import quote

import httpx


DEFAULT_SEED = 20260913
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_PREFIX = "GEN-CLAIM"
MIN_COUNT = 8

_DIAGNOSES = ("I10", "J18.9", "E11.9", "I21.9", "K35.8", "N18.3")
_PROCEDURES = {
    "I10": ("89.52",),
    "J18.9": ("89.52",),
    "E11.9": ("99.04",),
    "I21.9": ("36.10", "89.52"),
    "K35.8": ("47.09",),
    "N18.3": ("39.95",),
}

GROUP_NAMES = (
    "same_facility_diagnosis",
    "same_diagnosis_across_facilities",
    "same_facility_across_diagnoses",
    "mixed_controls",
)


def _minimum_count(value: str) -> int:
    parsed = int(value)
    if parsed < MIN_COUNT:
        raise argparse.ArgumentTypeError(f"must be at least {MIN_COUNT} to satisfy all relationship groups")
    return parsed


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.casefold()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic related claims through POST /api/claims."
    )
    parser.add_argument(
        "--count",
        type=_minimum_count,
        default=100,
        help=f"Number of claims (minimum {MIN_COUNT}, default: 100).",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Deterministic random seed (default: {DEFAULT_SEED}).")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", DEFAULT_BASE_URL), help=f"Backend URL (default: {DEFAULT_BASE_URL}).")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help=f"Claim ID prefix (default: {DEFAULT_PREFIX}).")
    parser.add_argument(
        "--analyze",
        nargs="?",
        const=True,
        default=False,
        type=_parse_bool,
        help="Request analysis; accepts --analyze or --analyze=true|false (default: false/pending-only).",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Reset only existing generated claims whose IDs start with PREFIX-; requires --yes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the individual prefix-scoped cleanup DELETE requests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate claims without making HTTP requests.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds (default: 30).")
    return parser


def _group_sizes(count: int) -> tuple[int, int, int, int]:
    base, remainder = divmod(count, len(GROUP_NAMES))
    return tuple(base + (index < remainder) for index in range(len(GROUP_NAMES)))


def _claim_id(rng: random.Random, prefix: str, used: set[str]) -> str:
    while True:
        candidate = f"{prefix}-{rng.getrandbits(40):010X}"
        if candidate not in used:
            used.add(candidate)
            return candidate


def _make_claim(
    rng: random.Random,
    claim_id: str,
    provider_id: str,
    diagnosis: str,
    cost: float,
    index: int,
) -> dict[str, Any]:
    admission = date(2026, 1, 1) + timedelta(days=rng.randrange(300))
    length_of_stay = rng.randint(1, 14)
    procedure_codes = _PROCEDURES.get(diagnosis, ("89.52",))
    return {
        "claim_id": claim_id,
        "patient_id": f"PAT-GEN-{index:05d}-{rng.getrandbits(24):06X}",
        "provider_id": provider_id,
        "doctor_id": f"DR-{provider_id}-{rng.randrange(1000, 10000)}",
        "diagnosis_primary": diagnosis,
        "diagnosis_secondary": [],
        "procedure_codes": list(procedure_codes),
        "medication": [],
        "severity_level": rng.randint(1, 4),
        "cost_claimed": round(cost, 2),
        "length_of_stay": length_of_stay,
        "admission_date": admission.isoformat(),
        "discharge_date": (admission + timedelta(days=length_of_stay)).isoformat(),
    }


def generate_claims(count: int = 100, seed: int = DEFAULT_SEED, prefix: str = DEFAULT_PREFIX) -> list[dict[str, Any]]:
    """Build deterministic claims in four contiguous relationship groups."""
    if count < MIN_COUNT:
        raise ValueError(f"count must be at least {MIN_COUNT} to satisfy all relationship groups")
    prefix = prefix.strip()
    if not prefix:
        raise ValueError("prefix must not be empty")

    rng = random.Random(seed)
    used_ids: set[str] = set()
    claims: list[dict[str, Any]] = []
    group_sizes = _group_sizes(count)
    index = 0

    # Shared facility and diagnosis make cost variation the only deliberate signal.
    for group_index, group_size in enumerate(group_sizes):
        for offset in range(group_size):
            claim_id = _claim_id(rng, prefix, used_ids)
            if group_index == 0:
                provider_id = "FAC-GROUP-COST"
                diagnosis = "I10"
                cost = 4_000_000 + (offset * 375_000) + rng.randrange(10_000)
            elif group_index == 1:
                provider_id = f"FAC-GROUP-DX-{offset:03d}"
                diagnosis = "J18.9"
                cost = 3_000_000 + rng.randrange(1_500_000)
            elif group_index == 2:
                provider_id = "FAC-GROUP-FACILITY"
                diagnosis = _DIAGNOSES[offset % len(_DIAGNOSES)]
                cost = 2_000_000 + rng.randrange(8_000_000)
            else:
                provider_id = f"FAC-CONTROL-{offset:03d}"
                diagnosis = _DIAGNOSES[(offset + rng.randrange(len(_DIAGNOSES))) % len(_DIAGNOSES)]
                cost = 1_000_000 + rng.randrange(12_000_000)

            claims.append(_make_claim(rng, claim_id, provider_id, diagnosis, cost, index))
            index += 1

    return claims


def relationship_invariants(claims: list[dict[str, Any]]) -> dict[str, bool]:
    """Return checks for the four generated blocks, including small counts."""
    sizes = _group_sizes(len(claims))
    blocks: list[list[dict[str, Any]]] = []
    start = 0
    for size in sizes:
        blocks.append(claims[start:start + size])
        start += size

    cost_group, diagnosis_group, facility_group, controls = blocks
    return {
        "same_facility_diagnosis_different_costs": (
            len(cost_group) >= 2
            and len({claim["provider_id"] for claim in cost_group}) == 1
            and len({claim["diagnosis_primary"] for claim in cost_group}) == 1
            and len({claim["cost_claimed"] for claim in cost_group}) == len(cost_group)
        ),
        "same_diagnosis_across_facilities": (
            len(diagnosis_group) >= 2
            and len({claim["diagnosis_primary"] for claim in diagnosis_group}) == 1
            and len({claim["provider_id"] for claim in diagnosis_group}) == len(diagnosis_group)
        ),
        "same_facility_across_diagnoses": (
            len(facility_group) >= 2
            and len({claim["provider_id"] for claim in facility_group}) == 1
            and len({claim["diagnosis_primary"] for claim in facility_group}) > 1
        ),
        "mixed_controls_have_unique_facility_diagnosis_pairs": len({
            (claim["provider_id"], claim["diagnosis_primary"]) for claim in controls
        }) == len(controls),
    }


def _response_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return str(body)


def cleanup_claims(
    prefix: str,
    *,
    base_url: str,
    confirm: bool,
    timeout: float,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Reset matching generated claims through individual API DELETE calls.

    The backend's DELETE route resets a claim's analysis state; it does not
    hard-delete the record. Matching is narrowed locally to IDs beginning
    with the exact generated prefix, even though the list API search is broad.
    """
    prefix = prefix.strip()
    if not prefix:
        raise ValueError("prefix must not be empty")

    owns_client = client is None
    http_client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
    candidate_ids: list[str] = []
    failures: list[dict[str, str]] = []
    try:
        skip = 0
        while True:
            try:
                response = http_client.get(
                    "/api/claims",
                    params={"q": f"{prefix}-", "skip": skip, "limit": 1000, "sort": "id"},
                )
            except httpx.HTTPError as exc:
                failures.append({"operation": "list", "error": str(exc)})
                break
            if not 200 <= response.status_code < 300:
                failures.append({
                    "operation": "list",
                    "status": str(response.status_code),
                    "error": _response_detail(response),
                })
                break

            try:
                payload = response.json()
            except ValueError:
                failures.append({"operation": "list", "error": "API returned invalid JSON"})
                break
            items = payload.get("items", [])
            candidate_ids.extend(
                item["claim_id"]
                for item in items
                if isinstance(item, dict)
                and isinstance(item.get("claim_id"), str)
                and item["claim_id"].startswith(f"{prefix}-")
            )
            skip += len(items)
            if not items or skip >= payload.get("total", skip):
                break

        candidate_ids = list(dict.fromkeys(candidate_ids))
        result: dict[str, Any] = {
            "mode": "cleanup",
            "prefix": prefix,
            "matched": len(candidate_ids),
            "candidate_claim_ids": candidate_ids,
            "confirmation_required": not confirm,
            "reset": 0,
            "failed": len(failures),
            "failures": failures,
            "operation": "individual DELETE /api/claims/{claim_id} reset calls",
        }
        if failures:
            result["aborted"] = True
            result["message"] = "Cleanup aborted because prefix discovery failed; no DELETE requests sent."
            return result
        if not confirm:
            result["aborted"] = False
            result["message"] = "No DELETE requests sent. Re-run with --cleanup --yes to confirm these exact IDs."
            return result

        for claim_id in candidate_ids:
            try:
                response = http_client.delete(f"/api/claims/{quote(claim_id, safe='')}")
            except httpx.HTTPError as exc:
                failures.append({"claim_id": claim_id, "error": str(exc)})
                continue
            if 200 <= response.status_code < 300:
                result["reset"] += 1
            else:
                failures.append({
                    "claim_id": claim_id,
                    "status": str(response.status_code),
                    "error": _response_detail(response),
                })
        result["failed"] = len(failures)
        result["failures"] = failures
        result["aborted"] = False
        result["message"] = "Prefix-scoped cleanup completed through individual API reset calls."
        return result
    finally:
        if owns_client:
            http_client.close()


def _summary(
    *,
    args: argparse.Namespace,
    claims: list[dict[str, Any]],
    mode: str,
    created: int = 0,
    duplicates: list[str] | None = None,
    failures: list[dict[str, str]] | None = None,
    analyzed: int = 0,
    analysis_failures: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    sizes = _group_sizes(len(claims))
    return {
        "mode": mode,
        "base_url": args.base_url.rstrip("/"),
        "prefix": args.prefix,
        "seed": args.seed,
        "requested": args.count,
        "generated": len(claims),
        "created": created,
        "duplicates": len(duplicates or []),
        "duplicate_claim_ids": duplicates or [],
        "failed": len(failures or []),
        "failures": failures or [],
        "analyze_requested": args.analyze,
        "analyzed": analyzed,
        "analysis_failed": len(analysis_failures or []),
        "analysis_failures": analysis_failures or [],
        "relationship_groups": dict(zip(GROUP_NAMES, sizes)),
        "relationship_invariants": relationship_invariants(claims),
    }


def submit_claims(
    claims: Iterable[dict[str, Any]],
    *,
    base_url: str,
    analyze: bool,
    timeout: float,
    client: httpx.Client | None = None,
) -> tuple[int, list[str], list[dict[str, str]], int, list[dict[str, str]]]:
    """POST claims and optionally analyze only claims created in this run."""
    owns_client = client is None
    http_client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
    created = 0
    duplicates: list[str] = []
    failures: list[dict[str, str]] = []
    analyzed = 0
    analysis_failures: list[dict[str, str]] = []
    try:
        for claim in claims:
            claim_id = claim["claim_id"]
            try:
                response = http_client.post("/api/claims", json=claim)
            except httpx.HTTPError as exc:
                failures.append({"claim_id": claim_id, "error": str(exc)})
                continue

            if 200 <= response.status_code < 300:
                created += 1
            elif response.status_code == 409:
                duplicates.append(claim_id)
                continue
            else:
                failures.append({
                    "claim_id": claim_id,
                    "status": str(response.status_code),
                    "error": _response_detail(response),
                })
                continue

            if not analyze:
                continue
            try:
                analysis_response = http_client.post("/api/claims/analyze", json=claim)
            except httpx.HTTPError as exc:
                analysis_failures.append({"claim_id": claim_id, "error": str(exc)})
                continue
            if 200 <= analysis_response.status_code < 300:
                analyzed += 1
            else:
                analysis_failures.append({
                    "claim_id": claim_id,
                    "status": str(analysis_response.status_code),
                    "error": _response_detail(analysis_response),
                })
    finally:
        if owns_client:
            http_client.close()
    return created, duplicates, failures, analyzed, analysis_failures


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cleanup and args.dry_run:
        parser.error("--cleanup cannot be combined with --dry-run; dry-run must make zero HTTP requests")
    if args.yes and not args.cleanup:
        parser.error("--yes requires --cleanup")

    if args.cleanup:
        if args.analyze:
            parser.error("--cleanup cannot be combined with --analyze")
        try:
            summary = cleanup_claims(
                args.prefix,
                base_url=args.base_url,
                confirm=args.yes,
                timeout=args.timeout,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 2 if summary["confirmation_required"] else (1 if summary["failed"] else 0)

    try:
        claims = generate_claims(args.count, args.seed, args.prefix)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps(_summary(args=args, claims=claims, mode="dry-run"), indent=2, sort_keys=True))
        return 0

    created, duplicates, failures, analyzed, analysis_failures = submit_claims(
        claims,
        base_url=args.base_url,
        analyze=args.analyze,
        timeout=args.timeout,
    )
    summary = _summary(
        args=args,
        claims=claims,
        mode="api",
        created=created,
        duplicates=duplicates,
        failures=failures,
        analyzed=analyzed,
        analysis_failures=analysis_failures,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures or analysis_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
