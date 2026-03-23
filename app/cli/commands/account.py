from __future__ import annotations

import logging
import re
from pathlib import Path

from rich.console import Console

from app.cli.display import print_account_card, print_accounts_table
from app.core.context import AppContext
from app.filters.aliases import expand_aliases
from app.filters.engine import apply_filter
from app.filters.parser import FilterParseError, parse_filter

logger = logging.getLogger(__name__)

_VANITY_RE = re.compile(r'^[a-zA-Z0-9_-]{3,32}$')


def validate_vanity(vanity: str) -> str:
    """Validate and normalise a Steam vanity name to lowercase."""
    if not _VANITY_RE.match(vanity):
        raise ValueError(
            f'Invalid vanity name: {vanity!r}. '
            f'Must be 3–32 characters, only [a-zA-Z0-9_-] allowed.'
        )
    return vanity.lower()


def parse_account_file(path: Path) -> list[str]:
    """Read a file and return a deduplicated list of normalised vanity names."""
    text = path.read_text(encoding='utf-8')
    tokens = re.split(r'[\s,;]+', text)
    return list(dict.fromkeys(t.strip().lower() for t in tokens if t.strip()))


async def cmd_add(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Add a single account by vanity name."""
    if not args:
        console.print('[yellow]Usage: add <vanity>[/yellow]')
        return

    try:
        vanity = validate_vanity(args[0])
    except ValueError as exc:
        console.print(f'[red]{exc}[/red]')
        return

    if ctx.db.get_account(vanity) is not None:
        console.print(f'[yellow]Already exists: {vanity}[/yellow]')
        return

    ctx.db.add_account(vanity)
    ctx.index.rebuild(ctx.db.all_accounts())
    console.print(f'[green][+] Added: {vanity}[/green]  (sync_status: never_synced)')


async def cmd_import(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Import accounts from a file (newline / space / comma / semicolon delimiters)."""
    if not args:
        console.print('[yellow]Usage: import <filepath>[/yellow]')
        return

    path = Path(args[0])
    if not path.exists():
        console.print(f'[red]File not found: {path}[/red]')
        return

    try:
        tokens = parse_account_file(path)
    except OSError as exc:
        console.print(f'[red]Failed to read file: {exc}[/red]')
        return

    added = 0
    already_in_db = 0
    invalid = 0

    for raw in tokens:
        try:
            vanity = validate_vanity(raw)
        except ValueError:
            invalid += 1
            continue
        if ctx.db.get_account(vanity) is not None:
            already_in_db += 1
            continue
        ctx.db.add_account(vanity)
        added += 1

    ctx.index.rebuild(ctx.db.all_accounts())
    logger.info(f'Import: {added} added, {already_in_db} already in DB, {invalid} invalid')
    console.print(
        f'Tokens: [cyan]{len(tokens)}[/cyan]'
        f'  |  Invalid: [red]{invalid}[/red]'
        f'  |  Already in DB: [yellow]{already_in_db}[/yellow]'
        f'  |  Added: [green]{added}[/green]'
    )


async def cmd_list(ctx: AppContext, console: Console, args: list[str]) -> None:
    """List all accounts, optionally filtered by an expression."""
    accounts = ctx.db.all_accounts()

    if '--filter' in args:
        idx = args.index('--filter')
        expr = ' '.join(args[idx + 1:])
        if not expr:
            console.print('[yellow]Usage: list --filter <expr>[/yellow]')
            return
        try:
            criteria = parse_filter(expr)
            criteria = expand_aliases(criteria, ctx.config.stale_threshold_hours)
            accounts = apply_filter(accounts, criteria)
        except FilterParseError as exc:
            console.print(f'[red]Filter error: {exc}[/red]')
            return

    if not accounts:
        console.print('[dim]No accounts.[/dim]')
        return

    print_accounts_table(console, accounts)
    console.print(f'  [dim]{len(accounts)} account(s)[/dim]')


async def cmd_show(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Show a detailed card for a single account."""
    if not args:
        console.print('[yellow]Usage: show <vanity>[/yellow]')
        return

    vanity = args[0].lower()
    account = ctx.db.get_account(vanity)
    if account is None:
        console.print(f'[red]Account not found: {vanity}[/red]')
        return

    print_account_card(console, account)
