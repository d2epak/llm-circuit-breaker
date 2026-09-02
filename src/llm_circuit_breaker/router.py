"""Universal Failover Router with Round-Robin Cooldowns and Dynamic Re-binding."""

from __future__ import annotations
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from llm_circuit_breaker.discovery import get_top_free_models
from llm_circuit_breaker.classifier import classify_api_error, FailoverReason

logger = logging.getLogger("llm_circuit_breaker.router")


class UniversalFailoverRouter:
    """Manages multi-provider LLM failover, cooldown timers, and catalog augmentation."""

    def __init__(
        self,
        configured_fallbacks: Optional[List[Dict[str, Any]]] = None,
        auto_discover_free: bool = True,
        max_discovered_free: int = 5,
    ):
        self.fallback_chain: List[Dict[str, Any]] = list(configured_fallbacks or [])
        self.provider_cooldowns: Dict[str, float] = {}
        self.deprecated_models: Set[str] = set()
        self.fallback_index: int = 0
        self.active_provider: Dict[str, Any] = self.fallback_chain[0] if self.fallback_chain else {}
        self.auto_discover_free = auto_discover_free
        self.max_discovered_free = max_discovered_free

        if self.auto_discover_free:
            self._load_auto_discovered_fallbacks()

    def _load_auto_discovered_fallbacks(self) -> None:
        """Append top discovered free models to the end of the backup pool."""
        try:
            discovered = get_top_free_models(limit=self.max_discovered_free)
            existing_models = {f.get("model") for f in self.fallback_chain}
            for m in discovered:
                if m["id"] not in existing_models:
                    self.fallback_chain.append({
                        "provider": "openrouter",
                        "model": m["id"],
                        "base_url": "https://openrouter.ai/api/v1",
                        "key_env": "OPENROUTER_API_KEY",
                        "context_length": m.get("context_length", 128000),
                        "is_auto_discovered": True,
                    })
        except Exception as e:
            logger.warning("Could not append auto-discovered models: %s", e)

    def mark_cooldown(self, provider: str, seconds: float = 60.0) -> None:
        """Place provider on cooldown to prevent turn-thrashing."""
        self.provider_cooldowns[provider.lower()] = time.monotonic() + seconds
        logger.info("Provider %s placed on cooldown for %.1fs", provider, seconds)

    def mark_deprecated(self, model: str) -> None:
        """Permanently skip model for this session."""
        self.deprecated_models.add(model)
        logger.warning("Blacklisted deprecated model: %s", model)

    def get_next_available_route(self, reason: Optional[FailoverReason] = None) -> Optional[Dict[str, Any]]:
        """Select next healthy provider respecting cooldowns and deprecations."""
        if not self.fallback_chain:
            return None

        attempts = 0
        max_attempts = len(self.fallback_chain) * 2

        while attempts < max_attempts:
            if self.fallback_index >= len(self.fallback_chain):
                self.fallback_index = 0

            candidate = self.fallback_chain[self.fallback_index]
            self.fallback_index += 1
            attempts += 1

            provider = candidate.get("provider", "").lower()
            model = candidate.get("model", "")

            # 1. Skip deprecated models
            if model in self.deprecated_models or (provider, model) in self.deprecated_models:
                continue

            # 2. Skip providers currently in cooldown
            cooldown = self.provider_cooldowns.get(provider, 0)
            if time.monotonic() < cooldown:
                continue

            self.active_provider = candidate
            logger.info("Switched active LLM route to %s/%s", provider, model)
            return candidate

        logger.error("All configured and discovered LLM providers are currently exhausted or on cooldown.")
        return None
