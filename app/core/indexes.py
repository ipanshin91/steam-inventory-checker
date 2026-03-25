from __future__ import annotations

import logging

from app.core.models import (
    Account,
    AccountBanStatus,
    AccountExistsStatus,
    InventoryVisibilityStatus,
    SyncStatus,
)

logger = logging.getLogger(__name__)


class AccountIndex:
    """In-memory lookup tables and aggregate counters over the account collection."""

    def __init__(self) -> None:
        self.by_vanity: dict[str, Account] = {}
        self.by_steam_id: dict[str, Account] = {}

        self.total_count: int = 0
        self.exists_count: int = 0
        self.not_found_count: int = 0
        self.unknown_exists_count: int = 0

        self.vac_banned_count: int = 0
        self.not_banned_count: int = 0
        self.unknown_ban_count: int = 0

        self.public_count: int = 0
        self.private_count: int = 0
        self.unknown_inventory_count: int = 0
        self.empty_public_count: int = 0

        self.success_count: int = 0
        self.partial_success_count: int = 0
        self.failed_count: int = 0
        self.never_synced_count: int = 0

    def rebuild(self, accounts: list[Account]) -> None:
        """Rebuild all indexes and counters from a fresh account list."""
        self.by_vanity = {}
        self.by_steam_id = {}

        self.total_count = 0
        self.exists_count = 0
        self.not_found_count = 0
        self.unknown_exists_count = 0
        self.vac_banned_count = 0
        self.not_banned_count = 0
        self.unknown_ban_count = 0
        self.public_count = 0
        self.private_count = 0
        self.unknown_inventory_count = 0
        self.empty_public_count = 0
        self.success_count = 0
        self.partial_success_count = 0
        self.failed_count = 0
        self.never_synced_count = 0

        for account in accounts:
            self.by_vanity[account.vanity_name] = account
            if account.steam_id64:
                self.by_steam_id[account.steam_id64] = account

            self.total_count += 1

            match account.account_exists_status:
                case AccountExistsStatus.exists:
                    self.exists_count += 1
                case AccountExistsStatus.not_found:
                    self.not_found_count += 1
                case _:
                    self.unknown_exists_count += 1

            match account.account_ban_status:
                case AccountBanStatus.vac_banned:
                    self.vac_banned_count += 1
                case AccountBanStatus.not_banned:
                    self.not_banned_count += 1
                case _:
                    self.unknown_ban_count += 1

            match account.inventory_visibility_status:
                case InventoryVisibilityStatus.public:
                    self.public_count += 1
                    if account.items_count_total == 0:
                        self.empty_public_count += 1
                case InventoryVisibilityStatus.private:
                    self.private_count += 1
                case _:
                    self.unknown_inventory_count += 1

            match account.sync_status:
                case SyncStatus.success:
                    self.success_count += 1
                case SyncStatus.partial_success:
                    self.partial_success_count += 1
                case SyncStatus.failed:
                    self.failed_count += 1
                case _:
                    self.never_synced_count += 1

        logger.debug('Index rebuilt: %d accounts', self.total_count)
