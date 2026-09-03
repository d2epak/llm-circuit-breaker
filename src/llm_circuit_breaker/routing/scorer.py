"""Multi-Objective Routing Scorer and Strategies."""

from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional

from llm_circuit_breaker.breaker.state import CircuitBreakerState
from llm_circuit_breaker.capability.profile import Endpoint
from llm_circuit_breaker.routing.decision import CandidateEvaluation
from llm_circuit_breaker.routing.requirements import RequirementVector


class RoutingScorer:
    """Computes normalized soft scores for eligible candidates."""

    def __init__(
        self,
        weight_quality: float = 0.3,
        weight_reliability: float = 0.3,
        weight_latency: float = 0.2,
        weight_cost: float = 0.2,
    ):
        self.w_quality = weight_quality
        self.w_reliability = weight_reliability
        self.w_latency = weight_latency
        self.w_cost = weight_cost

    def score_candidate(
        self,
        endpoint: Endpoint,
        breaker_state: CircuitBreakerState,
        latency_ms: float = 200.0,
        failure_rate: float = 0.0,
    ) -> CandidateEvaluation:
        """Compute normalized multi-objective score for an endpoint."""
        # 1. Health / Reliability Score (0.0 to 1.0)
        if breaker_state == CircuitBreakerState.OPEN:
            health_score = 0.0
        elif breaker_state == CircuitBreakerState.HALF_OPEN:
            health_score = 0.5
        else:
            health_score = max(0.0, 1.0 - (failure_rate / 100.0))

        # 2. Latency Score (Normalized against 5000ms ceiling)
        latency_score = max(0.0, min(1.0, 1.0 - (latency_ms / 5000.0)))

        # 3. Cost Score (Free = 1.0, otherwise inversely proportional)
        profile = endpoint.profile
        if profile and profile.is_free:
            cost_score = 1.0
        elif profile and profile.input_price_per_1m > 0:
            cost_score = max(0.1, min(1.0, 1.0 / (1.0 + profile.input_price_per_1m)))
        else:
            cost_score = 0.8

        # 4. Quality Score
        quality_score = 1.0 if (profile and profile.supports_tools) else 0.7

        final_score = (
            self.w_quality * quality_score
            + self.w_reliability * health_score
            + self.w_latency * latency_score
            + self.w_cost * cost_score
        )

        return CandidateEvaluation(
            endpoint_id=endpoint.id,
            provider=endpoint.provider,
            model=endpoint.model,
            eligible=True,
            breaker_state=breaker_state.value,
            hard_constraints_passed=True,
            health_score=health_score,
            latency_score=latency_score,
            cost_score=cost_score,
            final_score=final_score,
        )
