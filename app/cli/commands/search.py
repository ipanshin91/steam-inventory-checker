from __future__ import annotations

import logging

from rich.console import Console

from app.cli.display import print_accounts_table, print_find_results
from app.core.context import AppContext
from app.filters.aliases import expand_aliases
from app.filters.criteria import SortSpec
from app.filters.engine import apply_filter, apply_sort
from app.filters.parser import FilterParseError, parse_filter

logger = logging.getLogger(__name__)

_SORT_FIELDS = (
    'items_count_total',
    'items_count_distinct',
    'last_successful_sync_at',
    'sync_status',
    'total_value',
)


async def cmd_find(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Search items by display_name or market_hash_name (partial match, offline)."""
    if not args:
        console.print('[yellow]Usage: find <query>[/yellow]')
        return

    query = ' '.join(args).lower()
    results = []

    for account in ctx.db.all_accounts():
        for item in account.items:
            if query in item.display_name.lower() or query in item.market_hash_name.lower():
                results.append((account, item))

    if not results:
        console.print(f'No items matching [cyan]{query!r}[/cyan] found.')
        return

    print_find_results(console, results)


async def cmd_filter(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Filter accounts by an expression and display results (offline)."""
    if not args:
        console.print('[yellow]Usage: filter <expr>[/yellow]')
        console.print('[dim]Example: filter "sync_status=failed, account_exists_status=exists"[/dim]')
        return

    expr = ' '.join(args)
    try:
        criteria = parse_filter(expr)
        criteria = expand_aliases(criteria, ctx.config.stale_threshold_hours)
    except FilterParseError as exc:
        console.print(f'[red]Filter error: {exc}[/red]')
        return

    accounts = apply_filter(ctx.db.all_accounts(), criteria)

    if not accounts:
        console.print('[dim]No accounts matched.[/dim]')
        return

    print_accounts_table(console, accounts)
    console.print(f'  [dim]{len(accounts)} account(s) matched[/dim]')


async def cmd_sort(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Sort all accounts by a field and display results (offline)."""
    if not args:
        console.print('[yellow]Usage: sort <field> [asc|desc][/yellow]')
        console.print(f'[dim]Fields: {", ".join(_SORT_FIELDS)}[/dim]')
        return

    field = args[0]
    direction = args[1].lower() if len(args) > 1 else 'desc'

    if field not in _SORT_FIELDS:
        console.print(f'[red]Unknown field: {field!r}. Valid: {list(_SORT_FIELDS)}[/red]')
        return

    if direction not in ('asc', 'desc'):
        console.print(f'[red]Invalid direction: {direction!r}. Use asc or desc.[/red]')
        return

    spec = SortSpec(field=field, direction=direction)  # type: ignore[arg-type]
    accounts = apply_sort(ctx.db.all_accounts(), spec)

    if not accounts:
        console.print('[dim]No accounts.[/dim]')
        return

    print_accounts_table(console, accounts)
    console.print(f'  [dim]{len(accounts)} account(s) sorted by {field} {direction}[/dim]')
