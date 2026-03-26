from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp

from app.steam.exceptions import RateLimitError

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
    error: str = ''


class PriceFetcher:
    """Fetches CS2 item prices from the Steam Market API with per-item request deduplication."""

    def __init__(self, client: SteamHttpClient, config: AppConfig) -> None:
        self._client = client
        self._currency = config.pricing_currency
        self._currency_code = _CURRENCY_CODES.get(config.pricing_currency, str(config.pricing_currency))
        self._request_delay = config.request_delay
        self._cache: dict[str, PriceData] = {}
        self._item_locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    async def enrich_items(
        self, items: list[Item], proxy: str | None = None
    ) -> tuple[int, dict[str, str]]:
        """Fetch prices sequentially.

        Returns (fresh_count, errors) where fresh_count is the number of items
        that received a new price in this call, and errors maps market_hash_name
        to a failure reason for items that could not be priced.
        """
        fresh = 0
        errors: dict[str, str] = {}
        first = True
        for item in items:
            if not item.marketable:
                continue
            if not first:
                await asyncio.sleep(self._request_delay)
            first = False
            updated, err = await self._enrich_one(item, proxy)
            if updated:
                fresh += 1
            elif err:
                errors[item.market_hash_name] = err
        return fresh, errors

    async def _enrich_one(self, item: Item, proxy: str | None) -> tuple[bool, str]:
        """Update item price in-place.

        Returns (updated, error): updated=True means a fresh price was received,
        error is non-empty when the fetch failed.
        """
        data = await self._get_price(item.market_hash_name, proxy)
        if data.price is not None:
            item.price = data.price
            item.price_updated_at = data.updated_at
            item.currency = data.currency
            return True, ''
        return False, data.error

    async def _get_price(self, name: str, proxy: str | None) -> PriceData:
        async with self._meta_lock:
            if name not in self._item_locks:
                self._item_locks[name] = asyncio.Lock()
            lock = self._item_locks[name]

        async with lock:
            if name in self._cache:
                return self._cache[name]
            data = await self._fetch(name, proxy)
            if data.price is not None:
                self._cache[name] = data
            return data

    async def _fetch(self, name: str, proxy: str | None) -> PriceData:
        """Fetch price with retry on rate limit. Only successful prices are cached by the caller."""
        url = _PRICE_URL.format(
            currency=self._currency,
            name=urllib.parse.quote(name),
        )
        now = datetime.now(timezone.utc)
        last_error = 'unknown'

        try:
            resp = await self._client.get_json(url, proxy=proxy)
            if resp.get('success'):
                raw = resp.get('median_price') or resp.get('lowest_price')
                price = _parse_price(raw)
                if price is not None:
                    logger.info('Price fetched for %r: %s %s', name, price, self._currency_code)
                    return PriceData(price=price, currency=self._currency_code, updated_at=now)
                last_error = f'unparseable price: {raw!r}'
                logger.warning('Unparseable price for %r: %r', name, raw)
            else:
                last_error = 'no_listing'
                logger.debug('No market listing for %r', name)
        except RateLimitError:
            last_error = 'rate_limited'
            logger.warning('Rate limited fetching price for %r', name)
        except aiohttp.ClientResponseError as exc:
            if exc.status == 429:
                last_error = 'rate_limited'
                logger.warning('Rate limited fetching price for %r', name)
            else:
                last_error = f'HTTP {exc.status}'
                logger.warning('HTTP %d fetching price for %r', exc.status, name)
        except Exception as exc:
            last_error = str(exc) or type(exc).__name__
            logger.warning('Price fetch failed for %r: %s', name, exc)

        return PriceData(price=None, currency=None, updated_at=now, error=last_error)


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
