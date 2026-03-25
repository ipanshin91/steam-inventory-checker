from __future__ import annotations

import logging
from pathlib import Path

from filelock import FileLock, Timeout

logger = logging.getLogger(__name__)


class DatabaseLockError(RuntimeError):
    """Raised when the database lock cannot be acquired."""


class FileLockManager:
    """Prevents concurrent access to the same JSON database file."""

    def __init__(self, db_path: Path) -> None:
        self._lock_path = db_path.with_suffix('.lock')
        self._lock = FileLock(str(self._lock_path), timeout=1)

    def acquire(self) -> None:
        """Acquire the exclusive database lock. Raises DatabaseLockError on timeout."""
        try:
            self._lock.acquire()
            logger.info('Database lock acquired: %s', self._lock_path)
        except Timeout:
            raise DatabaseLockError(
                f'Cannot acquire database lock: {self._lock_path}\n'
                f'Another instance may already be running with the same database.'
            )

    def release(self) -> None:
        """Release the database lock."""
        self._lock.release()
        logger.info('Database lock released: %s', self._lock_path)

    def __enter__(self) -> FileLockManager:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
