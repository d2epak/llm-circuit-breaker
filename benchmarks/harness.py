"""Reproducible Benchmark Harness for LLM Gateway Systems."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from benchmarks.scenarios import BenchmarkScenario, get_all_scenarios
from llm_circuit_breaker.breaker.circuit_breaker import CircuitBreakerConfig
from llm_circuit_breaker.breaker.registry import CircuitBreakerRegistry
from llm_circuit_breaker.capability.profile import Endpoint, ModelProfile
from llm_circuit_breaker.capability.registry import CapabilityRegistry
from llm_circuit_breaker.execution.executor import GatewayExecutor
from llm_circuit_breaker.execution.policy import ExecutionPolicy, FallbackPolicy, RetryPolicy
from llm_circuit_breaker.providers.adapters import ProviderAdapterRegistry
from tests.faults.mock_provider import ProgrammableMockAdapter


@dataclass
class ScenarioResult:
    """Outcome metrics for a benchmark scenario."""
    scenario_id: str
    system_name: str
    success: bool
    recovery_occurred: bool
    total_latency_ms: float
    attempts_count: int
    fallback_depth: int
    semantic_error: bool
    final_output: Optional[str] = None


@dataclass
class SystemBenchmarkSummary:
    """Aggregated benchmark metrics across all scenarios."""
    system_name: str
    total_scenarios: int = 0
    successful_scenarios: int = 0
    completion_rate_pct: float = 0.0
    recovery_rate_pct: float = 0.0
    median_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_attempts_per_request: float = 0.0
    avg_fallback_depth: float = 0.0
    semantic_error_rate_pct: float = 0.0
    scenario_results: List[ScenarioResult] = field(default_factory=list)


class BenchmarkHarness:
    """Harness that evaluates scenarios against gateway systems."""

    def __init__(self):
        self.scenarios = get_all_scenarios()

    def run_v2_gateway(self, scenario: BenchmarkScenario) -> ScenarioResult:
        """Execute scenario using LLM Circuit Breaker V2 Gateway."""
        cap_reg = CapabilityRegistry()
        breaker_reg = CircuitBreakerRegistry(
            default_config=CircuitBreakerConfig(minimum_number_of_calls=2, failure_rate_threshold=50.0)
        )
        adapter_reg = ProviderAdapterRegistry()

        # Build mock adapters from scenario definitions
        for prov_id, seq in scenario.provider_sequences.items():
            mock_adapter = ProgrammableMockAdapter(prov_id)
            mock_adapter.set_sequence(seq)
            adapter_reg._adapters[prov_id] = mock_adapter

            ep = Endpoint(
                id=f"ep-{prov_id}",
                provider=prov_id,
                model=f"model-{prov_id}",
                base_url=f"mock://{prov_id}",
                priority=1 if prov_id == "provider_a" else (2 if prov_id == "provider_b" else 3),
                pool="coding",
                profile=ModelProfile(prov_id, f"model-{prov_id}", context_window=65536, supports_tools=True),
            )
            cap_reg.register_endpoint(ep)

        executor = GatewayExecutor(
            capability_registry=cap_reg,
            breaker_registry=breaker_reg,
            adapter_registry=adapter_reg,
            policy=ExecutionPolicy(
                retry=RetryPolicy(max_attempts_same_endpoint=1),
                fallback=FallbackPolicy(max_fallback_hops=4),
                max_total_attempts=5,
            ),
        )

        start = time.monotonic()
        try:
            resp, decision, ledger = executor.execute(
                scenario.request, pool="coding", strategy="priority", deadline_ms=5000.0
            )
            latency = (time.monotonic() - start) * 1000.0
            recovery = ledger.fallback_count > 0 or ledger.total_attempts > 1
            return ScenarioResult(
                scenario_id=scenario.id,
                system_name="LLM-Circuit-Breaker-V2",
                success=True,
                recovery_occurred=recovery,
                total_latency_ms=latency,
                attempts_count=ledger.total_attempts,
                fallback_depth=ledger.fallback_count,
                semantic_error=False,
                final_output=resp.content or "Tool Call",
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000.0
            return ScenarioResult(
                scenario_id=scenario.id,
                system_name="LLM-Circuit-Breaker-V2",
                success=False,
                recovery_occurred=False,
                total_latency_ms=latency,
                attempts_count=1,
                fallback_depth=0,
                semantic_error=False,
                final_output=str(e),
            )

    def run_direct_baseline(self, scenario: BenchmarkScenario) -> ScenarioResult:
        """Direct Provider baseline (fails on first fault without failover)."""
        adapter = ProgrammableMockAdapter("provider_a")
        seq = scenario.provider_sequences.get("provider_a", [])
        adapter.set_sequence(seq)

        start = time.monotonic()
        ep = Endpoint(id="ep-a", provider="provider_a", model="model-a", base_url="mock://a")
        prep = adapter.prepare_request(ep, scenario.request)
        res = adapter.execute(prep, timeout_seconds=0.3)
        latency = (time.monotonic() - start) * 1000.0

        success = res.status_code == 200
        # If tool call was returned, check if malformed
        semantic_err = False
        if success and b"invalid json" in res.body:
            semantic_err = True

        return ScenarioResult(
            scenario_id=scenario.id,
            system_name="Direct-Provider-Baseline",
            success=success and not semantic_err,
            recovery_occurred=False,
            total_latency_ms=latency,
            attempts_count=1,
            fallback_depth=0,
            semantic_error=semantic_err,
        )

    def run_all(self) -> Dict[str, SystemBenchmarkSummary]:
        """Execute full benchmark suite against V2 and Direct Baseline."""
        systems = ["LLM-Circuit-Breaker-V2", "Direct-Provider-Baseline"]
        results: Dict[str, List[ScenarioResult]] = {s: [] for s in systems}

        for sc in self.scenarios:
            results["LLM-Circuit-Breaker-V2"].append(self.run_v2_gateway(sc))
            results["Direct-Provider-Baseline"].append(self.run_direct_baseline(sc))

        summaries: Dict[str, SystemBenchmarkSummary] = {}
        for s, res_list in results.items():
            total = len(res_list)
            succ = sum(1 for r in res_list if r.success)
            recovers = sum(1 for r in res_list if r.recovery_occurred)
            sem_errs = sum(1 for r in res_list if r.semantic_error)
            latencies = [r.total_latency_ms for r in res_list]
            attempts = [r.attempts_count for r in res_list]
            depths = [r.fallback_depth for r in res_list]

            median_lat = statistics.median(latencies) if latencies else 0.0
            p95_lat = sorted(latencies)[int(0.95 * len(latencies))] if latencies else 0.0

            summaries[s] = SystemBenchmarkSummary(
                system_name=s,
                total_scenarios=total,
                successful_scenarios=succ,
                completion_rate_pct=(succ / total) * 100.0 if total > 0 else 0.0,
                recovery_rate_pct=(recovers / total) * 100.0 if total > 0 else 0.0,
                median_latency_ms=median_lat,
                p95_latency_ms=p95_lat,
                avg_attempts_per_request=statistics.mean(attempts) if attempts else 0.0,
                avg_fallback_depth=statistics.mean(depths) if depths else 0.0,
                semantic_error_rate_pct=(sem_errs / total) * 100.0 if total > 0 else 0.0,
                scenario_results=res_list,
            )

        return summaries
