"""llm-circuit-breaker: Self-healing multi-provider failover and discovery engine for AI agents."""

from llm_circuit_breaker.classifier import FailoverReason, ClassifiedError, classify_api_error
from llm_circuit_breaker.discovery import discover_models, load_model_catalog, get_top_free_models
from llm_circuit_breaker.router import UniversalFailoverRouter

__version__ = "0.1.0"
__all__ = [
    "UniversalFailoverRouter",
    "FailoverReason",
    "ClassifiedError",
    "classify_api_error",
    "discover_models",
    "load_model_catalog",
    "get_top_free_models",
]
