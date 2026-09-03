# ADR 0005: Canonical Protocol Intermediate Representation (IR)

## Status
Accepted

## Context
Supporting $M$ client protocols (Anthropic, OpenAI, Gemini) and $N$ upstream provider APIs requires $M \times N$ translation pathways if done peer-to-peer. Adding a new provider requires updating translations for every client.

## Decision
Establish a canonical Normalized Protocol IR:
- `NormalizedRequest`: model, messages, tools, system_instruction, parameters, stream flag.
- `NormalizedMessage`: role (system, user, assistant, tool), content, reasoning_content, tool_calls, tool_results.
- `NormalizedResponse`: response_id, model, content, reasoning_content, tool_calls, finish_reason, usage tokens.
- Adapters only translate between native formats and IR ($2 \times N$ complexity).

## Consequences
- O(N) architectural scalability.
- Standardized handling of thinking/reasoning blocks across models (Claude 3.7 / DeepSeek / Gemini).
- Zero data loss for multi-turn tool call IDs and arguments.
