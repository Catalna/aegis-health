"""Stable error categories and messages safe to expose outside the backend."""

from dataclasses import dataclass


ANALYSIS_RETRYABLE_CODE = "analysis_retryable"
ANALYSIS_RETRYABLE_MESSAGE = "Pemeriksaan gagal sementara. Silakan coba lagi."
VALIDATION_REJECTED_CODE = "validation_rejected"
VALIDATION_REJECTED_MESSAGE = "Klaim ditolak karena tidak memenuhi validasi data."
DEPENDENCY_UNAVAILABLE_CODE = "dependency_unavailable"
DEPENDENCY_UNAVAILABLE_MESSAGE = "Layanan pemeriksaan sedang tidak tersedia. Silakan coba lagi."

# Existing callers use this name; its value is deliberately the public-safe text.
ANALYSIS_FAILURE_MESSAGE = ANALYSIS_RETRYABLE_MESSAGE
INTERNAL_ANALYSIS_FAILURE_REASON = "Orchestration failed: internal error"


@dataclass(frozen=True)
class SafeFailure:
    code: str
    message: str


_SAFE_FAILURES = {
    ANALYSIS_RETRYABLE_CODE: SafeFailure(ANALYSIS_RETRYABLE_CODE, ANALYSIS_RETRYABLE_MESSAGE),
    VALIDATION_REJECTED_CODE: SafeFailure(VALIDATION_REJECTED_CODE, VALIDATION_REJECTED_MESSAGE),
    DEPENDENCY_UNAVAILABLE_CODE: SafeFailure(DEPENDENCY_UNAVAILABLE_CODE, DEPENDENCY_UNAVAILABLE_MESSAGE),
}


def safe_failure(code: str | None) -> SafeFailure:
    return _SAFE_FAILURES.get(code, _SAFE_FAILURES[ANALYSIS_RETRYABLE_CODE])


def failure_for_exception(exc: BaseException) -> SafeFailure:
    """Classify without copying exception text into persisted or public data."""
    code = getattr(exc, "error_code", None)
    if code in _SAFE_FAILURES:
        return _SAFE_FAILURES[code]
    return _SAFE_FAILURES[ANALYSIS_RETRYABLE_CODE]


def failure_for_rejection(code: str | None, reason: str | None = None) -> SafeFailure:
    if code in _SAFE_FAILURES:
        return _SAFE_FAILURES[code]
    if reason and "validation" in reason.lower():
        return _SAFE_FAILURES[VALIDATION_REJECTED_CODE]
    return _SAFE_FAILURES[ANALYSIS_RETRYABLE_CODE]
