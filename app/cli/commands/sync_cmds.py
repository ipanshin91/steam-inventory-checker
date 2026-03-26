from __future__ import annotations

import asyncio
import logging

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from app.core.context import AppContext
from app.core.models import InventoryVisibilityStatus, SyncErrorCategory, SyncStatus
from app.filters.aliases import expand_aliases
from app.filters.engine import apply_filter
from app.filters.parser import FilterParseError, parse_filter
from app.pricing.fetcher import PriceFetcher
from app.sync.orchestrator import SyncOrchestrator
from app.sync.result import SyncResult, SyncSummary
from app.sync.worker import _sum_value

logger = logging.getLogger(__name__)


async def cmd_sync(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Dispatch sync subcommands: one, all, filter."""
    if not args:
        console.print('[yellow]Usage: sync one <vanity> | sync all | sync filter <expr>[/yellow]')
        return

    subcommand = args[0].lower()

    if subcommand == 'one':
        await _sync_one(ctx, console, args[1:])
    elif subcommand == 'all':
        await _sync_all(ctx, console)
    elif subcommand == 'filter':
        await _sync_filter(ctx, console, args[1:])
    else:
        console.print(f'[red]Unknown sync subcommand: {subcommand!r}[/red]')
        console.print('[yellow]Usage: sync one <vanity> | sync all | sync filter <expr>[/yellow]')


async def _sync_one(ctx: AppContext, console: Console, args: list[str]) -> None:
    if not args:
        console.print('[yellow]Usage: sync one <vanity>[/yellow]')
        return
    vanity = args[0].lower()
    if ctx.db.get_account(vanity) is None:
        console.print(f'[red]Account not found: {vanity}[/red]')
        return

    console.print(f'Syncing [cyan]{vanity}[/cyan]...')
    orchestrator = SyncOrchestrator(ctx)
    try:
        result = await orchestrator.sync_one(vanity)
    except Exception as exc:
        console.print(f'[red]Sync error: {exc}[/red]')
        return

    _print_one_result(console, result)


async def _sync_all(ctx: AppContext, console: Console) -> None:
    total = ctx.index.total_count
    if total == 0:
        console.print('[yellow]No accounts to sync.[/yellow]')
        return

    answer = await asyncio.to_thread(
        input, f'Sync all {total} accounts? [y/N] '
    )
    if answer.strip().lower() != 'y':
        console.print('[dim]Cancelled.[/dim]')
        return

    orchestrator = SyncOrchestrator(ctx)
    summary = await orchestrator.sync_all()
    _print_summary(console, summary)


async def _sync_filter(ctx: AppContext, console: Console, args: list[str]) -> None:
    if not args:
        console.print('[yellow]Usage: sync filter <expr>[/yellow]')
        return
    expr = ' '.join(args)
    try:
        criteria = parse_filter(expr)
        criteria = expand_aliases(criteria, ctx.config.stale_threshold_hours)
    except FilterParseError as exc:
        console.print(f'[red]Filter error: {exc}[/red]')
        return

    matched = apply_filter(ctx.db.all_accounts(), criteria)
    count = len(matched)
    if count == 0:
        console.print('[yellow]No accounts match the filter.[/yellow]')
        return

    console.print(f'Found [yellow]{count}[/yellow] account(s) matching filter.')
    answer = await asyncio.to_thread(input, 'Continue? [y/N] ')
    if answer.strip().lower() != 'y':
        console.print('[dim]Cancelled.[/dim]')
        return

    orchestrator = SyncOrchestrator(ctx)
    _, summary = await orchestrator.sync_filter(criteria)
    _print_summary(console, summary)


async def cmd_reprice(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Fetch or refresh prices for already-synced accounts without re-fetching inventory."""
    if not ctx.config.pricing_enabled:
        console.print('[yellow]Pricing is disabled. Set pricing_enabled = true in config.toml.[/yellow]')
        return

    all_accounts = ctx.db.all_accounts()
    eligible = [
        a for a in all_accounts
        if a.inventory_visibility_status == InventoryVisibilityStatus.public and a.items
    ]

    if not eligible:
        console.print('[yellow]No accounts with public inventories and items to reprice.[/yellow]')
        return

    if args and args[0].lower() == 'one':
        if len(args) < 2:
            console.print('[yellow]Usage: reprice one <vanity>[/yellow]')
            return
        vanity = args[1].lower()
        eligible = [a for a in eligible if a.vanity_name == vanity]
        if not eligible:
            console.print(f'[red]Account not found or has no items: {vanity}[/red]')
            return

    console.print(f'Repricing [yellow]{len(eligible)}[/yellow] account(s)...')
    price_fetcher = PriceFetcher(ctx.http_client, ctx.config)
    semaphore = asyncio.Semaphore(ctx.config.global_concurrency)
    db_lock = asyncio.Lock()

    results: list[tuple[str, int, int, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        bar = progress.add_task('Repricing...', total=len(eligible))

        async def _reprice_one(acc) -> None:
            async with semaphore:
                entry = await ctx.proxy_manager.acquire()
                proxy_url: str | None = entry.url if hasattr(entry, 'url') else None
                fresh = 0
                item_errors: dict[str, str] = {}
                try:
                    fresh, item_errors = await price_fetcher.enrich_items(acc.items, proxy_url)
                    ctx.proxy_manager.release(entry, success=True)
                except Exception as exc:
                    ctx.proxy_manager.release(entry, success=False)
                    item_errors = {'_fetch': str(exc)}

                marketable_count = sum(1 for i in acc.items if i.marketable)
                acc_failed = len(item_errors)
                acc.total_inventory_value = _sum_value(acc.items)

                error_summary = '; '.join(
                    f'{name}: {reason}' for name, reason in item_errors.items()
                )

                async with db_lock:
                    ctx.db.update_account(acc)
                    results.append((acc.vanity_name, fresh, marketable_count, error_summary))
                    progress.advance(bar)

        await asyncio.gather(*[_reprice_one(a) for a in eligible], return_exceptions=True)

    ctx.index.rebuild(ctx.db.all_accounts())
    ctx.db.save()

    total_fresh = sum(r[1] for r in results)
    total_failed = sum(r[3] != '' for r in results)

    from rich.table import Table

    table = Table(show_header=True, header_style='bold', box=None)
    table.add_column('Vanity', style='cyan', no_wrap=True)
    table.add_column('Priced', justify='right')
    table.add_column('Total', justify='right')
    table.add_column('Status')
    table.add_column('Error', style='dim red')

    for vanity, fresh, total_m, error_msg in results:
        failed_count = len(error_msg.split('; ')) if error_msg else 0
        if failed_count == 0:
            status = '[green]OK[/green]'
        elif fresh > 0:
            status = '[yellow]PARTIAL[/yellow]'
        else:
            status = '[red]FAIL[/red]'
        table.add_row(vanity, str(fresh), str(total_m), status, error_msg)

    console.print(table)

    price_color = 'green' if total_failed == 0 else ('yellow' if total_fresh > 0 else 'red')
    console.print(
        f'Reprice complete — '
        f'[{price_color}]updated: {total_fresh}[/{price_color}]'
        f'  [dim]failed: {total_failed} accounts[/dim]'
    )


def _print_one_result(console: Console, result: SyncResult) -> None:
    if result.status == SyncStatus.success:
        icon = '[green]OK[/green]'
    elif result.status == SyncStatus.partial_success:
        icon = '[yellow]PARTIAL[/yellow]'
    else:
        icon = '[red]FAIL[/red]'

    line = (
        f'{icon}  [cyan]{result.vanity_name}[/cyan]'
        f'  {_fmt_duration(result.duration_ms)}'
        f'  items: {result.items_fetched}'
    )
    if result.error_category != SyncErrorCategory.none:
        line += f'  [dim]{result.error_category.value}[/dim]'
    if result.prices_fetched > 0 or result.prices_failed > 0:
        if result.prices_failed == 0:
            line += f'  [dim]prices: {result.prices_fetched}[/dim]'
        else:
            line += f'  [yellow]prices: {result.prices_fetched}/{result.prices_fetched + result.prices_failed}[/yellow]'
    console.print(line)

    if result.error_message:
        console.print(f'  [dim red]{result.error_message}[/dim red]')


def _print_summary(console: Console, summary: SyncSummary) -> None:
    lines = [
        f'total: [white]{summary.total}[/white]'
        f'   success: [green]{summary.success}[/green]'
        f'   partial: [yellow]{summary.partial_success}[/yellow]'
        f'   failed: [red]{summary.failed}[/red]',
        f'duration: {_fmt_duration(summary.duration_ms)}',
    ]
    if summary.errors_by_category:
        err_parts = [f'{k.value}={v}' for k, v in summary.errors_by_category.items()]
        lines.append('errors: ' + '  '.join(err_parts))

    total_marketable = summary.total_prices_fetched + summary.total_prices_failed
    if total_marketable > 0:
        if summary.total_prices_failed == 0:
            lines.append(f'prices: [green]{summary.total_prices_fetched}/{total_marketable}[/green]')
        else:
            lines.append(
                f'prices: [yellow]{summary.total_prices_fetched}/{total_marketable}[/yellow]'
                f'  [dim red]({summary.total_prices_failed} not priced)[/dim red]'
            )

    border = 'green' if summary.failed == 0 else ('yellow' if summary.success > 0 else 'red')
    console.print(Panel('\n'.join(lines), title='Sync complete', border_style=border))

    if summary.failed_results:
        for r in summary.failed_results:
            _print_one_result(console, r)


def _fmt_duration(ms: int) -> str:
    """Format milliseconds as a human-readable duration string."""
    total_s = ms // 1000
    minutes = total_s // 60
    seconds = total_s % 60
    if minutes > 0:
        return f'{minutes}m {seconds}s'
    if total_s > 0:
        return f'{seconds}s'
    return f'{ms}ms'
