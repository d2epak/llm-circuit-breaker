"""Tool Execution Idempotency and Deduplication Ledger."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ToolExecutionStatus(str, Enum):
    PROPOSED = "proposed"      # Tool call parsed from model output
    VALIDATED = "validated"    # Tool call passed schema & parameter validation
    SUBMITTED = "submitted"    # Dispatched to local execution environment
    COMMITTED = "committed"    # Execution completed with verified receipt
    AMBIGUOUS = "ambiguous"    # Execution status uncertain (e.g. network dropped after submission)
    FAILED = "failed"          # Execution failed with definitive error


@dataclass
class ToolExecutionRecord:
    """Audit record for a tool execution attempt."""
    tool_call_id: str
    logical_operation_id: str
    tool_name: str
    arguments_hash: str
    arguments: Dict[str, Any]
    status: ToolExecutionStatus = ToolExecutionStatus.PROPOSED
    execution_receipt: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ToolExecutionLedger:
    """
    Thread-safe ledger tracking tool call lifecycles.
    Enforces idempotency and prevents duplicate side-effects when requests
    are retried or failover occurs after network drops.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._records_by_call_id: Dict[str, ToolExecutionRecord] = {}
        self._receipts_by_op_hash: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def compute_arguments_hash(arguments: Any) -> str:
        raw = json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _op_key(self, logical_op_id: str, tool_name: str, arguments_hash: str) -> str:
        return f"{logical_op_id}:{tool_name}:{arguments_hash}"

    def register_tool_call(
        self,
        tool_call_id: str,
        logical_operation_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolExecutionRecord:
        """Register a proposed tool call."""
        arg_hash = self.compute_arguments_hash(arguments)
        with self._lock:
            if tool_call_id in self._records_by_call_id:
                return self._records_by_call_id[tool_call_id]

            rec = ToolExecutionRecord(
                tool_call_id=tool_call_id,
                logical_operation_id=logical_operation_id,
                tool_name=tool_name,
                arguments_hash=arg_hash,
                arguments=dict(arguments),
                status=ToolExecutionStatus.PROPOSED,
            )
            self._records_by_call_id[tool_call_id] = rec
            return rec

    def mark_validated(self, tool_call_id: str) -> None:
        with self._lock:
            rec = self._records_by_call_id.get(tool_call_id)
            if rec and rec.status == ToolExecutionStatus.PROPOSED:
                rec.status = ToolExecutionStatus.VALIDATED
                rec.updated_at = time.time()

    def mark_submitted(self, tool_call_id: str) -> None:
        with self._lock:
            rec = self._records_by_call_id.get(tool_call_id)
            if rec:
                rec.status = ToolExecutionStatus.SUBMITTED
                rec.updated_at = time.time()

    def mark_committed(self, tool_call_id: str, receipt: Dict[str, Any]) -> None:
        """Mark tool call committed and cache receipt for replay idempotency."""
        with self._lock:
            rec = self._records_by_call_id.get(tool_call_id)
            if rec:
                rec.status = ToolExecutionStatus.COMMITTED
                rec.execution_receipt = receipt
                rec.updated_at = time.time()
                op_key = self._op_key(rec.logical_operation_id, rec.tool_name, rec.arguments_hash)
                self._receipts_by_op_hash[op_key] = receipt

    def mark_ambiguous(self, tool_call_id: str, reason: str = "") -> None:
        with self._lock:
            rec = self._records_by_call_id.get(tool_call_id)
            if rec:
                rec.status = ToolExecutionStatus.AMBIGUOUS
                rec.error_message = reason
                rec.updated_at = time.time()

    def mark_failed(self, tool_call_id: str, error_message: str = "") -> None:
        with self._lock:
            rec = self._records_by_call_id.get(tool_call_id)
            if rec:
                rec.status = ToolExecutionStatus.FAILED
                rec.error_message = error_message
                rec.updated_at = time.time()

    def check_idempotency(
        self,
        logical_operation_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check whether an identical tool call already has a committed execution receipt.
        Returns (has_receipt, cached_receipt).
        If has_receipt is True, the tool MUST NOT be executed again.
        """
        arg_hash = self.compute_arguments_hash(arguments)
        op_key = self._op_key(logical_operation_id, tool_name, arg_hash)
        with self._lock:
            if op_key in self._receipts_by_op_hash:
                return True, self._receipts_by_op_hash[op_key]
            return False, None

    def get_record(self, tool_call_id: str) -> Optional[ToolExecutionRecord]:
        with self._lock:
            return self._records_by_call_id.get(tool_call_id)


DEFAULT_TOOL_LEDGER = ToolExecutionLedger()
