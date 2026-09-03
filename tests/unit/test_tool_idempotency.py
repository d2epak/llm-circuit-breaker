"""Unit tests for Tool Execution Idempotency and Deduplication Ledger."""

import unittest

from llm_circuit_breaker.agent.idempotency import (
    ToolExecutionLedger,
    ToolExecutionStatus,
)


class TestToolExecutionIdempotency(unittest.TestCase):
    def setUp(self):
        self.ledger = ToolExecutionLedger()

    def test_tool_call_lifecycle(self):
        rec = self.ledger.register_tool_call(
            tool_call_id="call_1",
            logical_operation_id="op_100",
            tool_name="write_file",
            arguments={"path": "/tmp/test.txt", "content": "hello"},
        )
        self.assertEqual(rec.status, ToolExecutionStatus.PROPOSED)

        self.ledger.mark_validated("call_1")
        self.assertEqual(self.ledger.get_record("call_1").status, ToolExecutionStatus.VALIDATED)

        self.ledger.mark_submitted("call_1")
        self.assertEqual(self.ledger.get_record("call_1").status, ToolExecutionStatus.SUBMITTED)

        receipt = {"bytes_written": 5, "checksum": "abc123"}
        self.ledger.mark_committed("call_1", receipt)
        self.assertEqual(self.ledger.get_record("call_1").status, ToolExecutionStatus.COMMITTED)
        self.assertEqual(self.ledger.get_record("call_1").execution_receipt, receipt)

    def test_idempotency_prevents_duplicate_side_effects_on_retry(self):
        # Scenario: Tool executes successfully on upstream A, but connection drops before response reaches agent.
        # Gateway initiates retry with same logical operation ID and arguments.
        op_id = "agent_turn_42"
        tool_name = "transfer_funds"
        args = {"from_account": "A", "to_account": "B", "amount": 100}

        rec = self.ledger.register_tool_call("call_transfer_1", op_id, tool_name, args)
        self.ledger.mark_submitted("call_transfer_1")
        self.ledger.mark_committed("call_transfer_1", {"tx_id": "tx_999", "status": "settled"})

        # Gateway or Agent retries under same logical operation ID:
        has_receipt, cached_receipt = self.ledger.check_idempotency(op_id, tool_name, args)
        self.assertTrue(has_receipt)
        self.assertIsNotNone(cached_receipt)
        self.assertEqual(cached_receipt["tx_id"], "tx_999")
        self.assertEqual(cached_receipt["status"], "settled")

    def test_different_arguments_or_operation_not_suppressed(self):
        self.ledger.register_tool_call("call_x", "op_1", "run_cmd", {"cmd": "ls"})
        self.ledger.mark_committed("call_x", {"output": "file1.txt"})

        # Different arguments:
        has_receipt, _ = self.ledger.check_idempotency("op_1", "run_cmd", {"cmd": "pwd"})
        self.assertFalse(has_receipt)

        # Different logical operation:
        has_receipt, _ = self.ledger.check_idempotency("op_2", "run_cmd", {"cmd": "ls"})
        self.assertFalse(has_receipt)


if __name__ == "__main__":
    unittest.main()
