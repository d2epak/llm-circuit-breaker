"""Tests for Multi-Agent Isolated Pools and Independent Cooldowns."""

import unittest
from llm_circuit_breaker.pools import IsolatedPoolManager, RouteDefinition


class TestIsolatedPools(unittest.TestCase):

    def setUp(self):
        self.mgr = IsolatedPoolManager()
        self.mgr.coding_routes = [
            RouteDefinition("code-gemini", "gemini", "gemini-2.5-flash", "coding", "http://mock", "gemini", None, 1048576),
            RouteDefinition("code-mistral", "mistral", "codestral-latest", "coding", "http://mock", "openai", None, 256000),
        ]
        self.mgr.agent_routes = [
            RouteDefinition("agent-cerebras", "cerebras", "llama3.3-70b", "general_agent", "http://mock", "openai", None, 65536),
            RouteDefinition("agent-groq", "groq", "llama-3.3-70b-versatile", "general_agent", "http://mock", "openai", None, 131072),
        ]

    def test_pool_selection_independence(self):
        c_route = self.mgr.select_route("coding")
        self.assertEqual(c_route.pool, "coding")
        self.assertEqual(c_route.id, "code-gemini")

        a_route = self.mgr.select_route("general_agent")
        self.assertEqual(a_route.pool, "general_agent")
        self.assertEqual(a_route.id, "agent-cerebras")

    def test_cooldown_in_coding_does_not_affect_agent_pool(self):
        # Place Gemini on cooldown in coding pool
        self.mgr.mark_cooldown("coding", "gemini", seconds=60.0)

        # In coding pool, gemini is skipped -> mistral selected
        c_route = self.mgr.select_route("coding")
        self.assertEqual(c_route.id, "code-mistral")

        # In agent pool, agent-cerebras is still healthy and selected
        a_route = self.mgr.select_route("general_agent")
        self.assertEqual(a_route.id, "agent-cerebras")


if __name__ == "__main__":
    unittest.main()
