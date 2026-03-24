from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.proxy.manager import ProxyManager
    from app.steam.client import SteamHttpClient

logger = logging.getLogger(__name__)

_HEALTH_CHECK_URL = 'https://steamcommunity.com/'


class ProxyHealthChecker:
    """Background task that periodically probes every proxy in the pool."""

    def __init__(
        self,
        manager: ProxyManager,
        client: SteamHttpClient,
        interval: float = 60.0,
    ) -> None:
        self._manager = manager
        self._client = client
        self._interval = interval

    def start(self) -> asyncio.Task:
        """Schedule the health-check loop as a background asyncio task."""
        proxies = self._manager.all_proxies()
        if not proxies:
            loop = asyncio.get_event_loop()
            task = loop.create_task(asyncio.sleep(0))
            return task
        return asyncio.create_task(self._run(), name='proxy-health-checker')

    async def _run(self) -> None:
        """Probe all proxies in a loop, sleeping between passes."""
        while True:
            await self._check_all()
            await asyncio.sleep(self._interval)

    async def _check_all(self) -> None:
        tasks = [
            asyncio.create_task(self._check_one(proxy))
            for proxy in self._manager.all_proxies()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_one(self, proxy) -> None:
        try:
            await self._client.get_text(_HEALTH_CHECK_URL, proxy=proxy.url)
            if not proxy.is_alive:
                logger.info(f'Proxy {proxy.url} is back online')
            proxy.is_alive = True
        except Exception:
            proxy.is_alive = False
            logger.warning(f'Proxy {proxy.url} is unreachable')
