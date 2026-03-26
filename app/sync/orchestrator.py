from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TimeRemainingColumn

from app.core.models import Account, SyncErrorCategory, SyncStatus
from app.filters.criteria import FilterCriteria
from app.filters.engine import apply_filter
from app.sync.queue import AsyncTaskQueue
from app.sync.result import SyncResult, SyncSummary
from app.sync.worker import AccountSyncWorker

if TYPE_CHECKING:
    from app.core.context import AppContext

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    """High-level coordinator for sync_one / sync_all / sync_filter operations."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    async def sync_one(self, vanity: str) -> SyncResult:
        """Sync a single account by vanity name and persist the result."""
        account = self._ctx.db.get_account(vanity)
        if account is None:
            raise ValueError(f'Account not found: {vanity!r}')

        worker = AccountSyncWorker(
            account=account,
            client=self._ctx.http_client,
            proxy_manager=self._ctx.proxy_manager,
            config=self._ctx.config,
        )
        result = await worker.run()
        self._ctx.db.update_account(result.updated_account)
        self._ctx.index.rebuild(self._ctx.db.all_accounts())
        if self._ctx.config.autosave:
            self._ctx.db.save()
        return result

    async def sync_all(self) -> SyncSummary:
        """Sync every account in the database."""
        accounts = self._ctx.db.all_accounts()
        return await self._run_batch(accounts)

    async def sync_filter(self, criteria: FilterCriteria) -> tuple[int, SyncSummary]:
        """Filter accounts and sync the matching subset. Returns (matched_count, summary)."""
        accounts = apply_filter(self._ctx.db.all_accounts(), criteria)
        summary = await self._run_batch(accounts)
        return len(accounts), summary

    async def _run_batch(self, accounts: list[Account]) -> SyncSummary:
        """Run a batch sync with a rich progress bar, autosave, and index rebuild."""
        if not accounts:
            return SyncSummary(
                total=0,
                success=0,
                partial_success=0,
                failed=0,
                skipped=0,
                duration_ms=0,
                errors_by_category={},
            )

        start = time.monotonic()

        with Progress(
            SpinnerColumn(),
            '[progress.description]{task.description}',
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            prog_task = progress.add_task(
                f'Syncing {len(accounts)} account(s)...', total=len(accounts)
            )
            queue = AsyncTaskQueue(
                concurrency=self._ctx.config.global_concurrency,
                db=self._ctx.db,
                config=self._ctx.config,
                client=self._ctx.http_client,
                proxy_manager=self._ctx.proxy_manager,
                on_progress=lambda: progress.advance(prog_task),
            )
            raw_results = await queue.run(accounts)

        self._ctx.index.rebuild(self._ctx.db.all_accounts())
        self._ctx.db.save()

        return _build_summary(raw_results, int((time.monotonic() - start) * 1000))


def _build_summary(
    raw_results: list[SyncResult | BaseException],
    duration_ms: int,
) -> SyncSummary:
    success = 0
    partial = 0
    failed = 0
    prices_fetched = 0
    prices_failed = 0
    errors: dict[SyncErrorCategory, int] = {}
    failed_results: list[SyncResult] = []

    for r in raw_results:
        if isinstance(r, BaseException):
            failed += 1
            errors[SyncErrorCategory.internal_error] = (
                errors.get(SyncErrorCategory.internal_error, 0) + 1
            )
            logger.error('Unhandled exception in sync task: %s', type(r).__name__)
            continue
        if r.status == SyncStatus.success:
            success += 1
        elif r.status == SyncStatus.partial_success:
            partial += 1
            failed_results.append(r)
        else:
            failed += 1
            failed_results.append(r)
        if r.error_category != SyncErrorCategory.none:
            errors[r.error_category] = errors.get(r.error_category, 0) + 1
        prices_fetched += r.prices_fetched
        prices_failed += r.prices_failed

    return SyncSummary(
        total=len(raw_results),
        success=success,
        partial_success=partial,
        failed=failed,
        skipped=0,
        duration_ms=duration_ms,
        errors_by_category=errors,
        failed_results=failed_results,
        total_prices_fetched=prices_fetched,
        total_prices_failed=prices_failed,
    )
