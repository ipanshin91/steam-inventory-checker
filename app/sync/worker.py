from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import aiohttp

from app.core.config import AppConfig
from app.core.models import Account, InventoryVisibilityStatus, SyncErrorCategory, SyncStatus
from app.pricing.fetcher import PriceFetcher
from app.proxy.manager import MaxRetriesExceeded, NoHealthyProxyError, ProxyManager, with_retry
from app.steam.client import SteamHttpClient
from app.steam.exceptions import ParseError, RateLimitError, SourceError
from app.steam.inventory import InventoryFetcher
from app.steam.normalizer import count_items, normalize
from app.steam.profile_xml import ProfileXmlFetcher
from app.sync.result import SyncResult

logger = logging.getLogger(__name__)


class AccountSyncWorker:
    """Executes the full sync cycle for a single Steam account."""

    def __init__(
        self,
        account: Account,
        client: SteamHttpClient,
        proxy_manager: ProxyManager,
        config: AppConfig,
        price_fetcher: PriceFetcher | None = None,
    ) -> None:
        self._account = account
        self._proxy_manager = proxy_manager
        self._config = config
        self._price_fetcher = price_fetcher
        self._profile_fetcher = ProfileXmlFetcher(client)
        self._inventory_fetcher = InventoryFetcher(client)

    async def run(self) -> SyncResult:
        """Run the complete sync pipeline and return the result."""
        start = time.monotonic()
        acc = self._account.model_copy(deep=True)
        now = datetime.now(timezone.utc)
        acc.last_sync_attempt_at = now

        try:
            entry = await self._proxy_manager.acquire()
        except NoHealthyProxyError:
            acc.sync_status = SyncStatus.failed
            acc.sync_error_category = SyncErrorCategory.proxy_failure
            logger.warning('No healthy proxy for %s', acc.vanity_name)
            return SyncResult(
                vanity_name=acc.vanity_name,
                status=acc.sync_status,
                error_category=acc.sync_error_category,
                duration_ms=_elapsed_ms(start),
                updated_account=acc,
            )

        proxy_url: str | None = entry.url if hasattr(entry, 'url') else None
        await asyncio.sleep(entry.delay)

        profile_ok = False
        try:
            profile = await with_retry(
                lambda: self._profile_fetcher.fetch(acc.vanity_name, proxy_url),
                retries=self._config.retry_count,
                backoff_base=self._config.backoff_base,
                jitter=self._config.backoff_jitter,
            )
            profile_ok = True

            acc.steam_id64 = profile.steam_id64
            acc.display_name = profile.display_name
            acc.profile_url = profile.profile_url
            acc.account_exists_status = profile.exists_status
            acc.account_ban_status = profile.ban_status

            if profile.exists_status == 'not_found':
                acc.sync_status = SyncStatus.failed
                acc.sync_error_category = SyncErrorCategory.profile_not_found
                self._proxy_manager.release(entry, success=True, latency_ms=_elapsed_ms(start))
                return SyncResult(
                    vanity_name=acc.vanity_name,
                    status=acc.sync_status,
                    error_category=acc.sync_error_category,
                    duration_ms=_elapsed_ms(start),
                    updated_account=acc,
                )

            if not profile.profile_is_public or not profile.steam_id64:
                acc.inventory_visibility_status = InventoryVisibilityStatus.private
                acc.sync_status = SyncStatus.success
                acc.sync_error_category = SyncErrorCategory.none
                acc.last_successful_sync_at = now
                self._proxy_manager.release(entry, success=True, latency_ms=_elapsed_ms(start))
                return SyncResult(
                    vanity_name=acc.vanity_name,
                    status=acc.sync_status,
                    error_category=acc.sync_error_category,
                    duration_ms=_elapsed_ms(start),
                    updated_account=acc,
                )

            steam_id64 = profile.steam_id64
            inv = await with_retry(
                lambda: self._inventory_fetcher.fetch(steam_id64, proxy_url),
                retries=self._config.retry_count,
                backoff_base=self._config.backoff_base,
                jitter=self._config.backoff_jitter,
            )

            acc.inventory_visibility_status = inv.visibility
            if inv.visibility == InventoryVisibilityStatus.public:
                items = normalize(inv)
                if self._price_fetcher is not None and items:
                    await self._price_fetcher.enrich_items(items, proxy_url)
                total, distinct, marketable, tradable = count_items(items)
                acc.items = items
                acc.items_count_total = total
                acc.items_count_distinct = distinct
                acc.marketable_items_count = marketable
                acc.tradable_items_count = tradable
                acc.total_inventory_value = _sum_value(items)
            else:
                acc.items = []
                acc.items_count_total = 0
                acc.items_count_distinct = 0
                acc.marketable_items_count = 0
                acc.tradable_items_count = 0
                acc.total_inventory_value = None

            acc.sync_status = SyncStatus.success
            acc.sync_error_category = SyncErrorCategory.none
            acc.last_successful_sync_at = now
            self._proxy_manager.release(entry, success=True, latency_ms=_elapsed_ms(start))
            return SyncResult(
                vanity_name=acc.vanity_name,
                status=acc.sync_status,
                error_category=acc.sync_error_category,
                items_fetched=acc.items_count_total,
                duration_ms=_elapsed_ms(start),
                updated_account=acc,
            )

        except Exception as exc:
            error_category = _classify_error(exc)
            acc.sync_status = SyncStatus.partial_success if profile_ok else SyncStatus.failed
            acc.sync_error_category = error_category
            error_message = _format_exc(exc)
            logger.warning(
                f'Sync error for {acc.vanity_name}: {type(exc).__name__} ({error_category.value}) — {error_message}'
            )
            self._proxy_manager.release(entry, success=False, latency_ms=_elapsed_ms(start))
            return SyncResult(
                vanity_name=acc.vanity_name,
                status=acc.sync_status,
                error_category=acc.sync_error_category,
                error_message=error_message,
                duration_ms=_elapsed_ms(start),
                updated_account=acc,
            )


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _sum_value(items: list) -> float | None:
    """Return total inventory value or None if no prices are available."""
    total = sum(
        item.price * item.quantity
        for item in items
        if item.price is not None
    )
    return round(total, 2) if any(item.price is not None for item in items) else None


def _format_exc(exc: Exception) -> str:
    """Return a concise human-readable exception message, including cause if present."""
    msg = str(exc) or type(exc).__name__
    if exc.__cause__ is not None:
        cause = str(exc.__cause__) or type(exc.__cause__).__name__
        return f'{msg} (caused by {type(exc.__cause__).__name__}: {cause})'
    return msg


def _classify_error(exc: Exception) -> SyncErrorCategory:
    if isinstance(exc, RateLimitError):
        return SyncErrorCategory.source_rate_limited
    if isinstance(exc, ParseError):
        return SyncErrorCategory.parse_failure
    if isinstance(exc, SourceError):
        return SyncErrorCategory.source_temporary_failure
    if isinstance(exc, (aiohttp.ClientError, MaxRetriesExceeded)):
        return SyncErrorCategory.source_temporary_failure
    if isinstance(exc, NoHealthyProxyError):
        return SyncErrorCategory.proxy_failure
    return SyncErrorCategory.internal_error
