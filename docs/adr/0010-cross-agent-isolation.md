# ADR 0010: Multi-Agent Pool Isolation and Contention Prevention

## Status
Accepted

## Context
When high-throughput coding agents (such as Claude Code or Aider) saturate rate limits on a primary provider, shared gateways trip circuit breakers globally. This causes background agents (such as Hermes Agent or OpenClaw) to experience starvation and downtime even though their tasks require completely different model capabilities.

## Decision
Isolate routing pools (`coding` vs `general_agent`):
- Each pool maintains independent route definitions, candidate lists, and priority configurations.
- Cooldowns and rate-limit quotas incurred in one pool do not affect candidate selection in another pool.
- Circuit breaker registries support fine-grained endpoint identifiers (`pool:provider:model`) ensuring agent failure domains remain strictly decoupled.

## Consequences
- Coding agents can burst and failover without degrading conversational or autonomous background agents.
- Independent observability and quota management per agent class.
