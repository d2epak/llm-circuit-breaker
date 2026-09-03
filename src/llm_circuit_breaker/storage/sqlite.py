"""Optional SQLite Persistence Backend for Circuit Breakers and Tool Ledgers."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, Optional, Tuple

from llm_circuit_breaker.agent.idempotency import ToolExecutionRecord, ToolExecutionStatus


class SQLitePersistenceStore:
    """
    Thread-safe SQLite storage for circuit breaker states and tool idempotency receipts.
    Used when persistence across process restarts is required.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS circuit_breakers (
                    breaker_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    failure_rate REAL NOT NULL,
                    slow_call_rate REAL NOT NULL,
                    last_transition_time REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_executions (
                    tool_call_id TEXT PRIMARY KEY,
                    logical_operation_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_hash TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_receipt_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tool_op_hash 
                ON tool_executions(logical_operation_id, tool_name, arguments_hash)
                """
            )
            self._conn.commit()

    def save_breaker_state(
        self,
        breaker_id: str,
        state: str,
        failure_rate: float,
        slow_call_rate: float,
        last_transition_time: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO circuit_breakers (breaker_id, state, failure_rate, slow_call_rate, last_transition_time, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(breaker_id) DO UPDATE SET
                    state = excluded.state,
                    failure_rate = excluded.failure_rate,
                    slow_call_rate = excluded.slow_call_rate,
                    last_transition_time = excluded.last_transition_time,
                    updated_at = excluded.updated_at
                """,
                (breaker_id, state, failure_rate, slow_call_rate, last_transition_time, time.time()),
            )
            self._conn.commit()

    def load_breaker_state(self, breaker_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM circuit_breakers WHERE breaker_id = ?", (breaker_id,))
            row = cur.fetchone()
            if row:
                return dict(row)
            return None

    def save_tool_execution(self, record: ToolExecutionRecord) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tool_executions (
                    tool_call_id, logical_operation_id, tool_name, arguments_hash,
                    arguments_json, status, execution_receipt_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tool_call_id) DO UPDATE SET
                    status = excluded.status,
                    execution_receipt_json = excluded.execution_receipt_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record.tool_call_id,
                    record.logical_operation_id,
                    record.tool_name,
                    record.arguments_hash,
                    json.dumps(record.arguments),
                    record.status.value,
                    json.dumps(record.execution_receipt) if record.execution_receipt else None,
                    record.created_at,
                    record.updated_at,
                ),
            )
            self._conn.commit()

    def check_tool_receipt(
        self,
        logical_operation_id: str,
        tool_name: str,
        arguments_hash: str,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT execution_receipt_json FROM tool_executions
                WHERE logical_operation_id = ? AND tool_name = ? AND arguments_hash = ? AND status = ?
                """,
                (logical_operation_id, tool_name, arguments_hash, ToolExecutionStatus.COMMITTED.value),
            )
            row = cur.fetchone()
            if row and row["execution_receipt_json"]:
                return True, json.loads(row["execution_receipt_json"])
            return False, None
