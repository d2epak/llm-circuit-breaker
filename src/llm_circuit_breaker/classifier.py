"""API Error Classifier for LLM Provider Calls.

Maps HTTP status codes, exception payloads, and WAF error bodies into
structured failover actions.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class FailoverReason(str, Enum):
    rate_limit = "rate_limit"
    upstream_rate_limit = "upstream_rate_limit"
    billing = "billing"
    auth = "auth"
    model_not_found = "model_not_found"
    overloaded = "overloaded"
    server_error = "server_error"
    timeout = "timeout"
    ssl_cert_verification = "ssl_cert_verification"
    unknown = "unknown"


@dataclass
class ClassifiedError:
    reason: FailoverReason
    should_fallback: bool
    retryable: bool
    status_code: Optional[int] = None
    message: str = ""


_BILLING_PATTERNS = [
    "insufficient credits",
    "credit balance",
    "billing",
    "payment required",
    "out of credits",
    "usage limit reached",
]
_DEPRECATION_PATTERNS = [
    "deprecated",
    "decommissioned",
    "model does not exist",
    "not found",
    "model_not_found",
    "has been removed",
]
_UPSTREAM_429_PATTERNS = [
    "temporarily rate-limited upstream",
    "upstream_provider_shared_pool",
    "provider returned error",
    "rate limit exceeded: free-models-per-day",
]
_SSL_PATTERNS = [
    "certificate verify failed",
    "self signed certificate",
    "sslcertverificationerror",
]


def classify_api_error(error: Exception, status_code: Optional[int] = None) -> ClassifiedError:
    """Classify an exception or response into a structured recovery instruction."""
    code = status_code or getattr(error, "status_code", None)
    if code is None and hasattr(error, "response") and hasattr(error.response, "status_code"):
        code = error.response.status_code

    msg = str(error).lower()
    if hasattr(error, "body") and isinstance(error.body, dict):
        msg += " " + str(error.body).lower()

    # 1. SSL / TLS Verification Failures
    if any(p in msg for p in _SSL_PATTERNS) or "ssLError" in type(error).__name__:
        return ClassifiedError(FailoverReason.ssl_cert_verification, should_fallback=True, retryable=False, status_code=code, message=msg)

    # 2. HTTP 402 Billing / Credits Exhaustion
    if code == 402 or any(p in msg for p in _BILLING_PATTERNS):
        return ClassifiedError(FailoverReason.billing, should_fallback=True, retryable=False, status_code=402, message=msg)

    # 3. HTTP 429 Rate Limits
    if code == 429 or "ratelimit" in type(error).__name__.lower():
        if any(p in msg for p in _UPSTREAM_429_PATTERNS):
            return ClassifiedError(FailoverReason.upstream_rate_limit, should_fallback=True, retryable=True, status_code=429, message=msg)
        return ClassifiedError(FailoverReason.rate_limit, should_fallback=True, retryable=True, status_code=429, message=msg)

    # 4. HTTP 404 / 400 Model Deprecation
    if code in (404, 400) and any(p in msg for p in _DEPRECATION_PATTERNS):
        return ClassifiedError(FailoverReason.model_not_found, should_fallback=True, retryable=False, status_code=code, message=msg)

    # 5. HTTP 403 Auth / WAF / Network Access Block
    if code in (401, 403) or "access denied" in msg or "forbidden" in msg:
        return ClassifiedError(FailoverReason.auth, should_fallback=True, retryable=False, status_code=code, message=msg)

    # 6. HTTP 5xx Server Outage & Overload
    if code in (500, 502, 503, 504, 529) or "overloaded" in msg or "bad gateway" in msg:
        return ClassifiedError(
            FailoverReason.overloaded if code in (503, 529) else FailoverReason.server_error,
            should_fallback=True,
            retryable=True,
            status_code=code,
            message=msg,
        )

    # 7. Network Timeouts
    if "timeout" in msg or "connecttimeout" in type(error).__name__.lower():
        return ClassifiedError(FailoverReason.timeout, should_fallback=True, retryable=True, status_code=code, message=msg)

    return ClassifiedError(FailoverReason.unknown, should_fallback=False, retryable=True, status_code=code, message=msg)
