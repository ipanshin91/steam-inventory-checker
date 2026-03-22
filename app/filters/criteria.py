from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.models import (
    AccountBanStatus,
    AccountExistsStatus,
    InventoryVisibilityStatus,
    SyncStatus,
)


class RangeFilter(BaseModel):
    """Numeric range constraint with optional gte/lte/gt/lt bounds."""

    gte: int | None = None
    lte: int | None = None
    gt: int | None = None
    lt: int | None = None


class DateFilter(BaseModel):
    """Datetime range constraint with optional before/after bounds."""

    before: datetime | None = None
    after: datetime | None = None


class FilterCriteria(BaseModel):
    """Filter parameters for offline account queries and selective sync."""

    account_exists_status: AccountExistsStatus | None = None
    account_ban_status: AccountBanStatus | None = None
    inventory_visibility_status: InventoryVisibilityStatus | None = None
    sync_status: SyncStatus | None = None
    has_items: bool | None = None
    has_marketable_items: bool | None = None
    has_tradable_items: bool | None = None
    items_count_total: RangeFilter | None = None
    items_count_distinct: RangeFilter | None = None
    last_successful_sync_at: DateFilter | None = None
    last_sync_attempt_at: DateFilter | None = None

    inventory_empty: bool | None = None
    inventory_non_empty: bool | None = None
    stale: bool | None = None
    failed_last_sync: bool | None = None


class SortSpec(BaseModel):
    """Sort specification for account listing."""

    field: Literal[
        'items_count_total',
        'items_count_distinct',
        'last_successful_sync_at',
        'sync_status',
        'total_value',
    ]
    direction: Literal['asc', 'desc'] = 'desc'
