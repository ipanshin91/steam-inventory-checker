from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProxyStats:
    """Per-proxy request counters."""

    success_count: int = 0
    fail_count: int = 0
    total_requests: int = 0
    total_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        """Average latency across all recorded requests."""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    def record_success(self, latency_ms: float) -> None:
        """Record a successful request with its measured latency."""
        self.success_count += 1
        self.total_requests += 1
        self.total_latency_ms += latency_ms

    def record_failure(self) -> None:
        """Record a failed request."""
        self.fail_count += 1
        self.total_requests += 1
