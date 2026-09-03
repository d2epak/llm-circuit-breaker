"""Base Provider Adapter Protocol and Interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol

from llm_circuit_breaker.capability.profile import Endpoint, ModelProfile
from llm_circuit_breaker.protocol.ir import NormalizedRequest, NormalizedResponse


@dataclass
class PreparedRequest:
    """Pre-processed native HTTP request ready for execution."""
    url: str
    headers: Dict[str, str]
    body_bytes: bytes
    method: str = "POST"


@dataclass
class ProviderExecutionResult:
    """Result of an HTTP invocation to an upstream provider."""
    status_code: int
    headers: Dict[str, str]
    body: bytes
    duration_ms: float = 0.0


class ProviderAdapter(Protocol):
    """Narrow provider abstraction isolating provider-specific network protocols."""

    provider_id: str

    def prepare_request(
        self,
        endpoint: Endpoint,
        request: NormalizedRequest,
        api_key: Optional[str] = None,
    ) -> PreparedRequest:
        """Translate NormalizedRequest into provider-specific HTTP headers and body."""
        ...

    def execute(
        self,
        prepared: PreparedRequest,
        timeout_seconds: float,
    ) -> ProviderExecutionResult:
        """Execute request with per-attempt timeout."""
        ...

    def normalize_response(
        self,
        endpoint: Endpoint,
        result: ProviderExecutionResult,
    ) -> NormalizedResponse:
        """Translate raw provider HTTP response into NormalizedResponse IR."""
        ...
