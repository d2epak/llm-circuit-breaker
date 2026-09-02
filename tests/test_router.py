import unittest
import time
from unittest.mock import patch
from llm_circuit_breaker.router import UniversalFailoverRouter
from llm_circuit_breaker.classifier import FailoverReason

class TestFailoverRouter(unittest.TestCase):

    def test_routing_and_cooldowns(self):
        fallbacks = [
            {"provider": "nvidia", "model": "nemotron"},
            {"provider": "cerebras", "model": "llama3.3"},
            {"provider": "groq", "model": "llama-versatile"},
        ]
        router = UniversalFailoverRouter(configured_fallbacks=fallbacks, auto_discover_free=False)

        # 1. Initial route is nvidia
        self.assertEqual(router.active_provider["provider"], "nvidia")

        # 2. Nvidia fails with 429 -> cooldown -> failover to cerebras
        router.mark_cooldown("nvidia", seconds=60.0)
        route1 = router.get_next_available_route(reason=FailoverReason.rate_limit)
        self.assertEqual(route1["provider"], "cerebras")

        # 3. Cerebras is deprecated -> failover to groq
        router.mark_deprecated("llama3.3")
        route2 = router.get_next_available_route(reason=FailoverReason.model_not_found)
        self.assertEqual(route2["provider"], "groq")

        # 4. Next route wraps around (nvidia still in cooldown, cerebras deprecated -> skips to groq)
        route3 = router.get_next_available_route(reason=FailoverReason.rate_limit)
        self.assertEqual(route3["provider"], "groq")

if __name__ == "__main__":
    unittest.main()
