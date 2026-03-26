from __future__ import annotations

import logging
from typing import Callable

from rich.console import Console

from app.cli.display import print_stats
from app.core.context import AppContext

logger = logging.getLogger(__name__)

_HELP_TEXT = """\
[bold]Account management:[/bold]
  add <vanity>                Add account [dim](3-32 chars, [a-zA-Z0-9_-])[/dim]
  import <filepath>           Import accounts from file
  list [--filter <expr>]      List accounts
  show <vanity>               Show account details

[bold]Search and filter[/bold] [dim](offline, no network):[/dim]
  find <query>                Find item by name (partial match)
  filter <expr>               Filter accounts
  sort <field> [asc|desc]     Sort accounts

[bold]Sync[/bold] [dim](blocking — REPL pauses until complete):[/dim]
  sync one <vanity>           Sync one account
  sync all                    Sync all accounts
  sync filter <expr>          Sync accounts matching filter
  reprice [one <vanity>]      Re-fetch prices without re-syncing inventory

[bold]Database:[/bold]
  save                        Force save DB to disk
  reload                      Reload DB from disk

[bold]Other:[/bold]
  stats                       Full DB statistics
  help                        Show this help
  exit / quit                 Exit with autosave\
"""


async def cmd_stats(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Display database and proxy statistics."""
    print_stats(console, ctx.index, ctx.db.db.schema_version, ctx.proxy_manager)


async def cmd_help(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Print the command reference."""
    console.print(_HELP_TEXT)


async def cmd_exit(
    ctx: AppContext,
    console: Console,
    args: list[str],
    stop: Callable[[], None],
) -> None:
    """Signal graceful shutdown."""
    stop()
