from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

import aiohttp

from app.core.config import AppConfig
from app.proxy.circuit_breaker import CircuitBreaker, CircuitState
from app.proxy.stats import ProxyStats
from app.steam.exceptions import RateLimitError

logger = logging.getLogger(__name__)

T = TypeVar('T')


class NoHealthyProxyError(Exception):
    """Raised when the proxy pool has no alive proxy with a closed circuit."""


class MaxRetriesExceeded(Exception):
    """Raised when all retry attempts for a request have been exhausted."""


@dataclass
class ProxyEntry:
    """Single proxy with its own semaphore, circuit breaker, stats, and per-request delay."""

    url: str
    delay: float
    semaphore: asyncio.Semaphore
    circuit: CircuitBreaker
    stats: ProxyStats
    active_connections: int = 0
    is_alive: bool = True


@dataclass
class DirectEntry:
    """Fallback when no proxies are configured."""

    proxy_url: None = None
    delay: float = 1.5


class ProxyManager:
    """Manages a pool of proxies with least-connections selection and circuit breaking."""

    def __init__(self, config: AppConfig) -> None:
        self._lock = asyncio.Lock()
        if not config.proxies:
            self._direct_mode = True
            self._direct = DirectEntry(delay=config.no_proxy_delay)
            self._pool: list[ProxyEntry] = []
        else:
            self._direct_mode = False
            self._pool = [
                ProxyEntry(
                    url=url,
                    delay=config.proxy_request_delay,
                    semaphore=asyncio.Semaphore(config.proxy_concurrency),
                    circuit=CircuitBreaker(),
                    stats=ProxyStats(),
                )
                for url in config.proxies
            ]

    @property
    def is_direct_mode(self) -> bool:
        """True when operating without a proxy pool."""
        return self._direct_mode

    async def acquire(self) -> ProxyEntry | DirectEntry:
        """Return the best available proxy entry or the direct entry."""
        if self._direct_mode:
            return self._direct
        return await self._acquire_from_pool()

    async def _acquire_from_pool(self) -> ProxyEntry:
        async with self._lock:
            candidates = [
                p for p in self._pool
                if p.is_alive and p.circuit.state == CircuitState.CLOSED
            ]
            if not candidates:
                candidates = [
                    p for p in self._pool
                    if p.is_alive and p.circuit.state == CircuitState.HALF_OPEN
                ]
            if not candidates:
                raise NoHealthyProxyError('No healthy proxies available in the pool')
            proxy = min(candidates, key=lambda p: p.active_connections)
            proxy.active_connections += 1
        return proxy

    def release(
        self,
        entry: ProxyEntry | DirectEntry,
        *,
        success: bool,
        latency_ms: float = 0.0,
    ) -> None:
        """Update stats and circuit state after a request completes."""
        if isinstance(entry, DirectEntry):
            return
        entry.active_connections = max(0, entry.active_connections - 1)
        if success:
            entry.circuit.record_success()
            entry.stats.record_success(latency_ms)
        else:
            entry.circuit.record_failure()
            entry.stats.record_failure()

    def all_proxies(self) -> list[ProxyEntry]:
        """Return all proxy entries for health checking."""
        return list(self._pool)

    def proxy_summary(self) -> list[dict]:
        """Return per-proxy statistics for display."""
        return [
            {
                'url': p.url,
                'alive': p.is_alive,
                'circuit': p.circuit.state.value,
                'ok': p.stats.success_count,
                'fail': p.stats.fail_count,
                'avg_ms': round(p.stats.avg_latency_ms, 1),
                'active': p.active_connections,
            }
            for p in self._pool
        ]


async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    retries: int,
    backoff_base: float,
    jitter: float,
) -> T:
    """Execute coro_factory with exponential backoff retry on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return await coro_factory()
        except (RateLimitError, aiohttp.ClientError) as exc:
            last_exc = exc
            delay = backoff_base * (2 ** attempt) + random.uniform(0, jitter)
            logger.warning(
                f'Retry {attempt + 1}/{retries} in {delay:.1f}s ({type(exc).__name__})'
            )
            await asyncio.sleep(delay)
    raise MaxRetriesExceeded(f'Max retries ({retries}) exceeded') from last_exc
