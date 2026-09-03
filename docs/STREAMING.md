# Streaming Architecture & Mid-Stream Failover

An authoritative specification of Server-Sent Events (SSE) stream handling and mid-stream disconnect recovery in **LLM Circuit Breaker (V3)**.

---

## 1. The Fundamental Streaming Trilemma

When an LLM streams tokens via SSE, the gateway faces a fundamental trade-off:
- **Low Latency:** Stream tokens immediately to the client as they arrive.
- **Failover Ability:** Buffer tokens so that if the upstream provider crashes after 100 tokens, the request can restart cleanly on a fallback provider without the client receiving truncated or garbage text.
- **Deduplication:** Avoid re-delivering already consumed tokens.

---

## 2. Supported Streaming Modes

### Mode A: Direct Passthrough (Low Latency)
- Tokens are streamed to the client in real-time as SSE chunks.
- If upstream connection fails mid-stream, the stream emits an explicit error event `event: error` with failover metadata.
- Mid-stream failover is **NOT** transparent in Mode A because the client has already consumed partial output.

### Mode B: Atomic Buffered Replay (High Resilience)
- Tokens are buffered in the gateway until generation finishes or tool calls are verified.
- If upstream disconnects or throws 5xx mid-stream, the buffer is discarded and the request is transparently re-dispatched to the fallback candidate.
- Client receives a clean, unbroken stream once the fallback candidate responds.
