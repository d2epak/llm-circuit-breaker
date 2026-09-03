# ADR 0002: Sliding Window Metrics Algorithm

## Status
Accepted

## Context
Fixed time-window metrics suffer from boundary reset effects where bursts of errors immediately disappear when a new window begins. Conversely, simple counters fail to age out historical errors.

## Decision
Support two sliding window strategies in `SlidingWindowMetrics`:
1. `COUNT_BASED`: Uses a circular buffer of the last $N$ call outcomes. A minimum sample size (`minimum_number_of_calls`) is required before evaluating thresholds.
2. `TIME_BASED`: Uses discrete 1-second sub-buckets across a duration of $T$ seconds, evicting buckets older than $T$.

Both failure rate percentage and slow call rate percentage are evaluated independently:
$$\text{FailureRate} = \frac{\text{Failures}}{\text{TotalCallsInWindow}} \times 100\%$$
$$\text{SlowCallRate} = \frac{\text{SlowCalls}}{\text{TotalCallsInWindow}} \times 100\%$$

## Consequences
- Accurate rolling error accounting with zero boundary cliff artifacts.
- Constant memory consumption bounded by $O(N)$ elements.
