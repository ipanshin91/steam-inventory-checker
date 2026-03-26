from __future__ import annotations

import time
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


class CircuitBreaker:
    """Per-proxy circuit breaker: CLOSED → OPEN after failures → HALF_OPEN after cooldown → CLOSED on success."""

    def __init__(self, failure_threshold: int = 5, cooldown_secs: float = 300.0) -> None:
        self._state = CircuitState.CLOSED
        self._failure_threshold = failure_threshold
        self._cooldown_secs = cooldown_secs
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        """Return current state, auto-transitioning OPEN → HALF_OPEN after cooldown."""
        if (
            self._state == CircuitState.OPEN
            and self._opened_at is not None
            and time.monotonic() - self._opened_at >= self._cooldown_secs
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        """Reset failure counter and close the circuit."""
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        """Increment failure counter; open the circuit when threshold is reached."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()

    def trip(self) -> None:
        """Immediately open the circuit regardless of failure threshold (e.g. on rate limit)."""
        self._consecutive_failures = self._failure_threshold
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
