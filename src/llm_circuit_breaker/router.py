"""Universal Failover Router with Multi-Agent Pool Isolation and Fast Failover."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

from llm_circuit_breaker.classifier import classify_api_error, FailoverReason
from llm_circuit_breaker.pools import POOL_MANAGER, RouteDefinition
from llm_circuit_breaker.pruner import prune_openai_request
from llm_circuit_breaker.translators import (
    convert_openai_to_gemini_payload,
    convert_gemini_to_openai_response,
)

logger = logging.getLogger("llm_circuit_breaker.router")
DEFAULT_TIMEOUT = int(os.environ.get("GATEWAY_TIMEOUT", "25"))


def execute_upstream_request(
    route: RouteDefinition,
    openai_payload: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Tuple[int, Dict[str, str], bytes]:
    """Execute completion request against upstream API endpoint."""
    api_key = route.env_key and POOL_MANAGER.keys.get(route.env_key)

    if route.api_format == "gemini":
        gemini_payload = convert_openai_to_gemini_payload(openai_payload)
        gemini_payload["generationConfig"] = {
            "maxOutputTokens": openai_payload.get("max_tokens", route.max_output_tokens),
            "temperature": openai_payload.get("temperature", 0.7),
        }
        data = json.dumps(gemini_payload, ensure_ascii=False).encode("utf-8")
        url = f"{route.base_url.rstrip('/')}/models/{route.model}:generateContent"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["x-goog-api-key"] = api_key
    else:
        url = f"{route.base_url.rstrip('/')}/chat/completions"
        payload_copy = dict(openai_payload)
        payload_copy["model"] = route.model
        if "thinking" in payload_copy and route.provider not in ("anthropic", "openrouter"):
            payload_copy.pop("thinking", None)

        data = json.dumps(payload_copy, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if route.headers:
            headers.update(route.headers)

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read()
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp_headers, resp_body
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if hasattr(exc, "headers") else {}
        return exc.code, resp_headers, body
    except Exception as exc:
        return 599, {}, str(exc).encode("utf-8")


class UniversalFailoverRouter:
    """Manages multi-provider LLM failover with isolated pools, cooldowns, and self-healing."""

    def __init__(
        self,
        configured_fallbacks: Optional[List[Dict[str, Any]]] = None,
        auto_discover_free: bool = True,
        max_discovered_free: int = 5,
        default_pool: str = "general_agent",
    ):
        self.default_pool = default_pool
        self.pool_manager = POOL_MANAGER
        self.fallback_chain: List[Dict[str, Any]] = list(configured_fallbacks or [])
        self.provider_cooldowns: Dict[str, float] = {}
        self.deprecated_models: Set[str] = set()
        self.fallback_index: int = 0

        # Also register configured fallbacks into pool manager if provided
        if configured_fallbacks:
            converted_routes: List[RouteDefinition] = []
            for item in configured_fallbacks:
                route = RouteDefinition(
                    id=item.get("id") or f"{item.get('provider')}-{item.get('model')}",
                    provider=item.get("provider", "custom"),
                    model=item.get("model", "default"),
                    pool=item.get("pool", default_pool),
                    base_url=item.get("base_url", "https://api.openai.com/v1"),
                    api_format=item.get("api_format", "openai"),
                    env_key=item.get("key_env") or item.get("env_key"),
                    context_length=item.get("context_length", 65536),
                    headers=item.get("headers", {}),
                )
                converted_routes.append(route)

            if default_pool == "coding":
                self.pool_manager.coding_routes = converted_routes + self.pool_manager.coding_routes
            else:
                self.pool_manager.agent_routes = converted_routes + self.pool_manager.agent_routes

        if auto_discover_free:
            from llm_circuit_breaker.discovery import register_discovered_models_to_pools
            register_discovered_models_to_pools(limit_per_pool=max_discovered_free)

    @property
    def active_provider(self) -> Dict[str, Any]:
        """Return currently active provider definition."""
        if self.fallback_chain:
            return self.fallback_chain[self.fallback_index % len(self.fallback_chain)]
        route = self.pool_manager.select_route(self.default_pool)
        if not route:
            return {}
        return {
            "provider": route.provider,
            "model": route.model,
            "base_url": route.base_url,
            "key_env": route.env_key,
            "context_length": route.context_length,
        }

    def mark_cooldown(self, provider: str, seconds: float = 60.0, pool: Optional[str] = None) -> None:
        """Place a provider on cooldown to avoid turn-thrashing."""
        self.provider_cooldowns[provider.lower()] = time.monotonic() + seconds
        target_pool = pool or self.default_pool
        self.pool_manager.mark_cooldown(target_pool, provider, seconds)
        logger.info("Provider %s placed on cooldown for %.1fs", provider, seconds)

    def mark_deprecated(self, model: str, pool: Optional[str] = None) -> None:
        """Permanently skip model for this session."""
        self.deprecated_models.add(model)
        target_pool = pool or self.default_pool
        self.pool_manager.mark_deprecated(target_pool, model)
        logger.warning("Blacklisted deprecated model: %s", model)

    def get_next_available_route(self, reason: Optional[FailoverReason] = None, pool: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Select next healthy route in fallback chain or pool."""
        if self.fallback_chain:
            max_attempts = len(self.fallback_chain) * 2
            attempts = 0
            while attempts < max_attempts:
                self.fallback_index = (self.fallback_index + 1) % len(self.fallback_chain)
                candidate = self.fallback_chain[self.fallback_index]
                attempts += 1

                p = candidate.get("provider", "").lower()
                m = candidate.get("model", "")

                if m in self.deprecated_models:
                    continue
                cooldown = self.provider_cooldowns.get(p, 0)
                if time.monotonic() < cooldown:
                    continue

                return candidate

        target_pool = pool or self.default_pool
        route = self.pool_manager.select_route(target_pool)
        if not route:
            return None
        return {
            "provider": route.provider,
            "model": route.model,
            "base_url": route.base_url,
            "key_env": route.env_key,
            "context_length": route.context_length,
        }

    def dispatch(
        self,
        pool: str,
        openai_payload: Dict[str, Any],
        requested_model: str = "default",
        max_attempts: int = 8
    ) -> Tuple[int, Dict[str, Any], Optional[RouteDefinition]]:
        """
        Execute request with automatic failover across isolated pool candidates.
        Returns (status_code, parsed_openai_response, successful_route).
        """
        attempts = 0
        while attempts < max_attempts:
            route = self.pool_manager.select_route(pool, requested_model)
            if not route:
                logger.error("Pool '%s' has exhausted all available healthy routes.", pool)
                break

            attempts += 1
            logger.info(
                "[%s] Upstream attempt %d/%d -> %s (%s)",
                pool.upper(), attempts, max_attempts, route.provider, route.model
            )

            pruned_payload = prune_openai_request(openai_payload, route.context_length)
            status, headers, body = execute_upstream_request(route, pruned_payload)

            if status == 200:
                try:
                    raw_json = json.loads(body.decode("utf-8"))
                    if route.api_format == "gemini":
                        parsed = convert_gemini_to_openai_response(raw_json, route.model)
                    else:
                        parsed = raw_json
                    return 200, parsed, route
                except Exception as e:
                    logger.warning("Provider %s returned invalid JSON: %s", route.provider, e)
                    status = 502

            classified = classify_api_error(body.decode("utf-8", errors="ignore"), status_code=status)
            logger.warning(
                "[%s] Upstream error from %s (%d): %s (classified as: %s)",
                pool.upper(), route.provider, status, classified.message[:160], classified.reason
            )

            if classified.reason == FailoverReason.billing:
                self.pool_manager.mark_quota_exhausted(pool, route.id, 86400)
                continue

            if classified.reason in (FailoverReason.rate_limit, FailoverReason.upstream_rate_limit):
                retry_after = headers.get("retry-after")
                try:
                    cd = min(120, max(30, int(float(retry_after or "60"))))
                except Exception:
                    cd = 60
                self.pool_manager.mark_cooldown(pool, route.provider, cd)
                continue

            if classified.reason == FailoverReason.model_not_found or status == 404:
                self.pool_manager.mark_deprecated(pool, route.model)
                continue

            if classified.reason in (FailoverReason.overloaded, FailoverReason.server_error, FailoverReason.timeout, FailoverReason.connection_refused):
                self.pool_manager.mark_cooldown(pool, route.provider, 45.0)
                continue

        return 503, {"error": {"message": f"All providers in pool '{pool}' are temporarily unavailable."}}, None
