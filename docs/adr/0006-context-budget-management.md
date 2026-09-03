# ADR 0006: Context Budget Management and Compaction

## Status
Accepted

## Context
When failing over from a large-context model (e.g. Gemini 1M) to a smaller fallback model (e.g. Groq 128k or Cerebras 32k), uncompacted requests trigger 413 or 400 context overflow errors. Naive truncation drops system instructions or current user tasks, inducing amnesia.

## Decision
Implement hierarchical, budget-aware compaction via `ContextManager`:
$$\text{AvailableInputBudget} = \text{ContextWindow} - \text{DesiredOutputTokens} - \text{SafetyMargin}$$

Compaction priority:
1. **Never Drop**: System instructions, root user prompt (turn 0), active constraints.
2. **Preserve Intact**: Latest $K$ turns (default 6) representing current execution context.
3. **Compact**: Truncate large tool outputs in older intermediate turns to representative head and tail previews.
4. **Evict**: Drop oldest intermediate turns between root prompt and recent tail turns only if budget remains exceeded.

## Consequences
- Enables cross-context failover without agent disorientation.
- Critical task objectives and system constraints survive context size reduction.
