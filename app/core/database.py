from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.models import Account, Database, CURRENT_SCHEMA_VERSION

logger = logging.getLogger(__name__)


class SchemaMismatchError(RuntimeError):
    """Raised when the DB file schema version does not match the application."""


class JsonDatabase:
    """Persistent JSON storage for Steam accounts with atomic save."""

    def __init__(self, db: Database, path: Path) -> None:
        self._db = db
        self._path = path

    @property
    def db(self) -> Database:
        return self._db

    @staticmethod
    def load(path: Path) -> JsonDatabase:
        """Load database from path, creating a new one if the file does not exist."""
        if not path.exists():
            logger.info('DB file not found, creating new database: %s', path)
            instance = JsonDatabase(Database(), path)
            instance.save()
            return instance

        logger.info('Loading database from %s', path)
        data = json.loads(path.read_text(encoding='utf-8'))
        file_version = data.get('schema_version', 'unknown')

        if file_version != CURRENT_SCHEMA_VERSION:
            raise SchemaMismatchError(
                f'DB schema version {file_version!r} does not match expected '
                f'{CURRENT_SCHEMA_VERSION!r}.\n'
                f'File: {path}\n'
                f'Resolution: back up and delete the DB file, '
                f'or use a compatible version of the application.'
            )

        db = Database.model_validate(data)
        logger.info('Loaded %d accounts from database', len(db.accounts))
        return JsonDatabase(db, path)

    def save(self) -> None:
        """Atomically write the database to disk using a unique tmp file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db.db_updated_at = datetime.now(timezone.utc)

        json_data = self._db.model_dump_json(indent=2, exclude_none=True)
        tmp = self._path.with_name(
            f'{self._path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp'
        )
        tmp.write_text(json_data, encoding='utf-8')
        os.replace(tmp, self._path)
        logger.info('Database saved to %s', self._path)

    def add_account(self, vanity: str) -> Account:
        """Create and persist a new account entry with never_synced status."""
        account = Account(vanity_name=vanity)
        self._db.accounts[vanity] = account
        logger.info('Account added: %s', vanity)
        return account

    def update_account(self, account: Account) -> None:
        """Replace an existing account record in memory."""
        account.updated_at = datetime.now(timezone.utc)
        self._db.accounts[account.vanity_name] = account

    def get_account(self, vanity: str) -> Account | None:
        """Return the account by vanity name, or None if not found."""
        return self._db.accounts.get(vanity)

    def all_accounts(self) -> list[Account]:
        """Return all stored accounts as a list."""
        return list(self._db.accounts.values())

    def account_count(self) -> int:
        """Return the total number of stored accounts."""
        return len(self._db.accounts)
