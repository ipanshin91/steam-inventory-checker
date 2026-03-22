from __future__ import annotations

import asyncio
import logging
import sys

from rich.console import Console

from app.core.config import AppConfig, load_config
from app.core.context import AppContext
from app.core.database import JsonDatabase, SchemaMismatchError
from app.core.filelock import FileLockManager, DatabaseLockError
from app.core.indexes import AccountIndex
from app.core.logger import setup_logging

console = Console()
logger = logging.getLogger(__name__)


async def run_app(ctx: AppContext) -> None:
    """Main application coroutine. Replaced by full CLI in Stage 3."""
    console.print(
        f'[bold green]Steam Inventory Checker v0.1.0[/bold green]'
        f'  |  Python {sys.version.split()[0]}'
    )
    console.print(
        f'DB: [cyan]{ctx.config.db_path}[/cyan]'
        f'  |  Accounts: [yellow]{ctx.index.total_count}[/yellow]'
    )
    if not ctx.config.proxies:
        console.print(
            f'[yellow][WARNING] No proxies configured. '
            f'Using direct connection with {ctx.config.no_proxy_delay}s delay.[/yellow]'
        )
    else:
        console.print(f'Proxies configured: [green]{len(ctx.config.proxies)}[/green]')

    console.print('[dim]CLI not yet available — Stage 3 pending.[/dim]')


async def async_main(config: AppConfig) -> None:
    """Bootstrap resources, run the application, and guarantee clean shutdown."""
    lock_manager = FileLockManager(config.db_path)

    try:
        lock_manager.acquire()
    except DatabaseLockError as exc:
        console.print(f'[bold red]Error:[/bold red] {exc}')
        return

    db: JsonDatabase | None = None
    try:
        db = JsonDatabase.load(config.db_path)
        index = AccountIndex()
        index.rebuild(db.all_accounts())

        ctx = AppContext(
            config=config,
            db=db,
            index=index,
            lock_manager=lock_manager,
        )

        try:
            await run_app(ctx)
        except KeyboardInterrupt:
            pass

    except SchemaMismatchError as exc:
        console.print(f'[bold red]Schema Error:[/bold red] {exc}')

    finally:
        if db is not None and config.autosave:
            console.print('[dim]Saving DB...[/dim]')
            db.save()
        lock_manager.release()
        logger.info('Application shutdown complete')


def cli_entry() -> None:
    """Synchronous entry point registered in pyproject.toml scripts."""
    config = load_config()
    setup_logging(config.log_path, debug=config.debug_raw_mode)
    logger.info('Starting Steam Inventory Checker')

    loop_factory = None
    if config.loop_acceleration and sys.platform != 'win32':
        try:
            import uvloop  # type: ignore[import-untyped]
            loop_factory = uvloop.new_event_loop
        except ImportError:
            logger.warning('uvloop not installed, using default event loop')

    asyncio.run(async_main(config), loop_factory=loop_factory)


if __name__ == '__main__':
    cli_entry()
