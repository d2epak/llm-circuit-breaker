"""Structured JSON Event Logging and Credential Redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any, Dict, Optional

SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer|secret|token|password|cookie)",
    re.IGNORECASE,
)


def redact_sensitive_data(obj: Any, max_prompt_preview_chars: int = 120) -> Any:
    """Recursively redacts secrets and truncates raw prompts."""
    if isinstance(obj, dict):
        redacted = {}
        for k, v in obj.items():
            if SENSITIVE_KEY_PATTERN.search(str(k)):
                redacted[k] = "[REDACTED]"
            elif k in ("prompt", "messages", "content") and isinstance(v, str):
                if len(v) > max_prompt_preview_chars:
                    redacted[k] = f"{v[:max_prompt_preview_chars]}... [TRUNCATED_OBSERVABILITY_PREVIEW]"
                else:
                    redacted[k] = v
            else:
                redacted[k] = redact_sensitive_data(v, max_prompt_preview_chars)
        return redacted
    elif isinstance(obj, list):
        return [redact_sensitive_data(item, max_prompt_preview_chars) for item in obj]
    elif isinstance(obj, str):
        # Look for sk-... / gsk_... patterns
        if re.search(r"(sk-[a-zA-Z0-9_-]{20,}|gsk_[a-zA-Z0-9_-]{20,}|AIza[a-zA-Z0-9_-]{30,})", obj):
            return "[REDACTED_API_KEY]"
        return obj
    return obj


class StructuredJsonLogger:
    """Emits JSON-formatted structured logs with automatic redaction."""

    def __init__(self, name: str = "llm_circuit_breaker", stream=sys.stdout):
        self.name = name
        self.stream = stream

    def log_event(
        self,
        level: str,
        event: str,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "timestamp": time.time(),
            "logger": self.name,
            "level": level.upper(),
            "event": event,
            "request_id": request_id,
            "data": redact_sensitive_data(metadata or {}),
        }
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        self.stream.write(line)
        self.stream.flush()

    def info(self, event: str, request_id: Optional[str] = None, **kwargs) -> None:
        self.log_event("INFO", event, request_id, kwargs)

    def warning(self, event: str, request_id: Optional[str] = None, **kwargs) -> None:
        self.log_event("WARNING", event, request_id, kwargs)

    def error(self, event: str, request_id: Optional[str] = None, **kwargs) -> None:
        self.log_event("ERROR", event, request_id, kwargs)


DEFAULT_STRUCTURED_LOGGER = StructuredJsonLogger()
