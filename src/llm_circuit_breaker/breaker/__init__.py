"""Circuit Breaker Subsystem."""

from llm_circuit_breaker.breaker.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from llm_circuit_breaker.breaker.metrics import (
    CallOutcome,
    SlidingWindowMetrics,
    SlidingWindowType,
)
from llm_circuit_breaker.breaker.registry import (
    DEFAULT_BREAKER_REGISTRY,
    CircuitBreakerRegistry,
)
from llm_circuit_breaker.breaker.state import (
    CircuitBreakerState,
    StateTransitionEvent,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerRegistry",
    "DEFAULT_BREAKER_REGISTRY",
    "CircuitBreakerState",
    "StateTransitionEvent",
    "SlidingWindowMetrics",
    "SlidingWindowType",
    "CallOutcome",
]
