"""Provider & Model Capability Registry."""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from llm_circuit_breaker.capability.profile import Endpoint, ModelProfile


class CapabilityRegistry:
    """Thread-safe registry for model capability profiles and endpoints."""

    def __init__(self):
        self._lock = threading.RLock()
        self._profiles: Dict[str, ModelProfile] = {}
        self._endpoints: Dict[str, Endpoint] = {}
        self._seed_builtin_profiles()

    def _make_key(self, provider: str, model: str) -> str:
        return f"{provider.lower()}:{model.lower()}"

    def register_profile(self, profile: ModelProfile) -> None:
        """Register or update a model profile."""
        with self._lock:
            key = self._make_key(profile.provider, profile.model)
            self._profiles[key] = profile

    def get_profile(self, provider: str, model: str) -> ModelProfile:
        """Get model profile, falling back to safe default assumptions if unknown."""
        with self._lock:
            key = self._make_key(provider, model)
            if key in self._profiles:
                return self._profiles[key]

            # Model suffix/prefix heuristic fallback
            for k, p in self._profiles.items():
                if model.lower() in k or k in model.lower():
                    return p

            # Safe generic fallback
            return ModelProfile(
                provider=provider,
                model=model,
                protocol="openai",
                context_window=32768,
                max_output_tokens=4096,
                supports_tools=True,
                supports_streaming=True,
            )

    def register_endpoint(self, endpoint: Endpoint) -> None:
        """Register an endpoint and associate its profile."""
        with self._lock:
            if not endpoint.profile:
                endpoint.profile = self.get_profile(endpoint.provider, endpoint.model)
            self._endpoints[endpoint.id] = endpoint

    def get_endpoint(self, endpoint_id: str) -> Optional[Endpoint]:
        with self._lock:
            return self._endpoints.get(endpoint_id)

    def all_endpoints(self) -> List[Endpoint]:
        with self._lock:
            return list(self._endpoints.values())

    def endpoints_for_pool(self, pool: str) -> List[Endpoint]:
        with self._lock:
            return [e for e in self._endpoints.values() if e.pool == pool]

    def _seed_builtin_profiles(self) -> None:
        """Seed known profiles for core providers."""
        profiles = [
            # Cerebras
            ModelProfile("cerebras", "llama3.3-70b", protocol="openai", context_window=65536, max_output_tokens=8192, supports_tools=True, is_free=True),
            ModelProfile("cerebras", "llama3.1-8b", protocol="openai", context_window=65536, max_output_tokens=4096, supports_tools=True, is_free=True),
            # Groq
            ModelProfile("groq", "llama-3.3-70b-versatile", protocol="openai", context_window=131072, max_output_tokens=8192, supports_tools=True, is_free=True),
            # OpenRouter Free
            ModelProfile("openrouter", "qwen/qwen-2.5-coder-32b-instruct:free", protocol="openai", context_window=32768, max_output_tokens=8192, supports_tools=True, is_free=True),
            ModelProfile("openrouter", "mistralai/devstral-2512:free", protocol="openai", context_window=262144, max_output_tokens=8192, supports_tools=True, is_free=True),
            ModelProfile("openrouter", "meta-llama/llama-3.3-70b-instruct:free", protocol="openai", context_window=65536, max_output_tokens=4096, supports_tools=True, is_free=True),
            # Mistral
            ModelProfile("mistral", "codestral-latest", protocol="openai", context_window=256000, max_output_tokens=8192, supports_tools=True),
            ModelProfile("mistral", "mistral-small-latest", protocol="openai", context_window=128000, max_output_tokens=4096, supports_tools=True),
            # NVIDIA NIM
            ModelProfile("nvidia", "nvidia/nemotron-3-ultra-550b-a55b", protocol="openai", context_window=131072, max_output_tokens=8192, supports_tools=True),
            # Google Gemini
            ModelProfile("gemini", "gemini-2.5-flash", protocol="gemini", context_window=1048576, max_output_tokens=8192, supports_tools=True, supports_vision=True, is_free=True),
            ModelProfile("gemini", "gemini-1.5-pro", protocol="gemini", context_window=2097152, max_output_tokens=8192, supports_tools=True, supports_vision=True),
            # Anthropic
            ModelProfile("anthropic", "claude-3-7-sonnet-20250219", protocol="anthropic", context_window=200000, max_output_tokens=8192, supports_tools=True, supports_reasoning=True, supports_vision=True),
            ModelProfile("anthropic", "claude-3-5-haiku-20241022", protocol="anthropic", context_window=200000, max_output_tokens=8192, supports_tools=True),
            # OpenAI
            ModelProfile("openai", "gpt-4o", protocol="openai", context_window=128000, max_output_tokens=4096, supports_tools=True, supports_vision=True),
            ModelProfile("openai", "gpt-4o-mini", protocol="openai", context_window=128000, max_output_tokens=4096, supports_tools=True, supports_vision=True),
        ]
        for p in profiles:
            self.register_profile(p)


DEFAULT_CAPABILITY_REGISTRY = CapabilityRegistry()
