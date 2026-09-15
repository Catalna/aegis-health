"""Application version constants shared without importing agent dependencies."""

ANALYSIS_VERSION = 6


def analysis_version_from_evidence(evidence_json: str | None) -> int | None:
    """Read a numeric engine version without allowing malformed evidence through."""
    if not evidence_json:
        return None
    try:
        import json
        evidence = json.loads(evidence_json)
    except (TypeError, json.JSONDecodeError):
        return None
    version = evidence.get("analysis_version") if isinstance(evidence, dict) else None
    return version if type(version) is int else None


def is_current_analysis(analysis_version: int | None, evidence_json: str | None) -> bool:
    return (
        analysis_version == ANALYSIS_VERSION
        and analysis_version_from_evidence(evidence_json) == ANALYSIS_VERSION
    )
