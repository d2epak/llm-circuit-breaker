"""Multi-Agent Isolated Routing Pools & Cooldown Management.

Provides separate, isolated provider fallback pools:
- Pool 'coding': Specialised for Claude Code (1M context, code generation, strict JSON tool calls).
- Pool 'general_agent': Specialised for Hermes Agent and OpenClaw (fast inference, reasoning, multi-turn chat).

Independent cooldown and quota tracking ensures that token exhaustion or 429s
in one pool never block or degrade the other.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("llm_circuit_breaker.pools")


def load_all_env_keys() -> Dict[str, str]:
    """Scan process environment and config files for API keys."""
    keys: Dict[str, str] = {}
    target_keys = [
        "CEREBRAS_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "MISTRAL_API_KEY",
        "NVIDIA_API_KEY",
    ]
    for k in target_keys:
        if os.getenv(k):
            keys[k] = os.getenv(k, "").strip()

    for candidate in [
        Path.home() / ".claude" / ".env",
        Path.home() / ".hermes" / ".env",
    ]:
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("\"'")
                            if k in target_keys and k not in keys and v:
                                keys[k] = v
            except Exception as e:
                logger.debug("Could not read %s: %s", candidate, e)

    return keys


@dataclass
class RouteDefinition:
    id: str
    provider: str
    model: str
    pool: str  # 'coding' or 'general_agent'
    base_url: str
    api_format: str  # 'openai'
    env_key: Optional[str]
    context_length: int = 65536
    max_output_tokens: int = 4096
    headers: Dict[str, str] = field(default_factory=dict)
    is_discovered: bool = False


_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Default Coding Pool (Claude Code, Cursor, Aider) - 5 Core Providers: Cerebras, Groq, OpenRouter, Mistral, NVIDIA
DEFAULT_CODING_ROUTES: List[RouteDefinition] = [
    # 1. Cerebras Llama 3.3 70B (Fastest inference, high-fidelity tool calling)
    RouteDefinition(
        id="cerebras-llama33-coding",
        provider="cerebras",
        model="llama3.3-70b",
        pool="coding",
        base_url="https://api.cerebras.ai/v1",
        api_format="openai",
        env_key="CEREBRAS_API_KEY",
        context_length=65536,
        max_output_tokens=8192,
        headers={"User-Agent": _BROWSER_UA}
    ),
    # 2. Groq Llama 3.3 70B Versatile (128k context)
    RouteDefinition(
        id="groq-llama33-coding",
        provider="groq",
        model="llama-3.3-70b-versatile",
        pool="coding",
        base_url="https://api.groq.com/openai/v1",
        api_format="openai",
        env_key="GROQ_API_KEY",
        context_length=131072,
        max_output_tokens=8192,
        headers={"User-Agent": _BROWSER_UA}
    ),
    # 3. OpenRouter Qwen 2.5 Coder 32B (Free specialist)
    RouteDefinition(
        id="openrouter-qwencoder-coding",
        provider="openrouter",
        model="qwen/qwen-2.5-coder-32b-instruct:free",
        pool="coding",
        base_url="https://openrouter.ai/api/v1",
        api_format="openai",
        env_key="OPENROUTER_API_KEY",
        context_length=32768,
        max_output_tokens=8192,
        headers={"User-Agent": _BROWSER_UA}
    ),
    # 4. OpenRouter Devstral 2512 (Free 256k context)
    RouteDefinition(
        id="openrouter-devstral-coding",
        provider="openrouter",
        model="mistralai/devstral-2512:free",
        pool="coding",
        base_url="https://openrouter.ai/api/v1",
        api_format="openai",
        env_key="OPENROUTER_API_KEY",
        context_length=262144,
        max_output_tokens=8192,
        headers={"User-Agent": _BROWSER_UA}
    ),
    # 5. Mistral Codestral (256k context)
    RouteDefinition(
        id="mistral-codestral-coding",
        provider="mistral",
        model="codestral-latest",
        pool="coding",
        base_url="https://api.mistral.ai/v1",
        api_format="openai",
        env_key="MISTRAL_API_KEY",
        context_length=256000,
        max_output_tokens=8192,
    ),
    # 6. NVIDIA NIM Nemotron 3 Ultra
    RouteDefinition(
        id="nvidia-nemotron-coding",
        provider="nvidia",
        model="nvidia/nemotron-3-ultra-550b-a55b",
        pool="coding",
        base_url="https://integrate.api.nvidia.com/v1",
        api_format="openai",
        env_key="NVIDIA_API_KEY",
        context_length=131072,
        max_output_tokens=8192,
        headers={"User-Agent": _BROWSER_UA}
    ),
]

# Default General Agent Pool (Hermes Agent, OpenClaw) - 5 Core Providers: Cerebras, Groq, OpenRouter, Mistral, NVIDIA
DEFAULT_AGENT_ROUTES: List[RouteDefinition] = [
    # 1. Cerebras Llama 3.3 70B (Fastest conversational response)
    RouteDefinition(
        id="cerebras-llama33-agent",
        provider="cerebras",
        model="llama3.3-70b",
        pool="general_agent",
        base_url="https://api.cerebras.ai/v1",
        api_format="openai",
        env_key="CEREBRAS_API_KEY",
        context_length=65536,
        max_output_tokens=4096,
        headers={"User-Agent": _BROWSER_UA}
    ),
    # 2. Groq Llama 3.3 70B Versatile
    RouteDefinition(
        id="groq-llama33-agent",
        provider="groq",
        model="llama-3.3-70b-versatile",
        pool="general_agent",
        base_url="https://api.groq.com/openai/v1",
        api_format="openai",
        env_key="GROQ_API_KEY",
        context_length=131072,
        max_output_tokens=4096,
        headers={"User-Agent": _BROWSER_UA}
    ),
    # 3. Cerebras Llama 3.1 8B
    RouteDefinition(
        id="cerebras-llama31-agent",
        provider="cerebras",
        model="llama3.1-8b",
        pool="general_agent",
        base_url="https://api.cerebras.ai/v1",
        api_format="openai",
        env_key="CEREBRAS_API_KEY",
        context_length=65536,
        max_output_tokens=4096,
        headers={"User-Agent": _BROWSER_UA}
    ),
    # 4. OpenRouter Llama 3.3 70B (Free)
    RouteDefinition(
        id="openrouter-llama33-agent",
        provider="openrouter",
        model="meta-llama/llama-3.3-70b-instruct:free",
        pool="general_agent",
        base_url="https://openrouter.ai/api/v1",
        api_format="openai",
        env_key="OPENROUTER_API_KEY",
        context_length=65536,
        max_output_tokens=4096,
        headers={"User-Agent": _BROWSER_UA}
    ),
    # 5. Mistral Small
    RouteDefinition(
        id="mistral-small-agent",
        provider="mistral",
        model="mistral-small-latest",
        pool="general_agent",
        base_url="https://api.mistral.ai/v1",
        api_format="openai",
        env_key="MISTRAL_API_KEY",
        context_length=128000,
        max_output_tokens=4096,
    ),
    # 6. NVIDIA Nemotron
    RouteDefinition(
        id="nvidia-nemotron-agent",
        provider="nvidia",
        model="nvidia/nemotron-3-ultra-550b-a55b",
        pool="general_agent",
        base_url="https://integrate.api.nvidia.com/v1",
        api_format="openai",
        env_key="NVIDIA_API_KEY",
        context_length=65536,
        max_output_tokens=4096,
        headers={"User-Agent": _BROWSER_UA}
    ),
]


class IsolatedPoolManager:
    """Thread-safe manager for dual-pool routing and independent cooldowns."""

    def __init__(self):
        self._lock = threading.RLock()
        self.keys = load_all_env_keys()

        self.coding_routes: List[RouteDefinition] = list(DEFAULT_CODING_ROUTES)
        self.agent_routes: List[RouteDefinition] = list(DEFAULT_AGENT_ROUTES)

        self.coding_index = 0
        self.agent_index = 0

        # Cooldowns map: (pool, provider) -> expiration_monotonic
        self.cooldowns: Dict[tuple[str, str], float] = {}

        # Deprecated / blacklisted models per pool: set of (pool, model_id)
        self.deprecated: Set[tuple[str, str]] = set()

        # Quota exhausted models until reset: map (pool, route_id) -> reset_epoch
        self.exhausted_quotas: Dict[tuple[str, str], float] = {}

    def refresh_keys(self) -> None:
        with self._lock:
            self.keys = load_all_env_keys()

    def mark_cooldown(self, pool: str, provider: str, seconds: float = 60.0) -> None:
        """Place a provider on cooldown for a SPECIFIC pool only."""
        with self._lock:
            key = (pool.lower(), provider.lower())
            self.cooldowns[key] = time.monotonic() + seconds
            logger.info("[🛡️ COOLDOWN] Pool '%s' placed provider '%s' on cooldown for %.1fs", pool, provider, seconds)

    def mark_quota_exhausted(self, pool: str, route_id: str, seconds: float = 86400.0) -> None:
        """Mark a route as having exhausted daily/monthly quota."""
        with self._lock:
            key = (pool.lower(), route_id.lower())
            self.exhausted_quotas[key] = time.time() + seconds
            logger.warning("[🛑 QUOTA EXHAUSTED] Pool '%s' route '%s' locked out for %.1fh", pool, route_id, seconds / 3600)

    def mark_deprecated(self, pool: str, model: str) -> None:
        """Permanently skip model in this pool for current process lifecycle."""
        with self._lock:
            self.deprecated.add((pool.lower(), model.lower()))
            logger.warning("[⚠️ DEPRECATED] Blacklisted model '%s' in pool '%s'", model, pool)

    def get_candidate_routes(self, pool: str) -> List[RouteDefinition]:
        with self._lock:
            routes = self.coding_routes if pool == "coding" else self.agent_routes
            now_mono = time.monotonic()
            now_epoch = time.time()
            valid: List[RouteDefinition] = []

            for r in routes:
                # If route requires an API key, only activate if the user exported a valid, non-empty key!
                # If key is missing, simply skip this provider without failing the fallback!
                if r.env_key:
                    key_val = self.keys.get(r.env_key, "").strip()
                    if not key_val:
                        continue

                if (pool.lower(), r.model.lower()) in self.deprecated:
                    continue

                quota_reset = self.exhausted_quotas.get((pool.lower(), r.id.lower()), 0)
                if now_epoch < quota_reset:
                    continue

                cooldown_exp = self.cooldowns.get((pool.lower(), r.provider.lower()), 0)
                if now_mono < cooldown_exp:
                    continue

                valid.append(r)
            return valid

    def select_route(self, pool: str, requested_model: Optional[str] = None) -> Optional[RouteDefinition]:
        """Select next viable route in the requested pool using round-robin fallback."""
        with self._lock:
            candidates = self.get_candidate_routes(pool)
            if not candidates:
                # If all candidates are on cooldown, clear oldest cooldown as safety relief
                pool_cooldowns = {k: v for k, v in self.cooldowns.items() if k[0] == pool.lower()}
                if pool_cooldowns:
                    oldest_key = min(pool_cooldowns.keys(), key=lambda k: pool_cooldowns[k])
                    del self.cooldowns[oldest_key]
                    candidates = self.get_candidate_routes(pool)

            if not candidates:
                return None

            idx = (self.coding_index if pool == "coding" else self.agent_index) % len(candidates)
            selected = candidates[idx]

            if pool == "coding":
                self.coding_index = (self.coding_index + 1) % len(candidates)
            else:
                self.agent_index = (self.agent_index + 1) % len(candidates)

            return selected

    def add_discovered_route(self, pool: str, route: RouteDefinition) -> None:
        """Dynamically append a newly discovered free model to the pool."""
        with self._lock:
            target_list = self.coding_routes if pool == "coding" else self.agent_routes
            existing_ids = {r.id for r in target_list}
            if route.id not in existing_ids:
                target_list.append(route)
                logger.info("[✨ DISCOVERED] Added model '%s' to pool '%s'", route.model, pool)


POOL_MANAGER = IsolatedPoolManager()
