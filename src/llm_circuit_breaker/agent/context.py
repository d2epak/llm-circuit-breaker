"""Budget-Aware Context Manager and History Compactor."""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from llm_circuit_breaker.protocol.ir import (
    NormalizedMessage,
    NormalizedRequest,
    NormalizedToolResult,
)

logger = logging.getLogger("llm_circuit_breaker.agent.context")


def estimate_tokens(payload: Any) -> int:
    """Safe, conservative token estimation (~3.8 characters per token)."""
    if isinstance(payload, str):
        text_len = len(payload)
    elif isinstance(payload, NormalizedRequest):
        parts = []
        if payload.system_instruction:
            parts.append(payload.system_instruction)
        for m in payload.messages:
            if m.content:
                parts.append(m.content)
            if m.reasoning_content:
                parts.append(m.reasoning_content)
            for tc in m.tool_calls:
                parts.append(tc.raw_arguments or json.dumps(tc.arguments))
            for tr in m.tool_results:
                parts.append(tr.content)
        text_len = sum(len(p) for p in parts)
    else:
        try:
            text_len = len(json.dumps(payload, ensure_ascii=False))
        except Exception:
            text_len = len(str(payload))
    return max(1, (text_len + 3) // 4)


@dataclass
class ContextBudget:
    """Model context window and reserved output token budget."""
    model_context_window: int = 65536
    desired_output_tokens: int = 4096
    safety_margin_tokens: int = 2048

    @property
    def available_input_budget(self) -> int:
        """Remaining tokens available for input prompt history."""
        return max(512, self.model_context_window - self.desired_output_tokens - self.safety_margin_tokens)


class ContextManager:
    """
    Manages request context size, enforcing explicit token budgets and hierarchical compaction.
    Preservation priority:
    1. System instructions
    2. Root user objective (first user prompt)
    3. Active constraints
    4. Recent execution turns (latest 6 turns)
    5. Summarize older tool outputs (truncate large terminal/file dumps)
    6. Evict oldest intermediate pairs if still exceeding budget.
    """

    def __init__(self, preserve_tail_turns: int = 6):
        self.preserve_tail_turns = preserve_tail_turns

    def compact(
        self,
        request: NormalizedRequest,
        budget: ContextBudget,
    ) -> Tuple[NormalizedRequest, bool]:
        """
        Compact request to fit strictly within the target model's available input budget.
        Returns (compacted_request, was_compacted).
        """
        current_tokens = estimate_tokens(request)
        target_tokens = budget.available_input_budget

        if current_tokens <= target_tokens:
            return request, False

        logger.info(
            "Request size (%d tokens) exceeds available budget (%d tokens). Initiating hierarchical compaction.",
            current_tokens, target_tokens
        )

        compacted = copy.deepcopy(request)
        messages = compacted.messages

        if len(messages) <= (self.preserve_tail_turns + 2):
            # Too few messages to drop; perform aggressive truncation on content
            for m in messages:
                for tr in m.tool_results:
                    if len(tr.content) > 500:
                        tr.content = (
                            tr.content[:200]
                            + "\n... [Tool output compacted by Circuit Breaker] ...\n"
                            + tr.content[-200:]
                        )
            return compacted, True

        # Phase 1: Compact historical tool results in older turns
        # Keep index 0/1 (root prompt) and latest preserve_tail_turns intact
        cutoff_idx = len(messages) - self.preserve_tail_turns
        for idx in range(1, cutoff_idx):
            m = messages[idx]
            for tr in m.tool_results:
                if len(tr.content) > 500:
                    tr.content = (
                        tr.content[:200]
                        + "\n... [Historical output compacted by Circuit Breaker to fit target budget] ...\n"
                        + tr.content[-200:]
                    )
            if m.content and len(m.content) > 1000 and m.role == "assistant":
                m.content = (
                    m.content[:400]
                    + "\n... [Prior assistant reasoning compacted] ...\n"
                    + m.content[-400:]
                )

        if estimate_tokens(compacted) <= target_tokens:
            return compacted, True

        # Phase 2: Drop oldest intermediate message turns until within target
        # Protect root prompt at index 0 (or 1 if system)
        start_evict_idx = 1
        while len(compacted.messages) > (self.preserve_tail_turns + 2):
            if estimate_tokens(compacted) <= target_tokens:
                break
            compacted.messages.pop(start_evict_idx)

        return compacted, True
