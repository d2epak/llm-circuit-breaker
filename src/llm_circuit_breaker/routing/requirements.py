"""Routing Requirement Vectors and Hard-Constraint Matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from llm_circuit_breaker.capability.profile import ModelProfile


@dataclass
class RequirementVector:
    """Explicit requirements that candidate models must satisfy."""
    require_tools: bool = False
    require_parallel_tools: bool = False
    require_structured_output: bool = False
    require_vision: bool = False
    require_reasoning: bool = False
    minimum_context_tokens: int = 0
    maximum_cost_usd: Optional[float] = None
    latency_budget_ms: Optional[float] = None
    task_class: str = "general"  # "coding" or "general"
    allowed_providers: Optional[List[str]] = None
    forbidden_providers: Optional[List[str]] = None

    def matches_hard_constraints(self, profile: ModelProfile) -> Tuple[bool, Optional[str]]:
        """
        Evaluate candidate against hard constraints.
        Returns (passed, exclusion_reason).
        """
        # Provider filtering
        if self.allowed_providers is not None:
            if profile.provider.lower() not in [p.lower() for p in self.allowed_providers]:
                return False, f"Provider '{profile.provider}' not in allowed list"

        if self.forbidden_providers is not None:
            if profile.provider.lower() in [p.lower() for p in self.forbidden_providers]:
                return False, f"Provider '{profile.provider}' is in forbidden list"

        # Tool calling
        if self.require_tools and not profile.supports_tools:
            return False, f"Model '{profile.model}' does not support tool calling"

        # Parallel tools
        if self.require_parallel_tools and not profile.supports_parallel_tools:
            return False, f"Model '{profile.model}' does not support parallel tool calling"

        # Structured output
        if self.require_structured_output and not profile.supports_structured_output:
            return False, f"Model '{profile.model}' does not support structured output"

        # Vision
        if self.require_vision and not profile.supports_vision:
            return False, f"Model '{profile.model}' does not support vision/images"

        # Reasoning
        if self.require_reasoning and not profile.supports_reasoning:
            return False, f"Model '{profile.model}' does not support reasoning/thinking"

        # Minimum context window
        if self.minimum_context_tokens > 0 and profile.context_window < self.minimum_context_tokens:
            return False, f"Context window ({profile.context_window} tokens) below minimum required ({self.minimum_context_tokens} tokens)"

        return True, None
