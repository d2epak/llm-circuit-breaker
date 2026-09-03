"""V2 Capability-Aware Circuit-Breaker Routing Engine."""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional, Tuple

from llm_circuit_breaker.breaker.circuit_breaker import CircuitBreaker
from llm_circuit_breaker.breaker.registry import (
    DEFAULT_BREAKER_REGISTRY,
    CircuitBreakerRegistry,
)
from llm_circuit_breaker.breaker.state import CircuitBreakerState
from llm_circuit_breaker.capability.profile import Endpoint
from llm_circuit_breaker.capability.registry import (
    DEFAULT_CAPABILITY_REGISTRY,
    CapabilityRegistry,
)
from llm_circuit_breaker.routing.decision import (
    CandidateEvaluation,
    RoutingDecision,
)
from llm_circuit_breaker.routing.requirements import RequirementVector
from llm_circuit_breaker.routing.scorer import RoutingScorer

logger = logging.getLogger("llm_circuit_breaker.routing")


class CapabilityRouter:
    """Capability-aware and circuit-breaker-controlled routing engine."""

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        breaker_registry: Optional[CircuitBreakerRegistry] = None,
        default_strategy: str = "balanced",
    ):
        self.capability_registry = capability_registry or DEFAULT_CAPABILITY_REGISTRY
        self.breaker_registry = breaker_registry or DEFAULT_BREAKER_REGISTRY
        self.default_strategy = default_strategy
        self.scorer = RoutingScorer()

        self._lock = threading.RLock()
        self._round_robin_indices: Dict[str, int] = {}

    def select_candidate(
        self,
        requirements: RequirementVector,
        pool: str = "general_agent",
        strategy: Optional[str] = None,
        request_id: str = "",
        excluded_endpoints: Optional[List[str]] = None,
        fallback_reason: Optional[str] = None,
    ) -> Tuple[Optional[Endpoint], RoutingDecision]:
        """
        Evaluate candidate pipeline:
        1. Hard constraint compatibility
        2. Breaker admission filter
        3. Soft scoring
        4. Strategy selection
        """
        strat = strategy or self.default_strategy
        endpoints = self.capability_registry.endpoints_for_pool(pool)
        if not endpoints:
            # Fallback to all endpoints if pool-specific list is empty
            endpoints = self.capability_registry.all_endpoints()

        exclusions = set(excluded_endpoints or [])
        evaluations: List[CandidateEvaluation] = []
        eligible_endpoints: List[Tuple[Endpoint, CandidateEvaluation]] = []

        for ep in endpoints:
            # Check manual exclusion (e.g. from current attempt ledger)
            if ep.id in exclusions:
                evaluations.append(
                    CandidateEvaluation(
                        endpoint_id=ep.id,
                        provider=ep.provider,
                        model=ep.model,
                        eligible=False,
                        exclusion_reason="Excluded by attempt ledger or recent failure",
                    )
                )
                continue

            profile = ep.profile or self.capability_registry.get_profile(ep.provider, ep.model)

            # 1. Hard constraint filter
            passed, reason = requirements.matches_hard_constraints(profile)
            if not passed:
                evaluations.append(
                    CandidateEvaluation(
                        endpoint_id=ep.id,
                        provider=ep.provider,
                        model=ep.model,
                        eligible=False,
                        hard_constraints_passed=False,
                        exclusion_reason=reason,
                    )
                )
                continue

            # 2. Circuit Breaker Admission filter
            breaker = self.breaker_registry.get_or_create(f"{ep.provider}:{ep.model}")
            breaker_state = breaker.state
            if breaker_state == CircuitBreakerState.OPEN or breaker_state == CircuitBreakerState.FORCED_OPEN:
                evaluations.append(
                    CandidateEvaluation(
                        endpoint_id=ep.id,
                        provider=ep.provider,
                        model=ep.model,
                        eligible=False,
                        breaker_state=breaker_state.value,
                        exclusion_reason=f"Circuit breaker is {breaker_state.value}",
                    )
                )
                continue

            # 3. Soft scoring
            metrics_snap = breaker.snapshot().get("metrics", {})
            eval_record = self.scorer.score_candidate(
                endpoint=ep,
                breaker_state=breaker_state,
                latency_ms=200.0,
                failure_rate=metrics_snap.get("failure_rate", 0.0),
            )
            evaluations.append(eval_record)
            eligible_endpoints.append((ep, eval_record))

        total_considered = len(endpoints)
        total_eligible = len(eligible_endpoints)

        if not eligible_endpoints:
            decision = RoutingDecision(
                request_id=request_id,
                strategy=strat,
                selected_endpoint=None,
                evaluated_candidates=evaluations,
                total_considered=total_considered,
                total_eligible=0,
                fallback_reason=fallback_reason,
            )
            return None, decision

        # 4. Strategy Selection
        selected_endpoint: Optional[Endpoint] = None

        if strat == "priority":
            # Order by priority ascending (1 highest), then final score descending
            eligible_endpoints.sort(key=lambda x: (x[0].priority, -x[1].final_score))
            selected_endpoint = eligible_endpoints[0][0]

        elif strat == "round_robin":
            with self._lock:
                idx = self._round_robin_indices.get(pool, 0) % len(eligible_endpoints)
                selected_endpoint = eligible_endpoints[idx][0]
                self._round_robin_indices[pool] = (idx + 1) % len(eligible_endpoints)

        elif strat == "latency_aware":
            eligible_endpoints.sort(key=lambda x: x[1].latency_score, reverse=True)
            selected_endpoint = eligible_endpoints[0][0]

        elif strat == "cost_aware":
            eligible_endpoints.sort(key=lambda x: x[1].cost_score, reverse=True)
            selected_endpoint = eligible_endpoints[0][0]

        elif strat == "reliability_aware":
            eligible_endpoints.sort(key=lambda x: x[1].health_score, reverse=True)
            selected_endpoint = eligible_endpoints[0][0]

        else:  # "balanced" / default
            eligible_endpoints.sort(key=lambda x: x[1].final_score, reverse=True)
            selected_endpoint = eligible_endpoints[0][0]

        # Assign ranks
        for rank, (ep, ev) in enumerate(eligible_endpoints, 1):
            ev.rank = rank

        decision = RoutingDecision(
            request_id=request_id,
            strategy=strat,
            selected_endpoint=selected_endpoint,
            evaluated_candidates=evaluations,
            total_considered=total_considered,
            total_eligible=total_eligible,
            fallback_reason=fallback_reason,
        )

        return selected_endpoint, decision
