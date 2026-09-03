# ADR 0008: Streaming Architecture and Mid-Stream Failure Handling

## Status
Accepted

## Context
Standard streaming connects the client directly to the upstream SSE connection. If the upstream provider drops the connection after emitting 50 tokens, the client receives a severed stream. Failing over to another provider midway through streaming could emit duplicate or corrupted content if not handled deliberately.

## Decision
Provide two distinct streaming modes:
1. `TRUE_STREAMING` (Mode A): Chunks are streamed directly from compatible upstreams to minimize TTFT. If the connection fails after the first byte is emitted to the client, failover is prevented to avoid corrupting the client's token buffer (`MidStreamFailurePolicy.DISABLE_FALLBACK_AFTER_FIRST_BYTE`).
2. `ATOMIC_BUFFERED` (Mode B): Upstream response is completely buffered and validated before streaming. Synthetic SSE events are then emitted at line rate to the client. If an error occurs upstream, the gateway seamlessly fails over to another provider and completes the turn cleanly before sending anything to the client.

## Consequences
- Agents requiring strict validation and zero mid-turn network drops can choose Mode B.
- Interactive latency-critical chat can choose Mode A.
