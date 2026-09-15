"""Recursive projection of persisted analysis data safe for public clients."""

import re
from typing import Any

from backend.app.core.errors import ANALYSIS_RETRYABLE_MESSAGE
from backend.app.core.human_language import humanize_public_text


_PRIVATE_PRESENTATION_KEYS = frozenset({"model_used", "generated_by"})


_PRIVATE_ANALYSIS_KEYS = frozenset({
    "agent_errors",
    "error",
    "error_code",
    "error_detail",
    "error_message",
    "error_type",
    "exception",
    "exception_detail",
    "failure_reason",
    "fallback_error",
    "internal_error",
    "last_analysis_error",
    "raw_output",
    "stack_trace",
    "traceback",
})

_INTERNAL_ANALYSIS_CONTEXT = re.compile(
    r"""
    \b(?:localhost|127\.0\.0\.1|0\.0\.0\.0|internal[-_ ]?(?:host|service|api|db))\b
    |\b[a-z0-9-]+\.(?:internal|local)(?::\d+)?\b
    |[A-Za-z]:[\\/][^\s]+|(?<!\w)/(?:app|srv|workspace|home|tmp|var|usr|opt)(?:/[^\s]*)?
    |\b(?:sqlalchemy|asyncpg|psycopg|postgres(?:ql)?|lancedb|ollama)\b
    |file://[^\s]+
    """,
    re.IGNORECASE | re.VERBOSE,
)
_INTERNAL_ANALYSIS_WORDS = frozenset({
    "traceback", "exception", "failed", "failure", "error", "gagal", "unavailable",
    "internal", "unexpected", "unhandled", "runtime", "value", "type", "key", "json",
    "sql", "database", "connection", "timeout", "permission", "assertion",
})
_INTERNAL_ANALYSIS_COMPACT_MARKERS = (
    "traceback", "stacktrace", "callstack", "exception", "internalerror",
    "runtimeerror", "valueerror", "typeerror", "keyerror", "jsondecodeerror",
)


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def _is_private_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    return normalized in _PRIVATE_ANALYSIS_KEYS or normalized in _PRIVATE_PRESENTATION_KEYS or any(
        part in normalized
        for part in (
            "raw_output",
            "traceback",
            "stack_trace",
            "exception_detail",
            "internal_error",
            "error_detail",
            "error_message",
            "failure_reason",
            "fallback_error",
            "last_analysis_error",
        )
    )


def _contains_internal_analysis_text(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    compact = normalized.replace(" ", "")
    if any(marker in compact for marker in _INTERNAL_ANALYSIS_COMPACT_MARKERS):
        return True
    if any(token in _INTERNAL_ANALYSIS_WORDS for token in normalized.split()):
        return True
    if any(token.endswith(("error", "exception")) for token in normalized.split()):
        return True
    return bool(_INTERNAL_ANALYSIS_CONTEXT.search(value))


def public_analysis_projection(value: Any) -> Any:
    """Recursively remove private fields and redact internal-looking strings."""
    if isinstance(value, dict):
        return {
            key: public_analysis_projection(item)
            for key, item in value.items()
            if not _is_private_key(key)
        }
    if isinstance(value, list):
        return [public_analysis_projection(item) for item in value]
    if isinstance(value, str):
        value = humanize_public_text(value)
        if _contains_internal_analysis_text(value):
            return ANALYSIS_RETRYABLE_MESSAGE
    return value
