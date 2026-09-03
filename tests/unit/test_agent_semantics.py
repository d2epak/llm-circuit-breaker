"""Tests for Agent Semantic State and Budget-Aware Context Compaction."""

import unittest

from llm_circuit_breaker.agent import (
    AgentState,
    ContextBudget,
    ContextManager,
    StateSnapshot,
    estimate_tokens,
)
from llm_circuit_breaker.protocol.ir import (
    NormalizedMessage,
    NormalizedRequest,
    NormalizedToolDefinition,
    NormalizedToolResult,
)


class TestAgentSemantics(unittest.TestCase):

    def test_agent_state_snapshot_roundtrip(self):
        state = AgentState(
            agent_id="test_agent_007",
            objective="Build an asynchronous Raft consensus cluster in Python",
            constraints=["Zero third-party network libraries", "Use python 3.11+"],
            important_decisions=["Leader election uses randomized 150-300ms election timer"],
            tool_definitions=[
                NormalizedToolDefinition(name="write_file", description="Write file", parameters={"type": "object"})
            ],
            known_files={"raft.py": "hash_abc123"},
            unresolved_errors=["Network partition test needs chaos injection"],
        )

        # Snapshot
        snapshot = state.create_snapshot()
        self.assertIn("Build an asynchronous Raft consensus cluster", snapshot.payload_json)

        # Restore from snapshot
        restored = snapshot.restore_agent_state()
        self.assertEqual(restored.agent_id, "test_agent_007")
        self.assertEqual(restored.objective, state.objective)
        self.assertEqual(restored.constraints, state.constraints)
        self.assertEqual(restored.important_decisions, state.important_decisions)
        self.assertEqual(restored.known_files["raft.py"], "hash_abc123")
        self.assertEqual(len(restored.tool_definitions), 1)

    def test_budget_aware_context_compaction_preserves_planted_critical_state(self):
        # Construct large request with planted critical goal, constraint, and large tool output
        planted_goal = "CRITICAL_GOAL: Refactor database connection pool with zero leaks"
        planted_constraint = "CRITICAL_CONSTRAINT: Must not close persistent connections"

        req = NormalizedRequest(
            model="test-model",
            system_instruction="You are a principal engineer.",
            messages=[
                NormalizedMessage(role="user", content=f"{planted_goal}\n{planted_constraint}"),
                NormalizedMessage(role="assistant", content="Understood, inspecting files..."),
                # Turn with massive tool output
                NormalizedMessage(
                    role="user",
                    content="",
                    tool_results=[
                        NormalizedToolResult(
                            tool_call_id="call_dump",
                            tool_name="cat_large_log",
                            content="DATABASE_LOG_LINE_" * 1500,  # ~27,000 characters
                        )
                    ],
                ),
                NormalizedMessage(role="assistant", content="Step 1 complete."),
                NormalizedMessage(role="user", content="Step 2 please."),
                NormalizedMessage(role="assistant", content="Step 2 complete."),
                NormalizedMessage(role="user", content="Step 3 please."),
                NormalizedMessage(role="assistant", content="Step 3 complete."),
                NormalizedMessage(role="user", content="Step 4 please."),
                NormalizedMessage(role="assistant", content="Step 4 complete."),
                NormalizedMessage(role="user", content="Final step please."),
            ],
        )

        initial_tokens = estimate_tokens(req)
        self.assertGreater(initial_tokens, 5000)

        # Target 32k model context with 4k output reservation and 2k safety margin -> ~26k max input budget
        # For this test, set a tight budget to trigger compaction: 1500 tokens
        budget = ContextBudget(model_context_window=3500, desired_output_tokens=1000, safety_margin_tokens=500)
        manager = ContextManager(preserve_tail_turns=4)

        compacted_req, was_compacted = manager.compact(req, budget)

        self.assertTrue(was_compacted)
        compacted_tokens = estimate_tokens(compacted_req)
        self.assertLessEqual(compacted_tokens, budget.available_input_budget)

        # VERIFY INVARIANTS:
        # 1. System instructions strictly preserved
        self.assertEqual(compacted_req.system_instruction, "You are a principal engineer.")

        # 2. Planted Root Goal strictly preserved in first user turn!
        first_user_content = compacted_req.messages[0].content
        self.assertIn(planted_goal, first_user_content)
        self.assertIn(planted_constraint, first_user_content)

        # 3. Massive tool output was compacted
        self.assertIn("compacted by Circuit Breaker", compacted_req.messages[2].tool_results[0].content)


if __name__ == "__main__":
    unittest.main()
