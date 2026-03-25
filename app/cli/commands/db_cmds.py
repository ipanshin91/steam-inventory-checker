from __future__ import annotations

import logging

from rich.console import Console

from app.core.context import AppContext
from app.core.database import JsonDatabase, SchemaMismatchError
from app.core.indexes import AccountIndex

logger = logging.getLogger(__name__)


async def cmd_save(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Force-save the database to disk."""
    ctx.db.save()
    console.print('[green]DB saved.[/green]')


async def cmd_reload(ctx: AppContext, console: Console, args: list[str]) -> None:
    """Reload the database from disk and rebuild in-memory indexes."""
    try:
        new_db = JsonDatabase.load(ctx.config.db_path)
    except SchemaMismatchError as exc:
        console.print(f'[red]Schema error: {exc}[/red]')
        return
    except OSError as exc:
        console.print(f'[red]Failed to reload DB: {exc}[/red]')
        return

    ctx.db = new_db
    ctx.index = AccountIndex()
    ctx.index.rebuild(ctx.db.all_accounts())
    logger.info('Database reloaded: %d accounts', ctx.index.total_count)
    console.print(f'[green]Reloaded.[/green]  Accounts: [yellow]{ctx.index.total_count}[/yellow]')
