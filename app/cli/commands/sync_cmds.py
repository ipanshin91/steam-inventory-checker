from __future__ import annotations

import asyncio
import logging

from rich.console import Console
from rich.panel import Panel

from app.core.context import AppContext
from app.core.models import SyncErrorCategory, SyncStatus
from app.filters.aliases import expand_aliases
from app.filters.engine import apply_filter, preview_count
from app.filters.parser import FilterParseError, parse_filter
from app.sync.orchestrator import SyncOrchestrator
from app.sync.result import SyncResult, SyncSummary

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


def _print_one_result(console: Console, result: SyncResult) -> None:
    if result.status == SyncStatus.success:
        icon = '[green]OK[/green]'
    elif result.status == SyncStatus.partial_success:
        icon = '[yellow]PARTIAL[/yellow]'
    else:
        icon = '[red]FAIL[/red]'

    line = (
        f'{icon}  [cyan]{result.vanity_name}[/cyan]'
        f'  {result.duration_ms}ms'
        f'  items: {result.items_fetched}'
    )
    if result.error_category != SyncErrorCategory.none:
        line += f'  [dim]{result.error_category.value}[/dim]'
    console.print(line)

    if result.error_message:
        console.print(f'  [dim red]{result.error_message}[/dim red]')


def _print_summary(console: Console, summary: SyncSummary) -> None:
    lines = [
        f'total: [white]{summary.total}[/white]'
        f'   success: [green]{summary.success}[/green]'
        f'   partial: [yellow]{summary.partial_success}[/yellow]'
        f'   failed: [red]{summary.failed}[/red]',
        f'duration: {summary.duration_ms}ms',
    ]
    if summary.errors_by_category:
        err_parts = [f'{k.value}={v}' for k, v in summary.errors_by_category.items()]
        lines.append('errors: ' + '  '.join(err_parts))

    border = 'green' if summary.failed == 0 else ('yellow' if summary.success > 0 else 'red')
    console.print(Panel('\n'.join(lines), title='Sync complete', border_style=border))

    if summary.failed_results:
        for r in summary.failed_results:
            _print_one_result(console, r)
