# ADR 0007: Tool Call Schema Validation and Syntactic Normalization

## Status
Accepted

## Context
When models return malformed JSON or miss required tool arguments, naive gateways either crash, pass broken payloads to agent execution environments, or use unprincipled heuristics that synthesize arbitrary parameters (e.g. inventing dummy keys). Synthesizing arbitrary code or parameters is dangerous for code execution agents.

## Decision
Establish Rule 3: **Fail Closed on Semantic Uncertainty**:
- Allow deterministic syntactic normalizations only:
  - Strip markdown code fences (` ```json ... ``` `)
  - Strip trailing commas before closing brackets
  - Trim surrounding whitespace
  - Coerce string digits to integers when schema unambiguously defines `type: integer`
- Prohibit semantic guessing:
  - Never invent missing required fields
  - Never fabricate tool names
  - Never wrap unparseable arbitrary text into dummy commands
- Return `ToolCallResult.UNSAFE_TO_REPAIR` or `INVALID`, triggering clean semantic failover to an alternative model rather than corrupting execution.

## Consequences
- 100% protection against corrupted tool invocations reaching bash or filesystem tools.
- Models prone to syntax errors are smoothly swapped for compliant models without agent crash.
