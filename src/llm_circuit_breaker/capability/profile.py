"""Model and Provider Capability Profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelProfile:
    """Declared and verified capabilities of an LLM."""
    provider: str
    model: str
    protocol: str = "openai"  # "openai", "anthropic", "gemini"
    context_window: int = 65536
    max_output_tokens: int = 4096
    supports_tools: bool = True
    supports_parallel_tools: bool = True
    supports_structured_output: bool = True
    supports_vision: bool = False
    supports_reasoning: bool = False
    supports_streaming: bool = True
    supports_json_mode: bool = True
    supports_system_prompt: bool = True
    supports_multipart: bool = False
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0
    is_free: bool = False
    region: Optional[str] = None
    privacy_class: str = "public"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Endpoint:
    """Target provider endpoint definition."""
    id: str
    provider: str
    model: str
    base_url: str
    protocol: str = "openai"
    env_key: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    weight: float = 1.0
    priority: int = 1
    profile: Optional[ModelProfile] = None
    pool: str = "general_agent"
    is_discovered: bool = False
