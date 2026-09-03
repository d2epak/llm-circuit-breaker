"""Provider Health Telemetry and Performance Metrics."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class EndpointHealthSnapshot:
    """Rolling telemetry and health stats for an endpoint."""
    endpoint_id: str
    provider: str
    model: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    consecutive_failures: int = 0
    ema_latency_ms: float = 200.0
    last_latency_ms: float = 0.0
    cooldown_until_monotonic: float = 0.0
    quota_exhausted_until: float = 0.0
    last_error_message: Optional[str] = None
    last_updated: float = field(default_factory=time.time)

    @property
    def is_in_cooldown(self) -> bool:
        return time.monotonic() < self.cooldown_until_monotonic

    @property
    def is_quota_exhausted(self) -> bool:
        return time.time() < self.quota_exhausted_until

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls


class HealthTelemetryStore:
    """Thread-safe store for provider health telemetry."""

    def __init__(self, ema_alpha: float = 0.2):
        self.ema_alpha = ema_alpha
        self._lock = threading.RLock()
        self._snapshots: Dict[str, EndpointHealthSnapshot] = {}

    def get_or_create(self, endpoint_id: str, provider: str = "", model: str = "") -> EndpointHealthSnapshot:
        with self._lock:
            if endpoint_id not in self._snapshots:
                self._snapshots[endpoint_id] = EndpointHealthSnapshot(
                    endpoint_id=endpoint_id,
                    provider=provider,
                    model=model,
                )
            return self._snapshots[endpoint_id]

    def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        with self._lock:
            snap = self.get_or_create(endpoint_id)
            snap.total_calls += 1
            snap.successful_calls += 1
            snap.consecutive_failures = 0
            snap.last_latency_ms = latency_ms
            # Update Exponential Moving Average (EMA) of latency
            snap.ema_latency_ms = (self.ema_alpha * latency_ms) + ((1.0 - self.ema_alpha) * snap.ema_latency_ms)
            snap.last_updated = time.time()

    def record_failure(
        self,
        endpoint_id: str,
        latency_ms: float,
        error_message: str = "",
        cooldown_seconds: Optional[float] = None,
        quota_exhausted_seconds: Optional[float] = None,
    ) -> None:
        with self._lock:
            snap = self.get_or_create(endpoint_id)
            snap.total_calls += 1
            snap.failed_calls += 1
            snap.consecutive_failures += 1
            snap.last_latency_ms = latency_ms
            snap.last_error_message = error_message
            snap.last_updated = time.time()

            if cooldown_seconds and cooldown_seconds > 0:
                snap.cooldown_until_monotonic = time.monotonic() + cooldown_seconds

            if quota_exhausted_seconds and quota_exhausted_seconds > 0:
                snap.quota_exhausted_until = time.time() + quota_exhausted_seconds

    def all_snapshots(self) -> Dict[str, EndpointHealthSnapshot]:
        with self._lock:
            return dict(self._snapshots)


DEFAULT_HEALTH_STORE = HealthTelemetryStore()
