from __future__ import annotations

import logging

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from app.cli.dispatcher import CommandDispatcher

logger = logging.getLogger(__name__)


async def run_shell(dispatcher: CommandDispatcher) -> None:
    """Run the interactive REPL until the dispatcher signals exit or EOF."""
    session: PromptSession[str] = PromptSession(
        '> ',
        history=InMemoryHistory(),
    )

    while dispatcher.running:
        try:
            line = await session.prompt_async()
        except KeyboardInterrupt:
            break
        except EOFError:
            break

        line = line.strip()
        if not line:
            continue

        await dispatcher.dispatch(line)

    logger.info('REPL loop exited')
