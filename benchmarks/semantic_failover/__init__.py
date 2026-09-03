"""Primary research benchmark package."""

from benchmarks.semantic_failover.runner import (
    SemanticFailoverMetrics,
    run_semantic_failover_benchmark,
)

__all__ = ["SemanticFailoverMetrics", "run_semantic_failover_benchmark"]
