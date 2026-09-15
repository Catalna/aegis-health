"""Pure claim relationship scoring without vector-store or model imports."""

from datetime import date


W_CODE, W_COST, W_PROVIDER, W_TEMPORAL, W_PATIENT = 0.40, 0.30, 0.15, 0.10, 0.05
RELATIONSHIP_WINDOW_DAYS = 45


def cost_proximity(cost_a: float, cost_b: float) -> float:
    """1.0 = biaya hampir identik; 0.0 = sangat berbeda."""
    if cost_a <= 0 and cost_b <= 0:
        return 0.0
    hi = max(cost_a, cost_b)
    if hi <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(cost_a - cost_b) / hi)


def temporal_proximity(days_apart: int | None) -> float:
    """1.0 jika <=7 hari, meluruh ke 0 di 90 hari; None = 0."""
    if days_apart is None:
        return 0.0
    days = max(0, days_apart)
    if days <= 7:
        return 1.0
    return max(0.0, 1.0 - (days - 7) / 83)


def composite_similarity(
    code_sim: float,
    cost_prox: float,
    same_provider: bool,
    same_patient: bool,
    days_apart: int | None,
) -> float:
    """Skor kemiripan mencurigakan 0-1 dari faktor relasional."""
    return (
        W_CODE * code_sim
        + W_COST * cost_prox
        + W_PROVIDER * (1.0 if same_provider else 0.0)
        + W_TEMPORAL * temporal_proximity(days_apart)
        + W_PATIENT * (1.0 if same_patient else 0.0)
    )


def is_investigation_candidate(
    code_similarity: float,
    cost_proximity: float,
    same_provider: bool,
    same_patient: bool,
    days_apart: int | None,
) -> bool:
    """Return whether two claims have a relationship worth investigating."""
    if days_apart is None or days_apart > RELATIONSHIP_WINDOW_DAYS:
        return False
    if same_patient:
        return code_similarity >= 0.8
    return same_provider and code_similarity > 0.9 and cost_proximity > 0.95


def _days_between(date_a: str, date_b: str) -> int | None:
    if not date_a or not date_b:
        return None
    try:
        left = date.fromisoformat(str(date_a)[:10])
        right = date.fromisoformat(str(date_b)[:10])
        return abs((left - right).days)
    except ValueError:
        return None


def compute_jaccard_similarity(claim1: dict, claim2: dict) -> float:
    """Kemiripan eksak kode medis (diagnosis + prosedur) antara dua klaim."""
    def codes(claim: dict) -> set:
        secondary = claim.get("diagnosis_secondary", [])
        if isinstance(secondary, str):
            secondary = [item.strip() for item in secondary.split(",") if item.strip()]
        procedures = claim.get("procedure_codes", [])
        if isinstance(procedures, str):
            procedures = [item.strip() for item in procedures.split(",") if item.strip()]
        values = {claim.get("diagnosis_primary", "")} | set(secondary) | set(procedures)
        values.discard("")
        return values

    left, right = codes(claim1), codes(claim2)
    if not left and not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0
