from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

CURRENT_SCHEMA_VERSION = '1.0'


class AccountExistsStatus(StrEnum):
    exists = 'exists'
    not_found = 'not_found'
    unknown = 'unknown'


class AccountBanStatus(StrEnum):
    vac_banned = 'vac_banned'
    not_banned = 'not_banned'
    unknown = 'unknown'


class InventoryVisibilityStatus(StrEnum):
    public = 'public'
    private = 'private'
    unknown = 'unknown'


class SyncStatus(StrEnum):
    never_synced = 'never_synced'
    success = 'success'
    partial_success = 'partial_success'
    failed = 'failed'


class SyncErrorCategory(StrEnum):
    none = 'none'
    invalid_input = 'invalid_input'
    resolution_failed = 'resolution_failed'
    profile_not_found = 'profile_not_found'
    inventory_private = 'inventory_private'
    source_temporary_failure = 'source_temporary_failure'
    source_rate_limited = 'source_rate_limited'
    proxy_failure = 'proxy_failure'
    parse_failure = 'parse_failure'
    internal_error = 'internal_error'


class Item(BaseModel):
    """A single CS2 inventory item."""

    display_name: str
    market_hash_name: str
    quantity: int = 1
    marketable: bool = False
    commodity: bool = False
    type: str | None = None
    tags: list[dict[str, str]] = Field(default_factory=list)
    icon_url: str | None = None

    price: float | None = None
    price_updated_at: datetime | None = None
    currency: str | None = None


class Account(BaseModel):
    """Steam account with profile data and CS2 inventory state."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vanity_name: str

    steam_id64: str | None = None
    profile_url: str | None = None
    display_name: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_sync_attempt_at: datetime | None = None
    last_successful_sync_at: datetime | None = None

    account_exists_status: AccountExistsStatus = AccountExistsStatus.unknown
    account_ban_status: AccountBanStatus = AccountBanStatus.unknown
    inventory_visibility_status: InventoryVisibilityStatus = InventoryVisibilityStatus.unknown
    sync_status: SyncStatus = SyncStatus.never_synced
    sync_error_category: SyncErrorCategory = SyncErrorCategory.none

    items_count_total: int = 0
    items_count_distinct: int = 0
    marketable_items_count: int = 0
    total_inventory_value: float | None = None

    items: list[Item] = Field(default_factory=list)


class Database(BaseModel):
    """Top-level JSON database structure."""

    schema_version: str = CURRENT_SCHEMA_VERSION
    db_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    db_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    accounts: dict[str, Account] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
