from __future__ import annotations

import logging

from rich.console import Console

from app.core.context import AppContext
from app.filters.aliases import expand_aliases
from app.filters.engine import preview_count
from app.filters.parser import FilterParseError, parse_filter

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
    console.print('[dim]Sync not available — Stages 4–6 pending.[/dim]')


async def _sync_all(ctx: AppContext, console: Console) -> None:
    total = ctx.index.total_count
    if total == 0:
        console.print('[yellow]No accounts to sync.[/yellow]')
        return
    console.print(f'[dim]Sync not available — Stages 4–6 pending. ({total} accounts queued)[/dim]')


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
    count = preview_count(ctx.db.all_accounts(), criteria)
    console.print(
        f'[dim]Found {count} account(s) matching filter. '
        f'Sync not available — Stages 4–6 pending.[/dim]'
    )
