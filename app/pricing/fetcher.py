from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.core.models import Item
    from app.steam.client import SteamHttpClient

logger = logging.getLogger(__name__)

_PRICE_URL = (
    'https://steamcommunity.com/market/priceoverview/'
    '?appid=730&currency={currency}&market_hash_name={name}'
)

_CURRENCY_CODES: dict[int, str] = {
    1: 'USD', 3: 'EUR', 5: 'RUB', 6: 'PLN', 7: 'BRL',
    8: 'JPY', 17: 'TRY', 18: 'UAH', 23: 'CNY', 37: 'ARS', 40: 'KZT',
}


@dataclass
class PriceData:
    """Fetched price for a single market item."""

    price: float | None
    currency: str | None
    updated_at: datetime


class PriceFetcher:
    """Fetches CS2 item prices from the Steam Market API with per-item request deduplication."""

    def __init__(self, client: SteamHttpClient, config: AppConfig) -> None:
        self._client = client
        self._currency = config.pricing_currency
        self._currency_code = _CURRENCY_CODES.get(config.pricing_currency, str(config.pricing_currency))
        self._cache: dict[str, PriceData] = {}
        self._item_locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    async def enrich_items(self, items: list[Item], proxy: str | None = None) -> None:
        """Fetch prices for marketable items and update their price fields in-place."""
        tasks = [
            asyncio.create_task(self._enrich_one(item, proxy))
            for item in items
            if item.marketable
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _enrich_one(self, item: Item, proxy: str | None) -> None:
        data = await self._get_price(item.market_hash_name, proxy)
        item.price = data.price
        item.price_updated_at = data.updated_at
        item.currency = data.currency

    async def _get_price(self, name: str, proxy: str | None) -> PriceData:
        async with self._meta_lock:
            if name not in self._item_locks:
                self._item_locks[name] = asyncio.Lock()
            lock = self._item_locks[name]

        async with lock:
            if name in self._cache:
                return self._cache[name]
            data = await self._fetch(name, proxy)
            self._cache[name] = data
            return data

    async def _fetch(self, name: str, proxy: str | None) -> PriceData:
        url = _PRICE_URL.format(
            currency=self._currency,
            name=urllib.parse.quote(name),
        )
        now = datetime.now(timezone.utc)
        try:
            resp = await self._client.get_json(url, proxy=proxy)
            if resp.get('success'):
                raw = resp.get('median_price') or resp.get('lowest_price')
                price = _parse_price(raw)
                logger.debug('Price for %r: %s %s', name, price, self._currency_code)
                return PriceData(price=price, currency=self._currency_code, updated_at=now)
        except Exception as exc:
            logger.warning('Price fetch failed for %r: %s', name, exc)
        return PriceData(price=None, currency=None, updated_at=now)


def _parse_price(raw: str | None) -> float | None:
    """Extract a float value from a Steam Market price string (e.g. '$0.03', '0,03€')."""
    if not raw:
        return None
    digits = re.sub(r'[^\d.,]', '', raw)
    # Treat trailing comma+1-2 digits as decimal separator (European format: "0,03")
    digits = re.sub(r',(\d{1,2})$', r'.\1', digits)
    # Remove remaining commas (thousands separators)
    digits = digits.replace(',', '')
    try:
        return float(digits) if digits else None
    except ValueError:
        return None
