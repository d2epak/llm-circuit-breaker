"""Benchmark Scenarios B1 through B15 for Agent Resilience Evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from llm_circuit_breaker.protocol.ir import (
    NormalizedMessage,
    NormalizedRequest,
    NormalizedToolDefinition,
)
from tests.faults.mock_provider import MockFaultAction


@dataclass
class BenchmarkScenario:
    """Benchmark scenario definition."""
    id: str
    name: str
    description: str
    request: NormalizedRequest
    provider_sequences: Dict[str, List[MockFaultAction]]
    expected_outcome: str


def get_all_scenarios() -> List[BenchmarkScenario]:
    """Return complete authoritative benchmark scenarios B1 through B15."""
    tool_def = NormalizedToolDefinition(
        name="bash",
        description="Execute bash command",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    )

    return [
        # B1 — Permanent Outage
        BenchmarkScenario(
            id="B1",
            name="Permanent Provider Outage",
            description="Primary provider permanently fails with 503; secondary provider is healthy.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Execute build")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.server_error(503, "Outage")] * 10,
                "provider_b": [MockFaultAction.success("Build successful via Provider B")],
            },
            expected_outcome="fallback_success",
        ),
        # B2 — Intermittent 429
        BenchmarkScenario(
            id="B2",
            name="Intermittent 429 Rate Limit",
            description="Primary provider alternates 429 (Retry-After: 1s) and 200.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Check health")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.rate_limit(retry_after=1), MockFaultAction.success("Primary recovered")],
                "provider_b": [MockFaultAction.success("Secondary fallback")],
            },
            expected_outcome="retry_or_fallback_success",
        ),
        # B3 — Slow Provider / Timeout
        BenchmarkScenario(
            id="B3",
            name="Slow Provider Timeout Stall",
            description="Primary provider exceeds deadline timeout; secondary succeeds under 100ms.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Run analysis")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.timeout(10.0)],
                "provider_b": [MockFaultAction.success("Quick response from secondary")],
            },
            expected_outcome="deadline_fallback_success",
        ),
        # B4 — Context Mismatch Recovery
        BenchmarkScenario(
            id="B4",
            name="Context Window Mismatch Recovery",
            description="Large conversation (60k tokens) fails over from 128k primary to 32k secondary, compacting safely.",
            request=NormalizedRequest(
                model="default",
                system_instruction="Preserve mission objectives.",
                messages=[
                    NormalizedMessage(role="user", content="ROOT_GOAL: Deploy cluster securely\n" + ("DATA_TOKEN_ " * 1500)),
                    NormalizedMessage(role="assistant", content="Acknowledged."),
                    NormalizedMessage(role="user", content="Status update?"),
                ],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.server_error(503, "Context Outage")],
                "provider_b": [MockFaultAction.success("Compacted context processed successfully by Secondary")],
            },
            expected_outcome="compaction_fallback_success",
        ),
        # B5 — Deep Critical Fact Preservation
        BenchmarkScenario(
            id="B5",
            name="Deep Critical Fact Preservation",
            description="Critical continuation fact buried deep in old history survives compaction.",
            request=NormalizedRequest(
                model="default",
                system_instruction="Keep critical secrets.",
                messages=[
                    NormalizedMessage(role="user", content="CRITICAL_SECRET: auth_token_xyz999\n" + ("PADDING_ " * 1000)),
                    NormalizedMessage(role="assistant", content="Noted secret."),
                    NormalizedMessage(role="user", content="Continue execution."),
                ],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.server_error(503, "Unavailable")],
                "provider_b": [MockFaultAction.success("Retrieved and processed with secret intact")],
            },
            expected_outcome="critical_fact_preserved",
        ),
        # B6 — Malformed Tool Call (Invalid JSON Syntax)
        BenchmarkScenario(
            id="B6",
            name="Malformed Tool Call Syntax",
            description="Primary emits corrupt JSON; validator fails closed and recovers on Secondary.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="List directory contents")],
                tools=[tool_def],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.malformed_tool_json("{command: missing_quotes")],
                "provider_b": [MockFaultAction.valid_tool_call("bash", {"command": "ls -la"})],
            },
            expected_outcome="syntactic_repair_or_failover",
        ),
        # B7 — Semantically Invalid Tool Call (Wrong Schema)
        BenchmarkScenario(
            id="B7",
            name="Semantically Invalid Tool Call Schema",
            description="Primary emits valid JSON but violates schema; validator triggers safe failover.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Execute maintenance")],
                tools=[tool_def],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.valid_tool_call("bash", {"unknown_arg": 123})],
                "provider_b": [MockFaultAction.valid_tool_call("bash", {"command": "echo ok"})],
            },
            expected_outcome="schema_failover_success",
        ),
        # B8 — Tool Execution Ambiguity & Idempotency
        BenchmarkScenario(
            id="B8",
            name="Tool Execution Ambiguity & Idempotency",
            description="Tool executes, network response lost; gateway retry must not re-execute with receipt.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Run safe tool")],
                tools=[tool_def],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.valid_tool_call("bash", {"command": "echo unique_idempotent_test"})],
                "provider_b": [MockFaultAction.valid_tool_call("bash", {"command": "echo unique_idempotent_test"})],
            },
            expected_outcome="idempotent_deduplication",
        ),
        # B9 — Mid-Stream Disconnect Recovery
        BenchmarkScenario(
            id="B9",
            name="Mid-Stream Disconnect Recovery",
            description="Provider drops connection mid-stream; Mode B atomic buffering recovers on secondary.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Generate report")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.mid_stream_reset("Partial report header...")],
                "provider_b": [MockFaultAction.success("Complete atomic report successfully recovered")],
            },
            expected_outcome="mid_stream_recovery_success",
        ),
        # B10 — Provider Recovery & Half-Open Probe
        BenchmarkScenario(
            id="B10",
            name="Provider Recovery and Breaker Probe",
            description="Provider trips breaker to OPEN, wait duration elapses, HALF_OPEN probe closes breaker.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Probe health")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.success("Provider recovered and healthy")],
            },
            expected_outcome="probe_recovery_success",
        ),
        # B11 — Multi-Provider Cascade Failure
        BenchmarkScenario(
            id="B11",
            name="Multi-Provider Cascade Failure",
            description="Provider A fails with 500, Provider B fails with 429, Provider C succeeds without loop.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Cascade test")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.server_error(500, "Dead")],
                "provider_b": [MockFaultAction.rate_limit(retry_after=30)],
                "provider_c": [MockFaultAction.success("Cascade resolved at Provider C")],
            },
            expected_outcome="cascade_resolution_success",
        ),
        # B12 — Concurrent Agent Contention
        BenchmarkScenario(
            id="B12",
            name="Cross-Agent Pool Contention",
            description="Coding pool exhausts provider_a; general_agent pool continues unimpeded.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Agent dialogue")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.success("Agent turn succeeded")],
                "provider_b": [MockFaultAction.success("Backup agent turn")],
            },
            expected_outcome="cross_pool_isolation",
        ),
        # B13 — Cost Constraint & Budget Enforcement
        BenchmarkScenario(
            id="B13",
            name="Cost Constraint & Route Selection",
            description="Selects cost-effective candidate within budget ceiling.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Cost sensitive request")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.success("Cost-efficient candidate output")],
                "provider_b": [MockFaultAction.success("Expensive candidate output")],
            },
            expected_outcome="cost_effective_selection",
        ),
        # B14 — Tool Reliability Differentiation
        BenchmarkScenario(
            id="B14",
            name="Tool Reliability Differentiation",
            description="Router selects endpoint with higher historical tool success rate.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Need reliable tool execution")],
                tools=[tool_def],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.valid_tool_call("bash", {"command": "pwd"})],
                "provider_b": [MockFaultAction.valid_tool_call("bash", {"command": "pwd"})],
            },
            expected_outcome="tool_reliability_selection",
        ),
        # B15 — Capability Mismatch Non-Poisoning Failover
        BenchmarkScenario(
            id="B15",
            name="Capability Mismatch Non-Poisoning Failover",
            description="Candidate lacking required capability is filtered without tripping its circuit breaker.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Vision request with image data")],
                tools=[],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.success("Text only")],
                "provider_b": [MockFaultAction.success("Vision capable response")],
            },
            expected_outcome="capability_matched_success",
        ),
    ]
