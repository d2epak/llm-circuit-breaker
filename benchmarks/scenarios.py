"""Benchmark Scenarios B1 through B10 for Agent Resilience."""

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
    """Return scenarios B1 through B10."""
    return [
        # B1 — Provider Outage
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
        # B3 — Timeout / TTFT Stall
        BenchmarkScenario(
            id="B3",
            name="Upstream Network Timeout",
            description="Primary provider hangs beyond per-attempt timeout; fallback answers promptly.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Generate report")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.timeout(duration_ms=500.0)],
                "provider_b": [MockFaultAction.success("Report generated via Provider B")],
            },
            expected_outcome="timeout_fallback_success",
        ),
        # B4 — Context Overflow
        BenchmarkScenario(
            id="B4",
            name="Context Window Overflow",
            description="Primary 1M context provider down; fallback 32k provider requires context compaction.",
            request=NormalizedRequest(
                model="default",
                system_instruction="You are a coding assistant.",
                messages=[
                    NormalizedMessage(role="user", content="CRITICAL_GOAL: Fix authentication memory leak"),
                    NormalizedMessage(role="assistant", content="LOG_HISTORY_" * 500),
                    NormalizedMessage(role="user", content="Continue work"),
                ],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.server_error(503, "Unavailable")],
                "provider_b": [MockFaultAction.success("Recovery succeeded on compacted history")],
            },
            expected_outcome="compacted_fallback_success",
        ),
        # B5 — Malformed Tool Call
        BenchmarkScenario(
            id="B5",
            name="Malformed Tool Call Arguments",
            description="Primary emits unparseable tool call JSON; strict mode rejects and falls over to valid provider.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Run test")],
                tools=[
                    NormalizedToolDefinition(
                        name="bash",
                        description="Run command",
                        parameters={"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]},
                    )
                ],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.malformed_tool_call("bash")],
                "provider_b": [
                    MockFaultAction.success(
                        content="",
                        tool_calls=[{"id": "tc1", "type": "function", "function": {"name": "bash", "arguments": '{"cmd": "ls"}'}}],
                    )
                ],
            },
            expected_outcome="semantic_tool_fallback_success",
        ),
        # B6 — Incompatible Tool Schema
        BenchmarkScenario(
            id="B6",
            name="Incompatible Tool Schema Rejection",
            description="Provider returns 400 schema error; classified as compatibility failure (does not poison health).",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Run schema task")],
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.server_error(400, "unrecognized parameter: $schema")],
                "provider_b": [MockFaultAction.success("Compatible fallback completed")],
            },
            expected_outcome="compatibility_fallback_success",
        ),
        # B7 — Mid-Stream Reset
        BenchmarkScenario(
            id="B7",
            name="Mid-Stream Reset and Replay",
            description="Provider disconnects mid-response; atomic buffer mode catches error and executes fallback.",
            request=NormalizedRequest(
                model="default",
                messages=[NormalizedMessage(role="user", content="Stream response")],
                stream=True,
            ),
            provider_sequences={
                "provider_a": [MockFaultAction.server_error(502, "Connection reset by peer")],
                "provider_b": [MockFaultAction.success("Clean stream complete")],
            },
            expected_outcome="mid_stream_recovery_success",
        ),
        # B8 — Cross-Agent Contention
        BenchmarkScenario(
            id="B8",
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
        # B9 — Provider Recovery
        BenchmarkScenario(
            id="B9",
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
        # B10 — Multi-Provider Cascade Failure
        BenchmarkScenario(
            id="B10",
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
    ]
