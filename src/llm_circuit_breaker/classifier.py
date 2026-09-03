"""API Error Classifier for LLM Provider Calls.

Maps HTTP status codes, exception payloads, and network errors into
structured failure classifications, preserving the V1 interface while
providing hierarchical taxonomy for the V2 Circuit Breaker and Routing engines.
"""

from __future__ import annotations

import email.utils
import time
from typing import Any, Dict, Optional

from llm_circuit_breaker.models import (
    ClassifiedError,
    FailureCategory,
    FailureClassification,
    FailoverReason,
)

_BILLING_PATTERNS = [
    "insufficient credits",
    "credit balance",
    "billing",
    "payment required",
    "out of credits",
    "usage limit reached",
    "monthly spending cap",
]

_DEPRECATION_PATTERNS = [
    "deprecated",
    "decommissioned",
    "model does not exist",
    "not found",
    "model_not_found",
    "has been removed",
    "is no longer available",
    "is not found for api version",
]

_UPSTREAM_429_PATTERNS = [
    "temporarily rate-limited upstream",
    "upstream_provider_shared_pool",
    "provider returned error",
    "rate limit exceeded: free-models-per-day",
    "daily",
    "quota exceeded",
]

_WAF_PATTERNS = [
    "cloudflare",
    "security challenge",
    "attention required",
    "error 1010",
    "error 1015",
    "error 1020",
]

_SSL_PATTERNS = [
    "certificate verify failed",
    "self signed certificate",
    "sslcertverificationerror",
    "ssLError",
]

_CONTEXT_OVERFLOW_PATTERNS = [
    "context_length_exceeded",
    "payload too large",
    "maximum context length",
    "token count exceeds limit",
    "request size exceeds",
    "too many tokens",
]

_SCHEMA_INCOMPATIBILITY_PATTERNS = [
    "unrecognized parameter",
    "unknown field",
    "additionalproperties",
    "$schema",
    "invalid_request_error",
    "unknown parameter",
    "schema validation error",
]

_TOOL_MALFORMED_PATTERNS = [
    "malformed tool call",
    "failed to parse function arguments",
    "invalid json in tool arguments",
    "invalid_tool_call",
]

_CLIENT_FAULT_PATTERNS = [
    "invalid api key",
    "unauthorized",
    "incorrect api key",
    "bad request syntax",
    "malformed json request",
]


def parse_retry_after(header_val: Optional[str]) -> Optional[float]:
    """Parse HTTP Retry-After header value (seconds integer or HTTP date string)."""
    if not header_val:
        return None
    val = header_val.strip()
    try:
        return max(0.0, float(val))
    except ValueError:
        pass
    try:
        parsed_tuple = email.utils.parsedate_tz(val)
        if parsed_tuple:
            timestamp = email.utils.mktime_tz(parsed_tuple)
            diff = timestamp - time.time()
            return max(0.0, diff)
    except Exception:
        pass
    return None


def classify_api_error(
    error: Any,
    status_code: Optional[int] = None,
    headers: Optional[Dict[str, str]] = None,
) -> ClassifiedError:
    """Classify an exception or response into a structured ClassifiedError (V1/V2 compatible)."""
    classification = classify_failure(error, status_code=status_code, headers=headers)
    return ClassifiedError(
        reason=classification.reason,
        should_fallback=classification.should_fallback,
        retryable=classification.retryable,
        status_code=classification.status_code,
        message=classification.message,
        category=classification.category,
        poisons_health=classification.poisons_health,
        retry_after_seconds=classification.retry_after_seconds,
        details=classification.details,
    )


def classify_failure(
    error: Any,
    status_code: Optional[int] = None,
    headers: Optional[Dict[str, str]] = None,
) -> FailureClassification:
    """Comprehensive failure classification mapping errors to categories and health impacts."""
    code = status_code
    if code is None and hasattr(error, "status_code"):
        code = getattr(error, "status_code")
    if code is None and hasattr(error, "code"):
        code = getattr(error, "code")
    if code is None and hasattr(error, "response") and hasattr(error.response, "status_code"):
        code = error.response.status_code

    msg = str(error).lower()
    if hasattr(error, "body") and isinstance(error.body, dict):
        msg += " " + str(error.body).lower()

    # Normalize headers
    clean_headers = {k.lower(): v for k, v in (headers or {}).items()}
    retry_after = parse_retry_after(clean_headers.get("retry-after"))

    # 1. SSL / TLS Verification Failures (Infrastructure)
    if any(p in msg for p in _SSL_PATTERNS) or "ssLError" in type(error).__name__:
        return FailureClassification(
            category=FailureCategory.INFRASTRUCTURE,
            reason=FailoverReason.ssl_cert_verification,
            should_fallback=True,
            retryable=False,
            poisons_health=True,
            status_code=code,
            message=msg,
        )

    # 2. Connection Refused / Socket Refusal (Infrastructure)
    if "connection refused" in msg or "errno 61" in msg or "errno 111" in msg:
        return FailureClassification(
            category=FailureCategory.INFRASTRUCTURE,
            reason=FailoverReason.connection_refused,
            should_fallback=True,
            retryable=False,
            poisons_health=True,
            status_code=599,
            message=msg,
        )

    # 3. Context Length / Payload Overflow (Request Incompatibility / Sizing)
    if code == 413 or any(p in msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return FailureClassification(
            category=FailureCategory.REQUEST_INCOMPATIBILITY,
            reason=FailoverReason.payload_too_large,
            should_fallback=True,
            retryable=False,
            poisons_health=False,  # Context overflow does NOT poison provider health!
            status_code=413,
            message=msg,
        )

    # 4. HTTP 402 Billing / Credits Exhaustion (Rate/Quota Limit)
    if code == 402 or any(p in msg for p in _BILLING_PATTERNS):
        return FailureClassification(
            category=FailureCategory.RATE_LIMIT,
            reason=FailoverReason.billing,
            should_fallback=True,
            retryable=False,
            poisons_health=True,
            status_code=402,
            message=msg,
        )

    # 5. HTTP 429 Rate Limits (Rate Limit)
    if code == 429 or "ratelimit" in type(error).__name__.lower():
        is_upstream_shared = any(p in msg for p in _UPSTREAM_429_PATTERNS)
        return FailureClassification(
            category=FailureCategory.RATE_LIMIT,
            reason=FailoverReason.upstream_rate_limit if is_upstream_shared else FailoverReason.rate_limit,
            should_fallback=True,
            retryable=True,
            poisons_health=True,
            status_code=429,
            retry_after_seconds=retry_after,
            message=msg,
        )

    # 6. HTTP 404 Model Deprecation or Sunset
    if code in (404, 400) and any(p in msg for p in _DEPRECATION_PATTERNS):
        return FailureClassification(
            category=FailureCategory.REQUEST_INCOMPATIBILITY,
            reason=FailoverReason.model_not_found,
            should_fallback=True,
            retryable=False,
            poisons_health=False,  # Specific model missing does not imply entire provider is dead
            status_code=code,
            message=msg,
        )
    if code == 404:
        return FailureClassification(
            category=FailureCategory.REQUEST_INCOMPATIBILITY,
            reason=FailoverReason.model_not_found,
            should_fallback=True,
            retryable=False,
            poisons_health=False,
            status_code=404,
            message=msg,
        )

    # 7. Semantic Tool / Schema Failures
    if any(p in msg for p in _TOOL_MALFORMED_PATTERNS):
        return FailureClassification(
            category=FailureCategory.SEMANTIC_AGENT_FAILURE,
            reason=FailoverReason.malformed_tool_call,
            should_fallback=True,
            retryable=False,
            poisons_health=False,  # Model produced bad tool call, provider infra is healthy
            status_code=code or 200,
            message=msg,
        )

    # 8. Request Schema Incompatibility (e.g. Gemini protobuf rejected $schema)
    if code == 400 and any(p in msg for p in _SCHEMA_INCOMPATIBILITY_PATTERNS):
        return FailureClassification(
            category=FailureCategory.REQUEST_INCOMPATIBILITY,
            reason=FailoverReason.schema_incompatible,
            should_fallback=True,
            retryable=False,
            poisons_health=False,  # Incompatible schema does not mean provider is down
            status_code=400,
            message=msg,
        )

    # 9. Upstream / Client Auth Failures (401, 403)
    if code in (401, 403) or "access denied" in msg or "forbidden" in msg or any(p in msg for p in _CLIENT_FAULT_PATTERNS):
        return FailureClassification(
            category=FailureCategory.CLIENT_FAULT if any(p in msg for p in _CLIENT_FAULT_PATTERNS) else FailureCategory.INFRASTRUCTURE,
            reason=FailoverReason.auth,
            should_fallback=True,  # Fallback to alternate provider with valid key
            retryable=False,
            poisons_health=False,  # Bad credentials do NOT mean provider is down
            status_code=code or 403,
            message=msg,
        )

    # 10. WAF / Cloudflare Challenge (Infrastructure)
    if any(p in msg for p in _WAF_PATTERNS):
        return FailureClassification(
            category=FailureCategory.INFRASTRUCTURE,
            reason=FailoverReason.waf_blocked,
            should_fallback=True,
            retryable=False,
            poisons_health=True,
            status_code=code or 403,
            message=msg,
        )

    # 11. Upstream Server Errors 5xx / 529 / 408 (Infrastructure)
    if code in (408, 500, 502, 503, 504, 529) or "overloaded" in msg or "bad gateway" in msg or "gateway timeout" in msg:
        is_overload = code in (503, 529) or "overloaded" in msg
        return FailureClassification(
            category=FailureCategory.INFRASTRUCTURE,
            reason=FailoverReason.overloaded if is_overload else FailoverReason.server_error,
            should_fallback=True,
            retryable=True,
            poisons_health=True,
            status_code=code,
            message=msg,
        )

    # 12. Network Timeouts (Infrastructure)
    if "timeout" in msg or "timed out" in msg or "connecttimeout" in type(error).__name__.lower():
        return FailureClassification(
            category=FailureCategory.INFRASTRUCTURE,
            reason=FailoverReason.timeout,
            should_fallback=True,
            retryable=True,
            poisons_health=True,
            status_code=code or 504,
            message=msg,
        )

    # Fallback to Unknown
    return FailureClassification(
        category=FailureCategory.UNKNOWN,
        reason=FailoverReason.unknown,
        should_fallback=False,
        retryable=True,
        poisons_health=True,
        status_code=code,
        message=msg,
    )
