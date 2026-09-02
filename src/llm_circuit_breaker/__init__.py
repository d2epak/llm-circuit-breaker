"""⚡ LLM Circuit Breaker

Zero-Downtime Multi-Provider LLM Failover & Autonomous Free-Model Discovery
for AI Agents (Claude Code, Hermes Agent, OpenClaw, Cursor, Aider).
"""

from __future__ import annotations

from llm_circuit_breaker.classifier import (
    ClassifiedError,
    FailoverReason,
    classify_api_error,
)
from llm_circuit_breaker.discovery import (
    discover_free_models,
    is_model_free,
    supports_tool_calling,
)
from llm_circuit_breaker.pools import (
    POOL_MANAGER,
    IsolatedPoolManager,
    RouteDefinition,
)
from llm_circuit_breaker.pruner import (
    estimate_tokens,
    prune_anthropic_request,
    prune_openai_request,
)
from llm_circuit_breaker.proxy import (
    CircuitBreakerGatewayHandler,
    create_proxy_app,
    start_proxy_server,
)
from llm_circuit_breaker.router import UniversalFailoverRouter
from llm_circuit_breaker.translators import (
    anthropic_to_openai_request,
    clean_gemini_schema,
    convert_gemini_to_openai_response,
    convert_openai_to_gemini_payload,
    openai_to_anthropic_response,
    repair_json_string,
)

__version__ = "0.2.0"

__all__ = [
    "UniversalFailoverRouter",
    "classify_api_error",
    "FailoverReason",
    "ClassifiedError",
    "POOL_MANAGER",
    "IsolatedPoolManager",
    "RouteDefinition",
    "prune_anthropic_request",
    "prune_openai_request",
    "estimate_tokens",
    "anthropic_to_openai_request",
    "openai_to_anthropic_response",
    "clean_gemini_schema",
    "convert_openai_to_gemini_payload",
    "convert_gemini_to_openai_response",
    "repair_json_string",
    "discover_free_models",
    "is_model_free",
    "supports_tool_calling",
    "CircuitBreakerGatewayHandler",
    "start_proxy_server",
    "create_proxy_app",
]
