from __future__ import annotations

import logging
from dataclasses import dataclass, field

import aiohttp

from app.core.models import InventoryVisibilityStatus
from app.steam.client import SteamHttpClient
from app.steam.exceptions import RateLimitError, SourceError

logger = logging.getLogger(__name__)

_BASE_URL = 'https://steamcommunity.com/inventory/{steam_id64}/730/2?l=english&count=5000'
_PAGE_URL = _BASE_URL + '&start_assetid={start_assetid}'


@dataclass
class InventoryData:
    """Raw inventory response ready for normalisation."""

    visibility: InventoryVisibilityStatus
    raw_assets: list[dict] = field(default_factory=list)
    raw_descriptions: list[dict] = field(default_factory=list)


class InventoryFetcher:
    """Fetches CS2 inventory from the Steam community endpoint. Handles pagination."""

    def __init__(self, client: SteamHttpClient) -> None:
        self._client = client

    async def fetch(self, steam_id64: str, proxy: str | None = None) -> InventoryData:
        """Fetch the full CS2 inventory for the given steam_id64."""
        all_assets: list[dict] = []
        desc_map: dict[str, dict] = {}
        start_assetid: str | None = None

        while True:
            url = (
                _PAGE_URL.format(steam_id64=steam_id64, start_assetid=start_assetid)
                if start_assetid
                else _BASE_URL.format(steam_id64=steam_id64)
            )
            logger.debug(f'Fetching inventory page: {url}')

            try:
                data = await self._client.get_json(url, proxy=proxy)
            except aiohttp.ClientResponseError as exc:
                if exc.status == 403:
                    logger.debug(f'Inventory private for {steam_id64} (HTTP 403)')
                    return InventoryData(visibility=InventoryVisibilityStatus.private)
                if exc.status == 429:
                    raise RateLimitError(
                        f'Rate limited fetching inventory for {steam_id64}'
                    ) from exc
                raise SourceError(
                    f'HTTP {exc.status} fetching inventory for {steam_id64}'
                ) from exc

            if not data.get('success', 0):
                raise SourceError(f'Steam returned success=0 for inventory of {steam_id64}')

            all_assets.extend(data.get('assets', []))

            for desc in data.get('descriptions', []):
                desc_map.setdefault(desc['classid'], desc)

            if data.get('more_items'):
                start_assetid = data.get('last_assetid')
                logger.debug(f'Inventory has more pages, next start_assetid={start_assetid}')
            else:
                break

        logger.debug(
            f'Inventory fetched for {steam_id64}: '
            f'{len(all_assets)} assets, {len(desc_map)} description types'
        )
        return InventoryData(
            visibility=InventoryVisibilityStatus.public,
            raw_assets=all_assets,
            raw_descriptions=list(desc_map.values()),
        )
