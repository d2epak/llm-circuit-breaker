# ADR 0003: Hierarchical Failure Classification Taxonomy

## Status
Accepted

## Context
Standard gateways treat any HTTP 4xx or 5xx code as a generic failure, often poisoning healthy providers when a client sends invalid schemas (400) or oversized prompt contexts (413). In multi-agent systems, client faults must never open upstream circuit breakers.

## Decision
Establish a structured failure taxonomy with 6 orthogonal categories:
1. `INFRASTRUCTURE`: 500, 502, 503, 504, connection reset, socket timeout (`poisons_health=True`, `should_fallback=True`).
2. `RATE_LIMIT`: 429, 529, upstream quota (`poisons_health=True`, `retryable=True` after backoff, honors `Retry-After`).
3. `REQUEST_INCOMPATIBILITY`: 413 context window overflow, 400 protobuf schema rejection (`poisons_health=False`, `should_fallback=True` to adapt or choose alternative model).
4. `SEMANTIC_AGENT_FAILURE`: Model generates unparseable tool JSON or hallucinates tool names (`poisons_health=False`, `should_fallback=True` to capable model).
5. `CLIENT_FAULT`: Bad client API token, malformed JSON from agent (`poisons_health=False`, `should_fallback=False`).
6. `UNKNOWN`: Unclassified errors.

## Consequences
- Prevents cascade failures caused by client-side errors.
- Ensures requests with format/context incompatibilities failover gracefully without degrading provider health scores.
