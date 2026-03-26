from __future__ import annotations

import asyncio
import logging
import sys

from rich.console import Console

from app.cli.dispatcher import CommandDispatcher
from app.cli.shell import run_shell
from app.core.config import AppConfig, load_config
from app.core.context import AppContext
from app.core.database import JsonDatabase, SchemaMismatchError
from app.core.filelock import DatabaseLockError, FileLockManager
from app.core.indexes import AccountIndex
from app.core.logger import setup_logging
from app.proxy.health import ProxyHealthChecker
from app.proxy.manager import ProxyManager
from app.steam.client import SteamHttpClient

console = Console()
logger = logging.getLogger(__name__)


def _print_banner(ctx: AppContext) -> None:
    console.print(
        f'[bold green]Steam Inventory Checker v0.1.0[/bold green]'
        f'  |  Python {sys.version.split()[0]}'
    )
    console.print(
        f'DB: [cyan]{ctx.config.db_path}[/cyan]'
        f'  |  Accounts: [yellow]{ctx.index.total_count}[/yellow]'
    )
    if ctx.proxy_manager.is_direct_mode:
        console.print(
            f'[yellow][WARNING] No proxies configured. '
            f'Using direct connection with {ctx.config.request_delay}s delay per request.[/yellow]'
        )
    else:
        console.print(
            f'Proxies configured: [green]{len(ctx.config.proxies)}[/green]'
        )


async def async_main(config: AppConfig) -> None:
    """Bootstrap resources, run the CLI shell, and guarantee clean shutdown."""
    lock_manager = FileLockManager(config.db_path)

    try:
        lock_manager.acquire()
    except DatabaseLockError as exc:
        console.print(f'[bold red]Error:[/bold red] {exc}')
        return

    http_client = SteamHttpClient(config)
    proxy_manager = ProxyManager(config)
    health_checker = ProxyHealthChecker(proxy_manager, http_client)
    health_task = health_checker.start()

    try:
        db = JsonDatabase.load(config.db_path)
    except SchemaMismatchError as exc:
        console.print(f'[bold red]Schema Error:[/bold red] {exc}')
        health_task.cancel()
        await asyncio.gather(health_task, return_exceptions=True)
        await http_client.close()
        lock_manager.release()
        return

    index = AccountIndex()
    index.rebuild(db.all_accounts())

    ctx = AppContext(
        config=config,
        db=db,
        index=index,
        lock_manager=lock_manager,
        http_client=http_client,
        proxy_manager=proxy_manager,
    )

    _print_banner(ctx)

    try:
        dispatcher = CommandDispatcher(ctx, console)
        await run_shell(dispatcher)
    finally:
        health_task.cancel()
        await asyncio.gather(health_task, return_exceptions=True)
        await http_client.close()
        if config.autosave:
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
