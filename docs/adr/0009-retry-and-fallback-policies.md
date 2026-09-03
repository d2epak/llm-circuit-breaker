# ADR 0009: Bounded Retries, Deadlines, and Cycle Protection

## Status
Accepted

## Context
Unbounded retry loops against failing providers worsen cascading outages. Furthermore, static fallback chains without cycle detection can oscillate between endpoints indefinitely ($A \to B \to A \to B$).

## Decision
Enforce bounded execution via `Deadline`, `RetryPolicy`, `FallbackPolicy`, and `AttemptLedger`:
- **Hierarchical Deadlines**: Every request has a total deadline (e.g. 60s). Each attempt timeout is bounded by `min(per_attempt, remaining_deadline)`.
- **Exponential Backoff with Full Jitter**: Retries on the same endpoint use randomized jitter to desynchronize stampedes. Explicit `Retry-After` headers take precedence.
- **Per-Endpoint Budget**: Maximum attempts on the same endpoint is strictly bounded (default 2).
- **Fallback Hop Budget**: Maximum fallback hops is strictly bounded (default 3).
- **Cycle Prevention**: The `AttemptLedger` tracks traversed endpoints; re-visiting a previously failed endpoint in the same request raises `CycleDetectedError`.

## Consequences
- Guaranteed request termination.
- Zero infinite loops or thundering herds under provider outages.
