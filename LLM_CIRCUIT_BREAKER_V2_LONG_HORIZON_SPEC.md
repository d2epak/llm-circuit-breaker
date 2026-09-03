# LLM Circuit Breaker V2 — Long-Horizon Implementation Specification

**Repository:** `https://github.com/d2epak/llm-circuit-breaker`  
**Primary implementation agent:** Antigravity  
**Secondary reviewers:** Codex, Claude Code  
**Working mode:** Long-horizon, repository-first, test-gated implementation  
**Target:** Production-grade local/self-hosted agent-resilience gateway with measurable superiority in semantic failover

---

## 0. Mission

Transform the current `llm-circuit-breaker` prototype into a robust **agent-resilience gateway**.

Do not merely add providers, retries, or superficial gateway features.

The finished system must:

1. Reach practical feature parity with serious LLM gateway competitors for the reliability/routing layer.
2. Correctly implement a conventional circuit breaker rather than using "cooldown" as a synonym.
3. Provide provider/model routing based on explicit hard capability constraints plus soft quality/reliability/cost/latency objectives.
4. Preserve agent semantic continuity when the inference provider/model changes.
5. Handle tool calls, structured output, context limits, protocol translation, timeouts, rate limits, malformed outputs, and provider outages as distinct failure classes.
6. Provide deterministic failure-injection tests and benchmark infrastructure so resilience claims are experimentally defensible.
7. Remain lightweight and usable locally.
8. Avoid needless enterprise complexity unless it directly improves correctness, observability, or reproducibility.
9. Maintain backward compatibility with the current documented API surface unless a breaking change is explicitly justified and documented.
10. Produce enough evidence that an external reviewer can compare the system against LiteLLM, OpenRouter, Portkey, Helicone, and a conventional circuit-breaker implementation such as Resilience4j.

The central differentiator should become:

> **Semantic failover for autonomous agents: when an inference substrate fails or becomes unsuitable, preserve task/tool/state invariants while selecting and adapting to a compatible alternative.**

---

# 1. Non-negotiable working rules for the implementation agent

## 1.1 Inspect first

Before changing code:

- inspect the complete repository;
- inspect `README.md`;
- inspect `ARCHITECTURE.md`;
- inspect `pyproject.toml`;
- inspect all source files;
- inspect all tests;
- inspect CI workflows;
- run the existing test suite;
- run lint/type/static checks if present;
- identify claims in documentation that are not currently proven;
- identify current public APIs and compatibility constraints.

Create:

`docs/IMPLEMENTATION_BASELINE.md`

containing:

- current architecture;
- current modules;
- current public interfaces;
- current tests;
- known defects;
- compatibility constraints;
- implementation gaps;
- inferred risk areas.

Do not begin a large refactor before this baseline exists.

## 1.2 Do not ask for clarification

Make reasonable engineering decisions and document them.

Only stop for a user decision when a genuinely irreversible external choice is required, such as:

- changing the repository's license;
- deleting a public API with no compatibility layer;
- introducing a paid/hosted dependency as a mandatory runtime requirement;
- exposing secrets or external credentials.

Otherwise continue autonomously.

## 1.3 Never use real provider APIs as the primary test harness

Build a deterministic mock-provider/fault-injection framework.

Real-provider smoke tests are optional and must never be required for the core suite.

No API keys may appear in:

- source;
- tests;
- fixtures;
- logs;
- examples;
- snapshots.

## 1.4 Preserve causality

Every request attempt must have:

- request ID;
- attempt ID;
- logical operation ID;
- provider;
- model;
- route;
- policy;
- start time;
- end time;
- outcome;
- failure classification;
- whether the request was transformed;
- whether context was compacted;
- whether fallback occurred;
- whether validation failed;
- final disposition.

## 1.5 Fail closed on semantic uncertainty

Never silently turn a malformed or semantically ambiguous tool call into an apparently valid tool invocation unless correctness can be demonstrated.

Distinguish:

- syntactic JSON repair;
- schema repair;
- semantic repair.

The last category should default to **reject + re-ask/fallback**, not silent mutation.

## 1.6 Do not claim "zero downtime", "seamless streaming", "self-healing", or equivalent phrases without a measurable definition

Every reliability claim in the documentation must map to:

- a metric;
- a test;
- a methodology;
- a reproducible result.

---

# 2. Competitive reference model

Use the following systems as design references, not as code to copy:

### Resilience4j

Reference for formal circuit breaker semantics:

- CLOSED / OPEN / HALF_OPEN;
- sliding windows;
- minimum call thresholds;
- failure-rate thresholds;
- slow-call thresholds;
- bounded half-open probes;
- explicit state transitions.

### LiteLLM

Reference for:

- provider abstraction;
- model/provider routing;
- fallback groups;
- retries;
- cooldown behavior;
- routing policies;
- gateway compatibility;
- operational configuration.

### OpenRouter

Reference for:

- provider selection;
- model fallback;
- price/performance routing;
- provider health;
- tool-call-aware provider optimization;
- separation of model selection from provider selection.

### Portkey

Reference for:

- fallback policies;
- retry policies;
- conditional routing;
- load balancing;
- request-level observability;
- governance/configuration separation.

### Helicone

Reference for:

- gateway observability;
- cost/latency metrics;
- provider routing;
- endpoint selection;
- OpenTelemetry;
- rate limiting;
- operational deployment.

### RouteLLM

Reference for:

- task-dependent model selection;
- learned routing;
- quality/cost trade-offs;
- router evaluation methodology.

Do not attempt to reproduce every enterprise feature from these products. Focus on the reliability/routing layer and the agent-specific problems where this project can differentiate.

---

# 3. Target architecture

Move toward these logical planes:

```text
                         CLIENT / AGENT
                              |
                              v
                    +-------------------+
                    | API / Protocol    |
                    | Compatibility     |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    | Request Normalizer|
                    +---------+---------+
                              |
               +--------------+---------------+
               |                              |
               v                              v
      Capability Extractor             Policy Engine
               |                              |
               +--------------+---------------+
                              |
                              v
                    +-------------------+
                    | Candidate Builder |
                    | hard constraints  |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    | Health / Breaker  |
                    | admission control |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    | Scoring / Routing |
                    | quality/cost/etc. |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    | Adaptation Layer  |
                    | protocol/context  |
                    | schema/tool state |
                    +---------+---------+
                              |
                              v
                    +-------------------+
                    | Provider Executor |
                    +---------+---------+
                              |
                      +-------+-------+
                      |               |
                   success          failure
                      |               |
                      v               v
                 validator      failure taxonomy
                      |               |
                 +----+----+          v
                 |         |    breaker/state update
               valid     invalid       |
                 |         |            v
                 |      recover?   next candidate
                 |         |
                 +---------+
                       |
                       v
              semantic response
                       |
                       v
                     AGENT
```

---

# 4. Phase 0 — Baseline and repository audit

## Deliverables

Create:

- `docs/IMPLEMENTATION_BASELINE.md`
- `docs/ARCHITECTURE_V2.md`
- `docs/ADR/0001-target-architecture.md`

Run and record:

- test suite;
- package build;
- import smoke test;
- CLI/proxy startup test;
- type/static checks if available;
- formatting/lint checks;
- current coverage if available.

Fix only trivial blockers required to establish a clean baseline. Do not mix major feature work into Phase 0.

### Exit criterion

A clean baseline exists and all pre-existing failures are classified as:

- pass;
- known defect;
- environment-dependent;
- unavailable without external credentials.

---

# 5. Phase 1 — Formal circuit breaker

Replace the current implicit cooldown-only behavior with a real breaker implementation.

## Required state machine

```text
CLOSED
  |
  | threshold exceeded
  v
OPEN
  |
  | wait duration elapsed
  v
HALF_OPEN
  |                |
  | success        | failure
  v                v
CLOSED            OPEN
```

Support optional administrative states if useful:

- DISABLED;
- FORCED_OPEN;
- METRICS_ONLY.

## Required configuration

At minimum:

```yaml
circuit_breaker:
  failure_rate_threshold: 50
  slow_call_rate_threshold: 50
  slow_call_duration_ms: 5000
  minimum_number_of_calls: 10
  sliding_window_type: time
  sliding_window_size_seconds: 30
  wait_duration_open_ms: 30000
  half_open_max_calls: 2
  max_half_open_duration_ms: 10000
```

Defaults must be conservative and documented.

## Semantics

Implement:

- count-based and/or time-based sliding window;
- minimum sample requirement;
- failure-rate calculation;
- slow-call-rate calculation;
- bounded half-open probe admission;
- thread-safe state transitions;
- monotonic clocks for elapsed-time decisions;
- explicit transition events.

## Failure classification

Do NOT count every error as a provider failure.

Separate:

### Provider availability failures

Examples:

- connection refusal;
- DNS failure;
- TLS failure;
- 408;
- 429;
- 500;
- 502;
- 503;
- 504;
- upstream timeout;
- connection reset.

### Request incompatibility

Examples:

- unsupported parameter;
- invalid request shape;
- provider-specific feature mismatch.

Do not poison provider health for deterministic request incompatibility.

### Agent/semantic failures

Examples:

- malformed tool call;
- invalid structured output;
- schema violation;
- empty response;
- safety refusal.

These require policy-driven handling and should not automatically mean "provider is down."

### Client faults

Examples:

- invalid API key from gateway client;
- malformed JSON request;
- invalid model name supplied by caller.

Never poison provider health for these.

## Tests

At minimum:

1. below-threshold failures remain CLOSED;
2. threshold reached opens breaker;
3. OPEN rejects without upstream call;
4. wait period controls HALF_OPEN;
5. only bounded probe calls enter HALF_OPEN;
6. successful probes close breaker;
7. failed probes reopen breaker;
8. slow-call threshold works independently;
9. ignored exceptions do not affect breaker;
10. concurrent callers cannot exceed half-open permit count;
11. clock behavior is deterministic under injected clock;
12. state transitions emit events.

---

# 6. Phase 2 — Provider/model capability registry

Create a canonical internal representation of providers and models.

Suggested concepts:

```python
Provider
ModelProfile
CapabilityProfile
Endpoint
HealthSnapshot
Policy
```

A `ModelProfile` should describe, where known:

```text
provider
model
protocol
context_window
max_output_tokens
supports_tools
supports_parallel_tools
supports_structured_output
supports_vision
supports_reasoning
supports_streaming
supports_json_mode
supports_system_prompt
supports_multipart
pricing
rate_limit_metadata
region
privacy_class
```

The registry must support incomplete metadata.

Unknown is not equivalent to false unless policy explicitly says so.

---

# 7. Phase 3 — Hard-constraint candidate selection

Replace model-name heuristics such as string matching against "code"/"coder" with an explicit requirement vector.

Represent each request as:

```yaml
requirements:
  tools: required
  structured_output: preferred
  reasoning: preferred
  vision: forbidden
  minimum_context: 90000
  protocol: anthropic
  task_class: coding
  latency_budget_ms: 15000
  maximum_cost_usd: 0.02
  privacy_policy: external_allowed
```

The candidate pipeline must be:

```text
requested model/provider constraints
        ↓
capability requirements
        ↓
hard compatibility filter
        ↓
breaker admission filter
        ↓
policy restrictions
        ↓
soft scoring
```

A candidate that violates a hard constraint must not be selected simply because it is cheap or healthy.

---

# 8. Phase 4 — Routing/scoring engine

Implement pluggable routing strategies.

Minimum strategies:

1. priority;
2. round-robin;
3. weighted;
4. latency-aware;
5. reliability-aware;
6. cost-aware;
7. balanced;
8. adaptive.

Define an explainable score such as:

```text
score =
    w_quality * quality_score
  + w_reliability * reliability_score
  + w_latency * latency_score
  + w_cost * cost_score
  + w_tool_success * tool_success_score
  + w_availability * availability_score
```

All scores must be normalized.

Never permit the scorer to override hard constraints.

Every routing decision should produce an explainable record:

```json
{
  "candidate": "provider/model",
  "eligible": true,
  "hard_constraints": {"passed": true},
  "breaker": "closed",
  "health_score": 0.97,
  "latency_score": 0.82,
  "cost_score": 0.61,
  "tool_success_score": 0.93,
  "final_score": 0.87,
  "rank": 1
}
```

---

# 9. Phase 5 — Reliable retry/fallback policy engine

Do not implement retry logic as nested `try/except` statements scattered across modules.

Create a policy layer.

Suggested model:

```yaml
retry_policy:
  max_attempts: 3
  retry_on:
    - timeout
    - connection_error
    - rate_limit
    - 502
    - 503
    - 504
  never_retry_on:
    - invalid_request
    - auth_error
  backoff:
    algorithm: exponential_jitter
    base_ms: 250
    max_ms: 5000

fallback_policy:
  max_fallbacks: 3
  require_capability_match: true
  avoid_same_endpoint: true
  avoid_recent_failure: true
```

Implement:

- exponential backoff;
- full jitter or equivalent;
- `Retry-After` handling;
- per-attempt timeout;
- overall deadline;
- retry budget;
- fallback budget;
- loop/cycle detection;
- duplicate-attempt protection.

The policy engine must know the difference between:

```text
retry same provider
retry different endpoint
fallback same model/different provider
fallback different model
degraded mode
fail
```

---

# 10. Phase 6 — Request deadline and timeout model

Remove global process-wide socket timeout semantics.

Use explicit per-attempt and per-operation deadlines.

At minimum:

```text
connect timeout
request/write timeout
TTFT timeout
idle stream timeout
total operation deadline
```

The gateway should calculate remaining budget:

```text
remaining_deadline = operation_deadline - elapsed
```

and never start a fallback attempt if insufficient budget remains.

Document why a timeout may cause:

- retry;
- fallback;
- degraded response;
- terminal failure.

---

# 11. Phase 7 — Semantic request normalization

Introduce an internal neutral representation.

Example:

```text
NormalizedRequest
  messages
  system_instruction
  tools
  tool_choice
  response_format
  max_output_tokens
  temperature
  reasoning_settings
  multimodal_parts
  metadata
```

Provider adapters should translate:

```text
native protocol → normalized request → provider protocol
```

Responses should similarly pass through:

```text
provider response → normalized response → caller protocol
```

Do not create pairwise translators for every provider.

Avoid:

```text
Anthropic ↔ OpenAI
Anthropic ↔ Gemini
OpenAI ↔ Gemini
...
```

Instead implement:

```text
Anthropic → IR
OpenAI → IR
Gemini → IR
...
```

This prevents N² complexity.

---

# 12. Phase 8 — Tool-call correctness layer

This is a core differentiator.

Create a validator that checks tool calls against the declared tool schema.

For each tool call:

1. identify tool;
2. validate arguments against schema;
3. classify error;
4. optionally perform deterministic syntactic normalization;
5. reject ambiguous/unsafe repairs;
6. emit structured failure telemetry.

Define:

```text
ToolCallResult:
  valid
  normalized
  invalid
  unsafe_to_repair
```

Examples of safe normalization:

- whitespace normalization;
- valid JSON trailing-comma cleanup if deterministic;
- canonical serialization.

Examples of unsafe repair:

- inventing missing required fields;
- guessing tool names;
- coercing arbitrary natural language into executable arguments;
- replacing invalid arguments with `{}`.

Add a configurable policy:

```yaml
tool_validation:
  strict: true
  allow_syntactic_repairs: true
  allow_semantic_repairs: false
  max_repair_attempts: 1
```

---

# 13. Phase 9 — Agent semantic state

Create an explicit agent-state representation.

It must be possible to preserve, independent of provider:

```text
task objective
constraints
important decisions
tool definitions
tool execution state
known files/state
latest tool outputs
unresolved errors
current subgoal
conversation history
```

Do not rely exclusively on raw message history.

Create:

`AgentState`

and:

`StateSnapshot`

with serialization/deserialization.

State snapshots must be:

- deterministic;
- versioned;
- size-bounded;
- provider-independent.

---

# 14. Phase 10 — Context adaptation

Replace naive character-count-only pruning with a token-budget-aware context manager.

Required behavior:

```text
target model context
      ↓
estimate exact or conservative token budget
      ↓
reserve output budget
      ↓
reserve safety margin
      ↓
compute available input budget
      ↓
select compaction strategy
```

Compaction hierarchy:

1. retain system instructions;
2. retain current user objective;
3. retain unresolved constraints;
4. retain recent turns;
5. retain active tool-call state;
6. retain important tool outputs;
7. summarize older state;
8. truncate low-value raw outputs;
9. drop reconstructable history last.

Implement multiple strategies:

- raw truncation;
- structured tool-result summarization;
- message summarization;
- state reconstruction;
- hybrid compaction.

Token estimation must be model/provider-aware where practical.

If an exact tokenizer is unavailable, use a conservative estimate and record the method used.

Never claim "without losing context" unless verified experimentally.

---

# 15. Phase 11 — Context-overflow recovery

Explicitly detect:

- 400 context errors;
- 413;
- provider-specific context-limit errors;
- token-budget validation errors.

Recovery path:

```text
context failure
   ↓
reduce context
   ↓
revalidate against target budget
   ↓
retry same candidate
   ↓
if impossible → select larger-context candidate
```

Do not blindly switch providers first.

The router should determine whether:

- the selected provider is unsuitable;
- the request is too large;
- the context can be compacted safely.

---

# 16. Phase 12 — Streaming architecture

The current synthetic-stream approach must be retained only as one explicit strategy.

Implement two modes:

### Mode A — true streaming

Pass upstream chunks through when:

- request is streaming;
- provider supports compatible streaming;
- semantic failover is not required mid-stream.

### Mode B — atomic/synthetic response

Buffer upstream generation when:

- response atomicity is preferred;
- provider-switch semantics require full-response validation;
- tool/structured-output validation requires complete response;
- the request is configured for resilient replay.

Expose the trade-off explicitly.

Metrics:

- TTFT;
- total latency;
- buffered latency;
- bytes buffered;
- response generation time;
- synthetic-vs-true streaming mode.

Never describe synthetic streaming as equivalent to true streaming.

---

# 17. Phase 13 — Mid-stream failure semantics

Do not pretend that a new provider can continue from an arbitrary partial token stream.

Define explicit policies:

```text
stream_failure_policy:
  abort
  restart_full_response
  restart_with_state
  disable_fallback_after_first_byte
```

Default should favor correctness.

For agent tool calls, only commit tool execution after the complete tool call passes validation.

The benchmark must test:

- failure before first byte;
- failure after text;
- failure during tool-call emission;
- connection reset;
- malformed final chunk.

---

# 18. Phase 14 — Provider health telemetry

Track per provider/model/endpoint:

```text
requests
successes
failures
timeouts
429s
5xx
context failures
schema failures
tool-call failures
TTFT
total latency
tokens
cost
fallback count
retry count
breaker state
```

Maintain rolling statistics.

Separate:

- provider availability health;
- request semantic quality;
- route-level quality.

Do not use a single "health score" for everything.

---

# 19. Phase 15 — Observability

Implement structured logging plus metrics.

Every logical operation should expose:

```text
request_id
operation_id
attempt_id
agent_id
route_id
provider
model
breaker_state
attempt_index
fallback_index
latency_ms
ttft_ms
input_tokens
output_tokens
estimated_cost
failure_class
retry_reason
fallback_reason
context_compacted
context_tokens_before
context_tokens_after
tool_calls
tool_validation_result
final_status
```

Support at least:

- JSON logs;
- counters;
- histograms;
- gauges;
- routing-decision explanations.

Add optional OpenTelemetry support rather than making it mandatory.

Do not log secrets or raw prompts by default.

---

# 20. Phase 16 — Rate-limit intelligence

Treat 429s as structured events.

Parse:

- `Retry-After`;
- provider-specific reset headers where available;
- remaining quota headers where available.

Support:

```text
provider unavailable until timestamp
```

rather than only a fixed cooldown.

A 429 with `Retry-After: 60` should not be retried after 250 ms merely because generic exponential backoff says so.

Implement token-aware/request-aware admission if provider quotas are known.

---

# 21. Phase 17 — Load balancing

Add:

- priority;
- weighted round robin;
- least-latency;
- least-failure-rate;
- weighted adaptive.

Avoid random routing as the default.

Support sticky routing when useful for:

- cache locality;
- provider-specific session affinity;
- reproducibility.

Make stickiness compatible with breaker override.

---

# 22. Phase 18 — Cost intelligence

Introduce a pricing registry.

Track:

```text
input_price_per_1m
output_price_per_1m
cached_input_price
reasoning_price
minimum_charge
free_tier
```

Cost scoring must never violate hard requirements.

Provide:

```text
max_request_cost
monthly_budget
route_budget
agent_budget
```

At minimum implement request-level cost ceilings.

If exact provider billing cannot be determined, label cost as estimated.

---

# 23. Phase 19 — Autonomous free-model discovery

Retain the existing discovery concept but make it evidence-based.

Discovery must validate:

1. model still exists;
2. provider endpoint is available;
3. advertised context is sufficient;
4. tools are supported;
5. required request format is supported;
6. pricing is actually zero under the relevant conditions;
7. model is permitted by policy.

Then optionally run a lightweight capability probe.

Store:

```text
last_verified
verification_source
verification_latency
tool_probe_result
structured_output_probe_result
```

Do not promote a model simply because metadata says "tools=true".

---

# 24. Phase 20 — Adaptive routing / learning without unsafe autonomous drift

Build a pluggable scorer that can learn from historical telemetry.

Start with deterministic online statistics:

```text
EMA latency
EMA success
EMA tool success
EMA context failure
EMA semantic validation success
```

Do not start with a black-box RL system.

The router must remain:

- interpretable;
- deterministic under frozen telemetry;
- bounded;
- auditable.

Optional later extension:

- contextual bandit;
- learned router;
- RouteLLM-style quality predictor.

But do not make learned routing a requirement for V2 completion.

---

# 25. Phase 21 — Recovery verification

A fallback response must be validated before being returned.

Pipeline:

```text
provider response
     ↓
protocol decode
     ↓
schema validation
     ↓
tool-call validation
     ↓
semantic sanity checks
     ↓
usage/cost extraction
     ↓
return
```

A provider returning HTTP 200 with malformed tool calls must be treated according to policy, not as automatic success.

Introduce a `ResponseValidator` interface.

---

# 26. Phase 22 — Loop/cascade protection

The router must detect:

- repeated same-provider retries;
- provider cycles;
- model cycles;
- fallback recursion;
- retry storms;
- multiple gateways retrying the same request;
- insufficient deadline.

Implement an attempt ledger:

```text
attempt 1: A/model-X
attempt 2: A/model-X retry
attempt 3: B/model-X fallback
attempt 4: C/model-Y fallback
```

Before each attempt, verify:

- not already exhausted;
- candidate not already attempted unless explicitly allowed;
- enough deadline remains;
- budget remains;
- request is still semantically compatible.

---

# 27. Phase 23 — Configuration system

Provide one canonical configuration schema.

Example:

```yaml
gateway:
  host: 127.0.0.1
  port: 8080

routing:
  strategy: adaptive
  max_attempts: 4
  max_fallbacks: 3

providers:
  - id: anthropic
    api_key_env: ANTHROPIC_API_KEY
    enabled: true
  - id: openai
    api_key_env: OPENAI_API_KEY
    enabled: true

circuit_breaker:
  failure_rate_threshold: 50
  minimum_number_of_calls: 10
  wait_duration_open_ms: 30000
  half_open_max_calls: 2

timeouts:
  connect_ms: 5000
  ttft_ms: 15000
  idle_stream_ms: 10000
  total_ms: 60000

context:
  safety_margin_tokens: 2048
  compaction_enabled: true

tools:
  validation: strict
  allow_syntactic_repairs: true
  allow_semantic_repairs: false

observability:
  logs: json
  prompts: false
  metrics: true
  otel: false
```

Environment variables may override configuration.

Configuration validation must fail at startup for impossible combinations.

---

# 28. Phase 24 — Provider adapter interface

Create a narrow provider interface.

Conceptually:

```python
class ProviderAdapter(Protocol):
    provider_id: str

    def capabilities(self, model: str) -> ModelProfile: ...

    def prepare_request(
        self,
        request: NormalizedRequest,
        target: Endpoint,
    ) -> PreparedRequest: ...

    def execute(
        self,
        prepared: PreparedRequest,
        deadline: Deadline,
    ) -> ProviderResponse: ...

    def normalize_response(
        self,
        response: ProviderResponse,
    ) -> NormalizedResponse: ...
```

Provider-specific code must not leak into the router.

Add adapters incrementally.

Do not add a new provider until:

- capability metadata;
- translation;
- error mapping;
- timeout behavior;
- mock adapter;
- tests

exist.

---

# 29. Phase 25 — Deterministic fault-injection framework

Create:

`tests/faults/`

with programmable providers capable of:

- return 200;
- return 429 with Retry-After;
- return 500;
- return 503;
- delay response;
- delay TTFT;
- stall;
- reset connection;
- fail mid-stream;
- return context error;
- return malformed JSON;
- return invalid tool call;
- return valid response with wrong schema;
- return empty response;
- change behavior after N requests.

Example configuration:

```python
Scenario(
    provider="A",
    sequence=[
        Failure.timeout,
        Failure.rate_limit(retry_after=5),
        Success.response(...)
    ]
)
```

This becomes the foundation of all resilience tests.

---

# 30. Phase 26 — Reproducible agent benchmark harness

Build:

`benchmarks/`

with synthetic agent workloads.

Minimum scenarios:

### B1 — provider outage

Primary provider permanently fails.

Measure fallback success.

### B2 — intermittent 429

Provider alternates 429/success.

Measure throughput, retries, and recovery.

### B3 — timeout

Provider stalls beyond TTFT or total deadline.

### B4 — context overflow

Primary supports 128k; fallback only 32k.

Measure whether compaction allows recovery.

### B5 — malformed tool call

Primary emits malformed tool JSON; fallback should recover without unsafe tool execution.

### B6 — incompatible tool schema

Provider rejects schema.

Router should classify as compatibility failure rather than poison health.

### B7 — mid-stream connection reset

Measure response correctness and policy behavior.

### B8 — cross-agent rate-limit contention

Two independent logical agents share a provider.

Measure whether per-agent/provider routing prevents one workload from starving the other.

### B9 — provider recovery

Provider fails, breaker opens, provider recovers.

Measure half-open recovery time and probe containment.

### B10 — multi-failure cascade

A → B → C fail in different ways.

Measure bounded attempts and useful terminal diagnostics.

---

# 31. Phase 27 — Baselines

Implement a benchmark harness that can compare:

1. direct provider;
2. naive retry;
3. naive ordered fallback;
4. current V1 implementation;
5. V2 formal breaker;
6. V2 semantic failover;
7. optionally LiteLLM;
8. optionally OpenRouter.

Where external systems cannot be executed reproducibly without credentials, use published capability evidence plus clearly labeled non-executable comparisons.

Do not fabricate comparative results.

---

# 32. Phase 28 — Metrics and acceptance targets

The following are engineering targets, not claims that may be reported without measurement.

## Reliability

Target:

- zero unbounded retry loops;
- zero fallback cycles;
- 100% deterministic breaker state-transition tests;
- 100% protection against half-open probe stampede.

## Semantic safety

Target:

- zero unsafe tool-call repairs in strict mode;
- invalid tool calls never execute;
- context compaction tests preserve required state fields;
- provider translation round-trips preserve required semantic invariants.

## Recovery

For synthetic fault scenarios:

- >95% recovery rate for failures classified as recoverable;
- <5% duplicate logical operations caused by retry/fallback;
- recovery must stop when deadline is exhausted.

These are target thresholds to guide implementation; replace with actual measured values in final documentation.

## Performance

Measure separately:

- direct latency;
- gateway overhead;
- true-stream TTFT;
- synthetic-stream TTFT;
- fallback recovery latency.

Do not optimize a headline average at the expense of tail behavior.

Report:

- median;
- P95;
- P99 where sample size permits.

---

# 33. Phase 29 — Security hardening

Audit:

- API key handling;
- URL/query-string credentials;
- log redaction;
- prompt/response logging;
- SSRF risk;
- arbitrary endpoint configuration;
- header forwarding;
- request-size limits;
- response-size limits;
- resource exhaustion;
- retry amplification;
- malicious tool schemas;
- prompt injection through tool results.

Provider secrets must never be placed in URLs if a secure header mechanism exists.

Add security tests where appropriate.

---

# 34. Phase 30 — Concurrency and state correctness

The gateway must be correct under concurrency.

Test:

- many requests hitting one provider;
- multiple agents;
- concurrent breaker transitions;
- simultaneous half-open probes;
- concurrent discovery;
- concurrent provider health updates;
- concurrent request cancellation;
- shutdown during in-flight request.

Use locks or atomics deliberately.

Document state ownership.

Avoid global mutable state where possible.

---

# 35. Phase 31 — Persistence / multi-process mode

Keep the default deployment lightweight.

Add optional state persistence abstraction:

```text
HealthStore
BreakerStore
TelemetryStore
```

Provide:

- in-memory implementation;
- SQLite implementation if useful;
- optional Redis implementation only if justified.

The core gateway must remain runnable without Redis.

Document which guarantees apply to:

- single-process;
- multi-process;
- distributed deployments.

Do not claim distributed breaker guarantees without shared state.

---

# 36. Phase 32 — API compatibility

Maintain:

- OpenAI-compatible endpoint support;
- Anthropic Messages-compatible endpoint support;
- existing documented routes.

Where semantics cannot be perfectly preserved, return explicit errors or warnings.

Add compatibility contract tests.

---

# 37. Phase 33 — Developer experience

Provide:

```text
examples/
  minimal/
  multi-provider/
  agent-resilience/
  fault-injection/
```

Provide a one-command local demo:

```bash
python -m llm_circuit_breaker.demo
```

The demo must simulate:

- primary provider failure;
- breaker OPEN;
- fallback;
- recovery;
- tool-call validation;
- context compaction.

No real API keys required.

---

# 38. Phase 34 — Documentation rewrite

Rewrite:

`README.md`

to describe what is actually implemented.

Avoid unsupported marketing language.

Include:

- architecture;
- installation;
- configuration;
- supported protocols;
- provider model;
- circuit breaker semantics;
- routing;
- tool safety;
- context adaptation;
- streaming trade-offs;
- observability;
- benchmark methodology;
- limitations;
- competitor positioning;
- reproducible results.

Rewrite:

`ARCHITECTURE.md`

to reflect V2.

Add:

`docs/RELIABILITY_MODEL.md`

`docs/FAILURE_TAXONOMY.md`

`docs/ROUTING_POLICY.md`

`docs/SEMANTIC_FAILOVER.md`

`docs/BENCHMARKS.md`

`docs/SECURITY.md`

`docs/OPERATIONS.md`

---

# 39. ADR requirements

Create ADRs for major architectural choices.

At minimum:

1. target architecture;
2. normalized request/response IR;
3. circuit breaker semantics;
4. retry/fallback separation;
5. context compaction design;
6. semantic tool validation;
7. streaming policy;
8. health-state persistence;
9. routing/scoring;
10. observability.

Each ADR should contain:

- context;
- decision;
- alternatives;
- trade-offs;
- consequences;
- test strategy.

---

# 40. Code quality requirements

Prefer:

- standard library where practical;
- minimal third-party dependencies;
- small focused modules;
- explicit types;
- dependency injection for clocks, stores, providers;
- deterministic tests;
- pure functions for classification/scoring where possible.

Avoid:

- giant router classes;
- hidden global state;
- implicit retries;
- provider-specific hacks inside generic routing code;
- circular imports;
- background threads without lifecycle management;
- swallowing exceptions.

---

# 41. Testing requirements

Final suite should include:

### Unit tests

All core pure logic.

### Contract tests

Provider adapter behavior.

### Integration tests

Gateway request path.

### Concurrency tests

Breaker and health state.

### Fault-injection tests

All failure types.

### Property-based tests

Where valuable:

- breaker transitions;
- scoring monotonicity;
- context budget calculations;
- retry budget invariants.

### Golden tests

Protocol translation and tool schemas.

### Regression tests

Every discovered bug gets a regression test.

---

# 42. CI requirements

CI should run:

- supported Python versions;
- formatting;
- lint;
- type checking;
- unit tests;
- integration tests;
- fault-injection suite;
- coverage;
- package build;
- import smoke test.

Add a compatibility matrix for Python versions actually supported by `pyproject.toml`.

CI must not require external provider credentials.

---

# 43. Release criteria

Do not declare V2 complete until all of the following are true:

- formal circuit breaker implemented;
- retries/fallbacks are policy-driven;
- routing uses capability constraints;
- provider health is tracked;
- request deadlines exist;
- protocol normalization exists;
- tool-call validation is strict by default;
- context compaction is budget-aware;
- context-overflow recovery works;
- streaming modes are explicit;
- fallback loops are impossible;
- deterministic fault injection exists;
- concurrency tests pass;
- security review is documented;
- benchmark suite exists;
- README reflects reality;
- architecture docs match code;
- CI is green;
- all known limitations are documented.

---

# 44. Final benchmark report

Create:

`results/v2_benchmark_report.md`

It must contain:

## Environment

- machine;
- Python version;
- package version/commit;
- configuration;
- benchmark seed.

## Systems

- V1;
- V2;
- direct baseline;
- external gateway baselines where reproducibly executable.

## Scenarios

List every fault scenario.

## Metrics

Report:

- success rate;
- recovery rate;
- total latency;
- recovery latency;
- TTFT;
- P95/P99;
- attempts/request;
- fallback depth;
- token overhead;
- cost estimate;
- semantic/tool error rate.

## Statistical methodology

For repeated scenarios:

- number of runs;
- confidence intervals where appropriate;
- seed;
- variance;
- exclusion rules.

Do not cherry-pick successful examples.

---

# 45. What V2 should claim as its unique contribution

Do NOT claim:

> "We invented LLM routing."

Do NOT claim:

> "We invented provider fallback."

Do NOT claim:

> "We have a better gateway than LiteLLM/OpenRouter overall."

The defensible claim is:

> **V2 treats LLM failover as a semantic continuity problem rather than only an availability problem. It combines formal circuit-breaking with capability-aware routing, protocol adaptation, context adaptation, tool-call validation, and bounded recovery for autonomous agents.**

The most important experiment is therefore:

```text
provider failure
      ↓
model/provider changes
      ↓
capability mismatch detected
      ↓
request adapted
      ↓
context adapted
      ↓
tool semantics validated
      ↓
agent task continues
```

---

# 46. Suggested final repository structure

Target approximately:

```text
src/llm_circuit_breaker/
  api/
  config.py
  models.py
  errors.py

  breaker/
    state.py
    metrics.py
    registry.py

  routing/
    requirements.py
    candidates.py
    policies.py
    scoring.py
    router.py

  providers/
    base.py
    registry.py
    anthropic.py
    openai.py
    gemini.py
    openrouter.py

  protocol/
    ir.py
    anthropic.py
    openai.py
    gemini.py

  agent/
    state.py
    snapshots.py
    context.py
    compaction.py
    tool_validation.py

  execution/
    deadlines.py
    retries.py
    fallback.py
    streaming.py

  health/
    telemetry.py
    health_store.py

  discovery/
    catalog.py
    verification.py

  observability/
    logging.py
    metrics.py
    tracing.py

  server/
    http.py
    asgi.py
    handlers.py

tests/
  unit/
  contract/
  integration/
  concurrency/
  faults/
  regression/
  golden/

benchmarks/
  scenarios/
  harness/
  baselines/
  reports/

docs/
  ADR/
  IMPLEMENTATION_BASELINE.md
  ARCHITECTURE_V2.md
  RELIABILITY_MODEL.md
  FAILURE_TAXONOMY.md
  ROUTING_POLICY.md
  SEMANTIC_FAILOVER.md
  BENCHMARKS.md
  SECURITY.md
  OPERATIONS.md

examples/
```

Do not mechanically create this exact structure if the existing repository supports a materially better organization. Preserve conceptual separation.

---

# 47. Phase execution discipline

For every phase:

1. state objective;
2. inspect affected code;
3. write/update tests first where practical;
4. implement smallest coherent change;
5. run focused tests;
6. run full regression suite;
7. update documentation;
8. inspect diff;
9. remove dead code;
10. commit with a meaningful message;
11. record outcome in `docs/IMPLEMENTATION_LOG.md`.

Suggested commit naming:

```text
v2-01-baseline
v2-02-formal-circuit-breaker
v2-03-capability-registry
v2-04-routing-engine
...
```

Do not create meaningless micro-commits.

---

# 48. Implementation log

Create:

`docs/IMPLEMENTATION_LOG.md`

For each phase record:

```text
Phase
Date
Objective
Files changed
Tests added
Tests run
Results
Known limitations
Performance impact
Security impact
Follow-up
```

---

# 49. Definition of "done"

"Done" does NOT mean:

- code compiles;
- tests pass;
- feature exists.

A phase is done only when:

```text
implementation
+
tests
+
failure cases
+
documentation
+
observability
+
compatibility assessment
```

are complete.

---

# 50. End-to-end acceptance scenario

Build a deterministic scenario approximating an autonomous coding agent:

```text
Agent starts with 90k context requirement.
Primary provider:
  available initially
  supports tools
  128k context

Fallback provider:
  32k context
  supports tools
  different protocol

During task:
  primary begins returning 503
  breaker transitions OPEN
  fallback selected
  context exceeds fallback budget
  context compactor executes
  tool call is generated
  tool arguments are malformed
  syntactic repair is possible
  validator approves deterministic repair
  tool executes
  provider recovers
  breaker enters HALF_OPEN
  probe succeeds
  breaker closes
```

The benchmark must verify:

- no retry storm;
- no duplicate tool execution;
- correct state preservation;
- bounded latency;
- provider recovery;
- correct breaker transitions;
- complete audit trail.

---

# 51. Important negative requirements

Do NOT:

- add dozens of providers merely to inflate feature count;
- introduce mandatory cloud services;
- make Redis mandatory;
- implement opaque autonomous model selection without evaluation;
- silently discard important agent state;
- silently execute repaired/guessed tool calls;
- call synthetic streaming "true streaming";
- use global socket timeouts;
- log secrets;
- log full prompts by default;
- treat client errors as provider health failures;
- treat every 2xx as semantically successful;
- allow unbounded retries;
- allow fallback cycles;
- claim parity without tests;
- claim superiority without a benchmark.

---

# 52. Final deliverables required from Antigravity

At completion, produce:

1. working V2 implementation;
2. passing CI;
3. deterministic fault-injection harness;
4. benchmark harness;
5. V2 benchmark report;
6. updated README;
7. updated architecture documentation;
8. ADR set;
9. migration/compatibility notes;
10. security audit notes;
11. implementation log;
12. final list of known gaps relative to LiteLLM/OpenRouter/Portkey/Helicone;
13. final list of areas where V2 is intentionally differentiated.

The final response from the implementation agent must include:

```text
Repository state
Current commit
Test result
Coverage
Supported protocols
Supported providers
Circuit-breaker semantics
Routing strategies
Semantic failover features
Known limitations
Benchmark results
Competitor parity gaps
Outstanding risks
```

---

# 53. Instructions for autonomous long-horizon execution

Work continuously through the phases.

Do not stop after implementing only the easy gateway features.

If a phase exposes an architectural flaw, fix the architecture before continuing.

If a planned feature conflicts with correctness, choose correctness and document the deviation.

Do not optimize for number of files or amount of code.

Optimize for:

```text
correctness
+
measurability
+
semantic safety
+
resilience
+
maintainability
```

At major milestones, run the complete regression suite.

At the end, perform a fresh repository-wide review as though you were an external principal engineer.

Do not trust your own earlier assumptions.

---

# 54. External-review preparation

After V2 is complete, the repository will be reviewed independently by:

- Codex;
- Claude Code.

The reviewers should specifically challenge:

### Architecture

- Is the abstraction boundary correct?
- Is the normalized IR sufficient?
- Are provider adapters isolated?

### Reliability

- Is the breaker actually a circuit breaker?
- Are state transitions race-free?
- Can retries amplify outages?

### Agent semantics

- Can failover corrupt tool state?
- Can context compaction remove essential facts?
- Can protocol translation change semantics?

### Routing

- Are hard constraints truly hard?
- Can cost/latency heuristics select an inferior model?
- Are telemetry metrics statistically stable?

### Security

- Can secrets leak?
- Can user input trigger SSRF?
- Can a malicious provider response cause execution?

### Research validity

- Are benchmark scenarios reproducible?
- Are baselines fair?
- Are claims backed by measurements?

Do not preemptively weaken criticism to make the project look better.

