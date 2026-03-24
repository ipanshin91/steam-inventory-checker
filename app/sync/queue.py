from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.core.config import AppConfig
from app.core.database import JsonDatabase
from app.core.models import Account
from app.proxy.manager import ProxyManager
from app.steam.client import SteamHttpClient
from app.sync.result import SyncResult
from app.sync.worker import AccountSyncWorker

logger = logging.getLogger(__name__)


class AsyncTaskQueue:
    """Runs account sync tasks concurrently with a semaphore and periodic autosave."""

    def __init__(
        self,
        concurrency: int,
        db: JsonDatabase,
        config: AppConfig,
        client: SteamHttpClient,
        proxy_manager: ProxyManager,
        on_progress: Callable[[], None] | None = None,
    ) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._db = db
        self._config = config
        self._client = client
        self._proxy_manager = proxy_manager
        self._on_progress = on_progress
        self._completed = 0
        self._lock = asyncio.Lock()

    async def run(self, accounts: list[Account]) -> list[SyncResult | BaseException]:
        """Deduplicate accounts and run all sync tasks, returning results in completion order."""
        seen: set[str] = set()
        deduped: list[Account] = []
        for acc in accounts:
            if acc.vanity_name not in seen:
                seen.add(acc.vanity_name)
                deduped.append(acc)

        tasks = [asyncio.create_task(self._run_one(acc)) for acc in deduped]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_one(self, account: Account) -> SyncResult:
        async with self._semaphore:
            worker = AccountSyncWorker(
                account=account,
                client=self._client,
                proxy_manager=self._proxy_manager,
                config=self._config,
            )
            result = await worker.run()
            self._db.update_account(result.updated_account)

            async with self._lock:
                self._completed += 1
                if self._completed % self._config.autosave_interval == 0:
                    self._db.save()
                    logger.info(f'Autosave after {self._completed} accounts synced')

            if self._on_progress is not None:
                self._on_progress()

            return result
