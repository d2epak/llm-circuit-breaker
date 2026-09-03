# ADR 0004: Model Capability Registry

## Status
Accepted

## Context
Routing an agent requiring tool calling to an endpoint that only supports basic completion causes runtime crashes. In V1, capabilities were hardcoded or inferred informally.

## Decision
Introduce `ModelProfile` and `CapabilityRegistry`:
- Declares context window size, maximum output tokens, and explicit flags:
  - `supports_tools: bool`
  - `supports_parallel_tools: bool`
  - `supports_structured_output: bool`
  - `supports_vision: bool`
  - `supports_reasoning: bool`
  - `is_free: bool`
- Pre-seeds verified profiles for major frontier and free providers (Cerebras, Groq, Mistral, OpenRouter, NVIDIA, Anthropic, OpenAI, Gemini).
- Provides `RequirementVector.matches_hard_constraints(profile)` to eliminate unqualified models before soft scoring.

## Consequences
- Guarantees agent requests are routed only to candidate models that can fulfill the request's structural requirements.
