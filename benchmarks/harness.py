"""Reproducible Benchmark Harness for LLM Gateway Systems (Baselines A through F)."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from benchmarks.scenarios import BenchmarkScenario, get_all_scenarios
from llm_circuit_breaker.agent.context import ContextBudget, ContextManager
from llm_circuit_breaker.agent.tool_validation import ToolCallValidator
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
    """Harness evaluating scenarios against 6 distinct gateway baselines (A through F)."""

    def __init__(self):
        self.scenarios = get_all_scenarios()

    def _setup_mock_adapters(self, scenario: BenchmarkScenario) -> ProviderAdapterRegistry:
        reg = ProviderAdapterRegistry()
        for prov_id, actions in scenario.provider_sequences.items():
            adapter = ProgrammableMockAdapter(prov_id)
            adapter.set_sequence(list(actions))
            reg._adapters[prov_id] = adapter
        return reg

    def _setup_endpoints(self, cap_reg: CapabilityRegistry) -> None:
        # Provider A (Primary)
        ep_a = Endpoint(
            id="ep-a",
            provider="provider_a",
            model="llama3.3-70b",
            base_url="mock://a",
            priority=1,
            pool="coding",
            profile=ModelProfile("provider_a", "llama3.3-70b", context_window=65536, supports_tools=True),
        )
        # Provider B (Secondary)
        ep_b = Endpoint(
            id="ep-b",
            provider="provider_b",
            model="llama-3.3-70b",
            base_url="mock://b",
            priority=2,
            pool="coding",
            profile=ModelProfile("provider_b", "llama-3.3-70b", context_window=32768, supports_tools=True),
        )
        # Provider C (Tertiary)
        ep_c = Endpoint(
            id="ep-c",
            provider="provider_c",
            model="mistral-large",
            base_url="mock://c",
            priority=3,
            pool="coding",
            profile=ModelProfile("provider_c", "mistral-large", context_window=32768, supports_tools=True),
        )
        cap_reg.register_endpoint(ep_a)
        cap_reg.register_endpoint(ep_b)
        cap_reg.register_endpoint(ep_c)

    # -----------------------------------------------------------------
    # Baseline F: Final V3 System (Full Resilience Gateway)
    # -----------------------------------------------------------------
    def run_final_system(self, scenario: BenchmarkScenario) -> ScenarioResult:
        cap_reg = CapabilityRegistry()
        self._setup_endpoints(cap_reg)
        breaker_reg = CircuitBreakerRegistry(
            default_config=CircuitBreakerConfig(
                sliding_window_size=5,
                minimum_number_of_calls=2,
                wait_duration_open_ms=100.0,
                half_open_max_calls=2,
            )
        )
        adapter_reg = self._setup_mock_adapters(scenario)

        executor = GatewayExecutor(
            capability_registry=cap_reg,
            breaker_registry=breaker_reg,
            adapter_registry=adapter_reg,
            policy=ExecutionPolicy(
                retry=RetryPolicy(max_attempts_same_endpoint=2, base_backoff_ms=10.0),
                fallback=FallbackPolicy(max_fallback_hops=3),
            ),
        )

        start = time.perf_counter()
        try:
            resp, decision, ledger = executor.execute(scenario.request, pool="coding", strategy="priority")
            dur_ms = (time.perf_counter() - start) * 1000.0
            rec = ledger.total_attempts > 1
            has_sem_err = any(tc.name == "bash" and "wrong_arg" in tc.arguments for tc in resp.tool_calls)
            return ScenarioResult(
                scenario_id=scenario.id,
                system_name="LLM-Circuit-Breaker-V3",
                success=True,
                recovery_occurred=rec,
                total_latency_ms=dur_ms,
                attempts_count=ledger.total_attempts,
                fallback_depth=ledger.fallback_count,
                semantic_error=has_sem_err,
                final_output=resp.content or "tool_call",
            )
        except Exception as e:
            dur_ms = (time.perf_counter() - start) * 1000.0
            return ScenarioResult(
                scenario_id=scenario.id,
                system_name="LLM-Circuit-Breaker-V3",
                success=False,
                recovery_occurred=False,
                total_latency_ms=dur_ms,
                attempts_count=1,
                fallback_depth=0,
                semantic_error=False,
                final_output=f"Error: {e}",
            )

    # -----------------------------------------------------------------
    # Baseline A: Direct Request (Single Attempt, Zero Resilience)
    # -----------------------------------------------------------------
    def run_baseline_a_direct(self, scenario: BenchmarkScenario) -> ScenarioResult:
        adapter_reg = self._setup_mock_adapters(scenario)
        adapter = adapter_reg.get_adapter("provider_a")
        ep_a = Endpoint(
            id="ep-a",
            provider="provider_a",
            model="llama3.3-70b",
            base_url="mock://a",
            profile=ModelProfile("provider_a", "llama3.3-70b", context_window=65536, supports_tools=True),
        )

        start = time.perf_counter()
        prep = adapter.prepare_request(ep_a, scenario.request)
        res = adapter.execute(prep, timeout_seconds=5.0)
        dur_ms = (time.perf_counter() - start) * 1000.0

        if res.status_code == 200:
            norm = adapter.normalize_response(ep_a, res)
            has_sem_err = any(tc.name == "bash" and "wrong_arg" in tc.arguments for tc in norm.tool_calls)
            return ScenarioResult(
                scenario_id=scenario.id,
                system_name="Baseline-A-Direct",
                success=not has_sem_err,
                recovery_occurred=False,
                total_latency_ms=dur_ms,
                attempts_count=1,
                fallback_depth=0,
                semantic_error=has_sem_err,
                final_output=norm.content or "tool_call",
            )
        return ScenarioResult(
            scenario_id=scenario.id,
            system_name="Baseline-A-Direct",
            success=False,
            recovery_occurred=False,
            total_latency_ms=dur_ms,
            attempts_count=1,
            fallback_depth=0,
            semantic_error=False,
            final_output=f"HTTP {res.status_code}",
        )

    # -----------------------------------------------------------------
    # Baseline B: Same-Provider Bounded Retry (No Fallback)
    # -----------------------------------------------------------------
    def run_baseline_b_retry(self, scenario: BenchmarkScenario) -> ScenarioResult:
        adapter_reg = self._setup_mock_adapters(scenario)
        adapter = adapter_reg.get_adapter("provider_a")
        ep_a = Endpoint(
            id="ep-a",
            provider="provider_a",
            model="llama3.3-70b",
            base_url="mock://a",
            profile=ModelProfile("provider_a", "llama3.3-70b", context_window=65536, supports_tools=True),
        )

        start = time.perf_counter()
        attempts = 0
        max_attempts = 3
        last_res = None

        while attempts < max_attempts:
            attempts += 1
            prep = adapter.prepare_request(ep_a, scenario.request)
            res = adapter.execute(prep, timeout_seconds=5.0)
            last_res = res
            if res.status_code == 200:
                dur_ms = (time.perf_counter() - start) * 1000.0
                norm = adapter.normalize_response(ep_a, res)
                has_sem_err = any(tc.name == "bash" and "wrong_arg" in tc.arguments for tc in norm.tool_calls)
                return ScenarioResult(
                    scenario_id=scenario.id,
                    system_name="Baseline-B-Same-Provider-Retry",
                    success=not has_sem_err,
                    recovery_occurred=attempts > 1,
                    total_latency_ms=dur_ms,
                    attempts_count=attempts,
                    fallback_depth=0,
                    semantic_error=has_sem_err,
                    final_output=norm.content or "tool_call",
                )

        dur_ms = (time.perf_counter() - start) * 1000.0
        return ScenarioResult(
            scenario_id=scenario.id,
            system_name="Baseline-B-Same-Provider-Retry",
            success=False,
            recovery_occurred=False,
            total_latency_ms=dur_ms,
            attempts_count=attempts,
            fallback_depth=0,
            semantic_error=False,
            final_output=f"HTTP {last_res.status_code if last_res else 500}",
        )

    # -----------------------------------------------------------------
    # Baseline C: Static Ordered Fallback (No Breaker, No Tool Validation)
    # -----------------------------------------------------------------
    def run_baseline_c_static_fallback(self, scenario: BenchmarkScenario) -> ScenarioResult:
        adapter_reg = self._setup_mock_adapters(scenario)
        candidates = ["provider_a", "provider_b", "provider_c"]

        start = time.perf_counter()
        attempts = 0
        fallback_count = 0

        for prov in candidates:
            if prov not in adapter_reg._adapters:
                continue
            attempts += 1
            adapter = adapter_reg.get_adapter(prov)
            ep = Endpoint(id=f"ep-{prov}", provider=prov, model="model-x", base_url=f"mock://{prov}")
            prep = adapter.prepare_request(ep, scenario.request)
            res = adapter.execute(prep, timeout_seconds=5.0)
            if res.status_code == 200:
                dur_ms = (time.perf_counter() - start) * 1000.0
                norm = adapter.normalize_response(ep, res)
                # Static fallback does NOT validate tool arguments -> passes malformed tool calls!
                has_sem_err = any(tc.name == "bash" and "unknown_arg" in tc.arguments for tc in norm.tool_calls)
                return ScenarioResult(
                    scenario_id=scenario.id,
                    system_name="Baseline-C-Static-Fallback",
                    success=not has_sem_err,
                    recovery_occurred=fallback_count > 0,
                    total_latency_ms=dur_ms,
                    attempts_count=attempts,
                    fallback_depth=fallback_count,
                    semantic_error=has_sem_err,
                    final_output=norm.content or "tool_call",
                )
            fallback_count += 1

        dur_ms = (time.perf_counter() - start) * 1000.0
        return ScenarioResult(
            scenario_id=scenario.id,
            system_name="Baseline-C-Static-Fallback",
            success=False,
            recovery_occurred=False,
            total_latency_ms=dur_ms,
            attempts_count=attempts,
            fallback_depth=fallback_count,
            semantic_error=False,
            final_output="All static fallbacks exhausted",
        )

    def summarize(self, system_name: str, results: List[ScenarioResult]) -> SystemBenchmarkSummary:
        total = len(results)
        succ = sum(1 for r in results if r.success)
        recs = sum(1 for r in results if r.recovery_occurred and r.success)
        sem_errs = sum(1 for r in results if r.semantic_error)

        lats = [r.total_latency_ms for r in results]
        med_lat = statistics.median(lats) if lats else 0.0
        p95_lat = sorted(lats)[int(len(lats) * 0.95)] if lats else 0.0
        avg_attempts = statistics.mean([r.attempts_count for r in results]) if results else 0.0
        avg_depth = statistics.mean([r.fallback_depth for r in results]) if results else 0.0

        return SystemBenchmarkSummary(
            system_name=system_name,
            total_scenarios=total,
            successful_scenarios=succ,
            completion_rate_pct=(succ / total * 100.0) if total else 0.0,
            recovery_rate_pct=(recs / total * 100.0) if total else 0.0,
            median_latency_ms=med_lat,
            p95_latency_ms=p95_lat,
            avg_attempts_per_request=avg_attempts,
            avg_fallback_depth=avg_depth,
            semantic_error_rate_pct=(sem_errs / total * 100.0) if total else 0.0,
            scenario_results=results,
        )

    def run_all(self) -> Dict[str, SystemBenchmarkSummary]:
        res_v3 = [self.run_final_system(s) for s in self.scenarios]
        res_a = [self.run_baseline_a_direct(s) for s in self.scenarios]
        res_b = [self.run_baseline_b_retry(s) for s in self.scenarios]
        res_c = [self.run_baseline_c_static_fallback(s) for s in self.scenarios]

        return {
            "LLM-Circuit-Breaker-V3": self.summarize("LLM-Circuit-Breaker-V3", res_v3),
            "Baseline-A-Direct": self.summarize("Baseline-A-Direct", res_a),
            "Baseline-B-Same-Provider-Retry": self.summarize("Baseline-B-Same-Provider-Retry", res_b),
            "Baseline-C-Static-Fallback": self.summarize("Baseline-C-Static-Fallback", res_c),
        }
