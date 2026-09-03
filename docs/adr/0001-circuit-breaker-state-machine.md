# ADR 0001: Finite State Machine for Circuit Breaker

## Status
Accepted

## Context
In the V1 prototype, failover cooldown was implemented as an advisory timestamp (`time.monotonic() + 60.0`). This allowed race conditions under concurrency, lacked slow-call detection, permitted unbounded probe requests during recovery, and failed to comply with standard circuit breaker specifications (e.g. Resilience4j / Martin Fowler).

## Decision
Implement a formal 6-state finite state machine with atomic transitions protected by reentrant synchronization:
- `CLOSED`: Normal operation; calls permitted; failures recorded in sliding window.
- `OPEN`: Calls immediately rejected without network execution (`BreakerOpenError`); transitions to `HALF_OPEN` after `wait_duration_in_open_seconds`.
- `HALF_OPEN`: Allows strictly bounded probe calls (`half_open_max_calls`). Probes are guarded by an in-flight permit counter. If all probes succeed, transition to `CLOSED`. If any probe experiences a poisoning failure, transition back to `OPEN`.
- `FORCED_OPEN`: Administratively tripped breaker; rejects all traffic until cleared.
- `DISABLED`: Circuit breaker protection turned off; all calls pass.
- `METRICS_ONLY`: Pass-through mode where metrics are tracked but calls are never rejected.

## Consequences
- Predictable, thread-safe recovery behavior under heavy agent load.
- Prevents thunderous herd and probe amplification against recovering upstreams.
- Dependency-injected monotonic clocks allow 100% deterministic unit testing without wall-clock sleeps.
