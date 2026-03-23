from __future__ import annotations

import logging
import shlex
from typing import Awaitable, Callable

from rich.console import Console

from app.cli.commands.account import cmd_add, cmd_import, cmd_list, cmd_show
from app.cli.commands.db_cmds import cmd_reload, cmd_save
from app.cli.commands.meta import cmd_exit, cmd_help, cmd_stats
from app.cli.commands.search import cmd_filter, cmd_find, cmd_sort
from app.cli.commands.sync_cmds import cmd_sync
from app.core.context import AppContext

logger = logging.getLogger(__name__)

Handler = Callable[[list[str]], Awaitable[None]]


class CommandDispatcher:
    """Routes parsed input lines to async command handlers."""

    def __init__(self, ctx: AppContext, console: Console) -> None:
        self._console = console
        self._running = True
        self._registry: dict[str, Handler] = self._build(ctx, console)

    def _build(self, ctx: AppContext, console: Console) -> dict[str, Handler]:
        stop = self.stop
        return {
            'add':    lambda a: cmd_add(ctx, console, a),
            'import': lambda a: cmd_import(ctx, console, a),
            'list':   lambda a: cmd_list(ctx, console, a),
            'show':   lambda a: cmd_show(ctx, console, a),
            'find':   lambda a: cmd_find(ctx, console, a),
            'filter': lambda a: cmd_filter(ctx, console, a),
            'sort':   lambda a: cmd_sort(ctx, console, a),
            'sync':   lambda a: cmd_sync(ctx, console, a),
            'save':   lambda a: cmd_save(ctx, console, a),
            'reload': lambda a: cmd_reload(ctx, console, a),
            'stats':  lambda a: cmd_stats(ctx, console, a),
            'help':   lambda a: cmd_help(ctx, console, a),
            'exit':   lambda a: cmd_exit(ctx, console, a, stop),
            'quit':   lambda a: cmd_exit(ctx, console, a, stop),
        }

    @property
    def running(self) -> bool:
        return self._running

    def stop(self) -> None:
        """Signal the REPL loop to exit after the current command."""
        self._running = False

    async def dispatch(self, line: str) -> None:
        """Parse and dispatch a single input line to its handler."""
        if not line:
            return

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            self._console.print(f'[red]Parse error: {exc}[/red]')
            return

        cmd = parts[0].lower()
        args = parts[1:]

        handler = self._registry.get(cmd)
        if handler is None:
            self._console.print(
                f'[red]Unknown command: {cmd!r}[/red]  [dim]Type help for available commands.[/dim]'
            )
            return

        try:
            await handler(args)
        except Exception as exc:
            logger.exception(f'Unhandled error in command {cmd!r}')
            self._console.print(f'[bold red]Error:[/bold red] {exc}')
