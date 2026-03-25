from __future__ import annotations

import logging

import aiohttp
from fake_useragent import UserAgent

from app.core.config import AppConfig

logger = logging.getLogger(__name__)


class SteamHttpClient:
    """Single aiohttp session for the application lifetime. Create once in async_main, close on shutdown."""

    def __init__(self, config: AppConfig) -> None:
        ua = UserAgent()
        connector = aiohttp.TCPConnector(limit=config.global_concurrency)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=config.request_timeout),
            headers={
                'User-Agent': ua.random,
                'Referer': 'https://steamcommunity.com/',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-US,en;q=0.9',
            },
        )
        logger.info('HTTP client session created (concurrency limit=%d)', config.global_concurrency)

    async def get_text(self, url: str, proxy: str | None = None) -> str:
        """Fetch URL and return response body as UTF-8 text."""
        async with self._session.get(url, proxy=proxy) as resp:
            resp.raise_for_status()
            return await resp.text(encoding='utf-8')

    async def get_json(self, url: str, proxy: str | None = None) -> dict:
        """Fetch URL and return parsed JSON body."""
        async with self._session.get(url, proxy=proxy) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        await self._session.close()
        logger.info('HTTP client session closed')
